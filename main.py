# ============================================================
#  Stream Subs — local live subtitles for Streamlabs / OBS
#  Stream Subs — локальные субтитры в реальном времени
# ------------------------------------------------------------
#  Mic  ->  VAD  ->  Whisper (ru->en)  ->  WebSocket  ->  Browser
#  Микрофон  ->  VAD  ->  Whisper (ru->en)  ->  WebSocket  ->  Браузер
#
#  Web UI:    http://127.0.0.1:8000/          — subtitles / субтитры
#  Settings:  http://127.0.0.1:8000/settings  — settings / настройки
# ============================================================

import sys, queue, time, threading, asyncio, json, re
from pathlib import Path
from datetime import datetime
import numpy as np
import sounddevice as sd
import ctranslate2
from silero_vad import load_silero_vad, VADIterator
from faster_whisper import WhisperModel
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import FileResponse, JSONResponse
import uvicorn
import requests

# ------------------------------------------------------------
#  Audio / Аудио
# ------------------------------------------------------------
SR = 16000          # sample rate / частота дискретизации
BLK = 512           # block size / размер блока
MIN_SEC = 0.8       # minimum speech length / минимальная длина речи
import os as _os
MODEL = _os.environ.get("STREAMSUBS_MODEL", "medium")    # tiny|base|small|medium|large-v3
COMPUTE_OVERRIDE = _os.environ.get("STREAMSUBS_COMPUTE", "")  # float16|int8|int8_float16

# ------------------------------------------------------------
#  Server / Сервер
# ------------------------------------------------------------
HOST = "127.0.0.1"
PORT = 8000

# ------------------------------------------------------------
#  Version / Версия и проверка обновлений
# ------------------------------------------------------------
APP_VERSION = "1.2.0"
GITHUB_REPO = "TenLux-dev/Stream-Subs"
GITHUB_RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
UPDATE_TIMEOUT = 8
_update_cache = {"checked": False, "result": None}


def _version_tuple(v):
    parts = []
    for chunk in str(v).strip().lstrip("vV").split("."):
        num = ""
        for ch in chunk:
            if ch.isdigit():
                num += ch
            else:
                break
        parts.append(int(num) if num else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def check_update(force=False):
    """Проверка новой версии на GitHub. Возвращает dict или None при ошибке сети."""
    if _update_cache["checked"] and not force:
        return _update_cache["result"]
    info = None
    try:
        resp = requests.get(
            GITHUB_RELEASES_API,
            timeout=UPDATE_TIMEOUT,
            headers={"Accept": "application/vnd.github+json", "User-Agent": f"StreamSubs/{APP_VERSION}"},
        )
        if resp.status_code == 200:
            data = resp.json()
            latest = (data.get("tag_name") or "").strip()
            if latest:
                has_update = _version_tuple(latest) > _version_tuple(APP_VERSION)
                info = {
                    "current": APP_VERSION,
                    "latest": latest.lstrip("vV"),
                    "hasUpdate": has_update,
                    "url": data.get("html_url") or f"https://github.com/{GITHUB_REPO}/releases",
                    "publishedAt": data.get("published_at"),
                }
                if has_update:
                    print(f"[UPDATE] Доступна новая версия {latest} (текущая {APP_VERSION}): {info['url']}")
                    print(f"[UPDATE] New version {latest} available (current {APP_VERSION})")
    except Exception as exc:
        print(f"[UPDATE] Не удалось проверить обновления: {exc}")
        info = None
    _update_cache["checked"] = True
    _update_cache["result"] = info
    return info


# ------------------------------------------------------------
#  Paths / Пути
# ------------------------------------------------------------
import sys
import os
from pathlib import Path
_env_base = os.environ.get("STREAMSUBS_BASE_DIR")
if _env_base:
    BASE_DIR = Path(_env_base)
elif getattr(sys, "frozen", False):
    # PyInstaller bundle / сборка PyInstaller
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
LOG_PATH = BASE_DIR / "whisper_log.txt"
LISTS_DIR = BASE_DIR / "lists"

# ------------------------------------------------------------
#  Autostart / Автозапуск (Windows, HKCU\...\Run)
# ------------------------------------------------------------
AUTOSTART_NAME = "StreamSubs"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_command():
    """Команда для HKCU\\...\\Run или None, если автозапуск невозможен.

    Установленная версия: "<install dir>\\StreamSubs.exe" --desktop.
    Dev-запуск: pythonw.exe desktop.py --desktop (чтобы автозапуск тоже
    открывал настольное окно, а не голый сервер).
    Installed build: '<install dir>\\StreamSubs.exe' --desktop.
    Dev run: pythonw desktop.py --desktop.
    """
    exe = BASE_DIR / "StreamSubs.exe"
    if exe.exists():
        return f'"{exe}" --desktop'
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --desktop'
    desktop = BASE_DIR / "desktop.py"
    if desktop.exists():
        py = Path(sys.executable)
        pyw = py.with_name("pythonw.exe")
        if pyw.exists():
            py = pyw
        return f'"{py}" "{desktop}" --desktop'
    return None


def autostart_read():
    """Прочитать текущее значение Run. Возвращает (value, error)."""
    try:
        import winreg
    except ImportError:
        return None, "Windows registry is not available"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ)
    except FileNotFoundError:
        return None, None
    except OSError as exc:
        return None, str(exc)
    try:
        value, _ = winreg.QueryValueEx(key, AUTOSTART_NAME)
        return value, None
    except FileNotFoundError:
        return None, None
    except OSError as exc:
        return None, str(exc)
    finally:
        key.Close()


def autostart_write(command):
    """Включить автозапуск / enable autostart."""
    import winreg
    key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE)
    try:
        winreg.SetValueEx(key, AUTOSTART_NAME, 0, winreg.REG_SZ, command)
    finally:
        key.Close()


def autostart_delete():
    """Выключить автозапуск / disable autostart."""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE)
    except (ImportError, FileNotFoundError):
        return
    try:
        winreg.DeleteValue(key, AUTOSTART_NAME)
    except FileNotFoundError:
        pass
    finally:
        key.Close()

# ------------------------------------------------------------
#  Default appearance config / Настройки внешнего вида по умолчанию
# ------------------------------------------------------------
DEFAULT_CONFIG = {
    "googleFont": "",                                  # Google Font name / имя
    "fontFamily": '"Segoe UI", Arial, sans-serif',     # fallback
    "fontSize": 42,                                    # px
    "fontWeight": 700,                                 # 400..900
    "color": "#ffffff",                                # hex
    "bottom": 80,                                      # px from bottom / отступ снизу
    "maxWidth": 80,                                    # % of viewport / % ширины
    "timeout": 6000,                                   # ms after last chunk / мс
    "maxChars": 80,                                    # split into chunks / символов в куске
    "chunkTime": 2500,                                 # ms per chunk / мс на кусок
    "historyLines": 1,                                 # previous lines visible / прошлых строк
    "textShadow": "0 0 8px #000, 0 0 4px #000, 2px 2px 4px #000",
    "testBackground": "transparent",                   # for preview / для предпросмотра
}


# ============================================================
#  LISTS (lists/*.txt) — editable without restart
#  СПИСКИ (lists/*.txt) — правятся без перезапуска
# ============================================================

DEFAULT_BANNED = """# ============================================================
#  BANNED WORDS / ЗАПРЕЩЁННЫЕ СЛОВА
# ------------------------------------------------------------
#  One word or phrase per line. Case-insensitive.
#  Одно слово или фраза на строку. Регистр не важен.
#  Lines starting with # are comments.
#  Строки, начинающиеся с # — комментарии.
#  Changes apply automatically on save.
#  Изменения применяются автоматически при сохранении.
# ============================================================

# --- [En] English profanity ---
fuck
fucking
fucker
shit
damn
bitch
bastard
cunt
asshole
dick
cock
pussy
whore
slut

# --- [En] Slurs / hate speech ---
nigger
nigga
faggot
retard
kys
rape
nazi
hitler
terrorist
incel
simp

# --- [Ru] Русский мат ---
хуй
хуя
хую
пизда
пиздец
бля
блядь
блять
ебать
ебал
мудак
мудила
гандон
долбоёб
залупа
манда

# --- [Ru] Оскорбления ---
пидор
пидар
педик
гомик
пидорас

# --- [Ru/En] Ненависть / Hate speech ---
москаль
хохол
хач
чурка
нигер
жид
ватник
колорад
рашист
свидомит
бандеровец
расист
расизм
гомофоб
ненависть
дискриминация

# --- [Ru/En] Насилие / Violence ---
убийство
убить
насилие
терроризм
теракт
бомба
взрыв
оружие
пистолет
автомат
kill
murder
bomb

# --- [Ru/En] Наркотики / Drugs ---
наркотик
марихуана
кокаин
героин
мефедрон
drugs
cocaine
heroin

# --- [Ru/En] NSFW ---
секс
порнография
порно
эротика
оргазм
sex
sexy
nsfw
nude
naked
"""

DEFAULT_HALLUCINATIONS = """# ============================================================
#  WHISPER HALLUCINATIONS / ГАЛЛЮЦИНАЦИИ WHISPER
# ------------------------------------------------------------
#  Phrases Whisper invents on silence / noise / short clips.
#  Фразы, которые Whisper придумывает на тишине, шуме, обрывках.
#  One phrase per line. Case-insensitive.
#  Одна фраза на строку. Регистр не важен.
# ============================================================

# --- [En] English hallucinations ---
thank you
thanks
thanks for watching
thank you for watching
please subscribe
subscribe
bye
bye bye
okay
you
yeah
hmm
uh
um
good job
well done
see you soon
see you next time
this is a translation
quiet advice
just great
music
[music]
(music)
the end
we'll be right back
translate naturally
translated by
subtitles by
amara.org
subtitle
subtitles

# --- [Ru] Русские галлюцинации ---
продолжение следует
спасибо за просмотр
субтитры сделал
субтитры подогнал
редактор субтитров
корректор
до встречи
пока
пока-пока
спасибо
подписывайтесь
подпишись
ставьте лайк
"""

DEFAULT_PATTERNS = """# ============================================================
#  REGEX PATTERNS / РЕГУЛЯРНЫЕ ВЫРАЖЕНИЯ
# ------------------------------------------------------------
#  One Python regex per line. Case-insensitive.
#  Одно регулярное выражение на строку. Регистр не важен.
#  Used to catch banned words inside phrases.
#  Используется для поиска слов внутри фраз.
#  If a line is broken, it is skipped with an error message.
#  Если строка сломана — она пропускается с сообщением об ошибке.
# ============================================================

# --- [En] English patterns ---
^translated by
^subtitles? by
^edited by
^amara\\.org
^www\\.
^thank you
^this is
^quiet
\\bfuck
\\bshit
\\bbitch

# --- [Ru] Русские паттерны (мат как часть слова) ---
хуй|хуя|хую|хуё|хуе
пизд
бляд|блят
ебал|ебёт|ебет|ебат|ебуч|ёбан|ебан
пидор|пидар|пидр
мудак|мудил
"""

DEFAULT_SLANG = """# ============================================================
#  SLANG / MEMES — REPLACEMENTS / СЛЕНГ И МЕМЫ — ЗАМЕНЫ
# ------------------------------------------------------------
#  Format: key = value
#  Формат:  ключ = значение
#  Key   — what Whisper returned (lowercase, no trailing dot).
#  Ключ  — то, что вернул Whisper (нижний регистр, без точки).
#  Value — what to show in subtitles.
#  Значение — то, что показываем в субтитрах.
# ============================================================

# --- [Ru] Мем "я 415 база" ---
315th base = I'm 415 based
415 base = I'm 415 based
base 15 = based
base = based
i'm base = I'm based
я база = I'm based

# --- [Ru] "А в ответ тишина" ---
silence = and in response — silence
why don't we answer = and in response — silence
"""


def ensure_lists():
    """Create lists/ folder and default txt files / создаёт папку и файлы."""
    LISTS_DIR.mkdir(exist_ok=True)
    defaults = {
        "banned_words.txt": DEFAULT_BANNED,
        "hallucinations.txt": DEFAULT_HALLUCINATIONS,
        "patterns.txt": DEFAULT_PATTERNS,
        "slang.txt": DEFAULT_SLANG,
    }
    for name, content in defaults.items():
        p = LISTS_DIR / name
        if not p.exists():
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
            print("Создан файл / Created: " + str(p))


# Cache with mtime check — files re-read automatically when edited
# Кэш с проверкой mtime — файлы перечитываются при изменении
_cache = {}


def _load_file(path, kind):
    """kind: 'set' | 'patterns' | 'slang'"""
    if not path.exists():
        return set() if kind == "set" else ([] if kind == "patterns" else {})
    mtime = path.stat().st_mtime
    key = str(path)
    cached = _cache.get(key)
    if cached and cached[0] == mtime:
        return cached[1]

    result = set() if kind == "set" else ([] if kind == "patterns" else {})
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if kind == "set":
                result.add(line.lower())
            elif kind == "patterns":
                try:
                    result.append(re.compile(line, re.IGNORECASE))
                except re.error as e:
                    print("Regex error in patterns.txt: " + str(e) + " -> " + line)
            else:
                if "=" in line:
                    k, v = line.split("=", 1)
                    result[k.strip().lower()] = v.strip()
    _cache[key] = (mtime, result)
    return result


def get_banned():
    return _load_file(LISTS_DIR / "banned_words.txt", "set")


def get_hallucinations():
    return _load_file(LISTS_DIR / "hallucinations.txt", "set")


def get_patterns():
    return _load_file(LISTS_DIR / "patterns.txt", "patterns")


def get_slang():
    return _load_file(LISTS_DIR / "slang.txt", "slang")


# ============================================================
#  FILTERING / ФИЛЬТРАЦИЯ
# ============================================================

def fix_slang(text):
    """Replace memes / заменяем мемы на нормальный перевод."""
    t = text.strip()
    tl = t.lower().rstrip(".!")
    slang = get_slang()
    if tl in slang:
        return slang[tl]
    for k, v in slang.items():
        if k in tl and len(tl) <= len(k) + 10:
            return v
    return text


def is_hallucination(text):
    """Return True if text should be dropped / True — если фразу отбрасываем."""
    t = text.strip().lower().rstrip("!.,?…")
    if not t:
        return True
    if t in get_banned():
        return True
    if t in get_hallucinations():
        return True
    for pat in get_patterns():
        if pat.search(t):
            return True
    if len(t.split()) <= 1 and len(t) <= 6:
        return True
    if re.match(r"^\d+$", t):
        return True
    return False


def dedupe_loops(text):
    """Collapse Whisper repetition loops / схлопываем циклы повторов.

    Whisper на шуме любит выдавать одну и ту же фразу десятки раз
    ("the driver went to heaven" x14). Убираем подряд идущие дубли
    предложений и повторяющиеся куски фраз, режем абсурдно длинный текст.
    """
    t = (text or "").strip()
    if not t:
        return ""

    # 1) collapse consecutive duplicate sentences
    parts = re.split(r'(?<=[.!?])\s+', t)
    out = []
    prev = None
    for p in parts:
        p = p.strip()
        if not p:
            continue
        norm = re.sub(r'\s+', ' ', p.lower().strip(' .,!?…'))
        if prev is not None and norm == prev:
            continue
        out.append(p)
        prev = norm
    t = ' '.join(out).strip()

    # 2) collapse any repeated run of words (longest match first)
    words = t.split()
    i = 0
    while i < len(words):
        collapsed = False
        maxp = min(12, (len(words) - i) // 2)
        for p in range(maxp, 1, -1):
            reps = 1
            j = i + p
            while j + p <= len(words) and words[j:j + p] == words[i:i + p]:
                reps += 1
                j += p
            if reps >= 2:
                del words[i + p:j]
                collapsed = True
                break
        if collapsed:
            continue
        i += 1

    # 3) hard cap: nothing sane is longer than ~60 words
    if len(words) > 60:
        words = words[:60]
    return ' '.join(words)


def log_event(kind, text, sec=None, dt=None):
    """Append to whisper_log.txt / пишем в лог."""
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            extra = ""
            if sec is not None:
                extra += f" len={sec:.2f}s"
            if dt is not None:
                extra += f" whisper={dt:.2f}s"
            f.write(f"[{ts}] [{kind}]{extra} {text!r}\n")
    except Exception:
        pass


# ============================================================
#  CONFIG / КОНФИГ
# ============================================================

def load_config():
    cfg = DEFAULT_CONFIG.copy()
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ============================================================
#  WEB SERVER / ВЕБ-СЕРВЕР
# ============================================================

app = FastAPI()


# Global pause flag / Глобальный флаг паузы.
# Tray menu and /api/pause set it; audio_loop reads it and, while paused,
# skips transcription and never broadcasts subtitles. Toggle via the tray.
# Трей и /api/pause переключают флаг; audio_loop при паузе пропускает
# распознавание и не отправляет субтитры. Переключение — из трея.
PAUSED = False


@app.get("/api/update")
def api_update():
    """Информация о доступном обновлении / update info."""
    return {"current": APP_VERSION, "update": check_update(force=True)}
clients = set()
loop_ref = {"loop": None}


@app.get("/")
async def root():
    """Subtitles page / страница субтитров."""
    return FileResponse(str(BASE_DIR / "web" / "index.html"))


@app.get("/settings")
async def settings_page():
    """Settings UI / страница настроек."""
    return FileResponse(str(BASE_DIR / "web" / "settings.html"))


@app.get("/api/config")
async def get_config():
    return load_config()


@app.post("/api/config")
async def post_config(request: Request):
    data = await request.json()
    cfg = load_config()
    cfg.update(data)
    save_config(cfg)
    return {"ok": True, "config": cfg}


@app.post("/api/config/reset")
async def reset_config():
    save_config(DEFAULT_CONFIG)
    return {"ok": True, "config": DEFAULT_CONFIG}


# ------------------------------------------------------------
#  Pause / Пауза — управление из трея и API
# ------------------------------------------------------------

@app.get("/api/pause")
def api_pause_get():
    """Текущее состояние паузы / current pause state."""
    return {"paused": PAUSED}


@app.post("/api/pause")
def api_pause_set():
    """Поставить субтитры на паузу / pause subtitles."""
    global PAUSED
    PAUSED = True
    print("[PAUSE] Распознавание приостановлено / subtitles paused")
    return {"paused": PAUSED, "ok": True}


@app.post("/api/resume")
def api_resume_set():
    """Снять паузу / resume subtitles."""
    global PAUSED
    PAUSED = False
    print("[PAUSE] Распознавание продолжено / subtitles resumed")
    return {"paused": PAUSED, "ok": True}


# ------------------------------------------------------------
#  Autostart / Автозапуск — настройки и HKCU\...\Run
# ------------------------------------------------------------

@app.get("/api/autostart")
def api_autostart_get():
    """Состояние автозапуска / autostart state."""
    current, read_error = autostart_read()
    target = autostart_command()
    return {
        "enabled": bool(current),
        "command": current,
        "target": target,
        "supported": target is not None,
        "error": read_error,
    }


@app.post("/api/autostart")
async def api_autostart_set(request: Request):
    """Включить/выключить автозапуск / toggle autostart.

    Body: {"enabled": true|false}. Без поля enabled — переключить.
    """
    try:
        data = await request.json()
    except Exception:
        data = {}
    current, _ = autostart_read()
    enabled = data.get("enabled")
    if enabled is None:
        enabled = not bool(current)
    enabled = bool(enabled)

    if enabled:
        command = autostart_command()
        if not command:
            return JSONResponse(
                {
                    "ok": False,
                    "enabled": bool(current),
                    "error": "Автозапуск доступен только в установленной версии Windows / "
                             "Autostart is available only in the installed Windows build.",
                },
                status_code=409,
            )
        try:
            autostart_write(command)
        except Exception as exc:
            return JSONResponse(
                {"ok": False, "enabled": bool(current), "error": str(exc)},
                status_code=500,
            )
        print("[AUTOSTART] Включён / enabled: " + command)
        return {"ok": True, "enabled": True, "command": command}

    try:
        autostart_delete()
    except Exception as exc:
        return JSONResponse(
            {"ok": False, "enabled": bool(current), "error": str(exc)},
            status_code=500,
        )
    print("[AUTOSTART] Выключен / disabled")
    return {"ok": True, "enabled": False, "command": None}


@app.get("/api/lists/stats")
async def lists_stats():
    """How many entries loaded from each list / сколько записей загружено."""
    return {
        "banned": len(get_banned()),
        "hallucinations": len(get_hallucinations()),
        "patterns": len(get_patterns()),
        "slang": len(get_slang()),
    }


@app.websocket("/ws")
async def ws(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    try:
        await ws.send_text(json.dumps({"text": "WebSocket connected"}))
    except Exception:
        pass
    try:
        while True:
            await ws.receive_text()
    except Exception:
        pass
    finally:
        clients.discard(ws)


def broadcast(text):
    """Send text to all WebSocket clients / рассылаем текст всем клиентам."""
    loop = loop_ref["loop"]
    if loop is None:
        return
    payload = json.dumps({"text": text})
    for c in list(clients):
        asyncio.run_coroutine_threadsafe(c.send_text(payload), loop)


# ============================================================
#  AUDIO / АУДИО
# ============================================================

def find_input():
    """Return default input device index / индекс устройства ввода."""
    try:
        d = sd.default.device[0]
        if d is not None and d >= 0:
            return d
    except Exception:
        pass
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0:
            return i
    return None


def load_whisper():
    """Load Whisper on GPU if CUDA available, else CPU.
    Загружаем Whisper на GPU, если CUDA доступна, иначе на CPU."""
    if ctranslate2.get_cuda_device_count() > 0:
        dev, ct = "cuda", "float16"
    else:
        dev, ct = "cpu", "int8"
    print("Whisper: " + dev + " / " + ct)
    return WhisperModel(MODEL, device=dev, compute_type=ct)


def transcribe(m, audio):
    """Transcribe ru -> en / распознаём и переводим ru -> en."""
    segs, _ = m.transcribe(
        audio,
        language="ru",
        task="translate",
        beam_size=1,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=300),
        condition_on_previous_text=False,
        no_speech_threshold=0.4,
        log_prob_threshold=-1.5,
        compression_ratio_threshold=2.4,
        temperature=0.0,
    )
    return " ".join(s.text.strip() for s in segs).strip()


def audio_loop():
    """Main audio thread / главный аудио-поток."""
    device = find_input()
    if device is None:
        print("No input device! / Не найдено устройство ввода!")
        return
    print("Device #" + str(device) + ": " + sd.query_devices(device)["name"])

    print("Loading VAD... / Загружаю VAD...")
    vad = VADIterator(load_silero_vad(), threshold=0.5, sampling_rate=SR,
                      min_silence_duration_ms=400, speech_pad_ms=500)
    print("Loading Whisper (" + MODEL + ")... / Загружаю Whisper...")
    whisper = load_whisper()
    print("Ready. Speak! / Готово. Говорите!")
    print("Log / Лог:    " + str(LOG_PATH))
    print("Lists / Списки: " + str(LISTS_DIR))

    q = queue.Queue()

    def cb(indata, frames, ti, status):
        q.put(indata[:, 0].copy())

    buf = []
    speaking = False

    with sd.InputStream(device=device, channels=1, samplerate=SR,
                        blocksize=BLK, dtype="float32", callback=cb):
        # clear stale audio / очищаем очередь от старого звука
        while not q.empty():
            q.get_nowait()
        while True:
            chunk = q.get()
            r = vad(chunk, return_seconds=True)
            if r and "start" in r:
                speaking = True
                buf = []
            if speaking:
                buf.append(chunk)
            if r and "end" in r:
                speaking = False
                if buf:
                    audio = np.concatenate(buf)
                    sec = len(audio) / SR
                    if sec < MIN_SEC:
                        pass  # too short / слишком коротко
                    elif PAUSED:
                        # Pause mode: skip recognition entirely to save GPU/CPU
                        # and never broadcast subtitles while paused.
                        # Режим паузы: пропускаем распознавание целиком (экономия
                        # GPU/CPU) и ничего не отправляем в оверлей, пока пауза.
                        log_event("PAUSED", "", sec)
                        print("[PAUSED] пропуск / skipped " + str(round(sec, 2)) + "s")
                    else:
                        t0 = time.time()
                        txt = transcribe(whisper, audio)
                        dt = time.time() - t0
                        if not txt:
                            log_event("EMPTY", "", sec, dt)
                        else:
                            fixed = fix_slang(txt)
                            deduped = dedupe_loops(fixed)
                            if deduped != fixed:
                                log_event("DEDUP", txt, sec, dt)
                                print("[DEDUP] " + repr(fixed) + " -> " + repr(deduped))
                            if not deduped or is_hallucination(deduped):
                                log_event("FILTERED", txt, sec, dt)
                                print("[FILTERED] " + repr(txt))
                            else:
                                log_event("OK", deduped, sec, dt)
                                print("[OK] " + str(round(sec, 2))
                                      + "s, whisper " + str(round(dt, 2)) + "s")
                                print("   -> " + deduped)
                                broadcast(deduped)
                    buf = []


# ============================================================
#  ENTRY POINT / ТОЧКА ВХОДА
# ============================================================

def main():
    ensure_lists()

    print(f"Stream Subs {APP_VERSION} / Stream Subs версия {APP_VERSION}")
    threading.Thread(target=check_update, daemon=True).start()

    config = uvicorn.Config(app, host=HOST, port=PORT,
                            log_level="warning", ws="auto")
    server = uvicorn.Server(config)

    async def runner():
        loop_ref["loop"] = asyncio.get_running_loop()
        t_audio = threading.Thread(target=audio_loop, daemon=True)
        t_audio.start()
        print("Subtitles / Субтитры:  http://127.0.0.1:8000/")
        print("Settings / Настройки:   http://127.0.0.1:8000/settings")
        await server.serve()

    try:
        asyncio.run(runner())
    except KeyboardInterrupt:
        print("\nBye / Пока")


if __name__ == "__main__":
    main()

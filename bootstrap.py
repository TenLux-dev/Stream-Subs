# ============================================================
#  Stream Subs — Bootstrap / Загрузчик компонентов
# ------------------------------------------------------------
#  Uses embedded Python if available, else system Python.
#  Использует встроенный Python, если есть, иначе системный.
# ============================================================

import sys
import subprocess
import os
import shutil
import json
import time
import urllib.request
import re
from pathlib import Path

# Не падаем на юникоде в cp866/cp1251 консолях / never crash on Unicode
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except Exception:
        pass

# Включаем ANSI цвета в Windows console
# Enable ANSI colors in Windows console
os.system("")

# ------------------------------------------------------------
#  Colors / Цвета
# ------------------------------------------------------------
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

BLACK = "\033[30m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
WHITE = "\033[97m"

BG_BLUE = "\033[44m"
BG_CYAN = "\033[46m"

CHECK = f"{GREEN}✓{RESET}"
CROSS = f"{RED}✗{RESET}"
WARN = f"{YELLOW}⚠️{RESET}"
ARROW = f"{CYAN}→{RESET}"
# ------------------------------------------------------------
#  Progress bar / красивый прогресс-бар
# ------------------------------------------------------------
BAR_FILL = "\033[48;5;205m"   # pink/magenta fill
BAR_EMPTY = "\033[48;5;28m"   # dark green empty
BAR_WIDTH = 26



if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

MODELS_DIR = BASE_DIR / "models"
MODELS_DIR.mkdir(exist_ok=True)

WHISPER_MODEL_SIZE = "medium"
VAD_MODEL_URL = "https://huggingface.co/runanywhere/silero-vad-v5/resolve/main/silero_vad.onnx"
VAD_MODEL_PATH = MODELS_DIR / "silero_vad.onnx"

REQUIRED_PACKAGES = [
    "torch",
    "faster-whisper",
    "silero-vad",
    "sounddevice",
    "fastapi",
    "uvicorn[standard]",
    "websockets",
    "numpy",
    # Desktop wrapper / настольная обёртка (desktop.py)
    "pywebview",
    "pystray",
    "pillow",
]

# Package name -> import name where they differ / где имя пакета != модуля
PACKAGE_IMPORTS = {
    "pywebview": "webview",
    "pillow": "PIL",
}

CUDA_PACKAGES = [
    "nvidia-cublas-cu12",
    "nvidia-cuda-runtime-cu12",
    "nvidia-cudnn-cu12",
    "nvidia-cuda-nvrtc-cu12",
]

# Installation variant / Вариант установки: "gpu" (default) or "cpu"
# Устанавливается флагом --cpu или переменной окружения STREAMSUBS_VARIANT=cpu.
VARIANT = "cpu" if ("--cpu" in sys.argv or os.environ.get("STREAMSUBS_VARIANT", "").lower() == "cpu") else "gpu"
CPU_TORCH_INDEX = "https://download.pytorch.org/whl/cpu"

# Desktop mode / Настольный режим: --desktop opens desktop.py (window + tray)
# instead of the bare main.py server. Added by the installer shortcuts.
DESKTOP_MODE = "--desktop" in sys.argv

START_TIME = time.time()

def elapsed():
    sec = int(time.time() - START_TIME)
    m, s = divmod(sec, 60)
    return f"{m:02d}:{s:02d}"


def print_section(title):
    print()
    line = f"{DIM}────────────────────────────────────────────────────────────{RESET}"
    print(line)
    print(f"  {YELLOW}⏱  [{elapsed()}]{RESET}  {BOLD}{CYAN}{title}{RESET}")
    print(line)


def print_banner():
    print()
    print(f"{CYAN}{BOLD} _______ _______  ______ _______ _______ _______      _______ _     _ ______  _______")
    print(f" |______    |    |_____/ |______ |_____| |  |  |      |______ |     | |_____] |______")
    print(f" ______|    |    |    \\_ |______ |     | |  |  |      ______| |_____| |_____] ______|{RESET}")
    print()
    print(f"                {BOLD}{WHITE}Stream Subs{RESET} — {CYAN}Bootstrap / Загрузчик компонентов{RESET}")
    print(f"                {DIM}Локальные субтитры RU→EN / Local RU→EN live subtitles{RESET}")
    print()


def check_internet():
    try:
        urllib.request.urlopen("https://huggingface.co", timeout=10)
        return True
    except Exception:
        return False


def check_disk_space(required_gb=6):
    try:
        usage = shutil.disk_usage(str(BASE_DIR))
        free_gb = usage.free / (1024 ** 3)
        print(f"  💾 Свободно на диске / Free disk space: {GREEN}{free_gb:.1f} ГБ{RESET}")
        if free_gb < required_gb:
            print(f"  {WARN}  Требуется минимум {required_gb} ГБ. Места мало!")
            print(f"  {WARN}  At least {required_gb} GB required. Low disk space!")
            return False
        return True
    except Exception:
        return True


def get_python_executable():
    embedded = BASE_DIR / "python-embedded" / "python.exe"
    if embedded.exists():
        print(f"  {CHECK} Using embedded Python / Использую встроенный Python:")
        print(f"     {CYAN}{embedded}{RESET}")
        return str(embedded)

    if getattr(sys, "frozen", False):
        candidates = ["python", "python3", "py"]
        for cmd in candidates:
            path = shutil.which(cmd)
            if path and "StreamSubs" not in path:
                print(f"  {CHECK} Using system Python / Использую системный Python:")
                print(f"     {CYAN}{path}{RESET}")
                return path
        print(f"  {CROSS} Python не найден! / Python not found!")
        print("     Установите Python 3.11+ с https://python.org")
        input("Press Enter to exit...")
        sys.exit(1)
    else:
        return sys.executable


PYTHON = get_python_executable()


def to_mb(value, unit):
    unit = (unit or "").upper()
    if unit == "GB":
        return value * 1024.0
    if unit == "KB":
        return value / 1024.0
    return value


def human_mb(value):
    if value is None:
        return "?"
    return f"{value:.1f} MB"


def render_bar(done, total, extra=""):
    """Retro glyph bar: blocks if console supports them, ASCII fallback if not."""
    if not total or total <= 0:
        return
    import shutil
    try:
        term_w = shutil.get_terminal_size((100, 24)).columns
    except Exception:
        term_w = 100
    width = max(12, min(34, term_w - 64))
    frac = max(0.0, min(1.0, done / total))
    cells = frac * width
    full = int(cells)
    rest = cells - full

    FULL, HALF, EMPTY = "\u2588", "\u2592", "\u2591"
    enc = (getattr(sys.stdout, "encoding", None) or "utf-8")
    try:
        FULL.encode(enc)
    except Exception:
        FULL, HALF, EMPTY = "#", "+", "."

    c_full = "\033[38;5;205m"   # pink
    c_half = "\033[38;5;199m"   # dim pink
    c_empty = "\033[38;5;22m"   # dark green

    bar = c_full + (FULL * full)
    if full < width:
        if rest >= 0.5:
            bar += c_half + HALF
            filled = full + 1
        else:
            filled = full
        bar += c_empty + (EMPTY * (width - filled))
    bar += RESET

    pct = int(frac * 100)
    line = f"\r  {bar} {WHITE}{pct:3d}%{RESET}  {DIM}{human_mb(done):>9} / {human_mb(total):>9}{RESET}"
    if extra:
        line += f"  {extra}"
    print(line, end="", flush=True)


def _norm_name(name):
    return (name or "").lower().replace("-", "_").replace(".", "_")


def report_sizes(pkg):
    """Ask pip for the full dependency tree, then HEAD each wheel for size.

    pi p 26+ больше не кладёт size в --report, поэтому берём Content-Length
    у файла на files.pythonhosted.org. Ошибки/таймауты просто пропускаем:
    тогда install_package покажет прогресс по текущему файлу.
    """
    report_path = None
    try:
        import tempfile
        fd, report_path = tempfile.mkstemp(prefix="ssubs_report_", suffix=".json")
        os.close(fd)
        subprocess.run(
            [PYTHON, "-m", "pip", "install", "--dry-run", "--quiet",
             "--report", report_path, pkg],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=180,
        )
        with open(report_path, encoding="utf-8") as f:
            data = json.loads(f.read().strip() or "{}")
        sizes = {}
        for item in data.get("install", []):
            name = item.get("metadata", {}).get("name", "")
            url = (item.get("download_info") or {}).get("url", "")
            if not name or not url:
                continue
            try:
                req = urllib.request.Request(url, method="HEAD")
                with urllib.request.urlopen(req, timeout=15) as resp:
                    length = resp.headers.get("Content-Length")
                if length:
                    sizes[_norm_name(name)] = int(length)
            except Exception:
                continue
        return sizes
    except Exception:
        return {}
    finally:
        try:
            if report_path:
                os.remove(report_path)
        except Exception:
            pass


def install_package(pkg, index=1, total=1, extra_args=None):
    print()
    print(f"  {YELLOW}📦 [{index}/{total}]{RESET} {BOLD}{pkg}{RESET}")

    sizes = report_sizes(pkg)
    total_mb = (sum(sizes.values()) / 1048576.0) if sizes else 0.0

    pip_cmd = [PYTHON, "-m", "pip", "install", "--progress-bar", "on"]
    if extra_args:
        pip_cmd.extend(extra_args)
    pip_cmd.append(pkg)

    proc = subprocess.Popen(
        pip_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=0,
    )

    buf = ""
    completed = 0.0
    cur_name = None
    cur_total = 0.0
    cur_done = 0.0

    def file_size(name):
        key = _norm_name(name.split("-")[0]) if name else ""
        return float(sizes.get(key, 0.0)) / 1048576.0

    def on_seg(seg):
        nonlocal completed, cur_name, cur_total, cur_done
        seg = seg.strip()
        if not seg:
            return
        m = re.search(r"Downloading (\S+) \(([\d.]+) (MB|kB|GB)\)", seg)
        if m:
            if cur_name:
                completed += file_size(cur_name) or cur_total
            cur_name = m.group(1)
            cur_total = to_mb(float(m.group(2)), m.group(3))
            cur_done = 0.0
            if total_mb:
                render_bar(completed, total_mb)
            return
        m = re.search(r"([\d.]+)/([\d.]+) (MB|kB|GB)", seg)
        if m:
            cur_done = to_mb(float(m.group(1)), m.group(3))
            tot = to_mb(float(m.group(2)), m.group(3))
            speed = re.search(r"([\d.]+) (MB|kB)/s", seg)
            eta = re.search(r"eta (\S+)", seg)
            extra = ((speed.group(0) if speed else "") + "  " +
                     ("ETA " + eta.group(1) if eta else "")).strip()
            if total_mb:
                done = completed + min(cur_done, file_size(cur_name) or tot)
                render_bar(done, total_mb, extra)
            else:
                render_bar(cur_done, tot, extra)
            return
        if "Successfully installed" in seg:
            if total_mb:
                render_bar(total_mb, total_mb)
            print(f"\r     {GREEN}{seg[:110]}{RESET}")
            return
        if ("Collecting " in seg or "Installing " in seg or "Using cached" in seg):
            print(f"\r     {DIM}{seg[:110]}{RESET}")

    while True:
        chunk = proc.stdout.read(256)
        if not chunk:
            break
        buf += chunk.decode("utf-8", "replace")
        parts = re.split(r"[\r\n]", buf)
        buf = parts.pop()
        for seg in parts:
            on_seg(seg)
    on_seg(buf)

    proc.wait()
    print()
    if proc.returncode != 0:
        print(f"  {WARN}  pip завершился с кодом {proc.returncode}")


def check_and_install_packages():
    print_section("[1/4] Installing Python packages / Установка Python-пакетов")
    total = len(REQUIRED_PACKAGES)
    for i, pkg in enumerate(REQUIRED_PACKAGES, 1):
        module_name = PACKAGE_IMPORTS.get(pkg, pkg.split("[")[0].replace("-", "_"))
        result = subprocess.run(
            [PYTHON, "-c", f"import {module_name}"],
            capture_output=True,
        )
        if result.returncode != 0:
            if pkg == "torch" and VARIANT == "cpu":
                install_package(pkg, i, total, extra_args=["--index-url", CPU_TORCH_INDEX])
            else:
                install_package(pkg, i, total)
        else:
            print(f"  {CHECK} [{i}/{total}] {DIM}{pkg} — уже установлен{RESET}")


def check_and_install_cuda():
    if VARIANT == "cpu":
        print_section("[2/4] CUDA libraries / CUDA-библиотеки")
        print(f"  {DIM}CPU-вариант: CUDA-библиотеки не нужны — пропускаем.{RESET}")
        print(f"  {DIM}CPU build: CUDA libraries are not required — skipped.{RESET}")
        return

    print_section("[2/4] CUDA libraries / CUDA-библиотеки")

    result = subprocess.run(
        [PYTHON, "-c", "import ctranslate2; print(ctranslate2.get_cuda_device_count())"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return

    try:
        cuda_count = int(result.stdout.strip())
    except ValueError:
        return

    if cuda_count == 0:
        print(f"  {WARN}  NVIDIA GPU не найдена. Whisper будет работать на CPU.")
        print(f"  {WARN}  No CUDA GPU found. Whisper will run on CPU.")
        return

    print(f"  🎮 {GREEN}Обнаружено GPU: {cuda_count}{RESET}")
    print(f"  🎮 {DIM}GPU detected: {cuda_count}{RESET}")

    total = len(CUDA_PACKAGES)
    for i, pkg in enumerate(CUDA_PACKAGES, 1):
        module_name = pkg.replace("-", "_")
        result = subprocess.run(
            [PYTHON, "-c", f"import {module_name}"],
            capture_output=True,
        )
        if result.returncode != 0:
            install_package(pkg, i, total)
        else:
            print(f"  {CHECK} [{i}/{total}] {DIM}{pkg} — уже установлен{RESET}")


def copy_nvidia_dlls_to_ctranslate2():
    print_section("[3/4] Copying NVIDIA DLLs / Копирование DLL")

    result = subprocess.run(
        [PYTHON, "-c",
         "import ctranslate2, os; print(os.path.dirname(ctranslate2.__file__))"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  {WARN}  ctranslate2 import failed: {result.stderr.strip()}")
        return

    ct2_path = Path(result.stdout.strip())
    if not ct2_path.exists():
        print(f"  {WARN}  ctranslate2 path not found: {ct2_path}")
        return

    print(f"  📂 {DIM}Куда копируем / Destination:{RESET}")
    print(f"     {DIM}{ct2_path}{RESET}")

    site_packages = ct2_path.parent
    dll_dirs = [
        site_packages / "nvidia" / "cublas" / "bin",
        site_packages / "nvidia" / "cuda_runtime" / "bin",
        site_packages / "nvidia" / "cudnn" / "bin",
        site_packages / "nvidia" / "cuda_nvrtc" / "bin",
    ]

    copied = 0
    for dll_dir in dll_dirs:
        if dll_dir.exists():
            for dll in dll_dir.glob("*.dll"):
                try:
                    shutil.copy(dll, ct2_path / dll.name)
                    copied += 1
                except Exception as e:
                    print(f"     {DIM}Skip {dll.name}: {e}{RESET}")
    print(f"  {CHECK} {GREEN}Скопировано {copied} DLL / Copied {copied} DLLs{RESET}")


def download_file_with_progress(url, dest):
    headers = {}
    existing = 0
    if dest.exists():
        existing = dest.stat().st_size
        headers["Range"] = f"bytes={existing}-"

    req = urllib.request.Request(url, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=60)
    except Exception as e:
        print(f"  {CROSS} Ошибка загрузки / Download error: {e}")
        return

    total = int(resp.headers.get("Content-Length", 0))
    if existing and resp.status == 206:
        total += existing
        mode = "ab"
    else:
        existing = 0
        mode = "wb"

    done = existing
    with open(dest, mode) as f:
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total:
                pct = int(done * 100 / total)
                mb = done // 1024 // 1024
                total_mb = total // 1024 // 1024
                print(f"\r  {CYAN}{dest.name}{RESET}: {GREEN}{pct}%{RESET} ({mb}/{total_mb} МБ)", end="", flush=True)
    print()


def download_models():
    print_section("[4/4] Downloading models / Скачивание моделей")

    print(f"  📥 {BOLD}Whisper '{WHISPER_MODEL_SIZE}'{RESET} {DIM}(~1.5 ГБ / GB){RESET}")
    print(f"     {DIM}Это самый долгий шаг / This is the longest step{RESET}")
    try:
        subprocess.check_call([
            PYTHON, "-c",
            f"from faster_whisper import download_model; "
            f"download_model('{WHISPER_MODEL_SIZE}')"
        ])
        print(f"  {CHECK} {GREEN}Whisper model ready / Модель Whisper готова{RESET}")
    except subprocess.CalledProcessError:
        print(f"  {CROSS} Не удалось скачать модель Whisper")

    if not VAD_MODEL_PATH.exists():
        print(f"\n  📥 {BOLD}Silero VAD{RESET} {DIM}(~2.2 МБ / MB){RESET}")
        try:
            download_file_with_progress(VAD_MODEL_URL, VAD_MODEL_PATH)
            print(f"  {CHECK} {GREEN}Silero VAD ready / Готова{RESET}")
        except Exception as e:
            print(f"  {CROSS} VAD model error: {e}")
    else:
        print(f"  {CHECK} {DIM}Silero VAD — уже есть / already exists{RESET}")


# ------------------------------------------------------------
#  Main / Главная
# ------------------------------------------------------------

def bar_demo():
    """Show the progress bar without installing anything (dev/demo)."""
    print_banner()
    print(f"  {DIM}Demo / демо: imitated package download{RESET}")
    print()
    total = 120.0
    import math
    for i in range(0, 121):
        done = total * i / 120.0
        speed = 6.6 + 1.2 * math.sin(i / 8.0)
        eta = 0 if i >= 120 else int((total - done) / max(speed, 0.1))
        render_bar(done, total, f"{speed:4.1f} MB/s  ETA 0:{eta:02d}  [{elapsed()}]")
        time.sleep(0.03)
    print(f"\n  {CHECK} Demo finished / демо завершено")


def main():
    print_banner()
    print(f"  {DIM}Python:{RESET} {CYAN}{PYTHON}{RESET}")

    print()
    print(f"  🌐 Проверка интернета / Checking internet...")
    if not check_internet():
        print(f"  {CROSS} {RED}Нет доступа к интернету / No internet access{RESET}")
        print("     Проверьте соединение и запустите снова")
        print("     Check your connection and try again")
        input("\nPress Enter to exit...")
        sys.exit(1)
    print(f"  {CHECK} {GREEN}Есть интернет / Internet OK{RESET}")

    print()
    print(f"  💾 Проверка места / Checking disk space...")
    check_disk_space(required_gb=6)

    print()
    line = f"{YELLOW}{'─' * 60}{RESET}"
    print(line)
    print(f"  {WARN}  {BOLD}Будет скачано около 4 ГБ / About 4 GB will be downloaded{RESET}")
    print(f"  {WARN}  {BOLD}Это займёт 10-30 минут / Takes 10-30 minutes{RESET}")
    print(line)
    print()

    try:
        input(f"  {CYAN}Нажмите Enter, чтобы продолжить / Press Enter to continue...{RESET}")
    except EOFError:
        pass

    try:
        check_and_install_packages()
        check_and_install_cuda()
        copy_nvidia_dlls_to_ctranslate2()
        download_models()
    except KeyboardInterrupt:
        print(f"\n\n  {CROSS} {RED}Установка прервана / Installation cancelled{RESET}")
        input("Press Enter to exit...")
        sys.exit(1)

    print()
    print(f"{GREEN}{BOLD}╔" + "═" * 58 + "╗")
    print(f"║  ✅ ВСЁ ГОТОВО! / ALL COMPONENTS READY!                ║")
    print(f"╚" + "═" * 58 + "╝{RESET}")
    print()
    print(f"  {DIM}Общее время / Total time:{RESET} {GREEN}{elapsed()}{RESET}")
    print()
    if DESKTOP_MODE:
        print(f"  🖥️  {BOLD}Запускаю настольное окно Stream Subs / Starting desktop app...{RESET}")
        print(f"  {DIM}Окно настроек + иконка в трее. Выход — через меню трея.{RESET}")
        print(f"  {DIM}Settings window + tray icon. Quit from the tray menu.{RESET}")
    else:
        print(f"  🚀 {BOLD}Запускаю Stream Subs / Starting Stream Subs...{RESET}")
        print()
        print(f"  {DIM}После запуска откройте в браузере / After launch open in browser:{RESET}")
        print(f"     {CYAN}http://127.0.0.1:8000{RESET}         {DIM}— субтитры / subtitles{RESET}")
        print(f"     {CYAN}http://127.0.0.1:8000/settings{RESET} {DIM}— настройки / settings{RESET}")
        print()
        print(f"  {DIM}Для остановки нажмите Ctrl+C в этом окне.{RESET}")
        print(f"  {DIM}To stop press Ctrl+C in this window.{RESET}")
    print()

    main_py = BASE_DIR / "main.py"
    if hasattr(sys, "_MEIPASS"):
        candidate = Path(sys._MEIPASS) / "main.py"
        if candidate.exists():
            main_py = candidate

    desktop_py = BASE_DIR / "desktop.py"
    if hasattr(sys, "_MEIPASS"):
        candidate = Path(sys._MEIPASS) / "desktop.py"
        if candidate.exists():
            desktop_py = candidate

    env = os.environ.copy()
    env["STREAMSUBS_BASE_DIR"] = str(BASE_DIR)
    env["STREAMSUBS_PYTHON"] = PYTHON
    os.chdir(str(BASE_DIR))

    if DESKTOP_MODE and desktop_py.exists():
        # desktop.py starts main.py itself and owns the server process.
        # desktop.py сам запускает main.py и владеет процессом сервера.
        env["STREAMSUBS_MAIN"] = str(main_py)
        print(f"  {DIM}desktop.py:{RESET} {CYAN}{desktop_py}{RESET}")
        subprocess.run([PYTHON, str(desktop_py)], env=env)
    else:
        if DESKTOP_MODE:
            print(f"  {WARN}  desktop.py не найден / not found — запускаю main.py в браузере")
        subprocess.run([PYTHON, str(main_py)], env=env)


if __name__ == "__main__":
    if "--bar-demo" in sys.argv:
        bar_demo()
        sys.exit(0)
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("\n" + "=" * 60)
        print("  ОШИБКА / ERROR: " + str(e))
        print("=" * 60)
        print("  Нажмите Enter для выхода / Press Enter to exit...")
        input()

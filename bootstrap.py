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
    """Draw a single-line bar: pink fill on green track."""
    if not total or total <= 0:
        return
    frac = max(0.0, min(1.0, done / total))
    filled = int(frac * BAR_WIDTH)
    bar = BAR_FILL + (" " * filled) + RESET + BAR_EMPTY + (" " * (BAR_WIDTH - filled)) + RESET
    pct = int(frac * 100)
    line = f"\r  {bar} {WHITE}{pct:3d}%{RESET}  {DIM}{human_mb(done)} / {human_mb(total)}{RESET}"
    if extra:
        line += f"  {extra}"
    print(line, end="", flush=True)

# ------------------------------------------------------------
#  Paths / Пути
# ------------------------------------------------------------
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
]

CUDA_PACKAGES = [
    "nvidia-cublas-cu12",
    "nvidia-cuda-runtime-cu12",
    "nvidia-cudnn-cu12",
    "nvidia-cuda-nvrtc-cu12",
]

START_TIME = time.time()


# ------------------------------------------------------------
#  Helpers / Вспомогательные функции
# ------------------------------------------------------------

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


# ------------------------------------------------------------
#  pip install with live output / pip с живым выводом
# ------------------------------------------------------------

def install_package(pkg, index=1, total=1):
    print()
    print(f"  {YELLOW}📦 [{index}/{total}]{RESET} {BOLD}{pkg}{RESET}")

    proc = subprocess.Popen(
        [PYTHON, "-m", "pip", "install", "--progress-bar", "on", pkg],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=0,
    )

    buf = ""
    cur_total = None
    cur_done = 0.0

    def on_seg(seg):
        nonlocal cur_total, cur_done
        seg = seg.strip()
        if not seg:
            return
        m = re.search(r"Downloading (\S+) \(([\d.]+) (MB|kB|GB)\)", seg)
        if m:
            cur_total = to_mb(float(m.group(2)), m.group(3))
            cur_done = 0.0
            return
        m = re.search(r"([\d.]+)/([\d.]+) (MB|kB|GB)", seg)
        if m:
            cur_done = to_mb(float(m.group(1)), m.group(3))
            tot = to_mb(float(m.group(2)), m.group(3))
            speed = re.search(r"([\d.]+) (MB|kB)/s", seg)
            eta = re.search(r"eta (\S+)", seg)
            extra = ((speed.group(0) if speed else "") + "  " +
                     ("ETA " + eta.group(1) if eta else "")).strip()
            render_bar(cur_done, tot, extra)
            return
        if ("Collecting " in seg or "Installing " in seg or
                "Successfully installed" in seg or "Using cached" in seg):
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
        module_name = pkg.split("[")[0].replace("-", "_")
        result = subprocess.run(
            [PYTHON, "-c", f"import {module_name}"],
            capture_output=True,
        )
        if result.returncode != 0:
            install_package(pkg, i, total)
        else:
            print(f"  {CHECK} [{i}/{total}] {DIM}{pkg} — уже установлен{RESET}")


def check_and_install_cuda():
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

    env = os.environ.copy()
    env["STREAMSUBS_BASE_DIR"] = str(BASE_DIR)
    os.chdir(str(BASE_DIR))
    subprocess.run([PYTHON, str(main_py)], env=env)


if __name__ == "__main__":
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

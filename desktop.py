#!/usr/bin/env python3
# ============================================================
#  Stream Subs — Desktop wrapper / Настольная обёртка
# ------------------------------------------------------------
#  Starts main.py in the background, opens /settings in a
#  pywebview window (1000×760) and keeps a pystray icon in the
#  Windows tray with pause / autostart / exit actions.
#
#  Запускает main.py в фоне, открывает /settings в окне pywebview
#  (1000×760) и держит иконку pystray в трее Windows с действиями
#  пауза / автозапуск / выход.
#
#  Fallbacks / Запасные варианты:
#    - pywebview недоступен/упал  -> браузер в app-mode (msedge/chrome)
#    - pystray недоступен         -> работаем без трея, выход по Ctrl+C
#  Missing UI dependencies never crash the app / без зависимостей не падаем.
#
#  Dev flags / Флаги для проверки:
#    --smoke-test   запустить, подождать N секунд и корректно выйти
#                   (N = STREAMSUBS_SMOKE_SECONDS, по умолчанию 6)
#    STREAMSUBS_DESKTOP_NO_BROWSER=1 — не открывать браузер (для тестов)
# ============================================================

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8000
BASE_URL = f"http://{HOST}:{PORT}"
SETTINGS_URL = BASE_URL + "/settings"
SUBTITLES_URL = BASE_URL + "/"
WINDOW_TITLE = "Stream Subs — настройки"
WINDOW_WIDTH = 1000
WINDOW_HEIGHT = 760
SERVER_START_TIMEOUT = 60
APP_ICON = "app.ico"


# ------------------------------------------------------------
#  Paths & logging / Пути и лог
# ------------------------------------------------------------

def resolve_base_dir() -> Path:
    """Каталог с config.json/lists/web — как в main.py / same as main.py."""
    env_base = os.environ.get("STREAMSUBS_BASE_DIR")
    if env_base:
        return Path(env_base)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR = resolve_base_dir()
DESKTOP_LOG = BASE_DIR / "desktop.log"
SERVER_LOG = BASE_DIR / "desktop_server.log"
_log_lock = threading.Lock()


def log(message: str) -> None:
    """Write to console + desktop.log / пишем в консоль и desktop.log."""
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}"
    with _log_lock:
        try:
            print(line, flush=True)
        except Exception:
            pass
        try:
            with open(DESKTOP_LOG, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except Exception:
            pass


# ------------------------------------------------------------
#  HTTP helpers / HTTP-хелперы
# ------------------------------------------------------------

def api_json(path: str, method: str = "GET", payload=None, timeout: float = 2.0):
    """Call local Stream Subs API / запрос к локальному API."""
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE_URL + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def server_alive() -> bool:
    """Server responds to /api/pause / сервер отвечает."""
    try:
        api_json("/api/pause", timeout=1.0)
        return True
    except Exception:
        return False


# ------------------------------------------------------------
#  Server subprocess / Подпроцесс сервера
# ------------------------------------------------------------

def find_main_py() -> Path | None:
    """Find main.py in dev or PyInstaller bundle / ищем main.py."""
    candidates = []
    env_main = os.environ.get("STREAMSUBS_MAIN")
    if env_main:
        candidates.append(Path(env_main))
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "main.py")
    candidates.append(Path(__file__).resolve().with_name("main.py"))
    candidates.append(BASE_DIR / "main.py")
    for candidate in candidates:
        try:
            if candidate and candidate.exists():
                return candidate
        except OSError:
            continue
    return None


class ServerProcess:
    """Runs main.py in background; attaches to an already running server."""

    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self.owned = False
        self.log_file = None

    def ensure(self) -> bool:
        if server_alive():
            log("server already running — attaching / подключаюсь к запущенному серверу")
            self.owned = False
            return True

        main_py = find_main_py()
        if not main_py:
            log("ERROR: main.py not found / main.py не найден")
            return False

        env = os.environ.copy()
        env["STREAMSUBS_BASE_DIR"] = str(BASE_DIR)
        env["STREAMSUBS_PYTHON"] = sys.executable
        env.setdefault("PYTHONUNBUFFERED", "1")

        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        try:
            self.log_file = open(SERVER_LOG, "a", encoding="utf-8")
            self.log_file.write(
                f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} desktop launch: "
                f"{sys.executable} {main_py} (cwd={BASE_DIR}) ===\n"
            )
            self.log_file.flush()
            self.proc = subprocess.Popen(
                [sys.executable, str(main_py)],
                cwd=str(BASE_DIR),
                env=env,
                stdout=self.log_file,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )
        except Exception as exc:
            log(f"ERROR: cannot start server / не удалось запустить сервер: {exc}")
            return False

        self.owned = True
        log(f"server started / сервер запущен: pid={self.proc.pid}, main={main_py}")

        deadline = time.time() + SERVER_START_TIMEOUT
        while time.time() < deadline:
            if self.proc.poll() is not None:
                log(f"ERROR: server exited early, code={self.proc.returncode} (see {SERVER_LOG.name})")
                return False
            if server_alive():
                log("server ready / сервер отвечает")
                return True
            time.sleep(0.4)

        log("ERROR: server did not start in time / сервер не поднялся за отведённое время")
        return False

    def stop(self) -> None:
        if not self.owned or not self.proc:
            return
        log(f"stopping server / останавливаю сервер: pid={self.proc.pid}")
        try:
            if self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    log("server did not stop in 5s — kill / не остановился, kill")
                    self.proc.kill()
                    self.proc.wait(timeout=5)
        except Exception as exc:
            log(f"server stop error: {exc}")
        finally:
            self.owned = False
            self.proc = None
            if self.log_file:
                try:
                    self.log_file.close()
                except Exception:
                    pass
                self.log_file = None


# ------------------------------------------------------------
#  Browser fallback / Запасной браузер
# ------------------------------------------------------------

BROWSER_CANDIDATES = [
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    / "Google" / "Chrome" / "Application" / "chrome.exe",
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    / "Google" / "Chrome" / "Application" / "chrome.exe",
]


def open_in_browser_app(url: str, title: str = "") -> bool:
    """Open URL in Edge/Chrome app window; fallback to default browser."""
    if os.environ.get("STREAMSUBS_DESKTOP_NO_BROWSER") == "1":
        log("browser launch skipped by STREAMSUBS_DESKTOP_NO_BROWSER=1")
        return False
    if os.name == "nt":
        for exe in BROWSER_CANDIDATES:
            try:
                if not exe.exists():
                    continue
                subprocess.Popen(
                    [
                        str(exe),
                        f"--app={url}",
                        f"--window-size={WINDOW_WIDTH},{WINDOW_HEIGHT}",
                        "--no-first-run",
                        "--no-default-browser-check",
                    ],
                    close_fds=True,
                )
                log(f"opened app-mode browser: {exe.name} -> {url}")
                return True
            except Exception as exc:
                log(f"browser app-mode failed ({exe}): {exc}")
    try:
        webbrowser.open(url)
        log(f"opened default browser -> {url}")
        return True
    except Exception as exc:
        log(f"cannot open browser / не удалось открыть браузер: {exc}")
        return False


# ------------------------------------------------------------
#  Desktop application / Настольное приложение
# ------------------------------------------------------------

class DesktopApp:
    def __init__(self):
        self.server = ServerProcess()
        self.window = None
        self.webview = None
        self.tray = None
        self.pystray = None
        self.pil_image = None
        self.paused = False
        self.autostart = False
        self.autostart_supported = True
        self.quit_event = threading.Event()
        self.quitting = False
        self.cleanup_done = False
        self.smoke = "--smoke-test" in sys.argv
        self.browser_opened = False
        self.hide_notice_shown = False

    # ---------------- state ----------------

    def load_state(self) -> None:
        try:
            data = api_json("/api/pause")
            self.paused = bool(data.get("paused"))
        except Exception as exc:
            log(f"cannot read pause state: {exc}")
        try:
            data = api_json("/api/autostart")
            self.autostart = bool(data.get("enabled"))
            self.autostart_supported = bool(data.get("supported", True))
        except Exception as exc:
            log(f"cannot read autostart state: {exc}")
        log(f"state: paused={self.paused}, autostart={self.autostart}")

    def refresh_menu(self) -> None:
        if self.tray:
            try:
                self.tray.update_menu()
            except Exception as exc:
                log(f"menu update failed: {exc}")

    def notify(self, message: str, title: str = "Stream Subs") -> None:
        if self.tray:
            try:
                self.tray.notify(message, title)
            except Exception:
                pass

    # ---------------- tray ----------------

    def _load_tray(self) -> bool:
        try:
            import pystray
            from PIL import Image
        except Exception as exc:
            log(f"tray unavailable / трей недоступен: {exc}")
            return False

        self.pystray = pystray
        self.pil_image = Image
        try:
            if (BASE_DIR / APP_ICON).exists():
                image = Image.open(BASE_DIR / APP_ICON)
            else:
                image = self._fallback_icon()
            Menu, MenuItem = pystray.Menu, pystray.MenuItem
            menu = Menu(
                MenuItem("Открыть настройки", self.action_open_settings, default=True),
                MenuItem("Открыть субтитры", self.action_open_subtitles),
                Menu.SEPARATOR,
                MenuItem(self._pause_label, self.action_toggle_pause),
                MenuItem(self._autostart_label, self.action_toggle_autostart),
                Menu.SEPARATOR,
                MenuItem("Выход", self.action_quit),
            )
            self.tray = pystray.Icon("StreamSubs", image, "Stream Subs", menu)
        except Exception as exc:
            log(f"tray init failed / не удалось создать трей: {exc}")
            self.tray = None
            return False

        def run_tray():
            try:
                self.tray.run()
            except Exception as exc:
                log(f"tray stopped with error: {exc}")

        threading.Thread(target=run_tray, name="streamsubs-tray", daemon=True).start()
        log("tray icon started / иконка в трее запущена")
        return True

    def _fallback_icon(self):
        """Draw a simple icon if app.ico is missing / рисуем простую иконку."""
        from PIL import Image, ImageDraw
        image = Image.new("RGBA", (64, 64), (30, 30, 30, 255))
        draw = ImageDraw.Draw(image)
        draw.polygon([(22, 14), (50, 32), (22, 50)], fill=(0, 122, 204, 255))
        return image

    def _pause_label(self, _item) -> str:
        return "Продолжить" if self.paused else "Пауза"

    def _autostart_label(self, _item) -> str:
        return "Автозапуск: вкл" if self.autostart else "Автозапуск: выкл"

    # ---------------- tray actions ----------------

    def action_open_settings(self, _icon=None, _item=None) -> None:
        if self.window:
            try:
                self.window.show()
                log("window shown from tray / окно восстановлено из трея")
            except Exception as exc:
                log(f"window show failed: {exc}")
                self.window = None
            else:
                try:
                    self.window.restore()
                except Exception:
                    pass
                return
        open_in_browser_app(SETTINGS_URL)
        self.browser_opened = True

    def action_open_subtitles(self, _icon=None, _item=None) -> None:
        try:
            webbrowser.open(SUBTITLES_URL)
            log("subtitles opened in browser / субтитры открыты в браузере")
        except Exception as exc:
            log(f"cannot open subtitles: {exc}")

    def action_toggle_pause(self, _icon=None, _item=None) -> None:
        target = not self.paused
        try:
            api_json("/api/pause" if target else "/api/resume", method="POST", payload={})
            self.paused = target
            log("paused / пауза" if target else "resumed / продолжаем")
        except Exception as exc:
            log(f"pause toggle failed: {exc}")
            self.notify(f"Не удалось переключить паузу: {exc}")
        self.refresh_menu()

    def action_toggle_autostart(self, _icon=None, _item=None) -> None:
        target = not self.autostart
        try:
            data = api_json("/api/autostart", method="POST", payload={"enabled": target}, timeout=5.0)
            if data.get("ok"):
                self.autostart = bool(data.get("enabled"))
                self.autostart_supported = True
                log(f"autostart {'enabled' if self.autostart else 'disabled'}")
            else:
                self.notify(f"Автозапуск: {data.get('error', 'ошибка')}")
                log(f"autostart error: {data.get('error')}")
        except Exception as exc:
            log(f"autostart request failed: {exc}")
            self.notify(f"Автозапуск недоступен: {exc}")
        self.refresh_menu()

    def action_quit(self, _icon=None, _item=None) -> None:
        log("quit requested from tray / выход из трея")
        self.request_quit()

    # ---------------- window ----------------

    def _on_window_closing(self):
        """Hide to tray instead of exiting / прячем в трей, не выходим."""
        if self.quitting:
            return True
        if not self.tray:
            # No tray to return to — let the window close and the app exit.
            # Трея нет — закрываем окно и выходим, чтобы не оставить зомби.
            self.quitting = True
            return True
        try:
            if self.window:
                self.window.hide()
                log("window hidden to tray / окно свёрнуто в трей")
        except Exception as exc:
            log(f"window hide failed: {exc}")
        if not self.hide_notice_shown:
            self.hide_notice_shown = True
            self.notify("Свёрнуто в трей. Выход — через меню трея.", "Stream Subs")
        return False

    def _start_webview(self) -> bool:
        """Show pywebview window; returns True when its loop finished."""
        if self.quitting:
            return True
        try:
            import webview
            self.webview = webview
        except Exception as exc:
            log(f"pywebview unavailable / недоступен: {exc} -> browser fallback")
            return False

        try:
            self.window = webview.create_window(
                WINDOW_TITLE,
                SETTINGS_URL,
                width=WINDOW_WIDTH,
                height=WINDOW_HEIGHT,
                min_size=(800, 600),
                resizable=True,
                confirm_close=False,
                text_select=True,
            )
            if hasattr(self.window.events, "closing"):
                self.window.events.closing += self._on_window_closing
            log("pywebview window starting / окно запускается")
            webview.start(
                debug=False,
                private_mode=False,
                icon=str(BASE_DIR / APP_ICON) if (BASE_DIR / APP_ICON).exists() else None,
            )
            log("pywebview loop finished / цикл окна завершён")
            return True
        except Exception as exc:
            log(f"pywebview failed / окно не запустилось: {exc} -> browser fallback")
            self.window = None
            return False

    def _fallback_browser(self) -> None:
        if not self.browser_opened:
            self.browser_opened = True
            open_in_browser_app(SETTINGS_URL)

    # ---------------- lifecycle ----------------

    def request_quit(self) -> None:
        if self.quitting:
            return
        self.quitting = True
        if self.tray:
            try:
                self.tray.stop()
            except Exception as exc:
                log(f"tray stop error: {exc}")
        if self.window:
            try:
                self.window.destroy()
            except Exception as exc:
                log(f"window destroy error: {exc}")
        self.quit_event.set()

    def cleanup(self) -> None:
        if self.cleanup_done:
            return
        self.cleanup_done = True
        self.server.stop()
        if self.tray:
            try:
                self.tray.stop()
            except Exception:
                pass
            self.tray = None
        if self.smoke:
            log("SMOKE OK: desktop wrapper stopped cleanly / обёртка завершилась корректно")
        else:
            log("desktop wrapper stopped / настольная обёртка остановлена")

    def _run_smoke_timer(self) -> None:
        try:
            delay = float(os.environ.get("STREAMSUBS_SMOKE_SECONDS", "6"))
        except ValueError:
            delay = 6.0
        log(f"SMOKE: auto-quit in {delay:.1f}s")
        time.sleep(delay)
        self.request_quit()

    def run(self) -> int:
        log(f"Stream Subs desktop wrapper / настольная обёртка; base={BASE_DIR}")
        if not self.server.ensure():
            self._fatal("Не удалось запустить сервер Stream Subs.\n"
                        "Смотрите desktop_server.log рядом с программой.")
            return 2

        self.load_state()
        tray_ok = self._load_tray()
        if not tray_ok:
            log("running without tray / работаем без трея")
        if self.smoke:
            threading.Thread(target=self._run_smoke_timer, name="smoke", daemon=True).start()

        try:
            if self._start_webview():
                # pywebview loop exited: either quit from tray or smoke timer.
                self.cleanup()
                return 0
            # pywebview unavailable -> app-mode browser + tray keeps app alive.
            log("fallback mode / запасной режим: browser app window")
            self._fallback_browser()
            self.notify("Stream Subs работает в фоне. Иконка — в трее.", "Stream Subs")
            try:
                while not self.quit_event.wait(0.5):
                    pass
            except KeyboardInterrupt:
                log("Ctrl+C — quit / выход")
                self.request_quit()
            self.cleanup()
            return 0
        except KeyboardInterrupt:
            log("Ctrl+C — quit / выход")
            self.request_quit()
            self.cleanup()
            return 0
        except Exception as exc:
            log(f"FATAL desktop error: {exc}")
            self._fatal(f"Ошибка настольного режима:\n{exc}")
            self.cleanup()
            return 1

    def _fatal(self, message: str) -> None:
        log("FATAL: " + message.replace("\n", " | "))
        if self.smoke:
            return
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, "Stream Subs — ошибка", 0x10)
        except Exception:
            pass


def main() -> int:
    try:
        return DesktopApp().run()
    except Exception:
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""Backtester desktop launcher.

Boots uvicorn on a free loopback port in a background thread. A pystray tray
icon and webbrowser-open are added in later tasks. The --no-tray path here is
used by the CI smoke test and by the test suite.
"""
from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Optional

import paths


def _pick_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _configure_logging() -> None:
    logs = paths.logs_dir()
    logs.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        logs / "backtester.log", maxBytes=10 * 1024 * 1024, backupCount=5
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def _start_uvicorn(port: int):
    """Start uvicorn in a background thread; return (thread, server)."""
    import uvicorn
    import api

    config = uvicorn.Config(api.app, host="127.0.0.1", port=port, log_level="info")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, name="uvicorn", daemon=False)
    thread.start()
    return thread, server


def _wait_for_health(port: int, timeout_s: float = 10.0) -> bool:
    import httpx
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=1.0)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def _write_lockfile(data_dir: Path, port: int) -> Path:
    lock = data_dir / "backtester.lock"
    lock.write_text(json.dumps({"pid": os.getpid(), "port": port}))
    return lock


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    except Exception:
        return False
    return True


def _check_existing_instance(data_dir: Path) -> Optional[int]:
    """Return the port of an existing running instance, or None."""
    lock = data_dir / "backtester.lock"
    if not lock.exists():
        return None
    try:
        info = json.loads(lock.read_text())
        if _pid_alive(int(info["pid"])):
            return int(info["port"])
    except Exception:
        pass
    return None


def _open_data_dir(data_dir: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(str(data_dir))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(data_dir)])
    else:
        subprocess.Popen(["xdg-open", str(data_dir)])


def _icon_path() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS) / "assets"
    else:
        base = Path(__file__).resolve().parent / "assets"
    return base / "icon.png"


def _run_tray(port: int, data_dir: Path, server, thread, lock: Path) -> None:
    import pystray
    from PIL import Image

    image = Image.open(_icon_path())

    def _quit(icon, _item):
        server.should_exit = True
        thread.join(timeout=5)
        try:
            lock.unlink()
        except FileNotFoundError:
            pass
        icon.stop()

    def _open(_icon, _item):
        webbrowser.open(f"http://127.0.0.1:{port}/")

    def _copy_url(_icon, _item):
        url = f"http://127.0.0.1:{port}"
        try:
            import pyperclip
            pyperclip.copy(url)
        except Exception:
            logging.getLogger("launcher").info("URL: %s", url)

    def _open_dir(_icon, _item):
        _open_data_dir(data_dir)

    def _about(_icon, _item):
        logging.getLogger("launcher").info("Backtester — data dir: %s", data_dir)

    menu = pystray.Menu(
        pystray.MenuItem("Open Backtester", _open, default=True),
        pystray.MenuItem("Copy URL", _copy_url),
        pystray.MenuItem("Open data folder", _open_dir),
        pystray.MenuItem("About", _about),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", _quit),
    )
    icon = pystray.Icon("backtester", image, "Backtester", menu)
    icon.run()


def _show_fatal_dialog(title: str, message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:
        logging.getLogger("launcher").error("[FATAL] %s — %s", title, message)


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="backtester")
    p.add_argument("--portable", action="store_true", help="store data next to the executable")
    p.add_argument("--port", type=int, default=0, help="loopback port (0 = auto)")
    p.add_argument("--no-browser", action="store_true", help="do not open a browser tab")
    p.add_argument("--no-tray", action="store_true", help="do not register a tray icon (CI/test)")
    p.add_argument("--dev", action="store_true", help="dev mode (verbose logging)")
    return p.parse_args(argv)


def _main_impl(args: argparse.Namespace) -> int:
    data_dir = paths.resolve_user_data_dir(portable_flag=args.portable)
    os.environ["BACKTESTER_DATA_DIR"] = str(data_dir)
    paths.ensure_data_dir()

    existing_port = _check_existing_instance(data_dir)
    if existing_port is not None:
        if not args.no_browser:
            webbrowser.open(f"http://127.0.0.1:{existing_port}/")
        # Logger may not be configured yet — print is fine for this diagnostic.
        print(f"backtester: another instance is running at port {existing_port}; opening browser", file=sys.stderr)
        return 0

    _configure_logging()
    log = logging.getLogger("launcher")
    log.info("data dir: %s", data_dir)

    port = args.port if args.port else _pick_free_port()
    log.info("port: %d", port)

    lock = _write_lockfile(data_dir, port)
    log.info("lockfile: %s", lock)

    thread, server = _start_uvicorn(port)

    if not _wait_for_health(port, timeout_s=10.0):
        log_path = paths.logs_dir() / "backtester.log"
        msg = f"Backtester could not start.\n\nLog file:\n{log_path}"
        log.error("server failed readiness probe")
        _show_fatal_dialog("Backtester — startup failed", msg)
        server.should_exit = True
        thread.join(timeout=5)
        try:
            lock.unlink()
        except FileNotFoundError:
            pass
        return 1

    if not args.no_browser:
        webbrowser.open(f"http://127.0.0.1:{port}/")

    if args.no_tray:
        try:
            while thread.is_alive():
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass
        finally:
            server.should_exit = True
            thread.join(timeout=5)
            try:
                lock.unlink()
            except FileNotFoundError:
                pass
        return 0

    try:
        _run_tray(port, data_dir, server, thread, lock)
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        try:
            lock.unlink()
        except FileNotFoundError:
            pass
    return 0


def main(argv: Optional[list] = None) -> int:
    args = parse_args(argv)
    try:
        return _main_impl(args)
    except Exception as exc:
        logging.getLogger("launcher").exception("unhandled error in launcher")
        _show_fatal_dialog(
            "Backtester — internal error",
            f"{exc}\n\nLog: {paths.logs_dir() / 'backtester.log'}",
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())

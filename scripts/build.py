"""Local + CI build orchestration for the Backtester desktop bundle."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True)


def check_prereqs() -> None:
    py = sys.version_info
    assert py >= (3, 11), f"python 3.11+ required, got {py.major}.{py.minor}"
    if shutil.which("node") is None:
        sys.exit("error: node not found on PATH")
    if shutil.which("npm") is None:
        sys.exit("error: npm not found on PATH")


def build_frontend() -> None:
    npm = "npm.cmd" if sys.platform.startswith("win") else "npm"
    run([npm, "ci"], cwd=ROOT / "frontend")
    run([npm, "run", "build"], cwd=ROOT / "frontend")


def build_pyinstaller() -> None:
    run([sys.executable, "-m", "PyInstaller", "backtester.spec", "--noconfirm"], cwd=ROOT)


def post_windows() -> None:
    nsi = ROOT / "scripts" / "backtester.nsi"
    if shutil.which("makensis") and nsi.exists():
        run(["makensis", str(nsi)], cwd=ROOT)
    else:
        print("skip: makensis or backtester.nsi missing — installer not built")


def post_macos() -> None:
    release = ROOT / "dist" / "release"
    release.mkdir(parents=True, exist_ok=True)
    app_bundle = ROOT / "dist" / "Backtester.app"
    dmg = release / "Backtester-1.0.0.dmg"
    if dmg.exists():
        dmg.unlink()
    if not app_bundle.exists():
        # PyInstaller writes a folder; build an .app wrapper here if missing.
        sys.exit(f"missing {app_bundle} - adjust .spec to produce a .app bundle on macOS")
    run([
        "hdiutil", "create",
        "-volname", "Backtester",
        "-srcfolder", str(app_bundle),
        "-ov", "-format", "UDZO",
        str(dmg),
    ])


def post_linux() -> None:
    # Phase 6 wires AppImage + .deb here.
    print("skip: linux .AppImage / .deb packaging not yet wired (Phase 6 task)")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--skip-frontend", action="store_true")
    p.add_argument("--skip-installer", action="store_true")
    args = p.parse_args()

    check_prereqs()
    if not args.skip_frontend:
        build_frontend()
    build_pyinstaller()
    if not args.skip_installer:
        if sys.platform.startswith("win"):
            post_windows()
        elif sys.platform == "darwin":
            post_macos()
        else:
            post_linux()
    print("\nbuild complete: dist/Backtester/")
    return 0


if __name__ == "__main__":
    sys.exit(main())

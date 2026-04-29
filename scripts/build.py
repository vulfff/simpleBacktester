"""Local + CI build orchestration for the Backtester desktop bundle."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

VERSION="1.0.2" """ Just change new version build here """

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
    release = ROOT / "dist" / "release"
    release.mkdir(parents=True, exist_ok=True)
    zip_path = release / f"backtester-{VERSION}-windows-x64.zip"
    shutil.make_archive(str(zip_path.with_suffix("")), "zip", ROOT / "dist", "Backtester")
    nsi = ROOT / "scripts" / "backtester.nsi"
    if shutil.which("makensis") and nsi.exists():
        run(["makensis", f"/DVERSION={VERSION}", str(nsi)], cwd=ROOT)
    else:
        print("skip: makensis or backtester.nsi missing — installer not built")


def generate_macos_icons() -> None:
    """Generate icon.icns from icon.png via sips + iconutil (macOS built-ins)."""
    png = ROOT / "assets" / "icon.png"
    icns = ROOT / "assets" / "icon.icns"
    if icns.exists():
        return
    iconset = ROOT / "assets" / "icon.iconset"
    iconset.mkdir(exist_ok=True)
    for s in [16, 32, 64, 128, 256, 512, 1024]:
        run(["sips", "-z", str(s), str(s), str(png), "--out", str(iconset / f"icon_{s}x{s}.png")])
    run(["iconutil", "-c", "icns", str(iconset), "-o", str(icns)])
    shutil.rmtree(iconset)


def post_macos() -> None:
    release = ROOT / "dist" / "release"
    release.mkdir(parents=True, exist_ok=True)
    app_bundle = ROOT / "dist" / "Backtester.app"
    dmg = release / f"Backtester-{VERSION}.dmg"
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
    release = ROOT / "dist" / "release"
    release.mkdir(parents=True, exist_ok=True)

    # AppImage
    appdir = ROOT / "dist" / "Backtester.AppDir"
    if appdir.exists():
        shutil.rmtree(appdir)
    shutil.copytree(ROOT / "dist" / "Backtester", appdir / "usr" / "bin")
    shutil.copy(ROOT / "scripts" / "backtester.desktop", appdir / "backtester.desktop")
    shutil.copy(ROOT / "assets" / "icon.png", appdir / "backtester.png")
    apprun = appdir / "AppRun"
    apprun.write_text("#!/bin/sh\nexec \"$(dirname \"$0\")/usr/bin/Backtester\" \"$@\"\n")
    apprun.chmod(0o755)
    if shutil.which("appimagetool"):
        run(["appimagetool", str(appdir), str(release / f"Backtester-{VERSION}-x86_64.AppImage")])
    else:
        print("skip: appimagetool missing - AppImage not built")

    # Debian package
    deb_root = ROOT / "dist" / "deb"
    if deb_root.exists():
        shutil.rmtree(deb_root)
    (deb_root / "DEBIAN").mkdir(parents=True)
    (deb_root / "opt" / "backtester").mkdir(parents=True)
    (deb_root / "usr" / "share" / "applications").mkdir(parents=True)
    shutil.copytree(ROOT / "dist" / "Backtester", deb_root / "opt" / "backtester", dirs_exist_ok=True)
    shutil.copy(ROOT / "scripts" / "backtester.desktop", deb_root / "usr" / "share" / "applications" / "backtester.desktop")
    (deb_root / "DEBIAN" / "control").write_text(
        "Package: backtester\n"
        "Version: " + VERSION + "\n"
        "Section: misc\n"
        "Priority: optional\n"
        "Architecture: amd64\n"
        "Maintainer: vulfff <noreply@github.com>\n"
        "Description: Algorithmic trading backtester (desktop)\n"
    )
    if shutil.which("dpkg-deb"):
        run(["dpkg-deb", "--build", str(deb_root), str(release / "backtester_" + VERSION + "_amd64.deb")])
    else:
        print("skip: dpkg-deb missing - .deb not built")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--skip-frontend", action="store_true")
    p.add_argument("--skip-installer", action="store_true")
    args = p.parse_args()

    check_prereqs()
    if not args.skip_frontend:
        build_frontend()
    if sys.platform == "darwin":
        generate_macos_icons()
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

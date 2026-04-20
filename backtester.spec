# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

block_cipher = None
ROOT = Path(SPECPATH).resolve()


HIDDEN = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "pystray._win32",
    "pystray._darwin",
    "pystray._appindicator",
    "pystray._gtk",
    "PIL.Image",
]


def _icon_for_platform():
    if sys.platform.startswith("win"):
        return str(ROOT / "assets" / "icon.ico")
    if sys.platform == "darwin":
        return str(ROOT / "assets" / "icon.icns")
    return str(ROOT / "assets" / "icon.png")


a = Analysis(
    [str(ROOT / "backtester_launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "frontend" / "dist"), "frontend_dist"),
        (str(ROOT / "assets"), "assets"),
    ],
    hiddenimports=HIDDEN,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Backtester",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,           # --windowed
    icon=_icon_for_platform(),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Backtester",
)

import sys as _sys
if _sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Backtester.app",
        icon=str(ROOT / "assets" / "icon.icns"),
        bundle_identifier="org.backtester.Backtester",
        info_plist={"LSUIElement": True},  # tray-only, no Dock icon
    )

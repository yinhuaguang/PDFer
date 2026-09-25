# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 单文件 Release 配置：产物为 dist/PDFer.exe。"""

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs

DEBUG_CONSOLE = os.environ.get("PDFER_DEBUG_CONSOLE") == "1"
APP_NAME = "PDFer-debug" if DEBUG_CONSOLE else "PDFer"

ROOT = Path(SPECPATH).resolve()
if not (ROOT / "src" / "pdfer").is_dir():
    ROOT = ROOT.parent
SRC = ROOT / "src"
ICON = ROOT / "assets" / "pdfer.ico"

print(f"[spec] project root: {ROOT}")
print(f"[spec] source dir  : {SRC}")
print(f"[spec] icon        : {ICON} (exists={ICON.exists()})")


def _collect_pdfium() -> list:
    collected = []
    for package in ("pypdfium2_raw", "pypdfium2"):
        try:
            collected += collect_dynamic_libs(package)
        except Exception:
            print(f"[spec] warning: failed to collect dynamic libraries from {package}", file=sys.stderr)
    return collected


EXCLUDES = [
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQuickControls2",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtGraphs",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtPositioning",
    "PySide6.QtLocation",
    "PySide6.QtSerialPort",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtUiTools",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtSensors",
    "PySide6.QtSpatialAudio",
    "PySide6.QtStateMachine",
    "PySide6.QtTextToSpeech",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtNetworkAuth",
    # reportlab 仅用于测试生成样例，不属于正式程序依赖。
    "reportlab",
    "PIL.AvifImagePlugin",
    "numpy",
    "tkinter",
    "unittest",
    "pydoc",
    "doctest",
    "lib2to3",
    "test",
]

a = Analysis(
    [str(SRC / "pdfer" / "__main__.py")],
    pathex=[str(SRC)],
    binaries=_collect_pdfium(),
    datas=[
        (str(ROOT / "LICENSE"), "."),
        (str(ROOT / "THIRD_PARTY_LICENSES.md"), "."),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=1,
)

DEAD_WEIGHT = {
    "opengl32sw.dll",
    "Qt6Quick.dll",
    "Qt6Qml.dll",
    "Qt6QmlModels.dll",
    "Qt6QmlMeta.dll",
    "Qt6QmlWorkerScript.dll",
    "Qt6VirtualKeyboard.dll",
    "Qt6Pdf.dll",
    "Qt6Network.dll",
    "QtQuick.pyd",
    "QtQml.pyd",
    "QtPdf.pyd",
    "QtNetwork.pyd",
    "QtVirtualKeyboard.pyd",
    "qdirect2d.dll",
}
DEAD_DIRS = {"/translations/", "/plugins/tls/"}
DEAD_PREFIXES = ("_avif.",)  # Pillow 的 AVIF 原生解码器约 7.5MB，本项目不支持 AVIF 输入


def _strip_dead_weight(entries: list) -> tuple[list, list[str]]:
    kept, dropped = [], []
    for entry in entries:
        path = entry[0].replace("\\", "/")
        name = path.rsplit("/", 1)[-1]
        if (
            name in DEAD_WEIGHT
            or any(name.startswith(prefix) for prefix in DEAD_PREFIXES)
            or any(part in path for part in DEAD_DIRS)
        ):
            dropped.append(name)
        else:
            kept.append(entry)
    return kept, dropped


a.binaries, _dropped = _strip_dead_weight(a.binaries)
a.datas, _dropped_data = _strip_dead_weight(a.datas)
print(f"[spec] removed {len(_dropped) + len(_dropped_data)} unused Qt entries")

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=DEBUG_CONSOLE,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON) if ICON.exists() else None,
)

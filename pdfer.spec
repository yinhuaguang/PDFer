# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：目录模式（onedir），产物为 dist/PDFer/PDFer.exe。

为什么用 onedir 而不是 onefile：
1. PySide6 是 LGPL-3.0，要求用户能够替换 Qt 库本身。目录模式下 Qt 的 DLL 是独立文件，
   用户可以自行替换；单文件模式把它们压进 exe，属于合规上的灰色地带。
2. 单文件模式每次启动都要先把几十 MB 解压到临时目录，冷启动明显变慢。

用法：``python -m PyInstaller --noconfirm --clean pdfer.spec``
"""

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs

# 排查打包后启动崩溃时用：设 PDFER_DEBUG_CONSOLE=1 会额外产出一个带控制台的
# PDFer-debug，启动时的 Python 栈回溯会直接打到终端上（正常打包不受影响）。
#   PowerShell: $env:PDFER_DEBUG_CONSOLE=1; .\build.ps1
DEBUG_CONSOLE = os.environ.get("PDFER_DEBUG_CONSOLE") == "1"
APP_NAME = "PDFer-debug" if DEBUG_CONSOLE else "PDFer"

ROOT = Path(SPECPATH).resolve()
# SPECPATH 在不同 PyInstaller 版本里可能是「spec 所在目录」，也可能是 spec 文件本身，
# 这里按项目结构自适应判断，避免多退/少退一层目录导致找不到源码。
if not (ROOT / "src" / "pdfer").is_dir():
    ROOT = ROOT.parent
SRC = ROOT / "src"
ICON = ROOT / "assets" / "pdfer.ico"

print(f"[spec] project root: {ROOT}")
print(f"[spec] source dir  : {SRC}")
print(f"[spec] icon        : {ICON} (exists={ICON.exists()})")


def _collect_pdfium() -> list:
    """pypdfium2 的 pdfium 是随包分发的原生 DLL，必须显式收集。"""
    collected = []
    for package in ("pypdfium2_raw", "pypdfium2"):
        try:
            collected += collect_dynamic_libs(package)
        except Exception:  # noqa: BLE001 - 包结构变化时不应直接让打包失败
            print(f"[spec] warning: failed to collect dynamic libraries from {package}", file=sys.stderr)
    return collected


# Qt 里本项目完全用不到的模块。其中 QtWebEngineCore 单个就有近 200MB，
# 一旦被 PyInstaller 的钩子顺手收进去，产物体积会从 ~80MB 直接涨到 250MB+。
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
    # 标准库里用不到的大件
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
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)

# PyInstaller 的 PySide6 钩子会把 PySide6 目录下的 Qt 动态库整体收进来，
# 光靠上面的 excludes 只能挡住 Python 侧模块，挡不住这些 DLL。这里二次剔除。
# 以下每一项都核过：纯 Widgets 应用用不到，实测不影响启动。
DEAD_WEIGHT = {
    "opengl32sw.dll",               # 19.7MB 软件 OpenGL 回退；Widgets 走光栅绘制，用不到
    "Qt6Quick.dll",                 # 12.6MB QML/Quick 整套（下面四个同属一套）
    "Qt6Qml.dll",
    "Qt6QmlModels.dll",
    "Qt6QmlMeta.dll",
    "Qt6QmlWorkerScript.dll",
    "Qt6VirtualKeyboard.dll",
    "Qt6Pdf.dll",                   # 4.4MB 渲染走 pypdfium2，不用 QtPdf
    "Qt6Network.dll",               # 程序不发任何网络请求
    "QtQuick.pyd",
    "QtQml.pyd",
    "QtPdf.pyd",
    "QtNetwork.pyd",
    "QtVirtualKeyboard.pyd",
    "qdirect2d.dll",                # 备用平台插件，默认用的是 qwindows
}
# 程序没有安装 QTranslator，Qt 自带的多语言文件纯属死重量（6.7MB）
DEAD_DIRS = {"/translations/", "/plugins/tls/"}
DEAD_PREFIXES = ("_avif.",)  # Pillow 的 AVIF 原生解码器约 7.5MB，本项目不支持 AVIF 输入


def _strip_dead_weight(entries: list) -> tuple[list, list[str]]:
    """从 TOC 里剔除用不到的 Qt 组件，返回 (保留项, 被剔除的名字)。"""
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
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=DEBUG_CONSOLE,  # 正式产物不弹黑框（异常走对话框 + 崩溃日志）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON) if ICON.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)

# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。

用法（在仓库根目录执行）::

    pyinstaller --noconfirm --clean packaging/File-Renaming-Assistant.spec

产物为单文件 ``dist/File-Renaming-Assistant.exe``（Windows）/ 可执行文件（macOS、Linux）。
更方便的方式是直接运行 ``python scripts/build_exe.py``。
"""

import os

ROOT = os.path.dirname(os.path.abspath(SPECPATH))
RESOURCES = os.path.join(ROOT, "src", "renamer", "resources")

# 本程序只用到 QtWidgets / QtGui / QtCore，其余 Qt 模块一律排除以压缩体积
EXCLUDES = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DAnimation",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtQuick", "PySide6.QtQuick3D",
    "PySide6.QtQml", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtPdf",
    "PySide6.QtNetworkAuth", "PySide6.QtBluetooth", "PySide6.QtNfc",
    "PySide6.QtPositioning", "PySide6.QtSerialPort", "PySide6.QtSensors",
    "PySide6.QtRemoteObjects", "PySide6.QtWebSockets", "PySide6.QtWebChannel",
    "tkinter",
]

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[os.path.join(ROOT, "src")],
    binaries=[],
    datas=[(RESOURCES, "renamer/resources")],
    hiddenimports=[
        "renamer",
        "renamer.app",
        "renamer.core",
        "renamer.icons",
        "renamer.theme",
        "renamer.update",
        "renamer.paths",
        "renamer.ui.main_window",
        "renamer.ui.tab_selector",
        # 图标是 SVG，运行时用 QSvgRenderer 着色渲染；PyInstaller 的
        # 静态分析不一定能跟到 PySide6.QtSvg，这里显式声明。
        "PySide6.QtSvg",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="File-Renaming-Assistant",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(RESOURCES, "icon.ico"),
)

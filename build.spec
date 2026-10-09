# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：把工具打成单个 exe（文件名带版本号）。

只保留界面需要的 QtCore / QtGui / QtWidgets，其余 Qt 模块全部排除，
这样 exe 体积能压到最小。
"""
import importlib.util
import os

PROJECT_DIR = os.path.abspath(SPECPATH)

# 直接读 core/version.py，避免把整个 core 包（含 openpyxl）拉进来
_vspec = importlib.util.spec_from_file_location(
    "_wage_version", os.path.join(PROJECT_DIR, "core", "version.py"))
_ver = importlib.util.module_from_spec(_vspec)
_vspec.loader.exec_module(_ver)
VERSION = _ver.__version__
EXE_NAME = _ver.exe_filename(VERSION)     # 员工工资申报转换工具_v1.1.0.exe

EXCLUDES = [
    # —— 用不到的 Qt 模块（体积大头）——
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQuickControls2",
    "PySide6.Qt3DCore",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    "PySide6.QtHttpServer",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtPositioning",
    "PySide6.QtLocation",
    "PySide6.QtTextToSpeech",
    "PySide6.QtSpatialAudio",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtStateMachine",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtSvgWidgets",
    "PySide6.QtUiTools",
    "PySide6.QtXml",
    "PySide6.QtDBus",
    "PySide6.QtNetwork",
    "PySide6.QtConcurrent",
    # —— 其它用不到的三方库 ——
    "tkinter",
    "matplotlib",
    "numpy",
    "pandas",
    "PIL",
    "scipy",
    "PyQt5",
    "PyQt6",
    "IPython",
    "pytest",
    "setuptools",
    "distutils",
]

a = Analysis(
    [os.path.join(PROJECT_DIR, "main.py")],
    pathex=[PROJECT_DIR],
    binaries=[],
    datas=[(os.path.join(PROJECT_DIR, "app.ico"), ".")],
    hiddenimports=["openpyxl", "openpyxl.styles", "core", "core.excel_reader",
                   "core.rules", "core.converter", "core.exporter",
                   "core.settings", "core.updater", "core.version",
                   "ui", "ui.main_window", "ui.rule_dialog", "ui.update_dialog",
                   "urllib.request", "http.client", "ssl", "json", "hashlib"],
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=EXE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(PROJECT_DIR, "app.ico"),
)

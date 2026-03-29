# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules, collect_data_files
import sys as _sys

# ── 确保 SPECPATH（autoflow 目录）在 sys.path 中，collect_submodules 才能找到 src ──
if SPECPATH not in _sys.path:
    _sys.path.insert(0, SPECPATH)

# ── 版本号：动态读取 src/version.py，不需要手动维护 ──
import os as _os, types as _types
_vmod = _types.ModuleType("_ver")
with open(_os.path.join(SPECPATH, "src", "version.py"), encoding="utf-8") as _f:
    exec(_f.read(), _vmod.__dict__)
APP_VERSION = _vmod.VERSION
EXE_NAME    = f"AutoFlow_v{APP_VERSION}"

# ── 手动枚举 src 下所有模块，确保 settings_page 等不被遗漏 ──
hiddenimports = [
    # src.ui
    'src', 'src.ui', 'src.ui.main_window', 'src.ui.block_editor',
    'src.ui.task_editor', 'src.ui.settings_page', 'src.ui.log_panel',
    'src.ui.effects', 'src.ui.themes', 'src.ui.styles',
    'src.ui.trigger_editor', 'src.ui.constraint_editor',
    'src.ui.plugin_page', 'src.ui.onboarding',
    # src.engine
    'src.engine', 'src.engine.models', 'src.engine.runner',
    'src.engine.trigger_monitor',
    # src 顶层
    'src.version', 'src.i18n',
    'src.plugin_api', 'src.plugin_manager',
    # src.blocks / src.triggers / src.utils
    'src.blocks', 'src.triggers', 'src.utils',
    # win32
    'win32gui', 'win32con', 'win32clipboard', 'win32api',
    # 其他
    'psutil', 'plyer', 'imaplib', 'watchdog',
    'watchdog.observers', 'watchdog.events',
    # pycaw 用于应用级音量控制
    'pycaw', 'pycaw.pycaw', 'comtypes', 'comtypes.client',
    'comtypes.server', 'comtypes.automation',
    # pynput 用于键鼠宏录制
    'pynput', 'pynput.mouse', 'pynput.keyboard',
    'pynput.mouse._win32', 'pynput.keyboard._win32',
    # pyautogui + opencv 用于屏幕识别功能块
    'pyautogui', 'PIL', 'PIL.Image', 'PIL.ImageGrab',
    'cv2',
    # pywinauto 用于窗口控件操作功能块
    'pywinauto', 'pywinauto.application', 'pywinauto.findwindows',
    'pywinauto.controls', 'pywinauto.base_wrapper',
    # browser-use 为可选依赖（体积过大不打包进 exe）
    # 用户可在「设置→AI→浏览器自动化」区块一键安装：pip install browser-use
    # 然后运行：playwright install chromium
]
# collect_submodules 依赖 sys.path 已包含 SPECPATH
try:
    hiddenimports += collect_submodules('src')
except Exception:
    pass
hiddenimports += collect_submodules('pycaw')
hiddenimports += collect_submodules('comtypes')
hiddenimports += collect_submodules('pynput')
hiddenimports += collect_submodules('pywinauto')



a = Analysis(
    ['main.py'],
    pathex=[SPECPATH],
    binaries=[],
    datas=[
        ('assets', 'assets'),
        # 内置示例插件随 exe 一起打包
        ('plugins', 'plugins'),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name=EXE_NAME,
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
    icon=['assets\\autoflow.ico'],
)

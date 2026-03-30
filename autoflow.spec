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
APP_VERSION  = _vmod.VERSION
# ✅ exe 名固定为 AutoFlow，不带版本号，方便 PATH 注册 / 快捷方式固定路径
EXE_NAME     = "AutoFlow"
# onedir 模式：输出文件夹名（带版本号，方便区分，但 exe 本身固定）
DIR_NAME     = f"AutoFlow_v{APP_VERSION}"

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



# ── 要从 binaries 里移除的 Qt6 DLL（AutoFlow 不使用这些模块）──
# 只用 QtCore / QtGui / QtWidgets，其余的 Qt 模块 DLL 全部排除
_QT_DLL_EXCLUDES = {
    'Qt6Bluetooth.dll',
    'Qt6Concurrent.dll',
    'Qt6DBus.dll',
    'Qt6Designer.dll',
    'Qt6Help.dll',
    'Qt6LabsAnimation.dll',
    'Qt6LabsFolderListModel.dll',
    'Qt6LabsPlatform.dll',
    'Qt6LabsQmlModels.dll',
    'Qt6LabsSettings.dll',
    'Qt6LabsSharedImage.dll',
    'Qt6LabsWavefrontMesh.dll',
    'Qt6Multimedia.dll',
    'Qt6MultimediaQuick.dll',
    'Qt6MultimediaWidgets.dll',
    'Qt6Network.dll',
    'Qt6Nfc.dll',
    'Qt6OpenGL.dll',
    'Qt6OpenGLWidgets.dll',
    'Qt6Pdf.dll',
    'Qt6PdfQuick.dll',
    'Qt6PdfWidgets.dll',
    'Qt6Positioning.dll',
    'Qt6PositioningQuick.dll',
    'Qt6PrintSupport.dll',
    'Qt6Qml.dll',
    'Qt6QmlMeta.dll',
    'Qt6QmlModels.dll',
    'Qt6QmlWorkerScript.dll',
    'Qt6Quick.dll',
    'Qt6Quick3D.dll',
    'Qt6Quick3DAssetImport.dll',
    'Qt6Quick3DAssetUtils.dll',
    'Qt6Quick3DEffects.dll',
    'Qt6Quick3DGlslParser.dll',
    'Qt6Quick3DHelpers.dll',
    'Qt6Quick3DHelpersImpl.dll',
    'Qt6Quick3DIblBaker.dll',
    'Qt6Quick3DParticles.dll',
    'Qt6Quick3DPhysics.dll',
    'Qt6Quick3DPhysicsHelpers.dll',
    'Qt6Quick3DRuntimeRender.dll',
    'Qt6Quick3DSpatialAudio.dll',
    'Qt6Quick3DUtils.dll',
    'Qt6Quick3DXr.dll',
    'Qt6QuickControls2.dll',
    'Qt6QuickControls2Basic.dll',
    'Qt6QuickControls2BasicStyleImpl.dll',
    'Qt6QuickControls2Fusion.dll',
    'Qt6QuickControls2FusionStyleImpl.dll',
    'Qt6QuickControls2Imagine.dll',
    'Qt6QuickControls2ImagineStyleImpl.dll',
    'Qt6QuickControls2Impl.dll',
    'Qt6QuickControls2Material.dll',
    'Qt6QuickControls2MaterialStyleImpl.dll',
    'Qt6QuickControls2Universal.dll',
    'Qt6QuickControls2UniversalStyleImpl.dll',
    'Qt6QuickDialogs2.dll',
    'Qt6QuickDialogs2QuickImpl.dll',
    'Qt6QuickDialogs2Utils.dll',
    'Qt6QuickEffects.dll',
    'Qt6QuickLayouts.dll',
    'Qt6QuickParticles.dll',
    'Qt6QuickShapes.dll',
    'Qt6QuickTemplates2.dll',
    'Qt6QuickTest.dll',
    'Qt6QuickTimeline.dll',
    'Qt6QuickTimelineBlendTrees.dll',
    'Qt6QuickVectorImage.dll',
    'Qt6QuickVectorImageGenerator.dll',
    'Qt6QuickWidgets.dll',
    'Qt6RemoteObjects.dll',
    'Qt6RemoteObjectsQml.dll',
    'Qt6Sensors.dll',
    'Qt6SensorsQuick.dll',
    'Qt6SerialPort.dll',
    'Qt6ShaderTools.dll',
    'Qt6SpatialAudio.dll',
    'Qt6Sql.dll',
    'Qt6StateMachine.dll',
    'Qt6StateMachineQml.dll',
    'Qt6Svg.dll',
    'Qt6SvgWidgets.dll',
    'Qt6Test.dll',
    'Qt6TextToSpeech.dll',
    'Qt6WebChannel.dll',
    'Qt6WebChannelQuick.dll',
    'Qt6WebSockets.dll',
    'Qt6Xml.dll',
}


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
    excludes=[
        # ── Qt 模块：只用 QtCore/QtGui/QtWidgets，其余全排除 ──
        'PyQt6.QtBluetooth',
        'PyQt6.QtDBus',
        'PyQt6.QtDesigner',
        'PyQt6.QtHelp',
        'PyQt6.QtMultimedia',
        'PyQt6.QtMultimediaWidgets',
        'PyQt6.QtNetwork',
        'PyQt6.QtNfc',
        'PyQt6.QtOpenGL',
        'PyQt6.QtOpenGLWidgets',
        'PyQt6.QtPdf',
        'PyQt6.QtPdfWidgets',
        'PyQt6.QtPositioning',
        'PyQt6.QtPrintSupport',
        'PyQt6.QtQml',
        'PyQt6.QtQuick',
        'PyQt6.QtQuick3D',
        'PyQt6.QtQuickControls2',
        'PyQt6.QtQuickWidgets',
        'PyQt6.QtRemoteObjects',
        'PyQt6.QtSensors',
        'PyQt6.QtSerialPort',
        'PyQt6.QtShaderTools',
        'PyQt6.QtSpatialAudio',
        'PyQt6.QtSql',
        'PyQt6.QtStateMachine',
        'PyQt6.QtSvg',
        'PyQt6.QtSvgWidgets',
        'PyQt6.QtTest',
        'PyQt6.QtTextToSpeech',
        'PyQt6.QtWebChannel',
        'PyQt6.QtWebSockets',
        'PyQt6.QtXml',
        'PyQt6.QtConcurrent',
        # ── 标准库中不需要的大模块 ──
        'tkinter',
        'unittest',
        'test',
        'xmlrpc',
        'ftplib',
        # ── 其他用不到的三方库 ──
        'matplotlib',
        'pandas',
        'scipy',
        'skimage',
        'IPython',
        'jupyter',
        'notebook',
        'docutils',
        'sphinx',
        # 注意：distutils/_distutils_hack/setuptools/pkg_resources 不能 exclude，
        # PyInstaller 内部 hook 依赖 distutils 做 alias，强制排除会导致构建失败
    ],
    noarchive=False,
    optimize=2,
)
# ── 从 binaries 里过滤掉不需要的 Qt6 DLL ──
import os as _os2
_removed = []
_kept = []
for _b in a.binaries:
    _basename = _os2.path.basename(_b[0]).lower()
    # _b = (dest_name, source_path, typecode)
    if _os2.path.basename(_b[0]) in _QT_DLL_EXCLUDES:
        _removed.append(_b[0])
    else:
        _kept.append(_b)
a.binaries = TOC(_kept)
if _removed:
    print(f"[spec] 已排除 {len(_removed)} 个无用 Qt6 DLL，例如: {_removed[:3]}")

pyz = PYZ(a.pure)

# ── onedir 模式：EXE 只含启动器，binaries/datas 由 COLLECT 单独处理 ──
exe = EXE(
    pyz,
    a.scripts,
    [],          # onedir 不在 EXE 里嵌入 binaries/datas
    name=EXE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,   # onedir 启动器本身不需要 UPX，DLL 们已 zlib 解压到文件夹
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\autoflow.ico'],
)

# ── COLLECT：把所有 DLL、数据、PYZ 汇集到 dist/<DIR_NAME>/ 文件夹 ──
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=DIR_NAME,
)

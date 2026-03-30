"""
AutoFlow 主入口
"""
import sys
import os
import logging
import json
import threading

# 确保能找到 src 包
sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import Qt
from src.ui.main_window import MainWindow
from src.ui.onboarding import (
    should_show_disclaimer, should_show_tutorial,
    DisclaimerDialog, TutorialDialog
)


# ──────────────────────────────────────────────────────────────
# 管理员权限检测与 UAC 提权
# ──────────────────────────────────────────────────────────────

def _is_admin() -> bool:
    """检测当前进程是否以管理员身份运行"""
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _relaunch_as_admin() -> bool:
    """
    尝试通过 UAC 以管理员身份重新启动本程序。
    成功触发 UAC 请求后返回 True（当前进程应立即退出）。
    返回 False 表示用户取消 / 提权失败。
    """
    import ctypes

    # 判断当前运行环境：打包 exe 还是 Python 脚本
    if getattr(sys, "frozen", False):
        # PyInstaller 打包后：sys.argv[0] 是 .exe 真实路径
        exe = sys.argv[0]
        params = " ".join(f'"{a}"' for a in sys.argv[1:]) if len(sys.argv) > 1 else None
    else:
        # 开发环境：用 python.exe 重跑 main.py
        exe = sys.executable
        script = os.path.abspath(__file__)
        extra = " ".join(f'"{a}"' for a in sys.argv[1:]) if len(sys.argv) > 1 else ""
        params = f'"{script}" {extra}'.strip()

    SW_SHOWNORMAL = 1
    ret = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", exe, params, None, SW_SHOWNORMAL
    )
    # ShellExecuteW 返回值 > 32 表示成功触发
    return int(ret) > 32


# ──────────────────────────────────────────────────────────────
# 无头任务执行模式（--run-task <task_id>）
# ──────────────────────────────────────────────────────────────

def _run_task_headless(task_id: str, project_path: str | None = None) -> int:
    """
    无头模式：加载项目 → 找到指定 task_id 的任务 → 运行 → 等待完成 → 返回退出码。

    不显示任何 Qt 窗口，专供命令行 / 桌面快捷方式调用。
    返回：0=成功，1=任务未找到，2=项目加载失败，3=执行中出错
    """
    # 确定项目路径
    if not project_path:
        _local = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        default_path = os.path.join(
            _local, "XinyuCraft", "AutoFlow", "Project", "autoflow_default.afp"
        )
        _old_default = os.path.join(os.path.expanduser("~"), "autoflow_default.afp")
        if os.path.exists(default_path):
            project_path = default_path
        elif os.path.exists(_old_default):
            project_path = _old_default

    if not project_path:
        # 没有项目文件，创建一个空的默认项目
        import tempfile
        from src.engine.models import Project
        from src.engine.models import AppConfig
        
        # 创建临时项目文件
        temp_dir = tempfile.gettempdir()
        project_path = os.path.join(temp_dir, f"autoflow_temp_{task_id}.afp")
        
        try:
            # 创建空项目
            config = AppConfig()
            project = Project(
                id="default",
                name="临时项目",
                config=config,
                tasks=[],
                global_variables={}
            )
            project.save(project_path)
            print(f"[AutoFlow] 警告：默认项目文件不存在，已创建临时项目: {project_path}")
        except Exception as e:
            print(f"[AutoFlow] 错误：无法创建临时项目: {e}", file=sys.stderr)
            print(f"[AutoFlow] 请先运行 AutoFlow 并保存至少一个任务")
            return 2
    elif not os.path.isfile(project_path):
        print(f"[AutoFlow] 错误：项目文件不存在: {project_path}", file=sys.stderr)
        return 2

    # 加载项目
    try:
        from src.engine.models import Project, AppConfig
        project = Project.load(project_path)
    except Exception as e:
        print(f"[AutoFlow] 错误：项目加载失败: {e}", file=sys.stderr)
        return 2

    # 查找任务
    task = next((t for t in project.tasks if t.id == task_id), None)
    if not task:
        print(f"[AutoFlow] 错误：未找到任务 ID: {task_id}", file=sys.stderr)
        print(f"[AutoFlow] 项目中的任务：", file=sys.stderr)
        for t in project.tasks:
            print(f"  {t.id}  {t.name}", file=sys.stderr)
        return 1

    print(f"[AutoFlow] 正在运行任务: {task.name} ({task.id})")

    # 加载应用配置（读取 AI / 热键等配置）
    try:
        _local = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        cfg_path = os.path.join(_local, "XinyuCraft", "AutoFlow", "app_config.json")
        config = project.config
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg_data = json.load(f)
            for k, v in cfg_data.items():
                if hasattr(config, k):
                    try:
                        setattr(config, k, v)
                    except Exception:
                        pass
    except Exception:
        config = project.config

    # 执行任务（同步等待）
    from src.engine.runner import TaskRunner

    done_event = threading.Event()
    exit_code   = [0]
    log_lines   = []

    def on_log(level: str, msg: str):
        print(f"[AutoFlow] [{level.upper()}] {msg}")
        log_lines.append(msg)

    def on_finished(tid: str, success: bool):
        if not success:
            print(f"[AutoFlow] 任务执行失败", file=sys.stderr)
            exit_code[0] = 3
        else:
            print(f"[AutoFlow] 任务完成: {task.name}")
        done_event.set()

    runner = TaskRunner(
        task=task,
        config=config,
        global_variables=dict(project.global_variables),
        on_log=on_log,
        on_finished=on_finished,
    )
    runner.start()
    done_event.wait()   # 阻塞直到任务完成

    return exit_code[0]


def _check_and_elevate():
    """
    检测管理员权限，若缺少则自动提权。
    此函数在 QApplication 创建之前调用，无法使用 Qt 弹窗，
    退出/提权均通过 sys.exit 完成。
    """
    if _is_admin():
        return  # 已是管理员，直接继续

    # 尝试自动提权（触发 UAC）
    success = _relaunch_as_admin()
    if success:
        # UAC 请求已发出，新进程（管理员）正在启动，当前进程退出
        sys.exit(0)
    else:
        # 用户拒绝了 UAC 或提权失败
        # 此时 QApplication 尚未创建，用 ctypes MessageBox 提示
        import ctypes
        MB_YESNO        = 0x00000004
        MB_ICONWARNING  = 0x00000030
        IDYES           = 6
        msg = (
            "AutoFlow 需要管理员权限才能正常执行键鼠操作\n"
            "（如向其他程序注入鼠标点击、键盘输入等）。\n\n"
            "未以管理员身份运行时，向高权限程序的鼠标/键盘操作将被\n"
            "Windows UIPI 机制静默丢弃，导致自动化流程失效。\n\n"
            "建议：右键程序图标 → 以管理员身份运行\n\n"
            "是否仍以普通权限继续运行（部分功能可能失效）？"
        )
        result = ctypes.windll.user32.MessageBoxW(
            0, msg, "AutoFlow - 需要管理员权限", MB_YESNO | MB_ICONWARNING
        )
        if result != IDYES:
            sys.exit(0)
        # 用户选择继续（带限制运行）


# ──────────────────────────────────────────────────────────────
# 单实例检测（防止重复开启）
# ──────────────────────────────────────────────────────────────

_MUTEX_HANDLE = None   # 保持引用，防止被 GC

def _ensure_single_instance():
    """
    使用 Windows 命名互斥体确保只有一个 AutoFlow 实例运行。
    若已有实例，则激活其窗口并退出当前进程。
    必须在 QApplication 创建之前调用（使用 ctypes MessageBox）。
    """
    global _MUTEX_HANDLE
    import ctypes

    MUTEX_NAME = "Global\\AutoFlow_SingleInstance_XinyuCraft"
    ERROR_ALREADY_EXISTS = 183

    handle = ctypes.windll.kernel32.CreateMutexW(None, True, MUTEX_NAME)
    last_error = ctypes.windll.kernel32.GetLastError()

    if last_error == ERROR_ALREADY_EXISTS:
        # 已有实例运行，尝试激活其窗口
        hwnd = ctypes.windll.user32.FindWindowW("AutoFlowMainWindow", None)
        if not hwnd:
            # 按窗口标题查找（兜底）
            hwnd = ctypes.windll.user32.FindWindowW(None, "AutoFlow")
        if hwnd:
            # 如果最小化则恢复
            SW_RESTORE = 9
            ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        else:
            MB_OK = 0x00000000
            MB_ICONINFORMATION = 0x00000040
            ctypes.windll.user32.MessageBoxW(
                0,
                "AutoFlow 已在运行中！\n\n请在任务栏或系统托盘中找到已运行的窗口。",
                "AutoFlow - 已在运行",
                MB_OK | MB_ICONINFORMATION
            )
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
        sys.exit(0)
    else:
        # 当前是第一个实例，持有互斥体句柄直到进程退出
        _MUTEX_HANDLE = handle


def _ensure_language_dir(local_appdata: str):
    """
    确保 Language 目录存在，并写入示例/内置语言包文件（如不存在）。
    调用者无需关心是否首次运行。
    """
    lang_dir = os.path.join(local_appdata, "XinyuCraft", "AutoFlow", "Language")
    os.makedirs(lang_dir, exist_ok=True)

    # 写入英文包（如不存在）
    en_path = os.path.join(lang_dir, "en_US.json")
    if not os.path.exists(en_path):
        en_pack = {
            "_meta": {
                "name": "English (US)",
                "author": "AutoFlow built-in",
                "version": "1.0"
            },
            "app.name": "AutoFlow",
            "settings.language.en_US": "English (US)",
            "settings.language.zh_CN": "Simplified Chinese",
            "settings.language.zh_TW": "Traditional Chinese"
        }
        try:
            import json as _json
            with open(en_path, "w", encoding="utf-8") as f:
                _json.dump(en_pack, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # 写入繁体中文包（如不存在）
    tw_path = os.path.join(lang_dir, "zh_TW.json")
    if not os.path.exists(tw_path):
        tw_pack = {
            "_meta": {
                "name": "繁體中文",
                "author": "AutoFlow built-in",
                "version": "1.0"
            },
            "settings.language.zh_TW": "繁體中文",
            "settings.language.zh_CN": "簡體中文",
            "settings.language.en_US": "英文 (美國)"
        }
        try:
            import json as _json
            with open(tw_path, "w", encoding="utf-8") as f:
                _json.dump(tw_pack, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # 写入使用说明 README（如不存在）
    readme_path = os.path.join(lang_dir, "README.txt")
    if not os.path.exists(readme_path):
        readme = (
            "AutoFlow 语言包目录\n"
            "===================\n\n"
            "此目录用于存放自定义语言包文件。\n\n"
            "文件格式：JSON，文件名即语言代码，例如：\n"
            "  ja_JP.json  → 日语\n"
            "  ko_KR.json  → 韩语\n"
            "  fr_FR.json  → 法语\n\n"
            "JSON 结构示例：\n"
            '{\n'
            '  "_meta": { "name": "日本語", "version": "1.0" },\n'
            '  "app.name": "AutoFlow",\n'
            '  "settings.language.ja_JP": "日本語"\n'
            '}\n\n'
            "保存文件后重启 AutoFlow，新语言将出现在「设置 → 通用 → 语言」列表中。\n"
        )
        try:
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write(readme)
        except Exception:
            pass

    return lang_dir


def _apply_startup_language():
    """
    在 QApplication 创建后、MainWindow 实例化前，提前从 app_config.json 读取语言设置
    并从 Language 目录加载外部语言包，确保重启后语言切换真正生效。
    """
    _local = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    cfg_path = os.path.join(_local, "XinyuCraft", "AutoFlow", "app_config.json")
    lang = "zh_CN"
    try:
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            lang = data.get("language", "zh_CN") or "zh_CN"
    except Exception:
        pass

    from src.i18n import set_language, load_language_dir
    # 确保 Language 目录存在并包含示例文件
    lang_dir = _ensure_language_dir(_local)
    # 加载外部语言包
    load_language_dir(lang_dir)
    set_language(lang)


def main():
    # ── --run-task 无头模式（命令行直接运行任务，不显示 UI）──
    # 格式：AutoFlow.exe --run-task <task_id> [project.afp]
    # 示例：AutoFlow.exe --run-task a1b2c3d4
    #       AutoFlow.exe --run-task a1b2c3d4 "C:\path\to\project.afp"
    if "--run-task" in sys.argv:
        idx = sys.argv.index("--run-task")
        if idx + 1 >= len(sys.argv):
            print("[AutoFlow] 错误：--run-task 后必须跟任务 ID", file=sys.stderr)
            sys.exit(1)
        _headless_task_id = sys.argv[idx + 1]
        # 可选：从剩余参数中找 .afp 路径
        _headless_project = None
        for _a in sys.argv[1:]:
            if not _a.startswith("--") and _a.endswith(".afp") and os.path.isfile(_a):
                _headless_project = _a
                break
        # 语言目录（Runner 可能用到日志文字，此处仅保证目录存在）
        try:
            _local = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
            _ensure_language_dir(_local)
        except Exception:
            pass
        sys.exit(_run_task_headless(_headless_task_id, _headless_project))

    # ── 管理员权限检查（必须在 QApplication 创建之前）──
    # AutoFlow 需要管理员权限才能向高权限程序注入鼠标/键盘操作（UIPI 机制）
    _check_and_elevate()

    # ── 单实例检测（防止重复开启）──
    _ensure_single_instance()

    # 高 DPI 支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("AutoFlow")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("AutoFlow")

    # ── 设置应用图标 ──
    from PyQt6.QtGui import QIcon
    _icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "autoflow.ico")
    if os.path.exists(_icon_path):
        app.setWindowIcon(QIcon(_icon_path))
    else:
        # 回退到旧图标
        _old_icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.ico")
        if os.path.exists(_old_icon):
            app.setWindowIcon(QIcon(_old_icon))

    # ── 提前应用语言设置（必须在 MainWindow 构建 UI 之前）──
    _apply_startup_language()

    # ── 首次使用：显示免责声明 ──
    if should_show_disclaimer():
        dlg = DisclaimerDialog()
        result = dlg.exec()
        if not dlg.was_accepted():
            # 用户不同意，退出程序
            sys.exit(0)

    # 解析命令行
    start_minimized = "--minimized" in sys.argv
    project_path    = None
    for arg in sys.argv[1:]:
        if not arg.startswith("--") and os.path.isfile(arg):
            project_path = arg
            break

    # 默认项目路径迁移到 AppData\Local\XinyuCraft\AutoFlow\Project\
    _local = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    default_path = os.path.join(_local, "XinyuCraft", "AutoFlow", "Project", "autoflow_default.afp")
    # 兼容旧版：若新路径不存在但旧路径存在，自动迁移
    _old_default = os.path.join(os.path.expanduser("~"), "autoflow_default.afp")
    if project_path is None:
        if os.path.exists(default_path):
            project_path = default_path
        elif os.path.exists(_old_default):
            project_path = _old_default

    win = MainWindow(project_path=project_path, start_minimized=start_minimized)

    # 读取启动后行为：--minimized 命令行参数优先（开机自启时使用）
    # 否则按用户配置 launch_behavior 决定
    if not start_minimized:
        launch_behavior = getattr(win._project.config, 'launch_behavior', 'show')
        if launch_behavior == 'tray':
            # 隐藏至托盘，不显示主窗口
            pass
        elif launch_behavior == 'minimize':
            # 先 show 再最小化（保证任务栏有图标）
            win.show()
            win.showMinimized()
        else:
            # 默认：打开主界面
            win.show()
    # start_minimized=True 时主窗口已在 __init__ 末尾通过 QTimer 隐藏

    # ── 首次使用：显示新手引导 ──
    if should_show_tutorial():
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(300, lambda: _show_tutorial(win))

    sys.exit(app.exec())


def _show_tutorial(parent):
    """在主窗口显示后展示新手引导"""
    try:
        dlg = TutorialDialog(parent)
        dlg.exec()
    except Exception:
        pass


if __name__ == "__main__":
    main()

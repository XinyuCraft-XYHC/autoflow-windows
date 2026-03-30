"""
AutoFlow 主窗口
"""
import copy
import json
import os
import sys
import logging
import logging.handlers
import threading
from typing import Dict, List, Optional

from PyQt6.QtCore import (Qt, QThread, pyqtSignal, QObject,
                          QTimer, QSize, QPropertyAnimation, QEasingCurve)
from PyQt6.QtGui import QIcon, QAction, QCloseEvent, QColor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSplitter, QStackedWidget, QListWidget, QListWidgetItem,
    QFileDialog, QMessageBox, QSystemTrayIcon, QMenu, QInputDialog,
    QFrame, QSizePolicy, QApplication, QStatusBar, QDialog,
    QListWidgetItem, QScrollArea, QFormLayout, QComboBox, QDialogButtonBox,
    QLineEdit, QAbstractItemView
)
from PyQt6.QtGui import QDrag
from PyQt6.QtCore import QMimeData

from .effects import FadeStackedWidget, fade_in, show_toast, animate_dialog_show

from ..engine.models import Task, Project, AppConfig, Block
from ..version import FULL_NAME, VERSION
from ..engine.runner import TaskRunner
from ..engine.trigger_monitor import TriggerMonitor
from .themes import get_stylesheet, PALETTES
from .task_editor import TaskEditorPage
from .settings_page import SettingsPage
from .log_panel import LogPanel
from .block_editor import CoordPickerEdit, MacroRecorderWidget
from .plugin_page import PluginManagerPage
from ..i18n import tr, set_language, add_language_observer, remove_language_observer

logger = logging.getLogger("autoflow.main")

# ─── 统一数据目录：%LOCALAPPDATA%\XinyuCraft\AutoFlow ───
_APP_DATA_DIR     = os.path.join(os.environ.get("LOCALAPPDATA",
                        os.path.expanduser("~")), "XinyuCraft", "AutoFlow")
_APP_PROJECT_DIR  = os.path.join(_APP_DATA_DIR, "Project")
_APP_CONFIG_PATH  = os.path.join(_APP_DATA_DIR, "app_config.json")
_APP_LOG_DIR      = os.path.join(_APP_DATA_DIR, "Log")
_APP_LOG_PATH     = os.path.join(_APP_LOG_DIR, "autoflow.log")

def _ensure_dirs():
    """确保应用数据目录存在，并迁移旧版配置文件（如果有）"""
    os.makedirs(_APP_DATA_DIR,    exist_ok=True)
    os.makedirs(_APP_PROJECT_DIR, exist_ok=True)
    os.makedirs(_APP_LOG_DIR,     exist_ok=True)
    # 兼容旧版：将 ~/.autoflow_app.json 迁移到新路径
    _old_cfg = os.path.join(os.path.expanduser("~"), ".autoflow_app.json")
    if os.path.exists(_old_cfg) and not os.path.exists(_APP_CONFIG_PATH):
        try:
            import shutil
            shutil.copy2(_old_cfg, _APP_CONFIG_PATH)
        except Exception:
            pass

_ensure_dirs()


def _hex2rgb(hex_color: str) -> str:
    """将 #RRGGBB 转换为 'R,G,B' 字符串（用于 rgba()）"""
    try:
        c = hex_color.lstrip("#")
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        return f"{r},{g},{b}"
    except Exception:
        return "0,0,0"


def _save_app_config(data: dict):
    try:
        with open(_APP_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _load_app_config() -> dict:
    try:
        if os.path.exists(_APP_CONFIG_PATH):
            with open(_APP_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}




# ─── Qt 信号中转（跨线程安全） ───
class SignalBridge(QObject):
    log_signal    = pyqtSignal(str, str)
    task_finished = pyqtSignal(str, bool)
    trigger_fired = pyqtSignal(str)


# ─── 操作历史记录项 ───
class HistoryEntry:
    def __init__(self, desc: str, snapshot: dict):
        self.desc     = desc        # 操作描述
        self.snapshot = snapshot    # 项目快照 (to_dict)


# ─────────────────── 任务列表控件 ───────────────────
class TaskListWidget(QListWidget):
    """
    支持拖拽排序、多选（Shift点击）、空白取消选中的任务列表。
    分组标题行用单击切换折叠，不触发任务选中逻辑。
    """
    # 任务行被单击（task_id）
    task_clicked    = pyqtSignal(str)
    # 分组标题单击（gid）
    group_clicked   = pyqtSignal(str)
    # 任务拖动重排完成 (dragged_task_id, target_task_id_or_none, insert_after: bool)
    task_reordered  = pyqtSignal(str, str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_start_pos = None
        self._dragging       = False
        self._drag_item      = None
        # 多选
        self._selected_task_ids: set = set()
        self._anchor_task_id: str | None = None
        self._multiselect_mode: bool = False

        self.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

    # ── 鼠标事件 ──────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
            self._dragging = False
            item = self.itemAt(event.pos())
            self._drag_item = item
        # 不调 super() 的 press（避免 currentRowChanged 触发任务选中）
        # 但需要允许原生高亮
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (event.buttons() & Qt.MouseButton.LeftButton
                and self._drag_start_pos is not None
                and not self._dragging):
            dist = (event.pos() - self._drag_start_pos).manhattanLength()
            if dist > 8 and self._drag_item is not None:
                task_id = self._drag_item.data(Qt.ItemDataRole.UserRole)
                # 只允许拖动任务行，不拖分组标题
                if task_id and isinstance(task_id, str):
                    self._dragging = True
                    drag = QDrag(self)
                    mime = QMimeData()
                    mime.setData("application/x-tasklist-id",
                                 task_id.encode())
                    drag.setMimeData(mime)
                    drag.exec(Qt.DropAction.MoveAction)
                    self._dragging = False
                    self._drag_start_pos = None
                    return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self._dragging:
            item = self.itemAt(event.pos())
            if item is None:
                # 点击空白区域 → 清除选中
                self._clear_task_selection()
                self.clearSelection()
                self.setCurrentRow(-1)
                self._drag_start_pos = None
                return
            task_id  = item.data(Qt.ItemDataRole.UserRole)
            item_kind = item.data(Qt.ItemDataRole.UserRole + 2)
            shift_held = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

            if task_id is None and item_kind == "group_header":
                # 分组标题单击 → 只发出折叠信号，不干扰任务选中
                gid = item.data(Qt.ItemDataRole.UserRole + 1)
                if gid:
                    self.group_clicked.emit(gid)
                self._drag_start_pos = None
                return

            if task_id and isinstance(task_id, str):
                # 普通任务行
                if shift_held:
                    self._do_shift_select(task_id)
                else:
                    self._do_single_select(task_id)
                self.task_clicked.emit(task_id)
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-tasklist-id"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-tasklist-id"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat("application/x-tasklist-id"):
            event.ignore()
            return
        drag_id = event.mimeData().data("application/x-tasklist-id").data().decode()
        drop_item = self.itemAt(event.pos())
        if drop_item is None:
            event.ignore()
            return
        target_id = drop_item.data(Qt.ItemDataRole.UserRole)
        # target 是分组标题则忽略
        if not target_id or not isinstance(target_id, str):
            event.ignore()
            return
        # 判断插入在 target 前还是后
        item_rect = self.visualItemRect(drop_item)
        insert_after = (event.position().toPoint().y() > item_rect.center().y())
        self.task_reordered.emit(drag_id, target_id, insert_after)
        event.acceptProposedAction()

    # ── 多选逻辑 ──────────────────────────────────────
    def _do_single_select(self, task_id: str):
        if not self._multiselect_mode and task_id in self._selected_task_ids:
            self._selected_task_ids.clear()
            self._anchor_task_id = None
        else:
            self._multiselect_mode = False
            self._selected_task_ids = {task_id}
            self._anchor_task_id = task_id
        self._sync_task_selection_ui()

    def _do_shift_select(self, task_id: str):
        self._multiselect_mode = True
        all_task_ids = []
        for i in range(self.count()):
            it = self.item(i)
            tid = it.data(Qt.ItemDataRole.UserRole) if it else None
            if tid and isinstance(tid, str):
                all_task_ids.append(tid)
        anchor = self._anchor_task_id or (next(iter(self._selected_task_ids), None))
        if not anchor:
            anchor = task_id
        try:
            a_idx = all_task_ids.index(anchor)
        except ValueError:
            a_idx = 0
        try:
            b_idx = all_task_ids.index(task_id)
        except ValueError:
            b_idx = len(all_task_ids) - 1
        lo, hi = min(a_idx, b_idx), max(a_idx, b_idx)
        self._selected_task_ids = set(all_task_ids[lo:hi + 1])
        self._sync_task_selection_ui()

    def _clear_task_selection(self):
        self._selected_task_ids.clear()
        self._anchor_task_id = None
        self._multiselect_mode = False
        self._sync_task_selection_ui()

    def _sync_task_selection_ui(self):
        """根据 _selected_task_ids 更新条目高亮颜色"""
        for i in range(self.count()):
            it = self.item(i)
            if it is None:
                continue
            tid = it.data(Qt.ItemDataRole.UserRole)
            if tid and isinstance(tid, str):
                if tid in self._selected_task_ids:
                    it.setBackground(QColor("#1e3a5f"))
                    it.setForeground(QColor("#89B4FA"))
                else:
                    it.setBackground(QColor("transparent"))
                    # 恢复默认前景色
                    it.setForeground(QColor("#CDD6F4"))

    def setAcceptDrops(self, accept: bool):
        super().setAcceptDrops(accept)
        if accept:
            self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)


class MainWindow(QMainWindow):
    # 跨线程信号：子线程完成后安全回到主线程
    _update_result_sig       = pyqtSignal(dict)   # 更新检测结果
    _announcements_result_sig = pyqtSignal(list)  # 远程公告结果

    def __init__(self, project_path: Optional[str] = None,
                 start_minimized: bool = False):
        super().__init__()
        self._project_path: Optional[str] = project_path
        self._project: Project = Project()
        self._runners: Dict[str, TaskRunner] = {}
        self._quitting: bool = False   # 正在退出，避免 closeEvent 误弹托盘通知
        self._bridge  = SignalBridge()
        self._bridge.log_signal.connect(self._on_log)
        self._bridge.task_finished.connect(self._on_task_finished)
        self._bridge.trigger_fired.connect(self._on_trigger_fired)

        self._trigger_monitor: Optional[TriggerMonitor] = None
        self._task_editors: Dict[str, TaskEditorPage] = {}

        # 强制终止热键（全局后台线程）
        self._force_stop_thread: Optional[threading.Thread] = None
        self._force_stop_stop_event = threading.Event()

        # 撤回/重做历史
        self._history: List[HistoryEntry] = []
        self._history_pos: int = -1          # 当前位置
        self._max_undo: int = 50
        self._restoring: bool = False        # 快照恢复期间屏蔽 _push_history
        self._selected_task_id: Optional[str] = None  # 当前选中的任务 ID

        # 防抖定时器：任务变化后延迟重启触发器监控
        self._trigger_reload_timer = QTimer(self)
        self._trigger_reload_timer.setSingleShot(True)
        self._trigger_reload_timer.setInterval(1500)
        self._trigger_reload_timer.timeout.connect(self._start_trigger_monitor)

        # 自动保存定时器
        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.timeout.connect(self._auto_save)

        # 修改标记
        self._modified = False

        # 分组折叠状态（gid -> True=折叠）
        self._collapsed_groups: set = set()

        self.setWindowTitle(f"{FULL_NAME} — 智能自动化工具")
        self.resize(1200, 780)
        self.setMinimumSize(900, 600)
        # 设置窗口类名，供单实例检测（FindWindowW）查找
        self.setObjectName("AutoFlowMainWindow")

        # ── 设置应用图标 ──
        _icon_path = os.path.join(os.path.dirname(__file__), "../../assets/icon.ico")
        if os.path.exists(_icon_path):
            _app_icon = QIcon(_icon_path)
            self.setWindowIcon(_app_icon)
            QApplication.instance().setWindowIcon(_app_icon)

        self._build_ui()
        self._setup_tray()
        self._setup_logging()
        self._setup_shortcuts()

        # 决定打开哪个项目
        app_cfg = _load_app_config()
        if project_path and os.path.exists(project_path):
            self._load_project(project_path)
        elif app_cfg.get("reopen_last") and app_cfg.get("last_project"):
            lp = app_cfg["last_project"]
            if os.path.exists(lp):
                self._load_project(lp)
            else:
                self._new_project()
        else:
            self._new_project()

        self._start_trigger_monitor()
        # 延迟 100ms 应用主题（确保窗口句柄已创建）
        QTimer.singleShot(100, lambda: self._apply_theme(self._project.config.theme))
        self._reset_auto_save_timer()
        # 启动强制终止全局热键监听
        QTimer.singleShot(200, self._restart_force_stop_hotkey)

        if start_minimized:
            QTimer.singleShot(100, self.hide)

        # ── 注册语言变更观察者（语言切换后立即刷新侧边栏文字）──
        add_language_observer(self._retranslate_ui)

        # ── 初始化插件系统 ──
        QTimer.singleShot(300, self._init_plugin_manager)

        # ── 跨线程信号连接（子线程→主线程安全回调）──
        self._update_result_sig.connect(self._show_update_tip)
        self._announcements_result_sig.connect(self._show_announcements)

        # ── 启动后静默检测更新（延迟 5 秒，不阻塞启动）──
        QTimer.singleShot(5000, self._silent_check_update)

        # ── 启动后拉取远程公告（延迟 8 秒，避免与更新检测同时发起网络请求）──
        QTimer.singleShot(8000, self._fetch_remote_announcements)

    def _retranslate_ui(self):
        """语言切换后立即刷新所有静态 UI 文字"""
        from ..i18n import tr
        # ── 侧边栏 ──
        if hasattr(self, '_tasks_lbl'):
            self._tasks_lbl.setText(tr("sidebar.tasks"))
        if hasattr(self, '_add_task_btn'):
            self._add_task_btn.setText(tr("sidebar.new_task") + "  Ctrl+T")
        if hasattr(self, '_btn_undo'):
            self._btn_undo.setText(tr("sidebar.undo"))
        if hasattr(self, '_btn_redo'):
            self._btn_redo.setText(tr("sidebar.redo"))
        if hasattr(self, '_btn_hist'):
            self._btn_hist.setText(tr("sidebar.history") + "  Ctrl+H")
        if hasattr(self, '_btn_settings'):
            self._btn_settings.setText(tr("sidebar.settings"))
        if hasattr(self, '_sidebar_file_btns'):
            _labels = [
                (tr("sidebar.new_project") + "  Ctrl+N"),
                (tr("sidebar.open_project") + "  Ctrl+O"),
                (tr("sidebar.save_project") + "  Ctrl+S"),
                (tr("sidebar.save_as") + "  Ctrl+Shift+S"),
                (tr("sidebar.close_project") + "  Ctrl+W"),
            ]
            for btn, lbl in zip(self._sidebar_file_btns, _labels):
                btn.setText(lbl)
        if hasattr(self, '_btn_settings'):
            self._btn_settings.setText(tr("sidebar.settings"))
        if hasattr(self, '_btn_plugins'):
            self._btn_plugins.setText("🔌 " + tr("sidebar.plugins"))
        # ── 刷新任务列表（任务名/状态文字）──
        self._refresh_task_list()
        # ── 刷新设置页（如已打开）──
        if hasattr(self, '_settings_page'):
            self._settings_page.retranslate()

    # ─────────────────── 构建 UI ───────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar = self._build_sidebar()
        root.addWidget(sidebar)

        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.setHandleWidth(4)

        self._stack = FadeStackedWidget(duration=200)
        right_splitter.addWidget(self._stack)

        self._log_panel = LogPanel()
        self._log_panel.setMaximumHeight(200)
        right_splitter.addWidget(self._log_panel)
        right_splitter.setSizes([580, 160])

        root.addWidget(right_splitter)

        self.statusBar().setObjectName("status_bar")
        self._status_label = QLabel("就绪")
        self.statusBar().addWidget(self._status_label)

        # 状态栏右侧：撤回/重做计数
        self._undo_label = QLabel("撤回: 0/0")
        self._undo_label.setStyleSheet("color: #6C7086; font-size: 11px; padding-right: 8px;")
        self.statusBar().addPermanentWidget(self._undo_label)

        # 修改标记
        self._modified_label = QLabel("")
        self.statusBar().addPermanentWidget(self._modified_label)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(200)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Logo 区
        logo_area = QWidget()
        la = QVBoxLayout(logo_area)
        la.setContentsMargins(14, 18, 14, 10)
        la.setSpacing(2)
        logo_lbl = QLabel("AutoFlow")
        logo_lbl.setObjectName("app_title")
        la.addWidget(logo_lbl)
        sub_lbl = QLabel("智能自动化工具")
        sub_lbl.setStyleSheet("color:#6C7086; font-size:10px;")
        la.addWidget(sub_lbl)
        layout.addWidget(logo_area)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("sidebar_sep")
        layout.addWidget(sep)

        # ── 任务列表标题行（含分组管理按钮） ──
        tasks_header = QHBoxLayout()
        tasks_header.setContentsMargins(14, 8, 8, 4)
        self._tasks_lbl = QLabel("任务列表")
        self._tasks_lbl.setObjectName("sidebar_section_lbl")
        self._tasks_lbl.setContentsMargins(0, 0, 0, 0)
        tasks_header.addWidget(self._tasks_lbl)
        tasks_header.addStretch()
        self._group_btn = QPushButton("⊞")
        self._group_btn.setToolTip("管理任务分组")
        self._group_btn.setObjectName("btn_flat")
        self._group_btn.setFixedSize(22, 22)
        self._group_btn.clicked.connect(self._show_group_manager)
        tasks_header.addWidget(self._group_btn)
        layout.addLayout(tasks_header)

        self._task_list = TaskListWidget()
        self._task_list.setObjectName("task_list")
        # 任务行单击 → 显示编辑器
        self._task_list.task_clicked.connect(self._on_task_item_clicked)
        # 分组标题单击 → 切换折叠
        self._task_list.group_clicked.connect(self._on_group_item_clicked)
        # 任务拖动重排
        self._task_list.task_reordered.connect(self._on_task_reordered)
        layout.addWidget(self._task_list)

        self._add_task_btn = QPushButton("+  新建任务  Ctrl+T")
        self._add_task_btn.setObjectName("sidebar_add_btn")
        self._add_task_btn.setToolTip("新建任务 (Ctrl+T)")
        self._add_task_btn.clicked.connect(self._add_task)
        layout.addWidget(self._add_task_btn)

        layout.addStretch()

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setObjectName("sidebar_sep")
        layout.addWidget(sep2)

        # 底部按钮：新建/打开/保存/另存为/关闭/撤回/重做/历史/设置
        self._btn_undo = self._make_sidebar_btn("撤回  Ctrl+Z",         self._undo)
        self._btn_redo = self._make_sidebar_btn("重做  Ctrl+Y / Ctrl+Shift+Z", self._redo)
        self._btn_hist = self._make_sidebar_btn("操作历史  Ctrl+H", self._show_history)

        self._sidebar_file_btns = []
        for text, slot, tip in [
            ("新建项目  Ctrl+N",     self._new_project_prompt, "新建项目 (Ctrl+N)"),
            ("打开项目  Ctrl+O",     self._open_project,       "打开项目 (Ctrl+O)"),
            ("保存项目  Ctrl+S",     self._save_project,       "保存项目 (Ctrl+S)"),
            ("另存为  Ctrl+Shift+S", self._save_project_as,    "另存为 (Ctrl+Shift+S)"),
            ("关闭项目  Ctrl+W",     self._close_project,      "关闭项目 (Ctrl+W)"),
        ]:
            btn = self._make_sidebar_btn(text, slot)
            btn.setToolTip(tip)
            layout.addWidget(btn)
            self._sidebar_file_btns.append(btn)

        sep3 = QFrame(); sep3.setFrameShape(QFrame.Shape.HLine)
        sep3.setObjectName("sidebar_sep")
        layout.addWidget(sep3)

        layout.addWidget(self._btn_undo)
        layout.addWidget(self._btn_redo)
        layout.addWidget(self._btn_hist)

        sep4 = QFrame(); sep4.setFrameShape(QFrame.Shape.HLine)
        sep4.setObjectName("sidebar_sep")
        layout.addWidget(sep4)

        self._btn_refresh_ui = self._make_sidebar_btn("🔄 刷新界面  F5", self._force_ui_refresh)
        self._btn_refresh_ui.setToolTip("强制刷新当前编辑器的功能块和触发器列表（修复偶发 UI 错乱）(F5)")
        layout.addWidget(self._btn_refresh_ui)

        self._btn_settings = self._make_sidebar_btn("设置", self._show_settings)
        layout.addWidget(self._btn_settings)

        self._btn_plugins = self._make_sidebar_btn("🔌 插件管理", self._show_plugin_manager)
        layout.addWidget(self._btn_plugins)

        layout.setContentsMargins(0, 0, 0, 8)
        return sidebar

    def _make_sidebar_btn(self, text: str, slot) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("sidebar_btn")
        btn.clicked.connect(slot)
        return btn

    def _apply_theme(self, theme: str = "dark"):
        """应用主题（支持亚克力毛玻璃效果）"""
        from .themes import PALETTES as _P
        from .block_editor import set_theme_dark
        # 确定当前调色板
        effective_theme = theme
        if theme == "system":
            try:
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
                )
                val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                winreg.CloseKey(key)
                effective_theme = "light" if val == 1 else "dark"
            except Exception:
                effective_theme = "dark"
        palette = _P.get(effective_theme, _P["dark"])
        is_dark  = palette["mode"] == "dark"

        # ── 更新全局主题状态（BlockItem / TriggerCard 据此渲染）──
        set_theme_dark(is_dark)

        # ── 生成 QSS ──
        qss = get_stylesheet(effective_theme)

        # ── 侧边栏专属样式（根据主题动态着色） ──
        hover_bg = "rgba(255,255,255,0.07)" if is_dark else "rgba(0,0,0,0.05)"
        qss += f"""
#sidebar_sep {{ max-height: 1px; margin: 0 10px; }}
#sidebar_section_lbl {{
    color: {palette['fg2']}; font-size: 10px; font-weight: bold;
    padding: 10px 14px 4px 14px; letter-spacing: 1px;
}}
#sidebar_btn {{
    background: transparent; border: none; border-radius: 0;
    padding: 10px 14px; text-align: left; font-size: 12px;
    color: {palette['fg1']};
}}
#sidebar_btn:hover {{ background: {hover_bg}; color: {palette['fg0']}; }}
#sidebar_add_btn {{
    background: transparent; border: 1px dashed {palette['bg3']};
    border-radius: 8px; margin: 4px 10px; padding: 7px;
    font-size: 12px; color: {palette['fg1']};
}}
#sidebar_add_btn:hover {{ border-color: {palette['accent']}; color: {palette['accent']}; }}
#task_list {{
    background: transparent; border: none; outline: none;
}}
#task_list::item {{
    padding: 8px 14px; border-radius: 6px; margin: 1px 6px;
    color: {palette['fg1']};
}}
#task_list::item:selected {{
    background: {palette['accent']}22; color: {palette['accent']};
}}
"""
        self.setStyleSheet(qss)

        # ── 通知 LogPanel 更新颜色 ──
        if hasattr(self, '_log_panel'):
            self._log_panel.update_theme_colors(palette)

        # ── 通知所有任务编辑器刷新功能块/触发器颜色 ──
        if hasattr(self, '_task_editors'):
            for editor in self._task_editors.values():
                if hasattr(editor, '_block_list'):
                    editor._block_list._refresh()
                if hasattr(editor, '_trigger_editor'):
                    editor._trigger_editor._refresh()



    # ─────────────────── 系统托盘 ───────────────────

    def _setup_tray(self):
        self._tray = QSystemTrayIcon(self)
        icon_path = os.path.join(os.path.dirname(__file__), "../../assets/icon.ico")
        if os.path.exists(icon_path):
            self._tray.setIcon(QIcon(icon_path))
        else:
            self._tray.setIcon(self.style().standardIcon(
                self.style().StandardPixmap.SP_ComputerIcon))

        tray_menu = QMenu()
        tray_menu.addAction("显示主窗口", self.show_and_raise)
        tray_menu.addSeparator()
        self._tray_run_menu = tray_menu.addMenu("手动运行任务")
        tray_menu.addSeparator()
        tray_menu.addAction("退出", self._quit_app)

        self._tray.setContextMenu(tray_menu)
        self._tray.setToolTip("AutoFlow — 智能自动化工具")
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _refresh_tray_menu(self):
        self._tray_run_menu.clear()
        for task in self._project.tasks:
            action = self._tray_run_menu.addAction(
                f"{'>' if task.enabled else 'o'}  {task.name}"
            )
            action.triggered.connect(lambda _, tid=task.id: self._run_task(tid))

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_and_raise()

    def show_and_raise(self):
        self.show(); self.raise_(); self.activateWindow()

    # ─────────────────── 日志 ───────────────────

    def _setup_logging(self):
        root_logger = logging.getLogger("autoflow")
        root_logger.setLevel(logging.DEBUG)

        # ── UI 日志面板 Handler ──
        ui_handler = _QtLogHandler(self._bridge.log_signal)
        ui_handler.setFormatter(logging.Formatter("%(message)s"))
        root_logger.addHandler(ui_handler)

        # ── 文件日志 Handler ──
        log_path = getattr(self._project.config, "log_path", "").strip()
        if not log_path:
            log_path = _APP_LOG_PATH
        try:
            file_handler = logging.handlers.RotatingFileHandler(
                log_path, maxBytes=4 * 1024 * 1024, backupCount=3,
                encoding="utf-8"
            )
            file_handler.setFormatter(
                logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                                  datefmt="%Y-%m-%d %H:%M:%S")
            )
            root_logger.addHandler(file_handler)
            self._file_log_handler = file_handler
        except Exception as e:
            logger.warning(f"日志文件初始化失败: {e}")

    def _setup_shortcuts(self):
        """注册全局快捷键（窗口聚焦时生效）"""
        def _bind(seq: str, slot):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.ShortcutContext.WindowShortcut)
            sc.activated.connect(slot)

        # ── 撤回 / 重做 ──
        _bind("Ctrl+Z",       self._undo)
        _bind("Ctrl+Y",       self._redo)
        _bind("Ctrl+Shift+Z", self._redo)   # 兼容

        # ── 项目操作 ──
        _bind("Ctrl+N", self._new_project_prompt)
        _bind("Ctrl+O", self._open_project)
        _bind("Ctrl+S", self._save_project)
        _bind("Ctrl+Shift+S", self._save_project_as)
        _bind("Ctrl+W", self._close_project)

        # ── 新建任务 ──
        _bind("Ctrl+T", self._add_task)

        # ── 操作历史 ──
        _bind("Ctrl+H", self._show_history)

        # ── 刷新界面（F5）──
        _bind("F5", self._force_ui_refresh)

    def _force_ui_refresh(self):
        """F5：强制刷新当前任务编辑器的功能块列表和触发器列表（用于修复偶发 UI 错乱）"""
        refreshed = False
        if hasattr(self, '_task_editors'):
            for editor in self._task_editors.values():
                if hasattr(editor, '_block_list'):
                    bl = editor._block_list
                    # 直接触发 _do_refresh（跳过防抖，立即执行）
                    if hasattr(bl, '_do_refresh'):
                        bl._do_refresh()
                    else:
                        bl._refresh()
                    refreshed = True
                if hasattr(editor, '_trigger_editor'):
                    editor._trigger_editor._refresh()
                    refreshed = True
        # 强制重绘整个主窗口
        self.update()
        self.repaint()
        if refreshed:
            show_toast(self, "界面已刷新", duration_ms=1500, color="#A6E3A1")



    def _on_log(self, level: str, message: str):
        self._log_panel.append(level, message)

    # ─────────────────── 项目管理 ───────────────────

    def _new_project(self):
        self._project = Project()
        self._project_path = None
        self._task_editors.clear()
        self._history.clear()
        self._history_pos = -1
        self._modified = False
        self._refresh_task_list()
        self._refresh_tray_menu()
        self._push_history("新建项目")
        self.setWindowTitle(f"{FULL_NAME} — 新项目")
        self._status_label.setText("新项目")
        self._update_undo_label()

    def _new_project_prompt(self):
        """检查保存后再新建"""
        if self._modified:
            reply = QMessageBox.question(
                self, "新建项目",
                "当前项目有未保存的更改，是否保存？",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Save:
                self._save_project()
            elif reply == QMessageBox.StandardButton.Cancel:
                return
        self._new_project()

    def _close_project(self):
        """关闭当前项目，回到空白状态"""
        if self._modified:
            reply = QMessageBox.question(
                self, "关闭项目",
                "当前项目有未保存的更改，关闭将丢失。确定关闭？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        # 清理编辑器
        for w in list(self._task_editors.values()):
            self._stack.removeWidget(w)
            w.deleteLater()
        self._task_editors.clear()
        self._project = Project()
        self._project_path = None
        self._history.clear()
        self._history_pos = -1
        self._modified = False
        self._task_list.clear()
        self._refresh_tray_menu()
        self.setWindowTitle(f"{FULL_NAME} — 智能自动化工具")
        self._status_label.setText("已关闭项目")
        self._update_undo_label()

    def _load_project(self, path: str):
        try:
            self._project = Project.load(path)
            self._project_path = path
            self._task_editors.clear()
            self._history.clear()
            self._history_pos = -1
            self._modified = False
            self._refresh_task_list()
            self.setWindowTitle(f"{FULL_NAME} — {os.path.basename(path)}")
            self._status_label.setText(f"已加载: {os.path.basename(path)}")
            self._start_trigger_monitor()
            self._push_history(f"打开项目: {os.path.basename(path)}")
            self._reset_auto_save_timer()
            self._apply_theme(self._project.config.theme)
            # 同步坐标选点快捷键
            CoordPickerEdit.pick_hotkey     = getattr(self._project.config, "coord_pick_hotkey", "F9")
            MacroRecorderWidget.stop_hotkey = getattr(self._project.config, "macro_stop_hotkey", "F10")
            # 同步语言设置
            set_language(getattr(self._project.config, "language", "zh_CN"))
            # 记住上次打开路径 + 语言（确保下次重启提前应用正确语言）
            app_cfg = _load_app_config()
            app_cfg["last_project"] = path
            app_cfg["reopen_last"] = self._project.config.reopen_last_project
            app_cfg["language"] = getattr(self._project.config, "language", "zh_CN")
            _save_app_config(app_cfg)
            logger.info(f"项目已加载: {path}")
        except Exception as e:
            QMessageBox.critical(self, "加载失败", f"无法加载项目文件：\n{e}")

    def _open_project(self):
        if self._modified:
            reply = QMessageBox.question(
                self, "打开项目",
                "当前有未保存的更改，是否保存？",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Save:
                self._save_project()
            elif reply == QMessageBox.StandardButton.Cancel:
                return
        path, _ = QFileDialog.getOpenFileName(
            self, "打开项目", _APP_PROJECT_DIR, "AutoFlow 项目 (*.afp *.json);;所有文件 (*)")
        if path:
            for w in list(self._task_editors.values()):
                self._stack.removeWidget(w)
                w.deleteLater()
            self._load_project(path)

    def _save_project(self, silent: bool = False):
        for editor in self._task_editors.values():
            editor.save_to_task()

        if not self._project_path:
            default_name = "新项目.afp"
            path, _ = QFileDialog.getSaveFileName(
                self, "保存项目",
                os.path.join(_APP_PROJECT_DIR, default_name),
                "AutoFlow 项目 (*.afp);;JSON文件 (*.json)")
            if not path:
                return
            self._project_path = path

        try:
            self._project.save(self._project_path)
            self._modified = False
            self._modified_label.setText("")
            self.setWindowTitle(f"{FULL_NAME} — {os.path.basename(self._project_path)}")
            if not silent:
                self._status_label.setText(f"已保存: {os.path.basename(self._project_path)}")
            # 更新最近路径
            app_cfg = _load_app_config()
            app_cfg["last_project"] = self._project_path
            _save_app_config(app_cfg)
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"保存失败：\n{e}")

    def _save_project_as(self):
        """项目另存为（选择新路径保存，并将当前路径切换到新路径）"""
        for editor in self._task_editors.values():
            editor.save_to_task()

        # 以当前文件名为默认，若无则用"新项目"
        current_name = (os.path.basename(self._project_path)
                        if self._project_path else "新项目.afp")
        start_dir = (os.path.dirname(self._project_path)
                     if self._project_path else _APP_PROJECT_DIR)

        path, _ = QFileDialog.getSaveFileName(
            self, "项目另存为",
            os.path.join(start_dir, current_name),
            "AutoFlow 项目 (*.afp);;JSON文件 (*.json)")
        if not path:
            return

        try:
            self._project.save(path)
            self._project_path = path
            self._modified = False
            self._modified_label.setText("")
            self.setWindowTitle(f"{FULL_NAME} — {os.path.basename(path)}")
            self._status_label.setText(f"已另存为: {os.path.basename(path)}")
            # 更新最近路径
            app_cfg = _load_app_config()
            app_cfg["last_project"] = path
            _save_app_config(app_cfg)
        except Exception as e:
            QMessageBox.critical(self, "另存为失败", f"保存失败：\n{e}")

    def _auto_save(self):
        """自动保存（静默）"""
        """自动保存（静默）"""
        if self._modified and self._project_path:
            self._save_project(silent=True)
            self._status_label.setText(
                f"自动保存: {os.path.basename(self._project_path)}")

    def _reset_auto_save_timer(self):
        self._auto_save_timer.stop()
        cfg = self._project.config
        if cfg.auto_save_enabled and cfg.auto_save_interval > 0:
            self._auto_save_timer.start(cfg.auto_save_interval * 1000)

    # ─────────────────── 撤回 / 重做 / 历史 ───────────────────

    def _push_history(self, desc: str):
        """保存当前项目快照到历史栈"""
        if self._restoring:
            return   # 快照恢复期间禁止写入历史
        for editor in self._task_editors.values():
            editor.save_to_task()
        snapshot = copy.deepcopy(self._project.to_dict())
        entry = HistoryEntry(desc, snapshot)

        # 截断当前位置之后的历史
        if self._history_pos < len(self._history) - 1:
            self._history = self._history[:self._history_pos + 1]

        self._history.append(entry)
        # 限制历史数量
        max_steps = self._project.config.max_undo_steps or 50
        if len(self._history) > max_steps:
            self._history = self._history[-max_steps:]
        self._history_pos = len(self._history) - 1
        self._update_undo_label()

    def _undo(self):
        if self._history_pos <= 0:
            self._status_label.setText("没有更多撤回步骤")
            return
        self._history_pos -= 1
        self._restore_snapshot(self._history[self._history_pos].snapshot)
        self._status_label.setText(f"已撤回: {self._history[self._history_pos].desc}")
        self._update_undo_label()

    def _redo(self):
        if self._history_pos >= len(self._history) - 1:
            self._status_label.setText("没有更多重做步骤")
            return
        self._history_pos += 1
        self._restore_snapshot(self._history[self._history_pos].snapshot)
        self._status_label.setText(f"已重做: {self._history[self._history_pos].desc}")
        self._update_undo_label()

    def _restore_snapshot(self, snapshot: dict):
        """从快照恢复项目状态"""
        self._restoring = True
        # 清理现有编辑器（先断开 changed 信号，避免延迟事件触发 _push_history）
        for w in list(self._task_editors.values()):
            try:
                w.changed.disconnect()
            except Exception:
                pass
            self._stack.removeWidget(w)
            w.deleteLater()
        self._task_editors.clear()

        self._project = Project(version=snapshot.get("version", "1.0"))
        from ..engine.models import Task as _Task, AppConfig as _AC
        self._project.tasks            = [_Task.from_dict(t) for t in snapshot.get("tasks", [])]
        self._project.config           = _AC.from_dict(snapshot.get("config", {}))
        self._project.task_groups      = list(snapshot.get("task_groups", []))
        self._project.global_variables = dict(snapshot.get("global_variables", {}))

        # 同步 settings_page 对 config 的引用，避免旧引用覆盖恢复后的配置
        if hasattr(self, "_settings_page"):
            self._settings_page.config = self._project.config

        self._refresh_task_list()
        self._refresh_tray_menu()
        self._modified = True
        self._modified_label.setText("  * 未保存  ")

        # 延迟到下一个事件循环周期：
        # 1. 解除 _restoring 保护（覆盖 deleteLater 残留信号）
        # 2. 尝试恢复之前选中的任务
        def _after_restore():
            self._restoring = False
            self._reselect_task()

        QTimer.singleShot(0, _after_restore)

    def _reselect_task(self):
        """恢复到操作前选中的任务（遍历列表找匹配行并激活）"""
        tid = self._selected_task_id
        if not tid:
            return
        # 检查任务在恢复后的项目里是否还存在
        task = next((t for t in self._project.tasks if t.id == tid), None)
        if not task:
            # 任务不在快照里（可能已被撤销删除），清除选中状态
            self._selected_task_id = None
            return
        # 在列表里找到对应行并设置选中（会触发 _on_task_selected → _show_task_editor）
        for row in range(self._task_list.count()):
            item = self._task_list.item(row)
            if item and item.data(Qt.ItemDataRole.UserRole) == tid:
                self._task_list.setCurrentRow(row)
                return

    def _update_undo_label(self):
        total = len(self._history)
        pos   = self._history_pos + 1
        self._undo_label.setText(f"历史: {pos}/{total}")

    def _show_history(self):
        """弹出操作历史对话框"""
        dlg = QDialog(self)
        dlg.setWindowTitle("操作历史")
        dlg.setMinimumWidth(420)
        dlg.setMinimumHeight(360)
        layout = QVBoxLayout(dlg)

        hint = QLabel("点击条目可跳转到该历史节点")
        hint.setObjectName("hint")
        layout.addWidget(hint)

        lst = QListWidget()
        for i, entry in enumerate(self._history):
            marker = " <-- 当前" if i == self._history_pos else ""
            item = QListWidgetItem(f"{i+1}. {entry.desc}{marker}")
            item.setData(Qt.ItemDataRole.UserRole, i)
            if i == self._history_pos:
                item.setForeground(QColor("#89B4FA"))
            lst.addItem(item)
        lst.scrollToBottom()
        layout.addWidget(lst)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_restore = QPushButton("还原到此节点")
        btn_restore.setObjectName("btn_primary")
        btn_box.addButton(btn_restore, QDialogButtonBox.ButtonRole.ActionRole)
        btn_box.rejected.connect(dlg.reject)
        layout.addWidget(btn_box)

        def do_restore():
            row = lst.currentRow()
            if row < 0:
                return
            idx = lst.item(row).data(Qt.ItemDataRole.UserRole)
            self._history_pos = idx
            self._restore_snapshot(self._history[idx].snapshot)
            self._status_label.setText(f"已还原到: {self._history[idx].desc}")
            self._update_undo_label()
            dlg.accept()

        btn_restore.clicked.connect(do_restore)
        dlg.exec()

    # ─────────────────── 任务管理 ───────────────────

    def _add_task(self):
        name, ok = QInputDialog.getText(self, "新建任务", "任务名称：", text="新任务")
        if not ok or not name.strip():
            return
        task = Task(name=name.strip())
        self._project.tasks.append(task)
        self._refresh_task_list()
        idx = len(self._project.tasks) - 1
        self._task_list.setCurrentRow(idx)
        self._refresh_tray_menu()
        if hasattr(self, '_settings_page'):
            self._settings_page.refresh_tasks(self._project.tasks)
        self._mark_modified()
        self._push_history(f"新建任务: {task.name}")

    def _refresh_task_list(self):
        self._task_list.clear()
        groups = self._project.task_groups  # [{"id":..,"name":..}]
        tasks  = self._project.tasks

        # 分组任务
        gid_to_tasks = {}
        ungrouped = []
        for t in tasks:
            gid = t.group_id or ""
            if gid:
                gid_to_tasks.setdefault(gid, []).append(t)
            else:
                ungrouped.append(t)

        from PyQt6.QtGui import QFont
        # 先输出有分组的任务
        for grp in groups:
            gid      = grp["id"]
            gname    = grp["name"]
            is_col   = gid in self._collapsed_groups
            cnt      = len(gid_to_tasks.get(gid, []))
            arrow    = "▶" if is_col else "▼"
            # 分组标题行
            header = QListWidgetItem(f"{arrow} 📁 {gname}  ({cnt})")
            header.setData(Qt.ItemDataRole.UserRole, None)          # None=分组标题
            header.setData(Qt.ItemDataRole.UserRole + 1, gid)       # 分组ID
            header.setData(Qt.ItemDataRole.UserRole + 2, "group_header")  # 标记为可折叠
            header.setFlags(header.flags() | Qt.ItemFlag.ItemIsSelectable)
            header.setForeground(QColor("#89B4FA"))
            f = header.font()
            f.setBold(True)
            f.setPointSize(10)
            header.setFont(f)
            self._task_list.addItem(header)
            if not is_col:
                for task in gid_to_tasks.get(gid, []):
                    item = QListWidgetItem()
                    status = "▷" if task.enabled else "○"
                    item.setText(f"    {status}  {task.name}")
                    item.setData(Qt.ItemDataRole.UserRole, task.id)
                    self._task_list.addItem(item)

        # 未分组任务
        if ungrouped:
            for task in ungrouped:
                item = QListWidgetItem()
                status = "▷" if task.enabled else "○"
                item.setText(f"{status}  {task.name}")
                item.setData(Qt.ItemDataRole.UserRole, task.id)
                self._task_list.addItem(item)

        # 恢复选中高亮
        self._task_list._sync_task_selection_ui()

    def _on_task_item_clicked(self, task_id: str):
        """任务行被单击"""
        task = next((t for t in self._project.tasks if t.id == task_id), None)
        if task:
            self._selected_task_id = task_id
            self._show_task_editor(task)

    def _on_group_item_clicked(self, gid: str):
        """分组标题单击 → 切换折叠"""
        if gid in self._collapsed_groups:
            self._collapsed_groups.discard(gid)
        else:
            self._collapsed_groups.add(gid)
        self._refresh_task_list()

    def _on_task_reordered(self, dragged_task_id: str, target_task_id: str, insert_after: bool):
        """任务拖动重排"""
        dragged = next((t for t in self._project.tasks if t.id == dragged_task_id), None)
        target = next((t for t in self._project.tasks if t.id == target_task_id), None)
        if not dragged or not target:
            return
        self._project.tasks.remove(dragged)
        target_idx = self._project.tasks.index(target)
        if insert_after:
            target_idx += 1
        self._project.tasks.insert(target_idx, dragged)
        self._refresh_task_list()
        self._mark_modified()
        self._push_history(f"重排任务: {dragged.name}")

    def _quick_add_group(self):
        """快速新建分组（右键菜单）"""
        name, ok = QInputDialog.getText(self, "新建分组", "分组名称：")
        if ok and name.strip():
            import uuid as _uuid
            gid = str(_uuid.uuid4())[:8]
            self._project.task_groups.append({"id": gid, "name": name.strip()})
            self._refresh_task_list()
            self._mark_modified()
            self._push_history(f"新建分组: {name.strip()}")

    def _on_task_selected(self, row: int):
        if row < 0:
            return
        item = self._task_list.item(row)
        if not item:
            return
        task_id = item.data(Qt.ItemDataRole.UserRole)
        item_kind = item.data(Qt.ItemDataRole.UserRole + 2)
        if task_id is None:
            # 点击了分组标题行 → 切换折叠
            if item_kind == "group_header":
                gid = item.data(Qt.ItemDataRole.UserRole + 1)
                if gid:
                    if gid in self._collapsed_groups:
                        self._collapsed_groups.discard(gid)
                    else:
                        self._collapsed_groups.add(gid)
                    self._refresh_task_list()
            return
        task = next((t for t in self._project.tasks if t.id == task_id), None)
        if task:
            self._selected_task_id = task_id   # 记录当前选中任务
            self._show_task_editor(task)

    def _show_task_editor(self, task: Task):
        try:
            if task.id not in self._task_editors:
                editor = TaskEditorPage(task)
                editor.changed.connect(lambda: self._on_task_changed(task.id))
                editor.run_task.connect(self._run_task)
                editor.stop_task.connect(self._stop_task)
                editor.run_single.connect(self._run_single_block)
                editor.run_from.connect(self._run_from_block)
                self._task_editors[task.id] = editor
                self._stack.addWidget(editor)

            # 把所有任务注入到 block_list（供 task_picker 控件使用）
            editor = self._task_editors[task.id]
            if hasattr(editor, '_block_list'):
                editor._block_list.set_all_tasks(self._project.tasks)

            self._stack.setCurrentWidget(self._task_editors[task.id])
        except Exception as _e:
            import traceback
            from PyQt6.QtWidgets import QMessageBox as _MB
            _MB.warning(
                self,
                "加载任务失败",
                f"任务「{task.name}」加载时出错，请检查项目文件是否损坏。\n\n"
                f"错误信息：{_e}\n\n"
                f"{traceback.format_exc()}"
            )

        self._task_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._task_list.customContextMenuRequested.connect(self._task_list_context_menu)
        # 允许任务拖动重排
        self._task_list.setAcceptDrops(True)

    def _task_list_context_menu(self, pos):
        item = self._task_list.itemAt(pos)
        menu = QMenu(self)

        if not item:
            # 右键空白区域：提供新建任务 + 新建分组
            menu.addAction("＋ 新建任务", self._add_task)
            menu.addAction("📁 新建分组", self._quick_add_group)
            menu.exec(self._task_list.mapToGlobal(pos))
            return

        task_id = item.data(Qt.ItemDataRole.UserRole)
        if task_id is None:
            # 右键分组标题
            gid = item.data(Qt.ItemDataRole.UserRole + 1)
            if not gid:
                return
            menu.addAction("✏ 重命名分组", lambda: self._rename_group(gid))
            menu.addAction("🗑 删除分组（任务保留）", lambda: self._delete_group(gid))
            menu.addSeparator()
            menu.addAction("📁 新建分组", self._quick_add_group)
            menu.exec(self._task_list.mapToGlobal(pos))
            return

        task = next((t for t in self._project.tasks if t.id == task_id), None)
        if not task:
            return
        menu = QMenu(self)
        menu.addAction("重命名", lambda: self._rename_task(task))
        menu.addAction("复制任务", lambda: self._duplicate_task(task))

        # 移入分组子菜单
        if self._project.task_groups:
            move_sub = menu.addMenu("移入分组")
            move_sub.addAction("（不分组）", lambda: self._move_task_to_group(task, ""))
            for grp in self._project.task_groups:
                grp_id   = grp["id"]
                grp_name = grp["name"]
                move_sub.addAction(grp_name, lambda _=None, gid=grp_id: self._move_task_to_group(task, gid))

        menu.addSeparator()
        run_action = menu.addAction("> 立即运行", lambda: self._run_task(task.id))
        if task.id in self._runners:
            run_action.setEnabled(False)
            menu.addAction("停止运行", lambda: self._stop_task(task.id))
        menu.addSeparator()
        menu.addAction("删除任务", lambda: self._delete_task(task))
        menu.exec(self._task_list.mapToGlobal(pos))

    def _rename_task(self, task: Task):
        name, ok = QInputDialog.getText(self, "重命名任务", "新名称：", text=task.name)
        if ok and name.strip():
            task.name = name.strip()
            self._refresh_task_list()
            if task.id in self._task_editors:
                self._task_editors[task.id]._name_edit.setText(task.name)
            self._mark_modified()
            self._push_history(f"重命名任务: {task.name}")

    def _duplicate_task(self, task: Task):
        import uuid as _uuid
        d = task.to_dict()
        d["id"]   = str(_uuid.uuid4())[:8]
        d["name"] = task.name + "_副本"
        new_task = Task.from_dict(d)
        self._project.tasks.append(new_task)
        self._refresh_task_list()
        self._refresh_tray_menu()
        if hasattr(self, '_settings_page'):
            self._settings_page.refresh_tasks(self._project.tasks)
        self._mark_modified()
        self._push_history(f"复制任务: {new_task.name}")

    def _delete_task(self, task: Task):
        reply = QMessageBox.question(
            self, "删除任务", f"确认删除任务「{task.name}」？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._stop_task(task.id)
        self._project.tasks = [t for t in self._project.tasks if t.id != task.id]
        if task.id in self._task_editors:
            widget = self._task_editors.pop(task.id)
            self._stack.removeWidget(widget)
            widget.deleteLater()
        self._refresh_task_list()
        self._refresh_tray_menu()
        # 同步设置页任务列表（如已打开）
        if hasattr(self, '_settings_page'):
            self._settings_page.refresh_tasks(self._project.tasks)
        self._mark_modified()
        self._push_history(f"删除任务: {task.name}")

    def _on_task_changed(self, task_id: str):
        self._refresh_task_list()
        self._refresh_tray_menu()
        # 同步 all_tasks 给所有编辑器的 BlockListWidget
        for editor in self._task_editors.values():
            if hasattr(editor, '_block_list'):
                editor._block_list.set_all_tasks(self._project.tasks)
        self._mark_modified()
        self._push_history(f"编辑任务")
        self._trigger_reload_timer.start()

    # ─────────────────── 任务分组 ───────────────────

    def _show_group_manager(self):
        """弹出任务分组管理对话框"""
        dlg = QDialog(self)
        dlg.setWindowTitle("任务分组管理")
        dlg.setMinimumSize(360, 320)
        dlg.setModal(True)
        layout = QVBoxLayout(dlg)

        hint = QLabel("在侧边栏任务列表上右键可以将任务移入分组")
        hint.setObjectName("hint")
        layout.addWidget(hint)

        from PyQt6.QtWidgets import QListWidget, QListWidgetItem
        lst = QListWidget()
        def _refresh_list():
            lst.clear()
            for grp in self._project.task_groups:
                cnt = sum(1 for t in self._project.tasks if t.group_id == grp["id"])
                item = QListWidgetItem(f"{grp['name']}  ({cnt} 个任务)")
                item.setData(Qt.ItemDataRole.UserRole, grp["id"])
                lst.addItem(item)
        _refresh_list()
        layout.addWidget(lst)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("+ 新建分组")
        btn_add.setObjectName("btn_primary")
        btn_rename = QPushButton("重命名")
        btn_rename.setObjectName("btn_flat")
        btn_delete = QPushButton("删除")
        btn_delete.setObjectName("btn_danger")
        btn_close  = QPushButton("关闭")
        btn_row.addWidget(btn_add); btn_row.addWidget(btn_rename)
        btn_row.addWidget(btn_delete); btn_row.addStretch(); btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        def _add():
            name, ok = QInputDialog.getText(dlg, "新建分组", "分组名称：")
            if not ok or not name.strip():
                return
            import uuid as _uuid
            grp = {"id": str(_uuid.uuid4())[:8], "name": name.strip()}
            self._project.task_groups.append(grp)
            _refresh_list()
            self._refresh_task_list()
            self._mark_modified()
            self._push_history(f"新建分组: {name.strip()}")

        def _rename():
            item = lst.currentItem()
            if not item:
                return
            gid = item.data(Qt.ItemDataRole.UserRole)
            grp = next((g for g in self._project.task_groups if g["id"] == gid), None)
            if not grp:
                return
            name, ok = QInputDialog.getText(dlg, "重命名分组", "新名称：", text=grp["name"])
            if ok and name.strip():
                grp["name"] = name.strip()
                _refresh_list()
                self._refresh_task_list()
                self._mark_modified()
                self._push_history(f"重命名分组: {name.strip()}")

        def _delete():
            item = lst.currentItem()
            if not item:
                return
            gid = item.data(Qt.ItemDataRole.UserRole)
            grp = next((g for g in self._project.task_groups if g["id"] == gid), None)
            if not grp:
                return
            reply = QMessageBox.question(dlg, "删除分组",
                f"删除分组「{grp['name']}」？该分组内的任务将变为未分组，不会删除。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return
            for t in self._project.tasks:
                if t.group_id == gid:
                    t.group_id = ""
            self._project.task_groups = [g for g in self._project.task_groups if g["id"] != gid]
            _refresh_list()
            self._refresh_task_list()
            self._mark_modified()
            self._push_history(f"删除分组: {grp['name']}")

        btn_add.clicked.connect(_add)
        btn_rename.clicked.connect(_rename)
        btn_delete.clicked.connect(_delete)
        btn_close.clicked.connect(dlg.accept)
        dlg.exec()

    def _rename_group(self, gid: str):
        grp = next((g for g in self._project.task_groups if g["id"] == gid), None)
        if not grp:
            return
        name, ok = QInputDialog.getText(self, "重命名分组", "新名称：", text=grp["name"])
        if ok and name.strip():
            grp["name"] = name.strip()
            self._refresh_task_list()
            self._mark_modified()

    def _delete_group(self, gid: str):
        grp = next((g for g in self._project.task_groups if g["id"] == gid), None)
        if not grp:
            return
        for t in self._project.tasks:
            if t.group_id == gid:
                t.group_id = ""
        self._project.task_groups = [g for g in self._project.task_groups if g["id"] != gid]
        self._refresh_task_list()
        self._mark_modified()

    def _move_task_to_group(self, task, gid: str):
        task.group_id = gid
        self._refresh_task_list()
        self._mark_modified()
        self._push_history(f"移动任务到分组")

    def _mark_modified(self):
        self._modified = True
        self._modified_label.setText("  * 未保存  ")


    # ─────────────────── 设置 ───────────────────

    def _show_settings(self):
        if not hasattr(self, "_settings_page"):
            self._settings_page = SettingsPage(self._project.config, self._project.tasks)
            self._settings_page.config_changed.connect(self._on_config_changed)
            self._settings_page.back_requested.connect(self._back_from_settings)
            self._stack.addWidget(self._settings_page)
        else:
            # 每次打开都刷新任务列表（处理任务增删的情况）
            self._settings_page.refresh_tasks(self._project.tasks)
        self._stack.setCurrentWidget(self._settings_page)
        self._task_list.clearSelection()

    def _back_from_settings(self):
        row = self._task_list.currentRow()
        if 0 <= row < len(self._project.tasks):
            self._show_task_editor(self._project.tasks[row])
        elif self._project.tasks:
            self._task_list.setCurrentRow(0)
        else:
            if self._stack.count() > 0:
                self._stack.setCurrentIndex(0)

    def _on_config_changed(self, config: AppConfig):
        self._project.config = config
        self._apply_theme(config.theme)
        self._reset_auto_save_timer()
        self._save_project(silent=True)
        # 同步坐标选点快捷键到全局类属性
        CoordPickerEdit.pick_hotkey       = getattr(config, "coord_pick_hotkey", "F9")
        MacroRecorderWidget.stop_hotkey   = getattr(config, "macro_stop_hotkey", "F10")
        # 同步强制终止热键（重启后台线程）
        self._restart_force_stop_hotkey()
        # 同步 reopen_last + 语言（语言需持久化到 app_config 以便下次启动时提前应用）
        app_cfg = _load_app_config()
        app_cfg["reopen_last"] = config.reopen_last_project
        app_cfg["language"] = getattr(config, "language", "zh_CN")
        if self._project_path:
            app_cfg["last_project"] = self._project_path
        _save_app_config(app_cfg)

    # ─────────────────── 任务运行 ───────────────────

    def _run_task(self, task_id: str, trigger_vars: dict = None):
        task = next((t for t in self._project.tasks if t.id == task_id), None)
        if not task:
            return
        if task_id in self._runners and self._runners[task_id].is_alive():
            return

        # 合并全局变量 + 触发器变量（如剪贴板内容）
        # 全局变量作为基础，触发器变量（如剪贴板内容）覆盖同名全局变量
        init_vars: dict = dict(self._project.global_variables)
        if trigger_vars:
            init_vars.update(trigger_vars)

        runner = TaskRunner(
            task, self._project.config,
            global_variables=init_vars,
            on_log=lambda level, msg: self._bridge.log_signal.emit(level, msg),
            on_finished=lambda tid, ok: self._bridge.task_finished.emit(tid, ok),
            # 任务联动回调
            run_task_fn=lambda tid: self._bridge.trigger_fired.emit(f"__run__{tid}"),
            stop_task_fn=lambda tid: self._bridge.trigger_fired.emit(f"__stop__{tid}"),
            is_task_running_fn=lambda tid: tid in self._runners and self._runners[tid].is_alive(),
            all_tasks_fn=lambda: list(self._project.tasks),
        )
        self._runners[task_id] = runner
        runner.start()

        if task_id in self._task_editors:
            self._task_editors[task_id].set_running(True)
        self._status_label.setText(f"正在运行: {task.name}")

        # 手动运行时，根据设置决定是否最小化主窗口
        if getattr(self._project.config, 'minimize_on_run', False) and not trigger_vars:
            QTimer.singleShot(200, self.showMinimized)

    def _stop_task(self, task_id: str):
        if task_id in self._runners:
            self._runners[task_id].stop()
        if task_id in self._task_editors:
            self._task_editors[task_id].set_running(False)

    def _run_single_block(self, task_id: str, block):
        """运行单个功能块（创建仅含该块的临时任务）"""
        import copy as _copy
        task = next((t for t in self._project.tasks if t.id == task_id), None)
        if not task:
            return
        # 先保存当前编辑器状态
        if task_id in self._task_editors:
            self._task_editors[task_id].save_to_task()

        # 构建临时任务（仅含目标块）
        tmp_id = f"__single__{task_id}"
        tmp_task = _copy.deepcopy(task)
        tmp_task.id    = tmp_id
        tmp_task.name  = f"[单块] {task.name}"
        tmp_task.blocks = [_copy.deepcopy(block)]

        if tmp_id in self._runners and self._runners[tmp_id].is_alive():
            return

        init_vars = dict(self._project.global_variables)
        runner = TaskRunner(
            tmp_task, self._project.config,
            global_variables=init_vars,
            on_log=lambda level, msg: self._bridge.log_signal.emit(level, msg),
            on_finished=lambda tid, ok: self._bridge.task_finished.emit(tid, ok),
            run_task_fn=lambda tid: self._bridge.trigger_fired.emit(f"__run__{tid}"),
            stop_task_fn=lambda tid: self._bridge.trigger_fired.emit(f"__stop__{tid}"),
            is_task_running_fn=lambda tid: tid in self._runners and self._runners[tid].is_alive(),
            all_tasks_fn=lambda: list(self._project.tasks),
        )
        self._runners[tmp_id] = runner
        runner.start()
        self._status_label.setText(f"单块运行: {task.name} → {block.block_type}")

    def _run_from_block(self, task_id: str, start_idx: int):
        """从指定索引开始运行任务的剩余块"""
        import copy as _copy
        task = next((t for t in self._project.tasks if t.id == task_id), None)
        if not task:
            return
        # 先保存当前编辑器状态
        if task_id in self._task_editors:
            self._task_editors[task_id].save_to_task()

        # 构建临时任务（从 start_idx 开始的块）
        tmp_id = f"__from__{task_id}"
        tmp_task = _copy.deepcopy(task)
        tmp_task.id    = tmp_id
        tmp_task.name  = f"[从第{start_idx+1}块] {task.name}"
        tmp_task.blocks = [_copy.deepcopy(b) for b in task.blocks[start_idx:]]

        if tmp_id in self._runners and self._runners[tmp_id].is_alive():
            return

        init_vars = dict(self._project.global_variables)
        runner = TaskRunner(
            tmp_task, self._project.config,
            global_variables=init_vars,
            on_log=lambda level, msg: self._bridge.log_signal.emit(level, msg),
            on_finished=lambda tid, ok: self._bridge.task_finished.emit(tid, ok),
            run_task_fn=lambda tid: self._bridge.trigger_fired.emit(f"__run__{tid}"),
            stop_task_fn=lambda tid: self._bridge.trigger_fired.emit(f"__stop__{tid}"),
            is_task_running_fn=lambda tid: tid in self._runners and self._runners[tid].is_alive(),
            all_tasks_fn=lambda: list(self._project.tasks),
        )
        self._runners[tmp_id] = runner
        runner.start()
        self._status_label.setText(f"从第{start_idx+1}块运行: {task.name}")

    def _on_task_finished(self, task_id: str, success: bool):
        self._runners.pop(task_id, None)
        task = next((t for t in self._project.tasks if t.id == task_id), None)
        if task_id in self._task_editors:
            self._task_editors[task_id].set_running(False)
        name = task.name if task else task_id
        if success:
            self._status_label.setText(f"[OK] {name} 已完成")
            show_toast(self, f"✅ {name} 已完成", color="#A6E3A1", duration_ms=2000)
        else:
            self._status_label.setText(f"[STOP] {name} 已停止")
            show_toast(self, f"🛑 {name} 已停止", color="#F38BA8", duration_ms=2000)

    # ─────────────────── 触发器 ───────────────────

    def _start_trigger_monitor(self):
        if self._trigger_monitor:
            self._trigger_monitor.stop()

        self._trigger_monitor = TriggerMonitor(
            config=self._project.config,
            on_trigger=self._on_trigger_fired_raw
        )
        self._trigger_monitor.set_tasks(self._project.tasks)
        self._trigger_monitor.start()

        cfg = self._project.config
        if cfg.auto_start_enabled and cfg.auto_start_task_id:
            QTimer.singleShot(500, lambda: self._run_task(cfg.auto_start_task_id))

        for task in self._project.tasks:
            if task.enabled:
                for trig in task.triggers:
                    if trig.trigger_type == "startup" and trig.enabled:
                        QTimer.singleShot(600, lambda tid=task.id: self._run_task(tid))
                        break

    def _on_trigger_fired_raw(self, task_id: str):
        self._bridge.trigger_fired.emit(task_id)

    def _on_trigger_fired(self, task_id: str):
        # 任务联动特殊信号：__run__<id> 和 __stop__<id>
        if task_id.startswith("__run__"):
            real_id = task_id[7:]
            self._run_task(real_id)
        elif task_id.startswith("__stop__"):
            real_id = task_id[8:]
            self._stop_task(real_id)
        else:
            # 从触发器监控获取本次触发携带的变量（如剪贴板内容）
            tvars = {}
            if self._trigger_monitor is not None:
                tvars = self._trigger_monitor.get_trigger_vars(task_id)
            self._run_task(task_id, trigger_vars=tvars)

    # ─────────────────── 窗口关闭 ───────────────────

    def closeEvent(self, event: QCloseEvent):
        if self._quitting:
            # 正在执行退出流程，直接接受关闭，不弹通知
            event.accept()
            return
        if self._project.config.minimize_to_tray:
            event.ignore()
            self.hide()
            self._tray.showMessage(
                "AutoFlow", "程序已最小化到托盘，触发器继续运行中。",
                QSystemTrayIcon.MessageIcon.Information, 2000
            )
        else:
            if self._modified:
                reply = QMessageBox.question(
                    self, "退出", "有未保存的更改，退出前是否保存？",
                    QMessageBox.StandardButton.Save |
                    QMessageBox.StandardButton.Discard |
                    QMessageBox.StandardButton.Cancel
                )
                if reply == QMessageBox.StandardButton.Save:
                    self._save_project()
                elif reply == QMessageBox.StandardButton.Cancel:
                    event.ignore()
                    return
            self._quit_app()
            event.accept()

    # ─────────────────── 强制终止热键 ───────────────────

    def _restart_force_stop_hotkey(self):
        """停掉旧线程，用当前配置的快捷键重新启动监听线程。"""
        self._stop_force_stop_hotkey()
        hk = getattr(self._project.config, "force_stop_hotkey", "ctrl+alt+s").strip()
        if not hk:
            return
        self._force_stop_stop_event = threading.Event()
        self._force_stop_thread = threading.Thread(
            target=self._force_stop_hotkey_loop,
            args=(hk, self._force_stop_stop_event),
            daemon=True,
            name="force-stop-hotkey",
        )
        self._force_stop_thread.start()
        logger.info(f"强制终止热键已注册: {hk}")

    def _stop_force_stop_hotkey(self):
        """通知后台线程退出。"""
        import ctypes
        self._force_stop_stop_event.set()
        if self._force_stop_thread and self._force_stop_thread.is_alive():
            tid = self._force_stop_thread.ident
            if tid:
                ctypes.windll.user32.PostThreadMessageW(tid, 0x0012, 0, 0)  # WM_QUIT

    def _force_stop_hotkey_loop(self, hk_str: str, stop_event: threading.Event):
        """
        后台线程：RegisterHotKey + GetMessage 监听强制终止热键。
        检测到热键后通过 QTimer.singleShot 在主线程执行 _force_stop_all_tasks。
        RegisterHotKey 的 WM_HOTKEY 只投递到注册它的线程消息队列，
        必须在同一线程 GetMessage 才能收到。
        """
        import ctypes, ctypes.wintypes

        WM_HOTKEY = 0x0312
        HOTKEY_ID = 0x7FFD   # 与 CoordOverlay 的 0x7FFF/0x7FFE 不重叠

        MOD_ALT   = 0x0001
        MOD_CTRL  = 0x0002
        MOD_SHIFT = 0x0004

        def parse_vk(s: str):
            parts = [p.strip().upper() for p in s.replace("+", " ").split()]
            mods, vk = 0, 0
            for part in parts:
                if part in ("CTRL", "CONTROL"):  mods |= MOD_CTRL
                elif part == "ALT":              mods |= MOD_ALT
                elif part == "SHIFT":            mods |= MOD_SHIFT
                elif part.startswith("F") and part[1:].isdigit():
                    fnum = int(part[1:])
                    if 1 <= fnum <= 24:
                        vk = 0x6F + fnum
                elif len(part) == 1:
                    vk = ctypes.windll.user32.VkKeyScanW(ord(part)) & 0xFF
            return mods, vk

        mods, vk = parse_vk(hk_str)
        if not vk:
            logger.warning(f"强制终止热键解析失败: {hk_str}")
            return

        registered = bool(ctypes.windll.user32.RegisterHotKey(None, HOTKEY_ID, mods, vk))
        if not registered:
            logger.warning(f"强制终止热键注册失败（可能被占用）: {hk_str}")
            return

        msg = ctypes.wintypes.MSG()
        while not stop_event.is_set():
            ret = ctypes.windll.user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret <= 0:
                break
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                QTimer.singleShot(0, self._force_stop_all_tasks)
                # 继续监听，不退出循环（一次按键只触发一次）

        ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID)

    def _force_stop_all_tasks(self):
        """主线程：停止所有正在运行的任务，并在状态栏提示。"""
        running = [tid for tid, r in self._runners.items() if r.is_alive()]
        if not running:
            return
        for tid in running:
            self._stop_task(tid)
        names = []
        for tid in running:
            task = next((t for t in self._project.tasks if t.id == tid), None)
            names.append(task.name if task else tid)
        msg = f"🛑 已强制终止: {', '.join(names)}"
        self._status_label.setText(msg)
        logger.info(msg)

    # ─────────────────── 窗口关闭 ───────────────────

    def _quit_app(self):
        self._quitting = True
        if self._trigger_monitor:
            self._trigger_monitor.stop()
        for runner in self._runners.values():
            runner.stop()
        self._stop_force_stop_hotkey()
        QApplication.quit()

    # ─────────────────── 插件系统 ───────────────────

    def _init_plugin_manager(self):
        """初始化插件管理器（启动后延迟加载）"""
        try:
            from ..plugin_manager import PluginManager
            pm = PluginManager.instance()
            pm.config = self._project.config
            pm.load_all()
            loaded = [m for m in pm.get_all_metas() if m.loaded]
            if loaded:
                logger.info(f"已加载 {len(loaded)} 个插件: "
                            + ", ".join(m.name for m in loaded))
        except Exception as e:
            logger.warning(f"插件系统初始化失败: {e}")

    def _show_plugin_manager(self):
        """显示插件管理器页面"""
        if not hasattr(self, '_plugin_page'):
            self._plugin_page = PluginManagerPage()
            self._plugin_page.back_requested.connect(self._back_from_plugin_manager)
            self._stack.addWidget(self._plugin_page)
        self._stack.setCurrentWidget(self._plugin_page)
        self._task_list.clearSelection()

    def _back_from_plugin_manager(self):
        """从插件页返回"""
        row = self._task_list.currentRow()
        if 0 <= row < len(self._project.tasks):
            self._show_task_editor(self._project.tasks[row])
        elif self._project.tasks:
            self._task_list.setCurrentRow(0)
        else:
            if self._stack.count() > 0:
                self._stack.setCurrentIndex(0)

    # ─────────────────── 静默更新检测 ───────────────────

    def _silent_check_update(self):
        """启动后静默检测更新，有新版本时在状态栏显示小提示"""
        from ..updater import check_update
        from ..version import VERSION

        def _on_result(result: dict):
            self._update_result_sig.emit(result)  # 信号跨线程安全

        check_update(VERSION, callback=_on_result, timeout=6)

    def _show_update_tip(self, result: dict):
        """有新版本时在状态栏显示非侵入性提示（点击可打开 Release 页）"""
        if not result.get("has_update"):
            return
        tag = result.get("latest_tag", "")
        url = result.get("html_url", "")
        if not hasattr(self, "_update_tip_lbl"):
            from PyQt6.QtWidgets import QLabel as _QLabel
            self._update_tip_lbl = _QLabel()
            self._update_tip_lbl.setOpenExternalLinks(True)
            self._update_tip_lbl.setTextFormat(Qt.TextFormat.RichText)
            self._update_tip_lbl.setStyleSheet(
                "color:#4ade80; font-size:11px; padding:0 8px;"
            )
            self.statusBar().addPermanentWidget(self._update_tip_lbl)
        self._update_tip_lbl.setText(
            f'🎉 <a href="{url}" style="color:#4ade80;">发现新版本 {tag}，点此下载</a>'
        )
        self._update_tip_lbl.setVisible(True)

    # ─────────────────────── 远程公告 ───────────────────────

    def _fetch_remote_announcements(self):
        """启动后异步拉取远程公告，有未读公告时弹出提示"""
        from ..updater import fetch_announcements

        def _on_result(announcements: list):
            self._announcements_result_sig.emit(announcements)  # 信号跨线程安全

        fetch_announcements(_on_result, timeout=8)

    def _show_announcements(self, announcements: list):
        """过滤已读公告，有未读时弹出公告对话框"""
        if not announcements:
            return

        read_ids: list = getattr(self._project.config, "read_announcement_ids", [])
        # pinned 公告每次都显示；普通公告只在未读时显示
        pending = [
            ann for ann in announcements
            if ann.get("pinned", False) or ann.get("id", "") not in read_ids
        ]
        if not pending:
            return

        dlg = _AnnouncementDialog(pending, read_ids, self)
        dlg.exec()

        # 将非 pinned 的已展示公告标为已读并持久化
        for ann in pending:
            ann_id = ann.get("id", "")
            if ann_id and not ann.get("pinned", False):
                if ann_id not in read_ids:
                    read_ids.append(ann_id)

        self._project.config.read_announcement_ids = read_ids
        self._save_project(silent=True)











# ─── 远程公告对话框 ───
class _AnnouncementDialog(QDialog):
    """
    远程公告展示对话框。
    支持多条公告翻页；level 颜色区分（info=蓝/warning=橙/important=红）。
    """

    _LEVEL_COLORS = {
        "info":      "#89B4FA",
        "warning":   "#FAB387",
        "important": "#F38BA8",
    }
    _LEVEL_LABELS = {
        "info":      "📢 公告",
        "warning":   "⚠️ 注意",
        "important": "🔔 重要",
    }

    def __init__(self, announcements: list, read_ids: list, parent=None):
        super().__init__(parent)
        self._announcements = announcements
        self._read_ids = read_ids
        self._idx = 0
        self.setWindowTitle("AutoFlow 公告")
        self.setMinimumWidth(480)
        self.setMinimumHeight(300)
        self.setModal(True)
        self._build_ui()
        self._load_page(0)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # 标题行
        title_row = QHBoxLayout()
        self._level_lbl = QLabel()
        self._level_lbl.setStyleSheet("font-size: 14px; font-weight: bold;")
        title_row.addWidget(self._level_lbl)
        title_row.addStretch()
        self._page_lbl = QLabel()
        self._page_lbl.setStyleSheet("font-size: 11px; color: gray;")
        title_row.addWidget(self._page_lbl)
        layout.addLayout(title_row)

        # 主标题
        self._title_lbl = QLabel()
        self._title_lbl.setStyleSheet("font-size: 16px; font-weight: bold;")
        self._title_lbl.setWordWrap(True)
        layout.addWidget(self._title_lbl)

        # 日期
        self._date_lbl = QLabel()
        self._date_lbl.setStyleSheet("font-size: 11px; color: gray;")
        layout.addWidget(self._date_lbl)

        # 正文
        from PyQt6.QtWidgets import QTextEdit
        self._body_edit = QTextEdit()
        self._body_edit.setReadOnly(True)
        self._body_edit.setStyleSheet(
            "QTextEdit { border-radius: 8px; padding: 8px; font-size: 13px; }"
        )
        self._body_edit.setMinimumHeight(120)
        layout.addWidget(self._body_edit)

        # 底部按钮行
        btn_row = QHBoxLayout()

        self._prev_btn = QPushButton("◀ 上一条")
        self._prev_btn.setFixedWidth(90)
        self._prev_btn.clicked.connect(lambda: self._load_page(self._idx - 1))
        btn_row.addWidget(self._prev_btn)

        self._next_btn = QPushButton("下一条 ▶")
        self._next_btn.setFixedWidth(90)
        self._next_btn.clicked.connect(lambda: self._load_page(self._idx + 1))
        btn_row.addWidget(self._next_btn)

        btn_row.addStretch()

        self._detail_btn = QPushButton("🔗 查看详情")
        self._detail_btn.setFixedWidth(100)
        self._detail_btn.setVisible(False)
        self._detail_btn.clicked.connect(self._open_detail)
        btn_row.addWidget(self._detail_btn)

        close_btn = QPushButton("✓ 我知道了")
        close_btn.setFixedWidth(100)
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

    def _load_page(self, idx: int):
        n = len(self._announcements)
        if idx < 0 or idx >= n:
            return
        self._idx = idx
        ann = self._announcements[idx]

        level = ann.get("level", "info")
        color = self._LEVEL_COLORS.get(level, "#89B4FA")
        level_text = self._LEVEL_LABELS.get(level, "📢 公告")

        self._level_lbl.setText(level_text)
        self._level_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {color};"
        )
        self._page_lbl.setText(f"{idx + 1} / {n}")
        self._title_lbl.setText(ann.get("title", "（无标题）"))
        self._title_lbl.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {color};"
        )
        date_str = ann.get("date", "")
        self._date_lbl.setText(f"发布时间：{date_str}" if date_str else "")
        self._date_lbl.setVisible(bool(date_str))
        self._body_edit.setPlainText(ann.get("body", ""))

        url = ann.get("url", "")
        self._detail_btn.setVisible(bool(url))
        self._detail_url = url

        self._prev_btn.setEnabled(idx > 0)
        self._next_btn.setEnabled(idx < n - 1)

    def _open_detail(self):
        import webbrowser
        if getattr(self, "_detail_url", ""):
            webbrowser.open(self._detail_url)


# ─── 日志 Handler ───
class _QtLogHandler(logging.Handler):
    def __init__(self, signal):
        super().__init__()
        self._signal = signal

    def emit(self, record):
        level = record.levelname
        msg   = self.format(record)
        try:
            self._signal.emit(level, msg)
        except Exception:
            pass

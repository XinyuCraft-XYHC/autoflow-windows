"""
约束条件编辑器
可嵌入到 BlockEditDialog / TriggerEditDialog 中，
提供可视化的约束条件列表管理。
"""
import copy
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QComboBox, QLineEdit, QCheckBox,
    QDialog, QFormLayout, QDialogButtonBox, QSizePolicy,
    QFileDialog, QListWidget, QListWidgetItem, QAbstractItemView
)
from typing import List

from ..engine.models import Constraint


# 可选的约束条件类型（与 condition_type 一致）
CONSTRAINT_TYPES = {
    "always_true":       "始终为真（不限制）",
    "process_exists":    "进程存在",
    "window_exists":     "窗口存在（支持*通配符）",
    "file_exists":       "文件/目录存在",
    "variable_equals":   "变量等于",
    "variable_gt":       "变量大于",
    "variable_lt":       "变量小于",
    "variable_contains": "变量包含",
    "clipboard_contains":"剪贴板包含",
    "internet_connected":"已连接互联网",
    "network_connected": "网络已连接",
    "ping_latency_gt":   "Ping延迟大于(ms) [target=主机 value=ms]",
    "ping_latency_lt":   "Ping延迟小于(ms) [target=主机 value=ms]",
    "capslock_on":       "大写锁定已开启",
    "cpu_above":         "CPU占用超过(%) [target=阈值]",
    "memory_above":      "内存占用超过(%) [target=阈值]",
    "battery_below":     "电池低于(%) [target=阈值]",
    "battery_charging":  "正在充电",
    "time_between":      "时间在范围内 [target=HH:MM value=HH:MM]",
    "day_of_week":       "今天是指定星期 [target=1-7,逗号分隔]",
}

# 目标输入框标签（随类型变化）
_TARGET_LABELS = {
    "process_exists":    "进程名",
    "window_exists":     "窗口标题",
    "file_exists":       "路径",
    "variable_equals":   "变量名",
    "variable_gt":       "变量名",
    "variable_lt":       "变量名",
    "variable_contains": "变量名",
    "clipboard_contains":"包含文本",
    "ping_latency_gt":   "主机",
    "ping_latency_lt":   "主机",
    "cpu_above":         "阈值(%)",
    "memory_above":      "阈值(%)",
    "battery_below":     "阈值(%)",
    "time_between":      "开始时间",
    "day_of_week":       "星期(1-7)",
}

_FLAT_BTN_STYLE = """
    QPushButton {
        background: #313244; border: 1px solid #45475A;
        border-radius: 4px; color: #CDD6F4;
        font-size: 11px; padding: 0 7px; min-height: 22px;
    }
    QPushButton:hover { background: #45475A; }
    QPushButton:disabled { color: #585B70; }
"""


# ─── 进程选择列表对话框 ─────────────────────────────────────────────────────

class _ProcessListDialog(QDialog):
    """弹出当前运行中的进程列表，让用户选择一个"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择进程")
        self.setMinimumSize(380, 480)
        self.setModal(True)
        self.selected_name = ""
        self._build_ui()
        self._load()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        hint = QLabel("双击或选中后点确认，填入进程名（含.exe）")
        hint.setStyleSheet("color: #6C7086; font-size: 11px;")
        layout.addWidget(hint)

        self._filter = QLineEdit()
        self._filter.setPlaceholderText("筛选进程名…")
        self._filter.textChanged.connect(self._apply_filter)
        layout.addWidget(self._filter)

        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.itemDoubleClicked.connect(self._accept_item)
        layout.addWidget(self._list)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _load(self):
        try:
            import psutil
            procs = sorted({p.name() for p in psutil.process_iter(['name']) if p.info['name']})
            self._all_items = procs
        except Exception:
            self._all_items = []
        self._apply_filter("")

    def _apply_filter(self, text: str):
        self._list.clear()
        text = text.lower()
        for name in self._all_items:
            if text in name.lower():
                self._list.addItem(name)

    def _accept_item(self, item: QListWidgetItem):
        self.selected_name = item.text()
        self.accept()

    def _on_ok(self):
        cur = self._list.currentItem()
        if cur:
            self.selected_name = cur.text()
        self.accept()


# ─── 约束条件卡片 ─────────────────────────────────────────────────────────

class ConstraintItemWidget(QFrame):
    """单个约束条件卡片（自适应高度，带智能辅助按钮）"""
    delete_requested = pyqtSignal(object)
    changed = pyqtSignal()

    def __init__(self, constraint: Constraint, parent=None):
        super().__init__(parent)
        self.constraint = constraint
        self._pick_countdown = 3
        self._build_ui()

    def _build_ui(self):
        self.setObjectName("constraint_item")
        self.setStyleSheet("""
            #constraint_item {
                background: #1E1E2E;
                border: 1px solid #45475A;
                border-left: 3px solid #89B4FA;
                border-radius: 6px;
                margin: 2px 0;
            }
        """)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 5, 6, 5)
        root.setSpacing(4)

        # ── 顶行：NOT + 类型下拉 + 删除 ──
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        self._negate = QCheckBox("NOT")
        self._negate.setChecked(self.constraint.negate)
        self._negate.setFixedWidth(50)
        self._negate.setStyleSheet("color: #F38BA8; font-size: 11px;")
        self._negate.stateChanged.connect(self._on_changed)
        top_row.addWidget(self._negate)

        self._type_combo = QComboBox()
        self._type_combo.setMinimumWidth(200)
        for key, label in CONSTRAINT_TYPES.items():
            self._type_combo.addItem(label, key)
        # ── 追加插件扩展条件 ──
        try:
            from ..plugin_manager import PluginManager
            for cdef in PluginManager.instance().get_plugin_conditions(scope="constraint"):
                ctype = cdef.get("type", "")
                clabel = cdef.get("label", ctype)
                icon   = cdef.get("icon", "🔌")
                self._type_combo.addItem(f"{icon} {clabel}（插件）", ctype)
        except Exception:
            pass
        # 恢复当前选中
        all_types = [self._type_combo.itemData(i) for i in range(self._type_combo.count())]
        ct_idx = all_types.index(self.constraint.condition_type) \
                 if self.constraint.condition_type in all_types else 0
        self._type_combo.setCurrentIndex(ct_idx)
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        top_row.addWidget(self._type_combo, 1)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(22, 22)
        del_btn.setStyleSheet("""
            QPushButton { background: transparent; border: none;
                border-radius: 4px; color: #585B70; font-size: 12px; }
            QPushButton:hover { background: #45475A; color: #F38BA8; }
        """)
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self))
        top_row.addWidget(del_btn)

        root.addLayout(top_row)

        # ── 底行：目标标签 + 目标输入 + 辅助按钮 + 值输入 ──
        self._input_row = QHBoxLayout()
        self._input_row.setSpacing(4)

        # 目标标签
        self._target_label = QLabel("目标：")
        self._target_label.setFixedWidth(52)
        self._target_label.setStyleSheet("color: #A6ADC8; font-size: 11px;")
        self._target_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._input_row.addWidget(self._target_label)

        # 目标输入框
        self._target = QLineEdit(self.constraint.target)
        self._target.setPlaceholderText("目标（进程名/窗口标题/文件/变量名）")
        self._target.textChanged.connect(self._on_changed)
        self._input_row.addWidget(self._target, 1)

        # 辅助按钮区（动态）
        self._aux_btns: List[QPushButton] = []
        self._aux_container = QHBoxLayout()
        self._aux_container.setSpacing(3)
        self._input_row.addLayout(self._aux_container)

        # 比较值
        self._value_label = QLabel("值：")
        self._value_label.setFixedWidth(26)
        self._value_label.setStyleSheet("color: #A6ADC8; font-size: 11px;")
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._input_row.addWidget(self._value_label)

        self._value = QLineEdit(self.constraint.value)
        self._value.setPlaceholderText("比较值")
        self._value.setFixedWidth(100)
        self._value.textChanged.connect(self._on_changed)
        self._input_row.addWidget(self._value)

        root.addLayout(self._input_row)

        self._update_visibility()

    # ── 辅助按钮管理 ────────────────────────────────────────────────────────

    def _clear_aux_btns(self):
        for btn in self._aux_btns:
            self._aux_container.removeWidget(btn)
            btn.deleteLater()
        self._aux_btns.clear()

    def _add_aux_btn(self, label: str, tooltip: str, callback) -> QPushButton:
        btn = QPushButton(label)
        btn.setStyleSheet(_FLAT_BTN_STYLE)
        btn.setToolTip(tooltip)
        btn.clicked.connect(callback)
        self._aux_container.addWidget(btn)
        self._aux_btns.append(btn)
        return btn

    # ── 类型变化 ────────────────────────────────────────────────────────────

    def _on_type_changed(self):
        self._update_visibility()
        self._on_changed()

    def _update_visibility(self):
        ct = self._type_combo.currentData()
        no_target_types = ("always_true", "internet_connected", "network_connected",
                           "capslock_on", "battery_charging")
        needs_target = ct not in no_target_types
        needs_value  = ct in ("variable_equals", "variable_gt", "variable_lt", "variable_contains",
                               "ping_latency_gt", "ping_latency_lt", "time_between")

        self._target_label.setVisible(needs_target)
        self._target.setVisible(needs_target)
        self._value_label.setVisible(needs_value)
        self._value.setVisible(needs_value)

        # 动态标签
        label = _TARGET_LABELS.get(ct, "目标")
        self._target_label.setText(f"{label}：")

        # 更新 placeholder
        placeholders = {
            "process_exists": "进程名，如 notepad.exe",
            "window_exists": "窗口标题，支持 * 通配符",
            "file_exists": "文件或目录完整路径",
            "variable_equals": "变量名",
            "variable_gt": "变量名",
            "variable_lt": "变量名",
            "variable_contains": "变量名",
            "clipboard_contains": "剪贴板包含的文本",
            "ping_latency_gt": "主机IP/域名",
            "ping_latency_lt": "主机IP/域名",
            "cpu_above": "CPU阈值，如 80",
            "memory_above": "内存阈值，如 90",
            "battery_below": "电量阈值，如 20",
            "time_between": "开始时间，如 09:00",
            "day_of_week": "星期数1-7，如 1,2,3,4,5",
        }
        self._target.setPlaceholderText(placeholders.get(ct, "目标"))
        self._value.setPlaceholderText({
            "variable_equals": "比较值",
            "variable_gt": "比较值",
            "variable_lt": "比较值",
            "variable_contains": "包含文本",
            "ping_latency_gt": "延迟阈值(ms)",
            "ping_latency_lt": "延迟阈值(ms)",
            "time_between": "结束时间，如 18:00",
        }.get(ct, "比较值"))

        # 重建辅助按钮
        self._clear_aux_btns()
        self._rebuild_aux_btns(ct)

    def _rebuild_aux_btns(self, ct: str):
        """根据条件类型添加对应的辅助按钮"""
        if ct == "file_exists":
            self._add_aux_btn("📁 选择", "通过资源管理器选择文件或目录",
                              self._pick_file_or_dir)

        elif ct == "process_exists":
            self._add_aux_btn("🖱 点选", "最小化窗口，3秒后读取前台窗口进程名",
                              self._start_pick_process)
            self._add_aux_btn("📋 进程列表", "从运行中的进程列表中选择",
                              self._show_process_list)

        elif ct == "window_exists":
            self._add_aux_btn("🖱 点选", "最小化窗口，3秒后读取前台窗口标题",
                              self._start_pick_window)

        elif ct in ("ping_latency_gt", "ping_latency_lt"):
            self._add_aux_btn("🌐 本机", "填入 127.0.0.1（本机测试）",
                              lambda: self._target.setText("127.0.0.1"))

        elif ct in ("variable_equals", "variable_gt", "variable_lt", "variable_contains"):
            pass  # 变量名直接输入即可，暂无辅助

        elif ct in ("time_between",):
            pass  # HH:MM 格式直接输入

    # ── 辅助动作：文件/目录选择 ─────────────────────────────────────────────

    def _pick_file_or_dir(self):
        """弹出资源管理器，让用户选择文件或目录"""
        # 先问用户是要选文件还是目录
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background: #1E1E2E; color: #CDD6F4; border: 1px solid #45475A; }
            QMenu::item:selected { background: #313244; }
        """)
        act_file = menu.addAction("📄  选择文件")
        act_dir  = menu.addAction("📂  选择目录")
        btn = self._aux_btns[0] if self._aux_btns else None
        pos = btn.mapToGlobal(btn.rect().bottomLeft()) if btn else self.mapToGlobal(self.rect().center())
        chosen = menu.exec(pos)
        if chosen == act_file:
            path, _ = QFileDialog.getOpenFileName(self, "选择文件", "", "所有文件 (*)")
            if path:
                self._target.setText(path)
        elif chosen == act_dir:
            path = QFileDialog.getExistingDirectory(self, "选择目录", "")
            if path:
                self._target.setText(path)

    # ── 辅助动作：窗口点选 ──────────────────────────────────────────────────

    def _start_pick_window(self):
        """最小化顶层窗口，倒计时3秒后读取前台窗口标题"""
        top = self
        while top.parent():
            top = top.parent()
        if hasattr(top, 'showMinimized'):
            top.showMinimized()

        self._pick_countdown = 3
        pick_btn = self._aux_btns[0] if self._aux_btns else None
        if pick_btn:
            pick_btn.setEnabled(False)
            pick_btn.setText("3s…")
        self._pick_timer = QTimer(self)
        self._pick_timer.timeout.connect(lambda: self._tick_pick_window(pick_btn, top))
        self._pick_timer.start(1000)

    def _tick_pick_window(self, pick_btn, top):
        self._pick_countdown -= 1
        if self._pick_countdown > 0:
            if pick_btn:
                pick_btn.setText(f"{self._pick_countdown}s…")
        else:
            self._pick_timer.stop()
            try:
                import ctypes
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                buf = ctypes.create_unicode_buffer(256)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
                title = buf.value.strip()
                if title:
                    self._target.setText(title)
            except Exception:
                pass
            if pick_btn:
                pick_btn.setEnabled(True)
                pick_btn.setText("🖱 点选")
            if hasattr(top, 'showNormal'):
                top.showNormal()
            if hasattr(top, 'activateWindow'):
                top.activateWindow()

    # ── 辅助动作：进程点选 ──────────────────────────────────────────────────

    def _start_pick_process(self):
        """最小化顶层窗口，倒计时3秒后读取前台窗口进程名"""
        top = self
        while top.parent():
            top = top.parent()
        if hasattr(top, 'showMinimized'):
            top.showMinimized()

        self._pick_countdown = 3
        pick_btn = self._aux_btns[0] if self._aux_btns else None
        if pick_btn:
            pick_btn.setEnabled(False)
            pick_btn.setText("3s…")
        self._pick_timer = QTimer(self)
        self._pick_timer.timeout.connect(lambda: self._tick_pick_process(pick_btn, top))
        self._pick_timer.start(1000)

    def _tick_pick_process(self, pick_btn, top):
        self._pick_countdown -= 1
        if self._pick_countdown > 0:
            if pick_btn:
                pick_btn.setText(f"{self._pick_countdown}s…")
        else:
            self._pick_timer.stop()
            try:
                import ctypes, psutil
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                pid = ctypes.c_ulong()
                ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                proc = psutil.Process(pid.value)
                name = proc.name()
                if name:
                    self._target.setText(name)
            except Exception:
                pass
            if pick_btn:
                pick_btn.setEnabled(True)
                pick_btn.setText("🖱 点选")
            if hasattr(top, 'showNormal'):
                top.showNormal()
            if hasattr(top, 'activateWindow'):
                top.activateWindow()

    # ── 辅助动作：进程列表 ──────────────────────────────────────────────────

    def _show_process_list(self):
        dlg = _ProcessListDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_name:
            self._target.setText(dlg.selected_name)

    # ── 数据同步 ─────────────────────────────────────────────────────────────

    def _on_changed(self):
        self.constraint.condition_type = self._type_combo.currentData()
        self.constraint.target = self._target.text()
        self.constraint.value  = self._value.text()
        self.constraint.negate = self._negate.isChecked()
        self.changed.emit()

    def get_constraint(self) -> Constraint:
        self._on_changed()
        return self.constraint


class ConstraintListWidget(QWidget):
    """
    约束条件列表控件，可嵌入到 BlockEditDialog / TriggerEditDialog。
    提供"添加约束"按钮，以及各条约束的编辑/删除。
    """
    changed = pyqtSignal()

    def __init__(self, constraints: List[Constraint], parent=None):
        super().__init__(parent)
        self._constraints: List[Constraint] = list(constraints)
        self._item_widgets: List[ConstraintItemWidget] = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(4)

        # 标题行
        header = QHBoxLayout()
        header.setSpacing(6)
        title_lbl = QLabel("🔒 约束条件")
        title_lbl.setStyleSheet(
            "color: #89B4FA; font-size: 11px; font-weight: bold; letter-spacing: 1px;"
        )
        header.addWidget(title_lbl)

        hint_lbl = QLabel("（所有条件均满足时才执行，留空=不限制）")
        hint_lbl.setStyleSheet("color: #6C7086; font-size: 10px;")
        header.addWidget(hint_lbl)
        header.addStretch()

        add_btn = QPushButton("＋ 添加约束")
        add_btn.setObjectName("btn_flat")
        add_btn.setFixedHeight(24)
        add_btn.setStyleSheet("""
            QPushButton { background: #313244; border: 1px solid #45475A;
                border-radius: 4px; color: #89B4FA; font-size: 11px; padding: 0 8px; }
            QPushButton:hover { background: #45475A; }
        """)
        add_btn.clicked.connect(self._add_constraint)
        header.addWidget(add_btn)

        layout.addLayout(header)

        # 约束条件列表容器
        self._list_container = QVBoxLayout()
        self._list_container.setSpacing(2)
        layout.addLayout(self._list_container)

        self._refresh()

    def _refresh(self):
        # 清除旧控件：先 hide() 立即隐藏，再 removeWidget + deleteLater
        for w in self._item_widgets:
            w.hide()
            self._list_container.removeWidget(w)
            w.deleteLater()
        self._item_widgets.clear()

        for c in self._constraints:
            item = ConstraintItemWidget(c, self)
            item.delete_requested.connect(self._remove_constraint)
            item.changed.connect(self.changed.emit)
            self._list_container.addWidget(item)
            self._item_widgets.append(item)

        # 强制布局刷新
        self._list_container.invalidate()
        self._list_container.activate()

    def _add_constraint(self):
        c = Constraint(condition_type="always_true")
        self._constraints.append(c)
        self._refresh()
        self.changed.emit()

    def _remove_constraint(self, item: ConstraintItemWidget):
        c = item.constraint
        self._constraints = [x for x in self._constraints if x is not c]
        self._refresh()
        self.changed.emit()

    def get_constraints(self) -> List[Constraint]:
        """返回当前约束列表（已同步到各 Constraint 对象）"""
        for w in self._item_widgets:
            w.get_constraint()
        return self._constraints

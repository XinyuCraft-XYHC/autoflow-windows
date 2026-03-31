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
from ..i18n import tr, add_language_observer, remove_language_observer


# 可选的约束条件类型（与 condition_type 一致）
# key 列表保持不变，label 由 tr() 动态获取
CONSTRAINT_TYPE_KEYS = [
    "always_true",
    "process_exists",
    "window_exists",
    "file_exists",
    "variable_equals",
    "variable_gt",
    "variable_lt",
    "variable_contains",
    "clipboard_contains",
    "internet_connected",
    "network_connected",
    "ping_latency_gt",
    "ping_latency_lt",
    "capslock_on",
    "cpu_above",
    "memory_above",
    "battery_below",
    "battery_charging",
    "time_between",
    "day_of_week",
]

# 保留原始硬编码字典用于向后兼容（其他模块可能 import CONSTRAINT_TYPES）
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
    "ping_latency_gt":   "Ping延迟大于(ms)",
    "ping_latency_lt":   "Ping延迟小于(ms)",
    "capslock_on":       "大写锁定已开启",
    "cpu_above":         "CPU占用超过(%)",
    "memory_above":      "内存占用超过(%)",
    "battery_below":     "电池低于(%)",
    "battery_charging":  "正在充电",
    "time_between":      "时间在范围内",
    "day_of_week":       "今天是指定星期",
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


def _get_constraint_type_label(key: str) -> str:
    """获取约束类型的国际化标签"""
    return tr(f"constraint.type.{key}", default=CONSTRAINT_TYPES.get(key, key))


# ─── 进程选择列表对话框 ─────────────────────────────────────────────────────

class _ProcessListDialog(QDialog):
    """弹出当前运行中的进程列表，让用户选择一个"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("constraint.proc_dlg_title"))
        self.setMinimumSize(380, 480)
        self.setModal(True)
        self.selected_name = ""
        self._build_ui()
        self._load()
        add_language_observer(self._retranslate)

    def _retranslate(self):
        self.setWindowTitle(tr("constraint.proc_dlg_title"))
        hint = self.findChild(QLabel, "proc_dlg_hint")
        if hint:
            hint.setText(tr("constraint.proc_dlg_hint"))
        flt = self.findChild(QLineEdit, "proc_filter")
        if flt:
            flt.setPlaceholderText(tr("constraint.proc_filter_ph"))

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        hint = QLabel(tr("constraint.proc_dlg_hint"))
        hint.setObjectName("proc_dlg_hint")
        hint.setStyleSheet("color: #6C7086; font-size: 11px;")
        layout.addWidget(hint)

        self._filter = QLineEdit()
        self._filter.setObjectName("proc_filter")
        self._filter.setPlaceholderText(tr("constraint.proc_filter_ph"))
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
        add_language_observer(self._retranslate)

    def _retranslate(self):
        """语言切换时重新翻译各控件文本"""
        # 重建 type combo 文本
        ct = self._type_combo.currentData()
        self._type_combo.blockSignals(True)
        self._type_combo.clear()
        for key in CONSTRAINT_TYPE_KEYS:
            self._type_combo.addItem(_get_constraint_type_label(key), key)
        # 追加插件扩展条件
        try:
            from ..plugin_manager import PluginManager
            for cdef in PluginManager.instance().get_plugin_conditions(scope="constraint"):
                ctype = cdef.get("type", "")
                clabel = cdef.get("label", ctype)
                icon   = cdef.get("icon", "🔌")
                self._type_combo.addItem(f"{icon} {clabel}（插件）", ctype)
        except Exception:
            pass
        all_types = [self._type_combo.itemData(i) for i in range(self._type_combo.count())]
        idx = all_types.index(ct) if ct in all_types else 0
        self._type_combo.setCurrentIndex(idx)
        self._type_combo.blockSignals(False)
        # 更新其余静态文本
        self._update_visibility()

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
        for key in CONSTRAINT_TYPE_KEYS:
            self._type_combo.addItem(_get_constraint_type_label(key), key)
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
        self._target_label = QLabel(tr("constraint.target_label"))
        self._target_label.setFixedWidth(52)
        self._target_label.setStyleSheet("color: #A6ADC8; font-size: 11px;")
        self._target_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._input_row.addWidget(self._target_label)

        # 目标输入框
        self._target = QLineEdit(self.constraint.target)
        self._target.setPlaceholderText(tr("constraint.target_ph"))
        self._target.textChanged.connect(self._on_changed)
        self._input_row.addWidget(self._target, 1)

        # 辅助按钮区（动态）
        self._aux_btns: List[QPushButton] = []
        self._aux_container = QHBoxLayout()
        self._aux_container.setSpacing(3)
        self._input_row.addLayout(self._aux_container)

        # 比较值
        self._value_label = QLabel(tr("constraint.value_label"))
        self._value_label.setFixedWidth(26)
        self._value_label.setStyleSheet("color: #A6ADC8; font-size: 11px;")
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._input_row.addWidget(self._value_label)

        self._value = QLineEdit(self.constraint.value)
        self._value.setPlaceholderText(tr("constraint.value_ph"))
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
        label = tr(f"constraint.target.{ct}", default=tr("constraint.ph.default"))
        self._target_label.setText(f"{label}：")

        # 更新 placeholder
        ph_map = {
            "process_exists":    tr("constraint.ph.process_exists"),
            "window_exists":     tr("constraint.ph.window_exists"),
            "file_exists":       tr("constraint.ph.file_exists"),
            "variable_equals":   tr("constraint.ph.variable"),
            "variable_gt":       tr("constraint.ph.variable"),
            "variable_lt":       tr("constraint.ph.variable"),
            "variable_contains": tr("constraint.ph.variable"),
            "clipboard_contains":tr("constraint.ph.clipboard_contains"),
            "ping_latency_gt":   tr("constraint.ph.ping"),
            "ping_latency_lt":   tr("constraint.ph.ping"),
            "cpu_above":         tr("constraint.ph.cpu"),
            "memory_above":      tr("constraint.ph.memory"),
            "battery_below":     tr("constraint.ph.battery"),
            "time_between":      tr("constraint.ph.time_start"),
            "day_of_week":       tr("constraint.ph.day"),
        }
        self._target.setPlaceholderText(ph_map.get(ct, tr("constraint.ph.default")))
        val_ph_map = {
            "variable_equals":   tr("constraint.ph.compare"),
            "variable_gt":       tr("constraint.ph.compare"),
            "variable_lt":       tr("constraint.ph.compare"),
            "variable_contains": tr("constraint.ph.contains_text"),
            "ping_latency_gt":   tr("constraint.ph.ping_ms"),
            "ping_latency_lt":   tr("constraint.ph.ping_ms"),
            "time_between":      tr("constraint.ph.time_end"),
        }
        self._value.setPlaceholderText(val_ph_map.get(ct, tr("constraint.ph.compare")))

        # 重建辅助按钮
        self._clear_aux_btns()
        self._rebuild_aux_btns(ct)

    def _rebuild_aux_btns(self, ct: str):
        """根据条件类型添加对应的辅助按钮"""
        if ct == "file_exists":
            self._add_aux_btn(tr("constraint.aux.pick_file"),
                              tr("constraint.aux.pick_file_tip"),
                              self._pick_file_or_dir)

        elif ct == "process_exists":
            self._add_aux_btn(tr("constraint.aux.pick_proc"),
                              tr("constraint.aux.pick_proc_tip"),
                              self._start_pick_process)
            self._add_aux_btn(tr("constraint.aux.proc_list"),
                              tr("constraint.aux.proc_list_tip"),
                              self._show_process_list)

        elif ct == "window_exists":
            self._add_aux_btn(tr("constraint.aux.pick_win"),
                              tr("constraint.aux.pick_win_tip"),
                              self._start_pick_window)

        elif ct in ("ping_latency_gt", "ping_latency_lt"):
            self._add_aux_btn(tr("constraint.aux.localhost"),
                              "127.0.0.1",
                              lambda: self._target.setText("127.0.0.1"))

        elif ct in ("variable_equals", "variable_gt", "variable_lt", "variable_contains"):
            pass  # 变量名直接输入即可，暂无辅助

        elif ct in ("time_between",):
            pass  # HH:MM 格式直接输入

    # ── 辅助动作：文件/目录选择 ─────────────────────────────────────────────

    def _pick_file_or_dir(self):
        """弹出资源管理器，让用户选择文件或目录"""
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background: #1E1E2E; color: #CDD6F4; border: 1px solid #45475A; }
            QMenu::item:selected { background: #313244; }
        """)
        act_file = menu.addAction(tr("constraint.menu.file"))
        act_dir  = menu.addAction(tr("constraint.menu.dir"))
        btn = self._aux_btns[0] if self._aux_btns else None
        pos = btn.mapToGlobal(btn.rect().bottomLeft()) if btn else self.mapToGlobal(self.rect().center())
        chosen = menu.exec(pos)
        if chosen == act_file:
            path, _ = QFileDialog.getOpenFileName(self, tr("constraint.file_dlg_title"), "", "")
            if path:
                self._target.setText(path)
        elif chosen == act_dir:
            path = QFileDialog.getExistingDirectory(self, tr("constraint.dir_dlg_title"), "")
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
                pick_btn.setText(tr("constraint.aux.pick_win"))
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
                pick_btn.setText(tr("constraint.aux.pick_proc"))
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
        add_language_observer(self._retranslate)

    def _retranslate(self):
        lbl = self.findChild(QLabel, "constraint_title_lbl")
        if lbl:
            lbl.setText(tr("constraint.title"))
        hint = self.findChild(QLabel, "constraint_hint_lbl")
        if hint:
            hint.setText(tr("constraint.hint"))
        btn = self.findChild(QPushButton, "constraint_add_btn")
        if btn:
            btn.setText(tr("constraint.add_btn"))

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(4)

        # 标题行
        header = QHBoxLayout()
        header.setSpacing(6)
        title_lbl = QLabel(tr("constraint.title"))
        title_lbl.setObjectName("constraint_title_lbl")
        title_lbl.setStyleSheet(
            "color: #89B4FA; font-size: 11px; font-weight: bold; letter-spacing: 1px;"
        )
        header.addWidget(title_lbl)

        hint_lbl = QLabel(tr("constraint.hint"))
        hint_lbl.setObjectName("constraint_hint_lbl")
        hint_lbl.setStyleSheet("color: #6C7086; font-size: 10px;")
        header.addWidget(hint_lbl)
        header.addStretch()

        add_btn = QPushButton(tr("constraint.add_btn"))
        add_btn.setObjectName("constraint_add_btn")
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

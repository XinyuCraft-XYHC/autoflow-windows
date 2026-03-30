"""
触发器编辑器面板
"""
import copy
from PyQt6.QtCore import Qt, pyqtSignal, QTime, QMimeData, QByteArray, QTimer
from PyQt6.QtGui import QCursor, QDrag
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QMenu, QDialog,
    QFormLayout, QLineEdit, QComboBox, QCheckBox,
    QDialogButtonBox, QFileDialog,
    QTextEdit, QTimeEdit, QApplication
)
from typing import List

from ..engine.models import Trigger, TRIGGER_TYPES, TRIGGER_PARAMS, Constraint
from .block_editor import HotkeyEdit, is_theme_dark
from ..i18n import tr, add_language_observer, remove_language_observer


class TriggerCard(QFrame):
    edit_requested   = pyqtSignal(object)
    delete_requested = pyqtSignal(object)
    copy_requested   = pyqtSignal(object)   # 复制
    select_toggled   = pyqtSignal(object, bool)  # 多选切换
    move_up_requested   = pyqtSignal(object)
    move_down_requested = pyqtSignal(object)
    # 单击选中信号 (card, shift_held)
    card_clicked        = pyqtSignal(object, bool)
    # 双击编辑信号
    card_double_clicked = pyqtSignal(object)

    def __init__(self, trigger: Trigger, parent=None):
        super().__init__(parent)
        self.trigger = trigger
        self._selected = False
        self._select_cb: QCheckBox = None  # 多选复选框
        self._drag_start_pos = None
        self._dragged = False
        self._pending_click_shift = False
        self._build_ui()
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def set_selected(self, selected: bool):
        self._selected = selected
        if self._select_cb:
            self._select_cb.setChecked(selected)
        self._apply_selection_style()

    def set_multiselect_visible(self, visible: bool):
        if self._select_cb:
            self._select_cb.setVisible(visible)

    def _apply_selection_style(self):
        dark = is_theme_dark()
        if self._selected:
            if dark:
                self.setStyleSheet("""
                    #trigger_card {
                        background: #1e3a5f;
                        border: 2px solid #89B4FA;
                        border-left: 4px solid #89B4FA;
                        border-radius: 8px;
                        margin: 2px 2px;
                    }
                """)
            else:
                self.setStyleSheet("""
                    #trigger_card {
                        background: #dbeafe;
                        border: 2px solid #3B82F6;
                        border-left: 4px solid #3B82F6;
                        border-radius: 8px;
                        margin: 2px 2px;
                    }
                """)
        else:
            if hasattr(self, '_base_stylesheet'):
                self.setStyleSheet(self._base_stylesheet)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
            self._pending_click_shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self._dragged = False
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = None
            self._dragged = True  # 阻止 release 再发 click
            self.card_double_clicked.emit(self)
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event):
        if (event.buttons() == Qt.MouseButton.LeftButton
                and self._drag_start_pos is not None):
            dist = (event.pos() - self._drag_start_pos).manhattanLength()
            if dist > QApplication.startDragDistance():
                self._dragged = True
                drag = QDrag(self)
                mime = QMimeData()
                mime.setData("application/x-trigger-id",
                             QByteArray(self.trigger.id.encode()))
                drag.setMimeData(mime)
                drag.exec(Qt.DropAction.MoveAction)
                self._drag_start_pos = None
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton
                and not self._dragged
                and self._drag_start_pos is not None):
            self.card_clicked.emit(self, self._pending_click_shift)
        self._drag_start_pos = None
        self._dragged = False
        super().mouseReleaseEvent(event)

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        dark = is_theme_dark()
        menu.setStyleSheet(f"""
            QMenu {{background: {'#2A2A3E' if dark else '#FFFFFF'};
                    color: {'#CDD6F4' if dark else '#212121'};
                    border: 1px solid {'#45475A' if dark else '#D0D0D0'};
                    border-radius: 6px; padding: 4px;}}
            QMenu::item {{padding: 6px 16px; border-radius: 4px;}}
            QMenu::item:selected {{background: {'#45475A' if dark else '#E0E0E0'};}}
        """)
        act_edit   = menu.addAction("✏  编辑触发器")
        act_copy   = menu.addAction("⎘  复制触发器")
        menu.addSeparator()
        act_up     = menu.addAction("↑  上移")
        act_down   = menu.addAction("↓  下移")
        menu.addSeparator()
        act_delete = menu.addAction("🗑  删除触发器")
        act_delete.setProperty("danger", True)

        action = menu.exec(self.mapToGlobal(pos))
        if action == act_edit:
            self.edit_requested.emit(self)
        elif action == act_copy:
            self.copy_requested.emit(self)
        elif action == act_up:
            self.move_up_requested.emit(self)
        elif action == act_down:
            self.move_down_requested.emit(self)
        elif action == act_delete:
            self.delete_requested.emit(self)

    def refresh_theme(self):
        """主题切换后重建 UI（重新计算背景色）"""
        old_layout = self.layout()
        if old_layout:
            while old_layout.count():
                item = old_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            import sip
            try:
                sip.delete(old_layout)
            except Exception:
                pass
        self._select_cb = None
        self._build_ui()

    def _build_ui(self):
        info  = TRIGGER_TYPES.get(self.trigger.trigger_type, {})
        color = info.get("color", "#888")
        icon  = info.get("icon", "🔔")
        label = info.get("label", self.trigger.trigger_type)

        # 根据全局主题状态选择颜色
        dark = is_theme_dark()
        if dark:
            card_bg       = "#2A2A3E"
            card_bg_hover = "#2E2E42"
            card_border   = "#45475A"
            summary_color = "#6C7086"
            dis_color     = "#585B70"
            btn_fg        = "#585B70"
            btn_hover_bg  = "#45475A"
            btn_hover_fg  = "#CDD6F4"
        else:
            card_bg       = "#F5F5F5"
            card_bg_hover = "#EAEAF5"
            card_border   = "#D0D0D0"
            summary_color = "#757575"
            dis_color     = "#BDBDBD"
            btn_fg        = "#9E9E9E"
            btn_hover_bg  = "#E0E0E0"
            btn_hover_fg  = "#212121"

        self.setObjectName("trigger_card")
        self.setStyleSheet(f"""
            #trigger_card {{
                background: {card_bg};
                border: 1px solid {card_border};
                border-left: 4px solid {color};
                border-radius: 8px;
                margin: 2px 2px;
            }}
            #trigger_card:hover {{
                border-color: {color};
                background: {card_bg_hover};
            }}
        """)
        self.setFixedHeight(52)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 8, 6)
        layout.setSpacing(8)

        # 多选复选框（默认隐藏）
        self._select_cb = QCheckBox()
        self._select_cb.setFixedWidth(18)
        self._select_cb.setChecked(self._selected)
        self._select_cb.setVisible(False)
        self._select_cb.toggled.connect(lambda checked: self.select_toggled.emit(self, checked))
        layout.addWidget(self._select_cb)

        icon_lbl = QLabel(icon)
        icon_lbl.setFixedWidth(22)
        icon_lbl.setStyleSheet("font-size: 16px;")
        layout.addWidget(icon_lbl)

        content = QVBoxLayout()
        content.setSpacing(1)

        title_row = QHBoxLayout()
        name_lbl = QLabel(label)
        name_lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 12px;")
        title_row.addWidget(name_lbl)

        if not self.trigger.enabled:
            dis_lbl = QLabel(tr("trigger.disabled"))
            dis_lbl.setStyleSheet(f"color: {dis_color}; font-size: 11px;")
            title_row.addWidget(dis_lbl)
        title_row.addStretch()
        content.addLayout(title_row)

        summary = self._get_summary()
        if summary:
            sum_lbl = QLabel(summary)
            sum_lbl.setStyleSheet(f"color: {summary_color}; font-size: 11px;")
            content.addWidget(sum_lbl)

        layout.addLayout(content)
        layout.addStretch()

        btn_style = f"""
            QPushButton {{ background: transparent; border: none; border-radius: 4px;
                padding: 2px 4px; color: {btn_fg}; font-size: 14px; }}
            QPushButton:hover {{ background: {btn_hover_bg}; color: {btn_hover_fg}; }}
        """
        # 复制按钮
        btn_copy = QPushButton("⎘")
        btn_copy.setFixedSize(24, 24)
        btn_copy.setToolTip(tr("trigger.copy_tip"))
        btn_copy.setStyleSheet(btn_style + "QPushButton:hover { color: #89DCEB; }")
        btn_copy.clicked.connect(lambda _, s=self.copy_requested: s.emit(self))
        layout.addWidget(btn_copy)

        for text, sig in [("✏", self.edit_requested), ("🗑", self.delete_requested)]:
            btn = QPushButton(text)
            btn.setFixedSize(26, 26)
            btn.setStyleSheet(btn_style)
            btn.clicked.connect(lambda _, s=sig: s.emit(self))
            layout.addWidget(btn)

        # 保存基础样式，用于取消选中时恢复
        self._base_stylesheet = self.styleSheet()

    def _get_summary(self) -> str:
        p  = self.trigger.params
        tt = self.trigger.trigger_type
        if tt == "schedule":
            st = p.get("schedule_type", "interval")
            if st == "interval":
                return f"每 {p.get('interval_sec','?')} 秒"
            elif st == "daily":
                return f"每天 {p.get('time_of_day','?')}"
            elif st == "weekly":
                return f"每周{p.get('weekday','?')} {p.get('time_of_day','?')}"
            elif st == "once":
                return f"一次性: {p.get('once_datetime','?')}"
        elif tt == "hotkey":
            return f"快捷键: {p.get('hotkey', '')}"
        elif tt == "mouse_click":
            btn = p.get("button", "middle")
            mod = p.get("modifier", "")
            return f"{mod}+{btn}点击" if mod else f"{btn}键点击"
        elif tt in ("process_start", "process_stop"):
            return p.get("name", "")
        elif tt in ("window_appear", "window_close"):
            return p.get("title", "")
        elif tt in ("file_changed", "file_created", "file_deleted"):
            return p.get("path", "")
        elif tt == "email_received":
            parts = []
            if p.get("sender"):  parts.append(f"来自: {p['sender']}")
            if p.get("subject"): parts.append(f"主题含: {p['subject']}")
            return "  ".join(parts) or "任意新邮件"
        elif tt == "clipboard_match":
            text = p.get("text", "")
            mode = p.get("match_mode", "contains")
            if text:
                mode_label = {
                    "contains":   "包含",
                    "exact":      "等于",
                    "startswith": "开头为",
                    "endswith":   "结尾为",
                    "wildcard":   "通配符",
                }.get(mode, mode)
                return f"{mode_label}: {text[:30]}"
            return "任意剪贴板内容变化"
        elif tt == "cpu_high":
            return f"CPU > {p.get('threshold','?')}% 持续 {p.get('duration','?')}s"
        elif tt == "memory_high":
            return f"内存 > {p.get('threshold','?')}%"
        elif tt == "disk_full":
            d = p.get('drive','') or '所有磁盘'
            return f"{d} 剩余 < {p.get('threshold','?')}GB"
        elif tt == "battery_change":
            ev = {"low":"低电量","critical":"极低","charging":"开始充电",
                  "discharging":"开始放电","full":"充满"}.get(p.get("event","low"), "")
            return f"{ev} (阈值 {p.get('threshold','?')}%)"
        elif tt == "idle_detect":
            return f"空闲 {p.get('idle_sec','?')}s"
        elif tt == "window_focus":
            return p.get("title", "") or "任意窗口获得焦点"
        elif tt == "time_range":
            return f"{p.get('start_time','?')} ~ {p.get('end_time','?')} 每{p.get('interval_sec','?')}s"
        elif tt == "network_change":
            ev = p.get("event", "any")
            label_map = {"connected": "网络连接时", "disconnected": "断网时", "any": "网络状态变化"}
            return label_map.get(ev, ev)
        elif tt == "wifi_ssid":
            ev = "连接" if p.get("event") == "connected" else "断开"
            return f"{ev}: {p.get('ssid','')}"
        elif tt == "ping_latency":
            host  = p.get("host", "")
            thr   = p.get("threshold_ms", "")
            d_map = {"above": "延迟>", "below": "延迟<", "timeout": "超时时触发"}
            direc = d_map.get(p.get("direction", "above"), "")
            if p.get("direction") == "timeout":
                return f"{host} {direc}"
            return f"{host} {direc}{thr}ms 每{p.get('interval_sec','?')}s"
        elif tt == "system_boot":
            delay = p.get("delay_sec", 30)
            return f"开机后延迟 {delay}s 触发"
        summary = self.trigger.comment or ""
        # 长度限制
        if len(summary) > 55:
            summary = summary[:52] + "…"
        return summary


class TriggerEditDialog(QDialog):
    def __init__(self, trigger: Trigger, parent=None):
        super().__init__(parent)
        self.trigger = trigger
        info = TRIGGER_TYPES.get(trigger.trigger_type, {})
        self.setWindowTitle(
            tr("trigger.edit_title") + f"{info.get('icon','')} {info.get('label', trigger.trigger_type)}"
        )
        self.setMinimumWidth(460)
        self.setModal(True)
        self._widgets = {}
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        self._comment = QLineEdit(self.trigger.comment)
        self._comment.setPlaceholderText(tr("trigger.comment_ph"))
        form.addRow(tr("trigger.comment"), self._comment)

        self._enabled = QCheckBox(tr("trigger.enabled"))
        self._enabled.setChecked(self.trigger.enabled)
        form.addRow("", self._enabled)
        layout.addLayout(form)

        params_spec = TRIGGER_PARAMS.get(self.trigger.trigger_type, {})
        if params_spec:
            pform = QFormLayout()
            pform.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
            pform.setSpacing(8)
            for key, spec in params_spec.items():
                widget = self._make_widget(key, spec)
                pform.addRow(spec["label"] + "：", widget)
                self._widgets[key] = widget
            layout.addLayout(pform)

        # 热键触发器提示
        if self.trigger.trigger_type == "hotkey":
            hint = QLabel(tr("trigger.hint.hotkey"))
            hint.setObjectName("hint")
            hint.setWordWrap(True)
            layout.addWidget(hint)

        # 剪贴板触发器提示
        if self.trigger.trigger_type == "clipboard_match":
            hint = QLabel(tr("trigger.hint.clipboard"))
            hint.setObjectName("hint")
            hint.setWordWrap(True)
            layout.addWidget(hint)

        # ── 约束条件区域 ──
        from PyQt6.QtWidgets import QFrame
        from .constraint_editor import ConstraintListWidget
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #313244; margin: 4px 0;")
        layout.addWidget(sep)
        self._constraint_widget = ConstraintListWidget(
            list(self.trigger.constraints), self
        )
        layout.addWidget(self._constraint_widget)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(tr("btn.ok"))
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("btn.cancel"))
        btns.button(QDialogButtonBox.StandardButton.Ok).setObjectName("btn_primary")
        layout.addWidget(btns)

    def _make_widget(self, key: str, spec: dict) -> QWidget:
        ptype   = spec["type"]
        default = self.trigger.params.get(key, spec.get("default", ""))

        if ptype == "hotkey_input":
            return HotkeyEdit(str(default))
        elif ptype == "process_picker":
            from .block_editor import ProcessWindowPickerEdit
            return ProcessWindowPickerEdit(str(default), mode="process")
        elif ptype == "process_window_picker":
            from .block_editor import ProcessWindowPickerEdit
            return ProcessWindowPickerEdit(str(default), mode="both")
        elif ptype == "window_picker":
            from .block_editor import WindowPickerEdit
            return WindowPickerEdit(str(default))
        elif ptype == "select":
            w = QComboBox()
            options = spec.get("options", [])
            labels  = spec.get("option_labels", options)
            for i, opt in enumerate(options):
                label = labels[i] if i < len(labels) else opt
                w.addItem(label, userData=opt)
            for i in range(w.count()):
                if w.itemData(i) == str(default):
                    w.setCurrentIndex(i)
                    break
            return w
        elif ptype == "number_or_var":
            w = QLineEdit(str(default))
            w.setPlaceholderText("数字或 {{变量名}}")
            return w
        elif ptype == "bool":
            w = QCheckBox()
            w.setChecked(bool(default))
            return w
        elif ptype == "time":
            w = QTimeEdit()
            try:
                h, m = map(int, str(default).split(":"))
                w.setTime(QTime(h, m))
            except Exception:
                pass
            return w
        elif ptype == "datetime":
            w = QLineEdit(str(default))
            w.setPlaceholderText("2025-01-01 08:00")
            return w
        elif ptype == "text_multiline":
            w = QTextEdit()
            w.setPlainText(str(default))
            w.setFixedHeight(80)
            return w
        elif ptype in ("file_picker", "folder_picker"):
            row = QWidget()
            hl  = QHBoxLayout(row)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(4)
            edit = QLineEdit(str(default))
            btn  = QPushButton("浏览")
            btn.setObjectName("btn_flat")
            btn.setFixedWidth(52)
            if ptype == "folder_picker":
                btn.clicked.connect(lambda: self._pick_folder(edit))
            else:
                btn.clicked.connect(lambda: self._pick_file(edit))
            hl.addWidget(edit)
            hl.addWidget(btn)
            return row
        else:
            w = QLineEdit(str(default))
            ph = spec.get("placeholder", "")
            if ph:
                w.setPlaceholderText(ph)
            return w

    def _pick_file(self, edit: QLineEdit):
        path, _ = QFileDialog.getOpenFileName(self, tr("btn.browse"))
        if path:
            edit.setText(path)

    def _pick_folder(self, edit: QLineEdit):
        path = QFileDialog.getExistingDirectory(self, tr("btn.browse"))
        if path:
            edit.setText(path)

    def _get_widget_value(self, key: str, spec: dict):
        w     = self._widgets.get(key)
        ptype = spec["type"]
        if w is None:
            return spec.get("default", "")
        if ptype == "select":
            data = w.currentData()
            return data if data is not None else w.currentText()
        elif ptype == "bool":
            return w.isChecked()
        elif ptype == "time":
            return w.time().toString("HH:mm")
        elif ptype == "hotkey_input":
            return w.text()
        elif ptype in ("window_picker", "process_picker", "process_window_picker"):
            return w.text()
        elif ptype == "text_multiline":
            return w.toPlainText()
        elif ptype in ("file_picker", "folder_picker"):
            edit = w.findChild(QLineEdit)
            return edit.text() if edit else ""
        elif ptype == "number_or_var":
            txt = w.text()
            try:
                v = float(txt)
                return int(v) if v == int(v) else v
            except Exception:
                return txt
        else:
            return w.text()

    def _save(self):
        self.trigger.comment = self._comment.text()
        self.trigger.enabled = self._enabled.isChecked()
        spec = TRIGGER_PARAMS.get(self.trigger.trigger_type, {})
        for key, s in spec.items():
            self.trigger.params[key] = self._get_widget_value(key, s)
        # 保存约束条件
        if hasattr(self, "_constraint_widget"):
            self.trigger.constraints = self._constraint_widget.get_constraints()
        self.accept()


class TriggerListWidget(QWidget):
    changed           = pyqtSignal()
    # 只要有选中状态变更就发出（用于与 BlockListWidget 互斥）
    selection_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._triggers: List[Trigger] = []
        self._card_widgets: List[TriggerCard] = []
        self._selected_ids: set = set()
        self._multiselect_mode: bool = False
        self._clipboard_triggers: List[Trigger] = []
        self._anchor_trigger_id = None   # Shift 多选的锚点
        self._build_ui()
        self.setAcceptDrops(True)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 工具栏
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 8)
        toolbar.setSpacing(6)
        self._section_lbl = QLabel(tr("trigger.section"))
        self._section_lbl.setObjectName("section_title")
        toolbar.addWidget(self._section_lbl)
        toolbar.addStretch()

        # 多选按钮
        self._multiselect_btn = QPushButton("☑")
        self._multiselect_btn.setObjectName("btn_flat")
        self._multiselect_btn.setToolTip("多选模式 (Ctrl+点击)")
        self._multiselect_btn.setFixedSize(28, 28)
        self._multiselect_btn.clicked.connect(self._toggle_multiselect_mode)
        toolbar.addWidget(self._multiselect_btn)

        self._add_btn = QPushButton(tr("trigger.add"))
        self._add_btn.setObjectName("btn_primary")
        self._add_btn.clicked.connect(self._show_add_menu)
        toolbar.addWidget(self._add_btn)

        self._clear_btn = QPushButton(tr("trigger.clear"))
        self._clear_btn.setObjectName("btn_danger")
        self._clear_btn.setToolTip(tr("trigger.clear_tip"))
        self._clear_btn.clicked.connect(self._clear_all)
        toolbar.addWidget(self._clear_btn)

        layout.addLayout(toolbar)

        # 多选操作工具栏（默认隐藏）
        self._multiselect_toolbar = QHBoxLayout()
        self._multiselect_toolbar.setContentsMargins(0, 0, 0, 6)
        self._multiselect_toolbar.setSpacing(4)
        self._select_all_btn = QPushButton("全选")
        self._select_all_btn.setObjectName("btn_flat")
        self._select_all_btn.setFixedHeight(24)
        self._select_all_btn.clicked.connect(self._select_all)
        self._multiselect_toolbar.addWidget(self._select_all_btn)
        self._deselect_btn = QPushButton("取消全选")
        self._deselect_btn.setObjectName("btn_flat")
        self._deselect_btn.setFixedHeight(24)
        self._deselect_btn.clicked.connect(self._deselect_all)
        self._multiselect_toolbar.addWidget(self._deselect_btn)
        self._multiselect_toolbar.addStretch()
        self._copy_sel_btn = QPushButton("⎘ 复制")
        self._copy_sel_btn.setObjectName("btn_flat")
        self._copy_sel_btn.setFixedHeight(24)
        self._copy_sel_btn.clicked.connect(self._copy_selected)
        self._multiselect_toolbar.addWidget(self._copy_sel_btn)
        self._del_sel_btn = QPushButton("🗑 删除")
        self._del_sel_btn.setObjectName("btn_danger")
        self._del_sel_btn.setFixedHeight(24)
        self._del_sel_btn.clicked.connect(self._delete_selected)
        self._multiselect_toolbar.addWidget(self._del_sel_btn)
        self._multiselect_bar_widget = QWidget()
        self._multiselect_bar_widget.setLayout(self._multiselect_toolbar)
        self._multiselect_bar_widget.setVisible(False)
        layout.addWidget(self._multiselect_bar_widget)

        # 滚动区
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._scroll_body = QWidget()
        self._body_layout = QVBoxLayout(self._scroll_body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(4)

        self._empty_hint = QLabel(tr("trigger.empty"))
        self._empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_hint.setStyleSheet("""
            color: #45475A; font-size: 13px; padding: 24px;
            border: 2px dashed #313244; border-radius: 12px; margin: 8px 0;
        """)
        self._body_layout.addWidget(self._empty_hint)
        self._body_layout.addStretch()

        scroll.setWidget(self._scroll_body)
        layout.addWidget(scroll)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # 在 scroll body 上安装事件过滤器，用于空白处取消选中
        self._scroll_body.installEventFilter(self)

    def eventFilter(self, obj, event):
        """监听 _scroll_body 上的鼠标点击，点击空白处清除选中"""
        from PyQt6.QtCore import QEvent
        if obj is self._scroll_body and event.type() == QEvent.Type.MouseButtonPress:
            from PyQt6.QtCore import Qt as _Qt
            if event.button() == _Qt.MouseButton.LeftButton:
                child = self._scroll_body.childAt(event.position().toPoint())
                # 如果没有点到任何控件，或者点到的控件不在 TriggerCard 内部
                hit_card = False
                w = child
                while w is not None and w is not self._scroll_body:
                    if isinstance(w, TriggerCard):
                        hit_card = True
                        break
                    w = w.parent() if callable(getattr(w, 'parent', None)) else None
                if not hit_card:
                    self._selected_ids.clear()
                    self._anchor_trigger_id = None
                    self._multiselect_mode = False
                    self._sync_selection_ui()
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        """键盘快捷键：Ctrl+A 全选，Ctrl+C 复制，Delete/Ctrl+X 删除"""
        if self._multiselect_mode:
            key  = event.key()
            ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier
            if ctrl and key == Qt.Key.Key_A:
                self._select_all()
                return
            elif ctrl and key == Qt.Key.Key_C:
                self._copy_selected()
                return
            elif key == Qt.Key.Key_Delete or (ctrl and key == Qt.Key.Key_X):
                self._delete_selected()
                return
        super().keyPressEvent(event)

    def retranslate(self):
        self._section_lbl.setText(tr("trigger.section"))
        self._add_btn.setText(tr("trigger.add"))
        self._clear_btn.setText(tr("trigger.clear"))
        self._clear_btn.setToolTip(tr("trigger.clear_tip"))
        self._empty_hint.setText(tr("trigger.empty"))

    def set_triggers(self, triggers: List[Trigger]):
        self._triggers = triggers
        self._refresh()

    def get_triggers(self) -> List[Trigger]:
        return self._triggers

    def _toggle_multiselect_mode(self):
        self._multiselect_mode = not self._multiselect_mode
        self._multiselect_bar_widget.setVisible(self._multiselect_mode)
        if not self._multiselect_mode:
            self._selected_ids.clear()
            self._anchor_trigger_id = None
        self._sync_selection_ui()

    def _select_all(self):
        self._multiselect_mode = True
        self._selected_ids = {t.id for t in self._triggers}
        self._sync_selection_ui()

    def _deselect_all(self):
        self._selected_ids.clear()
        self._sync_selection_ui()

    def _on_select_toggled(self, card: "TriggerCard", checked: bool):
        if checked:
            self._selected_ids.add(card.trigger.id)
        else:
            self._selected_ids.discard(card.trigger.id)

    def _on_card_clicked(self, card: "TriggerCard", shift_held: bool):
        """单击触发器卡片：普通单击=单选，Shift单击=范围多选"""
        tid = card.trigger.id
        if shift_held:
            self._multiselect_mode = True
            if self._anchor_trigger_id:
                anchor_id = self._anchor_trigger_id
            elif self._selected_ids:
                anchor_id = next(iter(self._selected_ids))
            else:
                anchor_id = tid
            tids = [t.id for t in self._triggers]
            try:
                a_idx = tids.index(anchor_id)
            except ValueError:
                a_idx = 0
            try:
                b_idx = tids.index(tid)
            except ValueError:
                b_idx = len(tids) - 1
            lo, hi = min(a_idx, b_idx), max(a_idx, b_idx)
            self._selected_ids = {tids[i] for i in range(lo, hi + 1)}
        else:
            if self._multiselect_mode and tid in self._selected_ids and len(self._selected_ids) == 1:
                self._selected_ids.clear()
                self._multiselect_mode = False
                self._anchor_trigger_id = None
            elif not self._multiselect_mode and tid in self._selected_ids:
                self._selected_ids.clear()
                self._anchor_trigger_id = None
            else:
                self._multiselect_mode = False
                self._selected_ids = {tid}
                self._anchor_trigger_id = tid
        self._sync_selection_ui()

    def _sync_selection_ui(self):
        """根据 _selected_ids 和 _multiselect_mode 同步所有卡片视觉状态"""
        for c in self._card_widgets:
            selected = c.trigger.id in self._selected_ids
            c.set_selected(selected)
            if hasattr(c, '_select_cb'):
                c._select_cb.setVisible(self._multiselect_mode)
                c._select_cb.blockSignals(True)
                c._select_cb.setChecked(selected)
                c._select_cb.blockSignals(False)
        self.selection_changed.emit()

    def clear_selection(self):
        """外部调用：清除所有选中（不发 selection_changed 防止循环）"""
        self._selected_ids.clear()
        self._anchor_trigger_id = None
        self._multiselect_mode = False
        for c in self._card_widgets:
            c.set_selected(False)
            if hasattr(c, '_select_cb'):
                c._select_cb.setVisible(False)
                c._select_cb.blockSignals(True)
                c._select_cb.setChecked(False)
                c._select_cb.blockSignals(False)



    def _copy_selected(self):
        """复制选中的触发器到内部剪贴板"""
        selected = [t for t in self._triggers if t.id in self._selected_ids]
        if not selected:
            return
        self._clipboard_triggers = []
        for t in selected:
            nt = Trigger(trigger_type=t.trigger_type)
            nt.params   = copy.deepcopy(t.params)
            nt.comment  = t.comment
            nt.enabled  = t.enabled
            self._clipboard_triggers.append(nt)
        # 把复制内容粘贴到末尾
        for nt in self._clipboard_triggers:
            # 给每个复制出来的触发器分配新ID（Trigger.__init__已分配）
            pass
        # 实际插入
        for nt in self._clipboard_triggers:
            import uuid as _uuid
            nt2 = Trigger(trigger_type=nt.trigger_type)
            nt2.params   = copy.deepcopy(nt.params)
            nt2.comment  = nt.comment
            nt2.enabled  = nt.enabled
            self._triggers.append(nt2)
        self._refresh()
        self.changed.emit()

    def _delete_selected(self):
        """删除选中的触发器"""
        if not self._selected_ids:
            return
        self._triggers = [t for t in self._triggers if t.id not in self._selected_ids]
        self._selected_ids.clear()
        self._refresh()
        self.changed.emit()

    def _move_trigger_up(self, trigger: Trigger):
        idx = next((i for i, t in enumerate(self._triggers) if t.id == trigger.id), -1)
        if idx > 0:
            self._triggers[idx], self._triggers[idx-1] = self._triggers[idx-1], self._triggers[idx]
            self._refresh()
            self.changed.emit()

    def _move_trigger_down(self, trigger: Trigger):
        idx = next((i for i, t in enumerate(self._triggers) if t.id == trigger.id), -1)
        if 0 <= idx < len(self._triggers) - 1:
            self._triggers[idx], self._triggers[idx+1] = self._triggers[idx+1], self._triggers[idx]
            self._refresh()
            self.changed.emit()

    # ── 拖拽排序支持 ──
    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-trigger-id"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-trigger-id"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat("application/x-trigger-id"):
            event.ignore()
            return
        drag_id = event.mimeData().data("application/x-trigger-id").data().decode()
        drag_idx = next((i for i, t in enumerate(self._triggers) if t.id == drag_id), -1)
        if drag_idx < 0:
            event.ignore()
            return

        # 确定放置位置（基于鼠标在 _scroll_body 的位置）
        drop_pos = self._scroll_body.mapFrom(self, event.position().toPoint())
        drop_idx = len(self._triggers)
        for i, card in enumerate(self._card_widgets):
            card_center_y = card.geometry().center().y()
            if drop_pos.y() < card_center_y:
                drop_idx = i
                break

        # ── 多选拖动：若被拖动的触发器在选中集合中，整组移动 ──
        if drag_id in self._selected_ids and len(self._selected_ids) > 1:
            selected_triggers = [t for t in self._triggers if t.id in self._selected_ids]
            sel_indices = {i for i, t in enumerate(self._triggers) if t.id in self._selected_ids}
            if drop_idx in sel_indices:
                event.acceptProposedAction()
                return
            remaining = [t for t in self._triggers if t.id not in self._selected_ids]
            offset = sum(1 for idx in sel_indices if idx < drop_idx)
            insert_at = max(0, min(drop_idx - offset, len(remaining)))
            for k, trig in enumerate(selected_triggers):
                remaining.insert(insert_at + k, trig)
            self._triggers[:] = remaining
            self._refresh()
            self.changed.emit()
            event.acceptProposedAction()
            return

        # ── 单块拖动 ──
        if drag_idx == drop_idx or drag_idx + 1 == drop_idx:
            event.acceptProposedAction()
            return

        trig = self._triggers.pop(drag_idx)
        if drop_idx > drag_idx:
            drop_idx -= 1
        self._triggers.insert(drop_idx, trig)
        self._refresh()
        self.changed.emit()
        event.acceptProposedAction()

    def _clear_all(self):
        if not self._triggers:
            return
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, tr("trigger.clear"),
            tr("trigger.clear_confirm", len(self._triggers)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._triggers.clear()
        self._selected_ids.clear()
        self._refresh()
        self.changed.emit()

    def _refresh(self):
        for card in self._card_widgets:
            card.hide()
            self._body_layout.removeWidget(card)
            card.deleteLater()
        self._card_widgets.clear()

        self._empty_hint.setVisible(len(self._triggers) == 0)

        for i, trig in enumerate(self._triggers):
            card = TriggerCard(trig, self._scroll_body)
            card.edit_requested.connect(lambda c: self._edit_trigger(c.trigger))
            card.delete_requested.connect(lambda c: self._delete_trigger(c.trigger))
            card.copy_requested.connect(lambda c: self._copy_trigger(c.trigger))
            card.select_toggled.connect(self._on_select_toggled)
            card.card_clicked.connect(self._on_card_clicked)
            card.card_double_clicked.connect(lambda c: self._edit_trigger(c.trigger))
            card.move_up_requested.connect(lambda c: self._move_trigger_up(c.trigger))
            card.move_down_requested.connect(lambda c: self._move_trigger_down(c.trigger))
            card.set_multiselect_visible(self._multiselect_mode)
            if trig.id in self._selected_ids:
                card.set_selected(True)
            self._body_layout.insertWidget(i, card)
            self._card_widgets.append(card)

        # ── 触发器卡片淡入动画 ──
        from .effects import fade_in as _fade_in
        for i, card in enumerate(self._card_widgets):
            QTimer.singleShot(
                min(i * 8, 80),
                lambda c=card: _fade_in(c, 100, on_finished=lambda _c=c: _c.setGraphicsEffect(None))
            )

        # ── 强制刷新布局，消除残影 ──
        self._body_layout.invalidate()
        self._body_layout.activate()
        self._scroll_body.update()

    def _show_add_menu(self):
        menu = QMenu(self)
        categories: dict = {}
        for tt, info in TRIGGER_TYPES.items():
            cat = info.get("category", "其他")
            categories.setdefault(cat, []).append((tt, info))

        CAT_ORDER = ["基础", "应用&进程", "文件&系统", "系统资源", "网络", "数据", "其他"]
        sorted_cats = sorted(categories.keys(),
                             key=lambda c: CAT_ORDER.index(c) if c in CAT_ORDER else 99)

        for cat in sorted_cats:
            items = categories[cat]
            sub = menu.addMenu(f"  {cat}")
            for tt, info in items:
                action = sub.addAction(f"{info['icon']}  {info['label']}")
                action.triggered.connect(lambda checked, t=tt: self._add_trigger(t))
        menu.exec(QCursor.pos())

    def _add_trigger(self, trigger_type: str):
        trig = Trigger(trigger_type=trigger_type)
        spec = TRIGGER_PARAMS.get(trigger_type, {})
        trig.params = {k: v["default"] for k, v in spec.items()}
        if spec:
            dlg = TriggerEditDialog(trig, self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
        self._triggers.append(trig)
        self._refresh()
        self.changed.emit()

    def _edit_trigger(self, trigger: Trigger):
        dlg = TriggerEditDialog(trigger, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh()
            self.changed.emit()

    def _delete_trigger(self, trigger: Trigger):
        self._triggers = [t for t in self._triggers if t.id != trigger.id]
        self._selected_ids.discard(trigger.id)
        self._refresh()
        self.changed.emit()

    def _copy_trigger(self, trigger: Trigger):
        """复制单个触发器，插入到原触发器后面"""
        idx = next((i for i, t in enumerate(self._triggers) if t.id == trigger.id), -1)
        if idx < 0:
            return
        nt = Trigger(trigger_type=trigger.trigger_type)
        nt.params   = copy.deepcopy(trigger.params)
        nt.comment  = trigger.comment
        nt.enabled  = trigger.enabled
        self._triggers.insert(idx + 1, nt)
        self._refresh()
        self.changed.emit()

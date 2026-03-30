"""
积木式功能块编辑器
可视化拖放、添加、删除、排序、复制功能块
"""
import copy
import os
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve, QSize, QTimer
from PyQt6.QtGui import QCursor, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QMenu, QToolButton,
    QDialog, QFormLayout, QLineEdit, QComboBox, QSpinBox,
    QDoubleSpinBox, QCheckBox, QDialogButtonBox, QFileDialog,
    QTextEdit, QApplication, QMessageBox, QTimeEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QSplitter, QListWidget, QListWidgetItem
)
import time
import json
from typing import List, Optional, Callable

from ..engine.models import Block, BLOCK_TYPES, BLOCK_PARAMS, Constraint
from ..i18n import tr, add_language_observer, remove_language_observer

# 标记类型：loop/loop_end/group/group_end 都是"包裹标记"
_MARKER_TYPES  = {"loop", "loop_end", "group", "group_end",
                  "if_block", "elif_block", "else_block", "if_end"}
_OPEN_MARKERS  = {"loop", "group", "if_block"}
_CLOSE_MARKERS = {"loop_end", "group_end", "if_end"}
_PAIR_MAP      = {"loop": "loop_end", "group": "group_end", "if_block": "if_end",
                  "loop_end": "loop", "group_end": "group", "if_end": "if_block"}

# ── 全局主题状态（由 main_window._apply_theme 维护）──
_DARK_MODE: bool = True   # 默认深色

def set_theme_dark(is_dark: bool):
    """由 main_window._apply_theme() 调用，切换主题时更新此全局状态。"""
    global _DARK_MODE
    _DARK_MODE = is_dark

def is_theme_dark() -> bool:
    """返回当前是否为深色主题。BlockItem / TriggerCard 等均应调用此函数。"""
    return _DARK_MODE

# 哪些折叠段可以折叠
_COLLAPSIBLE   = {"loop", "group", "if_block"}

# if 内部分支标记（不增加深度、不减少深度，但影响缩进基于if层级）
_IF_BRANCH_MARKERS = {"elif_block", "else_block"}


# ── 只响应焦点滚轮的 SpinBox ─────────────────────────────────────
class FocusDoubleSpinBox(QDoubleSpinBox):
    """只有在输入框被点击/获得焦点后才响应鼠标滚轮，避免滚动页面时误触数值"""
    
    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()  # 把事件向上传递，让外层滚动区处理


class FocusSpinBox(QSpinBox):
    """只有在输入框被点击/获得焦点后才响应鼠标滚轮"""
    
    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


def _ctype_to_label(block_type: str, ctype: str) -> str:
    """将 condition_type 的原始 value 映射为中文标签（查 BLOCK_PARAMS option_labels）。"""
    spec = BLOCK_PARAMS.get(block_type, {}).get("condition_type", {})
    options = spec.get("options", [])
    labels  = spec.get("option_labels", [])
    if ctype in options:
        idx = options.index(ctype)
        if idx < len(labels):
            return labels[idx]
    return ctype  # 找不到时回退显示原值




# ─────────────────── 热键输入控件 ───────────────────

class HotkeyEdit(QLineEdit):
    """按键捕获输入框：聚焦后监听键盘事件，自动填充热键字符串"""

    def __init__(self, default: str = "", parent=None):
        super().__init__(default, parent)
        self.setPlaceholderText(tr("widget.hotkey_ph"))
        self.setReadOnly(False)
        self._recording = False

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.setPlaceholderText(tr("widget.hotkey_rec"))
        self._recording = True

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.setPlaceholderText(tr("widget.hotkey_ph"))
        self._recording = False

    def keyPressEvent(self, event):
        if not self._recording:
            super().keyPressEvent(event)
            return
        from PyQt6.QtCore import Qt as _Qt
        key = event.key()
        mods = event.modifiers()

        parts = []
        if mods & _Qt.KeyboardModifier.ControlModifier: parts.append("ctrl")
        if mods & _Qt.KeyboardModifier.AltModifier:     parts.append("alt")
        if mods & _Qt.KeyboardModifier.ShiftModifier:   parts.append("shift")
        if mods & _Qt.KeyboardModifier.MetaModifier:    parts.append("win")

        key_name = None
        if _Qt.Key.Key_F1 <= key <= _Qt.Key.Key_F12:
            key_name = f"f{key - _Qt.Key.Key_F1 + 1}"
        elif key == _Qt.Key.Key_Return or key == _Qt.Key.Key_Enter:
            key_name = "enter"
        elif key == _Qt.Key.Key_Escape:
            key_name = "esc"
        elif key == _Qt.Key.Key_Space:
            key_name = "space"
        elif key == _Qt.Key.Key_Tab:
            key_name = "tab"
        elif key == _Qt.Key.Key_Delete:
            key_name = "delete"
        elif key == _Qt.Key.Key_Backspace:
            key_name = "backspace"
        elif 0x41 <= key <= 0x5A:
            key_name = chr(key).lower()
        elif 0x30 <= key <= 0x39:
            key_name = chr(key)
        elif key not in (
            _Qt.Key.Key_Control, _Qt.Key.Key_Alt,
            _Qt.Key.Key_Shift, _Qt.Key.Key_Meta
        ):
            key_name = event.text() or None

        if key_name:
            parts.append(key_name)
            self.setText("+".join(parts))
            self._recording = False
            self.clearFocus()


class HotkeyEditWidget(QWidget):
    """
    快捷键输入组合控件（点击输入框即可开始录制，无需额外按钮）。
    对外接口与 HotkeyEdit 一致（text() / setText()）。
    """

    def __init__(self, default: str = "", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._edit = HotkeyEdit(default, self)
        layout.addWidget(self._edit)

    def text(self) -> str:
        return self._edit.text()

    def setText(self, t: str):
        self._edit.setText(t)


# ─────────────────── 条件目标动态辅助控件 ───────────────────

# 目标输入框标签（随条件类型变化）
_COND_TARGET_LABELS = {
    "process_exists":    "进程名",
    "window_exists":     "窗口标题",
    "file_exists":       "路径",
    "file_changed":      "路径",
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

# 哪些类型不需要 target 输入（隐藏整行）
_COND_NO_TARGET = {"always_true", "internet_connected", "battery_charging", "capslock_on"}


class ConditionTargetWidget(QWidget):
    """
    条件目标输入控件（用于 if_block/elif_block）：
    - 左侧：动态描述标签（随 condition_type 切换）
    - 中间：QLineEdit 输入框
    - 右侧：智能辅助按钮（随 condition_type 切换）：
        process_exists   → [🖱 点选] + [📋 进程列表]
        window_exists    → [🖱 点选]
        file_exists/changed → [📁 选择]（选文件/选目录）
        ping_latency_*   → [🌐 本机]（填 127.0.0.1）
        其他             → 无辅助按钮
    """

    def __init__(self, default: str = "", parent=None):
        super().__init__(parent)
        self._ctype = "process_exists"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)

        # 动态标签行（在输入行上方）
        self._label = QLabel("进程名：")
        self._label.setStyleSheet("color: #A6ADC8; font-size: 11px;")
        outer.addWidget(self._label)

        # 输入行
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        self._edit = QLineEdit(default)
        self._edit.setPlaceholderText("输入目标值或使用右侧辅助按钮")
        row.addWidget(self._edit)

        # 占位按钮容器（动态替换内容）
        self._btn_container = QHBoxLayout()
        self._btn_container.setContentsMargins(0, 0, 0, 0)
        self._btn_container.setSpacing(4)
        row.addLayout(self._btn_container)

        outer.addLayout(row)
        self._countdown = 3
        self._current_mode = None  # 避免重复构建

    def text(self) -> str:
        return self._edit.text()

    def setText(self, t: str):
        self._edit.setText(t)

    def update_condition_type(self, ctype: str):
        """当 condition_type 下拉改变时调用，刷新标签和辅助按钮。"""
        if ctype == self._ctype and self._current_mode is not None:
            return
        self._ctype = ctype

        # 更新标签
        lbl_text = _COND_TARGET_LABELS.get(ctype, "目标值")
        self._label.setText(f"{lbl_text}：")

        # 隐藏/显示整个控件（无目标类型隐藏）
        self.setVisible(ctype not in _COND_NO_TARGET)

        # 清空旧按钮
        while self._btn_container.count():
            item = self._btn_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._current_mode = ctype

        # 按类型添加辅助按钮
        if ctype == "process_exists":
            self._add_btn("🖱 点选", self._start_pick_process)
            self._add_btn("📋 进程列表", self._show_process_list)
        elif ctype == "window_exists":
            self._add_btn("🖱 点选", self._start_pick_window)
        elif ctype in ("file_exists", "file_changed"):
            btn = QPushButton("📁 选择")
            btn.setObjectName("btn_flat")
            btn.setFixedHeight(26)
            btn.setStyleSheet(self._btn_style())
            menu = QMenu(btn)
            menu.addAction("选择文件", lambda: self._pick_file())
            menu.addAction("选择目录", lambda: self._pick_dir())
            btn.setMenu(menu)
            self._btn_container.addWidget(btn)
        elif ctype in ("ping_latency_gt", "ping_latency_lt"):
            self._add_btn("🌐 本机", lambda: self._edit.setText("127.0.0.1"))

    def _btn_style(self):
        return (
            "QPushButton { background: transparent; border: 1px solid #45475A;"
            " border-radius: 6px; padding: 2px 8px; color: #A6ADC8; font-size: 11px; }"
            "QPushButton:hover { background: #45475A33; border-color: #89B4FA; color: #CDD6F4; }"
            "QPushButton::menu-indicator { image: none; width: 0; }"
        )

    def _add_btn(self, label: str, slot):
        btn = QPushButton(label)
        btn.setObjectName("btn_flat")
        btn.setFixedHeight(26)
        btn.setStyleSheet(self._btn_style())
        btn.clicked.connect(slot)
        self._btn_container.addWidget(btn)

    # ── 点选进程 ──
    def _start_pick_process(self):
        self._pick_target_mode = "process"
        self._do_start_pick()

    # ── 点选窗口 ──
    def _start_pick_window(self):
        self._pick_target_mode = "window"
        self._do_start_pick()

    def _do_start_pick(self):
        # 最小化父对话框
        top = self
        while top.parent():
            top = top.parent()
        if hasattr(top, 'showMinimized'):
            top.showMinimized()
        self._countdown = 3
        self._pick_timer = QTimer(self)
        self._pick_timer.timeout.connect(self._pick_tick)
        self._pick_timer.start(1000)

    def _pick_tick(self):
        self._countdown -= 1
        if self._countdown > 0:
            pass
        else:
            self._pick_timer.stop()
            self._do_pick_now()

    def _do_pick_now(self):
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if getattr(self, '_pick_target_mode', 'window') == "process":
                pid = ctypes.c_ulong()
                ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                import psutil
                self._edit.setText(psutil.Process(pid.value).name())
            else:
                buf = ctypes.create_unicode_buffer(256)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
                title = buf.value.strip()
                if title:
                    self._edit.setText(title)
        except Exception:
            pass
        # 恢复父对话框
        top = self
        while top.parent():
            top = top.parent()
        if hasattr(top, 'showNormal'):
            top.showNormal()
        if hasattr(top, 'activateWindow'):
            top.activateWindow()

    def _show_process_list(self):
        dlg = ProcessWindowListDialog(mode="process", parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_value:
            self._edit.setText(dlg.selected_value)

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择文件")
        if path:
            self._edit.setText(path)

    def _pick_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择目录")
        if path:
            self._edit.setText(path)


# ─────────────────── 窗口选择器控件 ───────────────────

class WindowPickerEdit(QWidget):
    """
    窗口选择控件：文本框 + [选择] 按钮
    点击选择按钮后最小化主窗口，3秒后识别鼠标所在位置的窗口标题
    回调 on_picked(title, class_name, process_name) 用于父控件自动填写附加字段
    """

    def __init__(self, default: str = "", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._edit = QLineEdit(default)
        self._edit.setPlaceholderText(tr("widget.window_ph"))
        layout.addWidget(self._edit)

        self._btn = QPushButton(tr("widget.pick"))
        self._btn.setObjectName("btn_flat")
        self._btn.setFixedWidth(66)
        self._btn.setToolTip(tr("widget.pick_tip"))
        self._btn.clicked.connect(self._start_pick)
        layout.addWidget(self._btn)

        self._countdown = 3
        # 可选回调：on_picked(title: str, class_name: str, process_name: str)
        self.on_picked = None

    def text(self) -> str:
        return self._edit.text()

    def setText(self, t: str):
        self._edit.setText(t)

    def _start_pick(self):
        """最小化主窗口，延时后读取前台窗口标题"""
        # 找最顶层窗口并最小化
        top = self
        while top.parent():
            top = top.parent()
        if hasattr(top, 'showMinimized'):
            top.showMinimized()

        self._countdown = 3
        self._btn.setEnabled(False)
        self._btn.setText("3s...")
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)

    def _tick(self):
        self._countdown -= 1
        if self._countdown > 0:
            self._btn.setText(f"{self._countdown}s...")
        else:
            self._timer.stop()
            self._do_pick()

    def _do_pick(self):
        title = ""
        class_name = ""
        process_name = ""
        try:
            import ctypes
            import ctypes.wintypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            # 标题
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            title = buf.value.strip()
            if title:
                self._edit.setText(title)
            # 类名
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buf, 256)
            class_name = cls_buf.value.strip()
            # 进程名
            pid = ctypes.wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            try:
                import psutil
                process_name = psutil.Process(pid.value).name()
            except Exception:
                pass
        except Exception:
            pass
        self._btn.setEnabled(True)
        self._btn.setText(tr("widget.pick"))
        # 恢复主窗口
        top = self
        while top.parent():
            top = top.parent()
        if hasattr(top, 'showNormal'):
            top.showNormal()
        if hasattr(top, 'activateWindow'):
            top.activateWindow()
        # 触发回调（回填 class_name / process_name 到同一表单）
        if callable(self.on_picked):
            self.on_picked(title, class_name, process_name)


# ─────────────────── 进程/窗口选择器控件 ───────────────────

class ProcessWindowPickerEdit(QWidget):
    """
    进程/窗口选择控件：文本框 + [点选] + [列表选] 按钮
    点选：最小化主窗口，3s后读前台窗口并填入
    列表选：弹出类似任务管理器的进程/窗口列表让用户选择
    """

    def __init__(self, default: str = "", mode: str = "window", parent=None):
        """
        mode: "window"=只显示窗口标题, "process"=只显示进程名, "both"=两者都显示
        """
        super().__init__(parent)
        self._mode = mode
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._edit = QLineEdit(default)
        self._edit.setPlaceholderText(tr("widget.proc_win_ph"))
        layout.addWidget(self._edit)

        self._btn_pick = QPushButton(tr("widget.pick"))
        self._btn_pick.setObjectName("btn_flat")
        self._btn_pick.setFixedWidth(66)
        self._btn_pick.setToolTip(tr("widget.pick_tip"))
        self._btn_pick.clicked.connect(self._start_pick)
        layout.addWidget(self._btn_pick)

        self._btn_list = QPushButton(tr("widget.list"))
        self._btn_list.setObjectName("btn_flat")
        self._btn_list.setFixedWidth(60)
        self._btn_list.setToolTip(tr("widget.list_tip"))
        self._btn_list.clicked.connect(self._show_list)
        layout.addWidget(self._btn_list)

        self._countdown = 3

    def text(self) -> str:
        return self._edit.text()

    def setText(self, t: str):
        self._edit.setText(t)

    def _start_pick(self):
        """mode=window/both: 3秒倒计时取前台窗口标题；mode=process: 直接弹出进程列表"""
        if self._mode == "process":
            # 进程名模式直接弹列表，更精准
            self._show_list()
            return
        top = self
        while top.parent():
            top = top.parent()
        if hasattr(top, 'showMinimized'):
            top.showMinimized()
        self._countdown = 3
        self._btn_pick.setEnabled(False)
        self._btn_pick.setText("3s...")
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)

    def _tick(self):
        self._countdown -= 1
        if self._countdown > 0:
            self._btn_pick.setText(f"{self._countdown}s...")
        else:
            self._timer.stop()
            self._do_pick()

    def _do_pick(self):
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
            title = buf.value.strip()
            if title and self._mode in ("window", "both"):
                self._edit.setText(title)
        except Exception:
            pass
        self._btn_pick.setEnabled(True)
        self._btn_pick.setText(tr("widget.pick"))
        top = self
        while top.parent():
            top = top.parent()
        if hasattr(top, 'showNormal'):
            top.showNormal()
        if hasattr(top, 'activateWindow'):
            top.activateWindow()

    def _show_list(self):
        dlg = ProcessWindowListDialog(mode=self._mode, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_value:
            self._edit.setText(dlg.selected_value)


class ProcessWindowListDialog(QDialog):
    """弹出进程/窗口列表（类任务管理器）供用户选择"""

    def __init__(self, mode: str = "both", parent=None):
        super().__init__(parent)
        self._mode = mode
        self.selected_value = ""
        self.setWindowTitle(tr("proc_list.title"))
        self.setMinimumSize(600, 420)
        self.setModal(True)
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # 搜索框
        search_row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText(tr("proc_list.filter_ph"))
        self._search.textChanged.connect(self._filter)
        search_row.addWidget(self._search)
        refresh_btn = QPushButton(tr("btn.refresh"))
        refresh_btn.setObjectName("btn_flat")
        refresh_btn.setFixedWidth(52)
        refresh_btn.clicked.connect(self._refresh)
        search_row.addWidget(refresh_btn)
        layout.addLayout(search_row)

        # 表格
        self._table = QTableWidget()
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.doubleClicked.connect(self._accept_selection)
        layout.addWidget(self._table)

        # 按钮
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._accept_selection)
        btns.rejected.connect(self.reject)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(tr("btn.ok"))
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("btn.cancel"))
        layout.addWidget(btns)

    def _refresh(self):
        import psutil, ctypes

        self._data = []

        if self._mode in ("process", "both"):
            seen_pids = set()
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info']):
                try:
                    pid  = proc.info['pid']
                    name = proc.info['name'] or ""
                    cpu  = proc.cpu_percent() if hasattr(proc, 'cpu_percent') else 0
                    mem  = proc.info['memory_info'].rss // (1024*1024) if proc.info['memory_info'] else 0
                    self._data.append({
                        "type": "process", "name": name, "pid": pid,
                        "cpu": cpu, "mem": mem, "value": name
                    })
                    seen_pids.add(pid)
                except Exception:
                    pass

        if self._mode in ("window", "both"):
            EnumWindowsCB = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.LPARAM)
            wins = []
            def _cb(hwnd, _):
                if not ctypes.windll.user32.IsWindowVisible(hwnd):
                    return True
                buf = ctypes.create_unicode_buffer(256)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
                title = buf.value.strip()
                if not title:
                    return True
                pid = ctypes.c_ulong()
                ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                proc_name = ""
                try:
                    import psutil as _ps
                    proc_name = _ps.Process(pid.value).name()
                except Exception:
                    pass
                wins.append({"type":"window","name":title,"pid":pid.value,
                              "proc":proc_name,"value":title})
                return True
            ctypes.windll.user32.EnumWindows(EnumWindowsCB(_cb), 0)
            self._data.extend(wins)

        self._build_table(self._data)

    def _build_table(self, data):
        if self._mode == "both":
            cols = [tr("proc_list.col_proc"), tr("proc_list.col_win"), tr("proc_list.col_pid"), "CPU%", "MB"]
        elif self._mode == "process":
            cols = [tr("proc_list.col_proc"), tr("proc_list.col_pid"), "CPU%", "MB"]
        else:
            cols = [tr("proc_list.col_win"), tr("proc_list.col_pid"), tr("proc_list.col_proc")]

        self._table.setColumnCount(len(cols))
        self._table.setHorizontalHeaderLabels(cols)
        self._table.setRowCount(len(data))
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        for row, item in enumerate(data):
            if self._mode == "both":
                self._table.setItem(row, 0, QTableWidgetItem(item["type"]))
                self._table.setItem(row, 1, QTableWidgetItem(item["name"]))
                self._table.setItem(row, 2, QTableWidgetItem(str(item.get("pid",""))))
                self._table.setItem(row, 3, QTableWidgetItem(str(item.get("cpu",""))))
                self._table.setItem(row, 4, QTableWidgetItem(str(item.get("mem",""))))
            elif self._mode == "process":
                self._table.setItem(row, 0, QTableWidgetItem(item["name"]))
                self._table.setItem(row, 1, QTableWidgetItem(str(item.get("pid",""))))
                self._table.setItem(row, 2, QTableWidgetItem(str(item.get("cpu",""))))
                self._table.setItem(row, 3, QTableWidgetItem(str(item.get("mem",""))))
            else:
                self._table.setItem(row, 0, QTableWidgetItem(item["name"]))
                self._table.setItem(row, 1, QTableWidgetItem(str(item.get("pid",""))))
                self._table.setItem(row, 2, QTableWidgetItem(item.get("proc","")))

    def _filter(self, text: str):
        text = text.lower()
        filtered = [d for d in self._data if text in d["name"].lower()]
        self._build_table(filtered)

    def _accept_selection(self):
        row = self._table.currentRow()
        if row < 0:
            return
        name_item = self._table.item(row, 0 if self._mode != "both" else 1)
        if name_item:
            self.selected_value = name_item.text()
        self.accept()


# ─────────────────── 窗口类名选择对话框 ───────────────────

class WindowClassListDialog(QDialog):
    """
    弹出所有可见窗口列表，显示 窗口标题 / 类名 / 进程名，
    用户点选后将 class_name 返回。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_class = ""
        self.selected_title = ""
        self.selected_process = ""
        self.setWindowTitle("选择窗口类名")
        self.setMinimumSize(680, 420)
        self.setModal(True)
        self._all_data = []
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        hint = QLabel("选择目标窗口后点击确定，类名将被自动填入。标题和进程名也可一并回填。")
        hint.setStyleSheet("color: #aaa; font-size: 12px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        search_row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("搜索标题 / 类名 / 进程名...")
        self._search.textChanged.connect(self._filter)
        search_row.addWidget(self._search)
        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("btn_flat")
        refresh_btn.setFixedWidth(52)
        refresh_btn.clicked.connect(self._refresh)
        search_row.addWidget(refresh_btn)
        layout.addLayout(search_row)

        self._table = QTableWidget()
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["窗口标题", "窗口类名", "进程名"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.doubleClicked.connect(self._accept_selection)
        layout.addWidget(self._table)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._accept_selection)
        btns.rejected.connect(self.reject)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("确定")
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        layout.addWidget(btns)

    def _refresh(self):
        import ctypes, ctypes.wintypes
        user32 = ctypes.windll.user32
        EnumWindowsCB = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.LPARAM)
        wins = []

        def _cb(hwnd, _):
            if not user32.IsWindowVisible(hwnd):
                return True
            # 标题
            title_buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, title_buf, 256)
            title = title_buf.value.strip()
            if not title:
                return True
            # 类名
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buf, 256)
            class_name = cls_buf.value.strip()
            # 进程名
            pid = ctypes.wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            proc_name = ""
            try:
                import psutil as _ps
                proc_name = _ps.Process(pid.value).name()
            except Exception:
                pass
            wins.append({
                "title": title, "class_name": class_name, "proc": proc_name
            })
            return True

        user32.EnumWindows(EnumWindowsCB(_cb), 0)
        self._all_data = wins
        self._build_table(wins)

    def _build_table(self, data):
        self._table.setRowCount(len(data))
        for row, item in enumerate(data):
            self._table.setItem(row, 0, QTableWidgetItem(item["title"]))
            self._table.setItem(row, 1, QTableWidgetItem(item["class_name"]))
            self._table.setItem(row, 2, QTableWidgetItem(item["proc"]))

    def _filter(self, text: str):
        text = text.lower()
        filtered = [d for d in self._all_data
                    if text in d["title"].lower()
                    or text in d["class_name"].lower()
                    or text in d["proc"].lower()]
        self._build_table(filtered)

    def _accept_selection(self):
        row = self._table.currentRow()
        if row < 0:
            return
        item_cls = self._table.item(row, 1)
        item_title = self._table.item(row, 0)
        item_proc = self._table.item(row, 2)
        if item_cls:
            self.selected_class = item_cls.text()
        if item_title:
            self.selected_title = item_title.text()
        if item_proc:
            self.selected_process = item_proc.text()
        self.accept()


# ─────────────────── 坐标选点控件 ───────────────────

class CoordPickerEdit(QWidget):
    """
    坐标选点控件：X输入框 + Y输入框 + 模式切换(像素/百分比) + [选点] 按钮
    点击选点：最小化主窗口，实时显示鼠标坐标，
    用户移动到目标位置后按快捷键（默认 F9）确认。

    数据格式：{"x": <值>, "y": <值>, "mode": "pixel"/"percent"}
    - pixel 模式：x/y 为整数像素坐标
    - percent 模式：x/y 为 0.0~100.0 的百分比（保留2位小数），运行时按屏幕分辨率换算
    """

    # 默认确认快捷键（可由外部覆盖）
    pick_hotkey: str = "F9"

    def __init__(self, default_x=0, default_y=0, default_mode="pixel", parent=None):
        super().__init__(parent)
        self._mode = default_mode  # "pixel" or "percent"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 模式切换按钮（像素 ⇆ 百分比）
        self._mode_btn = QPushButton()
        self._mode_btn.setObjectName("btn_flat")
        self._mode_btn.setFixedWidth(60)
        self._mode_btn.setToolTip("切换定位模式：像素坐标（绝对）或百分比（相对屏幕尺寸，跨分辨率兼容）")
        self._mode_btn.clicked.connect(self._toggle_mode)
        layout.addWidget(self._mode_btn)

        lx = QLabel("X:")
        lx.setFixedWidth(16)
        layout.addWidget(lx)
        self._x_edit = QLineEdit(str(default_x))
        self._x_edit.setFixedWidth(64)
        layout.addWidget(self._x_edit)

        ly = QLabel("Y:")
        ly.setFixedWidth(16)
        layout.addWidget(ly)
        self._y_edit = QLineEdit(str(default_y))
        self._y_edit.setFixedWidth(64)
        layout.addWidget(self._y_edit)

        self._btn = QPushButton("📍 选点")
        self._btn.setObjectName("btn_flat")
        self._btn.setMinimumWidth(72)
        self._btn.clicked.connect(self._start_pick)
        layout.addWidget(self._btn)
        layout.addStretch()

        self._update_mode_ui()

    def _update_mode_ui(self):
        if self._mode == "percent":
            self._mode_btn.setText("百分比")
            self._mode_btn.setStyleSheet("color: #A6E3A1; font-size: 11px;")
            self._x_edit.setPlaceholderText("0.00 ~ 100.00")
            self._y_edit.setPlaceholderText("0.00 ~ 100.00")
            self._btn.setToolTip(f"选点后自动换算为屏幕百分比，按 {self.pick_hotkey} 确认")
        else:
            self._mode_btn.setText("像素")
            self._mode_btn.setStyleSheet("color: #89B4FA; font-size: 11px;")
            self._x_edit.setPlaceholderText("像素X")
            self._y_edit.setPlaceholderText("像素Y")
            self._btn.setToolTip(f"选点后记录像素坐标，按 {self.pick_hotkey} 确认")

    def _toggle_mode(self):
        """切换模式时，尝试换算现有值"""
        try:
            import ctypes
            sw = ctypes.windll.user32.GetSystemMetrics(0)
            sh = ctypes.windll.user32.GetSystemMetrics(1)
        except Exception:
            sw, sh = 1920, 1080

        old_x = self._x_edit.text().strip()
        old_y = self._y_edit.text().strip()
        try:
            xv = float(old_x)
            yv = float(old_y)
            if self._mode == "pixel":
                # 像素→百分比
                new_x = f"{xv / sw * 100:.2f}"
                new_y = f"{yv / sh * 100:.2f}"
                self._mode = "percent"
            else:
                # 百分比→像素
                new_x = str(int(xv / 100 * sw))
                new_y = str(int(yv / 100 * sh))
                self._mode = "pixel"
            self._x_edit.setText(new_x)
            self._y_edit.setText(new_y)
        except Exception:
            self._mode = "percent" if self._mode == "pixel" else "pixel"

        self._update_mode_ui()

    def x_value(self):
        """向下兼容，返回 x 的原始字符串（或 int/float）"""
        try:
            t = self._x_edit.text().strip()
            return float(t) if self._mode == "percent" else int(t)
        except Exception:
            return 0

    def y_value(self):
        """向下兼容，返回 y 的原始字符串（或 int/float）"""
        try:
            t = self._y_edit.text().strip()
            return float(t) if self._mode == "percent" else int(t)
        except Exception:
            return 0

    def get_value(self) -> dict:
        """返回含 mode 的完整字典：{"x": <值>, "y": <值>, "mode": "pixel"/"percent"}"""
        return {"x": self.x_value(), "y": self.y_value(), "mode": self._mode}

    def set_value(self, data: dict):
        """从字典恢复值（加载已保存数据时调用）"""
        if not isinstance(data, dict):
            return
        mode = data.get("mode", "pixel")
        self._mode = mode
        xv = data.get("x", 0)
        yv = data.get("y", 0)
        if mode == "percent":
            self._x_edit.setText(f"{float(xv):.2f}")
            self._y_edit.setText(f"{float(yv):.2f}")
        else:
            self._x_edit.setText(str(int(xv)))
            self._y_edit.setText(str(int(yv)))
        self._update_mode_ui()

    def _start_pick(self):
        """
        选点流程：
        - MainWindow（有任务栏图标）：hide() 隐藏
        - BlockEditDialog（模态弹窗，exec() 运行中）：移出屏幕外，不 hide()
          ！重要：hide() 一个正在 exec() 中的 QDialog 会导致 Qt 自动 reject
                  它，从而使"新增功能块"流程提前返回，功能块无法插入。
        - 其他 Tool 窗口（CoordOverlay 除外）：hide()
        """
        import ctypes
        # 屏幕尺寸（用于把窗口移出屏幕外）
        sw = ctypes.windll.user32.GetSystemMetrics(0)
        sh = ctypes.windll.user32.GetSystemMetrics(1)

        self._pick_hidden  = []   # hide() 的窗口，恢复时 show()
        self._pick_exiled  = []   # 移出屏幕的窗口，恢复时移回原位
        # 记录原始位置：{widget: QRect}
        self._pick_exiled_pos = {}

        for w in QApplication.topLevelWidgets():
            if not w.isVisible():
                continue
            if isinstance(w, CoordOverlay):
                continue
            if isinstance(w, QDialog):
                # 模态对话框：移出屏幕外而非 hide，保证 exec() 不被中断
                orig = w.geometry()
                self._pick_exiled.append(w)
                self._pick_exiled_pos[id(w)] = orig
                w.move(sw + 100, sh + 100)
            else:
                # 普通窗口（MainWindow 等）：直接 hide
                self._pick_hidden.append(w)

        # 创建并显示浮窗
        self._overlay = CoordOverlay(hotkey=self.pick_hotkey,
                                     on_confirm=self._on_confirm,
                                     on_cancel=self._on_cancel,
                                     percent_mode=(self._mode == "percent"))
        self._overlay.show()

        # 延迟 120ms 执行隐藏（让 overlay 先完全显示、热键线程已启动）
        hidden  = self._pick_hidden
        exiled  = self._pick_exiled
        expos   = self._pick_exiled_pos
        def _do_hide():
            for w in hidden:
                try:
                    w.hide()
                except Exception:
                    pass
            for w in exiled:
                try:
                    w.move(sw + 100, sh + 100)
                except Exception:
                    pass
        QTimer.singleShot(120, _do_hide)

    def _on_confirm(self, x: int, y: int):
        if self._mode == "percent":
            try:
                import ctypes
                sw = ctypes.windll.user32.GetSystemMetrics(0)
                sh = ctypes.windll.user32.GetSystemMetrics(1)
                self._x_edit.setText(f"{x / sw * 100:.2f}")
                self._y_edit.setText(f"{y / sh * 100:.2f}")
            except Exception:
                self._x_edit.setText(str(x))
                self._y_edit.setText(str(y))
        else:
            self._x_edit.setText(str(x))
            self._y_edit.setText(str(y))
        self._restore_main()

    def _on_cancel(self):
        self._restore_main()

    def _restore_main(self):
        hidden = getattr(self, '_pick_hidden', [])
        exiled = getattr(self, '_pick_exiled', [])
        expos  = getattr(self, '_pick_exiled_pos', {})

        def _do_restore():
            # 恢复 hide() 的普通窗口
            for w in hidden:
                try:
                    w.show()
                except Exception:
                    pass
            # 把移出屏幕的对话框移回原位
            for w in exiled:
                try:
                    orig = expos.get(id(w))
                    if orig:
                        w.move(orig.x(), orig.y())
                    w.raise_()
                    w.activateWindow()
                except Exception:
                    pass
        # 延迟 200ms，等 overlay 彻底关闭后再恢复，避免竞争崩溃
        QTimer.singleShot(200, _do_restore)






class CoordOverlay(QWidget):
    """
    坐标拾取浮层：始终置顶的小窗口，
    实时显示当前鼠标坐标，按指定快捷键确认。

    热键监听原理：
    - 用独立后台线程用 GetAsyncKeyState 轮询确认键（F9）和 ESC。
    - 不使用 RegisterHotKey，避免注册失败/冲突/消息队列未创建等问题。
    - 窗口最小化/失焦后同样有效，50Hz 轮询 CPU 占用极低。
    - 检测到热键后通过 pyqtSignal 安全回调到 Qt 主线程（线程安全）。
    """

    # 类级别信号：后台线程 → 主线程（"confirm" 或 "cancel"）
    _hotkey_signal = pyqtSignal(str)

    def __init__(self, hotkey: str = "F9", on_confirm=None, on_cancel=None,
                 percent_mode: bool = False, parent=None):
        super().__init__(parent, Qt.WindowType.WindowStaysOnTopHint |
                         Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.Tool)
        self._hotkey      = hotkey.upper()
        self._on_confirm  = on_confirm
        self._on_cancel   = on_cancel
        self._closed      = False
        self._percent_mode = percent_mode

        # 连接信号到主线程槽（线程安全）
        self._hotkey_signal.connect(self._on_hotkey_action)

        # 获取屏幕尺寸（用于百分比换算）
        try:
            import ctypes
            self._sw = ctypes.windll.user32.GetSystemMetrics(0)
            self._sh = ctypes.windll.user32.GetSystemMetrics(1)
        except Exception:
            self._sw, self._sh = 1920, 1080

        h = 100 if percent_mode else 80
        self.setFixedSize(260, h)
        self.setStyleSheet("""
            QWidget { background: #1E1E2E; border: 2px solid #89B4FA;
                      border-radius: 10px; }
            QLabel  { color: #CDD6F4; font-size: 13px; border: none; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        self._coord_lbl = QLabel("X: —   Y: —")
        self._coord_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._coord_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #89B4FA;")
        layout.addWidget(self._coord_lbl)

        if percent_mode:
            self._pct_lbl = QLabel("—% , —%")
            self._pct_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._pct_lbl.setStyleSheet("font-size: 13px; color: #A6E3A1;")
            layout.addWidget(self._pct_lbl)
        else:
            self._pct_lbl = None

        hint = QLabel(f"移动鼠标到目标，按 {hotkey} 确认，ESC 取消")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: #6C7086; font-size: 11px;")
        layout.addWidget(hint)

        # 居中显示在屏幕底部
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() // 2 - 130, screen.height() - 130)

        self._cur_x = 0
        self._cur_y = 0

        # ── 主线程定时器：仅轮询鼠标坐标 ──
        self._coord_timer = QTimer(self)
        self._coord_timer.timeout.connect(self._update_coord)
        self._coord_timer.start(30)

        # ── 后台线程：Win32 RegisterHotKey + GetMessage 消息循环 ──
        import threading
        self._stop_event = threading.Event()
        self._hotkey_thread = threading.Thread(
            target=self._hotkey_loop,
            daemon=True,
            name="coord-hotkey"
        )
        self._hotkey_thread.start()

    # ── 坐标轮询（主线程）────────────────────────────

    def _update_coord(self):
        import ctypes, ctypes.wintypes
        pt = ctypes.wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        self._cur_x = pt.x
        self._cur_y = pt.y
        self._coord_lbl.setText(f"X: {pt.x}   Y: {pt.y}")
        if self._pct_lbl is not None:
            px = pt.x / self._sw * 100
            py = pt.y / self._sh * 100
            self._pct_lbl.setText(f"{px:.1f}% , {py:.1f}%")

    # ── 热键监听（后台线程）─────────────────────────
    # RegisterHotKey 的消息必须在注册它的同一线程里用 GetMessage 取，
    # 否则永远收不到 WM_HOTKEY。

    @staticmethod
    def _parse_vk(hk_str: str):
        """热键字符串 → (modifiers, vk_code)，支持 F1-F24 / 修饰键+字母"""
        import ctypes
        MOD_ALT   = 0x0001
        MOD_CTRL  = 0x0002
        MOD_SHIFT = 0x0004
        parts = [p.strip().upper() for p in hk_str.replace("+", " ").split()]
        mods, vk = 0, 0
        for part in parts:
            if part in ("CTRL", "CONTROL"):
                mods |= MOD_CTRL
            elif part == "ALT":
                mods |= MOD_ALT
            elif part == "SHIFT":
                mods |= MOD_SHIFT
            elif part.startswith("F") and part[1:].isdigit():
                fnum = int(part[1:])
                if 1 <= fnum <= 24:
                    vk = 0x6F + fnum   # VK_F1=0x70
            elif len(part) == 1:
                vk = ctypes.windll.user32.VkKeyScanW(ord(part)) & 0xFF
        return mods, vk

    def _hotkey_loop(self):
        """
        后台线程：用 Windows 低级键盘钩子（WH_KEYBOARD_LL）监听热键。

        关键注意事项：
        1. WH_KEYBOARD_LL 是系统级钩子，hMod 必须为 NULL，dwThreadId 必须为 0
        2. 钩子回调必须在安装钩子的线程的消息循环中被「抽取」，
           否则 Windows 会在约 300ms 内超时并自动移除钩子
        3. 因此本线程用 GetMessage 阻塞消息循环（而不是 PeekMessage+sleep），
           确保每个钩子回调都被及时处理
        4. 退出时发 WM_QUIT 给本线程，GetMessage 返回 False 后自然退出循环
        """
        import ctypes, ctypes.wintypes, time

        user32   = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        WH_KEYBOARD_LL = 13
        WM_KEYDOWN     = 0x0100
        WM_SYSKEYDOWN  = 0x0104
        WM_QUIT        = 0x0012
        VK_ESCAPE      = 0x1B

        _, vk_confirm = self._parse_vk(self._hotkey)

        # 先强制创建本线程的消息队列（Windows 懒初始化，必须先调用一次消息相关函数）
        msg = ctypes.wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)  # PM_NOREMOVE=0，仅创建队列

        # 等启动时的按键余震消散
        time.sleep(0.15)

        # ── 钩子回调 ──────────────────────────────────────────────────────────
        HOOKPROC = ctypes.CFUNCTYPE(
            ctypes.c_long,
            ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM
        )

        result_sent  = [False]
        my_thread_id = [kernel32.GetCurrentThreadId()]

        def low_level_handler(nCode, wParam, lParam):
            if nCode >= 0 and not result_sent[0] and not self._stop_event.is_set():
                if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    # KBDLLHOOKSTRUCT.vkCode 是第一个 DWORD
                    vk = ctypes.cast(lParam, ctypes.POINTER(ctypes.wintypes.DWORD))[0]
                    action = None
                    if vk_confirm and vk == vk_confirm:
                        action = "confirm"
                    elif vk == VK_ESCAPE:
                        action = "cancel"
                    if action:
                        result_sent[0] = True
                        try:
                            self._hotkey_signal.emit(action)
                        except RuntimeError:
                            pass
                        # 通知消息循环退出
                        user32.PostThreadMessageW(my_thread_id[0], WM_QUIT, 0, 0)
            # 必须调用 CallNextHookEx 保证钩子链正常传递
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        hook_proc = HOOKPROC(low_level_handler)

        # hMod=NULL, dwThreadId=0 → 全局低级钩子（WH_KEYBOARD_LL 规定必须这样）
        hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, hook_proc, None, 0)

        if not hook:
            # 钩子安装失败（极少见），回退到 GetAsyncKeyState 轮询
            GetAsyncKeyState = user32.GetAsyncKeyState
            GetAsyncKeyState(vk_confirm or 0x78)  # 清 bit0
            GetAsyncKeyState(VK_ESCAPE)
            while not self._stop_event.is_set():
                if vk_confirm and (GetAsyncKeyState(vk_confirm) & 0x0001):
                    try:
                        self._hotkey_signal.emit("confirm")
                    except RuntimeError:
                        pass
                    break
                if GetAsyncKeyState(VK_ESCAPE) & 0x0001:
                    try:
                        self._hotkey_signal.emit("cancel")
                    except RuntimeError:
                        pass
                    break
                time.sleep(0.005)
            return

        # ── 消息循环 ─────────────────────────────────────────────────────────
        # 用 GetMessage 阻塞等待，每次有消息（包括钩子驱动的消息）就立即处理。
        # 这保证钩子回调永远不会因为"消息循环太慢"被 Windows 超时移除。
        while not self._stop_event.is_set() and not result_sent[0]:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret == 0 or ret == -1:   # WM_QUIT 或错误
                break
            # WM_QUIT 的 message 值为 0x0012，GetMessage 返回 0 时表示收到 WM_QUIT
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        user32.UnhookWindowsHookEx(hook)

    def _stop_hotkey_thread(self):
        """通知后台钩子线程退出"""
        self._stop_event.set()
        # 向热键线程投递 WM_QUIT，让其消息循环退出
        t = getattr(self, '_hotkey_thread', None)
        if t is not None and t.is_alive():
            tid = t.ident
            if tid:
                try:
                    import ctypes
                    ctypes.windll.user32.PostThreadMessageW(tid, 0x0012, 0, 0)
                except Exception:
                    pass

    # ── 热键信号槽（主线程）───────────────────────────

    def _on_hotkey_action(self, action: str):
        """主线程槽：处理后台线程发来的热键动作"""
        if action == "confirm":
            self._do_confirm()
        elif action == "cancel":
            self._do_cancel()

    # ── 确认 / 取消（主线程调用）────────────────────

    def _do_confirm(self):
        if self._closed:
            return
        self._closed = True
        self._coord_timer.stop()
        self._stop_hotkey_thread()
        self.close()
        if self._on_confirm:
            self._on_confirm(self._cur_x, self._cur_y)

    def _do_cancel(self):
        if self._closed:
            return
        self._closed = True
        self._coord_timer.stop()
        self._stop_hotkey_thread()
        self.close()
        if self._on_cancel:
            self._on_cancel()

    # ── Qt 兜底（窗口有焦点时）───────────────────────

    def keyPressEvent(self, event):
        from PyQt6.QtCore import Qt as _Qt
        key      = event.key()
        key_text = event.text().upper()
        if key == _Qt.Key.Key_Escape:
            self._do_cancel()
            return
        hk        = self._hotkey
        confirmed = False
        if hk.startswith("F") and hk[1:].isdigit():
            fnum = int(hk[1:])
            fkey = getattr(_Qt.Key, f"Key_F{fnum}", None)
            if fkey and key == fkey:
                confirmed = True
        elif len(hk) == 1 and key_text == hk:
            confirmed = True
        if confirmed:
            self._do_confirm()

    def closeEvent(self, event):
        self._coord_timer.stop()
        self._stop_hotkey_thread()
        super().closeEvent(event)


# ─────────────────── 任务选择器控件 ───────────────────

class TaskPickerEdit(QWidget):
    """
    任务选择控件：显示任务名的下拉框
    需要外部通过 set_tasks() 传入任务列表
    """

    def __init__(self, default: str = "", parent=None):
        super().__init__(parent)
        self._default = default
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._combo = QComboBox()
        self._combo.setEditable(True)
        self._combo.setPlaceholderText("选择目标任务")
        layout.addWidget(self._combo)

        self._tasks = []  # List[Task]
        self._task_id_map = {}  # display_name -> task_id

    def set_tasks(self, tasks):
        """外部传入 Task 列表"""
        self._tasks = tasks
        self._task_id_map = {}
        current_id = self._default

        self._combo.clear()
        for t in tasks:
            display = t.name
            self._combo.addItem(display, t.id)
            self._task_id_map[display] = t.id

        # 尝试恢复默认值
        if current_id:
            for i in range(self._combo.count()):
                if self._combo.itemData(i) == current_id:
                    self._combo.setCurrentIndex(i)
                    return
            # 没找到 ID，尝试按名称
            for i in range(self._combo.count()):
                if self._combo.itemText(i) == current_id:
                    self._combo.setCurrentIndex(i)
                    return
            self._combo.setCurrentText(current_id)

    def value(self) -> str:
        """返回所选任务的 ID（若找不到则返回显示文字）"""
        data = self._combo.currentData()
        if data:
            return data
        return self._combo.currentText()

    def setText(self, t: str):
        self._default = t
        # 尝试按 ID 设置
        for i in range(self._combo.count()):
            if self._combo.itemData(i) == t or self._combo.itemText(i) == t:
                self._combo.setCurrentIndex(i)
                return
        self._combo.setCurrentText(t)

class BlockCard(QFrame):
    """可视化功能块卡片，支持上移/下移排序和折叠"""

    delete_requested  = pyqtSignal(object)
    edit_requested    = pyqtSignal(object)
    copy_requested    = pyqtSignal(object)   # 新增：复制
    move_up           = pyqtSignal(object)
    move_down         = pyqtSignal(object)
    toggle_collapse   = pyqtSignal(object)   # 仅 loop/group 发出
    add_elif          = pyqtSignal(object)   # if_block 专用：添加 elif 分支
    toggle_else       = pyqtSignal(object)   # if_block 专用：切换 else 分支
    run_from_here     = pyqtSignal(object)   # 从此处开始运行
    cut_requested     = pyqtSignal(object)   # 剪切
    context_menu_requested = pyqtSignal(object, object)  # (card, QPoint)
    # 单击选中信号 (card, shift_held)
    card_clicked      = pyqtSignal(object, bool)
    # 双击编辑信号
    card_double_clicked = pyqtSignal(object)

    def __init__(self, block: Block, depth: int = 0,
                 collapsed: bool = False, parent=None):
        super().__init__(parent)
        self.block     = block
        self.depth     = depth
        self.collapsed = collapsed
        self._selected = False   # 多选状态
        self._drag_start_pos = None
        self._dragged = False              # 本次 press 是否已触发拖拽
        self._pending_click_shift = False  # 本次 press 时 shift 是否按下
        self._build_ui()
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(
            lambda pos: self.context_menu_requested.emit(self, self.mapToGlobal(pos))
        )

    @staticmethod
    def _is_dark() -> bool:
        """返回当前是否为深色主题（由全局 _DARK_MODE 决定，main_window 切换主题时更新）"""
        return is_theme_dark()

    def set_selected(self, selected: bool):
        """设置多选选中状态，直接切换高亮 QSS，不重建 UI"""
        if self._selected == selected:
            return
        self._selected = selected
        self._apply_selection_style()

    def _apply_selection_style(self):
        """根据 _selected 状态切换卡片高亮边框（直接修改 QSS，不重建 UI）"""
        bt = self.block.block_type
        is_marker = bt in (_OPEN_MARKERS | _CLOSE_MARKERS | _IF_BRANCH_MARKERS)
        obj = self.objectName()   # "block_card"
        depth = self.depth
        indent = depth * 24

        dark = self._is_dark()

        if self._selected:
            # ── 选中状态：醒目蓝色多边框 ──
            sel_border   = "#89B4FA"  # 蓝色选中边
            sel_bg_dark  = "#1e3a5f"  # 深色主题选中背景
            sel_bg_light = "#dbeafe"  # 浅色主题选中背景
            sel_bg = sel_bg_dark if dark else sel_bg_light

            if is_marker:
                self.setStyleSheet(f"""
                    #{obj} {{
                        background: {sel_bg};
                        border: 2px solid {sel_border};
                        border-radius: 6px;
                        margin: 3px {indent}px 3px {indent}px;
                    }}
                """)
            else:
                info  = BLOCK_TYPES.get(bt, {})
                color = info.get("color", "#888")
                if bt in ("group", "group_end"):
                    color = self.block.params.get("color", color)
                if bt in ("if_block", "elif_block", "else_block", "if_end"):
                    color = "#FF9A3C"
                self.setStyleSheet(f"""
                    #{obj} {{
                        background: {sel_bg};
                        border: 2px solid {sel_border};
                        border-left: 5px solid {color};
                        border-radius: 8px;
                        margin: 2px {indent}px 2px {indent + 2}px;
                    }}
                """)
        else:
            # ── 取消选中：恢复基础样式（从 _base_stylesheet 还原）──
            if hasattr(self, '_base_stylesheet'):
                self.setStyleSheet(self._base_stylesheet)
            else:
                self._build_ui()

    def mousePressEvent(self, event):
        from PyQt6.QtCore import Qt as _Qt
        if event.button() == _Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.position().toPoint()
            self._pending_click_shift = bool(event.modifiers() & _Qt.KeyboardModifier.ShiftModifier)
            self._dragged = False  # 本次按下是否已触发拖拽
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        from PyQt6.QtCore import Qt as _Qt
        if event.button() == _Qt.MouseButton.LeftButton:
            # 双击时取消掉 press 发起的 pending click
            self._drag_start_pos = None
            self._dragged = True  # 阻止 release 再发 click
            self.card_double_clicked.emit(self)
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event):
        from PyQt6.QtCore import Qt as _Qt
        from PyQt6.QtGui import QDrag
        from PyQt6.QtCore import QMimeData
        if (self._drag_start_pos is not None and
                event.buttons() & _Qt.MouseButton.LeftButton):
            dist = (event.position().toPoint() - self._drag_start_pos).manhattanLength()
            if dist > 10:
                self._dragged = True   # 标记已拖拽，release 不再触发 click
                drag = QDrag(self)
                mime = QMimeData()
                mime.setText(f"block_drag:{self.block.id}")
                drag.setMimeData(mime)
                drag.exec(_Qt.DropAction.MoveAction)
                self._drag_start_pos = None
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        from PyQt6.QtCore import Qt as _Qt
        if (event.button() == _Qt.MouseButton.LeftButton
                and not getattr(self, '_dragged', False)
                and self._drag_start_pos is not None):
            # 真正的单击（没有变成拖拽）才发出选中信号
            self.card_clicked.emit(self, getattr(self, '_pending_click_shift', False))
        self._drag_start_pos = None
        self._dragged = False
        super().mouseReleaseEvent(event)

    def _build_ui(self):
        info  = BLOCK_TYPES.get(self.block.block_type, {})
        color = info.get("color", "#888")
        label = info.get("label", self.block.block_type)
        bt    = self.block.block_type

        is_open_marker  = bt in _OPEN_MARKERS
        is_close_marker = bt in _CLOSE_MARKERS
        is_branch       = bt in _IF_BRANCH_MARKERS
        is_marker       = is_open_marker or is_close_marker or is_branch

        if bt in ("group", "group_end"):
            color = self.block.params.get("color", color)

        # if系列用醒目橙色
        if bt in ("if_block", "elif_block", "else_block", "if_end"):
            color = "#FF9A3C"

        # 根据当前主题动态选择背景/边框颜色
        dark = self._is_dark()
        if dark:
            card_bg_marker = "#1E1E2E"
            card_bg_block  = "#2A2A3E"
            card_bg_hover  = "#2E2E42"
            card_border    = "#45475A"
            btn_fg         = "#585B70"
            btn_hover_bg   = "#45475A"
            btn_hover_fg   = "#CDD6F4"
            lbl_disabled   = "#585B70"
            lbl_collapsed  = "#6C7086"
            lbl_constraint = "#89B4FA"
        else:
            card_bg_marker = "#FFFFFF"
            card_bg_block  = "#F5F5F5"
            card_bg_hover  = "#EAEAF5"
            card_border    = "#D0D0D0"
            btn_fg         = "#9E9E9E"
            btn_hover_bg   = "#E0E0E0"
            btn_hover_fg   = "#212121"
            lbl_disabled   = "#BDBDBD"
            lbl_collapsed  = "#9E9E9E"
            lbl_constraint = "#1E88E5"

        self.setObjectName("block_card")
        indent = self.depth * 24

        if is_marker:
            self.setStyleSheet(f"""
                #block_card {{
                    background: {card_bg_marker};
                    border: 2px solid {color};
                    border-radius: 6px;
                    margin: 3px {indent}px 3px {indent}px;
                }}
            """)
            # elif/else 卡片稍高以容纳删除按钮
            if bt in _IF_BRANCH_MARKERS:
                self.setFixedHeight(44)
            else:
                self.setFixedHeight(40)
        else:
            self.setStyleSheet(f"""
                #block_card {{
                    background: {card_bg_block};
                    border: 1px solid {card_border};
                    border-left: 4px solid {color};
                    border-radius: 8px;
                    margin: 2px {indent}px 2px {indent + 2}px;
                }}
                #block_card:hover {{
                    border-color: {color};
                    background: {card_bg_hover};
                }}
            """)
            self.setFixedHeight(52)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 8, 4)
        layout.setSpacing(8)

        # ── 多选复选框（最左侧，默认隐藏，多选模式时显示）──
        self._select_cb = QCheckBox()
        self._select_cb.setFixedSize(16, 16)
        self._select_cb.setVisible(False)
        self._select_cb.stateChanged.connect(
            lambda state: self.context_menu_requested.emit(
                self, self.mapToGlobal(self.rect().center())
            ) if False else None  # 触发父级多选逻辑（通过 _select_cb.isChecked() 判断）
        )
        layout.addWidget(self._select_cb)

        # 折叠按钮（仅 loop/group/if_block 开始标记有）
        if is_open_marker:
            collapse_btn = QPushButton("▼" if not self.collapsed else "▶")
            collapse_btn.setFixedSize(20, 20)
            collapse_btn.setStyleSheet(f"""
                QPushButton {{ background: transparent; border: 1px solid {color};
                    border-radius: 4px; color: {color}; font-size: 9px; font-weight: bold; }}
                QPushButton:hover {{ background: {color}33; }}
            """)
            collapse_btn.clicked.connect(lambda _, s=self.toggle_collapse: s.emit(self))
            layout.addWidget(collapse_btn)
        else:
            layout.addSpacing(24)  # 对齐折叠按钮占位，不插入可见 widget

        # 图标
        icon_text = info.get("icon", "◆")
        icon_lbl = QLabel(icon_text)
        icon_lbl.setFixedWidth(32)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet(f"color: {color}; font-size: 15px; font-weight: bold;")
        layout.addWidget(icon_lbl)

        # 内容
        content = QVBoxLayout()
        content.setSpacing(1)
        title_row = QHBoxLayout()
        title_row.setSpacing(6)

        if is_marker:
            if bt in ("group", "group_end"):
                title_text = self.block.params.get("title", label)
                show_label = f"{'[ ' if bt=='group' else '[ /'}{title_text} ]"
            elif bt == "if_block":
                ctype  = self.block.params.get("condition_type", "")
                target = self.block.params.get("target", "")
                neg    = "非 " if self.block.params.get("negate", False) else ""
                clabel = _ctype_to_label(bt, ctype)
                show_label = f"[ 如果  {neg}{clabel}  {target} ]" if target else f"[ 如果  {neg}{clabel} ]"
            elif bt == "elif_block":
                ctype  = self.block.params.get("condition_type", "")
                target = self.block.params.get("target", "")
                neg    = "非 " if self.block.params.get("negate", False) else ""
                clabel = _ctype_to_label(bt, ctype)
                show_label = f"[ 否则如果  {neg}{clabel}  {target} ]" if target else f"[ 否则如果  {neg}{clabel} ]"
            elif bt == "else_block":
                show_label = "[ 否则 ]"
            elif bt == "if_end":
                show_label = "[ 结束判断 ]"
            else:
                show_label = f"{'[ ' if is_open_marker else '[ /'}{label} ]"
            name_lbl = QLabel(show_label)
            name_lbl.setStyleSheet(
                f"color: {color}; font-weight: bold; font-size: 11px; letter-spacing: 1px;"
            )
        else:
            name_lbl = QLabel(label)
            name_lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 12px;")
        title_row.addWidget(name_lbl)

        if not self.block.enabled:
            dis_lbl = QLabel(tr("block.disabled"))
            dis_lbl.setStyleSheet(f"color: {lbl_disabled}; font-size: 11px;")
            title_row.addWidget(dis_lbl)
        if self.collapsed and is_open_marker:
            col_lbl = QLabel("[已折叠]")
            col_lbl.setStyleSheet(f"color: {lbl_collapsed}; font-size: 11px;")
            title_row.addWidget(col_lbl)
        # 约束条件指示器
        if getattr(self.block, 'constraints', []):
            n = len(self.block.constraints)
            cst_lbl = QLabel(f"🔒×{n}")
            cst_lbl.setToolTip(f"有 {n} 个约束条件")
            cst_lbl.setStyleSheet(f"color: {lbl_constraint}; font-size: 10px;")
            title_row.addWidget(cst_lbl)

        title_row.addStretch()

        # ── if_block 专属内嵌操作按钮 ──
        if bt == "if_block":
            _ibtn_style = (
                f"QPushButton {{ background: {card_bg_block}; border: 1px solid #FF9A3C55;"
                " border-radius: 4px; padding: 1px 6px; color: #FF9A3C; font-size: 10px; }"
                "QPushButton:hover { background: #FF9A3C33; border-color: #FF9A3C; }"
            )
            btn_add_elif = QPushButton("＋ELIF")
            btn_add_elif.setFixedHeight(20)
            btn_add_elif.setToolTip("在此 IF 块内添加 ELIF 子判断分支")
            btn_add_elif.setStyleSheet(_ibtn_style)
            btn_add_elif.clicked.connect(lambda _, s=self.add_elif: s.emit(self))
            title_row.addWidget(btn_add_elif)

            # 判断当前是否已有 else 分支——由父控件刷新时通过 set_has_else() 传入
            self._else_active = getattr(self, '_else_active', False)
            btn_else = QPushButton("ELSE ✓" if self._else_active else "ELSE ☐")
            btn_else.setFixedHeight(20)
            btn_else.setToolTip("开启/关闭 ELSE 否则块（与此 IF 绑定）")
            btn_else.setCheckable(True)
            btn_else.setChecked(self._else_active)
            btn_else.setStyleSheet(_ibtn_style)
            btn_else.clicked.connect(lambda _, s=self.toggle_else: s.emit(self))
            title_row.addWidget(btn_else)
            self._btn_else = btn_else  # 保存引用以便外部更新

        # ── elif/else 卡片：右侧显示删除按钮 ──
        elif bt in _IF_BRANCH_MARKERS:
            _dbtn_style = (
                f"QPushButton {{ background: transparent; border: 1px solid {btn_fg};"
                f" border-radius: 4px; padding: 1px 6px; color: {btn_fg}; font-size: 10px; }}"
                "QPushButton:hover { background: #F38BA822; border-color: #F38BA8; color: #F38BA8; }"
            )
            btn_del_branch = QPushButton("✕ 删除")
            btn_del_branch.setFixedHeight(20)
            btn_del_branch.setToolTip("删除此分支块")
            btn_del_branch.setStyleSheet(_dbtn_style)
            btn_del_branch.clicked.connect(lambda _, s=self.delete_requested: s.emit(self))
            title_row.addWidget(btn_del_branch)

        content.addLayout(title_row)

        if not is_marker or bt in ("group", "loop"):
            summary = self._get_param_summary()
            if summary:
                sum_lbl = QLabel(summary)
                sum_lbl.setStyleSheet(f"color: {lbl_collapsed}; font-size: 11px;")
                sum_lbl.setMaximumWidth(400)
                content.addWidget(sum_lbl)
            elif self.block.comment:
                cmt_lbl = QLabel(f"  {self.block.comment}")
                cmt_lbl.setStyleSheet(f"color: {lbl_collapsed}; font-size: 11px; font-style: italic;")
                content.addWidget(cmt_lbl)

        layout.addLayout(content)
        layout.addStretch()

        # 操作按钮
        btn_style = (
            f"QPushButton {{ background: transparent; border: none;"
            f" border-radius: 4px; padding: 2px 4px; color: {btn_fg}; font-size: 12px; }}"
            f"QPushButton:hover {{ background: {btn_hover_bg}; color: {btn_hover_fg}; }}"
        )
        for text, sig in [("↑", self.move_up), ("↓", self.move_down)]:
            btn = QPushButton(text)
            btn.setFixedSize(22, 22)
            btn.setStyleSheet(btn_style)
            btn.clicked.connect(lambda _, s=sig: s.emit(self))
            layout.addWidget(btn)

        # 复制按钮（关闭标记不需要）
        if bt not in _CLOSE_MARKERS:
            btn_copy = QPushButton("⎘")
            btn_copy.setFixedSize(22, 22)
            btn_copy.setToolTip(tr("block.copy_tip"))
            btn_copy.setStyleSheet(btn_style + "QPushButton:hover { color: #89DCEB; }")
            btn_copy.clicked.connect(lambda _, s=self.copy_requested: s.emit(self))
            layout.addWidget(btn_copy)

        if bt not in _CLOSE_MARKERS:
            btn_edit = QPushButton("✎")
            btn_edit.setFixedSize(26, 26)
            btn_edit.setStyleSheet(btn_style)
            btn_edit.clicked.connect(lambda _, s=self.edit_requested: s.emit(self))
            layout.addWidget(btn_edit)

        btn_del = QPushButton("✕")
        btn_del.setFixedSize(26, 26)
        btn_del.setStyleSheet(btn_style + "QPushButton:hover { color: #F38BA8; }")
        btn_del.clicked.connect(lambda _, s=self.delete_requested: s.emit(self))
        layout.addWidget(btn_del)

        # ── 保存基础样式，供 set_selected 切换高亮后恢复使用 ──
        self._base_stylesheet = self.styleSheet()

    def _get_param_summary(self) -> str:
        p  = self.block.params
        bt = self.block.block_type
        parts = []
        if bt == "wait":
            parts.append(f"{p.get('duration','?')} 秒")
        elif bt == "condition":
            parts.append(f"若 [{p.get('condition_type','?')}] {p.get('target','')}")
        elif bt == "loop":
            lt = p.get("loop_type","count")
            if lt == "count":   parts.append(f"循环 {p.get('count','?')} 次")
            elif lt == "infinite": parts.append("无限循环")
            else: parts.append(f"[{lt}] {p.get('target','')}")
        elif bt == "group":
            desc = p.get("description", "")
            if desc: parts.append(desc[:40])
        elif bt in ("launch_app",):
            parts.append(p.get("path","")[-40:])
        elif bt in ("close_window", "wait_window", "close_foreground_window",
                    "activate_window", "set_window_topmost", "move_window"):
            parts.append(p.get("title",""))
        elif bt in ("kill_process", "wait_process"):
            parts.append(p.get("name",""))
        elif bt == "run_command":
            cmd = p.get("command","")
            parts.append(cmd[:50] + ("..." if len(cmd)>50 else ""))
        elif bt in ("copy_file","move_file","delete_file"):
            parts.append(p.get("path","") or p.get("src",""))
        elif bt == "set_variable":
            parts.append(f"{p.get('name','')} = {p.get('value','')}")
        elif bt == "calc_variable":
            parts.append(f"{p.get('name','')} = {p.get('expression','')}")
        elif bt == "notify":
            parts.append(p.get("message",""))
        elif bt == "volume_set":
            parts.append(f"音量 {p.get('level','?')}%")
        elif bt == "shutdown":
            parts.append(p.get("action",""))
        elif bt == "screenshot":
            parts.append(f"[{p.get('mode','save_file')}] {p.get('filename_fmt','')}.{p.get('format','png')}")
        elif bt == "mouse_move":
            pos = p.get('pos', {})
            x = pos.get('x', p.get('x', '?'))
            y = pos.get('y', p.get('y', '?'))
            curve = p.get('curve', 'linear')
            curve_map = {"linear":"线性","ease_in":"缓入","ease_out":"缓出","ease_in_out":"缓入缓出","bezier":"贝塞尔","random":"随机"}
            parts.append(f"移到 ({x}, {y})")
            if curve != "linear":
                parts.append(curve_map.get(curve, curve))
        elif bt == "mouse_click_pos":
            pos = p.get('pos', {})
            x = pos.get('x', p.get('x', '?'))
            y = pos.get('y', p.get('y', '?'))
            parts.append(f"{p.get('button','left')}键 @ ({x},{y})")
        elif bt == "mouse_scroll":
            pos = p.get('pos', {})
            x = pos.get('x', p.get('x', '?'))
            y = pos.get('y', p.get('y', '?'))
            parts.append(f"滚轮 ({x},{y}) x{p.get('amount',3)}")
        elif bt == "mouse_drag":
            fp = p.get('from_pos', {})
            tp = p.get('to_pos', {})
            fx = fp.get('x', p.get('from_x', '?'))
            fy = fp.get('y', p.get('from_y', '?'))
            tx = tp.get('x', p.get('to_x', '?'))
            ty = tp.get('y', p.get('to_y', '?'))
            parts.append(f"({fx},{fy}) → ({tx},{ty})")
            curve = p.get('curve', 'linear')
            curve_map = {"linear":"线性","ease_in":"缓入","ease_out":"缓出","ease_in_out":"缓入缓出","bezier":"贝塞尔","random":"随机"}
            if curve != "linear":
                parts.append(curve_map.get(curve, curve))
        elif bt == "keymouse_macro":
            data = p.get('macro_data', [])
            cnt = len(data) if isinstance(data, list) else 0
            speed = p.get('speed', 1.0)
            repeat = p.get('repeat', 1)
            parts.append(f"{cnt} 事件 x{repeat} 速度x{speed}")
        elif bt == "open_url":
            parts.append(p.get("url","")[:50])
        elif bt == "input_text":
            parts.append(p.get("text","")[:40])
        elif bt == "msgbox":
            parts.append(p.get("text","")[:40])
        elif bt == "play_sound":
            parts.append(p.get("path","")[-40:])
        elif bt == "clipboard":
            if p.get("action") == "get":
                parts.append(f"读取 → {p.get('save_to','')}")
            elif p.get("action") == "set":
                parts.append(f"写入: {p.get('content','')[:30]}")
        elif bt == "get_window_info":
            parts.append(f"{p.get('title','')} -> {p.get('save_to','')}")
        elif bt == "get_ping_latency":
            host    = p.get("host", "8.8.8.8")
            save_to = p.get("save_to", "ping_ms")
            parts.append(f"Ping {host} → {save_to}")
        elif bt == "launch_steam":
            app_id = p.get("app_id", "")
            parts.append(f"AppID: {app_id}" if app_id else "打开 Steam 库")
        elif bt == "launch_app":
            path     = p.get("path", "")
            run_mode = p.get("run_mode", "normal")
            wait     = p.get("wait", False)
            mode_map = {"normal": "", "minimized": " [最小化]", "maximized": " [最大化]", "hidden": " [后台]"}
            label    = os.path.basename(path) if path else "未设置"
            parts.append(f"{label}{mode_map.get(run_mode,'')}" + (" 等待退出" if wait else ""))
        elif bt == "browser_search":
            kw     = p.get("keyword", "")
            engine = p.get("engine", "baidu")
            ENGINE_LABEL = {"baidu": "百度", "google": "Google", "bing": "Bing",
                            "bilibili": "B站", "zhihu": "知乎", "custom": "自定义"}
            parts.append(f"[{ENGINE_LABEL.get(engine, engine)}] {kw[:30]}")
        elif bt == "download_file":
            url = p.get("url", "")
            parts.append(url[:50] + ("..." if len(url) > 50 else ""))
        elif bt == "extract_archive":
            arc = p.get("archive", "")
            parts.append(arc[-40:] if arc else "")
        elif bt == "show_desktop":
            parts.append("切换显示桌面")
        elif bt == "lock_computer":
            parts.append("锁定 Win+L")
        elif bt == "browser_auto":
            task = p.get("task", "")
            provider = p.get("llm_provider", "settings")
            headless = p.get("headless", False)
            close_after = p.get("close_after", True)
            mode = p.get("mode", "ai_run")
            label = (task[:35] + "...") if len(task) > 35 else (task or "未设置任务")
            flags = []
            if mode == "ai_generate":
                flags.append("生成步骤")
            if provider != "settings":
                flags.append(provider)
            if headless:
                flags.append("无头")
            if not close_after:
                flags.append("保留浏览器")
            parts.append(label + (f" [{', '.join(flags)}]" if flags else ""))
        elif bt == "browser_open_url":
            url = p.get("url", "")
            parts.append((url[:50] + "...") if len(url) > 50 else (url or "未设置URL"))
        elif bt == "browser_click":
            sel = p.get("selector", "") or p.get("by_text", "")
            by_text = p.get("by_text", "")
            if by_text:
                parts.append(f"文本: {by_text[:40]}")
            else:
                parts.append(sel[:40] or "未设置选择器")
        elif bt == "browser_type":
            sel = p.get("selector", "")
            text = p.get("text", "")
            parts.append(f"{sel[:20]} ← {text[:25]}" if sel else (text[:40] or "未设置"))
        elif bt == "browser_get_text":
            sel = p.get("selector", "")
            save_to = p.get("save_to", "browser_text")
            parts.append(f"{sel[:30]} → {save_to}" if sel else f"→ {save_to}")
        elif bt == "browser_screenshot":
            path = p.get("save_path", "screenshot.png")
            full = p.get("full_page", False)
            parts.append((path[-40:] if len(path) > 40 else path) + (" [整页]" if full else ""))
        elif bt == "browser_wait_element":
            sel = p.get("selector", "")
            state = p.get("state", "visible")
            state_map = {"visible": "可见", "hidden": "隐藏", "attached": "出现", "detached": "消失"}
            parts.append(f"{sel[:35]} [{state_map.get(state, state)}]" if sel else "未设置选择器")

        # ── 屏幕识别 ──
        elif bt == "screen_find_image":
            img = p.get("image_path", "")
            conf = p.get("confidence", 0.8)
            name = os.path.basename(img) if img else "未选择图片"
            parts.append(f"{name}  精度={conf}")
        elif bt == "screen_click_image":
            img = p.get("image_path", "")
            conf = p.get("confidence", 0.8)
            btn = p.get("button", "left")
            btn_map = {"left": "左键", "right": "右键", "middle": "中键"}
            name = os.path.basename(img) if img else "未选择图片"
            parts.append(f"{name}  {btn_map.get(btn, btn)}  精度={conf}")
        elif bt == "screen_wait_image":
            img = p.get("image_path", "")
            timeout = p.get("timeout", 30)
            name = os.path.basename(img) if img else "未选择图片"
            parts.append(f"{name}  超时={timeout}s")
        elif bt == "screen_screenshot_region":
            region = p.get("region", "")
            save_path = p.get("save_path", "region_shot.png")
            region_str = region if region else "全屏"
            name = os.path.basename(save_path) if save_path else "region_shot.png"
            parts.append(f"区域={region_str} → {name}")

        # ── 窗口控件 ──
        elif bt == "win_find_window":
            title = p.get("title", "")
            save_to = p.get("save_to", "win_handle")
            parts.append(f"{title[:30] if title else '任意窗口'} → {save_to}")
        elif bt == "win_click_control":
            win = p.get("window_title", "")
            ctrl = p.get("control_title", "")
            dbl = p.get("double_click", False)
            parts.append(f"{win[:20]} / {ctrl[:20] if ctrl else '控件'}" + (" [双击]" if dbl else ""))
        elif bt == "win_input_control":
            win = p.get("window_title", "")
            text = p.get("text", "")
            parts.append(f"{win[:20]} ← {text[:25] if text else '(空)'}")
        elif bt == "win_get_control_text":
            win = p.get("window_title", "")
            save_to = p.get("save_to", "ctrl_text")
            parts.append(f"{win[:25]} → {save_to}")
        elif bt == "win_wait_window":
            title = p.get("title", "")
            timeout = p.get("timeout", 30)
            parts.append(f"{title[:30] if title else '任意窗口'}  超时={timeout}s")
        elif bt == "win_close_window":
            title = p.get("title", "")
            force = p.get("force", False)
            parts.append(f"{title[:35] if title else '未设置'}" + (" [强制]" if force else ""))



        elif bt == "hotkey_input":
            key = p.get("key", "enter")
            repeat = p.get("repeat", 1)
            parts.append(f"{key}" + (f" ×{repeat}" if int(repeat) > 1 else ""))
        elif bt == "capslock":
            action_map = {"on": "开启", "off": "关闭", "toggle": "切换", "get": "获取状态"}
            parts.append(action_map.get(p.get("action", "toggle"), "切换"))
        summary = "  ".join(parts)
        # 统一限制长度并加省略号
        MAX_LEN = 55
        if len(summary) > MAX_LEN:
            summary = summary[:MAX_LEN] + "…"
        return summary


# ─────────────────── 块参数编辑对话框 ───────────────────

class BlockEditDialog(QDialog):
    def __init__(self, block: Block, parent=None, all_tasks=None):
        super().__init__(parent)
        self.block = block
        self._all_tasks = all_tasks or []  # List[Task] 用于 task_picker
        info = BLOCK_TYPES.get(block.block_type, {})
        self.setWindowTitle(tr("block.edit_title") + f"{info.get('icon','')} {info.get('label', block.block_type)}")
        self.setMinimumWidth(480)
        self.setModal(True)
        self._widgets = {}
        self._task_picker_widgets = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        self._comment = QLineEdit(self.block.comment)
        self._comment.setPlaceholderText(tr("block.comment_ph"))
        form.addRow(tr("block.comment"), self._comment)

        self._enabled = QCheckBox(tr("block.enabled"))
        self._enabled.setChecked(self.block.enabled)
        form.addRow("", self._enabled)

        layout.addLayout(form)

        params_spec = BLOCK_PARAMS.get(self.block.block_type, {})
        if params_spec:
            pform = QFormLayout()
            pform.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
            pform.setSpacing(8)
            for key, spec in params_spec.items():
                widget = self._make_widget(key, spec)
                pform.addRow(spec["label"] + "：", widget)
                self._widgets[key] = widget
            layout.addLayout(pform)
            # ── 如果有 condition_type + condition_target 联动，绑定刷新 ──
            if "condition_type" in self._widgets and "target" in self._widgets:
                ctype_w  = self._widgets["condition_type"]
                target_w = self._widgets["target"]
                if isinstance(target_w, ConditionTargetWidget):
                    # 初始化时刷新一次
                    target_w.update_condition_type(ctype_w.currentData() or ctype_w.currentText())
                    # 绑定下拉变化
                    ctype_w.currentIndexChanged.connect(
                        lambda _: target_w.update_condition_type(
                            ctype_w.currentData() or ctype_w.currentText()
                        )
                    )

        # ── 约束条件区域 ──
        from .constraint_editor import ConstraintListWidget
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #313244; margin: 4px 0;")
        layout.addWidget(sep)
        self._constraint_widget = ConstraintListWidget(
            list(self.block.constraints), self
        )
        layout.addWidget(self._constraint_widget)

        # 为所有 task_picker 控件注入任务列表
        for tw in self._task_picker_widgets:
            tw.set_tasks(self._all_tasks)

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
        default = self.block.params.get(key, spec.get("default", ""))
        ph      = spec.get("placeholder", "")

        if ptype == "hotkey_input":
            w = HotkeyEditWidget(str(default))
            return w
        elif ptype == "window_picker":
            # ── win_click_offset + win_click_control/win_input_control 等控件块 ──
            # 所有含 window_title 的窗口控件块都注册 on_picked 回调，实现一键填所有字段
            _ctrl_win_block_types = {
                "win_click_offset", "win_click_control", "win_input_control",
                "win_get_control_text", "win_wait_control", "win_find_control",
            }
            if self.block.block_type in _ctrl_win_block_types and key == "window_title":
                row = QWidget()
                hl = QHBoxLayout(row)
                hl.setContentsMargins(0, 0, 0, 0)
                hl.setSpacing(4)
                w = WindowPickerEdit(str(default))
                w.setObjectName(f"_win_picker_{key}")

                # 回调：选窗口后自动回填 class_name / process_name（以及偏移点按钮的特殊逻辑）
                def _on_win_picked_common(title, class_name, process_name, _w=w):
                    cn_widget = self._widgets.get("class_name")
                    pn_widget = self._widgets.get("process_name")
                    if cn_widget is not None and class_name:
                        if hasattr(cn_widget, "_line_edit"):
                            cn_widget._line_edit.setText(class_name)
                        elif hasattr(cn_widget, "setText"):
                            cn_widget.setText(class_name)
                        elif hasattr(cn_widget, "_edit"):
                            cn_widget._edit.setText(class_name)
                        else:
                            from PyQt6.QtWidgets import QLineEdit as _QLE2
                            _le = cn_widget.findChild(_QLE2)
                            if _le:
                                _le.setText(class_name)
                    if pn_widget is not None and process_name:
                        if hasattr(pn_widget, "_line_edit"):
                            pn_widget._line_edit.setText(process_name)
                        elif hasattr(pn_widget, "setText"):
                            pn_widget.setText(process_name)
                        elif hasattr(pn_widget, "_edit"):
                            pn_widget._edit.setText(process_name)
                        else:
                            from PyQt6.QtWidgets import QLineEdit as _QLE2
                            _le = pn_widget.findChild(_QLE2)
                            if _le:
                                _le.setText(process_name)
                w.on_picked = _on_win_picked_common

                if self.block.block_type == "win_click_offset":
                    # win_click_offset 还额外需要"选偏移点"按钮
                    btn = QPushButton("选偏移点")
                    btn.setObjectName("btn_flat")
                    btn.setMinimumWidth(72)
                    btn.setToolTip("在目标窗口上点击一个位置，自动计算相对窗口左上角的偏移坐标")
                    btn.clicked.connect(lambda checked=False, wp=w: self._pick_window_offset(wp))
                    hl.addWidget(w)
                    hl.addWidget(btn)
                else:
                    hl.addWidget(w)
                return row
            w = WindowPickerEdit(str(default))
            return w
        elif ptype == "window_class_picker":
            # 窗口类名参数：文本框 + [选择] 按钮（弹出窗口列表让用户选择，同时回填进程名）
            row = QWidget()
            hl = QHBoxLayout(row)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(4)
            edit_cls = QLineEdit(str(default))
            edit_cls.setPlaceholderText(ph or "如 WeChatMainWndForPC, Notepad")
            edit_cls.setObjectName(f"_edit_{key}")
            # 暴露 _line_edit 属性，供外部回填使用
            row._line_edit = edit_cls

            def _do_pick_class(target_edit=edit_cls):
                """弹出窗口列表，让用户选择要识别的窗口，自动填入类名，并回填进程名"""
                try:
                    dlg = WindowClassListDialog(self)
                except Exception as e:
                    QMessageBox.warning(self, "错误", f"无法打开窗口选择器：{e}")
                    return
                if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_class:
                    target_edit.setText(dlg.selected_class)
                    # 同时尝试回填进程名字段（如果同一表单里有 process_name 字段）
                    if dlg.selected_process:
                        pn_widget = self._widgets.get("process_name")
                        if pn_widget is not None:
                            if hasattr(pn_widget, "_line_edit"):
                                pn_widget._line_edit.setText(dlg.selected_process)
                            elif hasattr(pn_widget, "setText"):
                                pn_widget.setText(dlg.selected_process)
                            elif hasattr(pn_widget, "_edit"):
                                pn_widget._edit.setText(dlg.selected_process)
                    # 也回填窗口标题字段（如果同一表单里有 window_title 字段且当前为空）
                    if dlg.selected_title:
                        wt_widget = self._widgets.get("window_title")
                        if wt_widget is not None:
                            cur_title = ""
                            if hasattr(wt_widget, "text"):
                                cur_title = wt_widget.text().strip()
                            elif hasattr(wt_widget, "_edit"):
                                cur_title = wt_widget._edit.text().strip()
                            else:
                                from PyQt6.QtWidgets import QLineEdit as _QLE3
                                _le = wt_widget.findChild(_QLE3)
                                if _le:
                                    cur_title = _le.text().strip()
                            # 仅在窗口标题为空时自动填入
                            if not cur_title:
                                if hasattr(wt_widget, "setText"):
                                    wt_widget.setText(dlg.selected_title)
                                elif hasattr(wt_widget, "_edit"):
                                    wt_widget._edit.setText(dlg.selected_title)
                                else:
                                    from PyQt6.QtWidgets import QLineEdit as _QLE3
                                    _le = wt_widget.findChild(_QLE3)
                                    if _le:
                                        _le.setText(dlg.selected_title)

            btn_cls = QPushButton("选择")
            btn_cls.setObjectName("btn_flat")
            btn_cls.setFixedWidth(52)
            btn_cls.setToolTip("弹出窗口列表，点选目标窗口自动识别类名（同时回填进程名）")
            btn_cls.clicked.connect(_do_pick_class)
            hl.addWidget(edit_cls)
            hl.addWidget(btn_cls)
            return row
        elif ptype == "process_picker":
            w = ProcessWindowPickerEdit(str(default), mode="process")
            return w
        elif ptype == "process_window_picker":
            w = ProcessWindowPickerEdit(str(default), mode="both")
            return w
        elif ptype == "coord_picker":
            # default 可能是 {"x": 0, "y": 0} 或 {"x": 0, "y": 0, "mode": "pixel"/"percent"}
            if isinstance(default, dict):
                x    = default.get("x", 0)
                y    = default.get("y", 0)
                mode = default.get("mode", "pixel")
            else:
                x, y, mode = 0, 0, "pixel"
            w = CoordPickerEdit(x, y, mode)
            return w
        elif ptype == "task_picker":
            w = TaskPickerEdit(str(default))
            # 延迟设置任务（等 _tasks 通过 set_all_tasks 传入）
            self._task_picker_widgets = getattr(self, "_task_picker_widgets", [])
            self._task_picker_widgets.append(w)
            return w
        elif ptype == "number_or_var":
            w = QLineEdit(str(default))
            w.setPlaceholderText(ph or "数字或变量名 {{var}}")
            return w
        elif ptype == "number":
            w = FocusDoubleSpinBox()
            w.setRange(-1e9, 1e9)
            w.setValue(float(default) if default else 0)
            return w
        elif ptype == "select":
            w = QComboBox()
            options = spec.get("options", [])
            labels  = spec.get("option_labels", options)  # 若有中文标签则用中文显示
            for i, opt in enumerate(options):
                label = labels[i] if i < len(labels) else opt
                w.addItem(label, userData=opt)  # userData 存储真实 value
            # 根据 default 选中对应项
            for i in range(w.count()):
                if w.itemData(i) == default:
                    w.setCurrentIndex(i)
                    break
            return w
        elif ptype == "bool":
            w = QCheckBox()
            w.setChecked(bool(default))
            return w
        elif ptype == "text_multiline":
            w = QTextEdit()
            w.setPlainText(str(default))
            w.setFixedHeight(80)
            return w
        elif ptype in ("file_picker", "folder_picker"):
            row = QWidget()
            hl  = QHBoxLayout(row)
            hl.setContentsMargins(0,0,0,0); hl.setSpacing(4)
            edit = QLineEdit(str(default)); edit.setObjectName(f"_edit_{key}")
            
            # 为屏幕识别功能块的图片路径添加截图功能
            is_screen_image_param = (self.block.block_type in ["screen_find_image", "screen_click_image", "screen_wait_image"] 
                                     and key == "image_path")
            
            if is_screen_image_param:
                # 添加截图按钮
                btn_screenshot = QPushButton("截图")
                btn_screenshot.setObjectName("btn_flat")
                btn_screenshot.setMinimumWidth(52)
                btn_screenshot.clicked.connect(lambda: self._capture_screenshot(edit))
                hl.addWidget(btn_screenshot)
            
            btn = QPushButton("浏览")
            btn.setObjectName("btn_flat")
            btn.setMinimumWidth(52)
            if ptype == "folder_picker":
                btn.clicked.connect(lambda: self._pick_folder(edit))
            else:
                btn.clicked.connect(lambda: self._pick_file(edit))
            
            hl.addWidget(edit)
            hl.addWidget(btn)
            return row
        elif ptype == "app_launcher_picker":
            placeholder = spec.get("placeholder", "")
            w = AppLauncherPickerWidget(default=str(default), placeholder=placeholder)
            return w
        elif ptype == "time":
            from PyQt6.QtCore import QTime
            w = QTimeEdit()
            try:
                h, m = map(int, str(default).split(":"))
                w.setTime(QTime(h, m))
            except Exception:
                pass
            return w
        elif ptype == "datetime":
            w = QLineEdit(str(default))
            w.setPlaceholderText("格式: 2025-01-01 08:00")
            return w
        elif ptype == "macro_recorder":
            # 键鼠宏录制控件
            w = MacroRecorderWidget(default if isinstance(default, list) else [])
            return w
        elif ptype == "ai_cmd_gen":
            # AI 智能生成命令控件：描述框 + 生成按钮
            container = QWidget()
            vlay = QVBoxLayout(container)
            vlay.setContentsMargins(0, 0, 0, 0)
            vlay.setSpacing(4)

            desc_edit = QLineEdit(str(default))
            desc_edit.setPlaceholderText(spec.get("placeholder", "描述要做什么，点击「生成」按钮自动填入命令"))
            desc_edit.setObjectName(f"_ai_desc_{key}")
            vlay.addWidget(desc_edit)

            gen_btn = QPushButton("🤖 AI 生成命令")
            gen_btn.setObjectName("btn_flat")
            gen_btn.setFixedHeight(28)
            gen_btn.setToolTip("根据描述，使用 AI 生成对应的命令并填入命令框")
            # 绑定生成逻辑（需要获取 shell 类型和 command 控件）
            gen_btn.clicked.connect(lambda _checked, de=desc_edit: self._ai_generate_command(de))
            vlay.addWidget(gen_btn)

            container._desc_edit = desc_edit
            return container
        elif ptype == "condition_target":
            # 动态辅助按钮控件：根据同表单中的 condition_type 下拉变化
            w = ConditionTargetWidget(str(default))
            return w
        elif ptype == "text":
            # 检查是否为窗口控件功能块的窗口标题或控件标题参数
            is_window_control = self.block.block_type in [
                "win_click_control", "win_input_control", "win_get_control_text",
                "win_find_window", "win_wait_window", "win_close_window",
                "win_wait_control", "win_find_control",
            ]
            is_window_title_param = (key in ["window_title", "title"]) and is_window_control
            is_control_title_param = (key in ["control_title"]) and is_window_control

            # 检查是否为屏幕识别功能块的区域参数
            is_screen_region_param = (self.block.block_type in ["screen_find_image", "screen_click_image", "screen_wait_image", "screen_screenshot_region"]
                                      and key == "region")

            if is_window_title_param or is_control_title_param:
                # 为窗口/控件标题参数添加选点按钮
                row = QWidget()
                hl = QHBoxLayout(row)
                hl.setContentsMargins(0,0,0,0)
                hl.setSpacing(4)
                
                edit = QLineEdit(str(default))
                edit.setObjectName(f"_edit_{key}")
                if ph: edit.setPlaceholderText(ph)
                
                # 根据参数类型设置不同的按钮文本
                btn_text = "选窗口" if is_window_title_param else "选控件"
                btn = QPushButton(btn_text)
                btn.setObjectName("btn_flat")
                btn.setMinimumWidth(60)
                btn.clicked.connect(lambda checked=False, e=edit, is_win=is_window_title_param, is_ctrl=is_control_title_param: 
                                  self._pick_window_control(e, is_win, is_ctrl))
                
                hl.addWidget(edit)
                hl.addWidget(btn)
                return row
            elif is_screen_region_param:
                # 为屏幕识别区域参数添加框选按钮
                row = QWidget()
                hl = QHBoxLayout(row)
                hl.setContentsMargins(0,0,0,0)
                hl.setSpacing(4)

                edit = QLineEdit(str(default))
                edit.setObjectName(f"_edit_{key}")
                if ph: edit.setPlaceholderText(ph)

                btn = QPushButton("框选")
                btn.setObjectName("btn_flat")
                btn.setMinimumWidth(52)
                btn.clicked.connect(lambda checked=False, e=edit: self._select_region(e))

                hl.addWidget(edit)
                hl.addWidget(btn)
                return row
            else:
                w = QLineEdit(str(default))
                if ph: w.setPlaceholderText(ph)
                return w
        else:
            w = QLineEdit(str(default))
            if ph: w.setPlaceholderText(ph)
            return w

    def _pick_file(self, edit: QLineEdit):
        """打开文件对话框选择文件"""
        path, _ = QFileDialog.getOpenFileName(self, "选择文件")
        if path: edit.setText(path)

    def _capture_screenshot(self, edit: QLineEdit):
        """框选截图并保存到指定路径。
        使用 QScreen.grabWindow(0) 截全屏（正确处理 DPI 缩放），
        松开鼠标立即弹出保存对话框。
        """
        import os, datetime
        from PyQt6.QtWidgets import QDialog, QApplication
        from PyQt6.QtCore import Qt, QRect, QPoint, QSize
        from PyQt6.QtGui import QPainter, QPixmap, QColor, QPen, QFont, QCursor

        app = QApplication.instance()

        # ── 1. 先截全屏（在弹出遮罩之前，正确处理 DPI）──
        # 枚举所有屏幕，分别截图，再拼成虚拟桌面大图
        screen_shots = []  # (geometry_in_logical, pixmap_in_physical)
        for scr in app.screens():
            pm = scr.grabWindow(0)   # 物理像素截图
            screen_shots.append((scr.geometry(), pm))

        # 计算虚拟桌面逻辑坐标范围
        total_logical = QRect()
        for geom, _ in screen_shots:
            total_logical = total_logical.united(geom)

        # 创建以物理像素为单位的拼接画布
        # 取主屏 DPR 作为整体 devicePixelRatio
        main_dpr = app.primaryScreen().devicePixelRatio()
        canvas_w = int(total_logical.width()  * main_dpr)
        canvas_h = int(total_logical.height() * main_dpr)
        full_pixmap = QPixmap(canvas_w, canvas_h)
        full_pixmap.fill(QColor(0, 0, 0))
        painter = QPainter(full_pixmap)
        for geom, pm in screen_shots:
            # 计算该屏在画布中的位置（物理像素）
            px = int((geom.x() - total_logical.x()) * main_dpr)
            py = int((geom.y() - total_logical.y()) * main_dpr)
            painter.drawPixmap(px, py, pm)
        painter.end()

        # ── 2. 全屏遮罩对话框 ──
        class ScreenCaptureDialog(QDialog):
            def __init__(self_d):
                super().__init__(None)
                self_d.setWindowFlags(
                    Qt.WindowType.FramelessWindowHint |
                    Qt.WindowType.WindowStaysOnTopHint |
                    Qt.WindowType.Tool
                )
                self_d.setCursor(QCursor(Qt.CursorShape.CrossCursor))
                self_d.setMouseTracking(True)
                self_d.setGeometry(total_logical)
                self_d._offset = total_logical.topLeft()

                self_d._start    = QPoint()
                self_d._end      = QPoint()
                self_d._dragging = False
                self_d._has_sel  = False   # 松手后置 True
                self_d.selection_rect = None   # QRect（逻辑坐标，相对虚拟桌面原点）

                # 背景：把物理像素画布缩放成逻辑像素大小铺满窗口
                self_d._bg = full_pixmap.scaled(
                    total_logical.width(), total_logical.height(),
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.FastTransformation
                )

            def showEvent(self_d, ev):
                super().showEvent(ev)
                self_d.activateWindow()
                self_d.setFocus()

            def _sel_rect(self_d):
                """返回当前选区（窗口本地坐标）"""
                x1 = min(self_d._start.x(), self_d._end.x())
                y1 = min(self_d._start.y(), self_d._end.y())
                x2 = max(self_d._start.x(), self_d._end.x())
                y2 = max(self_d._start.y(), self_d._end.y())
                return QRect(x1, y1, x2 - x1, y2 - y1)

            def paintEvent(self_d, event):
                p = QPainter(self_d)
                # 绘制背景截图
                p.drawPixmap(0, 0, self_d._bg)
                # 半透明遮罩
                p.fillRect(self_d.rect(), QColor(0, 0, 0, 80))

                # 如果有选区（拖动中 or 已松手）
                if (self_d._dragging or self_d._has_sel) and not self_d._start.isNull():
                    sel = self_d._sel_rect()
                    if sel.width() > 2 and sel.height() > 2:
                        # 镂空：显示原始画面
                        p.drawPixmap(sel, self_d._bg, sel)
                        # 蓝色边框
                        p.setPen(QPen(QColor(30, 144, 255), 2))
                        p.drawRect(sel)
                        # 尺寸提示
                        info = f"{sel.width()} x {sel.height()}"
                        font = QFont()
                        font.setPointSize(10)
                        font.setBold(True)
                        p.setFont(font)
                        p.setPen(QColor(255, 255, 255))
                        tx = sel.left()
                        ty = sel.top() - 6 if sel.top() > 22 else sel.bottom() + 18
                        fm = p.fontMetrics()
                        tw = fm.horizontalAdvance(info)
                        p.fillRect(tx, ty - 14, tw + 8, 18, QColor(0, 0, 0, 160))
                        p.drawText(tx + 4, ty, info)

                # 底部提示
                tip = "拖动框选  |  松开鼠标确认  |  Esc 取消"
                font2 = QFont()
                font2.setPointSize(10)
                p.setFont(font2)
                fm2 = p.fontMetrics()
                tw2 = fm2.horizontalAdvance(tip)
                p.fillRect(self_d.width() - tw2 - 20, self_d.height() - 34,
                           tw2 + 16, 24, QColor(0, 0, 0, 160))
                p.setPen(QColor(255, 255, 255))
                p.drawText(self_d.width() - tw2 - 12, self_d.height() - 16, tip)

            def mousePressEvent(self_d, ev):
                if ev.button() == Qt.MouseButton.LeftButton:
                    self_d._start    = ev.pos()
                    self_d._end      = ev.pos()
                    self_d._dragging = True
                    self_d._has_sel  = False
                    self_d.update()

            def mouseMoveEvent(self_d, ev):
                if self_d._dragging:
                    self_d._end = ev.pos()
                    self_d.update()

            def mouseReleaseEvent(self_d, ev):
                if ev.button() == Qt.MouseButton.LeftButton and self_d._dragging:
                    self_d._end      = ev.pos()
                    self_d._dragging = False
                    self_d._has_sel  = True
                    sel = self_d._sel_rect()
                    if sel.width() > 5 and sel.height() > 5:
                        # 转换为虚拟桌面逻辑坐标
                        self_d.selection_rect = QRect(
                            sel.x() + self_d._offset.x(),
                            sel.y() + self_d._offset.y(),
                            sel.width(), sel.height()
                        )
                        self_d.accept()
                    else:
                        # 太小，重置
                        self_d._has_sel = False
                        self_d.update()

            def keyPressEvent(self_d, ev):
                if ev.key() == Qt.Key.Key_Escape:
                    self_d.reject()

        dlg = ScreenCaptureDialog()
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.selection_rect:
            return

        sel = dlg.selection_rect

        # ── 3. 从全屏拼合图中裁剪对应区域 ──
        # sel 是逻辑坐标（相对虚拟桌面），需换算成物理像素
        lx = sel.x() - total_logical.x()
        ly = sel.y() - total_logical.y()
        crop_x = int(lx * main_dpr)
        crop_y = int(ly * main_dpr)
        crop_w = max(int(sel.width()  * main_dpr), 1)
        crop_h = max(int(sel.height() * main_dpr), 1)
        cropped = full_pixmap.copy(crop_x, crop_y, crop_w, crop_h)

        # ── 4. 保存对话框 ──
        default_name = f"screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        pictures_dir = os.path.join(os.path.expanduser("~"), "Pictures")
        os.makedirs(pictures_dir, exist_ok=True)
        save_path, _ = QFileDialog.getSaveFileName(
            self, "保存截图",
            os.path.join(pictures_dir, default_name),
            "PNG 图像 (*.png);;JPEG 图像 (*.jpg);;所有文件 (*.*)"
        )
        if not save_path:
            return
        if not save_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
            save_path += '.png'

        cropped.save(save_path)
        edit.setText(save_path)

    @staticmethod
    @staticmethod
    def _ocr_pixmap(pixmap) -> str:
        """
        识别 QPixmap 中的文字。
        方案1：将图像保存为临时文件，通过 PowerShell 调用 Windows.Media.OCR（同步子进程，无asyncio冲突）。
        方案2：PIL + pytesseract（备用）。
        返回识别出的文字；失败返回空字符串。
        """
        import io, os, tempfile, subprocess
        from PyQt6.QtCore import QBuffer, QByteArray

        # 将 QPixmap 保存为临时 PNG
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QBuffer.OpenModeFlag.WriteOnly)
        pixmap.save(buf, "PNG")
        buf.close()
        png_bytes = bytes(ba)

        tmp_img  = None
        tmp_txt  = None
        try:
            fd, tmp_img = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            with open(tmp_img, "wb") as f:
                f.write(png_bytes)

            # ── 方案1：PowerShell + Windows.Media.OCR ──
            ps_script = r"""
$imgPath = 'IMG_PATH'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[void][Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
[void][Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
[void][Windows.Graphics.Imaging.BitmapDecoder,Windows.Foundation,ContentType=WindowsRuntime]

function Await-Task($WinRtTask) {
    $asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 } |
        Select-Object -First 1)
    $netTask = $asTask.MakeGenericMethod($WinRtTask.GetType().GetGenericArguments()[0]).Invoke($null, @($WinRtTask))
    $netTask.Wait() | Out-Null
    return $netTask.Result
}

try {
    $sf      = Await-Task ([Windows.Storage.StorageFile]::GetFileFromPathAsync($imgPath))
    $stream  = Await-Task ($sf.OpenReadAsync())
    $dec     = Await-Task ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream))
    $bmp     = Await-Task ($dec.GetSoftwareBitmapAsync())
    $eng     = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    if (-not $eng) {
        $lang = [Windows.Globalization.Language]::new('zh-Hans')
        $eng  = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang)
    }
    if (-not $eng) { Write-Output ''; exit }
    $res = Await-Task ($eng.RecognizeAsync($bmp))
    Write-Output $res.Text
} catch {
    Write-Output ''
}
""".replace("IMG_PATH", tmp_img.replace("\\", "\\\\"))

            try:
                # 将脚本写入临时 .ps1 文件，用 -File 执行（避免 -Command 多行截断/编码问题）
                fd2, tmp_ps1 = tempfile.mkstemp(suffix=".ps1")
                os.close(fd2)
                with open(tmp_ps1, "w", encoding="utf-8") as f:
                    f.write(ps_script)
                try:
                    result = subprocess.run(
                        ["powershell", "-NoProfile", "-NonInteractive",
                         "-ExecutionPolicy", "Bypass", "-File", tmp_ps1],
                        capture_output=True, text=True, timeout=25,
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                    text = (result.stdout or "").strip()
                    if text:
                        return text
                finally:
                    try:
                        os.unlink(tmp_ps1)
                    except Exception:
                        pass
            except Exception:
                pass

            # ── 方案2：PIL + pytesseract ──
            try:
                from PIL import Image
                import pytesseract
                img = Image.open(io.BytesIO(png_bytes))
                text = pytesseract.image_to_string(img, lang="chi_sim+eng")
                return text.strip()
            except Exception:
                pass

            return ""
        except Exception:
            return ""
        finally:
            for p in [tmp_img, tmp_txt]:
                if p and os.path.exists(p):
                    try:
                        os.unlink(p)
                    except Exception:
                        pass

    def _select_region(self, edit: QLineEdit):
        """框选搜索区域，将 x,y,w,h 坐标填入文本框。
        复用截图遮罩逻辑，框选后不保存图片，只将区域坐标写入编辑框。
        """
        from PyQt6.QtWidgets import QDialog, QApplication
        from PyQt6.QtCore import Qt, QRect, QPoint
        from PyQt6.QtGui import QPainter, QPixmap, QColor, QPen, QFont, QCursor

        app = QApplication.instance()

        # 截全屏作为背景
        screen_shots = []
        for scr in app.screens():
            pm = scr.grabWindow(0)
            screen_shots.append((scr.geometry(), pm))

        total_logical = QRect()
        for geom, _ in screen_shots:
            total_logical = total_logical.united(geom)

        main_dpr = app.primaryScreen().devicePixelRatio()
        canvas_w = int(total_logical.width()  * main_dpr)
        canvas_h = int(total_logical.height() * main_dpr)
        full_pixmap = QPixmap(canvas_w, canvas_h)
        full_pixmap.fill(QColor(0, 0, 0))
        painter = QPainter(full_pixmap)
        for geom, pm in screen_shots:
            px = int((geom.x() - total_logical.x()) * main_dpr)
            py = int((geom.y() - total_logical.y()) * main_dpr)
            painter.drawPixmap(px, py, pm)
        painter.end()

        class RegionSelectDialog(QDialog):
            def __init__(self_d):
                super().__init__(None)
                self_d.setWindowFlags(
                    Qt.WindowType.FramelessWindowHint |
                    Qt.WindowType.WindowStaysOnTopHint |
                    Qt.WindowType.Tool
                )
                self_d.setCursor(QCursor(Qt.CursorShape.CrossCursor))
                self_d.setMouseTracking(True)
                self_d.setGeometry(total_logical)
                self_d._offset = total_logical.topLeft()
                self_d._start    = QPoint()
                self_d._end      = QPoint()
                self_d._dragging = False
                self_d._has_sel  = False
                self_d.selection_rect = None
                self_d._bg = full_pixmap.scaled(
                    total_logical.width(), total_logical.height(),
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.FastTransformation
                )

            def showEvent(self_d, ev):
                super().showEvent(ev)
                self_d.activateWindow()
                self_d.setFocus()

            def _sel_rect(self_d):
                x1 = min(self_d._start.x(), self_d._end.x())
                y1 = min(self_d._start.y(), self_d._end.y())
                x2 = max(self_d._start.x(), self_d._end.x())
                y2 = max(self_d._start.y(), self_d._end.y())
                return QRect(x1, y1, x2 - x1, y2 - y1)

            def paintEvent(self_d, event):
                p = QPainter(self_d)
                p.drawPixmap(0, 0, self_d._bg)
                p.fillRect(self_d.rect(), QColor(0, 0, 0, 80))
                if (self_d._dragging or self_d._has_sel) and not self_d._start.isNull():
                    sel = self_d._sel_rect()
                    if sel.width() > 2 and sel.height() > 2:
                        p.drawPixmap(sel, self_d._bg, sel)
                        p.setPen(QPen(QColor(30, 144, 255), 2))
                        p.drawRect(sel)
                        info = f"{sel.width()} × {sel.height()}"
                        font = QFont()
                        font.setPointSize(10)
                        font.setBold(True)
                        p.setFont(font)
                        p.setPen(QColor(255, 255, 255))
                        tx = sel.left()
                        ty = sel.top() - 6 if sel.top() > 22 else sel.bottom() + 18
                        fm = p.fontMetrics()
                        tw = fm.horizontalAdvance(info)
                        p.fillRect(tx, ty - 14, tw + 8, 18, QColor(0, 0, 0, 160))
                        p.drawText(tx + 4, ty, info)
                tip = "拖动框选搜索区域  |  松开确认  |  Esc 取消"
                font2 = QFont()
                font2.setPointSize(10)
                p.setFont(font2)
                fm2 = p.fontMetrics()
                tw2 = fm2.horizontalAdvance(tip)
                p.fillRect(self_d.width() - tw2 - 20, self_d.height() - 34,
                           tw2 + 16, 24, QColor(0, 0, 0, 160))
                p.setPen(QColor(255, 255, 255))
                p.drawText(self_d.width() - tw2 - 12, self_d.height() - 16, tip)

            def mousePressEvent(self_d, ev):
                if ev.button() == Qt.MouseButton.LeftButton:
                    self_d._start    = ev.pos()
                    self_d._end      = ev.pos()
                    self_d._dragging = True
                    self_d._has_sel  = False
                    self_d.update()

            def mouseMoveEvent(self_d, ev):
                if self_d._dragging:
                    self_d._end = ev.pos()
                    self_d.update()

            def mouseReleaseEvent(self_d, ev):
                if ev.button() == Qt.MouseButton.LeftButton and self_d._dragging:
                    self_d._end      = ev.pos()
                    self_d._dragging = False
                    self_d._has_sel  = True
                    sel = self_d._sel_rect()
                    if sel.width() > 5 and sel.height() > 5:
                        self_d.selection_rect = QRect(
                            sel.x() + self_d._offset.x(),
                            sel.y() + self_d._offset.y(),
                            sel.width(), sel.height()
                        )
                        self_d.accept()
                    else:
                        self_d._has_sel = False
                        self_d.update()

            def keyPressEvent(self_d, ev):
                if ev.key() == Qt.Key.Key_Escape:
                    self_d.reject()

        dlg = RegionSelectDialog()
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.selection_rect:
            return

        sel = dlg.selection_rect
        edit.setText(f"{sel.x()},{sel.y()},{sel.width()},{sel.height()}")

    def _pick_window_control(self, edit: QLineEdit, is_window: bool, is_control: bool):
        """
        选窗口：独立 Win32 线程运行，悬停到目标窗口后按 F2 确认，Esc 取消。
          - 提示条：不透明深色 QLabel，始终置顶
          - 无 GDI 遮罩（已移除，避免偏移问题）
        """
        # ── 选控件 → OCR 方式 ──
        if is_control:
            self._pick_control_by_ocr(edit)
            return

        import ctypes
        import ctypes.wintypes
        import threading

        from PyQt6.QtWidgets import QApplication, QLabel
        from PyQt6.QtCore import Qt, QTimer

        user32 = ctypes.windll.user32
        GWL_EXSTYLE      = -20
        WS_EX_NOACTIVATE = 0x08000000

        app = QApplication.instance()

        # ── 提示条（不透明深色，不抢焦点）──
        tip = QLabel("悬停到目标窗口，按 F2 确认  |  Esc 取消", None)
        tip.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool)
        tip.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        tip.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        tip.setStyleSheet(
            "background:#1a1a2e; color:white; font-size:13px;"
            " padding:8px 18px; border-radius:6px;")
        tip.adjustSize()
        sg = app.primaryScreen().geometry()
        tip.move(sg.center().x() - tip.width() // 2, sg.bottom() - tip.height() - 20)
        tip.show()
        hwnd_tip = int(tip.winId())
        ex = user32.GetWindowLongW(hwnd_tip, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd_tip, GWL_EXSTYLE, ex | WS_EX_NOACTIVATE)

        # ── 线程通信 ──
        result = {"title": None, "class_name": None, "process_name": None, "hwnd": 0, "ok": False}
        done_event = threading.Event()

        def _gdi_thread():
            """独立 Win32 线程：轮询鼠标位置，F2 确认，Esc 取消。"""
            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

            def _get_window_text(hwnd):
                buf = ctypes.create_unicode_buffer(512)
                user32.GetWindowTextW(hwnd, buf, 512)
                return buf.value

            def _get_window_class(hwnd):
                buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, buf, 256)
                return buf.value

            def _get_process_name(hwnd):
                pid = ctypes.wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                try:
                    import psutil
                    proc = psutil.Process(pid.value)
                    return proc.name()
                except Exception:
                    return ""

            cur_hwnd = -1
            import time as _time

            # 先等鼠标松开（防止进入后立即误触）
            while user32.GetAsyncKeyState(0x01) & 0x8000:
                _time.sleep(0.02)

            while True:
                _time.sleep(0.04)  # 25fps

                pt = POINT()
                user32.GetCursorPos(ctypes.byref(pt))
                wfp = ctypes.wintypes.POINT()
                wfp.x, wfp.y = pt.x, pt.y
                hwnd = user32.WindowFromPoint(wfp)

                # 忽略提示条
                if hwnd == hwnd_tip:
                    hwnd = 0

                # 找根窗口
                if hwnd:
                    root = user32.GetAncestor(hwnd, 2)  # GA_ROOT
                    if root:
                        hwnd = root

                cur_hwnd = hwnd

                # F2 = 0x71 确认
                if user32.GetAsyncKeyState(0x71) & 0x8000:
                    result["title"] = _get_window_text(cur_hwnd) if cur_hwnd else ""
                    result["class_name"] = _get_window_class(cur_hwnd) if cur_hwnd else ""
                    result["process_name"] = _get_process_name(cur_hwnd) if cur_hwnd else ""
                    result["hwnd"] = cur_hwnd
                    result["ok"]    = True
                    done_event.set()
                    return

                # Esc = 0x1B 取消
                if user32.GetAsyncKeyState(0x1B) & 0x8000:
                    done_event.set()
                    return

        t = threading.Thread(target=_gdi_thread, daemon=True)
        t.start()

        # ── Qt 侧轮询 done_event，完成后回填结果 ──
        def _check_done():
            if done_event.is_set():
                tip.hide()
                tip.deleteLater()
                if result["ok"] and result["title"] is not None:
                    edit.setText(result["title"])
                    # 所有窗口控件功能块都支持自动回填 class_name 和 process_name
                    _win_block_types = {
                        "win_click_offset", "win_click_control", "win_input_control",
                        "win_get_control_text", "win_wait_control", "win_find_control",
                        "win_find_window", "win_wait_window", "win_close_window",
                    }
                    if self.block.block_type in _win_block_types:
                        cn_widget = self._widgets.get("class_name")
                        pn_widget = self._widgets.get("process_name")
                        if cn_widget is not None and result["class_name"]:
                            # window_class_picker 类型的 widget 是 QWidget 容器，
                            # 内部 QLineEdit 通过 _line_edit 属性暴露
                            if hasattr(cn_widget, "_line_edit"):
                                cn_widget._line_edit.setText(result["class_name"])
                            elif hasattr(cn_widget, "setText"):
                                cn_widget.setText(result["class_name"])
                            elif hasattr(cn_widget, "_edit"):
                                cn_widget._edit.setText(result["class_name"])
                            else:
                                from PyQt6.QtWidgets import QLineEdit as _QLE2
                                _le = cn_widget.findChild(_QLE2)
                                if _le:
                                    _le.setText(result["class_name"])
                        if pn_widget is not None and result["process_name"]:
                            if hasattr(pn_widget, "_line_edit"):
                                pn_widget._line_edit.setText(result["process_name"])
                            elif hasattr(pn_widget, "setText"):
                                pn_widget.setText(result["process_name"])
                            elif hasattr(pn_widget, "_edit"):
                                pn_widget._edit.setText(result["process_name"])
                            else:
                                from PyQt6.QtWidgets import QLineEdit as _QLE2
                                _le = pn_widget.findChild(_QLE2)
                                if _le:
                                    _le.setText(result["process_name"])
            else:
                QTimer.singleShot(50, _check_done)

        QTimer.singleShot(50, _check_done)

    def _pick_control_by_ocr(self, edit: QLineEdit):
        """
        OCR 方式选控件文字：
          1. 从 window_title 参数（同一功能块）读取目标窗口标题
          2. 用 Win32 将目标窗口前置
          3. 最小化 AutoFlow 主窗口（避免遮挡目标）
          4. 延时 400ms 后显示框选 UI（全屏截图背景 + 拖拽框选）
          5. 框选区域截图 → Windows.Media.OCR 识别（无需额外安装）
          6. 识别结果填入 edit；还原主窗口
        """
        import ctypes
        import ctypes.wintypes
        import re as _re

        from PyQt6.QtWidgets import (QDialog, QApplication, QMessageBox,
                                     QWidget, QLabel)
        from PyQt6.QtCore import Qt, QTimer, QRect, QPoint
        from PyQt6.QtGui import (QPainter, QColor, QPen, QFont,
                                 QCursor, QPixmap)

        user32 = ctypes.windll.user32

        # ── 1. 读取同一功能块编辑器中的 window_title ──
        win_title_widget = self._widgets.get("window_title")
        win_title = ""
        if win_title_widget is not None:
            if hasattr(win_title_widget, "text"):
                win_title = win_title_widget.text().strip()
            elif hasattr(win_title_widget, "findChild"):
                from PyQt6.QtWidgets import QLineEdit as _QLE
                child = win_title_widget.findChild(_QLE)
                if child:
                    win_title = child.text().strip()

        if not win_title:
            QMessageBox.warning(self, "提示",
                "请先填写「窗口标题」，再使用「选控件」功能。\n"
                "选控件将把该窗口前置，然后截图框选识别文字。")
            return

        # ── 2. 前置目标窗口 ──
        target_hwnd = 0
        pattern = _re.compile(win_title.replace("*", ".*"), _re.IGNORECASE)

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        def _enum_cb(h, _):
            nonlocal target_hwnd
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(h, buf, 512)
            if pattern.search(buf.value) and user32.IsWindowVisible(h):
                target_hwnd = h
                return False
            return True

        user32.EnumWindows(_enum_cb, 0)
        if target_hwnd:
            # 恢复最小化 + 前置
            SW_RESTORE = 9
            user32.ShowWindow(target_hwnd, SW_RESTORE)
            user32.SetForegroundWindow(target_hwnd)

        # ── 3. 最小化 AutoFlow 主窗口 ──
        # 找到主窗口（最顶层 parent）
        main_win = self
        while main_win.parent():
            main_win = main_win.parent()
        main_win.showMinimized()

        app = QApplication.instance()
        dpr = app.primaryScreen().devicePixelRatio()

        # ── 4. 延时后开始框选 ──
        def _do_select():
            # 全屏截图
            screens = app.screens()
            total_rect = QRect()
            for s in screens:
                total_rect = total_rect.united(s.geometry())

            canvas_w = int(total_rect.width()  * dpr)
            canvas_h = int(total_rect.height() * dpr)
            full_pm = QPixmap(canvas_w, canvas_h)
            full_pm.fill(QColor(0, 0, 0))
            tmp_p = QPainter(full_pm)
            for s in screens:
                pm = s.grabWindow(0)
                dx = int((s.geometry().x() - total_rect.x()) * dpr)
                dy = int((s.geometry().y() - total_rect.y()) * dpr)
                tmp_p.drawPixmap(dx, dy, pm)
            tmp_p.end()
            bg = full_pm.scaled(total_rect.width(), total_rect.height(),
                                Qt.AspectRatioMode.IgnoreAspectRatio,
                                Qt.TransformationMode.FastTransformation)

            # ── 框选遮罩 Dialog ──
            class SelectionDialog(QDialog):
                def __init__(self_d):
                    super().__init__(None)
                    self_d.setWindowFlags(
                        Qt.WindowType.FramelessWindowHint |
                        Qt.WindowType.WindowStaysOnTopHint |
                        Qt.WindowType.Tool)
                    self_d.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
                    self_d.setGeometry(total_rect)
                    self_d.setCursor(QCursor(Qt.CursorShape.CrossCursor))
                    self_d._bg = bg
                    self_d._start  = QPoint()
                    self_d._end    = QPoint()
                    self_d._drawing = False
                    self_d.selection_rect = QRect()

                    tip = QLabel("框选要识别的文字区域  |  Esc 取消", self_d)
                    tip.setStyleSheet(
                        "background:rgba(0,0,0,200);color:white;"
                        "padding:5px 12px;border-radius:4px;font-size:13px;")
                    tip.adjustSize()
                    tip.move(16, 16)

                def mousePressEvent(self_d, ev):
                    if ev.button() == Qt.MouseButton.LeftButton:
                        self_d._start = ev.pos()
                        self_d._end   = ev.pos()
                        self_d._drawing = True
                        self_d.update()

                def mouseMoveEvent(self_d, ev):
                    if self_d._drawing:
                        self_d._end = ev.pos()
                        self_d.update()

                def mouseReleaseEvent(self_d, ev):
                    if ev.button() == Qt.MouseButton.LeftButton and self_d._drawing:
                        self_d._drawing = False
                        self_d._end = ev.pos()
                        r = QRect(self_d._start, self_d._end).normalized()
                        if r.width() > 4 and r.height() > 4:
                            self_d.selection_rect = r
                            self_d.accept()
                        else:
                            self_d.update()

                def paintEvent(self_d, ev):
                    p = QPainter(self_d)
                    p.drawPixmap(0, 0, self_d._bg)
                    p.fillRect(self_d.rect(), QColor(0, 0, 0, 80))
                    r = QRect(self_d._start, self_d._end).normalized()
                    if r.isValid():
                        p.drawPixmap(r, self_d._bg, r)
                        p.fillRect(r, QColor(30, 144, 255, 30))
                        p.setPen(QPen(QColor(30, 144, 255), 2))
                        p.drawRect(r)

                def keyPressEvent(self_d, ev):
                    if ev.key() == Qt.Key.Key_Escape:
                        self_d.reject()

            dlg = SelectionDialog()
            if dlg.exec() != QDialog.DialogCode.Accepted:
                main_win.showNormal()
                main_win.activateWindow()
                return

            sel = dlg.selection_rect
            if not sel.isValid():
                main_win.showNormal()
                main_win.activateWindow()
                return

            # ── 5. 裁剪截图并 OCR ──
            # 用 DPI 缩放换算回物理坐标裁剪
            px_x = int(sel.x()      * dpr)
            px_y = int(sel.y()      * dpr)
            px_w = int(sel.width()  * dpr)
            px_h = int(sel.height() * dpr)
            cropped = full_pm.copy(px_x, px_y, px_w, px_h)

            text = BlockEditDialog._ocr_pixmap(cropped)

            # ── 6. 还原主窗口，写入结果 ──
            main_win.showNormal()
            main_win.activateWindow()
            main_win.raise_()

            if text:
                edit.setText(text.strip())
            else:
                QMessageBox.information(
                    main_win, "OCR 未识别到文字",
                    "选区内未能识别到文字，请尝试更大的选区或清晰度更高的区域。")

        QTimer.singleShot(500, _do_select)

    def _pick_window_offset(self, window_picker_widget):
        """
        选偏移点：独立 Win32 线程运行 GDI 边框 + 十字线，F2 确认 / Esc 取消。
          1. 找到目标窗口并前置激活（失败则最小化自身）
          2. 独立线程绘制窗口边框 + 鼠标位置十字线
          3. 提示条实时显示相对坐标 (x, y)
          4. F2 键确认 → 回传 offset_x / offset_y
        """
        import ctypes
        import ctypes.wintypes
        import re as _re
        import threading

        from PyQt6.QtWidgets import QApplication, QLabel, QMessageBox
        from PyQt6.QtCore import Qt, QTimer

        win_title = window_picker_widget.text().strip()
        if not win_title:
            QMessageBox.warning(self, "提示", "请先填写窗口标题，再选偏移点。")
            return

        user32 = ctypes.windll.user32
        GWL_EXSTYLE      = -20
        WS_EX_NOACTIVATE = 0x08000000

        # 找到目标窗口
        pattern    = _re.compile(win_title.replace("*", ".*"), _re.IGNORECASE)
        target_hwnd = 0

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        def _enum_cb(h, _):
            nonlocal target_hwnd
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(h, buf, 512)
            if pattern.search(buf.value) and user32.IsWindowVisible(h):
                target_hwnd = h
                return False
            return True

        user32.EnumWindows(_enum_cb, 0)
        if not target_hwnd:
            QMessageBox.warning(self, "提示", f"未找到窗口：{win_title}\n请确认窗口已打开。")
            return

        # 前置目标窗口
        user32.ShowWindow(target_hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(target_hwnd)
        import time as _time; _time.sleep(0.1)

        r = ctypes.wintypes.RECT()
        user32.GetWindowRect(target_hwnd, ctypes.byref(r))
        win_l, win_t, win_r, win_b = r.left, r.top, r.right, r.bottom

        app = QApplication.instance()

        # 如果前置失败（AutoFlow仍在前台），最小化自身
        main_win = self
        while main_win.parent():
            main_win = main_win.parent()
        _minimized = False
        if user32.GetForegroundWindow() != target_hwnd:
            main_win.showMinimized()
            _minimized = True
            _time.sleep(0.2)

        # ── 提示条（实时显示坐标）──
        tip = QLabel("移到窗口内：(?, ?)  |  F2 确认  |  Esc 取消", None)
        tip.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool)
        tip.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        tip.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        tip.setStyleSheet(
            "background:#1a1a2e; color:white; font-size:13px;"
            " padding:8px 18px; border-radius:6px;")
        tip.adjustSize()
        sg = app.primaryScreen().geometry()
        tip.move(sg.center().x() - tip.width() // 2, sg.bottom() - tip.height() - 20)
        tip.show()
        hwnd_tip = int(tip.winId())
        ex = user32.GetWindowLongW(hwnd_tip, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd_tip, GWL_EXSTYLE, ex | WS_EX_NOACTIVATE)

        # ── 线程通信 ──
        result    = {"ox": None, "oy": None, "ok": False}
        done_evt  = threading.Event()
        coord_box = {"ox": 0, "oy": 0, "in_win": False}  # 供 Qt 侧更新提示条

        def _gdi_thread():
            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

            last_in_win_px = -1
            last_in_win_py = -1

            # 先等鼠标松开
            import time as _t2
            while user32.GetAsyncKeyState(0x01) & 0x8000:
                _t2.sleep(0.02)

            while True:
                _t2.sleep(0.04)

                pt = POINT()
                user32.GetCursorPos(ctypes.byref(pt))
                px, py = pt.x, pt.y
                in_win = (win_l <= px <= win_r and win_t <= py <= win_b)

                # 更新提示条数据
                coord_box["ox"]     = px - win_l
                coord_box["oy"]     = py - win_t
                coord_box["in_win"] = in_win

                # 记录最后一次在窗口内的鼠标位置
                if in_win:
                    last_in_win_px, last_in_win_py = px, py

                # F2 = 0x71 确认
                if user32.GetAsyncKeyState(0x71) & 0x8000:
                    if last_in_win_px >= 0 and last_in_win_py >= 0:
                        result["ox"] = last_in_win_px - win_l
                        result["oy"] = last_in_win_py - win_t
                    else:
                        result["ox"] = max(0, min(px - win_l, win_r - win_l))
                        result["oy"] = max(0, min(py - win_t, win_b - win_t))
                    result["ok"] = True
                    done_evt.set()
                    return

                # Esc = 0x1B 取消
                if user32.GetAsyncKeyState(0x1B) & 0x8000:
                    done_evt.set()
                    return

        threading.Thread(target=_gdi_thread, daemon=True).start()

        # ── Qt 侧：轮询 done_evt + 更新提示条文字 ──
        def _check_done():
            if done_evt.is_set():
                tip.hide()
                tip.deleteLater()
                if _minimized:
                    main_win.showNormal()
                    main_win.activateWindow()
                if result["ok"]:
                    ox = result["ox"]
                    oy = result["oy"]
                    try:
                        from PyQt6.QtWidgets import QDoubleSpinBox, QSpinBox
                        for w_key, val in [("offset_x", ox), ("offset_y", oy)]:
                            widget = self._widgets.get(w_key)
                            if widget is None:
                                continue
                            # number_or_var → QLineEdit
                            if isinstance(widget, QLineEdit):
                                widget.setText(str(int(val)))
                            elif isinstance(widget, (QDoubleSpinBox, QSpinBox)):
                                widget.setValue(val)
                            elif hasattr(widget, "setValue"):
                                widget.setValue(val)
                            elif hasattr(widget, "setText"):
                                widget.setText(str(int(val)))
                    except Exception as _e:
                        import traceback; traceback.print_exc()
            else:
                # 更新提示条文字
                if coord_box["in_win"]:
                    tip.setText(
                        f"偏移 ({coord_box['ox']}, {coord_box['oy']})  |  F2 确认  |  Esc 取消")
                    tip.adjustSize()
                    sg2 = app.primaryScreen().geometry()
                    tip.move(sg2.center().x() - tip.width() // 2,
                             sg2.bottom() - tip.height() - 20)
                QTimer.singleShot(50, _check_done)

        QTimer.singleShot(50, _check_done)

    def _pick_folder(self, edit: QLineEdit):
        path = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if path: edit.setText(path)

    def _get_widget_value(self, key: str, spec: dict):
        w     = self._widgets.get(key)
        ptype = spec["type"]
        if w is None: return spec.get("default", "")

        if ptype == "bool":             return w.isChecked()
        elif ptype == "number":         return w.value()
        elif ptype == "select":
            # userData 存储真实 value（当 option_labels 时与显示文本不同）
            data = w.currentData()
            return data if data is not None else w.currentText()
        elif ptype == "text_multiline": return w.toPlainText()
        elif ptype in ("file_picker", "folder_picker"):
            edit = w.findChild(QLineEdit)
            return edit.text() if edit else ""
        elif ptype == "app_launcher_picker":
            return w.text() if isinstance(w, AppLauncherPickerWidget) else ""
        elif ptype == "time":           return w.time().toString("HH:mm")
        elif ptype == "hotkey_input":   return w.text()
        elif ptype == "window_picker":
            # win_click_offset 的 window_title 参数是复合行（WindowPickerEdit + 按钮）
            if self.block.block_type == "win_click_offset" and key == "window_title":
                wp = w.findChild(WindowPickerEdit)
                return wp.text() if wp else ""
            return w.text()
        elif ptype in ("process_picker", "process_window_picker"):
            return w.text()
        elif ptype == "window_class_picker":
            # 复合 widget（QLineEdit + 识别按钮），取第一个 QLineEdit 的文本
            if isinstance(w, QLineEdit):
                return w.text()
            edit = w.findChild(QLineEdit)
            return edit.text() if edit else ""
        elif ptype == "coord_picker":
            return w.get_value() if isinstance(w, CoordPickerEdit) else {"x": 0, "y": 0, "mode": "pixel"}
        elif ptype == "task_picker":
            return w.value()
        elif ptype == "macro_recorder":
            return w.get_data()
        elif ptype == "condition_target":
            return w.text() if hasattr(w, 'text') else ""
        elif ptype == "ai_cmd_gen":
            # 返回描述文本（命令内容已经填入 command 控件，这里只存描述）
            de = getattr(w, '_desc_edit', None)
            return de.text() if de else ""
        elif ptype == "number_or_var":
            txt = w.text()
            try:
                v = float(txt)
                return int(v) if v == int(v) else v
            except Exception:
                return txt
        else:
            # text 类型：可能是 QLineEdit，也可能是含按钮的 QWidget 容器
            if isinstance(w, QLineEdit):
                return w.text()
            edit = w.findChild(QLineEdit)
            return edit.text() if edit else (w.text() if hasattr(w, 'text') else "")

    def _save(self):
        self.block.comment = self._comment.text()
        self.block.enabled = self._enabled.isChecked()
        spec = BLOCK_PARAMS.get(self.block.block_type, {})
        for key, s in spec.items():
            self.block.params[key] = self._get_widget_value(key, s)
        # 保存约束条件
        self.block.constraints = self._constraint_widget.get_constraints()
        self.accept()

    def _ai_generate_command(self, desc_edit: "QLineEdit"):
        """AI 智能生成命令：根据描述和选择的 shell 类型，调用 AI 生成命令并填入 command 控件"""
        desc = desc_edit.text().strip()
        if not desc:
            QMessageBox.warning(self, "提示", "请先填写「描述要做什么」再生成命令。")
            return

        # 获取 shell 类型
        shell_widget = self._widgets.get("shell")
        shell = "cmd"
        if shell_widget and isinstance(shell_widget, QComboBox):
            shell = shell_widget.currentData() or "cmd"

        # 获取 command 控件
        cmd_widget = self._widgets.get("command")
        if not cmd_widget:
            QMessageBox.warning(self, "提示", "找不到命令输入框。")
            return

        shell_names = {
            "cmd": "Windows CMD 批处理命令",
            "powershell": "Windows PowerShell 脚本",
            "bat": "Windows .bat 批处理脚本",
            "python": "Python 脚本",
            "wscript": "VBScript 脚本",
            "bash": "Linux/WSL Bash 脚本",
        }
        shell_desc = shell_names.get(shell, shell)

        # 构建 AI 提示词
        sys_prompt = (
            f"你是一个命令行专家。请根据用户的描述，生成一段 {shell_desc}，"
            "只输出代码，不要任何解释或 Markdown 格式，直接输出可执行的命令内容。"
        )
        user_prompt = f"请生成{shell_desc}，实现以下功能：{desc}"

        # 获取 AI 配置（从主窗口 _project.config）
        cfg = None
        from PyQt6.QtWidgets import QApplication as _QApp
        for _w in _QApp.topLevelWidgets():
            if hasattr(_w, '_project') and hasattr(_w._project, 'config'):
                cfg = _w._project.config
                break
        if cfg is None:
            top = self
            while top.parent():
                top = top.parent()
            if hasattr(top, '_project') and hasattr(top._project, 'config'):
                cfg = top._project.config

        if not cfg or not getattr(cfg, 'ai_api_key', '').strip():
            QMessageBox.warning(self, "AI 未配置",
                "请先在「设置 → AI」中配置 API Key，然后再使用 AI 生成命令。")
            return

        # 显示等待状态
        gen_btn = self.sender()
        if gen_btn:
            gen_btn.setEnabled(False)
            gen_btn.setText("⏳ 生成中…")

        # 在后台线程调用 AI
        import threading, urllib.request, json as _json, ssl

        def _do_ai():
            try:
                base_url = getattr(cfg, 'ai_base_url', '').strip() or "https://api.openai.com/v1"
                api_key  = getattr(cfg, 'ai_api_key', '').strip()
                model    = getattr(cfg, 'ai_model', 'gpt-4o-mini')
                payload  = _json.dumps({
                    "model": model,
                    "messages": [
                        {"role": "system", "content": sys_prompt},
                        {"role": "user",   "content": user_prompt},
                    ],
                    "max_tokens": 1024,
                    "temperature": 0.2,
                }).encode("utf-8")
                req = urllib.request.Request(
                    f"{base_url.rstrip('/')}/chat/completions",
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}",
                    },
                    method="POST",
                )
                # 忽略 SSL 证书验证（兼容国内代理 API）
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
                    data = _json.loads(resp.read().decode("utf-8"))
                result = data["choices"][0]["message"]["content"].strip()
                # 去掉可能的 markdown 代码块
                if result.startswith("```"):
                    lines = result.splitlines()
                    result = "\n".join(
                        l for l in lines
                        if not l.startswith("```")
                    ).strip()
                QTimer.singleShot(0, lambda: _on_done(result, None))
            except Exception as e:
                import traceback as _tb
                QTimer.singleShot(0, lambda: _on_done(None, _tb.format_exc()))

        def _on_done(result, error):
            if gen_btn:
                gen_btn.setEnabled(True)
                gen_btn.setText("🤖 AI 生成命令")
            if error:
                short = error.strip().splitlines()[-1] if error.strip() else "未知错误"
                QMessageBox.critical(self, "AI 生成失败",
                    f"调用 AI 时出错，请检查：\n"
                    f"• API Key 是否正确\n"
                    f"• Base URL 是否填写正确\n"
                    f"• 网络是否可以访问该接口\n\n"
                    f"详细错误：\n{error}")
                return
            if result:
                if isinstance(cmd_widget, QTextEdit):
                    cmd_widget.setPlainText(result)
                elif isinstance(cmd_widget, QLineEdit):
                    cmd_widget.setText(result)

        threading.Thread(target=_do_ai, daemon=True).start()





# ─────────────────── 已安装应用选择对话框 ───────────────────

class InstalledAppChooserDialog(QDialog):
    """
    从注册表读取已安装应用列表，供用户选择启动路径。
    支持搜索过滤、显示应用图标（可选）、双击确认。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择已安装应用")
        self.setMinimumSize(580, 520)
        self.setModal(True)
        self._selected_path = ""
        self._apps: list[dict] = []   # [{name, path, publisher}]
        self._build_ui()
        self._load_apps()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(16, 12, 16, 12)

        # 搜索栏
        search_row = QHBoxLayout()
        search_lbl = QLabel("🔍")
        self._search = QLineEdit()
        self._search.setPlaceholderText("输入应用名称搜索...")
        self._search.textChanged.connect(self._filter)
        search_row.addWidget(search_lbl)
        search_row.addWidget(self._search)
        root.addLayout(search_row)

        # 提示
        hint = QLabel("双击应用名称即可选择，或选中后点击「确定」")
        hint.setStyleSheet("color: #808080; font-size: 11px;")
        root.addWidget(hint)

        # 应用列表
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["应用名称", "发行商", "路径"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.doubleClicked.connect(self._on_double_click)
        self._table.setStyleSheet("""
            QTableWidget { font-size: 12px; }
            QTableWidget::item:selected { background: #3A5FBF; color: white; }
        """)
        root.addWidget(self._table)

        # 状态行
        self._status_lbl = QLabel("正在读取应用列表...")
        self._status_lbl.setStyleSheet("color: #808080; font-size: 11px;")
        root.addWidget(self._status_lbl)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton("✅ 确定")
        ok_btn.setObjectName("btn_primary")
        ok_btn.setFixedHeight(32)
        ok_btn.clicked.connect(self._on_accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("btn_flat")
        cancel_btn.setFixedHeight(32)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        root.addLayout(btn_row)

    def _load_apps(self):
        """在子线程读取注册表，加载完成后刷新列表"""
        import threading
        threading.Thread(target=self._read_registry, daemon=True).start()

    def _read_registry(self):
        """读取注册表已安装应用（HKLM + HKCU，32位+64位）"""
        apps = {}
        try:
            import winreg
            reg_paths = [
                (winreg.HKEY_LOCAL_MACHINE,
                 r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                (winreg.HKEY_LOCAL_MACHINE,
                 r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
                (winreg.HKEY_CURRENT_USER,
                 r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            ]
            for hive, sub_key in reg_paths:
                try:
                    key = winreg.OpenKey(hive, sub_key)
                except Exception:
                    continue
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        sub_name = winreg.EnumKey(key, i)
                        sub = winreg.OpenKey(key, sub_name)
                        def _get(k):
                            try: return winreg.QueryValueEx(sub, k)[0]
                            except Exception: return ""
                        name      = _get("DisplayName").strip()
                        publisher = _get("Publisher").strip()
                        exe_path  = (_get("DisplayIcon") or "").split(",")[0].strip().strip('"')
                        install_loc = _get("InstallLocation").strip()
                        # 只保留有名称且有可执行路径的
                        if not name:
                            continue
                        # 优先用 DisplayIcon 里的 exe，其次在安装目录下搜
                        if not exe_path.lower().endswith(".exe") or not os.path.isfile(exe_path):
                            exe_path = ""
                        if not exe_path and install_loc and os.path.isdir(install_loc):
                            # 在安装目录首层找 .exe（排除 uninstall）
                            try:
                                for fn in os.listdir(install_loc):
                                    if fn.lower().endswith(".exe") and "uninstall" not in fn.lower():
                                        exe_path = os.path.join(install_loc, fn)
                                        break
                            except Exception:
                                pass
                        if name not in apps:
                            apps[name] = {"name": name, "publisher": publisher,
                                          "path": exe_path}
                        elif exe_path and not apps[name]["path"]:
                            apps[name]["path"] = exe_path
                    except Exception:
                        continue
        except Exception as e:
            pass

        self._apps = sorted(apps.values(), key=lambda x: x["name"].lower())
        # 回主线程刷新
        QTimer.singleShot(0, self._populate_table)

    def _populate_table(self):
        self._filter(self._search.text())
        total = len(self._apps)
        with_path = sum(1 for a in self._apps if a["path"])
        self._status_lbl.setText(
            f"共 {total} 个已安装应用，其中 {with_path} 个找到可执行文件路径"
        )

    def _filter(self, keyword: str = ""):
        kw = keyword.strip().lower()
        filtered = [a for a in self._apps if kw in a["name"].lower()
                    or kw in a["publisher"].lower()] if kw else self._apps
        self._table.setRowCount(0)
        for app in filtered:
            row = self._table.rowCount()
            self._table.insertRow(row)
            name_item = QTableWidgetItem(app["name"])
            pub_item  = QTableWidgetItem(app["publisher"])
            path_item = QTableWidgetItem(app["path"] or "（未找到路径）")
            if not app["path"]:
                path_item.setForeground(QTableWidgetItem().foreground())
                from PyQt6.QtGui import QColor as _QC
                path_item.setForeground(_QC("#888888"))
            self._table.setItem(row, 0, name_item)
            self._table.setItem(row, 1, pub_item)
            self._table.setItem(row, 2, path_item)
            # 把原始 app dict 存到 UserRole
            name_item.setData(Qt.ItemDataRole.UserRole, app)

    def _on_double_click(self, idx):
        self._on_accept()

    def _on_accept(self):
        row = self._table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "提示", "请先选择一个应用。")
            return
        item = self._table.item(row, 0)
        app  = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not app:
            return
        if not app["path"]:
            QMessageBox.warning(self, "无可执行路径",
                f"「{app['name']}」未找到可执行文件路径。\n"
                "请关闭此对话框后手动填写路径，或点击「浏览」选择文件。")
            return
        self._selected_path = app["path"]
        self.accept()

    def get_path(self) -> str:
        return self._selected_path


# ─────────────────── 应用启动路径选择控件 ───────────────────

class AppLauncherPickerWidget(QWidget):
    """
    launch_app 专用路径输入控件：
    - 文本输入框（手动填写路径 / 变量）
    - 「浏览文件」按钮 → 弹出文件选择器
    - 「选择应用」按钮 → 弹出已安装应用列表（读注册表）
    """

    def __init__(self, default: str = "", placeholder: str = "", parent=None):
        super().__init__(parent)
        hl = QHBoxLayout(self)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(4)

        self._edit = QLineEdit(str(default))
        if placeholder:
            self._edit.setPlaceholderText(placeholder)
        hl.addWidget(self._edit, 1)

        browse_btn = QPushButton("📂 浏览")
        browse_btn.setObjectName("btn_flat")
        browse_btn.setMinimumWidth(62)
        browse_btn.setToolTip("打开文件浏览器选择可执行文件")
        browse_btn.clicked.connect(self._browse_file)
        hl.addWidget(browse_btn)

        app_btn = QPushButton("📋 应用")
        app_btn.setObjectName("btn_flat")
        app_btn.setMinimumWidth(62)
        app_btn.setToolTip("从已安装应用列表中选择")
        app_btn.clicked.connect(self._pick_app)
        hl.addWidget(app_btn)

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择程序文件",
            self._edit.text() or "",
            "可执行文件 (*.exe *.bat *.cmd *.ps1 *.py *.lnk);;所有文件 (*.*)"
        )
        if path:
            self._edit.setText(path)

    def _pick_app(self):
        dlg = InstalledAppChooserDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            path = dlg.get_path()
            if path:
                self._edit.setText(path)

    def text(self) -> str:
        return self._edit.text()

    def setText(self, v: str):
        self._edit.setText(v)


# ─────────────────── 键鼠宏录制控件 ───────────────────



class MacroRecorderWidget(QWidget):
    """
    键鼠宏录制控件：
    - 使用 pynput 库录制鼠标/键盘事件（事件格式参考 KeymouseGo）
    - 坐标以相对屏幕比例存储（0.0~1.0），兼容不同分辨率回放
    - 录制数据格式：[{"type":"EM"|"EK","time":ms,"event":...,...}, ...]
    - 停止录制热键通过 Win32 RegisterHotKey 实现，最小化后仍可触发
    """

    # 类级别信号：后台热键线程 → 主线程（线程安全）
    _stop_signal = pyqtSignal()

    # 类级别停止热键字符串（由 main_window 从 AppConfig 同步）
    stop_hotkey: str = "F10"

    def __init__(self, data: list, parent=None):
        super().__init__(parent)
        self._data: list = list(data) if data else []
        self._recording = False
        self._rec_thread = None
        self._events = []
        self._rec_start_time = 0
        self._stop_hotkey_thread = None
        self._stop_hotkey_event = None
        # 连接停止信号到主线程槽（线程安全）
        self._stop_signal.connect(self._stop_record)
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(6)

        # ── 状态栏 ──
        top = QHBoxLayout()
        self._status_lbl = QLabel("就绪")
        self._status_lbl.setStyleSheet("font-size: 11px;")
        top.addWidget(self._status_lbl)
        top.addStretch()
        self._count_lbl = QLabel(f"{len(self._data)} 个事件")
        self._count_lbl.setStyleSheet("font-size: 11px; color: gray;")
        top.addWidget(self._count_lbl)
        lay.addLayout(top)

        # ── 按钮行 ──
        btn_row = QHBoxLayout()
        self._btn_record = QPushButton("⏺ 开始录制")
        self._btn_record.setObjectName("btn_primary")
        self._btn_record.clicked.connect(self._toggle_record)

        self._btn_clear = QPushButton("🗑 清空")
        self._btn_clear.setObjectName("btn_flat")
        self._btn_clear.clicked.connect(self._clear_data)

        self._btn_preview = QPushButton("📋 查看事件")
        self._btn_preview.setObjectName("btn_flat")
        self._btn_preview.clicked.connect(self._preview_data)

        btn_row.addWidget(self._btn_record)
        btn_row.addWidget(self._btn_preview)
        btn_row.addWidget(self._btn_clear)
        lay.addLayout(btn_row)

        # ── 提示 ──
        hint = QLabel(f"录制时按 {MacroRecorderWidget.stop_hotkey} 停止录制。坐标以屏幕比例存储，可在不同分辨率下回放。")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 10px; color: gray;")
        lay.addWidget(hint)

    def _toggle_record(self):
        if self._recording:
            self._stop_record()
        else:
            self._start_record()

    def _start_record(self):
        try:
            import pynput  # noqa
        except ImportError:
            QMessageBox.warning(self, "缺少依赖",
                "录制功能需要安装 pynput 库。\n\n请在命令行运行：\npip install pynput")
            return

        self._recording = True
        self._events = []
        stop_hk = MacroRecorderWidget.stop_hotkey
        self._btn_record.setText(f"⏹ 停止录制 ({stop_hk})")
        self._btn_record.setStyleSheet("background: #F44336; color: white;")
        self._status_lbl.setText("🔴 正在录制...")
        self._status_lbl.setStyleSheet("font-size: 11px; color: #F44336;")

        import threading, time as _t
        self._rec_start_time = _t.time()

        def record_loop():
            from pynput import mouse as pm, keyboard as pk
            import ctypes, time as _t2

            sw = ctypes.windll.user32.GetSystemMetrics(0)
            sh = ctypes.windll.user32.GetSystemMetrics(1)

            def ts():
                return int((_t2.time() - self._rec_start_time) * 1000)

            def on_move(x, y):
                if not self._recording: return
                self._events.append({
                    "type": "EM", "time": ts(), "event": "move",
                    "x": round(x / sw, 6), "y": round(y / sh, 6),
                    "wx": 0, "wy": 0
                })

            def on_click(x, y, button, pressed):
                if not self._recording: return
                btn_name = "left" if button == pm.Button.left else \
                           "right" if button == pm.Button.right else "middle"
                ev = f"{btn_name}_{'down' if pressed else 'up'}"
                self._events.append({
                    "type": "EM", "time": ts(), "event": ev,
                    "x": round(x / sw, 6), "y": round(y / sh, 6),
                    "wx": 0, "wy": 0
                })

            def on_scroll(x, y, dx, dy):
                if not self._recording: return
                self._events.append({
                    "type": "EM", "time": ts(), "event": "wheel",
                    "x": round(x / sw, 6), "y": round(y / sh, 6),
                    "wx": dx, "wy": dy
                })

            def on_key_press(key):
                if not self._recording: return
                try:
                    vk = key.vk
                except AttributeError:
                    try:
                        vk = key.value.vk
                    except Exception:
                        vk = 0
                # 停止热键由 RegisterHotKey 线程负责，此处不再处理 F10
                if vk:
                    self._events.append({
                        "type": "EK", "time": ts(), "event": "key_down", "vk_code": vk
                    })

            def on_key_release(key):
                if not self._recording: return
                try:
                    vk = key.vk
                except AttributeError:
                    try:
                        vk = key.value.vk
                    except Exception:
                        vk = 0
                if vk:
                    self._events.append({
                        "type": "EK", "time": ts(), "event": "key_up", "vk_code": vk
                    })

            with pm.Listener(on_move=on_move, on_click=on_click, on_scroll=on_scroll) as ml, \
                 pk.Listener(on_press=on_key_press, on_release=on_key_release) as kl:
                ml.join()
                kl.stop()

        self._rec_thread = threading.Thread(target=record_loop, daemon=True)
        self._rec_thread.start()

        # 启动 RegisterHotKey 线程监听停止热键（最小化后仍有效）
        self._start_stop_hotkey_watcher(MacroRecorderWidget.stop_hotkey)

    def _start_stop_hotkey_watcher(self, hotkey_str: str):
        """
        后台线程：用 GetAsyncKeyState bit0 轮询停止录制热键，最小化后仍可触发。
        使用 bit0（曾被按下标志）+ 5ms 轮询，不会漏检快速轻敲。
        """
        import threading
        self._stop_hotkey_stop_event = threading.Event()
        _, vk = CoordOverlay._parse_vk(hotkey_str)

        def _watcher():
            import ctypes, time
            GetAsyncKeyState = ctypes.windll.user32.GetAsyncKeyState

            # 等待启动余震 + 清掉积累的 bit0
            time.sleep(0.3)
            if vk:
                GetAsyncKeyState(vk)  # 清掉积累的 bit0

            while not self._stop_hotkey_stop_event.is_set():
                # bit0：自上次读取后"曾经被按下"过
                if vk and (GetAsyncKeyState(vk) & 0x0001):
                    if not self._stop_hotkey_stop_event.is_set():
                        try:
                            self._stop_signal.emit()
                        except RuntimeError:
                            pass
                    break
                time.sleep(0.005)  # 200Hz 轮询

        self._stop_hotkey_thread = threading.Thread(target=_watcher, daemon=True,
                                                     name="macro-stop-hotkey")
        self._stop_hotkey_thread.start()

    def _kill_stop_hotkey_watcher(self):
        """通知停止热键监视线程退出"""
        if hasattr(self, '_stop_hotkey_stop_event') and self._stop_hotkey_stop_event:
            self._stop_hotkey_stop_event.set()

    def _stop_record(self):
        self._kill_stop_hotkey_watcher()
        self._recording = False
        self._data = list(self._events)
        self._btn_record.setText("⏺ 重新录制")
        self._btn_record.setStyleSheet("")
        self._status_lbl.setText(f"录制完成 ✔")
        self._status_lbl.setStyleSheet("font-size: 11px; color: #A6E3A1;")
        self._count_lbl.setText(f"{len(self._data)} 个事件")

    def _clear_data(self):
        self._data = []
        self._events = []
        self._status_lbl.setText("已清空")
        self._status_lbl.setStyleSheet("font-size: 11px;")
        self._count_lbl.setText("0 个事件")

    def _preview_data(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("宏事件预览")
        dlg.setMinimumSize(520, 380)
        lay = QVBoxLayout(dlg)
        tbl = QTableWidget(len(self._data), 4)
        tbl.setHorizontalHeaderLabels(["时间(ms)", "类型", "事件", "坐标/VK"])
        tbl.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for row, ev in enumerate(self._data):
            tbl.setItem(row, 0, QTableWidgetItem(str(ev.get("time", 0))))
            tbl.setItem(row, 1, QTableWidgetItem(ev.get("type", "")))
            tbl.setItem(row, 2, QTableWidgetItem(ev.get("event", "")))
            if ev.get("type") == "EM":
                detail = f"({ev.get('x',0):.4f}, {ev.get('y',0):.4f})"
            else:
                detail = f"VK={ev.get('vk_code','')}"
            tbl.setItem(row, 3, QTableWidgetItem(detail))
        lay.addWidget(tbl)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dlg.accept)
        lay.addWidget(close_btn)
        dlg.exec()

    def get_data(self) -> list:
        return list(self._data)


# ─────────────────── 插入提示线控件 ───────────────────

class InsertHandle(QWidget):
    """
    功能块之间的插入提示线。
    平时只占 8px 高度（透明间隔）；
    鼠标进入时展开为 26px，显示一条橙色横线和「＋」按钮；
    点击「＋」按钮触发 insert_requested 信号，携带插入位置索引。
    """
    insert_requested = pyqtSignal(int)   # 发出插入位置（在 _blocks 中的下标）

    _H_IDLE = 8
    _H_HOVER = 26

    def __init__(self, insert_pos: int, parent=None):
        super().__init__(parent)
        self._insert_pos = insert_pos
        self.setFixedHeight(self._H_IDLE)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)
        self._hovered = False
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(0)

        # 左侧横线
        self._line_l = QFrame()
        self._line_l.setFrameShape(QFrame.Shape.HLine)
        self._line_l.setStyleSheet("color: #FF9A3C; background: #FF9A3C; max-height: 2px; border: none;")
        self._line_l.hide()

        # 「＋」按钮
        self._btn = QPushButton("＋")
        self._btn.setFixedSize(20, 20)
        self._btn.setStyleSheet(
            "QPushButton { background: #FF9A3C; color: #1E1E2E; border: none; border-radius: 10px;"
            " font-size: 14px; font-weight: bold; padding: 0; }"
            "QPushButton:hover { background: #FFB347; }"
        )
        self._btn.setToolTip("在此处插入功能块")
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.hide()
        self._btn.clicked.connect(lambda: self.insert_requested.emit(self._insert_pos))

        # 右侧横线
        self._line_r = QFrame()
        self._line_r.setFrameShape(QFrame.Shape.HLine)
        self._line_r.setStyleSheet("color: #FF9A3C; background: #FF9A3C; max-height: 2px; border: none;")
        self._line_r.hide()

        layout.addWidget(self._line_l, 1)
        layout.addWidget(self._btn)
        layout.addWidget(self._line_r, 1)

    def enterEvent(self, event):
        self._hovered = True
        self.setFixedHeight(self._H_HOVER)
        self._line_l.show()
        self._btn.show()
        self._line_r.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.setFixedHeight(self._H_IDLE)
        self._line_l.hide()
        self._btn.hide()
        self._line_r.hide()
        super().leaveEvent(event)

    def update_pos(self, insert_pos: int):
        """刷新后更新插入位置（循环复用时使用）"""
        self._insert_pos = insert_pos


# ─────────────────── 功能块列表面板（积木流） ───────────────────

class BlockListWidget(QWidget):
    changed           = pyqtSignal()
    run_single_block  = pyqtSignal(object)   # 发出: Block 对象（运行此单块）
    run_from_block    = pyqtSignal(int)      # 发出: 起始索引（从此处开始运行）
    # 只要有选中状态变更就发出（用于与 TriggerListWidget 互斥）
    selection_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._blocks: List[Block] = []
        self._card_widgets: List[QWidget] = []
        self._handle_widgets: List[QWidget] = []   # InsertHandle 插入提示线
        # 折叠状态：block_id -> bool（仅 loop/group 开始标记）
        self._collapsed: dict = {}
        # 多选状态
        self._selected_ids: set = set()
        self._multiselect_mode: bool = False
        self._anchor_block_id: str = None   # Shift多选的锚点块ID
        # 剪贴板（内部）
        self._clipboard_blocks: List[Block] = []
        # 防抖定时器：避免快速连续调用 _refresh() 时重复重建卡片
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(16)  # 约 1 帧（60fps）
        self._refresh_timer.timeout.connect(self._do_refresh)
        self._build_ui()
        # 接受拖拽
        self.setAcceptDrops(True)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 8)
        toolbar.setSpacing(6)

        self._section_lbl = QLabel(tr("block.section"))
        self._section_lbl.setObjectName("section_title")
        toolbar.addWidget(self._section_lbl)
        toolbar.addStretch()

        self._add_btn = QPushButton(tr("block.add"))
        self._add_btn.setObjectName("btn_primary")
        self._add_btn.clicked.connect(self._show_add_menu)
        toolbar.addWidget(self._add_btn)

        self._ai_gen_btn = QPushButton("✨ AI 生成")
        self._ai_gen_btn.setObjectName("btn_flat")
        self._ai_gen_btn.setToolTip("使用 AI 根据自然语言描述自动生成功能块序列")
        self._ai_gen_btn.clicked.connect(self._show_ai_generator)
        toolbar.addWidget(self._ai_gen_btn)

        self._clear_btn = QPushButton(tr("block.clear"))
        self._clear_btn.setObjectName("btn_danger")
        self._clear_btn.setToolTip(tr("block.clear_tip"))
        self._clear_btn.clicked.connect(self._clear_all_blocks)
        toolbar.addWidget(self._clear_btn)

        layout.addLayout(toolbar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._scroll_body = QWidget()
        self._body_layout = QVBoxLayout(self._scroll_body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(0)  # InsertHandle 自己控制间隔

        self._empty_hint = QLabel(tr("block.empty"))
        self._empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_hint.setStyleSheet(
            "color: #45475A; font-size: 13px; padding: 40px;"
            "border: 2px dashed #313244; border-radius: 12px; margin: 8px 0;"
        )
        self._body_layout.addWidget(self._empty_hint)
        self._body_layout.addStretch()

        scroll.setWidget(self._scroll_body)
        layout.addWidget(scroll)

    def retranslate(self):
        """语言切换后刷新固定文字控件"""
        self._section_lbl.setText(tr("block.section"))
        self._add_btn.setText(tr("block.add"))
        self._clear_btn.setText(tr("block.clear"))
        self._clear_btn.setToolTip(tr("block.clear_tip"))
        self._empty_hint.setText(tr("block.empty"))

    def _show_ai_generator(self):
        """弹出 AI 生成功能块对话框，生成后批量插入块"""
        # 获取 config —— MainWindow 将 config 存在 _project.config
        cfg = None
        from PyQt6.QtWidgets import QApplication as _QApp
        for _w in _QApp.topLevelWidgets():
            if hasattr(_w, '_project') and hasattr(_w._project, 'config'):
                cfg = _w._project.config
                break
        if cfg is None:
            top = self
            while top.parent():
                top = top.parent()
            if hasattr(top, '_project') and hasattr(top._project, 'config'):
                cfg = top._project.config

        dlg = AiBlockGeneratorDialog(config=cfg, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_blocks = dlg.get_generated_blocks()
        if not new_blocks:
            return
        insert_pos = dlg.get_insert_position()
        import copy as _copy
        if insert_pos == "start":
            for i, b in enumerate(new_blocks):
                self._blocks.insert(i, _copy.deepcopy(b))
        else:
            for b in new_blocks:
                self._blocks.append(_copy.deepcopy(b))
        self._refresh()
        self.changed.emit()



    def set_blocks(self, blocks: List[Block]):
        self._blocks = blocks
        self._refresh()

    def set_all_tasks(self, tasks):
        """注入全部任务列表（用于 task_picker 控件）"""
        self._all_tasks = tasks

    def get_blocks(self) -> List[Block]:
        return self._blocks

    def _refresh(self):
        """防抖刷新：在下一帧触发真正的重建（避免连续多次调用重复 UI 重建）"""
        if not self._refresh_timer.isActive():
            self._refresh_timer.start()

    def _do_refresh(self):
        # 清理旧卡片：先 hide() 立即视觉消失，再 removeWidget + deleteLater
        for card in self._card_widgets:
            card.hide()
            self._body_layout.removeWidget(card)
            card.deleteLater()
        self._card_widgets.clear()
        # 清理旧插入提示线
        for h in self._handle_widgets:
            h.hide()
            self._body_layout.removeWidget(h)
            h.deleteLater()
        self._handle_widgets.clear()

        self._empty_hint.setVisible(len(self._blocks) == 0)

        depth = 0
        skip_stack = []   # True=折叠中，False=展开中

        # 收集 (block, display_depth, block_list_idx) 列表，然后统一渲染带 InsertHandle
        visible_items = []   # List of (block, display_depth, block_list_idx)

        i = 0
        while i < len(self._blocks):
            block = self._blocks[i]
            bt    = block.block_type

            in_collapsed = any(skip_stack)

            if bt in _CLOSE_MARKERS:
                depth = max(0, depth - 1)
                was_collapsed = skip_stack.pop() if skip_stack else False
                outer_collapsed = any(skip_stack)
                if not outer_collapsed:
                    visible_items.append((block, depth, i))
                i += 1
                continue

            # elif_block/else_block：显示在 if 所在深度（depth-1）
            if bt in _IF_BRANCH_MARKERS:
                if in_collapsed:
                    i += 1
                    continue
                display_depth = max(0, depth - 1)
                visible_items.append((block, display_depth, i))
                i += 1
                continue

            if in_collapsed:
                if bt in _OPEN_MARKERS:
                    skip_stack.append(True)
                    depth += 1
                i += 1
                continue

            visible_items.append((block, depth, i))

            if bt in _OPEN_MARKERS:
                depth += 1
                skip_stack.append(self._collapsed.get(block.id, False))

            i += 1

        # 渲染：handle → card → handle → card → … → handle
        # body_layout 中位置 0 是 _empty_hint，所以从 1 开始插入，stretch 在末尾不受影响
        widget_idx = 1

        def _insert_handle(block_list_pos: int):
            """在 body_layout 的 widget_idx 位置插入一个 InsertHandle"""
            nonlocal widget_idx
            h = InsertHandle(block_list_pos)
            h.insert_requested.connect(self._insert_block_at)
            self._body_layout.insertWidget(widget_idx, h)
            self._handle_widgets.append(h)
            widget_idx += 1

        # 最顶端：插入到位置 0（列表最前面）
        _insert_handle(0)

        for block, disp_depth, blk_idx in visible_items:
            collapsed = self._collapsed.get(block.id, False)
            card = self._make_card(block, widget_idx, depth=disp_depth, collapsed=collapsed)
            self._body_layout.insertWidget(widget_idx, card)
            self._card_widgets.append(card)
            widget_idx += 1

            # 每个卡片后面插入一个 handle，插入位置为该 block 在 _blocks 中的下一位
            _insert_handle(blk_idx + 1)

        # ── 新卡片淡入动画（整体刷新时轻微淡入，提升流畅感）──
        from .effects import fade_in as _fade_in
        if self._card_widgets:
            for i, card in enumerate(self._card_widgets):
                # 延迟 8ms/张（最多 80ms），创造轻微层叠感
                # on_finished 清除 GraphicsEffect，避免残留影响后续重绘
                QTimer.singleShot(
                    min(i * 8, 80),
                    lambda c=card: _fade_in(c, 100, on_finished=lambda _c=c: _c.setGraphicsEffect(None))
                )

        # ── 强制刷新布局，消除删除/添加控件后的残影 ──
        self._body_layout.invalidate()
        self._body_layout.activate()
        self._scroll_body.update()



    def _make_card(self, block: Block, idx: int, depth: int = 0,
                   collapsed: bool = False) -> QWidget:
        try:
            card = BlockCard(block, depth=depth, collapsed=collapsed)
        except Exception as _e:
            import traceback
            # 渲染失败时生成一个占位错误卡片，不影响其他功能块
            err_card = QFrame()
            err_card.setFixedHeight(52)
            err_card.setStyleSheet(
                "QFrame { background: #3d1515; border: 1px solid #f38ba8;"
                "border-left: 4px solid #f38ba8; border-radius: 8px; margin: 2px 4px; }"
            )
            _lay = QHBoxLayout(err_card)
            _lay.setContentsMargins(12, 4, 8, 4)
            from PyQt6.QtWidgets import QLabel as _QL
            _lbl = _QL(f"⚠ 功能块 [{block.block_type}] 渲染失败：{_e}")
            _lbl.setStyleSheet("color: #f38ba8; font-size: 12px;")
            _lay.addWidget(_lbl)
            return err_card
        card.edit_requested.connect(lambda c: self._edit_block(c.block))
        card.delete_requested.connect(lambda c: self._delete_block(c.block))
        card.copy_requested.connect(lambda c: self._copy_block(c.block))
        card.move_up.connect(lambda c: self._move_block(c.block, -1))
        card.move_down.connect(lambda c: self._move_block(c.block, +1))
        card.toggle_collapse.connect(lambda c: self._toggle_collapse(c.block))
        card.add_elif.connect(lambda c: self._add_elif_to_if(c.block))
        card.toggle_else.connect(lambda c: self._toggle_else_of_if(c.block))
        # 右键菜单
        card.context_menu_requested.connect(self._show_block_context_menu)
        # 单击选中（单选/Shift多选）
        card.card_clicked.connect(self._on_card_clicked)
        # 双击直接打开编辑器
        card.card_double_clicked.connect(lambda c: self._edit_block(c.block))
        # 多选：复选框状态变化
        if hasattr(card, '_select_cb'):
            cb = card._select_cb
            cb.setVisible(self._multiselect_mode)
            cb.setChecked(block.id in self._selected_ids)
            cb.stateChanged.connect(
                lambda state, bid=block.id: self._on_select_toggle(bid, bool(state))
            )
        # 若是 if_block，标记是否已有 else 分支（更新按钮显示）
        if block.block_type == "if_block":
            has_else = self._if_has_else(block)
            card._else_active = has_else
            if hasattr(card, '_btn_else'):
                card._btn_else.setChecked(has_else)
                card._btn_else.setText("ELSE ✓" if has_else else "ELSE ☐")
        return card

    def _on_select_toggle(self, block_id: str, selected: bool):
        if selected:
            self._selected_ids.add(block_id)
        else:
            self._selected_ids.discard(block_id)

    def _on_card_clicked(self, card: "BlockCard", shift_held: bool):
        """
        处理功能块单击选中逻辑：
        - 普通单击：清空之前选中，只选中当前块（如果已选中则取消）
        - Shift单击：进入多选模式，连续选中上次选中块到当前块之间的所有块
        """
        bid = card.block.id

        if shift_held:
            # Shift 单击：进入多选模式，范围选中
            self._multiselect_mode = True
            # 找上一个锚点（最后单独选中的）
            if hasattr(self, '_anchor_block_id') and self._anchor_block_id:
                anchor_id = self._anchor_block_id
            elif self._selected_ids:
                anchor_id = next(iter(self._selected_ids))
            else:
                anchor_id = bid

            # 找两者在可见 card_widgets 中的索引
            card_ids = [c.block.id for c in self._card_widgets if hasattr(c, 'block')]
            try:
                a_idx = card_ids.index(anchor_id)
            except ValueError:
                a_idx = 0
            try:
                b_idx = card_ids.index(bid)
            except ValueError:
                b_idx = len(card_ids) - 1

            lo, hi = min(a_idx, b_idx), max(a_idx, b_idx)
            self._selected_ids = {card_ids[i] for i in range(lo, hi + 1)}
        else:
            # 普通单击
            if self._multiselect_mode and bid in self._selected_ids and len(self._selected_ids) == 1:
                # 再次点击唯一已选中块 → 退出多选、取消选中
                self._selected_ids.clear()
                self._multiselect_mode = False
                self._anchor_block_id = None
            elif not self._multiselect_mode and bid in self._selected_ids:
                # 非多选模式下再次点击已选中块 → 取消选中
                self._selected_ids.clear()
                self._anchor_block_id = None
            else:
                # 单选当前块，退出多选模式
                self._multiselect_mode = False
                self._selected_ids = {bid}
                self._anchor_block_id = bid

        # 同步所有卡片的视觉选中状态
        self._sync_selection_ui()


    def _sync_selection_ui(self):
        """根据 _selected_ids 和 _multiselect_mode 同步所有卡片的视觉状态"""
        for c in self._card_widgets:
            if not hasattr(c, 'block'):
                continue
            selected = c.block.id in self._selected_ids
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
        self._anchor_block_id = None
        self._multiselect_mode = False
        for c in self._card_widgets:
            if not hasattr(c, 'block'):
                continue
            c.set_selected(False)
            if hasattr(c, '_select_cb'):
                c._select_cb.setVisible(False)
                c._select_cb.blockSignals(True)
                c._select_cb.setChecked(False)
                c._select_cb.blockSignals(False)

    def mousePressEvent(self, event):
        """点击空白区域时取消所有选中"""
        # 判断是否点击了任何卡片内部
        from PyQt6.QtCore import Qt as _Qt
        if event.button() == _Qt.MouseButton.LeftButton:
            child = self.childAt(event.position().toPoint())
            # 如果点击的不是卡片内的任何子控件，则清空选中
            hit_card = False
            w = child
            while w is not None:
                if isinstance(w, BlockCard):
                    hit_card = True
                    break
                w = w.parent() if hasattr(w, 'parent') else None
            if not hit_card:
                self._selected_ids.clear()
                self._multiselect_mode = False
                self._anchor_block_id = None
                self._sync_selection_ui()
        super().mousePressEvent(event)



    def _show_block_context_menu(self, card: "BlockCard", global_pos):
        """显示功能块右键菜单"""
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        bt = card.block.block_type

        # ── 运行选项 ──
        act_run = menu.addAction("▶  运行此功能块")
        act_run_from = menu.addAction("▶▶  从此处开始运行")
        menu.addSeparator()

        # ── 编辑操作 ──
        if bt not in _CLOSE_MARKERS:
            act_edit = menu.addAction("✎  编辑")
        else:
            act_edit = None
        act_copy = menu.addAction("⎘  复制")
        act_cut  = menu.addAction("✂  剪切")
        act_paste = menu.addAction("📋  粘贴到此后")
        act_paste.setEnabled(bool(self._clipboard_blocks))
        menu.addSeparator()

        # ── 多选模式 ──
        act_multisel = menu.addAction(
            "☑  退出多选模式" if self._multiselect_mode else "☑  进入多选模式"
        )
        if self._multiselect_mode and self._selected_ids:
            act_del_sel = menu.addAction(f"🗑  删除已选中 ({len(self._selected_ids)} 个)")
            act_copy_sel = menu.addAction(f"⎘  复制已选中 ({len(self._selected_ids)} 个)")
        else:
            act_del_sel  = None
            act_copy_sel = None
        menu.addSeparator()

        # ── 删除 ──
        act_del = menu.addAction("✕  删除此块")

        action = menu.exec(global_pos)
        if not action:
            return

        if action == act_run:
            self._run_single_block(card.block)
        elif action == act_run_from:
            self._run_from_block(card.block)
        elif act_edit and action == act_edit:
            self._edit_block(card.block)
        elif action == act_copy:
            self._clipboard_blocks = self._get_block_segment(card.block)
        elif action == act_cut:
            self._clipboard_blocks = self._get_block_segment(card.block)
            self._delete_block_segment(card.block)
        elif action == act_paste:
            self._paste_after_block(card.block)
        elif action == act_multisel:
            self._toggle_multiselect_mode()
        elif act_del_sel and action == act_del_sel:
            self._delete_selected()
        elif act_copy_sel and action == act_copy_sel:
            self._copy_selected()
        elif action == act_del:
            self._delete_block(card.block)

    def _run_single_block(self, block: Block):
        """运行单个功能块——发出信号通知上层"""
        self.run_single_block.emit(block)

    def _run_from_block(self, block: Block):
        """从此功能块开始运行——发出起始索引信号通知上层"""
        idx = next((i for i, b in enumerate(self._blocks) if b.id == block.id), 0)
        self.run_from_block.emit(idx)

    def _toggle_multiselect_mode(self):
        self._multiselect_mode = not self._multiselect_mode
        if not self._multiselect_mode:
            self._selected_ids.clear()
            self._anchor_block_id = None
        self._sync_selection_ui()

    def _get_block_segment(self, block: Block) -> List[Block]:
        """获取 block 对应的完整片段（含 group/loop/if 的结束标记）"""
        idx = next((i for i, b in enumerate(self._blocks) if b.id == block.id), -1)
        if idx < 0:
            return []
        if block.block_type in _OPEN_MARKERS:
            pair_type = _PAIR_MAP[block.block_type]
            depth = 1; end_idx = idx + 1
            while end_idx < len(self._blocks) and depth > 0:
                if self._blocks[end_idx].block_type == block.block_type: depth += 1
                elif self._blocks[end_idx].block_type == pair_type: depth -= 1
                if depth > 0: end_idx += 1
                else: break
            return copy.deepcopy(self._blocks[idx: end_idx + 1])
        return [copy.deepcopy(block)]

    def _delete_block_segment(self, block: Block):
        """删除 block 对应的完整片段"""
        idx = next((i for i, b in enumerate(self._blocks) if b.id == block.id), -1)
        if idx < 0: return
        if block.block_type in _OPEN_MARKERS:
            pair_type = _PAIR_MAP[block.block_type]
            depth = 1; end_idx = idx + 1
            while end_idx < len(self._blocks) and depth > 0:
                if self._blocks[end_idx].block_type == block.block_type: depth += 1
                elif self._blocks[end_idx].block_type == pair_type: depth -= 1
                if depth > 0: end_idx += 1
                else: break
            del self._blocks[idx: end_idx + 1]
        else:
            del self._blocks[idx]
        self._refresh(); self.changed.emit()

    def _paste_after_block(self, block: Block):
        """粘贴剪贴板内容到 block 之后"""
        if not self._clipboard_blocks:
            return
        idx = next((i for i, b in enumerate(self._blocks) if b.id == block.id), -1)
        if idx < 0:
            idx = len(self._blocks) - 1
        # 重新生成 ID 避免冲突
        import uuid
        new_blocks = copy.deepcopy(self._clipboard_blocks)
        for b in new_blocks:
            b.id = str(uuid.uuid4())[:8]
        for i, nb in enumerate(new_blocks):
            self._blocks.insert(idx + 1 + i, nb)
        self._refresh(); self.changed.emit()

    def _delete_selected(self):
        if not self._selected_ids:
            return
        self._blocks = [b for b in self._blocks if b.id not in self._selected_ids]
        self._selected_ids.clear()
        self._multiselect_mode = False
        self._refresh(); self.changed.emit()

    def _copy_selected(self):
        selected = [b for b in self._blocks if b.id in self._selected_ids]
        if selected:
            self._clipboard_blocks = copy.deepcopy(selected)

    # ── 拖拽排序 ────────────────────────────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasText() and event.mimeData().text().startswith("block_drag:"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasText() and event.mimeData().text().startswith("block_drag:"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not (event.mimeData().hasText() and
                event.mimeData().text().startswith("block_drag:")):
            event.ignore()
            return

        drag_id = event.mimeData().text().split(":", 1)[1]
        drop_pos = event.position().toPoint()

        # 找到拖动的 block 索引
        drag_idx = next((i for i, b in enumerate(self._blocks) if b.id == drag_id), -1)
        if drag_idx < 0:
            event.ignore()
            return

        # 找到鼠标位置最近的 card，计算插入位置
        target_idx = drag_idx
        for i, card in enumerate(self._card_widgets):
            if hasattr(card, 'block'):
                card_pos = card.mapTo(self, card.rect().center())
                if drop_pos.y() < card_pos.y():
                    for j, b in enumerate(self._blocks):
                        if b.id == card.block.id:
                            target_idx = j
                            break
                    break
                else:
                    for j, b in enumerate(self._blocks):
                        if b.id == card.block.id:
                            target_idx = j + 1
                            break

        # ── 多选拖动：若被拖动的块在选中集合中，整组移动 ──
        if drag_id in self._selected_ids and len(self._selected_ids) > 1:
            # 按原始顺序收集选中块
            selected_blocks = [b for b in self._blocks if b.id in self._selected_ids]
            # 检查 target_idx 是否在被拖动块之间（无意义移动则忽略）
            sel_indices = {i for i, b in enumerate(self._blocks) if b.id in self._selected_ids}
            if target_idx in sel_indices:
                event.ignore()
                return
            # 移除所有选中块
            remaining = [b for b in self._blocks if b.id not in self._selected_ids]
            # 计算插入点（target_idx 在删除后的偏移）
            offset = sum(1 for idx in sel_indices if idx < target_idx)
            insert_at = target_idx - offset
            insert_at = max(0, min(insert_at, len(remaining)))
            # 插回
            for k, blk in enumerate(selected_blocks):
                remaining.insert(insert_at + k, blk)
            self._blocks[:] = remaining
            self._refresh()
            self.changed.emit()
            event.acceptProposedAction()
            return

        # ── 单块拖动 ──
        if target_idx == drag_idx or target_idx == drag_idx + 1:
            event.ignore()
            return

        drag_block = self._blocks.pop(drag_idx)
        if target_idx > drag_idx:
            target_idx -= 1
        self._blocks.insert(target_idx, drag_block)
        self._refresh()
        self.changed.emit()
        event.acceptProposedAction()

    def keyPressEvent(self, event):
        """键盘快捷键：多选模式下 Ctrl+C/X/Delete"""
        from PyQt6.QtCore import Qt as _Qt
        mods = event.modifiers()
        key  = event.key()
        if self._multiselect_mode and self._selected_ids:
            if mods & _Qt.KeyboardModifier.ControlModifier and key == _Qt.Key.Key_C:
                self._copy_selected()
                return
            elif mods & _Qt.KeyboardModifier.ControlModifier and key == _Qt.Key.Key_X:
                self._copy_selected()
                self._delete_selected()
                return
            elif key in (_Qt.Key.Key_Delete, _Qt.Key.Key_Backspace):
                self._delete_selected()
                return
        super().keyPressEvent(event)

    def _toggle_collapse(self, block: Block):
        bid = block.id
        self._collapsed[bid] = not self._collapsed.get(bid, False)
        self._refresh()

    def _copy_block(self, block: Block):
        """复制功能块（以及 open_marker 整个 group/loop 块）到其后面"""
        import uuid
        idx = next((i for i, b in enumerate(self._blocks) if b.id == block.id), -1)
        if idx < 0:
            return

        def _deep_copy_block(b: Block) -> Block:
            nb = Block(block_type=b.block_type)
            nb.params   = copy.deepcopy(b.params)
            nb.comment  = b.comment
            nb.enabled  = b.enabled
            return nb

        if block.block_type in _IF_BRANCH_MARKERS:
            # elif_block / else_block 单块复制（不包含内容）
            new_segment = [_deep_copy_block(block)]
            insert_at = idx + 1
        elif block.block_type in _OPEN_MARKERS:
            # 找到整个 group/loop/if 范围
            pair_type = _PAIR_MAP[block.block_type]
            depth = 1
            end_idx = idx + 1
            while end_idx < len(self._blocks) and depth > 0:
                if self._blocks[end_idx].block_type == block.block_type:
                    depth += 1
                elif self._blocks[end_idx].block_type == pair_type:
                    depth -= 1
                if depth > 0:
                    end_idx += 1
                else:
                    break
            segment = self._blocks[idx: end_idx + 1]
            new_segment = [_deep_copy_block(b) for b in segment]
            # group_end 继承颜色
            if block.block_type == "group" and len(new_segment) >= 2:
                new_segment[-1].params["color"] = new_segment[0].params.get("color", "#A080FF")
            insert_at = end_idx + 1
        else:
            new_segment = [_deep_copy_block(block)]
            insert_at = idx + 1

        for i, nb in enumerate(new_segment):
            self._blocks.insert(insert_at + i, nb)

        self._refresh()
        self.changed.emit()

    def _move_block(self, block: Block, direction: int):
        idx = next((i for i, b in enumerate(self._blocks) if b.id == block.id), -1)
        if idx < 0:
            return

        if block.block_type in _OPEN_MARKERS:
            pair_type = _PAIR_MAP[block.block_type]
            depth = 1
            end_idx = idx + 1
            while end_idx < len(self._blocks) and depth > 0:
                if self._blocks[end_idx].block_type == block.block_type:
                    depth += 1
                elif self._blocks[end_idx].block_type == pair_type:
                    depth -= 1
                if depth > 0:
                    end_idx += 1
                else:
                    break
            group = self._blocks[idx: end_idx + 1]
            if direction < 0:
                if idx == 0: return
                swap = [self._blocks[idx - 1]]
                self._blocks = (self._blocks[:idx - 1] + group + swap
                                + self._blocks[end_idx + 1:])
            else:
                if end_idx + 1 >= len(self._blocks): return
                swap = [self._blocks[end_idx + 1]]
                self._blocks = (self._blocks[:idx] + swap + group
                                + self._blocks[end_idx + 2:])

        elif block.block_type in _CLOSE_MARKERS:
            open_type = _PAIR_MAP[block.block_type]
            depth = 1
            loop_idx = idx - 1
            open_block = None
            while loop_idx >= 0 and depth > 0:
                if self._blocks[loop_idx].block_type == block.block_type:
                    depth += 1
                elif self._blocks[loop_idx].block_type == open_type:
                    depth -= 1
                    if depth == 0:
                        open_block = self._blocks[loop_idx]
                loop_idx -= 1
            if open_block:
                self._move_block(open_block, direction)
                return

        else:
            new_idx = idx + direction
            if new_idx < 0 or new_idx >= len(self._blocks):
                return
            self._blocks[idx], self._blocks[new_idx] = \
                self._blocks[new_idx], self._blocks[idx]

        self._refresh()
        self.changed.emit()

    def _show_add_menu(self):
        menu = self._build_block_menu(callback=self._add_block)
        menu.exec(QCursor.pos())

    def _clear_all_blocks(self):
        """清空所有功能块"""
        if not self._blocks:
            return
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, tr("block.clear"),
            tr("block.clear_confirm", len(self._blocks)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._blocks.clear()
        self._refresh()
        self.changed.emit()



    def _insert_block_at(self, pos: int):
        """InsertHandle 点击：在 _blocks[pos] 位置插入新块"""
        menu = self._build_block_menu(callback=lambda bt: self._add_block_at(bt, pos))
        menu.exec(QCursor.pos())

    def _build_block_menu(self, callback) -> QMenu:
        """构建分类功能块选择菜单，选中后调用 callback(block_type)"""
        menu = QMenu(self)
        categories: dict = {}
        _auto_types = {"loop_end", "group_end", "elif_block", "else_block", "if_end"}
        for bt, info in BLOCK_TYPES.items():
            if bt in _auto_types:
                continue
            cat = info.get("category", "其他")
            categories.setdefault(cat, []).append((bt, info))

        for cat, items in categories.items():
            sub = menu.addMenu(f"  {cat}")
            for bt, info in items:
                action = sub.addAction(f"{info['icon']}  {info['label']}")
                action.setData(bt)
                action.triggered.connect(lambda checked, b=bt: callback(b))
        return menu



    def _add_block(self, block_type: str):
        """在列表末尾添加块"""
        self._add_block_at(block_type, len(self._blocks))

    def _add_block_at(self, block_type: str, pos: int):
        """在 _blocks[pos] 位置插入块（pos == len 时追加到末尾）"""
        block = Block(block_type=block_type)
        spec  = BLOCK_PARAMS.get(block_type, {})
        block.params = {k: v["default"] for k, v in spec.items()}

        if spec and block_type not in _CLOSE_MARKERS and block_type not in _IF_BRANCH_MARKERS:
            dlg = BlockEditDialog(block, self, all_tasks=getattr(self, "_all_tasks", []))
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return

        insert_pos = max(0, min(pos, len(self._blocks)))

        if block_type == "if_block":
            if_end = Block(block_type="if_end")
            self._blocks.insert(insert_pos, block)
            self._blocks.insert(insert_pos + 1, if_end)
        elif block_type in _OPEN_MARKERS:
            pair_type = _PAIR_MAP[block_type]
            close_block = Block(block_type=pair_type)
            if block_type == "group":
                close_block.params["color"] = block.params.get("color", "#A080FF")
            self._blocks.insert(insert_pos, block)
            self._blocks.insert(insert_pos + 1, close_block)
        else:
            self._blocks.insert(insert_pos, block)

        self._refresh()
        self.changed.emit()



    def _if_has_else(self, if_block: Block) -> bool:
        """检查 if_block 对应区域内（外层）是否已有 else_block"""
        idx = next((i for i, b in enumerate(self._blocks) if b.id == if_block.id), -1)
        if idx < 0:
            return False
        depth = 1
        end_idx = idx + 1
        while end_idx < len(self._blocks) and depth > 0:
            bt2 = self._blocks[end_idx].block_type
            if bt2 == "if_block":
                depth += 1
            elif bt2 == "if_end":
                depth -= 1
            if depth > 0:
                end_idx += 1
            else:
                break
        inner_depth = 0
        for j in range(idx + 1, end_idx):
            bt2 = self._blocks[j].block_type
            if bt2 == "if_block":
                inner_depth += 1
            elif bt2 == "if_end":
                inner_depth -= 1
            elif inner_depth == 0 and bt2 == "else_block":
                return True
        return False

    def _toggle_else_of_if(self, if_block: Block):
        """切换 if_block 的 else 分支：有则删除，无则添加"""
        if self._if_has_else(if_block):
            # 找到并删除该 else_block
            idx = next((i for i, b in enumerate(self._blocks) if b.id == if_block.id), -1)
            if idx < 0:
                return
            depth_search = 1
            end_idx = idx + 1
            while end_idx < len(self._blocks) and depth_search > 0:
                bt2 = self._blocks[end_idx].block_type
                if bt2 == "if_block":
                    depth_search += 1
                elif bt2 == "if_end":
                    depth_search -= 1
                if depth_search > 0:
                    end_idx += 1
                else:
                    break
            inner_depth = 0
            for j in range(idx + 1, end_idx):
                bt2 = self._blocks[j].block_type
                if bt2 == "if_block":
                    inner_depth += 1
                elif bt2 == "if_end":
                    inner_depth -= 1
                elif inner_depth == 0 and bt2 == "else_block":
                    self._blocks.pop(j)
                    break
        else:
            self._add_else_to_if(if_block)
            return
        self._refresh()
        self.changed.emit()

    def _add_elif_to_if(self, if_block: Block):
        """在 if_block 对应的 if_end 前插入一个 elif_block"""
        idx = next((i for i, b in enumerate(self._blocks) if b.id == if_block.id), -1)
        if idx < 0:
            return
        # 找 if_end
        depth = 1
        end_idx = idx + 1
        while end_idx < len(self._blocks) and depth > 0:
            if self._blocks[end_idx].block_type == "if_block":
                depth += 1
            elif self._blocks[end_idx].block_type == "if_end":
                depth -= 1
            if depth > 0:
                end_idx += 1
            else:
                break
        # 新建 elif_block 并编辑
        elif_blk = Block(block_type="elif_block")
        spec = BLOCK_PARAMS.get("elif_block", {})
        elif_blk.params = {k: v["default"] for k, v in spec.items()}
        dlg = BlockEditDialog(elif_blk, self, all_tasks=getattr(self, "_all_tasks", []))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        # 插入到 if_end 之前
        self._blocks.insert(end_idx, elif_blk)
        self._refresh()
        self.changed.emit()

    def _add_else_to_if(self, if_block: Block):
        """在 if_block 对应的 if_end 前插入一个 else_block（如果没有的话）"""
        idx = next((i for i, b in enumerate(self._blocks) if b.id == if_block.id), -1)
        if idx < 0:
            return
        # 找 if_end（只看外层）
        depth = 1
        end_idx = idx + 1
        while end_idx < len(self._blocks) and depth > 0:
            if self._blocks[end_idx].block_type == "if_block":
                depth += 1
            elif self._blocks[end_idx].block_type == "if_end":
                depth -= 1
            if depth > 0:
                end_idx += 1
            else:
                break
        # 检查是否已有 else_block（只检查外层）
        inner_depth = 0
        for j in range(idx + 1, end_idx):
            bt2 = self._blocks[j].block_type
            if bt2 == "if_block":
                inner_depth += 1
            elif bt2 == "if_end":
                inner_depth -= 1
            elif inner_depth == 0 and bt2 == "else_block":
                from PyQt6.QtWidgets import QMessageBox as _QMB
                _QMB.information(self, "提示", "该 if 块已有 else 分支")
                return
        # 插入 else_block 到 if_end 之前
        else_blk = Block(block_type="else_block")
        self._blocks.insert(end_idx, else_blk)
        self._refresh()
        self.changed.emit()

    def _edit_block(self, block: Block):
        bt = block.block_type
        if bt in ("else_block", "if_end"):
            # 这些块无参数，编辑无意义
            return
        self._edit_block_dialog(block)

    def _edit_block_dialog(self, block: Block):
        dlg = BlockEditDialog(block, self, all_tasks=getattr(self, "_all_tasks", []))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh()
            self.changed.emit()



    def _delete_block(self, block: Block):
        if block.block_type in _IF_BRANCH_MARKERS:
            # elif_block / else_block 直接移除（不配对）
            self._blocks = [b for b in self._blocks if b.id != block.id]
        elif block.block_type in _OPEN_MARKERS:
            pair_type = _PAIR_MAP[block.block_type]
            result = []
            found = False
            skip_depth = 0
            for b in self._blocks:
                if not found:
                    if b.id == block.id:
                        found = True
                        skip_depth = 1
                    else:
                        result.append(b)
                else:
                    if b.block_type == block.block_type:
                        skip_depth += 1
                    elif b.block_type == pair_type:
                        skip_depth -= 1
                        if skip_depth == 0:
                            found = False
            self._blocks = result

        elif block.block_type in _CLOSE_MARKERS:
            open_type = _PAIR_MAP[block.block_type]
            end_pos = next((i for i, b in enumerate(self._blocks) if b.id == block.id), -1)
            if end_pos < 0: return
            depth = 1
            j = end_pos - 1
            open_block = None
            while j >= 0 and depth > 0:
                if self._blocks[j].block_type == block.block_type:
                    depth += 1
                elif self._blocks[j].block_type == open_type:
                    depth -= 1
                    if depth == 0:
                        open_block = self._blocks[j]
                j -= 1
            if open_block:
                self._delete_block(open_block)
                return

        else:
            self._blocks = [b for b in self._blocks if b.id != block.id]

        self._refresh()
        self.changed.emit()


# ─────────────────── AI 生成功能块对话框 ───────────────────

class AiBlockGeneratorDialog(QDialog):
    """
    AI 智能生成功能块对话框。
    用户输入自然语言描述，AI 返回结构化 JSON 功能块列表，
    预览后确认批量插入到编辑器。
    """
    # 用于从子线程安全回调主线程（PyQt6 跨线程必须用 Signal）
    _ai_result_signal = pyqtSignal(str, str)  # (raw_text, error)

    # AI 给 AutoFlow 的 system prompt（含所有可用功能块说明）
    _SYSTEM_PROMPT = """\
你是 AutoFlow 自动化工具的 AI 助手。AutoFlow 是一款积木式任务自动化工具，用户可以通过拼接"功能块"来创建自动化任务。

你的任务：根据用户的描述，生成一组功能块序列，以 JSON 数组格式返回。

【重要约束】
- "type" 字段必须从下方列出的名称中精确选取，区分大小写，禁止使用任何未列出的名称（如 delay、notification、action 等均无效）
- 参数必须放在 "params" 字段中（不是 config、data、properties 等其他名称）
- 直接输出 JSON 数组，不要 Markdown 代码块（不要 ```json），不要任何解释文字

【可用功能块及参数（type名称必须精确一致）】

流程控制:
- wait: params={duration: 秒数(数字)}  → 等待指定秒数
- if_block: params={condition_type:"process_exists"|"window_exists"|"file_exists"|"variable_equals"|"variable_gt"|"variable_lt"|"variable_contains"|"internet_connected"|"always_true", target:"目标值", value:"比较值", negate:false}
- if_end: params={}  → if_block的结束标记，必须成对出现
- elif_block: params={condition_type:..., target:..., value:..., negate:false}
- else_block: params={}
- loop: params={count:次数(0=无限), loop_var:"循环变量名"}
- loop_end: params={}  → loop的结束标记，必须成对出现
- break: params={}
- stop_task: params={}

应用&进程:
- launch_app: params={path:"程序路径"}  → 打开应用或文件
- close_window: params={title:"窗口标题关键词"}
- kill_process: params={name:"进程名.exe"}
- activate_window: params={title:"窗口标题关键词"}
- minimize_window: params={title:"窗口标题关键词"}
- maximize_window: params={title:"窗口标题关键词"}
- wait_window: params={title:"窗口标题关键词", timeout:30}
- wait_process: params={name:"进程名.exe", timeout:30}

文件操作:
- copy_file: params={src:"源路径", dst:"目标路径"}
- move_file: params={src:"源路径", dst:"目标路径"}
- delete_file: params={path:"文件路径"}
- read_file: params={path:"文件路径", var_name:"保存结果的变量名"}
- write_file: params={path:"文件路径", content:"内容", mode:"w"}

变量:
- set_variable: params={name:"变量名", value:"值"}
- calc_variable: params={name:"变量名", expr:"表达式如 {{x}}+1"}
- show_variable: params={name:"变量名"}

系统:
- exec_command: params={command:"命令内容", shell:"cmd", var_name:""}
- screenshot: params={path:"保存路径.png"}
- clipboard: params={action:"read", text:"", var_name:"变量名"}
- input_text: params={text:"要输入的文字"}
- http_request: params={url:"URL", method:"GET", body:"", var_name:"结果变量名"}
- open_url: params={url:"网址"}
- shutdown: params={action:"shutdown"}
- lock_computer: params={}
- turn_off_display: params={}

通知&消息:
- notify: params={title:"通知标题", message:"通知内容"}  → 发送系统通知
- msgbox: params={title:"标题", message:"消息内容", level:"info"}  → 弹出对话框
- log_message: params={message:"日志内容"}
- play_sound: params={path:"音频文件路径"}

键鼠操作:
- keyboard: params={keys:"组合键如 ctrl+c"}
- input_text: params={text:"输入文字"}
- mouse_move: params={pos:{x:100,y:200}, duration:0.3}
- mouse_click_pos: params={pos:{x:100,y:200}, button:"left"}
- mouse_scroll: params={amount:3, direction:"down"}
- mouse_drag: params={from_pos:{x:0,y:0}, to_pos:{x:100,y:100}}

媒体控制:
- volume_set: params={level:50, mode:"global"}
- media_play: params={}
- media_next: params={}
- media_prev: params={}

任务控制:
- run_task: params={task_name:"任务名"}
- stop_other_task: params={task_name:"任务名"}

AI:
- ai_chat: params={prompt:"提示词", var_name:"输出变量名"}
- ai_generate: params={prompt:"提示词", var_name:"输出变量名"}

【输出格式（严格遵守）】
直接输出如下 JSON 数组，无任何前缀或后缀：
[
  {"type": "wait", "params": {"duration": 3}, "comment": "等待3秒"},
  {"type": "notify", "params": {"title": "完成", "message": "任务结束"}, "comment": "发送通知"}
]

注意：
1. if_block 必须有对应的 if_end；loop 必须有对应的 loop_end
2. comment 字段用简短中文说明该步骤作用
3. type 名称必须与上面列表完全一致，大小写敏感
4. 禁止使用 delay/notification/sleep/alert 等未列出的 type 名
"""


    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self._config = config
        self._generated_blocks: List[Block] = []
        self.setWindowTitle("✨ AI 智能生成功能块")
        self.setMinimumSize(700, 580)
        self.setModal(True)
        # 连接跨线程信号（子线程 emit → 主线程执行）
        self._ai_result_signal.connect(self._on_ai_done)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(20, 16, 20, 16)

        # ── 顶部说明 ──
        hint = QLabel(
            "描述你想要实现的自动化任务，AI 将自动生成对应的功能块序列。\n"
            "例如：「每隔5秒截图保存到桌面，共截10次」「如果记事本已打开则关闭它」"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #A0A0C0; font-size: 12px; padding: 6px 0;")
        root.addWidget(hint)

        # ── 描述输入区 ──
        desc_label = QLabel("📝  任务描述")
        desc_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        root.addWidget(desc_label)

        self._desc_edit = QTextEdit()
        self._desc_edit.setPlaceholderText(
            "在这里输入你想实现的自动化任务描述...\n\n"
            "示例：\n"
            "• 打开微信，等待3秒，然后截图保存到 D:/screenshots/\n"
            "• 循环10次：点击坐标(500,300)，等待1秒\n"
            "• 检查 Chrome 进程是否存在，如果存在则关闭它，否则显示通知"
        )
        self._desc_edit.setMinimumHeight(100)
        self._desc_edit.setMaximumHeight(130)
        root.addWidget(self._desc_edit)

        # ── 生成按钮行 ──
        gen_row = QHBoxLayout()
        gen_row.setSpacing(8)

        self._gen_btn = QPushButton("🤖  AI 生成功能块")
        self._gen_btn.setObjectName("btn_primary")
        self._gen_btn.setFixedHeight(34)
        self._gen_btn.clicked.connect(self._do_generate)
        gen_row.addWidget(self._gen_btn)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color: #A0A0C0; font-size: 12px;")
        gen_row.addWidget(self._status_lbl, 1)
        root.addLayout(gen_row)

        # ── 预览区标题 ──
        preview_row = QHBoxLayout()
        preview_label = QLabel("👁  生成预览")
        preview_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        preview_row.addWidget(preview_label)
        preview_row.addStretch()
        self._count_lbl = QLabel("共 0 个功能块")
        self._count_lbl.setStyleSheet("color: #A0A0C0; font-size: 12px;")
        preview_row.addWidget(self._count_lbl)
        root.addLayout(preview_row)

        # ── 预览列表 ──
        self._preview_list = QListWidget()
        self._preview_list.setAlternatingRowColors(True)
        self._preview_list.setStyleSheet(
            "QListWidget { border: 1px solid #313244; border-radius: 8px;"
            " background: #1E1E2E; font-size: 12px; }"
            "QListWidget::item { padding: 5px 8px; }"
            "QListWidget::item:alternate { background: #252535; }"
            "QListWidget::item:selected { background: #6366F1; color: white; }"
        )
        self._preview_list.setMinimumHeight(150)
        root.addWidget(self._preview_list, 1)

        # ── 插入位置选择 ──
        pos_row = QHBoxLayout()
        pos_lbl = QLabel("插入位置：")
        pos_lbl.setStyleSheet("font-size: 12px;")
        pos_row.addWidget(pos_lbl)
        self._pos_combo = QComboBox()
        self._pos_combo.addItem("追加到末尾", "end")
        self._pos_combo.addItem("插入到开头", "start")
        self._pos_combo.setFixedWidth(150)
        pos_row.addWidget(self._pos_combo)
        pos_row.addStretch()
        root.addLayout(pos_row)

        # ── 底部按钮 ──
        btns_row = QHBoxLayout()
        btns_row.addStretch()
        self._ok_btn = QPushButton("✅  插入到任务")
        self._ok_btn.setObjectName("btn_primary")
        self._ok_btn.setFixedHeight(32)
        self._ok_btn.setEnabled(False)
        self._ok_btn.clicked.connect(self._on_accept)
        btns_row.addWidget(self._ok_btn)
        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedHeight(32)
        cancel_btn.clicked.connect(self.reject)
        btns_row.addWidget(cancel_btn)
        root.addLayout(btns_row)

    def _do_generate(self):
        desc = self._desc_edit.toPlainText().strip()
        if not desc:
            QMessageBox.warning(self, "提示", "请先输入任务描述。")
            return

        # 获取 AI 配置 —— MainWindow 将 config 存在 _project.config
        cfg = self._config
        if not cfg:
            from PyQt6.QtWidgets import QApplication as _QApp
            for _w in _QApp.topLevelWidgets():
                if hasattr(_w, '_project') and hasattr(_w._project, 'config'):
                    cfg = _w._project.config
                    break
        if not cfg:
            top = self
            while top.parent():
                top = top.parent()
            if hasattr(top, '_project') and hasattr(top._project, 'config'):
                cfg = top._project.config
        if not cfg or not getattr(cfg, 'ai_api_key', '').strip():
            QMessageBox.warning(self, "AI 未配置",
                "请先在「设置 → AI」中配置 API Key，然后再使用 AI 生成功能块。")
            return

        self._gen_btn.setEnabled(False)
        self._gen_btn.setText("⏳  生成中，请稍候...")
        self._status_lbl.setText("")
        self._preview_list.clear()
        self._ok_btn.setEnabled(False)
        self._count_lbl.setText("共 0 个功能块")
        self._generated_blocks = []

        import threading, urllib.request, json as _json, ssl

        system_prompt = self._SYSTEM_PROMPT
        user_prompt = f"请为以下任务描述生成 AutoFlow 功能块序列：\n\n{desc}"
        # 保存 cfg 引用供子线程使用
        _cfg = cfg
        _sig = self._ai_result_signal  # 信号引用，子线程安全 emit

        def _do_ai():
            try:
                base_url = getattr(_cfg, 'ai_base_url', '').strip() or "https://api.openai.com/v1"
                api_key  = getattr(_cfg, 'ai_api_key', '').strip()
                model    = getattr(_cfg, 'ai_model', 'gpt-4o-mini')
                temp     = getattr(_cfg, 'ai_temperature', 0.3)
                max_tok  = getattr(_cfg, 'ai_max_tokens', 2048)

                payload = _json.dumps({
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_prompt},
                    ],
                    "temperature": float(temp),
                    "max_tokens":  int(max_tok),
                }).encode("utf-8")

                endpoint = base_url.rstrip("/") + "/chat/completions"
                req = urllib.request.Request(
                    endpoint,
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}",
                    },
                    method="POST",
                )
                # 忽略 SSL 证书验证（兼容国内代理 API）
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with urllib.request.urlopen(req, context=ctx, timeout=90) as resp:
                    data = _json.loads(resp.read().decode("utf-8"))
                raw = data["choices"][0]["message"]["content"].strip()
                # 去掉可能的 markdown 代码块包裹
                if raw.startswith("```"):
                    lines = raw.splitlines()
                    raw = "\n".join(l for l in lines if not l.startswith("```")).strip()
                _sig.emit(raw, "")  # 成功：通过信号安全回调主线程
            except Exception as e:
                import traceback
                err = traceback.format_exc()
                _sig.emit("", err)  # 失败：通过信号安全回调主线程

        threading.Thread(target=_do_ai, daemon=True).start()

    def _on_ai_done(self, raw_text: str, error: str):
        """AI 调用完成后的回调（由信号触发，在主线程执行）"""
        self._gen_btn.setEnabled(True)
        self._gen_btn.setText("🤖  AI 生成功能块")
        if error:
            # 提取最后一行作为简短提示
            short = error.strip().splitlines()[-1] if error.strip() else "未知错误"
            self._status_lbl.setText(f"❌ {short}")
            QMessageBox.critical(self, "AI 生成失败",
                f"调用 AI 时出错，请检查：\n"
                f"• API Key 是否正确\n"
                f"• Base URL 是否填写正确（如 https://api.deepseek.com/v1）\n"
                f"• 网络是否可以访问该接口\n\n"
                f"详细错误：\n{error}")
            return
        if not raw_text:
            self._status_lbl.setText("❌ AI 返回了空内容")
            return
        self._parse_and_preview(raw_text)

    def _parse_and_preview(self, raw_text: str):
        """解析 AI 返回的 JSON，转换为 Block 列表并显示预览"""
        import json as _json

        raw = raw_text.strip()
        # 找到 JSON 数组范围
        start = raw.find("[")
        end   = raw.rfind("]")
        if start == -1 or end == -1 or end <= start:
            self._status_lbl.setText("❌ AI 返回格式错误，未找到 JSON 数组")
            QMessageBox.warning(self, "解析失败",
                f"AI 返回内容无法识别为功能块列表。\n\n原始内容（前300字）：\n{raw[:300]}")
            return

        json_str = raw[start:end + 1]
        try:
            items = _json.loads(json_str)
        except Exception as e:
            self._status_lbl.setText(f"❌ JSON 解析失败")
            QMessageBox.warning(self, "解析失败",
                f"JSON 解析错误：{e}\n\n原始内容（前400字）：\n{json_str[:400]}")
            return

        if not isinstance(items, list) or len(items) == 0:
            self._status_lbl.setText("❌ AI 返回了空列表")
            return

        blocks = []
        warnings = []
        # AI 常见误用名称 → 正确 AutoFlow type 映射
        _TYPE_ALIAS = {
            "delay": "wait", "sleep": "wait", "pause": "wait",
            "notification": "notify", "alert": "notify", "toast": "notify",
            "dialog": "msgbox", "message_box": "msgbox", "popup": "msgbox",
            "run_command": "exec_command", "execute": "exec_command", "command": "exec_command",
            "open_app": "launch_app", "start_app": "launch_app", "run_app": "launch_app",
            "open_file": "launch_app", "start": "launch_app",
            "end_if": "if_end", "endif": "if_end", "fi": "if_end",
            "end_loop": "loop_end", "endloop": "loop_end",
            "type_text": "input_text", "type": "input_text",
            "click": "mouse_click_pos", "mouse_click": "mouse_click_pos",
            "move_mouse": "mouse_move", "scroll": "mouse_scroll",
            "press_key": "keyboard", "key_press": "keyboard", "hotkey": "keyboard",
            "send_notification": "notify", "show_notification": "notify",
            "set_var": "set_variable", "variable": "set_variable",
        }
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                warnings.append(f"第{i+1}项不是对象，已跳过")
                continue
            btype = item.get("type", "").strip()
            if not btype:
                warnings.append(f"第{i+1}项缺少 type 字段，已跳过")
                continue
            # 自动映射常见别名到正确 type
            if btype not in BLOCK_TYPES:
                mapped = _TYPE_ALIAS.get(btype) or _TYPE_ALIAS.get(btype.lower())
                if mapped and mapped in BLOCK_TYPES:
                    btype = mapped
            if btype not in BLOCK_TYPES:
                warnings.append(f"第{i+1}项类型 '{item.get('type')}' 不存在，已跳过")
                continue

            block = Block(block_type=btype)
            spec = BLOCK_PARAMS.get(btype, {})
            block.params = {k: v["default"] for k, v in spec.items()}
            # 兼容 AI 返回 params/config/data/properties 等不同字段名
            ai_params = (item.get("params") or item.get("config") or
                         item.get("data") or item.get("properties") or {})
            if isinstance(ai_params, dict):
                for k, v in ai_params.items():
                    block.params[k] = v
            block.comment = item.get("comment", "")
            blocks.append(block)

        if not blocks:
            self._status_lbl.setText("❌ 没有生成有效的功能块")
            if warnings:
                QMessageBox.warning(self, "生成失败",
                    "没有生成有效的功能块。\n问题：\n" + "\n".join(warnings[:5]))
            return

        self._generated_blocks = blocks

        # 显示预览
        self._preview_list.clear()
        from PyQt6.QtGui import QColor as _QColor
        for idx, block in enumerate(blocks):
            info  = BLOCK_TYPES.get(block.block_type, {})
            icon  = info.get("icon", "▪")
            label = info.get("label", block.block_type)
            comment = f"  — {block.comment}" if block.comment else ""
            # 简略显示参数
            param_parts = []
            for k, v in list(block.params.items())[:3]:
                sv = str(v)
                if sv not in ("", "None", "{}", "[]", "False"):
                    param_parts.append(sv[:22])
            param_str = "  [" + ", ".join(param_parts) + "]" if param_parts else ""
            list_item = QListWidgetItem(f"  {idx+1:>2}. {icon}  {label}{param_str}{comment}")
            list_item.setForeground(_QColor(info.get("color", "#A0A0C0")))
            self._preview_list.addItem(list_item)

        warn_msg = f"  （{len(warnings)} 项被跳过）" if warnings else ""
        self._status_lbl.setText(f"✅ 成功生成 {len(blocks)} 个功能块{warn_msg}")
        self._count_lbl.setText(f"共 {len(blocks)} 个功能块")
        self._ok_btn.setEnabled(True)

        # 如果含有 launch_app 块，给出醒目的路径核对提示
        launch_blocks = [b for b in blocks if b.block_type == "launch_app"]
        if launch_blocks:
            names = [b.params.get("path", "（未填路径）") or "（未填路径）" for b in launch_blocks]
            names_str = "\n".join(f"  • {n}" for n in names[:5])
            extra = f"\n  …共 {len(launch_blocks)} 处" if len(launch_blocks) > 5 else ""
            QMessageBox.warning(
                self, "⚠️ 请手动核对应用路径",
                f"AI 生成的脚本包含 {len(launch_blocks)} 个「打开应用/文件」功能块：\n\n"
                f"{names_str}{extra}\n\n"
                f"AI 通常不知道软件在你电脑上的实际安装路径，\n"
                f"插入后请双击这些功能块，点击「📋 应用」从已安装列表选择，\n"
                f"或点击「📂 浏览」手动定位 .exe 文件。"
            )

    def get_generated_blocks(self) -> List[Block]:
        return self._generated_blocks

    def get_insert_position(self) -> str:
        return self._pos_combo.currentData() or "end"

    def _on_accept(self):
        if not self._generated_blocks:
            QMessageBox.warning(self, "提示", "还没有生成功能块，请先点击「AI 生成功能块」。")
            return
        self.accept()


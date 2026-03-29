"""
日志面板 —— 颜色跟随主题系统，不硬编码深色
"""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QTextCharFormat, QTextCursor, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QFrame
)
from datetime import datetime


class LogPanel(QWidget):
    """运行日志面板，背景/前景色由外部主题 QSS 控制，日志级别颜色在 append 时动态指定"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._max_lines = 2000
        # 当前级别颜色（会被 update_theme_colors 更新）
        self._colors = {
            "INFO":  "#A6E3A1",
            "WARN":  "#F9E2AF",
            "ERROR": "#F38BA8",
            "DEBUG": "#888888",
        }
        self._ts_color  = "#888888"
        self._msg_color = "#CCCCCC"
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 标题栏（由 QSS 控制颜色，不写死） ──
        bar = QFrame()
        bar.setObjectName("log_bar")
        bar.setFixedHeight(32)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(10, 0, 8, 0)
        bl.setSpacing(0)

        lbl = QLabel("📋  运行日志")
        lbl.setObjectName("log_title")
        bl.addWidget(lbl)
        bl.addStretch()

        clear_btn = QPushButton("清空")
        clear_btn.setObjectName("log_clear_btn")
        clear_btn.clicked.connect(self.clear)
        bl.addWidget(clear_btn)
        layout.addWidget(bar)

        # ── 日志文本区（背景/前景由 QSS 控制） ──
        self._log_view = QTextEdit()
        self._log_view.setObjectName("log_view")
        self._log_view.setReadOnly(True)
        self._log_view.setFont(QFont("Consolas", 10))
        layout.addWidget(self._log_view)

    def update_theme_colors(self, palette: dict):
        """
        由主窗口在切换主题时调用，传入当前 PALETTES 调色板字典。
        palette 包含 bg1, bg0, fg0, fg1, fg2, success, warn, danger 等 key。
        """
        is_dark = palette.get("mode", "dark") == "dark"

        self._colors = {
            "INFO":  palette.get("success", "#A6E3A1"),
            "WARN":  palette.get("warn",    "#F9E2AF"),
            "ERROR": palette.get("danger",  "#F38BA8"),
            "DEBUG": palette.get("fg2",     "#888888"),
        }
        self._ts_color  = palette.get("fg2", "#888888")
        self._msg_color = palette.get("fg0", "#CCCCCC")

        # 用 QSS 刷新 log_view 背景/前景
        bg  = palette.get("bg1", "#181825") if is_dark else palette.get("bg1", "#EBEBEB")
        fg  = palette.get("fg0", "#CDD6F4")
        bar_bg  = palette.get("bg1", "#181825") if is_dark else palette.get("bg0", "#F5F5F5")
        bar_fg  = palette.get("fg2", "#6C7086")
        btn_fg  = palette.get("fg2", "#6C7086")
        btn_hover = palette.get("fg0", "#CDD6F4")
        border = palette.get("bg3", "#313244")

        self._log_view.setStyleSheet(f"""
            QTextEdit#log_view {{
                background-color: {bg};
                color: {fg};
                border: none;
                padding: 6px;
            }}
        """)
        self.findChild(QFrame, "log_bar").setStyleSheet(
            f"QFrame#log_bar {{ background-color: {bar_bg}; border-top: 1px solid {border}; }}"
        )
        self.findChild(QLabel, "log_title").setStyleSheet(
            f"color: {bar_fg}; font-size: 11px; font-weight: bold;"
        )
        self.findChild(QPushButton, "log_clear_btn").setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {btn_fg}; font-size: 11px; padding: 2px 8px;
            }}
            QPushButton:hover {{ color: {btn_hover}; }}
        """)

    def append(self, level: str, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        color = self._colors.get(level.upper(), self._msg_color)

        cursor = self._log_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        def append_colored(text, hex_color, bold=False):
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(hex_color))
            if bold:
                fmt.setFontWeight(QFont.Weight.Bold)
            cursor.insertText(text, fmt)

        append_colored(f"[{timestamp}] ", self._ts_color)
        append_colored(f"{level:<5} ", color, bold=True)
        append_colored(message + "\n", self._msg_color)

        self._log_view.setTextCursor(cursor)
        self._log_view.ensureCursorVisible()

        # 限制行数
        doc = self._log_view.document()
        while doc.blockCount() > self._max_lines:
            cursor2 = QTextCursor(doc.firstBlock())
            cursor2.select(QTextCursor.SelectionType.BlockUnderCursor)
            cursor2.movePosition(QTextCursor.MoveOperation.NextBlock,
                                  QTextCursor.MoveMode.KeepAnchor)
            cursor2.removeSelectedText()

    def clear(self):
        self._log_view.clear()

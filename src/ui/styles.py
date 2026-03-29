"""
AutoFlow 样式表
深色主题
"""

DARK_STYLE = """
QWidget {
    background-color: #1E1E2E;
    color: #CDD6F4;
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 13px;
}

QMainWindow {
    background-color: #1E1E2E;
}

/* ─── 侧边栏 ─── */
#sidebar {
    background-color: #181825;
    border-right: 1px solid #313244;
    min-width: 200px;
    max-width: 200px;
}

#sidebar QPushButton {
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 10px 14px;
    text-align: left;
    font-size: 13px;
    color: #A6ADC8;
}

#sidebar QPushButton:hover {
    background-color: #313244;
    color: #CDD6F4;
}

#sidebar QPushButton[active="true"] {
    background-color: #89B4FA22;
    color: #89B4FA;
    border-left: 3px solid #89B4FA;
}

#app_title {
    font-size: 18px;
    font-weight: bold;
    color: #89B4FA;
    padding: 20px 14px 10px 14px;
}

#app_subtitle {
    font-size: 10px;
    color: #6C7086;
    padding: 0 14px 16px 14px;
}

/* ─── 工具栏 ─── */
#toolbar {
    background-color: #181825;
    border-bottom: 1px solid #313244;
    padding: 8px 16px;
}

/* ─── 主按钮 ─── */
QPushButton#btn_primary {
    background-color: #89B4FA;
    color: #1E1E2E;
    border: none;
    border-radius: 8px;
    padding: 7px 16px;
    font-weight: bold;
}
QPushButton#btn_primary:hover { background-color: #74C7EC; }
QPushButton#btn_primary:pressed { background-color: #6EC3E5; }

QPushButton#btn_danger {
    background-color: #F38BA8;
    color: #1E1E2E;
    border: none;
    border-radius: 8px;
    padding: 7px 16px;
    font-weight: bold;
}
QPushButton#btn_danger:hover { background-color: #EBA0AC; }

QPushButton#btn_success {
    background-color: #A6E3A1;
    color: #1E1E2E;
    border: none;
    border-radius: 8px;
    padding: 7px 16px;
    font-weight: bold;
}
QPushButton#btn_success:hover { background-color: #94E2A0; }

QPushButton#btn_warning {
    background-color: #FAB387;
    color: #1E1E2E;
    border: none;
    border-radius: 8px;
    padding: 7px 16px;
    font-weight: bold;
}
QPushButton#btn_warning:hover { background-color: #F5A87A; }

QPushButton#btn_flat {
    background: transparent;
    border: 1px solid #45475A;
    border-radius: 8px;
    padding: 7px 14px;
    color: #BAC2DE;
}
QPushButton#btn_flat:hover {
    background-color: #313244;
    border-color: #585B70;
}

/* ─── 输入框 ─── */
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #313244;
    border: 1px solid #45475A;
    border-radius: 6px;
    padding: 6px 8px;
    color: #CDD6F4;
    selection-background-color: #89B4FA44;
}
QLineEdit:focus, QTextEdit:focus {
    border-color: #89B4FA;
}

QComboBox {
    background-color: #313244;
    border: 1px solid #45475A;
    border-radius: 6px;
    padding: 5px 8px;
    color: #CDD6F4;
}
QComboBox:focus { border-color: #89B4FA; }
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView {
    background-color: #313244;
    border: 1px solid #45475A;
    selection-background-color: #89B4FA33;
}

QSpinBox, QDoubleSpinBox {
    background-color: #313244;
    border: 1px solid #45475A;
    border-radius: 6px;
    padding: 5px 8px;
    color: #CDD6F4;
}
QSpinBox:focus, QDoubleSpinBox:focus { border-color: #89B4FA; }

QCheckBox {
    color: #CDD6F4;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 16px; height: 16px;
    border-radius: 4px;
    border: 2px solid #585B70;
    background: transparent;
}
QCheckBox::indicator:checked {
    background-color: #89B4FA;
    border-color: #89B4FA;
    image: none;
}

/* ─── 滚动条 ─── */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #45475A;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #585B70; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }

QScrollBar:horizontal {
    background: transparent;
    height: 8px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #45475A;
    border-radius: 4px;
    min-width: 24px;
}
QScrollBar::handle:horizontal:hover { background: #585B70; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ─── 标签页 ─── */
QTabWidget::pane {
    border: 1px solid #313244;
    border-radius: 8px;
    background: #1E1E2E;
}
QTabBar::tab {
    background: transparent;
    border: none;
    padding: 8px 16px;
    color: #6C7086;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:selected {
    color: #89B4FA;
    border-bottom: 2px solid #89B4FA;
}
QTabBar::tab:hover { color: #CDD6F4; }

/* ─── 列表/树 ─── */
QListWidget, QTreeWidget {
    background: #181825;
    border: 1px solid #313244;
    border-radius: 8px;
    outline: none;
}
QListWidget::item, QTreeWidget::item {
    padding: 6px 8px;
    border-radius: 4px;
}
QListWidget::item:hover, QTreeWidget::item:hover {
    background: #313244;
}
QListWidget::item:selected, QTreeWidget::item:selected {
    background: #89B4FA22;
    color: #89B4FA;
}

/* ─── 分割器 ─── */
QSplitter::handle {
    background: #313244;
    width: 1px;
    height: 1px;
}

/* ─── 分组框 ─── */
QGroupBox {
    border: 1px solid #313244;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 8px;
    color: #A6ADC8;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #89B4FA;
    font-weight: bold;
}

/* ─── 状态栏 ─── */
QStatusBar {
    background: #181825;
    border-top: 1px solid #313244;
    color: #6C7086;
}

/* ─── 菜单 ─── */
QMenu {
    background: #313244;
    border: 1px solid #45475A;
    border-radius: 8px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px;
    border-radius: 4px;
}
QMenu::item:selected { background: #89B4FA22; color: #89B4FA; }
QMenu::separator { height: 1px; background: #45475A; margin: 4px 8px; }

/* ─── 工具提示 ─── */
QToolTip {
    background: #313244;
    border: 1px solid #45475A;
    border-radius: 6px;
    color: #CDD6F4;
    padding: 4px 8px;
}

/* ─── 弹窗 ─── */
QDialog {
    background: #1E1E2E;
}

/* ─── 标签 ─── */
QLabel#section_title {
    font-size: 15px;
    font-weight: bold;
    color: #CDD6F4;
}
QLabel#hint {
    color: #6C7086;
    font-size: 11px;
}
"""

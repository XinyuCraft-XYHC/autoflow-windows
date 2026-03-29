"""
AutoFlow 主题系统
支持：深色/浅色/跟随系统 + 多预设
"""
from typing import Dict


# ─── 调色板定义 ───
PALETTES: Dict[str, Dict[str, str]] = {

    # === 深色系 ===
    "dark": {
        "name": "深色 · Catppuccin Mocha",
        "mode": "dark",
        "bg0":     "#1E1E2E",  # 最深背景
        "bg1":     "#181825",  # 侧边栏
        "bg2":     "#313244",  # 输入框/卡片
        "bg3":     "#45475A",  # 边框/分割线
        "bg4":     "#585B70",  # 禁用色
        "accent":  "#89B4FA",  # 主强调（蓝）
        "accent2": "#CBA6F7",  # 次强调（紫）
        "success": "#A6E3A1",  # 绿
        "warn":    "#FAB387",  # 橙
        "danger":  "#F38BA8",  # 红
        "fg0":     "#CDD6F4",  # 主文字
        "fg1":     "#A6ADC8",  # 次文字
        "fg2":     "#6C7086",  # 暗文字
    },

    "dark_nord": {
        "name": "深色 · Nord",
        "mode": "dark",
        "bg0":     "#2E3440",
        "bg1":     "#242933",
        "bg2":     "#3B4252",
        "bg3":     "#434C5E",
        "bg4":     "#4C566A",
        "accent":  "#88C0D0",
        "accent2": "#81A1C1",
        "success": "#A3BE8C",
        "warn":    "#EBCB8B",
        "danger":  "#BF616A",
        "fg0":     "#ECEFF4",
        "fg1":     "#D8DEE9",
        "fg2":     "#9199A8",
    },

    "dark_dracula": {
        "name": "深色 · Dracula",
        "mode": "dark",
        "bg0":     "#282A36",
        "bg1":     "#21222C",
        "bg2":     "#44475A",
        "bg3":     "#6272A4",
        "bg4":     "#4D5169",
        "accent":  "#BD93F9",
        "accent2": "#FF79C6",
        "success": "#50FA7B",
        "warn":    "#FFB86C",
        "danger":  "#FF5555",
        "fg0":     "#F8F8F2",
        "fg1":     "#CFCFCF",
        "fg2":     "#8B9DC3",
    },

    "dark_onedark": {
        "name": "深色 · One Dark",
        "mode": "dark",
        "bg0":     "#21252B",
        "bg1":     "#181A1F",
        "bg2":     "#2C313A",
        "bg3":     "#3E4451",
        "bg4":     "#4B5263",
        "accent":  "#61AFEF",
        "accent2": "#C678DD",
        "success": "#98C379",
        "warn":    "#E5C07B",
        "danger":  "#E06C75",
        "fg0":     "#ABB2BF",
        "fg1":     "#9DA5B4",
        "fg2":     "#5C6370",
    },

    # === 浅色系 ===
    "light": {
        "name": "浅色 · 清新",
        "mode": "light",
        "bg0":     "#F5F5F5",
        "bg1":     "#EBEBEB",
        "bg2":     "#FFFFFF",
        "bg3":     "#D0D0D0",
        "bg4":     "#B0B0B0",
        "accent":  "#1E88E5",
        "accent2": "#7B1FA2",
        "success": "#388E3C",
        "warn":    "#E65100",
        "danger":  "#C62828",
        "fg0":     "#212121",
        "fg1":     "#424242",
        "fg2":     "#757575",
    },

    "light_sakura": {
        "name": "浅色 · 樱花",
        "mode": "light",
        "bg0":     "#FFF5F7",
        "bg1":     "#FFE4EA",
        "bg2":     "#FFFFFF",
        "bg3":     "#F8C8D0",
        "bg4":     "#E8A0B0",
        "accent":  "#E91E63",
        "accent2": "#9C27B0",
        "success": "#4CAF50",
        "warn":    "#FF9800",
        "danger":  "#F44336",
        "fg0":     "#2D1B25",
        "fg1":     "#5C3A45",
        "fg2":     "#8C6070",
    },

    "light_ocean": {
        "name": "浅色 · 海洋",
        "mode": "light",
        "bg0":     "#F0F8FF",
        "bg1":     "#E1F0FB",
        "bg2":     "#FFFFFF",
        "bg3":     "#B0D8F0",
        "bg4":     "#80B8D8",
        "accent":  "#0277BD",
        "accent2": "#01579B",
        "success": "#2E7D32",
        "warn":    "#E65100",
        "danger":  "#B71C1C",
        "fg0":     "#0D1B2A",
        "fg1":     "#1B3A55",
        "fg2":     "#4A7A9B",
    },
}


def get_stylesheet(theme: str = "dark") -> str:
    """根据主题名生成完整 QSS 样式表"""
    if theme == "system":
        # 跟随系统：检测系统深浅色
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            )
            val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            theme = "light" if val == 1 else "dark"
        except Exception:
            theme = "dark"

    p = PALETTES.get(theme, PALETTES["dark"])
    return _build_qss(p)


def _build_qss(p: Dict[str, str]) -> str:
    is_dark = p["mode"] == "dark"
    # 卡片/块背景（比 bg0 稍亮）
    card_bg = _lighten(p["bg0"], 0.05) if is_dark else p["bg2"]

    return f"""
/* ─── 全局 ─── */
QWidget {{
    background-color: {p["bg0"]};
    color: {p["fg0"]};
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 13px;
}}
QMainWindow {{ background-color: {p["bg0"]}; }}

/* ─── 侧边栏 ─── */
#sidebar {{
    background-color: {p["bg1"]};
    border-right: 1px solid {p["bg3"]};
    min-width: 200px; max-width: 200px;
}}
#sidebar QPushButton {{
    background: transparent; border: none;
    border-radius: 8px; padding: 10px 14px;
    text-align: left; font-size: 13px; color: {p["fg1"]};
}}
#sidebar QPushButton:hover {{
    background-color: {p["bg2"]}; color: {p["fg0"]};
}}
#app_title {{
    font-size: 18px; font-weight: bold;
    color: {p["accent"]}; padding: 20px 14px 10px 14px;
}}

/* ─── 按钮 ─── */
QPushButton#btn_primary {{
    background-color: {p["accent"]}; color: {p["bg0"]};
    border: none; border-radius: 8px; padding: 7px 16px; font-weight: bold;
}}
QPushButton#btn_primary:hover {{
    background-color: {_lighten(p["accent"], 0.1)};
}}
QPushButton#btn_primary:pressed {{
    background-color: {_darken(p["accent"], 0.1)};
}}
QPushButton#btn_danger {{
    background-color: {p["danger"]}; color: {p["bg0"]};
    border: none; border-radius: 8px; padding: 7px 16px; font-weight: bold;
}}
QPushButton#btn_danger:hover {{ background-color: {_lighten(p["danger"], 0.1)}; }}
QPushButton#btn_success {{
    background-color: {p["success"]}; color: {p["bg0"]};
    border: none; border-radius: 8px; padding: 7px 16px; font-weight: bold;
}}
QPushButton#btn_success:hover {{ background-color: {_lighten(p["success"], 0.1)}; }}
QPushButton#btn_warning {{
    background-color: {p["warn"]}; color: {p["bg0"]};
    border: none; border-radius: 8px; padding: 7px 16px; font-weight: bold;
}}
QPushButton#btn_warning:hover {{ background-color: {_lighten(p["warn"], 0.1)}; }}
QPushButton#btn_flat {{
    background: transparent; border: 1px solid {p["bg3"]};
    border-radius: 8px; padding: 7px 14px; color: {p["fg1"]};
}}
QPushButton#btn_flat:hover {{
    background-color: {p["bg2"]}; border-color: {p["bg4"]};
}}

/* ─── 输入框 ─── */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {p["bg2"]}; border: 1px solid {p["bg3"]};
    border-radius: 6px; padding: 6px 8px; color: {p["fg0"]};
    selection-background-color: {p["accent"]}44;
}}
QLineEdit:focus, QTextEdit:focus {{ border-color: {p["accent"]}; }}

QComboBox {{
    background-color: {p["bg2"]}; border: 1px solid {p["bg3"]};
    border-radius: 6px; padding: 5px 8px; color: {p["fg0"]};
}}
QComboBox:focus {{ border-color: {p["accent"]}; }}
QComboBox::drop-down {{ border: none; }}
QComboBox QAbstractItemView {{
    background-color: {p["bg2"]}; border: 1px solid {p["bg3"]};
    selection-background-color: {p["accent"]}33; color: {p["fg0"]};
}}

QSpinBox, QDoubleSpinBox {{
    background-color: {p["bg2"]}; border: 1px solid {p["bg3"]};
    border-radius: 6px; padding: 5px 8px; color: {p["fg0"]};
}}
QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {p["accent"]}; }}

QCheckBox {{ color: {p["fg0"]}; spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 4px;
    border: 2px solid {p["bg4"]}; background: transparent;
}}
QCheckBox::indicator:checked {{
    background-color: {p["accent"]}; border-color: {p["accent"]};
}}

/* ─── 滚动条 ─── */
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {p["bg3"]}; border-radius: 4px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: {p["bg4"]}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {p["bg3"]}; border-radius: 4px; min-width: 24px; }}
QScrollBar::handle:horizontal:hover {{ background: {p["bg4"]}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ─── 标签页 ─── */
QTabWidget::pane {{
    border: 1px solid {p["bg3"]}; border-radius: 8px; background: {p["bg0"]};
}}
QTabBar::tab {{
    background: transparent; border: none;
    padding: 8px 16px; color: {p["fg2"]};
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {p["accent"]}; border-bottom: 2px solid {p["accent"]}; }}
QTabBar::tab:hover {{ color: {p["fg0"]}; }}

/* ─── 列表 ─── */
QListWidget, QTreeWidget {{
    background: {p["bg1"]}; border: 1px solid {p["bg3"]};
    border-radius: 8px; outline: none;
}}
QListWidget::item, QTreeWidget::item {{ padding: 6px 8px; border-radius: 4px; }}
QListWidget::item:hover, QTreeWidget::item:hover {{ background: {p["bg2"]}; }}
QListWidget::item:selected, QTreeWidget::item:selected {{
    background: {p["accent"]}22; color: {p["accent"]};
}}

/* ─── 分割器 ─── */
QSplitter::handle {{ background: {p["bg3"]}; width: 1px; height: 1px; }}

/* ─── 卡片内子控件背景透明（消除割裂感）─── */
/* BlockCard / TriggerCard 自带背景，内部所有子控件须透明继承 */
#block_card > QLabel,
#block_card QLabel,
#block_card QCheckBox,
#block_card > QWidget > QLabel,
#block_card > QHBoxLayout QLabel,
#trigger_card > QLabel,
#trigger_card QLabel,
#trigger_card QCheckBox,
#trigger_card > QWidget > QLabel {{
    background: transparent;
}}
/* 卡片内按钮背景透明（各卡片内按钮已通过 setStyleSheet 覆盖，此处补全兜底）*/
#block_card QPushButton {{ background: transparent; }}
#trigger_card QPushButton {{ background: transparent; }}

/* ─── 分组框 ─── */
QGroupBox {{
    border: 1px solid {p["bg3"]}; border-radius: 8px;
    margin-top: 12px; padding-top: 8px; color: {p["fg1"]};
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 12px; padding: 0 6px;
    color: {p["accent"]}; font-weight: bold;
}}

/* ─── 状态栏 ─── */
QStatusBar {{
    background: {p["bg1"]}; border-top: 1px solid {p["bg3"]}; color: {p["fg2"]};
}}

/* ─── 菜单 ─── */
QMenu {{
    background: {p["bg2"]}; border: 1px solid {p["bg3"]};
    border-radius: 8px; padding: 4px;
}}
QMenu::item {{ padding: 6px 24px; border-radius: 4px; color: {p["fg0"]}; }}
QMenu::item:selected {{ background: {p["accent"]}22; color: {p["accent"]}; }}
QMenu::separator {{ height: 1px; background: {p["bg3"]}; margin: 4px 8px; }}

/* ─── 工具提示 ─── */
QToolTip {{
    background: {p["bg2"]}; border: 1px solid {p["bg3"]};
    border-radius: 6px; color: {p["fg0"]}; padding: 4px 8px;
}}

/* ─── 弹窗 ─── */
QDialog {{ background: {p["bg0"]}; }}

/* ─── 标签 ─── */
QLabel#section_title {{
    font-size: 15px; font-weight: bold; color: {p["fg0"]};
}}
QLabel#hint {{ color: {p["fg2"]}; font-size: 11px; }}
"""


def _lighten(hex_color: str, factor: float = 0.1) -> str:
    """将颜色加亮"""
    try:
        c = hex_color.lstrip("#")
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        r = min(255, int(r + (255 - r) * factor))
        g = min(255, int(g + (255 - g) * factor))
        b = min(255, int(b + (255 - b) * factor))
        return f"#{r:02X}{g:02X}{b:02X}"
    except Exception:
        return hex_color


def _darken(hex_color: str, factor: float = 0.1) -> str:
    """将颜色加深"""
    try:
        c = hex_color.lstrip("#")
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        r = max(0, int(r * (1 - factor)))
        g = max(0, int(g * (1 - factor)))
        b = max(0, int(b * (1 - factor)))
        return f"#{r:02X}{g:02X}{b:02X}"
    except Exception:
        return hex_color

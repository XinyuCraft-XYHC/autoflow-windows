"""
设置面板（完整版）
"""
import os
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QCheckBox, QSpinBox, QDoubleSpinBox, QComboBox, QFormLayout,
    QGroupBox, QScrollArea, QFrame, QFileDialog, QMessageBox,
    QTabWidget
)

from ..engine.models import AppConfig, Task
from .themes import PALETTES
from .block_editor import HotkeyEdit  # 点击即录制的输入框


# ─── 只在获得焦点时响应滚轮的 SpinBox ─────────────────────────────
class FocusSpinBox(QSpinBox):
    """只有在输入框被点击/获得焦点后才响应鼠标滚轮，避免滚动页面时误触数值"""

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()  # 把事件向上传递，让外层滚动区处理


class FocusDoubleSpinBox(QDoubleSpinBox):
    """只有在输入框被点击/获得焦点后才响应鼠标滚轮"""

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()
from ..i18n import tr, add_language_observer, remove_language_observer
from typing import List


class SettingsPage(QWidget):
    config_changed    = pyqtSignal(AppConfig)
    back_requested    = pyqtSignal()

    # 跨线程信号：用于安装完成/失败的回调（替代不可靠的 QMetaObject.invokeMethod）
    _bu_install_done_sig  = pyqtSignal()
    _bu_install_fail_sig  = pyqtSignal(str)
    _cr_install_done_sig  = pyqtSignal()
    _cr_install_fail_sig  = pyqtSignal(str)
    # 跨线程信号：检查更新结果（子线程→主线程）
    _update_result_sig    = pyqtSignal(dict)

    def __init__(self, config: AppConfig, tasks: List[Task], parent=None):
        super().__init__(parent)
        self.config = config
        self.tasks  = tasks
        self._build_ui()
        self._load_config()
        add_language_observer(self.retranslate)
        # 连接跨线程安装信号
        self._bu_install_done_sig.connect(self._on_bu_install_done)
        self._bu_install_fail_sig.connect(self._on_bu_install_fail)
        self._cr_install_done_sig.connect(self._on_chromium_install_done)
        self._cr_install_fail_sig.connect(self._on_chromium_install_fail)

    def __del__(self):
        try:
            remove_language_observer(self.retranslate)
        except Exception:
            pass

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # 顶部栏
        top_bar = QHBoxLayout()
        back_btn = QPushButton("<  返回")
        back_btn.setObjectName("btn_flat")
        back_btn.setFixedWidth(80)
        back_btn.clicked.connect(self.back_requested)
        top_bar.addWidget(back_btn)

        title = QLabel("  设置")
        title.setObjectName("section_title")
        title.setStyleSheet("font-size: 20px; font-weight: bold; margin-left: 12px;")
        top_bar.addWidget(title)
        top_bar.addStretch()
        root.addLayout(top_bar)

        tabs = QTabWidget()
        tabs.addTab(self._build_general_tab(),  "  通用  ")
        tabs.addTab(self._build_project_tab(),  "  项目  ")
        tabs.addTab(self._build_email_tab(),    "  邮箱  ")
        tabs.addTab(self._build_theme_tab(),    "  外观  ")
        tabs.addTab(self._build_hotkeys_tab(),  "  按键  ")
        tabs.addTab(self._build_ai_tab(),       "  AI  ")
        tabs.addTab(self._build_advanced_tab(), "  高级  ")
        tabs.addTab(self._build_about_tab(),    "  关于  ")
        root.addWidget(tabs)

        save_btn = QPushButton("  " + tr("settings.save"))
        save_btn.setObjectName("btn_primary")
        save_btn.setFixedHeight(38)
        save_btn.clicked.connect(self._save)
        self._save_btn = save_btn
        root.addWidget(save_btn, alignment=Qt.AlignmentFlag.AlignRight)

    # ─── 通用 ───
    def _build_general_tab(self) -> QWidget:
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(16)
        layout.setContentsMargins(8, 8, 8, 8)


        self._grp_startup = QGroupBox(tr("settings.grp.startup"))
        gf  = QFormLayout(self._grp_startup)
        gf.setSpacing(10)
        self._auto_start_cb = QCheckBox(tr("settings.auto_start"))
        gf.addRow("", self._auto_start_cb)
        self._auto_task_combo = QComboBox()
        self._auto_task_combo.addItem(tr("settings.no_task"), "")
        for t in self.tasks:
            self._auto_task_combo.addItem(t.name, t.id)
        gf.addRow(tr("settings.auto_start_task"), self._auto_task_combo)
        # 启动后行为
        self._launch_behavior_combo = QComboBox()
        self._launch_behavior_combo.addItem(tr("settings.launch_behavior.show"),     "show")
        self._launch_behavior_combo.addItem(tr("settings.launch_behavior.minimize"), "minimize")
        self._launch_behavior_combo.addItem(tr("settings.launch_behavior.tray"),     "tray")
        gf.addRow(tr("settings.launch_behavior"), self._launch_behavior_combo)
        layout.addWidget(self._grp_startup)


        self._grp_ui = QGroupBox(tr("settings.grp.ui"))
        gf2  = QFormLayout(self._grp_ui)
        gf2.setSpacing(10)
        self._minimize_cb = QCheckBox(tr("settings.minimize_to_tray"))
        gf2.addRow("", self._minimize_cb)
        self._show_log_cb = QCheckBox(tr("settings.show_log"))
        gf2.addRow("", self._show_log_cb)
        self._minimize_on_run_cb = QCheckBox("任务运行时最小化工具窗口")
        self._minimize_on_run_cb.setToolTip("每次手动点击[运行]时，自动最小化 AutoFlow 主窗口（触发器自动触发的任务不受此影响）")
        gf2.addRow("", self._minimize_on_run_cb)
        layout.addWidget(self._grp_ui)

        layout.addStretch()
        page.setWidget(container)
        return page

    # ─── 项目 ───
    def _build_project_tab(self) -> QWidget:
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(16)
        layout.setContentsMargins(8, 8, 8, 8)

        self._grp_last_proj = QGroupBox(tr("settings.grp.last_project"))
        gf1 = QFormLayout(self._grp_last_proj)
        gf1.setSpacing(10)
        self._reopen_cb = QCheckBox(tr("settings.reopen_last"))
        gf1.addRow("", self._reopen_cb)
        layout.addWidget(self._grp_last_proj)

        self._grp_autosave = QGroupBox(tr("settings.grp.autosave"))
        gf2 = QFormLayout(self._grp_autosave)
        gf2.setSpacing(10)
        self._auto_save_cb = QCheckBox(tr("settings.autosave_enable"))
        gf2.addRow("", self._auto_save_cb)
        self._auto_save_interval = FocusSpinBox()
        self._auto_save_interval.setRange(10, 3600)
        self._auto_save_interval.setSuffix(tr("settings.autosave_unit"))
        self._autosave_form = gf2
        gf2.addRow(tr("settings.autosave_interval"), self._auto_save_interval)
        layout.addWidget(self._grp_autosave)

        self._grp_undo = QGroupBox(tr("settings.grp.undo"))
        gf3 = QFormLayout(self._grp_undo)
        gf3.setSpacing(10)
        self._max_undo = FocusSpinBox()
        self._max_undo.setRange(5, 500)
        self._max_undo.setSuffix(tr("settings.undo_unit"))
        gf3.addRow(tr("settings.max_undo"), self._max_undo)
        self._undo_hint = QLabel(tr("settings.undo_hint"))
        self._undo_hint.setObjectName("hint")
        gf3.addRow("", self._undo_hint)
        layout.addWidget(self._grp_undo)

        self._grp_screenshot = QGroupBox(tr("settings.grp.screenshot"))
        gf4 = QFormLayout(self._grp_screenshot)
        gf4.setSpacing(10)
        row = QWidget()
        hl  = QHBoxLayout(row); hl.setContentsMargins(0,0,0,0); hl.setSpacing(4)
        self._screenshot_dir = QLineEdit()
        self._screenshot_dir.setPlaceholderText(tr("settings.screenshot_ph"))
        hl.addWidget(self._screenshot_dir)
        self._screenshot_btn = QPushButton(tr("btn.browse"))
        self._screenshot_btn.setObjectName("btn_flat"); self._screenshot_btn.setFixedWidth(52)
        self._screenshot_btn.clicked.connect(lambda: self._pick_folder(self._screenshot_dir))
        hl.addWidget(self._screenshot_btn)
        gf4.addRow(tr("settings.screenshot_dir"), row)
        layout.addWidget(self._grp_screenshot)

        layout.addStretch()
        page.setWidget(container)
        return page

    # ─── 邮箱 ───
    def _build_email_tab(self) -> QWidget:
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(16)
        layout.setContentsMargins(8, 8, 8, 8)

        self._grp_smtp = QGroupBox(tr("settings.grp.smtp"))
        sf = QFormLayout(self._grp_smtp)
        sf.setSpacing(8)
        self._smtp_server = QLineEdit(); sf.addRow(tr("settings.smtp.server"), self._smtp_server)
        self._smtp_port   = FocusSpinBox(); self._smtp_port.setRange(1,65535); sf.addRow(tr("settings.smtp.port"), self._smtp_port)
        self._smtp_user   = QLineEdit(); sf.addRow(tr("settings.smtp.user"), self._smtp_user)
        self._smtp_pass   = QLineEdit(); self._smtp_pass.setEchoMode(QLineEdit.EchoMode.Password)
        sf.addRow(tr("settings.smtp.pass"), self._smtp_pass)
        self._smtp_ssl    = QCheckBox(tr("settings.smtp.ssl")); sf.addRow("", self._smtp_ssl)
        self._btn_test_smtp = QPushButton(tr("btn.test_send"))
        self._btn_test_smtp.setObjectName("btn_flat")
        self._btn_test_smtp.clicked.connect(self._test_smtp)
        sf.addRow("", self._btn_test_smtp)
        layout.addWidget(self._grp_smtp)

        self._grp_imap = QGroupBox(tr("settings.grp.imap"))
        imf = QFormLayout(self._grp_imap)
        imf.setSpacing(8)
        self._imap_server = QLineEdit(); imf.addRow(tr("settings.imap.server"), self._imap_server)
        self._imap_port   = FocusSpinBox(); self._imap_port.setRange(1,65535); imf.addRow(tr("settings.imap.port"), self._imap_port)
        self._imap_user   = QLineEdit(); imf.addRow(tr("settings.imap.user"), self._imap_user)
        self._imap_pass   = QLineEdit(); self._imap_pass.setEchoMode(QLineEdit.EchoMode.Password)
        imf.addRow(tr("settings.imap.pass"), self._imap_pass)
        self._imap_ssl    = QCheckBox(tr("settings.imap.ssl")); imf.addRow("", self._imap_ssl)
        self._btn_test_imap = QPushButton(tr("btn.test_connect"))
        self._btn_test_imap.setObjectName("btn_flat")
        self._btn_test_imap.clicked.connect(self._test_imap)
        imf.addRow("", self._btn_test_imap)
        layout.addWidget(self._grp_imap)

        self._email_hint_lbl = QLabel(tr("settings.email_hint"))
        self._email_hint_lbl.setObjectName("hint")
        self._email_hint_lbl.setStyleSheet("font-size: 11px; padding: 8px;")
        layout.addWidget(self._email_hint_lbl)
        layout.addStretch()
        page.setWidget(container)
        return page

    # ─── 外观/主题 ───
    def _build_theme_tab(self) -> QWidget:
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(16)
        layout.setContentsMargins(8, 8, 8, 8)

        # ── 语言设置 ──
        self._grp_lang = QGroupBox(tr("settings.grp.lang"))
        gf_lang  = QFormLayout(self._grp_lang)
        gf_lang.setSpacing(10)
        self._lang_combo = QComboBox()
        from ..i18n import get_available_languages, load_language_dir as _lld
        import os as _os
        _lang_dir = _os.path.join(
            _os.environ.get("LOCALAPPDATA", _os.path.expanduser("~")),
            "XinyuCraft", "AutoFlow", "Language"
        )
        _lld(_lang_dir)
        for code, name in get_available_languages():
            self._lang_combo.addItem(name, code)
        self._lang_hint = QLabel(tr("settings.language_hint"))
        self._lang_hint.setObjectName("hint")
        self._lang_hint.setWordWrap(True)
        gf_lang.addRow(tr("settings.lang_label"), self._lang_combo)
        gf_lang.addRow("", self._lang_hint)

        # ── 语言包市场入口 ──
        lang_market_row = QHBoxLayout()
        self._lang_market_btn = QPushButton("🌐 " + tr("settings.lang_market_btn", "语言包市场"))
        self._lang_market_btn.setObjectName("btn_flat")
        self._lang_market_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lang_market_btn.clicked.connect(self._open_language_market)
        lang_market_row.addWidget(self._lang_market_btn)
        lang_market_row.addStretch()
        self._lang_market_hint = QLabel(
            tr("settings.lang_market_hint",
               "从社区下载更多语言包（日语、韩语、法语等）"))
        self._lang_market_hint.setObjectName("hint")
        lang_market_row.addWidget(self._lang_market_hint)
        gf_lang.addRow("", lang_market_row)

        layout.addWidget(self._grp_lang)

        self._grp_theme = QGroupBox(tr("settings.grp.theme"))
        gf  = QFormLayout(self._grp_theme)
        gf.setSpacing(12)

        self._theme_combo = QComboBox()
        self._theme_combo.addItem(tr("settings.theme_follow"), "system")
        # 按深/浅分组
        dark_items  = [(k, v) for k, v in PALETTES.items() if v["mode"] == "dark"]
        light_items = [(k, v) for k, v in PALETTES.items() if v["mode"] == "light"]
        for k, v in dark_items:
            self._theme_combo.addItem(f"  {v['name']}", k)
        for k, v in light_items:
            self._theme_combo.addItem(f"  {v['name']}", k)

        gf.addRow(tr("settings.theme_label"), self._theme_combo)
        layout.addWidget(self._grp_theme)

        # 预览色块
        self._theme_preview = QLabel()
        self._theme_preview.setFixedHeight(60)
        self._theme_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._theme_preview)

        self._theme_combo.currentIndexChanged.connect(self._update_theme_preview)

        self._theme_hint = QLabel(tr("settings.theme_hint"))
        self._theme_hint.setObjectName("hint")
        layout.addWidget(self._theme_hint)

        layout.addStretch()
        page.setWidget(container)
        return page

    def _update_theme_preview(self):
        key = self._theme_combo.currentData() or "dark"
        if key == "system":
            key = "dark"
        from .themes import PALETTES as P
        p = P.get(key, P["dark"])
        self._theme_preview.setStyleSheet(
            f"background: {p['bg0']}; border: 2px solid {p['accent']}; "
            f"border-radius: 8px; color: {p['fg0']};"
        )
        accent = p["accent"]
        fg2    = p["fg2"]
        name   = p["name"]
        self._theme_preview.setText(
            f"<b style='color:{accent}'>{name}</b>  "
            f"<span style='color:{fg2}'>预览</span>"
        )

    # ─── 按键 ───
    def _build_hotkeys_tab(self) -> QWidget:
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(16)
        layout.setContentsMargins(8, 8, 8, 8)

        # ── 可自定义快捷键 ──
        self._grp_hotkeys_custom = QGroupBox(tr("settings.grp.hotkeys_custom"))
        gf_custom  = QFormLayout(self._grp_hotkeys_custom)
        gf_custom.setSpacing(12)

        # 坐标选点 —— 点击输入框即录制
        self._coord_hotkey = HotkeyEdit()
        self._coord_hotkey.setFixedWidth(200)
        gf_custom.addRow(tr("settings.coord_hotkey"), self._coord_hotkey)
        self._coord_hotkey_hint = QLabel(tr("settings.coord_hotkey_hint"))
        self._coord_hotkey_hint.setObjectName("hint")
        self._coord_hotkey_hint.setWordWrap(True)
        gf_custom.addRow("", self._coord_hotkey_hint)

        # 键鼠宏停止录制
        self._macro_stop_hotkey = HotkeyEdit()
        self._macro_stop_hotkey.setFixedWidth(200)
        gf_custom.addRow("停止录制热键", self._macro_stop_hotkey)
        _macro_stop_hint = QLabel("录制键鼠宏时，按此键停止录制（最小化窗口后仍有效，默认 F10）")
        _macro_stop_hint.setObjectName("hint")
        _macro_stop_hint.setWordWrap(True)
        gf_custom.addRow("", _macro_stop_hint)

        # 强制终止
        self._force_stop_hotkey = HotkeyEdit()
        self._force_stop_hotkey.setFixedWidth(200)
        gf_custom.addRow(tr("settings.stop_hotkey"), self._force_stop_hotkey)
        self._stop_hotkey_hint = QLabel(tr("settings.stop_hotkey_hint"))
        self._stop_hotkey_hint.setObjectName("hint")
        self._stop_hotkey_hint.setWordWrap(True)
        gf_custom.addRow("", self._stop_hotkey_hint)

        layout.addWidget(self._grp_hotkeys_custom)

        # ── 内置固定快捷键参考表 ──
        from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
        self._grp_hotkeys_ref = QGroupBox(tr("settings.grp.hotkeys_ref"))
        grp_ref_layout = QVBoxLayout(self._grp_hotkeys_ref)
        grp_ref_layout.setContentsMargins(8, 8, 8, 8)
        grp_ref_layout.setSpacing(6)

        HOTKEYS = [
            # 分类,  快捷键,           说明
            ("项目",  "Ctrl+N",         "新建项目"),
            ("项目",  "Ctrl+O",         "打开项目"),
            ("项目",  "Ctrl+S",         "保存项目"),
            ("项目",  "Ctrl+Shift+S",   "另存为"),
            ("项目",  "Ctrl+W",         "关闭项目"),
            ("任务",  "Ctrl+T",         "新建任务"),
            ("编辑",  "Ctrl+Z",         "撤回"),
            ("编辑",  "Ctrl+Y",         "重做"),
            ("编辑",  "Ctrl+Shift+Z",   "重做（备选）"),
            ("编辑",  "Ctrl+H",         "操作历史"),
        ]

        tbl = QTableWidget(len(HOTKEYS), 3)
        tbl.setHorizontalHeaderLabels([tr("settings.hotkeys.cat"), tr("settings.hotkeys.key"), tr("settings.hotkeys.desc")])
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tbl.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        tbl.setAlternatingRowColors(True)
        tbl.setFrameShape(QFrame.Shape.NoFrame)

        for row_idx, (cat, key, desc) in enumerate(HOTKEYS):
            for col_idx, text in enumerate([cat, key, desc]):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                tbl.setItem(row_idx, col_idx, item)

        tbl.setFixedHeight(tbl.rowHeight(0) * len(HOTKEYS) + tbl.horizontalHeader().height() + 4)
        grp_ref_layout.addWidget(tbl)
        layout.addWidget(self._grp_hotkeys_ref)

        layout.addStretch()
        page.setWidget(container)
        return page

    # ─── AI 大模型 ───
    def _build_ai_tab(self) -> QWidget:
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(16)
        layout.setContentsMargins(8, 8, 8, 8)

        # ── 说明 ──
        self._ai_hint_top = QLabel(tr("settings.ai_hint"))
        self._ai_hint_top.setObjectName("hint")
        self._ai_hint_top.setWordWrap(True)
        layout.addWidget(self._ai_hint_top)

        # ── 服务商与模型 ──
        self._grp_ai_model = QGroupBox(tr("settings.grp.ai_model"))
        gf_model  = QFormLayout(self._grp_ai_model)
        gf_model.setSpacing(10)

        # ── 服务商预设表：(代码, 显示名, base_url, 推荐模型, api_key_hint) ──
        self._AI_PRESETS = [
            ("openai",    "OpenAI (GPT-4o/GPT-3.5)",
             "",
             "gpt-4o-mini",
             "sk-xxxxxxxx（platform.openai.com/api-keys）"),
            ("deepseek",  "DeepSeek（深度求索）",
             "https://api.deepseek.com/v1",
             "deepseek-chat",
             "sk-xxxxxxxx（platform.deepseek.com）"),
            ("kimi",      "Kimi（月之暗面 Moonshot）",
             "https://api.moonshot.cn/v1",
             "moonshot-v1-8k",
             "sk-xxxxxxxx（platform.moonshot.cn）"),
            ("qwen",      "通义千问 (Qwen / 阿里云)",
             "https://dashscope.aliyuncs.com/compatible-mode/v1",
             "qwen-plus",
             "sk-xxxxxxxx（dashscope.aliyun.com）"),
            ("zhipu",     "智谱 AI (GLM / ChatGLM)",
             "https://open.bigmodel.cn/api/paas/v4",
             "glm-4-flash",
             "xxxxxxxx.xxxxxxxx（open.bigmodel.cn）"),
            ("baidu",     "百度文心 (ERNIE / 千帆)",
             "https://qianfan.baidubce.com/v2",
             "ernie-4.5-8k",
             "（百度智能云控制台获取 API Key）"),
            ("claude",    "Anthropic Claude",
             "https://api.anthropic.com/v1",
             "claude-3-5-haiku-20241022",
             "sk-ant-xxxxxxxx（console.anthropic.com）"),
            ("gemini",    "Google Gemini",
             "https://generativelanguage.googleapis.com/v1beta/openai",
             "gemini-2.0-flash",
             "AIza...（aistudio.google.com/apikey）"),
            ("ollama",    "Ollama（本地模型）",
             "http://localhost:11434/v1",
             "llama3",
             "ollama（不需要真实 Key，填 ollama 即可）"),
            ("azure",     "Azure OpenAI",
             "",
             "",
             "（Azure 门户 → 密钥和终结点）"),
            ("custom",    "自定义（兼容 OpenAI 接口）",
             "",
             "",
             ""),
        ]

        self._ai_provider = QComboBox()
        for val, label, *_ in self._AI_PRESETS:
            self._ai_provider.addItem(label, val)
        self._ai_provider.currentIndexChanged.connect(self._on_ai_provider_changed)
        gf_model.addRow(tr("settings.ai_provider"), self._ai_provider)

        self._ai_model = QLineEdit()
        self._ai_model.setPlaceholderText("如 gpt-4o-mini / deepseek-chat / moonshot-v1-8k")
        gf_model.addRow(tr("settings.ai_model_name"), self._ai_model)

        # 快速选择模型下拉（根据服务商动态更新）
        self._ai_model_preset = QComboBox()
        self._ai_model_preset.setToolTip("点击快速选择常用模型（也可手动填写上方输入框）")
        self._ai_model_preset.currentTextChanged.connect(
            lambda t: self._ai_model.setText(t) if t and not t.startswith("—") else None
        )
        gf_model.addRow(tr("settings.ai_model_preset"), self._ai_model_preset)

        self._ai_api_key = QLineEdit()
        self._ai_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._ai_api_key.setPlaceholderText("填入 API Key（sk-xxxxxxxx...）")
        gf_model.addRow(tr("settings.ai_api_key"), self._ai_api_key)

        # 显示/隐藏 API Key
        self._show_key_cb = QCheckBox(tr("settings.ai_show_key"))
        self._show_key_cb.stateChanged.connect(
            lambda s: self._ai_api_key.setEchoMode(
                QLineEdit.EchoMode.Normal if s else QLineEdit.EchoMode.Password
            )
        )
        gf_model.addRow("", self._show_key_cb)

        self._ai_base_url = QLineEdit()
        self._ai_base_url.setPlaceholderText(
            "留空=自动使用官方地址  /  自定义: https://your-proxy/v1"
        )
        gf_model.addRow(tr("settings.ai_base_url"), self._ai_base_url)

        # API Key 获取提示（根据服务商动态更新）
        self._ai_key_hint = QLabel("")
        self._ai_key_hint.setObjectName("hint")
        self._ai_key_hint.setWordWrap(True)
        self._ai_key_hint.setStyleSheet("font-size: 11px; padding: 4px 0;")
        gf_model.addRow("", self._ai_key_hint)

        layout.addWidget(self._grp_ai_model)

        # ── 参数 ──
        self._grp_ai_params = QGroupBox(tr("settings.grp.ai_params"))
        gf_params  = QFormLayout(self._grp_ai_params)
        gf_params.setSpacing(10)

        from PyQt6.QtWidgets import QDoubleSpinBox
        self._ai_temperature = FocusDoubleSpinBox()
        self._ai_temperature.setRange(0.0, 2.0)
        self._ai_temperature.setSingleStep(0.1)
        self._ai_temperature.setDecimals(1)
        self._ai_temperature.setValue(0.7)
        gf_params.addRow(tr("settings.ai_temperature"), self._ai_temperature)

        from PyQt6.QtWidgets import QSpinBox as _QSpin
        self._ai_max_tokens = FocusSpinBox()
        self._ai_max_tokens.setRange(128, 32768)
        self._ai_max_tokens.setSingleStep(256)
        self._ai_max_tokens.setValue(2048)
        gf_params.addRow(tr("settings.ai_max_tokens"), self._ai_max_tokens)

        self._ai_temp_hint = QLabel(tr("settings.ai_temp_hint"))
        self._ai_temp_hint.setObjectName("hint")
        gf_params.addRow("", self._ai_temp_hint)

        layout.addWidget(self._grp_ai_params)

        # ── 默认系统提示词 ──
        self._grp_ai_system = QGroupBox(tr("settings.grp.ai_system"))
        gf_sys  = QVBoxLayout(self._grp_ai_system)
        gf_sys.setContentsMargins(8, 8, 8, 8)
        self._ai_system_prompt = QLineEdit()
        self._ai_system_prompt.setPlaceholderText(
            "留空=无系统提示词  /  也可在功能块中单独设置"
        )
        # 使用多行文本
        from PyQt6.QtWidgets import QTextEdit
        self._ai_system_prompt_edit = QTextEdit()
        self._ai_system_prompt_edit.setFixedHeight(80)
        self._ai_system_prompt_edit.setPlaceholderText(
            "可选。例如：你是一个专业的代码助手，请用中文回答。\n"
            "每个功能块也可以单独设置系统提示词（会覆盖此处设置）。"
        )
        gf_sys.addWidget(self._ai_system_prompt_edit)
        layout.addWidget(self._grp_ai_system)

        # ── 测试连接 ──
        self._btn_test_ai = QPushButton(tr("btn.test_ai"))
        self._btn_test_ai.setObjectName("btn_flat")
        self._btn_test_ai.setFixedWidth(120)
        self._btn_test_ai.clicked.connect(self._test_ai_connection)
        layout.addWidget(self._btn_test_ai, alignment=Qt.AlignmentFlag.AlignLeft)

        # ── browser-use 浏览器自动化 ──
        from PyQt6.QtWidgets import QFrame as _QFrame
        sep_bu = _QFrame(); sep_bu.setFrameShape(_QFrame.Shape.HLine)
        layout.addWidget(sep_bu)

        self._grp_browser_auto = QGroupBox("🌐 AI 浏览器自动化（browser-use）")
        gf_bu = QVBoxLayout(self._grp_browser_auto)
        gf_bu.setSpacing(8)
        gf_bu.setContentsMargins(8, 8, 8, 8)

        bu_hint = QLabel(
            "基于开源项目 <a href='https://github.com/browser-use/browser-use'>browser-use</a>（MIT License），"
            "让 AI 以自然语言操控浏览器自动完成网页任务。\n"
            "使用前需安装依赖：<b>pip install browser-use</b>  然后运行：<b>playwright install chromium</b>"
        )
        bu_hint.setObjectName("hint")
        bu_hint.setWordWrap(True)
        bu_hint.setOpenExternalLinks(True)
        bu_hint.setTextFormat(Qt.TextFormat.RichText)
        gf_bu.addWidget(bu_hint)

        # 安装检测 + 一键安装按钮
        btn_row = QHBoxLayout()
        self._bu_status_lbl = QLabel("⚪ 检测中…")
        self._bu_status_lbl.setStyleSheet("font-size: 11px;")
        btn_row.addWidget(self._bu_status_lbl)
        btn_row.addStretch()

        self._btn_install_bu = QPushButton("一键安装 browser-use")
        self._btn_install_bu.setObjectName("btn_flat")
        self._btn_install_bu.setFixedHeight(28)
        self._btn_install_bu.clicked.connect(self._install_browser_use)
        btn_row.addWidget(self._btn_install_bu)

        self._btn_install_chromium = QPushButton("安装 Chromium")
        self._btn_install_chromium.setObjectName("btn_flat")
        self._btn_install_chromium.setFixedHeight(28)
        self._btn_install_chromium.clicked.connect(self._install_chromium)
        btn_row.addWidget(self._btn_install_chromium)

        gf_bu.addLayout(btn_row)
        layout.addWidget(self._grp_browser_auto)

        # 初始检测安装状态
        QTimer.singleShot(300, self._check_browser_use_status)

        # 初始化一次模型列表
        self._on_ai_provider_changed(0)

        layout.addStretch()
        page.setWidget(container)
        return page

    # 每个服务商的推荐模型列表
    _AI_MODEL_LISTS = {
        "openai":   ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo", "o1", "o1-mini", "o3-mini"],
        "deepseek": ["deepseek-chat", "deepseek-reasoner", "deepseek-coder"],
        "kimi":     ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k",
                     "moonshot-v1-auto", "kimi-k2.5", "kimi-k2-thinking"],
        "qwen":     ["qwen-max", "qwen-plus", "qwen-turbo", "qwen-long",
                     "qwen2.5-72b-instruct", "qwen2.5-7b-instruct"],
        "zhipu":    ["glm-4-plus", "glm-4-flash", "glm-4-air", "glm-4", "glm-3-turbo"],
        "baidu":    ["ernie-4.5-8k", "ernie-4.0-8k", "ernie-speed-128k", "ernie-lite-8k", "ernie-tiny-8k"],
        "claude":   ["claude-opus-4-5", "claude-sonnet-4-5", "claude-3-5-haiku-20241022",
                     "claude-3-5-sonnet-20241022", "claude-3-opus-20240229"],
        "gemini":   ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-pro", "gemini-1.5-flash"],
        "ollama":   ["llama3", "llama3.1", "mistral", "qwen2", "deepseek-r1", "phi3", "gemma2"],
        "azure":    [],
        "custom":   [],
    }

    def _on_ai_provider_changed(self, index: int = -1):
        """切换服务商时自动填充 Base URL、API Key 提示，并更新模型快速选择列表"""
        code = self._ai_provider.currentData() or "openai"
        preset = next((p for p in self._AI_PRESETS if p[0] == code), None)
        if not preset:
            return
        _, _, base_url, default_model, key_hint = preset

        # 自动填充 Base URL（仅在用户没手动修改或当前是另一个预设URL时填入）
        current_url = self._ai_base_url.text().strip()
        # 判断当前 URL 是否是某个预设的URL（说明是自动填的，可以安全覆盖）
        preset_urls = {p[2] for p in self._AI_PRESETS if p[2]}
        if current_url == "" or current_url in preset_urls:
            self._ai_base_url.setText(base_url)

        # 更新 API Key 提示
        self._ai_key_hint.setText(f"Key 格式：{key_hint}" if key_hint else "")

        # 更新模型快速选择列表
        models = self._AI_MODEL_LISTS.get(code, [])
        self._ai_model_preset.blockSignals(True)
        self._ai_model_preset.clear()
        if models:
            self._ai_model_preset.addItem(f"—— 点击选择 {len(models)} 个推荐模型 ——")
            for m in models:
                self._ai_model_preset.addItem(m)
            # 如果当前模型输入框为空或是另一个服务商的默认模型，自动填入默认模型
            cur_model = self._ai_model.text().strip()
            all_default_models = {p[3] for p in self._AI_PRESETS if p[3]}
            if not cur_model or cur_model in all_default_models:
                self._ai_model.setText(default_model)
        else:
            self._ai_model_preset.addItem("—— 请手动填写模型名称 ——")
        self._ai_model_preset.blockSignals(False)

    def _refresh_model_preset_list(self, code: str):
        """只刷新模型快速选择列表，不覆盖 base_url / model 文本"""
        models = self._AI_MODEL_LISTS.get(code, [])
        self._ai_model_preset.blockSignals(True)
        self._ai_model_preset.clear()
        if models:
            self._ai_model_preset.addItem(f"—— 点击选择 {len(models)} 个推荐模型 ——")
            for m in models:
                self._ai_model_preset.addItem(m)
        else:
            self._ai_model_preset.addItem("—— 请手动填写模型名称 ——")
        self._ai_model_preset.blockSignals(False)

    def _test_ai_connection(self):
        """测试 AI 连接"""
        api_key  = self._ai_api_key.text().strip()
        base_url = self._ai_base_url.text().strip()
        model    = self._ai_model.text().strip() or "gpt-4o-mini"

        if not api_key:
            QMessageBox.warning(self, "测试失败", "请先填写 API Key！")
            return

        try:
            import urllib.request, urllib.error, json as _json, ssl
            # 确定请求地址
            if not base_url:
                base_url = "https://api.openai.com/v1"
            base_url = base_url.rstrip("/")
            url = f"{base_url}/chat/completions"

            payload = _json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 5,
            }).encode("utf-8")

            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                method="POST"
            )
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                body = _json.loads(resp.read().decode("utf-8"))
                reply = body["choices"][0]["message"]["content"]
                QMessageBox.information(self, "✅ 连接成功",
                    f"模型 {model} 连接成功！\n回复预览：{reply[:80]}")
        except urllib.error.HTTPError as e:
            try:
                err_body = _json.loads(e.read().decode("utf-8"))
                err_msg = err_body.get("error", {}).get("message", str(e))
            except Exception:
                err_msg = str(e)
            QMessageBox.critical(self, "连接失败", f"HTTP {e.code}：{err_msg}")
        except Exception as e:
            QMessageBox.critical(self, "连接失败", f"连接失败：\n{e}")

    def _check_browser_use_status(self):
        """检测 browser-use 安装状态"""
        try:
            import importlib
            bu = importlib.import_module("browser_use")
            version = getattr(bu, "__version__", "已安装")
            if hasattr(self, "_bu_status_lbl"):
                self._bu_status_lbl.setText(f"✅ browser-use {version} 已安装")
                self._bu_status_lbl.setStyleSheet("font-size:11px; color:#4ade80;")
        except ImportError:
            if hasattr(self, "_bu_status_lbl"):
                self._bu_status_lbl.setText("❌ browser-use 未安装")
                self._bu_status_lbl.setStyleSheet("font-size:11px; color:#f87171;")

    def _install_browser_use(self):
        """一键安装 browser-use（browser_use.llm 内置适配层，无需 langchain）"""
        import sys, subprocess, threading
        self._btn_install_bu.setEnabled(False)
        self._bu_status_lbl.setText("⏳ 正在安装 browser-use，请稍候…")

        def do_install():
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "browser-use", "--upgrade"],
                    capture_output=True, text=True, timeout=120
                )
                if result.returncode == 0:
                    self._bu_install_done_sig.emit()
                else:
                    self._bu_install_fail_sig.emit(result.stderr[-500:])
            except Exception as e:
                self._bu_install_fail_sig.emit(str(e))

        threading.Thread(target=do_install, daemon=True).start()

    def _on_bu_install_done(self):
        self._btn_install_bu.setEnabled(True)
        self._check_browser_use_status()
        QMessageBox.information(self, "安装成功",
            "browser-use 已安装！\n\n下一步：点击「安装 Chromium」按钮安装浏览器驱动。")

    def _on_bu_install_fail(self, err: str = ""):
        self._btn_install_bu.setEnabled(True)
        if not err:
            err = getattr(self, "_bu_install_error", "未知错误")
        QMessageBox.critical(self, "安装失败",
            f"browser-use 安装失败，请手动执行：\n\npip install browser-use\n\n错误信息：\n{err}")

    def _install_chromium(self):
        """安装 Playwright Chromium"""
        import sys, subprocess, threading
        self._btn_install_chromium.setEnabled(False)
        self._bu_status_lbl.setText("⏳ 正在安装 Chromium，这可能需要几分钟…")

        def do_install():
            try:
                # 先确保 playwright 已安装
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "playwright"],
                    capture_output=True, text=True, timeout=60
                )
                result = subprocess.run(
                    [sys.executable, "-m", "playwright", "install", "chromium"],
                    capture_output=True, text=True, timeout=300
                )
                if result.returncode == 0:
                    self._cr_install_done_sig.emit()
                else:
                    self._cr_install_fail_sig.emit(result.stderr[-500:])
            except Exception as e:
                self._cr_install_fail_sig.emit(str(e))

        threading.Thread(target=do_install, daemon=True).start()

    def _on_chromium_install_done(self):
        self._btn_install_chromium.setEnabled(True)
        self._bu_status_lbl.setText("✅ browser-use + Chromium 均已就绪！")
        self._bu_status_lbl.setStyleSheet("font-size:11px; color:#4ade80;")
        QMessageBox.information(self, "安装完成",
            "Chromium 浏览器驱动安装成功！\n\n现在可以使用「AI 浏览器自动化」功能块了。")

    def _on_chromium_install_fail(self, err: str = ""):
        self._btn_install_chromium.setEnabled(True)
        if not err:
            err = getattr(self, "_chromium_install_error", "未知错误")
        QMessageBox.critical(self, "安装失败",
            f"Chromium 安装失败，请手动执行：\n\nplaywright install chromium\n\n错误信息：\n{err}")

    # ─── 高级 ───
    def _build_advanced_tab(self) -> QWidget:
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(16)
        layout.setContentsMargins(8, 8, 8, 8)

        self._grp_log = QGroupBox(tr("settings.grp.log"))
        gf  = QFormLayout(self._grp_log)
        gf.setSpacing(8)
        self._log_path = QLineEdit()
        _default_log = os.path.join(
            os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
            "XinyuCraft", "AutoFlow", "Log", "autoflow.log"
        )
        self._log_path.setPlaceholderText(f"留空=自动使用  {_default_log}")
        row = QWidget()
        hl  = QHBoxLayout(row); hl.setContentsMargins(0,0,0,0); hl.setSpacing(4)
        hl.addWidget(self._log_path)
        self._log_browse_btn = QPushButton(tr("btn.browse"))
        self._log_browse_btn.setObjectName("btn_flat"); self._log_browse_btn.setFixedWidth(52)
        self._log_browse_btn.clicked.connect(self._pick_log_path)
        hl.addWidget(self._log_browse_btn)
        gf.addRow(tr("settings.log_path"), row)
        self._max_log = FocusSpinBox()
        self._max_log.setRange(100, 100000)
        gf.addRow(tr("settings.max_log_lines"), self._max_log)
        layout.addWidget(self._grp_log)

        layout.addStretch()
        page.setWidget(container)
        return page

    # ─── 关于 ───
    def _build_about_tab(self) -> QWidget:
        from ..version import VERSION, FULL_NAME
        from ..updater import (GITHUB_REPO_URL, GITHUB_RELEASES_URL,
                               GITEE_REPO_URL, GITEE_RELEASES_URL,
                               ISSUES_URL, WIKI_URL)
        from PyQt6.QtWidgets import QScrollArea, QFrame as _QFrame
        # 外层滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(_QFrame.Shape.NoFrame)

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 16, 20, 16)

        logo = QLabel("AF")
        logo.setStyleSheet("font-size: 64px; font-weight: bold; color: #89B4FA;")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)

        name = QLabel(FULL_NAME)
        name.setStyleSheet("font-size: 26px; font-weight: bold; color: #89B4FA;")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name)

        ver = QLabel(f"版本 {VERSION}")
        ver.setStyleSheet("font-size: 13px; color: #89B4FA;")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(ver)

        desc = QLabel("Windows 智能自动化工具\n积木式编程 · 触发器驱动 · 开机自启")
        desc.setStyleSheet("font-size: 13px;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc)

        # ── 版本检测行 ──
        update_row = QWidget()
        update_hl = QHBoxLayout(update_row)
        update_hl.setContentsMargins(0, 4, 0, 4)
        update_hl.setSpacing(8)
        update_hl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._update_status_lbl = QLabel("点击右侧按钮检查更新")
        self._update_status_lbl.setStyleSheet("font-size: 12px; color: #6C7086;")
        update_hl.addWidget(self._update_status_lbl)

        check_btn = QPushButton("🔍 检查更新")
        check_btn.setFixedWidth(110)
        check_btn.setFixedHeight(28)
        check_btn.setStyleSheet(
            "QPushButton { font-size:11px; border-radius:5px; padding:2px 8px; "
            "background:#313244; color:#CDD6F4; border:1px solid #45475A; }"
            "QPushButton:hover { background:#45475A; }"
        )
        check_btn.clicked.connect(lambda: self._do_check_update(VERSION))
        update_hl.addWidget(check_btn)

        self._update_open_btn = QPushButton("📥 前往下载")
        self._update_open_btn.setFixedWidth(100)
        self._update_open_btn.setFixedHeight(28)
        self._update_open_btn.setStyleSheet(
            "QPushButton { font-size:11px; border-radius:5px; padding:2px 8px; "
            "background:#1e3a5f; color:#89B4FA; border:1px solid #89B4FA; }"
            "QPushButton:hover { background:#2a4f7a; }"
        )
        self._update_open_btn.setVisible(False)
        update_hl.addWidget(self._update_open_btn)
        layout.addWidget(update_row)

        # ── GitHub / Gitee 链接行 ──
        link_row = QWidget()
        link_hl = QHBoxLayout(link_row)
        link_hl.setContentsMargins(0, 0, 0, 0)
        link_hl.setSpacing(16)
        link_hl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for icon, text, url in [
            ("🐙", "GitHub", GITHUB_REPO_URL),
            ("🦊", "Gitee",  GITEE_REPO_URL),
            ("📋", "Issues",  ISSUES_URL),
        ]:
            lbl = QLabel(f'{icon} <a href="{url}" style="color:#89B4FA;">{text}</a>')
            lbl.setOpenExternalLinks(True)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setStyleSheet("font-size: 12px;")
            link_hl.addWidget(lbl)
        layout.addWidget(link_row)

        # 分隔线
        from PyQt6.QtWidgets import QFrame
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        # 出品 / 开发者 / 策划
        info_lines = [
            ("🏢 出品公司",  "广州新遇绘创美术工艺有限公司"),
            ("💻 开发者",    "扣子、阿浠"),
            ("📋 策划",      "扣子"),
        ]
        for label, value in info_lines:
            row = QLabel(f"<b>{label}</b>：{value}")
            row.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row.setStyleSheet("font-size: 12px;")
            layout.addWidget(row)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep2)

        # 第三方技术
        tech_lbl = QLabel("<b>📦 技术栈 &amp; 第三方支持</b>")
        tech_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tech_lbl.setStyleSheet("font-size: 12px;")
        layout.addWidget(tech_lbl)

        tech_items = [
            "Python 3.14  ·  PyQt6（界面框架）",
            "psutil（系统进程/网络监控）",
            "pycaw / comtypes（Windows 音量控制）",
            "pywin32（Win32 API 调用）",
            "PyInstaller（打包发行）",
            "Sysinternals PsTools（进程管理辅助）",
            "browser-use + Playwright（AI 浏览器自动化）",
        ]
        for item in tech_items:
            lbl = QLabel(f"• {item}")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("font-size: 11px; color: gray;")
            layout.addWidget(lbl)

        sep3 = QFrame(); sep3.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep3)

        # ── 开源致谢 ──
        oss_title = QLabel("<b>🙏 开源致谢</b>")
        oss_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        oss_title.setStyleSheet("font-size: 12px;")
        layout.addWidget(oss_title)

        oss_items = [
            (
                "🌐 browser-use",
                "AI 驱动的浏览器自动化框架，让 AI 以自然语言操控浏览器",
                "https://github.com/browser-use/browser-use",
                "Gregor Zunic 等开发者",
                "MIT License",
            ),
        ]
        for icon_name, desc_text, url, author, lic in oss_items:
            oss_box = QWidget()
            oss_layout = QVBoxLayout(oss_box)
            oss_layout.setContentsMargins(12, 6, 12, 6)
            oss_layout.setSpacing(2)

            name_row = QLabel(
                f"<b>{icon_name}</b> &nbsp;·&nbsp; "
                f"<a href='{url}' style='color:#89B4FA;'>{url}</a>"
            )
            name_row.setOpenExternalLinks(True)
            name_row.setTextFormat(Qt.TextFormat.RichText)
            name_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name_row.setStyleSheet("font-size: 11px;")
            oss_layout.addWidget(name_row)

            desc_row = QLabel(f"{desc_text}  ·  作者：{author}  ·  {lic}")
            desc_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
            desc_row.setStyleSheet("font-size: 10px; color: gray;")
            oss_layout.addWidget(desc_row)

            layout.addWidget(oss_box)

        copyright_lbl = QLabel("© 2026 广州新遇绘创美术工艺有限公司  保留所有权利")
        copyright_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        copyright_lbl.setStyleSheet("font-size: 10px; color: gray;")
        layout.addWidget(copyright_lbl)

        layout.addStretch()
        scroll.setWidget(page)
        return scroll

    def _do_check_update(self, current_version: str) -> None:
        """触发后台版本检测，结果通过信号安全回到主线程"""
        from ..updater import check_update
        self._update_status_lbl.setText("⏳ 正在检查更新...")
        self._update_status_lbl.setStyleSheet("font-size: 12px; color: #CDD6F4;")
        self._update_open_btn.setVisible(False)

        # 确保信号只连接一次（多次点击时先断开旧连接）
        try:
            self._update_result_sig.disconnect()
        except Exception:
            pass
        self._update_result_sig.connect(self._apply_update_result)

        # 子线程回调：直接 emit 信号（Qt 信号跨线程是安全的）
        def _on_result(result: dict):
            self._update_result_sig.emit(result)

        check_update(current_version, callback=_on_result)

    def _apply_update_result(self, result: dict) -> None:
        """在主线程更新版本检测结果 UI"""
        import webbrowser
        if result.get("error"):
            self._update_status_lbl.setText(f"❌ {result['error']}")
            self._update_status_lbl.setStyleSheet("font-size: 12px; color: #f87171;")
            self._update_open_btn.setVisible(False)
            return

        if result.get("has_update"):
            tag = result.get("latest_tag", "")
            self._update_status_lbl.setText(f"🎉 发现新版本 {tag}，点击右侧前往下载")
            self._update_status_lbl.setStyleSheet("font-size: 12px; color: #4ade80;")
            url = result.get("download_url") or result.get("html_url", "")
            self._update_open_btn.setVisible(True)
            # 断开旧连接再重新连接，防止多次触发
            try:
                self._update_open_btn.clicked.disconnect()
            except Exception:
                pass
            self._update_open_btn.clicked.connect(lambda: webbrowser.open(url))
        else:
            tag = result.get("latest_tag", "")
            self._update_status_lbl.setText(f"✅ 已是最新版本（{tag}）")
            self._update_status_lbl.setStyleSheet("font-size: 12px; color: #4ade80;")
            self._update_open_btn.setVisible(False)

    # ─── 加载/保存 ───
    def _load_config(self):
        c = self.config
        self._auto_start_cb.setChecked(c.auto_start_enabled)
        idx = self._auto_task_combo.findData(c.auto_start_task_id)
        if idx >= 0:
            self._auto_task_combo.setCurrentIndex(idx)
        # 启动后行为
        lb_idx = self._launch_behavior_combo.findData(getattr(c, 'launch_behavior', 'show'))
        self._launch_behavior_combo.setCurrentIndex(lb_idx if lb_idx >= 0 else 0)
        self._minimize_cb.setChecked(c.minimize_to_tray)
        self._show_log_cb.setChecked(c.show_run_log)
        self._minimize_on_run_cb.setChecked(getattr(c, 'minimize_on_run', False))
        self._coord_hotkey.setText(getattr(c, "coord_pick_hotkey", "F9"))
        self._macro_stop_hotkey.setText(getattr(c, "macro_stop_hotkey", "F10"))
        self._force_stop_hotkey.setText(getattr(c, "force_stop_hotkey", "ctrl+alt+s"))

        self._reopen_cb.setChecked(c.reopen_last_project)
        self._auto_save_cb.setChecked(c.auto_save_enabled)
        self._auto_save_interval.setValue(c.auto_save_interval)
        self._max_undo.setValue(c.max_undo_steps)
        self._screenshot_dir.setText(c.screenshot_default_dir)

        self._smtp_server.setText(c.smtp_server)
        self._smtp_port.setValue(c.smtp_port)
        self._smtp_user.setText(c.smtp_user)
        self._smtp_pass.setText(c.smtp_password)
        self._smtp_ssl.setChecked(c.smtp_ssl)

        self._imap_server.setText(c.imap_server)
        self._imap_port.setValue(c.imap_port)
        self._imap_user.setText(c.imap_user)
        self._imap_pass.setText(c.imap_password)
        self._imap_ssl.setChecked(c.imap_ssl)

        self._log_path.setText(c.log_path)
        self._max_log.setValue(c.max_log_lines)

        # 主题
        idx2 = self._theme_combo.findData(c.theme)
        if idx2 >= 0:
            self._theme_combo.setCurrentIndex(idx2)
        self._update_theme_preview()

        # 语言
        lang = getattr(c, 'language', 'zh_CN')
        idx_lang = self._lang_combo.findData(lang)
        if idx_lang >= 0:
            self._lang_combo.setCurrentIndex(idx_lang)

        # AI 配置 — 先填 model/base_url，再切换 provider（避免 _on_ai_provider_changed 覆盖已保存值）
        self._ai_model.setText(getattr(c, 'ai_model', 'gpt-4o-mini'))
        self._ai_api_key.setText(getattr(c, 'ai_api_key', ''))
        self._ai_base_url.setText(getattr(c, 'ai_base_url', ''))
        self._ai_temperature.setValue(float(getattr(c, 'ai_temperature', 0.7)))
        self._ai_max_tokens.setValue(int(getattr(c, 'ai_max_tokens', 2048)))
        self._ai_system_prompt_edit.setPlainText(getattr(c, 'ai_system_prompt', ''))

        ai_provider = getattr(c, 'ai_provider', 'openai')
        idx_ai = self._ai_provider.findData(ai_provider)
        if idx_ai >= 0:
            # 暂时断开自动填充信号，加载时不触发覆盖
            self._ai_provider.blockSignals(True)
            self._ai_provider.setCurrentIndex(idx_ai)
            self._ai_provider.blockSignals(False)
            # 只刷新模型列表，不覆盖已填入的 base_url/model
            self._refresh_model_preset_list(ai_provider)

    def _save(self):
        c = self.config
        # 记录保存前的语言，用于检测是否变化
        old_language = getattr(c, 'language', 'zh_CN')

        c.auto_start_enabled = self._auto_start_cb.isChecked()
        c.auto_start_task_id = self._auto_task_combo.currentData() or ""
        c.launch_behavior    = self._launch_behavior_combo.currentData() or "show"
        c.minimize_to_tray   = self._minimize_cb.isChecked()
        c.show_run_log       = self._show_log_cb.isChecked()
        c.minimize_on_run    = self._minimize_on_run_cb.isChecked()
        c.coord_pick_hotkey  = self._coord_hotkey.text().strip() or "F9"
        c.macro_stop_hotkey  = self._macro_stop_hotkey.text().strip() or "F10"
        c.force_stop_hotkey  = self._force_stop_hotkey.text().strip() or "ctrl+alt+s"

        c.reopen_last_project = self._reopen_cb.isChecked()
        c.auto_save_enabled   = self._auto_save_cb.isChecked()
        c.auto_save_interval  = self._auto_save_interval.value()
        c.max_undo_steps      = self._max_undo.value()
        c.screenshot_default_dir = self._screenshot_dir.text()

        c.smtp_server   = self._smtp_server.text()
        c.smtp_port     = self._smtp_port.value()
        c.smtp_user     = self._smtp_user.text()
        c.smtp_password = self._smtp_pass.text()
        c.smtp_ssl      = self._smtp_ssl.isChecked()

        c.imap_server   = self._imap_server.text()
        c.imap_port     = self._imap_port.value()
        c.imap_user     = self._imap_user.text()
        c.imap_password = self._imap_pass.text()
        c.imap_ssl      = self._imap_ssl.isChecked()

        c.log_path      = self._log_path.text()
        c.max_log_lines = self._max_log.value()

        c.theme = self._theme_combo.currentData() or "dark"
        c.language = self._lang_combo.currentData() or "zh_CN"

        # AI 配置
        c.ai_provider     = self._ai_provider.currentData() or "openai"
        c.ai_model        = self._ai_model.text().strip()
        c.ai_api_key      = self._ai_api_key.text().strip()
        c.ai_base_url     = self._ai_base_url.text().strip()
        c.ai_temperature  = self._ai_temperature.value()
        c.ai_max_tokens   = self._ai_max_tokens.value()
        c.ai_system_prompt = self._ai_system_prompt_edit.toPlainText().strip()

        # 立即应用语言设置（set_language 内部会通知所有 UI 观察者刷新文字）
        from ..i18n import set_language, tr as _tr
        set_language(c.language)

        self._apply_autostart(c.auto_start_enabled)
        self.config_changed.emit(c)
        QMessageBox.information(self, _tr("settings.saved"), _tr("settings.saved_msg"))

    def _open_language_market(self):
        from .language_market import LanguageMarketPage
        dlg = LanguageMarketPage(self)
        dlg.exec()
        # 市场关闭后刷新语言列表（用户可能新安装了语言包）
        from ..i18n import get_available_languages, load_language_dir as _lld
        import os as _os
        _lang_dir = _os.path.join(
            _os.environ.get("LOCALAPPDATA", _os.path.expanduser("~")),
            "XinyuCraft", "AutoFlow", "Language"
        )
        _lld(_lang_dir)
        current_data = self._lang_combo.currentData()
        self._lang_combo.blockSignals(True)
        self._lang_combo.clear()
        for code, name in get_available_languages():
            self._lang_combo.addItem(name, code)
        idx = self._lang_combo.findData(current_data)
        if idx >= 0:
            self._lang_combo.setCurrentIndex(idx)
        self._lang_combo.blockSignals(False)

    def _apply_autostart(self, enable: bool):
        import sys
        try:
            import winreg
            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
            app_name = "AutoFlow"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            if enable:
                if getattr(sys, "frozen", False):
                    # 打包 exe（onefile / onedir）：sys.argv[0] 就是 exe 真实路径
                    cmd = f'"{os.path.abspath(sys.argv[0])}" --minimized'
                else:
                    # 开发环境：python.exe main.py
                    exe = sys.executable
                    script = os.path.abspath(sys.argv[0])
                    cmd = f'"{exe}" "{script}" --minimized'
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            QMessageBox.warning(self, "注册表错误", f"开机自启设置失败：{e}")

    def refresh_tasks(self, tasks=None):
        """
        刷新任务相关下拉框（任务增删后调用），保留当前选中的任务 ID。
        tasks: 新任务列表（可选，若不传则使用 self.tasks）
        """
        if tasks is not None:
            self.tasks = tasks
        # 记住当前选中的任务 ID
        cur_task_id = self._auto_task_combo.currentData() or ""
        self._auto_task_combo.blockSignals(True)
        self._auto_task_combo.clear()
        self._auto_task_combo.addItem("（不运行任何任务）", "")
        for t in self.tasks:
            self._auto_task_combo.addItem(t.name, t.id)
        # 尝试恢复之前选中的项
        idx = self._auto_task_combo.findData(cur_task_id)
        if idx >= 0:
            self._auto_task_combo.setCurrentIndex(idx)
        self._auto_task_combo.blockSignals(False)

    def retranslate(self):
        """语言切换后刷新设置页内所有静态文字"""
        from ..i18n import tr
        # 保存按钮
        if hasattr(self, '_save_btn'):
            self._save_btn.setText("  " + tr("settings.save"))
        # Tab 标签
        tabs = self.findChild(QTabWidget)
        if tabs and tabs.count() >= 8:
            tabs.setTabText(0, "  " + tr("settings.general") + "  ")
            tabs.setTabText(1, "  " + tr("settings.project") + "  ")
            tabs.setTabText(2, "  " + tr("settings.email") + "  ")
            tabs.setTabText(3, "  " + tr("settings.appearance") + "  ")
            tabs.setTabText(4, "  " + tr("settings.hotkeys") + "  ")
            tabs.setTabText(5, "  AI  ")
            tabs.setTabText(6, "  " + tr("settings.advanced") + "  ")
            tabs.setTabText(7, "  " + tr("settings.about") + "  ")

        # ── 通用 Tab ──
        if hasattr(self, '_grp_startup'):
            self._grp_startup.setTitle(tr("settings.grp.startup"))
        if hasattr(self, '_auto_start_cb'):
            self._auto_start_cb.setText(tr("settings.auto_start"))
        if hasattr(self, '_launch_behavior_combo'):
            cur = self._launch_behavior_combo.currentData()
            self._launch_behavior_combo.blockSignals(True)
            self._launch_behavior_combo.setItemText(0, tr("settings.launch_behavior.show"))
            self._launch_behavior_combo.setItemText(1, tr("settings.launch_behavior.minimize"))
            self._launch_behavior_combo.setItemText(2, tr("settings.launch_behavior.tray"))
            self._launch_behavior_combo.blockSignals(False)
        if hasattr(self, '_grp_ui'):
            self._grp_ui.setTitle(tr("settings.grp.ui"))
        if hasattr(self, '_minimize_cb'):
            self._minimize_cb.setText(tr("settings.minimize_to_tray"))
        if hasattr(self, '_show_log_cb'):
            self._show_log_cb.setText(tr("settings.show_log"))

        # ── 项目 Tab ──
        if hasattr(self, '_grp_last_proj'):
            self._grp_last_proj.setTitle(tr("settings.grp.last_project"))
        if hasattr(self, '_reopen_cb'):
            self._reopen_cb.setText(tr("settings.reopen_last"))
        if hasattr(self, '_grp_autosave'):
            self._grp_autosave.setTitle(tr("settings.grp.autosave"))
        if hasattr(self, '_auto_save_cb'):
            self._auto_save_cb.setText(tr("settings.autosave_enable"))
        if hasattr(self, '_auto_save_interval'):
            self._auto_save_interval.setSuffix(tr("settings.autosave_unit"))
        if hasattr(self, '_grp_undo'):
            self._grp_undo.setTitle(tr("settings.grp.undo"))
        if hasattr(self, '_max_undo'):
            self._max_undo.setSuffix(tr("settings.undo_unit"))
        if hasattr(self, '_undo_hint'):
            self._undo_hint.setText(tr("settings.undo_hint"))
        if hasattr(self, '_grp_screenshot'):
            self._grp_screenshot.setTitle(tr("settings.grp.screenshot"))
        if hasattr(self, '_screenshot_dir'):
            self._screenshot_dir.setPlaceholderText(tr("settings.screenshot_ph"))
        if hasattr(self, '_screenshot_btn'):
            self._screenshot_btn.setText(tr("btn.browse"))

        # ── 邮箱 Tab ──
        if hasattr(self, '_grp_smtp'):
            self._grp_smtp.setTitle(tr("settings.grp.smtp"))
        if hasattr(self, '_smtp_ssl'):
            self._smtp_ssl.setText(tr("settings.smtp.ssl"))
        if hasattr(self, '_btn_test_smtp'):
            self._btn_test_smtp.setText(tr("btn.test_send"))
        if hasattr(self, '_grp_imap'):
            self._grp_imap.setTitle(tr("settings.grp.imap"))
        if hasattr(self, '_imap_ssl'):
            self._imap_ssl.setText(tr("settings.imap.ssl"))
        if hasattr(self, '_btn_test_imap'):
            self._btn_test_imap.setText(tr("btn.test_connect"))
        if hasattr(self, '_email_hint_lbl'):
            self._email_hint_lbl.setText(tr("settings.email_hint"))

        # ── 外观 Tab ──
        if hasattr(self, '_grp_lang'):
            self._grp_lang.setTitle(tr("settings.grp.lang"))
        if hasattr(self, '_lang_hint'):
            self._lang_hint.setText(tr("settings.language_hint"))
        if hasattr(self, '_grp_theme'):
            self._grp_theme.setTitle(tr("settings.grp.theme"))
        if hasattr(self, '_theme_hint'):
            self._theme_hint.setText(tr("settings.theme_hint"))

        # ── 按键 Tab ──
        if hasattr(self, '_grp_hotkeys_custom'):
            self._grp_hotkeys_custom.setTitle(tr("settings.grp.hotkeys_custom"))
        if hasattr(self, '_coord_hotkey_hint'):
            self._coord_hotkey_hint.setText(tr("settings.coord_hotkey_hint"))
        if hasattr(self, '_stop_hotkey_hint'):
            self._stop_hotkey_hint.setText(tr("settings.stop_hotkey_hint"))
        if hasattr(self, '_grp_hotkeys_ref'):
            self._grp_hotkeys_ref.setTitle(tr("settings.grp.hotkeys_ref"))

        # ── AI Tab ──
        if hasattr(self, '_ai_hint_top'):
            self._ai_hint_top.setText(tr("settings.ai_hint"))
        if hasattr(self, '_grp_ai_model'):
            self._grp_ai_model.setTitle(tr("settings.grp.ai_model"))
        if hasattr(self, '_show_key_cb'):
            self._show_key_cb.setText(tr("settings.ai_show_key"))
        if hasattr(self, '_grp_ai_params'):
            self._grp_ai_params.setTitle(tr("settings.grp.ai_params"))
        if hasattr(self, '_ai_temp_hint'):
            self._ai_temp_hint.setText(tr("settings.ai_temp_hint"))
        if hasattr(self, '_grp_ai_system'):
            self._grp_ai_system.setTitle(tr("settings.grp.ai_system"))
        if hasattr(self, '_btn_test_ai'):
            self._btn_test_ai.setText(tr("btn.test_ai"))

        # ── 高级 Tab ──
        if hasattr(self, '_grp_log'):
            self._grp_log.setTitle(tr("settings.grp.log"))
        if hasattr(self, '_log_browse_btn'):
            self._log_browse_btn.setText(tr("btn.browse"))

    def _pick_log_path(self):
        path, _ = QFileDialog.getSaveFileName(self, "选择日志文件", filter="日志文件 (*.log *.txt)")
        if path:
            self._log_path.setText(path)

    def _pick_folder(self, edit: QLineEdit):
        path = QFileDialog.getExistingDirectory(self, "选择目录")
        if path:
            edit.setText(path)

    def _test_smtp(self):
        import smtplib
        from email.utils import parseaddr
        try:
            _, addr = parseaddr(self._smtp_user.text())
            if not addr:
                addr = self._smtp_user.text().strip()
            if self._smtp_ssl.isChecked():
                s = smtplib.SMTP_SSL(self._smtp_server.text(), self._smtp_port.value(), timeout=8)
            else:
                s = smtplib.SMTP(timeout=8)
                s.connect(self._smtp_server.text(), self._smtp_port.value())
                s.ehlo(); s.starttls(); s.ehlo()
            s.login(addr, self._smtp_pass.text())
            s.quit()
            QMessageBox.information(self, "测试成功", "SMTP 连接和登录成功！")
        except Exception as e:
            QMessageBox.critical(self, "测试失败", f"SMTP 连接失败：\n{e}")

    def _test_imap(self):
        import imaplib
        try:
            if self._imap_ssl.isChecked():
                m = imaplib.IMAP4_SSL(self._imap_server.text(), self._imap_port.value())
            else:
                m = imaplib.IMAP4(self._imap_server.text(), self._imap_port.value())
            m.login(self._imap_user.text(), self._imap_pass.text())
            m.logout()
            QMessageBox.information(self, "测试成功", "IMAP 连接和登录成功！")
        except Exception as e:
            QMessageBox.critical(self, "测试失败", f"IMAP 连接失败：\n{e}")

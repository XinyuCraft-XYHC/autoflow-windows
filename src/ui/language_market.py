"""
AutoFlow 语言包市场 UI
从社区 GitHub 仓库下载语言包
"""
import os
import sys

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QDialog, QProgressBar, QMessageBox,
    QLineEdit
)

from ..i18n import tr, add_language_observer, remove_language_observer, \
    load_language_dir, get_available_languages, get_language, set_language
from ..updater import fetch_language_market, download_language, LANG_MARKET_URL

# 语言包存储目录（跟 i18n.load_language_dir 使用相同路径）
_LANG_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "XinyuCraft", "AutoFlow", "Language"
)


class LanguageCard(QFrame):
    """单个语言包卡片"""

    download_requested = pyqtSignal(dict)   # item dict

    def __init__(self, item: dict, installed: bool = False, parent=None):
        super().__init__(parent)
        self._item = item
        self._installed = installed
        self.setObjectName("plugin_card")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._build()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(12)

        # ── 语言旗标/图标 ──
        flag_lbl = QLabel()
        flag_lbl.setFixedSize(44, 44)
        flag_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        flag_lbl.setStyleSheet("font-size: 28px;")
        # 根据语言代码选 emoji 旗帜
        code = self._item.get("code", "")
        flags = {
            "ja_JP": "🇯🇵", "ko_KR": "🇰🇷", "fr_FR": "🇫🇷",
            "de_DE": "🇩🇪", "ru_RU": "🇷🇺", "es_ES": "🇪🇸",
            "pt_BR": "🇧🇷", "it_IT": "🇮🇹", "ar_SA": "🇸🇦",
            "tr_TR": "🇹🇷", "vi_VN": "🇻🇳", "th_TH": "🇹🇭",
        }
        flag_lbl.setText(flags.get(code, "🌐"))
        root.addWidget(flag_lbl)

        # ── 文字区 ──
        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name_lbl = QLabel(f"<b>{self._item.get('name', code)}</b>")
        name_lbl.setObjectName("plugin_name")
        name_row.addWidget(name_lbl)

        name_en_lbl = QLabel(f"({self._item.get('name_en', '')})")
        name_en_lbl.setStyleSheet("color: #6C7086; font-size: 11px;")
        name_row.addWidget(name_en_lbl)

        ver_lbl = QLabel(f"v{self._item.get('version', '1.0.0')}")
        ver_lbl.setStyleSheet("color: #6C7086; font-size: 11px;")
        name_row.addWidget(ver_lbl)

        if self._item.get("verified"):
            veri_lbl = QLabel("✅ 官方验证")
            veri_lbl.setStyleSheet("color: #A6E3A1; font-size: 10px;")
            name_row.addWidget(veri_lbl)

        name_row.addStretch()
        text_col.addLayout(name_row)

        desc_lbl = QLabel(self._item.get("description", ""))
        desc_lbl.setStyleSheet("color: #A6ADC8; font-size: 12px;")
        desc_lbl.setWordWrap(True)
        text_col.addWidget(desc_lbl)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(12)
        author_lbl = QLabel(f"👤 {self._item.get('author', '')}")
        author_lbl.setStyleSheet("color: #6C7086; font-size: 10px;")
        meta_row.addWidget(author_lbl)
        updated_lbl = QLabel(f"🕒 {self._item.get('updated', '')}")
        updated_lbl.setStyleSheet("color: #6C7086; font-size: 10px;")
        meta_row.addWidget(updated_lbl)
        meta_row.addStretch()
        text_col.addLayout(meta_row)

        root.addLayout(text_col)
        root.addStretch()

        # ── 右侧按钮 ──
        btn_col = QVBoxLayout()
        btn_col.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        btn_col.setSpacing(6)

        self._action_btn = QPushButton()
        self._action_btn.setFixedWidth(88)
        self._action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_btn_state()
        self._action_btn.clicked.connect(self._on_action)
        btn_col.addWidget(self._action_btn)

        # 语言代码标签
        code_lbl = QLabel(code)
        code_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        code_lbl.setStyleSheet(
            "background: #313244; color: #CDD6F4; border-radius: 3px;"
            " padding: 1px 6px; font-size: 10px;")
        btn_col.addWidget(code_lbl)

        root.addLayout(btn_col)

    def _update_btn_state(self):
        if self._installed:
            self._action_btn.setText("✅ 已安装")
            self._action_btn.setObjectName("btn_primary")
        else:
            self._action_btn.setText("⬇ 下载")
            self._action_btn.setObjectName("btn_flat")
        self._action_btn.style().unpolish(self._action_btn)
        self._action_btn.style().polish(self._action_btn)

    def _on_action(self):
        self.download_requested.emit(self._item)

    def set_installed(self, v: bool):
        self._installed = v
        self._update_btn_state()

    def set_downloading(self):
        self._action_btn.setText("下载中...")
        self._action_btn.setEnabled(False)
        self._action_btn.style().unpolish(self._action_btn)
        self._action_btn.style().polish(self._action_btn)


class LanguageMarketPage(QDialog):
    """语言包市场对话框"""

    # 跨线程信号
    _fetch_done_sig = pyqtSignal(list, str)   # items, error
    _dl_progress_sig = pyqtSignal(int, int)  # downloaded, total
    _dl_done_sig = pyqtSignal(str, str)      # lang_code, dest_path
    _dl_error_sig = pyqtSignal(str, str)     # lang_code, error_msg

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🌐 语言包市场")
        self.setMinimumSize(640, 520)
        self._items = []
        self._cards: dict[str, LanguageCard] = {}
        self._build_ui()
        self._connect_signals()
        self._load_market()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 顶部 ──
        header = QWidget()
        header.setObjectName("settings_header")
        hb = QHBoxLayout(header)
        hb.setContentsMargins(20, 14, 20, 14)

        title_lbl = QLabel("🌐 语言包市场")
        title_lbl.setObjectName("settings_title")
        hb.addWidget(title_lbl)
        hb.addStretch()

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("搜索语言...")
        self._search_edit.setFixedWidth(180)
        self._search_edit.textChanged.connect(self._filter_cards)
        hb.addWidget(self._search_edit)

        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.setObjectName("btn_flat")
        refresh_btn.clicked.connect(self._load_market)
        hb.addWidget(refresh_btn)

        github_btn = QPushButton("📦 贡献语言包")
        github_btn.setObjectName("btn_flat")
        github_btn.clicked.connect(lambda: self._open_url(LANG_MARKET_URL))
        hb.addWidget(github_btn)

        root.addWidget(header)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("sidebar_sep")
        root.addWidget(sep)

        # ── 提示栏 ──
        self._hint_bar = QLabel("正在加载语言包市场...")
        self._hint_bar.setStyleSheet("color: #6C7086; font-size: 11px; padding: 6px 20px;")
        root.addWidget(self._hint_bar)

        # ── 进度条（下载时显示）──
        self._progress_bar = QProgressBar()
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFixedHeight(6)
        self._progress_bar.hide()
        self._progress_bar.setStyleSheet(
            "QProgressBar{background:#1E1E2E;border-radius:3px;}"
            "QProgressBar::chunk{background:#89B4FA;border-radius:3px;}"
        )
        root.addWidget(self._progress_bar)

        # ── 卡片列表 ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._card_container = QWidget()
        self._card_layout = QVBoxLayout(self._card_container)
        self._card_layout.setContentsMargins(20, 12, 20, 20)
        self._card_layout.setSpacing(10)
        self._card_layout.addStretch()
        scroll.setWidget(self._card_container)
        root.addWidget(scroll)

    def _connect_signals(self):
        self._fetch_done_sig.connect(self._on_fetch_done)
        self._dl_progress_sig.connect(self._on_dl_progress)
        self._dl_done_sig.connect(self._on_dl_done)
        self._dl_error_sig.connect(self._on_dl_error)

    def _load_market(self):
        self._hint_bar.setText("正在加载语言包市场...")
        self._clear_cards()
        from ..updater import fetch_language_market
        fetch_language_market(
            lambda items, err: self._fetch_done_sig.emit(items or [], err or "")
        )

    def _clear_cards(self):
        for card in list(self._cards.values()):
            self._card_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

    def _get_installed_codes(self) -> set:
        """返回已安装（已有 JSON 文件）的语言代码集合"""
        installed = set()
        if os.path.isdir(_LANG_DIR):
            for fn in os.listdir(_LANG_DIR):
                if fn.lower().endswith(".json"):
                    installed.add(fn[:-5])
        return installed

    def _on_fetch_done(self, items: list, error: str):
        if error:
            self._hint_bar.setText(f"❌ {error}")
            return
        self._items = items
        self._hint_bar.setText(f"共 {len(items)} 个语言包可用，点击「下载」安装")
        self._render_cards(items)

    def _render_cards(self, items: list):
        self._clear_cards()
        installed = self._get_installed_codes()
        pos = 0  # 在 stretch 前插入
        for item in items:
            code = item.get("code", "")
            is_installed = code in installed
            card = LanguageCard(item, installed=is_installed)
            card.download_requested.connect(self._on_download)
            # 在 stretch 前插入
            self._card_layout.insertWidget(pos, card)
            self._cards[code] = card
            pos += 1

    def _filter_cards(self, text: str):
        text = text.lower().strip()
        items = self._items
        if text:
            items = [
                it for it in items
                if text in it.get("name", "").lower()
                or text in it.get("name_en", "").lower()
                or text in it.get("code", "").lower()
            ]
        self._render_cards(items)

    def _on_download(self, item: dict):
        code = item.get("code", "")
        url = item.get("download_url", "")
        if not url:
            QMessageBox.warning(self, "下载失败", "该语言包没有下载链接")
            return

        card = self._cards.get(code)
        if card:
            card.set_downloading()

        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.show()

        from ..updater import download_language
        download_language(
            download_url=url,
            lang_code=code,
            dest_lang_dir=_LANG_DIR,
            on_progress=lambda d, t: self._dl_progress_sig.emit(d, t),
            on_done=lambda path: self._dl_done_sig.emit(code, path),
            on_error=lambda err: self._dl_error_sig.emit(code, err),
        )

    def _on_dl_progress(self, downloaded: int, total: int):
        if total > 0:
            pct = int(downloaded * 100 / total)
            self._progress_bar.setValue(pct)

    def _on_dl_done(self, lang_code: str, dest_path: str):
        self._progress_bar.hide()
        card = self._cards.get(lang_code)
        if card:
            card.set_installed(True)
        # 重新加载语言目录，使新语言包立即可用
        load_language_dir(_LANG_DIR)
        QMessageBox.information(
            self, "安装成功",
            f"语言包 [{lang_code}] 已安装！\n"
            f"请在「设置 → 外观」中切换语言。"
        )

    def _on_dl_error(self, lang_code: str, error: str):
        self._progress_bar.hide()
        card = self._cards.get(lang_code)
        if card:
            card.set_installed(False)
        QMessageBox.critical(self, "下载失败", f"语言包 [{lang_code}] 下载失败：\n{error}")

    def _open_url(self, url: str):
        import webbrowser
        webbrowser.open(url)

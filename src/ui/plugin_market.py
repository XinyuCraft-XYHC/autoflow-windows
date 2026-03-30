"""
AutoFlow 插件市场 UI
从社区 GitHub 仓库下载和发布插件
"""
import os
import webbrowser

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QDialog, QProgressBar, QMessageBox,
    QLineEdit, QTabWidget
)

from ..plugin_manager import PluginManager, _PLUGIN_DIR
from ..i18n import tr, add_language_observer, remove_language_observer
from ..updater import fetch_plugin_market, download_plugin, PLUGIN_MARKET_URL, \
    PLUGIN_SUBMIT_URL, PLUGIN_DEV_DOCS_URL


class MarketPluginCard(QFrame):
    """插件市场中的单个插件卡片"""

    download_requested = pyqtSignal(dict)

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

        # ── 图标 ──
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(44, 44)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 28px;")
        icon_lbl.setText("🔌")
        root.addWidget(icon_lbl)

        # ── 文字区 ──
        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name_lbl = QLabel(f"<b>{self._item.get('name', '')}</b>")
        name_lbl.setObjectName("plugin_name")
        name_row.addWidget(name_lbl)

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

        # 标签行
        tags = self._item.get("tags", [])
        if tags:
            tags_row = QHBoxLayout()
            tags_row.setSpacing(4)
            for tag in tags[:5]:
                tl = QLabel(tag)
                tl.setStyleSheet(
                    "background: #313244; color: #CDD6F4; border-radius: 3px;"
                    " padding: 1px 6px; font-size: 10px;")
                tags_row.addWidget(tl)
            tags_row.addStretch()
            text_col.addLayout(tags_row)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(12)
        author_lbl = QLabel(f"👤 {self._item.get('author', '')}")
        author_lbl.setStyleSheet("color: #6C7086; font-size: 10px;")
        meta_row.addWidget(author_lbl)
        updated_lbl = QLabel(f"🕒 {self._item.get('updated', '')}")
        updated_lbl.setStyleSheet("color: #6C7086; font-size: 10px;")
        meta_row.addWidget(updated_lbl)
        min_ver = self._item.get("min_autoflow_version", "")
        if min_ver:
            req_lbl = QLabel(f"📌 需要 v{min_ver}+")
            req_lbl.setStyleSheet("color: #6C7086; font-size: 10px;")
            meta_row.addWidget(req_lbl)
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

        # 源码链接
        repo_url = self._item.get("repository", "")
        if repo_url:
            source_btn = QPushButton("📂 源码")
            source_btn.setObjectName("btn_flat")
            source_btn.setFixedWidth(88)
            source_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            source_btn.clicked.connect(lambda: webbrowser.open(repo_url))
            btn_col.addWidget(source_btn)

        root.addLayout(btn_col)

    def _update_btn_state(self):
        if self._installed:
            self._action_btn.setText("🔄 更新/重装")
            self._action_btn.setObjectName("btn_primary")
        else:
            self._action_btn.setText("⬇ 安装")
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


class PluginMarketDialog(QDialog):
    """插件市场对话框"""

    # 跨线程信号
    _fetch_done_sig = pyqtSignal(list, str)
    _dl_progress_sig = pyqtSignal(int, int)
    _dl_done_sig = pyqtSignal(str, str)    # plugin_id, dest_path
    _dl_error_sig = pyqtSignal(str, str)   # plugin_id, error

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🛒 插件市场")
        self.setMinimumSize(720, 580)
        self._items = []
        self._cards: dict[str, MarketPluginCard] = {}
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

        title_lbl = QLabel("🛒 插件市场")
        title_lbl.setObjectName("settings_title")
        hb.addWidget(title_lbl)
        hb.addStretch()

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("搜索插件...")
        self._search_edit.setFixedWidth(180)
        self._search_edit.textChanged.connect(self._filter_cards)
        hb.addWidget(self._search_edit)

        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.setObjectName("btn_flat")
        refresh_btn.clicked.connect(self._load_market)
        hb.addWidget(refresh_btn)

        # 发布插件按钮
        submit_btn = QPushButton("📤 发布我的插件")
        submit_btn.setObjectName("btn_primary")
        submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        submit_btn.clicked.connect(lambda: self._open_url(PLUGIN_SUBMIT_URL))
        hb.addWidget(submit_btn)

        root.addWidget(header)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("sidebar_sep")
        root.addWidget(sep)

        # ── 说明栏 ──
        info_bar = QWidget()
        info_bar.setStyleSheet("padding: 0 20px;")
        ib = QHBoxLayout(info_bar)
        ib.setContentsMargins(20, 8, 20, 4)
        self._hint_lbl = QLabel("正在加载插件市场...")
        self._hint_lbl.setStyleSheet("color: #6C7086; font-size: 11px;")
        ib.addWidget(self._hint_lbl)
        ib.addStretch()

        dev_lbl = QLabel(
            f'<a href="{PLUGIN_DEV_DOCS_URL}" style="color:#89B4FA;">如何开发插件？</a>'
            f' &nbsp;|&nbsp; '
            f'<a href="{PLUGIN_MARKET_URL}" style="color:#89B4FA;">插件市场仓库</a>'
        )
        dev_lbl.setOpenExternalLinks(True)
        ib.addWidget(dev_lbl)
        root.addWidget(info_bar)

        # ── 进度条 ──
        self._progress_bar = QProgressBar()
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

        # ── 发布引导区 ──
        publish_bar = QFrame()
        publish_bar.setObjectName("plugin_card")
        publish_bar.setFrameShape(QFrame.Shape.StyledPanel)
        pb = QHBoxLayout(publish_bar)
        pb.setContentsMargins(20, 14, 20, 14)
        pb_text = QLabel(
            "💡 <b>想发布你的插件？</b>  "
            "开发完成后，在 GitHub 提交 PR 到插件市场仓库，审核通过后就会出现在市场中。"
        )
        pb_text.setWordWrap(True)
        pb_text.setStyleSheet("font-size: 12px;")
        pb.addWidget(pb_text)
        pb.addStretch()
        guide_btn = QPushButton("📖 查看发布指南")
        guide_btn.setObjectName("btn_flat")
        guide_btn.clicked.connect(lambda: self._open_url(PLUGIN_DEV_DOCS_URL))
        pb.addWidget(guide_btn)
        submit_btn2 = QPushButton("📤 提交插件 PR")
        submit_btn2.setObjectName("btn_primary")
        submit_btn2.clicked.connect(lambda: self._open_url(PLUGIN_SUBMIT_URL))
        pb.addWidget(submit_btn2)
        root.addWidget(publish_bar)

    def _connect_signals(self):
        self._fetch_done_sig.connect(self._on_fetch_done)
        self._dl_progress_sig.connect(self._on_dl_progress)
        self._dl_done_sig.connect(self._on_dl_done)
        self._dl_error_sig.connect(self._on_dl_error)

    def _load_market(self):
        self._hint_lbl.setText("正在加载插件市场...")
        self._clear_cards()
        fetch_plugin_market(
            lambda items, err: self._fetch_done_sig.emit(items or [], err or "")
        )

    def _clear_cards(self):
        for card in list(self._cards.values()):
            self._card_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

    def _get_installed_ids(self) -> set:
        pm = PluginManager.instance()
        return {m.id for m in pm.get_all_metas()}

    def _on_fetch_done(self, items: list, error: str):
        if error:
            self._hint_lbl.setText(f"❌ {error}")
            return
        self._items = items
        self._hint_lbl.setText(f"共 {len(items)} 个插件可用")
        self._render_cards(items)

    def _render_cards(self, items: list):
        self._clear_cards()
        installed_ids = self._get_installed_ids()
        pos = 0
        for item in items:
            pid = item.get("id", "")
            card = MarketPluginCard(item, installed=pid in installed_ids)
            card.download_requested.connect(self._on_download)
            self._card_layout.insertWidget(pos, card)
            self._cards[pid] = card
            pos += 1

    def _filter_cards(self, text: str):
        text = text.lower().strip()
        items = self._items
        if text:
            items = [
                it for it in items
                if text in it.get("name", "").lower()
                or text in it.get("description", "").lower()
                or any(text in t.lower() for t in it.get("tags", []))
            ]
        self._render_cards(items)

    def _on_download(self, item: dict):
        pid = item.get("id", "")
        url = item.get("download_url", "")
        zip_dir = item.get("plugin_dir_in_zip", "")

        if not url or not zip_dir:
            QMessageBox.warning(self, "安装失败", "该插件没有有效的下载链接")
            return

        card = self._cards.get(pid)
        if card:
            card.set_downloading()

        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.show()

        download_plugin(
            download_url=url,
            plugin_dir_in_zip=zip_dir,
            dest_plugins_dir=_PLUGIN_DIR,
            on_progress=lambda d, t: self._dl_progress_sig.emit(d, t),
            on_done=lambda path: self._dl_done_sig.emit(pid, path),
            on_error=lambda err: self._dl_error_sig.emit(pid, err),
        )

    def _on_dl_progress(self, downloaded: int, total: int):
        if total > 0:
            self._progress_bar.setValue(int(downloaded * 100 / total))

    def _on_dl_done(self, plugin_id: str, dest_path: str):
        self._progress_bar.hide()
        card = self._cards.get(plugin_id)
        if card:
            card.set_installed(True)
        # 扫描并加载新安装的插件
        pm = PluginManager.instance()
        pm.scan()
        for meta in pm.get_all_metas():
            if meta.id == plugin_id and meta.enabled and not meta.loaded:
                pm._load_plugin(meta)
        QMessageBox.information(
            self, "安装成功",
            f"插件「{plugin_id}」已安装！\n请前往插件管理页面启用。"
        )

    def _on_dl_error(self, plugin_id: str, error: str):
        self._progress_bar.hide()
        card = self._cards.get(plugin_id)
        if card:
            card.set_installed(False)
        QMessageBox.critical(self, "安装失败", f"插件下载失败：\n{error}")

    def _open_url(self, url: str):
        import webbrowser
        webbrowser.open(url)

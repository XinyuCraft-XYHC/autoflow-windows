"""
AutoFlow 主题市场 UI
从社区 GitHub 仓库下载主题整合包
"""
import os
import threading

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QDialog, QProgressBar, QMessageBox,
    QLineEdit
)

from .theme_manager import (
    fetch_theme_market_index,
    download_theme_pack,
    list_installed_packs,
    remove_theme_pack,
)

_THEMES_REPO_URL = "https://github.com/XinyuCraft-XYHC/autoflow-themes"


class ThemeCard(QFrame):
    """单个主题整合包卡片"""

    download_requested = pyqtSignal(dict)
    remove_requested   = pyqtSignal(dict)

    def __init__(self, item: dict, installed: bool = False, parent=None):
        super().__init__(parent)
        self._item      = item
        self._installed = installed
        self.setObjectName("plugin_card")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._build()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(12)

        # 图标（emoji / 颜色方块）
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(44, 44)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 26px;")
        icon_lbl.setText(self._item.get("icon", "🎨"))
        root.addWidget(icon_lbl)

        # 文字区
        text_col = QVBoxLayout()
        text_col.setSpacing(3)

        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name_lbl = QLabel(f"<b>{self._item.get('name', self._item.get('id', ''))}</b>")
        name_lbl.setObjectName("plugin_name")
        name_row.addWidget(name_lbl)

        ver_lbl = QLabel(f"v{self._item.get('version', '1.0.0')}")
        ver_lbl.setStyleSheet("color: #6C7086; font-size: 11px;")
        name_row.addWidget(ver_lbl)

        # base_theme 标签
        base = self._item.get("base_theme", "")
        if base:
            base_lbl = QLabel(f"  {base}  ")
            base_lbl.setStyleSheet(
                "background: #313244; color: #CDD6F4; border-radius: 3px;"
                " padding: 1px 6px; font-size: 10px;"
            )
            name_row.addWidget(base_lbl)

        if self._item.get("verified"):
            veri_lbl = QLabel("✅ 官方")
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

        # 右侧按钮
        btn_col = QVBoxLayout()
        btn_col.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        btn_col.setSpacing(6)

        self._action_btn = QPushButton()
        self._action_btn.setFixedWidth(88)
        self._action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_btn_state()
        self._action_btn.clicked.connect(self._on_action)
        btn_col.addWidget(self._action_btn)

        if self._installed:
            rm_btn = QPushButton("🗑 删除")
            rm_btn.setObjectName("btn_flat")
            rm_btn.setFixedWidth(88)
            rm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            rm_btn.clicked.connect(lambda: self.remove_requested.emit(self._item))
            btn_col.addWidget(rm_btn)

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


class ThemeMarketPage(QDialog):
    """主题市场对话框"""

    _fetch_done_sig   = pyqtSignal(list, str)
    _dl_progress_sig  = pyqtSignal(int, int)
    _dl_done_sig      = pyqtSignal(str)      # pack_id
    _dl_error_sig     = pyqtSignal(str, str) # pack_id, error

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🎨 主题市场")
        self.setMinimumSize(680, 560)
        self._items: list = []
        self._cards: dict[str, ThemeCard] = {}
        self._build_ui()
        self._connect_signals()
        self._load_market()

    # ─── UI 构建 ───

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 顶部
        header = QWidget()
        header.setObjectName("settings_header")
        hb = QHBoxLayout(header)
        hb.setContentsMargins(20, 14, 20, 14)

        title_lbl = QLabel("🎨 主题市场")
        title_lbl.setObjectName("settings_title")
        hb.addWidget(title_lbl)
        hb.addStretch()

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("搜索主题...")
        self._search_edit.setFixedWidth(180)
        self._search_edit.textChanged.connect(self._filter_cards)
        hb.addWidget(self._search_edit)

        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.setObjectName("btn_flat")
        refresh_btn.clicked.connect(self._load_market)
        hb.addWidget(refresh_btn)

        github_btn = QPushButton("📦 贡献主题")
        github_btn.setObjectName("btn_flat")
        github_btn.clicked.connect(lambda: self._open_url(_THEMES_REPO_URL))
        hb.addWidget(github_btn)

        root.addWidget(header)

        # 进度条
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setFixedHeight(3)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(
            "QProgressBar{border:none;background:transparent;}"
            "QProgressBar::chunk{background:#89B4FA;}"
        )
        self._progress.setVisible(False)
        root.addWidget(self._progress)

        # 状态标签
        self._status_lbl = QLabel("正在连接市场...")
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_lbl.setObjectName("hint")
        self._status_lbl.setContentsMargins(20, 8, 20, 8)
        root.addWidget(self._status_lbl)

        # 滚动列表
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._list_container = QWidget()
        self._list_layout    = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(12, 12, 12, 12)
        self._list_layout.setSpacing(10)
        self._list_layout.addStretch()
        scroll.setWidget(self._list_container)
        root.addWidget(scroll, 1)

        # 底部
        footer = QWidget()
        fb = QHBoxLayout(footer)
        fb.setContentsMargins(20, 10, 20, 10)
        self._footer_lbl = QLabel("")
        self._footer_lbl.setObjectName("hint")
        fb.addWidget(self._footer_lbl)
        fb.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setObjectName("btn_primary")
        close_btn.setFixedWidth(80)
        close_btn.clicked.connect(self.accept)
        fb.addWidget(close_btn)
        root.addWidget(footer)

    def _connect_signals(self):
        self._fetch_done_sig.connect(self._on_fetch_done)
        self._dl_progress_sig.connect(self._on_dl_progress)
        self._dl_done_sig.connect(self._on_dl_done)
        self._dl_error_sig.connect(self._on_dl_error)

    # ─── 数据加载 ───

    def _load_market(self):
        self._status_lbl.setText("正在连接市场...")
        self._status_lbl.setVisible(True)
        self._progress.setVisible(True)
        # 清空旧卡片
        for card in self._cards.values():
            card.deleteLater()
        self._cards.clear()
        # 已清理 stretch，重新加
        while self._list_layout.count() > 0:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._list_layout.addStretch()

        def _fetch():
            items = fetch_theme_market_index()
            if items is None:
                self._fetch_done_sig.emit([], "无法连接到主题市场，请检查网络连接。")
            else:
                self._fetch_done_sig.emit(items, "")

        threading.Thread(target=_fetch, daemon=True).start()

    def _on_fetch_done(self, items: list, error: str):
        self._progress.setVisible(False)
        if error:
            self._status_lbl.setText(error)
            return
        if not items:
            self._status_lbl.setText("主题市场暂无内容，敬请期待。")
            return
        self._status_lbl.setVisible(False)
        self._items = items

        installed_ids = {p.id for p in list_installed_packs()}

        # 已安装放前面
        sorted_items = sorted(items, key=lambda x: (0 if x.get("id") in installed_ids else 1))

        for item in sorted_items:
            pack_id = item.get("id", "")
            installed = pack_id in installed_ids
            card = ThemeCard(item, installed=installed)
            card.download_requested.connect(self._download_pack)
            card.remove_requested.connect(self._remove_pack)
            self._cards[pack_id] = card
            self._list_layout.insertWidget(self._list_layout.count() - 1, card)

        self._footer_lbl.setText(f"共 {len(items)} 个主题包，{len(installed_ids)} 个已安装")

    # ─── 搜索过滤 ───

    def _filter_cards(self, text: str):
        text = text.strip().lower()
        for pack_id, card in self._cards.items():
            item = next((i for i in self._items if i.get("id") == pack_id), {})
            visible = (
                not text
                or text in item.get("name", "").lower()
                or text in item.get("description", "").lower()
                or text in item.get("author", "").lower()
            )
            card.setVisible(visible)

    # ─── 下载 ───

    def _download_pack(self, item: dict):
        pack_id = item.get("id", "")
        if pack_id in self._cards:
            self._cards[pack_id].set_downloading()
        self._progress.setVisible(True)
        self._status_lbl.setText(f"正在下载「{item.get('name', pack_id)}」...")
        self._status_lbl.setVisible(True)

        def _worker():
            try:
                def _cb(done, total):
                    self._dl_progress_sig.emit(done, total)
                download_theme_pack(item, progress_cb=_cb)
                self._dl_done_sig.emit(pack_id)
            except Exception as e:
                self._dl_error_sig.emit(pack_id, str(e))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_dl_progress(self, done: int, total: int):
        if total > 0:
            self._progress.setRange(0, total)
            self._progress.setValue(done)
        else:
            self._progress.setRange(0, 0)

    def _on_dl_done(self, pack_id: str):
        self._progress.setVisible(False)
        self._status_lbl.setVisible(False)
        if pack_id in self._cards:
            self._cards[pack_id].set_installed(True)
        QMessageBox.information(self, "下载成功",
                                f"主题包已安装。\n前往「设置 → 外观 → 整合包」中导入并应用。")

    def _on_dl_error(self, pack_id: str, error: str):
        self._progress.setVisible(False)
        self._status_lbl.setVisible(False)
        if pack_id in self._cards:
            self._cards[pack_id]._action_btn.setEnabled(True)
            self._cards[pack_id]._update_btn_state()
        QMessageBox.warning(self, "下载失败", f"下载主题包时出错：\n{error}")

    # ─── 删除 ───

    def _remove_pack(self, item: dict):
        pack_id = item.get("id", "")
        name = item.get("name", pack_id)
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除主题包「{name}」吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        remove_theme_pack(pack_id)
        if pack_id in self._cards:
            self._cards[pack_id].set_installed(False)
        QMessageBox.information(self, "已删除", f"主题包「{name}」已删除。")

    # ─── 工具 ───

    @staticmethod
    def _open_url(url: str):
        import subprocess
        try:
            subprocess.Popen(["start", url], shell=True)
        except Exception:
            pass

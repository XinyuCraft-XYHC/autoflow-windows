"""
AutoFlow 插件管理器 UI 页面
"""
import os
import subprocess
import sys

from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QStackedWidget, QMessageBox,
    QFileDialog, QDialog, QTextEdit, QDialogButtonBox, QCheckBox,
    QLineEdit
)

from ..plugin_manager import PluginManager, PluginMeta, _PLUGIN_DIR
from ..i18n import tr, add_language_observer, remove_language_observer


class PluginCard(QFrame):
    """单个插件卡片"""

    toggle_requested = pyqtSignal(str, bool)   # (plugin_id, enabled)
    settings_requested = pyqtSignal(str)       # plugin_id
    detail_requested = pyqtSignal(str)         # plugin_id

    def __init__(self, meta: PluginMeta, parent=None):
        super().__init__(parent)
        self.meta = meta
        self.setObjectName("plugin_card")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._build()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(12)

        # ── 图标 ──
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(44, 44)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if os.path.exists(self.meta.icon_path):
            pix = QPixmap(self.meta.icon_path).scaled(
                40, 40, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            icon_lbl.setPixmap(pix)
        else:
            icon_lbl.setText("🔌")
            icon_lbl.setStyleSheet("font-size: 24px;")
        root.addWidget(icon_lbl)

        # ── 文本区 ──
        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        self._name_lbl = QLabel(f"<b>{self.meta.name}</b>")
        self._name_lbl.setObjectName("plugin_name")
        name_row.addWidget(self._name_lbl)

        ver_lbl = QLabel(f"v{self.meta.version}")
        ver_lbl.setStyleSheet("color: #6C7086; font-size: 11px;")
        name_row.addWidget(ver_lbl)

        if self.meta.author:
            author_lbl = QLabel(f"· {self.meta.author}")
            author_lbl.setStyleSheet("color: #6C7086; font-size: 11px;")
            name_row.addWidget(author_lbl)
        name_row.addStretch()
        text_col.addLayout(name_row)

        self._desc_lbl = QLabel(self.meta.description or tr("plugin.no_desc"))
        self._desc_lbl.setStyleSheet("color: #A6ADC8; font-size: 12px;")
        self._desc_lbl.setWordWrap(True)
        text_col.addWidget(self._desc_lbl)

        # 错误提示
        if self.meta.error:
            err_lbl = QLabel(f"⚠ {self.meta.error[:80]}...")
            err_lbl.setStyleSheet("color: #F38BA8; font-size: 11px;")
            text_col.addWidget(err_lbl)

        # 标签行
        if self.meta.tags:
            tags_row = QHBoxLayout()
            tags_row.setSpacing(4)
            for tag in self.meta.tags[:5]:
                tl = QLabel(tag)
                tl.setObjectName("plugin_tag")
                tl.setStyleSheet(
                    "background: #313244; color: #CDD6F4; border-radius: 3px;"
                    " padding: 1px 6px; font-size: 10px;")
                tags_row.addWidget(tl)
            tags_row.addStretch()
            text_col.addLayout(tags_row)

        root.addLayout(text_col)
        root.addStretch()

        # ── 右侧按钮区 ──
        btn_col = QVBoxLayout()
        btn_col.setSpacing(6)
        btn_col.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # 启用/禁用开关
        self._toggle_btn = QPushButton()
        self._toggle_btn.setObjectName("btn_primary" if self.meta.enabled else "btn_flat")
        self._toggle_btn.setFixedWidth(72)
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_toggle_text()
        self._toggle_btn.clicked.connect(self._on_toggle)
        btn_col.addWidget(self._toggle_btn)

        # 设置按钮（若插件有 settings）
        self._settings_btn = QPushButton(tr("plugin.settings_btn"))
        self._settings_btn.setObjectName("btn_flat")
        self._settings_btn.setFixedWidth(72)
        self._settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_btn.clicked.connect(lambda: self.settings_requested.emit(self.meta.id))
        btn_col.addWidget(self._settings_btn)

        # 详情按钮
        self._detail_btn = QPushButton(tr("plugin.detail_btn"))
        self._detail_btn.setObjectName("btn_flat")
        self._detail_btn.setFixedWidth(72)
        self._detail_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._detail_btn.clicked.connect(lambda: self.detail_requested.emit(self.meta.id))
        btn_col.addWidget(self._detail_btn)

        root.addLayout(btn_col)

    def _update_toggle_text(self):
        if self.meta.enabled:
            self._toggle_btn.setText(tr("plugin.enabled_btn"))
            self._toggle_btn.setObjectName("btn_primary")
        else:
            self._toggle_btn.setText(tr("plugin.disabled_btn"))
            self._toggle_btn.setObjectName("btn_flat")
        # 触发 QSS 重新计算
        self._toggle_btn.style().unpolish(self._toggle_btn)
        self._toggle_btn.style().polish(self._toggle_btn)

    def _on_toggle(self):
        self.toggle_requested.emit(self.meta.id, not self.meta.enabled)

    def refresh(self):
        """刷新卡片状态（启用/错误状态变化后调用）"""
        self._update_toggle_text()


class PluginManagerPage(QWidget):
    """插件管理器主页面"""

    back_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pm = PluginManager.instance()
        self._pm.add_on_changed(self._on_plugins_changed)
        self._cards: dict[str, PluginCard] = {}
        self._build_ui()
        self._refresh_list()
        add_language_observer(self._retranslate)

    def __del__(self):
        try:
            self._pm.remove_on_changed(self._on_plugins_changed)
            remove_language_observer(self._retranslate)
        except Exception:
            pass

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 顶部工具栏 ──
        toolbar = QWidget()
        toolbar.setObjectName("settings_header")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(20, 14, 20, 14)

        self._back_btn = QPushButton("← " + tr("plugin.back"))
        self._back_btn.setObjectName("btn_flat")
        self._back_btn.clicked.connect(self.back_requested.emit)
        tb_layout.addWidget(self._back_btn)

        self._title_lbl = QLabel(tr("plugin.title"))
        self._title_lbl.setObjectName("settings_title")
        tb_layout.addWidget(self._title_lbl)
        tb_layout.addStretch()

        # 搜索框
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText(tr("plugin.search_ph"))
        self._search_edit.setFixedWidth(200)
        self._search_edit.textChanged.connect(self._on_search)
        tb_layout.addWidget(self._search_edit)

        # 安装插件按钮（从文件夹）
        self._install_btn = QPushButton("📦 " + tr("plugin.install_btn"))
        self._install_btn.setObjectName("btn_primary")
        self._install_btn.clicked.connect(self._install_from_folder)
        tb_layout.addWidget(self._install_btn)

        # 打开插件目录
        self._open_dir_btn = QPushButton("📁 " + tr("plugin.open_dir_btn"))
        self._open_dir_btn.setObjectName("btn_flat")
        self._open_dir_btn.clicked.connect(self._open_plugin_dir)
        tb_layout.addWidget(self._open_dir_btn)

        # 刷新
        self._refresh_btn = QPushButton("🔄 " + tr("btn.refresh"))
        self._refresh_btn.setObjectName("btn_flat")
        self._refresh_btn.clicked.connect(self._on_reload)
        tb_layout.addWidget(self._refresh_btn)

        root.addWidget(toolbar)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("sidebar_sep")
        root.addWidget(sep)

        # ── 统计条 ──
        stats_bar = QWidget()
        stats_bar.setStyleSheet("padding: 0 20px;")
        sb_layout = QHBoxLayout(stats_bar)
        sb_layout.setContentsMargins(20, 8, 20, 4)
        self._stats_lbl = QLabel()
        self._stats_lbl.setStyleSheet("color: #6C7086; font-size: 11px;")
        sb_layout.addWidget(self._stats_lbl)
        sb_layout.addStretch()
        # 「如何开发插件」链接
        from ..updater import PLUGIN_DEV_DOCS_URL
        dev_lbl = QLabel(
            f'<a href="{PLUGIN_DEV_DOCS_URL}" style="color:#89B4FA;">'
            f'{tr("plugin.dev_docs")}</a>'
        )
        dev_lbl.setOpenExternalLinks(True)
        sb_layout.addWidget(dev_lbl)
        root.addWidget(stats_bar)

        # ── 插件卡片列表 ──
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

        # 空状态提示
        self._empty_lbl = QLabel(tr("plugin.empty_hint"))
        self._empty_lbl.setObjectName("hint")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet("color: #6C7086; font-size: 14px; padding: 40px;")
        self._card_layout.insertWidget(0, self._empty_lbl)

    # ── 列表刷新 ──

    def _refresh_list(self, search: str = ""):
        # 清除现有卡片（保留空状态标签和底部弹性）
        for card in list(self._cards.values()):
            self._card_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

        metas = self._pm.get_all_metas()
        if search:
            kw = search.lower()
            metas = [m for m in metas
                     if kw in m.name.lower()
                     or kw in m.description.lower()
                     or any(kw in t.lower() for t in m.tags)]

        enabled_count = sum(1 for m in self._pm.get_all_metas() if m.enabled)
        total = len(self._pm.get_all_metas())
        self._stats_lbl.setText(
            tr("plugin.stats").format(total=total, enabled=enabled_count)
        )
        self._empty_lbl.setVisible(len(metas) == 0)

        insert_pos = 1  # 0 是 empty_lbl
        for meta in metas:
            card = PluginCard(meta)
            card.toggle_requested.connect(self._on_toggle)
            card.settings_requested.connect(self._on_settings)
            card.detail_requested.connect(self._on_detail)
            self._card_layout.insertWidget(insert_pos, card)
            self._cards[meta.id] = card
            insert_pos += 1

    def _on_search(self, text: str):
        self._refresh_list(text.strip())

    def _on_plugins_changed(self):
        QTimer.singleShot(0, lambda: self._refresh_list(self._search_edit.text()))

    # ── 操作 ──

    def _on_toggle(self, plugin_id: str, enable: bool):
        self._pm.set_enabled(plugin_id, enable)
        meta = next((m for m in self._pm.get_all_metas() if m.id == plugin_id), None)
        if meta:
            action = tr("plugin.enabled_btn") if enable else tr("plugin.disabled_btn")
            if meta.error and enable:
                QMessageBox.warning(self, tr("plugin.load_failed"),
                                    f"{meta.name}\n\n{meta.error}")
        card = self._cards.get(plugin_id)
        if card:
            card.refresh()

    def _on_settings(self, plugin_id: str):
        meta = next((m for m in self._pm.get_all_metas() if m.id == plugin_id), None)
        if not meta or not meta.instance:
            QMessageBox.information(self, tr("plugin.no_settings_title"),
                                    tr("plugin.no_settings_msg"))
            return
        w = meta.instance.get_settings_widget()
        if w is None:
            QMessageBox.information(self, tr("plugin.no_settings_title"),
                                    tr("plugin.no_settings_msg"))
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"{meta.name} — {tr('plugin.settings_btn')}")
        dlg.setMinimumSize(500, 400)
        layout = QVBoxLayout(dlg)
        layout.addWidget(w)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(dlg.accept)
        layout.addWidget(btns)
        dlg.exec()

    def _on_detail(self, plugin_id: str):
        meta = next((m for m in self._pm.get_all_metas() if m.id == plugin_id), None)
        if not meta:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"{meta.name} — {tr('plugin.detail_btn')}")
        dlg.setMinimumSize(480, 360)
        layout = QVBoxLayout(dlg)

        # 基本信息
        info_html = f"""
        <b>{meta.name}</b> v{meta.version}<br>
        <span style='color:#6C7086'>{tr('plugin.author_label')}: {meta.author or '-'}</span><br>
        <span style='color:#6C7086'>{tr('plugin.id_label')}: {meta.id}</span><br>
        <span style='color:#6C7086'>{tr('plugin.dir_label')}: {meta.dir}</span><br><br>
        {meta.description or tr('plugin.no_desc')}
        """
        info_lbl = QLabel(info_html)
        info_lbl.setWordWrap(True)
        info_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(info_lbl)

        # 功能块列表
        if meta.instance:
            blocks = []
            for bdef in meta.instance.get_blocks():
                blocks.append(f"  {bdef.get('icon','🔌')} {bdef.get('label', bdef.get('type','?'))}")
            if blocks:
                bl = QLabel(f"<b>{tr('plugin.provided_blocks')}:</b><br>" + "<br>".join(blocks))
                bl.setStyleSheet("font-size: 12px; color: #CDD6F4;")
                layout.addWidget(bl)

        # README
        readme_path = os.path.join(meta.dir, "README.md")
        if os.path.exists(readme_path):
            try:
                with open(readme_path, "r", encoding="utf-8") as f:
                    readme = f.read()
                readme_edit = QTextEdit()
                readme_edit.setReadOnly(True)
                readme_edit.setPlainText(readme)
                readme_edit.setMaximumHeight(160)
                layout.addWidget(readme_edit)
            except Exception:
                pass

        # 错误信息
        if meta.error:
            err_edit = QTextEdit()
            err_edit.setReadOnly(True)
            err_edit.setPlainText(meta.error)
            err_edit.setStyleSheet("color: #F38BA8; font-size: 11px;")
            err_edit.setMaximumHeight(100)
            layout.addWidget(err_edit)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(dlg.accept)
        layout.addWidget(btns)
        dlg.exec()

    def _on_reload(self):
        """重新扫描插件目录"""
        self._pm.scan()
        # 加载新发现的已启用插件
        for meta in self._pm.get_all_metas():
            if meta.enabled and not meta.loaded:
                self._pm._load_plugin(meta)
        self._refresh_list(self._search_edit.text())

    def _install_from_folder(self):
        """从文件夹安装插件"""
        folder = QFileDialog.getExistingDirectory(
            self, tr("plugin.install_from_folder"), os.path.expanduser("~")
        )
        if not folder:
            return
        # 检查是否有 plugin.json
        info_path = os.path.join(folder, "plugin.json")
        if not os.path.exists(info_path):
            QMessageBox.warning(self, tr("plugin.install_error"),
                                tr("plugin.no_plugin_json").format(path=folder))
            return

        import json as _json, shutil
        try:
            with open(info_path, "r", encoding="utf-8") as f:
                info = _json.load(f)
            pid = info.get("id", os.path.basename(folder))
            dest = os.path.join(_PLUGIN_DIR, pid)
            if os.path.exists(dest):
                reply = QMessageBox.question(
                    self, tr("plugin.install_overwrite_title"),
                    tr("plugin.install_overwrite_msg").format(name=info.get("name", pid)),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
                shutil.rmtree(dest)
            shutil.copytree(folder, dest)
            self._on_reload()
            QMessageBox.information(self, tr("plugin.install_ok_title"),
                                    tr("plugin.install_ok_msg").format(
                                        name=info.get("name", pid)))
        except Exception as e:
            QMessageBox.critical(self, tr("plugin.install_error"), str(e))

    def _open_plugin_dir(self):
        """用资源管理器打开插件目录"""
        os.makedirs(_PLUGIN_DIR, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(_PLUGIN_DIR)
        else:
            subprocess.Popen(["xdg-open", _PLUGIN_DIR])

    # ── 国际化 ──

    def _retranslate(self):
        if hasattr(self, '_back_btn'):
            self._back_btn.setText("← " + tr("plugin.back"))
        if hasattr(self, '_title_lbl'):
            self._title_lbl.setText(tr("plugin.title"))
        if hasattr(self, '_search_edit'):
            self._search_edit.setPlaceholderText(tr("plugin.search_ph"))
        if hasattr(self, '_install_btn'):
            self._install_btn.setText("📦 " + tr("plugin.install_btn"))
        if hasattr(self, '_open_dir_btn'):
            self._open_dir_btn.setText("📁 " + tr("plugin.open_dir_btn"))
        if hasattr(self, '_refresh_btn'):
            self._refresh_btn.setText("🔄 " + tr("btn.refresh"))
        if hasattr(self, '_empty_lbl'):
            self._empty_lbl.setText(tr("plugin.empty_hint"))
        self._refresh_list(self._search_edit.text() if hasattr(self, '_search_edit') else "")

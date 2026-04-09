"""
AutoFlow 更新对话框
检测到新版本时弹出，支持：
  - 前往下载页（手动）
  - 自动下载安装（选择下载源 → 进度条 → 启动安装包 → 关闭程序）
  - 忽略此版本 / 稍后再说
"""
import os
import sys
import threading
import urllib.request
import urllib.error
import tempfile

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QWidget, QTextEdit, QComboBox, QFrame,
    QApplication
)
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import QUrl

from ..i18n import tr


# ─── 下载源定义 ───────────────────────────────────────────────
_GITHUB_OWNER = "XinyuCraft-XYHC"
_GITHUB_REPO  = "autoflow-windows"

def _build_sources(download_url: str, tag: str) -> list:
    """
    构建可用下载源列表。
    优先使用 API 返回的 download_url（browser_download_url），
    若为空则按 GitHub Release 资产的固定 URL 规律拼接，确保始终能生成至少一个源。
    """
    filename = f"AutoFlow_{tag}_Setup.exe"

    # GitHub Release 资产直链：API 有就用，没有就按固定规律拼
    gh_direct = download_url or (
        f"https://github.com/{_GITHUB_OWNER}/{_GITHUB_REPO}"
        f"/releases/download/{tag}/{filename}"
    )

    sources = [
        # ① GitHub 官方直链
        ("GitHub Release（官方）", gh_direct),
        # ② ghproxy.net 国内加速镜像
        ("GitHub Proxy 镜像（国内加速）",
         f"https://ghproxy.net/{gh_direct}"),
        # ③ gitclone.com 镜像
        ("GitClone 镜像（国内加速）",
         f"https://gitclone.com/github.com/{_GITHUB_OWNER}/{_GITHUB_REPO}"
         f"/releases/download/{tag}/{filename}"),
    ]

    return sources


class _DownloadWorker(threading.Thread):
    """后台下载线程，支持无进度超时自动切换源"""

    def __init__(self, sources: list, dest: str,
                 on_progress, on_done, on_error,
                 on_source_switch=None,
                 stall_timeout: float = 6.0):
        """
        sources: [(label, url), ...]
        stall_timeout: 下载进度无变化超过此秒数则切换到下一源（默认6秒）
        on_source_switch(label): 切换源时的回调（可选）
        """
        super().__init__(daemon=True)
        self._sources = sources
        self._dest = dest
        self._on_progress = on_progress
        self._on_done = on_done
        self._on_error = on_error
        self._on_source_switch = on_source_switch
        self._stall_timeout = stall_timeout
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        last_error = None
        for label, url in self._sources:
            if self._cancelled:
                return
            try:
                if self._on_source_switch and label != self._sources[0][0]:
                    self._on_source_switch(label)
                self._download_from(url)
                return  # 成功，退出
            except _StallTimeout:
                last_error = f"下载源 [{label}] 超时无响应，正在切换..."
                continue
            except Exception as e:
                if self._cancelled:
                    return
                last_error = str(e)
                continue

        # 所有源均失败
        if not self._cancelled and self._on_error:
            self._on_error(last_error or "所有下载源均失败，请检查网络或手动下载")

    def _download_from(self, url: str):
        """从单个 URL 下载，无进度超过 stall_timeout 秒则抛出 _StallTimeout"""
        import time
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "AutoFlow-Updater/1.0"}
        )
        with urllib.request.urlopen(req, timeout=self._stall_timeout + 5) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 65536
            last_progress_time = time.monotonic()

            with open(self._dest, "wb") as f:
                while not self._cancelled:
                    # 用 select/非阻塞读配合超时检测
                    chunk = None
                    read_done = threading.Event()
                    read_result = [None, None]

                    def _read():
                        try:
                            read_result[0] = resp.read(chunk_size)
                        except Exception as ex:
                            read_result[1] = ex
                        finally:
                            read_done.set()

                    t = threading.Thread(target=_read, daemon=True)
                    t.start()
                    # 等待最多 stall_timeout 秒
                    read_done.wait(timeout=self._stall_timeout)

                    if not read_done.is_set():
                        # 超时仍未读到数据
                        raise _StallTimeout(f"下载 {self._stall_timeout:.0f}s 无进度")

                    if read_result[1] is not None:
                        raise read_result[1]

                    chunk = read_result[0]
                    if not chunk:
                        break

                    f.write(chunk)
                    downloaded += len(chunk)
                    last_progress_time = time.monotonic()
                    if self._on_progress:
                        self._on_progress(downloaded, total)

        if self._cancelled:
            try:
                os.remove(self._dest)
            except Exception:
                pass
            return

        if self._on_done:
            self._on_done(self._dest)


class _StallTimeout(Exception):
    """下载进度长时间无变化，触发源切换"""
    pass


class UpdateDialog(QDialog):
    """发现新版本弹窗"""

    # 跨线程信号
    _progress_sig      = pyqtSignal(int, int)   # downloaded, total
    _done_sig          = pyqtSignal(str)        # dest_path
    _error_sig         = pyqtSignal(str)        # error_msg
    _source_switch_sig = pyqtSignal(str)        # new_source_label

    def __init__(self, result: dict, current_version: str, parent=None):
        super().__init__(parent)
        self._result = result
        self._current_version = current_version
        self._worker: _DownloadWorker = None
        self._dest_path: str = None

        self.setWindowTitle(tr("update.title", default="发现新版本"))
        self.setMinimumWidth(520)
        self.setModal(True)

        self._build_ui()
        self._connect_signals()

    # ─── UI 构建 ────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        tag  = self._result.get("latest_tag", "")
        name = self._result.get("latest_name", tag)
        body = self._result.get("body", "")

        # ── 标题区 ──
        title_row = QHBoxLayout()
        icon_lbl = QLabel("🎉")
        icon_lbl.setStyleSheet("font-size: 28px;")
        title_row.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        h_lbl = QLabel(tr("update.found", default="发现新版本！").format(latest=tag))
        h_lbl.setStyleSheet("font-size: 15px; font-weight: bold;")
        title_col.addWidget(h_lbl)

        ver_row = QHBoxLayout()
        ver_row.setSpacing(16)
        ver_row.addWidget(QLabel(
            tr("update.current", default="当前版本：{current}").format(current=self._current_version)
        ))
        latest_lbl = QLabel(
            tr("update.latest", default="最新版本：{latest}").format(latest=tag)
        )
        latest_lbl.setStyleSheet("color: #89B4FA; font-weight: bold;")
        ver_row.addWidget(latest_lbl)
        ver_row.addStretch()
        title_col.addLayout(ver_row)

        title_row.addLayout(title_col)
        title_row.addStretch()
        root.addLayout(title_row)

        # ── 分割线 ──
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #45475A;")
        root.addWidget(line)

        # ── 更新说明 ──
        if body:
            notes_lbl = QLabel(tr("update.notes", default="更新说明"))
            notes_lbl.setStyleSheet("font-weight: bold; color: #CDD6F4;")
            root.addWidget(notes_lbl)
            notes_edit = QTextEdit()
            notes_edit.setReadOnly(True)
            notes_edit.setPlainText(body)
            notes_edit.setMaximumHeight(140)
            notes_edit.setStyleSheet("background: #181825; border: 1px solid #45475A; border-radius: 6px;")
            root.addWidget(notes_edit)

        # ── 自动下载区（初始隐藏） ──
        self._dl_widget = QWidget()
        dl_layout = QVBoxLayout(self._dl_widget)
        dl_layout.setContentsMargins(0, 0, 0, 0)
        dl_layout.setSpacing(8)

        src_row = QHBoxLayout()
        src_lbl = QLabel(tr("update.dl_source", default="选择下载源："))
        src_row.addWidget(src_lbl)
        self._src_combo = QComboBox()
        self._src_combo.setMinimumWidth(280)
        tag  = self._result.get("latest_tag", "")
        dl_url = self._result.get("download_url", "")
        for label, _ in _build_sources(dl_url, tag):
            self._src_combo.addItem(label)
        src_row.addWidget(self._src_combo)
        src_row.addStretch()
        dl_layout.addLayout(src_row)

        self._prog_bar = QProgressBar()
        self._prog_bar.setRange(0, 100)
        self._prog_bar.setValue(0)
        self._prog_bar.setTextVisible(True)
        self._prog_bar.setFormat("%p%  (%v / %m KB)")
        self._prog_bar.setFixedHeight(22)
        dl_layout.addWidget(self._prog_bar)

        self._status_lbl = QLabel()
        self._status_lbl.setStyleSheet("color: #6C7086; font-size: 11px;")
        dl_layout.addWidget(self._status_lbl)

        self._dl_widget.setVisible(False)
        root.addWidget(self._dl_widget)

        # ── 按钮区 ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        self._ignore_btn = QPushButton(tr("update.btn_ignore", default="忽略此版本"))
        self._ignore_btn.setObjectName("btn_flat")
        self._ignore_btn.clicked.connect(self._on_ignore)
        btn_row.addWidget(self._ignore_btn)

        self._later_btn = QPushButton(tr("update.btn_later", default="稍后再说"))
        self._later_btn.setObjectName("btn_flat")
        self._later_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._later_btn)

        self._manual_btn = QPushButton(tr("update.btn_manual", default="前往下载页"))
        self._manual_btn.setObjectName("btn_secondary")
        self._manual_btn.clicked.connect(self._on_manual)
        btn_row.addWidget(self._manual_btn)

        self._auto_btn = QPushButton(tr("update.btn_auto", default="自动下载安装"))
        self._auto_btn.setObjectName("btn_primary")
        self._auto_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._auto_btn.clicked.connect(self._on_auto_download)
        btn_row.addWidget(self._auto_btn)

        self._cancel_dl_btn = QPushButton(tr("update.dl_cancel", default="取消"))
        self._cancel_dl_btn.setObjectName("btn_flat")
        self._cancel_dl_btn.clicked.connect(self._on_cancel_dl)
        self._cancel_dl_btn.setVisible(False)
        btn_row.addWidget(self._cancel_dl_btn)

        root.addLayout(btn_row)

    def _connect_signals(self):
        self._progress_sig.connect(self._on_progress)
        self._done_sig.connect(self._on_done)
        self._error_sig.connect(self._on_error)
        self._source_switch_sig.connect(self._on_source_switch)

    # ─── 按钮事件 ─────────────────────────────────────────
    def _on_manual(self):
        url = self._result.get("html_url", "")
        if url:
            QDesktopServices.openUrl(QUrl(url))
        self.accept()

    def _on_ignore(self):
        """忽略此版本：将版本号写入配置，下次不再提示"""
        tag = self._result.get("latest_tag", "")
        try:
            from ..engine.models import AppConfig
            import json, os as _os
            cfg_path = _os.path.join(
                _os.environ.get("LOCALAPPDATA", _os.path.expanduser("~")),
                "XinyuCraft", "AutoFlow", "app_config.json"
            )
            if _os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = {}
            data["ignored_update_version"] = tag
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        self.reject()

    def _on_auto_download(self):
        """展开下载区，开始下载（支持无进度超时自动切换源）"""
        if self._worker and self._worker.is_alive():
            return  # 已在下载中

        tag = self._result.get("latest_tag", "")
        dl_url = self._result.get("download_url", "")

        if not tag:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, tr("update.dl_error", default="下载失败"),
                                "未获取到版本信息，无法自动下载，请前往下载页手动下载。")
            return

        all_sources = _build_sources(dl_url, tag)
        # 从用户选择的源开始，之后按顺序尝试其余源
        start_idx = self._src_combo.currentIndex()
        start_idx = min(start_idx, len(all_sources) - 1)
        ordered_sources = all_sources[start_idx:] + all_sources[:start_idx]

        # 从设置读取超时阈值（默认 6 秒）
        stall_timeout = 6.0
        try:
            import json as _json, os as _os
            _cfg = _os.path.join(
                _os.environ.get("LOCALAPPDATA", _os.path.expanduser("~")),
                "XinyuCraft", "AutoFlow", "app_config.json"
            )
            if _os.path.exists(_cfg):
                with open(_cfg, "r", encoding="utf-8") as _f:
                    _d = _json.load(_f)
                stall_timeout = float(_d.get("update_dl_stall_timeout", 6))
        except Exception:
            pass

        # 展示下载区
        self._dl_widget.setVisible(True)
        self._auto_btn.setVisible(False)
        self._manual_btn.setVisible(False)
        self._cancel_dl_btn.setVisible(True)
        self._status_lbl.setText("准备下载...")
        self._prog_bar.setValue(0)
        self.adjustSize()

        # 目标文件
        filename = f"AutoFlow_{tag}_Setup.exe"
        tmp_dir = tempfile.gettempdir()
        self._dest_path = os.path.join(tmp_dir, filename)

        self._worker = _DownloadWorker(
            ordered_sources, self._dest_path,
            on_progress=lambda d, t: self._progress_sig.emit(d, t),
            on_done=lambda p: self._done_sig.emit(p),
            on_error=lambda e: self._error_sig.emit(e),
            on_source_switch=lambda lbl: self._source_switch_sig.emit(lbl),
            stall_timeout=stall_timeout,
        )
        self._worker.start()
        self._status_lbl.setText(f"正在从 {ordered_sources[0][0]} 下载...")

    def _on_cancel_dl(self):
        if self._worker:
            self._worker.cancel()
        self._dl_widget.setVisible(False)
        self._auto_btn.setVisible(True)
        self._manual_btn.setVisible(True)
        self._cancel_dl_btn.setVisible(False)
        self._status_lbl.setText("")
        self._prog_bar.setValue(0)

    # ─── 跨线程信号槽 ───────────────────────────────────────
    def _on_source_switch(self, label: str):
        """切换下载源时更新状态文字"""
        self._status_lbl.setText(f"⚠ 正在切换到备用源：{label}...")
        self._prog_bar.setValue(0)
        self._prog_bar.setRange(0, 100)

    def _on_progress(self, downloaded: int, total: int):
        if total > 0:
            pct = int(downloaded * 100 / total)
            self._prog_bar.setRange(0, 100)
            self._prog_bar.setValue(pct)
            self._prog_bar.setFormat(
                f"%p%  ({downloaded // 1024} KB / {total // 1024} KB)"
            )
        else:
            # Content-Length 未知
            self._prog_bar.setRange(0, 0)   # 进度条变为 indeterminate
            self._status_lbl.setText(f"已下载 {downloaded // 1024} KB...")

    def _on_done(self, dest: str):
        self._prog_bar.setRange(0, 100)
        self._prog_bar.setValue(100)
        msg = tr("update.dl_done", default="下载完成，即将打开安装包...")
        self._status_lbl.setText(msg)
        self._cancel_dl_btn.setEnabled(False)

        # 延迟 1 秒后打开安装包，给用户看到 100% 的时间
        QTimer.singleShot(1000, lambda: self._launch_installer(dest))

    def _on_error(self, msg: str):
        self._prog_bar.setRange(0, 100)
        self._prog_bar.setValue(0)
        self._status_lbl.setText(f"❌ 下载失败: {msg}")
        self._cancel_dl_btn.setVisible(False)
        self._auto_btn.setVisible(True)
        self._manual_btn.setVisible(True)
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.warning(
            self,
            tr("update.dl_error", default="下载失败"),
            f"下载失败：{msg}\n\n请尝试切换下载源，或前往下载页手动下载。"
        )

    def _launch_installer(self, dest: str):
        """启动安装包，然后关闭 AutoFlow"""
        try:
            os.startfile(dest)
        except Exception:
            try:
                import subprocess
                subprocess.Popen([dest])
            except Exception as e:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "启动安装包失败",
                                    f"请手动打开安装包：\n{dest}\n\n错误：{e}")
                self.accept()
                return

        self._status_lbl.setText(tr("update.installing",
                                    default="正在启动安装程序，安装完成后请手动重启 AutoFlow..."))

        # 延迟 2 秒后退出当前程序
        QTimer.singleShot(2000, self._quit_app)

    def _quit_app(self):
        self.accept()
        QApplication.quit()

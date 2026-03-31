"""
AutoFlow 主题管理器
负责：
- 自定义背景（静图 PNG/JPG、动图 GIF）
- 自定义字体（TTF/OTF，动态注册到 QFontDatabase）
- 自定义调色板颜色覆盖
- 整合包（.aftheme ZIP）的导入与导出
- 主题市场的索引获取与下载

整合包格式（.aftheme = ZIP）：
  theme.json          ← 元信息 + palette_override
  background.*        ← 可选背景图/GIF
  font.*              ← 可选字体文件（TTF/OTF/WOFF）
"""
from __future__ import annotations

import json
import os
import shutil
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# 主题包本地存储目录
_THEME_PACK_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "XinyuCraft", "AutoFlow", "ThemePacks"
)

# 主题市场索引（从 GitHub / jsDelivr / Gitee 三级备用拉取）
_GITHUB_RAW = "https://raw.githubusercontent.com/XinyuCraft-XYHC/autoflow-themes/main/index.json"
_JSDELIVR   = "https://cdn.jsdelivr.net/gh/XinyuCraft-XYHC/autoflow-themes@main/index.json"
_GITEE_RAW  = "https://gitee.com/XinyuCraft-XYHC/autoflow-themes/raw/main/index.json"

_FALLBACK_URLS = [_GITHUB_RAW, _JSDELIVR, _GITEE_RAW]


# ─────────────────── 整合包管理 ───────────────────

class ThemePackInfo:
    """一个已安装的整合包元数据"""
    def __init__(self, pack_dir: str, meta: dict):
        self.pack_dir     = pack_dir
        self.id           = meta.get("id", os.path.basename(pack_dir))
        self.name         = meta.get("name", self.id)
        self.author       = meta.get("author", "")
        self.version      = meta.get("version", "1.0.0")
        self.description  = meta.get("description", "")
        self.base_theme   = meta.get("base_theme", "dark")
        self.palette_override: Dict[str, str] = meta.get("palette_override", {})
        self.bg_file: Optional[str] = None  # 绝对路径
        self.font_file: Optional[str] = None  # 绝对路径
        self.font_family: str = meta.get("font_family", "")
        self.font_size: int = meta.get("font_size", 0)
        self.bg_opacity: float = meta.get("bg_opacity", 0.15)
        self.bg_mode: str = meta.get("bg_mode", "fill")

        # 找背景文件
        for ext in ("gif", "png", "jpg", "jpeg", "webp"):
            p = os.path.join(pack_dir, f"background.{ext}")
            if os.path.exists(p):
                self.bg_file = p
                break

        # 找字体文件
        for ext in ("ttf", "otf", "woff", "woff2"):
            p = os.path.join(pack_dir, f"font.{ext}")
            if os.path.exists(p):
                self.font_file = p
                break


def list_installed_packs() -> List[ThemePackInfo]:
    """列出所有已安装的整合包"""
    result = []
    if not os.path.isdir(_THEME_PACK_DIR):
        return result
    for name in sorted(os.listdir(_THEME_PACK_DIR)):
        pack_dir = os.path.join(_THEME_PACK_DIR, name)
        meta_path = os.path.join(pack_dir, "theme.json")
        if not os.path.isdir(pack_dir) or not os.path.exists(meta_path):
            continue
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            result.append(ThemePackInfo(pack_dir, meta))
        except Exception:
            pass
    return result


def get_installed_pack(pack_id: str) -> Optional[ThemePackInfo]:
    """根据 ID 获取已安装的整合包"""
    for p in list_installed_packs():
        if p.id == pack_id:
            return p
    return None


def import_theme_pack(aftheme_path: str) -> ThemePackInfo:
    """
    导入一个 .aftheme 整合包文件到本地存储目录。
    返回解析后的 ThemePackInfo。
    如有同 ID 的包则覆盖。
    """
    os.makedirs(_THEME_PACK_DIR, exist_ok=True)
    if not zipfile.is_zipfile(aftheme_path):
        raise ValueError(f"不是有效的整合包文件：{aftheme_path}")

    with zipfile.ZipFile(aftheme_path, "r") as zf:
        names = zf.namelist()
        if "theme.json" not in names:
            raise ValueError("整合包缺少 theme.json")
        meta = json.loads(zf.read("theme.json").decode("utf-8"))
        pack_id = meta.get("id") or ""
        if not pack_id:
            raise ValueError("整合包 theme.json 缺少 id 字段")

        # 清理旧目录
        dest = os.path.join(_THEME_PACK_DIR, pack_id)
        if os.path.exists(dest):
            shutil.rmtree(dest)
        os.makedirs(dest, exist_ok=True)

        # 解压（只允许根目录文件，防路径穿越）
        for member in names:
            if "/" in member or "\\" in member:
                continue  # 忽略子目录，只解压根目录文件
            zf.extract(member, dest)

    pack_dir = os.path.join(_THEME_PACK_DIR, pack_id)
    return ThemePackInfo(pack_dir, meta)


def export_theme_pack(
    pack_id: str,
    name: str,
    author: str,
    description: str,
    base_theme: str,
    palette_override: dict,
    bg_path: Optional[str],
    font_path: Optional[str],
    font_family: str,
    font_size: int,
    bg_opacity: float,
    bg_mode: str,
    out_path: str,
) -> str:
    """
    将当前主题配置打包为 .aftheme 整合包。
    返回生成的文件路径。
    """
    meta = {
        "id":               pack_id,
        "name":             name,
        "author":           author,
        "description":      description,
        "version":          "1.0.0",
        "base_theme":       base_theme,
        "palette_override": palette_override,
        "font_family":      font_family,
        "font_size":        font_size,
        "bg_opacity":       bg_opacity,
        "bg_mode":          bg_mode,
    }

    if not out_path.endswith(".aftheme"):
        out_path += ".aftheme"

    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("theme.json", json.dumps(meta, ensure_ascii=False, indent=2))
        if bg_path and os.path.exists(bg_path):
            ext = os.path.splitext(bg_path)[1].lower()
            zf.write(bg_path, f"background{ext}")
        if font_path and os.path.exists(font_path):
            ext = os.path.splitext(font_path)[1].lower()
            zf.write(font_path, f"font{ext}")

    return out_path


def remove_theme_pack(pack_id: str) -> bool:
    """删除一个已安装的整合包"""
    dest = os.path.join(_THEME_PACK_DIR, pack_id)
    if os.path.exists(dest):
        shutil.rmtree(dest)
        return True
    return False


# ─────────────────── 字体注册 ───────────────────

_registered_font_ids: Dict[str, int] = {}  # font_path → QFontDatabase id


def register_font(font_path: str) -> str:
    """
    将字体文件注册到 Qt 字体数据库。
    返回字体家族名称（family name）。
    """
    from PyQt6.QtGui import QFontDatabase
    if font_path in _registered_font_ids:
        fid = _registered_font_ids[font_path]
    else:
        fid = QFontDatabase.addApplicationFont(font_path)
        _registered_font_ids[font_path] = fid

    if fid < 0:
        raise RuntimeError(f"字体注册失败：{font_path}")
    families = QFontDatabase.applicationFontFamilies(fid)
    return families[0] if families else ""


# ─────────────────── 背景图控件 ───────────────────

class BackgroundWidget:
    """
    给任意 QWidget 添加背景图/GIF 效果。
    使用时：BackgroundWidget.install(widget, config)
    主题切换时：BackgroundWidget.uninstall(widget)
    """

    @staticmethod
    def install(widget, config) -> None:
        """
        在 widget 上安装背景（通过 paintEvent 重写）。
        config: AppConfig
        """
        from PyQt6.QtCore import Qt, QTimer
        from PyQt6.QtGui import QPainter, QPixmap, QColor, QMovie
        from PyQt6.QtWidgets import QLabel

        bg_path = config.theme_bg_image
        if not bg_path or not os.path.exists(bg_path):
            BackgroundWidget.uninstall(widget)
            return

        opacity = max(0.0, min(1.0, config.theme_bg_opacity))
        mode    = config.theme_bg_mode  # fill/contain/center/tile

        # ── 创建背景 QLabel（置于底层）──
        old = getattr(widget, "_bg_label", None)
        if old is not None:
            old.deleteLater()

        bg_label = QLabel(widget)
        bg_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        bg_label.setGeometry(widget.rect())
        bg_label.lower()

        is_gif = bg_path.lower().endswith(".gif")
        if is_gif:
            movie = QMovie(bg_path)
            movie.start()
            widget._bg_movie = movie

            def _update_gif_frame():
                pm = movie.currentPixmap()
                if pm.isNull():
                    return
                scaled = _scale_pixmap(pm, bg_label.size(), mode)
                # 应用透明度
                final = _apply_opacity(scaled, opacity)
                bg_label.setPixmap(final)

            movie.frameChanged.connect(lambda _: _update_gif_frame())
            _update_gif_frame()
        else:
            pm = QPixmap(bg_path)
            if not pm.isNull():
                widget._bg_movie = None
                widget._bg_pixmap = pm
                scaled = _scale_pixmap(pm, bg_label.size(), mode)
                final = _apply_opacity(scaled, opacity)
                bg_label.setPixmap(final)

        widget._bg_label = bg_label
        widget._bg_mode  = mode
        widget._bg_opacity = opacity

        # 监听 resizeEvent，动态缩放背景（用 eventFilter 替代猴子补丁，更可靠）
        _install_resize_hook(widget)
        bg_label.show()
        bg_label.lower()  # 再次确保在底层

        # 延迟刷新一次，解决首次显示时 rect() 为空的问题
        from PyQt6.QtCore import QTimer as _QT
        _QT.singleShot(100, lambda: _refresh_bg_label(widget))

    @staticmethod
    def uninstall(widget) -> None:
        """移除背景"""
        old = getattr(widget, "_bg_label", None)
        if old is not None:
            old.deleteLater()
            widget._bg_label = None
        movie = getattr(widget, "_bg_movie", None)
        if movie is not None:
            movie.stop()
            widget._bg_movie = None


def _scale_pixmap(pm, size, mode: str):
    """按模式缩放 pixmap 到 size"""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QPixmap, QPainter
    if size.width() <= 0 or size.height() <= 0:
        return pm
    if mode == "fill":
        return pm.scaled(size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                         Qt.TransformationMode.SmoothTransformation)
    elif mode == "contain":
        return pm.scaled(size, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    elif mode == "tile":
        # 平铺：创建目标 pixmap 并重复绘制
        result = QPixmap(size)
        result.fill(Qt.GlobalColor.transparent)
        p = QPainter(result)
        for y in range(0, size.height(), pm.height()):
            for x in range(0, size.width(), pm.width()):
                p.drawPixmap(x, y, pm)
        p.end()
        return result
    else:  # center
        result = QPixmap(size)
        result.fill(Qt.GlobalColor.transparent)
        p = QPainter(result)
        x = (size.width()  - pm.width())  // 2
        y = (size.height() - pm.height()) // 2
        p.drawPixmap(x, y, pm)
        p.end()
        return result


def _apply_opacity(pm, opacity: float):
    """将 pixmap 叠加透明度（返回新 pixmap）"""
    from PyQt6.QtGui import QPixmap, QPainter, QColor
    from PyQt6.QtCore import Qt
    result = QPixmap(pm.size())
    result.fill(Qt.GlobalColor.transparent)
    p = QPainter(result)
    p.setOpacity(opacity)
    p.drawPixmap(0, 0, pm)
    p.end()
    return result


def _refresh_bg_label(widget) -> None:
    """立即刷新背景 label 的尺寸和 pixmap（用于延迟初始化）"""
    bg_label = getattr(widget, "_bg_label", None)
    if bg_label is None or not widget.rect().isValid():
        return
    bg_label.setGeometry(widget.rect())
    bg_label.lower()
    pm_src = getattr(widget, "_bg_pixmap", None)
    if pm_src is not None and not pm_src.isNull():
        mode    = getattr(widget, "_bg_mode", "fill")
        opacity = getattr(widget, "_bg_opacity", 0.15)
        if bg_label.size().width() > 0 and bg_label.size().height() > 0:
            scaled = _scale_pixmap(pm_src, bg_label.size(), mode)
            final  = _apply_opacity(scaled, opacity)
            bg_label.setPixmap(final)


def _install_resize_hook(widget) -> None:
    """给 widget 安装 resizeEvent hook，以便背景随窗口尺寸变化"""
    orig_resize = widget.__class__.resizeEvent if hasattr(widget.__class__, 'resizeEvent') else None
    _hooked_attr = "_bg_resize_hooked"
    if getattr(widget, _hooked_attr, False):
        return  # 已安装过

    def _new_resize(self_w, event):
        if orig_resize:
            orig_resize(self_w, event)
        bg_label = getattr(self_w, "_bg_label", None)
        if bg_label is None:
            return
        bg_label.setGeometry(self_w.rect())
        bg_label.lower()
        pm_src = getattr(self_w, "_bg_pixmap", None)
        movie  = getattr(self_w, "_bg_movie", None)
        if pm_src is not None and not pm_src.isNull():
            mode    = getattr(self_w, "_bg_mode", "fill")
            opacity = getattr(self_w, "_bg_opacity", 0.15)
            scaled  = _scale_pixmap(pm_src, bg_label.size(), mode)
            final   = _apply_opacity(scaled, opacity)
            bg_label.setPixmap(final)
        elif movie is not None:
            # GIF 动图在 frameChanged 里处理
            pass

    # 为该实例（不是类）创建 resizeEvent 补丁
    import types
    widget.resizeEvent = types.MethodType(_new_resize, widget)
    setattr(widget, _hooked_attr, True)


# ─────────────────── 主题市场 ───────────────────

def fetch_theme_market_index(timeout: int = 8) -> Optional[list]:
    """
    获取主题市场索引。
    返回主题包列表（字典列表），失败返回 None。
    """
    import urllib.request
    for url in _FALLBACK_URLS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AutoFlow/4"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, list):
                    return data
        except Exception:
            continue
    return None


def download_theme_pack(
    pack_info: dict,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    timeout: int = 30,
) -> ThemePackInfo:
    """
    从市场下载并安装一个主题包。
    pack_info 是 fetch_theme_market_index 返回列表中的一项：
    {
      "id":          "my_theme",
      "name":        "我的主题",
      "download_url": "https://...",
      ...
    }
    返回安装后的 ThemePackInfo。
    自动尝试 GitHub raw → jsDelivr CDN 三级备用源。
    """
    import urllib.request, tempfile
    primary_url = pack_info.get("download_url") or pack_info.get("url", "")
    if not primary_url:
        raise ValueError("主题包没有 download_url")

    # 构建备用 URL 列表（GitHub raw → jsDelivr CDN）
    fallback_urls = [primary_url]
    if "raw.githubusercontent.com" in primary_url:
        try:
            parts = primary_url.split("raw.githubusercontent.com/", 1)[1].split("/", 3)
            owner, repo, branch, path = parts[0], parts[1], parts[2], parts[3]
            cdn_url = f"https://cdn.jsdelivr.net/gh/{owner}/{repo}@{branch}/{path}"
            fallback_urls.append(cdn_url)
        except Exception:
            pass

    # 下载到临时文件
    with tempfile.NamedTemporaryFile(suffix=".aftheme", delete=False) as tf:
        tmp_path = tf.name

    try:
        last_error = None
        for url in fallback_urls:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "AutoFlow/4"})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    total = int(resp.headers.get("Content-Length", 0))
                    downloaded = 0
                    with open(tmp_path, "wb") as f:
                        while True:
                            chunk = resp.read(65536)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)
                            if progress_cb and total > 0:
                                progress_cb(downloaded, total)
                return import_theme_pack(tmp_path)
            except Exception as e:
                last_error = e
                continue
        raise RuntimeError(f"主题包下载失败（已尝试所有备用源）：{last_error}")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

# src/updater.py — AutoFlow 自动更新模块
# 使用 GitHub Releases API 检测和下载新版本，无需第三方依赖（仅标准库）

import sys
import os
import threading
import urllib.request
import urllib.error
import json
import re
import tempfile
import shutil
from typing import Optional, Callable

# ─── GitHub 仓库配置 ───
GITHUB_OWNER = "XinyuCraft-XYHC"
GITHUB_REPO  = "autoflow-windows"
GITHUB_REPO_URL    = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases"
GITHUB_LATEST_API   = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
GITEE_REPO_URL      = f"https://gitee.com/{GITHUB_OWNER}/{GITHUB_REPO}"
GITEE_RELEASES_URL  = f"https://gitee.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases"
# Gitee releases API（作为 GitHub API 限流时的备用）
GITEE_LATEST_API    = f"https://gitee.com/api/v5/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"

# 插件相关链接
PLUGIN_DEV_DOCS_URL  = f"{GITHUB_REPO_URL}/blob/master/docs/plugin-dev-guide.md"
PLUGIN_REPO_URL      = f"{GITHUB_REPO_URL}/tree/master/plugins"
ISSUES_URL           = f"{GITHUB_REPO_URL}/issues"
WIKI_URL             = f"{GITHUB_REPO_URL}/wiki"

# ─── 社区语言包市场 ───
LANG_MARKET_OWNER    = "XinyuCraft-XYHC"
LANG_MARKET_REPO     = "autoflow-languages"
LANG_MARKET_URL      = f"https://github.com/{LANG_MARKET_OWNER}/{LANG_MARKET_REPO}"
# index.json 三级备用源：GitHub raw → jsDelivr CDN → Gitee raw（均为 master 分支）
LANG_MARKET_INDEX    = (
    f"https://raw.githubusercontent.com/{LANG_MARKET_OWNER}/{LANG_MARKET_REPO}"
    "/master/index.json"
)
LANG_MARKET_INDEX_CDN = (
    f"https://cdn.jsdelivr.net/gh/{LANG_MARKET_OWNER}/{LANG_MARKET_REPO}@master/index.json"
)
# Gitee 镜像（国内最稳定）用户名 XinyuCraft-XYHC_admin
LANG_MARKET_INDEX_GITEE = (
    "https://gitee.com/XinyuCraft-XYHC_admin/autoflow-languages"
    "/raw/master/index.json"
)

# ─── 社区插件市场 ───
PLUGIN_MARKET_OWNER  = "XinyuCraft-XYHC"
PLUGIN_MARKET_REPO   = "autoflow-plugins"
PLUGIN_MARKET_URL    = f"https://github.com/{PLUGIN_MARKET_OWNER}/{PLUGIN_MARKET_REPO}"
PLUGIN_MARKET_INDEX  = (
    f"https://raw.githubusercontent.com/{PLUGIN_MARKET_OWNER}/{PLUGIN_MARKET_REPO}"
    "/master/index.json"
)
PLUGIN_MARKET_INDEX_CDN = (
    f"https://cdn.jsdelivr.net/gh/{PLUGIN_MARKET_OWNER}/{PLUGIN_MARKET_REPO}@master/index.json"
)
# Gitee 镜像（国内最稳定）
PLUGIN_MARKET_INDEX_GITEE = (
    "https://gitee.com/XinyuCraft-XYHC_admin/autoflow-plugins"
    "/raw/master/index.json"
)
# 发布插件的 Issue 模板（引导用户提交 PR）
PLUGIN_SUBMIT_URL    = (
    f"https://github.com/{PLUGIN_MARKET_OWNER}/{PLUGIN_MARKET_REPO}"
    "/issues/new?template=submit_plugin.md"
)


def _parse_version(ver_str: str) -> tuple:
    """将版本字符串（如 v4.3.1 / 4.3.1）解析为可比较的整数元组"""
    ver_str = ver_str.lstrip("vV").strip()
    parts = re.findall(r"\d+", ver_str)
    return tuple(int(p) for p in parts[:3]) if parts else (0, 0, 0)


def _fetch_latest_release(timeout: int = 8) -> Optional[dict]:
    """
    从 GitHub API 获取最新 Release 信息，失败时 fallback 到 Gitee API。
    返回字典含：tag_name, name, body, published_at, assets, html_url
    若所有请求均失败返回 None。
    """
    # 优先 GitHub API
    try:
        req = urllib.request.Request(
            GITHUB_LATEST_API,
            headers={
                "User-Agent": "AutoFlow-Updater/1.0",
                "Accept": "application/vnd.github.v3+json",
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        # GitHub API 限流时返回 message 字段而非 tag_name
        if "tag_name" in data:
            return data
    except Exception:
        pass

    # Fallback：Gitee API
    try:
        req = urllib.request.Request(
            GITEE_LATEST_API,
            headers={"User-Agent": "AutoFlow-Updater/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        # Gitee release 格式与 GitHub 基本一致，tag_name/name/body/html_url 字段均有
        if "tag_name" in data:
            # Gitee 的 assets 格式略有不同，assets[].browser_download_url 可能没有
            # 把 html_url 指向 Gitee releases 页面
            if not data.get("html_url"):
                data["html_url"] = GITEE_RELEASES_URL
            return data
    except Exception:
        pass

    return None


def check_update(current_version: str, callback: Callable[[dict], None],
                 timeout: int = 8) -> None:
    """
    异步检查更新，在后台线程执行，完成后在主线程回调。

    callback 参数：
    {
        "has_update": bool,          # 是否有新版本
        "latest_tag": str,           # 最新版本号，如 "v4.4.0"
        "latest_name": str,          # Release 名称
        "body": str,                 # Release 更新说明
        "html_url": str,             # Release 页面链接
        "download_url": str | None,  # exe 直链（若 asset 存在）
        "error": str | None,         # 错误信息（网络失败等）
    }
    """
    def _worker():
        data = _fetch_latest_release(timeout=timeout)
        if data is None:
            result = {
                "has_update": False,
                "latest_tag": "",
                "latest_name": "",
                "body": "",
                "html_url": GITHUB_RELEASES_URL,
                "download_url": None,
                "error": "无法连接到 GitHub，请检查网络连接",
            }
        else:
            latest_tag  = data.get("tag_name", "")
            latest_name = data.get("name", "")
            body        = data.get("body", "")
            html_url    = data.get("html_url", GITHUB_RELEASES_URL)

            # 找 exe 资源下载链接
            download_url = None
            for asset in data.get("assets", []):
                name = asset.get("name", "")
                if name.lower().endswith(".exe"):
                    download_url = asset.get("browser_download_url")
                    break

            current_tuple = _parse_version(current_version)
            latest_tuple  = _parse_version(latest_tag)
            has_update = latest_tuple > current_tuple

            result = {
                "has_update": has_update,
                "latest_tag": latest_tag,
                "latest_name": latest_name,
                "body": body,
                "html_url": html_url,
                "download_url": download_url,
                "error": None,
            }
        # 回调需在 Qt 主线程执行，调用方自行决定（可通过信号/槽桥接）
        callback(result)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


# ─── 远程公告 ───

# 公告数据源：优先 GitHub raw，失败时 fallback 到 Gitee raw
ANNOUNCEMENTS_URL = (
    f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}"
    "/master/docs/announcements.json"
)
ANNOUNCEMENTS_URL_GITEE = (
    f"https://gitee.com/{GITHUB_OWNER}/{GITHUB_REPO}"
    "/raw/master/docs/announcements.json"
)


def _fetch_url_json(url: str, timeout: int) -> list | None:
    """尝试从 url 拉取 JSON 列表，失败返回 None"""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "AutoFlow-Updater/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        return data if isinstance(data, list) else None
    except Exception:
        return None


def fetch_announcements(callback: Callable[[list], None],
                        timeout: int = 8) -> None:
    """
    异步拉取远程公告列表，完成后回调。
    优先访问 GitHub raw，失败时自动 fallback 到 Gitee raw。

    每条公告格式：
    {
        "id":      str,   # 唯一 ID（用于去重，如 "ann_2026_04_01"）
        "title":   str,   # 标题
        "body":    str,   # 正文（纯文本，可含换行）
        "level":   str,   # "info" | "warning" | "important"（控制样式）
        "date":    str,   # 发布日期（仅展示，如 "2026-04-01"）
        "url":     str,   # 可选，点击「查看详情」跳转的链接（可空）
        "pinned":  bool,  # true = 永远显示，false = 已读后不再弹出
    }

    callback 接收一个公告列表（所有源均失败时为空列表）。
    """
    def _worker():
        # 优先 GitHub
        announcements = _fetch_url_json(ANNOUNCEMENTS_URL, timeout)
        # 失败时 fallback 到 Gitee
        if announcements is None:
            announcements = _fetch_url_json(ANNOUNCEMENTS_URL_GITEE, timeout)
        callback(announcements or [])

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


def fetch_language_market(callback: Callable[[list, Optional[str]], None],
                          timeout: int = 8) -> None:
    """
    异步拉取语言包市场索引，完成后回调 callback(items, error_msg)。
    items 为语言包列表（失败时为 []），error_msg 为错误信息或 None。
    优先 GitHub raw，失败时 fallback 到 jsDelivr CDN（国内可访问）。
    """
    def _worker():
        data = _fetch_url_json(LANG_MARKET_INDEX, timeout)
        if data is None:
            data = _fetch_url_json(LANG_MARKET_INDEX_CDN, timeout)
        if data is None:
            data = _fetch_url_json(LANG_MARKET_INDEX_GITEE, timeout)
        if data is None:
            callback([], "无法连接到语言包市场，请检查网络连接\n（GitHub raw + jsDelivr CDN + Gitee 均不可访问）")
        else:
            callback(data if isinstance(data, list) else [], None)

    threading.Thread(target=_worker, daemon=True).start()


def fetch_plugin_market(callback: Callable[[list, Optional[str]], None],
                        timeout: int = 8) -> None:
    """
    异步拉取插件市场索引，完成后回调 callback(items, error_msg)。
    items 为插件列表（失败时为 []），error_msg 为错误信息或 None。
    优先 GitHub raw，失败时 fallback 到 jsDelivr CDN（国内可访问）。
    """
    def _worker():
        data = _fetch_url_json(PLUGIN_MARKET_INDEX, timeout)
        if data is None:
            data = _fetch_url_json(PLUGIN_MARKET_INDEX_CDN, timeout)
        if data is None:
            data = _fetch_url_json(PLUGIN_MARKET_INDEX_GITEE, timeout)
        if data is None:
            callback([], "无法连接到插件市场，请检查网络连接\n（GitHub raw + jsDelivr CDN + Gitee 均不可访问）")
        else:
            callback(data if isinstance(data, list) else [], None)

    threading.Thread(target=_worker, daemon=True).start()


def download_plugin(download_url: str, plugin_dir_in_zip: str,
                    dest_plugins_dir: str,
                    on_progress: Optional[Callable[[int, int], None]] = None,
                    on_done: Optional[Callable[[str], None]] = None,
                    on_error: Optional[Callable[[str], None]] = None) -> None:
    """
    异步下载插件 zip 包，解压指定子目录到 dest_plugins_dir/<plugin_id>/。

    plugin_dir_in_zip: zip 内插件目录路径，如 "autoflow-plugins-main/plugins/http_request"
    dest_plugins_dir:  AutoFlow 插件目录（如 %LOCALAPPDATA%/XinyuCraft/AutoFlow/plugins）
    """
    import zipfile

    def _worker():
        try:
            # 下载 zip
            import tempfile
            req = urllib.request.Request(
                download_url, headers={"User-Agent": "AutoFlow-PluginMarket/1.0"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                chunk_size = 65536
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    tmp.write(chunk)
                    downloaded += len(chunk)
                    if on_progress:
                        on_progress(downloaded, total)
                tmp.flush()
                tmp_path = tmp.name
                tmp.close()

            # 解压指定子目录
            plugin_name = os.path.basename(plugin_dir_in_zip.rstrip("/"))
            dest_path = os.path.join(dest_plugins_dir, plugin_name)

            with zipfile.ZipFile(tmp_path, "r") as zf:
                prefix = plugin_dir_in_zip.rstrip("/") + "/"
                members = [m for m in zf.namelist() if m.startswith(prefix)]
                if not members:
                    raise ValueError(f"zip 内找不到目录: {plugin_dir_in_zip}")

                # 如果目标已存在，先删除
                if os.path.exists(dest_path):
                    shutil.rmtree(dest_path)
                os.makedirs(dest_path, exist_ok=True)

                for member in members:
                    # 计算相对路径
                    rel = member[len(prefix):]
                    if not rel:
                        continue
                    target = os.path.join(dest_path, rel.replace("/", os.sep))
                    if member.endswith("/"):
                        os.makedirs(target, exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(target), exist_ok=True)
                        with zf.open(member) as src, open(target, "wb") as dst:
                            dst.write(src.read())

            os.unlink(tmp_path)
            if on_done:
                on_done(dest_path)

        except Exception as e:
            if on_error:
                on_error(str(e))

    threading.Thread(target=_worker, daemon=True).start()


def download_language(download_url: str, lang_code: str,
                      dest_lang_dir: str,
                      on_progress: Optional[Callable[[int, int], None]] = None,
                      on_done: Optional[Callable[[str], None]] = None,
                      on_error: Optional[Callable[[str], None]] = None) -> None:
    """
    异步下载单个语言包 JSON 文件到 dest_lang_dir/<lang_code>.json。
    """
    def _worker():
        try:
            os.makedirs(dest_lang_dir, exist_ok=True)
            dest_path = os.path.join(dest_lang_dir, f"{lang_code}.json")
            req = urllib.request.Request(
                download_url, headers={"User-Agent": "AutoFlow-LangMarket/1.0"}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                chunk_size = 16384
                with open(dest_path, "wb") as f:
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if on_progress:
                            on_progress(downloaded, total)
            if on_done:
                on_done(dest_path)
        except Exception as e:
            if on_error:
                on_error(str(e))

    threading.Thread(target=_worker, daemon=True).start()


def download_update(url: str, dest_dir: str,
                    on_progress: Optional[Callable[[int, int], None]] = None,
                    on_done: Optional[Callable[[str], None]] = None,
                    on_error: Optional[Callable[[str], None]] = None) -> None:
    """
    异步下载新版本 exe 到 dest_dir。

    on_progress(downloaded_bytes, total_bytes)
    on_done(saved_path)
    on_error(err_msg)
    """
    def _worker():
        try:
            filename = url.split("/")[-1] or "AutoFlow_update.exe"
            dest_path = os.path.join(dest_dir, filename)

            req = urllib.request.Request(
                url, headers={"User-Agent": "AutoFlow-Updater/1.0"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                chunk_size = 65536  # 64 KB
                with open(dest_path, "wb") as f:
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if on_progress:
                            on_progress(downloaded, total)

            if on_done:
                on_done(dest_path)
        except Exception as e:
            if on_error:
                on_error(str(e))

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

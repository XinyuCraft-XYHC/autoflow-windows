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

# 插件相关链接
PLUGIN_DEV_DOCS_URL  = f"{GITHUB_REPO_URL}/blob/master/docs/plugin-dev-guide.md"
PLUGIN_REPO_URL      = f"{GITHUB_REPO_URL}/tree/master/plugins"
ISSUES_URL           = f"{GITHUB_REPO_URL}/issues"
WIKI_URL             = f"{GITHUB_REPO_URL}/wiki"


def _parse_version(ver_str: str) -> tuple:
    """将版本字符串（如 v4.3.1 / 4.3.1）解析为可比较的整数元组"""
    ver_str = ver_str.lstrip("vV").strip()
    parts = re.findall(r"\d+", ver_str)
    return tuple(int(p) for p in parts[:3]) if parts else (0, 0, 0)


def _fetch_latest_release(timeout: int = 8) -> Optional[dict]:
    """
    从 GitHub API 获取最新 Release 信息。
    返回字典含：tag_name, name, body, published_at, assets, html_url
    若请求失败返回 None。
    """
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
        return data
    except Exception:
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

# 公告数据源：GitHub raw 文件（主分支）
ANNOUNCEMENTS_URL = (
    f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}"
    "/master/docs/announcements.json"
)


def fetch_announcements(callback: Callable[[list], None],
                        timeout: int = 8) -> None:
    """
    异步拉取远程公告列表，完成后回调。

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

    callback 接收一个公告列表（解析失败时为空列表）。
    """
    def _worker():
        try:
            req = urllib.request.Request(
                ANNOUNCEMENTS_URL,
                headers={"User-Agent": "AutoFlow-Updater/1.0"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
            announcements = json.loads(raw)
            if not isinstance(announcements, list):
                announcements = []
        except Exception:
            announcements = []
        callback(announcements)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


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

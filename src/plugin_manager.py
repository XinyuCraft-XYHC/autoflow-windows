"""
AutoFlow 插件管理器
负责：
  1. 扫描并加载 plugins/ 目录下的所有插件
  2. 向 BLOCK_TYPES / BLOCK_PARAMS 注册插件提供的功能块
  3. 向触发器系统注册插件提供的触发器
  4. 提供插件启用/禁用/卸载接口
  5. 持久化插件启用状态
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import sys
import traceback
from typing import Any, Callable, Dict, List, Optional, Set

from .plugin_api import AutoFlowPlugin, PluginRegistrationAPI
from .engine.models import BLOCK_TYPES, BLOCK_PARAMS

logger = logging.getLogger("autoflow.plugin_manager")

# 插件目录：%LOCALAPPDATA%\XinyuCraft\AutoFlow\plugins\
_APP_DATA_DIR   = os.path.join(os.environ.get("LOCALAPPDATA",
                    os.path.expanduser("~")), "XinyuCraft", "AutoFlow")
_PLUGIN_DIR     = os.path.join(_APP_DATA_DIR, "plugins")
_PLUGIN_STATE_F = os.path.join(_APP_DATA_DIR, "plugin_state.json")

# 内置示例插件目录（随源码/exe 发布）
# 源码运行时：autoflow/src/ -> autoflow/plugins/
# PyInstaller 打包后：_MEIPASS/src/ -> _MEIPASS/plugins/（需在 spec 中添加）
_BUILTIN_PLUGIN_DIR = os.path.join(
    os.path.dirname(__file__),   # autoflow/src/
    "..",                         # autoflow/
    "plugins"
)


def _ensure_plugin_dir():
    os.makedirs(_PLUGIN_DIR, exist_ok=True)


# ─────────────────── 插件元信息 ───────────────────

class PluginMeta:
    """描述一个已发现（但不一定加载）的插件"""
    def __init__(self, plugin_dir: str, info: dict):
        self.dir         = plugin_dir
        self.id: str     = info.get("id", os.path.basename(plugin_dir))
        self.name: str   = info.get("name", self.id)
        self.version: str= info.get("version", "?")
        self.author: str = info.get("author", "")
        self.description = info.get("description", "")
        self.entry: str  = info.get("entry", "main.py")
        self.permissions: List[str] = info.get("permissions", [])
        self.tags: List[str]        = info.get("tags", [])
        self.min_app_version: str   = info.get("min_app_version", "0.0.0")
        self.icon_path: str         = os.path.join(plugin_dir, "icon.png")
        # 运行时状态
        self.loaded: bool  = False
        self.enabled: bool = True
        self.error: str    = ""
        self.instance: Optional[AutoFlowPlugin] = None


# ─────────────────── 插件管理器 ───────────────────

class PluginManager:
    """单例插件管理器"""

    _instance: Optional["PluginManager"] = None

    @classmethod
    def instance(cls) -> "PluginManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        if PluginManager._instance is not None:
            raise RuntimeError("PluginManager 是单例，请使用 PluginManager.instance()")
        self.config: Optional[Any] = None           # AppConfig（主窗口注入）
        self._metas: Dict[str, PluginMeta] = {}     # id -> PluginMeta
        self._enabled: Set[str] = set()             # 启用的插件 id
        self._loaded_ids: List[str] = []            # 加载顺序
        # 插件注入到宿主的资源
        self._plugin_block_types: Dict[str, dict] = {}   # type -> BLOCK_TYPES 条目
        self._plugin_block_params: Dict[str, dict] = {}  # type -> BLOCK_PARAMS 条目
        self._plugin_executors: Dict[str, Callable] = {} # type -> executor 函数
        self._plugin_triggers: List[dict] = []           # 所有插件触发器定义
        # 变更回调（UI 监听）
        self._on_changed_callbacks: List[Callable] = []
        _ensure_plugin_dir()
        self._load_state()

    # ── 状态持久化 ──

    def _load_state(self):
        try:
            if os.path.exists(_PLUGIN_STATE_F):
                with open(_PLUGIN_STATE_F, "r", encoding="utf-8") as f:
                    state = json.load(f)
                self._enabled = set(state.get("enabled", []))
        except Exception:
            self._enabled = set()

    def _save_state(self):
        try:
            state = {"enabled": list(self._enabled)}
            with open(_PLUGIN_STATE_F, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"插件状态保存失败: {e}")

    # ── 扫描插件目录 ──

    def scan(self) -> List[PluginMeta]:
        """扫描所有插件目录，返回发现的插件列表"""
        search_dirs = [_PLUGIN_DIR]
        # 如果内置插件目录存在则也扫描
        if os.path.isdir(_BUILTIN_PLUGIN_DIR):
            search_dirs.append(_BUILTIN_PLUGIN_DIR)

        found: Dict[str, PluginMeta] = {}
        for base_dir in search_dirs:
            if not os.path.isdir(base_dir):
                continue
            for name in sorted(os.listdir(base_dir)):
                pdir = os.path.join(base_dir, name)
                if not os.path.isdir(pdir):
                    continue
                info_path = os.path.join(pdir, "plugin.json")
                if not os.path.exists(info_path):
                    continue
                try:
                    with open(info_path, "r", encoding="utf-8") as f:
                        info = json.load(f)
                    meta = PluginMeta(pdir, info)
                    # 默认启用（若状态文件中明确禁用则 False）
                    # 若状态文件里完全没有此 id，视为首次安装，默认启用
                    if self._enabled:
                        meta.enabled = meta.id in self._enabled
                    else:
                        meta.enabled = True
                    if meta.id not in found:
                        found[meta.id] = meta
                        logger.debug(f"发现插件: {meta.name} ({meta.id}) @ {pdir}")
                except Exception as e:
                    logger.warning(f"解析插件元信息失败 {pdir}: {e}")

        self._metas = found
        return list(found.values())

    # ── 加载 & 卸载 ──

    def load_all(self) -> None:
        """加载所有已启用插件"""
        self.scan()
        for meta in self._metas.values():
            if meta.enabled:
                self._load_plugin(meta)

    def _load_plugin(self, meta: PluginMeta) -> bool:
        """加载单个插件，返回是否成功"""
        if meta.loaded:
            return True
        entry = os.path.join(meta.dir, meta.entry)
        if not os.path.exists(entry):
            meta.error = f"入口文件不存在: {entry}"
            logger.error(f"[{meta.id}] {meta.error}")
            return False

        # 版本兼容检查
        try:
            from .version import VERSION
            if not _version_gte(VERSION, meta.min_app_version):
                meta.error = f"需要 AutoFlow >= {meta.min_app_version}"
                logger.warning(f"[{meta.id}] {meta.error}")
                return False
        except Exception:
            pass

        # 动态加载模块
        try:
            module_name = f"autoflow_plugin_{meta.id}"
            spec = importlib.util.spec_from_file_location(module_name, entry)
            module = importlib.util.module_from_spec(spec)
            # 将插件目录加入 sys.path（允许插件内相对导入）
            if meta.dir not in sys.path:
                sys.path.insert(0, meta.dir)
            spec.loader.exec_module(module)

            # 调用 register(api)
            if not hasattr(module, "register"):
                meta.error = "未找到 register(api) 函数"
                logger.error(f"[{meta.id}] {meta.error}")
                return False

            api = PluginRegistrationAPI(self)
            module.register(api)
            meta.loaded = True
            meta.error  = ""
            if meta.id not in self._loaded_ids:
                self._loaded_ids.append(meta.id)
            logger.info(f"插件已加载: {meta.name} v{meta.version}")
            return True

        except Exception:
            meta.error = traceback.format_exc()
            logger.error(f"[{meta.id}] 加载失败:\n{meta.error}")
            return False

    def _do_register(self, plugin: AutoFlowPlugin) -> None:
        """由 PluginRegistrationAPI 调用，将插件注入到宿主系统"""
        pid = plugin.id
        if not pid:
            logger.warning("插件未设置 id，跳过注册")
            return

        # 找到对应 meta
        meta = self._metas.get(pid)
        if meta:
            meta.instance = plugin

        # 调用 on_load
        try:
            plugin.on_load()
        except Exception as e:
            logger.warning(f"[{pid}] on_load 失败: {e}")

        # 注册功能块
        for bdef in plugin.get_blocks():
            btype = bdef.get("type")
            if not btype:
                continue
            BLOCK_TYPES[btype] = {
                "label":    bdef.get("label", btype),
                "category": bdef.get("category", f"插件:{plugin.name}"),
                "color":    bdef.get("color", "#607D8B"),
                "icon":     bdef.get("icon", "🔌"),
            }
            if "params" in bdef:
                BLOCK_PARAMS[btype] = bdef["params"]
            if "executor" in bdef:
                self._plugin_executors[btype] = bdef["executor"]
            self._plugin_block_types[btype] = BLOCK_TYPES[btype]
            self._plugin_block_params[btype] = BLOCK_PARAMS.get(btype, {})
            logger.debug(f"[{pid}] 注册功能块: {btype}")

        # 注册触发器
        for tdef in plugin.get_triggers():
            if tdef.get("type"):
                self._plugin_triggers.append(tdef)
                logger.debug(f"[{pid}] 注册触发器: {tdef['type']}")

        # 通知 UI 变更
        self._fire_changed()

    def unload_plugin(self, plugin_id: str) -> None:
        """卸载插件（从 BLOCK_TYPES/BLOCK_PARAMS 移除，调用 on_unload）"""
        meta = self._metas.get(plugin_id)
        if not meta or not meta.loaded:
            return
        if meta.instance:
            try:
                meta.instance.on_unload()
            except Exception as e:
                logger.warning(f"[{plugin_id}] on_unload 失败: {e}")
            # 移除功能块
            for btype in list(self._plugin_block_types.keys()):
                BLOCK_TYPES.pop(btype, None)
                BLOCK_PARAMS.pop(btype, None)
                self._plugin_executors.pop(btype, None)
            self._plugin_block_types.clear()
            self._plugin_block_params.clear()
            meta.instance = None
        meta.loaded = False
        if plugin_id in self._loaded_ids:
            self._loaded_ids.remove(plugin_id)
        logger.info(f"插件已卸载: {plugin_id}")
        self._fire_changed()

    # ── 启用/禁用 ──

    def set_enabled(self, plugin_id: str, enabled: bool) -> None:
        meta = self._metas.get(plugin_id)
        if not meta:
            return
        meta.enabled = enabled
        if enabled:
            self._enabled.add(plugin_id)
            if not meta.loaded:
                self._load_plugin(meta)
        else:
            self._enabled.discard(plugin_id)
            if meta.loaded:
                self.unload_plugin(plugin_id)
        self._save_state()
        self._fire_changed()

    # ── 查询 ──

    def get_all_metas(self) -> List[PluginMeta]:
        return list(self._metas.values())

    def get_executor(self, block_type: str) -> Optional[Callable]:
        return self._plugin_executors.get(block_type)

    def get_plugin_triggers(self) -> List[dict]:
        return list(self._plugin_triggers)

    def is_plugin_block(self, block_type: str) -> bool:
        return block_type in self._plugin_block_types

    # ── 变更通知 ──

    def add_on_changed(self, cb: Callable) -> None:
        if cb not in self._on_changed_callbacks:
            self._on_changed_callbacks.append(cb)

    def remove_on_changed(self, cb: Callable) -> None:
        self._on_changed_callbacks = [c for c in self._on_changed_callbacks if c != cb]

    def _fire_changed(self):
        for cb in list(self._on_changed_callbacks):
            try:
                cb()
            except Exception:
                pass


# ─────────────────── 工具函数 ───────────────────

def _version_gte(v1: str, v2: str) -> bool:
    """v1 >= v2"""
    try:
        def parse(v):
            return tuple(int(x) for x in v.split(".")[:3])
        return parse(v1) >= parse(v2)
    except Exception:
        return True

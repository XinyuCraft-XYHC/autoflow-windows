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
        # ── 新增：扩展资源 ──
        self._plugin_conditions: List[dict] = []         # 所有插件条件定义（约束+判断）
        self._condition_evaluators: Dict[str, Callable] = {}  # type -> evaluator
        self._plugin_hotkeys: List[dict] = []            # 所有插件快捷键定义
        self._hotkey_bindings: Dict[str, str] = {}       # id -> 当前绑定按键（用户可覆盖）
        self._plugin_settings_tabs: List[tuple] = []     # [(title, widget), ...]
        self._plugin_context_menus: List[dict] = []      # 右键菜单扩展项
        self._plugin_tray_menus: List[dict] = []         # 托盘菜单扩展项
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
                self._hotkey_bindings = state.get("hotkey_bindings", {})
        except Exception:
            self._enabled = set()
            self._hotkey_bindings = {}

    def _save_state(self):
        try:
            state = {
                "enabled": list(self._enabled),
                "hotkey_bindings": self._hotkey_bindings,
            }
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

            # ── 注入兼容模块 autoflow_plugin_api ──────────────────
            # 旧版插件或社区插件可能 `from autoflow_plugin_api import PluginBase`
            # 此处动态创建兼容模块并注入 sys.modules，使其指向本包的 AutoFlowPlugin
            if "autoflow_plugin_api" not in sys.modules:
                import types as _types
                _compat = _types.ModuleType("autoflow_plugin_api")
                _compat.PluginBase        = AutoFlowPlugin   # 兼容旧命名
                _compat.AutoFlowPlugin    = AutoFlowPlugin
                _compat.PluginRegistrationAPI = PluginRegistrationAPI
                sys.modules["autoflow_plugin_api"] = _compat
            # ──────────────────────────────────────────────────────

            spec.loader.exec_module(module)

            # 调用 register(api)
            # 兼容两种插件签名：
            #   新版：register(api)  直接调 api.register_plugin(plugin)
            #   旧版：register()     返回 AutoFlowPlugin 实例
            if not hasattr(module, "register"):
                meta.error = "未找到 register(api) 函数"
                logger.error(f"[{meta.id}] {meta.error}")
                return False

            api = PluginRegistrationAPI(self)

            import inspect as _inspect
            _reg_sig = _inspect.signature(module.register)
            if len(_reg_sig.parameters) == 0:
                # 旧版签名：register() → 返回插件实例
                _plugin_inst = module.register()
                if isinstance(_plugin_inst, AutoFlowPlugin):
                    api.register_plugin(_plugin_inst)
                else:
                    meta.error = "register() 未返回有效的 AutoFlowPlugin 实例"
                    logger.error(f"[{meta.id}] {meta.error}")
                    return False
            else:
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
        # 兼容旧版插件：id 可能在 get_info() 里返回而不是直接设置到属性
        if not pid:
            try:
                info = plugin.get_info() if hasattr(plugin, "get_info") else {}
                pid = info.get("id", "") if isinstance(info, dict) else ""
                if pid:
                    plugin.id = pid  # 回写，使后续访问一致
                    # 同步 name/version/author（若基类属性为空）
                    if not plugin.name:
                        plugin.name = info.get("name", pid)
                    if plugin.version == "1.0.0" or not plugin.version:
                        plugin.version = info.get("version", plugin.version)
                    if not plugin.author:
                        plugin.author = info.get("author", "")
            except Exception:
                pass
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
            # 兼容新格式（params dict）和旧格式（fields list）
            if "params" in bdef:
                BLOCK_PARAMS[btype] = bdef["params"]
            elif "fields" in bdef:
                # 将 fields list 转换为 params dict
                params_dict = {}
                for f in bdef["fields"]:
                    fname = f.get("name", "")
                    if fname:
                        params_dict[fname] = {
                            "type":    f.get("type", "string"),
                            "label":   f.get("label", fname),
                            "default": f.get("default", ""),
                        }
                        if "options" in f:
                            params_dict[fname]["options"] = f["options"]
                        if "placeholder" in f:
                            params_dict[fname]["placeholder"] = f["placeholder"]
                BLOCK_PARAMS[btype] = params_dict
            if "executor" in bdef:
                self._plugin_executors[btype] = bdef["executor"]
            elif not bdef.get("executor") and hasattr(plugin, "execute_block"):
                # 旧格式插件只有 execute_block(block_type, params, ctx) 方法
                # 包装成 executor(params_dict, ctx) 函数
                _bt = btype   # 闭包变量
                _inst = plugin
                def _make_executor(bt, inst):
                    def _executor(params_dict, ctx):
                        result = inst.execute_block(bt, params_dict, ctx)
                        # 将返回的 variables 写入 ctx.variables
                        if isinstance(result, dict) and ctx is not None:
                            for k, v in result.get("variables", {}).items():
                                ctx.variables[k] = v
                    return _executor
                self._plugin_executors[btype] = _make_executor(_bt, _inst)
            self._plugin_block_types[btype] = BLOCK_TYPES[btype]
            self._plugin_block_params[btype] = BLOCK_PARAMS.get(btype, {})
            logger.debug(f"[{pid}] 注册功能块: {btype}")

        # 注册触发器
        for tdef in plugin.get_triggers():
            if tdef.get("type"):
                self._plugin_triggers.append(tdef)
                logger.debug(f"[{pid}] 注册触发器: {tdef['type']}")

        # ── 注册约束/判断条件 ──
        try:
            for cdef in plugin.get_conditions():
                ctype = cdef.get("type")
                if not ctype:
                    continue
                self._plugin_conditions.append(cdef)
                if "evaluator" in cdef:
                    self._condition_evaluators[ctype] = cdef["evaluator"]
                logger.debug(f"[{pid}] 注册条件: {ctype}")
        except Exception as e:
            logger.warning(f"[{pid}] get_conditions 失败: {e}")

        # ── 注册快捷键 ──
        try:
            for hdef in plugin.get_hotkeys():
                hid = hdef.get("id")
                if not hid:
                    continue
                # 若用户曾手动绑定，用用户绑定；否则用默认
                if hid not in self._hotkey_bindings:
                    self._hotkey_bindings[hid] = hdef.get("default", "")
                self._plugin_hotkeys.append({**hdef, "_binding": self._hotkey_bindings[hid]})
                logger.debug(f"[{pid}] 注册快捷键: {hid}")
        except Exception as e:
            logger.warning(f"[{pid}] get_hotkeys 失败: {e}")

        # ── 注册设置 Tab ──
        try:
            tab_info = plugin.get_settings_tab()
            if tab_info is not None:
                tab_title, tab_widget = tab_info
                self._plugin_settings_tabs.append((tab_title, tab_widget, pid))
                logger.debug(f"[{pid}] 注册设置Tab: {tab_title}")
        except Exception as e:
            logger.warning(f"[{pid}] get_settings_tab 失败: {e}")

        # ── 注册右键菜单项 ──
        try:
            for mdef in plugin.get_context_menu_items():
                if mdef.get("id"):
                    self._plugin_context_menus.append(mdef)
                    logger.debug(f"[{pid}] 注册右键菜单: {mdef['id']}")
        except Exception as e:
            logger.warning(f"[{pid}] get_context_menu_items 失败: {e}")

        # ── 注册托盘菜单项 ──
        try:
            for mdef in plugin.get_tray_menu_items():
                if mdef.get("id"):
                    self._plugin_tray_menus.append(mdef)
                    logger.debug(f"[{pid}] 注册托盘菜单: {mdef['id']}")
        except Exception as e:
            logger.warning(f"[{pid}] get_tray_menu_items 失败: {e}")

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
            # 移除条件
            self._plugin_conditions = [
                c for c in self._plugin_conditions
                if not c.get("type", "").startswith(f"{plugin_id}.")
            ]
            for ctype in [k for k in self._condition_evaluators
                          if k.startswith(f"{plugin_id}.")]:
                self._condition_evaluators.pop(ctype, None)
            # 移除快捷键
            self._plugin_hotkeys = [
                h for h in self._plugin_hotkeys
                if not h.get("id", "").startswith(f"{plugin_id}.")
            ]
            # 移除设置Tab
            self._plugin_settings_tabs = [
                t for t in self._plugin_settings_tabs if t[2] != plugin_id
            ]
            # 移除菜单
            self._plugin_context_menus = [
                m for m in self._plugin_context_menus
                if not m.get("id", "").startswith(f"{plugin_id}.")
            ]
            self._plugin_tray_menus = [
                m for m in self._plugin_tray_menus
                if not m.get("id", "").startswith(f"{plugin_id}.")
            ]
            # 移除触发器
            self._plugin_triggers = [
                t for t in self._plugin_triggers
                if not t.get("type", "").startswith(f"{plugin_id}.")
            ]
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

    def get_plugin_conditions(self, scope: str = "both") -> List[dict]:
        """返回指定场景的插件条件定义列表（scope: constraint/if/both）"""
        result = []
        for c in self._plugin_conditions:
            cscope = c.get("scope", "both")
            if scope == "both" or cscope == "both" or cscope == scope:
                result.append(c)
        return result

    def get_condition_evaluator(self, ctype: str) -> Optional[Callable]:
        return self._condition_evaluators.get(ctype)

    def get_plugin_hotkeys(self) -> List[dict]:
        """返回所有插件快捷键定义（含当前绑定键）"""
        return list(self._plugin_hotkeys)

    def set_hotkey_binding(self, hotkey_id: str, key: str) -> None:
        """用户修改快捷键绑定，持久化"""
        self._hotkey_bindings[hotkey_id] = key
        for hdef in self._plugin_hotkeys:
            if hdef.get("id") == hotkey_id:
                hdef["_binding"] = key
        self._save_state()

    def get_plugin_settings_tabs(self) -> List[tuple]:
        """返回 [(tab_title, widget, plugin_id), ...]"""
        return list(self._plugin_settings_tabs)

    def get_context_menu_items(self, block_type: str = "") -> List[dict]:
        """返回适用于 block_type 的右键菜单扩展项"""
        result = []
        for m in self._plugin_context_menus:
            for_types = m.get("for_types", [])
            if not for_types or block_type in for_types:
                result.append(m)
        return result

    def get_tray_menu_items(self) -> List[dict]:
        return list(self._plugin_tray_menus)

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

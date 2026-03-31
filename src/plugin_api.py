"""
AutoFlow 插件 API 接口定义
插件开发者只需继承 AutoFlowPlugin 并实现对应方法，
然后在 plugin.json 中声明元信息即可。

目录结构示例：
  plugins/
    my_plugin/
      plugin.json          ← 插件元信息
      main.py              ← 插件主文件（必须含 register(api) 函数）
      icon.png             ← 可选图标
      README.md            ← 可选说明

plugin.json 格式：
{
  "id": "my_plugin",
  "name": "我的插件",
  "version": "1.0.0",
  "author": "作者名",
  "description": "插件功能描述",
  "min_app_version": "2.6.0",
  "entry": "main.py",
  "permissions": ["block", "trigger", "condition", "hotkey", "setting", "menu"],
  "tags": ["工具", "效率"]
}

权限说明（permissions）：
  block     - 提供自定义功能块
  trigger   - 提供自定义触发器
  condition - 提供自定义约束条件/判断条件
  hotkey    - 注册全局快捷键
  setting   - 在设置页面添加 Tab
  menu      - 扩展右键菜单/托盘菜单
"""

from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    pass


# ─────────────────── 插件基类 ───────────────────

class AutoFlowPlugin:
    """
    AutoFlow 插件基类。
    插件的 register(api) 函数应实例化此类（或子类）并调用 api.register_plugin(plugin)。
    插件按需覆写以下方法。
    """

    # ── 元信息（应与 plugin.json 保持一致）──
    id: str = ""
    name: str = ""
    version: str = "1.0.0"
    author: str = ""
    description: str = ""

    def on_load(self) -> None:
        """插件加载时调用（初始化资源等）"""
        pass

    def on_unload(self) -> None:
        """插件卸载时调用（清理资源等）"""
        pass

    def get_blocks(self) -> List[Dict[str, Any]]:
        """
        返回此插件提供的功能块定义列表。
        每个字典格式：
        {
          "type":        "my_plugin.do_something",   # 全局唯一
          "label":       "做某事",
          "category":    "我的插件",
          "color":       "#4CAF50",
          "icon":        "⚡",
          "params": {                                  # 参数规格（同 BLOCK_PARAMS）
            "param1": {"type": "string", "label": "参数1", "default": ""},
          },
          "executor":    self._exec_do_something,      # Callable(params, ctx) -> None
        }
        """
        return []

    def get_triggers(self) -> List[Dict[str, Any]]:
        """
        返回此插件提供的触发器定义列表。
        每个字典格式：
        {
          "type":       "my_plugin.my_trigger",
          "label":      "我的触发器",
          "icon":       "🔔",
          "params": { ... },
          "monitor_class": MyMonitorClass,   # TriggerMonitor 要实例化的类
        }
        """
        return []

    def get_conditions(self) -> List[Dict[str, Any]]:
        """
        返回此插件提供的约束条件/判断条件定义列表。
        既可用于任务约束（constraint_editor），也可用于 if 条件判断。
        每个字典格式：
        {
          "type":    "my_plugin.check_something",  # 全局唯一，建议带插件前缀
          "label":   "检查某事",
          "icon":    "🔍",                          # 可选
          "params": {                               # 参数规格，同 BLOCK_PARAMS
            "target": {"type": "string", "label": "目标值", "default": ""},
          },
          "evaluator": self._eval_check,  # Callable(params, ctx) -> bool
          # 可选：条件可用于的场景（"constraint"=任务约束, "if"=判断条件, both=两者）
          "scope": "both",
        }
        """
        return []

    def get_hotkeys(self) -> List[Dict[str, Any]]:
        """
        返回此插件注册的全局快捷键列表。
        每个字典格式：
        {
          "id":       "my_plugin.action_x",  # 全局唯一
          "label":    "触发动作X",             # 显示在设置 → 按键列表中
          "default":  "ctrl+shift+x",         # 默认快捷键
          "callback": self._on_hotkey_x,      # Callable() -> None（在主线程调用）
        }
        """
        return []

    def get_settings_widget(self) -> Optional[Any]:
        """
        返回插件设置页面的 QWidget（用于插件管理页面内联设置区域），
        None 则不显示设置按钮。
        """
        return None

    def get_settings_tab(self) -> Optional[Any]:
        """
        返回在「设置」面板中作为独立 Tab 展示的 QWidget。
        返回值应为 (tab_title: str, widget: QWidget) 元组，或 None。
        示例：return ("我的插件", MySettingsWidget())
        """
        return None

    def get_context_menu_items(self) -> List[Dict[str, Any]]:
        """
        返回在任务编辑器功能块右键菜单中扩展的菜单项列表。
        每个字典格式：
        {
          "id":       "my_plugin.menu_item",
          "label":    "我的菜单项",
          "icon":     "🔧",             # 可选
          "callback": self._on_menu,    # Callable(block_data: dict) -> None
          # 可选：仅对特定 block type 显示
          "for_types": ["my_plugin.my_block"],
        }
        """
        return []

    def get_tray_menu_items(self) -> List[Dict[str, Any]]:
        """
        返回系统托盘菜单中扩展的菜单项列表。
        每个字典格式：
        {
          "id":       "my_plugin.tray_item",
          "label":    "托盘项目",
          "icon":     "🔌",            # 可选
          "callback": self._on_tray,   # Callable() -> None
        }
        """
        return []

    def open_dialog(self, title: str, widget_factory: Callable) -> Optional[Any]:
        """
        便捷方法：在主线程弹出一个对话框。
        widget_factory: Callable(parent: QDialog) -> QWidget
        返回对话框结果（QDialog.DialogCode）。
        注意：仅在主线程中调用。
        """
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox
        try:
            dlg = QDialog()
            dlg.setWindowTitle(title)
            layout = QVBoxLayout(dlg)
            w = widget_factory(dlg)
            layout.addWidget(w)
            btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
            btns.accepted.connect(dlg.accept)
            btns.rejected.connect(dlg.reject)
            layout.addWidget(btns)
            return dlg.exec()
        except Exception:
            return None


# ─────────────────── 插件执行上下文 ───────────────────

class BlockExecutionContext:
    """
    传递给插件功能块 executor 的上下文对象。
    executor(params: dict, ctx: BlockExecutionContext) -> None
    """
    def __init__(self,
                 variables: Dict[str, Any],
                 log: Callable[[str, str], None],
                 stop_event=None,
                 config: Optional[Any] = None):
        self.variables  = variables      # 当前任务变量（可读写）
        self._log       = log
        self._stop_event = stop_event
        self.config     = config         # AppConfig 对象

    def log(self, message: str, level: str = "INFO"):
        """向日志面板写入消息"""
        self._log(level, f"[Plugin] {message}")

    def is_stopped(self) -> bool:
        """检查任务是否被要求停止"""
        return self._stop_event is not None and self._stop_event.is_set()

    def set_variable(self, name: str, value: Any):
        """设置任务变量"""
        self.variables[name] = value

    def get_variable(self, name: str, default: Any = "") -> Any:
        """获取任务变量"""
        return self.variables.get(name, default)


# ─────────────────── 插件注册 API ───────────────────

class PluginRegistrationAPI:
    """
    传递给每个插件 register(api) 函数的注册接口。
    插件通过此接口向 AutoFlow 注册自身。
    """
    def __init__(self, manager: "PluginManager"):
        self._manager = manager

    def register_plugin(self, plugin: AutoFlowPlugin) -> None:
        """注册一个插件实例"""
        self._manager._do_register(plugin)

    def get_app_version(self) -> str:
        """返回当前 AutoFlow 版本字符串"""
        from .version import VERSION
        return VERSION

    def get_config(self) -> Optional[Any]:
        """返回当前 AppConfig（可能为 None）"""
        return self._manager.config

    def log(self, message: str, level: str = "INFO"):
        """写日志"""
        import logging
        logging.getLogger("autoflow.plugin").log(
            getattr(logging, level.upper(), logging.INFO), message
        )


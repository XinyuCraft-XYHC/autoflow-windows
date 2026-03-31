# AutoFlow 插件开发指南

> 适用版本：AutoFlow v4.16.0+

## 概述

AutoFlow 提供了灵活的插件系统，允许开发者编写自定义功能块、触发器、约束条件、全局快捷键、设置页 Tab 和菜单扩展。本指南将帮助你从零开始创建、测试并发布一个 AutoFlow 插件。

---

## 目录

1. [快速开始](#快速开始)
2. [插件结构](#插件结构)
3. [核心概念](#核心概念)
4. [开发功能块](#开发功能块)
5. [开发触发器](#开发触发器)
6. [开发约束条件](#开发约束条件)
7. [注册全局快捷键](#注册全局快捷键)
8. [添加设置 Tab](#添加设置-tab)
9. [扩展菜单](#扩展菜单)
10. [API 参考](#api-参考)
11. [示例代码](#示例代码)
12. [测试与调试](#测试与调试)
13. [打包与发布](#打包与发布)
14. [发布到插件市场](#发布到插件市场)
15. [常见问题](#常见问题)

---

## 快速开始

### 1. 创建插件目录结构

```
plugins/
  my_plugin/
    plugin.json          # 插件元信息（必需）
    main.py              # 入口文件（必需，需含 register(api) 函数）
    icon.png             # 插件图标（可选，建议 64×64 PNG）
    README.md            # 插件说明（推荐）
    utils.py             # 辅助模块（可选）
```

### 2. 编写 plugin.json

```json
{
  "id": "my_plugin",
  "name": "我的插件",
  "version": "1.0.0",
  "author": "你的名字",
  "description": "插件的功能描述",
  "entry": "main.py",
  "min_app_version": "4.0.0",
  "permissions": ["block"],
  "tags": ["效率", "工具"]
}
```

**字段说明：**
- `id`: 插件的全局唯一标识符（推荐使用 `snake_case`）
- `name`: 插件的显示名称
- `version`: 遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)
- `author`: 开发者名字或组织
- `description`: 插件的简要介绍
- `entry`: 入口文件名（默认 `main.py`）
- `min_app_version`: 插件依赖的最低 AutoFlow 版本（v4.16.0+ 建议填 `"4.16.0"`）
- `permissions`: 权限列表，支持以下值：
  - `"block"` — 提供自定义功能块
  - `"trigger"` — 提供自定义触发器
  - `"condition"` — 提供自定义约束条件 / IF 判断条件
  - `"hotkey"` — 注册全局快捷键（显示在设置→快捷键列表）
  - `"setting"` — 在「设置」面板添加独立 Tab
  - `"menu"` — 扩展功能块右键菜单 / 系统托盘菜单
- `tags`: 插件标签（用于分类和搜索）

### 3. 编写 main.py

最小示例：

```python
def register(api):
    """AutoFlow 调用此函数完成插件注册"""
    from src.plugin_api import AutoFlowPlugin

    class MyPlugin(AutoFlowPlugin):
        id = "my_plugin"
        name = "我的插件"
        version = "1.0.0"
        author = "你的名字"
        description = "插件描述"

        def get_blocks(self):
            """返回此插件提供的功能块"""
            return []

        def get_triggers(self):
            """返回此插件提供的触发器"""
            return []

    plugin = MyPlugin()
    api.register_plugin(plugin)
```

### 4. 安装与测试

将插件文件夹放在以下目录：

- **Windows**: `%LOCALAPPDATA%\XinyuCraft\AutoFlow\plugins\`

然后启动 AutoFlow，打开「设置」→「插件」，应该能看到你的插件。

---

## 插件结构

### 目录布局

AutoFlow 在启动时扫描以下两个位置的插件：

1. **用户插件目录**（用户安装）：`%LOCALAPPDATA%\XinyuCraft\AutoFlow\plugins\`
2. **内置插件目录**（随源码发布）：`plugins/`（相对于应用目录）

### 元信息文件 (plugin.json)

每个插件 **必须** 在根目录包含 `plugin.json` 文件，用于声明插件元信息。

**必需字段：**
- `id`: 插件唯一标识
- `name`: 显示名称
- `version`: 版本号

**可选字段：**
- `author`: 作者名
- `description`: 描述
- `entry`: 入口文件（默认 `main.py`）
- `min_app_version`: 最低版本要求
- `permissions`: 权限列表 `["block", "trigger", "setting"]`
- `tags`: 标签列表

### 入口文件 (main.py)

入口文件 **必须** 定义一个全局函数 `register(api)`，AutoFlow 在加载插件时会调用此函数。

```python
def register(api):
    # 这里完成插件初始化和注册
    pass
```

---

## 核心概念

### 1. 自动加载与版本检查

AutoFlow 在启动时：
1. 扫描插件目录，读取所有 `plugin.json`
2. 检查插件版本是否符合 `min_app_version`
3. 根据插件启用状态（保存在 `plugin_state.json`）加载插件
4. 调用每个插件的 `register(api)` 函数

### 2. 权限系统

插件在 `plugin.json` 的 `permissions` 字段中声明所需权限：

| 权限 | 说明 | 对应方法 |
|------|------|---------|
| `"block"` | 提供自定义功能块 | `get_blocks()` |
| `"trigger"` | 提供自定义触发器 | `get_triggers()` |
| `"condition"` | 提供自定义约束条件 / IF 判断条件 | `get_conditions()` |
| `"hotkey"` | 注册全局快捷键（显示在设置→快捷键） | `get_hotkeys()` |
| `"setting"` | 在「设置」面板添加独立 Tab | `get_settings_tab()` |
| `"menu"` | 扩展功能块右键菜单 / 系统托盘菜单 | `get_context_menu_items()` / `get_tray_menu_items()` |

### 3. 变量替换

AutoFlow 任务支持 `{{variable_name}}` 语法替换变量。插件功能块可使用 `ctx.variables` 访问和修改任务变量。

---

## 开发功能块

### 基础概念

功能块是插件提供的可执行单元，在任务编辑器中显示为一张卡片，用户可以配置参数、设置约束条件、添加到任务中。

### 定义功能块

在 `get_blocks()` 方法中返回功能块定义列表：

```python
def get_blocks(self):
    return [
        {
            "type":        "my_plugin.do_something",    # 全局唯一标识
            "label":       "做某事",                     # UI 显示标签
            "category":    "我的插件",                   # 分类名
            "color":       "#4CAF50",                    # 卡片颜色（十六进制）
            "icon":        "⚡",                         # 卡片图标（Unicode emoji）
            "params": {                                  # 参数规格
                "name": {
                    "type": "string",
                    "label": "名称",
                    "default": "世界",
                    "placeholder": "输入名称"
                }
            },
            "executor":    self._exec_do_something,     # 执行函数
        }
    ]
```

### 参数类型

AutoFlow 支持以下参数类型：

| 类型 | 说明 | 示例 |
|------|------|------|
| `string` | 文本字符串 | `"hello"` |
| `number` | 整数或浮点数 | `42`, `3.14` |
| `number_or_var` | 数字或变量引用 | `10` 或 `{{count}}` |
| `select` | 下拉选择 | 需搭配 `options` 字段 |
| `checkbox` | 复选框 | 布尔值 |
| `textarea` | 多行文本 | 长文本内容 |
| `file` | 文件路径 | `"C:\\path\\to\\file"` |
| `color` | 颜色选择器 | `"#FF0000"` |
| `coordinate` | 坐标（支持百分比模式） | `[100, 200]` 或 `[50%, 50%]` |

### 参数配置示例

```python
"params": {
    "text": {
        "type": "string",
        "label": "输入文本",
        "default": "hello",
        "placeholder": "输入任意文本"
    },
    "count": {
        "type": "number_or_var",
        "label": "重复次数",
        "default": 1
    },
    "mode": {
        "type": "select",
        "label": "模式",
        "default": "normal",
        "options": ["normal", "advanced"],
        "option_labels": ["普通模式", "高级模式"]
    },
    "enabled": {
        "type": "checkbox",
        "label": "是否启用",
        "default": True
    }
}
```

### 执行函数

执行函数接收两个参数：`params` 和 `ctx`

```python
def _exec_do_something(self, params, ctx):
    """
    params: dict，用户配置的参数值
    ctx: BlockExecutionContext，执行上下文
    """
    name = params.get("name", "世界")
    message = f"你好，{name}！"
    ctx.log(message)
    ctx.set_variable("greeting", message)
```

### 上下文对象 (BlockExecutionContext)

执行函数中的 `ctx` 提供以下方法：

| 方法 | 说明 |
|------|------|
| `ctx.log(message, level="INFO")` | 向日志面板写入消息（level: INFO/WARN/ERROR）|
| `ctx.set_variable(name, value)` | 设置任务变量 |
| `ctx.get_variable(name, default="")` | 获取任务变量 |
| `ctx.is_stopped()` | 检查任务是否被要求停止 |
| `ctx.variables` | 直接访问变量字典 |
| `ctx.config` | 访问 AppConfig 对象（如果需要） |

### 变量替换

插件功能块应自己处理 `{{variable_name}}` 替换：

```python
def _resolve_variables(self, value, variables):
    """简单变量替换"""
    import re
    if not isinstance(value, str):
        return value
    return re.sub(r"\{\{(\w+)\}\}",
                  lambda m: str(variables.get(m.group(1), m.group(0))),
                  value)

def _exec_do_something(self, params, ctx):
    text = params.get("text", "")
    # 替换变量
    text = self._resolve_variables(text, ctx.variables)
    ctx.log(f"处理后的文本: {text}")
```

---

## 开发触发器

### 基础概念

触发器监控特定事件，当条件满足时触发任务执行。AutoFlow 内置支持 21 种触发器，插件可添加自定义触发器。

### 定义触发器

在 `get_triggers()` 方法中返回触发器定义列表：

```python
def get_triggers(self):
    return [
        {
            "type":           "my_plugin.custom_trigger",
            "label":          "自定义事件",
            "icon":           "🔔",
            "params": {
                "threshold": {
                    "type": "number",
                    "label": "阈值",
                    "default": 10
                }
            },
            "monitor_class":   MyCustomMonitor,  # TriggerMonitor 的子类
        }
    ]
```

### 实现 Monitor 类

自定义触发器需要实现 `TriggerMonitor` 的子类：

```python
from src.triggers.base import TriggerMonitor

class MyCustomMonitor(TriggerMonitor):
    def __init__(self, trigger_id, params):
        super().__init__(trigger_id, params)
        self.threshold = params.get("threshold", 10)

    def start(self):
        """启动监控"""
        # 初始化监控逻辑
        pass

    def stop(self):
        """停止监控"""
        # 清理资源
        pass

    def check(self):
        """检查是否满足触发条件"""
        # 返回 True 表示应该触发任务
        # 返回 (True, data) 可附加数据到任务变量
        return False
```

---

## 开发约束条件

约束条件（Condition）既可用于任务的「前置约束」（所有条件满足时任务才执行），也可用于 IF 功能块的判断逻辑。

### 定义约束条件

```python
def get_conditions(self):
    return [
        {
            "type":      "my_plugin.check_file_size",    # 全局唯一，建议带插件前缀
            "label":     "文件大小超过",
            "icon":      "📁",
            "params": {
                "path":      {"type": "string", "label": "文件路径"},
                "size_kb":   {"type": "number", "label": "大小（KB）", "default": 1024},
            },
            "evaluator": self._eval_file_size,    # Callable(params, ctx) -> bool
            "scope":     "both",   # "constraint"=仅用于约束, "if"=仅用于IF, "both"=两者
        }
    ]
```

### 实现评估函数

```python
def _eval_file_size(self, params, ctx):
    """返回 True 表示条件满足"""
    import os
    path = params.get("path", "")
    size_kb = params.get("size_kb", 1024)
    if not path or not os.path.exists(path):
        return False
    return os.path.getsize(path) / 1024 >= size_kb
```

---

## 注册全局快捷键

插件可注册全局快捷键（系统级，即使 AutoFlow 窗口不在前台也会响应），并在设置页的快捷键列表中自动显示，允许用户自定义。

### 定义快捷键

```python
def get_hotkeys(self):
    return [
        {
            "id":       "my_plugin.trigger_action",    # 全局唯一
            "label":    "触发我的动作",                 # 显示在设置→快捷键
            "default":  "ctrl+shift+x",                # 默认快捷键
            "callback": self._on_hotkey,               # 无参数回调（在主线程中调用）
        }
    ]

def _on_hotkey(self):
    import logging
    logging.getLogger("my_plugin").info("快捷键触发！")
```

> **注意**：`callback` 在主线程中调用，可以安全地操作 UI 或发出 Qt 信号。

---

## 添加设置 Tab

插件可在「设置」面板中添加独立的设置 Tab，适合有较多配置项的插件。

### 实现 get_settings_tab

```python
def get_settings_tab(self):
    """返回 (tab_title: str, widget: QWidget) 元组，或 None"""
    from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.addWidget(QLabel("API Key:"))
    self._key_edit = QLineEdit()
    self._key_edit.setPlaceholderText("输入你的 API Key")
    layout.addWidget(self._key_edit)
    layout.addStretch()
    return ("我的插件", widget)
```

> Tab 标题即为返回元组的第一个字符串，通常使用插件名称。

---

## 扩展菜单

### 功能块右键菜单

```python
def get_context_menu_items(self):
    return [
        {
            "id":       "my_plugin.export_block",
            "label":    "导出此功能块",
            "icon":     "📤",
            "callback": self._on_export_block,      # Callable(block_data: dict) -> None
            # 可选：仅对指定 block type 显示（省略则对所有块显示）
            "for_types": ["my_plugin.my_block"],
        }
    ]

def _on_export_block(self, block_data):
    import json
    print("导出功能块:", json.dumps(block_data, ensure_ascii=False))
```

### 系统托盘菜单

```python
def get_tray_menu_items(self):
    return [
        {
            "id":       "my_plugin.open_panel",
            "label":    "打开我的面板",
            "icon":     "🔌",
            "callback": self._on_open_panel,    # Callable() -> None
        }
    ]

def _on_open_panel(self):
    # 在主线程中弹出对话框
    self.open_dialog("我的面板", lambda parent: self._build_panel(parent))
```

### AutoFlowPlugin 基类

```python
class AutoFlowPlugin:
    # 元信息（应与 plugin.json 保持一致）
    id: str = ""
    name: str = ""
    version: str = "1.0.0"
    author: str = ""
    description: str = ""

    def on_load(self) -> None:
        """插件加载时调用"""
        pass

    def on_unload(self) -> None:
        """插件卸载时调用"""
        pass

    def get_blocks(self) -> List[Dict[str, Any]]:
        """返回功能块定义列表"""
        return []

    def get_triggers(self) -> List[Dict[str, Any]]:
        """返回触发器定义列表"""
        return []

    def get_conditions(self) -> List[Dict[str, Any]]:
        """返回约束条件/IF判断条件定义列表（v4.16.0+）"""
        return []

    def get_hotkeys(self) -> List[Dict[str, Any]]:
        """返回全局快捷键定义列表（v4.16.0+）"""
        return []

    def get_settings_widget(self) -> Optional[QWidget]:
        """返回插件内联设置区域（在插件管理页内显示）"""
        return None

    def get_settings_tab(self) -> Optional[Tuple[str, QWidget]]:
        """返回 (tab_title, widget)，在「设置」面板添加独立 Tab（v4.16.0+）"""
        return None

    def get_context_menu_items(self) -> List[Dict[str, Any]]:
        """返回功能块右键菜单扩展项（v4.16.0+）"""
        return []

    def get_tray_menu_items(self) -> List[Dict[str, Any]]:
        """返回系统托盘菜单扩展项（v4.16.0+）"""
        return []

    def open_dialog(self, title: str, widget_factory: Callable) -> Optional[int]:
        """便捷方法：在主线程弹出对话框（v4.16.0+）"""
        pass
```

### PluginRegistrationAPI

```python
class PluginRegistrationAPI:
    def register_plugin(self, plugin: AutoFlowPlugin) -> None:
        """注册插件实例"""
        pass

    def get_app_version(self) -> str:
        """获取 AutoFlow 版本"""
        pass

    def get_config(self) -> Optional[AppConfig]:
        """获取应用配置对象"""
        pass

    def log(self, message: str, level: str = "INFO") -> None:
        """写日志"""
        pass
```

### BlockExecutionContext

```python
class BlockExecutionContext:
    variables: Dict[str, Any]     # 任务变量字典

    def log(self, message: str, level: str = "INFO") -> None:
        """向日志面板写消息"""
        pass

    def is_stopped(self) -> bool:
        """检查是否要求停止任务"""
        pass

    def set_variable(self, name: str, value: Any) -> None:
        """设置变量"""
        pass

    def get_variable(self, name: str, default: Any = "") -> Any:
        """获取变量"""
        pass
```

---

## 示例代码

### 示例 1: 简单的文本处理插件

```python
def register(api):
    from src.plugin_api import AutoFlowPlugin

    class TextToolsPlugin(AutoFlowPlugin):
        id = "text_tools"
        name = "文本处理工具"
        version = "1.0.0"
        author = "你"
        description = "提供文本转换功能"

        def get_blocks(self):
            return [
                {
                    "type": "text_tools.uppercase",
                    "label": "转换为大写",
                    "category": "文本处理",
                    "color": "#2196F3",
                    "icon": "🔤",
                    "params": {
                        "text": {
                            "type": "string",
                            "label": "输入文本",
                            "default": "{{input_text}}",
                            "placeholder": "输入或选择变量"
                        },
                        "save_to": {
                            "type": "string",
                            "label": "保存到变量",
                            "default": "result"
                        }
                    },
                    "executor": self._exec_uppercase,
                }
            ]

        def _exec_uppercase(self, params, ctx):
            text = params.get("text", "")
            result = text.upper()
            save_to = params.get("save_to", "result")
            ctx.set_variable(save_to, result)
            ctx.log(f"文本已转换为大写: {result}")

    plugin = TextToolsPlugin()
    api.register_plugin(plugin)
```

### 示例 2: 带参数验证的功能块

```python
def _exec_multiply(self, params, ctx):
    try:
        a = float(params.get("a", 1))
        b = float(params.get("b", 1))
    except (ValueError, TypeError):
        ctx.log("参数必须是数字", "ERROR")
        return

    result = a * b
    ctx.set_variable("result", result)
    ctx.log(f"{a} × {b} = {result}")
```

### 示例 3: 异步操作（使用线程）

```python
import threading
import time

def _exec_delay_action(self, params, ctx):
    delay = int(params.get("delay", 1))
    message = params.get("message", "任务完成")

    def delayed_task():
        for i in range(delay):
            if ctx.is_stopped():
                ctx.log("任务已停止", "WARN")
                return
            time.sleep(1)
        ctx.log(message)
        ctx.set_variable("completed", True)

    thread = threading.Thread(target=delayed_task, daemon=True)
    thread.start()
```

### 示例 4: 调用第三方库（HTTP 请求）

```python
def register(api):
    try:
        import urllib.request
        import json
    except ImportError:
        api.log("缺少必要的标准库", "ERROR")
        return

    from src.plugin_api import AutoFlowPlugin

    class HttpPlugin(AutoFlowPlugin):
        id = "http_request"
        name = "HTTP 请求"
        version = "1.0.0"
        author = "AutoFlow Community"
        description = "发送 HTTP 请求"

        def get_blocks(self):
            return [
                {
                    "type": "http_request.get",
                    "label": "HTTP GET",
                    "category": "网络",
                    "color": "#FF9800",
                    "icon": "🌐",
                    "params": {
                        "url": {
                            "type": "string",
                            "label": "URL",
                            "placeholder": "https://api.example.com/data"
                        },
                        "save_to": {
                            "type": "string",
                            "label": "响应存入变量",
                            "default": "response"
                        }
                    },
                    "executor": self._exec_get,
                }
            ]

        def _exec_get(self, params, ctx):
            url = params.get("url", "")
            if not url:
                ctx.log("URL 不能为空", "ERROR")
                return
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "AutoFlow/4.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    body = resp.read().decode("utf-8")
                save_to = params.get("save_to", "response")
                ctx.set_variable(save_to, body)
                ctx.log(f"请求成功，响应长度: {len(body)} 字符")
            except Exception as e:
                ctx.log(f"请求失败: {e}", "ERROR")

    api.register_plugin(HttpPlugin())
```

---

## 测试与调试

### 1. 启用日志

```python
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("my_plugin")

def _exec_something(self, params, ctx):
    logger.debug(f"参数: {params}")
    ctx.log("调试信息")
```

### 2. 查看日志

打开 AutoFlow「运行日志」面板，可以看到所有插件输出的日志。

### 3. 测试步骤

1. 将插件文件夹放在 `%LOCALAPPDATA%\XinyuCraft\AutoFlow\plugins\`
2. 启动 AutoFlow（或重启）
3. 打开「设置」→「插件」，验证插件是否出现
4. 打开任务编辑器，功能块应该出现在对应分类中
5. 创建任务，使用你的功能块，查看日志输出

### 4. 常见问题排查

| 问题 | 排查方法 |
|------|----------|
| 插件不显示 | 检查 `plugin.json` 是否存在且格式正确 |
| 加载失败 | 查看日志中的错误信息；检查 `register(api)` 是否定义 |
| 功能块不出现 | 检查 `get_blocks()` 是否返回正确的列表 |
| 执行出错 | 在执行函数中添加详细日志，逐步调试 |
| 版本不兼容 | 检查 `min_app_version` 是否高于当前 AutoFlow 版本 |

---

## 打包与发布

### 标准目录结构

```
my_plugin/
  ├── plugin.json          # 必需
  ├── main.py              # 必需
  ├── icon.png             # 推荐（64×64 PNG）
  ├── README.md            # 推荐
  ├── LICENSE              # 推荐（MIT / Apache 2.0）
  ├── utils.py             # 可选
  ├── config.json          # 可选
  └── assets/              # 可选
      └── images/
```

### 发布建议

1. **开源分享**: 在 GitHub 创建仓库，使用 MIT/Apache 2.0 等开源协议
2. **编写文档**: 详细说明插件功能、安装方法、使用示例
3. **测试覆盖**: 确保功能块在各种参数下都正常工作
4. **版本管理**: 遵循语义化版本，在 `plugin.json` 中更新版本

---

## 发布到插件市场

AutoFlow 内置了插件市场（v4.9.0+），你可以将插件提交到社区仓库，让所有用户一键安装。

### 提交流程

1. **Fork** [autoflow-plugins 仓库](https://github.com/XinyuCraft-XYHC/autoflow-plugins)
2. 将插件目录放入 `plugins/<your_plugin_id>/`，包含完整文件
3. 在 `index.json` 中添加你的插件条目：

```json
{
  "id": "your_plugin_id",
  "name": "插件名称",
  "name_en": "Plugin Name",
  "version": "1.0.0",
  "author": "你的名字",
  "description": "功能描述（中文）",
  "description_en": "Description (English)",
  "tags": ["标签"],
  "download_url": "https://github.com/XinyuCraft-XYHC/autoflow-plugins/archive/refs/heads/master.zip",
  "plugin_dir_in_zip": "autoflow-plugins-master/plugins/your_plugin_id",
  "updated": "2026-03-30",
  "stars": 0,
  "downloads": 0,
  "verified": false,
  "min_autoflow_version": "4.0.0",
  "repository": "https://github.com/你/你的仓库",
  "issues_url": "https://github.com/你/你的仓库/issues"
}
```

4. 提交 Pull Request，等待官方审核
5. 审核通过后 `verified` 字段会被设为 `true`，插件将在市场中显示官方认证标记

### 审核标准

官方审核主要检查：
- 插件功能描述与实际一致
- 没有恶意代码或安全风险
- `plugin.json` 格式正确，字段完整
- 有清晰的 README 说明

### 下载 URL 说明

若插件放在 `autoflow-plugins` 仓库的 `plugins/` 目录下，`download_url` 填仓库 ZIP 地址即可，AutoFlow 会自动从 ZIP 中提取 `plugin_dir_in_zip` 指定的目录。

若插件有独立仓库，`download_url` 填你自己仓库的 ZIP 地址，并相应调整 `plugin_dir_in_zip`。

---

## API 版本兼容性

| 能力 | 最低版本 | 对应方法 |
|------|---------|---------|
| 功能块 | v4.0.0 | `get_blocks()` |
| 触发器 | v4.0.0 | `get_triggers()` |
| 内联设置区域 | v4.0.0 | `get_settings_widget()` |
| 约束条件 / IF 条件 | v4.16.0 | `get_conditions()` |
| 全局快捷键 | v4.16.0 | `get_hotkeys()` |
| 设置面板 Tab | v4.16.0 | `get_settings_tab()` |
| 功能块右键菜单 | v4.16.0 | `get_context_menu_items()` |
| 托盘菜单 | v4.16.0 | `get_tray_menu_items()` |
| 弹出对话框 | v4.16.0 | `open_dialog()` |

---

## 常见问题

### Q: 如何在插件中使用第三方库？

A: 直接在代码中导入即可。如果依赖库不是 Python 标准库，建议在 README 中提示用户安装依赖：

```bash
pip install requests
```

或者在 `main.py` 中自动检查并提示：

```python
def register(api):
    try:
        import requests
    except ImportError:
        api.log("需要安装 requests: pip install requests", "ERROR")
        return
    # ... 插件代码
```

### Q: 如何访问应用配置（如 AI 设置）？

A: 使用 `ctx.config` 或 `api.get_config()` 获取 `AppConfig` 对象：

```python
def _exec_something(self, params, ctx):
    config = ctx.config
    if config:
        ai_key = config.ai_api_key
        ai_model = config.ai_model
```

### Q: 功能块之间如何通信？

A: 通过任务变量 (`ctx.variables`) 传递数据：

```python
# 功能块 A：计算并保存结果
ctx.set_variable("temp_data", result)

# 功能块 B：读取结果并处理
data = ctx.get_variable("temp_data")
```

### Q: 如何调用其他功能块？

A: 目前不支持直接调用其他功能块。建议将共用逻辑提取到独立函数或类中。

### Q: 插件可以保存状态吗？

A: 可以。建议使用 JSON 文件保存持久化状态：

```python
import json, os

config_dir = os.path.join(os.environ["LOCALAPPDATA"], "XinyuCraft", "AutoFlow", "plugins", "my_plugin")
config_file = os.path.join(config_dir, "state.json")

def save_state(data):
    os.makedirs(config_dir, exist_ok=True)
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(data, f)

def load_state():
    if os.path.exists(config_file):
        with open(config_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}
```

### Q: 如何处理长时间运行的操作而不阻塞 UI？

A: 使用多线程：

```python
import threading, time

def _exec_long_task(self, params, ctx):
    def background_work():
        for i in range(100):
            if ctx.is_stopped():
                return
            ctx.log(f"进度: {i}%")
            time.sleep(0.1)
        ctx.set_variable("done", True)

    thread = threading.Thread(target=background_work, daemon=True)
    thread.start()
```

### Q: 如何确保插件兼容多个 AutoFlow 版本？

A: 在 `plugin.json` 中设置 `min_app_version`，并在代码中条件性地使用新特性：

```python
def register(api):
    version = api.get_app_version()
    if version >= "4.0.0":
        # 使用 4.0+ 的新功能
        pass
    else:
        # 降级处理
        pass
```

---

## 更多资源

- **社区插件仓库**: [autoflow-plugins](https://github.com/XinyuCraft-XYHC/autoflow-plugins)（提交你的插件）
- **官方示例**: 参考 `plugins/example_tools/` 目录中的示例插件
- **源码参考**: 查看 `src/plugin_api.py` 和 `src/plugin_manager.py`
- **GitHub**: [AutoFlow 官方仓库](https://github.com/XinyuCraft-XYHC/autoflow-windows)
- **问题反馈**: [Issue Tracker](https://github.com/XinyuCraft-XYHC/autoflow-windows/issues)

---

## 许可证

AutoFlow 本体使用 BSL 1.1 协议。插件可选择合适的开源协议（MIT、Apache 2.0、GPL 等）。

"""
示例工具包 (example_tools) — AutoFlow 插件示例
提供三个功能块：
  1. example_tools.random_number  随机整数
  2. example_tools.text_process   文本处理（大写/小写/反转/去空格）
  3. example_tools.json_get       HTTP GET 并解析 JSON 字段

开发者可参照此文件开发自己的插件。
"""
import random
import json
import urllib.request


def register(api):
    """AutoFlow 调用此函数完成插件注册"""
    # 延迟导入 AutoFlowPlugin（由宿主程序的 sys.path 提供）
    from src.plugin_api import AutoFlowPlugin

    class ExampleToolsPlugin(AutoFlowPlugin):
        id          = "example_tools"
        name        = "示例工具包"
        version     = "1.0.0"
        author      = "AutoFlow Team"
        description = "展示插件 API 的用法"

        def get_blocks(self):
            return [
                # ── 随机整数 ──
                {
                    "type":     "example_tools.random_number",
                    "label":    "随机整数",
                    "category": "示例工具",
                    "color":    "#8B5CF6",
                    "icon":     "🎲",
                    "params": {
                        "min": {
                            "type": "number_or_var", "label": "最小值",
                            "default": 1, "placeholder": "整数或变量"
                        },
                        "max": {
                            "type": "number_or_var", "label": "最大值",
                            "default": 100, "placeholder": "整数或变量"
                        },
                        "save_to": {
                            "type": "string", "label": "保存到变量",
                            "default": "random_result", "placeholder": "变量名"
                        },
                    },
                    "executor": self._exec_random_number,
                },
                # ── 文本处理 ──
                {
                    "type":     "example_tools.text_process",
                    "label":    "文本处理",
                    "category": "示例工具",
                    "color":    "#06B6D4",
                    "icon":     "✂️",
                    "params": {
                        "text": {
                            "type": "string", "label": "输入文本",
                            "default": "{{my_var}}", "placeholder": "文本或 {{变量名}}"
                        },
                        "operation": {
                            "type": "select", "label": "操作",
                            "default": "upper",
                            "options": ["upper", "lower", "reverse", "strip", "len"],
                            "option_labels": ["转大写", "转小写", "反转", "去空格", "求长度"],
                        },
                        "save_to": {
                            "type": "string", "label": "保存到变量",
                            "default": "text_result", "placeholder": "变量名"
                        },
                    },
                    "executor": self._exec_text_process,
                },
                # ── HTTP GET + JSON ──
                {
                    "type":     "example_tools.json_get",
                    "label":    "HTTP GET JSON",
                    "category": "示例工具",
                    "color":    "#10B981",
                    "icon":     "🌐",
                    "params": {
                        "url": {
                            "type": "string", "label": "URL",
                            "default": "https://api.ipify.org?format=json",
                            "placeholder": "https://..."
                        },
                        "json_path": {
                            "type": "string", "label": "JSON 字段路径",
                            "default": "ip",
                            "placeholder": "例: data.user.name（空则保存全部）"
                        },
                        "save_to": {
                            "type": "string", "label": "保存到变量",
                            "default": "http_result", "placeholder": "变量名"
                        },
                        "timeout": {
                            "type": "number_or_var", "label": "超时(秒)",
                            "default": 10
                        },
                    },
                    "executor": self._exec_json_get,
                },
            ]

        # ── 执行函数 ──

        def _resolve(self, val, variables):
            """简单变量替换（插件内不依赖宿主 resolve_value）"""
            import re
            if not isinstance(val, str):
                return val
            return re.sub(r"\{\{(\w+)\}\}",
                          lambda m: str(variables.get(m.group(1), m.group(0))),
                          val)

        def _resolve_num(self, val, variables):
            try:
                return float(self._resolve(str(val), variables))
            except Exception:
                return 0.0

        def _exec_random_number(self, params, ctx):
            lo = int(self._resolve_num(params.get("min", 1), ctx.variables))
            hi = int(self._resolve_num(params.get("max", 100), ctx.variables))
            if lo > hi:
                lo, hi = hi, lo
            result = random.randint(lo, hi)
            save_to = params.get("save_to", "random_result") or "random_result"
            ctx.set_variable(save_to, result)
            ctx.log(f"随机整数 [{lo}, {hi}] → {result}，已保存到 {save_to}")

        def _exec_text_process(self, params, ctx):
            text    = self._resolve(params.get("text", ""), ctx.variables)
            op      = params.get("operation", "upper")
            if   op == "upper":   result = text.upper()
            elif op == "lower":   result = text.lower()
            elif op == "reverse": result = text[::-1]
            elif op == "strip":   result = text.strip()
            elif op == "len":     result = len(text)
            else:                 result = text
            save_to = params.get("save_to", "text_result") or "text_result"
            ctx.set_variable(save_to, result)
            ctx.log(f"文本处理 [{op}]: '{str(text)[:30]}' → '{result}'")

        def _exec_json_get(self, params, ctx):
            url     = self._resolve(params.get("url", ""), ctx.variables)
            path    = self._resolve(params.get("json_path", ""), ctx.variables).strip()
            save_to = params.get("save_to", "http_result") or "http_result"
            timeout = int(self._resolve_num(params.get("timeout", 10), ctx.variables))

            if not url:
                ctx.log("HTTP GET JSON: URL 为空", "WARN")
                return
            try:
                ctx.log(f"HTTP GET: {url}")
                req = urllib.request.Request(url, headers={"User-Agent": "AutoFlow/2.7"})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                if path:
                    val = data
                    for k in path.split("."):
                        if isinstance(val, dict):
                            val = val.get(k)
                        elif isinstance(val, list):
                            try:
                                val = val[int(k)]
                            except Exception:
                                val = None
                        else:
                            val = None
                    result = val
                else:
                    result = json.dumps(data, ensure_ascii=False)
                ctx.set_variable(save_to, result)
                ctx.log(f"HTTP GET 成功 → 已保存到 {save_to}")
            except Exception as e:
                ctx.log(f"HTTP GET 失败: {e}", "ERROR")
                ctx.set_variable(save_to, f"[错误] {e}")

    plugin = ExampleToolsPlugin()
    api.register_plugin(plugin)


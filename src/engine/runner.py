"""
任务执行引擎
支持：变量替换、条件判断、循环、所有功能块执行
"""
import os
import re
import sys
import time
import shutil
import fnmatch
import logging
import subprocess
import threading
from typing import Any, Dict, List, Optional

import psutil

from .models import Block, Task, AppConfig, Constraint

logger = logging.getLogger("autoflow.engine")


def _make_title_re(title: str) -> str:
    """将支持 * 通配符的窗口标题转为 pywinauto 的 title_re 正则表达式"""
    import re as _re
    if "*" in title:
        return _re.escape(title).replace(r"\*", ".*")
    # 精确匹配（pywinauto title_re 默认是部分匹配，加 ^ $ 精确）
    return "^" + _re.escape(title) + "$"




class StopTaskException(Exception):
    pass

class BreakLoopException(Exception):
    pass


def resolve_value(value: Any, variables: Dict[str, Any]) -> str:
    """将 {{var}} 替换为变量值"""
    if not isinstance(value, str):
        return value
    def replace(m):
        key = m.group(1).strip()
        return str(variables.get(key, m.group(0)))
    return re.sub(r"\{\{(\w+)\}\}", replace, value)


def resolve_number(value: Any, variables: Dict[str, Any]) -> float:
    v = resolve_value(str(value), variables)
    try:
        return float(v)
    except Exception:
        return 0.0


class TaskRunner(threading.Thread):
    """在独立线程中运行一个任务"""

    def __init__(self, task: Task, config: AppConfig,
                 global_variables: Dict[str, Any],
                 on_log=None, on_finished=None,
                 run_task_fn=None, stop_task_fn=None,
                 is_task_running_fn=None, all_tasks_fn=None):
        super().__init__(daemon=True)
        self.task = task
        self.config = config
        self._stop_event = threading.Event()
        # 变量空间：全局 → 任务默认 → 运行时
        self.variables: Dict[str, Any] = {}
        self.variables.update(self._coerce_vars(global_variables))
        self.variables.update(self._coerce_vars(task.variables))
        self.on_log = on_log or (lambda level, msg: None)
        self.on_finished = on_finished or (lambda task_id, success: None)
        # 任务间联动回调（由 MainWindow 传入）
        self._run_task_fn      = run_task_fn         # fn(task_id) -> None
        self._stop_task_fn     = stop_task_fn        # fn(task_id) -> None
        self._is_task_running  = is_task_running_fn  # fn(task_id) -> bool
        self._all_tasks_fn     = all_tasks_fn        # fn() -> List[Task]

    @staticmethod
    def _coerce_vars(var_dict: dict) -> dict:
        """将变量字典转为运行时值字典，支持新格式 {name: {value, type}} 和旧格式 {name: value}"""
        import json as _json
        result = {}
        for name, raw in (var_dict or {}).items():
            if isinstance(raw, dict) and "value" in raw:
                val = raw.get("value", "")
                vtype = raw.get("type", "string")
            else:
                val = raw
                vtype = "string"
            # 类型转换
            val_str = str(val) if val is not None else ""
            if vtype == "number":
                try:
                    result[name] = float(val_str) if '.' in val_str else int(val_str)
                except (ValueError, TypeError):
                    result[name] = val_str
            elif vtype == "bool":
                result[name] = val_str.lower() in ("1", "true", "yes", "是", "true")
            elif vtype == "list":
                try:
                    parsed = _json.loads(val_str)
                    result[name] = parsed if isinstance(parsed, list) else [val_str]
                except Exception:
                    result[name] = [v.strip() for v in val_str.split(',') if v.strip()]
            else:
                result[name] = val_str
        return result

    def stop(self):
        self._stop_event.set()

    def _log(self, level: str, msg: str):
        logger.log(getattr(logging, level, logging.INFO), "[%s] %s", self.task.name, msg)

    def run(self):
        try:
            self._log("INFO", "▶ 任务开始执行")
            self._run_blocks(self.task.blocks)
            self._log("INFO", "✅ 任务执行完毕")
            self.on_finished(self.task.id, True)
        except StopTaskException:
            self._log("INFO", "🛑 任务被停止")
            self.on_finished(self.task.id, False)
        except Exception as e:
            self._log("ERROR", f"❌ 任务异常: {e}")
            self.on_finished(self.task.id, False)

    def _check_stop(self):
        if self._stop_event.is_set():
            raise StopTaskException()


    def _run_blocks(self, blocks: List[Block]):
        """执行块列表，支持 loop/loop_end / if_block/if_end 扁平配对模式"""
        i = 0
        while i < len(blocks):
            self._check_stop()
            block = blocks[i]
            if not block.enabled:
                i += 1
                continue

            if block.block_type == "if_block":
                # ── 扁平 if/elif/else/if_end 结构 ──
                # 找对应的 if_end（支持 if 嵌套）
                depth = 1
                end_idx = i + 1
                while end_idx < len(blocks) and depth > 0:
                    if blocks[end_idx].block_type == "if_block":
                        depth += 1
                    elif blocks[end_idx].block_type == "if_end":
                        depth -= 1
                    if depth > 0:
                        end_idx += 1
                    else:
                        break

                # 收集 if/elif/else 各分支（只处理最外层，不处理嵌套内部的 elif/else）
                # 分段：inner = blocks[i+1 .. end_idx-1]
                inner = blocks[i + 1: end_idx]
                # 按最外层的 elif_block / else_block 切分
                branches = []  # [(header_block_or_None, [body_blocks])]
                cur_header = block       # if_block
                cur_body   = []
                inner_depth = 0
                for b in inner:
                    if b.block_type == "if_block":
                        inner_depth += 1
                        cur_body.append(b)
                    elif b.block_type == "if_end":
                        inner_depth -= 1
                        cur_body.append(b)
                    elif inner_depth == 0 and b.block_type in ("elif_block", "else_block"):
                        branches.append((cur_header, cur_body))
                        cur_header = b
                        cur_body   = []
                    else:
                        cur_body.append(b)
                branches.append((cur_header, cur_body))

                # 按顺序执行第一个满足条件的分支
                executed = False
                for hdr, body in branches:
                    if hdr.block_type == "else_block":
                        if not executed:
                            self._log("INFO", "    [else] 执行 else 分支")
                            self._run_blocks(body)
                        break
                    else:
                        # if_block 或 elif_block
                        result = self._eval_condition(hdr.params)
                        if hdr.params.get("negate", False):
                            result = not result
                        ctype = hdr.params.get("condition_type", "?")
                        kw    = "if" if hdr.block_type == "if_block" else "elif"
                        self._log("INFO", f"    [{kw}] {ctype} => {result}")
                        if result and not executed:
                            executed = True
                            self._run_blocks(body)
                i = end_idx + 1  # 跳过 if_end

            elif block.block_type in ("elif_block", "else_block", "if_end"):
                # 孤立标记，跳过
                i += 1

            elif block.block_type == "loop":
                # 找对应的 loop_end（支持嵌套计数）
                depth = 1
                end_idx = i + 1
                while end_idx < len(blocks) and depth > 0:
                    if blocks[end_idx].block_type == "loop":
                        depth += 1
                    elif blocks[end_idx].block_type == "loop_end":
                        depth -= 1
                    if depth > 0:
                        end_idx += 1
                    else:
                        break

                # 循环体 = i+1 到 end_idx-1
                loop_body = blocks[i + 1: end_idx]
                try:
                    self._run_loop_flat(block, loop_body)
                except BreakLoopException:
                    pass  # break 跳出循环，继续 loop_end 之后
                i = end_idx + 1  # 跳过 loop_end

            elif block.block_type == "loop_end":
                # 孤立的 loop_end（没有配对的 loop），跳过
                i += 1

            elif block.block_type == "group":
                # 折叠块：结构性标记，运行时透明执行——找到对应 group_end 后直接执行内部块
                depth = 1
                end_idx = i + 1
                while end_idx < len(blocks) and depth > 0:
                    if blocks[end_idx].block_type == "group":
                        depth += 1
                    elif blocks[end_idx].block_type == "group_end":
                        depth -= 1
                    if depth > 0:
                        end_idx += 1
                    else:
                        break
                group_body = blocks[i + 1: end_idx]
                title = block.params.get("title", "折叠块")
                self._log("INFO", f"    >> 进入折叠块: {title}")
                self._run_blocks(group_body)
                self._log("INFO", f"    << 离开折叠块: {title}")
                i = end_idx + 1  # 跳过 group_end

            elif block.block_type == "group_end":
                # 孤立的 group_end，跳过
                i += 1

            else:
                try:
                    self._execute_block(block)
                except BreakLoopException:
                    raise  # 传给上层 loop 处理
                i += 1

    def _execute_block(self, block: Block):
        self._check_stop()
        p = block.params
        bt = block.block_type
        self._log("INFO", f"  ⚡ 执行块: {bt} " + (f"({block.comment})" if block.comment else ""))

        # ── 约束条件检查 ──
        if block.constraints:
            if not self._check_constraints(block.constraints, f"块[{bt}]"):
                self._log("INFO", f"  ⏭ 约束条件不满足，跳过块: {bt}")
                return

        if bt == "wait":
            secs = resolve_number(p.get("duration", 1), self.variables)
            self._log("INFO", f"    等待 {secs} 秒")
            end = time.time() + secs
            while time.time() < end:
                self._check_stop()
                time.sleep(0.2)

        elif bt == "condition":
            result = self._eval_condition(p)
            if p.get("negate", False):
                result = not result
            self._log("INFO", f"    条件结果: {result}")
            if result:
                self._run_blocks(block.children_true)
            else:
                on_false = p.get("on_false", "skip")
                if on_false == "stop_task":
                    raise StopTaskException()
                elif on_false == "skip":
                    pass
                self._run_blocks(block.children_false)

        elif bt == "loop":
            # 扁平模式：由 _run_blocks 的 loop/loop_end 配对逻辑处理
            # 兼容旧的 children_loop 嵌套模式
            if block.children_loop:
                self._run_loop(block)
            # 否则什么都不做（由 _run_blocks 层面的 loop/loop_end 配对处理）

        elif bt == "loop_end":
            pass  # 由 _run_blocks 的 loop 配对逻辑跳过

        elif bt in ("if_block", "elif_block", "else_block", "if_end"):
            pass  # 由 _run_blocks 的 if_block/if_end 配对逻辑处理

        elif bt == "group":
            pass  # 由 _run_blocks 的 group 配对逻辑处理

        elif bt == "group_end":
            pass  # 由 _run_blocks 的 group 配对逻辑跳过

        elif bt == "break":
            raise BreakLoopException()

        elif bt == "stop_task":
            raise StopTaskException()

        elif bt == "launch_app":
            path     = resolve_value(p.get("path", ""), self.variables).strip()
            args     = resolve_value(p.get("args", ""), self.variables).strip()
            cwd      = resolve_value(p.get("cwd", ""), self.variables).strip() or None
            run_mode = p.get("run_mode", "normal")
            as_admin = p.get("as_admin", False)
            wait     = p.get("wait", False)
            timeout  = float(resolve_number(p.get("timeout", 0), self.variables))
            save_pid = p.get("save_pid", "").strip()
            self._log("INFO", f"    打开: {path} {args}")
            self._launch_app(path, args, cwd, run_mode, as_admin, wait, timeout, save_pid)

        elif bt == "close_window":
            match_mode = p.get("match_mode", "title")
            force = p.get("force", False)
            if match_mode == "hwnd":
                hwnd_str = resolve_value(p.get("hwnd", ""), self.variables)
                self._close_window_by_hwnd(hwnd_str, force)
            elif match_mode == "process":
                proc_name = resolve_value(p.get("process", ""), self.variables)
                self._close_window_by_process(proc_name, force)
            else:
                title = resolve_value(p.get("title", ""), self.variables)
                self._close_window(title, force)

        elif bt == "close_foreground_window":
            title = resolve_value(p.get("title", ""), self.variables)
            self._close_foreground_window(title)

        elif bt == "kill_process":
            match_mode = p.get("match_mode", "name")
            if match_mode == "pid":
                pid_str = resolve_value(p.get("pid", ""), self.variables)
                self._kill_process_by_pid(pid_str)
            elif match_mode == "window_title":
                wt = resolve_value(p.get("window_title", ""), self.variables)
                self._kill_process_by_window(wt)
            else:
                name = resolve_value(p.get("name", ""), self.variables)
                self._kill_process(name)

        elif bt == "wait_window":
            match_mode = p.get("match_mode", "title")
            timeout    = resolve_number(p.get("timeout", 30), self.variables)
            on_to      = p.get("on_timeout", "continue")
            if match_mode == "hwnd":
                hwnd_str = resolve_value(p.get("hwnd", ""), self.variables)
                found = self._wait_window_hwnd(hwnd_str, timeout)
            elif match_mode == "process":
                proc_name = resolve_value(p.get("process", ""), self.variables)
                found = self._wait_window_process(proc_name, timeout)
            else:
                title = resolve_value(p.get("title", ""), self.variables)
                found = self._wait_window(title, timeout)
            if not found and on_to == "stop_task":
                raise StopTaskException()

        elif bt == "wait_process":
            match_mode = p.get("match_mode", "name")
            timeout    = resolve_number(p.get("timeout", 30), self.variables)
            on_to      = p.get("on_timeout", "continue")
            if match_mode == "pid":
                pid_str = resolve_value(p.get("pid", ""), self.variables)
                found = self._wait_process_pid(pid_str, timeout)
            else:
                name  = resolve_value(p.get("name", ""), self.variables)
                found = self._wait_process(name, timeout)
            if not found and on_to == "stop_task":
                raise StopTaskException()

        elif bt == "run_command":
            cmd      = resolve_value(p.get("command", ""), self.variables)
            shell    = p.get("shell", "cmd")
            wait     = p.get("wait", True)
            save_out = p.get("save_output", "")
            as_admin = p.get("as_admin", False)
            self._run_command(cmd, shell, wait, save_out, as_admin=as_admin)

        elif bt == "copy_file":
            src = resolve_value(p.get("src", ""), self.variables)
            dst = resolve_value(p.get("dst", ""), self.variables)
            overwrite = p.get("overwrite", True)
            self._log("INFO", f"    复制: {src} → {dst}")
            if os.path.isdir(src):
                if os.path.exists(dst) and overwrite:
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else:
                if overwrite or not os.path.exists(dst):
                    shutil.copy2(src, dst)

        elif bt == "move_file":
            src = resolve_value(p.get("src", ""), self.variables)
            dst = resolve_value(p.get("dst", ""), self.variables)
            self._log("INFO", f"    移动: {src} → {dst}")
            shutil.move(src, dst)

        elif bt == "delete_file":
            path = resolve_value(p.get("path", ""), self.variables)
            confirm = p.get("confirm", True)
            self._log("INFO", f"    删除: {path}")
            if not confirm or self._confirm_action(f"确认删除: {path}?"):
                if os.path.isdir(path):
                    shutil.rmtree(path)
                elif os.path.exists(path):
                    os.remove(path)

        elif bt == "read_file":
            path    = resolve_value(p.get("path", ""), self.variables)
            enc     = p.get("encoding", "utf-8")
            save_to = p.get("save_to", "file_content")
            with open(path, "r", encoding=enc) as f:
                content = f.read()
            self.variables[save_to] = content
            self._log("INFO", f"    已读取文件到变量 {save_to}")

        elif bt == "write_file":
            path    = resolve_value(p.get("path", ""), self.variables)
            content = resolve_value(p.get("content", ""), self.variables)
            mode    = "a" if p.get("mode") == "append" else "w"
            enc     = p.get("encoding", "utf-8")
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, mode, encoding=enc) as f:
                f.write(content)
            self._log("INFO", f"    已写入文件: {path}")

        elif bt == "wait_file":
            path    = resolve_value(p.get("path", ""), self.variables)
            event   = p.get("event", "any")
            timeout = resolve_number(p.get("timeout", 60), self.variables)
            self._wait_file_change(path, event, timeout)

        elif bt == "set_variable":
            name  = p.get("name", "")
            value = resolve_value(p.get("value", ""), self.variables)
            vtype = p.get("type", "string")
            if vtype == "number":
                try:
                    value = float(value)
                    if value == int(value):
                        value = int(value)
                except Exception:
                    pass
            elif vtype == "bool":
                value = value.lower() in ("1", "true", "yes")
            self.variables[name] = value
            self._log("INFO", f"    变量 {name} = {value}")

        elif bt == "calc_variable":
            name = p.get("name", "result")
            expr = resolve_value(p.get("expression", "0"), self.variables)
            try:
                result = eval(expr, {"__builtins__": {}}, self.variables)
                self.variables[name] = result
                self._log("INFO", f"    {name} = {result}")
            except Exception as e:
                self._log("WARN", f"    计算失败: {e}")

        elif bt == "show_variable":
            name = p.get("name", "")
            val  = self.variables.get(name, "(未定义)")
            self._log("INFO", f"    变量 {name} = {val}")

        elif bt == "media_play":
            self._send_media_key("play_pause")
        elif bt == "media_next":
            self._send_media_key("next_track")
        elif bt == "media_prev":
            self._send_media_key("prev_track")
        elif bt == "volume_set":
            level       = int(resolve_number(p.get("level", 50), self.variables))
            target      = resolve_value(p.get("target", ""), self.variables).strip()
            target_type = p.get("target_type", "global")
            self._set_volume(level, target=target, target_type=target_type)

        elif bt == "notify":
            title   = resolve_value(p.get("title", "AutoFlow"), self.variables)
            message = resolve_value(p.get("message", ""), self.variables)
            timeout = int(resolve_number(p.get("timeout", 5), self.variables))
            self._show_notification(title, message, timeout)

        elif bt == "send_email":
            to      = resolve_value(p.get("to", ""), self.variables)
            subject = resolve_value(p.get("subject", ""), self.variables)
            body    = resolve_value(p.get("body", ""), self.variables)
            self._send_email(to, subject, body)

        elif bt == "log_message":
            message = resolve_value(p.get("message", ""), self.variables)
            level   = p.get("level", "INFO")
            self._log(level, f"    📝 {message}")

        elif bt == "shutdown":
            action  = p.get("action", "shutdown")
            delay   = int(resolve_number(p.get("delay", 0), self.variables))
            confirm = p.get("confirm", True)
            if not confirm or self._confirm_action(f"确认执行: {action}?"):
                self._system_action(action, delay)

        elif bt == "screenshot":
            mode       = p.get("mode", "save_file")
            save_dir   = resolve_value(p.get("save_path", ""), self.variables)
            name_fmt   = p.get("filename_fmt", "screenshot_{datetime}")
            fmt        = p.get("format", "png")
            region     = p.get("region", "fullscreen")
            self._take_screenshot(mode, save_dir, name_fmt, fmt, region)

        elif bt == "clipboard":
            action  = p.get("action", "get")
            content = resolve_value(p.get("content", ""), self.variables)
            save_to = p.get("save_to", "clipboard_text")
            self._clipboard_op(action, content, save_to)

        elif bt == "keyboard":
            keys = resolve_value(p.get("keys", ""), self.variables)
            self._send_keys(keys)

        elif bt == "hotkey_input":
            key     = p.get("key", "enter")
            repeat  = int(resolve_number(p.get("repeat", 1), self.variables))
            delay_ms = resolve_number(p.get("delay_ms", 50), self.variables)
            self._log("INFO", f"    [hotkey_input] 按键: {key} × {repeat}")
            for _ in range(max(1, repeat)):
                self._send_keys(key)
                if delay_ms > 0:
                    time.sleep(delay_ms / 1000.0)
                self._check_stop()

        elif bt == "capslock":
            action  = p.get("action", "toggle")
            save_to = p.get("save_to", "capslock_state")
            self._capslock_op(action, save_to)

        elif bt == "http_request":
            url     = resolve_value(p.get("url", ""), self.variables)
            method  = p.get("method", "GET")
            headers = p.get("headers", "{}")
            body_s  = resolve_value(p.get("body", ""), self.variables)
            save_to = p.get("save_to", "http_resp")
            self._http_request(url, method, headers, body_s, save_to)

        elif bt == "msgbox":
            text    = resolve_value(p.get("text", ""), self.variables)
            title   = resolve_value(p.get("title", "AutoFlow"), self.variables)
            buttons = p.get("buttons", "ok")
            icon    = p.get("icon", "info")
            save_to = p.get("save_to", "msgbox_result")
            self._msgbox(title, text, buttons, icon, save_to)

        elif bt == "play_sound":
            path_ = resolve_value(p.get("path", ""), self.variables)
            wait  = p.get("wait", False)
            self._play_sound(path_, wait)

        elif bt == "write_clipboard":
            content = resolve_value(p.get("content", ""), self.variables)
            self._clipboard_op("set", content, "")

        elif bt == "input_text":
            text  = resolve_value(p.get("text", ""), self.variables)
            delay = resolve_number(p.get("delay", 0), self.variables)
            self._input_text(text, delay)

        elif bt == "open_url":
            url     = resolve_value(p.get("url", ""), self.variables)
            browser = p.get("browser", "default")
            self._open_url(url, browser)

        elif bt == "exec_command":
            cmd      = resolve_value(p.get("command", ""), self.variables)
            shell    = p.get("shell", "cmd")
            as_admin = p.get("as_admin", False)
            wait     = p.get("wait", True)
            # 兼容旧版 hidden 字段；新版用 run_mode
            run_mode = p.get("run_mode", "hidden" if p.get("hidden", False) else "normal")
            hidden   = (run_mode == "hidden")
            save_out = p.get("save_output", "")

            # ── AI 生成命令 ──
            if p.get("ai_generate_cmd", False):
                ai_desc = resolve_value(p.get("ai_cmd_desc", ""), self.variables)
                if ai_desc.strip():
                    self._log("INFO", f"    [AI] 根据描述生成 {shell} 命令…")
                    _shell_name = {"cmd": "CMD", "powershell": "PowerShell",
                                   "bat": "批处理(.bat)", "python": "Python",
                                   "bash": "Bash"}.get(shell, shell)
                    _ai_prompt = (
                        f"请生成一段 {_shell_name} 命令/脚本，用于完成以下任务：\n{ai_desc}\n\n"
                        "要求：\n"
                        "1. 只输出命令/脚本本身，不要任何解释\n"
                        "2. 不要使用 markdown 代码块\n"
                        "3. 命令要安全、简洁、可直接执行"
                    )
                    _save_var = "__ai_cmd_tmp__"
                    self._ai_call(_ai_prompt, "", "", _save_var, 30, 0.1,
                                  False, "", "ai_generate")
                    generated = self.variables.get(_save_var, "").strip()
                    if generated and not generated.startswith("[错误]"):
                        cmd = generated
                        self._log("INFO", f"    [AI] 生成命令: {cmd[:80]}{'...' if len(cmd)>80 else ''}")
                    else:
                        self._log("WARN", f"    [AI] 命令生成失败，使用原始命令")

            self._run_command(cmd, shell, wait, save_out, as_admin=as_admin, hidden=hidden)

        elif bt == "turn_off_display":
            delay_sec = resolve_number(p.get("delay_sec", 0), self.variables)
            self._turn_off_display(delay_sec)

        elif bt == "get_ping_latency":
            host    = resolve_value(p.get("host", "8.8.8.8"), self.variables)
            count   = int(resolve_number(p.get("count", 1), self.variables))
            save_to = p.get("save_to", "ping_ms")
            latency = self._get_ping_latency_ms(host, count)
            result  = latency if latency is not None else -1
            self.variables[save_to] = result
            if latency is not None:
                self._log("INFO", f"    Ping {host}: {latency:.0f}ms → 存入 {save_to}")
            else:
                self._log("INFO", f"    Ping {host}: 超时/不可达 → {save_to} = -1")

        elif bt == "run_other_task":
            other_id = p.get("task_id", "")
            wait     = p.get("wait", False)
            timeout  = resolve_number(p.get("timeout", 0), self.variables)
            self._run_other_task(other_id, wait, timeout)

        elif bt == "stop_other_task":
            other_id = p.get("task_id", "")
            self._stop_other_task(other_id)

        elif bt == "wait_task_done":
            other_id   = p.get("task_id", "")
            timeout    = resolve_number(p.get("timeout", 60), self.variables)
            on_timeout = p.get("on_timeout", "continue")
            self._wait_task_done(other_id, timeout, on_timeout)

        elif bt == "show_desktop":
            self._show_desktop()

        elif bt == "lock_computer":
            self._lock_computer()

        elif bt == "launch_steam":
            app_id  = resolve_value(p.get("app_id", ""), self.variables).strip()
            save_to = p.get("save_to", "")
            self._launch_steam(app_id, save_to)

        elif bt == "browser_search":
            keyword    = resolve_value(p.get("keyword", ""), self.variables)
            engine     = p.get("engine", "baidu")
            custom_url = p.get("custom_url", "")
            self._browser_search(keyword, engine, custom_url)

        elif bt == "download_file":
            url          = resolve_value(p.get("url", ""), self.variables)
            save_dir     = resolve_value(p.get("save_dir", ""), self.variables)
            filename_opt = p.get("filename", "original")      # original / custom
            custom_name  = resolve_value(p.get("custom_name", ""), self.variables)
            overwrite    = p.get("overwrite", True)
            save_path_to = p.get("save_path_to", "")
            self._download_file(url, save_dir, filename_opt, custom_name,
                                overwrite, save_path_to)

        elif bt == "extract_archive":
            archive       = resolve_value(p.get("archive", ""), self.variables)
            dest_dir      = resolve_value(p.get("dest_dir", ""), self.variables)
            create_folder = p.get("create_folder", True)
            folder_name   = p.get("folder_name", "archive_name")   # archive_name / custom
            custom_folder = resolve_value(p.get("custom_folder", ""), self.variables)
            overwrite     = p.get("overwrite", True)
            save_dest_to  = p.get("save_dest_to", "")
            self._extract_archive(archive, dest_dir, create_folder,
                                  folder_name, custom_folder, overwrite, save_dest_to)

        elif bt == "mouse_move":
            # 兼容旧格式 {x, y} 和新格式 {pos: {x, y, mode}}
            pos     = p.get("pos", {})
            if pos:
                x, y = self._resolve_coord(pos)
            else:
                x = int(resolve_number(p.get("x", 0), self.variables))
                y = int(resolve_number(p.get("y", 0), self.variables))
            rel     = p.get("relative", False)
            dur     = resolve_number(p.get("duration", 0), self.variables)
            curve   = p.get("curve", "linear")
            jitter  = int(resolve_number(p.get("jitter", 0), self.variables))
            offset  = int(resolve_number(p.get("offset", 0), self.variables))
            self._mouse_move(x, y, rel, dur, curve=curve, jitter=jitter, rand_offset=offset)

        elif bt == "mouse_click_pos":
            pos             = p.get("pos", {})
            if pos:
                x, y = self._resolve_coord(pos)
            else:
                x = int(resolve_number(p.get("x", 0), self.variables))
                y = int(resolve_number(p.get("y", 0), self.variables))
            button          = p.get("button", "left")
            clicks          = int(resolve_number(p.get("clicks", 1), self.variables))
            move_f          = p.get("move_first", True)
            offset          = int(resolve_number(p.get("offset", 0), self.variables))
            move_curve      = p.get("move_curve", "linear")
            move_dur        = resolve_number(p.get("move_duration", 0), self.variables)
            click_interval  = float(resolve_number(p.get("click_interval", 0.12), self.variables))
            down_up_delay   = float(resolve_number(p.get("down_up_delay", 0.05), self.variables))
            self._mouse_click_pos(x, y, button, clicks, move_f,
                                  rand_offset=offset, move_curve=move_curve, move_duration=move_dur,
                                  click_interval=click_interval, down_up_delay=down_up_delay)

        elif bt == "mouse_scroll":
            pos    = p.get("pos", {})
            if pos:
                x, y = self._resolve_coord(pos)
            else:
                x = int(resolve_number(p.get("x", 0), self.variables))
                y = int(resolve_number(p.get("y", 0), self.variables))
            amount = int(resolve_number(p.get("amount", 3), self.variables))
            self._mouse_scroll(x, y, amount)

        elif bt == "mouse_drag":
            fp      = p.get("from_pos", {})
            tp      = p.get("to_pos", {})
            if fp:
                fx, fy = self._resolve_coord(fp)
            else:
                fx = int(resolve_number(p.get("from_x", 0), self.variables))
                fy = int(resolve_number(p.get("from_y", 0), self.variables))
            if tp:
                tx, ty = self._resolve_coord(tp)
            else:
                tx = int(resolve_number(p.get("to_x", 0), self.variables))
                ty = int(resolve_number(p.get("to_y", 0), self.variables))
            btn     = p.get("button", "left")
            dur     = resolve_number(p.get("duration", 0.5), self.variables)
            curve   = p.get("curve", "linear")
            jitter  = int(resolve_number(p.get("jitter", 0), self.variables))
            self._mouse_drag(fx, fy, tx, ty, btn, dur, curve=curve, jitter=jitter)

        elif bt == "keymouse_macro":
            macro_data   = p.get("macro_data", [])
            speed        = float(resolve_number(p.get("speed", 1.0), self.variables))
            repeat       = int(resolve_number(p.get("repeat", 1), self.variables))
            use_relative = p.get("use_relative", True)
            self._play_macro(macro_data, speed, repeat, use_relative)

        elif bt == "launch_app":
            path     = resolve_value(p.get("path", ""), self.variables).strip()
            args     = resolve_value(p.get("args", ""), self.variables).strip()
            cwd      = resolve_value(p.get("cwd", ""), self.variables).strip() or None
            run_mode = p.get("run_mode", "normal")
            as_admin = p.get("as_admin", False)
            wait     = p.get("wait", False)
            timeout  = float(resolve_number(p.get("timeout", 0), self.variables))
            save_pid = p.get("save_pid", "").strip()
            self._launch_app(path, args, cwd, run_mode, as_admin, wait, timeout, save_pid)

        elif bt == "activate_window":
            title   = resolve_value(p.get("title", ""), self.variables)
            timeout = resolve_number(p.get("wait_timeout", 0), self.variables)
            self._activate_window(title, timeout)

        elif bt == "set_window_topmost":
            title   = resolve_value(p.get("title", ""), self.variables)
            topmost = p.get("topmost", True)
            self._set_window_topmost(title, topmost)

        elif bt == "move_window":
            title  = resolve_value(p.get("title", ""), self.variables)
            x      = int(resolve_number(p.get("x", -1), self.variables))
            y      = int(resolve_number(p.get("y", -1), self.variables))
            width  = int(resolve_number(p.get("width", -1), self.variables))
            height = int(resolve_number(p.get("height", -1), self.variables))
            self._move_window(title, x, y, width, height)

        elif bt == "get_window_info":
            title   = resolve_value(p.get("title", ""), self.variables)
            save_to = p.get("save_to", "win")
            self._get_window_info(title, save_to)

        elif bt == "minimize_window":
            title = resolve_value(p.get("title", ""), self.variables)
            self._minimize_window(title)

        elif bt == "maximize_window":
            title = resolve_value(p.get("title", ""), self.variables)
            self._maximize_window(title)

        elif bt in ("ai_chat", "ai_generate"):
            prompt        = resolve_value(p.get("prompt", ""), self.variables)
            system_prompt = resolve_value(p.get("system_prompt", ""), self.variables)
            model         = p.get("model", "").strip()
            save_to       = p.get("save_to", "ai_reply")
            timeout       = int(resolve_number(p.get("timeout", 30), self.variables))
            temperature   = p.get("temperature", "")
            # 连续对话（ai_chat 独有）
            append_history = p.get("append_history", False)
            history_var    = p.get("history_var", "ai_history")
            self._ai_call(prompt, system_prompt, model, save_to,
                          timeout, temperature, append_history, history_var, bt)

        elif bt == "browser_auto":
            task        = resolve_value(p.get("task", ""), self.variables).strip()
            llm_provider= p.get("llm_provider", "settings")
            model       = p.get("model", "").strip()
            start_url   = resolve_value(p.get("start_url", ""), self.variables).strip()
            headless    = p.get("headless", False)
            max_steps   = int(resolve_number(p.get("max_steps", 20), self.variables))
            timeout_sec = float(resolve_number(p.get("timeout", 120), self.variables))
            save_result = p.get("save_result", "browser_result").strip()
            save_history= p.get("save_history", "").strip()
            close_after = p.get("close_after", True)
            ba_mode     = p.get("mode", "ai_run")
            self._browser_auto(task, llm_provider, model, start_url,
                               headless, max_steps, timeout_sec, save_result, save_history,
                               close_after=close_after, mode=ba_mode)

        elif bt == "run_task":
            task_id = resolve_value(p.get("task_id", ""), self.variables).strip()
            wait    = bool(p.get("wait", False))
            timeout = float(resolve_number(p.get("timeout", 0), self.variables))
            self._run_other_task(task_id, wait, timeout)

        elif bt == "stop_other_task":
            task_id = resolve_value(p.get("task_id", ""), self.variables).strip()
            self._stop_other_task(task_id)

        elif bt == "wait_task_done":
            task_id    = resolve_value(p.get("task_id", ""), self.variables).strip()
            timeout    = float(resolve_number(p.get("timeout", 60), self.variables))
            on_timeout = p.get("on_timeout", "continue")
            self._wait_task_done(task_id, timeout, on_timeout)

        elif bt == "browser_open_url":
            url_val   = resolve_value(p.get("url", ""), self.variables).strip()
            wait_load = p.get("wait_load", True)
            timeout_b = float(resolve_number(p.get("timeout", 15), self.variables))
            self._browser_op_open_url(url_val, wait_load, timeout_b)

        elif bt == "browser_click":
            selector  = resolve_value(p.get("selector", ""), self.variables).strip()
            by_text   = resolve_value(p.get("by_text", ""), self.variables).strip()
            timeout_b = float(resolve_number(p.get("timeout", 10), self.variables))
            self._browser_op_click(selector, by_text, timeout_b)

        elif bt == "browser_type":
            selector  = resolve_value(p.get("selector", ""), self.variables).strip()
            text_val  = resolve_value(p.get("text", ""), self.variables)
            clear_first = p.get("clear_first", True)
            timeout_b = float(resolve_number(p.get("timeout", 10), self.variables))
            self._browser_op_type(selector, text_val, clear_first, timeout_b)

        elif bt == "browser_get_text":
            selector  = resolve_value(p.get("selector", ""), self.variables).strip()
            save_to   = p.get("save_to", "browser_text").strip()
            timeout_b = float(resolve_number(p.get("timeout", 10), self.variables))
            self._browser_op_get_text(selector, save_to, timeout_b)

        elif bt == "browser_screenshot":
            save_path = resolve_value(p.get("save_path", "screenshot.png"), self.variables).strip()
            full_page = p.get("full_page", False)
            save_to   = p.get("save_to", "").strip()
            self._browser_op_screenshot(save_path, full_page, save_to)

        elif bt == "browser_wait_element":
            selector  = resolve_value(p.get("selector", ""), self.variables).strip()
            state_val = p.get("state", "visible")
            timeout_b = float(resolve_number(p.get("timeout", 15), self.variables))
            self._browser_op_wait_element(selector, state_val, timeout_b)

        # ── 屏幕识别 ──
        elif bt == "screen_find_image":
            img_path     = resolve_value(p.get("image_path", ""), self.variables).strip()
            confidence   = float(resolve_number(p.get("confidence", 0.8), self.variables))
            region_str   = resolve_value(p.get("region", ""), self.variables).strip()
            save_x       = p.get("save_x_to", "found_x").strip()
            save_y       = p.get("save_y_to", "found_y").strip()
            on_not_found = p.get("on_not_found", "continue")
            self._screen_find_image(img_path, confidence, region_str, save_x, save_y, on_not_found)

        elif bt == "screen_click_image":
            img_path     = resolve_value(p.get("image_path", ""), self.variables).strip()
            confidence   = float(resolve_number(p.get("confidence", 0.8), self.variables))
            button       = p.get("button", "left")
            clicks       = int(resolve_number(p.get("clicks", 1), self.variables))
            region_str   = resolve_value(p.get("region", ""), self.variables).strip()
            offset_x     = int(resolve_number(p.get("offset_x", 0), self.variables))
            offset_y     = int(resolve_number(p.get("offset_y", 0), self.variables))
            on_not_found = p.get("on_not_found", "continue")
            self._screen_click_image(img_path, confidence, button, clicks, region_str,
                                     offset_x, offset_y, on_not_found)

        elif bt == "screen_wait_image":
            img_path    = resolve_value(p.get("image_path", ""), self.variables).strip()
            confidence  = float(resolve_number(p.get("confidence", 0.8), self.variables))
            timeout_sw  = float(resolve_number(p.get("timeout", 30), self.variables))
            interval    = float(resolve_number(p.get("interval", 0.5), self.variables))
            region_str  = resolve_value(p.get("region", ""), self.variables).strip()
            save_x      = p.get("save_x_to", "").strip()
            save_y      = p.get("save_y_to", "").strip()
            on_timeout  = p.get("on_timeout", "continue")
            self._screen_wait_image(img_path, confidence, timeout_sw, interval,
                                    region_str, save_x, save_y, on_timeout)

        elif bt == "screen_screenshot_region":
            region_str = resolve_value(p.get("region", ""), self.variables).strip()
            save_path  = resolve_value(p.get("save_path", "region_shot.png"), self.variables).strip()
            save_to    = p.get("save_to", "").strip()
            self._screen_screenshot_region(region_str, save_path, save_to)

        # ── 窗口控件操作（pywinauto）──
        elif bt == "win_find_window":
            title        = resolve_value(p.get("title", ""), self.variables).strip()
            class_name   = resolve_value(p.get("class_name", ""), self.variables).strip()
            process      = resolve_value(p.get("process", ""), self.variables).strip()
            timeout_wf   = float(resolve_number(p.get("timeout", 5), self.variables))
            save_to      = p.get("save_to", "win_handle").strip()
            on_not_found = p.get("on_not_found", "continue")
            self._win_find_window(title, class_name, process, timeout_wf, save_to, on_not_found)

        elif bt == "win_click_control":
            win_title    = resolve_value(p.get("window_title", ""), self.variables).strip()
            class_name   = resolve_value(p.get("class_name", ""), self.variables).strip()
            process_name = resolve_value(p.get("process_name", ""), self.variables).strip()
            ctrl_title   = resolve_value(p.get("control_title", ""), self.variables).strip()
            ctrl_type    = p.get("control_type", "Button")
            double_click = p.get("double_click", False)
            timeout_wc   = float(resolve_number(p.get("timeout", 5), self.variables))
            self._win_click_control(win_title, class_name, process_name, ctrl_title, ctrl_type, double_click, timeout_wc)

        elif bt == "win_input_control":
            win_title    = resolve_value(p.get("window_title", ""), self.variables).strip()
            class_name   = resolve_value(p.get("class_name", ""), self.variables).strip()
            process_name = resolve_value(p.get("process_name", ""), self.variables).strip()
            ctrl_title   = resolve_value(p.get("control_title", ""), self.variables).strip()
            text_val     = resolve_value(p.get("text", ""), self.variables)
            clear_first  = p.get("clear_first", True)
            timeout_wi   = float(resolve_number(p.get("timeout", 5), self.variables))
            self._win_input_control(win_title, class_name, process_name, ctrl_title, text_val, clear_first, timeout_wi)

        elif bt == "win_get_control_text":
            win_title    = resolve_value(p.get("window_title", ""), self.variables).strip()
            class_name   = resolve_value(p.get("class_name", ""), self.variables).strip()
            process_name = resolve_value(p.get("process_name", ""), self.variables).strip()
            ctrl_title   = resolve_value(p.get("control_title", ""), self.variables).strip()
            ctrl_type    = p.get("control_type", "any")
            save_to      = p.get("save_to", "ctrl_text").strip()
            timeout_wg   = float(resolve_number(p.get("timeout", 5), self.variables))
            self._win_get_control_text(win_title, class_name, process_name, ctrl_title, ctrl_type, save_to, timeout_wg)

        elif bt == "win_wait_window":
            title      = resolve_value(p.get("title", ""), self.variables).strip()
            class_name = resolve_value(p.get("class_name", ""), self.variables).strip()
            timeout_ww = float(resolve_number(p.get("timeout", 30), self.variables))
            on_timeout = p.get("on_timeout", "continue")
            found = self._win_wait_window_ctrl(title, class_name, timeout_ww)
            if not found and on_timeout == "stop_task":
                raise StopTaskException()

        elif bt == "win_close_window":
            title      = resolve_value(p.get("title", ""), self.variables).strip()
            class_name = resolve_value(p.get("class_name", ""), self.variables).strip()
            force      = p.get("force", False)
            timeout_wc = float(resolve_number(p.get("timeout", 3), self.variables))
            self._win_close_window_ctrl(title, class_name, force, timeout_wc)

        elif bt == "win_wait_control":
            win_title    = resolve_value(p.get("window_title", ""), self.variables).strip()
            class_name   = resolve_value(p.get("class_name", ""), self.variables).strip()
            process_name = resolve_value(p.get("process_name", ""), self.variables).strip()
            ctrl_title   = resolve_value(p.get("control_title", ""), self.variables).strip()
            ctrl_type    = p.get("control_type", "Button")
            timeout_wt   = float(resolve_number(p.get("timeout", 30), self.variables))
            on_timeout   = p.get("on_timeout", "continue")
            found = self._win_wait_control(win_title, class_name, process_name, ctrl_title, ctrl_type, timeout_wt)
            if not found and on_timeout == "stop_task":
                raise StopTaskException()

        elif bt == "win_find_control":
            win_title    = resolve_value(p.get("window_title", ""), self.variables).strip()
            class_name   = resolve_value(p.get("class_name", ""), self.variables).strip()
            process_name = resolve_value(p.get("process_name", ""), self.variables).strip()
            ctrl_title   = resolve_value(p.get("control_title", ""), self.variables).strip()
            ctrl_type    = p.get("control_type", "Button")
            timeout_wf2  = float(resolve_number(p.get("timeout", 5), self.variables))
            save_to_fc   = p.get("save_to", "ctrl_info").strip()
            on_not_found = p.get("on_not_found", "continue")
            found = self._win_find_control(win_title, class_name, process_name, ctrl_title, ctrl_type, timeout_wf2, save_to_fc)
            if not found and on_not_found == "stop_task":
                raise StopTaskException()

        elif bt == "win_click_offset":
            win_title    = resolve_value(p.get("window_title", ""), self.variables).strip()
            class_name   = resolve_value(p.get("class_name", ""), self.variables).strip()
            process_name = resolve_value(p.get("process_name", ""), self.variables).strip()
            offset_x     = int(resolve_number(p.get("offset_x", 0), self.variables))
            offset_y     = int(resolve_number(p.get("offset_y", 0), self.variables))
            button       = p.get("button", "left")
            clicks       = int(resolve_number(p.get("clicks", 1), self.variables))
            move_first   = p.get("move_first", True)
            timeout_wo   = float(resolve_number(p.get("timeout", 5), self.variables))
            self._win_click_offset(win_title, class_name, process_name, offset_x, offset_y, button, clicks, move_first, timeout_wo)

        elif bt == "win_find_image":
            win_title    = resolve_value(p.get("window_title", ""), self.variables).strip()
            class_name   = resolve_value(p.get("class_name", ""), self.variables).strip()
            process_name = resolve_value(p.get("process_name", ""), self.variables).strip()
            img_path     = resolve_value(p.get("image_path", ""), self.variables).strip()
            confidence   = float(resolve_number(p.get("confidence", 0.8), self.variables))
            timeout_wfi  = float(resolve_number(p.get("timeout", 5), self.variables))
            save_x       = p.get("save_x", "")
            save_y       = p.get("save_y", "")
            on_not_found = p.get("on_not_found", "continue")
            found = self._win_find_image(win_title, class_name, process_name, img_path, confidence, timeout_wfi, save_x, save_y)
            if not found and on_not_found == "stop_task":
                raise StopTaskException()

        elif bt == "win_click_image":
            win_title    = resolve_value(p.get("window_title", ""), self.variables).strip()
            class_name   = resolve_value(p.get("class_name", ""), self.variables).strip()
            process_name = resolve_value(p.get("process_name", ""), self.variables).strip()
            img_path     = resolve_value(p.get("image_path", ""), self.variables).strip()
            confidence   = float(resolve_number(p.get("confidence", 0.8), self.variables))
            button       = p.get("button", "left")
            clicks       = int(resolve_number(p.get("clicks", 1), self.variables))
            offset_x     = int(resolve_number(p.get("offset_x", 0), self.variables))
            offset_y     = int(resolve_number(p.get("offset_y", 0), self.variables))
            timeout_wci  = float(resolve_number(p.get("timeout", 5), self.variables))
            on_not_found = p.get("on_not_found", "continue")
            found = self._win_click_image(win_title, class_name, process_name, img_path, confidence, button, clicks, offset_x, offset_y, timeout_wci)
            if not found and on_not_found == "stop_task":
                raise StopTaskException()

        else:
            # ── 尝试插件功能块 ──
            try:
                from ..plugin_manager import PluginManager as _PM
                from ..plugin_api import BlockExecutionContext
                executor = _PM.instance().get_executor(bt)
                if executor:
                    ctx = BlockExecutionContext(
                        variables=self.variables,
                        log=self.on_log,
                        stop_event=self._stop_event,
                        config=self.config,
                    )
                    executor(p, ctx)
                else:
                    self._log("WARN", f"    未知功能块类型: {bt}")
            except ImportError:
                self._log("WARN", f"    未知功能块类型: {bt}")

    # ─── 辅助执行方法 ───

    # ── 浏览器基础操作（基于 playwright，共享持久化浏览器实例）──
    # 全局单例 playwright 页面，在任务结束时不自动关闭（除非用 browser_open_url 的 close 参数）
    _pw_browser = None   # Browser
    _pw_page    = None   # Page
    _pw_lock    = None   # threading.Lock

    @classmethod
    def _get_pw_lock(cls):
        import threading
        if cls._pw_lock is None:
            cls._pw_lock = threading.Lock()
        return cls._pw_lock

    @classmethod
    def _get_pw_page(cls, timeout_ms=15000):
        """获取或创建 playwright 页面（全局共享实例）"""
        with cls._get_pw_lock():
            if cls._pw_page and not cls._pw_page.is_closed():
                return cls._pw_page
            # 新建
            from playwright.sync_api import sync_playwright
            cls._pw_playwright = sync_playwright().start()
            cls._pw_browser = cls._pw_playwright.chromium.launch(headless=False)
            ctx = cls._pw_browser.new_context()
            cls._pw_page = ctx.new_page()
            return cls._pw_page

    @classmethod
    def _close_pw_browser(cls):
        """关闭 playwright 浏览器"""
        with cls._get_pw_lock():
            try:
                if cls._pw_page and not cls._pw_page.is_closed():
                    cls._pw_page.close()
            except Exception:
                pass
            try:
                if cls._pw_browser:
                    cls._pw_browser.close()
            except Exception:
                pass
            try:
                if hasattr(cls, "_pw_playwright") and cls._pw_playwright:
                    cls._pw_playwright.stop()
            except Exception:
                pass
            cls._pw_browser = None
            cls._pw_page = None

    def _browser_op_open_url(self, url: str, wait_load: bool, timeout: float):
        if not url:
            self._log("WARN", "    [browser_open_url] 未填写 URL，跳过")
            return
        try:
            page = self._get_pw_page(timeout_ms=int(timeout * 1000))
            self._log("INFO", f"    [browser_open_url] 打开: {url}")
            page.goto(url, timeout=int(timeout * 1000),
                      wait_until="domcontentloaded" if wait_load else "commit")
            self._log("INFO", f"    [browser_open_url] 已加载: {page.title()}")
        except Exception as e:
            self._log("ERROR", f"    [browser_open_url] 失败: {e}")

    def _browser_op_click(self, selector: str, by_text: str, timeout: float):
        if not selector and not by_text:
            self._log("WARN", "    [browser_click] 未填写选择器或文本，跳过")
            return
        try:
            page = self._get_pw_page()
            t_ms = int(timeout * 1000)
            if by_text:
                self._log("INFO", f"    [browser_click] 点击文本: {by_text}")
                page.get_by_text(by_text, exact=False).first.click(timeout=t_ms)
            else:
                self._log("INFO", f"    [browser_click] 点击: {selector}")
                page.click(selector, timeout=t_ms)
            self._log("INFO", "    [browser_click] 点击成功")
        except Exception as e:
            self._log("ERROR", f"    [browser_click] 失败: {e}")

    def _browser_op_type(self, selector: str, text: str, clear_first: bool, timeout: float):
        if not selector:
            self._log("WARN", "    [browser_type] 未填写选择器，跳过")
            return
        try:
            page = self._get_pw_page()
            t_ms = int(timeout * 1000)
            self._log("INFO", f"    [browser_type] 输入到 {selector}: {text[:40]}...")
            if clear_first:
                page.fill(selector, text, timeout=t_ms)
            else:
                page.type(selector, text, timeout=t_ms)
            self._log("INFO", "    [browser_type] 输入完成")
        except Exception as e:
            self._log("ERROR", f"    [browser_type] 失败: {e}")

    def _browser_op_get_text(self, selector: str, save_to: str, timeout: float):
        if not selector:
            self._log("WARN", "    [browser_get_text] 未填写选择器，跳过")
            return
        try:
            page = self._get_pw_page()
            t_ms = int(timeout * 1000)
            text = page.text_content(selector, timeout=t_ms) or ""
            self.variables[save_to] = text.strip()
            self._log("INFO", f"    [browser_get_text] 已获取文本（{len(text)} 字符）→ {save_to}")
        except Exception as e:
            self._log("ERROR", f"    [browser_get_text] 失败: {e}")

    def _browser_op_screenshot(self, save_path: str, full_page: bool, save_to: str):
        try:
            page = self._get_pw_page()
            page.screenshot(path=save_path, full_page=full_page)
            self._log("INFO", f"    [browser_screenshot] 截图已保存: {save_path}")
            if save_to:
                self.variables[save_to] = save_path
        except Exception as e:
            self._log("ERROR", f"    [browser_screenshot] 失败: {e}")

    def _browser_op_wait_element(self, selector: str, state: str, timeout: float):
        if not selector:
            self._log("WARN", "    [browser_wait_element] 未填写选择器，跳过")
            return
        try:
            page = self._get_pw_page()
            t_ms = int(timeout * 1000)
            self._log("INFO", f"    [browser_wait_element] 等待 {selector} [{state}]…")
            page.wait_for_selector(selector, state=state, timeout=t_ms)
            self._log("INFO", "    [browser_wait_element] 元素已就绪")
        except Exception as e:
            self._log("ERROR", f"    [browser_wait_element] 超时或失败: {e}")

    # ── 屏幕识别（基于 pyautogui + opencv）──

    @staticmethod
    def _load_cv2_image(img_path: str):
        """用 numpy.fromfile 读取图片，绕过 OpenCV 不支持非 ASCII 路径的限制。
        返回 BGR numpy 数组，失败则抛出 FileNotFoundError / cv2 异常。
        """
        import cv2
        import numpy as np
        data = np.fromfile(img_path, dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError(f"无法解码图片文件: {img_path}")
        return img

    def _parse_region(self, region_str: str):
        """解析区域字符串 'x,y,w,h' 为元组，失败返回 None（全屏）"""
        if not region_str:
            return None
        try:
            parts = [int(v.strip()) for v in region_str.split(",")]
            if len(parts) == 4:
                return tuple(parts)
        except Exception:
            pass
        return None

    def _screen_find_image(self, img_path: str, confidence: float, region_str: str,
                           save_x: str, save_y: str, on_not_found: str):
        if not img_path:
            self._log("WARN", "    [screen_find_image] 未填写图片路径，跳过")
            return
        try:
            import pyautogui
            region = self._parse_region(region_str)
            self._log("INFO", f"    [screen_find_image] 搜索图片: {img_path}（精度={confidence}）")
            needle = self._load_cv2_image(img_path)
            loc = pyautogui.locateOnScreen(needle, confidence=confidence, region=region)
            if loc is None:
                self._log("WARN", "    [screen_find_image] 未找到目标图片")
                if save_x:
                    self.variables[save_x] = ""
                if save_y:
                    self.variables[save_y] = ""
                if on_not_found == "stop_task":
                    raise StopTaskException()
                return
            cx, cy = pyautogui.center(loc)
            if save_x:
                self.variables[save_x] = int(cx)
            if save_y:
                self.variables[save_y] = int(cy)
            self._log("INFO", f"    [screen_find_image] 找到！坐标=({cx},{cy}) → {save_x},{save_y}")
        except StopTaskException:
            raise
        except ImportError:
            self._log("ERROR", "    [screen_find_image] 依赖未安装，请运行：pip install pyautogui opencv-python")
        except Exception as e:
            self._log("ERROR", f"    [screen_find_image] 失败: {e}")

    def _screen_click_image(self, img_path: str, confidence: float, button: str,
                            clicks: int, region_str: str, offset_x: int, offset_y: int,
                            on_not_found: str):
        if not img_path:
            self._log("WARN", "    [screen_click_image] 未填写图片路径，跳过")
            return
        try:
            import pyautogui
            region = self._parse_region(region_str)
            self._log("INFO", f"    [screen_click_image] 查找并点击: {img_path}（精度={confidence}）")
            needle = self._load_cv2_image(img_path)
            loc = pyautogui.locateOnScreen(needle, confidence=confidence, region=region)
            if loc is None:
                self._log("WARN", "    [screen_click_image] 未找到目标图片")
                if on_not_found == "stop_task":
                    raise StopTaskException()
                return
            cx, cy = pyautogui.center(loc)
            target_x = int(cx) + offset_x
            target_y = int(cy) + offset_y
            self._log("INFO", f"    [screen_click_image] 点击坐标=({target_x},{target_y})，次数={clicks}")
            pyautogui.click(target_x, target_y, clicks=clicks, button=button, interval=0.12)
            self._log("INFO", "    [screen_click_image] 点击完成")
        except StopTaskException:
            raise
        except ImportError:
            self._log("ERROR", "    [screen_click_image] 依赖未安装，请运行：pip install pyautogui opencv-python")
        except Exception as e:
            self._log("ERROR", f"    [screen_click_image] 失败: {e}")

    def _screen_wait_image(self, img_path: str, confidence: float, timeout: float,
                           interval: float, region_str: str, save_x: str, save_y: str,
                           on_timeout: str):
        if not img_path:
            self._log("WARN", "    [screen_wait_image] 未填写图片路径，跳过")
            return
        try:
            import pyautogui
            region = self._parse_region(region_str)
            self._log("INFO", f"    [screen_wait_image] 等待图片出现: {img_path}（超时={timeout}s）")
            needle = self._load_cv2_image(img_path)
            deadline = time.time() + timeout if timeout > 0 else None
            while True:
                self._check_stop()
                loc = pyautogui.locateOnScreen(needle, confidence=confidence, region=region)
                if loc is not None:
                    cx, cy = pyautogui.center(loc)
                    if save_x:
                        self.variables[save_x] = int(cx)
                    if save_y:
                        self.variables[save_y] = int(cy)
                    self._log("INFO", f"    [screen_wait_image] 图片已出现，坐标=({cx},{cy})")
                    return
                if deadline and time.time() >= deadline:
                    self._log("WARN", "    [screen_wait_image] 等待超时，未找到图片")
                    if on_timeout == "stop_task":
                        raise StopTaskException()
                    return
                time.sleep(max(0.1, interval))
        except StopTaskException:
            raise
        except ImportError:
            self._log("ERROR", "    [screen_wait_image] 依赖未安装，请运行：pip install pyautogui opencv-python")
        except Exception as e:
            self._log("ERROR", f"    [screen_wait_image] 失败: {e}")

    def _screen_screenshot_region(self, region_str: str, save_path: str, save_to: str):
        try:
            import pyautogui
            from PIL import Image
            self._log("INFO", f"    [screen_screenshot_region] 截图区域={region_str or '全屏'} → {save_path}")
            region = self._parse_region(region_str)
            if region:
                x, y, w, h = region
                img = pyautogui.screenshot(region=(x, y, w, h))
            else:
                img = pyautogui.screenshot()
            # 确保保存目录存在
            save_dir = os.path.dirname(save_path)
            if save_dir and not os.path.exists(save_dir):
                os.makedirs(save_dir, exist_ok=True)
            img.save(save_path)
            if save_to:
                self.variables[save_to] = save_path
            self._log("INFO", f"    [screen_screenshot_region] 已保存: {save_path}")
        except ImportError:
            self._log("ERROR", "    [screen_screenshot_region] 依赖未安装，请运行：pip install pyautogui Pillow")
        except Exception as e:
            self._log("ERROR", f"    [screen_screenshot_region] 失败: {e}")

    # ── 窗口控件操作（基于 pywinauto）──

    def _get_pywinauto_app(self, title: str, class_name: str = "", timeout: float = 5):
        """获取 pywinauto Application 连接到指定窗口"""
        from pywinauto import Application, findwindows
        kwargs = {}
        if title:
            # 支持通配符
            if "*" in title:
                import re as _re
                pat = _re.compile(_re.escape(title).replace(r"\*", ".*"), _re.IGNORECASE)
                handles = findwindows.find_windows()
                matched = None
                for hwnd in handles:
                    try:
                        import win32gui
                        t = win32gui.GetWindowText(hwnd)
                        if pat.match(t):
                            matched = hwnd
                            break
                    except Exception:
                        continue
                if matched:
                    app = Application(backend="uia").connect(handle=matched)
                    return app, app.window(handle=matched)
                return None, None
            else:
                kwargs["title"] = title
        if class_name:
            kwargs["class_name"] = class_name
        app = Application(backend="uia").connect(timeout=timeout, **kwargs)
        win = app.top_window()
        return app, win

    def _win_find_window(self, title: str, class_name: str, process: str,
                         timeout: float, save_to: str, on_not_found: str):
        try:
            from pywinauto import Application, findwindows
            import win32gui as _wg
            self._log("INFO", f"    [win_find_window] 查找窗口: title={title!r} class={class_name!r} proc={process!r}")
            deadline = time.time() + max(timeout, 0.1)
            found_hwnd = None
            while time.time() < deadline:
                self._check_stop()
                try:
                    kw = {}
                    if title:
                        kw["title"] = title
                    if class_name:
                        kw["class_name"] = class_name
                    if process:
                        kw["process"] = process
                    handles = findwindows.find_windows(**kw) if kw else []
                    if handles:
                        found_hwnd = handles[0]
                        break
                except Exception:
                    pass
                time.sleep(0.3)
            if found_hwnd:
                win_title = _wg.GetWindowText(found_hwnd)
                if save_to:
                    self.variables[save_to] = found_hwnd
                self._log("INFO", f"    [win_find_window] 找到窗口: {win_title!r}，句柄={found_hwnd} → {save_to}")
            else:
                self._log("WARN", f"    [win_find_window] 未找到窗口: {title!r}")
                if save_to:
                    self.variables[save_to] = ""
                if on_not_found == "stop_task":
                    raise StopTaskException()
        except StopTaskException:
            raise
        except ImportError:
            self._log("ERROR", "    [win_find_window] 依赖未安装，请运行：pip install pywinauto")
        except Exception as e:
            self._log("ERROR", f"    [win_find_window] 失败: {e}")

    def _win_click_control(self, win_title: str, class_name: str, process_name: str,
                           ctrl_title: str, ctrl_type: str,
                           double_click: bool, timeout: float):
        if not win_title and not class_name and not process_name:
            self._log("WARN", "    [win_click_control] 未填写任何窗口识别条件，跳过")
            return
        try:
            from pywinauto import Application
            self._log("INFO", f"    [win_click_control] 窗口={win_title!r} 类名={class_name!r} 进程={process_name!r} 控件={ctrl_title!r}")
            hwnd = self._find_hwnd_by_conditions(win_title, class_name, process_name, timeout)
            if not hwnd:
                self._log("WARN", f"    [win_click_control] 超时未找到目标窗口")
                return
            app = Application(backend="uia").connect(handle=hwnd)
            dlg = app.top_window()
            if ctrl_type == "any" or not ctrl_type:
                ctrl_kw = {}
            else:
                ctrl_kw = {"control_type": ctrl_type}
            if ctrl_title:
                ctrl_kw["title"] = ctrl_title
            ctrl = dlg.child_window(**ctrl_kw)
            if double_click:
                ctrl.double_click_input()
                self._log("INFO", "    [win_click_control] 双击完成")
            else:
                ctrl.click_input()
                self._log("INFO", "    [win_click_control] 点击完成")
        except ImportError:
            self._log("ERROR", "    [win_click_control] 依赖未安装，请运行：pip install pywinauto")
        except Exception as e:
            self._log("ERROR", f"    [win_click_control] 失败: {e}")

    def _win_input_control(self, win_title: str, class_name: str, process_name: str,
                           ctrl_title: str, text: str,
                           clear_first: bool, timeout: float):
        if not win_title and not class_name and not process_name:
            self._log("WARN", "    [win_input_control] 未填写任何窗口识别条件，跳过")
            return
        try:
            from pywinauto import Application
            self._log("INFO", f"    [win_input_control] 窗口={win_title!r} 类名={class_name!r} 进程={process_name!r} 输入={text[:30]!r}…")
            hwnd = self._find_hwnd_by_conditions(win_title, class_name, process_name, timeout)
            if not hwnd:
                self._log("WARN", f"    [win_input_control] 超时未找到目标窗口")
                return
            app = Application(backend="uia").connect(handle=hwnd)
            dlg = app.top_window()
            if ctrl_title:
                edit = dlg.child_window(title=ctrl_title, control_type="Edit")
            else:
                edit = dlg.child_window(control_type="Edit")
            if clear_first:
                edit.set_text("")
            edit.type_keys(text, with_spaces=True)
            self._log("INFO", "    [win_input_control] 输入完成")
        except ImportError:
            self._log("ERROR", "    [win_input_control] 依赖未安装，请运行：pip install pywinauto")
        except Exception as e:
            self._log("ERROR", f"    [win_input_control] 失败: {e}")

    def _win_get_control_text(self, win_title: str, class_name: str, process_name: str,
                              ctrl_title: str, ctrl_type: str,
                              save_to: str, timeout: float):
        if not win_title and not class_name and not process_name:
            self._log("WARN", "    [win_get_control_text] 未填写任何窗口识别条件，跳过")
            return
        try:
            from pywinauto import Application
            self._log("INFO", f"    [win_get_control_text] 窗口={win_title!r} 类名={class_name!r} 进程={process_name!r} 控件={ctrl_title!r}")
            hwnd = self._find_hwnd_by_conditions(win_title, class_name, process_name, timeout)
            if not hwnd:
                self._log("WARN", f"    [win_get_control_text] 超时未找到目标窗口")
                return
            app = Application(backend="uia").connect(handle=hwnd)
            dlg = app.top_window()
            if ctrl_title or (ctrl_type and ctrl_type != "any"):
                ctrl_kw = {}
                if ctrl_title:
                    ctrl_kw["title"] = ctrl_title
                if ctrl_type and ctrl_type != "any":
                    ctrl_kw["control_type"] = ctrl_type
                ctrl = dlg.child_window(**ctrl_kw)
                text = ctrl.window_text()
            else:
                text = dlg.window_text()
            self.variables[save_to] = text
            self._log("INFO", f"    [win_get_control_text] 获取文本({len(text)}字符) → {save_to}")
        except ImportError:
            self._log("ERROR", "    [win_get_control_text] 依赖未安装，请运行：pip install pywinauto")
        except Exception as e:
            self._log("ERROR", f"    [win_get_control_text] 失败: {e}")

    def _win_wait_window_ctrl(self, title: str, class_name: str, timeout: float) -> bool:
        try:
            from pywinauto import findwindows
            self._log("INFO", f"    [win_wait_window] 等待窗口: {title!r}（超时={timeout}s）")
            deadline = time.time() + timeout if timeout > 0 else None
            while True:
                self._check_stop()
                try:
                    kw = {}
                    if title:
                        kw["title_re"] = _make_title_re(title)
                    if class_name:
                        kw["class_name"] = class_name
                    handles = findwindows.find_windows(**kw) if kw else []
                    if handles:
                        self._log("INFO", "    [win_wait_window] 窗口已出现")
                        return True
                except Exception:
                    pass
                if deadline and time.time() >= deadline:
                    self._log("WARN", "    [win_wait_window] 等待超时")
                    return False
                time.sleep(0.3)
        except ImportError:
            self._log("ERROR", "    [win_wait_window] 依赖未安装，请运行：pip install pywinauto")
            return False
        except Exception as e:
            self._log("ERROR", f"    [win_wait_window] 失败: {e}")
            return False

    def _win_close_window_ctrl(self, title: str, class_name: str, force: bool, timeout: float):
        if not title and not class_name:
            self._log("WARN", "    [win_close_window] 未填写窗口标题，跳过")
            return
        try:
            from pywinauto import Application
            self._log("INFO", f"    [win_close_window] 关闭窗口: {title!r} force={force}")
            app = Application(backend="uia").connect(title_re=_make_title_re(title) if title else None,
                                                     class_name=class_name if class_name else None,
                                                     timeout=timeout)
            win = app.top_window()
            if force:
                win.close()
            else:
                win.close()
            self._log("INFO", "    [win_close_window] 窗口已关闭")
        except ImportError:
            self._log("ERROR", "    [win_close_window] 依赖未安装，请运行：pip install pywinauto")
        except Exception as e:
            self._log("ERROR", f"    [win_close_window] 失败: {e}")

    def _find_hwnd_by_conditions(self, win_title: str, class_name: str,
                                  process_name: str, timeout: float) -> int:
        """
        多条件组合查找窗口句柄（HWND）。
        条件之间为 AND 关系：满足所有填写的条件才算匹配。
        返回找到的第一个窗口 HWND，超时返回 0。
        """
        import ctypes
        import ctypes.wintypes
        import re as _re

        user32 = ctypes.windll.user32
        title_re = _make_title_re(win_title) if win_title else None
        pattern = _re.compile(title_re, _re.IGNORECASE) if title_re else None

        found_hwnd = [0]

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        def _enum_cb(h, _lp):
            if not user32.IsWindowVisible(h):
                return True
            # 检查窗口标题
            if pattern:
                buf = ctypes.create_unicode_buffer(512)
                user32.GetWindowTextW(h, buf, 512)
                if not pattern.search(buf.value):
                    return True
            # 检查窗口类名
            if class_name:
                cn_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(h, cn_buf, 256)
                if cn_buf.value.lower() != class_name.lower():
                    return True
            # 检查进程名
            if process_name:
                pid = ctypes.wintypes.DWORD()
                user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
                try:
                    import psutil
                    proc = psutil.Process(pid.value)
                    if proc.name().lower() != process_name.lower():
                        return True
                except Exception:
                    return True
            found_hwnd[0] = h
            return False  # 停止枚举

        deadline = time.time() + timeout if timeout > 0 else None
        while not found_hwnd[0]:
            self._check_stop()
            user32.EnumWindows(_enum_cb, 0)
            if found_hwnd[0]:
                break
            if deadline and time.time() >= deadline:
                conditions = []
                if win_title: conditions.append(f"标题={win_title!r}")
                if class_name: conditions.append(f"类名={class_name!r}")
                if process_name: conditions.append(f"进程={process_name!r}")
                self._log("WARN", f"    [find_hwnd] 超时未找到窗口: {' AND '.join(conditions)}")
                return 0
            time.sleep(0.2)
        return found_hwnd[0]

    def _win_wait_control(self, win_title: str, class_name: str, process_name: str,
                          ctrl_title: str, ctrl_type: str, timeout: float) -> bool:
        """等待目标窗口中指定控件出现，返回是否找到。"""
        try:
            from pywinauto import Application
            self._log("INFO", f"    [win_wait_control] 等待窗口={win_title!r} 类名={class_name!r} 进程={process_name!r} 控件={ctrl_title!r} 类型={ctrl_type}（超时={timeout}s）")
            deadline = time.time() + timeout if timeout > 0 else None
            while True:
                self._check_stop()
                try:
                    hwnd = self._find_hwnd_by_conditions(win_title, class_name, process_name, min(timeout, 1.0))
                    if hwnd:
                        app = Application(backend="uia").connect(handle=hwnd)
                        dlg = app.top_window()
                        ctrl_kw = {}
                        if ctrl_type and ctrl_type != "any":
                            ctrl_kw["control_type"] = ctrl_type
                        if ctrl_title:
                            ctrl_kw["title"] = ctrl_title
                        ctrl = dlg.child_window(**ctrl_kw)
                        if ctrl.exists(timeout=0):
                            self._log("INFO", "    [win_wait_control] 控件已出现")
                            return True
                except Exception:
                    pass
                if deadline and time.time() >= deadline:
                    self._log("WARN", "    [win_wait_control] 等待超时")
                    return False
                time.sleep(0.3)
        except ImportError:
            self._log("ERROR", "    [win_wait_control] 依赖未安装，请运行：pip install pywinauto")
            return False
        except Exception as e:
            self._log("ERROR", f"    [win_wait_control] 失败: {e}")
            return False

    def _win_find_control(self, win_title: str, class_name: str, process_name: str,
                          ctrl_title: str, ctrl_type: str,
                          timeout: float, save_to: str) -> bool:
        """查找目标窗口中的控件，将控件文本或句柄存入变量，返回是否找到。"""
        try:
            from pywinauto import Application
            self._log("INFO", f"    [win_find_control] 查找窗口={win_title!r} 类名={class_name!r} 进程={process_name!r} 控件={ctrl_title!r} 类型={ctrl_type}")
            hwnd = self._find_hwnd_by_conditions(win_title, class_name, process_name, timeout)
            if not hwnd:
                self._log("WARN", "    [win_find_control] 超时未找到目标窗口")
                if save_to:
                    self.variables[save_to] = ""
                return False
            app = Application(backend="uia").connect(handle=hwnd)
            dlg = app.top_window()
            ctrl_kw = {}
            if ctrl_type and ctrl_type != "any":
                ctrl_kw["control_type"] = ctrl_type
            if ctrl_title:
                ctrl_kw["title"] = ctrl_title
            ctrl = dlg.child_window(**ctrl_kw)
            if ctrl.exists(timeout=0):
                ctrl_text = ctrl.window_text()
                if save_to:
                    self.variables[save_to] = ctrl_text
                self._log("INFO", f"    [win_find_control] 找到控件，文本={ctrl_text!r} → {save_to}")
                return True
            else:
                self._log("WARN", f"    [win_find_control] 在窗口中未找到控件: {ctrl_title!r}")
                if save_to:
                    self.variables[save_to] = ""
                return False
        except ImportError:
            self._log("ERROR", "    [win_find_control] 依赖未安装，请运行：pip install pywinauto")
            return False
        except Exception as e:
            self._log("ERROR", f"    [win_find_control] 失败: {e}")
            return False

    def _win_click_offset(self, win_title: str, class_name: str, process_name: str,
                          offset_x: int, offset_y: int, button: str, clicks: int,
                          move_first: bool, timeout: float):
        """
        窗口坐标偏移点击：找到目标窗口，计算窗口左上角 + (offset_x, offset_y) 的屏幕坐标，然后点击。
        支持多条件组合识别：窗口标题(通配符) + 窗口类名(精确) + 进程名(精确)，条件之间为 AND 关系。
        即使窗口移动了位置，也能根据实时坐标精确点击。
        """
        if not win_title and not class_name and not process_name:
            self._log("WARN", "    [win_click_offset] 未填写任何窗口识别条件，跳过")
            return
        import ctypes
        import ctypes.wintypes
        try:
            user32 = ctypes.windll.user32
            hwnd = self._find_hwnd_by_conditions(win_title, class_name, process_name, timeout)
            if not hwnd:
                return

            # 获取窗口左上角坐标（物理像素）
            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            target_x = rect.left + offset_x
            target_y = rect.top  + offset_y

            self._log("INFO", f"    [win_click_offset] 窗口左上角=({rect.left},{rect.top}) "
                              f"偏移=({offset_x},{offset_y}) 点击=({target_x},{target_y})")

            # 点击（复用现有 _mouse_click_pos）
            self._mouse_click_pos(target_x, target_y, button, clicks, move_first)
            self._log("INFO", "    [win_click_offset] 点击完成")
        except Exception as e:
            self._log("ERROR", f"    [win_click_offset] 失败: {e}")

    def _win_capture_client(self, hwnd: int):
        """对指定窗口截图（客户区），返回 numpy 图像（BGR）。"""
        import ctypes
        import ctypes.wintypes
        import numpy as np
        user32 = ctypes.windll.user32
        gdi32  = ctypes.windll.gdi32

        # 获取窗口客户区尺寸
        rect = ctypes.wintypes.RECT()
        user32.GetClientRect(hwnd, ctypes.byref(rect))
        w = rect.right  - rect.left
        h = rect.bottom - rect.top
        if w <= 0 or h <= 0:
            # 回退：用窗口区域
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = rect.right  - rect.left
            h = rect.bottom - rect.top

        # BitBlt 截图
        hdc_win = user32.GetDC(hwnd)
        hdc_mem = gdi32.CreateCompatibleDC(hdc_win)

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize",          ctypes.c_uint32),
                ("biWidth",         ctypes.c_int32),
                ("biHeight",        ctypes.c_int32),
                ("biPlanes",        ctypes.c_uint16),
                ("biBitCount",      ctypes.c_uint16),
                ("biCompression",   ctypes.c_uint32),
                ("biSizeImage",     ctypes.c_uint32),
                ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32),
                ("biClrUsed",       ctypes.c_uint32),
                ("biClrImportant",  ctypes.c_uint32),
            ]

        bmi = BITMAPINFOHEADER()
        bmi.biSize        = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth       = w
        bmi.biHeight      = -h   # 负值 = 从上到下
        bmi.biPlanes      = 1
        bmi.biBitCount    = 32
        bmi.biCompression = 0

        buf = (ctypes.c_byte * (w * h * 4))()
        hbm = gdi32.CreateDIBSection(hdc_mem, ctypes.byref(bmi), 0, None, None, 0)
        gdi32.SelectObject(hdc_mem, hbm)
        gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_win, 0, 0, 0x00CC0020)  # SRCCOPY
        gdi32.GetDIBits(hdc_mem, hbm, 0, h, buf, ctypes.byref(bmi), 0)

        gdi32.DeleteObject(hbm)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(hwnd, hdc_win)

        img = np.frombuffer(buf, dtype=np.uint8).reshape(h, w, 4)
        return img[:, :, :3].copy()  # BGR（去掉 alpha）

    def _win_find_image(self, win_title: str, class_name: str, process_name: str,
                        img_path: str, confidence: float, timeout: float,
                        save_x: str, save_y: str) -> bool:
        """
        窗口查找图片：对指定窗口截图，在截图中查找目标图片（不依赖屏幕坐标）。
        坐标结果为相对窗口客户区的像素坐标，存入变量。
        """
        if not win_title and not class_name and not process_name:
            self._log("WARN", "    [win_find_image] 未填写任何窗口识别条件，跳过")
            return False
        if not img_path:
            self._log("WARN", "    [win_find_image] 未填写图片路径，跳过")
            return False
        try:
            import cv2
            hwnd = self._find_hwnd_by_conditions(win_title, class_name, process_name, timeout)
            if not hwnd:
                if save_x: self.variables[save_x] = ""
                if save_y: self.variables[save_y] = ""
                return False

            self._log("INFO", f"    [win_find_image] 对窗口截图并查找: {img_path}（精度={confidence}）")
            screenshot = self._win_capture_client(hwnd)
            needle     = self._load_cv2_image(img_path)

            # 用 matchTemplate 查找
            result = cv2.matchTemplate(screenshot, needle, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val < confidence:
                self._log("WARN", f"    [win_find_image] 未找到目标图片（最大匹配度={max_val:.3f} < {confidence}）")
                if save_x: self.variables[save_x] = ""
                if save_y: self.variables[save_y] = ""
                return False

            # 中心坐标（相对窗口客户区）
            nh, nw = needle.shape[:2]
            cx = max_loc[0] + nw // 2
            cy = max_loc[1] + nh // 2
            if save_x: self.variables[save_x] = cx
            if save_y: self.variables[save_y] = cy
            self._log("INFO", f"    [win_find_image] 找到！窗口内坐标=({cx},{cy})  匹配度={max_val:.3f}")
            return True
        except ImportError:
            self._log("ERROR", "    [win_find_image] 依赖未安装，请运行：pip install opencv-python")
            return False
        except Exception as e:
            self._log("ERROR", f"    [win_find_image] 失败: {e}")
            return False

    def _win_click_image(self, win_title: str, class_name: str, process_name: str,
                         img_path: str, confidence: float, button: str, clicks: int,
                         offset_x: int, offset_y: int, timeout: float) -> bool:
        """
        窗口点击图片：对指定窗口截图查找图片，将匹配中心换算成屏幕坐标后点击。
        即使窗口不在屏幕最前面也能获取截图（后台操作）。
        """
        if not win_title and not class_name and not process_name:
            self._log("WARN", "    [win_click_image] 未填写任何窗口识别条件，跳过")
            return False
        if not img_path:
            self._log("WARN", "    [win_click_image] 未填写图片路径，跳过")
            return False
        try:
            import cv2
            import ctypes, ctypes.wintypes
            user32 = ctypes.windll.user32

            hwnd = self._find_hwnd_by_conditions(win_title, class_name, process_name, timeout)
            if not hwnd:
                return False

            self._log("INFO", f"    [win_click_image] 对窗口截图并查找: {img_path}（精度={confidence}）")
            screenshot = self._win_capture_client(hwnd)
            needle     = self._load_cv2_image(img_path)

            result = cv2.matchTemplate(screenshot, needle, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val < confidence:
                self._log("WARN", f"    [win_click_image] 未找到目标图片（最大匹配度={max_val:.3f} < {confidence}）")
                return False

            nh, nw = needle.shape[:2]
            rel_x = max_loc[0] + nw // 2
            rel_y = max_loc[1] + nh // 2

            # 换算为屏幕坐标（客户区坐标 → 屏幕坐标）
            pt = ctypes.wintypes.POINT(rel_x, rel_y)
            user32.ClientToScreen(hwnd, ctypes.byref(pt))
            target_x = pt.x + offset_x
            target_y = pt.y + offset_y

            self._log("INFO", f"    [win_click_image] 找到！匹配度={max_val:.3f} 点击=({target_x},{target_y})")
            self._mouse_click_pos(target_x, target_y, button, clicks, True)
            self._log("INFO", "    [win_click_image] 点击完成")
            return True
        except ImportError:
            self._log("ERROR", "    [win_click_image] 依赖未安装，请运行：pip install opencv-python")
            return False
        except Exception as e:
            self._log("ERROR", f"    [win_click_image] 失败: {e}")
            return False






    def _browser_auto(self, task: str, llm_provider: str, model: str,
                      start_url: str, headless: bool, max_steps: int,
                      timeout_sec: float, save_result: str, save_history: str,
                      close_after: bool = True, mode: str = "ai_run"):
        """
        使用 browser-use 库执行 AI 浏览器自动化任务。
        依赖：pip install browser-use playwright
              playwright install chromium
        项目：https://github.com/browser-use/browser-use  (MIT License)

        实现策略：
        - 直接在当前进程尝试导入 browser_use（源码运行时）
        - 若当前进程无法导入（PyInstaller exe 内嵌环境），则通过子进程调用系统 Python 执行
        - 结果通过 JSON 标准输出传回
        - mode: "ai_run" = 每次由 AI 思考执行; "ai_generate" = AI 生成步骤列表（返回 JSON 步骤）
        """
        import sys, os, json as _json, importlib, time as _time

        if not task:
            self._log("WARN", "    [browser_auto] 未填写任务描述，跳过")
            return

        cfg = self.config
        # ── 确定实际使用的 provider 和 model ──
        effective_provider = llm_provider if llm_provider != "settings" else getattr(cfg, "ai_provider", "openai")
        effective_model    = model or getattr(cfg, "ai_model", "gpt-4o-mini")
        api_key            = getattr(cfg, "ai_api_key", "").strip()
        base_url           = getattr(cfg, "ai_base_url", "").strip()

        self._log("INFO", f"    [browser_auto] 启动 AI 浏览器任务: {task[:60]}{'...' if len(task)>60 else ''}")
        self._log("INFO", f"    [browser_auto] LLM: {effective_provider} / {effective_model}"
                          + (" [无头]" if headless else " [有头]")
                          + (f" [模式: {mode}]"))

        # ── ai_generate 模式：让 AI 生成步骤列表，返回 JSON 步骤数组（不启动浏览器）──
        if mode == "ai_generate":
            self._log("INFO", "    [browser_auto] ai_generate 模式：AI 生成操作步骤列表")
            gen_prompt = (
                "你是一个专业的浏览器自动化专家。请将下面的任务拆解为一个步骤数组，"
                "每个步骤包含 action（open_url/click/type/get_text/screenshot/wait）和相关参数。"
                "直接返回 JSON 数组，不要任何多余说明。\n\n"
                f"任务：{task}"
            )
            try:
                self._ai_call(gen_prompt, "", model, save_result,
                              int(timeout_sec) if timeout_sec > 0 else 60,
                              "", False, "", "ai_generate")
                self._log("INFO", f"    [browser_auto] 步骤列表已生成，存入变量 {save_result}")
            except Exception as e:
                self._log("ERROR", f"    [browser_auto] ai_generate 失败: {e}")
                self.variables[save_result] = f"[错误] {e}"
            return


        script = r"""
import sys, json, asyncio, os

# 从环境变量读取参数
task         = os.environ.get("BU_TASK", "")
provider     = os.environ.get("BU_PROVIDER", "openai")
model_name   = os.environ.get("BU_MODEL", "gpt-4o-mini")
api_key      = os.environ.get("BU_API_KEY", "")
base_url     = os.environ.get("BU_BASE_URL", "")
headless     = os.environ.get("BU_HEADLESS", "1") == "1"
max_steps    = int(os.environ.get("BU_MAX_STEPS", "50"))
timeout_sec  = float(os.environ.get("BU_TIMEOUT", "120"))
close_after  = os.environ.get("BU_CLOSE_AFTER", "1") == "1"

def _progress(msg: str):
    # 实时进度行，以 PROGRESS: 前缀打印到 stdout，主进程读取后显示在日志
    print(f"PROGRESS: {msg}", flush=True)

def build_llm(provider, model_name, key, url):
    # build LLM via browser_use.llm builtin adapters, no langchain_openai needed
    p = provider.lower()
    if p == "deepseek":
        from browser_use.llm import ChatDeepSeek
        kwargs = {"model": model_name}
        if key: kwargs["api_key"] = key
        if url: kwargs["base_url"] = url
        return ChatDeepSeek(**kwargs)
    elif p == "anthropic":
        from browser_use.llm import ChatAnthropic
        kwargs = {"model": model_name}
        if key: kwargs["api_key"] = key
        return ChatAnthropic(**kwargs)
    elif p in ("google", "gemini"):
        from browser_use.llm.google import ChatGoogle
        kwargs = {"model": model_name}
        if key: kwargs["api_key"] = key
        return ChatGoogle(**kwargs)
    elif p == "ollama":
        from browser_use.llm import ChatOllama
        return ChatOllama(model=model_name)
    else:
        # openai / kimi / qwen / zhipu / baidu / azure / custom 等所有 OpenAI 兼容接口
        from browser_use.llm import ChatOpenAI
        kwargs = {"model": model_name}
        if key: kwargs["api_key"] = key
        if url: kwargs["base_url"] = url
        return ChatOpenAI(**kwargs)


async def run_agent():
    from browser_use import Agent, Browser
    from browser_use.browser.profile import BrowserProfile
    llm = build_llm(provider, model_name, api_key, base_url)
    # 禁用自动下载扩展（uBlock Origin / I don't care cookies / ClearURLs）
    # 避免每次启动时联网下载导致卡死
    try:
        profile = BrowserProfile(
            headless=headless,
            enable_default_extensions=False,
        )
        browser_instance = Browser(browser_profile=profile)
    except Exception:
        try:
            profile = BrowserProfile(headless=headless)
            browser_instance = Browser(browser_profile=profile)
        except Exception:
            try:
                browser_instance = Browser(headless=headless)
            except Exception:
                browser_instance = Browser()

    _progress("浏览器已启动，正在初始化 Agent…")

    # 创建步骤回调：每次 agent 完成一步就输出进度
    step_count = [0]
    def _on_step(state=None, output=None, **kwargs):
        step_count[0] += 1
        msg = f"步骤 {step_count[0]}"
        if output and hasattr(output, 'action'):
            try:
                act = str(output.action)[:80]
                msg += f": {act}"
            except Exception:
                pass
        elif output:
            try:
                msg += f": {str(output)[:80]}"
            except Exception:
                pass
        _progress(msg)

    try:
        agent = Agent(task=task, llm=llm, browser=browser_instance,
                      max_actions_per_step=max_steps,
                      on_step_end=_on_step)
    except TypeError:
        try:
            agent = Agent(task=task, llm=llm, browser=browser_instance,
                          max_actions_per_step=max_steps)
        except TypeError:
            agent = Agent(task=task, llm=llm, browser=browser_instance)

    _progress("Agent 已就绪，开始执行任务…")

    try:
        if timeout_sec > 0:
            result = await asyncio.wait_for(agent.run(), timeout=timeout_sec)
        else:
            result = await agent.run()
    finally:
        # 执行完毕或超时后，根据 close_after 决定是否关闭浏览器
        if close_after:
            try:
                await browser_instance.close()
                _progress("浏览器已关闭")
            except Exception:
                pass

    return result

try:
    result = asyncio.run(run_agent())
    # 提取结果文本
    if result is None:
        result_text = "[完成] 任务已执行，无返回值"
    elif hasattr(result, "final_result") and callable(result.final_result):
        result_text = str(result.final_result() or "[完成]")
    elif hasattr(result, "final_result") and not callable(result.final_result):
        result_text = str(result.final_result or "[完成]")
    else:
        result_text = str(result)
    # 提取历史
    history = []
    if hasattr(result, "history") and result.history:
        for step in result.history:
            history.append(str(step))
    print(json.dumps({"ok": True, "result": result_text, "history": history}, ensure_ascii=False))
except asyncio.TimeoutError:
    print(json.dumps({"ok": False, "error": f"任务超时（{timeout_sec}秒内未完成）"}, ensure_ascii=False))
except Exception as e:
    import traceback
    print(json.dumps({"ok": False, "error": str(e), "traceback": traceback.format_exc()}, ensure_ascii=False))
"""

        # ── 寻找合适的 Python 解释器 ──
        def _find_system_python():
            """查找系统 Python（不是 PyInstaller 的内嵌 Python / AutoFlow exe 本身）"""
            import subprocess

            def _is_real_python(path: str) -> bool:
                """判断路径是真正的 python 解释器，而非 AutoFlow exe 或其他非 python 程序"""
                basename = os.path.basename(path).lower()
                # 必须以 python 开头（python.exe / python3.exe / python3.12.exe ...）
                if not (basename.startswith("python") and basename.endswith(".exe")):
                    # Linux/macOS 允许无后缀
                    if os.path.sep == "/" and basename.startswith("python"):
                        pass
                    else:
                        return False
                return True

            def _can_import_browser_use(exe_path: str) -> bool:
                try:
                    r = subprocess.run(
                        [exe_path, "-c", "import browser_use; print('ok')"],
                        capture_output=True, text=True, timeout=15,
                        encoding="utf-8", errors="replace",
                    )
                    return r.returncode == 0 and "ok" in r.stdout
                except Exception:
                    return False

            # 1. 打包 exe 模式：sys.executable 就是 AutoFlow.exe，直接跳过
            #    源码运行模式：sys.executable 才是真正的 python，可以尝试
            if not getattr(sys, "frozen", False):
                exe = sys.executable
                if _is_real_python(exe) and _can_import_browser_use(exe):
                    return exe

            # 2. 尝试常见 Python 命令（包含版本号后缀形式）
            for cmd in ["python", "python3", "python3.11", "python3.12",
                        "python3.13", "python3.10", "py"]:
                try:
                    r = subprocess.run(
                        [cmd, "-c", "import browser_use; print('ok')"],
                        capture_output=True, text=True, timeout=15,
                        encoding="utf-8", errors="replace",
                    )
                    if r.returncode == 0 and "ok" in r.stdout:
                        return cmd
                except Exception:
                    pass

            # 3. 在 PATH 里搜索 python*.exe，跳过 AutoFlow exe
            path_dirs = os.environ.get("PATH", "").split(os.pathsep)
            for d in path_dirs:
                for name in ("python.exe", "python3.exe",
                             "python3.12.exe", "python3.11.exe", "python3.10.exe"):
                    candidate = os.path.join(d, name)
                    if os.path.isfile(candidate) and _is_real_python(candidate):
                        if _can_import_browser_use(candidate):
                            return candidate

            # 4. 扫描常见安装目录
            common_roots = [
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python"),
                os.path.expandvars(r"%APPDATA%\Python"),
                r"C:\Python312", r"C:\Python311", r"C:\Python310",
                r"C:\Python39",
            ]
            for root in common_roots:
                if not os.path.isdir(root):
                    continue
                # 第一层子目录（Python312, Python311 ...）
                try:
                    subdirs = [root] + [
                        os.path.join(root, d)
                        for d in os.listdir(root)
                        if os.path.isdir(os.path.join(root, d))
                    ]
                except OSError:
                    subdirs = [root]
                for sdir in subdirs:
                    candidate = os.path.join(sdir, "python.exe")
                    if os.path.isfile(candidate) and _is_real_python(candidate):
                        if _can_import_browser_use(candidate):
                            return candidate

            return None

        # ── 先尝试直接在当前进程 import（仅源码运行模式）──
        # 打包 exe (sys.frozen) 下 importlib.resources 无法访问外部包的数据文件
        # (.md system_prompt 模板)，必须强制走子进程（系统 Python）
        _is_frozen = getattr(sys, "frozen", False)
        if _is_frozen:
            use_subprocess = True
            self._log("INFO", "    [browser_auto] 打包运行模式，使用子进程执行 browser_use")
        else:
            try:
                importlib.import_module("browser_use")
                use_subprocess = False
                self._log("INFO", "    [browser_auto] 当前进程可用 browser_use，直接执行")
            except ImportError:
                use_subprocess = True
                self._log("INFO", "    [browser_auto] 当前进程无 browser_use，切换到子进程模式")

        if use_subprocess:
            # ── 子进程模式：调用系统 Python ──
            import subprocess, tempfile

            py_exe = _find_system_python()
            if not py_exe:
                self._log("ERROR",
                    "    [browser_auto] 未找到安装了 browser-use 的 Python 解释器！\n"
                    "    请在系统 Python 中运行：pip install browser-use\n"
                    "    然后安装浏览器：playwright install chromium")
                self.variables[save_result] = "[错误] 未找到可用的 Python + browser-use 环境"
                return

            self._log("INFO", f"    [browser_auto] 使用系统 Python: {py_exe}")

            # 写临时脚本文件（避免命令行长度限制）
            tmp_script = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", suffix=".py",
                                                 delete=False, encoding="utf-8") as f:
                    f.write(script)
                    tmp_script = f.name

                env = os.environ.copy()
                env.update({
                    "BU_TASK":        task,
                    "BU_PROVIDER":    effective_provider,
                    "BU_MODEL":       effective_model,
                    "BU_API_KEY":     api_key,
                    "BU_BASE_URL":    base_url,
                    "BU_HEADLESS":    "1" if headless else "0",
                    "BU_MAX_STEPS":   str(max_steps),
                    "BU_TIMEOUT":     str(timeout_sec),
                    "BU_CLOSE_AFTER": "1" if close_after else "0",
                    # 禁止 playwright 在 exe 里寻找 Chromium
                    "PLAYWRIGHT_BROWSERS_PATH": os.environ.get("PLAYWRIGHT_BROWSERS_PATH", ""),
                    # 禁用 browser_use 自动下载扩展（uBlock Origin / cookies / ClearURLs）
                    # 避免每次启动时联网下载导致进程卡死
                    "BROWSER_USE_DISABLE_EXTENSIONS": "1",
                })

                proc = subprocess.Popen(
                    [py_exe, tmp_script],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )

                # 用后台线程实时读取 stdout，将 PROGRESS 行实时转发到日志
                # 普通输出行（JSON 结果）收集到 stdout_lines
                import threading as _threading
                stdout_lines = []

                def _read_stdout():
                    for line in proc.stdout:
                        line = line.rstrip("\n\r")
                        if line.startswith("PROGRESS:"):
                            msg = line[len("PROGRESS:"):].strip()
                            self._log("INFO", f"    [browser_auto] ▷ {msg}")
                        else:
                            stdout_lines.append(line)

                _t = _threading.Thread(target=_read_stdout, daemon=True)
                _t.start()

                # 等待子进程，同时响应停止信号
                deadline = _time.time() + (timeout_sec + 30 if timeout_sec > 0 else 600)
                while proc.poll() is None:
                    self._check_stop()
                    _time.sleep(0.5)
                    if _time.time() > deadline:
                        proc.kill()
                        proc.wait()  # 确保进程已退出
                        self._log("WARN", "    [browser_auto] 子进程超时，已强制结束")
                        self.variables[save_result] = f"[超时] 任务在 {timeout_sec} 秒内未完成"
                        return

                # 等后台 stdout 读取线程结束（stdout 已被 _read_stdout 消费完毕）
                _t.join(timeout=5)
                stdout_data = "\n".join(stdout_lines)
                stderr_data = proc.stderr.read()

                # 过滤 stderr：只保留 WARNING/ERROR 级别，去掉 INFO 和 DEBUG 噪音
                if stderr_data.strip():
                    for line in stderr_data.splitlines():
                        s = line.strip()
                        if not s:
                            continue
                        # 只打印警告和错误行
                        low = s.lower()
                        if any(kw in low for kw in ("warning", "error", "exception", "traceback", "critical")):
                            self._log("WARN", f"    [browser_auto] {s}")

                # 解析 JSON 输出（从 stdout_lines 中找最后一个 { 开头的行）
                json_line = ""
                for line in reversed(stdout_lines):
                    line = line.strip()
                    if line.startswith("{"):
                        json_line = line
                        break

                if not json_line:
                    # 没有 JSON 输出时，打印完整 stderr 帮助诊断
                    stderr_tail = "\n".join(
                        l for l in stderr_data.strip().splitlines()[-30:]
                        if l.strip() and not l.strip().lower().startswith("info")
                    ) or stderr_data.strip()[-800:]
                    self._log("ERROR",
                        f"    [browser_auto] 子进程无 JSON 输出\n"
                        f"stdout: {stdout_data.strip()[:300]}\n"
                        f"stderr（末尾30行）:\n{stderr_tail}")
                    self.variables[save_result] = "[错误] 子进程无有效输出"
                    return

                data = _json.loads(json_line)
                if data.get("ok"):
                    result_text = data.get("result", "[完成]")
                    self.variables[save_result] = result_text
                    self._log("INFO", f"    [browser_auto] 任务完成。结果: {result_text[:100]}")
                    if save_history and data.get("history"):
                        self.variables[save_history] = _json.dumps(
                            data["history"], ensure_ascii=False)
                        self._log("INFO", f"    [browser_auto] 历史已存入 {save_history}")
                else:
                    err = data.get("error", "未知错误")
                    tb  = data.get("traceback", "")
                    self._log("ERROR", f"    [browser_auto] 执行失败: {err}")
                    if tb:
                        # 打印 traceback 的最后几行方便定位
                        tb_tail = "\n".join(tb.strip().splitlines()[-10:])
                        self._log("ERROR", f"    [browser_auto] traceback:\n{tb_tail}")
                    self.variables[save_result] = f"[错误] {err}"

            except Exception as e:
                self._log("ERROR", f"    [browser_auto] 子进程模式异常: {e}")
                self.variables[save_result] = f"[错误] {e}"
            finally:
                if tmp_script and os.path.exists(tmp_script):
                    try:
                        os.unlink(tmp_script)
                    except Exception:
                        pass

        else:
            # ── 直接在当前进程执行（源码运行模式）──
            import asyncio

            browser_use_mod = importlib.import_module("browser_use")

            def _build_browser_llm(provider: str, model_name: str, key: str, url: str):
                """build LLM via browser_use.llm builtin adapters, no langchain needed"""
                p = provider.lower()
                if p == "deepseek":
                    from browser_use.llm import ChatDeepSeek
                    kwargs = {"model": model_name}
                    if key: kwargs["api_key"] = key
                    if url: kwargs["base_url"] = url
                    return ChatDeepSeek(**kwargs)
                elif p == "anthropic":
                    from browser_use.llm import ChatAnthropic
                    kwargs = {"model": model_name}
                    if key: kwargs["api_key"] = key
                    return ChatAnthropic(**kwargs)
                elif p in ("google", "gemini"):
                    from browser_use.llm.google import ChatGoogle
                    kwargs = {"model": model_name}
                    if key: kwargs["api_key"] = key
                    return ChatGoogle(**kwargs)
                elif p == "ollama":
                    from browser_use.llm import ChatOllama
                    return ChatOllama(model=model_name)
                else:
                    # openai / kimi / qwen / zhipu / baidu / azure / custom 等所有 OpenAI 兼容接口
                    from browser_use.llm import ChatOpenAI
                    kwargs = {"model": model_name}
                    if key: kwargs["api_key"] = key
                    if url: kwargs["base_url"] = url
                    return ChatOpenAI(**kwargs)

            async def _run_task():
                Agent   = browser_use_mod.Agent
                Browser = browser_use_mod.Browser
                llm = _build_browser_llm(effective_provider, effective_model, api_key, base_url)
                # browser_use v0.12.x: 使用 BrowserProfile 配置 headless
                try:
                    from browser_use.browser.profile import BrowserProfile
                    profile = BrowserProfile(headless=headless)
                    browser_instance = Browser(browser_profile=profile)
                except Exception:
                    try:
                        browser_instance = Browser(headless=headless)
                    except Exception:
                        browser_instance = Browser()
                try:
                    agent = Agent(task=task, llm=llm, browser=browser_instance,
                                  max_actions_per_step=max_steps)
                except TypeError:
                    agent = Agent(task=task, llm=llm, browser=browser_instance)
                if timeout_sec > 0:
                    return await asyncio.wait_for(agent.run(), timeout=timeout_sec)
                return await agent.run()

            try:
                # 兼容已有事件循环（Qt 环境）
                import threading
                result_holder = [None]
                err_holder    = [None]

                def thread_target():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        result_holder[0] = new_loop.run_until_complete(_run_task())
                    except Exception as e:
                        err_holder[0] = e
                    finally:
                        new_loop.close()

                t = threading.Thread(target=thread_target, daemon=True)
                t.start()

                deadline = _time.time() + (timeout_sec + 10 if timeout_sec > 0 else 3600)
                while t.is_alive():
                    self._check_stop()
                    _time.sleep(0.3)
                    if _time.time() > deadline:
                        self._log("WARN", "    [browser_auto] 等待线程超时")
                        break

                if err_holder[0]:
                    raise err_holder[0]

                result = result_holder[0]
                if result is None:
                    result_text = "[完成] 任务已执行，无返回值"
                elif hasattr(result, "final_result"):
                    result_text = str(result.final_result() or "[完成]")
                else:
                    result_text = str(result)

                self.variables[save_result] = result_text
                self._log("INFO", f"    [browser_auto] 任务完成。结果: {result_text[:100]}")

                if save_history:
                    history = []
                    if hasattr(result, "history") and result.history:
                        for step in result.history:
                            history.append(str(step))
                    self.variables[save_history] = _json.dumps(history, ensure_ascii=False)
                    self._log("INFO", f"    [browser_auto] 历史已存入 {save_history}")

            except asyncio.TimeoutError:
                self._log("WARN", f"    [browser_auto] 任务超时（{timeout_sec}秒）")
                self.variables[save_result] = f"[超时] 任务在 {timeout_sec} 秒内未完成"
            except ImportError as e:
                self._log("ERROR", f"    [browser_auto] 缺少依赖: {e}\n"
                                   "    安装: pip install browser-use langchain-openai")
                self.variables[save_result] = f"[错误] 缺少依赖: {e}"
            except Exception as e:
                self._log("ERROR", f"    [browser_auto] 执行失败: {e}")
                self.variables[save_result] = f"[错误] {e}"

    def _ai_call(self, prompt: str, system_prompt: str, model: str,
                 save_to: str, timeout: int, temperature,
                 append_history: bool, history_var: str, block_type: str):
        """调用 AI 大模型接口（兼容 OpenAI 接口）"""
        import urllib.request, urllib.error, json as _json, ssl

        cfg = self.config
        api_key  = getattr(cfg, "ai_api_key",  "").strip()
        base_url = getattr(cfg, "ai_base_url", "").strip()
        default_model = getattr(cfg, "ai_model", "gpt-4o-mini")
        default_temp  = getattr(cfg, "ai_temperature", 0.7)
        max_tokens    = getattr(cfg, "ai_max_tokens",  2048)
        default_sys   = getattr(cfg, "ai_system_prompt", "").strip()

        if not api_key:
            self._log("ERROR", "    [AI] 未配置 API Key，请前往「设置→AI」填写")
            self.variables[save_to] = ""
            return

        if not base_url:
            base_url = "https://api.openai.com/v1"
        base_url = base_url.rstrip("/")

        used_model = model or default_model
        used_sys   = system_prompt.strip() or default_sys

        # 解析 temperature
        try:
            used_temp = float(str(temperature).strip()) if str(temperature).strip() else default_temp
        except Exception:
            used_temp = default_temp

        # 构建消息列表
        messages = []
        if used_sys:
            messages.append({"role": "system", "content": used_sys})

        # 连续对话：从变量中读取历史记录
        if append_history and history_var:
            history = self.variables.get(history_var, [])
            if isinstance(history, list):
                messages.extend(history)

        messages.append({"role": "user", "content": prompt})

        payload = _json.dumps({
            "model": used_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": used_temp,
        }).encode("utf-8")

        url = f"{base_url}/chat/completions"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST"
        )

        self._log("INFO", f"    [AI] 调用 {used_model} …")
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                body = _json.loads(resp.read().decode("utf-8"))
            reply = body["choices"][0]["message"]["content"]
            self.variables[save_to] = reply
            self._log("INFO", f"    [AI] 回复已存入 {save_to}（{len(reply)} 字）")

            # 更新对话历史
            if append_history and history_var:
                history = list(self.variables.get(history_var, []))
                if not isinstance(history, list):
                    history = []
                history.append({"role": "user", "content": prompt})
                history.append({"role": "assistant", "content": reply})
                self.variables[history_var] = history

        except urllib.error.HTTPError as e:
            try:
                err_body = _json.loads(e.read().decode("utf-8"))
                err_msg = err_body.get("error", {}).get("message", str(e))
            except Exception:
                err_msg = str(e)
            self._log("ERROR", f"    [AI] HTTP {e.code}: {err_msg}")
            self.variables[save_to] = f"[错误] HTTP {e.code}: {err_msg}"
        except Exception as e:
            self._log("ERROR", f"    [AI] 调用失败: {e}")
            self.variables[save_to] = f"[错误] {e}"

    def _run_loop_flat(self, block: Block, body: List[Block]):
        """执行扁平模式的循环（loop块 + 循环体列表）"""
        p         = block.params
        loop_type = p.get("loop_type", "count")
        count     = int(resolve_number(p.get("count", 3), self.variables))
        target    = resolve_value(p.get("target", ""), self.variables)
        value     = resolve_value(p.get("value", ""), self.variables)

        self._log("INFO", f"    循环开始 [{loop_type}] 共 {count if loop_type=='count' else '∞'} 次")
        iteration = 0
        while True:
            self._check_stop()
            if loop_type == "count":
                if iteration >= count:
                    break
            elif loop_type == "while_process":
                if not self._process_exists(target):
                    break
            elif loop_type == "while_window":
                if not self._window_exists(target):
                    break
            elif loop_type == "while_file_exists":
                if not os.path.exists(target):
                    break
            elif loop_type == "while_variable":
                if str(self.variables.get(target, "")) != value:
                    break
            # infinite 不 break

            self.variables["_loop_index"] = iteration
            try:
                self._run_blocks(body)
            except BreakLoopException:
                break
            iteration += 1
        self._log("INFO", f"    循环结束，共执行 {iteration} 次")

    def _run_loop(self, block: Block):
        """兼容旧的 children_loop 模式"""
        self._run_loop_flat(block, block.children_loop)

    def _eval_condition(self, p: dict) -> bool:
        ct     = p.get("condition_type", "always_true")
        target = resolve_value(p.get("target", ""), self.variables)
        value  = resolve_value(p.get("value", ""), self.variables)

        if ct == "always_true":
            return True
        elif ct == "process_exists":
            return self._process_exists(target)
        elif ct == "window_exists":
            return self._window_exists(target)
        elif ct == "file_exists":
            return os.path.exists(target)
        elif ct == "file_changed":
            mtime = self.variables.get(f"__mtime_{target}", None)
            cur   = os.path.getmtime(target) if os.path.exists(target) else None
            self.variables[f"__mtime_{target}"] = cur
            return cur != mtime
        elif ct == "variable_equals":
            return str(self.variables.get(target, "")) == value
        elif ct == "variable_gt":
            try:
                return float(self.variables.get(target, 0)) > float(value)
            except Exception:
                return False
        elif ct == "variable_lt":
            try:
                return float(self.variables.get(target, 0)) < float(value)
            except Exception:
                return False
        elif ct == "variable_contains":
            return value in str(self.variables.get(target, ""))
        elif ct == "clipboard_contains":
            # target 为要检测的文本，留空=只要剪贴板有内容即满足
            cb_text = self._get_clipboard_text()
            if not target:
                return bool(cb_text)
            return target.lower() in (cb_text or "").lower()
        elif ct == "internet_connected":
            return self._wininet_connected()
        elif ct == "ping_latency_gt":
            # target=主机, value=阈值ms；延迟超过阈值返回 True
            try:
                threshold = float(value) if value else 200.0
                latency = self._get_ping_latency_ms(target)
                return latency is not None and latency > threshold
            except Exception:
                return False
        elif ct == "ping_latency_lt":
            # target=主机, value=阈值ms；延迟低于阈值（且可达）返回 True
            try:
                threshold = float(value) if value else 200.0
                latency = self._get_ping_latency_ms(target)
                return latency is not None and latency < threshold
            except Exception:
                return False
        return False

    def _get_clipboard_text(self) -> str:
        """获取当前剪贴板文本（Win32 API，不依赖Qt）"""
        try:
            import ctypes
            CF_UNICODETEXT = 13
            if not ctypes.windll.user32.OpenClipboard(None):
                return ""
            try:
                h = ctypes.windll.user32.GetClipboardData(CF_UNICODETEXT)
                if not h:
                    return ""
                p = ctypes.windll.kernel32.GlobalLock(h)
                if not p:
                    return ""
                try:
                    return ctypes.wstring_at(p)
                finally:
                    ctypes.windll.kernel32.GlobalUnlock(h)
            finally:
                ctypes.windll.user32.CloseClipboard()
        except Exception:
            return ""

    def _wininet_connected(self) -> bool:
        """Windows WinINet 系统级网络连通性检测"""
        try:
            import ctypes
            flags = ctypes.c_ulong(0)
            connected = ctypes.windll.wininet.InternetGetConnectedState(
                ctypes.byref(flags), 0)
            return bool(connected)
        except Exception:
            pass
        try:
            stats = psutil.net_if_stats()
            return any(s.isup for name, s in stats.items()
                       if name.lower() not in ("lo", "loopback"))
        except Exception:
            return False

    def _get_ping_latency_ms(self, host: str, count: int = 1) -> Optional[float]:
        """
        用系统 ping 命令获取延迟(ms)，返回 None 表示超时/不可达。
        使用 subprocess 调用系统自带 ping，无需管理员权限。
        Windows: ping -n count host；解析 "平均 = XXms" / "Average = XXms"
        """
        import re
        try:
            result = subprocess.run(
                ["ping", "-n", str(max(1, count)), host],
                capture_output=True, text=True, timeout=15,
                encoding="gbk", errors="replace",
                creationflags=0x08000000  # CREATE_NO_WINDOW，静默不弹窗
            )
            output = result.stdout
            # 解析中文系统: "平均 = 12ms" 或英文: "Average = 12ms"
            m = re.search(r'(?:平均|Average)\s*=\s*(\d+)\s*ms', output, re.IGNORECASE)
            if m:
                return float(m.group(1))
            # 备用：解析单次回复行中的延迟 "时间=12ms" 或 "time=12ms"
            m2 = re.findall(r'(?:时间|time)\s*[=<]\s*(\d+)\s*ms', output, re.IGNORECASE)
            if m2:
                vals = [float(v) for v in m2]
                return sum(vals) / len(vals)
        except Exception as e:
            logger.debug(f"ping 执行失败: {e}")
        return None

    def _process_exists(self, name: str) -> bool:
        for proc in psutil.process_iter(["name"]):
            try:
                if fnmatch.fnmatch(proc.info["name"].lower(), name.lower()):
                    return True
            except Exception:
                pass
        return False

    def _window_exists(self, title_pattern: str) -> bool:
        try:
            import win32gui
            result = []
            def cb(hwnd, _):
                t = win32gui.GetWindowText(hwnd)
                if fnmatch.fnmatch(t.lower(), title_pattern.lower()):
                    result.append(hwnd)
            win32gui.EnumWindows(cb, None)
            return bool(result)
        except Exception:
            return False

    def _close_window(self, title_pattern: str, force: bool):
        try:
            import win32gui, win32con, win32process
            hwnds = []
            def cb(hwnd, _):
                t = win32gui.GetWindowText(hwnd)
                if fnmatch.fnmatch(t.lower(), title_pattern.lower()):
                    hwnds.append(hwnd)
            win32gui.EnumWindows(cb, None)
            for hwnd in hwnds:
                if force:
                    # 强制关闭：找到进程并 kill
                    try:
                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                        proc = psutil.Process(pid)
                        proc.kill()
                    except Exception:
                        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                else:
                    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            self._log("INFO", f"    已发送关闭消息给 {len(hwnds)} 个窗口: {title_pattern}")
        except Exception as e:
            self._log("WARN", f"    关闭窗口失败: {e}")

    def _close_foreground_window(self, title: str):
        """
        关闭前台（当前激活）窗口，或关闭指定标题的窗口。
        使用 PostMessage WM_CLOSE，不杀进程，不影响后台同名窗口。
        """
        import ctypes
        import ctypes.wintypes as wt
        WM_CLOSE = 0x0010

        try:
            if title:
                # 有标题：用 FindWindow 精确查找，只发消息不杀进程
                hwnd = ctypes.windll.user32.FindWindowW(None, title)
                if hwnd:
                    ctypes.windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                    self._log("INFO", f"    已发送 WM_CLOSE 给窗口 '{title}' (hwnd={hwnd})")
                else:
                    self._log("WARN", f"    未找到窗口: '{title}'")
            else:
                # 无标题：获取当前前台窗口并关闭
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                if hwnd:
                    # 获取窗口标题用于日志
                    buf = ctypes.create_unicode_buffer(256)
                    ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
                    win_title = buf.value or "(无标题)"
                    ctypes.windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                    self._log("INFO", f"    已关闭前台窗口: '{win_title}' (hwnd={hwnd})")
                else:
                    self._log("WARN", "    当前没有前台窗口")
        except Exception as e:
            self._log("WARN", f"    关闭前台窗口失败: {e}")

    def _kill_process(self, name: str):
        killed = 0
        for proc in psutil.process_iter(["name", "pid"]):
            try:
                if fnmatch.fnmatch(proc.info["name"].lower(), name.lower()):
                    proc.kill()
                    killed += 1
            except Exception:
                pass
        self._log("INFO", f"    已终止 {killed} 个进程: {name}")

    def _wait_window(self, title_pattern: str, timeout: float) -> bool:
        self._log("INFO", f"    等待窗口: {title_pattern}")
        deadline = time.time() + (timeout if timeout > 0 else 1e9)
        while time.time() < deadline:
            self._check_stop()
            if self._window_exists(title_pattern):
                self._log("INFO", f"    ✅ 窗口已出现: {title_pattern}")
                return True
            time.sleep(0.5)
        self._log("WARN", f"    ⏱ 等待窗口超时: {title_pattern}")
        return False

    def _wait_process(self, name: str, timeout: float) -> bool:
        self._log("INFO", f"    等待进程: {name}")
        deadline = time.time() + (timeout if timeout > 0 else 1e9)
        while time.time() < deadline:
            self._check_stop()
            if self._process_exists(name):
                self._log("INFO", f"    ✅ 进程已出现: {name}")
                return True
            time.sleep(0.5)
        self._log("WARN", f"    ⏱ 等待进程超时: {name}")
        return False

    # ── hwnd/pid 扩展方法 ──

    def _parse_hwnd(self, hwnd_str: str) -> int:
        """将字符串形式的句柄(十进制或十六进制)转为整数"""
        s = hwnd_str.strip()
        try:
            return int(s, 16) if s.lower().startswith("0x") else int(s)
        except Exception:
            return 0

    def _close_window_by_hwnd(self, hwnd_str: str, force: bool):
        """通过句柄关闭窗口"""
        import ctypes
        hwnd = self._parse_hwnd(hwnd_str)
        if not hwnd:
            self._log("WARN", f"    无效的窗口句柄: {hwnd_str}")
            return
        try:
            if force:
                import win32process, win32con, win32api
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                handle = win32api.OpenProcess(win32con.PROCESS_TERMINATE, False, pid)
                win32api.TerminateProcess(handle, 0)
            else:
                ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)
            self._log("INFO", f"    已关闭句柄窗口: hwnd={hwnd}")
        except Exception as e:
            self._log("WARN", f"    关闭句柄窗口失败: {e}")

    def _close_window_by_process(self, proc_name: str, force: bool):
        """关闭某进程的所有主窗口"""
        try:
            import win32gui, win32con, win32process
            pids = set()
            for proc in psutil.process_iter(["name", "pid"]):
                if fnmatch.fnmatch(proc.info["name"].lower(), proc_name.lower()):
                    pids.add(proc.info["pid"])
            closed = 0
            def cb(hwnd, _):
                if win32gui.IsWindowVisible(hwnd):
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if pid in pids:
                        if force:
                            try:
                                psutil.Process(pid).kill()
                            except Exception:
                                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                        else:
                            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                        closed  # noqa
            win32gui.EnumWindows(cb, None)
            self._log("INFO", f"    已处理进程 {proc_name} 的窗口（pids={pids}）")
        except Exception as e:
            self._log("WARN", f"    按进程关闭窗口失败: {e}")

    def _kill_process_by_pid(self, pid_str: str):
        """按 PID 终止进程"""
        try:
            pid = int(pid_str.strip())
            proc = psutil.Process(pid)
            proc.kill()
            self._log("INFO", f"    已终止 PID={pid}")
        except Exception as e:
            self._log("WARN", f"    按PID终止失败: {e}")

    def _kill_process_by_window(self, title_pattern: str):
        """终止拥有指定标题窗口的进程"""
        try:
            import win32gui, win32process
            pids = set()
            def cb(hwnd, _):
                t = win32gui.GetWindowText(hwnd)
                if fnmatch.fnmatch(t.lower(), title_pattern.lower()):
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    pids.add(pid)
            win32gui.EnumWindows(cb, None)
            for pid in pids:
                try:
                    psutil.Process(pid).kill()
                except Exception:
                    pass
            self._log("INFO", f"    按窗口标题终止了 {len(pids)} 个进程: {title_pattern}")
        except Exception as e:
            self._log("WARN", f"    按窗口标题终止进程失败: {e}")

    def _wait_window_hwnd(self, hwnd_str: str, timeout: float) -> bool:
        """等待指定 hwnd 的窗口出现（变为可见）"""
        import ctypes
        hwnd = self._parse_hwnd(hwnd_str)
        if not hwnd:
            return False
        self._log("INFO", f"    等待窗口句柄: {hwnd_str}")
        deadline = time.time() + (timeout if timeout > 0 else 1e9)
        while time.time() < deadline:
            self._check_stop()
            if ctypes.windll.user32.IsWindowVisible(hwnd):
                self._log("INFO", f"    ✅ 句柄窗口已出现: hwnd={hwnd}")
                return True
            time.sleep(0.5)
        self._log("WARN", f"    ⏱ 等待句柄窗口超时: {hwnd_str}")
        return False

    def _wait_window_process(self, proc_name: str, timeout: float) -> bool:
        """等待某进程出现且有可见窗口"""
        self._log("INFO", f"    等待进程主窗口: {proc_name}")
        deadline = time.time() + (timeout if timeout > 0 else 1e9)
        while time.time() < deadline:
            self._check_stop()
            if self._process_exists(proc_name) and self._window_exists_by_process(proc_name):
                self._log("INFO", f"    ✅ 进程窗口已出现: {proc_name}")
                return True
            time.sleep(0.5)
        self._log("WARN", f"    ⏱ 等待进程窗口超时: {proc_name}")
        return False

    def _wait_process_pid(self, pid_str: str, timeout: float) -> bool:
        """等待指定 PID 的进程存在"""
        try:
            pid = int(pid_str.strip())
        except Exception:
            return False
        self._log("INFO", f"    等待 PID={pid} 进程")
        deadline = time.time() + (timeout if timeout > 0 else 1e9)
        while time.time() < deadline:
            self._check_stop()
            if psutil.pid_exists(pid):
                self._log("INFO", f"    ✅ PID={pid} 进程已存在")
                return True
            time.sleep(0.5)
        self._log("WARN", f"    ⏱ 等待 PID={pid} 超时")
        return False

    def _window_exists_by_process(self, proc_name: str) -> bool:
        """判断某进程是否有可见窗口"""
        try:
            import win32gui, win32process
            pids = {proc.info["pid"] for proc in psutil.process_iter(["name","pid"])
                    if fnmatch.fnmatch(proc.info["name"].lower(), proc_name.lower())}
            result = []
            def cb(hwnd, _):
                if win32gui.IsWindowVisible(hwnd):
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if pid in pids:
                        result.append(hwnd)
            win32gui.EnumWindows(cb, None)
            return bool(result)
        except Exception:
            return False

    def _run_command(self, cmd: str, shell: str, wait: bool, save_output: str,
                     as_admin: bool = False, hidden: bool = False):
        self._log("INFO", f"    执行命令 [{shell}{'|管理员' if as_admin else ''}{'|静默' if hidden else ''}]: {cmd[:60]}...")
        try:
            creation_flags = 0x08000000 if hidden else 0  # CREATE_NO_WINDOW

            # bat: 将命令内容写入临时 .bat 文件再执行
            if shell == "bat":
                import tempfile
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".bat", delete=False,
                    encoding="gbk", errors="replace"
                ) as f:
                    f.write("@echo off\r\n")
                    f.write(cmd)
                    bat_path = f.name
                executable = bat_path
                flag       = None  # 直接运行 .bat
            elif shell == "powershell":
                executable = "powershell.exe"
                flag       = "-Command"
                bat_path   = None
            elif shell == "python":
                executable = sys.executable
                flag       = "-c"
                bat_path   = None
            elif shell in ("wscript", "bash"):
                executable = shell
                flag       = None
                bat_path   = None
            else:  # cmd（默认）
                executable = "cmd.exe"
                flag       = "/c"
                bat_path   = None

            if as_admin:
                import ctypes
                if shell == "bat":
                    params = ""
                    target = executable
                elif flag:
                    params = f'{flag} {cmd}'
                    target = executable
                else:
                    params = cmd
                    target = executable
                show_flag = 0 if hidden else 1  # SW_HIDE / SW_SHOWNORMAL
                ret = ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", target, params, None, show_flag
                )
                if ret <= 32:
                    self._log("WARN", f"    管理员启动失败，错误码: {ret}")
                elif wait:
                    time.sleep(0.5)
            else:
                if shell == "bat":
                    popen_args = [executable]
                elif flag:
                    popen_args = [executable, flag, cmd]
                else:
                    popen_args = [executable, cmd]

                proc = subprocess.Popen(
                    popen_args,
                    stdout=subprocess.PIPE if save_output else None,
                    stderr=subprocess.PIPE if save_output else None,
                    text=True, shell=False,
                    creationflags=creation_flags
                )
                if wait:
                    out, err = proc.communicate()
                    if save_output and out:
                        self.variables[save_output] = out.strip()
                        self._log("INFO", f"    命令输出已存入变量 {save_output}")
                # 清理临时 bat 文件
                if bat_path:
                    try:
                        import os as _os
                        if wait:
                            _os.unlink(bat_path)
                    except Exception:
                        pass
        except Exception as e:
            self._log("ERROR", f"    命令执行失败: {e}")

    def _wait_file_change(self, path: str, event: str, timeout: float):
        import hashlib
        def file_hash(p):
            try:
                h = hashlib.md5()
                with open(p, "rb") as f:
                    h.update(f.read(65536))
                return h.hexdigest()
            except Exception:
                return None

        self._log("INFO", f"    等待文件变化: {path}")
        initial_hash    = file_hash(path) if os.path.exists(path) else None
        initial_exists  = os.path.exists(path)
        deadline = time.time() + (timeout if timeout > 0 else 1e9)
        while time.time() < deadline:
            self._check_stop()
            cur_exists = os.path.exists(path)
            cur_hash   = file_hash(path) if cur_exists else None
            triggered = False
            if event in ("any", "created") and cur_exists and not initial_exists:
                triggered = True
            elif event in ("any", "deleted") and not cur_exists and initial_exists:
                triggered = True
            elif event in ("any", "modified") and cur_hash != initial_hash and cur_hash is not None:
                triggered = True
            if triggered:
                self._log("INFO", f"    ✅ 文件变化已检测")
                return
            time.sleep(0.5)
        self._log("WARN", f"    ⏱ 等待文件变化超时")

    def _send_media_key(self, action: str):
        try:
            import ctypes
            VK_MAP = {"play_pause": 0xB3, "next_track": 0xB0, "prev_track": 0xB1}
            vk = VK_MAP.get(action, 0xB3)
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
            self._log("INFO", f"    媒体控制: {action}")
        except Exception as e:
            self._log("WARN", f"    媒体控制失败: {e}")

    def _set_volume(self, level: int, target: str = "", target_type: str = "global"):
        """
        设置音量。
        target_type: global=全局主音量, process=按进程名, window=按窗口标题（找进程PID）
        使用 Windows Core Audio API (ISimpleAudioVolume) 实现应用级音量控制。
        """
        level_scalar = max(0.0, min(1.0, level / 100.0))
        try:
            import ctypes, ctypes.util
            # 尝试加载 pycaw (推荐安装: pip install pycaw comtypes)
            try:
                from ctypes import cast, POINTER
                from comtypes import CLSCTX_ALL
                from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume, ISimpleAudioVolume
                _pycaw_ok = True
            except ImportError:
                _pycaw_ok = False

            if target_type == "global" or not target:
                # 全局主音量
                if _pycaw_ok:
                    devices = AudioUtilities.GetSpeakers()
                    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                    vol_ctrl = cast(interface, POINTER(IAudioEndpointVolume))
                    vol_ctrl.SetMasterVolumeLevelScalar(level_scalar, None)
                    self._log("INFO", f"    全局音量设置为 {level}%")
                else:
                    # 回退：用系统 API SendMessageW
                    APPCOMMAND_VOLUME_MUTE = 8
                    # 无法精确设置百分比，只能用 nircmd 回退
                    vol = int(65535 * level / 100)
                    subprocess.Popen(f"nircmd.exe setsysvolume {vol}", shell=True)
                    self._log("INFO", f"    全局音量设置为 {level}%（nircmd）")
                return

            # 应用级音量 (通过 pycaw)
            if not _pycaw_ok:
                self._log("WARN", "    应用级音量控制需要 pycaw，请 pip install pycaw comtypes")
                return

            # 找到目标进程PID
            target_pids: set = set()
            if target_type == "process":
                # 按进程名匹配
                for proc in psutil.process_iter(['pid', 'name']):
                    if fnmatch.fnmatch(proc.info['name'].lower(), target.lower()):
                        target_pids.add(proc.info['pid'])
            elif target_type == "window":
                # 按窗口标题找PID
                import ctypes as _ct
                pid_buf = _ct.c_ulong()
                def _enum_cb(hwnd, _):
                    buf = _ct.create_unicode_buffer(256)
                    _ct.windll.user32.GetWindowTextW(hwnd, buf, 256)
                    title = buf.value
                    if title and fnmatch.fnmatch(title.lower(), target.lower()):
                        _ct.windll.user32.GetWindowThreadProcessId(hwnd, _ct.byref(pid_buf))
                        target_pids.add(pid_buf.value)
                    return True
                WNDENUMPROC = _ct.WINFUNCTYPE(_ct.c_bool, _ct.c_int, _ct.c_int)
                _ct.windll.user32.EnumWindows(WNDENUMPROC(_enum_cb), 0)

            if not target_pids:
                self._log("WARN", f"    未找到目标进程/窗口: {target}")
                return

            # 设置每个匹配进程的音量
            sessions = AudioUtilities.GetAllSessions()
            matched = 0
            for session in sessions:
                if session.Process and session.Process.pid in target_pids:
                    vol_ctrl = session._ctl.QueryInterface(ISimpleAudioVolume)
                    vol_ctrl.SetMasterVolume(level_scalar, None)
                    matched += 1
            if matched:
                self._log("INFO", f"    已设置 {matched} 个应用的音量为 {level}%: {target}")
            else:
                self._log("WARN", f"    找到进程但无音频会话(进程可能没有播放音频): {target}")
        except Exception as e:
            self._log("WARN", f"    音量设置失败: {e}")

    def _show_notification(self, title: str, message: str, timeout: int):
        """
        发送系统通知，多重降级：
        1. winrt（Windows 10+ 原生 Toast，无需第三方包）
        2. win10toast（第三方，pip install win10toast）
        3. plyer（兼容性广，但部分环境不可用）
        4. Win32 Shell_NotifyIcon ctypes（纯标准库）
        5. 静默忽略（记录 WARN）
        """
        # ── 方案1：winrt Windows.UI.Notifications ──
        try:
            from winrt.windows.ui.notifications import (
                ToastNotificationManager, ToastNotification, ToastTemplateType
            )
            from winrt.windows.data.xml.dom import XmlDocument
            app_id = "AutoFlow"
            template = ToastNotificationManager.get_template_content(
                ToastTemplateType.TOAST_TEXT02)
            texts = template.get_elements_by_tag_name("text")
            texts[0].append_child(template.create_text_node(title))
            texts[1].append_child(template.create_text_node(message))
            notifier = ToastNotificationManager.create_toast_notifier(app_id)
            notif = ToastNotification(template)
            notifier.show(notif)
            self._log("INFO", f"    通知已发送(winrt): {title}")
            return
        except Exception:
            pass

        # ── 方案2：win10toast ──
        try:
            from win10toast import ToastNotifier
            _toast = ToastNotifier()
            _toast.show_toast(title, message, duration=timeout, threaded=True)
            self._log("INFO", f"    通知已发送(win10toast): {title}")
            return
        except Exception:
            pass

        # ── 方案3：plyer ──
        try:
            from plyer import notification
            notification.notify(title=title, message=message,
                                timeout=timeout, app_name="AutoFlow")
            self._log("INFO", f"    通知已发送(plyer): {title}")
            return
        except Exception:
            pass

        # ── 方案4：纯 Win32 ctypes Shell_NotifyIcon ──
        try:
            import ctypes, ctypes.wintypes as wt
            _NIM_ADD      = 0x00000000
            _NIM_MODIFY   = 0x00000001
            _NIM_DELETE   = 0x00000002
            _NIF_MESSAGE  = 0x00000001
            _NIF_ICON     = 0x00000002
            _NIF_TIP      = 0x00000004
            _NIF_INFO     = 0x00000010
            _NIIF_INFO    = 0x00000001
            _WM_USER      = 0x0400

            class NOTIFYICONDATA(ctypes.Structure):
                _fields_ = [
                    ("cbSize",           wt.DWORD),
                    ("hWnd",             wt.HWND),
                    ("uID",              wt.UINT),
                    ("uFlags",           wt.UINT),
                    ("uCallbackMessage", wt.UINT),
                    ("hIcon",            wt.HICON),
                    ("szTip",            wt.WCHAR * 128),
                    ("dwState",          wt.DWORD),
                    ("dwStateMask",      wt.DWORD),
                    ("szInfo",           wt.WCHAR * 256),
                    ("uTimeout",         wt.UINT),
                    ("szInfoTitle",      wt.WCHAR * 64),
                    ("dwInfoFlags",      wt.DWORD),
                ]

            shell32 = ctypes.windll.shell32
            user32  = ctypes.windll.user32

            # 创建一个隐藏窗口作为宿主
            hwnd = user32.CreateWindowExW(
                0, "STATIC", "AF_NOTIF", 0, 0, 0, 0, 0, 0, 0, 0, None)

            nid = NOTIFYICONDATA()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
            nid.hWnd   = hwnd
            nid.uID    = 1
            nid.uFlags = _NIF_ICON | _NIF_TIP | _NIF_INFO | _NIF_MESSAGE
            nid.uCallbackMessage = _WM_USER + 20
            nid.hIcon  = user32.LoadIconW(0, 32512)  # IDI_APPLICATION
            nid.szTip  = "AutoFlow"
            nid.szInfo      = message[:255]
            nid.szInfoTitle = title[:63]
            nid.uTimeout    = timeout * 1000
            nid.dwInfoFlags = _NIIF_INFO

            shell32.Shell_NotifyIconW(_NIM_ADD, ctypes.byref(nid))
            import time as _t; _t.sleep(timeout)
            shell32.Shell_NotifyIconW(_NIM_DELETE, ctypes.byref(nid))
            user32.DestroyWindow(hwnd)
            self._log("INFO", f"    通知已发送(Win32): {title}")
            return
        except Exception:
            pass

        # ── 最终降级：静默忽略，只记录日志 ──
        self._log("WARN", f"    通知发送失败（当前环境不支持系统通知），已跳过: {title}")

    def _send_email(self, to: str, subject: str, body: str):
        import smtplib
        from email.mime.text import MIMEText
        from email.header import Header
        from email.utils import parseaddr, formataddr
        cfg = self.config
        try:
            # 提取纯邮件地址（兼容 "昵称 <email>" 格式）
            _, from_addr = parseaddr(cfg.smtp_user)
            if not from_addr:
                from_addr = cfg.smtp_user.strip()
            _, to_addr = parseaddr(to)
            if not to_addr:
                to_addr = to.strip()

            msg = MIMEText(body, "plain", "utf-8")
            msg["From"]    = formataddr(("AutoFlow", from_addr))
            msg["To"]      = to_addr
            msg["Subject"] = Header(subject, "utf-8")

            if cfg.smtp_ssl:
                server = smtplib.SMTP_SSL(cfg.smtp_server, cfg.smtp_port, timeout=10)
            else:
                server = smtplib.SMTP(timeout=10)
                server.connect(cfg.smtp_server, cfg.smtp_port)
                server.ehlo()
                server.starttls()
                server.ehlo()
            server.login(from_addr, cfg.smtp_password)
            server.sendmail(from_addr, [to_addr], msg.as_string())
            server.quit()
            self._log("INFO", f"    邮件已发送至 {to_addr}")
        except Exception as e:
            self._log("ERROR", f"    邮件发送失败: {e}")

    def _system_action(self, action: str, delay: int):
        cmds = {
            "shutdown":  f"shutdown /s /t {delay}",
            "restart":   f"shutdown /r /t {delay}",
            "logoff":    f"shutdown /l /t {delay}",
            "sleep":     "rundll32.exe powrprof.dll,SetSuspendState 0,1,0",
            "hibernate": "rundll32.exe powrprof.dll,SetSuspendState 1,1,0",
        }
        cmd = cmds.get(action, "")
        if cmd:
            subprocess.Popen(cmd, shell=True)
            self._log("INFO", f"    系统操作: {action}")

    def _take_screenshot(self, mode: str, save_dir: str, filename_fmt: str,
                          fmt: str, region: str):
        """截图增强版：支持保存文件/复制剪贴板/两者兼有，可自定义命名"""
        try:
            import ctypes
            import ctypes.wintypes
            import struct
            import zlib
            from datetime import datetime as _dt

            user32  = ctypes.windll.user32
            gdi32   = ctypes.windll.gdi32

            # 获取截图区域
            if region == "active_window":
                hwnd = user32.GetForegroundWindow()
                rect = ctypes.wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                x, y = rect.left, rect.top
                sw = rect.right - rect.left
                sh = rect.bottom - rect.top
                if sw <= 0 or sh <= 0:
                    x, y, sw, sh = 0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
            else:
                x, y = 0, 0
                sw = user32.GetSystemMetrics(0)
                sh = user32.GetSystemMetrics(1)

            # 截图
            hdc_screen = user32.GetDC(None)
            hdc_mem    = gdi32.CreateCompatibleDC(hdc_screen)
            hbmp       = gdi32.CreateCompatibleBitmap(hdc_screen, sw, sh)
            gdi32.SelectObject(hdc_mem, hbmp)
            gdi32.BitBlt(hdc_mem, 0, 0, sw, sh, hdc_screen, x, y, 0x00CC0020)

            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [
                    ("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                    ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                    ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                    ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                    ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                    ("biClrImportant", ctypes.c_uint32),
                ]

            bih = BITMAPINFOHEADER()
            bih.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bih.biWidth = sw; bih.biHeight = -sh
            bih.biPlanes = 1; bih.biBitCount = 24; bih.biCompression = 0

            row_bytes = (sw * 3 + 3) & ~3
            buf = ctypes.create_string_buffer(row_bytes * sh)
            gdi32.GetDIBits(hdc_mem, hbmp, 0, sh, buf, ctypes.byref(bih), 0)

            gdi32.DeleteObject(hbmp)
            gdi32.DeleteDC(hdc_mem)
            user32.ReleaseDC(None, hdc_screen)

            # 构建 RGB rows
            raw_bgr = buf.raw
            rgb_rows = []
            for row_y in range(sh):
                row_start = row_y * row_bytes
                row = bytearray()
                for px in range(sw):
                    b = raw_bgr[row_start + px * 3]
                    g = raw_bgr[row_start + px * 3 + 1]
                    r = raw_bgr[row_start + px * 3 + 2]
                    row += bytes([r, g, b])
                rgb_rows.append(bytes(row))

            # 编码为 PNG bytes
            def png_chunk(tag, data):
                c = zlib.crc32(tag + data) & 0xFFFFFFFF
                return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", c)

            ihdr = struct.pack(">IIBBBBB", sw, sh, 8, 2, 0, 0, 0)
            idat_raw = b"".join(b"\x00" + row for row in rgb_rows)
            idat     = zlib.compress(idat_raw, 6)
            png_bytes = (b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", ihdr)
                         + png_chunk(b"IDAT", idat) + png_chunk(b"IEND", b""))

            # 生成文件名
            now = _dt.now()
            idx = getattr(self, "_screenshot_index", 0) + 1
            self._screenshot_index = idx
            name = filename_fmt
            name = name.replace("{datetime}", now.strftime("%Y%m%d_%H%M%S"))
            name = name.replace("{date}",     now.strftime("%Y%m%d"))
            name = name.replace("{time}",     now.strftime("%H%M%S"))
            name = name.replace("{index}",    str(idx))
            ext  = fmt.lower()
            if not name.endswith(f".{ext}"):
                name = f"{name}.{ext}"

            # 确定保存目录
            if not save_dir:
                import os as _os
                save_dir = _os.path.expanduser("~/Pictures")
            os.makedirs(save_dir, exist_ok=True)
            save_path = os.path.join(save_dir, name)

            # 根据模式处理
            if mode in ("save_file", "save_and_clipboard"):
                if fmt == "png":
                    file_bytes = png_bytes
                elif fmt == "jpg":
                    # 简单降级：先写 PNG 再用 ctypes BMP 方式，实际直接保存为 png 改名
                    file_bytes = png_bytes
                    save_path = save_path.replace(".jpg", ".png")
                else:
                    file_bytes = png_bytes
                with open(save_path, "wb") as f:
                    f.write(file_bytes)
                self._log("INFO", f"    截图已保存: {save_path}")

            if mode in ("clipboard", "save_and_clipboard"):
                # 将 BMP 格式放入剪贴板
                try:
                    import win32clipboard, win32con
                    # 构造 DIB 格式的内存块
                    bmp_data = (struct.pack("<IIIHHIIIIII",
                        40, sw, -sh, 1, 24, 0, row_bytes * sh, 3780, 3780, 0, 0)
                        + raw_bgr)
                    win32clipboard.OpenClipboard()
                    win32clipboard.EmptyClipboard()
                    win32clipboard.SetClipboardData(win32con.CF_DIB, bmp_data)
                    win32clipboard.CloseClipboard()
                    self._log("INFO", f"    截图已复制到剪贴板 ({sw}x{sh})")
                except Exception as e:
                    self._log("WARN", f"    截图复制到剪贴板失败: {e}")

        except Exception as e:
            self._log("WARN", f"    截图失败: {e}")

    def _clipboard_op(self, action: str, content: str, save_to: str):
        try:
            import win32clipboard
            if action == "get":
                win32clipboard.OpenClipboard()
                data = win32clipboard.GetClipboardData()
                win32clipboard.CloseClipboard()
                self.variables[save_to] = data
                self._log("INFO", f"    剪贴板内容已存入 {save_to}")
            else:
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(content)
                win32clipboard.CloseClipboard()
                self._log("INFO", f"    已设置剪贴板内容")
        except Exception as e:
            self._log("WARN", f"    剪贴板操作失败: {e}")

    def _send_keys(self, keys: str):
        try:
            import win32api, win32con
            import time as _time
            # 解析形如 ctrl+c, win+d 等
            KEY_MAP = {
                "ctrl": win32con.VK_CONTROL, "shift": win32con.VK_SHIFT,
                "alt": win32con.VK_MENU, "win": win32con.VK_LWIN,
                "enter": win32con.VK_RETURN, "esc": win32con.VK_ESCAPE,
                "escape": win32con.VK_ESCAPE,
                "space": win32con.VK_SPACE, "tab": win32con.VK_TAB,
                "backspace": win32con.VK_BACK, "delete": win32con.VK_DELETE,
                "home": win32con.VK_HOME, "end": win32con.VK_END,
                "pageup": win32con.VK_PRIOR, "pagedown": win32con.VK_NEXT,
                "up": win32con.VK_UP, "down": win32con.VK_DOWN,
                "left": win32con.VK_LEFT, "right": win32con.VK_RIGHT,
                "insert": win32con.VK_INSERT,
                "printscreen": win32con.VK_SNAPSHOT,
                "numlock": win32con.VK_NUMLOCK,
                "scrolllock": win32con.VK_SCROLL,
                "pause": win32con.VK_PAUSE,
                "f1": win32con.VK_F1, "f2": win32con.VK_F2, "f3": win32con.VK_F3,
                "f4": win32con.VK_F4, "f5": win32con.VK_F5, "f6": win32con.VK_F6,
                "f7": win32con.VK_F7, "f8": win32con.VK_F8, "f9": win32con.VK_F9,
                "f10": win32con.VK_F10, "f11": win32con.VK_F11, "f12": win32con.VK_F12,
            }
            parts = [k.strip().lower() for k in keys.split("+")]
            vkeys = []
            for p in parts:
                if p in KEY_MAP:
                    vkeys.append(KEY_MAP[p])
                elif len(p) == 1:
                    vkeys.append(ord(p.upper()))
            import ctypes
            for vk in vkeys:
                ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            _time.sleep(0.05)
            for vk in reversed(vkeys):
                ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
            self._log("INFO", f"    已发送按键: {keys}")
        except Exception as e:
            self._log("WARN", f"    发送按键失败: {e}")

    def _capslock_op(self, action: str, save_to: str):
        """大写锁定操作"""
        try:
            import ctypes
            VK_CAPITAL = 0x14
            # 获取当前状态
            cur_state = bool(ctypes.windll.user32.GetKeyState(VK_CAPITAL) & 0x0001)
            if action == "get":
                self.variables[save_to] = cur_state
                self._log("INFO", f"    [capslock] 当前状态: {cur_state} → {save_to}")
            elif action == "on":
                if not cur_state:
                    ctypes.windll.user32.keybd_event(VK_CAPITAL, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(VK_CAPITAL, 0, 2, 0)
                self._log("INFO", "    [capslock] 已开启大写锁定")
            elif action == "off":
                if cur_state:
                    ctypes.windll.user32.keybd_event(VK_CAPITAL, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(VK_CAPITAL, 0, 2, 0)
                self._log("INFO", "    [capslock] 已关闭大写锁定")
            elif action == "toggle":
                ctypes.windll.user32.keybd_event(VK_CAPITAL, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_CAPITAL, 0, 2, 0)
                new_state = bool(ctypes.windll.user32.GetKeyState(VK_CAPITAL) & 0x0001)
                self._log("INFO", f"    [capslock] 切换 → {new_state}")
        except Exception as e:
            self._log("WARN", f"    [capslock] 操作失败: {e}")

    def _http_request(self, url: str, method: str, headers_json: str,
                      body: str, save_to: str):
        import urllib.request
        import urllib.error
        import json as _json
        try:
            headers = _json.loads(headers_json) if headers_json.strip() else {}
        except Exception:
            headers = {}
        try:
            data = body.encode("utf-8") if body else None
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read().decode("utf-8", errors="replace")
            self.variables[save_to] = content
            self._log("INFO", f"    HTTP {method} {url} → 已存入 {save_to}")
        except Exception as e:
            self._log("ERROR", f"    HTTP请求失败: {e}")

    def _confirm_action(self, msg: str) -> bool:
        """无GUI模式下总是通过，GUI模式会弹窗（通过信号处理）"""
        return True  # 可由UI层覆写

    def _check_constraints(self, constraints, label: str = "") -> bool:
        """
        评估约束条件列表（AND 逻辑：所有条件都必须为真）。
        返回 True 表示可以执行，False 表示跳过。
        """
        from .models import Constraint
        for i, c in enumerate(constraints):
            result = self._eval_constraint(c)
            if c.negate:
                result = not result
            if not result:
                ct = c.condition_type
                target = c.target
                neg = "NOT " if c.negate else ""
                self._log("INFO", f"    约束[{i+1}] {neg}[{ct}] {target} => False，跳过 {label}")
                return False
        return True

    def _eval_constraint(self, c) -> bool:
        """评估单个约束条件"""
        ct     = c.condition_type
        target = resolve_value(c.target, self.variables)
        value  = resolve_value(c.value, self.variables)

        if ct == "always_true":
            return True
        elif ct == "process_exists":
            return self._process_exists(target)
        elif ct == "window_exists":
            return self._window_exists(target)
        elif ct == "file_exists":
            return os.path.exists(target)
        elif ct == "file_changed":
            mtime = self.variables.get(f"__mtime_{target}", None)
            cur   = os.path.getmtime(target) if os.path.exists(target) else None
            self.variables[f"__mtime_{target}"] = cur
            return cur != mtime
        elif ct == "variable_equals":
            return str(self.variables.get(target, "")) == value
        elif ct == "variable_gt":
            try:
                return float(self.variables.get(target, 0)) > float(value)
            except Exception:
                return False
        elif ct == "variable_lt":
            try:
                return float(self.variables.get(target, 0)) < float(value)
            except Exception:
                return False
        elif ct == "variable_contains":
            return value in str(self.variables.get(target, ""))
        elif ct == "clipboard_contains":
            try:
                import ctypes
                ctypes.windll.user32.OpenClipboard(None)
                data = ctypes.windll.user32.GetClipboardData(13)  # CF_UNICODETEXT
                buf  = ctypes.cast(data, ctypes.c_wchar_p)
                text = buf.value or ""
                ctypes.windll.user32.CloseClipboard()
                return target in text
            except Exception:
                return False
        elif ct in ("internet_connected", "network_connected"):
            try:
                import psutil as _ps
                return any(s.isup for s in _ps.net_if_stats().values())
            except Exception:
                return False
        elif ct == "ping_latency_gt":
            try:
                ms = self._get_ping_latency_ms(target, 1)
                return (ms or -1) > float(value) if value else False
            except Exception:
                return False
        elif ct == "ping_latency_lt":
            try:
                ms = self._get_ping_latency_ms(target, 1)
                if ms is None: return False
                return ms < float(value) if value else False
            except Exception:
                return False
        elif ct == "capslock_on":
            try:
                import ctypes
                return bool(ctypes.windll.user32.GetKeyState(0x14) & 0x0001)
            except Exception:
                return False
        elif ct == "cpu_above":
            try:
                import psutil as _ps
                threshold = float(target) if target else 80
                return _ps.cpu_percent(interval=0.5) > threshold
            except Exception:
                return False
        elif ct == "memory_above":
            try:
                import psutil as _ps
                threshold = float(target) if target else 90
                return _ps.virtual_memory().percent > threshold
            except Exception:
                return False
        elif ct == "battery_below":
            try:
                import psutil as _ps
                battery = _ps.sensors_battery()
                if battery is None: return False
                threshold = float(target) if target else 20
                return battery.percent < threshold
            except Exception:
                return False
        elif ct == "battery_charging":
            try:
                import psutil as _ps
                battery = _ps.sensors_battery()
                return battery is not None and battery.power_plugged
            except Exception:
                return False
        elif ct == "time_between":
            try:
                import datetime as _dt
                now = _dt.datetime.now().time()
                start = _dt.time(*map(int, target.split(":"))) if target else _dt.time(0, 0)
                end   = _dt.time(*map(int, value.split(":")))  if value  else _dt.time(23, 59)
                if start <= end:
                    return start <= now <= end
                else:
                    return now >= start or now <= end
            except Exception:
                return False
        elif ct == "day_of_week":
            try:
                import datetime as _dt
                weekday = _dt.datetime.now().weekday() + 1  # 1=周一 ~ 7=周日
                allowed = [int(x.strip()) for x in target.split(",") if x.strip().isdigit()]
                return weekday in allowed
            except Exception:
                return False
        return False

    # ─────────────────── 新增辅助方法 ───────────────────

    def _msgbox(self, title: str, text: str, buttons: str, icon: str, save_to: str):
        """弹出系统消息框，保存结果到变量"""
        try:
            import ctypes
            MB_FLAGS = {
                "ok":           0x00000000,
                "ok_cancel":    0x00000001,
                "yes_no":       0x00000004,
                "yes_no_cancel":0x00000003,
            }
            ICON_FLAGS = {
                "info":     0x00000040,
                "warning":  0x00000030,
                "error":    0x00000010,
                "question": 0x00000020,
            }
            MB_RESULT = {1: "ok", 2: "cancel", 6: "yes", 7: "no", 3: "abort"}
            flags = MB_FLAGS.get(buttons, 0) | ICON_FLAGS.get(icon, 0x40)
            ret = ctypes.windll.user32.MessageBoxW(None, text, title, flags)
            result = MB_RESULT.get(ret, str(ret))
            if save_to:
                self.variables[save_to] = result
            self._log("INFO", f"    消息框结果: {result}")
        except Exception as e:
            self._log("WARN", f"    消息框失败: {e}")

    def _play_sound(self, path: str, wait: bool):
        """播放音频文件"""
        try:
            import ctypes
            SND_ASYNC = 0x0001
            SND_FILENAME = 0x00020000
            SND_SYNC = 0x0000
            flags = SND_FILENAME | (SND_SYNC if wait else SND_ASYNC)
            ctypes.windll.winmm.PlaySoundW(path, None, flags)
            self._log("INFO", f"    播放声音: {path}")
        except Exception as e:
            self._log("WARN", f"    播放声音失败: {e}")

    def _input_text(self, text: str, delay_ms: float):
        """模拟键盘输入文字（逐字符发送 WM_CHAR）"""
        try:
            import ctypes
            import time as _t
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            WM_CHAR = 0x0102
            for ch in text:
                ctypes.windll.user32.PostMessageW(hwnd, WM_CHAR, ord(ch), 0)
                if delay_ms > 0:
                    _t.sleep(delay_ms / 1000.0)
            self._log("INFO", f"    已输入文字: {text[:30]}...")
        except Exception as e:
            self._log("WARN", f"    输入文字失败: {e}")

    def _open_url(self, url: str, browser: str):
        """在浏览器中打开网址"""
        try:
            import subprocess, os
            if browser == "chrome":
                # 尝试常见安装路径
                chrome_paths = [
                    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                ]
                exe = next((p for p in chrome_paths if os.path.exists(p)), None)
                if exe:
                    subprocess.Popen([exe, url])
                else:
                    subprocess.Popen(["chrome", url], shell=True)
            elif browser == "firefox":
                ff_paths = [
                    r"C:\Program Files\Mozilla Firefox\firefox.exe",
                    r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
                ]
                exe = next((p for p in ff_paths if os.path.exists(p)), None)
                if exe:
                    subprocess.Popen([exe, url])
                else:
                    subprocess.Popen(["firefox", url], shell=True)
            elif browser == "edge":
                # Edge 官方路径（微软商店版和安装版）
                edge_paths = [
                    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                ]
                exe = next((p for p in edge_paths if os.path.exists(p)), None)
                if exe:
                    subprocess.Popen([exe, url])
                else:
                    # 回退：用 start ms-edge: 协议
                    subprocess.Popen(["cmd", "/c", f"start msedge {url}"], shell=False)
            else:
                os.startfile(url)
            self._log("INFO", f"    已打开: {url}")
        except Exception as e:
            self._log("WARN", f"    打开网址失败: {e}")

    def _turn_off_display(self, delay_sec: float = 0):
        """
        关闭显示器。
        原理：发送 WM_SYSCOMMAND SC_MONITORPOWER 消息（-1=开, 1=省电, 2=关闭）
        不依赖任何第三方工具，纯 Win32 API 实现。
        """
        try:
            import ctypes, time as _t
            if delay_sec > 0:
                self._log("INFO", f"    将在 {delay_sec:.0f} 秒后关闭显示器...")
                _t.sleep(delay_sec)
            WM_SYSCOMMAND    = 0x0112
            SC_MONITORPOWER  = 0xF170
            MONITOR_OFF      = 2      # 2=完全关闭
            HWND_BROADCAST   = 0xFFFF
            ctypes.windll.user32.SendMessageW(
                HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, MONITOR_OFF
            )
            self._log("INFO", "    显示器已关闭")
        except Exception as e:
            self._log("WARN", f"    关闭显示器失败: {e}")

    def _resolve_task_id(self, task_id_or_name: str) -> Optional[str]:
        """通过 task_id 或 task_name 解析得到实际 task_id"""
        if not task_id_or_name:
            return None
        if self._all_tasks_fn is None:
            return task_id_or_name
        tasks = self._all_tasks_fn()
        # 先精确匹配 ID
        for t in tasks:
            if t.id == task_id_or_name:
                return t.id
        # 再按名称匹配
        for t in tasks:
            if t.name == task_id_or_name:
                return t.id
        return task_id_or_name

    def _run_other_task(self, task_id: str, wait: bool, timeout: float):
        """运行另一个任务"""
        resolved_id = self._resolve_task_id(task_id)
        if not resolved_id:
            self._log("WARN", f"    未指定目标任务")
            return
        if self._run_task_fn is None:
            self._log("WARN", f"    任务联动不可用（未传入 run_task_fn）")
            return
        task_name = resolved_id
        if self._all_tasks_fn:
            for t in self._all_tasks_fn():
                if t.id == resolved_id:
                    task_name = t.name
                    break
        self._log("INFO", f"    启动任务: {task_name}")
        self._run_task_fn(resolved_id)
        if wait and self._is_task_running is not None:
            deadline = time.time() + timeout if timeout > 0 else None
            while self._is_task_running(resolved_id):
                if deadline and time.time() > deadline:
                    self._log("WARN", f"    等待任务超时: {task_name}")
                    return
                time.sleep(0.2)
            self._log("INFO", f"    任务已完成: {task_name}")

    def _stop_other_task(self, task_id: str):
        """停止另一个任务"""
        resolved_id = self._resolve_task_id(task_id)
        if not resolved_id:
            self._log("WARN", f"    未指定目标任务")
            return
        if self._stop_task_fn is None:
            self._log("WARN", f"    任务联动不可用（未传入 stop_task_fn）")
            return
        task_name = resolved_id
        if self._all_tasks_fn:
            for t in self._all_tasks_fn():
                if t.id == resolved_id:
                    task_name = t.name
                    break
        self._log("INFO", f"    停止任务: {task_name}")
        self._stop_task_fn(resolved_id)

    def _wait_task_done(self, task_id: str, timeout: float, on_timeout: str):
        """等待另一个任务完成"""
        resolved_id = self._resolve_task_id(task_id)
        if not resolved_id or self._is_task_running is None:
            return
        task_name = resolved_id
        if self._all_tasks_fn:
            for t in self._all_tasks_fn():
                if t.id == resolved_id:
                    task_name = t.name
                    break
        self._log("INFO", f"    等待任务完成: {task_name}")
        deadline = time.time() + timeout if timeout > 0 else None
        while self._is_task_running(resolved_id):
            self._check_stop()
            if deadline and time.time() > deadline:
                self._log("WARN", f"    等待超时: {task_name}")
                if on_timeout == "stop_task":
                    raise StopTaskException()
                return
            time.sleep(0.2)
        self._log("INFO", f"    任务已完成: {task_name}")

    # ─── 曲线缓动工具方法 ───

    @staticmethod
    def _easing(t: float, curve: str) -> float:
        """将线性进度 t∈[0,1] 映射为缓动进度（不含 bezier/humanize，这两种在调用处单独处理）"""
        import math as _math
        if curve == "ease_in":
            # 二次缓入
            return t * t
        elif curve == "ease_out":
            # 二次缓出
            return 1 - (1 - t) * (1 - t)
        elif curve == "ease_in_out":
            # 三次 S 形缓入缓出（smoothstep）
            return t * t * (3 - 2 * t)
        elif curve == "ease_in_cubic":
            # 三次缓入，启动更慢
            return t * t * t
        elif curve == "ease_out_cubic":
            # 三次缓出，结束更柔
            u = 1 - t
            return 1 - u * u * u
        elif curve == "ease_out_back":
            # 超出回弹：到达终点后稍微超过再回来，像手指自然滑过
            c1 = 1.70158
            c3 = c1 + 1
            return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2
        elif curve == "spring":
            # 弹性衰减：到达终点附近轻微弹跳，模拟手腕惯性
            if t == 0.0:
                return 0.0
            if t == 1.0:
                return 1.0
            c4 = (2 * _math.pi) / 3.0
            return -(2 ** (10 * t - 10)) * _math.sin((t * 10 - 10.75) * c4)
        else:
            # linear 及 bezier/humanize 的 fallback
            return t

    # ─── 拟人化曲线路径生成器 ───

    @staticmethod
    def _humanize_path(start_x: float, start_y: float,
                       end_x: float, end_y: float,
                       steps: int) -> list:
        """
        生成拟人化鼠标轨迹点列表（共 steps+1 个点）。

        算法说明：
        1. 基础速度曲线采用"先加速后减速"的 ease_in_out（smoothstep），模拟人手出发慢-中间快-到达慢；
        2. 在中段叠加一条轻微贝塞尔弧线（随机控制点），避免走直线；
        3. 整条路径叠加低频正弦漂移（模拟手腕旋转产生的圆弧感）；
        4. 在速度快的中段叠加极小高频噪声（模拟手的细微震颤），
           靠近起终点时噪声趋近于 0，保证起终点精确；
        5. 速度非均匀：中间步骤间隔短，起步和停止前间隔略长（模拟加减速节奏）。

        返回：[(x, y, sleep_sec), ...]，sleep_sec 为该步之后的等待时长。
        """
        import math as _math
        import random as _rand

        dx = end_x - start_x
        dy = end_y - start_y
        dist = _math.hypot(dx, dy)

        # 控制点偏移量随距离动态缩放，短距离不需要大弧度
        arc_scale = min(dist * 0.18, 60.0)
        # 随机选择弯曲方向和程度（左弯或右弯，幅度 20-100%）
        arc_sign = _rand.choice([-1, 1])
        arc_ratio = _rand.uniform(0.2, 1.0)
        perp_x = -dy / (dist + 1e-9)
        perp_y =  dx / (dist + 1e-9)
        offset = arc_scale * arc_ratio * arc_sign
        cp_x = (start_x + end_x) / 2 + perp_x * offset
        cp_y = (start_y + end_y) / 2 + perp_y * offset

        # 低频漂移参数（正弦波幅度 0-3px，频率 0.8-1.5 周期/全程）
        drift_amp   = _rand.uniform(0.0, min(dist * 0.015, 3.0))
        drift_freq  = _rand.uniform(0.8, 1.5)
        drift_phase = _rand.uniform(0, 2 * _math.pi)

        # 高频抖动幅度（在速度峰值区最大 1.5px，靠近端点收缩）
        jitter_max = min(dist * 0.008, 1.5)

        path = []
        for i in range(steps + 1):
            t_raw = i / steps

            # ── 速度曲线：smoothstep + 轻微 ease_in_out 混合 ──
            t_ease = t_raw * t_raw * (3 - 2 * t_raw)

            # ── 二次贝塞尔弧线位置 ──
            u = 1 - t_ease
            bx = u * u * start_x + 2 * u * t_ease * cp_x + t_ease * t_ease * end_x
            by = u * u * start_y + 2 * u * t_ease * cp_y + t_ease * t_ease * end_y

            # ── 低频漂移（正弦，靠近端点衰减） ──
            edge_fade = _math.sin(t_raw * _math.pi)  # 0→1→0
            drift = drift_amp * _math.sin(drift_freq * t_raw * 2 * _math.pi + drift_phase) * edge_fade
            bx += perp_x * drift
            by += perp_y * drift

            # ── 高频抖动（中段才有，端点无） ──
            jitter = jitter_max * edge_fade
            bx += _rand.uniform(-jitter, jitter)
            by += _rand.uniform(-jitter, jitter)

            # ── 非均匀步长：中段快、两端慢 ──
            # speed_factor 越大表示该步耗时越短
            speed_factor = 0.4 + 0.6 * edge_fade  # 端点 0.4x，中段 1.0x
            sleep_val = (1.0 / (steps + 1)) / (speed_factor + 1e-9)

            path.append((int(round(bx)), int(round(by)), sleep_val))

        # 归一化 sleep_val 使总和等于 1.0（便于外层乘以 duration）
        total = sum(p[2] for p in path) or 1.0
        path = [(p[0], p[1], p[2] / total) for p in path]

        # 强制首尾精确
        path[0]  = (int(round(start_x)), int(round(start_y)), path[0][2])
        path[-1] = (int(round(end_x)),   int(round(end_y)),   path[-1][2])

        return path

    @staticmethod
    def _bezier_point(t: float, p0: float, p1: float, p2: float, p3: float) -> float:
        """三阶贝塞尔曲线，控制点可自定义（用于路径弯曲）"""
        u = 1 - t
        return u*u*u*p0 + 3*u*u*t*p1 + 3*u*t*t*p2 + t*t*t*p3

    @staticmethod
    def _resolve_coord(pos: dict, var_x_key: str = "x", var_y_key: str = "y") -> tuple:
        """
        解析坐标字典，支持像素和百分比两种模式。
        pos 格式：
          - 旧格式：{"x": 100, "y": 200}（视为像素）
          - 新格式：{"x": 50.0, "y": 30.0, "mode": "percent"}（百分比，换算为像素）
        返回 (x_pixels, y_pixels)
        """
        if not isinstance(pos, dict):
            return 0, 0
        x_raw = pos.get(var_x_key, 0)
        y_raw = pos.get(var_y_key, 0)
        mode  = pos.get("mode", "pixel")
        if mode == "percent":
            try:
                import ctypes
                sw = ctypes.windll.user32.GetSystemMetrics(0)
                sh = ctypes.windll.user32.GetSystemMetrics(1)
                x_px = int(float(x_raw) / 100.0 * sw)
                y_px = int(float(y_raw) / 100.0 * sh)
            except Exception:
                x_px, y_px = int(float(x_raw)), int(float(y_raw))
        else:
            try:
                x_px, y_px = int(float(x_raw)), int(float(y_raw))
            except Exception:
                x_px, y_px = 0, 0
        return x_px, y_px

    def _mouse_move(self, x: int, y: int, relative: bool, duration: float,
                    curve: str = "linear", jitter: int = 0, rand_offset: int = 0):
        """移动鼠标到绝对/相对坐标，支持多种曲线和拟人化轨迹"""
        import ctypes, random as _rand
        MOUSEEVENTF_MOVE = 0x0001
        try:
            # 最终目标坐标加随机偏移
            if rand_offset > 0 and not relative:
                x += _rand.randint(-rand_offset, rand_offset)
                y += _rand.randint(-rand_offset, rand_offset)

            if relative:
                ctypes.windll.user32.mouse_event(MOUSEEVENTF_MOVE, x, y, 0, 0)
            else:
                if duration > 0:
                    class POINT(ctypes.Structure):
                        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
                    pt = POINT()
                    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
                    start_x, start_y = pt.x, pt.y
                    steps = max(int(duration * 60), 8)

                    import time as _t

                    if curve == "humanize":
                        # 拟人化：使用专用路径生成器，步长非均匀
                        path = self._humanize_path(start_x, start_y, x, y, steps)
                        for px, py, sleep_ratio in path:
                            self._check_stop()
                            if jitter > 0:
                                px += _rand.randint(-jitter, jitter)
                                py += _rand.randint(-jitter, jitter)
                            ctypes.windll.user32.SetCursorPos(px, py)
                            _t.sleep(duration * sleep_ratio)
                    elif curve == "bezier":
                        # 贝塞尔：三阶曲线，随机控制点产生自然弧形
                        mid_x = (start_x + x) / 2 + _rand.randint(-80, 80)
                        mid_y = (start_y + y) / 2 + _rand.randint(-80, 80)
                        cx1, cy1 = mid_x, start_y
                        cx2, cy2 = mid_x, y
                        for i in range(steps + 1):
                            self._check_stop()
                            t_raw = i / steps
                            cx = int(self._bezier_point(t_raw, start_x, cx1, cx2, x))
                            cy = int(self._bezier_point(t_raw, start_y, cy1, cy2, y))
                            if jitter > 0 and 0 < i < steps:
                                cx += _rand.randint(-jitter, jitter)
                                cy += _rand.randint(-jitter, jitter)
                            ctypes.windll.user32.SetCursorPos(cx, cy)
                            _t.sleep(duration / steps)
                    else:
                        # 其余缓动曲线：均匀步长 + easing
                        for i in range(steps + 1):
                            self._check_stop()
                            t_raw = i / steps
                            t_ease = self._easing(t_raw, curve)
                            cx = int(start_x + (x - start_x) * t_ease)
                            cy = int(start_y + (y - start_y) * t_ease)
                            if jitter > 0 and 0 < i < steps:
                                cx += _rand.randint(-jitter, jitter)
                                cy += _rand.randint(-jitter, jitter)
                            ctypes.windll.user32.SetCursorPos(cx, cy)
                            _t.sleep(duration / steps)
                else:
                    ctypes.windll.user32.SetCursorPos(x, y)
            self._log("INFO", f"    鼠标移到 ({x},{y}) relative={relative} curve={curve}")
        except StopTaskException:
            raise
        except Exception as e:
            self._log("WARN", f"    鼠标移动失败: {e}")

    def _mouse_click_pos(self, x: int, y: int, button: str, clicks: int, move_first: bool,
                         rand_offset: int = 0, move_curve: str = "linear", move_duration: float = 0,
                         click_interval: float = 0.12, down_up_delay: float = 0.05):
        """在指定坐标点击鼠标，支持随机偏移和先移动曲线。
        使用 mouse_event（兼容性最好，不受 UIPI 权限限制）。
        down_up_delay: 按下→松开之间的等待时长（秒），默认 0.05。
        click_interval: 多次点击之间的等待时长（秒），默认 0.12，避免被目标程序误识别为双击。
        """
        import ctypes, random as _rand
        import time as _t

        MOUSEEVENTF_LEFTDOWN   = 0x0002
        MOUSEEVENTF_LEFTUP     = 0x0004
        MOUSEEVENTF_RIGHTDOWN  = 0x0008
        MOUSEEVENTF_RIGHTUP    = 0x0010
        MOUSEEVENTF_MIDDLEDOWN = 0x0020
        MOUSEEVENTF_MIDDLEUP   = 0x0040

        try:
            # 随机偏移最终落点
            tx = x + (_rand.randint(-rand_offset, rand_offset) if rand_offset > 0 else 0)
            ty = y + (_rand.randint(-rand_offset, rand_offset) if rand_offset > 0 else 0)

            if move_first:
                if move_duration > 0:
                    self._mouse_move(tx, ty, False, move_duration, curve=move_curve)
                else:
                    ctypes.windll.user32.SetCursorPos(tx, ty)
                _t.sleep(0.05)

            if button == "right":
                dn, up = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
            elif button == "middle":
                dn, up = MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP
            else:
                dn, up = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP

            user32 = ctypes.windll.user32
            for i in range(clicks):
                self._check_stop()
                # 每次点击前确保光标在目标位置
                user32.SetCursorPos(tx, ty)
                _t.sleep(0.01)
                user32.mouse_event(dn, 0, 0, 0, 0)   # 按下
                _t.sleep(max(0, down_up_delay))        # 按下→松开延迟（可自定义）
                user32.mouse_event(up, 0, 0, 0, 0)   # 松开
                if i < clicks - 1:
                    _t.sleep(max(0, click_interval))   # 多次点击间隔（可自定义）

            self._log("INFO", f"    鼠标{button}键点击 ({tx},{ty}) x{clicks}")
        except StopTaskException:
            raise
        except Exception as e:
            self._log("WARN", f"    鼠标点击失败: {e}")

    def _mouse_scroll(self, x: int, y: int, amount: int):
        """鼠标滚轮滚动"""
        try:
            import ctypes
            MOUSEEVENTF_WHEEL = 0x0800
            if x or y:
                ctypes.windll.user32.SetCursorPos(x, y)
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, amount * 120, 0)
            self._log("INFO", f"    鼠标滚轮: {amount}")
        except Exception as e:
            self._log("WARN", f"    鼠标滚轮失败: {e}")

    def _mouse_drag(self, from_x: int, from_y: int, to_x: int, to_y: int,
                    button: str, duration: float, curve: str = "linear", jitter: int = 0):
        """鼠标拖拽，支持多种缓动曲线、贝塞尔弧线、拟人化轨迹和随机抖动。"""
        import ctypes, random as _rand
        import time as _t

        MOUSEEVENTF_LEFTDOWN   = 0x0002
        MOUSEEVENTF_LEFTUP     = 0x0004
        MOUSEEVENTF_RIGHTDOWN  = 0x0008
        MOUSEEVENTF_RIGHTUP    = 0x0010

        try:
            if button == "right":
                dn, up = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
            else:
                dn, up = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP
            user32 = ctypes.windll.user32
            user32.SetCursorPos(from_x, from_y)
            _t.sleep(0.05)
            user32.mouse_event(dn, 0, 0, 0, 0)
            steps = max(int(duration * 60), 8)

            if curve == "humanize":
                path = self._humanize_path(from_x, from_y, to_x, to_y, steps)
                for px, py, sleep_ratio in path:
                    self._check_stop()
                    if jitter > 0:
                        px += _rand.randint(-jitter, jitter)
                        py += _rand.randint(-jitter, jitter)
                    user32.SetCursorPos(px, py)
                    _t.sleep(duration * sleep_ratio)
            elif curve == "bezier":
                cx1 = (from_x + to_x) / 2 + _rand.randint(-80, 80)
                cy1_b = from_y
                cx2 = (from_x + to_x) / 2 + _rand.randint(-80, 80)
                cy2_b = to_y
                for i in range(steps + 1):
                    self._check_stop()
                    t_raw = i / steps
                    cx = int(self._bezier_point(t_raw, from_x, cx1, cx2, to_x))
                    cy = int(self._bezier_point(t_raw, from_y, cy1_b, cy2_b, to_y))
                    if jitter > 0 and 0 < i < steps:
                        cx += _rand.randint(-jitter, jitter)
                        cy += _rand.randint(-jitter, jitter)
                    user32.SetCursorPos(cx, cy)
                    _t.sleep(duration / steps)
            else:
                for i in range(steps + 1):
                    self._check_stop()
                    t_raw = i / steps
                    t_ease = self._easing(t_raw, curve)
                    cx = int(from_x + (to_x - from_x) * t_ease)
                    cy = int(from_y + (to_y - from_y) * t_ease)
                    if jitter > 0 and 0 < i < steps:
                        cx += _rand.randint(-jitter, jitter)
                        cy += _rand.randint(-jitter, jitter)
                    user32.SetCursorPos(cx, cy)
                    _t.sleep(duration / steps)

            user32.mouse_event(up, 0, 0, 0, 0)
            self._log("INFO", f"    鼠标拖拽: ({from_x},{from_y}) -> ({to_x},{to_y}) curve={curve}")
        except StopTaskException:
            try:
                ctypes.windll.user32.mouse_event(up, 0, 0, 0, 0)
            except Exception:
                pass
            raise
        except Exception as e:
            self._log("WARN", f"    鼠标拖拽失败: {e}")

    def _play_macro(self, macro_data: list, speed: float, repeat: int, use_relative: bool):
        """
        键鼠宏回放。macro_data 格式（参考KeymouseGo）：
        每条事件: {"type": "EM"|"EK", "time": ms, ...}
        EM: {"type":"EM","time":ms,"event":"move"|"left_down"|"left_up"|"right_down"|"right_up"|"wheel",
             "x":rel_x,"y":rel_y,"wx":0,"wy":0}  (x,y 为相对比例 0.0~1.0 或绝对像素)
        EK: {"type":"EK","time":ms,"event":"key_down"|"key_up","vk_code":vk}
        """
        import ctypes, time as _t
        if not macro_data:
            self._log("WARN", "    键鼠宏：录制数据为空")
            return

        # 获取屏幕分辨率（相对坐标换算）
        sw = ctypes.windll.user32.GetSystemMetrics(0)
        sh = ctypes.windll.user32.GetSystemMetrics(1)

        MOUSEEVENTF_MOVE       = 0x0001
        MOUSEEVENTF_LEFTDOWN   = 0x0002
        MOUSEEVENTF_LEFTUP     = 0x0004
        MOUSEEVENTF_RIGHTDOWN  = 0x0008
        MOUSEEVENTF_RIGHTUP    = 0x0010
        MOUSEEVENTF_MIDDLEDOWN = 0x0020
        MOUSEEVENTF_MIDDLEUP   = 0x0040
        MOUSEEVENTF_WHEEL      = 0x0800
        KEYEVENTF_EXTENDEDKEY  = 0x0001
        KEYEVENTF_KEYUP        = 0x0002

        speed = max(0.1, speed)   # 防止除零

        for _rep in range(repeat):
            self._check_stop()
            prev_time_ms = 0
            for ev in macro_data:
                self._check_stop()
                ev_time = ev.get("time", 0)
                delay = (ev_time - prev_time_ms) / 1000.0 / speed
                if delay > 0:
                    _t.sleep(max(0, delay))
                prev_time_ms = ev_time

                ev_type = ev.get("type", "")
                ev_name = ev.get("event", "")

                if ev_type == "EM":
                    rx = ev.get("x", 0)
                    ry = ev.get("y", 0)
                    if use_relative:
                        ax = int(rx * sw)
                        ay = int(ry * sh)
                    else:
                        ax = int(rx)
                        ay = int(ry)

                    if ev_name == "move":
                        ctypes.windll.user32.SetCursorPos(ax, ay)
                    elif ev_name == "left_down":
                        ctypes.windll.user32.SetCursorPos(ax, ay)
                        ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                    elif ev_name == "left_up":
                        ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                    elif ev_name == "right_down":
                        ctypes.windll.user32.SetCursorPos(ax, ay)
                        ctypes.windll.user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
                    elif ev_name == "right_up":
                        ctypes.windll.user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
                    elif ev_name == "middle_down":
                        ctypes.windll.user32.SetCursorPos(ax, ay)
                        ctypes.windll.user32.mouse_event(MOUSEEVENTF_MIDDLEDOWN, 0, 0, 0, 0)
                    elif ev_name == "middle_up":
                        ctypes.windll.user32.mouse_event(MOUSEEVENTF_MIDDLEUP, 0, 0, 0, 0)
                    elif ev_name == "wheel":
                        wd = ev.get("wy", 0)
                        ctypes.windll.user32.SetCursorPos(ax, ay)
                        ctypes.windll.user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, int(wd * 120), 0)

                elif ev_type == "EK":
                    vk = ev.get("vk_code", 0)
                    if not vk:
                        continue
                    flags = KEYEVENTF_EXTENDEDKEY
                    if ev_name == "key_down":
                        ctypes.windll.user32.keybd_event(vk, 0, flags, 0)
                    elif ev_name == "key_up":
                        ctypes.windll.user32.keybd_event(vk, 0, flags | KEYEVENTF_KEYUP, 0)

        self._log("INFO", f"    键鼠宏回放完成，共 {len(macro_data)} 事件 x{repeat}")

    def _find_window_hwnd(self, title: str) -> int:
        """根据标题查找窗口句柄（精确或通配）"""
        if not title:
            import ctypes
            return ctypes.windll.user32.GetForegroundWindow()
        try:
            import win32gui
            hwnds = []
            def cb(hwnd, _):
                t = win32gui.GetWindowText(hwnd)
                if fnmatch.fnmatch(t.lower(), title.lower()):
                    hwnds.append(hwnd)
            win32gui.EnumWindows(cb, None)
            return hwnds[0] if hwnds else 0
        except Exception:
            import ctypes
            return ctypes.windll.user32.FindWindowW(None, title)

    def _launch_app(self, path: str, args: str, cwd, run_mode: str,
                    as_admin: bool, wait: bool, timeout: float, save_pid: str):
        """启动外部应用程序"""
        import subprocess, shlex, os as _os

        if not path:
            self._log("WARN", "    启动应用：未指定程序路径")
            return

        # 展开环境变量 & 用户目录
        path = _os.path.expandvars(_os.path.expanduser(path))

        self._log("INFO", f"    启动应用: {path}" + (f" {args}" if args else ""))

        # ── 快捷方式 / 文档类文件：直接用 ShellExecuteW（Windows Shell 处理）──
        ext = _os.path.splitext(path)[1].lower()
        _SHELL_EXTS = {".lnk", ".url", ".pif", ".bat", ".cmd", ".ps1",
                       ".vbs", ".wsf", ".reg", ".msi", ".msc"}
        if ext in _SHELL_EXTS:
            try:
                import ctypes as _ctypes
                SW_SHOWNORMAL = 1
                SW_SHOWMINIMIZED = 2
                SW_SHOWMAXIMIZED = 3
                sw = SW_SHOWNORMAL
                if run_mode == "minimized":
                    sw = SW_SHOWMINIMIZED
                elif run_mode == "maximized":
                    sw = SW_SHOWMAXIMIZED
                verb = "runas" if as_admin else "open"
                params = args if args else None
                ret = _ctypes.windll.shell32.ShellExecuteW(
                    None, verb, path, params,
                    cwd if cwd else None, sw
                )
                if ret <= 32:
                    self._log("WARN", f"    启动应用(Shell)失败，错误码: {ret}，尝试 os.startfile")
                    _os.startfile(path)
                else:
                    self._log("INFO", f"    已通过 Shell 启动: {path}")
            except Exception as _e:
                self._log("ERROR", f"    启动应用失败: {_e}")
            return

        # 构建 creationflags（窗口模式）
        CREATE_NO_WINDOW   = 0x08000000
        CREATE_MINIMIZED   = 0x00000006   # CREATE_NEW_CONSOLE | STARTF_USESHOWWINDOW
        SW_HIDE            = 0
        SW_SHOWNORMAL      = 1
        SW_SHOWMINIMIZED   = 2
        SW_SHOWMAXIMIZED   = 3

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creation_flags = 0

        if run_mode == "hidden":
            startupinfo.wShowWindow = SW_HIDE
            creation_flags |= CREATE_NO_WINDOW
        elif run_mode == "minimized":
            startupinfo.wShowWindow = SW_SHOWMINIMIZED
        elif run_mode == "maximized":
            startupinfo.wShowWindow = SW_SHOWMAXIMIZED
        else:
            startupinfo.wShowWindow = SW_SHOWNORMAL

        # 构建命令列表
        cmd = [path]
        if args:
            try:
                cmd += shlex.split(args)
            except ValueError:
                cmd += args.split()

        try:
            if as_admin:
                # 以管理员身份运行：通过 ShellExecute runas
                import ctypes
                params = args if args else None
                ret = ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", path, params,
                    cwd if cwd else None, SW_SHOWNORMAL
                )
                if ret <= 32:
                    self._log("WARN", f"    启动应用(管理员)失败，错误码: {ret}")
                else:
                    self._log("INFO", f"    已以管理员身份请求启动: {path}")
            else:
                proc = subprocess.Popen(
                    cmd,
                    cwd=cwd if cwd else None,
                    startupinfo=startupinfo,
                    creationflags=creation_flags,
                    close_fds=True,
                )
                if save_pid:
                    self.variables[save_pid] = proc.pid
                    self._log("INFO", f"    进程 PID={proc.pid} 已存入变量 {save_pid}")

                if wait:
                    deadline = time.time() + timeout if timeout > 0 else None
                    while proc.poll() is None:
                        self._check_stop()
                        if deadline and time.time() > deadline:
                            self._log("WARN", f"    等待程序退出超时: {path}")
                            break
                        time.sleep(0.2)
                    if proc.returncode is not None:
                        self._log("INFO", f"    程序已退出，返回码: {proc.returncode}")

        except FileNotFoundError:
            self._log("ERROR", f"    启动失败：找不到程序 {path}")
        except PermissionError:
            self._log("ERROR", f"    启动失败：权限不足，请尝试「以管理员身份运行」")
        except Exception as e:
            self._log("ERROR", f"    启动应用失败: {e}")

    def _activate_window(self, title: str, timeout: float):
        """激活/前置窗口"""
        try:
            import ctypes
            import time as _t
            deadline = _t.time() + (timeout if timeout > 0 else 0.1)
            hwnd = 0
            while True:
                hwnd = self._find_window_hwnd(title)
                if hwnd or _t.time() >= deadline:
                    break
                _t.sleep(0.3)
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 9)   # SW_RESTORE
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                self._log("INFO", f"    已激活窗口: '{title}'")
            else:
                self._log("WARN", f"    未找到窗口: '{title}'")
        except Exception as e:
            self._log("WARN", f"    激活窗口失败: {e}")

    def _set_window_topmost(self, title: str, topmost: bool):
        """设置窗口置顶"""
        try:
            import ctypes
            HWND_TOPMOST    = -1
            HWND_NOTOPMOST  = -2
            SWP_NOMOVE      = 0x0002
            SWP_NOSIZE      = 0x0001
            hwnd = self._find_window_hwnd(title)
            if hwnd:
                flag = HWND_TOPMOST if topmost else HWND_NOTOPMOST
                ctypes.windll.user32.SetWindowPos(hwnd, flag, 0, 0, 0, 0,
                                                   SWP_NOMOVE | SWP_NOSIZE)
                self._log("INFO", f"    窗口置顶={'是' if topmost else '否'}: '{title}'")
            else:
                self._log("WARN", f"    未找到窗口: '{title}'")
        except Exception as e:
            self._log("WARN", f"    设置置顶失败: {e}")

    def _move_window(self, title: str, x: int, y: int, width: int, height: int):
        """移动/缩放窗口"""
        try:
            import ctypes
            hwnd = self._find_window_hwnd(title)
            if hwnd:
                # 获取当前位置
                class RECT(ctypes.Structure):
                    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                                 ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
                r = RECT()
                ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
                cx = r.left if x == -1 else x
                cy = r.top  if y == -1 else y
                cw = (r.right - r.left) if width == -1 else width
                ch = (r.bottom - r.top) if height == -1 else height
                ctypes.windll.user32.MoveWindow(hwnd, cx, cy, cw, ch, True)
                self._log("INFO", f"    已移动窗口 '{title}' 到 ({cx},{cy}) {cw}x{ch}")
            else:
                self._log("WARN", f"    未找到窗口: '{title}'")
        except Exception as e:
            self._log("WARN", f"    移动窗口失败: {e}")

    def _get_window_info(self, title: str, save_to: str):
        """获取窗口位置/尺寸等信息，存入变量"""
        try:
            import ctypes
            hwnd = self._find_window_hwnd(title)
            if hwnd:
                class RECT(ctypes.Structure):
                    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                                 ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
                r = RECT()
                ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
                buf = ctypes.create_unicode_buffer(256)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
                self.variables[save_to + "_title"]  = buf.value
                self.variables[save_to + "_x"]      = r.left
                self.variables[save_to + "_y"]      = r.top
                self.variables[save_to + "_w"]      = r.right - r.left
                self.variables[save_to + "_h"]      = r.bottom - r.top
                self.variables[save_to + "_hwnd"]   = hwnd
                self._log("INFO", f"    窗口信息已存入 {save_to}_*")
            else:
                self._log("WARN", f"    未找到窗口: '{title}'")
        except Exception as e:
            self._log("WARN", f"    获取窗口信息失败: {e}")

    def _minimize_window(self, title: str):
        """最小化窗口"""
        try:
            import ctypes
            hwnd = self._find_window_hwnd(title)
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
                self._log("INFO", f"    已最小化: '{title}'")
            else:
                self._log("WARN", f"    未找到窗口: '{title}'")
        except Exception as e:
            self._log("WARN", f"    最小化失败: {e}")

    def _maximize_window(self, title: str):
        """最大化窗口"""
        try:
            import ctypes
            hwnd = self._find_window_hwnd(title)
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
                self._log("INFO", f"    已最大化: '{title}'")
            else:
                self._log("WARN", f"    未找到窗口: '{title}'")
        except Exception as e:
            self._log("WARN", f"    最大化失败: {e}")

    # ─────────────────── v2.2.0 新增辅助方法 ───────────────────

    def _show_desktop(self):
        """
        显示/隐藏桌面（与 Windows 任务栏右下角「显示桌面」按钮等效）。
        原理：向 Shell_TrayWnd 发送 COMMAND 消息 MIN_ALL(0x0419) 或
        直接调用 IVirtualDesktopManager，回退方案：Win+D 热键模拟。
        """
        try:
            import ctypes
            # 方案1：向 Shell 发送最小化全部窗口消息（切换式）
            HWND_SHELL = ctypes.windll.user32.FindWindowW("Shell_TrayWnd", None)
            if HWND_SHELL:
                WM_COMMAND   = 0x0111
                MIN_ALL      = 0x0419   # 最小化所有窗口（再次发送则还原）
                ctypes.windll.user32.PostMessageW(HWND_SHELL, WM_COMMAND, MIN_ALL, 0)
                self._log("INFO", "    已切换显示桌面")
                return
        except Exception:
            pass
        try:
            # 方案2：Win+D 热键模拟
            import ctypes
            VK_LWIN  = 0x5B
            VK_D     = 0x44
            KEYEVENTF_KEYUP = 0x0002
            kbe = ctypes.windll.user32.keybd_event
            kbe(VK_LWIN, 0, 0, 0)
            kbe(VK_D,    0, 0, 0)
            kbe(VK_D,    0, KEYEVENTF_KEYUP, 0)
            kbe(VK_LWIN, 0, KEYEVENTF_KEYUP, 0)
            self._log("INFO", "    已切换显示桌面（Win+D）")
        except Exception as e:
            self._log("WARN", f"    显示桌面失败: {e}")

    def _lock_computer(self):
        """
        锁定计算机（等同 Win+L）。
        调用 user32.LockWorkStation()，无需管理员权限。
        """
        try:
            import ctypes
            result = ctypes.windll.user32.LockWorkStation()
            if result:
                self._log("INFO", "    计算机已锁定")
            else:
                self._log("WARN", "    锁定计算机失败（LockWorkStation 返回 0）")
        except Exception as e:
            self._log("WARN", f"    锁定计算机失败: {e}")

    def _launch_steam(self, app_id: str, save_to: str):
        """
        通过 Steam URI 协议启动游戏。
        steam://rungameid/<AppID>  — 启动游戏
        steam://open/games         — 打开 Steam 游戏库（app_id 为空时）
        """
        try:
            import os as _os
            if app_id:
                uri = f"steam://rungameid/{app_id}"
                msg = f"启动 Steam 游戏 AppID={app_id}"
            else:
                uri = "steam://open/games"
                msg = "打开 Steam 游戏库"
            _os.startfile(uri)
            self._log("INFO", f"    {msg}，URI={uri}")
            if save_to:
                self.variables[save_to] = uri
        except Exception as e:
            self._log("WARN", f"    启动 Steam 失败: {e}")

    def _browser_search(self, keyword: str, engine: str, custom_url: str):
        """
        在默认浏览器中搜索关键词。
        支持引擎: baidu / google / bing / bilibili / zhihu / custom
        custom 模式下 custom_url 应包含 {query} 占位符。
        """
        import urllib.parse
        import webbrowser
        ENGINES = {
            "baidu":    "https://www.baidu.com/s?wd={query}",
            "google":   "https://www.google.com/search?q={query}",
            "bing":     "https://www.bing.com/search?q={query}",
            "bilibili": "https://search.bilibili.com/all?keyword={query}",
            "zhihu":    "https://www.zhihu.com/search?q={query}&type=content",
        }
        try:
            encoded = urllib.parse.quote_plus(keyword)
            if engine == "custom":
                tpl = custom_url if custom_url else "https://www.google.com/search?q={query}"
            else:
                tpl = ENGINES.get(engine, ENGINES["baidu"])
            url = tpl.replace("{query}", encoded)
            webbrowser.open(url)
            self._log("INFO", f"    浏览器搜索 [{engine}]: {keyword[:40]}")
        except Exception as e:
            self._log("WARN", f"    浏览器搜索失败: {e}")

    def _download_file(self, url: str, save_dir: str, filename_opt: str,
                       custom_name: str, overwrite: bool, save_path_to: str):
        """
        下载文件到本地。
        filename_opt: "original"=保持服务器文件名, "custom"=使用 custom_name
        save_dir 为空时默认使用系统下载目录。
        支持重命名预设占位符: {datetime}, {url_name}
        """
        import urllib.request
        import urllib.parse
        from datetime import datetime as _dt

        try:
            if not url:
                self._log("WARN", "    下载文件：URL 不能为空")
                return

            # 确定保存目录（默认：系统下载目录）
            if not save_dir:
                save_dir = os.path.join(os.path.expanduser("~"), "Downloads")
            os.makedirs(save_dir, exist_ok=True)

            # 确定文件名
            url_name = os.path.basename(urllib.parse.urlparse(url).path) or "download"
            if filename_opt == "custom" and custom_name:
                now = _dt.now()
                fname = custom_name
                fname = fname.replace("{datetime}", now.strftime("%Y%m%d_%H%M%S"))
                fname = fname.replace("{date}",     now.strftime("%Y%m%d"))
                fname = fname.replace("{url_name}", url_name)
                # 若无扩展名，自动加上原始扩展名
                if "." not in os.path.basename(fname):
                    ext = os.path.splitext(url_name)[1]
                    if ext:
                        fname = fname + ext
            else:
                fname = url_name

            save_path = os.path.join(save_dir, fname)

            # 冲突处理
            if os.path.exists(save_path) and not overwrite:
                base, ext = os.path.splitext(fname)
                counter = 1
                while os.path.exists(save_path):
                    save_path = os.path.join(save_dir, f"{base}_{counter}{ext}")
                    counter += 1

            self._log("INFO", f"    开始下载: {url[:60]}...")
            req = urllib.request.Request(url, headers={"User-Agent": "AutoFlow/2.2"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                CHUNK = 65536
                with open(save_path, "wb") as f:
                    while True:
                        self._check_stop()
                        chunk = resp.read(CHUNK)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            pct = downloaded * 100 // total
                            self._log("INFO", f"    下载中 {pct}%  {downloaded}/{total} bytes")

            self._log("INFO", f"    ✅ 下载完成: {save_path}")
            if save_path_to:
                self.variables[save_path_to] = save_path
        except StopTaskException:
            raise
        except Exception as e:
            self._log("ERROR", f"    下载文件失败: {e}")

    def _extract_archive(self, archive: str, dest_dir: str, create_folder: bool,
                         folder_name: str, custom_folder: str, overwrite: bool,
                         save_dest_to: str):
        """
        解压缩文件。支持 .zip / .tar.gz / .tar.bz2 / .tar / .7z（需要 py7zr）。
        archive: 支持具体路径、通配符（*.zip）、目录（解压目录下所有支持格式）。
        dest_dir: 解压到目标目录，为空则与压缩包同目录。
        create_folder: 是否在目标目录下创建同名文件夹再解压。
        folder_name: "archive_name"=压缩包名, "custom"=使用 custom_folder。
        """
        import zipfile
        import tarfile
        import glob as _glob

        # 展开文件列表
        if "*" in archive or "?" in archive:
            files = _glob.glob(archive, recursive=True)
        elif os.path.isdir(archive):
            files = []
            for root, _, names in os.walk(archive):
                for n in names:
                    if any(n.lower().endswith(ext) for ext in
                           (".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".7z", ".gz", ".bz2")):
                        files.append(os.path.join(root, n))
        elif os.path.isfile(archive):
            files = [archive]
        else:
            self._log("WARN", f"    解压缩：找不到文件 {archive}")
            return

        if not files:
            self._log("WARN", f"    解压缩：没有匹配的压缩文件 {archive}")
            return

        last_dest = ""
        for arc_path in files:
            self._check_stop()
            arc_name = os.path.splitext(os.path.basename(arc_path))[0]
            # 处理 .tar.gz/.tar.bz2 双扩展名
            if arc_name.endswith(".tar"):
                arc_name = arc_name[:-4]

            # 确定解压目标目录
            base_dir = dest_dir if dest_dir else os.path.dirname(os.path.abspath(arc_path))

            if create_folder:
                if folder_name == "custom" and custom_folder:
                    sub = custom_folder
                else:
                    sub = arc_name
                out_dir = os.path.join(base_dir, sub)
            else:
                out_dir = base_dir

            if overwrite and os.path.exists(out_dir) and create_folder:
                import shutil as _sh
                _sh.rmtree(out_dir)

            os.makedirs(out_dir, exist_ok=True)
            self._log("INFO", f"    解压 {arc_path} → {out_dir}")

            try:
                lower = arc_path.lower()
                if lower.endswith(".zip"):
                    with zipfile.ZipFile(arc_path, "r") as zf:
                        zf.extractall(out_dir)
                elif (lower.endswith(".tar.gz") or lower.endswith(".tgz")
                      or lower.endswith(".tar.bz2") or lower.endswith(".tar")
                      or lower.endswith(".gz") or lower.endswith(".bz2")):
                    with tarfile.open(arc_path, "r:*") as tf:
                        tf.extractall(out_dir)
                elif lower.endswith(".7z"):
                    try:
                        import py7zr
                        with py7zr.SevenZipFile(arc_path, mode="r") as sz:
                            sz.extractall(path=out_dir)
                    except ImportError:
                        self._log("WARN", "    解压 .7z 需要安装 py7zr: pip install py7zr")
                        continue
                else:
                    self._log("WARN", f"    不支持的压缩格式: {arc_path}")
                    continue
                self._log("INFO", f"    ✅ 解压完成: {out_dir}")
                last_dest = out_dir
            except Exception as e:
                self._log("ERROR", f"    解压失败 {arc_path}: {e}")

        if save_dest_to and last_dest:
            self.variables[save_dest_to] = last_dest

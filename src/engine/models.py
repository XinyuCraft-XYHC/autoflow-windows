"""
AutoFlow 核心数据模型
定义任务、功能块、触发器的数据结构
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import uuid
import json


# ─────────────────────────── 功能块定义 ───────────────────────────

BLOCK_TYPES = {
    # 流程控制
    "wait":            {"label": "等待",          "category": "流程控制", "color": "#5B8CFF", "icon": "⏳"},
    "if_block":        {"label": "如果 (if)",      "category": "流程控制", "color": "#FF9A3C", "icon": "🔀"},
    "elif_block":      {"label": "否则如果 (elif)","category": "流程控制", "color": "#FF9A3C", "icon": "🔁"},
    "else_block":      {"label": "否则 (else)",    "category": "流程控制", "color": "#FF9A3C", "icon": "🔀"},
    "if_end":          {"label": "结束条件 (end)", "category": "流程控制", "color": "#FF9A3C", "icon": "🔚"},
    "loop":            {"label": "循环",           "category": "流程控制", "color": "#FF9A3C", "icon": "🔁"},
    "loop_end":        {"label": "循环结束",       "category": "流程控制", "color": "#FF9A3C", "icon": "🔚"},
    "group":           {"label": "折叠块",         "category": "流程控制", "color": "#A080FF", "icon": "📦"},
    "group_end":       {"label": "折叠块结束",     "category": "流程控制", "color": "#A080FF", "icon": "🔒"},
    "break":           {"label": "跳出循环",       "category": "流程控制", "color": "#FF6B6B", "icon": "⛔"},
    "stop_task":       {"label": "停止任务",       "category": "流程控制", "color": "#FF6B6B", "icon": "🛑"},
    # 窗口 & 进程
    "launch_app":              {"label": "打开应用/文件",     "category": "应用&进程", "color": "#4CAF50", "icon": "🚀"},
    "close_window":            {"label": "关闭指定窗口",      "category": "应用&进程", "color": "#F44336", "icon": "❌"},
    "close_foreground_window": {"label": "关闭前台窗口",      "category": "应用&进程", "color": "#FF5722", "icon": "🪟"},
    "kill_process":            {"label": "结束进程",          "category": "应用&进程", "color": "#F44336", "icon": "💀"},
    "wait_window":     {"label": "等待窗口出现",   "category": "应用&进程", "color": "#5B8CFF", "icon": "🪟"},
    "wait_process":    {"label": "等待进程出现",   "category": "应用&进程", "color": "#5B8CFF", "icon": "⏳"},
    # 文件操作
    "copy_file":       {"label": "复制文件",       "category": "文件操作", "color": "#00BCD4", "icon": "📋"},
    "move_file":       {"label": "移动文件",       "category": "文件操作", "color": "#00BCD4", "icon": "📂"},
    "delete_file":     {"label": "删除文件",       "category": "文件操作", "color": "#F44336", "icon": "🗑️"},
    "read_file":       {"label": "读取文件内容",   "category": "文件操作", "color": "#00BCD4", "icon": "📖"},
    "write_file":      {"label": "写入文件内容",   "category": "文件操作", "color": "#00BCD4", "icon": "✏️"},
    "wait_file":       {"label": "等待文件变化",   "category": "文件操作", "color": "#5B8CFF", "icon": "👁️"},
    # 变量
    "set_variable":    {"label": "设置变量",       "category": "变量",    "color": "#FF5722", "icon": "📝"},
    "calc_variable":   {"label": "计算变量",       "category": "变量",    "color": "#FF5722", "icon": "🧮"},
    "show_variable":   {"label": "显示变量值",     "category": "变量",    "color": "#FF5722", "icon": "🔍"},
    # 媒体控制
    "media_play":      {"label": "媒体播放/暂停",  "category": "媒体控制", "color": "#E91E63", "icon": "▶️"},
    "media_next":      {"label": "下一首",         "category": "媒体控制", "color": "#E91E63", "icon": "⏭️"},
    "media_prev":      {"label": "上一首",         "category": "媒体控制", "color": "#E91E63", "icon": "⏮️"},
    "volume_set":      {"label": "设置音量",       "category": "媒体控制", "color": "#E91E63", "icon": "🔊"},
    # 通知 & 消息
    "notify":          {"label": "发送通知",       "category": "通知&消息", "color": "#FF9800", "icon": "🔔"},
    "send_email":      {"label": "发送邮件",       "category": "通知&消息", "color": "#FF9800", "icon": "📧"},
    "log_message":     {"label": "写日志",         "category": "通知&消息", "color": "#607D8B", "icon": "📋"},
    "msgbox":          {"label": "弹出消息框",     "category": "通知&消息", "color": "#FF9800", "icon": "💬"},
    "play_sound":      {"label": "播放声音",       "category": "通知&消息", "color": "#E91E63", "icon": "🎵"},
    # 系统
    "shutdown":        {"label": "关机/重启/睡眠", "category": "系统",    "color": "#795548", "icon": "⏻"},
    "screenshot":      {"label": "截图",           "category": "系统",    "color": "#795548", "icon": "📸"},
    "clipboard":       {"label": "读写剪贴板",     "category": "系统",    "color": "#795548", "icon": "📋"},
    "keyboard":        {"label": "模拟按键",       "category": "键鼠操作", "color": "#E91E63", "icon": "⌨️"},
    "hotkey_input":    {"label": "常用按键输入",   "category": "键鼠操作", "color": "#E91E63", "icon": "🎹"},
    "capslock":        {"label": "大写锁定",       "category": "键鼠操作", "color": "#E91E63", "icon": "🔠"},
    "input_text":      {"label": "输入文字",       "category": "系统",    "color": "#795548", "icon": "✍️"},
    "http_request":    {"label": "HTTP请求",       "category": "系统",    "color": "#3F51B5", "icon": "🌐"},
    "open_url":        {"label": "打开网址",       "category": "系统",    "color": "#3F51B5", "icon": "🔗"},
    "exec_command":    {"label": "执行命令",       "category": "系统",    "color": "#9C27B0", "icon": "💻"},
    "turn_off_display":{"label": "关闭显示器",     "category": "系统",    "color": "#607D8B", "icon": "🖥️"},
    # 网络工具
    "get_ping_latency": {"label": "获取连接延迟",    "category": "系统",    "color": "#3F51B5", "icon": "📡"},
    "run_task":        {"label": "运行任务",         "category": "任务控制","color": "#4CAF50", "icon": "▶"},
    "stop_other_task": {"label": "停止其他任务",   "category": "任务控制","color": "#FF5722", "icon": "⏹"},
    "wait_task_done":  {"label": "等待任务完成",   "category": "任务控制","color": "#5B8CFF", "icon": "⏳"},
    # 键鼠操作
    "mouse_move":      {"label": "移动鼠标",       "category": "键鼠操作", "color": "#E91E63", "icon": "🖱️"},
    "mouse_click_pos": {"label": "鼠标点击坐标",   "category": "键鼠操作", "color": "#E91E63", "icon": "👆"},
    "mouse_scroll":    {"label": "鼠标滚轮",       "category": "键鼠操作", "color": "#E91E63", "icon": "🖱️"},
    "mouse_drag":      {"label": "鼠标拖拽",       "category": "键鼠操作", "color": "#E91E63", "icon": "↔️"},
    "keymouse_macro":  {"label": "键鼠宏",         "category": "键鼠操作", "color": "#C2185B", "icon": "🎬"},
    # 窗口管理
    "activate_window": {"label": "激活/前置窗口",  "category": "应用&进程", "color": "#4CAF50", "icon": "🪟"},
    "set_window_topmost": {"label": "窗口置顶/取消", "category": "应用&进程", "color": "#5B8CFF", "icon": "📌"},
    "move_window":     {"label": "移动/缩放窗口",  "category": "应用&进程", "color": "#5B8CFF", "icon": "📐"},
    "get_window_info": {"label": "获取窗口信息",   "category": "应用&进程", "color": "#607D8B", "icon": "🔍"},
    "minimize_window": {"label": "最小化窗口",     "category": "应用&进程", "color": "#607D8B", "icon": "➖"},
    "maximize_window": {"label": "最大化窗口",     "category": "应用&进程", "color": "#607D8B", "icon": "⬜"},
    # 系统辅助
    "show_desktop":    {"label": "显示/隐藏桌面",  "category": "系统",    "color": "#607D8B", "icon": "🖥️"},
    "lock_computer":   {"label": "锁定计算机",     "category": "系统",    "color": "#607D8B", "icon": "🔒"},
    # 互联网&工具
    "launch_steam":    {"label": "启动Steam游戏",  "category": "应用&进程", "color": "#1B2838", "icon": "🎮"},
    "browser_search":  {"label": "浏览器搜索",     "category": "系统",    "color": "#3F51B5", "icon": "🔍"},
    "download_file":   {"label": "下载文件",       "category": "文件操作", "color": "#00BCD4", "icon": "⬇️"},
    "extract_archive": {"label": "解压缩",         "category": "文件操作", "color": "#FF9800", "icon": "📦"},
    # AI 大模型
    "ai_chat":         {"label": "AI 对话",         "category": "AI",      "color": "#6366F1", "icon": "🤖"},
    "ai_generate":     {"label": "AI 生成文本",     "category": "AI",      "color": "#6366F1", "icon": "✨"},
    "browser_auto":    {"label": "AI 浏览器自动化", "category": "浏览器操作", "color": "#06B6D4", "icon": "🌐"},
    # 浏览器基础操作
    "browser_open_url":    {"label": "浏览器打开网址",   "category": "浏览器操作", "color": "#0EA5E9", "icon": "🔗"},
    "browser_click":       {"label": "浏览器点击元素",   "category": "浏览器操作", "color": "#0EA5E9", "icon": "👆"},
    "browser_type":        {"label": "浏览器输入文字",   "category": "浏览器操作", "color": "#0EA5E9", "icon": "⌨️"},
    "browser_get_text":    {"label": "浏览器获取文本",   "category": "浏览器操作", "color": "#0EA5E9", "icon": "📝"},
    "browser_screenshot":  {"label": "浏览器截图",       "category": "浏览器操作", "color": "#0EA5E9", "icon": "📸"},
    "browser_wait_element":{"label": "浏览器等待元素",   "category": "浏览器操作", "color": "#0EA5E9", "icon": "⏳"},
    # 屏幕识别
    "screen_find_image":   {"label": "屏幕查找图片",     "category": "屏幕识别", "color": "#10B981", "icon": "🔍"},
    "screen_click_image":  {"label": "屏幕点击图片",     "category": "屏幕识别", "color": "#10B981", "icon": "🖱️"},
    "screen_wait_image":   {"label": "等待图片出现",     "category": "屏幕识别", "color": "#10B981", "icon": "⏳"},
    "screen_screenshot_region": {"label": "区域截图",    "category": "屏幕识别", "color": "#10B981", "icon": "✂️"},
    # 窗口控件操作
    "win_find_window":     {"label": "查找窗口",         "category": "窗口控件", "color": "#F59E0B", "icon": "🔎"},
    "win_click_control":   {"label": "点击控件",         "category": "窗口控件", "color": "#F59E0B", "icon": "👆"},
    "win_input_control":   {"label": "向控件输入文字",   "category": "窗口控件", "color": "#F59E0B", "icon": "⌨️"},
    "win_get_control_text":{"label": "获取控件文本",     "category": "窗口控件", "color": "#F59E0B", "icon": "📋"},
    "win_wait_window":     {"label": "等待窗口(控件级)", "category": "窗口控件", "color": "#F59E0B", "icon": "⏳"},
    "win_close_window":    {"label": "关闭窗口(控件级)", "category": "窗口控件", "color": "#F59E0B", "icon": "❌"},
}

# 每种块的参数规格：  param_name -> {type, label, default, options?, placeholder?}
BLOCK_PARAMS: Dict[str, Dict[str, Any]] = {
    "wait": {
        "duration": {"type": "number_or_var", "label": "等待时长(秒)", "default": 1, "placeholder": "秒数或变量名"},
    },
    # ── 新版 if/elif/else/if_end 扁平结构 ──
    # 条件参数与 condition 相同；elif_block 也复用
    "if_block": {
        "condition_type": {"type": "select", "label": "条件类型", "default": "process_exists",
                           "options": ["process_exists", "window_exists", "file_exists",
                                       "file_changed", "variable_equals", "variable_gt",
                                       "variable_lt", "variable_contains",
                                       "clipboard_contains", "internet_connected",
                                       "ping_latency_gt", "ping_latency_lt",
                                       "capslock_on",
                                       "cpu_above", "memory_above",
                                       "battery_below", "battery_charging",
                                       "time_between", "day_of_week",
                                       "always_true"],
                           "option_labels": ["进程存在", "窗口存在", "文件存在",
                                             "文件变化", "变量等于", "变量大于",
                                             "变量小于", "变量包含",
                                             "剪贴板包含", "已连接互联网",
                                             "Ping延迟大于(ms)", "Ping延迟小于(ms)",
                                             "大写锁定已开启",
                                             "CPU占用超过(%)", "内存占用超过(%)",
                                             "电池低于(%)", "正在充电",
                                             "时间在范围内", "今天是指定星期",
                                             "始终为真"]},
        "target":         {"type": "condition_target", "label": "目标值", "default": ""},
        "value":          {"type": "text", "label": "比较值(变量)/延迟ms(Ping)/结束时间(时间范围)", "default": ""},
        "negate":         {"type": "bool", "label": "取反(NOT)", "default": False},
    },
    "elif_block": {
        "condition_type": {"type": "select", "label": "条件类型", "default": "process_exists",
                           "options": ["process_exists", "window_exists", "file_exists",
                                       "file_changed", "variable_equals", "variable_gt",
                                       "variable_lt", "variable_contains",
                                       "clipboard_contains", "internet_connected",
                                       "ping_latency_gt", "ping_latency_lt",
                                       "capslock_on",
                                       "cpu_above", "memory_above",
                                       "battery_below", "battery_charging",
                                       "time_between", "day_of_week",
                                       "always_true"],
                           "option_labels": ["进程存在", "窗口存在", "文件存在",
                                             "文件变化", "变量等于", "变量大于",
                                             "变量小于", "变量包含",
                                             "剪贴板包含", "已连接互联网",
                                             "Ping延迟大于(ms)", "Ping延迟小于(ms)",
                                             "大写锁定已开启",
                                             "CPU占用超过(%)", "内存占用超过(%)",
                                             "电池低于(%)", "正在充电",
                                             "时间在范围内", "今天是指定星期",
                                             "始终为真"]},
        "target":         {"type": "condition_target", "label": "目标值", "default": ""},
        "value":          {"type": "text", "label": "比较值(变量)/延迟ms(Ping)/结束时间(时间范围)", "default": ""},
        "negate":         {"type": "bool", "label": "取反(NOT)", "default": False},
    },
    "else_block": {},
    "if_end":    {},
    "loop": {
        "loop_type":  {"type": "select", "label": "循环类型", "default": "count",
                       "options": ["count", "while_process", "while_window",
                                   "while_file_exists", "while_variable", "infinite"],
                       "option_labels": ["固定次数", "当进程存在时", "当窗口存在时",
                                         "当文件存在时", "当变量满足条件时", "无限循环"]},
        "count":      {"type": "number_or_var", "label": "循环次数", "default": 3},
        "target":     {"type": "text", "label": "监测目标(进程/窗口/文件/变量名)", "default": ""},
        "value":      {"type": "text", "label": "变量比较值", "default": ""},
    },
    "launch_app": {
        "path":    {"type": "app_launcher_picker", "label": "文件/应用路径", "default": ""},
        "args":    {"type": "text", "label": "启动参数", "default": ""},
        "wait":    {"type": "bool", "label": "等待启动完成", "default": False},
        "as_admin":{"type": "bool", "label": "以管理员身份运行", "default": False},
    },
    "close_window": {
        "match_mode": {"type": "select", "label": "识别方式", "default": "title",
                       "options": ["title", "hwnd", "process"],
                       "option_labels": ["窗口标题", "窗口句柄(hwnd)", "所属进程名"]},
        "title":   {"type": "window_picker",   "label": "窗口标题(支持*通配符)", "default": ""},
        "hwnd":    {"type": "text",            "label": "窗口句柄(十进制/十六进制)", "default": ""},
        "process": {"type": "process_picker",  "label": "进程名(关闭其所有窗口)", "default": ""},
        "force":   {"type": "bool", "label": "强制关闭", "default": False},
    },
    "close_foreground_window": {
        "title": {"type": "window_picker", "label": "窗口标题(留空=当前前台窗口)", "default": "",
                  "placeholder": "留空关闭当前前台窗口，或填精确标题"},
    },
    "kill_process": {
        "match_mode": {"type": "select", "label": "识别方式", "default": "name",
                       "options": ["name", "pid", "window_title"],
                       "option_labels": ["进程名", "进程PID", "窗口标题"]},
        "name":         {"type": "process_picker", "label": "进程名(如 notepad.exe)", "default": ""},
        "pid":          {"type": "text",           "label": "进程 PID", "default": ""},
        "window_title": {"type": "window_picker",  "label": "窗口标题(关闭该窗口的进程)", "default": ""},
    },
    "wait_window": {
        "match_mode": {"type": "select", "label": "识别方式", "default": "title",
                       "options": ["title", "hwnd", "process"],
                       "option_labels": ["窗口标题", "窗口句柄(hwnd)", "所属进程名"]},
        "title":   {"type": "window_picker",  "label": "窗口标题(支持*通配符)", "default": ""},
        "hwnd":    {"type": "text",           "label": "窗口句柄(十进制/十六进制)", "default": ""},
        "process": {"type": "process_picker", "label": "进程名(等待其窗口出现)", "default": ""},
        "timeout": {"type": "number_or_var", "label": "超时秒数(0=无限)", "default": 30},
        "on_timeout": {"type": "select", "label": "超时行为", "default": "continue",
                       "options": ["continue", "stop_task"],
                       "option_labels": ["继续执行", "停止任务"]},
    },
    "wait_process": {
        "match_mode": {"type": "select", "label": "识别方式", "default": "name",
                       "options": ["name", "pid"],
                       "option_labels": ["进程名", "进程PID"]},
        "name":    {"type": "process_picker", "label": "进程名(如 chrome.exe)", "default": ""},
        "pid":     {"type": "text",           "label": "进程 PID", "default": ""},
        "timeout": {"type": "number_or_var", "label": "超时秒数(0=无限)", "default": 30},
        "on_timeout": {"type": "select", "label": "超时行为", "default": "continue",
                       "options": ["continue", "stop_task"],
                       "option_labels": ["继续执行", "停止任务"]},
    },
    "run_command": {
        "command": {"type": "text_multiline", "label": "命令", "default": ""},
        "shell":   {"type": "select", "label": "Shell", "default": "cmd",
                    "options": ["cmd", "powershell"]},
        "wait":    {"type": "bool", "label": "等待完成", "default": True},
        "save_output": {"type": "text", "label": "输出存入变量(可选)", "default": ""},
        "as_admin": {"type": "bool", "label": "以管理员身份运行", "default": False},
    },
    "copy_file": {
        "src":  {"type": "file_picker", "label": "源文件/文件夹", "default": ""},
        "dst":  {"type": "folder_picker", "label": "目标路径", "default": ""},
        "overwrite": {"type": "bool", "label": "覆盖已存在", "default": True},
    },
    "move_file": {
        "src":  {"type": "file_picker", "label": "源文件/文件夹", "default": ""},
        "dst":  {"type": "folder_picker", "label": "目标路径", "default": ""},
    },
    "delete_file": {
        "path":    {"type": "file_picker", "label": "文件/文件夹路径", "default": ""},
        "confirm": {"type": "bool", "label": "执行前确认", "default": True},
    },
    "read_file": {
        "path":     {"type": "file_picker", "label": "文件路径", "default": ""},
        "encoding": {"type": "select", "label": "编码", "default": "utf-8",
                     "options": ["utf-8", "gbk", "utf-16", "ascii"]},
        "save_to":  {"type": "text", "label": "存入变量名", "default": "file_content"},
    },
    "write_file": {
        "path":    {"type": "file_picker", "label": "文件路径", "default": ""},
        "content": {"type": "text_multiline", "label": "内容(支持{{变量}})", "default": ""},
        "mode":    {"type": "select", "label": "写入模式", "default": "overwrite",
                    "options": ["overwrite", "append"],
                    "option_labels": ["覆盖写入", "追加到末尾"]},
        "encoding": {"type": "select", "label": "编码", "default": "utf-8",
                     "options": ["utf-8", "gbk", "utf-16"]},
    },
    "wait_file": {
        "path":    {"type": "file_picker", "label": "监测文件/目录", "default": ""},
        "event":   {"type": "select", "label": "事件类型", "default": "any",
                    "options": ["any", "created", "modified", "deleted"],
                    "option_labels": ["任意变化", "文件创建", "文件修改", "文件删除"]},
        "timeout": {"type": "number_or_var", "label": "超时秒数(0=无限)", "default": 60},
    },
    "set_variable": {
        "name":  {"type": "text", "label": "变量名", "default": "my_var"},
        "value": {"type": "text", "label": "值(支持{{变量}})", "default": ""},
        "type":  {"type": "select", "label": "类型", "default": "string",
                  "options": ["string", "number", "bool"],
                  "option_labels": ["文本", "数字", "布尔值"]},
    },
    "calc_variable": {
        "name":       {"type": "text", "label": "变量名", "default": "result"},
        "expression": {"type": "text", "label": "表达式(如 {{count}}+1)", "default": ""},
    },
    "show_variable": {
        "name": {"type": "text", "label": "变量名", "default": ""},
    },
    "media_play":  {},
    "media_next":  {},
    "media_prev":  {},
    "volume_set": {
        "level":   {"type": "number_or_var", "label": "音量(0-100)", "default": 50},
        "target":  {"type": "text", "label": "目标进程/窗口(留空=全局)", "default": "",
                    "placeholder": "留空=全局音量，填进程名如 chrome.exe 或窗口标题"},
        "target_type": {"type": "select", "label": "目标类型", "default": "global",
                        "options": ["global", "process", "window"],
                        "option_labels": ["全局音量", "指定进程", "指定窗口"]},
    },
    "notify": {
        "title":   {"type": "text", "label": "标题", "default": "AutoFlow通知"},
        "message": {"type": "text", "label": "消息(支持{{变量}})", "default": ""},
        "timeout": {"type": "number_or_var", "label": "显示秒数", "default": 5},
    },
    "send_email": {
        "to":      {"type": "text", "label": "收件人", "default": ""},
        "subject": {"type": "text", "label": "主题(支持{{变量}})", "default": ""},
        "body":    {"type": "text_multiline", "label": "正文(支持{{变量}})", "default": ""},
    },
    "log_message": {
        "message": {"type": "text", "label": "日志内容(支持{{变量}})", "default": ""},
        "level":   {"type": "select", "label": "级别", "default": "INFO",
                    "options": ["INFO", "WARN", "ERROR"]},
    },
    "shutdown": {
        "action":  {"type": "select", "label": "操作", "default": "shutdown",
                    "options": ["shutdown", "restart", "sleep", "hibernate", "logoff"],
                    "option_labels": ["关机", "重启", "睡眠", "休眠", "注销"]},
        "delay":   {"type": "number_or_var", "label": "延迟秒数", "default": 0},
        "confirm": {"type": "bool", "label": "执行前确认", "default": True},
    },
    "screenshot": {
        "mode":        {"type": "select", "label": "截图模式", "default": "save_file",
                        "options": ["save_file", "clipboard", "save_and_clipboard"],
                        "option_labels": ["保存为文件", "复制到剪贴板", "保存文件并复制到剪贴板"]},
        "save_path":   {"type": "text", "label": "保存目录(空=图片库)", "default": ""},
        "filename_fmt":{"type": "text", "label": "文件名格式", "default": "screenshot_{datetime}",
                        "placeholder": "支持 {datetime} {date} {time} {index}"},
        "format":      {"type": "select", "label": "图片格式", "default": "png",
                        "options": ["png", "jpg", "bmp"]},
        "region":      {"type": "select", "label": "截图范围", "default": "fullscreen",
                        "options": ["fullscreen", "active_window"],
                        "option_labels": ["全屏", "当前活动窗口"]},
    },
    "clipboard": {
        "action":  {"type": "select", "label": "操作", "default": "get",
                    "options": ["get", "set"],
                    "option_labels": ["读取剪贴板", "写入剪贴板"]},
        "content": {"type": "text", "label": "设置内容(支持{{变量}})", "default": ""},
        "save_to": {"type": "text", "label": "读取结果存入变量", "default": "clipboard_text"},
    },
    "keyboard": {
        "keys": {"type": "text", "label": "按键组合(如 ctrl+c, win+d)", "default": ""},
    },
    "hotkey_input": {
        "key":    {"type": "select", "label": "按键", "default": "enter",
                   "options": ["enter", "tab", "space", "backspace", "delete",
                               "escape", "home", "end", "pageup", "pagedown",
                               "up", "down", "left", "right",
                               "f1","f2","f3","f4","f5","f6","f7","f8","f9","f10","f11","f12",
                               "printscreen", "insert", "numlock", "scrolllock", "pause",
                               "ctrl+a", "ctrl+c", "ctrl+v", "ctrl+x", "ctrl+z", "ctrl+y",
                               "ctrl+s", "ctrl+w", "alt+f4", "win+d", "win+l"],
                   "option_labels": ["回车 Enter", "制表 Tab", "空格 Space", "退格 Backspace", "删除 Delete",
                                     "退出 Escape", "Home", "End", "Page Up", "Page Down",
                                     "↑ 上", "↓ 下", "← 左", "→ 右",
                                     "F1","F2","F3","F4","F5","F6","F7","F8","F9","F10","F11","F12",
                                     "截图 PrintScreen", "Insert", "NumLock", "ScrollLock", "Pause",
                                     "全选 Ctrl+A", "复制 Ctrl+C", "粘贴 Ctrl+V", "剪切 Ctrl+X", "撤销 Ctrl+Z", "重做 Ctrl+Y",
                                     "保存 Ctrl+S", "关标签 Ctrl+W", "关窗口 Alt+F4", "显示桌面 Win+D", "锁屏 Win+L"]},
        "repeat":  {"type": "number_or_var", "label": "按下次数", "default": 1},
        "delay_ms":{"type": "number_or_var", "label": "按次间隔(毫秒)", "default": 50},
    },
    "capslock": {
        "action": {"type": "select", "label": "操作", "default": "toggle",
                   "options": ["on", "off", "toggle", "get"],
                   "option_labels": ["开启大写锁定", "关闭大写锁定", "切换大写锁定", "获取状态存入变量"]},
        "save_to": {"type": "text", "label": "状态存入变量(get模式下)", "default": "capslock_state",
                    "placeholder": "值为 True 或 False"},
    },
    "http_request": {
        "url":     {"type": "text", "label": "URL", "default": "https://"},
        "method":  {"type": "select", "label": "方法", "default": "GET",
                    "options": ["GET", "POST", "PUT", "DELETE"]},
        "headers": {"type": "text_multiline", "label": "Headers(JSON)", "default": "{}"},
        "body":    {"type": "text_multiline", "label": "请求体", "default": ""},
        "save_to": {"type": "text", "label": "响应存入变量", "default": "http_resp"},
    },
    "stop_task": {},
    "break":     {},
    "loop_end":  {},
    "group": {
        "title":       {"type": "text",   "label": "折叠块标题", "default": "分组"},
        "description": {"type": "text",   "label": "描述",       "default": ""},
        "color":       {"type": "select", "label": "标题颜色",   "default": "#A080FF",
                        "options": ["#A080FF", "#5B8CFF", "#4CAF50", "#FF9A3C",
                                    "#F44336", "#E91E63", "#00BCD4", "#FF9800"]},
        "collapsed":   {"type": "bool",   "label": "默认折叠",   "default": False},
    },
    "group_end": {},
    # ── 新增功能块参数 ──
    "msgbox": {
        "text":    {"type": "text_multiline", "label": "消息内容(支持{{变量}})", "default": "提示信息"},
        "title":   {"type": "text", "label": "标题",  "default": "AutoFlow"},
        "buttons": {"type": "select", "label": "按钮", "default": "ok",
                    "options": ["ok", "ok_cancel", "yes_no", "yes_no_cancel"],
                    "option_labels": ["确定", "确定/取消", "是/否", "是/否/取消"]},
        "icon":    {"type": "select", "label": "图标", "default": "info",
                    "options": ["info", "warning", "error", "question"],
                    "option_labels": ["信息", "警告", "错误", "询问"]},
        "save_to": {"type": "text", "label": "结果存入变量", "default": "msgbox_result"},
    },
    "play_sound": {
        "path":   {"type": "file_picker", "label": "音频文件(.wav/.mp3)", "default": ""},
        "wait":   {"type": "bool", "label": "等待播放完成", "default": False},
    },
    "input_text": {
        "text":  {"type": "text_multiline", "label": "输入内容(支持{{变量}})", "default": ""},
        "delay": {"type": "number_or_var",  "label": "每字符间隔(毫秒)",       "default": 0},
    },
    "open_url": {
        "url":     {"type": "text", "label": "网址(支持{{变量}})", "default": "https://",
                    "placeholder": "https://example.com 或 file:///C:/..."},
        "browser": {"type": "select", "label": "打开方式", "default": "default",
                    "options": ["default", "chrome", "firefox", "edge"],
                    "option_labels": ["默认浏览器", "Chrome", "Firefox", "Edge"]},
    },
    "mouse_move": {
        "pos":        {"type": "coord_picker", "label": "目标坐标", "default": {"x": 0, "y": 0}},
        "relative":   {"type": "bool", "label": "相对移动(否=绝对坐标)", "default": False},
        "duration":   {"type": "number_or_var", "label": "移动时长(秒,0=瞬间)", "default": 0},
        "curve":      {"type": "select", "label": "移动曲线", "default": "linear",
                       "options": ["linear", "ease_in", "ease_out", "ease_in_out", "ease_in_cubic", "ease_out_cubic", "ease_out_back", "spring", "bezier", "humanize"],
                       "option_labels": ["线性", "缓入(二次)", "缓出(二次)", "缓入缓出(平滑)", "缓入(三次)", "缓出(三次)", "超出回弹", "弹性", "贝塞尔弧线", "拟人化曲线"]},
        "jitter":     {"type": "number_or_var", "label": "随机抖动半径(像素,0=关闭)", "default": 0},
        "offset":     {"type": "number_or_var", "label": "随机偏移半径(像素,0=关闭)", "default": 0},
    },
    "mouse_click_pos": {
        "pos":           {"type": "coord_picker", "label": "点击坐标", "default": {"x": 0, "y": 0}},
        "button":        {"type": "select", "label": "鼠标键", "default": "left",
                          "options": ["left", "right", "middle"],
                          "option_labels": ["左键", "右键", "中键(滚轮)"]},
        "clicks":        {"type": "number_or_var", "label": "点击次数", "default": 1},
        "click_interval":{"type": "number_or_var", "label": "多次点击间隔(秒,默认0.12)", "default": 0.12},
        "down_up_delay": {"type": "number_or_var", "label": "按下松开延迟(秒,默认0.05)", "default": 0.05},
        "move_first":    {"type": "bool", "label": "先移动到坐标再点击", "default": True},
        "offset":        {"type": "number_or_var", "label": "随机偏移半径(像素,0=关闭)", "default": 0},
        "move_curve":    {"type": "select", "label": "移动曲线(先移动时有效)", "default": "linear",
                          "options": ["linear", "ease_in", "ease_out", "ease_in_out", "ease_in_cubic", "ease_out_cubic", "ease_out_back", "spring", "bezier", "humanize"],
                          "option_labels": ["线性", "缓入(二次)", "缓出(二次)", "缓入缓出(平滑)", "缓入(三次)", "缓出(三次)", "超出回弹", "弹性", "贝塞尔弧线", "拟人化曲线"]},
        "move_duration": {"type": "number_or_var", "label": "移动时长(秒,0=瞬间)", "default": 0},
    },
    "mouse_scroll": {
        "pos":    {"type": "coord_picker", "label": "滚动位置(0,0=当前位置)", "default": {"x": 0, "y": 0}},
        "amount": {"type": "number_or_var", "label": "滚动量(正数向上)", "default": 3},
    },
    "mouse_drag": {
        "from_pos":  {"type": "coord_picker", "label": "起始坐标", "default": {"x": 0, "y": 0}},
        "to_pos":    {"type": "coord_picker", "label": "目标坐标", "default": {"x": 100, "y": 100}},
        "button":    {"type": "select", "label": "拖拽键", "default": "left",
                      "options": ["left", "right", "middle"],
                      "option_labels": ["左键", "右键", "中键(滚轮)"]},
        "duration":  {"type": "number_or_var", "label": "拖拽时长(秒)", "default": 0.5},
        "curve":     {"type": "select", "label": "移动曲线", "default": "linear",
                      "options": ["linear", "ease_in", "ease_out", "ease_in_out", "ease_in_cubic", "ease_out_cubic", "ease_out_back", "spring", "bezier", "humanize"],
                      "option_labels": ["线性", "缓入(二次)", "缓出(二次)", "缓入缓出(平滑)", "缓入(三次)", "缓出(三次)", "超出回弹", "弹性", "贝塞尔弧线", "拟人化曲线"]},
        "jitter":    {"type": "number_or_var", "label": "随机抖动半径(像素,0=关闭)", "default": 0},
    },
    "keymouse_macro": {
        "macro_data":   {"type": "macro_recorder", "label": "录制数据", "default": []},
        "speed":        {"type": "number_or_var", "label": "回放速度倍率(1.0=原速)", "default": 1.0},
        "repeat":       {"type": "number_or_var", "label": "重复次数", "default": 1},
        "use_relative": {"type": "bool", "label": "使用相对坐标(适配不同分辨率)", "default": True},
    },
    "launch_app": {
        "path":      {"type": "app_launcher_picker", "label": "程序路径/命令(支持{{变量}})", "default": "",
                      "placeholder": "如 C:\\Program Files\\xxx\\app.exe 或 notepad 或 {{path_var}}"},
        "args":      {"type": "text", "label": "启动参数(可选，支持{{变量}})", "default": "",
                      "placeholder": "传给程序的参数，如 --fullscreen 或 C:\\file.txt"},
        "cwd":       {"type": "text", "label": "工作目录(可选)", "default": "",
                      "placeholder": "程序的工作目录，留空=默认"},
        "run_mode":  {"type": "select", "label": "窗口模式", "default": "normal",
                      "options": ["normal", "minimized", "maximized", "hidden"],
                      "option_labels": ["正常窗口", "最小化启动", "最大化启动", "后台静默(无窗口)"]},
        "as_admin":  {"type": "bool", "label": "以管理员身份运行", "default": False},
        "wait":      {"type": "bool", "label": "等待程序退出再继续", "default": False},
        "timeout":   {"type": "number_or_var", "label": "等待超时(秒,0=无限)", "default": 0},
        "save_pid":  {"type": "text", "label": "进程ID存入变量(可选)", "default": "",
                      "placeholder": "变量名，用于后续操作该进程"},
    },
    "activate_window": {
        "match_mode": {"type": "select", "label": "识别方式", "default": "title",
                       "options": ["title", "hwnd", "process"],
                       "option_labels": ["窗口标题", "窗口句柄(hwnd)", "所属进程名"]},
        "title":   {"type": "window_picker",  "label": "窗口标题", "default": ""},
        "hwnd":    {"type": "text",           "label": "窗口句柄(十进制/十六进制)", "default": ""},
        "process": {"type": "process_picker", "label": "进程名(激活其主窗口)", "default": ""},
        "wait_timeout": {"type": "number_or_var", "label": "等待超时(秒,0=不等待)", "default": 0},
    },
    "set_window_topmost": {
        "match_mode": {"type": "select", "label": "识别方式", "default": "title",
                       "options": ["title", "hwnd"],
                       "option_labels": ["窗口标题", "窗口句柄(hwnd)"]},
        "title":   {"type": "window_picker", "label": "窗口标题", "default": ""},
        "hwnd":    {"type": "text",          "label": "窗口句柄(十进制/十六进制)", "default": ""},
        "topmost": {"type": "bool", "label": "置顶(否=取消置顶)", "default": True},
    },
    "move_window": {
        "match_mode": {"type": "select", "label": "识别方式", "default": "title",
                       "options": ["title", "hwnd"],
                       "option_labels": ["窗口标题", "窗口句柄(hwnd)"]},
        "title":  {"type": "window_picker", "label": "窗口标题", "default": ""},
        "hwnd":   {"type": "text",          "label": "窗口句柄(十进制/十六进制)", "default": ""},
        "x":      {"type": "number_or_var", "label": "左边位置X(-1=不变)", "default": -1},
        "y":      {"type": "number_or_var", "label": "顶部位置Y(-1=不变)", "default": -1},
        "width":  {"type": "number_or_var", "label": "宽度(-1=不变)", "default": -1},
        "height": {"type": "number_or_var", "label": "高度(-1=不变)", "default": -1},
    },
    "get_window_info": {
        "match_mode": {"type": "select", "label": "识别方式", "default": "title",
                       "options": ["title", "hwnd"],
                       "option_labels": ["窗口标题", "窗口句柄(hwnd)"]},
        "title":   {"type": "window_picker", "label": "窗口标题", "default": ""},
        "hwnd":    {"type": "text",          "label": "窗口句柄(十进制/十六进制)", "default": ""},
        "save_to": {"type": "text", "label": "信息存入变量前缀", "default": "win",
                    "placeholder": "会生成 {前缀}_title, {前缀}_x, {前缀}_y, {前缀}_w, {前缀}_h, {前缀}_hwnd"},
    },
    "minimize_window": {
        "match_mode": {"type": "select", "label": "识别方式", "default": "title",
                       "options": ["title", "hwnd"],
                       "option_labels": ["窗口标题", "窗口句柄(hwnd)"]},
        "title": {"type": "window_picker", "label": "窗口标题(留空=前台窗口)", "default": ""},
        "hwnd":  {"type": "text",          "label": "窗口句柄(留空=前台窗口)", "default": ""},
    },
    "maximize_window": {
        "match_mode": {"type": "select", "label": "识别方式", "default": "title",
                       "options": ["title", "hwnd"],
                       "option_labels": ["窗口标题", "窗口句柄(hwnd)"]},
        "title": {"type": "window_picker", "label": "窗口标题(留空=前台窗口)", "default": ""},
        "hwnd":  {"type": "text",          "label": "窗口句柄(留空=前台窗口)", "default": ""},
    },
    "exec_command": {
        "command":    {"type": "text_multiline", "label": "命令内容(支持{{变量}})", "default": ""},
        "shell":      {"type": "select", "label": "执行方式", "default": "cmd",
                       "options": ["cmd", "powershell", "bat", "python", "wscript", "bash"],
                       "option_labels": ["CMD 命令行", "PowerShell", "批处理(.bat)", "Python 脚本", "VBScript", "Bash(WSL)"]},
        "run_mode":   {"type": "select", "label": "运行模式", "default": "normal",
                       "options": ["normal", "hidden"],
                       "option_labels": ["正常窗口", "后台静默"]},
        "as_admin":   {"type": "bool", "label": "以管理员身份运行", "default": False},
        "wait":       {"type": "bool", "label": "等待执行完成", "default": True},
        "save_output": {"type": "text", "label": "输出存入变量(仅非管理员模式)", "default": ""},
        "ai_cmd_desc": {"type": "ai_cmd_gen", "label": "🤖 AI 智能生成命令", "default": "",
                        "placeholder": "描述要做什么，点击「生成」按钮自动填入命令"},
    },
    "turn_off_display": {
        "delay_sec": {"type": "number_or_var", "label": "延迟秒数(0=立即)", "default": 0},
    },
    # ── 网络工具块 ──
    "get_ping_latency": {
        "host":    {"type": "text", "label": "目标主机(IP/域名，支持{{变量}})", "default": "8.8.8.8",
                    "placeholder": "如 8.8.8.8 或 www.baidu.com 或 {{host_var}}"},
        "count":   {"type": "number_or_var", "label": "Ping次数", "default": 1},
        "save_to": {"type": "text", "label": "延迟结果存入变量(ms，超时=-1)", "default": "ping_ms",
                    "placeholder": "变量名，超时/不可达时存入 -1"},
    },
    "run_task": {
        "task_id":  {"type": "task_picker", "label": "目标任务", "default": "",
                     "placeholder": "选择要运行的任务"},
        "wait":     {"type": "bool", "label": "等待任务完成再继续", "default": False},
        "timeout":  {"type": "number_or_var", "label": "等待超时(秒,0=无限)", "default": 0},
    },
    "stop_other_task": {
        "task_id":  {"type": "task_picker", "label": "目标任务", "default": "",
                     "placeholder": "选择要停止的任务"},
    },
    "wait_task_done": {
        "task_id":  {"type": "task_picker", "label": "目标任务", "default": "",
                     "placeholder": "等待该任务执行完毕"},
        "timeout":  {"type": "number_or_var", "label": "超时秒数(0=无限等待)", "default": 60},
        "on_timeout": {"type": "select", "label": "超时后行为", "default": "continue",
                       "options": ["continue", "stop_task"],
                       "option_labels": ["继续执行", "停止任务"]},
    },
    # ── 新增功能块 ──
    "show_desktop": {},   # 无参数：切换显示/隐藏桌面
    "lock_computer": {},  # 无参数：锁定计算机（Win+L）
    "launch_steam": {
        "app_id":   {"type": "text", "label": "Steam AppID", "default": "",
                     "placeholder": "游戏的 Steam AppID，如 730（CS2）、570（Dota2）"},
        "save_to":  {"type": "text", "label": "结果存入变量(可选)", "default": ""},
    },
    "browser_search": {
        "keyword":  {"type": "text", "label": "搜索关键词(支持{{变量}})", "default": "",
                     "placeholder": "搜索内容，支持 {{变量名}}"},
        "engine":   {"type": "select", "label": "搜索引擎", "default": "baidu",
                     "options": ["baidu", "google", "bing", "bilibili", "zhihu", "custom"],
                     "option_labels": ["百度", "Google", "必应 Bing", "哔哩哔哩", "知乎", "自定义URL"]},
        "custom_url": {"type": "text", "label": "自定义搜索URL(含{keyword})", "default": "",
                       "placeholder": "如 https://www.taobao.com/search?q={keyword}"},
    },
    "download_file": {
        "url":      {"type": "text", "label": "下载链接(支持{{变量}})", "default": "",
                     "placeholder": "文件下载 URL"},
        "save_dir": {"type": "folder_picker", "label": "保存目录(空=系统下载目录)", "default": ""},
        "filename": {"type": "select", "label": "文件名方式", "default": "auto",
                     "options": ["auto", "custom", "timestamp", "url_name"],
                     "option_labels": ["自动(从URL提取)", "自定义文件名", "时间戳命名", "URL末尾段"]},
        "custom_name": {"type": "text", "label": "自定义文件名(支持{{变量}})", "default": "",
                        "placeholder": "如 report_{{date}}.pdf"},
        "overwrite": {"type": "bool", "label": "覆盖已存在的文件", "default": True},
        "save_path_to": {"type": "text", "label": "下载路径存入变量(可选)", "default": "downloaded_file"},
    },
    "extract_archive": {
        "archive":  {"type": "file_picker", "label": "压缩包路径(支持通配符{{变量}})", "default": "",
                     "placeholder": "如 C:/downloads/*.zip 或 {{archive_file}}"},
        "dest_dir": {"type": "folder_picker", "label": "解压到目录(空=同目录)", "default": ""},
        "create_folder": {"type": "select", "label": "是否创建独立文件夹", "default": "auto",
                          "options": ["auto", "always", "never"],
                          "option_labels": ["自动(多文件时创建)", "始终创建", "不创建"]},
        "folder_name": {"type": "select", "label": "文件夹命名方式", "default": "archive_name",
                        "options": ["archive_name", "custom", "timestamp"],
                        "option_labels": ["压缩包同名", "自定义名称", "时间戳"]},
        "custom_folder": {"type": "text", "label": "自定义文件夹名(支持{{变量}})", "default": ""},
        "overwrite": {"type": "bool", "label": "覆盖已有文件", "default": False},
        "save_dest_to": {"type": "text", "label": "解压目录存入变量(可选)", "default": "extracted_dir"},
    },
    # ── AI 大模型 ──
    "ai_chat": {
        "prompt":         {"type": "text_multiline", "label": "用户消息(支持{{变量}})", "default": "",
                           "placeholder": "输入发送给 AI 的消息内容，可用 {{变量}} 引用变量"},
        "system_prompt":  {"type": "text_multiline", "label": "系统提示词(可选，留空=使用设置里的默认值)", "default": "",
                           "placeholder": "留空则使用【设置→AI】中配置的默认系统提示词"},
        "model":          {"type": "text", "label": "模型名称(留空=使用设置默认)", "default": "",
                           "placeholder": "如 gpt-4o / deepseek-chat，留空使用设置中的默认模型"},
        "save_to":        {"type": "text", "label": "回复存入变量", "default": "ai_reply"},
        "append_history": {"type": "bool", "label": "追加到对话历史(连续对话)", "default": False},
        "history_var":    {"type": "text", "label": "对话历史变量名", "default": "ai_history"},
        "timeout":        {"type": "number_or_var", "label": "超时秒数", "default": 30},
    },
    "ai_generate": {
        "prompt":       {"type": "text_multiline", "label": "生成提示词(支持{{变量}})", "default": "",
                         "placeholder": "描述要生成的内容，例如：根据 {{data}} 生成一份摘要"},
        "system_prompt":{"type": "text_multiline", "label": "系统提示词(可选)", "default": ""},
        "model":        {"type": "text", "label": "模型名称(留空=使用设置默认)", "default": ""},
        "save_to":      {"type": "text", "label": "生成结果存入变量", "default": "ai_result"},
        "temperature":  {"type": "number_or_var", "label": "创造性(0.0-2.0，留空=使用设置默认)", "default": ""},
        "timeout":      {"type": "number_or_var", "label": "超时秒数", "default": 60},
    },
    "browser_auto": {
        "mode":         {"type": "select", "label": "运行模式", "default": "ai_run",
                         "options": ["ai_run", "ai_generate"],
                         "option_labels": ["AI 运行模式（每次由 AI 思考执行）", "AI 生成步骤（生成操作步骤列表）"]},
        "task":         {"type": "text_multiline", "label": "任务描述(自然语言，支持{{变量}})", "default": "",
                         "placeholder": "用自然语言描述要在浏览器中完成的任务，例如：\n打开 https://github.com 并搜索 browser-use，返回第一个结果的标题"},
        "llm_provider": {"type": "select", "label": "LLM 驱动", "default": "settings",
                         "options": ["settings", "openai", "anthropic", "google", "azure_openai", "deepseek"],
                         "option_labels": ["跟随设置（推荐）", "OpenAI", "Anthropic Claude", "Google Gemini", "Azure OpenAI", "DeepSeek"]},
        "model":        {"type": "text", "label": "模型名称(留空=跟随设置)", "default": "",
                         "placeholder": "留空则使用 AI 设置中配置的模型"},
        "start_url":    {"type": "text", "label": "初始URL(可选)", "default": "",
                         "placeholder": "任务开始前自动打开此页面，留空=从当前页继续"},
        "headless":     {"type": "bool", "label": "无头模式(后台运行，不显示浏览器窗口)", "default": False},
        "close_after":  {"type": "bool", "label": "任务完成后关闭浏览器", "default": True},
        "max_steps":    {"type": "number_or_var", "label": "最大操作步数", "default": 20},
        "timeout":      {"type": "number_or_var", "label": "任务超时秒数(0=不限制)", "default": 120},
        "save_result":  {"type": "text", "label": "任务结果存入变量", "default": "browser_result",
                         "placeholder": "变量名，用于保存 AI 浏览器任务执行结果"},
        "save_history": {"type": "text", "label": "操作历史存入变量(可选)", "default": "",
                         "placeholder": "变量名，保存 JSON 格式的完整操作步骤记录"},
    },
    # 浏览器基础操作（基于 playwright，共享浏览器实例）
    "browser_open_url": {
        "url":       {"type": "text", "label": "网址 URL（支持{{变量}}）", "default": "",
                      "placeholder": "https://www.example.com"},
        "wait_load": {"type": "bool", "label": "等待页面加载完成", "default": True},
        "timeout":   {"type": "number_or_var", "label": "超时秒数", "default": 15},
    },
    "browser_click": {
        "selector": {"type": "text", "label": "CSS选择器（支持{{变量}}）", "default": "",
                     "placeholder": "#submit-btn 或 .login-button"},
        "by_text":  {"type": "text", "label": "按文本内容点击（留空则用选择器）", "default": "",
                     "placeholder": "登录  ←填写按钮/链接的文字"},
        "timeout":  {"type": "number_or_var", "label": "超时秒数", "default": 10},
    },
    "browser_type": {
        "selector":    {"type": "text", "label": "CSS选择器（支持{{变量}}）", "default": "",
                        "placeholder": "input[name='username'] 或 #search-input"},
        "text":        {"type": "text", "label": "要输入的文字（支持{{变量}}）", "default": ""},
        "clear_first": {"type": "bool", "label": "输入前清空原有内容", "default": True},
        "timeout":     {"type": "number_or_var", "label": "超时秒数", "default": 10},
    },
    "browser_get_text": {
        "selector": {"type": "text", "label": "CSS选择器（支持{{变量}}）", "default": "",
                     "placeholder": "#result 或 .article-body"},
        "save_to":  {"type": "text", "label": "文本内容存入变量", "default": "browser_text"},
        "timeout":  {"type": "number_or_var", "label": "超时秒数", "default": 10},
    },
    "browser_screenshot": {
        "save_path": {"type": "text", "label": "截图保存路径（支持{{变量}}）", "default": "screenshot.png",
                      "placeholder": "C:/Users/xxx/screenshot.png"},
        "full_page": {"type": "bool", "label": "截取完整页面（滚动截图）", "default": False},
        "save_to":   {"type": "text", "label": "路径存入变量（可选）", "default": ""},
    },
    "browser_wait_element": {
        "selector": {"type": "text", "label": "CSS选择器（支持{{变量}}）", "default": "",
                     "placeholder": "#loading-spinner 或 .content-loaded"},
        "state":    {"type": "select", "label": "等待状态", "default": "visible",
                     "options": ["visible", "hidden", "attached", "detached"],
                     "option_labels": ["可见", "隐藏", "出现在DOM", "从DOM移除"]},
        "timeout":  {"type": "number_or_var", "label": "超时秒数", "default": 15},
    },
    # ── 屏幕识别（基于 pyautogui + opencv）──
    "screen_find_image": {
        "image_path":  {"type": "file_picker", "label": "目标图片路径", "default": "",
                        "placeholder": "截取目标按钮/图标的截图，支持 PNG/JPG"},
        "confidence":  {"type": "number_or_var", "label": "匹配精度(0.1-1.0)", "default": 0.8,
                        "placeholder": "0.8 = 80% 相似度，越高越严格"},
        "region":      {"type": "text", "label": "搜索区域(x,y,w,h，留空=全屏)", "default": "",
                        "placeholder": "如 0,0,1920,1080 或留空搜索全屏"},
        "save_x_to":   {"type": "text", "label": "找到的X坐标存入变量", "default": "found_x"},
        "save_y_to":   {"type": "text", "label": "找到的Y坐标存入变量", "default": "found_y"},
        "on_not_found": {"type": "select", "label": "未找到时", "default": "continue",
                         "options": ["continue", "stop_task"],
                         "option_labels": ["继续执行(变量置空)", "停止任务"]},
    },
    "screen_click_image": {
        "image_path":  {"type": "file_picker", "label": "目标图片路径", "default": "",
                        "placeholder": "截取目标按钮/图标的截图，支持 PNG/JPG"},
        "confidence":  {"type": "number_or_var", "label": "匹配精度(0.1-1.0)", "default": 0.8},
        "button":      {"type": "select", "label": "鼠标键", "default": "left",
                        "options": ["left", "right", "middle"],
                        "option_labels": ["左键", "右键", "中键"]},
        "clicks":      {"type": "number_or_var", "label": "点击次数", "default": 1},
        "region":      {"type": "text", "label": "搜索区域(x,y,w,h，留空=全屏)", "default": ""},
        "offset_x":    {"type": "number_or_var", "label": "点击X偏移(像素)", "default": 0},
        "offset_y":    {"type": "number_or_var", "label": "点击Y偏移(像素)", "default": 0},
        "on_not_found": {"type": "select", "label": "未找到时", "default": "continue",
                         "options": ["continue", "stop_task"],
                         "option_labels": ["继续执行", "停止任务"]},
    },
    "screen_wait_image": {
        "image_path":  {"type": "file_picker", "label": "目标图片路径", "default": ""},
        "confidence":  {"type": "number_or_var", "label": "匹配精度(0.1-1.0)", "default": 0.8},
        "timeout":     {"type": "number_or_var", "label": "超时秒数(0=无限等待)", "default": 30},
        "interval":    {"type": "number_or_var", "label": "检测间隔(秒)", "default": 0.5},
        "region":      {"type": "text", "label": "搜索区域(x,y,w,h，留空=全屏)", "default": ""},
        "save_x_to":   {"type": "text", "label": "找到的X坐标存入变量(可选)", "default": ""},
        "save_y_to":   {"type": "text", "label": "找到的Y坐标存入变量(可选)", "default": ""},
        "on_timeout":  {"type": "select", "label": "超时后", "default": "continue",
                        "options": ["continue", "stop_task"],
                        "option_labels": ["继续执行", "停止任务"]},
    },
    "screen_screenshot_region": {
        "region":      {"type": "text", "label": "截图区域(x,y,w,h)", "default": "",
                        "placeholder": "如 100,100,800,600；留空=全屏截图"},
        "save_path":   {"type": "text", "label": "保存路径(支持{{变量}})", "default": "region_shot.png",
                        "placeholder": "C:/shots/region.png 或使用 {{变量}}"},
        "save_to":     {"type": "text", "label": "路径存入变量(可选)", "default": ""},
    },
    # ── 窗口控件操作（基于 pywinauto）──
    "win_find_window": {
        "title":       {"type": "text", "label": "窗口标题(支持*通配符，支持{{变量}})", "default": "",
                        "placeholder": "如 *记事本* 或 Microsoft Word"},
        "class_name":  {"type": "text", "label": "窗口类名(可选)", "default": "",
                        "placeholder": "如 Notepad 或 #32770，留空不限制"},
        "process":     {"type": "process_picker", "label": "进程名(可选)", "default": "",
                        "placeholder": "如 notepad.exe，留空不限制"},
        "timeout":     {"type": "number_or_var", "label": "等待超时秒数(0=不等待)", "default": 5},
        "save_to":     {"type": "text", "label": "窗口句柄存入变量(可选)", "default": "win_handle",
                        "placeholder": "用于后续控件操作的句柄变量名"},
        "on_not_found": {"type": "select", "label": "未找到时", "default": "continue",
                         "options": ["continue", "stop_task"],
                         "option_labels": ["继续执行(变量置空)", "停止任务"]},
    },
    "win_click_control": {
        "window_title":  {"type": "text", "label": "窗口标题(支持*通配符)", "default": "",
                          "placeholder": "目标窗口的标题，支持 * 通配符"},
        "control_title": {"type": "text", "label": "控件标题/文本(支持{{变量}})", "default": "",
                          "placeholder": "按钮文字，如「确定」「OK」「保存」"},
        "control_type":  {"type": "select", "label": "控件类型", "default": "Button",
                          "options": ["Button", "Edit", "ComboBox", "ListBox", "CheckBox",
                                      "RadioButton", "MenuItem", "Static", "any"],
                          "option_labels": ["按钮", "文本框", "下拉框", "列表框", "复选框",
                                            "单选按钮", "菜单项", "静态文本", "任意类型"]},
        "double_click":  {"type": "bool", "label": "双击", "default": False},
        "timeout":       {"type": "number_or_var", "label": "超时秒数", "default": 5},
    },
    "win_input_control": {
        "window_title":  {"type": "text", "label": "窗口标题(支持*通配符)", "default": ""},
        "control_title": {"type": "text", "label": "控件标题/占位符(可选，支持{{变量}})", "default": "",
                          "placeholder": "输入框的标题或辅助名称，留空则选第一个可编辑框"},
        "text":          {"type": "text_multiline", "label": "输入内容(支持{{变量}})", "default": ""},
        "clear_first":   {"type": "bool", "label": "输入前清空原内容", "default": True},
        "timeout":       {"type": "number_or_var", "label": "超时秒数", "default": 5},
    },
    "win_get_control_text": {
        "window_title":  {"type": "text", "label": "窗口标题(支持*通配符)", "default": ""},
        "control_title": {"type": "text", "label": "控件标题(可选)", "default": "",
                          "placeholder": "留空则获取整个窗口的文本内容"},
        "control_type":  {"type": "select", "label": "控件类型", "default": "any",
                          "options": ["any", "Edit", "Static", "ListBox", "ComboBox"],
                          "option_labels": ["任意类型", "文本框", "静态文本", "列表框", "下拉框"]},
        "save_to":       {"type": "text", "label": "文本内容存入变量", "default": "ctrl_text"},
        "timeout":       {"type": "number_or_var", "label": "超时秒数", "default": 5},
    },
    "win_wait_window": {
        "title":         {"type": "text", "label": "窗口标题(支持*通配符，支持{{变量}})", "default": ""},
        "class_name":    {"type": "text", "label": "窗口类名(可选)", "default": ""},
        "timeout":       {"type": "number_or_var", "label": "超时秒数(0=无限等待)", "default": 30},
        "on_timeout":    {"type": "select", "label": "超时后", "default": "continue",
                          "options": ["continue", "stop_task"],
                          "option_labels": ["继续执行", "停止任务"]},
    },
    "win_close_window": {
        "title":         {"type": "text", "label": "窗口标题(支持*通配符，支持{{变量}})", "default": ""},
        "class_name":    {"type": "text", "label": "窗口类名(可选)", "default": ""},
        "force":         {"type": "bool", "label": "强制关闭(发送WM_DESTROY)", "default": False},
        "timeout":       {"type": "number_or_var", "label": "查找超时秒数", "default": 3},
    },
}


# ─────────────────────────── 触发器类型 ───────────────────────────

TRIGGER_TYPES = {
    "manual":         {"label": "手动运行",       "icon": "▶️",  "color": "#607D8B",  "category": "基础"},
    "schedule":       {"label": "定时执行",       "icon": "⏰",  "color": "#5B8CFF",  "category": "基础"},
    "hotkey":         {"label": "键盘快捷键",     "icon": "⌨️",  "color": "#A080FF",  "category": "基础"},
    "mouse_click":    {"label": "鼠标点击",       "icon": "🖱️",  "color": "#E91E63",  "category": "基础"},
    "startup":        {"label": "程序启动时",     "icon": "🚀",  "color": "#795548",  "category": "基础"},
    "system_boot":    {"label": "开机完成",       "icon": "💻",  "color": "#4CAF50",  "category": "基础"},
    "process_start":  {"label": "进程启动",       "icon": "✅",  "color": "#4CAF50",  "category": "应用&进程"},
    "process_stop":   {"label": "进程结束",       "icon": "🔴",  "color": "#F44336",  "category": "应用&进程"},
    "window_appear":  {"label": "窗口出现",       "icon": "🪟",  "color": "#4CAF50",  "category": "应用&进程"},
    "window_close":   {"label": "窗口关闭",       "icon": "❌",  "color": "#F44336",  "category": "应用&进程"},
    "window_focus":   {"label": "窗口获得焦点",   "icon": "🎯",  "color": "#E91E63",  "category": "应用&进程"},
    "window_blur":    {"label": "窗口失去焦点",   "icon": "🔳",  "color": "#9E9E9E",  "category": "应用&进程"},
    "file_changed":   {"label": "文件变化",       "icon": "📄",  "color": "#FF9800",  "category": "文件&系统"},
    "file_created":   {"label": "文件创建",       "icon": "📁",  "color": "#4CAF50",  "category": "文件&系统"},
    "file_deleted":   {"label": "文件删除",       "icon": "🗑️",  "color": "#F44336",  "category": "文件&系统"},
    "cpu_high":       {"label": "CPU占用率超限",  "icon": "🔥",  "color": "#FF5722",  "category": "系统资源"},
    "memory_high":    {"label": "内存占用率超限",  "icon": "🧠",  "color": "#9C27B0",  "category": "系统资源"},
    "disk_full":      {"label": "磁盘空间不足",   "icon": "💾",  "color": "#FF9800",  "category": "系统资源"},
    "battery_change": {"label": "电池电量变化",   "icon": "🔋",  "color": "#4CAF50",  "category": "系统资源"},
    "idle_detect":    {"label": "系统空闲检测",   "icon": "💤",  "color": "#607D8B",  "category": "系统资源"},
    "screen_change":  {"label": "屏幕分辨率变化", "icon": "🖥️",  "color": "#00BCD4",  "category": "系统资源"},
    "network_change":  {"label": "网络连接/断网",    "icon": "🌐",  "color": "#3F51B5", "category": "网络"},
    "wifi_ssid":      {"label": "连接指定WiFi",   "icon": "📶",  "color": "#2196F3",  "category": "网络"},
    "usb_connected":  {"label": "USB设备连接",    "icon": "🔌",  "color": "#00BCD4",  "category": "网络"},
    "ping_latency":   {"label": "Ping延迟触发",   "icon": "📡",  "color": "#3F51B5",  "category": "网络"},
    "variable_change":{"label": "变量变化",       "icon": "📊",  "color": "#FF5722",  "category": "数据"},
    "clipboard_copy":  {"label": "检测到复制操作", "icon": "📋",  "color": "#00BCD4", "category": "数据"},
    "email_received": {"label": "收到邮件",       "icon": "📧",  "color": "#9C27B0",  "category": "数据"},
    "notification":   {"label": "收到通知",       "icon": "🔔",  "color": "#FF9800",  "category": "数据"},
    "time_range":     {"label": "时间段内触发",   "icon": "⏱️",  "color": "#5B8CFF",  "category": "基础"},
}

TRIGGER_PARAMS: Dict[str, Dict[str, Any]] = {
    "manual": {},
    "startup": {},
    "system_boot": {
        "delay_sec": {"type": "number_or_var", "label": "延迟秒数(开机后等待多久再触发)", "default": 30,
                      "placeholder": "系统启动完成后延迟N秒触发，建议30秒以上"},
        "check_interval": {"type": "number_or_var", "label": "检测间隔(秒)", "default": 10},
    },
    "hotkey": {
        "hotkey": {"type": "hotkey_input", "label": "快捷键", "default": "ctrl+alt+r",
                   "placeholder": "如 ctrl+alt+r 或 F12"},
    },
    "mouse_click": {
        "button":   {"type": "select", "label": "鼠标按键", "default": "middle",
                     "options": ["left", "right", "middle", "x1", "x2"],
                     "option_labels": ["左键", "右键", "中键(滚轮)", "侧键X1", "侧键X2"]},
        "modifier": {"type": "text", "label": "同时按住(可选)", "default": "",
                     "placeholder": "如 ctrl+shift，留空=无修饰键"},
    },
    "schedule": {
        "schedule_type": {"type": "select", "label": "类型", "default": "interval",
                          "options": ["interval", "daily", "weekly", "once"],
                          "option_labels": ["按间隔重复", "每天定时", "每周定时", "仅执行一次"]},
        "interval_sec":  {"type": "number_or_var", "label": "间隔秒数", "default": 60},
        "time_of_day":   {"type": "time", "label": "每天时间", "default": "08:00"},
        "weekday":       {"type": "select", "label": "星期几", "default": "monday",
                          "options": ["monday","tuesday","wednesday","thursday",
                                      "friday","saturday","sunday"],
                          "option_labels": ["周一", "周二", "周三", "周四",
                                            "周五", "周六", "周日"]},
        "once_datetime": {"type": "datetime", "label": "一次性时间", "default": ""},
    },
    "process_start":  {"name": {"type": "process_picker", "label": "进程名(如 notepad.exe)", "default": ""}},
    "process_stop":   {"name": {"type": "process_picker", "label": "进程名", "default": ""}},
    "window_appear":  {"title": {"type": "window_picker", "label": "窗口标题(支持*通配符)", "default": ""}},
    "window_close":   {"title": {"type": "window_picker", "label": "窗口标题(支持*通配符)", "default": ""}},
    "file_changed":   {
        "path":    {"type": "file_picker", "label": "监测路径", "default": ""},
        "pattern": {"type": "text", "label": "文件匹配(如 *.txt)", "default": "*"},
    },
    "file_created":   {"path": {"type": "file_picker", "label": "监测目录", "default": ""}},
    "file_deleted":   {"path": {"type": "file_picker", "label": "监测目录", "default": ""}},
    "variable_change":{"name": {"type": "text", "label": "变量名", "default": ""}},
    "clipboard_copy": {
        "save_to": {"type": "text", "label": "复制内容存入变量(可选)", "default": "clipboard_text",
                    "placeholder": "每次复制操作触发，内容存入此变量"},
    },
    "email_received": {
        "sender":  {"type": "text", "label": "发件人(可留空)", "default": ""},
        "subject": {"type": "text", "label": "主题包含(可留空)", "default": ""},
    },
    "notification":   {"text": {"type": "text", "label": "通知内容包含", "default": ""}},
    "usb_connected":  {"device": {"type": "text", "label": "设备名称(可留空=任意)", "default": ""}},
    "network_change":  {"event": {"type": "select", "label": "事件", "default": "connected",
                                  "options": ["connected", "disconnected", "any"],
                                  "option_labels": ["网络连接时", "网络断开时", "任意变化"]}},
    # 新增触发器参数
    "cpu_high": {
        "threshold": {"type": "number_or_var", "label": "CPU阈值(%)", "default": 90},
        "duration":  {"type": "number_or_var", "label": "持续秒数", "default": 5},
    },
    "memory_high": {
        "threshold": {"type": "number_or_var", "label": "内存阈值(%)", "default": 90},
    },
    "disk_full": {
        "drive":     {"type": "text", "label": "磁盘(如 C:，留空=所有)", "default": ""},
        "threshold": {"type": "number_or_var", "label": "剩余空间警戒(GB)", "default": 5},
    },
    "battery_change": {
        "event":     {"type": "select", "label": "事件类型", "default": "low",
                      "options": ["low", "critical", "charging", "discharging", "full"],
                      "option_labels": ["低电量", "电量极低", "开始充电", "拔掉充电器", "充电完成"]},
        "threshold": {"type": "number_or_var", "label": "低电量阈值(%)", "default": 20},
    },
    "idle_detect": {
        "idle_sec":  {"type": "number_or_var", "label": "空闲时长(秒)", "default": 300},
    },
    "window_focus": {
        "title": {"type": "window_picker", "label": "窗口标题(支持*通配符)", "default": "",
                  "placeholder": "留空=任意窗口获得焦点"},
    },
    "time_range": {
        "start_time": {"type": "time", "label": "开始时间", "default": "09:00"},
        "end_time":   {"type": "time", "label": "结束时间", "default": "18:00"},
        "weekdays":   {"type": "text", "label": "星期(0=周一,逗号分隔,留空=每天)", "default": ""},
        "interval_sec": {"type": "number_or_var", "label": "时间段内触发间隔(秒)", "default": 3600},
    },
    "screen_change": {},
    "wifi_ssid": {
        "ssid": {"type": "text", "label": "WiFi名称(SSID)", "default": ""},
        "event": {"type": "select", "label": "事件", "default": "connected",
                  "options": ["connected", "disconnected"],
                  "option_labels": ["连接到此WiFi时", "断开此WiFi时"]},
    },
    "window_blur": {
        "title": {"type": "window_picker", "label": "窗口标题(支持*通配符，留空=任意)", "default": "",
                  "placeholder": "留空=任何窗口失去焦点时触发"},
    },
    # ── Ping 延迟触发器 ──
    "ping_latency": {
        "host":         {"type": "text", "label": "目标主机(IP/域名，支持{{变量}})", "default": "8.8.8.8",
                         "placeholder": "如 8.8.8.8 / www.baidu.com / {{host_var}}"},
        "threshold_ms": {"type": "number_or_var", "label": "延迟阈值(ms)", "default": 200},
        "direction":    {"type": "select", "label": "触发方向", "default": "above",
                         "options": ["above", "below", "timeout"],
                         "option_labels": ["延迟超过阈值时触发", "延迟低于阈值时触发", "超时/不可达时触发"]},
        "interval_sec": {"type": "number_or_var", "label": "检测间隔(秒)", "default": 30},
    },
}


# ─────────────────────────── 数据类 ───────────────────────────

@dataclass
class Constraint:
    """
    约束条件：只有当条件为真时，功能块/触发器才会运行。
    condition_type: 与 Block condition 相同类型
    target: 目标（进程名/窗口标题/文件路径/变量名）
    value: 比较值（仅变量条件）
    negate: 取反
    """
    condition_type: str = "always_true"
    target: str = ""
    value: str = ""
    negate: bool = False

    def to_dict(self) -> dict:
        return {
            "condition_type": self.condition_type,
            "target": self.target,
            "value": self.value,
            "negate": self.negate,
        }

    @staticmethod
    def from_dict(d: dict) -> "Constraint":
        return Constraint(
            condition_type=d.get("condition_type", "always_true"),
            target=d.get("target", ""),
            value=d.get("value", ""),
            negate=d.get("negate", False),
        )


@dataclass
class Block:
    """一个功能块实例"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    block_type: str = "wait"
    params: Dict[str, Any] = field(default_factory=dict)
    comment: str = ""
    enabled: bool = True
    constraints: List["Constraint"] = field(default_factory=list)  # 约束条件
    # 嵌套子块（用于 condition / loop）
    children_true: List["Block"] = field(default_factory=list)   # 条件为真时执行
    children_false: List["Block"] = field(default_factory=list)  # 条件为假时执行
    children_loop: List["Block"] = field(default_factory=list)   # 循环体

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "block_type": self.block_type,
            "params": self.params,
            "comment": self.comment,
            "enabled": self.enabled,
            "constraints": [c.to_dict() for c in self.constraints],
            "children_true": [b.to_dict() for b in self.children_true],
            "children_false": [b.to_dict() for b in self.children_false],
            "children_loop": [b.to_dict() for b in self.children_loop],
        }

    @staticmethod
    def from_dict(d: dict) -> "Block":
        b = Block(
            id=d.get("id", str(uuid.uuid4())[:8]),
            block_type=d.get("block_type", "wait"),
            params=d.get("params", {}),
            comment=d.get("comment", ""),
            enabled=d.get("enabled", True),
        )
        b.constraints    = [Constraint.from_dict(c) for c in d.get("constraints", [])]
        b.children_true  = [Block.from_dict(x) for x in d.get("children_true", [])]
        b.children_false = [Block.from_dict(x) for x in d.get("children_false", [])]
        b.children_loop  = [Block.from_dict(x) for x in d.get("children_loop", [])]
        return b


@dataclass
class Trigger:
    """触发器实例"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    trigger_type: str = "manual"
    params: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    comment: str = ""
    constraints: List["Constraint"] = field(default_factory=list)  # 约束条件

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "trigger_type": self.trigger_type,
            "params": self.params,
            "enabled": self.enabled,
            "comment": self.comment,
            "constraints": [c.to_dict() for c in self.constraints],
        }

    @staticmethod
    def from_dict(d: dict) -> "Trigger":
        t = Trigger(
            id=d.get("id", str(uuid.uuid4())[:8]),
            trigger_type=d.get("trigger_type", "manual"),
            params=d.get("params", {}),
            enabled=d.get("enabled", True),
            comment=d.get("comment", ""),
        )
        t.constraints = [Constraint.from_dict(c) for c in d.get("constraints", [])]
        return t


@dataclass
class Task:
    """一个完整的自动化任务"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = "新任务"
    description: str = ""
    enabled: bool = True
    group_id: str = ""          # 所属分组ID，空=""未分组
    blocks: List[Block] = field(default_factory=list)
    triggers: List[Trigger] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)  # 任务级变量初始值

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "group_id": self.group_id,
            "blocks": [b.to_dict() for b in self.blocks],
            "triggers": [t.to_dict() for t in self.triggers],
            "variables": self.variables,
        }

    @staticmethod
    def from_dict(d: dict) -> "Task":
        raw_vars = d.get("variables", {})
        t = Task(
            id=d.get("id", str(uuid.uuid4())[:8]),
            name=d.get("name", "新任务"),
            description=d.get("description", ""),
            enabled=d.get("enabled", True),
            group_id=d.get("group_id", ""),
            variables=dict(raw_vars) if isinstance(raw_vars, dict) else {},
        )
        t.blocks   = [Block.from_dict(b) for b in d.get("blocks", [])]
        t.triggers = [Trigger.from_dict(r) for r in d.get("triggers", [])]
        return t


@dataclass
class AppConfig:
    """全局应用配置"""
    # 开机自启
    auto_start_enabled: bool = False
    auto_start_task_id: str = ""
    # 项目
    reopen_last_project: bool = True   # 启动时打开上次项目
    last_project_path: str = ""        # 上次打开的项目路径
    # 自动保存
    auto_save_enabled: bool = True
    auto_save_interval: int = 60       # 自动保存间隔(秒)
    # 撤回
    max_undo_steps: int = 50           # 最大撤回步数
    # 邮箱(IMAP接收)
    imap_server: str = ""
    imap_port: int = 993
    imap_user: str = ""
    imap_password: str = ""
    imap_ssl: bool = True
    # 邮箱(SMTP发送)
    smtp_server: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_ssl: bool = True
    # 截图默认路径（空=系统图片库）
    screenshot_default_dir: str = ""
    # 坐标选点快捷键（选点浮窗确认键，默认 F9）
    coord_pick_hotkey: str = "F9"
    # 键鼠宏录制停止热键（默认 F10）
    macro_stop_hotkey: str = "F10"
    # 强制终止所有运行中任务的全局热键（默认 ctrl+alt+s）
    force_stop_hotkey: str = "ctrl+alt+s"
    # 界面
    theme: str = "dark"               # dark/light/system/preset_*
    language: str = "zh_CN"          # zh_CN=简体中文 / zh_TW=繁体中文 / en_US=英语
    minimize_to_tray: bool = True
    show_run_log: bool = True
    minimize_on_run: bool = False      # 任务运行时最小化主窗口
    # 日志
    log_path: str = ""      # 空=自动使用 %LOCALAPPDATA%\XinyuCraft\AutoFlow\Log\autoflow.log
    max_log_lines: int = 2000
    # AI 大模型
    ai_provider: str = "openai"        # openai/deepseek/kimi/qwen/zhipu/baidu/claude/gemini/ollama/azure/custom
    ai_api_key: str = ""
    ai_base_url: str = ""              # 空=使用官方默认URL，填自定义则覆盖
    ai_model: str = "gpt-4o-mini"     # 模型名称
    ai_temperature: float = 0.7
    ai_max_tokens: int = 2048
    ai_system_prompt: str = ""         # 默认系统提示词（可被功能块覆盖）
    # 远程公告：已读/永久忽略的公告 ID 列表
    read_announcement_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @staticmethod
    def from_dict(d: dict) -> "AppConfig":
        cfg = AppConfig()
        for k, v in d.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        return cfg


@dataclass
class Project:
    """项目文件（包含所有任务）"""
    version: str = "1.0"
    tasks: List[Task] = field(default_factory=list)
    config: AppConfig = field(default_factory=AppConfig)
    # 任务分组列表: [{"id": str, "name": str}]
    task_groups: List[Dict[str, Any]] = field(default_factory=list)
    # 全局变量（所有任务共享，可在任务间传递数据）
    global_variables: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "tasks": [t.to_dict() for t in self.tasks],
            "config": self.config.to_dict(),
            "task_groups": self.task_groups,
            "global_variables": self.global_variables,
        }

    def save(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @staticmethod
    def load(path: str) -> "Project":
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        p = Project(version=d.get("version", "1.0"))
        p.tasks  = [Task.from_dict(t) for t in d.get("tasks", [])]
        p.config = AppConfig.from_dict(d.get("config", {}))
        p.task_groups = list(d.get("task_groups", [])) or []
        raw_gv = d.get("global_variables", {})
        p.global_variables = dict(raw_gv) if isinstance(raw_gv, dict) else {}
        return p

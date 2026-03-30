"""
触发器监控引擎
负责监听所有触发器并在触发时通知
"""
import fnmatch
import imaplib
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

import psutil

from .models import Task, Trigger, AppConfig

logger = logging.getLogger("autoflow.trigger")


class TriggerMonitor:
    """
    监控所有任务的触发器，触发时调用 on_trigger(task_id)
    """

    # 类级别哨兵：用于区分"从未记录"和"记录为 False"
    _SENTINEL = object()

    def __init__(self, config: AppConfig, on_trigger: Callable[[str], None]):
        self.config = config
        self.on_trigger = on_trigger
        self._tasks: Dict[str, Task] = {}
        self._stop_event = threading.Event()
        self._threads: List[threading.Thread] = []

        # 状态缓存
        self._process_cache: set = set()
        self._window_cache: set = set()
        self._file_mtimes: Dict[str, float] = {}
        self._imap_last_uid: Optional[int] = None

        # 热键注册状态
        self._hotkey_ids: Dict[str, int] = {}   # trigger_id -> hotkey_id
        self._hotkey_id_counter = 0xBEEF

    def set_tasks(self, tasks: List[Task]):
        self._tasks = {t.id: t for t in tasks}

    def start(self):
        self._stop_event.clear()
        self._threads = []

        # 所有触发器类型在一个统一轮询线程中处理，以减少线程数
        t = threading.Thread(target=self._poll_loop, daemon=True, name="trigger-poll")
        t.start()
        self._threads.append(t)

        # 邮件触发器单独线程（IMAP IDLE 慢）
        t2 = threading.Thread(target=self._email_loop, daemon=True, name="trigger-email")
        t2.start()
        self._threads.append(t2)

        # 热键监听（Win32 RegisterHotKey 需要消息循环）
        t3 = threading.Thread(target=self._hotkey_loop, daemon=True, name="trigger-hotkey")
        t3.start()
        self._threads.append(t3)

        # 剪贴板监控单独线程（需要高频轮询，默认500ms，不影响主轮询1s节奏）
        t4 = threading.Thread(target=self._clipboard_loop, daemon=True, name="trigger-clipboard")
        t4.start()
        self._threads.append(t4)

        logger.info("触发器监控已启动")

    def stop(self):
        self._stop_event.set()
        self._unregister_all_hotkeys()
        logger.info("触发器监控已停止")

    def _fire(self, task_id: str, reason: str, trigger: "Trigger" = None):
        # 如果传入了触发器，检查其约束条件
        if trigger is not None and getattr(trigger, "constraints", []):
            if not self._check_trigger_constraints(trigger.constraints):
                logger.debug(f"触发器约束条件不满足，跳过 [{task_id}]: {reason}")
                return
        logger.info(f"触发任务 [{task_id}]: {reason}")
        self.on_trigger(task_id)

    def get_trigger_vars(self, task_id: str) -> dict:
        """
        取出并清除本次触发为 task_id 暂存的变量（如剪贴板内容）。
        每次调用后自动清除，保证下次触发前数据不残留。
        """
        if not hasattr(self, "_clipboard_match_vars"):
            return {}
        result = {}
        prefix = f"{task_id}:"
        keys_to_del = [k for k in self._clipboard_match_vars if k.startswith(prefix)]
        for k in keys_to_del:
            var_name = k[len(prefix):]
            result[var_name] = self._clipboard_match_vars.pop(k)
        return result

    def _check_trigger_constraints(self, constraints) -> bool:
        """评估触发器约束条件（AND 逻辑，所有约束都必须为真）"""
        for c in constraints:
            result = self._eval_one_constraint(c)
            if c.negate:
                result = not result
            if not result:
                return False
        return True

    def _eval_one_constraint(self, c) -> bool:
        """评估单个约束条件（不依赖 runner，独立实现）"""
        ct     = c.condition_type
        target = c.target
        value  = c.value
        try:
            if ct == "always_true":
                return True
            elif ct == "process_exists":
                procs = self._get_process_set()
                return target.lower() in procs
            elif ct == "window_exists":
                wins = self._get_window_set()
                return any(fnmatch.fnmatch(w, target.lower()) for w in wins)
            elif ct == "file_exists":
                import os as _os
                return _os.path.exists(target)
            elif ct in ("variable_equals", "variable_gt", "variable_lt", "variable_contains"):
                # trigger_monitor 没有变量系统，此条件始终返回 True（由 runner 处理）
                return True
            elif ct in ("network_connected", "internet_connected"):
                stats = psutil.net_if_stats()
                return any(s.isup for s in stats.values())
            elif ct == "clipboard_contains":
                text = self._get_clipboard_text() or ""
                return target in text
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
                    threshold = float(target) if target else 80.0
                    return psutil.cpu_percent(interval=0.5) > threshold
                except Exception:
                    return False
            elif ct == "memory_above":
                try:
                    threshold = float(target) if target else 90.0
                    return psutil.virtual_memory().percent > threshold
                except Exception:
                    return False
            elif ct == "battery_below":
                try:
                    bat = psutil.sensors_battery()
                    if bat is None: return False
                    threshold = float(target) if target else 20.0
                    return bat.percent < threshold
                except Exception:
                    return False
            elif ct == "battery_charging":
                try:
                    bat = psutil.sensors_battery()
                    return bat is not None and bat.power_plugged
                except Exception:
                    return False
            elif ct == "time_between":
                try:
                    from datetime import datetime as _dt, time as _t
                    now = _dt.now().time()
                    start = _t(*map(int, target.split(":"))) if target else _t(0, 0)
                    end   = _t(*map(int, value.split(":")))  if value  else _t(23, 59)
                    if start <= end:
                        return start <= now <= end
                    else:
                        return now >= start or now <= end
                except Exception:
                    return False
            elif ct == "day_of_week":
                try:
                    from datetime import datetime as _dt
                    weekday = _dt.now().weekday() + 1  # 1=周一 ~ 7=周日
                    allowed = [int(x.strip()) for x in target.split(",") if x.strip().isdigit()]
                    return weekday in allowed
                except Exception:
                    return False
        except Exception:
            pass
        return True

    # ────────────────────── 热键监听 ──────────────────────

    def _parse_hotkey_modifiers(self, hotkey_str: str):
        """解析热键字符串，返回 (modifiers, vk_code)"""
        import ctypes
        MOD_ALT   = 0x0001
        MOD_CTRL  = 0x0002
        MOD_SHIFT = 0x0004
        MOD_WIN   = 0x0008

        VK_MAP = {
            "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74,
            "f6": 0x75, "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79,
            "f11": 0x7A, "f12": 0x7B,
            "enter": 0x0D, "space": 0x20, "esc": 0x1B, "tab": 0x09,
            "backspace": 0x08, "delete": 0x2E, "insert": 0x2D,
            "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
            "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
        }

        parts = [p.strip().lower() for p in hotkey_str.split("+")]
        mods = 0
        vk = 0
        for p in parts:
            if p == "ctrl":    mods |= MOD_CTRL
            elif p == "alt":   mods |= MOD_ALT
            elif p == "shift": mods |= MOD_SHIFT
            elif p == "win":   mods |= MOD_WIN
            elif p in VK_MAP:  vk = VK_MAP[p]
            elif len(p) == 1:  vk = ord(p.upper())
        return mods, vk

    def _hotkey_loop(self):
        """在线程中注册热键并循环处理 WM_HOTKEY 消息"""
        import ctypes
        import ctypes.wintypes as wt

        # 收集所有热键触发器
        hotkey_map: Dict[int, str] = {}  # hotkey_win_id -> task_id

        for task in self._tasks.values():
            if not task.enabled:
                continue
            for trig in task.triggers:
                if trig.trigger_type not in ("hotkey", "mouse_click") or not trig.enabled:
                    continue
                if trig.trigger_type == "hotkey":
                    hk_str = trig.params.get("hotkey", "")
                    if not hk_str:
                        continue
                    mods, vk = self._parse_hotkey_modifiers(hk_str)
                    if vk == 0:
                        continue
                    hid = self._hotkey_id_counter
                    self._hotkey_id_counter += 1
                    ok = ctypes.windll.user32.RegisterHotKey(None, hid, mods, vk)
                    if ok:
                        hotkey_map[hid] = task.id
                        self._hotkey_ids[trig.id] = hid
                        logger.info(f"热键已注册: {hk_str} -> 任务[{task.id}]")
                    else:
                        logger.warning(f"热键注册失败(可能冲突): {hk_str}")

        if not hotkey_map:
            return  # 没有热键触发器，直接退出

        # 消息循环
        WM_HOTKEY = 0x0312
        msg = wt.MSG()
        while not self._stop_event.is_set():
            ret = ctypes.windll.user32.PeekMessageW(
                ctypes.byref(msg), None, 0, 0, 1  # PM_REMOVE
            )
            if ret and msg.message == WM_HOTKEY:
                hid = msg.wParam
                if hid in hotkey_map:
                    self._fire(hotkey_map[hid], f"热键触发 id={hid}")
            time.sleep(0.05)

        # 注销热键
        for hid in hotkey_map.keys():
            ctypes.windll.user32.UnregisterHotKey(None, hid)

    def _unregister_all_hotkeys(self):
        try:
            import ctypes
            for hid in self._hotkey_ids.values():
                ctypes.windll.user32.UnregisterHotKey(None, hid)
            self._hotkey_ids.clear()
        except Exception:
            pass

    # ────────────────────── 主轮询 ──────────────────────

    def _poll_loop(self):
        # 初始化进程/窗口快照
        self._process_cache = self._get_process_set()
        self._window_cache  = self._get_window_set()

        schedule_states: Dict[str, dict] = {}  # trigger_id -> state

        while not self._stop_event.is_set():
            now = datetime.now()
            for task in list(self._tasks.values()):
                if not task.enabled:
                    continue
                for trig in task.triggers:
                    if not trig.enabled:
                        continue
                    tt = trig.trigger_type
                    try:
                        if tt == "startup":
                            # 仅触发一次（任务启动时已处理）
                            pass
                        elif tt == "system_boot":
                            self._check_system_boot(task.id, trig)
                        elif tt == "schedule":
                            self._check_schedule(task.id, trig, schedule_states, now)
                        elif tt == "process_start":
                            self._check_process_start(task.id, trig)
                        elif tt == "process_stop":
                            self._check_process_stop(task.id, trig)
                        elif tt == "window_appear":
                            self._check_window_appear(task.id, trig)
                        elif tt == "window_close":
                            self._check_window_close(task.id, trig)
                        elif tt in ("file_changed", "file_created", "file_deleted"):
                            self._check_file_event(task.id, trig)
                        elif tt == "usb_connected":
                            self._check_usb(task.id, trig)
                        elif tt == "network_change":
                            self._check_network(task.id, trig)
                        # clipboard_match 由独立线程处理
                        elif tt == "cpu_high":
                            self._check_cpu_high(task.id, trig)
                        elif tt == "memory_high":
                            self._check_memory_high(task.id, trig)
                        elif tt == "disk_full":
                            self._check_disk_full(task.id, trig)
                        elif tt == "battery_change":
                            self._check_battery(task.id, trig)
                        elif tt == "idle_detect":
                            self._check_idle(task.id, trig)
                        elif tt == "window_focus":
                            self._check_window_focus(task.id, trig)
                        elif tt == "time_range":
                            self._check_time_range(task.id, trig, now)
                        elif tt == "wifi_ssid":
                            self._check_wifi(task.id, trig)
                        elif tt == "window_blur":
                            self._check_window_blur(task.id, trig)
                        elif tt == "ping_latency":
                            self._check_ping_latency(task.id, trig)
                        # hotkey 和 mouse_click 由专用线程处理
                    except Exception as e:
                        logger.debug(f"触发器检查异常 [{tt}]: {e}")

            # 更新缓存
            self._process_cache = self._get_process_set()
            self._window_cache  = self._get_window_set()
            time.sleep(1.0)

    # ────────────────────── 开机完成触发 ──────────────────────

    def _check_system_boot(self, task_id: str, trig: Trigger):
        """
        开机完成触发器：在系统启动后延迟 delay_sec 秒触发一次。
        通过 psutil.boot_time() 获取系统启动时间，计算已启动时长。
        触发策略：在 delay_sec ~ delay_sec + check_interval 窗口内触发一次，
                  之后永不再触发（每次监控器启动都最多触发一次）。
        若监控器启动时系统已运行超过 delay_sec，则不触发（避免常驻情况下每次重启工具都触发）。
        """
        key = trig.id + "_boot"
        delay_sec     = float(trig.params.get("delay_sec", 30))
        check_interval = float(trig.params.get("check_interval", 10))

        # "monitor_start_time" 记录本次监控器启动时间（首次访问时初始化）
        start_key = trig.id + "_boot_monitor_start"
        if start_key not in self._file_mtimes:
            self._file_mtimes[start_key] = time.time()

        monitor_start = self._file_mtimes[start_key]

        # 已触发标记
        if self._file_mtimes.get(key, 0) == 1:
            return  # 已触发过，不再触发

        try:
            boot_time = psutil.boot_time()
            uptime = time.time() - boot_time

            # 如果监控器启动时系统已运行 > delay_sec + 60，说明不是刚开机的情况
            # 记录初始 uptime（只记录一次）
            init_uptime_key = trig.id + "_init_uptime"
            if init_uptime_key not in self._file_mtimes:
                self._file_mtimes[init_uptime_key] = uptime
                logger.debug(f"[system_boot] 监控启动时系统已运行 {uptime:.0f}s，延迟阈值 {delay_sec}s")

            init_uptime = self._file_mtimes[init_uptime_key]

            # 若监控器启动时系统已运行超过 delay_sec + 120s，说明不是刚开机，跳过
            if init_uptime > delay_sec + 120:
                logger.debug(f"[system_boot] 系统早已启动({init_uptime:.0f}s)，跳过触发")
                self._file_mtimes[key] = 1  # 标记"已处理"，不再检查
                return

            # 系统启动后已过 delay_sec 秒 → 触发
            if uptime >= delay_sec:
                self._file_mtimes[key] = 1
                self._fire(task_id, f"开机完成，已启动 {uptime:.0f}s（延迟 {delay_sec}s）", trig)
                logger.info(f"[system_boot] 已触发，系统运行时长 {uptime:.0f}s")

        except Exception as e:
            logger.debug(f"[system_boot] 检查异常: {e}")

    # ────────────────────── 定时触发 ──────────────────────

    def _check_schedule(self, task_id: str, trig: Trigger,
                        states: dict, now: datetime):
        p   = trig.params
        sid = trig.id
        st  = p.get("schedule_type", "interval")

        if sid not in states:
            states[sid] = {"last": None, "done": False}
        state = states[sid]

        if st == "interval":
            sec = float(p.get("interval_sec", 60))
            if state["last"] is None:
                state["last"] = now
            elif (now - state["last"]).total_seconds() >= sec:
                state["last"] = now
                self._fire(task_id, f"定时间隔 {sec}s", trig)

        elif st == "daily":
            tod = p.get("time_of_day", "08:00")
            try:
                h, m = map(int, tod.split(":"))
                target = now.replace(hour=h, minute=m, second=0, microsecond=0)
                if state["last"] is None:
                    state["last"] = now - timedelta(days=1)
                if now >= target and state["last"].date() < target.date():
                    state["last"] = now
                    self._fire(task_id, f"每日定时 {tod}", trig)
            except Exception:
                pass

        elif st == "weekly":
            weekday_map = {"monday":0,"tuesday":1,"wednesday":2,"thursday":3,
                           "friday":4,"saturday":5,"sunday":6}
            wd  = weekday_map.get(p.get("weekday","monday"), 0)
            tod = p.get("time_of_day", "08:00")
            try:
                h, m = map(int, tod.split(":"))
                if now.weekday() == wd:
                    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
                    if state["last"] is None:
                        state["last"] = now - timedelta(days=7)
                    if now >= target and (state["last"] is None or
                                         (now - state["last"]).total_seconds() > 3600):
                        state["last"] = now
                        self._fire(task_id, f"每周定时", trig)
            except Exception:
                pass

        elif st == "once":
            if not state["done"]:
                dt_str = p.get("once_datetime", "")
                try:
                    target = datetime.fromisoformat(dt_str)
                    if now >= target:
                        state["done"] = True
                        self._fire(task_id, f"一次性定时 {dt_str}", trig)
                except Exception:
                    pass

    # ────────────────────── 进程监控 ──────────────────────

    def _get_process_set(self) -> set:
        try:
            return {p.info["name"].lower()
                    for p in psutil.process_iter(["name"])
                    if p.info.get("name")}
        except Exception:
            return set()

    def _check_process_start(self, task_id: str, trig: Trigger):
        name = trig.params.get("name", "").lower()
        if not name:
            return
        new_procs = self._get_process_set()
        if name in new_procs and name not in self._process_cache:
            self._fire(task_id, f"进程启动: {name}", trig)

    def _check_process_stop(self, task_id: str, trig: Trigger):
        name = trig.params.get("name", "").lower()
        if not name:
            return
        new_procs = self._get_process_set()
        if name not in new_procs and name in self._process_cache:
            self._fire(task_id, f"进程结束: {name}", trig)

    # ────────────────────── 窗口监控 ──────────────────────

    def _get_window_set(self) -> set:
        try:
            import win32gui
            titles = set()
            def cb(hwnd, _):
                t = win32gui.GetWindowText(hwnd)
                if t:
                    titles.add(t.lower())
            win32gui.EnumWindows(cb, None)
            return titles
        except Exception:
            return set()

    def _check_window_appear(self, task_id: str, trig: Trigger):
        pattern = trig.params.get("title", "").lower()
        if not pattern:
            return
        new_wins = self._get_window_set()
        for w in new_wins:
            if fnmatch.fnmatch(w, pattern) and w not in self._window_cache:
                self._fire(task_id, f"窗口出现: {w}", trig)
                break

    def _check_window_close(self, task_id: str, trig: Trigger):
        pattern = trig.params.get("title", "").lower()
        if not pattern:
            return
        new_wins = self._get_window_set()
        for w in self._window_cache:
            if fnmatch.fnmatch(w, pattern) and w not in new_wins:
                self._fire(task_id, f"窗口关闭: {w}", trig)
                break

    # ────────────────────── 文件监控 ──────────────────────

    def _check_file_event(self, task_id: str, trig: Trigger):
        path    = trig.params.get("path", "")
        pattern = trig.params.get("pattern", "*")
        tt      = trig.trigger_type

        if not path:
            return

        key = f"{trig.id}:{path}"
        if os.path.isfile(path):
            mtime = os.path.getmtime(path) if os.path.exists(path) else None
            prev  = self._file_mtimes.get(key)
            if prev is None:
                self._file_mtimes[key] = mtime
                return
            if tt == "file_changed" and mtime != prev:
                self._file_mtimes[key] = mtime
                self._fire(task_id, f"文件变化: {path}", trig)
            elif tt == "file_deleted" and mtime is None and prev is not None:
                self._file_mtimes[key] = None
                self._fire(task_id, f"文件删除: {path}", trig)
            elif tt == "file_created" and mtime is not None and prev is None:
                self._file_mtimes[key] = mtime
                self._fire(task_id, f"文件创建: {path}", trig)
        elif os.path.isdir(path):
            try:
                files = set(f for f in os.listdir(path)
                            if fnmatch.fnmatch(f, pattern))
                prev_files = self._file_mtimes.get(key + "_set")
                self._file_mtimes[key + "_set"] = files
                if prev_files is None:
                    return
                if tt == "file_created":
                    new = files - prev_files
                    if new:
                        self._fire(task_id, f"文件创建: {list(new)[0]}", trig)
                elif tt == "file_deleted":
                    removed = prev_files - files
                    if removed:
                        self._fire(task_id, f"文件删除: {list(removed)[0]}", trig)
                elif tt == "file_changed":
                    if files != prev_files:
                        self._fire(task_id, f"目录变化: {path}", trig)
            except Exception:
                pass

    # ────────────────────── USB / 网络 ──────────────────────

    def _check_usb(self, task_id: str, trig: Trigger):
        # 通过磁盘列表变化检测
        key = trig.id + "_drives"
        try:
            current = set(p.device for p in psutil.disk_partitions())
        except Exception:
            return
        prev = self._file_mtimes.get(key)
        if prev is None:
            self._file_mtimes[key] = current
            return
        if not isinstance(prev, set):
            prev = set()
        new_drives = current - prev
        if new_drives:
            self._file_mtimes[key] = current
            self._fire(task_id, f"USB/驱动器连接: {new_drives}", trig)

    def _check_network(self, task_id: str, trig: Trigger):
        event = trig.params.get("event", "any")
        key   = trig.id + "_net"
        try:
            stats = psutil.net_if_stats()
            is_up = any(s.isup for s in stats.values())
        except Exception:
            return
        prev = self._file_mtimes.get(key)
        if prev is None:
            self._file_mtimes[key] = is_up
            return
        if event in ("connected", "any") and is_up and not prev:
            self._file_mtimes[key] = is_up
            self._fire(task_id, "网络已连接", trig)
        elif event in ("disconnected", "any") and not is_up and prev:
            self._file_mtimes[key] = is_up
            self._fire(task_id, "网络已断开", trig)
        else:
            self._file_mtimes[key] = is_up

    # ────────────────────── 剪贴板监控（独立线程） ──────────────────────

    def _clipboard_loop(self):
        """剪贴板独立高频轮询线程（默认500ms），检测复制操作"""
        while not self._stop_event.is_set():
            for task in list(self._tasks.values()):
                if not task.enabled:
                    continue
                for trig in task.triggers:
                    if trig.trigger_type not in ("clipboard_copy", "clipboard_match") or not trig.enabled:
                        continue
                    try:
                        self._check_clipboard_copy(task.id, trig)
                    except Exception as e:
                        logger.debug(f"剪贴板检查异常: {e}")
            self._stop_event.wait(0.5)

    # ────────────────────── 邮件 ──────────────────────


    def _email_loop(self):
        while not self._stop_event.is_set():
            try:
                has_email_trigger = any(
                    any(t.trigger_type == "email_received" and t.enabled
                        for t in task.triggers)
                    for task in self._tasks.values()
                    if task.enabled
                )
                if has_email_trigger and self.config.imap_server:
                    self._check_emails()
            except Exception as e:
                logger.debug(f"邮件检查异常: {e}")
            # 邮件每30秒检查一次
            for _ in range(30):
                if self._stop_event.is_set():
                    return
                time.sleep(1)

    def _check_emails(self):
        cfg = self.config
        try:
            if cfg.imap_ssl:
                mail = imaplib.IMAP4_SSL(cfg.imap_server, cfg.imap_port)
            else:
                mail = imaplib.IMAP4(cfg.imap_server, cfg.imap_port)
            mail.login(cfg.imap_user, cfg.imap_password)
            mail.select("INBOX")
            _, data = mail.search(None, "UNSEEN")
            uids = data[0].split()
            if not uids:
                mail.logout()
                return
            for task in self._tasks.values():
                if not task.enabled:
                    continue
                for trig in task.triggers:
                    if trig.trigger_type != "email_received" or not trig.enabled:
                        continue
                    sender  = trig.params.get("sender", "").lower()
                    subject = trig.params.get("subject", "").lower()
                    # 简单匹配：只检测有未读邮件
                    for uid in uids:
                        _, msg_data = mail.fetch(uid, "(BODY[HEADER.FIELDS (FROM SUBJECT)])")
                        raw = msg_data[0][1].decode("utf-8", errors="replace").lower()
                        match = True
                        if sender and sender not in raw:
                            match = False
                        if subject and subject not in raw:
                            match = False
                        if match:
                            self._fire(task.id, "收到新邮件")
                            break
            mail.logout()
        except Exception as e:
            logger.debug(f"IMAP检查失败: {e}")

    # ────────────────────── 剪贴板监控 ──────────────────────

    def _get_clipboard_text(self) -> Optional[str]:
        """获取当前剪贴板文本内容（不依赖 Qt）"""
        try:
            import ctypes
            CF_UNICODETEXT = 13
            if not ctypes.windll.user32.OpenClipboard(None):
                return None
            try:
                h = ctypes.windll.user32.GetClipboardData(CF_UNICODETEXT)
                if not h:
                    return None
                p = ctypes.windll.kernel32.GlobalLock(h)
                if not p:
                    return None
                try:
                    text = ctypes.wstring_at(p)
                    return text
                finally:
                    ctypes.windll.kernel32.GlobalUnlock(h)
            finally:
                ctypes.windll.user32.CloseClipboard()
        except Exception:
            return None

    def _clipboard_matches(self, text: str, pattern: str, mode: str, case: bool) -> bool:
        """判断剪贴板文本是否匹配"""
        if not pattern:
            return True  # 留空 = 任意内容变化都触发
        t = text if case else text.lower()
        p = pattern if case else pattern.lower()
        if mode == "exact":
            return t == p
        elif mode == "contains":
            return p in t
        elif mode == "startswith":
            return t.startswith(p)
        elif mode == "endswith":
            return t.endswith(p)
        elif mode == "wildcard":
            return fnmatch.fnmatch(t, p)
        return p in t

    def _check_clipboard(self, task_id: str, trig: Trigger):
        """检查剪贴板是否出现指定内容"""
        key         = trig.id + "_cb"
        pattern     = trig.params.get("text", "")
        mode        = trig.params.get("match_mode", "contains")
        case        = trig.params.get("case_sensitive", False)
        save_to     = trig.params.get("save_to", "clipboard_text")

        current = self._get_clipboard_text()

        # 初始化快照（即使获取失败，也记录 None→"" 避免永远停在初始化）
        if key not in self._file_mtimes:
            self._file_mtimes[key] = current if current is not None else ""
            return

        if current is None:
            return

        prev = self._file_mtimes[key]
        # 内容没变化，不触发
        if current == prev:
            return

        # 内容变化了，更新快照
        self._file_mtimes[key] = current

        # 检查是否匹配
        if self._clipboard_matches(current, pattern, mode, case):
            # 把匹配内容存入共享变量缓存（供 runner 使用）
            self._clipboard_match_vars = getattr(self, "_clipboard_match_vars", {})
            self._clipboard_match_vars[f"{task_id}:{save_to}"] = current
            self._fire(task_id, f"剪贴板匹配: {current[:30]}", trig)

    def _check_clipboard_copy(self, task_id: str, trig: Trigger):
        """
        检测到复制操作（剪贴板序列号发生变化）即触发。
        使用 GetClipboardSequenceNumber() Win32 API 检测，不需要 OpenClipboard，
        无锁竞争问题，每次剪贴板内容变化序列号自动递增，是最可靠的检测方式。
        复制内容会尝试存入 save_to 变量供后续使用（读取失败不影响触发）。
        """
        key     = trig.id + "_cb_seq"
        save_to = trig.params.get("save_to", "clipboard_text")

        # 使用序列号检测——不需要打开剪贴板，无锁竞争
        try:
            import ctypes
            seq = ctypes.windll.user32.GetClipboardSequenceNumber()
        except Exception:
            return

        prev_seq = self._file_mtimes.get(key)
        if prev_seq is None:
            # 首次运行：仅记录当前序列号，不触发
            self._file_mtimes[key] = seq
            return
        if seq == prev_seq:
            return

        # 序列号变化 = 剪贴板已被写入 = 检测到复制操作
        self._file_mtimes[key] = seq

        # 尝试读取剪贴板内容存入变量（失败不影响触发）
        current = self._get_clipboard_text() or ""
        self._clipboard_match_vars = getattr(self, "_clipboard_match_vars", {})
        self._clipboard_match_vars[f"{task_id}:{save_to}"] = current
        self._fire(task_id, f"检测到复制: {current[:30]!r}", trig)

    # ────────────────────── CPU / 内存 / 磁盘 / 电池 ──────────────────────

    def _check_cpu_high(self, task_id: str, trig: Trigger):
        """CPU 占用率超阈值持续 N 秒触发"""
        key       = trig.id + "_cpu"
        threshold = float(trig.params.get("threshold", 90))
        duration  = float(trig.params.get("duration", 5))
        usage = psutil.cpu_percent(interval=None)
        now = time.time()
        if usage >= threshold:
            start = self._file_mtimes.get(key, now)
            if key not in self._file_mtimes:
                self._file_mtimes[key] = now
            elif now - start >= duration:
                self._file_mtimes[key] = now + duration * 2  # 避免连续触发
                self._fire(task_id, f"CPU {usage:.0f}% 超过 {threshold}% 持续 {duration}s", trig)
        else:
            self._file_mtimes[key] = now

    def _check_memory_high(self, task_id: str, trig: Trigger):
        """内存占用率超阈值触发"""
        key       = trig.id + "_mem"
        threshold = float(trig.params.get("threshold", 90))
        usage = psutil.virtual_memory().percent
        prev = self._file_mtimes.get(key, 0.0)
        if usage >= threshold and prev == 0.0:
            self._file_mtimes[key] = 1.0
            self._fire(task_id, f"内存 {usage:.0f}% 超过 {threshold}%", trig)
        elif usage < threshold:
            self._file_mtimes[key] = 0.0

    def _check_disk_full(self, task_id: str, trig: Trigger):
        """磁盘剩余空间不足触发"""
        key       = trig.id + "_disk"
        drive     = trig.params.get("drive", "").strip()
        threshold = float(trig.params.get("threshold", 5)) * 1024**3  # GB -> bytes
        drives = [drive] if drive else [p.mountpoint for p in psutil.disk_partitions(all=False)]
        for d in drives:
            try:
                free = psutil.disk_usage(d).free
                state_key = key + d
                prev = self._file_mtimes.get(state_key, 0.0)
                if free <= threshold and prev == 0.0:
                    self._file_mtimes[state_key] = 1.0
                    self._fire(task_id, f"磁盘 {d} 剩余 {free/1024**3:.1f}GB", trig)
                elif free > threshold:
                    self._file_mtimes[state_key] = 0.0
            except Exception:
                pass

    def _check_battery(self, task_id: str, trig: Trigger):
        """电池状态变化触发"""
        key       = trig.id + "_bat"
        event     = trig.params.get("event", "low")
        threshold = float(trig.params.get("threshold", 20))
        try:
            bat = psutil.sensors_battery()
            if bat is None:
                return
            pct     = bat.percent
            plugged = bat.power_plugged
            prev    = self._file_mtimes.get(key + "_state", -1)

            if event == "low":
                if pct <= threshold and prev > threshold:
                    self._fire(task_id, f"电池低电量 {pct:.0f}%", trig)
            elif event == "critical":
                if pct <= 5 and prev > 5:
                    self._fire(task_id, f"电池电量极低 {pct:.0f}%", trig)
            elif event == "charging" and not (prev >= 0 and bool(prev & 0x100)) and plugged:
                self._fire(task_id, "开始充电", trig)
            elif event == "discharging" and (prev >= 0 and bool(prev & 0x100)) and not plugged:
                self._fire(task_id, "开始放电", trig)
            elif event == "full" and pct >= 100 and not (prev >= 100):
                self._fire(task_id, "电池充满", trig)

            self._file_mtimes[key + "_state"] = pct | (0x100 if plugged else 0)
        except Exception:
            pass

    def _check_idle(self, task_id: str, trig: Trigger):
        """系统空闲检测（用 GetLastInputInfo 获取上次输入时间）"""
        key      = trig.id + "_idle"
        idle_sec = float(trig.params.get("idle_sec", 300))
        try:
            import ctypes
            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
            elapsed = (ctypes.windll.kernel32.GetTickCount() - lii.dwTime) / 1000.0
            fired = bool(self._file_mtimes.get(key, 0))
            if elapsed >= idle_sec and not fired:
                self._file_mtimes[key] = 1
                self._fire(task_id, f"系统空闲 {elapsed:.0f}s", trig)
            elif elapsed < idle_sec:
                self._file_mtimes[key] = 0
        except Exception:
            pass

    def _check_window_focus(self, task_id: str, trig: Trigger):
        """检测指定窗口获得焦点"""
        title = trig.params.get("title", "")
        key   = trig.id + "_focus"
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
            cur = buf.value
            prev = self._file_mtimes.get(key, "")
            if cur != prev:
                self._file_mtimes[key] = cur
                if not title or fnmatch.fnmatch(cur.lower(), title.lower()):
                    self._fire(task_id, f"窗口焦点: {cur}", trig)
        except Exception:
            pass

    def _check_time_range(self, task_id: str, trig: Trigger, now: datetime):
        """时间段内按间隔触发"""
        key          = trig.id + "_tr"
        start_time   = trig.params.get("start_time", "09:00")
        end_time     = trig.params.get("end_time", "18:00")
        weekdays_str = trig.params.get("weekdays", "")
        interval_sec = float(trig.params.get("interval_sec", 3600))
        try:
            sh, sm = map(int, start_time.split(":"))
            eh, em = map(int, end_time.split(":"))
            s_mins = sh * 60 + sm
            e_mins = eh * 60 + em
            cur_mins = now.hour * 60 + now.minute
            in_range = s_mins <= cur_mins <= e_mins
            # 检查星期
            if weekdays_str.strip():
                wd = [int(d.strip()) for d in weekdays_str.split(",") if d.strip().isdigit()]
                if now.weekday() not in wd:
                    in_range = False
            if not in_range:
                return
            last = self._file_mtimes.get(key, 0)
            if time.time() - last >= interval_sec:
                self._file_mtimes[key] = time.time()
                self._fire(task_id, f"时间段内触发 {now.strftime('%H:%M')}", trig)
        except Exception:
            pass

    def _check_wifi(self, task_id: str, trig: Trigger):
        """检测连接到指定 WiFi SSID"""
        key   = trig.id + "_wifi"
        ssid  = trig.params.get("ssid", "")
        event = trig.params.get("event", "connected")
        try:
            import subprocess
            result = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True, text=True, encoding="gbk", errors="replace"
            )
            cur_ssid = ""
            for line in result.stdout.splitlines():
                if "SSID" in line and "BSSID" not in line:
                    cur_ssid = line.split(":", 1)[-1].strip()
                    break
            prev = self._file_mtimes.get(key, "")
            if cur_ssid != prev:
                self._file_mtimes[key] = cur_ssid
                if event == "connected" and cur_ssid == ssid:
                    self._fire(task_id, f"已连接 WiFi: {ssid}", trig)
                elif event == "disconnected" and prev == ssid and cur_ssid != ssid:
                    self._fire(task_id, f"已断开 WiFi: {ssid}", trig)
        except Exception:
            pass

    def _check_internet(self, task_id: str, trig: Trigger):
        """
        通过 WinINet InternetGetConnectedState 检测互联网连通性。
        这是 Windows 系统级 API，直接查询系统网络状态（不做实际 TCP 连接）。
        若 WinINet 不可用则回退为 psutil 网卡状态判断。
        触发策略：
          - connected：网络从断线→恢复时触发 1 次
          - disconnected：网络从连通→断线时触发 1 次
          - any：每次状态切换都触发
        """
        key          = trig.id + "_inet"
        event        = trig.params.get("event", "disconnected")
        interval_sec = float(trig.params.get("interval_sec", 30))

        # 节流：避免每秒都调用
        last_check = self._file_mtimes.get(key + "_ts", 0)
        if time.time() - last_check < interval_sec:
            return
        self._file_mtimes[key + "_ts"] = time.time()

        is_connected = self._wininet_connected()

        # 使用类级别哨兵值区分"从未记录"和"记录为 False"
        prev_state = self._file_mtimes.get(key, TriggerMonitor._SENTINEL)

        if prev_state is TriggerMonitor._SENTINEL:
            # 首次检测：记录当前状态，不触发（避免启动时误触发）
            self._file_mtimes[key] = is_connected
            return

        # 状态未变化，不触发
        if is_connected == prev_state:
            return

        # 状态发生了切换，更新记录
        self._file_mtimes[key] = is_connected

        if event == "connected":
            if is_connected and not prev_state:
                self._fire(task_id, "网络已恢复（互联网可达）", trig)
        elif event == "disconnected":
            if not is_connected and prev_state:
                self._fire(task_id, "网络已断开（互联网不可达）", trig)
        elif event == "any":
            if is_connected and not prev_state:
                self._fire(task_id, "网络已恢复（互联网可达）", trig)
            elif not is_connected and prev_state:
                self._fire(task_id, "网络已断开（互联网不可达）", trig)

    def _wininet_connected(self) -> bool:
        """
        使用 Windows WinINet API 检测互联网连通性。
        InternetGetConnectedState 返回系统当前网络连接状态（无实际网络请求）。
        回退：若调用失败则用 psutil 检查是否有活跃网卡（有限可靠）。
        """
        try:
            import ctypes
            flags = ctypes.c_ulong(0)
            # wininet.dll: InternetGetConnectedState(lpdwFlags, dwReserved)
            connected = ctypes.windll.wininet.InternetGetConnectedState(
                ctypes.byref(flags), 0
            )
            return bool(connected)
        except Exception:
            pass
        # 回退：psutil 网卡活跃状态
        try:
            stats = psutil.net_if_stats()
            return any(s.isup for name, s in stats.items()
                       if name.lower() not in ("lo", "loopback"))
        except Exception:
            return False

    def _check_window_blur(self, task_id: str, trig: Trigger):
        """检测窗口失去焦点（前台窗口发生变化，前一个窗口匹配则触发）"""
        title = trig.params.get("title", "")
        key   = trig.id + "_blur"
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            buf  = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
            cur = buf.value
            prev = self._file_mtimes.get(key, "")
            if cur != prev:
                # 前台窗口切换了，prev 就是刚失去焦点的窗口
                old = prev
                self._file_mtimes[key] = cur
                if old:  # 排除初次记录
                    if not title or fnmatch.fnmatch(old.lower(), title.lower()):
                        self._fire(task_id, f"窗口失去焦点: {old}", trig)
        except Exception:
            pass

    # ────────────────────── Ping 延迟触发器 ──────────────────────

    def _get_ping_latency_ms(self, host: str, count: int = 1) -> Optional[float]:
        """
        用系统 ping 命令获取延迟(ms)，返回 None 表示超时/不可达。
        使用 subprocess 调用系统自带 ping，无需管理员权限。
        Windows: ping -n 1 host；解析 "平均 = XXms" / "Average = XXms"
        """
        import subprocess
        import re
        try:
            result = subprocess.run(
                ["ping", "-n", str(count), host],
                capture_output=True, text=True, timeout=15,
                encoding="gbk", errors="replace",
                creationflags=0x08000000  # CREATE_NO_WINDOW，静默不弹窗
            )
            output = result.stdout
            # 解析中文系统: "平均 = 12ms" 或英文: "Average = 12ms"
            m = re.search(r'(?:平均|Average)\s*=\s*(\d+)\s*ms', output, re.IGNORECASE)
            if m:
                return float(m.group(1))
            # 备用解析：任意行的 "XXms" TTL 回复（取最后一个有效值）
            m2 = re.findall(r'[时时间time]*\s*[=<]\s*(\d+)\s*ms', output, re.IGNORECASE)
            if m2:
                return float(m2[-1])
        except Exception as e:
            logger.debug(f"ping 执行失败: {e}")
        return None

    def _check_ping_latency(self, task_id: str, trig: Trigger):
        """
        Ping 延迟触发器：定期 ping 指定 host，当延迟超过/低于阈值时触发。
        params:
          host         - 目标主机（域名或IP，支持变量）
          threshold_ms - 延迟阈值（ms）
          direction    - "above" 超过阈值触发 / "below" 低于阈值触发 / "timeout" 超时/不可达时触发
          interval_sec - 检测间隔（秒，默认30）
        触发策略：状态发生切换时触发（避免连续重复触发）
        """
        key          = trig.id + "_ping"
        host         = trig.params.get("host", "8.8.8.8")
        threshold_ms = float(trig.params.get("threshold_ms", 200))
        direction    = trig.params.get("direction", "above")
        interval_sec = float(trig.params.get("interval_sec", 30))

        # 节流：避免每秒都调用，消耗网络资源
        last_check = self._file_mtimes.get(key + "_ts", 0)
        if time.time() - last_check < interval_sec:
            return
        self._file_mtimes[key + "_ts"] = time.time()

        latency = self._get_ping_latency_ms(host)

        # 判断当前是否满足触发条件
        # 注意：latency=None 表示超时/断网
        #   - direction="timeout"：明确检测超时，触发
        #   - direction="above"：延迟无限大，视为超过任何阈值，触发
        #   - direction="below"：无法 ping 通，视为不满足「低于阈值」，不触发
        if direction == "timeout":
            cur_state = (latency is None)
        elif direction == "above":
            # None（超时）视为延迟无限大，同样满足「超过阈值」
            cur_state = (latency is None or latency > threshold_ms)
        elif direction == "below":
            cur_state = (latency is not None and latency < threshold_ms)
        else:
            cur_state = False

        prev_state = self._file_mtimes.get(key, TriggerMonitor._SENTINEL)

        if prev_state is TriggerMonitor._SENTINEL:
            # 首次检测：记录当前状态，不触发
            self._file_mtimes[key] = cur_state
            return

        # 状态未变化，不触发
        if cur_state == prev_state:
            return

        # 状态从不满足→满足，触发
        self._file_mtimes[key] = cur_state
        if cur_state:
            if direction == "timeout":
                reason = f"Ping {host} 超时/不可达"
            elif direction == "above":
                if latency is None:
                    reason = f"Ping {host} 超时/不可达（视为超过 {threshold_ms:.0f}ms 阈值）"
                else:
                    reason = f"Ping {host} 延迟 {latency:.0f}ms > {threshold_ms:.0f}ms"
            else:
                reason = f"Ping {host} 延迟 {latency:.0f}ms < {threshold_ms:.0f}ms"
            self._fire(task_id, reason, trig)

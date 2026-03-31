"""
AutoFlow 国际化（i18n）模块
支持：简体中文 / 繁体中文 / 美式英语
外部语言包：%LOCALAPPDATA%\\XinyuCraft\\AutoFlow\\Language\\<lang_code>.json
"""
import os
from typing import Dict

# ─── 翻译字典 ───
_TRANSLATIONS: Dict[str, Dict[str, str]] = {

    "zh_CN": {
        # 通用
        "app.name": "AutoFlow",
        "app.subtitle": "智能自动化工具",
        "btn.ok": "确定",
        "btn.cancel": "取消",
        "btn.save": "保存",
        "btn.close": "关闭",
        "btn.add": "添加",
        "btn.delete": "删除",
        "btn.rename": "重命名",
        "btn.refresh": "刷新",
        "btn.browse": "浏览",
        "btn.back": "<  返回",
        "btn.test": "测试",
        "btn.test_send": "测试发送",
        "btn.test_connect": "测试连接",
        "btn.test_ai": "🔗  测试连接",
        # 侧边栏
        "sidebar.tasks": "任务列表",
        "sidebar.new_task": "+  新建任务",
        "sidebar.new_project": "新建项目",
        "sidebar.open_project": "打开项目",
        "sidebar.save_project": "保存项目",
        "sidebar.save_as": "另存为",
        "sidebar.close_project": "关闭项目",
        "sidebar.undo": "撤回  Ctrl+Z",
        "sidebar.redo": "重做  Ctrl+Y / Ctrl+Shift+Z",
        "sidebar.history": "操作历史",
        "sidebar.var_manager": "变量管理",
        "sidebar.settings": "设置",
        "sidebar.plugins": "插件管理",
        # 插件管理
        "plugin.title": "插件管理",
        "plugin.back": "返回",
        "plugin.search_ph": "搜索插件...",
        "plugin.install_btn": "安装插件",
        "plugin.open_dir_btn": "插件目录",
        "plugin.empty_hint": "暂无插件。点击「安装插件」从文件夹安装，或在插件目录中放置插件。",
        "plugin.stats": "共 {total} 个插件，已启用 {enabled} 个",
        "plugin.dev_docs": "如何开发插件？",
        "plugin.no_desc": "暂无描述",
        "plugin.enabled_btn": "已启用",
        "plugin.disabled_btn": "已禁用",
        "plugin.settings_btn": "设置",
        "plugin.detail_btn": "详情",
        "plugin.load_failed": "插件加载失败",
        "plugin.no_settings_title": "无设置",
        "plugin.no_settings_msg": "该插件没有提供设置界面。",
        "plugin.author_label": "作者",
        "plugin.id_label": "插件ID",
        "plugin.dir_label": "目录",
        "plugin.provided_blocks": "提供的功能块",
        "plugin.install_from_folder": "从文件夹安装插件",
        "plugin.install_error": "安装失败",
        "plugin.no_plugin_json": "所选目录中没有找到 plugin.json：\n{path}",
        "plugin.install_overwrite_title": "覆盖安装",
        "plugin.install_overwrite_msg": "插件「{name}」已存在，是否覆盖？",
        "plugin.install_ok_title": "安装成功",
        "plugin.install_ok_msg": "插件「{name}」已安装。",
        # 设置
        "settings.title": "设置",
        "settings.general": "通用",
        "settings.project": "项目",
        "settings.email": "邮箱",
        "settings.appearance": "外观",
        "settings.hotkeys": "按键",
        "settings.advanced": "高级",
        "settings.about": "关于",
        "settings.save": "保存设置",
        "settings.saved": "已保存",
        "settings.saved_msg": "设置已保存！",
        "settings.language": "界面语言",
        "settings.language.zh_CN": "简体中文",
        "settings.language.zh_TW": "繁体中文",
        "settings.language.en_US": "English",
        "settings.language_hint": "切换后立即生效，无需重启。",
        # 设置 - 通用 Tab
        "settings.grp.startup": "开机自启",
        "settings.auto_start": "程序开机后自动启动",
        "settings.auto_start_task": "启动后自动运行任务：",
        "settings.no_task": "（不运行任何任务）",
        "settings.launch_behavior": "软件启动后：",
        "settings.launch_behavior.show": "打开主界面",
        "settings.launch_behavior.minimize": "最小化至任务栏",
        "settings.launch_behavior.tray": "隐藏至托盘",
        "settings.grp.ui": "界面行为",
        "settings.minimize_to_tray": "关闭窗口时最小化到托盘",
        "settings.show_log": "运行时显示日志面板",
        # 设置 - 项目 Tab
        "settings.grp.last_project": "上次项目",
        "settings.reopen_last": "启动时自动打开上次项目",
        "settings.grp.autosave": "自动保存",
        "settings.autosave_enable": "启用自动保存",
        "settings.autosave_interval": "自动保存间隔：",
        "settings.autosave_unit": " 秒",
        "settings.grp.undo": "撤回历史",
        "settings.max_undo": "最大撤回步数：",
        "settings.undo_unit": " 步",
        "settings.undo_hint": "撤回步数越多，内存占用越大。推荐 50 步。",
        "settings.grp.screenshot": "截图默认目录",
        "settings.screenshot_dir": "默认保存目录：",
        "settings.screenshot_ph": "留空 = 系统图片库",
        # 设置 - 邮箱 Tab
        "settings.grp.smtp": "SMTP（发送邮件）",
        "settings.grp.imap": "IMAP（接收邮件，用于触发器）",
        "settings.smtp.server": "服务器：",
        "settings.smtp.port": "端口：",
        "settings.smtp.user": "账号：",
        "settings.smtp.pass": "密码/授权码：",
        "settings.smtp.ssl": "使用 SSL",
        "settings.imap.server": "服务器：",
        "settings.imap.port": "端口：",
        "settings.imap.user": "账号：",
        "settings.imap.pass": "密码/授权码：",
        "settings.imap.ssl": "使用 SSL",
        "settings.email_hint": "常见配置：\n  QQ邮箱 SMTP: smtp.qq.com:465  IMAP: imap.qq.com:993\n  163邮箱 SMTP: smtp.163.com:465  IMAP: imap.163.com:993\n  Outlook SMTP: smtp.office365.com:587  IMAP: outlook.office365.com:993",
        # 设置 - 外观 Tab
        "settings.grp.lang": "界面语言",
        "settings.lang_label": "语言：",
        "settings.grp.theme": "主题",
        "settings.theme_label": "主题预设：",
        "settings.theme_hint": "切换主题后立即预览，点击「保存设置」永久生效。",
        "settings.theme_follow": "跟随系统",
        # 设置 - 按键 Tab
        "settings.grp.hotkeys_custom": "自定义快捷键",
        "settings.coord_hotkey": "坐标选点确认键：",
        "settings.coord_hotkey_hint": "点击功能块里的「📍 选点」后，将鼠标移到目标位置，按此键确认坐标。\n点击输入框后直接按下目标按键组合即可录入。",
        "settings.stop_hotkey": "强制终止所有任务：",
        "settings.stop_hotkey_hint": "按下此快捷键立即停止所有正在运行的任务（全局有效，不需要窗口获得焦点）。\n点击输入框后直接按下目标按键组合即可录入。",
        "settings.grp.hotkeys_ref": "内置快捷键（只读参考）",
        "settings.hotkeys.cat": "分类",
        "settings.hotkeys.key": "快捷键",
        "settings.hotkeys.desc": "说明",
        # 设置 - AI Tab
        "settings.grp.ai_model": "模型配置",
        "settings.ai_provider": "服务商：",
        "settings.ai_model_name": "模型名称：",
        "settings.ai_model_preset": "快速选择模型：",
        "settings.ai_api_key": "API Key：",
        "settings.ai_show_key": "显示 API Key",
        "settings.ai_base_url": "API 地址(Base URL)：",
        "settings.grp.ai_params": "默认参数",
        "settings.ai_temperature": "Temperature（创造性）：",
        "settings.ai_max_tokens": "Max Tokens（最大回复长度）：",
        "settings.ai_temp_hint": "Temperature=0 更精确，=1 更有创意，=2 更随机。推荐 0.7。",
        "settings.grp.ai_system": "默认系统提示词（System Prompt）",
        "settings.ai_hint": "🤖  配置 AI 大模型后，可在功能块中使用「AI 对话」和「AI 生成文本」功能。\n支持 OpenAI、DeepSeek、通义千问、Azure OpenAI 等兼容 OpenAI 接口的服务。",
        # 设置 - 高级 Tab
        "settings.grp.log": "日志",
        "settings.log_path": "日志文件路径：",
        "settings.max_log_lines": "最大日志行数：",
        # 任务编辑器
        "task.new": "新任务",
        "task.rename": "重命名任务",
        "task.delete": "删除任务",
        "task.run": "> 立即运行",
        "task.stop": "停止运行",
        "task.running": "正在运行",
        "task.finished": "已完成",
        "task.stopped": "已停止",
        "task.run_btn": "▶  立即运行",
        "task.stop_btn": "⏹  停止",
        "task.enabled": "启用",
        "task.name_ph": "任务名称",
        "task.desc_ph": "任务描述（可选）",
        "task.unnamed": "未命名任务",
        # 触发器
        "trigger.section": "⚡ 触发器",
        "trigger.add": "＋ 添加触发器",
        "trigger.clear": "🗑 清空",
        "trigger.clear_tip": "清空所有触发器",
        "trigger.empty": "还没有触发器\n添加触发器后任务将自动运行",
        "trigger.edit_title": "编辑触发器：",
        "trigger.comment": "备注：",
        "trigger.comment_ph": "可选备注",
        "trigger.enabled": "启用此触发器",
        "trigger.copy_tip": "复制此触发器",
        "trigger.disabled": "(已禁用)",
        "trigger.hint.hotkey": "提示：如果快捷键与其他程序冲突，触发可能失效，但不影响使用。",
        "trigger.hint.clipboard": "提示：程序每隔指定毫秒轮询一次剪贴板。使用通配符模式时支持 * 和 ? 通配符。",
        # 功能块
        "block.add": "＋ 添加功能块",
        "block.empty": "还没有功能块\n点击「＋ 添加功能块」开始构建流程",
        "block.section": "🧱 功能块",
        "block.clear": "🗑 清空",
        "block.clear_tip": "清空所有功能块",
        "block.edit_title": "编辑：",
        "block.comment": "备注：",
        "block.comment_ph": "可选备注",
        "block.enabled": "启用此块",
        "block.copy_tip": "复制此功能块",
        "block.disabled": "(已禁用)",
        # 控件
        "widget.pick": "🎯 点选",
        "widget.list": "📋 列表",
        "widget.pick_tip": "点击后主窗口最小化，3秒内点击目标窗口，自动填入其标题",
        "widget.list_tip": "从进程/窗口列表中选择",
        "widget.hotkey_ph": "点击此处，然后按快捷键 (如 Ctrl+Alt+R)",
        "widget.hotkey_rec": "正在录制…按下快捷键",
        "widget.window_ph": "窗口标题（留空=当前前台窗口）",
        "widget.proc_win_ph": "窗口标题或进程名",
        # 坐标选点
        "coord.btn": "📍 选点",
        "coord.tip": "按 {} 键确认坐标",
        "coord.counting": "{}s...",
        # 宏录制
        "macro.start": "⏺ 开始录制",
        "macro.stop": "⏹ 停止录制",
        "macro.clear": "🗑 清空",
        "macro.events": "个事件",
        "macro.recording": "录制中...",
        "macro.ready": "就绪",
        "macro.hint": "录制鼠标点击与移动，回放时使用相对坐标（相对于录制起点）",
        # 主窗口对话框
        "dlg.new_task_name": "新任务名称",
        "dlg.enter_task_name": "请输入任务名称：",
        "dlg.rename_task": "重命名任务",
        "dlg.delete_task_title": "删除任务",
        "dlg.delete_task_msg": "确定要删除任务「{}」吗？",
        "dlg.unsaved_title": "未保存的更改",
        "dlg.unsaved_msg": "项目有未保存的更改，是否保存？",
        "dlg.no_project": "没有打开的项目",
        "dlg.open_project_title": "打开项目",
        "dlg.save_project_title": "保存项目",
        "dlg.project_filter": "AutoFlow 项目 (*.afp);;所有文件 (*.*)",
        "dlg.error": "错误",
        "dlg.warning": "警告",
        "dlg.info": "提示",
        # 状态栏
        "status.ready": "就绪",
        "status.running": "运行中",
        "status.undo_count": "撤回: {}/{}",
        "status.modified": "● 未保存",
        # 系统托盘
        "tray.show": "显示主窗口",
        "tray.run_task": "运行任务",
        "tray.stop_all": "停止所有任务",
        "tray.quit": "退出",
        # 变量管理
        "var.title": "变量管理",
        "var.global": "全局变量",
        "var.local": "局部变量",
        "var.name": "变量名",
        "var.value": "初始值",
        "var.add": "＋ 添加",
        "var.del": "✕ 删除选中",
        "var.saved": "✅ 变量已保存",
        # Toast
        "toast.saved": "✅ 已保存",
        "toast.task_done": "✅ {} 已完成",
        "toast.task_stopped": "🛑 {} 已停止",
        "toast.force_stopped": "🛑 已强制终止: {}",
        # 清空确认
        "block.clear_confirm": "确定要清空全部 {} 个功能块吗？",
        "trigger.clear_confirm": "确定要清空全部 {} 个触发器吗？",
        # 进程列表对话框
        "proc_list.title": "选择进程 / 窗口",
        "proc_list.filter_ph": "过滤（进程名/窗口标题）",
        "proc_list.col_proc": "进程名",
        "proc_list.col_win": "窗口标题",
        "proc_list.col_pid": "PID",
        # 市场相关
        "plugin.market_btn": "插件市场",
        "settings.lang_market_btn": "语言包市场",
        # 更新对话框
        "update.title": "发现新版本",
        "update.found": "AutoFlow {latest} 已发布！",
        "update.current": "当前版本：{current}",
        "update.latest": "最新版本：{latest}",
        "update.notes": "更新说明",
        "update.btn_manual": "前往下载页",
        "update.btn_auto": "自动下载安装",
        "update.btn_ignore": "忽略此版本",
        "update.btn_later": "稍后再说",
        "update.dl_title": "下载更新",
        "update.dl_source": "选择下载源：",
        "update.dl_progress": "下载进度",
        "update.dl_done": "下载完成，即将打开安装包...",
        "update.dl_error": "下载失败",
        "update.dl_cancel": "取消",
        "update.installing": "正在启动安装程序，安装完成后请手动重启 AutoFlow...",
        # 主窗口动态文字
        "main.title": "智能自动化工具",
        "main.new_project": "新项目",
        "main.closed_project": "已关闭项目",
        "main.no_more_undo": "没有更多撤回步骤",
        "main.no_more_redo": "没有更多重做步骤",
        "main.modified": "  * 未保存  ",
        "main.history_dlg": "操作历史",
        "main.shortcut_dlg": "快捷方式已创建",
        "main.groups_dlg": "任务分组管理",
        "main.copy": "复制",
        "main.push_history.new_project": "新建项目",
        # 主题相关
        "theme.market_btn": "主题市场",
        "theme.pack_loaded": "已加载：{pack_id}",
        "theme.pack_none": "未加载整合包",
        "theme.import_btn": "导入整合包",
        "theme.export_btn": "导出整合包",
        "theme.bg_image_label": "背景图：",
        "theme.bg_opacity_label": "背景透明度：",
        "theme.bg_mode_label": "背景模式：",
        "theme.font_label": "字体：",
        # 外观 Tab 内其他字段
        "settings.grp.bg": "自定义背景",
        "settings.grp.font": "自定义字体",
        "settings.grp.theme_pack": "主题整合包",
    },

    "zh_TW": {
        # 通用
        "app.name": "AutoFlow",
        "app.subtitle": "智慧自動化工具",
        "btn.ok": "確定",
        "btn.cancel": "取消",
        "btn.save": "儲存",
        "btn.close": "關閉",
        "btn.add": "新增",
        "btn.delete": "刪除",
        "btn.rename": "重新命名",
        "btn.refresh": "重新整理",
        "btn.browse": "瀏覽",
        "btn.back": "<  返回",
        "btn.test": "測試",
        "btn.test_send": "測試發送",
        "btn.test_connect": "測試連線",
        "btn.test_ai": "🔗  測試連線",
        # 侧边栏
        "sidebar.tasks": "任務列表",
        "sidebar.new_task": "+  新建任務",
        "sidebar.new_project": "新建專案",
        "sidebar.open_project": "開啟專案",
        "sidebar.save_project": "儲存專案",
        "sidebar.save_as": "另存新檔",
        "sidebar.close_project": "關閉專案",
        "sidebar.undo": "復原  Ctrl+Z",
        "sidebar.redo": "重做  Ctrl+Y / Ctrl+Shift+Z",
        "sidebar.history": "操作歷史",
        "sidebar.var_manager": "變數管理",
        "sidebar.settings": "設定",
        "sidebar.plugins": "外掛管理",
        "plugin.title": "外掛管理",
        "plugin.back": "返回",
        "plugin.search_ph": "搜尋外掛...",
        "plugin.install_btn": "安裝外掛",
        "plugin.open_dir_btn": "外掛目錄",
        "plugin.empty_hint": "暫無外掛。請點擊「安裝外掛」從資料夾安裝。",
        "plugin.stats": "共 {total} 個外掛，已啟用 {enabled} 個",
        "plugin.dev_docs": "如何開發外掛？",
        "plugin.no_desc": "暫無描述",
        "plugin.enabled_btn": "已啟用",
        "plugin.disabled_btn": "已停用",
        "plugin.settings_btn": "設定",
        "plugin.detail_btn": "詳情",
        "plugin.load_failed": "外掛載入失敗",
        "plugin.no_settings_title": "無設定",
        "plugin.no_settings_msg": "該外掛沒有提供設定介面。",
        "plugin.author_label": "作者",
        "plugin.id_label": "外掛ID",
        "plugin.dir_label": "目錄",
        "plugin.provided_blocks": "提供的功能塊",
        "plugin.install_from_folder": "從資料夾安裝外掛",
        "plugin.install_error": "安裝失敗",
        "plugin.no_plugin_json": "所選目錄中沒有找到 plugin.json：\n{path}",
        "plugin.install_overwrite_title": "覆蓋安裝",
        "plugin.install_overwrite_msg": "外掛「{name}」已存在，是否覆蓋？",
        "plugin.install_ok_title": "安裝成功",
        "plugin.install_ok_msg": "外掛「{name}」已安裝。",
        # 設定
        "settings.title": "設定",
        "settings.general": "一般",
        "settings.project": "專案",
        "settings.email": "電子郵件",
        "settings.appearance": "外觀",
        "settings.hotkeys": "按鍵",
        "settings.advanced": "進階",
        "settings.about": "關於",
        "settings.save": "儲存設定",
        "settings.saved": "已儲存",
        "settings.saved_msg": "設定已儲存！",
        "settings.language": "介面語言",
        "settings.language.zh_CN": "簡體中文",
        "settings.language.zh_TW": "繁體中文",
        "settings.language.en_US": "English",
        "settings.language_hint": "切換後立即生效，無需重啟。",
        # 設定 - 通用
        "settings.grp.startup": "開機自啟",
        "settings.auto_start": "程式開機後自動啟動",
        "settings.auto_start_task": "啟動後自動執行任務：",
        "settings.no_task": "（不執行任何任務）",
        "settings.launch_behavior": "軟體啟動後：",
        "settings.launch_behavior.show": "開啟主介面",
        "settings.launch_behavior.minimize": "最小化至工作列",
        "settings.launch_behavior.tray": "隱藏至系統匣",
        "settings.grp.ui": "介面行為",
        "settings.minimize_to_tray": "關閉視窗時最小化到系統匣",
        "settings.show_log": "執行時顯示日誌面板",
        # 設定 - 專案
        "settings.grp.last_project": "上次專案",
        "settings.reopen_last": "啟動時自動開啟上次專案",
        "settings.grp.autosave": "自動儲存",
        "settings.autosave_enable": "啟用自動儲存",
        "settings.autosave_interval": "自動儲存間隔：",
        "settings.autosave_unit": " 秒",
        "settings.grp.undo": "復原歷史",
        "settings.max_undo": "最大復原步數：",
        "settings.undo_unit": " 步",
        "settings.undo_hint": "復原步數越多，記憶體占用越大。建議 50 步。",
        "settings.grp.screenshot": "截圖預設目錄",
        "settings.screenshot_dir": "預設儲存目錄：",
        "settings.screenshot_ph": "留空 = 系統圖片庫",
        # 設定 - 郵件
        "settings.grp.smtp": "SMTP（發送郵件）",
        "settings.grp.imap": "IMAP（接收郵件，用於觸發器）",
        "settings.smtp.server": "伺服器：",
        "settings.smtp.port": "連接埠：",
        "settings.smtp.user": "帳號：",
        "settings.smtp.pass": "密碼/授權碼：",
        "settings.smtp.ssl": "使用 SSL",
        "settings.imap.server": "伺服器：",
        "settings.imap.port": "連接埠：",
        "settings.imap.user": "帳號：",
        "settings.imap.pass": "密碼/授權碼：",
        "settings.imap.ssl": "使用 SSL",
        "settings.email_hint": "常見設定：\n  QQ郵箱 SMTP: smtp.qq.com:465  IMAP: imap.qq.com:993\n  163郵箱 SMTP: smtp.163.com:465  IMAP: imap.163.com:993\n  Outlook SMTP: smtp.office365.com:587  IMAP: outlook.office365.com:993",
        # 設定 - 外觀
        "settings.grp.lang": "介面語言",
        "settings.lang_label": "語言：",
        "settings.grp.theme": "主題",
        "settings.theme_label": "主題預設：",
        "settings.theme_hint": "切換主題後立即預覽，點擊「儲存設定」永久生效。",
        "settings.theme_follow": "跟隨系統",
        # 設定 - 按鍵
        "settings.grp.hotkeys_custom": "自訂快捷鍵",
        "settings.coord_hotkey": "座標選點確認鍵：",
        "settings.coord_hotkey_hint": "點擊功能塊裡的「📍 選點」後，將滑鼠移到目標位置，按此鍵確認座標。\n點擊輸入框後直接按下目標按鍵組合即可錄入。",
        "settings.stop_hotkey": "強制終止所有任務：",
        "settings.stop_hotkey_hint": "按下此快捷鍵立即停止所有正在執行的任務（全域有效，不需要視窗取得焦點）。\n點擊輸入框後直接按下目標按鍵組合即可錄入。",
        "settings.grp.hotkeys_ref": "內建快捷鍵（唯讀參考）",
        "settings.hotkeys.cat": "分類",
        "settings.hotkeys.key": "快捷鍵",
        "settings.hotkeys.desc": "說明",
        # 設定 - AI
        "settings.grp.ai_model": "模型設定",
        "settings.ai_provider": "服務商：",
        "settings.ai_model_name": "模型名稱：",
        "settings.ai_model_preset": "快速選擇模型：",
        "settings.ai_api_key": "API Key：",
        "settings.ai_show_key": "顯示 API Key",
        "settings.ai_base_url": "API 位址(Base URL)：",
        "settings.grp.ai_params": "預設參數",
        "settings.ai_temperature": "Temperature（創造性）：",
        "settings.ai_max_tokens": "Max Tokens（最大回覆長度）：",
        "settings.ai_temp_hint": "Temperature=0 更精確，=1 更有創意，=2 更隨機。建議 0.7。",
        "settings.grp.ai_system": "預設系統提示詞（System Prompt）",
        "settings.ai_hint": "🤖  設定 AI 大型語言模型後，可在功能塊中使用「AI 對話」和「AI 生成文字」功能。\n支援 OpenAI、DeepSeek、通義千問、Azure OpenAI 等相容 OpenAI 介面的服務。",
        # 設定 - 進階
        "settings.grp.log": "日誌",
        "settings.log_path": "日誌檔案路徑：",
        "settings.max_log_lines": "最大日誌行數：",
        # 任務
        "task.new": "新任務",
        "task.rename": "重新命名任務",
        "task.delete": "刪除任務",
        "task.run": "> 立即執行",
        "task.stop": "停止執行",
        "task.running": "正在執行",
        "task.finished": "已完成",
        "task.stopped": "已停止",
        "task.run_btn": "▶  立即執行",
        "task.stop_btn": "⏹  停止",
        "task.enabled": "啟用",
        "task.name_ph": "任務名稱",
        "task.desc_ph": "任務描述（可選）",
        "task.unnamed": "未命名任務",
        # 觸發器
        "trigger.section": "⚡ 觸發器",
        "trigger.add": "＋ 新增觸發器",
        "trigger.clear": "🗑 清空",
        "trigger.clear_tip": "清空所有觸發器",
        "trigger.empty": "尚無觸發器\n新增觸發器後任務將自動執行",
        "trigger.edit_title": "編輯觸發器：",
        "trigger.comment": "備註：",
        "trigger.comment_ph": "可選備註",
        "trigger.enabled": "啟用此觸發器",
        "trigger.copy_tip": "複製此觸發器",
        "trigger.disabled": "(已停用)",
        "trigger.hint.hotkey": "提示：如果快捷鍵與其他程式衝突，觸發可能失效，但不影響使用。",
        "trigger.hint.clipboard": "提示：程式每隔指定毫秒輪詢一次剪貼簿。使用萬用字元模式時支援 * 和 ? 萬用字元。",
        # 功能塊
        "block.add": "＋ 新增功能塊",
        "block.empty": "尚無功能塊\n點擊「＋ 新增功能塊」開始建構流程",
        "block.section": "🧱 功能塊",
        "block.clear": "🗑 清空",
        "block.clear_tip": "清空所有功能塊",
        "block.edit_title": "編輯：",
        "block.comment": "備註：",
        "block.comment_ph": "可選備註",
        "block.enabled": "啟用此塊",
        "block.copy_tip": "複製此功能塊",
        "block.disabled": "(已停用)",
        # 控件
        "widget.pick": "🎯 點選",
        "widget.list": "📋 列表",
        "widget.pick_tip": "點擊後主視窗最小化，3秒內點擊目標視窗，自動填入其標題",
        "widget.list_tip": "從行程/視窗列表中選擇",
        "widget.hotkey_ph": "點擊此處，然後按快捷鍵 (如 Ctrl+Alt+R)",
        "widget.hotkey_rec": "正在錄製…按下快捷鍵",
        "widget.window_ph": "視窗標題（留空=當前前景視窗）",
        "widget.proc_win_ph": "視窗標題或行程名稱",
        # 座標選點
        "coord.btn": "📍 選點",
        "coord.tip": "按 {} 鍵確認座標",
        "coord.counting": "{}s...",
        # 宏錄製
        "macro.start": "⏺ 開始錄製",
        "macro.stop": "⏹ 停止錄製",
        "macro.clear": "🗑 清空",
        "macro.events": "個事件",
        "macro.recording": "錄製中...",
        "macro.ready": "就緒",
        "macro.hint": "錄製滑鼠點擊與移動，回放時使用相對座標（相對於錄製起點）",
        # 主視窗對話框
        "dlg.new_task_name": "新任務名稱",
        "dlg.enter_task_name": "請輸入任務名稱：",
        "dlg.rename_task": "重新命名任務",
        "dlg.delete_task_title": "刪除任務",
        "dlg.delete_task_msg": "確定要刪除任務「{}」嗎？",
        "dlg.unsaved_title": "未儲存的變更",
        "dlg.unsaved_msg": "專案有未儲存的變更，是否儲存？",
        "dlg.no_project": "沒有開啟的專案",
        "dlg.open_project_title": "開啟專案",
        "dlg.save_project_title": "儲存專案",
        "dlg.project_filter": "AutoFlow 專案 (*.afp);;所有檔案 (*.*)",
        "dlg.error": "錯誤",
        "dlg.warning": "警告",
        "dlg.info": "提示",
        # 狀態列
        "status.ready": "就緒",
        "status.running": "執行中",
        "status.undo_count": "復原: {}/{}",
        "status.modified": "● 未儲存",
        # 系統匣
        "tray.show": "顯示主視窗",
        "tray.run_task": "執行任務",
        "tray.stop_all": "停止所有任務",
        "tray.quit": "結束",
        # 變數管理
        "var.title": "變數管理",
        "var.global": "全域變數",
        "var.local": "區域變數",
        "var.name": "變數名稱",
        "var.value": "初始值",
        "var.add": "＋ 新增",
        "var.del": "✕ 刪除選取",
        "var.saved": "✅ 變數已儲存",
        # Toast
        "toast.saved": "✅ 已儲存",
        "toast.task_done": "✅ {} 已完成",
        "toast.task_stopped": "🛑 {} 已停止",
        "toast.force_stopped": "🛑 已強制終止: {}",
        # 清空確認
        "block.clear_confirm": "確定要清空全部 {} 個功能塊嗎？",
        "trigger.clear_confirm": "確定要清空全部 {} 個觸發器嗎？",
        # 行程列表
        "proc_list.title": "選擇行程 / 視窗",
        "proc_list.filter_ph": "篩選（行程名稱/視窗標題）",
        "proc_list.col_proc": "行程名稱",
        "proc_list.col_win": "視窗標題",
        "proc_list.col_pid": "PID",
        # 市場相關
        "plugin.market_btn": "外掛市集",
        "settings.lang_market_btn": "語言包市集",
        # 更新對話框
        "update.title": "發現新版本",
        "update.found": "AutoFlow {latest} 已發布！",
        "update.current": "目前版本：{current}",
        "update.latest": "最新版本：{latest}",
        "update.notes": "更新說明",
        "update.btn_manual": "前往下載頁",
        "update.btn_auto": "自動下載安裝",
        "update.btn_ignore": "忽略此版本",
        "update.btn_later": "稍後再說",
        "update.dl_title": "下載更新",
        "update.dl_source": "選擇下載源：",
        "update.dl_progress": "下載進度",
        "update.dl_done": "下載完成，即將啟動安裝程式...",
        "update.dl_error": "下載失敗",
        "update.dl_cancel": "取消",
        "update.installing": "正在啟動安裝程式，安裝完成後請手動重啟 AutoFlow...",
        # 主視窗動態文字
        "main.title": "智慧自動化工具",
        "main.new_project": "新專案",
        "main.closed_project": "已關閉專案",
        "main.no_more_undo": "沒有更多撤回步驟",
        "main.no_more_redo": "沒有更多重做步驟",
        "main.modified": "  * 未儲存  ",
        "main.history_dlg": "操作歷史",
        "main.shortcut_dlg": "捷徑已建立",
        "main.groups_dlg": "任務分組管理",
        "main.copy": "複製",
        "main.push_history.new_project": "新建專案",
        # 主題相關
        "theme.market_btn": "主題市集",
        "theme.pack_loaded": "已載入：{pack_id}",
        "theme.pack_none": "未載入整合包",
        "theme.import_btn": "匯入整合包",
        "theme.export_btn": "匯出整合包",
        "theme.bg_image_label": "背景圖：",
        "theme.bg_opacity_label": "背景透明度：",
        "theme.bg_mode_label": "背景模式：",
        "theme.font_label": "字型：",
        # 外觀 Tab 其他
        "settings.grp.bg": "自訂背景",
        "settings.grp.font": "自訂字型",
        "settings.grp.theme_pack": "主題整合包",
    },

    "en_US": {
        # General
        "app.name": "AutoFlow",
        "app.subtitle": "Smart Automation Tool",
        "btn.ok": "OK",
        "btn.cancel": "Cancel",
        "btn.save": "Save",
        "btn.close": "Close",
        "btn.add": "Add",
        "btn.delete": "Delete",
        "btn.rename": "Rename",
        "btn.refresh": "Refresh",
        "btn.browse": "Browse",
        "btn.back": "<  Back",
        "btn.test": "Test",
        "btn.test_send": "Test Send",
        "btn.test_connect": "Test Connection",
        "btn.test_ai": "🔗  Test Connection",
        # Sidebar
        "sidebar.tasks": "Tasks",
        "sidebar.new_task": "+  New Task",
        "sidebar.new_project": "New Project",
        "sidebar.open_project": "Open Project",
        "sidebar.save_project": "Save Project",
        "sidebar.save_as": "Save As",
        "sidebar.close_project": "Close Project",
        "sidebar.undo": "Undo  Ctrl+Z",
        "sidebar.redo": "Redo  Ctrl+Y / Ctrl+Shift+Z",
        "sidebar.history": "History",
        "sidebar.var_manager": "Variables",
        "sidebar.settings": "Settings",
        "sidebar.plugins": "Plugins",
        "plugin.title": "Plugin Manager",
        "plugin.back": "Back",
        "plugin.search_ph": "Search plugins...",
        "plugin.install_btn": "Install Plugin",
        "plugin.open_dir_btn": "Plugin Folder",
        "plugin.empty_hint": "No plugins found. Click 'Install Plugin' to install from a folder.",
        "plugin.stats": "{total} plugin(s), {enabled} enabled",
        "plugin.dev_docs": "How to develop plugins?",
        "plugin.no_desc": "No description",
        "plugin.enabled_btn": "Enabled",
        "plugin.disabled_btn": "Disabled",
        "plugin.settings_btn": "Settings",
        "plugin.detail_btn": "Details",
        "plugin.load_failed": "Plugin Load Failed",
        "plugin.no_settings_title": "No Settings",
        "plugin.no_settings_msg": "This plugin does not provide a settings UI.",
        "plugin.author_label": "Author",
        "plugin.id_label": "Plugin ID",
        "plugin.dir_label": "Directory",
        "plugin.provided_blocks": "Provided Blocks",
        "plugin.install_from_folder": "Install Plugin From Folder",
        "plugin.install_error": "Installation Failed",
        "plugin.no_plugin_json": "No plugin.json found in selected folder:\n{path}",
        "plugin.install_overwrite_title": "Overwrite Plugin",
        "plugin.install_overwrite_msg": "Plugin '{name}' already exists. Overwrite?",
        "plugin.install_ok_title": "Installed",
        "plugin.install_ok_msg": "Plugin '{name}' has been installed.",
        # Settings
        "settings.title": "Settings",
        "settings.general": "General",
        "settings.project": "Project",
        "settings.email": "Email",
        "settings.appearance": "Appearance",
        "settings.hotkeys": "Hotkeys",
        "settings.advanced": "Advanced",
        "settings.about": "About",
        "settings.save": "Save Settings",
        "settings.saved": "Saved",
        "settings.saved_msg": "Settings saved!",
        "settings.language": "Language",
        "settings.language.zh_CN": "简体中文",
        "settings.language.zh_TW": "繁體中文",
        "settings.language.en_US": "English (US)",
        "settings.language_hint": "Changes take effect immediately, no restart needed.",
        # Settings - General
        "settings.grp.startup": "Startup",
        "settings.auto_start": "Launch AutoFlow at system startup",
        "settings.auto_start_task": "Auto-run task on launch:",
        "settings.no_task": "(Do not run any task)",
        "settings.launch_behavior": "After launch:",
        "settings.launch_behavior.show": "Show main window",
        "settings.launch_behavior.minimize": "Minimize to taskbar",
        "settings.launch_behavior.tray": "Hide to system tray",
        "settings.grp.ui": "UI Behavior",
        "settings.minimize_to_tray": "Minimize to tray on close",
        "settings.show_log": "Show log panel while running",
        # Settings - Project
        "settings.grp.last_project": "Last Project",
        "settings.reopen_last": "Reopen last project on startup",
        "settings.grp.autosave": "Auto Save",
        "settings.autosave_enable": "Enable auto save",
        "settings.autosave_interval": "Interval:",
        "settings.autosave_unit": " sec",
        "settings.grp.undo": "Undo History",
        "settings.max_undo": "Max undo steps:",
        "settings.undo_unit": " steps",
        "settings.undo_hint": "More undo steps = more memory. 50 is recommended.",
        "settings.grp.screenshot": "Screenshot Directory",
        "settings.screenshot_dir": "Default save path:",
        "settings.screenshot_ph": "Empty = system Pictures folder",
        # Settings - Email
        "settings.grp.smtp": "SMTP (Send Mail)",
        "settings.grp.imap": "IMAP (Receive Mail, for triggers)",
        "settings.smtp.server": "Server:",
        "settings.smtp.port": "Port:",
        "settings.smtp.user": "Username:",
        "settings.smtp.pass": "Password / App password:",
        "settings.smtp.ssl": "Use SSL",
        "settings.imap.server": "Server:",
        "settings.imap.port": "Port:",
        "settings.imap.user": "Username:",
        "settings.imap.pass": "Password / App password:",
        "settings.imap.ssl": "Use SSL",
        "settings.email_hint": "Common configs:\n  Gmail SMTP: smtp.gmail.com:465  IMAP: imap.gmail.com:993\n  Outlook SMTP: smtp.office365.com:587  IMAP: outlook.office365.com:993",
        # Settings - Appearance
        "settings.grp.lang": "Interface Language",
        "settings.lang_label": "Language:",
        "settings.grp.theme": "Theme",
        "settings.theme_label": "Theme preset:",
        "settings.theme_hint": "Preview updates instantly. Click 'Save Settings' to make it permanent.",
        "settings.theme_follow": "Follow System",
        # Settings - Hotkeys
        "settings.grp.hotkeys_custom": "Custom Hotkeys",
        "settings.coord_hotkey": "Coord picker confirm key:",
        "settings.coord_hotkey_hint": "After clicking 📍 Pick Point in a block, move your mouse to the target, then press this key to confirm.\nClick the input box and press the desired key combination to record it.",
        "settings.stop_hotkey": "Force stop all tasks:",
        "settings.stop_hotkey_hint": "Press this hotkey to immediately stop all running tasks (global, works without window focus).\nClick the input box and press the desired key combination to record it.",
        "settings.grp.hotkeys_ref": "Built-in Hotkeys (read-only)",
        "settings.hotkeys.cat": "Category",
        "settings.hotkeys.key": "Shortcut",
        "settings.hotkeys.desc": "Description",
        # Settings - AI
        "settings.grp.ai_model": "Model Configuration",
        "settings.ai_provider": "Provider:",
        "settings.ai_model_name": "Model name:",
        "settings.ai_model_preset": "Quick select model:",
        "settings.ai_api_key": "API Key:",
        "settings.ai_show_key": "Show API Key",
        "settings.ai_base_url": "API Base URL:",
        "settings.grp.ai_params": "Default Parameters",
        "settings.ai_temperature": "Temperature (creativity):",
        "settings.ai_max_tokens": "Max Tokens (reply length):",
        "settings.ai_temp_hint": "Temperature=0 for precise, =1 for creative, =2 for random. 0.7 recommended.",
        "settings.grp.ai_system": "Default System Prompt",
        "settings.ai_hint": "🤖  Configure an AI model to use 'AI Chat' and 'AI Generate Text' blocks.\nSupports OpenAI, DeepSeek, Qwen, Azure OpenAI and any OpenAI-compatible API.",
        # Settings - Advanced
        "settings.grp.log": "Logs",
        "settings.log_path": "Log file path:",
        "settings.max_log_lines": "Max log lines:",
        # Tasks
        "task.new": "New Task",
        "task.rename": "Rename Task",
        "task.delete": "Delete Task",
        "task.run": "> Run Now",
        "task.stop": "Stop",
        "task.running": "Running",
        "task.finished": "Finished",
        "task.stopped": "Stopped",
        "task.run_btn": "▶  Run Now",
        "task.stop_btn": "⏹  Stop",
        "task.enabled": "Enabled",
        "task.name_ph": "Task name",
        "task.desc_ph": "Task description (optional)",
        "task.unnamed": "Unnamed Task",
        # Triggers
        "trigger.section": "⚡ Triggers",
        "trigger.add": "＋ Add Trigger",
        "trigger.clear": "🗑 Clear",
        "trigger.clear_tip": "Clear all triggers",
        "trigger.empty": "No triggers yet\nAdd a trigger to run this task automatically",
        "trigger.edit_title": "Edit Trigger: ",
        "trigger.comment": "Comment:",
        "trigger.comment_ph": "Optional comment",
        "trigger.enabled": "Enable this trigger",
        "trigger.copy_tip": "Copy this trigger",
        "trigger.disabled": "(disabled)",
        "trigger.hint.hotkey": "Note: If the hotkey conflicts with another program, it may fail to trigger, but won't affect other usage.",
        "trigger.hint.clipboard": "Note: The app polls clipboard at the specified interval (ms). Wildcard mode supports * and ? wildcards.",
        # Blocks
        "block.add": "＋ Add Block",
        "block.empty": "No blocks yet\nClick '＋ Add Block' to start",
        "block.section": "🧱 Blocks",
        "block.clear": "🗑 Clear",
        "block.clear_tip": "Clear all blocks",
        "block.edit_title": "Edit: ",
        "block.comment": "Comment:",
        "block.comment_ph": "Optional comment",
        "block.enabled": "Enable this block",
        "block.copy_tip": "Copy this block",
        "block.disabled": "(disabled)",
        # Widgets
        "widget.pick": "🎯 Pick",
        "widget.list": "📋 List",
        "widget.pick_tip": "Click to minimize window, then click the target window within 3s to fill in its title",
        "widget.list_tip": "Select from process/window list",
        "widget.hotkey_ph": "Click here, then press hotkey (e.g. Ctrl+Alt+R)",
        "widget.hotkey_rec": "Recording… press hotkey",
        "widget.window_ph": "Window title (empty = current foreground window)",
        "widget.proc_win_ph": "Window title or process name",
        # Coord picker
        "coord.btn": "📍 Pick Point",
        "coord.tip": "Press {} to confirm coordinates",
        "coord.counting": "{}s...",
        # Macro recorder
        "macro.start": "⏺ Record",
        "macro.stop": "⏹ Stop",
        "macro.clear": "🗑 Clear",
        "macro.events": " events",
        "macro.recording": "Recording...",
        "macro.ready": "Ready",
        "macro.hint": "Records mouse clicks and movements. Playback uses relative coordinates from the recording origin.",
        # Main window dialogs
        "dlg.new_task_name": "New Task Name",
        "dlg.enter_task_name": "Enter task name:",
        "dlg.rename_task": "Rename Task",
        "dlg.delete_task_title": "Delete Task",
        "dlg.delete_task_msg": "Delete task '{}'?",
        "dlg.unsaved_title": "Unsaved Changes",
        "dlg.unsaved_msg": "The project has unsaved changes. Save now?",
        "dlg.no_project": "No project open",
        "dlg.open_project_title": "Open Project",
        "dlg.save_project_title": "Save Project",
        "dlg.project_filter": "AutoFlow Project (*.afp);;All Files (*.*)",
        "dlg.error": "Error",
        "dlg.warning": "Warning",
        "dlg.info": "Info",
        # Status bar
        "status.ready": "Ready",
        "status.running": "Running",
        "status.undo_count": "Undo: {}/{}",
        "status.modified": "● Unsaved",
        # System tray
        "tray.show": "Show Window",
        "tray.run_task": "Run Task",
        "tray.stop_all": "Stop All Tasks",
        "tray.quit": "Quit",
        # Variable Manager
        "var.title": "Variable Manager",
        "var.global": "Global Variables",
        "var.local": "Local Variables",
        "var.name": "Name",
        "var.value": "Value",
        "var.add": "＋ Add",
        "var.del": "✕ Delete",
        "var.saved": "✅ Variables saved",
        # Toast
        "toast.saved": "✅ Saved",
        "toast.task_done": "✅ {} done",
        "toast.task_stopped": "🛑 {} stopped",
        "toast.force_stopped": "🛑 Force stopped: {}",
        # Confirmation dialogs
        "block.clear_confirm": "Clear all {} blocks?",
        "trigger.clear_confirm": "Clear all {} triggers?",
        # Process list
        "proc_list.title": "Select Process / Window",
        "proc_list.filter_ph": "Filter (process name / window title)",
        "proc_list.col_proc": "Process",
        "proc_list.col_win": "Window Title",
        "proc_list.col_pid": "PID",
        # Marketplace
        "plugin.market_btn": "Plugin Market",
        "settings.lang_market_btn": "Language Market",
        # Update dialog
        "update.title": "New Version Available",
        "update.found": "AutoFlow {latest} is available!",
        "update.current": "Current version: {current}",
        "update.latest": "Latest version: {latest}",
        "update.notes": "Release Notes",
        "update.btn_manual": "Go to Download Page",
        "update.btn_auto": "Auto Download & Install",
        "update.btn_ignore": "Ignore This Version",
        "update.btn_later": "Remind Me Later",
        "update.dl_title": "Downloading Update",
        "update.dl_source": "Select download source:",
        "update.dl_progress": "Download Progress",
        "update.dl_done": "Download complete, launching installer...",
        "update.dl_error": "Download failed",
        "update.dl_cancel": "Cancel",
        "update.installing": "Launching installer... Please restart AutoFlow after installation.",
        # Main window dynamic text
        "main.title": "Smart Automation Tool",
        "main.new_project": "New Project",
        "main.closed_project": "Project closed",
        "main.no_more_undo": "Nothing left to undo",
        "main.no_more_redo": "Nothing left to redo",
        "main.modified": "  * Unsaved  ",
        "main.history_dlg": "Action History",
        "main.shortcut_dlg": "Shortcut Created",
        "main.groups_dlg": "Task Groups",
        "main.copy": "Copy",
        "main.push_history.new_project": "New Project",
        # Theme related
        "theme.market_btn": "Theme Market",
        "theme.pack_loaded": "Loaded: {pack_id}",
        "theme.pack_none": "No theme pack loaded",
        "theme.import_btn": "Import Pack",
        "theme.export_btn": "Export Pack",
        "theme.bg_image_label": "Background:",
        "theme.bg_opacity_label": "Opacity:",
        "theme.bg_mode_label": "Mode:",
        "theme.font_label": "Font:",
        # Appearance tab extras
        "settings.grp.bg": "Custom Background",
        "settings.grp.font": "Custom Font",
        "settings.grp.theme_pack": "Theme Pack",
    },
}

# 当前语言（默认简体中文）
_current_lang: str = "zh_CN"

# ─── 语言变更观察者列表 ───
# 每个元素为 callable()，语言切换时依次调用
_lang_observers: list = []


def add_language_observer(callback) -> None:
    """注册语言变更回调（弱引用安全：用 try/except 处理已销毁对象）"""
    if callback not in _lang_observers:
        _lang_observers.append(callback)


def remove_language_observer(callback) -> None:
    """注销语言变更回调"""
    try:
        _lang_observers.remove(callback)
    except ValueError:
        pass


def set_language(lang: str):
    """设置当前语言（zh_CN / zh_TW / en_US），并通知所有已注册的 UI 刷新回调"""
    global _current_lang
    if lang == _current_lang:
        return
    # 注册新语言（若 Language 目录已有则无需处理，否则忽略）
    if lang not in _TRANSLATIONS:
        return
    _current_lang = lang
    # 通知所有 UI 观察者刷新文字
    dead = []
    for cb in list(_lang_observers):
        try:
            cb()
        except Exception:
            dead.append(cb)
    for cb in dead:
        remove_language_observer(cb)


def get_language() -> str:
    return _current_lang


def tr(key: str, *args, default: str = None) -> str:
    """获取翻译文本，支持 .format() 占位符
    
    Args:
        key: 翻译键
        *args: format 占位符参数
        default: 找不到翻译时的默认值（不传则回退到 zh_CN，再无则返回 key）
    """
    lang_dict = _TRANSLATIONS.get(_current_lang, _TRANSLATIONS["zh_CN"])
    fallback = default if default is not None else key
    text = lang_dict.get(key, _TRANSLATIONS["zh_CN"].get(key, fallback))
    if args:
        try:
            text = text.format(*args)
        except Exception:
            pass
    return text


def get_available_languages() -> list:
    """返回可用语言列表 [(code, display_name), ...]，包含内置 + 外部语言包"""
    builtin = [
        ("zh_CN", "简体中文"),
        ("zh_TW", "繁體中文"),
        ("en_US", "English (US)"),
    ]
    # 合并外部语言包的语言（已通过 load_language_dir 注册到 _TRANSLATIONS）
    builtin_codes = {c for c, _ in builtin}
    extra = []
    for code in _TRANSLATIONS:
        if code not in builtin_codes:
            # 尝试从翻译字典里找 display name，否则用 code
            d = _TRANSLATIONS[code]
            name = d.get(f"settings.language.{code}", code)
            extra.append((code, name))
    return builtin + extra


def load_language_dir(lang_dir: str):
    """
    从目录加载外部语言包文件（JSON 格式）。
    文件名即语言代码，例如 ja_JP.json → 注册为 "ja_JP"。
    JSON 格式：{"key": "translated_text", ...}
    已存在的内置语言也可以通过外部文件覆盖/扩展。
    """
    if not os.path.isdir(lang_dir):
        return
    for fname in os.listdir(lang_dir):
        if not fname.lower().endswith(".json"):
            continue
        lang_code = fname[:-5]  # 去掉 .json
        fpath = os.path.join(lang_dir, fname)
        try:
            import json as _json
            with open(fpath, "r", encoding="utf-8") as f:
                data = _json.load(f)
            if isinstance(data, dict):
                if lang_code in _TRANSLATIONS:
                    # 覆盖/扩展已有语言
                    _TRANSLATIONS[lang_code].update(data)
                else:
                    # 注册新语言（以 zh_CN 为基础填充缺失键）
                    base = dict(_TRANSLATIONS.get("zh_CN", {}))
                    base.update(data)
                    _TRANSLATIONS[lang_code] = base
        except Exception:
            pass

# AutoFlow 版本信息
# 更新历史：
#   v1.0.0  基础版本（任务编辑器/触发器/执行引擎/日志/托盘）
#   v1.1.0  截图/邮件修复 + 打包流程修复（PyInstaller spec/icon/编码）
#   v1.2.0  浅色主题/日志主题/亚克力透明度修复
#   v1.3.0  剪贴板触发器 + 关闭前台窗口功能块
#   v1.4.0  复制按钮/窗口选择器/8个新触发器/15个新功能块/亚克力穿透修复
#   v1.5.0  约束条件系统（完整）
#   v1.6.0  亚克力拖拽漂移修复（WM_NCHITTEST 原生处理）+ 约束系统收尾
#   v1.6.3  网络连通性/窗口失焦触发器 + 执行命令/关闭显示器功能块 + BUG修复
#   v1.7.0  音量合成器(全局/进程/窗口) + 进程/窗口选择器+列表
#           + 鼠标坐标选点(实时显示+快捷键确认) + 触发器分类菜单
#           + 快捷键输入框自动捕捉 + 修复网络连通性检测触发器
#           + 任务分组(创建/删除/重命名/移入) + 任务联动功能块
#   v1.8.0  分组折叠/展开(点击分组标题行) + 条件判断完整重构(if/elif/else/end扁平结构
#           + 缩进显示 + 折叠 + 右键添加elif/else) + pycaw打包进exe
#           + 剪贴板触发器独立高频线程 + 网络连通性哨兵修复
#           + 窗口标题/进程参数全部支持点选

#   v1.9.0  删除应用&进程分类里重复的「执行命令」块
#           + 鼠标操作块坐标参数升级为 coord_picker，支持选点
#           + 坐标选点快捷键可在设置→通用→坐标选点中修改
#           + 剪贴板触发器改为「检测到复制操作」（clipboard_copy）
#           + 网络连通性触发器移除，集成到条件判断 internet_connected
#           + 条件判断新增 clipboard_contains / internet_connected 两种条件类型
#           + 关闭窗口/结束进程/等待窗口/等待进程 增加句柄(hwnd)/PID/进程名等多维识别模式
#           + 所有窗口操作块增加 match_mode: title/hwnd/process 识别方式

#   v1.9.1  修复撤回/重做/操作历史导致项目清空的 bug：
#           TaskEditorPage._load_task() 中 setText 触发 textChanged 信号 →
#           changed.emit() → _on_task_changed → _push_history 截断未来历史；
#           添加 _loading 标志，加载期间屏蔽 changed 信号。
#           修复 _restore_snapshot 遗漏恢复 task_groups。
#           修复 _restore_snapshot 后 _settings_page.config 引用旧对象。

#   v1.9.2  彻底修复撤回/重做/操作历史 bug：
#           添加 _restoring 标志，_restore_snapshot 期间完全屏蔽 _push_history。
#           _restore_snapshot 先 disconnect 旧编辑器 changed 信号再 deleteLater，
#           阻断 Qt 事件队列里残留信号触发 _push_history 截断历史。
#           _restoring 用 QTimer.singleShot(0) 延迟重置，覆盖异步事件。

#   v1.9.3  撤销/重做/操作历史还原后自动恢复到操作前选中的任务；
#           添加 Ctrl+Z（撤销）/ Ctrl+Y / Ctrl+Shift+Z（重做）全局快捷键。

#   v1.9.4  修复托盘右键退出时仍弹出"程序已最小化至托盘"通知的 bug：
#           _quit_app 先置 _quitting=True，closeEvent 检测到后直接 accept，不弹通知。

#   v1.9.6  配置文件/项目文件默认路径迁移至 %LOCALAPPDATA%\XinyuCraft\AutoFlow\ 和
#           %LOCALAPPDATA%\XinyuCraft\AutoFlow\Project\；兼容旧版自动迁移配置和检测旧默认项目。
#           侧边栏新增「另存为」按钮，保存副本并切换当前路径到新文件。
#           撤回/重做按钮显示快捷键备注（撤回 Ctrl+Z / 重做 Ctrl+Y / Ctrl+Shift+Z）。

#   v1.9.5  修复剪贴板检测：改用 GetClipboardSequenceNumber() Win32 API 检测剪贴板变化，
#           彻底解决 OpenClipboard 锁竞争导致检测失效的问题（序列号方式不需要打开剪贴板）。
#           新增触发器：Ping延迟触发器（ping_latency），当延迟超过/低于阈值或不可达时触发，
#           支持自定义主机、阈值、方向（above/below/timeout）和检测间隔。
#           新增功能块：获取连接延迟（get_ping_latency），Ping指定主机获取延迟ms值，
#           存入变量（超时/不可达时存入 -1），主机支持变量引用。
#           新增判断条件：ping_latency_gt（Ping延迟大于）和 ping_latency_lt（Ping延迟小于），
#           可在条件判断/if/elif 块中使用，target=主机, value=阈值ms。

#   v1.9.7  移除重复的「写入剪贴板」功能块（write_clipboard），
#           读写剪贴板（clipboard）图标更换为 📋，更美观。
#           移除旧版「条件判断」功能块（condition），统一使用 IF/ELIF/ELSE 扁平结构。
#           IF判断块卡片新增内嵌「＋ELIF」和「ELSE ☐/✓」按钮，
#           点击「＋ELIF」直接添加 ELIF 子判断分支；
#           点击「ELSE」开关绑定切换 ELSE 否则块（有则删除，无则添加）；
#           ELIF/ELSE 分支块卡片内嵌「✕ 删除」按钮，可直接点击删除对应分支；
#           所有 IF 系列块（if_block/elif_block/else_block/if_end）旧数据文件保持兼容。

#   v1.9.9  全面汉化所有下拉菜单选项：为所有缺少 option_labels 的 select 参数补充中文标签，
#           包含：循环类型、超时行为、写入模式、文件事件、变量类型、音量目标、
#           关机操作、截图模式/范围、剪贴板操作、浏览器选择、鼠标按键、拖拽键、
#           消息框按钮/图标、执行命令方式、定时类型/星期、网络事件、电池事件、
#           WiFi事件等，下拉框全部显示中文，内部 value 不变保持兼容。

#   v2.0.0  条件判断块全面汉化：if/elif/else/if_end 卡片标题由英文改为中文；
#           「if」→「如果」、「elif」→「否则如果」、「else」→「否则」、「end if」→「结束判断」；
#           「NOT」→「非」；condition_type 原始值（如 process_exists）映射为中文标签（如「进程存在」）；
#           新增 _ctype_to_label() 工具函数，查询 BLOCK_PARAMS option_labels 实现自动映射。

#   v2.1.0  修复浅色主题功能块颜色（BlockCard 动态感知 QPalette 深浅色）；
#           修复剪贴板触发器内容识别（TriggerMonitor.get_trigger_vars 将剪贴板内容
#           作为初始变量传入 TaskRunner）；
#           新增全局变量 vs 局部变量分离：Project.global_variables 全局共享，
#           Task.variables 为局部初始值；运行时全局变量注入 runner；
#           新增变量管理对话框（侧边栏「变量管理」按钮），可查看/添加/删除
#           全局变量和各任务的局部变量；
#           修复关于页版本号同步（动态读取 VERSION），
#           补充出品公司/开发者/策划/第三方技术信息。

#   v2.3.0  新建/打开/保存/另存为/关闭项目以及新建任务均添加快捷键
#           （Ctrl+N/O/S/Ctrl+Shift+S/Ctrl+W/Ctrl+T），侧边栏按钮显示对应快捷键提示；
#           触发器列表和功能块列表各新增「🗑 清空」按钮，带二次确认弹窗防误操作；
#           设置页新增「按键」Tab，汇总所有自定义快捷键（坐标选点/强制终止）及
#           内置固定快捷键只读参考表；原「通用」Tab 中的快捷键设置已迁移至「按键」Tab。

#   v2.4.0  新增首次使用免责声明弹窗（需勾选同意才能进入程序）；
#           新增多步骤卡片式新手引导（首次使用后自动弹出）；
#           设置页新增「AI」Tab：支持 OpenAI/DeepSeek/通义千问/Azure 等兼容接口，
#           可配置 API Key、Base URL、模型名称、Temperature、Max Tokens、默认系统提示词；
#           新增功能块「AI 对话」（ai_chat）：发送消息给 AI，支持连续对话/历史记录、变量存储；
#           新增功能块「AI 生成文本」（ai_generate）：根据提示词生成文本，结果存入变量；
#           执行命令功能块内嵌「AI 智能生成命令」选项：填写任务描述自动生成 Shell 命令。

#   v2.4.1  修复：任务控制分类补回缺失的「运行任务」功能块（run_task 已在 BLOCK_PARAMS 中定义，
#           但 BLOCK_TYPES 中遗漏）；重新实现变量管理（由弹窗改为内嵌页 VarManagerPage，
#           与设置页相同的进入/退出模式，彻底解决闪退问题）；变量管理现在在
#           返回时自动保存，无需额外确认。


#   v2.4.2  修复变量管理返回按钮闪退（_on_back 中 saved→back_requested 信号链重入，
#           改用 _saving 标志防重入 + QTimer.singleShot(0) 异步发出 back_requested）；
#           变量系统升级：数据格式升级为 {name: {value, type}}（向下兼容旧格式）；
#           变量管理页新增「类型」列（字符串/数字/布尔值/列表），列1为 QComboBox；
#           runner._coerce_vars() 初始化时按类型自动转换（list 支持 JSON 解析或逗号分隔）。

#   v2.4.3  彻底修复变量管理返回闪退（改为 _do_var_save 直接调用，完全绕开信号链，
#           _back_from_var_manager 串行执行保存→跳转，无任何重入风险）；
#           修复语言切换无效（切换语言后保存时弹出询问框，选「立即重启」直接重启）；
#           新增「重启工具」功能（托盘右键菜单加入 🔄 重启工具，
#           QProcess.startDetached 重新启动自身后退出当前进程）。

#   v2.4.4  彻底修复变量管理保存/返回闪退（_do_var_save 不再调用 _push_history，
#           避免其内部遍历 editor.save_to_task() 触发重入崩溃；改为只调用 _mark_modified）；
#           修复重启弹两个错误窗口（PyInstaller 下 sys.executable 指向 _MEI 临时目录，
#           改用 sys.argv[0] 获取 exe 真实路径，开发环境下自动回落到 sys.executable+.py）；
#           去掉托盘「重启工具」菜单的 emoji。

#   v2.4.5  终极修复变量管理保存/返回闪退：VarManagerPage 彻底移除 saved 信号，
#           改为 MainWindow 通过 set_save_callback() 注入纯函数回调；
#           保存按钮直接调用回调，返回按钮直接发出 back_requested，全程无信号重入。
#           重启功能改为临时 bat 脚本方案：写临时 bat → 轮询等待当前进程退出 → 
#           自动启动 exe → bat 自删，彻底解决 PyInstaller 下的 encodings 报错和托盘图标丢失问题。

#   v2.5.0  移除变量管理功能（长期存在信号重入崩溃，彻底删除）；
#           移除重启工具功能（托盘菜单/设置页/相关代码全部移除）；
#           "鼠标操作"分类改名为"键鼠操作"，"模拟按键"块从"系统"分类移入"键鼠操作"；
#           键鼠操作块新增拟人化参数：随机偏移(offset)、随机抖动(jitter)、
#           移动曲线(linear/ease_in/ease_out/ease_in_out/bezier/random)；
#           runner 实现缓动方程、贝塞尔曲线路径和随机抖动算法（60fps 平滑移动）；
#           新增功能块「键鼠宏」(keymouse_macro)：基于 pynput 录制键鼠操作，
#           使用相对坐标（比例）存储实现跨分辨率回放，支持速度倍率和重复次数；
#           block_editor 新增 MacroRecorderWidget 控件（录制/停止/预览/清空）。

#   v2.5.1  修复语言切换无效：main.py 在 QApplication 创建后、MainWindow 实例化前，
#           提前从 app_config.json 读取语言并调用 set_language()，重启后语言真正生效；
#           _on_config_changed 同时将 language 写入 app_config.json 持久化；
#           i18n.py 新增 load_language_dir() 支持从
#           %LOCALAPPDATA%\XinyuCraft\AutoFlow\Language\ 目录加载外部 JSON 语言包；
#           pynput 已集成到打包依赖（键鼠宏录制功能可正常使用）。

#   v2.5.2  彻底修复语言切换无效：_load_project 保存 app_config 时同步写入 language 字段，
#           修复了「设置语言→保存→重启后被项目文件覆盖」的根本问题；
#           AI 设置页新增 Kimi/智谱GLM/百度文心/Claude/Gemini/Ollama 等预设服务商，
#           切换服务商自动填充 Base URL + 推荐模型，新增模型快速选择下拉列表。

#   v2.5.3  语言包目录：启动时自动创建 %LOCALAPPDATA%\XinyuCraft\AutoFlow\Language\ 并写入
#           en_US.json/zh_TW.json 示例文件和 README.txt，解决用户找不到语言目录的问题；
#           主题修复：block_editor.py 新增模块级 _DARK_MODE + set_theme_dark/is_theme_dark，
#           _apply_theme 切换主题时更新全局变量，BlockItem._is_dark() 和 TriggerCard
#           均改为读此变量，彻底修复浅色主题下功能块/触发器仍显示深色背景的问题；
#           通知修复：_show_notification 改为多重降级方案（winrt→win10toast→plyer
#           →Win32 ctypes Shell_NotifyIcon→静默忽略），解决 No usable implementation 错误。

#   v2.5.4  语言切换即时生效：i18n.py 新增 Observer 机制（add/remove_language_observer），
#           set_language() 变更时通知所有注册回调；MainWindow 注册 _retranslate_ui()
#           回调，切换语言后立即刷新侧边栏所有按钮/标签文字，无需重启；
#           SettingsPage 新增 retranslate() 方法，切换后同步刷新设置标题和 Tab 标签；
#           任务删除同步修复：SettingsPage 新增 refresh_tasks() 方法，删除/新建/复制
#           任务后立即刷新「启动后自动运行任务」下拉框，打开设置时也自动刷新。

#   v2.6.0  全局语言切换全面覆盖：
#           - task_editor.py：所有静态文字用 tr()，注册语言观察者，添加 retranslate()；
#           - trigger_editor.py：TriggerListWidget/TriggerCard/TriggerEditDialog 全面使用 tr()，
#             TriggerListWidget 添加 retranslate()；
#           - block_editor.py：HotkeyEdit/WindowPickerEdit/ProcessWindowPickerEdit/
#             BlockCard/BlockEditDialog/ProcessWindowListDialog/BlockListWidget
#             全部使用 tr()，BlockListWidget 添加 retranslate()；
#           - settings_page.py：retranslate() 全面扩展，覆盖所有 GroupBox/CheckBox/
#             Label/按钮，所有 Tab 的 FormRow 标签同步改用 tr()；
#           - i18n.py：zh_TW 和 en_US 补充大量缺失翻译键（共 200+ 新键），
#             新增 block.clear_confirm / trigger.clear_confirm 等键。

#   v2.7.0  插件生态系统（Plugin Ecosystem）：
#           - src/plugin_api.py：插件 API 接口定义（AutoFlowPlugin 基类、
#             BlockExecutionContext、PluginRegistrationAPI）；
#           - src/plugin_manager.py：插件管理器单例（scan/load_all/unload_plugin、
#             启用/禁用状态持久化到 plugin_state.json、插件 BLOCK_TYPES/BLOCK_PARAMS 注入）；
#           - src/ui/plugin_page.py：插件管理器 UI 页面（PluginManagerPage + PluginCard），
#             支持搜索、启用/禁用、从文件夹安装、查看详情、打开插件目录；
#           - src/engine/runner.py：_execute_block 末尾新增插件功能块执行分支，
#             通过 PluginManager.get_executor() 调用插件注册的 executor；
#           - src/ui/main_window.py：侧边栏新增「🔌 插件管理」按钮，
#             启动后 300ms 延迟异步加载所有已启用插件；
#           - plugins/example_tools/：内置示例插件（随机整数/文本处理/HTTP GET JSON），
#             可作为插件开发模板，展示完整的 plugin.json + register(api) 模式；
#           - i18n.py：新增 plugin.* 共 30 个翻译键（zh_CN/zh_TW/en_US 全覆盖）。
#   v2.8.0  集成 browser-use AI 浏览器自动化：
#           - 新增「AI 浏览器自动化」(browser_auto) 功能块，归属 AI 分类；
#             支持自然语言任务描述、LLM 驱动选择（跟随设置/OpenAI/Claude/Gemini/DeepSeek）、
#             无头模式、最大步数、超时、结果&历史存变量；
#           - runner._browser_auto() 使用 browser-use + langchain 执行异步任务，兼容 Qt 线程环境；
#           - 设置→AI Tab 新增「浏览器自动化」配置区：安装状态检测、一键安装 browser-use、
#             一键安装 Chromium（playwright install chromium）；
#           - 关于页新增「开源致谢」区块，注明 browser-use 项目地址/作者/许可证；
#           - 修复 launch_app 在 BLOCK_TYPES 重复定义（行27/行78 冲突）；
#           - 项目：https://github.com/browser-use/browser-use（MIT License）

#   v2.9.0  完善触发器与约束系统，全面改进 UI 交互：
#           - 新增「开机完成」触发器 (system_boot)：通过 psutil.boot_time() 检测系统启动时间，
#             在开机后延迟 N 秒触发一次，避免监控器重启时误触发；
#           - trigger_monitor._eval_one_constraint() 全面扩展：新增 clipboard_contains、
#             capslock_on、cpu_above、memory_above、battery_below、battery_charging、
#             time_between、day_of_week、ping_latency_gt/lt、internet_connected 等约束条件；
#           - 触发器列表新增多选功能：复选框模式切换按钮（☑），支持全选/取消全选/
#             批量复制/批量删除，Ctrl+A/Ctrl+C/Delete/Ctrl+X 快捷键；
#           - 触发器卡片新增拖拽排序（QDrag/QMimeData），支持鼠标拖动重排序；
#           - 触发器卡片新增右键菜单：编辑/复制/上移/下移/删除；
#           - 触发器摘要长度限制：超 55 字符自动截断加 … 省略；
#           - 新增 system_boot 触发器的摘要显示「开机后延迟 Ns 触发」；
#           - 全新 Logo 设计：六边形渐变背景 + 白色闪电 + 右下角齿轮，
#             纯 Python 生成（无需 Pillow），多尺寸 ICO（16/32/48/64/128/256px）；
#           - main.py 在启动时加载 assets/autoflow.ico 作为应用窗口图标。

#   v2.9.1  新增「AI 智能生成功能块」功能：
#           - BlockListWidget 工具栏新增「✨ AI 生成」按钮；
#           - 弹出 AiBlockGeneratorDialog 对话框，用户输入自然语言任务描述；
#           - AI（基于 OpenAI 兼容接口）解析描述并返回结构化 JSON 功能块序列；
#           - 支持预览生成结果（彩色列表，含类型/参数/注释），确认后一键插入；
#           - 支持插入到末尾或开头两种位置；
#           - 内置精细 system prompt，覆盖全部 30+ 功能块类型及参数规范；
#           - 自动处理 if_block/loop 配对结构、参数填充、JSON 容错解析。

#   v2.9.2  launch_app「打开应用/文件」功能块路径输入优化：
#           - 新增 AppLauncherPickerWidget 复合控件（路径输入框 + 📂浏览 + 📋应用）；
#           - 「📂 浏览」按钮：弹出文件选择器，过滤 .exe/.bat/.cmd/.ps1 等可执行文件；
#           - 「📋 应用」按钮：弹出 InstalledAppChooserDialog，读取注册表（HKLM+HKCU
#             32位+64位 Uninstall 项）列出所有已安装应用，支持按名称/发行商搜索、
#             双击快速选择，显示找到路径的数量；
#           - AI 生成包含 launch_app 块时，自动弹出路径核对提醒弹窗，
#             提示用户使用 📋 应用 / 📂 浏览 按钮手动核对路径；
#           - 修复 AI 生成功能块卡死问题：AiBlockGeneratorDialog 添加跨线程信号，
#             子线程改用 emit 信号替代 QTimer.singleShot（QTimer 跨线程不可靠）；
#             API timeout 从 30 增至 90 秒。

#   v2.9.3  修复 launch_app 功能块执行时报错「missing 4 required positional arguments」：
#           runner.py 中存在两个 _launch_app 方法定义（旧版4参数@L1760 和新版8参数@L3064），
#           Python 后者覆盖前者，而第一处调用分支（L324）仍传旧4参数导致参数缺失；
#           修复：删除旧版 _launch_app 定义，将第一处调用分支改为与新版签名一致（8参数全传）。

#   v3.0.0  鼠标坐标百分比模式 + 运行此功能块 / 从此处开始运行：
#           【坐标百分比模式】
#           - CoordPickerEdit 控件新增模式切换按钮（像素 ⇆ 百分比），点击切换并自动换算当前值；
#           - 像素模式：存储整数像素坐标（原有行为，向下兼容）；
#           - 百分比模式：存储 0.0~100.0 的屏幕百分比（兼容不同分辨率），
#             选点浮层同时显示「像素坐标 + 百分比」双行信息，确认后自动换算为百分比存储；
#           - runner._resolve_coord() 新增辅助方法：读取 pos.mode 字段，
#             percent 模式运行时按当前屏幕分辨率实时换算为像素坐标；
#           - 全面适配 mouse_move/mouse_click_pos/mouse_scroll/mouse_drag 四个块；
#           【运行此功能块 / 从此处开始运行】
#           - BlockListWidget 新增 run_single_block(Block) / run_from_block(int) 两个信号；
#           - 右键菜单「▶ 运行此功能块」：创建仅含该块的临时 Task（id=__single__<task_id>）
#             并启动独立 TaskRunner 线程执行，状态栏显示「单块运行: xxx → block_type」；
#           - 右键菜单「▶▶ 从此处开始运行」：截取从目标块起的所有块，
#             创建临时 Task（id=__from__<task_id>）并启动独立 TaskRunner 线程，
#             状态栏显示「从第N块运行: xxx」；
#           - TaskEditorPage 新增 run_single(task_id, Block) / run_from(task_id, int) 信号；
#           - MainWindow 实现 _run_single_block / _run_from_block，先 save_to_task 获取最新块数据，
#             再创建深拷贝临时任务，共享全局变量与任务联动回调。

#   v3.0.1  修复最小化后快捷键不触发 + 新增停止录制热键配置：
#           【CoordOverlay 选点 F9 修复】
#           - 原因：_start_pick() 先最小化主窗口再 show overlay，导致 overlay 被
#             Windows 连带最小化，RegisterHotKey 虽已注册但浮窗不可见/无消息泵；
#             另外多次打开选点时 RegisterHotKey ID 硬编码 1/2，同进程重复注册会失败；
#           - 修复：新增全局递增 ID 分配函数 _alloc_hotkey_ids()，每次实例化分配唯一 ID；
#             _start_pick() 改为先 show overlay、再延迟 100ms 最小化主窗口，
#             确保 overlay 完全显示且热键已注册后再隐藏主窗口；
#           【键鼠宏录制停止 F10 修复】
#           - 原因：pynput keyboard.Listener 的 on_key_press 在主窗口最小化/失焦后
#             可能无法正常接收系统热键（取决于平台钩子权限）；
#           - 修复：录制开始时额外启动 _start_stop_hotkey_watcher() 后台线程，
#             用 Win32 RegisterHotKey + GetMessage 独立监听停止热键，最小化后仍有效；
#             pynput listener 仅负责录制普通按键，不再处理停止逻辑；
#           【设置→按键 Tab 补全停止录制热键配置项】
#           - 新增「停止录制热键」输入框（默认 F10），写入 AppConfig.macro_stop_hotkey；
#           - 加载/保存项目时同步到 MacroRecorderWidget.stop_hotkey 类属性；
#           【鼠标点击修复（一并收录）】
#           - _mouse_click_pos() 在每次 DOWN/UP 事件前额外调用 SetCursorPos(tx, ty)，
#             确保光标精确落在目标坐标（参考键鼠宏实现）；
#
# v3.2.0   2026-03-29
#   【自动管理员提权（UAC 自动请求）】
#   - main.py 新增 _is_admin() / _relaunch_as_admin() / _check_and_elevate()；
#   - 启动时检测是否管理员：若非管理员则自动触发 UAC（ShellExecuteW runas）并退出当前进程；
#   - 用户拒绝 UAC 后弹出 Win32 MessageBoxW 说明影响，提供「继续（受限）/ 退出」选择；
#   - 支持打包 exe（sys.argv[0]）和开发环境（sys.executable + main.py）两种重启方式；
#   - 根因说明：激活/前置窗口后若目标是高权限进程，非管理员进程的 mouse_event 被
#     Windows UIPI 机制静默丢弃，必须与目标进程同等或更高权限才能注入输入事件；
#
# v3.3.0   2026-03-29
#   【browser_auto 适配 browser-use v0.12.x，修复 langchain_openai 缺失】
#   - build_llm / _build_browser_llm 全部改用 browser_use.llm 内置适配层：
#       ChatOpenAI / ChatDeepSeek / ChatAnthropic / ChatGoogle / ChatOllama
#     彻底去除对 langchain_openai / langchain_anthropic / langchain_google_genai 的依赖；
#   - run_agent / _run_task 改用 BrowserProfile(headless=...) 适配 v0.12.x API；
#   - settings_page.py 一键安装去掉 langchain 包（只安装 browser-use）；
#   - 修复一键安装/Chromium 安装后无回调（QMetaObject.invokeMethod 不可靠）：
#     在 SettingsPage 类添加 pyqtSignal 信号（_bu_install_done_sig 等），
#     安装线程直接 emit 信号，替代按名字调用槽的方式；

# v3.4.1   2026-03-29
#   【修复打包 exe 下 browser_auto 报错 No module named 'browser_use.agent.system_prompts'】
#   - 根因：PyInstaller frozen exe 中 sys.frozen=True，但系统 Python site-packages 里
#     安装有 browser_use，导致 importlib.import_module("browser_use") 意外成功，
#     程序误判为"直接执行模式"；然而 frozen 进程内 importlib.resources.files() 无法
#     访问外部包的数据文件（.md system_prompt 模板），browser_use 内部报 ModuleNotFoundError；
#   - 修复：检测 sys.frozen，打包运行时强制走子进程模式（系统 Python 执行），
#     仅源码开发模式（sys.frozen 为 False）才走直接进程内执行路径；

# v3.5.0   2026-03-29
#   【鼠标点击间隔自定义 + 约束条件智能辅助按钮】
#   - mouse_click_pos 功能块新增两个参数：
#       click_interval（多次点击间隔秒数，默认 0.12）
#       down_up_delay（按下→松开延迟秒数，默认 0.05）
#     runner.py _mouse_click_pos 改为接受这两个参数，彻底取代硬编码值；
#   - 约束条件编辑器（constraint_editor.py）全面升级：
#       · 条件卡片改为自适应高度（取消固定 38px），支持双行布局
#       · 目标输入框左侧加动态标签（随条件类型变化：进程名/路径/窗口标题/…）
#       · 目标输入框右侧加智能辅助按钮（随条件类型动态切换）：
#           file_exists    → [📁 选择] 弹出文件/目录选择菜单（资源管理器）
#           process_exists → [🖱 点选] + [📋 进程列表]（倒计时点选前台窗口进程 / 弹出进程列表对话框）
#           window_exists  → [🖱 点选]（倒计时点选前台窗口标题）
#           ping_latency_* → [🌐 本机] 快速填入 127.0.0.1
#       · 新增 _ProcessListDialog：弹出运行中的进程列表（含筛选框），双击或确认填入；

# v3.6.0   2026-03-29
#   【条件判断辅助按钮 + UI割裂修复 + 动画优化 + 性能优化】
#   - if_block/elif_block 目标输入框新增 ConditionTargetWidget：
#       · 随 condition_type 下拉动态切换标签和辅助按钮（与约束条件一致）
#       · process_exists → [🖱 点选] + [📋 进程列表]
#       · window_exists  → [🖱 点选]
#       · file_exists/changed → [📁 选择]（文件/目录菜单）
#       · ping_latency_* → [🌐 本机]（填 127.0.0.1）
#       · 无目标类型（始终为真/网络/大写锁/充电）自动隐藏目标行
#   - 全局 UI 修复（themes.py QSS）：
#       · #block_card/#trigger_card 内 QLabel/QCheckBox/QPushButton 设为 background:transparent
#       · 彻底消除卡片内文字背景与卡片背景的割裂感
#   - 动画效果补全：
#       · BlockListWidget._do_refresh() 和 TriggerListWidget._refresh() 新卡片淡入动画
#       · 复用 effects.py fade_in()，每张卡延迟 8ms 层叠出现（最多 80ms），更流畅
#   - 性能优化：
#       · BlockListWidget 新增 _refresh_timer 防抖（16ms），避免连续调用重复重建卡片
#       · _refresh() 改为防抖入口，_do_refresh() 为真正的重建逻辑

# v4.3.0   2026-03-29
#   【交互修复 + 触发器多选拖动排序】
#   - 修复功能块多选拖动与单击冲突：press 只记录起始位置，
#     move 超阈值才启动 QDrag（标记 _dragged=True），
#     release 没有拖拽才发出 card_clicked 信号，彻底消除拖拽时意外改变选中状态；
#   - 修复双击时 release 误发 click 信号：mouseDoubleClickEvent 设 _dragged=True 阻止；
#   - 触发器卡片（TriggerCard）新增双击编辑：card_double_clicked 信号 →
#     TriggerListWidget 连接到 _edit_trigger；
#   - 触发器全面支持多选+拖动排序（与功能块完全对齐）：
#       · 单击 = 单选/取消，Shift+单击 = 范围多选；
#       · _on_card_clicked / _sync_selection_ui / _anchor_trigger_id 完整多选逻辑；
#       · dropEvent 支持多选整组移动；
#       · 选中时蓝色边框+蓝色背景高亮（深/浅主题各异），_base_stylesheet 快速恢复。

# v4.3.1   2026-03-29
#   【修复点击触发器任务闪退】
#   - TriggerCard.__init__ 中 customContextMenuRequested.connect(self._show_context_menu)
#     因方法定义头漏写，导致右键菜单代码被并入 mouseReleaseEvent，
#     AttributeError: 'TriggerCard' object has no attribute '_show_context_menu'；
#   - 修复：补上 def _show_context_menu(self, pos): 方法头，将右键菜单逻辑独立为正确方法。

# v4.4.0   2026-03-29
#   【鼠标运动曲线全面升级 + 自动更新/版本检测 + GitHub 信息同步回软件】
#
#   鼠标运动曲线升级：
#     - 新增 5 种缓动曲线：ease_in_cubic（三次缓入）、ease_out_cubic（三次缓出）、
#       ease_out_back（超出回弹）、spring（弹性衰减）
#     - 「随机曲线」更名为「拟人化曲线」（humanize），算法完全重写：
#         * 基础速度采用 smoothstep（先慢→快→慢），模拟手腕加减速节奏
#         * 叠加随机控制点的二次贝塞尔弧线，避免机械直线路径
#         * 叠加低频正弦漂移（模拟手腕旋转的圆弧感），幅度随距离自适应
#         * 叠加高频微抖动（端点处收缩为 0，保证起终点精确）
#         * 非均匀步长（端点步长是中段的 2.5 倍），模拟真实加减速节奏
#     - mouse_move / mouse_drag / mouse_click_pos 三个功能块均支持全部新曲线
#
#   自动更新 / 版本检测（src/updater.py 新模块）：
#     - 启动后 5 秒静默检测 GitHub Releases（不阻塞启动，网络超时 6 秒）
#     - 发现新版本在状态栏底部显示绿色非侵入性提示链接，点击直达下载页
#     - 设置→关于 Tab 新增「检查更新」按钮，支持手动触发，实时显示检测状态
#     - 检测到新版本时显示「前往下载」按钮，自动跳转到 Release exe 直链
#     - 版本号对比基于语义版本三段整数比较（v4.3.1 格式）
#
#   GitHub 信息同步回软件：
#     - 关于页新增 GitHub / Gitee / Issues 三个可点击链接
#     - 插件页「如何开发插件」链接更新为真实 GitHub 仓库文档路径
#     - src/updater.py 统一维护所有外部链接常量（GITHUB_REPO_URL、GITEE_REPO_URL、
#       PLUGIN_DEV_DOCS_URL、ISSUES_URL、WIKI_URL 等），方便日后统一修改

# v4.5.0   2026-03-30
#   【远程公告系统】
#   - updater.py 新增 fetch_announcements() 函数：从 GitHub 仓库 docs/announcements.json
#     拉取远程公告列表，后台异步执行，不阻塞 UI
#   - AppConfig 新增 read_announcement_ids 字段：记录已读公告 ID，避免重复弹出
#   - 启动后 8 秒异步拉取公告（与更新检测错开，各自独立网络请求）
#   - _AnnouncementDialog 公告展示对话框：
#       · 支持多条公告翻页（上一条/下一条）
#       · level 颜色区分：info=蓝色 / warning=橙色 / important=红色
#       · pinned=true 的固定公告每次启动都显示；普通公告只在首次（未读）时弹出
#       · 可选「查看详情」按钮跳转外链（url 为空时自动隐藏）
#   - docs/announcements.json：运营公告数据源，推送到 GitHub master 分支后即时生效，
#     无需重新发布版本，支持远程运营/紧急通知/更新提示等场景

# v4.5.1   2026-03-30
#   【Bug 修复：检查更新卡住 + 公告不显示】
#   - 根本原因：子线程中直接调用 QTimer.singleShot() 在 PyQt6 中不安全，
#     会导致回调永远无法进入主线程事件队列，UI 卡在"正在检查更新"
#   - 修复方案：改为 pyqtSignal 信号跨线程通信（Qt 信号是线程安全的）
#       · MainWindow 新增 _update_result_sig / _announcements_result_sig 两个信号
#       · SettingsPage 新增 _update_result_sig 信号
#       · 子线程回调统一改为 self._xxx_sig.emit(result)
#   - 公告不显示：国内访问 raw.githubusercontent.com 不稳定
#     updater.py 为公告和 Release 检测均加入 Gitee 备用源（fallback 机制）：
#       · 公告：GitHub raw → 失败时 fallback Gitee raw
#       · 检测更新：GitHub API → 失败/限流时 fallback Gitee API
#     Gitee raw 和 API 均测试可用，国内用户不再受 GitHub 网络影响

# v4.6.0   2026-03-30
#   【任务列表拖动排序 + 分组管理升级 + 触发器/功能块选中互斥修复】
#   任务列表交互升级（TaskListWidget 全重写）：
#     - 支持拖动排序（MouseMove 超阈值触发 QDrag，dropEvent 发出 task_reordered 信号）；
#     - 支持多选（Shift+单击范围多选）+ 选中蓝色高亮（与功能块/触发器风格统一）；
#     - 点击空白区域清除选中；分组标题行单击切换折叠，不影响任务选中状态；
#     - _refresh_task_list 末尾调用 _sync_task_selection_ui() 恢复刷新后高亮；
#   任务分组管理：
#     - 右键空白区域：「新建分组」快速弹窗新建分组，无需打开分组管理页面；
#     - 右键任务行：「移入分组」子菜单，含「不分组」选项；
#     - 右键分组标题：「重命名分组」/ 「删除分组（任务保留）」；
#     - 分组折叠/展开状态跨刷新保持（_collapsed_groups set）；
#   触发器修复：
#     - 空白处取消选中：在 _scroll_body 安装 eventFilter，
#       MouseButtonPress 时检查点击是否落在 TriggerCard 内，否则清除选中；
#     - 触发器/功能块选中互斥：双方各加 selection_changed 信号 + clear_selection() 方法，
#       TaskEditorPage 连接 _on_trigger_selection_changed / _on_block_selection_changed 互斥；

# v4.6.1   2026-03-30
#   【插件开发文档 + GitHub Release 修复】
#   - 新增 docs/plugin-dev-guide.md：完整插件开发指南（快速开始/目录结构/功能块/触发器/
#     API 参考/示例代码/调试/发布）；修复插件管理页「如何开发插件」链接 404 问题；

# v4.6.2   2026-03-30
#   【崩溃修复 + 更新检测修复】
#   - 修复打包后启动崩溃：main_window.py 将 QMimeData 从 PyQt6.QtGui 改回正确的
#     PyQt6.QtCore（QMimeData 在 PyQt6 中属于 QtCore 模块，不属于 QtGui）；
#   - 修复「检测更新」显示旧版本：GitHub API 国内网络超时时 fallback 到 Gitee，
#     但 Gitee Release 未同步，显示 v4.3.1；现已在 Gitee 补全历史 Release；

# v4.10.0  2026-03-30
#   【更新对话框 + 市场修复 + 滚轮优化 + Bug 修复】
#   - 新增自动更新对话框（update_dialog.py）：检测到新版本时弹出对话框，
#     支持「前往下载页」/ 「自动下载安装」（选择下载源+进度条+启动安装包+关闭程序）
#     / 「忽略此版本」/ 「稍后再说」；支持 GitHub / GitHub Proxy 等多个下载源；
#   - 修复语言包/插件市场按钮显示 key 字符串（plugin.market_btn 等 key 未在 i18n 中注册）；
#   - 修复市场无法连接：改用 jsDelivr CDN 作为 GitHub raw 的备用源（国内可访问）；
#   - 修复设置页 SpinBox 滚轮误触：新增 FocusSpinBox/FocusDoubleSpinBox，
#     只有在获得输入焦点后才响应鼠标滚轮，滚动页面时不再误调数值；
#   - 修复 launch_app 无法打开 .lnk 快捷方式文件（WinError 193）：
#     对 .lnk/.bat/.cmd 等 Shell 文件改用 ShellExecuteW(open) 而非 Popen；
#   - 修复 Ping 延迟触发器断网时不触发：direction=above 时 latency=None（超时/断网）
#     视为延迟无限大，满足「超过阈值」条件，同样触发；
#   - i18n.py 新增 update.* / plugin.market_btn / settings.lang_market_btn 翻译键；
#   - Gitee 主仓库已同步（代码与 GitHub 一致）；

# v4.11.0  2026-03-30
#   【市场连接优化 + 启动行为设置】
#   - 语言包市场 / 插件市场新增 Gitee raw 第三备用源（GitHub raw → jsDelivr → Gitee），
#     解决国内 GitHub + jsDelivr 均无法访问时的连接问题；
#   - autoflow-languages / autoflow-plugins 已镜像推送至 Gitee（XinyuCraft-XYHC_admin）；
#   - 新增「软件启动后」设置项（设置→通用→开机自启分组）：
#     支持「打开主界面」/「最小化至任务栏」/「隐藏至托盘」三种模式，
#     默认「打开主界面」；--minimized 命令行参数优先级高于该设置；
#
# v4.11.1  2026-03-30
#   【市场连接彻底修复 + 插件仓库 README】
#   - 修复市场所有备用源 URL 分支名 main -> master（与实际分支一致）；
#   - 修复 Gitee 镜像仓库 private=true 导致 403 Forbidden；
#   - autoflow-plugins 仓库新增 README.md 介绍及贡献指南；
#   - 更新 docs/plugin-dev-guide.md 插件制作指南，补充插件市场发布流程；
#
# v4.11.2  2026-03-30
#   【修复自动下载安装「未找到可用下载链接」】
#   - 修复 update_dialog._build_sources：当 GitHub API 未返回 assets（download_url=None）时，
#     按固定 URL 规律（/releases/download/{tag}/{filename}）拼接直链，确保三个下载源始终可用；
#   - 原逻辑所有源都依赖 download_url 非空，导致 Gitee 备用 API 返回的 Release 缺少 assets
#     时 sources 列表为空，直接弹"未找到可用下载链接"弹窗；

VERSION       = "4.11.2"
VERSION_TUPLE = (4, 11, 2)

APP_NAME      = "AutoFlow"
FULL_NAME     = f"{APP_NAME} v{VERSION}"

# v4.1.0   2026-03-29
#   【屏幕识别 + 窗口控件操作 两大新功能分类】
#   屏幕识别（screen_* 系列，基于 pyautogui + opencv）：
#     - screen_find_image：在屏幕上查找目标图片，找到后将坐标存入变量；支持精度/区域/未找到策略
#     - screen_click_image：查找图片并直接点击；支持左/右/中键、多次点击、坐标偏移
#     - screen_wait_image：等待某图片出现在屏幕上，超时可停止任务；支持轮询间隔/坐标存储
#     - screen_screenshot_region：截取屏幕指定区域并保存；留空=全屏截图
#   窗口控件操作（win_* 系列，基于 pywinauto UIA）：
#     - win_find_window：按标题/类名/进程名查找窗口，将句柄存入变量；支持 * 通配符
#     - win_click_control：点击窗口内指定控件（按钮/复选框/菜单项等），支持双击
#     - win_input_control：向窗口内输入框输入文字，支持清空原内容
#     - win_get_control_text：读取窗口/控件文本内容，存入变量
#     - win_wait_window：等待指定窗口出现（控件级），超时可停止任务
#     - win_close_window：关闭指定窗口（通过 pywinauto 控件接口）

# v4.2.0   2026-03-29
#   【交互优化 + 多选拖动 + 任务运行最小化开关 + 多选高亮醒目化】
#   交互优化：
#     - 单击功能块：进入单选状态（高亮当前块，再次点击取消）
#     - 双击功能块：直接打开编辑器（双击触发器同理）
#     - Shift+单击：范围多选（自动扩展为连续区域）
#     - 点击空白区域：取消所有选中并退出多选模式
#   多选拖动排序：
#     - 拖动已选中的块时，所有选中块整体移动到目标位置
#     - 未选中单块拖动行为不变
#   多选高亮样式优化：
#     - 选中块显示醒目蓝色边框 + 蓝色背景色（深/浅色主题各异）
#     - 不再重建卡片 UI，直接切换 QSS，性能更优
#     - 保存 _base_stylesheet 用于取消选中时快速恢复
#   设置面板：
#     - 通用 Tab 新增「任务运行时最小化工具窗口」开关（minimize_on_run）
#     - 手动运行任务时（非触发器触发）自动最小化主窗口（200ms 延迟防闪烁）












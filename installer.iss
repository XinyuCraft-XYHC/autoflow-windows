; AutoFlow Windows 安装包脚本
; 使用 Inno Setup 6 编译
; 由 build.py 自动调用，也可手动编译：
;   C:\InnoSetup6\ISCC.exe installer.iss

; ── 版本号由 build.py 通过 /DAPP_VERSION=x.x.x 参数传入 ──
#ifndef APP_VERSION
  #define APP_VERSION "4.18.2"
#endif

#define APP_NAME        "AutoFlow"
#define APP_PUBLISHER   "XinyuCraft"
#define APP_URL         "https://github.com/XinyuCraft-XYHC/autoflow-windows"
; ✅ exe 名固定，不带版本号，更新后快捷方式和 PATH 命令无需变更
#define APP_EXE_NAME    "AutoFlow.exe"
#define APP_DIR_NAME    "AutoFlow_v" + APP_VERSION
#define INSTALLER_NAME  "AutoFlow_v" + APP_VERSION + "_Setup"

[Setup]
; 唯一 GUID（每次升级保持不变，用于检测已有安装）
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#APP_NAME}
AppVersion={#APP_VERSION}
AppPublisher={#APP_PUBLISHER}
AppPublisherURL={#APP_URL}
AppSupportURL={#APP_URL}/issues
AppUpdatesURL={#APP_URL}/releases

; 默认安装目录
DefaultDirName={autopf}\{#APP_NAME}
DefaultGroupName={#APP_NAME}
AllowNoIcons=no

; 输出安装包
OutputDir=dist
OutputBaseFilename={#INSTALLER_NAME}

; 安装包压缩（lzma2 压缩率最高）
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; 界面设置
WizardStyle=modern
WizardSizePercent=110

; 图标（固定引用 AutoFlow.exe）
SetupIconFile=assets\autoflow.ico
UninstallDisplayIcon={app}\{#APP_EXE_NAME}

; 权限设置（需要管理员，因为 AutoFlow 本身需要管理员权限）
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog

; 版本信息（用于卸载程序）
VersionInfoVersion={#APP_VERSION}
VersionInfoCompany={#APP_PUBLISHER}
VersionInfoDescription={#APP_NAME} Installer
VersionInfoProductName={#APP_NAME}
VersionInfoProductVersion={#APP_VERSION}

; 安装包内嵌许可证
LicenseFile=LICENSE

[Languages]
; 简体中文优先，英文备用
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
; ── 简体中文 ──
chinesesimplified.CreateDesktopIcon=创建桌面快捷方式(&D)
chinesesimplified.AddToPath=将 AutoFlow 添加到系统 PATH（可在命令行直接运行 AutoFlow）(&P)
chinesesimplified.LaunchAtStartup=开机时自动启动 AutoFlow(&S)
chinesesimplified.AdditionalTasks=附加任务：
chinesesimplified.LaunchAfterInstall=安装完成后立即启动 {#APP_NAME}

; ── English ──
english.CreateDesktopIcon=Create &desktop shortcut
english.AddToPath=Add AutoFlow to system &PATH (run AutoFlow from any command line)
english.LaunchAtStartup=Launch AutoFlow at Windows &startup
english.AdditionalTasks=Additional tasks:
english.LaunchAfterInstall=Launch {#APP_NAME} after installation

[Tasks]
; 桌面快捷方式：默认勾选
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalTasks}"
; 添加到 PATH：默认勾选（方便 cmd/bat 调用 AutoFlow --run-task）
Name: "addtopath"; Description: "{cm:AddToPath}"; GroupDescription: "{cm:AdditionalTasks}"
; 开机自启：默认不勾选
Name: "startupicon"; Description: "{cm:LaunchAtStartup}"; GroupDescription: "{cm:AdditionalTasks}"; Flags: unchecked

[Files]
; 把 onedir 产出的整个文件夹打包进安装包
Source: "dist\{#APP_DIR_NAME}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; 开始菜单快捷方式（固定 exe 名，升级后无需重建）
Name: "{group}\{#APP_NAME}"; Filename: "{app}\{#APP_EXE_NAME}"; WorkingDir: "{app}"
Name: "{group}\卸载 {#APP_NAME}"; Filename: "{uninstallexe}"

; 桌面快捷方式（固定 exe 名）
Name: "{autodesktop}\{#APP_NAME}"; Filename: "{app}\{#APP_EXE_NAME}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; 安装完成后可选立即运行
Filename: "{app}\{#APP_EXE_NAME}"; Description: "{cm:LaunchAfterInstall}"; Flags: nowait postinstall skipifsilent

[Registry]
; 开机自启（可选任务）
Root: HKCU; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "AutoFlow"; ValueData: """{app}\{#APP_EXE_NAME}"" --minimized"; Tasks: startupicon; Flags: uninsdeletevalue

; ── 添加到系统 PATH（用户级，可选任务）──
; 注册 {app} 到 PATH，用户可在 cmd/powershell 任意位置执行 AutoFlow --run-task <id>
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Tasks: addtopath; Flags: preservestringtype uninsdeletevalue

[UninstallDelete]
; 卸载时清理插件和临时缓存（不删除用户数据/配置/项目文件）
; 用户数据保存在 %LOCALAPPDATA%\XinyuCraft\AutoFlow，不在安装目录，卸载不受影响

[Code]
// ── 安装前检测是否有旧版本在运行，提示关闭 ──
function InitializeSetup(): Boolean;
begin
  if FindWindowByClassName('AutoFlowMainWindow') <> 0 then
  begin
    if MsgBox('检测到 AutoFlow 正在运行。' + #13#10 +
              '请先关闭 AutoFlow，然后点击「是」继续安装。' + #13#10 +
              '点击「否」取消安装。',
              mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
      Exit;
    end;
  end;
  Result := True;
end;

// ── 安装前删除旧版本程序文件（保留用户数据/配置）──
// 只删除 {app} 目录下的 .exe / .dll / .pyd / .py 程序文件和 _internal 子目录
// 不删除 plugins/ 目录（用户可能安装了第三方插件）
procedure CurStepChanged(CurStep: TSetupStep);
var
  AppPath: String;
begin
  if CurStep = ssInstall then
  begin
    AppPath := ExpandConstant('{app}');
    if DirExists(AppPath) then
    begin
      // 删除旧版带版本号的 exe（AutoFlow_v*.exe 匹配模式无法用 DelTree，逐个检查）
      // 用 FindFirst/FindNext 删除所有 AutoFlow_v*.exe 文件（旧版残留）
      DelTree(AppPath + '\__pycache__', True, True, True);
      // 删除 _internal 子目录（PyInstaller onedir 依赖目录，每次更新需全量替换）
      DelTree(AppPath + '\_internal', True, True, True);
    end;
  end;
end;

; AutoFlow Windows 安装包脚本
; 使用 Inno Setup 6 编译
; 由 build.py 自动调用，也可手动编译：
;   C:\InnoSetup6\ISCC.exe installer.iss

; ── 版本号由 build.py 通过 /DAPP_VERSION=x.x.x 参数传入 ──
#ifndef APP_VERSION
  #define APP_VERSION "4.9.0"
#endif

#define APP_NAME        "AutoFlow"
#define APP_PUBLISHER   "XinyuCraft"
#define APP_URL         "https://github.com/XinyuCraft-XYHC/autoflow-windows"
#define APP_EXE_NAME    "AutoFlow_v" + APP_VERSION + ".exe"
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

; 图标
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
chinesesimplified.LaunchAtStartup=开机时自动启动 AutoFlow(&S)
chinesesimplified.AdditionalTasks=附加任务：
chinesesimplified.LaunchAfterInstall=安装完成后立即启动 {#APP_NAME}

; ── English ──
english.CreateDesktopIcon=Create &desktop shortcut
english.LaunchAtStartup=Launch AutoFlow at Windows &startup
english.AdditionalTasks=Additional tasks:
english.LaunchAfterInstall=Launch {#APP_NAME} after installation

[Tasks]
; 桌面快捷方式：默认勾选
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalTasks}"
; 开机自启：默认不勾选
Name: "startupicon"; Description: "{cm:LaunchAtStartup}"; GroupDescription: "{cm:AdditionalTasks}"; Flags: unchecked

[Files]
; 把 onedir 产出的整个文件夹打包进安装包
Source: "dist\{#APP_DIR_NAME}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; 开始菜单快捷方式
Name: "{group}\{#APP_NAME}"; Filename: "{app}\{#APP_EXE_NAME}"; WorkingDir: "{app}"
Name: "{group}\卸载 {#APP_NAME}"; Filename: "{uninstallexe}"

; 桌面快捷方式（默认勾选）
Name: "{autodesktop}\{#APP_NAME}"; Filename: "{app}\{#APP_EXE_NAME}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; 安装完成后可选立即运行
Filename: "{app}\{#APP_EXE_NAME}"; Description: "{cm:LaunchAfterInstall}"; Flags: nowait postinstall skipifsilent

[Registry]
; 开机自启（可选任务）
Root: HKCU; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "AutoFlow"; ValueData: """{app}\{#APP_EXE_NAME}"" --minimized"; Tasks: startupicon; Flags: uninsdeletevalue

[UninstallDelete]
; 卸载时可选清理用户数据（注释掉默认不清理，保护用户项目文件）
; Type: filesandordirs; Name: "{app}\plugins"

[Code]
// 安装前检测是否有旧版本在运行，提示关闭
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

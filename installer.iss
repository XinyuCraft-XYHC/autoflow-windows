; AutoFlow Windows 安装包脚本
; 使用 Inno Setup 6 编译
; 由 build.py 自动调用，也可手动编译：
;   C:\InnoSetup6\ISCC.exe installer.iss

; ── 版本号由 build.py 通过 /DAPP_VERSION=x.x.x 参数传入 ──
#ifndef APP_VERSION
  #define APP_VERSION "4.8.0"
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
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
english.CreateDesktopIcon=Create &desktop shortcut
english.LaunchAtStartup=Launch AutoFlow at Windows &startup
english.AdditionalTasks=Additional tasks:

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalTasks}"; Flags: unchecked
Name: "startupicon"; Description: "{cm:LaunchAtStartup}"; GroupDescription: "{cm:AdditionalTasks}"; Flags: unchecked

[Files]
; 把 onedir 产出的整个文件夹打包进安装包
Source: "dist\{#APP_DIR_NAME}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; 开始菜单快捷方式
Name: "{group}\{#APP_NAME}"; Filename: "{app}\{#APP_EXE_NAME}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#APP_NAME}"; Filename: "{uninstallexe}"

; 桌面快捷方式（可选）
Name: "{autodesktop}\{#APP_NAME}"; Filename: "{app}\{#APP_EXE_NAME}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; 安装完成后可选立即运行
Filename: "{app}\{#APP_EXE_NAME}"; Description: "Launch {#APP_NAME} now"; Flags: nowait postinstall skipifsilent

[Registry]
; 开机自启（可选任务）
Root: HKCU; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "AutoFlow"; ValueData: """{app}\{#APP_EXE_NAME}"" --minimized"; Tasks: startupicon; Flags: uninsdeletevalue

[UninstallDelete]
; 卸载时清理插件目录（用户安装的插件，可选）
; Type: filesandordirs; Name: "{app}\plugins"

[Code]
// Check if AutoFlow is running before install
function InitializeSetup(): Boolean;
begin
  if FindWindowByClassName('AutoFlowMainWindow') <> 0 then
  begin
    if MsgBox('AutoFlow appears to be running.' + #13#10 +
              'Please close AutoFlow before installing, then click Yes to continue.' + #13#10 +
              'Click No to cancel installation.',
              mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
      Exit;
    end;
  end;
  Result := True;
end;

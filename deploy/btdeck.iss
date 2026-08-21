; BtDeck Inno Setup 安装脚本
; 用于创建 Windows 安装包 (.exe)
; 版本: v1.0.5

#define AppName "BtDeck"
#define AppVersion "1.0.5"
#define AppPublisher "BtDeck Team"
#define AppURL "https://github.com/strainhzj/BtDeck"
#define AppExeName "btdeck.exe"

[Setup]
AppId={{B7E3F2A1-4D56-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=BtDeck-v{#AppVersion}-windows-x64-setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=..\frontend\public\favicon.ico
UninstallDisplayIcon={app}\{#AppExeName}

[Languages]
; 简体中文为非官方语言包，需随项目分发（deploy/ChineseSimplified.isl）
; 用 compiler 前缀加载官方 Default.isl，再用中文包覆盖翻译
Name: "chinesesimplified"; MessagesFile: "compiler:Default.isl,ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startmenuicon"; Description: "Create Start Menu shortcut"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startup"; Description: "Run at Windows startup"; GroupDescription: "Auto Start"; Flags: unchecked

[Files]
; 主可执行文件（PyInstaller 输出到 dist/ 目录）
Source: "..\dist\btdeck.exe"; DestDir: "{app}"; Flags: ignoreversion
; NSSM 服务管理器（用于注册 Windows 服务，解决 SCM 协议问题）
Source: "nssm.exe"; DestDir: "{app}"; Flags: ignoreversion
; 安全修复（W12）：不再从构建机复制 backend/config/*（含开发库 app.db 与
; 真实密钥的 config.yaml）。运行时 config 由应用首启 init_config_file 自动生成。

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent; Check: ShouldLaunchAppDirectly

[Code]
var
  CustomPage: TInputOptionWizardPage;

function ShouldLaunchAppDirectly: Boolean;
begin
  Result := not CustomPage.Values[0];
end;

procedure InitializeWizard;
begin
  { 创建安装选项页 }
  CustomPage := CreateInputOptionPage(
    wpSelectDir,
    'Installation Options',
    'Select additional options',
    'Choose how BtDeck should be installed:',
    False,
    False
  );
  CustomPage.Add('Install as Windows Service (recommended)');
  CustomPage.Add('Open browser after installation');
  CustomPage.Values[0] := True;
  CustomPage.Values[1] := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    { 如果选择安装为服务 }
    if CustomPage.Values[0] then
    begin
      { 使用 NSSM 注册服务（解决 PyInstaller 控制台程序无法满足 SCM 协议的问题） }
      Exec(ExpandConstant('{app}\nssm.exe'), 'install BtDeck "' + ExpandConstant('{app}\{#AppExeName}') + '"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      Exec(ExpandConstant('{app}\nssm.exe'), 'set BtDeck AppDirectory "' + ExpandConstant('{app}') + '"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      Exec(ExpandConstant('{app}\nssm.exe'), 'set BtDeck Description "BtDeck - BitTorrent Management Platform"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      Exec(ExpandConstant('{app}\nssm.exe'), 'set BtDeck Start SERVICE_AUTO_START', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      Exec(ExpandConstant('{app}\nssm.exe'), 'start BtDeck', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    { 使用 NSSM 停止服务 }
    Exec(ExpandConstant('{app}\nssm.exe'), 'stop BtDeck', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    { 卸载前终止所有 btdeck 进程（含服务进程和手动启动的实例），
      避免文件被占用导致 exe 无法删除 }
    Exec('taskkill', '/im btdeck.exe /f /t', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Sleep(2000);
    { 必须在 usUninstall 阶段删除服务条目：usPostUninstall 时 nssm.exe
      已被卸载器删除，那时 remove 必然失败并残留孤儿服务 }
    Exec(ExpandConstant('{app}\nssm.exe'), 'remove BtDeck confirm', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;

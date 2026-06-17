; BtDeck Inno Setup 安装脚本
; 用于创建 Windows 安装包 (.exe)
; 版本: v1.0.9

#define AppName "BtDeck"
#define AppVersion "1.0.9"
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
; 配置文件模板
Source: "..\backend\config\*"; DestDir: "{app}\config"; Flags: ignoreversion recursesubdirs createallsubdirs; Check: not FileExists('{app}\config\config.yaml')

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
var
  CustomPage: TInputOptionWizardPage;

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
      { 使用 NSSM 或 WinSW 注册服务 }
      Exec('sc', 'create BtDeck binPath= "' + ExpandConstant('{app}\{#AppExeName}') + '" start= auto', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      Exec('sc', 'description BtDeck "BtDeck - BitTorrent Management Platform"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      Exec('sc', 'start BtDeck', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    { 卸载前终止所有 btdeck 进程（含服务进程和手动启动的实例），
      避免文件被占用导致 exe 无法删除 }
    Exec('taskkill', '/im btdeck.exe /f /t', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Sleep(2000);
  end;

  if CurUninstallStep = usPostUninstall then
  begin
    { 停止并删除服务 }
    Exec('sc', 'stop BtDeck', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec('sc', 'delete BtDeck', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;

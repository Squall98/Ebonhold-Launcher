; Build : python -m PyInstaller build.spec --noconfirm
; Puis  : ISCC.exe installer.iss /DAppVersion=1.0.8
; -> dist_installer/EbonholdLauncherSetup.exe
; AppVersion doit matcher core/version.py (APP_VERSION).

#ifndef AppVersion
  #define AppVersion "1.0.8"
#endif
#define AppName "Ebonhold Launcher"
#define AppExeName "EbonholdLauncher.exe"
#define AppPublisher "Ebonhold"
#define AppURL "https://github.com/Squall98/Ebonhold-Launcher"
#define SourceDir "dist\EbonholdLauncher"

[Setup]
AppId={{B6E2B6B0-6E9B-4B9E-9F4E-3F2E5C9C2C7B}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
VersionInfoVersion={#AppVersion}

; Par utilisateur, sans UAC (coherent avec l'auto-update via robocopy).
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
DisableReadyPage=yes

UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
SetupIconFile=assets\icon.ico
LicenseFile=LICENSE

OutputDir=dist_installer
OutputBaseFilename=EbonholdLauncherSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

CloseApplications=yes
RestartApplications=yes

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

; Inno Setup script for the Parallel Agents Office desktop app.
;
; Consumes the PyInstaller onedir bundle at dist\parallel-agents-desktop\ and
; produces a single Windows installer at installer\Output\.
;
; Build:
;   pyinstaller --noconfirm parallel-agents-desktop.spec
;   iscc installer\parallel-agents-desktop.iss
;
; Version can be overridden from CI:
;   iscc /DMyAppVersion=1.2.3 installer\parallel-agents-desktop.iss

#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif

#define MyAppName "Parallel Agents Office"
#define MyAppPublisher "Parallel Agents"
#define MyAppExeName "parallel-agents-desktop.exe"
#define MyAppURL "https://github.com/ErenAri/parallel-agents"

[Setup]
AppId={{8E2A6F4C-2B7D-4E2A-9C1F-PA0FFICE0001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
DefaultDirName={autopf}\Parallel Agents Office
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Per-user install needs no admin elevation.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=Output
OutputBaseFilename=parallel-agents-office-setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The entire PyInstaller onedir bundle.
Source: "..\dist\parallel-agents-desktop\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

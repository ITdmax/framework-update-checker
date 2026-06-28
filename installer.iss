; Inno Setup script for Framework Update Checker
; Compile with:  ISCC.exe installer.iss   (or just run build_installer.ps1)
; Produces: dist_installer\FrameworkUpdateCheckerSetup.exe
;
; This is a PER-USER install (no admin / UAC prompt). It installs to your
; local Programs folder, adds a Start Menu shortcut, optionally starts the app
; at sign-in, and registers an uninstaller in Add/Remove Programs.

#define MyAppName "Framework Update Checker"
#define MyAppVersion "1.0.5"
#define MyAppPublisher "James"
#define MyAppExeName "FrameworkUpdateChecker.exe"

[Setup]
AppId={{1AEB48BE-38EC-45D2-9D78-83CCEB67FA7E}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={userpf}\Framework Update Checker
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=dist_installer
OutputBaseFilename=FrameworkUpdateCheckerSetup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "startup"; Description: "Start automatically when I sign in to Windows"; GroupDescription: "Startup:"

[Files]
; The whole PyInstaller --onedir output folder.
Source: "dist\FrameworkUpdateChecker\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
; Startup shortcut uses the same name the app's in-app "Run at startup" toggle manages,
; so the two stay consistent.
Name: "{userstartup}\FrameworkUpdateChecker"; Filename: "{app}\{#MyAppExeName}"; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName} now"; Flags: nowait postinstall

[UninstallDelete]
; Clean up the startup shortcut on uninstall if it's still there.
Type: files; Name: "{userstartup}\FrameworkUpdateChecker.lnk"

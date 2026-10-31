; Compile with Inno Setup 6 after the portable Windows payload passes smoke.
; The source repository has no application license grant. Resolve licensing and
; third-party obligations before distributing the resulting developer artifact.
#ifndef AppVersion
  #define AppVersion "0.2.0"
#endif
#define AppName "Android Automation Studio"

[Setup]
AppId={{F5C3960F-D8EA-4973-9B47-5395BDF1B918}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=MD7-1337
AppPublisherURL=https://github.com/MD7-1337/Bot_Frm
AppSupportURL=https://github.com/MD7-1337/Bot_Frm/issues
VersionInfoVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\AndroidAutomationStudio
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=AndroidAutomationStudio-windows-x64-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\AndroidAutomationStudio.exe
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\AndroidAutomationStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\AndroidAutomationStudio.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\AndroidAutomationStudio.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\AndroidAutomationStudio.exe"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

; Deliberately no [UninstallDelete] or project/settings paths. User data remains
; in user-owned locations and survives an upgrade or uninstall.

#define AppName "BluettiWidget"
#define AppVersion "0.4.0"

[Setup]
AppId={{53EF3E31-279B-4B2E-90A9-D808FEE98F64}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion} Preview
AppPublisher=wertalya
AppPublisherURL=https://github.com/wertalya/BluettiWidget
AppSupportURL=https://github.com/wertalya/BluettiWidget/issues
DefaultDirName={localappdata}\Programs\{#AppName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
MinVersion=10.0.22000
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\BluettiWidget.exe
AppMutex=Local\VitToolsBluettiPowerCompanion
SetupIconFile=assets\bluetti-widget.ico
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
SourceDir=..
OutputDir=dist\installer
OutputBaseFilename=BluettiWidget-Setup

[Languages]
Name: "ukrainian"; MessagesFile: "compiler:Languages\Ukrainian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
english.StartupTask=Start BluettiWidget when I sign in to Windows
ukrainian.StartupTask=Запускати BluettiWidget після входу у Windows
english.LaunchWidget=Open BluettiWidget
ukrainian.LaunchWidget=Відкрити BluettiWidget

[Tasks]
Name: "startup"; Description: "{cm:StartupTask}"

[Files]
Source: "dist\BluettiWidget\BluettiWidget.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\BluettiWidget\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "README.uk.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "THIRD_PARTY.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "settings.example.ini"; DestDir: "{app}"; Flags: ignoreversion
Source: "docs\compatibility.md"; DestDir: "{app}\docs"; Flags: ignoreversion

[InstallDelete]
Type: files; Name: "{userstartup}\BluettiWidget.lnk"

[Icons]
Name: "{userprograms}\BluettiWidget"; Filename: "{app}\BluettiWidget.exe"; WorkingDir: "{app}"
Name: "{userstartup}\BluettiWidget"; Filename: "{app}\BluettiWidget.exe"; Parameters: "--start-in-tray"; WorkingDir: "{app}"; Tasks: startup

[Run]
Filename: "{app}\BluettiWidget.exe"; Description: "{cm:LaunchWidget}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

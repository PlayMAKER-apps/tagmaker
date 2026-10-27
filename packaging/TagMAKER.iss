#define AppVersion "0.1.0"

[Setup]
AppId={{8BE9ED68-992C-496A-853D-14368AE4AB20}
AppName=TagMAKER
AppVersion={#AppVersion}
AppPublisher=PlayMAKER
ChangesAssociations=yes
DefaultDirName={localappdata}\Programs\TagMAKER
DefaultGroupName=TagMAKER
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=TagMAKER-{#AppVersion}-external-mpv-private-test-setup
Compression=zip
SolidCompression=no
SetupIconFile=..\app\assets\tagmaker.ico
UninstallDisplayIcon={app}\TagMAKER.exe
ArchitecturesAllowed=x64compatible
WizardStyle=modern

[Files]
Source: "..\dist\TagMAKER\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Registry]
Root: HKA; Subkey: "Software\Classes\.tagmaker"; ValueType: string; ValueData: "PlayMAKER.TagMAKER.Project"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\PlayMAKER.TagMAKER.Project"; ValueType: string; ValueData: "TagMAKER project"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\PlayMAKER.TagMAKER.Project\DefaultIcon"; ValueType: string; ValueData: "{app}\app\assets\tagmaker-file.ico,0"
Root: HKA; Subkey: "Software\Classes\PlayMAKER.TagMAKER.Project\shell\open\command"; ValueType: string; ValueData: """{app}\TagMAKER.exe"" ""%1"""

[Icons]
Name: "{group}\TagMAKER"; Filename: "{app}\TagMAKER.exe"
Name: "{autodesktop}\TagMAKER"; Filename: "{app}\TagMAKER.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

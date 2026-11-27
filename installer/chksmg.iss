#ifndef AppVersion
  #error AppVersion must be supplied by build-windows.ps1
#endif
#ifndef AppExe
  #error AppExe must be supplied by build-windows.ps1
#endif

[Setup]
AppId={{C85F1E07-88BD-4E47-85EF-5798297A28B3}
AppName=Checksum Calculator
AppVersion={#AppVersion}
DefaultDirName={commonpf}\chksmg
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\chksmg.exe
SetupIconFile=..\icon.ico
OutputDir=dist
OutputBaseFilename=chksmg-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{commonprograms}\Checksum Calculator"; Filename: "{app}\chksmg.exe"
Name: "{commondesktop}\Checksum Calculator"; Filename: "{app}\chksmg.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\chksmg.exe"; Description: "{cm:LaunchProgram,Checksum Calculator}"; Flags: nowait postinstall skipifsilent

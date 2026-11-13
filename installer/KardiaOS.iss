#define AppVersion "0.2.0"
[Setup]
AppId={{D7C2A4A3-6346-4B50-9F47-B87283E88A12}
AppName=KardiaOS
AppVersion={#AppVersion}
AppPublisher=KardiaOS contributors
DefaultDirName={localappdata}\Programs\KardiaOS
DefaultGroupName=KardiaOS
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=KardiaOS-Setup-{#AppVersion}-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE
UninstallDisplayIcon={app}\KardiaOS.exe
SetupIconFile=..\build\app.ico

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; Flags: unchecked

[Files]
Source: "..\dist\KardiaOS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\src\kardiaos\*"; DestDir: "{app}\source\src\kardiaos"; Excludes: "*.pyc,__pycache__\*"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\tests\*.py"; DestDir: "{app}\source\tests"; Flags: ignoreversion
Source: "..\scripts\*"; DestDir: "{app}\source\scripts"; Flags: ignoreversion
Source: "KardiaOS.iss"; DestDir: "{app}\source\installer"; Flags: ignoreversion
Source: "..\pyproject.toml"; DestDir: "{app}\source"; Flags: ignoreversion
Source: "..\requirements-lock.txt"; DestDir: "{app}\source"; Flags: ignoreversion
Source: "..\run.py"; DestDir: "{app}\source"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}\source"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}\source"; Flags: ignoreversion
Source: "..\THIRD_PARTY.md"; DestDir: "{app}\source"; Flags: ignoreversion

[Icons]
Name: "{group}\KardiaOS"; Filename: "{app}\KardiaOS.exe"
Name: "{autodesktop}\KardiaOS"; Filename: "{app}\KardiaOS.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\KardiaOS.exe"; Description: "Abrir KardiaOS"; Flags: nowait postinstall skipifsilent

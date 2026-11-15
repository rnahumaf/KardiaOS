#define AppVersion "0.10.0"
[Setup]
AppId={{D7C2A4A3-6346-4B50-9F47-B87283E88A12}
AppName=KardiaOS
AppVersion={#AppVersion}
AppPublisher=KardiaOS contributors
DefaultDirName={localappdata}\Programs\KardiaOS
DefaultGroupName=KardiaOS
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
CloseApplications=no
RestartApplications=no
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

[Icons]
Name: "{group}\KardiaOS"; Filename: "{app}\KardiaOS.exe"
Name: "{autodesktop}\KardiaOS"; Filename: "{app}\KardiaOS.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\KardiaOS.exe"; Description: "Abrir KardiaOS"; Flags: nowait postinstall skipifsilent


[Code]
function InitializeSetup(): Boolean;
var
  Locator, Services, Processes: Variant;
begin
  Result := False;
  try
    Locator := CreateOleObject('WbemScripting.SWbemLocator');
    Services := Locator.ConnectServer('', 'root\CIMV2');
    Processes := Services.ExecQuery('SELECT ProcessId FROM Win32_Process WHERE Name="KardiaOS.exe"');
    Result := Processes.Count = 0;
    if not Result then begin
      Log('KardiaOS ativo: instalacao recusada sem fechar a sessao.');
      if not WizardSilent then MsgBox('Feche o KardiaOS manualmente depois de salvar sua captura e execute o instalador novamente.', mbError, MB_OK);
    end;
  except
    Log('Nao foi possivel verificar processos ativos; instalacao recusada.');
  end;
end;

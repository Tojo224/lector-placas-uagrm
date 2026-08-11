#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

#define MyAppName "UAGRM Plate Agent"
#define MyAppPublisher "Universidad Autonoma Gabriel Rene Moreno"
#define MyAppExeName "UAGRMPlateAgent.exe"
#define MyAppId "{{61F4D650-284C-4AA8-A45D-9C74615B7B9D}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\UAGRM\PlateAgent
DefaultGroupName=UAGRM Plate Agent
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
OutputDir=..\dist\windows
OutputBaseFilename=UAGRMPlateAgent-Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=Instalador de UAGRM Plate Agent
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
ChangesAssociations=no
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo del scanner en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Dirs]
Name: "{commonappdata}\UAGRM\PlateAgent"; Permissions: users-modify
Name: "{commonappdata}\UAGRM\PlateAgent\config"; Permissions: users-modify
Name: "{commonappdata}\UAGRM\PlateAgent\data"; Permissions: users-modify
Name: "{commonappdata}\UAGRM\PlateAgent\logs"; Permissions: users-modify
Name: "{commonappdata}\UAGRM\PlateAgent\spool"; Permissions: users-modify

[Files]
Source: "..\dist\windows\UAGRMPlateAgent\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Retira modelos obsoletos de builds anteriores sin tocar los datos persistentes.
Type: filesandordirs; Name: "{app}\runtime\resources\models"

[Icons]
Name: "{group}\UAGRM Plate Scanner"; Filename: "http://127.0.0.1:8765/subir-placa"
Name: "{group}\Estado del UAGRM Plate Agent"; Filename: "http://127.0.0.1:8765/subir-placa#edge-status"
Name: "{autodesktop}\UAGRM Plate Scanner"; Filename: "http://127.0.0.1:8765/subir-placa"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Iniciar UAGRM Plate Agent"; Flags: nowait postinstall skipifsilent runasoriginaluser
Filename: "http://127.0.0.1:8765/configuracion"; Description: "Abrir configuración inicial"; Flags: shellexec postinstall skipifsilent runasoriginaluser

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/IM UAGRMPlateAgent.exe /T /F"; Flags: runhidden waituntilterminated; RunOnceId: "StopPlateAgent"

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM UAGRMPlateAgent.exe /T /F', '', SW_HIDE,
    ewWaitUntilTerminated, ResultCode);
  Result := '';
end;

procedure RegisterAutoStartTask;
var
  Service, RootFolder, TaskDefinition, Trigger, Action: Variant;
begin
  Service := CreateOleObject('Schedule.Service');
  Service.Connect;
  RootFolder := Service.GetFolder('\');
  TaskDefinition := Service.NewTask(0);
  TaskDefinition.RegistrationInfo.Description := 'Inicia UAGRM Plate Agent al iniciar sesion.';
  TaskDefinition.Settings.Enabled := True;
  TaskDefinition.Settings.StartWhenAvailable := True;
  TaskDefinition.Settings.ExecutionTimeLimit := 'PT0S';
  TaskDefinition.Settings.MultipleInstances := 2;
  TaskDefinition.Principal.RunLevel := 0;
  Trigger := TaskDefinition.Triggers.Create(9);
  Trigger.Enabled := True;
  Trigger.UserId := ExpandConstant('{username}');
  Action := TaskDefinition.Actions.Create(0);
  Action.Path := ExpandConstant('{app}\{#MyAppExeName}');
  RootFolder.RegisterTaskDefinition('UAGRM Plate Agent', TaskDefinition, 6, '', '', 3, '');
end;

procedure DeleteAutoStartTask;
var
  Service, RootFolder: Variant;
begin
  try
    Service := CreateOleObject('Schedule.Service');
    Service.Connect;
    RootFolder := Service.GetFolder('\');
    RootFolder.DeleteTask('UAGRM Plate Agent', 0);
  except
    Log('La tarea de autoarranque no existia o no pudo eliminarse.');
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    RegisterAutoStartTask;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    DeleteAutoStartTask;
end;

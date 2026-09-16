; Instalador do CadastroAuto (per-usuário, sem admin)
; Build: & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" cadastroauto.iss

#define MyAppName "Cadastro Auto"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Starke Parts"
#define MyAppExeName "cadastroauto.exe"

[Setup]
; Instala no perfil do usuário: sem UAC/admin e com permissão de escrita
; para o app gravar o banco em data/ (base_path() = pasta do exe).
AppId={{6A3C9E1F-4B15-4C7E-9D2A-4F8B1C2D3E4F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\CadastroAuto
DefaultGroupName=Cadastro Auto
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist\installer
OutputBaseFilename=CadastroAuto-Setup
Compression=lzma2/ultra64
SolidCompression=yes
InternalCompressLevel=ultra64
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
; não reclama de arquivo em uso durante atualização (o app fecha antes)
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "portuguese"; MessagesFile: "compiler:Languages\Portuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Area de Trabalho"; GroupDescription: "Atalhos:"

[Files]
; App + Chromium embutido (fica tudo na pasta de instalação)
Source: "dist\cadastroauto\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir {#MyAppName}"; Flags: nowait postinstall skipifsilent

; Ícone do uninstaller herdando o ícone do app
[UninstallDelete]
Type: filesandordirs; Name: "{app}\data"
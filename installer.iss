; ============================================================
;  Instalador (Inno Setup 6) do Cadastro Auto
; ------------------------------------------------------------
;  Gera: CadastroAuto-Setup.exe  (instalação por usuário, sem admin)
;
;  Compilar manualmente:
;     ISCC.exe /DMyAppVersion=1.3.2 /DSrcDir="C:\caminho\cadastroauto" installer.iss
;
;  O jeito recomendado é rodar o release.bat, que já faz o build do exe
;  (PyInstaller), copia o Chromium e chama este script.
;
;  Defines aceitos:
;     MyAppVersion  versão exibida/gravada (obrigatório na prática)
;     SrcDir        pasta com o build onedir (cadastroauto.exe + _internal + chromium-*)
;     OutputDir     pasta de saída do instalador
;     OutputBase    nome base do .exe gerado (sem extensão)
; ============================================================

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

#ifndef SrcDir
  #define SrcDir "dist\cadastroauto"
#endif

#ifndef OutputDir
  #define OutputDir "dist\installer"
#endif

#ifndef OutputBase
  #define OutputBase "CadastroAuto-Setup"
#endif

#define MyAppName "Cadastro Auto"
#define MyAppPublisher "Starke Parts"
#define MyAppExeName "cadastroauto.exe"
#define MyAppURL "https://github.com/Brakister/autobot"
; AppId fixo: mantém o mesmo "programa instalado" entre versões, então o
; instalador atualiza no lugar em vez de criar uma segunda cópia.
#define MyAppId "{{6A3C9E1F-4B15-4C7E-9D2A-4F8B1C2D3E4F}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases

; Instalação por usuário (sem UAC). Se o usuário quiser, pode escolher
; instalar para todos via /ALLUSERS na linha de comando.
DefaultDirName={localappdata}\Programs\CadastroAuto
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

OutputDir={#OutputDir}
OutputBaseFilename={#OutputBase}
Compression=lzma2/ultra64
SolidCompression=yes
InternalCompressLevel=ultra64
WizardStyle=modern

; Fecha o app automaticamente durante a atualização
CloseApplications=yes
RestartApplications=no

UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SrcDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

; Observação: os dados do usuário ficam em "{app}\data" (banco SQLite e
; sessão do navegador). Eles NÃO são removidos na desinstalação de
; propósito, para não apagar o histórico por engano.

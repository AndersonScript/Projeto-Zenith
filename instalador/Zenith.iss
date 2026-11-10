; ============================================================================================================
;  Zenith — INSTALADOR (Inno Setup 6.3 ou mais novo)  —  https://jrsoftware.org/isinfo.php
;
;  Para gerar:   1) python build_exe.py --edicao publico        (cria dist\Zenith)
;                2) abrir este arquivo no Inno Setup e apertar Compilar  (ou: instalador\construir_instalador.bat)
;  Resultado:    dist_instalador\Zenith_Instalador_v<versão>.exe
;
;  O que o instalador faz:
;    - instala por padrão SÓ PARA VOCÊ (pasta Programas do seu usuário): NÃO precisa ser administrador;
;    - mostra ONDE vai ficar e deixa trocar a pasta;
;    - pergunta ONDE guardar as criações e os dados (imagens, vídeos, programas criados, memória, modelos de voz);
;    - cria atalhos (menu Iniciar e, se quiser, área de trabalho);
;    - ao desinstalar, pergunta se apaga as configurações; as criações NUNCA são apagadas.
;
;  AINDA NÃO FOI COMPILADO NEM TESTADO (foi escrito num computador sem Windows). Se o compilador reclamar de algo,
;  mande a mensagem — normalmente é uma linha só.
; ============================================================================================================

#ifndef AppVersion
  #define AppVersion "1.4"
#endif
#define AppName "Zenith"
#define AppPublisher "Zenith"
#define AppURL "https://github.com/SEU_USUARIO/zenith"
#define AppExe "Zenith.exe"

[Setup]
AppId={{4861871C-6933-46FB-89E5-D5E0C140C81C}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\Zenith
DefaultGroupName=Zenith
DisableProgramGroupPage=yes
DisableDirPage=no
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist_instalador
OutputBaseFilename=Zenith_Instalador_v{#AppVersion}
SetupIconFile=..\assets\zenith_icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
WizardImageFile=..\assets\instalador_lateral.bmp
WizardSmallImageFile=..\assets\instalador_pequena.bmp
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes
RestartApplications=no
LicenseFile=..\LICENSE
InfoBeforeFile=bem_vindo.txt
VersionInfoVersion={#AppVersion}.0.0
VersionInfoProductName={#AppName}
VersionInfoDescription={#AppName}
; Assinatura digital (tira o aviso "Windows protegeu seu PC"). Quando tiver certificado, ative as duas linhas:
;SignTool=signtool $f
;SignedUninstaller=yes

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar um atalho na área de trabalho"; GroupDescription: "Atalhos:"; Flags: unchecked

[Files]
; Tudo que o build_exe.py colocou em dist\Zenith, MENOS o que é de quem usa (se por acaso estiver na pasta).
Source: "..\dist\Zenith\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion; Excludes: "config\settings.json,config\conversations.json,config\chaves.txt,config\instalacao.json,memory_db\*,creations\*,models\*,temp\*,zenith_log.txt"

[Icons]
Name: "{autoprograms}\Zenith"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{autodesktop}\Zenith"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir o Zenith agora"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\temp"
Type: filesandordirs; Name: "{app}\libs"

[Code]
var
  PaginaDados: TInputDirWizardPage;

procedure InitializeWizard;
begin
  PaginaDados := CreateInputDirPage(wpSelectDir,
    'Pasta das criações e dos dados',
    'Onde o Zenith vai guardar o que você criar?',
    'Aqui ficam as imagens, vídeos e programas que o Zenith criar, a memória dele e os modelos de voz que ele baixar ' +
    '(os modelos podem ocupar uns 500 MB). Escolha um lugar com espaço livre. ' +
    'Você pode mudar isso depois em Configurações.',
    False, '');
  PaginaDados.Add('');
  PaginaDados.Values[0] := ExpandConstant('{userdocs}\Zenith');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = PaginaDados.ID then
  begin
    if Trim(PaginaDados.Values[0]) = '' then
    begin
      MsgBox('Escolha uma pasta para as criações e os dados.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function JsonEscape(const S: String): String;
begin
  Result := S;
  StringChangeEx(Result, '\', '\\', True);
  StringChangeEx(Result, '"', '\"', True);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Pasta: String;
  Linhas: TArrayOfString;
begin
  if CurStep = ssPostInstall then
  begin
    Pasta := RemoveBackslashUnlessRoot(Trim(PaginaDados.Values[0]));
    ForceDirectories(Pasta);
    ForceDirectories(ExpandConstant('{app}\config'));
    SetArrayLength(Linhas, 1);
    Linhas[0] := '{"data_root_path": "' + JsonEscape(Pasta) + '", "instalado_por": "instalador", "versao": "{#AppVersion}"}';
    { UTF-8 (o nome da pasta pode ter acento); o Zenith lê com utf-8-sig, então tanto faz o BOM }
    SaveStringsToUTF8File(ExpandConstant('{app}\config\instalacao.json'), Linhas, False);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if MsgBox('Quer apagar também as suas configurações, chaves de IA e conversas?' + #13#10 + #13#10 +
              'As imagens, vídeos e programas que o Zenith criou NÃO serão apagados. ' +
              'Se você pretende instalar de novo, responda Não.',
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
    begin
      DelTree(ExpandConstant('{app}\config'), True, True, True);
      RemoveDir(ExpandConstant('{app}'));
    end;
  end;
end;

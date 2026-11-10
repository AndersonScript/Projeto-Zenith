@echo off
rem Zenith — gera o instalador. Rode DEPOIS de: python build_exe.py --edicao publico
rem Precisa do Inno Setup 6.3+ (https://jrsoftware.org/isdl.php). Se ele estiver em outra pasta, ajuste a linha ISCC abaixo.
setlocal
cd /d "%~dp0"
if not exist "..\dist\Zenith\Zenith.exe" (
  echo [ERRO] Nao achei ..\dist\Zenith\Zenith.exe. Rode antes:  python build_exe.py --edicao publico
  exit /b 1
)
if not exist "..\LICENSE" (
  echo [ERRO] Falta o arquivo LICENSE na raiz do projeto.
  exit /b 1
)
set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
  echo [ERRO] Inno Setup 6 nao encontrado. Instale em https://jrsoftware.org/isdl.php e rode de novo.
  exit /b 1
)
for /f "delims=" %%v in ('python -c "import sys; sys.path.insert(0,'..'); from brain import zenith_version as v; print('.'.join(map(str, v.numero()[:2])))"') do set VER=%%v
%ISCC% /DAppVersion=%VER% Zenith.iss
if errorlevel 1 (
  echo [ERRO] O compilador do Inno Setup reclamou. Copie a mensagem de cima e mande no chat.
  exit /b 1
)
echo.
echo Pronto: ..\dist_instalador\Zenith_Instalador_v%VER%.exe
echo Calcule o SHA-256 para a pagina de download:  certutil -hashfile ..\dist_instalador\Zenith_Instalador_v%VER%.exe SHA256
endlocal

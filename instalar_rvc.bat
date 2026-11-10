@echo off
REM ============================================================
REM  ZENITH - instalar_rvc.bat
REM  Cria um ambiente SO do RVC (Python 3.10) em tools\rvc\venv,
REM  separado do Python do Zenith. O Zenith acha sozinho.
REM
REM  Antes de rodar (uma vez):
REM    1) Python 3.10 instalado (python.org/downloads/release/python-31011)
REM       e marcado "py launcher".
REM    2) "Microsoft C++ Build Tools" (visualstudio.microsoft.com/visual-cpp-build-tools)
REM       - o fairseq, que o RVC usa, as vezes precisa compilar.
REM  Leva alguns minutos e baixa ~2 GB (torch). Pode fechar a janela depois.
REM ============================================================
setlocal
cd /d "%~dp0"
echo.
echo [RVC] Procurando Python 3.10...
py -3.10 --version >nul 2>&1
if errorlevel 1 (
  echo [RVC] NAO achei o Python 3.10 ^(comando "py -3.10"^).
  echo       Instale em https://www.python.org/downloads/release/python-31011/ e rode de novo.
  pause
  exit /b 1
)
if not exist "tools\rvc" mkdir "tools\rvc"
if not exist "tools\rvc\venv\Scripts\python.exe" (
  echo [RVC] Criando ambiente em tools\rvc\venv ...
  py -3.10 -m venv "tools\rvc\venv"
  if errorlevel 1 ( echo [RVC] Falhou ao criar o ambiente. & pause & exit /b 1 )
)
echo [RVC] Atualizando o pip...
"tools\rvc\venv\Scripts\python.exe" -m pip install --upgrade pip
echo [RVC] Instalando rvc-python ^(demora; baixa o torch^)...
"tools\rvc\venv\Scripts\python.exe" -m pip install rvc-python
if errorlevel 1 (
  echo.
  echo [RVC] A instalacao falhou. Se a mensagem falar de "fairseq" ou "Microsoft Visual C++",
  echo       instale o "Microsoft C++ Build Tools" e rode este arquivo de novo.
  pause
  exit /b 1
)
echo.
echo [RVC] Pronto! Em Configuracoes ^> Voz o modelo .pth ja pode ser usado.
echo       Digite /testar_voz no chat pra conferir ^(deve aparecer "Python 3.10 do RVC: encontrado"^).
pause

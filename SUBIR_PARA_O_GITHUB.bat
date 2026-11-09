@echo off
chcp 65001 >nul
cd /d "C:\Zenith\_repo_github"
echo ======================================================
echo  Subindo todas as atualizações do Zenith para o GitHub
echo ======================================================
echo.
echo Repositorio: https://github.com/AndersonScript/Projeto-Zenith
echo.
git push origin main
echo.
if errorlevel 1 (
    echo.
    echo [X] Ocorreu uma falha no envio. Se abriu a janela do navegador, autorize o GitHub e rode novamente.
) else (
    echo.
    echo [OK] Todos os arquivos e versoes foram enviados com sucesso para o GitHub!
    echo      O site na Vercel (projeto-zenith-five.vercel.app) ja esta atualizando.
)
echo.
pause

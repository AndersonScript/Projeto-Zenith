@echo off
chcp 65001 >nul
cd /d "C:\Zenith\_repo_github"
title Subir Zenith para o GitHub

echo ======================================================
echo  Subindo todas as atualizacoes do Zenith para o GitHub
echo ======================================================
echo.
echo Repositorio: https://github.com/AndersonScript/Projeto-Zenith
echo.
echo 1. Preparando arquivos...
git add -A
git commit -m "Atualizacao v1.0: site, launcher e novidades" >nul 2>&1

echo 2. Enviando para o GitHub (git push)...
echo    (Se abrir uma janela no navegador, clique em 'Authorize' para confirmar seu login)
echo.
git push origin main
echo.

if errorlevel 1 (
    echo.
    echo ======================================================
    echo [!] O envio precisou de autorizacao.
    echo     Se uma pagina do GitHub abriu no navegador, clique
    echo     em "Authorize" e depois execute este arquivo de novo.
    echo ======================================================
) else (
    echo.
    echo ======================================================
    echo [OK] Sucesso! Tudo enviado para o GitHub!
    echo      O site na Vercel ja esta atualizando sozinho:
    echo      https://projeto-zenith-five.vercel.app/
    echo ======================================================
)
echo.
pause

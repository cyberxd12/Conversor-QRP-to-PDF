@echo off
title Compilar Executavel - Conversor QRP para PDF
cd /d "%~dp0"
echo ============================================================
echo   Compilando Conversor QRP para PDF em Executavel (.exe)
echo ============================================================
echo.
echo Verificando PyInstaller...
pip install pyinstaller customtkinter pillow pypdf --quiet
echo.
echo Gerando executavel standalone...
pyinstaller --noconsole --onefile --clean --collect-all customtkinter --name "ConversorQRP" main.py

echo.
if exist "dist\ConversorQRP.exe" (
    echo ============================================================
    echo   SUCESSO! O executavel foi gerado em:
    echo   dist\ConversorQRP.exe
    echo ============================================================
) else (
    echo Ocorreu um erro durante a compilacao.
)
pause

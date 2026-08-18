@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title AutoBook - Instalador

echo ============================================================
echo   AutoBook - Instalador automatico
echo ============================================================
echo.

rem --- Detectar Python ---
set "PY="
where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py -3"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set "PY=python"
    )
)
if "%PY%"=="" (
    echo [ERROR] No se encontro Python. Instalalo desde https://www.python.org/downloads/
    echo         IMPORTANTE: marca "Add python.exe to PATH" al instalar.
    pause
    exit /b 1
)

echo [1/4] Creando entorno virtual (.venv)...
%PY% -m venv .venv
if errorlevel 1 (
    echo [ERROR] No se pudo crear el entorno virtual.
    pause
    exit /b 1
)

echo [2/4] Actualizando pip...
.\.venv\Scripts\python.exe -m pip install --upgrade pip >nul 2>nul

echo [3/4] Instalando dependencias...
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Fallo la instalacion de dependencias.
    pause
    exit /b 1
)

echo [4/4] Comprobando que el servidor arranca...
.\.venv\Scripts\python.exe -c "import autobook.server; print('OK: autobook.server importa correctamente')"
if errorlevel 1 (
    echo [ERROR] El servidor no arranca. Revisa los errores anteriores.
    pause
    exit /b 1
)

if not exist .env (
    copy .env.example .env >nul 2>nul
    echo.
    echo Se creo .env (opcional: editalo si quieres otra carpeta de descargas).
)

echo.
echo ============================================================
echo   INSTALACION COMPLETA
echo ============================================================
echo.
echo   Siguiente paso: abrir Claude Code o opencode EN ESTA CARPETA
echo   y pegar el prompt de instalacion que esta en:
echo.
echo       docs\instalacion-ai.md
echo.
echo   Requisitos restantes:
echo     - Google Chrome o Microsoft Edge instalado (auto-detectado).
echo     - opencode o Claude Code instalado.
echo.
pause
exit /b 0
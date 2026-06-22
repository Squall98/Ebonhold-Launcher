@echo off
title Ebonhold Launcher
cd /d "%~dp0"

REM --- Verifie que Python est installe ---
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo Python est introuvable.
    echo Installe Python 3 depuis https://www.python.org/downloads/
    echo en cochant "Add Python to PATH" pendant l'installation, puis relance ce fichier.
    echo.
    pause
    exit /b 1
)

REM --- Installe les dependances a la premiere utilisation ---
python -c "import webview" >nul 2>&1
if errorlevel 1 (
    echo Premiere utilisation : installation des dependances...
    python -m pip install -r requirements.txt
    echo.
)

REM --- Lance le launcher ---
python main.py
if errorlevel 1 (
    echo.
    echo Le launcher s'est arrete avec une erreur ^(voir ci-dessus^).
    pause
)

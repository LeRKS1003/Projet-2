@echo off
rem DERIVE - lanceur Windows : double-cliquez sur ce fichier pour jouer.
rem La premiere fois, il installe tout seul ce qu'il faut (une ou deux minutes).
chcp 65001 >nul
cd /d "%~dp0"
title DERIVE

if exist ".venv\installe.txt" goto jouer

echo Premiere installation du jeu, patientez une ou deux minutes...
echo.
if not exist ".venv\Scripts\python.exe" (
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 -m venv .venv
    ) else (
        python -m venv .venv
    )
)
if not exist ".venv\Scripts\python.exe" goto sans_python
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto erreur
echo ok> ".venv\installe.txt"

:jouer
echo Lancement de DERIVE...
".venv\Scripts\python.exe" main.py
if errorlevel 1 goto erreur
exit /b 0

:sans_python
echo.
echo Python est introuvable. Installez-le depuis https://www.python.org/downloads/
echo en cochant bien la case "Add python.exe to PATH", puis relancez ce fichier.
pause
exit /b 1

:erreur
echo.
echo Une erreur est survenue. Faites une capture de cette fenetre et envoyez-la.
pause
exit /b 1

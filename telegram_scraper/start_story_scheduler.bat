@echo off
title Story Scheduler — Telegram

echo ============================================
echo   Story Scheduler  ^|  http://localhost:8001
echo ============================================
echo.

cd /d "%~dp0"

:: Verifier Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python non trouve. Installe Python 3.11+
    pause
    exit /b 1
)

:: Tuer tout process existant sur le port 8001
echo Arret du serveur precedent si existant...
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8001 "') do (
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 1 >nul

:: Installer les dependances si besoin
echo Installation des dependances...
pip install fastapi "uvicorn[standard]" telethon python-multipart Pillow --quiet

echo.
echo Demarrage du serveur sur http://localhost:8001
echo Appuie sur Ctrl+C pour arreter.
echo.

:: Ouvrir UNE SEULE fenetre navigateur apres 2 secondes
start /b "" cmd /c "timeout /t 2 >nul && start http://localhost:8001"

:: Lancer le serveur
python -m uvicorn story_scheduler:app --host 0.0.0.0 --port 8001 --app-dir "%~dp0"

pause

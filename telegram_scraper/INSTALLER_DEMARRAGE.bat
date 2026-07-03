@echo off
title Installer le demarrage automatique — Story Scheduler

echo =====================================================
echo   Installation du demarrage automatique
echo   Story Scheduler se lancera a chaque allumage du PC
echo =====================================================
echo.

set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set SRC=%~dp0start_silent.vbs
set DEST=%STARTUP%\story_scheduler.vbs

echo Installation dans : %STARTUP%
echo.

:: Copier le lanceur silencieux dans le dossier Startup de Windows
copy /Y "%SRC%" "%DEST%" >nul

if exist "%DEST%" (
    echo [OK] Story Scheduler demarrera automatiquement au prochain allumage.
    echo.
    echo Le serveur tourne en arriere-plan, sans fenetre noire.
    echo Pour acceder au site : http://localhost:8001
    echo Pour voir les logs   : %~dp0scheduler.log
    echo.
    echo Pour DESINSTALLER, supprime ce fichier :
    echo %DEST%
) else (
    echo [ERREUR] Impossible de copier le fichier. Relance en tant qu'administrateur.
)

echo.
pause

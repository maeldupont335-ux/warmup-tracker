@echo off
cd /d "%~dp0"
echo === Higgsfield Studio ===
echo Installation des dependances...
pip install -r requirements.txt
echo.
echo Demarrage du serveur sur http://localhost:8080
echo Page Upload   : http://localhost:8080/
echo Page Resultats: http://localhost:8080/results
echo.
uvicorn app:app --host 0.0.0.0 --port 8080 --reload
pause

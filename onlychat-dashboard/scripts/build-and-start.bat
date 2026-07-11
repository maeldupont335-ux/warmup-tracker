@echo off
cd /d "C:\Users\MAEL\Downloads\higgsfield-batch\higgsfield-batch\onlychat-dashboard"
call npm run build
start /min cmd /c "npm run start"

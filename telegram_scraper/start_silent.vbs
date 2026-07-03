Dim fso, scriptDir, shell

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = scriptDir

' Chemin complet vers Python (ne depend pas du PATH)
Dim python
python = "C:\Users\MAEL\AppData\Local\Programs\Python\Python312\python.exe"

' Si Python introuvable a cet endroit, chercher dans le PATH
If Not fso.FileExists(python) Then
    python = "python"
End If

' Tuer le process existant sur le port 8001 si present
shell.Run "cmd /c for /f ""tokens=5"" %a in ('netstat -aon 2^>nul ^| findstr "":8001 ""') do taskkill /PID %a /F >nul 2>&1", 0, True

' Petite pause pour liberer le port
WScript.Sleep 2000

' Lancer le serveur en arriere-plan, sans fenetre noire
shell.Run """" & python & """ -m uvicorn story_scheduler:app --host 0.0.0.0 --port 8001 --app-dir """ & scriptDir & """ >> """ & scriptDir & "\scheduler.log"" 2>&1", 0, False

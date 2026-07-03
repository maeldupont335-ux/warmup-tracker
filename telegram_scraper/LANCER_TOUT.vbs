Dim base
base = "C:\Users\MAEL\Downloads\higgsfield-batch\higgsfield-batch\telegram_scraper"

Dim python
python = "C:\Users\MAEL\AppData\Local\Programs\Python\Python312\python.exe"

Dim WshShell
Set WshShell = CreateObject("WScript.Shell")

' Lance le scraper en arriere-plan (silencieux)
WshShell.Run Chr(34) & python & Chr(34) & " " & Chr(34) & base & "\scraper.py" & Chr(34), 0, False

' Lance le daemon warmup/MassDM via le fichier .bat (terminal visible)
WshShell.Run Chr(34) & base & "\start_daemon.bat" & Chr(34), 1, False

Set WshShell = Nothing

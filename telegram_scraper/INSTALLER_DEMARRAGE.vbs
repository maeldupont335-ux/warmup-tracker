' INSTALLER_DEMARRAGE.vbs
' Double-clique UNE SEULE FOIS pour que le daemon se lance
' automatiquement à chaque démarrage de Windows.
' (Sans toucher au terminal)

Dim WshShell, WshFSO, oShell
Set WshShell = CreateObject("WScript.Shell")
Set WshFSO   = CreateObject("Scripting.FileSystemObject")
Set oShell   = CreateObject("Shell.Application")

Dim base
base = "C:\Users\MAEL\Downloads\higgsfield-batch\higgsfield-batch\telegram_scraper"

Dim vbsSource
vbsSource = base & "\LANCER_TOUT.vbs"

' Dossier Démarrage Windows (pour l'utilisateur courant)
Dim startupFolder
startupFolder = WshShell.SpecialFolders("Startup")

' Chemin du raccourci à créer
Dim shortcutPath
shortcutPath = startupFolder & "\Telegram_Daemon.lnk"

If WshFSO.FileExists(shortcutPath) Then
    MsgBox "✅ Le daemon est déjà configuré pour démarrer automatiquement." & vbCrLf & _
           "Rien à faire — il se lancera à chaque démarrage de Windows.", _
           vbInformation, "Déjà installé"
Else
    ' Crée un raccourci dans le dossier Démarrage
    Dim oShortcut
    Set oShortcut = WshShell.CreateShortcut(shortcutPath)
    oShortcut.TargetPath     = "wscript.exe"
    oShortcut.Arguments      = """" & vbsSource & """"
    oShortcut.WorkingDirectory = base
    oShortcut.Description    = "Telegram Daemon (warmup + mass DM + profile changer)"
    oShortcut.Save

    MsgBox "✅ Installé avec succès !" & vbCrLf & vbCrLf & _
           "Le daemon démarrera automatiquement à chaque connexion Windows." & vbCrLf & _
           "Tu n'as plus besoin de lancer quoi que ce soit manuellement.", _
           vbInformation, "Installation réussie"
End If

Set WshShell = Nothing
Set WshFSO   = Nothing
Set oShell   = Nothing

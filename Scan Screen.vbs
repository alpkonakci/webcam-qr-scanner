Option Explicit

Dim shell, fileSystem, appDirectory, packagedApplication
Dim pythonWindowed, sourceApplication, command

Set shell = CreateObject("WScript.Shell")
Set fileSystem = CreateObject("Scripting.FileSystemObject")

appDirectory = fileSystem.GetParentFolderName(WScript.ScriptFullName)
packagedApplication = appDirectory & "\QR-Scanner.exe"
pythonWindowed = appDirectory & "\.venv\Scripts\pythonw.exe"
sourceApplication = appDirectory & "\launcher.py"

If fileSystem.FileExists(packagedApplication) Then
    command = Chr(34) & packagedApplication & Chr(34) & " --screen --desktop"
ElseIf fileSystem.FileExists(pythonWindowed) Then
    command = Chr(34) & pythonWindowed & Chr(34) & " " & _
        Chr(34) & sourceApplication & Chr(34) & " --screen --desktop"
Else
    MsgBox "Application files were not found.", 16, "Scan Screen"
    WScript.Quit 1
End If

shell.Run command, 0, False

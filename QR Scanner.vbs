Option Explicit

Dim shell, fileSystem, appDirectory, pythonWindowed, application, command

Set shell = CreateObject("WScript.Shell")
Set fileSystem = CreateObject("Scripting.FileSystemObject")

appDirectory = fileSystem.GetParentFolderName(WScript.ScriptFullName)
pythonWindowed = appDirectory & "\.venv\Scripts\pythonw.exe"
application = appDirectory & "\app.py"

If Not fileSystem.FileExists(pythonWindowed) Then
    MsgBox "Application environment not found. Follow the setup instructions in README.md.", 16, "QR Scanner"
    WScript.Quit 1
End If

command = Chr(34) & pythonWindowed & Chr(34) & " " & Chr(34) & application & Chr(34) & " --desktop"
shell.Run command, 0, False

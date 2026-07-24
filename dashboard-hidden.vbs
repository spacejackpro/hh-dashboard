' Starts HH Dashboard without a console window.
' Server output goes to server.log next to this file.
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")

dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = dir

If Not fso.FileExists(dir & "\.venv\Scripts\uvicorn.exe") Then
    ' First run: installation takes minutes, so keep the window visible.
    sh.Run "cmd /c dashboard.cmd", 1, False
Else
    sh.Run "cmd /c dashboard.cmd > server.log 2>&1", 0, False
End If

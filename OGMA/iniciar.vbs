Set ws = CreateObject("WScript.Shell")
ws.Run "cmd /c """ & CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName) & "\iniciar.bat""", 0, False

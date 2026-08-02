Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\AWS\Desktop\ملفات متنوعة\بوتات التليجرام\movies_finder_bot"
WshShell.Run "cmd /c """"venv\Scripts\python.exe"" -u movies_bot.py > movies_bot.log 2>&1"""", 0, False

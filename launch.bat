@echo off
setlocal
cd /d "%~dp0"

set "PY=C:\Users\zhehua\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if not exist "%PY%" set "PY=python"

rem Already listening on 8765 -> just open the browser.
powershell -NoProfile -Command "$c=New-Object Net.Sockets.TcpClient; try { $ok=$c.ConnectAsync('127.0.0.1',8765).Wait(400) } catch { $ok=$false }; if ($ok) { exit 0 } else { exit 1 }" >nul 2>&1
if not errorlevel 1 goto openweb

rem Start the server minimized, then wait until the port answers (max ~12s).
start "AniMe Vision" /min "%PY%" -X utf8 "app.py" 8765
powershell -NoProfile -Command "for($i=0;$i -lt 40;$i++){ $c=New-Object Net.Sockets.TcpClient; try { if($c.ConnectAsync('127.0.0.1',8765).Wait(300)){ exit 0 } } catch {} ; Start-Sleep -Milliseconds 300 }; exit 1" >nul 2>&1

:openweb
start "" "http://127.0.0.1:8765"
exit /b

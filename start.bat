@echo off
chcp 65001 >nul
cd /d "%~dp0"
title AniMe Vision 控制台
set "BUNDLED=C:\Users\zhehua\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
set "PY="
if exist "%BUNDLED%" (
  "%BUNDLED%" -c "import PIL, numpy" >nul 2>&1
  if not errorlevel 1 set "PY=%BUNDLED%"
)
if not defined PY where py >nul 2>&1 && set "PY=py -3"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY (
  echo 未找到可用的 Python 3，请安装后重试。
  pause
  exit /b 1
)
%PY% -c "import PIL, numpy" >nul 2>&1
if errorlevel 1 (
  echo 正在安装依赖 Pillow / numpy ...
  %PY% -m pip install --user pillow numpy
)
echo 启动 AniMe Vision 控制台: http://127.0.0.1:8765
%PY% app.py 8765
pause
@echo off
chcp 65001 >nul
cd /d "%~dp0"
title AniMe Vision 控制台（管理员模式）
net session >nul 2>&1
if %errorlevel% neq 0 (
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
echo [管理员模式] 独占灯板，临时暂停奥创灯效服务
call "%~dp0start.bat"
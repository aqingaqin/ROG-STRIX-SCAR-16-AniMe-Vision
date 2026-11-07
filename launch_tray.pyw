# -*- coding: utf-8 -*-
"""双击快捷方式时隐藏启动托盘，不经过 VBS / 控制台窗口。"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
POWERSHELL = os.path.join(
    os.environ.get("SystemRoot", r"C:\Windows"),
    "System32", "WindowsPowerShell", "v1.0", "powershell.exe")


def main():
    script = os.path.join(ROOT, "tray.ps1")
    if not os.path.exists(script):
        return 1
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    subprocess.Popen(
        [POWERSHELL, "-NoProfile", "-WindowStyle", "Hidden",
         "-ExecutionPolicy", "Bypass", "-File", script],
        cwd=ROOT, creationflags=flags, close_fds=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)
    return 0


if __name__ == "__main__":
    sys.exit(main())

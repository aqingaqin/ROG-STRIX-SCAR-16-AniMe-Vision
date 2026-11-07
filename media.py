# -*- coding: utf-8 -*-
"""media.py — 读取系统正在播放的媒体信息（Windows SMTC / GSMTC）

通过 Windows PowerShell 5.1 调用 WinRT 的
Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager，
拿到当前播放器的 歌名 / 歌手 / 播放状态，后台线程定期刷新。
"""

import base64
import subprocess
import threading
import time

_PS_SCRIPT = r'''
try {
  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  Add-Type -AssemblyName System.Runtime.WindowsRuntime -ErrorAction Stop
  $null = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager,Windows.Media.Control,ContentType=WindowsRuntime]
  $asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | ? { $_.Name -eq "AsTask" -and $_.GetParameters().Count -eq 1 -and $_.IsGenericMethod })[0]
  $op = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync()
  $task = $asTask.MakeGenericMethod([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]).Invoke($null, @($op))
  $task.Wait(3000) | Out-Null
  $mgr = $task.Result
  $s = $mgr.GetCurrentSession()
  if ($s -ne $null) {
    $p = $s.TryGetMediaPropertiesAsync()
    $tp = $asTask.MakeGenericMethod([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties]).Invoke($null, @($p))
    $tp.Wait(3000) | Out-Null
    $mp = $tp.Result
    Write-Output ("TITLE|" + $mp.Title)
    Write-Output ("ARTIST|" + $mp.Artist)
  }
} catch { }
'''


def _ps_encoded(script):
    return base64.b64encode(script.encode("utf-16-le")).decode()


def query_now_playing(timeout=15):
    """返回 (title, artist)；无会话或失败时返回空字符串。"""
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive",
             "-EncodedCommand", _ps_encoded(_PS_SCRIPT)],
            capture_output=True, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
        out = r.stdout.decode("utf-8", "ignore")
    except Exception:
        return "", ""
    title = artist = ""
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("TITLE|"):
            title = line[6:].strip()
        elif line.startswith("ARTIST|"):
            artist = line[7:].strip()
    return title, artist


class NowPlaying:
    """后台线程定期刷新当前播放信息。"""

    def __init__(self, interval=4.0):
        self.interval = float(interval)
        self.title = ""
        self.artist = ""
        self.updated = 0.0
        self.error = None
        self._run = False
        self._thread = None
        self._lock = threading.Lock()

    def start(self):
        if self._run:
            return self
        self._run = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def _loop(self):
        while self._run:
            try:
                t, a = query_now_playing()
                with self._lock:
                    self.title, self.artist = t, a
                    self.updated = time.time()
                self.error = None
            except Exception as e:
                self.error = str(e)
            time.sleep(self.interval)

    def stop(self):
        self._run = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def text(self):
        """'歌手 - 歌名' 形式，供滚动显示。"""
        with self._lock:
            a, t = self.artist, self.title
        if a and t:
            return f"{a} - {t}"
        return t or a or ""

    def refresh_now(self):
        t, a = query_now_playing()
        with self._lock:
            self.title, self.artist = t, a
            self.updated = time.time()
        return self.text()


if __name__ == "__main__":
    print("查询中 ...")
    t, a = query_now_playing()
    print("歌手:", a or "(无)")
    print("歌名:", t or "(无)")

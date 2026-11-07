# -*- coding: utf-8 -*-
"""诊断第 10 轮：持续刷新 20 秒，压过奥创的覆盖。"""
import ctypes
import time
from ctypes import wintypes

import animelib

_hid = ctypes.WinDLL("hid", use_last_error=True)
_hid.HidD_SetFeature.argtypes = [wintypes.HANDLE, ctypes.c_char_p, wintypes.DWORD]
_hid.HidD_SetFeature.restype = wintypes.BOOL


def open_dev():
    for p in animelib.find_anime_paths():
        d = animelib.AnimeDevice(p)
        d.open()
        if d.caps and d.caps.FeatureReportByteLength >= 640:
            return d
        d.close()
    raise RuntimeError("未找到设备")


def send(dev, pkt):
    ok = _hid.HidD_SetFeature(dev.handle, bytes(pkt), len(pkt))
    if not ok:
        # 设备可能被短暂独占，重试一次
        time.sleep(0.02)
        ok = _hid.HidD_SetFeature(dev.handle, bytes(pkt), len(pkt))
    return ok


def show(dev, frame):
    for p in animelib.frame_packets(frame):
        send(dev, p)
    send(dev, animelib.flush_packet())


dev = open_dev()
for p in animelib.init_packets():
    send(dev, p)
send(dev, animelib.flush_packet())
send(dev, animelib.enable_display_packet(True))
send(dev, animelib.flush_packet())
send(dev, animelib.brightness_packet(3))
send(dev, animelib.flush_packet())

data = bytearray(animelib.LED_COUNT)
for i in range(210):
    data[i] = 255
frame = bytes(data)

print("持续显示「线序 1~210 亮」20 秒，请在这段时间内观察 A 面 ...", flush=True)
t0 = time.time()
while time.time() - t0 < 20:
    show(dev, frame)
    time.sleep(0.15)
print("20 秒保持结束。")

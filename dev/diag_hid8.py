# -*- coding: utf-8 -*-
"""诊断第 8 轮：线序渐变，揭示真实线序方向。"""
import ctypes
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
    if not _hid.HidD_SetFeature(dev.handle, bytes(pkt), len(pkt)):
        raise OSError(ctypes.get_last_error(), "SetFeature 失败")


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

n = animelib.LED_COUNT
grad = bytearray(n)
for i in range(n):
    grad[i] = int(i * 255 / (n - 1))
show(dev, bytes(grad))
print("已发送线序渐变（线序 #1 最暗 → #810 最亮），灯板保持该图案。")
print("线序 1..405 是暗的一半，406..810 是亮的一半。")

# -*- coding: utf-8 -*-
"""诊断第 9 轮：只亮线序前 210 颗，判定几何布局。"""
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

data = bytearray(animelib.LED_COUNT)
for i in range(210):
    data[i] = 255
for p in animelib.frame_packets(bytes(data)):
    send(dev, p)
send(dev, animelib.flush_packet())
print("已点亮线序第 1~210 颗（其余全灭）。请查看 A 面亮起区域的形状。")

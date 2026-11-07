# -*- coding: utf-8 -*-
"""诊断第 7 轮：整片全亮，看清物理轮廓。"""
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
    if not _hid.HidD_SetFeature(dev.handle, bytes(pkt), len(pkt)):
        raise OSError(ctypes.get_last_error(), "SetFeature 失败")


dev = open_dev()
for p in animelib.init_packets():
    send(dev, p)
send(dev, animelib.flush_packet())
send(dev, animelib.enable_display_packet(True))
send(dev, animelib.flush_packet())
send(dev, animelib.brightness_packet(3))
send(dev, animelib.flush_packet())

print("发送整片全亮 ...")
for p in animelib.frame_packets(bytes([255] * animelib.LED_COUNT)):
    send(dev, p)
send(dev, animelib.flush_packet())
print("已发送，灯板保持全亮。请现在看 A 面。")

# -*- coding: utf-8 -*-
"""验证方向与文字渲染：分区域点亮 + 文字。"""
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
print("初始化完成")


def show(frame, label, hold=4.0):
    for p in animelib.frame_packets(frame):
        send(dev, p)
    send(dev, animelib.flush_packet())
    print(f"  >>> {label}（{hold}s）", flush=True)
    time.sleep(hold)


def region(pred):
    data = bytearray(animelib.LED_COUNT)
    for i, (x, y) in enumerate(animelib.LEDS):
        if pred(x, y):
            data[i] = 255
    return bytes(data)


print("1) 顶部 1/3 亮")
show(region(lambda x, y: y < 23), "顶部1/3亮")

print("2) 底部 1/3 亮")
show(region(lambda x, y: y >= 45), "底部1/3亮")

print("3) 左半边亮（物理 x 小于中心）")
mid = (animelib._PANEL_MIN_X_CM + animelib._PANEL_MAX_X_CM) / 2
show(region(lambda x, y: x * animelib.SCALE_X_CM < mid), "左半边亮")

print("4) 文字「枪神9」")
try:
    show(animelib.text_to_leds("枪神9", font_size=110), "文字", hold=5.0)
except Exception as e:
    print("   文字渲染失败:", e)

print("完成，当前停在文字图案")

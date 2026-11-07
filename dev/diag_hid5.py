# -*- coding: utf-8 -*-
"""HID 诊断第 5 轮：带零值图案的分步演示，验证协议与渲染映射。"""
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
    raise RuntimeError("未找到特征报告 640 字节的接口")


def send(dev, pkt):
    ok = _hid.HidD_SetFeature(dev.handle, bytes(pkt), len(pkt))
    if not ok:
        raise OSError(ctypes.get_last_error(), "SetFeature 失败")


dev = open_dev()
send(dev, animelib.init_packets()[0])
send(dev, animelib.init_packets()[1])
send(dev, animelib.flush_packet())
send(dev, animelib.enable_display_packet(True))
send(dev, animelib.flush_packet())
send(dev, animelib.brightness_packet(3))
send(dev, animelib.flush_packet())
print("已初始化，亮度=高")


def show(frame, label, hold=2.0):
    for p in animelib.frame_packets(frame):
        send(dev, p)
    send(dev, animelib.flush_packet())
    print(f"  -> {label}（保持 {hold}s）", flush=True)
    time.sleep(hold)


print("步骤 1：全灭（正确的话 A 面应完全变黑）")
show(bytes(animelib.LED_COUNT), "全灭", 2.5)

print("步骤 2：棋盘格（明暗相间的格子）")
chk = bytearray(animelib.LED_COUNT)
for i, (x, y) in enumerate(animelib.LEDS):
    chk[i] = 255 if (int(round(x)) + y) % 2 == 0 else 0
show(bytes(chk), "棋盘格", 2.5)

print("步骤 3：文字 (中英混排)")
try:
    txt = animelib.text_to_leds("ROG 枪神9", font_size=90, brightness=1.0)
    show(txt, "文字", 3.0)
except Exception as e:
    print("   文字渲染失败:", e)

print("步骤 4：仅描边（空心轮廓）")
border = bytearray(animelib.LED_COUNT)
for i, (x, y) in enumerate(animelib.LEDS):
    first = 0 if y < 28 else (y - 28) // 2
    width = (y // 2 + 1) if y < 28 else 15
    j = int(round(x + 0.5 * (y % 2) - first))
    border[i] = 255 if (y in (0, animelib.HEIGHT - 1) or j in (0, width - 1)) else 0
show(bytes(border), "仅描边", 1.0)

print("完成，当前停在描边图案")

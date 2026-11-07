# -*- coding: utf-8 -*-
"""试验：奥创灯效按 (u,v) 等比拉伸到灯板，看字母是否端正。"""
import glob

from PIL import Image

import animelib as A

path = glob.glob(r"C:\ProgramData\ASUS\ACStore\UserContent\*\matrix\*\*\Kinetic Stream.gif")[0]
im = Image.open(path)
im.seek(90)
fr = im.convert("RGBA")
iw, ih = fr.size
px = fr.load()

slot = {}
for lin, (u, v) in enumerate(A.LEDS):
    fx = (u - A.MIN_U) / (A.MAX_U - A.MIN_U)
    fy = (v - A.MIN_V) / (A.MAX_V - A.MIN_V)
    ix = min(iw - 1, max(0, int(fx * iw)))
    iy = min(ih - 1, max(0, int(fy * ih)))
    slot[lin] = (ix, iy)

out = bytearray(A.LED_COUNT)
for lin, (ix, iy) in slot.items():
    r, g, b, a = px[ix, iy]
    if a:
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        if lum > 20:
            out[lin] = min(255, int(lum * 1.2))

print("点亮:", sum(1 for x in out if x))
open(r"E:\dsh\anime-vision\fx_stretch_lid.png", "wb").write(A.lid_preview_png(bytes(out)))

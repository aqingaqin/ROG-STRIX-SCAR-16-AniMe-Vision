# -*- coding: utf-8 -*-
"""试验：把奥创灯效（68x49 的画稿）按 45° 映射到灯板，看是否能读出字母。"""
import glob
import math

from PIL import Image

import animelib as A

path = [p for p in glob.glob(r"C:\ProgramData\ASUS\ACStore\UserContent\*\matrix\*\*\Kinetic Stream.gif")][0]
im = Image.open(path)
im.seek(90)
fr = im.convert("RGBA")
iw, ih = fr.size
px = fr.load()

cu = (A.MIN_U + A.MAX_U) / 2.0
cv = (A.MIN_V + A.MAX_V) / 2.0
# 灯板在画稿中的菱形：对角线沿画稿的 x/y
sx = iw / 2.0 / max(1e-6, (A.MAX_U - A.MIN_U) / 2.0)
sy = ih / 2.0 / max(1e-6, (A.MAX_V - A.MIN_V) / 2.0)

out = bytearray(A.LED_COUNT)
for lin, (u, v) in enumerate(A.LEDS):
    du, dv = u - cu, v - cv
    # 旋转 45°
    rx = (du + dv) * math.sqrt(0.5)
    ry = (dv - du) * math.sqrt(0.5)
    ix = int(iw / 2 + rx * sx * 0.5)
    iy = int(ih / 2 + ry * sy * 0.5)
    if 0 <= ix < iw and 0 <= iy < ih:
        r, g, b, a = px[ix, iy]
        if a:
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            if lum > 20:
                out[lin] = min(255, int(lum * 1.2))

lit = sum(1 for x in out if x)
print("点亮:", lit)
open(r"E:\dsh\anime-vision\fx_rot45.png", "wb").write(A.lid_preview_png(bytes(out)))

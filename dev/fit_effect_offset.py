# -*- coding: utf-8 -*-
"""找出灯带在奥创灯效画稿（68x49，A 面坐标）中的最佳位置。"""
import glob

from PIL import Image

import animelib as A

root = r"C:\ProgramData\ASUS\ACStore\UserContent\*\matrix\*\*\*.gif"
paths = [p for p in glob.glob(root) if "thumbnail" not in p.lower()]

# 用几张代表性帧的平均亮度作为“内容丰富度”
frames = []
for p in paths:
    im = Image.open(p)
    n = getattr(im, "n_frames", 1)
    for k in (int(n * 0.2), int(n * 0.5), int(n * 0.8)):
        im.seek(max(0, min(n - 1, k)))
        frames.append(im.convert("RGB"))
print("采样帧数:", len(frames))

best = None
for dx in range(-90, 91, 10):
    for dy in range(-70, 71, 10):
        total = 0
        for fr in frames[:6]:
            px = fr.load()
            iw, ih = fr.size
            for (u, v) in A.LEDS:
                x, y = A._lid_xy(u, v)
                ix = int((x + dx) / 355.0 * iw)
                iy = int((y + dy) / 245.0 * ih)
                if 0 <= ix < iw and 0 <= iy < ih:
                    r, g, b = px[ix, iy]
                    total += (r + g + b) / 3.0
        if best is None or total > best[0]:
            best = (total, dx, dy)
print("最佳偏移: dx=%d mm, dy=%d mm, 亮度总和=%.0f" % (best[1], best[2], best[0]))

# 顺便看当前 (0,0) 有多亮
total0 = 0
for fr in frames[:6]:
    px = fr.load()
    iw, ih = fr.size
    for (u, v) in A.LEDS:
        x, y = A._lid_xy(u, v)
        ix = int(x / 355.0 * iw)
        iy = int(y / 245.0 * ih)
        if 0 <= ix < iw and 0 <= iy < ih:
            r, g, b = px[ix, iy]
            total0 += (r + g + b) / 3.0
print("当前 (0,0) 亮度总和=%.0f  →  提升 %.1f 倍" % (total0, best[0] / max(1.0, total0)))

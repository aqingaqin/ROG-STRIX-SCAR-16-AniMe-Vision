# -*- coding: utf-8 -*-
"""预览奥创所有灯效的某一帧。"""
import glob
import os

from PIL import Image

root = r"C:\ProgramData\ASUS\ACStore\UserContent\*\matrix\*\*\*.gif"
paths = [p for p in glob.glob(root) if "thumbnail" not in p.lower()]
paths.sort()

cells = []
for p in paths:
    try:
        im = Image.open(p)
        n = getattr(im, "n_frames", 1)
        im.seek(min(60, n - 1))
        cells.append((os.path.splitext(os.path.basename(p))[0], im.size, im.convert("RGB").copy()))
    except Exception as e:
        print("skip", p, e)

W, H = 190, 140
cols = 5
rows = (len(cells) + cols - 1) // cols
out = Image.new("RGB", (W * cols, H * rows), (25, 25, 30))
for i, (name, size, fr) in enumerate(cells):
    out.paste(fr.resize((W - 6, H - 6)), ((i % cols) * W + 3, (i // cols) * H + 3))
out.save(r"E:\dsh\anime-vision\fx_all.png")
print("\n".join(f"{n}: {s}" for n, s, _ in cells))

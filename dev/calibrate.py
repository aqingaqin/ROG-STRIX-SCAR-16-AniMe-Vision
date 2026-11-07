# -*- coding: utf-8 -*-
"""标定：把 68x34 的 webmatrix 画稿按不同映射贴到灯板，比较哪个不变形。"""
import animelib as A
from PIL import Image

p = r"C:\Users\zhehua\Downloads\ImportAnimation_G635_G835.webmatrix"
im = Image.open(p)
im.seek(60)
fr = im.convert("RGBA")
iw, ih = fr.size
px = fr.load()


def render(mode):
    out = bytearray(A.LED_COUNT)
    for lin, plx, ply in A.LED_TABLE:
        if mode == "uv_stretch":
            u, v = A.LEDS[lin]
            fx = (u - A.MIN_U) / (A.MAX_U - A.MIN_U)
            fy = (v - A.MIN_V) / (A.MAX_V - A.MIN_V)
        elif mode == "transpose":
            fx = ply / 67.0
            fy = plx / 33.0
        elif mode == "transpose_mirror":
            fx = 1.0 - ply / 67.0
            fy = plx / 33.0
        elif mode == "col_row":
            fx = plx / 33.0
            fy = ply / 67.0
        else:
            raise ValueError(mode)
        ix = min(iw - 1, max(0, int(fx * iw)))
        iy = min(ih - 1, max(0, int(fy * ih)))
        r, g, b, a = px[ix, iy]
        if a:
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            if lum > 20:
                out[lin] = min(255, int(lum * 1.2))
    return out


imgs = []
for m in ("uv_stretch", "transpose", "transpose_mirror", "col_row"):
    f = render(m)
    data = A.lid_preview_png(f)
    open(rf"E:\dsh\anime-vision\cal_{m}.png", "wb").write(data)
    imgs.append((m, Image.open(rf"E:\dsh\anime-vision\cal_{m}.png")))
    print(m, "点亮", sum(1 for x in f if x))

w = imgs[0][1].width // 2
h = imgs[0][1].height // 2
out = Image.new("RGB", (w * 4, h), (20, 20, 24))
for i, (m, img) in enumerate(imgs):
    out.paste(img.resize((w, h), Image.LANCZOS), (i * w, 0))
out.save(r"E:\dsh\anime-vision\cal_cmp.png")
print("saved cal_cmp.png")

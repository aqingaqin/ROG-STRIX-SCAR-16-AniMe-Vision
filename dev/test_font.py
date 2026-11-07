# -*- coding: utf-8 -*-
"""用华硕官方点阵字体渲染文字效果对比。"""
import os

from PIL import Image, ImageDraw, ImageFont

import animelib

FONT_STRIX = r"C:\Windows\Fonts\ROG FONTS STRIX SCAR REGULAR.ttf"
FONT_ROG = r"C:\Windows\Fonts\ROGFonts-Regular.otf"


def glyph(text, size, path):
    font = ImageFont.truetype(path, size)
    tmp = Image.new("L", (8, 8))
    bbox = ImageDraw.Draw(tmp).textbbox((0, 0), text, font=font)
    tw, th = max(1, bbox[2] - bbox[0]), max(1, bbox[3] - bbox[1])
    img = Image.new("L", (tw, th), 0)
    ImageDraw.Draw(img).text((-bbox[0], -bbox[1]), text, font=font, fill=255)
    return img


def frame_from(img, font_cells=14, flip_v=True):
    fc = min(15, font_cells)
    nw = max(1, int(round(img.width * fc / img.height)))
    g = img.resize((nw, fc), Image.NEAREST)
    strip = Image.new("L", (nw, 15), 0)
    strip.paste(g, (0, (15 - fc) // 2))
    if flip_v:
        strip = strip.transpose(Image.FLIP_TOP_BOTTOM)
    frame = bytearray(animelib.LED_COUNT)
    for idx, j, along in animelib.BAND_CELLS:
        sx = along % nw
        frame[idx] = strip.getpixel((sx, j))
    return bytes(frame)


for name, path in (("strix", FONT_STRIX), ("rog", FONT_ROG)):
    if not os.path.exists(path):
        print("missing", path)
        continue
    for size in (14, 16, 28):
        try:
            img = glyph("ROG 2025", size, path)
        except Exception as e:
            print(name, size, "渲染失败:", e)
            continue
        fr = frame_from(img)
        open(f"E:/dsh/anime-vision/font_{name}_{size}.png", "wb").write(
            animelib.frame_to_png(fr))
        print(f"{name} size={size} -> font_{name}_{size}.png 亮灯={sum(1 for v in fr if v)}")

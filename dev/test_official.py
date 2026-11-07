# -*- coding: utf-8 -*-
"""官方点阵字体 1:1 映射到 LED 网格的效果。"""
from PIL import Image, ImageDraw, ImageFont

import animelib

FONT = r"C:\Windows\Fonts\ROG FONTS STRIX SCAR REGULAR.ttf"


def strip_from(text, size=18):
    font = ImageFont.truetype(FONT, size)
    tmp = Image.new("L", (8, 8))
    bbox = ImageDraw.Draw(tmp).textbbox((0, 0), text, font=font)
    tw, th = max(1, bbox[2] - bbox[0]), max(1, bbox[3] - bbox[1])
    img = Image.new("L", (tw, th), 0)
    ImageDraw.Draw(img).text((-bbox[0], -bbox[1]), text, font=font, fill=255)
    strip = Image.new("L", (img.width, 15), 0)
    strip.paste(img, (0, max(0, (15 - img.height) // 2)))
    return strip


def frame_from(strip, flip_v=True, offset=0):
    s = strip.transpose(Image.FLIP_TOP_BOTTOM) if flip_v else strip
    nw = s.width
    frame = bytearray(animelib.LED_COUNT)
    for idx, j, along in animelib.BAND_CELLS:
        frame[idx] = s.getpixel(((along + offset) % nw, j))
    return bytes(frame)


for text in ("ROG 2025", "ROG", "10:42"):
    st = strip_from(text)
    fr = frame_from(st)
    name = text.replace(":", "").replace(" ", "_")
    open(f"E:/dsh/anime-vision/official_{name}.png", "wb").write(
        animelib.frame_to_png(fr))
    print(f"{text!r} 条带 {st.width}x{st.height} 亮灯={sum(1 for v in fr if v)}")

# 检查中文字形覆盖
try:
    st = strip_from("枪神9")
    fr = frame_from(st)
    open("E:/dsh/anime-vision/official_cn.png", "wb").write(animelib.frame_to_png(fr))
    print("中文测试: 亮灯 =", sum(1 for v in fr if v), "（0 表示字体不含中文字形）")
except Exception as e:
    print("中文渲染异常:", e)

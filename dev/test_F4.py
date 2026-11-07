# -*- coding: utf-8 -*-
"""四种朝向依次显示 F，用于确定正确字形变换。"""
import base64
import json
import time
import urllib.request

from PIL import Image, ImageDraw, ImageFont

import animelib

BASE = "http://127.0.0.1:8765"


def post(path, obj):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(obj).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def glyph_img(text="F", size=64, path=None):
    font = ImageFont.truetype(path or animelib._find_cjk_font(True), size)
    tmp = Image.new("L", (8, 8))
    bbox = ImageDraw.Draw(tmp).textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    img = Image.new("L", (tw, th), 0)
    ImageDraw.Draw(img).text((-bbox[0], -bbox[1]), text, font=font, fill=255)
    return img


def frame_from(img, font_cells=14):
    """把字形图缩放到 (nw, font_cells) 并居中放进 15 格高条带，按带坐标采样。"""
    fc = min(15, font_cells)
    nw = max(1, int(round(img.width * fc / img.height)))
    g = img.resize((nw, fc), Image.LANCZOS)
    strip = Image.new("L", (nw, 15), 0)
    strip.paste(g, (0, (15 - fc) // 2))
    frame = bytearray(animelib.LED_COUNT)
    for idx, j, along in animelib.BAND_CELLS:
        sx = along % nw
        frame[idx] = strip.getpixel((sx, j))
    return bytes(frame)


base = glyph_img("F")
variants = {
    "1_原样": base,
    "2_上下翻转": base.transpose(Image.FLIP_TOP_BOTTOM),
    "3_旋转90顺时针": base.transpose(Image.ROTATE_270),
    "4_旋转90逆时针": base.transpose(Image.ROTATE_90),
}

for name, img in variants.items():
    print(f"\n>>> 现在显示：{name}")
    post("/api/frame", {"data": base64.b64encode(frame_from(img)).decode()})
    time.sleep(5)
print("\n四种都已显示完毕")

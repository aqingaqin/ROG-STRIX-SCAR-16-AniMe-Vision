# -*- coding: utf-8 -*-
"""确认 STRIX 点阵字体的整数倍尺寸。"""
from PIL import Image, ImageDraw, ImageFont

path = r"C:\Windows\Fonts\ROG FONTS STRIX SCAR REGULAR.ttf"
for size in (9, 18, 27, 36, 45):
    font = ImageFont.truetype(path, size)
    bbox = font.getbbox("ROG")
    img = Image.new("L", (200, 80), 0)
    ImageDraw.Draw(img).text((2, 2), "ROG", font=font, fill=255)
    px = img.load()
    rows = [y for y in range(80) if any(px[x, y] > 100 for x in range(200))]
    cols = [x for x in range(200) if any(px[x, y] > 100 for y in range(80))]
    print(f"size={size:2d} bbox={bbox} 实际像素高度={len(rows)} 宽度={len(cols)}")
    if size in (18, 27):
        for y in rows[:14]:
            line = "".join("#" if px[x, y] > 100 else "." for x in range(60))
            print(f"   {y:2d} {line}")

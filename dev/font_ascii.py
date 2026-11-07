# -*- coding: utf-8 -*-
"""打印点阵字体的原生位图，判断其设计尺寸。"""
from PIL import Image, ImageDraw, ImageFont

FONTS = {
    "strix": r"C:\Windows\Fonts\ROG FONTS STRIX SCAR REGULAR.ttf",
    "rog": r"C:\Windows\Fonts\ROGFonts-Regular.otf",
    "msyh": r"C:\Windows\Fonts\msyhbd.ttc",
}

for name, path in FONTS.items():
    for size in (9, 12, 14, 16):
        try:
            font = ImageFont.truetype(path, size)
        except Exception as e:
            print(name, size, "load fail", e)
            continue
        img = Image.new("L", (120, 40), 0)
        ImageDraw.Draw(img).text((2, 2), "ROG", font=font, fill=255)
        px = img.load()
        rows = []
        for y in range(40):
            line = "".join("#" if px[x, y] > 100 else "." for x in range(40))
            if "#" in line:
                rows.append(f"{y:2d} {line}")
        print(f"\n--- {name} size={size} (bbox={font.getbbox('ROG')}) ---")
        print("\n".join(rows[:16]))

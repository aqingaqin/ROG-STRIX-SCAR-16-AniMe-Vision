# -*- coding: utf-8 -*-
"""对比不同字高/拉伸/灰度设置下的可读性。"""
import animelib

text = "ROG 枪神9"
cases = [
    ("A_12_1.0_gray", dict(font_cells=12, stretch=1.0, min_level=1)),
    ("B_12_1.4_gray", dict(font_cells=12, stretch=1.4, min_level=1)),
    ("C_14_1.0_gray", dict(font_cells=14, stretch=1.0, min_level=1)),
    ("D_10_1.2_gray", dict(font_cells=10, stretch=1.2, min_level=1)),
]
for name, kw in cases:
    frame = animelib.render_text_band(text, gap_cells=12, offset_cells=0, **kw)
    open(f"E:/dsh/anime-vision/opt_{name}.png", "wb").write(animelib.frame_to_png(frame))
    print(name, "亮灯=", sum(1 for v in frame if v))

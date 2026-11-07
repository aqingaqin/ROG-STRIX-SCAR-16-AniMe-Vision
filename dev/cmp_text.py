# -*- coding: utf-8 -*-
"""对比不同格高下的点阵文字清晰度。"""
import animelib

text = "ROG 枪神9"
for cells in (5, 6, 7, 8, 10):
    frame = animelib.render_text_band(text, font_cells=cells, gap_cells=max(8, cells),
                                      offset_cells=0)
    png = animelib.frame_to_png(frame)
    open(f"E:/dsh/anime-vision/cmp_{cells}.png", "wb").write(png)
    print(f"cells={cells} -> cmp_{cells}.png, 亮灯数={sum(1 for v in frame if v)}")

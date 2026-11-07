# -*- coding: utf-8 -*-
"""对比不同格高下的点阵文字清晰度。"""
import animelib

text = "ROG 枪神9"
for cells in (4, 5, 6, 7, 8):
    frame = animelib.render_text_band(text, font_cells=cells, gap_cells=6,
                                      offset_cells=0)
    png = animelib.frame_to_png(frame)
    open(f"E:/dsh/anime-vision/cmp2_{cells}.png", "wb").write(png)
    print(f"cells={cells} -> cmp2_{cells}.png 亮灯={sum(1 for v in frame if v)}")

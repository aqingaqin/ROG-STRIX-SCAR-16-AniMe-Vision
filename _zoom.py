# -*- coding: utf-8 -*-
"""临时：放大参考图的灯带区域，看清灯珠排布到底是正交网格还是菱形斜格。"""
from PIL import Image

p = r"C:\Users\zhehua\Desktop\h732.png"
im = Image.open(p).convert("RGB")
# 取灯带中段一块放大
crop = im.crop((150, 250, 350, 400))
crop = crop.resize((crop.width * 5, crop.height * 5), Image.NEAREST)
crop.save(r"E:\1234\anime-vision\_zoom.png")
print("saved", crop.size)

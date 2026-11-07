# -*- coding: utf-8 -*-
"""方向判定：显示单个大号 F，用来确定字形在灯带中的正确朝向。"""
import base64
import json
import time
import urllib.request

import animelib

BASE = "http://127.0.0.1:8765"


def post(path, obj):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(obj).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


frame = animelib.render_text_band("F", font_cells=14, gap_cells=8, offset_cells=0,
                                 stretch=1.0, min_level=1)
print(post("/api/frame", {"data": base64.b64encode(frame).decode()}))
time.sleep(0.4)
with urllib.request.urlopen(BASE + "/api/preview.png", timeout=10) as r:
    open("E:/dsh/anime-vision/preview_F.png", "wb").write(r.read())
print("F 已显示")

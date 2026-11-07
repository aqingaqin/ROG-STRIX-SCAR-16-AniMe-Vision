# -*- coding: utf-8 -*-
"""比例标定：显示一个 12x12 格的方块，判断面板横纵间距比。"""
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


frame = bytearray(animelib.LED_COUNT)
# 带内坐标：along 31..42（12 行），列 j 2..13（12 列）
for idx, j, along in animelib.BAND_CELLS:
    if 2 <= j <= 13 and 31 <= along <= 42:
        frame[idx] = 255

print(post("/api/frame", {"data": base64.b64encode(bytes(frame)).decode()}))
time.sleep(0.4)
with urllib.request.urlopen(BASE + "/api/preview.png", timeout=10) as r:
    open("E:/dsh/anime-vision/calib_square.png", "wb").write(r.read())
print("已显示 12x12 格方块")

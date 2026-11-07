# -*- coding: utf-8 -*-
"""坐标系判定：在平面坐标画十字（横线 ply=34，竖线 plx=17）。"""
import base64
import json
import time
import urllib.request

import animelib as A

BASE = "http://127.0.0.1:8765"


def post(path, obj):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(obj).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


frame = bytearray(A.LED_COUNT)
for lin, plx, ply in A.LED_TABLE:
    on = False
    if ply == 34:                      # 平面坐标的“横线”
        on = True
    if plx == 17:                      # 平面坐标的“竖线”
        on = True
    if on:
        frame[lin] = 255

print(post("/api/frame", {"data": base64.b64encode(bytes(frame)).decode()}))
time.sleep(0.5)
with urllib.request.urlopen(BASE + "/api/preview.png", timeout=10) as r:
    open("E:/dsh/anime-vision/cross_test.png", "wb").write(r.read())
print("已显示平面坐标的十字：横线 ply=34，竖线 plx=17")

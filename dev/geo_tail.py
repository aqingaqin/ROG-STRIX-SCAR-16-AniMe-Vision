# -*- coding: utf-8 -*-
"""几何验证：只点亮线序末尾 60 颗（751~810），看它们出现在面板哪里。"""
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
for i in range(750, animelib.LED_COUNT):
    frame[i] = 255

print("点亮线序 751~810 共 60 颗")
print(post("/api/frame", {"data": base64.b64encode(bytes(frame)).decode()}))
time.sleep(0.5)
with urllib.request.urlopen(BASE + "/api/preview.png", timeout=10) as r:
    open("E:/dsh/anime-vision/preview_tail.png", "wb").write(r.read())
print("预览已保存")

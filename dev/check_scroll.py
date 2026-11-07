# -*- coding: utf-8 -*-
"""验证滚动文字：连续采样预览图，确认不会长时间黑屏。"""
import io
import json
import time
import urllib.request

from PIL import Image

BASE = "http://127.0.0.1:8765"


def get(path):
    return urllib.request.urlopen(BASE + path, timeout=10).read()


def post(path, obj):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(obj).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


print("connect:", post("/api/connect", {}))
print("text:", post("/api/text", {"text": "ROG 枪神9", "size": 200,
                                  "rotate": True, "scroll": True, "speed": 80}))
print("连续采样 8 次（每 0.6s）：")
for i in range(8):
    png = get("/api/preview.png")
    img = Image.open(io.BytesIO(png)).convert("L")
    hist = img.histogram()
    lit = sum(hist[120:])          # 较亮的像素数量
    total = img.width * img.height
    print(f"  t={i*0.6:4.1f}s  png={len(png):5d}B  亮像素占比={lit/total*100:5.1f}%")
    time.sleep(0.6)

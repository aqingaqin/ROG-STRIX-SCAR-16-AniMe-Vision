# -*- coding: utf-8 -*-
"""慢速演示：每组停留 10 秒，中间黑屏分隔。"""
import base64
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8765"


def post(path, obj):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(obj).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"})
    return json.loads(urllib.request.urlopen(req, timeout=40).read())


def blank(dur=1.5):
    post("/api/frame", {"data": base64.b64encode(bytes(810)).decode()})
    time.sleep(dur)


presets = [
    ("第1组 拉伸1.6 不旋转", dict(stretch=1.6, rotate_deg=0)),
    ("第2组 拉伸1.6 旋转+30", dict(stretch=1.6, rotate_deg=30)),
    ("第3组 拉伸1.6 旋转-30", dict(stretch=1.6, rotate_deg=-30)),
    ("第4组 拉伸2.2 旋转-20", dict(stretch=2.2, rotate_deg=-20)),
]

for i, (name, kw) in enumerate(presets, 1):
    blank()
    print(f"\n>>> {name}（停留 10 秒）", flush=True)
    post("/api/text", {"text": "ROG 2025", "size": 280, "speed": 40,
                       "scroll": True, "brightness": 1.0, **kw})
    time.sleep(10)
print("\n演示结束，当前停在最后一组")

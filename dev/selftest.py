# -*- coding: utf-8 -*-
"""对运行中的控制台做一轮自测：图片 / GIF / 系统信息。"""
import base64
import io
import json
import urllib.request

BASE = "http://127.0.0.1:8765"


def post(path, obj):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(obj).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def get_png(path, out):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        data = r.read()
    open(out, "wb").write(data)
    return len(data)


from PIL import Image, ImageDraw

# ---------- 1) 图片：同心圆 + 渐变 ----------
img = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
for i in range(10, 0, -1):
    r = i * 24
    v = int(255 * (1 - i / 11))
    d.ellipse([256 - r, 256 - r, 256 + r, 256 + r], outline=(v, v, v, 255), width=14)
d.ellipse([256 - 60, 256 - 60, 256 + 60, 256 + 60], fill=(255, 255, 255, 255))
buf = io.BytesIO()
img.save(buf, "PNG")
print("image:", post("/api/image", {"data": base64.b64encode(buf.getvalue()).decode(),
                                    "brightness": 1.0, "rotate": False}))
print("  preview bytes:", get_png("/api/preview.png", "E:/dsh/anime-vision/preview_img.png"))

# ---------- 2) GIF：滚动方块 ----------
frames = []
for k in range(12):
    fr = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    dd = ImageDraw.Draw(fr)
    x = k * 24
    dd.rectangle([x, 100, x + 80, 200], fill=(255, 255, 255, 255))
    frames.append(fr)
buf = io.BytesIO()
frames[0].save(buf, "GIF", save_all=True, append_images=frames[1:],
               duration=120, loop=0)
print("gif:", post("/api/gif", {"data": base64.b64encode(buf.getvalue()).decode(),
                                "loops": 0, "brightness": 1.0, "rotate": False}))
import time
time.sleep(0.4)
print("  preview bytes:", get_png("/api/preview.png", "E:/dsh/anime-vision/preview_gif.png"))

# ---------- 3) 系统信息 ----------
print("sysinfo:", post("/api/sysinfo", {"battery": True, "cpu": True}))
time.sleep(0.6)
print("  preview bytes:", get_png("/api/preview.png", "E:/dsh/anime-vision/preview_sys.png"))

print("state:", json.loads(urllib.request.urlopen(BASE + "/api/state").read().decode()))

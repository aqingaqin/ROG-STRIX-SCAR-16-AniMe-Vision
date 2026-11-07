# -*- coding: utf-8 -*-
"""临时：量出 h732.png 里灯珠的点阵——间距与两个基矢方向。"""
import numpy as np
from PIL import Image
from collections import deque

p = r"C:\Users\zhehua\Desktop\h732.png"
im = Image.open(p).convert("RGB")
a = np.asarray(im, dtype=np.float32)
H, W, _ = a.shape
r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
lum = a.mean(2)

# 灯珠：中性偏白的亮点，限制在面板内（避开青色眼和边框）
inner = np.zeros((H, W), bool)
inner[150:590, 80:660] = True
cyan = (g > 140) & (b > 150) & (r < 150)
mask = (lum > 95) & (np.abs(r - b) < 55) & (np.abs(g - b) < 55) & inner & ~cyan

# 连通域取质心
seen = np.zeros((H, W), bool)
cents = []
for y in range(H):
    for x in range(W):
        if mask[y, x] and not seen[y, x]:
            q = deque([(y, x)])
            seen[y, x] = True
            pts = []
            while q:
                cy, cx = q.popleft()
                pts.append((cx, cy))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < H and 0 <= nx < W and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        q.append((ny, nx))
            if 2 <= len(pts) <= 60:
                arr = np.array(pts, np.float32)
                cents.append((arr[:, 0].mean(), arr[:, 1].mean()))

cents = np.array(cents, np.float32)
print("检测到灯珠:", len(cents))
if len(cents) < 10:
    raise SystemExit("点太少")

# 最近邻间距统计
d = np.linalg.norm(cents[:, None, :] - cents[None, :, :], axis=2)
np.fill_diagonal(d, 1e9)
nn = d.min(1)
print("最近邻间距: 中位 %.2f px, 25%%=%.2f, 75%%=%.2f"
      % (np.median(nn), np.percentile(nn, 25), np.percentile(nn, 75)))

# 第二近邻方向：取每个点的 6 个最近邻，统计向量角度
vecs = []
for i in range(len(cents)):
    idx = np.argsort(d[i])[:6]
    for j in idx:
        if d[i, j] < np.median(nn) * 1.6:
            vecs.append(cents[j] - cents[i])
vecs = np.array(vecs)
ang = np.degrees(np.arctan2(vecs[:, 1], vecs[:, 0])) % 180
hist, edges = np.histogram(ang, bins=36, range=(0, 180))
top = np.argsort(hist)[::-1][:4]
print("主导方向（度）:")
for t in top:
    if hist[t] > 5:
        print("   %.0f°  计数 %d" % ((edges[t] + edges[t + 1]) / 2, hist[t]))
print("平均向量长度 %.2f px" % np.linalg.norm(vecs, axis=1).mean())

# 灯带包围盒
print("灯珠 bbox: x %.0f..%.0f  y %.0f..%.0f"
      % (cents[:, 0].min(), cents[:, 0].max(), cents[:, 1].min(), cents[:, 1].max()))

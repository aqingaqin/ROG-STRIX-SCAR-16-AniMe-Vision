# -*- coding: utf-8 -*-
"""生成一段测试音（40Hz~16kHz 扫频 + 节拍），用于验证音乐可视化。"""
import wave

import numpy as np

rate = 48000
dur = 20.0
t = np.arange(int(rate * dur)) / rate

# 扫频
f0, f1 = 60.0, 14000.0
k = (f1 / f0) ** (1.0 / dur)
phase = 2 * np.pi * f0 * ((k ** t - 1) / np.log(k))
sig = 0.35 * np.sin(phase)

# 节拍包络（2Hz）
env = 0.5 + 0.5 * np.sin(2 * np.pi * 2.0 * t) ** 4
sig = sig * env

# 低音鼓点
for i in range(int(dur * 2)):
    start = int(i * rate / 2)
    n = int(rate * 0.25)
    tt = np.arange(n) / rate
    drum = 0.5 * np.sin(2 * np.pi * 60 * tt) * np.exp(-tt * 18)
    end = min(len(sig), start + n)
    sig[start:end] += drum[: end - start]

sig = np.clip(sig, -1, 1)
data = (sig * 32767).astype(np.int16)
stereo = np.repeat(data[:, None], 2, axis=1)

with wave.open(r"E:\dsh\anime-vision\dev\tone.wav", "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(rate)
    w.writeframes(stereo.tobytes())
print("tone.wav written, 20s")

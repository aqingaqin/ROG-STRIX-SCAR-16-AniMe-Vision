# -*- coding: utf-8 -*-
"""HID 诊断第 3 轮：SetupAPI 拿路径 → 打开 → 冒烟点亮。"""
import ctypes

import animelib

print("== 1) SetupAPI 枚举灯板接口 ==")
found = animelib.find_anime_paths()
print(f"  找到 {len(found)} 条:")
for p in found:
    print("   ", p)

print("\n== 2) 打开并读取 HID 能力 ==")
opened = None
for p in found:
    try:
        dev = animelib.AnimeDevice(p)
        dev.open()
        print("OPEN OK:", p)
        if dev.caps:
            c = dev.caps
            print(f"   UsagePage=0x{c.UsagePage:04X} Usage=0x{c.Usage:04X} "
                  f"In={c.InputReportByteLength} Out={c.OutputReportByteLength} "
                  f"Feat={c.FeatureReportByteLength}")
            if c.OutputReportByteLength >= animelib.PACKET_SIZE:
                opened = dev
                continue
        dev.close()
    except OSError as e:
        print("OPEN FAIL:", e)

print("\n== 3) 若可用，直接冒烟点亮 ==")
if opened:
    import smoke_test
    print("发送初始化包 ...")
    opened.init()
    print("设置亮度=中 ...")
    opened.set_brightness(2)
    print("发送测试图案 ...")
    opened.send_frame(smoke_test.test_pattern())
    print(">>> 完成！请查看笔记本 A 面（或合盖）是否出现：面板描边 + 十字 + 上暗下亮 <<<")
else:
    print("未能打开任何灯板接口。")

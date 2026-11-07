# -*- coding: utf-8 -*-
"""HID 诊断：注册表枚举 + 直接打开 + SetupAPI 对照。"""
import ctypes
import winreg

import animelib

print("== 1) 注册表枚举 Enum\\HID 下 VID_0B05&PID_193B ==")
paths = []
try:
    base = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                          r"SYSTEM\CurrentControlSet\Enum\HID")
    i = 0
    while True:
        try:
            k1 = winreg.EnumKey(base, i)
            i += 1
        except OSError:
            break
        if "vid_0b05&pid_193b" not in k1.lower():
            continue
        sub = winreg.OpenKey(base, k1)
        j = 0
        while True:
            try:
                k2 = winreg.EnumKey(sub, j)
                j += 1
            except OSError:
                break
            inst = k1 + "\\" + k2
            paths.append("\\\\?\\hid#" + inst.replace("\\", "#").lower()
                         + "#{4d1e55b2-f16c-11cf-88cb-001111000030}")
        winreg.CloseKey(sub)
    winreg.CloseKey(base)
except Exception as e:
    print("注册表读取失败:", e)

print(f"构造出 {len(paths)} 条设备路径")
for p in paths:
    print("   ", p)

print("\n== 2) 直接打开并读取 HID 能力 ==")
for p in paths:
    try:
        dev = animelib.AnimeDevice(p)
        dev.open()
        print("OPEN OK:", p)
        if dev.caps:
            c = dev.caps
            print(f"   UsagePage=0x{c.UsagePage:04X} Usage=0x{c.Usage:04X} "
                  f"In={c.InputReportByteLength} Out={c.OutputReportByteLength} "
                  f"Feat={c.FeatureReportByteLength}")
        else:
            print("   无 caps")
        dev.close()
    except OSError as e:
        print("OPEN FAIL:", e)

print("\n== 3) SetupAPI 枚举对照 ==")
lst = animelib.enumerate_hid_paths()
print(f"SetupAPI 共枚举到 {len(lst)} 条")
for p, ok in lst[:10]:
    print("   ", ("[灯板] " if ok else "[其他] ") + p)

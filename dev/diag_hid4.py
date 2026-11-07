# -*- coding: utf-8 -*-
"""HID 诊断第 4 轮：找出正确的写入方式（Feature 报告 vs 输出报告）。"""
import ctypes
from ctypes import wintypes

import animelib

_hid = ctypes.WinDLL("hid", use_last_error=True)
_hid.HidD_SetFeature.argtypes = [wintypes.HANDLE, ctypes.c_char_p, wintypes.DWORD]
_hid.HidD_SetFeature.restype = wintypes.BOOL
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_char_p, wintypes.DWORD,
                           ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
_k32.WriteFile.restype = wintypes.BOOL
_k32.GetLastError.restype = wintypes.DWORD

paths = animelib.find_anime_paths()
print(f"找到 {len(paths)} 个接口")

dev = None
for p in paths:
    d = animelib.AnimeDevice(p)
    d.open()
    c = d.caps
    if c and c.FeatureReportByteLength >= 640:
        dev = d
        print(f"使用接口: {p}")
        print(f"  Feature={c.FeatureReportByteLength} Output={c.OutputReportByteLength}")
        break
    d.close()

if not dev:
    raise SystemExit("没有特征报告长度 >= 640 的接口")

pkt = animelib.init_packets()[0]
attempts = []


def try_set_feature(buf):
    ok = _hid.HidD_SetFeature(dev.handle, bytes(buf), len(buf))
    return bool(ok), ctypes.get_last_error()


def try_write(buf):
    n = wintypes.DWORD(0)
    ok = _k32.WriteFile(dev.handle, bytes(buf), len(buf), ctypes.byref(n), None)
    return bool(ok), ctypes.get_last_error()


print("\n== 尝试各种写入方式（发送初始化包1） ==")
methods = [
    ("SetFeature 641(0x00+640)", lambda: try_set_feature(b"\x00" + bytes(pkt))),
    ("SetFeature 640(raw)", lambda: try_set_feature(bytes(pkt))),
    ("SetFeature 647(0x00+640+6pad)", lambda: try_set_feature(b"\x00" + bytes(pkt) + b"\x00" * 6)),
    ("WriteFile 641(0x00+640)", lambda: try_write(b"\x00" + bytes(pkt))),
    ("WriteFile 640(raw)", lambda: try_write(bytes(pkt))),
]
good = []
for name, fn in methods:
    ok, err = fn()
    print(f"  {name}: ok={ok} lasterr={err}")
    if ok:
        good.append(name)

print("\n可用方式:", good if good else "无")

if good:
    import smoke_test
    print("\n== 用第一个可用方式冒烟点亮 ==")
    method = good[0]

    def send(p):
        ok, err = (try_set_feature if method.startswith("SetFeature") else try_write)(
            b"\x00" + bytes(p) if "641" in method else bytes(p))
        if not ok:
            print(f"    发送失败 lasterr={err}")
        return ok

    print("  初始化包2 + 刷新 ...")
    send(animelib.init_packets()[1])
    send(animelib.flush_packet())
    print("  设置亮度=中 ...")
    send(animelib.brightness_packet(2))
    send(animelib.flush_packet())
    print("  发送测试图案 ...")
    for p in animelib.frame_packets(smoke_test.test_pattern()):
        send(p)
    send(animelib.flush_packet())
    print(">>> 完成！请查看笔记本 A 面（或合盖）是否出现：面板描边 + 十字 + 上暗下亮 <<<")

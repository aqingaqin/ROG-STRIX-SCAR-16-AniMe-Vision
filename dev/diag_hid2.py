# -*- coding: utf-8 -*-
"""HID 诊断第 2 轮：用 DeviceClasses 注册表拿真实接口路径。"""
import ctypes
import winreg

import animelib

GUID_HID = "{4d1e55b2-f16f-11cf-88cb-001111000030}"

print("== 1) DeviceClasses 注册的 HID 接口（筛选 VID_0B05&PID_193B） ==")
found = []
base = winreg.OpenKey(
    winreg.HKEY_LOCAL_MACHINE,
    r"SYSTEM\CurrentControlSet\Control\DeviceClasses" + "\\" + GUID_HID)
i = 0
while True:
    try:
        name = winreg.EnumKey(base, i)
        i += 1
    except OSError:
        break
    if "vid_0b05&pid_193b" not in name.lower():
        continue
    try:
        val = winreg.QueryValueEx(base, name)[0]
    except OSError:
        val = "(无默认值)"
    print("  key:", name)
    print("  val:", val)
    if isinstance(val, str) and val.startswith("\\\\"):
        found.append(val)
winreg.CloseKey(base)
print(f"  共 {len(found)} 条符号链接")

print("\n== 2) 尝试打开 ==")
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

print("\n== 3) SetupAPI 逐步错误码 ==")
s = animelib._setupapi
guid = animelib._make_guid(animelib.GUID_DEVINTERFACE_HID_STR)
di = s.SetupDiGetClassDevsW(ctypes.byref(guid), None, None,
                            animelib.DIGCF_PRESENT | animelib.DIGCF_DEVICEINTERFACE)
print("  GetClassDevs 返回:", hex(di) if di not in (0, animelib.INVALID_HANDLE_VALUE) else di,
      "lasterr:", ctypes.get_last_error())
for idx in range(3):
    data = animelib.SP_DEVICE_INTERFACE_DATA()
    data.cbSize = ctypes.sizeof(animelib.SP_DEVICE_INTERFACE_DATA)
    ok = s.SetupDiEnumDeviceInterfaces(di, None, ctypes.byref(guid), idx,
                                       ctypes.byref(data))
    print(f"  Enum idx={idx}: ok={ok} cbSize={data.cbSize} "
          f"GUID=0x{data.InterfaceClassGuid.Data1:08X} lasterr={ctypes.get_last_error()}")

print("\n== 4) 若打开成功，直接冒烟点亮 ==")
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
    print("未能打开任何灯板接口，跳过点亮。")

# -*- coding: utf-8 -*-
"""
animelib.py — ROG AniMe Vision 控制库（枪神9超竞版 G635L / G835L）
====================================================================
硬件通路（已在本机实测确认）：
  * USB HID  VID_0B05 & PID_193B，使用 Col02 集合
  * 通道：HID **Feature 报告**，长度必须正好 640 字节（HidD_SetFeature，无报告 ID 前缀）
  * 每包：byte0=0x5E；数据包头 [0x5E,0xC0,0x02, 起始LO, 起始HI, 长度LO, 长度HI]
  * 810 颗 LED 分两包：LED 1..490 + LED 491..810，写完后发 [0x5E,0xC0,0x03] 刷新
  * 亮度 [0x5E,0xC0,0x04,0..3]；显示开关 [0x5E,0xC3,0x01,0x00|0x80]；初始化 [0x5E]+"ASUS Tech.Inc." 与 [0x5E,0xC2]

面板几何（实测确认）：
  * 线序 #1..#210  = 左上角三角区（0-27 行，行宽 1,1,2,2,...,14,14）
  * 线序 #211..#810 = 斜带（28-67 行，每行 15 颗，逐行右移半格）
  * 物理比例：横向 0.77 cm/单位，纵向 0.28 cm/单位，包围盒约 25.8 x 19.0 cm
"""

import ctypes
import math
import threading
import time
from ctypes import wintypes

# ================================================================ 常量

VID = 0x0B05
PID = 0x193B

PACKET_SIZE = 640
DEV_PAGE = 0x5E
LED_COUNT = 810
PANE1_LEN = 490
PANE2_LEN = 320
HEIGHT = 68

SCALE_X_CM = 0.77
SCALE_Y_CM = 0.28

GUID_DEVINTERFACE_HID_STR = "{4D1E55B2-F16F-11CF-88CB-001111000030}"

# ================================================================ LED 布局
#
# 几何模型对齐 g-helper 的 AniMeMatrixDevice (STRIX 分支)：
#   MaxColumns=34, MaxRows=68, FullRows=29, LedCount=810
#   行宽 Width(y) = 1 + y/2；起始列 FirstX(y) = ceil(max(0, y-FullRows)/2)
#   每行 LED 数 Pitch(y) = Width(y) - FirstX(y)
#   线序（线性地址）= RowStart(y) + (x - FirstX(y))
#
# 关键：面板物理网格是 45° 旋转的。g-helper 用 Planar() 把「对角(视觉)坐标」
# 旋转成「平面(寻址)坐标」，因此想要文字水平显示，必须在对角坐标系里渲染。

PLANAR_ROWS = 68            # MaxRows
PLANAR_FULL_ROWS = 29       # FullRows
TEXT_DELTA_X = 9            # 5 + 4（STRIX）
TEXT_DELTA_Y = PLANAR_ROWS - PLANAR_FULL_ROWS - PLANAR_FULL_ROWS // 2 - 1   # = 24
TEXT_BITMAP_HEIGHT = PLANAR_ROWS - PLANAR_FULL_ROWS                          # = 39


def planar_width(y):
    """该行 LED 数（含被裁掉的左侧列）。"""
    return 1 + y // 2


def planar_first_x(y):
    """该行起始列。"""
    return int(math.ceil(max(0, y - PLANAR_FULL_ROWS) / 2.0))


def planar_pitch(y):
    return planar_width(y) - planar_first_x(y)


_ROW_START = []
_acc = 0
for _y in range(PLANAR_ROWS):
    _ROW_START.append(_acc)
    _acc += planar_pitch(_y)
assert _acc == LED_COUNT, f"LED 总数 {_acc} != {LED_COUNT}"


def _led_table():
    """[(线性下标, 平面x, 平面y)]，按线性下标排序。"""
    out = []
    for y in range(PLANAR_ROWS):
        fx = planar_first_x(y)
        for x in range(fx, planar_width(y)):
            out.append((_ROW_START[y] - fx + x, x, y))
    out.sort(key=lambda t: t[0])
    return out


LED_TABLE = _led_table()


def planar_to_visual(plx, ply):
    """平面坐标 → 视觉(对角)坐标（Planar 的逆变换，45° 旋转）。"""
    return (ply / 2.0 + plx - TEXT_DELTA_X,
            ply / 2.0 - plx + TEXT_DELTA_Y)


LEDS = [planar_to_visual(x, y) for _, x, y in LED_TABLE]
_VIS_U = [u for u, _ in LEDS]
_VIS_V = [v for _, v in LEDS]
MIN_U, MAX_U = min(_VIS_U), max(_VIS_U)
MIN_V, MAX_V = min(_VIS_V), max(_VIS_V)
PANEL_UNITS_W = MAX_U - MIN_U + 1.0
PANEL_UNITS_H = MAX_V - MIN_V + 1.0
MIN_X_UNIT = MIN_U
MIN_Y_UNIT = MIN_V
PX_PER_UNIT = 8.0

# 兼容旧接口（单位 = 格）
PANEL_W_CM = PANEL_UNITS_W
PANEL_H_CM = PANEL_UNITS_H
HEIGHT = PLANAR_ROWS
RIBBON_ANGLE_DEG = 0.0      # 视觉坐标系下不再需要旋转

# 视觉坐标系的画布尺寸（供文字/图片排版参考）
VIS_W = PANEL_UNITS_W
VIS_H = PANEL_UNITS_H

# ================================================================ 协议封包

def _pkt(*payload):
    p = bytearray(PACKET_SIZE)
    p[0] = DEV_PAGE
    for i, b in enumerate(payload, start=1):
        p[i] = b
    return p


def init_packets():
    p1 = bytearray(PACKET_SIZE)
    p1[0] = DEV_PAGE
    p1[1:1 + 14] = b"ASUS Tech.Inc."
    p2 = bytearray(PACKET_SIZE)
    p2[0] = DEV_PAGE
    p2[1] = 0xC2
    return [p1, p2]


def flush_packet():
    return _pkt(0xC0, 0x03)


def brightness_packet(level):
    return _pkt(0xC0, 0x04, int(level) & 0xFF)


def enable_display_packet(on):
    return _pkt(0xC3, 0x01, 0x00 if on else 0x80)


def frame_packets(data):
    """810 字节亮度数据 -> 两个 640 字节数据包。"""
    if len(data) != LED_COUNT:
        raise ValueError(f"数据长度必须为 {LED_COUNT} 字节，实际 {len(data)}")
    p1 = bytearray(PACKET_SIZE)
    p2 = bytearray(PACKET_SIZE)
    p1[0:7] = bytes([0x5E, 0xC0, 0x02, 0x01, 0x00, 0xEA, 0x01])   # start=1   len=490
    p2[0:7] = bytes([0x5E, 0xC0, 0x02, 0xEB, 0x01, 0x40, 0x01])   # start=491 len=320
    p1[7:7 + PANE1_LEN] = data[:PANE1_LEN]
    p2[7:7 + PANE2_LEN] = data[PANE1_LEN:]
    return [p1, p2]


# ================================================================ Win32 封装

class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


def _make_guid(s):
    from uuid import UUID
    u = UUID(s)
    return GUID(u.time_low, u.time_mid, u.time_hi_version,
                (ctypes.c_ubyte * 8)(*u.bytes[8:16]))


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("InterfaceClassGuid", GUID),
                ("Flags", wintypes.DWORD), ("Reserved", ctypes.c_size_t)]


class SP_DEVICE_INTERFACE_DETAIL_DATA_W(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("DevicePath", wintypes.WCHAR * 1)]


class HIDP_CAPS(ctypes.Structure):
    _fields_ = [
        ("Usage", wintypes.USHORT), ("UsagePage", wintypes.USHORT),
        ("InputReportByteLength", wintypes.USHORT),
        ("OutputReportByteLength", wintypes.USHORT),
        ("FeatureReportByteLength", wintypes.USHORT),
        ("Reserved", wintypes.USHORT * 17),
        ("NumberLinkCollectionNodes", wintypes.USHORT),
        ("NumberInputButtonCaps", wintypes.USHORT),
        ("NumberInputValueCaps", wintypes.USHORT),
        ("NumberInputDataIndices", wintypes.USHORT),
        ("NumberOutputButtonCaps", wintypes.USHORT),
        ("NumberOutputValueCaps", wintypes.USHORT),
        ("NumberOutputDataIndices", wintypes.USHORT),
        ("NumberFeatureButtonCaps", wintypes.USHORT),
        ("NumberFeatureValueCaps", wintypes.USHORT),
        ("NumberFeatureDataIndices", wintypes.USHORT),
    ]


_setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_hid = ctypes.WinDLL("hid", use_last_error=True)

_setupapi.SetupDiGetClassDevsW.argtypes = [
    ctypes.POINTER(GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
_setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE
_setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(GUID),
    wintypes.DWORD, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA)]
_setupapi.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL
_setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
    wintypes.HANDLE, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA), ctypes.c_void_p,
    wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
_setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL
_setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]

_kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
_kernel32.CreateFileW.restype = wintypes.HANDLE
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

_hid.HidD_GetPreparsedData.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
_hid.HidD_GetPreparsedData.restype = wintypes.BOOL
_hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]
_hid.HidP_GetCaps.restype = ctypes.c_long
_hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
_hid.HidD_SetFeature.argtypes = [wintypes.HANDLE, ctypes.c_char_p, wintypes.DWORD]
_hid.HidD_SetFeature.restype = wintypes.BOOL

INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x80
DIGCF_PRESENT = 0x00000002
DIGCF_DEVICEINTERFACE = 0x00000010


def _guid_hid():
    return _make_guid(GUID_DEVINTERFACE_HID_STR)


def enumerate_hid_paths():
    """枚举全部 HID 设备接口路径，返回 (路径, 是否视频/灯板) 列表。"""
    guid = _guid_hid()
    dev_info = _setupapi.SetupDiGetClassDevsW(
        ctypes.byref(guid), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
    if dev_info == INVALID_HANDLE_VALUE:
        raise OSError(ctypes.get_last_error(), "SetupDiGetClassDevsW 失败")
    out = []
    try:
        idx = 0
        while True:
            data = SP_DEVICE_INTERFACE_DATA()
            data.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
            if not _setupapi.SetupDiEnumDeviceInterfaces(
                    dev_info, None, ctypes.byref(guid), idx, ctypes.byref(data)):
                break
            idx += 1
            required = wintypes.DWORD(0)
            _setupapi.SetupDiGetDeviceInterfaceDetailW(
                dev_info, ctypes.byref(data), None, 0, ctypes.byref(required), None)
            if not required.value:
                continue
            buf = ctypes.create_string_buffer(required.value)
            detail = ctypes.cast(buf, ctypes.POINTER(SP_DEVICE_INTERFACE_DETAIL_DATA_W))
            detail.contents.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA_W)
            if _setupapi.SetupDiGetDeviceInterfaceDetailW(
                    dev_info, ctypes.byref(data), buf, required.value, None, None):
                out.append(ctypes.wstring_at(ctypes.addressof(buf) + 4))
    finally:
        _setupapi.SetupDiDestroyDeviceInfoList(dev_info)
    needle = f"vid_{VID:04x}&pid_{PID:04x}".lower()
    return [(p, needle in p.lower()) for p in out]


def find_anime_paths():
    paths = [p for p, ok in enumerate_hid_paths() if ok]
    if not paths:
        paths = _paths_from_registry()
    return paths


def _paths_from_registry():
    """备用：从 Control\\DeviceClasses 读取（若存在默认值）。"""
    import winreg
    out = []
    needle = f"vid_{VID:04x}&pid_{PID:04x}".lower()
    try:
        base = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            "SYSTEM\\CurrentControlSet\\Control\\DeviceClasses\\"
            + GUID_DEVINTERFACE_HID_STR)
    except OSError:
        return out
    try:
        i = 0
        while True:
            try:
                name = winreg.EnumKey(base, i)
                i += 1
            except OSError:
                break
            if needle not in name.lower():
                continue
            try:
                val = winreg.QueryValueEx(base, name)[0]
            except OSError:
                continue
            if isinstance(val, str) and val.startswith("\\\\"):
                out.append(val)
    finally:
        winreg.CloseKey(base)
    return out


def _caps_of(handle):
    ppd = ctypes.c_void_p()
    caps = HIDP_CAPS()
    if _hid.HidD_GetPreparsedData(handle, ctypes.byref(ppd)) and ppd.value:
        try:
            if _hid.HidP_GetCaps(ppd.value, ctypes.byref(caps)) >= 0:
                return caps
        finally:
            _hid.HidD_FreePreparsedData(ppd.value)
    return None


class AnimeDevice:
    """灯板设备句柄（低层）。写入走 640 字节 Feature 报告。"""

    def __init__(self, path=None):
        self.path = path
        self.handle = None
        self.caps = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()

    def open(self, path=None):
        if path:
            self.path = path
        h = _kernel32.CreateFileW(
            self.path, GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE, None,
            OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, None)
        if h == INVALID_HANDLE_VALUE:
            raise OSError(ctypes.get_last_error(), f"无法打开设备 {self.path}")
        self.handle = h
        self.caps = _caps_of(h)
        return self

    def close(self):
        if self.handle:
            _kernel32.CloseHandle(self.handle)
            self.handle = None

    def write_packet(self, packet):
        """写入 640 字节包（Feature 报告，无报告 ID 前缀）。"""
        if len(packet) != PACKET_SIZE:
            raise ValueError(f"包大小必须为 {PACKET_SIZE}，实际 {len(packet)}")
        ok = _hid.HidD_SetFeature(self.handle, bytes(packet), PACKET_SIZE)
        if not ok:
            raise OSError(ctypes.get_last_error(), "HidD_SetFeature 失败")
        return PACKET_SIZE

    def init(self):
        for p in init_packets():
            self.write_packet(p)
        self.write_packet(flush_packet())

    def set_brightness(self, level):
        self.write_packet(brightness_packet(level))
        self.write_packet(flush_packet())

    def enable_display(self, on):
        self.write_packet(enable_display_packet(on))
        self.write_packet(flush_packet())

    def send_frame(self, data):
        for p in frame_packets(data):
            self.write_packet(p)
        self.write_packet(flush_packet())

    def clear(self):
        self.send_frame(bytes(LED_COUNT))


def open_anime(verbose=True):
    """打开灯板（选特征报告 >= 640 字节的集合）。"""
    paths = find_anime_paths()
    if not paths:
        raise RuntimeError("未找到 AniMe Vision 设备（VID_0B05 PID_193B）")
    last_err = None
    for path in paths:
        try:
            dev = AnimeDevice(path)
            dev.open()
            feat = dev.caps.FeatureReportByteLength if dev.caps else 0
            if verbose:
                print(f"  尝试 {path}\n    特征报告长度={feat}")
            if feat >= PACKET_SIZE:
                return dev
            dev.close()
        except OSError as e:
            last_err = e
            if verbose:
                print(f"  打开失败: {e}")
    if last_err:
        raise last_err
    raise RuntimeError("没有可用的 640 字节特征报告集合")


# ================================================================ 面板（带后台刷新线程）

class Panel:
    """灯板控制器：后台线程持续刷新当前帧，压制奥创的覆盖。"""

    def __init__(self, fps=None, keepalive_hz=None):
        import os
        self.fps = int(fps or os.environ.get("ANIME_FPS", "40"))
        self.keepalive_hz = float(keepalive_hz or os.environ.get(
            "ANIME_KEEPALIVE", str(self.fps)))
        self.dev = None
        self.brightness = 2
        self.display_on = True
        self._frame = bytes(LED_COUNT)
        self._lock = threading.Lock()
        self._dirty = threading.Event()
        self._run = False
        self._th = None
        self._last_write = 0.0
        self.error = None

    # -- 连接 -------------------------------------------------------
    @property
    def connected(self):
        return self.dev is not None

    def open(self):
        if self.dev:
            return True
        self.dev = open_anime(verbose=False)
        self.dev.init()
        self.dev.set_brightness(self.brightness)
        self.dev.enable_display(self.display_on)
        self.start()
        return True

    def close(self):
        self.stop()
        if self.dev:
            self.dev.close()
            self.dev = None

    # -- 帧控制 -----------------------------------------------------
    def set_frame(self, data):
        with self._lock:
            self._frame = bytes(data)
        self._dirty.set()

    def set_brightness(self, level):
        self.brightness = int(level) & 0x3
        if self.dev:
            self.dev.set_brightness(self.brightness)

    def enable_display(self, on):
        self.display_on = bool(on)
        if self.dev:
            self.dev.enable_display(self.display_on)

    # -- 刷新线程 ---------------------------------------------------
    def start(self):
        if self._run:
            return
        self._run = True
        self._th = threading.Thread(target=self._loop, daemon=True)
        self._th.start()

    def stop(self):
        self._run = False
        if self._th:
            self._th.join(timeout=1.0)
            self._th = None

    def _loop(self):
        period = 1.0 / max(1, self.fps)
        keep = (1.0 / self.keepalive_hz) if self.keepalive_hz > 0 else 0.0
        while self._run:
            now = time.time()
            try:
                dirty = self._dirty.is_set()
                due = (now - self._last_write) >= keep if keep else False
                if dirty or due:
                    with self._lock:
                        frame = self._frame
                    self._dirty.clear()
                    if self.dev:
                        self.dev.send_frame(frame)
                        self._last_write = time.time()
                        self.error = None
            except Exception as e:  # 设备短暂不可用时不影响用户操作
                self.error = str(e)
                self._dirty.set()
            time.sleep(period)

    def send_now(self, data):
        """立即发送（同步），用于需要即时反馈的场景。"""
        if self.dev:
            self.dev.send_frame(data)

    def clear(self):
        """停止刷新并同步写一帧全灭，关闭显示（下次 open 会重新点亮）。"""
        black = bytes(LED_COUNT)
        self.stop()
        self.set_frame(black)
        self.send_now(black)
        self.enable_display(False)
        self.display_on = True


# ================================================================ 渲染

_INDEX_CACHE = {}


# 真机可见坐标系 = 平面坐标（实测：平面横线与竖线在灯板上互相垂直）
PLANAR_MIN_X = 0
PLANAR_MAX_X = max(plx for _, plx, _ in LED_TABLE)      # 33
PLANAR_MIN_Y = 0
PLANAR_MAX_Y = max(ply for _, _, ply in LED_TABLE)      # 67
PLANAR_W = PLANAR_MAX_X - PLANAR_MIN_X + 1.0            # 34
PLANAR_H = PLANAR_MAX_Y - PLANAR_MIN_Y + 1.0            # 68


def _led_indices(w, h, u):
    """LED 在「平面坐标」画布上的像素下标（用于图片/GIF 渲染）。"""
    key = (w, h, round(u, 6))
    if key in _INDEX_CACHE:
        return _INDEX_CACHE[key]
    import numpy as np
    idx = []
    for lin, plx, ply in LED_TABLE:
        px = int(round((plx - PLANAR_MIN_X) * u))
        py = int(round((ply - PLANAR_MIN_Y) * u))
        px = max(0, min(w - 1, px))
        py = max(0, min(h - 1, py))
        idx.append(py * w + px)
    arr = np.array(idx, dtype=np.int64)
    _INDEX_CACHE[key] = arr
    return arr


def panel_canvas_size(px_per_unit=None):
    u = px_per_unit or PX_PER_UNIT
    return int(round(PLANAR_W * u)), int(round(PLANAR_H * u))


def compose_canvas(img, px_per_unit=None, offset=(0, 0), fit="contain"):
    """把 RGBA 图像合到面板画布（黑底），返回 (L 图像, px_per_unit)。

    fit: "contain"=整张塞进画布（可能留黑边）/ "cover"=填满画布（可能裁边）
         / False=按原始像素居中
    """
    from PIL import Image

    u = px_per_unit or PX_PER_UNIT
    w, h = panel_canvas_size(u)
    rgba = img.convert("RGBA")
    if fit == "stretch":
        rgba = rgba.resize((w, h), Image.LANCZOS)
    elif fit:
        sx, sy = w / rgba.width, h / rgba.height
        scale = min(sx, sy) if fit == "contain" else max(sx, sy)
        nw, nh = max(1, int(round(rgba.width * scale))), max(1, int(round(rgba.height * scale)))
        rgba = rgba.resize((nw, nh), Image.LANCZOS)
    base = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    ox = (w - rgba.width) // 2 + int(offset[0])
    oy = (h - rgba.height) // 2 + int(offset[1])
    sx0, sy0 = max(0, -ox), max(0, -oy)
    sx1, sy1 = min(rgba.width, w - ox), min(rgba.height, h - oy)
    if sx1 > sx0 and sy1 > sy0:
        base.alpha_composite(rgba.crop((sx0, sy0, sx1, sy1)),
                             (ox + sx0, oy + sy0))
    return base.convert("L"), u


def leds_from_canvas(canvas, px_per_unit=None, brightness=1.0):
    import numpy as np

    u = px_per_unit or PX_PER_UNIT
    w, h = canvas.size
    arr = np.asarray(canvas, dtype=np.float32).reshape(-1)
    vals = arr[_led_indices(w, h, u)] * brightness
    return bytes(np.clip(vals, 0, 255).astype(np.uint8).tobytes())


def image_to_leds(pil_image, brightness=1.0, px_per_unit=None,
                  offset=(0, 0), fit="contain", rotate_deg=0.0):
    """任意图像 -> 810 字节 LED 数据。"""
    img = pil_image.convert("RGBA")
    if rotate_deg:
        img = img.rotate(-rotate_deg, expand=True, resample=3, fillcolor=(0, 0, 0, 0))
    canvas, u = compose_canvas(img, px_per_unit, offset, fit)
    return leds_from_canvas(canvas, u, brightness)


# 奥创矩阵灯效 GIF 的坐标约定（已在本机用真机灯板验证）：
#   GIF 是 68x49，按「视觉(对角)坐标」绘制，1 像素 = 1 格，
#   内容贴着画布底边：visual u = gx - 9，visual v = gy - 9.5
MATRIX_GIF_W = 68
MATRIX_GIF_H = 49
MATRIX_GIF_OFF_U = 9.0
MATRIX_GIF_OFF_V = 9.5


def _bilinear_lum(px, w, h, x, y):
    """在 RGBA 像素序列上做双线性采样，返回亮度（0..255）。"""
    x0 = int(math.floor(x))
    y0 = int(math.floor(y))
    if 0 <= x0 < w - 1 and 0 <= y0 < h - 1:
        fx = x - x0
        fy = y - y0
        r0, g0, b0, a0 = px[x0, y0]
        r1, g1, b1, a1 = px[x0 + 1, y0]
        r2, g2, b2, a2 = px[x0, y0 + 1]
        r3, g3, b3, a3 = px[x0 + 1, y0 + 1]
        l0 = 0.299 * r0 + 0.587 * g0 + 0.114 * b0
        l1 = 0.299 * r1 + 0.587 * g1 + 0.114 * b1
        l2 = 0.299 * r2 + 0.587 * g2 + 0.114 * b2
        l3 = 0.299 * r3 + 0.587 * g3 + 0.114 * b3
        top = l0 * (1 - fx) + l1 * fx
        bot = l2 * (1 - fx) + l3 * fx
        return top * (1 - fy) + bot * fy
    xi = min(w - 1, max(0, int(round(x))))
    yi = min(h - 1, max(0, int(round(y))))
    r, g, b, _a = px[xi, yi]
    return 0.299 * r + 0.587 * g + 0.114 * b


def image_to_leds_matrix(pil_image, brightness=1.0, rot_deg=0.0,
                         mirror_x=False, mode="auto", ox=0.0, oy=0.0,
                         zoom=1.0):
    """奥创矩阵灯效（GIF）-> 810 字节帧。

    mode:
      "auto"  按图片尺寸判断：68x49 走 GIF 约定，否则按 A 面铺满
      "gif"   强制按 GIF 约定（1 像素 = 1 格视觉坐标，底边对齐）
      "lid"   按 A 面(盖板 355x245mm)铺满，适合任意画稿
    ox/oy/zoom 用于微调（单位：格 / 倍数）
    """
    from PIL import Image
    img = pil_image.convert("RGBA")
    if rot_deg:
        img = img.rotate(float(rot_deg), resample=Image.BICUBIC, expand=False,
                         fillcolor=(0, 0, 0, 0))
    if mirror_x:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)

    if mode == "auto":
        if img.size == (MATRIX_GIF_W, MATRIX_GIF_H):
            mode = "gif"
        elif img.width >= 40 and img.height >= 40 and abs(img.width - img.height) <= 8:
            # 接近正方形（如内置的 90x90 ECAnimations），按整块画布缩放
            mode = "scaled"
        elif img.size in ((69, 51), (70, 52)):
            # 内置 system 提示动画的固定画布
            mode = "scaled"
        else:
            mode = "lid"
    iw, ih = img.size
    px = img.load()
    out = bytearray(LED_COUNT)

    if mode == "scaled":
        # 奥创内置灯效：画布尺寸不固定（90x90 的 ECAnimations、69x51 的
        # system 提示动画），内容铺满整块画布、按画布比例排版。
        # 面板可见区只有 67x15 格的细长条，用双线性把整张画布拉伸铺满它。
        for lin, (u, v) in enumerate(LEDS):
            gx = (u - MIN_U) / (MAX_U - MIN_U) * (iw - 1)
            gy = (v - MIN_V) / (MAX_V - MIN_V) * (ih - 1)
            val = _bilinear_lum(px, iw, ih, gx, gy) * brightness
            if val >= 12:
                out[lin] = min(255, int(val))
        return bytes(out)

    if mode == "gif":
        off_u = MATRIX_GIF_OFF_U + float(ox)
        off_v = MATRIX_GIF_OFF_V + float(oy)
        z = float(zoom) or 1.0
        cu = (MIN_U + MAX_U) / 2.0
        cv = (MIN_V + MAX_V) / 2.0
        for lin, (u, v) in enumerate(LEDS):
            su = (u - cu) / z + cu + off_u
            sv = (v - cv) / z + cv + off_v
            # 双线性采样：LED 落点未必正好压在像素中心，最近邻会让笔画
            # 忽明忽暗、边缘锯齿明显，双线性过渡更顺滑（真机对比选定的方案）
            val = _bilinear_lum(px, iw, ih, su, sv)
            val *= brightness
            if val >= 12:
                out[lin] = min(255, int(val))
        return bytes(out)

    # mode == "lid"：GIF 当作整张盖板，按 LED 的毫米位置采样
    z = float(zoom) or 1.0
    for lin, plx, ply in LED_TABLE:
        x_mm, y_mm = _lid_xy(plx, ply)
        x_mm = (x_mm - 355.0 / 2) / z + 355.0 / 2 + float(ox) * 3.55
        y_mm = (y_mm - 245.0 / 2) / z + 245.0 / 2 + float(oy) * 2.45
        ix = int(x_mm / 355.0 * iw)
        iy = int(y_mm / 245.0 * ih)
        if not (0 <= ix < iw and 0 <= iy < ih):
            continue
        r, g, b, a = px[ix, iy]
        if a == 0:
            continue
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        val = min(255.0, lum * 1.15 * brightness)
        if val >= 12:
            out[lin] = int(val)
    return bytes(out)


def image_to_leds_lid(pil_image, brightness=1.0, rot_deg=0.0, mirror_x=False):
    """兼容旧接口：按 A 面(盖板整图)坐标映射，等价于 fit="lid"。"""
    return image_to_leds_matrix(pil_image, brightness=brightness,
                                rot_deg=rot_deg, mirror_x=mirror_x,
                                mode="lid")


def image_to_leds_stretch(pil_image, brightness=1.0, ox=0.0, oy=0.0, zoom=1.0,
                          rot_deg=0.0, mirror_x=False):
    """把画稿按 (u,v) 铺满灯板，可带偏移/缩放/旋转（用于灯效微调）。"""
    from PIL import Image
    img = pil_image.convert("RGBA")
    if rot_deg:
        img = img.rotate(float(rot_deg), resample=Image.BICUBIC, expand=False,
                         fillcolor=(0, 0, 0, 0))
    if mirror_x:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    iw, ih = img.size
    px = img.load()
    out = bytearray(LED_COUNT)
    su = max(1e-6, MAX_U - MIN_U)
    sv = max(1e-6, MAX_V - MIN_V)
    for lin, (u, v) in enumerate(LEDS):
        fx = (u - MIN_U) / su
        fy = (v - MIN_V) / sv
        fx = (fx - 0.5) / zoom + 0.5 + ox
        fy = (fy - 0.5) / zoom + 0.5 + oy
        if not (0.0 <= fx < 1.0 and 0.0 <= fy < 1.0):
            continue
        r, g, b, a = px[min(iw - 1, int(fx * iw)), min(ih - 1, int(fy * ih))]
        if not a:
            continue
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        val = min(255.0, lum * 1.15 * brightness)
        if val >= 12:
            out[lin] = int(val)
    return bytes(out)


def _find_cjk_font(bold=False):
    import os
    base = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    names = ("msyhbd.ttc", "msyh.ttc", "simhei.ttf", "simsun.ttc",
             "Deng.ttf", "arial.ttf") if bold else \
            ("msyh.ttc", "msyhbd.ttc", "simhei.ttf", "simsun.ttc",
             "Deng.ttf", "arial.ttf")
    for name in names:
        p = os.path.join(base, name)
        if os.path.exists(p):
            return p
    raise RuntimeError("未找到可用字体")


def text_image(text, font_size=110, font_path=None, padding=12,
               bold=True, stroke=0):
    """把一行文字渲染成 RGBA 图像（白字透明底）。

    LED 点阵分辨率很低（斜带每行 15 颗），默认使用粗体并加描边，
    否则细笔画会采样丢失。
    """
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(font_path or _find_cjk_font(bold), font_size)
    tmp = Image.new("RGBA", (8, 8))
    bbox = ImageDraw.Draw(tmp).textbbox((0, 0), text, font=font)
    w = max(1, bbox[2] - bbox[0] + 2 * padding)
    h = max(1, bbox[3] - bbox[1] + 2 * padding)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).text(
        (padding - bbox[0], padding - bbox[1]), text, font=font,
        fill=(255, 255, 255, 255), stroke_width=stroke,
        stroke_fill=(255, 255, 255, 255))
    return img


def render_strip_leds(strip, offset=(0, 0), fit=True, brightness=1.0, dilate=2):
    """把条状图像渲染成 LED 数据；dilate>0 时先膨胀笔画以适配低分辨率点阵。"""
    canvas, u = compose_canvas(strip, None, offset, fit)
    return _leds_from_canvas_dilated(canvas, u, brightness, dilate)


def canvas_with_images(items, px_per_unit=None):
    """把多张 (图像, (ox, oy)) 依次合成到面板画布，返回 (L 图像, px_per_unit)。"""
    from PIL import Image

    u = px_per_unit or PX_PER_UNIT
    w, h = panel_canvas_size(u)
    base = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    for img, (ox, oy) in items:
        rgba = img.convert("RGBA")
        sx0, sy0 = max(0, -ox), max(0, -oy)
        sx1, sy1 = min(rgba.width, w - ox), min(rgba.height, h - oy)
        if sx1 > sx0 and sy1 > sy0:
            base.alpha_composite(rgba.crop((sx0, sy0, sx1, sy1)),
                                 (ox + sx0, oy + sy0))
    return base.convert("L"), u


def _leds_from_canvas_dilated(canvas, px_per_unit, brightness, dilate):
    if dilate:
        from PIL import ImageFilter
        canvas = canvas.filter(ImageFilter.MaxFilter(2 * int(dilate) + 1))
    return leds_from_canvas(canvas, px_per_unit, brightness)


def text_to_leds(text, font_size=110, brightness=1.0, rotate_deg=None,
                 font_path=None, bold=True, stroke=0, dilate=2):
    """一行文字 -> LED 数据（默认沿斜带方向旋转）。"""
    if rotate_deg is None:
        rotate_deg = RIBBON_ANGLE_DEG
    img = text_image(text, font_size, font_path, bold=bold, stroke=stroke)
    if rotate_deg:
        img = img.rotate(-rotate_deg, expand=True, resample=3,
                         fillcolor=(0, 0, 0, 0))
    return render_strip_leds(img, brightness=brightness, dilate=dilate)


def load_gif_frames(path):
    """读取 GIF 全部分帧，返回 (frames[RGBA], durations_ms)。"""
    from PIL import Image, ImageSequence
    im = Image.open(path)
    frames, durations = [], []
    for fr in ImageSequence.Iterator(im):
        frames.append(fr.convert("RGBA"))
        durations.append(max(20, int(fr.info.get("duration", 100))))
    return frames, durations


# ================================================================ 预览图

def frame_to_png(frame, scale=8):
    """把 810 字节帧渲染成 LED 点阵预览 PNG（返回 bytes）。"""
    from PIL import Image, ImageDraw
    import io

    u = PX_PER_UNIT
    w = int(PLANAR_W * u)
    h = int(PLANAR_H * u)
    img = Image.new("RGB", (w, h), (10, 10, 14))
    d = ImageDraw.Draw(img)
    r = max(1, int(u * 0.42))
    for lin, plx, ply in LED_TABLE:
        v = frame[lin] if lin < len(frame) else 0
        cx = (plx - PLANAR_MIN_X) * u
        cy = (ply - PLANAR_MIN_Y) * u
        if v > 0:
            g = int(20 + v * 0.92)
            col = (g, g, int(g * 0.96))
        else:
            col = (28, 28, 34)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    # 预览装饰：右上角画 ROG 标识，方便对照真机 A 面的方向
    try:
        from PIL import ImageFont
        fpath = _official_matrix_font() or _find_cjk_font(True)
        fs = max(10, int(u * 2.2))
        font = ImageFont.truetype(fpath, fs)
        txt = "ROG"
        tb = d.textbbox((0, 0), txt, font=font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        pad = max(4, int(u * 0.8))
        d.text((w - tw - pad - tb[0], pad - tb[1]), txt, font=font,
               fill=(214, 52, 62))
    except Exception:
        pass
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _eye_outline(cx, cy, w, h, n=90, exp=0.55):
    """ROG 大眼睛的杏仁形轮廓点（左右尖角、上下弧线）。"""
    import math
    pts = []
    for i in range(n + 1):          # 上弧：左 → 右
        t = i / n
        pts.append((cx - w / 2 + w * t, cy - h * math.sin(math.pi * t) ** exp))
    for i in range(n + 1):          # 下弧：右 → 左
        t = i / n
        pts.append((cx + w / 2 - w * t, cy + h * math.sin(math.pi * t) ** exp))
    return pts


import os

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
# 想换成别的 logo：把图片（建议透明底 PNG）保存为这个路径即可，无需改代码
ROG_EYE_PATH = os.path.join(ROOT_DIR, "rog_eye.png")


def _paste_eye_image(img, cx_px, cy_px, width_px, color=None):
    """若存在 rog_eye.png 就按原图贴到指定位置；返回是否成功。

    不再改色，方便直接替换素材。
    """
    from PIL import Image
    if not os.path.exists(ROG_EYE_PATH):
        return False
    try:
        eye = Image.open(ROG_EYE_PATH).convert("RGBA")
        w = max(8, int(width_px))
        h = max(8, int(round(eye.height * w / eye.width)))
        eye = eye.resize((w, h), Image.LANCZOS)
        img.paste(eye, (int(cx_px - w / 2), int(cy_px - h / 2)), eye)
        return True
    except Exception:
        return False


def _draw_rog_eye(d, cx, cy, size, color=(98, 199, 227), bg=(35, 36, 40)):
    """画 ROG 大眼睛 logo：杏仁形镜框（外亮内挖空）+ 实心圆瞳。"""
    w = size
    h = size * 0.38
    d.polygon(_eye_outline(cx, cy, w, h), fill=color)            # 外轮廓
    d.polygon(_eye_outline(cx, cy, w * 0.70, h * 0.60), fill=bg)  # 挖空
    pr = h * 0.55
    d.ellipse([cx - pr, cy - pr, cx + pr, cy + pr], fill=color)   # 瞳孔


def lid_preview_png(frame, px_per_mm=3.6):
    """生成“A 面”示意图：深色面板 + 斜带点阵 + 右侧青色 ROG 眼。

    版面参照真机 A 面照片（h732.png）：
      * 圆角机身（不画外圈灯效）
      * 深灰面板占据机身大部分
      * 光显矩阵是面板左上到右下的一条斜带（平面坐标）
      * ROG 大眼睛在面板右侧偏上，冰蓝色
    """
    from PIL import Image, ImageDraw
    import io

    lid_w, lid_h = 355.0, 245.0            # 盖子尺寸（mm）
    S = px_per_mm
    W, H = int(lid_w * S), int(lid_h * S)
    img = Image.new("RGB", (W, H), (0, 0, 0))

    m = 5 * S                                # 机身外留白
    box = [m, m, lid_w * S - m, lid_h * S - m]
    rad = 16 * S

    d = ImageDraw.Draw(img)

    # ---- 机身底色 ----
    d.rounded_rectangle([box[0], box[1], box[2], box[3]],
                        radius=rad, fill=(23, 24, 28))

    # ---- 面板 ----
    px0, py0 = box[0] + 13 * S, box[1] + 13 * S
    px1, py1 = box[2] - 13 * S, box[3] - 13 * S
    d.rounded_rectangle([px0, py0, px1, py1], radius=6 * S, fill=(35, 36, 40))
    # 面板渐变高光（左上稍亮）
    for i in range(10):
        t = i / 10.0
        c = int(46 - t * 12)
        d.rounded_rectangle([px0 + i, py0 + i, px1 - i, py1 - i],
                            radius=6 * S - i, outline=(c, c, c + 2))

    # ---- 光显矩阵：按平面坐标铺开，比例对齐真机 A 面照片 ----
    # 真机照片里 LED 区占面板宽 66%、高 72%，左起 6%、上起 8%；
    # 列距与行距之比约 2.5:1（这是 45° 斜格在平面坐标上的投影比例）。
    led_w = (px1 - px0) / S * 0.66
    led_h = (py1 - py0) / S * 0.72
    ox = (px0 / S) + (px1 - px0) / S * 0.06
    oy = (py0 / S) + (py1 - py0) / S * 0.08
    unit_x = led_w / PLANAR_W
    unit_y = led_h / PLANAR_H
    # 间距≈2.5px、灯珠直径≈3px：半径取间距的 ~0.34，既密又能看出单独的点
    r = max(0.6, unit_x * S * 0.34)
    for lin, plx, ply in LED_TABLE:
        vv = frame[lin] if lin < len(frame) else 0
        cx = (ox + plx * unit_x) * S
        cy = (oy + ply * unit_y) * S
        if vv > 0:
            # 点亮：偏暖的白（参考图里灯珠是暖白色）
            gv = int(30 + vv * 0.88)
            col = (min(255, int(gv * 1.02)), gv, min(255, int(gv * 0.86)))
        else:
            col = (58, 60, 68)          # 未点亮：暗灰点，仍能看出矩阵形状
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)

    # ---- ROG 之眼：面板右侧偏上，冰蓝色 ----
    eye_cx = (px1 + px0) / 2 + (px1 - px0) * 0.28
    eye_cy = py0 + (py1 - py0) * 0.26
    if not _paste_eye_image(img, eye_cx, eye_cy, (px1 - px0) * 0.30):
        _draw_rog_eye(ImageDraw.Draw(img), eye_cx, eye_cy, (px1 - px0) * 0.28)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _lid_xy(plx, ply, lid_w=355.0, lid_h=245.0):
    """LED 平面坐标 → A 面上的 mm 坐标。

    比例对齐真机 A 面照片：LED 区占面板宽 66%、高 72%，左起 6%、上起 8%。
    （面板 = 机身内缩 13mm）
    """
    px0, py0 = 13.0, 13.0
    pw, ph = lid_w - 26.0, lid_h - 26.0
    led_w = pw * 0.66
    led_h = ph * 0.72
    ox = px0 + pw * 0.06
    oy = py0 + ph * 0.08
    return ox + plx * (led_w / PLANAR_W), oy + ply * (led_h / PLANAR_H)


def _hull_2d(points):
    """Andrew monotone chain：返回点集凸包顶点（逆时针）。"""
    pts = sorted(set(points))
    if len(pts) <= 1:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def lid_geometry():
    """返回 A 面预览所需的几何数据（单位 mm），供前端 Canvas 直接绘制。

    灯带的每一行沿斜带方向（左上 -> 右下）排列：把视觉(对角)坐标整体
    旋转 35°，再把外接矩形对齐真机照片里的灯带位置，这样灯珠是斜行，
    而不是竖列，位置也和 A 面照片一致。
    """
    lid_w, lid_h = 355.0, 245.0
    theta = math.radians(35.0)
    cs, sn = math.cos(theta), math.sin(theta)
    u_mid = (MIN_U + MAX_U) / 2.0
    v_mid = (MIN_V + MAX_V) / 2.0

    raw = []
    for lin, plx, ply in LED_TABLE:
        u = ply / 2.0 + plx - TEXT_DELTA_X
        v = ply / 2.0 - plx + TEXT_DELTA_Y
        du = u - u_mid
        dv = v - v_mid
        raw.append([du * cs - dv * sn, du * sn + dv * cs, lin])

    xs = [p[0] for p in raw]
    ys = [p[1] for p in raw]
    # 真机 A 面照片（h732.png）里灯带外接矩形的比例位置：
    # 盖子约 75..654 x 145..585，灯带约 93..584 x 186..531
    x0, x1 = 11.0, 312.0
    y0, y1 = 23.0, 215.0
    sx = (x1 - x0) / (max(xs) - min(xs))
    sy = (y1 - y0) / (max(ys) - min(ys))
    mapped = [(x0 + (x - min(xs)) * sx,
               y0 + (y - min(ys)) * sy, lin)
              for x, y, lin in raw]

    # 整体顺时针微调 11°：屏幕坐标 y 向下，正角度即顺时针
    tilt = math.radians(11.0)
    ct, st = math.cos(tilt), math.sin(tilt)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    rotated = []
    for x, y, lin in mapped:
        dx, dy = x - cx, y - cy
        rotated.append([cx + dx * ct - dy * st,
                        cy + dx * st + dy * ct, lin])

    # 旋转会让外接矩形偏移，重新居中，避免整体跑偏
    xs2 = [p[0] for p in rotated]
    ys2 = [p[1] for p in rotated]
    bx = (min(xs2) + max(xs2)) / 2.0
    by = (min(ys2) + max(ys2)) / 2.0
    leds = [[round(x - bx + cx, 2), round(y - by + cy, 2), lin]
            for x, y, lin in rotated]

    # 垂直居中：让灯带上方和下方的留白一样
    ys3 = [p[1] for p in leds]
    dy = lid_h / 2.0 - (min(ys3) + max(ys3)) / 2.0
    leds = [[x, round(y + dy, 2), lin] for x, y, lin in leds]

    # 用灯珠凸包做裁剪边界，把边缘的楼梯状锯齿切成直线
    hull = _hull_2d([(x, y) for x, y, lin in leds])
    clip = [[round(x, 2), round(y, 2)] for x, y in hull]

    # 灯珠网格的两个基矢（mm/格），前端用它把每颗灯珠再细分，画得更密
    by_lin = {lin: (plx, ply) for lin, plx, ply in LED_TABLE}
    pos = {(by_lin[lin][0], by_lin[lin][1]): (x, y) for x, y, lin in leds}
    p00, p02, p12 = pos[(0, 0)], pos[(0, 2)], pos[(1, 2)]
    row_v = (p12[0] - p02[0], p12[1] - p02[1])
    col_v = ((p02[0] - p00[0]) / 2.0, (p02[1] - p00[1]) / 2.0)
    return {
        "lid_w": lid_w, "lid_h": lid_h,
        # 眼睛在面板右侧偏上（参照真机 A 面照片）
        "eye": {"cx": 297.5, "cy": 56.0, "size": 49.0, "color": "#62c7e3"},
        "basis": [[round(row_v[0], 4), round(row_v[1], 4)],
                  [round(col_v[0], 4), round(col_v[1], 4)]],
        "clip": clip,
        "leds": leds,
    }


ROG_MATRIX_FONTS = [
    r"C:\Windows\Fonts\ROG FONTS STRIX SCAR REGULAR.ttf",
    r"C:\Windows\Fonts\ROGFonts-Regular.otf",
]


def _official_matrix_font():
    import os
    for p in ROG_MATRIX_FONTS:
        if os.path.exists(p):
            return p
    return None


def _strip_official(text, size=18, height=15):
    """用华硕官方点阵字体渲染，1 像素 = 1 颗 LED（不重采样，保持锐利）。"""
    from PIL import Image, ImageDraw, ImageFont

    path = _official_matrix_font()
    font = ImageFont.truetype(path, int(size))
    tmp = Image.new("L", (8, 8))
    bbox = ImageDraw.Draw(tmp).textbbox((0, 0), text, font=font)
    tw, th = max(1, bbox[2] - bbox[0]), max(1, bbox[3] - bbox[1])
    img = Image.new("L", (tw, th), 0)
    ImageDraw.Draw(img).text((-bbox[0], -bbox[1]), text, font=font, fill=255)
    strip = Image.new("L", (img.width, height), 0)
    strip.paste(img, (0, max(0, (height - img.height) // 2)))
    return strip


def _planar_xy(x, y, dX=TEXT_DELTA_X, dY=TEXT_DELTA_Y):
    """g-helper 的 Planar()：对角(视觉)坐标 → 平面坐标（C# 整数除法语义）。"""
    dx = x + dX
    dy = y - dY
    num = dx - dy
    plx = int(num / 2)          # 截断（向零取整），与 C# 一致
    ply = dx + dy
    if num == -1:
        plx = -1
    return plx, ply


def _set_planar(frame, plx, ply, value):
    """平面坐标 → 线性地址（越界忽略）。"""
    if 0 <= ply < PLANAR_ROWS:
        fx = planar_first_x(ply)
        if fx <= plx < planar_width(ply):
            lin = _ROW_START[ply] - fx + plx
            if 0 <= lin < LED_COUNT and value > frame[lin]:
                frame[lin] = value


def render_text_visual(text, font_units=16, u_pos=None, v_offset=0.0,
                       brightness=1.0, font_path=None, bold=True,
                       bitmap_height=None, v_center=None):
    """完全按 g-helper 的做法渲染文字，返回 810 字节帧。

    g-helper 的流程：
      1. 画一张高 (MaxRows-FullRows)=39 像素的文字位图，文字底部对齐
      2. 逐像素 (x,y) 调用 Planar(x, y, 9, 24) 旋转成平面坐标
      3. SetLedPlanar 写入对应 LED
    位图 x 坐标即视觉 u（水平），y 坐标即视觉 v（垂直），因此：
      u_pos   控制文字左边缘水平位置（滚动用）
      v_offset 控制上下位置（正数向下）
    字体：纯 ASCII 用华硕官方点阵字体（锐利）；含中文回退微软雅黑粗体。
    """
    from PIL import Image, ImageDraw, ImageFont

    if font_path:
        path = font_path
    elif text.isascii() and _official_matrix_font():
        path = _official_matrix_font()
    else:
        path = _find_cjk_font(False)      # 中文用常规体（粗体会显得糊）
    size = max(4, int(round(float(font_units))))
    font = ImageFont.truetype(path, size)
    # 中文抗锯齿灰边会让笔画显粗，用更高阈值只保留实心部分
    level = 20 if text.isascii() else 110

    bmp_h = int(bitmap_height or TEXT_BITMAP_HEIGHT)     # 39
    tmp = Image.new("L", (8, 8))
    bbox = ImageDraw.Draw(tmp).textbbox((0, 0), text, font=font)
    tw = max(1, bbox[2] - bbox[0])
    th = max(1, bbox[3] - bbox[1])

    if u_pos is None:
        u_pos = (MIN_U + MAX_U) / 2.0 - tw / 2.0

    bmp_w = int(MAX_U) + tw + 24
    bmp = Image.new("L", (max(8, bmp_w), bmp_h), 0)
    d = ImageDraw.Draw(bmp)
    x0 = int(round(u_pos)) - bbox[0]
    # 垂直：默认在可见灯带内居中，v_offset 微调（正=向下）
    if v_center is None:
        v_center = (MIN_V + MAX_V) / 2.0
    v_top = float(v_center) - th / 2.0 + float(v_offset)
    ty = int(round(v_top - bbox[1]))
    d.text((x0, ty), text, font=font, fill=255)

    frame = bytearray(LED_COUNT)
    px = bmp.load()
    bw = bmp.width
    for y in range(bmp_h):
        for x in range(bw):
            v = px[x, y]
            if v < level:
                continue
            plx, ply = _planar_xy(x, y)
            _set_planar(frame, plx, ply, min(255, int(v * brightness)))
    return bytes(frame)


def render_bars(levels, peaks=None, brightness=1.0, gap=0.28,
                bars=13, mirror=False, segmented=True):
    """把频段电平渲染成柱状频谱（视觉坐标），返回 810 字节帧。

    levels/peaks: 0..1 频段电平；bars: 柱数（对输入做线性插值重采样）；
    mirror: True 左右对称；False 从左到右（低频→高频），与奥创的音频柱一致；
    segmented: 每格之间留一点暗缝，看起来像点阵柱。
    """
    import numpy as np

    lv = np.asarray(levels, dtype=np.float32).ravel()
    n = int(lv.size)
    if n == 0 or bars <= 0:
        return bytes(LED_COUNT)
    src = np.linspace(0.0, 1.0, n)
    dst = np.linspace(0.0, 1.0, bars)
    lvv = np.interp(dst, src, lv).astype(np.float32)
    pkk = lvv if peaks is None else np.interp(
        dst, src, np.asarray(peaks, dtype=np.float32).ravel()).astype(np.float32)

    W = MAX_U - MIN_U
    H = MAX_V - MIN_V
    frame = bytearray(LED_COUNT)
    for i, (u, v) in enumerate(LEDS):
        t = (u - MIN_U) / W                      # 0..1
        if mirror:
            t = abs(t - 0.5) * 2.0
        slot = t * bars
        b = min(bars - 1, max(0, int(slot)))
        if (slot % 1.0) > (1.0 - gap):           # 柱间空隙
            continue
        rel = MAX_V - v                          # 距底部高度（格）
        h = float(lvv[b]) * H
        if rel <= h:
            if segmented and (rel % 1.0) > 0.82:  # 点阵柱的横向暗缝
                continue
            frac = min(1.0, rel / max(h, 1e-6))
            val = 110 + 145 * (0.35 + 0.65 * frac)
            frame[i] = min(255, int(val * brightness))
        elif rel <= float(pkk[b]) * H:           # 峰值帽
            frame[i] = min(255, int(225 * brightness))
    return bytes(frame)


_COL_V_RANGE = {}


def _col_v_range(plx, cache=_COL_V_RANGE):
    """某平面列实际可用的视觉 v 范围（面板是斜三角形，各列不同）。"""
    if plx in cache:
        return cache[plx]
    vs = []
    for lin, x, _y in LED_TABLE:
        if x == plx:
            vs.append(LEDS[lin][1])
    if vs:
        r = (min(vs), max(vs))
    else:
        r = (MIN_V, MAX_V)
    cache[plx] = r
    return r


def render_bars_planar(levels, peaks=None, bars=12, brightness=1.0,
                       gap=0.22, floor=0.04, antialias=True,
                       col_width=None, col_gap=None, distribute=False,
                       gap_level=0.0, edge_level=0.0, max_height=1.0,
                       top_tol=1.0, gradient=True):
    """在平面(寻址)坐标里画柱状频谱 —— 柱沿点阵对角线排列，是**实心**的。

    distribute=True 时把 34 列按「柱 + col_gap 列缝隙」均匀分配，不会并条；
    gap_level>0 时缝隙列给一定亮度（看起来缝更细、柱更粗）；
    edge_level>0 时每根柱右侧再补一列半亮边，视觉上加粗柱身。
    """
    import numpy as np

    lv = np.asarray(levels, dtype=np.float32).ravel()
    n = int(lv.size)
    if n == 0 or bars <= 0:
        return bytes(LED_COUNT)
    src = np.linspace(0.0, 1.0, n)
    dst = np.linspace(0.0, 1.0, bars)
    lvv = np.interp(dst, src, lv).astype(np.float32)
    pkk = lvv if peaks is None else np.interp(
        dst, src, np.asarray(peaks, dtype=np.float32).ravel()).astype(np.float32)

    max_x = max(plx for _, plx, _ in LED_TABLE)
    min_x = min(plx for _, plx, _ in LED_TABLE)
    top_y = min(ply for _, _, ply in LED_TABLE)
    bot_y = max(ply for _, _, ply in LED_TABLE)
    span_y = float(bot_y - top_y) or 1.0
    cols = int(max_x - min_x + 1)                     # 34

    starts, widths = [], []
    if distribute:
        g = max(0, int(col_gap if col_gap is not None else 1))
        gaps_total = (bars - 1) * g
        free = cols - gaps_total
        if free < bars:
            g, gaps_total = 0, 0
            free = cols
        base = max(1, free // bars)
        extra = max(0, free - base * bars)
        total = g * (bars - 1) + base * bars + extra
        pos = max(0, (cols - total) // 2)
        acc = 0
        for i in range(bars):
            w = base
            acc += extra
            if acc >= bars:
                w += 1
                acc -= bars
            starts.append(pos)
            widths.append(w)
            pos += w + g
    elif col_width is not None and col_gap is not None:
        cw, cg = int(col_width), int(col_gap)
        total = (cw + cg) * bars - cg
        pos = max(0, (cols - total) // 2)
        for i in range(bars):
            starts.append(pos)
            widths.append(cw)
            pos += cw + cg
    else:
        slot_w = cols / float(bars)
        for i in range(bars):
            starts.append(i * slot_w)
            widths.append(slot_w * (1.0 - gap))

    def locate(rel_x):
        for i in range(bars):
            s, w = starts[i], widths[i]
            if s <= rel_x < s + w:
                return i, False, 1.0
            nxt = starts[i + 1] if i + 1 < bars else cols
            if s + w <= rel_x < nxt:                  # 落在缝隙里
                if edge_level > 0.02 and rel_x < s + w + 1:
                    return i, True, edge_level
                if gap_level > 0.02:
                    # 缝隙亮度按「靠近哪边」线性过渡，看起来更自然
                    span = max(1e-6, nxt - (s + w))
                    t = (rel_x - (s + w)) / span
                    return i, True, gap_level * (1.0 - 0.35 * t)
                return None, True, 0.0
        return None, False, 0.0

    frame = bytearray(LED_COUNT)
    for lin, plx, ply in LED_TABLE:
        rel_x = float(plx - min_x)
        b, in_gap, cover = locate(rel_x)
        if b is None or cover <= 0.02:
            continue
        if (not distribute) and col_width is None and antialias and not in_gap:
            slot_w = cols / float(bars)
            pos_in_slot = rel_x - (b * slot_w)
            cover = min(1.0, max(0.0, slot_w * (1.0 - gap) - pos_in_slot))
            if cover <= 0.05:
                continue

        # 高度按「视觉垂直坐标」计算，柱顶在面板上才是平齐的
        # （若按平面行号算，可见区域是斜带，等高柱顶会依次错开形成锯齿）
        vis_v = LEDS[lin][1]
        # 每列的可用高度不同：面板是斜三角形，列 0 能到 v=38.5，
        # 列 33 只能到 v=24.5。按该列自己的 v 范围归一化，
        # 这样等高输入时每根柱都能填满它所在列的可用空间。
        v_lo, v_hi = _col_v_range(plx)
        span_v = (v_hi - v_lo) or 1.0
        rel = (v_hi - vis_v) / span_v                # 0=该列底 1=该列顶
        if rel > float(max_height):
            continue
        # 柱高按"半格"量化后统一截止：视觉 v 在相邻 LED 间步进 0.5，
        # 柱高若是连续值，柱顶那几颗灯会在亮/灭之间反复跳，顶边就呈锯齿。
        # 量化到半格后，同一柱顶上的灯要么全亮、要么全灭，顶边是一条直线。
        step = 0.5 / span_v
        h = round(min(float(lvv[b]), float(max_height)) / step) * step
        h = min(h, float(max_height))
        if h <= floor:
            continue
        # 顶边补偿：量化后柱顶可能比原高度低半格，把那一格补回来，
        # 避免整条柱在视觉上"矮一截"
        if rel <= h + step * 0.5:
            if gradient:
                v = 115 + 140 * (0.35 + 0.65 * min(1.0, rel / max(h, 1e-6)))
            else:
                v = 190                      # 平面亮度：顶边不再有亮线，看起来更平
            frame[lin] = min(255, int(v * cover * brightness))
        elif (not in_gap) and rel <= float(pkk[b]):  # 峰值帽（不画在缝隙里）
            frame[lin] = min(255, int(225 * cover * brightness))
    return bytes(frame)


def render_spectrum1(levels, peaks=None, brightness=1.0, bars=17,
                     seg_gap=0.22, max_height=1.0, top_boost=1.0,
                     bar_gap=1):
    """奥创「频谱 1」（AniMe Vision · 音乐模式 · 显示模式）。

    按奥创界面/真机效果实现：
      * 沿灯带宽度排 **12 条柱**（每条 2 格厚、间隔 1 格）
      * 柱沿灯带长度方向生长，长度 = 频段能量
      * 柱身连续，不分段、没有单独的峰值点
      * 越靠末端越亮；整块画布 68x34，按三角 mask 裁切

    矩阵坐标和 LED 平面的对应关系（已用 mask.csv 校验）：
      x = 67 - ply, y = 33 - plx
    """
    import numpy as np

    lv = np.asarray(levels, dtype=np.float32).ravel()
    out = bytearray(LED_COUNT)
    if lv.size == 0:
        return bytes(out)

    bands = 12
    if lv.size != bands:
        src = np.linspace(0.0, 1.0, lv.size)
        dst = np.linspace(0.0, 1.0, bands)
        lv = np.interp(dst, src, lv).astype(np.float32)
    vals = np.clip(lv, 0.0, 1.0)[::-1]   # 奥创频谱 1：高频在左、低频在右

    # 每一条横向画布行的可见 x 范围（mask 是斜的，基线跟着斜边走）
    row_x = {}
    for _, plx, ply in LED_TABLE:
        x = 67 - ply
        y = 33 - plx
        lo, hi = row_x.get(y, (x, x))
        row_x[y] = (min(lo, x), max(hi, x))

    # 12 条柱、每柱 2 格厚、1 格间隙；34 行不够 12*3-1=35，按比例压缩
    total = bands * 3 - 1
    bar_rows = [[] for _ in range(bands)]
    bar_of_y = {}
    for y in range(34):
        v = (y * total) // 34
        b, pos = v // 3, v % 3
        if b < bands and pos < 2:
            bar_rows[b].append(y)
            bar_of_y[y] = b
    bar_x = []
    for rows in bar_rows:
        if not rows:
            bar_x.append((0, 0))
            continue
        lo = min(row_x[y][0] for y in rows)
        hi = max(row_x[y][1] for y in rows)
        bar_x.append((lo, hi))

    bscale = float(brightness)
    for lin, plx, ply in LED_TABLE:
        x = 67 - ply
        y = 33 - plx
        b = bar_of_y.get(y)
        if b is None:
            continue
        lo, hi = bar_x[b]
        span = hi - lo + 1
        h = int(round(float(vals[b]) * span))
        if h <= 0 or x < lo or x >= lo + h:
            continue
        k = 1.0 if h <= 1 else (x - lo) / float(h - 1)
        val = 95.0 + 160.0 * k
        out[lin] = max(0, min(255, int(val * bscale)))
    return bytes(out)


def render_beat_flash(levels, beat, brightness=1.0, level=1.0):
    """节拍频闪（对应奥创的 Music_Effect_Strobing）。

    整块灯板随节拍整体点亮：beat 为 0..1 的瞬时强度，
    底噪也保留一点亮度，避免静音时全黑。level 取低频段能量做底光。
    """
    import numpy as np
    b = max(0.0, min(1.0, float(beat)))
    base = 0.12 + 0.88 * b
    # 低频段（前 1/4）稍亮，让低频重的曲子更有冲击感
    lv = np.asarray(levels, dtype=np.float32).ravel()
    low = float(lv[:max(1, len(lv) // 4)].mean()) if len(lv) else 0.0
    v = min(255.0, (base * 0.72 + low * 0.5) * 255.0 * brightness)
    return bytes([int(v)] * LED_COUNT)


def render_raindrop(levels, peaks=None, drops=None, brightness=1.0, dt=0.0):
    """雨滴（对应奥创的 Music_Effect_Raindrop）。

    每个频段的能量决定一颗"雨滴"从灯带顶部滴落到其高度位置。
    drops 是共享状态：{频段下标: 当前下落位置 0..1}。
    """
    import numpy as np
    lv = np.asarray(levels, dtype=np.float32).ravel()
    if drops is None:
        drops = {}
    frame = bytearray(LED_COUNT)
    nb = max(1, len(lv))
    W = MAX_U - MIN_U
    H = MAX_V - MIN_V
    for i, (u, v) in enumerate(LEDS):
        t = (u - MIN_U) / W                       # 0..1 横向位置
        b = min(nb - 1, max(0, int(t * nb)))
        target = float(lv[b])                     # 该频段应到达的高度（0=底）
        cur = drops.get(b)
        if cur is None:
            cur = 1.0
        # 下落：从顶部(1.0)朝目标高度掉，速度可调
        if cur > target:
            cur = max(target, cur - max(0.6, 3.0) * max(dt, 1 / 60.0))
            drops[b] = cur
        rel = (MAX_V - v) / H                     # 0=底 1=顶
        # 雨滴头部：一个窄亮带；底下留一条淡淡的水痕
        if abs(rel - cur) < 0.10:
            frame[i] = min(255, int(245 * brightness))
        elif cur < rel < target + 0.02:
            frame[i] = min(255, int(90 * brightness))
    return bytes(frame)


def render_wave(levels, brightness=1.0, phase=0.0, mirror=False):
    """波形（对应奥创的 Music_Effect_Wave）。

    把各频段电平当作波形高度，沿灯带横向画出连续曲线。
    """
    import numpy as np
    lv = np.asarray(levels, dtype=np.float32).ravel()
    if len(lv) == 0:
        return bytes(LED_COUNT)
    nb = len(lv)
    W = MAX_U - MIN_U
    H = MAX_V - MIN_V
    frame = bytearray(LED_COUNT)
    for i, (u, v) in enumerate(LEDS):
        t = (u - MIN_U) / W
        if mirror:
            t = abs(t - 0.5) * 2.0
        # 用平滑插值取该位置的波形高度
        pos = t * (nb - 1)
        i0 = int(pos)
        i1 = min(nb - 1, i0 + 1)
        frac = pos - i0
        h = float(lv[i0]) * (1 - frac) + float(lv[i1]) * frac
        h = h * 0.5 + 0.5 * h * (0.5 + 0.5 * np.sin(phase + t * 6.283))  # 轻微起伏
        rel = (MAX_V - v) / H
        if abs(rel - h) < 0.14:
            frame[i] = min(255, int(250 * brightness))
        elif rel < h:
            frame[i] = min(255, int(70 * brightness))
    return bytes(frame)


def render_bars_gh(levels, brightness=1.0, bars=20, delta_x=13, delta_y=-13,
                   height_norm=20.0):
    """精确移植 g-helper 的音频柱 (DrawBarDiagonal)。

    g-helper 的做法（STRIX）：
        pos = 20 - i                       # 柱位置（索引反序）
        dx = pos * 2                       # 每条柱占 2 个对角列
        for y in 0..h/2: for x in 0..1: SetLedDiagonal(x+dx, -y, h*255/30, 13, -13)

    特点：每条柱 2 个对角列宽、随高度倾斜、亮度随柱高变化（越高越亮），
    20 个频段，每条柱的高度 h = level*20（偶数步进）。
    """
    import numpy as np

    lv = np.asarray(levels, dtype=np.float32).ravel()
    n = int(lv.size)
    if n == 0:
        return bytes(LED_COUNT)
    if n != bars:
        src = np.linspace(0.0, 1.0, n)
        dst = np.linspace(0.0, 1.0, bars)
        lv = np.interp(dst, src, lv).astype(np.float32)

    frame = bytearray(LED_COUNT)
    for idx in range(bars):
        pos = bars - idx                       # 与 g-helper 的 20 - i 一致
        h = float(lv[idx]) * height_norm
        if h < 2:
            continue
        col = int(min(255.0, h * 255.0 / 30.0) * brightness)
        if col <= 4:
            continue
        steps = int(h // 2)
        for yy in range(steps):
            for xx in range(2):
                x = pos * 2 + xx
                y = -yy
                plx, ply = _planar_xy(x, y, delta_x, delta_y)
                _set_planar(frame, plx, ply, col)
    return bytes(frame)


def render_spectrogram(history, brightness=1.0, floor=0.03):
    """滚动瀑布频谱：横轴=时间（右侧最新），纵轴=频率（底部最低），返回 810 字节帧。

    history: 按时间顺序排列的 [(bands,) 数组]，最后一个为最新。
    """
    import numpy as np

    if not history:
        return bytes(LED_COUNT)
    hist = [np.asarray(h, dtype=np.float32).ravel() for h in history]
    n = len(hist)
    bands = int(hist[0].size)
    if bands == 0:
        return bytes(LED_COUNT)

    W = MAX_U - MIN_U
    H = MAX_V - MIN_V
    frame = bytearray(LED_COUNT)
    for i, (u, v) in enumerate(LEDS):
        t = (u - MIN_U) / W                     # 0(左,最旧) .. 1(右,最新)
        col = min(n - 1, max(0, int(t * n)))
        rel = (MAX_V - v) / H                   # 0(底) .. 1(顶)
        b = min(bands - 1, max(0, int(rel * bands)))
        val = float(hist[col][b])
        if val > floor:
            g = 70 + 185 * min(1.0, val * 1.5)
            frame[i] = min(255, int(g * brightness))
    return bytes(frame)


# 兼容旧调用名
def render_text_band(text, font_cells=16, gap_cells=6, offset_cells=0,
                     brightness=1.0, **kw):
    return render_text_visual(text, font_units=font_cells, u_pos=offset_cells,
                              brightness=brightness)


if __name__ == "__main__":
    print(f"面板视觉尺寸 {PANEL_UNITS_W:.1f} x {PANEL_UNITS_H:.1f} 格，{LED_COUNT} 颗 LED")
    print(f"平面行数 {PLANAR_ROWS}，行宽由 1 递增至 {planar_width(PLANAR_ROWS - 1)}")
    for p, ok in enumerate_hid_paths():
        print(("  [灯板] " if ok else "  [其他] ") + p)

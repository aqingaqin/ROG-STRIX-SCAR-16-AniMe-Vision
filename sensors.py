# -*- coding: utf-8 -*-
"""Windows 传感器：CPU/GPU 名称、占用、温度、功率，内存/显存。"""
import ctypes
import os
import struct
import subprocess
import threading
import time
from ctypes import wintypes

_CREATE_NO_WINDOW = 0x08000000
_lock = threading.Lock()
_started = False
_run = False
_gen = 0
_cache = {
    "cpu_name": "", "gpu_name": "",
    "cpu_usage": None, "cpu_temp": None, "cpu_power": None,
    "gpu_usage": None, "gpu_temp": None, "gpu_power": None,
    "gpu_mem_used": None, "gpu_mem_total": None,
    "ram_percent": None, "ram_used": None, "ram_total": None,
}

# ---------------------------------------------------------------- CPU 名称
_cpu_name = ""


def _clean_cpu_name(name):
    for s in ("(R)", "(TM)", "CPU", "Processor"):
        name = name.replace(s, "")
    return " ".join(name.split())


def _read_cpu_name():
    global _cpu_name
    if _cpu_name:
        return _cpu_name
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
        raw = winreg.QueryValueEx(key, "ProcessorNameString")[0]
        _cpu_name = _clean_cpu_name(raw)
    except Exception:
        _cpu_name = "CPU"
    return _cpu_name


def cpu_short_name():
    name = _read_cpu_name()
    for s in ("Intel ", "Core "):
        name = name.replace(s, "")
    return name.strip() or "CPU"


# ---------------------------------------------------------------- CPU 占用
class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD),
                ("dwHighDateTime", wintypes.DWORD)]


_cpu_prev = None


def _ft_value(ft):
    return (ft.dwHighDateTime << 32) | ft.dwLowDateTime


def _cpu_usage():
    global _cpu_prev
    idle, kern, user = _FILETIME(), _FILETIME(), _FILETIME()
    if not ctypes.windll.kernel32.GetSystemTimes(
            ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user)):
        return None
    cur = (_ft_value(idle), _ft_value(kern) + _ft_value(user))
    if _cpu_prev is None:
        _cpu_prev = cur
        return None
    di = cur[0] - _cpu_prev[0]
    dt = cur[1] - _cpu_prev[1]
    _cpu_prev = cur
    if dt <= 0:
        return None
    return max(0.0, min(100.0, (1.0 - di / float(dt)) * 100.0))


# ---------------------------------------------------------------- 内存
class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _ram():
    m = _MEMORYSTATUSEX()
    m.dwLength = ctypes.sizeof(m)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
        return None, None, None
    total = int(m.ullTotalPhys)
    used = total - int(m.ullAvailPhys)
    return int(m.dwMemoryLoad), used, total


# ---------------------------------------------------------------- CPU 功率
class _PDH_U(ctypes.Union):
    _fields_ = [("longValue", wintypes.LONG),
                ("doubleValue", ctypes.c_double),
                ("largeValue", ctypes.c_longlong),
                ("AnsiStringValue", ctypes.c_char_p),
                ("WideStringValue", ctypes.c_wchar_p)]


class _PDH_V(ctypes.Structure):
    _fields_ = [("CStatus", wintypes.DWORD), ("u", _PDH_U)]


_pdh = None
_pdh_query = None
_pdh_pkg = None
_pdh_tried = False


def _pdh_init():
    global _pdh, _pdh_query, _pdh_pkg, _pdh_tried
    if _pdh_tried:
        return
    _pdh_tried = True
    try:
        lib = ctypes.WinDLL("pdh.dll")
        query = ctypes.c_void_p()
        if lib.PdhOpenQueryW(None, 0, ctypes.byref(query)) != 0:
            return
        counter = ctypes.c_void_p()
        path = r"\Energy Meter(rapl_package0_pkg)\Power"
        if lib.PdhAddEnglishCounterW(query, path, 0,
                                     ctypes.byref(counter)) != 0:
            lib.PdhCloseQuery(query)
            return
        lib.PdhCollectQueryData(query)
        time.sleep(0.2)
        lib.PdhCollectQueryData(query)
        _pdh, _pdh_query, _pdh_pkg = lib, query, counter
    except Exception:
        _pdh = None


def _cpu_power():
    _pdh_init()
    if not _pdh:
        return None
    try:
        _pdh.PdhCollectQueryData(_pdh_query)
        val = _PDH_V()
        r = _pdh.PdhGetFormattedCounterValue(
            _pdh_pkg, 0x00000200, None, ctypes.byref(val))
        if r != 0 or val.CStatus not in (0, 1):
            return None
        mw = float(val.u.doubleValue)
        w = mw / 1000.0
        if 0.5 <= w <= 500.0:
            return round(w, 1)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------- CPU 温度
_cpu_temp_val = None
_cpu_temp_ts = 0.0
_cpu_temp_busy = False

# ASUS ATKACPI（GHelper 同款，普通权限即可读）
_ATK_CONTROL = 0x0022240C
_ATK_DSTS = 0x53545344
_ATK_CPU_TEMP = 0x00120094
_atk_handle = None
_atk_tried = False


def _atk_open():
    global _atk_handle, _atk_tried
    if _atk_tried:
        return _atk_handle
    _atk_tried = True
    try:
        k = ctypes.windll.kernel32
        k.CreateFileW.restype = wintypes.HANDLE
        k.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
        k.DeviceIoControl.restype = wintypes.BOOL
        k.DeviceIoControl.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
            ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        h = k.CreateFileW(r"\\.\ATKACPI", 0xC0000000, 3, None, 3, 0x80, None)
        if h in (None, ctypes.c_void_p(-1).value):
            _atk_handle = None
        else:
            _atk_handle = h
    except Exception:
        _atk_handle = None
    return _atk_handle


def _atk_device_get(device_id):
    h = _atk_open()
    if not h:
        return None
    try:
        inp = struct.pack("<IIII", _ATK_DSTS, 8, int(device_id), 0)
        out = ctypes.create_string_buffer(16)
        n = wintypes.DWORD(0)
        ok = ctypes.windll.kernel32.DeviceIoControl(
            h, _ATK_CONTROL, inp, len(inp), out, 16,
            ctypes.byref(n), None)
        if not ok:
            return None
        raw = struct.unpack("<i", out.raw[:4])[0]
        return raw - 65536
    except Exception:
        return None


def _atk_cpu_temp():
    v = _atk_device_get(_ATK_CPU_TEMP)
    if v is not None and 1 <= v <= 125:
        return float(v)
    return None


_asus_tried = False
_asus_dll = None
_wmi_temp_val = None
_wmi_temp_ts = 0.0


def _asus_cpu_temp():
    """ASUS EC 传感器（AsusWinIO64）。普通权限读不到时返回 None。"""
    global _asus_tried, _asus_dll
    if not _asus_tried:
        _asus_tried = True
        paths = [r"C:\Program Files\ASUS\AsLogDumpTool\EC\AsusWinIO64.dll"]
        try:
            import glob
            paths += glob.glob(
                r"C:\Windows\System32\DriverStore\FileRepository"
                r"\asussci2.inf_amd64_*\ASUSSystemAnalysis\AsusWinIO64.dll")
        except Exception:
            pass
        for path in paths:
            try:
                try:
                    os.add_dll_directory(os.path.dirname(path))
                except Exception:
                    pass
                lib = ctypes.WinDLL(path)
                lib.InitializeWinIo.restype = ctypes.c_int
                lib.Thermal_Read_Cpu_Temperature.restype = ctypes.c_int
                lib.InitializeWinIo()
                _asus_dll = lib
                break
            except Exception:
                continue
    if not _asus_dll:
        return None
    try:
        v = int(_asus_dll.Thermal_Read_Cpu_Temperature())
        if 100 < v <= 1250:
            return round(v / 10.0, 1)
        if 1 <= v <= 125:
            return float(v)
    except Exception:
        pass
    return None


def _wmi_cpu_temp():
    """ACPI 热区（部分机器这里才是 CPU 温度），失败返回 None。"""
    global _wmi_temp_val, _wmi_temp_ts
    now = time.time()
    if now - _wmi_temp_ts < 10.0:
        return _wmi_temp_val
    _wmi_temp_ts = now
    try:
        script = (
            "$z=Get-CimInstance -Namespace root/WMI "
            "-ClassName MSAcpi_ThermalZoneTemperature -ErrorAction Stop; "
            "$z | ForEach-Object { [int]$_.CurrentTemperature }")
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, timeout=4, creationflags=_CREATE_NO_WINDOW)
        vals = []
        for line in r.stdout.decode("utf-8", "ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                v = float(line)
            except Exception:
                continue
            if v > 1000.0:
                c = v / 10.0 - 273.15
            elif v > 150.0:
                c = v - 273.15
            else:
                c = v
            if 20.0 <= c <= 110.0:
                vals.append(c)
        # 单个 28°C 通常是主板/环境热区，不当作 CPU 温度
        _wmi_temp_val = round(max(vals), 1) if vals and max(vals) > 30.0 else None
    except Exception:
        _wmi_temp_val = None
    return _wmi_temp_val


def _fetch_cpu_temp():
    global _cpu_temp_val, _cpu_temp_busy
    try:
        c = _atk_cpu_temp()
        if c is None:
            c = _asus_cpu_temp()
        if c is None:
            c = _wmi_cpu_temp()
        _cpu_temp_val = round(c, 1) if c is not None else None
    except Exception:
        _cpu_temp_val = None
    finally:
        _cpu_temp_busy = False


def _cpu_temp():
    global _cpu_temp_ts, _cpu_temp_busy
    now = time.time()
    if now - _cpu_temp_ts < 4.0 or _cpu_temp_busy:
        return _cpu_temp_val
    _cpu_temp_ts = now
    _cpu_temp_busy = True
    threading.Thread(target=_fetch_cpu_temp, daemon=True).start()
    return _cpu_temp_val


# ---------------------------------------------------------------- GPU (NVML)
class _NV_UTIL(ctypes.Structure):
    _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]


class _NV_MEM(ctypes.Structure):
    _fields_ = [("total", ctypes.c_ulonglong),
                ("free", ctypes.c_ulonglong),
                ("used", ctypes.c_ulonglong)]


_nv = None
_nv_handle = None
_nv_name = ""
_nv_tried = False


def _nv_init():
    global _nv, _nv_handle, _nv_name, _nv_tried
    if _nv_tried:
        return
    _nv_tried = True
    try:
        lib = ctypes.WinDLL("nvml.dll")
        if lib.nvmlInit_v2() != 0:
            return
        count = ctypes.c_uint()
        if lib.nvmlDeviceGetCount_v2(ctypes.byref(count)) != 0 or count.value == 0:
            return
        handle = ctypes.c_void_p()
        if lib.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(handle)) != 0:
            return
        buf = ctypes.create_string_buffer(96)
        lib.nvmlDeviceGetName(handle, buf, 96)
        _nv = lib
        _nv_handle = handle
        _nv_name = buf.value.decode("utf-8", "ignore").strip()
    except Exception:
        _nv = None


def _clean_gpu_name(name):
    for s in ("NVIDIA ", "GeForce ", " GPU"):
        name = name.replace(s, "")
    return " ".join(name.split())


def gpu_short_name():
    _nv_init()
    name = _clean_gpu_name(_nv_name) or "GPU"
    return name.replace(" Laptop", "").strip() or "GPU"


def _gpu():
    _nv_init()
    if not _nv:
        return None
    try:
        util = _NV_UTIL()
        temp = ctypes.c_uint()
        power = ctypes.c_uint()
        mem = _NV_MEM()
        ok_u = _nv.nvmlDeviceGetUtilizationRates(
            _nv_handle, ctypes.byref(util)) == 0
        if not ok_u:
            util = _NV_UTIL()
            ok_u = _nv.nvmlDeviceGetUtilizationRates(
                _nv_handle, ctypes.byref(util)) == 0
        ok_t = _nv.nvmlDeviceGetTemperature(
            _nv_handle, 0, ctypes.byref(temp)) == 0
        ok_p = _nv.nvmlDeviceGetPowerUsage(
            _nv_handle, ctypes.byref(power)) == 0
        ok_m = _nv.nvmlDeviceGetMemoryInfo(
            _nv_handle, ctypes.byref(mem)) == 0
        return {
            "name": _clean_gpu_name(_nv_name),
            "usage": float(util.gpu) if ok_u else 0.0,
            "temp": float(temp.value) if ok_t else None,
            "power": round(power.value / 1000.0, 1) if ok_p else None,
            "mem_used": int(mem.used) if ok_m else None,
            "mem_total": int(mem.total) if ok_m else None,
        }
    except Exception:
        return None


# ---------------------------------------------------------------- 后台刷新
def _update():
    cpu_usage = _cpu_usage()
    ram_pct, ram_used, ram_total = _ram()
    gpu = _gpu()
    with _lock:
        _cache["cpu_name"] = _read_cpu_name()
        _cache["cpu_usage"] = cpu_usage
        _cache["ram_percent"] = ram_pct
        _cache["ram_used"] = ram_used
        _cache["ram_total"] = ram_total
        if gpu:
            _cache["gpu_name"] = gpu["name"]
            _cache["gpu_usage"] = gpu["usage"]
            _cache["gpu_temp"] = gpu["temp"]
            _cache["gpu_power"] = gpu["power"]
            _cache["gpu_mem_used"] = gpu["mem_used"]
            _cache["gpu_mem_total"] = gpu["mem_total"]
    cpu_power = _cpu_power()
    cpu_temp = _cpu_temp()
    with _lock:
        _cache["cpu_power"] = cpu_power
        _cache["cpu_temp"] = cpu_temp


def _loop(gen):
    while _run and gen == _gen:
        try:
            _update()
        except Exception:
            pass
        time.sleep(1.5)


def get():
    global _started, _run, _gen
    if not _started:
        _started = True
        _run = True
        _gen += 1
        _read_cpu_name()
        with _lock:
            _cache["cpu_name"] = _cpu_name
        threading.Thread(target=_loop, args=(_gen,), daemon=True).start()
    with _lock:
        return dict(_cache)


def stop():
    global _started, _run
    _run = False
    _started = False

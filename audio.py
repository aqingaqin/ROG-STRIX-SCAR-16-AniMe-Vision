# -*- coding: utf-8 -*-
"""audio.py — WASAPI 回环采集 + 频谱分析（纯 ctypes，零第三方依赖）

用途：让灯板随系统播放的声音律动（音乐可视化）。
参考微软 WASAPI 文档：IMMDeviceEnumerator / IAudioClient / IAudioCaptureClient。
"""

import ctypes
import threading
import time
from ctypes import wintypes

import numpy as np

_ole32 = ctypes.WinDLL("ole32")

# ---------------------------------------------------------------- COM 基础

class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


def _guid(s):
    from uuid import UUID
    u = UUID(s)
    return GUID(u.time_low, u.time_mid, u.time_hi_version,
                (ctypes.c_ubyte * 8)(*u.bytes[8:16]))


CLSID_MMDeviceEnumerator = _guid("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
IID_IMMDeviceEnumerator = _guid("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
IID_IAudioClient = _guid("{1CB9AD4C-DBFA-4C32-B178-C2F568A703B2}")
IID_IAudioCaptureClient = _guid("{C8ADBD64-E71E-48A0-A4DE-185C395CD317}")

CLSCTX_ALL = 0x17
AUDCLNT_STREAMFLAGS_LOOPBACK = 0x00020000
WAVE_FORMAT_IEEE_FLOAT = 3
WAVE_FORMAT_EXTENSIBLE = 0xFFFE


class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [("wFormatTag", wintypes.WORD), ("nChannels", wintypes.WORD),
                ("nSamplesPerSec", wintypes.DWORD), ("nAvgBytesPerSec", wintypes.DWORD),
                ("nBlockAlign", wintypes.WORD), ("wBitsPerSample", wintypes.WORD),
                ("cbSize", wintypes.WORD)]


def _vcall(this, index, argtypes, *args, restype=ctypes.c_long):
    """调用 COM 接口第 index 个虚函数。"""
    vtbl = ctypes.cast(this, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    proto = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    return proto(vtbl[index])(this, *args)


class WasapiLoopback:
    """采集系统正在播放的声音（回环模式）。"""

    def __init__(self):
        self.enum = ctypes.c_void_p()
        self.dev = ctypes.c_void_p()
        self.ac = ctypes.c_void_p()
        self.cc = ctypes.c_void_p()
        self.channels = 2
        self.rate = 48000
        self.is_float = True
        self.block_align = 8
        self.started = False
        self.error = None

    # -- 打开 --------------------------------------------------------
    def open(self):
        hr = _ole32.CoInitializeEx(None, 0)      # COINIT_MULTITHREADED
        if hr not in (0, 1):
            raise OSError(hr, "CoInitializeEx 失败")

        hr = _ole32.CoCreateInstance(
            ctypes.byref(CLSID_MMDeviceEnumerator), None, CLSCTX_ALL,
            ctypes.byref(IID_IMMDeviceEnumerator), ctypes.byref(self.enum))
        if hr < 0:
            raise OSError(hr, "CoCreateInstance(MMDeviceEnumerator) 失败")

        # GetDefaultAudioEndpoint(eRender=0, eConsole=0)
        hr = _vcall(self.enum, 4,
                    [ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)],
                    0, 0, ctypes.byref(self.dev))
        if hr < 0:
            raise OSError(hr, "GetDefaultAudioEndpoint 失败")

        # IMMDevice::Activate(IID_IAudioClient)
        hr = _vcall(self.dev, 3,
                    [ctypes.POINTER(GUID), ctypes.c_ulong, ctypes.c_void_p,
                     ctypes.POINTER(ctypes.c_void_p)],
                    ctypes.byref(IID_IAudioClient), CLSCTX_ALL, None,
                    ctypes.byref(self.ac))
        if hr < 0:
            raise OSError(hr, "Activate(IAudioClient) 失败")

        # GetMixFormat
        pwf = ctypes.c_void_p()
        hr = _vcall(self.ac, 8, [ctypes.POINTER(ctypes.c_void_p)], ctypes.byref(pwf))
        if hr < 0:
            raise OSError(hr, "GetMixFormat 失败")
        wf = ctypes.cast(pwf, ctypes.POINTER(WAVEFORMATEX)).contents
        self.channels = wf.nChannels
        self.rate = wf.nSamplesPerSec
        self.block_align = wf.nBlockAlign
        self.is_float = (wf.wFormatTag == WAVE_FORMAT_IEEE_FLOAT or
                         (wf.wFormatTag == WAVE_FORMAT_EXTENSIBLE and wf.wBitsPerSample == 32))

        # Initialize(shared, loopback, 1s buffer)
        hr = _vcall(self.ac, 3,
                    [ctypes.c_int, ctypes.c_ulong, ctypes.c_longlong,
                     ctypes.c_longlong, ctypes.c_void_p, ctypes.c_void_p],
                    0, AUDCLNT_STREAMFLAGS_LOOPBACK, 10_000_000, 0, pwf, None)
        if hr < 0:
            raise OSError(hr, "IAudioClient::Initialize 失败")

        # GetService(IAudioCaptureClient)
        hr = _vcall(self.ac, 14,
                    [ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)],
                    ctypes.byref(IID_IAudioCaptureClient), ctypes.byref(self.cc))
        if hr < 0:
            raise OSError(hr, "GetService(IAudioCaptureClient) 失败")

        hr = _vcall(self.ac, 10, [])             # Start()
        if hr < 0:
            raise OSError(hr, "IAudioClient::Start 失败")
        self.started = True
        return self

    # -- 读取 --------------------------------------------------------
    def read(self):
        """读取当前可用样本，返回 float32 单声道数组（可能为空）。"""
        if not self.started:
            return np.zeros(0, dtype=np.float32)
        chunks = []
        for _ in range(4):
            pkt = wintypes.UINT(0)
            hr = _vcall(self.cc, 5, [ctypes.POINTER(wintypes.UINT)], ctypes.byref(pkt))
            if hr < 0 or pkt.value == 0:
                break
            data = ctypes.POINTER(ctypes.c_byte)()
            frames = wintypes.UINT(0)
            flags = wintypes.DWORD(0)
            devpos = ctypes.c_ulonglong(0)
            qpc = ctypes.c_ulonglong(0)
            hr = _vcall(self.cc, 3,
                        [ctypes.POINTER(ctypes.POINTER(ctypes.c_byte)),
                         ctypes.POINTER(wintypes.UINT), ctypes.POINTER(wintypes.DWORD),
                         ctypes.POINTER(ctypes.c_ulonglong), ctypes.POINTER(ctypes.c_ulonglong)],
                        ctypes.byref(data), ctypes.byref(frames), ctypes.byref(flags),
                        ctypes.byref(devpos), ctypes.byref(qpc))
            if hr < 0:
                break
            n = frames.value
            if n:
                nbytes = n * self.block_align
                raw = ctypes.string_at(data, nbytes)
                dtype = np.float32 if self.is_float else np.int16
                arr = np.frombuffer(raw, dtype=dtype)
                if not self.is_float:
                    arr = arr.astype(np.float32) / 32768.0
                arr = arr.reshape(-1, self.channels).mean(axis=1)
                chunks.append(arr.astype(np.float32))
            _vcall(self.cc, 4, [wintypes.UINT], n)   # ReleaseBuffer
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks)

    def close(self):
        try:
            if self.started:
                _vcall(self.ac, 11, [])          # Stop()
                self.started = False
        except Exception:
            pass
        for ptr in (self.cc, self.ac, self.dev, self.enum):
            try:
                if ptr and ptr.value:
                    _vcall(ptr, 2, [])           # Release()
            except Exception:
                pass


# ---------------------------------------------------------------- 频谱分析

class BandAnalyzer:
    """把音频块转成频段电平（0..1），参数模型参照奥创的 AudioMode。

    奥创（ArmouryCrate.dll）暴露的可调项：
      AudioStrength / AudioDecay / AudioFullRange / AudioPattern
      / AnimationSpeedRatio / StrobingBeat{Start,End}Freq,Threshold,UseMax
    这里对应实现：
      gain     = AudioStrength（灵敏度）
      decay    = AudioDecay（衰减速度）
      full     = AudioFullRange（True=线性等宽频段，False=对数频段）
      beat_*   = StrobingBeatStartFreq/EndFreq/Threshold/UseMax（节拍检测）
    """

    def __init__(self, bands=24, fft_size=4096, sample_rate=48000,
                 decay=0.86, gain=1.0, full=False):
        self.bands = bands
        self.fft_size = fft_size
        self.rate = sample_rate
        self.decay = decay
        self.gain = gain
        self.full = full
        self.levels = np.zeros(bands, dtype=np.float32)
        self.levels_raw = np.zeros(bands, dtype=np.float32)
        self._max = np.zeros(bands, dtype=np.float32)
        self._peak = 0.0
        self._buf = np.zeros(0, dtype=np.float32)
        self._window = np.hanning(fft_size).astype(np.float32)

        # 频段划分：对数（音乐感更好）或全频段线性等宽
        if full:
            edges = np.linspace(20.0, sample_rate / 2.0, bands + 1)
        else:
            edges = np.geomspace(60.0, 12000.0, bands + 1)
        freqs = np.fft.rfftfreq(fft_size, 1.0 / sample_rate)
        self._idx = []
        for i in range(bands):
            lo, hi = edges[i], edges[i + 1]
            sel = np.where((freqs >= lo) & (freqs < hi))[0]
            if len(sel) == 0:
                sel = np.array([min(len(freqs) - 1,
                                    max(0, int((lo + hi) / 2 / (freqs[1] or 1))))])
            self._idx.append(sel)

        # 节拍检测（对应 StrobingBeat*）：在 [start,end] 频段内看能量包络
        self.beat_start = 60.0
        self.beat_end = 250.0
        self.beat_threshold = 1.35     # 当前能量 / 滑动均值 超过它算一拍
        self.beat_use_max = False
        self.beat_budget = 0.0         # 0..1，触发后衰减，供渲染用
        self._beat_flash = 0.0
        self._beat_hist = np.zeros(64, dtype=np.float32)
        self._beat_pos = 0
        self._beat_last = 0.0
        self.beat_bpm = 0.0
        self._beat_times = []

    # -- 频段 -> 频谱 -------------------------------------------------
    def _spectrum(self):
        block = self._buf[-self.fft_size:]
        spec = np.abs(np.fft.rfft(block * self._window)) / (self.fft_size / 4)
        return spec

    def feed(self, samples):
        if samples is None or len(samples) == 0:
            return
        self._buf = np.concatenate([self._buf, samples])
        if len(self._buf) < self.fft_size:
            return
        spec = self._spectrum()
        self._buf = self._buf[-self.fft_size // 2:]

        vals = np.array([spec[idxs].mean() if len(idxs) else 0.0
                         for idxs in self._idx], dtype=np.float32)
        # 对数压缩动态范围，弱信号也能看见
        vals = np.log1p(vals * 40.0) / np.log1p(40.0)
        # 全局缓降峰值自动增益，并设噪声下限
        self._peak = max(self._peak * 0.995, float(vals.max()))
        base = vals / max(self._peak, 0.08)
        vals = np.clip(base * float(self.gain), 0.0, 1.0)
        vals[vals < 0.03] = 0.0
        self.levels_raw = vals
        # 与奥创的 AudioDecay 对应：值衰减速度可调（越小掉得越快）
        self.levels = np.maximum(vals, self.levels * self.decay)
        self._update_beat(spec)

    def _freq_band_energy(self, spec):
        """节拍检测用频段的总能量（对应 StrobingBeatStartFreq/EndFreq）。"""
        freqs = np.fft.rfftfreq(self.fft_size, 1.0 / self.rate)
        lo = max(0, int(self.beat_start / (freqs[1] or 1)))
        hi = min(len(spec) - 1, int(self.beat_end / (freqs[1] or 1)))
        if hi <= lo:
            return 0.0
        seg = spec[lo:hi + 1]
        val = float(seg.max()) if self.beat_use_max else float(seg.mean())
        return val

    def _update_beat(self, spec):
        e = self._freq_band_energy(spec)
        e = float(np.log1p(e * 40.0))
        self._beat_hist[self._beat_pos] = e
        self._beat_pos = (self._beat_pos + 1) % len(self._beat_hist)
        avg = float(self._beat_hist.mean())
        now = time.time()
        # 包络相对均值突然抬升 = 一拍；两次触发至少隔 120ms，避免连击
        if avg > 1e-4 and e > avg * self.beat_threshold and now - self._beat_last > 0.12:
            self._beat_last = now
            self._beat_flash = 1.0
            self._beat_times.append(now)
            self._beat_times = [t for t in self._beat_times if now - t < 3.0]
            if len(self._beat_times) >= 2:
                span = self._beat_times[-1] - self._beat_times[0]
                if span > 0.2:
                    self.beat_bpm = 60.0 * (len(self._beat_times) - 1) / span
        # 频闪强度按 12/s 衰减
        self._beat_flash = max(0.0, self._beat_flash - 0.08)
        self.beat_budget = self._beat_flash

    def set_gain(self, gain):
        """实时调整灵敏度（对应 AudioStrength，0.1~4）。"""
        self.gain = max(0.1, min(4.0, float(gain)))

    def rebuild(self, full=None):
        """切换全频段模式时重建频段边界。"""
        if full is not None:
            self.full = bool(full)
        freqs = np.fft.rfftfreq(self.fft_size, 1.0 / self.rate)
        bands = self.bands
        if self.full:
            edges = np.linspace(20.0, self.rate / 2.0, bands + 1)
        else:
            edges = np.geomspace(60.0, 12000.0, bands + 1)
        idx = []
        for i in range(bands):
            lo, hi = edges[i], edges[i + 1]
            sel = np.where((freqs >= lo) & (freqs < hi))[0]
            if len(sel) == 0:
                sel = np.array([min(len(freqs) - 1, max(0, int(lo / (freqs[1] or 1))))])
            idx.append(sel)
        self._idx = idx
        self.levels = np.zeros(bands, dtype=np.float32)
        self.levels_raw = np.zeros(bands, dtype=np.float32)

    def set_decay(self, decay):
        """实时调整衰减（对应 AudioDecay，0.5~0.99）。"""
        self.decay = max(0.5, min(0.99, float(decay)))

    def set_beat(self, start=None, end=None, threshold=None, use_max=None):
        if start is not None:
            self.beat_start = max(20.0, min(2000.0, float(start)))
        if end is not None:
            self.beat_end = max(self.beat_start + 20.0, min(5000.0, float(end)))
        if threshold is not None:
            self.beat_threshold = max(1.05, min(4.0, float(threshold)))
        if use_max is not None:
            self.beat_use_max = bool(use_max)

    def get(self):
        return self.levels

    def beat(self):
        return self.beat_budget, self.beat_bpm


class AudioWorker:
    """后台线程：持续采集系统声音并更新频谱（COM 需要在本线程初始化）。"""

    def __init__(self, bands=24, gain=1.0):
        self.bands = bands
        self.analyzer = BandAnalyzer(bands=bands, gain=gain)
        self.peaks = np.zeros(bands, dtype=np.float32)
        self._thread = None
        self._run = False
        self.error = None
        self.cap = None

    def start(self):
        self._run = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def _loop(self):
        try:
            self.cap = WasapiLoopback().open()
        except Exception as e:      # 设备/权限问题
            self.error = str(e)
            return
        while self._run:
            try:
                s = self.cap.read()
                if len(s):
                    self.analyzer.rate = self.cap.rate
                    self.analyzer.feed(s)
            except Exception as e:
                self.error = str(e)
                break
            time.sleep(0.008)
        try:
            self.cap.close()
        except Exception:
            pass
        self.cap = None

    def levels(self):
        """返回 (当前电平, 峰值保持)。"""
        lv = self.analyzer.get()
        self.peaks = np.maximum(lv, self.peaks * 0.96)
        return lv, self.peaks

    def beat(self):
        """返回 (节拍强度 0..1, BPM)。"""
        return self.analyzer.beat()

    def stop(self):
        self._run = False
        if self._thread:
            self._thread.join(timeout=1.5)
            self._thread = None
        self.analyzer.levels = np.zeros(self.bands, dtype=np.float32)


if __name__ == "__main__":
    cap = WasapiLoopback().open()
    print(f"采集: {cap.rate} Hz, {cap.channels} ch, float={cap.is_float}")
    an = BandAnalyzer()
    t0 = time.time()
    peak = 0.0
    while time.time() - t0 < 3.0:
        s = cap.read()
        if len(s):
            peak = max(peak, float(np.abs(s).max()))
            an.feed(s)
        time.sleep(0.01)
    print("峰值:", round(peak, 4))
    print("频段:", np.round(an.get(), 2).tolist())
    cap.close()

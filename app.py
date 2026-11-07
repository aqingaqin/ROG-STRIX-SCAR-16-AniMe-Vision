# -*- coding: utf-8 -*-
"""AniMe Vision 控制台 —— 本地 Web 应用。

启动：python app.py [端口]
然后浏览器打开 http://127.0.0.1:8765
"""

import base64
import ctypes
import io
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import animelib

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("ANIME_PORT", "8765"))
BRIGHTNESS_NAMES = ["关", "低", "中", "高"]

SYS_KEYS = ["cpu_name", "cpu_usage", "cpu_temp", "cpu_power",
            "gpu_name", "gpu_usage", "gpu_temp", "gpu_power",
            "ram", "vram", "time", "battery", "app"]


def default_sys_prefs():
    return {
        "enabled": {k: True for k in SYS_KEYS},
        "order": list(SYS_KEYS),
        "display": "scroll",
        "durations": {k: 4.0 for k in SYS_KEYS},
        "rotate_sec": 4.0,
        "font_size": 12,
        "font_v": 1.0,
        "scroll_speed": 90.0,
        "custom_cpu_name": "",
        "custom_gpu_name": "",
        "app_prefix": "正在使用",
        "auto_game": True,
    }


def log(*a):
    print("[anime]", *a, flush=True)


# ================================================================ 系统信息

class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [("ACLineStatus", ctypes.c_ubyte),
                ("BatteryFlag", ctypes.c_ubyte),
                ("BatteryLifePercent", ctypes.c_ubyte),
                ("Reserved1", ctypes.c_ubyte),
                ("BatteryLifeTime", ctypes.c_ulong),
                ("BatteryFullLifeTime", ctypes.c_ulong)]


def battery_percent():
    try:
        st = SYSTEM_POWER_STATUS()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(st)):
            if st.BatteryLifePercent != 255:
                return st.BatteryLifePercent
    except Exception:
        pass
    return None


def cpu_percent_cached():
    """基于 GetSystemTimes 的整机 CPU 占用（需两次采样）。"""
    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", ctypes.c_uint32),
                    ("dwHighDateTime", ctypes.c_uint32)]

    def snap():
        idle, kern, user = FILETIME(), FILETIME(), FILETIME()
        ctypes.windll.kernel32.GetSystemTimes(
            ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user))

        def q(f):
            return (f.dwHighDateTime << 32) | f.dwLowDateTime
        return q(idle), q(kern) + q(user)

    a = snap()
    time.sleep(0.15)
    b = snap()
    di, dt = b[0] - a[0], b[1] - a[1]
    if dt <= 0:
        return None
    return max(0, min(100, int(round((1 - di / dt) * 100))))


_APP_LABELS = {
    # 浏览器
    "chrome.exe": "Chrome", "msedge.exe": "Edge", "firefox.exe": "Firefox",
    "brave.exe": "Brave", "opera.exe": "Opera", "vivaldi.exe": "Vivaldi",
    "iexplore.exe": "Internet Explorer",
    # 办公
    "winword.exe": "Word", "excel.exe": "Excel", "powerpnt.exe": "PowerPoint",
    "outlook.exe": "Outlook", "onenote.exe": "OneNote",
    "msaccess.exe": "Access", "mspublisher.exe": "Publisher",
    "wps.exe": "WPS Office", "et.exe": "WPS 表格",
    "wpp.exe": "WPS 演示", "wpspdf.exe": "WPS PDF",
    # 开发
    "code.exe": "VS Code", "devenv.exe": "Visual Studio",
    "idea64.exe": "IntelliJ IDEA", "pycharm64.exe": "PyCharm",
    "webstorm64.exe": "WebStorm", "clion64.exe": "CLion",
    "goland64.exe": "GoLand", "rider64.exe": "Rider",
    "datagrip64.exe": "DataGrip", "android studio.exe": "Android Studio",
    "sublime_text.exe": "Sublime Text", "notepad++.exe": "Notepad++",
    "git-bash.exe": "Git Bash",
    # Windows 系统
    "notepad.exe": "记事本", "explorer.exe": "资源管理器",
    "desktop": "桌面",
    "taskmgr.exe": "任务管理器",
    "systemsettings.exe": "设置",
    "control.exe": "控制面板",
    "cmd.exe": "命令提示符",
    "conhost.exe": "控制台",
    "powershell.exe": "PowerShell", "pwsh.exe": "PowerShell",
    "powershell_ise.exe": "PowerShell ISE",
    "windowsterminal.exe": "终端", "wt.exe": "终端",
    "openconsole.exe": "终端",
    "regedit.exe": "注册表编辑器",
    "mmc.exe": "管理控制台",
    "devmgmt": "设备管理器", "services": "服务",
    "diskmgmt": "磁盘管理", "taskschd": "任务计划程序",
    "gpedit": "组策略", "compmgmt": "计算机管理",
    "eventvwr": "事件查看器",
    "eventvwr.exe": "事件查看器",
    "resmon.exe": "资源监视器",
    "perfmon": "性能监视器",
    "perfmon.exe": "性能监视器",
    "msinfo32.exe": "系统信息",
    "cleanmgr.exe": "磁盘清理",
    "dfrgui.exe": "优化驱动器",
    "mstsc.exe": "远程桌面连接",
    "quickassist.exe": "快速助手",
    "sechealthui.exe": "Windows 安全中心",
    "smartscreen.exe": "SmartScreen",
    "searchhost.exe": "搜索",
    "startmenuexperiencehost.exe": "开始菜单",
    "shellexperiencehost.exe": "系统界面",
    "lockapp.exe": "锁屏",
    "logonui.exe": "登录",
    "applicationframehost.exe": "应用",
    # Windows 应用
    "calculatorapp.exe": "计算器", "calculator.exe": "计算器",
    "mspaint.exe": "画图", "paint3d.exe": "画图 3D",
    "snippingtool.exe": "截图工具", "screensketch.exe": "截图工具",
    "photos.exe": "照片", "microsoft.photos.exe": "照片",
    "windowscamera.exe": "相机", "camera.exe": "相机",
    "microsoft.media.player.exe": "媒体播放器",
    "wmplayer.exe": "Windows Media Player",
    "video.ui.exe": "电影和电视", "music.ui.exe": "Groove 音乐",
    "time.exe": "时钟", "alarms.exe": "闹钟和时钟",
    "weather.exe": "天气", "maps.exe": "地图", "people.exe": "人脉",
    "hxoutlook.exe": "邮件", "hxcalendarappimm.exe": "日历",
    "winstore.app.exe": "Microsoft Store",
    "xboxpcapp.exe": "Xbox", "gamebar.exe": "Xbox Game Bar",
    "phoneexperiencehost.exe": "手机连接", "yourphone.exe": "手机连接",
    "soundrecorder.exe": "录音机",
    "magnify.exe": "放大镜", "narrator.exe": "讲述人",
    "osk.exe": "屏幕键盘", "psr.exe": "步骤记录器",
    # 通讯与音乐
    "steam.exe": "Steam", "steamwebhelper.exe": "Steam",
    "spotify.exe": "Spotify", "discord.exe": "Discord",
    "telegram.exe": "Telegram", "whatsapp.exe": "WhatsApp",
    "zoom.exe": "Zoom", "teams.exe": "Teams", "ms-teams.exe": "Teams",
    "wemeetapp.exe": "腾讯会议",
    "dingtalk.exe": "钉钉", "feishu.exe": "飞书", "lark.exe": "飞书",
    "wechat.exe": "微信", "weixin.exe": "微信", "qq.exe": "QQ",
    "qqnt.exe": "QQ", "skype.exe": "Skype", "slack.exe": "Slack",
    # 米哈游与游戏
    "hyp.exe": "米哈游启动器", "hoyoplay.exe": "米哈游启动器",
    "hyplauncher.exe": "米哈游启动器",
    "mihoyolauncher.exe": "米哈游启动器",
    "mihoyo launcher.exe": "米哈游启动器",
    "yuanshen.exe": "原神", "genshinimpact.exe": "原神",
    "starrail.exe": "崩坏：星穹铁道",
    "zenlesszonezero.exe": "绝区零",
    "bh3.exe": "崩坏3", "honkaiimpact3.exe": "崩坏3",
    "tearsofthemis.exe": "未定事件簿",
    "wutheringwaves.exe": "鸣潮", "wuthering waves.exe": "鸣潮",
    "narakabladepoint.exe": "永劫无间",
    "deltaforceclient-win64-shipping.exe": "三角洲行动",
    "crossfire.exe": "穿越火线",
    "dnf.exe": "地下城与勇士",
    "leagueclient.exe": "英雄联盟", "leagueclientux.exe": "英雄联盟",
    "league of legends.exe": "英雄联盟",
    "valorant.exe": "无畏契约",
    "valorant-win64-shipping.exe": "无畏契约",
    "cs2.exe": "CS2", "csgo.exe": "CS:GO",
    "dota2.exe": "Dota 2",
    "tslgame.exe": "PUBG",
    "r5apex.exe": "Apex 英雄",
    "fortniteclient-win64-shipping.exe": "堡垒之夜",
    "gta5.exe": "GTA V", "gta5_enhanced.exe": "GTA V",
    "rdr2.exe": "荒野大镖客 2",
    "cyberpunk2077.exe": "赛博朋克 2077",
    "eldenring.exe": "艾尔登法环",
    "bg3.exe": "博德之门 3", "bg3_dx11.exe": "博德之门 3",
    "b1-win64-shipping.exe": "黑神话：悟空",
    "palworld-win64-shipping.exe": "幻兽帕鲁",
    "helldivers2.exe": "绝地潜兵 2",
    "overwatch.exe": "守望先锋",
    "rainbowsix.exe": "彩虹六号：围攻",
    "bf2042.exe": "战地 2042",
    "forzahorizon5.exe": "极限竞速：地平线 5",
    "ittakestwo.exe": "双人成行",
    "robloxplayerbeta.exe": "Roblox",
    "minecraft.windows.exe": "Minecraft",
    "minecraftlauncher.exe": "Minecraft 启动器",
    "hearthstone.exe": "炉石传说",
    "wow.exe": "魔兽世界",
    "diablo iv.exe": "暗黑破坏神 IV",
    "starcraft ii.exe": "星际争霸 II",
    "osu!.exe": "osu!",
    "rocketleague.exe": "火箭联盟",
    "terraria.exe": "泰拉瑞亚",
    "stardew valley.exe": "星露谷物语",
    "among us.exe": "Among Us",
    "phasmophobia.exe": "恐鬼症",
    "lethal company.exe": "致命公司",
    "pgr.exe": "战双帕弥什",
    "nikke.exe": "胜利女神：妮姬",
    # 媒体
    "vlc.exe": "VLC", "potplayermini64.exe": "PotPlayer",
    "potplayermini.exe": "PotPlayer",
    "mpc-hc64.exe": "MPC-HC", "mpc-hc.exe": "MPC-HC",
    "mpv.exe": "mpv", "foobar2000.exe": "foobar2000",
    "qqmusic.exe": "QQ 音乐", "cloudmusic.exe": "网易云音乐",
    "obs64.exe": "OBS Studio", "obs32.exe": "OBS Studio",
    # 游戏平台
    "epicgameslauncher.exe": "Epic Games",
    "battle.net.exe": "Battle.net",
    "eadesktop.exe": "EA app",
    "ubisoftconnect.exe": "Ubisoft Connect",
    "galaxyclient.exe": "GOG Galaxy",
    "riotclientservices.exe": "Riot Client",
    # 工具与 Adobe
    "winrar.exe": "WinRAR", "7zfm.exe": "7-Zip",
    "bandizip.exe": "Bandizip",
    "idman.exe": "IDM", "thunder.exe": "迅雷",
    "qbittorrent.exe": "qBittorrent",
    "photoshop.exe": "Photoshop", "illustrator.exe": "Illustrator",
    "premiere pro.exe": "Premiere Pro", "afterfx.exe": "After Effects",
    "indesign.exe": "InDesign", "lightroom.exe": "Lightroom",
    "acrobat.exe": "Acrobat", "acrord32.exe": "Acrobat Reader",
}


# 只有真正的游戏进程算“正在玩”；Steam/Epic/米哈游启动器这类平台仍算“正在使用”
_GAME_IDS = frozenset({
    "yuanshen.exe", "genshinimpact.exe", "starrail.exe",
    "zenlesszonezero.exe", "bh3.exe", "honkaiimpact3.exe",
    "tearsofthemis.exe", "wutheringwaves.exe", "wuthering waves.exe",
    "narakabladepoint.exe", "deltaforceclient-win64-shipping.exe",
    "crossfire.exe", "dnf.exe",
    "leagueclient.exe", "leagueclientux.exe", "league of legends.exe",
    "valorant.exe", "valorant-win64-shipping.exe",
    "cs2.exe", "csgo.exe", "dota2.exe", "tslgame.exe", "r5apex.exe",
    "fortniteclient-win64-shipping.exe",
    "gta5.exe", "gta5_enhanced.exe", "rdr2.exe", "cyberpunk2077.exe",
    "eldenring.exe", "bg3.exe", "bg3_dx11.exe",
    "b1-win64-shipping.exe", "palworld-win64-shipping.exe",
    "helldivers2.exe", "overwatch.exe", "rainbowsix.exe", "bf2042.exe",
    "forzahorizon5.exe", "ittakestwo.exe", "robloxplayerbeta.exe",
    "minecraft.windows.exe", "hearthstone.exe", "wow.exe",
    "diablo iv.exe", "starcraft ii.exe", "osu!.exe",
    "rocketleague.exe", "terraria.exe", "stardew valley.exe",
    "among us.exe", "phasmophobia.exe", "lethal company.exe",
    "pgr.exe", "nikke.exe",
})


def is_game_app(exe):
    return bool(exe) and exe.lower() in _GAME_IDS


def _window_class(hwnd):
    """取窗口类名；取不到返回空串。"""
    try:
        user32 = ctypes.windll.user32
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(ctypes.c_void_p(hwnd), buf, 256)
        return buf.value
    except Exception:
        return ""


def _window_title(hwnd):
    """取窗口标题；取不到返回空串。"""
    try:
        user32 = ctypes.windll.user32
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(ctypes.c_void_p(hwnd), buf, 512)
        return buf.value
    except Exception:
        return ""


def foreground_app():
    """当前前台窗口对应的程序标识（如 chrome.exe；桌面返回 desktop）。"""
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd),
                                        ctypes.byref(pid))
        kernel32.OpenProcess.restype = ctypes.c_void_p
        # PROCESS_QUERY_LIMITED_INFORMATION，普通权限也能查大多数进程
        handle = kernel32.OpenProcess(0x1000, False, pid.value)
        if not handle:
            return None
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = ctypes.c_ulong(len(buf))
            kernel32.QueryFullProcessImageNameW.argtypes = [
                ctypes.c_void_p, ctypes.c_ulong, ctypes.c_wchar_p,
                ctypes.POINTER(ctypes.c_ulong)]
            if not kernel32.QueryFullProcessImageNameW(
                    handle, 0, buf, ctypes.byref(size)):
                return None
            exe = os.path.basename(buf.value)
            key = exe.lower()
            if key in ("javaw.exe", "java.exe"):
                if "minecraft" in _window_title(hwnd).lower():
                    return "minecraft.windows.exe"
            if key == "client-win64-shipping.exe":
                title = _window_title(hwnd).lower()
                if "wuthering" in title or "鸣潮" in title:
                    return "wutheringwaves.exe"
            if key == "launcher.exe":
                title = _window_title(hwnd)
                tl = title.lower()
                if ("米哈游" in title or "hoyo" in tl or "原神" in title
                        or "星穹" in title or "绝区零" in title
                        or "未定事件" in title):
                    return "hyp.exe"
            if key == "explorer.exe":
                cls = _window_class(hwnd).lower()
                if cls in ("progman", "workerw", "shelldll_defview"):
                    return "desktop"
                title = _window_title(hwnd)
                if "控制面板" in title or "control panel" in title.lower():
                    return "control.exe"
                return "explorer.exe"
            if key == "mmc.exe":
                title = _window_title(hwnd).lower()
                for needle, ident in (
                        ("设备管理器", "devmgmt"),
                        ("device manager", "devmgmt"),
                        ("磁盘管理", "diskmgmt"),
                        ("disk management", "diskmgmt"),
                        ("任务计划程序", "taskschd"),
                        ("task scheduler", "taskschd"),
                        ("事件查看器", "eventvwr"),
                        ("event viewer", "eventvwr"),
                        ("性能监视器", "perfmon"),
                        ("performance monitor", "perfmon"),
                        ("组策略", "gpedit"),
                        ("group policy", "gpedit"),
                        ("计算机管理", "compmgmt"),
                        ("computer management", "compmgmt"),
                        ("服务", "services"),
                        ("services", "services")):
                    if needle in title:
                        return ident
                return "mmc.exe"
            if key in ("steamwebhelper.exe", "steamwebhelper"):
                return "steam.exe"
            return exe
        finally:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
    except Exception:
        return None


def app_display_name(exe):
    """进程文件名 -> 屏幕上显示的短名字。"""
    if not exe:
        return None
    key = exe.lower()
    if key in _APP_LABELS:
        return _APP_LABELS[key]
    name = exe[:-4] if key.endswith(".exe") else exe
    return (name[:1].upper() + name[1:]) if name else None


# ================================================================ 华硕灯效冲突处理

CONFLICT_SERVICES = ("LightingService", "ROG Live Service")
CONFLICT_PROCS = ("AacAmbientLighting.exe",)


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def pause_asus_lighting():
    """停止与灯板抢控制的华硕服务/进程（需管理员权限）。"""
    if not is_admin() or os.environ.get("ANIME_NO_PAUSE") == "1":
        return False
    import subprocess
    ok = False
    for svc in CONFLICT_SERVICES:
        try:
            r = subprocess.run(["sc", "stop", svc], capture_output=True,
                               text=True, timeout=25,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
            log(f"停止服务 {svc}: exit={r.returncode}")
            ok = ok or r.returncode == 0
        except Exception as e:
            log(f"停止服务 {svc} 失败: {e}")
    for _ in range(4):
        for proc in CONFLICT_PROCS:
            try:
                subprocess.run(["taskkill", "/F", "/IM", proc],
                               capture_output=True, timeout=10,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
            except Exception:
                pass
        time.sleep(0.5)
    return ok


def start_conflict_watchdog():
    """管理员模式下持续看守：华硕环境光进程被看门狗拉起时再次结束它。"""
    if not is_admin() or os.environ.get("ANIME_NO_PAUSE") == "1":
        return None
    import subprocess

    def run():
        while True:
            for proc in CONFLICT_PROCS:
                try:
                    subprocess.run(["taskkill", "/F", "/IM", proc],
                                   capture_output=True, timeout=10,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
                except Exception:
                    pass
            time.sleep(2.5)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


def resume_asus_lighting():
    """退出时把服务恢复运行。"""
    if not is_admin():
        return
    import subprocess
    for svc in CONFLICT_SERVICES:
        try:
            subprocess.run(["sc", "start", svc], capture_output=True, timeout=25,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
            log(f"已恢复服务 {svc}")
        except Exception:
            pass


# ================================================================ 渲染引擎

def _clean_builtin_name(name):
    """内置灯效文件名 -> 显示名。

    For Those Who Dare_Strix_NB      -> For Those Who Dare
    For-those-who-dare_2_strix_NB    -> For-those-who-dare 2
    ROG_glitch_still_NB              -> ROG glitch still
    start_1 / sleep_2                -> start 1 / sleep 2
    """
    import re
    s = name
    s = re.sub(r"_thumbnail$", "", s, flags=re.I)
    # 去掉设备/型号后缀
    s = re.sub(r"(_strix)?_NB$", "", s, flags=re.I)
    # "_2_strix" 这种变体：把 _2 变成 " 2"
    s = re.sub(r"_(\d+)(?=$|_)", r" \1", s)
    s = re.sub(r"_+", " ", s).strip()
    return s or name


def _builtin_theme(dirpath, root):
    """内置灯效的主题名取相对路径的首段。"""
    import os
    rel = os.path.relpath(dirpath, root)
    parts = [p for p in rel.replace("\\", "/").split("/") if p and p != "."]
    if not parts:
        return "内置"
    if parts[0] == "DefaultGifData" and len(parts) > 1:
        return parts[1]          # ROG Gallery / Trend
    if parts[0] == "system" and len(parts) > 1:
        return parts[1]          # PowerIndicator / Notification / Alarm / Calendar
    return parts[0]              # ECAnimations


class Engine:
    def __init__(self):
        self.panel = animelib.Panel(fps=20)
        self.mode = "off"
        self.frame = bytes(animelib.LED_COUNT)
        self._lock = threading.Lock()
        self._png_ver = -1
        self._png_cache = b""
        self._frame_ver = 0
        self.cfg = {}
        self._sys_prefs = default_sys_prefs()
        self._restore = {"type": "off"}
        self._strip = None
        self._scroll = 0.0
        self._gif = []
        self._gif_idx = 0
        self._gif_next = 0.0
        self._gif_loops = 0
        self._gif_speed = 0.5      # 播放倍速（>1 更快，<1 更慢）
        self._gif_total = 0.0      # 当前动画的总时长（秒，已按倍速折算）
        self._last_effect = None
        self._last_fx = None
        self._pl_ids = []          # 播放列表（灯效 id，按顺序）
        self._pl_index = 0         # 当前播到第几个
        self._pl_active = False    # 播放列表是否在运行
        self._pl_cycles = 0        # 当前灯效已播完的轮数
        self._pl_loops = 1         # 每个灯效播几轮再切
        self._pl_params = {}       # 播放列表用的亮度/倍速/模式
        self._pl_pending = False   # 需要切到下一个灯效（主循环处理）
        self._sys_last = 0.0
        self._sys_page = 0
        self._sys_page_t = 0.0
        self._sys_pages = []
        self._sys_page_keys = []
        self._music = None
        self._music_style = "bars"
        self._m_bars = 11
        self._m_cw = 2
        self._m_cg = 1
        self._m_gap_level = 0.0
        self._m_mode = "even"      # even=固定整数列(完全均匀) / compact=12条紧凑
        self._np = None            # 当前播放信息（SMTC）
        self._np_show = True       # 显示歌名/歌手
        self._m_show_bars = True   # 显示音频柱
        self._np_frac = 0.45       # 上方文字区占面板高度比例
        self._np_units = 15        # 歌名字号（按灯带高度适配）
        self._np_speed = 12.0      # 滚动速度（格/秒）
        self._np_bar_dim = 0.40    # 有歌名时柱子的亮度系数
        self._np_v_off = 0.5       # 歌名垂直偏移（格，正数向下）默认下移半格
        self._music_gain = 1.0     # 灵敏度（归一化之后生效）
        self._music_decay = 0.86   # 频段衰减（对应奥创 AudioDecay）
        self._music_full = False   # True=线性全频段（对应 AudioFullRange）
        self._drops = None         # 雨滴状态
        self._wave_phase = 0.0     # 波形相位
        self._dt = 1 / 60.0        # 上一帧间隔（供动画类样式用）
        self._m_peaks = False      # 是否画柱顶峰值白点（关掉顶边更平齐）
        self._m_gradient = False   # 柱身亮度是否渐变（关掉顶边更平）
        self._load_prefs()         # 载入上次保存的设置
        self._music_sub = "bars"
        self._sub_t0 = 0.0
        self._bars_time = 12.0
        self._np_time = 12.0
        self._np_scroll = 0.0
        self._history = None
        self._stop = False
        self._th = threading.Thread(target=self._loop, daemon=True)
        self._th.start()

    # -- 偏好持久化 -------------------------------------------------
    PREFS_PATH = None

    def _prefs_file(self):
        if Engine.PREFS_PATH is None:
            Engine.PREFS_PATH = os.path.join(ROOT, "prefs.json")
        return Engine.PREFS_PATH

    def _load_prefs(self):
        try:
            with open(self._prefs_file(), "r", encoding="utf-8") as f:
                p = json.load(f)
        except Exception:
            return
        try:
            self._m_bars = int(p.get("bars", self._m_bars))
            self._m_cw = int(p.get("col_width", self._m_cw))
            self._m_cg = int(p.get("col_gap", self._m_cg))
            self._m_gap_level = float(p.get("gap_level", self._m_gap_level))
            if p.get("mode") in ("even", "compact"):
                self._m_mode = p["mode"]
            self._np_show = bool(p.get("show_title", self._np_show))
            self._m_show_bars = bool(p.get("show_bars", self._m_show_bars))
            self._np_units = int(p.get("np_units", self._np_units))
            self._np_speed = float(p.get("np_speed", self._np_speed))
            self._np_bar_dim = float(p.get("np_bar_dim", self._np_bar_dim))
            self._np_v_off = float(p.get("np_v_off", self._np_v_off))
            self._music_gain = float(p.get("gain", self._music_gain))
            self._m_peaks = bool(p.get("peaks", self._m_peaks))
            self._m_gradient = bool(p.get("gradient", self._m_gradient))
            if p.get("music_style") in ("bars", "vbar", "pbar11", "waterfall",
                                        "gh", "strobing", "raindrop", "wave",
                                        "spectrum1"):
                self._music_style = p["music_style"]
            self._gif_speed = float(p.get("gif_speed", self._gif_speed))
            self._music_decay = float(p.get("music_decay", self._music_decay))
            self._music_full = bool(p.get("music_full", self._music_full))
            pl = p.get("playlist")
            if isinstance(pl, list):
                self._pl_ids = [str(x) for x in pl]
            self._pl_loops = max(1, min(20, int(p.get("playlist_loops", self._pl_loops))))
            pp = p.get("playlist_params")
            if isinstance(pp, dict):
                try:
                    if pp.get("brightness") is not None:
                        self._pl_params["brightness"] = max(
                            0.1, min(2.0, float(pp["brightness"])))
                    if pp.get("speed") is not None:
                        self._pl_params["speed"] = max(
                            0.1, min(5.0, float(pp["speed"])))
                    if "mode" in pp:
                        self._pl_params["mode"] = pp.get("mode") or None
                except Exception:
                    pass
            si = p.get("sysinfo")
            if isinstance(si, dict):
                base = default_sys_prefs()
                if isinstance(si.get("enabled"), dict):
                    for k in SYS_KEYS:
                        if k in si["enabled"]:
                            base["enabled"][k] = bool(si["enabled"][k])
                else:
                    # 旧格式：time / battery / cpu / app
                    base["enabled"]["time"] = bool(si.get("time", True))
                    base["enabled"]["battery"] = bool(si.get("battery", True))
                    base["enabled"]["cpu_usage"] = bool(si.get("cpu", True))
                    base["enabled"]["app"] = bool(si.get("app", True))
                order = si.get("order")
                if isinstance(order, list):
                    valid = []
                    for k in order:
                        k = str(k)
                        if k in SYS_KEYS and k not in valid:
                            valid.append(k)
                    for k in SYS_KEYS:
                        if k not in valid:
                            valid.append(k)
                    base["order"] = valid
                if si.get("display") in ("scroll", "rotate"):
                    base["display"] = si["display"]
                try:
                    base["rotate_sec"] = max(
                        2.0, min(15.0, float(si.get("rotate_sec", 4))))
                except Exception:
                    pass
                durs = si.get("durations")
                if isinstance(durs, dict):
                    for k in SYS_KEYS:
                        if k in durs:
                            try:
                                base["durations"][k] = max(
                                    1.0, min(30.0, float(durs[k])))
                            except Exception:
                                pass
                if isinstance(si.get("custom_cpu_name"), str):
                    base["custom_cpu_name"] = si["custom_cpu_name"].strip()
                if isinstance(si.get("custom_gpu_name"), str):
                    base["custom_gpu_name"] = si["custom_gpu_name"].strip()
                try:
                    base["font_size"] = max(
                        6, min(14, int(si.get("font_size", 12))))
                except Exception:
                    pass
                try:
                    base["scroll_speed"] = max(
                        30.0, min(300.0, float(si.get("scroll_speed", 90))))
                except Exception:
                    pass
                try:
                    base["font_v"] = max(
                        -3.0, min(3.0, float(si.get("font_v", 1.0))))
                except Exception:
                    pass
                if "app_prefix" in si:
                    base["app_prefix"] = str(si["app_prefix"])
                if "auto_game" in si:
                    base["auto_game"] = bool(si["auto_game"])
                self._sys_prefs = base
            r = p.get("restore")
            if isinstance(r, dict) and r.get("type") in (
                    "off", "effect", "playlist", "music", "sysinfo", "text"):
                self._restore = r
            log("已载入上次的设置:", self._prefs_file())
        except Exception as e:
            log("载入设置失败:", e)

    def _save_prefs(self):
        data = {
            "bars": self._m_bars, "col_width": self._m_cw, "col_gap": self._m_cg,
            "gap_level": self._m_gap_level, "mode": self._m_mode,
            "show_title": self._np_show, "show_bars": self._m_show_bars,
            "np_units": self._np_units, "np_speed": self._np_speed,
            "np_bar_dim": self._np_bar_dim, "np_v_off": self._np_v_off,
            "music_style": self._music_style, "gain": self._music_gain,
            "peaks": self._m_peaks, "gradient": self._m_gradient,
            "gif_speed": self._gif_speed,
            "music_decay": self._music_decay,
            "music_full": self._music_full,
            "playlist": list(self._pl_ids), "playlist_loops": self._pl_loops,
            "playlist_params": dict(self._pl_params),
            "sysinfo": dict(self._sys_prefs),
            "restore": dict(self._restore),
        }
        try:
            with open(self._prefs_file(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log("保存设置失败:", e)

    def restore_last(self):
        """启动时恢复上次的灯效/模式；失败就保持关闭。"""
        r = dict(self._restore or {})
        t = r.get("type", "off")
        if t == "off":
            return
        try:
            if t == "effect":
                e = r.get("effect") or {}
                eid = e.get("id")
                if not eid:
                    raise RuntimeError("没有记录灯效 id")
                res = self.play_effect(
                    eid, float(e.get("brightness", 1.0)),
                    int(e.get("loops", 0)), e.get("mode"),
                    float(e.get("ox", 0.0)), float(e.get("oy", 0.0)),
                    float(e.get("zoom", 1.0)), float(e.get("rot_deg", 0.0)),
                    bool(e.get("mirror_x", False)), e.get("speed"))
                if not res.get("ok"):
                    raise RuntimeError(res.get("error") or "播放失败")
                log("已恢复上次灯效:", res.get("name") or eid)
            elif t == "playlist":
                if not self._pl_ids:
                    raise RuntimeError("播放列表为空")
                res = self.playlist_start(index=int(r.get("index", 0)))
                if not res.get("ok"):
                    raise RuntimeError(res.get("error") or "播放失败")
                log("已恢复播放列表")
            elif t == "music":
                res = self.set_music(True, float(r.get("gain", 1.0)),
                                     str(r.get("style", "bars")))
                if not res.get("ok"):
                    raise RuntimeError(res.get("error") or "音乐启动失败")
                log("已恢复音乐可视化")
            elif t == "sysinfo":
                self.set_sysinfo_saved()
                log("已恢复系统信息")
            elif t == "text":
                text = str(r.get("text") or "")
                if text:
                    self.set_text(text, size=r.get("size", 280),
                                  speed=r.get("speed", 90),
                                  scroll=bool(r.get("scroll", True)),
                                  brightness=float(r.get("brightness", 1.0)),
                                  v_offset=float(r.get("v_offset", 0.0)))
                    log("已恢复文字")
        except Exception as e:
            log("恢复上次灯效失败:", e)
            self._restore = {"type": "off"}
            self._save_prefs()

    # -- 基础 -------------------------------------------------------
    def connect(self):
        try:
            self.panel.open()
            log("设备已连接")
            return {"ok": True}
        except Exception as e:
            log("连接失败:", e)
            return {"ok": False, "error": str(e)}

    def disconnect(self):
        try:
            self.panel.clear()
        except Exception:
            pass
        self.panel.close()
        return {"ok": True}

    def state(self):
        return {
            "connected": self.panel.connected,
            "mode": self.mode,
            "brightness": self.panel.brightness,
            "brightness_name": BRIGHTNESS_NAMES[self.panel.brightness],
            "display_on": self.panel.display_on,
            "error": self.panel.error,
            "frame_version": self._frame_ver,
        }

    # -- 帧输出 -----------------------------------------------------
    def _set(self, frame):
        with self._lock:
            self.frame = frame
            self._frame_ver += 1
        self.panel.set_frame(frame)

    def preview_png(self):
        with self._lock:
            ver, frame = self._frame_ver, self.frame
        if ver != self._png_ver:
            self._png_cache = animelib.lid_preview_png(frame)
            self._png_ver = ver
        return self._png_cache

    # -- 模式：图片 -------------------------------------------------
    def set_image(self, data_b64, brightness=1.0, rotate=False):
        from PIL import Image
        self._stop_sensors()
        self._ensure_music_off()
        img = Image.open(io.BytesIO(base64.b64decode(data_b64)))
        deg = animelib.RIBBON_ANGLE_DEG if rotate else 0.0
        frame = animelib.image_to_leds(img, brightness=brightness, rotate_deg=deg)
        self.mode = "image"
        self._set(frame)
        self._restore = {"type": "off"}
        self._save_prefs()
        return {"ok": True}

    # -- 模式：GIF --------------------------------------------------
    def set_gif(self, data_b64, loops=0, brightness=1.0, rotate=False,
                fit="cover", space="band", ox=0.0, oy=0.0, zoom=1.0,
                rot_deg=0.0, mirror_x=False, speed=None,
                persist_restore=True):
        from PIL import Image, ImageSequence
        self._stop_sensors()
        self._ensure_music_off()
        img = Image.open(io.BytesIO(base64.b64decode(data_b64)))
        frames, durs = [], []
        for fr in ImageSequence.Iterator(img):
            rgba = fr.convert("RGBA")
            if rotate:
                rgba = rgba.rotate(-animelib.RIBBON_ANGLE_DEG, expand=True,
                                   resample=3, fillcolor=(0, 0, 0, 0))
            if space == "lid":
                frames.append(animelib.image_to_leds_matrix(
                    rgba, brightness=brightness, rot_deg=rot_deg,
                    mirror_x=mirror_x, mode="lid", ox=ox, oy=oy, zoom=zoom))
            elif space in ("fx", "matrix", "scaled"):
                frames.append(animelib.image_to_leds_matrix(
                    rgba, brightness=brightness, rot_deg=rot_deg,
                    mirror_x=mirror_x,
                    mode=("gif" if space == "matrix" else
                          ("scaled" if space == "scaled" else "lid")),
                    ox=ox, oy=oy, zoom=zoom))
            else:
                frames.append(animelib.image_to_leds(rgba, brightness=brightness,
                                                     fit=fit))
            # 部分灯效（如 520_NB）的 GIF 里每帧 delay 都是 0，是导出缺陷；
            # 直接按 0 播会变成 50fps 的"快放"，用 30ms 兜底（与多数灯效一致）
            dur = int(fr.info.get("duration") or 0)
            durs.append(dur if dur > 0 else 30)
        self._gif = list(zip(frames, durs))
        self._gif_idx = 0
        self._gif_next = 0
        self._gif_loops = int(loops)
        if speed is not None:
            self._gif_speed = max(0.1, min(5.0, float(speed)))
        self._gif_total = sum(durs) / 1000.0 / max(0.05, self._gif_speed)
        if space in ("fx", "matrix", "lid"):
            # 记住这次灯效的参数，方便 /api/effects/tune 实时重映射
            self._last_fx = {
                "data": data_b64, "brightness": brightness, "loops": loops,
                "space": space,
                "ox": ox, "oy": oy, "zoom": zoom, "rot_deg": rot_deg,
                "mirror_x": mirror_x,
            }
        self.mode = "gif"
        if persist_restore:
            self._restore = {"type": "off"}
            self._save_prefs()
        return {"ok": True, "frames": len(self._gif),
                "duration": round(self._gif_total, 2),
                "speed": self._gif_speed}

    # -- 播放倍速（不打断当前播放）-----------------------------------
    def set_speed(self, speed):
        """调整当前 GIF/灯效的播放倍速，保持播放位置不跳。"""
        s = max(0.1, min(5.0, float(speed)))
        # 已排到未来的下一帧时间点，按新旧倍速比例折算，避免卡顿或跳帧
        now = time.time()
        if self._gif_next > now and self._gif_speed > 0:
            remain = (self._gif_next - now) * (self._gif_speed / s)
            self._gif_next = now + remain
        self._gif_speed = s
        if self._last_fx is not None:
            self._last_fx["speed"] = s
        if self._last_effect is not None:
            self._last_effect["speed"] = s
            if self._restore.get("type") == "effect":
                self._restore["effect"] = dict(self._last_effect)
        self._save_prefs()
        return {"ok": True, "speed": s}

    # -- 播放列表（按顺序轮播灯效）-----------------------------------
    def playlist(self):
        m = getattr(Engine, "_effect_map", None) or {}
        if not m:
            # 服务刚启动、还没人调用过 /api/effects 时，_effect_map 是空的，
            # 这里补扫一次，否则列表里全是「(已移除)」
            items = self._scan_effects()
            Engine._effect_map = {i["id"]: i for i in items}
            m = Engine._effect_map
        items = []
        for eid in self._pl_ids:
            it = m.get(eid)
            items.append({"id": eid, "name": (it or {}).get("name", "(已移除)"),
                          "theme": (it or {}).get("theme", "")})
        cur = None
        if self._pl_active and 0 <= self._pl_index < len(self._pl_ids):
            cur = self._pl_ids[self._pl_index]
        return {"ok": True, "items": items, "active": self._pl_active,
                "index": self._pl_index, "current": cur,
                "loops": self._pl_loops}

    def playlist_set(self, ids=None, loops=None, brightness=None, speed=None):
        """设置播放列表内容与参数。ids 为空表示清空。"""
        if ids is not None:
            if not isinstance(ids, (list, tuple)):
                return {"ok": False, "error": "ids 需要是数组"}
            known = {i["id"] for i in self._scan_effects()}
            self._pl_ids = [str(x) for x in ids if str(x) in known]
        if loops is not None:
            self._pl_loops = max(1, min(20, int(loops)))
        if brightness is not None:
            self._pl_params["brightness"] = max(0.1, min(2.0, float(brightness)))
        if speed is not None:
            self._pl_params["speed"] = max(0.1, min(5.0, float(speed)))
        self._save_prefs()
        return self.playlist()

    def _playlist_params(self):
        p = self._pl_params
        return {"brightness": float(p.get("brightness", 1.0)),
                "speed": float(p.get("speed", self._gif_speed)),
                "mode": p.get("mode")}

    def playlist_start(self, ids=None, loops=None, brightness=None,
                       speed=None, index=0):
        """开始按顺序轮播；每个灯效播 loops 轮后切下一个。"""
        if ids is not None or loops is not None or brightness is not None \
                or speed is not None:
            r = self.playlist_set(ids, loops, brightness, speed)
            if not r.get("ok"):
                return r
        if not self._pl_ids:
            return {"ok": False, "error": "播放列表是空的"}
        self._pl_active = True
        self._pl_index = max(0, min(len(self._pl_ids) - 1, int(index)))
        self._pl_cycles = 0
        r = self._playlist_play_current()
        if r.get("ok"):
            self._restore = {"type": "playlist", "index": int(self._pl_index)}
            self._save_prefs()
        return r

    def _playlist_play_current(self, _depth=0):
        eid = self._pl_ids[self._pl_index]
        self._pl_cycles = 0
        p = self._playlist_params()
        r = self.play_effect(eid, brightness=p["brightness"], loops=0,
                             mode=p["mode"], speed=p["speed"],
                             playlist=True)
        if not r.get("ok"):
            # 单个灯效出问题就跳到下一个，避免整个列表卡死；
            # 全部灯效都失败时停止，防止无限递归
            log("播放列表：跳过", eid, r.get("error"))
            if _depth + 1 >= len(self._pl_ids):
                self._pl_active = False
                return {"ok": False, "error": "播放列表中的灯效都无法播放"}
            self._pl_index = (self._pl_index + 1) % len(self._pl_ids)
            return self._playlist_play_current(_depth + 1)
        r["playlist"] = self.playlist()
        return r

    def _on_cycle_end(self):
        """一轮动画播完时调用（由渲染循环触发）。只做计数，切换在主循环里完成。"""
        if not self._pl_active or self.mode != "gif":
            return
        self._pl_cycles += 1
        if self._pl_cycles >= max(1, self._pl_loops):
            self._pl_pending = True

    def _playlist_advance(self):
        if not self._pl_ids:
            self._pl_active = False
            return {"ok": False, "error": "播放列表是空的"}
        self._pl_index = (self._pl_index + 1) % len(self._pl_ids)
        r = self._playlist_play_current()
        if r.get("ok") and self._pl_active:
            self._restore = {"type": "playlist", "index": int(self._pl_index)}
            self._save_prefs()
        return r

    def playlist_next(self):
        if not self._pl_ids:
            return {"ok": False, "error": "播放列表是空的"}
        return self._playlist_advance()

    def playlist_stop(self):
        self._pl_active = False
        self._pl_cycles = 0
        self._restore = {"type": "off"}
        self._save_prefs()
        return {"ok": True, "active": False}

    # -- 一键关闭 ---------------------------------------------------
    def clear_for_exit(self):
        """收到关闭请求时先同步熄灯，再回响应。"""
        self.mode = "off"
        self.panel.clear()

    def shutdown_all(self):
        """停止音乐、熄灭灯板、恢复被暂停的华硕服务。"""
        self._stop_sensors()
        try:
            # 先熄灯，音频停止慢也不影响灯板
            self.mode = "off"
            self.panel.clear()
        except Exception:
            pass
        try:
            self.stop_music()
        except Exception:
            pass
        try:
            self.panel.close()
        except Exception:
            pass
        try:
            resume_asus_lighting()
        except Exception:
            pass
        log("已关闭灯控")

    # -- 奥创灯效库 ---------------------------------------------------
    # 两个来源：
    #   1) ACStore\UserContent   奥创商店下载的灯效（每目录一个 GIF + ini 元数据）
    #   2) ROG Live Service      奥创自带的内置灯效（每目录多个 GIF，无 ini）
    EFFECT_ROOTS = [
        r"C:\ProgramData\ASUS\ACStore\UserContent",
        r"C:\ProgramData\ASUS\ROG Live Service\MatrixContent\G635\G635",
        # 注：MatrixSyncContent 里是主板/整机/键盘/耳机（MB/AIO/KB/HS）
        # 联动灯效，没有笔记本矩阵版本，故不扫描
    ]

    # 内置库里这些目录是系统状态提示（电量、通知、开关机动画等），
    # 不适合当灯效播放，扫描时跳过
    EFFECT_SKIP_DIRS = {"system", "ECAnimations"}

    def _scan_effects(self):
        """扫描奥创矩阵灯效（商店下载 + 内置）。

        两种目录结构都要兼容：
          * ACStore：一个目录一个灯效（GIF + 同名 ini + _thumbnail.gif）
          * 内置：一个目录多个 GIF（如 ROG Gallery 下 4 个），无 ini
        theme 在内置库中取自上级目录名（ROG Gallery / Trend / ECAnimations …）。
        """
        import hashlib
        import os
        items = []
        for root in Engine.EFFECT_ROOTS:
            if not os.path.isdir(root):
                continue
            builtin = "ROG Live Service" in root
            for dirpath, dirs, files in os.walk(root):
                if builtin:
                    dirs[:] = [d for d in dirs if d not in Engine.EFFECT_SKIP_DIRS]
                gifs = sorted(f for f in files if f.lower().endswith(".gif")
                              and "thumbnail" not in f.lower())
                if not gifs:
                    continue
                ini = {}
                for f in sorted(files):
                    if f.lower().endswith(".ini"):
                        try:
                            txt = open(os.path.join(dirpath, f), encoding="utf-8",
                                       errors="ignore").read()
                        except Exception:
                            txt = ""
                        for line in txt.splitlines():
                            line = line.strip()
                            if line.startswith("theme="):
                                ini["theme"] = line[6:]
                            elif line.startswith("Tag="):
                                ini["tag"] = line[4:]
                            elif line.startswith("OnlySupportedModel="):
                                ini["models"] = line[19:]
                        break

                thumbs = {}
                for f in files:
                    if f.lower().endswith(".gif") and "thumbnail" in f.lower():
                        thumbs[f.lower()] = os.path.join(dirpath, f)

                for g in gifs:
                    gif_path = os.path.join(dirpath, g)
                    name = os.path.splitext(g)[0]
                    if builtin:
                        # 内置库：名称去掉设备后缀（_NB / _strix_NB / _2_strix_NB）
                        label = _clean_builtin_name(name)
                        theme = _builtin_theme(dirpath, root)
                    else:
                        label = name
                        theme = ini.get("theme", "")
                    thumb = thumbs.get((name + "_thumbnail.gif").lower())
                    eid = hashlib.md5(gif_path.lower().encode("utf-8")).hexdigest()[:12]
                    items.append({
                        "id": eid, "name": label, "theme": theme,
                        "tag": ini.get("tag", ""), "models": ini.get("models", ""),
                        "dir": dirpath, "gif": gif_path, "thumb": thumb,
                        "builtin": builtin,
                        "kb": round(os.path.getsize(gif_path) / 1024, 1),
                    })
        items.sort(key=lambda x: (x["theme"] or "zz", x["name"]))
        return items

    def effects(self):
        items = self._scan_effects()
        Engine._effect_map = {i["id"]: i for i in items}
        for i in items:
            i.pop("dir", None)
        return {"ok": True, "count": len(items), "items": items}

    def effect_bytes(self, eid, kind="gif"):
        m = getattr(Engine, "_effect_map", {}) or {}
        it = m.get(eid) or next((x for x in self._scan_effects() if x["id"] == eid), None)
        if not it:
            return None, None
        path = it["thumb"] if kind == "thumb" else it["gif"]
        if kind == "thumb" and (not path or not os.path.exists(path)):
            # 内置灯效大多没有 _thumbnail.gif，退回用原 GIF 当缩略图
            path = it["gif"]
        if not path or not os.path.exists(path):
            return None, None
        with open(path, "rb") as f:
            return f.read(), ("image/gif" if path.lower().endswith(".gif") else "image/png")

    @staticmethod
    def _pick_space(data):
        """按 GIF 画布尺寸选映射：68x49 用矩阵约定，其余按整块画布缩放。"""
        try:
            import struct
            # GIF 逻辑屏幕尺寸在文件头第 6..10 字节（小端）
            if data[:6] in (b"GIF89a", b"GIF87a"):
                w, h = struct.unpack("<HH", data[6:10])
                if (w, h) == (animelib.MATRIX_GIF_W, animelib.MATRIX_GIF_H):
                    return "matrix"
                return "scaled"
        except Exception:
            pass
        return "scaled"

    def play_effect(self, eid, brightness=1.0, loops=0, mode=None,
                    ox=0.0, oy=0.0, zoom=1.0, rot_deg=0.0, mirror_x=False,
                    speed=None, playlist=False):
        data, _ = self.effect_bytes(eid)
        if not data:
            return {"ok": False, "error": "灯效文件不存在"}
        if mode in (None, "", "auto"):
            mode = self._pick_space(data)
        if not playlist:
            # 手动播放才记录为"上次灯效"，避免轮播时覆盖 /api/effects/tune 的目标
            self._last_effect = {"id": eid, "brightness": brightness,
                                 "loops": loops, "mode": mode, "ox": ox,
                                 "oy": oy, "zoom": zoom, "rot_deg": rot_deg,
                                 "mirror_x": mirror_x, "speed": speed}
        if mode == "lid":
            r = self.set_gif(base64.b64encode(data).decode(), loops=loops,
                             brightness=brightness, space="lid",
                             ox=ox, oy=oy, zoom=zoom,
                             rot_deg=rot_deg, mirror_x=mirror_x, speed=speed,
                             persist_restore=False)
        elif mode == "stretch":
            r = self.set_gif(base64.b64encode(data).decode(), loops=loops,
                             brightness=brightness, space="fx",
                             ox=ox, oy=oy, zoom=zoom, rot_deg=rot_deg,
                             mirror_x=mirror_x, speed=speed,
                             persist_restore=False)
        elif mode == "matrix":
            # 奥创灯效 GIF：按验证过的视觉坐标 1px=1格 映射
            r = self.set_gif(base64.b64encode(data).decode(), loops=loops,
                             brightness=brightness, space="matrix",
                             ox=ox, oy=oy, zoom=zoom,
                             rot_deg=rot_deg, mirror_x=mirror_x, speed=speed,
                             persist_restore=False)
        elif mode == "scaled":
            # 内置灯效（非 68x49 画布）：整块缩放铺进面板可见区
            r = self.set_gif(base64.b64encode(data).decode(), loops=loops,
                             brightness=brightness, space="scaled",
                             ox=ox, oy=oy, zoom=zoom,
                             rot_deg=rot_deg, mirror_x=mirror_x, speed=speed,
                             persist_restore=False)
        else:
            r = self.set_gif(base64.b64encode(data).decode(), loops=loops,
                             brightness=brightness, fit=mode,
                             persist_restore=False)
        if r.get("ok") and not playlist:
            self._restore = {"type": "effect",
                             "effect": dict(self._last_effect or {})}
            self._save_prefs()
        r["name"] = next((x["name"] for x in self._scan_effects() if x["id"] == eid), "")
        return r

    # -- 模式：文字 -------------------------------------------------
    def set_text(self, text, size=280, speed=90, rotate=True,
                 scroll=True, brightness=1.0, stretch=1.0, rotate_deg=0.0,
                 v_offset=0.0):
        # 字号（界面 140~320）映射成「字高（格）」，灯带高度约 14.5 格
        font_units = max(6, min(14, int(round(float(size) / 22.0))))
        self._stop_sensors()
        self._ensure_music_off()
        self._text = text
        self.cfg = {"font_units": font_units, "speed": float(speed),
                    "scroll": bool(scroll), "bright": float(brightness),
                    "v_offset": float(v_offset)}
        self._scroll = 0.0
        self.mode = "text"
        self._tick_text()
        self._restore = {"type": "text", "text": text, "size": size,
                         "speed": speed, "scroll": bool(scroll),
                         "brightness": brightness, "v_offset": v_offset}
        self._save_prefs()
        return {"ok": True}

    def _tick_text(self, dt=0.0):
        """在视觉坐标系里水平渲染文字（g-helper 方案），并按需滚动。"""
        text = getattr(self, "_text", "")
        if not text:
            return
        units = self.cfg.get("font_units", 13)
        # 文字宽度估算（用于滚动循环）
        approx_w = int(len(text) * units * 0.62) + 4
        if self.cfg.get("scroll"):
            self._scroll += self.cfg.get("speed", 90) * 0.30 * max(dt, 0.0)
            start_u = animelib.MAX_U + 4.0                 # 从右侧外进入
            end_u = animelib.MIN_U - approx_w - 4.0        # 完全离开左侧
            span = start_u - end_u
            if self._scroll > span:
                self._scroll = 0.0
            u_pos = start_u - self._scroll
        else:
            u_pos = None
        frame = animelib.render_text_visual(
            text, font_units=units, u_pos=u_pos,
            v_offset=self.cfg.get("v_offset", 0.0),
            brightness=self.cfg.get("bright", 1.0))
        self._set(frame)

    # -- 模式：系统信息 ---------------------------------------------
    def sysinfo_prefs(self):
        return dict(self._sys_prefs)

    def set_sysinfo_font_v(self, font_v):
        try:
            fv = max(-3.0, min(3.0, float(font_v)))
        except Exception:
            fv = 1.0
        self._sys_prefs["font_v"] = fv
        self._save_prefs()
        if self.mode == "sysinfo":
            self.cfg["v_offset"] = fv
            self._tick_text(0)
        return {"ok": True, "font_v": fv}

    def set_sysinfo_auto_game(self, enabled):
        ag = bool(enabled)
        self._sys_prefs["auto_game"] = ag
        self._save_prefs()
        if self.mode == "sysinfo":
            self._rebuild_sys()
        return {"ok": True, "auto_game": ag}

    def set_sysinfo_saved(self):
        p = self._sys_prefs
        return self.set_sysinfo(
            app_prefix=p.get("app_prefix", "正在使用"),
            order=list(p.get("order") or SYS_KEYS),
            enabled=dict(p.get("enabled") or {}),
            display=p.get("display", "scroll"),
            rotate_sec=p.get("rotate_sec", 4),
            durations=dict(p.get("durations") or {}),
            font_size=p.get("font_size", 12),
            font_v=p.get("font_v", 1.0),
            auto_game=p.get("auto_game", True),
            scroll_speed=p.get("scroll_speed", 90),
            custom_cpu_name=p.get("custom_cpu_name", ""),
            custom_gpu_name=p.get("custom_gpu_name", ""))

    def set_sysinfo(self, show_battery=True, show_cpu=True, speed=90,
                    show_app=True, show_time=True, app_prefix="正在使用",
                    order=None, enabled=None, display=None, rotate_sec=None,
                    durations=None, font_size=None, font_v=None,
                    auto_game=None, scroll_speed=None,
                    custom_cpu_name=None, custom_gpu_name=None):
        try:
            import sensors
            sensors.get()
        except Exception:
            pass
        self._ensure_music_off()
        cur = self._sys_prefs
        if enabled is None:
            # 兼容托盘旧调用：只改这四项，其他指标保持原样
            en = dict(cur.get("enabled") or {k: True for k in SYS_KEYS})
            en["time"] = bool(show_time)
            en["battery"] = bool(show_battery)
            en["cpu_usage"] = bool(show_cpu)
            en["app"] = bool(show_app)
        else:
            en = {}
            old = cur.get("enabled") or {}
            for k in SYS_KEYS:
                if isinstance(enabled, dict) and k in enabled:
                    en[k] = bool(enabled[k])
                else:
                    en[k] = bool(old.get(k, True))
        valid = []
        src = order if isinstance(order, list) else (cur.get("order") or SYS_KEYS)
        for k in src:
            k = str(k)
            if k in SYS_KEYS and k not in valid:
                valid.append(k)
        for k in SYS_KEYS:
            if k not in valid:
                valid.append(k)
        disp = display if display in ("scroll", "rotate") \
            else cur.get("display", "scroll")
        try:
            rs = float(rotate_sec if rotate_sec is not None
                       else cur.get("rotate_sec", 4))
            rs = max(1.0, min(30.0, rs))
        except Exception:
            rs = 4.0
        durs = dict(cur.get("durations") or {})
        if isinstance(durations, dict):
            for k in SYS_KEYS:
                if k in durations:
                    try:
                        durs[k] = max(1.0, min(30.0, float(durations[k])))
                    except Exception:
                        pass
        for k in SYS_KEYS:
            if k not in durs:
                durs[k] = rs
        try:
            fs = int(font_size if font_size is not None
                     else cur.get("font_size", 12))
            fs = max(6, min(14, fs))
        except Exception:
            fs = 12
        try:
            fv = float(font_v if font_v is not None
                       else cur.get("font_v", 1.0))
            fv = max(-3.0, min(3.0, fv))
        except Exception:
            fv = 1.0
        ag = bool(auto_game if auto_game is not None
                  else cur.get("auto_game", True))
        try:
            if scroll_speed is not None:
                ss = float(scroll_speed)
            elif speed is not None:
                ss = float(speed)
            else:
                ss = float(cur.get("scroll_speed", 90))
            ss = max(30.0, min(300.0, ss))
        except Exception:
            ss = 90.0
        prefix = str(app_prefix if app_prefix is not None
                     else cur.get("app_prefix", "")).strip()
        custom_cpu = str(custom_cpu_name if custom_cpu_name is not None
                         else cur.get("custom_cpu_name", "")).strip()
        custom_gpu = str(custom_gpu_name if custom_gpu_name is not None
                         else cur.get("custom_gpu_name", "")).strip()
        self._sys_prefs = {
            "enabled": en, "order": valid, "display": disp,
            "rotate_sec": rs, "durations": durs,
            "font_size": fs, "font_v": fv, "auto_game": ag,
            "scroll_speed": ss,
            "custom_cpu_name": custom_cpu, "custom_gpu_name": custom_gpu,
            "app_prefix": prefix,
        }
        self.cfg = {"font_units": fs, "speed": ss,
                    "scroll": disp == "scroll",
                    "bright": 1.0, "v_offset": fv,
                    "app_prefix": prefix}
        self._restore = {"type": "sysinfo"}
        self._save_prefs()
        self.mode = "sysinfo"
        self._sys_last = 0.0
        self._sys_page = 0
        self._sys_page_t = time.time()
        self._sys_pages = []
        self._sys_page_keys = []
        self._scroll = 0.0
        self._rebuild_sys()
        return {"ok": True}

    def _sys_duration(self):
        keys = getattr(self, "_sys_page_keys", [])
        if not keys:
            return 4.0
        if self._sys_page >= len(keys):
            self._sys_page = 0
        key = keys[self._sys_page]
        durs = self._sys_prefs.get("durations") or {}
        try:
            return max(1.0, min(30.0, float(durs.get(key, 4))))
        except Exception:
            return 4.0

    def _apply_sys_page(self, reset_scroll=False):
        if not self._sys_pages:
            self._text = "系统信息"
            self.cfg["scroll"] = True
            self._tick_text(0)
            return
        if self._sys_page >= len(self._sys_pages):
            self._sys_page = 0
        self._text = self._sys_pages[self._sys_page]
        self.cfg["scroll"] = True
        self.cfg["speed"] = float(self._sys_prefs.get("scroll_speed", 90))
        if reset_scroll:
            self._scroll = 0.0
        self._tick_text(0)

    def _rebuild_sys(self):
        try:
            import sensors
            s = sensors.get()
            cpu_short = sensors.cpu_short_name()
            gpu_short = sensors.gpu_short_name()
        except Exception:
            s, cpu_short, gpu_short = {}, "CPU", "GPU"

        rotate = self._sys_prefs.get("display") == "rotate"

        def num(v, suffix="", nd=0):
            if isinstance(v, (int, float)):
                return f"{v:.{nd}f}{suffix}"
            return "--"

        cpu_full = s.get("cpu_name") or cpu_short or "CPU"
        gpu_full = s.get("gpu_name") or gpu_short or "GPU"
        cpu_custom = (self._sys_prefs.get("custom_cpu_name") or "").strip()
        gpu_custom = (self._sys_prefs.get("custom_gpu_name") or "").strip()
        cpu_label = cpu_custom or cpu_full
        gpu_label = gpu_custom or gpu_full
        mu = s.get("gpu_mem_used")
        mt = s.get("gpu_mem_total")
        vram_pct = (mu / mt * 100.0) if mu is not None and mt else None
        b = battery_percent()
        fg = foreground_app()
        app_name = app_display_name(fg)
        prefix = (self._sys_prefs.get("app_prefix") or "").strip()
        auto_game = bool(self._sys_prefs.get("auto_game", True))
        if app_name:
            if auto_game and is_game_app(fg):
                app_text = f"正在玩 - {app_name}"
            elif prefix:
                app_text = f"{prefix} - {app_name}"
            else:
                app_text = f"应用 - {app_name}"
        else:
            app_text = "应用 - --"

        ru, rt = s.get("ram_used"), s.get("ram_total")
        ram_pct = s.get("ram_percent")
        ram_used_g = (ru / (1024 ** 3)) if ru else 0.0
        ram_total_g = (rt / (1024 ** 3)) if rt else 0.0
        ram_pct_v = ram_pct if isinstance(ram_pct, (int, float)) else 0
        mu_g = (mu / (1024 ** 3)) if mu is not None else 0.0
        mt_g = (mt / (1024 ** 3)) if mt else 0.0
        vram_pct_v = vram_pct if isinstance(vram_pct, (int, float)) else 0
        ram_text = (f"ram - {ram_pct_v:.0f}% "
                    f"{ram_used_g:.0f}/{ram_total_g:.0f}G")
        vram_text = (f"vram - {vram_pct_v:.0f}% "
                     f"{mu_g:.0f}/{mt_g:.0f}G")

        texts = {
            "cpu_name": f"CPU - {cpu_label}",
            "cpu_usage": f"CPU - {num(s.get('cpu_usage'), '%')}",
            "cpu_temp": f"CPU - {num(s.get('cpu_temp'), '°C')}",
            "cpu_power": f"CPU - {num(s.get('cpu_power'), 'W', 1)}",
            "gpu_name": f"GPU - {gpu_label}",
            "gpu_usage": f"GPU - {num(s.get('gpu_usage'), '%')}",
            "gpu_temp": f"GPU - {num(s.get('gpu_temp'), '°C')}",
            "gpu_power": f"GPU - {num(s.get('gpu_power'), 'W', 1)}",
            "ram": ram_text,
            "vram": vram_text,
            "time": f"时间 - {time.strftime('%H:%M')}",
            "battery": f"电量 - {b}%" if b is not None else "电量 - --",
            "app": app_text,
        }
        order = self._sys_prefs.get("order") or SYS_KEYS
        enabled = self._sys_prefs.get("enabled") or {}
        keys = [k for k in order if k in texts and enabled.get(k, True)]
        parts = [texts[k] for k in keys]
        if not parts:
            parts = ["系统信息"]
            keys = ["info"]
        self._sys_pages = parts
        self._sys_page_keys = keys

        if rotate:
            if self._sys_page >= len(parts):
                self._sys_page = 0
            self._apply_sys_page(False)
        else:
            self._text = "   ".join(parts)
            self.cfg["scroll"] = True
            self._tick_text(0)

    # -- 模式：原始帧（调试用） ---------------------------------------
    def set_raw(self, data_b64):
        self._stop_sensors()
        raw = base64.b64decode(data_b64)
        if len(raw) != animelib.LED_COUNT:
            raise ValueError(f"需要 {animelib.LED_COUNT} 字节，收到 {len(raw)}")
        self.mode = "raw"
        self._set(raw)
        return {"ok": True}

    # -- 模式：音乐可视化 ---------------------------------------------
    def set_music(self, on=True, gain=1.0, style="bars"):
        self._stop_sensors()
        if not on:
            self.stop_music()
            self.mode = "off"
            self._set(bytes(animelib.LED_COUNT))
            self._restore = {"type": "off"}
            self._save_prefs()
            return {"ok": True}
        try:
            import audio as audio_mod
        except Exception as e:
            return {"ok": False, "error": f"音频模块不可用：{e}"}
        self._ensure_music_off()
        worker = audio_mod.AudioWorker(bands=24, gain=float(gain))
        try:
            worker.analyzer.decay = float(self._music_decay)
            worker.analyzer.rebuild(self._music_full)
        except Exception:
            pass
        worker.start()
        time.sleep(0.5)                       # 等回环采集启动
        if worker.error:
            err = worker.error
            worker.stop()
            return {"ok": False, "error": f"音频采集失败：{err}"}
        self._music = worker
        self._music_style = (style if style in
                             ("bars", "vbar", "pbar11", "waterfall", "gh",
                              "strobing", "raindrop", "wave", "spectrum1")
                             else "bars")
        self._music_sub = "bars"
        self._sub_t0 = time.time()
        self._np_scroll = 0.0
        # 启动歌名/歌手读取（SMTC）
        try:
            import media as media_mod
            if self._np is None:
                self._np = media_mod.NowPlaying(interval=4.0).start()
        except Exception as e:
            log("媒体信息不可用:", e)
        import collections
        self._history = collections.deque(maxlen=90) if self._music_style == "waterfall" else None
        self.mode = "music"
        self._restore = {"type": "music", "gain": float(gain),
                         "style": self._music_style}
        self._save_prefs()
        return {"ok": True, "bands": worker.bands, "style": self._music_style}

    def music_set(self, bars=None, col_width=None, col_gap=None, gap_level=None,
                  mode=None, show_title=None, bars_time=None, np_time=None,
                  np_frac=None, np_units=None, np_speed=None, np_bar_dim=None,
                  np_v_off=None, show_bars=None, gain=None, peaks=None,
                  gradient=None, decay=None, full=None, style=None):
        """调整柱状频谱参数与歌名显示。"""
        if mode in ("even", "compact"):
            self._m_mode = mode
        if bars is not None:
            self._m_bars = max(3, min(17, int(bars)))
        if col_width is not None:
            self._m_cw = max(1, min(3, int(col_width)))
        if col_gap is not None:
            self._m_cg = max(0, min(3, int(col_gap)))
        if gap_level is not None:
            self._m_gap_level = max(0.0, min(1.0, float(gap_level)))
        if show_title is not None:
            self._np_show = bool(show_title)
        if show_bars is not None:
            self._m_show_bars = bool(show_bars)
        if np_frac is not None:
            self._np_frac = max(0.2, min(0.7, float(np_frac)))
        if np_units is not None:
            self._np_units = max(3, min(24, int(np_units)))
        if np_speed is not None:
            self._np_speed = max(4.0, min(60.0, float(np_speed)))
        if np_bar_dim is not None:
            self._np_bar_dim = max(0.1, min(1.0, float(np_bar_dim)))
        if np_v_off is not None:
            self._np_v_off = max(-7.0, min(7.0, float(np_v_off)))
        if gain is not None:
            g = max(0.1, min(4.0, float(gain)))
            self._music_gain = g
            if self._music:
                try:
                    self._music.analyzer.set_gain(g)
                except Exception:
                    pass
        if peaks is not None:
            self._m_peaks = bool(peaks)
        if gradient is not None:
            self._m_gradient = bool(gradient)
        if style is not None and style in ("bars", "vbar", "pbar11",
                                           "waterfall", "gh", "strobing",
                                           "raindrop", "wave", "spectrum1"):
            self._music_style = style
        if decay is not None:
            self._music_decay = max(0.5, min(0.99, float(decay)))
        if full is not None:
            self._music_full = bool(full)
        if self._music is not None:
            try:
                self._music.analyzer.set_gain(self._music_gain)
                self._music.analyzer.set_decay(self._music_decay)
                self._music.analyzer.rebuild(self._music_full)
            except Exception:
                pass
        self._save_prefs()
        return {"ok": True, "bars": self._m_bars, "mode": self._m_mode,
                "col_width": self._m_cw, "col_gap": self._m_cg,
                "gap_level": self._m_gap_level, "show_title": self._np_show,
                "np_frac": self._np_frac, "np_units": self._np_units,
                "np_speed": self._np_speed, "np_bar_dim": self._np_bar_dim,
                "np_v_off": self._np_v_off, "show_bars": self._m_show_bars,
                "gain": self._music_gain, "peaks": self._m_peaks,
                "gradient": self._m_gradient, "style": self._music_style,
                "decay": self._music_decay, "full": self._music_full}

    def stop_music(self):
        if self._music:
            try:
                self._music.stop()
            except Exception:
                pass
            self._music = None
        if self._np:
            try:
                self._np.stop()
            except Exception:
                pass
            self._np = None

    def _ensure_music_off(self):
        self.stop_music()

    def _stop_sensors(self):
        try:
            import sensors
            sensors.stop()
        except Exception:
            pass

    def music_state(self):
        if not self._music:
            return {"on": False, "error": None}
        lv, _ = self._music.levels()
        return {"on": True, "error": self._music.error,
                "levels": [round(float(x), 2) for x in lv]}

    # -- 模式控制 ---------------------------------------------------
    def off(self):
        self._stop_sensors()
        self.stop_music()
        self.mode = "off"
        self._set(bytes(animelib.LED_COUNT))
        self._restore = {"type": "off"}
        self._save_prefs()
        return {"ok": True}

    def _music_bars_frame(self, lv, pk, max_height=1.0, bscale=1.0):
        """按当前样式渲染音频柱（max_height 给文字留位，bscale 整体压暗）。"""
        style = self._music_style
        bright = self.cfg.get("bright", 1.0) * float(bscale)
        peaks = pk if self._m_peaks else None
        if style == "spectrum1":
            # 奥创 AniMe Vision「频谱 1」：细竖柱 + 柱身分段 + 柱顶渐亮
            return animelib.render_spectrum1(lv, peaks, bars=self._m_bars,
                                             brightness=bright,
                                             max_height=max_height)
        if style == "strobing":
            # 奥创 Music_Effect_Strobing：整板随节拍频闪
            beat = 0.0
            if self._music is not None:
                try:
                    beat = self._music.beat()[0]
                except Exception:
                    beat = 0.0
            return animelib.render_beat_flash(lv, beat, brightness=bright)
        if style == "raindrop":
            # 奥创 Music_Effect_Raindrop：频段能量决定雨滴落点
            if self._drops is None:
                self._drops = {}
            return animelib.render_raindrop(lv, drops=self._drops,
                                            brightness=bright, dt=self._dt)
        if style == "wave":
            # 奥创 Music_Effect_Wave：频段电平画成连续波形
            self._wave_phase = (getattr(self, "_wave_phase", 0.0)
                                + 4.0 * max(self._dt, 1 / 60.0))
            return animelib.render_wave(lv, brightness=bright,
                                        phase=self._wave_phase)
        if style == "waterfall":
            if self._history is None:
                import collections
                self._history = collections.deque(maxlen=90)
            self._history.append(lv.copy())
            return animelib.render_spectrogram(list(self._history),
                                               brightness=bright)
        if style == "gh":
            return animelib.render_bars_gh(lv, brightness=bright)
        if style == "vbar":
            return animelib.render_bars(lv, pk, bars=self._m_bars, mirror=False,
                                        segmented=False, gap=0.15,
                                        brightness=bright)
        if style == "pbar11":
            return animelib.render_bars_planar(lv, peaks, bars=11, col_width=2,
                                               col_gap=1, max_height=max_height,
                                               brightness=bright)
        if self._m_mode == "even":
            return animelib.render_bars_planar(
                lv, peaks, bars=self._m_bars, col_width=self._m_cw,
                col_gap=self._m_cg, gap_level=float(self._m_gap_level),
                max_height=max_height, brightness=bright,
                gradient=self._m_gradient)
        # 紧凑模式：12 条柱各占 1 列，柱间 2 列缝隙，正好铺满 34 列
        return animelib.render_bars_planar(
            lv, peaks, bars=self._m_bars, distribute=True,
            col_gap=2, gap_level=float(self._m_gap_level), edge_level=0.5,
            max_height=max_height, brightness=bright,
            gradient=self._m_gradient)
    # -- 主循环 -----------------------------------------------------
    def _loop(self):
        last = time.time()
        while not self._stop:
            now = time.time()
            dt = now - last
            last = now
            try:
                if self.mode == "gif" and self._gif:
                    if self._pl_pending:
                        self._pl_pending = False
                        self._playlist_advance()
                    elif now >= self._gif_next:
                        frame, d = self._gif[self._gif_idx]
                        self._gif_idx += 1
                        if self._gif_idx >= len(self._gif):
                            self._gif_idx = 0
                            if self._gif_loops > 0:
                                self._gif_loops -= 1
                            self._on_cycle_end()
                        self._gif_next = now + (d / 1000.0) / max(0.05, self._gif_speed)
                        self._set(frame)
                elif self.mode == "text":
                    self._tick_text(dt)
                elif self.mode == "sysinfo":
                    self._tick_text(dt)
                    if (self._sys_prefs.get("display") == "rotate"
                            and self._sys_pages
                            and now - self._sys_page_t >= self._sys_duration()):
                        self._sys_page_t = now
                        self._sys_page = ((self._sys_page + 1)
                                          % len(self._sys_pages))
                        self._apply_sys_page(True)
                    if now - self._sys_last >= 2.0:
                        self._sys_last = now
                        self._rebuild_sys()
                elif self.mode == "music" and self._music:
                    self._dt = dt
                    lv, pk = self._music.levels()
                    np_text = self._np.text() if self._np else ""
                    want_title = bool(self._np_show and np_text)
                    want_bars = bool(self._m_show_bars)

                    if want_title:
                        # 歌名在中间滚动
                        self._np_scroll += self._np_speed * dt
                        tw = len(np_text) * self._np_units * 0.62 + 40
                        if self._np_scroll > tw + animelib.PANEL_UNITS_W:
                            self._np_scroll = 0.0
                        txt = animelib.render_text_visual(
                            np_text, font_units=self._np_units,
                            u_pos=animelib.MAX_U + 4.0 - self._np_scroll,
                            v_center=((animelib.MIN_V + animelib.MAX_V) / 2.0
                                      + self._np_v_off),
                            brightness=self.cfg.get("bright", 1.0))
                    else:
                        txt = None

                    if want_bars:
                        # 有歌名时柱子压暗，避免抢文字
                        bars = self._music_bars_frame(
                            lv, pk, bscale=(self._np_bar_dim if want_title else 1.0))
                    else:
                        bars = None

                    if bars is not None and txt is not None:
                        self._set(bytes(max(a, b) for a, b in zip(bars, txt)))
                    elif bars is not None:
                        self._set(bars)
                    elif txt is not None:
                        self._set(txt)
                    else:
                        # 两个都关：保持黑屏
                        self._set(bytes(animelib.LED_COUNT))
            except Exception as e:
                log("渲染异常:", e)
            time.sleep(0.03)


# ================================================================ HTTP

class Handler(BaseHTTPRequestHandler):
    engine = None
    server_version = "AniMeVision/1.0"

    def log_message(self, *a):
        pass

    # -- 工具 -------------------------------------------------------
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        # 先完成序列化，保证任何异常都发生在发送响应头之前
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        elif body is None:
            body = b""
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _json_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    # -- GET --------------------------------------------------------
    def do_GET(self):
        u = urlparse(self.path)
        p = u.path
        e = self.engine
        if p in ("/", "/index.html"):
            fp = os.path.join(ROOT, "webui.html")
            with open(fp, "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        elif p == "/api/state":
            self._send(200, e.state())
        elif p == "/api/sysinfo":
            self._send(200, e.sysinfo_prefs())
        elif p == "/api/geometry":
            g = animelib.lid_geometry()
            g["count"] = animelib.LED_COUNT
            self._send(200, g)
        elif p == "/api/effects":
            self._send(200, e.effects())
        elif p == "/api/playlist":
            self._send(200, e.playlist())
        elif p.startswith("/api/effects/thumb/") or p.startswith("/api/effects/gif/"):
            kind = "thumb" if "/thumb/" in p else "gif"
            eid = p.rsplit("/", 1)[-1]
            data, mime = e.effect_bytes(eid, kind)
            if not data:
                self._send(404, {"error": "not found"})
            else:
                self._send(200, data, mime)
        elif p == "/rog_eye.png":
            try:
                with open(animelib.ROG_EYE_PATH, "rb") as f:
                    self._send(200, f.read(), "image/png")
            except Exception:
                self._send(404, {"error": "no rog_eye.png"})
        elif p == "/api/live":
            # 轻量实时帧：只发 810 字节 + 版本号，供前端 Canvas 绘制
            with e._lock:
                ver, frame = e._frame_ver, e.frame
            self._send(200, {"v": ver, "f": base64.b64encode(frame).decode()})
        elif p == "/api/preview.png":
            self._send(200, e.preview_png(), "image/png")
        else:
            self._send(404, {"error": "not found"})

    # -- 一键关闭 ---------------------------------------------------
    def _do_shutdown(self, e):
        """先同步熄灯并回响应，再清理并退出进程。"""
        try:
            e.clear_for_exit()
        except Exception:
            pass
        self._send(200, {"ok": True, "msg": "灯控程序已关闭"})
        server = getattr(Handler, "server", None)

        def _bye():
            import os as _os
            import time as _t
            _t.sleep(0.5)
            try:
                e.shutdown_all()
            except Exception:
                pass
            try:
                if server is not None:
                    server.shutdown()
            except Exception:
                pass
            _os._exit(0)

        threading.Thread(target=_bye, daemon=True).start()

    # -- POST -------------------------------------------------------
    def do_POST(self):
        u = urlparse(self.path)
        p = u.path
        e = self.engine
        b = self._json_body()
        try:
            if p == "/api/connect":
                self._send(200, e.connect())
            elif p == "/api/disconnect":
                self._send(200, e.disconnect())
            elif p == "/api/brightness":
                e.panel.set_brightness(int(b.get("level", 2)))
                self._send(200, e.state())
            elif p == "/api/power":
                e.panel.enable_display(bool(b.get("on", True)))
                self._send(200, e.state())
            elif p == "/api/off":
                self._send(200, e.off())
            elif p == "/api/shutdown":
                self._do_shutdown(e)
            elif p == "/api/image":
                self._send(200, e.set_image(
                    b["data"], float(b.get("brightness", 1.0)),
                    bool(b.get("rotate", False))))
            elif p == "/api/effects/play":
                self._send(200, e.play_effect(
                    b.get("id"), float(b.get("brightness", 1.0)),
                    int(b.get("loops", 0)), b.get("mode") or None,
                    float(b.get("ox", 0.0)), float(b.get("oy", 0.0)),
                    float(b.get("zoom", 1.0)), float(b.get("rot_deg", 0.0)),
                    bool(b.get("mirror_x", False)),
                    b.get("speed")))
            elif p == "/api/speed":
                self._send(200, e.set_speed(float(b.get("speed", 1.0))))
            elif p == "/api/playlist/set":
                self._send(200, e.playlist_set(
                    b.get("ids"), b.get("loops"), b.get("brightness"),
                    b.get("speed")))
            elif p == "/api/playlist/start":
                self._send(200, e.playlist_start(
                    b.get("ids"), b.get("loops"), b.get("brightness"),
                    b.get("speed"), b.get("index", 0)))
            elif p == "/api/playlist/next":
                self._send(200, e.playlist_next())
            elif p == "/api/playlist/stop":
                self._send(200, e.playlist_stop())
            elif p == "/api/effects/tune":
                last = getattr(e, "_last_effect", None)
                fx = getattr(e, "_last_fx", None)
                if not last and not fx:
                    self._send(400, {"ok": False, "error": "还没有播放过灯效"})
                elif last:
                    r = e.play_effect(
                        last["id"], last.get("brightness", 1.0),
                        last.get("loops", 0), last.get("mode", "matrix"),
                        float(b.get("ox", last.get("ox", 0.0))),
                        float(b.get("oy", last.get("oy", 0.0))),
                        float(b.get("zoom", last.get("zoom", 1.0))),
                        float(b.get("rot_deg", last.get("rot_deg", 0.0))),
                        bool(b.get("mirror_x", last.get("mirror_x", False))))
                    self._send(200, r)
                else:
                    r = e.set_gif(
                        fx["data"], loops=fx.get("loops", 0),
                        brightness=fx.get("brightness", 1.0),
                        space=fx.get("space", "fx"),
                        ox=float(b.get("ox", fx.get("ox", 0.0))),
                        oy=float(b.get("oy", fx.get("oy", 0.0))),
                        zoom=float(b.get("zoom", fx.get("zoom", 1.0))),
                        rot_deg=float(b.get("rot_deg", fx.get("rot_deg", 0.0))),
                        mirror_x=bool(b.get("mirror_x", fx.get("mirror_x", False))))
                    r["name"] = "(自定义动画)"
                    self._send(200, r)
            elif p == "/api/gif":
                self._send(200, e.set_gif(
                    b["data"], int(b.get("loops", 0)),
                    float(b.get("brightness", 1.0)),
                    bool(b.get("rotate", False)),
                    b.get("fit") or "cover", b.get("space") or "band",
                    float(b.get("ox", 0.0)), float(b.get("oy", 0.0)),
                    float(b.get("zoom", 1.0)), float(b.get("rot_deg", 0.0)),
                    bool(b.get("mirror_x", False)), b.get("speed")))
            elif p == "/api/text":
                self._send(200, e.set_text(
                    b.get("text", ""), int(b.get("size", 286)),
                    float(b.get("speed", 60)), bool(b.get("rotate", True)),
                    bool(b.get("scroll", True)),
                    float(b.get("brightness", 1.0)),
                    float(b.get("stretch", 1.0)),
                    float(b.get("rotate_deg", 0.0)),
                    float(b.get("v_offset", 0.0))))
            elif p == "/api/sysinfo/fontv":
                self._send(200, e.set_sysinfo_font_v(
                    b.get("font_v", 1.0)))
            elif p == "/api/sysinfo/autogame":
                self._send(200, e.set_sysinfo_auto_game(
                    bool(b.get("auto_game", True))))
            elif p == "/api/sysinfo":
                if b.get("use_saved"):
                    self._send(200, e.set_sysinfo_saved())
                else:
                    self._send(200, e.set_sysinfo(
                        show_battery=bool(b.get("battery", True)),
                        show_cpu=bool(b.get("cpu", True)),
                        speed=float(b.get("speed", 90)),
                        show_app=bool(b.get("app", True)),
                        show_time=bool(b.get("time", True)),
                        app_prefix=str(b.get("app_prefix", "正在使用")),
                        order=b.get("order"),
                        enabled=b.get("enabled"),
                        display=b.get("display"),
                        rotate_sec=b.get("rotate_sec"),
                        durations=b.get("durations"),
                        font_size=b.get("font_size"),
                        font_v=b.get("font_v"),
                        auto_game=b.get("auto_game"),
                        scroll_speed=b.get("scroll_speed"),
                        custom_cpu_name=b.get("custom_cpu_name"),
                        custom_gpu_name=b.get("custom_gpu_name")))
            elif p == "/api/music":
                self._send(200, e.set_music(bool(b.get("on", True)),
                                            float(b.get("gain", 1.0)),
                                            str(b.get("style", "bars"))))
            elif p == "/api/music/state":
                self._send(200, e.music_state())
            elif p == "/api/music/params":
                self._send(200, e.music_set(
                    b.get("bars"), b.get("col_width"), b.get("col_gap"),
                    b.get("gap_level"), b.get("mode"), b.get("show_title"),
                    b.get("bars_time"), b.get("np_time"),
                    b.get("np_frac"), b.get("np_units"), b.get("np_speed"),
                    b.get("np_bar_dim"), b.get("np_v_off"), b.get("show_bars"),
                    b.get("gain"), b.get("peaks"), b.get("gradient"),
                    b.get("decay"), b.get("full"), b.get("style")))
            elif p == "/api/music/now":
                self._send(200, {"text": e._np.text() if e._np else "",
                                 "title": e._np.title if e._np else "",
                                 "artist": e._np.artist if e._np else ""})
            elif p == "/api/frame":
                self._send(200, e.set_raw(b["data"]))
            else:
                self._send(404, {"error": "not found"})
        except Exception as ex:
            import traceback
            log("请求失败:", ex)
            log(traceback.format_exc())
            self._send(500, {"ok": False, "error": str(ex)})


def main():
    global PORT
    import atexit
    # pythonw（无控制台）下 stdout/stderr 为 None，print 会报错；转到日志文件
    if sys.stdout is None or sys.stderr is None:
        try:
            _lf = open(os.path.join(ROOT, "anime-vision.log"), "a",
                       encoding="utf-8", buffering=1)
        except Exception:
            _lf = open(os.devnull, "w")
        if sys.stdout is None:
            sys.stdout = _lf
        if sys.stderr is None:
            sys.stderr = _lf
    if len(sys.argv) > 1:
        PORT = int(sys.argv[1])
    if is_admin():
        log("管理员模式：暂停华硕灯效服务以独占灯板")
        pause_asus_lighting()
        start_conflict_watchdog()
        atexit.register(resume_asus_lighting)
    else:
        log("提示：以管理员身份运行可暂停华硕灯效服务，彻底消除闪烁")
    engine = Engine()
    Handler.engine = engine
    # 启动时就连接灯板，后台/托盘模式下不用先打开网页
    for _ in range(2):
        r = engine.connect()
        if r.get("ok"):
            break
        time.sleep(1.0)
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    Handler.server = srv
    log(f"控制台已启动: http://127.0.0.1:{PORT}")
    threading.Thread(target=engine.restore_last, daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log("退出")
    finally:
        try:
            engine.shutdown_all()
        except Exception:
            pass
        srv.server_close()


if __name__ == "__main__":
    main()

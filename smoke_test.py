# -*- coding: utf-8 -*-
"""AniMe Vision 冒烟测试 / 简易命令行工具。

用法示例:
  python smoke_test.py list              # 列出设备
  python smoke_test.py test              # 初始化+亮度+测试图案（验证硬件通路）
  python smoke_test.py clear             # 清空灯板
  python smoke_test.py brightness 2      # 设置亮度 0-3
  python smoke_test.py on / off          # 显示开关
  python smoke_test.py image path.png    # 显示图片
  python smoke_test.py gif path.gif --loops 3
"""

import argparse
import sys
import time

import animelib


def cmd_list(args):
    print("枚举 HID 设备:")
    for p, ok in animelib.enumerate_hid_paths():
        print(("  [灯板] " if ok else "  [其他] ") + p)
    paths = animelib.find_anime_paths()
    if not paths:
        print("\n!! 未找到灯板 (VID_0B05 PID_193B)")
        return 1
    print(f"\n找到 {len(paths)} 个灯板接口")
    return 0


def test_pattern():
    """两区域亮度 + 面板描边 + 中心十字，用于验证几何映射。"""
    data = bytearray(animelib.LED_COUNT)
    for i, (x, y) in enumerate(animelib.LEDS):
        first = 0 if y < 28 else (y - 28) // 2
        width = (y // 2 + 1) if y < 28 else 15
        j = int(round(x + 0.5 * (y % 2) - first))
        if y == 0 or y == animelib.HEIGHT - 1 or j == 0 or j == width - 1:
            v = 255                       # 描边
        elif abs(x - 16.5) < 1.2 or abs(y - 34) < 1.2:
            v = 255                       # 中心十字
        else:
            v = 70 if y < 28 else 140     # 三角区暗 / 矩形区亮
        data[i] = v
    return bytes(data)


def cmd_test(args):
    print("1) 打开设备 ...")
    with animelib.open_anime() as dev:
        print("2) 发送初始化包 ...")
        dev.init()
        time.sleep(0.1)
        print("3) 设置亮度为中 ...")
        dev.set_brightness(2)
        time.sleep(0.1)
        print("4) 发送测试图案（描边+区域+十字）...")
        dev.send_frame(test_pattern())
        print("5) 完成！请查看笔记本 A 面（合盖看）。")
        print("   如果图案正确显示，说明协议通路完全打通。")
    return 0


def cmd_clear(args):
    with animelib.open_anime() as dev:
        dev.init()
        dev.send_frame(bytes(animelib.LED_COUNT))
        print("灯板已清空")
    return 0


def cmd_brightness(args):
    level = int(args.level)
    if not 0 <= level <= 3:
        print("亮度必须是 0-3")
        return 1
    with animelib.open_anime() as dev:
        dev.init()
        dev.set_brightness(level)
        print(f"亮度已设为 {level}")
    return 0


def cmd_onoff(args):
    with animelib.open_anime() as dev:
        dev.init()
        dev.enable_display(args.on)
        print("显示已" + ("开启" if args.on else "关闭"))
    return 0


def cmd_image(args):
    from PIL import Image
    img = Image.open(args.path)
    with animelib.open_anime() as dev:
        dev.init()
        dev.set_brightness(2)
        data = animelib.image_to_leds(img, brightness=args.bright)
        dev.send_frame(data)
        print(f"已显示 {args.path}（亮度 {args.bright}）")
    return 0


def cmd_gif(args):
    frames, durations = animelib.load_gif_frames(args.path)
    print(f"GIF 共 {len(frames)} 帧")
    with animelib.open_anime() as dev:
        dev.init()
        dev.set_brightness(2)
        try:
            animelib.play_gif(dev, frames, durations,
                              loops=args.loops, brightness=args.bright)
        except KeyboardInterrupt:
            print("\n已停止")
    return 0


def main():
    ap = argparse.ArgumentParser(description="AniMe Vision 冒烟测试工具")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list").set_defaults(fn=cmd_list)
    sub.add_parser("test").set_defaults(fn=cmd_test)
    sub.add_parser("clear").set_defaults(fn=cmd_clear)

    p = sub.add_parser("brightness")
    p.add_argument("level")
    p.set_defaults(fn=cmd_brightness)

    p = sub.add_parser("on")
    p.set_defaults(fn=cmd_onoff, on=True)
    p = sub.add_parser("off")
    p.set_defaults(fn=cmd_onoff, on=False)

    p = sub.add_parser("image")
    p.add_argument("path")
    p.add_argument("--bright", type=float, default=1.0)
    p.set_defaults(fn=cmd_image)

    p = sub.add_parser("gif")
    p.add_argument("path")
    p.add_argument("--loops", type=int, default=0)
    p.add_argument("--bright", type=float, default=1.0)
    p.set_defaults(fn=cmd_gif)

    args = ap.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()

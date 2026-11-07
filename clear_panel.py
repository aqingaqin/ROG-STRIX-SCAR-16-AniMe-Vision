# -*- coding: utf-8 -*-
"""退出时兜底：直接打开灯板写一帧全灭。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import animelib


def main():
    panel = animelib.Panel()
    try:
        panel.open()
        panel.clear()
    finally:
        try:
            panel.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()

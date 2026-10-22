#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把自定义 WAV 写入 Z8 EG 的音源库,并修改长度/地址常量。

输入:未加密的 EG 模块(81,807,711 字节,含尾部 CRC)
输出:打过补丁的 EG 模块

用法:
    python build_custom_sound.py eg.bin my_sound.wav C out_eg.bin

说明:
  - 只处理 EG 模块本身;如何从固件包里取出/放回 EG 由使用者自行完成
  - 版本号不会改动(需要另行替换),请自行确保输出版本高于相机当前版本
"""
import argparse
import struct
import sys
import wave
from pathlib import Path

import numpy as np

BASE = 0x40160000
EG_SIZE = 81807711          # 含尾部 2 字节 CRC

# 类型 -> 四个资源的 (ROM 地址, 字节数)
TYPE_RES = {
    'B': [(0x43FBB850, 28800), (0x43FC28D0, 9600), (0x43FC4E50, 19200), (0x43FC9950, 7680)],
    'C': [(0x43FCB750, 28800), (0x43FD27D0, 9600), (0x43FD4D50, 19200), (0x43FD9850, 7680)],
    'D': [(0x43FDB650, 28800), (0x43FE26D0, 9600), (0x43FE4C50, 19200), (0x43FE9750, 7680)],
    'E': [(0x43FEB550, 28800), (0x43FF25D0, 9600), (0x43FF4B50, 7680 + 0)],  # E 的终段见 inspect
}
# A 型只有两个资源,结构不同,本脚本暂不支持

LEN_GETTER = 0x40E34920     # mov w0,#0x7080 (28800) -> 改成 0xFF00 (65280)
LEN_TABLE  = 0x43FB7E70     # kind -> 长度 getter
ADR_TABLE  = 0x43FB7DA0     # kind -> 地址 getter
RAM_BASE   = 0x0A15C2B100   # C 型 RAM 缓冲基址
TYPE_KIND0 = {'B': 10, 'C': 14, 'D': 18, 'E': 22}


def load_wav(path, frames):
    with wave.open(str(path)) as w:
        if w.getnchannels() != 2 or w.getsampwidth() != 2:
            raise SystemExit('WAV 必须是 16-bit 立体声(先用 ffmpeg 转换)')
        rate = w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').astype(np.float32).reshape(-1, 2)
    if rate != 48000:
        idx = np.linspace(0, len(data) - 1, int(round(len(data) * 48000 / rate)))
        data = np.stack([np.interp(idx, np.arange(len(data)), data[:, c]) for c in (0, 1)], axis=1)
    if len(data) < frames:
        data = np.vstack([data, np.zeros((frames - len(data), 2), dtype=np.float32)])
    data = data[:frames].copy()
    # 尾部 20 ms 渐隐
    fo = min(int(0.020 * 48000), len(data))
    for i in range(fo):
        data[len(data) - 1 - i] *= i / fo
    peak = np.abs(data).max()
    if peak > 0:
        data *= (32768 * 0.84) / peak
    return np.clip(data, -32768, 32767).astype('<i2')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('eg', type=Path, help='未加密的 EG 模块 (81,807,711 字节)')
    ap.add_argument('wav', type=Path, help='自定义音频 (48 kHz 立体声 16-bit)')
    ap.add_argument('type', choices=sorted(TYPE_KIND0), help='要替换的快门音类型')
    ap.add_argument('out', type=Path)
    a = ap.parse_args()

    eg = bytearray(a.eg.read_bytes())
    if len(eg) != EG_SIZE:
        raise SystemExit('EG 长度不符: %d (期望 %d)' % (len(eg), EG_SIZE))

    res = TYPE_RES[a.type]
    total = sum(r[1] for r in res)
    print('类型 %s: %d 个资源, 共 %d 字节 (%.1f ms)'
          % (a.type, len(res), total, total / 192.0))

    pcm = load_wav(a.wav, total // 4).tobytes()
    if len(pcm) != total:
        raise SystemExit('音频填充长度不符')

    # 1) 写入音频(四个资源在 ROM 里连续)
    first = res[0][0]
    eg[first - BASE:first - BASE + total] = pcm
    print('  音频写入 0x%08X, %d 字节' % (first, total))

    # 2) 长度 getter: 28800 -> total
    cur = struct.unpack_from('<I', eg, LEN_GETTER - BASE)[0]
    if cur != 0x528E1000:
        raise SystemExit('长度 getter 处的字节不符预期(0x%08X),固件版本可能不同' % cur)
    eg[LEN_GETTER - BASE:LEN_GETTER - BASE + 4] = struct.pack('<I', 0x52800000 | ((total & 0xFFFF) << 5))
    print('  长度 getter 0x%08X -> %d 字节' % (LEN_GETTER, total))

    # 3) 前段(kind0+1)的长度表项指向同一个 getter, 地址指向块首
    k = TYPE_KIND0[a.type] + 1
    at = LEN_TABLE + (k - 1) * 8
    eg[at - BASE:at - BASE + 8] = struct.pack('<Q', LEN_GETTER)
    print('  kind%d 长度表项 -> 0x%08X' % (k, LEN_GETTER))
    at = ADR_TABLE + (k - 1) * 8
    eg[at - BASE:at - BASE + 8] = struct.pack('<Q', 0x40E34804)   # 现成的"返回块首"getter
    print('  kind%d 地址表项 -> 0x40E34804' % k)

    # 4) CRC
    import binascii
    eg[-2:] = binascii.crc_hqx(bytes(eg[:-2]), 0).to_bytes(2, 'big')
    a.out.write_bytes(bytes(eg))
    print('\n输出 %s' % a.out)
    print('注意:版本号未改动,回写固件包前请自行处理')


if __name__ == '__main__':
    main()

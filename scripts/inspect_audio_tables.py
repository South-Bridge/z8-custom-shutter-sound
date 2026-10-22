#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打印 Z8 EG 里的音频 kind 分派表与资源清单。

用法:
    python inspect_audio_tables.py eg.bin
"""
import argparse
import struct
from pathlib import Path

BASE = 0x40160000
LEN_TABLE = 0x43FB7E70
ADR_TABLE = 0x43FB7DA0
VOL_TABLE = 0x43FB7F40
TYPES = {'A': (0, 1, 2, 6), 'B': (10, 11, 12, 13), 'C': (14, 15, 16, 17),
         'D': (18, 19, 20, 21), 'E': (22, 23, 24, 25)}
ROLES = ('合成段/快', '前段', '中段', '终段')

MOVZ_W, MOVK_W = 0x52800000, 0x72800000
MOVZ_X, MOVK_X = 0xD2800000, 0xF2800000
ORR_W_IMM = 0x32000000


def bitmask_imm(w):
    """解码逻辑立即数 (位掩码形式),用于 `orr w0, wzr, #imm` 别名。"""
    n = (w >> 22) & 1
    immr = (w >> 16) & 0x3F
    imms = (w >> 10) & 0x3F
    combined = (n << 6) | (~imms & 0x3F)
    length = combined.bit_length() - 1
    if length < 1:
        return None
    levels = (1 << length) - 1
    s = imms & levels
    r = immr & levels
    if s == levels:
        return None
    esize = 1 << length
    welem = (1 << (s + 1)) - 1
    welem = ((welem >> r) | (welem << (esize - r))) & ((1 << esize) - 1)
    val = 0
    for i in range(0, 32, esize):
        val |= welem << i
    return val


def const_of(eg, va):
    """解析 getter:若它以 movz/movk 往 w0/x0 装常量并 ret,返回值;否则返回 None(动态)。"""
    # 分发器在跳转前已经把 w0 设成默认 9600;直接指向那条 ret 的 getter 返回默认值
    if va == 0x40E34934:
        return 9600
    val = 0
    known = False
    for i in range(10):
        off = va - BASE + i * 4
        if off < 0 or off + 4 > len(eg):
            return None
        w = struct.unpack_from('<I', eg, off)[0]
        m = w & 0xFF800000
        rd = w & 0x1F
        if m == MOVZ_W or m == MOVZ_X:
            val = ((w >> 5) & 0xFFFF) << (16 * ((w >> 21) & 3))
            known = (rd == 0)
        elif m == MOVK_W or m == MOVK_X:
            if rd != 0:
                return None
            sh = 16 * ((w >> 21) & 3)
            val = (val & ~(0xFFFF << sh)) | (((w >> 5) & 0xFFFF) << sh)
        elif w == 0xD65F03C0:                     # ret
            return val if known else None
        elif (w & 0xFF800000) == ORR_W_IMM and (w & 0x1F) == 0 and ((w >> 5) & 0x1F) == 31:
            v = bitmask_imm(w)                    # orr w0, wzr, #imm  (mov w0,#imm 别名)
            if v is None:
                return None
            val = v
            known = True
        elif (w & 0xFFC00000) in (0xB9400000, 0xB9000000, 0xB8400000, 0xF9400000):
            return None                            # ldr/str -> 动态
        elif (w & 0xFFC00000) == 0x79000000 or (w & 0xFFC00000) == 0x79400000:
            return None                            # ldrh -> 动态
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('eg', type=Path)
    a = ap.parse_args()
    eg = a.eg.read_bytes()
    if len(eg) < 0x43FB8000 - BASE:
        raise SystemExit('文件太短,确认这是解密后的 EG 模块')

    print('=== 长度表 (0x%08X) ===' % LEN_TABLE)
    for kind in range(1, 27):
        at = LEN_TABLE + (kind - 1) * 8
        fn = struct.unpack_from('<Q', eg, at - BASE)[0]
        v = const_of(eg, fn)
        desc = '%6d B (%5.1f ms)' % (v, v / 192.0) if v is not None else '动态/未知'
        print('  kind %2d -> getter 0x%08X  %s' % (kind, fn, desc))

    print('\n=== 地址表 (0x%08X) ===' % ADR_TABLE)
    for kind in range(1, 27):
        at = ADR_TABLE + (kind - 1) * 8
        fn = struct.unpack_from('<Q', eg, at - BASE)[0]
        v = const_of(eg, fn)
        desc = '0x%012X' % v if v is not None else '动态/未知'
        print('  kind %2d -> getter 0x%08X  %s' % (kind, fn, desc))

    print('\n=== 五个类型 ===')
    for t, kinds in TYPES.items():
        print(' 类型 %s:' % t)
        for role, kind in zip(ROLES, kinds):
            af = struct.unpack_from('<Q', eg, ADR_TABLE + (kind - 1) * 8 - BASE)[0]
            addr = const_of(eg, af)
            lf = struct.unpack_from('<Q', eg, LEN_TABLE + (kind - 1) * 8 - BASE)[0]
            ln = const_of(eg, lf)
            if t == 'A' and role.startswith('合成'):
                print('    %-8s kind %2d  特殊结构(另见地址表)' % (role, kind))
                continue
            print('    %-8s kind %2d  RAM %s  长度 %s'
                  % (role, kind,
                     ('0x%012X' % addr) if addr else '?',
                     ('%d B (%.0f ms)' % (ln, ln / 192.0)) if ln else '?'))


if __name__ == '__main__':
    main()

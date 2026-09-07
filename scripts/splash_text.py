#!/usr/bin/env python3
"""Blend the "NOW LOADING..." coverage strip onto splash.bin (phase 7 T7
round 2). Runs as the last step of the loader/Makefile splash.bin rule, so
the text is baked into the RGB565 image the loader displays and the shim's
side-buffer copy scans through the boot gap.

usage: splash_text.py <splash.bin> <strip.bin>
strip format: [u16 w][u16 h] LE + w*h coverage bytes (255 = full ink); see
scripts/gen_nowloading_strip.py. Ink is black: each covered pixel is scaled
toward 0, keeping the antialiased edges correct on the off-white splash.
"""
import struct
import sys

W, H = 640, 480
TOP = 396           # strip's top row; keeps rows 428+ free for the spinner

splash_path, strip_path = sys.argv[1], sys.argv[2]
buf = bytearray(open(splash_path, "rb").read())
assert len(buf) == W * H * 2, f"unexpected splash size {len(buf)}"
raw = open(strip_path, "rb").read()
sw, sh = struct.unpack_from("<HH", raw)
mask = raw[4:]
assert len(mask) == sw * sh, "strip header/payload mismatch"

x0 = (W - sw) // 2
for y in range(sh):
    for x in range(sw):
        m = mask[y * sw + x]
        if not m:
            continue
        o = ((TOP + y) * W + x0 + x) * 2
        v = buf[o] | (buf[o + 1] << 8)
        r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
        k = 255 - m
        v = (((r * k) // 255) << 11) | (((g * k) // 255) << 5) | ((b * k) // 255)
        buf[o] = v & 0xFF
        buf[o + 1] = v >> 8
open(splash_path, "wb").write(bytes(buf))
print(f"splash_text: blended {sw}x{sh} strip at ({x0},{TOP})")

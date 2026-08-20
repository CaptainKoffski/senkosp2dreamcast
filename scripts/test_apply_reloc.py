#!/usr/bin/env python3
"""Self-check for apply_reloc.py — synthetic image, one patch, one mismatch."""
import struct

import apply_reloc as A

img = struct.pack("<4I", 0x11111111, 0x8d244c20, 0x33333333, 0x44444444)
patches = [{"dat_offset": "0x4", "old": "0x8d244c20", "new": "0x8c400000", "why": "test"}]
out = A.apply(img, patches)
assert struct.unpack("<4I", out) == (0x11111111, 0x8c400000, 0x33333333, 0x44444444)

try:
    A.apply(img, [{"dat_offset": "0x8", "old": "0xdeadbeef", "new": "0x0", "why": "bad"}])
    raise SystemExit("FAIL: mismatch not detected")
except ValueError:
    pass
print("OK apply_reloc self-check")

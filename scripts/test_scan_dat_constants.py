#!/usr/bin/env python3
"""Self-check for scan_dat_constants.py — synthetic image, known hits."""
import os
import struct
import tempfile

import scan_dat_constants as S

# corridor1 value (0x8d244c20 -> phys 0x0d244c20), vram64 value, and noise.
words = [0x00000000, 0x8d244c20, 0xdeadbeef, 0x04810000, 0x0e000000]
with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
    f.write(struct.pack("<%dI" % len(words), *words))
    path = f.name
try:
    hits = S.scan(path)
    assert hits == [(4, 0x8d244c20, "corridor1"), (12, 0x04810000, "vram64")], hits
    print("OK scan_dat_constants self-check")
finally:
    os.unlink(path)

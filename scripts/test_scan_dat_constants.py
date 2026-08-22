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

    # --range: window is [start, end), offsets stay absolute file offsets.
    assert S.scan(path, start=8) == [(12, 0x04810000, "vram64")], S.scan(path, start=8)
    assert S.scan(path, start=0, end=8) == [(4, 0x8d244c20, "corridor1")]
    assert S.scan(path, start=5, end=8) == [(4, 0x8d244c20, "corridor1")]  # start rounds down

    # --words: explicit 29-bit-physical ranges replace RANGES; P1/P2/P4 forms
    # all mask to the same physical, so 0x8d244c20 matches a 0x0d24… spec.
    w = S.parse_words("a0000000-a0000000,8d244c20-8d244c21")
    assert w == [("00000000-00000000", 0, 0), ("0d244c20-0d244c21", 0x0d244c20, 0x0d244c21)], w
    assert S.scan(path, w) == [(0, 0x00000000, "00000000-00000000"),
                               (4, 0x8d244c20, "0d244c20-0d244c21")], S.scan(path, w)
    # single-value spec (no '-')
    assert S.parse_words("deadbeef") == [("1eadbeef-1eadbeef", 0x1eadbeef, 0x1eadbeef)]
    assert S.scan(path, S.parse_words("deadbeef")) == [(8, 0xdeadbeef, "1eadbeef-1eadbeef")]

    print("OK scan_dat_constants self-check")
finally:
    os.unlink(path)

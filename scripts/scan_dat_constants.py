#!/usr/bin/env python3
"""Scan a flat Naomi image for LE u32 words whose 29-bit physical value lands
in a watched range (above-cap corridors / VRAM). Candidate generator for
Phase 3 target 3 — catches descriptor tables OUTSIDE the boot slice (streamed
data). Keep RANGES in sync with scripts/ghidra/ScanPlacementConstants.java.

Usage: scan_dat_constants.py senkosp.dat
Output: DATHIT off=0x<file offset> word=0x<value> range=<label>
"""
import argparse
import array
import sys

RANGES = [  # (label, lo, hi) — 29-bit physical, inclusive
    ("corridor1", 0x0d244c20, 0x0dd73e00),
    ("corridor2", 0x0dd7d020, 0x0dd92020),
    ("corridor3", 0x0ddc2960, 0x0dde3960),
    ("corridor4", 0x0de4dbe0, 0x0de8b480),
    ("corridor5", 0x0dfe6d20, 0x0dfe7520),
    ("vram64",    0x04800000, 0x04ffffff),
    ("vram32",    0x05800000, 0x05ffffff),
]


def scan(path):
    with open(path, "rb") as f:
        data = f.read()
    words = array.array("I")
    words.frombytes(data[: len(data) // 4 * 4])
    if sys.byteorder != "little":
        words.byteswap()
    hits = []
    # ponytail: ~62M-word pure-python loop, ~1 min on the 250 MB .dat — fine
    # for a one-shot analysis; vectorize only if it gets re-run in a loop.
    for i, w in enumerate(words):
        p = w & 0x1FFFFFFF
        for label, lo, hi in RANGES:
            if lo <= p <= hi:
                hits.append((i * 4, w, label))
                break
    return hits


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    args = ap.parse_args(argv)
    for off, w, label in scan(args.image):
        print(f"DATHIT off=0x{off:08x} word=0x{w:08x} range={label}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

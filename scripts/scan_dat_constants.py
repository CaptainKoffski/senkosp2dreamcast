#!/usr/bin/env python3
"""Scan a flat Naomi image for LE u32 words whose 29-bit physical value lands
in a watched range (above-cap corridors / VRAM). Candidate generator for
Phase 3 target 3 — catches descriptor tables OUTSIDE the boot slice (streamed
data). Keep RANGES in sync with scripts/ghidra/ScanPlacementConstants.java.

Usage: scan_dat_constants.py senkosp.dat
       scan_dat_constants.py senkosp.dat --range 0x171ff8:0x1bfc38 \
                             --words a05f7000-a05f77ff,a05f6c00-a05f6cff
Output: DATHIT off=0x<file offset> word=0x<value> range=<label>

`--range` limits the file window (Phase 4 uses it to scan one load entry, e.g.
the Test image at `.dat` 0x171ff8 + 0x4dc40); `--words` replaces RANGES with
an explicit inclusive 29-bit-physical list (label = "lo-hi").
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


def scan(path, ranges=RANGES, start=0, end=None):
    """Hits in [start, end) of `path`; offsets returned are absolute file
    offsets. `start` is rounded down to a 4-byte boundary."""
    start &= ~3
    with open(path, "rb") as f:
        f.seek(start)
        data = f.read(-1 if end is None else max(0, end - start))
    words = array.array("I")
    words.frombytes(data[: len(data) // 4 * 4])
    if sys.byteorder != "little":
        words.byteswap()
    hits = []
    # ponytail: ~62M-word pure-python loop, ~1 min on the 250 MB .dat — fine
    # for a one-shot analysis; vectorize only if it gets re-run in a loop.
    for i, w in enumerate(words):
        p = w & 0x1FFFFFFF
        for label, lo, hi in ranges:
            if lo <= p <= hi:
                hits.append((start + i * 4, w, label))
                break
    return hits


def parse_words(spec):
    """'a05f7000-a05f77ff,a05f6c00-a05f6cff' -> [(label, lo, hi), ...],
    each bound masked to 29-bit physical (so P1/P2/P4 forms all work)."""
    out = []
    for part in spec.split(","):
        lo, _, hi = part.strip().partition("-")
        lo = int(lo, 16) & 0x1FFFFFFF
        hi = (int(hi, 16) & 0x1FFFFFFF) if hi else lo
        out.append((f"{lo:08x}-{hi:08x}", lo, hi))
    return out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--range", dest="window", metavar="LO:HI",
                    help="hex file-offset window, end-exclusive (default: whole file)")
    ap.add_argument("--words", metavar="LO-HI[,LO-HI...]",
                    help="hex 29-bit-physical ranges replacing the built-in RANGES")
    args = ap.parse_args(argv)
    start, end = 0, None
    if args.window:
        lo, _, hi = args.window.partition(":")
        start, end = int(lo, 16), int(hi, 16) if hi else None
    ranges = parse_words(args.words) if args.words else RANGES
    for off, w, label in scan(args.image, ranges, start, end):
        print(f"DATHIT off=0x{off:08x} word=0x{w:08x} range={label}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

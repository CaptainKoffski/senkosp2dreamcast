#!/usr/bin/env python3
"""Apply the Phase 3 relocation patch set to a flat Naomi image.
Each entry must match its expected old value or the run refuses (a moved
base or a stale patchset must never half-patch an image).

Usage: apply_reloc.py senkosp.dat scripts/reloc_patchset.json -o senkosp-reloc.dat
Patchset: JSON array of {"dat_offset": "0x..", "old": "0x..", "new": "0x..", "why": ".."}
"""
import argparse
import json
import struct
import sys


def apply(image, patches):
    buf = bytearray(image)
    for p in patches:
        off = int(p["dat_offset"], 16)
        old = int(p["old"], 16)
        new = int(p["new"], 16)
        cur = struct.unpack_from("<I", buf, off)[0]
        if cur != old:
            raise ValueError(
                f"at 0x{off:x}: expected 0x{old:08x}, found 0x{cur:08x} ({p['why']})")
        struct.pack_into("<I", buf, off, new)
    return bytes(buf)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("patchset")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args(argv)
    with open(a.patchset) as f:
        patches = json.load(f)
    with open(a.image, "rb") as f:
        img = f.read()
    with open(a.out, "wb") as f:
        f.write(apply(img, patches))
    print(f"patched {len(patches)} words -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

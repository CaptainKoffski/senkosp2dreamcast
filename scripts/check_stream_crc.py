#!/usr/bin/env python3
"""Verify SHIMCRC (delivered) + GDPIO/GDDMA (drive) lines against ground truth.
Spec: docs/superpowers/specs/2026-08-23-phase5-hardware-design.md (verdict table).
Conventions (CHECK lines, exit code) follow parse_cartlog.py.

Ground truth:
  senkosp.dat    -- cart byte domain. SHIMCRC o=/l= index straight into it
                     (the loader patches only in-RAM boot images at load
                     time; the disc always carries the pristine cart bytes).
  build/track04.iso -- FAD domain. file offset = (fad - base_fad) * 2048
                     (base_fad default 450150 = LBA 450000 + 150,
                     scripts/make_gdi.py:149). GDPIO/GDDMA fad/secs/type
                     index straight into it -- track04.iso already IS
                     [loader+padding][senkosp.dat], so no separate cart-FAD
                     split is needed here.

Texpatch caveat (2026-08-24): default make_gdi.py builds splice the
shrink_vq.py records into track04, so its cart region is NOT byte-identical
to senkosp.dat there. GD checks are unaffected (track04 is the on-disc
truth). SHIMCRC ranges overlapping those records WOULD mismatch a pristine
--dat: for SHIM_CRC diagnostic legs on a patched build, pass a
texpatch-applied flat image as --dat (or diagnose on a --no-texpatch build).
"""
import argparse
import os
import re
import sys
import zlib

SHIMCRC = re.compile(r'SHIMCRC o=([0-9a-f]{8}) l=([0-9a-f]{8}) c=([0-9a-f]{8})')
GDREAD  = re.compile(r'GD(PIO|DMA) fad=([0-9a-f]{8}) secs=([0-9a-f]+) type=([0-9a-f]+) crc=([0-9a-f]{8})')
TRACK04_BASE_FAD = 450150          # LBA 450000 + 150 (make_gdi.py:149)
SECTOR_TYPE_DATA = 0x800           # 2048 B/sector; anything else is a TOC/raw read

def crc(buf): return zlib.crc32(buf) & 0xffffffff


def parse_shimcrc(path):
    """(o, l, c) per SHIMCRC line, log order. Unanchored match per line --
    the serial layer emits \\r\\n and Flycast may prefix its own
    timestamp/log text on stdout lines."""
    recs = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            for m in SHIMCRC.finditer(line):
                recs.append(tuple(int(g, 16) for g in m.groups()))
    return recs


def parse_gdread(path):
    """(kind, fad, secs, type, crc) per GDPIO/GDDMA line, log order."""
    recs = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            for m in GDREAD.finditer(line):
                kind, fad, secs, typ, c = m.groups()
                recs.append((kind, int(fad, 16), int(secs, 16), int(typ, 16), int(c, 16)))
    return recs


def verify_shimcrc(records, dat_path):
    """Each record -> (o, l, c, got, status). One open file handle, seek+read
    per record -- senkosp.dat is 251 MB, never slurped whole."""
    out = []
    with open(dat_path, "rb") as f:
        for o, l, c in records:
            f.seek(o)
            buf = f.read(l)
            got = crc(buf)
            status = "PASS" if (got == c and len(buf) == l) else "FAIL"
            out.append((o, l, c, got, status))
    return out


def verify_gdread(records, track04_path, base_fad):
    """Each record -> (kind, fad, secs, type, crc, got, status). status is
    one of PASS, FAIL, lowfad, typeskip.
      fad < base_fad          -> lowfad (TOC/low-track read, never fails)
      type != 0x800            -> typeskip (raw/TOC read, never fails)
      byte range past EOF      -> FAIL (malformed/misattributed read)
      otherwise                -> PASS/FAIL on CRC-32/IEEE match
    """
    size = os.path.getsize(track04_path)
    out = []
    with open(track04_path, "rb") as f:
        for kind, fad, secs, typ, c in records:
            if fad < base_fad:
                out.append((kind, fad, secs, typ, c, None, "lowfad"))
                continue
            if typ != SECTOR_TYPE_DATA:
                out.append((kind, fad, secs, typ, c, None, "typeskip"))
                continue
            off = (fad - base_fad) * 2048
            length = secs * typ
            if off + length > size:
                out.append((kind, fad, secs, typ, c, None, "FAIL"))
                continue
            f.seek(off)
            buf = f.read(length)
            got = crc(buf)
            status = "PASS" if (got == c and len(buf) == length) else "FAIL"
            out.append((kind, fad, secs, typ, c, got, status))
    return out


def _fmt_shim(r):
    o, l, c, got, status = r
    tail = f" got={got:08x}" if got is not None else ""
    return f"SHIMCRC o={o:08x} l={l:08x} c={c:08x}{tail} -> {status}"


def _fmt_gd(r):
    kind, fad, secs, typ, c, got, status = r
    tail = f" got={got:08x}" if got is not None else ""
    return f"GD{kind} fad={fad:08x} secs={secs:x} type={typ:x} crc={c:08x}{tail} -> {status}"


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stdout", required=True, dest="stdout_path", metavar="LEG.stdout.log",
                     help="leg's stdout log (Task 1 SHIMCRC lines)")
    ap.add_argument("--cartlog", required=True, metavar="LEG.log",
                     help="leg's cartlog (Task 2 GDPIO/GDDMA lines)")
    ap.add_argument("--dat", required=True, help="senkosp.dat (cart byte domain)")
    ap.add_argument("--track04", required=True, help="build/track04.iso (FAD domain)")
    ap.add_argument("--track04-base-fad", type=int, default=TRACK04_BASE_FAD)
    ap.add_argument("--tail", type=int, default=0,
                     help="print the last N records of each stream, with verify status")
    args = ap.parse_args(argv)

    shim_recs = parse_shimcrc(args.stdout_path)
    gd_recs = parse_gdread(args.cartlog)

    shim_v = verify_shimcrc(shim_recs, args.dat)
    gd_v = verify_gdread(gd_recs, args.track04, args.track04_base_fad)

    shim_fail = [r for r in shim_v if r[-1] == "FAIL"]
    gd_fail = [r for r in gd_v if r[-1] == "FAIL"]
    lowfad = [r for r in gd_v if r[-1] == "lowfad"]
    typeskip = [r for r in gd_v if r[-1] == "typeskip"]
    gd_verified = len(gd_v) - len(lowfad) - len(typeskip)

    if lowfad:
        print(f"== lowfad ({len(lowfad)} record(s), fad < {args.track04_base_fad}) ==")
        for r in lowfad:
            print(f"  {_fmt_gd(r)}")
    if typeskip:
        print(f"== typeskip ({len(typeskip)} record(s), type != 0x{SECTOR_TYPE_DATA:x}) ==")
        for r in typeskip:
            print(f"  {_fmt_gd(r)}")

    if args.tail:
        print(f"== tail: last {args.tail} shim record(s) ==")
        for r in shim_v[-args.tail:]:
            print(f"  {_fmt_shim(r)}")
        print(f"== tail: last {args.tail} drive record(s) ==")
        for r in gd_v[-args.tail:]:
            print(f"  {_fmt_gd(r)}")

    checks = [
        ("shimcrc_match", not shim_fail,
         f"{len(shim_v)} SHIMCRC record(s), {len(shim_fail)} mismatch(es)"),
        ("gdread_match", not gd_fail,
         f"{gd_verified} verified (fad>=base,type=0x{SECTOR_TYPE_DATA:x}), "
         f"{len(lowfad)} lowfad, {len(typeskip)} typeskip, {len(gd_fail)} mismatch(es)"),
        ("coverage_nonzero", bool(shim_recs) and bool(gd_recs),
         f"shim={len(shim_recs)} record(s), drive={len(gd_recs)} record(s)"),
    ]
    for name, ok, detail in checks:
        print(f"CHECK {name}: {'PASS' if ok else 'FAIL'} — {detail}")

    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

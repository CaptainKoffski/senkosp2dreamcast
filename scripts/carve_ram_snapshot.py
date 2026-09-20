#!/usr/bin/env python3
"""Carve the 32 MB Naomi main-RAM image out of a Flycast savestate.

This is docs/kb/tooling.md §Phase 3: RAM snapshot, steps 4+5, as one
command: the AutoSaveState route (steps 1-3) produces
~/Library/Application Support/Flycast/data/senkosp.state; this script
inflates it and writes tools/ram-snapshot.bin, refusing to write unless
every carve control test passes.

Container format (../flycast4naomi2dreamcast/core/archive/rzip.cpp):
8-byte magic '#RZIPv\\x01#', u32 LE maxChunkSize, u64 LE total size
(states from 32-bit platforms stored a u32 -- detected the same way
RZipFile::Open does), then u32-length-prefixed zlib chunks (length 0 =
empty chunk, skipped).

Main RAM is located inside the inflated stream by plaintext, not by
parsing the serializer layout: the syMalloc banner sits at RAM offset
0x15c980, so RAM starts at banner_offset - 0x15c980. A candidate is
accepted only if all four KB control tests pass: the banner itself, the
GDFS error strings at 0x15b2c4, the boot-image head == senkosp.dat head
(the boot image loads at 0x8c020000 = .dat offset 0), and the
heap-create code == its .dat twin.

Usage: python3 scripts/carve_ram_snapshot.py [state] [-o out]
  state defaults to the Flycast senkosp.state path above
  out   defaults to tools/ram-snapshot.bin and is never overwritten
        (the snapshot is primary data -- move the old one aside first)
"""
import argparse
import pathlib
import struct
import sys
import zlib

REPO = pathlib.Path(__file__).resolve().parent.parent
MAGIC = b"#RZIPv\x01#"
RAM_SIZE = 32 * 1024 * 1024
BANNER = b"\nsyMalloc Ver 2.01"
BANNER_OFF = 0x15C980
GDFS = b"E00000009:\x00\x00Illegal File Name"
GDFS_OFF = 0x15B2C4
BOOT_BASE = 0x20000            # boot image at 0x8c020000 = .dat offset 0
HEAP_LO, HEAP_HI = 0x85B00, 0x85BB4


def inflate_rzip(blob):
    """Inflate the RZip container found inside blob -> the raw stream."""
    pos = blob.find(MAGIC)
    assert pos >= 0, "RZip magic not found -- not a Flycast savestate?"
    pos += len(MAGIC)
    (max_chunk,) = struct.unpack_from("<I", blob, pos)
    pos += 4
    (size,) = struct.unpack_from("<Q", blob, pos)
    pos += 8
    if size >> 32:             # legacy 32-bit-platform state: u32 size field
        size &= 0xFFFFFFFF
        pos -= 4
    out = bytearray()
    while len(out) < size and pos + 4 <= len(blob):
        (zlen,) = struct.unpack_from("<I", blob, pos)
        pos += 4
        if zlen == 0:
            continue
        chunk = zlib.decompress(blob[pos:pos + zlen])
        assert len(chunk) <= max_chunk, "chunk exceeds declared maxChunkSize"
        pos += zlen
        out += chunk
    assert len(out) >= size, f"stream truncated: {len(out)} < declared {size}"
    return bytes(out[:size])


def carve(stream, dat):
    """Return the first 32 MB window that passes all four control tests."""
    tried = 0
    off = stream.find(BANNER)
    while off >= 0:
        base = off - BANNER_OFF
        if 0 <= base and base + RAM_SIZE <= len(stream):
            tried += 1
            ram = stream[base:base + RAM_SIZE]
            if (ram[GDFS_OFF:GDFS_OFF + len(GDFS)] == GDFS
                    and ram[BOOT_BASE:BOOT_BASE + 0x1000] == dat[:0x1000]
                    and ram[HEAP_LO:HEAP_HI]
                        == dat[HEAP_LO - BOOT_BASE:HEAP_HI - BOOT_BASE]):
                return ram
        off = stream.find(BANNER, off + 1)
    sys.exit(f"FAIL: no RAM candidate passed the carve control tests "
             f"({tried} candidate(s) tried)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("state", nargs="?", default=str(
        pathlib.Path.home()
        / "Library/Application Support/Flycast/data/senkosp.state"))
    ap.add_argument("-o", "--out", default=str(REPO / "tools/ram-snapshot.bin"))
    args = ap.parse_args()

    out = pathlib.Path(args.out)
    if out.exists():
        sys.exit(f"refusing to overwrite existing {out} -- the snapshot is "
                 f"primary data; move it aside first")
    dat_path = REPO / "senkosp.dat"
    if not dat_path.exists():
        sys.exit(f"{dat_path} missing -- the control tests compare against "
                 f"it; extract it first (README step 1)")

    stream = inflate_rzip(pathlib.Path(args.state).read_bytes())
    with open(dat_path, "rb") as f:
        dat = f.read(HEAP_HI - BOOT_BASE)  # covers both compared .dat spans
    ram = carve(stream, dat)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(ram)
    print(f"OK: {len(stream)}-byte stream, all 4 control tests PASS -> "
          f"{out} ({RAM_SIZE} bytes)")


if __name__ == "__main__":
    main()

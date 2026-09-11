#!/usr/bin/env python3
"""Decode/diff the game area (0x24..0x4B) of a Naomi EEPROM image.

T9 recon helper: flip ONE item in Flycast's GAME ASSIGNMENTS menu, exit-save,
quit Flycast, then run this against
  ~/Library/Application Support/Flycast/data/senkosp.zip.eeprom
It prints the 16-byte game record, validates CRC/copies/headers, and diffs
against the previous record if given. Stdlib-only (build-tool rule).

CRC: port of Flycast eeprom_crc (naomi_flashrom.cpp:26-51, the emulator's
implementation of the Naomi BIOS algorithm; KB cite
docs/kb/phase4-conversion.md §EEPROM). Header: [crc_lo][crc_hi][0x10][0x10].

Usage:
  eeprom_game_diff.py EEPROM_FILE [PREV_RECORD_HEX]
"""
import sys


def crc16(buf):
    n = 0xdebdeb00
    for b in buf:
        n = (n & 0xffffff00) + b
        for _ in range(8):
            n = ((n << 1) + 0x10210000) & 0xffffffff if n & 0x80000000 \
                else (n << 1) & 0xffffffff
    for _ in range(8):
        n = ((n << 1) + 0x10210000) & 0xffffffff if n & 0x80000000 \
            else (n << 1) & 0xffffffff
    return n >> 16


def decode(image):
    hdr1, hdr2 = image[0x24:0x28], image[0x28:0x2c]
    rec1, rec2 = image[0x2c:0x3c], image[0x3c:0x4c]
    crc_stored = hdr1[0] | (hdr1[1] << 8)
    return {
        "rec": rec1,
        "crc_stored": crc_stored,
        "crc_ok": crc16(rec1) == crc_stored,
        "copies_ok": rec1 == rec2,
        "headers_ok": hdr1 == hdr2 and hdr1[2] == 16 and hdr1[3] == 16,
    }


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    image = open(sys.argv[1], "rb").read()
    d = decode(image)
    print(f"record: {d['rec'].hex()}")
    print(f"crc stored={d['crc_stored']:04x} ok={d['crc_ok']} "
          f"copies_ok={d['copies_ok']} headers_ok={d['headers_ok']}")
    if len(sys.argv) > 2:
        prev = bytes.fromhex(sys.argv[2])
        changed = [(i, prev[i], d["rec"][i]) for i in range(16)
                   if prev[i] != d["rec"][i]]
        for i, a, b in changed:
            print(f"idx{i}: {a:02x} -> {b:02x}")
        if not changed:
            print("no change")


if __name__ == "__main__":
    main()

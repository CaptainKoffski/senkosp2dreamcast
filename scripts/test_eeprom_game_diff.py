#!/usr/bin/env python3
"""Self-check for eeprom_game_diff.py (T9 recon helper).

Vectors are the three Flycast-BIOS-written game records already in the KB
(docs/kb/phase5-hardware.md §EEPROM game record); the event-area 40-byte hex
is recorded verbatim there, so decode() is tested against a REAL BIOS-written
area, not our own encoder.
"""
import sys
sys.path.insert(0, "scripts")   # run from repo root: python3 scripts/test_...
from eeprom_game_diff import crc16, decode

DEFAULT = bytes.fromhex("23511703000101020200460096004600")
EVENT   = bytes.fromhex("23511703010101020200460096004600")
EASY    = bytes.fromhex("23511703000100020200780096006e00")

assert crc16(DEFAULT) == 0x1e1c
assert crc16(EVENT)   == 0x544f
assert crc16(EASY)    == 0x6808

# Real BIOS-written area (docs/kb/phase5-hardware.md, event bake): headers
# [crc_lo crc_hi 0x10 0x10] x2, then the record twice.
area = bytes.fromhex(
    "4f5410104f5410102351170301010102020046009600460023511703010101020200460096004600")
img = bytes(0x24) + area + bytes(128 - 0x24 - 40)   # pad to a 128-B image
d = decode(img)
assert d["rec"] == EVENT
assert d["crc_stored"] == 0x544f
assert d["crc_ok"] and d["copies_ok"] and d["headers_ok"]

# Corrupt one record byte: crc_ok and copies_ok must both trip.
bad = bytearray(img); bad[0x2c] ^= 0xff
d = decode(bytes(bad))
assert not d["crc_ok"] and not d["copies_ok"]

print("test_eeprom_game_diff OK")

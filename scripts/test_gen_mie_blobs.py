#!/usr/bin/env python3
"""Self-check for gen_mie_blobs.py. Run from repo root:
    python3 scripts/test_gen_mie_blobs.py
Always-on checks use synthetic inputs and KB vectors. The oracle check
(generator == capture-based extract_mie_blobs.py, byte-for-byte) runs only
when senkosp.dat AND captures/phase4/pc2.log exist; otherwise it SKIPs.
Spec: docs/superpowers/specs/2026-10-04-mie-blobs-generator-design.md
"""
import os
import re
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import gen_mie_blobs as g      # noqa: E402
import menu_def                # noqa: E402
from eeprom_game_diff import crc16   # noqa: E402

EVENT_REC = bytes.fromhex("23511703010101020200460096004600")
# Real BIOS-written Event-mode game area (docs/kb/phase5-hardware.md, event
# bake; same vector as scripts/test_eeprom_game_diff.py) -- not our encoder.
EVENT_AREA = bytes.fromhex("4f5410104f541010" "23511703010101020200460096004600"
                           "23511703010101020200460096004600")


def parse_c(text):
    """{name: bytes} from a mie_blobs.c, in file order."""
    return {m.group(1): bytes(int(x, 16) for x in re.findall(r"0x([0-9a-f]{2})", m.group(2)))
            for m in re.finditer(r"const unsigned char (\w+)\[\] = \{([^}]*)\}", text)}


def synth_header(game_id=b"TEST", coin=bytes(16), cabinet=0x02, vertical=1):
    h = bytearray(0x500)
    h[0:5] = b"NAOMI"
    h[0x134:0x138] = game_id
    h[0x1E0:0x1F0] = coin
    h[0x429], h[0x42B] = cabinet, vertical
    return bytes(h)


def must_exit(fn, *args):
    try:
        fn(*args)
    except SystemExit as e:
        return str(e.code)
    raise AssertionError(f"{fn.__name__}{args!r} did not exit")


def test_protocol_frames():
    assert set(g.PROTOCOL) | {"mie_sub03"} == set(g.ORDER) and len(g.ORDER) == 15
    for name, b in g.PROTOCOL.items():
        assert b[:3] == b"\x87\x00\x20", name
        if b[26:27] == b"\xe0":                     # JVS data frame
            words = b[3]
            n = b[0x1c]                             # JVS length byte
            assert b[0x1c + n] == sum(b[0x1b:0x1c + n]) & 0xFF, f"{name} checksum"
            data_len = len(b) - (8 if name == "mie_sub33" else 0)
            assert data_len == 4 * words, f"{name}: {data_len} != 4*{words} (dword_length)"
        else:                                       # plain MIE reply
            assert len(b) == 4 + 4 * b[3], f"{name}: len {len(b)} vs {b[3]} words"
    assert g.PROTOCOL["mie_jvs10"][31:31 + len(g.BOARD_ID)] == g.BOARD_ID


def test_sub33_idle_identity():
    """shims/src/main.c mie_poll rebuilds each poll from mie_sub33: player
    words 0x20..0x23 := live pads, checksum 0x3a := sum(0x1b..0x39). With
    idle pads that transform must be the identity (extract_mie_blobs.py
    rebuild_sub33 asserted the same on the capture)."""
    out = g.PROTOCOL["mie_sub33"]
    built = bytearray(out)
    built[0x20:0x24] = bytes(4)
    built[0x3a] = sum(built[0x1b:0x3a]) & 0xFF
    assert bytes(built) == out
    assert out[0x1a] == 0xE0 and 0x1c + out[0x1c] == 0x3a
    assert out[-8:] == g.PROTOCOL["mie_sub17"]


def test_system_bios_defaults():
    s = g.system_section(synth_header(), 27)
    body = b"\x10TEST\x09\x10\x1a\x01\x01\x01\x00\x11\x11\x11\x11"
    assert s[2:18] == body, s[2:18].hex()
    assert s[0:2] == crc16(body).to_bytes(2, "little")
    assert s[18:36] == s[0:18]
    # vertical=2 sets bit 0 of byte 2 (configure_naomi_eeprom)
    assert g.system_section(synth_header(vertical=2), 27)[2] == 0x11


def test_system_rom_defaults():
    coin = bytes([1, 1, 1, 5, 2, 3, 4, 6, 1, 2, 3, 4, 5, 6, 7, 8])
    s = g.system_section(synth_header(coin=coin, cabinet=0x0C, vertical=0), 1)
    # b2 = (1&1)|0x10; b8 = 4P 0x30 | individual chute 1; b9 = setting 1 - 1;
    # b10..12 = max(coin6,1), max(coin4,1), max(coin5,1); b13 = coin7;
    # b14..17 = coin8|coin9<<4 ...
    assert s[2:18] == bytes([0x11]) + b"TEST" + bytes(
        [0x09, 0x31, 0x00, 4, 2, 3, 6, 0x21, 0x43, 0x65, 0x87]), s[2:18].hex()


def test_game_area_matches_bios_written():
    assert g.game_area(EVENT_REC) == EVENT_AREA


def test_sub03_layout():
    b = g.sub03(synth_header(), EVENT_REC, 27)
    assert len(b) == 132 and b[:4] == bytes.fromhex("87002020")
    assert b[4 + 0x24:4 + 0x4C] == EVENT_AREA and b[4 + 0x4C:] == bytes(52)


if __name__ == "__main__":
    for fn in (test_protocol_frames, test_sub33_idle_identity, test_system_bios_defaults,
               test_system_rom_defaults, test_game_area_matches_bios_written,
               test_sub03_layout):
        fn()
    print("test_gen_mie_blobs OK")

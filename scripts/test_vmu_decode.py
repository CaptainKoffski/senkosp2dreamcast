#!/usr/bin/env python3
"""Self-check for scripts/vmu_decode.py (the VMU save-file decoder the emulator
legs use). Run from repo root:  python3 scripts/test_vmu_decode.py
"""
import contextlib
import io
import os
import struct
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import menu_def as M    # noqa: E402
from vmu_decode import crc16ccitt, decode_payload, find_file, main, parse_vms    # noqa: E402


def test_crc16_xmodem_vector():
    assert crc16ccitt(b"123456789", 0) == 0x31C3        # CRC-16/XMODEM check value (same algorithm as KOS net_crc16ccitt: poly 0x1021, init 0, unreflected)


def test_decode_payload_names():
    rec = bytes.fromhex(M.DEFAULT_RECORD); rec = rec[:6] + bytes([0x02]) + rec[7:]      # GAME DIFFICULTY idx 6 -> HARD
    lib = bytearray(116); ids = [M.FUNC_WORDS.index(M.CUSTOM_DEMO[b]) for b in M.PAD_BUTTONS]
    lib[0:6] = ids; lib[96] = 1; lib[112] = 2                                           # pad slot 0 used; P1 pad sel = CTL_N_STOCK[0] (2)
    d = decode_payload(b"SKSP" + bytes([1, 0, 0, 0]) + rec + bytes(lib))
    assert d["version"] == 1 and d["settings"]["GAME DIFFICULTY"] == "HARD"
    assert d["pad"]["slots"][0] == dict(M.CUSTOM_DEMO) and d["pad"]["sel"] == ["CUSTOM 1", "TOURNAMENT"]


def make_card(payload):
    """Synthetic 256-block card: dir chain 253 -> 252 (entry in the 2nd block), file chain 10 -> 5
    (out of order), VMS with 1 icon. Layout per vmu_decode.py's header. Returns (image, file blob)."""
    img = bytearray(256 * 512)
    img[255 * 512:255 * 512 + 16] = b"\x55" * 16
    struct.pack_into("<6H", img, 255 * 512 + 0x46, 254, 1, 253, 2, 0, 200)          # fat_loc fat_size dir_loc dir_size icon_shape blk_cnt
    fat = {253: 252, 252: 0xFFFA, 10: 5, 5: 0xFFFA}
    for b in range(256):
        struct.pack_into("<H", img, 254 * 512 + 2 * b, fat.get(b, 0xFFFC))
    vms = bytearray(128 + 512 + len(payload))
    vms[0:14] = b"SENKO NO RONDE"; struct.pack_into("<HHHHI", vms, 64, 1, 0, 0, 0, len(payload))
    vms[640:] = payload
    struct.pack_into("<H", vms, 70, crc16ccitt(bytes(vms), 0))                      # crc field was zero while summing
    blob = bytes(vms) + bytes(1024 - len(vms))
    img[10 * 512:11 * 512], img[5 * 512:6 * 512] = blob[:512], blob[512:]
    struct.pack_into("<BBH12s", img, 252 * 512 + 32, 0x33, 0, 10, b"SENKOSP_SYS\0")  # dirent #1 of block 252
    struct.pack_into("<HH", img, 252 * 512 + 32 + 24, 2, 0)
    return bytes(img), blob


def test_fat_chain_and_crc():
    payload = bytes(range(140))
    img, blob = make_card(payload)
    f = find_file(img, "SENKOSP_SYS")
    assert f == blob
    p = parse_vms(f)
    assert p["crc_ok"] and p["data_len"] == 140 and p["payload"] == payload and p["desc_short"] == "SENKO NO RONDE"
    bad = bytearray(f); bad[700] ^= 1
    assert not parse_vms(bytes(bad))["crc_ok"]
    assert find_file(img, "NOPE") is None


def test_cli_exit_codes():
    """0 = file ok; 1 = no SENKOSP_SYS / unreadable; 3 = file there but undecodable (the canary relies on != 1)."""
    rec = bytes.fromhex(M.DEFAULT_RECORD)
    good = b"SKSP" + bytes([1, 0, 0, 0]) + rec + bytes(116)
    with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
        def run(img):
            path = os.path.join(d, "c.bin"); open(path, "wb").write(img)
            return main(["vmu_decode.py", path])
        assert run(make_card(good)[0]) == 0
        assert run(make_card(bytes(range(140)))[0]) == 3          # CRC ok, not an SKSP payload
        assert run(bytes(256 * 512)) == 1                         # unformatted card: no root
        assert run(bytes(1000)) == 1                              # not a card image
        img = bytearray(make_card(good)[0]); img[255 * 512 + 0x46] = 0xFF; img[255 * 512 + 0x47] = 0xFF   # fat_loc past the image
        assert run(bytes(img)) == 1


if __name__ == "__main__":
    test_crc16_xmodem_vector()
    test_decode_payload_names()
    test_fat_chain_and_crc()
    test_cli_exit_codes()
    print("test_vmu_decode: PASS")

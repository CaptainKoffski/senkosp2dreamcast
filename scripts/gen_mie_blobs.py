#!/usr/bin/env python3
"""Generate shims/build/mie_blobs.c -- the 15 MIE reply blobs the shim
serves -- without a capture.
Spec: docs/superpowers/specs/2026-10-04-mie-blobs-generator-design.md

Fourteen blobs are output of Flycast's emulated MIE + JVS I/O board, committed
below as constants with their emitter cited
(../flycast4naomi2dreamcast/core/hw/maple/maple_jvs.cpp); JVS replies are
stored as payload only and framed by jvs_blob(). mie_sub03 (EEPROM read) is
computed: system section from the builder's own senkosp.dat header (port of
Flycast initEeprom + configure_naomi_eeprom, core/hw/naomi/
naomi_flashrom.cpp:144-235) plus the port's coin setting, game area from
menu_def.DEFAULT_RECORD (the layout loader/naomi_crc.c:20-31 pokes at boot).
The output carries the ROM's 4-char game ID: generated, gitignored, never
committed.

Oracle: scripts/extract_mie_blobs.py (capture-based, dev-only) -- compared
byte-for-byte by scripts/test_gen_mie_blobs.py when a capture exists.

Usage: python3 scripts/gen_mie_blobs.py [--dat senkosp.dat] [--out shims/build]
"""
import argparse
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
from eeprom_game_diff import crc16      # noqa: E402  (vector-tested, test_eeprom_game_diff.py)
import menu_def                          # noqa: E402  (port defaults, single source)

# Emission order = the extractor's WANT order (consumer contract: symbol
# names + order are what shims/src/main.c and build_patch_table.py see).
ORDER = ("mie_sub01", "mie_sub03", "mie_sub13", "mie_sub17", "mie_sub21",
         "mie_sub31", "mie_sub33", "mie_86empty", "mie_jvsf1", "mie_jvs10",
         "mie_jvs11", "mie_jvs12", "mie_jvs13", "mie_jvs14", "mie_jvsdflt")

# receive_jvs_messages (maple_jvs.cpp:1716-1754), after the 4-byte reply
# header: w8(0x16) w8(ff)x3 | w32(0xffffff00) | w32(0) w32(0) | w8(0)
# w8(channel 0) w8(sense 0x8e) -- 19 bytes; header + these = headerLength 23.
JVS_WRAP = bytes.fromhex("16ffffff" "00ffffff" "00000000" "00000000" "00008e")


def jvs_blob(body):
    """One JVS data-frame MIE reply. `body` = the JVS frame between the E0
    sync and the checksum: [dest 00][length][status][report][data...].
    Receive-buffer entry [node 01][status 00][frame length]
    (send_jvs_message, maple_jvs.cpp:1673-1677); checksum = sum of the bytes
    after the sync (:2487-2491); padded to Flycast's dword_length words
    (:1719) -- which declares one word more than the bytes after the header,
    so len(blob) == 4 * words, not 4 + 4 * words."""
    frame = b"\xe0" + body + bytes([sum(body) & 0xFF])
    recv = bytes([0x01, 0x00, len(frame)]) + frame
    words = (len(recv) + 23 - 1) // 4 + 1
    out = bytes([0x87, 0x00, 0x20, words]) + JVS_WRAP + recv
    return out + bytes(words * 4 - len(out))


BOARD_ID = b"SEGA ENTERPRISES,LTD.;I/O BD JVS;837-13551 ;Ver1.00;98/10"   # get_id(), :1105

# reply(MDRS_JVSReply=0x87, words) writes 87 00 20 <words> (BaseMIE::reply,
# maple_jvs.cpp:1283-1289); line refs below are handle_86_subcommand / the
# JVS command switch in that file.
SUB17_ACK = bytes.fromhex("87002001" "18008e00")   # 0x17: 18 <chan> 8e 00, :1831-1838
PROTOCOL = {
    "mie_sub01": bytes.fromhex("87002001" "02000000"),       # ready ack, :1972-1977
    "mie_sub13": bytes.fromhex("87002001" "14000800"),       # sub+1, 0, len(7)+1, 0, :1804-1815
    "mie_sub17": SUB17_ACK,
    "mie_sub21": bytes.fromhex("87002001" "18008e00"),       # 18 <chan> sense 00, :1851-1858
    "mie_sub31": bytes.fromhex("87002005" "32ffffff" "00fff9ff") + bytes(12),   # DIP, :1944-1966
    # 0x15 poll, has-data variant: reply to the game's stored repeat request
    # (status 01; switches: report 01, test 00, P1/P2 00 00; coins: report 01,
    # 2 slots 0000; analog: report 01, 8 ch centred 0x8000), then the 0x17-style
    # ack frame (:1889-1894). shims/src/main.c mie_poll rebuilds every poll
    # from this frame (player words 0x20..0x23, checksum 0x3a).
    "mie_sub33": jvs_blob(bytes.fromhex("001e01" "010000000000" "0100000000"
                                        "01" + "8000" * 8)) + SUB17_ACK,
    "mie_86empty": bytes.fromhex("87002000"),                # empty 0x86, :1762-1764
    "mie_jvsf1": jvs_blob(bytes.fromhex("0004010105")),      # F1 set address: 01 01 05(?), :2101-2104
    "mie_jvs10": jvs_blob(bytes.fromhex("003d0101") + BOARD_ID + b"\x00"),   # read ID, :2108-2114
    "mie_jvs11": jvs_blob(bytes.fromhex("0004010111")),      # cmd format rev 1.1, :2116-2120
    "mie_jvs12": jvs_blob(bytes.fromhex("0004010120")),      # JVS rev 2.0, :2122-2126
    "mie_jvs13": jvs_blob(bytes.fromhex("0004010110")),      # comm rev 1.0, :2128-2132
    # slave features: 01 digital (2 players, 13 sw) | 02 coins (2) | 03 analog
    # (8 ch, 16 bit) | 12 gp output (6) | 00 end, :2134-2180
    "mie_jvs14": jvs_blob(bytes.fromhex("001401" "01" "01020d00" "02020000"
                                        "03081000" "12060000" "00")),
    "mie_jvsdflt": jvs_blob(bytes.fromhex("0007010100000000")),   # default branch, :2209+
}


def _players_byte(cabinet):
    # cabinet bitmap -> EEPROM[8] b4-5 (naomi_flashrom.cpp:152-161, 211-232)
    return 0x30 if cabinet & 8 else 0x20 if cabinet & 4 else 0x10 if cabinet & 2 else 0


def system_section(header, coin_setting):
    """EEPROM 0x00..0x23: Flycast initEeprom + configure_naomi_eeprom over a
    fresh image (naomi_flashrom.cpp:144-235; RomBootID offsets per
    core/hw/naomi/naomi_cart.h:9-46), then byte 9 := coin_setting - 1 (the
    port's setting; 27 = FREE PLAY, docs/kb/phase4-conversion.md §FREE PLAY).
    write_naomi_eeprom (:116-135) mirrors bytes 2..17 at +18 and keeps both
    CRCs (over 2..17, little-endian) in sync -- done once at the end here."""
    game_id = header[0x134:0x138]
    coin = header[0x1E0:0x1F0]          # coinFlag[0]
    cabinet, vertical = header[0x429], header[0x42B]
    s = bytearray(18)
    s[3:7] = game_id
    s[7] = 9                            # "FIXME 9 or 0x18?" upstream, :151
    s[8] = _players_byte(cabinet)
    if coin[0] == 1:                    # ROM-specific defaults, :163-179
        s[2] = (coin[1] & 1) | 0x10
        if coin[2] == 1:
            s[8] |= 1
        s[9] = (coin[3] - 1) & 0xFF
        s[10], s[11], s[12] = max(coin[6], 1), max(coin[4], 1), max(coin[5], 1)
        s[13] = coin[7]
        for i in range(4):
            s[14 + i] = (coin[8 + 2 * i] | coin[9 + 2 * i] << 4) & 0xFF
    else:                               # BIOS defaults, :180-193
        s[2] = 0x11 if vertical & 2 else 0x10
        s[9:18] = bytes([0, 1, 1, 1, 0, 0x11, 0x11, 0x11, 0x11])
    if vertical == 2:                   # configure_naomi_eeprom, :200-209
        s[2] |= 1
    elif vertical == 1:
        s[2] &= 0xFE
    if cabinet != 0 and cabinet < 0x10 and not cabinet & (1 << (s[8] >> 4)):
        s[8] = _players_byte(cabinet) | (s[8] & 1)      # :211-232
    s[9] = coin_setting - 1             # the port's setting (menu_def.py)
    s[0:2] = crc16(bytes(s[2:18])).to_bytes(2, "little")
    return bytes(s) * 2


def game_area(record):
    """EEPROM 0x24..0x4B: [crc_lo crc_hi 0x10 0x10] x2, then the record x2 --
    the exact layout the loader pokes at boot (loader/naomi_crc.c:20-31)."""
    hdr = crc16(record).to_bytes(2, "little") + b"\x10\x10"
    return hdr * 2 + record * 2


def sub03(header, record, coin_setting):
    """EEPROM read reply: 87 00 20 20 (32 words) + the 128-byte image
    (maple_jvs.cpp:1931-1940); zero tail past the game area."""
    image = system_section(header, coin_setting) + game_area(record)
    return bytes.fromhex("87002020") + image + bytes(128 - len(image))


def check_inputs(header, record, coin_setting):
    """Fail loudly on inputs that would bake a wrong image."""
    if header[:5] != b"NAOMI":
        sys.exit("gen_mie_blobs: senkosp.dat header has no NAOMI magic -- "
                 "not a flat decrypted cart image (README step 1)")
    gid = header[0x134:0x138]
    if not all(0x20 <= c < 0x7F for c in gid):
        sys.exit(f"gen_mie_blobs: game ID {gid!r} not printable -- encrypted "
                 "or foreign header (naomi_cart.h:43)")
    if len(record) != 16:
        sys.exit(f"gen_mie_blobs: menu_def.DEFAULT_RECORD is {len(record)} B, need 16")
    if not 1 <= coin_setting <= 28:
        sys.exit(f"gen_mie_blobs: SYSTEM_COIN_SETTING {coin_setting} outside 1..28")


def all_blobs(header, record, coin_setting):
    check_inputs(header, record, coin_setting)
    blobs = dict(PROTOCOL, mie_sub03=sub03(header, record, coin_setting))
    return {name: blobs[name] for name in ORDER}


def render_c(blobs):
    out = ["/* GENERATED by scripts/gen_mie_blobs.py -- do not edit, do not\n"
           " * commit (mie_sub03 carries the ROM's game ID). */\n"]
    for name, b in blobs.items():
        rows = ",\n    ".join(",".join(f"0x{x:02x}" for x in b[i:i + 12])
                              for i in range(0, len(b), 12))
        out.append(f"const unsigned char {name}[] = {{\n    {rows}\n}};\n"
                   f"const unsigned int {name}_len = {len(b)};\n")
    return "".join(out)


def cart_size():
    iface = open(os.path.join(REPO, "shims/include/shim_iface.h")).read()
    return int(re.search(r"#define\s+CART_SIZE\s+(0x[0-9a-fA-F]+)", iface).group(1), 16)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dat", default=os.path.join(REPO, "senkosp.dat"))
    ap.add_argument("--out", default=os.path.join(REPO, "shims/build"))
    a = ap.parse_args(argv)
    if not os.path.exists(a.dat):
        sys.exit(f"gen_mie_blobs: {a.dat} missing -- README step 1 "
                 "(generate it from your own romset)")
    if os.path.getsize(a.dat) != cart_size():
        sys.exit(f"gen_mie_blobs: {a.dat} is {os.path.getsize(a.dat)} B, "
                 f"expected CART_SIZE {cart_size()} (shim_iface.h)")
    with open(a.dat, "rb") as f:
        header = f.read(0x500)
    try:
        record = bytes.fromhex(menu_def.DEFAULT_RECORD)
    except ValueError:
        sys.exit("gen_mie_blobs: menu_def.DEFAULT_RECORD is not hex")
    blobs = all_blobs(header, record, menu_def.SYSTEM_COIN_SETTING)
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, "mie_blobs.c")
    with open(path, "w") as f:
        f.write(render_c(blobs))
    print(f"gen_mie_blobs: {len(blobs)} blobs -> {os.path.relpath(path, REPO)} "
          f"(EEPROM sys {blobs['mie_sub03'][4:22].hex()})")


if __name__ == "__main__":
    main()

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

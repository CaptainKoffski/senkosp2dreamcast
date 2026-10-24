#!/usr/bin/env python3
"""Self-check: loader/menu_sheet.pal8 (the shipped sprite-sheet blob: 256 x
RGB565-LE palette then SHEET_W*SHEET_H 8bpp indices) decodes to exactly
loader/menu_sheet.png (the decoded preview). Run from repo root:
    python3 scripts/test_gen_menu_sheet.py
"""
import os
import struct
import sys

from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import gen_menu_assets as g    # noqa: E402
import menu_def as M           # noqa: E402


def test_pal8_matches_png():
    blob = open(os.path.join(REPO, "loader", "menu_sheet.pal8"), "rb").read()
    assert len(blob) == 512 + M.SHEET_W * M.SHEET_H
    pal = [struct.unpack_from("<H", blob, 2 * i)[0] for i in range(256)]
    png = Image.open(os.path.join(REPO, "loader", "menu_sheet.png")).convert("RGB")
    assert png.size == (M.SHEET_W, M.SHEET_H)
    for y in range(M.SHEET_H):                 # every pixel
        for x in range(M.SHEET_W):
            assert pal[blob[512 + y * M.SHEET_W + x]] == g.rgb565(png.getpixel((x, y)))


if __name__ == "__main__":
    test_pal8_matches_png()
    print("test_gen_menu_sheet: PASS")

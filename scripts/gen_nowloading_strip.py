#!/usr/bin/env python3
"""Generate loader/nowloading_strip.bin -- the "NOW LOADING..." mask for the
boot splash (phase 7 T7 round 2; replaces the bfont draw the operator vetoed
on style).

Output: [u16 w][u16 h] little-endian, then w*h bytes of 8-bit coverage
(255 = full text ink). scripts/splash_text.py blends it onto splash.bin at
build time, so the type survives splash.png regeneration.

The strip itself is COMMITTED (it is our own rendering of a system typeface,
nothing BIOS/ROM-derived), so normal builds never need this generator or its
Pillow venv (tools/venv-pil -- docs/kb/tooling.md). Re-run only to change the
text:  tools/venv-pil/bin/python scripts/gen_nowloading_strip.py

Face: Avenir Next Medium (macOS system TTC, face index 5) at 30 px with +7 px
tracking -- the closest system face to the NAOMI logotype's geometric sans
(Futura class; Futura itself is not shipped on this macOS).
"""
import struct
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

TEXT = "NOW LOADING..."
FONT = "/System/Library/Fonts/Avenir Next.ttc"
FACE = 5            # Avenir Next Medium
SIZE = 30
TRACK = 7           # extra px between glyphs

font = ImageFont.truetype(FONT, SIZE, index=FACE)
img = Image.new("L", (800, 80), 0)
d = ImageDraw.Draw(img)
x = 20
for ch in TEXT:
    d.text((x, 20), ch, fill=255, font=font)
    x += d.textlength(ch, font=font) + TRACK
bbox = img.getbbox()
img = img.crop(bbox)
w, h = img.size
out = Path(__file__).resolve().parent.parent / "loader" / "nowloading_strip.bin"
out.write_bytes(struct.pack("<HH", w, h) + img.tobytes())
print(f"wrote {out} ({w}x{h})")

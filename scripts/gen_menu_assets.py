#!/usr/bin/env python3
"""T9 offline asset generator (Pillow -- NOT a build dependency; outputs are
committed). Renders loader/menu_sheet.png (640x768 sprite sheet) and
loader/controls.png (640x480), and emits loader/menu_layout.h with every
sheet rect + dest coordinate + the settings byte tables from menu_def.py.

All art is drawn here (text + flat shapes) -- never pixels from the game
(copyright rule, CLAUDE.md). Rerun after any menu_def.py change:
    python3 scripts/gen_menu_assets.py
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import menu_def as M

FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
assert os.path.exists(FONT_PATH), f"stock macOS font missing: {FONT_PATH}"

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOADER_DIR = os.path.join(REPO, "loader")

BG = (0x10, 0x10, 0x18)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
AMBER = (0xe0, 0xa0, 0x20)
GREY = (0x90, 0x90, 0x90)

F_TOP = ImageFont.truetype(FONT_PATH, 28)      # top-menu labels
F_ROW = ImageFont.truetype(FONT_PATH, 20)      # settings rows/footers/values
F_TITLE = ImageFont.truetype(FONT_PATH, 24)    # titles


def rgb565(rgb):
    r, g, b = rgb
    return (r >> 3) << 11 | (g >> 2) << 5 | b >> 3


class Shelf:
    """Top-left shelf packer: fills a row left-to-right, wraps to a new row
    when a band would overflow the sheet width. Cursor never moves back."""
    def __init__(self, width):
        self.w = width
        self.x = 0
        self.y = 0
        self.row_h = 0

    def place(self, w, h):
        if self.x + w > self.w:
            self.x = 0
            self.y += self.row_h
            self.row_h = 0
        rect = (self.x, self.y, w, h)
        self.x += w
        self.row_h = max(self.row_h, h)
        return rect

    @property
    def bottom(self):
        return self.y + self.row_h


def check_fits(draw, w, h, text, font, margin=16):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    assert tw <= w - margin, \
        f"text {text!r} width {tw}px clips {w}x{h} band (margin {margin})"
    assert th <= h, f"text {text!r} height {th}px clips {w}x{h} band"


def put_centered(draw, rect, text, font, fill):
    x, y, w, h = rect
    draw.text((x + w / 2, y + h / 2), text, font=font, fill=fill, anchor="mm")


def put_left(draw, rect, text, font, fill, pad=10):
    x, y, w, h = rect
    draw.text((x + pad, y + h / 2), text, font=font, fill=fill, anchor="lm")


def fill_rect(draw, rect, color):
    x, y, w, h = rect
    draw.rectangle([x, y, x + w - 1, y + h - 1], fill=color)


def R(rect):
    return "{%d,%d,%d,%d}" % rect


def main():
    rec_bytes = bytes.fromhex(M.DEFAULT_RECORD)
    assert len(rec_bytes) == 16, f"DEFAULT_RECORD not 16 bytes: {M.DEFAULT_RECORD!r}"
    for label, idx, vals, idx2, bytes2 in M.SETTINGS:
        assert rec_bytes[idx] in [b for _, b in vals], \
            f"{label}: default byte {rec_bytes[idx]:#04x} (idx{idx}) not in its value list"
        assert idx2 is None and bytes2 is None, \
            f"{label}: idx2 mechanism not implemented by this recon (T9 has no 2-byte rows)"

    n_settings = len(M.SETTINGS)
    max_values = max(len(vals) for _, _, vals, _, _ in M.SETTINGS)
    assert n_settings * 34 + 96 <= 440, \
        f"{n_settings} rows overflow the settings screen: {n_settings * 34 + 96} > 440"

    # ---- menu_sheet.png ----------------------------------------------
    sheet = Image.new("RGB", (M.SHEET_W, M.SHEET_H), BG)
    draw = ImageDraw.Draw(sheet)
    shelf = Shelf(M.SHEET_W)

    top_label_rects = []
    for item in M.TOP_ITEMS:
        r_norm = shelf.place(320, 36)
        check_fits(draw, 320, 36, item, F_TOP)
        put_centered(draw, r_norm, item, F_TOP, WHITE)
        r_hi = shelf.place(320, 36)
        fill_rect(draw, r_hi, AMBER)
        check_fits(draw, 320, 36, item, F_TOP)
        put_centered(draw, r_hi, item, F_TOP, BLACK)
        top_label_rects.append((r_norm, r_hi))

    top_footer_rect = shelf.place(640, 24)
    check_fits(draw, 640, 24, M.TOP_FOOTER, F_ROW)
    put_centered(draw, top_footer_rect, M.TOP_FOOTER, F_ROW, GREY)

    title_rect = shelf.place(640, 32)
    check_fits(draw, 640, 32, "SETTINGS", F_TITLE)
    put_centered(draw, title_rect, "SETTINGS", F_TITLE, WHITE)

    # Value chips are shared across rows/values that render identical text
    # (e.g. "1".."5" for both point-vs-human and point-vs-cpu, "50".."120"
    # for both round-time rows) -- ponytail: 41 raw (row, value) pairs but
    # only 22 distinct strings; at 288x28 each, 41 unique chips would not
    # fit the fixed 640x768 sheet (41*288*28 alone exceeds the whole canvas
    # area), 22 comfortably does. Dedup by exact label text.
    value_cache = {}

    def get_chip(text):
        if text in value_cache:
            return value_cache[text]
        r = shelf.place(288, 28)
        check_fits(draw, 288, 28, text, F_ROW)
        put_centered(draw, r, text, F_ROW, WHITE)
        value_cache[text] = r
        return r

    set_label_rects = []
    set_value_rects = []
    set_bytes = []
    for label, idx, vals, idx2, bytes2 in M.SETTINGS:
        r_norm = shelf.place(288, 28)
        check_fits(draw, 288, 28, label, F_ROW)
        put_left(draw, r_norm, label, F_ROW, WHITE)
        r_hi = shelf.place(288, 28)
        fill_rect(draw, r_hi, AMBER)
        check_fits(draw, 288, 28, label, F_ROW)
        put_left(draw, r_hi, label, F_ROW, BLACK)
        set_label_rects.append((r_norm, r_hi))

        set_value_rects.append([get_chip(vl) for vl, _ in vals])
        set_bytes.append([vb for _, vb in vals])

    set_footer_rect = shelf.place(640, 24)
    check_fits(draw, 640, 24, M.SET_FOOTER, F_ROW)
    put_centered(draw, set_footer_rect, M.SET_FOOTER, F_ROW, GREY)

    assert shelf.bottom <= M.SHEET_H, \
        f"sheet content {shelf.bottom}px exceeds {M.SHEET_H}px budget"
    # Canvas was allocated at the full 640x768 up front and pre-filled with
    # BG, so the untouched tail below shelf.bottom is already the required
    # #101018 padding -- no separate crop+pad step needed.
    sheet.save(os.path.join(LOADER_DIR, "menu_sheet.png"))

    # ---- controls.png ---------------------------------------------------
    ctrl = Image.new("RGB", (640, 480), BG)
    cd = ImageDraw.Draw(ctrl)
    check_fits(cd, 640, 480, "CONTROLS", F_TITLE)
    cd.text((320, 40), "CONTROLS", font=F_TITLE, fill=WHITE, anchor="mm")
    row_y = 120
    for btn, act in M.CONTROLS_ROWS:
        check_fits(cd, 340 - 120, 34, btn, F_ROW, margin=10)
        check_fits(cd, 640 - 340, 34, act, F_ROW, margin=20)
        cd.text((120, row_y), btn, font=F_ROW, fill=AMBER, anchor="lm")
        cd.text((340, row_y), act, font=F_ROW, fill=WHITE, anchor="lm")
        row_y += 34
    assert row_y <= 440, f"controls rows ({row_y}px) collide with the footer"
    check_fits(cd, 640, 480, "B: BACK", F_ROW)
    cd.text((320, 440), "B: BACK", font=F_ROW, fill=GREY, anchor="mm")
    ctrl.save(os.path.join(LOADER_DIR, "controls.png"))

    # ---- loader/menu_layout.h -------------------------------------------
    top_dest_y = [310, 354, 398]
    lines = [
        "/* GENERATED by scripts/gen_menu_assets.py from scripts/menu_def.py --"
        " do not edit. Committed alongside the PNGs it describes. */",
        "#ifndef MENU_LAYOUT_H",
        "#define MENU_LAYOUT_H",
        "",
        "typedef struct { unsigned short x, y, w, h; } mrect_t;",
        "",
        f"#define MENU_SHEET_W {M.SHEET_W}",
        f"#define MENU_BG_COLOR 0x{rgb565(BG):04x}",
        "",
        "static const mrect_t MENU_TOP_LABEL[3][2] = {",
    ]
    for norm, hi in top_label_rects:
        lines.append(f"  {{{R(norm)}, {R(hi)}}},")
    lines.append("};")
    lines.append("")
    lines.append("static const unsigned short MENU_TOP_DEST[3][2] = {")
    for i, (norm, _) in enumerate(top_label_rects):
        lines.append(f"  {{{(640 - norm[2]) // 2}, {top_dest_y[i]}}},")
    lines.append("};")
    lines.append("")
    lines.append(f"static const mrect_t MENU_TOP_FOOTER = {R(top_footer_rect)};")
    lines.append(f"#define MENU_TOP_FOOTER_X {(640 - top_footer_rect[2]) // 2}")
    lines.append("#define MENU_TOP_FOOTER_Y 452")
    lines.append("")
    lines.append(f"#define MENU_N_SETTINGS {n_settings}")
    lines.append(f"#define MENU_MAX_VALUES {max_values}")
    lines.append("")
    lines.append(f"static const mrect_t MENU_SET_LABEL[{n_settings}][2] = {{")
    for norm, hi in set_label_rects:
        lines.append(f"  {{{R(norm)}, {R(hi)}}},")
    lines.append("};")
    lines.append("")
    zero_rect = "{0,0,0,0}"
    lines.append(f"static const mrect_t MENU_SET_VALUE[{n_settings}][{max_values}] = {{")
    for row_rects in set_value_rects:
        padded = [R(r) for r in row_rects] + [zero_rect] * (max_values - len(row_rects))
        lines.append("  {" + ", ".join(padded) + "},")
    lines.append("};")
    lines.append("")
    lines.append(f"static const unsigned char MENU_SET_NVAL[{n_settings}] = {{"
                  + ", ".join(str(len(r)) for r in set_value_rects) + "};")
    lines.append(f"static const unsigned char MENU_SET_IDX[{n_settings}] = {{"
                  + ", ".join(str(idx) for _, idx, _, _, _ in M.SETTINGS) + "};")
    lines.append(f"static const unsigned char MENU_SET_IDX2[{n_settings}] = {{"
                  + ", ".join("0xff" for _ in M.SETTINGS) + "};   /* unused: no 2-byte rows in this recon */")
    lines.append("")
    lines.append(f"static const unsigned char MENU_SET_BYTE[{n_settings}][{max_values}] = {{")
    for byte_row in set_bytes:
        padded = [f"0x{b:02x}" for b in byte_row] + ["0"] * (max_values - len(byte_row))
        lines.append("  {" + ", ".join(padded) + "},")
    lines.append("};")
    lines.append("")
    lines.append(f"static const unsigned char MENU_SET_BYTE2[{n_settings}][{max_values}] = {{"
                  "   /* unused: no 2-byte rows in this recon */")
    for _ in M.SETTINGS:
        lines.append("  {" + ", ".join(["0"] * max_values) + "},")
    lines.append("};")
    lines.append("")
    lines.append("#define MENU_SET_LABEL_X 48")
    lines.append("#define MENU_SET_VALUE_X 344")
    lines.append("#define MENU_SET_ROW_Y(i) (96 + (i) * 34)")
    lines.append("")
    lines.append(f"static const mrect_t MENU_SET_TITLE = {R(title_rect)};")
    lines.append(f"#define MENU_SET_TITLE_X {(640 - title_rect[2]) // 2}")
    lines.append("#define MENU_SET_TITLE_Y 40")
    lines.append("")
    lines.append(f"static const mrect_t MENU_SET_FOOTER = {R(set_footer_rect)};")
    lines.append(f"#define MENU_SET_FOOTER_X {(640 - set_footer_rect[2]) // 2}")
    lines.append("#define MENU_SET_FOOTER_Y 452")
    lines.append("")
    lines.append("#define MENU_DEFAULT_RECORD {" + ", ".join(f"0x{b:02x}" for b in rec_bytes) + "}")
    lines.append("")
    lines.append("#endif /* MENU_LAYOUT_H */")

    with open(os.path.join(LOADER_DIR, "menu_layout.h"), "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"gen_menu_assets: sheet {shelf.bottom}/{M.SHEET_H}px used "
          f"({100 * shelf.bottom / M.SHEET_H:.1f}% vertical), "
          f"{n_settings} settings rows, {len(value_cache)} unique value chips, "
          f"controls.png {len(M.CONTROLS_ROWS)} rows")


if __name__ == "__main__":
    main()

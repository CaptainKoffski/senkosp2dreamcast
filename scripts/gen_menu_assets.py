#!/usr/bin/env python3
"""T9 offline asset generator (Pillow -- NOT a build dependency; outputs are
committed). Renders loader/menu_sheet.png (640x1024 sprite sheet) and the two
controls pages, loader/controls_pad.png / controls_stick.png (640x480), and
emits loader/menu_layout.h (sheet rects + dest coordinates + the settings byte
tables) and shims/src/layouts.h (button->JVS tables), both from menu_def.py.

All art is drawn here (text + flat shapes) or derived from the operator's own
controller diagrams -- never pixels from the game (copyright rule, CLAUDE.md).
Rerun after any menu_def.py change, then VIEW build/preview_*.png: those
composite the label chips onto the pages exactly as the C code blits them, and
are the only check that an anchor actually lands beside its button.
    python3 scripts/gen_menu_assets.py
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import menu_def as M

FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
assert os.path.exists(FONT_PATH), f"stock macOS font missing: {FONT_PATH}"

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOADER_DIR = os.path.join(REPO, "loader")

BG = (224, 224, 224)          # T16 round 2: soft gray -- operator found the
                              # splash-white (248) menu bg too bright on a TV.
                              # No longer matches splash.png's 248 bg; the
                              # splash->menu transition shows a small shade
                              # step (accepted). Exactly representable in
                              # RGB565 (224>>3<<3 == 224).
FG = (0x10, 0x10, 0x18)       # dark navy text (the pre-white-bg BG color)
BLACK = (0, 0, 0)
AMBER = (0xe0, 0xa0, 0x20)    # highlight bands (black text on top)
AMBER_TXT = (0xa8, 0x70, 0x00)  # amber as TEXT needs more contrast on white
GREY = (0x70, 0x70, 0x70)

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


CHIP_W, CHIP_H = 160, 24        # CTL_WORD label-chip cell
CTL_ROW_LABEL_X = 48
CTL_ROW_VALUE_X = 344


def CTL_ROW_Y(i):
    return 352 + i * 34


def box_of(rect):
    x, y, w, h = rect
    return (x, y, x + w, y + h)


# Controls pages. Per page: the paste x of the scaled art ("center" or a
# literal), the baked identity tags the art itself does not carry, and the
# leader polylines for chips the art leaves no adjacent room for. Tag/lead
# coordinates are page space, like menu_def's anchors, and are art-only --
# the C code never sees them, so they live here and not in menu_def.
#   pad:   face view, no triggers visible -> L/R TRIGGER tags in the shoulder
#          corners, with the LTRIG/RTRIG chips directly under them.
#   stick: Start is an unlabeled yellow circle -> START tag left of it; X/Y/B
#          are interior cluster buttons -> elbows out to their chips, routed
#          between the art's own letters (never across one).
PAD_PAGE = dict(art_x="center",
                tags=[(118, 186, "MOVE"), (320, 274, "START"),
                      (92, 20, "L TRIGGER"),
                      (546, 20, "R TRIGGER")],
                leads=[])
STICK_PAGE = dict(art_x=4,
                  tags=[(98, 88, "MOVE"), (240, 33, "START")],
                  leads=[[(331, 74), (331, 42), (440, 42)],      # Y
                         [(331, 157), (331, 190), (440, 190)],   # B
                         [(261, 118), (170, 118), (170, 205)]])  # X


def clean_art(im):
    """Flatten the operator art to schematic colors: a 3x median kills the
    JPEG ringing the stick art came over-compressed with, then an octree
    palette (32, no dither) snaps the result to flat fills. Octree, not
    MEDIANCUT: median-cut allocates the palette by pixel population, and the
    pad's buttons are small enough that it merged red A / blue B into the
    body gray (viewed; that is what killed the first pass)."""
    return (im.filter(ImageFilter.MedianFilter(3))
              .quantize(colors=32, method=Image.FASTOCTREE,
                        dither=Image.Dither.NONE)
              .convert("RGB"))


def tag(draw, x, y, text):
    """Baked identity label: FG text on its own BG plate. The plate is what
    makes it readable on the stick's dark panel (bare FG text on that gray
    is ~2:1 contrast)."""
    check_fits(draw, 640, 24, text, F_ROW)
    b = draw.textbbox((x, y), text, font=F_ROW, anchor="mm")
    draw.rectangle([b[0] - 6, y - 12, b[2] + 6, y + 12], fill=BG)
    draw.text((x, y), text, font=F_ROW, fill=FG, anchor="mm")


def build_page(name, spec):
    """640x480 controls page: operator art cleaned, autocropped, scaled into
    the art region (y 8..338, above the selector rows), tinted + flood-filled
    onto the page BG, then the baked tags / leader lines / footer."""
    art = os.path.join(LOADER_DIR, f"{name}_diagram.png")
    assert os.path.exists(art), f"missing {art} (operator-provided art)"
    src = clean_art(Image.open(art).convert("RGB"))
    # autocrop the art's own margin. The threshold is relative to the corner
    # level, not a fixed near-white: the stick art's background is light grey
    # (232), so a fixed "darker than 245" test crops nothing.
    g = src.convert("L")
    lvl = sorted(g.getpixel(p) for p in [(2, 2), (src.width - 3, 2),
                                         (2, src.height - 3),
                                         (src.width - 3, src.height - 3)])[2]
    bbox = g.point(lambda p: 255 if abs(p - lvl) > 14 else 0).getbbox()
    assert bbox, f"{name}: autocrop found no content"
    pad = 12
    src = src.crop((max(bbox[0] - pad, 0), max(bbox[1] - pad, 0),
                    min(bbox[2] + pad, src.width),
                    min(bbox[3] + pad, src.height)))
    scale = min(620 / src.width, 330 / src.height)
    dw, dh = round(src.width * scale), round(src.height * scale)
    img = src.resize((dw, dh), Image.LANCZOS)
    # tint so the art's own background lands exactly on the page BG: sample
    # the bg level from the corners (inside the autocrop pad, pure bg by
    # construction) and scale all pixels by BG/bg_level
    g = img.convert("L")
    bg_level = sorted(g.getpixel(p) for p in
                      [(2, 2), (dw - 3, 2), (2, dh - 3), (dw - 3, dh - 3)])[2]
    img = img.point(lambda p: min(255, p * BG[0] // bg_level))
    # flatten the outer bg region to exactly BG (the tint gets it close; the
    # art bg's soft gradient would still show as a faint block edge on the
    # page without this). Interior lights (VMU window, pad body) are enclosed
    # by darker outlines, so the fill cannot reach them. thresh is PIL's
    # summed-channel difference: 60 = ~20/channel, enough for the bg's +-8
    # gradient, far below the outlines. Two-pass sentinel fill: floodfill()
    # no-ops when the seed already sits within thresh of the target value
    # (our corners == BG by the tint above), so fill to a sentinel first,
    # then sentinel -> BG.
    SENTINEL = (255, 0, 255)
    for corner in [(2, 2), (dw - 3, 2), (2, dh - 3), (dw - 3, dh - 3)]:
        ImageDraw.floodfill(img, corner, SENTINEL, thresh=60)
        ImageDraw.floodfill(img, corner, BG, thresh=60)
    page = Image.new("RGB", (640, 480), BG)
    ox = (640 - dw) // 2 if spec["art_x"] == "center" else spec["art_x"]
    assert 0 <= ox and ox + dw <= 640 and dh <= 330, \
        f"{name}: art {dw}x{dh} at x{ox} leaves the art region"
    page.paste(img, (ox, 8))
    d = ImageDraw.Draw(page)
    for poly in spec["leads"]:
        d.line(poly, fill=FG, width=2, joint="curve")
    for x, y, text in spec["tags"]:
        tag(d, x, y, text)
    check_fits(d, 640, 24, M.CTL_FOOTER, F_ROW)
    d.text((320, 464), M.CTL_FOOTER, font=F_ROW, fill=GREY, anchor="mm")
    print(f"gen_menu_assets: controls_{name}.png art {dw}x{dh} at x{ox}")
    return page


def emit_layouts_h():
    # self-checks: a pad layout that can't reach every game function is a
    # shipping bug, not a preference (stick OverDrive gap was exactly this)
    playable = {"MAIN", "SUB", "BARRAGE", "ACTION", "OVERDRIVE"}
    for name, lay in M.PAD_LAYOUTS:
        assert set(lay) == set(M.PAD_BUTTONS), f"{name}: buttons mismatch"
        assert playable <= set(lay.values()), f"{name}: unreachable function"
    assert set(M.STICK_LAYOUT) == set(M.STICK_BUTTONS)
    assert playable <= set(M.STICK_LAYOUT.values()), "stick: unreachable function"
    assert len(M.PAD_BUTTONS) == len(M.STICK_BUTTONS), "tables share JVS_LAYOUT_N"
    for f in list(M.FUNC_JVS) + M.FUNC_WORDS:
        assert f in M.FUNC_WORDS and f in M.FUNC_JVS, f"function list drift: {f}"
    # layout-id order is load-bearing in four places (LAYOUT_* defines below,
    # jvs_pick_layout, CTL_PAD_VALUES, preview labels) -- pin PAD_LAYOUTS and
    # CTL_PAD_VALUES to the same order so a reorder in one can't silently
    # desync from the others.
    assert [n for n, _ in M.PAD_LAYOUTS] == M.CTL_PAD_VALUES, \
        "PAD_LAYOUTS order must match CTL_PAD_VALUES (layout id is positional)"

    n = len(M.PAD_BUTTONS)
    L = [
        "/* GENERATED by scripts/gen_menu_assets.py from scripts/menu_def.py --",
        " * do not edit. Consumed by shims/src/jvs.c, which #includes it AFTER",
        " * its CONT_* / JVS_* defines (the tables reference them). Committed,",
        " * same rule as loader/menu_layout.h. */",
        "#ifndef LAYOUTS_H",
        "#define LAYOUTS_H",
        "",
        "#define LAYOUT_PAD_TOURNAMENT 0",
        "#define LAYOUT_PAD_CLASSIC    1",
        "#define LAYOUT_STICK          2",
        f"#define JVS_LAYOUT_N {n}",
        "",
        "typedef struct { unsigned dc, jvs; } jvs_map_t;",
        "",
        f"static const jvs_map_t JVS_LAYOUT_PAD[2][{n}] = {{",
    ]
    for name, lay in M.PAD_LAYOUTS:
        cells = ", ".join("{CONT_%s, %s}" % (b, M.FUNC_JVS[lay[b]])
                          for b in M.PAD_BUTTONS)
        L.append(f"  {{ {cells} }},   /* {name} */")
    L += ["};", "", f"static const jvs_map_t JVS_LAYOUT_STICK[{n}] = {{"]
    for b in M.STICK_BUTTONS:
        L.append("  {CONT_%s, %s}," % (b, M.FUNC_JVS[M.STICK_LAYOUT[b]]))
    L += ["};", "", "#endif /* LAYOUTS_H */"]
    with open(os.path.join(REPO, "shims", "src", "layouts.h"), "w") as f:
        f.write("\n".join(L) + "\n")


def main():
    emit_layouts_h()
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
        put_centered(draw, r_norm, item, F_TOP, FG)
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
    put_centered(draw, title_rect, "SETTINGS", F_TITLE, FG)

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
        put_centered(draw, r, text, F_ROW, FG)
        value_cache[text] = r
        return r

    set_label_rects = []
    set_value_rects = []
    set_bytes = []
    for label, idx, vals, idx2, bytes2 in M.SETTINGS:
        r_norm = shelf.place(288, 28)
        check_fits(draw, 288, 28, label, F_ROW)
        put_left(draw, r_norm, label, F_ROW, FG)
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

    # ---- CONTROLS sheet cells (same shelf) -------------------------------
    ctl_word_rects = []
    for word in M.FUNC_WORDS:
        r = shelf.place(160, 24)
        check_fits(draw, 160, 24, word, F_ROW)
        put_centered(draw, r, word, F_ROW, FG)
        ctl_word_rects.append(r)

    ctl_row_rects = []
    for item in M.CTL_ROW_ITEMS:
        r_norm = shelf.place(288, 28)
        check_fits(draw, 288, 28, item, F_ROW)
        put_left(draw, r_norm, item, F_ROW, FG)
        r_hi = shelf.place(288, 28)
        fill_rect(draw, r_hi, AMBER)
        check_fits(draw, 288, 28, item, F_ROW)
        put_left(draw, r_hi, item, F_ROW, BLACK)
        ctl_row_rects.append((r_norm, r_hi))

    ctl_pad_value_rects = [get_chip(v) for v in M.CTL_PAD_VALUES]
    ctl_stick_value_rect = get_chip(M.CTL_STICK_VALUE)

    assert shelf.bottom <= M.SHEET_H, \
        f"sheet content {shelf.bottom}px exceeds {M.SHEET_H}px budget"
    # Canvas was allocated at the full sheet size up front and pre-filled with
    # BG, so the untouched tail below shelf.bottom is already the required
    # padding -- no separate crop+pad step needed.
    sheet.save(os.path.join(LOADER_DIR, "menu_sheet.png"))

    # ---- controls_pad.png / controls_stick.png ---------------------------
    pad_page = build_page("pad", PAD_PAGE)
    stick_page = build_page("stick", STICK_PAGE)
    pad_page.save(os.path.join(LOADER_DIR, "controls_pad.png"))
    stick_page.save(os.path.join(LOADER_DIR, "controls_stick.png"))

    # anchor sanity: the chip must stay inside the art region, and two chips
    # on one page must never collide (they are blitted, not blended)
    for page_name, anchors, buttons in [("pad", M.PAD_ANCHORS, M.PAD_BUTTONS),
                                        ("stick", M.STICK_ANCHORS, M.STICK_BUTTONS)]:
        assert set(anchors) == set(buttons), f"{page_name}: anchor/button drift"
        for b in buttons:
            x, y = anchors[b]
            assert 0 <= x <= 640 - CHIP_W, f"{page_name} {b}: anchor x {x} off-page"
            assert 8 <= y <= 340 - CHIP_H, f"{page_name} {b}: anchor y {y} off-art"
            assert (x, y) != (0, 0), f"{page_name} {b}: anchor unmeasured"
        for i, a in enumerate(buttons):
            for b in buttons[i + 1:]:
                ax, ay = anchors[a]
                bx, by = anchors[b]
                assert ax + CHIP_W <= bx or bx + CHIP_W <= ax \
                    or ay + CHIP_H <= by or by + CHIP_H <= ay, \
                    f"{page_name}: {a} and {b} chips overlap"

    # ---- previews (verification discipline: chips composited exactly as
    # the C code blits them, so the anchors are checked against the truth)
    build_dir = os.path.join(REPO, "build")
    os.makedirs(build_dir, exist_ok=True)

    def preview(name, page, anchors, buttons, layout, row_hi, values):
        pv = page.copy()
        for b in buttons:
            pv.paste(sheet.crop(box_of(ctl_word_rects[M.FUNC_WORDS.index(layout[b])])),
                     anchors[b])
        for i, (r_norm, r_hi) in enumerate(ctl_row_rects):
            pv.paste(sheet.crop(box_of(r_hi if i == row_hi else r_norm)),
                     (CTL_ROW_LABEL_X, CTL_ROW_Y(i)))
            pv.paste(sheet.crop(box_of(values[i])), (CTL_ROW_VALUE_X, CTL_ROW_Y(i)))
        pv.save(os.path.join(build_dir, f"preview_{name}.png"))

    for lid, (lname, lay) in enumerate(M.PAD_LAYOUTS):
        # row values as the menu shows them: P1 = this preview's layout,
        # P2 = the other one (so both chips are eyeballed), stick fixed
        preview(f"pad_{lname.lower()}", pad_page, M.PAD_ANCHORS, M.PAD_BUTTONS,
                lay, 0, [ctl_pad_value_rects[lid], ctl_pad_value_rects[1 - lid],
                         ctl_stick_value_rect])
    preview("stick", stick_page, M.STICK_ANCHORS, M.STICK_BUTTONS,
            M.STICK_LAYOUT, 2, ctl_pad_value_rects + [ctl_stick_value_rect])

    # ---- loader/menu_layout.h -------------------------------------------
    top_dest_y = [178, 222, 266]    # block 178..302, centered on the 480 screen
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
    lines.append("/* ---- CONTROLS pages (controls_pad.png / controls_stick.png) ----"
                 "\n * CTL_*_FUNC index FUNC_WORDS/CTL_WORD; button order is"
                 "\n * menu_def.py's PAD_BUTTONS / STICK_BUTTONS, same order as"
                 "\n * shims/src/layouts.h's JVS_LAYOUT_* rows. CTL_*_ANCHOR is the"
                 "\n * chip's top-left on the page. The footer is baked into both"
                 "\n * pages -- nothing to blit. */")
    lines.append(f"#define CTL_N_BUTTONS {len(M.PAD_BUTTONS)}")
    lines.append(f"static const mrect_t CTL_WORD[{len(M.FUNC_WORDS)}] = {{"
                 + ", ".join(R(r) for r in ctl_word_rects) + "};   /* "
                 + ", ".join(M.FUNC_WORDS) + " */")
    lines.append("")
    lines.append(f"static const unsigned char CTL_PAD_FUNC[2][{len(M.PAD_BUTTONS)}] = {{")
    for name, lay in M.PAD_LAYOUTS:
        lines.append("  {" + ", ".join(str(M.FUNC_WORDS.index(lay[b]))
                                       for b in M.PAD_BUTTONS) + f"}},   /* {name} */")
    lines.append("};")
    lines.append(f"static const unsigned char CTL_STICK_FUNC[{len(M.STICK_BUTTONS)}] = {{"
                 + ", ".join(str(M.FUNC_WORDS.index(M.STICK_LAYOUT[b]))
                             for b in M.STICK_BUTTONS) + "};")
    lines.append("")
    for tname, buttons, anchors in [("PAD", M.PAD_BUTTONS, M.PAD_ANCHORS),
                                    ("STICK", M.STICK_BUTTONS, M.STICK_ANCHORS)]:
        lines.append(f"static const unsigned short CTL_{tname}_ANCHOR[{len(buttons)}][2] = {{")
        for b in buttons:
            lines.append("  {%d, %d},   /* %s */" % (anchors[b][0], anchors[b][1], b))
        lines.append("};")
    lines.append("")
    lines.append(f"static const mrect_t CTL_ROW_LABEL[{len(M.CTL_ROW_ITEMS)}][2] = {{")
    for norm, hi in ctl_row_rects:
        lines.append(f"  {{{R(norm)}, {R(hi)}}},")
    lines.append("};")
    lines.append(f"static const mrect_t CTL_PAD_VALUE[{len(M.CTL_PAD_VALUES)}] = {{"
                 + ", ".join(R(r) for r in ctl_pad_value_rects) + "};")
    lines.append(f"static const mrect_t CTL_STICK_VALUE = {R(ctl_stick_value_rect)};")
    lines.append("")
    lines.append(f"#define CTL_ROW_LABEL_X {CTL_ROW_LABEL_X}")
    lines.append(f"#define CTL_ROW_VALUE_X {CTL_ROW_VALUE_X}")
    lines.append(f"#define CTL_ROW_Y(i) ({CTL_ROW_Y(0)} + (i) * 34)")
    lines.append("")
    lines.append("#endif /* MENU_LAYOUT_H */")

    with open(os.path.join(LOADER_DIR, "menu_layout.h"), "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"gen_menu_assets: sheet {shelf.bottom}/{M.SHEET_H}px used "
          f"({100 * shelf.bottom / M.SHEET_H:.1f}% vertical), "
          f"{n_settings} settings rows, {len(value_cache)} unique value chips, "
          f"{len(ctl_word_rects)} control-word chips")


if __name__ == "__main__":
    main()

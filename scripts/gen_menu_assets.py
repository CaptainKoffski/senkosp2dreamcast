#!/usr/bin/env python3
"""T9 offline asset generator (Pillow -- NOT a build dependency; outputs are
committed). Renders loader/menu_sheet.png (640x1024 sprite sheet) and the two
controls pages, loader/controls_pad.png / controls_stick.png (640x480), and
emits loader/menu_layout.h (sheet rects + dest coordinates + the settings byte
tables) and shims/src/layouts.h (button->JVS tables), both from menu_def.py.

All art is drawn here (text + flat shapes, including the two controller
schematics) -- never pixels from the game (copyright rule, CLAUDE.md).
Rerun after any menu_def.py change, then VIEW build/preview_*.png: those
composite the label chips onto the pages exactly as the C code blits them, and
are the only check that an anchor actually lands beside its button.
    python3 scripts/gen_menu_assets.py
"""
import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

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


CHIP_W, CHIP_H = 126, 24        # CTL_WORD label-chip cell ("OVERDRIVE" is 118)
CTL_ROW_LABEL_X = 48
CTL_ROW_VALUE_X = 344

# The two controls-page label columns. chip_x is where menu.c blits the
# function chip (== menu_def's anchor x); the baked "<button> --" prefix is
# right-aligned to chip_x - PREFIX_GAP so every em dash in a column lines up
# and the chip's left-aligned word starts one gap later ("Y -- ACTION" reads
# as one line). lead_x is where that row's leader line leaves the label block
# (fixed, not word-dependent: the leaders are baked, the words are not).
# inv_x is where a baked invariant label (MOVE / START) starts.
PREFIX_GAP = 8
COL_L = dict(chip_x=60, lead_x=192, inv_x=12)
COL_R = dict(chip_x=506, lead_x=450, inv_x=458)


def col_of(anchor_x):
    return COL_L if anchor_x < 320 else COL_R


def CTL_ROW_Y(i):
    return 352 + i * 34


def box_of(rect):
    x, y, w, h = rect
    return (x, y, x + w, y + h)


# Controls pages. Round 3 (2026-09-30): the operator dropped the AI-generated
# photos ("the gamepad image still looks like shit") for schematics drawn in
# code -- exact flat colors, no smooth/autocrop/quantize/tint pipeline, and
# button centres that are geometry constants instead of measured pixels.
# Per page:
#   render             () -> (art image, paste origin); everything inside is
#                      drawn in PAGE coordinates at 4x and downscaled once.
#   buttons            button -> (page_x, page_y, r), the same constants the
#                      render used; asserts each leader lands on its button.
#   prefix             override for the baked "<button> --" tag (the DC pad's
#                      triggers are CONT_LTRIG/RTRIG but read as "L"/"R").
#   leads              button -> leader polyline in PAGE space, WITHOUT its
#                      first point: that is always (column lead_x, row centre),
#                      so a leader can never drift off its own label row.
#   tags               invariant labels: (column, row centre y, text, polyline
#                      tail). Same deal, but the leader starts just past the
#                      baked text since there is no chip cell to leave from.
# Routing rules the hand-picked polylines follow: orthogonal only, elbows only
# where the art forces them, no two leaders crossing, and no leader crossing
# a button it does not belong to. The stick's staggered 3x2 cluster leaves a
# clean lane per button (Y overflies Z's top edge; X drops over the top);
# the pad's START rides up the grip gap and doubles as the cable.
SS = 4                          # supersample factor for the drawn art
SHELL = (204, 204, 204)         # device body (vs page BG 224)
SHELL_DK = (176, 176, 176)      # wells, d-pad, triggers, stick base
BTN_FACE = (246, 246, 246)      # button caps, VMU window
LCD = (196, 208, 196)           # VMU screen
BALL = (200, 44, 44)            # stick ball top
PAD_LETTER = {"A": (200, 40, 40), "B": (40, 90, 200),
              "X": (196, 150, 0), "Y": (30, 150, 60)}   # HKT-7700 colors


def art_canvas(ox, oy, w, h):
    """4x canvas + helpers that take PAGE coordinates. union() outlines the
    union of several filled shapes (mask edge = mask minus its erosion), so
    the pad shell and the d-pad cross get one clean silhouette outline."""
    img = Image.new("RGB", (w * SS, h * SS), BG)

    def box(x0, y0, x1, y1):
        return [(x0 - ox) * SS, (y0 - oy) * SS, (x1 - ox) * SS, (y1 - oy) * SS]

    def union(shapes, fill, width=2):
        mask = Image.new("L", img.size, 0)
        md = ImageDraw.Draw(mask)
        for meth, b, kw in shapes:
            getattr(md, meth)(b, fill=255, **kw)
        edge = ImageChops.subtract(
            mask, mask.filter(ImageFilter.MinFilter(2 * width * SS + 1)))
        img.paste(fill, (0, 0), mask)
        img.paste(FG, (0, 0), edge)

    return img, ImageDraw.Draw(img), box, union


def draw_pad():
    """HKT-7700 schematic, front view: shoulder triggers, analog stick over
    the d-pad, VMU window, START under it on the cable boss, A/B/X/Y diamond
    with the pad's letter colors."""
    ox, oy, w, h = 208, 70, 244, 168
    img, d, B, union = art_canvas(ox, oy, w, h)
    W = 2 * SS
    for x0, x1 in [(240, 290), (370, 420)]:     # trigger nubs, shell overlaps
        d.rounded_rectangle(B(x0, 76, x1, 96), radius=6 * SS,
                            fill=SHELL_DK, outline=FG, width=W)
    union([("rounded_rectangle", B(215, 90, 445, 175), dict(radius=42 * SS)),
           ("ellipse", B(220, 110, 288, 230), {}),      # grip lobes
           ("ellipse", B(372, 110, 440, 230), {}),
           ("ellipse", B(307, 145, 353, 200), {})], SHELL)  # cable boss
    d.ellipse(B(248, 94, 296, 142), fill=SHELL_DK, outline=FG, width=W)
    d.ellipse(B(259, 105, 285, 131), fill=SHELL, outline=FG, width=W)
    union([("rounded_rectangle", B(233, 161, 277, 175), dict(radius=3 * SS)),
           ("rounded_rectangle", B(248, 146, 262, 190), dict(radius=3 * SS))],
          SHELL_DK)                                     # d-pad cross
    d.rounded_rectangle(B(306, 98, 354, 142), radius=8 * SS,
                        fill=BTN_FACE, outline=FG, width=W)
    d.rounded_rectangle(B(315, 106, 345, 134), radius=3 * SS,
                        fill=LCD, outline=FG, width=SS)
    d.ellipse(B(321, 173, 339, 191), fill=BTN_FACE, outline=FG, width=W)
    f = ImageFont.truetype(FONT_PATH, 15 * SS)
    for b, (bx, by, br) in PAD_PAGE["buttons"].items():
        if b in ("LTRIG", "RTRIG"):
            continue                                    # the nubs above
        d.ellipse(B(bx - br, by - br, bx + br, by + br),
                  fill=BTN_FACE, outline=FG, width=W)
        d.text(((bx - ox) * SS, (by - oy) * SS), b, font=f,
               fill=PAD_LETTER[b], anchor="mm")
    return img.resize((w, h), Image.LANCZOS), (ox, oy)


def draw_stick():
    """HKT-7300 schematic, top-down: panel on its base, ball-top lever,
    START top-centre, the staggered X/Y/Z + A/B/C rows."""
    ox, oy, w, h = 192, 72, 258, 174
    img, d, B, _ = art_canvas(ox, oy, w, h)
    W = 2 * SS
    d.rounded_rectangle(B(206, 215, 436, 238), radius=6 * SS,
                        fill=SHELL_DK, outline=FG, width=W)   # base side
    d.rounded_rectangle(B(200, 80, 442, 225), radius=16 * SS,
                        fill=SHELL, outline=FG, width=W)      # panel
    d.ellipse(B(221, 116, 269, 164), fill=SHELL_DK, outline=FG, width=W)
    d.ellipse(B(231, 126, 259, 154), fill=BALL, outline=FG, width=W)
    d.ellipse(B(278, 84, 294, 100), fill=BTN_FACE, outline=FG, width=W)
    f = ImageFont.truetype(FONT_PATH, 17 * SS)
    for b, (bx, by, br) in STICK_PAGE["buttons"].items():
        d.ellipse(B(bx - br, by - br, bx + br, by + br),
                  fill=BTN_FACE, outline=FG, width=W)
        d.text(((bx - ox) * SS, (by - oy) * SS), b, font=f, fill=FG,
               anchor="mm")
    return img.resize((w, h), Image.LANCZOS), (ox, oy)


PAD_PAGE = dict(
    render=draw_pad,
    buttons={"Y": (400, 106, 13), "X": (375, 131, 13), "B": (425, 131, 13),
             "A": (400, 156, 13),
             "LTRIG": (265, 86, 14), "RTRIG": (395, 86, 14)},
    prefix={"LTRIG": "L", "RTRIG": "R"},
    leads={"LTRIG": [(265, 72), (265, 80)],
           "RTRIG": [(395, 72), (395, 80)],
           "Y": [(411, 113)],
           "B": [(426, 145), (426, 141)],
           "A": [(400, 177), (400, 169)],
           "X": [(365, 209), (365, 141)]},     # up the grip/body gap
    tags=[(COL_L, 163, "MOVE", [(233, 163)]),  # d-pad left arm tip
          (COL_L, 241, "START", [(330, 241), (330, 192)])])  # "the cable"
STICK_PAGE = dict(
    render=draw_stick,
    buttons={"X": (316, 121, 16), "Y": (366, 108, 16), "Z": (416, 126, 16),
             "A": (316, 173, 16), "B": (366, 160, 16), "C": (416, 178, 16)},
    prefix={},
    leads={"X": [(316, 71), (316, 104)],       # over the top, down X's lane
           "Y": [(386, 105)],                  # overflies Z's top edge
           "Z": [(432, 139)],
           "C": [(433, 173)],
           "B": [(370, 207), (370, 178)],      # under C, up to B
           "A": [(316, 241), (316, 192)]},     # under everything, up X's lane
    tags=[(COL_L, 125, "MOVE", [(223, 125)]),
          (COL_L, 37, "START", [(286, 37), (286, 85)])])


def label(draw, x, cy, text, anchor="lm"):
    """Baked page text: plain FG on the page BG. No plate -- every label now
    sits outside the art, so there is nothing to knock back."""
    check_fits(draw, 640, CHIP_H, text, F_ROW)
    draw.text((x, cy), text, font=F_ROW, fill=FG, anchor=anchor)


def build_page(name, spec, anchors):
    """640x480 controls page: device schematic rendered by spec["render"],
    pasted at its origin, then the baked leader lines, button prefixes,
    invariant labels and footer -- all outside the art."""
    img, (ox, oy) = spec["render"]()
    dw, dh = img.size
    page = Image.new("RGB", (640, 480), BG)
    artbox = (ox, oy, ox + dw, oy + dh)
    assert 0 <= ox and ox + dw <= 640 and oy + dh <= 340, \
        f"{name}: art {dw}x{dh} at ({ox},{oy}) leaves the art region"
    page.paste(img, (ox, oy))

    # every label row: (leader polyline, then what to draw in the margin)
    polys, texts = [], []
    for b, tail in spec["leads"].items():
        col = col_of(anchors[b][0])
        cy = anchors[b][1] + CHIP_H // 2
        polys.append([(col["lead_x"], cy)] + tail)
        pre = spec["prefix"].get(b, b) + " —"
        texts.append((col["chip_x"] - PREFIX_GAP, cy, pre, "rm"))
    for col, cy, text, tail in spec["tags"]:
        tw = ImageDraw.Draw(page).textlength(text, font=F_ROW)
        start = col["lead_x"] if col is COL_R else col["inv_x"] + tw + PREFIX_GAP
        polys.append([(start, cy)] + tail)
        texts.append((col["inv_x"], cy, text, "lm"))

    # halos first, then every stroke: drawn per-leader the halo of a later
    # leader would punch a BG notch through an earlier one's stroke.
    d = ImageDraw.Draw(page)
    for poly in polys:
        d.line(poly, fill=BG, width=6, joint="curve")
    for poly in polys:
        d.line(poly, fill=FG, width=2, joint="curve")
    for x, cy, text, anchor in texts:
        label(d, x, cy, text, anchor)

    # asserts: nothing in the margins may touch the art, and every leader
    # must actually reach the button it claims (page-space polylines are
    # hand-routed, so this is the check that keeps them tied to the art).
    for b, (ax, ay) in anchors.items():
        chip = (ax, ay, ax + CHIP_W, ay + CHIP_H)
        assert chip[2] <= artbox[0] or artbox[2] <= chip[0] \
            or chip[3] <= artbox[1] or artbox[3] <= chip[1], \
            f"{name} {b}: chip {chip} overlaps the art box {artbox}"
    for b, (bx, by, br) in spec["buttons"].items():
        ex, ey = spec["leads"][b][-1]
        dist = ((ex - bx) ** 2 + (ey - by) ** 2) ** 0.5
        assert dist <= br + 5, \
            f"{name} {b}: leader ends at ({ex},{ey}), {dist:.1f}px from the " \
            f"button at ({bx},{by}) r{br}"

    check_fits(d, 640, 24, M.CTL_FOOTER, F_ROW)
    d.text((320, 464), M.CTL_FOOTER, font=F_ROW, fill=GREY, anchor="mm")
    print(f"gen_menu_assets: controls_{name}.png art {dw}x{dh} at ({ox},{oy}),"
          " buttons "
          + " ".join(f"{b}({v[0]},{v[1]})" for b, v in
                     sorted(spec["buttons"].items())))
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
    # LEFT-aligned, not centred: the page bakes a "<button> --" prefix just
    # left of every chip cell, so a centred word would float away from its
    # own dash by however much shorter than "OVERDRIVE" it happens to be.
    ctl_word_rects = []
    for word in M.FUNC_WORDS:
        r = shelf.place(CHIP_W, CHIP_H)
        check_fits(draw, CHIP_W, CHIP_H, word, F_ROW, margin=6)
        put_left(draw, r, word, F_ROW, FG, pad=2)
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

    # "< X >", not bare "X": the angle brackets are baked into BOTH pad chips
    # and mark the row as changeable with LEFT/RIGHT (operator request, round
    # 2). Not a selection cursor -- they show on P1 and P2 at all times. The
    # stick row is fixed, so its chip stays arrow-less; that contrast is the
    # whole point. Same 288-wide centred cell as every other value chip, so
    # the value column's alignment is unchanged.
    ctl_pad_value_rects = [get_chip(f"< {v} >") for v in M.CTL_PAD_VALUES]
    ctl_stick_value_rect = get_chip(M.CTL_STICK_VALUE)

    assert shelf.bottom <= M.SHEET_H, \
        f"sheet content {shelf.bottom}px exceeds {M.SHEET_H}px budget"
    # Canvas was allocated at the full sheet size up front and pre-filled with
    # BG, so the untouched tail below shelf.bottom is already the required
    # padding -- no separate crop+pad step needed.
    sheet.save(os.path.join(LOADER_DIR, "menu_sheet.png"))

    # ---- controls_pad.png / controls_stick.png ---------------------------
    # anchor sanity: the chip must stay on the page above the selector rows,
    # sit in one of the two label columns, and two chips on one page must
    # never collide (they are blitted, not blended). build_page adds the
    # chip-vs-art-box and leader-vs-button checks.
    for page_name, anchors, buttons in [("pad", M.PAD_ANCHORS, M.PAD_BUTTONS),
                                        ("stick", M.STICK_ANCHORS, M.STICK_BUTTONS)]:
        assert set(anchors) == set(buttons), f"{page_name}: anchor/button drift"
        for b in buttons:
            x, y = anchors[b]
            assert x in (COL_L["chip_x"], COL_R["chip_x"]), \
                f"{page_name} {b}: anchor x {x} is not a label column"
            assert 8 <= y <= 340 - CHIP_H, f"{page_name} {b}: anchor y {y} off-page"
        for i, a in enumerate(buttons):
            for b in buttons[i + 1:]:
                ax, ay = anchors[a]
                bx, by = anchors[b]
                assert ax + CHIP_W <= bx or bx + CHIP_W <= ax \
                    or ay + CHIP_H <= by or by + CHIP_H <= ay, \
                    f"{page_name}: {a} and {b} chips overlap"

    pad_page = build_page("pad", PAD_PAGE, M.PAD_ANCHORS)
    stick_page = build_page("stick", STICK_PAGE, M.STICK_ANCHORS)
    pad_page.save(os.path.join(LOADER_DIR, "controls_pad.png"))
    stick_page.save(os.path.join(LOADER_DIR, "controls_stick.png"))

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

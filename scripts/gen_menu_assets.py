#!/usr/bin/env python3
"""T9 offline asset generator (Pillow -- NOT a build dependency; outputs are
committed). Renders loader/menu_sheet.png (640x1024 sprite sheet) and the two
controls pages, loader/controls_pad.png / controls_stick.png (640x480), and
emits loader/menu_layout.h (sheet rects + dest coordinates + the settings byte
tables) and shims/src/layouts.h (button->JVS tables), both from menu_def.py.

All art is drawn here (text + flat shapes) or derived from the operator's own
controller diagrams (vector-traced, see PAD_PAGE comment) -- never pixels
from the game (copyright rule, CLAUDE.md).
Rerun after any menu_def.py change, then VIEW build/preview_*.png: those
composite the label chips onto the pages exactly as the C code blits them, and
are the only check that an anchor actually lands beside its button.
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
LOGO_W, LOGO_H = 424, 246       # top-menu logo rect (mockup-measured; fixed so
LOGO_X, LOGO_Y = (640 - LOGO_W) // 2, 16   # menu_layout.h is stable even when
                                # the gitignored logo.png is absent). Menu rows
                                # moved to 275+ to clear it, see top_dest_y.
CTL_ROW_LABEL_X = 48
CTL_ROW_VALUE_X = 344

# The two controls-page label columns. chip_x is where menu.c blits the
# function chip (== menu_def's anchor x); chips are bare function words since
# 2026-10-03 (operator: the art itself letters every face button, so the old
# baked "<button> --" prefixes were redundant) -- chip_x + the cell's 2px pad
# puts the word on the column text line shared with the baked tags (inv_x).
# lead_x is where that row's leader line leaves the label block (fixed, not
# word-dependent: the leaders are baked, the words are not). inv_x is where
# a baked invariant label (MOVE / START) starts.
TEXT_GAP = 8
COL_L = dict(chip_x=10, lead_x=192, inv_x=12)
COL_R = dict(chip_x=456, lead_x=450, inv_x=458)
# Stick-page right column: the centered stick art (2026-10-03) carries shell
# ink out to x~465, past COL_R's text line, so its tags sit further right --
# x482 (operator: x470 hugged the shell; "OVERDRIVE" still ends at 600,
# inside the left column's own 12px margin). Tag-only, hence no chip_x.
SCOL_R = dict(lead_x=476, inv_x=482)


def col_of(anchor_x):
    return COL_L if anchor_x < 320 else COL_R


def CTL_ROW_Y(i):
    return 352 + i * 34


def box_of(rect):
    x, y, w, h = rect
    return (x, y, x + w, y + h)


# Controls pages. The art is the operator's AI-generated device diagrams,
# VECTORIZED (round 4, 2026-09-30): the original JPEGs' compression noise was
# unfixable by filtering (rounds 1-2) and a from-scratch code-drawn schematic
# lost the art's character (round 3, reverted). vtracer fits flat-color
# splines to the original, which kills the noise by construction; the
# committed loader/*_diagram.svg is the traced vector and *_diagram.png its
# 1024x1024 resvg render, the generator's actual input (tools + exact flags:
# docs/kb/tooling.md §vtracer). Per page:
#   art_h/art_x/art_y  the scaled art's paste box -- height drives the scale,
#                      x/y are chosen so the art clears both label columns.
#   buttons            button -> (src_x, src_y, src_r) in ORIGINAL art pixels
#                      (1024x1024), used to assert each leader lands on its
#                      button and to keep the hand-routed page-space leads
#                      honest if the art or the scale ever moves.
#   leads              button -> leader polyline in PAGE space, WITHOUT its
#                      first point: that is always (column lead_x, row centre),
#                      so a leader can never drift off its own label row.
#   tags               invariant labels: (column, row centre y, text, polyline
#                      tail[, button]). Same deal, but the leader starts just
#                      past the baked text since there is no chip cell to
#                      leave from. A 5th element names the button the tag
#                      points at, opting it into the leader-end assert (the
#                      stick page's rows are all tags -- its layout is fixed,
#                      so nothing is blitted at runtime, see STICK_PAGE).
# Routing rules the hand-picked polylines follow: orthogonal only, one elbow
# where the art allows it, no two leaders crossing, and no leader crossing a
# button it does not belong to (2026-10-03 re-route: corners only where a
# straight shot is geometrically impossible).
PAD_PAGE = dict(
    art_h=240, art_x=203, art_y=34,
    buttons={"Y": (822, 345, 38), "X": (742, 426, 38),
             "B": (897, 426, 38), "A": (822, 507, 38)},
    leads={"LTRIG": [(230, 52), (230, 76)],         # J-drop onto the shoulder
           "RTRIG": [(410, 52), (410, 76)],         # ledge above each trigger
           "Y": [(404, 113)],
           "B": [(415, 145), (415, 141)],
           "A": [(395, 177), (395, 160)],
           "X": [(375, 209), (375, 141)]},
    tags=[(COL_L, 163, "MOVE",                      # forks: d-pad left arm +
           [[(229, 163)],                           # analog ring left edge.
            [(195, 163), (195, 115), (211, 115)]]), # Split at x195, in the BG
          (COL_L, 205, "START", [(307, 205)])])     # clear of the shell, so it
                                                    # reads as TWO lines (ring
                                                    # page c(236,115) r26;
                                                    # operator round: the old
                                                    # split 1px before the tip
                                                    # read as stick-only)
# No "B" row on the stick page (operator, round 5): B maps to NONE, and a
# labeled leader pointing at an unmapped button is noise.
# Every label here is a baked TAG, not a chip row: the stick layout is fixed
# ("ARCADE (FIXED)"), so menu.c blits nothing on this page (2026-10-03,
# operator: the chip-grid routes were overcomplicated). Freed from the chip
# columns, each row sits at its button's own height and the leaders are as
# straight as the art allows:
#   Z/C   horizontals at the button centre heights (y83/y123), kissing the
#         cluster's east rims (rim east points x427.7). BARRAGE's text row
#         sits lower, y95, stepping up to y83 mid-run at x450 (operator:
#         at y83 the label crowded SUB, whose own line cannot leave the
#         y65 seam, and a step right at the label read badly; x450 keeps
#         the leg's halo clear of the screw at ~(442,76), Z's rim at 428,
#         and the shell edge verticals at 455-457/464);
#   Y     rides the button panel's top edge line (y65 -- the corridor the
#         old 3-corner route jogged into), one drop onto Y's crown;
#   X     top-left tag: over the dome (y30 clears the art box entirely),
#         one drop down the canyon between the VMU (right edge x338) and
#         the START button (left edge x361), landing on X's crown;
#   A     one elbow, its vertical rising onto A's south rim dead under the
#         button centre (x348; operator 2026-10-03: the old logo-edge x365
#         landed on the SE arc and read as off-centre). The horizontal at
#         y173 clears the "Dreamcast" logo top (ink from y~180) with its
#         halo; the vertical stays above the logo's y-range entirely;
#   START one drop onto the button crown (centre ~(368,54) r7; the old hook
#         cut through the vent panel's left slope).
# art_x 131 -> 172 (2026-10-03): ink centered at x320 like the pad page's
# (operator). Every page-space x in the routes and the measurements above
# moved +41 with it; the right column is SCOL_R, see its comment.
STICK_PAGE = dict(
    art_h=224, art_x=172, art_y=34,
    buttons={"X": (605, 397, 50), "Y": (705, 327, 50), "Z": (827, 327, 50),
             "A": (606, 524, 50), "C": (828, 461, 50)},
    leads={},
    tags=[(COL_L, 30, "MAIN", [(347, 30), (347, 88)], "X"),
          (COL_L, 123, "MOVE", [(230, 123)]),       # lever ball west point:
                                                    # ball x231-261 y108-138,
                                                    # kiss at centre height
          (SCOL_R, 37, "START", [(368, 37), (368, 48)]),
          (SCOL_R, 65, "SUB", [(377, 65), (377, 67)], "Y"),
          (SCOL_R, 95, "BARRAGE", [(450, 95), (450, 83), (429, 83)], "Z"),
          (SCOL_R, 123, "OVERDRIVE", [(429, 123)], "C"),
          (SCOL_R, 173, "ACTION", [(348, 173), (348, 157)], "A")])


def label(draw, x, cy, text, anchor="lm"):
    """Baked page text: plain FG on the page BG. No plate -- every label now
    sits outside the art, so there is nothing to knock back."""
    check_fits(draw, 640, CHIP_H, text, F_ROW)
    draw.text((x, cy), text, font=F_ROW, fill=FG, anchor=anchor)


def build_page(name, spec, anchors):
    """640x480 controls page: vector-traced art autocropped, scaled to
    spec["art_h"] and pasted at (art_x, art_y), then the baked leader lines,
    invariant labels and footer -- all outside the art.
    No de-noise/quantize steps: the input is a flat-color (<=32) render of
    the traced SVG, so there is no JPEG noise left to clean."""
    art = os.path.join(LOADER_DIR, f"{name}_diagram.png")
    assert os.path.exists(art), f"missing {art} (render of {name}_diagram.svg)"
    src = Image.open(art).convert("RGB")
    # autocrop the art's own margin. The threshold is relative to the corner
    # level, not a fixed near-white: the stick art's background is light grey
    # (230), so a fixed "darker than 245" test crops nothing. DARKER than the
    # corner level: both devices are darker than their background, while any
    # brighter-than-bg patch (the pad's glare remnant between the grips) is
    # background.
    g = src.convert("L")
    lvl = sorted(g.getpixel(p) for p in [(2, 2), (src.width - 3, 2),
                                         (2, src.height - 3),
                                         (src.width - 3, src.height - 3)])[2]
    bbox = g.point(lambda p: 255 if lvl - p > 14 else 0).getbbox()
    assert bbox, f"{name}: autocrop found no content"
    pad = 12
    cx0, cy0 = max(bbox[0] - pad, 0), max(bbox[1] - pad, 0)
    src = src.crop((cx0, cy0, min(bbox[2] + pad, src.width),
                    min(bbox[3] + pad, src.height)))
    scale = spec["art_h"] / src.height
    dw, dh = round(src.width * scale), spec["art_h"]
    img = src.resize((dw, dh), Image.LANCZOS)
    # tint so the art's own background lands exactly on the page BG: sample
    # the bg level from the corners (inside the autocrop pad, pure bg by
    # construction) and scale all pixels by BG/bg_level
    g = img.convert("L")
    bg_level = sorted(g.getpixel(p) for p in
                      [(2, 2), (dw - 3, 2), (2, dh - 3), (dw - 3, dh - 3)])[2]
    img = img.point(lambda p: min(255, p * BG[0] // bg_level))
    # flatten the outer bg region to exactly BG. Interior lights (VMU window,
    # pad body) are enclosed by darker outlines, so the fill cannot reach
    # them. thresh is PIL's summed-channel difference: 60 = ~20/channel,
    # enough to absorb the bg and its light remnants, far below the outlines.
    # Two-pass sentinel fill: floodfill() no-ops when the seed already sits
    # within thresh of the target value (our corners == BG by the tint
    # above), so fill to a sentinel first, then sentinel -> BG.
    SENTINEL = (255, 0, 255)
    for corner in [(2, 2), (dw - 3, 2), (2, dh - 3), (dw - 3, dh - 3)]:
        ImageDraw.floodfill(img, corner, SENTINEL, thresh=60)
        ImageDraw.floodfill(img, corner, BG, thresh=60)
    page = Image.new("RGB", (640, 480), BG)
    ox, oy = spec["art_x"], spec["art_y"]
    artbox = (ox, oy, ox + dw, oy + dh)
    assert 0 <= ox and ox + dw <= 640 and oy + dh <= 340, \
        f"{name}: art {dw}x{dh} at ({ox},{oy}) leaves the art region"
    page.paste(img, (ox, oy))

    def to_page(sx, sy):        # original art pixel -> page pixel
        return (round((sx - cx0) * scale) + ox, round((sy - cy0) * scale) + oy)

    # every label row: (leader polyline, then what to draw in the margin)
    polys, texts = [], []
    for b, tail in spec["leads"].items():
        col = col_of(anchors[b][0])
        cy = anchors[b][1] + CHIP_H // 2
        polys.append([(col["lead_x"], cy)] + tail)
    for tag in spec["tags"]:
        col, cy, text, tail = tag[:4]
        tw = ImageDraw.Draw(page).textlength(text, font=F_ROW)
        # right column iff the leader exits LEFT of the text (lead_x < inv_x);
        # a left column's leader exits just past the text's right end.
        start = col["lead_x"] if col["lead_x"] < col["inv_x"] \
            else col["inv_x"] + tw + TEXT_GAP
        # tail is one polyline, or a list of them for a forking leader (the
        # pad's MOVE points at BOTH the d-pad and the analog stick); each
        # fork starts at the same label exit, so shared segments overdraw.
        for t in (tail if isinstance(tail[0], list) else [tail]):
            polys.append([(start, cy)] + t)
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
    lead_end = {b: tail[-1] for b, tail in spec["leads"].items()}
    for tag in spec["tags"]:
        if len(tag) == 5:
            lead_end[tag[4]] = tag[3][-1]
    for b, (sx, sy, sr) in spec["buttons"].items():
        bx, by = to_page(sx, sy)
        ex, ey = lead_end[b]
        dist = ((ex - bx) ** 2 + (ey - by) ** 2) ** 0.5
        assert dist <= sr * scale + 5, \
            f"{name} {b}: leader ends at ({ex},{ey}), {dist:.1f}px from the " \
            f"button at ({bx},{by}) r{sr * scale:.1f}"

    check_fits(d, 640, 24, M.CTL_FOOTER, F_ROW)
    d.text((320, 464), M.CTL_FOOTER, font=F_ROW, fill=GREY, anchor="mm")
    print(f"gen_menu_assets: controls_{name}.png art {dw}x{dh} at ({ox},{oy}) "
          f"scale {scale:.4f}, buttons "
          + " ".join(f"{b}{to_page(*v[:2])}" for b, v in
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
        "#define LAYOUT_PAD_OLD        1",
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
    # LEFT-aligned, not centred: the word must hug the cell's left edge --
    # that edge is the column text line shared with the baked tags, and a
    # centred word would float off it by however much shorter than
    # "OVERDRIVE" it happens to be.
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
    for page_name, anchors, buttons in [("pad", M.PAD_ANCHORS, M.PAD_BUTTONS)]:
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
    stick_page = build_page("stick", STICK_PAGE, {})   # all-tag page, no chips
    pad_page.save(os.path.join(LOADER_DIR, "controls_pad.png"))
    stick_page.save(os.path.join(LOADER_DIR, "controls_stick.png"))

    # ---- logo_strip.pal8 + .png (tester mockup 2026-10-03: game logo above
    # the top menu). logo.png is the official G.Rev logo art -- branded, so
    # it and both outputs are gitignored (the uncommitted outputs of this
    # script, same category as loader/splash.png). PALETTIZED, not RGB565:
    # the raw rect (~209 KB) blew the CDI's 1792-sector FS+loader region
    # (make_cdi.py asserts it); 8bpp is ~105 KB and leaves ~90 KB headroom.
    # Blob layout menu.c's draw_logo() reads: 256 x RGB565-LE palette (512 B)
    # then LOGO_W*LOGO_H indices, row-major. The .png is the DECODED preview
    # -- view it, it is exactly what ships (verification discipline).
    logo_src = os.path.join(REPO, "logo.png")
    if os.path.exists(logo_src):
        logo = Image.open(logo_src).convert("RGBA")
        lh = round(logo.height * LOGO_W / logo.width)
        assert lh == LOGO_H, f"logo.png aspect changed: {LOGO_W}x{lh}, " \
            f"menu_layout.h pins {LOGO_W}x{LOGO_H}"
        flat = Image.new("RGB", (LOGO_W, LOGO_H), BG)
        rgba = logo.resize((LOGO_W, LOGO_H), Image.LANCZOS)
        flat.paste(rgba, (0, 0), rgba)
        q = flat.quantize(256)
        pal = (q.getpalette() + [0] * 768)[:768]
        blob = b"".join(
            rgb565(tuple(pal[i * 3:i * 3 + 3])).to_bytes(2, "little")
            for i in range(256)) + bytes(q.getdata())
        assert len(blob) == 512 + LOGO_W * LOGO_H
        with open(os.path.join(LOADER_DIR, "logo_strip.pal8"), "wb") as f:
            f.write(blob)
        q.convert("RGB").save(os.path.join(LOADER_DIR, "logo_strip.png"))
        print(f"gen_menu_assets: logo_strip.pal8 {LOGO_W}x{LOGO_H} 8bpp "
              f"({len(blob)} B) at ({LOGO_X},{LOGO_Y})")
    else:
        print("gen_menu_assets: logo.png missing (gitignored branded art) -- "
              "logo_strip.pal8 not regenerated; loader build needs it")

    # ---- previews (verification discipline: chips composited exactly as
    # the C code blits them, so the anchors are checked against the truth)
    build_dir = os.path.join(REPO, "build")
    os.makedirs(build_dir, exist_ok=True)

    def preview(name, page, anchors, buttons, layout, row_hi, values):
        pv = page.copy()
        for b in buttons:
            if layout[b] == "NONE":     # mirror menu.c's CTL_FUNC_NONE skip
                continue
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
    preview("stick", stick_page, {}, [],   # labels baked -- nothing to blit
            M.STICK_LAYOUT, 2, ctl_pad_value_rects + [ctl_stick_value_rect])

    # ---- loader/menu_layout.h -------------------------------------------
    top_dest_y = [275, 319, 363]    # below the logo strip (was 178..302
                                    # centered, pre-logo); footer 452 unmoved
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
        "/* logo_strip.pal8 rect: 256 x RGB565-LE palette then 8bpp indices */",
        f"#define MENU_LOGO_W {LOGO_W}",
        f"#define MENU_LOGO_H {LOGO_H}",
        f"#define MENU_LOGO_X {LOGO_X}",
        f"#define MENU_LOGO_Y {LOGO_Y}",
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
                 "\n * CTL_PAD_FUNC indexes FUNC_WORDS/CTL_WORD; button order is"
                 "\n * menu_def.py's PAD_BUTTONS, same order as shims/src/layouts.h's"
                 "\n * JVS_LAYOUT_* rows. CTL_PAD_ANCHOR is the chip's top-left on"
                 "\n * the page. The stick page is fully baked (fixed layout) and"
                 "\n * needs no tables; the footer is baked into both pages. */")
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
    lines.append("")
    lines.append(f"static const unsigned short CTL_PAD_ANCHOR[{len(M.PAD_BUTTONS)}][2] = {{")
    for b in M.PAD_BUTTONS:
        lines.append("  {%d, %d},   /* %s */" % (M.PAD_ANCHORS[b][0], M.PAD_ANCHORS[b][1], b))
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

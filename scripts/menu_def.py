"""T9 menu single source: settings rows, labels, layout constants.

Read by gen_menu_assets.py (renders loader/menu_sheet.png + the two controls
pages and emits loader/menu_layout.h). SETTINGS rows transcribed verbatim from the
T9 recon table (docs/kb/phase7-polishing.md "### T9 RECON -- GAME ASSIGNMENTS
byte map (2026-09-12, operator emulator leg)") -- byte index into the 16-byte
game record, (label, byte) per value. No recon row changes two bytes together
(idx9/11/13/15 are fixed-zero high bytes of the three round-time fields,
treated as single bytes per the recon table's own note), so every row below
carries idx2=None/bytes2=None; the mechanism stays in the header format
(MENU_SET_IDX2/MENU_SET_BYTE2) because the C code (Task 5) reads it.
"""
DEFAULT_RECORD = "23511703010101020200460096004600"   # KB §EEPROM game record, idx4 Event=ON (operator 2026-09-30)
SYSTEM_COIN_SETTING = 27   # Naomi coin setting 27 = FREE PLAY: system EEPROM byte 9 = 27 - 1 = 0x1a (KB phase4-conversion.md §FREE PLAY) -- same value Flycast's ForceFreePlay writes (naomi_flashrom.cpp:266-268); read by gen_mie_blobs.py

TOP_ITEMS = ["START GAME", "SETTINGS", "CONTROLS"]
TOP_FOOTER = "UP/DOWN: MOVE   A: SELECT"
SET_FOOTER = "UP/DOWN: ITEM   LEFT/RIGHT: CHANGE   B: BACK"

# (label, idx, [(value_label, byte), ...], idx2, [byte2, ...] or None)
# Order matches the recon table's row order.
SETTINGS = [
    ("GAME DIFFICULTY", 6, [
        ("EASY", 0x00), ("NORMAL", 0x01), ("HARD", 0x02), ("MANIA", 0x03),
    ], None, None),
    ("POINT VS HUMAN", 7, [
        ("1", 0x01), ("2", 0x02), ("3", 0x03), ("4", 0x04), ("5", 0x05),
    ], None, None),
    ("POINT VS CPU", 8, [
        ("1", 0x01), ("2", 0x02), ("3", 0x03), ("4", 0x04), ("5", 0x05),
    ], None, None),
    ("ROUND TIME VS HUMAN", 10, [
        ("50", 0x32), ("60", 0x3c), ("70", 0x46), ("80", 0x50),
        ("90", 0x5a), ("100", 0x64), ("110", 0x6e), ("120", 0x78),
    ], None, None),
    ("ROUND TIME CPU STORY", 12, [
        ("90", 0x5a), ("100", 0x64), ("110", 0x6e), ("120", 0x78),
        ("130", 0x82), ("140", 0x8c), ("150", 0x96),
    ], None, None),
    ("ROUND TIME VS CPU", 14, [
        ("50", 0x32), ("60", 0x3c), ("70", 0x46), ("80", 0x50),
        ("90", 0x5a), ("100", 0x64), ("110", 0x6e), ("120", 0x78),
    ], None, None),
    ("EVENT MODE", 4, [("OFF", 0x00), ("ON", 0x01)], None, None),
    ("NOVICE MODE", 5, [("OFF", 0x00), ("ON", 0x01)], None, None),
]

# ---- Control layouts (controls spec 2026-09-27) -------------------------
# Single source for BOTH the shim's button->JVS tables (shims/src/layouts.h)
# and the controls page's label chips/anchors (menu_layout.h). Button names
# match jvs.c's CONT_* constants (KOS controller.h bit numbering); function
# names index FUNC_WORDS / FUNC_JVS.
# B.O.S.S. (tester ask 2026-10-15): a macro -- one DC button raises Main, Sub
# and Action in the same poll, the three-button chord the cabinet needs for
# B.O.S.S. mode (the 360 Rev.X port exposes it as an assignable function).
# List index = the 4-bit function id a CUSTOM layout stores (CTL_N_FUNC /
# JVS_FUNC_N, <= 16); NONE stays last so LEFT/RIGHT cycling ends on "off".
FUNC_WORDS = ["MAIN", "SUB", "BARRAGE", "ACTION", "OVERDRIVE", "B.O.S.S.", "NONE"]
FUNC_JVS = {            # function -> jvs.c expression (NONE = unmapped)
    "MAIN": "JVS_M", "SUB": "JVS_S", "BARRAGE": "JVS_BARRAGE",
    "ACTION": "JVS_A", "OVERDRIVE": "JVS_OD",
    "B.O.S.S.": "(JVS_M | JVS_S | JVS_A)", "NONE": "0",
}
PAD_BUTTONS   = ["A", "B", "X", "Y", "LTRIG", "RTRIG"]  # runtime-labeled, fixed order
STICK_BUTTONS = ["A", "B", "X", "Y", "Z", "C"]

# List order = shim layout id: 0 TOURNAMENT (default), 1 OLD.
# TOURNAMENT is the tester's EVO layout (CONTROLS_TASK.MD); OLD is the
# pre-2026-09-27 shipped mapping (docs/kb/input-map.md §DC pad layout).
# "OLD" was "CLASSIC" until 2026-09-30 (operator: nothing classic about it).
PAD_LAYOUTS = [
    ("TOURNAMENT", {"A": "MAIN", "B": "SUB", "X": "BARRAGE", "Y": "ACTION",
                    "LTRIG": "OVERDRIVE", "RTRIG": "ACTION"}),
    ("OLD",        {"A": "MAIN", "B": "ACTION", "X": "SUB", "Y": "BARRAGE",
                    "LTRIG": "ACTION", "RTRIG": "OVERDRIVE"}),
]
# Arcade stick: the Naomi cabinet layout, entry 0 = the stock stick word
# (JVS_WORD_ARCADE). B deliberately unmapped -- the tester's spec says "B =
# none"; since the controls library (2026-10-24) the stick page blits chips
# like the pad page, so B gets a chip too and shows NONE here.
STICK_LAYOUTS = [
    ("ARCADE", {"X": "MAIN", "Y": "SUB", "Z": "BARRAGE", "A": "ACTION",
                "B": "NONE", "C": "OVERDRIVE"}),
]

# ---- Controls page (controls library, spec 2026-10-24) -----------------
# One shared library of CTL_N_CUSTOM custom layouts per device class; each
# port picks a stock layout or a slot on its own row. Slot i is always named
# CUSTOM i+1 (CTL_CUSTOM_NAMES); the row's value cell turns into the red
# CTL_DELETE_CELL while a delete waits for its second X.
CTL_PORTS = 2
CTL_N_CUSTOM = 8
CTL_CUSTOM_NAMES = [f"CUSTOM {i + 1}" for i in range(CTL_N_CUSTOM)]
CTL_DELETE_CELL = "DELETE?"
# Preview-only layout a CUSTOM row can produce (B.O.S.S. and NONE chips).
CUSTOM_DEMO = {"A": "ACTION", "B": "B.O.S.S.", "X": "BARRAGE", "Y": "OVERDRIVE",
               "LTRIG": "MAIN", "RTRIG": "NONE"}
# Footer strip per page state (dict order = CTL_FOOT_* index). check_fits is
# the gate; a strip that clips loses "UP/DOWN: ROW" first (spec section 7) --
# ROWS_STOCK did (644px with it, 624px max at F_ROW).
CTL_FOOTERS = {
    "ROWS_STOCK": "LEFT/RIGHT: LAYOUT   A: CUSTOMIZE   B: BACK",
    "ROWS_CUSTOM": "LEFT/RIGHT: LAYOUT   A: EDIT   X: DELETE   B: BACK",
    "EDIT": "D-PAD: BUTTON   A: CHANGE   B: DONE",
    "VALUE": "LEFT/RIGHT: FUNCTION   A: KEEP   B: UNDO",
    "CONFIRM": "X: DELETE   ANY OTHER BUTTON: CANCEL",
    "FULL": "ALL 8 CUSTOM SLOTS USED: DELETE ONE FIRST",
}

# Label-chip anchors: top-left of the CHIP_W x 24 function chip per button, in
# PAGE space. Redesign 2026-09-30 (operator rejected the first pass: chips sat
# ON the art with white plates and no button identity). Rules now:
#   - every chip lives OUTSIDE the device art's bounding box, in one of two
#     label columns -- left x10, right x456 (stick x480; gen_menu_assets
#     COL_L/COL_R/SCOL_R);
#     the generator asserts chip-vs-art-box separation;
#   - the chip is the bare function word -- no "<button> --" prefix since
#     2026-10-03 (operator: the art letters every face button already, and
#     each leader touches its own button, so the letters were redundant);
#   - a baked leader line (halo + stroke) runs from the row to its button;
#     the generator asserts each leader ends on its button's circle.
# Row y here IS the design: anchor_y + 12 is the row centre the generator
# routes the leader from, and anchor_x picks the column. MOVE / START are
# invariant, so they are baked labels with leaders and carry no anchor.
# L/R rows sit at y40 (row centre 52), ABOVE the shell's shoulder ledges
# (top edge y72-79): their leaders run horizontal then drop vertically onto
# the ledge above each hidden trigger (operator 2026-10-02: straight side
# stubs didn't read as pointing at the triggers underneath).
PAD_ANCHORS   = {"A": (456, 165), "B": (456, 133), "X": (456, 197),
                 "Y": (456, 101), "LTRIG": (10, 40), "RTRIG": (456, 40)}
# Stick chips sit exactly where the 2026-10-03 baked tags sat (anchor y =
# tag y - 12), so the tags' straight leaders keep their routes; the right
# column is x480 (SCOL_R, look block below). B is new: its row sits between
# OVERDRIVE and ACTION so the column still reads top-down.
STICK_ANCHORS = {"X": (10, 18), "Y": (480, 53), "Z": (480, 83), "C": (480, 111),
                 "B": (480, 136), "A": (480, 161)}

# Rows: class-major (P1 PAD, P2 PAD, P1 STICK, P2 STICK); row i is class
# i // CTL_PORTS, port i % CTL_PORTS.
CTL_CLASSES = [("PAD", PAD_BUTTONS, PAD_LAYOUTS, PAD_ANCHORS),
               ("STICK", STICK_BUTTONS, STICK_LAYOUTS, STICK_ANCHORS)]
CTL_ROW_ITEMS = [f"P{p + 1} {name} LAYOUT" for name, *_ in CTL_CLASSES
                 for p in range(CTL_PORTS)]

SHEET_W, SHEET_H = 640, 1280    # fixed; generator asserts everything fits

# ---- look (fonts, colours, layout numbers, leader routes) ----------------
# Read by kit/scripts/gen_menu_assets.py (its LOOK tuple, no defaults). Moved
# verbatim from the generator at the kit's final review (spec §2: senkosp's
# look is senkosp's definition); the generator builds the fonts from
# FONT_PATH and the *_PT sizes.
FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
F_TOP_PT = 28          # top-menu labels
F_ROW_PT = 20          # settings rows/footers/values
F_TITLE_PT = 24        # titles

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
RED = (0xc0, 0x38, 0x28)      # DELETE? cell fill; RED/WHITE sit on the RGB565
WHITE = (0xf8, 0xfc, 0xf8)    # grid, so the sheet's 565 snap leaves them alone

CHIP_W, CHIP_H = 126, 24        # CTL_WORD label-chip cell ("OVERDRIVE" is 118)
LOGO_W, LOGO_H = 424, 246       # top-menu logo rect (mockup-measured; fixed so
LOGO_X, LOGO_Y = (640 - LOGO_W) // 2, 16   # menu_layout.h is stable even when
                                # the gitignored logo.png is absent). Menu rows
                                # moved to 275+ to clear it, see top_dest_y.
CTL_ROW_LABEL_X = 48
CTL_ROW_VALUE_X = 344
CTL_FOOTER_Y = 452              # same line as the top/settings footers

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
# ink out to x~465, past COL_R's text line, so its text line sits further
# right -- x482 (operator: x470 hugged the shell; "OVERDRIVE" still ends at
# 600, inside the left column's own 12px margin). Chips since the controls
# library (2026-10-24): chip_x 480 puts the word on that same x482 line.
SCOL_R = dict(chip_x=480, lead_x=476, inv_x=482)

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
#   col_r              the page's right label column (COL_R / SCOL_R); a
#                      chip anchored at x < 320 is in COL_L.
#   leads              button -> leader polyline in PAGE space, WITHOUT its
#                      first point: that is always (column lead_x, row centre),
#                      so a leader can never drift off its own label row.
#   tags               invariant labels: (column, row centre y, text, polyline
#                      tail). Same deal, but the leader starts just past the
#                      baked text since there is no chip cell to leave from.
# Routing rules the hand-picked polylines follow: orthogonal only, one elbow
# where the art allows it, no two leaders crossing, and no leader crossing a
# button it does not belong to (2026-10-03 re-route: corners only where a
# straight shot is geometrically impossible).
PAD_PAGE = dict(
    art_h=240, art_x=203, art_y=34, col_r=COL_R,
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
# Stick page (controls library, 2026-10-24): runtime chips like the pad page.
# The chip cells sit where the 2026-10-03 baked tags sat (menu_def
# STICK_ANCHORS: anchor y = tag y - 12), so every tag's leader kept its route
# -- each row sits at its button's own height and the leaders are as straight
# as the art allows:
#   Z/C   horizontals at the button centre heights (y83/y123), kissing the
#         cluster's east rims (rim east points x427.7). BARRAGE's text row
#         sits lower, y95, stepping up to y83 mid-run at x450 (operator:
#         at y83 the label crowded SUB, whose own line cannot leave the
#         y65 seam, and a step right at the label read badly; x450 keeps
#         the leg's halo clear of the screw at ~(442,76), Z's rim at 428,
#         and the shell edge verticals at 455-457/464);
#   Y     rides the button panel's top edge line (y65 -- the corridor the
#         old 3-corner route jogged into), one drop onto Y's crown;
#   X     top-left row: over the dome (y30 clears the art box entirely),
#         one drop down the canyon between the VMU (right edge x338) and
#         the START button (left edge x361), landing on X's crown;
#   B     new row at y148, between OVERDRIVE and ACTION. B shares C's centre
#         height, so a straight line would cross C: the horizontal runs under
#         C (rim bottom ~y138) and rises onto B's south rim dead under its
#         centre -- one elbow, the same shape as A's. B's art centre
#         (705,461) r50 was measured on stick_diagram.png (outer ring ink
#         x655-756, y411-512);
#   A     one elbow, its vertical rising onto A's south rim dead under the
#         button centre (x348; operator 2026-10-03: the old logo-edge x365
#         landed on the SE arc and read as off-centre). The horizontal at
#         y173 clears the "Dreamcast" logo top (ink from y~180) with its
#         halo; the vertical stays above the logo's y-range entirely;
#   START baked tag (no function), one drop onto the button crown (centre
#         ~(368,54) r7; the old hook cut through the vent panel's left slope).
# art_x 131 -> 172 (2026-10-03): ink centered at x320 like the pad page's
# (operator). Every page-space x in the routes and the measurements above
# moved +41 with it; the right column is SCOL_R, see its comment.
STICK_PAGE = dict(
    art_h=224, art_x=172, art_y=34, col_r=SCOL_R,
    buttons={"X": (605, 397, 50), "Y": (705, 327, 50), "Z": (827, 327, 50),
             "A": (606, 524, 50), "B": (705, 461, 50), "C": (828, 461, 50)},
    leads={"X": [(347, 30), (347, 88)],
           "Y": [(377, 65), (377, 67)],
           "Z": [(450, 95), (450, 83), (429, 83)],
           "C": [(429, 123)],
           "B": [(377, 148), (377, 138)],
           "A": [(348, 173), (348, 157)]},
    tags=[(COL_L, 123, "MOVE", [(230, 123)]),       # lever ball west point:
                                                    # ball x231-261 y108-138,
                                                    # kiss at centre height
          (SCOL_R, 37, "START", [(368, 37), (368, 48)])])

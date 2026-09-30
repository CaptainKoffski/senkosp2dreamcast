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
FUNC_WORDS = ["MAIN", "SUB", "BARRAGE", "ACTION", "OVERDRIVE", "NONE"]
FUNC_JVS = {            # function -> jvs.c constant (NONE = unmapped)
    "MAIN": "JVS_M", "SUB": "JVS_S", "BARRAGE": "JVS_BARRAGE",
    "ACTION": "JVS_A", "OVERDRIVE": "JVS_OD", "NONE": "0",
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
# Arcade stick: the Naomi cabinet layout, fixed (layout id 2). B deliberately
# unmapped -- the tester's spec says "B = none". No B row on the stick page
# (operator, round 5): the C code skips NONE chips (CTL_FUNC_NONE) and the
# page bakes no prefix/leader for B.
STICK_LAYOUT = {"X": "MAIN", "Y": "SUB", "Z": "BARRAGE", "A": "ACTION",
                "B": "NONE", "C": "OVERDRIVE"}

# ---- Controls page (controls spec 2026-09-27) ---------------------------
CTL_ROW_ITEMS = ["P1 PAD LAYOUT", "P2 PAD LAYOUT", "STICK LAYOUT"]
CTL_PAD_VALUES = ["TOURNAMENT", "OLD"]              # index = layout id
CTL_STICK_VALUE = "ARCADE (FIXED)"
CTL_FOOTER = "UP/DOWN: ROW   LEFT/RIGHT: CHANGE   B: BACK"

# Label-chip anchors: top-left of the CHIP_W x 24 function chip per button, in
# PAGE space. Redesign 2026-09-30 (operator rejected the first pass: chips sat
# ON the art with white plates and no button identity). Rules now:
#   - every chip lives OUTSIDE the device art's bounding box, in one of two
#     label columns -- left x60, right x506 (gen_menu_assets.COL_L/COL_R);
#     the generator asserts chip-vs-art-box separation;
#   - the column slot to the LEFT of each chip carries a baked "<button> --"
#     prefix, so the row reads "Y -- ACTION" with the runtime chip supplying
#     only the function word (chips are LEFT-aligned for that reason);
#   - a baked leader line (halo + stroke) runs from the row to its button;
#     the generator asserts each leader ends on its button's circle.
# Row y here IS the design: anchor_y + 12 is the row centre the generator
# routes the leader from, and anchor_x picks the column. MOVE / START are
# invariant, so they are baked labels with leaders and carry no anchor.
PAD_ANCHORS   = {"A": (506, 165), "B": (506, 133), "X": (506, 197),
                 "Y": (506, 101), "LTRIG": (60, 60), "RTRIG": (506, 60)}
# Stick B is a dead slot: its chip is never blitted (NONE skip in menu.c),
# but the anchor entry stays so the [6]-wide tables keep their shape; parked
# on the vacated bottom row so the chip-overlap assert holds.
STICK_ANCHORS = {"A": (506, 195), "B": (506, 229), "X": (506, 59),
                 "Y": (506, 93), "Z": (506, 127), "C": (506, 161)}

SHEET_W, SHEET_H = 640, 1024    # fixed; generator asserts everything fits

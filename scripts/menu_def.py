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
DEFAULT_RECORD = "23511703000101020200460096004600"   # KB §EEPROM game record

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
FUNC_WORDS = ["MAIN", "SUB", "BARRAGE", "ACTION", "OVERDRIVE", "-"]
FUNC_JVS = {            # function -> jvs.c constant ("-" = unmapped)
    "MAIN": "JVS_M", "SUB": "JVS_S", "BARRAGE": "JVS_BARRAGE",
    "ACTION": "JVS_A", "OVERDRIVE": "JVS_OD", "-": "0",
}
PAD_BUTTONS   = ["A", "B", "X", "Y", "LTRIG", "RTRIG"]  # runtime-labeled, fixed order
STICK_BUTTONS = ["A", "B", "X", "Y", "Z", "C"]

# List order = shim layout id: 0 TOURNAMENT (default), 1 CLASSIC.
# TOURNAMENT is the tester's EVO layout (CONTROLS_TASK.MD); CLASSIC is the
# pre-2026-09-27 shipped mapping (docs/kb/input-map.md §DC pad layout).
PAD_LAYOUTS = [
    ("TOURNAMENT", {"A": "MAIN", "B": "SUB", "X": "BARRAGE", "Y": "ACTION",
                    "LTRIG": "OVERDRIVE", "RTRIG": "ACTION"}),
    ("CLASSIC",    {"A": "MAIN", "B": "ACTION", "X": "SUB", "Y": "BARRAGE",
                    "LTRIG": "ACTION", "RTRIG": "OVERDRIVE"}),
]
# Arcade stick: the Naomi cabinet layout, fixed (layout id 2). B deliberately
# unmapped -- the tester's spec says "B = none"; it renders as the "-" chip.
STICK_LAYOUT = {"X": "MAIN", "Y": "SUB", "Z": "BARRAGE", "A": "ACTION",
                "B": "-", "C": "OVERDRIVE"}

# ---- Controls page (controls spec 2026-09-27) ---------------------------
CTL_ROW_ITEMS = ["P1 PAD LAYOUT", "P2 PAD LAYOUT", "STICK LAYOUT"]
CTL_PAD_VALUES = ["TOURNAMENT", "CLASSIC"]          # index = layout id
CTL_STICK_VALUE = "ARCADE (FIXED)"
CTL_FOOTER = "UP/DOWN: ROW   LEFT/RIGHT: CHANGE   B: BACK"

# Label-chip anchors: top-left of the 160x24 chip per button, in PAGE space
# (measured off build/preview_*.png -- the art is scaled + pasted first, so
# these are NOT source-art coordinates). Art region is y 8..340; the selector
# rows start at y 352 (CTL_ROW_Y). Placement rules, in order:
#   - never cover a button-identity letter (A/B/X/Y, X/Y/Z/A/B/C) or the
#     Dreamcast swirl/wordmark -- those are the art's own labels;
#   - sit adjacent to the button where the art leaves room (pad: a compass
#     ring around the face diamond; stick: Z/C/A);
#   - where the art leaves no adjacent room (stick X/Y/B are interior buttons
#     of a 3x2 cluster, hemmed in by the lever, the VMU and each other), the
#     chip moves out to free panel space and the page bakes a leader line to
#     it (CTL_LEADS in gen_menu_assets.py).
# The pad art is a face view with no visible triggers, so LTRIG/RTRIG sit in
# the shoulder corners beside baked "L TRIGGER"/"R TRIGGER" tags.
PAD_ANCHORS   = {"A": (343, 187), "B": (478, 131), "X": (218, 136),
                 "Y": (350, 76), "LTRIG": (12, 44), "RTRIG": (466, 44)}
STICK_ANCHORS = {"A": (200, 206), "B": (440, 178), "X": (10, 193),
                 "Y": (440, 30), "Z": (400, 79), "C": (400, 128)}

SHEET_W, SHEET_H = 640, 1024    # fixed; generator asserts everything fits

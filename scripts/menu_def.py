"""T9 menu single source: settings rows, labels, layout constants.

Read by gen_menu_assets.py (renders loader/menu_sheet.png + loader/controls.png
and emits loader/menu_layout.h). SETTINGS rows transcribed verbatim from the
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

CONTROLS_ROWS = [   # verbatim from docs/kb/input-map.md §DC pad map.
                    # T16: no longer rendered -- the controls page shows
                    # loader/controls_diagram.png; kept as the textual ground
                    # truth the diagram's labels are verified against.
    ("D-PAD / STICK", "MOVE (8-WAY)"),
    ("A",             "M - MAIN"),
    ("X",             "S - SUB"),
    ("B / L TRIGGER", "ACTION"),
    ("Y",             "BARRAGE"),
    ("R TRIGGER",     "OVERDRIVE"),
    ("START",         "START"),
]

SHEET_W, SHEET_H = 640, 768     # fixed; generator asserts everything fits

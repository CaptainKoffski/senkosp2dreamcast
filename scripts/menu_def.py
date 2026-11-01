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
# column is x480 (gen_menu_assets.SCOL_R). B is new: its row sits between
# OVERDRIVE and ACTION so the column still reads top-down.
STICK_ANCHORS = {"X": (10, 18), "Y": (480, 53), "Z": (480, 83), "C": (480, 111),
                 "B": (480, 136), "A": (480, 161)}

# Rows: class-major (P1 PAD, P2 PAD, P1 STICK, P2 STICK); row i is class
# i // CTL_PORTS, port i % CTL_PORTS.
CTL_CLASSES = [("PAD", PAD_BUTTONS, PAD_LAYOUTS, PAD_ANCHORS),
               ("STICK", STICK_BUTTONS, STICK_LAYOUTS, STICK_ANCHORS)]
CTL_ROW_ITEMS = [f"P{p + 1} {name} LAYOUT" for name, *_ in CTL_CLASSES
                 for p in range(CTL_PORTS)]

# ---- VMU persistence (spec docs/superpowers/specs/2026-11-01-vmu-persistence-design.md) --
# Status line under the top menu: "{}" = the VMU slot token, always the last
# word (the generator blits message + token as two strips so the token can be
# any of VMU_SLOTS). Dict order = the MENU_VMU_* index in menu_layout.h.
VMU_SLOTS = ["A1", "A2", "B1", "B2", "C1", "C2", "D1", "D2"]      # index = port*2 + unit-1
VMU_LINES = {                                                     # dict order = MENU_VMU_* index; "{}" = slot token, always last
    "LOADED": "LOADED FROM VMU {}", "SAVED": "SAVED TO VMU {}", "SAVING": "SAVING TO VMU {}",
    "ASK": "SAVE SETTINGS TO VMU {}", "REPLACE": "REPLACE SAVE ON VMU {}",
    "FULL": "NEED 2 FREE BLOCKS ON VMU {}", "FAILED": "SAVE FAILED ON VMU {}",
    "NOCARD": "NO VMU: CHANGES WON'T BE KEPT", "DECLINED": "NOT SAVED: KEPT UNTIL POWER OFF",
}
VMU_PROMPT_FOOTERS = ["A: YES   B: NO", "A: YES   B: NO   LEFT/RIGHT: OTHER VMU"]   # [1] when > 1 card
VMU_ICON_TEXT = "SR"
VMU_FILE = {"name": "SENKOSP_SYS", "short": "SENKO NO RONDE",
            "long": "DC PORT SETTINGS AND CONTROLS", "app": "SENKOSP2DC"}

SHEET_W, SHEET_H = 640, 1536    # fixed; generator asserts everything fits

# Phase 7 T9 — Pre-game Menu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A boot-time menu in the loader — START GAME (default) / SETTINGS (full native GAME ASSIGNMENTS list) / CONTROLS (control-scheme screen) — that writes the chosen bytes into the shim's baked EEPROM image before handoff.

**Architecture:** New `loader/menu.c` runs after the boot-combo check and before the load path (which stays untouched); it blits offline-generated image assets (one sprite sheet + one full-screen controls image) and polls pad 1. On START GAME the loader builds the 16-byte EEPROM game record, computes the Naomi CRC-16, and pokes the game area into the staged shim blob's `eeprom_img` — the shim's proven EEPROM RAM-copy path does the rest. Stateless: defaults every power-on.

**Tech Stack:** KOS (from `../cleopatra/tools/kos/environ.sh`), sh-elf toolchain, Python 3 (stdlib for build scripts; Pillow for the offline asset generator only), instrumented Flycast (`../cleopatra/tools/flycast-src/build/Flycast.app`).

**Spec:** `docs/superpowers/specs/2026-09-11-phase7-t9-pregame-menu-design.md`

## Global Constraints

- Never commit or upload ROM/BIOS/disc bytes or extracted game assets. Menu assets must be OUR OWN generated art (text/shapes rendered by our script) — never pixels copied from the game.
- Release builds are serial-silent (serial-SD dongles use the SCIF pins). All diag output goes behind `SERIAL=1`-style knobs; release ships with every knob off.
- Every KOS/loader build needs `source ../cleopatra/tools/kos/environ.sh` first (path relative to repo root; see `docs/kb/tooling.md`).
- Leg logs under `captures/` are primary data — the capture scripts refuse to overwrite; never delete or rename a leg log except by hand with intent.
- Operator legs (a human at Flycast's GUI or the real DC) are stop-and-wait: post the protocol, stop, wait for the human's report. Never fake or skip them.
- Record every new tool install (name, version, exact command) in `docs/kb/tooling.md`.
- Every hardware/behavioral claim added to the KB carries a citation; primary sources outrank wikis.
- The 16-byte EEPROM game record lives at image `0x2C..0x3B`, duplicated at `0x3C..0x4B`, with two 4-byte headers at `0x24..0x2B`; header layout is `[crc_lo][crc_hi][0x10][0x10]` (CRC-16 little-endian + record length twice). Verified this session against three Flycast-BIOS-written areas: DEFAULT record CRC `0x1e1c`, Event record `0x544f` (stored bytes `4f 54 10 10`), Task-18 easy record `0x6808`.
- Known field map so far (`docs/kb/phase5-hardware.md` §EEPROM game record): idx4 = Event mode (0/1), idx6 = difficulty (01 default, 00 easy), idx10/idx14 unidentified (changed with difficulty). DEFAULT record hex: `23511703000101020200460096004600`.

---

### Task 1: EEPROM game-area diff helper (`eeprom_game_diff.py`)

The recon leg (Task 2) needs a one-command decode/diff of Flycast's saved EEPROM so the human can flip one setting, quit, and read the byte change in seconds.

**Files:**
- Create: `scripts/eeprom_game_diff.py`
- Create: `scripts/test_eeprom_game_diff.py`
- Modify: `Makefile:143-146` (add the test to the `test:` target)

**Interfaces:**
- Produces: CLI `python3 scripts/eeprom_game_diff.py <eeprom-file> [prev-record-hex]` → prints record hex, CRC validity, copies-equal, and per-byte diff vs `prev-record-hex`. Also importable: `crc16(buf: bytes) -> int`, `decode(image: bytes) -> dict` (keys `rec` (bytes, 16), `crc_stored` (int), `crc_ok` (bool), `copies_ok` (bool), `headers_ok` (bool)).
- Consumes: nothing from this repo (stdlib only).

- [ ] **Step 1: Write the failing test**

```python
#!/usr/bin/env python3
"""Self-check for eeprom_game_diff.py (T9 recon helper).

Vectors are the three Flycast-BIOS-written game records already in the KB
(docs/kb/phase5-hardware.md §EEPROM game record); the event-area 40-byte hex
is recorded verbatim there, so decode() is tested against a REAL BIOS-written
area, not our own encoder.
"""
import sys
sys.path.insert(0, "scripts")   # run from repo root: python3 scripts/test_...
from eeprom_game_diff import crc16, decode

DEFAULT = bytes.fromhex("23511703000101020200460096004600")
EVENT   = bytes.fromhex("23511703010101020200460096004600")
EASY    = bytes.fromhex("23511703000100020200780096006e00")

assert crc16(DEFAULT) == 0x1e1c
assert crc16(EVENT)   == 0x544f
assert crc16(EASY)    == 0x6808

# Real BIOS-written area (docs/kb/phase5-hardware.md, event bake): headers
# [crc_lo crc_hi 0x10 0x10] x2, then the record twice.
area = bytes.fromhex(
    "4f5410104f5410102351170301010102020046009600460023511703010101020200460096004600")
img = bytes(0x24) + area + bytes(128 - 0x24 - 40)   # pad to a 128-B image
d = decode(img)
assert d["rec"] == EVENT
assert d["crc_stored"] == 0x544f
assert d["crc_ok"] and d["copies_ok"] and d["headers_ok"]

# Corrupt one record byte: crc_ok and copies_ok must both trip.
bad = bytearray(img); bad[0x2c] ^= 0xff
d = decode(bytes(bad))
assert not d["crc_ok"] and not d["copies_ok"]

print("test_eeprom_game_diff OK")
```

Note the import: the test runs from repo root (`python3 scripts/test_eeprom_game_diff.py`), so `sys.path.insert(0, "scripts")` — same convention as needed for a flat scripts dir; if the sibling tests do it differently (check `scripts/test_parse_cartlog.py`'s first lines), copy that convention instead.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 scripts/test_eeprom_game_diff.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'eeprom_game_diff'`

- [ ] **Step 3: Write the helper**

```python
#!/usr/bin/env python3
"""Decode/diff the game area (0x24..0x4B) of a Naomi EEPROM image.

T9 recon helper: flip ONE item in Flycast's GAME ASSIGNMENTS menu, exit-save,
quit Flycast, then run this against
  ~/Library/Application Support/Flycast/data/senkosp.zip.eeprom
It prints the 16-byte game record, validates CRC/copies/headers, and diffs
against the previous record if given. Stdlib-only (build-tool rule).

CRC: port of Flycast eeprom_crc (naomi_flashrom.cpp:26-51, the emulator's
implementation of the Naomi BIOS algorithm; KB cite
docs/kb/phase4-conversion.md §EEPROM). Header: [crc_lo][crc_hi][0x10][0x10].

Usage:
  eeprom_game_diff.py EEPROM_FILE [PREV_RECORD_HEX]
"""
import sys


def crc16(buf):
    n = 0xdebdeb00
    for b in buf:
        n = (n & 0xffffff00) + b
        for _ in range(8):
            n = ((n << 1) + 0x10210000) & 0xffffffff if n & 0x80000000 \
                else (n << 1) & 0xffffffff
    for _ in range(8):
        n = ((n << 1) + 0x10210000) & 0xffffffff if n & 0x80000000 \
            else (n << 1) & 0xffffffff
    return n >> 16


def decode(image):
    hdr1, hdr2 = image[0x24:0x28], image[0x28:0x2c]
    rec1, rec2 = image[0x2c:0x3c], image[0x3c:0x4c]
    crc_stored = hdr1[0] | (hdr1[1] << 8)
    return {
        "rec": rec1,
        "crc_stored": crc_stored,
        "crc_ok": crc16(rec1) == crc_stored,
        "copies_ok": rec1 == rec2,
        "headers_ok": hdr1 == hdr2 and hdr1[2] == 16 and hdr1[3] == 16,
    }


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    image = open(sys.argv[1], "rb").read()
    d = decode(image)
    print(f"record: {d['rec'].hex()}")
    print(f"crc stored={d['crc_stored']:04x} ok={d['crc_ok']} "
          f"copies_ok={d['copies_ok']} headers_ok={d['headers_ok']}")
    if len(sys.argv) > 2:
        prev = bytes.fromhex(sys.argv[2])
        changed = [(i, prev[i], d["rec"][i]) for i in range(16)
                   if prev[i] != d["rec"][i]]
        for i, a, b in changed:
            print(f"idx{i}: {a:02x} -> {b:02x}")
        if not changed:
            print("no change")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 scripts/test_eeprom_game_diff.py`
Expected: `test_eeprom_game_diff OK`

- [ ] **Step 5: Wire into `make test`**

In the top `Makefile`, the `test:` target (line ~143) runs the script tests; add ours after `test_maple_literals.py`:

```make
	python3 scripts/test_eeprom_game_diff.py
```

Run: `make test`
Expected: shims host tests + all script tests pass, including the new line.

- [ ] **Step 6: Commit**

```bash
git add scripts/eeprom_game_diff.py scripts/test_eeprom_game_diff.py Makefile
git commit -m "phase7 T9 task 1: eeprom game-area decode/diff helper (recon tooling)"
```

---

### Task 2: Recon leg — GAME ASSIGNMENTS byte map (OPERATOR, emulator)

**This is an operator leg: prepare the protocol, post it, STOP, and wait for the human's results.** Nothing downstream of Task 3 should be considered final until this table exists — Task 4 transcribes it.

**Files:**
- Modify: `docs/kb/phase7-polishing.md` (new `### T9 RECON — GAME ASSIGNMENTS byte map` subsection under the T9 entry)
- Modify: `docs/kb/tooling.md` (leg record if any logs are captured)

**Interfaces:**
- Produces: a KB table, one row per GAME ASSIGNMENTS item: on-screen label, record byte index (0..15), encoding (`value label` ↔ byte), default byte. This table is the single source Task 4 transcribes into `scripts/menu_def.py`.
- Consumes: `scripts/eeprom_game_diff.py` (Task 1).

- [ ] **Step 1: Post the operator protocol and wait**

Post exactly this protocol (paths verified: eeprom file per `docs/kb/tooling.md` §EEPROM game-area bake hook; keyboard map per `docs/kb/input-map.md`: Test = T, Service = Q):

> **T9 recon leg — needs you at Flycast's GUI (Naomi profile, ~20 min).**
> 1. Launch stock-config Flycast with `roms/senkosp.zip` (Naomi profile — the plain ROM, not our disc build).
> 2. Enter the test menu (Test = `T`), go to `GAME ASSIGNMENTS`. **Screenshot the full list** (every item + its current value). Report the list.
> 3. Select `restore defaults` (if present), `SYSTEM MENU EXIT` (saves), quit Flycast. Run:
>    `python3 scripts/eeprom_game_diff.py ~/Library/Application\ Support/Flycast/data/senkosp.zip.eeprom`
>    Report the printed record hex — this is the baseline (expected `23511703000101020200460096004600`).
> 4. For EACH item in GAME ASSIGNMENTS, for EACH of its values: relaunch, change that ONE item one step, exit-save, quit, rerun the helper with the previous record hex as the second argument. Note `item, value label, idxN: old -> new`. (Service = `Q` moves, Test = `T` selects, per the game's own footer.)
> 5. Report the full list of (item, value label, byte) rows and anything odd (items that change two bytes, items that change nothing).

STOP HERE until the operator reports.

- [ ] **Step 2: Write the KB table**

From the operator's report, add to `docs/kb/phase7-polishing.md` under the T9 pool entry:

```markdown
### T9 RECON — GAME ASSIGNMENTS byte map (2026-09-XX, operator emulator leg)

Method: stock Naomi-profile Flycast, one item flipped per save-quit cycle,
`scripts/eeprom_game_diff.py` diff of `senkosp.zip.eeprom` (the Task-18 /
event-bake method, tooling.md §EEPROM game-area bake hook). BIOS-written
areas validated (crc_ok/copies_ok/headers_ok all true on every capture).

| GAME ASSIGNMENTS item | record idx | values (label = byte) | default |
|---|---|---|---|
| <from operator> | ... | ... | ... |

<notes: multi-byte items, unreachable values, anything odd>
```

Every row must come from an observed diff — no wiki values. If an item changes two bytes together (the idx10/idx14 pattern), record BOTH indices in that row; the menu treats it as one setting writing two bytes (Task 4 handles this via one row per byte with linked labels — see Task 4 Step 1 note).

- [ ] **Step 3: Commit**

```bash
git add docs/kb/phase7-polishing.md docs/kb/tooling.md
git commit -m "phase7 T9 task 2: GAME ASSIGNMENTS byte map (operator recon leg)"
```

---

### Task 3: Naomi CRC + game-area builder, host-tested

**Files:**
- Create: `loader/naomi_crc.c`
- Create: `loader/naomi_crc.h`
- Create: `shims/test/test_naomi_crc.c`
- Modify: `shims/Makefile:27-33` (test target)
- Modify: `loader/Makefile:4` (add `naomi_crc.o` to `OBJS`)

**Interfaces:**
- Produces: `unsigned short naomi_eeprom_crc(const unsigned char *buf, int size);` and `void naomi_build_game_area(unsigned char out[40], const unsigned char rec[16]);` — `out` = the full `0x24..0x4B` area: header ×2 (`crc_lo, crc_hi, 0x10, 0x10`), record ×2. Freestanding C, no KOS includes (host-testable, links into the loader).
- Consumes: nothing.

- [ ] **Step 1: Write the failing test**

`shims/test/test_naomi_crc.c` (pattern: `test_gd_math.c` — plain `cc`, assert, print OK):

```c
/* Host test of the T9 Naomi EEPROM CRC + game-area builder.
 * Vectors: the three Flycast-BIOS-written game records in the KB
 * (docs/kb/phase5-hardware.md §EEPROM game record); the event-area bytes are
 * recorded there verbatim, so the builder is checked against a REAL
 * BIOS-written area, not itself. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../../loader/naomi_crc.h"

static const unsigned char DEF[16] = {0x23,0x51,0x17,0x03,0x00,0x01,0x01,0x02,
                                      0x02,0x00,0x46,0x00,0x96,0x00,0x46,0x00};
static const unsigned char EVT[16] = {0x23,0x51,0x17,0x03,0x01,0x01,0x01,0x02,
                                      0x02,0x00,0x46,0x00,0x96,0x00,0x46,0x00};
static const unsigned char EZY[16] = {0x23,0x51,0x17,0x03,0x00,0x01,0x00,0x02,
                                      0x02,0x00,0x78,0x00,0x96,0x00,0x6e,0x00};
/* The BIOS-written event area, byte-for-byte (KB). */
static const unsigned char EVT_AREA[40] = {
    0x4f,0x54,0x10,0x10, 0x4f,0x54,0x10,0x10,
    0x23,0x51,0x17,0x03,0x01,0x01,0x01,0x02,0x02,0x00,0x46,0x00,0x96,0x00,0x46,0x00,
    0x23,0x51,0x17,0x03,0x01,0x01,0x01,0x02,0x02,0x00,0x46,0x00,0x96,0x00,0x46,0x00};

int main(void) {
    assert(naomi_eeprom_crc(DEF, 16) == 0x1e1c);
    assert(naomi_eeprom_crc(EVT, 16) == 0x544f);
    assert(naomi_eeprom_crc(EZY, 16) == 0x6808);
    unsigned char a[40];
    naomi_build_game_area(a, EVT);
    assert(!memcmp(a, EVT_AREA, 40));          /* byte-identical to the BIOS's */
    printf("test_naomi_crc OK\n");
    return 0;
}
```

- [ ] **Step 2: Add the build line and verify it fails**

In `shims/Makefile`, append to the `test:` recipe (after the `test_gd_math` line):

```make
	cc -o $(B)/test_naomi_crc test/test_naomi_crc.c ../loader/naomi_crc.c && $(B)/test_naomi_crc
```

Run: `make -C shims test`
Expected: FAIL — `naomi_crc.h: No such file or directory`

- [ ] **Step 3: Write the implementation**

`loader/naomi_crc.h`:

```c
/* T9: Naomi EEPROM CRC-16 + game-area builder. Freestanding (host-tested by
 * shims/test/test_naomi_crc.c; linked into the loader for the menu poke). */
#ifndef NAOMI_CRC_H
#define NAOMI_CRC_H
unsigned short naomi_eeprom_crc(const unsigned char *buf, int size);
void naomi_build_game_area(unsigned char out[40], const unsigned char rec[16]);
#endif
```

`loader/naomi_crc.c`:

```c
/* Port of Flycast's eeprom_crc (naomi_flashrom.cpp:26-51 -- the emulator's
 * implementation of the Naomi BIOS algorithm; KB cite
 * docs/kb/phase4-conversion.md §EEPROM: both stored CRCs of our captured
 * image recompute correctly under it). Seed 0xdebdeb00, one trailing round,
 * result is the top half. */
#include "naomi_crc.h"

unsigned short naomi_eeprom_crc(const unsigned char *buf, int size) {
    unsigned int n = 0xdebdeb00u;
    for (int i = 0; i < size; i++) {
        n = (n & 0xffffff00u) + buf[i];
        for (int c = 0; c < 8; c++)
            n = (n & 0x80000000u) ? (n << 1) + 0x10210000u : n << 1;
    }
    for (int c = 0; c < 8; c++)
        n = (n & 0x80000000u) ? (n << 1) + 0x10210000u : n << 1;
    return (unsigned short)(n >> 16);
}

/* Game area 0x24..0x4B: [crc_lo crc_hi 0x10 0x10] x2, then the record x2.
 * Header layout verified against three BIOS-written areas (KB §T9 /
 * test_naomi_crc.c): CRC little-endian, 0x10 = record length, twice. */
void naomi_build_game_area(unsigned char out[40], const unsigned char rec[16]) {
    unsigned short c = naomi_eeprom_crc(rec, 16);
    out[0] = (unsigned char)(c & 0xff);
    out[1] = (unsigned char)(c >> 8);
    out[2] = 0x10;
    out[3] = 0x10;
    for (int i = 0; i < 4; i++)  out[4 + i]  = out[i];
    for (int i = 0; i < 16; i++) { out[8 + i] = rec[i]; out[24 + i] = rec[i]; }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `make -C shims test`
Expected: all four host tests pass, ending `test_naomi_crc OK`.

- [ ] **Step 5: Link into the loader**

`loader/Makefile` line 4: `OBJS = main.o handoff.o gd.o gd_sys.o shim_blob.o bios_data.o splash_blob.o naomi_crc.o` (KOS `%.o` pattern rule compiles it). Build check:

```bash
source ../cleopatra/tools/kos/environ.sh && make gdi
```

Expected: builds clean (function is unreferenced until Task 6 — that's fine).

- [ ] **Step 6: Commit**

```bash
git add loader/naomi_crc.c loader/naomi_crc.h shims/test/test_naomi_crc.c shims/Makefile loader/Makefile
git commit -m "phase7 T9 task 3: Naomi EEPROM CRC + game-area builder, host-tested against BIOS-written vectors"
```

---

### Task 4: Menu definition + asset generator + build wiring

**Files:**
- Create: `scripts/menu_def.py` (single source: settings rows, labels, layout)
- Create: `scripts/gen_menu_assets.py` (offline, Pillow — renders the assets)
- Create: `loader/menu_sheet.png`, `loader/controls.png` (generated, committed — our own art)
- Create: `loader/menu_layout.h` (generated, committed)
- Modify: `loader/Makefile` (blob rules for the two images, clean lines, OBJS)
- Modify: `scripts/make_gdi.py:280-283` (boot-region size guard)
- Modify: `docs/kb/tooling.md` (Pillow install record + new-scripts note)

**Interfaces:**
- Produces: `loader/menu_layout.h` — `mrect_t {unsigned short x, y, w, h;}` sheet-source rects plus dest coordinates, all generated:
  - `MENU_SHEET_W` (640), `MENU_BG_COLOR` (RGB565 fill for the settings screen)
  - `MENU_TOP_LABEL[3][2]` (item × normal/highlight src rects), `MENU_TOP_DEST[3][2]` (x, y), `MENU_TOP_FOOTER` + `MENU_TOP_FOOTER_X/_Y`
  - `MENU_N_SETTINGS`, `MENU_MAX_VALUES`, `MENU_SET_LABEL[N][2]`, `MENU_SET_VALUE[N][MENU_MAX_VALUES]`, `MENU_SET_NVAL[N]`, `MENU_SET_IDX[N]` (record byte index), `MENU_SET_IDX2[N]`/`MENU_SET_BYTE2[N][..]` (0xff / unused when single-byte — for recon rows that change two bytes together), `MENU_SET_BYTE[N][MENU_MAX_VALUES]`, `MENU_SET_LABEL_X`, `MENU_SET_VALUE_X`, `MENU_SET_ROW_Y(i)` macro, `MENU_SET_TITLE` + `_X/_Y`, `MENU_SET_FOOTER` + `_X/_Y`
  - `MENU_DEFAULT_RECORD` — 16-byte initializer list matching the KB DEFAULT record
  - Blob symbols (from Makefile objcopy): `menu_sheet_bin[]`, `controls_bin[]`
- Consumes: Task 2's KB byte-map table (transcribed into `menu_def.py`).

- [ ] **Step 1: Install Pillow (offline tool only) and record it**

```bash
python3 -m pip install --user pillow
python3 -c "import PIL; print(PIL.__version__)"
```

Add to `docs/kb/tooling.md` (new dated subsection "T9 menu asset generator"): the exact command, the version printed, and the rule that Pillow is generator-only — `loader/Makefile` stays stdlib+sips (`bmp2rgb565.py` header comment states that rule; do not break it).

- [ ] **Step 2: Write `scripts/menu_def.py`** — transcribe the Task 2 table

```python
"""T9 menu single source: settings rows, labels, layout constants.

Read by gen_menu_assets.py (renders loader/menu_sheet.png + loader/controls.png
and emits loader/menu_layout.h). SETTINGS rows transcribed from the T9 recon
table (docs/kb/phase7-polishing.md §T9 RECON) -- byte index into the 16-byte
game record, (label, byte) per value, verbatim. A row that changes TWO bytes
together (the idx10/idx14 class) carries idx2/bytes2; single-byte rows use
idx2=None.
"""
DEFAULT_RECORD = "23511703000101020200460096004600"   # KB §EEPROM game record

TOP_ITEMS = ["START GAME", "SETTINGS", "CONTROLS"]
TOP_FOOTER = "UP/DOWN: MOVE   A: SELECT"
SET_FOOTER = "UP/DOWN: ITEM   LEFT/RIGHT: CHANGE   B: BACK"

# (label, idx, [(value_label, byte), ...], idx2, [byte2, ...] or None)
SETTINGS = [
    # FROM THE RECON TABLE -- the two rows below are the already-mapped
    # fields and MUST be replaced/extended to the full recon table:
    ("EVENT MODE", 4, [("OFF", 0x00), ("ON", 0x01)], None, None),
    ("DIFFICULTY", 6, [("EASY", 0x00), ("NORMAL", 0x01)], None, None),
]

CONTROLS_ROWS = [   # verbatim from docs/kb/input-map.md §DC pad map
    ("D-PAD / STICK", "MOVE (8-WAY)"),
    ("A",             "M - MAIN"),
    ("X",             "S - SUB"),
    ("B / L TRIGGER", "ACTION"),
    ("Y",             "BARRAGE"),
    ("R TRIGGER",     "OVERDRIVE"),
    ("START",         "START"),
]

SHEET_W, SHEET_H = 640, 768     # fixed; generator asserts everything fits
```

Transcription rules: one tuple per recon-table row, labels uppercased as the game's test menu spells them, bytes verbatim. After writing, cross-check by eye: for every row, the byte for its default label must equal `DEFAULT_RECORD`'s byte at that idx (the generator asserts this too).

- [ ] **Step 3: Write `scripts/gen_menu_assets.py`**

Requirements (implement exactly; rendering details like font size may be tuned to fit):

```python
#!/usr/bin/env python3
"""T9 offline asset generator (Pillow -- NOT a build dependency; outputs are
committed). Renders loader/menu_sheet.png (640x768 sprite sheet) and
loader/controls.png (640x480), and emits loader/menu_layout.h with every
sheet rect + dest coordinate + the settings byte tables from menu_def.py.

All art is drawn here (text + flat shapes) -- never pixels from the game
(copyright rule, CLAUDE.md). Rerun after any menu_def.py change:
    python3 scripts/gen_menu_assets.py
"""
```

Behavior:
1. Fonts: use `/System/Library/Fonts/Supplemental/Arial Bold.ttf` (assert it exists; it's stock macOS). Sizes: ~28 px top-menu labels, ~20 px settings rows/footers, ~24 px titles.
2. Sheet layout (top-left packing, y advances per band; generator tracks a cursor):
   - 3 top-menu labels × 2 variants: 320×36 bands, text centered. Normal: white text on near-black (#101018); highlight: black text on amber (#e0a020) — placeholder palette, operator iterates style in the hardware round.
   - Top footer: 640×24 band, grey text on near-black.
   - Settings title `SETTINGS`: 640×32.
   - Per settings row: label plate 288×28 × 2 variants (normal/highlight), left-aligned text.
   - Per value: chip 288×28, centered text, one variant (the row highlight lives on the label plate).
   - Settings footer: 640×24.
   - Assert final cursor ≤ SHEET_H; pad the sheet image to exactly 640×768 with #101018.
3. `controls.png` 640×480: title `CONTROLS` top-center, then `CONTROLS_ROWS` as two-column rows (button left column x≈120, action x≈340, ~34 px pitch starting y≈120), footer `B: BACK` at y≈440. Background #101018, white text, amber column for the button names.
4. Emit `loader/menu_layout.h`:
   - Banner: `/* GENERATED by scripts/gen_menu_assets.py from scripts/menu_def.py -- do not edit. Committed alongside the PNGs it describes. */`
   - `typedef struct { unsigned short x, y, w, h; } mrect_t;` guarded by `#ifndef MENU_LAYOUT_H`.
   - All tables listed in **Interfaces** above as `static const` arrays; dest coords: top-menu labels centered at x=(640−w)/2, y = 310/354/398; top footer y=452; settings rows `MENU_SET_LABEL_X 48`, `MENU_SET_VALUE_X 344`, `#define MENU_SET_ROW_Y(i) (96 + (i) * 34)`; title y=40; footer y=452.
   - `MENU_BG_COLOR`: RGB565 of #101018, computed by the generator (`(r>>3)<<11 | (g>>2)<<5 | b>>3`) — never hand-derived.
   - `#define MENU_DEFAULT_RECORD {0x23,0x51,...}` from `DEFAULT_RECORD`.
   - `MENU_MAX_VALUES` = max row value count; pad `MENU_SET_VALUE`/`MENU_SET_BYTE` rows with `{0,0,0,0}` rects / `0` bytes up to it.
   - Assert: every row's default-byte (from `DEFAULT_RECORD[idx]`) appears in its value list; assert `MENU_N_SETTINGS * 34 + 96 <= 440` (rows fit above the footer).
5. Print a one-line summary (sheet fill %, n rows, n chips).

- [ ] **Step 4: Generate and VIEW the outputs**

```bash
python3 scripts/gen_menu_assets.py
```

Then **view** `loader/menu_sheet.png` and `loader/controls.png` with the Read tool (verification-discipline: view decoded images before claiming they're right). Check: no clipped text, variants aligned, controls table complete and matching `docs/kb/input-map.md`. Skim `loader/menu_layout.h`: rects sane, byte tables match `menu_def.py`.

- [ ] **Step 5: Build wiring**

`loader/Makefile`:
- `OBJS` += `menu_sheet_blob.o controls_blob.o` (and keep `naomi_crc.o` from Task 3; `menu.o` arrives in Task 5).
- After the splash rules, add (mirror the splash pattern exactly — sips + bmp2rgb565 with explicit sizes, objcopy with redefined symbols):

```make
../build/menu_sheet.bin: menu_sheet.png ../scripts/bmp2rgb565.py
	mkdir -p ../build
	sips -s format bmp menu_sheet.png --out ../build/menu_sheet.bmp > /dev/null
	python3 ../scripts/bmp2rgb565.py ../build/menu_sheet.bmp $@ 640 768
menu_sheet_blob.o: ../build/menu_sheet.bin
	sh-elf-objcopy -I binary -O elf32-shl -B sh4 \
	  --redefine-sym _binary____build_menu_sheet_bin_start=_menu_sheet_bin \
	  --redefine-sym _binary____build_menu_sheet_bin_end=_menu_sheet_bin_end \
	  $< $@
../build/controls.bin: controls.png ../scripts/bmp2rgb565.py
	mkdir -p ../build
	sips -s format bmp controls.png --out ../build/controls.bmp > /dev/null
	python3 ../scripts/bmp2rgb565.py ../build/controls.bmp $@ 640 480
controls_blob.o: ../build/controls.bin
	sh-elf-objcopy -I binary -O elf32-shl -B sh4 \
	  --redefine-sym _binary____build_controls_bin_start=_controls_bin \
	  --redefine-sym _binary____build_controls_bin_end=_controls_bin_end \
	  $< $@
```

- Add `../build/menu_sheet.bin ../build/menu_sheet.bmp ../build/controls.bin ../build/controls.bmp` to `clean:` (the splash clean comment explains why generated .bins must die on clean — same reason).

`scripts/make_gdi.py`: immediately before `t4.write(ldr)` (line ~281) add the missing size guard — today an oversized loader silently corrupts the layout (`b"\0" * negative` = empty):

```python
    assert len(ldr) <= BOOT_FILE_SIZE, \
        f"1ST_READ.BIN {len(ldr)} B exceeds donor FS size {BOOT_FILE_SIZE}"
```

- [ ] **Step 6: Build and verify sizes**

```bash
source ../cleopatra/tools/kos/environ.sh && make gdi
ls -l build/1ST_READ.BIN
```

Expected: builds clean; `1ST_READ.BIN` grew by roughly the two blobs (~1.6 MB) and is < 3,538,016 B; `make_gdi.py` prints its OK line (assert silent).

- [ ] **Step 7: Commit**

```bash
git add scripts/menu_def.py scripts/gen_menu_assets.py loader/menu_sheet.png \
  loader/controls.png loader/menu_layout.h loader/Makefile scripts/make_gdi.py \
  docs/kb/tooling.md
git commit -m "phase7 T9 task 4: menu asset pipeline (menu_def -> generated sheet/controls/layout) + gdi size guard"
```

---

### Task 5: `loader/menu.c` — the menu itself

**Files:**
- Create: `loader/menu.c`, `loader/menu.h`
- Modify: `loader/main.c:251` (call site, after the boot-combo block closes)
- Modify: `loader/Makefile` (OBJS += `menu.o`; header deps)
- Modify: `Makefile` (top): `MENU=0` knob

**Interfaces:**
- Consumes: `menu_layout.h` tables (Task 4), `naomi_crc.h` (not yet — Task 6 does the poke), KOS maple/vram as used in `main.c`.
- Produces: `void menu_run(void);` — blocks until START GAME is chosen, leaves the splash repainted; `extern unsigned char menu_game_record[16];` (the session record, defaults-initialized) and `extern int menu_dirty;` (1 iff any setting was changed). `main.c` consumes both in Task 6.

- [ ] **Step 1: Write `loader/menu.h`**

```c
/* T9 pre-game menu (spec docs/superpowers/specs/2026-09-11-phase7-t9-pregame-menu-design.md). */
#ifndef MENU_H
#define MENU_H
extern unsigned char menu_game_record[16];   /* session record, defaults each boot */
extern int menu_dirty;                       /* 1 iff a setting was changed */
void menu_run(void);   /* blocks until START GAME; repaints the splash on exit */
#endif
```

- [ ] **Step 2: Write `loader/menu.c`**

```c
/* T9 pre-game menu: START GAME / SETTINGS / CONTROLS, drawn by blitting
 * rects from the offline-generated sheet (menu_layout.h -- regenerate with
 * scripts/gen_menu_assets.py after any scripts/menu_def.py change). Pad 1
 * polled the same way main.c's boot-combo check does. Stateless: the record
 * starts at the baked defaults every boot; the staged-EEPROM poke consuming
 * menu_game_record/menu_dirty lives in main.c. */
#include <kos.h>
#include "menu.h"
#include "menu_layout.h"

extern uint8 splash_bin[];
extern uint8 menu_sheet_bin[];
extern uint8 controls_bin[];

unsigned char menu_game_record[16] = MENU_DEFAULT_RECORD;
int menu_dirty = 0;

static void blit(mrect_t src, int dx, int dy) {
    const uint16 *sheet = (const uint16 *)menu_sheet_bin;
    for (int row = 0; row < src.h; row++)
        memcpy(vram_s + (dy + row) * 640 + dx,
               sheet + (src.y + row) * MENU_SHEET_W + src.x, src.w * 2);
}

/* One ~60 Hz poll; returns newly-pressed buttons (edge detect). A missing /
 * unplugged pad reads as 0 -- the menu just waits. */
static uint32 edge(void) {
    static uint32 prev;
    maple_device_t *c = maple_enum_type(0, MAPLE_FUNC_CONTROLLER);
    cont_state_t *st = c ? (cont_state_t *)maple_dev_status(c) : NULL;
    uint32 cur = st ? (uint32)st->buttons : 0;
    uint32 e = cur & ~prev;
    prev = cur;
    thd_sleep(16);
    return e;
}

static void draw_top(int cur) {
    memcpy(vram_s, splash_bin, 640 * 480 * 2);
    for (int i = 0; i < 3; i++)
        blit(MENU_TOP_LABEL[i][i == cur],
             MENU_TOP_DEST[i][0], MENU_TOP_DEST[i][1]);
    blit(MENU_TOP_FOOTER, MENU_TOP_FOOTER_X, MENU_TOP_FOOTER_Y);
}

static void draw_settings(int cur, const int *val) {
    for (int i = 0; i < 640 * 480; i++) vram_s[i] = MENU_BG_COLOR;
    blit(MENU_SET_TITLE, MENU_SET_TITLE_X, MENU_SET_TITLE_Y);
    for (int i = 0; i < MENU_N_SETTINGS; i++) {
        blit(MENU_SET_LABEL[i][i == cur], MENU_SET_LABEL_X, MENU_SET_ROW_Y(i));
        blit(MENU_SET_VALUE[i][val[i]],   MENU_SET_VALUE_X, MENU_SET_ROW_Y(i));
    }
    blit(MENU_SET_FOOTER, MENU_SET_FOOTER_X, MENU_SET_FOOTER_Y);
}

static void apply_row(int i, int v) {
    menu_game_record[MENU_SET_IDX[i]] = MENU_SET_BYTE[i][v];
    if (MENU_SET_IDX2[i] != 0xff)               /* two-byte rows (recon) */
        menu_game_record[MENU_SET_IDX2[i]] = MENU_SET_BYTE2[i][v];
    menu_dirty = 1;
}

static void settings_screen(void) {
    int val[MENU_N_SETTINGS], cur = 0;
    for (int i = 0; i < MENU_N_SETTINGS; i++) {   /* current record -> indices */
        val[i] = 0;
        for (int v = 0; v < MENU_SET_NVAL[i]; v++)
            if (MENU_SET_BYTE[i][v] == menu_game_record[MENU_SET_IDX[i]])
                val[i] = v;
    }
    draw_settings(cur, val);
    for (;;) {
        uint32 e = edge();
        if (e & CONT_B) return;
        if (e & CONT_DPAD_UP)
            cur = (cur + MENU_N_SETTINGS - 1) % MENU_N_SETTINGS;
        if (e & CONT_DPAD_DOWN)
            cur = (cur + 1) % MENU_N_SETTINGS;
        if (e & (CONT_DPAD_LEFT | CONT_DPAD_RIGHT)) {
            int n = MENU_SET_NVAL[cur];
            val[cur] = (val[cur] + ((e & CONT_DPAD_RIGHT) ? 1 : n - 1)) % n;
            apply_row(cur, val[cur]);
        }
        if (e) draw_settings(cur, val);
    }
}

static void controls_screen(void) {
    memcpy(vram_s, controls_bin, 640 * 480 * 2);
    for (;;)
        if (edge() & CONT_B) return;
}

void menu_run(void) {
    int cur = 0;
    draw_top(cur);
    for (;;) {
        uint32 e = edge();
        if (e & CONT_START) break;               /* start from anywhere */
        if (e & CONT_DPAD_UP)   { cur = (cur + 2) % 3; draw_top(cur); }
        if (e & CONT_DPAD_DOWN) { cur = (cur + 1) % 3; draw_top(cur); }
        if (e & CONT_A) {
            if (cur == 0) break;
            if (cur == 1) settings_screen();
            else          controls_screen();
            draw_top(cur);
        }
    }
    memcpy(vram_s, splash_bin, 640 * 480 * 2);   /* today's load screen */
}
```

- [ ] **Step 3: Call site + knob**

`loader/main.c` — after the boot-combo block (the `{...}` closing at line 251), before `uint32 img_off = ...`:

```c
#ifndef LOADER_MENU
#define LOADER_MENU 1   /* T9 pre-game menu; MENU=0 (top Makefile) disables it
                         * for unattended legs that must boot straight to
                         * attract (the menu waits for input forever). */
#endif
#if LOADER_MENU
    /* T9: main-image boots only -- the A+Start combo goes to the game's own
     * test menu, which IS a settings UI already. */
    if (!test_boot) menu_run();
#endif
```

Add `#include "menu.h"` next to the `shim_iface.h` include.

Top `Makefile`, next to the other knobs:

```make
# MENU=0: build without the T9 pre-game menu -- for unattended emulator legs
# (attract sits, VMU canaries): the menu waits for input forever, so a
# menu build never reaches attract on its own. Release ships menu ON.
ifeq ($(MENU),0)
DEFS += -DLOADER_MENU=0
endif
```

`loader/Makefile`: `OBJS` += `menu.o`; add dep line `menu.o main.o: menu.h menu_layout.h` (keep the existing `main.o:` dep line's entries too — merge, don't duplicate the target).

- [ ] **Step 4: Build both flavors**

```bash
source ../cleopatra/tools/kos/environ.sh
make gdi && md5 build/1ST_READ.BIN
make clean >/dev/null; make gdi MENU=0 && md5 build/1ST_READ.BIN
make clean >/dev/null; make gdi     # leave the menu build in place
```

Expected: both build; different md5s; no size-guard trip.

- [ ] **Step 5: Unattended screenshot leg — the menu renders**

```bash
FLYCAST_SHOT=$PWD/captures/phase7/t9-menu-shot.png FLYCAST_SHOT_EVERY=100000 \
  scripts/capture_dc_leg.sh phase7/t9-menu-shot &
sleep 45 && kill -USR1 $(pgrep -f "flycast-src.*Flycast") && sleep 5 \
  && pkill -9 -f "flycast-src.*Flycast"
```

(Adjust to the exact capture_dc_leg.sh invocation conventions in `docs/kb/tooling.md` §Screenshots — `kill -USR1` is the reliable grab.) **View the PNG**: expect the splash with the three menu bands, START GAME highlighted, footer legend. The stdout log should show the loader banner and then silence (menu waiting) — no `HANDOFF`.

- [ ] **Step 6: Commit**

```bash
git add loader/menu.c loader/menu.h loader/main.c loader/Makefile Makefile
git commit -m "phase7 T9 task 5: pre-game menu (top/settings/controls screens) + MENU=0 leg knob"
```

---

### Task 6: The EEPROM poke — settings reach the game

**Files:**
- Modify: `scripts/build_patch_table.py:654-671` (emit `EEPROM_IMG_ADDR`)
- Modify: `scripts/test_build_patch_table.py` (assert the define)
- Modify: `loader/main.c:432` (poke block after the `GD_STACK_CANARY` store, before the dcache purges)
- Modify: `Makefile` (top): `MENUDIAG=1` knob

**Interfaces:**
- Consumes: `menu_game_record`/`menu_dirty` (Task 5), `naomi_build_game_area`/`naomi_eeprom_crc` (Task 3), `EEPROM_IMG_ADDR` (this task), `STAGE_SHIM`/`shim_len`/`shim_bin` (existing `main.c` staging block).
- Produces: the staged shim's `eeprom_img` game area (`+0x24..0x4B`) carries the session record at handoff; `MENUEE` dbglog line (SERIAL builds) prints the poked record + CRC.

- [ ] **Step 1: Emit `EEPROM_IMG_ADDR`**

`scripts/build_patch_table.py`, next to the `_gd_test_server_addr` block (line ~654):

```python
# T9: the baked EEPROM image's runtime address -- the loader pokes the menu's
# session record into the STAGED copy's game area before handoff
# (loader/main.c MENUEE block). sym(), not sym_opt(): every shim build has
# eeprom_img (build/mie_blobs.c).
_eeprom_img_addr = sym("eeprom_img")
```

and in the `out` list, next to the `GD_TEST_SERVER_ADDR` line:

```python
    f"#define EEPROM_IMG_ADDR 0x{_eeprom_img_addr:08x}u",
```

`scripts/test_build_patch_table.py`: where the header text is in hand (after `run_gen()`), add:

```python
m = re.search(r"#define\s+EEPROM_IMG_ADDR\s+0x([0-9a-fA-F]{8})u", text)
assert m and int(m.group(1), 16) != 0, "EEPROM_IMG_ADDR missing/zero"
```

Run: `python3 scripts/test_build_patch_table.py` — expected PASS (fails first if you add the assert before the generator change: do that, watch it fail, then add the generator line — that's the TDD order).

- [ ] **Step 2: The poke block**

`loader/main.c`: add `#include "naomi_crc.h"` next to the other includes. Then insert AFTER the `GD_STACK_CANARY` store (line ~432) and BEFORE the `bios_data` staging memcpys:

```c
#if LOADER_MENUDIAG
    /* T9 unattended byte leg: pretend the menu chose the Task-18 easy record
     * (known-visible in-game: easier campaign). Test-only, never shipped. */
    {
        static const unsigned char ez[16] = {0x23,0x51,0x17,0x03,0x00,0x01,0x00,
                                             0x02,0x02,0x00,0x78,0x00,0x96,0x00,0x6e,0x00};
        memcpy(menu_game_record, ez, 16);
        menu_dirty = 1;
    }
#endif
    /* T9: session settings -> the staged shim's baked EEPROM image (game
     * area +0x24..0x4B: CRC headers x2 + record x2). The shim serves and
     * copies eeprom_img post-handoff (shims/src/main.c), so this staged poke
     * IS the whole write path. Self-check + pristine fallback: a bug here
     * can only ever yield the baked defaults, never a corrupt image. */
    if (menu_dirty) {
        uint32 ee_off = (EEPROM_IMG_ADDR - SHIM_BASE) + 0x24;
        if (EEPROM_IMG_ADDR == 0 || ee_off + 40 > shim_len) {
            dbglog(DBG_INFO, "MENUEE SKIP addr=%08x len=%lx\n",
                   (unsigned)EEPROM_IMG_ADDR, (unsigned long)shim_len);
        } else {
            uint8 *ee = (uint8 *)STAGE_SHIM + ee_off;
            naomi_build_game_area(ee, menu_game_record);
            unsigned short c = naomi_eeprom_crc(ee + 8, 16);
            if (ee[0] != (c & 0xff) || ee[1] != (c >> 8) ||
                memcmp(ee, ee + 4, 4) || memcmp(ee + 8, ee + 24, 16)) {
                memcpy(ee, shim_bin + ee_off, 40);      /* pristine bytes */
                dbglog(DBG_INFO, "MENUEE SELFCHECK FAIL -> defaults\n");
            } else {
                dbglog(DBG_INFO, "MENUEE crc=%04x rec=%02x%02x%02x%02x%02x%02x"
                       "%02x%02x%02x%02x%02x%02x%02x%02x%02x%02x\n", c,
                       ee[8], ee[9], ee[10], ee[11], ee[12], ee[13], ee[14],
                       ee[15], ee[16], ee[17], ee[18], ee[19], ee[20], ee[21],
                       ee[22], ee[23]);
                say("menu: settings applied");
            }
        }
    }
```

Guard the whole block with `#if LOADER_MENU || LOADER_MENUDIAG` / `#endif` so a `MENU=0 MENUDIAG=0` build compiles it out entirely. Add near the knob defines:

```c
#ifndef LOADER_MENUDIAG
#define LOADER_MENUDIAG 0
#endif
```

Top `Makefile`:

```make
# MENUDIAG=1 (pair with SERIAL=1 to hear it, MENU=0 to run unattended): the
# loader force-feeds the Task-18 easy record through the T9 poke path --
# unattended end-to-end check (MENUEE line + easier in-game campaign).
# Test-only, never shipped.
ifeq ($(MENUDIAG),1)
DEFS += -DLOADER_MENUDIAG=1
endif
```

- [ ] **Step 3: Unattended byte leg**

```bash
source ../cleopatra/tools/kos/environ.sh
make clean >/dev/null && make gdi SERIAL=1 MENU=0 MENUDIAG=1
scripts/capture_dc_leg.sh phase7/t9-menudiag &
sleep 90 && pkill -9 -f "flycast-src.*Flycast"
grep MENUEE captures/phase7/t9-menudiag.stdout.log
```

Expected: exactly one `MENUEE crc=6808 rec=23511703000100020200780096006e00` line (the easy record + its verified CRC), then normal boot to attract. Also check acceptance: `grep -c "EE WR" captures/phase7/t9-menudiag.log` (or the equivalent token `parse_cartlog.py` reports — see `docs/kb/phase4-conversion.md` §EEPROM item 6) — expected 0 writes: the game accepted the image and did not wipe/rewrite it.

- [ ] **Step 4: Rebuild discipline**

```bash
make clean >/dev/null && make gdi   # all knobs off
md5 build/1ST_READ.BIN build/track04.iso
```

Record the md5s — this is the T9 release-candidate build. Store them for Task 8's tooling.md entry.

- [ ] **Step 5: Commit**

```bash
git add scripts/build_patch_table.py scripts/test_build_patch_table.py loader/main.c Makefile
git commit -m "phase7 T9 task 6: menu record -> staged eeprom_img poke (CRC self-check, pristine fallback, MENUDIAG leg knob)"
```

---

### Task 7: Operator emulator round — navigation + effects + regression (OPERATOR)

**Files:**
- Modify: `docs/kb/phase7-polishing.md` (§T9 leg records)

**Interfaces:**
- Consumes: the Task 6 all-knobs-off build (`build/disc.gdi`).
- Produces: PASS/FAIL verdicts gating the hardware round.

- [ ] **Step 1: Post the operator protocol and wait**

Post exactly (Flycast DC-profile keyboard: d-pad = arrows, A = whatever the operator's Flycast pad-map says — they know their bindings from prior legs):

> **T9 emulator round — needs you at Flycast (DC profile, `build/disc.gdi`, ~15 min).**
> 1. **Navigation:** boot → menu over the splash, START GAME highlighted. Walk all three items (wrap both directions), enter CONTROLS (check the table against how the game actually plays), B back, enter SETTINGS, walk every row, cycle every value both directions past the ends (wrap), B back. Verdict: anything missing/misdrawn/stuck?
> 2. **Effect — difficulty:** SETTINGS → difficulty to its easiest value → START GAME → play a stage. Verdict: matches the Task-18 easy-leg feel (visibly easier than default)?
> 3. **Effect — event mode:** relaunch → SETTINGS → EVENT MODE ON → START GAME. Verdict: same event-mode behavior you saw in the phase-6 hardware leg?
> 4. **Regression:** relaunch → touch nothing → START (button) immediately. Verdict: loads and plays exactly like release v13 (splash → attract, FREE PLAY on screen)?
> 5. **Test combo:** relaunch holding A+Start. Verdict: game's own TEST MENU boots, no T9 menu shown?

STOP and wait for the verdicts.

- [ ] **Step 2: Record results**

Write the verdicts into `docs/kb/phase7-polishing.md` §T9 (round table: leg, verdict, notes). Any FAIL: stop, fix, re-run the failed leg before proceeding (systematic-debugging applies; do not advance with a red leg).

- [ ] **Step 3: Commit**

```bash
git add docs/kb/phase7-polishing.md
git commit -m "phase7 T9 task 7: emulator round verdicts (nav + difficulty/event effects + regression)"
```

---

### Task 8: Docs, release candidate, hardware-round protocol

**Files:**
- Modify: `docs/kb/00-status.md` (T9 BUILT entry in the phase-7 log)
- Modify: `docs/kb/phase7-polishing.md` (§T9 full record: design link, build, legs, hardware protocol)
- Modify: `docs/kb/tooling.md` (T9 build md5s; leg-log table rows for `t9-menu-shot`, `t9-menudiag`; scripts summary)

**Interfaces:**
- Consumes: everything above.
- Produces: the operator's hardware-round protocol; the staged release candidate. **Release promotion (v14 / tag) happens only after the operator's hardware PASS — that is outside this plan, per project convention.**

- [ ] **Step 1: KB updates**

- `00-status.md`: add a "Phase 7 T9 BUILT" paragraph in the established style (what shipped, knobs, leg evidence one-liners, "hardware round owed").
- `phase7-polishing.md` §T9: append the build record — mechanism summary (menu → record → staged `eeprom_img` poke → shim RAM-copy path), knob list (`MENU=0`, `MENUDIAG=1`), leg links, and the hardware protocol from Step 2.
- `tooling.md`: candidate md5s (from Task 6 Step 4) in a "§T9 build md5s" block; the two leg logs added to the captures table with one-line descriptions; note that `menu_sheet.png`/`controls.png`/`menu_layout.h` are generated-but-committed (regenerate via `gen_menu_assets.py`); and a standing note that EVERY unattended emulator leg that must reach attract (including `scripts/test_vmu_untouched.sh` runs) now needs a `make gdi MENU=0` build first — a menu build waits at the menu forever.

- [ ] **Step 2: Write the hardware-round protocol into §T9**

```markdown
### T9 hardware round (operator protocol)

Build: T9 candidate (md5s in tooling.md §T9). Backends: GDEMU and
DreamShell serial-SD. Cables: VGA and composite.

| # | leg | pass criterion |
|---|---|---|
| 1 | boot, don't touch | menu over the splash, START GAME highlighted; style verdict (assets are round-1 placeholders -- name wanted changes) |
| 2 | controls screen | table readable on the TV, matches the pad; B returns |
| 3 | settings end-to-end | easiest difficulty via menu -> START -> visibly easier stage 1 |
| 4 | regression | untouched boot -> START button -> plays exactly like v13 (no new blink/garbage at the splash->game transition) |
| 5 | test combo | A+Start still boots the game's own TEST MENU, no T9 menu first |
| 6 | 2P hot-plug regression (T11) | plug pad 2 after boot mid-attract -> 2P start works |

PASS on all -> respin release v14 from defaults, md5s to tooling.md,
promote. Any FAIL -> round record + fix cycle, per T7/T8 precedent.
```

- [ ] **Step 3: Full test sweep + final build check**

```bash
make test
source ../cleopatra/tools/kos/environ.sh && make clean >/dev/null && make gdi
md5 build/1ST_READ.BIN build/track04.iso   # must equal Task 6 Step 4's md5s
```

Expected: all host/script tests green; md5s reproduce (deterministic build discipline).

- [ ] **Step 4: Commit and hand off to the operator**

```bash
git add docs/kb/00-status.md docs/kb/phase7-polishing.md docs/kb/tooling.md
git commit -m "phase7 T9 task 8: KB records + release candidate + hardware round protocol"
```

Post the hardware protocol to the operator. The plan ends here; promotion is gated on their PASS.

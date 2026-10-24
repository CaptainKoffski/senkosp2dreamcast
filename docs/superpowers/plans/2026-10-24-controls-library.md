# Controls Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the per-port CUSTOM pad layout with a shared library of up
to 8 custom pad layouts and 8 custom stick layouts, selectable per port on a
four-row controls page, forked from any stock layout on first change,
deletable with a two-press X, with the shim reduced to "one resolved word per
port per device class".

**Architecture:** `scripts/menu_def.py` stays the single source; the
generator emits packed stock words for the shim (`shims/src/layouts.h`) and
per-class anchor/nav/value tables for the menu (`loader/menu_layout.h`),
and writes the sprite sheet as an 8bpp palettized blob so the new sprites
fit the loader region. A new pure module `loader/ctl_lib.c` owns the
library state (slots, per-port selection, cycle/fork/delete/pack) and is
host-tested; `loader/menu.c` only draws and routes input; `loader/main.c`
stages four resolved words plus a valid flag; the shim maps buttons through
whichever word its DEVINFO class picks.

**Tech Stack:** Freestanding SH4 C (shim), KOS C (loader), Python 3 + Pillow
(offline generator, committed outputs), host `cc` tests, Flycast fork for
the emulator leg.

**Spec:** `docs/superpowers/specs/2026-10-24-controls-library-design.md`
(read it first: it carries the approved UX, the row order, the fork and
delete rules, and the cap).

## Global Constraints

- Branch `feat/controls-library` off `main`; commits end with
  `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Every hardware/behavioral claim in code comments or KB carries a citation;
  primary sources (KOS at `tools/kos`, Flycast fork at
  `../flycast4naomi2dreamcast`) outrank wikis (CLAUDE.md).
- Never commit copyrighted bytes; all menu art is our own generated work.
- `1ST_READ.BIN` must stay ≤ 1728 sectors = 3,538,944 bytes (`make gdi` /
  `make cdi` assert). Today: 3,536,144 bytes.
- Shim code+data ≤ 16 KB (`SHIM_CODE_MAX`, `shim.ld` ASSERT, loader
  `SHIM TOO BIG` halt).
- Loader builds need `source tools/kos/environ.sh` from repo root before
  `make gdi` / `make -C loader`.
- Menu text is offline-baked sprites, never runtime-typeset; no full-frame
  clears per keypress (T9 flicker rule); every menu string lives in
  `scripts/menu_def.py`.
- Generated-and-committed: `loader/menu_layout.h`, `shims/src/layouts.h`,
  `loader/menu_sheet.png`, `loader/menu_sheet.pal8` (new),
  `loader/controls_pad.png`, `loader/controls_stick.png`. Regenerate with
  `python3 scripts/gen_menu_assets.py` after any `menu_def.py` change.
- Function ids are frozen: 0 MAIN, 1 SUB, 2 BARRAGE, 3 ACTION, 4 OVERDRIVE,
  5 B.O.S.S., 6 NONE. Button order per class is frozen: pad A B X Y L R,
  stick A B X Y Z C. Packed stock words (nibble i = button i):
  Tournament `0x343210`, Old `0x432130`, Arcade `0x421063`.
- Stock layouts are immutable; the cap is 8 custom slots per class; slot
  *i* is named CUSTOM *i+1*; the lowest free slot is always the one taken.
- `make test` stays green after every task (it runs `shims/Makefile test`
  and the `scripts/test_*.py` checks).
- No "works" claim for input behavior before the operator's hardware leg
  (Task 7 hands off; it does not claim PASS).

## Review Focus

- Deleting pad slot 0 must leave stick slot 0 untouched: the classes are
  separate libraries (test in Task 4, `test_ctl_lib.c`).
- LEFT on a stick row with no custom layouts must stay on ARCADE, never go
  negative or onto a pad entry (Task 4).
- A staged valid flag that is not exactly 1 (0, 2, garbage) must select the
  generated default word, and valid == 1 must trust a staged word of 0
  (Task 1).
- A full library must never block editing a row that already shows a custom
  layout; only forking is refused (Task 4 for `ctl_keep`, Task 6 for the
  footer rule).
- Keeping a value equal to the one the button already has must not fork a
  stock layout (Task 4).

## File map

- `scripts/menu_def.py` — ports, cap, stick layouts list, stick anchors,
  row items, custom names, footer strings, delete cell.
- `scripts/gen_menu_assets.py` — packed words + class button tables into
  `layouts.h`; pal8 sheet; stick page with chips; four-row tables; footers;
  previews.
- `scripts/test_gen_menu_nav.py` (extend), `scripts/test_gen_menu_sheet.py`
  (new, pal8 ↔ png).
- `shims/include/shim_iface.h` — `SHIM_STATE` word 2 = valid flag, 3–6 =
  resolved words.
- `shims/src/jvs.c`, `shims/src/main.c`, `shims/test/test_host.c`,
  `shims/test/test_shim_iface.c`.
- `loader/ctl_lib.h`, `loader/ctl_lib.c` (new), `shims/test/test_ctl_lib.c`
  (new; the loader's host tests live under `shims/test`, precedent
  `test_naomi_crc.c`), `shims/Makefile` (test line).
- `loader/menu.c`, `loader/menu.h`, `loader/main.c`, `loader/Makefile`.
- `docs/kb/input-map.md`, `docs/kb/00-status.md`,
  `docs/kb/phase7-polishing.md` (T20 ledger), `docs/kb/tooling.md`.

Build state between tasks: the loader does not compile after Task 3 until
Task 5 lands (the generated header changes shape). Tasks 3 and 4 are
verified by their own host checks; `make gdi` is a Task 5 gate.

---

### Task 1: Shim maps through one resolved word per port, by device class

**Files:**
- Modify: `scripts/menu_def.py:77-83` (STICK_LAYOUT → `STICK_LAYOUTS` list)
- Modify: `scripts/gen_menu_assets.py:391-453` (`emit_layouts_h`)
- Modify: `shims/include/shim_iface.h:28-38`
- Modify: `shims/src/jvs.c:43-92, 124-128, 191-206`
- Modify: `shims/src/main.c:261-286`
- Modify: `loader/main.c:465-469` (flag write only; library staging is Task 5)
- Test: `shims/test/test_host.c:34-95, 108-125`, `shims/test/test_shim_iface.c:33-34`

**Interfaces:**
- Produces (generated `shims/src/layouts.h`): `JVS_CLASS_PAD 0`,
  `JVS_CLASS_STICK 1`, `JVS_LAYOUT_N 6`, `JVS_FUNC_N 7`, `JVS_FUNC_*`,
  `static const unsigned JVS_FUNC_MASK[7]`,
  `static const unsigned JVS_CLASS_BUTTON[2][6]` (pad row = CONT_A, CONT_B,
  CONT_X, CONT_Y, CONT_LTRIG, CONT_RTRIG; stick row = CONT_A, CONT_B,
  CONT_X, CONT_Y, CONT_Z, CONT_C), `JVS_WORD_TOURNAMENT 0x343210u`,
  `JVS_WORD_OLD 0x432130u`, `JVS_WORD_ARCADE 0x421063u`,
  `static const unsigned JVS_WORD_DEFAULT[2] = { JVS_WORD_TOURNAMENT, JVS_WORD_ARCADE }`.
  Deleted: `LAYOUT_*`, `PAD_SEL_CUSTOM`, `jvs_map_t`, `JVS_LAYOUT_PAD`,
  `JVS_LAYOUT_STICK`, `JVS_PAD_BUTTON`.
- Produces (`shims/src/jvs.c`):
  `unsigned jvs_pick_class(unsigned caps)` (no analog caps ⇒ `JVS_CLASS_STICK`),
  `unsigned jvs_layout_word(unsigned valid, unsigned staged, unsigned cls)`
  (`valid == 1u ? staged : JVS_WORD_DEFAULT[cls]`),
  `unsigned dc_to_jvs_word(unsigned dc_buttons, unsigned cls, unsigned word)`,
  `unsigned dc_to_jvs_test(unsigned dc_buttons, unsigned cls, unsigned word, unsigned *test_bit)`.
  Deleted: `dc_to_jvs`, `dc_to_jvs_custom`, `dc_to_jvs_port`, `jvs_pick_layout`.
- Produces (`shim_iface.h`): `SHIM_STATE_LAYOUT_VALID 2`,
  `SHIM_STATE_PAD_CUSTOM 3` (unchanged value), `SHIM_STATE_STICK_CUSTOM 5`,
  `SHIM_STATE_LAYOUT_WORD(cls, port) (SHIM_STATE_PAD_CUSTOM + 2 * (cls) + (port))`.
  Deleted: `SHIM_STATE_PAD_LAYOUT`.

- [ ] **Step 1: Rewrite the layout block of `test_host.c` to the new API (failing)**

Replace lines 34–95 with asserts in these groups, keeping every expected JVS
literal the old tests pinned:

```c
/* stock words reproduce the three tables */
assert(dc_to_jvs_word(CONT_A, JVS_CLASS_PAD, JVS_WORD_TOURNAMENT) == JVS_M);
assert(dc_to_jvs_word(CONT_B, JVS_CLASS_PAD, JVS_WORD_TOURNAMENT) == JVS_S);
assert(dc_to_jvs_word(CONT_X, JVS_CLASS_PAD, JVS_WORD_TOURNAMENT) == JVS_BARRAGE);
assert(dc_to_jvs_word(CONT_Y, JVS_CLASS_PAD, JVS_WORD_TOURNAMENT) == JVS_A);
assert(dc_to_jvs_word(CONT_LTRIG, JVS_CLASS_PAD, JVS_WORD_TOURNAMENT) == JVS_OD);
assert(dc_to_jvs_word(CONT_RTRIG, JVS_CLASS_PAD, JVS_WORD_TOURNAMENT) == JVS_A);
assert(dc_to_jvs_word(CONT_B, JVS_CLASS_PAD, JVS_WORD_OLD) == JVS_A);
assert(dc_to_jvs_word(CONT_X, JVS_CLASS_PAD, JVS_WORD_OLD) == JVS_S);
assert(dc_to_jvs_word(CONT_LTRIG | CONT_B, JVS_CLASS_PAD, JVS_WORD_OLD) == JVS_A);
assert(dc_to_jvs_word(CONT_Z, JVS_CLASS_STICK, JVS_WORD_ARCADE) == JVS_BARRAGE);
assert(dc_to_jvs_word(CONT_C, JVS_CLASS_STICK, JVS_WORD_ARCADE) == JVS_OD);
assert(dc_to_jvs_word(CONT_B, JVS_CLASS_STICK, JVS_WORD_ARCADE) == 0);
assert(dc_to_jvs_word(CONT_Z, JVS_CLASS_PAD, JVS_WORD_ARCADE) == 0);        /* class picks the button list */
/* Start + 8-way are layout-blind; chords OR */
assert(dc_to_jvs_word(CONT_START | CONT_DPAD_LEFT, JVS_CLASS_PAD, 0xffffffu) == (JVS_START | JVS_LEFT));
assert(dc_to_jvs_word(CONT_A | CONT_X, JVS_CLASS_PAD, JVS_WORD_TOURNAMENT) == (JVS_M | JVS_BARRAGE));
/* B.O.S.S. on B (nibble 1), NONE on R (nibble 5), junk nibble */
assert(dc_to_jvs_word(CONT_B, JVS_CLASS_PAD, (JVS_WORD_TOURNAMENT & ~(0xfu << 4)) | ((unsigned)JVS_FUNC_BOSS << 4)) == (JVS_M | JVS_S | JVS_A));
assert(dc_to_jvs_word(CONT_RTRIG, JVS_CLASS_PAD, (JVS_WORD_TOURNAMENT & ~(0xfu << 20)) | ((unsigned)JVS_FUNC_NONE << 20)) == 0);
assert(dc_to_jvs_word(CONT_A, JVS_CLASS_PAD, 0xfu) == 0);
/* classifier (measured caps words) */
assert(jvs_pick_class(0xfe060f00u) == JVS_CLASS_PAD);
assert(jvs_pick_class(0xff070000u) == JVS_CLASS_STICK);
/* staged-flag rule */
assert(jvs_layout_word(1u, 0u, JVS_CLASS_PAD) == 0u);
assert(jvs_layout_word(0u, 0x111111u, JVS_CLASS_PAD) == JVS_WORD_TOURNAMENT);
assert(jvs_layout_word(2u, 0x111111u, JVS_CLASS_STICK) == JVS_WORD_ARCADE);
assert(jvs_layout_word(0xffffffffu, 0x111111u, JVS_CLASS_STICK) == JVS_WORD_ARCADE);
/* test boot: Start -> test bit, A -> Service, everything else live */
{ unsigned tb; assert(dc_to_jvs_test(CONT_START | CONT_X, JVS_CLASS_PAD, JVS_WORD_OLD, &tb) == JVS_S && tb == 1u);
  assert(dc_to_jvs_test(CONT_A, JVS_CLASS_PAD, JVS_WORD_OLD, &tb) == JVS_SERVICE && tb == 0u); }
```

In the `dc_cond_to_pressed` block (lines 108–125 and below), replace every
`dc_to_jvs(x, LAYOUT_PAD_OLD)` with `dc_to_jvs_word(x, JVS_CLASS_PAD, JVS_WORD_OLD)`.
In `test_shim_iface.c:33-34` replace the `SHIM_STATE_PAD_LAYOUT < 8` assert
with `assert(SHIM_STATE_LAYOUT_WORD(1, 1) < 8);`.

- [ ] **Step 2: Run the shim tests to verify they fail**

Run: `make -C shims test`
Expected: compile error, `JVS_CLASS_PAD` / `dc_to_jvs_word` undeclared.

- [ ] **Step 3: `menu_def.py`: `STICK_LAYOUTS = [("ARCADE", {...})]`**

Same dict as today's `STICK_LAYOUT`; delete the old name and point the
generator's two readers (`emit_layouts_h` and the stick preview at
`gen_menu_assets.py:679`) at `STICK_LAYOUTS[0][1]`. Keep the comment about B
unmapped per the tester. Leave the `CTL_PAD_VALUES` / `CTL_CUSTOM_DEFAULT`
asserts in place; Task 3 removes them with the names.

- [ ] **Step 4: `emit_layouts_h`: emit words and class button lists**

Add `pack_word(buttons, layout) -> int` (nibble i = `FUNC_WORDS.index(layout[buttons[i]])`)
to the generator and emit the Interfaces block above. Keep the existing
playable/unreachable asserts, applied to every entry of both lists.
Run `python3 scripts/gen_menu_assets.py` and check the three word literals in
`shims/src/layouts.h` match the Global Constraints; `loader/menu_layout.h`
must come out byte-identical (`git diff --stat loader/menu_layout.h` empty).

- [ ] **Step 5: `shim_iface.h`: the word map**

Replace lines 28–38 with the four defines in Interfaces and a comment: word 2
is 1 when the loader staged words 3–6 (pad A, pad B, stick A, stick B; six
4-bit function ids, nibble i = `JVS_CLASS_BUTTON[cls][i]`); anything else
means the shim uses `JVS_WORD_DEFAULT[cls]`, so a zero-filled window is
never read as a layout.

- [ ] **Step 6: `jvs.c`: the four functions, delete the tables' consumers**

`dc_to_jvs_word` = `jvs_common()` OR, for each i < `JVS_LAYOUT_N`, if the
nibble < `JVS_FUNC_N` and `dc_buttons & JVS_CLASS_BUTTON[cls][i]`, the mask.
`dc_to_jvs_test` keeps its body with `dc_to_jvs_word(dc & ~(CONT_START|CONT_A), cls, word)`.
Update the header comments (the "Which layout drives a port" comment becomes
the class rule; cite the same KOS/flycast lines).

- [ ] **Step 7: `shims/src/main.c:261-286`: read flag + class words**

```c
u32 valid = UW(SHIM_STATE + 4 * SHIM_STATE_LAYOUT_VALID);
u32 k1 = jvs_pick_class(devinfo_caps[0]), k2 = jvs_pick_class(devinfo_caps[1]);
u32 w1 = jvs_layout_word(valid, UW(SHIM_STATE + 4 * SHIM_STATE_LAYOUT_WORD(k1, 0)), k1);
u32 w2 = jvs_layout_word(valid, UW(SHIM_STATE + 4 * SHIM_STATE_LAYOUT_WORD(k2, 1)), k2);
```

Test boot calls `dc_to_jvs_test(p1, k1, w1, &test_bit)`; otherwise
`dc_to_jvs_word(p1, k1, w1)`; P2 `dc_to_jvs_word(p2, k2, w2)`. Update the
prototypes at `main.c:132-137`.

- [ ] **Step 8: `loader/main.c:465-469`: write the flag as 0**

Replace the `SHIM_STATE_PAD_LAYOUT` write with a write of `0u` to word
`SHIM_STATE_LAYOUT_VALID` and a comment "0 until the library staging lands
(controls-library plan Task 5): shim uses the generated defaults". Leave the
word 3–4 loop as is (harmless, replaced in Task 5).

- [ ] **Step 9: Run the shim tests, then both builds**

Run: `make -C shims test && source tools/kos/environ.sh && make gdi`
Expected: `test_host` and `test_iface` PASS; `shim.bin` within
`SHIM_CODE_MAX`; the loader still builds (it stages flag 0, so the shim runs
the generated defaults: Tournament on pads, Arcade on sticks).

- [ ] **Step 10: Commit**

```bash
git add scripts/menu_def.py scripts/gen_menu_assets.py shims/src/layouts.h shims/include/shim_iface.h shims/src/jvs.c shims/src/main.c shims/test/test_host.c shims/test/test_shim_iface.c loader/main.c
git commit -m "shim: one resolved layout word per port per device class (presets leave the shim)"
```

---

### Task 2: Sprite sheet becomes an 8bpp palettized blob

**Files:**
- Modify: `scripts/gen_menu_assets.py:471-474, 574-579, 639-659` (sheet creation, save, previews)
- Create: `scripts/test_gen_menu_sheet.py`
- Modify: `loader/Makefile:145-154` (sheet rule), `Makefile:243-248` (`test` target)
- Modify: `loader/menu.c:34-39` (`blit`), `menu_run` entry
- Modify: `scripts/menu_def.py:125` (`SHEET_H` stays 1024 here)

**Interfaces:**
- Produces: `loader/menu_sheet.pal8` = 256 × RGB565-LE palette (512 B) then
  `SHEET_W * SHEET_H` 8bpp indices, row-major (the `logo_strip.pal8` format,
  `gen_menu_assets.py:606-634`); `loader/menu_sheet.png` becomes the DECODED
  preview of that blob. Loader symbol names `_menu_sheet_bin` /
  `_menu_sheet_bin_end` unchanged.
- Produces (`menu_layout.h`): `#define MENU_SHEET_H <SHEET_H>`.

- [ ] **Step 1: Write `scripts/test_gen_menu_sheet.py` (failing)**

```python
def test_pal8_matches_png():
    blob = open("loader/menu_sheet.pal8", "rb").read()
    assert len(blob) == 512 + M.SHEET_W * M.SHEET_H
    pal = [struct.unpack_from("<H", blob, 2 * i)[0] for i in range(256)]
    png = Image.open("loader/menu_sheet.png").convert("RGB")
    assert png.size == (M.SHEET_W, M.SHEET_H)
    for y in range(0, M.SHEET_H, 7):           # strided: whole-sheet exactness, fast
        for x in range(0, M.SHEET_W, 5):
            assert pal[blob[512 + y * M.SHEET_W + x]] == g.rgb565(png.getpixel((x, y)))
```

Paths relative to the repo root (resolve from `__file__` like
`test_gen_menu_nav.py`). Add `python3 scripts/test_gen_menu_sheet.py` to the
top-level `test` target.

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 scripts/test_gen_menu_sheet.py`
Expected: FAIL, `menu_sheet.pal8` missing.

- [ ] **Step 3: Generator writes the blob and the decoded preview**

After the shelf assert: `q = sheet.quantize(256, dither=Image.Dither.NONE)`;
write the blob exactly as the logo block does; save
`q.convert("RGB")` as `loader/menu_sheet.png`; use that decoded image (not
`sheet`) for every preview crop; print the distinct-colour count of the
un-quantized sheet. Emit `MENU_SHEET_H`.

- [ ] **Step 4: Loader rule and blit**

`loader/Makefile`: delete the `../build/menu_sheet.bin` sips rule; make
`menu_sheet_blob.o` an objcopy of `menu_sheet.pal8` with the redefined
symbols above (copy the `logo_blob.o` rule). `loader/menu.c`: a
`static uint16 sheet_pal[256]` filled by `memcpy(sheet_pal, menu_sheet_bin, 512)`
at the top of `menu_run()` (the blob may be misaligned: the `draw_logo`
lesson); `blit()` becomes a per-pixel `vram_s[...] = sheet_pal[idx]` loop over
`menu_sheet_bin + 512 + (src.y + row) * MENU_SHEET_W + src.x`.

- [ ] **Step 5: Verify: sheet test, loader size, `.gitignore`**

Run: `python3 scripts/gen_menu_assets.py && python3 scripts/test_gen_menu_sheet.py && git check-ignore -v loader/menu_sheet.pal8; source tools/kos/environ.sh && make gdi && /bin/ls -l build/1ST_READ.BIN`
Expected: test PASS; `check-ignore` prints nothing (tracked); `1ST_READ.BIN`
≈ 2,881,300 bytes (3,536,144 − 1,310,720 + 655,872); `make gdi` passes its
region assert. View `build/preview_pad_tournament.png`: text unchanged.

- [ ] **Step 6: Commit**

```bash
git add scripts/gen_menu_assets.py scripts/test_gen_menu_sheet.py Makefile loader/Makefile loader/menu.c loader/menu_layout.h loader/menu_sheet.png loader/menu_sheet.pal8
git commit -m "menu sheet: 8bpp palettized blob (frees ~650 KB of the loader region)"
```

---

### Task 3: Generator: library sprites, four rows, stick chips, footers, nav

**Files:**
- Modify: `scripts/menu_def.py:85-125`
- Modify: `scripts/gen_menu_assets.py:109-136, 200-260, 327-383, 532-604, 639-679, 764-826`
- Test: `scripts/test_gen_menu_nav.py`

**Interfaces:**
- Produces (`menu_def.py`): `CTL_PORTS = 2`, `CTL_N_CUSTOM = 8`,
  `CTL_CLASSES = [("PAD", PAD_BUTTONS, PAD_LAYOUTS, PAD_ANCHORS), ("STICK", STICK_BUTTONS, STICK_LAYOUTS, STICK_ANCHORS)]`,
  `CTL_ROW_ITEMS = [f"P{p + 1} {name} LAYOUT" for name, *_ in CTL_CLASSES for p in range(CTL_PORTS)]`
  (class-major: P1 PAD, P2 PAD, P1 STICK, P2 STICK),
  `CTL_CUSTOM_NAMES = [f"CUSTOM {i + 1}" for i in range(CTL_N_CUSTOM)]`,
  `CTL_DELETE_CELL = "DELETE?"`,
  `CTL_FOOTERS` (ordered): `ROWS_STOCK = "UP/DOWN: ROW   LEFT/RIGHT: LAYOUT   A: CUSTOMIZE   B: BACK"`,
  `ROWS_CUSTOM = "LEFT/RIGHT: LAYOUT   A: EDIT   X: DELETE   B: BACK"`,
  `EDIT = "D-PAD: BUTTON   A: CHANGE   B: DONE"`,
  `VALUE = "LEFT/RIGHT: FUNCTION   A: KEEP   B: UNDO"`,
  `CONFIRM = "X: DELETE   ANY OTHER BUTTON: CANCEL"`,
  `FULL = "ALL 8 CUSTOM SLOTS USED: DELETE ONE FIRST"`.
  `STICK_ANCHORS = {"X": (10, 18), "Y": (480, 53), "Z": (480, 83), "C": (480, 111), "B": (480, 136), "A": (480, 161)}`
  (tag y − 12 of the 2026-10-03 tags; B new). `SHEET_H = 1280`.
  Deleted: `CTL_PAD_VALUES`, `CTL_CUSTOM_DEFAULT`, `CTL_STICK_VALUE`, `CTL_FOOTER`.
- Produces (`menu_layout.h`): `CTL_PORTS`, `CTL_N_CLASS 2`, `CTL_N_CUSTOM`,
  `CTL_N_ROWS 4`, `CTL_N_BUTTONS 6`, `CTL_N_FUNC 7`, `CTL_MAX_STOCK 2`,
  `static const unsigned char CTL_N_STOCK[2] = {2, 1}`,
  `static const unsigned char CTL_STOCK_FUNC[2][2][6]` (stick[1] zero-filled),
  `static const mrect_t CTL_STOCK_VALUE[2][2]` (`< TOURNAMENT >`, `< OLD >` / `< ARCADE >`, `{0,0,0,0}`),
  `static const mrect_t CTL_CUSTOM_VALUE[8]` (`< CUSTOM n >`),
  `static const mrect_t CTL_DELETE_VALUE` (288×28, red `(0xc0,0x39,0x2b)` fill, white text),
  `static const mrect_t CTL_ROW_LABEL[4][2]`,
  `CTL_FOOT_ROWS_STOCK 0 … CTL_FOOT_FULL 5`, `static const mrect_t CTL_FOOTER[6]` (640×24 strips),
  `CTL_FOOTER_X 0`, `CTL_FOOTER_Y 452`,
  `static const unsigned short CTL_ANCHOR[2][6][2]`,
  `static const unsigned char CTL_EDIT_FIRST[2]`,
  `static const unsigned char CTL_EDIT_NAV[2][6][4]`,
  `#define CTL_ROW_Y(i) (300 + (i) * 34 + ((i) / CTL_PORTS) * 12)` (rows at 300, 334, 380, 414),
  `CTL_WORD[7]`, `CTL_WORD_HI[7]`, `CTL_ROW_LABEL_X`, `CTL_ROW_VALUE_X` unchanged.
  Deleted: `CTL_PAD_CUSTOM`, `CTL_CUSTOM_DEFAULT`, `CTL_PAD_FUNC`,
  `CTL_PAD_ANCHOR`, `CTL_PAD_VALUE`, `CTL_STICK_VALUE`, the old 1-D
  `CTL_EDIT_NAV` / `CTL_EDIT_FIRST`.
- Pages: the baked footer leaves both page PNGs (footer area = BG); the
  stick page keeps only the MOVE and START tags and gains leaders for all six
  chips.

- [ ] **Step 1: Add `test_real_stick_page` to `scripts/test_gen_menu_nav.py` (failing)**

```python
def test_real_stick_page():
    nav = g.edit_nav(M.STICK_ANCHORS, M.STICK_BUTTONS)
    b = M.STICK_BUTTONS.index
    want = {
        "X": [None, None, None, b("Y")],
        "Y": [None, b("Z"), b("X"), None],
        "Z": [b("Y"), b("C"), b("X"), None],
        "C": [b("Z"), b("B"), b("X"), None],
        "B": [b("C"), b("A"), b("X"), None],
        "A": [b("B"), None, b("X"), None],
    }
    for name, row in want.items():
        assert nav[b(name)] == row, f"{name}: {nav[b(name)]} != {row}"
```

Call it from `__main__`.

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 scripts/test_gen_menu_nav.py`
Expected: FAIL, `STICK_ANCHORS` missing.

- [ ] **Step 3: `menu_def.py` additions and deletions per Interfaces**

- [ ] **Step 4: Stick page with chips**

`SCOL_R` gains `chip_x=480`; `build_page(name, spec, anchors)` takes the
right column from `spec["col_r"]` (`COL_R` for pad, `SCOL_R` for stick) in
place of `col_of`. `STICK_PAGE`: `buttons` gains `"B": (src_x, src_y, 50)`
measured on `loader/stick_diagram.png` (bottom row, between A and C);
`leads` = the old tags' tails keyed by button (`X` `[(347, 30), (347, 88)]`,
`Y` `[(377, 65), (377, 67)]`, `Z` `[(450, 95), (450, 83), (429, 83)]`,
`C` `[(429, 123)]`, `A` `[(348, 173), (348, 157)]`) plus
`B` = a horizontal at y 148 from the column to B's page centre x (the
leader-end assert, radius × scale + 5 px, is the gate); `tags` keeps MOVE and
START only. The anchor sanity loop (`:586-599`) runs for both classes with the
page's own column xs and `y <= CTL_ROW_Y(0) - CHIP_H`. Delete the baked
footer draw (`:377-378`).

- [ ] **Step 5: Sheet cells and header tables per Interfaces**

Four row labels; stock/custom/delete value chips via `get_chip` (add a
`fill`/`color` variant for the red cell; define `RED`, `WHITE`); six footer
strips via `shelf.place(640, 24)` + `check_fits`. If `check_fits` rejects
`ROWS_STOCK`, drop its leading `UP/DOWN: ROW   ` in `menu_def.py` (spec §7
rule) and say so in the commit. Nav + reachability per class
(`CTL_EDIT_FIRST[cls]` = min by (y, x)).

- [ ] **Step 6: Previews from the decoded sheet**

`preview(name, cls, layout, row_hi, values[4], footer, cursor=None, editing=False)`
composes page + six chips + four rows + footer. Emit:
`preview_pad_tournament`, `preview_pad_old`, `preview_stick_arcade`,
`preview_pad_custom_demo` (P1 value `CUSTOM 1`, layout `CUSTOM_DEMO`),
`preview_pad_custom_cursor`, `preview_pad_custom_editing`,
`preview_stick_custom_cursor` (cursor on X), `preview_pad_delete`
(P2 value cell `DELETE?`, `CONFIRM` footer), `preview_pad_full` (`FULL` footer).

- [ ] **Step 7: Run the generator, the nav test, the sheet test; view previews**

Run: `python3 scripts/gen_menu_assets.py && python3 scripts/test_gen_menu_nav.py && python3 scripts/test_gen_menu_sheet.py`
Expected: generator prints `sheet N/1280px used` with N ≤ 1280 and no
assert; both tests PASS. Read every `build/preview_*.png` listed in Step 6:
stick chips sit on the old tag lines with straight leaders, B has a leader,
four rows clear the art and the footer, `DELETE?` is red, footers fit.

- [ ] **Step 8: Commit**

```bash
git add scripts/menu_def.py scripts/gen_menu_assets.py scripts/test_gen_menu_nav.py loader/menu_layout.h loader/menu_sheet.png loader/menu_sheet.pal8 loader/controls_pad.png loader/controls_stick.png shims/src/layouts.h
git commit -m "menu generator: controls library sprites, four rows, stick chips, state footers"
```

---

### Task 4: `ctl_lib`: the library model, host-tested

**Files:**
- Create: `loader/ctl_lib.h`, `loader/ctl_lib.c`
- Create: `shims/test/test_ctl_lib.c`
- Modify: `shims/Makefile:75-83` (add the test line)

**Interfaces:**
- Consumes: `loader/menu_layout.h` tables from Task 3 (`CTL_PORTS`,
  `CTL_N_CLASS`, `CTL_N_CUSTOM`, `CTL_N_BUTTONS`, `CTL_N_STOCK`, `CTL_STOCK_FUNC`).
- Produces (`loader/ctl_lib.h`, pure C, no KOS):

```c
typedef struct {
    unsigned char custom[CTL_N_CLASS][CTL_N_CUSTOM][CTL_N_BUTTONS];
    unsigned char used[CTL_N_CLASS][CTL_N_CUSTOM];
    unsigned char sel[CTL_N_CLASS][CTL_PORTS];   /* < CTL_N_STOCK[cls]: stock id; else CTL_N_STOCK[cls] + slot */
} ctl_lib_t;
extern ctl_lib_t ctl_lib;                        /* the session instance; all-zero == defaults (KOS clears .bss) */
#define CTL_KEEP_FULL   (-1)
#define CTL_KEEP_SAME   0
#define CTL_KEEP_WRITTEN 1
#define CTL_KEEP_FORKED 2
int  ctl_slot(const ctl_lib_t *L, int cls, int port);                /* custom slot or -1 (stock) */
const unsigned char *ctl_funcs(const ctl_lib_t *L, int cls, int port);   /* the six ids the row shows */
void ctl_cycle(ctl_lib_t *L, int cls, int port, int dir);            /* dir +1/-1; stock ids, then used slots ascending; wraps */
int  ctl_free_slot(const ctl_lib_t *L, int cls);                     /* lowest unused slot or -1 */
int  ctl_keep(ctl_lib_t *L, int cls, int port, int button, unsigned char value);
void ctl_delete(ctl_lib_t *L, int cls, int slot);                    /* free it; every port selecting it -> 0 */
unsigned ctl_pack(const ctl_lib_t *L, int cls, int port);            /* nibble i = funcs[i] */
```

`ctl_keep`: value equal to the current id ⇒ `CTL_KEEP_SAME`, nothing
written; stock selection ⇒ copy the stock ids into the lowest free slot,
mark used, select it, write the value ⇒ `CTL_KEEP_FORKED` (no free slot ⇒
`CTL_KEEP_FULL`, nothing changed); custom selection ⇒ write in place ⇒
`CTL_KEEP_WRITTEN`.

- [ ] **Step 1: Write `shims/test/test_ctl_lib.c` (failing)**

`#include "../../loader/ctl_lib.h"`, a local `ctl_lib_t L` zeroed with
`memset` per case. Assert, with `P = 0` pad class, `S = 1` stick class:

```c
/* defaults */
assert(ctl_slot(&L, P, 0) == -1 && ctl_pack(&L, P, 0) == 0x343210u && ctl_pack(&L, S, 1) == 0x421063u);
assert(memcmp(ctl_funcs(&L, P, 1), CTL_STOCK_FUNC[P][0], 6) == 0);
/* cycle without customs */
ctl_cycle(&L, P, 0, +1); assert(L.sel[P][0] == 1 && ctl_pack(&L, P, 0) == 0x432130u);
ctl_cycle(&L, P, 0, +1); assert(L.sel[P][0] == 0);
ctl_cycle(&L, P, 0, -1); assert(L.sel[P][0] == 1);
ctl_cycle(&L, S, 0, -1); assert(L.sel[S][0] == 0);           /* single stock: stays */
/* keep: same value never forks; first change forks a copy and selects it */
assert(ctl_keep(&L, P, 1, 0, 0) == CTL_KEEP_SAME && ctl_slot(&L, P, 1) == -1 && L.used[P][0] == 0);
assert(ctl_keep(&L, P, 1, 5, 5) == CTL_KEEP_FORKED && ctl_slot(&L, P, 1) == 0 && L.used[P][0] == 1);
assert(ctl_funcs(&L, P, 1)[5] == 5 && ctl_funcs(&L, P, 1)[0] == 0);        /* B.O.S.S. on R, rest Tournament */
assert(memcmp(CTL_STOCK_FUNC[P][0], (unsigned char[]){0,1,2,3,4,3}, 6) == 0);  /* stock untouched */
assert(ctl_keep(&L, P, 1, 5, 6) == CTL_KEEP_WRITTEN && ctl_slot(&L, P, 1) == 0);
assert(ctl_pack(&L, P, 1) == 0x643210u);
/* shared object: port 0 (on Old, sel 1) steps onto slot 0 and sees the edit */
ctl_cycle(&L, P, 0, +1); assert(ctl_slot(&L, P, 0) == 0 && ctl_funcs(&L, P, 0)[5] == 6);
/* cycle order with a hole: fork slot 1 from Old, delete slot 0, cycle skips it */
ctl_cycle(&L, P, 0, -1); assert(L.sel[P][0] == 1);                /* back on Old */
assert(ctl_keep(&L, P, 0, 0, 1) == CTL_KEEP_FORKED && ctl_slot(&L, P, 0) == 1);
ctl_delete(&L, P, 0); assert(L.used[P][0] == 0 && L.sel[P][1] == 0 && ctl_slot(&L, P, 0) == 1);
ctl_cycle(&L, P, 1, +1); ctl_cycle(&L, P, 1, +1); assert(ctl_slot(&L, P, 1) == 1);  /* 0 -> 1 -> slot 1 */
ctl_cycle(&L, P, 1, +1); assert(L.sel[P][1] == 0);
assert(ctl_free_slot(&L, P) == 0);                                 /* freed number reused */
/* classes independent */
assert(ctl_keep(&L, S, 0, 1, 0) == CTL_KEEP_FORKED && L.used[S][0] == 1);
ctl_delete(&L, P, 1); assert(L.used[S][0] == 1 && ctl_slot(&L, S, 0) == 0);
/* full: 8 forks then refusal; editing a custom row still allowed */
memset(&L, 0, sizeof L);
for (int i = 0; i < 8; i++) { L.sel[P][0] = 0; assert(ctl_keep(&L, P, 0, 0, 1) == CTL_KEEP_FORKED && ctl_slot(&L, P, 0) == i); }
assert(ctl_free_slot(&L, P) == -1);
L.sel[P][0] = 0; assert(ctl_keep(&L, P, 0, 0, 1) == CTL_KEEP_FULL && ctl_slot(&L, P, 0) == -1);
L.sel[P][0] = 2 + 7; assert(ctl_keep(&L, P, 0, 1, 2) == CTL_KEEP_WRITTEN);
```

Add to `shims/Makefile` `test`:
`cc -I../loader -o $(B)/test_ctl_lib test/test_ctl_lib.c ../loader/ctl_lib.c && $(B)/test_ctl_lib`.

- [ ] **Step 2: Run it to verify it fails**

Run: `make -C shims test`
Expected: FAIL, `ctl_lib.h` not found.

- [ ] **Step 3: Implement `loader/ctl_lib.c`**

Pure C, `#include "ctl_lib.h"` only; `ctl_cycle` walks the ordered list
`[0 .. n_stock) ++ [n_stock + s for used s ascending]` and wraps; no
dynamic allocation; a `ponytail:` comment on `ctl_cycle` naming the linear
scan (10 entries max).

- [ ] **Step 4: Run the tests**

Run: `make -C shims test`
Expected: `test_ctl_lib` PASS alongside the others.

- [ ] **Step 5: Commit**

```bash
git add loader/ctl_lib.h loader/ctl_lib.c shims/test/test_ctl_lib.c shims/Makefile
git commit -m "ctl_lib: shared custom-layout library (slots, per-port selection, fork/delete/pack), host-tested"
```

---

### Task 5: Controls page: four rows, cycling, per-class art, footers, staging

**Files:**
- Modify: `loader/menu.c:21-32, 131-252` (state, controls page), `loader/menu.h`
- Modify: `loader/main.c:465-475` (staging), `loader/Makefile:4-5, 25` (`ctl_lib.o`, header deps)

**Interfaces:**
- Consumes: Task 3 tables, Task 4 `ctl_lib` API, Task 1 `SHIM_STATE_LAYOUT_VALID` / `SHIM_STATE_LAYOUT_WORD`.
- Produces (`menu.c`, static): `ctl_cls(row) = row / CTL_PORTS`,
  `ctl_port(row) = row % CTL_PORTS`,
  `const mrect_t *ctl_value_rect(int row)` (stock id → `CTL_STOCK_VALUE[cls][id]`, slot → `CTL_CUSTOM_VALUE[slot]`),
  `void ctl_draw_labels(int row)` (six chips from `ctl_funcs` at `CTL_ANCHOR[cls]`),
  `void ctl_draw_rows(int cur)`, `void ctl_draw_footer(int which)`,
  `void ctl_draw_all(int cur)` (page bin by class, labels, rows, footer
  `ROWS_STOCK`/`ROWS_CUSTOM` by the highlighted row),
  `const uint8 *ctl_page_bin(int cls)`.
  `menu.h` exports only `menu_game_record` and `menu_run`; `menu_pad_layout`
  and `menu_custom` are deleted.
- Row semantics: UP/DOWN across `CTL_N_ROWS`; the art page flips when the
  class changes; LEFT/RIGHT = `ctl_cycle(&ctl_lib, cls, port, ±1)` then
  labels + rows + footer; the page opens on row `CTL_PORTS` (P1 STICK) iff
  `stick_on_menu_pad()`, else 0. A and X do nothing in this task.
- Staging (`main.c`, unconditional, replaces lines 465–475):
  word `SHIM_STATE_LAYOUT_VALID` = `1u`; for each class and port, word
  `SHIM_STATE_LAYOUT_WORD(c, p)` = `ctl_pack(&ctl_lib, c, p)`.

- [ ] **Step 1: Rewrite the controls page in `menu.c`**

Delete `menu_pad_layout`, `menu_custom`, `ctl_edit`, `ctl_chip`,
`ctl_cursor` (they return in Task 6 against the class tables). Keep the
"art memcpy only on entry / class change" rule.

- [ ] **Step 2: `main.c` staging and `Makefile`**

`#include "ctl_lib.h"` in `main.c`; `OBJS += ctl_lib.o`; add `ctl_lib.h
menu_layout.h` to the `menu.o main.o` dependency line and a
`ctl_lib.o: ctl_lib.h menu_layout.h` line.

- [ ] **Step 3: Build everything**

Run: `source tools/kos/environ.sh && make test && make gdi && make cdi && /bin/ls -l build/1ST_READ.BIN`
Expected: tests PASS; both masters build and pass their region asserts;
loader ≈ 3,045,000 bytes (under 3,538,944).

- [ ] **Step 4: Commit**

```bash
git add loader/menu.c loader/menu.h loader/main.c loader/Makefile
git commit -m "controls page: four rows over the shared layout library; loader stages four resolved words"
```

---

### Task 6: Customize (A, fork on first change, full refusal) and delete (X, two presses)

**Files:**
- Modify: `loader/menu.c` (editor + controls loop)

**Interfaces:**
- Consumes: Task 4 `ctl_keep`, `ctl_free_slot`, `ctl_delete`, `ctl_slot`.
- Produces (static): `void ctl_cursor(int cls, int b, int on)` (frame outside
  `CTL_ANCHOR[cls][b]`, off = restore from `ctl_page_bin(cls)`),
  `void ctl_chip(int cls, int b, unsigned char id, int hi)`,
  `void ctl_edit(int row)`.
- Editor rules (spec §3): cursor starts at `CTL_EDIT_FIRST[cls]`; d-pad via
  `CTL_EDIT_NAV[cls]`; footer `EDIT` on entry, `VALUE` in value mode, `EDIT`
  on return. Value mode cycles a local `cand` (starts at the current id) and
  draws `ctl_chip(cls, b, cand, 1)`; A ⇒ `ctl_keep(&ctl_lib, cls, port, b, cand)`;
  on `CTL_KEEP_FORKED` redraw the rows (the highlighted value flips to
  `CUSTOM n`); on `CTL_KEEP_FULL` or `CTL_KEEP_SAME` nothing changes; B ⇒
  redraw the chip with the current id. B outside value mode returns; the
  caller redraws rows + the `ROWS_STOCK`/`ROWS_CUSTOM` footer.
- Controls loop additions: A on a stock row with `ctl_free_slot == -1` ⇒
  footer `FULL`, flag `msg = 1`; the next edge restores the row footer first,
  then is processed normally. A otherwise ⇒ `ctl_edit(cur)`. X on a custom
  row ⇒ value cell `CTL_DELETE_VALUE`, footer `CONFIRM`, state `confirm`;
  next edge: X ⇒ `ctl_delete(&ctl_lib, cls, slot)`, redraw labels + rows +
  footer; anything else ⇒ redraw value + footer, and `continue` (the press
  is consumed). X on a stock row does nothing.

- [ ] **Step 1: Implement per the rules above**

No dimmed rows and no flash on fork: the value text flipping to `CUSTOM n`
is the signal (the spec leaves both optional; skipped).

- [ ] **Step 2: Build and run the host tests**

Run: `source tools/kos/environ.sh && make test && make gdi && make cdi`
Expected: PASS / both masters build.

- [ ] **Step 3: Desk-check against the spec's operator leg (1)**

Walk the code for each item of spec §Verification "Operator legs (1)" and
the five Review Focus lines; fix anything that does not match before
committing. Record the walk in the commit body as a checklist.

- [ ] **Step 4: Commit**

```bash
git add loader/menu.c
git commit -m "controls page: A customizes (fork on first change, full-library refusal), X deletes with a two-press confirm"
```

---

### Task 7: Emulator boot smoke, KB, hand-off to the operator legs

**Files:**
- Modify: `docs/kb/input-map.md` (new section after "Custom pad layout",
  marking that one superseded), `docs/kb/00-status.md` (top entry),
  `docs/kb/phase7-polishing.md` (new `## T20 — controls library` ledger in
  the T19 format), `docs/kb/tooling.md` (§Legs: `ctl-library/boot-smoke1`;
  sheet format note next to the logo pal8 note)

- [ ] **Step 1: Emulator boot smoke on the new sheet**

Run: `make objclean && source tools/kos/environ.sh && FAKESTART=6000 make gdi && scripts/capture_rawfb_leg.sh ctl-library/boot-smoke1 160 4`
Expected: `leg done`; view `captures/ctl-library/shot-boot-smoke1-003-t15s.png`
(the pre-game top menu renders from the pal8 sheet: logo, three items,
footer); the log has 0 `SHIMERR`, 0 `System reset`, `TAEND` in the
thousands (the fake START launched the game). The fork cannot inject pad
input, so the controls page itself is an operator leg. Then
`make objclean && make gdi` (knob off) and confirm `build/1ST_READ.BIN`
md5 differs from the FAKESTART build.

- [ ] **Step 2: KB**

`input-map.md`: the mechanism (library, class words, flag, cycle/fork/delete
rules, cap, sheet format), word literals, the spec/plan paths, and
"Verification: host tests + emulator smoke; **operator legs pending**".
`00-status.md`: one paragraph at the top in the existing style.
`phase7-polishing.md` T20: origin, what changed (file list), verification
state. `tooling.md`: the leg record and the pal8 sheet note.

- [ ] **Step 3: `make test` and commit**

Run: `make test`
Expected: PASS.

```bash
git add docs/kb/input-map.md docs/kb/00-status.md docs/kb/phase7-polishing.md docs/kb/tooling.md
git commit -m "KB: controls library (emulator-proven; operator legs pending)"
```

(`captures/` is gitignored; the leg's log and the kept t=15 s frame stay on
disk and are cited by path, as every earlier leg is.)

- [ ] **Step 4: Hand off (stop and wait; operator-leg protocol)**

Give the operator `make deploy` (GDEmu) and the checklist from the spec's
§Verification "Operator legs" (1) emulator walkthrough and (2) hardware,
verbatim. Do not claim PASS, do not tag; the release flow (ff-merge, tag
`0.21.0`, push, delete branch) follows the operator's hardware verdict.

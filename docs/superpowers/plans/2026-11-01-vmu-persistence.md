# VMU Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The pre-game menu keeps the settings record and the controls library on a Dreamcast memory card: loaded silently at boot, saved by itself when the player leaves a page or starts the game, written only to a card the player consented to, with one status line that says what happened.

**Architecture:** A new `loader/vmu_save.c` holds a pure half (140-byte payload build/parse with validation, root-block sanity guard, the consent decision) that is host-tested, and a KOS half (card scan with fingerprint, load, write) over `vmufs_*`/`vmu_pkg_*`. `loader/menu.c` owns the UI: boot load at `menu_run` entry, the status line on the top page, the sync at the two sync points, the LEFT/RIGHT prompt, and a `VMUDIAG` block for the unattended emulator leg. The generator bakes the nine message strips, eight slot tokens, two prompt footers and the 32×32 icon. Nothing in `main.c` changes: the VMU-safety tripwire forbids VMU symbols there.

**Tech Stack:** C (KOS at `tools/kos`, sh-elf), Python 3 + Pillow (generator, decoder), sh (emulator legs), the instrumented Flycast fork.

**Spec:** `docs/superpowers/specs/2026-11-01-vmu-persistence-design.md` (read it first; it carries the citations and the exact strings).

## Global Constraints

- Branch in place: `git checkout -b feat/vmu-persistence` from `main`. No git worktree (gitignored build inputs live only in this checkout).
- Every hardware/behavioural claim in code comments and KB cites a primary source: KOS `tools/kos/...:line`, the Flycast fork `../flycast4naomi2dreamcast/...:line`. No wikis.
- `loader/main.c` and `loader/handoff.c` never reference a `vmu*`/`maple*` symbol beyond `maple_wait_scan`, `maple_enum_type`, `maple_dev_status` (`scripts/test_maple_literals.py` gates `make test`). All VMU code hangs off `menu_run`.
- `build/1ST_READ.BIN` ≤ 3,538,944 bytes, measured after `make gdi` (`make cdi` deletes it).
- Menu text is baked offline; no runtime font. Every new strip passes `check_fits` (624 px at `F_ROW`). The sheet stays ≤ 256 colours at RGB565 (generator assert). `scripts/test_gen_menu_sheet.py` stays exhaustive.
- The icon contains no copyrighted art: text/shapes in the menu colours only. Generated outputs that ship are committed (`menu_layout.h`, `menu_sheet.pal8`, `menu_sheet.png`); previews go to gitignored `build/`.
- Exact strings (spec §The status line): `LOADED FROM VMU xx`, `SAVED TO VMU xx`, `SAVING TO VMU xx`, `SAVE SETTINGS TO VMU xx`, `REPLACE SAVE ON VMU xx`, `NEED 2 FREE BLOCKS ON VMU xx`, `SAVE FAILED ON VMU xx`, `NO VMU: CHANGES WON'T BE KEPT`, `NOT SAVED: KEPT UNTIL POWER OFF`; footers `A: YES   B: NO`, `A: YES   B: NO   LEFT/RIGHT: OTHER VMU`.
- File: name `SENKOSP_SYS`, desc_short `SENKO NO RONDE`, desc_long `DC PORT SETTINGS AND CONTROLS`, app_id `SENKOSP2DC`, 1 icon, no eyecatch, payload 140 bytes, 2 blocks.
- Payload v1: `SKSP` (4) · version 1 (1) · zero (3) · `menu_game_record` (16) · `ctl_lib_t` (116).
- Consent: a silent write goes only to `home` = (slot, 8-byte root timestamp fingerprint) loaded from at boot or A-pressed this session, re-verified at write time. Loading happens at boot only.
- A card is readable iff `MAPLE_FUNC_MEMCARD`, block 255 reads, magic 16×0x55, `fat_size == 1`, `1 ≤ dir_size ≤ 13`, `blk_cnt ≤ 256`, `fat_loc < 256`, `dir_loc < 256`.
- `make test` and `make test-vmu` stay green. Copyrighted bytes never enter git. Commit trailer: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Verification discipline: decoded images are viewed (icon PNG, previews, the framebuffer dump), never byte-echoed. Operator legs on hardware are the claim gate; the KB says "emulator-proven" until then.

## Review Focus

1. A card carrying a `SENKOSP_SYS` from a newer build (version byte ≠ 1) must boot blank and later show `REPLACE SAVE ON VMU xx`, never a silent overwrite. Pinned: Task 1 `version 2 → reject`, Task 4 prompt wording by `has_file`.
2. A payload whose `sel` names an unused custom slot would make the menu show an empty layout; it must be rejected whole. Pinned: Task 1.
3. The 0xA5 canary cards and any unformatted card must be skipped without a crash, and `make test-vmu` must pass on the shipped `MENU=1` image. Pinned: Task 1 `vmu_root_ok` cases, Task 5 canary run.
4. The home card swapped for a different card in the same slot after an A must be asked again, not written. Pinned: Task 1 `vmu_decide` fingerprint cases, Task 3 `vmu_write` re-check.
5. START GAME with unsaved changes and no card must start the game, not block. Pinned: Task 1 `VMU_NO_CARD`, Task 5 no-card boot.

---

### Task 1: Pure half — payload, root guard, consent decision (host-tested)

**Files:**
- Create: `loader/vmu_save.h`, `loader/vmu_save.c` (pure half only; KOS half arrives in Task 3 under `#ifndef HOST_TEST`)
- Create: `shims/test/test_vmu_save.c`
- Modify: `shims/Makefile:83` (add the test line after `test_ctl_lib`)

**Interfaces:**
- Consumes: `ctl_lib_t`, `CTL_N_STOCK`, `CTL_N_CUSTOM`, `CTL_N_FUNC`, `MENU_SET_IDX`, `MENU_SET_BYTE`, `MENU_SET_NVAL`, `MENU_N_SETTINGS`, `MENU_DEFAULT_RECORD` from `loader/ctl_lib.h` / `loader/menu_layout.h`.
- Produces (`loader/vmu_save.h`):

```c
#include "ctl_lib.h"
#define VMU_FILE_NAME    "SENKOSP_SYS"
#define VMU_PAYLOAD_LEN  140
#define VMU_FP_LEN       8
#define VMU_ROOT_FP_OFF  0x30            /* vmu_root_t.timestamp: 16 magic + 1 + 4 + 27 pad */
typedef struct { unsigned char port, unit, has_file, fp[VMU_FP_LEN]; } vmu_card_t;  /* a readable card; has_file: a SENKOSP_SYS dirent exists by name */
typedef struct { unsigned char valid, port, unit, fp[VMU_FP_LEN]; } vmu_home_t;
#define VMU_ASK       (-1)
#define VMU_NO_CARD   (-2)
#define VMU_DECLINED  (-3)
void vmu_payload_build(unsigned char out[VMU_PAYLOAD_LEN], const unsigned char rec[16], const ctl_lib_t *L);
int  vmu_payload_parse(const unsigned char *buf, unsigned len, unsigned char rec[16], ctl_lib_t *L);  /* 0 ok; -1 reject, outputs untouched */
int  vmu_root_ok(const unsigned char root[512]);                                                      /* 1 = readable card */
int  vmu_decide(const vmu_home_t *home, int declined, const vmu_card_t *cards, int n);               /* >= 0: index of home in cards -> silent write; else VMU_ASK / VMU_NO_CARD / VMU_DECLINED */
/* KOS half (Task 3) */
int  vmu_scan(vmu_card_t out[8]);                                                                    /* readable cards, enumeration order; count */
int  vmu_load(const vmu_card_t *c, unsigned char rec[16], ctl_lib_t *L);                             /* 0 ok; < 0 absent/invalid */
#define VMU_WRITE_OK    0
#define VMU_WRITE_FULL  (-1)
#define VMU_WRITE_FAIL  (-2)
int  vmu_write(const vmu_card_t *c, const unsigned char rec[16], const ctl_lib_t *L);
```

Root-block byte offsets for `vmu_root_ok` (from `vmu_root_t`, `tools/kos/kernel/arch/dreamcast/include/dc/vmufs.h:55-69`): magic 0x00 (16), timestamp 0x30 (8), `fat_loc` 0x46, `fat_size` 0x48, `dir_loc` 0x4a, `dir_size` 0x4c, `blk_cnt` 0x50, all `uint16_t` little-endian. Cite them in the header comment.

`vmu_decide` order: no cards → `VMU_NO_CARD`; `home->valid` and a card with the same port, unit and fp → its index; `declined` → `VMU_DECLINED`; else `VMU_ASK`. The caller clears `home` whenever the result is not an index.

- [ ] **Step 1: Write the failing test `shims/test/test_vmu_save.c`** (plain `assert`, style of `test_ctl_lib.c`). Helper `good(out, rec, L)` builds: `L` zeroed, `L.custom[0][0] = {3,5,2,4,0,6}`, `L.used[0][0] = 1`, `L.sel[0][1] = CTL_N_STOCK[0]`; `rec = MENU_DEFAULT_RECORD` with `rec[MENU_SET_IDX[0]] = MENU_SET_BYTE[0][2]`. Assertions:

```c
assert(sizeof(ctl_lib_t) == 116);
/* build layout */
assert(memcmp(out, "SKSP", 4) == 0 && out[4] == 1 && out[5] == 0 && out[6] == 0 && out[7] == 0);
assert(memcmp(out + 8, rec, 16) == 0 && memcmp(out + 24, &L, 116) == 0);
/* roundtrip */
assert(vmu_payload_parse(out, 140, rec2, &L2) == 0 && memcmp(rec2, rec, 16) == 0 && memcmp(&L2, &L, 116) == 0);
/* rejects: each on a fresh good() buffer; rec2/L2 pre-filled with 0xEE and asserted unchanged after */
len 139; len 141; out[3] = 'Q'; out[4] = 2; out[24] = CTL_N_FUNC (id 7); out[24 + 96] = 2 (used);
out[24 + 112] = CTL_N_STOCK[0] + CTL_N_CUSTOM (sel out of range);
out[24 + 112] = CTL_N_STOCK[0] + 3 with used[0][3] == 0 (sel names unused slot);
out[8 + 0] ^= 1 (fixed record byte); out[8 + MENU_SET_IDX[0]] = 0x7f (setting byte off-table);
/* root guard: r = 512 zeros, magic 16 x 0x55, fat_loc 254, fat_size 1, dir_loc 253, dir_size 13, blk_cnt 200 */
assert(vmu_root_ok(r) == 1);  blk_cnt 241 -> 1;
all 0xA5 -> 0; r[3] = 0x54 -> 0; fat_size 2 -> 0; dir_size 0 -> 0; dir_size 14 -> 0; blk_cnt 257 -> 0; fat_loc 256 -> 0; dir_loc 256 -> 0;
/* decide: cards[0] = A1 fp "11111111", cards[1] = B1 fp "22222222" */
home invalid, declined 0, n 2 -> VMU_ASK;   home valid A1 fp1, n 0 -> VMU_NO_CARD;
home A1 fp1 -> 0;   home B1 fp2 -> 1;   home A1 fp "33333333" -> VMU_ASK;   home A1 fp1 but cards = {B1} -> VMU_ASK;
home invalid, declined 1 -> VMU_DECLINED;   home A1 fp1, declined 1 -> 0;
```

- [ ] **Step 2: Add the test line to `shims/Makefile` after the `test_ctl_lib` line and run it to see it fail**

```make
	cc -DHOST_TEST -I../loader -o $(B)/test_vmu_save test/test_vmu_save.c ../loader/vmu_save.c ../loader/ctl_lib.c && $(B)/test_vmu_save
```

Run: `make -C shims test`
Expected: FAIL (missing `loader/vmu_save.c` / `vmu_save.h`).

- [ ] **Step 3: Implement the pure half in `loader/vmu_save.c`** with the header above. `vmu_payload_parse` validates everything, then copies. Record rule: for each index `i` in 0..15, if `i` is some `MENU_SET_IDX[k]` the byte must equal one of `MENU_SET_BYTE[k][0..MENU_SET_NVAL[k]-1]`, else it must equal `MENU_DEFAULT_RECORD[i]`. Guard the KOS includes and functions with `#ifndef HOST_TEST` (pattern: `shims/src/gd.c`). Header comment cites `vmu_pkg.h`/`vmufs.h` per the spec's "VMU facts".

- [ ] **Step 4: Run the tests**

Run: `make -C shims test`
Expected: all host tests pass, `test_vmu_save` included.

- [ ] **Step 5: Commit**

```bash
git add loader/vmu_save.h loader/vmu_save.c shims/test/test_vmu_save.c shims/Makefile
git commit -m "vmu_save: payload v1 build/parse with validation, root guard, consent decision (host-tested)"
```

---

### Task 2: Generator — status strips, slot tokens, prompt footers, icon, layout constants

**Files:**
- Modify: `scripts/menu_def.py` (new constants; `SHEET_H`), `scripts/gen_menu_assets.py` (strips, icon, header emission, previews)
- Regenerate + commit: `loader/menu_layout.h`, `loader/menu_sheet.pal8`, `loader/menu_sheet.png`
- Test: `make test` (sheet test exhaustive, nav test), previews viewed

**Interfaces:**
- Produces in `scripts/menu_def.py`:

```python
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
SHEET_W, SHEET_H = 640, 1536
```

- Produces in `loader/menu_layout.h` (generated):

```c
#define MENU_VMU_LINE_Y 416
#define MENU_VMU_NONE (-1)
#define MENU_VMU_LOADED 0 … #define MENU_VMU_DECLINED 8      /* VMU_LINES order */
#define MENU_VMU_N_LINES 9
static const mrect_t        MENU_VMU_LINE[9];        /* message strip, text-width (not 640), text left-aligned, trailing space when tokened */
static const unsigned short MENU_VMU_LINE_X[9];      /* x so that message (+ token) is centred on 640 */
static const unsigned char  MENU_VMU_HAS_TOKEN[9];
static const mrect_t        MENU_VMU_SLOT[8];        /* "A1".."D2", all the same width, text left-aligned; blit at MENU_VMU_LINE_X[i] + MENU_VMU_LINE[i].w */
static const mrect_t        MENU_VMU_FOOT[2];        /* 640 x 24 prompt footers, GREY like the other footers; blit at (0, MENU_TOP_FOOTER_Y) */
static const unsigned char  CTL_DEMO_FUNC[CTL_N_BUTTONS];   /* CUSTOM_DEMO ids in PAD_BUTTONS order (VMUDIAG forced layout) */
#define VMU_FILE_NAME_STR "SENKOSP_SYS"  #define VMU_DESC_SHORT "SENKO NO RONDE"  #define VMU_DESC_LONG "DC PORT SETTINGS AND CONTROLS"  #define VMU_APP_ID "SENKOSP2DC"
static const unsigned short VMU_ICON_PAL[16];        /* ARGB4444, alpha 0xF */
static const unsigned char  VMU_ICON[512];           /* 32x32 4bpp, row-major top-down, high nibble = left pixel */
```

- [ ] **Step 1: Add the constants to `scripts/menu_def.py`** exactly as above (CUSTOM_DEMO and the controls constants already exist).

- [ ] **Step 2: Extend `scripts/gen_menu_assets.py`** after the controls footer strips (same `shelf`):
  - Message strips: width = `textlength(text_with_space)` + 2·pad for tokened lines (replace `{}` by nothing, keep the trailing space), plain text width for the others; `FG` text, `put_left`, `check_fits` against 624 on the composed width (message + token). Assert each tokened text ends with `" {}"` and no `{}` appears elsewhere.
  - Slot tokens: eight strips of one shared width = max token text width + 2·pad, `FG`, left-aligned.
  - Prompt footers: two 640×24 strips, `GREY`, centred (as `CTL_FOOTERS`).
  - Icon: 32×32 RGB canvas `BG`, an `AMBER` band on the bottom 10 rows, `VMU_ICON_TEXT` in `FONT_PATH` at a size that fills the width (`check_fits`-style assert, margin 2) in `FG`; `quantize(16, dither=NONE)`; palette → ARGB4444 `0xF000 | (r >> 4) << 8 | (g >> 4) << 4 | (b >> 4)`; pixels packed two per byte, high nibble first, rows top-down. Assert ≥ 2 distinct indices used. Save `build/vmu_icon.png` scaled ×8 (nearest) for viewing.
  - `menu_layout.h`: emit everything in the Interfaces block; `MENU_VMU_LINE_X[i] = (640 - (msg_w + (tok_w if tokened else 0))) // 2`.
  - Previews: `build/preview_top_vmu.png` = BG canvas, logo strip if `loader/logo_strip.png` exists, the three top labels at `MENU_TOP_DEST` (item 0 highlighted), top footer, `LOADED` + token `A1` at (`MENU_VMU_LINE_X`, 416); `build/preview_top_vmu_prompt.png` = same with `REPLACE` + token `B1` and `VMU_PROMPT_FOOTERS[1]` in place of the top footer. Composite exactly as `menu.c` will blit (band cleared to BG first).
  - Keep the `shelf.bottom <= SHEET_H` assert; raise `SHEET_H` only to the next multiple of 256 that fits.

- [ ] **Step 3: Regenerate and run the tests**

Run: `python3 scripts/gen_menu_assets.py && make test`
Expected: generator prints no assertion, `make test` green (sheet test exhaustive, nav test, maple literals).

- [ ] **Step 4: View `build/preview_top_vmu.png`, `build/preview_top_vmu_prompt.png`, `build/vmu_icon.png`** (Read tool). The line sits between the items and the footer, centred, token hugging the message; the icon letters are legible at 32×32. Fix and regenerate if not.

- [ ] **Step 5: Commit**

```bash
git add scripts/menu_def.py scripts/gen_menu_assets.py loader/menu_layout.h loader/menu_sheet.pal8 loader/menu_sheet.png
git commit -m "menu sheet: VMU status strips, slot tokens, prompt footers, save icon"
```

---

### Task 3: KOS half — card scan with fingerprint, load, write

**Files:**
- Modify: `loader/vmu_save.c` (inside `#ifndef HOST_TEST`), `loader/vmu_save.h` (comments only if needed)
- Modify: `loader/Makefile:4-5` (`OBJS` += `vmu_save.o`), `:25-26` (deps: `vmu_save.o: vmu_save.h ctl_lib.h menu_layout.h`; add `vmu_save.h` to `menu.o`'s deps)

**Interfaces:**
- Consumes: Task 1 header; Task 2 `VMU_ICON_PAL`, `VMU_ICON`, `VMU_DESC_*`, `VMU_APP_ID`.
- Consumes KOS: `maple_enum_type(n, MAPLE_FUNC_MEMCARD)`, `maple_enum_dev(port, unit)`, `vmu_block_read(dev, 255, buf)` (`include/dc/maple/vmu.h:356`), `vmufs_readdir` (`include/dc/vmufs.h:316`, mallocs), `vmufs_read` (`:301`), `vmufs_free_blocks` (`:383`), `vmufs_write(dev, fn, buf, size, VMUFS_OVERWRITE)` (`:334`), `vmu_pkg_build` / `vmu_pkg_parse` (`include/dc/vmu_pkg.h:109,123`; `vmu_pkg_t` fields `util/vmu_pkg.c:82-137`).
- Produces: `vmu_scan`, `vmu_load`, `vmu_write` as declared in Task 1.

- [ ] **Step 1: Implement `vmu_scan(vmu_card_t out[8])`**: walk `maple_enum_type(n, MAPLE_FUNC_MEMCARD)` until NULL; skip units other than 1 and 2 (the token table has 8 slots); read block 255 into a stack `uint8 root[512]`; skip on read error or `!vmu_root_ok`; `fp = root + VMU_ROOT_FP_OFF`; `has_file` from `vmufs_readdir` (entry with `filetype != 0` and `!strncmp(filename, VMU_FILE_NAME, 12)`), `free()` the directory; stop at 8.

- [ ] **Step 2: Implement `vmu_load`**: `maple_enum_dev(c->port, c->unit)` → `vmufs_read(dev, VMU_FILE_NAME, &buf, &size)` → `vmu_pkg_parse(buf, size, &pkg)` → `vmu_payload_parse(pkg.data, pkg.data_len, rec, L)`; `free(buf)`; any failure → -1 with `rec`/`L` untouched.

- [ ] **Step 3: Implement `vmu_write`**: re-read block 255, require `vmu_root_ok` and `memcmp(root + VMU_ROOT_FP_OFF, c->fp, 8) == 0` else `VMU_WRITE_FAIL` (closes the swap window after a consented-but-failed first write). `existing` = `filesize` blocks of our dirent via `vmufs_readdir` (0 if none); if `vmufs_free_blocks(dev) + existing < 2` → `VMU_WRITE_FULL`. Build the payload; fill a zeroed `vmu_pkg_t`: `desc_short`/`desc_long`/`app_id` from the `VMU_DESC_*`/`VMU_APP_ID` defines, `icon_cnt 1`, `icon_anim_speed 0`, `eyecatch_type VMUPKG_EC_NONE`, `data_len VMU_PAYLOAD_LEN`, `icon_pal` ← `VMU_ICON_PAL`, `icon_data` ← `(uint8_t *)VMU_ICON`, `data` ← payload; `vmu_pkg_build(&pkg, &out, &out_size)`; `vmufs_write(dev, VMU_FILE_NAME, out, out_size, VMUFS_OVERWRITE)`; `free(out)`; `rc < 0` → `VMU_WRITE_FAIL` else `VMU_WRITE_OK`. Comment the 780 → 1024-byte padding (`vmufs.c:689-699`).

- [ ] **Step 4: Wire `loader/Makefile` and build**

Run: `make loader && make test`
Expected: links; `make test` green (the maple-literal gate scans only `main.o`/`handoff.o`). Record `sh-elf-nm loader/vmu_save.o | grep ' U '` in the report (expected undefined: `vmufs_*`, `vmu_pkg_*`, `vmu_block_read`, `maple_enum_*`, `malloc`/`free`, `memcmp`/`strncmp`).

- [ ] **Step 5: Commit**

```bash
git add loader/vmu_save.c loader/vmu_save.h loader/Makefile
git commit -m "vmu_save: KOS half -- readable-card scan with root fingerprint, load, consent-checked write"
```

---

### Task 4: Menu integration — boot load, status line, sync, prompt, VMUDIAG

**Files:**
- Modify: `loader/menu.c` (`menu_run` :344-372, `draw_top` :87-92, new static helpers), `loader/menu.h` (no API change)
- Modify: `Makefile:152-165` (add the `VMUDIAG=1` knob next to `MENUDIAG`)

**Interfaces:**
- Consumes: Task 1/3 API; Task 2 `MENU_VMU_*`, `CTL_DEMO_FUNC`; existing `edge()`, `held`, `blit()`, `clear_bg()`, `draw_logo()`, `draw_top()`, `menu_game_record`, `ctl_lib`.
- Produces: no new exports. Serial lines (grep-able, Task 5 depends on them): `VMUSAVE load=<0|-1> home=<A1|-0> cards=<n>`, `VMUSAVE payload=<280 hex chars>` (only when loaded), `VMUSAVE write=<rc> slot=<A1>` (only when forced).

State in `menu.c` (static): `vmu_home_t vmu_home; int vmu_declined; unsigned char vmu_saved[VMU_PAYLOAD_LEN]; int vmu_line = MENU_VMU_NONE, vmu_tok;`. Helpers:

```c
static int  vmu_slot_of(const vmu_card_t *c);                 /* c->port * 2 + c->unit - 1 */
static void vmu_show(int line, int tok);                       /* fill rows 416..439 with MENU_BG_COLOR, blit MENU_VMU_LINE[line] at MENU_VMU_LINE_X[line], then the token strip if MENU_VMU_HAS_TOKEN; MENU_VMU_NONE = band cleared */
static int  vmu_dirty(void);                                   /* vmu_payload_build(now, ...) != vmu_saved */
static void vmu_boot(void);                                    /* vmu_saved = defaults; scan; first card with vmu_load()==0 -> home, vmu_saved rebuilt, line LOADED; none readable -> line NOCARD; else NONE */
static int  vmu_prompt(const vmu_card_t *cards, int n);        /* footer MENU_VMU_FOOT[n > 1]; LEFT/RIGHT cycle (wrap), line ASK or REPLACE by has_file, redraw on change only; A -> index, B -> -1; restores MENU_TOP_FOOTER */
static void vmu_do_write(const vmu_card_t *c);                 /* line SAVING; vmu_write; OK -> vmu_saved = now, line SAVED; FULL -> line FULL; FAIL -> line FAILED */
static void vmu_sync(void);                                    /* spec §Sync */
```

`vmu_sync`: if `!vmu_dirty()`: when `vmu_line == MENU_VMU_NOCARD` and `vmu_scan()` now returns > 0, set `vmu_line = MENU_VMU_NONE`; return. Else `n = vmu_scan(cards)`; `d = vmu_decide(&vmu_home, vmu_declined, cards, n)`; `d >= 0` → `vmu_do_write(&cards[d])`; else `vmu_home.valid = 0` and: `VMU_NO_CARD` → line NOCARD; `VMU_DECLINED` → line DECLINED; `VMU_ASK` → `i = vmu_prompt(cards, n)`; `i < 0` → `vmu_declined = 1`, line DECLINED; else `vmu_home = {1, port, unit, fp}` and `vmu_do_write(&cards[i])`.

`menu_run` changes: at entry after the palette copy: `vmu_boot()`; after `draw_top(cur)` at entry: `vmu_show(vmu_line, vmu_tok)`. START branch: after the release wait, `vmu_sync();` then `break`. After `settings_screen()`/`controls_screen()`: `clear_bg(); draw_logo(); draw_top(cur); vmu_sync(); vmu_show(vmu_line, vmu_tok);`. The reboot combo path in `edge()` is untouched (spec non-goal).

- [ ] **Step 1: Implement the helpers and the `menu_run` changes** as specified. Comments cite the spec section for the consent rule and KOS `maple_irq.c:32-230` for why a fresh `vmu_scan` sees hot-plugged cards.

- [ ] **Step 2: Add the `VMUDIAG` block** at the top of `menu_run` right after `vmu_boot()`:

```c
#if LOADER_VMUDIAG
    vmu_diag();                                   /* logs; forces + writes when nothing loaded */
    memcpy(vram_s, splash_bin, 640 * 480 * 2);
    return;                                       /* no input wait: unattended leg goes on to attract */
#endif
```

`vmu_diag()` (static, inside the same `#if`): `dbglog(DBG_INFO, "VMUSAVE load=%d home=%c%d cards=%d\n", …)` with `-0` for no home; if loaded → `VMUSAVE payload=` + 140 bytes as `%02x`; else force `ctl_lib.custom[0][0] = CTL_DEMO_FUNC`, `ctl_lib.used[0][0] = 1`, `ctl_lib.sel[0][0] = CTL_N_STOCK[0]`, `menu_game_record[MENU_SET_IDX[0]] = MENU_SET_BYTE[0][2]`, then if `cards > 0`: `rc = vmu_write(&cards[0], …)`, log `VMUSAVE write=%d slot=%c%d`. Top `Makefile`: 

```make
# VMUDIAG=1 (pair with SERIAL=1 to hear it; menu stays compiled in): menu_run
# loads from the card, logs VMUSAVE lines, force-writes a known library when
# nothing was loaded, and returns without waiting for input. Test-only, never shipped.
ifeq ($(VMUDIAG),1)
DEFS += -DLOADER_VMUDIAG=1
endif
```

- [ ] **Step 3: Build both flavours and measure**

Run: `make objclean && make gdi VMUDIAG=1 SERIAL=1 && make objclean && make gdi && wc -c build/1ST_READ.BIN && make test`
Expected: both build; size ≤ 3,538,944 (record the number); `make test` green.

- [ ] **Step 4: Commit**

```bash
git add loader/menu.c Makefile
git commit -m "menu: VMU boot load, status line, auto-save with per-card consent prompt, VMUDIAG leg hook"
```

---

### Task 5: Emulator legs — decoder, two-boot save/load leg, framebuffer check, no-card boot, canary

**Files:**
- Create: `scripts/vmu_decode.py`, `scripts/test_vmu_decode.py`, `scripts/test_vmu_save.sh`
- Modify: `Makefile:239-246` (`test:` += `python3 scripts/test_vmu_decode.py`)
- Captures (gitignored): `captures/vmu-save/boot1.stdout.log`, `boot2.stdout.log`, `nocard.stdout.log`, `vmu_save_A1.bin` copy, `icon.png`, `menu_fb.png`

**Interfaces:**
- Consumes: Task 4 serial lines; `scripts/menu_def.py` (`VMU_FILE`, `CUSTOM_DEMO`, `PAD_BUTTONS`, `FUNC_WORDS`, `CTL_CLASSES`, `SETTINGS`, `DEFAULT_RECORD`); Flycast flags from `scripts/test_vmu_untouched.sh` (VMU dir redirect, pads + VMUs pinned, graceful TERM quit) plus `-config Debug:SerialConsoleEnabled=yes -config config:pvr.rend=0` (dbglog → stdout and the renderer that does not segfault this bundle, both as `scripts/capture_rawfb_leg.sh` passes them); the raw framebuffer dump = `FLYCAST_SHOT_RAWFB=<png>` in the environment plus `kill -USR2 <pid>` no earlier than ~30 s after launch (`capture_rawfb_leg.sh` header; `docs/kb/tooling.md` §RAWFB).
- Produces: `vmu_decode.py <vmu_save.bin> [--icon out.png]` printing header fields, `crc_ok`, payload hex, and the decoded settings/layouts by name; exit 1 when no `SENKOSP_SYS`.

Decoder layout (cite in the script): image = 256 blocks × 512 B (Flycast `maple_devs.cpp:679-707`, `write_adr = Block*512 + …`); root at block 255 with the offsets of Task 1; directory entries 32 B (`vmu_dir_t`, `vmufs.h:71-86`: filetype @0, firstblk u16 @2, filename[12] @4, filesize u16 @24, hdroff u16 @26), directory and file both followed through the FAT (u16 per block at `fat_loc`; chain ends at 0xfffa) starting at `dir_loc` / `firstblk`; VMS header per `vmu_hdr_t` (`vmu_pkg.h`): desc_short @0 (16), desc_long @16 (32), app_id @48 (16), icon_cnt u16 @64, anim @66, eyecatch @68, crc u16 @70, data_len u32 @72, palette 16×u16 @96, icon 512 B @128, data @640. CRC per `net_crc16ccitt` (`tools/kos/kernel/net/net_crc.c:52-63`) over the whole file with the crc field zeroed.

- [ ] **Step 1: Write the failing test `scripts/test_vmu_decode.py`**

```python
def test_crc16_xmodem_vector():
    assert crc16ccitt(b"123456789", 0) == 0x31C3        # CRC-16/XMODEM check value (same algorithm as KOS net_crc16ccitt: poly 0x1021, init 0, unreflected)
def test_decode_payload_names():
    rec = bytes.fromhex(M.DEFAULT_RECORD); rec = rec[:6] + bytes([0x02]) + rec[7:]      # GAME DIFFICULTY idx 6 -> HARD
    lib = bytearray(116); ids = [M.FUNC_WORDS.index(M.CUSTOM_DEMO[b]) for b in M.PAD_BUTTONS]
    lib[0:6] = ids; lib[96] = 1; lib[112] = 2                                           # pad slot 0 used; P1 pad sel = CTL_N_STOCK[0] (2)
    d = decode_payload(b"SKSP" + bytes([1, 0, 0, 0]) + rec + bytes(lib))
    assert d["version"] == 1 and d["settings"]["GAME DIFFICULTY"] == "HARD"
    assert d["pad"]["slots"][0] == dict(M.CUSTOM_DEMO) and d["pad"]["sel"] == ["CUSTOM 1", "TOURNAMENT"]
```

Run: `python3 scripts/test_vmu_decode.py` → FAIL (module missing).

- [ ] **Step 2: Implement `scripts/vmu_decode.py`** (`crc16ccitt`, `read_image`, `find_file`, `parse_vms`, `decode_payload`, `icon_png`, CLI). Add the test to `make test`. Run `make test` → green.

- [ ] **Step 3: Write `scripts/test_vmu_save.sh`** with two modes, the canary script's launch/quit idiom and a `captures/vmu-save/` output dir:
  - `diag [vmudir]`: needs the `VMUDIAG=1 SERIAL=1` disc as `build/disc.gdi`. Fresh temp VMU dir unless given; `vmu_save_A1.bin` = 128 KB zeros (Flycast auto-formats it). CFG as the canary's plus `Debug.SerialConsoleEnabled=yes`, pad on port A with VMU in A1 only. Boot 1 (60 s, stdout → `boot1.stdout.log`): require `VMUSAVE load=-1` and `VMUSAVE write=0 slot=A1`; run `vmu_decode.py` on `vmu_save_A1.bin --icon captures/vmu-save/icon.png`: require `crc_ok`, name/short/long/app as `VMU_FILE`, `data_len 140`, decoded settings `GAME DIFFICULTY = HARD`, pad slot 0 = `CUSTOM_DEMO`, `P1 PAD = CUSTOM 1`. Boot 2 (same dir, 60 s → `boot2.stdout.log`): require `VMUSAVE load=0 home=A1` and `VMUSAVE payload=` equal to the decoder's payload hex. Boot 3 "nocard" (`input:device1.1=0`, fresh dir → `nocard.stdout.log`): require `VMUSAVE load=-1 home=-0 cards=0` and the later `boot: MAIN image` line (the game still boots). Print the VMU dir path at the end (kept).
  - `show <vmudir>`: needs the normal disc. Launch Flycast directly (same CFG as `diag`, the dir from `diag`, `FLYCAST_SHOT_RAWFB=captures/vmu-save/menu_fb.png` in the environment); after 35 s `kill -USR2` the PID (the fork writes the scan-out framebuffer PNG), after 5 more seconds quit it gracefully. `capture_rawfb_leg.sh` itself is not reused: it does not forward the VMU-dir config.

- [ ] **Step 4: Run the legs**

Run: `make objclean && make gdi VMUDIAG=1 SERIAL=1 && scripts/test_vmu_save.sh diag`
Expected: the three `require` sets pass; script prints `PASS diag` and the VMU dir.

Run: `make objclean && make gdi && scripts/test_vmu_save.sh show <vmudir> && make test-vmu`
Expected: `menu_fb.png` written; `make test-vmu` prints `PASS: no VMU writes` on this `MENU=1` build (the menu sits with no input; the three 0xA5 cards are unreadable to the loader, the formatted B1 control card is untouched).

- [ ] **Step 5: View `captures/vmu-save/icon.png` and `captures/vmu-save/menu_fb.png`** (Read tool). The icon shows the letters; the menu shows `LOADED FROM VMU A1` between the items and the footer. Note any misplacement and fix in Task 2/4 code before committing.

- [ ] **Step 6: Commit**

```bash
git add scripts/vmu_decode.py scripts/test_vmu_decode.py scripts/test_vmu_save.sh Makefile
git commit -m "vmu legs: VMS decoder (+icon PNG), two-boot save/load leg, no-card boot, canary on the menu build"
```

---

### Task 6: Knowledge base

**Files:**
- Modify: `docs/kb/00-status.md` (top paragraph), `docs/kb/input-map.md` (§Controls library), `docs/kb/phase7-polishing.md` (new `## T21 — VMU persistence (spec 2026-11-01, branch feat/vmu-persistence)` after T20), `docs/kb/tooling.md` (VMUDIAG knob, the two scripts, the Flycast serial key, §VMU canary note), `docs/superpowers/specs/2026-10-24-controls-library-design.md` (one line under the 2026-10-25 amendment: closed by the 2026-11-01 spec)

- [ ] **Step 1: Write the entries.** T21 carries: the file table (name, strings, 780 → 1024 bytes, payload layout), the consent rule in two sentences, the status-line table, the evidence (leg logs and the two viewed PNGs by path, the loader size from Task 4, `make test`/`make test-vmu` results), and the eight hardware legs from the spec as an unchecked operator checklist. Status says "emulator-proven; hardware round pending". The VMU-safety note: criterion 6 unchanged for the game; the loader is now the one writer, in the menu, after consent, verified by the canary on the menu build. Every hardware claim keeps its citation (copy from the spec).

- [ ] **Step 2: Commit**

```bash
git add docs/kb/00-status.md docs/kb/input-map.md docs/kb/phase7-polishing.md docs/kb/tooling.md docs/superpowers/specs/2026-10-24-controls-library-design.md
git commit -m "KB: VMU persistence (emulator-proven; operator legs pending)"
```

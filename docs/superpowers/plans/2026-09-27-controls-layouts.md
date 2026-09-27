# Controls Layouts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Per-port pad layout presets (Tournament default / Classic) plus a fixed
arcade-stick layout auto-applied via DEVINFO capability classification, chosen on a
rebuilt controls page that renders device art + label chips at runtime.

**Architecture:** Layouts are defined once in `scripts/menu_def.py`; the asset
generator emits both the menu's label/anchor tables (`loader/menu_layout.h`) and the
shim's button→JVS tables (`shims/src/layouts.h`, new). The shim picks a layout per
port per poll from the already-latched `devinfo_caps[]`; the loader passes the two
pad presets through a new `SHIM_STATE` word. The menu's controls page becomes the
selector: three rows under the diagram, diagram previews the highlighted row.

**Tech Stack:** Freestanding SH4 C (shim), KOS C (loader), Python 3 + Pillow
(offline asset generator, not a build dependency), host `cc` tests.

**Spec:** `docs/superpowers/specs/2026-09-27-controls-layouts-design.md` (read it
first; it carries the approved layout tables and the UX).

## Global Constraints

- Every hardware/behavioral claim in code comments or KB carries a citation;
  primary sources (KOS source at `tools/kos`, flycast source at
  `../flycast4naomi2dreamcast`) outrank wikis (CLAUDE.md).
- Never commit copyrighted bytes (ROMs, BIOS, disc images, game-extracted pixels).
  All menu art is our own generated work (existing `gen_menu_assets.py` rule).
- Shim code+data budget: 16 KB (`SHIM_CODE_MAX`, enforced by `shim.ld` ASSERT and
  the loader's `SHIM TOO BIG` halt at `loader/main.c:471`).
- Loader builds need KOS: `source tools/kos/environ.sh` from repo root before any
  `make loader` / `make -C loader`.
- House styles: nonzero-init for shim .data flags (RAM boots as garbage on real
  DC); no full-frame clears per keypress in the menu (T9 flicker rule — full
  repaints only on screen entry / device-view switch); menu text is offline-baked
  sprite blits, never runtime-typeset (T7 precedent).
- Generated-and-committed pattern: `menu_layout.h`, `menu_sheet.png`, and the new
  `layouts.h` / controls pages are generator outputs committed to git (Pillow runs
  offline, not at build time).
- No "works" claim for input behavior before the hardware leg (Task 7); emulator
  results are labeled as emulator results.
- Layout IDs are frozen: 0 = PAD_TOURNAMENT (default; the zero-fill IS the
  default), 1 = PAD_CLASSIC, 2 = STICK. Out-of-range pad selector byte ⇒
  Tournament.

---

### Task 1: Layout single source + generated `shims/src/layouts.h`

**Files:**
- Modify: `scripts/menu_def.py` (append layout data after `CONTROLS_ROWS`)
- Modify: `scripts/gen_menu_assets.py` (emit `layouts.h`; no sheet changes yet)
- Create (generated, committed): `shims/src/layouts.h`

**Interfaces:**
- Consumes: nothing new.
- Produces: `shims/src/layouts.h` defining `LAYOUT_PAD_TOURNAMENT 0`,
  `LAYOUT_PAD_CLASSIC 1`, `LAYOUT_STICK 2`, `JVS_LAYOUT_N 6`,
  `typedef struct { unsigned dc, jvs; } jvs_map_t;`,
  `static const jvs_map_t JVS_LAYOUT_PAD[2][6]`, `static const jvs_map_t
  JVS_LAYOUT_STICK[6]` — all entries symbolic (`CONT_*`/`JVS_*`), so the header
  must be `#include`d AFTER those defines (Task 2 does). Python-side names
  `PAD_BUTTONS`, `STICK_BUTTONS`, `PAD_LAYOUTS`, `STICK_LAYOUT`, `FUNC_JVS`,
  `FUNC_WORDS` (Task 5 reuses them for chips/anchors).

- [ ] **Step 1: Add layout data to `scripts/menu_def.py`** (after `CONTROLS_ROWS`,
  before `SHEET_W`):

```python
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
```

- [ ] **Step 2: Emit `layouts.h` from `scripts/gen_menu_assets.py`.** Add this
  function above `main()` and call it as the FIRST line of `main()` (it has no
  Pillow dependency and must not be skipped if a later assert trips):

```python
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
```

- [ ] **Step 3: Run the generator twice and inspect.**

Run: `python3 scripts/gen_menu_assets.py && python3 scripts/gen_menu_assets.py && git status --short`
Expected: prints the usual `gen_menu_assets:` line both times; `git status` shows
ONLY `shims/src/layouts.h` (new) — the sheet/controls PNGs and `menu_layout.h`
must be byte-identical (deterministic generator, nothing else touched). Read
`shims/src/layouts.h` and check the CLASSIC row is byte-for-byte the current
`jvs.c:51-58` mapping: A→M, B→A, X→S, Y→BARRAGE, LTRIG→A, RTRIG→OD.

- [ ] **Step 4: Commit**

```bash
git add scripts/menu_def.py scripts/gen_menu_assets.py shims/src/layouts.h
git commit -m "Controls T1: layout single source + generated shims/src/layouts.h"
```

---

### Task 2: Table-driven `dc_to_jvs` + `jvs_pick_layout` + shim wiring (TDD)

**Files:**
- Modify: `shims/src/jvs.c` (mapping if-chain → tables; new pure classifier)
- Modify: `shims/test/test_host.c` (existing asserts pinned to CLASSIC; new tests)
- Modify: `shims/src/main.c:180-196` (`mie_poll`: per-port layout selection)
- Modify: `shims/include/shim_iface.h` (`SHIM_STATE_PAD_LAYOUT`)
- Modify: `shims/Makefile` (elf rule dep on `src/layouts.h`)

**Interfaces:**
- Consumes: `shims/src/layouts.h` from Task 1 (`jvs_map_t`, `JVS_LAYOUT_PAD`,
  `JVS_LAYOUT_STICK`, `LAYOUT_*`, `JVS_LAYOUT_N`); `devinfo_caps[2]` (non-static
  `u32[2]` in `shims/src/maple.c:56`).
- Produces: `unsigned dc_to_jvs(unsigned dc_buttons, unsigned layout)`;
  `unsigned dc_to_jvs_test(unsigned dc_buttons, unsigned layout, unsigned
  *test_bit)`; `unsigned jvs_pick_layout(unsigned caps, unsigned pad_sel)`
  (all in `jvs.c`, host-testable); `#define SHIM_STATE_PAD_LAYOUT 2` — the
  `SHIM_STATE` word Task 4's loader writes (byte0 = port A pad preset, byte1 =
  port B; 0 Tournament, 1 Classic).

- [ ] **Step 1: Update `shims/test/test_host.c` first.**
  1. Every existing `dc_to_jvs(X)` call becomes `dc_to_jvs(X, LAYOUT_PAD_CLASSIC)`
     — the existing asserts ARE the Classic layout and now pin it forever. Same
     for the composed calls like `dc_to_jvs(dc_cond_to_pressed(...))` →
     `dc_to_jvs(dc_cond_to_pressed(...), LAYOUT_PAD_CLASSIC)`.
  2. Every `dc_to_jvs_test(X, &tb)` becomes `dc_to_jvs_test(X, LAYOUT_PAD_CLASSIC, &tb)`.
  3. Add after the existing `dc_to_jvs` block (before the `dc_cond_to_pressed`
     block):

```c
    /* Layout tables (controls spec 2026-09-27). TOURNAMENT = the tester's EVO
       pad layout, the new DEFAULT; CLASSIC = the pre-2026-09-27 mapping (the
       asserts above, now pinned); STICK = the Naomi cab layout, fixed --
       the only layout that reaches OverDrive on a triggerless device. */
    assert(dc_to_jvs(CONT_A, LAYOUT_PAD_TOURNAMENT) == JVS_M);
    assert(dc_to_jvs(CONT_B, LAYOUT_PAD_TOURNAMENT) == JVS_S);
    assert(dc_to_jvs(CONT_X, LAYOUT_PAD_TOURNAMENT) == JVS_BARRAGE);
    assert(dc_to_jvs(CONT_Y, LAYOUT_PAD_TOURNAMENT) == JVS_A);
    assert(dc_to_jvs(CONT_LTRIG, LAYOUT_PAD_TOURNAMENT) == JVS_OD);
    assert(dc_to_jvs(CONT_RTRIG, LAYOUT_PAD_TOURNAMENT) == JVS_A);
    assert(dc_to_jvs(CONT_START | CONT_DPAD_LEFT, LAYOUT_PAD_TOURNAMENT)
           == (JVS_START | JVS_LEFT));                /* common bits layout-blind */
    assert(dc_to_jvs(CONT_X, LAYOUT_STICK) == JVS_M);
    assert(dc_to_jvs(CONT_Y, LAYOUT_STICK) == JVS_S);
    assert(dc_to_jvs(CONT_Z, LAYOUT_STICK) == JVS_BARRAGE);
    assert(dc_to_jvs(CONT_A, LAYOUT_STICK) == JVS_A);
    assert(dc_to_jvs(CONT_C, LAYOUT_STICK) == JVS_OD); /* OverDrive reachable: the fix */
    assert(dc_to_jvs(CONT_B, LAYOUT_STICK) == 0);      /* B unmapped, tester's spec */
    assert(dc_to_jvs(CONT_RTRIG | CONT_LTRIG, LAYOUT_STICK) == 0); /* no trigger ghosts */

    /* jvs_pick_layout: DEVINFO caps classifier + per-port pad preset byte.
       PAD/STICK caps words as in the block below (flycast maple_devs.cpp:85/:292). */
    assert(jvs_pick_layout(0xfe060f00u, 0) == LAYOUT_PAD_TOURNAMENT);
    assert(jvs_pick_layout(0xfe060f00u, 1) == LAYOUT_PAD_CLASSIC);
    assert(jvs_pick_layout(0xfe060f00u, 0x77) == LAYOUT_PAD_TOURNAMENT); /* junk sel -> default */
    assert(jvs_pick_layout(0xff070000u, 0) == LAYOUT_STICK);
    assert(jvs_pick_layout(0xff070000u, 1) == LAYOUT_STICK);   /* stick ignores pad sel */
    /* per-port independence is just two calls with different sel bytes */
    assert(jvs_pick_layout(0xfe060f00u, 1) != jvs_pick_layout(0xfe060f00u, 0));
```

- [ ] **Step 2: Run and watch it fail.**

Run: `make test`
Expected: FAIL — compile error, `dc_to_jvs` called with 2 args but declared with 1
(and `LAYOUT_PAD_CLASSIC` undeclared).

- [ ] **Step 3: Rework `shims/src/jvs.c`.**
  1. Add below the `CONT_Y/CONT_X` defines (`jvs.c:21-22`):

```c
#define CONT_Z          (1u << 8)   /* KOS controller.h:111 CONT_Z BIT(8); stick top row */
```

  2. Add directly under the `JVS_COIN` define (`jvs.c:40`):

```c
/* GENERATED layout tables (Task-1 header; single source scripts/menu_def.py):
 * LAYOUT_* ids, jvs_map_t, JVS_LAYOUT_PAD[2][], JVS_LAYOUT_STICK[]. Included
 * here, after the CONT_/JVS_ defines the tables reference. */
#include "layouts.h"
```

  3. Replace the whole `dc_to_jvs` body (`jvs.c:42-60`) with:

```c
/* Start + the 8-way are identical in every layout; the per-layout table maps
 * the face/trigger buttons (controls spec 2026-09-27: TOURNAMENT default /
 * CLASSIC per-port pad presets, STICK fixed arcade layout). Callers pick the
 * layout with jvs_pick_layout() below. */
unsigned dc_to_jvs(unsigned dc_buttons, unsigned layout) {
    const jvs_map_t *m = (layout == LAYOUT_STICK) ? JVS_LAYOUT_STICK
        : JVS_LAYOUT_PAD[layout == LAYOUT_PAD_CLASSIC ? 1 : 0];
    unsigned w = 0;
    if (dc_buttons & CONT_START)         w |= JVS_START;
    if (dc_buttons & CONT_DPAD_UP)       w |= JVS_UP;
    if (dc_buttons & CONT_DPAD_DOWN)     w |= JVS_DOWN;
    if (dc_buttons & CONT_DPAD_LEFT)     w |= JVS_LEFT;
    if (dc_buttons & CONT_DPAD_RIGHT)    w |= JVS_RIGHT;
    for (unsigned i = 0; i < JVS_LAYOUT_N; i++)
        if (dc_buttons & m[i].dc) w |= m[i].jvs;
    return w;
}
```

  4. `dc_to_jvs_test` grows the layout parameter (pass-through; Start/A remap is
     layout-independent — the test image's arcade convention):

```c
unsigned dc_to_jvs_test(unsigned dc_buttons, unsigned layout, unsigned *test_bit) {
    *test_bit = (dc_buttons & CONT_START) ? 1u : 0u;
    return dc_to_jvs(dc_buttons & ~(CONT_START | CONT_A), layout)
         | ((dc_buttons & CONT_A) ? JVS_SERVICE : 0u);
}
```

  (Keep its existing header comment; only the signature line changes.)
  5. Add after the `CONT_CAP_*` defines (`jvs.c:145-148`), before
     `dc_cond_to_pressed`:

```c
/* Which layout drives a port right now. A device declaring NO analog axes
 * (triggers or stick) is an arcade stick -- flycast's Ascii Stick declares
 * 0xff070000 (maple_devs.cpp:292) vs standard pad 0xfe060f00 (:85); bit
 * meanings KOS dc/maple/controller.h:258-263 -- and always gets the fixed
 * arcade layout. Anything else is a pad and takes its port's preset byte
 * (SHIM_STATE_PAD_LAYOUT word, shim_iface.h): 1 = Classic, anything else
 * (0 = default, junk) = Tournament. Pure: host-tested. */
unsigned jvs_pick_layout(unsigned caps, unsigned pad_sel) {
    if (!(caps & (CONT_CAP_RTRIG | CONT_CAP_LTRIG |
                  CONT_CAP_ANALOG_X | CONT_CAP_ANALOG_Y)))
        return LAYOUT_STICK;
    return (pad_sel == LAYOUT_PAD_CLASSIC) ? LAYOUT_PAD_CLASSIC
                                           : LAYOUT_PAD_TOURNAMENT;
}
```

- [ ] **Step 4: Run tests to verify they pass.**

Run: `make test`
Expected: `PASS test_host dc_to_jvs + jvs_checksum` and the other test binaries
all pass.

- [ ] **Step 5: Wire the shim callers.**
  1. `shims/include/shim_iface.h`, after `SHIM_STATE_GD_BACKEND` (line 26):

```c
/* Controls layouts (spec 2026-09-27): per-port PAD preset word. byte0 =
 * port A, byte1 = port B; 0 = Tournament (the staged window zero-fill IS
 * the default), 1 = Classic. Sticks never read it -- the shim classifies
 * per poll from DEVINFO caps (src/jvs.c jvs_pick_layout). Loader writes it
 * at staging (loader/main.c, Task 4). */
#define SHIM_STATE_PAD_LAYOUT 2
```

  2. `shims/src/main.c` `mie_poll` (`main.c:180-196`): update the prototypes for
     `dc_to_jvs`/`dc_to_jvs_test` wherever main.c declares them (grep
     `dc_to_jvs` — declarations only, skip the `#if 0` legacy block at
     main.c:756-1767), add `extern u32 devinfo_caps[2];` and
     `unsigned jvs_pick_layout(unsigned caps, unsigned pad_sel);` next to them,
     and replace the poll body lines 187-194 with:

```c
    /* getcond FIRST (a success-after-dead poll refreshes devinfo_caps, Task 3),
     * then classify: stick -> fixed arcade layout, pad -> this port's preset
     * byte from the loader-staged word (0 Tournament / 1 Classic). */
    u32 p1 = maple_getcond(0), p2 = maple_getcond(1);
    u32 sel = UW(SHIM_STATE + 4 * SHIM_STATE_PAD_LAYOUT);
    u32 l1 = jvs_pick_layout(devinfo_caps[0], sel & 0xffu);
    u32 l2 = jvs_pick_layout(devinfo_caps[1], (sel >> 8) & 0xffu);
    if (UW(SHIM_STATE) == 1u) {         /* test boot: P1 Start->Test, A->Service */
        unsigned test_bit;
        j1 = dc_to_jvs_test(p1, l1, &test_bit);
        f[0x1f] = (u8)(test_bit ? 0x80 : 0x00);
    } else {
        j1 = dc_to_jvs(p1, l1);         /* DC port A -> P1 */
    }
    j2 = dc_to_jvs(p2, l2);             /* DC port B -> P2 (no pad -> 0 = idle) */
```

  3. `shims/Makefile`: the elf rule gains the generated header as a prerequisite:

```make
$(B)/shim.elf: $(SRCS) shim.ld include/shim_iface.h src/layouts.h
```

- [ ] **Step 6: Build the shim and re-run tests.**

Run: `make shims && make test`
Expected: shim links (the 16 KB `shim.ld` ASSERT holding is the size gate —
tables add ~150 bytes), all host tests pass.

- [ ] **Step 7: Commit**

```bash
git add shims/src/jvs.c shims/src/main.c shims/include/shim_iface.h \
        shims/test/test_host.c shims/Makefile
git commit -m "Controls T2: table-driven dc_to_jvs, per-port layout pick from DEVINFO caps"
```

---

### Task 3: Dead-port re-probe closes the stale-caps hot-swap gap

**Files:**
- Modify: `shims/src/maple.c` (`maple_getcond` success/fail paths; the
  `devinfo_caps` header comment)

**Interfaces:**
- Consumes: `probe_devinfo(port)`, `devinfo_caps[]` (both already in maple.c).
- Produces: no API change — behavioral: first successful poll after any failed
  poll re-probes DEVINFO before the caps are consumed.

- [ ] **Step 1: Add the flag and the re-probe.** In `shims/src/maple.c`:
  1. Next to `fail_cnt` (maple.c:105):

```c
/* Controls spec 2026-09-27: a port that failed and then answers again is a
 * candidate hot-swap (pad<->stick) or late plug-in, so its latched caps may
 * describe the PREVIOUS device -- and the layout now follows the caps. One
 * DEVINFO on the first success after any failure; steady state sends nothing
 * extra. Closes the stale-caps note that used to sit on devinfo_caps.
 * Nonzero init = .data (house style); starting "dead" costs one probe on the
 * first-ever successful poll, right after init's own probe -- harmless. */
static u32 was_dead[2] = { 1, 1 };
```

  2. Replace the success return (maple.c:137-139) with:

```c
        if ((rx[0] & 0xff) == 8) {
            u32 w2 = rx[2], w3 = rx[3];    /* latch: probe below reuses RX */
            if (was_dead[port]) {          /* swap/late-plug: refresh caps */
                was_dead[port] = 0;
                probe_devinfo(port);
            }
            return dc_cond_to_pressed(w2, w3, devinfo_caps[port]);
        }
```

  3. Set the flag on the fall-through failure path, next to the T11 wake
     (maple.c:141-142):

```c
    was_dead[port] = 1;                    /* next success re-probes DEVINFO */
    if ((++fail_cnt[port] & 63u) == 0)     /* T11: wake hot-plugged pads */
        probe_devinfo(port);
```

  4. Update the `devinfo_caps` header comment (maple.c:53-55): delete the
     `ponytail:` stale-caps caveat and replace with one line:
     `Hot-swap staleness: closed by was_dead below (re-probe on first success after a failure).`

- [ ] **Step 2: Build + tests.**

Run: `make shims && make test`
Expected: links within budget; host tests unaffected (this path is MMIO-side, not
host-testable — behavior is verified on hardware in Task 7's swap case).

- [ ] **Step 3: Commit**

```bash
git add shims/src/maple.c
git commit -m "Controls T3: DEVINFO re-probe on first poll success after a dead port"
```

---

### Task 4: Loader carries the presets into SHIM_STATE

**Files:**
- Modify: `loader/menu.h` (export), `loader/menu.c` (state variable)
- Modify: `loader/main.c:475-477` region (staging write)

**Interfaces:**
- Consumes: `SHIM_STATE_PAD_LAYOUT` (Task 2), `STAGE_SHIM`/`SHIM_STATE`/`SHIM_BASE`
  (existing staging idiom at `loader/main.c:475-477`).
- Produces: `unsigned char menu_pad_layout[2]` (0 Tournament / 1 Classic; index =
  DC port) — Task 6's controls page mutates it; the staging write consumes it.

- [ ] **Step 1: Add the state.** `loader/menu.h` gains, next to
  `menu_game_record`:

```c
extern unsigned char menu_pad_layout[2];  /* per-port PAD preset: 0 Tournament, 1 Classic */
```

  `loader/menu.c`, under `menu_dirty` (menu.c:16):

```c
/* Controls-page selector state (spec 2026-09-27): per-port pad preset,
 * 0 = Tournament (default), 1 = Classic. Session-only like the record above
 * (VMU save-all-settings will serialize it later); consumed by main.c's
 * SHIM_STATE staging write. Sticks ignore it (shim classifies from DEVINFO). */
unsigned char menu_pad_layout[2] = { 0, 0 };
```

- [ ] **Step 2: Stage it.** In `loader/main.c`, directly after the
  `SHIM_STATE[1] = backend` write (main.c:477):

```c
    /* SHIM_STATE[2] = per-port pad layout (controls spec 2026-09-27): byte0
     * port A, byte1 port B; 0 Tournament (default), 1 Classic. Unconditional:
     * with the menu off (MENU=0) the defaults {0,0} restate the zero-fill. */
    *(uint32 *)(STAGE_SHIM + (SHIM_STATE - SHIM_BASE) + 4 * SHIM_STATE_PAD_LAYOUT) =
        (uint32)menu_pad_layout[0] | ((uint32)menu_pad_layout[1] << 8);
```

- [ ] **Step 3: Build everything.**

Run: `source tools/kos/environ.sh && make shims && make loader`
Expected: clean build of `build/1ST_READ.BIN`.

- [ ] **Step 4: Emulator smoke (defaults flip to Tournament here).**
  Build a GDI (`make gdi`) and boot it in the instrumented Flycast
  (`../flycast4naomi2dreamcast/build/Flycast.app`, one-call foreground pattern,
  kill by PID). Confirm it reaches attract; with keyboard/pad input confirm in
  the game (or via a `SERIAL=1` build's SHIM_TRACE line) that DC **B now emits
  JVS_S (Sub, 0x0100)** — the observable Tournament-vs-Classic discriminator.
  Label the result as emulator-only.

- [ ] **Step 5: Commit**

```bash
git add loader/menu.h loader/menu.c loader/main.c
git commit -m "Controls T4: loader stages per-port pad presets into SHIM_STATE[2]"
```

---

### Task 5: Art gate + controls pages, label chips, anchors (OPERATOR-GATED)

**Files:**
- Create (operator-provided, committed): `loader/pad_diagram.png` (HKT-7700),
  `loader/stick_diagram.png` (HKT-7300)
- Modify: `scripts/menu_def.py` (anchors, footer, `SHEET_H`), 
  `scripts/gen_menu_assets.py` (two pages + chips + CTL_ tables + previews)
- Modify: `loader/Makefile` (blob rules), regenerated `loader/menu_layout.h`,
  `loader/menu_sheet.png`, new `loader/controls_pad.png`, `loader/controls_stick.png`
- Delete: `loader/controls_diagram.png`, `loader/controls.png`, `CONTROLS_ROWS`
  in `menu_def.py`

**Interfaces:**
- Consumes: Task 1's `PAD_LAYOUTS`/`STICK_LAYOUT`/`FUNC_WORDS` + the two art PNGs.
- Produces (in `menu_layout.h`, for Task 6): `CTL_WORD[6]` (mrect_t chips, one per
  FUNC_WORDS entry, 160x24 cells), `CTL_PAD_FUNC[2][6]` / `CTL_STICK_FUNC[6]`
  (unsigned char function indices, button order = `PAD_BUTTONS`/`STICK_BUTTONS`),
  `CTL_PAD_ANCHOR[6][2]` / `CTL_STICK_ANCHOR[6][2]` (unsigned short label cell
  top-left x,y), `CTL_ROW_LABEL[3][2]` (row labels, normal/highlight),
  `CTL_PAD_VALUE[2]` + `CTL_STICK_VALUE` (value chips), `CTL_ROW_LABEL_X`,
  `CTL_ROW_VALUE_X`, `CTL_ROW_Y(i)`, `CTL_FOOTER` + `CTL_FOOTER_X/Y`. Loader
  blob symbols `ctl_pad_bin` / `ctl_stick_bin` (640x480 RGB565 pages).

- [ ] **Step 1: STOP — request the art from the operator.** Per the operator-leg
  protocol: stop and wait. Ask for two images (ChatGPT generation is fine):
  HKT-7700 standard controller and HKT-7300 arcade stick; consistent line-art
  style; every button clearly visible; **no text on or near buttons**; plain
  near-white background (autocrop + floodfill must work); each button needs
  clear margin for a 160x24 label chip beside it. Save as
  `loader/pad_diagram.png` / `loader/stick_diagram.png`. **View both images**
  (Read tool) before proceeding — verification-discipline rule.

- [ ] **Step 2: Extend `menu_def.py`.**
  1. Delete `CONTROLS_ROWS` (its ground-truth role is superseded by
     `PAD_LAYOUTS`/`STICK_LAYOUT`; JVS bits stay documented in
     `docs/kb/input-map.md`).
  2. Change `SHEET_W, SHEET_H = 640, 768` to `640, 1024` (chips + row cells need
     ~250px more shelf; blob grows 320 KB — fine, loader tops out far below
     `STAGING_ADDR`).
  3. Add:

```python
CTL_FOOTER = "UP/DOWN: ROW   LEFT/RIGHT: CHANGE   B: BACK"
CTL_ROW_ITEMS = ["P1 PAD LAYOUT", "P2 PAD LAYOUT", "STICK LAYOUT"]
CTL_PAD_VALUES = ["TOURNAMENT", "CLASSIC"]          # index = layout id
CTL_STICK_VALUE = "ARCADE (FIXED)"
# Label-chip anchors: top-left of the 160x24 chip per button, measured off the
# operator art AFTER it lands (Step 4 iterates against build/preview_*.png).
# Art region is y 8..340; rows start at y 352 (CTL_ROW_Y in the generator).
PAD_ANCHORS   = {"A": (0, 0), "B": (0, 0), "X": (0, 0), "Y": (0, 0),
                 "LTRIG": (0, 0), "RTRIG": (0, 0)}   # measured in Step 4
STICK_ANCHORS = {"A": (0, 0), "B": (0, 0), "X": (0, 0), "Y": (0, 0),
                 "Z": (0, 0), "C": (0, 0)}           # measured in Step 4
```

- [ ] **Step 3: Extend `gen_menu_assets.py`.**
  1. Extract the existing controls-page pipeline (autocrop → scale → tint →
     floodfill, lines 185-225) into a helper and run it for BOTH diagrams, with
     the art region reduced to fit above the selector rows (max 620 wide x 330
     high, pasted centered at y 8..340). Bake the layout-INVARIANT labels into
     each page at page-build time (the generator already typesets): "MOVE"
     beside the d-pad/lever, "START" beside Start. Output
     `loader/controls_pad.png` and `loader/controls_stick.png` (640x480, BG
     background). The footer (`CTL_FOOTER`) is also baked into both pages at
     y 452, centered.
  2. Sheet additions (after the settings footer, same shelf):
     - 6 `CTL_WORD` chips: 160x24 cells, `FUNC_WORDS` text centered, `F_ROW`,
       FG on BG (`check_fits` each).
     - 3 `CTL_ROW_LABEL` rows: 288x28 normal/highlight pairs (same pattern as
       `MENU_SET_LABEL`, text = `CTL_ROW_ITEMS`).
     - Value chips via the existing `get_chip()`: `CTL_PAD_VALUES` + 
       `CTL_STICK_VALUE`.
  3. Emit the `CTL_*` tables listed under **Interfaces** into `menu_layout.h`
     (same style as the `MENU_*` tables; function indices =
     `FUNC_WORDS.index(...)` looked up through each layout dict, button order =
     `PAD_BUTTONS`/`STICK_BUTTONS`; anchor values straight from
     `PAD_ANCHORS`/`STICK_ANCHORS`), plus:

```python
    lines.append("#define CTL_ROW_LABEL_X 48")
    lines.append("#define CTL_ROW_VALUE_X 344")
    lines.append("#define CTL_ROW_Y(i) (352 + (i) * 34)")
```

  4. Generator asserts: every anchor cell inside x 0..480 / y 8..316 (so the
     160x24 chip stays in the art region); no two anchor cells on the same page
     overlap; anchors nonzero once art exists.
  5. Previews (verification-discipline): composite chips onto the pages exactly
     as the C code will blit them and write `build/preview_pad_tournament.png`,
     `build/preview_pad_classic.png`, `build/preview_stick.png` (gitignored
     `build/`, never committed).

- [ ] **Step 4: Measure anchors, iterate, VIEW.** View each diagram, fill
  `PAD_ANCHORS`/`STICK_ANCHORS` with real coordinates, run the generator, VIEW
  all three previews. Iterate until every label reads unambiguously next to its
  button. Do not proceed on unviewed output.

- [ ] **Step 5: `loader/Makefile`.** Replace the `controls.bin`/`controls_blob.o`
  rules (lines 152-160) with the same pattern twice
  (`controls_pad.png` → `../build/ctl_pad.bin` → `ctl_pad_blob.o` with syms
  `_binary____build_ctl_pad_bin_start=_ctl_pad_bin` etc., and the `_stick`
  twin); swap `controls_blob.o` for `ctl_pad_blob.o ctl_stick_blob.o` in
  `OBJS`; update the `menu_sheet.bin` rule's dimension args `640 768` →
  `640 1024`; update the `clean` list (`ctl_pad.bin ctl_pad.bmp ctl_stick.bin
  ctl_stick.bmp` in, `controls.bin controls.bmp` out — the clean-kills-stale-bins
  rule).

- [ ] **Step 6: Delete the superseded assets.**

```bash
git rm loader/controls_diagram.png loader/controls.png
```

  (menu.c still references `controls_bin` until Task 6 — expected: the loader
  does not build between Steps 6 and Task 6 Step 1. Do Task 6 before pushing any
  build; if an intermediate loader build is needed, do Task 6 first.)

- [ ] **Step 7: Commit**

```bash
git add scripts/menu_def.py scripts/gen_menu_assets.py loader/Makefile \
        loader/menu_layout.h loader/menu_sheet.png \
        loader/controls_pad.png loader/controls_stick.png \
        loader/pad_diagram.png loader/stick_diagram.png
git commit -m "Controls T5: HKT-7700/7300 pages, label chips + anchors, sheet 1024"
```

---

### Task 6: Controls page becomes the selector

**Files:**
- Modify: `loader/menu.c` (replace `controls_screen`, menu.c:95-99)

**Interfaces:**
- Consumes: every `CTL_*` symbol from Task 5, `menu_pad_layout` from Task 4,
  existing `blit()`/`edge()`.
- Produces: user-visible selector; `menu_pad_layout[]` mutations that Task 4's
  staging write ships.

- [ ] **Step 1: Replace `controls_screen` in `loader/menu.c`.** Swap the
  `controls_bin` extern (menu.c:13) for `ctl_pad_bin`/`ctl_stick_bin` and
  replace menu.c:95-99 with:

```c
extern uint8 ctl_pad_bin[];
extern uint8 ctl_stick_bin[];

/* Controls page = layout selector (spec 2026-09-27). Three rows under the
 * diagram; the diagram previews the HIGHLIGHTED row (pad rows: that port's
 * preset on the HKT-7700 art; stick row: the fixed arcade layout on the
 * HKT-7300 art). Chips carry the page BG, so they sit seamlessly on the
 * art's cleared margins. Art memcpy only on entry / device-view change --
 * T9 flicker rule; row/label changes re-blit fixed cells. */
static void ctl_draw_labels(int cur) {
    for (int i = 0; i < 6; i++) {
        if (cur == 2)
            blit(CTL_WORD[CTL_STICK_FUNC[i]],
                 CTL_STICK_ANCHOR[i][0], CTL_STICK_ANCHOR[i][1]);
        else
            blit(CTL_WORD[CTL_PAD_FUNC[menu_pad_layout[cur]][i]],
                 CTL_PAD_ANCHOR[i][0], CTL_PAD_ANCHOR[i][1]);
    }
}

static void ctl_draw_rows(int cur) {
    for (int i = 0; i < 3; i++)
        blit(CTL_ROW_LABEL[i][i == cur], CTL_ROW_LABEL_X, CTL_ROW_Y(i));
    blit(CTL_PAD_VALUE[menu_pad_layout[0]], CTL_ROW_VALUE_X, CTL_ROW_Y(0));
    blit(CTL_PAD_VALUE[menu_pad_layout[1]], CTL_ROW_VALUE_X, CTL_ROW_Y(1));
    blit(CTL_STICK_VALUE, CTL_ROW_VALUE_X, CTL_ROW_Y(2));
}

static void ctl_draw_all(int cur) {
    memcpy(vram_s, cur == 2 ? ctl_stick_bin : ctl_pad_bin, 640 * 480 * 2);
    ctl_draw_labels(cur);
    ctl_draw_rows(cur);
}

/* Same caps rule the shim applies (jvs.c jvs_pick_layout): no analog axes
 * declared = arcade stick. function_data[0] is the controller function's raw
 * DEVINFO data word (KOS dc/maple.h:252 maple_devinfo_t; same word the shim
 * latches as devinfo_caps). First enumerated controller = the one driving
 * this menu (edge() uses the same lookup). */
static int stick_on_menu_pad(void) {
    maple_device_t *c = maple_enum_type(0, MAPLE_FUNC_CONTROLLER);
    return c && !(c->info.function_data[0] & 0x00000f00u);
}

static void controls_screen(void) {
    int cur = stick_on_menu_pad() ? 2 : 0;   /* open on the device in hand */
    ctl_draw_all(cur);
    for (;;) {
        uint32 e = edge();
        if (e & CONT_B) return;
        if (e & (CONT_DPAD_UP | CONT_DPAD_DOWN)) {
            int nxt = (cur + ((e & CONT_DPAD_DOWN) ? 1 : 2)) % 3;
            int devchg = (nxt == 2) != (cur == 2);
            cur = nxt;
            if (devchg) ctl_draw_all(cur);
            else { ctl_draw_labels(cur); ctl_draw_rows(cur); }
        }
        if ((e & (CONT_DPAD_LEFT | CONT_DPAD_RIGHT)) && cur < 2) {
            menu_pad_layout[cur] ^= 1;       /* 0 Tournament <-> 1 Classic */
            ctl_draw_labels(cur);
            ctl_draw_rows(cur);
        }
    }
}
```

- [ ] **Step 2: Build.**

Run: `source tools/kos/environ.sh && make shims && make loader && make test`
Expected: clean build; host tests pass.

- [ ] **Step 3: Emulator leg (Flycast, one-call foreground pattern).**
  `make gdi`, boot in the instrumented Flycast:
  1. Pad on port A: CONTROLS opens on the P1 PAD row, HKT-7700 art, Tournament
     labels. Left/Right flips labels in place (A: MAIN, B: SUB↔ACTION, X:
     BARRAGE↔SUB, Y: ACTION↔BARRAGE, L/R swap). Down twice → stick view,
     HKT-7300 art, ARCADE (FIXED). Screenshots of all three states; VIEW them.
  2. Set P1 = CLASSIC, start game: DC B must emit Action (block) again —
     the Classic discriminator (SHIM_TRACE or in-game behavior).
  3. Configure Flycast port A device = Ascii Stick (Settings → Controls):
     CONTROLS must open on the STICK row; in-game the stick's C button must
     fire OverDrive with no menu interaction.
  Record results in the KB as emulator results.

- [ ] **Step 4: Commit**

```bash
git add loader/menu.c
git commit -m "Controls T6: controls page = per-port layout selector with live preview"
```

---

### Task 7: Docs, KB, and the hardware claim gate (OPERATOR-GATED)

**Files:**
- Modify: `docs/kb/input-map.md` (§DC pad layout → the three-layout tables,
  per-port selection rule, new defaults, DEVINFO classifier + re-probe note),
  `docs/kb/phase7-polishing.md` (new ledger entry, next free T-number, linking
  spec + this plan + the tester request in `CONTROLS_TASK.MD`),
  `docs/kb/00-status.md` (state + next step)

**Interfaces:**
- Consumes: everything shipped in Tasks 1-6.
- Produces: KB truth + the verified-on-hardware claim (or the failure record).

- [ ] **Step 1: Update the three KB docs.** input-map.md gets the exact tables
  from the spec (Classic/Tournament/Stick, JVS bits unchanged) and states:
  defaults Tournament; per-port preset via `SHIM_STATE[2]`; stick = fixed
  arcade layout selected per poll by `jvs_pick_layout` on `devinfo_caps`;
  `was_dead` re-probe closes the hot-swap gap. Cite spec, `CONTROLS_TASK.MD`,
  and flycast/KOS sources already cited in code.

- [ ] **Step 2: Build the release candidate.**

Run: `source tools/kos/environ.sh && make gdi && make deploy CARD=/Volumes/GDEMU/<slot>`
Expected: five disc files on the card entry, `dot_clean` run (playbook trap).

- [ ] **Step 3: STOP — hardware leg (operator, stop-and-wait).** Checklist for
  the operator on the real DC (Ascii Stick + standard pad available):
  1. Pad port A, defaults: verify Tournament (A Main, B Sub, X Barrage,
     Y Action, L OverDrive, R Action).
  2. Menu → CONTROLS → P1 = CLASSIC: verify the old mapping (B Action,
     R OverDrive).
  3. Stick port A: page opens on STICK row; in game X Main, Y Sub, Z Barrage,
     A Action, C OverDrive (OverDrive reachable = the fixed defect), B inert.
  4. Mixed: stick A + pad B, then pad A + stick B — each side correct
     simultaneously; P2 preset applies to whichever port holds the pad.
  5. Mid-session swap on port A pad→stick during gameplay: arcade layout takes
     over within ~1 s (the was_dead re-probe); swap back: pad preset returns.
  6. Boot with port B empty; plug a pad mid-game → P2 alive with B's preset;
     repeat with a stick → arcade layout.
  7. Menu regression: SETTINGS rows still work; START boots; controls page
     legible on a real TV (chip contrast, art brightness).
- [ ] **Step 4: Record the verdict** in `docs/kb/phase7-polishing.md` (per-case
  PASS/FAIL + serial lines if a SERIAL build was used) and update
  `docs/kb/00-status.md`. Only after PASS may any external message claim the
  feature works.
- [ ] **Step 5: Commit**

```bash
git add docs/kb/input-map.md docs/kb/phase7-polishing.md docs/kb/00-status.md
git commit -m "Controls T7: KB updated; hardware leg verdict recorded"
```

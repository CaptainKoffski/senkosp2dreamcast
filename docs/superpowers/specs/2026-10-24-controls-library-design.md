# Controls library — shared custom layouts for pads and sticks (design)

2026-10-24. Origin: operator review of the 0.20.0 CUSTOM pad layout
(`docs/kb/input-map.md` §Custom pad layout) against the tester's round-2
message (`CONTROLS_TASK.MD` §Round 2). Brainstormed and approved in-session
2026-10-24 (row model, fork moment, delete placement and cap chosen by the
operator from mockups; mockups archived under `.superpowers/brainstorm/`,
gitignored).

Supersedes the CUSTOM part of
`docs/superpowers/specs/2026-09-27-controls-layouts-design.md` and the
2026-10-15 custom-layout branch's menu model. The three stock layouts, the
B.O.S.S. macro, the chip editor's controls and the DEVINFO pad/stick
classifier are all kept as they are.

## Intent

Testers send half-formed layout wishes (a screenshot of another port, "we can
work something from here"). The operator does not want to turn each of those
into a baked preset. The menu should let a tester build, keep and share their
own layouts so well that they stop asking. The feel must be production-grade:
obvious on first use, no hidden rules, and reusable in the operator's future
port kit (other titles, possibly 4 players).

## Problems with the shipped CUSTOM (0.20.0)

1. CUSTOM always starts from Tournament; tweaking Old means rebuilding it.
2. Sticks cannot be customized at all (fixed ARCADE).
3. Nothing on screen says CUSTOM is editable (the "A edits" affordance has
   no hint).
4. One custom layout per port, owned by that port: a layout built for P1
   cannot be applied to P2 without redoing it.

## Goals

- **Tweak what you see.** On any row, A opens the editor on the layout that
  row currently shows. Editing a stock layout forks it into a custom one;
  the stock stays intact.
- **Same for sticks.** Stick layouts are selectable and customizable per
  port, exactly like pad layouts.
- **Visible affordances.** The footer always says what A, X and B do on the
  current row.
- **Shared library.** Custom layouts belong to nobody; any port can select
  any custom layout of its device class.
- **Several custom layouts**, with delete, capped at 8 per device class.
- **Always a way back** to the stock layouts.
- **VMU-ready state**: session-only today, but laid out so the planned
  save-all-settings task serializes it as-is.
- **Port-count-agnostic model** for the port kit: rows are generated from
  one port-count constant.

## Non-goals

- VMU persistence (separate task; this design only shapes the bytes).
- Naming layouts. The menu has no runtime font (every word is a baked
  sprite), so custom layouts are numbered: CUSTOM 1 … CUSTOM 8. Operator
  accepted numbered names 2026-10-24.
- A per-player sub-page (the "C" mockup). Not needed at 2 ports; the model
  below is what a 4p title would reuse behind a different page.
- Changing any stock layout, the B.O.S.S. mask, D-pad/analog handling, the
  test-boot mapping or the reset combo.

## Anti-goals

- Modal dialogs or multi-step wizards. The page stays one screen; every
  action is one or two presses with the footer as the only prompt.
- Growing `1ST_READ.BIN` past the CDI/GDI loader region (1728 sectors =
  3,538,944 bytes; today's loader is 3,536,144 bytes, 2.8 KB spare). The
  sprite-sheet format change below is what keeps this possible.
- A runtime text renderer. Every string stays a generator-baked sprite.

## Constraints (measured, with sources)

- **Sprite sheet is nearly full**: `scripts/gen_menu_assets.py` reports
  `sheet 936/1024px used` (run 2026-10-24); `SHEET_W, SHEET_H = 640, 1024`
  is RGB565, 1,310,720 bytes of the loader. This design needs roughly
  270 px more (eight `< CUSTOM n >` value chips, one row-label pair, an
  `< ARCADE >` chip, a red `DELETE?` cell, six footer strips). It does not
  fit, and the sheet cannot grow in RGB565 (loader region above).
- **The logo already solved the same problem**: `logo_strip.pal8` is a
  512-byte RGB565 palette followed by 8bpp indices
  (`gen_menu_assets.py:628`, `loader/menu.c draw_logo`). The sheet goes
  the same way (§Sheet format).
- **Stick page labels are baked** today (no `STICK_ANCHORS`;
  `gen_menu_assets.STICK_PAGE` tags, 2026-10-03 re-route because the
  operator found chip-grid routes overcomplicated and baking let each
  label sit at its button's own height). Customizable sticks need runtime
  chips again; §Stick chips keeps the 2026-10-03 positions so the routes
  stay straight.
- **Stick B has no art coordinate** (`STICK_PAGE.buttons` lists X Y Z A C
  only) because the stock Arcade layout leaves B unmapped. A custom stick
  layout may assign B, so B needs a chip and a leader.
- **Shim carrier**: `SHIM_STATE` is `u32[8]` at `SHIM_BASE + 0x5200`
  (`shims/include/shim_iface.h`); words 0 boot mode, 1 GD backend,
  2 pad preset bytes, 3–4 per-port custom words; 5–7 free.
- **Menu input**: both ports are configured from the first enumerated pad
  (`loader/menu.c buttons(0)`), unchanged.

## Decisions (approved by the operator 2026-10-24 unless marked *my call*)

### 1. Controls page = four fixed rows, grouped by device

```
            [ device art + label chips for the highlighted row ]

   P1 PAD LAYOUT      < TOURNAMENT >
   P2 PAD LAYOUT      < CUSTOM 1 >

   P1 STICK LAYOUT    < ARCADE >
   P2 STICK LAYOUT    < CUSTOM 2 >
   UP/DOWN: ROW   LEFT/RIGHT: LAYOUT   A: CUSTOMIZE   B: BACK
```

- UP/DOWN moves the highlight across the four rows; the art page flips
  once, between the pad group and the stick group. Every assignment is
  visible and settable whatever is plugged in right now (chosen over
  "rows follow the detected device": a hot-swap must never change what a
  row means, and a stick layout must be settable before the stick is in).
- LEFT/RIGHT cycles the highlighted row through its class's library in
  this order: stock layouts, then every **existing** custom layout by slot
  number. Pad: TOURNAMENT, OLD, CUSTOM 1…8. Stick: ARCADE, CUSTOM 1…8.
  Unused slots are skipped. Wraps.
- The art previews the highlighted row's layout: HKT-7700 art with pad
  chips for pad rows, HKT-7300 art with stick chips for stick rows.
- The page opens on the P1 STICK row iff a stick drives the menu
  (`stick_on_menu_pad()`, unchanged rule), else P1 PAD.
- Defaults: every pad row TOURNAMENT, every stick row ARCADE (the
  2026-09-27 default decision stands).
- Row count = `CTL_PORTS` (2) × classes (2). *My call*: rows are generated
  from `CTL_PORTS` and the class list in `scripts/menu_def.py`, so the port
  kit changes one constant; a 4p title would instead want the per-player
  page, which this model supports but this design does not build.

### 2. One shared library per device class

- Two classes: **pad** (buttons A B X Y L R, `PAD_BUTTONS` order) and
  **stick** (A B X Y Z C, `STICK_BUTTONS` order). A layout is six 4-bit
  function ids (`FUNC_WORDS` order, unchanged: MAIN, SUB, BARRAGE, ACTION,
  OVERDRIVE, B.O.S.S., NONE). The classes are separate libraries because
  the physical buttons differ.
- Per class: the stock layouts (pad: Tournament, Old; stick: Arcade) and
  `CTL_N_CUSTOM = 8` custom slots. A slot is either unused or holds a
  layout. Slot *i* is always named CUSTOM *i+1*; numbers are stable while a
  layout exists and a freed number is reused by the next new layout
  (lowest free slot wins).
- A custom layout is one object. Two rows selecting CUSTOM 1 share it:
  editing it from either row changes both. That is the point (operator
  requirement 8).
- Stock layouts are immutable. Nothing in the menu can write them.
- Cap = 8 per class, operator's choice. The VMU is not the limit (one
  512-byte block holds over a hundred 3-byte layouts); the sprite sheet and
  LEFT/RIGHT cycling length are.

### 3. Customize = A on any row; fork on first change

- Footer on a stock row: `A: CUSTOMIZE`. Footer on a custom row:
  `A: EDIT` (plus `X: DELETE`, §4).
- A opens the existing chip editor (`ctl_edit`) on the layout the row
  shows, pad or stick. Editor controls are unchanged: d-pad walks the
  chips by the cone-rule nav table, A opens value mode (amber band),
  LEFT/RIGHT cycles the seven functions, A keeps, B restores, B outside
  value mode returns to the rows. The four rows stay drawn under the art
  while editing (dimmed look is *my call* and optional; the row value must
  stay readable because it is where the fork shows).
- **Fork on first change** (chosen over fork-on-enter): while the row's
  selection is a stock layout, the editor shows the stock values and
  nothing is copied. The first time the player *keeps* a value that
  differs from the stock one, the menu copies the stock layout into the
  lowest free slot of that class, writes the kept change into the copy,
  switches **only the highlighted row** to that slot, and redraws the row
  value (`< CUSTOM n >`). Keeping an unchanged value, or restoring with B,
  forks nothing. Leaving the editor without a kept change leaves the row on
  the stock layout. Other rows selecting the same stock layout are
  untouched.
- While the row's selection is already a custom layout, A edits that
  object in place; no copy.
- **Library full**: A on a stock row when all 8 slots of that class are
  used does not open the editor. The footer shows
  `ALL 8 CUSTOM SLOTS USED: DELETE ONE FIRST` until the next key press
  (that press is processed normally). This check is up front so the fork
  can never fail mid-edit.
- Editor footers (new; today the editor leaves the page footer as is):
  frame mode `D-PAD: BUTTON   A: CHANGE   B: DONE`; value mode
  `LEFT/RIGHT: FUNCTION   A: KEEP   B: UNDO`.

### 4. Delete = X on the rows page, two presses

- Only while the highlighted row shows a custom layout (footer advertises
  `X: DELETE` only then). X on a stock row does nothing.
- First X: the row's value cell turns into a red `DELETE?` cell and the
  footer reads `X: DELETE   ANY OTHER BUTTON: CANCEL`. Second X deletes.
  Any other button cancels: the value cell and footer are restored and
  **that press is consumed** (B must not also leave the page).
- Delete frees the slot. Every row of that class selecting the slot
  (highlighted or not) falls back to the class default (TOURNAMENT /
  ARCADE); rows and, if the highlighted row changed, the art chips are
  redrawn. The cycle order simply loses that entry.

### 5. Stick chips

- The stick page gains `STICK_ANCHORS` and runtime chips like the pad page;
  the baked function tags are removed (START and MOVE stay baked, they carry
  no function). *My call*: chip cells sit exactly where the 2026-10-03 tags
  sit, so the leaders keep their routes and straightness: MAIN left column
  at the tag's y (30), SUB/BARRAGE/OVERDRIVE/ACTION right column at tag ys
  65/95/123/173, chip cell `CHIP_W×CHIP_H` (126×24) with its top at
  `tag_y − 12`, right-column `chip_x` chosen so the cell ends inside the
  page (≈ 480; the builder measures). Chip labels now come from the layout,
  so the text under the tag positions is whatever the row's layout says.
- **B gets a chip**: a leader from the B button (bottom row between A and
  C; the builder measures its art coordinate like the others) to a new
  right-column cell at a free y (≈ 148, between OVERDRIVE and ACTION, so
  the column still reads top-down). In the stock Arcade layout it shows
  NONE, as the pad page shows NONE on an unmapped button.
- `CTL_EDIT_FIRST` for the stick is MAIN (top-left), matching the pad's L.
  The nav generator (`gen_menu_assets.edit_nav`, cone rule, reachability
  assert, `scripts/test_gen_menu_nav.py`) runs on the stick anchors too;
  with the positions above LEFT from any right-column chip lands on MAIN
  and RIGHT from MAIN lands on SUB.

### 6. Shim: two resolved words per port, no preset tables

- The loader resolves every row to a packed 6-nibble word and stages four
  words: pad A, pad B, stick A, stick B. The shim no longer knows presets.
  *My call* on the carrier: `SHIM_STATE[3]`/`[4]` keep their meaning (pad
  words, A B X Y L R nibbles), `[5]`/`[6]` are the stick words (A B X Y Z C
  nibbles), and `SHIM_STATE[2]` becomes a "layout words staged" flag
  (1 = valid). The shim uses the staged word when the flag is set and the
  generated stock default word (`JVS_WORD_TOURNAMENT` / `JVS_WORD_ARCADE`,
  emitted by the generator from the same tables) when it is not, so a
  zero-filled window is never read as a layout, with or without the menu
  built in (`LOADER_MENU=0` stages the defaults like today's unconditional
  write).
- `jvs_pick_layout(caps)` keeps only the DEVINFO classifier (no analog
  caps ⇒ stick) and returns the class; `dc_to_jvs_custom` gains a class
  argument selecting the button-bit list (`PAD_BUTTONS` vs
  `STICK_BUTTONS`, both generated). `JVS_LAYOUT_PAD[2]`,
  `JVS_LAYOUT_STICK`, `LAYOUT_PAD_OLD/TOURNAMENT/CUSTOM` and
  `PAD_SEL_CUSTOM` are deleted. *My call* (builder check 2026-10-24): the
  generator still emits every stock layout as a packed word
  (`JVS_WORD_PAD[2]` = Tournament, Old; `JVS_WORD_STICK` = Arcade) so the
  host tests can pin all three against the old literals; the shim's poll
  path only ever uses the Tournament/Arcade words as the unstaged
  fallback. The test-boot path (`dc_to_jvs_test`, `SHIM_STATE[0] == 1`)
  keeps its behaviour but routes through the resolved pad word like
  everything else, since its tables are gone; test boots skip the menu, so
  it sees the default word.
- Everything else in the poll path (active-low normalization, trigger
  threshold, capability-gated axes, `was_dead[]` re-probe, hot-swap, the
  reset combo) is untouched.

### 7. Sheet format: 8bpp palettized

- `menu_sheet` becomes the logo's format: 512-byte RGB565-LE palette then
  8bpp indices, quantized by the generator the way `logo_strip.pal8` is
  (`gen_menu_assets.py:628`). `blit()` in `loader/menu.c` becomes a
  palette-lookup loop (the only consumer; page bins, splash and logo paths
  are unchanged). At `SHEET_H = 1024` this frees ~655 KB of the loader;
  the builder raises `SHEET_H` to the smallest multiple of 256 that fits
  the new sprites (the generator's budget assert decides), staying at or
  under 2048 so the loader never exceeds today's size. `make cdi` and
  `make gdi` region checks stay the proof.
- The controls footer leaves the page bins (today it is baked into
  `ctl_pad_bin`/`ctl_stick_bin` at y 452–476) and becomes sheet strips
  blitted per state (§3, §4 strings plus the rows-page pair). The page
  bins' footer area is plain background.
- New sprites: `P1/P2 STICK LAYOUT` row labels (normal + highlighted),
  `< ARCADE >`, `< CUSTOM 1 >` … `< CUSTOM 8 >` (shared by both classes),
  the red `DELETE?` cell, six footer strips. Footer strings are set in
  `scripts/menu_def.py`; `check_fits` is the gate. If a strip does not fit
  640 px at `F_ROW`, the builder drops `UP/DOWN: ROW` from that strip
  first, then shortens words; never a smaller font for one strip only.

### 8. Loader state (VMU-ready)

```c
#define CTL_PORTS     2
#define CTL_N_CUSTOM  8
#define CTL_CLASSES   2            /* 0 pad, 1 stick */
unsigned char ctl_custom[CTL_CLASSES][CTL_N_CUSTOM][6];   /* function ids */
unsigned char ctl_custom_used[CTL_CLASSES][CTL_N_CUSTOM]; /* 0/1 */
unsigned char ctl_sel[CTL_CLASSES][CTL_PORTS];  /* 0..n_stock-1 = stock id,
                                                   n_stock + i = CUSTOM i+1 */
```

Plus the existing 16-byte `menu_game_record`. That is 96 + 16 + 4 + 16 =
132 bytes of settings; the future VMU task prepends a format/version byte
and serializes these arrays verbatim (fits one data block with the
mandatory VMS header in a second). Nothing in this design writes a VMU.

## Verification

- **Host tests** (`shims/test/test_host.c`, TDD): the generated stock
  words produce, for every button, the same JVS bits the old tables did
  (keep the old expected literals: Tournament, Old, Stick/Arcade); the
  classifier returns pad/stick from the measured caps words
  (`0xfe060f00`, `0xff070000`); stick words index A B X Y Z C (Z → BARRAGE
  and C → OVERDRIVE in Arcade); the staged-flag fallback picks the default
  word; B.O.S.S., NONE, junk-nibble, OR-of-two-buttons and layout-blind
  Start/8-way cases carried over.
- **Generator checks**: `scripts/test_gen_menu_nav.py` extended to the
  stick anchors (reachability, cone rule); the sheet budget assert; a host
  self-check that the loader's library logic (fork to lowest free slot,
  delete fallback, cycle order skipping unused slots, library-full refusal)
  behaves, as a small C or Python test of the pure functions, per the
  ponytail rule of one runnable check.
- **Previews viewed**: pad and stick pages for a stock row, a custom row,
  the DELETE? state, the library-full footer.
- **Emulator leg** (Flycast fork, `FAKESTART` build, tooling.md §Legs):
  boot smoke on the regenerated sheet (menu renders, game launches, 0
  `SHIMERR`); the fork cannot inject pad input, so navigation is an
  operator leg.
- **Operator legs** (claim gate, operator-leg protocol): (1) emulator
  walkthrough: four rows, art flips once, LEFT/RIGHT order, A on
  TOURNAMENT → edit → first kept change flips the row to CUSTOM 1 → both
  pad rows can select CUSTOM 1 → editing it from P2 changes P1's preview →
  X twice deletes it and both rows fall back → library-full footer after
  eight forks; same on the stick rows incl. B assigned; (2) hardware, real
  DC + GDEmu, pad in one port and stick in the other: each port plays with
  its selected custom layout, B.O.S.S. still fires, stick custom with Z/C
  remapped works, hot-swap keeps per-port selection; CDI and GDI both
  build and boot.

## Left to the builder

- Exact row y positions for four rows plus the group gap (art ends ≈ y 290;
  footer stays at y 452), the dim look while editing, and whether the row
  value flashes on fork.
- Stick right-column `chip_x`, the B button art coordinate and its leader
  route, in `STICK_PAGE` / `STICK_ANCHORS`.
- Palette quantization settings for the sheet and the final `SHEET_H`.
- Footer wording trims if `check_fits` rejects a strip.
- Whether `SHIM_STATE[2]` stays a flag or the shim simply trusts the words
  (the loader writes them unconditionally); the flag is the safer default.
- Order of work and branch name (plan: `superpowers:writing-plans`).

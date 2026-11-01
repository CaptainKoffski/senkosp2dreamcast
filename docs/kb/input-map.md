# Input map — senkosp (Phase 2, measured)

Captured 2026-08-19, legs `captures/input.log` (13-control press sequence)
and `captures/service-retest.log` (Service re-test, 4 clean presses,
attract screen only) — recipe: `tooling.md` §Phase 2 capture harness.
Source: `JVSREPORT` (P1 JVS digital word, `maple_jvs.cpp:2241`) — in both
legs it is the *only* channel that carries a per-press signal; `MIERESP
sub=15` (MIE input response, `maple_if.cpp:292`), which the brief expected
to cross-check byte.bit against, never fired during any button hold in
either leg — see "Why no MIE sub=15 byte.bit" below. Instrumented fork @
`f014a410c5f267ba58dd1d007edcf680044c5d09` (current HEAD of
`../flycast4naomi2dreamcast`, same commit as `maple_jvs.cpp:2241` cited
above).

Bindings used for the input.log leg (keyboard, Flycast arcade profile —
supersedes the stage-A prediction in `task-4-report.md`, per user rebind
before capture): stick = arrow keys; M = X; S = C; A = S; Barrage = B;
OverDrive = D; Start = Enter; Coin = A; Test = T; Service = Q (same Service
binding used, unchanged, for the service-retest.log leg).

Neutral JVS word baseline: `0000` (P1 digital word, all controls released).

| Control | Flycast binding used | MIE sub=15 byte.bit | JVS word bit |
|---|---|---|---|
| Up | Up Arrow | n/a¹ | `0x2000` (`NAOMI_UP_KEY`, `maple_devs.h:80`) — measured |
| Down | Down Arrow | n/a¹ | `0x1000` (`NAOMI_DOWN_KEY`) — measured |
| Left | Left Arrow | n/a¹ | `0x0800` (`NAOMI_LEFT_KEY`) — measured |
| Right | Right Arrow | n/a¹ | `0x0400` (`NAOMI_RIGHT_KEY`) — measured |
| M | X | n/a¹ | `0x0200` (`NAOMI_BTN0_KEY`, `maple_devs.h:85`; senkosp label "MAIN") — measured |
| S | C | n/a¹ | `0x0100` (`NAOMI_BTN1_KEY`; senkosp label "SUB") — measured |
| A | S | n/a¹ | `0x0040` (`NAOMI_BTN3_KEY`; senkosp label "ACTION") — measured |
| Barrage (C) | B | n/a¹ | `0x0080` (`NAOMI_BTN2_KEY`, `maple_devs.h:87`) — arcade "Button 3" / senkosp label "MAIN+SUB". Held bit flipped exactly once (`bits-vs-baseline: 1`) — a plain single-button read, not a runtime M+S combo — measured |
| OverDrive | D | n/a¹ | `0x0020` (`NAOMI_BTN4_KEY`, `maple_devs.h:89`) — see "OverDrive wire" below — measured |
| Start | Enter | n/a¹ | `0x8000` (`NAOMI_START_KEY`, `maple_devs.h:77`) — measured |
| Service | Q | n/a¹ | `0x4000` (`NAOMI_SERVICE_KEY`, `maple_devs.h:78`) — measured (retest leg, see "Service retest" below) |
| Coin | A | n/a¹ | not in the 16-bit word — bit 19, `NAOMI_COIN_KEY = 1 << 19` (`maple_devs.h:98`), **source-derived**, not measured — see "Coin / Test" below |
| Test | T | n/a¹ | not in the 16-bit word — bit 18, `NAOMI_TEST_KEY = 1 << 18` (`maple_devs.h:97`), **source-derived**, not measured — see "Coin / Test" below |

¹ `MIERESP sub=15` never fires during any button hold in either leg — see
"Why no MIE sub=15 byte.bit" below for the line-range evidence.

## DC pad layout (Phase 3, user-approved 2026-08-19) — SUPERSEDED 2026-09-29

**Superseded 2026-09-29 by the three-layout controls system** (§Three-layout
controls, below): a tester request (EVO Japan player, archived in
`CONTROLS_TASK.MD`) plus the shipped-defect finding that OverDrive lived only
on triggers — unreachable on an arcade stick — replaced this single binding
with three selectable layouts. The table below is kept as the historical
Phase-3/4 record; it is byte-identical to what is now called the **Old**
layout (one of the three), not the live default. See §Three-layout controls
for the current binding, the per-port selection rule, and verification
status.

The port's original controller binding, decided in the Phase 3 design spec
(`docs/superpowers/specs/2026-08-19-phase3-reverse-engineering-design.md`
§9 "Control layout (decided in this design)") and recorded here verbatim.
Phase 4's loader/shim implemented it as the sole layout through 2026-09-27;
the wire bit each row targets is the measured one from the table above.

| DC pad | Game control |
|---|---|
| D-pad + analog (both) | Stick (8-way) |
| A | M — Main |
| X | S — Sub |
| B | A — Action |
| Y | Barrage |
| R trigger | OverDrive |
| L trigger | A — Action (duplicates B; operator request 2026-08-30 — block is held during barrier-shots, awkward on a face button. Supersedes the Phase-3 "unbound / may duplicate Barrage" reservation; `shims/src/jvs.c` CONT_LTRIG, threshold 128 like R) |
| Start | Start |

Coin needs no binding — free-play is baked in per the charter; Start alone
starts a credit. Test/Service: wire bits known (this file — Test bit 18,
Service `0x4000`), but the access mechanism (e.g. boot-time combo) is a
Phase 4 loader decision, not a pad binding.

Notes for the implementer, from the measured rows above: the DC pad has 6
face/trigger controls for 5 game buttons, which is why L is free; Barrage is
a **plain single button** on the wire (`0x0080`, one bit flip — not a runtime
M+S combo, despite its "MAIN+SUB" cabinet label); and OverDrive's final wire
bit is `0x0020` (`NAOMI_BTN4_KEY`) after senkosp's own descriptor remap — see
§OverDrive wire.

## Three-layout controls (decided + shipped 2026-09-27) — current binding

*2026-10-24: the three layouts and the caps classifier below still bind;
the shim mechanism described here (`jvs_pick_layout`, the preset bytes in
`SHIM_STATE[2]`, the three-row selector) is replaced by §Controls library.*

**HARDWARE VERIFICATION: PASS (operator, 2026-09-30).** The operator ran
the interactive emulator walkthrough and the hardware-leg matrix (task-7
brief, Step 3: pad defaults, Old preset, Stick row, mixed ports,
mid-session hot-swap, empty-port hot-plug, menu regression on a real TV)
and reported both PASS in-session ("I've tested in both emulator and HW").
Single-rig evidence per the project's standing caveat (one console, one
GDEMU, one SD card). Release tag `0.12.0`.

**Origin.** A tester (EVO Japan competitor for this game) requested a
gamepad remap and, separately, a layout usable with a permanently-attached
arcade stick, in a message archived verbatim in `CONTROLS_TASK.MD`. The old
single mapping (§DC pad layout above) put OverDrive only on the R trigger —
a real defect on a stick, which has no triggers. Design decided in-session
2026-09-27 by the operator and approved against the tester's own wording;
spec `docs/superpowers/specs/2026-09-27-controls-layouts-design.md`, plan
`docs/superpowers/plans/2026-09-27-controls-layouts.md`. Full task ledger
and verification state: `docs/kb/phase7-polishing.md` §T17.

**The three layouts.** JVS bits are unchanged from the measured table above
(M 0x0200, S 0x0100, A 0x0040, Barrage 0x0080, OverDrive 0x0020, Start
0x8000); only which DC control drives which bit changes, and D-pad/analog
handling is identical in all three. Single source of truth:
`scripts/menu_def.py`, generating `shims/src/layouts.h` (the shim's
`JVS_LAYOUT_PAD[2]`/`JVS_LAYOUT_STICK` tables, `shims/src/layouts.h:15-27`) and
`loader/menu_layout.h` (the controls-page chips/anchors) from one place.

| DC control | Old (id 1) | Tournament (id 0, default) | Stick (id 2, fixed) |
|---|---|---|---|
| A | Main | Main | Action |
| B | Action | Sub | unmapped |
| X | Sub | Barrage | Main |
| Y | Barrage | Action | Sub |
| Z | — | — | Barrage |
| C | — | — | OverDrive |
| L trigger | Action (dup) | OverDrive | n/a |
| R trigger | OverDrive | Action | n/a |
| Start | Start | Start | Start |

Old is byte-for-byte the old single mapping (§DC pad layout above); it was
named CLASSIC until 2026-09-30 (operator: "nothing classic in it") — the
spec, the plan, and pre-rename ledger/commit text still use that name.
Tournament and Stick are the tester's own layouts verbatim from
`CONTROLS_TASK.MD`; Stick's B is deliberately unmapped, matching the
tester's "B = none". Tables: `shims/src/layouts.h:15-27` (generated,
committed).

**Per-poll layout selection — `jvs_pick_layout()`.** Each port's layout is
chosen fresh every poll from that port's DEVINFO capability word (`caps`)
and its preset byte (`pad_sel`), `shims/src/jvs.c:161-167`:

```c
unsigned jvs_pick_layout(unsigned caps, unsigned pad_sel) {
    if (!(caps & (CONT_CAP_RTRIG | CONT_CAP_LTRIG |
                  CONT_CAP_ANALOG_X | CONT_CAP_ANALOG_Y)))
        return LAYOUT_STICK;
    return (pad_sel == LAYOUT_PAD_OLD) ? LAYOUT_PAD_OLD
                                           : LAYOUT_PAD_TOURNAMENT;
}
```

A device that declares **none** of the four analog capability bits (R
trigger, L trigger, analog X, analog Y — `CONT_CAPABILITY_RTRIG/LTRIG` at
bits 8/9, analog X/Y at bits 10/11, KOS `dc/maple/controller.h:258-263`) is
classified as an arcade stick and always gets the fixed Stick layout,
regardless of any preset. Measured caps words: standard DC pad `0xfe060f00`
(all four bits set, flycast `maple_devs.cpp:85`) vs Flycast's Ascii Stick
`0xff070000` (none set, `maple_devs.cpp:292`) — the same DEVINFO word and
the same capability-gating mechanism the 2026-09-26 Arcade-Stick fix
introduced (§Non-standard controllers, below); `jvs_pick_layout` is a second
consumer of that same `caps`/`devinfo_caps[]` latch, not a new probe. Any
device that *does* declare an axis is treated as a pad and takes its port's
preset byte: 1 selects Old, anything else (0 = default, or an
out-of-range/junk byte) selects Tournament.

**Per-port presets — `SHIM_STATE[2]`.** The menu selection is staged into
shared state, one byte per port, by `loader/main.c:478-482`:

```c
/* SHIM_STATE[2] = per-port pad layout (controls spec 2026-09-27): byte0
 * port A, byte1 port B; 0 Tournament (default), 1 Old. Unconditional:
 * with the menu off (MENU=0) the defaults {0,0} restate the zero-fill. */
*(uint32 *)(STAGE_SHIM + (SHIM_STATE - SHIM_BASE) + 4 * SHIM_STATE_PAD_LAYOUT) =
    (uint32)menu_pad_layout[0] | ((uint32)menu_pad_layout[1] << 8);
```

read back per-port by the shim (`shims/src/main.c:193`,
`sel = UW(SHIM_STATE + 4 * SHIM_STATE_PAD_LAYOUT)`) and fed to
`jvs_pick_layout()` alongside that port's `devinfo_caps[]`. A zero-fill
`SHIM_STATE` word (menu compiled out, or menu never visited) reproduces
`{0,0}` — both ports default to Tournament — so the default-Tournament
decision holds even with `LOADER_MENU=0`. This state is session-only, same
as every other `SHIM_STATE` word (loader-staged, not EEPROM-backed).

**Menu selector.** The pre-game controls page (`loader/menu.c`) is a
three-row selector: P1 PAD LAYOUT, P2 PAD LAYOUT, STICK LAYOUT (fixed,
display-only). Left/right on a pad row flips that port's preset
(`loader/menu.c:155-158`, `menu_pad_layout[cur] ^= 1`); the diagram
underneath previews whichever row is highlighted, on the HKT-7700 (pad) or
HKT-7300 (stick) art page (the operator's AI-generated diagrams, vectorized
2026-09-30 — `loader/*_diagram.svg` traced with vtracer, rendered by resvg;
see `docs/kb/tooling.md` §vtracer). The page opens on the Stick row
iff a stick is detected on the menu's own input pad, via the same caps rule
(`loader/menu.c:132-140 stick_on_menu_pad()`, masking
`function_data[0] & 0x00000f00` — the same four capability bits
`jvs_pick_layout` tests, read through KOS's own `maple_device_t` rather than
the shim's latched `devinfo_caps[]`, since the menu runs before the shim is
resident).

**Hot-swap gap closed — `was_dead[]` re-probe.** DEVINFO is latched once by
`probe_devinfo()` and cached in `devinfo_caps[]` (`shims/src/maple.c:54-73`);
a poll failure (unplug) sets `was_dead[port] = 1`
(`shims/src/maple.c:112,153`), and the **first successful poll after any
failure** re-probes DEVINFO before trusting the reply
(`shims/src/maple.c:146-150`), on top of the pre-existing T11 64-fail
hotplug re-probe. This is what makes a pad↔stick swap on one port pick up
the new device's caps — and therefore its layout — promptly instead of
running stale.

**Default change.** Decided 2026-09-27 (operator + tester, in-session):
**Tournament is the new default** (was Old/the old single mapping).
Old is preserved, one menu press away, for players who prefer the
original binding. Rationale: Tournament matches the tester's stated EVO
layout, and — unlike the old default — reaches OverDrive without a
trigger-bearing device, which the fixed Stick layout also achieves.

Verification: host tests `shims/test/test_host.c` cover all three tables,
the `jvs_pick_layout` classifier, per-port independence, and out-of-range
preset fallback; one emulator boot-leg screenshot
(`docs/kb/img/controls-t6-menu-top.png`) shows the controls page rendering;
the operator's emulator walkthrough and hardware-leg matrix both PASS
(2026-09-30 — see the verification notice at the top of this section).

### Custom pad layout + B.O.S.S. macro (2026-10-15, branch `feat/custom-layout`)

**Superseded (menu model only) by §Controls library below (2026-10-24,
`feat/controls-library`)**: the per-port CUSTOM, its preset byte and
`SHIM_STATE[2]`/`[3..4]` meanings, and `dc_to_jvs_port` are gone. The
B.O.S.S. mask and its 2026-10-24 hardware verification still stand.

**Origin.** The same tester's third controls message (verbatim in
`CONTROLS_TASK.MD` §Round 2): a single-button B.O.S.S. — on the cabinet,
B.O.S.S. mode is the Main+Sub+Action chord (tester's statement; the 360
Rev.X port exposes "B.O.S.S." as an assignable button, visible in his
reference screenshot of Rev.X's Controller Setting screen) — plus a 360
layout he admires but no concrete DC placement ("we can work something from
here"). Nobody could say which DC button B.O.S.S. belongs on, so instead of
guessing a preset, the pad rows gained a per-port **CUSTOM** layout the
player edits in the menu; whatever he settles on can be baked as a preset.
Old, Tournament and Stick are untouched (their `layouts.h` tables are
byte-identical; the header only gained definitions).

**Function ids.** `scripts/menu_def.py` `FUNC_WORDS` gained `B.O.S.S.`
before `NONE`: ids 0 MAIN, 1 SUB, 2 BARRAGE, 3 ACTION, 4 OVERDRIVE,
5 B.O.S.S., 6 NONE (generated `shims/src/layouts.h` `JVS_FUNC_*`,
`JVS_FUNC_MASK[]`). B.O.S.S. is the mask `JVS_M | JVS_S | JVS_A` (0x0340):
one DC button raises all three JVS bits in the same poll — a cleaner chord
than any human press, and nothing the cabinet's own three buttons could not
send.

**State.** Preset byte value 2 (`PAD_SEL_CUSTOM`) in the existing
`SHIM_STATE[2]` word means CUSTOM for that port; the layout itself is one
word per port, `SHIM_STATE[3]` (port A) / `SHIM_STATE[4]` (port B)
(`shims/include/shim_iface.h` `SHIM_STATE_PAD_CUSTOM`): six 4-bit function
ids, nibble i = pad button i in `PAD_BUTTONS` order A, B, X, Y, L, R.
`loader/main.c` stages both words next to the preset bytes, unconditionally.
The shim reads them every poll (`shims/src/main.c` `c1`/`c2`) but consults a
port's word only when `jvs_pick_layout()` returned `LAYOUT_PAD_CUSTOM` (3):
`dc_to_jvs_port()` routes to `dc_to_jvs_custom()` then and to the table
`dc_to_jvs()` otherwise (`shims/src/jvs.c`), so the menu-off zero-fill is
never interpreted and a stick still wins the classifier. A junk nibble
(≥ `JVS_FUNC_N`) maps to nothing. Test boot (`SHIM_STATE[0] == 1`) keeps the
plain `dc_to_jvs_test()` path — a CUSTOM P1 falls to Tournament there; the
test menu only needs Start/A.

**Menu.** Pad rows cycle TOURNAMENT → OLD → CUSTOM with LEFT/RIGHT. Each
port's custom layout starts as a copy of Tournament (`CTL_CUSTOM_DEFAULT`,
generated from `menu_def.CTL_CUSTOM_DEFAULT`) so CUSTOM is never empty. On a
row showing CUSTOM, **A enters edit mode** (`loader/menu.c` `ctl_edit()`):
an amber 2-px frame (`MENU_HI_COLOR`) around one chip, starting at the
top-left one (`CTL_EDIT_FIRST` = L). **Cursor rework 2026-10-22** (operator:
UP/DOWN-only walking was counter-intuitive — on the L chip you press RIGHT
to reach R, not DOWN): the d-pad moves the frame to the neighbouring chip
in that direction, `CTL_EDIT_NAV[chip][UP, DOWN, LEFT, RIGHT]`, generated
from the chip anchors by `gen_menu_assets.edit_nav()` — the nearest chip
inside the direction's 90° cone (lateral offset ≤ forward offset, so DOWN
on the lone left-column chip never hops across the page), no wrap. On the
shipped page: L ↔ R by LEFT/RIGHT, UP/DOWN walk the right column R, Y, B,
A, X, and LEFT from any right-column chip lands on L. MOVE and START carry
no chip and are unreachable by design. **A opens value mode**: the chip
turns into an amber band with black text (`CTL_WORD_HI` — the selected
settings row's look, so "amber band = LEFT/RIGHT changes this" reads the
same everywhere in the menu) and LEFT/RIGHT cycle that button through all
seven function words; **A keeps the value, B restores the one it had**,
either returns to the frame. B outside value mode returns to the rows. The
frame sits just outside the chip cell and is erased by restoring the page's
own pixels from `ctl_pad_bin` (a leader line ends right under it — a flat
fill would nick it). The table and the cone rule have a host self-check,
`scripts/test_gen_menu_nav.py` (in `make test`), and the generator asserts
every chip is reachable from the first, so an anchor redesign that strands
a chip fails at generation time. The footer is unchanged: the "A edits
CUSTOM" affordance has no on-screen hint yet (tester-facing lab feature). Session-only like every
menu setting — nothing was written to a VMU; power-off reverted to Tournament
(superseded 2026-11-01: §Controls library → Persistence).
Both ports are edited from the first enumerated pad, as the presets are.

**Verification.** Host tests (`shims/test/test_host.c`): the classifier
returns CUSTOM for preset byte 2 and STICK for a stick regardless; the
B.O.S.S. mask is exactly the three bits; Tournament packed as a custom word
equals the Tournament table for every button; NONE and junk nibbles yield
nothing; Start/8-way stay layout-blind; two custom buttons OR;
`dc_to_jvs_port` ignores the word off CUSTOM. Generator preview
`build/preview_pad_custom_demo.png` (viewed): the CUSTOM row chip, the
B.O.S.S. and NONE chips land on their buttons; `make cdi` still fits the
fixed 1792-sector loader region. Emulator boot smoke
`captures/customlayout/boot-smoke3` (FAKESTART build, default Tournament
path through the new staging + read code): **PASS** — the pre-game menu
renders on the regenerated sheet (RAWFB dump at t=15 s, kept as
`shot-boot-smoke3-003-t15s.png`), the fake START launches the game, and
160 s unattended end with 0 `SHIMERR`, 0 `System reset`, 18,648 `TAEND`,
1,374 `GDDMA` transfers, cart streamed to +194 MB. Two earlier launch
attempts died inside the emulator before any boot (leftover Vulkan
renderer setting; the SH4 vmem `Verify Failed` flake) — both known
host-side traps, `tooling.md` §Legs: customlayout. Cursor rework
(2026-10-22): `scripts/test_gen_menu_nav.py` PASS (watched failing first);
previews `build/preview_pad_custom_cursor.png` / `preview_pad_custom_editing.png`
viewed; emulator boot smoke `captures/customlayout/nav-smoke2` **PASS** (top
menu renders on the regenerated sheet at t=15 s; 160 s: 0 `SHIMERR`,
0 `System reset`, 18,592 `TAEND`, cart to +194 MB; `nav-smoke1` never
launched — leftover emulator process, `tooling.md` §Legs:
customlayout/nav-smoke). **Operator verdict 2026-10-22: "It works
perfectly"** — legs (1) and (3) below done on the reworked editor, **on
hardware** (hardware-verified). Shipped as `0.20.0`. **Leg (2) done 2026-10-24** (operator, real DC +
GDEmu, `0.20.0`): B.O.S.S. on a single custom button with a full gauge
activates B.O.S.S. mode — senkosp accepts Main+Sub+Action arriving in the
same poll. All three legs closed.
**Operator legs:** (1)
emulator walkthrough — CUSTOM on both pad rows, d-pad cursor following the
page (RIGHT on L → R, LEFT from the right column → L, no wrap), A → amber
band, LEFT/RIGHT cycling, A keeps / B restores, B back, START; (2) in-game: B.O.S.S. on a face button with a full
gauge activates B.O.S.S. mode — also the first measurement that senkosp
accepts the simultaneous three-bit press (tester's claim — confirmed on hardware 2026-10-24, see above);
(3) the hardware round, standing Flycast≠hardware rule.

### Controls library (2026-10-24, branch `feat/controls-library`)

**HARDWARE VERIFICATION: PASS (operator, 2026-11-01).** The operator ran
the hardware round on a real Dreamcast + GDEmu serving the GDI master and
reported "work fine" (spec §Verification "Operator legs" (2): per-port
custom layouts in play, B.O.S.S., stick custom, hot-swap). Single-rig
evidence per the project's standing caveat; the CDI master was not run on
hardware this round (it builds and passes its region assert). Merged to
`main` and released as tag `0.21.0` (2026-11-01). Before that round: host
tests and one emulator boot smoke only — the Flycast fork cannot inject pad
input on macOS (Lua is off on Apple builds, `tooling.md` §RAWFB), so walking
the page was the operator's leg.

**Origin.** Operator review (2026-10-24) of the `0.20.0` CUSTOM (§Custom pad
layout above) against the tester's round-2 message (`CONTROLS_TASK.MD`
§Round 2). Four problems: CUSTOM always started from Tournament, sticks could
not be customized, nothing on screen said CUSTOM was editable, and each port
owned its one custom layout, so P1's could not be reused on P2. Design
brainstormed and approved in-session 2026-10-24; the operator picked the row
model, the fork moment, the delete placement and the cap from mockups. Spec
`docs/superpowers/specs/2026-10-24-controls-library-design.md`, plan
`docs/superpowers/plans/2026-10-24-controls-library.md`, ledger
`phase7-polishing.md` §T20. Unchanged: the three stock layouts, the B.O.S.S.
mask, the chip editor's controls, the DEVINFO pad/stick classifier, the
test-boot mapping and the reset combo.

**Library model** (`loader/ctl_lib.c/.h`, host test
`shims/test/test_ctl_lib.c`). There is one shared library per device class.
**Pad** has buttons A B X Y L R (`menu_def.PAD_BUTTONS`), **stick** has
A B X Y Z C (`STICK_BUTTONS`). Each class has its stock layouts (pad
TOURNAMENT, OLD; stick ARCADE), which are immutable, plus `CTL_N_CUSTOM` = 8
custom slots. Slot *i* is always named CUSTOM *i+1*. A layout is six
function ids in `FUNC_WORDS` order (unchanged). State is
`ctl_lib_t {custom[2][8][6], used[2][8], sel[2][2]}`, 116 bytes. `sel` below
`CTL_N_STOCK[cls]` is a stock id; above it, it means `CTL_N_STOCK[cls]` +
slot. A custom layout belongs to nobody: two rows that select CUSTOM 1 share
one object, so editing it from either row changes both (operator requirement
8, spec §2). The state is session-only unless saved to a VMU (Persistence,
below). The all-zero `.bss` instance is the
defaults (every pad row TOURNAMENT, every stick row ARCADE; KOS clears
`.bss`: `arch_main` memsets `_bss_start`, `tools/kos/kernel/arch/dreamcast/
kernel/init.c:299`). The in-game A+B+X+Y+Start warm boot reloads the loader
from disc (`shims/src/main.c` `pad_reboot`, §Warm boot to the menu) and KOS
clears `.bss` on entry (`init.c:299`), so every custom layout and selection
is back to defaults after it, unless a VMU save restores them (Persistence,
below). The arrays are serialized as-is into the save (spec §8). The game and
the shim write nothing to a VMU; the loader's menu is the one writer.

**Persistence (2026-11-01, branch `feat/vmu-persistence`; emulator-proven,
hardware round pending).** The record (`menu_game_record`, 16 bytes) and
`ctl_lib_t` (116 bytes) are saved as one 2-block file `SENKOSP_SYS` on a
memory card, with no save button; full record, status-line table and operator
checklist in `phase7-polishing.md` §T21.
- **Load:** once, at boot, from the first readable card with a valid file,
  scanning A1, A2, B1 … D2 (KOS `hardware/maple/maple_enum.c:35-50`, under
  `tools/kos/kernel/arch/dreamcast/`). A card inserted later is never loaded
  into the live state; the warm boot loads it.
- **Save:** when Controls or Settings is left with changes, and at START GAME
  if changes are still unsaved. Nothing is written when nothing changed.
- **Consent:** the loader writes silently only to the card this session
  loaded from or got an A on, checked at write time by slot and the root
  block's format timestamp. Any other card is asked first (REPLACE when it
  already holds a save), and B declines for the session. The top page's
  status line says what happened.

**Rows page.** There are four fixed rows, class-major: P1 PAD, P2 PAD,
P1 STICK, P2 STICK (`CTL_ROW_ITEMS`, generated from `CTL_PORTS` = 2 × the
class list in `scripts/menu_def.py`), at y 300/334/380/414 (`CTL_ROW_Y`, a
12 px gap between the groups). UP/DOWN moves the highlight. The art page
(HKT-7700 pad / HKT-7300 stick) is copied only on entry and when the
highlight crosses class (`loader/menu.c` `ctl_draw_all`), so it flips once,
between the groups. Every row is settable whatever is plugged in (a hot-swap
never changes what a row means). The page opens on P1 STICK if a stick drives
the menu (`stick_on_menu_pad()`, unchanged rule), otherwise on P1 PAD.

**Cycle, customize, fork, delete** (`loader/menu.c` controls loop over
`ctl_lib`):
- **LEFT/RIGHT** (`ctl_cycle`) steps through the stock ids, then the used
  slots in ascending order. Unused slots are skipped and the list wraps: pad
  TOURNAMENT, OLD, CUSTOM n…; stick ARCADE, CUSTOM n….
- **A on any row** opens the chip editor (`ctl_edit`) on the layout the row
  shows, pad or stick. The editor controls are the 2026-10-22 ones (§Custom
  pad layout): the d-pad walks `CTL_EDIT_NAV`, A opens value mode, LEFT/RIGHT
  cycle the seven functions, A keeps, B restores, and B outside value mode
  returns. The frame starts on `CTL_EDIT_FIRST` = {pad L, stick X}, the
  top-left chip on each page (X is MAIN in ARCADE).
- **Fork on first change** (`ctl_keep`). On a stock selection, the first kept
  value that differs from the stock one copies the stock layout into the
  lowest free slot, writes the change into the copy, and selects that slot on
  the highlighted row only (`CTL_KEEP_FORKED`). The row value flips to
  `< CUSTOM n >`. Keeping an unchanged value (`CTL_KEEP_SAME`), or B in value
  mode, forks nothing. Leaving without a kept change leaves the row on the
  stock layout. On a custom selection the edit is written in place
  (`CTL_KEEP_WRITTEN`).
- **Library full.** A on a stock row while all 8 slots of that class are used
  does not open the editor. The footer shows FULL until the next press, and
  that press is then processed normally. The check happens up front so a fork
  can never fail mid-edit. A on a custom row still opens the editor, because
  it edits in place.
- **Delete is X, twice, on a custom row only.** X on a stock row does
  nothing. The first X turns the row's value cell into a red `DELETE?` cell
  and the footer to CONFIRM. A second X runs `ctl_delete`: the slot is freed,
  and every port of that class selecting it falls back to stock 0
  (TOURNAMENT / ARCADE), with rows and labels redrawn. Any other button
  cancels, and that press is consumed (B does not also leave the page). A
  freed number is reused by the next fork (lowest free slot wins).

**Cap: 8 per class.** This was the operator's choice. The VMU is not the
limit: one 512-byte block holds over a hundred 3-byte layouts (spec §2). The
limits are the sprite sheet and the LEFT/RIGHT cycle length. The menu has no
runtime font, so every slot needs its own baked `< CUSTOM n >` chip (1–8,
shared by both classes).

**Shim: resolved words and a flag.** The shim no longer knows presets. The
loader stages these unconditionally (`loader/main.c`, staging block before
the GD stack canary):
- `SHIM_STATE[SHIM_STATE_LAYOUT_VALID]` ([2]) = 1;
- four words `SHIM_STATE_LAYOUT_WORD(cls, port)` = 3 + 2·cls + port: [3] pad
  A, [4] pad B, [5] stick A, [6] stick B (`shims/include/shim_iface.h`; slot
  pins in `shims/test/test_shim_iface.c`). Each is `ctl_pack`: six 4-bit
  ids, nibble *i* = the class's button *i*.

On every poll, `mie_poll` (`shims/src/main.c`) does the following for each
port:
1. It classifies the port with `jvs_pick_class(devinfo_caps[port])`
   (`shims/src/jvs.c`). The rule is the old one: no RTRIG/LTRIG/analog X/Y
   capability bit means stick. Measured caps words are `0xfe060f00` for a pad
   and `0xff070000` for a stick (§Three-layout controls).
2. It takes `jvs_layout_word(valid, staged, cls)`: the staged word only when
   `SHIM_STATE[SHIM_STATE_LAYOUT_VALID] == 1`, otherwise
   `JVS_WORD_DEFAULT[cls]` (Tournament / Arcade). A zero-filled window is
   therefore never read as a layout.
3. It maps the input through `dc_to_jvs_word(dc, cls, word)`, where the class
   picks the button-bit list (`JVS_CLASS_BUTTON`).

A test boot uses `dc_to_jvs_test(dc, cls, word, &test_bit)` on the same
resolved word. Because the class is chosen per poll, a pad↔stick hot-swap
moves that port between its pad word and its stick word. That is the
mechanism only; the hardware check is operator leg (2). Deleted:
`jvs_pick_layout`, `dc_to_jvs`, `dc_to_jvs_custom`, `dc_to_jvs_port`, the
preset tables (`JVS_LAYOUT_PAD[2]`, `JVS_LAYOUT_STICK`), `LAYOUT_PAD_*` and
`PAD_SEL_CUSTOM`. The rest of the poll path is untouched: active-low
normalization, trigger threshold, capability-gated axes, the `was_dead[]`
re-probe and the reset combo.

**Stock words** (generated into `shims/src/layouts.h` from `menu_def.py`;
ids 0 MAIN, 1 SUB, 2 BARRAGE, 3 ACTION, 4 OVERDRIVE, 5 B.O.S.S., 6 NONE;
nibble *i* = button *i*). They match the old tables button for button (the
§Three-layout table; host-pinned in `shims/test/test_host.c`):

| Word | Literal | A | B | X | Y | L / Z | R / C |
|---|---|---|---|---|---|---|---|
| `JVS_WORD_TOURNAMENT` (pad) | `0x343210` | MAIN | SUB | BARRAGE | ACTION | OVERDRIVE | ACTION |
| `JVS_WORD_OLD` (pad) | `0x432130` | MAIN | ACTION | SUB | BARRAGE | ACTION | OVERDRIVE |
| `JVS_WORD_ARCADE` (stick) | `0x421063` | ACTION | NONE | MAIN | SUB | BARRAGE | OVERDRIVE |

**Sprite sheet: 8bpp palettized.** `menu_sheet` now uses the logo's format
(`loader/menu_sheet.pal8`): a 512-byte RGB565-LE palette, then 640 ×
`SHEET_H` 8bpp indices. `blit()` in `loader/menu.c` is a palette lookup.
`SHEET_H` went from 1024 to 1280 (1220 px used, 197 colours at RGB565). The
blob is 819,712 bytes, against 1,310,720 for the RGB565 sheet at 1024.
Loader `1ST_READ.BIN`: 3,536,144 → **3,045,188 bytes**, against the
1728-sector loader limit of 3,538,944. The generator pipeline is in
`tooling.md` §T9 menu asset generator.

**Stick chips and the B leader.** The stick page's baked function tags are
gone. Its chips are now drawn at runtime like the pad page's (`STICK_ANCHORS`,
`scripts/menu_def.py`). They sit exactly where the 2026-10-03 tags sat
(anchor y = tag y − 12), so the leaders keep their straight routes:
- X (10,18) in the left column;
- Y (480,53), Z (480,83), C (480,111), B (480,136), A (480,161) in the right
  column at x480 (`SCOL_R`).

B is new. Stock ARCADE leaves it unmapped, so it never had an art coordinate.
Its art centre is (705,461) r50, measured on `stick_diagram.png` (outer ring
ink x655–756, y411–512). Its leader has one elbow, (476,148)→(377,148)→
(377,138): it runs under C and rises onto B's south rim
(`gen_menu_assets.STICK_PAGE`; the generator asserts every leader ends on its
button's circle). On ARCADE, B shows NONE. MOVE and START stay baked (they
carry no function). The cone-rule nav table now covers the stick anchors too
(`scripts/test_gen_menu_nav.py` `test_real_stick_page`).

**Footers.** The footer left the page bins: the bins' footer area is now
background. Six 640×24 sheet strips are blitted per state at y 452
(`CTL_FOOTER_Y`):

| State | Strip |
|---|---|
| ROWS_STOCK | `LEFT/RIGHT: LAYOUT   A: CUSTOMIZE   B: BACK` |
| ROWS_CUSTOM | `LEFT/RIGHT: LAYOUT   A: EDIT   X: DELETE   B: BACK` |
| EDIT | `D-PAD: BUTTON   A: CHANGE   B: DONE` |
| VALUE | `LEFT/RIGHT: FUNCTION   A: KEEP   B: UNDO` |
| CONFIRM | `X: DELETE   ANY OTHER BUTTON: CANCEL` |
| FULL | `ALL 8 CUSTOM SLOTS USED: DELETE ONE FIRST` |

The spec's rows footer started with `UP/DOWN: ROW`. With it, ROWS_STOCK
measured 644 px against the 624 px maximum at `F_ROW` (`check_fits`), so it
was dropped, which is the spec §7 rule's first step. The plan's ROWS_CUSTOM
never carried `UP/DOWN: ROW`, so neither rows strip advertises UP/DOWN now.
The other five strips are as the plan wrote them.

**Verification:** host tests (`make test`), an emulator boot smoke (leg
below), and the operator's hardware round — **PASS 2026-11-01** (real DC +
GDEmu, GDI master; see the status line at the top of this section).
- **Host tests:**
  - `shims/test/test_host.c`: all three stock words against the old literals
    for every button; the classifier from the measured caps words; stick
    nibbles A B X Y Z C, including Z → BARRAGE and C → OVERDRIVE on ARCADE;
    the staged-flag fallback; B.O.S.S., NONE, junk nibbles, OR of two
    buttons, and layout-blind Start / 8-way.
  - `shims/test/test_shim_iface.c`: slot pins 3/4/5/6.
  - `shims/test/test_ctl_lib.c`: defaults; the cycle with a hole and wrap; a
    same-value keep; fork to the lowest free slot on the highlighted port
    only; the shared object; delete fallback; freed-number reuse; class
    independence; eight forks, then FULL refusal while a custom row still
    edits.
  - `scripts/test_gen_menu_nav.py` (stick anchors) and
    `scripts/test_gen_menu_sheet.py` (blob ↔ png).
- **Previews viewed** (by the Task 3 reviewer): all nine `build/preview_*.png`,
  including the DELETE? and FULL states.
- **Emulator boot smoke `captures/ctl-library/boot-smoke1`** (FAKESTART build;
  `tooling.md` §Legs: ctl-library):
  - The pre-game top menu renders from the pal8 sheet: RAWFB dump
    `shot-boot-smoke1-004-t20s.png`, viewed, pixel-identical (0 differing
    pixels) to the RGB565-sheet menu frames of `customlayout/boot-smoke3` and
    `nav-smoke2`. The t=15 s dump caught the loader splash instead (dump
    timing; see the leg record).
  - The fake START launches the game. Over 160 s: 0 `SHIMERR`,
    0 `System reset`, 18,528 `TAEND`, 1,374 `GDDMA`.
  - What this covers: the flag-1 staging and the shim's per-poll word read on
    the default path (all-zero library, so Tournament / Arcade words). It does
    **not** cover the controls page.
- **Operator legs** (the claim gate, spec §Verification):
  1. emulator walkthrough of the four rows, the art flip, the cycle order,
     fork, sharing, delete and the FULL footer, on pad and stick rows,
     including B;
  2. hardware (real DC + GDEmu, pad in one port, stick in the other): per-port
     custom layouts in game, B.O.S.S., a stick custom with Z/C remapped,
     hot-swap, CDI and GDI.

### Non-standard controllers: axis bytes are capability-gated (2026-09-26)

Tester report (Flycast, "Arcade Stick" driver): shield + OverDrive stuck
held from boot. Root cause: the GetCondition reply always carries all six
analog bytes, but a device without an axis fills its byte with a **neutral
filler of the sender's choosing** — Flycast's Ascii Stick returns `0x80`
for every axis (`maple_devs.cpp:313 getAnalogAxis`) while declaring **zero
analog axes** in its DEVINFO word (`0xff070000`, `maple_devs.cpp:292`), and
the shim's threshold-128 trigger digitizer read that filler as both
triggers half-pressed, forever (`IN p1=00000060` at first poll, leg
`dcstick-prefix-repro3`). Fix: `maple.c probe_devinfo()` latches each
port's DEVINFO function-data word (`devinfo_caps[]`; reply word 2 =
`function_data[0]`, KOS `dc/maple.h maple_devinfo_t`), and
`jvs.c dc_cond_to_pressed()` only trusts an axis byte whose capability bit
is declared — rtrig bit 8, ltrig bit 9, analog X/Y bits 10/11 (KOS
`dc/maple/controller.h:258-263 CONT_CAPABILITY_*`; standard pad
`0xfe060f00` has all four). Undeclared axis ⇒ bit never synthesized,
whatever the filler value — real HKT-7300 filler bytes are undocumented,
so the gate is on the declaration, not the value. Buttons (incl. the
stick-only C/Z, unmapped) are unaffected. Verified: host tests
(`test_host.c` Arcade Stick block) + emulator A/B legs
`dcstick-prefix-repro3` (pre-fix, `p1=00000060` held) /
`dcstick-fix-verify` (fixed, `p1=00000000` idle, crc `0x22` = the
phase-4 idle baseline) / `dcstick-pad-regress` (standard pad, idle
unchanged), all `input:device1=4|0`, tooling.md §Leg records.

### Pad reset combo — A+B+X+Y+Start reboots (2026-10-05, branch `feat/pad-reset-combo`)

Tester request (GDEmu users): the retail DC soft-reset combo. Holding
A+B+X+Y+Start on either port cold-boots the console the same way KOS
`arch_reboot` does: mask IRQs, then call the BIOS reset vector at P2
`0xa0000000` (`tools/kos/kernel/arch/dreamcast/kernel/init.c:438-449`; combo
= `CONT_RESET_BUTTONS`, `dc/maple/controller.h:127`). We can't use
`arch_menu` (the BIOS-menu syscall) because every BIOS syscall is dead after
handoff (the Naomi kernel slice sits on the BIOS's low RAM, `shims/src/gd.c`
header). There's no return to the game's own title screen: the Naomi
original has no such path. Code: `dc_reset_combo()` in `shims/src/jvs.c`
(host-tested), acted on in `mie_poll` (`shims/src/main.c`). It's live in
every mode, test menu included. **Hardware-verified 2026-10-05** (operator,
real DC + GDEmu). The combo mid-game reboots cleanly to the BIOS swirl
animation. GDEmu then treats it as a normal boot and loads its first image,
so the player lands back in **GDMenu**. It works from both port A and
port B.

**Loader menu (2026-10-07):** the combo is live in the pre-game menu too
(`loader/menu.c` `edge()`): held on either of the first two enumerated pads
→ KOS `arch_reboot()`, the same reset-vector jump. Checked on the held
mask, not the edge, because five buttons rarely land in one 60 Hz frame.
START therefore starts the game on *release*: a START that lands a frame
before A+B+X+Y would otherwise launch the game instead of rebooting.
Before this the menu simply never looked at the combo — it polls the pad
itself, and this KOS installs no default combo handler
(`cont_btn_callback` has no caller under `tools/kos/kernel`). Emulator
evidence (the fork can't inject pad input — tooling.md §RAWFB): leg
`captures/menu-reset/rt1`, a throwaway build that OR-ed the combo into
`cur` once `timer_ms_gettime64()` passed 8 s, RAWFB dumps every 2 s for
70 s — four cycles of menu → ~8 s black (BIOS boot; the swirl's TA frames
don't land in the FB-only dump) → Naomi splash → menu, i.e. `arch_reboot`
from the menu re-boots the disc into the loader. Throwaway reverted same
session; the clean rebuild is byte-identical to the pre-diag loader
(`1ST_READ.BIN` md5 `f5b48e17…`). **Hardware-verified 2026-10-10**
(operator, real DC + GDEmu: "yes it works"; protocol asked: combo in the
menu → reboot, plain START → game, START-then-A+B+X+Y → reboot, not
start).

#### Why the in-game combo reboots instead of returning to the pre-game menu

The obvious ask — in-game combo → our menu, menu combo → console reset —
is half a tweak and half a feature. After handoff there is nothing to
return to:

- **The loader is gone.** KOS links it at `0x8c010000` (~838 KB), which is
  exactly where the shim window, the 0x60000 blob and the game image land;
  the handoff stub copies them over it (`loader/main.c` §staging layout,
  `loader/handoff.S` header). Menu code, assets and the KOS runtime no
  longer exist in RAM once the game runs.
- **The BIOS is gone too.** The Naomi kernel slice sits on
  `0x8c000600-0x8c003800`, the BIOS's own syscall RAM (`shims/src/gd.c`
  header; `pad_reboot` comment, `shims/src/main.c`), so neither `arch_menu`
  nor any GD syscall can re-launch anything. Only the reset vector
  survives, and that is a full cold boot.
- **Cheap middle ground — holds everywhere except GDEmu.** The reboot comes
  back through the BIOS into our loader and menu on the emulator (leg
  above) and, by the ordinary disc-boot path, on a real GD-R / CD-R (not
  hardware-tested for this port). On GDEmu it never does — **operator
  hardware test 2026-10-10:** GDEMU.ini `reset_goto = 1` → GDMenu,
  `reset_goto = 0` → the DC BIOS menu (i.e. no bootable disc presented
  after the reset; GDEmu does not re-boot the running image either way).
  So for GDEmu users the in-game combo means "back to the launcher", and
  our menu is one image boot away. This is what tag `0.17.1` ships.

The 2026-10-10 pricing above assumed the loader had to be rebuilt from
disc AND KOS had to boot without a BIOS (opt out of `INIT_CDROM`, raw-ATA
cart read, isoldr fingerprinting) — "a few sessions plus two or three
hardware rounds". The branch below found the BIOS half avoidable.

#### Warm boot to the menu — branch `soft-reset-menu` (2026-10-10, emulator-proven)

The in-game combo now re-enters the loader instead of the reset vector,
so the combo lands in the pre-game menu, where the same combo reboots the
console (the retail two-stage soft reset). Two facts make it cheap:

- **The DC BIOS's syscall RAM can be snapshotted, not rebuilt.** Everything
  KOS needs from the BIOS at boot lives in `[0x8c000000, 0x8c010000)` (GD
  syscalls, sysinfo, font vector) — the ROM is never touched by the game,
  only this RAM copy is (kernel slice at `KERNEL_DST`, game stack under
  `0x8c00f000`, `docs/kb/boot-binary.md` row 7). The loader copies the
  64 KB into `BIOSRAM_SNAP = 0x8cfe0000` as its last act before the handoff
  purges (`loader/main.c`, after the record build — last so its own KOS
  stack, top of RAM downward, cannot have scribbled it). The region is a
  heap-top carve: the Phase 7 T1 isoldr carve, now **unconditional and one
  byte deeper** (`scripts/build_patch_table.py` HEAP-CARVE: `add #-2` →
  top `0x8cfe0000`; `[0x8cff0000, 0x8d000000)` stays isoldr's). Heap slack
  after both carves ≈ 280 KB of the measured ~410 KB
  (`docs/kb/relocation-map.md` §Arithmetic check); a carved raw-ATA boot
  was already shown clean by the FORCE_CARVE leg
  (`docs/kb/phase7-polishing.md` forcecarve-attract).
- **The game is dead at the combo, so all 14 MB of its RAM is scratch.** The
  loader image is **3.5 MB** with the menu (the "~838 KB" above is the
  MENU=0 figure; `_edata` `0x8c36f384`), far over the heap slack, so it
  cannot be stashed — but it can be read back from disc into dead-game RAM
  at `WARM_IMG = 0x8c800000`: the shim's own dual-backend `gd_read`
  (`shims/src/gd.c`, raw ATA or isoldr syscall) reads the GDI's plain
  `1ST_READ.BIN` at `LOADER_FAD = 450150` (`make_gdi.py` BOOT_LBA + 150),
  the whole 1728-sector donor boot region, in 512 KB chunks. On the CDI
  the same read targets `LOADER_FAD = 13644`, a plain copy `make_cdi.py`
  writes right before the cart (see §CDI below).

Placement reuses `loader/handoff.S` unchanged — the PIC copy-record walker
is linked into the shim too (`shims/Makefile`), relocated to `WARM_STUB`
and run through P2: record 1 restores the snapshot over the syscall RAM,
record 2 places the image at `SHIM_BASE` (= KOS `_start`, over the shim
itself), then the stub's CCR write invalidates both caches and jumps to
`0x8c010000`. Before the jump the shim mirrors the loader's own handoff
block: IRQs masked (SR.IMASK=15), `MMUCR = 0` (the game runs AT=1), TA
reset, interrupt latches cleared (`shims/src/main.c` `pad_reboot`). Hooks
never nest, so no GD or maple DMA is in flight when `mie_poll` sees the
combo. A failed disc read falls back to the old cold reboot. KOS then
boots exactly as from the BIOS: `startup.s` sets its own SR/stack,
`arch_main` clears `.bss` (`tools/kos/kernel/arch/dreamcast/kernel/
init.c:299`), `cdrom_init` re-inits the restored GD syscalls.

**Sound is silenced FIRST, before the disc read.** The first hardware
build held the AICA ARM only after the read, and the operator heard the
music stutter for the ~0.5 s the 3.5 MB read takes (the AICA kept looping
its stale buffers with nobody feeding it). The fix is KOS's own
`spu_disable` + `spu_reset_chans` sequence, in their order
(`tools/kos/kernel/arch/dreamcast/hardware/spu.c:253-300`): master volume
`0x2800 &= ~0xf`, ARM held (`0x2c00 |= 1`), every channel keyed off
(`0x8000` = KYONEX with KYONB clear, 64 channels), each G2 write preceded
by a FIFO wait on `0xa05f688c` AICA|G2 (`g2bus.c:162-166`, `dc/fifo.h`).
Safe by construction: KOS `spu_init` leaves the master volume at 0 on
every boot (`spu.c:357`) and the game restores it itself, so the warm boot
hands the game the same silent AICA a BIOS boot does. Emulator regression
of the reorder: leg `wb6` (menu on, `FAKECOMBO=1800 FAKESTART=6000`,
165 s) — three game → menu → game cycles, 3,556 frames each, `SHIMERR` 0,
post-warm-boot menu dumps md5-identical to the first boot (`wb5` was the
host-side dynarec VMEM `Verify Failed` launch flake, entry1's twin; kept).

**Emulator evidence (Flycast fork, `captures/softreset/`, 2026-10-10):**
the fork cannot inject the combo, and its `FLYCAST_START_AT` hook advances
only on TA-rendered frames (`core/ui/mainui.cpp:65` passes
`MainFrameCount`), so it never fires on the FB-only menu — leg `wb3`
stalled there. Both legs below used throwaway knobs, reverted before the
clean rebuild: shim `SHIM_FAKE_COMBO=1800` (combo after 1800 polls ≈ 30 s
in-game) and loader `LOADER_FAKE_START=6000` (START 6 s into the menu).
- `wb2` (`MENU=0`, 170 s): five `WARMBOOT` → KOS banner → `GD init OK` →
  `cart read OK (KOS)` + `(raw ATA)` → `patches OK` → `heap carved` →
  `HANDOFF -> game` cycles; cartlog `TAEND` **3,556 frames in every
  warm-boot segment** (deterministic), `SHIMERR` 0, `System reset` 0; the
  `MMUCRWR` trail per cycle is shim `pc=8c0100c4` (warm boot) → loader
  (handoff) → game `val=00040005` (AT on). RAWFB dumps right after each
  warm boot show the NAOMI splash + boot-gap spinner.
- `wb4` (menu on, 165 s): menu → START → game → combo → **menu** three
  times; the menu dumps after every warm boot (t=60/105/150 s) are
  md5-identical to the first-boot menu dump; 3,556 frames per segment,
  `SHIMERR` 0.
- `wb1` crashed at launch on the known Vulkan flake (`pvr.rend=0`,
  `docs/kb/tooling.md` §RAWFB); kept per the never-delete-a-leg rule.

**Hardware (operator, 2026-10-10, real DC + GDEmu): PASS, two rounds.**
Round 1: "yes it works on hardware, combo goes to the menu"; one finding,
the music stutter above. Round 2, silence-first build (c6e79bf): "music
cuts clean now, works on hardware".

**CDI — branch `soft-reset-cdi` (2026-10-10, emulator-proven).** The
CDI's FS copy of `1ST_READ.BIN` is scrambled (the CD boot ROM descrambles
it; `tooling.md` §CDI mastering), useless to the shim, so through tag
0.18.0 the CDI compiled the `#ifdef LOADER_FAD` path out and kept the
cold reboot. Fix: `make_cdi.py` writes a **plain** copy of the loader,
zero-padded to `LOADER_SECS` (1728 sectors), between the FS region and
the cart, and the cart moves 1728 sectors up: `shim_iface.h` gets an
`#elif CART_FAD == 15372` arm defining `LOADER_FAD 13644`
(= 150 + 11702 + 1792), Makefile `CD_CART_FAD` 13644 → 15372. No shim or
loader code change — the warm boot is the same `gd_read` of the same
region length at a different FAD. The copy goes BEFORE the cart rather
than after it (where the optional LZ4 blob lives, its presence varying
per build) so the FAD stays a compile-time constant; descrambling in the
shim was priced and rejected (the permutation + a 256 KB index table +
an ISO directory parse for the exact file size that seeds its LFSR,
`tools/kos/utils/scramble/scramble.c`, vs. three lines of mastering and
3.4 MB on a 700 MB disc). Evidence, leg `softreset/cdi-wb2` (170 s,
`FAKECOMBO=1800 FAKESTART=6000`, `make cdi SERIAL=1`,
`capture_rawfb_leg.sh … build/cdi/disc.cdi 12`): BIOS → scrambled
loader → menu → START → game → combo → `WARMBOOT` → plain-copy read at
FAD `0x354c` → loader (`heap carved`, `MENUEE`) → menu → … **three
game → menu → game cycles**, four `heap carved`, three `WARMBOOT`,
cartlog MMUCRWR ladder per cycle `8c0108d2` (loader) → `8c02d630` (game)
→ `8c0100fc` (shim, warm boot), 14,816 TAEND frames over four game runs
(~3,700 each, in line with the GDI's 3,556), `SHIMERR` 0, `System reset`
0. Menu RAWFB frame md5 `2610066e…` identical at t=18 s (cold) and
t=63/108/153 s (after each warm boot); NAOMI splash frame identical
cold vs warm. **Hardware (operator, 2026-10-11, real DC + GDEmu serving
the clean `make cdi` image, md5 `d82112f0…`): PASS** — "works on
hardware, combo goes to the menu on the CDI too". Not yet run from a
burned CD-R (per the standing CDI lesson a GDEmu pass ≠ burned-disc
pass); expectation there: the drive reads the 3.5 MB plain copy at
~1.8 MB/s (12× CAV peak), so the combo's black gap is ~2 s vs. GDEmu's
~0.5 s.

**Open (not a blocker):** DreamShell / isoldr: untested — the syscall
backend path is the same `gd_read` dispatch, and isoldr's resident
driver at `0x8cff0000` is outside both destinations.
The `FORCE_CARVE` knob is retired (`docs/kb/tooling.md` §Phase 7 build
knobs); the two leg knobs `FAKECOMBO`/`FAKESTART` are recorded there.

## OverDrive wire

Capture-time binding: D → `DC_BTN_Z` ("Button 6" per Flycast's own
binding-UI table — `DC_BTN_C`/`DC_BTN_Y`/`DC_BTN_Z` = "Button 3"/"Button
5"/"Button 6", `../flycast4naomi2dreamcast/core/ui/settings_controls.cpp:259,261,262`).
Three independent sources agree on this, not just one:

1. User's in-session report: they remapped D "from button 5 (no marks) to
   buttons 6 (It is marked in the emulator as Overdrive)" and tested it
   in-game, before the capture.
2. Live cfg, re-read by the controller after the capture:
   `bind3 = 7:btn_z` (`SDL_Keyboard_arcade.cfg`) — D (scancode 7) →
   `btn_z` → `DC_BTN_Z`. Not post-capture drift: this is the same state the
   user's remap produced, corroborated by (1) and (3).
3. Per-game DB label: `DC_BTN_Z` → `naomi_button_mapping[8]`
   (`maple_jvs.cpp:50`, verified: `NAOMI_BTN5_KEY, // DC_BTN_Z`) →
   `NAOMI_BTN5_KEY`, and senkosp's own descriptor names that slot
   "OVER DRIVE" (`naomi_roms_input.h:475`) — exactly the label Flycast's
   per-game control screen would show for that row, matching what the user
   reported seeing.

The round-1 fix's stage-A snapshot (`SDL_Keyboard_arcade.cfg:14`,
`bind2 = 7:btn_y`, D → `DC_BTN_Y`, "Button 5") predates the user's remap —
it was read before they touched the bindings — so it isn't in conflict with
the above, it's simply superseded for capture-time purposes.

Actual path for the measured `0x0020`: `DC_BTN_Z` →
`naomi_button_mapping[8]` (`maple_jvs.cpp:50`) → `NAOMI_BTN5_KEY` →
senkosp's own descriptor remap (`{ NAOMI_BTN5_KEY, "OVER DRIVE",
NAOMI_BTN4_KEY }`, `naomi_roms_input.h:475`, applied in
`jvs_io_board::init_mappings()` / `read_digital_in()`,
`maple_jvs.cpp:343-369` / `231-270`) → final wire `NAOMI_BTN4_KEY`
(`0x0020`).

Why the bit alone could never settle this: `DC_BTN_Y`'s own path
(`naomi_button_mapping[9]`, `maple_jvs.cpp:51`) reaches `NAOMI_BTN4_KEY`
natively too, with no remap — so `0x0020` is consistent with D being bound
to either `DC_BTN_Z` (remapped) or `DC_BTN_Y` (native). The measured bit
can't discriminate between the two paths by itself; the user's testimony,
the live cfg, and the per-game label all point to `DC_BTN_Z`, and all three
agree with each other, which is what settles it.

## Why no MIE sub=15 byte.bit

`MIERESP sub=15` (`maple_if.cpp:289-296`) only prints when the SH4 issues a
maple `MDC_JVSCommand` (`0x86`) DMA with sub-command `0x15`. In
`input.log`: 826 occurrences total, matching 826 `MAPLEPC cmd=86 sub=15`
entries one-for-one, clustering in two narrow windows (log lines
1,463–13,783 at boot/attract-entry, and 109,080–119,099 at and after the
Test-menu re-handshake) with **zero** occurring in lines 72,308–102,689 —
the entire span covering all ten button holds measured in that leg. In
`service-retest.log`: same shape — 376 occurrences, all within lines
1,463–13,783 (the fresh boot handshake after relaunch), **zero** across the
four Service press windows (lines 91,442–102,950). `JVSREPORT`
(`maple_jvs.cpp:2241`), by contrast, is unconditional inside the
digital-read handler and fires throughout both legs (4,149 and 4,469 lines
respectively), which is why it — not the raw MIE dump — is the only usable
signal here. Confirmed by direct line-range counts against both capture
files (1-indexed, matching `grep -n`), not inferred.

## Service retest

`captures/service-retest.log`: 4 presses, ~1 s holds, attract screen only,
no other inputs. All 4 are clean single-bit holds:

| Press | Word transition |
|---|---|
| 1 | `0000→4000→0000` (log lines 91,442 / 92,674) |
| 2 | `0000→4000→0000` (log lines 94,242 / 96,062) |
| 3 | `0000→4000→0000` (log lines 97,742 / 99,478) |
| 4 | `0000→4000→0000` (log lines 101,046 / 102,950) |

`0x4000` = `NAOMI_SERVICE_KEY` (`maple_devs.h:78`) exactly — confirms
verdict (a): Service reads normally on the attract screen. The zero-bit
result in the original `input.log` leg (Service pressed *inside* the
Test-menu) was specific to that context, not a broken binding — most likely
the Test-menu UI reads Service through a path that bypasses this
digital-read handler while test mode is active, consistent with `input.log`
showing zero `MIERESP`/no word change for the entire post-Test window
(still true, see "Why no MIE sub=15 byte.bit" above) even though the
control itself is confirmed good here.

## Coin / Test

Both are outside the 16-bit mask the digital-read handler logs
(`cartlog("JVSREPORT buttons=%04x\n", inputs[0] & 0xffff)`,
`maple_jvs.cpp:2241`) — architectural, not something a re-run or retest
fixes:

- **Coin**: `NAOMI_COIN_KEY = 1 << 19` (`maple_devs.h:98`), source-derived
  from the frozen fork, not measured. Reported via a separate JVS coin-count
  command (`0x21`) that isn't cartlog'd at all. Behavioral confirmation: a
  credit was added on press (operator-observed at the controls; matches the
  task brief's design note that Coin issues a credit and gates Start).
- **Test**: `NAOMI_TEST_KEY = 1 << 18` (`maple_devs.h:97`), source-derived
  from the frozen fork, not measured — reported via a status/tilt byte
  (`maple_jvs.cpp:2242`), also not separately logged. Behavioral
  confirmation: the test menu opened on press (operator-observed),
  independently corroborated by a full JVS bus re-handshake logged right
  after the press (ID-string re-request etc., `input.log` lines
  109,080–109,184, structurally identical to the boot-time handshake at
  lines 1,463–1,567) — proof the input reached the system and changed game
  mode, even without a byte.bit or word-bit value to show for it.

## Sanity

11 of 13 rows (Up, Down, Left, Right, M, S, A, Barrage, OverDrive, Start,
Service) are **measured**: exactly one changed bit vs. the `0000` baseline
in the JVS-word transition list (`bits-vs-baseline: 1` per hold — 10 in
`input.log`, in the exact press order specified, plus Service confirmed
separately via 4 clean holds in `service-retest.log`), each matching a
distinct `NAOMI_KEYS` constant (`maple_devs.h:75-99`). Coin and Test are
**not measured** — both are architecturally outside the 16-bit logged word
(bits 19 and 18) — and are documented as **source-derived** constants (cited
above) plus **behavioral** confirmations (credit added; test menu opened),
not measured values.

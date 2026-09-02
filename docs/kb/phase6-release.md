# Phase 6 — safety tripwires & release

Charter: three tripwires green on the release candidate (`make test` static
maple scan, `make test-vmu` unattended canary, `make test-vmu-play` operator
session — all PASS, see `docs/kb/tooling.md`), plus the two coverage legs
(#31 composite, #32 DreamShell serial-SD), then release packaging.

## Composite fix (Task 31, MONITOR-SENSE-HOOK, 2026-09-03)

**Symptom (operator hardware leg, composite cable):** after the loader splash,
black screen — but music plays and the game responds to input (START moves it
into player-select audio). Exactly the Cleopatra composite/RGB class predicted
in the task flag: the game drives 31 kHz timing on every cable, a 15 kHz TV
never syncs. The loader splash being visible proves KOS's cable-aware init is
fine; it's the game's own from-scratch mode-set (`pc=8c032140`) that kills it.

### RE chain (Ghidra, tools/ghidra-proj boot.bin analysis)

- `FUN_8c032140` — SDK PVR reg-poke helper (known since phase 5).
- `FUN_8c03d48e` — the SDK's public display-mode entry (KAMUI2 wrapper),
  **one caller in the whole image**: game-side `FUN_8c06ed98` via the single
  fn-ptr pool word at `0x8c06edcc` (whole-.dat u32 scan: exactly 1 hit).
- Mode word semantics (decompile + pool constants `8c03d59c–8c03d5b4`):
  bits1:0 = monitor class (0 = 15 kHz, 1 = 31 kHz VGA, 2 = PAL);
  **bit31 = auto** — wrapper queries the monitor sense `FUN_8c02a0ea` and
  rewrites the class itself (sense 0 → class 1, 1 → class 0, 2 → class 2);
  **bit30 = PAL request** (its branch demands sense==2 or `return -1` —
  NOT a "force" bit, see failed attempt below). With bit31 and bit30 both
  clear, the requested class is *validated* against the sense (mismatch →
  `return -1`).
- The game's one call passes **`mode = 0x80000038`** (auto; measured via a
  SERIAL=1 shim print, `captures/phase6/comp-dbg.stdout.log`): the game
  never chooses a frequency — the SDK's sense does.
- `FUN_8c02a0ea` (sense): `if (*0x8c170d7c != 1) return -1; return
  *0x8c170d88;` — a cached monitor code in the KAMUI2 config block, only
  ever populated from Naomi BIOS/DIP state. Post-BIOS-bypass it reads 0
  (31 kHz) on every cable. Shipped .dat defaults: flag 0, code -1.
- Class dispatch (`FUN_8c033c00`, jump tables at `8c033c88`/`8c033c9c`):
  under the Naomi device word `0x00010000` (state `0x8c19e4bc`), class 0 →
  `FUN_8c039260` — the SDK's own native 15 kHz builder. The library ships
  full 15 kHz support (Naomi cabinets run 15 kHz via DIP1); it just never
  gets selected on DC.

### Failed attempt (recorded because measured)

First hook repointed the *call-site* pool word (`0x4edcc`) and transformed
`mode -> (mode & ~0x80000003) | 0x40000000` ("force class 0"). Result
(`captures/phase6/comp-leg.*`, Cable=3): display blanked at takeover, **no
SPG program at all**, game alive underneath (155k cart-log lines, TA
geometry flowing) — the wrapper returned `-1`. The decompile's bit30 branch
falls into `if (sense != 2) return -1`: bit30 is a PAL *request*, not a
validation bypass. Lesson: with an auto-mode game, hook the **sense**, not
the mode word — then every SDK path (auto and validation alike) agrees with
the real cable.

### The fix

`shim_monitor_sense()` (shims/src/util.c): return 0 (31 kHz) on VGA cable,
1 (15 kHz) otherwise, via the existing `shim_cable_is_vga()` PDTRA read.
Patch: MONITOR-SENSE-HOOK repoints the sense's single fn-ptr pool word per
image (main dat `0x1d5a8` = the wrapper's pool; test dat `0x18f020` — the
SDK core links at the same addresses in both images, twin verified by byte
search). The game's own `0x80000038` then resolves to `0x38` = class 0 and
the SDK builds its native 15 kHz mode itself. No mode-word surgery, no
validation conflicts.

**SPG_CONTROL note:** the game's mode-set never writes SPG_CONTROL; the
interlace/NTSC bits (`0x150`) come from our KOS loader's cable-aware boot
init and persist (census: exactly one SPG_CONTROL write per composite leg,
`pc=8c00b87c` = KOS). The shipped fix is the composition: KOS control bits
+ hooked game timing, both present in every boot path we ship.

### Evidence (all Flycast fork legs, `captures/phase6/`)

| Leg | Cable | Verdict |
|---|---|---|
| `comp-leg.*` | 3 | pre-fix control: blank forever, game alive (the failed call-site hook) |
| `comp-dbg.*` | 3 | SERIAL=1: `VIDINIT m=80000038 -> 40000038 ... ret=ffffffff` — the -1 measurement |
| `comp-dbg2.*` | 3 | SERIAL=1 + sense hook: `SENSE ->1`; game programs full 15 kHz set — `SPG_LOAD=02180353`, `FB_R_CTRL=00000004/5` (**vclk_div=0**), `FB_R_SIZE=1413b53f` (modulus-321 interlace — byte-equal to Cleopatra's measured real-NTSC mode), blank→set→unblank normal |
| `rel-comp3.*` | 3 | release build: same 15 kHz set, attract renders — screenshot `docs/kb/img/phase6-composite-attract.png` |
| `rel-vga0.*` | 0 | release build: game mode-set census **byte-identical** to the pre-hook 31 kHz baseline (`SPG_LOAD=02110353`, `FB_R_CTRL=00800004/5` vclk_div=1, all 13 write rows match) |

**Real-target status:** emulator-verified; awaiting the operator's composite
re-test on hardware (the actual Task 31 gate — a TV's sync tolerance is the
thing Flycast cannot prove).

## Composite round 2 — TV centering (VIDEO-GEOM-HOOK, 2026-09-03)

**Operator verdict on the sense hook:** composite now syncs and the game is
visible — but shifted ~10% down, FREE PLAY cut off
(`docs/kb/img/phase6-composite-shift.jpeg`). Cause: the SDK's class-0
builder programs *arcade-monitor* geometry — 536-line frame
(`SPG_LOAD=02180353`), active start line 0x17 — while the KOS splash on the
same boot/TV displays centered with the DC-native NTSC-IL set (525 lines,
start 0x12).

**Fix:** VIDEO-GEOM-HOOK wraps the game's one display-init call (the
call-site pool word from the round-1 RE: main dat `0x4edcc`, test dat
`0x1aa9c0`) — mode word passes through untouched (bit30 lesson) — and after
the SDK's mode-set returns, on non-VGA cables only, rewrites the six
geometry regs to KOS's measured values: SPG_HBLANK `007e0345`, SPG_LOAD
`020c0359`, SPG_VBLANK `00240204`, SPG_WIDTH `07d6c63f`, VO_STARTX `a4`,
VO_STARTY `00120012` (offsets per Flycast `core/hw/pvr/pvr_regs.h`; values
from KOS's own `pc=8c00b87c` boot writes in the same legs). FB layout,
interlace fields, vclk stay the SDK's.

**Evidence (`captures/phase6/geo-comp3.*`, `geo-vga0.*`):** fixup lands 2 ms
after the SDK's writes (six-write block `pr=8c010a2e`), end-state = KOS
geometry; game activity profile byte-comparable to the pre-fix leg through
the full 90 s (TAREG/TAEND/C2D rates identical; the "SOFWR stops" scare is
the fork's 2000-record SOFWR logging cap, present in both legs) — so the
525-line frame does NOT starve the game's vblank interrupt; attract
screenshot normal; VGA census still byte-identical to baseline.

**Real-target status:** awaiting operator composite re-test (centering is an
analog scan-position property Flycast cannot show).

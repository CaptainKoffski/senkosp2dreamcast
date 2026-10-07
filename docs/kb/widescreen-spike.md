# Widescreen (16:9 anamorphic) spike — PARKED

**Status: PARKED (2026-10-07, operator emulator leg `ws-probe2`).** The
rendering half works with a 3-word RAM poke; the game's own playfield
rule (the 4:3 screen edge *is* the arena boundary) shows up as an
invisible wall in the newly revealed area. Making the field wider is a
gameplay change, not a port fix. Not shipped. The probe file stays at
`captures/ws-probe/ws.cht` (gitignored, throwaway).

## 1. Prior art — what Dolphin Blue's "widescreen" actually is

`deploy/dolphinblue/widescreen/track04.iso` differs from the base
track04 by **12 bytes at 4 sites** (`cmp -l`, 2026-10-07): four
literal-pool pointers `0x8c3f218c → 0x8c01ac18`, i.e. the code's
reference to one float constant redirected to another. The output stays
640×480; the player sets the TV to 16:9. This is the same mechanism as
Flycast's built-in `naomi_widescreen_cheats[]` table
(`core/cheats.cpp:320-367`, Dolphin Blue row at `:323`), which pokes
RAM floats at VBlank. Dolphin Blue's 3D stages are world-space scrolling
levels with no screen-bound playfield, so the hack has nothing to
collide with.

## 2. The senkosp lever — Ninja2's screen struct

senkosp links **Ninja2 2.01.011** (`game.md` §SDK stack). Its screen
struct lives at **`0x8c1a1c48`** (.bss, RAM offset `0x1a1c48`); layout
read from `tools/ram-snapshot.bin` and the two writer functions
(Ghidra `senkosp3`, `FindRefsTo`/`DisasmRange`, 2026-10-07):

| off | value (snapshot) | meaning |
|---|---|---|
| +0x00 | 381.4189 | X scale = dist × ax |
| +0x04 | −381.4189 | Y scale = −dist × ay |
| +0x08 / +0x0c | 320, 240 | cx, cy |
| +0x10 / +0x14 | 1/X, 1/Y | reciprocals |
| +0x18 | 381.4189 | dist (raw) |
| +0x1c / +0x20 / +0x24 | 1.0, 1.0, 1.0 | **ax, ay, az** |
| +0x28 / +0x2c | 640, 480 | w, h |
| +0x30 / +0x34 | 60000, 1.0 | far, near |
| +0x38..+0x44 | 319, −320, 239, −240 | clip bounds |
| +0x48..+0x54 | 0, 0, 639, 479 | viewport |

- **Setter `FUN_8c051878` = njSetPerspective(angle)** (`0x8c051878..d3`):
  `dist = w / (2·tan(angle/2))` → +0x18; `+0x00 = dist·ax`;
  `+0x04 = −dist·ay`; `+0x10 = 1/+0x00`; `+0x14 = 1/+0x04`. 381.4189 ⇒
  angle = 80° horizontal. 16 call sites in game code (Decomp callers
  list), so the game re-sets perspective per scene/camera.
- **Init `FUN_8c03d810`** (← `FUN_8c03d472` ← `FUN_8c086258`, system
  init) writes ax=ay=az=1.0 via `fldi1` and the default dist.
- All ~17 Ninja2 transform/projection readers load +0x00 for X and
  +0x04 for Y into separate registers (e.g. `FUN_8c051180` at
  `0x8c0511a4-aa`: fr8..fr11 ← +0x00,+0x04,+0x08,+0x0c). No game-code
  function (≥ `0x8c060000`) reads the struct directly — only library
  code does.

**Anamorphic 16:9 = ax 0.75.** Every later njSetPerspective call then
yields X = 0.75·dist by itself; +0x00/+0x10 need one rewrite for the
value set before the poke. Emulator-verified 2026-10-07 (`ws-probe2`,
operator): 3D geometry renders correctly proportioned under a 133 %
horizontal stretch (Flycast `rend.ScreenStretching=133`).

### Probe recipe (Flycast cheat file, `captures/ws-probe/ws.cht`)

Five entries: `ax=0x3F400000` every VBlank; `runNextIfEq(+0x00 ==
0x43BEB59F) → +0x00 = 0x438F0837` (286.064 = 381.4189×0.75);
`runNextIfEq(+0x10 == 0x3B2BD253) → +0x10 = 0x3B65186F`.
**Gotcha:** `memory_search_size` is a bit-width exponent
(`cheat.size = 1 << n`, `core/cheats.cpp:421`; read/write switch on
8/16/32 bits, `:641-676`). Use **5** for 32-bit; `2` (as first
written) silently degrades to a masked byte write that changes nothing
— the first leg showed a plain stretch for exactly that reason.
Launch (operator leg; the loader menu has no auto-start):

    FLYCAST_SHOT=$PWD/captures/ws-probe/shot.png \
    scripts/capture_dc_leg.sh <leg> build/disc.gdi \
      -config config:pvr.rend=0 \
      -config config:rend.ScreenStretching=133 \
      -config "cheats:T-SRS001M=$PWD/captures/ws-probe/ws.cht"

`pvr.rend=0` is mandatory: a persisted `pvr.rend = 4` (Vulkan) in
`emu.cfg` segfaults in `VulkanRenderer::Init` on this build
(`tooling.md` §RAWFB). Flycast persists the cheat path under
`[cheats] T-SRS001M` in `~/Library/Application Support/Flycast/emu.cfg`
(`loadCheatFile` → `config::saveStr`, `cheats.cpp:435`); it was removed
after the spike so normal runs stay 4:3.

## 3. Why it is parked — the wall

With the projection widened, the operator saw an **invisible wall at the
old 4:3 screen edge**: the view shows arena beyond it, but play stops
there. The game's bound is not derived from Ninja's struct (no game-code
reader of any field, §2), and the image holds none of the 4:3 frustum
constants a bounds routine would need (scan for tan 40°, 1/tan 40°,
381.4, 1.333 over `tools/boot.bin`: 0 hits), so the playfield limit is
either a world-space arena size tuned to fill 4:3 at max zoom-out or a
clamp computed inside game camera code from its own angle. Either way
it is the game's rule — in this series the screen edge is the corner you
push the opponent into — and widening it means a wider field, different
dodge room and projectile travel, and CPU logic that assumes the 4:3
field. Senko no Ronde DUO / 2 are 16:9 because the game was *designed*
for it, not because the renderer was. The only other knob, scaling Y by
4/3 instead (crop top/bottom), hides parts of a vertically screen-bound
field and is worse than 4:3.

**If ever resumed:** the work is finding the game's bound/camera routine
(callers of njSetPerspective: `FUN_8c043a42`, `FUN_8c0ae5f4`,
`FUN_8c0aad9c`, `FUN_8c0aac4c`, plus sites at `0x8c076xxx`,
`0x8c07bxxx`, `0x8c087xxx`, `0x8c136xxx`), widening its X half-extent
by 4/3, and then playtesting balance — a day or more, outcome uncertain.
Ship path if it ever passes: menu row in `scripts/menu_def.py`,
`SHIM_STATE[3]` flag, per-poll shim poke (`ax=0.75; X=−Y·0.75;
inv=1/X`), one hardware leg on a 16:9 TV. Known limit regardless: 2D
HUD/menus are screen-space and stretch with the TV, as in every DC
widescreen hack.

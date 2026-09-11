# Phase 7 T9 — Pre-game menu (design)

2026-09-11. Pool entry: `docs/kb/phase7-polishing.md` §T9 (operator ask
2026-09-07). Brainstormed and approved in-session 2026-09-11.

## Goal

A menu shown at every boot, before the game loads, with three items:

1. **START GAME** — pre-selected default; boots the game.
2. **SETTINGS** — submenu exposing the full native GAME ASSIGNMENTS
   settings list; chosen values take effect for this session.
3. **CONTROLS** — full-screen image of the control scheme; B returns.

Stateless: settings reset to the baked defaults every power-on. VMU
persistence is explicitly deferred (pool entry: "stateless first,
optional VMU persistence later").

## Decisions (approved)

- **Settings set**: everything the game's own GAME ASSIGNMENTS test
  menu exposes — not just the already-RE'd fields. Requires the recon
  leg below.
- **Boot flow**: the menu waits indefinitely; no idle auto-start.
- **Text/style**: offline-generated image assets in a style matching
  the game, baked like `splash.png`. No KOS bfont, no runtime typeset
  text (T7 precedent: hand-typeset shim text judged off-style,
  `docs/kb/phase7-polishing.md` §T7 round 2 hardware verdict).

## Why this shape (context)

- The game reads all its game-assignment settings from the 16-byte
  EEPROM game record (`0x2C..0x3B`, duplicated at `0x3C..0x4B`, two
  4-byte CRC headers at `0x24..0x2B`) — field map so far in
  `docs/kb/phase5-hardware.md` §EEPROM game record: idx4 = Event mode,
  idx6 = difficulty, idx10/idx14 changed with difficulty but not
  identified.
- The shim serves the EEPROM from a baked blob `eeprom_img`
  (`shims/build/mie_blobs.c`) and copies it into game RAM pre-handoff
  (`shims/src/main.c` — full image + both system copies). Writing
  session settings = poking that blob's game area in RAM before
  handoff; the proven RAM-copy path does the rest. Zero new game-side
  code.
- The loader already does everything a menu needs: full-screen RGB565
  blits (`splash_bin` memcpy in `loader/main.c`) and maple controller
  polling (the A+START test-boot combo).

## 0. Prerequisite recon leg — GAME ASSIGNMENTS byte map

Emulator-only, no operator. In Flycast (instrumented fork or stock):
boot into the game's GAME TEST MENU → GAME ASSIGNMENTS, enumerate
every item and its value range (screenshots), then change ONE item at
a time, save-exit, and diff the saved EEPROM game record against the
previous state. Same method that mapped Event mode
(`docs/kb/phase5-hardware.md` §EEPROM game record).

Output (gate for the build work): a complete field-map table in the KB
— for each GAME ASSIGNMENTS item: byte index in the record, encoding
(value ↔ on-screen label), default. This also settles idx10/idx14.
BOOKKEEPING and BACKUP DATA CLEAR are not settings and are out of
scope.

## 1. Menu core

New `loader/menu.c`, called from `loader/main.c` before the existing
splash/load path, which stays untouched — START GAME falls through to
today's exact boot sequence.

- KOS maple polling (existing pattern) — d-pad up/down moves the
  cursor, A selects, B backs out of a submenu.
- Framebuffer compositing (existing `vram_s` blit pattern), 640×480
  RGB565.
- Waits indefinitely for input.
- Port-A controller only (same device the test-combo check uses).

## 2. Settings submenu

- One row per field from the recon map; left/right on the d-pad cycles
  the value through its legal range. Cursor up/down between rows; B
  returns to the top menu.
- State: a plain struct of current values, initialized each boot from
  the baked default record (stateless by construction).
- Apply (on START GAME): build the 16-byte record from the struct,
  compute the game-section CRC-16 (seed `0xdebdeb00`, trailing round —
  algorithm from `naomi_flashrom.cpp:26-51`, already cited in
  `docs/kb/phase4-conversion.md`), and write record + duplicate + both
  CRC headers into the shim blob's `eeprom_img` game area
  (`0x24..0x4B`) in RAM before handoff. The offset into the shim image
  is exported via `shims/include/shim_iface.h` (or a linker symbol) so
  the loader never hardcodes a blob layout.

## 3. Controls screen

One full-screen baked image (existing `splash.png` → RGB565 blob
pipeline) showing the control scheme per the shim's actual maple→JVS
mapping (`docs/kb/input-map.md` §DC pad map — our code, so
authoritative; no game RE needed). Round 1 renders it as a clean
button→action table; a drawn controller diagram is an operator-gated
style iteration, like all T9 asset styling. Generated offline. B
returns to the menu.

## 4. Assets

All offline-generated, committed as source images, baked by the
existing objcopy pipeline (`loader/Makefile`):

- One menu background (may reuse/derive from the splash).
- Label/value **strips**: each menu label in normal + highlighted
  variants, each settings value string pre-rendered once. The loader
  blits strips at fixed coordinates — one mechanism for every screen.
  (Full per-state screens rejected: combinatorial across settings
  values × cursor positions.)
- The controls screen (full-screen, §3).

Asset count is bounded by the recon map: 3 top-menu labels + N
settings rows + their value strings.

## 5. Safety

- After poking, validate the image exactly the way the game does:
  serial intact, game-section CRC recomputes to the stored value
  (acceptance criteria from `naomi.md`, cited in
  `docs/kb/phase4-conversion.md` §EEPROM). Any mismatch → restore the
  untouched baked image and boot with defaults. The menu can never
  produce a worse boot than today's.
- Any menu-code failure mode defaults to START GAME semantics with
  the baked record.

## 6. Testing

Emulator legs:

- **Navigation leg**: drive the full menu tree (all rows, wrap
  behavior, B backing out, controls screen and back), screenshot
  verdicts — viewed, not byte-checked (verification-discipline
  memory).
- **Effect control tests**: at least difficulty (EASY vs default —
  known-visible, Task 18) and Event mode (known-visible, phase 6 leg)
  set via the menu and confirmed in-game.
- **Byte leg**: SERIAL diag prints the poked record + CRC; compare
  against a hand-built expected record.
- **Regression**: boot with zero menu interaction beyond START GAME →
  poked record byte-identical to the baked default; game behavior
  identical to release v13.

Hardware round (operator): drive the menu on the real DC — style
verdict on the assets, one setting changed end-to-end and observed
in-game, regression boot on both cables.

## Non-goals

- VMU persistence (pool entry: later).
- Menu sound, animated transitions.
- Overlapping the disc load behind the menu (possible later
  optimization; START GAME simply enters today's load path).
- 2P/port-B menu navigation.

## Open items

- Exact GAME ASSIGNMENTS item list and encodings — produced by the
  §0 recon leg before implementation planning of the submenu rows.
- Final visual style of the assets — iterated with the operator via
  the hardware round, as with T7/T12.

# Controls layouts — per-port pad presets + arcade-stick layout (design)

2026-09-27. Origin: tester request (EVO Japan player, message archived in
`CONTROLS_TASK.MD`). Brainstormed and approved in-session 2026-09-27.

## Goal

Let players choose a control layout the modern way, without ever declaring
who sits at which port:

1. **Two pad presets** — *Tournament* (the tester's EVO layout, new
   default) and *Classic* (the current shipped mapping), selectable
   **per port** on the menu's Controls page.
2. **Arcade-stick layout** — the original Naomi cabinet layout, applied
   automatically whenever an arcade stick is detected in a port. Not a
   setting; sticks always get it. This also fixes a real defect: the
   current mapping puts OverDrive only on the triggers, which the stick
   (HKT-7300 class) does not have, so stick players today have no
   OverDrive at all.
3. **Controls page rebuilt** as device art + labels drawn by loader code
   (no more single baked screenshot), doubling as the layout selector.

Session-only like the rest of the menu, but the chosen bytes live in the
same loader-side settings state that the planned save-all-settings (VMU)
work will serialize later.

## Decisions (approved)

- **Presets, not free remap.** Two pad tables + one stick table. The
  codegen'd table structure is what a future remap screen would edit,
  so nothing forecloses it.
- **Default pad layout = Tournament.** Deliberate behavior change from
  the shipped default; Classic remains one press away.
- **Pad layout keyed per port** (`P1 PAD LAYOUT`, `P2 PAD LAYOUT`), so
  P1-Classic + P2-Tournament works. A port's setting applies to
  whatever *pad* occupies that port whenever it does; a stick in that
  port ignores it.
- **Device classification per port per poll** from the already-latched
  DEVINFO capability word — hot-plug, mid-session swaps, and a port
  empty at boot all resolve without menu interaction.
- **Selector lives on the Controls page** (see §3), not as rows in the
  GAME ASSIGNMENTS settings screen — you pick a layout while looking
  at it.
- **No runtime font** (T9 precedent): label words baked offline into
  the existing sprite sheet, blitted at per-device anchor coordinates.
- **Single source of truth**: layouts defined once in
  `scripts/menu_def.py`; the generator emits both the menu label/anchor
  tables and the shim's button→JVS tables.

## The three layouts

JVS bits per `shims/src/jvs.c:26-40` / `docs/kb/input-map.md`:
M(ain) 0x0200, S(ub) 0x0100, A(ction) 0x0040, Barrage 0x0080,
OverDrive 0x0020, Start 0x8000. D-pad/analog handling is unchanged in
all layouts.

| DC control | Classic (current) | Tournament (default) | Stick (fixed) |
|---|---|---|---|
| A | Main | Main | Action |
| B | Action | Sub | — (unmapped) |
| X | Sub | Barrage | Main |
| Y | Barrage | Action | Sub |
| Z | — | — | Barrage |
| C | — | — | OverDrive |
| L trigger | Action (dup) | OverDrive | n/a |
| R trigger | OverDrive | Action | n/a |
| Start | Start | Start | Start |

Classic is byte-for-byte today's mapping (`jvs.c:42-60`). Tournament and
Stick are the tester's layouts verbatim; Stick B stays unmapped per the
tester's spec (B still works loader-side as menu Back).

## Why this shape (context)

- The shim already latches a per-port DEVINFO capability word:
  `devinfo_caps[2]` in `shims/src/maple.c:56-76` (commit 162a8a4), with
  measured values pad `0xfe060f00` vs Ascii Stick `0xff070000`
  (regression test `shims/test/test_host.c`). Classifier: **no analog
  triggers and no analog stick ⇒ arcade stick**; anything else
  (including unknown) ⇒ pad. Capability bits, not product-name strings
  — the RX window isn't sized for the full 108-byte DEVINFO payload and
  doesn't need to be.
- Hot-plug already re-probes DEVINFO after 64 consecutive failed polls
  (T11, `maple.c:141-142`), which covers human-speed swaps and
  late-plugged ports. The one known gap (in-code `ponytail:` comment,
  `maple.c:53-55`): a swap that answers GETCOND before any re-probe
  keeps stale caps. Now that mapping follows the device, close it: set
  a per-port "was dead" flag on a failed poll and re-probe on the first
  successful poll after it.
- The menu has a loader→shim side channel that is not the EEPROM game
  record: `SHIM_STATE` words (`loader/main.c:475-477` pass `test_boot`,
  `backend`). Layout choice rides there — it is not a game setting and
  must not touch the Naomi EEPROM path.
- The menu's rendering model (offline-baked sprite sheet + `vram_s`
  cell blits, no full-frame clears after entry — T9) extends directly:
  bake the label words once, blit them at anchor coordinates over the
  device art, redraw label cells only on change.

## 1. Shim: table-driven mapping

`shims/src/jvs.c` — replace the hardcoded if-chain (`jvs.c:42-60`) with
three generated `{dc_button_bit, jvs_bits}` tables (Classic,
Tournament, Stick) compiled in from the generated header.

Per port per poll in the GETCOND path:

1. Classify `devinfo_caps[port]` → stick or pad (rule above).
2. Stick → `STICK_ARCADE`. Pad → table indexed by that port's
   SHIM_STATE layout byte (out-of-range ⇒ Tournament).
3. Existing normalization (`dc_cond_to_pressed`: active-low, trigger
   threshold 128, analog→d-pad, mutual exclusion) is untouched and runs
   before table lookup, as today.

Test-mode remap (`jvs.c:83-87`) and everything else in the JVS path is
unchanged.

`shims/src/maple.c` — the dead-port re-probe flag (§context above).
A few lines; no new probe traffic in steady state.

## 2. Loader→shim carrier

One SHIM_STATE word carrying two bytes: P1 pad layout, P2 pad layout
(0 = Tournament, 1 = Classic; 0 is the default so an unwritten word is
correct). Written next to the existing stagings at
`loader/main.c:475-477`. Loader-side the two bytes live in the menu's
settings state alongside `menu_game_record`, so the future VMU
serializer picks them up with everything else.

## 3. Controls page = selector

Replaces the single static blit (`loader/menu.c:95-99`). Layout:

```
        [ device art + labels ]

  P1 PAD LAYOUT   ◄ TOURNAMENT ►
  P2 PAD LAYOUT   ◄ TOURNAMENT ►
  STICK LAYOUT      ARCADE (fixed)
```

- Up/Down moves the highlight across the three rows; Left/Right cycles
  the highlighted pad row's value; the stick row is informational.
- The diagram always previews the **highlighted** row: pad rows show
  the HKT-7700 art labeled with that port's current preset; the stick
  row shows the HKT-7300 art with the fixed arcade labels.
- Initial highlight: P1's row if a pad (or nothing) is in port A, the
  stick row if a stick is detected there. Loader-side classification
  uses the same caps rule via KOS device info.
- B backs out to the top menu, as today. Rendering per the existing
  cell-redraw pattern; label cells and selector rows are the only
  repaint targets after entry.
- Row labels and values are baked into the sprite sheet like every
  other menu string (normal + highlighted variants).

## 4. Art assets (operator-provided)

Two backgrounds, generated by the operator (ChatGPT), same pipeline as
the current diagram (`gen_menu_assets.py` autocrop/resize/tint →
RGB565 blob):

- **HKT-7700** standard controller, and **HKT-7300** arcade stick.
- Requirements: consistent line-art style between the two; every button
  clearly visible and identifiable; **no text baked on or near
  buttons** (labels are runtime blits); plain background (corner
  floodfill must work); enough clear margin next to each button for a
  label word.
- Anchor coordinates (per device: button → label x,y) are measured once
  when the art lands and recorded in `scripts/menu_def.py`.

## 5. Codegen

`scripts/menu_def.py` gains: the three layout tables (button → JVS
function), the label word list, and per-device anchor tables.
`scripts/gen_menu_assets.py` renders the new label sprites into the
sheet and emits, alongside `menu_layout.h`, a second generated header
`shims/src/layouts.h` with the three button-bit→JVS-bit tables for the
shim (gitignored like other generated build inputs if that's the local
convention; the plan settles the exact path/ignore rule). One definition; menu display
and shim behavior cannot drift.

## 6. Testing & verification

- **Host tests** (`shims/test/test_host.c`): all three tables
  (including Stick reaching OverDrive — the regression this fixes),
  the caps classifier on the three cases (pad word, stick word,
  unknown⇒pad), per-port independence (P1 Classic + P2 Tournament),
  layout-byte out-of-range fallback, dead-port re-probe flag behavior.
- **Emulator leg**: menu navigation + both art pages + selector
  behavior in Flycast; mapping sanity with a pad.
- **Hardware leg (the claim gate, per operator-leg protocol)**: real
  DC with the Ascii Stick and a standard pad — stick-only, pad-only,
  mixed both ways, a mid-session pad↔stick swap on one port, and
  boot-with-empty-port-B then late plug-in. No "works" claim before
  this passes.

## Out of scope

- **VMU persistence** — near-future separate task (operator: save all
  settings, including controls). This design only parks the bytes
  where that task will find them.
- **Free per-button remap** — the generated tables are the structure a
  remap screen would edit; nothing more.
- **"OLD dash type" default** (the tester's other recommendation) —
  separate task; needs a GAME ASSIGNMENTS recon pass to locate the
  EEPROM byte before it can become a settings row / default.

# Project status

**Updated:** 2026-08-19 (Phase 2 Instrumented Analysis — DONE; gate green)

## What this is

Static binary conversion of *Senko no Ronde Special* (Sega Naomi GD-ROM,
`senkosp`, GDL-0038) to Sega Dreamcast: patch the Naomi-specific hardware
touchpoints in the game binary (DIMM/cart reads → GD-ROM streaming, MIE/JVS
input → Maple controllers, EEPROM/settings → native-path stubs, free-play
baked in) and boot it from a GDI via a custom loader.
Charter + Phase 1 spec:
`docs/superpowers/specs/2026-08-13-charter-phase1-foundation-design.md`.

## Decisions

- Target: real Dreamcast hardware (GDEMU-class ODE). Emulators are dev
  tools, not the goal.
- Method: the six-phase playbook from the Cleopatra Fortune Plus port
  (`docs/kb/port-playbook.md`), gates enforced, spec + plan per phase.
- Central technical problem (from `../naomi2dreamcast/assessments/senkosp.md`,
  v9 2026-08-09): assets park above DC caps — main-RAM cart-DMA high-water
  33,453,344 (33.4 MB) vs DC's 16 MB (content only 5.85 MB); VRAM address
  extent 11.9 MB vs 8 MB (content 4.79 MB incl. double framebuffer). Phase 2
  measures which streams land high; Phase 3 decides relocation vs streaming
  retarget. ARAM expected to fit (content 1.35 MB / 2 MB).
- Asset cutting/compression is a last resort (REQUIREMENTS.md).

## Phases

1. **Foundation — DONE 2026-08-13** (repo, KB, tooling records, .dat, boot verification)
2. **Instrumented analysis — DONE 2026-08-19** (streaming/input/memory ground truth; the high-address DMA map)
3. Reverse engineering (touchpoint addresses + patch plan; relocation strategy)
4. Conversion (loader + shim + patch table → bootable GDI)
5. Real-hardware testing & fit
6. Safety tripwires & release

## Phase 1 checklist

- [x] Repo scaffolding: .gitignore, CLAUDE.md, KB skeleton, playbook carried over
- [x] tooling.md — every tool verified + recorded (Flycast build, Ghidra, dat-extract)
- [x] senkosp.dat extracted from CHD, carve sanity-checked vs assessment
- [x] Boot verification: untouched game reaches attract in Flycast naomigd profile (screenshot in KB)
- [x] Exit audit + fresh-agent test

## Phase 2 checklist (gate — all six exit criteria met, 2026-08-19)

- [x] `cart-streaming-map.csv` — 1,590 merged/deduped DMA tuples + 2 PIO
      seeks (1,592 rows) from all 14 legs, all six parser CHECKs PASS,
      above-16m map (5 spans) summarized in `cart-streaming-map.md`.
- [x] Per-region write-truth verdicts + above-cap bucket maps in
      `phase2-measurements.md` §Region verdicts.
- [x] `input-map.md` — 13/13 controls mapped (11 measured via MIE sub=15 +
      JVS cross-check, 2 source-derived: Coin/Test, masked out of the
      16-bit JVS log line — `maple_devs.h:97-98`).
- [x] Serial/RTC/watchdog verdicts in `phase2-measurements.md` §Device
      verdicts — all three: 0 pokes across all 14 legs.
- [x] Coverage checklist closed (`phase2-measurements.md`): full roster (8
      characters), all 8 stages, Novice mode, test menu (incl. EEPROM
      write-back), input leg.
- [x] Capture recipe in `tooling.md` §Phase 2 capture harness; this file
      advanced to Phase 3.

## Key facts so far

- `senkosp` = the 2006 arcade back-port of the X360 Rev.X set; only member
  of its family; GD-ROM GDL-0038, 237.7 MB, machine `naomigd`, ROT0;
  export/English PIC `317-5123-COM`. Assessment: 91.0 (S), rank 1
  (`../naomi2dreamcast/assessments/senkosp.md`).
- Boots and runs fully (attract/demo cycle) under the instrumented Flycast
  fork at commit `f014a410c` — assessment v9 capture, 2026-08-09.
- Controls: stick + 5 buttons (M/S/A + Barrage/C + OverDrive) → DC pad has
  6, one to spare.
- Streaming is modest: 26.6 MiB per 600 s attract, steady 2.3 MB/min.
- Guts flags to watch in Phase 3: `eeprom_bios`, `serial`, `rtc` (RTC is
  new vs Cleopatra — 3 MMIO refs).
- Boot verification 2026-08-13: untouched romset reaches title + demo in the
  reused fork build (`f014a410c`) on this machine —
  `docs/kb/img/senkosp-{title,attract}.png` (title grab is the
  title-sequence press-start/staff-credit frame, not the SP logo card — the
  ~2 s logo window fell between samples; demo frame is the dispositive gate
  evidence).
- **Phase 2 headline numbers (2026-08-19, full campaign, 14 legs, gate
  evidence — `docs/kb/cart-streaming-map.md`,
  `docs/kb/phase2-measurements.md`):**
  - Merged main-RAM DMA high-water: `0x1fe7520` = 33,453,344 B, unchanged
    from the v9 attract-only anchor and from `attract` leg alone — no leg
    pushed the ceiling higher, only the floor of the largest above-16m span
    moved (via `2p-stages`).
  - Above-16m map: **5 contiguous main-RAM spans**, 11.64 MB unique
    destination footprint, 253,100,032 B (241.4 MB) actually streamed into
    that footprint across the campaign (~20.7× re-streaming, not a one-shot
    load) — 1,590 unique DMA tuples total.
  - Region verdicts (write-truth, full campaign vs v9 attract-only): main
    content 13,014,015 B / 16 MB cap (u 0.776, up from v9's 0.349) — fits as
    volume, but 11,428,714 B above-16m needs relocation, not cutting (5
    streams). VRAM content+2×fb 7,239,988 B / 8 MB cap (u 0.863, up from
    v9's 0.571) — still fits, no headroom left. ARAM content 1,348,121 B /
    2 MB cap (u 0.643, essentially unchanged from v9) — still fits, as
    expected.
  - Device verdicts (runtime, all 14 legs): serial (SCIF), RTC, and
    watchdog all **0 pokes** anywhere in the campaign — not touched. EEPROM
    (MIE `sub=0x0b`) confirmed BIOS-path: 32 ops, all in the test-menu leg
    only, 0 elsewhere.
  - Input map: 13/13 controls mapped (`docs/kb/input-map.md`).

## Next step

Phase 3 — reverse engineering. Brainstorm + spec first (superpowers loop,
per the playbook cadence): find the touchpoint addresses behind Phase 2's
measured behavior and decide the relocation-vs-streaming-retarget strategy
for the 5 above-16m main-RAM streams and the tight-but-fitting VRAM budget;
decide the shim/ignore call for serial/RTC/watchdog (0 runtime pokes,
static-only guts refs); trace the EEPROM `sub=0x0b` handler (test-menu-only,
BIOS-path confirmed); finalize the control-layout choice from the closed
input map. Inputs, all from this phase: `docs/kb/cart-streaming-map.md` +
`.csv` (above-16m map, per-stream cart-offset provenance),
`docs/kb/phase2-measurements.md` (region + device verdicts, above-cap
bucket maps — the relocation source map), `docs/kb/input-map.md` (13/13
controls). Use
Ghidra (`docs/kb/tooling.md` §Ghidra — reused install, not yet exercised in
this repo) against `senkosp.dat`.

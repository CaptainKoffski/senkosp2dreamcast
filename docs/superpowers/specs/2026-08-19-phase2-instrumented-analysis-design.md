# Phase 2 — Instrumented Analysis: design spec

**Date:** 2026-08-19
**Status:** approved (design), pending implementation plan
**Predecessor:** Phase 1 Foundation
(`docs/superpowers/specs/2026-08-13-charter-phase1-foundation-design.md`)
**Project:** static binary conversion of *Senko no Ronde Special* (Naomi
GD-ROM → Dreamcast). See `CLAUDE.md`, `docs/kb/00-status.md`.

## Purpose

Phase 1 proved the untouched game boots under the instrumented Flycast fork.
Phase 2 observes what the game actually does at runtime and records it as
data Phase 3 can decide against. The assessment
(`../naomi2dreamcast/assessments/senkosp.md`, v9 capture 2026-08-09) already
measured the *aggregates* — DMA high-water 33,453,344 B, per-region content
volumes, streaming rate — but kept no per-event log for senkosp, and its
capture was attract-only. Phase 2 re-captures with the raw logs kept and
real gameplay covered.

The central question this phase answers, per the charter risk list: **which
cart-DMA streams land above the Dreamcast's 16 MB main-RAM line, and which
VRAM placements exceed the 8 MB cap** — the per-stream input to Phase 3's
relocation-vs-streaming-retarget decision.

Phase 2 captures **behavior, not code**. Disassembling the functions that
issue these requests is Phase 3.

## Key difference from the Cleopatra Phase 2

No instrumentation is built in this phase. The fork
(`../flycast4naomi2dreamcast`, commit `f014a410c`, already built on this
machine — `docs/kb/tooling.md`) carries everything Cleopatra's Phase 2/3/4
added, and the log format is already parsed by
`../naomi2dreamcast/tools/assess/parse_capture.py`:

- `CARTDMA src= dest= len=` per DMA event; `CARTPIO offset=` per PIO read
  (`core/hw/naomi/naomi.cpp`, `core/hw/naomi/naomi_cart.cpp:1020`).
- `MAINPROFILE`/`VRAMPROFILE`/`ARAMPROFILE` write-truth vs handoff baseline,
  plus `MAINHIST`/`VRAMHIST`/`ARAMHIST` nonzero-bytes-per-256 KB-bucket maps
  (`core/hw/naomi/naomi.cpp`).
- `MIERESP sub=.. data=..` — MIE (Maple cmd `0x86`) response bytes, input
  subcommand `0x15` included; `JVSREPORT buttons=` as a second decode
  (`core/hw/maple/maple_if.cpp:292`, `maple_jvs.cpp:2241`).
- `SERIALPOKE` (`naomi.cpp:120`) and the game-code HW-poke log `HW[rw]`
  (`core/hw/mem/addrspace.cpp:136`). The HW log's PC filter
  (`0x0c020000–0x0c200000` physical) covers senkosp unchanged: carve base
  `0x8c020000` + code 1,515,512 B ends at `0x0c1920f8`.

Logging is off unless `FLYCAST_CARTLOG=<path>` is set
(`core/hw/naomi/cartlog.cpp`), so the same build serves plain play and
instrumented capture. **The fork stays frozen at `f014a410c` for this
phase.**

## Approach (chosen: per-leg raw logs + offline parser)

Each capture leg is one launch of the fork with its own log file
(`FLYCAST_CARTLOG=captures/<leg>.log`); a thin wrapper script names the
legs; one offline parser merges all legs into the deliverables.
Attribution is by leg file — stronger than Cleopatra's
run-ordering-within-one-log, with zero fork changes.

Rejected:

- **Reusing the assessment battery (`run_battery.py`).** Built for
  unattended fixed-duration captures with automatic handoff detection and
  screenshot timelines; interactive play legs fight all of its assumptions.
  More glue than value.
- **Extending the fork (scene-tag hotkey, timestamps).** Cleopatra's spec
  deferred the same idea unless ordering attribution failed; per-leg files
  make it less necessary still. YAGNI.

Roles: the user plays every leg; the agent launches runs, collects and
parses logs between legs, and reports remaining coverage.

## The four capture targets

### 1. Cart-streaming map with the high-address destination map (primary)

Every `CARTDMA`/`CARTPIO` event becomes a
`(leg, cart_offset, length, dest, mode)` tuple, merged and deduped across
legs. The senkosp-specific core: classify each main-RAM destination against
the 16 MB line — a destination whose offset within the RAM window
(`(dest & 0x1fffffff) − 0x0c000000`) is ≥ 16 MB is flagged `above_16m`.
The summary leads with the high-address map: per-stream destination ranges
above the line, sizes, and cart-offset provenance.

Cross-check: the **attract leg** must reproduce the assessment's
`dma_high_water` 33,453,344 (byte-identical across the independent v4 and
v9 attract captures — same coverage, same figure); falling short means the
capture is blind, not that the game changed. The merged sweep may only
raise it (gameplay can add DMA, never remove it), bounded by the 32 MB
window top.

Output: `docs/kb/cart-streaming-map.md` (summary, high-address map first)
+ `docs/kb/cart-streaming-map.csv` (columns
`leg,cart_offset,length,dest,mode,above_16m`; append-friendly for top-ups).

### 2. Region write-truth under real gameplay

The v9 profiles were attract-only. The sweep answers: does gameplay push
content beyond attract's figures — main 5,850,229 B nonzero (4,266,292
above the 16 MB line), VRAM content 3,557,968 + 614,400 framebuffer, ARAM
1,348,105 B — and exactly which 256 KB buckets above each cap hold content
(the relocation source map for Phase 3). ARAM is expected to keep fitting
(2 MB cap); verify.

Output: per-region verdicts + above-cap bucket maps in
`docs/kb/phase2-measurements.md`.

### 3. Input map

`MIERESP sub=15` bits during a dedicated input leg, pressed in stated
order: Up, Down, Left, Right, M, S, A, Barrage (C), OverDrive, Start,
Coin, Test, Service — ~1 s holds with gaps. Exactly one bit changes per
control; `JVSREPORT` is the cross-check decode. Read by hand — no parser
(13 rows).

Output: `docs/kb/input-map.md`.

### 4. Serial / RTC / watchdog runtime verdicts

`SERIALPOKE` counts plus `HW[rw]` lines touching SCIF/RTC ranges, during
gameplay *and* the test-menu leg. Runtime ground truth for the assessment
guts flags `eeprom_bios`, `serial`, `rtc` — RTC (3 static MMIO refs) is new
vs Cleopatra and gets its first dynamic evidence here. The attract-only v9
capture already recorded `serial_pokes = 0`; gameplay and test menu may
differ.

Output: one-line verdict per device in `phase2-measurements.md` — touched
or not; shim needed or ignorable (decision itself is Phase 3).

## Capture campaign

Each leg gets its own log; the parser merges. Coverage is tracked as a
checklist in the KB; top-ups are just more legs.

1. **Attract leg** — one full attract cycle (story card → title → both
   DEMONSTRATION fights → hiscore ranking → loop). Same shape as v9, raw
   log kept. Reproduction anchor for the high-water cross-check.
2. **Roster sweep legs** — one arcade run per playable character: pick
   each character once, play to game over including the continue screen.
   Opponents and stages accumulate across runs; use SP's stage/music
   select to vary stages between runs. One run in Novice mode. The roster
   checklist is enumerated from the character-select screen during the
   first leg, not from external claims.
3. **Test-menu leg** — enter the service/test menu, walk bookkeeping and
   game-settings screens, flip one harmless setting and restore it, exit.
   Exercises the EEPROM write-back and RTC read paths behind the guts
   flags — runtime evidence Cleopatra only collected once real hardware
   made it painful.
4. **Input leg** — the stated press order from target 3.

**Coverage target (part of the gate):** every roster character has appeared
in at least one captured match (as pick or opponent), every selectable
stage seen at least once, Novice covered, test menu covered, input leg
decoded.

## Tooling & data flow

```
scripts/capture_leg.sh <leg>          # FLYCAST_CARTLOG=captures/<leg>.log,
        │                             # launches the built fork, Phase 1 senkosp setup
        ▼
captures/<leg>.log                    # raw, gitignored, never committed
        │
scripts/parse_cartlog.py  ───────────► docs/kb/cart-streaming-map.{md,csv}
  (adapted from ../cleopatra/          docs/kb/phase2-measurements.md
   scripts/parse_cart_log.py;          (region verdicts, bucket maps,
   regexes proven in assess/           serial/RTC/watchdog verdicts)
   parse_capture.py)
input leg, read by hand  ────────────► docs/kb/input-map.md
```

Raw logs stay out of git (`captures/` gitignored — they are large, and
derived-from-ROM addresses are fine but bulk is not). Parsed outputs are
measurements, not copyrighted bytes: committed.

## Verification

Asserts in `parse_cartlog.py`, not prose:

- Every DMA destination lands inside a real RAM region (main/VRAM/ARAM
  windows).
- Every DMA length is a whole number of `0x20`-byte units (DMA_COUNT
  granularity — Cleopatra Phase 2 finding, same hardware).
- At least one request lies beyond the 1 MB boot region — proof of runtime
  streaming, not just the boot load.
- Main write-truth watermark ≥ the boot-load extent (carve base
  `0x8c020000` + 1,515,512 B), else the logger is blind.
- Attract-leg high-water equals 33,453,344; merged high-water is
  ≥ that and ≤ the 32 MB window top.
- Input leg: exactly one bit change per held control; zero or many bits
  means the decode is wrong.

Human-side gate: the roster/stage coverage checklist is closed.

## Deliverables

- `scripts/capture_leg.sh` — leg launcher (env + fork invocation).
- `scripts/parse_cartlog.py` — legs → CSV/summary + region verdicts +
  device verdicts, sanity asserts included.
- `docs/kb/cart-streaming-map.md` + `.csv`.
- `docs/kb/phase2-measurements.md`.
- `docs/kb/input-map.md`.
- `docs/kb/tooling.md` — capture recipe recorded (env var, invocation,
  leg naming).
- `docs/kb/00-status.md` — Phase 2 done, coverage checklist closed,
  Phase 3 next.

## Scope boundaries

- **In:** runtime capture (streaming, memory, input, device pokes) via the
  existing fork build; the wrapper + parser; KB writeups.
- **Out — Phase 3:** disassembly, touchpoint addresses, the
  relocation-vs-retarget decision itself, control-layout choice.
- **Out — Phase 4+:** patching, loader, disc mastering.
- **No fork changes.** If a capture gap genuinely requires new
  instrumentation, that is a spec amendment, not a quiet commit to the
  fork.
- Decrypt handling irrelevant: the `.dat` is already decrypted (Phase 1).

## Exit criteria

Phase 2 is done when:

1. `cart-streaming-map.csv` holds the merged per-request tuples from all
   legs, passing every parser assert, with the `above_16m` map summarized
   in the `.md`.
2. Per-region gameplay write-truth verdicts + above-cap bucket maps are
   recorded in `phase2-measurements.md`.
3. `input-map.md` maps all 13 controls to MIE bits, JVS cross-checked.
4. Serial/RTC/watchdog verdicts are recorded.
5. The coverage checklist (roster, stages, Novice, test menu) is closed.
6. The capture recipe is in `tooling.md`; `00-status.md` advanced to
   Phase 3.

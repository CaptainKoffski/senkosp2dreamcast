# Phase 5 — Real-hardware testing & fit: design spec

**Date:** 2026-08-23
**Status:** approved (design), pending implementation plan
**Predecessor:** Phase 4 conversion
(`docs/superpowers/specs/2026-08-22-phase4-conversion-design.md`;
gate green 2026-08-23, all eight criteria — `docs/kb/00-status.md`
§Phase 4 checklist)
**Precedent:** the Cleopatra Phase 5 hardware rounds
(`../cleopatra/docs/kb/00-status.md`, `port-playbook.md` §Gotchas —
mastering traps, control-test discipline, on-screen HUD).
**Project:** static binary conversion of *Senko no Ronde Special*
(Naomi GD-ROM → Dreamcast). See `CLAUDE.md`, `docs/kb/00-status.md`.

## Purpose

Phase 4 shipped a reproducible GDI (`build/disc.gdi`, criterion 7)
proven only in Flycast's DC profile. Phase 5 has two jobs, in a fixed
order:

1. **Close the texture-load-error hang** — the one high-severity
   finding Phase 4 carried (`docs/kb/phase4-conversion.md`
   §Texture-error hang (play1)) — **in the emulator, as a hard gate
   before any hardware boot.**
2. **Prove the disc on real silicon**: boot and play on the bench
   Dreamcast + GDEMU, re-earning Phase 4's five play criteria on
   hardware, and disposition the remaining carried findings
   (pad-poll latency, cyan splash).

**Gate (playbook):** boots and plays on real hardware. Exit criteria
in §Exit criteria below. The playbook's warning applies in both
directions here: emulator-green proves nothing about hardware, and
the hang gate is deliberately scoped so an emulator-only artifact
cannot stall the phase forever (§Decision 2 — exoneration counts).

## Decisions taken in this design (user-approved 2026-08-23)

1. **The texture hang is a hard gate.** No hardware boot until the
   hang is reproduced under instrumentation and root-caused. Rationale:
   if it is a data-integrity bug in the shim's raw-ATA driver, hardware
   rounds would be debugging on top of known-bad ground truth.
2. **Exoneration satisfies the gate.** If the instruments prove the
   shim handed the game bytes identical to the source GDI and the fault
   lands emulator-side (Flycast texture cache or GD emulation), the
   port artifact is clean: record the verdict in the KB and proceed to
   hardware. No obligation to fix the fork.
3. **Operator legs first for reproduction.** The one sighting was on a
   match-win transition (`play1`, once in ~6 sessions) — a path attract
   mode may never exercise. Repro hunting is human sessions (repeated
   1P match wins; the operator's offered 2P all-stages leg), run under
   the stop-and-wait operator protocol. Unattended soaks are not the
   primary plan.
4. **Instrumentation approach C — both ends plus a hang marker, armed
   before the first operator leg.** Each repro costs a 1-in-6 hunt of
   operator time; one captured occurrence must yield a full verdict
   (§Instrumentation).
5. **Scope:** pad-poll latency stays in scope as a *reactive*
   contingency (staged `#if 0` TCNT0 cache); cyan-splash diagnosis is
   in scope; **VMU settings persistence is out** — deferred until after
   Phase 6's safety tripwires.
6. **Rig:** primary path is the bench Dreamcast + GDEMU (same rig as
   Cleopatra); DreamShell serial-SD is the planned secondary boot/debug
   path. No outside-tester round this phase.

## Work item 1 — the texture-hang gate (emulator)

### What Phase 4 established (do not re-derive)

`docs/kb/phase4-conversion.md` §Texture-error hang (play1): the game's
*own* `ERROR !! / TEXTURE LOAD ERROR !` handler fired; maple service
dead, render loop re-presenting one static frame; no reset attempted;
operator killed the process. Ranked candidates: (1) cart-stream data
integrity (shim's raw-ATA driver handing bad bytes), (2) Flycast's
texture cache. The named evidence gap: **no DC-profile cart/GD-read
probe existed** — `CARTDMA` is Naomi-cart-specific and taps nothing on
the DC profile.

### Instrumentation (build first, all three, then verify)

- **Shim CRC probe — delivered-truth.** The shim's raw-ATA driver
  CRC32s every block it returns to the game and records
  `(offset, len, crc)` in a small RAM ring buffer; a fork tap reads
  the ring out host-side. Diagnostic build flag (precedent:
  `LOADER_SERIAL`, `LOADER_FORCE_TEST_BOOT`) — the release GDI is
  byte-identical with the flag off.
- **Fork GD-read probe — drive-truth.** The instrumented Flycast fork
  (`../flycast4naomi2dreamcast`, source of truth) logs
  `(offset, len, crc)` for every DC-profile GD/IDE read the emulated
  drive serves, into the existing cartlog stream.
- **Hang marker.** One Ghidra string-ref lookup names the game's
  texture-error handler address; the fork logs a marker when the PC
  hits it (precedent: `PCSAMPLE`). No game patch — the occurrence
  self-timestamps with PC context.
- **Offline checker.** A script compares both CRC streams against the
  source GDI and prints the verdict per the table below. Ships with a
  self-test (parser-CHECK discipline, as in `parse_cartlog.py`).

**Instrument control test (before any operator leg):** one unattended
attract leg with everything armed — every delivered and drive CRC must
match the GDI, the hang marker must stay silent, and the leg must not
collapse in performance. A probe that can't pass its own null leg is
not evidence (Phase 2's `FLYCAST_HWLOG` null instrument is the cautionary
precedent — `docs/kb/00-status.md`, Device verdicts retraction).

### Repro legs and verdict

Operator sessions, instrumented, stop-and-wait: repeated 1P match wins
first (the sighted trigger), then the 2P all-stages leg. Repeat until
the hang marker fires in a capture.

| Evidence at the marked hang | Verdict | Action |
|---|---|---|
| delivered == GDI (and drive == GDI) | Emulator-side (texture cache) | Record in KB; **gate satisfied by exoneration** (Decision 2) |
| delivered ≠ GDI, drive == GDI | Our raw-ATA driver | Fix the shim driver |
| drive ≠ GDI | Flycast GD/IDE emulation | Fix-or-exonerate call, made on the evidence; port bytes are clean either way |

**Fix standard:** a fix must *explain the captured evidence* (root
cause, per systematic debugging), then survive the reproducing
scenario plus a soak. "Didn't happen again" alone cannot close a
1-in-6 intermittent.

### Exit of work item 1

Root cause named with captured evidence; either fixed-and-verified or
exonerated as emulator-side. Written up in the KB (new
`docs/kb/phase5-hardware.md`) before the first hardware boot.

## Work item 2 — hardware bring-up (after the gate clears)

Order of operations, each step a recorded round in
`docs/kb/phase5-hardware.md` with captures under `captures/phase5/`:

1. **On-screen shim HUD first.** Port Cleopatra's HUD (breadcrumb
   blocks, heartbeat, PC sampler) into the senkosp shim before the
   first hardware boot — the playbook is explicit: build observability
   before the blind boots, not after
   (`port-playbook.md` §Gotchas, on-screen observability). Diagnostic
   build flag; release GDI unchanged.
2. **Mastering per the playbook's trap list.** 2048-byte sectors, donor
   low-track structure, `dot_clean` (AppleDouble sidecars), boot binary
   in the last data track.
3. **Control test.** The known-good disc (Dolphin Blue) through the
   *same* SD card + GDEMU before theorizing about our artifact — one
   command that isolates "my bytes" from "the process".
4. **First senkosp boot**, then iterate debugging rounds. Budgeted as
   real work, not a formality (playbook, phase 5). DreamShell
   serial-SD is the secondary path when a GDEMU boot fails structurally
   or a serial debug channel is worth having.

Known hardware-only risks carried in (indexed, argued at their
citations): the MIE boot ladder runs for real on hardware where
Flycast's timing may have been generous (`phase4-conversion.md`
§Attract — 345 boot transactions); blocking pad-poll cost becomes real
wire time (§Work item 3); the `0x60000` BIOS-blob and low-RAM RTOS
kernel placements (`00-status.md` Phase 4 flags 1, 8) are now load-order
facts on a real BIOS boot; main-RAM watermark headroom is **91 bytes**
(`00-status.md`, Phase 3 headline) — the first number to suspect if
hardware behavior diverges under memory pressure.

## Work item 3 — fit & carried findings (on hardware)

- **Re-earn Phase 4's five play criteria on silicon:** attract, full
  1P match (approved pad layout, `docs/kb/input-map.md` §DC pad
  layout), 2P including mid-game join, test-menu round trip (combo
  boot → navigate → exit → reboot → attract), free-play (Start alone
  starts a match).
- **Pad-poll latency — reactive.** If hardware shows input lag or slow
  2P (Cleopatra's exact symptom), enable the staged TCNT0-keyed ~8 ms
  cache (`shims/src/main.c`, `#if 0`; writeup
  `phase4-conversion.md` §Steady input, finding 5) and re-test. If no
  lag: record the observation and leave the cache staged.
- **Cyan splash.** Observe on hardware first — it may not exist
  outside Flycast. Then diagnose (frame-stepped framebuffer capture
  across the boot window, in whichever environment shows it) far
  enough to *explain or reclassify* it. Cosmetic: the exit bar is an
  explanation, not necessarily a fix.

## Out of scope

- **VMU settings persistence** (Phase 4 finding 3) — deferred until
  after Phase 6's safety tripwires; the `mie_86` case `0x0b` choke
  point is the future plug-in site.
- Outside-tester distribution round.
- Asset cutting/compression (unchanged last resort, REQUIREMENTS.md).
- Fixing the Flycast fork's texture cache if exoneration lands there
  (recording the finding suffices; revisitable if emulator legs keep
  tripping on it).

## Exit criteria (the gate)

1. **Texture hang closed:** root cause named with captured
   instrumented evidence; fixed-and-verified or exonerated as
   emulator-side. KB writeup exists.
2. **The GDI boots on the bench DC + GDEMU to attract** (photo/video
   evidence in `docs/kb/img/`).
3. **Full 1P match on hardware** with the approved pad layout.
4. **2P match on hardware**, including mid-game join on port B.
5. **Test-menu round trip on hardware:** combo boot → navigate →
   `SYSTEM MENU EXIT` → reboot → attract.
6. **Free-play on hardware:** Start alone credits and starts.
7. **Pad-poll latency dispositioned:** no-lag observed and recorded,
   or the cache applied and verified.
8. **Cyan splash explained or reclassified**, with the hardware
   observation recorded.
9. **`docs/kb/phase5-hardware.md` written; `00-status.md` advanced to
   Phase 6.**

## Honest limit

Criteria 2–6 are operator-attested, on-screen, single-rig evidence —
one console, one GDEMU, one SD card. That is the phase's definition of
done; broader hardware coverage (other GDEMU firmware, other ODEs,
VGA/RGB variance) is explicitly not claimed. Phase 6 (safety tripwires
& release) still stands between this gate and anything shipped.

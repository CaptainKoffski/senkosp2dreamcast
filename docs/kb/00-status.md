# Project status

**Updated:** 2026-08-23 (Phase 4 Task 14 — **gate closed, all eight exit
criteria evidenced.** Criteria 1-5 (attract, 1P, 2P, test-menu round trip,
free-play) banked by the 2026-08-23 operator session (§Phase 4 checklist);
criterion 6 (VMU-safety static scan) closed this task with every literal
hit individually classified (82 + 1, three buckets, zero write-class finds
outside the already-patched-and-mirrored set); criterion 7 (clean-checkout
build) closed with a fresh `git clone` + documented gitignored inputs +
`make gdi` producing byte-identical disc tracks to the main checkout;
criterion 8 (this file, advanced to Phase 5) closed by this update. Phase
4 — **DONE**. Real hardware (Phase 5) is untested — see §Honest limit.)

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
  **Settled by Phase 3 (2026-08-22): relocation, not streaming retarget** —
  a four-word patch to two seed constants (one heap top, one VRAM size),
  proven by dry run on the Naomi profile. The fallback (shim-side streaming
  retarget + consumer-read patching) was not needed.
  `docs/kb/relocation-map.md`.
- Asset cutting/compression is a last resort (REQUIREMENTS.md).

## Phases

1. **Foundation — DONE 2026-08-13** (repo, KB, tooling records, .dat, boot verification)
2. **Instrumented analysis — DONE 2026-08-19** (streaming/input/memory ground truth; the high-address DMA map)
3. **Reverse engineering — DONE 2026-08-22** (touchpoint addresses; relocation strategy proven by dry run)
4. **Conversion — DONE 2026-08-23** (loader + shim + patch table → bootable GDI; gate green, all eight criteria)
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
- [x] `input-map.md` — 13/13 controls mapped (11 measured via JVS word
      bits — MIE sub=15 carried no per-press signal, see input-map.md
      §Why no MIE sub=15 — 2 source-derived: Coin/Test, masked out of the
      16-bit JVS log line — `maple_devs.h:97-98`). Exit criterion 3 met in
      substance (all 13 controls' wire bits established); the "MIE +
      JVS cross-check" phrasing in the original spec text does not hold —
      JVS is the sole measured channel.
- [x] Serial/RTC/watchdog verdicts in `phase2-measurements.md` §Device
      verdicts — all three: 0 pokes across all 14 legs.
- [x] Coverage checklist closed (`phase2-measurements.md`): full roster (8
      characters), all 8 stages, Novice mode, test menu (incl. EEPROM
      write-back), input leg.
- [x] Capture recipe in `tooling.md` §Phase 2 capture harness; this file
      advanced to Phase 3.

## Phase 3 checklist (gate — the six spec exit criteria, audited 2026-08-22)

Mirrors
`docs/superpowers/specs/2026-08-19-phase3-reverse-engineering-design.md`
§Exit criteria, one box per criterion, each with the file + line that earns
it. **Criteria 2 and 4 are `[~]`: met in substance, not literally** — each
row states exactly what is missing and what would close it. Criteria 1, 3, 5
and 6 are `[x]`, unqualified.

- [x] **1 — All nine targets answered** with static + dynamic evidence where
      runtime-reachable (RTC/SCIF/WDT static-only by nature).
      `docs/kb/boot-binary.md` §The nine targets — answer index: one row per
      target with address, static evidence, dynamic evidence and Phase 4
      implication. Targets 3/4 answered in `docs/kb/relocation-map.md`
      (§Provenance, §Patch set, §Dry-run evidence), cross-referenced not
      duplicated. Target 9 in `docs/kb/input-map.md` §DC pad layout.
      Two answers are partial **by evidence, and say so**: the EEPROM *write*
      call site (target 6 — observed 16×, PC unattributable by two
      independent probes) and the second stack's *extent* (target 7 — bounded
      to static BSS, not measured).
- [~] **2 — Parser cross-checks on the PC-capture leg: 10 of 11 PASS**
      (Phase 4 Task 4, 2026-08-22, same leg `captures/phase4/pc2.log` and the
      **same function ranges** as run C, with the Naomi-BIOS era excluded —
      `docs/kb/boot-binary.md` §Check lines, verbatim, **run D**. Was 7 of 10
      at run C; `shim_home_clean` is the eleventh line, added to the parser
      after run C was recorded).
      **What Task 4 found:** the "second, unidentified `trig=reg` call site"
      that run C blamed is the **Naomi BIOS**, running its own maple/JVS
      driver out of RAM before it loads the cart image over that RAM — every
      event of that PC family is pre-`MAINHANDOFF`, i.e. before the game's
      first instruction (`docs/kb/phase4-conversion.md` §R5;
      `docs/kb/boot-binary.md` §Addendum 2026-08-22 — Phase 4 Task 4).
      `input_pc_in_input_fn` and `eeprom_read_seen` were failing on BIOS
      traffic charged against a game-image range, so **both now PASS with no
      range widened** (`parse_cartlog.py --since-handoff`); `FUN_8c02532a`'s
      `0x8c02532a`–`0x8c025505` was correct all along.
      **Still `[~]`, one sub-check open: `eeprom_write_seen` FAILs on an
      empty set** — 0 sub-`0x0b` events in this unattended attract leg, and
      the only EEPROM writer this project has ever observed is the BIOS, so
      no game PC can satisfy it in this title. The pending operator
      test-menu leg exercises the *test image*, a different `.dat` entry, and
      is the remaining evidence that could change that.
      Historical detail from run C follows.
      `dest_known`, `len_aligned_32`, `beyond_boot_read`,
      `main_watermark_boot`, `no_bios_exec`, `dma_pc_in_cart_fn` — PASS
      (six lines, Phase 2/3 carry-overs), plus **`sp_consistent` now PASSes**
      on real measured evidence (below) — seven.
      **What Task 1 shipped and what it found:** the fork now tags every
      `maple_DoDma()` call with its trigger source (`trig=reg` guest
      `SB_MDST` store vs `trig=vbl` hardware vblank) and samples `r15` per
      transaction (`../flycast4naomi2dreamcast@0d55a1812`). Re-captured
      against `pc2.log` (boot→attract, ~300s): **every transaction is
      `trig=reg` — zero `trig=vbl` observed.** This *disproves* the theory
      below (`SB_MDTSEL==1`) that Phase 3 used to explain the three FAILs —
      the probe now exists and shows senkosp never arms the hardware
      trigger. `docs/kb/boot-binary.md` §Why three checks cannot pass as
      written and §SP — two stacks, not one both carry dated addenda with
      the full evidence.
      **PASS: `sp_consistent`** — now measured, not just statically bounded:
      per-PC-correlated `r15` samples put the confirmed input/EEPROM
      function (`FUN_8c02532a`) at a constant task-stack SP `0x8c1d4a1c`
      (≥ the `0x8c1c0000` floor) and the confirmed boot-time device-scan
      function inside the confirmed boot-stack region — both exactly where
      the static model predicted.
      **FAIL at run C, closed at run D: `input_pc_in_input_fn`,
      `eeprom_read_seen`** — run C explained them as "a second, real
      `trig=reg` call site (physical ≈`0x03161e`, function unidentified)
      issues genuine sub-`15`/`01`/`03` maple transactions outside
      `FUN_8c02532a`'s confirmed range, so the range — not the trigger — is
      what's incomplete." **Half right:** the call site is real and
      register-triggered, but it is the Naomi BIOS and the range was never
      incomplete (Task 4, above). `eeprom_write_seen` FAILed then and still
      FAILs, on zero sub-`0x0b` evidence in this unattended leg.
      The phase was never blocked on this, because every affected target has
      independent confirming evidence (input via sub `0x33`,
      `docs/kb/boot-binary.md` §Target: input function).
- [x] **3 — Dry run passes.** `docs/kb/relocation-map.md` §Dry-run evidence:
      three legs on `senkosp-reloc.dat` (`md5 a80f03676c0595bcae1bebcc5f16f884`),
      `parse_cartlog.py --dryrun` → **`exit=0`**, with
      `dryrun_main_below_16m`, `dryrun_vram_below_8m` and
      `dryrun_stream_shape` (205/205 `(src,len)` multiset match) all PASS —
      **re-run 2026-08-22 against the same three logs, `exit=0`, CHECK lines
      identical**; `scripts/test_parse_cartlog.py` → `ok`; the four patch
      `old` words re-verified in `senkosp.dat` and the artifact md5 re-checked.
      Operator-observed playability, in two dated parts: **2026-08-21** the
      operator played a full match on the patched image and reported it
      visually normal *with* a ~10 s stutter caveat (full quote:
      `relocation-map.md` §Operator playability report — its opening clause
      must not be quoted alone), and **2026-08-22** a single-variable control
      test (`FLYCAST_CARTLOG` unset → *"no lags anymore, all smooth"*) closed
      that caveat as **the instrument's own periodic scan** — the patch is
      exonerated.
- [~] **4 — Ghidra scripts re-run headlessly and reproduce — proven against
      the existing project DB, NOT yet from a fresh checkout.** Re-run
      2026-08-22 from the committed harness `scripts/ghidra/run.sh` and
      diffed mechanically: `FindMmioXrefs.java` → 73 payload lines identical
      to the previously reported output (`TOTAL hits=72`; per-block counts
      reproduce boot-binary.md's table exactly); `DumpEntryChain.java` → all
      35 instruction lines quoted in §Entry chain match, all three SP writes
      identical. Recipe + result: `docs/kb/tooling.md` §Phase 3: this repo's
      Ghidra project (incl. the `boot.bin` slice command and md5
      `07008ad629d628c519635dbc113487f5`).
      **The gap:** the spec says "re-run headlessly **from a fresh checkout**
      (given the gitignored ROM)". This re-run used the existing `senkosp3`
      DB, which carries Task 4's force-disassembly additions. The fresh path
      — `scripts/ghidra/run.sh import` then the same two scripts — is
      recorded but **untested**, and a fresh checkout has no reference copy
      of `tools/mmio-xrefs.txt` (gitignored) to diff against; it would
      regenerate it from the same script. Same one standard as criterion 2:
      met in substance, box not fully checked.
- [x] **5 — Control layout recorded.** `docs/kb/input-map.md` §DC pad layout
      (Phase 3, user-approved 2026-08-19) — table verbatim from the spec §9,
      plus the Coin (free-play) and Test/Service (Phase 4 loader decision)
      notes.
- [x] **6 — This file advanced to Phase 4** (below: key facts, Phase 4
      inputs, and the accumulated Phase 4 flags).

## Phase 4 checklist (gate — all eight spec exit criteria, audited 2026-08-23)

Mirrors
`docs/superpowers/specs/2026-08-22-phase4-conversion-design.md`
§Exit criteria, one box per criterion, each with the file + evidence that
earns it. All eight are `[x]`, unqualified — full detail and command output
for criteria 6/7 and the final verification leg:
`docs/kb/phase4-conversion.md` §Gate audit — criteria 6/7/8; criteria 1-5:
§Attract, §Steady input, §Test menu, §Operator legs.

- [x] **1 — The built GDI boots in Flycast's DC profile to attract.**
      `docs/kb/img/phase4-dc-attract.png` (Task 11, release configuration,
      unattended, `FLYCAST_SHOT`); 12,739 frames rendered, 8,353 large
      display lists, asset stream matches the Phase 2 Naomi attract capture,
      **zero** real maple DMA from any game PC, 345 boot transactions (the
      Naomi count exactly), 0 resets. `phase4-conversion.md` §Attract.
- [x] **2 — Full 1P match played with the approved pad layout.** Operator
      session 2026-08-23, leg `captures/phase4/play1.log`: every control
      exercised, free play confirmed (Start alone starts a match), dpad⊕
      analog mutual exclusion behaving. One intermittent finding carried to
      Phase 5, not blocking (§Findings for Phase 5 item 1 — texture-load-error
      hang, once in ~6 sessions). `phase4-conversion.md` §Operator legs →
      `play1`.
- [x] **3 — 2P match entry and play.** Leg `captures/phase4/play2p.log`:
      2P entry, play, and mid-game Start-join on port B all confirmed by the
      operator. `phase4-conversion.md` §Operator legs → `play2p`.
- [x] **4 — Test-menu round trip: combo boot → navigate → exit → reboot
      lands in a main boot.** Leg `captures/phase4/testmenu-rt.log`:
      A+Start combo boot → GAME TEST MENU (own on-screen instruction text
      confirms the Start/A → Test/Service convention) → navigation via the
      on-screen footer → controls test screen → difficulty changed → `SYSTEM
      MENU EXIT` → full console reboot (swirl) → attract. Session-only
      EEPROM is by design (§EEPROM — a RAM copy, session-only).
      `phase4-conversion.md` §Test menu, §Operator legs → `testmenu-rt`.
- [x] **5 — Free-play: Start alone credits and starts.** Confirmed on-screen
      (`FREE PLAY` + `PRESS 1P OR 2P START BUTTON`,
      `docs/kb/img/phase4-dc-steady.png`) and by the operator's own 1P/2P
      sessions (Start alone starts a match, no coin needed). Coin byte `[9] =
      0x1a` = setting 27 (free-play), two independent layout sources, CRC
      valid. `phase4-conversion.md` §FREE PLAY — the evidence chain.
- [x] **6 — VMU-safety preview: the static maple-literal scan runs clean.**
      `python3 scripts/test_maple_literals.py` → `exit=0`. Every literal hit
      (82 in `senkosp.dat` + 1 in `build/bios_data.bin`) individually
      classified into three justified buckets (36 already-patched
      maple-mirror words, 4 entries in a read-only SDK exception-dump table
      — Ghidra-confirmed, not a maple-frame builder — + its 1 BIOS-blob
      twin, 42 streamed-asset statistical noise). Zero write-class literals
      found outside the already-patched set. Loader objects (`main.o`/
      `handoff.o`) gate the build unconditionally: zero unclassified vmu/
      maple references. `phase4-conversion.md` §Gate audit → Criterion 6.
- [x] **7 — One-command reproducible build (`make gdi`) from a clean
      checkout plus gitignored ROM/BIOS.** Fresh `git clone -b
      phase4-conversion` + the six gitignored inputs `tooling.md` documents
      (`senkosp.dat`, `bios/naomi/epr-21576h.ic27`, `tools/ram-snapshot.bin`,
      the GDI donor 7z, `loader/splash.png`, `captures/phase4/pc2.log`) +
      `source ../cleopatra/tools/kos/environ.sh && make gdi` → `exit=0`,
      first attempt once inputs were supplied. All five produced disc files
      (`track01-04`, `disc.gdi`) md5-identical to the main checkout's build.
      `phase4-conversion.md` §Gate audit → Criterion 7.
- [x] **8 — This file advanced to Phase 5, honest limit carried verbatim**
      (below, §Honest limit, and the phase list above).

### Honest limit (spec, verbatim)

> Real hardware is Phase 5; the honest limit from Phase 3 carries forward
> verbatim — emulator-green proves nothing about real hardware.

Every criterion above is proven in Flycast's DC profile. None of it has run
on a real Dreamcast + GDEMU-class ODE yet. Two findings already flag the
kind of gap only real hardware can expose or close: the unthrottled
blocking pad-poll latency (free in Flycast, real time on the wire — remedy
already sitting `#if 0`'d, `phase4-conversion.md` §Steady input finding 5)
and the once-observed texture-load-error hang (intermittent, uncharacterized
root cause). Full Phase 5 findings list: `phase4-conversion.md` §Findings
for Phase 5.

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
  new vs Cleopatra — 3 MMIO refs; **Phase 3 found 5**, and closed the flag:
  `docs/kb/boot-binary.md` §RTC / SCIF / watchdog).
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
    **Retracted (Phase 3, Task 4):** the "0 pokes" half is a null instrument
    — the probe emitting those lines is gated on `FLYCAST_HWLOG`, which
    `scripts/capture_leg.sh:16` never sets, so no leg could have recorded a
    poke to any address. Devices were re-decided statically instead
    (all three: **ignore, no shim**); the RTC is in fact read on a live
    periodic tick. See `docs/kb/phase2-measurements.md` §Device verdicts
    correction and `docs/kb/boot-binary.md` §RTC / SCIF / watchdog. The
    EEPROM row is unaffected (`MIERESP` is a separate, always-on probe).
  - Input map: 13/13 controls mapped (`docs/kb/input-map.md`).
- **Phase 3 headline findings (2026-08-22, gate evidence —
  `docs/kb/boot-binary.md`, `docs/kb/relocation-map.md`):**
  - **The patch set is four words** (`scripts/reloc_patchset.json`), applied
    by `scripts/apply_reloc.py`:
    | `dat_offset` | old → new | What it does |
    |---|---|---|
    | `0x65b50` | `0x4028cb8e` → `0x4028cb8d` | Main image `0x8c085b50`: heap-top seed `0x8e000000` → `0x8d000000`. Moves **all five above-16m corridors** at once. |
    | `0x1af894` | `0x4028cb8e` → `0x4028cb8d` | Test image: verbatim copy of the same seed, so test mode uses the same 16 MB heap top. |
    | `0x1203c` | `0x01000000` → `0x00800000` | Main image `0x8c03203c`: kmInitDevice's VRAM-size seed 16 MB → 8 MB. Moves **every above-8m VRAM placement**. |
    | `0x183bb4` | `0x01000000` → `0x00800000` | Test image: same VRAM-size seed for the service/test menu. |
    Every `dat_offset` is a **raw `.dat` offset**; for boot-image entries
    that happens to equal `P1 − 0x8c020000`, since the boot image starts at
    `.dat` offset 0.
  - **Corridor provenance: one site, not five.** No corridor destination
    exists as a constant anywhere (exhaustive scans over boot image and the
    251 MB `.dat`). All five are **computed by the game's single syMalloc
    heap**, created once in `FUN_8c085b00` as `[0x8c1de200, 0x8e000000)`;
    the allocator carves block *tails*, so the whole layout shifts rigidly
    by `−0x1000000` and all 24 low bits of every buffer are preserved.
  - **VRAM provenance: one cell.** senkosp runs **KAMUI2** (NEC) in 16 MB
    Naomi VRAM mode; `kmInitDevice` writes the total-VRAM-size word, and
    every above-8m placement (scan-out FB pair `0x800000`/`0xc00000`,
    texture arena limit) derives from it. Flipping the seed makes the
    library take its **native DC 8 MB paths, which already ship in the
    binary**.
  - **Devices: RTC, SCIF, watchdog — all three ignore, no shim** (decided
    statically; Phase 2's "0 runtime pokes" was a null instrument and is
    retracted above). WDT has **0 refs**; SCIF is one boot-path pin write +
    an exception-vector crash console; RTC is 5 words / 5 functions — 2 live
    readers on a periodic tick, 3 writers behind an **unreferenced** setter,
    all targeting a register the DC has.
  - **SP: no patch needed.** Final SP `0x8c00f000` (phys `0x0c00f000`), 60 KB
    above the bottom of RAM — the classic "SP near 32 MB" Naomi→DC patch does
    not apply. Recorded anyway as a one-constant site (`0x8c170c14`) if it is
    ever needed.
  - **senkosp is multi-stack.** The boot stack is confirmed
    (`0x8c000000`–`0x8c00f000`, 118 SP samples); 554 samples sit at
    `0x8c1d4984` — a task stack, bounded to static BSS (ends `0x8c1de200`),
    so no free-space reservation beyond BSS is needed.
  - **Dry-run headline:** the caps held through boot, attract and a full
    played match on the Naomi profile — `dryrun_main_below_16m`,
    `dryrun_vram_below_8m`, `dryrun_stream_shape` green, `exit=0`, and the
    operator confirmed normal play. Measured margins: **~680 KB VRAM
    headroom** at the match peak (`content_high 0x756120` vs the 8 MB cap =
    696,032 B free) and **~410 KB main-heap slack** (capacity 14,818,816 B vs
    the 14-leg peak reservation 14,398,432 B = 420,384 B). Main-RAM
    watermark headroom at peak is only **91 B** — expected, the shift is
    rigid and the highest allocation was already flush against the old
    32 MB top.
  - **Honest limit (spec, verbatim):** the dry run proves the *game tolerates
    relocation* on Naomi emulation. It proves nothing about DC behavior —
    that is Phases 4–5.

## Next step

**Phase 5 — real-hardware testing & fit.** Phase 4 (loader + shim + patch
table → bootable GDI) is **DONE 2026-08-23** — gate green, all eight exit
criteria evidenced (§Phase 4 checklist above). Everything below this line is
the Phase 4 build narrative, kept for its citations. Phase 5's spec and plan
landed 2026-08-23 (`docs/superpowers/specs/2026-08-23-phase5-hardware-design.md`,
`docs/superpowers/plans/2026-08-23-phase5-hardware.md`); results go in
`docs/kb/phase5-hardware.md`. Starting inputs for Phase 5: the shipped disc (`build/disc.gdi`,
reproducible from a clean checkout — criterion 7), the Phase 4 findings list
carried forward (`docs/kb/phase4-conversion.md` §Findings for Phase 5 — pad-
poll latency, the texture-load-error hang, the cyan splash, the VMU-settings
feature request), and the honest limit above: none of Phase 4's evidence has
touched real silicon.

**Phase 5 progress — the texture-error hang gate (Work item 1).** Wave A is
done: the delivered/drive CRC instrument verifies clean on every DC-profile
leg run so far, the hang was reproduced **unattended and deterministically**
(two independent legs are byte-identical for 319,549 cartlog lines up to the
marker), and a savestate was captured at the hang.

**Gate status: verdict named, gate NOT closed — a fix is required.**
Task 7's savestate forensics classify the captured occurrence as **T1 — VRAM
texture-arena exhaustion** (`docs/kb/phase5-hardware.md` §Texture-error hang
verdict). That is the brief's **verdict 2: our fit bug**, not exoneration.
Headline numbers, all read out of the RAM image at the hang: the KAMUI2
bank-0 arena is exactly 8,388,608 B (the patched 8 MB seed, confirmed live at
`0x8c19ecb4`), 8,244,256 B allocated across 87 blocks with **zero gaps**, one
free block of **144,352 B** — against a **264,192 B** request for a 1024×1024
VQ texture. **Short by at least 119,840 B (117 KB)**; short by at least
384,032 B to place the rest of that one `TXTR` chunk. **Both figures are
floors, not the scene's peak demand** — nothing downstream of the failure
ran (the game parked in its error loop), so a fix sized at 384 KB is shown to
be *necessary*, not sufficient; sizing one needs a fresh high-water
measurement. Not fragmentation (no gaps), not a leak (the previous
scene's surfaces were released — live count fell 102 → 84), not the bytes
(both CRC streams PASS *and* the failing asset is byte-identical to
`senkosp.dat` over its full `0x40820` B), not a bad header (all three of
`FUN_8c03ea1c`'s error branches individually excluded by observed cells).

This also revises the §Dry-run headline above: the arena high-water at the
hang (`0x7dcc20`) is **551,680 B above** the Phase 3 campaign's measured peak
`content_high 0x756120`, so the "~680 KB VRAM headroom" figure did not bound
the game's true peak demand. `dryrun_vram_below_8m` stays green as a record of
what those 14 legs measured; it is no longer evidence that the 8 MB budget
fits.

**Next action: fix scope is a user decision** — Task 7 stops at the verdict by
its own hard boundary and designs nothing. Hardware rounds stay blocked until
the fix lands and the spec's re-verification bar is met. Phase is **not**
advanced.

**Fix decision resolved — config F-2 built (2026-08-26).** The fix went
through four generations: the option-2 stage-texture shrink (Tasks
15–17, A/B-gated), the Ghidra + savestate recon that found the real
payload (character PKTX portrait raws resident all match,
`docs/kb/phase5-hardware.md` §Ghidra + savestate recon), config
**F-zero** (all portrait sheets → VQ) — built, its VS leg technically
PASS and the source of the measured Ernula-mirror baseline (peak
7,685,120), then **rejected at the art gate** (cockpit VQ unacceptable;
operator rule: never compress textures with text), and the operator's
final choice **F-2** (`docs/kb/arena-fit-options.md` §7): 48 pilot
cut-ins + 2 ring sheets → same-size VQ, one STAGE08 hero (**0b736ff0**,
operator-amended from 0b6f67d0) → tuned 512², cockpits/MODESEL/COMMON
and every text sheet untouched. Margin 312,320 B at the worst measured
transition. Built and mastered (`phase5-hardware.md` §F-2 build).

**Task 18 verification suite — COMPLETE, all PASS (2026-08-27).** Leg 1
operator VS/mirror (peak 7,718,528, +4,736 over prediction), splash
question resolved (FONT text, untouched), leg 2 unattended 30.1-min
attract soak (3 stage-8 demos, peak 7,448,928), leg 3 operator 1P
campaign to the ending (two sessions, easy-difficulty leg build md5
`ec3dba3c…`; boss beaten, END2 + credits watched; campaign peak
7,305,536; ending stretch set no new high-water above 5,339,424 — no
END-overlap hazard; disc has only END1/END2, no END3/END4).
STAGE09/P09/P10 never load on any exercised path (attract, VS, full
campaign incl. ending) — unreachable in observed play, no fit exposure.
Every leg: TEXERR clean, CRC 0 mismatches. Shipping build re-mastered
byte-identical after the leg (`b056f460…`). **The emulator-side fix
gate is closed; hardware rounds (Tasks 9–13) are unblocked.** Evidence:
`phase5-hardware.md` §Task 18.

**Historical: Phase 4 build narrative (Tasks 1–13, superseded framing below
kept for citations).** Spec + plan: `docs/superpowers/specs/` and `plans/`.

**State as of Task 11 (2026-08-22): the game reaches ATTRACT on the DC
profile — gate criterion 1.** Every maple register constant in both images is
repointed into the shim's RAM mirror, the boot driver's five kick+poll windows
are detoured into a register-preserving trampoline, and the steady engine's
one fn-ptr pool word (MAPLE-KICK-HOOK) routes its kick to the same service.
The shim replays the MIE's Z80 firmware-upload ladder (345 transactions, the
Naomi count exactly), answers the JVS I/O-board enumeration from senkosp's own
captured replies, and the game's per-frame input poll (MIE sub 0x33) runs — so
the `I/O BD IS NOT CONNECTED` / `DOES NOT FULFILL THE GAME SPECS` gate passes
and never fires again. In the release configuration the game renders 12,739
frames with 8,353 large display lists and streams attract assets whose
`(offset, length)` pairs match the Phase 2 Naomi attract capture, with **zero**
real maple DMA from any game PC — and the attract DEMONSTRATION on screen,
`docs/kb/img/phase4-dc-attract.png` (headless framebuffer grab, unattended
leg). Evidence: `docs/kb/phase4-conversion.md` §Attract, legs
`captures/phase4/attract*`.

**State as of Task 12 (2026-08-22): the DC pads are wired into the game's
JVS input, and free play is baked.** The steady sub-`0x33` poll no longer
replays a captured idle frame — the shim runs its own GetCondition on maple
ports A and B every poll, normalizes the reply (buttons inverted, R trigger
thresholded at 128, analog stick folded into the D-pad), maps it through
`dc_to_jvs`, writes the two player words at the pinned frame offsets and
recomputes the JVS checksum. The EEPROM is served from a RAM copy that accepts
the game's own sub-`0x0b` writes (session-only). Proven unattended: the built
idle frame is **byte-identical to the captured idle frame** (asserted at build
time, and confirmed live — `crc=0x22`), attract cycles unchanged, 13,283
GetConditions per port with every reply `DATATRF` and zero retries, and still
**zero** real maple DMA from any game PC. Free play is evidenced by the coin
byte (image `[9] = 0x1a` = coin assignment #27, two independent layout sources),
a CRC that validates, and `FREE PLAY` on the target's own screen
(`docs/kb/img/phase4-dc-steady.png`). Evidence:
`docs/kb/phase4-conversion.md` §Steady input, legs `captures/phase4/steady*`.

**State as of Task 13 (2026-08-22): the test image's boot combo, input
mapping and menu render are proven unattended; the round trip itself needs
the operator (gate criterion 4).** `SHIM_STATE[0]` (seeded by Task 10's boot
combo) now gates a P1-only remap in `mie_poll`: DC Start → Test (frame
`+0x1f` bit 7, its own byte per §TESTBIT-INJECT — not folded into the 16-bit
button word) and DC A → Service (`0x4000`, genuinely a word bit); every other
control, and P2 entirely, keep their live `dc_to_jvs()` mapping, so the
normal-mode code path is byte-for-byte what Task 12 shipped. A completeness
audit against §Cart-patch sites / §Maple-patch sites found both images' test
columns already fully dispositioned (32/32, 20/20) and RESET-PATCH's test
entry (dat `0x1a4678`) already wired (Task 10) — no generator changes were
needed. A transient diagnostic build (`LOADER_FORCE_TEST_BOOT=1`, reverted
before commit, same precedent as `LOADER_SERIAL`) forced the test-image path
with no operator: the loader selected and patched the TEST image (`patch
table: … applied: test`), the game reached its steady MIE poll under
`SHIM_STATE[0]==1`, and the on-screen result is senkosp's own **GAME TEST
MENU**, its own instruction line reading `SELECT WITH SERVICE BUTTON AND
PRESS TEST BUTTON` — independent, in-game confirmation of the exact
Start/A → Test/Service convention this task wired. 12,982 frames rendered,
6,492 GetConditions per port (equal, zero retries), 0 resets, 0 tripwires.
A same-session regression leg with the identical diagnostic shim but a
normal (no-combo) boot reproduced Task 12's exact idle evidence
(`crc=0x22`, 345 boot transactions, 0 tripwires, all post-handoff maple DMA
from shim PCs only). Evidence: `docs/kb/phase4-conversion.md` §Test menu,
legs `captures/phase4/teststatic1`, `captures/phase4/testboot-diag1`,
`docs/kb/img/phase4-dc-testmenu.png`.

**Closed 2026-08-23 (was "pending — needs the operator," criteria 2, 3, 4,
5):** the operator session ran the 1P playtest, the 2P leg on port B, and
the criterion-4 round trip (combo boot → test menu → `SYSTEM MENU EXIT` →
reboot → attract) — all four banked, see §Phase 4 checklist above and
`docs/kb/phase4-conversion.md` §Operator legs.

**State as of Task 10 (2026-08-22): senkosp's own code runs on a Dreamcast
and streams from the disc.** The loader stages everything high and a
copy-record handoff places the shim, the Naomi kernel slice, the 0x60000 BIOS
blob and the patched image; the game boots, enables its own MMU, initialises
video, and performs 26 cart streams per boot through the shim's G1-register
mirror + raw-ATA driver — destinations landing in the relocated (sub-16 MB)
corridors, i.e. the relocation seeds work at runtime. It then hits its own
Naomi fatal error, `I/O BD IS NOT CONNECTED TO NAOMI BD.`, and restarts,
because nothing maple-side is patched yet. Evidence:
`docs/kb/phase4-conversion.md` §Integration v1, legs
`captures/phase4/entry2`–`entry4`.

That error message is exactly what Task 11's MAPLE-BASE repoint, kick hook and
five boot detours eliminated (see the Task 11 state above).

### Direct inputs (everything Phase 4 needs, all produced by Phase 3)

- **`docs/kb/boot-binary.md`** — start with §The nine targets — answer index;
  it names every address Phase 4 patches or hooks, with its static and
  dynamic evidence and its Phase 4 implication.
- **`docs/kb/relocation-map.md`** — the relocation strategy: provenance, the
  below-cap free-space layout, what is deliberately *not* patched (with
  reasons), and the dry-run evidence.
- **`scripts/reloc_patchset.json`** + `scripts/apply_reloc.py` — the four-word
  patch set, applied deterministically; `senkosp-reloc.dat` is regenerable
  and gitignored (md5 `a80f03676c0595bcae1bebcc5f16f884`).
- **`docs/kb/input-map.md`** §DC pad layout — the user-approved control
  binding, plus the 13/13 wire bits behind it.
- **`docs/kb/tooling.md`** — Ghidra project + `boot.bin` slice, the capture
  harness, the RAM-snapshot recipe, the dry-run recipe, the capture-file
  inventory.

### Phase 4 flags (accumulated across Phase 3 — read before designing the loader)

Each is argued where it is cited; this is the index, not the argument.

1. **The `0x60000` BIOS blob is executed at runtime — the loader must place
   it.** `FUN_8c065ff0` checks an 8-pointer vector table at Naomi BIOS phys
   `0x00060000` and copies **28,672 B** to phys `0x0c018000`; the leg caught
   the guest executing inside the copy (`PCSAMPLE pc=0c018b4a`). On DC the
   signature fails and nothing is copied, but the dispatch pointer
   (`0x8c1bf42c`) is installed regardless → jump into uninitialized RAM.
   Place the blob from the user's own BIOS dump at load time (**never commit
   those bytes**) or reimplement the 8 vectors.
   `boot-binary.md` §The two BIOS-ROM data reads.
2. **The restart path jumps into Naomi BIOS.** The reset stub `FUN_8c067e18`
   (runs on test-menu exit) copies itself to `0xadfff000` and ends by jumping
   to BIOS code (`0xa0082262` &c.). Shifting constants cannot fix it — Phase 4
   must **own restart** (intercept the stub or replace the jump with a loader
   re-entry). `relocation-map.md` §Deliberately not patched.
3. **The reset stub's top-page writes land at `0x0cfff000` on DC** — inside
   the patched heap's top page. Acceptable only because that path is a reboot
   anyway; the loader design must not assume the top page survives. Same
   source as (2).
4. **A dead-code RTC *setter* exists** (`0x8c029b04`, unreferenced, plus its
   three leaf writers). If it is ever reached it writes the **Dreamcast's own
   AICA RTC** — i.e. sets the console clock. Not a blocker, not something to
   shim; know it before calling an RTC store a stray write.
   `boot-binary.md` §RTC / SCIF / watchdog.
5. **The DC BIOS syscall vector block overlaps the game's stack region.**
   Vectors at `0x8c0000b0`–`0x8c0000e0`, SYSINFO `0x8c001010`, GD entrypoint
   `0x8c0010f0` all sit inside `0x8c000000`–`0x8c00f000`. Harmless once the
   game owns the machine; **only matters if the loader/shim needs GD-ROM
   syscalls after the game's SP init** — do that work earlier, or move the
   stack with the one-constant patch. `boot-binary.md` §Phase 4 note.
6. **`FB_W_SOF2`'s `0xc00000` is a never-written BIOS default**, not a game
   placement — written once per leg from `was=00000000`, identical patched
   and unpatched. The dry-run gate exempts exactly that cell, narrowly.
   Don't chase it as a VRAM leak. `relocation-map.md` §FB_W_SOF2 exemption.
7. **`dat_offset` is uniformly a raw `.dat` offset** — all four entries. The
   boot-image ones merely *coincide* with `P1 − 0x8c020000` because the boot
   image sits at `.dat` offset 0 (checked: `0x8c085b50 − 0x8c020000` =
   `0x65b50`, `0x8c03203c − 0x8c020000` = `0x1203c`). A Phase 4 patch table
   can use one raw-offset schema; only the *derivation* of a boot-image
   address from its P1 form needs the subtraction.
   `relocation-map.md` §Patch set.
8. **Low RAM is the Naomi BIOS's resident RTOS kernel.**
   `0x0c000600`–`0x0c007xxx` is byte-identical to the BIOS ROM at ROM
   offset − `0x800` (VBR+0x600 stub, INTEVT dispatcher `0x0c001cba`, 0x200-byte
   TCBs at `0x0c004000`) and is **not** in `senkosp.dat`. The game runs its
   tasks under that kernel — which is also why so many sampled PCs render in
   P0 form. The loader must account for it alongside flag (1).
   `tooling.md` §Phase 3: RAM snapshot.
9. **The input shim must serve maple sub `0x33`**, the per-frame
   receive-then-transmit poll (80 392 events) — **not** sub `0x15`, which is
   the boot-phase subcommand. `boot-binary.md` §Target: input function.
10. **The EEPROM *write* call site is unknown**, and free-play forcing must
    therefore filter by **subcommand** in the shim rather than patch a call
    site. Naming it needs a one-line fork change (tag which caller reached
    `maple_DoDma()`); the same change plus an `r15` water-mark probe is what
    would turn the four FAILing parser checks green.
    `boot-binary.md` §Why three checks cannot pass as written.

### Out of scope for Phase 4 (unchanged)

Real hardware is Phase 5. ARAM fits (u 0.643, confirmed) and asset cutting is
not triggered — all content fits as volume.

# Project status

**Updated:** 2026-08-22 (Phase 3 Reverse Engineering — DONE; gate green with
**two** criteria met in substance rather than literally — 2 and 4, see the
Phase 3 checklist)

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
- [~] **2 — Parser cross-checks on the PC-capture leg: 7 of 10 PASS**
      (Phase 4 Task 1, 2026-08-22, re-run against `captures/phase4/pc2.log`
      with the trig=/sp=-tagged fork — `docs/kb/boot-binary.md` §Check lines,
      verbatim, run C).
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
      **Still FAIL: `input_pc_in_input_fn`, `eeprom_read_seen`,
      `eeprom_write_seen`** — for a *different, newly precise* reason than
      Phase 3 recorded: a second, real `trig=reg` call site (physical
      ≈`0x03161e`, function unidentified) issues genuine sub-`15`/`01`/`03`
      maple transactions outside `FUN_8c02532a`'s confirmed range, so the
      range — not the trigger — is what's incomplete. `eeprom_write_seen`
      additionally has zero sub-`0x0b` evidence in this unattended leg
      (attract-mode never touches the EEPROM).
      **What would close it now:** static (Ghidra) identification of the
      `0x03161e`-region function, plus a repeat operator test-menu leg to
      re-observe the EEPROM write under the trig-tagged fork. Both are
      follow-up work, out of Task 1's fork-probe scope. Carried as a Phase 4
      flag; the phase is not blocked on it because every affected target has
      independent confirming evidence (input via sub `0x33`, `docs/kb/boot-binary.md`
      §Target: input function).
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

**Phase 4 — conversion** (loader + shim + patch table → bootable GDI).
Brainstorm + spec first (superpowers loop, per the playbook cadence:
`docs/kb/port-playbook.md`), then a plan, then implementation behind the
gate.

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

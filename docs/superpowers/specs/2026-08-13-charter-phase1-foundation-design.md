# Senko no Ronde Special → Dreamcast: project charter + Phase 1 Foundation spec

Approved 2026-08-13. Two parts: a project-level charter (goals, method,
risks — stable across the whole port) and the full spec for Phase 1
(Foundation), the first sub-project. Later phases get their own specs when
reached, per the working cadence below.

## Part A — Project charter

### Goal

Port *Senko no Ronde Special* (`senkosp`, Naomi GD-ROM GDL-0038, G.Rev 2006)
to Sega Dreamcast as a static binary conversion: patch the Naomi-specific
hardware touchpoints in the game binary (DIMM/cart reads → GD-ROM streaming,
MIE/JVS input → Maple controllers, EEPROM/settings → native-path stubs,
free-play baked in) and boot it from a GDI via a custom loader.

**Done means:** fully playable on a real Dreamcast via a GDEMU-class ODE,
arcade-identical behavior, VMU-safety tripwires pass, the pipeline is
reproducible from the KB, and findings are documented well enough that a
human or future agent can retrace the port. The emulator is a dev tool,
never the target.

### Method

The six-phase playbook distilled from the Cleopatra Fortune Plus port
(`../cleopatra/docs/kb/port-playbook.md`), gates enforced — a phase does not
start until the previous gate is green. Working cadence: the superpowers
loop (brainstorm → spec, writing-plans → plan, then execute) runs **per
phase**, as it did for Cleopatra.

| Phase | Gate | Senkosp-specific notes |
|---|---|---|
| 1. Foundation | Untouched game boots in Flycast (naomigd profile) | `.dat` from CHD via `../naomi2dreamcast/tools/dat-extract`; KB skeleton; tooling recorded. Spec: Part B below |
| 2. Instrumented analysis | Streaming/input/memory ground truth from real traces | Focus: the cart-DMA destination map above 16 MB (the relocation problem); capture gameplay, not just attract |
| 3. Reverse engineering | Every hardware touchpoint has an exact address + patch plan | Entry chain (carve base `0x8c020000`, entry `0x8c021000` per assessment); relocation strategy decided here |
| 4. Conversion | Boots + playable in Flycast DC profile | Loader/shim/patch-table architecture reused from Cleopatra; 237.7 MB of GD data on disc |
| 5. Hardware test & fit | Boots + plays on real DC | Expect Cleopatra's four real-HW-only divergence classes (MMU, D-cache, G1 regs, BIOS-GD state) from day one |
| 6. Safety tripwires & release | All three VMU tripwires PASS on the release candidate | Reuse Cleopatra's `test_maple_literals.py` / `test_vmu_untouched.sh` method + baselines |

Approaches rejected at charter level, both for cause during Cleopatra:
a trap-based generic Naomi runtime (Naomi cart registers share hardware
addresses with the DC GD-ROM ATA registers — indistinguishable on real HW)
and asset-extraction/engine-reimplementation (no source; 4,012 functions;
out of all proportion).

### Senkosp-specific risks (watch list)

Source: `../naomi2dreamcast/assessments/senkosp.md` (91.0 S, capture v9,
2026-08-09).

- **Main-RAM placement** — the central technical problem. Cart-DMA
  high-water 33,453,344 (33.4 MB) vs DC's 16 MB; nonzero content is only
  5.85 MB, so it fits, but DMA destinations above the 16 MB line must be
  relocated or their streams retargeted. Phase 2 measures exactly which
  destinations; Phase 3 decides relocation vs streaming-tweak per stream.
- **VRAM placement** — address extent 11.9 MB vs the 8 MB cap; content
  4.79 MB (FB-masked + double framebuffer) fits. The high-parked asset
  store must move.
- **ARAM** — content 1.35 MB / 2 MB cap, address peak 16 B under the cap:
  expected to fit as-is; verify in Phase 2.
- **GD-ROM/DIMM origin** — unlike Cleopatra's ~109 MB cart, the "cart" is
  a DIMM-RAM image sourced from a 237.7 MB GD-ROM. `.dat` extraction and
  boot-flow differences are handled by the naomi2dreamcast toolset; the
  streamed volume is larger but measured modest (26.6 MiB per 600 s
  attract, steady 2.3 MB/min).
- **Controls** — stick + 5 buttons (M/S/A + Barrage/C + OverDrive) → DC
  pad's 6 inputs, one to spare. Layout decision deferred to Phase 3/4;
  the X360 Rev.X pad mapping is prior art.
- **Assessment guts flags** `eeprom_bios`, `serial`, `rtc` — expect the
  same BIOS-thunk EEPROM traps Cleopatra hit (19 unpatched `0x5f7xxx`
  literals inside the Naomi BIOS library was its longest hunt); `serial`
  echoes Cleopatra's per-frame SCIF cost on real HW; **RTC (3 MMIO refs)
  is new vs Cleopatra** — needs a Phase 3 look.

### Assumptions

- Real Dreamcast + GDEMU-class ODE available for Phase 5 (same rig as
  Cleopatra, both cable types).
- Sibling repos stay in place and are referenced: `../cleopatra` (KB +
  reusable code), `../naomi2dreamcast` (assessment + dat tools),
  `../flycast4naomi2dreamcast` (instrumented emulator). Code is copied
  into this repo only when a phase needs it, not wholesale.
- No netplay/online features — arcade behavior only.
- The set we have (export/English, PIC `317-5123-COM`) is the set we ship
  for.
- Asset cutting/compression is a last resort, per REQUIREMENTS.md — the
  assessment says memory reallocation / streaming tweaks should suffice.

### Rules

- Never commit copyrighted bytes: ROM, BIOS, disc images, `.dat`,
  extracted assets stay gitignored. Ship method, tools, patches.
- Every hardware/behavioral claim carries a citation; primary sources
  (emulator/kernel/library source) outrank wikis and forums.
- Every tool install is recorded (version, flags, exact steps) in
  `docs/kb/tooling.md`.
- All findings and solutions land in `docs/kb/` — the KB must let a human
  or a fresh agent reconstruct how the port was done.

## Part B — Phase 1: Foundation spec

### Purpose

Stand up the repo so every later phase has its infrastructure: knowledge
base, verified toolchain, the ROM in workable form, and proof the untouched
game runs. Produces no game modifications.

### Deliverables

1. **Repo scaffolding.**
   - `CLAUDE.md`: project orientation — what this is, current state
     pointer (`docs/kb/00-status.md`), sibling-repo map, rules.
   - Hardened `.gitignore`: `roms/`, `bios/`, `*.dat`, `*.chd`, `*.gdi`,
     `*.iso`, `.DS_Store`, `._*` (the copyright rule enforced
     structurally; AppleDouble sidecars were a real Cleopatra boot bug).
   - `docs/kb/` skeleton: `00-status.md` (living status, Cleopatra-style),
     `game.md` (senkosp identity + parsed header facts), `tooling.md`
     (install records).
   - `port-playbook.md` copied from Cleopatra into `docs/kb/` — it was
     written to be carried to the next port's repo.
2. **Toolchain verified and recorded** in `tooling.md`:
   - Flycast fork (`../flycast4naomi2dreamcast`): build it on this
     machine, record commit hash + exact build steps.
   - Ghidra 12.1.2 (installed during Cleopatra): record the reuse.
   - MAME reference checkout: not installed in Phase 1; record it in
     `tooling.md` when a later phase first uses it (assessment cites
     `59e7c0b`).
   - dat-extract toolset: record location + invocation.
3. **`.dat` extraction.** Run
   `../naomi2dreamcast/tools/dat-extract/chd2dat.sh` on
   `roms/senkosp/gdl-0038.chd` → `senkosp.dat` (gitignored). Sanity-check
   the carve against the assessment's ground truth: header title
   `SENKO NO RONDE SP`, carve base `0x8c020000`, entry `0x8c021000`.
   Record the exact commands in `tooling.md`.
4. **Boot verification — the gate.** The untouched game boots in the
   Flycast fork's Naomi GD profile and reaches attract/demo; screenshot
   evidence goes into the KB. If it will not boot, control-test a
   known-good title through the same profile before theorizing about our
   setup (playbook gotcha #2).
5. **Exit audit + fresh-agent test.** A clean-context agent must identify
   the project, its state, and the next step from `CLAUDE.md` +
   `00-status.md` alone (Cleopatra Phase 1 exit criterion).

### Out of scope

Any patching, any reverse engineering beyond the header/carve sanity
check, disc mastering, and Flycast instrumentation work (Phase 2 owns
that).

### Gate to Phase 2

Untouched game runs in the arcade profile (screenshot in KB) + toolchain
recorded + `.dat` carve verified.

# Port playbook — Naomi/Atomiswave → Dreamcast

Forward-looking distillation of the *Cleopatra Fortune Plus* port: how to do
the **next** static binary conversion with fewer re-learned mistakes. The rest
of `docs/kb/` is the *record* of this port (chronological, game-specific); this
is the *method* (ordered, reusable). Bring this file to the next port's repo.

> Carried into `senkosp2dreamcast` 2026-08-13 from
> `../cleopatra/docs/kb/port-playbook.md` (verbatim below this note).
> Deep-reference paths like `atomiswave-method.md` refer to
> `../cleopatra/docs/kb/`.

Deeper references, cited throughout: `atomiswave-method.md` (technique
catalog), `naomi-vs-dreamcast.md` (hardware deltas), `tooling.md` (install
recipes), `boot-binary.md` (RE findings).

## The method — do it in this order

Each phase produces something the next one spends, and has a go/no-go gate.
Don't start a phase until the previous gate is green.

1. **Foundation.** Repo, KB skeleton, toolchain installed and *recorded*
   (`tooling.md`), and a plain unmodified boot verified in-emulator.
   *Gate:* the untouched game runs in the emulator's arcade profile.
2. **Instrumented analysis.** Build an instrumented emulator (see
   `tooling.md` → Flycast source build) and capture ground truth: the
   cart-streaming map, RAM/serial measurements, the input map. Measure before
   you reverse — dynamic truth beats static guessing.
   *Gate:* you know how the game streams data and reads inputs, from real
   traces, not inference.
3. **Reverse engineering.** Ghidra headless + interpreter-mode dynamic
   analysis. Find the touchpoints: entry chain, cart-read fn, input fn,
   EEPROM fn, and the SP/BIOS verdicts (`boot-binary.md`).
   *Gate:* every hardware touchpoint has an exact address and a patch plan.
4. **Conversion.** Loader + freestanding shim + patch table → a bootable GDI.
   Patch the arcade touchpoints to DC equivalents (see next section).
   *Gate:* boots in the emulator's *Dreamcast* profile, attract runs, playable.
5. **Hardware test & fit.** Run on real hardware via a GDEMU-class ODE. This
   is where the emulator's lies surface (see gotchas). Budget real debugging
   rounds here — it is not a formality.
   *Gate:* boots and plays on real hardware.
6. **Safety tripwires, then release.** An arcade game has no VMU concept, so
   the port must never write one (worst case: corrupting a user's saves).
   Run all three before packaging: `make test` (static maple-literal baseline
   scan over every executable surface — full cart, BIOS slices, loader
   objects), `make test-vmu` (unattended emulator canary run: seeded VMU
   images must survive byte-identical, an all-zero control file must get
   auto-formatted, proving the harness is wired), and a `make test-vmu-play`
   session covering settings, 2P, game over, and high-score screens. Method
   + baselines: `docs/superpowers/specs/2026-07-26-vmu-safety-design.md`,
   `scripts/test_maple_literals.py`, `scripts/test_vmu_untouched.sh` —
   reusable for the next port (start from an empty baseline, classify every
   hit).
   *Gate:* all three tripwires PASS on the release candidate.

## Core mechanism

Patch the Naomi/AW-specific touchpoints in the game binary and boot it from a
GDI via a custom loader:

- **Cart reads → GD-ROM loads.** Mirror the cart DMA registers to a
  shim-owned block; the streaming trigger becomes a shim call. No need to
  decode the game's DMA-descriptor struct — the parameters are the values the
  game was about to poke into the registers.
- **JVS input → controllers.** Map the game's input read to maple/controller.
- **EEPROM/coin logic → shims.** Return the game's own "nothing changed"
  native path; bake free-play into the image.

Project-level decisions that generalize:

- **Real hardware is the goal; the emulator is a dev tool, not the target.**
- **A trap-based generic "arcade runtime" does not work** — the Naomi cart
  registers and the DC GD-ROM ATA registers share hardware addresses, so a
  trap cannot tell them apart on real hardware. Patch specific touchpoints.

## Gotchas — the traps that actually cost us

The highest-value transferable content. Each of these burned real time.

- **The emulator masks real hardware.** Emulator-green is not a boot. Benign
  reads and HLE boot paths hide real-HW spins (a settings write-back spun
  forever on G1 drive status on a real DC; the emulator's reads were benign)
  and skip init ladders the real machine runs (the MIE reset/firmware-upload
  ladder never executes under HLE boot). **Verify on the target.**
- **Control-test with a known-good disc.** When stuck on "does it boot at
  all," run a proven-bootable disc (for us, Dolphin Blue) through the *same*
  pipeline and ODE before theorizing about your own artifact. It isolates
  "your bytes" from "the process" in one step.
- **macOS AppleDouble sidecars poison disc/data folders.** `._*` files (e.g.
  `._disc.gdi`) made GDEMU pick up junk and refuse to boot. Run `dot_clean`,
  or master on Linux. This one masqueraded as a deep boot bug for a while.
- **Boot binary placement matters.** The boot binary must live in the last
  data track. Max-clone a proven-bootable donor's low tracks + structure
  verbatim and keep *your* delta to a single track — it minimizes the surface
  that can be wrong.
- **IP.BIN / bootstrap traps.** `makeip` hardcoded CD-ROM device-info and a
  CD-R bootstrap; use a donor IP.BIN instead of a synthesized one.
- **Sector size is 2048, not 2352.** Don't guess 2352; it cost a round.
- **Unpatched register literals hide in vendor-BIOS thunks.** The stall we
  chased longest was hardware-register literals (`0x5f7xxx`) reached
  *indirectly* through Naomi BIOS library calls, not in the game's own code.
  Grep every touchpoint address across the whole image, including code reached
  through BIOS thunks.
- **Build on-screen observability early.** With no debugger on real hardware,
  the breakthrough tool was an on-screen shim HUD: breadcrumb blocks,
  heartbeats, a PC sampler painting the stalled main-thread address, and hex
  dumps of live descriptor lists read off the TV. Invest in this before you
  need it, not after five blind boots.

## What mattered vs. red herrings

For a **"does it boot at all"** problem, exhaust the structural and
disc-mastering explanations *first* — a control test is one command — before
deep-diving the game binary. Our costly red herrings lived in the binary (the
2352 sector guess, the uncached-descriptor-walk "fix" that was correct but not
the bug); the real blockers were structural (disc mastering, the AppleDouble
sidecars) and one deep (the BIOS EEPROM bit-bang). The debugging model itself
was wrong more than once — hold hypotheses loosely and let the HUD, not the
theory, decide.

## Working cadence

The backbone that kept this from flailing was the superpowers loop, run **per
phase**: `brainstorming` → spec, `writing-plans` → plan, then
`executing-plans` / `subagent-driven-development`. Every phase in this project
has a spec and a plan under `docs/superpowers/`. Two more that earned their
keep: `systematic-debugging` for the on-hardware bug hunts, and
`verification-before-completion` before any "it boots / it works" claim —
which is the same discipline as gotcha #1.

Recommended for port #2. Not automated here — a port skill that mandates this
was considered and deferred (see the reuse spec).

## Pointers

- Technique catalog & what transfers to Naomi: `atomiswave-method.md`
- Hardware deltas: `naomi-vs-dreamcast.md`
- Can a game damage the ODE / real GD-ROM drive? `drive-safety.md`
- Toolchain install recipes: `tooling.md`
- This port's RE findings: `boot-binary.md`
- Deferred tooling handoff (kit repo, instrumented-Flycast fork) and the full
  reuse plan: `../superpowers/specs/2026-07-26-experience-reuse-design.md`

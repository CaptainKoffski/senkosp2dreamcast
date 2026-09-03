# Phase 7 — Polishing

**Status:** chartered 2026-09-03 (this doc), not yet started. Phase 6 closed
same day (tripwires 3/3, composite fixed + hardware-proven, DreamShell
known-fail characterized, release packaged by the operator and sent to a
closed-beta tester).

**Ground rules (operator decisions, 2026-09-03):**

- **T1 (DreamShell) is the ONLY must-have, and runs FIRST.** Everything
  else in this phase is optional — attempt, keep, or drop on merit.
- Playbook applies per task as usual: brainstorming → spec → plan for T1
  before code (`docs/kb/port-playbook.md`).
- The closed beta is live: keep `main` releasable at all times; phase branch
  `phase7-polishing`.

---

## T1 (MUST, first): boot and run via DreamShell serial-SD

**Goal:** the game boots through DreamShell isoldr from an SD card on the
serial port and plays, on the same release disc image.

### What we measured in phase 6 (docs/kb/phase6-release.md §DreamShell)

- isoldr **correctly serves BIOS-syscall GD reads from the SD image**: the
  loader's KOS-path cart read passed the `NAOMI` magic check.
- The loader's raw-ATA rehearsal then halted (by design, loudly):
  `RAW-ATA READ FAIL r=-6 err=da061150` = `GD_E_CHECK`, sense key 5
  ILLEGAL REQUEST — the raw task-file path talks to the *physical* drive,
  which holds the DreamShell boot disc, not our game.

### Why the shim is raw-ATA today (shims/src/gd.c header)

The loader places the Naomi RTOS kernel slice over
`0x8c000600–0x8c003800` (`KERNEL_DST`/`KERNEL_TOTAL_LEN`,
`shims/include/shim_iface.h:38`; `docs/kb/phase4-conversion.md` §Low-RAM
placements) — which is where the **real DC BIOS** keeps its GD driver
state. On a real-BIOS boot, GD syscalls are dead after handoff, hence raw
ATA.

### The key architectural fact that makes T1 feasible

The syscall **vector table** (pointers at `0x8c0000b0/b4/b8/bc` —
[mc.pp.se/dc/syscalls](https://mc.pp.se/dc/syscalls.html)) sits **below
0x600 and survives our kernel-slice placement**. Under DreamShell, the
GDROM vector (`0x8c0000bc`) points into **isoldr's own resident driver**,
loaded at a user-selectable address — the BIOS work area we stomp is
irrelevant to it. So syscalls are dead only on real-BIOS boots; under
isoldr they can stay alive through the whole game, *if* isoldr's resident
blob and our memory map don't collide.

### Preferred solution: dual-backend GD driver ("A")

Runtime cart reads go through one of two backends, chosen once at boot:

1. **raw** (today's `gd.c`): real-BIOS boots (GDEMU, optical). Unchanged.
2. **syscall**: `gdGdcReqCmd(PIOREAD)` + `gdGdcExecServer` polling +
   `GdcGetCmdStat` — cooperative, no IRQ ownership needed; the Cleopatra
   port's shim is a **proven reference implementation of exactly this
   streaming loop on this hardware class** (`../cleopatra/shims/`), port
   it as `shims/src/gd_sys.c`.

**Backend probe** (extend the loader rehearsal, `loader/main.c` ~line 205):
try raw first against the sector KOS just read; on `GD_E_*` failure, try
the syscall backend against the same sector + byte-compare; halt (current
red screen) only if both fail. Record the chosen backend in a shim_iface
flag; `gd_read_cart` dispatches on it. The probe IS the detection — no
isoldr signature sniffing needed.

**Suggested step order:**

0. **Throughput reality check FIRST** (cheap, hardware, no code): the
   serial dongle ceiling is SCIF ~1.56 Mbps ≈ ~190 KB/s. Boot image ~1 MB
   ≈ 6 s; big scene loads are tens of MB ≈ **minutes**. Measure real
   throughput with the tester's dongle (time the phase-6 leg's KOS-read
   stage, or a DreamShell file copy) and get the operator's go/no-go on
   the expected load times *before* engineering. If the dongle is
   actually SD-over-something-faster, even better — measure, don't
   assume.
1. Recon isoldr source (github.com/DreamShell/DreamShell, `firmware/isoldr`):
   confirm syscall coverage (PIOREAD by FAD, 2048-byte data sectors — our
   `gd_plan()` math carries over), resident-blob size, placement presets.
2. Low-RAM map audit: pick the isoldr placement preset that fits our map.
   Candidate hole: `0x8c003800–0x8c010000` (between kernel slice and
   loader; isoldr's `0x8c004000` preset targets exactly this — same slot
   dcload uses). Verify against phase-4 placements + loader staging that
   nothing of ours touches it at runtime. **Operator instruction must pin
   the preset** — the `0x8c000100` preset would land under our kernel
   slice and die.
3. Port the syscall backend from Cleopatra; wire the probe + dispatch.
4. Legs. Note two hard constraints:
   - **All DreamShell legs are serial-silent** — the dongle owns the SCIF
     pins (standing rule). Diagnostics = on-screen hex only (shim_die /
     HUD kit precedent).
   - **Flycast cannot emulate the serial-SD dongle** (no serial peer).
     Emulator control legs can still validate the syscall backend partly:
     DreamShell itself boots in Flycast, and the syscall path can be
     forced via a build flag against a normal virtual disc *before*
     handoff stomps BIOS state — but the end-to-end verdict is
     hardware + operator, stop-and-wait.

### Alternatives if A hits a wall

- **B — own SD driver in the shim:** speak the dongle's SPI-over-SCIF
  protocol + read the image directly (DreamShell's SD driver source as
  reference). Removes the isoldr memory dance entirely; costs owning SD
  init/protocol + an image-location convention. Same throughput ceiling.
- **C — relocate/virtualize the kernel slice** so the real BIOS GD driver
  survives everywhere: phase-4-scale RE of every game reference into
  low RAM. Last resort; almost certainly not worth it.

### Risks / open questions (resolve in spec)

- Does anything of ours write below `0x8c000600` at handoff? (Phase-4 KB
  says the slice starts at 0x600; verify no zeroing below it.)
- isoldr resident vs our runtime map (step 2) — the one real collision
  risk.
- Syscall reentrancy vs the game's IRQ context: Cleopatra ran ExecServer
  pumping from shim context — mirror their guards (their KB records the
  gotchas).
- GDEMU/optical regression: the raw path must stay byte-identical —
  re-run the phase-5 boot legs + `make test` as the regression gate.

---

## Optional pool (any order, none required)

**T2 — Profiling leg: attribute the loading times + stage-8 microfreezes.**
Operator reports (00-status 2026-09-03 backlog): (a) long loads at
attract→START (descending-tone hang moment) and at 2P join; (b) background
microfreezes on stage 8. One instrumented leg (fork cartlog timings +
arena telemetry) to split each into disc-transfer vs game-side unpack vs
VRAM-arena churn. Stage 8 peaks within ~100–200 KB of the 8 MB arena
ceiling (`docs/kb/arena-fit-options.md`) — (b) may be eviction churn, not
disc. **T3/T4 are gated on this measurement — don't touch the driver
before it.**

**T3 — G1 DMA / async cart service** (only if T2 says disc-bound): the
recorded upgrade path in `gd.c`'s ponytail note. Caveats already recorded
there: shim mirrors the game's G1 registers, DMA completion IRQ must stay
masked (Cleopatra lesson). Async completion could also unblock the
descending-tone stall if the game's streaming API is kick+poll.

**T4 — Stage-8 arena margin** (only if T2 says arena churn): widen the
margin via further VQ shrink of the stage-8 PAK set or eviction tuning —
the phase-5 texpatch toolchain (`scripts/shrink_vq.py`, `vq_tuner.py`) is
built for exactly this.

**T5 — Ernula barrier-hang watch item** (postponed from phase 5):
hard-to-reproduce, possibly-not-issue. A repro attempt only if the beta
tester hits it too.

**T6 — Dev-disc experiment** (postponed from phase 6): master the game
disc with dcload as its boot binary → serial upload iteration without the
GDEMU button-swap dance. Quality-of-life for us, invisible to users.

**T7 — Boot black-gap cosmetics** (rolled back once — operator judged the
bar no better on hardware, commit `7476d47` has the whole implementation
+ recon): only revisit with a new idea, e.g. keeping the splash visible
through the gap (BOOT-UNBLANK recon in `docs/kb/phase5-hardware.md`
§Black-gap decorate has the scanout facts).

---

**Wiring for the next session:** start from this doc + `docs/kb/00-status.md`.
T1 begins with the playbook loop (brainstorm → spec → plan), and its step 0
(throughput measurement) needs only the operator and a stopwatch.

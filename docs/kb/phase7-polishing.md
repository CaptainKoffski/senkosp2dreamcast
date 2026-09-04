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

   **MEASURED (operator stopwatch, 2026-09-03, phase-6 Task 32 setup
   re-run):** isoldr launch → loader splash ≈ 7 s (≈880 KB `1ST_READ.BIN`
   + isoldr's own init ⇒ ≥125 KB/s, overhead-diluted lower bound); splash
   → red rehearsal-halt screen ≈ 3 s. That second window is GD init + the
   loader's single `cdrom_read_sectors` of the 1,515,512 B main image
   through isoldr's syscall layer (`loader/main.c` rehearsal block) — the
   exact mechanism a syscall backend would use — so effective sequential
   throughput ≈ **490 KB/s** (eyeball band 2–4 s ⇒ 370–740 KB/s). The
   ~190 KB/s SCIF-ceiling planning assumption is **disproven low**; the
   dongle transport is 2–4× faster. Caveat: one large sequential read is
   the best case — the game's runtime mix (1,590 smaller DMA tuples,
   Phase 2) pays per-read overhead, so treat 490 KB/s as the ceiling-ish
   figure, not the in-game guarantee. Sustained in-game demand (2.3
   MB/min ≈ 39 KB/s, Phase 2) fits with ~10× margin; a 10 MB scene burst
   projects to ~20–30 s.

### T1 measurements (2026-09-03)

**Instrument path (three legs, two defects found and fixed along the way).**
Fork commits (`../flycast4naomi2dreamcast`), oldest first:
`f821cdc3c` (SHIMWATCH2 per-address dedup, Task 1's own landed instrument) →
`871fc3274` ("DC-boot arming for SHIMWATCH2/SPWATER") →
`704e96afe` (build-warning fixup, no logic change) →
`8ce3b451d` ("fix round 3: DC-boot arming trigger fired via P2, matched only P1").

- **Leg 1** (`captures/phase7/hole-attract.log`, against `f821cdc3c`): 0
  `SHIMWATCH2`/`SPWATER` lines. **Defect 1 — Naomi-gated arming:** both tags
  print only from `cartlog_sample()`, which every call site gates on
  `cartlog_aram_base != nullptr`, armed only by Naomi-cartridge DMA/PIO events
  (`naomi.cpp:195,635,650,655-681`) — architecturally unreachable on a native
  DC `.gdi` boot (confirmed live: independent instrument `ARENAHW` fired 6
  times in the same leg, proving the log pipe itself was healthy). Fixed by
  `871fc3274`: a DC-reachable baseline (`HANDOFF-DC`, armed off the record-walk
  stub's final CCR write) + a DC-reachable periodic tick (piggybacked on the
  existing `STARTRENDER` hook, dynarec-safe) + per-window caps (hole window
  uncapped, dedup-bounded; shim-home window keeps its 64+CAP budget).
- **Leg 2** (`hole-attract2.log`, against `871fc3274`+`704e96afe`): still 0
  `HANDOFF-DC`/`SPWATER`/`SHIMWATCH2`. **Defect 2 — P1/P2 address-mirror
  alias:** the CCR-write trigger compared the raw PC against
  `HANDOFF_SCRATCH`'s **P1** address (`0x8ce9xxxx`), but the handoff stub runs
  via `P2ADDR()` — the uncached alias, `| 0xa0000000` (`shims/include/shim_iface.h:74`)
  — so it genuinely executes at `0xace9xxxx` and the raw-PC compare could never
  match, on dynarec or interpreter alike. Fixed by `8ce3b451d`: mask
  `Sh4cntx.pc & 0x1fffffff` before compare (SH4 P1/P2/P3 mirror the same
  physical space at address bits 31:29) — a real fix, not a fallback trigger.
- **Leg 3** (`hole-attract3.log`, against `8ce3b451d`): armed correctly —
  `HANDOFF-DC` ×1 (line 14566, one-shot latch), `SPWATER` ×116, `SHIMWATCH2`
  ×3,427 (3,362 hole-window + 64 shim-home + 1 CAP sentinel).

**Leg-3 verdict: the hole is NOT quiet.** 3,362 unique diverged bytes,
confined to `0x8c009e10–0x8c00bfff`, in three front-loaded spans (gap-collapse
≤16 B; independently re-derived twice, matching to the byte both times):

| span | width | unique hits |
|---|---|---|
| `0x8c009e10–0x8c009f8b` | 380 B | 378 |
| `0x8c00a2dc–0x8c00a6fb` | 1,056 B | 1,056 |
| `0x8c00b828–0x8c00bfff` | 2,008 B | 1,928 |

99.85% of unique addresses first appear in the first third of the 600 s leg,
0 in the last third — one-time initialization, not steady-state churn.
**Identified: live Naomi RTOS TCB-table content, not our code and not a
boot-chain fill.** `0x8c009e00` is exactly `0x0c004000 + 47×0x200` — slot 47 of
the documented 0x200-stride per-task TCB array (`§Phase 3: RAM snapshot`
above). Cross-checked against `tools/ram-snapshot.bin` (a pre-port Naomi
capture, independent of this DC leg): byte-exact agreement — snapshot is zero
through `0x9e0f`, non-zero from `0x9e10`; same pattern at span 2's boundary
(`0xa2dc`) and span 3's (~`0xb824`); the documented 4 KB internal quiet gap
`0xa800-0xb7ff` is zero in the snapshot too; and the snapshot's non-zero
content continues past `0x8c00c000` (through at least `0xc020`), so the live
structure extends into the previously "game-owned, unwatched" gap as well.
Content shape (pointers into static BSS, IEEE-754-shaped floats, no
repeated byte / no ASCII / no counter) matches a task context area, not a
fill sweep. **`0x8c003800–0x8c009e0f` stayed silent the full 600 s but this is
not evidence it's free** — it's the same live TCB table's slots that simply
weren't claimed during attract mode; a played match or other game state could
still touch lower slots. Full derivation: `.superpowers/sdd/2026-09-03-phase7-t1-dreamshell/task-3-report.md` §4a.
Honest limit on the `SHIMWATCH2` content-scan itself (same as the phase-4
watch): it runs at the C level inside the fork's periodic tick, so it only
sees whatever byte value is resident *at the sampled instant* — a write that
flips a byte and reverts it between two sampled ticks bypasses the scan
entirely and would never show up as a divergence.

**`bootmin=0x8c00e7ec`** (deepest `r15` sampled over the 600 s leg, `min ==
bootmin` in both the first and last `SPWATER` line — the deepest excursion
happened at/near boot and was never exceeded later). This is *deeper* than
both the Naomi floor (`0x8c00e864`) and the DC hang datum (`0x8c00e940`) on a
leg that ran clean for 600 s with no hang. Honest limit: `sp_boot_min` is
event-sampled (maple/GD-command entry points), not continuous — a still-deeper
excursion between samples cannot be ruled out from this leg alone.

**Fill-pool decode — closes the boot-binary.md step-11 "detail deferred"
note.** Pool words `.dat 0x122c-0x123c`: `0x8c170c14, 0x41474553("SEGA"),
0x8c00c000, 0x8c15ae64, 0x8c15ae60`. Disassembly (`sh-elf-objdump -EL`) of the
consuming code at `0x8c021150` resolves two fill loops, neither touching the
hole or the hot spans: **stack SEGA-canary fill `[0x8c00c000, 0x8c00f000)`**
(end = the same `0x8c00f000` SP literal from step 10 — paint the unused boot
stack before it's live, to measure high-water depth later) and a **52-byte
BSS-tail SEGA-canary `[0x8c1de1cc, 0x8c1de200)`**. The real zero-fill BSS
clear is a separate, adjacent routine (`bsr 0x8c021188`, `[0x8c1bf180,
0x8c1de1c9)`, confirmed `mov #0,r4`). See `docs/kb/boot-binary.md` §Entry
chain step 11 for the addendum, full derivation in the task-3 report §1.

**TMU0 verdict: confirmed writer, `GD_SYS_FIRST_LADDER` pinned 0.**
Disassembly-verified at two sites (`0x8c02a150`, byte-for-byte duplicated at
`0x8c19c150`): stop TMU0 → `TCR0=2` → `TCOR0=TCNT0=0xFFFFFFFF` → restart —
a full reprogram, not a read (many separate lone-`TCNT0` call sites remain
pure reads, confirmed by spot-check). Drove the decision-6 revision now
committed in the spec (`docs/superpowers/specs/2026-09-03-phase7-t1-dreamshell-design.md`,
commit `ca60b97`): the recovery-ladder `InitSystem`+`CMD_INIT` call moved to
the probe stage only (loader context, pre-handoff, timers BIOS-owned); the
between-attempt retry ladder's residual risk (mis-timed sleeps if the syscall
backend is re-entered post-handoff, after the game has reclaimed TMU0) is
accepted — a failed retry dies loud, it does not hang the happy path.

**isoldr heap bound: N = 9,432 B worst case (1,216 B without CISO)** —
compiler-verified struct sizes (`sh-elf-nm --print-size` on a probe TU built
with the exact plain-sd flags) + exact bump-allocator arithmetic over the real
allocation sites (`fs_init`'s `_files`/`_fat_fs`, plus the CISO LZO work
buffer, which is compiled into the plain "sd" build's `DEFS` even though our
deployment's uncompressed image never triggers it at runtime). **Slim-build
sizes** (`make -f Makefile.sd`, `sh-elf-size`, vs the `dec+1024+32 ≤ 25,615 B`
fit ceiling — itself exactly 512 B / one TCB slot short of the raw measured
safe window `0x8c009e0f − 0x8c003800` = 26,127 B):

| variant | dec (text+data+bss) | dec+1024+32 | vs 25,615 B |
|---|---|---|---|
| `sd` as shipped (`ENABLE_CISO=1 ENABLE_MULTI_DISC=1`) | 29,928 | 30,984 | +5,369 over |
| `sd_min` (both dropped) | 28,072 | 29,128 | +3,513 over |
| `sd_nociso` (`ENABLE_MULTI_DISC=1` only) | 28,284 | 29,340 | +3,725 over |

**None fit — not even the maximally-trimmed build.** Independent confirmation
(byte-content hazard above, raw size here) that low RAM is dead regardless of
build trimming.

**Falsification conclusion.** The original contract (`memory=0x8c004000,
heap=0x8c00c000`) is dead on both counts. **Operator-decided revision
(committed, `ca60b97`):** isoldr moves to the top of the game's own relocated
heap — a shim hook carves 64 KB off the heap's top (`0x8d000000 →
0x8cff0000`) once, after the game's own `syMalloc` heap-create
(`FUN_8c085b00`), conditional on `backend == syscall` (GDEMU/optical boots are
untouched). Final pins: **`memory = 0x8cff0000`, `heap = 0x8cff7a00`**. Full
memory map + fatal-alternatives list: spec §Memory contract (same file/commit).
Full recon: `.superpowers/sdd/2026-09-03-phase7-t1-dreamshell/task-3-report.md`.

1. Recon isoldr source (github.com/DreamShell/DreamShell, `firmware/isoldr`):
   confirm syscall coverage (PIOREAD by FAD, 2048-byte data sectors — our
   `gd_plan()` math carries over), resident-blob size, placement presets.
2. Low-RAM map audit: pick the isoldr placement preset that fits our map.
   Candidate hole: `0x8c003800–0x8c010000` (between kernel slice and
   loader; isoldr's `0x8c004000` preset targets exactly this — same slot
   dcload uses). Verify against phase-4 placements + loader staging that
   nothing of ours touches it at runtime. **Operator instruction must pin
   the preset** — the `0x8c000100` preset would land under our kernel
   slice and die. *[Superseded by §T1 measurements — the candidate hole is
   live TCB table, not free; placement moved to the heap-top carve, see
   spec §Memory contract.]*
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

### T1 emulator gate (2026-09-04)

Task 7 (verification suite), closing exit criterion 5 + re-recording the
release md5s (criterion 3's emulator half). Full data: `task-7-report.md`.

**Task 6 legs (carried forward for the record — `task-6-report.md` FIX
ROUND 2):**

| leg | build | duration | key counts | carve-window (`addr=8cff`) |
|---|---|---|---|---|
| `testsrv-attract.log` | `TESTSRV=1` | ~595 s | 809,733 lines; `MDODMA`=277,743, `TAREG`/`TAEND`=70,440/70,440, `PVRW`=309,412, `SHIMERR`=0, `SHIMWATCH2`=3,427 (full established baseline) | 0 — carve intact under real syscall traffic; `gdstack.S` trampoline exercised end-to-end for the first time, `GDPIO fad=0006f526` (the request that hung forever pre-fix-round-2) completes clean |
| `forcecarve-attract.log` | `FORCE_CARVE=1` (raw backend) | ~595 s | 808,512 lines; `MDODMA`=277,679, `TAREG`/`TAEND`=70,424/70,424, `SHIMERR`=0, `SHIMWATCH2`=3,427 | 0 — carve applied on the raw backend doesn't perturb a normal boot |
| `dispatch-raw2.log` | plain `make gdi` | ~180 s | `TAREG`/`TAEND`=21,406/21,406 each, continuous to EOF, `SHIMERR`=0 | **314** — expected/correct: uncarved raw backend, ordinary top-of-heap allocator traffic just below `0x8d000000`, not a breach (the carve gate is `if (backend)`, off here by design) |

**This task's soak — TESTSRV attract, ~1800 s (30 min), one-call
foreground/backgrounded pattern, killed by PID** (`captures/phase7/testsrv-soak.log`
+ `.stdout.log`, gitignored): build `make clean && make gdi TESTSRV=1
SERIAL=1 CRC=1`, flags confirmed on the actual compile lines (repo's
standing `make clean`-before-reflag rule, `phase5-hardware.md:477`).

```
CHECK shimcrc_match: PASS — 464 SHIMCRC record(s), 0 mismatch(es)
CHECK gdread_match: PASS — 1738 verified (fad>=base,type=0x800), 4 lowfad, 0 typeskip, 0 mismatch(es)
CHECK coverage_nonzero: PASS — shim=464 record(s), drive=1742 record(s)
```

`check_stream_crc.py`'s own texpatch caveat (its docstring) applied: this
build splices `shrink_vq.py` records into track04 by default (69 records),
so `--dat` was a texpatch-applied slice (`dd if=build/track04.iso bs=4096
skip=864`, cart region starts at byte 3,538,944 — `make_gdi.py`'s
`BOOT_REGION` constant, fixed regardless of loader/shim size), not raw
`senkosp.dat` — same convention as `tooling.md`'s r5/r7-smoke legs.

Other verdicts: 0 `TEXERR` (206 `TEXHUD` health lines, all-zero fields), 0
`SHIMERR` anywhere in either log (covers the stack-canary `shim_die(5, ...)`
specifically, `gd_sys.c:157` — no canary trip), carve-window grep (`grep
SHIMWATCH2 captures/phase7/testsrv-soak.log | grep -cE "addr=8cff"`) → **0**
— carve stayed intact for the full 30 min under sustained syscall traffic.
`SHIMWATCH2` total 4,002 (vs the 3,427 established baseline — longer leg,
more hole/shim-home churn; carve window itself is the 0 above). No
error/fail/abort/halt/wedge/crash tag in either log (one substring hit is a
boot-time patch-table descriptive string, "CART-WAIT-B ... settle/abort" —
not an event). `TAREG`/`TAEND`/`PVRW`/`MDODMA` still firing on the log's
final lines — no freeze.

**Attract cycle count**, derived from the `GDPIO` fad sequence (1,630 reads):
12 large backward jumps, alternating between two fixed rewind points
(`0x86a27→0x7a490`, `0x86514→0x76b9e`) at an even cadence through the whole
leg — 2 rewinds per full attract loop (matching the documented "attract's
two scripted demo fights", `cart-streaming-map.md`) = **6 full attract
cycles**, comfortably past the brief's ≥3 bar.

**Verdict: PASS, unconditionally green.** Byte-perfect delivery through the
trampoline+dispatch+carve path for 30 min sustained, carve never breached,
no wedge, no canary trip, attract free-running the whole leg.

**New release md5 set (Release md5s v7 — supersedes `phase5-hardware.md`
§Release md5s v6 for deploys; same convention as #26/#28 in `00-status.md`).**
`make test` exit 0 (host tests + patch-table + maple-literal scan, all
green) immediately before; reproducibility re-proved by running `make clean
&& make gdi` **twice** and diffing all five disc files — identical both
times:

| file | md5 |
|---|---|
| disc.gdi | c527f1ec937b56caa65084d436f8c0a0 (unchanged since v2) |
| track01.iso | 681fa4c8daa058ce2df8ea1b604d6e91 (unchanged since v2) |
| track02.raw | 03c796f60db2e9ef0b65a42a47a9d321 (unchanged since v2) |
| track03.iso | 244ae7e5a321345e995edc4793fcbdd5 (unchanged since v2) |
| track04.iso | **c6c622d759ff93c8cd8b4483c3a850ca** (was `3460af24d9e21ab59d6bae88fb929ff2` in v6 — shim grew: `gd_testsrv.c`, `gdstack.S` revival, carve tables, dispatch) |

Card is stale: `make deploy` before the next hardware session.

**R12 honest limit (unchanged, restated for the closing record).** Flycast
has no serial peer — it cannot host a real isoldr. The `TESTSRV`/
`FORCE_CARVE` legs above validate **our own calling machinery**: the
`gdc_call` trampoline, the probe/dispatch/carve wiring, and a real
(if deliberately dumb) GD-syscall server that actually completes requests —
not isoldr's real timing, FatFs, coroutine, or CISO behavior. `GD_TEST_SERVER`
is `#if`-gated test-only code, never shipped. **End-to-end isoldr validation
is a real DreamShell hardware leg with the dongle — this emulator gate closes
everything upstream of that, not the thing itself.**

**Build hygiene note:** this soak's build carries `SERIAL=1` (SCIF voice on,
`-DSHIM_SERIAL=1 -DLOADER_SERIAL=1 -DSHIM_TEXHUD=1`) — an emulator-only
diagnostic; a real DreamShell dongle owns the SCIF pins (standing rule,
§T1 step 4). Release builds (the md5 set above) stay serial-silent by
construction (`SERIAL` defaults unset), and `TESTSRV`/`FORCE_CARVE`/`GDDIAG`
are test-only knobs gated `#ifndef`/default-0 — none of the three is ever
part of a shipped build (`docs/kb/tooling.md` §Phase 7 build knobs has the
full record).

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

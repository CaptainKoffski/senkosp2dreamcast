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
  `phase7-polishing` (T1) — merged to `main` 2026-09-05 and deleted; pool
  work continues on `phase7-pool`.

---

## T1 (MUST, first): boot and run via DreamShell serial-SD

**STATUS: CLOSED 2026-09-04 — all 7 exit criteria earned (§T1 gate
audit below; hardware round PASS both legs).**

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

**Evidence-chain pin (fix round, 2026-09-04 — review caught a real
artifact-state trap, not a real integrity bug).** The CHECK block above was
captured against **the TESTSRV build's own `track04.iso`**, md5
`572cdb336a9e18af3fdd5db6d4f826f4` — the exact artifact this soak actually
ran against. `build/track04.iso` is a **shared, overwritten-in-place**
build product: Step 2 of this same task (below) later ran `make clean &&
make gdi` (release, no flags) on top of it. A review that re-ran this
section's documented `check_stream_crc.py` command *after* Step 2 had
already landed was — correctly — checking the soak's logs against the
**release** `track04.iso` instead, and got **12 `GDDMA` mismatches**, all at
`fad` 450150–450566 (file offsets 0–851,968 B), i.e. strictly below
`CART_FAD` (451,878) — the fixed-size boot-region window (loader + shim
bytes), not the `.dat` cart domain. `shimcrc_match` stayed PASS throughout
(0/464) because that check only ever reads the `--dat` cart slice, which is
genuinely build-invariant: the texpatch-applied slice extracted from the
release `track04.iso` is byte-identical (md5 `beac24c0ed3744e07c7dc8b69ec836e4`)
to the one extracted from the TESTSRV build — only the boot region differs
between builds (different `SERIAL`/`CRC`/`TESTSRV` `DEFS` baked into the
same loader source), exactly as expected. **Second CRC run (the review's
own ask for a second evidence point):** rebuilt `make clean && make gdi
TESTSRV=1 SERIAL=1 CRC=1` from the identical, unchanged source tree —
`track04.iso` reproduced **byte-for-byte** (md5
`572cdb336a9e18af3fdd5db6d4f826f4`, matching the pre-soak build exactly) —
and re-ran the checker against *this* artifact: **0 mismatches, all three
CHECKs PASS**, reproducing the original result exactly. The hypothesis is
proven, not assumed: the 12 "mismatches" were a documentation gap (this
section never pinned the TESTSRV track04's own md5) meeting a shared
mutable build directory, not a soak-integrity defect. **Anyone
re-verifying this soak must rebuild `make clean && make gdi TESTSRV=1
SERIAL=1 CRC=1` first** (md5 `572cdb336a9e18af3fdd5db6d4f826f4`) — checking
these logs against any other `track04.iso` will reproduce the same 12
boot-region false mismatches.

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

Card refreshed with this set on 2026-09-04 (`make deploy`, hardware round
below).

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

### T1 hardware round (2026-09-04) — PASS, both legs

Operator session on the release md5 set v7 (`track04`
`c6c622d759ff93c8cd8b4483c3a850ca`), deployed to both the DreamShell SD
(phase-6 Task 32 method) and the GDEMU card (`make deploy`).

**Leg 1 — DreamShell 4.0.4 / isoldr 0.8.4, serial-SD, pinned preset**
(Boot memory `0x8cff0000`, Heap memory `0x8cff7a00`, firmware plain `sd`,
preset saved): **PASS.** Boots clean — the phase-6 red screen is gone.
Operator watched the full attract loop, then played 2P and 1P matches;
all transitions OK. Costs observed, both expected for a ~490 KB/s serial
link (step-0 measurement, top of this doc):

- Loading times noticeably longer than GDEMU.
- Stage-8 microfreezes clearly noticeable (already on the T2 backlog).
- **New symptom for T2:** character-select background microfreezes — the
  bg freezes for a fraction of a second roughly once per second
  (observed on the DreamShell leg; never reported on GDEMU). Consistent
  with the slow link stalling a background stream; goes to T2's
  attribution leg alongside the other two.

**Leg 2 — GDEMU regression: PASS.** Operator: "no regressions, works as
usual." Raw path byte-identical by construction (carve gated on
`backend==syscall`; `gd.c` diff is the 3-line dispatch only).

**Characterized known-fail — isoldr default settings (no preset).**
Operator also tried defaults: the game boots, 2D story art renders, but
the console **hard-reboots the moment the first 3D model renders** in
attract. Root cause from source + our own measurements, no
instrumentation needed: with no preset, isoldr places itself at
`ISOLDR_DEFAULT_ADDR_LOW = 0x8c004000`
(`tools/dreamshell-4.0.4/include/isoldr.h:38`, applied in
`applications/iso_loader/modules/module.c:2088`). That address is the
game RTOS's **live 0x200-stride TCB table** (§T1 measurements above:
slots 47+ = `0x8c009e10`–`0x8c00bfff` written during boot, deeper slots
claimed as tasks spawn). The `sd` loader blob ends ~`0x8c00b908` —
its tail sits inside the live table. Boot limps through, then attract's
first 3D scene spawns the demo-battle tasks → fresh TCB slots overwrite
isoldr's resident body → the next GD syscall jumps into clobbered
memory → reboot. Timing matches exactly (2D art already resident; the
3D presentation is when streaming + task-spawn resume). This is the
same falsification that killed low-RAM placement in the measurements
section: **no placement fix can make Auto/defaults work** — every byte
of RAM except the carved `[0x8cff0000, 0x8d000000)` is game-owned.

Practical equivalent, zero code: DreamShell presets are per-image files
`<dev>_<md5>.cfg` under `DS/apps/iso_loader/presets/`, keyed by md5 of
the image's boot sector (`modules/isoldr/preset.c`
`format_preset_filename`; md5 computed at `module.c:372`). Our release
image is bit-reproducible, so the correct preset file is derivable and
**shippable in the release package** — copied once, stock isoldr
auto-applies it and defaults "just work". ~~Parked as release-packaging
polish (operator call)~~ **SHIPPED 2026-09-05** — §T1 follow-up below.

**Ernula barrier watch item (Optional pool T5): RESOLVED — feature, not
bug.** Operator: releasing the barrier button while continuing to spam
projectiles keeps the barrier up until the attack series ends;
reproduced deliberately in 2P with no other projectiles on screen, so
it is unrelated to slowdown. Case closed.

### T1 gate audit — CLOSED (2026-09-04)

Spec: `docs/superpowers/specs/2026-09-03-phase7-t1-dreamshell-design.md`
§Exit criteria. One row per criterion, evidence named.

| # | criterion | earned by | verdict |
|---|---|---|---|
| 1 | DreamShell boot, no red screen, probe selected syscall | §T1 hardware round leg 1: boots through isoldr 0.8.4 (pinned preset) to attract. Syscall selection is proven structurally, not by an on-screen tag: raw ATA **cannot** serve serial-SD (phase-6 Task 32 known-fail is the control — same rig, raw path halts loud), so every read behind a successful boot was syscall-served | ✅ |
| 2 | DreamShell play, full match, load times accepted | leg 1: full 1P + 2P matches, all transitions OK; loads longer as the step-0 GO (~490 KB/s) predicted, operator-accepted; microfreeze notes routed to T2 | ✅ |
| 3 | GDEMU regression + `gd.c` raw path identical + `make test` + reproducible md5s | hardware round leg 2 ("no regressions, works as usual"); `gd.c` diff = 3-line `gd_read` dispatch only (Task 6 review); `make test` exit 0; double-rebuild byte-identical, Release md5s v7 recorded (§T1 emulator gate) | ✅ |
| 4 | Probe totality: raw on GDEMU, syscall on DreamShell, both-fail halts red+readable | raw chosen: leg 2 + `dispatch-raw2.log` (flag=0); syscall chosen: leg 1; both-fail halt: the `halt()` renderer is hardware-proven red+readable (phase-6 Task 32 photo, same machinery), and the two-error-word composition passed Task 6 code review — but **that exact path never executed** (firing it needs failure-injection knobs on both backends; declined as test scope for a cosmetic-only residual: worst case is imperfect text on an already-halted console) | ✅ (residual recorded) |
| 5 | Emulator control: TESTSRV soak + FORCE_CARVE leg, unattended | §T1 emulator gate: 30-min TESTSRV soak (464 SHIMCRC + 1,738 verified reads, 0 mismatches, carve-window hits 0, 6 attract cycles) + FORCE_CARVE attract leg clean; both unattended one-call legs | ✅ |
| 6 | Pre-code measurements banked with verdicts | §T1 measurements: hole write-watch (live TCB table → low-RAM falsified → carve pivot), SP low-water `bootmin=0x8c00e7ec`, fill-pool decode (stack canary fill, not the hole writer), TMU0 verdict (game writes TMU0 → `GD_SYS_FIRST_LADDER=0`) | ✅ |
| 7 | KB written: this doc §T1, tooling records, 00-status advanced | this doc (measurements + emulator gate + hardware round + this audit); `tooling.md` (DreamShell clone/build :1445, build knobs :1512, carve helper :1568, preset recipe); `00-status.md` phase-7 entry, phase-6 "GDEMU/optical only" limitation retired | ✅ |

**Honest limits carried into the record:** single rig (one console, one
dongle, DreamShell 4.0.4/isoldr 0.8.4 only); Flycast cannot host real
isoldr (R12), so end-to-end serial-SD validation is hardware-only — done
above; other isoldr versions/devices untested and out of scope.

### T1 follow-up — defaults just work, no tester-side settings (2026-09-05)

Operator decision (brainstorm 2026-09-05): a preset file shipped in the
release zip counts as "no DreamShell modification on the tester's side";
true bare-defaults play (own SPI/SD driver, charter alternative B) stays
parked. Two pieces shipped:

**1. Auto-applied preset in the release zip (packaging, zero runtime
code).** `make release` now runs `scripts/make_preset.py`, which derives
the preset filename from the built image and adds
`DS/apps/iso_loader/presets/sd_<md5>.cfg` + a tester `README.txt` to the
zip **with paths**; the disc files are wrapped in a `Senko no Ronde
Special/` folder (the Sushi Bar / Dolphin Blue release convention,
operator-directed 2026-09-05 — never loose files at the card root).
Tester instruction: copy the game folder anywhere, merge `DS/` at the
card root, launch, touch nothing. Chain, all source-verified in the
v4.0.4 tree: on image select the GUI auto-loads a matching preset
(`applications/iso_loader/modules/module.c:1758` isoLoader_LoadPreset →
`modules/isoldr/preset.c:191` isoldr_find_preset — user file beats the
built-in romdisk pack) and populates every widget from it; `<md5>` = md5
of the 2048 B boot sector = first sector of the data track
(`modules/isofs/fs_iso9660.c:1386`, session_base−150) = first 2048 B of
our donor-verbatim `track03.iso`, so the name — currently
`sd_f9b8dd28f12a741cd2ae1526f544aecb.cfg` — is **stable across
shim/loader rebuilds** (IP.BIN bytes). Values = the T1-proven pins
(memory `8cff0000`, heap `8cff7a00`) + the 4.0.4 GUI defaults the
operator's save carried (async=8 per app.xml `checked=` state, OS auto,
mode 0, dma 0; save format `preset.c:433`). `sd_` only — no `ide_` twin
(heap pin sized against the measured `sd` blob; IDE blob size
unverified). The script self-guards: refuses a track03 whose boot sector
isn't IP.BIN, and drops stale `sd_*.cfg` siblings.

**2. Friendly preset tripwire in the loader (~20 lines,
`loader/main.c` `preset_note()`).** Bare defaults used to limp to a
mystery hard-reboot at attract's first 3D scene; now, when the probe
selects the syscall backend, the loader checks the live GD vector's RAM
offset — `< 0x10000` (the gdstack G8 fingerprint threshold) means an
isoldr-class resident in game-owned low RAM, measured-fatal per the §T1
characterization — and stops **before staging** with a tester-facing
screen: calm steel-blue fill (`0x2331`, deliberately NOT the red
`halt()` — operator: testers "are very afraid of red"), instructions to
copy the DS folder from the zip (or pin boot/heap manually), closing
with "Nothing is wrong with your Dreamcast :)". Raw/GDEMU boots never
reach the check; the pinned preset (`0x8cff0000` → offset `0xff0000`)
clears it by construction; TESTSRV installs its vector high, unaffected.

**Emulator evidence (2026-09-05):**
- `phase7/preset-note-shot` — `PRESET_NOTE=1` screenshot-knob build
  (new test-only knob, top Makefile; fires `preset_note()` at loader
  entry): loader parks forever in the note loop — log ends at the
  loader's KOS video init, **0 cart DMA / 0 handoff / game never
  boots** over the whole leg. (The parked screen itself doesn't
  re-present in headless Flycast — same boot-gap present quirk as the
  phase-5 loading-bar autopsy; the visual renders via the same
  bfont+vram path as the hardware-proven red halt screen, photo owed by
  the hardware leg. First leg attempt burned on the known no-header-dep
  trap: `DEFS` knobs don't rebuild an up-to-date `main.o` — `touch
  loader/main.c` first, now recorded in tooling.md.)
- `phase7/preset-regress1` — clean release rebuild, unattended 3-min DC
  attract leg: attract DEMONSTRATION + FREE PLAY on screen, 0 real
  maple DMA (`MDODMA` 0). Raw path byte-path unchanged (the tripwire
  sits inside the raw-failure branch; `preset_note` is dead code on
  GDEMU boots).

**Release md5s v8** (build 2026-09-05, double-rebuild byte-identical):
`track04.iso` = `ba63905ca7b551ca8de1451872f8420d` (loader grew:
preset_note + tripwire), other four tracks donor-verbatim/unchanged.
Supersedes v7 (`c6c622d7…`). *(Same-day revision: first cut
`56f3ff8d…` said "keep the folder structure"; the screen now says "to
the ROOT of your SD card" — matching the README fix, so a tester who
unzipped into a subfolder isn't re-fed the ambiguous wording. Never
distributed. Attract regression re-run on the final bytes:
`phase7/preset-regress2`, clean — demo + FREE PLAY, 0 `MDODMA`.)*

**Hardware round — PASS, all three legs (operator-attested
2026-09-05, v8 build `track04 = ba63905c…`):**
1. DreamShell, image on card, **no preset, defaults untouched** →
   blue note screen shown, no reboot. ✅
2. Fresh release-zip contents on the DS SD, launch with defaults
   untouched → auto-preset applied, game boots and plays. ✅
   This leg also subsumes the planned filename/content bonus check:
   the game *playing* (rather than hitting the note screen or the
   characterized reboot) is end-to-end hardware proof that the
   boot-sector-md5 filename derivation is right, that stock isoldr
   found and parsed the generated cfg, and that its values (incl. the
   app.xml-derived `async = 8`) launch the game correctly.
3. GDEMU regression boot (loader bytes changed): works. ✅
Honest limit, same as every DreamShell verdict: single rig, operator
attestation without photos this round (the tripwire screen's renderer
is otherwise hardware-proven machinery; the phase-6 red-halt photo is
the precedent for it scanning out).

**Out of scope, recorded:** upstreaming the preset to DC-SWAT's
built-in pack (one-file PR, future DreamShell installs work with zero
files — operator call, doesn't help current 4.0.4 installs); Approach B
(own SPI/SD driver) remains the only path to true bare-defaults play.

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
microfreezes on stage 8; (c) NEW from the T1 hardware round (2026-09-04):
character-select background microfreezes on the DreamShell leg (~1/s,
fraction-of-a-second each — never reported on GDEMU, so likely pure
serial-link stall, but the leg should confirm). One instrumented leg (fork cartlog timings +
arena telemetry) to split each into disc-transfer vs game-side unpack vs
VRAM-arena churn. Stage 8 peaks within ~100–200 KB of the 8 MB arena
ceiling (`docs/kb/arena-fit-options.md`) — (b) may be eviction churn, not
disc. **T3/T4 are gated on this measurement — don't touch the driver
before it.** → **MEASURED 2026-09-05, verdicts in §T2 below:** loads
disc-bound at the 2.8 MB/s PIO ceiling (T3 gate OPEN), stage-8 freezes
= the 15 ms blocking drip read at ~1.05 s cadence, NOT arena churn (T4
CLOSED for this symptom); one operator question open on which
DreamShell screen froze.

**T3 — G1 DMA / async cart service** (only if T2 says disc-bound): the
recorded upgrade path in `gd.c`'s ponytail note. Caveats already recorded
there: shim mirrors the game's G1 registers, DMA completion IRQ must stay
masked (Cleopatra lesson). Async completion could also unblock the
descending-tone stall if the game's streaming API is kick+poll.
→ **CLOSED 2026-09-07** (§T3 below): both stages shipped, hardware round
PASS, all pre-registered targets met; release v9 respun.

**T4 — Stage-8 arena margin** (only if T2 says arena churn): widen the
margin via further VQ shrink of the stage-8 PAK set or eviction tuning —
the phase-5 texpatch toolchain (`scripts/shrink_vq.py`, `vq_tuner.py`) is
built for exactly this.

**T5 — Ernula barrier-hang watch item: CLOSED 2026-09-04, feature not
bug.** Operator repro (T1 hardware round): the barrier persists after
button release for as long as the projectile series continues — verified
in 2P with no foreign projectiles, unrelated to slowdown. No action.

**T6 — Dev-disc experiment** (postponed from phase 6): master the game
disc with dcload as its boot binary → serial upload iteration without the
GDEMU button-swap dance. Quality-of-life for us, invisible to users.

**T7 — Boot black-gap cosmetics** (rolled back once — operator judged the
bar no better on hardware, commit `7476d47` has the whole implementation
+ recon): only revisit with a new idea, e.g. keeping the splash visible
through the gap (BOOT-UNBLANK recon in `docs/kb/phase5-hardware.md`
§Black-gap decorate has the scanout facts). → **REVIVAL REGISTERED
2026-09-07 (operator ask, T8 follow-on):** the T8 pin plausibly explains
the rollback — on VGA the monitor was dropping/relocking during the gap,
so the decoration was invisible behind the "no signal" toast; with sync
held stable the gap becomes watchable for the first time. Plan when
funded: splash-persist through the gap (suppress the game's blank-set;
three redundant blank sites + splash-at-scanout-base proof already in
the recon), NOT a progress bar — the gap interior is 3.3 s of zero-I/O
CPU work (§Black-gap control test), nothing real to measure. Decide
AFTER the T8 pin's hardware verdict: operator watches one stable-signal
boot first, then judges whether the authentic black still bothers them.
→ **BUILT 2026-09-07 (§T7 REVIVAL BUILT below):** operator approved
option A (splash-persist + loader "NOW LOADING..." line; black length
is arcade-authentic and stays). Shim-side one-shot unblank at the
VIDEO-GEOM-HOOK wrapper exit — the census proves all three blank sites
fire inside the wrapped call, so this sticks without touching the
display-off routine (the v5 glitch-row class excluded by ordering).
Both-cable emulator legs PASS; v11 candidate `5c5e1cc6…`; operator
boot-watch owed. → **Round 1 FAIL 2026-09-07 (operator: garbage band
+ gauge ticks over the splash — the game's own compose, unhidden);
ROUND 2 BUILT 2026-09-08 (§T7 ROUND 2): side-buffer scanout at
measured-free 0x260000 + cart-read spinner + typeset text; both-cable
legs 0 foreign words. → **Round 2 hardware verdict 2026-09-08:
side-buffer PASS (splash byte-clean on HW), text off-style, spinner
never visible (design-dead: no cart reads in the gap). ROUND 3 SHIPPED
(operator chose bare splash): text + spinner deleted; v11 candidate
now `21494430…`; GAPISR recon found the vblank ISR live all gap
(~60 Hz) = a real spinner is a bounded round-4 if ever asked
(§T7 round 2 hardware verdict).**

**T8 — Video-signal dropout during loads** (operator, recurring; promoted
2026-09-07 from the T3 hardware round): the monitor loses sync and goes
to standby ~1 s on almost every load transition — tester-facing,
operator calls it unacceptable. Previously in the KB only as a
characterized-benign dcload-path quirk (`tooling.md` §GAME-VIA-DCLOAD:
from-scratch SPG reprogram `pc=8c032140` over dcload's video state,
"disc boots unaffected") — the new report contradicts that scope: it
happens on GDEMU disc boots too. Hypothesis: the game's KAMUI2 mode-set
(`FUN_8c032140` reg-poke; phase-6 MONITOR-SENSE-HOOK neighborhood)
re-fires at scene loads, and either the SPG rewrite lands non-atomically
(registers written one at a time = transient bad timing → real monitors
drop sync; VGA relock ≈1 s) or a transient teardown state intervenes
(phase-6 black-gap recon found three redundant blank-set sites). Plan
when funded: instrumented-fork leg logging the `0xa05f8000` block across
one load transition (VO_CONTROL/SPG census instrumentation already
exists from the black-gap recon), then a MONITOR-SENSE-HOOK-style shim
that skips the reprogram when the values are unchanged. Highest-value
open item per the operator. → **RECON DONE 2026-09-07** (§T8 below):
mechanism = the boot-time takeover mode-set really changing the raster
on VGA (old "same-values no-op" claim falsified); in-game loads are
video-silent. SPG-GEOMETRY-PIN fix designed, pending gate. →
**CLOSED 2026-09-07** (§T8 hardware round): pin shipped, operator
capture-device verdict PASS on VGA + composite; release v10.

**T9 — Pre-game settings screen** (operator ask 2026-09-07): let players
set difficulty, round time, game mode before the game starts. Stateless
first (defaults each power-on, no VMU); optional VMU persistence later.
New feature — needs its own design gate. Recon first: where the game
reads its game-assignment settings at boot (Naomi EEPROM/backup block —
the conversion currently stubs the native path, 00-status §What this
is), then a loader-side menu (the splash/preset_note screens are the UI
precedent) that writes the chosen bytes before handoff.

**T10 — Load floor + char-select transition cosmetics** (operator ask
2026-09-07, post-T3): (i) can the ~1 s GDEMU attract→START load shrink
further — run a `TIME=1` profile of that window FIRST to split remaining
disc time vs game-side unpack/init; if CPU-bound, it's the floor — don't
touch the driver on a hunch. (ii) the beginner→char-select circling
transition parks on a misaligned frame during the ~1 s pause
(operator screenshots 2026-09-07); options: pin the animation counter to
the aligned frame while loading (game-code surgery, needs recon) or just
shrink the pause via (i). Cosmetic; fund after T8/T9.

---

## T2 — profiling leg (2026-09-05: instrument + emulator control PASS; hardware leg owed)

Branch `phase7-pool`. Bounded task (brainstorm-approved design in chat,
no spec file): one timing instrument, one parser, one hardware leg, then
per-symptom verdicts gating T3/T4.

### Instrument: `SHIM_TIME=1` (`make gdi SERIAL=1 TIME=1`)

`gd_read_cart` (shims/src/gd.c — the single choke point every cart.c read
path routes through, both backends) stamps SH-4 TMU0 TCNT0 at entry and
exit and prints one line per delivered read:

```
SHIMTIME tcr=00000002                                  # once + on change
SHIMTIME o=<cart off> l=<len> s=<TCNT0 entry> d=<entry-exit ticks>
```

Timebase: the game's own TMU0 — reprogrammed by the game to TCR0=2
(P/64 = 781.25 kHz), TCOR0=0xFFFFFFFF free-running, ~92 min wrap (§T1
measurements, TMU0 verdict), so absolute stamps are a clean timeline at
1.28 µs/tick; the shim only reads it. `tcr=` is echoed so the parser
measures the rate instead of assuming it. Perturbation bound: one line ≈
53 chars ≈ 4.6 ms at 115200 baud, strictly lighter than the
hardware-proven round-4 `CRC=1` instrument (like-sized line + ~50
cycles/byte CRC over every delivered byte) which manufactured no
symptoms. Exit stamp is sampled before any serial output so `d` never
includes print cost; the print does inflate the *next* gap by ~5 ms —
below every effect T2 hunts (loads: seconds; freezes: 100s of ms cadence).

`scripts/parse_shimtime.py <leg>` rebuilds the timeline: per-read driver
ms + implied KB/s, game-side gaps, gap-split bursts with driver duty %,
and re-read churn (identical `(o,l)` tuples delivered twice = the
eviction-then-reload signature). Wrap-safe, re-anchors on a TMU0
reprogram. Self-check `scripts/test_parse_shimtime.py` → `ok`
(down-counter math, wrap, reset re-anchor, burst split, churn).

Build hygiene (all verified 2026-09-05): `make test` exit 0; knob-off
`make gdi` md5-identical to release v8 (`track04` =
`ba63905ca7b551ca8de1451872f8420d` — the knob is invisible when off);
`make clean && make gdi SERIAL=1 TIME=1` → diag `track04` =
`e370a097faf2d23403d581447be31e63`, `SHIMTIME` present in `shim.bin`
(the `DEFS` gotcha check, tooling.md).

### Emulator control leg — PASS (`captures/phase7/t2-emuctl1`)

~106 s unattended attract, DC profile, diag build. 83 SHIMTIME reads +
`tcr=00000002` — exactly the T1 TMU0 verdict's value, live. Parser
output is self-consistent against known ground truth: 26-read boot burst,
the 1.5 MB preload, steady attract drip ~39 KB every ~1.5 s (= phase 2's
2.3 MB/min), zero churn in attract, and implied driver throughput ~48
MB/s — the emulator's instant-read signature, exactly what hardware must
NOT show (GDEMU PIO expectation: ~1–2 MB/s; that number IS the
measurement). Capture needs `-config Debug:SerialConsoleEnabled=yes`
(tooling.md §build knobs, TIME=1 row).

### Hardware leg brief (operator, GDEMU, coder's cable) — OWED

Deploy the diag build (`make clean && make gdi SERIAL=1 TIME=1 && make
deploy`, md5 above; SERIAL=1 also lights the TEXHUD rows — known, fine).
Start `scripts/capture_serial.sh phase7/t2-hw-gdemu` BEFORE power-on.
One continuous leg, five scenes, rough wall-clock notes per scene
("load felt ~N s", "freezes at ~1/s while X"):

1. Boot → attract, let it run ~1 min.
2. Start at attract (the descending-tone load) → char select.
3. Dwell in char select ~30 s before confirming (the (c) rate window).
4. 1P match; have 2P join mid-match (the second reported long load).
5. A stage-8 scene for a few minutes where the microfreezes live
   (VS stage select reaches it fastest), then ctrl-C.

### Hardware leg — DONE (operator, 2026-09-05, `captures/phase7/t2-hw-gdemu.log`)

One continuous 600 s GDEMU session, diag build (`e370a097…`), all five
scenes walked. 420 SHIMTIME reads, 54.9 MB delivered, `tcr=00000002`
live (the T1 TMU0 verdict's exact value). Operator felt-times: char
select (descending tone) ~3 s, 1P stage load ~2 s, 2P join
("hi-rounder" screen) ~3 s, stage-8 load ~3 s; background microfreezes
on the character **loading** screen and during stage 8, a fraction of a
second each, ~1/s.

**Headline measurement: raw-ATA PIO tops out at ≈2.8 MB/s** (2,825
KB/s at every saturated burst — the number the emulator control leg
could not give). The read timeline maps to the operator's scenes
exactly (times = seconds from first read; duty = in-driver fraction of
the burst wall):

| t (s) | scene | bytes | wall | duty | felt |
|---|---|---|---|---|---|
| 0–2 | boot burst + 1.5 MB preload | 1.65 MB | — | — | — |
| 14–99 | attract drip | 38,912 B per ~1.5 s, 15 ms each | — | — | — |
| 108.7 | char-select entry (descending tone) | 2,723,840 | 1.18 s | 80.3% | ~3 s |
| 189.9, 206.1 | character picks | 63,488 + 30,720 | ms-scale | — | — |
| 226.3 | 1P beginner stage load | 6,131,712 | 2.32 s | 91.5% | ~2 s |
| 241.9 | 2P join reload | 8,400,896 | 2.98 s | 97.6% | ~3 s |
| 245–345 | 2P match drip | 38,912 B per ~1.05 s, 15 ms each | — | — | — |
| 347.4 | rematch reload (byte-identical 8,400,896) | 8,400,896 | 2.98 s | 97.6% | — |
| 386.0 | stage-8 load (VS stage select) | 6,082,560 | 2.44 s | 86.3% | ~3 s |
| 389–575 | stage-8 match drip | same 1.05 s cadence | — | — | freezes ~1/s |
| 599.0 | match exit read | 1,417,216 | 0.49 s | 100% | — |

The in-match drip is 6×38,912 B + 1×18,432 B per ~7.4 s ≈ 34 KB/s
(attract: same reads at 1.5 s cadence ≈ 25 KB/s — in family with
phase 2's 39 KB/s steady rate). Churn: 33 tuples ×2, 14.5 MB — ALL of
it whole-load repeats (the 8.4 MB stage pak twice = the rematch, etc.);
**zero cyclic mid-match re-reads**. Instrument overhead: 420 lines ≈
1.9 s serial total over 600 s, excluded from `d=` by construction;
TEXHUD mirrored only 68 summary lines (~1/9 s) — neither can fake a
~1/s symptom.

Side observations, dispositioned: `iea=00000001` sticky = SB_ISTERR
bit 0, the phase-5 **characterized-benign** per-tile ISP latch
(`phase5-hardware.md` §Round 8 — this leg's 16 IEE detail lines show
the identical signature: `itp` ≈ 22% of `lim`, both banks, space never
near exhaustion); `iee=0x4f08` (20,232 latches/10 min) is in family
with round 8's 33,033/45 min given these are all heavy match scenes;
**`ie2=00000000` — the queued bit-2 (TA parameter overflow) watch item
gets its first full-session ZERO** from the upgraded logger: bit 2
never fired across two 2P matches + stage 8.

### T2 verdicts (by the pre-registered attribution rules)

- **(a) Loads: DISC-BOUND — T3 gate OPEN.** The stage and join loads
  run at 91.5–97.6% in-driver duty, saturated at the 2.8 MB/s PIO
  ceiling; felt time ≈ burst wall ≈ bytes ÷ 2.8 MB/s. More throughput
  (G1 DMA) is the lever. Honest exception: the char-select ENTRY
  (descending tone) is only 1.18 s of disc in a felt ~3 s — the tone/
  anim window is game-side; T3 can shave ≤1.2 s there, not 3.
- **(b) Stage-8 microfreezes: NOT arena churn — T4 CLOSED (for this
  symptom).** Zero mid-match re-reads (the eviction-reload signature is
  absent; all churn is whole-stage reloads). The freeze cadence equals
  the drip cadence exactly (~1.05 s), each drip read blocking the CPU
  15 ms (≈1 frame) in polled PIO — the game thread IS the disc driver
  while it drains the FIFO. Remedy is T3-shaped: either faster transfer
  (15 ms → ~4 ms at DMA rates, under a frame) or async completion
  (kick+poll — `gd.c`'s recorded caveats apply). Matches the original
  (b) report coming from *release* play sessions — pre-instrument.
- **(c) DreamShell char-screen freezes: mechanism identified, one
  operator question open.** The char-select DWELL screen does **zero**
  disc I/O (110–226 s: two tiny pick-blips only) — so an idle-dwell
  freeze cannot be a disc stall on ANY backend, falsifying the "pure
  serial-link stall" guess for that exact screen. But the same ~1/s
  fraction-of-a-second signature appeared on THIS GDEMU leg on the
  character **loading** screen — where reads run — and the arithmetic
  closes cleanly there: the 38,912 B drip read = 15 ms at 2.8 MB/s
  (subtle) but **~78 ms at DreamShell's ~490 KB/s ≈ "fraction of a
  second, once per second"**; load-screen chunks (0.7–2.8 MB) = 1.4–
  5.7 s stalls each. ~~Pending: operator confirms which screen~~
  **ANSWERED (operator, 2026-09-06): the idle dwell screen itself** —
  "when I see a character and there is a green BG swirling, I see it
  freezes each ~1s"; first noticed on DreamShell where it is much more
  noticeable, then found on GDEMU too, subtler. ~~Reframe: (c) is NOT a
  disc stall and NOT closed by T3 — for the dwell screen the leg
  measured zero disc I/O~~ **WRONG, retracted by T2b (below): the
  "zero dwell I/O" claim was a timeline misattribution.** The drip was
  in `t2-hw-gdemu.log` all along: from t=28.1 s — squarely inside the
  char-select segment — single 38,912 B reads every ~1.5 s with
  occasional smaller ones (18,432 / 12,288 B), the exact signature this
  doc filed under "(b) in-match streaming". The dwell drip and the
  stage-8 drip are the SAME mechanism (a ~1/s streaming read, almost
  certainly music/voice), running on menus and in-match alike; T2's
  scene mapping folded the dwell reads into the entry burst's tail.
  ~~Root cause OPEN, two candidate mechanisms: (1) a game-side periodic
  ~1/s CPU task; (2) isoldr-resident periodic activity~~ both dead —
  killed by the T2b emulator control (drip present, `w` clean) and the
  moving `g` counter on both hardware backends.
  **Escalation instrument BUILT (T2b, 2026-09-06):**
  `FRAMEGAP=1` (`SHIM_FRAMEGAP`, tooling.md §Phase 7 knobs) — the live
  maple-kick hook `shim_maple_service` runs once per frame and cannot
  run during a blocking cart read, so its inter-call TCNT0 delta IS
  the felt frame time. Three GDDIAG-pattern cells at x=340
  (white-on-blue, serial-silent, dongle-safe): y236 worst frame ms in
  the last ~1 s window, y250 worst since boot, y264 `gd_read_cart`
  call count. With `SERIAL=1`, one `SHIMGAP w= x= g=` line per window.
  Emulator smoke sit (attract, ~100 s,
  `captures/phase7/t2b-emu-attract.stdout.log`): steady attract
  `w=0x10` = 16 ms = one clean frame; the boot attract-load burst
  shows `w=0x1b1` (433 ms worst frame) exactly while `g` steps
  1→0x1c, then `g` freezes and `w` returns to 0x10 — all three cells
  discriminate as designed. Distribution across 76 windows: 63×0x10
  (16 ms), 10×0x1d (29 ms), 1×0x18, 1×0x21, 1×0x1b1 (the boot load)
  — the emulator's attract baseline the dwell sits are judged
  against. **T2b leg protocol (operator):** sit on
  the 1P char-select dwell screen ≥30 s on each of (1) emulator
  (keyboard, stdout log — control), (2) GDEMU, (3) DreamShell; read or
  photograph the x=340 column *while the green BG swirls*. Verdict
  table: y236 elevated + y264 moving = disc path after all; y236
  elevated + y264 frozen = game-side periodic task (candidate 1 —
  emulator leg must then show it too); y236 elevated on DreamShell
  only, y264 frozen = isoldr-resident activity (candidate 2); y236
  pinned at 0x10-0x11 everywhere while the eye still sees hitches =
  not a CPU-loop stall at all (re-scope: video/TA-side).

  **T2b MEASURED (operator, 2026-09-06) — all three dwell sits done,
  verdict: (c) IS a disc stall — the same ~1/s streaming drip as (b),
  cost scaled by link throughput.** The `g` counter moved with every
  hitch on every backend; the pre-registered "y236 elevated + y264
  moving = disc path after all" row fired.
  - **Emulator** (`captures/phase7/t2b-emu-dwell.stdout.log`, 77
    windows): `g` steps ~1/window through the dwell — the drip is the
    game's own behavior, reproduced under Flycast — while `w` stays
    pinned 0x10 (reads are ~instant): 0 ms visible cost.
  - **GDEMU** (`captures/phase7/hw-t2b-1.log`, 86 windows, coder's
    cable): dwell runs `w=0x21` (33 ms = one dropped frame) in nearly
    every window with `g` stepping ~1/s — the T2-measured 15 ms PIO
    drip stall landing on a 16.7 ms frame. Transition max-hold
    `x=0x237` (567 ms). Matches "subtler on GDEMU".
  - **DreamShell** (TV reading, video kept by operator): dwell
    `w=0x42` (66 ms ≈ frame + ~50 ms stall) almost all the time,
    dropping to 0x21 twice for a couple seconds; transition peak
    0x11B (283 ms worst chunk), max-hold latches 0x11B; `g` starts
    0x20 and **increments on each hitch**, cadence ~1/s with
    occasional shorter gaps — the smaller drip reads (18,432 /
    12,288 B) visible in both hardware logs. Implied dwell-read
    throughput ≈ 38,912 B / ~50 ms ≈ **~780 KB/s serial-SD** —
    revises the earlier ~490 KB/s felt-time estimate upward; same
    mechanism either way.

**Net (T2b final): ONE root cause spans all three symptoms — blocking
synchronous cart service. T3 (G1 DMA / async cart service) is the
funded follow-up for (a), (b) AND (c); T4 stays shelved with no
symptom pointing at it.** The DreamShell-source check is unnecessary
(isoldr exonerated). The frame-gap meter is T3's acceptance
instrument, with hardware-proven baselines: GDEMU dwell `w` 0x21 →
target ≤0x11; DreamShell dwell `w` 0x42 → target ≈0x11 (an async
service hides the drip behind frames on both). T3 still starts with
`gd.c`'s recorded caveats (G1-mirror coherence, DMA completion IRQ
masked — the Cleopatra lesson) and is its own task with its own
approval.

### Attribution rules (the T2 verdicts, decided before the data)

- **(a) loads:** driver duty % across the load-window burst. Driver-
  dominant → disc-bound → T3 (G1 DMA / async). Gap-dominant →
  game-side unpack → record, no driver work (T3 declined).
- **(b) stage-8:** freezes with coincident reads + churn tuples on
  stage-8 offsets → eviction/reload → T4 (arena margin). No reads near
  freezes → not disc, not eviction-reload — re-scope before touching
  anything.
- **(c) char-select on DreamShell:** measured GDEMU-leg dwell rate
  (bytes/s + burst sizes) scaled to the ~490 KB/s serial budget. Burst
  size / 490 KB/s ≈ observed freeze length at ~1/s cadence → serial-link
  stall CONFIRMED by arithmetic, no DreamShell capture needed (the
  dongle owns SCIF — a serial capture there is physically impossible).
  Ambiguous → escalate to an on-screen-HUD DreamShell leg (GDDIAG
  pattern), only then.

---

**Wiring for the next session:** start from this doc + `docs/kb/00-status.md`.
T1 begins with the playbook loop (brainstorm → spec → plan), and its step 0
(throughput measurement) needs only the operator and a stopwatch.

---

## T3 — G1 DMA / async cart service (2026-09-06 BUILT; 2026-09-07 hardware round PASS — CLOSED)

Branch `phase7-pool`, commits `68fa3cc` (stage 1) + stage 2. Bounded task
(brainstorm-approved design in chat, both stages approved; no spec file).
Two stages, one shipping default each:

### Recon verdicts that shaped the design (decided before writing code)

1. **The drip cannot be deferred, only predicted.** The steady path is
   kick→wait in ONE call chain (`FUN_8c027f54` reaches the hooked wait
   directly — cart.c CART-WAIT-A header), and the kick itself is an
   unhookable RAM mirror write: the shim first learns of a transfer when
   the wait hook fires, and when that hook returns the buffer must be
   complete. So "async service" = **read-ahead**, not deferral.
2. **The drip is perfectly sequential.** `parse_shimtime`-domain audit of
   `captures/phase7/t2-hw-gdemu.log`: every drip read starts exactly where
   the previous ended (0x9800/0x4800 chunks chaining through one region,
   e.g. `o=0c467000 → +9800 → 0c470800 → …`), so a "next = end of last
   read" predictor hits ~100% after one miss per stream.
3. **A safe 64 KB ring home exists at the heap BOTTOM.** The heap-top seed
   is untouchable (16 MB-granular idiom; every corridor address depends on
   the exact 0x1000000 shift), but the heap *base* is a statically
   initialized pool word `[0x8c15ae68] = 0x8c1de200` (relocation-map.md
   provenance step 5), and the allocator carves every block from free-node
   TOPs with `remaining` derived from `size = top − base` (step 6) — so
   raising the base by 0x10000 changes NO allocation address, only
   capacity (−64 KB; −128 KB total on the syscall backend whose HEAP-CARVE
   already takes the top 64 KB for isoldr). Whole-image audit: exactly two
   words hold 0x8c1de200 — `0x13ae64` (BSS-clear bound, NOT patched) and
   `0x13ae68` (heap base, patched). Reloc entry `"0x13ae68"` in
   `scripts/reloc_patchset.json`; test image deliberately unpatched.

### Stage 1 — prefetch ring (`SHIM_PREFETCH`, default ON)

`shims/src/gd.c`: window `[pf_lo, pf_hi)` in cart-byte space over the
stolen `[0x8c1de200, 0x8c1ee200)`; ring index = `byte & 0xFFFF` (no anchor
state; pure math `pf_hit_plan` host-tested in `test/test_gd_math.c`).
Fill: ONE sector per frame from `shim_maple_service` via the normal
`gd_read` backend dispatch — no I/O state ever spans a frame, so there is
no reentrancy or paused-transfer hazard on either backend. Serve: at the
top of `gd_read_cart`, a request whole inside the window is a P2→P2 RAM
copy that falls through the same SHIM_TIME/SHIM_CRC tail as a real read; a
miss reads exactly as before and re-aims the window (sector-rounded down).
Fill rate ~120 KB/s (even on serial-SD) vs. drip consumption ~37 KB/s.

Never fatal: arming requires the heap word to read back PATCHED
(`PF_HEAP_BASE_NEW`) AND a main-mode boot; slice read errors, PFVERIFY
mismatches, and any game DMA dest overlapping the ring (new fence check in
cart.c) all DISARM sticky — `pf_stat[3]` records the site (1 unpatched, 2
test mode, 3 slice error, 4 fence overlap, 5 verify mismatch). Known
ceiling (recorded, not built): a second interleaved stream would ping-pong
the single window back to today's blocking behavior — visible as
`pf_stat[1]` climbing with `[0]` flat.

### Stage 2 — real G1 DMA (`SHIM_G1DMA`, default ON, raw backend only)

`gd_read_fad`: multi-sector bodies (≥2 sectors) into 32-aligned main RAM
go through the real `SB_GD*` engine (the game only ever touches the
mirror, so the real registers are the shim's alone); everything else —
bounce sectors, prefetch slices, the loader build, the whole syscall
backend — keeps the proven PIO path. Recipe and citations in the code:
KOS `dma_common` register order (g1ata.c:358-380), FEATURES bit0 latched
at packet exec (gdromv3.cpp:791-792, :1201), GDST kick/clear + GDLEND
convergence (:1349-1360, :1333-1336), abort via GDEN=0 (:1376-1379).
Real-hardware-only requirements flycast can't test: ISTNRM **bit 14**
masked in IML2/4/6NRM + acked per transfer (the HW-CONFIRMED Cleopatra
lesson, its gd.c:169-185/:200) and `SB_GDAPRO = 0x8843007f` (KOS ALLMEM
unlock, g1ata.c:114-118/:1116 — flycast stores but never enforces it,
sb.cpp:430). OCBI over the dest before every kick (discard, not flush —
Cleopatra's proven coherence rule). New failure site `GD_E_DMA` 9;
`gd_diag[6]` holds the final GDLEND.

### Emulator legs (2026-09-06, instrumented Flycast, 150 s attract each)

| leg | build | result |
|---|---|---|
| stage-1 verify | `SERIAL=1 TIME=1 FRAMEGAP=1 PFVERIFY=1` | 123 SHIMGAP windows, `w` pinned 0x10; **44 ring hits, all `PFVFY bad=0`**; tail chunk l=0x3000 also hit |
| stage-2 CRC | `SERIAL=1 TIME=1 CRC=1 FRAMEGAP=1` | 117 windows, same stream profile (g=0x54 p=0x2c); **83/83 SHIMCRC byte-exact vs track04** (DMA bodies included); 0 error markers, GCARVE rv=1 |

Emulator caveat for the next reader: flycast MODELS transfer time on the
DMA path (1.8 MB/s large-transfer drive rate, gdromv3.cpp:1255-1262)
where its PIO path answered in one poll — so emulator boot max-hold rose
0x1b1 → 0x3ae by MODEL, not by regression. GDEMU serves DMA faster than a
real drive; the hardware leg's SHIMTIME `d=` is the only real number.

### Operator hardware round — protocol + pre-registered verdicts (run 2026-09-07, results below)

Builds staged (gitignored): `build-t3/release/` (silent, all defaults —
release-v9 candidate, track04 `e731e34bc43b8612613efc1f1e74b4c0`) and
`build-t3/meter/` (`FRAMEGAP=1`, serial-silent, dongle-safe, track04
`b77e56d8b8b76c22e1e5821ad22fb8f3`; HUD x=340: y236 window-worst ms /
y250 max-hold / y264 gd calls / **y278 ring hits — NEW**).

1. **GDEMU dwell sit** (meter build, char-select, ~60 s): target y236
   `≤0x11` (T2b baseline 0x21). y278 climbing ~1/s = ring serving the drip.
2. **DreamShell dwell sit** (meter build + dongle, ~60 s): target y236
   `≈0x11` (T2b baseline 0x42).
3. **Stage-8 match** (meter build, GDEMU): microfreezes gone = (b) closed;
   this leg doubles as the heap-steal regression watch (stage 8 is the
   deepest allocator — an alloc failure here is the 64/128 KB steal
   biting; fallback = shrink `PF_RING_SZ`).
4. **Load stopwatch** (either build, GDEMU): attract→START and 2P join
   wall-clock vs. the T2 numbers — the stage-2 DMA win on (a).
5. **Full-campaign sanity** (release build): normal play-through.

Verdicts: targets met → respin release v9 from defaults and CLOSE
(a)+(b)+(c). Dwell `w` unimproved with y278 frozen → ring disarmed on
hardware — read `pf_stat[3]` (paint it via a follow-up diag) before
touching anything. (b) improved but (a) not → DMA rate on GDEMU ≈ PIO
rate; record, keep DMA (it can't be slower), (a) stays open honestly.

### T3 hardware round (2026-09-07, operator) — PASS, all targets met

Meter build `build-t3/meter/` on both backends, plus sanity extras:

| leg | result |
|---|---|
| 1. GDEMU dwell | **y236 = 0x10** (target ≤0x11, baseline 0x21) — pinned the whole char-select screen; one ~0.5 s 0x21 excursion at screen entry, once. **y278 ticks 1:1 with y264** = 100% drip hit rate. Background smooth, zero hitches. |
| 2. DreamShell dwell | **y236 = 0x10** (target ≈0x11, baseline 0x42) — entry burst 0x53→0x12C while the portraits populate, then pinned 0x10; one transient 0x42 (~1 s) after one char change out of several. Smooth. |
| 3. Stage-8 match (GDEMU) | **Microfreezes GONE** — full 2-round 2P match (both Ernulas), background smooth throughout; entry burst 0x23F→0x21→0x10 is the stage load behind the transition, not a dwell hitch. **Heap-steal regression watch clean**: the deepest-allocator scene ran both rounds + win animations with zero anomalies. |
| 4. Load stopwatch (GDEMU) | attract→START **~1 s** with the green background up immediately (no black gap — the T2-era felt multi-second hang with descending tone). Stage-select→stage-8 "feels faster" (untimed before). The stage-2 DMA win on (a). |
| 5. Sanity extras | GDEMU: story start, tutorial, stage-8 demo, attract full loop ×2 — clean. DreamShell: demo/story/tutorial + char-select entry — clean. |

Residuals (recorded, none gating):

- **DreamShell stage-8: two noticeable freezes in round 2** (`w` jumped
  0x42 right after each). (b) is CLOSED on GDEMU but only IMPROVED on
  serial-SD: a ring miss there costs a synchronous syscall read at
  dongle throughput, and the known single-window ceiling (§stage 1 —
  two interleaved streams ping-pong the window) or an SD latency spike
  degrades that one read to pre-T3 behaviour. Accepted for now;
  serial-SD is the courtesy path.
- DreamShell `w`=0x42 during win-animation close-ups — background not
  visible there; cosmetically irrelevant.
- DreamShell loads stay long (attract→char-select ~12 s, stage load
  ~7 s, beginner→char-select ~12 s): serial-SD link bandwidth; stage-2
  DMA never applies on the syscall backend (`gd_read_fad` not entered).
  Expected — recorded so nobody chases it as a regression.
- GDEMU max-hold (y250) F4 attract / 23F stage-8 entry = load-moment
  bursts behind transition screens, consistent with the meter's design.

**Verdict (per the pre-registered table): targets met → release v9
respun from defaults. (a) closed on the raw backend, (b) closed on
GDEMU / improved on DreamShell (residual above), (c) closed on both.**

**Release md5s v9** (respin 2026-09-07, `make clean` → `make release`,
`make test` green): `track04.iso` =
`e731e34bc43b8612613efc1f1e74b4c0` — byte-identical to the staged
2026-09-06 candidate (reproducibility check PASS); tracks 01–03
unchanged since v2 (`681fa4c8…`/`03c796f6…`/`244ae7e5…`, table at §T1
emulator gate). Supersedes v8. Zip re-packaged
(`build/[GDI] Senko no Ronde Special.zip` — embeds the ROM, never
upload).
The round spawned three new pool items from operator asks: **T8**
(video-signal dropout during loads — promoted from dcload-only benign
to open task), **T9** (pre-game settings screen), **T10** (load-floor
profile + char-select circle cosmetics).

---

## T8 — video-signal dropout (2026-09-07 RECON: mechanism pinned to the boot mode-set; fix design pending approval)

Branch `phase7-t8-videodrop` (post-0.2.0). Question: what drops the
operator's monitor for ~1 s "almost each time during loading"?

### Instrument — same-value SPG census (fork `ec9ac9dab`)

The phase-6 lesson ("change-only register logging hides redundant
writes", tooling.md blankrecon row) applied to the CLEO-SPG census
itself: every log site was gated on `PvrReg != data`, so a mode-set
re-run writing identical values — the exact thing a real monitor might
still drop sync on — was invisible. Fork commit `ec9ac9dab` adds a
`CLEO-SPG same` line (cap 1000/site, four independent counters) to the
SPG_CONTROL/SPG_LOAD, FB_R_CTRL, FB_R_SIZE and
VO_CONTROL-through-VO_STARTY census sites in
`core/hw/pvr/pvr_regs.cpp`. Caveat for reuse: some scenes re-assert
VO_CONTROL ~5×/frame from the relocated-BIOS region (`pc=8c010ab0/`
`8c010a4c`, measured t8-slot0) — that spam exhausts the shared
VO/geometry cap in ~4 s; the SPG_CONTROL/LOAD and FB caps stay armed.

### Census legs (captures/phase7/, release v9 disc, unattended)

| leg | span | census result |
|---|---|---|
| `t8-same-attract` (240 s) | boot → attract cycles (composite cfg) | ALL writes+sames land 17:43:22–:38 = the boot window; 3.5 min of attract (incl. demo loads — cart log shows the TA choreography running) touch NOTHING in the video block |
| `t8-same-start` (240 s) | replication of the above | identical 5-cluster shape (9/20/10/50/3) |
| `t8-slot0` (150 s) | August savestate resumed mid-scene, heavy streaming (133k cart-log lines) | zero `write` lines in 150 s; only the VO_CONTROL same-value re-assert spam above |

SOFTRESET census (the one sync-killer outside the SPG block —
bit 2 = PVR core reset; emulator models only bits 0/1 so it would be
invisible on screen): cart-log `PVRW SOFTRESET` lines across both big
legs show only values 0/1 (44k TA-reset toggles) + one 2/3 pair at
boot (the loader's own `main.c:482`). Never bit 2. Eliminated.

### Findings

1. **Post-boot, the game never touches the video block.** No SPG, VO,
   or FB_R writes — not even same-value ones — across attract loops,
   demo-battle loads, and a live in-game scene. In-game scene loads are
   video-silent; there is nothing to fix *at* those loads.
2. **The boot cascade on the VGA path is a real mode transition, and
   the prior KB claim is falsified.** tooling.md §GAME-VIA-DCLOAD had
   characterized disc boots as a "same-values no-op". The ernula-lili
   VGA boot census (change-only, so every line is a real change) shows
   the game's takeover mode-set (`pc=8c032140 pr=8c036cxx`) rewriting
   KOS's raster: SPG_CONTROL `150→100`, SPG_LOAD `020c0359→02110353`
   (525→531 total lines), SPG_HBLANK `007e0345→00880343`, SPG_VBLANK
   `00240204→00240208`, SPG_WIDTH, VO_STARTX `a4→a5`, VO_STARTY
   `12→24`. A ~0.5% vertical-frequency shift + sync-bit change = a VGA
   monitor drops and relocks (~1 s) at the NOW LOADING screen — **every
   boot, disc boots included**. Composite path: same cascade, then our
   `vid_geom_ntsc` restores six regs ~1 ms later (census
   t8-same-attract 17:43:35.60x).
3. Boot has FOUR video-block programmers in sequence: KOS loader
   (splash), the NOW-LOADING load engine (`8c0dxxxx`, all same-value),
   the relocated BIOS vid-init (`8c009xxx`/`8c019xxx`, FB churn +
   blank toggles), then the game's KAMUI2 mode-set (real changes).
4. Open question for the operator (splits two readings of "almost each
   time"): do drops recur at *in-game* loads (attract→char-select,
   stage entry), or only around boot / first NOW LOADING? The census
   says in-game loads write nothing, so a fix at the mode-set can only
   cure the boot drop; recurring in-game drops would need a different
   (non-reprogram) mechanism and a fresh hardware observation.

### Fix design (pending gate): SPG-GEOMETRY-PIN

Extend `shim_vid_init_main` (VIDEO-GEOM-HOOK — already wraps the
game's ONE display-init call, pool word `0x4edcc`): snapshot the six
`vid_geom_ntsc` registers (SPG_HBLANK/LOAD/VBLANK/WIDTH,
VO_STARTX/STARTY) live BEFORE calling the SDK entry `0x8c03d48e`,
restore them AFTER it returns — all cables, replacing the hardcoded
composite-only `vid_geom_ntsc` with one measured-live mechanism. The
monitor keeps the raster it locked on at the splash; the excursion
shrinks to ~1 ms (proven ride-through ordering: that's exactly where
vid_geom_ntsc already lands today). SPG_CONTROL is decided during
implementation by per-cable measurement (geo-vga0 / comp-dbg2 legs):
pin it only where pre/post differ AND the FB_R_SIZE interlace modulus
stays consistent. FB_R_CTRL (vclk_div), FB_R_SIZE, VO_CONTROL
(blank/unblank) stay game-owned. dcload path: the pin preserves
dcload's raster → fixes that drop too. Escalation if hardware still
drops: filter SPG writes inside a `FUN_8c032140` replacement (skip
while pinned). Verification: emulator census legs per cable (final
raster == splash raster), then operator hardware leg — VGA boot with
no monitor drop at NOW LOADING = PASS.

Lua input scripting for legs: dead end, recorded in tooling.md (the
fork binary ships without USE_LUA compiled in); savestate +
auto-advance legs and the census sufficed.

### T8 BUILT (2026-09-07): SPG-GEOMETRY-PIN — emulator legs PASS, hardware round owed

**Implementation** (`shims/src/util.c`, design approved pin-only):
`vid_init_pinned()` snapshots the six geometry regs (SPG_HBLANK/LOAD/
VBLANK/WIDTH, VO_STARTX/STARTY) live at wrapper entry — i.e. the raster
the monitor has been locked to since the loader splash, including the
relocated-BIOS blob's interim VBLANK/STARTX tweaks — calls the SDK
display-mode entry, restores them right after, and prints one `VIDPIN`
line on SERIAL builds. Both VIDEO-GEOM-HOOK wrappers
(`shim_vid_init_main`/`_test`) route through it; the hardcoded
composite-only `vid_geom_ntsc` table is deleted (subsumed). SPG_CONTROL
left unpinned by measurement: pre==post on both cables (0x100 VGA /
0x150 NTSC — geo-vga0 + t8-same-attract censuses; the ernula-lili
`150→100` change was an old-loader-era artifact). FB_R_SIZE, FB_R_CTRL
(vclk_div), VO_CONTROL (blank) stay game-owned. No knob: the pin
replaces the existing always-on fixup; the v9 build is the A-side.

**Emulator census legs** (fork `ec9ac9dab`, 150 s each, unattended;
emu.cfg Cable edit per phase-6 convention — the CLI override
`-config config:Dreamcast.Cable=0` does NOT take, see tooling.md):

| leg | cable | verdict |
|---|---|---|
| `phase7/t8-pin-vga` | 0 (VGA) | PASS — mode-set writes the arcade 31 kHz raster (SPG_LOAD `020c0359→02110353` etc.) at 18:23:16.665, pin restores all six at **.668 (~1 ms excursion)** to the exact live pre-call values (`020c0359/007e0345/00240204/03f1933f/ac/0028`); zero further SPG writes through attract; 0 SHIMERR; 195k cart-log lines, TA active at kill |
| `phase7/t8-pin-comp` | 3 (composite) | PASS — restore values byte-equal to the old `vid_geom_ntsc` table (`007e0345/020c0359/00240204/07d6c63f/a4/00120012`): behavior-identical to v9 on TVs by construction; 0 SHIMERR; attract renders |

**Release v10 CANDIDATE** (`make release` + `make test` green,
2026-09-07): `track04.iso` = `a77856d801e613d090cb879597921d60`;
tracks 01–03 unchanged since v2. Promotion to release v10 waits on the
operator hardware round below. Zip staged
(`build/[GDI] Senko no Ronde Special.zip` — embeds the ROM, never
upload).

**Operator hardware round — pre-registered verdicts:**

1. **VGA boot watch (the fix check):** cold boot the candidate on
   GDEMU + VGA, watch splash → black gap → NOW LOADING → attract.
   PASS = the monitor never loses signal after its first lock at the
   splash (v9 baseline: ~1 s drop/standby at NOW LOADING on almost
   every boot). PASS → T8 CLOSED, v10 promoted.
2. **Composite regression:** one boot on the TV — picture still
   centered, FREE PLAY visible (equivalence proven byte-level in the
   comp leg; this is the belt-and-braces look).
3. **Sanity:** brief play to char-select + one stage; DreamShell one
   boot if convenient (the pin runs at takeover, backend-agnostic).
4. **If VGA still drops at NOW LOADING:** the ~1 ms excursion is still
   too much for that monitor — escalation already sketched: filter the
   six regs inside a `FUN_8c032140` replacement (skip-while-pinned,
   zero excursion). Report, don't improvise.

After a PASS, decide T7 revival (splash-persist through the gap) by
taste: watch one stable-signal boot first — pool entry has the plan.

### T8 hardware round (2026-09-07, operator) — PASS, T8 CLOSED

**Operator instrument upgrade (record for all future video legs):** a
video capture device that switches to a color-bar test pattern the
instant the input signal drops — zero buffer time, 100% detection. By
eye the v9 drop was only catchable ~1 in 5 boots because its duration
sits right at the monitor's own timeout boundary; the capture device
ends that ambiguity.

**v9 re-characterization (control test on the old build first):** with
the capture device, drops re-confirmed on BOTH GDEMU and the serial
backend, and **only during the game's initial loading — never at any
later screen transition**. Matches the T8 census (the mode-set is
takeover-only, backend-agnostic) and retires the "almost every load"
reading for good.

**v10 candidate verdicts:**

| leg | verdict |
|---|---|
| 1. VGA boot watch (capture device) | **PASS — black screen through the load window, no color bars: signal held end-to-end** |
| 2. Composite regression | PASS — image correct, centered, no issues |

Per the pre-registered table: **T8 CLOSED, v10 promoted to release.**
Escalation path (FUN_8c032140 write filter) not needed — the ~1 ms
excursion rides through on real monitors, as bet.

**Release md5s v10** (respin from defaults, `make clean` →
`make release`, `make test` green): `track04.iso` =
`a77856d801e613d090cb879597921d60` — byte-identical to the staged
candidate (reproducibility check PASS); tracks 01–03 unchanged since
v2. Supersedes v9. Zip re-packaged (embeds the ROM — never upload).

## T7 REVIVAL BUILT (2026-09-07): SPLASH-PERSIST — emulator legs PASS, operator boot-watch owed

Approved design (operator, after the T8 hardware round): keep the
loader splash scanned out through the game's ~3.3 s boot init gap
instead of black, plus a loader-drawn "NOW LOADING..." line. The gap
itself cannot be shortened — its interior is the game's own zero-I/O
CPU/sound prep and the unmodified Naomi original shows the identical
3.36 s gap (§Black-gap control test, `phase6/blackgap-naomi` leg) —
so the fix is what the gap *shows*, not how long it is.

**Why shim-side one-shot works where BOOT-UNBLANK's ROM patches
failed.** The t8-pin census gives the exact ordering at gap start: all
three blank-set sites — mode-set `pr=8c036cea`, FB-config
`pr=8c036292`, display-off arm `pr=8c035398` — fire INSIDE the SDK
display-mode call that VIDEO-GEOM-HOOK already wraps, before the
wrapper's geometry restore runs (t8-pin-vga 18:23:16.665-.667: SPG
writes, blank trio, then restore at `pc=8c010864`). And the gap
interior has zero VO writes. So: clear VO_CONTROL bit 3 once at
wrapper exit, after the raster restore — the unblank sticks for the
whole gap, and the game's own gap-end unblank (`pr=8c035398`,
+3.36 s) degrades to a same-value no-op. Unlike the rolled-back
BOOT-UNBLANK `or #8→or #0` patches (v5), the blank stays ON during
the mode-set/FB-reconfig transient — the glitch-row flash class the
operator saw on v5 is structurally excluded — and the display-off
routine keeps its blank everywhere else. FB_R_CTRL needs nothing: its
fb-enable bit is already 1 through the gap (census).

**The two edits** (branch `phase7-t7-splash-persist`):

- `shims/src/util.c` `vid_init_pinned()`: `pvr[0xe8/4] &= ~8u` after
  the geometry-restore loop, with the ordering citation.
- `loader/main.c`: `bfont_draw_str_ex(..., 0x2104, 0, 16, false,
  "NOW LOADING...")` at rows 400-423, x=236, right after the splash
  memcpy — dark gray on the white splash, transparent draw. Drawn at
  splash time (not last-act-pre-handoff) so it also covers the
  loader's own disc read on slow backends (serial-SD). Rows 400-423
  sit inside the window the game repaints mid-gap (rows 385-434,
  splash-white + its first NOW LOADING glyphs — §Black-gap decorate),
  so the loader line hands off to the game's authentic text rather
  than stacking with it.

**Emulator legs (captures/phase7/, candidate build, both cables):**

| leg | verdict |
|---|---|
| `t7-persist-comp` (Cable=3) | PASS — game blank `pr=8c036cea` 21:12:34.209 → shim unblank `pc=8c01087c` +3 ms → ZERO blank writes across the gap → gap-end trio on schedule +3.36 s (game unblank = same-value n=26) → ARM up, attract presents, 0 SHIMERR |
| `t7-persist-vga` (Cable=0) | PASS — identical signature (blank .931 → shim unblank .935, gap end +3.36 s, game unblank same-value n=24), 0 SHIMERR |

**Visual evidence:** the fork's blank-edge VRAM dump (044a2fb6c
instrument) fires on the shim's own unblank — the decoded frame
(`t7-persist-{comp,vga}-blank0-08.png`) is the first scanned frame of
the gap: splash + NOW LOADING..., both cables identical. Decode
recipe recorded in tooling.md (the 32-bit-path bank interleave).

**Release v11 candidate:** `track04.iso` =
`5c5e1cc6a2958aab988875b49c90b303`; tracks 01–03 unchanged since v2.
Respin from defaults (`make clean` → shims → gdi → test) reproduced
it byte-identical, BUILD-TEST-GREEN.

**Pre-registered operator protocol (decides T7 revival):**

1. **GDEMU boot watch:** loader splash + "NOW LOADING..." → the ~2 s
   BIOS-blob window (untouched, today's black/garble) → splash +
   NOW LOADING back for the whole ~3.3 s gap (the game's own glyphs
   may appear over the lower third near the end) → game's NOW
   LOADING → attract. FAIL = any black gap after the BIOS-blob
   window, or a glitch-row flash (the v5 defect class).
2. **Serial backend boot:** same expectation.
3. **VGA regression (capture device):** no color bars — the T8 pin
   must still hold signal end-to-end.
4. **Composite regression:** image centered/clean as v10.

### T7 round 1 hardware verdict (2026-09-07, operator) — FAIL (cosmetic), root-caused

Operator boot-watch on the v11 candidate (`5c5e1cc6…`): splash + NOW
LOADING clean for ~3 s, then a flicker, then a garbage band near the
bottom (capture `Screenshot … 11.52.49 PM.png`), then — a fraction of
a second before the game's own NOW LOADING — evenly spaced red
vertical ticks across the lower third (`… 11.53.03 PM.png`). Also
vetoed on style: the bfont line "does not correspond to the splash
style" and shows no liveness; operator asked for a spinner in logo
colors.

Root cause (leg t7r2 series): the game pre-composes its NOW LOADING
scene INTO the framebuffer the splash occupies during the gap tail —
the red ticks are its loading-gauge frame, the band is tile data
copied from then-uninitialized memory (zeroed in Flycast = the
phase-6 "splash-white, invisible-to-harmless" reading; garbage on
real RAM). The blank always hid this; round 1's unblank exposed it.
The flicker is the game's own one-frame FB_R_CTRL enable toggle at
its (now no-op) unblank moment — present in v10 too, hidden by black.
Emulator could never catch the band/ticks: uninitialized-memory
content differs, and the single blank-edge dump sampled one moment of
a progressive compose.

### T7 ROUND 2 BUILT (2026-09-08): SPLASH-SIDE-BUFFER + spinner + typeset text — emulator legs PASS, operator round owed

Approved design, three parts:

1. **Side-buffer scanout** (`shims/src/util.c` vid_init_pinned): at
   wrapper exit the shim copies the splash frame (0x96000 bytes, P2
   32-bit path) to 32-path `0x260000` and points FB_R_SOF1/2 there,
   then unblanks. The game composes at its own base unseen; its first
   scene flip (`pr=8c037396`, ~+3.4 s) moves scanout off the copy by
   itself. **Placement is measured, not assumed** — first try
   0x100000 collided (game boot allocator packs VRAM upward from its
   0x08d000 scan buffer; flip-off dump showed writes at 0x123000+
   pre-flip). VRAM usage map (unblank→flip and flip→attract dump
   diffs): boot writes [0x08d000..0x140000), reaching 0x200000 by
   early attract, bank-1 mirror [0x48d000..0x600000); quiet band both
   windows = [0x200000,0x460000); 0x260000 = ~768 KB margin. Only the
   boot window matters — post-flip reuse of the copy is off-scan.
2. **Spinner** (`spinner_tick` in util.c, called from
   `cart_stream()`): 8-dot ring (4x4 px, radius 14, center 320,445),
   logo orange active dot / mid-gray trail, one step per 32 KB
   streamed. Gated on `FB_R_SOF1 == 0x260000` — appears at the game's
   first cart read, advances only while the disc actually works,
   permanently inert after the game's flip. Draws into OUR copy only
   (the v1 loadbar's defacing flaw is excluded by construction).
   Honest limit: during the fixed ~3.3 s zero-I/O CPU init nothing
   executes, so the ring appears only when disc work starts.
3. **Typeset text**: bfont draw deleted; "NOW LOADING..." is baked
   into splash.bin at build time (`loader/Makefile` splash rule →
   `scripts/splash_text.py` blends the committed coverage strip
   `loader/nowloading_strip.bin`, generated once by
   `scripts/gen_nowloading_strip.py` — Avenir Next Medium 30 px,
   +7 px tracking, the closest system face to the NAOMI logotype).
   Rows 396-417; strip is our own rendering, safe to commit.

**Verification (fork instrument `2215dbe48`: VRAM dump at the exact
FB_R_SOF1 write that leaves 0x260000):**

| leg | verdict |
|---|---|
| `t7r2-comp` (Cable=3) | PASS — repoint `val=00260000 pc=8c01089a`, unblank from shim, flip `val=0008d000 pr=8c037396`; copy-region diff unblank→flip: **0 foreign words** (64 = spinner's own dots); 0 SHIMERR |
| `t7r2-vga` (Cable=0) | PASS — identical signature, 0 foreign, 0 SHIMERR |

Decoded flip-off frame (`t7r2-comp-flipoff.png`): splash + typeset
NOW LOADING + spinner ring — the last frame shown before the game's
own scene, byte-clean. Round 1's garbage/ticks are structurally
invisible now (they land at the game's base, which nothing scans).

**Known residual (pre-registered):** the game's one-frame FB_R_CTRL
enable blink at its former unblank moment stays (game-owned, no hook
at that instant). Escalation if the operator objects: patch the
display-on arm's fb-disable toggle site.

**Release v11 candidate (round 2):** `track04.iso` =
`ca05d568a2769acec9d392ef9583d69c`; tracks 01–03 unchanged since v2.
Supersedes the round-1 candidate `5c5e1cc6…` (never released).

**Pre-registered operator protocol (round 2):**

1. **GDEMU boot:** splash + NOW LOADING (typeset) → ~2 s BIOS-blob
   window (unchanged) → splash returns; spinner ring appears when
   disc work starts and steps; NO garbage band, NO red ticks → game's
   own NOW LOADING → attract. FAIL = any garbage over the splash.
2. **Serial backend:** same; spinner should visibly rotate during the
   longer asset load.
3. **VGA (capture device):** no color bars end-to-end (T8 pin
   regression).
4. **Composite:** centered/clean (v10 regression).
5. **Note but tolerate:** the single-frame blink at gap end; report
   if it reads worse than a blink.

### T7 round 2 hardware verdict (2026-09-08, operator) — side-buffer PASS, decorations FAIL; ROUND 3 SHIPPED (bare splash)

**Operator round 2 verdict** (screenshot 2026-09-08 1.00.56 AM, repo
root, untracked): the splash survives the whole gap **byte-clean on
real hardware** — no garbage band, no gauge ticks, round 1's artifacts
gone. SPLASH-SIDE-BUFFER is hardware-proven. But both decorations
failed the eye: the typeset "NOW LOADING..." reads off-style against
the logotype, and **the spinner never appeared at all**.

**Spinner root cause — design-dead, not a bug.** The ring could only
advance from `cart_stream()`, and the gap interior has no cart reads:
the first read lands ~0.1 s before the game's first scene flip
(`phase5-hardware.md` §Loading bar v2 timeline: blank → 3.3 s of init →
first read at +3.319 s → flip). One ring draw right before the flip is
all it ever painted — the round-2 flip-off diff's "spinner-box diffs:
64" (= exactly one 8-dot ring) said this already; the emulator leg
verified the mechanism and could not model the perception.

**ROUND 3 (operator approved option A: bare splash).** Typeset-text
bake and spinner **deleted**: `scripts/splash_text.py`,
`scripts/gen_nowloading_strip.py`, `loader/nowloading_strip.bin`
removed, `loader/Makefile` splash rule back to plain bmp2rgb565,
`spinner_tick` gone from `shims/src/util.c`/`cart.c` (shim.map clean).
The side-buffer stays — the gap is the untouched splash, nothing else.

**Verification (subtractive change, one leg + byte-identity):**

| check | result |
|---|---|
| `make clean` → gdi → test | BUILD-TEST-GREEN |
| leg `t7r3-comp` (composite, dump-armed) SOF in/out | `val=00260000 pc=8c01089a pr=8c010864` in; `val=0008d000 pc=8c032140 pr=8c037396` out |
| SHIMERR | 0 |
| flip-off copy region vs `build/splash.bin` | **0 / 153600 words differ** (byte-identical — stronger than round 2's dump-to-dump diff: round 3's copy must equal the ground-truth splash exactly, and does) |
| VGA | not re-legged: change is subtractive, cable-dependent paths untouched since round 2's both-cable PASS |

**v11 candidate (round 3): track04 = `2149443002362b543ade8309c6294fcd`**
(tracks 01–03 unchanged since v2). Round-2 candidate `ca05d568…`
superseded, never released.

**GAPISR recon — the vblank ISR RUNS during the gap (round-4 lead,
not built).** Fork probe (holly_intc.cpp `Write_SB_ISTNRM`, commits
`c78d22f3d` v1 / `9a763076c` v2): count ISTNRM vblank-in/out acks while
FB_R_SOF1 == 0x260000. Result: **203 acks across the ~3.4 s window
(~60 Hz), ack site `pc=8c038f00 pr=8c02bf18` throughout**, consistent
on a plain leg (`t7r3-isr2a`, GAPISR-TOTAL n=203) and a dump-armed leg
(`t7r3-comp`, probe v1 hit its 40-line cap ~0.7 s in). This REVISES the
chat-round claim "no interrupts during the gap": that came from one
acks=0 leg (`t7r3-gapisr`, round-2 disc) which did not reproduce —
recorded as an unexplained outlier, suspected leg-hygiene artifact
(same-name rm+relaunch churn; see tooling.md). Mechanism agrees with
phase 5's vblank-registered per-frame callback (`FUN_8c02e7d8`'s
caller). **Implication:** a real gap spinner is a bounded follow-up —
trampoline a TCNT0-clocked ticker into the vblank path, self-gated on
`FB_R_SOF1 == 0x260000` (inert after the flip, draws only into our
copy). Operator chose the bare splash; build only on a fresh ask.

**Operator protocol (round 3, when next at the hardware):**
1. GDEMU boot: splash → ~2 s BIOS-blob window (unchanged) → splash
   back, **bare** (no text, no dots), clean through the gap → game's
   own NOW LOADING → attract. FAIL = any garbage or leftover text.
2. Composite + VGA capture device: same regressions as round 2
   (centered/clean; no color bars).
3. Still tolerated/known: the single-frame blink at gap end.

### T7 round 3 was DEFECTIVE (2026-09-08, operator): stale text-baked splash shipped; ROUND 4 SHIPPED — bare splash + vblank spinner

**Operator verdict on the round-3 build: text still there, both
splashes.** Root cause (build system, confirmed): round 2's text bake
edited `build/splash.bin` IN PLACE; no clean target removed it, so
round 3's `make clean` left the baked file, make saw it newer than
`splash.png`, and candidate `21494430…` shipped the stale bytes.
**The round-3 verification was circular:** the flip-off byte-check
compared the scanned copy against the SAME contaminated
`build/splash.bin` (0/153600 "pass"), and the decoded frame was sent
without being looked at — it shows the text plainly. Two rules burned
in: verify visual claims BY LOOKING at the decoded artifact, and
verify against the source of truth (`splash.png`-derived bytes), never
an intermediate the bug under test could have contaminated. Fixes:
loader clean rule now removes `../build/splash.bin`/`splash.bmp` (with
a warning comment), and the fresh splash.bin was decoded and visually
confirmed bare this time.

**ROUND 4 (operator asked: drop the text AND bring the spinner back,
real this time).** The GAPISR recon made it cheap — the game's vblank
ISR runs all gap, every pass through callback fn `0x8c038f00` via the
list-walker dispatcher (`jsr @r3` at `0x8c02bf12`, `r4` = node arg,
`pr=8c02bf18`). The game registers that fn at its own registrar
(`0x8c039060`: `mov.l 0x8c0391cc,r12` → `jsr @r11` register call,
`r5=r12`) through ONE literal-pool word — whole-.dat u32 scan for
`0x8c038f00`: exactly one hit, main image `dat 0x0191cc` (test image
carries no such literal; left stock — no spinner in test mode,
dev-facing, fine). New patch `VBL-SPIN` repoints it to
`shim_int_spin` (util.c): plain C, ticks `spinner_vbl()` then
tail-calls the original with `r4` preserved by the ABI (the callee
provably consumes only `r4`). The tick self-gates on
`FB_R_SOF1 == 0x260000` — live from side-buffer repoint to the game's
first flip, then permanently one PVR read + compare per interrupt.
Ring: 8 dots, radius 14 @ (320,445), logo orange `0xf345` active /
gray `0xad55` trail, one step per 8 calls. Strictly integer C (ISR
context, `-m4-single-only` shim).

**Verification (both cables, fresh splash ground truth):**

| check | t7r4b-comp | t7r4-vga |
|---|---|---|
| GAPISR-TOTAL (ISR healthy through the wrapper) | 203 | 202 |
| flip-off vs splash.bin | spinner-box 64 / **foreign 0** | spinner-box 64 / **foreign 0** |
| rotation (mid-gap dump @ack 100 vs flip-off) | dot 0 → dot 3 | dot 0 → dot 3 |
| SHIMERR | 0 | 0 |
| SOF in/out | clean pair | clean pair |

64 words = exactly one full ring; foreign 0 = the game's frame is
untouched, same guarantee as rounds 2–3. Rotation instrument: fork
mid-gap dump at ack 100 (`c2c668aca`); the 0→3 step delta also shows
the wrapper serves a couple of interrupt sources beyond vblank-in —
harmless (rotation slightly faster than the 1.07 s/rev vblank-only
math, still smooth). Decoded flip-off frame LOOKED AT this round:
bare logo + ring, no text. Fresh `splash.bin` also decoded + eyeballed
bare before building.

**v11 candidate (round 4): track04 = `3d98fb58154f93a616a8799994b27038`**
(tracks 01–03 unchanged since v2). Candidates `ca05d568…` (r2) and
`21494430…` (r3, defective) superseded, never released.

**Operator protocol (round 4):**
1. GDEMU boot: splash (NO text) → ~2 s BIOS-blob window (unchanged) →
   splash back with the small dot ring under the logo **visibly
   rotating** through the whole gap, no garbage → game's own NOW
   LOADING → attract. FAIL = text anywhere, frozen ring, garbage.
2. Serial backend: same boot; ring rotates through the gap there too
   (it is vblank-clocked, not disc-clocked).
3. Composite centered/clean; VGA capture device no color bars (same
   regressions as rounds 2–3).
4. Still tolerated/known: the single-frame blink at gap end.

### T7 round 4 hardware verdict (2026-09-09, operator) — FAIL: gap BLACK, splash+ring only FLASHES at gap end; ROUND 5 SHIPPED (per-vblank display re-assert)

**Operator:** "White splash without NOW LOADING, good, then black screen
for around 3 s, then splash with ring flashes for a fraction of a
second." Decoded: the copy, the SOF repoint and the spinner all work on
hardware (the flash shows the correct bare splash + ring from 0x260000)
— but the shim's ONE-SHOT wrapper-exit unblank does not stick on real
silicon: the display stays blanked through the gap, and the flash is
the game's own display-on arm (the round-1 "former unblank moment",
`pr=8c03538e`) revealing the copy for the last fraction of a second
before the first scene flip.

**Mechanism: NOT identified, and emulator-invisible.** New kill-proof
probes (fork `0f1d4cc6f`: GAPVO write mirror + GAPISR display-state
samples): in the emulator the shim's unblank is the ONLY
VO_CONTROL/FB_R_CTRL write in the whole gap window, and all 203
per-vblank samples show blank clear + fb enable, both cables —
whatever re-blanks on hardware has no emulator counterpart (round-1
lesson repeated: the emulator's zeroed-RAM/GL blind spots now have a
display-path sibling). Blank-edge transition census identical rounds
2–4 (9 transitions, all clustered at the mode-set).

**HINDSIGHT DOWNGRADE — rounds 2/3 "splash persists on HW" was never
operator-confirmed.** Their round-2/3 reports ("I see the text on the
second splash") are equally consistent with this same end-of-gap
flash; only round 1 (no side-buffer, no SOF repoint) clearly showed
~3 s of visible gap. The round-2 claim "side-buffer PASS on hardware,
splash byte-clean through the gap" is downgraded to: copy content
byte-clean (proven by the flash + emulator dumps), PERSISTENCE ON SCAN
unverified-on-HW, most likely absent since round 2.

**ROUND 5 defense (mechanism-agnostic):** we own per-vblank execution
now, so stop relying on a one-shot. `shim_int_spin` order flipped —
original handler FIRST, then the shim tick — and the tick, while
`FB_R_SOF1 == 0x260000`, RE-ASSERTS display-on every vblank:
clear `VO_CONTROL` bit3 if set, set `FB_R_CTRL` bit0 if clear
(conditional writes — zero extra PVR writes when state is healthy, as
in the emulator). Any re-blank, one-shot or periodic, is corrected
within one frame; after the game's flip the arm is inert as before.
The game's gap-end 5→4→5 FB toggle is in-line game code; worst
interleave is a same-value store. Sanity re-check of the VBL-SPIN
patch while here: whole-image disasm confirms the literal `0x8c0391cc`
has exactly ONE code reference (`mov.l` at `0x8c039060`) and r12 feeds
eight `register(idx, fn, …)` calls — eight sources share the callback
(hence rotation slightly faster than vblank-only; also why the wrapper
must stay arg-transparent, which plain C guarantees for the measured
r4-only contract).

**Diag knob (never ship): `SHIM_VBLROW=1`** — paints one 2×2 dot per
tick along row 470 of the copy; if round 5 still shows a black gap,
the operator's flash PHOTO becomes a measurement (dot count = ticks
that ran on hardware; ring position + row length localize when the
ISR ran). Escalation pre-registered: black gap again → respin with
`DEFS='-DSHIM_VBLROW=1'`, one more boot, photograph the flash.

**Verification (both cables):** GAPISR-TOTAL 203/202 through the
flipped wrapper; GAPVO: only the shim unblank writes in-window; state
samples blank-clear + fb-on across the window; flip-off vs fresh
`splash.bin` = spinner-box 64 / foreign 0; rotation midgap→flipoff
dot 0→3 (comp) / 0→2 (vga); SHIMERR 0; SOF pair clean;
BUILD-TEST-GREEN.

**v11 candidate (round 5): track04 = `cd7e07231c0fb1ca995bb6021b7119f4`**
(tracks 01–03 unchanged since v2; splash.bin md5 `b4ffd93d…` = the
visually-confirmed bare frame). Candidates r2/r3/r4 all superseded,
never released.

**Operator protocol (round 5):**
1. GDEMU boot: splash (no text) → ~2 s BIOS-blob window → **splash
   visible through the whole ~3 s gap with the ring rotating** → game's
   NOW LOADING → attract. The decisive observation: does the splash
   PERSIST (re-assert wins) or stay black with an end flash (re-assert
   loses → diag-build escalation above).
2. Composite centered/clean; VGA capture device no color bars.
3. Known/tolerated: one-frame blink at gap end.

# Phase 7 T1 — DreamShell serial-SD support: design spec

**Date:** 2026-09-03
**Status:** approved (design), pending implementation plan
**Charter:** `docs/kb/phase7-polishing.md` §T1 (the only must-have of
phase 7, runs first; operator ground rules 2026-09-03)
**Predecessor evidence:** Phase 6 Task 32 — DreamShell characterized
known-fail (`docs/kb/phase6-release.md` §DreamShell serial-SD control
test): isoldr serves BIOS-syscall GD reads correctly (NAOMI magic
passed), the loader's raw-ATA rehearsal then halts loud
(`GD_E_CHECK`, sense 5 ILLEGAL REQUEST — the raw path talks to the
physical drive, which holds the DreamShell boot disc).
**Precedent:** the Cleopatra port's DreamShell support — a
hardware-proven BIOS-syscall GD backend incl. the isoldr war stories
(`../cleopatra/shims/src/gd.c`, `../cleopatra/shims/src/gdstack.S`,
`../cleopatra/docs/kb/00-status.md` HW rounds 9–13 and the
DreamShell/isoldr rounds).
**Project:** static binary conversion of *Senko no Ronde Special*
(Naomi GD-ROM → Dreamcast). See `CLAUDE.md`, `docs/kb/00-status.md`.

## Purpose

Make the same release disc image boot and play through DreamShell
isoldr from an SD card on the serial port, without regressing the
GDEMU/optical path. The port's runtime disc path is raw ATA because
the loader places the Naomi RTOS kernel slice over the DC BIOS's
low-RAM GD driver state (`shims/src/gd.c` header); isoldr virtualizes
GD **at the syscall layer only**, so raw ATA can never work under it.
The syscall *vector table* (`0x8c0000b0–0xbc`) sits below `0x600` and
survives our kernel-slice placement — under isoldr the GDROM vector
points into isoldr's own resident driver, so syscalls stay alive
through the whole game run. T1 adds a second, syscall-based GD
backend, chosen once at boot by a probe.

## Step 0 — throughput gate (CLOSED, GO)

Measured 2026-09-03 (operator stopwatch, phase-6 Task 32 setup
re-run; recorded in `docs/kb/phase7-polishing.md` §T1 step 0):
isoldr launch → loader splash ≈ 7 s (~880 KB `1ST_READ.BIN` + isoldr
init); splash → red rehearsal halt ≈ 3 s = GD init + one
`cdrom_read_sectors` of the 1,515,512 B main image through isoldr's
syscall layer ⇒ **≈490 KB/s** sequential (eyeball band 370–740).
The charter's ~190 KB/s SCIF-ceiling assumption is disproven low.
Sustained in-game demand (2.3 MB/min ≈ 39 KB/s, Phase 2) fits with
~10× margin; a 10 MB scene burst projects to ~20–30 s. **Operator
verdict: GO** (this session).

## Decisions taken in this design (operator-approved 2026-09-03)

1. **Approach A — dual-backend GD driver.** Runtime cart reads
   dispatch on a boot-time flag: `raw` (today's `gd.c`, unchanged)
   on real-BIOS boots; `syscall` (new `gd_sys.c`) under isoldr.
   Rejected: **B** (own SPI/SD driver in the shim — owns card init +
   protocol + an image-location convention for zero gain now that A
   is confirmed feasible) and **C** (relocate the kernel slice so
   BIOS GD survives — phase-4-scale RE, last resort).
2. **Raw-first probe order.** The loader rehearsal tries raw ATA
   first; only on failure does it try the syscall backend. GDEMU
   boots therefore exercise exactly today's sequence.
3. **Supported DreamShell version: 4.0.4 (isoldr 0.8.4)** — the
   operator's installed version, source-verified (§Ground truth).
   Placement pins *(revised 2026-09-03, operator decision after the
   measurement falsified the low-RAM plan — §Memory contract)*:
   `memory = 0x8cff0000`, `heap = 0x8cff7a00`, backed by the 64 KB
   heap-top carve. Other presets are fatal (§Memory contract).
4. **Gate rig = the operator's** (console + dongle + DreamShell SD).
   The beta tester's dongle is bonus coverage. Single-rig honest
   limit recorded, as every phase before.
5. **8 KB private syscall stack** (the reserved `GD_STACK` slot),
   not Cleopatra's 16 KB — there is no free 16 KB anywhere in our
   map. Compensating control: stack canary + low-water diag; verify,
   don't hope.
6. **Recovery ladder at the probe stage only** *(revised
   2026-09-03: the Task-3 TMU scan found the game genuinely stops/
   reprograms/restarts TMU0 at two disassembly-verified sites, and
   isoldr's `CMD_INIT`/card-retry path spin-sleeps on a free-running
   BIOS-rate TMU0)*. `GD_SYS_FIRST_LADDER = 0`: no unconditional
   post-handoff `InitSystem`+`CMD_INIT` before the first stream —
   the loader-context probe (pre-handoff, timers BIOS-owned)
   exercises the backend instead. The between-attempt retry ladder
   stays; its residual risk (mis-timed isoldr sleeps under the
   game's TMU0 programming, error instead of recovery) is recorded
   as an accepted failure shape: a failed retry dies loud, it does
   not hang the happy path.
7. **Three fork measurements land before shim code** (§Pre-code
   measurements) — they convert "no evidence of collision" into
   "positive evidence of none".
8. **The maple `rcv` floor fix ships with T1**: `maple_service()`
   accepts any 16 MB-window receive pointer and writes replies there
   (`shims/src/main.c:438`); one line of floor (match `cart.c`'s
   `DEST_LO` fence) makes syscall-vector survival structural instead
   of incidental.

## Ground truth (recon, 2026-09-03)

Three tracks, full reports summarized here. isoldr citations are
against the clone in `tools/dreamshell-src` (gitignored; see
`docs/kb/tooling.md` §Phase 7: DreamShell source): upstream is
**DC-SWAT/DreamShell** (the charter's `DreamShell/DreamShell` URL is
a 404), HEAD `9b59b44` (isoldr 0.8.5) + tag `v4.0.4.Release`
(`5cc1200`, isoldr 0.8.4 — the operator's version, checked out at
`tools/dreamshell-4.0.4`).

### isoldr 0.8.4 facts (all verified in the v4.0.4 tree)

- **Dispatch:** vectors at `0xac0000bc`/`0xac0000c0` route r7 through
  an 18-entry table: fn 0 `gdcReqCmd`, 1 `gdcGetCmdStat`,
  2 `gdcExecServer`, 3 `gdcInitSystem`, … (`gdc_syscall.s:242-279`;
  identical file in 4.0.4 and HEAD). Lock byte `0x8c00002d` is
  `tas.b`'d on every syscall — below `0x600`, survives our slice.
- **Read command:** `CMD_PIOREAD=16` (`CMD_DMAREAD=17`), params
  `{start sector (FAD), count, dst pointer, unused}`
  (v4.0.4 `syscalls.c:440,509`), sector size defaults 2048.
  `GETTOC=18` is force-completed as a no-op; `GETTOC2=19` is real.
  Execution is a coroutine: `ReqCmd` queues, each `ExecServer` call
  resumes `gdcMainLoop()` until it yields; ≥2 pumps per read; the
  FatFs + SPI work runs **on the ExecServer caller's stack** (only
  ~30 words park in the blob at yield, `gdc_syscall.s:233-240`).
- **Serial-SD path is fully polled.** Bit-banged SPI on SCSPTR2;
  every byte routine wraps itself in `irq_disable/restore`
  (`dev/sd/spi.c` — identical 4.0.4/HEAD); no IRQs, no DMA, no
  timers in the transfer path. Caveat: **TMU0** is assumed
  free-running BIOS-style for card init/retry-reinit and `CMD_INIT`
  (`timer_spin_sleep_bios`); see Risks.
- **Cache discipline:** the driver stores through exactly the
  pointer in `param[2]`; after `CMD_PIOREAD` it deliberately does
  **not** purge (v4.0.4 `syscalls.c:517`). Passing a **P2 pointer**
  makes the path alias-safe for our P2-reading shim with no
  maintenance at all.
- **Placement:** loader is linked for `0x8ce00000` and literal-
  patched to any address at load time; GUI preset list includes
  `0x8c004000` (the default); per-game preset file keys `memory =`
  and `heap =` exist in 4.0.4 (`modules/isoldr/preset.c:309-310`).
- **Resident size (built from the v4.0.4 tag, sh-elf-gcc 15.2.0):**
  `sd` blob text+data+bss = 29,928 B; + 1 KB params + 32 ⇒
  loader_end ≈ **`0x8c00b908`** at the `0x8c004000` placement.
- **What our kernel slice stomps:** only isoldr's two firmware-
  redirect stubs at `0x8c001000`/`0x8c0010f0` (for games that call
  the firmware GD entry directly). Harmless — we call through the
  `0x8c0000bc` vector exclusively.
- **Handoff state to our loader:** SR with IRQs masked,
  VBR=SP=`0x8c00f400`, caches flushed (`startup.s:135-205`) — KOS
  re-initializes all of it; explains why phase-6's boot worked.

### Our low-RAM map (audit verdicts)

- **The candidate hole is real but tops out lower than chartered:**
  usable `0x8c003800–~0x8c00e800`, not `–0x8c010000`. Boot-stack
  floor: `0x8c00e864` (118 Naomi SP samples,
  `docs/kb/boot-binary.md`), DC-side hard datum `0x8c00e940` with
  the error loop known to run deeper, unmeasured
  (`docs/kb/phase5-hardware.md` §hang autopsy). Above that:
  VBR=`0x8c00f400` + handlers, and the game actively memsets
  `0x8c00fc00–0x8c00ffff` at boot. isoldr blob + pinned heap must
  stay under `0x8c00e800`.
- **Nothing of ours touches the hole**: kernel slice ends exactly
  `0x8c003800`; next copy record starts at `SHIM_BASE 0x8c010000`;
  no zero-fill in between; the shim's cart path is fenced at
  `DEST_LO 0x0c01f000` (`shims/src/cart.c:45`). Honest limit: the
  hole has never been *write-watched* — see Pre-code measurements.
- **Hardware precedent for the slot:** the phase-6 GAME-VIA-DCLOAD
  leg ran the full port to attract with dcload resident at
  `0x8c004000` (`docs/kb/tooling.md` §dcload). Proves placement
  compatibility; does NOT prove survivability (dcload didn't need to
  survive; its `0xb400` extent + `0x8c00f400` stub would in fact be
  eaten by the game's boot stack and VBR — isoldr's 31 KB blob is
  what makes the slot viable).
- **Sub-`0x600` (vector table) survival:** loader, handoff walker
  and cart path provably never write below `0x8c000600`; the one
  unguarded path is `maple_service()`'s reply pointer (decision 8).
- **Shim budget:** code occupancy `0x1ad8` of `SHIM_CODE_MAX
  0x4000` ⇒ ~9.3 KB free for `gd_sys.c` + `gdstack.S` (Cleopatra's
  equivalents are ~430 source lines total — fits). `GD_STACK_BOTTOM
  0x8c016000`–`GD_STACK_TOP 0x8c018000` (8 KB) is reserved, zeroed
  by record #2, and currently unused ("gdstack.S deleted Task 10" —
  `shims/Makefile`); this design revives exactly that slot.

### Cleopatra gotchas adopted wholesale

Their KB records the failure modes on this hardware class; we port
the fixes, not rediscover them (`../cleopatra/shims/src/gd.c`,
`gdstack.S`, `../cleopatra/docs/kb/00-status.md`):
G1 ladder (`InitSystem` on SEND-refused), G2 `NOT_FOUND` pickup
window (1M pumps), G3 4-attempt retry with `CMD_INIT` between,
G6 private stack (isoldr's FatFs kills a ~2 KB game stack),
G7 FPU quarantine (isoldr's memcpy clobbers both banks + FPSCR;
the real BIOS driver is integer-only), G8 MMUCR AT=0 window gated
on the isoldr fingerprint (`[0x8c0000c0] == [0x8c0000bc]+8` OR
entry RAM-offset ≥ `0x10000` — an unconditional toggle broke
Flycast's dynarec, and senkosp also runs MMU-on), G12–G14 on-screen
syscall-phase diag (TV-debuggable, throttled, never shipped),
G15 non-zero `.data` init convention, live vector deref per call.

## Design

### 1. `shims/src/gd_sys.c` — the syscall backend

Port of Cleopatra's `gd_read_sectors`: build `param = {fad, n,
dst_P2, 0}`; `ReqCmd(CMD_PIOREAD)`; pump `ExecServer` + poll
`GetCmdStat` every iteration; `COMPLETED` is the only success;
`<= FAILED` latches `stat[0]` into `gd_last_err` and retries;
`NOT_FOUND` tolerated for 1M pumps; 100M-pump guard `shim_die`s
loud. 4 attempts; between attempts `gdGdcInitSystem` then
`CMD_INIT` through the same machinery; ladder also runs once
unconditionally before the first stream (decision 6). Buffers are
passed as P2 (uncached) — no cache maintenance needed on the PIO
path (isoldr stores through the given pointer; PIOREAD doesn't
purge, P2 makes that moot). Errors surface through the existing
`gd_fail`/`shim_die` conventions.

### 2. `shims/src/gdstack.S` — the call trampoline (revived)

Port of Cleopatra's `gdc_call`, adjusted to our constants: swap to
the private stack at `GD_STACK_TOP 0x8c018000` (8 KB, decision 5)
with a canary word at `GD_STACK_BOTTOM` + a low-water diag readable
on-screen; full FPU quarantine (both banks + FPSCR/FPUL, run the
syscall under KOS-default FPSCR); MMUCR save→AT=0→restore gated on
the isoldr fingerprint probe (G8, verbatim); live deref of
`*(u32*)0x8c0000bc` per call. Not reentrant — same structural
argument as Cleopatra: every call sits sequentially in the game's
cart-service context, and nothing else in the shim calls GD.

### 3. Dispatch

One backend flag in the `SHIM_STATE` block (`shim_iface.h`),
seeded by the loader at staging exactly like the boot-mode word
(`loader/main.c:263` precedent): `0 = raw`, `1 = syscall`.
`gd_read_fad()` dispatches on it at the sector-read level;
`gd_plan()` and the head/body/tail walk in `gd_read_cart()` are
shared, untouched. `gd.c`'s raw path stays source-identical
(regression criterion).

### 4. Boot probe (loader rehearsal, `loader/main.c` rehearsal block)

Today: KOS read → magic check → raw-ATA rehearsal on the same
sector → halt on any failure. New: on raw failure, rehearse the
syscall backend against the same sector and byte-compare vs the KOS
buffer; on match, backend=syscall, `say("cart read OK (syscall)")`,
continue to staging; halt red only if both fail (message names both
errors). The probe IS the detection — no isoldr signature sniffing.
Phase-6 evidence already shows the raw probe fails *cleanly* under
DreamShell (ILLEGAL REQUEST, no hang). Loader-side syscall calls
follow Cleopatra's loader rehearsal shape (KOS live, no IRQ
masking needed for the syscall path — KOS's own driver already
pumps this server; the raw rehearsal keeps its existing IRQ-off
window).

### 5. Memory contract + operator instruction

**REVISED 2026-09-03 (operator decision, after the pre-code
measurements falsified the original contract).** The original plan —
isoldr at `0x8c004000` in the low-RAM hole — is dead: the DC-profile
write-watch legs (`captures/phase7/hole-attract3.log`) measured 3,362
diverged bytes in `0x8c009e10–0x8c00bfff`, byte-exact-matched against
`tools/ram-snapshot.bin` as **live Naomi RTOS TCB-table content**
(slot 47+ of the 0x200-stride table at `0x8c004000`) — the kernel
slice's RTOS actively uses its TCB region on the DC port. The
quiet-in-attract remainder (25.5 KB) is the same live table's unused
portion, and no isoldr build fits it anyway (slim no-CISO/no-multi
build still ~3.5 KB over). Low RAM is unsound for any resident blob.

**The carve:** isoldr lives at the top of the game's relocated heap
instead. A shim hook, run once after the game creates its syMalloc
heap `[0x8c1de200, 0x8d000000)` (`FUN_8c085b00`), pokes the heap's
top down to **`0x8cff0000`** — carving 64 KB the allocator can then
never touch (tail-carving allocator: the entire layout shifts down
rigidly by 0x10000, low 16 bits preserved — same mechanism the
16 MB relocation already proved, weaker alignment preservation, see
Risks). **The poke is conditional on backend == syscall**: real-BIOS
boots (GDEMU/optical) keep the full heap and byte-identical behavior.

| Range | Owner under DreamShell |
|---|---|
| `0x8c0000b0–0xe0` | syscall vectors — survive (below `0x600`) |
| `0x8c000600–0x8c003800` | our Naomi kernel slice (unchanged) |
| `0x8c003800–0x8c00ffff` | game/RTOS (TCB table, boot stack `bootmin=0x8c00e7ec` measured, VBR, scratch) — nothing of ours |
| `0x8c010000–0x8c018000` | shim window (incl. revived 8 KB GD stack) |
| `0x8c1de200–0x8cff0000` | game heap (top poked, syscall boots only) |
| `0x8cff0000–≈0x8cff7908` | isoldr `sd` blob (31 KB, v4.0.4 measured) |
| `0x8cff7a00–≈0x8cff9ee0` | isoldr heap (pinned; bound ≤9,432 B measured) |
| `0x8cfff000–0x8d000000` | reset-stub top page (reboot path only; above isoldr's extent — harmless) |

Operator pins in the isoldr per-game preset: **`memory =
0x8cff0000`** (a stock GUI preset), **`heap = 0x8cff7a00`**; plain
`sd` firmware (no CDDA — the game has no CDDA; audio is
AICA-streamed from cart data). Fatal alternatives, recorded so
nobody retries them: every low-RAM option (`0x8c000100–0x8c008000`)
lands under the kernel slice or inside the live TCB table;
`0x8cff4800` would force an unaligned 46 KB carve (allocation shift
0xb800 preserves only 11 low address bits — the 64 KB carve's
low-16-bit preservation is the safety argument); the lower high
presets (`0x8cfc0000–0x8cfe8000`) waste 32–192 KB of heap for no
gain; `0x8dfc0000` needs 32 MB; `HEAP_MODE_AUTO` must not be used —
pin the heap explicitly.

### 6. Pre-code measurements (fork legs, before any shim code)

1. **Write-watch the hole:** widen the fork's `SHIMWATCH2` window
   to `0x8c003800–0x8c010000`, re-run the three regimes (attract,
   played match, test menu) → positive evidence the game never
   writes the isoldr slot.
2. **DC boot-stack low-water:** PC-scoped `r15` min-watermark on
   the boot cluster (the fork's `SPWATER` probe + the
   `sp_consistent` construction) → real ceiling for blob+heap.
3. **Decode the two step-11 fill-loop pool bounds**
   (`0x8c02122c–0x8c02123c` pools, `docs/kb/boot-binary.md`) from
   `tools/ram-snapshot.bin` → close the last undecoded low-RAM
   writer. Low probability of a hit, non-zero, four unpack calls.

Plus one static check: TMU0 writers in the game image (Ghidra xref
over `0xffd80008–0x10` TCR0/TCNT0/TCOR0) — see Risks.

### 7. Verification

- **Host:** `make test` extended — dispatcher unit test (flag →
  backend selection), `gd_plan` suite unchanged.
- **Emulator (unattended):** `FORCE_SYSCALL=1` build flag forces
  backend=syscall on a normal virtual disc; Flycast HLEs GD
  syscalls statelessly, so the whole game runs on the new backend
  post-handoff (Cleopatra G11). Attract soak + existing CRC/TEXERR
  instruments clean. Plus a release-config regression leg (backend=
  raw, byte-path identical to phase-6 release behavior).
- **Hardware (operator, stop-and-wait):** all DreamShell legs are
  **serial-silent** (dongle owns SCIF; release `LOADER_SERIAL=0`
  already enforces this; never `SERIAL=1` with the dongle attached —
  standing rule). Diagnostics = on-screen only: the ported
  syscall-phase tracer + stack low-water cell behind a diag flag
  (never shipped, G14). Legs: DreamShell boot → attract; played
  match; then GDEMU regression boot leg on the same build.

## Exit criteria

1. **DreamShell boot:** the release disc image boots through isoldr
   (pinned preset, operator rig) to attract — no red screen, no
   hang. Backend probe visibly selected syscall.
2. **DreamShell play:** a full match played (operator-attested);
   load times reported and accepted per step-0 GO.
3. **GDEMU regression:** same build boots and plays on GDEMU;
   `gd.c` raw path source-identical; `make test` green; release
   rebuild reproducible with md5s re-recorded (disc bytes change —
   shim grew — same convention as #26/#28).
4. **Probe totality:** GDEMU boot → raw chosen; DreamShell boot →
   syscall chosen; both-fail still halts red and readable
   (emulator + hardware evidence).
5. **Emulator control:** `FORCE_SYSCALL` attract soak clean
   (instruments green), unattended.
6. **Pre-code measurements banked** with verdicts in the KB
   (hole write-watch, SP low-water, fill-pool decode, TMU0 check).
7. **KB written:** `docs/kb/phase7-polishing.md` §T1 results,
   `docs/kb/tooling.md` records (DreamShell clone/build, new legs),
   `00-status.md` advanced.

**Honest limit:** single rig (one console, one dongle, one
DreamShell install at 4.0.4); Flycast cannot emulate the serial-SD
dongle, so the end-to-end verdict is hardware-only by construction.
Other isoldr versions/devices (IDE mods, GDEMU-DreamShell) are
untested and out of scope.

## Risks / open questions

- **TMU0 collision — RESOLVED (2026-09-03, Task 3):** the game
  writes TMU0 (stop/reprogram/restart, two sites, disassembly-
  verified). Decision 6 revised accordingly: ladder at probe stage
  only; retry-path residual risk accepted (dies loud, not a hang of
  the happy path).
- **Heap-top carve correctness (new, from the placement revision):**
  the poke must hit every field the allocator consults (top/end and
  any cached capacity/limit) — Task 3b pins them from `FUN_8c085b00`
  disassembly + RAM-snapshot cross-check before any code. The 64 KB
  shift preserves low 16 address bits of every tail-carved block
  (the 16 MB relocation preserved 24 and was proven; no absolute
  heap-address constants exist per Phase 3's exhaustive scans) —
  the FORCE_SYSCALL emulator soak with the carve active is the
  behavioral gate before hardware. Carve is conditional on
  backend==syscall, so GDEMU boots are structurally unchanged.
- **8 KB stack sufficiency:** mitigated by canary + low-water diag
  (decision 5); if the watermark says tight, the fallback is
  shrinking `SHIM_BOUNCE`'s neighborhood or spilling into the
  `0x8c01f000` spare page — decided then, not now.
- **Boot-stack depth below the DC datum:** the error loop runs
  deeper than `0x8c00e940`, unmeasured. The SP low-water leg
  (pre-code measurement 2) closes this before placement is final.
- **isoldr `ReqCmd` refusal on wedged state:** `GDC_CHN_ERROR` (0)
  when not IDLE — covered by the ladder (G1) + distinct on-screen
  error codes.
- **isoldr heap growth is unbounded by the `heap =` pin:** the key
  pins the base address, not a ceiling. FatFs state is a few KB
  (MAX_OPEN_FILES=3), so `0x8c00c000 + growth < 0x8c00e800` is
  expected but not yet proven — the plan's recon task reads
  `malloc.c`'s allocation pattern in the v4.0.4 tree and bounds the
  worst case before the operator instruction is final.
- **Sequential-read throughput ≠ in-game throughput:** 1,590
  smaller reads pay per-read overhead (SPI command latency per
  chunk). Step-0 GO stands; if real loads disappoint, that's T2/T3
  territory (profiling, async), not T1 scope.

## Out of scope

T2–T7 (profiling, G1 DMA/async, stage-8 margin, Ernula watch,
dev-disc, boot cosmetics); CDDA-capable isoldr builds; isoldr
versions other than 4.0.4 (should work ≥4.0.x — preset keys and
ABI verified stable to HEAD — but only 4.0.4 is gate evidence);
DMAREAD on the syscall backend (PIOREAD only, same reasoning as
the raw path's PIO-only ponytail note); any change to the raw
backend.

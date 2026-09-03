# Phase 7 T1 — DreamShell Dual-Backend GD Driver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The same release disc image boots and plays through DreamShell
isoldr (serial-SD dongle) via a new BIOS-syscall GD backend, chosen by a
boot-time probe, with zero change to the GDEMU/optical raw-ATA path.

**Architecture:** Port Cleopatra's hardware-proven syscall backend
(`../cleopatra/shims/src/gd.c` PIO loop + `gdstack.S` trampoline) as
`shims/src/gd_sys.c` + `shims/src/gdstack.S`; dispatch per sector-read on a
`SHIM_STATE` flag the loader seeds after a raw-then-syscall rehearsal probe.
Three fork measurements land first (they de-risk the memory placement),
then code, then emulator legs, then operator hardware legs.

**Tech Stack:** freestanding SH-4 C + asm (sh-elf-gcc, `/opt/toolchains/dc`),
KOS loader (via `../cleopatra/tools/kos/environ.sh`), instrumented Flycast
fork (`../flycast4naomi2dreamcast` source of truth, built in
`../cleopatra/tools/flycast-src`), DreamShell 4.0.4 / isoldr 0.8.4
(recon clone `tools/dreamshell-src`, v4.0.4 worktree `tools/dreamshell-4.0.4`).

**Spec:** `docs/superpowers/specs/2026-09-03-phase7-t1-dreamshell-design.md`

## Global Constraints

- Branch: `phase7-polishing`. `main` stays releasable (closed beta live).
- **`gd.c`'s raw path stays source-identical** except the one dispatch
  call site named in Task 6 (spec decision 1 / exit criterion 3).
- **Never commit ROM/BIOS-derived bytes** (`build/`, `tools/`, captures are
  gitignored — keep it that way).
- **All DreamShell hardware legs are serial-silent**: the dongle owns the
  SCIF pins. Never build the operator's DreamShell image with `SERIAL=1`.
  Diagnostics are on-screen only.
- **Operator legs stop-and-wait** for the human; unattended emulator legs
  use the one-call foreground pattern; kill Flycast by PID (memory:
  operator-leg-protocol).
- Every hardware/behavioral claim recorded in the KB carries a citation;
  fork edits are committed in `../flycast4naomi2dreamcast` (source of
  truth), pushed, then `git pull --ff-only` in
  `../cleopatra/tools/flycast-src` before rebuilding (`docs/kb/tooling.md`
  §Instrumented Flycast).
- Shim code+data budget: `SHIM_CODE_MAX 0x4000`; link asserts in
  `shims/shim.ld` enforce it — a size failure is a build failure.

---

### Task 1: Fork instruments — widened hole write-watch + boot-SP watermark

**Files:**
- Modify: `../flycast4naomi2dreamcast/core/hw/naomi/naomi.cpp` (`cartlog_shimwatch2`, ~line 418)
- Modify: `../flycast4naomi2dreamcast/core/hw/naomi/cartlog.cpp` (~line 19, `cartlog_sp_sample` / `cartlog_sp_water`)
- Modify: `../flycast4naomi2dreamcast/core/hw/gdrom/gdromv3.cpp` (one `cartlog_sp_sample` feed)

**Interfaces:**
- Consumes: existing `cartlog_sp_sample(unsigned sp)` / `cartlog_sp_water()` (`cartlog.h:21-22`), existing `cartlog_shimwatch2()` baseline-and-compare pattern.
- Produces: `SHIMWATCH2` lines now covering `0x8c003800–0x8c00bfff` (capped at 64 lines + a `SHIMWATCH2 CAP` line), and a new `BOOTSP min=%08x` field on the `SPWATER` line. Tasks 2's legs parse these.

- [ ] **Step 1: Widen the shimwatch2 window (bounded, capped)**

In `cartlog_shimwatch2()` change the window and add a spam cap. The new
low bound covers the isoldr slot; the high bound deliberately stops at
`0x8c00c000` — the boot-stack/VBR region above is known game-owned and
churns every tick (would spam the log for no verdict value):

```cpp
static void cartlog_shimwatch2()
{
	const u8 *base = cartlog_main_base;
	if (base == nullptr)
		return;   // no baseline yet -- same discipline as cartlog_main_profile
	// Phase 7 T1: widened down to the DreamShell isoldr slot (P1
	// 0x8c003800-0x8c00bfff = planned blob 0x8c004000-0x8c00b908 + pinned
	// heap to 0x8c00c000, plus the 0x3800-0x4000 shoulder). The old window
	// 0x8c010000-0x8c017fff (shim home) is kept. The gap 0x8c00c000-0x8c010000
	// is game-owned (boot stack/VBR/scratch, boot-binary.md) and deliberately
	// NOT watched -- it would fire every tick. Line cap: a real collision
	// verdict needs the first hits, not a flood.
	static u32 emitted = 0;
	const u32 LO1 = 0x00003800, HI1 = 0x0000bfff;
	const u32 LO2 = 0x00010000, HI2 = 0x00017fff;
	for (u32 i = LO1; i <= HI2; i++)
	{
		if (i > HI1 && i < LO2)
			continue;
		if (mem_b[i] != base[i])
		{
			if (emitted < 64)
				cartlog("SHIMWATCH2 addr=%08x was=%02x now=%02x\n", 0x8c000000 + i, base[i], mem_b[i]);
			else if (emitted == 64)
				cartlog("SHIMWATCH2 CAP\n");
			emitted++;
		}
	}
}
```

- [ ] **Step 2: Add the boot-window SP watermark**

In `cartlog.cpp`, extend the existing sampler with a scoped minimum
(boot-cluster only, so task-stack samples at `0x8c1d4xxx` don't pollute):

```cpp
// Phase 7 T1: separate low-water for the BOOT stack window only
// (0x8c000000-0x8c010000) -- the isoldr blob+heap ceiling question.
// Event-sampled (maple + GD command starts), NOT per-instruction: the
// emitted floor is evidence, not proof (KB records the limit).
static uint32_t sp_boot_min = ~0u;

void cartlog_sp_sample(unsigned sp)
{
	if (!cartlog_enabled())
		return;
	if (sp < sp_min)
		sp_min = sp;
	if (sp > sp_max)
		sp_max = sp;
	if (sp >= 0x8c000000u && sp < 0x8c010000u && sp < sp_boot_min)
		sp_boot_min = sp;
}

void cartlog_sp_water()
{
	if (!cartlog_enabled())
		return;
	cartlog("SPWATER min=%08x max=%08x bootmin=%08x\n", sp_min, sp_max, sp_boot_min);
}
```

- [ ] **Step 3: Add a GD-command SP feed**

The two existing feeds are maple-side (`maple_jvs.cpp:1765`,
`maple_if.cpp:194`). Add one at the GD-ROM command start so every shim
disc read samples the live stack. In
`core/hw/gdrom/gdromv3.cpp`, find the SPI/PACKET command-execution entry
(the function that dispatches a received PACKET command — grep for the
existing cartlog GDPIO/GDDMA probe calls in that file and put the sample
beside the earliest one), and add:

```cpp
	cartlog_sp_sample(Sh4cntx.r[15]);   // Phase 7 T1: boot-SP watermark feed
```

Add `#include "hw/naomi/cartlog.h"` if the file doesn't already include it
(it does if the GDPIO/GDDMA probes live there — check first).

- [ ] **Step 4: Build the fork**

```bash
cd ../flycast4naomi2dreamcast && git fetch && git log --oneline HEAD..origin/master   # drift check first (tooling.md)
git add -A && git commit -m "senkosp phase7 T1: widen SHIMWATCH2 to isoldr slot; BOOTSP watermark" && git push
cd ../cleopatra/tools/flycast-src && git pull --ff-only
cmake --build build -j"$(sysctl -n hw.ncpu)"
```
Expected: exit 0, `build/Flycast.app/Contents/MacOS/Flycast` relinked.
(Full recipe incl. CMake pin: `../cleopatra/docs/kb/tooling.md` §Flycast —
source build.)

- [ ] **Step 5: Record the fork commit in tooling.md and commit**

Append the fork commit hash + what it adds to
`docs/kb/tooling.md` §Instrumented Flycast (one bullet, same style as the
Phase 4 Task 1 entry there).

```bash
git add docs/kb/tooling.md && git commit -m "phase7 T1 task1: fork instruments (SHIMWATCH2 widen + BOOTSP)"
```

---

### Task 2: Measurement legs — hole write-watch + boot-SP floor

**Files:**
- Create: `captures/phase7/` leg logs (gitignored)
- Modify: `docs/kb/phase7-polishing.md` (new §T1 measurements section)

**Interfaces:**
- Consumes: Task 1's instrument lines (`SHIMWATCH2` in `0x8c003800–0x8c00bfff`, `SPWATER ... bootmin=`).
- Produces: KB verdicts that Task 5/6 cite: (a) hole-quiet verdict, (b) measured DC boot-SP floor.

- [ ] **Step 1: Unattended DC attract leg (~10 min)**

Run the release disc in the rebuilt Flycast, DC profile, cartlog on —
same one-call foreground pattern as the phase-4 attract legs
(`docs/kb/tooling.md` §Phase 2 capture harness for the env-var pattern;
DC legs point Flycast at `build/disc.gdi`):

```bash
make gdi
FLYCAST_CARTLOG=captures/phase7/hole-attract.log \
  ../cleopatra/tools/flycast-src/build/Flycast.app/Contents/MacOS/Flycast \
  "$(pwd)/build/disc.gdi" &   # note PID; kill by PID after ~600 s
```

- [ ] **Step 2: Parse the leg**

```bash
grep -c "SHIMWATCH2" captures/phase7/hole-attract.log   # expect 0 in the hole window
grep "SPWATER" captures/phase7/hole-attract.log | tail -1
```
Expected: zero `SHIMWATCH2` lines with `addr=0x8c003800–0x8c00bfff`
(any `0x8c01xxxx` line would be a shim-home regression — investigate
before proceeding); `bootmin=` ≥ `0x8c00c000` (predicted ≈`0x8c00e8xx`).
If a hole write DOES fire: STOP, take the address to Ghidra, and revisit
the spec's memory contract before any code task.

- [ ] **Step 3: Operator leg — played match + test-menu round trip (STOP AND WAIT)**

Ask the operator to run one emulator session on the same build: boot →
play a 1P match → reboot with A+Start combo → test menu → exit. Capture
with `FLYCAST_CARTLOG=captures/phase7/hole-play.log`. Parse as step 2.
Do not proceed until the operator has run it and both regimes parse clean.

- [ ] **Step 4: Write the KB verdicts + commit**

Add to `docs/kb/phase7-polishing.md` under a new `### T1 measurements`
heading: the two leg names, the SHIMWATCH2 verdict (with the honest limit:
content-scan, dynarec-era caveat, same as phase-4's), the `bootmin=`
number vs the Naomi floor `0x8c00e864` and the DC hang datum `0x8c00e940`,
and the resulting confirmed ceiling for blob+heap.

```bash
git add docs/kb/phase7-polishing.md && git commit -m "phase7 T1 task2: hole write-watch + boot-SP floor measured"
```

---

### Task 3: Offline recon — fill-loop pools, TMU scan, isoldr heap bound

**Files:**
- Modify: `docs/kb/phase7-polishing.md` (§T1 measurements, three more verdicts)
- Read-only: `senkosp.dat`, `tools/dreamshell-4.0.4/firmware/isoldr/loader/malloc.c`, `fs/fat/`

**Interfaces:**
- Produces: (a) fill-pool verdict, (b) TMU verdict that pins Task 5's `GD_SYS_FIRST_LADDER` value, (c) heap-growth bound that finalizes Task 8's operator `heap =` pin.

- [ ] **Step 1: Decode the step-11 fill-loop pool bounds**

The undecoded boot-chain fill loops take their ranges from pointer pools
at P1 `0x8c02122c–0x8c02123c` (`docs/kb/boot-binary.md` §Entry chain,
step 11). Boot image loads from `.dat` offset 0 at `0x8c020000`, so pool
words sit at `.dat` offsets `0x122c–0x123c`:

```bash
python3 -c "
import struct
d=open('senkosp.dat','rb').read()
for off in range(0x122c,0x1240,4):
    print(hex(off), hex(struct.unpack_from('<I',d,off)[0]))
"
```
Verdict: do any decoded ranges intersect `0x8c003800–0x8c00c000`?
Expected no (the known BSS-clear bounds are `0x8c192000–0x8c1de200`,
`relocation-map.md`). If yes: STOP, spec revision needed.

- [ ] **Step 2: TMU register literal scan**

isoldr's card retry-reinit and `CMD_INIT` spin on a free-running TMU0
(spec §Risks). The game *reads* TCNT0 for delay loops (loader handoff
comment, `loader/main.c`); the question is whether it *writes* TMU0:

```bash
python3 -c "
import struct
d=open('senkosp.dat','rb').read()
regs={'TOCR':0xffd80000,'TSTR':0xffd80004,'TCOR0':0xffd80008,'TCNT0':0xffd8000c,'TCR0':0xffd80010}
for name,a in regs.items():
    for pat in (a, a & 0x1fffffff):
        b=struct.pack('<I',pat); i=d.find(b); hits=[]
        while i>=0: hits.append(hex(i)); i=d.find(b,i+1)
        if hits: print(name, hex(pat), hits)
"
```
- Zero hits on `TSTR`/`TCOR0`/`TCR0` → the game cannot reprogram TMU0 by
  literal; `GD_SYS_FIRST_LADDER` stays 1 (Task 5).
- Hits in the boot/main image range (`.dat` < `0x1c0000`) → chase each in
  Ghidra (`docs/kb/tooling.md` §Phase 3 Ghidra project) to classify
  read/write. A confirmed TMU0 *writer* → set `GD_SYS_FIRST_LADDER 0` in
  Task 5 and record the residual retry risk (spec §Risks disposition).
  Hits above `0x1c0000` are streamed-asset noise (same bucketing as
  `test_maple_literals.py`).

- [ ] **Step 3: Bound isoldr 0.8.4 heap growth**

Read `tools/dreamshell-4.0.4/firmware/isoldr/loader/malloc.c` (allocator
shape, whether frees exist / high-water is bounded) and grep allocation
call sites:

```bash
grep -rn "malloc\|calloc\|realloc" tools/dreamshell-4.0.4/firmware/isoldr/loader/*.c tools/dreamshell-4.0.4/firmware/isoldr/loader/fs/fat/*.c | grep -v "^.*malloc.c.*define"
```
Sum worst-case live allocations for the plain `sd` build
(`MAX_OPEN_FILES=3`, no CDDA — exclude `ENABLE_CDDA`/`ENABLE_IRQ`-gated
sites). Deliverable: a number N such that `0x8c00c000 + N` provably stays
under the Task-2-measured boot-SP floor. If N cannot be bounded under
that ceiling, evaluate `heap = 0x8c008000`-region alternatives (blob at
`0x8c004000` ends `0x8c00b908` — then heap must go BELOW the blob or the
placement moves; record whichever holds).

- [ ] **Step 4: KB + commit**

Record all three verdicts with the commands run, in
`docs/kb/phase7-polishing.md` §T1 measurements.

```bash
git add docs/kb/phase7-polishing.md && git commit -m "phase7 T1 task3: fill pools + TMU + isoldr heap bound"
```

---

### Task 4: Maple receive-pointer floor (vector-table survival made structural)

**Files:**
- Modify: `shims/src/main.c:438` area (`maple_service()`)

**Interfaces:**
- Consumes: existing `DEST_LO`-style fence precedent (`shims/src/cart.c:45`).
- Produces: no API change; the low-RAM guarantee Tasks 5–8 rely on.

- [ ] **Step 1: Add the floor**

`maple_service()` currently accepts any receive pointer in the 16 MB
window (`shims/src/main.c:438`):

```c
    if (rcv - 0x0c000000u < 0x01000000u)
```

Change to (and mirror on the list-base guards at ~`:425`/`:431` if they
gate stores rather than reads — read the three sites first; only
store-gating guards get the floor):

```c
    /* Floor at 0x0c01f000 (cart.c DEST_LO precedent): a garbage rcv below
     * the game image would overwrite loader-placed low RAM -- including the
     * BIOS syscall vectors at 0xc0000b0 that the DreamShell backend needs
     * alive. Measured maple buffers are all >= 0x0c1bxxxx (boot-binary.md). */
    if (rcv - 0x0c01f000u < 0x01000000u - 0x0001f000u)
```

- [ ] **Step 2: Build + host tests**

```bash
make test && make gdi
```
Expected: both exit 0.

- [ ] **Step 3: Unattended emulator smoke (attract, ~3 min)**

Same leg pattern as Task 2 step 1, log
`captures/phase7/maplefloor-smoke.log`. Expected: attract reached
(`FLYCAST_SHOT` screenshot if desired), zero `MIE skip rcv=` lines beyond
the baseline behavior, no tripwires.

- [ ] **Step 4: Commit**

```bash
git add shims/src/main.c && git commit -m "phase7 T1 task4: maple rcv floor -- vector-table survival structural"
```

---

### Task 5: `gd_sys.c` + `gdstack.S` — the syscall backend compiles in both worlds

**Files:**
- Modify: `shims/include/shim_iface.h` (backend flag index, knobs, canary)
- Create: `shims/src/gd_sys.c`
- Create: `shims/src/gdstack.S`
- Modify: `shims/Makefile` (SRCS), `loader/Makefile` (gd_sys.o rule)
- Modify: `shims/test/test_shim_iface.c` (one assert)

**Interfaces:**
- Consumes: `GD_STACK_BOTTOM/TOP`, `SHIM_STATE`, `P2ADDR` (`shim_iface.h`); `gd_last_err`, `shim_die`, `hex_paint_c` (existing shim symbols).
- Produces: `int gd_sys_read_sectors(void *dst, unsigned fad, unsigned n)` (0 = ok, negative = failure; latches `gd_last_err`), `int gdc_call(u32,u32,u32,u32)` (shim build only), `SHIM_STATE_GD_BACKEND` (=1, the `SHIM_STATE[1]` index; 0=raw 1=syscall), `GD_STACK_CANARY` (=0x57ac6a2d). Task 6 consumes all four.

- [ ] **Step 1: shim_iface.h additions**

Append after the `GD_STACK_TOP` line:

```c
/* Phase 7 T1: dual-backend GD dispatch. SHIM_STATE[SHIM_STATE_GD_BACKEND]
 * = 0 raw ATA (real-BIOS boots, GDEMU/optical) / 1 BIOS-syscall (DreamShell
 * isoldr). Seeded by the loader after the rehearsal probe (main.c). */
#define SHIM_STATE_GD_BACKEND 1
/* Canary at the bottom of the private syscall stack (gdstack.S swaps r15 to
 * GD_STACK_TOP; isoldr's FatFs+SPI runs on it -- Cleopatra measured >2 KB,
 * we reserve 8 KB and VERIFY instead of hoping; spec decision 5). Seeded by
 * the loader at staging (nonzero: the window memset would zero it). */
#define GD_STACK_CANARY 0x57ac6a2d
```

and in the HUD/diag toggle block:

```c
#ifndef SHIM_GD_DIAG
#define SHIM_GD_DIAG 0          /* on-screen GD-syscall tracer (Cleopatra
                                 * G12): send/status/heartbeat/phase cells +
                                 * stack low-water. TV-debuggable, serial-
                                 * silent. NEVER ship 1 (paints over play). */
#endif
```

- [ ] **Step 2: Write `shims/src/gd_sys.c`**

Port of `../cleopatra/shims/src/gd.c:20-146` with these deltas: (a) call
mechanism is `gdc_call` in the shim build but a **direct vector deref in
the loader build** — `GD_STACK_TOP 0x8c018000` is INSIDE the running
loader's own image (KOS links the loader at `0x8c010000`), so the
trampoline's stack swap would corrupt the loader; KOS's stack/FPSCR/MMU-off
world already satisfies isoldr's assumptions there; (b) hang guards return
an error in the loader build instead of `shim_die` (loader halts on the
negative return, same convention as `gd.c`'s `gd_fail`); (c) first-call
ladder per spec decision 6, gated by `GD_SYS_FIRST_LADDER` whose value
Task 3's TMU verdict pinned; (d) canary check after every read.

```c
/* GD-ROM via the DC BIOS GD syscall vector 0x8c0000bc -- the DreamShell
 * isoldr backend (Phase 7 T1). Port of the Cleopatra port's hardware-proven
 * loop (../cleopatra/shims/src/gd.c; their KB HW rounds 9-13 carry the
 * evidence for every hardening choice). Polling only, no IRQs. PIOREAD, not
 * DMAREAD: no G1-DMA side effects in game context (same reasoning as gd.c's
 * raw path being PIO-only).
 *
 * ABI (cross-checked against KOS syscalls.c and isoldr 0.8.4
 * gdc_syscall.s:242-279 -- docs/kb/tooling.md §Phase 7): call
 * (r4,r5,r6=0,r7=func); func SEND=0 CHECK=1 EXEC=2 SYSINIT=3;
 * CMD_PIOREAD=16 param {start_fad, num_sec, buffer, 0}; CHECK status
 * FAILED=-1 NOT_FOUND=0 PROCESSING=1 COMPLETED=2 STREAMING=3 BUSY=4. */
#include "shim_iface.h"
typedef unsigned int u32;
typedef int (*gdc_t)(u32, u32, u32, u32);

#ifndef GD_LOADER_BUILD
#define GD_LOADER_BUILD 0
#endif
#ifndef GD_SYS_FIRST_LADDER
#define GD_SYS_FIRST_LADDER 1   /* run InitSystem+CMD_INIT once before the
                                 * first stream (spec decision 6). Task 3's
                                 * TMU verdict may pin this to 0. */
#endif

#if GD_LOADER_BUILD
/* Loader context: KOS stack is deep, FPSCR is the KOS default, MMU is off --
 * exactly the world isoldr assumes. Direct live-vector call; gdc_call's
 * stack swap would land INSIDE the running loader image (GD_STACK_TOP
 * 0x8c018000 < loader end 0x8c0dc000). */
#define GDC ((gdc_t)(*(volatile u32 *)0x8c0000bc))
#else
int gdc_call(u32, u32, u32, u32);   /* gdstack.S: private stack + FPU
                                     * quarantine + MMUCR window */
#define GDC gdc_call
void shim_die(u32, u32, u32);
#endif

#define CMD_PIOREAD  16
#define CMD_INIT     24
#define GD_SEND      0
#define GD_CHECK     1
#define GD_EXEC      2
#define GD_SYSINIT   3
#define GD_NOT_FOUND 0
#define GD_COMPLETED 2
#define GD_FAILED   -1
#define GD_E_SYS     9   /* this backend's failure site (gd.c sites end at 8);
                          * gd_last_err disambiguates: raw CHECK stat[0], or
                          * 0xcafe0001 = NOT_FOUND timeout, 0xcafe0002 = SEND
                          * refused on every attempt, 0xcafe0003 = canary. */

extern unsigned int gd_last_err;    /* defined in gd.c (both builds) */

#if SHIM_GD_DIAG && !GD_LOADER_BUILD
/* diag is shim-only: hex_paint_c lives in util.c, which the loader never
 * links -- a GDDIAG=1 build must not break the loader link. */
void hex_paint_c(unsigned int, unsigned int, unsigned int,
                 unsigned short, unsigned short);
#define GD_DIAG(x, y, v) hex_paint_c((x), (y), (v), 0xffff, 0x001f)
#define GD_PHASE(n) GD_DIAG(20, 148, 0xAAAA0000u | (n))
#define GD_RET(n)   GD_DIAG(120, 148, 0xAAAA8000u | (n))
#else
#define GD_DIAG(x, y, v) ((void)0)
#define GD_PHASE(n) ((void)0)
#define GD_RET(n)   ((void)0)
#endif

/* Hang guard: on hardware ~100M pumps >> any PIO read (Cleopatra G-loop);
 * die loud in the shim, return the site in the loader (it halts red). */
static int gd_sys_wedge(unsigned fad, unsigned n) {
#if GD_LOADER_BUILD
    (void)fad; (void)n;
    return -GD_E_SYS;
#else
    shim_die(5, fad, n);            /* same code-5 blue as a raw-path wedge */
    return -GD_E_SYS;               /* unreachable */
#endif
}

static void gd_sys_reinit(void) { GD_PHASE(6); GDC(0, 0, 0, GD_SYSINIT); GD_RET(6); }

static int gd_init_drive(void) {
    u32 stat[4], guard = 0;
    GD_PHASE(4);
    int req = GDC((u32)CMD_INIT, 0, 0, GD_SEND);
    GD_RET(4);
    if (req <= 0) return 0;
    for (;;) {
        GD_PHASE(5);
        GDC(0, 0, 0, GD_EXEC);
        int s = GDC((u32)req, (u32)stat, 0, GD_CHECK);
        GD_RET(5);
        if (s == GD_COMPLETED || s <= GD_FAILED) return 0;
        if (s == GD_NOT_FOUND && guard > 1000000u) return 0;
        if (++guard > 100000000u) return gd_sys_wedge(0xdead1217, 0);
    }
}

/* nonzero .data init, house style (see gd.c gd_last_err) */
static int gd_sys_virgin = 1;

/* Read `n` 2048-byte data sectors at absolute `fad` into dst (pass the P2
 * alias -- isoldr stores through exactly the pointer given, and PIOREAD does
 * NOT purge caches (0.8.4 syscalls.c:517); P2 makes that moot).
 * 0 = ok; negative = -GD_E_SYS with the verdict in gd_last_err. */
int gd_sys_read_sectors(void *dst, unsigned fad, unsigned n) {
#if GD_SYS_FIRST_LADDER
    /* We overwrite BIOS low RAM at handoff; Cleopatra's record says budget
     * the rebuild as the mechanism, not the rare exception (their HW round
     * 11/12). Under isoldr the state lives in the resident blob and this is
     * cheap insurance; under a real BIOS this backend never runs. */
    if (gd_sys_virgin) {
        gd_sys_virgin = 0;
        gd_sys_reinit();
        if (gd_init_drive() < 0) return -GD_E_SYS;
    }
#endif
    for (u32 attempt = 0; attempt < 4; attempt++) {
        if (attempt) { gd_sys_reinit(); if (gd_init_drive() < 0) return -GD_E_SYS; }
        u32 param[4], stat[4], guard = 0;
        param[0] = fad; param[1] = n; param[2] = (u32)dst; param[3] = 0;
        GD_DIAG(120, 134, fad);
        GD_PHASE(1);
        int req = GDC((u32)CMD_PIOREAD, (u32)param, 0, GD_SEND);
        GD_RET(1);
        GD_DIAG(20, 120, (u32)req);
        if (req <= 0) { gd_last_err = 0xcafe0002u; continue; }  /* send refused: ladder+retry */
        for (;;) {
            GD_PHASE(2);
            GDC(0, 0, 0, GD_EXEC);          /* pump isoldr's coroutine */
            GD_RET(2);
            GD_PHASE(3);
            int s = GDC((u32)req, (u32)stat, 0, GD_CHECK);
            GD_RET(3);
            if ((guard & 0xffffu) == 0) { GD_DIAG(120, 120, (u32)s); GD_DIAG(20, 134, guard); }
            if (s == GD_COMPLETED) goto done;
            if (s <= GD_FAILED) { gd_last_err = stat[0]; break; }       /* hard error: retry */
            if (s == GD_NOT_FOUND && guard > 1000000u) { gd_last_err = 0xcafe0001u; break; }
            /* PROCESSING/STREAMING/BUSY/early NOT_FOUND: keep pumping */
            if (++guard > 100000000u) return gd_sys_wedge(fad, n);
        }
    }
    return -GD_E_SYS;
done:
#if !GD_LOADER_BUILD
    /* 8 KB stack sufficiency is VERIFIED, not assumed (spec decision 5). */
    if (*P2(GD_STACK_BOTTOM) != GD_STACK_CANARY) {
        gd_last_err = 0xcafe0003u;
        shim_die(5, fad, GD_STACK_CANARY);
    }
#if SHIM_GD_DIAG
    {   /* stack low-water: first non-zero word above the canary (window was
         * staged zero); painted as bytes-used-from-top. Diag builds only. */
        volatile u32 *w = P2(GD_STACK_BOTTOM) + 1;
        while (w < P2(GD_STACK_TOP) && *w == 0) w++;
        GD_DIAG(220, 148, GD_STACK_TOP - (((u32)w & 0x1fffffffu) | 0x80000000u));
    }
#endif
#endif
    return 0;
}
```

- [ ] **Step 3: Write `shims/src/gdstack.S`**

Copy `../cleopatra/shims/src/gdstack.S` **verbatim** (all 220 lines: the
private-stack swap, both-bank FPU quarantine under KOS-default FPSCR
`0x00040001`, the fingerprint-gated MMUCR AT=0 window
`[0x8c0000c0]==[0x8c0000bc]+8 OR entry-offset>=0x10000`, live vector
deref, and the three `.data` save slots). Two deltas only:

1. Header comment: replace their stack-size sentence with ours — 8 KB not
   16 KB, canary-verified (`GD_STACK_TOP` resolves via our `shim_iface.h`
   include to `0x8c018000` automatically; no code change).
2. Confirm the file compiles under our `shims/Makefile` CFLAGS
   (`-ml -m4-single-only` — same as Cleopatra's; no change expected).

Do NOT port their `#if SHIM_GD_STACK` toggle into `gd_sys.c` — our shim
build always uses `gdc_call` (the toggle existed to A/B an already-shipped
backend; we have the probe instead).

- [ ] **Step 4: Wire the builds**

`shims/Makefile`: replace the "gdstack.S deleted in Task 10" comment block
with a pointer to this plan/spec, and:

```make
SRCS = src/main.c src/scif.c src/util.c src/gd.c src/gd_sys.c src/cart.c \
       src/maple.c src/jvs.c src/mtramp.S src/gdstack.S $(B)/mie_blobs.c
```

`loader/Makefile`: add below the `gd.o` rule (same shape, same reason):

```make
# Syscall GD backend, loader build: direct-vector calls (no gdstack -- see
# gd_sys.c header: GD_STACK_TOP sits inside the running loader image).
gd_sys.o: ../shims/src/gd_sys.c ../shims/include/shim_iface.h
	kos-cc $(CFLAGS) $(CPPFLAGS) -DGD_LOADER_BUILD=1 -c $< -o $@
```
and add `gd_sys.o` to `OBJS`.

- [ ] **Step 5: One iface assert**

In `shims/test/test_shim_iface.c`, next to the existing layout asserts:

```c
    assert(SHIM_STATE_GD_BACKEND < 8);              /* inside SHIM_STATE u32[8] */
    assert(GD_STACK_TOP - GD_STACK_BOTTOM == 0x2000);
    assert(GD_STACK_CANARY != 0);                   /* staging memset is zero */
```

- [ ] **Step 6: Build + tests + size check**

```bash
make test && make gdi
grep -m1 "" shims/build/shim.map >/dev/null && /opt/toolchains/dc/sh-elf/bin/sh-elf-nm shims/build/shim.elf | sort | tail -5
```
Expected: exit 0 everywhere (the `shim.ld` ASSERT enforces the `0x4000`
budget — a link failure here means the port must shed bytes, e.g. drop
diag strings); highest `.text`/`.data` symbol < `0x8c014000`.

- [ ] **Step 7: Commit**

```bash
git add shims/include/shim_iface.h shims/src/gd_sys.c shims/src/gdstack.S \
        shims/Makefile loader/Makefile shims/test/test_shim_iface.c
git commit -m "phase7 T1 task5: syscall GD backend (gd_sys.c + gdstack.S revived, Cleopatra port)"
```

---

### Task 6: Dispatch + boot probe + build knobs

**Files:**
- Modify: `shims/src/gd.c` (one dispatch shim in `gd_read_cart`'s sector reads)
- Modify: `loader/main.c` (rehearsal block ~line 205; staging seed ~line 263)
- Modify: `Makefile` (FORCE_SYSCALL / GDDIAG knobs)

**Interfaces:**
- Consumes: `gd_sys_read_sectors`, `SHIM_STATE_GD_BACKEND`, `GD_STACK_CANARY` (Task 5).
- Produces: the shipped probe/dispatch behavior Tasks 7–8 verify; `make gdi FORCE_SYSCALL=1` (forces the syscall backend end-to-end); `make gdi GDDIAG=1` (on-screen tracer build).

- [ ] **Step 1: Dispatch in `gd.c`**

Immediately above `gd_read_cart` (inside the existing
`#if !GD_LOADER_BUILD`), add:

```c
int gd_sys_read_sectors(void *dst, unsigned fad, unsigned n);
/* Phase 7 T1 dispatch: backend chosen once by the loader's rehearsal probe
 * (main.c), 0 = raw ATA / 1 = BIOS-syscall (DreamShell isoldr). The raw
 * path below this line is untouched. */
static int gd_read(unsigned fad, void *dst, unsigned secs) {
    if (P2(SHIM_STATE)[SHIM_STATE_GD_BACKEND])
        return gd_sys_read_sectors(dst, fad, secs);
    return gd_read_fad(fad, dst, secs);
}
```

and in `gd_read_cart` replace its three `gd_read_fad(...)` calls with
`gd_read(...)` (same argument order as `gd_read`, note dst/fad swap vs
`gd_read_fad`):

```c
        if ((r = gd_read(fad, b, 1)) < 0) return r;      /* head */
        if ((r = gd_read(fad, d, pl.body_secs)) < 0) return r;  /* body */
        if ((r = gd_read(fad, b, 1)) < 0) return r;      /* tail */
```

No other line in `gd.c` changes.

- [ ] **Step 2: Loader probe**

In `loader/main.c`'s rehearsal block, replace the raw-fail `halt` with the
syscall fallback, and track the chosen backend. The block becomes:

```c
    {
        static uint8 rawbuf[2048] __attribute__((aligned(32)));
        char msg[96];
        uint32 backend = 0;                 /* 0 = raw, 1 = syscall */
        int gd_sys_read_sectors(void *dst, unsigned fad, unsigned n);
        dcache_inval_range((uintptr_t)rawbuf, sizeof(rawbuf));
#if !GD_FORCE_SYSCALL
        irq_mask_t old = irq_disable();
        int r = gd_read_fad(fad, rawbuf, 1);
        irq_restore(old);
#else
        int r = -99;                        /* FORCE_SYSCALL build: skip raw */
        uint32 raw_err_unused = gd_last_err; (void)raw_err_unused;
#endif
        if (r != 0) {
            uint32 raw_err = gd_last_err;
            /* Raw path failed (DreamShell: expected -- isoldr virtualizes GD
             * at the syscall layer only; the physical drive holds the DS boot
             * disc). Rehearse the syscall backend on the same sector. KOS is
             * live and its own driver already pumps this server; no IRQ mask
             * (Cleopatra loader rehearsal precedent). Buffer passed as P2 --
             * isoldr stores through the given pointer, PIOREAD doesn't purge. */
            dcache_inval_range((uintptr_t)rawbuf, sizeof(rawbuf));
            int rs = gd_sys_read_sectors((void *)P2ADDR((uint32)rawbuf), fad, 1);
            if (rs != 0) {
                sprintf(msg, "GD FAIL raw r=%d e=%08lx / sys r=%d e=%08lx",
                        r, (unsigned long)raw_err,
                        rs, (unsigned long)gd_last_err);
                halt(msg);
            }
            if (memcmp(rawbuf, buf, 2048))
                halt("SYSCALL MISMATCH VS KOS READ");
            backend = 1;
            say("cart read OK (syscall)");
        } else {
            if (memcmp(rawbuf, buf, 2048))
                halt("RAW-ATA MISMATCH VS KOS READ");
            say("cart read OK (raw ATA)");
        }
```

(The block no longer closes after the raw compare — `backend` must stay in
scope through staging. Either widen the block to include the staging seed
below, or hoist `uint32 backend` to function scope; take whichever reads
cleaner against the surrounding code, and delete the old
`RAW-ATA READ FAIL` sprintf/halt lines this replaces.)

At the staging seed (next to the existing `SHIM_STATE[0]` line):

```c
    /* SHIM_STATE[0] = boot mode (0 = main, 1 = test), read by the shim. */
    *(uint32 *)(STAGE_SHIM + (SHIM_STATE - SHIM_BASE)) = (uint32)test_boot;
    /* SHIM_STATE[1] = GD backend from the rehearsal probe (0 raw, 1 syscall). */
    *(uint32 *)(STAGE_SHIM + (SHIM_STATE - SHIM_BASE) + 4) = backend;
    /* Canary under the private syscall stack (gd_sys.c checks per read). */
    *(uint32 *)(STAGE_SHIM + (GD_STACK_BOTTOM - SHIM_BASE)) = GD_STACK_CANARY;
```

Also add near the top of `main.c` (default for non-force builds):

```c
#ifndef GD_FORCE_SYSCALL
#define GD_FORCE_SYSCALL 0
#endif
```

- [ ] **Step 3: Top-Makefile knobs**

Below the `CRC=1` block, mirroring the `SERIAL` pattern exactly:

```make
# FORCE_SYSCALL=1: loader skips the raw rehearsal and seeds the syscall
# backend -- the whole game then streams via BIOS GD syscalls. Emulator
# control legs only (Flycast HLEs the syscalls statelessly; the dongle
# itself cannot be emulated). Never a release knob.
ifeq ($(FORCE_SYSCALL),1)
DEFS += -DGD_FORCE_SYSCALL=1
endif
# GDDIAG=1: on-screen GD-syscall tracer + stack low-water (TV-debuggable,
# serial-silent -- the DreamShell debugging instrument). Never ship.
ifeq ($(GDDIAG),1)
DEFS += -DSHIM_GD_DIAG=1
endif
```

- [ ] **Step 4: Build + host tests**

```bash
make test && make gdi && make gdi FORCE_SYSCALL=1
```
Expected: all exit 0. (Each `make gdi` variant rebuilds loader+shim; the
patch-table regeneration chain reacts to the shim.map change — that is
expected and correct, see loader/Makefile's dependency comment.)

- [ ] **Step 5: Emulator regression leg — release config picks raw**

Rebuild clean release config (`make gdi`), run the Task 2 leg pattern
~5 min, log `captures/phase7/dispatch-raw.log`. Release builds are
serial-silent, so the raw-chosen verdict is behavioral: boots to attract,
cartlog stream shape matches the phase-6 baseline, zero new tripwires —
plus one `SERIAL=1` variant of the same leg if direct
`cart read OK (raw ATA)` log evidence is wanted (emulator only; that
line + the absence of the syscall line IS the probe verdict). This is
the "probe chose raw on a real-BIOS boot" half of exit criterion 4.

- [ ] **Step 6: Emulator FORCE_SYSCALL leg — whole game on the new backend**

```bash
make gdi FORCE_SYSCALL=1
FLYCAST_CARTLOG=captures/phase7/force-syscall.log \
  ../cleopatra/tools/flycast-src/build/Flycast.app/Contents/MacOS/Flycast \
  "$(pwd)/build/disc.gdi" &   # ~10 min, kill by PID
```
Expected: boots to attract and cycles; every cart stream served through
the syscall backend (Flycast HLE is stateless — Cleopatra G11 — so the
stomped low RAM doesn't matter in the emulator). Any hang here is a real
backend bug: debug with `make gdi FORCE_SYSCALL=1 GDDIAG=1` and the
phase-cell semantics (left cell without matching right = wedged INSIDE
that syscall).

- [ ] **Step 7: Commit**

```bash
git add shims/src/gd.c loader/main.c Makefile
git commit -m "phase7 T1 task6: backend dispatch + loader probe + FORCE_SYSCALL/GDDIAG knobs"
```

---

### Task 7: Verification suite — soak, tests, reproducibility

**Files:**
- Create: `captures/phase7/force-soak.log` (gitignored)
- Modify: `docs/kb/phase7-polishing.md` (§T1 emulator evidence)

**Interfaces:**
- Consumes: Task 6's builds and knobs.
- Produces: exit-criterion 5 evidence + re-recorded release md5s (criterion 3's emulator half).

- [ ] **Step 1: FORCE_SYSCALL attract soak with CRC (~30 min)**

CRC needs serial to be audible (`CRC=1` requires `SERIAL=1` — emulator
only, never hardware-with-dongle):

```bash
make gdi FORCE_SYSCALL=1 SERIAL=1 CRC=1
FLYCAST_CARTLOG=captures/phase7/force-soak.log <flycast> "$(pwd)/build/disc.gdi" &  # ~30 min, kill by PID
python3 scripts/check_stream_crc.py captures/phase7/force-soak.log
```
Expected: CRC checker PASS (0 mismatches — byte-perfect delivery through
the syscall path), 0 `TEXERR` counters, attract cycled ≥3 times.

- [ ] **Step 2: Full test suite + release rebuild**

```bash
make test
make clean && make gdi
md5 build/track01.iso build/track02.raw build/track03.iso build/track04.iso build/disc.gdi
```
Expected: tests green; build reproducible on a second `make clean && make
gdi` (identical md5s run-to-run). The md5s DIFFER from the phase-6 release
set (shim grew) — that is expected; these are the new release md5s.

- [ ] **Step 3: KB + commit**

Record in `docs/kb/phase7-polishing.md` §T1: soak verdict + CRC line
counts, the new release md5 set (note superseding the phase-6 set, same
convention as #26/#28 flagged in 00-status), and the FORCE_SYSCALL leg
from Task 6.

```bash
git add docs/kb/phase7-polishing.md && git commit -m "phase7 T1 task7: emulator gate green -- syscall soak CRC-clean, new release md5s"
```

---

### Task 8: Operator hardware session — DreamShell + GDEMU regression (STOP AND WAIT)

**Files:**
- Modify: `docs/kb/phase7-polishing.md` (§T1 hardware rounds)

**Interfaces:**
- Consumes: the Task 7 release build (`make gdi`, clean config — NO
  FORCE_SYSCALL, NO SERIAL, NO GDDIAG), Task 3's finalized `heap =` pin.
- Produces: exit criteria 1, 2, 3 (hardware half), 4 (hardware half).

- [ ] **Step 1: Prepare + hand the operator the instructions**

Build `make gdi` (release config) and `make deploy` for the GDEMU card.
Copy the same disc image set to the DreamShell SD card the way phase-6
Task 32 did. Operator instructions (verbatim, adjusted only if Task 3
moved the heap pin):

1. In DreamShell 4.0.4's ISO Loader app, select the senkosp image.
2. In its settings: **Boot memory = `0x8c004000`**, **Heap memory =
   `0x8c00c000`** (explicit hex — not Auto; Auto can land inside RAM the
   game overwrites). Firmware: plain `sd` (default; not cdda/full). Save
   the preset so it persists.
3. Launch. Expected on screen: loader splash (~7 s in), then ~3 s later
   the game boots — attract as normal. The phase-6 red screen must NOT
   appear.
4. Play one full 1P match. Note load-time feel vs GDEMU (subjective is
   fine; a stopwatch on attract→match-start is a bonus).
5. Then move the SD/GDEMU back to the normal GDEMU boot and re-run the
   usual boot-to-attract + short play check (regression).
6. On ANY failure: photograph the screen (red halts carry both backends'
   error words; a black hang → power off, note when it happened).

- [ ] **Step 2: WAIT for the operator report. Do not proceed.**

- [ ] **Step 3: Bank the verdicts**

Record in `docs/kb/phase7-polishing.md` §T1 hardware rounds: DreamShell
boot verdict, match verdict + reported load feel, GDEMU regression
verdict, any photos into `docs/kb/img/phase7-*`. If DreamShell failed:
this becomes round 1 of the debug loop — next build is
`make gdi GDDIAG=1` (still serial-silent) and the phase-cell photo
protocol; loop rounds stay inside this task.

```bash
git add docs/kb/phase7-polishing.md docs/kb/img/ && git commit -m "phase7 T1 task8: hardware verdicts -- DreamShell + GDEMU regression"
```

---

### Task 9: Gate audit + KB close-out

**Files:**
- Modify: `docs/kb/phase7-polishing.md`, `docs/kb/00-status.md`, `docs/kb/tooling.md`

**Interfaces:**
- Consumes: every prior task's evidence.
- Produces: T1 CLOSED (or an honest blocked-state record).

- [ ] **Step 1: Audit the seven exit criteria**

Walk spec §Exit criteria 1–7; for each, name the file+section/leg that
earns it (same one-row-per-criterion style as every prior phase gate in
`00-status.md`). Any criterion not fully earned stays `[ ]` with exactly
what is missing.

- [ ] **Step 2: Update the KB set**

- `docs/kb/phase7-polishing.md`: T1 section gets a status line (CLOSED /
  blocked-on-X) + the audit table.
- `docs/kb/00-status.md`: phase-7 T1 entry updated; new release md5s
  noted as superseding phase-6's; the "GDEMU/optical only" documented
  limitation from phase-6 Task 32 is retired/amended.
- `docs/kb/tooling.md`: any leg or recipe not yet recorded (fork commit,
  FORCE_SYSCALL/GDDIAG knobs, DreamShell preset recipe).

- [ ] **Step 3: Final commit**

```bash
git add docs/kb/ && git commit -m "phase7 T1: gate audit -- DreamShell serial-SD support CLOSED"
```

---

## Self-review notes (already applied)

- Spec §Verification names a "dispatcher unit test (flag → backend
  selection)". The dispatch reads live `SHIM_STATE` through a P2 MMIO
  alias — host-testing it would mean mocking the memory map for a
  three-line function. Delivered instead as: the Task 5 iface asserts +
  BOTH emulator legs of exit criterion 4 (release leg proves flag=0 →
  raw; FORCE_SYSCALL leg proves flag=1 → syscall, end to end). Deliberate
  simplification, ponytail: the real check is the pair of legs.
- Spec §Design 1–7 → Tasks 5/6 (backend+trampoline+dispatch+probe),
  §Pre-code measurements → Tasks 1–3, decision 8 → Task 4, §Verification
  → Tasks 6–8, §Exit criteria → Task 9. Heap-bound risk → Task 3 step 3.
- Loader-build trampoline hazard (GD_STACK inside the loader image) is a
  plan-discovered constraint the spec's §Design 2 didn't state; encoded
  in Task 5 step 2 and the gd_sys.c header comment.
- Type check: `gd_sys_read_sectors(void *dst, unsigned fad, unsigned n)`
  is used with that exact signature in Tasks 5, 6 (dispatch + probe).
  `gd_read(fad, dst, secs)` arg order matches its definition. Backend
  flag index `SHIM_STATE_GD_BACKEND` = 1 everywhere.

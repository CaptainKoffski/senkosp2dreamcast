# Phase 5 — Real-Hardware Testing & Fit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the texture-load-error hang in the emulator (hard gate), then
boot and play the shipped GDI on the bench Dreamcast + GDEMU, re-earning
Phase 4's five play criteria on silicon.

**Architecture:** Two waves. Wave A (Tasks 1–7) arms three instruments —
shim-side delivered-bytes CRC, fork-side drive-bytes CRC, static
characterization of the game's texture-error handler — control-tests them
unattended, then hunts the hang with operator legs until one captured
occurrence yields a verdict per the spec table. Wave B (Tasks 8–13) is the
hardware campaign: HUD parity, SD mastering with a control disc, first-boot
debugging rounds, the five play criteria, carried-findings disposition, gate
audit.

**Tech Stack:** SH-4 freestanding C (shim), C++ (instrumented Flycast fork
`../flycast4naomi2dreamcast`), Python 3 (offline checker), Ghidra headless
(`scripts/ghidra/run.sh`), GDEMU + SD (hardware).

**Spec:** `docs/superpowers/specs/2026-08-23-phase5-hardware-design.md`

## Plan-level refinements of the spec (found during plan research)

1. **The runtime hang marker is replaced.** The spec's "fork logs a marker
   when the PC hits the handler (PCSAMPLE precedent)" cannot run during play
   legs: every `pc=`-reporting probe (`PCSAMPLE`, `STRWATCH`) needs the SH-4
   interpreter (`INSTRUMENTATION.md` §12), which costs ~10× — unplayable for
   match-win repro legs, which must run dynarec. Replacement, same job:
   (a) Task 4 characterizes the handler statically (address, callers, trigger
   conditions), and (b) the hang self-identifies post-hoc by the proven
   `play1` log signature (`MDODMA` stops while `PVRW STARTRENDER` continues —
   `docs/kb/phase4-conversion.md` §Texture-error hang) plus the operator's
   screenshot. CRC streams, the actual verdict evidence, are MMIO-class and
   fire under dynarec.
2. **The verdict table gains a branch.** The error string sits beside
   `FILE NAME:%s` and `PACKTEX` strings (senkosp.dat `0x168b8a`), so the
   handler may fire on *allocation failure*, not only bad data. Clean CRCs +
   an allocation-failure trigger would mean **our fit bug** (the relocated
   8 MB VRAM arena at the match-win peak — measured margin was only ~680 KB,
   `docs/kb/00-status.md` Phase 3 headline), which is NOT exoneration and
   would reproduce on hardware. Task 4's taxonomy is what disambiguates;
   Task 7 applies it.
3. **HUD porting is mostly done.** The senkosp shim already ships the
   Cleopatra HUD ON by default (`shims/include/shim_iface.h:81`
   `SHIM_HUD 1`; marks + hex rows + death screens in `shims/src/util.c`).
   The one gap vs Cleopatra's Phase-5 kit: no poll heartbeat in
   `shims/src/gd.c`'s wait loops. Task 8 adds it.

## Global Constraints

- **Branch:** all work on `phase5-hardware`, from `main`.
- **Never commit copyrighted bytes** — ROM, BIOS, disc images, extracted
  assets, captured leg logs (`captures/` is gitignored; evidence goes into
  the KB as numbers + cited log line references).
- **Diagnostic flags never committed enabled.** `SHIM_SERIAL`, `SHIM_CRC`,
  `LOADER_SERIAL` are build-time toggles passed via
  `make DEFS='-D...=1'`; committed defaults stay 0 (precedent: Phase 4
  Task 10, `docs/kb/tooling.md` entry2 row). Exception: `SHIM_HUD 1` is the
  committed default by design (round-17 note in `util.c`).
- **Operator legs stop-and-wait.** Consolidate pending operator legs into ONE
  printed session list with exact commands and controls, then stop and wait.
  Never launch the emulator hoping input won't be needed. Kill Flycast by
  PID (`pgrep -f "Flycast.app/Contents/MacOS/Flycast"`); `kill -USR1` first
  saves a `FLYCAST_SHOT` screenshot. Unattended legs use the one-call
  foreground pattern (memory: operator-leg-protocol).
- **Every hardware/behavioral claim in the KB carries a citation**; primary
  sources outrank wikis.
- **CRC-32/IEEE everywhere:** reflected, polynomial `0xEDB88320`, init/final
  `0xFFFFFFFF` — the algorithm of Python's `zlib.crc32`. Shim, fork, and
  checker must agree on this exact variant or every comparison is noise.
- **Reproducibility must survive the phase:** at gate time `make gdi` from
  committed defaults must still produce the criterion-7 disc (compare md5s
  against `docs/kb/phase4-conversion.md` §Gate audit → Criterion 7).
- **Record every tool change** (fork rebuild, new scripts) in
  `docs/kb/tooling.md`.
- KB evidence file for this phase: `docs/kb/phase5-hardware.md` (created in
  Task 4, grown by every task after it).

---

## Wave A — the texture-hang hard gate (emulator)

### Task 1: Shim delivered-bytes CRC probe (`SHIM_CRC`)

**Files:**
- Modify: `shims/src/gd.c` (crc32 fn + hook in `gd_read_cart`)
- Modify: `shims/test/test_gd_math.c` (host test)

**Interfaces:**
- Produces: `unsigned int shim_crc32(const void *p, unsigned len)` — plain
  pointer in, no P2 conversion inside (host-testable); CRC-32/IEEE.
- Produces: serial line format consumed by Task 3's checker:
  `SHIMCRC o=<hex8> l=<hex8> c=<hex8>\n` — cart byte offset, byte length,
  CRC of the bytes delivered to the game's destination buffer.
- Emission point: end of `gd_read_cart` (`shims/src/gd.c:317`, the single
  choke point every cart read routes through — all four entry hooks in
  `cart.c` call it), success path only. Compiled out unless `SHIM_CRC=1`;
  output requires `SHIM_SERIAL=1` (`scif.c` no-ops otherwise).

- [ ] **Step 1: Write the failing host test.** In
  `shims/test/test_gd_math.c`, add to `main()` (next to the existing
  asserts):

```c
    /* CRC-32/IEEE check vector (zlib.crc32 compatible) */
    unsigned int shim_crc32(const void *p, unsigned len);
    assert(shim_crc32("123456789", 9) == 0xcbf43926u);
    assert(shim_crc32("", 0) == 0u);
```

  (If the file's style declares prototypes at top, put the prototype there
  instead — match what's already in the file.)

- [ ] **Step 2: Run it to verify it fails.**
  Run: `make -C shims test`
  Expected: link failure — `shim_crc32` undefined.

- [ ] **Step 3: Implement `shim_crc32` in `gd.c`.** Place it ABOVE the
  `#if !HOST_TEST` guard (the same region `gd_plan` lives in) so
  `test_gd_math.c`, which links `src/gd.c` under `-DHOST_TEST`, gets it:

```c
/* CRC-32/IEEE (reflected, poly 0xEDB88320) -- matches Python zlib.crc32 and
 * the fork's GDPIO/GDDMA probe. Diagnostic (SHIM_CRC) only. Caller passes the
 * alias it wants read (the hook passes P2 -- uncached, the C1 rule).
 * ponytail: bitwise ~50 cycles/byte; switch to a 1 KB table if diag legs drag. */
unsigned int shim_crc32(const void *p, unsigned len) {
    const unsigned char *s = (const unsigned char *)p;
    unsigned int c = 0xffffffffu;
    while (len--) {
        c ^= *s++;
        for (int k = 0; k < 8; k++)
            c = (c >> 1) ^ (0xedb88320u & (0u - (c & 1u)));
    }
    return ~c;
}
```

- [ ] **Step 4: Run tests to verify they pass.**
  Run: `make -C shims test`
  Expected: all three test binaries pass (`ok` lines, exit 0).

- [ ] **Step 5: Add the SHIMCRC hook.** In `gd_read_cart`
  (`shims/src/gd.c`), before the final `return 0;`:

```c
#if SHIM_CRC
    scif_puts("SHIMCRC o="); scif_puthex(cart_off);
    scif_puts(" l=");        scif_puthex(len);
    scif_puts(" c=");        scif_puthex(shim_crc32(
                                 (const void *)P2ADDR((unsigned long)dst), len));
    scif_puts("\n");
#endif
```

  Add near the top of the file (with the other `#ifndef` defaults, and the
  scif externs — `cart.c:53` has the declaration style to copy):

```c
#ifndef SHIM_CRC
#define SHIM_CRC 0      /* diagnostic: CRC every delivered cart read over serial */
#endif
#if SHIM_CRC
void scif_puts(const char *); void scif_puthex(unsigned int);
#endif
```

- [ ] **Step 6: Build both configurations.**
  Run: `make -C shims clean && make -C shims` — release build, must be
  byte-identical in behavior (flag compiled out).
  Run: `make -C shims clean && make -C shims DEFS='-DSHIM_SERIAL=1 -DSHIM_CRC=1'`
  Expected: both build clean; `shims/build/shim.map` in the diagnostic build
  shows `shim_crc32`; shim.bin still fits its 16 KB code window
  (`SHIM_BASE`→`SHIM_ERR`, i.e. size < 0x4000 — it was 5,896 B).
  Then rebuild release config (`make -C shims clean && make -C shims`) so no
  diagnostic artifact lingers.

- [ ] **Step 7: Commit.**

```bash
git add shims/src/gd.c shims/test/test_gd_math.c
git commit -m "phase5: SHIM_CRC delivered-bytes probe in gd_read_cart"
```

### Task 2: Fork drive-truth probe (`GDPIO`/`GDDMA`) + rebuild

**Files:**
- Modify: `../flycast4naomi2dreamcast/core/hw/gdrom/gdromv3.cpp`
- Modify: `../flycast4naomi2dreamcast/INSTRUMENTATION.md` (probe table)
- Modify: `docs/kb/tooling.md` (fork rebuild record)

**Interfaces:**
- Consumes: `cartlog(const char *fmt, ...)` from `core/hw/naomi/cartlog.h`.
- Produces: cartlog lines consumed by Task 3:
  `GDPIO fad=<hex8> secs=<hex> type=<hex> crc=<hex8>` (PIO refill path) and
  `GDDMA fad=<hex8> secs=<hex> type=<hex> crc=<hex8>` (DMA path). `fad` is
  the absolute FAD of the batch's first sector, `secs × type` bytes CRC'd.

- [ ] **Step 1: Add the probe.** In `gdromv3.cpp`, after the existing
  includes add:

```cpp
#include "hw/naomi/cartlog.h"

// Phase 5 (senkosp texture-hang gate): CRC-32/IEEE over every sector batch
// the emulated drive returns -- drive-truth for scripts/check_stream_crc.py.
// Same variant as the shim's shim_crc32 and Python zlib.crc32.
static u32 gd_crc32(const u8 *p, u32 len)
{
    u32 c = ~0u;
    while (len--) {
        c ^= *p++;
        for (int k = 0; k < 8; k++)
            c = (c >> 1) ^ (0xedb88320u & (0u - (c & 1u)));
    }
    return ~c;
}
```

  In the PIO refill (the `gds_readsector_pio` block, `gdromv3.cpp:252-264`),
  directly after the `libGDR_ReadSector((u8*)buffer, ...)` call and BEFORE
  `read_params.start_sector += sector_count;`:

```cpp
				cartlog("GDPIO fad=%08x secs=%x type=%x crc=%08x",
						read_params.start_sector, sector_count, read_params.sector_type,
						gd_crc32((const u8 *)buffer, sector_count * read_params.sector_type));
```

  In `DmaBuffer::fill` (`gdromv3.cpp:111-123`), directly after its
  `libGDR_ReadSector(cache, ...)` call and BEFORE
  `params.start_sector += count;`:

```cpp
	cartlog("GDDMA fad=%08x secs=%x type=%x crc=%08x",
			params.start_sector, count, params.sector_type,
			gd_crc32(cache, count * params.sector_type));
```

- [ ] **Step 2: Rebuild the fork.** Per
  `../flycast4naomi2dreamcast/INSTRUMENTATION.md` §13 (CMake 3.31.x, full
  Xcode `DEVELOPER_DIR`, arm64):
  Run: `cmake --build ../flycast4naomi2dreamcast/build -j"$(sysctl -n hw.ncpu)"`
  (incremental — the configured build tree exists; full recipe in §13 if it
  doesn't). Expected: exit 0.
  **Note:** `capture_dc_leg.sh` launches
  `../cleopatra/tools/flycast-src/build/Flycast.app` — establish which build
  tree that app comes from (it is the built fork per CLAUDE.md). If the
  fork's build output is not that path, copy/symlink the rebuilt binary to
  it and record the linkage in tooling.md.

- [ ] **Step 3: Smoke-test unattended (60 s attract).** One-call foreground
  pattern:

```bash
scripts/capture_dc_leg.sh phase5/probe-smoke & sleep 60; \
FPID=$(pgrep -f "Flycast.app/Contents/MacOS/Flycast" | head -1); \
kill -9 $FPID; wait
```

  Run: `grep -c 'GDPIO\|GDDMA' captures/phase5/probe-smoke.log`
  Expected: > 0 (the loader's boot reads alone guarantee hits).

- [ ] **Step 4: Record.** Add GDPIO/GDDMA rows to INSTRUMENTATION.md's probe
  table (§14 tag table); add a dated fork-rebuild row to
  `docs/kb/tooling.md` (commit hash of the fork after Step 5, flags, the
  smoke-test line count).

- [ ] **Step 5: Commit — both repos.**

```bash
cd ../flycast4naomi2dreamcast && git add core/hw/gdrom/gdromv3.cpp INSTRUMENTATION.md && \
  git commit -m "phase5(senkosp): GDPIO/GDDMA drive-truth CRC probes"
cd ../senkosp2dreamcast && git add docs/kb/tooling.md && \
  git commit -m "phase5: record fork GDPIO/GDDMA probe rebuild"
```

### Task 3: Offline checker `check_stream_crc.py`

**Files:**
- Create: `scripts/check_stream_crc.py`
- Create: `scripts/test_check_stream_crc.py`

**Interfaces:**
- Consumes: `SHIMCRC o= l= c=` lines (from a leg's `.stdout.log`, Task 1) and
  `GDPIO/GDDMA fad= secs= type= crc=` lines (from the leg's cartlog, Task 2).
- Consumes (ground truth): `senkosp.dat` (cart byte domain; the disc carries
  the PRISTINE image — the loader patches only the in-RAM boot images at
  load time, so streamed bytes must equal senkosp.dat bytes) and
  `build/track04.iso` (FAD domain: file offset = `(fad - 450150) * 2048`;
  track04 starts at LBA 450000, FAD = LBA + 150 — `scripts/make_gdi.py:149`;
  the cart region begins at FAD 451878 = `CART_FAD`).
- Produces: `CHECK <name>: PASS|FAIL (...)` lines + exit 0 iff all PASS —
  the same convention as `parse_cartlog.py`. Checks:
  `shimcrc_match` (every SHIMCRC line vs `dat[o:o+l]`),
  `gdread_match` (every GDPIO/GDDMA line with fad ≥ 450150 vs track04.iso;
  lines with fad < 450150 are TOC/low-track reads — counted and listed, not
  failed), `coverage_nonzero` (both streams present; FAIL on an
  instrumented leg that logged nothing — the null-instrument guard).
- Produces: `--tail N` — print the last N records of each stream (the
  "streams active before the hang" view Task 7 reads).

- [ ] **Step 1: Write the failing self-test.** `scripts/test_check_stream_crc.py`,
  same plain-assert style as `scripts/test_parse_cartlog.py`: build a
  temp dir with a 16 KiB fake dat (`bytes(range(256)) * 64`), a fake
  track04 (`b'\0' * (1728*2048)` boot region + the fake dat — mirrors the
  real layout `BOOT_REGION=3538944` scaled down: use boot region 2 sectors
  for the fixture and pass the boot-region size as a CLI flag), a stdout log
  with 2 correct + 1 wrong SHIMCRC lines, a cartlog with correct GDPIO and
  one fad < the track04 base. Assert: run via `subprocess`, wrong-CRC run
  exits 1 with `CHECK shimcrc_match: FAIL`, corrected run exits 0, low-fad
  line appears under `lowfad` in output but doesn't fail, empty-log run
  fails `coverage_nonzero`. Fixture CRCs computed in-test with
  `zlib.crc32`.
  Run: `python3 scripts/test_check_stream_crc.py`
  Expected: FAIL — script under test doesn't exist.

- [ ] **Step 2: Implement `scripts/check_stream_crc.py`.** Shape:

```python
#!/usr/bin/env python3
"""Verify SHIMCRC (delivered) + GDPIO/GDDMA (drive) lines against ground truth.
Spec: docs/superpowers/specs/2026-08-23-phase5-hardware-design.md (verdict table).
Conventions (CHECK lines, exit code) follow parse_cartlog.py."""
import argparse, re, sys, zlib

SHIMCRC = re.compile(r'SHIMCRC o=([0-9a-f]{8}) l=([0-9a-f]{8}) c=([0-9a-f]{8})')
GDREAD  = re.compile(r'GD(PIO|DMA) fad=([0-9a-f]{8}) secs=([0-9a-f]+) type=([0-9a-f]+) crc=([0-9a-f]{8})')
TRACK04_BASE_FAD = 450150          # LBA 450000 + 150 (make_gdi.py:149)

def crc(buf): return zlib.crc32(buf) & 0xffffffff
# parse both logs, verify each record, collect mismatches + lowfad list,
# print CHECK lines, honor --tail N, exit 0 iff all checks PASS.
```

  CLI: `check_stream_crc.py --stdout <leg.stdout.log> --cartlog <leg.log>
  --dat senkosp.dat --track04 build/track04.iso [--track04-base-fad N]
  [--tail N]`. Read ground-truth files with `mmap` or seek+read per record
  (records can sit anywhere in 251 MB — do NOT slurp whole files per line).

- [ ] **Step 3: Run the self-test to verify it passes.**
  Run: `python3 scripts/test_check_stream_crc.py`
  Expected: `ok`, exit 0.

- [ ] **Step 4: Run against the Task 2 smoke leg (real data).**
  Run: `python3 scripts/check_stream_crc.py --stdout captures/phase5/probe-smoke.stdout.log --cartlog captures/phase5/probe-smoke.log --dat senkosp.dat --track04 build/track04.iso`
  Expected: `gdread_match: PASS`; `shimcrc_match` will show n=0 (smoke leg
  ran a release shim — no SHIMCRC lines) and `coverage_nonzero` FAILs on
  that stream: correct behavior, notes the leg is not fully instrumented.
  (The fully-armed pass happens in Task 5.)

- [ ] **Step 5: Commit.**

```bash
git add scripts/check_stream_crc.py scripts/test_check_stream_crc.py
git commit -m "phase5: offline CRC checker for delivered/drive stream truth"
```

### Task 4: Texture-error handler — static characterization (Ghidra)

**Files:**
- Create: `scripts/ghidra/FindTexErrXrefs.java`
- Create: `docs/kb/phase5-hardware.md` (§Texture-error handler)

**Interfaces:**
- Consumes: the Ghidra project `senkosp3` (`scripts/ghidra/run.sh`; boot
  slice = first 1,515,512 B of senkosp.dat at base `0x8c020000`).
- Known anchors (verified by direct scan of senkosp.dat this plan-write):
  `TEXTURE LOAD ERROR !` at dat `0x168b8a` → P1 `0x8c188b8a` (inside the
  boot slice), preceded by a `...!\nFILE NAME:%s\n` format string and
  followed by `PACKTEX MA...`; test-image twin at dat `0x1bf8ae` (outside
  the boot slice — record, don't analyze).
- Produces (consumed by Task 7's verdict): §Texture-error handler in
  `docs/kb/phase5-hardware.md` — handler/caller addresses, and the **trigger
  taxonomy**: for each path that can print the string, is the proximate
  cause (a) a data-integrity check on loaded bytes, (b) an allocation /
  arena-space failure (KAMUI2 texture arena — VRAM-seed derived,
  `docs/kb/relocation-map.md`), or (c) a lookup/filename failure
  (`FILE NAME:%s` suggests a pack-file lookup path)?

- [ ] **Step 1: Write the xref script.** `scripts/ghidra/FindTexErrXrefs.java`
  (house pattern: `FindMmioXrefs.java`):

```java
// Refs to the TEXTURE LOAD ERROR string block. SH-4 reaches constants via
// literal pools, so a string's direct refs are usually pool words -- when a
// target has no code ref, dump refs to whatever DOES reference it (one hop).
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class FindTexErrXrefs extends GhidraScript {
    private void dumpRefs(Address a, int hop) {
        ReferenceIterator it = currentProgram.getReferenceManager().getReferencesTo(a);
        boolean any = false;
        while (it.hasNext()) {
            any = true;
            Reference r = it.next();
            Address from = r.getFromAddress();
            Function f = getFunctionContaining(from);
            println("XREF hop=" + hop + " to=" + a + " from=" + from +
                    " fn=" + (f == null ? "?" : f.getName() + "@" + f.getEntryPoint()));
            if (f == null && hop < 2) dumpRefs(from, hop + 1);   // pool word: follow
        }
        if (!any) println("NOREF to=" + a + " hop=" + hop);
    }
    @Override public void run() throws Exception {
        dumpRefs(toAddr(0x8c188b8aL), 0);   // "TEXTURE LOAD ERROR !"
    }
}
```

- [ ] **Step 2: Run it headlessly.**
  Run: `scripts/ghidra/run.sh script FindTexErrXrefs.java`
  Expected: at least one `XREF ... fn=FUN_...` line naming the printing
  function. If `NOREF` at every hop, the string may be reached by computed
  offset from the block start — fall back to dumping refs to the preceding
  `FILE NAME` string's start and to 32-byte-aligned addresses in the block
  (adjust the script's target list and re-run; record what worked).

- [ ] **Step 3: Characterize the handler.** In the Ghidra project (headless
  decompile dump via a variant of the script using
  `ghidra.app.decompiler.DecompInterface`, or targeted disassembly reads),
  walk: printing function → its callers → the branch conditions that reach
  the error path. Answer the taxonomy question (a)/(b)/(c) for every
  reachable path. Where the condition tests a return value, name the callee
  and what its failure means (KAMUI2 `km...` allocation vs decompress/
  signature check vs pack-directory lookup).

- [ ] **Step 4: Write the KB section.** Create `docs/kb/phase5-hardware.md`
  headed by phase/status/spec links (house style: see
  `docs/kb/phase4-conversion.md` top), with §Texture-error handler: the
  anchors, the xref chain (addresses cited), the trigger taxonomy, its
  Task 7 implication spelled out: *clean CRCs exonerate the emulator ONLY if
  the captured occurrence's path is (a)/(c)-with-good-bytes; path (b) is our
  fit bug and blocks hardware per the spec's hard gate.* Plus the operator
  note: the handler prints `FILE NAME:%s` — **photograph the full error
  text**; the filename names the failing asset.

- [ ] **Step 5: Commit.**

```bash
git add scripts/ghidra/FindTexErrXrefs.java docs/kb/phase5-hardware.md
git commit -m "phase5: texture-error handler xrefs + trigger taxonomy"
```

### Task 5: Diagnostic leg plumbing + instrument control test

**Files:**
- Modify: `scripts/capture_dc_leg.sh` (pass-through for extra Flycast args)
- Modify: `docs/kb/phase5-hardware.md` (§Instrument control test)

**Interfaces:**
- Produces: the **diagnostic leg recipe** every later task uses verbatim:

```bash
make gdi DEFS='-DSHIM_SERIAL=1 -DSHIM_CRC=1'        # diagnostic disc
scripts/capture_dc_leg.sh phase5/<leg> build/disc.gdi \
    -config Debug:SerialConsoleEnabled=yes           # serial -> .stdout.log
```

  (`make` command-line variables propagate to sub-makes, so root
  `make gdi DEFS=...` reaches `shims/Makefile`'s `CFLAGS += $(DEFS)`.
  `Debug.SerialConsoleEnabled=yes` is the Phase 4 Task 8 precedent for guest
  serial on Flycast stdout — `docs/kb/tooling.md` loader-alive-diag row.)

- [ ] **Step 1: Extend `capture_dc_leg.sh`.** Change the exec line to pass
  through any args after the GDI path:

```bash
FLYCAST_CARTLOG="$log" exec "$bin" -config config:rend.vsync=no "${@:3}" "$gdi" \
    > "${log%.log}.stdout.log" 2>&1
```

  (Flycast takes `-config section:key=value` flags before the content path.)
  Verify: `bash -n scripts/capture_dc_leg.sh`.

- [ ] **Step 2: Build the diagnostic disc.**
  Run: `make gdi DEFS='-DSHIM_SERIAL=1 -DSHIM_CRC=1'`
  Expected: exit 0; note this disc is diagnostic — do not let its tracks be
  mistaken for the release build (rebuild release at task end).

- [ ] **Step 3: Run the unattended control leg (~5 min attract).**

```bash
scripts/capture_dc_leg.sh phase5/instrument-ctl build/disc.gdi \
    -config Debug:SerialConsoleEnabled=yes & sleep 300; \
FPID=$(pgrep -f "Flycast.app/Contents/MacOS/Flycast" | head -1); \
kill -USR1 $FPID; sleep 5; kill -9 $FPID; wait
```

- [ ] **Step 4: Verify the instruments against their null leg.**
  Run: `python3 scripts/check_stream_crc.py --stdout captures/phase5/instrument-ctl.stdout.log --cartlog captures/phase5/instrument-ctl.log --dat senkosp.dat --track04 build/track04.iso`
  Expected: **all three CHECKs PASS** — every delivered and drive CRC
  matches ground truth, both streams non-empty. Also confirm no perf
  collapse: `grep -c 'PVRW STARTRENDER' captures/phase5/instrument-ctl.log`
  and compare frames-per-wall-clock against an equivalent Phase 4 attract
  window (`docs/kb/phase4-conversion.md` §Attract numbers) — same order of
  magnitude, no visible stutter class. If a CHECK fails here, STOP: the
  instrument is broken (or has found a constant-on bug); debug the
  instrument before any operator time is spent.

- [ ] **Step 5: Record + commit.** §Instrument control test in
  `phase5-hardware.md`: leg name, line counts, CHECK output verbatim, frame
  numbers. Rebuild release (`make gdi`) and note its md5s match criterion 7.

```bash
git add scripts/capture_dc_leg.sh docs/kb/phase5-hardware.md
git commit -m "phase5: diagnostic leg plumbing + instrument control test PASS"
```

### Task 6: Operator repro legs (STOP-AND-WAIT)

**Files:**
- Modify: `docs/kb/phase5-hardware.md` (§Repro campaign, one row per leg)

**Interfaces:**
- Consumes: the Task 5 diagnostic recipe verbatim.
- Produces: `captures/phase5/repro-<n>.{log,stdout.log}` legs; the campaign
  ends when one leg carries the hang (detector below). Every leg — hang or
  not — is checker-verified (a clean leg is rolling evidence the shim
  delivers correct bytes; log its CHECK results in the KB row).

- [ ] **Step 1: Prepare the printed session list, then STOP and WAIT.**
  Present to the operator (this is the whole step — no emulator launch):
  - Build first: `make gdi DEFS='-DSHIM_SERIAL=1 -DSHIM_CRC=1'`
  - Per session n = 1, 2, 3, …:
    `scripts/capture_dc_leg.sh phase5/repro-<n> build/disc.gdi -config Debug:SerialConsoleEnabled=yes`
  - **Play instruction (the sighted trigger):** 1P matches played to
    **winning the final round**, several matches per session; vary
    characters/stages. One session of the batch: the offered **2P
    run-all-stages** leg.
  - **On a hang:** note the on-screen text, `kill -USR1 <flycast-pid>`
    (screenshot), **photograph/note the `FILE NAME:` line** (Task 4), then
    kill by PID. Screenshots land in repo root as `Screenshot *.png` — they
    get moved to `docs/kb/img/` with descriptive names.
  - **On no hang:** quit normally after the planned matches; next session.

- [ ] **Step 2: After each returned batch — detect + verify.** Per leg:

```bash
F=captures/phase5/repro-<n>.log
grep -n 'MDODMA enter' "$F" | tail -1     # vs total lines: big gap = hang (play1 signature)
wc -l "$F"
python3 scripts/check_stream_crc.py --stdout "${F%.log}.stdout.log" \
    --cartlog "$F" --dat senkosp.dat --track04 build/track04.iso --tail 40
```

  Record one KB row per leg (§Repro campaign): matches played, hang?, CHECK
  results, notes. Clean batch → print the next batch (Step 1 again). Hang
  captured → Task 7.

- [ ] **Step 3: Commit KB rows as they land.**

```bash
git add docs/kb/phase5-hardware.md && git commit -m "phase5: repro campaign rows"
```

### Task 7: Verdict + hang-gate close

**Files:**
- Modify: `docs/kb/phase5-hardware.md` (§Texture-error hang verdict)
- Modify: `docs/kb/00-status.md` (hang-gate status)

**Interfaces:**
- Consumes: the hang leg's checker output (`--tail 40`), Task 4's trigger
  taxonomy, the operator's screenshot/`FILE NAME` note.
- Produces: the gate verdict, one of:
  1. delivered == GDI ∧ drive == GDI ∧ trigger path is data-validation or
     lookup with good bytes → **emulator-side; gate satisfied by
     exoneration** (spec Decision 2). Record; no fork fix required.
  2. delivered == GDI ∧ trigger path is allocation failure → **our fit
     bug** (VRAM arena / heap pressure at the transition). NOT exoneration.
     Fix required (below).
  3. delivered ≠ GDI ∧ drive == GDI → **our raw-ATA driver.** Fix required.
  4. drive ≠ GDI → **Flycast GD/IDE emulation.** Port bytes clean;
     fix-or-exonerate call presented to the user with the evidence.

- [ ] **Step 1: Classify.** Run the checker on the hang leg; read the tail
  against the taxonomy; write the classification with every number cited
  (log line refs, CRC pairs, screenshot filename).

- [ ] **Step 2: If a fix is required (verdicts 2/3, or 4-with-fix): STOP,
  present the evidence and the proposed fix scope to the user, then fix
  under superpowers:systematic-debugging.** The fix is authored from the
  captured evidence (it cannot be pre-written here). Non-negotiables from
  the spec: the fix must *explain the captured evidence*; then the
  reproducing scenario re-runs clean for **at least 6 operator sessions**
  (the observed 1-in-6 rate) **plus one ≥30-min unattended instrumented
  soak**, all checker-PASS. Shim-side fixes get a host test in
  `shims/test/` where the logic is host-testable (TDD).

- [ ] **Step 3: Close the gate in writing.** §Texture-error hang verdict in
  `phase5-hardware.md` (evidence-first, same standard as
  `phase4-conversion.md` §Texture-error hang); update `00-status.md`'s
  Phase 5 section: hang gate CLOSED (verdict named), hardware rounds now
  unblocked. Rebuild release `make gdi` from committed defaults; verify
  md5s against criterion 7 (or against the fixed build's new recorded md5s
  if the fix changed the disc — record both facts).

- [ ] **Step 4: Commit.**

```bash
git add docs/kb/phase5-hardware.md docs/kb/00-status.md
git commit -m "phase5: texture-hang verdict -- gate closed"
```

---

## Wave B — hardware bring-up & fit (after the Task 7 gate)

### Task 8: HUD parity — gd.c poll heartbeat

**Files:**
- Modify: `shims/src/gd.c` (heartbeat in the wait loops)
- Modify: `docs/kb/phase5-hardware.md` (§HUD kit — what the operator sees)

**Interfaces:**
- Consumes: `shim_mark(u32 slot, unsigned short color)` (`util.c`, HUD ON by
  default via `SHIM_HUD 1`).
- Produces: on-screen liveness for the drive path: a climbing/blinking mark
  while the shim polls the drive — frozen mark = wedged in a GD wait, the
  exact real-HW failure the emulator can't show (Cleopatra's gd.c carried
  the same: its §rows comment `../cleopatra/shims/src/gd.c:47`).

- [ ] **Step 1: Add the heartbeat.** In `gd_wait_drq` and `gd_wait_clear`
  (`shims/src/gd.c`), blink a dedicated HUD slot on a coarse spin-count
  stride so the paint cost stays off the fast path:

```c
        if (!(i & 0xffffu))                   /* every 64K polls: cheap, visible */
            shim_mark(6, (i & 0x10000u) ? 0x07e0 : 0x001f);  /* green<->blue blink */
```

  (Slot number: pick the first slot `util.c`'s slot map documents as free —
  read its comment block; if 6 is taken, use the next free one and record
  the choice in the KB section. `SHIM_HUD 0` builds compile `shim_mark` to a
  no-op, so no release-path cost question arises.)

- [ ] **Step 2: Host tests still pass.**
  Run: `make -C shims test`
  Expected: pass — the heartbeat sits inside `#if !HOST_TEST` code.

- [ ] **Step 3: Emulator smoke with screenshot.** Rebuild
  (`make gdi`), run a 60 s unattended leg (Task 2 Step 3 pattern, leg
  `phase5/hud-smoke`, add `kill -USR1` before the kill), read the
  `FLYCAST_SHOT` frame: breadcrumb blocks visible, no visual regression.

- [ ] **Step 4: Write §HUD kit for the operator.** In `phase5-hardware.md`:
  the slot map (from `util.c`'s comments + this heartbeat), death-screen
  decoding (`gd.c` failure sites `GD_E_*` 1–8 → red screen `0x6<site>`
  codes, `shim_die` field order), what "healthy boot" vs "wedged" looks like
  on a TV. This is the table the operator reads during Task 10 rounds.

- [ ] **Step 5: Commit.**

```bash
git add shims/src/gd.c docs/kb/phase5-hardware.md
git commit -m "phase5: gd wait-loop HUD heartbeat + operator HUD table"
```

### Task 9: SD mastering + hardware control test (operator)

**Files:**
- Modify: `docs/kb/phase5-hardware.md` (§Mastering, §Control test)

**Interfaces:**
- Consumes: `build/disc.gdi` + tracks (release build, criterion-7 md5s
  re-verified first), the donor control disc `'[GDI] Dolphin Blue.7z'`
  (repo root), the playbook trap list (`docs/kb/port-playbook.md` §Gotchas),
  Cleopatra's mastering record (`../cleopatra/docs/kb/00-status.md` — GDEMU
  rounds; `drive-safety.md` if VMU/SD handling notes apply).
- Produces: an SD card that boots the control disc, then carries senkosp;
  photographic evidence in `docs/kb/img/`.

- [ ] **Step 1: Verify the release build before it travels.**
  Run: `make gdi && md5 build/track01.iso build/track02.raw build/track03.iso build/track04.iso build/disc.gdi`
  Expected: matches the criterion-7 md5s (or Task 7's re-recorded ones).

- [ ] **Step 2: Print the operator checklist, then STOP and WAIT.**
  - Extract Dolphin Blue GDI from the 7z into its own folder.
  - SD layout per GDEMU convention (numbered game folders, GDEMU firmware
    as on the Cleopatra rounds — same card/firmware that already worked:
    v5.20.5 era per `../cleopatra/docs/kb/00-status.md`).
  - Copy senkosp's five disc files (`disc.gdi`, `track01.iso`,
    `track02.raw`, `track03.iso`, `track04.iso`) into their folder.
  - **`dot_clean` the card** (AppleDouble `._*` sidecars — the playbook's
    masquerading boot bug) and eject cleanly.
  - Boot order: **control disc first** (isolates card/GDEMU/process from
    our bytes), then senkosp.
  - Photograph: GDEMU slot screen, control-disc boot, senkosp's first
    on-screen state whatever it is (splash, HUD blocks, error, black).
- [ ] **Step 3: Record the returned evidence.** §Mastering + §Control test
  rows: card, firmware, `dot_clean` run, control-disc verdict (must be
  "boots" before any senkosp conclusion is drawn — if the control disc
  fails, the problem is process, not port; fix that first), photos moved to
  `docs/kb/img/phase5-*.{jpg,png}` and cited.

- [ ] **Step 4: Commit.**

```bash
git add docs/kb/phase5-hardware.md docs/kb/img/
git commit -m "phase5: SD mastering + hardware control test evidence"
```

### Task 10: First senkosp boot on hardware — debugging rounds (operator + agent)

**Files:**
- Modify: `docs/kb/phase5-hardware.md` (§Hardware rounds, one section per round)

**Interfaces:**
- Consumes: Task 8's §HUD kit table (the operator's decoder ring), Task 9's
  proven card, the spec's known-risk index (MIE boot ladder timing, BIOS
  blob placement, 91 B watermark headroom).
- Produces: **exit criterion 2** — senkosp boots to attract on the bench
  DC + GDEMU, photo evidence; plus a dated round log for every attempt,
  pass or fail.

- [ ] **Step 1: Print round-1 instructions, STOP and WAIT.** Boot senkosp
  from the card; observe against the §HUD kit table; photograph every
  distinct on-screen state; note timings (how long at each state). If a red
  death screen: photograph it — the hex fields decode to site + FAD + status
  per Task 8's table.
- [ ] **Step 2: Per returned round — diagnose before changing anything.**
  Use superpowers:systematic-debugging. House rules for this campaign,
  from the playbook's cost ledger: structural/mastering explanations FIRST
  (control test again if in doubt), binary explanations after; one variable
  per round; every conclusion cited to a photo or HUD state. Secondary
  channel decision when stuck: DreamShell serial-SD dongle for isoldr-path
  boots or serial logs — **note the conflict:** `SHIM_SERIAL` drives the
  same SCIF pins serial-SD dongles use (`shims/src/scif.c` header), so a
  serial-SD boot and a serial-printing shim are mutually exclusive; pick
  per round and record which.
- [ ] **Step 3: Iterate rounds until attract.** Each fix lands as its own
  commit with its evidence row; each new disc build re-runs
  `make -C shims test` + `make gdi` and re-masters per Task 9's checklist.
- [ ] **Step 4: Bank criterion 2.** §Hardware rounds closing row: attract on
  hardware, photo cited, disc build md5s named.

```bash
git add docs/kb/phase5-hardware.md docs/kb/img/
git commit -m "phase5: hardware round N -- <finding>"
```

### Task 11: Play criteria on hardware + pad-poll disposition (operator)

**Files:**
- Modify: `docs/kb/phase5-hardware.md` (§Play criteria, §Pad-poll latency)
- Possibly modify: `shims/src/main.c` (the `#if 0` TCNT0 cache at `:489`,
  only if lag is observed)

**Interfaces:**
- Consumes: criterion 2 banked; the staged remedy
  (`shims/src/main.c:489` `#if 0 /* re-enabled per-task */`, design at
  `docs/kb/phase4-conversion.md` §Steady input finding 5).
- Produces: exit criteria 3–7 evidence.

- [ ] **Step 1: Print the session list, STOP and WAIT.** One consolidated
  hardware session: (a) full 1P match, every control exercised per
  `docs/kb/input-map.md` §DC pad layout; (b) 2P match with mid-game Start
  join on port B; (c) test-menu round trip — hold A+Start through boot →
  GAME TEST MENU → change a setting → SYSTEM MENU EXIT → console reboots →
  attract; (d) free-play — Start alone starts a match from attract;
  (e) **explicit input-feel verdict**: any lag, slow 2P, missed inputs
  (Cleopatra's real-HW symptom) — yes or no, in the operator's words.
- [ ] **Step 2: Bank criteria 3–6** from the operator's attestation +
  photos, one KB row each, same evidence standard as Phase 4's operator
  legs (attestation quoted, not paraphrased).
- [ ] **Step 3: Disposition pad-poll latency (criterion 7).**
  - No lag reported → record "no lag observed on hardware, cache left
    staged" with the attestation. Done.
  - Lag reported → enable the block: remove the `#if 0`/`#endif` pair at
    `shims/src/main.c:489` (its round-16/17 comments carry the design;
    keep them), `make -C shims test && make gdi`, re-master, re-run
    Step 1(a,b,e). Both states recorded; the fix commit cites the before/
    after attestations.
- [ ] **Step 4: Commit.**

```bash
git add docs/kb/phase5-hardware.md docs/kb/img/ shims/src/main.c
git commit -m "phase5: play criteria on hardware + pad-poll disposition"
```

### Task 12: Cyan splash — explain or reclassify

**Files:**
- Modify: `docs/kb/phase5-hardware.md` (§Cyan splash)

**Interfaces:**
- Consumes: Phase 4's observation record (`docs/kb/phase4-conversion.md`
  §Findings for Phase 5 item 2 — cyan-tinted Naomi splash, ~1 s, every
  emulator boot, unexplained); hardware boots from Tasks 10–11 (the
  operator has now watched several).
- Produces: exit criterion 8 — explained or reclassified, hardware
  observation recorded.

- [ ] **Step 1: Ask the operator (with the Task 10/11 batches, not a
  separate session):** did the cyan-tinted splash appear on the TV during
  any hardware boot? Yes/no + phone photo if yes.
- [ ] **Step 2: Branch.**
  - **Absent on hardware** → reclassify: emulator-only rendering artifact;
    record with both observations cited (emulator: every boot; hardware:
    absent, sessions counted). Optionally note the fork-side suspicion for
    the record; no fix owed (spec: cosmetic, explain-or-reclassify).
  - **Present on hardware** → it's real: capture the boot window
    frame-by-frame in the emulator to localize it. Method: repeated
    `kill -USR1` `FLYCAST_SHOT` snaps across a scripted boot
    (`for i in $(seq 40); do kill -USR1 $FPID; sleep 0.25; done` against an
    unattended boot leg) — if 4 Hz sampling is too coarse to catch the
    transition, add a fork frame-dump probe (a `FLYCAST_SHOT_EVERY=n`
    variant of the existing screenshot path) and record it in
    INSTRUMENTATION.md + tooling.md. Localize which boot stage paints cyan
    (loader video init, KERNEL-SLICE handoff, game's own splash draw — the
    candidates from the Phase 4 record), explain, and decide fix-vs-record
    with the user.
- [ ] **Step 3: Write §Cyan splash + commit.**

```bash
git add docs/kb/phase5-hardware.md docs/kb/img/
git commit -m "phase5: cyan splash dispositioned"
```

### Task 13: Gate audit + status advance

**Files:**
- Modify: `docs/kb/phase5-hardware.md` (§Gate audit)
- Modify: `docs/kb/00-status.md` (Phase 5 checklist; advance to Phase 6)

- [ ] **Step 1: Audit all nine exit criteria** against the spec §Exit
  criteria — one row per criterion with the file + evidence that earns it,
  the Phase 4 checklist's format. Any criterion not unqualified-`[x]` gets
  the Phase 3 `[~]` treatment: what exactly is missing, what would close it
  — no silent rounding up.
- [ ] **Step 2: Reproducibility check.** Fresh `make gdi` from committed
  defaults; md5s vs the recorded release set; `make -C shims test`,
  `python3 scripts/test_check_stream_crc.py`, `python3 scripts/test_parse_cartlog.py`,
  `python3 scripts/test_maple_literals.py` — all green, outputs quoted in
  the audit row.
- [ ] **Step 3: Advance `00-status.md`.** Phase 5 checklist section (the
  audit table mirrored), phase list updated (5 → DONE if all nine hold),
  §Next step rewritten for Phase 6 (safety tripwires & release — the
  playbook's three-tripwire recipe), honest-limit note updated to what is
  now actually proven (single-rig scope per spec §Honest limit).
- [ ] **Step 4: Commit.**

```bash
git add docs/kb/phase5-hardware.md docs/kb/00-status.md
git commit -m "phase5: gate audit -- status advanced"
```

---

## Self-review (done at plan-write)

- **Spec coverage:** hang gate Decisions 1–4 → Tasks 1–7; Decision 5 scope →
  Tasks 11 (latency), 12 (splash), VMU absent (out of scope honored);
  Decision 6 rig → Tasks 9–11; work item 2's HUD/mastering/control-test/
  rounds → Tasks 8–10; exit criteria 1–9 → Tasks 7, 10, 11 (×4), 11, 12, 13.
- **Known deviations from spec, argued above:** runtime hang marker →
  static characterization + post-hoc signature (interpreter constraint);
  verdict table branch 2 added (allocation-failure trigger ≠ exoneration).
- **Type consistency:** `shim_crc32(const void*, unsigned)` (Task 1) is what
  Task 1's hook calls; SHIMCRC/GDPIO/GDDMA line grammars (Tasks 1–2) match
  Task 3's regexes; `check_stream_crc.py` CLI is identical at every call
  site (Tasks 3, 5, 6); heartbeat uses existing
  `shim_mark(u32, unsigned short)`.
- **Unverifiable-here details flagged in-task, not hidden:** free HUD slot
  number (Task 8 Step 1), Flycast binary path vs fork build tree (Task 2
  Step 2), literal-pool hop fallback (Task 4 Step 2).

# Phase 3 — Reverse Engineering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Find and prove every hardware touchpoint address in the senkosp
binary, produce the relocation patch set for the 5 above-16m main-RAM
corridors + above-8m VRAM placement, and prove it with a dry run on the
Naomi profile.

**Architecture:** Static Ghidra analysis (headless, committed Java scripts)
as the spine; dynamic guest-PC logging from the instrumented Flycast fork as
proof. Capstone: a patched `.dat` runs on the Naomi profile with all content
below the DC caps.

**Tech Stack:** Ghidra 12.1.2 (reused install, `SuperH4:LE:32`), the
instrumented Flycast fork (build tree `../cleopatra/tools/flycast-src`),
Python 3 (parser + scanners, stdlib only), zsh/bash.

**Spec:** `docs/superpowers/specs/2026-08-19-phase3-reverse-engineering-design.md`
— the plan argues from the spec; executors read both.

## Global Constraints

- **Never commit or upload ROM bytes**: `tools/boot.bin`, `tools/ghidra-proj`,
  `senkosp-reloc.dat`, all `captures/` logs stay gitignored (`.gitignore`
  already covers `/tools/`, `*.dat`, `/captures/`). Check `git status` before
  every commit.
- **Every KB hardware claim carries a citation**; primary sources (emulator/
  binary/library source) outrank wikis.
- **Record every tool step in `docs/kb/tooling.md`** (installs, rebuilds,
  recipes) — the pipeline must be reproducible by a session that wasn't there.
- **Flycast CLI**: `-config` flags must come BEFORE the ROM path (everything
  after the first non-flag arg is silently dropped). Grep every run's stdout
  for `ignored` to verify.
- **Capture legs are primary data — never overwrite** (`capture_leg.sh`
  enforces). Only `canary-*` smoke logs may be deleted.
- **Phase 3 legs live in `captures/phase3/`** so the Phase 2 glob
  (`captures/*.log`) never picks them up and Phase 2 results stay
  reproducible.
- **Fork changes**: edit + commit in `../cleopatra/tools/flycast-src` (the
  build tree, currently `405776c12` = `f014a410c` + 12 additive cartlog-watch
  commits), then `git push origin HEAD` — origin IS the
  `flycast4naomi2dreamcast` source-of-truth repo on GitHub.
- **Interpreter mode** (`Dynarec.Enabled = no` in
  `~/Library/Application Support/Flycast/emu.cfg`, line ~39) only for the PC
  leg; restore `yes` afterward (interpreter is ~10× slower).
- A static/dynamic disagreement is a **stop-and-debug event**
  (superpowers:systematic-debugging), never papered over.
- Python: stdlib only, no new dependencies. Tests follow the repo's existing
  assert-style self-check pattern (`scripts/test_parse_cartlog.py` — run
  directly with `python3`, exit 0 = pass), not pytest.

---

### Task 1: Ghidra harness — boot slice, import, smoke

**Files:**
- Create: `scripts/ghidra/run.sh`
- Create: `scripts/ghidra/*.java` (copied from `../cleopatra/scripts/ghidra/`)
- Modify: `scripts/ghidra/DisasmEntry.java` (entry constant)
- Create: `tools/boot.bin` (gitignored, never committed)

**Interfaces:**
- Produces: `scripts/ghidra/run.sh import` and
  `scripts/ghidra/run.sh script NAME.java [args...]` — the invocation every
  later Ghidra task uses. Imported program: name `senkosp3`, base
  `0x8c020000`, full SH-4 auto-analysis.

- [ ] **Step 1: Copy the Cleopatra script kit**

```bash
mkdir -p scripts/ghidra tools
cp ../cleopatra/scripts/ghidra/*.java scripts/ghidra/
```

(11 files: Decomp, DisasmEntry, DisasmRange, DumpEntryChain, ExportToXML,
FindMmioXrefs, FindRefsTo, ListPoolWords, ScanBiosTargets, WhichFunc — plus
run.sh which we rewrite next, so don't copy it.)

- [ ] **Step 2: Write `scripts/ghidra/run.sh`**

```sh
#!/bin/sh
# Re-runnable Ghidra headless harness for the Phase 3 boot-binary analysis.
# Usage:
#   scripts/ghidra/run.sh import              # import tools/boot.bin + full auto-analysis
#   scripts/ghidra/run.sh script NAME.java [args...]
# ROM content: tools/boot.bin and tools/ghidra-proj are gitignored (/tools/). Never commit.
set -e
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
GHIDRA_HOME="${GHIDRA_HOME:-$REPO/../cleopatra/tools/ghidra_12.1.2_PUBLIC}"
PROJ="$REPO/tools/ghidra-proj"
NAME=senkosp3
BOOT="$REPO/tools/boot.bin"
HL="$GHIDRA_HOME/support/analyzeHeadless"

# openjdk from brew (see ../cleopatra/docs/kb/tooling.md §Ghidra) — Java 21+.
export PATH="/opt/homebrew/opt/openjdk/bin:$PATH"

[ -x "$HL" ] || { echo "ERROR: analyzeHeadless not found: $HL" >&2; exit 1; }
[ -f "$BOOT" ] || { echo "ERROR: boot slice missing: $BOOT  (head -c 1515512 senkosp.dat > tools/boot.bin)" >&2; exit 1; }
mkdir -p "$PROJ"

case "${1:-}" in
  import)
    # No -noanalysis => full SH-4 auto-analysis (follows jmp @rN via literal pools).
    "$HL" "$PROJ" "$NAME" -import "$BOOT" -overwrite \
      -processor "SuperH4:LE:32:default" \
      -loader BinaryLoader -loader-baseAddr 0x8c020000
    ;;
  script)
    [ -n "${2:-}" ] || { echo "usage: $0 script NAME.java [args...]" >&2; exit 1; }
    SCRIPT="$2"; shift 2
    "$HL" "$PROJ" "$NAME" -process boot.bin -noanalysis \
      -scriptPath "$REPO/scripts/ghidra" -postScript "$SCRIPT" "$@"
    ;;
  *) echo "usage: $0 import | script NAME.java [args...]" >&2; exit 1 ;;
esac
```

```bash
chmod +x scripts/ghidra/run.sh
```

- [ ] **Step 3: Slice the boot binary**

The main load entry is ROM `0x0` → RAM `0x8c020000`, `0x171ff8` =
1,515,512 bytes (`docs/kb/game.md` §Parsed .dat header).

```bash
head -c 1515512 senkosp.dat > tools/boot.bin
stat -f%z tools/boot.bin   # expect: 1515512
md5 tools/boot.bin         # record the hash — it goes in tooling.md (Task 13)
```

- [ ] **Step 4: Import + auto-analysis**

Run: `scripts/ghidra/run.sh import`
Expected: exit 0; log contains `Import succeeded`; analysis takes a few
minutes. Grep stdout for `ERROR` — none expected.

- [ ] **Step 5: Smoke — disassemble the senkosp entry**

Edit `scripts/ghidra/DisasmEntry.java`: change
`private static final long ENTRY = 0x8c04ae2cL;` to
`private static final long ENTRY = 0x8c021000L;` (senkosp entrypoint,
`docs/kb/game.md`).

Run: `scripts/ghidra/run.sh script DisasmEntry.java`
Expected: 32 decoded SH-4 instructions printed from `0x8c021000` (real
mnemonics — `mov`, `sts`, `bra` forms — not `.word` junk). If it prints
undecoded data, STOP: the base/processor import is wrong; do not proceed.

- [ ] **Step 6: Commit**

```bash
git status   # verify: no tools/, no *.dat, no captures/
git add scripts/ghidra
git commit -m "Phase 3: Ghidra headless harness — Cleopatra script kit adapted, senkosp3 project imports"
```

---

### Task 2: Entry chain + SP verdict (target 7 static)

**Files:**
- Modify: `scripts/ghidra/DumpEntryChain.java`
- Create: `docs/kb/boot-binary.md` (started; grows through Tasks 3–4, 9–10,
  finalized in Task 13)

**Interfaces:**
- Produces: the **stack region `LO-HI`** (hex, P1 addresses) recorded in
  `boot-binary.md` §Entry chain & SP — Task 9 passes it to the parser as
  `--stack LO-HI`; Task 10 uses it in the below-16m free-space map.

- [ ] **Step 1: Adapt the entry constant**

Edit `scripts/ghidra/DumpEntryChain.java`: change
`private static final long ENTRY = 0x8c04ae2cL;` to `0x8c021000L`, and
update the header comment to name senkosp. (The script follows a pool-loaded
`jmp @rN` if the entry is a trampoline, and dumps every `r15` write with its
pool constant — it copes whether or not senkosp has a Cleopatra-style
trampoline.)

- [ ] **Step 2: Run it**

Run: `scripts/ghidra/run.sh script DumpEntryChain.java`
Expected: entry disassembly + at least one flagged `r15` write with a pool
constant. If no `r15` write is found in the dumped window, widen the dump
(the script's instruction-count constant) and re-run — the init code that
sets SP must exist.

- [ ] **Step 3: Record the verdict**

Create `docs/kb/boot-binary.md` with header ("Boot-binary map — senkosp
(Phase 3)") and §Entry chain & SP: the chain from `0x8c021000`, the SP
value, and the verdict with address citations:
- SP phys < `0x0d000000` (below the 16 MB line) → "main RAM safe as-is".
- SP near 32 MB → "Phase 4 must relocate SP — one-constant patch at
  `<address>`", noted for Phase 4.
Record the stack region as `LO-HI` (e.g. `8cff0000-8d000000` — whatever the
read value implies) for Task 9's `--stack` and Task 10's free-space map.

- [ ] **Step 4: Commit**

```bash
git add scripts/ghidra/DumpEntryChain.java docs/kb/boot-binary.md
git commit -m "Phase 3: entry chain + SP verdict (target 7 static)"
```

---

### Task 3: BIOS-range scan (target 1 static)

**Files:**
- Copy already present: `scripts/ghidra/ScanBiosTargets.java` (generic — no
  Cleopatra-specific constants; verify by reading it before running)
- Modify: `docs/kb/boot-binary.md` (§BIOS-call verdict)

**Interfaces:**
- Produces: the static half of the BIOS verdict; Task 9's `no_bios_exec`
  check is the dynamic half.

- [ ] **Step 1: Run the scan**

Run: `scripts/ghidra/run.sh script ScanBiosTargets.java`
Expected: `NONE` / 0 hits (no flow reference and no pool constant resolving
into phys `0x0`–`0x1fffff`). If there ARE hits: record each (address,
constant, containing function) — they become mandatory Task 9/10 follow-ups
(a real BIOS call means the Phase 4 loader must reimplement that routine;
do not silently drop it).

- [ ] **Step 2: Record in `boot-binary.md`**

§BIOS-call verdict: the scan result, the caveat verbatim from the spec (a
computed non-pool branch target could evade the static scan; the dynamic
backstop covers executed paths only), and "dynamic half: Task 9".

- [ ] **Step 3: Commit**

```bash
git add docs/kb/boot-binary.md
git commit -m "Phase 3: BIOS-range static scan (target 1) — verdict recorded"
```

---

### Task 4: MMIO xrefs — cart/G1/Maple/PVR-FB/RTC/SCIF/WDT (targets 2, 5, 6, 8 static)

**Files:**
- Modify: `scripts/ghidra/FindMmioXrefs.java` (extend watched blocks)
- Modify: `scripts/ghidra/Decomp.java` (point at the RTC/SCIF-referencing
  functions found — it carries a hardcoded address list like WhichFunc;
  adapt the same way)
- Modify: `docs/kb/boot-binary.md`

**Interfaces:**
- Produces: **candidate function ranges** recorded in `boot-binary.md`
  §Candidates: `cart_fn` (cart+g1dma referencers), `input_fn` /
  `eeprom_fn` (maple referencers; may share a path — record both), each as
  `LO-HI` P1 hex. Task 9 passes them as `--cart-fn/--input-fn/--eeprom-fn`.
- Produces: RTC/SCIF/watchdog verdicts (target 8, static-only by nature).

- [ ] **Step 1: Extend the watched blocks**

In `scripts/ghidra/FindMmioXrefs.java` replace the `BLOCKS`/`LABELS` pair
with:

```java
    private static final long[][] BLOCKS = {
        {0x005f7000L, 0x005f7014L}, // cart ROM-board regs
        {0x005f7400L, 0x005f74ffL}, // G1 GD-ROM DMA channel
        {0x005f6c00L, 0x005f6cffL}, // Maple bus controller
        {0x005f8050L, 0x005f8067L}, // PVR FB_R_SOF1/2 + FB_W_SOF1/2 (VRAM/FB placement)
        {0x00710000L, 0x0071ffffL}, // Naomi RTC (guts scan: 3 refs to trace)
        {0x1fe80000L, 0x1fe8ffffL}, // SH-4 SCIF (0xffe80000 & 0x1fffffff)
        {0x1fc00000L, 0x1fc000ffL}, // SH-4 WDT (WTCNT/WTCSR) — expect zero
    };
    private static final String[] LABELS = {"cart", "g1dma", "maple", "pvr_fb", "rtc", "scif", "wdt"};
```

- [ ] **Step 2: Run + collect**

Run: `scripts/ghidra/run.sh script FindMmioXrefs.java`
Expected: `XREF block=cart ...` and `block=g1dma`/`block=maple` hits exist
(the game must stream and poll input); `rtc` hits ≈ 3 (matching the guts
scan, `00-status.md` key facts); `wdt` hits = 0. Save the full output to
`tools/mmio-xrefs.txt` (gitignored working file).

- [ ] **Step 3: RTC/SCIF verdicts via decompilation**

Adapt `Decomp.java`'s address list to the `rtc` and `scif` hit functions;
run it; classify each ref: dead code (unreferenced function / unreachable
branch), compile-time gated (constant-false condition), or reachable.
Cross-cite Phase 2's dynamic zero (`phase2-measurements.md` §Device
verdicts: 0 pokes in 14 legs). Verdict per device in `boot-binary.md`
§RTC/SCIF/watchdog: **shim or ignore** for Phase 4.

- [ ] **Step 4: Candidate ranges**

From the `cart`/`g1dma` hits, name the cart-read candidate function(s);
from `maple`, the input/EEPROM path candidates. Record in `boot-binary.md`
§Candidates as `name: LO-HI` (use the functions' body bounds from the XREF
output; refine later with WhichFunc if a body looks truncated). These are
*candidates* — Task 9 proves them.

- [ ] **Step 5: Commit**

```bash
git add scripts/ghidra/FindMmioXrefs.java scripts/ghidra/Decomp.java docs/kb/boot-binary.md
git commit -m "Phase 3: MMIO xref sweep — cart/maple candidates, RTC/SCIF/WDT verdicts (targets 2,5,6,8 static)"
```

---

### Task 5: Placement-constant scan (target 3 static, candidate generator)

**Files:**
- Create: `scripts/ghidra/ScanPlacementConstants.java`
- Create: `scripts/scan_dat_constants.py`
- Create: `scripts/test_scan_dat_constants.py`

**Interfaces:**
- Produces: `PLACE range=<label> word=0x... at=<addr> fn=<fn>` lines (boot
  image) and `DATHIT off=0x... word=0x... range=<label>` lines (full
  `.dat`) — Task 10's candidate list for provenance slicing.
- The two scanners share one range table — keep them in sync (comment in
  both files says so).

- [ ] **Step 1: Write the Ghidra scanner**

`scripts/ghidra/ScanPlacementConstants.java`:

```java
// Phase 3 target 3: candidate provenance sites for above-cap placement.
// Scans every 4-byte-aligned LE word of the imported boot image for values
// resolving (29-bit phys) into one of the 5 above-16m main-RAM corridors
// (docs/kb/cart-streaming-map.md) or above-8m VRAM, printing address, value,
// containing function (or "data"). Keep RANGES in sync with
// scripts/scan_dat_constants.py.
//@category Senkosp
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.*;

public class ScanPlacementConstants extends GhidraScript {
    private static final long[][] RANGES = {
        {0x0d244c20L, 0x0dd73e00L}, // corridor 1 (main off 0x1244c20-0x1d73e00)
        {0x0dd7d020L, 0x0dd92020L}, // corridor 2
        {0x0ddc2960L, 0x0dde3960L}, // corridor 3
        {0x0de4dbe0L, 0x0de8b480L}, // corridor 4
        {0x0dfe6d20L, 0x0dfe7520L}, // corridor 5
        {0x04800000L, 0x04ffffffL}, // VRAM above-8m, 64-bit window
        {0x05800000L, 0x05ffffffL}, // VRAM above-8m, 32-bit window
    };
    private static final String[] LABELS = {
        "corridor1", "corridor2", "corridor3", "corridor4", "corridor5",
        "vram64", "vram32"};

    @Override
    public void run() throws Exception {
        Memory mem = currentProgram.getMemory();
        MemoryBlock blk = mem.getBlocks()[0];
        int hits = 0;
        for (Address a = blk.getStart(); a.compareTo(blk.getEnd().subtract(3)) <= 0; a = a.add(4)) {
            long v = ((long) mem.getInt(a)) & 0xffffffffL;
            long phys = v & 0x1fffffffL;
            for (int r = 0; r < RANGES.length; r++) {
                if (phys >= RANGES[r][0] && phys <= RANGES[r][1]) {
                    Function f = getFunctionContaining(a);
                    println(String.format("PLACE range=%s word=0x%08x at=%s fn=%s",
                            LABELS[r], v, a,
                            f == null ? "data" : f.getName() + "@" + f.getEntryPoint()));
                    hits++;
                }
            }
        }
        println("PLACE-TOTAL hits=" + hits);
    }
}
```

- [ ] **Step 2: Write the failing test for the `.dat` scanner**

`scripts/test_scan_dat_constants.py`:

```python
#!/usr/bin/env python3
"""Self-check for scan_dat_constants.py — synthetic image, known hits."""
import os
import struct
import tempfile

import scan_dat_constants as S

# corridor1 value (0x8d244c20 -> phys 0x0d244c20), vram64 value, and noise.
words = [0x00000000, 0x8d244c20, 0xdeadbeef, 0x04810000, 0x0e000000]
with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
    f.write(struct.pack("<%dI" % len(words), *words))
    path = f.name
try:
    hits = S.scan(path)
    assert hits == [(4, 0x8d244c20, "corridor1"), (12, 0x04810000, "vram64")], hits
    print("OK scan_dat_constants self-check")
finally:
    os.unlink(path)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd scripts && python3 test_scan_dat_constants.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'scan_dat_constants'`

- [ ] **Step 4: Write the scanner**

`scripts/scan_dat_constants.py`:

```python
#!/usr/bin/env python3
"""Scan a flat Naomi image for LE u32 words whose 29-bit physical value lands
in a watched range (above-cap corridors / VRAM). Candidate generator for
Phase 3 target 3 — catches descriptor tables OUTSIDE the boot slice (streamed
data). Keep RANGES in sync with scripts/ghidra/ScanPlacementConstants.java.

Usage: scan_dat_constants.py senkosp.dat
Output: DATHIT off=0x<file offset> word=0x<value> range=<label>
"""
import argparse
import array
import sys

RANGES = [  # (label, lo, hi) — 29-bit physical, inclusive
    ("corridor1", 0x0d244c20, 0x0dd73e00),
    ("corridor2", 0x0dd7d020, 0x0dd92020),
    ("corridor3", 0x0ddc2960, 0x0dde3960),
    ("corridor4", 0x0de4dbe0, 0x0de8b480),
    ("corridor5", 0x0dfe6d20, 0x0dfe7520),
    ("vram64",    0x04800000, 0x04ffffff),
    ("vram32",    0x05800000, 0x05ffffff),
]


def scan(path):
    with open(path, "rb") as f:
        data = f.read()
    words = array.array("I")
    words.frombytes(data[: len(data) // 4 * 4])
    if sys.byteorder != "little":
        words.byteswap()
    hits = []
    # ponytail: ~62M-word pure-python loop, ~1 min on the 250 MB .dat — fine
    # for a one-shot analysis; vectorize only if it gets re-run in a loop.
    for i, w in enumerate(words):
        p = w & 0x1FFFFFFF
        for label, lo, hi in RANGES:
            if lo <= p <= hi:
                hits.append((i * 4, w, label))
                break
    return hits


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    args = ap.parse_args(argv)
    for off, w, label in scan(args.image):
        print(f"DATHIT off=0x{off:08x} word=0x{w:08x} range={label}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd scripts && python3 test_scan_dat_constants.py`
Expected: `OK scan_dat_constants self-check`, exit 0.

- [ ] **Step 6: Run both scanners for real**

```bash
scripts/ghidra/run.sh script ScanPlacementConstants.java > tools/place-boot.txt
python3 scripts/scan_dat_constants.py senkosp.dat > tools/place-dat.txt
wc -l tools/place-boot.txt tools/place-dat.txt
```

Expected: nonzero hits (the corridors' base addresses must be *somewhere*).
Interpretation and slicing is Task 10 — here just confirm the outputs exist
and note hit counts. High noise in `place-dat.txt` is expected (any asset
byte pattern can collide); the boot-image scan with function context is the
primary signal.

- [ ] **Step 7: Commit**

```bash
git add scripts/ghidra/ScanPlacementConstants.java scripts/scan_dat_constants.py scripts/test_scan_dat_constants.py
git commit -m "Phase 3: placement-constant scanners (target 3 candidates) — boot image + full .dat"
```

---

### Task 6: Fork — parameterize the BIOSEXEC entry gate; capture wrapper updates

**Files:**
- Modify: `../cleopatra/tools/flycast-src/core/hw/sh4/interpr/sh4_interpreter.cpp`
  (~line 26, `cartlog_bios_check`)
- Modify: `scripts/capture_leg.sh`
- Modify: `docs/kb/tooling.md`

**Interfaces:**
- Produces: env var `FLYCAST_ENTRYPC` (hex, no `0x` prefix needed) — the PC
  that arms the BIOSEXEC watch; default stays Cleopatra's `0x8c04ae2c`.
- Produces: `capture_leg.sh <leg> [rom-path]` — optional 2nd arg overrides
  the ROM (Task 7's `.dat` boot test, Task 12's patched `.dat`); leg names
  may contain `/` (e.g. `phase3/pc`).

- [ ] **Step 1: Edit the gate**

In `sh4_interpreter.cpp`, replace the hardcoded entry compare in
`cartlog_bios_check`:

```cpp
// Phase 3 (senkosp): the arming PC comes from FLYCAST_ENTRYPC (hex); default
// stays Cleopatra's trampoline so existing recipes are unchanged.
static u32 cartlog_entry_pc;
static void cartlog_bios_check(u32 pc)
{
	if (cartlog_entry_pc == 0) {
		const char *e = getenv("FLYCAST_ENTRYPC");
		cartlog_entry_pc = e ? (u32)strtoul(e, nullptr, 16) : 0x8c04ae2c;
	}
	if (pc == cartlog_entry_pc)
		cartlog_entry_seen = true;
	if (cartlog_entry_seen && (pc & 0x1fffffff) < 0x00200000)
	{
		static u32 last = 0xffffffff;
		if (pc != last) { last = pc; cartlog("BIOSEXEC pc=%08x\n", pc); }
	}
}
```

(`getenv`/`strtoul` — add `#include <cstdlib>` at the top if not already
present.)

- [ ] **Step 2: Rebuild**

```bash
cd ../cleopatra/tools/flycast-src/build && make -j8
```

Expected: `Flycast.app/Contents/MacOS/Flycast` relinked, exit 0. (Recipe:
`../cleopatra/docs/kb/tooling.md` §Flycast source build.)

- [ ] **Step 3: Commit + push the fork change**

```bash
cd ../cleopatra/tools/flycast-src
git add core/hw/sh4/interpr/sh4_interpreter.cpp
git commit -m "cartlog: FLYCAST_ENTRYPC parameterizes the BIOSEXEC arming PC (senkosp phase 3)"
git push origin HEAD
```

- [ ] **Step 4: Update `capture_leg.sh`**

Apply these changes (the rest of the script is untouched):

```bash
rom="${2:-$repo/roms/senkosp.zip}"          # was: rom="$repo/roms/senkosp.zip"
log="$repo/captures/$leg.log"
mkdir -p "$(dirname "$log")"                 # was: mkdir -p "$repo/captures" — allows phase3/ legs
...
# senkosp entry arms the BIOSEXEC watch; an exported override wins (canary use)
FLYCAST_ENTRYPC="${FLYCAST_ENTRYPC:-8c021000}" FLYCAST_CARTLOG="$log" \
    exec "$bin" -config config:rend.vsync=no "$rom"
```

Also update the usage line to `capture_leg.sh <leg-name> [rom-path]`.

- [ ] **Step 5: Canary — prove the gate actually fires**

Instrument control test (playbook: control-test the instrument, not just the
silence). BIOSEXEC only fires under the interpreter: edit
`~/Library/Application Support/Flycast/emu.cfg` → `Dynarec.Enabled = no`.

Positive canary — arm at the BIOS reset vector so BIOS execution itself
logs:

```bash
FLYCAST_ENTRYPC=a0000000 scripts/capture_leg.sh canary-bios & sleep 60; pkill -9 -f "flycast-src.*Flycast"
grep -c BIOSEXEC captures/canary-bios.log   # expect: large nonzero
```

Negative canary — the real gate, expect silence during boot:

```bash
scripts/capture_leg.sh canary-entry & sleep 90; pkill -9 -f "flycast-src.*Flycast"
grep -c BIOSEXEC captures/canary-entry.log   # expect: 0
```

Restore `Dynarec.Enabled = yes`. Delete both canary logs
(`rm captures/canary-*.log` — the only deletable log class).

- [ ] **Step 6: Record + commit (this repo)**

`docs/kb/tooling.md`: new §Phase 3 — fork commit hash from Step 3, the
build-tree note (tree = `f014a410c` + 12 additive cartlog-watch commits +
this one; Phase 2's cited `f014a410c` lines are all present — the extras
are additive watches like `SOFWR`), `FLYCAST_ENTRYPC` usage, canary results,
interpreter toggle recipe (emu.cfg path + line).

```bash
git add scripts/capture_leg.sh docs/kb/tooling.md
git commit -m "Phase 3: capture wrapper — ROM override + FLYCAST_ENTRYPC; fork gate recorded"
```

---

### Task 7: Control test — does the flat `.dat` boot?

**Files:**
- Create: `captures/datboot.log` (gitignored evidence)
- Modify: `docs/kb/tooling.md` (verdict)

**Interfaces:**
- Produces: the **dry-run vehicle decision**. PASS → Tasks 11–12 patch and
  run `senkosp-reloc.dat` directly. FAIL → STOP; the fallback (a
  `FLYCAST_PATCHSET` load-time in-memory patch hook in the fork — env names
  a file of `offset old new` u32 triples applied to the DIMM buffer after
  cart load, equivalent bytes-wise to patching the `.dat`) must be designed
  as a task upgrade before Tasks 11–12 proceed. Do not improvise it inline.

- [ ] **Step 1: Boot the unpatched `.dat` (dynarec on)**

```bash
scripts/capture_leg.sh datboot "$PWD/senkosp.dat" & sleep 120; pkill -9 -f "flycast-src.*Flycast"
```

- [ ] **Step 2: Compare against the known-good zip boot**

```bash
grep -c CARTDMA captures/datboot.log
head -5 <(grep "^CARTDMA" captures/datboot.log)
head -5 <(grep "^CARTDMA" captures/attract.log)
```

Expected: nonzero DMA count and the first CARTDMA tuples byte-identical to
the Phase 2 zip-boot attract leg (same src/dest/len sequence). Also confirm
the game visually reaches the title/attract screen during the 120 s window
(operator observation — record it).

- [ ] **Step 3: Record the verdict**

`docs/kb/tooling.md` §Phase 3: ".dat boots identically: yes/no + evidence
(first-tuple comparison, operator observation)". On **no**: STOP, per the
Interfaces block — surface to the user with the fallback design; that is a
scope upgrade, not a silent detour.

- [ ] **Step 4: Commit**

```bash
git add docs/kb/tooling.md
git commit -m "Phase 3: flat-.dat boot control test — verdict recorded"
```

---

### Task 8: Parser — PC lines, PC checks, PC report (TDD)

**Files:**
- Modify: `scripts/parse_cartlog.py`
- Modify: `scripts/test_parse_cartlog.py`

**Interfaces:**
- Consumes: candidate ranges from `boot-binary.md` (Tasks 2, 4) — as CLI
  values, not imports.
- Produces CLI: `--cart-fn LO-HI[,LO-HI]`, `--input-fn LO-HI[,LO-HI]`,
  `--eeprom-fn LO-HI[,LO-HI]`, `--stack LO-HI` (all P1 hex, no `0x`); PC
  checks run **only when the matching flag is given** (Phase 2 re-parses
  stay untouched); `--pc-report` prints `PCPAIR dest=%08x pc=%08x sp=%08x`
  per DMA for Task 10's corridor→PC join.
- Produces checks: `no_bios_exec` (always on), `dma_pc_in_cart_fn`,
  `input_pc_in_input_fn`, `eeprom_read_seen` (sub 01/03),
  `eeprom_write_seen` (sub 0b), `sp_consistent`.
- Reference port source: `../cleopatra/scripts/parse_cart_log.py:130`
  (`_pc_checks`) — same shape, with the eeprom check split in two and
  `sp_consistent` testing against `--stack` when given (else the 1 MB-spread
  heuristic).

- [ ] **Step 1: Write the failing tests**

Append to `scripts/test_parse_cartlog.py` (same assert style; new synthetic
leg + assertions — adjust names to the module's actual test-runner shape
when editing):

```python
PCLEG = """\
CARTDMA src=00200000 dest=0dfe0000 len=7520
CARTDMAPC pc=8c03bd28 sp=8cffff00
CARTDMA src=00300000 dest=0d244c20 len=100
CARTDMAPC pc=8c03bd30 sp=8cfffef0
MAPLEPC cmd=86 sub=15 pc=8c031600
MAPLEPC cmd=86 sub=01 pc=8c032000
MAPLEPC cmd=86 sub=0b pc=8c032100
"""

legs = [P.parse_leg("pc", PCLEG)]
cks = dict((n, ok) for n, ok, _ in P.pc_checks(
    legs,
    cart_fn=[(0x8C03BD00, 0x8C03BE00)],
    input_fn=[(0x8C031000, 0x8C031FFF)],
    eeprom_fn=[(0x8C032000, 0x8C032200)],
    stack=[(0x8CFF0000, 0x8D000000)]))
assert cks == {"no_bios_exec": True, "dma_pc_in_cart_fn": True,
               "input_pc_in_input_fn": True, "eeprom_read_seen": True,
               "eeprom_write_seen": True, "sp_consistent": True}, cks

# cart-fn range excluding 8c03bd30 -> dma_pc_in_cart_fn fails
cks = dict((n, ok) for n, ok, _ in P.pc_checks(
    legs, cart_fn=[(0x8C03BD00, 0x8C03BD28)], input_fn=None,
    eeprom_fn=None, stack=None))
assert cks["dma_pc_in_cart_fn"] is False

# a BIOSEXEC line fails no_bios_exec
bad = [P.parse_leg("pc", PCLEG + "BIOSEXEC pc=8c000100\n")]
cks = dict((n, ok) for n, ok, _ in P.pc_checks(bad, None, None, None, None))
assert cks["no_bios_exec"] is False

# SP outside the static stack region fails sp_consistent
cks = dict((n, ok) for n, ok, _ in P.pc_checks(
    legs, None, None, None, stack=[(0x8C000000, 0x8C100000)]))
assert cks["sp_consistent"] is False

# regression: Phase 2 fixtures (no PC lines) still parse identically —
# re-assert the existing ATTRACT/PLAY expectations after the change.
print("OK pc_checks self-check")
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `cd scripts && python3 test_parse_cartlog.py`
Expected: FAIL (unknown line types are skipped silently, so the failures
come from missing checks/flags — KeyError/AssertionError).

- [ ] **Step 3: Implement**

In `scripts/parse_cartlog.py`:

Regexes (with the existing regex block):

```python
_DMAPC = re.compile(r"^CARTDMAPC pc=([0-9a-f]+) sp=([0-9a-f]+)", re.I)
_MPC = re.compile(r"^MAPLEPC cmd=86 sub=([0-9a-f]+) pc=([0-9a-f]+)", re.I)
_BIOS = re.compile(r"^BIOSEXEC pc=([0-9a-f]+)", re.I)
```

`parse_leg`: add keys `"dmapc": []` (tuples `(pc, sp)`; also attach to the
preceding CARTDMA as `(src, dest, len, pc, sp)` in a parallel
`"pcpairs": []` list — CARTDMAPC immediately follows its CARTDMA,
`naomi.cpp:468–470`), `"maplepc": []` (`(sub, pc)`), `"biosexec": []`.

Checks — new function, called from `checks()` and appended to the same
list; ranges parsed from the new argparse flags
(`ap.add_argument("--cart-fn")` etc., value `LO-HI[,LO-HI]`, parsed with a
small `_ranges()` helper):

```python
def _in(ranges, pc):
    return any(lo <= pc <= hi for lo, hi in ranges)

def pc_checks(legs, cart_fn, input_fn, eeprom_fn, stack):
    out = []
    bios = [p for l in legs for p in l["biosexec"]]
    out.append(("no_bios_exec", not bios,
                f"{len(bios)} BIOSEXEC lines (expect 0)"))
    dmapc = [p for l in legs for p, _ in l["dmapc"]]
    if cart_fn:
        out.append(("dma_pc_in_cart_fn", all(_in(cart_fn, p) for p in dmapc),
                    f"{len(dmapc)} DMA-kick PCs vs cart fn"))
    if input_fn:
        pcs = [p for l in legs for s, p in l["maplepc"] if s == 0x15]
        out.append(("input_pc_in_input_fn", bool(pcs) and all(_in(input_fn, p) for p in pcs),
                    f"{len(pcs)} sub=15 PCs vs input fn"))
    if eeprom_fn:
        rd = [p for l in legs for s, p in l["maplepc"] if s in (0x01, 0x03)]
        wr = [p for l in legs for s, p in l["maplepc"] if s == 0x0b]
        out.append(("eeprom_read_seen", bool(rd) and all(_in(eeprom_fn, p) for p in rd),
                    f"{len(rd)} sub=01/03 PCs vs eeprom fn"))
        out.append(("eeprom_write_seen", bool(wr) and all(_in(eeprom_fn, p) for p in wr),
                    f"{len(wr)} sub=0b PCs vs eeprom fn"))
    sps = [sp for l in legs for _, sp in l["dmapc"]]
    if sps:
        if stack:
            ok = all(_in(stack, sp) for sp in sps)
            det = f"{len(sps)} SPs vs static stack region"
        else:
            ok = max(sps) - min(sps) < 0x100000
            det = f"SP spread {max(sps) - min(sps):#x} (< 1 MB heuristic)"
        out.append(("sp_consistent", ok, det))
    return out
```

`--pc-report`: print `PCPAIR dest=%08x pc=%08x sp=%08x` from the merged
`pcpairs`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scripts && python3 test_parse_cartlog.py`
Expected: exit 0, all asserts pass (old + new).

- [ ] **Step 5: Phase 2 regression — full re-parse unchanged**

```bash
python3 scripts/parse_cartlog.py captures/*.log --attract-leg attract --hw-report > /tmp/p2-regress.txt; echo "exit=$?"
```

Expected: `exit=0`, all six Phase 2 CHECKs PASS (`captures/*.log` still
matches only the 14 Phase 2 legs — Phase 3 legs live in `captures/phase3/`;
`datboot.log` DOES match the glob, so pass the 14 legs explicitly if
`datboot` skews the merge — the tuples are a subset of attract's so the
merged map should be unchanged; verify the CHECK lines say PASS and the
high-water is still `0x1fe7520`).

- [ ] **Step 6: Commit**

```bash
git add scripts/parse_cartlog.py scripts/test_parse_cartlog.py
git commit -m "Phase 3: parser PC layer — CARTDMAPC/MAPLEPC/BIOSEXEC, five PC checks, --pc-report"
```

---

### Task 9: PC-capture leg (interpreter) + static/dynamic reconciliation

**Files:**
- Create: `captures/phase3/pc.log` (gitignored evidence)
- Modify: `docs/kb/boot-binary.md` (dynamic evidence per target)

**Interfaces:**
- Consumes: candidate ranges (`boot-binary.md` §Candidates), stack region
  (Task 2), parser flags (Task 8).
- Produces: **confirmed** function ranges (candidates promoted by dynamic
  proof) — Task 10 slices from these PCs; Task 13 cites them.

- [ ] **Step 1: Interpreter on**

`~/Library/Application Support/Flycast/emu.cfg`: `Dynarec.Enabled = no`.

- [ ] **Step 2: Capture the leg (operator at the controls)**

```bash
scripts/capture_leg.sh phase3/pc
```

Operator script (interpreter is ~10× slow — expect 15–25 min wall):
boot → attract through ≥1 demo cycle → coin (A) → start → one match with
all five buttons + stick exercised → Test menu (T) → flip Advertise Sound
OFF → exit → re-enter → restore ON (the Phase 2-proven EEPROM write
sequence) → quit Flycast.

- [ ] **Step 3: Parse with the ranges**

```bash
python3 scripts/parse_cartlog.py captures/phase3/pc.log \
    --cart-fn <LO-HI from boot-binary.md> \
    --input-fn <LO-HI> --eeprom-fn <LO-HI> \
    --stack <LO-HI from Task 2> --pc-report > tools/pc-parse.txt; echo "exit=$?"
```

Expected: `exit=0`; `no_bios_exec`, `dma_pc_in_cart_fn`,
`input_pc_in_input_fn`, `eeprom_read_seen`, `eeprom_write_seen`,
`sp_consistent` all PASS.

**Any FAIL = stop-and-debug** (superpowers:systematic-debugging): either
the static candidate is wrong (wrong function among the xref hits — check
the logged PCs with `WhichFunc.java`, adapt its `ADDRS` list to the actual
PCs, re-derive the range) or the dynamic data is suspect. Resolve before
proceeding; record which side was wrong and why in `boot-binary.md`.

- [ ] **Step 4: Interpreter off**

Restore `Dynarec.Enabled = yes`.

- [ ] **Step 5: Record dynamic evidence**

`boot-binary.md`: per target — cart-read fn (range + example PCs), input fn
(sub=15 PCs), EEPROM fn (read + write PCs), SP (logged range vs static),
BIOS verdict dynamic half (`no_bios_exec` PASS on this leg; cite the check
line). Also note the `SOFWR` lines present in this log (FB writes with
pc/pr) — Task 10 input.

- [ ] **Step 6: Commit**

```bash
git add docs/kb/boot-binary.md
git commit -m "Phase 3: PC-capture leg — five targets dynamically confirmed, candidates promoted"
```

---

### Task 10: Provenance analysis → `relocation-map.md` + patch set

This is the phase's center and its open-ended task: analysis, not
mechanical execution. The steps below are the procedure; the honest exit is
either a complete patch set or a documented blocker surfaced to the user —
never a guessed patch.

**Files:**
- Create: `docs/kb/relocation-map.md`
- Create: `scripts/reloc_patchset.json`
- Modify: `scripts/ghidra/WhichFunc.java`, `scripts/ghidra/Decomp.java`
  (address lists → the real PCs/functions under analysis, iteratively)

**Interfaces:**
- Consumes: `PCPAIR` report (Task 8/9), `PLACE`/`DATHIT` candidates
  (Task 5), `SOFWR` PCs (Task 9 log and any Phase 2 log), stack region +
  below-16m occupancy (Task 2, Phase 2 `MAINHIST`).
- Produces: `scripts/reloc_patchset.json` — a JSON array of
  `{"dat_offset": "0x...", "old": "0x...", "new": "0x...", "why": "..."}`
  (u32 LE words; for boot-image code/pool sites `dat_offset` =
  P1 address − `0x8c020000`; for streamed tables, the table's own `.dat`
  offset). Tasks 11–12 consume this schema exactly.
- Produces: `docs/kb/relocation-map.md` — provenance per corridor + VRAM/FB,
  the below-cap free-space layout, the patch-set rationale. Phase 4's direct
  input.

- [ ] **Step 1: Corridor → PC → dest source, one corridor at a time**

For each of the 5 corridors: filter `PCPAIR` lines whose dest falls in the
corridor; map the PCs with `WhichFunc.java` (adapt `ADDRS`); `Decomp.java`
the containing function(s); walk the decompiled source of the dest value
backward — pool constant, memory load from a table (find the table:
match against `PLACE`/`DATHIT` hits), or arithmetic. Classify each corridor:
`pool-constant` / `table` / `computed`, with addresses. Name span 4's hot
ring's owner function while there (the 1,263-request 252 KB ring,
`cart-streaming-map.md`).

**Contingency (spec §Static-analysis harness):** if a kick PC lies outside
the boot image (code streamed in later — the imported program covers only
`0x8c020000`–`0x8c191ff7`), extend the static image from an emulator RAM
snapshot at a known moment (`FLYCAST_ARAMDUMP`-style dump or a Flycast
savestate carve) and import it as a second program; record the exact steps
in `tooling.md`. Evidence-driven — do not build it preemptively.

- [ ] **Step 2: VRAM/FB provenance**

FB: take `SOFWR ... pc= pr=` lines (Task 9 log; also present in Phase 2
logs), map pc/pr with `WhichFunc.java`, `Decomp.java` the writer — find
where the SOF values come from (Ninja2 display init — expect a base
constant or config struct). Textures: from the `vram64`/`vram32` `PLACE`
hits, decompile the consuming function(s); verify the Ninja2-allocator
hypothesis (one base/table feeding both uploads and TCW references — spec
target 3b). **If static analysis cannot pin the texture-allocation source**,
stop and surface it: the contingency (a VRAM-write-PC watch in the fork) is
a scope decision for the user, not an inline improvisation.

- [ ] **Step 3: Choose relocation targets (the free-space layout)**

Below-16m main free map: 16 MB minus boot image (`0x20000`–`0x191ff8`),
minus Phase 2's measured below-16m occupancy (`MAINHIST` buckets < #64),
minus the stack region (Task 2). Slot the 5 corridors (11.64 MB total,
keep each span contiguous; preserve relative alignment of each base —
same low bits — so any alignment assumption in the game survives). VRAM:
below-8m free map from Phase 2 `VRAMHIST`/FB sizes; slot the ~4.96 MB
content + FB targets. Record the layout table in `relocation-map.md`.

- [ ] **Step 4: Write the patch set**

Every provenance site → one JSON entry with `why` naming its corridor/role.
Cross-check: the entries must cover **all five** corridors + VRAM/FB, or
the gap is documented as a blocker (see task exit note above).

- [ ] **Step 5: Write `relocation-map.md` + commit**

Sections: §Provenance (per corridor + VRAM/FB, evidence-cited), §Free-space
layout, §Patch set (the JSON, explained), §Dry-run evidence (placeholder
filled by Task 12 — mark it "pending Task 12", the one permitted
forward-reference).

```bash
git add docs/kb/relocation-map.md scripts/reloc_patchset.json
git commit -m "Phase 3: placement provenance + relocation patch set (target 3)"
```

---

### Task 11: Patch applier + dry-run parser checks (TDD)

**Files:**
- Create: `scripts/apply_reloc.py`
- Create: `scripts/test_apply_reloc.py`
- Modify: `scripts/parse_cartlog.py`, `scripts/test_parse_cartlog.py`
  (dry-run checks)

**Interfaces:**
- Consumes: `scripts/reloc_patchset.json` (Task 10 schema).
- Produces: `apply_reloc.py IMAGE PATCHSET -o OUT` (refuses on old-value
  mismatch); parser flag `--dryrun ANCHOR.log` adding checks
  `dryrun_main_below_16m`, `dryrun_vram_below_8m`, `dryrun_stream_shape`.

- [ ] **Step 1: Failing test for the applier**

`scripts/test_apply_reloc.py`:

```python
#!/usr/bin/env python3
"""Self-check for apply_reloc.py — synthetic image, one patch, one mismatch."""
import struct

import apply_reloc as A

img = struct.pack("<4I", 0x11111111, 0x8d244c20, 0x33333333, 0x44444444)
patches = [{"dat_offset": "0x4", "old": "0x8d244c20", "new": "0x8c400000", "why": "test"}]
out = A.apply(img, patches)
assert struct.unpack("<4I", out) == (0x11111111, 0x8c400000, 0x33333333, 0x44444444)

try:
    A.apply(img, [{"dat_offset": "0x8", "old": "0xdeadbeef", "new": "0x0", "why": "bad"}])
    raise SystemExit("FAIL: mismatch not detected")
except ValueError:
    pass
print("OK apply_reloc self-check")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd scripts && python3 test_apply_reloc.py`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `scripts/apply_reloc.py`**

```python
#!/usr/bin/env python3
"""Apply the Phase 3 relocation patch set to a flat Naomi image.
Each entry must match its expected old value or the run refuses (a moved
base or a stale patchset must never half-patch an image).

Usage: apply_reloc.py senkosp.dat scripts/reloc_patchset.json -o senkosp-reloc.dat
Patchset: JSON array of {"dat_offset": "0x..", "old": "0x..", "new": "0x..", "why": ".."}
"""
import argparse
import json
import struct
import sys


def apply(image, patches):
    buf = bytearray(image)
    for p in patches:
        off = int(p["dat_offset"], 16)
        old = int(p["old"], 16)
        new = int(p["new"], 16)
        cur = struct.unpack_from("<I", buf, off)[0]
        if cur != old:
            raise ValueError(
                f"at 0x{off:x}: expected 0x{old:08x}, found 0x{cur:08x} ({p['why']})")
        struct.pack_into("<I", buf, off, new)
    return bytes(buf)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("patchset")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args(argv)
    with open(a.patchset) as f:
        patches = json.load(f)
    with open(a.image, "rb") as f:
        img = f.read()
    with open(a.out, "wb") as f:
        f.write(apply(img, patches))
    print(f"patched {len(patches)} words -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd scripts && python3 test_apply_reloc.py`
Expected: `OK apply_reloc self-check`.

- [ ] **Step 5: Failing tests for the dry-run checks**

Append to `scripts/test_parse_cartlog.py`: synthetic anchor leg + dry-run
leg pairs asserting:

1. `dryrun_main_below_16m` — PASS when every dest+len < `0x0d000000` phys
   (main offset < `0x1000000`) and last `MAINPROFILE high` < `0x1000000`;
   FAIL when a DMA lands above.
2. `dryrun_vram_below_8m` — PASS when last `VRAMPROFILE content_high` <
   `0x800000` AND every `VRAMREGS` `fb_w_sof1/fb_w_sof2/fb_r_sof1`
   (masked `& 0x00fffffc` — SOF regs carry low-bit flags) < `0x800000`;
   FAIL otherwise.
3. `dryrun_stream_shape` — PASS when the dry-run leg's `(src, len)`
   multiset equals the anchor leg's; FAIL with a count diff otherwise.

- [ ] **Step 6: Implement `--dryrun ANCHOR.log`**

New argparse flag; when given, parse the anchor log as an extra
(non-merged) leg and append the three checks above to the checks list, run
against the provided legs. Multiset comparison:
`collections.Counter((d["src"], d["len"]) for ...)` equality; on failure
print the first 5 differing tuples each way.

- [ ] **Step 7: Run tests, expect all pass; commit**

Run: `cd scripts && python3 test_parse_cartlog.py && python3 test_apply_reloc.py`
Expected: exit 0 both.

```bash
git add scripts/apply_reloc.py scripts/test_apply_reloc.py scripts/parse_cartlog.py scripts/test_parse_cartlog.py
git commit -m "Phase 3: patch applier + dry-run gate checks"
```

---

### Task 12: The relocation dry run

**Files:**
- Create: `senkosp-reloc.dat` (gitignored via `*.dat`, regenerable)
- Create: `captures/phase3/dryrun-attract.log`, `captures/phase3/dryrun-play.log`
- Modify: `docs/kb/relocation-map.md` (§Dry-run evidence)

**Interfaces:**
- Consumes: everything — the patched image, the wrapper's ROM override, the
  `--dryrun` checks, Phase 2's `captures/attract.log` as anchor.
- Produces: the phase's capstone verdict (spec exit criterion 3).

- [ ] **Step 1: Generate the patched image**

```bash
python3 scripts/apply_reloc.py senkosp.dat scripts/reloc_patchset.json -o senkosp-reloc.dat
```

Expected: `patched N words -> senkosp-reloc.dat`, N = patchset size.

- [ ] **Step 2: Dry-run attract leg (dynarec on, same duration as Phase 2)**

```bash
scripts/capture_leg.sh phase3/dryrun-attract "$PWD/senkosp-reloc.dat" & sleep 660; pkill -9 -f "flycast-src.*Flycast"
```

Operator: confirm visually the game reaches title + attract demos, same as
the Phase 2 boot verification.

- [ ] **Step 3: Dry-run play leg (operator)**

```bash
scripts/capture_leg.sh phase3/dryrun-play "$PWD/senkosp-reloc.dat"
```

Boot → coin → one full match, then quit. Operator records: playable
yes/no, anomalies (missing textures, wrong sprites, hangs, garbage audio).

- [ ] **Step 4: Gate checks**

```bash
python3 scripts/parse_cartlog.py captures/phase3/dryrun-attract.log captures/phase3/dryrun-play.log \
    --dryrun captures/attract.log > tools/dryrun-parse.txt; echo "exit=$?"
```

Expected: `exit=0`, `dryrun_main_below_16m` / `dryrun_vram_below_8m` /
`dryrun_stream_shape` all PASS. Note: `dryrun_stream_shape` compares the
attract-leg multiset — if capture-window truncation makes the multiset
differ while the unique `(src, len)` set matches, record the set-equality
result + the boundary explanation in relocation-map.md rather than forcing
a re-run loop; the spec's intent is "game logic undisturbed".

**On FAIL:** superpowers:systematic-debugging. Iterate the patch set
(Task 10's provenance was incomplete — a consumer still reads the old
address) and re-run from Step 1. **If the strategy is fundamentally
falsified** (computed addresses everywhere, no coherent patch set): write
the fallback decision per spec exit criterion 3 — shim-side streaming
retarget + consumer-read patching — into `relocation-map.md`, and surface
to the user before Task 13.

- [ ] **Step 5: Record + commit**

`relocation-map.md` §Dry-run evidence: the three CHECK lines, operator
playability report, watermark numbers, image hash
(`md5 senkosp-reloc.dat`).

```bash
git add docs/kb/relocation-map.md
git commit -m "Phase 3: relocation dry run — gate checks + operator evidence"
```

---

### Task 13: KB writeup, control layout, status advance, exit audit

**Files:**
- Modify: `docs/kb/boot-binary.md` (finalize — all nine targets answered)
- Modify: `docs/kb/input-map.md` (control layout)
- Modify: `docs/kb/tooling.md` (Ghidra project recipe, boot.bin hash, any
  step not yet recorded)
- Modify: `docs/kb/00-status.md` (Phase 3 done, Phase 4 next)

**Interfaces:**
- Consumes: everything above.
- Produces: the phase gate evidence, in the same shape Phase 2's gate used.

- [ ] **Step 1: Finalize `boot-binary.md`**

All nine target answers present, each with address range + static evidence
+ dynamic evidence (or "static-only by nature" for RTC/SCIF/watchdog) +
Phase 4 patch implication. Cross-reference `relocation-map.md` for target 3/4
rather than duplicating it.

- [ ] **Step 2: Control layout into `input-map.md`**

New section "DC pad layout (Phase 3, user-approved 2026-08-19)" — the
approved table verbatim from the spec §target 9, including the Coin
(free-play) and Test/Service (Phase 4 loader decision) notes.

- [ ] **Step 3: `tooling.md` sweep**

Verify recorded: Ghidra import recipe + project location, `boot.bin` slice
command + md5, fork commit + rebuild, interpreter toggle, `.dat`-boot
verdict, capture-wrapper changes. Add whatever's missing.

- [ ] **Step 4: Advance `00-status.md`**

Phase 3 checklist (mirroring the six spec exit criteria, each checked with
its evidence pointer), key facts updated (patch-set size, corridor
provenance classes, RTC/SCIF verdicts, SP verdict, dry-run headline), Next
step = Phase 4 conversion (brainstorm + spec first, per the playbook
cadence), listing Phase 4's direct inputs (`boot-binary.md`,
`relocation-map.md`, `reloc_patchset.json`, control layout).

- [ ] **Step 5: Exit-criteria audit**

Walk spec §Exit criteria 1–6 one by one; for each, name the evidence file +
check line. For criterion 4 specifically, prove it now: re-run
`scripts/ghidra/run.sh script FindMmioXrefs.java` and
`scripts/ghidra/run.sh script DumpEntryChain.java`, and diff the reported
addresses against `boot-binary.md` — they must reproduce. Any unmet
criterion → the phase is NOT done; go back to the owning task.
(superpowers:verification-before-completion — evidence before assertions.)

- [ ] **Step 6: Commit**

```bash
git add docs/kb/boot-binary.md docs/kb/input-map.md docs/kb/tooling.md docs/kb/00-status.md
git commit -m "Phase 3 complete: gate green — touchpoints proven, relocation strategy decided with dry-run evidence"
```

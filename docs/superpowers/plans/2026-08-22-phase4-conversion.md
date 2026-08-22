# Phase 4 — Conversion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Loader + freestanding shim + patch table → a GDI that boots
in Flycast's Dreamcast profile, runs attract, and is playable.

**Architecture:** Cleopatra's Phase 4 skeleton (KOS loader →
old-byte-verified patch table → register-mirror shim → donor-clone GDI)
copy-adapted to senkosp, with two forced novelties: a raw-ATA GD-ROM
driver (the Naomi RTOS-kernel placement at `0x8c000600` kills DC BIOS
syscalls at runtime) and a new 32 KB shim home at
`0x8c010000`–`0x8c018000`. Pins first, then skeleton, then incremental
bring-up with the HUD wired before the first boot.

**Tech Stack:** KOS (`../cleopatra/tools/kos/environ.sh`), sh-elf-gcc
freestanding shim, Python 3 stdlib scripts, Ghidra 12.1.2 headless
(`scripts/ghidra/run.sh`), instrumented Flycast fork
(`../flycast4naomi2dreamcast`, built at
`../cleopatra/tools/flycast-src/build/Flycast.app/Contents/MacOS/Flycast`).

**Spec:** `docs/superpowers/specs/2026-08-22-phase4-conversion-design.md`

## Global Constraints

- **Never commit ROM/BIOS-derived bytes** — `roms/`, `bios/`, `tools/`,
  `build/`, `captures/`, `senkosp*.dat` stay gitignored. Blobs are
  extracted at build time from the user's dumps.
- **Every hardware/behavioral claim in the KB carries a citation**;
  primary sources (Flycast/KOS source, the image itself) outrank wikis.
- **Record every tool install/change in `docs/kb/tooling.md`** (KOS env,
  fork commits, config toggles).
- **Branch:** all work on `phase4-conversion` (create from `main` at
  task 1, step 1). Commit per task minimum; more is fine.
- **Capture legs are primary data**: `scripts/capture_leg.sh` refuses to
  overwrite; never delete a non-canary log. Phase 4 legs live under
  `captures/phase4/`.
- **Flycast fork changes** are made in `../flycast4naomi2dreamcast`
  (source of truth), committed there with a senkosp-phase-4 message,
  rebuilt via `make -j8` in `../cleopatra/tools/flycast-src/build`
  (same reused binary path — see `docs/kb/tooling.md` §Phase 3 BIOSEXEC
  entry gate for the precedent).
- **Dynarec config**: interpreter-only probes require
  `Dynarec.Enabled = no` in
  `~/Library/Application Support/Flycast/emu.cfg` (line ~39); restore
  `= yes` after — later legs depend on it.
- **Kill pattern** (macOS has no `timeout`):
  `scripts/capture_leg.sh <leg> [content] & sleep <secs>; pkill -9 -f "flycast-src.*Flycast"`.
- **The spec's honest limit**: Flycast-DC green proves nothing about
  real hardware; make no hardware claims in this phase. (Phase 5 owns HW.)

## Shared reference — the debug-loop protocol (bring-up tasks 10–13)

When a boot attempt hangs or misbehaves, do NOT guess-patch. In order:

1. Invoke `superpowers:systematic-debugging`.
2. Read the screen: shim HUD breadcrumbs (`util.c`), `SHIM_ERR` block,
   loader `halt()` message. The breadcrumb names the stage.
3. Read the Flycast stdout log (`captures/phase4/<leg>.stdout.log`) and
   the cartlog (`FLYCAST_CARTLOG`) — MDODMA/PVRW/TAREG classes fire in
   DC mode too.
4. Control-test: boot the same GDI pipeline with Cleopatra's proven
   `build/disc.gdi` (or the Dolphin Blue donor) to split "my bytes"
   from "the process".
5. Only then add a targeted fork probe (commit in the fork repo) or a
   Ghidra decompile of the stuck PC.
6. Record the finding in `docs/kb/phase4-conversion.md` before fixing.

---

### Task 1: Fork probe — maple trigger tag + r15 water-mark (closes Phase 3 criterion 2)

**Files:**
- Modify: `../flycast4naomi2dreamcast/core/hw/maple/maple_if.cpp` (callers at ~:64, ~:95; `maple_DoDma` at ~:139)
- Modify: `../flycast4naomi2dreamcast/core/hw/naomi/cartlog.cpp` (log lines gain `trig=`; new `SPWATER` line)
- Modify: `scripts/parse_cartlog.py` (checks `input_pc_in_input_fn`, `eeprom_read_seen`, `eeprom_write_seen`, `sp_consistent` learn `trig=`)
- Test: `scripts/test_parse_cartlog.py` (extend)
- Modify: `docs/kb/boot-binary.md`, `docs/kb/00-status.md`, `docs/kb/tooling.md`

**Interfaces:**
- Consumes: fork build recipe (`docs/kb/tooling.md` §Instrumented Flycast); `scripts/capture_leg.sh`.
- Produces: capture log lines `... trig=reg` / `trig=vbl` on every maple transaction line; `SPWATER min=<hex> max=<hex>` per profile tick; the EEPROM-write call-site PC recorded in `boot-binary.md` §Target: EEPROM; Phase 3 checklist criterion 2 `[~]` → `[x]`.

- [ ] **Step 1: Create the branch**

```bash
cd /Users/captainkoffski/AntigravityProjects/senkosp2dreamcast
git checkout -b phase4-conversion
```

- [ ] **Step 2: Make the fork change.** In `maple_if.cpp`, add a file-static
`const char *maple_trig = "?";` and set it at the two `maple_DoDma()` call
sites: the `SB_MDST` register-write path (~line 64) → `"reg"`, the vblank
path (~line 95) → `"vbl"`. Thread `maple_trig` into every maple log line
this file / `cartlog.cpp` emits for the transaction (`MDODMA`, `MAPLEPC`,
`MIERESP`) as a trailing ` trig=%s`. For the water-mark: in the existing
per-event PC/SP capture path in `cartlog.cpp`, keep
`static uint32_t sp_min = ~0u, sp_max = 0;` updated from every sampled
`r15`, and emit `SPWATER min=%08x max=%08x` at the existing ~10 s profile
tick. Read the surrounding code first and match its idiom — these are
additive lines, not restructures.

- [ ] **Step 3: Build and commit the fork**

```bash
cd ../flycast4naomi2dreamcast && git add -A && git commit -m "cartlog: maple trig tag + SPWATER r15 water-mark (senkosp phase 4)"
cd ../cleopatra/tools/flycast-src/build && make -j8   # expect exit 0
```

- [ ] **Step 4: Re-run the PC leg** (interpreter ON for this leg per the
Phase 3 recipe — `Dynarec.Enabled = no`, restore after):

```bash
scripts/capture_leg.sh phase4/pc2 & sleep 300; pkill -9 -f "flycast-src.*Flycast"
```

Coverage: boot → attract; then repeat with an operator ~60 s test-menu
visit for the EEPROM-write events
(`scripts/capture_leg.sh phase4/pc2-testmenu`, operator enters test menu,
changes nothing, exits).

- [ ] **Step 5: Update the parser.** The three maple checks filter
`trig=reg` lines only (vblank-triggered transactions have no guest store
to attribute — Phase 3's finding); `sp_consistent` accepts the two-stack
model using `SPWATER` bounds: PASS iff `min` ≥ `0x8c1c0000` for the task
cluster and boot-cluster SPs stay in `[0x8c000000,0x8c00f000)`. Extend
`test_parse_cartlog.py` with a synthetic log fixture containing both
`trig=` values and an `SPWATER` line; run `cd scripts && python3
test_parse_cartlog.py` → `ok`.

- [ ] **Step 6: Re-run the parser on the new legs; verify the four checks PASS**

```bash
python3 scripts/parse_cartlog.py captures/phase4/pc2*.log --input-report
```

Expected: `input_pc_in_input_fn`, `eeprom_read_seen`, `eeprom_write_seen`,
`sp_consistent` all PASS, exit 0. The `trig=reg` EEPROM sub-`0x0b` lines
now carry a real PC — record it.

- [ ] **Step 7: Update docs.** `boot-binary.md`: EEPROM write call site
named (§Target: EEPROM), §Why three checks cannot pass as written gets a
dated closure note; second stack extent bounded by measured `SPWATER`.
`00-status.md`: Phase 3 checklist criterion 2 `[~]` → `[x]` with the new
evidence line. `tooling.md`: fork commit hash + leg inventory.

- [ ] **Step 8: Commit**

```bash
git add scripts/ docs/ && git commit -m "phase4: fork trig tag + SPWATER close Phase 3 criterion 2; EEPROM write site named"
```

---

### Task 2: Shim-home write-watch (spec O1) — prove `0x8c010000`–`0x8c018000` clean

**Files:**
- Modify: `../flycast4naomi2dreamcast/core/hw/naomi/naomi.cpp` (`cartlog_shimwatch` senkosp window)
- Modify: `scripts/parse_cartlog.py` (+ check `shim_home_clean`)
- Test: `scripts/test_parse_cartlog.py`
- Create: `docs/kb/phase4-conversion.md` (new KB doc; §V2-senkosp section)

**Interfaces:**
- Consumes: `tools/ram-snapshot.bin` (regenerable, `tooling.md` §Phase 3 RAM snapshot); Cleopatra V2 method (`../cleopatra/docs/kb/phase4-conversion.md` §V2).
- Produces: verdict **shim home clean / dirty** in `docs/kb/phase4-conversion.md` §Shim home (V2s). Every later task assumes clean; if dirty, STOP — the fallback (heap-top carve + dry-run re-campaign) is a spec change, surface it to the user before proceeding.

- [ ] **Step 1: Free pre-check from the existing RAM snapshot** (no new run):

```bash
python3 - <<'EOF'
ram = open("tools/ram-snapshot.bin","rb").read()
window = ram[0x10000:0x18000]
nz = [(i+0x10000) for i,b in enumerate(window) if b]
print("non-zero bytes:", len(nz), "first:", [hex(a) for a in nz[:8]])
EOF
```

If non-zero bytes exist, decode what wrote them before proceeding (Ghidra
on the snapshot program `senkosp3ram`); a boot-time Naomi-BIOS artifact
that senkosp never reads is acceptable (the DC loader owns boot), a
game-runtime structure is a STOP.

- [ ] **Step 2: Fork change.** In `naomi.cpp`, alongside the existing
Cleopatra `cartlog_shimwatch()`, add a senkosp window over `mem_b` offsets
`0x00010000`–`0x00017fff`, sampled at the same every-64th-cart-DMA cadence.
**Baseline-and-compare, not non-zero** (the Naomi BIOS may legitimately
write low RAM at boot, which the DC loader replaces): snapshot the window
at the first sample, emit `SHIMWATCH2 addr=<hex> was=<b> now=<b>` for any
byte differing from baseline on later samples. Content scan, not a write
hook — the arm64 dynarec bypasses C-level write functions (V2's
documented reason). Commit in the fork; rebuild.

- [ ] **Step 3: Parser check.** `shim_home_clean`: PASS iff zero
`SHIMWATCH2` lines. Fixture + `python3 test_parse_cartlog.py` → `ok`.

- [ ] **Step 4: Campaign leg** (dynarec ON, unattended attract + one
operator match + one test-menu visit — the three behaviorally distinct
regimes):

```bash
scripts/capture_leg.sh phase4/shimwatch & sleep 660; pkill -9 -f "flycast-src.*Flycast"
scripts/capture_leg.sh phase4/shimwatch-play   # operator plays a full match, then test menu, then quit
python3 scripts/parse_cartlog.py captures/phase4/shimwatch*.log
```

Expected: `CHECK shim_home_clean: PASS`, exit 0.

- [ ] **Step 5: Record the verdict** in `docs/kb/phase4-conversion.md`
(new file, header modeled on Cleopatra's: analysis results feeding the
patches, every bound cited). Include the sampling caveat verbatim from
V2 (a write fully reverted between samples evades the scan).

- [ ] **Step 6: Commit**

```bash
git add docs/kb/phase4-conversion.md scripts/ && git commit -m "phase4: shim home 0x8c010000-0x8c018000 write-watch verdict (O1)"
```

---

### Task 3: Ghidra pins — cart path (spec P1, P2, P3)

**Files:**
- Modify: `docs/kb/phase4-conversion.md` (+§cart-patch-sites)
- Use: `scripts/ghidra/run.sh` + existing `WhichFunc.java`, `DisasmRange.java`, `Decomp.java`, `FindMmioXrefs.java` on program `senkosp3`

**Interfaces:**
- Consumes: `boot-binary.md` §Target: cart-read function, §Candidates (the un-promotion note names every known site); `tools/boot.bin`.
- Produces: §cart-patch-sites — the complete cart/G1 patch list: for each entry `dat_offset`, old u32, kind (pool/ptr/hook), what it repoints/hooks, citation. Named anchors Task 9 consumes: **CART-BASE** (steady-path base provenance), **CART-WAIT** (completion-wait hook site), **CART-PIO** (`FUN_8c027d7e` ABI: args in/out), **CART-BOOT-POOLS** (boot-driver + wrapper pool words), **G1-TIMING** (bus-timing literals in `FUN_8c066288`).

- [ ] **Step 1: CART-BASE.** The steady kick `0x8c027f72` reaches
`SB_GDST` through a struct base (Phase 3). Decompile the chain:

```bash
scripts/ghidra/run.sh Decomp.java 0x8c027f54 0x8c027a66 0x8c02751a
```

Trace where the struct's register-base field is initialized. Known
candidate: `FUN_8c02751a` returns the constant `DAT_8c0275e8` =
`0xa05f7000` (`boot-binary.md` §Candidates, "MMIO sites deliberately
outside the ranges"). Find every store of that constant (or of
`FUN_8c02751a`'s result) into the struct; the goal is **one pool/data
word whose rewrite makes the whole steady path base-relative to the
mirror** — the analog of Cleopatra's `0x8c02da74`. Cross-check with
`FindMmioXrefs.java` output (`tools/mmio-xrefs.txt`): every `0xa05f70xx`
xref must be either covered by the base repoint or listed as its own
patch entry. Record the verdict with instruction quotes.

- [ ] **Step 2: CART-WAIT.** Find how the game observes DMA completion
on the steady path: disassemble forward from the kick
(`scripts/ghidra/run.sh DisasmRange.java 0x8c027f54 0x8c028020`) and
`Decomp.java` the caller(s) of `FUN_8c027f54` (from the Ghidra xrefs).
Expected: a poll of `SB_GDST` (base-relative → lands in the mirror) or
of `SB_GDLEND`. Decide and record the hook site: prefer entry-hooking
the smallest function whose contract is "wait until this DMA is done"
(Cleopatra hooked `FUN_8c03bc12`, its V3). Also record the three
boot-path wrappers that spin on `SB_GDST`
(`FUN_8c0678c2`/`FUN_8c0679b4`/`FUN_8c067b48`) and whether their pools
(`0x8c067970`, `0x8c067adc`, `0x8c067c44`, `0x8c067e14`) are covered by
mirror repoints (each holds `0xa05f7418` → repoint to
`G1_MIRROR_P2 + 0x418`).

- [ ] **Step 3: CART-PIO.** `Decomp.java 0x8c027d7e` + its callers:
record the ABI (where offset/len/dest arrive — registers or struct
fields), so the entry hook can service it. The Phase 2 map shows exactly
2 PIO seeks, boot-time.

- [ ] **Step 4: CART-BOOT-POOLS + G1-TIMING.** From
`boot-binary.md` §Candidates: the boot cart driver's pool words at
`0x8c066534`–`0x8c06655c` (SB_GDSTAR/GDLEN/GDDIR, NAOMI_ROM_OFFSETH/L,
NAOMI_ROM_DATA, NAOMI_DMA_OFFSETL/COUNT, NAOMI_DMA_OFFSETH at the arm
fn) and `FUN_8c066288`'s bus-timing targets (SB_GDAPRO, SB_G1RRC/G1RWC,
SB_G1CRC, SB_G1GDWC — `0xa05f74xx`). Read each pool word's value from
`tools/boot.bin` (offset = addr − `0x8c020000`), list every entry as
`pool(dat_offset, old=0xa05f7xxx, new=G1_MIRROR_P2 + (old & 0x7ff))`.
The mirror block spans fake `0x5f7000`–`0x5f77ff`, so `+0x4b8` etc. fit.
Also cover `0x8c066a88` (the `NAOMI_DMA_OFFSETH` write inside the maple
init — it must go to the G1 mirror too).

- [ ] **Step 5: Test-image pass.** The test image
(`.dat 0x171ff8`+`0x4dc40`) is a different binary. Repeat the pool-word
inventory for it: scan the test-image bytes for the same `0xa05f7xxx` /
`0xa05f6cxx` constants —

```bash
python3 scripts/scan_dat_constants.py senkosp.dat --range 0x171ff8:0x1bfc38 --words a05f7000-a05f77ff,a05f6c00-a05f6cff
```

(extend `scan_dat_constants.py` if its CLI lacks a range/word-list mode —
it already scans the `.dat` for u32 constants; keep the extension
minimal and covered by `test_scan_dat_constants.py`). Every hit gets a
test-tagged patch entry or a written exemption.

- [ ] **Step 6: Commit**

```bash
git add docs/kb/phase4-conversion.md scripts/ && git commit -m "phase4: cart-patch-sites pinned (CART-BASE/WAIT/PIO, boot pools, G1 timing, test image)"
```

---

### Task 4: Ghidra pins — maple path (spec P4) + input ABI

**Files:**
- Modify: `docs/kb/phase4-conversion.md` (+§maple-patch-sites, +§input-ABI)

**Interfaces:**
- Consumes: `boot-binary.md` §Target: input function, §Candidates (boot maple driver `FUN_8c066964`/`FUN_8c0665fe` with five `SB_MDST` stores), §`MDODMA`; Task 1's `trig=reg` attribution.
- Produces: anchors Task 9/11/12 consume: **MAPLE-BASE** (the steady struct-field store from `FUN_8c026b30` and who reads it), **MAPLE-KICK-HOOK** (steady service hook site at/around `0x8c025446`), **MAPLE-BOOT-STRATEGY** (per boot-driver kick: pool repoints + chosen hook sites), **MIE-DESC** (the maple descriptor/frame layout the game programs: where dest/recv addresses and the MIE frame live relative to `SB_MDSTAR`), **TESTBIT-INJECT** (where the synthesized JVS word carries Test bit 18 / Service `0x4000`).

- [ ] **Step 1: MAPLE-BASE.** `Decomp.java 0x8c026b30` + xrefs to the
struct field it stores `0xa05f6c00` into; confirm the steady engine
(`FUN_8c02532a`) loads its base from that field. Record the single
pool/data word to repoint (the analog of Cleopatra's `0x8c030fec`), or
the full set if there are several.

- [ ] **Step 2: MAPLE-KICK-HOOK.** Disassemble
`0x8c025420`–`0x8c025480` (`DisasmRange.java`); the kick is
`mov.l r12,@(0x18,r2)` at `0x8c025446`. Decide the hook: replace the
kick + adjacent completion poll with a call into `shim_maple_service`
(6-byte thunk needs contiguous replaceable instructions — quote the
exact instruction bytes and what the thunk clobbers; the hook kind in
Task 9's generator handles save/restore).

- [ ] **Step 3: MIE-DESC.** From the same decompile plus the Phase 2/3
`MDODMA` lines: record the descriptor layout the game writes to
`SB_MDSTAR` (command-table address), the per-frame MIE frame format
(sub `0x33` receive-then-transmit), and where the recv address lives.
This is the contract `shim_maple_service` implements. Verify against
Flycast's `maple_if.cpp` descriptor walk (primary source, cite lines).

- [ ] **Step 4: MAPLE-BOOT-STRATEGY.** For the five boot-driver kicks
(`0x8c066726` ×1023-in-leg, `0x8c066810`, `0x8c0668a2`, `0x8c066926`,
`0x8c066a5e`): their register pools are absolute (`0xa05f6c04/10/14/18/
80/8c`). List each pool word (value from `boot.bin`) →
`MAPLE_MIRROR_P2 + (old & 0xff)` repoint, and decide the service point:
the driver polls `SB_MDST` to zero after each kick, so either (a)
entry-hook `FUN_8c066964` and `FUN_8c0665fe` and reimplement their
contract in the shim, or (b) hook the innermost kick+poll helper if one
exists. Choose the option with the fewest reimplemented semantics;
record the decision and the exact sites. Repeat the constant scan for
the test image (Task 3 step 5 already lists `0xa05f6cxx` hits there).

- [ ] **Step 5: TESTBIT-INJECT.** Confirm from the decompile where the
JVS digital word lands in the recv buffer (`input-ABI`: senkosp
equivalent of Cleopatra's BTN_OFF/checksum offsets) so the shim can set
bits 18/19 and `0x4000`. Record P1/P2 slot offsets and the checksum rule.

- [ ] **Step 6: Commit**

```bash
git add docs/kb/phase4-conversion.md && git commit -m "phase4: maple-patch-sites + input-ABI pinned (base, hooks, MIE descriptor, boot strategy)"
```

---

### Task 5: Pins — restart stub in both images (P5), kernel slice (P6), blob sanity

**Files:**
- Modify: `docs/kb/phase4-conversion.md` (+§restart, +§low-RAM placements)

**Interfaces:**
- Consumes: `relocation-map.md` §Deliberately not patched (reset stub `FUN_8c067e18`: copies `0x60c` B from `0x8c180904`, jumps via pools `0x8c067e3c`/`0x8c067e4c`); `tools/ram-snapshot.bin`; `bios/naomi/epr-21576h.ic27`.
- Produces: **RESET-PATCH** (dat_offsets + old/new words for both images), **KERNEL-SLICE** (`KERNEL_ROM_OFF`, `KERNEL_LEN`, `KERNEL_DST=0x8c000600`, byte-verified), **BLOB-CHECK** (the 8 vector words at BIOS ROM `0x60000` verified `(w & 0x0fff0000) == 0x0c010000`).

- [ ] **Step 1: RESET-PATCH.** The stub's escape is the jump target pool
words: `0x8c067e4c` (value `0x8dfff000` — where the copied stub runs)
and the BIOS targets inside the copied page (`0xa0082262`, `0xa01935ec`,
`0xa0039310`, within the `0x60c` B source at `0x8c180904`). The lazy
correct patch: **replace the first jump-target pool word
(`dat 0x47e4c`, old `0x8dfff000`) with the address of a shim reboot
routine** — the stub then "restarts" by entering the shim instead of
copying itself high; the shim routine does the DC reboot (Task 10 code).
Verify the old value in `senkosp.dat` at `0x47e4c`; find the same stub
in the test image:

```bash
python3 - <<'EOF'
d = open("senkosp.dat","rb").read()
needle = d[0x47e18:0x47e58]           # stub head, main image
i = d.find(needle, 0x171ff8, 0x1bfc38)
print("test-image stub at .dat", hex(i) if i >= 0 else "NOT FOUND")
EOF
```

Record both dat_offsets (or the written finding that the test image
lacks it — then test-exit path must be re-derived from the test image's
own exit code before Task 13).

- [ ] **Step 2: KERNEL-SLICE.** Diff the snapshot against the BIOS ROM
to pin exact bounds (identity: RAM offset − `0x800` = ROM offset, per
`tooling.md` §RAM snapshot):

```bash
python3 - <<'EOF'
ram  = open("tools/ram-snapshot.bin","rb").read()
rom  = open("bios/naomi/epr-21576h.ic27","rb").read()
# grow the identical run out from the known anchor (RAM 0x1004 == ROM 0x804);
# the ROM-side offset is RAM-0x800, so the run cannot start below RAM 0x800
lo = 0x1004
while lo > 0x800 and ram[lo-1] == rom[lo-1-0x800]: lo -= 1
hi = 0x1004
while hi < 0x8000 and ram[hi] == rom[hi-0x800]: hi += 1
print("identical run: RAM", hex(lo), "-", hex(hi), "ROM", hex(lo-0x800), "-", hex(hi-0x800))
# the 0x600-0x800 sub-window has no ROM-0x800 source: locate it separately
print("0x600-0x800 in ROM at:", hex(rom.find(ram[0x600:0x800])))
EOF
```

The `0x600`–`0x800` sub-window has no ROM−0x800 source (negative
offset) — locate its bytes in the ROM by direct search
(`rom.find(ram[0x600:0x800])`) or record it as snapshot-only content
that the loader takes from a build-time slice of the snapshot's own
recipe (re-derived from the BIOS boot, still never committed). Pin
`KERNEL_ROM_OFF`/`KERNEL_LEN` (or a two-piece slice list) such that
`loader-placed bytes == snapshot bytes` over `[0x600, hi)`, and verify:

```bash
# after deciding offsets, byte-compare the chosen ROM slice(s) against the snapshot window
```

- [ ] **Step 3: BLOB-CHECK.**

```bash
python3 - <<'EOF'
import struct
rom = open("bios/naomi/epr-21576h.ic27","rb").read()
ws = struct.unpack_from("<8I", rom, 0x60000)
print([hex(w) for w in ws], all((w & 0x0fff0000) == 0x0c010000 for w in ws))
EOF
```

Expected: `True` — the 8-vector signature holds in the user's dump, so
pre-placement satisfies `FUN_8c065ff0`'s consumers. Record. If any
vector points below `0x0c018000` (i.e., into the shim window
`0x0c010000`–`0x0c017fff`), STOP and surface: the blob claims part of
the shim home and the map must shrink.

- [ ] **Step 4: Commit**

```bash
git add docs/kb/phase4-conversion.md && git commit -m "phase4: restart, kernel-slice, blob pins (RESET-PATCH, KERNEL-SLICE, BLOB-CHECK)"
```

---

### Task 6: Skeleton import — shim + loader compile with senkosp constants

**Files:**
- Create: `shims/` (from `../cleopatra/shims/`: `Makefile`, `shim.ld`, `include/shim_iface.h` rewritten, `src/{main,cart,gd,maple,jvs,scif,util}.c`, `src/gdstack.S`, `test/`)
- Create: `loader/` (from `../cleopatra/loader/`: `Makefile`, `main.c`, `handoff.S`, `ip.txt`)
- Create: `Makefile` (top level: `shims`, `loader`, `test` targets)
- Create: `scripts/test_maple_literals.py` (copy from Cleopatra, empty senkosp baseline)
- Modify: `docs/kb/tooling.md` (KOS env record)
- Test: `shims/test/` host tests + `make test`

**Interfaces:**
- Consumes: Cleopatra sources verbatim as the base; pins from Tasks 3–5 are NOT needed yet (this task only compiles).
- Produces: `shims/include/shim_iface.h` — the single source of truth every later task includes; `make -C shims` → `shims/build/shim.bin` + `shim.map`; `make -C loader` → `build/1ST_READ.BIN`; `make test` runs host tests + the maple-literal scan.

- [ ] **Step 1: Copy the skeleton**

```bash
cp -R ../cleopatra/shims shims && rm -rf shims/build shims/data
cp -R ../cleopatra/loader loader && rm -f loader/*.o loader/loader.elf loader/splash.png
cp ../cleopatra/scripts/test_maple_literals.py scripts/
git add -N shims loader scripts/test_maple_literals.py
```

- [ ] **Step 2: Write the senkosp `shim_iface.h`** (replaces Cleopatra's
wholesale — this is the RAM map made executable):

```c
/* Single source of truth for Phase 4 addresses. Consumed by shim (freestanding),
 * loader (KOS), and scripts/build_patch_table.py (parses the #defines).
 * RAM map: spec 2026-08-22 §RAM map (corrected shim home 0x8c010000). */
#ifndef SHIM_IFACE_H
#define SHIM_IFACE_H

#define SHIM_BASE       0x8c010000  /* low window; Task 2 write-watch verified */
#define SHIM_CODE_MAX   0x00004000  /* 16 KB code+rodata+data+bss budget */
#define SHIM_END        0x8c018000  /* exclusive: BIOS blob home starts here */

/* Fixed data blocks (offsets from SHIM_BASE, accessed via P2) */
#define SHIM_ERR        (SHIM_BASE + 0x4000)  /* u32[4]: code, a, b, magic */
#define G1_MIRROR       (SHIM_BASE + 0x4800)  /* 0x800: fake 0x5f7000-0x5f77ff */
#define MAPLE_MIRROR    (SHIM_BASE + 0x5000)  /* 0x100: fake 0x5f6c00-0x5f6cff */
#define MAPLE_MIRROR_LEN 0x100
#define MAPLE_TX        (SHIM_BASE + 0x5100)  /* 32-byte aligned descriptor+frame */
#define MAPLE_RX        (SHIM_BASE + 0x5140)
#define SHIM_STATE      (SHIM_BASE + 0x5200)  /* u32[8]: [0]=boot mode 0=main 1=test */
#define SHIM_BOUNCE     (SHIM_BASE + 0x5800)  /* 2048-byte sector bounce */
#define GD_STACK_BOTTOM (SHIM_BASE + 0x6000)  /* 8 KB private stack, grows down */
#define GD_STACK_TOP    (SHIM_BASE + 0x8000)  /* = SHIM_END */

/* Loader-placed BIOS-derived blocks (outside shim home) */
#define KERNEL_DST      0x8c000600  /* Naomi RTOS kernel slice; len = Task 5 KERNEL-SLICE */
#define BIOS60000_DST   0x8c018000  /* 28,672 B blob; FUN_8c065ff0 contract */
#define BIOS60000_LEN   0x7000

/* Game images (docs/kb/game.md §Parsed .dat header) */
#define GAME_LOAD_ADDR  0x8c020000
#define GAME_ENTRY      0x8c021000
#define MAIN_DAT_OFF    0x00000000
#define MAIN_LEN        0x00171ff8
#define TEST_DAT_OFF    0x00171ff8
#define TEST_LEN        0x0004dc40

#define STAGING_ADDR    0x8cd00000  /* 3 MB to RAM top; images are 1.5 MB / 311 KB */

/* GDI geometry — B5 donor-clone layout (make_gdi.py):
 * track04 = [loader zero-padded to the donor 3,538,944 B boot region][.dat] */
#define CART_FAD        451878      /* = donor CART_LBA 451728 + 150 */
#define CART_SIZE       0x0efb0000  /* 251,342,848 = len(senkosp.dat) */

#define P2ADDR(a)       ((a) | 0xa0000000)
#ifndef HOST_TEST
#define P2(a)           ((volatile unsigned int *)P2ADDR(a))
#endif

/* HUD/diag toggles — same semantics as Cleopatra (util.c) */
#ifndef SHIM_HUD
#define SHIM_HUD 1              /* breadcrumbs on-screen; 0 for release */
#endif

#endif
```

- [ ] **Step 3: Adapt `shim.ld`**: base `. = 0x8c010000;`, budget assert
`ASSERT(. <= 0x8c014000, "shim exceeds SHIM_CODE_MAX")`.

- [ ] **Step 4: Gut the Cleopatra-specifics so it compiles.** In
`shims/src/`: `gd.c` → replace body with stubs
(`int gd_read_fad(unsigned fad, void *dst, unsigned sectors){ return -1; }` —
Task 7 implements); `cart.c`/`main.c`/`maple.c`/`jvs.c` → keep the
structure and the HUD/util plumbing, `#if 0` the Cleopatra-address
service bodies with a `/* re-enabled per-task: see plan Tasks 10-12 */`
marker, so the files compile against the new header. `jvs.c`: install
the senkosp bit table now (it is fully known —
`docs/kb/input-map.md`, measured):

```c
/* DC pad -> senkosp JVS P1 digital word (input-map.md §DC pad layout, measured bits) */
#define JVS_START  0x8000
#define JVS_SERVICE 0x4000
#define JVS_UP     0x2000
#define JVS_DOWN   0x1000
#define JVS_LEFT   0x0800
#define JVS_RIGHT  0x0400
#define JVS_M      0x0200   /* BTN0 "MAIN"   <- DC A */
#define JVS_S      0x0100   /* BTN1 "SUB"    <- DC X */
#define JVS_BARRAGE 0x0080  /* BTN2          <- DC Y */
#define JVS_A      0x0040   /* BTN3 "ACTION" <- DC B */
#define JVS_OD     0x0020   /* BTN4          <- DC R trigger */
/* Test = bit 18, Coin = bit 19 of the 32-bit word (source-derived) */
#define JVS_TEST   (1u << 18)
#define JVS_COIN   (1u << 19)

unsigned dc_to_jvs(unsigned dc_buttons) {
    unsigned w = 0;
    if (!(dc_buttons & CONT_DPAD_UP))    ;  /* KOS CONT_* bits are active-low in cond.buttons */
    /* Fill from the live GetCondition struct in maple.c; this fn takes the
     * already-normalized pressed-mask. */
    if (dc_buttons & CONT_START)         w |= JVS_START;
    if (dc_buttons & CONT_DPAD_UP)       w |= JVS_UP;
    if (dc_buttons & CONT_DPAD_DOWN)     w |= JVS_DOWN;
    if (dc_buttons & CONT_DPAD_LEFT)     w |= JVS_LEFT;
    if (dc_buttons & CONT_DPAD_RIGHT)    w |= JVS_RIGHT;
    if (dc_buttons & CONT_A)             w |= JVS_M;
    if (dc_buttons & CONT_X)             w |= JVS_S;
    if (dc_buttons & CONT_B)             w |= JVS_A;
    if (dc_buttons & CONT_Y)             w |= JVS_BARRAGE;
    if (dc_buttons & CONT_RTRIG)         w |= JVS_OD;   /* R as digital: rtrig > 128 mapped by caller */
    return w;
}
```

(The freestanding shim defines its own `CONT_*` constants matching the
maple GetCondition bit layout — copy them from Cleopatra's `maple.c`,
which already normalizes active-low + triggers.)

- [ ] **Step 5: Loader Makefile deltas.** `BIOS` path stays
`../bios/naomi/epr-21576h.ic27` (senkosp repo has `bios/naomi/` — verify
the file exists and record its md5 in `tooling.md`). Replace the
`bios_data.bin` recipe with senkosp's two slices (`dd` numbers from Task
5's KERNEL-SLICE + the `0x60000` blob):

```make
../build/bios_data.bin: $(BIOS)
	mkdir -p ../build
	dd if=$(BIOS) bs=1 skip=393216 count=28672 2>/dev/null > $@      # 0x60000 blob
	dd if=$(BIOS) bs=1 skip=$(KERNEL_ROM_OFF) count=$(KERNEL_LEN) 2>/dev/null >> $@
	@test $$(stat -f%z $@) -eq $(BIOS_DATA_TOTAL) || { echo "bios_data.bin wrong size"; rm -f $@; exit 1; }
```

with `KERNEL_ROM_OFF`/`KERNEL_LEN`/`BIOS_DATA_TOTAL` set from Task 5's
pinned values (literal numbers in the Makefile with a citation comment).
Keep `.DELETE_ON_ERROR`, the header-dependency lines, and the objcopy
blob rules verbatim (they encode two real Cleopatra bugs).

- [ ] **Step 6: Loader main.c minimal senkosp pass.** Change constants to
the new header names; **delete** the `sysrd_test` BIOS-syscall rehearsal
(runtime syscalls are dead by design here — loader still uses
`cdrom_read_sectors` which is fine pre-handoff); read `MAIN_LEN` from
`CART_FAD`; keep patch-apply, splash, halt/say. Combo + test image +
copy-record handoff land in Task 10 — for now keep Cleopatra's single
copy handoff and jump `GAME_ENTRY` guarded behind `#if 0` with an
unconditional `halt("PHASE4 TASK6: loader alive, image verified")` after
the `NAOMI` magic check.

- [ ] **Step 7: Build both; run host tests**

```bash
source ../cleopatra/tools/kos/environ.sh
make -C shims && make -C loader        # both exit 0
cc -DHOST_TEST -Ishims/include shims/test/test_host.c -o /tmp/senkosp_test_host && /tmp/senkosp_test_host   # exit 0
python3 scripts/test_maple_literals.py # empty baseline: classify any hit before proceeding
```

Record the KOS env + versions in `tooling.md` (rung: "reused install,
path + `kos-cc --version` output").

- [ ] **Step 8: Commit**

```bash
git add shims loader Makefile scripts/test_maple_literals.py docs/kb/tooling.md
git commit -m "phase4: skeleton imported, senkosp shim_iface.h, both builds compile"
```

---

### Task 7: Raw-ATA GD driver (`shims/src/gd.c`)

**Files:**
- Modify: `shims/src/gd.c` (full rewrite — the new code of this phase)
- Test: `shims/test/test_gd_math.c` (host: FAD/offset/alignment math)
- Modify: `loader/main.c` (loader-side self-test block)

**Interfaces:**
- Consumes: `shim_iface.h` (`CART_FAD`, `SHIM_BOUNCE`, `GD_STACK_*`).
- Produces: `int gd_read_fad(unsigned fad, void *dst, unsigned sectors)` (0 = ok, negative = error code into `SHIM_ERR`); `int gd_read_cart(unsigned cart_off, void *dst, unsigned len)` — the offset→FAD + head/body/tail splitter every cart service calls.

- [ ] **Step 1: Host test for the splitter math** (`test_gd_math.c`):

```c
#define HOST_TEST 1
#include "../include/shim_iface.h"
#include <assert.h>
/* recompute the (fad, head_skip, body_sectors, tail_len) plan for a read */
struct plan { unsigned fad, head_skip, head_len, body_secs, tail_len; };
struct plan gd_plan(unsigned cart_off, unsigned len);   /* from gd.c, pure */
int main(void) {
    struct plan p = gd_plan(0, 2048);                 /* aligned single sector */
    assert(p.fad == CART_FAD && p.head_len == 0 && p.body_secs == 1 && p.tail_len == 0);
    p = gd_plan(100, 100);                            /* inside one sector */
    assert(p.fad == CART_FAD && p.head_skip == 100 && p.head_len == 100 && p.body_secs == 0);
    p = gd_plan(2048 + 10, 4096);                     /* head + body + tail */
    assert(p.fad == CART_FAD + 1 && p.head_skip == 10 && p.head_len == 2038
        && p.body_secs == 1 && p.tail_len == 10);
    return 0;
}
```

- [ ] **Step 2: Run it to make sure it fails** (no `gd_plan` yet):
compile per the existing host-test recipe; expect link failure.

- [ ] **Step 3: Implement `gd.c`.** Structure:

```c
/* Raw-ATA GD-ROM PIO driver. Runtime replacement for BIOS syscalls, which die
 * when the loader places the Naomi RTOS kernel over their low-RAM home
 * (spec §Approach). References (verify + cite in KB while implementing):
 *   flycast core/hw/gdrom/gdrom_response.cpp / gdromv3.cpp  (SPI cmd 0x30, regs)
 *   KOS kernel/arch/dreamcast/hardware/cdrom.c              (packet protocol shape)
 */
#include "shim_iface.h"
#define GD_ALTSTAT (*(volatile unsigned char *)0xa05f7018)
#define GD_DATA    (*(volatile unsigned short*)0xa05f7080)
#define GD_FEATURES (*(volatile unsigned char *)0xa05f7084)
#define GD_SECCNT  (*(volatile unsigned char *)0xa05f7088)
#define GD_BCLO    (*(volatile unsigned char *)0xa05f7090)
#define GD_BCHI    (*(volatile unsigned char *)0xa05f7094)
#define GD_DRVSEL  (*(volatile unsigned char *)0xa05f7098)
#define GD_STATCMD (*(volatile unsigned char *)0xa05f709c)
#define ST_BSY 0x80
#define ST_DRQ 0x08
/* bounded waits: never spin forever -- on timeout write SHIM_ERR and return */
static int wait_clear(unsigned char mask) { ... guard loop ~50M iters ... }
static int wait_set(unsigned char mask)   { ... }
int gd_packet_read(unsigned fad, unsigned sectors, void *dst);
    /* select drive, FEATURES=0 (PIO), byte-count = 2048, CMD=0xA0 (PACKET),
     * wait DRQ, write 6 u16 packet words: {0x30, flags(data=1), FAD b23-16,
     * FAD b15-8, FAD b7-0, 0, 0, 0, len b23-16, len b15-8, len b7-0, 0}
     * (12 bytes, SPI CD_READ), then per sector: wait DRQ, read 1024 u16 -> dst. */
struct plan gd_plan(unsigned cart_off, unsigned len);   /* pure, host-tested */
int gd_read_cart(unsigned cart_off, void *dst, unsigned len);
    /* plan() -> head via SHIM_BOUNCE, body direct (dst 2-byte aligned: u16
     * stores; use bounce for odd dst), tail via bounce; all stores through
     * P2ADDR(dst) — cache coherency, the C1 lesson. */
```

Write the exact packet layout only after step 4's source check — the
sketch above is the shape, the emulator source is the authority.

- [ ] **Step 4: Verify the register map + SPI packet against primary
sources** — open
`../flycast4naomi2dreamcast/core/hw/gdrom/gdromv3.cpp` (register
handlers) and `gdrom_response.cpp` (command 0x30 parsing: FAD and
length fields' byte order); fix the driver to match; put the citations
(file:line) in `gd.c` comments and `docs/kb/phase4-conversion.md` §GD
driver.

- [ ] **Step 5: Host test passes**

```bash
# per the host-test make recipe
./test_gd_math   # exit 0
```

- [ ] **Step 6: Loader-side self-test** (in `main.c`, after the KOS-read
`NAOMI` check, before the Task 6 halt):

```c
/* Rehearse the shim's exact runtime GD path before handing the game to it
 * (replaces Cleopatra's syscall rehearsal -- our runtime path is raw ATA). */
static uint8 rawbuf[2048] __attribute__((aligned(32)));
extern int gd_read_fad(unsigned fad, void *dst, unsigned sectors);
if (gd_read_fad(CART_FAD, rawbuf, 1) != 0) halt("RAW-ATA READ FAIL");
if (memcmp(rawbuf, stage, 2048))           halt("RAW-ATA MISMATCH VS KOS READ");
say("cart read OK (raw ATA)");
```

Link `gd.c` into the loader too (add to `loader/Makefile` OBJS via a
small wrapper or compile the file twice — keep it lazy: add
`../shims/src/gd.c` to the loader's source list; it is freestanding C).

- [ ] **Step 7: Commit** (emulator proof of this step lands with Task 8's
first DC boot — the loader can't run before a disc exists)

```bash
git add shims/src/gd.c shims/test/ loader/ && git commit -m "phase4: raw-ATA GD driver + host-tested splitter + loader rehearsal"
```

---

### Task 8: GDI mastering + first DC-profile boot (loader alive)

**Files:**
- Create: `scripts/make_gdi.py` (adapt from `../cleopatra/scripts/make_gdi.py`)
- Create: `scripts/capture_dc_leg.sh` (DC-profile leg launcher)
- Modify: `Makefile` (top-level `gdi` target), `docs/kb/tooling.md`, `docs/kb/phase4-conversion.md`

**Interfaces:**
- Consumes: `build/1ST_READ.BIN`; `senkosp.dat`; the donor archive `"[GDI] Dolphin Blue.7z"` (copy from `../cleopatra/` to repo root, gitignored).
- Produces: `build/disc.gdi` + tracks; `make gdi` one-command build; `scripts/capture_dc_leg.sh <leg>` → `captures/phase4/<leg>.log` running `build/disc.gdi` in the fork's **DC** profile.

- [ ] **Step 1: Adapt `make_gdi.py`.** Deltas from Cleopatra's (keep the
B5 max-clone structure byte-for-byte — it is real-HW verified
2026-07-23):
  - cart source: `senkosp.dat` (assert `len == 251342848`);
  - IP.BIN metadata block: `IP_PRODUCT = "T-SRS001M"` (same fake-serial
    convention, no collision), `IP_TITLE = "SENKO NO RONDE SPECIAL"`,
    `IP_DATE = "20260822"`, `IP_COMPANY` unchanged (fan-port family
    convention);
  - track04 = loader zero-padded to 3,538,944 B + `senkosp.dat`
    (CART_FAD math identical — assert `451728*2048` alignment holds as
    in the donor layout).

- [ ] **Step 2: `capture_dc_leg.sh`** (clone of `capture_leg.sh` with a
GDI default and no BIOSEXEC export):

```bash
#!/bin/bash
set -euo pipefail
leg="${1:?usage: capture_dc_leg.sh <leg-name> [gdi-path]}"
repo="$(cd "$(dirname "$0")/.." && pwd)"
bin="$repo/../cleopatra/tools/flycast-src/build/Flycast.app/Contents/MacOS/Flycast"
gdi="${2:-$repo/build/disc.gdi}"
log="$repo/captures/$leg.log"
mkdir -p "$(dirname "$log")"
[ -e "$log" ] && { echo "refusing to overwrite existing $log" >&2; exit 1; }
defaults write com.flyinghead.Flycast ApplePersistenceIgnoreState -bool YES
pkill -9 -f "flycast-src.*Flycast" 2>/dev/null || true
sleep 1
FLYCAST_CARTLOG="$log" exec "$bin" -config config:rend.vsync=no "$gdi" \
    > "${log%.log}.stdout.log" 2>&1
```

- [ ] **Step 3: Build + boot**

```bash
make gdi
scripts/capture_dc_leg.sh phase4/loader-alive & sleep 90; pkill -9 -f "flycast-src.*Flycast"
```

Expected on screen (screenshot with `screencapture -x
docs/kb/img/phase4-loader-alive.png`): splash, then the
`PHASE4 TASK6: loader alive, image verified` halt — which also proves
`cart read OK (raw ATA)` ran (Task 7's rehearsal halts otherwise).
If the KOS read works but raw ATA fails: debug-loop protocol; the
Flycast gdrom source names which register write it rejected.

- [ ] **Step 4: Record** in `tooling.md` (make gdi recipe, donor copy
step) and `phase4-conversion.md` (§First DC boot, screenshot ref).

- [ ] **Step 5: Commit**

```bash
git add scripts/make_gdi.py scripts/capture_dc_leg.sh Makefile docs/
git commit -m "phase4: GDI mastering (B5 clone) + first DC-profile boot, raw-ATA verified"
```

---

### Task 9: Patch-table generator (raw `.dat` offsets, main/test tags)

**Files:**
- Create: `scripts/build_patch_table.py` (adapt from Cleopatra's)
- Test: `scripts/test_build_patch_table.py`
- Modify: `loader/Makefile` (generation dependency block — keep Cleopatra's dependency comments, they encode real bugs)

**Interfaces:**
- Consumes: `scripts/reloc_patchset.json` (the 4 words — imported, not duplicated); Task 3–5 pin anchors (§cart-patch-sites, §maple-patch-sites, RESET-PATCH) transcribed as generator definitions with `expect` values; `shims/build/shim.map`; `shims/include/shim_iface.h`; `senkosp.dat` (old-byte verification source — NOT `boot.bin`: entries span both images, and `dat_offset` is uniformly a raw `.dat` offset, Phase 4 flag 7).
- Produces: `build/patch_table.h` defining `patch_t { u32 dat_off; u8 img; u8 len; u8 old[12]; u8 neu[12]; const char *what; }` (12-byte capacity: a hook is a 6-byte thunk plus its contiguous pooled `.long` target), arrays `senkosp_patches_main[]` / `senkosp_patches_test[]`; loader's `apply_patches(img, table, n, load_base)` subtracts `load_base` (`MAIN_DAT_OFF`/`TEST_DAT_OFF`) per entry.

- [ ] **Step 1: Write the failing generator test.** `test_build_patch_table.py`:
run the generator in a mode pointed at a 4-entry table (the reloc words
only), parse the emitted header, assert: (a) every `old` matches
`senkosp.dat` at `dat_off`; (b) the two test-image entries carry
`img == 1`; (c) re-running is deterministic (identical output).

- [ ] **Step 2: Run it; expect failure** (`build_patch_table.py` absent).

- [ ] **Step 3: Implement.** Keep Cleopatra's structure (symtab from
`shim.map`, mirror addresses parsed from `shim_iface.h`, `pool/ptr/hook`
kinds, hook = 6-byte `mov.l @(disp,PC),r0; jmp @r0; nop` + pooled
target); change addressing to raw `dat_offset` verified against
`senkosp.dat`, add the `img` tag, and import
`scripts/reloc_patchset.json` for the 4 reloc entries (single source).
Definitions section is filled from the KB pin anchors — each entry's
comment cites its anchor (e.g. `# CART-BASE, phase4-conversion.md`).

- [ ] **Step 4: Test passes**

```bash
cd scripts && python3 test_build_patch_table.py   # ok
```

- [ ] **Step 5: Commit**

```bash
git add scripts/build_patch_table.py scripts/test_build_patch_table.py loader/Makefile
git commit -m "phase4: patch-table generator — dat-offset schema, main/test tags, reloc import"
```

---

### Task 10: Integration v1 — placements, handoff copy-records, cart service, first game entry

**Files:**
- Modify: `loader/handoff.S` (copy-record list), `loader/main.c` (combo, image select, staging of shim/kernel/blob, record table)
- Modify: `shims/src/cart.c` (senkosp service re-enabled), `shims/src/main.c` (service entry points + `shim_reboot`), `shims/src/util.c` (HUD)
- Modify: `scripts/build_patch_table.py` (cart entries live)

**Interfaces:**
- Consumes: CART-BASE/CART-WAIT/CART-PIO/CART-BOOT-POOLS/G1-TIMING/RESET-PATCH/KERNEL-SLICE anchors; `gd_read_cart`.
- Produces: `shim_cart_service(void)` (hooked from CART-WAIT; reads the G1 mirror, calls `gd_read_cart`, marks completion in the mirror); `shim_cart_pio(...)` (CART-PIO ABI); `shim_reboot(void)` (RESET-PATCH target: `void shim_reboot(void){ ((void(*)(void))0xa0000000)(); }` — jump to the DC BIOS reset entry); a GDI whose main boot **enters the game** and streams.

- [ ] **Step 1: handoff.S v2** — replace the single-copy loop with a
record walker (still PIC, still P2-only):

```asm
! handoff(records_p2 r4, entry r5)
! record: .long src_p2, dst_p2, len   ; list ends with len==0
    .globl _handoff
    .globl _handoff_end
    .align 2
_handoff:
0:  mov.l   @(8,r4),r0      ! len
    tst     r0,r0
    bt      2f
    mov.l   @r4+,r1         ! src
    mov.l   @r4+,r2         ! dst
    add     #4,r4           ! skip len (already in r0)
    shlr2   r0              ! longwords (all records 4-aligned by construction)
1:  mov.l   @r1+,r3
    mov.l   r3,@r2
    add     #4,r2
    dt      r0
    bf      1b
    bra     0b
    nop
2:  mov.l   ccr_a,r1        ! invalidate+enable both caches
    mov.l   ccr_v,r2
    mov.l   r2,@r1
    nop; nop; nop; nop; nop; nop; nop; nop
    jmp     @r5
    nop
    .align 2
ccr_a:  .long 0xff00001c
ccr_v:  .long 0x0000090d
_handoff_end:
```

- [ ] **Step 2: Loader main.c** — combo check + image select + records:

```c
/* Boot-combo: hold A+Start on pad 1 during boot -> test image (spec Decision 1). */
int test_boot = 0;
maple_device_t *cont = maple_enum_type(0, MAPLE_FUNC_CONTROLLER);
if (cont) {
    cont_state_t *st = (cont_state_t *)maple_dev_status(cont);
    if (st && (st->buttons & CONT_A) && (st->buttons & CONT_START)) test_boot = 1;
}
uint32 img_off = test_boot ? TEST_DAT_OFF : MAIN_DAT_OFF;
uint32 img_len = test_boot ? TEST_LEN     : MAIN_LEN;
/* read [CART_FAD + img_off/2048 ..] ceil(img_len/2048) sectors -> STAGING_ADDR
 * (img_off is 2048-aligned for main (0); TEST_DAT_OFF 0x171ff8 is NOT --
 * read from the containing sector and memmove the 0x171ff8 % 2048 = 0x7f8
 * misalignment, or read via a staging+offset; keep it simple: read
 * sector-floor..sector-ceil into STAGING_ADDR-((img_off%2048)) guard) */
```

then apply the matching patch sub-table (`apply_patches(stage,
senkosp_patches_test_boot ? ... : ..., load_base=img_off)`), stage shim +
`bios_data` pieces high (staging tail), seed `SHIM_STATE[0] = test_boot`,
build the record table:

```c
struct rec { uint32 src, dst, len; } __attribute__((aligned(4)));
static struct rec records[6];
/* image, shim(SHIM_BASE..), kernel(KERNEL_DST), blob(BIOS60000_DST), terminator */
```

purge dcache over every staged range, `irq_disable()`, MMU off + TA
soft-reset block (keep Cleopatra's verbatim — the comments carry the HW
evidence), copy stub to `HANDOFF_SCRATCH 0x8ce00000`, call
`handoff(P2ADDR(records_staged), GAME_ENTRY)`.

- [ ] **Step 3: Shim services v1.** `cart.c`: implement
`shim_cart_service` against the pinned mirror layout (dest/len/offset
cells per CART-BASE map); breadcrumb every service
(`hud_mark('C', n_served)`). `main.c`: `shim_reboot` as above (one
line + a breadcrumb). Wire the patch entries in the generator
(CART-* + RESET-PATCH + reloc; maple entries stay off).

- [ ] **Step 4: Boot attempt + iterate.**

```bash
make gdi && scripts/capture_dc_leg.sh phase4/entry1 & sleep 120; pkill -9 -f "flycast-src.*Flycast"
```

Success bar for this task (not attract): the game **enters** (HUD shows
cart services > 0, PC advances past init — check the stdout log and
cartlog MDODMA lines for the maple boot driver's first kicks, which
will spin/hang since maple isn't serviced yet — a hang INSIDE the boot
maple driver at this stage is the expected stop, and is itself the
evidence cart streaming works). Anything earlier (loader halt, patch
mismatch, no cart service breadcrumbs) → debug-loop protocol.

- [ ] **Step 5: Record + commit**

```bash
git add loader shims scripts docs && git commit -m "phase4: integration v1 — placements, copy-record handoff, cart service live; game enters"
```

---

### Task 11: Maple boot-phase service → attract (gate criterion 1)

**Files:**
- Create: `scripts/extract_mie_blobs.py` (adapt `../cleopatra/scripts/extract_jvs_replies.py`)
- Modify: `shims/src/main.c`, `shims/src/maple.c` (boot service per MAPLE-BOOT-STRATEGY), `scripts/build_patch_table.py` (maple boot entries)
- Create: `shims/build/mie_*.c` (generated, gitignored)

**Interfaces:**
- Consumes: MAPLE-BOOT-STRATEGY, MIE-DESC anchors; `captures/*.log` MIERESP lines (senkosp's own enum blobs).
- Produces: `shim_maple_boot(...)` servicing the enum/handshake so the boot driver's poll completes with node-count ≥ 1; attract reached.

- [ ] **Step 1: Extract senkosp MIE reply blobs** from the Phase 2/3
captures (MIERESP is always-on):

```bash
python3 scripts/extract_mie_blobs.py captures/attract.log --out build/
# emits mie_sub01.c mie_sub03.c ... (one const-array .c per distinct reply class)
```

Adapt Cleopatra's extractor; assert each blob class is byte-stable
across its occurrences in the leg (mismatch → dump both, decide which
phase it belongs to before proceeding).

- [ ] **Step 2: Implement the boot service** per MAPLE-BOOT-STRATEGY
(entry-hook or poll-hook as pinned): walk the descriptor from the
mirror (MIE-DESC layout), copy the matching reply blob to the recv
address (P2 stores), zero mirror `SB_MDST`, breadcrumb `hud_mark('M',…)`.
Config/EEPROM sub `0x01`/`0x03` replies come from the same blob set at
this stage (the real captured EEPROM content — free-play forcing is
Task 12).

- [ ] **Step 3: Boot; expect attract.**

```bash
make gdi && scripts/capture_dc_leg.sh phase4/attract1 & sleep 300; pkill -9 -f "flycast-src.*Flycast"
screencapture -x docs/kb/img/phase4-dc-attract.png   # while running
```

Success bar: title/attract cycle on the DC profile (gate criterion 1).
Hangs → debug-loop; the usual suspects in order: node-count reply
content (Cleopatra's lesson), a maple pool word not repointed (grep the
cartlog for real `SB_MDST` writes — there must be **none** from the
game), an unserviced sub.

- [ ] **Step 4: Record + commit** (`phase4-conversion.md` §Attract,
screenshot ref, blob provenance)

```bash
git add scripts shims docs && git commit -m "phase4: maple boot service — DC-profile attract reached (criterion 1)"
```

---

### Task 12: Steady input + EEPROM/free-play → playable (criteria 2, 3, 5)

**Files:**
- Modify: `shims/src/main.c` (steady service on MAPLE-KICK-HOOK), `shims/src/maple.c` (real GetCondition, ports A+B), `shims/src/jvs.c` (frame build + checksum per TESTBIT-INJECT anchor's offsets)
- Modify: `scripts/build_patch_table.py` (steady maple entries live)
- Create: `shims/data/eeprom.bin` decision record (see step 3 — the bytes themselves are captured content, gitignored under `build/`)

**Interfaces:**
- Consumes: MAPLE-KICK-HOOK, MIE-DESC, TESTBIT-INJECT; `dc_to_jvs` (Task 6); Task 1's named EEPROM-write PC (context only).
- Produces: `shim_maple_steady(void)` — per-frame sub-`0x33` service from real pads; free-play baked; a playable build.

- [ ] **Step 1: Steady service.** On the hook: run the shim's own
GetCondition transaction for ports A and B (`MAPLE_TX/RX`, Cleopatra
`maple.c` — reuse verbatim, it already normalizes buttons + triggers),
map through `dc_to_jvs` (R trigger digital at threshold 128), build the
JVS has-data frame at the pinned offsets, recompute the checksum, place
sub-`0x01`/`0x03` (EEPROM read) replies from the baked image, accept
sub-`0x0b` writes into the shim's RAM copy of that image (session-only).

- [ ] **Step 2: Playtest legs**

```bash
make gdi && scripts/capture_dc_leg.sh phase4/play1   # operator: full 1P match
scripts/capture_dc_leg.sh phase4/play2p              # operator: 2P match entry + play
```

Operator report + screenshots into `docs/kb/img/`. Criteria 2 and 3.

- [ ] **Step 3: Free-play.** Bake it into the EEPROM image: run ONE
Naomi-profile leg where the operator sets Free Play in the test menu
(`scripts/capture_leg.sh phase4/eeprom-freeplay`, operator sets it,
exits, plays one credit to verify), extract the post-write image from
the sub-`0x0b` MIERESP payloads (extend `extract_mie_blobs.py` with
`--eeprom-after-write`), bake THAT as the shim's default image, rebuild.
Verify on DC: attract screen shows FREE PLAY, Start alone starts
(criterion 5). If the game still gates on a coin/settings struct
(Cleopatra's Task 18 precedent), find the flag by diffing the two
captured EEPROM images and pin the equivalent per-frame struct write in
the steady service — one patch/pin, recorded in the KB.

- [ ] **Step 4: Commit**

```bash
git add shims scripts docs && git commit -m "phase4: steady input + free-play — 1P/2P playable on DC profile (criteria 2,3,5)"
```

---

### Task 13: Test menu round trip (criterion 4)

**Files:**
- Modify: `loader/main.c` (test-boot polish), `shims/src/main.c` (Test/Service mapping in test mode), `scripts/build_patch_table.py` (test-image sub-table complete)

**Interfaces:**
- Consumes: `SHIM_STATE[0]`; RESET-PATCH (both images); Task 3 step 5 / Task 4 step 4 test-image entries.
- Produces: combo boot → test menu; navigation; exit → reboot → main boot.

- [ ] **Step 1: Test-mode input mapping.** In `shim_maple_steady` (the
test image runs the same serviced path per its own patched copies):
when `SHIM_STATE[0] == 1`, map DC **Start → Test (bit 18)** and
**A → Service (`0x4000`)** in the synthesized word (menu navigation:
Test advances, Service selects — arcade convention); leave the rest of
the layout live.

- [ ] **Step 2: Round-trip leg**

```bash
make gdi && scripts/capture_dc_leg.sh phase4/testmenu
# operator: boot holding A+Start -> test menu; navigate; change a setting;
# exit via SYSTEM MENU EXIT -> expect console reboot -> main boot to attract
```

The exit path exercises RESET-PATCH → `shim_reboot` →
`0xa0000000`. If Flycast's DC profile handles the reset jump
differently than hardware would (it may reboot to BIOS menu instead of
re-running the disc), record the observed behavior honestly — the
criterion is "lands back in a main boot"; if the emulator parks in the
BIOS menu with the disc bootable from there, that satisfies the reboot
contract and the note travels to Phase 5.

- [ ] **Step 3: Screenshots + record + commit**

```bash
git add shims loader scripts docs && git commit -m "phase4: test-menu round trip via boot combo + owned restart (criterion 4)"
```

---

### Task 14: Gate close-out (criteria 6, 7, 8)

**Files:**
- Modify: `docs/kb/phase4-conversion.md` (§Shipped architecture — final summary, Cleopatra style), `docs/kb/00-status.md`, `docs/kb/tooling.md`, `scripts/test_maple_literals.py` baseline
- Optional: Phase 3 criterion 4 cleanup (fresh-checkout Ghidra re-run — `scripts/ghidra/run.sh import` then the two scripts; update `00-status.md` if done)

**Interfaces:**
- Consumes: everything above.
- Produces: the Phase 4 gate audit in `00-status.md`, one box per spec exit criterion with file+evidence, honest limit carried verbatim.

- [ ] **Step 1: VMU-safety static scan** (criterion 6):

```bash
python3 scripts/test_maple_literals.py   # over every loader/shim object + the patched image regions
```

Classify every hit against the baseline (start empty, per the playbook
Phase 6 method); the shim's only real maple traffic is GetCondition —
any write-class literal is a finding, not an exemption.

- [ ] **Step 2: Clean-checkout build proof** (criterion 7):

```bash
git clone . /tmp/senkosp-clean && cd /tmp/senkosp-clean
ln -s <paths> roms bios; cp <repo>/senkosp.dat .; cp "<repo>/[GDI] Dolphin Blue.7z" .
source ../cleopatra/tools/kos/environ.sh && make gdi   # exit 0, md5 of disc tracks recorded
```

(Adjust the symlink/copy lines to what `tooling.md` documents as the
required gitignored inputs; the point is: fresh clone + documented
inputs + one command.)

- [ ] **Step 3: Verification pass.** Invoke
`superpowers:verification-before-completion`. Re-run: host tests, parser
self-tests, the maple-literal scan, `make gdi`, and one fresh
`phase4/final` DC leg reaching attract. No claim without its command
output.

- [ ] **Step 4: Docs.** `phase4-conversion.md` gains the §Shipped
architecture summary (what actually shipped, divergences from this plan
recorded honestly — Cleopatra's plan diverged massively and said so);
`00-status.md`: Phase 4 checklist with all eight criteria + evidence
lines, phase list advanced to **5**, spec's honest limit verbatim;
`tooling.md`: final capture-file inventory.

- [ ] **Step 5: Commit + finish**

```bash
git add docs scripts && git commit -m "phase4: gate audit — all eight criteria evidenced; status advanced to Phase 5"
```

Then invoke `superpowers:finishing-a-development-branch` (merge
`phase4-conversion` → `main` after user review).

---

## Plan self-review (done at write time)

- **Spec coverage:** RAM map → Tasks 5/6/10; loader → 6/8/10; cart shim
  → 3/7/10; maple shim → 4/11/12; patch table/build → 9 (+6 Makefiles);
  GDI → 8; observability → 6 (HUD import) + every bring-up task;
  fork probe → 1; O1 → 2; P1–P5 → 3/4/5; decisions 1–2 → 13/1; exit
  criteria 1→11, 2/3/5→12, 4→13, 6/7/8→14. No spec section uncovered.
- **Known unknowns are pinned tasks, not placeholders:** every "per
  anchor X" reference names a task that produces X and the KB section
  where it lands.
- **Type consistency:** `gd_read_cart`/`gd_read_fad`/`gd_plan`
  (Tasks 7/10), `shim_cart_service`/`shim_maple_boot`/
  `shim_maple_steady`/`shim_reboot` (10/11/12/13), `dc_to_jvs` (6/12),
  `patch_t`+`img` tag (9/10/13), `SHIM_STATE[0]` (6/10/13) — names
  match across tasks.

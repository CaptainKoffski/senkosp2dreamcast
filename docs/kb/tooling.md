# Tooling

Every tool this project uses: exact install/reuse steps, version, usage.
The environment must be rebuildable from scratch from this file.
Deep recipes that already live in `../cleopatra/docs/kb/tooling.md` are
referenced, not duplicated — that file is part of this project's method.

### Instrumented Flycast (reused build)

- **Binary:** `../cleopatra/tools/flycast-src/build/Flycast.app/Contents/MacOS/Flycast`
  (Mach-O arm64), commit `6e3522822` (Phase 4 Task 2, rebuilt 2026-08-22 —
  see below). Originally the same build the senkosp assessment v9 capture
  used (`../naomi2dreamcast/assessments/senkosp.md` §1, then `f014a410c`).
- **Source of truth:** `../flycast4naomi2dreamcast` (fork), HEAD `6e3522822`
  (Phase 4 Task 2, 2026-08-22) — the built copy is current. Phase 2 rebuilds
  only if it adds instrumentation; full build recipe (CMake 3.31.6 pin,
  DEVELOPER_DIR, ZLIB_TBD, Syphon patch): `../cleopatra/docs/kb/tooling.md`
  §"Flycast — source build".
  **Note (2026-08-22):** `../cleopatra/tools/flycast-src` and
  `../flycast4naomi2dreamcast` are two independent checkouts of the same
  `origin` remote (`CaptainKoffski/flycast4naomi2dreamcast`) and can drift —
  found 13 commits apart (Cleopatra-side instrumentation pushed directly
  from the `flycast-src` checkout, never pulled into the standalone one).
  Reconciled via `git stash` / fast-forward pull / `git stash pop` before
  this task's edits landed; before any future fork edit, `git fetch && git
  log --oneline HEAD..origin/master` in `flycast4naomi2dreamcast` to catch
  this early. Commit in `flycast4naomi2dreamcast` (source of truth), push,
  then `git pull --ff-only` in `flycast-src` before rebuilding — do not edit
  `flycast-src` directly and leave it uncommitted.
  **Phase 4 Task 1 fork commits:**
  `0166c5b77` — maple `trig=` tag (`maple_SB_MDST_Write`→`reg`,
  `maple_vblank`'s `SB_MDTSEL==1` branch→`vbl`) threaded into `MDODMA`/
  `MAPLEPC`/`MIERESP`; `cartlog_sp_sample()`/`cartlog_sp_water()`
  (`cartlog.cpp`, `SPWATER` emitted at the existing ~10s `cartlog_sample()`
  tick). `0d55a1812` — follow-up: per-event `sp=` on `MDODMA`/`MAPLEPC`
  lines, added after the whole-run `SPWATER` aggregate proved unable to
  separate the task-cluster floor from a third low-SP region — **identified
  2026-08-22 (Phase 4 Task 4) as the Naomi BIOS's own stack**, sampled before
  the BIOS hands the machine to the game, not a game stack at all
  (`docs/kb/boot-binary.md` §SP — two stacks, addenda 2026-08-22).
  The per-event `sp=` field remains the right construction regardless: it is
  what let `sp_consistent` be scoped to fn-confirmed PCs and so exclude the
  BIOS.
  **Phase 4 Task 2 fork commit:** `6e3522822` — `cartlog_shimwatch2()`
  (`naomi.cpp`), a baseline-and-compare write-watch over senkosp's own
  shim-home window (`mem_b` `0x00010000`–`0x00017fff`, P1
  `0x8c010000`–`0x8c018000`), reusing the existing whole-RAM handoff
  baseline `cartlog_main_base` rather than a second private snapshot buffer.
  Emits `SHIMWATCH2 addr= was= now=` at the same `cartlog_sample()` cadence.
  No checkout drift this time (`git fetch && git log --oneline
  HEAD..origin/master` in both checkouts was clean before this edit landed).
  `docs/kb/phase4-conversion.md` §Shim home (V2s).
- **BIOS:** `~/Library/Application Support/Flycast/data/naomi.zip` already
  installed (verified 2026-08-13); source copy in this repo: `bios/naomi.zip`.
- **Launch gotchas (macOS, every unattended run):**
  - absolute ROM path (relative → `Cannot stat ...`);
  - `defaults write com.flyinghead.Flycast ApplePersistenceIgnoreState -bool YES`
    once per session (else a prior killed run silently blocks the next boot);
  - `-config config:rend.vsync=no` (unfocused window deadlocks the emu
    thread otherwise);
  - `pkill -9 -f "flycast-src.*Flycast"` before relaunch (stale instance →
    SH4 vmem `Verify Failed`, no boot).
- **Screenshots:** env `FLYCAST_SHOT=/abs/path.png` (+ optional
  `FLYCAST_SHOT_EVERY=N` frames, default 60); `kill -USR1 <pid>` = reliable
  on-demand single grab. 640×480 RGB PNG. Copy the file before reading —
  it is overwritten continuously.

### dat-extract (../naomi2dreamcast/tools/dat-extract)

- **Purpose:** GD-ROM CHD → flat decrypted `.dat` (`NAOMI` header) for
  Ghidra/static analysis. Flycast does NOT need it (runs the romset
  directly).
- **Prereqs (all present 2026-08-13):** chdman (`brew install rom-tools`),
  `/opt/homebrew/bin/7zz`, clang (auto-builds `extract_dat` on first run).
- **Invocation for this game:** see §"senkosp.dat" below.

### Ghidra — 12.1.2 (reused install)

- `../cleopatra/tools/ghidra_12.1.2_PUBLIC/` + OpenJDK via
  `export PATH="/opt/homebrew/opt/openjdk/bin:$PATH"`. Install recipe +
  headless harness: `../cleopatra/docs/kb/tooling.md` §Ghidra. Not
  exercised in Phase 1; Phase 3 sets up this repo's own project dir +
  scripts (below).

#### Phase 3: this repo's Ghidra project (Task 3 onward)

Everything here is driven by the committed wrapper `scripts/ghidra/run.sh`
(it exports the openjdk PATH itself and defaults
`GHIDRA_HOME=../cleopatra/tools/ghidra_12.1.2_PUBLIC`; override the env var
if the install moves). Java in use: **OpenJDK 26.0.1 (Homebrew)**.

**1. The working image — the boot slice.** Static analysis runs on the main
load only (`.dat` offset 0 → RAM `0x8c020000`, entry `0x8c021000`), not the
251 MB `.dat`:

```sh
head -c 1515512 senkosp.dat > tools/boot.bin
md5 tools/boot.bin      # 07008ad629d628c519635dbc113487f5
md5 senkosp.dat         # 6283cf5c75d7fc32740a8e8e54d10aa8
head -c 1515512 senkosp.dat | cmp - tools/boot.bin && echo reproduces
```

1,515,512 B = the main load size from `game.md` §Parsed .dat header
(`0x171ff8`). `tools/` is gitignored — `boot.bin` is ROM content, **never
committed**, always regenerable by the line above.

**2. Import (full auto-analysis, once).** Project dir `tools/ghidra-proj`
(gitignored — it embeds ROM bytes), program name **`senkosp3`**:

```sh
scripts/ghidra/run.sh import
# = analyzeHeadless tools/ghidra-proj senkosp3 -import tools/boot.bin -overwrite \
#     -processor "SuperH4:LE:32:default" -loader BinaryLoader -loader-baseAddr 0x8c020000
```

No `-noanalysis` on import — full SH-4 auto-analysis is what follows
`jmp @rN` through literal pools.

**3. Run a script** (always `-noanalysis`, so the DB is not re-analyzed):

```sh
scripts/ghidra/run.sh script FindMmioXrefs.java
scripts/ghidra/run.sh script DisasmRange.java 0x8c029ee8 0x8c029f5c force
```

Committed scripts (`scripts/ghidra/`, all headlessly re-runnable):
`FindMmioXrefs` (MMIO literal-pool xref reporter), `ScanBiosTargets`
(BIOS-range flow refs + pool constants), `DumpEntryChain` (entry walk + SP
writes), `ScanPlacementConstants` (corridor/VRAM placement constants),
`Decomp`, `DisasmRange` (`… force` force-disassembles an undefined span),
`DisasmEntry`, `FindRefsTo`, `WhichFunc`, `ListPoolWords`, `ExportToXML`.

**DB mutation caveat, stated because it affects reproducibility:** the
`senkosp3` DB carries the *force-disassembly* additions Task 4 made
(`DisasmRange … force` over the undefined hardware-driver and RTC spans).
Those are monotonic additions to the listing. Their non-effect is argued for
**`FindMmioXrefs` only**: it counts *defined data*, and `run.sh script`
passes `-noanalysis`, so nothing promotes the recovered code's pool words to
defined data — boot-binary.md §Coverage limits documents that exact
non-effect (re-running the scan after the force-disassembly still reported
`rtc` = 3). **No equivalent argument is made for `DumpEntryChain`**: it walks
disassembled instructions, so a DB with more disassembly *could* in principle
walk further. Its output reproduced exactly here, but that is an observation
on this DB, not a proof of DB-independence.

**Fresh-checkout status — untested, stated plainly.** The spec's exit
criterion 4 asks for a re-run *from a fresh checkout* (given the gitignored
ROM). That path is: regenerate `tools/boot.bin` (step 1), `run.sh import`
(step 2, full auto-analysis), then the scripts (step 3) — **it has not been
exercised**. Two things a fresh checkout would not have: the Task 4
force-disassembly state, and any reference output to diff against
(`tools/` is gitignored, so `tools/mmio-xrefs.txt` does not exist until the
scan regenerates it). `00-status.md` criterion 4 carries this as a `[~]`.

**Reproduction check (Task 13, exit criterion 4 — 2026-08-22).** Both
reporting scripts were re-run from the committed harness and diffed
mechanically, not eyeballed:

```sh
scripts/ghidra/run.sh script FindMmioXrefs.java  > /tmp/mmio-rerun.txt
scripts/ghidra/run.sh script DumpEntryChain.java > /tmp/entry-rerun.txt
# strip the "INFO  <script>.java> " prefix + Ghidra harness banner, then diff
```

- `FindMmioXrefs`: **73 payload lines identical** to the copy of its own
  earlier output kept at `tools/mmio-xrefs.txt` — **gitignored, not
  committed** (it is derived ROM content; the scan above is what regenerates
  it) — 72 hits + `TOTAL hits=72`; per-block counts
  reproduce boot-binary.md's table exactly — `wdt` 43, `maple` 11, `g1dma`
  10, `rtc` 3, `cart` 3, `scif` 2, `pvr_fb` 0. Only difference in the raw
  files: the Ghidra/JVM banner (timings, JDK warnings).
- `DumpEntryChain`: all **35** instruction lines quoted in boot-binary.md
  §Entry chain match address-for-address and mnemonic-for-mnemonic, and all
  three `<== writes r15` lines carry the same values (`0xac00f400`,
  `0x8c00f400`, `0x8c00f000` via `8c170c14`). One documentation fix fell out
  of this run: the `Stack region: …` line was never script output — it is a
  derived value, now labelled as such in boot-binary.md §Stack region.

### senkosp.dat

Extraction (2026-08-13), from `../naomi2dreamcast/tools/dat-extract`:

```
cd ../naomi2dreamcast/tools/dat-extract
./chd2dat.sh senkosp
```

Output:

```
OK  senkosp  <- 317-5123-com.pic   251342848 bytes -> /Users/captainkoffski/AntigravityProjects/naomi2dreamcast/tools/dat-extract/out/senkosp.dat
```

Copy into this repo + validate:

```
cd /Users/captainkoffski/AntigravityProjects/senkosp2dreamcast
cp ../naomi2dreamcast/tools/dat-extract/out/senkosp.dat senkosp.dat
head -c 16 senkosp.dat   # -> "NAOMI" magic, confirmed
python3 ../cleopatra/scripts/parse_header.py senkosp.dat
```

Result: `senkosp.dat`, 251,342,848 bytes, gitignored (`*.dat` rule) — never
committed. Full `parse_header.py` output recorded in `game.md` §"Parsed .dat
header".

### Phase 2 capture harness

- **Capture gotchas hit during the campaign** (transient SH4 vmem "Verify
  Failed" startup crash → just relaunch the leg; service-menu RAM TEST
  hangs the instrumented fork → skip it): `docs/kb/phase2-measurements.md`
  §Capture incidents has the full per-leg record.
- **One leg = one run:** `scripts/capture_leg.sh <leg-name>` →
  `captures/<leg-name>.log` (gitignored; primary data — the script refuses
  to overwrite an existing leg). Instrumentation is env-gated
  (`FLYCAST_CARTLOG`, `core/hw/naomi/cartlog.cpp`); same build as Phase 1,
  fork frozen at `f014a410c`.
- **Parse/merge:**
  `python3 scripts/parse_cartlog.py captures/*.log [--csv docs/kb/cart-streaming-map.csv] [--attract-leg attract] [--input-report] [--hw-report]`
  — exits nonzero on any failed CHECK.
  Self-check: `cd scripts && python3 test_parse_cartlog.py` → `ok`.
- **Launch/stop pattern (macOS has no `timeout(1)`):** background the leg,
  wait out the duration, then kill by process match —
  `scripts/capture_leg.sh <leg-name> & sleep <secs>; pkill -9 -f "flycast-src.*Flycast"`.
  `capture_leg.sh` execs into Flycast, so the
  `pkill` is what ends the run; a killed run mid-profile-scan is a valid
  log (profiles are emitted every ~10 s).
- **Attract leg (2026-08-19):**
  `scripts/capture_leg.sh attract & sleep 660; pkill -9 -f "flycast-src.*Flycast"`
  — 660 s unattended, 39 MB / 1,081,979 lines / 69 MAINPROFILE samples
  (~690 s covered). `CHECK attract_anchor: PASS` — attract high-water
  `0x1fe7520` (33,453,344) reproduces the assessment anchor exactly; all
  other CHECKs PASS, `exit=0`.
- Profile scans (32 MB main + 16 MB VRAM + 8 MB ARAM byte-diffs) fire every
  ~600 vblanks (~10 s, `core/hw/naomi/naomi.cpp` cartlog_sample) — a brief
  periodic stutter during play is the instrument, not the game.

### Phase 3: BIOSEXEC entry gate (FLYCAST_ENTRYPC)

- **Fork change:** `../flycast4naomi2dreamcast` commit `19c9acb4f`
  ("cartlog: FLYCAST_ENTRYPC parameterizes the BIOSEXEC arming PC (senkosp
  phase 3)"), pushed to `origin/master` (`f014a410c..19c9acb4f`). Rebuilt
  into the same reused binary path (`../cleopatra/tools/flycast-src/build/
  Flycast.app/Contents/MacOS/Flycast`); `make -j8`, exit 0.
- **Build-tree provenance:** the local build tree at `19c9acb4f` = `f014a410c`
  (Phase 2's cited base) + 12 additive cartlog-watch commits already ahead of
  `origin/master` before this task (MMUCRWR vecbc/vecc0, SQWR, VIDFLG, SOFWR,
  IMLWR, SETWR, GAMEWR/BANDWR, C2D/TAREG/TAEND, GD-rate divider, load-engine
  RAM dump — round 12 through 20) + this task's gate edit. All lines Phase 2
  cited against `f014a410c` are present unchanged; the extras are additive
  watches (e.g. `SOFWR`), not modifications to existing instrument paths.
- **`cartlog_bios_check`** (`core/hw/sh4/interpr/sh4_interpreter.cpp` ~line
  26): the PC that arms the BIOSEXEC watch now comes from env
  `FLYCAST_ENTRYPC` (hex, no `0x` prefix), read once via `getenv`/`strtoul`;
  unset → default `0x8c04ae2c` (Cleopatra's trampoline, existing recipes
  unchanged). `scripts/capture_leg.sh` exports `FLYCAST_ENTRYPC=8c021000`
  (senkosp's own entry) by default; an explicitly exported
  `FLYCAST_ENTRYPC` in the caller's environment wins over the script's
  default (canary use). BIOSEXEC only fires under the interpreter —
  dynarec never reaches this check.
- **Interpreter toggle (required for any BIOSEXEC capture):**
  `~/Library/Application Support/Flycast/emu.cfg` line 39,
  `Dynarec.Enabled = no` before the run, `= yes` restored after — later
  tasks depend on dynarec being back on by default.
- **Canary results (2026-08-20, instrument control test):**
  - Positive (`FLYCAST_ENTRYPC=a0000000`, BIOS reset vector — BIOS itself
    runs at phys < 0x200000 from cold reset): 60 s run, 133,766 log lines,
    `grep -c BIOSEXEC` = **81,169** (large nonzero, as expected).
  - Negative (script default, senkosp entry `8c021000`): 90 s run, 105,480
    log lines (other instrument classes present throughout, confirming the
    run and instrumentation were live), `grep -c BIOSEXEC` = **0**, as
    expected — first attempt hit the known transient SH4 vmem
    `Verify Failed` startup crash (§Phase 2 capture harness above), relaunch
    succeeded.
  - Both canary logs deleted after recording (`rm captures/canary-*.log`) —
    canary logs are the only deletable log class; all other `captures/*.log`
    are primary data.

### Phase 3: flat-.dat boot control test (2026-08-20)

- **Leg:** `scripts/capture_leg.sh phase3/datboot "$PWD/senkosp.dat" & sleep
  120; pkill -9 -f "flycast-src.*Flycast"` — dynarec ON (default; the
  wrapper's `FLYCAST_ENTRYPC` export is a no-op here since BIOSEXEC only
  fires under the interpreter, §Phase 3 BIOSEXEC entry gate above). Log:
  `captures/phase3/datboot.log` — leg name `phase3/datboot` per controller
  ruling (Phase 3 legs live under `captures/phase3/` so the Phase 2 glob
  `captures/*.log` never matches them; `capture_leg.sh`'s `mkdir -p
  "$(dirname "$log")"` from Task 6 creates the nested dir). One attempt,
  ran the full 120 s clean (no transient-crash retry needed).
- **Health:** 181,754 log lines (~1,515 lines/s — same order of magnitude
  as the Phase 2 attract leg's 1,081,979 lines / 660 s ≈ 1,639 lines/s, and
  Task 6's canary-entry 105,480 lines / 90 s ≈ 1,172 lines/s; not
  truncated/corrupted). Zero error/crash/panic/abort strings. Other
  instrument classes present throughout — MDODMA 67,908, PVRW 54,720,
  TAREG/TAEND 12,584 each, C2D 12,249, MIERESP/MAPLEPC/JVSREPORT, SOFWR,
  WATERMARK, IMLWR, VRAMREGS/VRAMPROFILE — confirming a live run, not
  silently dead.
- **CARTDMA count:** `grep -c CARTDMA captures/phase3/datboot.log` = **158**
  (79 pure `CARTDMA` transfers + 79 paired `CARTDMAPC` pc/sp lines) —
  nonzero.
- **Full-run tuple comparison vs the known-good zip boot** (`captures/
  attract.log`, Phase 2): `diff <(grep "^CARTDMA " captures/phase3/
  datboot.log) <(grep "^CARTDMA " captures/attract.log | head -79)` →
  **empty diff, byte-identical** — the entire 79-tuple pure `CARTDMA
  src=.../dest=.../len=...` sequence in the 120 s `datboot.log` run matches
  `attract.log`'s first 79 tuples exactly, well past the brief's "first 50"
  / "more than 5" ask (the whole run, not just a prefix). This is the
  verdict-relevant criterion (same src/dest/len sequence) and it holds with
  zero exceptions.
  Separately, the paired `CARTDMAPC pc=`/`sp=` lines (call-site + stack
  pointer at each transfer) match exactly for the first 33 tuples, then
  diverge intermittently: `diff <(grep "^CARTDMA" captures/phase3/
  datboot.log) <(grep "^CARTDMA" captures/attract.log | head -158)` shows
  8 `<`/8 `>` lines — six `CARTDMAPC pc=` substitutions (same `sp=`,
  alternating between two call sites already seen in the matching prefix,
  `8c027ad0` vs `8c027f54`) at combined lines 66, 70, 90, 94, 122, 136,
  plus one adjacent CARTDMAPC/CARTDMA pair-ordering swap at ~98–100 (same
  two lines, reversed order). No `src=`/`dest=`/`len=` value differs
  anywhere. This is a benign scheduling/logging-order artifact between two
  differently-timed real-time runs (120 s vs 660 s), outside the verdict's
  stated criterion, not a content mismatch.
- **Visual confirmation:** `screencapture -x .../datboot-visual.png` fired
  ~75 s into the window → `stderr: could not create image from display`
  (screen locked / no active display session; operator asleep, per task
  instructions). Verdict at the time rested on the CARTDMA tuple comparison
  alone, per the task's operator-asleep ruling — not treated as a FAIL
  signal.
  **Visual: CLOSED (recorded Task 13; the observations are dated 2026-08-21
  and 2026-08-22).** The operator watched the flat-`.dat` vehicle's
  descendant — the patched `senkosp-reloc.dat`, same flat-`.dat` boot path —
  through boot, attract and a full played match on **2026-08-21**
  (*"Everything looks and plays normal, except on moment…"*, quoted in full
  in `relocation-map.md` §Operator playability report), and its one caveat,
  the ~10 s stutter, was closed by the **2026-08-22** control test — see
  §Phase 3 relocation dry run → Operator confirmations. Since the patched
  image differs from the plain `.dat` by exactly 4 words and boots by the
  identical mechanism, the flat-`.dat` boot path is visually confirmed as
  well; the deferred item is discharged, not carried into Phase 4.
- **Verdict: `.dat` boots identically: YES** — nonzero CARTDMA count +
  byte-identical `src`/`dest`/`len` sequence across the entire 79-tuple run
  vs the known-good zip boot. Per the task's Interfaces block, this is the
  dry-run vehicle decision: Tasks 11–12 patch and run `senkosp-reloc.dat`
  directly; no `FLYCAST_PATCHSET` load-time patch-hook fallback needed.

### Phase 3: RAM snapshot via Flycast AutoSaveState (Task 10b, 2026-08-20)

Route: **no new fork code**. The stock savestate path in the reused
instrumented build already serializes all 32 MB of Naomi main RAM
(`Serializer` in `.../core/serialize.cpp`; save path `dc_savestate()`,
`.../core/nullDC.cpp:181` — RZip-compressed), and `Emulator::unloadGame()`
auto-saves when `Dreamcast.AutoSaveState = yes`
(`.../core/emulator.cpp:751`). SDL2's default signal handler turns
`SIGTERM` into `SDL_QUIT` → `dc_exit()` → graceful unload, so no GUI
interaction is needed. Exact steps (reproducible):

1. `sed -i '' 's/Dreamcast.AutoSaveState = no/Dreamcast.AutoSaveState = yes/' \
   ~/Library/Application\ Support/Flycast/emu.cfg` (restored to `no`
   afterwards — the emulator persists config on exit).
2. `scripts/capture_leg.sh canary-snapshot` (canary log class — deleted
   after use), let attract run ~150 s, then
   `pkill -TERM -f "flycast-src.*Flycast"` and wait ~20 s.
3. State lands at `~/Library/Application Support/Flycast/data/senkosp.state`
   (6.3 MB compressed for a 59.4 MB stream).
4. **Carve** (python3, stdlib only): find the RZip magic `#RZIPv\x01#`
   (format: magic + u32 maxChunkSize + u64 totalSize, then u32-length-
   prefixed zlib chunks — `.../core/archive/rzip.cpp`), inflate all chunks,
   locate main RAM by plaintext: the syMalloc banner `"\nsyMalloc Ver
   2.01"` lives at RAM offset `0x15c980` (`0x8c15c980`), so RAM starts at
   `banner_offset − 0x15c980` (this run: stream offset `0x18a5a63`;
   layout-independent — no need to parse the serializer field order).
   Extract 32 MB → `tools/ram-snapshot.bin` (gitignored, never committed).
5. **Carve control tests (all must pass before analysis):**
   - `ram[0x15c980..]` = syMalloc banner ✓
   - `ram[0x85b00:0x85bb4] == senkosp.dat[0x65b00:0x65bb4]` (heap-create
     code) ✓
   - `ram[0x15b2c4..]` = GDFS error strings ✓
   - `ram[0x20000:0x21000] == senkosp.dat[0:0x1000]` (boot-image head) ✓
   Whole-image sanity: only 907/1,515,512 bytes of the loaded image span
   differ from the `.dat` (all initialized-data cells), which is itself a
   Task 10b finding (no code overlay exists).
6. **Second Ghidra program** (same project dir, own program name):
   `analyzeHeadless tools/ghidra-proj senkosp3ram -import
   tools/ram-snapshot.bin -overwrite -processor "SuperH4:LE:32:default"
   -loader BinaryLoader -loader-baseAddr 0x8c000000 -noanalysis`, then
   `analyzeHeadless tools/ghidra-proj senkosp3ram -process ram-snapshot.bin
   -noanalysis -scriptPath scripts/ghidra -postScript DisasmRange.java
   <start> <end> force` for targeted regions (full auto-analysis of 32 MB
   deliberately skipped).

Bonus identification from the snapshot: low RAM `0x0c000600`–`0x0c007xxx`
is the **Naomi BIOS resident RTOS kernel** — byte runs match the BIOS ROM
(`bios/naomi/epr-21576h.ic27`) at ROM offset − `0x800` (e.g. RAM `0x1cca`
= ROM `0x14ca`, RAM `0x1004` = ROM `0x804`); VBR+0x600 stub at
`0x0c000600`, INTEVT dispatcher `0x0c001cba`, per-task 0x200-byte TCBs at
`0x0c004000`. Not present in `senkosp.dat` (byte-search negative) — on DC,
Phase 4's loader must account for the game running under this BIOS kernel
(task/interrupt services), alongside the already-known `0x0c018000` blob.

### Phase 3: relocation dry run (Task 12, 2026-08-20/21)

**Patch + guards.** Same `apply_reloc.py` used for the dry-run image as
Task 11 (`docs/kb/relocation-map.md` §Patch set); guards checked before
trusting the output: word-count in the success message equals the patch
set's length, `old` bytes re-verified byte-for-byte against `senkosp.dat`
before each write (script's own check, not re-implemented here), and output
file size equals the input `.dat` size (relocation only overwrites 4
existing words, never resizes).

```
python3 scripts/apply_reloc.py senkosp.dat scripts/reloc_patchset.json -o senkosp-reloc.dat
# -> "patched 4 words -> senkosp-reloc.dat", exit 0
md5 senkosp-reloc.dat   # a80f03676c0595bcae1bebcc5f16f884
ls -la senkosp-reloc.dat senkosp.dat   # both 251,342,848 B
```

**Capture legs** (dynarec on — default, no `Dynarec.Enabled` edit needed;
contrast the interpreter-only BIOSEXEC gate above):

```
scripts/capture_leg.sh phase3/dryrun-attract "$PWD/senkosp-reloc.dat" & sleep 660; pkill -9 -f "flycast-src.*Flycast"
scripts/capture_leg.sh phase3/dryrun-play "$PWD/senkosp-reloc.dat"       # operator: boot -> coin -> one full match -> quit
```

**Mislabel + rename (honesty record).** A third leg was launched intending
a second operator-played match, under a play-leg name, but the operator
stepped away before inserting a coin — the captured traffic is a second
unattended attract-mode run in substance (no coin-in, demo-loop content
ceiling matches the first attract leg exactly — see
`relocation-map.md` §Dry-run evidence). Renamed post-capture to
`captures/phase3/dryrun-attract-2-unattended.log` so the filename matches
what was actually captured, rather than discarding a clean 1,024,458-line
sample over a labeling mistake. No content was altered by the rename.

**Gate:**

```
python3 scripts/parse_cartlog.py captures/phase3/dryrun-attract.log captures/phase3/dryrun-play.log \
    --dryrun captures/attract.log > tools/dryrun-parse.txt; echo "exit=$?"
```

`exit=0` under the rulings implemented in `scripts/parse_cartlog.py`
`dryrun_checks()`: the narrow `FB_W_SOF2` BIOS-default exemption, a mirror
boot-transient exemption (a register that settles below cap once and never
regresses, checked across every `VRAMREGS` snapshot in the leg — not just
the last), and stream-shape scoped to the first/attract leg with a strict
(no auto-pass) multiset comparison. Full CHECK lines and evidence chain in
`relocation-map.md` §Dry-run evidence. Self-check:
`cd scripts && python3 test_parse_cartlog.py` → `ok`.

**Lag investigation (operator-reported ~half-second stutter every ~10 s).**
Root cause is the cartlog instrument's own periodic scan
(`cartlog_profiles_tick()`, `../cleopatra/tools/flycast-src/core/hw/naomi/naomi.cpp:441-448`,
600-vblank/~10 s cadence per its own comment at line 440), not the patch.
Commands used to build the traffic-count comparison exonerating the patch
(same 660 s window, unpatched Phase 2 `captures/attract.log` vs patched
`captures/phase3/dryrun-attract.log`):

```
for f in CARTDMA PVRW C2D TAREG SOFWR; do
  echo -n "$f  unpatched="; grep -c "^$f" captures/attract.log
  echo -n "$f  patched=";   grep -c "^$f" captures/phase3/dryrun-attract.log
done
```

**Control test — CLOSED 2026-08-22.** The single-variable A/B that the
traffic-count comparison could not supply on its own: same instrumented
fork, same `senkosp-reloc.dat`, same machine, with **`FLYCAST_CARTLOG`
unset** so `cartlog_profiles_tick()` never runs its periodic >50 MB scan.
`capture_leg.sh` always exports the variable, so this leg is launched
without the wrapper — Flycast invoked directly on the patched `.dat` with
the usual macOS launch gotchas (§Instrumented Flycast) and no cartlog
env. Operator verdict, verbatim: **"no lags anymore, all smooth"**. Logging
off ⇒ stutter gone; the relocation patch is exonerated and the lag question
is closed (mirrored in `relocation-map.md` §Dry-run evidence).

**Operator confirmations, for the record — two dated parts, not one
session.** The spec's operator-observed playability leg is satisfied by:
**(a) 2026-08-21** (Task 12) — the patched image watched through boot,
attract, character selection and a **full played match**; verdict quoted in
full in `relocation-map.md` §Operator playability report, opening
*"Everything looks and plays normal, except on moment…"* — visually normal,
**with** the ~10 s stutter caveat that the same sentence goes on to
describe. **(b) 2026-08-22** — the control test above closes that caveat
(*"no lags anymore, all smooth"*). Do not quote (a)'s opening clause on its
own; it is not the whole sentence. Together these also discharge the
flat-`.dat` leg's deferred visual (§Phase 3 flat-.dat boot control test).

**FB_R_SOF1/FB_W_SOF1 boot-transient investigation** (`relocation-map.md`
§Dry-run evidence → Boot-transient finding) — commands used to falsify a
too-hasty first read ("the patch made no difference to the scan-out
register") and pin the real pattern (a capped-instrument boot artifact that
settles once and never regresses):

```
# (a) the instrument's own per-register log-line budget (pvr_regs.cpp:241-243,274-276)
grep -c "^SOFWR FB_R_SOF1" captures/phase3/dryrun-attract.log; grep -c "^SOFWR FB_R_SOF2" captures/phase3/dryrun-attract.log   # sum = 800
grep -c "^SOFWR FB_W_SOF1" captures/phase3/dryrun-attract.log                                                                 # = 800

# (b) last above-cap-eligible line vs total file length -- not "the whole run"
grep -n "^SOFWR FB_R_SOF1" captures/phase3/dryrun-attract.log | tail -1
grep -n "^SOFWR FB_W_SOF1" captures/phase3/dryrun-attract.log | tail -1
wc -l captures/phase3/dryrun-attract.log

# (c) one-way handoff: cross-tab PC x value over every SOFWR line for the register
grep "^SOFWR FB_R_SOF1" captures/phase3/dryrun-attract.log | sed -E 's/^SOFWR FB_R_SOF1 val=([0-9a-f]+).*pc=([0-9a-f]+).*/val=\1 pc=\2/' | sort | uniq -c

# (d) the uncapped instrument (VRAMREGS, one line per profile tick): which
# snapshot indices are above cap
grep "^VRAMREGS" captures/phase3/dryrun-attract.log | nl | grep "fb_r_sof1=800000\|fb_r_sof1=c00000"
```

Repeated per leg (`dryrun-attract.log`, `dryrun-play.log`,
`dryrun-attract-2-unattended.log`) and against the unpatched
`captures/attract.log` baseline; source cross-check:
`../cleopatra/tools/flycast-src/core/hw/pvr/pvr_regs.cpp:229-267`
(`SOFWR` emission and the `rsof_lines`/`wsof1_lines` budget counters) and
`.../core/hw/pvr/Renderer_if.cpp:641-653` (`rend_set_fb_write_addr`/
`rend_swap_frame` — the per-frame flip site the handoff write pair
`pc=8c032140` belongs to).

### Capture-file inventory (all legs, Phases 2–3)

`captures/` is gitignored — these are primary data, never committed, and
(except the canary class) never deleted. Phase 3 legs live under
`captures/phase3/` so the Phase 2 glob `captures/*.log` never matches them.
Sizes/line counts verified 2026-08-22.

| Leg | Lines | Size | What it is |
|---|---|---|---|
| `attract.log` | 1,081,979 | 37 MB | Phase 2 **anchor leg**, 660 s unattended attract. The `dryrun_stream_shape` reference and the unpatched baseline for every A/B in Phase 3. |
| `char-{baek,cuilan,ernula,fabian,karel,lili,mika,sakurako}.log` | — | 24–40 MB ea. | Phase 2 roster coverage, one leg per character. |
| `2p-stages.log` | — | 42 MB | Phase 2 stage coverage; the leg that moved the largest above-16m span's floor. |
| `testmenu.log`, `testmenu2.log` | — | 2 / 19 MB | Phase 2 test-menu legs — the only legs with EEPROM `sub=0x0b` traffic. |
| `input.log` | — | 5 MB | Phase 2 13-control press sequence (`input-map.md`). |
| `service-retest.log` | — | 5 MB | Phase 2 Service re-test, 4 clean presses. |
| `phase3/pc.log` | 1,607,839 | 62 MB | **Task 9 PC-capture leg** — interpreter mode, boot → attract → coin → full match → test menu. The dynamic half of targets 1/2/5/6/7. |
| `phase3/datboot.log` | 181,754 | 7 MB | Task 6 flat-`.dat` boot control test (dynarec) — proved the `.dat` is a valid dry-run vehicle. |
| `phase3/dryrun-attract.log` | 1,080,610 | 37 MB | **Task 12 dry-run attract leg** on `senkosp-reloc.dat`, 660 s — the shape-check leg. |
| `phase3/dryrun-play.log` | 2,067,273 | 81 MB | **Task 12 dry-run play leg** — operator-played, boot → coin → one full match; the VRAM high-pressure sample. |
| `phase3/dryrun-attract-2-unattended.log` | 1,024,458 | 36 MB | Bonus corroboration leg. **Renamed post-capture** (honesty record): launched under a play-leg name, but the operator stepped away before inserting a coin, so it is a second unattended attract run in substance. Renamed to match what it captured; no content altered. |

Deleted by design: `captures/canary-*.log` (BIOSEXEC canaries, Task 6;
`canary-snapshot` for the RAM snapshot, Task 10b). The canary class is the
only deletable one — its result is recorded in this file instead.

### Phase 4 leg inventory

Phase 4 legs live under `captures/phase4/` (own subdirectory, same reason as
`phase3/`: keeps `captures/*.log` from picking them up).

| Leg | Lines | Size | What it is |
|---|---|---|---|
| `phase4/pc2.log` | 340,977 | 14 MB | **Task 1 PC-capture leg** — interpreter mode, unattended boot → attract, ~300s, against the `trig=`/`sp=`-tagged fork (`0d55a1812`). Zero `trig=vbl` observed (17,445/17,445 `MDODMA`, 16,567/16,567 `MAPLEPC` all `trig=reg`) and zero sub-`0x0b` EEPROM-write lines — attract-mode never touches the EEPROM. `docs/kb/boot-binary.md` §Check lines, verbatim, run C. |
| `phase4/pc2-presp-diagnostic.log` | 339,341 | 14 MB | **Superseded, kept not deleted.** Same recipe as `pc2.log` but captured one fork commit earlier (`0166c5b77`, before the per-event `sp=` field existed on `MDODMA`/`MAPLEPC`) — `MAPLEPC`'s `trig=` data is identical/valid, but `sp=` is absent so it can't feed the PC-correlated `sp_consistent` check. Superseded by `pc2.log`; not deleted per the capture-file rule (primary data). |
| `phase4/shimwatch.log` | 1,083,410 | 39 MB | **Task 2 shim-home write-watch leg** — dynarec ON, unattended boot → attract, ~660s, against the `SHIMWATCH2`-emitting fork (`6e3522822`). 205 `CARTDMA` events, 69 `cartlog_sample()` ticks, **0 `SHIMWATCH2` lines** — `shim_home_clean: PASS`, exit 0. `docs/kb/phase4-conversion.md` §Shim home (V2s) — verdict recorded there as **PARTIAL** (attract regime only; match-play and test-menu regimes pending, see below). |
| `phase4/loader-alive.log`(`+.stdout.log`) | 140,562 | 5.7 MB | **Task 8 first DC boot, release build** — the brief's exact `capture_dc_leg.sh phase4/loader-alive` command against the mastered `build/disc.gdi`, DC profile, `LOADER_SERIAL=0` (release default, silent stdout by design). Continuous `MDODMA` background activity for the whole run, no gap, no error tag — the CPU never stalls. `docs/kb/phase4-conversion.md` §First DC boot. |
| `phase4/loader-alive-diag.log`(`+.stdout.log`) | — | 1.7 MB | **Task 8 diagnostic leg** — same disc, `LOADER_SERIAL=1` (temporary, reverted before commit) so KOS `dbglog` reaches Flycast's stdout (`Debug.SerialConsoleEnabled=yes`). stdout shows the full success sequence verbatim: `SENKOSP LOADER PHASE4 TASK6` / `GD init OK` / `cart read OK (KOS)` / `cart read OK (raw ATA)` / `patches OK` — the definitive text proof that Task 7's raw-ATA driver matches KOS's own read byte-for-byte. `docs/kb/phase4-conversion.md` §First DC boot. |
| `phase4/loader-alive-shot2.log`(`+.stdout.log`) | — | 3.7 MB | **Task 8 screenshot-correlated leg** — same diagnostic build + `FLYCAST_SHOT`; stdout repeats the identical success sequence, and one auto-grabbed frame from this same run (mid-tear: top of frame red, bottom still the prior NAOMI-logo frame) is the committed `docs/kb/img/phase4-loader-alive.png`. `docs/kb/phase4-conversion.md` §First DC boot. |
| `phase4/control-cleopatra-shot.log` | — | 6.7 MB | **Task 8 control test** — Cleopatra's own `build/disc.gdi` (read-only, real-HW-verified) through the same `capture_dc_leg.sh` + `FLYCAST_SHOT` path, to split "my disc" from "the process" per the debug-loop protocol when the first screenshot came back flat grey. Produced the byte-identical flat-grey placeholder, confirming a session-level render-pipeline stall, not a senkosp-specific problem. `docs/kb/tooling.md` §GDI mastering (Task 8). |
| `phase4/entry1.stdout.log` | — | 695 B | **Task 10, no leg.** Flycast aborted in `Init` with `Verify Failed : &mem_b[0] == ...` (`core/hw/sh4/dyna/driver.cpp:349`) — its dynarec VMEM layout assertion; the emulator never opened the disc, so no cartlog exists. Host-side flake, not reproduced in entry2/3/4. Kept per the never-delete-a-leg rule. |
| `phase4/entry2.log`(`+.stdout.log`) | 79,205 | 2.7 MB | **Task 10 first game entry** — diagnostic build (`LOADER_SERIAL=1`, shim `DEFS='-DSHIM_SERIAL=1 -DSHIM_TRACE=1'`, both reverted before commit). All 36 main-image patches applied, handoff taken, **26 cart services per boot cycle** with destinations in the relocated corridors, then the game's own restart path reboots the console — 4 complete cycles in 120 s, deterministic. `docs/kb/phase4-conversion.md` §Integration v1. |
| `phase4/entry3.log`(`+.stdout.log`) | 17,695 | 652 KB | **Task 10 freeze-frame leg** — same build plus `-DSHIM_REBOOT_FREEZE=1`, which makes `shim_reboot` dump the caller's stack over serial and spin instead of rebooting. The dump carries the game's own error text, `I/O BD IS NOT CONNECTED TO NAOMI BD.`, plus the saved PRs naming the shutdown chain — the leg that identified the stop. `docs/kb/phase4-conversion.md` §Integration v1 `entry3`. |
| `phase4/entry4.log`(`+.stdout.log`) | 64,549 | 2.2 MB | **Task 10 release-configuration leg** — committed defaults, zero guest serial output; identical behaviour (3 resets / 4 BIOS boots / game MMU-on every cycle in 100 s), confirming the diagnostic flags gate visibility only. `docs/kb/phase4-conversion.md` §Integration v1 `entry4`. |
| `phase4/entry5.log`(`+.stdout.log`) | 79,205 | 2.7 MB | **Task 10 review-fix confirmation leg** — same diagnostic build, after the two boot-hook fixes (base-word guard, destination fence). Identical to `entry2`: 4 cycles, 26 `CART` streams each, same first/last offsets and destinations, 0 `SHIMERR`, same stop. The two cartlogs have **identical class histograms** and diverge on exactly one field, a KOS-side maple descriptor address (`mdstar=0c0f0b40` vs `0c0f0bc0`) shifted by the 140-byte-larger shim blob — i.e. the fixes did not touch the live path. `docs/kb/phase4-conversion.md` §Integration v1 `entry5`. |

**Pending:** `phase4/pc2-testmenu` — an operator ~60s test-menu visit (Task 1
step 4 / operator-leg rule), needed to re-observe an EEPROM write under the
trig-tagged fork. Not yet captured — see `docs/kb/boot-binary.md` §Target:
EEPROM's 2026-08-22 update and the Task 1 report for the exact command.

**Pending:** `phase4/shimwatch-play` — an operator-played full match, then a
test-menu visit, then quit (Task 2 step 4 / operator-leg rule), needed to
close the `shim_home_clean` verdict from PARTIAL to full CLEAN. Command:
`scripts/capture_leg.sh phase4/shimwatch-play` (dynarec stays ON), then
`pkill -9 -f "flycast-src.*Flycast"` after the operator quits. Parse with
`python3 scripts/parse_cartlog.py captures/phase4/shimwatch*.log`.

A 45s scratchpad diagnostic capture (per-PC `MDODMA` `sp=` correlation,
`docs/kb/boot-binary.md` §SP — two stacks addendum's table) was written
outside `captures/` (session scratchpad, not primary data — its result is
fully recorded in that table) and is not part of this inventory.

### Dynarec toggle — restore after an interpreter-only leg

`~/Library/Application Support/Flycast/emu.cfg` line ~39,
`Dynarec.Enabled`. Interpreter-only probes (PC-exact `Sh4cntx.pc`/`r[15]`
sampling — Task 9's precedent, reused for Task 1) need `= no`; **restore
`= yes` after** — later legs depend on it. Verified restored 2026-08-22
after Task 1's captures.

### sh-elf / KOS toolchain — reused install (Phase 4 Task 6)

This repo has no local toolchain or KOS checkout — both reused in place
from the Cleopatra port, same pattern as the Ghidra/Flycast entries above.

- **sh-elf (dc-chain):** `/opt/toolchains/dc/sh-elf/bin/` — machine-wide
  install, not per-repo. `sh-elf-gcc --version` → `sh-elf-gcc (GCC) 15.2.0`.
  Used directly by `shims/Makefile` (`CC`/`NM`/`OBJCOPY` point at this path)
  and indirectly by KOS's `kos-cc` wrapper (below).
- **KOS:** `../cleopatra/tools/kos` — reused checkout, not copied into this
  repo. `source ../cleopatra/tools/kos/environ.sh` before any `make -C
  loader` or top-level `make loader`/`make test`; sets `KOS_BASE` to the
  Cleopatra-repo path (absolute), `KOS_CC_BASE=/opt/toolchains/dc/sh-elf`,
  `KOS_ARCH=dreamcast`, `KOS_SUBARCH` unset (defaults to `pristine` — this
  loader boots as a normal DC homebrew via GDEMU, not native Naomi).
  `kos-cc --version` → `sh-elf-gcc (GCC) 15.2.0` (kos-cc wraps sh-elf-gcc
  with KOS's include/lib paths).
- **BIOS used by the loader build:** `bios/naomi/epr-21576h.ic27`
  (senkosp2dreamcast's own copy, not Cleopatra's — same filename, Naomi
  Japan bios0), md5 `d1e4be4862f1f9592b17a042abc5831e`.
- **Finding (Task 6, load-address collision):** KOS's default link origin
  for this pristine-subarch target is `0x8c010000`
  (`../cleopatra/tools/kos/utils/ldscripts/shlelf.xc` line 10,
  `LOAD_OFFSET = ... 0x8c010000`) — confirmed empirically:
  `sh-elf-nm loader/loader.elf` places `_start`/`__executable_start` at
  `0x8c010000` and `_main` at `0x8c010158`, with a combined text+data+bss
  footprint of 838,704 B (`sh-elf-size loader/loader.elf`), i.e. the running
  loader occupies roughly `0x8c010000`–`0x8c0dc000`. This is the SAME
  address as senkosp's `SHIM_BASE` (`shims/include/shim_iface.h`) and
  overlaps `GAME_LOAD_ADDR` (`0x8c020000`) too. Cleopatra never hit this
  because its shim home was `0x8cfc0000` (near RAM top, far from
  `LOAD_OFFSET`); senkosp's shim home moved to low RAM (spec-pinned,
  `docs/kb/phase4-conversion.md` §Shim home) specifically because
  Cleopatra's old high placement collides with senkosp's own relocated heap
  (`docs/kb/relocation-map.md` §Provenance). The loader code that would
  `memcpy` the shim into place is present (Task 6 copies it in, from
  Cleopatra) but kept behind `#if 0` — this collision is why it must stay
  disabled until a later task resolves it (see task-6-report.md).

### GDI mastering (Task 8) — `make gdi`

- **Donor archive:** `[GDI] Dolphin Blue.7z` (44 MB) copied from
  `../cleopatra/` to this repo's root:
  `cp "../cleopatra/[GDI] Dolphin Blue.7z" .` — gitignored (`*.7z` line
  added to `.gitignore`; `git check-ignore -v "[GDI] Dolphin Blue.7z"`
  confirms). Same donor, same B5 max-clone structure and extraction method as
  Cleopatra's own recipe (`../cleopatra/docs/kb/tooling.md` §"Reference
  self-boot GDIs"): `scripts/make_gdi.py` extracts it into `build/donor/`
  itself via `/opt/homebrew/bin/7zz` (brew `sevenzip`), cached — re-extracted
  only if any of the five donor files is missing.
- **Build:** `make gdi` (top-level target, `Makefile`) → `loader` then
  `python3 scripts/make_gdi.py` → `build/disc.gdi` + four tracks. Exit 0;
  deterministic (four runs from clean, identical md5s — recorded in
  `docs/kb/phase4-conversion.md` §First DC boot).
- **`scripts/make_gdi.py`** — adapted from `../cleopatra/scripts/make_gdi.py`
  byte-for-byte except the cart source (`senkosp.dat`), the IP.BIN identity
  fields, and track04's payload; the B5 clone strategy, the donor extraction,
  and the CART_FAD/CART_SIZE cross-check against `shims/include/shim_iface.h`
  are unchanged. That cross-check caught a real bug on the first run — see
  `docs/kb/phase4-conversion.md` §First DC boot for the `CART_SIZE` fix.
- **`scripts/capture_dc_leg.sh <leg> [gdi-path]`** — DC-profile leg launcher
  (clone of `scripts/capture_leg.sh`, no `FLYCAST_ENTRYPC`/BIOSEXEC export,
  GDI default `build/disc.gdi`, separate `<leg>.stdout.log`). Same launch
  gotchas as §"Instrumented Flycast" above (`ApplePersistenceIgnoreState`,
  `vsync=no`, pre-launch `pkill`) plus: the DC profile takes the `.gdi` path
  itself as the CLI argument (no ROM/BIOS args — DC HLE boot needs neither).
- **Screenshot in this session — two working mechanisms, two caveats found
  (Task 8):**
  - `screencapture -x` (macOS): failed every attempt —
    `could not create image from display` — a Screen Recording TCC
    permission this session's process does not hold. Needs a human to grant
    it in System Settings; not fixable from inside the session.
  - `FLYCAST_SHOT=/abs/path.png` + `kill -USR1 <pid>`
    (§"Instrumented Flycast" above) worked, but the render/present pipeline
    was **severely throttled** for a backgrounded/occluded window in this
    session: it delivered only a handful of real frames over roughly two
    minutes before stalling, rather than the normal continuous 60 Hz. A
    control-test capture of a known-good disc (`../cleopatra/build/disc.gdi`,
    same method) hit the identical stall, confirming it is this session's
    render-pipeline throttling, not any particular disc. Budget several
    minutes, not seconds, for a DC-profile screenshot in this environment;
    `docs/kb/phase4-conversion.md` §First DC boot has the full account and
    the resulting (torn-frame) evidence.

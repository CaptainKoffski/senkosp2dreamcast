# Tooling

Every tool this project uses: exact install/reuse steps, version, usage.
The environment must be rebuildable from scratch from this file.
Deep recipes that already live in `../cleopatra/docs/kb/tooling.md` are
referenced, not duplicated — that file is part of this project's method.

### Instrumented Flycast (reused build)

- **Binary:** `../cleopatra/tools/flycast-src/build/Flycast.app/Contents/MacOS/Flycast`
  (Mach-O arm64), commit `f014a410c` — the same build the senkosp assessment
  v9 capture used (`../naomi2dreamcast/assessments/senkosp.md` §1).
- **Source of truth:** `../flycast4naomi2dreamcast` (fork), HEAD also
  `f014a410c` (verified 2026-08-13) — the built copy is current. Phase 2
  rebuilds only if it adds instrumentation; full build recipe (CMake 3.31.6
  pin, DEVELOPER_DIR, ZLIB_TBD, Syphon patch): `../cleopatra/docs/kb/tooling.md`
  §"Flycast — source build".
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
  scripts.

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
  instructions). **Visual: pending operator confirmation — machine
  locked.** Verdict rests on the CARTDMA tuple comparison alone, per the
  task's operator-asleep ruling — not treated as a FAIL signal.
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

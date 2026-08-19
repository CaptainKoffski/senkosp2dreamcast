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

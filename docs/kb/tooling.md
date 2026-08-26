# Tooling

Every tool this project uses: exact install/reuse steps, version, usage.
The environment must be rebuildable from scratch from this file.
Deep recipes that already live in `../cleopatra/docs/kb/tooling.md` are
referenced, not duplicated — that file is part of this project's method.

### Instrumented Flycast (reused build)

- **Binary:** `../cleopatra/tools/flycast-src/build/Flycast.app/Contents/MacOS/Flycast`
  (Mach-O arm64), `flycast-src` checkout commit `625425f72` (Phase 5 Task 2,
  rebuilt 2026-08-23 — see below). Originally the same build the senkosp
  assessment v9 capture used (`../naomi2dreamcast/assessments/senkosp.md` §1,
  then `f014a410c`).
- **Source of truth:** `../flycast4naomi2dreamcast` (fork), HEAD `79182301d`
  (Phase 5 Task 2, 2026-08-23) — the built copy is current. Phase 2 rebuilds
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
  **Phase 5 Task 2 fork commit:** `79182301d` in `flycast4naomi2dreamcast`
  (canonical) — `gd_crc32()` (CRC-32/IEEE, same variant as the shim's
  `shim_crc32`/Python `zlib.crc32`) plus two `cartlog()` call sites in
  `gdromv3.cpp`: `GDPIO` after the PIO refill's `libGDR_ReadSector` (before
  `read_params.start_sector += sector_count`) and `GDDMA` after
  `DmaBuffer::fill`'s `libGDR_ReadSector` (before `params.start_sector +=
  count`) — drive-truth CRCs for `scripts/check_stream_crc.py` (Task 3).
  Both format strings end in `\n`, one deliberate departure from the task
  brief's snippet: every existing `cartlog()` call site in this fork
  (`naomi.cpp`, `maple_if.cpp`) terminates its line with `\n` (`cartlog()`
  is a raw `vfprintf`, no auto-newline — `cartlog.cpp`), and Task 3's
  parser reads `GDPIO`/`GDDMA` as one record per line; the brief's snippet
  omitted `\n` on both calls, which the smoke leg confirms would have run
  every record together into a single unparseable line.
  **No push this task** (task instruction: do not push either repo), so
  this checkout (`flycast-src`) could not `git pull --ff-only` from
  `origin` the way the drift note above prescribes. Instead: added the
  canonical fork as a scratch local remote inside `flycast-src`
  (`git remote add phase5canon /Users/captainkoffski/AntigravityProjects/flycast4naomi2dreamcast`),
  `git fetch phase5canon master`, `git cherry-pick 79182301d` (clean,
  `flycast-src` had no local commits ahead), then removed the scratch
  remote. Result: `flycast-src` HEAD `625425f72` — same author, message,
  and diff as `79182301d`, different SHA (different commit timestamp/tree
  parent chain from the independent checkout) rather than a true
  fast-forward. Rebuilt at `625425f72`, not `79182301d` — record this
  commit pairing, not just one SHA, if reconciling the two checkouts later.
  **Rebuild (2026-08-23):** `export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer`
  then `cmake --build build -j"$(sysctl -n hw.ncpu)"` in `flycast-src`
  (incremental — the configured tree already existed, no reconfigure
  needed), exit 0, only pre-existing linker warnings (`-s` obsolete,
  duplicate static libs, deployment-target mismatches on `libomp`/`libpng`
  dylibs — unrelated to this change). **Smoke leg** (`phase5/probe-smoke`,
  one-call foreground pattern, 60 s unattended attract, killed by PID):
  `captures/phase5/probe-smoke.log` — 241 `GDPIO|GDDMA` lines (129 `GDPIO`,
  112 `GDDMA`), all 241 correctly newline-terminated one-record-per-line
  (verified: 0 lines match two tags concatenated, 0 lines contain a tag
  without starting with it).
  **Phase 5 Task 5 fork commits:** `8b1d45f2e` (sampler) + `a13662ff1`
  (`INSTRUMENTATION.md` row) in `flycast4naomi2dreamcast` (canonical) —
  `cartlog_texerr_tick()` (`core/hw/naomi/naomi.cpp`), a baseline-and-compare
  sampler of senkosp's texture-error classifier cells (`docs/kb/
  phase5-hardware.md` §Texture-error handler: `0x8c1a20a0`/`0x8c1a20a8`/
  `0x8c1a2098`), called from `core/hw/pvr/pvr_regs.cpp`'s existing
  `STARTRENDER`-write `cartlog()` site and throttled to every 64th call.
  Emits `TEXERR idx= code= d98=` once at first sample, then only on change —
  same discipline as `cartlog_shimwatch2`. No checkout drift (`git fetch &&
  git log --oneline HEAD..origin/master` clean in both checkouts before this
  edit). Cherry-picked into `flycast-src` the same way as Task 2 (scratch
  local remote `phase5canon`, `git cherry-pick`, remote removed after): both
  commits landed clean as `875aea8ff` + `b4763c1e8`. **Rebuild (2026-08-23,
  same session):** `export DEVELOPER_DIR=/Applications/Xcode.app/Contents/
  Developer` then `cmake --build build -j"$(sysctl -n hw.ncpu)"` — exit 0,
  same pre-existing linker warnings as the Task 2 rebuild above, nothing new.
  **Instrument control leg** (`phase5/instrument-ctl`, `docs/kb/
  phase5-hardware.md` §Instrument control test has the full account): all
  three `check_stream_crc.py` CHECKs PASS, 8 `TEXERR` lines (baseline +
  legitimate live-surface-count churn + one `code=6` line that turned out to
  be a second, independently-captured occurrence of the texture-error hang,
  fully unattended — see that section), 16,958 `PVRW STARTRENDER` over
  ~296 s (57.3/s, above both cited Phase 4 reference rates — no perf
  collapse).
  **`make`/`DEFS` gotcha found this task, recorded for every future
  diagnostic or release rebuild in this repo:** `shims/Makefile`'s `CFLAGS +=
  $(DEFS)` is not a tracked prerequisite of `$(B)/shim.bin` — `make`'s
  mtime-based check cannot see that command-line flags changed between
  invocations, only that the sources didn't, so a `shim.bin` built with
  different (or no) `DEFS` earlier in a session can be silently reused by a
  later `make gdi DEFS=...`, exit 0, "Nothing to be done", and ship a build
  that does **not** actually have the requested flags compiled in. Caught by
  `strings shims/build/shim.bin | grep SHIMCRC` coming back empty right
  after a "successful" diagnostic build. **Always `make clean` before a
  flag-sensitive build, or verify with `strings`/`nm` that the requested
  macro actually compiled in** — the make exit code proves nothing here.
  **Phase 5 Task 6 fork commits:** `167661363` (one-shot TEXERR
  auto-savestate) + `afc25186f` (`INSTRUMENTATION.md` row) in
  `flycast4naomi2dreamcast` (canonical). `cartlog_texerr_tick()`
  (`core/hw/naomi/naomi.cpp`, emu thread) now arms a one-shot latch
  (`g_texerrSavePending`/`g_texerrSaveCode`, file-scope `std::atomic`) on the
  classifier-cell `0x8c1a20a8`'s 0->nonzero transition, independent of the
  existing print-throttle statics. It does **not** call `dc_savestate()`
  itself: `emu.stop()` (`core/emulator.cpp`) joins the emu thread's own
  `std::async` result via `checkStatus(true)`, which self-join-deadlocks if
  called from the thread being joined — the same reason every existing
  savestate call site (`gui.cpp` hotkey/menu, `gui_saveState()`) runs from
  the SDL/render thread, never the emu thread. New function
  `cartlog_texerr_save_poll()` is called once per frame from
  `mainui_rend_frame()` (`core/ui/mainui.cpp`, confirmed the "Flycast-rend"
  thread by `ThreadName` in `mainui_loop()`); on a pending flag it runs
  `emu.stop(); dc_savestate(0); emu.start();` — the exact sequence
  `gui_saveState(stopRestart=true)` already uses for the `AutoSaveState`
  path (`core/ui/gui.cpp:1635`) — and emits
  `TEXERRSAVE code=<hex> slot=0 <path>` (or `TEXERRSAVE FAILED code=<hex>
  reason=<...>` if `dc_savestateAllowed()` is false or the sequence throws
  `FlycastException`). Index 0 (no user-configured `SavestatePath`) resolves
  through `hostfs::getSavestatePath(0, true)` to
  `~/Library/Application Support/Flycast/data/<contentbasename>.state` —
  same location the Phase 3 canary-snapshot already established (`senkosp.state`,
  §Phase 3: RAM snapshot above); the poll function queries that exact path
  before saving and logs it, rather than reconstructing/guessing it. No
  checkout drift (`git fetch && git log --oneline HEAD..origin/master` clean
  in both checkouts before this edit). Cherry-picked into `flycast-src` the
  same way as Tasks 2/5 (scratch local remote `phase5canon`, `git
  cherry-pick`, remote removed after): both commits landed clean as
  `631e7b9d6` + `c3d0c8451`. **Rebuild:** `export
  DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer` then `cmake
  --build build -j"$(sysctl -n hw.ncpu)"` — exit 0, same pre-existing linker
  warnings as prior rebuilds, nothing new.
  **Sanity leg** (`phase5/task6-sanity`, one-call foreground pattern, 90 s
  unattended attract, `-config Debug:SerialConsoleEnabled=yes`, killed by
  PID): `captures/phase5/task6-sanity.log` — 108,988 lines; 5 `TEXERR`
  lines (cold-start baseline + 4 legitimate live-surface-count changes,
  `code=00000000` throughout — same healthy signature as the Task 5 control
  leg's first samples), 0 `TEXERRSAVE` lines (expected — the trigger
  condition, `code` 0->nonzero, never occurred on this healthy leg; the
  latch logic itself was verified by code read, not by a forced firing, per
  this task's scope). `check_stream_crc.py` — all three CHECKs PASS
  (`shimcrc_match`: 60 records/0 mismatches; `gdread_match`: 256
  verified/4 lowfad/0 mismatches; `coverage_nonzero`: shim=60, drive=260).
  No `abort|crash|signal|disconnected|fatal` in the `.stdout.log`. Build
  confirmed healthy before the soak campaign (docs/kb/phase5-hardware.md
  §Repro campaign has the per-leg soak table).
  **Phase 5 fix-scoping fork commit:** `10de83124` (ARENAHW texture-arena
  high-water walker: `cartlog_arena_tick()` in `core/hw/naomi/naomi.cpp`,
  called from the `STARTRENDER` write path in `core/hw/pvr/pvr_regs.cpp`
  next to `cartlog_texerr_tick()`; `INSTRUMENTATION.md` row in the same
  commit) in `flycast4naomi2dreamcast` (canonical). Cherry-picked into
  `flycast-src` the same way as Tasks 2/5/6 (scratch local remote
  `phase5canon`, removed after) as `b5a275a11`; rebuilt with the same
  `cmake --build build -j"$(sysctl -n hw.ncpu)"` recipe — exit 0, same
  pre-existing linker warnings only. Validated on the Naomi-profile smoke
  leg `phase5/arenahw-smoke` (docs/kb/phase5-hardware.md §High-water
  measurement). The walker is passive and always-on-when-cartlog: any
  future instrumented leg (either profile) keeps emitting `ARENAHW`
  running-max lines for free.
  **Phase 5 fix-scoping local tools:** `scripts/decode_pvr_vq.py` (pure
  stdlib GBIX/PVRT VQ→PNG decoder; usage
  `python3 scripts/decode_pvr_vq.py senkosp.dat <offset-hex> <out.png>`;
  outputs are ROM-derived — keep under gitignored `captures/`). Fixed
  2026-08-24: the codebook read started 16 B late (32-byte read of the
  16-byte `PVRT` header); control-tested after the fix against
  `/FONT.PAK`'s glyph sheet (clean A–Z/0–9 grid — see
  `docs/kb/phase5-hardware.md` §Fix scoping correction note).
  `scripts/list_pak_textures.py` (added 2026-08-24): lists the ISO root
  (`python3 scripts/list_pak_textures.py senkosp.dat`) or the `PVRT`
  textures inside one file (`… senkosp.dat STAGE08.PAK`) with absolute
  dat offsets ready for the decoder.
  **Option-2 fix tools (2026-08-24):** `tools/pyenv` — venv created with
  `python3 -m venv tools/pyenv && tools/pyenv/bin/pip install numpy`
  (numpy 2.5.2, Homebrew python 3.14.3; gitignored under `/tools/`).
  `scripts/shrink_vq.py` (run as
  `tools/pyenv/bin/python scripts/shrink_vq.py`) re-encodes the four
  STAGE08 textures at 512×512 into `build/texpatch/` (gitignored,
  deterministic — fixed k-means seed); `scripts/make_gdi.py` splices
  them at mastering time (md5-guarded both sides), `--no-texpatch` for
  the unpatched reference build. `decode_pvr_vq.py` gained an importable
  `decode()` (CLI unchanged, refactor verified byte-identical on a
  stage08 decode). The flat
  `.dat` is an ISO9660 image: PVD at `.dat 0x808000`, file mapping
  `dat_off = (LBA − 40904) × 2048` — walk recipe and file inventory in
  `docs/kb/phase5-hardware.md` §Fix scoping.
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
`DisasmEntry`, `FindRefsTo`, `WhichFunc`, `ListPoolWords`, `ExportToXML`,
`CallTree` (recursive caller tree following direct and pool-word computed
calls; added 2026-08-26 for the arena free-path recon; DB mutation note:
the 2026-08-26 recon also force-disassembled the scene-code windows
`0x8c1592xx–0x8c159axx`, `0x8c0b5b90–e8`, `0x8c087270–0x8c087830` — same
monotonic-additions caveat as the Task 4 spans).

**Savestate post-mortem (2026-08-26):** `scripts/texerrsave_postmortem.py`
— pure-python (stdlib) offline attribution of every VRAM texture-arena
block in a TEXERRSAVE Flycast savestate to its source texture on the
disc (RZIP-container decompress, RAM/VRAM location by content anchoring,
arena list walk, byte-exact match against all TXTR records + all
LZSS-decompressed PKTX entries). Run:
`tools/pyenv/bin/python3 scripts/texerrsave_postmortem.py [state] [dat]`.
No installs needed; the LZSS decoder semantics are documented in
`phase5-hardware.md` §Ghidra + savestate recon.

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
| `phase4/attract1.log`(`+.stdout.log`) | 14,349 | 516 KB | **Task 11 boot-detours-only leg** — diagnostic build, MAPLE-BASE + the 18 maple pool repoints + the five boot detours live, MAPLE-KICK-HOOK **off**. 345 `MB` transactions (the Naomi count exactly), 0 `System reset requested` (Task 10's reboot loop gone — the I/O-board error path never fires), 0 `CART off`: the game stops at the *unserviced steady engine*, which is where the JVS enumeration lives. The leg that justified wiring MAPLE-KICK-HOOK in Task 11. `docs/kb/phase4-conversion.md` §Attract. |
| `phase4/attract2.log`(`+.stdout.log`) | 38,930 | 2.0 MB | **Task 11 first leg with MAPLE-KICK-HOOK** — enumeration completes, game streams and renders. |
| `phase4/attract3.log`(`+.stdout.log`) | 171,140 | 5.0 MB | **Task 11 reproduction** of `attract2` — 83 cart streams, 0 errors. |
| `phase4/attract4.log`(`+.stdout.log`) | 441,550 | 12 MB | **Task 11 long leg** — 14,336 maple transactions serviced, 89 cart streams, service heartbeats climbing to the end. |
| `phase4/attract5-interp.log`(`+.stdout.log`) | 294 PCSAMPLEs | 8.7 MB | **Task 11 interpreter-mode diagnostic attempt** — `-config config:Dynarec.Enabled=no` to enable the fork's `PCSAMPLE`/busy-spin detector (interpreter-only, `sh4_interpreter.cpp:53-70`). Useless at this stage: in ~290 s the interpreter never got past the loader's 1.5 MB raw-ATA cart read, so all 294 samples are loader/KOS PCs. Kept per the never-delete-a-leg rule; the lesson is that interpreter-mode PC sampling is not affordable after the handoff. |
| `phase4/attract6.log`(`+.stdout.log`) | 166,560 | 5.0 MB | **Task 11 skip-diagnostic leg** — adds the `MIE skip` tripwire (a reply whose recv address is out of RAM range would be a silent stall). 0 skips; recv addresses `0cff9f60`/`0cff3f60` = the Naomi double buffer, relocated. |
| `phase4/attract7.log`(`+.stdout.log`) | 306,010 | 9.0 MB | **Task 11 maple-DMA-interrupt experiment** — a real pattern-3 maple DMA fired after each service so Holly raises `holly_MAPLE_DMA` (ISTNRM bit 12, which the game enables in IML4NRM). Same handshake, same 89-stream sequence, no observable difference → residual risk 1 closed and the experiment reverted. |
| `phase4/attract8.log`(`+.stdout.log`) | 97,685 | 3.0 MB | **Task 11 render-evidence leg** — plain service, killed by PID after ~6 min. 5,537 frames rendered post-handoff, 1,383 display lists > 4 KB (real geometry, first at 63% into the leg), AICA ARM sound driver booted (`CLEO-ARMRST … ram0=ea00003e`). |
| `phase4/attract9-release.stdout.log` | — | 695 B | **Task 11, no leg.** The same Flycast dynarec VMEM `Verify Failed` startup flake `entry1` hit; the emulator never opened the disc. Kept per the never-delete-a-leg rule. |
| `phase4/attract10-release.log`(`+.stdout.log`) | 205,514 | 6.0 MB | **Task 11 release-configuration leg (criterion 1 evidence)** — committed defaults, no guest serial. Post-handoff: **12,739 frames rendered, 8,353 display lists > 4 KB, 0 `MDODMA` from any game PC** (every maple access landed in the mirror), 0 resets. `docs/kb/phase4-conversion.md` §Attract. |
| `phase4/attract11-shot.log`(`+.stdout.log`) | 179,569 | 4.9 MB | **Task 11 screenshot leg** — release configuration, unattended, no input, `FLYCAST_SHOT=docs/kb/img/phase4-dc-attract.png FLYCAST_SHOT_EVERY=100000` + one `kill -USR1` at ~2.5 min for the on-demand grab (headless GL readback, no macOS screen-capture permission — `gui_dumpFramebuffer`, fork `core/ui/gui.cpp:510-545`; the Task 8 precedent). The PNG is senkosp's attract DEMONSTRATION with `FREE PLAY` on screen. 11,009 frames rendered post-handoff, 0 game-PC `MDODMA`. `docs/kb/phase4-conversion.md` §Attract. |
| `phase4/steady1.log`(`+.stdout.log`) | 348,937 | 12 MB | **Task 12 first leg with LIVE DC pads** — diagnostic build, unattended, input-free (operator AFK by design: an idle pad is the control that proves the real-pad path did not disturb attract). 345 boot transactions, 14,336 maple services, 15,202 frames, 8,822 display lists > 4 KB, 89 cart streams (`attract4`/`attract7`'s 89 — same attract sequence). One change-gated `IN` line, `crc=00000022` = the captured idle frame's own checksum, recomputed at runtime. 0 `EE WR`, 0 tripwires, 0 resets. **13,283 GetConditions per port, exactly equal, every reply `outlen=10` (DATATRF) — zero retries**; every post-handoff `MDODMA` PC is a shim symbol. `docs/kb/phase4-conversion.md` §Steady input. |
| `phase4/steady2.log`(`+.stdout.log`) | 137,324 | 5.0 MB | **Task 12 reproduction** of `steady1` with `hdrA`/`hdrB` (the raw maple reply headers) added to the `IN` trace, so an operator leg can split "pad not read" from "mapping wrong" without opening the cartlog. `IN p1=00000000 p2=00000000 crc=00000022 hdrA=03230008 hdrB=03634008` — both low bytes `08` = DATATRF, i.e. **both** DC ports answer in Flycast's DC profile. 345 boot transactions, 0 errors. |
| `phase4/steady3-release.log`(`+.stdout.log`) | 248,729 | 9.0 MB | **Task 12 release-configuration + screenshot leg** — committed defaults, no guest serial (stdout carries zero shim output), unattended, `FLYCAST_SHOT=docs/kb/img/phase4-dc-steady.png` + one `kill -USR1`. 10,169 frames post-handoff, 5,784 lists > 4 KB, 0 resets, 10,219 GetConditions per port all `outlen=10`, **0 `MDODMA` from any game PC**. The PNG shows `PRESS 1P OR 2P START BUTTON` and `FREE PLAY` — free play survived the sub-`0x03` rewrite to a RAM copy. `docs/kb/phase4-conversion.md` §Steady input. |
| `phase4/steady4.log`(`+.stdout.log`) | 137,000+ | 5.7 MB | **Task 12 review-fix regression leg** — diagnostic build after the opposed-direction mutual exclusion went into `dc_cond_to_pressed`. Idle behaviour byte-for-byte unchanged: the same single `IN p1=00000000 p2=00000000 crc=00000022 hdrA=03230008 hdrB=03634008` line, 345 boot transactions, enumeration ending at sub-`0x33`, 6,719 GetConditions per port all `outlen=10`, 0 `EE WR`, 0 tripwires, 0 resets, and every post-handoff `MDODMA` PC a shim symbol. `docs/kb/phase4-conversion.md` §Steady input. |
| `phase4/teststatic1.log`(`+.stdout.log`) | 79,138 | 3.0 MB | **Task 13 regression leg** — diagnostic build with the test-mode `mie_poll` branch added, but a NORMAL (no-combo) boot, so `SHIM_STATE[0]==0` and the `else` path (Task 12's unmodified line) runs. `boot: MAIN image`, `IN p1=00000000 p2=00000000 crc=00000022 hdrA=03230008 hdrB=03634008`, 345 boot transactions, 0 tripwires, 49 `CART off=` streams, 5,594 `TAEND` (frames), 2,820 GetConditions per port equal (0 retries), every post-handoff `MDODMA` PC a shim symbol. Byte-for-byte the same idle line as `steady1`/`steady4`. `docs/kb/phase4-conversion.md` §Test menu. |
| `phase4/testboot-diag1.log`(`+.stdout.log`) | 163,903 | 6.0 MB | **Task 13 test-image diagnostic leg** — transient `LOADER_FORCE_TEST_BOOT=1` (reverted before commit, `LOADER_SERIAL` precedent), no operator. `boot combo: TEST image`, all 60 test-image patches applied (`patch table: … applied: test`), `SHIM_STATE[0]==1` live (`IN` line under the test-mode branch, `crc=00000022`, unchanged from idle-normal-mode), 345 (`0x159`) boot transactions — same count as the main image — 6,656 (`0x1a00`) steady maple services, 0 tripwires, 0 resets in the whole cartlog, 12,982 `TAEND`, 6,492 GetConditions per port equal. `FLYCAST_SHOT` + one `kill -USR1` mid-leg captured `docs/kb/img/phase4-dc-testmenu.png` — senkosp's own **GAME TEST MENU**, instruction line `SELECT WITH SERVICE BUTTON AND PRESS TEST BUTTON`, confirming the Start→Test/A→Service mapping from the game's own on-screen text. `docs/kb/phase4-conversion.md` §Test menu. |
| `phase4/play1.log`(`+.stdout.log`) | 803,325 | 24 MB | **Operator session 2026-08-23, criterion 2** — 1P full match, all controls exercised, free play confirmed. One intermittent finding: game-rendered `ERROR !! TEXTURE LOAD ERROR !` after a won match (once in ~6 sessions), screenshot `docs/kb/img/phase4-dc-texerror.png`, carried to Phase 5. `docs/kb/phase4-conversion.md` §Operator legs → `play1`, §Texture-error hang. |
| `phase4/play1-revert.log`(`+.stdout.log`) | 434,467 | 14 MB | **Operator session 2026-08-23, criterion 5 support** — relaunch/EEPROM-revert check (session-only EEPROM as designed). `docs/kb/phase4-conversion.md` §Operator legs → `play1-revert`. |
| `phase4/play2p.log`(`+.stdout.log`) | 592,106 | 20 MB | **Operator session 2026-08-23, criterion 3** — 2P entry, play, mid-game Start-join on port B, all confirmed. `docs/kb/phase4-conversion.md` §Operator legs → `play2p`. |
| `phase4/testmenu-rt.log`(`+.stdout.log`) | 703,202 | 23 MB | **Operator session 2026-08-23, criterion 4** — combo boot → GAME TEST MENU → navigate → controls test screen → difficulty change → `SYSTEM MENU EXIT` → full console reboot → attract; the round-trip leg the Task 13 report left pending. `docs/kb/phase4-conversion.md` §Operator legs → `testmenu-rt`. |
| `phase4/shimwatch-play.log` | 458,748 | 17 MB | **Operator session 2026-08-23** — played a full match + test-menu visit + quit under the `SHIMWATCH2`-emitting fork; upgrades `shim_home_clean` PARTIAL → full CLEAN (0 `SHIMWATCH2` across match + testmenu + quit). `docs/kb/phase4-conversion.md` §Shim home (V2s). |
| `phase4/pc2-testmenu.log` | 139,759 | 7.0 MB | **Operator session 2026-08-23** — interpreter mode, ~60 s test-menu visit, no changes, exit; the `eeprom_write_seen` negative control (0 sub-`0x0b` events, confirms the BIOS-only attribution). Dynarec restored to `yes` after. `docs/kb/phase4-conversion.md` §Operator legs → `pc2-testmenu`. |
| `phase4/final.log`(`+.stdout.log`) | 193,248 | 6.5 MB | **Task 14 gate-closure verification leg** — release configuration, unattended, no input, ~155 s (`scripts/capture_dc_leg.sh phase4/final`, killed by PID per the plan-amendment kill pattern — the plan's `pkill -9 -f "flycast-src.*Flycast"` does not match the real process name). 0 `System reset requested`, 0 `SHIMERR`, 16,177 `MDODMA enter` events (561 pre-handoff at known loader/KOS PCs, 15,616 post-handoff at known shim PCs — zero at any other PC), 17,682 `TAEND` (frames), boot ladder reaches `MMUCRWR pc=8c02d630` (MAIN image's own MMU enable). `docs/kb/phase4-conversion.md` §Gate audit → `phase4/final`. |

Both prior "Pending" operator legs (`phase4/pc2-testmenu`, `phase4/shimwatch-play`)
were captured in the 2026-08-23 operator session, along with `play1`,
`play1-revert`, `play2p` and `testmenu-rt` above — see the OPS finalization
entries in `.superpowers/sdd/2026-08-22-phase4-conversion/progress.md` for
the session record.

A 45s scratchpad diagnostic capture (per-PC `MDODMA` `sp=` correlation,
`docs/kb/boot-binary.md` §SP — two stacks addendum's table) was written
outside `captures/` (session scratchpad, not primary data — its result is
fully recorded in that table) and is not part of this inventory.

### Phase 5 leg inventory

| Leg | Lines | Size | What it is |
|---|---|---|---|
| `phase5/probe-smoke.log`(`+.engine.bin`, `+.stdout.log`) | — | — | **Task 2 smoke leg** — 60 s unattended attract against the `GDPIO`/`GDDMA`-emitting fork. `docs/kb/tooling.md` §Instrumented Flycast has the full account. |
| `phase5/instrument-ctl.log`(`+.engine.bin`, `+.stdout.log`) | 367,518 | 12 MB | **Task 5 control leg** — diagnostic disc (`SHIM_SERIAL=1 SHIM_CRC=1`), unattended, ~296 s. All three `check_stream_crc.py` CHECKs PASS; 8 `TEXERR` lines including one `code=6` line that is a second, independently-captured occurrence of the texture-error hang (§Texture-error handler / §Instrument control test, `docs/kb/phase5-hardware.md`). Kept as primary data despite the mid-leg hang — same never-delete rule as every other capture. |
| `phase5/task6-sanity.log`(`+.engine.bin`, `+.stdout.log`) | 108,988 | 3.7 MB | **Task 6 sanity leg** — 90 s unattended attract against the auto-savestate fork. 5 `TEXERR` lines, all `code=00000000`; 0 `TEXERRSAVE`; all three CHECKs PASS. |
| `phase5/soak-1.log`(`+.engine.bin`, `+.stdout.log`) | 636,994 | 19 MB | **Task 6 soak leg — the hang capture.** 600 s unattended. `TEXERR idx=2 code=6 d98=0x54` at line 319,549, `TEXERRSAVE` at line 319,564; all three CHECKs PASS. Byte-identical to `instrument-ctl.log` for all 319,549 lines up to the marker (`head -319549 | md5` = `19cf13c13575cb7908b398fde0ddb833` for both) — the hang is deterministic on the attract path. |
| `phase5/soak-1-texerr.state` | — | 8,554,748 B | **The savestate at the hang** (md5 `1d3a3c6d943ec93292732f17dd7704d4`), preserved out of Flycast's overwrite-prone slot dir. RZip; carve recipe in §Phase 5: DC-profile RAM snapshot from a TEXERR savestate. ROM-derived — gitignored, never committed. |

### Phase 5: DC-profile RAM snapshot from a TEXERR savestate (Task 7, 2026-08-23)

Carving `captures/phase5/soak-1-texerr.state` (the one-shot auto-savestate
from `docs/kb/phase5-hardware.md` §Auto-savestate capture) into a 16 MB main-RAM
image. **No new script** — this is a one-off adaptation of the Phase 3 recipe
above (§Phase 3: RAM snapshot), recorded verbatim instead of committed, per
Task 7's "lazier sufficient option" ruling. Nothing new was installed; python3
stdlib (`struct`, `zlib`) only. Outputs go to a session scratchpad — the
inflated stream and the RAM image are ROM-derived and are **never** committed.

Three deltas from the Phase 3 recipe, all load-bearing:

1. **Format is RZip, not zstd.** `xxd -l 64` shows `FLYSAVE1`, then the magic
   `#RZIPv\x01#` at file offset `0x18`. Same `magic + u32 maxChunkSize +
   u64 totalSize + u32-length-prefixed zlib chunks` layout as Phase 3
   (`.../core/archive/rzip.cpp`), so `find(b"#RZIPv\x01#")` still works and no
   `zstd` tool is needed. Sanity: `totalSize` must equal the
   `N[SAVESTATE]: Saved state to ... size <N>` value in the leg's `.stdout.log`
   (here 28,106,129), and the chunk loop must consume the file to its last byte.
2. **DC profile = 16 MB at phys `0x0c000000`**, not Naomi's 32 MB. Address →
   image offset is `(addr & 0x1fffffff) - 0x0c000000`.
3. **Two markers must agree** before trusting the base — one alone is not
   enough here, because the `syMalloc` banner appears **twice** in the stream
   (the second is a data copy at RAM offset `0xe3c980`). Use the banner *and*
   the boot-image head:

```python
import struct, zlib
b   = open("captures/phase5/soak-1-texerr.state","rb").read()
o   = b.find(b"#RZIPv\x01#") + 8
mx, total = struct.unpack_from("<IQ", b, o); o += 12
out = bytearray()
while len(out) < total:                       # 27 chunks -> 28,106,129 B
    (n,) = struct.unpack_from("<I", b, o); o += 4
    out += zlib.decompress(b[o:o+n]);        o += n

dat  = open("senkosp.dat","rb").read(0x200000)
base = out.find(b"\nsyMalloc Ver 2.01") - 0x15c980      # 0xacc414
assert base == out.find(dat[0:0x1000]) - 0x20000        # same base from the boot-image head
ram  = out[base:base+16*1024*1024]                      # base+16M lands 6,525 B short of EOF
```

**Carve control tests** (run all four before analysing; Phase 3's list with one
DC-specific correction):

| Test | DC expectation |
|---|---|
| `ram[0x15c980:0x15c992]` == `b"\nsyMalloc Ver 2.01"` | pass |
| `ram[0x15b2c4:...]` == GDFS error strings (`E00000009:`, `Illegal File Name`) | pass |
| `ram[0x20000:0x21000] == senkosp.dat[0:0x1000]` | pass |
| `ram[0x85b00:0x85bb4] == senkosp.dat[0x65b00:0x65bb4]` | **fails on exactly one word** — `0x8c085b50` reads `0x4028cb8d` vs the `.dat`'s `0x4028cb8e`. That *is* the heap-top relocation patch (`scripts/reloc_patchset.json`, `dat_offset 0x65b50`). On a DC-profile image this test passes only in that corrected form; a byte-identical result would mean the patch did **not** take. |

Whole-image sanity for this capture: 1,350 of 1,515,512 bytes of the loaded
image span differ from the `.dat` (Phase 3's Naomi snapshot: 907) — the extra
diffs are this port's patched cells plus initialized-data writes.

Reading cells afterwards is plain `struct.unpack_from("<I", ram, off(addr))`;
the decompiler side used the already-committed harness unchanged
(`scripts/ghidra/run.sh script Decomp.java 0x8c03c46e` etc.).

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
  **One-call foreground pattern, 600 s hard cap (Task 6):** the agent
  Bash tool clamps a leg's execution to 600000 ms regardless of a larger
  requested `timeout`, so a `sleep 600` leg's own kill tail
  (`kill -USR1`/`sleep 5`/`kill -9`/`wait`) can get cut by the tool's own
  SIGTERM (exit 143) — captures completed fine when this happened, but keep
  unattended-leg `sleep` ≤ ~550 s under this pattern, or split launch/kill
  across two tool calls for longer legs (full account:
  `docs/kb/phase5-hardware.md` §Repro campaign (Task 6)).
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

### Clean-checkout build proof (Task 14, gate criterion 7, 2026-08-23)

`make gdi` needs **six** gitignored inputs, not just the three `.gitignore`
groups (`senkosp.dat`, `bios/`, the `*.7z` donor) that earlier tasks called
out — this task's clean clone hit two undocumented ones on the first two
build attempts, both now fixed by symlink and recorded here so a future
fresh checkout doesn't have to rediscover them the same way:

- `tools/ram-snapshot.bin` (34 MB, §Phase 3: RAM snapshot) — `loader/Makefile`
  reads it directly for the `bios_data.bin` kernel-slice recipe.
- `loader/splash.png` (12 KB, BIOS-rendered logo frame, gitignored same
  category as the BIOS ROM) — `loader/Makefile`'s `splash.bin` target.
- `captures/phase4/pc2.log` (14 MB, §Phase 4 leg inventory, Task 1's
  PC-capture leg) — `shims/Makefile` extracts the MIE reply blobs
  (`mie_blobs.c`) from it at build time; a fresh clone without it fails with
  a clear `make` error naming the missing file, not a silent bad build.

  **This one is more fragile than the other five.** It is not a dump that
  `dd` can regenerate — it is an emulator capture tied to instrumented-fork
  commit `0d55a1812`'s log format, and a re-captured leg is not guaranteed
  byte-identical (the blob extractor only asserts per-class byte-stability
  within a leg, not across legs). If this file is ever lost, "regenerable"
  means rebuilding that fork commit and re-running a Naomi leg, not a
  one-line `dd` — preserve it deliberately.

Recipe, run against a clone that is **not** a sibling of `../cleopatra` (a
scratch directory), so the top-level `Makefile`'s `. ../cleopatra/tools/kos/
environ.sh` needs the same relative path to resolve — fixed with one
parent-directory symlink rather than editing the (tracked) Makefile:

```sh
git clone -b phase4-conversion /Users/captainkoffski/AntigravityProjects/senkosp2dreamcast <scratch>/senkosp-clean
ln -sfn /Users/captainkoffski/AntigravityProjects/cleopatra <scratch>/cleopatra   # so ../cleopatra resolves
cd <scratch>/senkosp-clean
ln -sf /Users/captainkoffski/AntigravityProjects/senkosp2dreamcast/senkosp.dat senkosp.dat
mkdir -p bios/naomi tools captures/phase4
ln -sf /Users/captainkoffski/AntigravityProjects/senkosp2dreamcast/bios/naomi/epr-21576h.ic27 bios/naomi/epr-21576h.ic27
ln -sf /Users/captainkoffski/AntigravityProjects/senkosp2dreamcast/tools/ram-snapshot.bin tools/ram-snapshot.bin
ln -sf "/Users/captainkoffski/AntigravityProjects/senkosp2dreamcast/[GDI] Dolphin Blue.7z" "[GDI] Dolphin Blue.7z"
ln -sf /Users/captainkoffski/AntigravityProjects/senkosp2dreamcast/loader/splash.png loader/splash.png
ln -sf /Users/captainkoffski/AntigravityProjects/senkosp2dreamcast/captures/phase4/pc2.log captures/phase4/pc2.log
source ../cleopatra/tools/kos/environ.sh && make gdi
```

Result: `exit=0` on the first attempt once all six were in place. Every
produced disc file (`build/track01.iso`, `track02.raw`, `track03.iso`,
`track04.iso`, `disc.gdi`) is md5-identical to the same-session main-checkout
`make gdi` output — full table: `docs/kb/phase4-conversion.md` §Gate audit →
Criterion 7. Symlinks (not copies) are deliberate: `senkosp.dat` alone is
251 MB, and nothing in the build reads these paths in a way that requires a
real copy (all are read-only inputs).

**`track04.iso`'s criterion-7 md5 is now stale (found Task 5, 2026-08-23).**
A plain `make clean && make gdi` release rebuild that same day reproduced
`track01.iso`/`track02.raw`/`track03.iso`/`disc.gdi` byte-identically to the
table above, but `track04.iso` came back `126e587e977315febaac0c833ed86777`,
not `89ccb3e02522a8bd802f762ee1f74a2f` — deterministic (two consecutive
clean rebuilds matched each other), not a flake. **Root cause empirically
isolated (fix round 1), not just inferred from the diff:** a single-variable
before/after rebuild of `shims/` alone (same toolchain, same `mie_blobs.c`
generation, no `DEFS` either time — only `shims/src/gd.c`'s content
changed) —
```
git checkout 3bb4d05 -- shims/src/gd.c && make -C shims clean && make -C shims
# shim.bin: 5896 B, md5 adce0a3702b701ec7eb41feb1f809eac
git checkout HEAD    -- shims/src/gd.c && make -C shims clean && make -C shims
# shim.bin: 5948 B, md5 035d3537024c0b39c7b7f0615cede0a7
```
reproduces exactly the Phase 4 5,896 B artifact pre-Task-1 and exactly
5,948 B (+52 B) with Task 1's `gd.c` restored — isolating the variable and
also confirming `shim_crc32()` (added **unconditionally** by Task 1's
`dc64fbb`; only its call site is `#if SHIM_CRC`-gated, not the function
itself) is **not** dead-code-eliminated at `-Os`, an assumption the first
pass of this note made silently and this measurement now confirms rather
than asserts. `shim.bin` embeds byte-for-byte into `1ST_READ.BIN` into
`track04.iso` (§GDI mastering below, unchanged deterministic steps), so this
+52 B at the shim layer fully accounts for the md5 divergence.
`docs/kb/phase5-hardware.md` §Instrument control test → Step 5 has the full
account, both md5s, and the working-tree restore-to-HEAD confirmation. The
table above is left as originally recorded (it is Phase 4's own
gate-closure evidence); treat only the four unaffected files as still-valid
reproducibility checks, and recapture `track04.iso`'s baseline before
relying on it again.

### Phase 5: F-zero PKTX repacker (Task 20, 2026-08-26)

`scripts/pktx_vq.py` — no new installs; runs on the existing
`tools/pyenv` (numpy) and reuses `shrink_vq.py`'s encoder +
`decode_pvr_vq.py`'s decoder. One command, fully offline:

```
tools/pyenv/bin/python3 scripts/pktx_vq.py        # ~40 min (58 k-means encodes)
tools/pyenv/bin/python3 scripts/make_gdi.py       # splices the manifest it wrote
```

Rewrites `build/texpatch/` WHOLESALE (portrait entries only — the
F-zero config; re-run `shrink_vq.py` instead to rebuild the old hero
shrink config). Previews + INDEX.txt land in
`captures/phase5/textures/portraits-vq/` (gitignored, ROM-derived).
Build record: `phase5-hardware.md` §F-zero build.

# Phase 1 (Foundation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the senkosp2dreamcast repo — KB skeleton, verified toolchain, `.dat` extraction, and proof the untouched game boots to attract in the instrumented Flycast — per the approved spec (`docs/superpowers/specs/2026-08-13-charter-phase1-foundation-design.md`, Part B).

**Architecture:** No game modifications in this phase. All work is repo scaffolding, tool verification with recorded steps, one ROM-format conversion (CHD → flat `.dat`), and an evidence-backed boot run. Sibling repos are referenced in place: `../cleopatra` (prior port, KB, built Flycast), `../naomi2dreamcast` (assessment + dat-extract), `../flycast4naomi2dreamcast` (fork source).

**Tech Stack:** git, zsh, Python 3 (stdlib), chdman/7zz/clang (already installed), the instrumented Flycast build at `../cleopatra/tools/flycast-src/build/` (commit `f014a410c`), Ghidra 12.1.2 (installed, not exercised this phase).

## Global Constraints

- **Never commit copyrighted bytes**: ROM, BIOS, disc images, `.dat`, `.chd`, `.gdi`, `.iso` stay gitignored. Before adding any binary file to git, run `git check-ignore -v <file>`; if it is game/BIOS data and NOT ignored, stop and fix `.gitignore` first. Game *screenshots* into `docs/kb/img/` are fine (established practice in `../cleopatra/docs/kb/img/` and `../naomi2dreamcast/assessments/evidence/`).
- **Every hardware/behavioral claim in KB docs carries a citation**; primary sources (emulator/MAME source, assessment sidecars) outrank wikis.
- **Every tool install or reuse is recorded** in `docs/kb/tooling.md` with version, exact steps, and gotchas.
- **Flycast launch gotchas (macOS, always apply):** absolute ROM path (relative fails — Flycast's CWD is not the repo); `defaults write com.flyinghead.Flycast ApplePersistenceIgnoreState -bool YES` once per session before launching; `-config config:rend.vsync=no` on every unattended launch (unfocused window deadlocks the emu thread without it); `pkill -9 -f "flycast-src.*Flycast"` before relaunching (a stale instance makes the next one fail SH4 vmem verify and never boot).
- **Paths:** repo root is `/Users/captainkoffski/AntigravityProjects/senkosp2dreamcast`. Run all commands from there unless a step says otherwise. `$SCRATCH` below means the session scratchpad directory (any writable temp dir outside the repo works).
- **Commits:** plain imperative subject (repo style, e.g. "Add project charter…"), body optional, and end every commit message with the `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` trailer.

---

### Task 1: Repo scaffolding — .gitignore, CLAUDE.md, KB skeleton

**Files:**
- Modify: `.gitignore`
- Create: `CLAUDE.md`
- Create: `docs/kb/00-status.md`
- Create: `docs/kb/game.md`
- Create: `docs/kb/port-playbook.md` (copied from `../cleopatra/docs/kb/port-playbook.md`)

**Interfaces:**
- Produces: `docs/kb/00-status.md` — the living status doc every later task appends to. `docs/kb/tooling.md` does NOT exist yet (Task 2 creates it with real content).

- [ ] **Step 1: Harden .gitignore**

Replace the current 2-line `.gitignore` with:

```gitignore
/roms/
/bios/
/tools/
*.dat
*.chd
*.gdi
*.iso
.DS_Store
._*
```

(`/tools/` is for future third-party clones/binaries, matching the Cleopatra convention. `._*` — AppleDouble sidecars — masqueraded as a deep boot bug in the Cleopatra port; keep them out of git too.)

- [ ] **Step 2: Verify the ignore rules actually fire**

Run: `git check-ignore roms/senkosp.zip bios/naomi.zip roms/senkosp/gdl-0038.chd .DS_Store ._test senkosp.dat && git status --short`
Expected: all six paths print (= ignored). `git status --short` shows only `.idea/` (user's IDE dir, leave it), `REQUIREMENTS.md`, and the files this task creates — no `roms/`, `bios/`, or `.DS_Store` entries.

- [ ] **Step 3: Write CLAUDE.md**

```markdown
# Senko no Ronde Special — Naomi → Dreamcast port

Port of the Sega Naomi GD-ROM game *Senko no Ronde Special* (`senkosp`,
GDL-0038, G.Rev 2006) to Sega Dreamcast by static binary conversion (no
source code), following the method proven by the Cleopatra Fortune Plus
port (`../cleopatra`).

- **Start here:** `docs/kb/00-status.md` — project state, strategy, next step.
- **Method:** `docs/kb/port-playbook.md` — the six-phase playbook (carried
  over from the Cleopatra port; gates enforced, spec + plan per phase).
- **Knowledge base:** `docs/kb/` — game notes, tooling records, findings.
- **Specs & plans:** `docs/superpowers/specs/`, `docs/superpowers/plans/`.
- **ROM:** `roms/` (gitignored — never commit, never upload):
  `senkosp.zip` + `senkosp/gdl-0038.chd`; flat decrypted image `senkosp.dat`
  at repo root (gitignored, regenerable — see `docs/kb/tooling.md`).
- **BIOS:** `bios/` (gitignored).
- **Sibling repos:**
  - `../cleopatra` — the prior Naomi→DC port: KB, reusable loader/shim
    code, and the **built instrumented Flycast**
    (`tools/flycast-src/build/Flycast.app/Contents/MacOS/Flycast`).
  - `../naomi2dreamcast` — Naomi library assessment; this game's report:
    `assessments/senkosp.md`. Also the `.dat` toolset
    (`tools/dat-extract/`).
  - `../flycast4naomi2dreamcast` — the instrumented Flycast fork (source
    of truth for emulator instrumentation).

Rules: every hardware claim in the KB carries a citation (primary sources
outrank wikis); record every tool install in `docs/kb/tooling.md`; never
commit copyrighted bytes (ROMs, BIOS, disc images, extracted assets).
```

- [ ] **Step 4: Copy the playbook**

Run: `cp ../cleopatra/docs/kb/port-playbook.md docs/kb/port-playbook.md`

Then edit the copied file's intro line ("Bring this file to the next port's repo.") — append a provenance note right after the first paragraph:

```markdown
> Carried into `senkosp2dreamcast` 2026-08-13 from
> `../cleopatra/docs/kb/port-playbook.md` (verbatim below this note).
> Deep-reference paths like `atomiswave-method.md` refer to
> `../cleopatra/docs/kb/`.
```

- [ ] **Step 5: Write docs/kb/00-status.md**

```markdown
# Project status

**Updated:** 2026-08-13 (Phase 1 Foundation — in progress)

## What this is

Static binary conversion of *Senko no Ronde Special* (Sega Naomi GD-ROM,
`senkosp`, GDL-0038) to Sega Dreamcast: patch the Naomi-specific hardware
touchpoints in the game binary (DIMM/cart reads → GD-ROM streaming, MIE/JVS
input → Maple controllers, EEPROM/settings → native-path stubs, free-play
baked in) and boot it from a GDI via a custom loader.
Charter + Phase 1 spec:
`docs/superpowers/specs/2026-08-13-charter-phase1-foundation-design.md`.

## Decisions

- Target: real Dreamcast hardware (GDEMU-class ODE). Emulators are dev
  tools, not the goal.
- Method: the six-phase playbook from the Cleopatra Fortune Plus port
  (`docs/kb/port-playbook.md`), gates enforced, spec + plan per phase.
- Central technical problem (from `../naomi2dreamcast/assessments/senkosp.md`,
  v9 2026-08-09): assets park above DC caps — main-RAM cart-DMA high-water
  33,453,344 (33.4 MB) vs DC's 16 MB (content only 5.85 MB); VRAM address
  extent 11.9 MB vs 8 MB (content 4.79 MB incl. double framebuffer). Phase 2
  measures which streams land high; Phase 3 decides relocation vs streaming
  retarget. ARAM expected to fit (content 1.35 MB / 2 MB).
- Asset cutting/compression is a last resort (REQUIREMENTS.md).

## Phases

1. **Foundation — IN PROGRESS** (repo, KB, tooling records, .dat, boot verification)
2. Instrumented analysis (streaming/input/memory ground truth; the high-address DMA map)
3. Reverse engineering (touchpoint addresses + patch plan; relocation strategy)
4. Conversion (loader + shim + patch table → bootable GDI)
5. Real-hardware testing & fit
6. Safety tripwires & release

## Phase 1 checklist

- [ ] Repo scaffolding: .gitignore, CLAUDE.md, KB skeleton, playbook carried over
- [ ] tooling.md — every tool verified + recorded (Flycast build, Ghidra, dat-extract)
- [ ] senkosp.dat extracted from CHD, carve sanity-checked vs assessment
- [ ] Boot verification: untouched game reaches attract in Flycast naomigd profile (screenshot in KB)
- [ ] Exit audit + fresh-agent test

## Key facts so far

- `senkosp` = the 2006 arcade back-port of the X360 Rev.X set; only member
  of its family; GD-ROM GDL-0038, 237.7 MB, machine `naomigd`, ROT0;
  export/English PIC `317-5123-COM`. Assessment: 91.0 (S), rank 1
  (`../naomi2dreamcast/assessments/senkosp.md`).
- Boots and runs fully (attract/demo cycle) under the instrumented Flycast
  fork at commit `f014a410c` — assessment v9 capture, 2026-08-09.
- Controls: stick + 5 buttons (M/S/A + Barrage/C + OverDrive) → DC pad has
  6, one to spare.
- Streaming is modest: 26.6 MiB per 600 s attract, steady 2.3 MB/min.
- Guts flags to watch in Phase 3: `eeprom_bios`, `serial`, `rtc` (RTC is
  new vs Cleopatra — 3 MMIO refs).

## Next step

Finish Phase 1 per `docs/superpowers/plans/2026-08-13-phase1-foundation.md`.
```

- [ ] **Step 6: Write docs/kb/game.md**

```markdown
# senkosp — game dump notes

Identity facts sourced from `../naomi2dreamcast/assessments/senkosp.md`
(battery v9, 2026-08-09) unless noted.

| | |
|---|---|
| Title (header) | `SENKO NO RONDE SP` |
| Set | `senkosp` — own family, no parent, no clones (MAME `naomi.cpp` @59e7c0b, `ROM_START(senkosp)` lines 8920–8931) |
| Maker / year | G.Rev, 2006 (JP arcade 2006-08-01) |
| Media | GD-ROM GDL-0038, 237.7 MB, machine `naomigd`, horizontal ROT0 |
| Security PIC | `317-5123-COM` (export/common — English-capable build) |
| Carve (assessment guts) | base `0x8c020000`, entry `0x8c021000`, code 1,515,512 B, 4,012 functions |
| SDK stack | Kunoichi2 Library for NAOMI 2.07, Ninja2 2.01.011, "sd2 for DC" 2.50.17, CRI ADX |
| Controls | 8-way stick + 5 buttons (M/S/C/A/OD) |

## Our dump

- `roms/senkosp/gdl-0038.chd` — MAME CHD v5, 241 MB,
  md5 `bc9dd736cf7b49ae20efb6cf32d5f8a5` — byte-identical to the copy the
  assessment battery ran (`../naomi2dreamcast/naomi/senkosp/`, md5 verified
  2026-08-13).
- `roms/senkosp.zip` — the set zip (security PICs + metadata).

## Parsed .dat header

(Filled by Phase 1 Task 3 from `parse_header.py` output.)
```

- [ ] **Step 7: Verify tree + commit**

Run: `ls docs/kb/ && git status --short`
Expected: `00-status.md  game.md  port-playbook.md` listed; status shows only the new/modified files above (plus the pre-existing `.idea/`, `REQUIREMENTS.md`).

```bash
git add .gitignore CLAUDE.md docs/kb/
git commit -m "Phase 1: repo scaffolding — CLAUDE.md, KB skeleton, hardened .gitignore

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Toolchain verification + tooling.md

**Files:**
- Create: `docs/kb/tooling.md`

**Interfaces:**
- Consumes: KB skeleton from Task 1.
- Produces: `docs/kb/tooling.md` with the verified Flycast binary path (`FLYCAST_BIN` below) that Tasks 3–4 use. `FLYCAST_BIN = /Users/captainkoffski/AntigravityProjects/cleopatra/tools/flycast-src/build/Flycast.app/Contents/MacOS/Flycast`.

- [ ] **Step 1: Verify each tool exists and capture versions**

Run each; record actual output for the doc:

```bash
# Instrumented Flycast (built during Cleopatra/assessment work — reused, not rebuilt)
ls -la ../cleopatra/tools/flycast-src/build/Flycast.app/Contents/MacOS/Flycast
file ../cleopatra/tools/flycast-src/build/Flycast.app/Contents/MacOS/Flycast   # expect: Mach-O 64-bit executable arm64
git -C ../cleopatra/tools/flycast-src rev-parse --short HEAD                    # expect: f014a410c
git -C ../flycast4naomi2dreamcast rev-parse --short HEAD                        # expect: f014a410c (same — build is current vs fork HEAD)
# Naomi BIOS installed for Flycast
ls ~/Library/Application\ Support/Flycast/data/naomi.zip                        # expect: exists
# dat-extract prerequisites
chdman --help 2>&1 | head -1                                                    # expect: chdman - MAME Compressed Hunks of Data (CHD) manager <version>
/opt/homebrew/bin/7zz | head -2                                                 # expect: 7-Zip banner
clang --version | head -1                                                       # expect: Apple clang version …
# Ghidra (recorded reuse; not exercised until Phase 3)
ls ../cleopatra/tools/ghidra_12.1.2_PUBLIC/support/analyzeHeadless              # expect: exists
```

If the two `rev-parse` outputs differ, STOP and note it in `tooling.md` — Tasks 3–4 still work (the binary matches what the assessment used), but Phase 2 must rebuild from the fork before instrumenting.

Note on the spec's "build it on this machine": a build at exactly the fork's HEAD already exists on this machine (produced during the assessment campaign). Verifying binary == fork HEAD and recording the recipe pointer satisfies the spec's intent (working verified emulator + reproducible steps); rebuilding would produce the same artifact and is deferred to Phase 2, which changes the source anyway.

- [ ] **Step 2: Write docs/kb/tooling.md**

```markdown
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

(Filled by Task 3 — exact extraction commands + validation output.)
```

- [ ] **Step 3: Commit**

```bash
git add docs/kb/tooling.md
git commit -m "Phase 1: tooling.md — verified Flycast build, BIOS, dat-extract prereqs, Ghidra reuse

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Extract senkosp.dat + carve sanity check

**Files:**
- Create: `senkosp.dat` (repo root, gitignored — verify before creating)
- Modify: `docs/kb/tooling.md` (§senkosp.dat)
- Modify: `docs/kb/game.md` (§Parsed .dat header)

**Interfaces:**
- Consumes: dat-extract prereqs verified in Task 2.
- Produces: `senkosp.dat` at repo root — the input for Phase 3 Ghidra work; parsed header facts in `game.md` that Phase 3 relies on (base `0x8c020000`, entry `0x8c021000`).

- [ ] **Step 1: Confirm the .dat will be ignored by git**

Run: `git check-ignore -v senkosp.dat`
Expected: matches the `*.dat` rule. If not, STOP — fix `.gitignore` first.

- [ ] **Step 2: Run the extraction**

```bash
cd ../naomi2dreamcast/tools/dat-extract
./chd2dat.sh senkosp
```

Expected: one line `OK  senkosp  <- <pic>.pic  <N> bytes -> …/out/senkosp.dat` (tool prints title-parse success; non-zero exit + diagnostic = failure). The tool reads `../naomi2dreamcast/naomi/senkosp/` — byte-identical to our `roms/` copy (md5 `bc9dd736cf7b49ae20efb6cf32d5f8a5` both sides, recorded in `game.md`).

- [ ] **Step 3: Copy into this repo and validate the header**

```bash
cd /Users/captainkoffski/AntigravityProjects/senkosp2dreamcast
cp ../naomi2dreamcast/tools/dat-extract/out/senkosp.dat senkosp.dat
head -c 16 senkosp.dat   # expect the string NAOMI in the first bytes
python3 ../cleopatra/scripts/parse_header.py senkosp.dat
```

Expected from `parse_header.py`: `NAOMI` magic; title `SENKO NO RONDE SP`; a sane load table. Cross-check against the assessment's guts: carve base `0x8c020000`, entry `0x8c021000` (`../naomi2dreamcast/assessments/senkosp.md` §6). If title/entry disagree with the assessment, STOP — wrong PIC or corrupted extraction; re-run Step 2 and compare the tool's log.

- [ ] **Step 4: Record in the KB**

Fill `docs/kb/tooling.md` §"senkosp.dat" with the exact commands from Steps 2–3 plus the `OK` line and the byte size. Fill `docs/kb/game.md` §"Parsed .dat header" with `parse_header.py`'s actual output (magic, title, load-table entries, entrypoint) and the line: "Matches assessment guts: base `0x8c020000`, entry `0x8c021000` ✓".

- [ ] **Step 5: Verify nothing copyrighted is staged, then commit**

Run: `git status --short` — `senkosp.dat` must NOT appear.

```bash
git add docs/kb/tooling.md docs/kb/game.md
git commit -m "Phase 1: extract senkosp.dat (chd2dat), carve verified vs assessment

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Boot verification — the Phase 1 gate

**Files:**
- Create: `docs/kb/img/senkosp-title.png`, `docs/kb/img/senkosp-attract.png`
- Modify: `docs/kb/00-status.md` (checklist + gate evidence)

**Interfaces:**
- Consumes: `FLYCAST_BIN` (Task 2), romset at `roms/` (layout Flycast wants: `senkosp.zip` beside `senkosp/gdl-0038.chd`).
- Produces: gate evidence (screenshot committed to KB) — the go/no-go for Phase 2.

- [ ] **Step 1: Launch the untouched game in the Naomi GD profile**

```bash
: "${SCRATCH:=$(mktemp -d)}"; echo "$SCRATCH"   # session scratchpad preferred; any temp dir works
pkill -9 -f "flycast-src.*Flycast" 2>/dev/null || true
defaults write com.flyinghead.Flycast ApplePersistenceIgnoreState -bool YES
FLYCAST_BIN="/Users/captainkoffski/AntigravityProjects/cleopatra/tools/flycast-src/build/Flycast.app/Contents/MacOS/Flycast"
FLYCAST_SHOT="$SCRATCH/senkosp-shot.png" FLYCAST_SHOT_EVERY=600 \
  "$FLYCAST_BIN" -config config:rend.vsync=no \
  "/Users/captainkoffski/AntigravityProjects/senkosp2dreamcast/roms/senkosp.zip" &
```

Timeline from the assessment (§3): BIOS→game handoff ~20 s, story text card ~60 s, SP title logo ~121 s, DEMONSTRATION fight ~182 s.

- [ ] **Step 2: Grab evidence at title and demo timestamps**

```bash
FLYPID=$(pgrep -f "flycast-src.*Flycast" | head -1)   # re-derive — steps may run in separate shells
sleep 125 && kill -USR1 "$FLYPID" && sleep 2 && cp "$SCRATCH/senkosp-shot.png" "$SCRATCH/senkosp-title.png"
sleep 60  && kill -USR1 "$FLYPID" && sleep 2 && cp "$SCRATCH/senkosp-shot.png" "$SCRATCH/senkosp-attract.png"
kill "$FLYPID"
```

Read both PNGs (they are images — view them). Expected: the SP title logo and/or the in-game DEMONSTRATION fight (matching the assessment's `evidence/senkosp/shot-121s.png` / `shot-182s.png`). A black frame = load/transition sampled — re-grab with `kill -USR1` at a slightly different moment before concluding anything is wrong.

- [ ] **Step 3: Control-test only if it will not boot**

If no game frames appear by ~180 s: run the known-good Cleopatra `.dat` through the SAME binary (`"$FLYCAST_BIN" -config config:rend.vsync=no "/Users/captainkoffski/AntigravityProjects/cleopatra/Cleopatra Fortune Plus.dat"`, attract by ~40 s). Cleopatra boots + senkosp doesn't → problem is senkosp-side (romset path/layout); neither boots → environment (BIOS path, stale instance, persistence modal). Diagnose per `../cleopatra/docs/kb/tooling.md` launch gotchas before touching anything else.

- [ ] **Step 4: Commit the evidence**

Copy the good grabs to `docs/kb/img/senkosp-title.png` and `docs/kb/img/senkosp-attract.png`. In `docs/kb/00-status.md`: tick the boot-verification checklist item and add under "Key facts so far": "Boot verification 2026-08-13: untouched romset reaches title + demo in the reused fork build (`f014a410c`) on this machine — `docs/kb/img/senkosp-{title,attract}.png`."

```bash
git add docs/kb/img/ docs/kb/00-status.md
git commit -m "Phase 1: boot verification — untouched senkosp reaches attract in Flycast naomigd profile

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Status finalization, exit audit, fresh-agent test

**Files:**
- Modify: `docs/kb/00-status.md`

**Interfaces:**
- Consumes: all prior task outputs.
- Produces: Phase 1 marked DONE; the gate record Phase 2's spec will cite.

- [ ] **Step 1: Finalize 00-status.md**

Tick all five Phase-1 checklist items (each is now true). Change the header line to `**Updated:** <today> (Phase 1 Foundation — DONE; gate green)`. Change "Phases" line 1 to `1. **Foundation — DONE <today>** (…)`. Replace "Next step" with:

```markdown
## Next step

Phase 2 — instrumented analysis. Brainstorm + spec first (superpowers loop,
per the playbook cadence): capture the cart-streaming map with DMA
destinations (the >16 MB main-RAM placements are the port's central
problem), RAM/VRAM/ARAM write-truth, and the input map, using the
instrumented fork (`../flycast4naomi2dreamcast`, build recipe in
`docs/kb/tooling.md`). The assessment sidecar + capture scripts in
`../naomi2dreamcast/tools/assess/` are the starting harness.
```

- [ ] **Step 2: Exit audit — repo hygiene**

```bash
git status --short          # expect: only .idea/ and REQUIREMENTS.md (untracked user files)
git log --oneline           # expect: init + spec + 4 Phase-1 commits
find . \( -name '._*' -o -name '.DS_Store' \) -not -path './.git/*'   # any hit must pass git check-ignore
git ls-files | grep -iE '\.(dat|chd|gdi|iso|zip|bin)$' || echo CLEAN   # expect: CLEAN
```

The last command is the copyright tripwire: no game/BIOS binary may be tracked. (`docs/kb/img/*.png` screenshots are expected and fine.)

- [ ] **Step 3: Fresh-agent test**

Dispatch a clean-context subagent (Agent tool, `general-purpose`) with EXACTLY this prompt and nothing else:

> Read /Users/captainkoffski/AntigravityProjects/senkosp2dreamcast/CLAUDE.md and then /Users/captainkoffski/AntigravityProjects/senkosp2dreamcast/docs/kb/00-status.md. From ONLY those two files, answer: (1) What is this project? (2) What state is it in? (3) What is the next step? Answer in three short paragraphs.

PASS = the reply correctly states: (1) static binary conversion port of Senko no Ronde Special / senkosp from Naomi to Dreamcast; (2) Phase 1 Foundation complete, gate green (boot verified in emulator); (3) Phase 2 instrumented analysis, starting with its spec. FAIL on any of the three → fix the doc that under-communicated, re-dispatch, repeat until PASS.

- [ ] **Step 4: Ask the user to confirm REQUIREMENTS.md disposition, then commit**

`REQUIREMENTS.md` is untracked (user-authored). Ask whether to commit it alongside the status update (it is the project's origin document; committing is recommended) or leave it untracked. Then:

```bash
git add docs/kb/00-status.md    # + REQUIREMENTS.md if approved
git commit -m "Phase 1 complete: gate green — status finalized, exit audit + fresh-agent test passed

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Gate check (end of phase)

All three spec gate conditions, each pointing at its evidence:

1. **Untouched game runs in the arcade profile** → `docs/kb/img/senkosp-{title,attract}.png` (Task 4).
2. **Toolchain recorded** → `docs/kb/tooling.md` (Tasks 2–3).
3. **`.dat` carve verified** → `docs/kb/game.md` §Parsed .dat header matches assessment guts (Task 3).

Green = Phase 2 may start (its own brainstorm → spec → plan).

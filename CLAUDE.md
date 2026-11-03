# Senko no Ronde Special — Naomi → Dreamcast port

Port of the Sega Naomi GD-ROM game *Senko no Ronde Special* (`senkosp`,
GDL-0038, G.Rev 2006) to Sega Dreamcast by static binary conversion (no
source code), following the method proven by the Cleopatra Fortune Plus
port (`../cleopatra`).

- **Start here:** `docs/kb/00-status.md` — project state, strategy, next step.
- **Method:** `../naomi2dreamcast/docs/kb/port-playbook.md` — the port
  playbook, maintained in the umbrella repo (gates enforced, spec + plan per
  phase); `docs/kb/port-playbook.md` here is just the pointer.
- **Knowledge base:** `docs/kb/` — game notes, tooling records, findings.
- **Specs & plans:** `docs/superpowers/specs/`, `docs/superpowers/plans/`.
- **ROM:** `roms/` (gitignored — never commit, never upload):
  `senkosp.zip` + `senkosp/gdl-0038.chd`; flat decrypted image `senkosp.dat`
  at repo root (gitignored, regenerable — see `docs/kb/tooling.md`).
- **BIOS:** `bios/` (gitignored).
- **Kit (build-required):** `kit/` — git submodule
  `naomi-dc-port-kit` (github.com/CaptainKoffski/naomi-dc-port-kit; run
  `git submodule update --init` after cloning): the game-agnostic shims,
  loader, mastering, capture and test tooling this port builds against. What
  this port supplies to it (the contract) is `kit/README.md`. The gate for any
  kit change: `scripts/gate_hashes.sh check gd` and `check cd` against
  `docs/kb/kit-gate-baseline.txt` (silent = byte-identical).
- **Sibling repos:**
  - `../naomi2dreamcast` — Naomi library assessment; this game's report:
    `assessments/senkosp.md`. Also the `.dat` toolset
    (`tools/dat-extract/`). **Build-required sibling.**
  - `../flycast4naomi2dreamcast` — the instrumented Flycast fork (source
    of truth for emulator instrumentation); the built app this project
    runs is `build/Flycast.app` inside it. **Build-required sibling.**
  - `../cleopatra` — the prior Naomi→DC port: KB and method lineage only.
    Since 2026-09-21 the build does not reach into it (KOS lives at
    `tools/kos` in this repo — see `docs/kb/tooling.md` §Decoupling).

Rules: every hardware claim in the KB carries a citation (primary sources
outrank wikis); record every tool install in `docs/kb/tooling.md`; never
commit copyrighted bytes (ROMs, BIOS, disc images, extracted assets).

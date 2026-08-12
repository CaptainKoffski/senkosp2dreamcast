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

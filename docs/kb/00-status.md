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

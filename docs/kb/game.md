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

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

`python3 ../cleopatra/scripts/parse_header.py senkosp.dat` (2026-08-13):

```
- **File:** `senkosp.dat` (251,342,848 bytes)
- **Magic:** `NAOMI`
- **Publisher:** G.REV,LTD.
- **Title (Japan):** SENKO NO RONDE SP
- **Title (USA):** SENKO NO RONDE SP
- **Title (Export):** SENKO NO RONDE SP
- **Title (Korea):** SENKO NO RONDE SP
- **Title (Australia):** SENKO NO RONDE SP
- **Title (Reserved1):** SAMPLE GAME RESERVED 1
- **Title (Reserved2):** SAMPLE GAME RESERVED 2
- **Title (Reserved3):** SAMPLE GAME RESERVED 3
- **Main load entries:**
  - ROM 0x00000000 -> RAM 0x8c020000, 0x171ff8 bytes
- **Test load entries:**
  - ROM 0x00171ff8 -> RAM 0x8c020000, 0x4dc40 bytes
- **Entrypoint (main):** 0x8c021000
- **Entrypoint (test):** 0x8c021000
```

Matches assessment guts: base `0x8c020000`, entry `0x8c021000` ✓

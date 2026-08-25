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

## Character ↔ PAK mapping and texture budgets (2026-08-25)

Each playable character owns six PAKs (`PnnA`–`PnnF`, color/loadout
variants with near-identical texture inventories); bosses are single
PAKs. Mapping identified by the operator from decoded texture contact
sheets (`captures/phase5/textures/chars/`, gitignored — ROM-derived;
scratchpad `charsheets.py`, VQ-mipmap top-level decode). VRAM = sum of
`PVRT datalen − 8` over the A-variant PAK (the allocation the game
computes: `texobj+0x18 == datalen − 8`, phase5-hardware.md §Step 8).

| PAK | Character | Tex | VRAM (B) | Livery on sheet |
|---|---|---|---|---|
| P01 | B. Changpo | 12 | 184,448 | pink/lavender |
| P02 | Mika Mikli | 9 | 129,120 | navy/white, "VENTUNO" |
| P03 | Cuilan | 10 | 173,504 | teal/cream, foil panels |
| P04 | Fabian | 8 | 109,312 | red/black, cyan accents |
| P05 | Lili Levinas | 6 | 226,688 | violet, green-glow strips |
| P06 | S. Sakurako | 9 | 180,992 | gray urban-camo |
| P07 | Ernula | 15 | 309,408 | yellow/tan, white rabbits |
| P08 | Karel Werfel | 7 | 150,944 | khaki/green, "AZUREUS POW" |
| P09 | boss | 8 | 267,616 | industrial battleship; only character PAK with 512² textures |
| P10/P11 | boss (level-8 = P11 + STAGE10) | 4 | 51,904 | **byte-identical PAKs** |

Notes established alongside (all measured from `senkosp.dat`):

- Character textures are **VQ + mipmap** (`dt=04`): mip chain stored
  smallest-first immediately after the 2048 B codebook; the full-res
  index plane starts at `(w·h/4 − 1)/3 + 1` bytes into the index
  stream; every sampled record carries 10 trailing pad bytes (offset
  fixed empirically by a smoothness-scan after the end-anchored guess
  decoded to speckle). The 1024² arena offenders are plain VQ (`dt=03`);
  no character texture exceeds 256² except P09's three 512².
- `scripts/list_pak_textures.py` priced `dt=04` as raw 16bpp (~6× high)
  until commit 55b6cf5; the stage-PAK census in phase5-hardware.md used
  only formats where the old and new pricing agree — re-verified
  unchanged.
- Worst-case 2P texture pair is therefore **Ernula vs Ernula** (P07
  mirror, ≈618,816 B if fully resident) — the right character pick for
  stage-8 worst-case verification legs (Task 18); lightest is Fabian
  vs Fabian (≈218,624 B). Pair spread ≈400 KB, small next to the
  STAGE08 atlas the fix targets.

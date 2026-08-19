# Phase 2 measurements — senkosp

## Coverage checklist (gate)

Roster (from character-select screen, enumerated in-game 2026-08-19):
- [x] Mika Mikli (Rounder: Ventuno II) — leg char-mika
- [x] Baek Changpo (Rounder: Citronette) — leg char-baek (beginner run with novice=yes)
- [x] Cuilan (Rounder: Orangette) — leg char-cuilan
- [x] Fabian the Fastman (Rounder: Graphride) — leg char-fabian
- [x] Sakurako Sanjo (Rounder: Triad) — leg char-sakurako
- [x] Lili Levinas (Rounder: Brinsta) — leg char-lili (beginner stage 1 win-lose-win, then stage 2 losses + score attack loss)
- [x] Ernula (Rounder: Castrato) — leg char-ernula
- [x] Karel Werfel (Rounder: Azureus) — leg char-karel

## Mode/option coverage

Game has no stage select; per-credit choices are character, cartridge (loadout), novice yes/no, and mode. Arenas/opponents covered implicitly across character ladder (user report, 2026-08-19):
- [x] Beginner mode (char-mika: progressed to stage 2 — won 2 rounds on stage 1, lost 2 on stage 2)
- [x] Score attack mode (char-mika: one run, loss)
- [x] Game over + continue screen (char-mika: full continue → game-over sequence, continue timer waited out fully)
- [x] Novice mode (covered inside leg char-baek — novice=yes on beginner credit, 2026-08-19)
- [x] Draw / timer-out round (char-sakurako: timer-out on beginner first round)

Note: Cartridge (battle-style) loadouts and outfits varied across legs; both have no enumerated lists in-game to gate on. Outfits are cosmetic variants, not exhaustively covered (known non-gated variation). Stages: 8 stages total (enumerated from 2P stage-select screen, 2026-08-19).

## Standing rows

- [x] Novice-mode run (covered inside leg char-baek — novice=yes on the beginner credit, 2026-08-19; other legs ran novice=no, so both variants are captured)
- [x] Test-menu leg (Task 6: legs testmenu + testmenu2, full walk with EEPROM ops observed; setting flipped: Advertise Sound OFF → exit persists → re-enter confirmed → restored ON, 2026-08-19)
- [x] Input leg (Task 4)
- [x] 2P stage sweep (leg 2p-stages: all 8 stages played one round each; EXTENDED above-16-MB map floor from 0x145bd20 to 0x1244c20 — 2,191,616 B (~2.1 MB) new territory; merged high-water unchanged at 0x1fe7520)

## Capture incidents

- char-fabian (leg 1): startup crash (transient SH4 vmem "Verify Failed" — documented Cleopatra gotcha); one relaunch; merged data clean.
- char-sakurako (leg 1): startup crash (transient SH4 vmem "Verify Failed"); one relaunch; merged data clean.
- char-lili (leg 1): aborted by host-side PyCharm/terminal hang; partial log deleted, leg re-captured cleanly from scratch; merged data contains only the clean re-run.
- testmenu (leg 1): service-menu RAM TEST hangs the instrumented fork; partial log kept as evidence (48,130 lines); full walk re-captured in testmenu2 with RAM test deliberately skipped — Phase 3 curiosity, recorded not interpreted.

## Test-menu device evidence (raw)

Leg testmenu2 (full walk, RAM test skipped):
- MIERESP subcommand counts: sub=01 ×9, sub=03 ×9, sub=0b ×32 (EEPROM ops), sub=13 ×9, sub=15 ×12,483, sub=17 ×81, sub=21 ×21, sub=27 ×12,408, sub=31 ×12, sub=33 ×6,868, sub=ff ×3.
- SERIALPOKE lines: 0 (no serial writes).
- Game-code HW pokes (HWR/HWW from game PC range): 0 (no RTC/SCIF MMIO observed). (PC filter applied by the fork's probe, not the parser.)
- PIO bytes: 0x334b70 (vs. 0x172538 typical boot).

---

## Region verdicts (write-truth, all legs merged)

Source: final full parse, 2026-08-19
(`python3 scripts/parse_cartlog.py captures/*.log --attract-leg attract --csv docs/kb/cart-streaming-map.csv --hw-report`,
`exit=0`, all six CHECKs PASS — see cart-streaming-map.md
§Checks). "Full campaign" pairs mirror the assessment's own field pairing:
main is `nz` / `nz_above16m` (no separate content mask); vram is
`(content_below8m+content_above8m) + 2×fb_bytes` / raw `nz_above8m`; aram is
`(content_below2m+content_above2m)` / raw `nz_above2m` — matching how the v9
assessment (`../naomi2dreamcast/assessments/senkosp.md` §4) paired its own
scored and informational figures.

| Region | Attract-only (assessment v9) | Full campaign | DC cap | Verdict |
|---|---|---|---|---|
| main nz / above-16m | 5,850,229 / 4,266,292 | 13,014,015 / 11,428,714 | 16 MB | **Fits as content**: 13,014,015 / 16,777,216 = u 0.776 (up from v9's 0.349, more than double the content volume, but still under the cap). The 11,428,714 B currently sitting above the 16 MB line is not excess volume — it is 5 hard-coded streaming corridors (cart-streaming-map.md, above-16m map) that need **relocation for 5 streams**, not asset cutting. |
| vram content+2×fb / above-8m | 4,786,768 / 3,017,926 | 7,239,988 / 5,496,597 | 8 MB | **Still fits, tight**: 7,239,988 / 8,388,608 = u 0.863 (up from v9's 0.571 — real matches touch materially more VRAM than the 2-fight attract demo). Raw address-peak watermark also grew 11,897,553 → 14,571,136 B (+2,673,583 B / +2.55 MB). No further headroom under this cap; a Phase 3 relocation plan should not assume slack here. |
| aram content / above-2m | 1,348,105 / 0 | 1,348,121 / 6,291,456* | 2 MB | **Expected: still fits, confirmed**: content volume is unchanged from v9 (1,348,121 vs 1,348,105, +16 B noise; u 0.6428 both, identical to 5 significant figures). *The raw (content-unmasked) `nz_above2m` jumped from 0 to 6,291,456 B — real gameplay music drives AICA reverb/delay work buffers across the full 8 MB AICA window (every 256 KB bucket from 2 MB–8 MB reads fully saturated in the raw histogram) — but content-masking correctly excludes that as non-asset fill, so the scored figure barely moved. Not a relocation concern. |

Above-cap bucket maps (256 KB buckets, offsets — the relocation source map
for Phase 3):

```
main above-cap buckets (256 KB each): #73(0x1240000)=236334, #74(0x1280000)=255773, #75(0x12c0000)=255092, #76(0x1300000)=257652, #77(0x1340000)=257788, #78(0x1380000)=255437, #79(0x13c0000)=261341, #80(0x1400000)=259013, #81(0x1440000)=257876, #82(0x1480000)=260757, #83(0x14c0000)=256194, #84(0x1500000)=261326, #85(0x1540000)=259360, #86(0x1580000)=258596, #87(0x15c0000)=260880, #88(0x1600000)=260946, #89(0x1640000)=258054, #90(0x1680000)=258820, #91(0x16c0000)=260970, #92(0x1700000)=258529, #93(0x1740000)=259016, #94(0x1780000)=258181, #95(0x17c0000)=258302, #96(0x1800000)=256813, #97(0x1840000)=258136, #98(0x1880000)=260658, #99(0x18c0000)=260603, #100(0x1900000)=260834, #101(0x1940000)=259916, #102(0x1980000)=255971, #103(0x19c0000)=260644, #104(0x1a00000)=261768, #105(0x1a40000)=258505, #106(0x1a80000)=261898, #107(0x1ac0000)=261530, #108(0x1b00000)=261530, #109(0x1b40000)=260775, #110(0x1b80000)=261653, #111(0x1bc0000)=256362, #112(0x1c00000)=258147, #113(0x1c40000)=257113, #114(0x1c80000)=256571, #115(0x1cc0000)=255952, #116(0x1d00000)=256014, #117(0x1d40000)=212693, #118(0x1d80000)=84496, #119(0x1dc0000)=128090, #120(0x1e00000)=53, #121(0x1e40000)=235914, #122(0x1e80000)=116968, #123(0x1ec0000)=126242, #124(0x1f00000)=123703, #127(0x1fc0000)=18804

vram above-cap buckets (256 KB each): #32(0x800000)=262128, #33(0x840000)=254131, #34(0x880000)=209204, #35(0x8c0000)=240627, #36(0x900000)=252718, #37(0x940000)=246008, #38(0x980000)=256343, #39(0x9c0000)=260647, #40(0xa00000)=252282, #41(0xa40000)=259338, #42(0xa80000)=262129, #43(0xac0000)=261668, #44(0xb00000)=261733, #45(0xb40000)=248766, #46(0xb80000)=258190, #47(0xbc0000)=250440, #48(0xc00000)=253782, #49(0xc40000)=252854, #50(0xc80000)=261218, #51(0xcc0000)=258461, #52(0xd00000)=261912, #53(0xd40000)=256376, #54(0xd80000)=258804, #55(0xdc0000)=147246

aram above-cap buckets (256 KB each): #8(0x200000)=262144, #9(0x240000)=262144, #10(0x280000)=262144, #11(0x2c0000)=262144, #12(0x300000)=262144, #13(0x340000)=262144, #14(0x380000)=262144, #15(0x3c0000)=262144, #16(0x400000)=262144, #17(0x440000)=262144, #18(0x480000)=262144, #19(0x4c0000)=262144, #20(0x500000)=262144, #21(0x540000)=262144, #22(0x580000)=262144, #23(0x5c0000)=262144, #24(0x600000)=262144, #25(0x640000)=262144, #26(0x680000)=262144, #27(0x6c0000)=262144, #28(0x700000)=262144, #29(0x740000)=262144, #30(0x780000)=262144, #31(0x7c0000)=262144
```

**Corrected 2026-08-19 (review fix):** all three `*HIST` bucket arrays are
raw diff histograms — `hist[b]++` fires unconditionally on every nonzero
byte, **before** any content-masking check, in all three profile functions
(`../flycast4naomi2dreamcast/core/hw/naomi/naomi.cpp`): aram
`hist[b]++` at line 216, ahead of the `dup`-gated content increment at
lines 217–220; vram `hist[b]++` at line 269, ahead of the `in_fb`
framebuffer-exclusion check at lines 271–278
(`bool in_fb = …; if (in_fb) … else { cnz++; … }`). The FB/dup masking changes only the separate
`content_*` scalars printed on the `VRAMPROFILE`/`ARAMPROFILE` line — it
never touches the bucket arrays. `main` has no masking logic at all
(`naomi.cpp:292-299`: "Raw diff only — no ARAM-style content dedup"; no
`content_*` fields exist for main), so for `main` specifically the raw
`nz`-based bucket list *is* the content figure — there is nothing separate
to mask against.

So: the **`main` bucket list is the write-truth relocation source map**
(content actually observed above cap, bucket by bucket — main's `nz` and
"content" are the same measure by construction). The **`vram` and `aram`
bucket lists are both raw, unmasked histograms**, not content:
- `vram`: raw `nz_above8m` is 5,496,597 B vs. FB-masked `content_above8m`
  4,962,056 B — a 534,541 B gap. That gap is framebuffer scan-out traffic
  sitting inside the buckets above, which the scoring already budgets
  separately as `2×fb_bytes` (region-verdicts table above). Do not treat
  the vram bucket list as a pure relocation source map without subtracting
  known FB regions (`VRAMREGS fb_w_sof1/fb_w_sof2/fb_r_sof1`, logged
  alongside) — at face value it would double-count ~535 KB of framebuffer
  bytes as relocatable assets.
- `aram`: raw `nz_above2m` is 6,291,456 B vs. content `content_above2m` of
  16 B (per the note above, this is reverb/delay work-buffer traffic, not
  asset content). The content-side aram bucket list is empty
  (`content_above2m` is 16 B, below the 256 KB bucket granularity, so it
  does not surface a bucket row at all). Do not read the aram bucket list
  as a relocation source map — it is the informational raw counter,
  included here only because the brief's format calls for the full
  above-cap bucket dump per region.

## Device verdicts (runtime)

Evidence cross-checked against raw logs directly
(`grep -c "^SERIALPOKE" captures/*.log`, `grep -hc "^HW[RW]" captures/*.log`, and per-leg `MIERESP sub=` counts),
not only the parser's aggregate — across **all 14 legs**, not just testmenu2.

| Device | Evidence | Verdict |
|---|---|---|
| serial (SCIF) | `SERIALPOKE` lines: 0 in every one of the 14 legs (grep-verified per file, including testmenu2 and testmenu). `HW[RW]` game-code MMIO pokes tagged `scif` (`0x1FE80000`–`0x1FE8FFFF`): 0 — in fact **all** `HW[RW]` pokes across the entire campaign total 0 (parser `--hw-report` emits zero device lines; `grep -hc "^HW[RW]" captures/*.log` is 0 for every log). | Not touched, in any leg, at runtime. No shim needed on current evidence — Phase 3 confirms via disassembly whether the SCIF touchpoints are dead code or compile-time gated before deciding to ignore vs. stub. |
| RTC | Same `HW[RW]`=0 evidence — the `rtc` tag (`0x00710000`–`0x0071FFFF`) never fires in any leg, including `testmenu`/`testmenu2` where a BIOS-path RTC read would most plausibly appear (service menu date/time or bookkeeping screens). | Not touched at runtime anywhere in this campaign. The static guts scan flagged 3 MMIO refs (`00-status.md` "Key facts"); none fire dynamically through any UI path reached here (attract, all 8 characters, 2P stage sweep, full test-menu walk, input leg). Phase 3 traces those 3 refs directly — dead/conditional code, not a runtime gap in coverage. |
| watchdog | No separate watchdog device tag in the fork's probe (`DEVICES` covers rtc/scif only); since total `HW[RW]` pokes across the whole campaign are 0, no watchdog-range poke exists either, by construction (0 pokes to any address ⇒ 0 to a watchdog address). | Not touched — same 0/0 evidence as serial/RTC. Nothing further to add from this instrument; not expected to need a shim. |
| EEPROM | `MIERESP sub=0x0b` (EEPROM ops): 32 total, **all 32 in leg `testmenu2`**, 0 in every other leg (per-leg grep: `sub=0b` count is 0 in attract, all 8 char-* legs, 2p-stages, input, service-retest, testmenu; only testmenu2 shows 32). `sub=0x01`/`sub=0x03` (JVS/IO enumeration, not EEPROM-specific) fire in every leg at a 2–3 baseline, rising to 9 each in testmenu2 (37 total each across the campaign). | **BIOS-path confirmed**: the EEPROM read/write path is exercised only through the service/test-menu UI (Task 6's setting flip-and-persist: Advertise Sound OFF → exit → re-enter confirmed → restored ON), never during attract or any of the 10 gameplay/roster legs. Phase 3 traces the `sub=0x0b` handler function from this MIE evidence as its entry point. |

> **Correction (Phase 3, Task 4).** The `HW[RW]` = 0 evidence in the serial,
> RTC and watchdog rows above is a **null instrument, not a measurement**:
> `cartlog_hwaccess()` returns immediately unless `FLYCAST_HWLOG` is set in the
> environment (`../flycast4naomi2dreamcast/core/hw/mem/addrspace.cpp:118-120`),
> and `scripts/capture_leg.sh:16` sets only `FLYCAST_CARTLOG` — so no leg ever
> emitted an `HW[RW]` line for *any* address. `SERIALPOKE` = 0 remains valid
> evidence, but it watches the Naomi **communication board**
> (`0x5f7018`–`0x5f7028`), not the SH-4 SCIF. The device verdicts themselves
> survive on static grounds; see `docs/kb/boot-binary.md`
> §RTC / SCIF / watchdog for the replacement evidence and the re-run recipe.

---

Task 7 complete — see `docs/kb/00-status.md` for the Phase 2 gate summary and
`docs/kb/cart-streaming-map.md` for the above-16m map this table's main-row
verdict depends on.

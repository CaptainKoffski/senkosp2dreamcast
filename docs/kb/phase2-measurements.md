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
- [x] Test-menu leg (Task 6: legs testmenu + testmenu2, full walk with EEPROM ops observed, 2026-08-19)
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
- Game-code HW pokes (HWR/HWW from game PC range): 0 (no RTC/SCIF MMIO observed).
- PIO bytes: 0x334b70 (vs. 0x172538 typical boot — menu bookkeeping screens do extra PIO reads).

---

Region verdicts + device verdicts land here in Task 7.

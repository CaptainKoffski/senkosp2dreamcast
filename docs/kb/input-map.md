# Input map — senkosp (Phase 2, measured)

Captured 2026-08-19, legs `captures/input.log` (13-control press sequence)
and `captures/service-retest.log` (Service re-test, 4 clean presses,
attract screen only) — recipe: `tooling.md` §Phase 2 capture harness.
Source: `JVSREPORT` (P1 JVS digital word, `maple_jvs.cpp:2241`) — in both
legs it is the *only* channel that carries a per-press signal; `MIERESP
sub=15` (MIE input response, `maple_if.cpp:292`), which the brief expected
to cross-check byte.bit against, never fired during any button hold in
either leg — see "Why no MIE sub=15 byte.bit" below. Instrumented fork @
`f014a410c5f267ba58dd1d007edcf680044c5d09` (current HEAD of
`../flycast4naomi2dreamcast`, same commit as `maple_jvs.cpp:2241` cited
above).

Bindings used for the input.log leg (keyboard, Flycast arcade profile —
supersedes the stage-A prediction in `task-4-report.md`, per user rebind
before capture): stick = arrow keys; M = X; S = C; A = S; Barrage = B;
OverDrive = D; Start = Enter; Coin = A; Test = T; Service = Q (same Service
binding used, unchanged, for the service-retest.log leg).

Neutral JVS word baseline: `0000` (P1 digital word, all controls released).

| Control | Flycast binding used | MIE sub=15 byte.bit | JVS word bit |
|---|---|---|---|
| Up | Up Arrow | n/a¹ | `0x2000` (`NAOMI_UP_KEY`, `maple_devs.h:80`) — measured |
| Down | Down Arrow | n/a¹ | `0x1000` (`NAOMI_DOWN_KEY`) — measured |
| Left | Left Arrow | n/a¹ | `0x0800` (`NAOMI_LEFT_KEY`) — measured |
| Right | Right Arrow | n/a¹ | `0x0400` (`NAOMI_RIGHT_KEY`) — measured |
| M | X | n/a¹ | `0x0200` (`NAOMI_BTN0_KEY`, `maple_devs.h:85`; senkosp label "MAIN") — measured |
| S | C | n/a¹ | `0x0100` (`NAOMI_BTN1_KEY`; senkosp label "SUB") — measured |
| A | S | n/a¹ | `0x0040` (`NAOMI_BTN3_KEY`; senkosp label "ACTION") — measured |
| Barrage (C) | B | n/a¹ | `0x0080` (`NAOMI_BTN2_KEY`, `maple_devs.h:87`) — arcade "Button 3" / senkosp label "MAIN+SUB". Held bit flipped exactly once (`bits-vs-baseline: 1`) — a plain single-button read, not a runtime M+S combo — measured |
| OverDrive | D | n/a¹ | `0x0020` (`NAOMI_BTN4_KEY`, `maple_devs.h:89`) — see "OverDrive wire" below — measured |
| Start | Enter | n/a¹ | `0x8000` (`NAOMI_START_KEY`, `maple_devs.h:77`) — measured |
| Service | Q | n/a¹ | `0x4000` (`NAOMI_SERVICE_KEY`, `maple_devs.h:78`) — measured (retest leg, see "Service retest" below) |
| Coin | A | n/a¹ | not in the 16-bit word — bit 19, `NAOMI_COIN_KEY = 1 << 19` (`maple_devs.h:98`), **source-derived**, not measured — see "Coin / Test" below |
| Test | T | n/a¹ | not in the 16-bit word — bit 18, `NAOMI_TEST_KEY = 1 << 18` (`maple_devs.h:97`), **source-derived**, not measured — see "Coin / Test" below |

## OverDrive wire

The user rebound OverDrive's key (D) to arcade Button 6, which Flycast's
per-game control DB labels "Overdrive" for senkosp
(`naomi_roms_input.h:475`, the `INPUT_5_BUTTONS` 5th-slot argument). That
slot's *source* is `NAOMI_BTN5_KEY` (Button 6, `0x0010`), but senkosp's own
descriptor entry is `{ NAOMI_BTN5_KEY, "OVER DRIVE", NAOMI_BTN4_KEY }` — the
third field is a JVS-bit remap target, applied in
`jvs_io_board::init_mappings()` / `read_digital_in()`
(`maple_jvs.cpp:343-369`, `231-270`). So the bit actually placed on the wire
is `NAOMI_BTN4_KEY` (Button 5, `0x0020`), not Button 6. The captured word
confirms this directly: the OverDrive hold shows `0x0020`, exactly matching
the source-level prediction made in stage A (`task-4-report.md`, "OverDrive
alias") before this key was rebound — same final wire, reached by a
different route.

## Why no MIE sub=15 byte.bit

`MIERESP sub=15` (`maple_if.cpp:289-296`) only prints when the SH4 issues a
maple `MDC_JVSCommand` (`0x86`) DMA with sub-command `0x15`. In
`input.log`: 826 occurrences total, matching 826 `MAPLEPC cmd=86 sub=15`
entries one-for-one, clustering in two narrow windows (log lines
~1,462–13,782 at boot/attract-entry, and ~109,079–119,099 at and after the
Test-menu re-handshake) with **zero** occurring in lines 72,307–102,688 —
the entire span covering all ten button holds measured in that leg. In
`service-retest.log`: same shape — 376 occurrences, all within lines
1,462–13,782 (the fresh boot handshake after relaunch), **zero** across the
four Service press windows (lines 91,441–102,949). `JVSREPORT`
(`maple_jvs.cpp:2241`), by contrast, is unconditional inside the
digital-read handler and fires throughout both legs (4,149 and 4,469 lines
respectively), which is why it — not the raw MIE dump — is the only usable
signal here. Confirmed by direct line-range counts against both capture
files, not inferred.

## Service retest

`captures/service-retest.log`: 4 presses, ~1 s holds, attract screen only,
no other inputs. All 4 are clean single-bit holds:

| Press | Word transition |
|---|---|
| 1 | `0000→4000→0000` (log lines 91,441 / 92,673) |
| 2 | `0000→4000→0000` (log lines 94,241 / 96,061) |
| 3 | `0000→4000→0000` (log lines 97,741 / 99,477) |
| 4 | `0000→4000→0000` (log lines 101,045 / 102,949) |

`0x4000` = `NAOMI_SERVICE_KEY` (`maple_devs.h:78`) exactly — confirms
verdict (a): Service reads normally on the attract screen. The zero-bit
result in the original `input.log` leg (Service pressed *inside* the
Test-menu) was specific to that context, not a broken binding — most likely
the Test-menu UI reads Service through a path that bypasses this
digital-read handler while test mode is active, consistent with `input.log`
showing zero `MIERESP`/no word change for the entire post-Test window
(still true, see "Why no MIE sub=15 byte.bit" above) even though the
control itself is confirmed good here.

## Coin / Test

Both are outside the 16-bit mask the digital-read handler logs
(`cartlog("JVSREPORT buttons=%04x\n", inputs[0] & 0xffff)`,
`maple_jvs.cpp:2241`) — architectural, not something a re-run or retest
fixes:

- **Coin**: `NAOMI_COIN_KEY = 1 << 19` (`maple_devs.h:98`), source-derived
  from the frozen fork, not measured. Reported via a separate JVS coin-count
  command (`0x21`) that isn't cartlog'd at all. Behavioral confirmation: a
  credit was added on press (operator-observed at the controls; matches the
  task brief's design note that Coin issues a credit and gates Start).
- **Test**: `NAOMI_TEST_KEY = 1 << 18` (`maple_devs.h:97`), source-derived
  from the frozen fork, not measured — reported via a status/tilt byte
  (`maple_jvs.cpp:2242`), also not separately logged. Behavioral
  confirmation: the test menu opened on press (operator-observed),
  independently corroborated by a full JVS bus re-handshake logged right
  after the press (ID-string re-request etc., `input.log` lines
  ~109,079–109,183, structurally identical to the boot-time handshake at
  lines ~1,462–1,782) — proof the input reached the system and changed game
  mode, even without a byte.bit or word-bit value to show for it.

## Sanity

11 of 13 rows (Up, Down, Left, Right, M, S, A, Barrage, OverDrive, Start,
Service) are **measured**: exactly one changed bit vs. the `0000` baseline
in the JVS-word transition list (`bits-vs-baseline: 1` per hold — 10 in
`input.log`, in the exact press order specified, plus Service confirmed
separately via 4 clean holds in `service-retest.log`), each matching a
distinct `NAOMI_KEYS` constant (`maple_devs.h:75-99`). Coin and Test are
**not measured** — both are architecturally outside the 16-bit logged word
(bits 19 and 18) — and are documented as **source-derived** constants (cited
above) plus **behavioral** confirmations (credit added; test menu opened),
not measured values.

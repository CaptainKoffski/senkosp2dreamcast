# Input map — senkosp (Phase 2, measured)

Captured 2026-08-19, leg `captures/input.log` (recipe: `tooling.md` §Phase 2
capture harness). Source: `JVSREPORT` (P1 JVS digital word,
`maple_jvs.cpp:2241`) — in this leg it is the *only* channel that carries a
per-press signal; `MIERESP sub=15` (MIE input response, `maple_if.cpp:292`),
which the brief expected to cross-check byte.bit against, never fired during
any of the 13 button holds — see "Why no MIE sub=15 byte.bit" below.
Instrumented fork @ `f014a410c5f267ba58dd1d007edcf680044c5d09` (current HEAD
of `../flycast4naomi2dreamcast`, same commit as `maple_jvs.cpp:2241` cited
above).

Bindings used for this leg (keyboard, Flycast arcade profile — supersedes
the stage-A prediction in `task-4-report.md`, per user rebind before
capture): stick = arrow keys; M = X; S = C; A = S; Barrage = B; OverDrive =
D; Start = Enter; Coin = A; Test = T; Service = Q.

Neutral JVS word baseline: `0000` (P1 digital word, all controls released).

| Control | Flycast binding used | MIE sub=15 byte.bit | JVS word bit |
|---|---|---|---|
| Up | Up Arrow | n/a¹ | `0x2000` (`NAOMI_UP_KEY`, `maple_devs.h:80`) |
| Down | Down Arrow | n/a¹ | `0x1000` (`NAOMI_DOWN_KEY`) |
| Left | Left Arrow | n/a¹ | `0x0800` (`NAOMI_LEFT_KEY`) |
| Right | Right Arrow | n/a¹ | `0x0400` (`NAOMI_RIGHT_KEY`) |
| M | X | n/a¹ | `0x0200` (`NAOMI_BTN0_KEY`, `maple_devs.h:85`; senkosp label "MAIN") |
| S | C | n/a¹ | `0x0100` (`NAOMI_BTN1_KEY`; senkosp label "SUB") |
| A | S | n/a¹ | `0x0040` (`NAOMI_BTN3_KEY`; senkosp label "ACTION") |
| Barrage (C) | B | n/a¹ | `0x0080` (`NAOMI_BTN2_KEY`, `maple_devs.h:87`) — arcade "Button 3" / senkosp label "MAIN+SUB". Held bit flipped exactly once (`bits-vs-baseline: 1`) — a plain single-button read, not a runtime M+S combo |
| OverDrive | D | n/a¹ | `0x0020` (`NAOMI_BTN4_KEY`, `maple_devs.h:89`) — see "OverDrive wire" below |
| Start | Enter | n/a¹ | `0x8000` (`NAOMI_START_KEY`, `maple_devs.h:77`) |
| Coin | A | not observed — **needs controller decision** | not observed — see "Coin/Test/Service" below |
| Test | T | not observed — **needs controller decision** | not observed — see "Coin/Test/Service" below |
| Service | Q | not observed — **needs controller decision** | not observed — see "Coin/Test/Service" below |

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
maple `MDC_JVSCommand` (`0x86`) DMA with sub-command `0x15` — 826
occurrences total in this leg, matching the 826 `MAPLEPC cmd=86 sub=15`
entries one-for-one. But those 826 occurrences cluster in two narrow windows
(log lines ~1,462–13,782, at boot/attract-entry, and ~109,079–119,099, at
and after the Test-menu re-handshake) and **zero** occur in lines
72,307–102,688 — the entire span covering all ten successful button holds
(Up through Start). `JVSREPORT` (`maple_jvs.cpp:2241`), by contrast, is
unconditional inside the digital-read handler and fires throughout (4,149
lines spanning the whole capture), which is why it — not the raw MIE dump —
is the only usable signal for this leg. Confirmed by direct line-range count
against `captures/input.log`, not inferred.

## Coin / Test / Service

None of the three produced a usable single-bit result:

- **Coin** (`NAOMI_COIN_KEY = 1 << 19`, `maple_devs.h:98`) and **Test**
  (`NAOMI_TEST_KEY = 1 << 18`, `maple_devs.h:97`) are both outside the
  16-bit mask the digital-read handler logs
  (`cartlog("JVSREPORT buttons=%04x\n", inputs[0] & 0xffff)`,
  `maple_jvs.cpp:2241`) — architectural, not a bad capture; a re-run would
  not change this. Coin is reported via a separate JVS coin-count command
  (`0x21`) that isn't cartlog'd at all; Test via a status/tilt byte
  (`maple_jvs.cpp:2242`) also not separately logged. The Test *press* did
  produce a real, distinctive effect — a full JVS bus re-handshake
  (ID-string re-request etc., log lines ~109,079–109,183, structurally
  identical to the boot-time handshake at lines ~1,462–1,782) — proving the
  input reached the system and changed game mode, but it isn't expressible
  as a single MIE byte.bit or JVS word bit.
- **Service** (`NAOMI_SERVICE_KEY = 1 << 14 = 0x4000`, `maple_devs.h:78`)
  *is* inside the 16-bit word, and `JVSREPORT` keeps running through the
  Test-menu period (last line 119,090, still logging), but the word never
  leaves `0000` anywhere after line 102,688 — a genuine zero-bit result on
  an in-range bit, not a truncation artifact. Most likely explanation: the
  Test-menu UI reads Service through a path that bypasses this digital-read
  handler while test mode is active, but that's inference, not measurement.
  A quick way to disambiguate: re-test Service alone on the attract screen
  (not inside the test menu).

Per the controller's decision rule for zero/multi-bit results: reporting
these three as **not resolved from this leg** rather than guessing a bit.

## Sanity

10 of 13 rows (Up, Down, Left, Right, M, S, A, Barrage, OverDrive, Start)
show exactly one changed bit vs. the `0000` baseline in the JVS-word
transition list (input leg report, `bits-vs-baseline: 1` per hold), in the
exact press order specified, each matching a distinct `NAOMI_KEYS` constant
(`maple_devs.h:75-99`). Coin, Test, and Service are documented above as
open items, not measured values.

# MIE reply blobs without a capture — `gen_mie_blobs.py` (design)

2026-10-04. Origin: operator question after the 0.16.1 GDI fix — can a
fresh clone build the game? It cannot without first running the game in
the instrumented Flycast fork, because the shim's MIE reply blobs are
extracted at build time from a capture log (`captures/phase4/pc2.log`,
gitignored). Design agreed in-session 2026-10-04; branch `mie-blobs-gen`.

## Goal

Remove the capture from the build. `shims/build/mie_blobs.c` is generated
from inputs a fresh clone already has — committed source plus the
builder's own `senkosp.dat` — with **no new copyrighted bytes committed**.
README "Building from a fresh clone" loses step 2 (the ~300 s
interpreter-mode Flycast capture).

Scope is `pc2.log` only. README steps 3 (RAM snapshot, 512 B of
BIOS-runtime RAM) and 4 (BIOS splash frame) are the same class of problem
and get their own spec; the donor archive is a separate question
(see Out of scope).

## What the capture actually contributes (evidence)

The build consumes 15 blobs (`scripts/extract_mie_blobs.py` `WANT`); the
shim links them by name (`shims/src/main.c:107+`), and
`scripts/build_patch_table.py:665` resolves `mie_sub03`'s address. Their
bytes come from three different places:

| Blobs | Bytes come from | Evidence |
|---|---|---|
| `mie_sub01/13/17/21/31/33`, `mie_86empty`, `mie_jvsf1/10/11/12/13/14/dflt` (14) | **Flycast's emulated MIE + JVS I/O board** — frame header `87 00 20 <words>` (`BaseMIE::reply`, `maple_jvs.cpp:1283-1289`), sub-command acks and the DIP/ready replies (`:1760-1980`), JVS data frames (`receive_jvs_messages`, `:1716-1754`), JVS answers incl. board ID (`get_id()`, `:1105`) and checksum (`:2487-2491`) | emulator output, not Sega/G.Rev code; the board-ID string is already committed (`extract_mie_blobs.py` `BOARD_ID`) |
| `mie_sub03` EEPROM **system section** (image 0x00–0x23) | Flycast `initEeprom` + `configure_naomi_eeprom` (`naomi_flashrom.cpp:144-235`) applied to the cart's `RomBootID` header (`naomi_cart.h:9-46`: game ID @0x134, `coinFlag[0]` @0x1E0, `cabinet` @0x429, `vertical` @0x42B) — **plus one later change: byte 9 = `0x1a`** | spike 2026-10-04 (scratch, not committed): the port of `initEeprom` over `senkosp.dat` reproduces the captured section except byte 9 (derived `0x00`, captured `0x1a`); with byte 9 = `0x1a` the CRC is `9d 6e` = captured, all 36 bytes identical. `0x1a` = coin setting 27 = **FREE PLAY** (`docs/kb/phase4-conversion.md` §FREE PLAY) — an operator test-menu edit that persisted in Flycast's EEPROM file before the capture |
| `mie_sub03` EEPROM **game area** (0x24–0x4B) | the game's own defaults, as captured (Event Mode OFF) | since T18 the loader overwrites this area at every boot from the committed `MENU_DEFAULT_RECORD` (`loader/main.c:486-539`, `scripts/menu_def.py:13`); the captured bytes survive only as the self-check's pristine fallback |

So the port has **two** deliberate default changes, not one: Event Mode ON
(game area, explicit in `menu_def.py`) and Free Play (system area, today
present only *implicitly*, via the capture).

## Decisions

- **Committed constants for the 14 protocol replies**, each annotated with
  the Flycast emitter lines that produce it: plain MIE acks as hex, JVS
  replies as their payload only, wrapped by a ~10-line frame builder that
  mirrors Flycast's emitters (wrapper, `[node status len]` prefix, sync,
  checksum, word padding — so lengths and checksums are computed, never
  copied). They are emulator output, so committing them commits no game or
  BIOS bytes. (Refined while planning: a scratch run showed the builder
  reproduces all 8 JVS-carrying blobs byte-for-byte.)
- **EEPROM system section derived at build time** from the builder's
  `senkosp.dat` header with a Python port of Flycast's `initEeprom` /
  `configure_naomi_eeprom`. The 4-char game ID is ROM bytes, so the output
  stays generated and gitignored (same as today).
- **Port defaults are explicit and live in one place**,
  `scripts/menu_def.py`: the existing `DEFAULT_RECORD` (game area, Event
  ON) and a new `SYSTEM_COIN_SETTING = 27  # FREE PLAY` (system byte 9 =
  setting − 1). The generator reads both; nothing else hard-codes them.
- **Game area baked from `DEFAULT_RECORD`** with the same layout the loader
  writes (`loader/naomi_crc.c:20-31`: `[crc_lo crc_hi 0x10 0x10]` ×2, then
  the record ×2), so the baked image and the boot-time poke agree.
- **`extract_mie_blobs.py` stays as a dev-only oracle** — no longer a build
  input. It is the only tool that can re-prove the generator against a real
  capture, and the KB's provenance chain cites it.
- **`EEPROM_GAME_HEX` is not ported.** Its use case (bake a settings record
  for a leg) is covered by editing `DEFAULT_RECORD` or by the menu; the
  hook remains in the oracle only.

## Approaches considered

1. **Generator with committed protocol constants + derived EEPROM**
   (chosen). Small, every byte cited, oracle-checkable.
2. **Re-implement Flycast's MIE/JVS emulation in Python** and synthesize
   the replies from first principles. Same bytes, several times the code,
   and no extra assurance — the proof is the oracle comparison either way.
3. **Commit the generated `mie_blobs.c` wholesale.** Rejected: `mie_sub03`
   carries the ROM's game ID, and regeneration would still need the
   capture.

## Design

### 1. `scripts/gen_mie_blobs.py` (new)

- **Inputs:** `senkosp.dat` (repo root; already a build input of
  `build_patch_table.py`), `scripts/menu_def.py` (`DEFAULT_RECORD`,
  `SYSTEM_COIN_SETTING`). Reuses `scripts/eeprom_game_diff.py` `crc16`
  (already vector-tested against BIOS-written areas by
  `scripts/test_eeprom_game_diff.py`).
- **Output:** `shims/build/mie_blobs.c` — same 15 symbol names, same
  `<name>_len` companions, same emission order and lengths as today. This
  is the consumer contract; nothing in `shims/` or `build_patch_table.py`
  changes.
- **Protocol replies:** six plain MIE acks as hex (`sub01/13/17/21/31`,
  `86empty`) and eight JVS payloads (`jvsf1/10/11/12/13/14/dflt`, `sub33`)
  fed through `jvs_blob()`, the frame builder: MIE wrapper
  (`receive_jvs_messages`, `maple_jvs.cpp:1716-1754`), `[01 00 len]`
  (`send_jvs_message`, `:1673-1677`), `E0` sync + checksum (`:2487-2491`),
  zero pad to Flycast's `dword_length` (`:1719`). `mie_sub33` = the built
  data frame + the sub-0x17 ack frame (`:1889-1894`). One comment per blob
  names its emitter. The `mie_sub33` idle-frame equivalence the extractor
  asserts today (the shim rebuilds polls from that frame —
  `shims/src/jvs.c:200`) is kept as a test.
- **`mie_sub03`:** header `87 00 20 20` (32 words = 128 B,
  `maple_jvs.cpp:1936`) + 128-B image: system section = `initEeprom` port
  over the header, then byte 9 := `SYSTEM_COIN_SETTING − 1`, CRC + mirror
  recomputed (`write_naomi_eeprom` semantics, `naomi_flashrom.cpp:116-135`);
  game area from `DEFAULT_RECORD`; zero tail.
- **Input guards (fail loudly):** header magic `NAOMI` at 0, game ID
  printable ASCII (an encrypted header — `naomi_cart.h:43` — would garble
  it), `len(senkosp.dat) == CART_SIZE` (`shims/include/shim_iface.h`),
  `len(DEFAULT_RECORD) == 16`, `1 <= SYSTEM_COIN_SETTING <= 28`.

### 2. Build wiring — `shims/Makefile`

`$(B)/mie_blobs.c` depends on `../scripts/gen_mie_blobs.py`,
`../scripts/menu_def.py`, `../scripts/eeprom_game_diff.py`,
`../senkosp.dat`; recipe `python3 ../scripts/gen_mie_blobs.py`. The
`CAPTURE` variable and its "missing — recapture" error rule are deleted.

### 3. Oracle + tests

- **`scripts/test_gen_mie_blobs.py`** (new, in `make test`):
  - always: the protocol table's checksum/idle-frame self-checks; system
    section of a synthetic `RomBootID` header against hand-computed bytes
    for both `coinFlag` branches; game area of `DEFAULT_RECORD` against the
    KB's real BIOS-written Event area (`4f541010…`,
    `scripts/test_eeprom_game_diff.py`).
  - when `senkosp.dat` **and** `captures/phase4/pc2.log` exist: full
    generator output vs `extract_mie_blobs.py` run with
    `EEPROM_GAME_HEX=<game area of DEFAULT_RECORD>` — **byte-identical**
    blob bytes. Otherwise prints `SKIP (no capture)` and passes.

### 4. Docs

README: drop step 2 and the `MIE capture` input row; renumber.
`tooling.md`: `pc2.log` no longer a build input (the 2026-10-04
"must stay uncompressed" exception becomes historical; the 1061-1091
fresh-clone notes and the `EEPROM_GAME_HEX` recipe at :1157 marked
superseded). `phase4-conversion.md` §Blob provenance: superseding note
pointing here. `00-status.md` entry. `shims/src/main.c` / `jvs.c` comments
that name the extractor as the source get the generator's name.

## Intended behavior changes

Everything the game sees on the **shipping** build is unchanged. Two
bytes-on-disc differences, both deliberate:

- The baked game area becomes Event ON (from `DEFAULT_RECORD`) instead of
  the captured Event OFF. The shipping loader overwrites it at boot anyway;
  what changes is the **self-check fallback** (now Event ON, consistent
  with the menu) and **`MENU=0` builds** (no poke — `loader/main.c:486`
  — so they now boot with Event ON, where they booted OFF before).
- Free Play is now produced by an explicit setting rather than inherited
  from a capture; its value is unchanged.

## Gates

1. **Oracle identity** (this machine, which still has `pc2.log`):
   `test_gen_mie_blobs.py` full mode passes — generator ≡ extractor with
   the `DEFAULT_RECORD` game area.
2. **Binary diff confined:** old vs new `shims/build/shim.bin` and
   `build/1ST_READ.BIN` differ **only** inside `mie_sub03`'s game area
   (40 B at `mie_sub03 + 4 + 0x24`, located via `shim.map`); tracks 01–03
   identical; `track04.iso` differs only at those bytes in the loader
   region.
3. **`make test`** green.
4. **Fresh clone:** `git clone` into the scratchpad with no `captures/`
   directory, the builder's own `senkosp.dat` / BIOS / KOS / RAM snapshot /
   splash / donor provided, `make gdi` succeeds; md5s match gate 2's build.
5. **Flycast** (real BIOS): shipping build reaches the menu (RAWFB); a
   `MENU=0` build reaches attract with 0 SHIMERR.
6. **Hardware** (operator leg, GDEMU): boot; menu shows Event ON; a match
   starts without inserting credits (Free Play) and plays in Event Mode.

## Out of scope

- README step 3 (`tools/ram-snapshot.bin`, KERNEL_A 512 B) and step 4
  (`loader/splash.png`) — next spec, same method (derive from the
  builder's BIOS file if possible).
- The donor archive (`[GDI] Dolphin Blue.7z`): a third-party commercial
  image the builder must obtain; replacing it means mastering tracks 1–3
  from scratch and re-proving boot on hardware.
- Persistent settings (VMU save) — unchanged, session-only as today.
- **`loader/logo_strip.pal8`** (G.Rev menu logo, gitignored, hard
  dependency of `loader/Makefile:178` since 0.16.0) is missing from README's
  fresh-clone inputs — found while scoping this spec (2026-10-04). Gate 4
  supplies it by hand; documenting/optionalizing it is separate work.

## Risks

- **Byte-9 provenance.** The derivation explains the captured system
  section exactly with one override; if a future capture or a different
  romset revision disagrees, the oracle test (gate 1) is what catches it.
- **ROM revision.** The derivation reads the builder's header; a different
  `senkosp` revision with different `coinFlag`/`cabinet` bytes would yield
  a different (still Flycast-correct) system section. Nothing pins the
  `.dat` by hash today (README step 1 checks only the `NAOMI` magic); the
  generator prints the derived system section, the `CART_SIZE` guard
  rejects a different-size image, and the patch table's byte-exact
  relocation asserts (`build_patch_table.py`) already fail on a foreign
  ROM long before the EEPROM matters.

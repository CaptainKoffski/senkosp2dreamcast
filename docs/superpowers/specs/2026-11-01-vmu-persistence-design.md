# VMU persistence — settings and the controls library on the memory card (design)

2026-11-01. Origin: the 2026-10-25 amendment to
`docs/superpowers/specs/2026-10-24-controls-library-design.md` (§"Warm boot
resets the library") made persistence load-bearing: the in-game
A+B+X+Y+Start reset reloads the loader from disc and KOS clears .bss, so a
tester loses every custom layout on any reset. Brainstormed and approved in
chat 2026-11-01 (operator: "good UX, obvious, easy to use, not irritating";
consent-before-first-write and LEFT/RIGHT card choice were the operator's
asks). No mockups: the only new pixels are one text line on the existing
top page and the save icon, both previewed by the generator in the plan.

Amends §8 "Loader state (VMU-ready)" of the controls-library spec (this is
the "future VMU task" it names) and closes its 2026-10-25 amendment.

## Intent

A tester who builds layouts must find them again after power-off and after
the in-game warm boot. It has to feel like a normal Dreamcast game save:
nothing is written to anyone's card without a deliberate press, no question
is ever asked unless there is something to keep, and one line of plain text
on the main menu always says what happened. The operator's worry, in their
words: players "can be disappointed that the game silently wrote something
to their cards", and with many ports in the pipeline that adds up.

## Goals

1. Persist everything the menu can change: the 16-byte settings record
   (`menu_game_record`) and the whole controls library (`ctl_lib`: custom
   layouts, used flags, per-port selection).
2. Save automatically, with no save button: whenever the player leaves
   Controls or Settings with changes, and at START GAME if changes are still
   unsaved. Write nothing when nothing changed.
3. Consent once per card: the loader writes silently only to the one card
   this session loaded from or got an A on (see "Card identity"). Any other
   card is asked first, at the moment of the first save, never at boot, and
   the question says REPLACE when that card already carries a save.
4. Any memory card in any slot counts, ports C and D included (arcade sticks
   have no slot; a spare pad on C can hold the file). Hot-plug works: a card
   inserted mid-session is found at the next save.
5. One status line on the top menu reports the state (loaded / saved /
   saving / no card / declined / card full / failed) and names the slot.
6. The file shows in the Dreamcast file manager like any game save: name,
   description, a legible icon, 2 blocks.
7. Garbage, unformatted or foreign cards never crash, hang or get written.
8. The game itself still never touches a VMU (phase-6 VMU-safety story, KB
   `00-status.md` criterion 6 and `make test-vmu`): the only writer is the
   loader, in the menu, after consent.

## Non-goals

- Remembering a "no" across power cycles (that would need a write).
- Saving on the menu's own A+B+X+Y reboot combo (`loader/menu.c` edge(),
  `arch_reboot`): that is "abandon", not "leave the page".
- Profiles, several files, eyecatch art, the VMU's LCD, in-game saving,
  4x-memory-card specifics, per-game Flycast VMUs.
- Changing the saved-file format later without bumping the version byte.
- Loading a card after boot. A card inserted mid-session is never read into
  the live state (that would discard what the player just edited); the way
  to play with the layouts on a newly inserted card is the warm boot, and
  the status line then names the card it loaded from. Operator's decision
  2026-11-01: "ask to replace, never auto-load".

## Anti-goals (failure even if it "works")

- Any byte written to a card other than the one this session loaded from or
  got an A on. A silent overwrite of a save that another card, build or
  player left there (the tournament case: player 1's card loaded at boot,
  player 2's card with their own save plugged in later, one tweak, player 2's
  layouts gone). Any prompt at boot. Any prompt when nothing changed.
- A crash, hang or write on an unformatted / 0xA5-filled / foreign card.
- START GAME blocked by a missing or full card: the game must always start.
- A file larger than 2 blocks. A third block means the payload grew past
  384 bytes; redesign instead.
- `make test` or `make test-vmu` (the VMU canary) going red.

## Constraints

- Every hardware/behavioural claim cites a primary source (KOS at
  `tools/kos`, the Flycast fork). Wiki-free.
- Loader `build/1ST_READ.BIN` ≤ 3,538,944 bytes (3,045,188 today after
  `make gdi`; `make cdi` deletes it, measure after `make gdi`).
- All menu text is baked offline by `scripts/gen_menu_assets.py` from
  `scripts/menu_def.py` into `loader/menu_sheet.pal8` (≤ 256 RGB565
  colours, asserted); there is no runtime font. Every new strip passes
  `check_fits` at `F_ROW` (624 px usable).
- The icon ships in git, so it contains no copyrighted art (`logo.png` is a
  gitignored input): the generator draws it from text/shapes in the menu's
  own colours (`BG`, `FG`, `AMBER`).
- The Flycast fork cannot inject pad input (memory note), so the unattended
  emulator check is a build-time diag define, like `MENUDIAG=1`.
- The VMU-safety tripwire `scripts/test_maple_literals.py` (part of
  `make test`) fails the build on any undefined `vmu*`/`maple*` symbol in
  `loader/main.o` or `loader/handoff.o` beyond `maple_wait_scan`,
  `maple_enum_type`, `maple_dev_status` (`LOADER_MAPLE_ALLOW`, script lines
  135-154, 225-230). So every VMU call hangs off `menu_run` (`menu.o` →
  `vmu_save.o`); `main.c` does not change and never names a VMU symbol.
- Operator legs on real hardware are the claim gate (single-rig caveat).

### VMU facts the design rests on (cited)

- Files are whole 512-byte blocks: `vmufs_write` pads `insize` up to a
  multiple of 512 (`tools/kos/kernel/arch/dreamcast/fs/vmufs.c:689-699`).
- The BIOS-visible header is 128 bytes (`vmu_hdr_t`,
  `tools/kos/kernel/arch/dreamcast/include/dc/vmu_pkg.h`: 16+32+16+2+2+2+2+
  4+20+32); each icon frame is 512 bytes (32×32, 4 bpp) with a 16-entry
  ARGB4444 palette; `vmu_pkg_build` lays out header, icons, eyecatch, data
  and stores CRC16-CCITT over the whole file with the crc field zeroed
  (`tools/kos/kernel/arch/dreamcast/util/vmu_pkg.c:82-137`);
  `vmu_pkg_parse` recomputes and rejects a mismatch (`:143-171`).
- Icon pixels are two per byte, high nibble first (the .ico loader keeps the
  source nibble order: `vmu_pkg.c:318-332`, `(pxh << 4) | pxl`).
- Filenames are 12 bytes, no terminator, matched with `strncmp(…, 12)`
  (`include/dc/vmufs.h:79`, `vmufs.c` `vmufs_dir_find`).
- The root block is block 255 and starts with 16 bytes of 0x55
  (`vmufs.c` `vmufs_root_read`; `include/dc/vmufs.h:57` `magic[16]`). KOS
  does not validate it: `vmufs_setup` (`vmufs.c:482-`) checks only that the
  device is valid and a memory card, then mallocs `dir_size * 512` and
  `fat_size * 512` straight from the root; `vmufs_find_block` and
  `vmufs_fat_free` index the one-block FAT (256 entries) by `root->blk_cnt`
  with no bound (`vmufs.c:291-321`, `:446-457`). Hence the root guard
  below.
- The root block carries the format timestamp (`vmu_timestamp_t`, 8 BCD
  bytes, `include/dc/vmufs.h:37-46,58`), written when the card is formatted.
  It is the cheapest stable identity a card offers, and we hold the root
  block anyway for the guard.
- `maple_enum_type(n, MAPLE_FUNC_MEMCARD)` walks ports A..D then units 0..5
  (`tools/kos/kernel/arch/dreamcast/hardware/maple/maple_enum.c:35-50`), so
  "first card" is A1, A2, B1, B2, C1, C2, D1, D2. KOS's own slot spelling is
  `port + 'A'`, `unit + '0'` (every `vmufs.c` dbglog).
- Hot-plug: the vblank handler re-sends DEVINFO per port/unit and marks
  disconnects (`hardware/maple/maple_irq.c:32-230`, `maple_vbl_irq_hnd` →
  `vbl_autodetect` / `vbl_chk_disconnect`), so an enumeration at save time
  sees the cards present now, not at boot.
- `vmufs_free_blocks(dev)` reports free blocks (`include/dc/vmufs.h:383`);
  `VMUFS_OVERWRITE` deletes the old file before writing (`vmufs.c:689+`
  lines 23-34 of the function), so overwriting our own 2-block file needs
  no extra space.
- Warm boot: the in-game A+B+X+Y+Start path reloads the loader from disc;
  `arch_main` clears .bss
  (`tools/kos/kernel/arch/dreamcast/kernel/init.c:299`). Everything the
  menu holds is therefore rebuilt from the card on every boot.
- Emulator: Flycast writes VMU flash straight to `vmu_save_A1.bin` etc.
  (`../flycast4naomi2dreamcast/core/hw/maple/maple_devs.cpp:679-707`) and
  auto-formats only a missing or all-zero file (`:436-474`), as the canary
  script `scripts/test_vmu_untouched.sh` already relies on.

## The file

| Field | Value |
|---|---|
| Filename | `SENKOSP_SYS` (11 of 12 chars) |
| desc_short (16) | `SENKO NO RONDE` |
| desc_long (32) | `DC PORT SETTINGS AND CONTROLS` |
| app_id (16) | `SENKOSP2DC` |
| icon_cnt / anim / eyecatch | 1 / 0 / none |
| data_len | 140 |
| Size | 128 + 512 + 140 = 780 bytes → 2 blocks |

Payload v1, 140 bytes, in this order, all bytes verbatim:

| Offset | Bytes | Content |
|---|---|---|
| 0 | 4 | magic `SKSP` |
| 4 | 1 | version = 1 |
| 5 | 3 | reserved, 0 |
| 8 | 16 | `menu_game_record` |
| 24 | 116 | `ctl_lib_t` as laid out in memory: `custom[2][8][6]` (96), `used[2][8]` (16), `sel[2][2]` (4). All `unsigned char`, so no padding; the host test static-asserts `sizeof(ctl_lib_t) == 116`. |

A loaded file is accepted only if all of: `vmu_pkg_parse` succeeds (CRC),
magic and version match, `data_len == 140`, every function id ≤ 6 (ids
0..6 per `shims/src/layouts.h` `JVS_FUNC_MASK[7]`), every `used` is 0 or
1, every `sel` is `< CTL_N_STOCK[cls] + CTL_N_CUSTOM` and, when it names a
slot, that slot is used, and the record matches the menu's own table:
bytes at indices not in `MENU_SET_IDX` equal `MENU_DEFAULT_RECORD`, bytes
at `MENU_SET_IDX[i]` are one of `MENU_SET_BYTE[i][0..NVAL-1]`
(`loader/menu_layout.h`). One verdict for the whole file: anything off and
the file is treated as absent (defaults; the next consented save overwrites
it). Rationale: the record is poked into the game's EEPROM image, the
library into the shim's layout words; a card is an outside input.

Icon: 32×32, ≤ 16 colours, drawn by the generator from text in the menu
font and colours (my call: the letters `SR` on the menu grey with an amber
band, in the style of the top page; builder may do better, the bar is
"legible in the BIOS file manager", checked by eye on hardware). Emitted as
two C arrays (palette ARGB4444 with alpha 0xF, 512 bytes of 4-bpp pixels,
high nibble = left pixel) next to the other generated tables.

## Behaviour

### Card identity (what earns a silent write)

A card is identified by its slot plus the 8 timestamp bytes of its root
block (the fingerprint). `home` is one such identity: the card the boot
load came from, or the card the player pressed A for this session. A write
is silent only to `home`, checked at write time: the card now in that slot
must be readable and carry the same fingerprint. A different card in the
slot, or none, means `home` is cleared and the normal asking path runs.
Nothing else earns silence: not a `SENKOSP_SYS` by name, not a valid one,
not a consented-to slot whose card was swapped. Known narrow hole, accepted:
two cards formatted in the same second, swapped in the same slot
mid-session after an A. Emulator cards may share a canned timestamp
(Flycast auto-format); there the slot still separates them and a
mid-session swap in one slot is not a scenario.

### State (loader, session)

- `saved_image`: the 132 bytes (record + library) as last loaded or last
  successfully written; defaults when nothing was loaded. `dirty` means the
  live bytes differ from it (memcmp at sync time; no change tracking).
- `home`: a card identity (slot + fingerprint) or none.
- `declined`: the player answered B this session.

### Boot

Scan cards in enumeration order. The first *readable* card (see Hardening)
holding a `SENKOSP_SYS` that parses and validates becomes `home`; its bytes
replace the defaults before the menu draws. Status line: `LOADED FROM VMU
A1`. With no readable card anywhere: `NO VMU: CHANGES WON'T BE KEPT`.
Readable cards but no valid file (none, or one that fails validation): blank
line, no `home`; the REPLACE prompt tells the player later that a file is
there. Never a prompt, never a write. Boot is the only load.

### Sync points

1. Returning to the top menu from Controls or Settings (B).
2. START GAME, from anywhere START is honoured, before the splash. The
   prompt, if any, appears on the top page; the game starts right after the
   answer or the write.

Not a sync point: the reboot combo.

### Sync

```
if not dirty: return                      # nothing changed, touch nothing
cards = readable cards now (fresh enumeration, root read, fingerprint)
if home and the card in home's slot has home's fingerprint: write(home); return
home = none                               # gone or swapped: no silence left
if cards empty:  line NO VMU: CHANGES WON'T BE KEPT; return
if declined:     line NOT SAVED: KEPT UNTIL POWER OFF; return
prompt over cards (first = cards[0]):
    A: home = chosen (slot + fingerprint); write(home)
    B: declined = 1; line NOT SAVED: KEPT UNTIL POWER OFF
```

`write(home)`: line `SAVING TO VMU xx` (drawn before the first maple
write, the usual "don't pull the card" cue). Space check first: free
blocks plus the block count of any `SENKOSP_SYS` already in the directory
(by name; `VMUFS_OVERWRITE` deletes it first) must be ≥ 2, else line `NEED 2
FREE BLOCKS ON VMU xx`, no attempt. Else `vmufs_write(…, VMUFS_OVERWRITE)`;
success → `saved_image` = live bytes, line `SAVED TO VMU xx`; failure →
line `SAVE FAILED ON VMU xx`, `dirty` stays, so the next sync point retries
by itself. `home` is kept on failure: the player consented to that card,
and while that same card (fingerprint) sits in that slot it is retried
silently, never re-asked. Swap it and the asking path returns.

### The prompt

The status line becomes `SAVE SETTINGS TO VMU xx` when the shown card has
no `SENKOSP_SYS` in its directory, or `REPLACE SAVE ON VMU xx` when it has
one by name, whatever its validity, age or origin. The top footer swaps to
`A: YES   B: NO` (one card) or `A: YES   B: NO   LEFT/RIGHT: OTHER VMU`
(several). LEFT/RIGHT cycles the slot name through the readable cards,
wrapping, and the line's wording follows the shown card. The menu waits;
UP/DOWN and START are ignored while it shows. A or B ends it and the normal
footer `UP/DOWN: MOVE   A: SELECT` returns. The candidate list is taken
once when the prompt opens; a card pulled between the prompt and the write
surfaces as `SAVE FAILED ON VMU xx`.

### The status line

One strip-high line (24 px, 640 wide, `F_ROW`, `FG` on the page grey) at
y = 416 on the top page, between the last item (`MENU_TOP_DEST` y 363 + 36)
and the footer at 452. Strings, final (VMU, not MEMORY CARD: operator's
pick); `xx` is the slot token:

| Line | When |
|---|---|
| `LOADED FROM VMU xx` | boot, file found |
| `SAVED TO VMU xx` | after a successful write |
| `SAVING TO VMU xx` | during a write |
| `SAVE SETTINGS TO VMU xx` | the prompt, card without a `SENKOSP_SYS` |
| `REPLACE SAVE ON VMU xx` | the prompt, card with one (any validity) |
| `NEED 2 FREE BLOCKS ON VMU xx` | first save to a full card |
| `SAVE FAILED ON VMU xx` | any other write failure |
| `NO VMU: CHANGES WON'T BE KEPT` | no readable card (boot, or at sync) |
| `NOT SAVED: KEPT UNTIL POWER OFF` | player declined |
| (blank) | card present, no file, nothing to report yet |

The slot token is composed at draw time from eight small baked strips
(`A1`…`D2`) blitted after the message strip; the generator emits each
message's text width so the pair is centred as one line (centre on the
widest token; the token widths differ by a pixel or two, invisible). Every
message strip ends with the token or has none, by construction of the
wording above.

The line is redrawn with `draw_top`. Each time the top page is drawn, a
`NO VMU` line is re-evaluated against a fresh enumeration (a card plugged
in since turns it blank), so the warning never lies. Other lines stay as
they are until the next sync (no nagging when `home` is pulled).

## Hardening (trust boundary: the card)

- A card is *readable* only if it reports `MAPLE_FUNC_MEMCARD`, its block
  255 reads, its first 16 bytes are 0x55, `fat_size == 1`,
  `1 ≤ dir_size ≤ 13`, `blk_cnt ≤ 256`, `fat_loc < 256` and `dir_loc < 256`
  (the standard layout; bounds the two mallocs `vmufs_setup` does from
  those fields and the FAT indexing by `blk_cnt`). Anything else is skipped
  as if absent, silently. The canary script's 0xA5-filled cards exercise
  exactly this path, and `make test-vmu` must keep passing: on the usual
  `MENU=0` image (no menu, no VMU code linked) and on the shipped `MENU=1`
  image, where the loader sits in the menu with no input, nothing is dirty,
  nothing is written, and the three canaries are unreadable anyway.
- Parse validation as in "The file". No field from the card is used before
  it is range-checked.
- The save path runs only inside the menu, before the handoff; the shim and
  the game never see a maple memory-card frame (unchanged phase-6
  guarantee; `scripts/test_maple_literals.py` still gates the build).

## Unattended check (emulator, build-time diag)

`VMUDIAG=1` (`-DLOADER_VMUDIAG=1`, pairs with `SERIAL=1`; the menu stays
compiled in, unlike `MENUDIAG=1`, because the VMU code lives behind
`menu_run`): `menu_run` does the boot load, logs `VMUSAVE load=<0|-1>
home=<xx|->`, then, if no file was loaded, forces a known library (pad
CUSTOM 1 = `CUSTOM_DEMO` from `menu_def.py`, P1 pad selecting it, record =
the Task-18 easy record already in `main.c`) and runs `write()` on the
first readable card with consent granted by the define, logging `VMUSAVE
write=<rc> slot=<xx>`; if a file was loaded it logs the 140 payload bytes
as hex. Either way it then returns without waiting for input, so the
unattended leg goes on to attract. Two boots on one Flycast VMU directory
(the canary script's transient-config technique, formatted card on B1 or a
zeroed A1) give write then load. A host script `scripts/test_vmu_save.py`
decodes the emulator's `vmu_save_*.bin` (root block 255 → directory → FAT
→ file), checks the header fields and the payload against the forced
values, prints the decoded layouts by name, and writes the icon out as a
PNG to be looked at (verification discipline: decoded, viewed, not a byte
echo). Test-only, never shipped.

**Amendment 2026-11-01 (as built).** The shipped diag prints `VMUSAVE
load=<0|-1> home=<xx|-0> cards=<n>`: `home=-0` when there is no home (the
spec wrote `home=<xx|->`), and `cards=` is appended. With nothing loaded it
forces setting 0 (GAME DIFFICULTY) to HARD `0x02`, not "the Task-18 easy
record": an unambiguous grep token, and a non-default byte proves the record
round-trips. The logged `payload=` is the loaded state re-serialized, not the
card's bytes (reserved bytes 5..7 are not checked on load). The host
decoder is `scripts/vmu_decode.py` (with `scripts/test_vmu_decode.py`) and the
two-boot driver is `scripts/test_vmu_save.sh diag|show`, not
`scripts/test_vmu_save.py`.

## Hardware verification (operator legs, the claim gate)

1. Fresh card in A1: boot → blank line. Build a layout, B → prompt names
   A1, footer `A: YES   B: NO`. A → `SAVING` then `SAVED TO VMU A1`. Power
   cycle → `LOADED FROM VMU A1`, layout present. BIOS file manager shows
   `SENKO NO RONDE`, 2 blocks, icon legible.
2. Decline: fresh card, edit, B at the prompt → `NOT SAVED…`; START → no
   prompt, game starts; file manager shows no file.
3. Two cards (A1, B1), no file: prompt, LEFT/RIGHT flips the token, pick
   B1 → later boot says `LOADED FROM VMU B1`; A1 untouched.
4. No card: `NO VMU…` at boot; edit; B → same line, no prompt; insert a
   card; back out of any page → prompt (hot-plug).
5. In-game warm boot after a save → layouts back.
6. Full card (fewer than 2 free blocks, no file): `NEED 2 FREE BLOCKS…`;
   free space in the file manager; next boot, edit, B → saved.
7. Swap: boot from A1 (`LOADED FROM VMU A1`), pull it, insert another card
   that already carries a `SENKOSP_SYS` into A1, edit, B → `REPLACE SAVE ON
   VMU A1` prompt, not a silent write; B → `NOT SAVED…`; file manager shows
   that card's file unchanged. Warm boot → `LOADED FROM VMU A1` with that
   card's layouts.
8. `make test-vmu` on the shipped `MENU=1` build: PASS.

## Code shape (boundaries; the rest is the builder's)

- `loader/vmu_save.c` / `.h`: a pure half (payload build, payload parse +
  validation over a 140-byte buffer, slot token helpers) host-tested in
  `shims/test/test_vmu_save.c` the way `test_ctl_lib.c` is wired
  (`shims/Makefile:83`, part of `make test`); a KOS half (readable-card
  scan, load, write, free-block check) using `vmufs_*` and `vmu_pkg_*`
  directly, no VFS path strings.
- `loader/menu.c` owns the prompt and the status line (it owns `edge()` and
  the blits); `menu_run` calls sync at the two sync points.
- `scripts/menu_def.py` / `gen_menu_assets.py`: the eight messages, two
  prompt footers, eight slot tokens, the icon; `menu_layout.h` gains their
  rects, widths and the line's y. Sheet height grows as needed; the
  ≤ 256-colour assert and `check_fits` stay the gates;
  `scripts/test_gen_menu_sheet.py` stays exhaustive.
- KB: `input-map.md` §Controls library (persists; consent rule),
  `00-status.md` top, `phase7-polishing.md` (new T-item), the VMU-safety
  note ("the loader writes one file, in the menu, after consent; the game
  still never touches a VMU"), `tooling.md` (VMUDIAG, the decoder script;
  no new tool installs expected).

## Left to the builder

The exact icon art within the rules above; the generator's strip layout;
whether the slot-token centring uses the widest token or a fixed column;
`vmu_save.h` signatures; where the 132-byte snapshot lives; serial log
wording beyond the `VMUSAVE` prefix; the order of operator legs.

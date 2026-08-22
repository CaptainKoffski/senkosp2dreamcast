# Phase 4 — Conversion: design spec

**Date:** 2026-08-22
**Status:** approved (design), pending implementation plan
**Predecessor:** Phase 3 reverse engineering
(`docs/superpowers/specs/2026-08-19-phase3-reverse-engineering-design.md`;
gate green 2026-08-22, `docs/kb/00-status.md`)
**Precedent:** the Cleopatra Phase 4 shipped architecture
(`../cleopatra/docs/kb/phase4-conversion.md` §Shipped architecture;
spec `../cleopatra/docs/superpowers/specs/2026-07-18-phase4-conversion-design.md`)
— skeleton reused wholesale; senkosp deltas below.
**Project:** static binary conversion of *Senko no Ronde Special*
(Naomi GD-ROM → Dreamcast). See `CLAUDE.md`, `docs/kb/00-status.md`.

## Purpose

Phase 3 handed over every address Phase 4 needs
(`docs/kb/boot-binary.md` §The nine targets — answer index) and a
relocation strategy proven by dry run
(`docs/kb/relocation-map.md`). Phase 4 spends them: build the loader,
the freestanding shim, and the patch table, master a bootable GDI, and
prove it in the emulator's **Dreamcast** profile.

**Gate (playbook):** the GDI boots in Flycast's DC profile, attract
runs, and the game is playable. Exit criteria in §Exit criteria below.
Real hardware is Phase 5; the honest limit from Phase 3 carries
forward verbatim — emulator-green proves nothing about real hardware.

## Decisions taken in this design (user-approved 2026-08-22)

1. **Test/Service menu: reachable via boot combo; exit = console
   reboot.** Hold **A+Start** during boot (exact combo may be revised
   at implementation) → the loader boots the *test load* instead of
   the main load. The game-restart stub's Naomi-BIOS jump is patched
   to a DC hard reboot, so test-menu exit reruns IP.BIN → loader →
   main boot. Rationale: 2 of the 4 relocation words already exist
   solely to keep the test image working, so reachability costs
   nothing; reboot is the smallest restart surface
   (`docs/kb/relocation-map.md` §Deliberately not patched, reset stub).
2. **The instrumented-Flycast fork probe happens early in Phase 4**,
   before shim debugging starts: tag which caller reached
   `maple_DoDma()` plus an `r15` water-mark probe. Closes Phase 3's
   four FAILing parser checks, names the EEPROM-write call site, and
   upgrades Phase 3 gate criterion 2 from `[~]` to `[x]`
   (`docs/kb/boot-binary.md` §Why three checks cannot pass as written).

## Approach (chosen): Cleopatra skeleton, senkosp deltas

Copy-adapt `../cleopatra`'s proven Phase 4 deliverable — KOS loader →
old-byte-verified patch table → register-mirror shim → donor-clone GDI
mastering — into this repo. The shared-kit extraction remains deferred
(`../cleopatra/docs/superpowers/specs/2026-07-26-experience-reuse-design.md`);
a fresh build was rejected as discarding Flycast-proven code.

Two pieces are genuinely new, both forced by Phase 3 findings:

- **A raw-ATA GD-ROM driver** replaces Cleopatra's syscall-based
  `gd.c`. The loader must place the Naomi RTOS kernel at
  `0x0c000600`–`0x0c007xxx` (`docs/kb/tooling.md` §Phase 3: RAM
  snapshot; Phase 4 flag 8), which overwrites the DC BIOS syscall
  handlers resident in that same range (GD entrypoint `0x8c0010f0` —
  Phase 4 flag 5). Split: the *loader* uses KOS/GD freely before any
  low-RAM placement; the *runtime shim* drives the ATA registers
  directly.
- **A new shim home.** Cleopatra's `0x8cfc0000` sits inside senkosp's
  relocated heap. Candidate: the low window `0x8c010000`–`0x8c018000`
  (32 KB). See §RAM map, open question O1.
  *(Corrected 2026-08-22 during plan-writing: the window was first
  drawn from `0x8c00f000`, but `0x8c00f000`–`0x8c00ffff` is
  game-reserved — VBR = `0x8c00f400` set by entry-chain step 8, vectors
  plus the 1 KB scratch block above the stack top —
  `docs/kb/boot-binary.md` §Stack region.)*

## RAM map & placements

Final state at game entry (DC main RAM `0x8c000000`–`0x8d000000`):

| Range | Contents | Placed by |
|---|---|---|
| `0x8c0000b0`–`0xe0` | DC syscall vectors — untouched (kernel starts at `0x600`); loader-time use only, dead at runtime | DC BIOS |
| `0x8c000600`–`0x8c007xxx` | Naomi RTOS kernel slice from the user's BIOS dump (byte-identity recipe: `tooling.md` §Phase 3: RAM snapshot) | handoff stub |
| up to `0x8c00f000` | boot stack (SP seed `0x8c00f000`, unpatched — target 7) | game |
| `0x8c00f000`–`0x8c00ffff` | game-reserved: VBR vectors (VBR = `0x8c00f400`, entry-chain step 8) + the 1 KB scratch block — **not free** (`boot-binary.md` §Stack region) | game |
| `0x8c010000`–`0x8c018000` | **shim home (32 KB):** code + `SHIM_ERR` + `G1_MIRROR` + maple mirror + `MAPLE_TX/RX` + 2 KB sector bounce + MIE blobs + EEPROM image + GD stack. Pending write-watch proof (O1) | handoff stub |
| `0x8c018000`–`0x8c01f000` | Naomi BIOS `0x60000` blob, 28,672 B (target 1, mandatory). Pre-placed: the game's signature check at `FUN_8c065ff0` fails on DC and skips its own copy; ours is already there, so the dispatch pointer (`0x8c1bf42c`) lands on real code. Zero patches; fallback = Cleopatra-style pointer redirect if the game validates more than presence | handoff stub |
| `0x8c01f000`–`0x8c020000` | 4 KB spare | — |
| `0x8c020000`–`0x8c191ff8` | main image (`.dat 0x0`, `0x171ff8` B) — or test image to `0x8c06dc40` (`.dat 0x171ff8`, `0x4dc40` B) on combo boot; both entry `0x8c021000` (`docs/kb/game.md` §Parsed .dat header). Reloc words pre-applied | handoff stub |
| …–`0x8c1de200` | BSS; second task stack at `0x8c1d4984` inside it — no reservation needed (target 7) | game |
| `0x8c1de200`–`0x8d000000` | relocated syMalloc heap (the proven 4-word patch; peak reservation 14,398,432 B vs capacity 14,818,816 B) | game |

VRAM needs no map: the second patch pair puts KAMUI2 in its native DC
8 MB mode (`relocation-map.md` §Provenance). The reboot path's
top-page writes land in heap top — acceptable, that path is a reboot
(Phase 4 flag 3).

## Loader & boot flow

Cleopatra's KOS `1ST_READ.BIN` (`loader/main.c` + `handoff.S`) with
one structural change: **every final placement moves into the handoff
stub's copy-record list**, because three destinations (shim home,
BIOS blob, kernel) overlap or sit under the running loader/KOS (KOS
links at `0x8c010000`). The loader stages; the stub places.

1. KOS init; splash + boot-load indicator (reused; senkosp artwork is
   a build-time asset swap).
2. Combo check via KOS pad read: A+Start held → test boot, else main.
3. Read the selected load from the GDI game track into staging
   `0x8cd00000` (3 MB available; loads are 1.5 MB / 311 KB). FAD
   arithmetic against a `CART_FAD` base constant shared loader/shim
   via `shim_iface.h`. All disc I/O completes before low RAM is
   touched.
4. Apply the patch table to the staged image — old-byte-verified,
   abort with an on-screen message on mismatch (`apply_patches`
   reused). The loader applies the sub-table matching the boot mode.
5. Stage the rest: `shim.bin` (+ zero its BSS), kernel slice,
   `0x60000` blob. BIOS-derived pieces are linked into the loader as
   blob objects extracted at **build time** from the gitignored
   `bios/` dump, md5-checked in the Makefile — the repo never carries
   the bytes.
6. Seed the shim state block: boot mode (test mode enables the
   Test/Service mapping), zeroed G1 + maple mirrors.
7. Handoff: dcache purge over staged regions, `irq_disable`, jump to
   the PIC stub parked high; it walks the copy records (image, shim,
   kernel, blob), invalidates I+D caches (CCR `0x0000090d`, the
   verified Cleopatra sequence), and jumps `0x8c021000`.

## Cart-streaming shim

**Intercept (register mirror, target 2).** The cart path is
base-relative: the kick in `FUN_8c027f54` stores through
base+`0x418`/`0x414` (`SB_GDST`/`SB_GDEN` as `mov.w` pool offsets
`0x8c028014`/`0x8c028016`), destination programmed a frame earlier in
`FUN_8c027a66`. One repoint of the register-base source to
`G1_MIRROR` carries the whole programming layer; the game never
touches the real, colliding GD registers. Plan pins (P1, P2): the
exact pool word(s) supplying the base, and the completion-wait
mechanism (V3-equivalent; the service hook lands there — expected
adjacent to the kick, where all 672 logged kicks sit).

**Service.** `shim_cart_service` reads `(dest, cart_offset, len)`
from the mirror, computes FAD = `CART_FAD + cart_offset/2048`, issues
a raw-ATA PIO read, copies into `dest` via **P2 uncached** (the
Cleopatra C1 cache-coherency lesson), sets mirror completion state so
the game's wait falls through. Misaligned head/tail through the 2 KB
bounce; whole sectors direct.

**Raw-ATA driver** (the new code, ~200 lines): SPI packet READ by FAD
over the ATA data port, PIO only. Primary-source references: KOS
`cdrom.c` and Flycast's gdrom core — cited in the KB when written.
Runs on its own small stack in shim home (`gdstack.S` pattern,
shrunk).

**PIO path** (`FUN_8c027d7e`, 2 boot-time seeks in the Phase 2 map):
a passive RAM mirror cannot answer data-port *reads*, so this
function gets its own entry hook — the shim performs the read into
the caller's buffer directly. ABI is a plan pin (P3).

**Throughput:** steady state ~40 KB/s (2.3 MB/min) — trivial for PIO.
Largest-single-transfer hitch risk is measured in the DC-profile legs
first; read-ahead is added only if a hitch is observed (`ponytail:`
ceiling noted in the shim source).

## Input / EEPROM maple shim

**Same mirror pattern (target 5).** The game gets its maple base from
one accessor (`FUN_8c026b30`, pool `0xa05f6c00`); repointing that
pool word to the maple mirror makes the engine — descriptor
programming and the `SB_MDST` kick at `0x8c025446` — drive shim RAM.
The hook lands at the kick: `shim_maple_service` walks the descriptor
just programmed into the mirror, performs the **real** maple work
itself (GetCondition frames to ports A and B from `MAPLE_TX/RX` —
Cleopatra `maple.c`), synthesizes each MIE reply into the game's live
recv address, and marks the mirror done. The game's decode path runs
unmodified on the synthesized frames.

Per subcommand:

- **Sub `0x33`** (per-frame poll — Phase 4 flag 9): DC pad state →
  `dc_to_jvs` → JVS has-data frame, checksum recomputed. Bindings:
  the user-approved layout (`docs/kb/input-map.md` §DC pad layout).
  Wire facts carry over: Barrage is plain bit `0x0080`; OverDrive
  lands on `0x0020` after the game's own descriptor remap. P1 =
  port A, P2 = port B (Cleopatra Task 17: no extra game patch).
- **Sub `0x15` + JVS enum** (boot phase, driver
  `0x8c0665fe`–`0x8c066b0f`): served from senkosp's own captured
  `MIERESP` blobs (the probe is always-on; Phase 2/3 logs contain
  them). Cleopatra's lesson stands: enum must report node-count ≥ 1
  or the game never emits the per-frame poll. Whether senkosp has a
  separate config-time TX/RX layer needing its own fn-ptr repoints
  (Cleopatra Task 15c) is a plan pin (P4).
- **Sub `0x01`/`0x03`** (EEPROM reads): answered from a baked
  128-byte senkosp EEPROM image with **free-play set**, built from
  the test-menu leg's captured traffic.
- **Sub `0x0b`** (EEPROM writes — call site unknown, flag 10):
  accepted into the shim's RAM copy; test-menu settings stick for the
  session, never persisted. **No VMU writes ever** — arcade parity
  and the Phase 6 tripwires by construction. If free-play needs a
  Cleopatra-style settings-struct pin, it is discovered in testing
  and added as one patch.

**Test/Service:** only in a test boot does the shim map two DC
buttons onto Test (bit 18) / Service (`0x4000`) for menu navigation.
In a main boot those bits are never set.

## Patch table & build system

**One table, one schema.** Cleopatra's `build_patch_table.py` entry
types (hook / pool / ptr / insn16) with raw `.dat`-offset addressing
(Phase 4 flag 7) plus an image tag (`main`/`test`); the loader
translates `.dat` offset → staging offset by subtracting the load
base (`0x0` / `0x171ff8`). The 4 relocation words fold in as data
entries with `scripts/reloc_patchset.json` as the single source (the
generator imports it), so the dry-run workflow and the disc build
cannot diverge.

Known entries: 4 reloc words; maple-base repoint (both images);
cart-base repoint(s); three hooks (cart service, maple service, PIO
path); restart-stub jump → reboot (locate in both images — the
stub's offset fits inside the test load; plan pin P5). Contingent,
added only if testing demands: I/O-spec check force, free-play
struct pin (both with Cleopatra precedents). Every entry
old-byte-verified at apply time.

**Build:** one `make gdi` from a clean checkout + gitignored `roms/`
+ `bios/`: extract md5-checked BIOS slices → build shim (freestanding
sh-elf, `shim.ld` at `0x8c010000`, size-asserted ≤ `0x8c018000`) →
build loader with embedded blobs → generate patch table →
`make_gdi.py` **donor-clone mastering reused verbatim** (donor tracks
1–3 + `.gdi` byte-identical; everything of ours confined to track 4:
loader + patch table + the 251 MB `.dat`; 2048-byte sectors;
AppleDouble hygiene). ROM/BIOS-derived artifacts gitignored; sources,
scripts, patch JSON committed. New tool installs (KOS toolchain)
recorded in `docs/kb/tooling.md`.

## Observability & the early fork task

Cleopatra's shim HUD — breadcrumbs, heartbeat, PC sampler,
`SHIM_ERR` block — comes over with the skeleton and is wired
**before the first boot attempt** (playbook gotcha: build on-screen
observability early).

Early fork task (Decision 2): `maple_DoDma` caller tag + `r15`
water-mark probe; re-run the PC leg on the Naomi profile; update
Phase 3 docs (`00-status.md` criterion 2 → `[x]`, EEPROM write site
named in `boot-binary.md`). Optional cheap cleanup while there:
criterion 4's fresh-checkout Ghidra re-run.

## Open questions the plan must resolve (pins)

- **O1 — shim home proof.** A V2-style write-watch leg proving the
  game never writes `0x8c010000`–`0x8c018000` (harness exists;
  Cleopatra §V2 method). Fallback if dirty or too small: carve the
  heap top by lowering the seed — that abandons the proven rigid
  16 MB shift (24-low-bit preservation) and requires re-running the
  dry-run campaign; strictly plan B.
- **P1** — the pool word(s) supplying the cart register base.
- **P2** — senkosp's cart completion-wait mechanism (V3-equivalent).
- **P3** — `FUN_8c027d7e` PIO-path ABI.
- **P4** — whether the boot-phase maple driver needs its own
  fn-ptr repoints or the base repoint covers it.
- **P5** — the restart stub's location in the test image.

## Exit criteria (the gate)

Evidence named per criterion, same discipline as Phases 2–3:

1. The built GDI boots in Flycast's **DC profile** to attract
   (screenshot in KB).
2. Full 1P match played with the approved pad layout (operator
   report).
3. 2P match entry and play (operator report).
4. Test-menu round trip: combo boot → navigate → exit → reboot lands
   in a main boot (operator report / screenshots).
5. Free-play: Start alone credits and starts (charter requirement).
6. VMU-safety preview: the Cleopatra static maple-literal scan runs
   clean over every loader/shim object (Phase 6 tripwire, run early).
7. One-command reproducible build (`make gdi`) from a clean checkout
   plus gitignored ROM/BIOS, recorded in `tooling.md`.
8. `docs/kb/00-status.md` advanced to Phase 5, carrying the honest
   limit verbatim: emulator green ≠ hardware — Phase 5 owns that.

## Out of scope

Real-hardware testing and fit (Phase 5); the full VMU tripwire
campaign and release packaging (Phase 6); asset cutting/compression
(charter: last resort, not triggered — all content fits as volume);
the shared port-kit extraction (deferred, reuse spec).

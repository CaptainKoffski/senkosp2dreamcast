# Relocation map — senkosp (Phase 3, target 3)

Provenance of every above-cap placement (the 5 above-16m main-RAM corridors,
`docs/kb/cart-streaming-map.md`; VRAM/FB), the below-cap free-space layout,
and the patch set (`scripts/reloc_patchset.json`) that Tasks 11–12 apply and
dry-run. Addresses are P1 (`0x8c…`) unless noted; phys = addr `& 0x1fffffff`;
main offset = phys − `0x0c000000`; file offset into `senkosp.dat` = P1 −
`0x8c020000` (boot image only — `tools/boot.bin` is byte-identical to the
first 1,515,512 B of `senkosp.dat`, verified `head -c 1515512 senkosp.dat |
cmp - tools/boot.bin`).

Evidence tooling: `scripts/ghidra/run.sh script
{Decomp,FindRefsTo,DisasmRange}.java` against project `senkosp3`
(image `0x8c020000`–`0x8c191ff7`), plus direct byte reads of
`tools/boot.bin`/`senkosp.dat`. Every pool word quoted below was read
byte-for-byte out of the image; every dynamic number comes from
`captures/phase3/pc.log` or the Phase 2 logs as cited. Task 10b added a
**32 MB main-RAM snapshot** of the running game (`tools/ram-snapshot.bin`,
gitignored; carved from a Flycast AutoSaveState — recipe + carve control
tests in tooling.md §Phase 3) imported as Ghidra program `senkosp3ram`
(base `0x8c000000`, `-noanalysis`); "live"/"snapshot" values below come
from it.

---

## §Provenance

### The central finding: the five corridors have ONE provenance site

No corridor destination exists anywhere in the game as a constant. Two
exhaustive scans prove it:

- **Exact-dest scan.** The 59 unique `PCPAIR` dests (`tools/pc-parse.txt`)
  were searched as u32 LE words over the whole boot image and the whole
  251 MB `senkosp.dat`, matching on `word & 0x1fffffff` (catches every
  P0/P1/P2 mirror form). Boot image: **0 hits**. Full `.dat`: 6 hits, every
  one a non-pointer-shaped word (`0x4db320e0`, `0xedc61100`, …) in asset
  data — mask coincidences, not addresses.
- **Corridor-range scans** (`tools/place-boot.txt`, `tools/place-dat.txt`,
  Task 5) contain only mask noise for the corridors. The controller-flagged
  corridor-5 case (ruling: "find the streamed table or document the gap")
  resolves by arithmetic: the scan window is 0x800 B wide, so the expected
  false-positive count over the `.dat`'s 62,835,712 words is
  62,835,712 × (8 × 0x800 / 2³²) ≈ **240**; observed: **249**. The 249
  `corridor5` DATHITs are noise. There is no streamed placement table —
  for corridor 5 or any other.

The destinations are **computed at runtime by the game's single heap
allocator**, and the whole allocation layout derives from one seed constant.
Chain of evidence, walked from the confirmed DMA kick upward:

1. **Kick → GDSTAR writer.** All 672 kicks are the `SB_GDST` store at
   `0x8c027f72` in `FUN_8c027f54` (boot-binary.md §Dynamic reconciliation).
   The main-RAM dest is programmed one frame earlier in **`FUN_8c027a66`**
   (`0x8c027a66`–`0x8c027b5d`): `*(base + [0x8c027bd2]) = param_1[2]` with
   the `mov.w` pool `0x8c027bd2` = `0x0404` = **`SB_GDSTAR`** (likewise
   `0x8c027bd4` = `0x0408` `SB_GDLEN`, `0x8c027bd6` = `0x040c` `SB_GDDIR`).
   Decoding every `mov.w @(disp,PC)` against every candidate halfword finds
   exactly one other reachable GDSTAR/GDLEN/GDDIR pool triple in the image —
   `0x8c027e06/08/0a` in the chunked-read path `FUN_8c027d7e`, which kicks
   `SB_GDST` itself and accounts for **zero** of the 672 logged kicks (all
   672 carry `FUN_8c027f54`'s PC), so the dynamic evidence pins
   `FUN_8c027a66` as the live path. It then calls `FUN_8c027f54` — the
   confirmed kick. So the dest is `param_1[2]` of a request
   `(sector, count, dest)`.
2. **Request → GD-syscall layer.** `FUN_8c027a66` is entry **17 = 0x11**
   of a 48-slot command table at `0x8c06532c` (dispatcher `FUN_8c06530c`),
   drained by the **cart server task `FUN_8c027894`**, and fed by
   `FUN_8c027520` (ReqCmd: copies per-command argc words into the device
   object at `0x8c193e04` = pool `0x8c0275e4`, the only reference — all
   access goes through the accessor `FUN_8c027514`). This is a
   re-implementation of the Dreamcast GD-ROM syscall request/status model
   over the cart: the cart byte offset is computed as
   `(sector − 0xb05e) * 0x800 + [0x8c170d20]` with `[0x8c027e10]` =
   `0xffff4fa2` (= −0xb05e) and `[0x8c170d20]` = `0x00800000` — i.e. GD-ROM
   **LBA 45150** (high-density area base) maps to cart offset `0x800000`,
   exactly where every streamed cart offset in `cart-streaming-map.csv`
   begins. The first `PCPAIR` dest `0x0c193f60` is the device object's own
   sector buffer (`0x8c193e04 + 0x15c`).
3. **Syscall layer → GDFS → game.** The client wrapper `0x8c021846`
   (in the syscall-glue block `0x8c0212xx`–`0x8c021axx`, reached through
   the config block at `0x8c170c14`) masks the caller's buffer pointer with
   `[0x8c021a24]` = `0x1fffffff` (why every logged dest is phys-form) and
   issues cmd 0x11 (DMA) or 0x10 (PIO). Its **only** reference is the
   function table at `0x8c15b344` — the **GDFS** filesystem vtable (the
   "GDFS Error"/"Illegal File Name" strings sit directly above it at
   `0x8c15b2c4`–`0x8c15b318`). Game code reads files; the dest is whatever
   buffer the game passes.
4. **The buffers come from one heap.** The game's allocator entry is
   `FUN_8c069844` (~100 call sites across the game code; retry loop around
   an out-of-memory handler). It dispatches through the current heap object
   (`[[0x8c195f5c]]`), installed by `heap_set` = `0x8c02d1d2`. The library
   default instance carries the vtable `0x8c15c970` whose version string —
   `"\nsyMalloc Ver 2.01 Build:Aug 09 …"` at `0x8c15c980` — names the
   allocator (Sega's `syMalloc`). The game installs its own instance:
   descriptor `0x8c1cecb4`
   (BSS), methods `0x8c0700f4`/`0x8c06ff18`/`0x8c070100`/`0x8c07010c`,
   arena ring built by `FUN_8c06fd60`. Sub-heaps (`0x8c06fe30`) carve their
   arena out of an allocation from this same heap — there is **no second
   absolute-address seed anywhere**.
5. **The arena and its one seed.** The heap is created once, in the system
   init `FUN_8c085b00`, verbatim disassembly (`DisasmRange.java`):

   ```
   8c085b3a  mov.l 0x8c085bc4,r0    ; r0 = 0x8c15ae68 (pool)
   8c085b3c  mov.l @r0,r4           ; r4 = [0x8c15ae68] = 0x8c1de200  (base: BSS end)
   8c085b3e  mov #0x0,r0
   8c085b40  or #0x80,r0
   8c085b42  shll16 r0
   8c085b44  shll8 r0               ; r0 = 0x80000000
   8c085b46  or r0,r4               ; P1 form
   8c085b48  add #0x1f,r4
   8c085b4a  mov #-0x20,r0
   8c085b4c  and r0,r4              ; align 32
   8c085b4e  mov #0x0,r0
   8c085b50  or #0x8e,r0            ; <== THE SEED (0xcb8e)
   8c085b52  shll16 r0
   8c085b54  shll8 r0               ; r0 = 0x8e000000 = top of Naomi 32 MB
   8c085b56  sub r4,r0
   8c085b58  mov r0,r5              ; size = 0x8e000000 - base
   8c085b5a  mov.l 0x8c085bc8,r0    ; = 0x8c06fda8 (heap create + heap_set)
   8c085b5c  jsr @r0                ; heap_create(base=0x8c1de200, size)
   ```

   **Heap = `[0x8c1de200, 0x8e000000)`** — from the end of static BSS
   (`[0x8c15ae68]` = `0x8c1de200`, a statically initialized data word, the
   same value the startup BSS-clear bounds table ends at) to the top of the
   Naomi 32 MB main RAM.
6. **Why every corridor sits high: the allocator hands out block *tails*.**
   The game heap's alloc method (`0x8c0700f4` → thunk `0x8c06fe6c` →
   **`FUN_8c06fe80`**, `0x8c06fe80`–`0x8c06ff0f`): on a first-fit hit it
   shrinks the free node (`node[2] -= units+1`) and carves the new block
   from the node's *top end* (header at `node + remaining*0x20 + 0x20`,
   payload `0x20` above it). (The
   library-default syMalloc instance, `0x8c02d26e` family, allocates tails
   the same way; the game instance is the one live at runtime.) All address
   arithmetic is node-relative — no absolute-address decisions — so the
   layout is translation-invariant given the same arena and request
   sequence. The arena starts as one free block, so the earliest
   (boot-time) allocations get the highest addresses and the heap grows
   *downward*. That matches the dynamic map
   exactly: corridor 5 (a boot-time GDFS 2 KB bounce buffer, 24 × 0x800-B
   reads of cart `0x808000`–`0x815000` = LBA 45166+, the filesystem
   directory area) sits highest at `0x0dfe6d20`; the deepest the heap ever
   grew over the whole 14-leg campaign is corridor 1's floor `0x0d244c20`;
   and *nothing* was ever written between 16 MB and that floor (Phase 2
   `MAINHIST` above-cap buckets begin at #73/`0x1240000`).
7. **The seed is unique.** Constant scans cannot see immediate+shift
   materializations, so the whole image was swept for every way of building
   a RAM-top constant: `or #imm,r0` (`0xcbnn`) and `mov #imm,rN` (`0xeNnn`)
   for imm ∈ {0x8e, 0x8d, 0x0e, 0x0d} followed by `shll16`/`shll8` on the
   same register, `mov.w` pools holding `0x8e00`/`0x0e00`/`0x8d00`, and u32
   pool words `0x8e000000`/`0x8dffffff`/`0xae000000`. Result: **exactly one
   live site — `0x8c085b50`**. (The three `mov #0xd,r0`+shifts candidates at
   `0x8c0f2ce2`/`0x8c0f30dc`/`0x8c0f312e` are struct-offset builds
   (`0xd78`/`0xd6c`…) whose later shifts belong to an `0x00ff0000`-mask
   materialization — checked by disassembly. The `mov.w 0x0e00` load at
   `0x8c02e232` is a bank threshold in the MMU-window address codec, see
   §What is deliberately not patched.)
8. **The `.dat` ships a second program — the test image — with its own
   copy of the seed.** The Test load entry (ROM `0x171ff8` → RAM
   `0x8c020000`, `0x4dc40` B, entry `0x8c021000` — `docs/kb/game.md`
   §Parsed .dat header) contains a verbatim copy of the heap-create
   function: the 180-byte run `dat 0x1af844`–`0x1af8f8` is byte-identical
   to boot `0x65b00`–`0x65bb4` (`cmp`-verified), putting the same
   `or #0x8e,r0; shll16` word at **dat `0x1af894`** = test-RAM
   `0x8c05d89c`. The same idiom sweep over the whole test image finds
   exactly that one seed. It gets the second patch entry so that test mode
   (service menu boots the test entry) runs against the same 16 MB heap
   top — otherwise any future test-mode leg would produce above-16m dests
   that falsely indict the main patch.

### Per-corridor classification

Classification per the plan's taxonomy: **all five are `computed`** —
deterministic allocations from the single arena above. There are no
pool-constant or table sites to patch per corridor; the one seed covers all
five (and every other heap allocation) at once.

| # | Extent (main offset) | Size | Classification | Role (evidence) | Post-patch extent |
|---|---|---|---|---|---|
| 1 | `0x1244c20`–`0x1d73e00` | 11.18 MB | computed (heap) | Dominant streaming corridor: character/stage assets, every roster leg + attract. Its floor is the campaign-wide heap low-water mark. | `0x244c20`–`0xd73e00` |
| 2 | `0x1d7d020`–`0x1d92020` | 84 KB | computed (heap) | In-play-only buffers (absent from attract). | `0xd7d020`–`0xd92020` |
| 3 | `0x1dc2960`–`0x1de3960` | 132 KB | computed (heap) | In-play + attract, same shape as #1 but small. | `0xdc2960`–`0xde3960` |
| 4 | `0x1e4dbe0`–`0x1e8b480` | 246 KB | computed (heap) | Hot re-stream ring (1,263 requests, ~189× reuse): six `0x9800` slots + a `0x4800` tail + a `0x31000` block, the whole family's base moving in `0x1000` steps between matches — allocator churn, not a fixed object. **Owner:** requests are executed by the cart server task `FUN_8c027894` on the stack whose top is `0x8c1d4b64` (the `[0x8c085bbc]`=`0x8c1cfb64`+`0x5000` argument `FUN_8c085b00` passes at task setup — the 554-sample SP cluster `0x8c1d4984` sits 0x1e0 below it). The game-side requester is behind the GDFS file API and was not named statically; it is not needed for relocation, since the ring is heap-allocated like everything else. | `0xe4dbe0`–`0xe8b480` |
| 5 | `0x1fe6d20`–`0x1fe7520` | 2 KB | computed (heap) | Boot-time GDFS bounce buffer (single 0x800-B dest, 24 sequential directory-area reads). Highest allocation observed = one of the first made. | `0xfe6d20`–`0xfe7520` |

### Relative alignment (constraint: keep low bits)

The patch moves the arena **top** from `0x8e000000` to `0x8d000000` — a
shift of exactly `0x1000000`, which is 16 MB-aligned. Base and allocation
sequence are untouched, so every allocation lands at `old − 0x1000000`:
**all 24 low bits of every buffer address are preserved**, which preserves
every alignment the game could assume up to 16 MB (the allocator's own
granularity is 0x20; DMA lengths are 0x20-multiples; sector buffers are
0x800-aligned — all ⊆ 2²⁴). Each span moves rigidly, so contiguity is
preserved by construction.

### VRAM/FB

**Framebuffers — dynamic ground truth** (`captures/phase3/pc.log` `SOFWR`
lines; counts are cap-saturated per boot-binary.md §SOFWR and are used only
as value evidence):

| Register | Values seen (VRAM offsets) | Meaning |
|---|---|---|
| `FB_W_SOF1` | `0x2ea000` ⇄ `0x6ea000` (also once `0x800000`) | render target, double-buffered pair in banks 0/1 (stride `0x400000`) |
| `FB_W_SOF2` | `0xc00000` (once) | second write pointer, upper pair |
| `FB_R_SOF1` | mostly `0x800000` ⇄ `0xc00000`, briefly `0x2ea000` | scan-out, mostly from the **upper** pair |
| `FB_R_SOF2` | `R_SOF1 + 0x500` | interlace field (one 640×2-byte line offset) |

`VRAMREGS` (same log): `isp_base=0 isp_limit=0x2200e0 ol_base=0x2d5680` —
the TA ISP/object-list buffers occupy the bottom of VRAM.

**Writers: two disjoint populations, split exactly along the 8 MB line.**
Cross-tabulating every `SOFWR` line's `pc=` against its `val=`:

| PC | Lines | Values carried |
|---|---|---|
| `8c032146` (P1) | 446 | **only** the below-8m pair `0x2ea000`/`0x6ea000` (±`0x500`) |
| `0c0548da`/`0c0548e4`/`0c054da8`/`0c0558ea` (P0) | 1,155 | **all** of the above-8m `0x800000`/`0xc00000` (±`0x500`) writes — and nothing else |

The P1 site is the single store `0x8c032146` in `FUN_8c032140` — a
two-instruction PVR register poke (`*(reg + [0x8c032160]=0xa05f8000) =
val`). Callers seen in `pr=`: `FUN_8c03baa0` (per-frame flip; writes reg
`0x60`=`FB_W_SOF1`) and `FUN_8c0372d6` (display init; writes
`0x50`/`0x54`/`0x60`/`0x64` = `FB_R_SOF1/2`, `FB_W_SOF1/2` — offsets per
`../flycast4naomi2dreamcast/core/hw/pvr/pvr_regs.h:31-36`). Both take the
addresses from display-buffer descriptors (field `+0x1c`), built inside the
graphics library.

**The P0 population is a probe artifact, not overlay code — settled by the
Task 10b RAM snapshot.** Task 10 conjectured runtime-resident code differing
from the boot image at those PCs. The 32 MB main-RAM snapshot
(`tools/ram-snapshot.bin`, carve recipe in tooling.md §Phase 3) refutes it:
across the whole loaded image span only **907 bytes** differ from the boot
load — all in initialized-data cells (`0x8c170cxx` config, `0x8c17dxxx`,
`0x8c18xxxx` tables) — and the bytes at and around *every* SOFWR P0 PC
(`0c0548da/e4`, `0c054da8`, `0c0558ea`, and the canary-leg set
`0c0551c0/d0/d8`) are **byte-identical to the boot image**. There is no
overlay. The static bytes at `pc−2` are `cmp/eq`/pool-loads inside
`ldc SR` interrupt-masked critical sections of the command-packet library
(`0x8c054xxx`–`0x8c05axxx`), and the `pr=` values are similarly off-by-4
from any real `jsr` — the P0 pc/pr pairs do not obey the `+2` rule and are
**unattributable samples** (boot-binary.md §maple-trigger artifact already
classed them with the maple P0 population). The game runs its tasks in the
P0 mirror under the Naomi BIOS's resident RTOS kernel (low RAM
`0x0c000600`–`0x0c007xxx`, byte-identical to BIOS ROM `epr-21576h.ic27`
at ROM offset − 0x800; VBR+0x600 stub at `0x0c000600` → INTEVT dispatcher
`0x0c001cba` → per-task 0x200-byte TCBs at `0x0c004000`), which is why
these sampled PCs render in P0 form. The fork mechanism that makes a
synchronous FB-reg store log a non-store PC was not pinned (candidate:
pc staleness across the RTOS context-switch/`rte` path); it does not
matter for relocation — the *value* provenance below is complete.

**The graphics library is KAMUI2** (NEC): copyright string
`"KAMUI2 Copyright (C) NEC Corporation 1999 … Ver 16,5,3,2 Build:Jun 16
2000"` at `[0x8c032030]`, referenced by the device init `FUN_8c031fee`.
That function is `kmInitDevice`: it stores the device word
(`param & [0x8c03202c]`=`0xffff0000`) at state `0x8c19e4bc` and sets
state`+0x7f8` (`mov.w` pool `0x8c0320e0` = `0x07f8`; store in the `jsr`
delay slot `0x8c032048`) = **total VRAM size**. Verbatim disassembly
(corrects Task 10, which had the branch inverted): device ==
`[0x8c032038]` = `0x00010000` (the value senkosp passes, `[0x8c03d598]`)
→ size = **`[0x8c03203c]` = `0x01000000` (16 MB, Naomi)**; any other
device → `[0x8c0320ec]` = `0x00800000` (8 MB — the library's native
Dreamcast mode). The snapshot's live state settles it: `[0x8c19e4bc]` =
`0x00010000` and state`+0x7f8` = **`0x01000000`** — senkosp runs KAMUI2 in
**16 MB Naomi VRAM mode**, and that single cell is where every above-8m
placement comes from.

**The seed and its propagation** (each hop byte-verified in image +
snapshot):

1. **One seed.** A D-opcode sweep over every `mov.l @(disp,PC)` in the
   whole image finds exactly **one** loader of the 16 MB pool
   (`0x8c032012`, in `kmInitDevice`) and one of the 8 MB pool
   (`0x8c032040`, its else-branch). All other `0x01000000` pool words are
   audited non-sources: address-bound compares (`0x8c02acb4`,
   `0x8c02b0ca/122/182` — `cmp/hi`, superset checks, harmless below 8 MB),
   a 16 MB window-mapping length (`0x8c02e650`, same class as the MMU
   window item below), bit-24 flag tests/ors (`0x8c037c84`, `0x8c03ce86`),
   an address-mode flag added to `FB_W_SOF1` values (`0x8c03bc3c` — mode
   bit, not a placement), the size *classifier* codec (`0x8c03e9ca`,
   compares only), and the two genuine dual-path consumers next.
2. **state+0x7f8 has exactly two readers** (`mov.w 0x07f8` sweep, whole
   image): **`FUN_8c02e300`** — the display/TA config function Task 10's
   trace dead-ended at — reads it at `0x8c02e332` and passes it into the
   **placement function `0x8c038aa0`**, whose body carries explicit dual
   arithmetic: `cmp/eq r6,r7` against `[0x8c038b48]`=`0x1000000`, then
   `addr += 0x1000000` (16 MB path, `0x8c038af2`) or `addr +=
   [0x8c038b50]`=`0x800000` (8 MB path, `0x8c038b02`), plus arena-limit
   list setup. And **`0x8c031b60`** — the scan-out region clamp: under a
   `size == [0x8c031c0c]=0x1000000` guard it forces state`+0x7fc` ≥
   size/2 = **`0x800000`** (`shlr`, `0x8c031b84`) — the 8 MB line itself.
3. **The live structures downstream** (snapshot): the KAMUI2 config block
   `0x8c170eb8` — which the `.dat` **file-ships with 8 MB-mode defaults**
   (`+4` = `0x00800000`, `+0x14/18/1c` = `0x00400000`) — is runtime-
   overwritten to the 16 MB values (`+4` = `0x01000000`, snapshot diff);
   the scan-out display-descriptor pair (640×480, `0x96000`) with bases
   **`0x800000`/`0xc00000`** at `0x0c291cf8`/`0x0c291d20` (base field
   `+0x1c` = `0x0c291d14`/`0x0c291d3c`); and a second KAMUI2-layout
   display state block (`0x0c2b0540`+) that duplicates the game's own SPG
   timing words (`0x8c1a00b8`+) with the FB pair swapped in at `+0x20/24`
   and one `FB_R_CTRL` bit different — i.e. the two FB pairs are a
   **compose pipeline** (render into pair A `0x2ea000/0x6ea000`, per-frame
   copy/scan-out via pair B `0x800000/0xc00000`): open question (c)
   resolves **yes, 4 FBs are live in 16 MB mode**.
4. **No table alternative exists**: the pair `{0x00800000, 0x00c00000}`
   appears nowhere in the entire 251 MB `.dat` as adjacent words, and
   `0x00c00000` never appears in either program image as a pool word —
   `0xc00000` is computed (`0x800000` + the `0x400000` bank stride,
   `[0x8c035960]`). The 64↔32 bank mapper `FUN_8c035920` is 8 MB-safe:
   its `addr ≥ [0x8c035964]=0x800000 → +0x400000` upper-half branch
   simply never fires when no placement exceeds 8 MB.

**Patch: flip the seed to the library's native DC mode.** `dat 0x1203c`
(`P1 0x8c03203c`): `0x01000000` → `0x00800000`. kmInitDevice then reports
8 MB for the Naomi device word, and every placement decision — scan-out
region base, FB descriptor bases, texture-arena limit — takes the 8 MB
branch that already ships in the binary (it is the DC configuration of
this DC-native library; the `.dat`'s own static config defaults are the
8 MB values). Unlike the main-RAM patch this is not a rigid shift: the
library *recomputes* its native below-8m layout, so alignment and low-bit
flags are its own responsibility — the same code paths every DC KAMUI2
title runs. The test image carries a verbatim kmInitDevice copy (entry
`dat 0x183b66` = test-RAM `0x8c031b6e`; loaders `d20a`/`d22a` at entry
`+0x24`/`+0x52` byte-identical, entries congruent mod 4 so the
PC-relative pools resolve to entry`+0x4e`/`+0xfe` = `dat 0x183bb4` =
`0x01000000` / `dat 0x183c64` = `0x00800000`, byte-verified) — patched as
entry 4.

**Why it matters on DC:** DC VRAM is 8 MB
(`../flycast4naomi2dreamcast/core/emulator.cpp:456`; Naomi 16 MB, `:463`)
and accesses wrap through `VRAM_MASK`
(`.../core/hw/pvr/pvr_mem.cpp:229,313,329`), so `0x800000` aliases onto
`0x000000` and `0xc00000` onto `0x400000` — directly on top of the TA
ISP/OL buffers (`0x0`–`0x2d5680`) and the low FB pair. Scan-out would
display TA garbage and texture uploads would corrupt live buffers. The
VRAM-size seed patch (entries 3–4) removes every above-8m placement at its
single source.

> **Blocker resolution (Task 10b).** The former blocker's three open
> questions closed as: (a) the `0x800000`/`0xc00000` scan-out placement is
> computed by KAMUI2's 16 MB-mode paths (region clamp `0x8c031b60` =
> size/2; placement fn `0x8c038aa0`; bank stride `0x400000`) from the one
> seed `[0x8c03203c]` — the four logged P0 PCs were probe artifacts, not
> the writer; (b) the above-8m texture content is placed by the same
> library's texture arena, whose limit derives from the same
> state`+0x7f8` size — no second seed exists (whole-image loader sweep);
> (c) the two FB pairs ARE a compose pipeline — 4 FBs live in 16 MB mode
> (two KAMUI2-layout display states in the snapshot, identical SPG
> timing, one `FB_R_CTRL` bit apart). What the patch does **not** prove
> statically: whether the library's 8 MB mode keeps the compose stage
> (needing 2×`0x96000` more below-8m budget) or scans out directly from
> the render pair as DC titles do (the file-default 8 MB config suggests
> the latter), and whether per-moment texture residency fits the ~3.9 MB
> left after TA + FBs (campaign-*union* content 5.68 MB is an upper
> bound, not a per-moment figure). Both are exactly what Task 12's
> `dryrun_vram_below_8m` measures; the library's own out-of-VRAM error
> path is the failure signature to watch.

---

## §Free-space layout

### Below-16m main RAM (post-patch)

The free-space question collapses nicely: **the game's heap is the free
space**, and the patch shrinks it to end at the DC 16 MB line. Nothing else
moves. Layout after the patch, phys addresses:

| Range (phys) | Size | Owner | Source |
|---|---|---|---|
| `0x0c000000`–`0x0c00f000` | 60 KB | boot stack (grows down from `0x0c00f000`) | boot-binary.md §Stack region |
| `0x0c00f000`–`0x0c010000` | 4 KB | VBR vectors + scratch | boot-binary.md §Stack region |
| `0x0c010000`–`0x0c018000` | 32 KB | low system area (reios/syscall vectors live below `0x0c010000`; `0x0c010000`+ referenced by the BIOS-blob vector signature) | boot-binary.md §Phase 4 note |
| `0x0c018000`–`0x0c01f000` | 28 KB | Naomi-BIOS runtime blob copy target (`FUN_8c065ff0`: `0x1c00` words to `0xac018000`) | boot-binary.md §BIOS reads, closed |
| `0x0c020000`–`0x0c191ff8` | 1.44 MB | boot image (code+data) | game.md §Parsed .dat header |
| `0x0c192000`–`0x0c1de200` | 305 KB | static BSS — includes the cart device object `0x8c193e04`, heap descriptors `0x8c1cecac`/`b0`/`b4`, KAMUI2 state `0x8c19e4bc`, and the interrupt/cart-task stack block ending at `0x8c1d4b64` (SP cluster `0x8c1d4984` lives here — the "second stack" is static BSS, which closes boot-binary.md's open bound: reserve nothing beyond BSS itself) | `[0x8c15ae60]`/`[0x8c15ae64]` BSS-clear bounds; `FUN_8c085b00` pool `0x8c085bbc` |
| `0x0c1de200`–`0x0d000000` | **14,818,816 B (14.13 MB)** | **the heap (relocated)** — all five corridors and every other dynamic allocation land here | this doc §Provenance |

Arithmetic check (all figures campaign-measured):

- Heap capacity after patch: `0x8d000000 − 0x8c1de200` = `0xe21e00` =
  **14,818,816 B**.
- Peak heap reservation ever observed (14-leg union): top-down floor =
  corridor 1 floor `0x8d244c20` ⇒ `0x8e000000 − 0x8d244c20` = `0xdbb3e0` =
  **14,398,432 B**. Confirmed from the write side: `MAINHIST` above-cap
  buckets #64–#72 (16 MB–`0x1240000`) recorded **zero** writes across the
  campaign — the heap never grew below that floor.
- **Slack: `0x66a20` = 420,384 B (~410 KB).** It fits, tightly. This is the
  number the Task 12 dry run must watch (heap exhaustion → the game's
  malloc-retry/OOM path, `FUN_8c069844`; its semaphore-failure string
  `"FATAL ERROR Cannot get semaph…"` is a known failure signature).
- No collisions by construction: every relocated allocation is inside the
  heap span, which is disjoint from image/BSS/stacks; the shift is a rigid
  translation of a layout that was internally collision-free on Naomi; and
  Phase 2's below-16m occupancy (`nz_below16m` = `0x18578c`, essentially
  image+BSS writes) lies entirely below `0x0c1de200`.

### VRAM (below-8m layout — post-patch, library-computed)

Unlike the main-RAM half, the below-8m VRAM layout is not a rigid
translation this document can tabulate address-by-address: entries 3–4
switch KAMUI2 into its native 8 MB mode and the **library recomputes**
every placement. What is known and budgeted:

| Item | Size | Post-patch expectation |
|---|---|---|
| TA ISP/OL buffers | `0x0`–`0x2d5680` (~2.8 MB) | already below 8m (`VRAMREGS`); game-configured, size-independent — unchanged |
| FB pair A (render, was `0x2ea000`/`0x6ea000`) | 2 × `0x96000` (640×480×16bpp) | already below 8m; library re-places it in 8 MB mode |
| FB pair B (scan-out, was `0x800000`/`0xc00000`) | 2 × `0x96000` | 16 MB-mode compose stage; the 8 MB path either drops it (direct scan-out from pair A — the DC-normal arrangement the file-default config describes) or re-places it below 8m |
| Texture content (was 4.4 MB above + 1.0 MB below 8m) | ≤ `0x5699ef` (5.68 MB) union — see note | arena limit recomputed from size; all placements below 8m |

Budget arithmetic: TA (`0x2d5680` = 2.96 MB) + pair A (1.17 MB) leaves
**~3.9 MB** of texture space if the compose pair persists below 8m, or
**~5.1 MB** if 8 MB mode scans out directly from pair A. The campaign
**union** of texture content is 5.68 MB (`0x4697c3` above + `0x10022c`
below), but that is a 14-leg union, not per-moment residency; Phase 2's
scored per-moment fit (`content+2×fb` = 7,239,988 / 8,388,608, u 0.863)
excluded the TA regions. The honest statement: **placement authority is
resolved below 8 MB by construction; peak simultaneous occupancy is the
measured question Task 12 answers** (`VRAMHIST` above-8m buckets must go
to zero; watch the library's out-of-VRAM error path for pressure).

---

## §Patch set

`scripts/reloc_patchset.json` — **four entries** (schema: u32 LE words;
`dat_offset` = P1 − `0x8c020000` for boot-image sites [entries 1, 3]; the
test-image sites [entries 2, 4] use their own raw `.dat` offset directly):

| dat_offset | old | new | What |
|---|---|---|---|
| `0x65b50` | `0x4028cb8e` | `0x4028cb8d` | Main image, `0x8c085b50`: `or #0x8e,r0` → `or #0x8d,r0` (low halfword of the LE word; the `0x4028` = `shll16 r0` upper halfword is unchanged). Heap top `0x8e000000` → `0x8d000000`. Covers **all five corridors** via the single-seed mechanism proven in §Provenance. |
| `0x1af894` | `0x4028cb8e` | `0x4028cb8d` | Test image, test-RAM `0x8c05d89c`: the verbatim copy of the same seed (§Provenance item 8). Same one-halfword change, so test mode gets the same 16 MB heap top. |
| `0x1203c` | `0x01000000` | `0x00800000` | Main image, `0x8c03203c`: kmInitDevice's 16 MB VRAM-size pool (device `0x00010000`/Naomi branch) → 8 MB. Single seed for **every above-8m VRAM placement** (scan-out FB pair, texture arena) — §Provenance → VRAM/FB. The library's 8 MB (DC-native) paths ship in the binary and take over. |
| `0x183bb4` | `0x01000000` | `0x00800000` | Test image, test-RAM pool `0x8c031bbc` (kmInitDevice copy at entry `0x8c031b6e`, pools at entry`+0x4e`): same one-word change for the service/test menu. |

Old values verified against `senkosp.dat` byte-for-byte
(`python3` verify loop; the applier re-checks).

### Deliberately not patched (each checked, with reason)

- **Reset stub** (`FUN_8c067e18`): copies `0x60c` B from `0x8c180904` to
  `0xadfff000` (pool `0x8c067e3c`) and jumps to `0x8dfff000` (pool
  `0x8c067e4c`); 24 internal words reference its own `0x8dfffxxx` page, and
  it ends by jumping into **Naomi BIOS code** (`0xa0082262`, `0xa01935ec`,
  `0xa0039310` — phys < `0x200000`). This is the game-restart path (runs on
  test-menu exit; explains the campaign's `main` high-water `0x1ffffa5`
  inside the top page). Shifting its constants cannot make it work on DC —
  it re-enters a BIOS that is not there. **Phase 4 must own restart**
  (intercept the stub or replace the jump with a loader re-entry). On DC
  the stub's top-page writes mirror into `0x0cfff000` (post-patch heap
  top) — acceptable only because the path is a reboot anyway; flagged for
  the Phase 4 loader design.
- **Address checker** bring-up (`FUN_8c02c43c`): programs a valid-range of
  `[0x0c000000, 0x0dffffff]` (`[0x8c02c500]`, pool `0x8c02c4fc`). A
  superset of post-patch usage — allowing the unused upper 16 MB traps
  nothing that exists. No patch needed.
- **MMU window mapper** (`FUN_8c02e0e0`, gated on `MMUCR` `0xff000010`):
  maps phys `0x0c000000`–`0x0e000000` in 1 MB steps into virtual
  `0xe0000000`+ (and TA FIFO `0x10000000`+ into `0xe2000000`+); the
  companion codecs `FUN_8c02e210`/`FUN_8c02e256` translate
  address ⇄ `0xE0/E1/E2`-window forms with thresholds at 16 MB
  (`[0x8c02e2a4]` = `0x8d000000`) and 32 MB (`mov.w` `0x0e00` at
  `0x8c02e232`). Post-patch, no pointer in the `0x8d`/`0xE1` window is ever
  produced, so the codec round-trips consistently and the extra mapping is
  a harmless unused alias. No patch needed.
- **VRAM/FB scan-out region hint** `state+0x7fc` (live `0x900000`): written
  only inside the clamp fn `0x8c031b60` (both `mov.w 0x07fc` loaders in the
  whole image are in that function); post-patch the 16 MB guard fails and
  the caller's value stands unclamped. No other reader found — flagged for
  the Task 12 dry run, not patched. **Task 12 closes this**: `FB_R_SOF1`/
  `FB_W_SOF1` do briefly carry above-cap values from this or a related
  pre-handoff path, but only in the deterministic boot window before the
  first per-frame flip (`pc=8c032140`), which supersedes them for the rest
  of every leg — see §Dry-run evidence → Boot-transient finding.
- **Bank mapper `FUN_8c035920`** (`0x400000` stride / `0x800000` half
  pools): the upper-half branch is dead once no placement exceeds 8 MB —
  superset logic, no patch needed (same class as the address checker).

---

## §Dry-run evidence

Three legs against `senkosp-reloc.dat` (`md5 a80f03676c0595bcae1bebcc5f16f884`,
same 251,342,848 B size as `senkosp.dat`; `apply_reloc.py` reported
`patched 4 words -> senkosp-reloc.dat`, exit 0, matching the 4-entry patch
set): `captures/phase3/dryrun-attract.log` (660 s unattended, 1,080,610
lines), `captures/phase3/dryrun-play.log` (operator-played, boot → coin →
one full match, 2,067,273 lines), and a bonus corroboration leg —
`captures/phase3/dryrun-attract-2-unattended.log` (1,024,458 lines).
**Mislabel note (honesty record):** the third leg was launched intending a
second play session but the operator stepped away before providing input;
the resulting log is a second unattended-attract capture in substance
(coin never inserted), originally saved under a play-leg name and renamed
to `dryrun-attract-2-unattended` to match what it actually captured — see
`tooling.md` for the exact rename.

### Gate run (Step 4)

```
python3 scripts/parse_cartlog.py captures/phase3/dryrun-attract.log captures/phase3/dryrun-play.log \
    --dryrun captures/attract.log > tools/dryrun-parse.txt; echo "exit=$?"
```

`exit=0`. CHECK lines (verbatim, all Phase 2 CHECKs plus the three dry-run
CHECKs; full output `tools/dryrun-parse.txt`):

```
CHECK dest_known: PASS — every DMA dest in a known window (main/vram/aram/ta); 0 outside
CHECK len_aligned_32: PASS — every DMA len a whole number of 0x20-byte DMA_COUNT units
CHECK beyond_boot_read: PASS — at least one cart read past the 1 MB boot region (runtime streaming)
CHECK main_watermark_boot: PASS — main watermark 0xffffa5 >= boot-load end 0x191ff8
CHECK no_bios_exec: PASS — 0 BIOSEXEC lines (expect 0)
CHECK dryrun_main_below_16m: PASS — 0 main DMA(s) with dest+len above 16m; MAINPROFILE high=0xffffa5 (cap 0x1000000)
CHECK dryrun_vram_below_8m: PASS — VRAMPROFILE content_high=0x756120 (cap 0x800000); 0 SOF reg(s) above cap and not exempt []
CHECK dryrun_stream_shape: PASS — dryrun-attract: 205 (src,len) events match the anchor leg's multiset; exempt from shape (no anchor for interactive play, caps-only): dryrun-play
```

Phase 2 regression: flagless re-parse (`captures/*.log --attract-leg
attract`) still `exit=0`, all Phase 2 CHECKs unchanged, and
`docs/kb/cart-streaming-map.csv` regenerates byte-identical to the
committed copy — the ruling-A/B code changes touch only `dryrun_checks()`.

### Watermarks per leg (running-max write-truth, `MAINPROFILE`/`VRAMPROFILE`)

| Leg | MAINPROFILE high | nz_above16m | VRAMPROFILE content_high | content_above8m |
|---|---|---|---|---|
| `dryrun-attract` | `0xffffa5` | `0` | `0x5c4ad1` (5.77 MB) | `0` |
| `dryrun-play` | `0xffffa5` | `0` | `0x756120` (7.34 MB) | `0` |
| `dryrun-attract-2-unattended` | `0xffffa5` | `0` | `0x5c4ad1` (5.77 MB) | `0` |

Main-RAM headroom at peak: `0x1000000 − 0xffffa5` = 91 B — the patch lands
the heap's top-down allocations essentially flush against the DC 16 MB
line (expected: the shift is rigid, and corridor 5, the campaign's highest
allocation, was already the shallowest below the old 32 MB top).

**Play-leg VRAM watermark answers Task 10b's per-moment-fit open question.**
`content_high=0x756120` is the *measured*, in-play, single-leg peak (not the
14-leg campaign union of 5.68 MB from Phase 2) — `0x800000 − 0x756120` =
`0x6a020` = **696,032 B (~680 KB) of headroom** against the DC 8 MB VRAM cap
at the highest-pressure moment observed (full match). The two unattended
attract legs corroborate each other exactly (`0x5c4ad1` both, `content_above8m=0`
both) — same demo-loop content ceiling, reproduced independently.

### Operator playability report (verbatim)

> Everything looks and plays normal, except on moment. I see lags from time
> to time, once in ~10s the game hangs for about half of a second. I see
> this all the time, attract, character selection, real gameplay. I'm not
> sure if it is because of emulator or not, but I tried the original gdi
> rom with vanilla flycast and saw no lags.

**Lag root cause: the cartlog instrument's own periodic scan, not the
patch or the game.** `cartlog_profiles_tick()`
(`../cleopatra/tools/flycast-src/core/hw/naomi/naomi.cpp:441-448`) samples
every 600 vblanks — "~10 s" per its own comment (naomi.cpp:440) — matching
the operator's "once in ~10s" exactly. Each sample byte-scans the full 32 MB
main-RAM array + 16 MB VRAM array + ARAM + a 4 MB shim-watch window on the
**emulation thread** (`cartlog_sample()`, naomi.cpp:399-415, calling
`cartlog_shimwatch()` naomi.cpp:382-397 and `cartlog_vram_profile()`
naomi.cpp:243-290) — a >50 MB linear scan blocking guest execution, which is
the half-second stutter. This runs unconditionally, independent of the
relocation patch: same function, same cadence, in every Phase 1/2/3
instrumented leg to date (confirmed by code reading — `cartlog_sample()`
carries no patch-set or dry-run conditional).

**The patch is exonerated by traffic-count comparison**, unpatched
`captures/attract.log` (Phase 2) vs patched `captures/phase3/dryrun-attract.log`
(same 660 s window, reproduced from the logs, not copied from any prior
report):

| Instrument class | Unpatched (attract.log) | Patched (dryrun-attract.log) | Diff |
|---|---|---|---|
| `CARTDMA` | 205 | 205 | 0 |
| `PVRW` | 343,656 | 342,828 | 0.24% |
| `C2D` | 76,458 | 76,273 | 0.24% |
| `TAREG` | 76,792 | 76,608 | 0.24% |
| `SOFWR` | 1,601 | 1,601 | 0 |

Traffic is unchanged within noise — the stutter the operator sees was
already present in what the instrument measures before the patch; the
relocation is not adding load.

**Control test CLOSED — the lag is the instrument, and the patch is fully
exonerated (2026-08-22).** The single-variable A/B was run by the operator:
same instrumented fork, same `senkosp-reloc.dat`, `FLYCAST_CARTLOG` **unset**
(cartlog logging OFF, so `cartlog_profiles_tick()` never scans). Operator
verdict, verbatim:

> no lags anymore, all smooth

One variable changed (logging on → off); the patched image, the fork build
and the machine were identical to the lagging runs. That isolates the
~10 s stutter to `cartlog_profiles_tick()`'s >50 MB periodic scan and rules
out the relocation patch as a cause. Recipe + this closure are mirrored in
`tooling.md` §Phase 3 relocation dry run.

**Operator visual confirmation — complete, in two dated parts.** The spec's
operator-observed playability leg (§Cross-checks: "Playability itself is
operator-observed — boot → attract → one played match") is satisfied by two
separate observations, and neither is a 2026-08-22 fresh viewing:

- **(a) The played match, 2026-08-21** (Task 12, the §Operator playability
  report above — quoted there in full). The operator watched the patched
  image through boot/attract/character-selection and real gameplay. Its
  opening clause is the visual verdict — *"Everything looks and plays normal,
  except on moment…"* — and the sentence does **not** end there: the "except"
  is the ~10 s lag caveat, which is why that clause must never be quoted
  alone. Content, colour, geometry and playability: normal. One caveat:
  periodic stutter.
- **(b) The caveat's closure, 2026-08-22** (the control test immediately
  above): *"no lags anymore, all smooth"* — the stutter was the instrument,
  not the image.

(a) covers what the eye sees, (b) removes the only reservation (a) carried.
Together with the traffic-count table above and the caps evidence below, the
playability leg is satisfied on the patched image.

> **Provenance correction (Task 13 review).** An earlier pass of this
> section dated the visual confirmation 2026-08-22 and quoted
> *"everything looks and plays normal"* as a standalone verbatim verdict
> from the control-test session. Both were wrong: `git log -S` puts that
> sentence in commit `902f9e3` (2026-08-21, Task 12), it is the **opening
> clause** of the report above rather than a whole sentence, and the
> control-test session produced only the lag quote. Corrected here, in
> `tooling.md` and in `00-status.md`.

### FB_W_SOF2 exemption (`dryrun_vram_below_8m`, ruling A)

The unexempted check FAILs on `dryrun-attract:fb_w_sof2=0xc00000` /
`dryrun-play:fb_w_sof2=0xc00000` (both legs' final `VRAMREGS` snapshot).
Full evidence chain, each piece verified independently against the logs:

- **Single pre-init write, byte-identical to the unpatched baseline.** The
  first (and only) `SOFWR FB_W_SOF2` line in every leg — patched and
  unpatched alike — is
  `SOFWR FB_W_SOF2 val=00c00000 was=00000000 pc=0c0558e4 pr=0c045c94`,
  byte-for-byte identical across `captures/attract.log` (Phase 2,
  unpatched), `dryrun-attract.log`, `dryrun-play.log`, and
  `dryrun-attract-2-unattended.log`. `grep -c "^SOFWR FB_W_SOF2"` = **1** in
  all four logs — FB_W_SOF2 is written exactly once per leg, always the
  same value, from `was=00000000` (never touched again).
- **Nothing is ever written above 8 MB.** `nz_above8m=0` in every single
  `VRAMPROFILE` line of all three dry-run legs (69/139/64 samples
  respectively; verified `grep VRAMPROFILE | grep -v nz_above8m=0` = 0 lines
  in each), not just the running-max.
- **The fork's own source documents `0xc00000` as the never-written BIOS
  default:** naomi.cpp:256-258 — "FB_W_SOF2 is usually a never-written BIOS
  default (31 kHz progressive parks the field-2 pointer at 0xc00000);
  masking it costs nothing when nothing was written there."

**What the coded check actually samples.** `dryrun_checks()` reads **every**
`VRAMREGS` snapshot in a leg, in order (`leg["vramregs"]`, appended once per
sample — not just the last line, which was this check's original,
undocumented design: a leg could spuriously PASS or FAIL depending purely on
which snapshot happened to land last). For each of `fb_w_sof1`/`fb_w_sof2`/
`fb_r_sof1`, a register is only a problem if it is above cap in *some*
snapshot; when it is, one of two exemptions can clear it — no exemption,
still FAILs.

**Implementation, exemption 1 (ruling A):** `fb_w_sof2` is exempt **iff**
it reads the BIOS default (`0xc00000`, masked) in *every* snapshot of the
leg, it was written exactly once (`SOFWR` count), and `nz_above8m == 0`
throughout. Any second SOF2 write, any other masked value at any point, or
any above-8m content still FAILs — verified by
`scripts/test_parse_cartlog.py`: the exempt fixture PASSes; a synthetic
second `FB_W_SOF2` write FAILs; a synthetic `nz_above8m=5` FAILs; a
synthetic `fb_w_sof1` at the same masked value FAILs (the exemption never
widens past the one cell). Comment in code cites naomi.cpp:256-258.

**Implementation, exemption 2 (new ruling, mirrors ruling A) — the
boot-transient handoff:** a register is exempt **iff** every above-cap
snapshot comes strictly before every below-cap snapshot (it settles once
and never regresses back above cap for the rest of the leg) **and**
`nz_above8m == 0` throughout. A synthetic late/regressed above-cap
snapshot (inserted *after* the register has already settled below cap)
correctly still FAILs — `scripts/test_parse_cartlog.py` covers both
directions. This is what clears `fb_r_sof1`/`fb_w_sof1` — see §Boot-transient
finding below for the evidence this ruling is built on (it replaces an
earlier, incorrect "Open concern" write-up from this task's first pass,
which mis-read the same data — corrected here after review).

### Stream-shape scoping (`dryrun_stream_shape`, ruling B)

Unscoped (merging both legs' DMA tuples) FAILs: the merged multiset picks
up `dryrun-play`'s own cart traffic (e.g. `(0x800000, 0x800)`, a directory
read never issued during attract), which has no counterpart in the 660 s
attract anchor — expected, since interactive play has no fixed anchor.

**Implementation:** `dryrun_checks()` now judges the shape check against
only the *first* leg on the CLI (the dry-run attract leg, same "first leg"
CLI-order convention `merge()` already uses for tuple attribution — Step
4's command lists `dryrun-attract.log` first). Any further legs are
reported informationally (caps-only, no shape verdict) and never fail the
check. Result, scoped to `dryrun-attract` alone vs the Phase 2
`captures/attract.log` anchor: **exact multiset match**, 205/205 `(src,len)`
tuples (verified directly, not just via the gate's summary line) — no
truncation-boundary judgment call was needed on this run. `dryrun-play` is
reported exempt ("no anchor for interactive play, caps-only") in the CHECK
detail; its role — proving the caps hold under load — is covered by
`dryrun_main_below_16m` and `dryrun_vram_below_8m`, which run across all
legs unchanged.

**The multiset comparison stays strict — no auto-pass on a set-equality
fallback.** An earlier pass of this task's implementation added a code
branch that auto-PASSed whenever the *unique* `(src,len)` set matched even
if the multiset counts didn't (meant to implement the plan's truncation-
boundary provision in code). Review caught that this was a misreading: the
plan's provision — "record the set-equality result + the boundary
explanation... rather than forcing a re-run loop" — is a **manual** judgment
call a human makes and records in this document on a FAIL, not something
the gate should silently pass. That branch has been reverted; a multiset
mismatch, including a same-unique-set truncation case, now correctly FAILs
the check. `scripts/test_parse_cartlog.py` adds: a matching first leg +
mismatching second leg → PASS (second leg's mismatch doesn't fail it);
reversed leg order → the now-first (mismatching) leg correctly FAILs (order,
not name, decides the role); a synthetic capture-truncation case (same
unique set, differing counts) → still FAILs; and an empty `legs` list is
tolerated rather than raising (mirrors the old code's tolerance, which the
`shape_leg, *exempt_legs = legs` unpack had accidentally dropped).

### Boot-transient finding: FB_R_SOF1/FB_W_SOF1's above-cap writes are a capped boot artifact, not sustained behavior — the patch worked

**Correction note:** this task's first pass mis-read the raw `SOFWR` counts
as "the patch made no measurable difference to the scan-out register" and
recorded that as an open, Task-13-blocking concern. Review falsified that
reading against the same logs on four independent points below. The
corrected finding is the opposite: this is evidence the VRAM patch **did**
redirect the compose pipeline below 8 MB — the ruling A due-diligence check
(verify FB_R_SOF1/FB_R_SOF2 stay below 8 MB after the handoff) **passes**.

**(a) The ~192-per-value counts are the instrument's own log budget, not
game behavior.** `../cleopatra/tools/flycast-src/core/hw/pvr/pvr_regs.cpp:241-243`
caps the shared `FB_R_SOF1`/`FB_R_SOF2` case block at `rsof_lines < 800`
(one counter for both registers — confirmed: `grep -c "^SOFWR FB_R_SOF1"`
= 400 and `grep -c "^SOFWR FB_R_SOF2"` = 400 in `dryrun-attract.log`, sum
exactly 800); `:274-276` caps `FB_W_SOF1` at `wsof1_lines < 800`
(confirmed: exactly 800 lines). Once the shared budget is spent, the
instrument stops emitting `SOFWR` lines for that register **for the rest
of the run** — it does not mean the register stopped changing, and it does
not mean it kept changing above cap. Identical counts between the patched
and unpatched image are explained entirely by both runs hitting the same
800-line cap on the same early boot sequence; they are not evidence the
patch had "no effect."

**(b) The above-cap writes are not "the entire run" — they are the first
1.5% of it.** In `dryrun-attract.log` (1,080,610 lines total), the *last*
`SOFWR FB_R_SOF1` line is file line **15,964**; the last `SOFWR FB_W_SOF1`
line is **27,518**. Both registers stop being logged (budget exhausted)
well before the run is 3% complete.

**(c) It is a one-way handoff, not an oscillation.** Lines 13,931 and
13,940 of `dryrun-attract.log`:

```
13931:SOFWR FB_W_SOF1 val=00020000 was=00800000 pc=8c032140 pr=8c03bb3a
13940:SOFWR FB_R_SOF1 val=00020000 was=00c00000 pc=8c032140 pr=8c037396
```

— a single write pair, at `pc=8c032140` (the KAMUI2 per-frame flip site
already identified in §Provenance → VRAM/FB), moves both registers from the
above-cap pair to the relocated below-cap pair. **Zero** above-cap SOF1
writes occur after line 13,940 (`awk 'NR>13940 && /^SOFWR FB_R_SOF1|^SOFWR
FB_W_SOF1/'` → 214+215 lines, all `0x20000`/`0x420000`, none above cap).
Cross-tabulating PC × value over every `SOFWR FB_R_SOF1`/`FB_W_SOF1` line in
the leg makes the split absolute: **every** below-cap value is written from
`pc=8c032140` and **only** that PC; **every** above-cap value is written
from a disjoint set of boot-path PCs (`0c0551c0`, `0c0551d0`, `0c0551d8`,
`0c054886`, `0c054c5a`, `0c0558e4`, `0c054e22`) and **only** those PCs. Two
populations, never interleaved, never regressing.

**(d) The uncapped instrument (`VRAMREGS`, one snapshot per ~10 s profile
tick, no 800-line budget) settles it.** Above-cap `fb_r_sof1` appears in
**only** `VRAMREGS` snapshots #1 and #2, at file lines **10,935** and
**13,861** — byte-identical across all three dry-run legs (deterministic
pre-handoff boot state, independent of attract/play/duration). Every
snapshot from #3 onward is below cap: 67/69 samples in `dryrun-attract`,
137/139 in `dryrun-play`, 62/64 in `dryrun-attract-2-unattended`.

**Consequence for the coded check.** `dryrun_vram_below_8m` now reads every
`VRAMREGS` snapshot (not just the last — see the FB_W_SOF2 section above
for why that mattered) and applies a **boot-transient exemption**: a
register is exempt iff every above-cap snapshot comes strictly before every
below-cap snapshot (settles once, never regresses) and `nz_above8m == 0`
throughout. `fb_r_sof1`/`fb_w_sof1` both satisfy this on all three legs —
PASS, not a silent under-sample. A synthetic late/regressed above-cap
snapshot still FAILs (`scripts/test_parse_cartlog.py`), so a genuine
post-handoff regression would be caught, not masked by this exemption.

**Verdict: the relocation strategy is validated, not open.** Main-RAM
relocation, VRAM content placement, and the compose-pipeline's scan-out
register all move below the DC 8 MB cap and stay there for the entire
run past a single deterministic boot transient. This closes the concern
this document's §Deliberately-not-patched bullet had flagged pending Task
12 — the "unclamped `state+0x7fc`" caller's value, whatever it resolves to
during that brief pre-handoff window, is superseded by the same
`pc=8c032140` flip every other frame uses, and never recurs.

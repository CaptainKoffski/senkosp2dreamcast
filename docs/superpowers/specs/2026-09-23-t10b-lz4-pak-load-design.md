# T10b — transparent LZ4 pak load (design)

2026-09-23. Follows the T10b feasibility spike (`docs/kb/t10b-spike.md`,
ANSWERED YES: hardware SH4 LZ4 decompress 14.3 MB/s against the
pre-registered 10.8 MB/s bar). Brainstormed and approved in-session
2026-09-23. Branch `t10b-spike`; `main` untouched until an explicit
merge decision.

## Goal

Cut window B — the game→2P char-select stage-pak reload, one
8,288,256-byte whole-pak read `(0x0935a800, 0x7e7800)`, today 1.237 s
in-driver at the measured 6.7 MB/s GDEMU stage-2 DMA ceiling
(`docs/kb/phase7-polishing.md` §T10) — to ~0.78 s projected, by
storing an LZ4-compressed copy of the pak on disc and having the shim
inflate it into the game's destination while the disc DMA is still
delivering. Fewer bytes over the link is the only lever left; the
spike proved the decompress rate clears the bar with ~32 % margin.

## Scope

- **One map entry**: window B's pak. The mechanism is map-driven; all
  44 big tuples in `docs/kb/cart-streaming-map.csv` are whole-read-only,
  so extending later = rerun mastering with more entries, no code
  change. Not extended now (YAGNI: window B is the measured pain).
- **Build knob `SHIM_LZ4`** (top Makefile, same pattern as
  `SHIM_G1DMA`). Knob off ⇒ the produced image is bit-identical to
  release v16. Diag knob `SHIM_LZ4CRC` for emulator CRC legs.
- **Raw-ATA backend only.** The BIOS-syscall (DreamShell isoldr)
  backend keeps today's uncompressed path and today's speed.
- Loader untouched. The spike's `LZ4BENCH` loader instrument stays as
  a diagnostic.

## Non-goals

- No game disassembly or new patch-table sites: the shim already owns
  the read path (`shims/src/cart.c` → `gd_read_cart`).
- No zstd/gzip (spike: LZ4 is the SH4-realistic codec).
- No compression of other paks, no VMU/setting surface, no change to
  the prefetch ring (T3) beyond its existing miss re-aim behavior.

## On-disc format and mastering

The cart image (`senkosp.dat` bytes inside track04) is **not
modified**; the compressed blob is **appended to track04 after the
cart image**:

- `BLOB_FAD = CART_FAD + CART_SIZE/2048 = 451,878 + 122,726 = 574,604`
  — statically computable, no layout cycle. Track04 already ends past
  the 549,150 GD-ROM spec line (FAD 574,604) and is proven on GDEMU
  and Flycast; +~2,510 sectors is the same class of out-of-spec.
- A host pack tool (grown from `tools/t10b/pack_sample.c`, vendored
  lz4 v1.10.0 in `tools/t10b/lz4/`, BSD-2) compresses the pak in
  **64 KB chunks**, LZ4-HC-9 (amended during execution 2026-09-23 —
  see the bounce note below; LZ4's match window is 64 KB, so the
  spike's ratio and rate carry over):
  - 127 chunks: 126 × 65,536 B + one 30,720 B tail (`u_i`).
  - Each chunk's compressed stream is padded to a **32-byte multiple**
    (`a_i = align32(c_i)`) so every input range is cache-line-exact.
  - **Chunk classification**, backward pass from the last chunk
    (amended during execution 2026-09-23; the original slack-only pass
    was defective — slack seeds at zero at the tail and stored chunks
    add none, so it demoted every chunk, data-independently. The root
    cause is structural: right-justified geometry gives the innermost
    kept-LZ4 chunk a start-gap of exactly its own savings `u−a`, while
    LZ4's in-place rule needs `(u−c) + ((c>>8)+32)`
    (lz4.h `LZ4_DECOMPRESS_INPLACE_MARGIN`) — short by `pad+margin`
    for ANY contiguous placement):
    - a chunk where compression doesn't pay (`a_N ≥ u_N`) is
      **stored** (raw bytes, `a_N = u_N`);
    - the **innermost** kept-LZ4 chunk is flagged **BOUNCE**: at
      runtime it decodes into the already-reserved 64 KB T3 prefetch
      ring (exact fit) and is copied to its destination — output
      disjoint from input, so the in-place margin does not apply, and
      its full savings seed `slack` for every earlier chunk;
    - every earlier LZ4 chunk needs
      `slack ≥ (a_N − c_N) + (c_N>>8) + 32` from the accumulated
      savings of kept chunks after it, else it is stored.
    Guarantees `a_i ≤ u_i` for every chunk and the in-place margin for
    every non-bounced LZ4 chunk.
  - Host round-trip verify (decode + compare + CRC) — the build fails
    if it fails. **Amended during planning 2026-09-23:** the per-chunk
    checksum is **crc32 via the shim's own `shim_crc32`** (gd.c), not
    the spike's naomi crc16 — one implementation on host and target
    (the pack tool links gd.c's pure section, the `test_gd_math.c`
    idiom), so a divergence is a link failure rather than a copy.
- Blob layout (equals the RAM tail image byte-for-byte):
  `front_pad ‖ chunk_0 ‖ … ‖ chunk_126`, right-justified:
  `S = Σ a_i`, `R = ceil(S/2048)·2048`, `front_pad = R − S` garbage
  bytes at the front. One straight sector read reproduces the RAM
  image.
- The tool emits the blob plus a **generated header**
  (`build/lz4pak_map.h`) compiled into the shim: per pak
  `{cart_off, ulen, blob_fad, R}`, per chunk
  `{csize (exact, u32), flags (lz4|stored|bounce), crc32}` — ~1 KB per
  127 chunks. `scripts/make_gdi.py` appends the blob to track04 when the
  knob is on (and asserts blob length == R).

## Runtime read path

Routing in `gd_read_cart` (`shims/src/gd.c`), after the prefetch-hit
check (an 8.3 MB request can never hit the 64 KB ring), before the
head/body/tail plan: exact `(cart_off,len)` match against the map
**and** backend == raw-ATA **and** `dst` 32-aligned **and** `SHIM_LZ4`
(which requires `SHIM_G1DMA` compiled in — the route drives the DMA
engine) ⇒ `gd_read_lz4(entry, dst)` (**amended during planning 2026-09-23**:
`shims/src/gd_lz4.inc.c`, `#include`d into gd.c — see §Files touched).
Success
exits through the same `SHIM_TIME`/`SHIM_CRC` tail as any other read,
and performs the same prefetch miss re-aim, so instruments and T3
behavior are unchanged.

`gd_read_lz4`:

1. `base = dst + ulen − R` (32-aligned by construction: `dst`
   32-aligned, `ulen` and `R` 2048-multiples). `OCBI` the whole
   `[base, base+R)` range once (the existing DMA path's discipline).
2. Kick **one** ATA PACKET DMA read: `R/2048` sectors from
   `blob_fad` into `base` — via a helper extracted from
   `gd_read_fad`'s hardware-proven kick sequence (GDAPRO already
   opened by `gd_hw_init`; engine programmed before the packet, kicked
   after; FEATURES bit0 = DMA).
3. Chunk loop, i = 0…126: poll `SB_GDLEND ≥ t_i = front_pad +
   Σ_{j≤i} a_j` with the progress-rearmed budget (the existing
   pattern; `GDST` clearing also satisfies it). Then decode chunk i
   through **cached P1**: LZ4 chunk → `LZ4_decompress_safe` into
   `dst + i·65536`, must return `u_i`; BOUNCE chunk (amended
   2026-09-23) → `LZ4_decompress_safe` into the 64 KB T3 ring
   (`PF_RING_BASE`, P1), forward-copy ring → dest, then `ocbi` the
   used ring span (dirty P1 ring lines would otherwise clobber a
   later P2 prefetch fill on writeback — the C1 rule); stored chunk →
   forward copy (skip when src == dst). Then `ocbp` (write-back +
   invalidate) the output range so the game's uncached reads see it.
   Optional `SHIM_LZ4CRC`: `shim_crc32` the output chunk against the map.
   Ring preconditions (route disqualifiers, checked before the DMA
   kick — the same two tripwires as `pf_armed`, gd.c): the heap-base
   pool word must read back patched (the ring RAM is really reserved)
   and the boot must be main-mode; otherwise the read falls through
   to the uncompressed path. Scribbling the ring is safe: the pf miss
   re-aim empties the window after every mapped read, and prefetch
   ticks cannot interleave with a read (hooks do not nest).
4. Epilogue: wait `GDST` clear, verify `GDLEND == R`, ack ISTNRM
   bit 14, ATA end-of-command verdict (BSY|DRQ clear, `GD_STATCMD`
   CHECK) — same shape as `gd_read_fad`'s DMA path.

The shim compiles `lz4.c` decompress-only, freestanding
(`LZ4_FREESTANDING`, local `LZ4_memcpy`/`LZ4_memmove`/`LZ4_memset`),
`-Os` if the size budget demands it.

## Safety invariants (why in-place needs no staging RAM)

With `ulen = Σu_i`, unconsumed input after chunk N starts at
`dst + ulen − Σ_{i>N} a_i`; output through chunk N ends at
`dst + Σ_{i≤N} u_i`. Output never overruns unconsumed input ⇔
`Σ_{i>N} a_i ≤ Σ_{i>N} u_i` — guaranteed chunk-wise by `a_i ≤ u_i`
(mastering rule). Two corollaries:

- **CPU never writes ahead of the DMA frontier**: chunk N decodes only
  after `GDLEND ≥ t_N`, and its output ends at or below
  `base + t_N ≤ base + GDLEND`.
- **No cache line straddles a dirty-output/unconsumed-input
  boundary**: input starts are 32-aligned (chunk padding) and output
  chunk boundaries are 128 K-aligned, so the single up-front `OCBI`
  plus per-chunk `ocbp` is sufficient; no line-level corruption case
  exists.
- **Within a chunk** (output overtaking its own compressed bytes):
  LZ4's in-place margin, enforced by the mastering backward pass for
  non-bounced LZ4 chunks; the bounced chunk decodes into the disjoint
  64 KB ring so no margin applies (amended 2026-09-23); stored chunks
  are forward copies with src ≥ dst, overlap-safe.

## Failure policy — never worse than today

**Amended during planning 2026-09-23** (the original rule was a single
sentence: *any* failure falls back). Failures split in two, because
re-issuing a read on a wedged DMA engine without a drive reset would be
a NEW hang mode — strictly worse than today:

- **Disqualifiers** (map miss, syscall backend, unaligned dest, ring
  not reserved / test boot, ring overlapping the dest) and
  **decode-stage failures** (`LZ4_decompress_safe` error, `SHIM_LZ4CRC`
  mismatch) ⇒ drain + settle the engine, record forensics
  (`gd_diag`/`gd_last_err`/serial, site `GD_E_LZ4`), and **fall through
  to the existing uncompressed read of the original region**, which is
  still on disc, untouched. Compressed delivery is an optimization,
  never the only copy.
- **Transport failures** (DMA error, short `GDLEND`, ATA end-of-command
  verdict, a drain that never settles) ⇒ abort the engine (`GDEN = 0`),
  ack ISTNRM bit 14, and **propagate the negative site** — the caller
  dies exactly as it does today for the same failure on the
  uncompressed path. Transport failures keep today's die-loud envelope.

## Gates (all before any merge/release decision)

1. Host round-trip in the pack tool — build-fatal.
2. Emulator leg (`SHIM_CRC` + `SHIM_LZ4CRC`): delivered window-B bytes
   byte-identical to the original `.dat` region. Emulator = correctness
   only, per discipline.
3. Emulator 2p-stages functional leg: fail-free, normal gameplay.
4. **Hardware leg (`SHIM_TIME`, coder's cable)** — the pre-registered
   bar on window B's in-driver wall (today 1.237 s):
   **keep ≤ 0.9 s; discard > 1.1 s**; between = operator's call.
   This is where the unmeasured RAM-contention caveat becomes a
   measurement.
5. Knob-off rebuild: track04 md5 identical to a fresh build at the
   branch point (`merge-base main t10b-spike` = 3ca47dc). Amended
   2026-09-23: the original "identical to release v16" is unattainable
   for a reason predating this feature — the 2026-09-21 KOS decoupling
   changed the absolute checkout path `libkallisti.a` embeds in every
   loader binary (`…/cleopatra/tools/kos` → `…/senkosp2dreamcast/
   tools/kos`, found in both artifact generations at loader offset
   ~207.9 k). The redefined gate proves the same thing the original
   wanted: T10b contributes zero bytes to a knob-off image.

## Risks

- **Shim size**: 10 KB used of the hard 16 KB window (`shim.ld`
  ASSERT). Decoder + routing + map ≈ 5–6 KB. Ladder: `-Os` on the lz4
  object → compact hand-rolled block decoder (needs a re-bench against
  the 10.8 MB/s bar before trusting).
- **Cold-cache dest**: the spike bench inflated into a warm 128 KB
  buffer; the real path streams 8.3 MB of cold lines plus concurrent
  G1 DMA on the RAM bus. The 32 % margin should absorb it; gate 4
  decides. Plan B if in-place underperforms: 2 × 128 KB staging stolen
  from the heap (PF-ring precedent) with per-chunk ATA commands.
- **GDEMU `GDLEND` progress granularity** is unobserved (Flycast
  advances in 10,240-byte steps). The progress-rearmed budget
  tolerates any monotonic pattern; worst case (no visibility until
  completion) degrades to serial decode — slower, never incorrect;
  gate 4 would catch it.

## Files touched

- `shims/src/gd_lz4.inc.c` (new, ~200 lines), `shims/src/gd.c` (~15
  lines: include + routing + `delivered:` label in `gd_read_cart`),
  `shims/Makefile`. **Amended during planning 2026-09-23:** the runtime
  is an `.inc.c` `#include`d into gd.c, NOT a separate TU with helpers
  extracted from `gd_read_fad` — extraction would change knob-off
  codegen and break gate 5's bit-identity. The DMA arm/kick/epilogue
  sequences are therefore MIRRORED, with `KEEP IN SYNC` markers citing
  `gd_read_fad`'s line ranges. No `shim_iface.h` change either: the
  blob FAD is generated data in `build/lz4pak_map.h`, not a constant.
- `tools/lz4pak/pack_paks.c` (new host tool; reuses
  `tools/t10b/lz4/`), top `Makefile` (knob + blob/header deps),
  `scripts/make_gdi.py` (append blob).
- `build/lz4pak_map.h`, `build/lz4paks.bin` (generated, gitignored —
  derived game bytes stay out of git).
- KB: `docs/kb/t10b-spike.md` pointer to this spec;
  `docs/kb/phase7-polishing.md` §T10 addendum; leg records as they
  land.

## Amendment 4 (2026-09-23): decode-bound fix — SH4 span wildcopy with movca.l

**Why.** Gate 4 landed at 1.011 s (between-band; operator ruled: one
targeted iteration). The diagnostic leg `hw-t10b-4` (SHIMLZ4 split, KB
§T10b) proved the window **decode-bound**: w = 61 ms link-wait vs
c = 948 ms CPU work; decode runs 8.7 MB/s under the live DMA vs 14.3
contention-free. Disassembly of `lz4_dec.o` shows why the decoder is
this slow: on SH4, GCC lowers `LZ4_memcpy(d,s,8)` (unknown alignment,
strict-alignment target) to a **call** — every long literal/match copy
is a `jsr lz4_memcpy` loop, 8 bytes per call — and every output line
write-miss costs an allocate-read (OC is 16 KB direct-mapped copy-back,
write-allocate: `tools/kos/.../arch/cache.h:39-45`, `dc/cache.h:42`).

**Design.** All long copies in the generic decode path funnel through
`LZ4_wildCopy8` (lz4.c:465; call sites 2332 literals, 2425/2432
matches; the FAST_DEC_LOOP variants are not compiled on SH4). Patch
exactly that function, under `#if defined(LZ4_SH4_WILDCOPY)` (target
build only — host pack/verify builds stay pristine), to call
`lz4_sh4_wildcopy(d, s, e)` in `shims/src/lz4_mem.c`:

- **Fallback** (distance `|d−s| < 32` or span < 64 B): exact forward
  byte copy. Forward-exact is safe for every overlap the caller can
  legally present (callers guarantee offset ≥ 8 after the offset<8
  fixup; forward byte copy is safe for offset ≥ 1).
- **Line path** (distance ≥ 32 and span ≥ 64): byte-copy head until
  dst is 32-aligned, then per interior 32-byte line: `movca.l` the
  first word (allocate WITHOUT the RAM read — SH7750 manual §4.2.5;
  same instruction KOS wraps as `arch_dcache_alloc_line`,
  arch/cache.h:83), store the remaining 7 words; co-aligned sources
  use word loads, misaligned sources shift-merge from aligned words
  (LE merge: `(prev>>8a)|(cur<<(32−8a))`). Exact byte tail.
- **No overrun**: unlike stock wildCopy8 (up to 8 B past dstEnd), the
  replacement copies exactly [d,e) — strictly within the contract and
  the in-place margins.

**Safety argument (movca writes garbage to unwritten line bytes).**
`movca.l` is issued only on lines fully inside [d,e), so no byte
outside the requested copy is ever touched. Within the span: reads for
the line being filled come from `line ± distance` with distance ≥ 32,
i.e. never from the line under construction (matches read ≥ 32 behind
the write frontier — already final; literals read ≥ 32 ahead — outside
the movca'd line). Interrupt-eviction mid-line is self-healing: the
eviction writes back garbage tail bytes, the resuming store misses,
allocate-reads them back and overwrites — no reader exists mid-decode.
Both decode destinations (game buffer, T3 ring) are P1 copy-back
(`CCR_CB`, dc/cache.h:42), the mode movca requires. The per-chunk
`lz4_ocbp` flush after decode is unchanged, so delivered bytes reach
RAM exactly as before.

**Emulator caveat.** Flycast implements `movca.l` as a plain 32-bit
store with no cache model (`core/hw/sh4/interpr/sh4_opcodes.cpp:
788-794`, "TODO ocache") — the emulator CRC gate therefore proves the
copy SEQUENCING (shift-merge math, guards, tails) but not the cache
semantics; those are covered by the line-interior-only rule above and
observed on the hardware leg.

**Gates (re-registered).** Build A/B knob-off md5 vs branch point
(`750879c8cabd6622c53a5c93d852770e`); emulator CRC leg (LZ4CRC per-chunk
crc32 vs source, both window-B serves, plus functional play-through);
hardware leg `hw-t10b-5` with the SHIMLZ4 split. **Bar: unchanged
gate-4 bar** — ≤ 0.9 s keep, > 1.1 s discard, between = operator's
call. Expectation: c drops toward ~0.6-0.7 s; if the decoder starts
outrunning the link, w grows (GDLEND polling is P4 traffic, not RAM)
and the wall approaches the link floor ~0.8 s.

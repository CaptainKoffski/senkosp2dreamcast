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
  **128 KB chunks** (bench-matched), LZ4-HC-9:
  - 64 chunks: 63 × 131,072 B + one 30,720 B tail (`u_i`).
  - Each chunk's compressed stream is padded to a **32-byte multiple**
    (`a_i = align32(c_i)`) so every input range is cache-line-exact.
  - **Stored-chunk demotion**, backward pass from the last chunk:
    maintain `slack = Σ_{i>N}(u_i − a_i)`; demote chunk N to stored
    (raw bytes, `a_N = u_N`) when it is LZ4 and
    `slack < margin_N = a_N/256 + 32` (LZ4's in-place margin), or when
    `a_N ≥ u_N` (compression didn't pay). Guarantees `a_i ≤ u_i` for
    every chunk and the in-place margin for every LZ4 chunk.
  - Host round-trip verify (decode + compare + CRC16 via
    `naomi_eeprom_crc`) — the build fails if it fails.
- Blob layout (equals the RAM tail image byte-for-byte):
  `front_pad ‖ chunk_0 ‖ … ‖ chunk_63`, right-justified:
  `S = Σ a_i`, `R = ceil(S/2048)·2048`, `front_pad = R − S` garbage
  bytes at the front. One straight sector read reproduces the RAM
  image.
- The tool emits the blob plus a **generated header**
  (`build/lz4pak_map.h`) compiled into the shim: per pak
  `{cart_off, ulen, blob_fad, R}`, per chunk
  `{csize (exact, u32), flags (lz4|stored), crc16}` — ~1 KB for 64
  chunks. `scripts/make_gdi.py` appends the blob to track04 when the
  knob is on (and asserts blob length == R).

## Runtime read path

Routing in `gd_read_cart` (`shims/src/gd.c`), after the prefetch-hit
check (an 8.3 MB request can never hit the 64 KB ring), before the
head/body/tail plan: exact `(cart_off,len)` match against the map
**and** backend == raw-ATA **and** `dst` 32-aligned **and** `SHIM_LZ4`
(which requires `SHIM_G1DMA` compiled in — the route drives the DMA
engine) ⇒ `gd_read_lz4(entry, dst)` (new file `shims/src/gd_lz4.c`). Success
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
3. Chunk loop, i = 0…63: poll `SB_GDLEND ≥ t_i = front_pad +
   Σ_{j≤i} a_j` with the progress-rearmed budget (the existing
   pattern; `GDST` clearing also satisfies it). Then decode chunk i
   through **cached P1**: LZ4 chunk → `LZ4_decompress_safe` into
   `dst + i·131072`, must return `u_i`; stored chunk → forward copy
   (skip when src == dst). Then `ocbp` (write-back + invalidate) the
   output range so the game's uncached reads see it. Optional
   `SHIM_LZ4CRC`: CRC16 the output chunk against the map.
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
  LZ4's in-place margin, enforced by the mastering backward pass;
  stored chunks are forward copies with src ≥ dst, overlap-safe.

## Failure policy — never worse than today

Any disqualifier or failure (map miss, syscall backend, unaligned
dest, DMA error, `LZ4_decompress_safe` error, short `GDLEND`) ⇒ abort
the engine if needed (`GDEN = 0`), record forensics
(`gd_diag`/`gd_last_err`/serial), and **fall through to the existing
uncompressed read of the original region**, which is still on disc,
untouched. Compressed delivery is an optimization, never the only
copy.

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
5. Knob-off rebuild: track04 md5 identical to release v16.

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

- `shims/src/gd_lz4.c` (new, ~150 lines), `shims/src/gd.c` (extract
  DMA kick/epilogue helpers; ~10-line routing in `gd_read_cart`),
  `shims/include/shim_iface.h` (BLOB_FAD constant), `shims/Makefile`.
- `tools/lz4pak/pack_paks.c` (new host tool; reuses
  `tools/t10b/lz4/`), top `Makefile` (knob + blob/header deps),
  `scripts/make_gdi.py` (append blob).
- `build/lz4pak_map.h`, `build/lz4paks.bin` (generated, gitignored —
  derived game bytes stay out of git).
- KB: `docs/kb/t10b-spike.md` pointer to this spec;
  `docs/kb/phase7-polishing.md` §T10 addendum; leg records as they
  land.

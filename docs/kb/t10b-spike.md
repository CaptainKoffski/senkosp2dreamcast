# T10b spike — can the load floor be beaten? (branch `t10b-spike`, THROWAWAY)

> **The real build was implemented from this spike (2026-09-23/24) and
> KEPT: window B 1.237 → 0.907 s on hardware.** This file remains the
> spike record only. The implementation story lives in
> `phase7-polishing.md` §T10b; design + 4 amendments in
> `docs/superpowers/specs/2026-09-23-t10b-lz4-pak-load-design.md`;
> tooling records in `tooling.md` §T10b.

**Status: ANSWERED (2026-09-23, hardware leg `phase7/hw-t10b-1`) — YES,
the bar is met.** Operator-run boot on the bench rig (GDEMU + coder's
cable), bench build track04 `3da5e22…`:

    L4BENCH n=8 u=1048576 c=642833 fail=0 reps=4
            lz4_us=292919 mc_us=138253 lz4=13983 KB/s memcpy=29626 KB/s

- **fail=0** — all 8 chunks decode byte-correct (CRC16) on real SH4.
- **LZ4 decompress: 14.3 MB/s** (4,194,304 B / 292,919 µs) — clears the
  pre-registered 10.8 MB/s bar with ~32 % margin. Verdict row fired:
  **window-B wall ~1.24 s → ~0.78 s (−0.46 s, −37 %) — build it.**
- **memcpy control: 30.3 MB/s** — matches T10's independently measured
  ~29.6 MB/s ring-memcpy figure, so the timer and the machine are
  behaving; decompress at ~half memcpy speed is textbook LZ4.
- Two honest caveats for the real build: (1) overlap is REQUIRED, not
  optional — serial read-then-inflate is 0.765 + 0.579 = 1.34 s, WORSE
  than today; only chunked double-buffering (DMA N+1 ∥ inflate N) wins.
  (2) The bench measured decompress alone; under overlap the G1 DMA
  competes for RAM bandwidth. The 32 % margin (0.579 s vs 0.765 s)
  absorbs contention on paper; the real build's hardware leg must
  measure the actual wall before any verdict.

**Status before the leg: instrument ready, awaiting the operator hardware leg.**
Everything on this branch is spike code: it answers a question, it does
not ship. If the answer is "not worth it," discard the branch.

## Question

T10 closed with the load floor "reached": window B (game→2P char-select
stage-pak reload) is 8,400,896 B at 93.8 % in-driver duty, pinned at the
measured **6.7 MB/s GDEMU stage-2 DMA ceiling** (`phase7-polishing.md`
§T10). The link has no headroom. Can the window still shrink by sending
**fewer bytes** — LZ4-compressed paks on disc, shim inflating into the
game's destination, DMA of chunk N+1 overlapped with SH4 decompress of
chunk N?

Non-candidates, dead on T10/T2 numbers: async kick+poll (window B has
nothing game-side to overlap), speculative prefetch (needs ~8.3 MB free
RAM; ~410 KB heap slack exists).

## Step 1 — compressibility (2026-09-23, host): PASS

The window-B pak (`senkosp.dat` 0x0935a800 + 0x7e7800, the only tuple
ever observed in that region — 8 legs in `cart-streaming-map.csv`, always
the whole pak, so in-place compressed storage + an (offset→csize) map is
safe on every observed path):

| codec | bytes | ratio |
|---|---|---|
| original | 8,288,256 | 100 % |
| lz4hc −9 | 5,124,235 | 61.8 % |
| gzip −9 | 4,767,191 | 57.5 % |
| zstd −19 | 4,188,402 | 50.5 % |

LZ4 is the SH4-realistic codec (byte-oriented, memcpy-shaped inner
loop). Block-wise (8 × 128 KB stripes, HC-9): 61.3 % aggregate,
per-chunk spread 22–95 %.

## Step 2 — SH4 decompress rate: instrument built, emulator smoke PASS

- Vendored **lz4 v1.10.0** (`tools/t10b/lz4/`, BSD-2, four files) from
  `https://raw.githubusercontent.com/lz4/lz4/v1.10.0/lib/{lz4.c,lz4.h,lz4hc.c,lz4hc.h}`
  via curl 2026-09-23. Same `lz4.c` compiles host-side (pack tool) and
  under kos-cc (SH4) — one decoder, control-tested both ends.
- `tools/t10b/pack_sample.c` → `build/t10b_sample.bin` (gitignored,
  derived game bytes): 8 × 128 KB real pak stripes, LZ4-HC-9, per-chunk
  CRC16 (`naomi_eeprom_crc`, same function host and target), host
  round-trip verify PASS.
- `loader/lz4bench.c` behind `make gdi SERIAL=1 LZ4BENCH=1`: at loader
  `main()` entry (RAM free, before menu), one correctness pass (size +
  CRC per chunk) then 4 timed walks + a memcpy control, one `L4BENCH`
  serial line. Knob recorded in both Makefiles; never ship.
- Emulator smoke ×2 (`captures/phase7/t10b-emu-smoke{1,2}.stdout.log`,
  unattended, one-call pattern, killed by PID):
  - smoke1: `fail=0` (all 8 chunks decode byte-correct on target) but
    `mc_us=0` — the memcpy control was dead-store-eliminated at -O2.
    Fixed with a volatile sink; that first line is the record of why the
    sink exists.
  - smoke2: `L4BENCH n=8 u=1048576 c=642833 fail=0 reps=4 lz4_us=308327
    mc_us=26271 lz4=13284 KB/s memcpy=155913 KB/s`.
  - Emulator rates are Flycast's timing model, **not evidence** — only
    correctness (`fail=0`) counts from these legs.

Bench build (this branch, `make clean && make gdi SERIAL=1 LZ4BENCH=1`):
track04 md5 `3da5e22ba0f35adaad774f0f829c87af`.

## The decision bar (pre-registered before the hardware number)

Compressed transfer: 5,124,235 B ÷ 6.7 MB/s ≈ 0.765 s (vs 1.237 s
uncompressed). With chunked double-buffering the wall ≈
`max(0.765 s, 8.29 MB ÷ R)` where R = hardware LZ4 decompress rate:

| hardware R | window-B wall | verdict |
|---|---|---|
| ≥ 10.8 MB/s | ~0.77 s (decompress fully hidden) | **−0.47 s, −38 % — build it** |
| 8 MB/s | ~1.04 s | −0.2 s — marginal, operator's call |
| ≤ 6.7 MB/s | ≥ 1.24 s | no win — discard branch |

(The memcpy control number calibrates how far R sits from the machine's
copy ceiling; it also sanity-checks the timer.)

## Operator leg (one boot, ~1 minute)

1. `git checkout t10b-spike && source tools/kos/environ.sh &&
   make clean && make gdi SERIAL=1 LZ4BENCH=1 && make deploy`
   (or verify track04 md5 `3da5e22…` and deploy the already-built disc).
2. Coder's cable: `scripts/capture_serial.sh phase7/hw-t10b-1`, boot the
   console. The `L4BENCH` line prints during the loader splash — no
   input needed; power off after the menu appears.
3. Required: `fail=0`. The verdict is the `lz4=` KB/s against the table
   above.

## If the bar is met (sketch only, NOT built)

Shim-side: compress the hot big tuples (stage paks) in-place at
mastering (texpatch-style splice), ship an (offset→csize) map, teach
`gd_read_cart` to route mapped tuples through chunked
DMA-then-inflate with double buffering. No game disassembly needed —
the shim already owns the read path. Un-mapped reads unchanged.
Estimated new moving parts: mastering step + ~150 lines shim. All
gates (CRC instrument, emulator + hardware legs) would apply before
any release respin.

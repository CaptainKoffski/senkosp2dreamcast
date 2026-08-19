# Boot-binary map — senkosp (Phase 3)

Static map of the senkosp main boot binary (`.dat` main load entry: ROM
`0x00000000` → RAM `0x8c020000`, `0x171ff8` bytes; entrypoint `0x8c021000` —
`docs/kb/game.md` §Parsed .dat header). Addresses are P1 (`0x8c…`) unless
noted; phys = address `& 0x1fffffff`.

Evidence: `scripts/ghidra/run.sh script DumpEntryChain.java` against Ghidra
project `senkosp3` (image `0x8c020000`–`0x8c191ff7`, SuperH4:LE:32). Every
literal-pool word quoted below was cross-checked byte-for-byte against
`tools/boot.bin` with `xxd` (file offset = address − `0x8c020000`).

In the listings below, everything up to the `;` (or the `<==` flag) is verbatim
`DumpEntryChain.java` output; text after a `;` is annotation added here.

## Entry chain & SP

senkosp's entry is **not** a Cleopatra-style `jmp @rN` trampoline: it is a real
function whose first `jsr` *returns*, so the chain continues inside the entry
function itself. `DumpEntryChain.java` was taught `jsr` as a hop mnemonic and
its entry window widened to cover the post-`rts` continuation.

### The chain from `0x8c021000`

**1. `0x8c021000` — entry.** Pokes one PVR register, then calls a cache sub
through the P2 (uncached) mirror:

```
8c021000  mov.l 0x8c021024,r2      ; r2 = 0xa05f811c
8c021002  mov.w 0x8c02101e,r3      ; r3 = 0x00ff
8c021004  mov.l 0x8c02102c,r1      ; r1 = 0x8c0210c4
8c021006  mov.l r3,@r2             ; [0xa05f811c] = 0xff
8c021008  mov.l 0x8c021028,r3      ; r3 = 0xa0000000
8c02100a  or r3,r1                 ; r1 = 0xac0210c4  (P2 mirror of 0x8c0210c4)
8c02100c  jsr @r1
```

`0xa05f811c` is phys `0x005f811c` = PVR register offset `0x11c` =
`PT_ALPHA_REF` ("Alpha value for Punch Through polygon comparison"),
`../flycast4naomi2dreamcast/core/hw/pvr/pvr_regs.h:79`. Written `0xff`.

**2. `0x8c0210c4` (entered uncached as `0xac0210c4`) — invalidate I-cache.**
Reads, masks and writes back the SH-4 cache control register:
`CCR = (CCR & 0x000089af) | 0x0800`.

- `0xff00001c` (pool `0x8c0210dc`) is `CCN_CCR` — flycast defines
  `CCN_CCR_addr 0x1F00001C` (`../flycast4naomi2dreamcast/core/hw/sh4/sh4_mmr.h:58`),
  the P4 alias of which is `0xff00001c`.
- The AND mask `0x000089af` (pool `0x8c0210e0`) is exactly the implemented-bit
  mask: flycast's CCR write handler does `temp.reg_data = value & 0x89AF`
  (`../flycast4naomi2dreamcast/core/hw/sh4/modules/ccn.cpp:64`).
- `0x0800` (`mov.w` pool `0x8c0210d8`) is bit 11 = `ICI`, per the CCR bit
  layout in `../flycast4naomi2dreamcast/core/hw/sh4/sh4_mmr.h:987-1005`;
  setting it triggers the i-cache invalidate
  (`.../modules/ccn.cpp:69-73`).

Ends `rts` at `0x8c0210e4` → returns to `0x8c021010`.

**3. `0x8c021010` — mask interrupts.** `SR = (SR & 0xffffff0f) | 0xf0`
(`IMASK = 15`), then `bra 0x8c021030`.

**4. `0x8c021030` — SP write #1 (transient, uncached):**

```
8c021030  mov.l 0x8c021038,r0
8c021032  mov r0,r15                     <== writes r15 (SP), loads 0xac00f400 (from 8c021038)
```

SP = `0xac00f400`, P2/uncached, phys `0x0c00f400`. Then `bra 0x8c02103c`.

**5. `0x8c02103c` — caches off.** `jsr @(0x8c0210b8 | 0xa0000000)` =
`0xac0210b8` (pools `0x8c02105c` = `0x8c0210b8`, `0x8c021058` = `0xa0000000`):

```
8c0210b8  mov.l 0x8c0210c0,r2      ; r2 = 0xff00001c  (CCR)
8c0210ba  mov #0x0,r3
8c0210bc  rts
8c0210be  _mov.l r3,@r2            ; delay slot: CCR = 0  → caches OFF
```

Which is why the boot code runs through P2 mirrors from here on.

**6. `0x8c021046` — clear a 1 KB low-RAM block.** `jsr @0x8c069814` (pool
`0x8c021064`) with `r4 = 0xac00fc00` (pool `0x8c021060`), `r5 = 0`,
`r6 = 0x0400` (`mov.w` pool `0x8c021054`) — a memset-shaped call covering phys
`0x0c00fc00`–`0x0c00ffff`. Then `bra 0x8c021068`.

**7. `0x8c021068` — final SR, clear registers.** `SR = 0x700000f0` (pool
`0x8c0210ac`): `MD=1, RB=1, BL=1, IMASK=15`. Then `r0`–`r14` are zeroed
(`0x8c02106c`–`0x8c021088`).

**8. `0x8c02108a` — SP write #2 (transient, cached), VBR and FPSCR:**

```
8c02108a  mov.l 0x8c0210a4,r0
8c02108c  mov r0,r15                     <== writes r15 (SP), loads 0x8c00f400 (from 8c0210a4)
8c02108e  mov.l 0x8c0210b0,r0
8c021090  ldc r0,VBR                     ; VBR = 0x8c00f400 (pool 0x8c0210b0)
8c021092  mov.l 0x8c0210a8,r0
8c021094  lds r0,fpscr                   ; FPSCR = 0x00040000 (pool 0x8c0210a8)
8c021096  mov.l 0x8c0210a0,r0            ; r0 = 0x8c0210e8 (pool 0x8c0210a0)
8c021098  jsr @r0
8c02109a  _mov r1,r0
8c02109c  bra 0x8c02109c                 ; hang if that jsr ever returns
```

SP #2 = `0x8c00f400`, the same value as VBR (the exception vector base, so the
handlers live *above* `0x8c00f400`). Still transient.

**9. `0x8c0210e8` — six `nop`s** (`0x8c0210e8`–`0x8c0210f2`) that fall straight
through into `0x8c0210f4`.

**10. `0x8c0210f4` — I-cache invalidate again, then SP write #3, the final
one:**

```
8c0210f4  mov.l 0x8c021110,r0            ; r0 = 0xff00001c  (CCR)
8c0210f6  mov.l @r0,r1
8c0210f8  mov.l 0x8c021114,r2            ; r2 = 0x000089af
8c0210fa  and r2,r1
8c0210fc  mov.w 0x8c02110c,r2            ; r2 = 0x0800  (ICI)
8c0210fe  or r2,r1
8c021100  mov.l r1,@r0                   ; CCR = (CCR & 0x89af) | 0x800
8c021102  mov.l 0x8c021118,r0            ; r0 = 0x8c170c14
8c021104  mov.l @r0,r15                  <== writes r15 (SP), loads 0x8c00f000 (from 8c170c14)
8c021106  mov.l 0x8c02111c,r0            ; r0 = 0x8c021150
8c021108  jmp @r0
8c02110a  _nop
```

Note the **indirection**: the literal pool at `0x8c021118` holds a *pointer*
(`0x8c170c14`), and the SP value itself is the data word stored at
`0x8c170c14`. Verified in the image: `xxd -s 0x150c14 -l 4 tools/boot.bin` →
`00 f0 00 8c` = `0x8c00f000` (file offset `0x150c14` = `0x8c170c14` −
`0x8c020000`, inside the `0x171ff8`-byte main load entry).

**11. `0x8c021150` — runtime init.** Two longword fill loops over ranges taken
from pointer pools (`0x8c02122c`–`0x8c02123c`), then `bsr 0x8c0211e2` and
`bsr 0x8c021188` (the latter contains a further longword fill loop and a
byte-copy loop — bss-clear / data-copy shaped), then `jsr @[0x8c021240]` with
`bra .` behind it as the never-return guard. Detail deferred to later tasks.

### SP verdict

**Final SP = `0x8c00f000`** → phys `0x8c00f000 & 0x1fffffff` = **`0x0c00f000`**.

Dreamcast main RAM is 16 MB and Naomi's is 32 MB, both based at phys
`0x0c000000` (`../flycast4naomi2dreamcast/core/emulator.cpp:454` DC `16_MB`,
`:462` Naomi `32_MB`), so the 16 MB line is phys `0x0d000000`.

`0x0c00f000` < `0x0d000000` — and not marginally: it is 60 KB above the
*bottom* of main RAM, not near the 32 MB top. All three SP values on the chain
are low (phys `0x0c00f400`, `0x0c00f400`, `0x0c00f000`).

> **Verdict: main RAM safe as-is — Phase 4 needs no SP relocation.**
> senkosp puts its stack at the bottom of RAM growing down, so the classic
> Naomi→DC "SP initialised near 32 MB" patch does not apply.

Recorded for completeness in case a later task needs to move it anyway: the SP
would be a **one-constant patch** at the data word **`0x8c170c14`** (file
offset `0x150c14`), reached via the pointer pool at `0x8c021118` and consumed
at `0x8c021104`. The two transient SPs are pools `0x8c021038` and `0x8c0210a4`.

### Stack region

```
Stack region: 8c000000-8c00f000
```

Half-open `[LO, HI)` — the stack occupies addresses below HI. Derivation:

- **HI = `0x8c00f000`**, the initial SP itself (`0x8c021104`, value read from
  `0x8c170c14`). SH-4 pushes pre-decrement (`mov.l Rm,@-r15`), so `0x8c00f000`
  is never itself written; the first pushed longword lands at `0x8c00effc`.
  HI is therefore the exclusive top.
- **The stack grows down from HI, and nothing else claims the span below it.**
  Every low-RAM address the boot chain claims sits at or *above* `0x8c00f000`:
  the stack top (`0x8c00f000`), `VBR = 0x8c00f400` with its vectors above that
  (step 8), and the 1 KB block cleared at phys `0x0c00fc00`–`0x0c00ffff`
  (step 6). The loaded image itself begins at `0x8c020000`
  (`docs/kb/game.md` §Parsed .dat header), so no part of the game occupies
  `0x8c000000`–`0x8c01ffff`.
- **LO = `0x8c000000`.** No stack-limit constant appears anywhere on the chain,
  so the floor is not bounded by code; the only hard floor is the bottom of
  main RAM. Taking LO there is the conservative choice for the free-space map
  (Task 10): it keeps anything from being placed in a span the stack may grow
  into.

LO is a bound, not a measurement — a dynamic low-water reading of `r15` would
tighten it. Until then the whole span is treated as reserved.

The block **above** HI, `0x8c00f000`–`0x8c00ffff` (VBR vectors + the 1 KB
scratch), is game-reserved as well but is *not* stack; noted here so the
free-space map does not mistake it for free.

### Phase 4 note — low-RAM overlap (not a 16 MB problem)

On a real Dreamcast the bottom of main RAM is BIOS/system territory: the
syscall vector table sits at `0x8c0000b0` (system), `0x8c0000b4` (font),
`0x8c0000b8` (flashrom), `0x8c0000bc`/`0x8c0000c0` (GD-ROM), `0x8c0000e0`
(misc), with SYSINFO at `0x8c001010` and a GD entrypoint at `0x8c0010f0`
(`../flycast4naomi2dreamcast/core/reios/reios.cpp:36-45`). senkosp's stack
region overlaps that block.

Harmless if the port stops using DC BIOS syscalls once the game takes over; if
the loader/shim needs GD-ROM syscalls *after* SP init, the collision has to be
resolved (do the syscall work before the game's SP init, or relocate the
game's stack via the one-constant patch site above). Flagged for Phase 4 —
this is a low-RAM collision, unrelated to the above-16 MB relocation work.

## BIOS-call verdict

Static half of naomi-vs-dreamcast §8-3 ("does any call/jump/pool constant
resolve into BIOS ROM?"). Evidence: `scripts/ghidra/run.sh script
ScanBiosTargets.java` against the same `senkosp3` Ghidra project (image
`0x8c020000`–`0x8c191ff7`). The script scans **both halves** of that
question, over the whole image, for anything resolving into BIOS ROM phys
range `0x0`–`0x1fffff` (`inBios()`: `(v & 0x1fffffff) < 0x200000`):

- **(a) Resolved flow references** — every reference Ghidra's analyzer marks
  as flow (`isFlow()`), i.e. `jsr`/`jmp @rN` targets it managed to resolve
  through a literal pool. SH-4 `bsr`/`bra` are PC-relative ±4 KB and
  structurally cannot reach BIOS from code based at `0x8c02xxxx`, so they are
  excluded by construction, not by the scan (script header comment).
- **(b) Pool constants** — every defined 32-bit word in the listing whose
  value looks like a BIOS-range virtual address: P1 cached
  (`0x80000000`–`0x801fffff`) or P2 uncached (`0xa0000000`–`0xa01fffff`),
  excluding the exact `0x80000000`/`0xa0000000` masks. That exclusion
  (`ScanBiosTargets.java:40`, `p != 0`) is a residual hole: this image
  contains two thunks (`0x8c0660f0` → `jmp @r3`, `0x8c066100` → `jmp @r2`,
  same block as hit #3 below, both dispatching through the struct at
  `0x8c1bf42c`) that compute their jump target as `0xa0000000 + <a runtime
  struct field>` — the excluded pool literal `0xa0000000` plus a value
  neither scan half can resolve, so if that field is ever `< 0x200000` this
  is a BIOS-code call invisible to both halves. Task 9's dynamic
  `no_bios_exec` check is the expected backstop if it ever fires.

### Result: 5 candidates (not NONE)

`RESULT: 5 candidate(s) — inspect each`. Per the spec, each is recorded here
rather than dropped, with containing function and manual follow-up
(`DisasmRange.java`, and direct byte reads of `tools/boot.bin` at
`file offset = address − 0x8c020000`, same method used throughout this doc).

| # | Kind | Address | Value/target | Containing fn | Use | Assessment |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | BIOSREF (`COMPUTED_JUMP`) | `0x8c1035b8` | to `0x0009402b` | `FUN_8c103408` (`0x8c103408`–`0x8c103a4b`) | `jmp @r0` ending a 5-way jump table: `shll2 r13; mova 0x8c1035bc,r0; mov.l @(r0,r13),r0; jmp @r0`, index bounds-checked `0<=r13<=4` by the two `cmp`/`bt`/`bf` pairs immediately before it | **Static-analysis artifact, not a real BIOS call.** The 5 actual table entries, read directly from `tools/boot.bin` at `0x8c1035bc`–`0x8c1035cf`: `0x8c1035d0, 0x8c103764, 0x8c103698, 0x8c103838, 0x8c103910` — all local code in/near the same function. None matches `0x0009402b`; Ghidra's `COMPUTED_JUMP` resolver produced a value that is not any of the table's real contents (the index `r13` is data-dependent, not a compile-time constant). |
| 2 | POOLBIOS | `0x8c023b90` | `0x80000200` | `FUN_8c023aa4` | Not dereferenced: `mov.l 0x8c023b90,r1; shll16 r2; or r1,r2; mov.l r2,@r5` — folded into a composed word stored to memory | Coincidental VA-shaped literal (register/descriptor-style constant), never used as an address. |
| 3 | POOLBIOS | `0x8c066120` | `0xa0060000` | `FUN_8c065ff0` | **Dereferenced**: `mov.l 0x8c066120,r1` → `mov.l @r1+,r4` in an 8-word compare loop (`and r6,r4; cmp/eq r0,r4`), value reloaded as `r6` for a `mov.l @r6+,r3` copy loop | **Real BIOS-range data access** — reads/copies words directly from P2-uncached phys `0x00060000` (inside the BIOS ROM span). Mandatory Task 9/10 follow-up: what Naomi BIOS holds there and whether it must be reproduced for the DC loader. |
| 4 | POOLBIOS | `0x8c066ae0` | `0x80000300` | `FUN_8c066964` | Not dereferenced: `mov.l 0x8c066ae0,r3; mov.l r3,@-r1` — one of several values pushed the same way (others sourced from `r13`, a `.w` pool) building what looks like an argument list | Coincidental VA-shaped literal, never used as an address. |
| 5 | POOLBIOS | `0x8c06711c` | `0xa01ffd00` | `FUN_8c067084` | **Dereferenced**: `mov.l 0x8c06711c,r6` → `mov.b @r6,r1` in a byte-compare loop | **Real BIOS-range data access** — byte reads from P2-uncached phys `0x001ffd00` (near the top of the 2 MB BIOS window). Mandatory Task 9/10 follow-up, same as #3. |

Two of five (#3, #5) are genuine reads of BIOS-ROM *contents*; no hit is a
`jsr`/`jmp` that actually resolves into BIOS *code* (the one flow-reference
hit, #1, is contradicted by the jump table's real contents, read directly
from the image). Two (#2, #4) are coincidental VA-shaped constants never
used as addresses.

> **Verdict: no confirmed BIOS-code call.** Two confirmed BIOS-ROM
> *data* reads (phys `0x00060000`, `0x001ffd00`) carried forward as
> mandatory Task 9/10 follow-ups — the Phase 4 loader must supply
> equivalent data at those physical offsets (or reimplement whatever the
> read is checking) for the port to work. The one computed-jump hit is
> explained by manual verification as a scan/tooling artifact, not silently
> dropped.

Caveat (spec, verbatim): "a computed non-pool branch target could evade the
static scan; the dynamic backstop covers executed paths only." Dynamic
half: Task 9.

## MMIO xref sweep — cart / G1 / Maple / PVR-FB / RTC / SCIF / WDT

Evidence: `scripts/ghidra/run.sh script FindMmioXrefs.java` against the same
`senkosp3` project. The script reports every instruction operand and every
*defined* 32-bit data word whose value, masked `& 0x1fffffff`, lands in a
watched physical block. Full output: `tools/mmio-xrefs.txt` (gitignored).

Watched blocks (`FindMmioXrefs.java:13-22`), all physical:

| Label | Range | What |
| --- | --- | --- |
| `cart` | `0x005f7000`–`0x005f7014` | Naomi ROM-board regs (`../flycast4naomi2dreamcast/core/hw/naomi/naomi_regs.h:9-14`) |
| `g1dma` | `0x005f7400`–`0x005f74ff` | G1 / GD-DMA channel (`.../core/hw/holly/sb.h:150-183`) |
| `maple` | `0x005f6c00`–`0x005f6cff` | Maple bus controller (`.../core/hw/holly/sb.h:116-135`) |
| `pvr_fb` | `0x005f8050`–`0x005f8067` | `FB_R_SOF1/2`, `FB_W_SOF1/2` (`.../core/hw/pvr/pvr_regs.h:31-36`, offsets from PVR base `0x005f8000`) |
| `rtc` | `0x00710000`–`0x0071ffff` | AICA RTC counter (`.../core/hw/holly/sb_mem.cpp:35`) |
| `scif` | `0x1fe80000`–`0x1fe8ffff` | SH-4 SCIF (`.../core/hw/sh4/sh4_mmr.h:382-406`) |
| `wdt` | `0x1fc00000`–`0x1fc000ff` | SH-4 WDT `WTCNT`/`WTCSR` (`.../core/hw/sh4/sh4_mmr.h:235,:238`) |

In the listings below, everything up to the `;` is verbatim script output;
text after a `;` is annotation added here. Every pool word quoted was
re-read byte-for-byte from `tools/boot.bin` (file offset = address −
`0x8c020000`).

### Hit counts, and the raw-value triage

`TOTAL hits=72`, all of them `POOL` (literal-pool words); zero `XREF`
(instruction-operand) hits — senkosp materialises every MMIO address through
a pc-relative pool load, never as an inline scalar.

The `& 0x1fffffff` mask that makes the scan catch P1/P2 mirrors also makes it
catch *any* word sharing those low 29 bits, so each hit was resolved back to
its raw value before being counted as real:

| Block | Hits | Raw pool values | Real MMIO refs |
| --- | --- | --- | --- |
| `cart` | 3 | `0xa05f7000` ×1, `0xa05f700c` ×2 | 3 |
| `g1dma` | 10 | `0xa05f7418` ×5, `0xa05f7480/7484/7490/74a4/74b8` ×1 each | 10 |
| `maple` | 11 | `0xa05f6c04` ×4, `0xa05f6c14` ×2, `0xa05f6c00/6c10/6c18/6c80/6c8c` ×1 each | 11 |
| `pvr_fb` | 0 | — | 0 (see below) |
| `rtc` | 3 | `0xa0710000` ×2, `0xa0710004` ×1 | 3 — matches the guts scan's "3 MMIO refs" (`docs/kb/00-status.md` §Key facts) |
| `scif` | 2 | `0xffe80020` ×1, `0xffe80000` ×1 | 2 |
| `wdt` | 43 | `0x3fc00000` ×37, `0xbfc00000` ×4, `0xffc00004` ×2 | **0** |

> **Verdict: zero watchdog references.** `WTCNT` (`0xffc00008`) and `WTCSR`
> (`0xffc0000c`) do not appear anywhere in the image. All 43 `wdt`-block hits
> are false positives of the 29-bit mask: 41 are the IEEE-754 float constants
> `1.5f` (`0x3fc00000`) and `-1.5f` (`0xbfc00000`), and the remaining 2 are
> `0xffc00004` = **CPG `STBCR`**, not WDT
> (`../flycast4naomi2dreamcast/core/hw/sh4/sh4_mmr.h:232`) — both inside the
> serial driver (see §RTC / SCIF / watchdog).

### Coverage limits of this scan (read before trusting a zero)

An independent raw scan of every 4-byte-aligned word in `tools/boot.bin`
finds strictly more MMIO-shaped words than Ghidra reports, because
`FindMmioXrefs` only sees *defined* data and *disassembled* operands:

```sh
python3 -c 'import struct;b=open("tools/boot.bin","rb").read()
for o in range(0,len(b)-3,4):
 v=struct.unpack_from("<I",b,o)[0];p=v&0x1fffffff
 if 0x5f7000<=p<=0x5f7014: print("%08x %08x"%(0x8c020000+o,v))'
```

| Block | Ghidra hits | Raw-scan words in range | Of those, plausible MMIO addresses |
| --- | --- | --- | --- |
| `cart` | 3 | 11 | 11 |
| `g1dma` | 10 | 19 | 19 |
| `maple` | 11 | 20 | 20 |
| `pvr_fb` | 0 | 6 | 6 |
| `rtc` | 3 | 16 | 3 (`0xa0710000/4`, plus one `0xa0710008`) |
| `scif` | 2 | 37 | 2 |
| `wdt` | 43 | 173 | 0 |

Three distinct blind spots, all confirmed:

1. **Undefined data.** Ghidra's auto-analysis left large spans of the
   hardware-driver block undisassembled and undefined — `Decomp.java` reports
   `NO FUNCTION` at `0x8c0663a8`, `0x8c0663c8`, `0x8c066400`, `0x8c066460`,
   `0x8c0664cc`, `0x8c0664e0`, `0x8c066500`, `0x8c066564`, `0x8c0665a0`,
   `0x8c0665e0`, and `DisasmRange.java 0x8c0663a8 0x8c066600` returns
   instructions only for `0x8c0664b4`–`0x8c0664ca` and `0x8c0665f0`–onward.
   The cart pool words at `0x8c06642c`/`0x8c066430`/`0x8c06643c` and
   `0x8c066534`–`0x8c066544`, and the `SB_GDSTAR`/`SB_GDLEN`/`SB_GDDIR` words
   at `0x8c066554`–`0x8c06655c`, sit in those undefined spans and are
   therefore missing from the Ghidra counts.
2. **Base-pointer access.** Registers reached as *base + displacement* are
   structurally invisible to a constant-range scan. This is why `pvr_fb` = 0:
   the only `FB_R_SOF1/2`/`FB_W_SOF1/2` words in the image
   (`0x8c15c798`–`0x8c15c7ac`) are entries in a register-address *table*, and
   the PVR base `0xa05f8000` is loaded once as a pool word at `0x8c032160`.
   Same mechanism inside the serial driver: it reaches SCIF through a pointer
   (`0x8c02cbb4` → `0x8c15c938` → `0xffe80000`), so only the pointer's target
   word is visible, not the individual register accesses.
3. **Data tables.** A block of MMIO addresses used as *data* lives at
   `0x8c15c3e8`–`0x8c15c7b4` (a `(register, value)` init-pair list, then a
   flat register-address list). These are real references to the registers but
   are not code sites.

> **Verdict: `pvr_fb` = 0 is a scan limitation, not an absence.** senkosp
> does place framebuffers; it just never loads `FB_*_SOF*` as a whole-address
> pool constant. Framebuffer placement must be traced through the PVR base
> pointer (`0x8c032160`) or dynamically, not by constant xref.

### Candidates

Candidate function ranges for Task 9 to prove (`--cart-fn` / `--input-fn` /
`--eeprom-fn`). P1 hex, inclusive. These are **candidates**: derived
statically from where the register constants live, unproven until Task 9
drives them.

```
cart_fn: 0x8c0661e0-0x8c066560,0x8c0678c2-0x8c067e18
input_fn: 0x8c0665fe-0x8c066b0f
eeprom_fn: 0x8c0665fe-0x8c066b0f
```

**Why these bounds are spans, not Ghidra function bodies.** Every recovered
body in this block is truncated relative to the pool words its own code
loads — e.g. `FUN_8c0664b4` has body `0x8c0664b4`–`0x8c0664cb` (24 bytes) yet
its two instructions load pools at `0x8c066530` and `0x8c066550`, and the
gaps between bodies are the undefined spans of blind spot (1) above. Each
range is therefore taken as *the contiguous span from the end of the last
cleanly-recovered function before the block to the last register pool word in
it*, which is the smallest window guaranteed to contain the whole driver.

`cart_fn` range 1 — `0x8c0661e0`–`0x8c066560`. LO = first byte after
`FUN_8c0661b2`'s body end (`0x8c0661df`); HI = last G1 pool word
`0x8c06655c` + 4. Contains all 11 `cart`-block and 12 of the 19 `g1dma`-block
words, plus the two recovered functions in it:

- `FUN_8c066288` (`0x8c066288`–`0x8c066395`) — **G1 bus-timing setup.** Takes
  a clock/speed parameter and, per a 7-way `if/else` on it, writes
  `SB_GDAPRO` (`0xa05f74b8`), `SB_G1RRC`/`SB_G1RWC` (`0xa05f7480`/`7484`),
  `SB_G1CRC` (`0xa05f7490`) and `SB_G1GDWC` (`0xa05f74a4`).
- `FUN_8c0664b4` (`0x8c0664b4`–`0x8c0664cb`) — **cart DMA arm.**
  `if (*SB_GDST != 0) return 0; *NAOMI_DMA_OFFSETH = <const>; return 1;`
  (`SB_GDST` = `0xa05f7418`, `NAOMI_DMA_OFFSETH` = `0xa05f700c`). The
  `SB_GDSTAR`/`SB_GDLEN`/`SB_GDDIR` and `NAOMI_ROM_OFFSETH/L`/
  `NAOMI_ROM_DATA`/`NAOMI_DMA_OFFSETL`/`NAOMI_DMA_COUNT` words follow at
  `0x8c066534`–`0x8c06655c`, in the undefined span — i.e. the real cart-read
  routine extends past `0x8c0664cb`.

`cart_fn` range 2 — `0x8c0678c2`–`0x8c067e18`. The layer above: three
recovered wrappers that spin on `SB_GDST` and then dispatch through a
function pointer — `FUN_8c0678c2`, `FUN_8c0679b4`, `FUN_8c067b48` — plus
their shared pool area holding the remaining four `0xa05f7418` words
(`0x8c067970`, `0x8c067adc`, `0x8c067c44`, `0x8c067e14`). Note this range
also encloses the RTC reader `FUN_8c067c82` (below); that is expected, they
are neighbours in the same runtime library.

`input_fn` / `eeprom_fn` — `0x8c0665fe`–`0x8c066b0f`, the union of the two
recovered maple functions and the pool gap between them. **Input and EEPROM
share this path**, so both names resolve to the same range, per the plan's
"record both names anyway":

- `FUN_8c066964` (`0x8c066964`–`0x8c066b0f`) — **maple init + first
  transaction.** Writes `NAOMI_DMA_OFFSETH` (`0xa05f700c`), then
  `SB_MDEN = 0` (`0xa05f6c14`), `SB_MDAPRO` (`0xa05f6c8c`), `SB_MSYS`
  (`0xa05f6c80`), `SB_MDTSEL = 0` (`0xa05f6c10`), `SB_MDSTAR` = command-table
  address (`0xa05f6c04`), builds a maple frame, then `SB_MDEN = 1`,
  `SB_MDST = 1` (`0xa05f6c18`), polls `SB_MDST` to zero, `SB_MDEN = 0`.
  Reached from the system init `FUN_8c085b00` via the thunk at `0x8c06f9d0`
  (pool `0x8c085bb4`).
- `FUN_8c0665fe` (`0x8c0665fe`–`0x8c06694b`) — **maple device scan**, called
  at the end of `FUN_8c066964`; same DMA sequence in a retry loop, walking
  `0x18`-byte response records. This is the JVS/MIE enumeration Phase 2 saw
  as `MIERESP sub=0x01`/`0x03` in every leg
  (`docs/kb/phase2-measurements.md` §Device verdicts).

The EEPROM path (`MIERESP sub=0x0b`, test-menu only — same source) is *not* a
separate MMIO path: it is a different maple *frame payload* pushed through
this same DMA. The `sub=0x0b` frame builder is higher-level code with no MMIO
constant of its own, so this scan cannot name it; it needs the MIE-response
trace, not an xref.

**MMIO sites deliberately outside the ranges** (recorded so nothing is
silently dropped):

- `FUN_8c02751a` (`0x8c02751a`–`0x8c02751f`) — `return DAT_8c0275e8;`, i.e. a
  one-line accessor returning the constant `0xa05f7000`. Never dereferences
  it; not a cart access.
- `FUN_8c026b30` (`0x8c026b30`–`0x8c026b3b`) — stores the constant
  `0xa05f6c00` into a struct field. Records the maple base somewhere; not an
  access.
- `0x8c066a88` (`0xa05f700c`) is a `cart`-block site that falls in
  `input_fn`, not `cart_fn`: it is the `NAOMI_DMA_OFFSETH` write inside the
  maple init `FUN_8c066964`, not part of the cart-read path.
- `0x8c15c3e8`–`0x8c15c7b4` and `0x8c15c938` — the register-address data
  tables of blind spot (3).

Together those account for every one of the 11 `cart`, 19 `g1dma` and 20
`maple` words the raw scan finds: each is either inside a candidate range or
listed above.

### RTC / SCIF / watchdog

Static half of the device question (target 8). Classification per the plan:
dead code / compile-time gated / reachable.

**RTC — 3 refs, both sites reachable, reads only.**

The 3 pool words are `0xa0710000` (`0x8c029f98`, `0x8c067ddc`) and
`0xa0710004` (`0x8c067de0`). This is the **AICA RTC counter**, whose two
halves are exactly what flycast serves at those offsets — `case 0:` returns
`RealTimeClock >> 16`, `case 4:` returns `RealTimeClock & 0xFFFF`
(`../flycast4naomi2dreamcast/core/hw/aica/aica_if.cpp:60-68`).

```c
// FUN_8c067c82 @8c067c82  body 8c067c82..8c067ca5
*(int *)*DAT_8c067de4 =
     ((*DAT_8c067ddc << 0x10 | *DAT_8c067de0 & 0xffff) - *DAT_8c067de8) +
     ((int *)*DAT_8c067de4)[1];        ; hi<<16 | lo  ->  32-bit RTC seconds
```

Reachable, not dead: its caller `FUN_8c068034` (`0x8c068034`–`0x8c0680b7`)
is a periodic tick that, every 16th call and only while G1 DMA is idle, calls
it through the pointer at `0x8c0680d0` (= `0x8c067c82`, verified in the
image); the busy test at `0x8c0680c4` is `FUN_8c066396`, the `SB_GDST`
reader. `FUN_8c068034` is itself exported through the thunk at `0x8c07157e`.

The second site is a debounced read: `FUN_8c029e8c` (`0x8c029e8c`–
`0x8c029ee7`) passes `0xa0710000` to a generic reader
(`(*(code *)PTR_FUN_8c029f9c)(DAT_8c029f98,&local_10,4,2,1,1)`) and
recombines `hi<<16 | lo`; `FUN_8c029e00` calls it until three consecutive
reads agree; `FUN_8c029a74`/`FUN_8c029a3c` sit above that. **No write to any
RTC register exists anywhere in the image** — no `0xa0710008` store, which is
the enable register flycast requires before a write takes effect
(`aica_if.cpp:100`, `rtc_EN = data & 1`).

> **Verdict: RTC — ignore, no shim.** The register is not Naomi-specific:
> flycast's area-0 handler maps `0x00710000`–`0x0071000b` to the AICA RTC
> outside any `if constexpr (System == ...)` guard, i.e. identically for
> Dreamcast, Naomi and Atomiswave
> (`../flycast4naomi2dreamcast/core/hw/holly/sb_mem.cpp:118`, `:234`). Real
> Dreamcast hardware answers these reads. Phase 3 therefore closes the
> `rtc` guts flag: 3 refs, all reads, all of a register the target platform
> has.

**SCIF — 2 refs; one boot-path pin init, one debug console.**

- `0xffe80020` = `SCIF_SCSPTR2` (`.../core/hw/sh4/sh4_mmr.h:406`), pool
  `0x8c02c5e4`, written `0xc0` by `FUN_8c02c584` (`0x8c02c584`–`0x8c02c5d1`).
  That function is the machine bring-up: it also zeroes `0xffd00000`–
  `0xffd0000c` (SH-4 INTC) and then walks the `(register, value)` init-pair
  table at `0x8c15c3e8` — a single `SCSPTR2` write parking the serial pin, on
  the boot path (`FUN_8c085b00` → `FUN_8c02c37c` → `FUN_8c02c584`).
- `0xffe80000` = `SCIF_SCSMR2`, the SCIF register base
  (`.../core/hw/sh4/sh4_mmr.h:382`). It is not a code pool at all: it is the
  data word at `0x8c15c938`, pointed to by the pool at `0x8c02cbb4`. The
  sibling word `0x8c15c934` holds `0xffe00000`, the **SCI** base
  (`SCI_SCSCR1_addr 0x1FE00008`, `.../sh4_mmr.h:361`) — the driver picks one
  of the two at runtime from a flag.

What that driver is, from the decompilation:

```c
// FUN_8c02ca74 @8c02ca74 — serial putchar
do { } while ((*(ushort *)(*(int *)PTR_DAT_8c02cbb4 + 0x10) & 0x20) != 0x20);  ; wait SCFSR2.TDFE
*(undefined1 *)(*(int *)PTR_DAT_8c02cbb4 + 0xc) = param_1;                     ; write SCFTDR2
...
do { } while ((*(ushort *)(*(int *)puVar1 + 0x10) & 0x40) != 0x40);            ; wait SCFSR2.TEND
```

`+0x10` = `SCFSR2`, `+0xc` = `SCFTDR2` (`.../sh4_mmr.h:391,394`); bit `0x20`
= `TDFE`, bit `0x40` = `TEND` (`.../sh4_mmr.h:1185-1204`). Above it sit
`FUN_8c02cba6` (puts) and `FUN_8c02cbdc` (hex printer), and their one real
consumer is `FUN_8c02c5ec` (`0x8c02c5ec`–`0x8c02c823`), a **crash dump**:
it prints `"---- ADDRESS CHECKER TRAP ----"`, then `FR0-7:`, `FR8-15:`,
`FPUL:`, `FPSCR:`, `R0-7:`, `R8-15:`, `MACL:`, `MACH:`, `VBR:`, `GBR:`,
`DBR:`, `PR:`, `PC:`, `SR:`, a 0x45-entry table, then
`"Please cancel the interrupt from ..."` and blocks reading serial until it
receives `'\r'`. Its two callers (`0x8c02c8f2`, `0x8c02c9a4`) are not inside
any recognised function — exception-vector stubs.

The two `0xffc00004` words belong to the same driver and are the CPG
`STBCR`, not the WDT: `FUN_8c02c9ac` (serial init) does
`*DAT_8c02ca88 = *DAT_8c02ca88 & 0xfe` — clear bit 0 — before programming
the port, and `FUN_8c02cb50` (serial teardown) does
`*DAT_8c02cbc8 = *DAT_8c02cbc8 | 1` — set bit 0 — after. Module-stop-style
gating of the serial block around its use.

> **Verdict: SCIF — ignore, no shim.** One boot-path write of `0xc0` to
> `SCSPTR2` (idles the TX pin) plus a developer crash-dump console reachable
> only from an exception vector. Neither needs anything from the Dreamcast
> port: the DC has the same SH-4 SCIF at the same P4 addresses, so even if the
> trap handler fires the writes land on real hardware and are harmless. No
> game logic depends on a reply — the only serial *read* is the crash
> handler's "press Enter" loop, which is already a dead end on a cabinet with
> nothing attached.

**Watchdog — 0 refs.** See the `wdt` verdict above; nothing to shim, nothing
to ignore.

#### Cross-check against Phase 2 — and a correction to it

`docs/kb/phase2-measurements.md` §Device verdicts records `HW[RW]` = 0 for
`rtc` and `scif` across all 14 legs. That zero cannot be used as evidence
either way, because **the probe that emits `HW[RW]` was never enabled during
the campaign**: `cartlog_hwaccess()` returns immediately unless the
environment variable `FLYCAST_HWLOG` is set
(`../flycast4naomi2dreamcast/core/hw/mem/addrspace.cpp:118-120`), and
`scripts/capture_leg.sh:16` sets only `FLYCAST_CARTLOG`. `FLYCAST_HWLOG`
appears nowhere in this repository. Zero `HW[RW]` lines in every leg is a
null instrument, not a measurement — which also explains why the count is 0
for *every* address, including the cart and maple traffic the game
demonstrably performed.

Two further notes on that table:

- Its "serial (SCIF)" row also cites `SERIALPOKE` = 0. That probe is real
  (unconditional `cartlog`), but it watches the **Naomi communication board**,
  not the SH-4 SCIF: it fires only for
  `NAOMI_COMM_CTRL_addr`–`NAOMI_COMM_STATUS2_addr` = `0x5f7018`–`0x5f7028`
  (`../flycast4naomi2dreamcast/core/hw/naomi/naomi.cpp:119-120`). `SERIALPOKE`
  = 0 is therefore solid evidence that senkosp never touches the comm board
  — consistent with this scan finding no `cart`-block word above `0x5f7014` —
  and says nothing about SCIF.
- The watchdog row's argument ("0 pokes to any address ⇒ 0 to a watchdog
  address") inherits the same null instrument. The verdict survives anyway,
  on the stronger static ground above: `WTCNT`/`WTCSR` do not appear in the
  image at all.

Had `FLYCAST_HWLOG` been set, the probe *would* have covered both devices:
P4 system registers are mapped through `addrspace`
(`mapHandler(p4mmr_handler, 0xFF, 0xFF)`,
`../flycast4naomi2dreamcast/core/hw/sh4/sh4_mmr.cpp:658`), so `0xffe8xxxx`
accesses reach `cartlog_hwaccess`, and the parser's device ranges match
(`scripts/parse_cartlog.py:46`, tagging on `addr & 0x1fffffff`). A re-run
with the variable set is the cheap way to confirm the SCIF `SCSPTR2` write
dynamically, if Phase 4 ever wants it.

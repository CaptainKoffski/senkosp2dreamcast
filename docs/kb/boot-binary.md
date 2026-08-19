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
  excluding the exact `0x80000000`/`0xa0000000` masks.

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

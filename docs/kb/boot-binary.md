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

## The nine targets — answer index (Phase 3 exit criterion 1)

One row per target of the Phase 3 spec
(`docs/superpowers/specs/2026-08-19-phase3-reverse-engineering-design.md`
§The nine targets). "Static" = Ghidra/image evidence; "Dynamic" = a probe
firing in a capture leg. Targets 3 and 4 live in
`docs/kb/relocation-map.md` and are **not** duplicated here — this row set is
the index, that file is the answer.

| # | Target | Answer (address / verdict) | Static evidence | Dynamic evidence | Phase 4 implication | Where |
|---|---|---|---|---|---|---|
| 1 | BIOS-call verdict | **No BIOS-code call.** 5 static candidates, all resolved: 1 `COMPUTED_JUMP` tooling artifact, 2 coincidental VA-shaped literals, **2 genuine BIOS-ROM *data* reads** — `FUN_8c065ff0` (phys `0x00060000`, 28 KB blob → `0x0c018000`, and it **executes**) and `FUN_8c067084` (phys `0x001ffd00`, BIOS identity string; benign, has a DIP fallback) | `ScanBiosTargets.java`, both halves (flow refs + pool constants); `Decomp.java` on both readers; pool operands re-read from `tools/boot.bin` | `CHECK no_bios_exec: PASS` — 0 `BIOSEXEC` lines over boot→attract→match→test-menu; `PCSAMPLE pc=0c018b4a` proves the copied blob runs | **Mandatory:** loader must place the user's own Naomi-BIOS `0x60000` blob (28,672 B) at phys `0x0c018000`, or reimplement its 8 vectors. `0x001ffd00` needs nothing. | §BIOS-call verdict, §The two BIOS-ROM data reads |
| 2 | Cart-read function | **`FUN_8c027f54`, `0x8c027f54`–`0x8c027f99`**; kick = `SB_GDST` store at `0x8c027f72`. Dest programmed one frame earlier in `FUN_8c027a66`. PIO path `FUN_8c027d7e` (0 of the logged kicks) | `WhichFunc.java` body bounds; `DisasmRange.java 0x8c027f54 0x8c027f92`; `mov.w` pools `0x8c028014`=`0x0414`/`0x8c028016`=`0x0418` read from the image = `SB_GDEN`/`SB_GDST` | `CHECK dma_pc_in_cart_fn: PASS` — **672/672** `CARTDMAPC` PCs = `8c027f74` (= kick + 2) | The GD-ROM streaming shim's patch boundary. Static candidate ranges are the *register-programming* layer, not the trigger — see the un-promotion note | §Target: cart-read function; §Candidates (un-promotion) |
| 3 | Placement provenance | **One provenance site for all five corridors** (heap-top seed `0x8c085b50`) + **one for VRAM** (kmInitDevice size pool `0x8c03203c`) → 4-word patch set | — | — | — | **`docs/kb/relocation-map.md` §Provenance, §Patch set** |
| 4 | Relocation dry run | **PASSED** — 3 legs on `senkosp-reloc.dat`, all three gate CHECKs green, `exit=0`; operator-confirmed playable | — | — | — | **`docs/kb/relocation-map.md` §Dry-run evidence** |
| 5 | Input-decode function | **`FUN_8c02532a`, `0x8c02532a`–`0x8c025505`**; maple kick = `SB_MDST` store at `0x8c025446`. The per-frame poll is **sub `0x33`**, not sub `0x15` | `WhichFunc.java` body bounds; `mov.l r12,@(0x18,r2)` at `pc-2` read from the image = `SB_MDST`; base pointer supplied by the `0xa05f6c00` accessor `FUN_8c026b30` | **80 392** `MAPLEPC` sub-`0x33` events at `8c025448` (= store + 2), ~50/s = frame rate; `JVSREPORT` 83 220 ≈ `0x33`+`0x15` 83 268 | Phase 4's Maple/JVS shim must serve **sub `0x33`** (the boot-time driver `0x8c0665fe`–`0x8c066b0f` is real but boot-phase only) | §Target: input function; §`MDODMA` |
| 6 | EEPROM path | **Reads confirmed on the same path** (`FUN_8c02532a`, sub `0x01`/`0x03`). **Write call site NOT identified** — all 16 sub-`0x0b` events carry the vblank-artifact PC `0c03161e` | Static: no separate MMIO path — the `0x0b` frame is a payload on the same maple DMA (no constant of its own to xref) | 16 sub-`0x0b` writes observed (test-menu leg) — first ever seen in this project; PC unattributable by two independent probes (`MAPLEPC`, `MDODMA`) | Free-play forcing must be done by **subcommand filtering in the shim**, not by patching a call site. Naming the site needs a fork probe change (tag `maple_DoDma` caller) — Phase 4 flag | §Target: EEPROM; §Why three checks cannot pass |
| 7 | Stack-pointer verdict | **Final SP `0x8c00f000`** (phys `0x0c00f000`) — 60 KB above the bottom of RAM. **No SP relocation needed.** senkosp is **multi-stack**: a second (task) stack at `0x8c1d4984`, bounded to static BSS | `DumpEntryChain.java` — three SP writes, the last via pointer indirection `[0x8c021118]`→`[0x8c170c14]`, value byte-verified in `tools/boot.bin` | 672 `CARTDMAPC` SPs in two clusters: 118 in the boot stack (confirms it), 554 at `0x8c1d4984` | No patch. **But** the DC BIOS syscall vector block overlaps the stack region — matters only if the shim needs GD syscalls after SP init | §SP verdict, §Stack region, §SP — two stacks |
| 8 | RTC / SCIF / watchdog | **All three: ignore, no shim.** RTC = 5 words / 5 functions (2 live readers on a periodic tick, 3 writers behind an **unreferenced** setter `0x8c029b04`); SCIF = 1 boot-path `SCSPTR2` pin write + a crash-dump console on an exception vector; WDT = **0 refs** (all 43 hits are `1.5f`/`-1.5f` floats and CPG `STBCR`) | `FindMmioXrefs.java` + a raw whole-image word scan + `DisasmRange.java … force` to recover the undefined span; every register semantic cited to flycast source | **Static-only by nature** (spec §8: "the code never fires, so only disassembly can rule it dead"). Phase 2's "0 runtime pokes" was **retracted** — a null instrument (`FLYCAST_HWLOG` never set) | Nothing to shim: all three registers exist on DC at the same addresses. Note the live RTC *write* path would set the DC's own clock if ever reached | §RTC / SCIF / watchdog |
| 9 | Control layout | DC pad bindings, user-approved 2026-08-19 | Decided in the spec, not measured | Wire bits from Phase 2's 13/13 map | Phase 4 loader binds them; Test/Service access mechanism is a loader decision | **`docs/kb/input-map.md` §DC pad layout** |

**Open items carried into Phase 4, in one place** (each argued where cited):
the BIOS blob at `0x0c018000` (target 1, mandatory); the EEPROM-write call
site (target 6, needs a fork probe change); the game's restart path, which
jumps into Naomi BIOS (`relocation-map.md` §Deliberately not patched); and
the low-RAM syscall-vector overlap (target 7). `00-status.md` §Phase 4 flags
carries the full list.

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
Stack region: 8c000000-8c00f000     (derived here, NOT script output)
```

**Provenance note (Task 13 re-run):** unlike every other quoted block in this
section, this line is **not** `DumpEntryChain.java` output — the script emits
only the entry/hop headers and the instruction lines with the `<==` SP flag
(`scripts/ghidra/DumpEntryChain.java:31,41,60`). The region is derived below
from the SP value the script *does* report, and it is the value passed as
`--stack 8c000000-8c00f000` to `scripts/parse_cartlog.py`.

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

> **Correction (Task 9, dynamic): this region is the boot stack, not *the*
> stack — senkosp is multi-stack.** 554 of the 672 logged DMA-kick SPs sit at
> `0x8c1d4984`, ~1.8 MB above this region and past the end of the loaded image
> (`0x8c191ff8`). The span above is a *correct* description of the boot/init
> stack (118 SPs land in it) but an *incomplete* description of the game's
> stack usage. See §Dynamic reconciliation → "SP — two stacks". The free-space
> map (Task 10) must not treat `0x8c00f000`–`0x8c191ff8` as the only reserved
> low region.

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
static scan; the dynamic backstop covers executed paths only."

### Dynamic half (Task 9) — closed for code, still open for the two data reads

`captures/phase3/pc.log`, one interpreter leg covering boot → attract → coin →
a full match → the test-menu EEPROM sequence (provenance in §Dynamic
reconciliation):

```
CHECK no_bios_exec: PASS — 0 BIOSEXEC lines (expect 0)
```

`BIOSEXEC` fires from the interpreter's instruction-fetch path for any guest
PC with `(pc & 0x1fffffff) < 0x00200000` once the arming PC has been seen
(`../cleopatra/tools/flycast-src/core/hw/sh4/interpr/sh4_interpreter.cpp:31-44`).
Zero lines over the whole leg is therefore positive evidence on two counts:

- **The residual hole is not firing on any path this leg executed.** The
  `0xa0000000 + <runtime struct field>` thunks at `0x8c0660f0`/`0x8c066100`
  disclosed in (b) above never computed a target below `0x200000`. That is the
  backstop working as designed, not a scan that never ran.
- **The `COMPUTED_JUMP` hit #1 is confirmed a tooling artifact.** Had
  `0x8c1035b8` ever jumped to `0x0009402b`, this check would have caught it.

**Instrument validity — read before trusting the zero.** The arming PC is
`FLYCAST_ENTRYPC`, and its **compiled-in default is Cleopatra's trampoline
`0x8c04ae2c`** (`.../sh4_interpreter.cpp:35`), an address senkosp never
executes. Armed with that default the check would be a null instrument — the
same trap as the `FLYCAST_HWLOG` one dissected in §Cross-check against Phase 2.
It is *not* null here because `scripts/capture_leg.sh:17` exports
`FLYCAST_ENTRYPC="${FLYCAST_ENTRYPC:-8c021000}"`, senkosp's real entrypoint,
on every leg. That is a provenance argument, not a self-evidencing one: the
log records no arming event, so a leg launched *without* `capture_leg.sh`
would produce an identical, meaningless `PASS`. The cheap hardening
`capture_leg.sh:16` already anticipates — export `FLYCAST_ENTRYPC` to a PC the
game *does* execute and confirm `BIOSEXEC` fires — remains the canary worth
running once.

> **Verdict: no BIOS-code call, static and dynamic.** The static half found no
> `jsr`/`jmp` resolving into BIOS; the dynamic half executed the game through
> boot, attract, a match and the test menu without a single instruction fetch
> inside the BIOS window. §8-3 is answered for code.
>
> **Still open: the two BIOS-ROM *data* reads** (#3 phys `0x00060000`, #5 phys
> `0x001ffd00`). `BIOSEXEC` watches *execution*, not loads, so this leg says
> nothing about them, and the probe that would (`HW[RW]`) is the one
> §Cross-check against Phase 2 shows was never enabled. They stay mandatory
> Task 10 follow-ups exactly as recorded above — a re-run with
> `FLYCAST_HWLOG` set is the cheap way to learn whether either read actually
> happens on a live path.

### The two BIOS-ROM data reads, decoded (Task 10 — follow-up closed)

Both readers were decompiled (`Decomp.java 0x8c065ff0 0x8c067084`) and their
pool operands read byte-for-byte from `tools/boot.bin`.

**#3 — `FUN_8c065ff0`, phys `0x00060000`: the Naomi BIOS leaves a runtime
blob there, and the game copies it into RAM.** The function:

1. Unconditionally stores `[0x8c066118]` = `0xac018000` into the global
   `[0x8c06611c]` = `0x8c1bf42c` — the same struct the two computed-jump
   thunks at `0x8c0660f0`/`0x8c066100` dispatch through (§BIOS-call verdict
   residual hole).
2. Checks 8 words at `0xa0060000` (`[0x8c066120]`): each must satisfy
   `(word & 0x0fff0000) == 0x0c010000` (`[0x8c066128]`/`[0x8c066124]`) —
   i.e. the BIOS ROM at `0x60000` must begin with 8 pointers into low main
   RAM `0x0c01xxxx`: an entry-vector table.
3. On match, copies `[0x8c066114]` = `0x1c00` words (28,672 B) from
   `0xa0060000` to `0xac018000` — phys `0x0c018000`–`0x0c01efff`, between
   the VBR/scratch block and the load image.

So the "BIOS data" is a **28 KB BIOS-resident runtime with an 8-entry
vector table**, re-hosted into RAM and called through the `0x8c1bf42c`
struct. **And it demonstrably runs:** the Task 9 leg contains
`PCSAMPLE pc=0c018b4a` — the guest executing *inside* the copied blob
(phys `0x0c018000`–`0x0c01efff`). `BIOSEXEC` never fired because the code
runs from RAM, not from the BIOS window; this is why the §BIOS-call verdict
could stay "no BIOS-code call" while BIOS-*derived* code executes anyway.
**Phase 4 implication (mandatory):** on DC the `0xa0060000` read returns DC
BIOS bytes, the signature fails, nothing is copied — but the pointer at
`0x8c1bf42c` is installed regardless, so the live thunk path would jump
into uninitialized RAM. The loader must place the 28,672-byte blob from the
user's own Naomi BIOS dump (offset `0x60000`) at phys `0x0c018000` at boot
(never commit those bytes; extract at build/load time), or reimplement the
8 vectored services.

**#5 — `FUN_8c067084`, phys `0x001ffd00`: Naomi BOOT ROM identity check.**
Compares `0x70` bytes at `0xa01ffd00` (`[0x8c06711c]`) against the in-image
string at `[0x8c067118]` = `0x8c180891`, deobfuscated per byte as
`bios[i] == img[i] − (i & 7)`. Decoding the image string yields:

```
COPYRIGHT (C)SEGA ENTERPRISES,LTD.\0 1998 All rights reserved by SEGA
ENTERPRISES,LTD.\0 …\xff… NAOMI BOOT ROM\0
```

— the Naomi BIOS copyright block. On match it sets the flag
`[0x8c067114]` = `0x8c1bf430` = 1. Its consumer is the system init
`FUN_8c06773a` (which calls the check): when the flag is **0** it falls
back to deriving the parameter from the DIP switches — **the library
already has a working "not a Naomi BIOS" fallback path.** **Phase 4
implication:** on DC the flag is simply 0 and the fallback runs; benign,
nothing to synthesize. (If the fallback value ever proves wrong, the
one-byte fix is to pre-set `0x8c1bf430` from the loader.)

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
| `rtc` | 3 | `0xa0710000` ×2, `0xa0710004` ×1 | 3 *defined*; the image actually holds **5** — see below |
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
| `rtc` | 3 | 16 | **5** (`0xa0710000` ×2, `0xa0710004` ×2, `0xa0710008` ×1) |
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
   therefore missing from the Ghidra counts. **The same gap hides two of the
   five RTC words**: `0x8c029ee8`–`0x8c029f5b` was undefined, so the pools at
   `0x8c029fa4` (`0xa0710008`) and `0x8c029fac` (`0xa0710004`) — and the three
   functions that load them — did not appear at all until the span was
   force-disassembled (`DisasmRange.java <lo> <hi> force`, see §RTC). Note
   that recovering the *code* does **not** close the gap: re-running
   `FindMmioXrefs` afterwards still reports `rtc` = 3, because `run.sh script`
   passes `-noanalysis` and nothing promotes those two words to *defined*
   data. This is the blind spot that matters most: **a zero, or a low count,
   from this scan is never on its own evidence of absence.**
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

> **Task 9 outcome: NOT promoted — but for two different reasons, one per
> range.** The checks measure the PC at the **trigger store** (`SB_GDST = 1`,
> `SB_MDST = 1`), and the two candidates fail that test in unrelated ways:
>
> - **`cart_fn` is the wrong layer.** Every one of the 672 DMA kicks is a
>   `SB_GDST` store at `0x8c027f72`, in a different block entirely, reached
>   through a **struct base pointer** — blind spot (2) above doing exactly what
>   that section warned it would do. These ranges hold the register-programming
>   code that runs *before* the trigger (G1 bus timing, the
>   `SB_GDSTAR`/`GDLEN`/`GDDIR` arm). They never kick a cart DMA.
> - **`input_fn`/`eeprom_fn` is the right code but the wrong *phase*.** This
>   range does kick maple DMA, exactly as `FUN_8c066964` and `FUN_8c0665fe` are
>   described below — **1035 times in the leg**, from five `SB_MDST` stores
>   (`0x8c066726` ×1023, plus `0x8c066810`/`0x8c0668a2`/`0x8c066926` in the
>   device scan and `0x8c066a5e` in the init). It is the **boot-time** maple
>   driver, and it is real. What it is *not* is the **steady-state per-frame**
>   path: that is `FUN_8c02532a`, `0x8c025446`, 80 392 kicks. The check FAILs
>   because it filters sub `0x15`, and no sub-`0x15` line comes from this
>   range at all.
>
> **Nothing below is retracted** — least of all the `SB_MDST` store-and-poll
> attributed to `FUN_8c066964`/`FUN_8c0665fe`, which the log confirms
> instruction for instruction. A Phase 4 reader should take this block as a
> live maple call site, just a boot-time one. The confirmed steady-state sites,
> and why the static scan could not find them, are in §Dynamic reconciliation.

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

**RTC — 5 register words in 5 functions: 2 readers (reachable) and a complete
3-function write path (unreferenced).**

`FindMmioXrefs` reports 3, because two of the words sit in a Ghidra-undefined
span (blind spot (1) above). The image holds **five**:

| Pool word | Value | Loaded at | Function | Direction |
| --- | --- | --- | --- | --- |
| `0x8c029f98` | `0xa0710000` | `0x8c029e9a` | `FUN_8c029e8c` | read (both halves, stride) |
| `0x8c029fa4` | `0xa0710008` | `0x8c029ef0` | `0x8c029ee8`–`0x8c029f0f` | **write** (enable) |
| `0x8c029fac` | `0xa0710004` | `0x8c029f1e` | `0x8c029f10`–`0x8c029f35` | **write** (low half) |
| `0x8c029f98` | `0xa0710000` | `0x8c029f44` | `0x8c029f36`–`0x8c029f5b` | **write** (high half) |
| `0x8c067ddc` / `0x8c067de0` | `0xa0710000` / `0xa0710004` | `0x8c067c82` / `0x8c067c86` | `FUN_8c067c82` | read |

This is the **AICA RTC counter**, whose halves are exactly what flycast serves
at those offsets — `case 0:` returns `RealTimeClock >> 16`, `case 4:` returns
`RealTimeClock & 0xFFFF`, `case 8:` returns constant `0`
(`../flycast4naomi2dreamcast/core/hw/aica/aica_if.cpp:60-68`). Offset 8 being
read-as-zero is why a *load* of `0xa0710008` can only be a write-enable: there
is nothing there to read.

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
reads agree; `FUN_8c029a74`/`FUN_8c029a3c` sit above that.

**The write path.** Three sibling leaf functions immediately after
`FUN_8c029e8c`, all structurally identical, all calling the *mirror* helper
(pool `0x8c029fa8` = `0x8c02afe4`, versus the reader's `0x8c029f9c` =
`0x8c02ac28`) with the MMIO address and buffer arguments **swapped** — `r4` =
buffer, `r5` = register, `r6` = 4, `r7` = 1, where the reader passes `r4` =
register, `r5` = buffer, `r7` = 2:

```
8c029ef0  mov.l 0x8c029fa4,r5      ; r5 = 0xa0710008   (write-enable)
8c029ef4  mov.w r3,@r15            ; buffer = 1        (r3 = 1, immediate)
8c029f02  jsr @r3                  ; r3 = [0x8c029fa8]
8c029f1e  mov.l 0x8c029fac,r5      ; r5 = 0xa0710004   (low half),  buffer = param
8c029f44  mov.l 0x8c029f98,r5      ; r5 = 0xa0710000   (high half), buffer = param
```

Their one caller, `0x8c029b04`–`0x8c029b55`, is a complete **RTC setter** that
follows flycast's write protocol exactly (`aica_if.cpp:78-100`: offset 8 arms
`rtc_EN`, offset 4 writes the low half, offset 0 writes the high half and
clears the arm):

```
8c029b08  bsr 0x8c029b94           ; fetch the 32-bit value to set -> [r15]
8c029b0c  bsr 0x8c029ee8           ; enable   ; bail via bf 0x8c029b4e on failure
8c029b18  bsr 0x8c029f10           ; low half (extu.w r4,r4)
8c029b26  bsr 0x8c029f36           ; high half (shlr16 r4; extu.w r4,r4)
8c029b30  bsr 0x8c029e00           ; read back, accept value or value+1
8c029b46  mov.l r4,@r2             ; on match, store to [0x8c029c18]; return 0 / -1
```

> **Classification: the write path is dead code.** `0x8c029b04` has **no
> reference of any kind** in the image: no pool word anywhere in `boot.bin`
> holds `0x8c029b04`, and no `bsr`/`bra` in the whole ±4 KB PC-relative reach
> (`0x8c028b02`–`0x8c02ab00`, scanned raw) targets it. The three leaf writers
> are likewise referenced only from inside it. The residual hole is the one
> already disclosed in §BIOS-call verdict — a computed target no static scan
> resolves.

> **Verdict: RTC — ignore, no shim.** The register is not Naomi-specific:
> flycast's area-0 handler maps `0x00710000`–`0x0071000b` to the AICA RTC
> outside any `if constexpr (System == ...)` guard, i.e. identically for
> Dreamcast, Naomi and Atomiswave
> (`../flycast4naomi2dreamcast/core/hw/holly/sb_mem.cpp:118`, `:234`). Real
> Dreamcast hardware answers these accesses. Phase 3 closes the `rtc` guts
> flag: 5 words, 5 functions — 2 readers on live code paths, 3 writers behind
> an unreferenced setter, and every one of them targets a register the DC has.
>
> **Phase 4 note:** an RTC *write* path does exist, contrary to what a
> defined-data-only scan shows. If it is ever reached (computed target, or a
> service-menu clock-set screen no capture leg visited), it writes the
> **Dreamcast's own AICA RTC** — i.e. it would set the console clock. Not a
> port blocker and not something to shim, but worth knowing before anyone
> concludes an RTC store is a stray write.

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

## Dynamic reconciliation — Task 9 PC-capture leg

Dynamic half of the Phase 3 targets: drive the real game under the
instruction-exact interpreter and check where the PC actually is when the
hardware fires. Evidence: `captures/phase3/pc.log` (gitignored, 64 227 457 B),
one leg via `scripts/capture_leg.sh phase3/pc` — boot → attract through a demo
cycle → coin → one match with all five buttons and the stick → test menu →
Advertise Sound OFF → exit → re-enter → restore ON → quit.

**Full line census** — `awk '{print $1}' captures/phase3/pc.log | sort | uniq -c
| sort -rn`, every tag the file contains, reflowed into columns to fit. This is
the whole log, not a selection, so nothing in it goes unaccounted for:

```
842746 MDODMA      297292 PVRW        86222 MIERESP     86219 MAPLEPC
 83220 JVSREPORT    69307 TAREG       69306 TAEND       66524 C2D
  1614 PCSAMPLE      1601 SOFWR         672 CARTDMAPC     672 CARTDMA
   507 WATERMARK      169 VRAMREGS      169 VRAMPROFILE   169 VRAMHIST
   169 CARTPIOCNT     169 ARAMPROFILE   169 ARAMHIST      168 MAINPROFILE
   168 MAINHIST       136 LOWRAMWR      104 SETWR         104 CLOSERWR
   100 IMLWR           82 VIDFLG         22 CARTPIO        20 IOCHK
     8 ARAMREBASE       7 MMUCRWR         1 VRAMHANDOFF     1 MAINHANDOFF
     1 ARAMHANDOFF      1 HANG
```

`BIOSEXEC` is **absent from that list entirely** — `uniq -c` cannot emit a zero
row, so the count of 0 relied on elsewhere in this doc is the *absence* of the
tag, confirmed separately by `grep -c "^BIOSEXEC" … → 0`.

`MDODMA` is 92 % of the log and is **a second, independent maple probe** — see
"`MDODMA` — the wider maple probe" below; it is the reason the boot-time maple
driver could be attributed at all. The `PVRW`/`TAREG`/`TAEND`/`C2D` bulk is
render traffic, out of scope for Phase 3 targets. `HANG` ×1 and `IOCHK` ×20 are
Phase 4 probes riding along in the same build.

### Provenance and instrument checks (read before trusting any number below)

**The probes come from `../cleopatra/tools/flycast-src`, not
`../flycast4naomi2dreamcast`.** `scripts/capture_leg.sh:7` runs the build under
the *cleopatra* tree, so that tree is the source of truth for what these lines
mean. The two forks agree verbatim on `CARTDMAPC` and `MAPLEPC`, but only the
cleopatra tree carries `SOFWR`, `PCSAMPLE` and the `FLYCAST_ENTRYPC` arming
override — `scripts/parse_cartlog.py`'s docstring, which cites
`../flycast4naomi2dreamcast @ f014a410c`, is the older reference and does not
describe every line in this log.

**Interpreter confirmed, not assumed.** 1614 `PCSAMPLE` lines are present, and
`PCSAMPLE` is emitted from `Sh4Interpreter::ReadNexOp()`'s fetch path
(`.../core/hw/sh4/interpr/sh4_interpreter.cpp:68`) — a function the dynarec
never enters. Interpreter-exact PCs are therefore established for this leg,
which is what makes the `+2` reasoning below sound.

**`Dynarec.Enabled` was still `no` after the leg** (Flycast persists config on
exit). Restored to `yes` as part of this task; noted because a leg captured
with dynarec on would silently invalidate every PC in this section.

### The `+2` rule — what a logged PC actually is

Every probe logs `Sh4cntx.pc`. The interpreter advances that field **before**
executing the instruction it just fetched:

```c
// .../core/hw/sh4/interpr/sh4_interpreter.cpp:122-131  (verbatim)
u32 addr = ctx->pc;
cartlog_bios_check(addr);
...
ctx->pc = addr + 2;
return IReadMem16(addr);
```

So for a hardware event raised **synchronously by a guest store**, the logged
PC is `store_address + 2`. This holds through delay slots too: for `jsr` at
`A`, the slot at `A+2` is fetched via the same `ReadNexOp`, leaving
`ctx->pc = A+4` while the slot executes.

That rule is a **test**, not just a decoder — and applying it to every distinct
PC in this log splits them cleanly in two. Reading the instruction at `pc-2`
out of `tools/boot.bin` (file offset = address − `0x8c020000`):

| Probe | Logged PC | insn at `pc-2` | Store? |
| --- | --- | --- | --- |
| `CARTDMAPC` | `8c027f74` | `2142` `mov.l r4,@r1` | **yes** |
| `MAPLEPC` site A | `8c025448` | `12c6` `mov.l r12,@(0x18,r2)` | **yes** |
| `SOFWR` | `8c032146` | `2452` `mov.l r5,@r4` | **yes** |
| `MAPLEPC` site B | `0c03161e` | `4b08` `shll2 r11` | no |
| `SOFWR` | `0c054da8` | `8c1b` | no |
| `SOFWR` | `0c0548e4` | `d116` | no |
| `SOFWR` | `0c0548da` | `3010` | no |
| `SOFWR` | `0c0558ea` | `d217` | no |

Every PC logged in **P1** form (`8c…`) sits two bytes after a store; every PC
logged in **P0/U0** form (`0c…`) does not. senkosp genuinely executes from both
mirrors — `PCSAMPLE` finds the guest in `8c02/8c04/8c05` and in `0c02/0c03/0c04`
— so this is not a formatting artifact, and it is not a stale image either:
**no cart DMA in the whole leg writes into the loaded image span** (phys
`0x0c020000`–`0x0c191ff8`, 0 of 672 overlap), so `tools/boot.bin` *is* the code
that ran at these addresses. The split has a mechanical cause, given below.

### Target: cart-read function — **CONFIRMED** `FUN_8c027f54`

All **672** DMA kicks report one single PC, `8c027f74` → the store is at
`0x8c027f72`. Verbatim `DisasmRange.java 0x8c027f54 0x8c027f92`, annotations
after the `;`:

```
8c027f5e  mov.w 0x8c028014,r3      ; r3 = 0x0414
8c027f64  mov #0x58,r0
8c027f66  mov.l @(r0,r14),r2       ; r2 = obj->[0x58] = the G1/cart base pointer
8c027f68  add r3,r2                ; base + 0x414
8c027f6a  mov.l r4,@r2             ; SB_GDEN = 1   (r4 = 1, set at 8c027f58)
8c027f6c  mov.l @(r0,r14),r1
8c027f6e  mov.w 0x8c028016,r2      ; r2 = 0x0418
8c027f70  add r2,r1                ; base + 0x418
8c027f72  mov.l r4,@r1             ; SB_GDST = 1   <== THE DMA KICK
8c027f74  bsr 0x8c027e5e           ; <== logged PC (pc-2 = the kick)
```

The two `mov.w` pool words were read byte-for-byte out of `tools/boot.bin`:
`0x8c028014` = `0x0414`, `0x8c028016` = `0x0418`. Against the base `0xa05f7000`
those are `SB_GDEN` (`0x005F7414`, `.../core/hw/holly/sb.h:157`) and `SB_GDST`
(`0x005F7418`, `sb.h:159`) — and `SB_GDEN != 0` plus `data & 1` is exactly what
`Naomi_DmaStart` requires before it raises `CARTDMA`
(`.../core/hw/naomi/naomi.cpp:452-470`). Static and dynamic agree instruction
for instruction.

**Confirmed range: `0x8c027f54`–`0x8c027f99`** (`WhichFunc.java`, body bounds).
Contains the kick *and* the logged PC.

**Why the static scan could not find it.** Two compounding reasons, both
already named as blind spots earlier in this doc:

1. **Base pointer** — the address is `obj->[0x58] + disp`, never a whole-address
   pool constant. Blind spot (2). The base is the constant `0xa05f7000` that
   §Candidates dismissed under "MMIO sites deliberately outside the ranges" as
   *"`FUN_8c02751a` … Never dereferences it; not a cart access."* Locally true,
   and it is still the only function in the image that *returns* `0xa05f7000`
   — which makes it the obvious supplier of the base `FUN_8c027f54`
   dereferences. That link is inferred from the constant, not yet traced call
   by call; tracing it is a Task 10 item, and it does not affect the confirmed
   range above.
2. **16-bit offsets** — `0x0414`/`0x0418` are `mov.w` half-word pool words.
   `FindMmioXrefs.java` inspects *32-bit* defined words and instruction
   operands; a 16-bit displacement can never mask into an MMIO range.

> **Which side was wrong: the static side.** Not in what it described — the
> `0x8c0661e0`–`0x8c066560` range really is the G1 timing + DMA-arm code — but
> in the assumption that the code holding a register's *address constant* is
> the code performing the *trigger store*. In senkosp those are different
> functions in different blocks. The dynamic data was correct as logged.

### Target: input function — **CONFIRMED** `FUN_8c02532a`, via sub `0x33`

`MAPLEPC` by subcommand and PC (verbatim counts, whole leg):

| sub | at `8c025448` (real store) | at `0c03161e` (artifact) | what it is |
| --- | --- | --- | --- |
| `0x33` | **80 392** | 0 | receive-then-transmit JVS poll |
| `0x15` | 21 | 2855 | receive JVS data |
| `0x27` | 0 | 2810 | transmit with repeat |
| `0x17` | 27 | 45 | |
| `0x0b` | 0 | **16** | **EEPROM write** |
| `0x21` | 3 | 15 | |
| `0x31` | 6 | 5 | |
| `0x13` | 3 | 5 | |
| `0x01` | 3 | 5 | EEPROM read |
| `0x03` | 3 | 5 | EEPROM read |

The store at `0x8c025446` is `mov.l r12,@(0x18,r2)` in the delay slot of the
`jsr` at `0x8c025444`, with `r12 = 1` — i.e. `*(maple_base + 0x18) = 1` =
`SB_MDST` (`0x005F6C18`, `sb.h:123`), the maple DMA start. Same base-pointer
shape as the cart kick, and the same already-dismissed accessor supplies it:
§Candidates recorded *"`FUN_8c026b30` … stores the constant `0xa05f6c00` into a
struct field. Records the maple base somewhere; not an access."* That "somewhere"
is the struct field `FUN_8c02532a` dereferences — inferred from the constant,
not yet traced call by call, same caveat as the cart base above.

**Confirmed range: `0x8c02532a`–`0x8c025505`** (`WhichFunc.java`).

**The per-frame input poll is sub `0x33`, not sub `0x15`.** 80 392 events over
a ~27-minute leg (1614 one-per-second `PCSAMPLE` lines) is ~50/s — frame rate.
Sub `0x15`'s 2876 events are ~1.8/s and cannot be a per-frame poll. `0x33` is
*"Receive then transmit with repeat (15 then 21)"*
(`.../core/hw/maple/maple_jvs.cpp:1888`) — it calls `receive_jvs_messages`
then `send_jvs_messages`, the combined per-frame transaction. The
correspondence with `JVSREPORT` confirms it: 83 220 JVS reports vs 80 392 +
2876 = 83 268 `0x33`+`0x15` transactions.

This reproduces, independently and on a different game, the correction
Cleopatra had to make after its own Phase 3
(`../cleopatra/docs/kb/boot-binary.md` §5, "Addendum 2026-07-18 —
primary/secondary inversion"): the parser's `input_pc_in_input_fn` filters on
sub `0x15`, which is the **boot-phase** subcommand, so the check does not look
at the steady-state input path at all. Task 10 and the Phase 4 input shim must
serve sub `0x33`.

### Target: EEPROM — path confirmed, write call site **not** confirmable here

The static conclusion that *"input and EEPROM share this path"* is upheld: 3×
sub `0x01` and 3× sub `0x03` carry the real `SB_MDST` store PC, i.e. EEPROM
reads go through `FUN_8c02532a` like everything else. There is no PC-level
distinction between input and EEPROM; Phase 4 must differentiate by subcommand.

**The EEPROM *write* is observed but its call site is not.** The operator's
test-menu flip produced all 16 sub `0x0b` events — the first time this project
has seen an EEPROM write at all, and worth having — but every one of them
carries `0c03161e`, the artifact PC. This leg therefore proves the write
*happens* and says nothing about *where the game issues it from*.

### `MDODMA` — the wider maple probe, and the boot-time driver it reveals

`MAPLEPC` fires only inside `MIEImpl::handle_86_subcommand()`, i.e. only for
MIE command `0x86`. **`MDODMA enter` fires once per `maple_DoDma()` call**
(`.../core/hw/maple/maple_if.cpp:179`), whatever the command list contains, and
carries the same `pc=`. 89 578 `enter` lines, **12 distinct PCs** where
`MAPLEPC` showed 2 — and the `+2` store test separates them just as cleanly:

| `enter` count | PC | insn at `pc-2` | Store? | Where |
| --- | --- | --- | --- | --- |
| 81 016 | `8c025448` | `12c6` `mov.l r12,@(0x18,r2)` | **yes** | `FUN_8c02532a` — per-frame |
| 1023 | `8c066728` | `2572` `mov.l r7,@r5` | **yes** | `FUN_8c0665fe` — device scan |
| 3 | `8c066812` | `2572` `mov.l r7,@r5` | **yes** | `FUN_8c0665fe` |
| 3 | `8c0668a4` | `2572` `mov.l r7,@r5` | **yes** | `FUN_8c0665fe` |
| 3 | `8c066928` | `2572` `mov.l r7,@r5` | **yes** | `FUN_8c0665fe` |
| 3 | `8c066a60` | `2452` `mov.l r5,@r4` | **yes** | `FUN_8c066964` — init |
| 5787 | `0c03161e` | `4b08` `shll2 r11` | no | vblank trigger |
| 1705 | `0c031f36` | `8b07` | no | vblank trigger |
| 15 | `0c03179e` | `f20d` | no | vblank trigger |
| 10 | `0c031c80` | `8f07` | no | vblank trigger |
| 5 | `0c03204c` | `d12a` | no | vblank trigger |
| 5 | `0c03185c` | `034e` | no | vblank trigger |

Six of six P1 PCs are stores; zero of six P0 PCs are. The `+2` split now rests
on 12 points, not 3.

The `0x8c066726` site is the store-then-poll this doc already attributed to
`FUN_8c0665fe`, read straight out of `tools/boot.bin`:

```
8c066726  2572   mov.l r7,@r5     ; SB_MDST = 1   (r7 = 1)
8c066728  6252   mov.l @r5,r2     ; <== logged PC; poll it back
8c06672a  2228   tst r2,r2
8c06672c  8bfc   bf 0x8c066728    ; spin until the DMA completes
```

> **This is why §Candidates' `input_fn` range is un-promoted for *phase*, not
> for being the wrong code.** 1035 real maple kicks come out of it. `MAPLEPC`
> never showed them because that traffic is not MIE `0x86` — it is the maple
> device enumeration Phase 2 logged as `MIERESP sub=0x01`/`0x03`.

**What `MDODMA` does *not* buy: better attribution.** Both probes read the same
`Sh4cntx.pc` at the same moment, and the log proves it — joining every one of
the 86 219 `MAPLEPC` lines to its preceding `MDODMA enter` gives **0
mismatches**. So `MDODMA` widens *coverage* (all maple DMA, not just `0x86`)
without resolving the vblank problem below. Joining the 16 sub-`0x0b` EEPROM
writes to their `enter` lines puts **all 16 on `0c03161e`** — the write call
site stays unknown by a second, independent route.

### Why three checks cannot pass as written — the maple-trigger artifact

`MAPLEPC` is emitted inside `MIEImpl::handle_86_subcommand()`
(`.../core/hw/maple/maple_jvs.cpp:1758-1765`), which is downstream of
`maple_DoDma()`. `maple_DoDma()` has **two** callers:

- `maple_SB_MDST_Write()` — the guest's `SB_MDST = 1` store, synchronous
  (`.../core/hw/maple/maple_if.cpp:88-95`). Here `Sh4cntx.pc` is `store + 2`.
- `maple_vblank()` — the **hardware trigger**: when `SB_MDTSEL == 1` the
  controller starts the DMA on vblank by itself (`maple_if.cpp:50-64`). No
  guest store is involved, so `Sh4cntx.pc` is merely wherever the CPU happened
  to be — and because flycast's scheduler is cycle-deterministic and the guest
  is at the same point in its frame each time, that lands on the same
  instruction every time. Hence one stable, meaningless value.

That is the mechanical cause of the P1/P0 split — in the `+2` table, and again
across all 12 `MDODMA` PCs above: guest-store events are logged in the driver
code (P1); hardware-triggered events are logged wherever the main loop is (P0).
The four `SOFWR` P0 PCs are the same phenomenon on the PVR side. `MDODMA` does
not escape it either — it samples the same `Sh4cntx.pc` (0 mismatches over
86 219 joined lines).

> **Verdict: `input_pc_in_input_fn`, `eeprom_read_seen` and `eeprom_write_seen`
> cannot pass against any static range, and that is a probe limitation, not a
> wrong range.** The checks test the DMA-kick PC; for vblank-triggered maple
> transactions there is no kick PC to test. Neither widening a range nor
> re-deriving one can fix it — a range covering `0x8c03161c` would be asserting
> that `FUN_8c031560` issues maple commands, which the disassembly disproves.
>
> **A per-`DoDma` PC probe already exists and does not solve this** — see
> `MDODMA` above. It widens coverage to every maple DMA and is what exposed the
> boot-time driver's 1035 kicks, but it reads the same `Sh4cntx.pc`, so
> vblank-triggered transactions are just as unattributable there (all 16
> sub-`0x0b` writes land on `0c03161e` by that route too).
>
> **The fix is therefore a one-line change in the fork**, not in this repo, and
> it is about the *trigger source*, not about adding another PC: tag the log
> line with which caller reached `maple_DoDma()` — `maple_SB_MDST_Write()`
> (attributable) versus `maple_vblank()` (not) — and re-capture. A boolean
> would do. Until then the input target rests on the sub `0x33` evidence above,
> which *is* a confirmed guest store — strong enough for Task 10 — and the
> EEPROM-write call site stays unknown.

### SP — two stacks, not one

672 logged SPs, in two disjoint clusters:

| Cluster | Samples | Range |
| --- | --- | --- |
| boot/init stack | 118 | `0x8c00e864`–`0x8c00ee38` |
| second stack | **554** | `0x8c1d4984` (one exact value, every time) |

The low cluster lands inside the statically derived stack region
`0x8c000000`–`0x8c00f000` and **confirms it**: the initial SP `0x8c00f000`
derived from the pointer indirection at `0x8c021104` is real, and the boot
stack is 0.5–1.9 KB deep at DMA time (`0x8c00f000` minus the cluster bounds).

The high cluster does not, and is not noise: 554 identical readings of
`0x8c1d4984`, ~1.8 MB above the boot stack and past the end of the loaded image
(`0x8c191ff8`), i.e. in memory the runtime allocated. senkosp is running a
multi-tasking runtime — `FUN_8c02532a` references the string
`"FATAL ERROR Cannot get semaph…"` on its failure path — and most cart DMA is kicked from a task
with its own stack, at a constant call depth.

> **Verdict: `sp_consistent` FAIL is a real finding, not a bad range.** The
> `0x8c000000`–`0x8c00f000` region is correct *and incomplete*: it describes
> the boot stack only. It is **not** widened here, because widening it to reach
> `0x8c1d4984` would falsely claim the game image at `0x8c020000`–`0x8c191ff8`
> is stack. Two disjoint regions is the truth, and only one of them is bounded:
> a single SP sample gives a task stack's *depth at that moment*, never its
> extent.
>
> **Task 10 must not treat anything around `0x8c1d4984` as free**, and bounding
> that stack needs its own measurement (an `r15` high/low-water probe), not
> another PC leg.

**Task 10 resolution — the second stack is static BSS, bounded without a
probe.** The system init `FUN_8c085b00` passes `[0x8c085bbc]` = `0x8c1cfb64`
plus `0x5000` = **`0x8c1d4b64`** as the stack-top argument to both the
machine bring-up (`jsr` at `0x8c085b36`, → `FUN_8c02c37c`) and the task setup
(`jsr` at `0x8c085b7a`, → `[0x8c071754](0x10, 0x8c1d4b64, 0)`); the 554-sample SP
cluster `0x8c1d4984` sits `0x1e0` below that top. `0x8c1cfb64` is inside the
statically-cleared BSS, which ends at `[0x8c15ae64]` = `0x8c1de200` — the
exact base the game's heap is created with (`docs/kb/relocation-map.md`
§Provenance). The free-space consequence: everything below `0x8c1de200` is
image/BSS (reserved wholesale), everything above is the heap — no separate
reservation window around `0x8c1d4984` is needed.

### `SOFWR` — Task 10 input, and its cap

1601 `SOFWR` lines, each carrying `val=`/`was=`/`pc=`/`pr=` — the framebuffer
placements that §MMIO xref sweep's `pvr_fb` = 0 verdict predicted the constant
scan would miss. Split: `FB_W_SOF1` 800, `FB_R_SOF1` 400, `FB_R_SOF2` 400,
`FB_W_SOF2` 1.

> **These totals are cap-saturated, not measurements.** `pvr_regs.cpp` stops
> logging at 800 lines per counter (`:242` shared by `FB_R_SOF1/2`, `:275`
> `FB_W_SOF1`, `:287` `FB_W_SOF2`). 400+400 and 800 are counters that hit their
> ceiling; only the `FB_W_SOF2` count of 1 is a true total. Task 10 may use the
> *addresses* freely but must not treat the *counts* as write frequencies.

The `pc`/`pr` pairs obey the same trigger split as everything else: the P1 site
`pc=8c032146` (`pr=8c037396`) is a genuine `mov.l r5,@r4`, and it sits beside
the PVR base pool word at `0x8c032160` that §MMIO xref sweep already identified
as the way to trace framebuffer placement. That is the site to start from.

### Loose ends, accounted for

- **`MIERESP` 86 222 vs `MAPLEPC` 86 219** — the 3-line difference is
  `handle_86_subcommand`'s early return when `dma_count_in == 0`, which replies
  without reaching the log call (`maple_jvs.cpp:1758-1765`).
- **All 86 219 `MAPLEPC` lines parse**; the per-`(sub, pc)` counts above sum to
  exactly 86 219. No truncated or interleaved lines anywhere in the log.
- **Ten `MAPLEPC` subcommands** appear (`0x01 0x03 0x0b 0x13 0x15 0x17 0x21
  0x27 0x31 0x33`), more than the `0x01`/`0x03`/`0x0b`/`0x15` set Phase 2
  recorded from `MIERESP`. The extra ones are ordinary MIE/JVS traffic, not a
  mystery, but they are recorded rather than dropped — Phase 2's
  `input-map.md` §Why no MIE sub=15 was written without sight of them, and
  `0x33` in particular turns out to be the one that matters.

### Check lines, verbatim

Run A — the ranges §Candidates proposed:

```
python3 scripts/parse_cartlog.py captures/phase3/pc.log \
    --cart-fn 8c0661e0-8c066560,8c0678c2-8c067e18 \
    --input-fn 8c0665fe-8c066b0f --eeprom-fn 8c0665fe-8c066b0f \
    --stack 8c000000-8c00f000 --pc-report          # exit=1
```

```
CHECK dest_known: PASS — every DMA dest in a known window (main/vram/aram/ta); 0 outside
CHECK len_aligned_32: PASS — every DMA len a whole number of 0x20-byte DMA_COUNT units
CHECK beyond_boot_read: PASS — at least one cart read past the 1 MB boot region (runtime streaming)
CHECK main_watermark_boot: PASS — main watermark 0x1ffffa5 >= boot-load end 0x191ff8
CHECK no_bios_exec: PASS — 0 BIOSEXEC lines (expect 0)
CHECK dma_pc_in_cart_fn: FAIL — 672 DMA-kick PCs vs cart fn
CHECK input_pc_in_input_fn: FAIL — 2876 sub=15 PCs vs input fn
CHECK eeprom_read_seen: FAIL — 16 sub=01/03 PCs vs eeprom fn
CHECK eeprom_write_seen: FAIL — 16 sub=0b PCs vs eeprom fn
CHECK sp_consistent: FAIL — 672 SPs vs static stack region
```

Run B — the reconciled ranges, and the run that produced `tools/pc-parse.txt`
(60 deduped `PCPAIR` lines, Task 10's input):

```
python3 scripts/parse_cartlog.py captures/phase3/pc.log \
    --cart-fn 8c027f54-8c027f99 \
    --input-fn 8c02532a-8c025505 --eeprom-fn 8c02532a-8c025505 \
    --stack 8c000000-8c00f000 --pc-report > tools/pc-parse.txt    # exit=1
```

```
CHECK dest_known: PASS — every DMA dest in a known window (main/vram/aram/ta); 0 outside
CHECK len_aligned_32: PASS — every DMA len a whole number of 0x20-byte DMA_COUNT units
CHECK beyond_boot_read: PASS — at least one cart read past the 1 MB boot region (runtime streaming)
CHECK main_watermark_boot: PASS — main watermark 0x1ffffa5 >= boot-load end 0x191ff8
CHECK no_bios_exec: PASS — 0 BIOSEXEC lines (expect 0)
CHECK dma_pc_in_cart_fn: PASS — 672 DMA-kick PCs vs cart fn
CHECK input_pc_in_input_fn: FAIL — 2876 sub=15 PCs vs input fn
CHECK eeprom_read_seen: FAIL — 16 sub=01/03 PCs vs eeprom fn
CHECK eeprom_write_seen: FAIL — 16 sub=0b PCs vs eeprom fn
CHECK sp_consistent: FAIL — 672 SPs vs static stack region
```

The four remaining `FAIL`s (`input_pc_in_input_fn`, `eeprom_read_seen`,
`eeprom_write_seen`, `sp_consistent`) are the two findings above — the
maple-trigger probe limitation, which accounts for three of them, and the
second stack, which accounts for the fourth — not unresolved range errors. Both need
work outside this repo (a fork probe change; an `r15` water-mark probe) before
a green line is honest. **`tools/pc-parse.txt` is left in place regardless: the
`PCPAIR` data it carries comes from the cart path, which is fully confirmed.**

### Reconciliation ledger

| Target | Static candidate | Dynamic result | Which side was wrong |
| --- | --- | --- | --- |
| cart-read fn | `0x8c0661e0-0x8c066560`, `0x8c0678c2-0x8c067e18` | **`FUN_8c027f54` `0x8c027f54`–`0x8c027f99`**, 672/672 kicks | static — register-programming layer mistaken for the trigger; base-pointer + 16-bit-offset blind spots |
| input fn | `0x8c0665fe-0x8c066b0f` | **`FUN_8c02532a` `0x8c02532a`–`0x8c025505`**, 80 392 sub `0x33` | *not* the wrong code — the candidate really does kick maple DMA (1035×, `MDODMA`), it is the **boot-time** driver. Wrong *phase*, and the check filters the boot-phase sub `0x15` instead of the per-frame sub `0x33` |
| EEPROM fn | `0x8c0665fe-0x8c066b0f` | reads share `FUN_8c02532a`; **write call site unknown** | neither — probe cannot see vblank-triggered transactions |
| SP | `0x8c000000-0x8c00f000` | boot stack confirmed (118 SPs); **second stack at `0x8c1d4984`** (554 SPs) | static — correct but incomplete; senkosp is multi-stack |
| BIOS call | no confirmed BIOS-code call | `no_bios_exec` PASS, 0 lines | agree — verdict closed for code |

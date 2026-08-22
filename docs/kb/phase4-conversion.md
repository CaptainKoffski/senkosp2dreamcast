# Phase 4 — conversion analysis results

Analysis results feeding the Phase 4 static-conversion patches (loader +
shim + patch table). Every bound below is cited to an instrumented-fork
line format, a capture leg, or an instruction/pool-word address in the boot
binary, per this project's citation rule (primary sources outrank wikis —
`CLAUDE.md`). Addresses are P1 (`0x8c…`) unless noted; phys = addr `&
0x1fffffff`; main offset = phys − `0x0c000000`.

Method and conventions are carried over from the Cleopatra port
(`../cleopatra/docs/kb/phase4-conversion.md`), cited section-by-section
below where reused verbatim.

---

## Shim home (V2s) — spec open pin O1

**Question (spec `2026-08-22-phase4-conversion-design.md` §RAM map, open
question O1; task brief
`.superpowers/sdd/2026-08-22-phase4-conversion/task-2-brief.md`):** Phase 4
places the freestanding shim at RAM `0x8c010000`–`0x8c018000` (32 KB,
`mem_b` offset `0x00010000`–`0x00017fff`). Does senkosp — boot, attract, a
played match, or the test menu — ever write into that window? If yes, the
shim home must move (fallback: heap-top carve + dry-run re-campaign, a spec
change).

This is senkosp's own window, distinct from Cleopatra's V2
(`../cleopatra/docs/kb/phase4-conversion.md` §V2 — shim-home write-watch,
`mem_b` `0x00fc0000`–`0x00ffffff`): senkosp's relocated heap now occupies
Cleopatra's old shim home (`docs/kb/relocation-map.md` §Provenance), so a
new window and a new watch were required. The method is the same V2
technique, applied to the new window (hence "V2s" — V2, senkosp).

### Step 1 — free pre-check from the existing RAM snapshot

Before any new capture, the Task 10b `tools/ram-snapshot.bin` (32 MB Naomi
main RAM, carved from a Flycast AutoSaveState after ~150 s of unattended
attract — `docs/kb/tooling.md` §Phase 3: RAM snapshot) was checked directly
for the window:

```
python3 - <<'EOF'
ram = open("tools/ram-snapshot.bin","rb").read()
window = ram[0x10000:0x18000]
nz = [(i+0x10000) for i,b in enumerate(window) if b]
print("non-zero bytes:", len(nz), "first:", [hex(a) for a in nz[:8]])
EOF
```

Result: **`non-zero bytes: 0`.** The window is already all-zero in a
snapshot taken after boot has fully completed and attract has been running
for ~150 s — no boot-time Naomi-BIOS artifact and no game-runtime write
had touched it as of that snapshot. No decode work was needed (the brief's
"decode what wrote them" branch does not apply). This is consistent with,
not a substitute for, the dynamic write-watch below — a snapshot is one
instant, not a scan across the whole run.

### Method

Instrumented Flycast (`../flycast4naomi2dreamcast` fork,
`core/hw/naomi/naomi.cpp` `cartlog_shimwatch2()`, commit `6e3522822`): a
**baseline-and-compare** content scan of `mem_b` offsets
`0x00010000`–`0x00017fff`, sampled at the same every-64th-cart-DMA /
~10 s cadence as `cartlog_shimwatch()` (Cleopatra's V2) and the `WATERMARK`
scan (both driven by `cartlog_sample()`). Baseline-and-compare, not
non-zero, because — unlike Cleopatra's shim home, which is genuinely never
written pre-handoff — the Naomi BIOS may legitimately write low RAM at
boot, and the DC loader replaces this window wholesale before the game
runs, so a boot-time write here is not evidence of anything the shim needs
to avoid. Only a byte that changes **after** the handoff baseline is
attributable to the running game.

The baseline reused is `cartlog_main_base` — the same whole-32 MB handoff
snapshot `cartlog_main_profile()` already diffs against (`naomi.cpp`,
Task 6-era instrumentation), taken at the first cart DMA / first 32 KB of
cumulative PIO reads (`cartlog_handoff()`). Both call paths into
`cartlog_sample()` are gated on that baseline being non-null, so the scan
cannot run before it exists — satisfying the brief's "snapshot the window
at the first sample" without a second private baseline buffer.

Line format: `SHIMWATCH2 addr=<hex P1> was=<hex byte> now=<hex byte>` for
every byte found to differ from baseline on a given sample (not just the
first one found — contrast Cleopatra's `SHIMWATCH`, which trips once and
stops).

**Content scan, not a write-intercept** — the arm64 dynarec's fast memory
path (`core/rec-ARM64/rec_arm64.cpp` `GenWriteMemoryFast`/
`GenWriteMemoryImmediate`) stores directly into host-mapped RAM whenever
`addrspace::virtmemEnabled()`, bypassing every C-level write function for
register-indirect stores — the common case for game code — so a hook on
`WriteMem`/`addrspace::write*` would silently miss most writes with the
dynarec on (V2's documented reason, reused verbatim here). Scanning actual
RAM content sees the result of a write regardless of which path produced
it (interpreter, dynarec fast/slow path, or cart DMA memcpy).

Parser check: `shim_home_clean` (`scripts/parse_cartlog.py`) — **PASS iff
zero `SHIMWATCH2` lines** across all parsed legs. Unconditional safety
tripwire, like `no_bios_exec` — runs on every parse, no CLI flag needed.

**Sampling caveat, verbatim from V2** (`../cleopatra/docs/kb/phase4-conversion.md`
§V2 — shim-home write-watch, `Verdict`):
> Sampling caveat: a write that was fully re-zeroed between two 64-DMA
> samples would evade the scan — same accepted trade-off as the WATERMARK
> scan.

The same limitation applies unchanged to `SHIMWATCH2`: it is a sampled
content scan, not a write trap, and a write into the window that is fully
reverted to its baseline value before the next sample is invisible to it.

### Capture — regime coverage

The brief's step 4 calls for three behaviorally distinct regimes: (a)
unattended boot → attract, (b) an operator-played match, (c) an operator
test-menu visit. (a) is unattended and was run in this task; (b) and (c)
require a human at the controls (this task cannot drive them — the
operator-leg rule, `.superpowers/sdd/2026-08-22-phase4-conversion/task-2-brief.md`).

`scripts/capture_leg.sh phase4/shimwatch` — dynarec **ON**
(`~/Library/Application Support/Flycast/emu.cfg` `Dynarec.Enabled = yes`,
verified before the leg — this is the point of running under dynarec: the
content scan proves itself under the same fast-path memory writes a
write-hook would miss, not just under the interpreter), ~660 s unattended
boot → attract, killed via `pkill -9 -f "flycast-src.*Flycast"`.

```
scripts/capture_leg.sh phase4/shimwatch & sleep 660; pkill -9 -f "flycast-src.*Flycast"
python3 scripts/parse_cartlog.py captures/phase4/shimwatch.log
```

**Result:** `captures/phase4/shimwatch.log`, 1,083,410 lines, 39 MB. 205
`CARTDMA` events, 69 `cartlog_sample()` ticks (one `WATERMARK region=main`
line per tick — `grep -c "^WATERMARK region=main"` — each tick also runs
`cartlog_shimwatch2()` once), **0 `SHIMWATCH2` lines**.

```
$ python3 scripts/parse_cartlog.py captures/phase4/shimwatch.log
...
CHECK dest_known: PASS — every DMA dest in a known window (main/vram/aram/ta); 0 outside
CHECK len_aligned_32: PASS — every DMA len a whole number of 0x20-byte DMA_COUNT units
CHECK beyond_boot_read: PASS — at least one cart read past the 1 MB boot region (runtime streaming)
CHECK main_watermark_boot: PASS — main watermark 0x1ffffa5 >= boot-load end 0x191ff8
CHECK no_bios_exec: PASS — 0 BIOSEXEC lines (expect 0)
CHECK shim_home_clean: PASS — 0 SHIMWATCH2 lines (expect 0)
```
exit=0.

### Verdict — **PARTIAL: CLEAN, attract regime only**

**Covered:** boot → attract (unattended, ~660 s, dynarec ON) —
`shim_home_clean: PASS`, zero `SHIMWATCH2` lines.

**Pending:** an operator-played full match and a test-menu visit — the
brief's `phase4/shimwatch-play` leg. Per the operator-leg rule, a human
must run this (this task cannot). Exact command:

```
scripts/capture_leg.sh phase4/shimwatch-play
# operator: play a full match, then visit the test menu, then quit
pkill -9 -f "flycast-src.*Flycast"
python3 scripts/parse_cartlog.py captures/phase4/shimwatch*.log
```

**Every later Phase 4 task assumes CLEAN.** The attract-only result gives
no positive evidence either way for match-play or test-menu code paths —
those are exactly the regimes most likely to touch heap-adjacent low RAM
differently from attract (e.g. EEPROM write-back, which Phase 3 found is
test-menu-only). The verdict upgrades from PARTIAL to full CLEAN once
`phase4/shimwatch-play` is captured and parsed clean; if it is not clean
and the write traces to a game-runtime structure, this section's verdict
flips to DIRTY and the fallback (heap-top carve + dry-run re-campaign) must
be raised to the user as a spec change before any later task proceeds.

### Reproduction

```
python3 scripts/parse_cartlog.py captures/phase4/shimwatch*.log   # -> CHECK shim_home_clean: PASS/FAIL
cd scripts && python3 test_parse_cartlog.py                        # -> ok
```

---

## Cart-patch sites — spec pins P1, P2, P3

**Question (spec `2026-08-22-phase4-conversion-design.md` §Cart-streaming
shim, plan pins P1/P2/P3; task brief
`.superpowers/sdd/2026-08-22-phase4-conversion/task-3-brief.md`):** which
exact `.dat` words must be rewritten, and which functions entry-hooked, so
that every cart/G1 MMIO access senkosp performs lands in the shim's RAM
mirror instead of the real Dreamcast G1 registers.

### Conventions used below

- **`dat_offset`** — byte offset in `senkosp.dat`. Main image: ROM `0x0` →
  RAM `0x8c020000`, `0x171ff8` B, so `dat_offset = addr − 0x8c020000`. Test
  image: ROM `0x171ff8` → RAM `0x8c020000`, `0x4dc40` B, so
  `dat_offset = 0x171ff8 + (addr − 0x8c020000)` (`docs/kb/game.md` §Parsed
  `.dat` header). Both images load at the same RAM base; only one is
  resident at a time.
- **`G1_MIRROR`** = `0x8c014800`, `0x800` bytes, faking physical
  `0x5f7000`–`0x5f77ff`; `G1_MIRROR_P2` = `0xac014800`
  (`docs/superpowers/plans/2026-08-22-phase4-conversion.md`, `shim_iface.h`
  draft `SHIM_BASE + 0x4800`). It sits inside the shim home
  `0x8c010000`–`0x8c018000` this doc's §Shim home found clean.
- **`new` values are symbolic**: every repoint below is
  `new = G1_MIRROR_P2 + (old & 0x7ff)`. Task 9 computes the literals from
  `shim_iface.h`; no numeric `new` is written here, so the two can never
  drift.
- Every `old` value in every table was read byte-for-byte out of
  `senkosp.dat` at the stated `dat_offset` by the generator quoted under
  §Reproduction — not copied from a decompiler listing.

### Method, and the completeness bar

Three independent sweeps, because each has a known blind spot
(`docs/kb/boot-binary.md` §Coverage limits of this scan):

1. **Raw word scan** of both load entries for `(word & 0x1fffffff)` in
   `0x5f7000`–`0x5f77ff` — catches pool literals Ghidra never promoted to
   defined data. **32 words in the main image, 32 in the test image.**
2. **Raw pc-relative-loader scan** — decodes every `mov.l @(d,PC),Rn`
   (`0xDnnn`) and `mov.w @(d,PC),Rn` (`0x9nnn`) in the image and resolves its
   pool address, giving each pool word its loader instruction without
   depending on Ghidra's function recovery. 28 of the 32 main-image words
   have at least one loader; the remaining 4 are data-table entries (below).
3. **Ghidra** (`ListPoolWords.java 0x005f7000 0x005f7800`, `Decomp.java`,
   `DisasmRange.java … force`) for the semantics — what each site does.

Sweep 1 is a strict superset of `tools/mmio-xrefs.txt` for this block:
`FindMmioXrefs` reports 13 `cart`+`g1dma` hits inside the mirror range
(`mmio-xrefs.txt:53,58-65,70,77-79`), all 13 appear in the table below, and
the raw scan adds 19 more that sat in Ghidra-undefined spans. **Accounting
closes at 32 = 29 repointed + 3 exempted**, and the base repoint (entry 1)
additionally carries every base-relative access in the steady path, which
uses no whole-address constant at all.

### CART-BASE — one word carries the entire steady path

Phase 3 confirmed the live cart DMA kick is `0x8c027f72`, reached as
`obj->[0x58] + 0x418` (`docs/kb/boot-binary.md` §Target: cart-read function),
and left the provenance of `obj->[0x58]` as "inferred from the constant, not
yet traced call by call". It is now traced, and it resolves to **one word**.

```
// FUN_8c02751a @8c02751a  body 8c02751a..8c02751f   (Decomp.java)
undefined4 FUN_8c02751a(void) { return DAT_8c0275e8; }        ; DAT_8c0275e8 = 0xa05f7000
```

`FUN_8c02751a` has exactly one caller, and that caller stores its result into
the struct field the whole cart path dereferences — verbatim
`DisasmRange.java 0x8c027894 0x8c0278d8`:

```
8c0278a0  bsr 0x8c02751a           ; r0 = 0xa05f7000
8c0278a2  _mov.l r13,@(0x14,r14)
8c0278a4  mov #0x58,r1
8c0278a6  mov.w 0x8c027972,r3      ; (unrelated: r3/r2 preloaded for 8c0278d6)
8c0278a8  add r14,r1               ; r1 = obj + 0x58
8c0278aa  mov.w 0x8c027974,r2      ; (unrelated, same)
8c0278ac  mov.l r0,@r1             ; obj->[0x58] = 0xa05f7000   <== THE BASE STORE
```

(`Decomp.java 0x8c027894` renders the same store as `piVar3[0x16] = iVar4`,
`0x16 * 4 = 0x58`.) The constant enters the program exactly once: the raw
scan finds `0xa05f7000` at three addresses in the main image, and the other
two (`0x8c06642c`, `0x8c06653c`) are absolute pools of the boot driver, which
has its own entries below.

Every steady-path register is then *base + a 16-bit `mov.w` pool word*. All
of them, byte-verified from the image, with the function that uses them:

| Function | Displacement pool words (u16) | Registers reached |
| --- | --- | --- |
| `FUN_8c027a66` (`8c027a66`–`8c027b5d`) — read request | `8c027bd0`=`0x04b8`, `8c027bd2`=`0x0404`, `8c027bd4`=`0x0408`, `8c027bd6`=`0x040c`; plus literal `+0x00`/`+0x0c`/`+0x10` | `SB_GDAPRO`, `SB_GDSTAR`, `SB_GDLEN`, `SB_GDDIR`, `NAOMI_ROM_OFFSETH`, `NAOMI_DMA_OFFSETH/L` |
| `FUN_8c027d7e` (`8c027d7e`–`8c027dfd`) — re-arm | `8c027e04`=`0x04b8`, `8c027e06`=`0x0404`, `8c027e08`=`0x0408`, `8c027e0a`=`0x040c`, `8c027e0c`=`0x0414`; `+0x40c+0xc` = `0x418` | same, plus `SB_GDEN`, `SB_GDST` |
| `FUN_8c027f54` (`8c027f54`–`8c027f99`) — kick | `8c028014`=`0x0414`, `8c028016`=`0x0418` | `SB_GDEN`, `SB_GDST` |
| `FUN_8c027e5e` (`8c027e5e`–`8c027ebf`) — wait | `8c027f42`=`0x0418`, `8c027f46`=`0x04f8` | `SB_GDST`, `SB_GDLEND` |
| `FUN_8c027e34` (`8c027e34`–`8c027e5d`) — settle | `8c027f42`=`0x0418`, `8c027f44`=`0x0414` | `SB_GDST`, `SB_GDEN` |
| `FUN_8c027f9a` (`8c027f9a`–`8c027fe3`) — drain | `8c028018`=`0x04f8` | `SB_GDLEND` |
| `FUN_8c027fe4` (`8c027fe4`–`8c028013`) — PIO/DMA bus timing | `8c02801c`=`0x0490`, `8c02801e`=`0x0494`, both `+0x10`; `8c028024`=`0xa000` written to `+0x00` | `SB_G1CRC`, `SB_G1CWC`, `SB_G1GDRC`, `SB_G1GDWC`, `NAOMI_ROM_OFFSETH` |

Largest displacement in use is `0x4f8`, so the `0x800`-byte mirror covers all
of them.

> **CART-BASE verdict — 1 patch entry.**
> `pool(dat_offset=0x0075e8, old=0xa05f7000, new=G1_MIRROR_P2 + 0x000)`
> (main image; test image `0x1795e0`, same value, same instruction — see
> §Test image). This is senkosp's analog of Cleopatra's `0x8c02da74`. No
> displacement word needs patching: they are 16-bit `mov.w` literals and stay
> correct against any base.

### CART-WAIT — four entry hooks and one invariant

The steady path never polls `SB_GDST` inline; it delegates to two small
functions, both base-relative and therefore already inside the mirror after
the CART-BASE repoint. Both were decompiled (`Decomp.java 0x8c027e5e
0x8c027e34`):

```c
// FUN_8c027e5e @8c027e5e — "wait until this DMA is done"; r4 = snapshot flag, r5 = obj
do {
  if (obj->[0x70] != 0) { obj->[0x60] = 0; return; }      ; error/abort latch
  obj->[0x60] = 1;
  (*(code *)PTR_FUN_8c027f4c)(0x8c193f60);                 ; yield  (PTR = 0x8c06541c)
  if ((*(uint *)(obj->[0x58] + 0x0418) & 1) == 0) {        ; SB_GDST bit 0 clear -> done
    if (r4) obj->[0x5c] = *(obj->[0x58] + 0x04f8);         ; SB_GDLEND -> progress
    obj->[0x60] = 0; return;
  }
  if (r4) obj->[0x5c] = *(obj->[0x58] + 0x04f8);
} while (true);

// FUN_8c027e34 @8c027e34 — "settle/abort the current DMA"; r4 = obj
if (*(obj->[0x58] + 0x0418) == 1) {                        ; SB_GDST
  *(obj->[0x58] + 0x0414) = 0;                             ; SB_GDEN = 0
  do { } while ((*(obj->[0x58] + 0x0418) & 1) != 0);       ; spin until GDST clears
}
obj->[0x7c] = 0;
```

`FUN_8c027e5e` is the smallest function whose whole contract is "wait until
this DMA is done", and it is reached from **both** kick paths — directly from
the confirmed kick `FUN_8c027f54` (`8c027f74 bsr 0x8c027e5e`) and from the
streaming drain loop `FUN_8c027f9a` (`do { FUN_8c027e5e(1, obj); } while (0 <
obj->[0x74]);`), which is what waits for the `FUN_8c027d7e` re-arm chain. It is the
V3-equivalent (Cleopatra hooked `FUN_8c03bc12`,
`../cleopatra/docs/kb/phase4-conversion.md` §V3).

Everything the service routine needs is already in the mirror when the hook
fires: `SB_GDSTAR` (dest), `SB_GDLEN` (bytes), `SB_GDDIR`, and the cart-side
source in `NAOMI_DMA_OFFSETH/L` — all written before the kick by
`FUN_8c027a66` / `FUN_8c027d7e`.

> **The mirror invariant.** `mirror[0x418]` (`SB_GDST`) **must read 0 whenever
> no DMA is outstanding.** Nothing traps a store to RAM, so any spin waiting
> for a mirrored `SB_GDST` to clear is unbreakable unless a hook clears it.
> The invariant is what makes every remaining `SB_GDST` spin in the image
> (the boot wrappers below, and `FUN_8c027e34`'s inner loop) fall through
> with no patch of its own.

Four entry hooks, and why each is needed:

| Hook | `dat_offset` (main / test) | Function | Contract | Why |
| --- | --- | --- | --- | --- |
| **CART-WAIT-A** | `0x007e5e` / `0x179e56` | `FUN_8c027e5e` | wait for DMA completion | the steady-path completion wait; where the service runs |
| **CART-WAIT-B** | `0x007e34` / `0x179e2c` | `FUN_8c027e34` | settle/abort | `FUN_8c027d7e` kicks and returns without waiting; if this runs first its inner `while (GDST & 1)` spins on RAM forever |
| **CART-BOOT-DMA** | `0x046440` / `0x1a2c6c` | boot cart DMA (below) | blocking cart read | it sets *and then polls* the mirrored `SB_GDST` itself |
| **CART-PIO-READ** | `0x0463e6` / `0x1a2c12` | boot PIO reader (see CART-PIO) | half-word cart read loop | it *loads* from `mirror[0x008]` expecting hardware auto-increment; a RAM mirror returns the same word every iteration |

A single shim helper (`shim_cart_service` per the spec) satisfies the first
three: service whatever the mirror describes, then clear `mirror[0x418]`.
CART-WAIT-B and CART-BOOT-DMA degenerate to "nothing pending → return".
CART-PIO-READ needs a second, smaller helper — it is a byte-range copy with
no DMA state at all (ABI under §CART-PIO).

CART-WAIT-B's premise is hardware behaviour, not inference: clearing `SB_GDEN`
while a transfer is running clears `SB_GDST` on the real part, which is what
its `GDEN = 0` then `while (GDST & 1)` sequence is written against
(`Naomi_DmaEnable`, `../flycast4naomi2dreamcast/core/hw/naomi/naomi.cpp:533-542`
— `if (SB_GDEN == 0 && SB_GDST == 1) { SB_GDST = 0; … }`; registered at
`naomi.cpp:588`). In the mirror that write does nothing, hence the hook.

**Boot-path `SB_GDST` spinners — no hook, covered by the invariant.** Five
recovered functions spin `do { } while (*(u32*)0xa05f7418 != 0)` through an
absolute pool: `FUN_8c0678c2` and `FUN_8c06773a` (pool `0x8c067970`),
`FUN_8c0679b4` and `FUN_8c0679d2` (pool `0x8c067adc`), `FUN_8c067b48` (pool
`0x8c067c44`), plus one loader in an unrecovered span at `0x8c067db2` (pool
`0x8c067e14`). Every one of those pools is repointed (entries 24/25/27/28),
so they read `mirror[0x418]` = 0 and fall straight through. `FUN_8c066396`
(pool `0x8c066424`) and `FUN_8c0664b4` (pool `0x8c066530`) are single reads,
not spins, and behave the same way.

### CART-PIO — the ABI, and a correction to the brief's naming

`FUN_8c027d7e` is **not** a PIO path. Decompiled and disassembled
(`Decomp.java 0x8c027d7e`, `DisasmRange.java 0x8c027d7e 0x8c027e00`) it is a
second **DMA arm + kick**, reusing the cart-side source pointer the hardware
auto-advanced, and it drives the same base-relative registers as
`FUN_8c027a66`:

Abridged — every `base + disp` store is preceded by a `mov #0x58,r0` /
`mov.l @(r0,r14),rN` reload of the base out of the struct, elided below except
where it carries an annotation; `…` marks each cut:

```
8c027d86  mov #0x74,r0 ; 8c027d8c mov.l @(r0,r14),r2 ; 8c027d8e mov.l @(0x4,r13),r3
8c027d90  cmp/hs r3,r2 ; bf 8c027d9e                   ; fail if obj->[0x74] < desc[1]
   …
8c027da4  mov.w 0x8c027e04,r3   ; +0x4b8  SB_GDAPRO  <- 0x8843407f (pool 0x8c027e30)
8c027db0  mov.w 0x8c027e06,r2   ; +0x404  SB_GDSTAR  <- desc[0]   (mov.l @r13,r3)
8c027dba  mov.w 0x8c027e08,r3   ; +0x408  SB_GDLEN   <- desc[1]   (mov.l @(0x4,r13),r2)
8c027dc8  mov.w 0x8c027e0a,r2   ; r2 = 0x040c
8c027dcc  mov.l r4,@r1          ; +0x40c  SB_GDDIR   <- 1  (r4 = 1, set at 8c027dc6)
8c027dd6  mov.w 0x8c027e0c,r3   ; r3 = 0x0414
8c027dd8  mov.l r1,@(r0,r14)    ;         obj->[0x74] -= desc[1]   (r0 still 0x74)
8c027dda  mov #0x58,r0
8c027ddc  mov.l @(r0,r14),r0    ; r0 = base
8c027dde  add r3,r0             ; r0 = base + 0x414
8c027de0  mov.l r4,@r0          ; +0x414  SB_GDEN    <- 1
8c027de2  mov #0x58,r0
8c027de4  mov.l @(r0,r14),r1    ; r1 = base
8c027de6  add #0xc,r2           ; r2 = 0x040c + 0xc = 0x0418
8c027de8  add r2,r1             ; r1 = base + 0x418
8c027dea  mov.l r4,@r1          ; +0x418  SB_GDST    <- 1          <== second kick site
```

> **`FUN_8c027d7e` ABI (CART-PIO anchor, renamed CART-DMA-REARM).**
> `int FUN_8c027d7e(u32 *desc /*r4*/, obj *o /*r5*/)`; `desc[0]` = destination
> address (→ `SB_GDSTAR`), `desc[1]` = byte length (→ `SB_GDLEN`); reads and
> decrements `o->[0x74]` (bytes still owed on the current stream); returns `0`
> on success, `0xffffffff` if `o->[0x74] < desc[1]` or the callback at pool
> `0x8c027e2c` (= `0x8c029238`) fails. It does **not** wait — the wait is
> `FUN_8c027f9a`'s `FUN_8c027e5e` loop. **No patch entry of its own:** every
> register it touches is `o->[0x58] + disp16`, i.e. covered by CART-BASE. Its
> kick at `+0x418` explains why CART-WAIT-B is needed.

**The actual PIO reader is in the boot driver**, and it is the only code in
either image that touches `NAOMI_ROM_DATA`. Verbatim `DisasmRange.java
0x8c0663e6 0x8c066418 force`:

```
8c0663e6  mov.l 0x8c066430,r2   ; r2 = 0xa05f7004  NAOMI_ROM_OFFSETL
8c0663e8  extu.w r4,r3
8c0663ea  mov.l r3,@r2          ; <- offset & 0xffff
   …      (8c0663ec-8c0663fc: load 0x8c066428/0x8c066434/0x8c066438,
   …       r0 = *(u32 *)0x8c1bf18c, and/shlr16/or — see the note below)
8c0663f8  mov.l 0x8c06642c,r3   ; r3 = 0xa05f7000  NAOMI_ROM_OFFSETH
8c0663fe  mov.l r4,@r3          ; <- ((offset & 0xffff0000) >> 16)
                                ;    | *(u32 *)0x8c1bf18c | 0x00008000
8c066400  mov.l 0x8c06643c,r4   ; r4 = 0xa05f7008  NAOMI_ROM_DATA
8c066402  bra 0x8c06640c
8c066404  _shlr r6              ; r6 = byte count >> 1 = half-word count
8c066406  mov.l @r4,r2          ; <== the PIO read (auto-increment on hardware)
8c066408  mov.w r2,@r5          ; store 16 bits
8c06640a  add #0x2,r5
8c06640c  tst r6,r6
8c06640e  bf/s 0x8c066406
8c066410  _add #-0x1,r6
8c066412  rts
8c066414  _nop
```

(mask `0xffff0000` = pool `0x8c066434`, mode bit `0x00008000` = pool
`0x8c066438`, base pointer `0x8c1bf18c` = pool `0x8c066428`; all four
byte-verified. Bit `0x8000` in `NAOMI_ROM_OFFSETH` is exactly flycast's
`RomPioAutoIncrement = (data & 0x8000) != 0`,
`../flycast4naomi2dreamcast/core/hw/naomi/naomi_cart.cpp:1010` — the loop
depends on the hardware advancing `RomPioOffset` by 2 per read, `:1026`.)

> **CART-PIO disposition — repoint + a registered hook, because the repoint
> alone is not a service.** Entries 11/12/13 keep the writes off the real
> Dreamcast G1 bus, but `8c066406 mov.l @r4,r2` is a plain **load** from
> `mirror[0x008]`, and nothing traps a load from RAM any more than it traps a
> store (the same reasoning as the mirror invariant above). With no hook the
> loop returns the same stale word `r6/2` times. So the entry hook is named
> here rather than left implicit:
>
> | Hook | `dat_offset` (main / test) | entry | ABI |
> | --- | --- | --- | --- |
> | **CART-PIO-READ** | `0x0463e6` / `0x1a2c12` | `0x8c0663e6` / `0x8c050c1a` | `void pio_read(u32 rom_off /*r4*/, void *dest /*r5*/, u32 len_bytes /*r6*/)` — leaf, no prologue, no return value |
>
> Entry bounds byte-verified: the preceding word pair is `rts`/`nop`
> (`0x0463e2` = `000b`, `0x0463e4` = `0009`) and the body ends `8c066412 rts`
> / `8c066414 nop`. The test image's copy is byte-identical over
> `0x8c050c1a`–`0x8c050c49` and its own entry is likewise preceded by
> `000b`/`0009` at `0x1a2c0e`/`0x1a2c10`.

**Is this path live?** Static answer: **no caller reaches it.** No `bsr`/`bra`
anywhere in either image targets `0x8c0663e6` (or the test image's
`0x8c050c1a`), and no 32-bit word anywhere in either image holds that address,
so it cannot be entered except through the computed-target hole
`docs/kb/boot-binary.md` §BIOS-call verdict already discloses. Contrast its
neighbours in the same block, which do have callers: the boot cart DMA routine
`0x8c066440` (`bsr` at `0x8c0665b4`, `0x8c0665ca`) and `FUN_8c0664b4`
(`bsr` at `0x8c06614a`, plus pool words `0x8c071510`, `0x8c07174c`).

**The "2 PIO seeks" do not settle it either way.** The fork emits `CARTPIO` on
the **`NAOMI_ROM_OFFSETL` write**, not on a `NAOMI_ROM_DATA` read
(`.../core/hw/naomi/naomi_cart.cpp:1020`), so the count in
`docs/kb/cart-streaming-map.md:12`, `:78` cannot distinguish this reader
(`8c0663ea`) from the boot DMA routine's own `NAOMI_ROM_OFFSETL <- 0`
(`8c066458`) — nor from the **Naomi BIOS**, which PIO-loads the image before
any game code runs and dominates the byte counter: `CARTPIOCNT` = `0x172538`
on a typical boot (`docs/kb/phase2-measurements.md:46`) against a main image
of `0x171ff8`. Given Phase 3 logged **zero** DMA kicks at `0x8c06649e`, the
whole `0x8c066xxx` boot driver most likely did not run in any captured leg,
and the two seeks are the BIOS's.

**Net:** treat CART-PIO-READ exactly like CART-BOOT-DMA — a hook that is
expected never to fire, kept because the failure mode if it does fire is
silent data corruption (a buffer filled with one repeated half-word) rather
than a visible hang. Task 10 may implement all four hooks with one helper.

### CART-BOOT-POOLS — the boot cart driver

The `0x8c066xxx` block reaches its registers by absolute pool, so every word
is its own patch entry. Two functions matter beyond the PIO reader:

**The boot cart DMA routine, entry `0x8c066440`** (prologue byte-verified:
`0x046440` = `2fe6` `mov.l r14,@-r15`, `0x046442` = `7ffc` `add #-0x4,r15`;
body ends `8c0664b0 rts` / `8c0664b2 mov.l @r15+,r14`). Verbatim
`DisasmRange.java 0x8c066444 0x8c0664b4 force`:

```
8c066444  tst r6,r6 ; bt/s 8c0664ae      ; len == 0 -> return
8c06644a  _and r2,r4                     ; offset &= ~0x1f
8c06644c  mov.l 0x8c066530,r14           ; SB_GDST
8c06644e  do { r3 = *r14 } while (r3)    ; wait for idle
8c066454  0x8c066534 (NAOMI_ROM_OFFSETL) <- 0
8c06645c  0x8c06653c (NAOMI_ROM_OFFSETH) <- *(u32 *)0x8c1bf18c   (ptr pool 0x8c066538)
8c066466  0x8c066540 (NAOMI_DMA_COUNT)   <- r6 >> 5
8c06646e  0x8c066544 (NAOMI_DMA_OFFSETL) <- r4 & 0xffff
8c066480  0x8c066550 (NAOMI_DMA_OFFSETH) <- ((r4 & 0xffff0000) >> 16)
                                            | *(u32 *)0x8c1bf18c | 0x0000a000
8c066488  0x8c066554 (SB_GDSTAR)         <- r5
8c06648c  0x8c066558 (SB_GDLEN)          <- r6
8c066490  0x8c06655c (SB_GDDIR)          <- 1
8c066496  add #0x10,r2 ; mov.l r4,@r2    ; SB_GDEN  <- 1
                                         ;   r2 still = SB_GDSTAR pool value,
                                         ;   0x5f7404 + 0x10 = 0x5f7414
8c06649a  tst r7,r7 ; bf/s 8c0664ae
8c06649e  _mov.l r4,@r14                 ; SB_GDST <- 1   <== boot DMA kick
8c0664a0  do { r3 = *r14 } while (r3)    ; blocking wait (only when r7 == 0)
8c0664a8  0x8c066550 (NAOMI_DMA_OFFSETH) <- [0x8c066560] = 0x0000c000
```

> **ABI:** `void boot_cart_dma(u32 rom_off /*r4, rounded down to 0x20*/,
> void *dest /*r5*/, u32 len /*r6*/, int async /*r7*/)`. `r7 != 0` kicks and
> returns; `r7 == 0` kicks and blocks. **This is the CART-BOOT-DMA hook site**
> — after the repoint, the wait at `8c0664a0` and the idle wait at `8c06644e`
> both read RAM, so without a hook the first synchronous call hangs and every
> asynchronous call leaves `mirror[0x418]` stuck at 1, breaking the invariant
> for everyone else. It was **not observed executing** in any Phase 3 capture
> leg (all 672 logged kicks are `0x8c027f72` — `docs/kb/boot-binary.md`
> §Target: cart-read function; zero at `0x8c06649e`), so the hook is insurance,
> not a hot path. Unlike the PIO reader it is genuinely reachable — two `bsr`
> callers, `0x8c0665b4` and `0x8c0665ca` — so "not observed" is a statement
> about the captured regimes (unattended attract, played match, test menu),
> not about the code being dead.

**`FUN_8c0664b4`** (`Decomp.java`) — `if (*SB_GDST != 0) return 0;
*NAOMI_DMA_OFFSETH = 0x0000c000; return 1;` (`DAT_8c066560` byte-verified =
`0x0000c000`). Read-only on `SB_GDST`; covered by the invariant.

**Two non-obvious entries.** `0x8c066274` = `0xa05f703c` is
`NAOMI_DIMM_COMMAND` (`../flycast4naomi2dreamcast/core/hw/naomi/naomi_regs.h:22`),
read as a half-word at `8c0661f6 mov.w @r2,r3` in the board-probe function
at `0x8c0661e0`; `0x8c067b00` = `0xa05f7068` is `NAOMI_LED`
(`naomi_regs.h:28`), loaded at `8c067a00`. Both sit inside the mirror's
`0x800` span, both are repointed with everything else — a DIMM probe reading
mirror zero is the correct answer for a cartridge board, and an LED write to
RAM is a no-op.

### G1-TIMING — `FUN_8c066288`

`FUN_8c066288` (`0x8c066288`–`0x8c066395`) programs the G1 bus timing from a
clock parameter, through **five** absolute pool words plus pointer arithmetic
off them (`Decomp.java 0x8c066288`):

| Pool | Value | Reached as | Register |
| --- | --- | --- | --- |
| `0x8c066368` | `0xa05f74b8` | `*p` | `SB_GDAPRO` (`<- 0x8843007f`, `DAT_8c066364`) |
| `0x8c066368` | `0xa05f74b8` | `p[-0xc]` = `−0x30` | `SB_G1FRC` (`0x5f7488`) |
| `0x8c066368` | `0xa05f74b8` | `p[-9]` = `−0x24` | `SB_G1CWC` (`0x5f7494`) |
| `0x8c06636c` | `0xa05f7480` | `*p`, `p[3]` | `SB_G1RRC`, `SB_G1FWC` (`0x5f748c`) |
| `0x8c066370` | `0xa05f7484` | `*p` | `SB_G1RWC` |
| `0x8c066374` | `0xa05f7490` | `*p`, `p+4` | `SB_G1CRC`, `SB_G1GDRC` (`0x5f74a0`) |
| `0x8c066378` | `0xa05f74a4` | `*p` | `SB_G1GDWC` |

Nine registers, five patch entries (5–9). The `±` arithmetic survives the
repoint unchanged — the reached offsets span `0x480` (`SB_G1RRC`) to `0x4b8`
(`SB_GDAPRO`), all inside the `0x800` mirror — so no additional word is
touched. `FUN_8c027fe4`
programs the same `SB_G1CRC`/`CWC`/`GDRC`/`GDWC` group from the steady path
and needs no entry: it is base-relative (see CART-BASE).

### The full patch table — main image

Anchor column: `CART-BASE`, `CART-PIO`, `G1-TIMING`, `BOOT-POOLS`,
`CART-WAIT` (pool words the wait/spin sites read), `*exempt*`. Every row is
`pool(dat_offset, old, new = G1_MIRROR_P2 + (old & 0x7ff))` unless exempted.

| # | `dat_offset` | RAM addr | old u32 | register | anchor | loader instruction(s) |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `0x0075e8` | `8c0275e8` | `0xa05f7000` | `NAOMI_ROM_OFFSETH` | CART-BASE | `8c02751a` `mov.l @(0x33,PC),r0` |
| 2 | `0x04626c` | `8c06626c` | `0xa05f7418` | `SB_GDST` | BOOT-POOLS | `8c0661e4` `mov.l @(0x21,PC),r2` |
| 3 | `0x046274` | `8c066274` | `0xa05f703c` | `NAOMI_DIMM_COMMAND` | BOOT-POOLS | `8c0661f0` `mov.l @(0x20,PC),r2` |
| 4 | `0x04627c` | `8c06627c` | `0xa05f7014` | `NAOMI_DMA_COUNT` | BOOT-POOLS | `8c06623c` `mov.l @(0x0f,PC),r1` |
| 5 | `0x046368` | `8c066368` | `0xa05f74b8` | `SB_GDAPRO` | G1-TIMING | `8c066288` `mov.l @(0x37,PC),r2` |
| 6 | `0x04636c` | `8c06636c` | `0xa05f7480` | `SB_G1RRC` | G1-TIMING | `8c06628e` `mov.l @(0x37,PC),r3` |
| 7 | `0x046370` | `8c066370` | `0xa05f7484` | `SB_G1RWC` | G1-TIMING | `8c066294` `mov.l @(0x36,PC),r1` |
| 8 | `0x046374` | `8c066374` | `0xa05f7490` | `SB_G1CRC` | G1-TIMING | `8c0662a2` `mov.l @(0x34,PC),r7` |
| 9 | `0x046378` | `8c066378` | `0xa05f74a4` | `SB_G1GDWC` | G1-TIMING | `8c0662a6` `mov.l @(0x34,PC),r5` |
| 10 | `0x046424` | `8c066424` | `0xa05f7418` | `SB_GDST` | BOOT-POOLS | `8c066396` `mov.l @(0x23,PC),r2` |
| 11 | `0x04642c` | `8c06642c` | `0xa05f7000` | `NAOMI_ROM_OFFSETH` | CART-PIO | `8c0663da` `mov.l @(0x14,PC),r2`, `8c0663f8` `mov.l @(0x0c,PC),r3` |
| 12 | `0x046430` | `8c066430` | `0xa05f7004` | `NAOMI_ROM_OFFSETL` | CART-PIO | `8c0663e6` `mov.l @(0x12,PC),r2` |
| 13 | `0x04643c` | `8c06643c` | `0xa05f7008` | `NAOMI_ROM_DATA` | CART-PIO | `8c066400` `mov.l @(0x0e,PC),r4` |
| 14 | `0x046530` | `8c066530` | `0xa05f7418` | `SB_GDST` | BOOT-POOLS | `8c06644c` `mov.l @(0x38,PC),r14`, `8c0664b4` `mov.l @(0x1e,PC),r0` |
| 15 | `0x046534` | `8c066534` | `0xa05f7004` | `NAOMI_ROM_OFFSETL` | BOOT-POOLS | `8c066454` `mov.l @(0x37,PC),r2` |
| 16 | `0x04653c` | `8c06653c` | `0xa05f7000` | `NAOMI_ROM_OFFSETH` | BOOT-POOLS | `8c06645c` `mov.l @(0x37,PC),r3` |
| 17 | `0x046540` | `8c066540` | `0xa05f7014` | `NAOMI_DMA_COUNT` | BOOT-POOLS | `8c066466` `mov.l @(0x36,PC),r1` |
| 18 | `0x046544` | `8c066544` | `0xa05f7010` | `NAOMI_DMA_OFFSETL` | BOOT-POOLS | `8c06646e` `mov.l @(0x35,PC),r2` |
| 19 | `0x046550` | `8c066550` | `0xa05f700c` | `NAOMI_DMA_OFFSETH` | BOOT-POOLS | `8c066480` `mov.l @(0x33,PC),r3`, `8c0664a8` `mov.l @(0x29,PC),r2`, `8c0664c0` `mov.l @(0x23,PC),r2` |
| 20 | `0x046554` | `8c066554` | `0xa05f7404` | `SB_GDSTAR` | BOOT-POOLS | `8c066488` `mov.l @(0x32,PC),r2` |
| 21 | `0x046558` | `8c066558` | `0xa05f7408` | `SB_GDLEN` | BOOT-POOLS | `8c06648c` `mov.l @(0x32,PC),r3` |
| 22 | `0x04655c` | `8c06655c` | `0xa05f740c` | `SB_GDDIR` | BOOT-POOLS | `8c066490` `mov.l @(0x32,PC),r1` |
| 23 | `0x046a88` | `8c066a88` | `0xa05f700c` | `NAOMI_DMA_OFFSETH` | BOOT-POOLS | `8c066988` `mov.l @(0x3f,PC),r0` |
| 24 | `0x047970` | `8c067970` | `0xa05f7418` | `SB_GDST` | CART-WAIT | `8c0677dc` `mov.l @(0x64,PC),r4`, `8c0678a0` `mov.l @(0x33,PC),r5`, `8c0678c4` `mov.l @(0x2a,PC),r4`, `8c0678f0` `mov.l @(0x1f,PC),r4` |
| 25 | `0x047adc` | `8c067adc` | `0xa05f7418` | `SB_GDST` | CART-WAIT | `8c0679b8` `mov.l @(0x48,PC),r4`, `8c0679d2` `mov.l @(0x42,PC),r4` |
| 26 | `0x047b00` | `8c067b00` | `0xa05f7068` | `NAOMI_LED` | BOOT-POOLS | `8c067a00` `mov.l @(0x3f,PC),r3` |
| 27 | `0x047c44` | `8c067c44` | `0xa05f7418` | `SB_GDST` | CART-WAIT | `8c067bf8` `mov.l @(0x12,PC),r4` |
| 28 | `0x047e14` | `8c067e14` | `0xa05f7418` | `SB_GDST` | CART-WAIT | `8c067db2` `mov.l @(0x18,PC),r2` |
| 29 | `0x13c650` | `8c15c650` | `0xa05f7418` | `SB_GDST` | BOOT-POOLS | — (data-table entry, no pc-relative loader) |
| 30 | `0x13c718` | `8c15c718` | `0xa05f7404` | `SB_GDSTAR` | *exempt* | — (data-table entry, no pc-relative loader) |
| 31 | `0x13c71c` | `8c15c71c` | `0xa05f7408` | `SB_GDLEN` | *exempt* | — (data-table entry, no pc-relative loader) |
| 32 | `0x13c720` | `8c15c720` | `0xa05f740c` | `SB_GDDIR` | *exempt* | — (data-table entry, no pc-relative loader) |

**The four data-table words (29–32).** They have no pc-relative loader
because they are table entries, not code pools — the two tables of
`docs/kb/boot-binary.md` blind spot (3):

- Entry 29 lives in the `(register, value)` init-pair list based at
  `0x8c15c3e8` (pointer pool `0x8c02c5e8`), whose walker is
  `FUN_8c02c584` — `for (p = table; *p != 0; p += 2) *(int *)p[0] = p[1];`
  (`Decomp.java 0x8c02c584`). Its paired value word `0x8c15c654` is `0`, so
  the boot path **writes `SB_GDST = 0`**. Repointed: it becomes a free
  zero-init of `mirror[0x418]`, which is exactly the invariant's initial
  state. It is the only cart/G1 address in that whole table.
- Entries 30–32 live in the flat register-address list based at
  `0x8c15c6c0` (pointer pool `0x8c02c884`), which is inside `FUN_8c02c5ec`,
  the serial **crash dump** — the "0x45-entry table" of
  `docs/kb/boot-binary.md` §RTC / SCIF / watchdog, reachable only from an
  exception-vector stub (callers `0x8c02c8f2`, `0x8c02c9a4`, neither inside a
  recognised function).

> **Exemption (3 words, entries 30–32).** `0x13c718` / `0x13c71c` / `0x13c720`
> — `SB_GDSTAR` / `SB_GDLEN` / `SB_GDDIR` in the crash-dump register list.
> Read-only, from a developer trap handler, never from game logic; and
> **reading** the real Dreamcast `SB_GDSTAR`/`GDLEN`/`GDDIR` is side-effect
> free (`../flycast4naomi2dreamcast/core/hw/holly/sb.h:149-155` — plain RW
> registers, no read-side action; contrast `SB_GDST`, whose *write* triggers
> the transfer — `Naomi_DmaStart`, `.../core/hw/naomi/naomi.cpp:482`, wired to
> that address by
> `hollyRegs.setWriteHandler<SB_GDST_addr>(Naomi_DmaStart)`, `naomi.cpp:587`).
> Patching them would only change which zeros a crash dump prints. Left alone.

### Test image — the same 32 words, the same shape

The Test load entry (`.dat 0x171ff8`, `0x4dc40` B, same RAM base
`0x8c020000`) is a separately linked build of the same code. Scanned with the
committed scanner:

```
python3 scripts/scan_dat_constants.py senkosp.dat --range 0x171ff8:0x1bfc38 \
        --words a05f7000-a05f77ff,a05f6c00-a05f6cff
```

**52 hits: 32 cart/G1 + 20 maple** — identical counts to the main image
(`--range 0x0:0x171ff8`, same words). The 32 cart/G1 words map **1:1** onto
the main image's 32, in the same order, with the same values and the same
register roles; only the addresses of the driver block differ, because the
test image is smaller. CART-BASE is at the *same* RAM address in both
(`0x8c0275e8`), and the accessor and its caller are byte-identical:
`0x8c02751a` = `d033` (`mov.l @(0x33,PC),r0`) and
`0x8c0278a0`–`0x8c0278ac` = `be3b 1ed5 e158 9364 31ec 9263 2102` in both
images. `FUN_8c027e34`, `FUN_8c027e5e`, `FUN_8c027f54`, `FUN_8c027d7e` and
the whole boot cart DMA routine are byte-identical across the two images; the
displacement pools (`0x0418`/`0x0414`/`0x04f8`/`0x04b8`/`0x0404`/`0x0408`/
`0x040c`) were re-read from the test image and match.

| # | `dat_offset` | RAM addr | old u32 | register | anchor | loader instruction(s) |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `0x1795e0` | `8c0275e8` | `0xa05f7000` | `NAOMI_ROM_OFFSETH` | CART-BASE | `8c02751a` `mov.l @(0x33,PC),r0` |
| 2 | `0x1a2a98` | `8c050aa0` | `0xa05f7418` | `SB_GDST` | BOOT-POOLS | `8c050a18` `mov.l @(0x21,PC),r2` |
| 3 | `0x1a2aa0` | `8c050aa8` | `0xa05f703c` | `NAOMI_DIMM_COMMAND` | BOOT-POOLS | `8c050a24` `mov.l @(0x20,PC),r2` |
| 4 | `0x1a2aa8` | `8c050ab0` | `0xa05f7014` | `NAOMI_DMA_COUNT` | BOOT-POOLS | `8c050a70` `mov.l @(0x0f,PC),r1` |
| 5 | `0x1a2b94` | `8c050b9c` | `0xa05f74b8` | `SB_GDAPRO` | G1-TIMING | `8c050abc` `mov.l @(0x37,PC),r2` |
| 6 | `0x1a2b98` | `8c050ba0` | `0xa05f7480` | `SB_G1RRC` | G1-TIMING | `8c050ac2` `mov.l @(0x37,PC),r3` |
| 7 | `0x1a2b9c` | `8c050ba4` | `0xa05f7484` | `SB_G1RWC` | G1-TIMING | `8c050ac8` `mov.l @(0x36,PC),r1` |
| 8 | `0x1a2ba0` | `8c050ba8` | `0xa05f7490` | `SB_G1CRC` | G1-TIMING | `8c050ad6` `mov.l @(0x34,PC),r7` |
| 9 | `0x1a2ba4` | `8c050bac` | `0xa05f74a4` | `SB_G1GDWC` | G1-TIMING | `8c050ada` `mov.l @(0x34,PC),r5` |
| 10 | `0x1a2c50` | `8c050c58` | `0xa05f7418` | `SB_GDST` | BOOT-POOLS | `8c050bca` `mov.l @(0x23,PC),r2` |
| 11 | `0x1a2c58` | `8c050c60` | `0xa05f7000` | `NAOMI_ROM_OFFSETH` | CART-PIO | `8c050c0e` `mov.l @(0x14,PC),r2`, `8c050c2c` `mov.l @(0x0c,PC),r3` |
| 12 | `0x1a2c5c` | `8c050c64` | `0xa05f7004` | `NAOMI_ROM_OFFSETL` | CART-PIO | `8c050c1a` `mov.l @(0x12,PC),r2` |
| 13 | `0x1a2c68` | `8c050c70` | `0xa05f7008` | `NAOMI_ROM_DATA` | CART-PIO | `8c050c34` `mov.l @(0x0e,PC),r4` |
| 14 | `0x1a2d5c` | `8c050d64` | `0xa05f7418` | `SB_GDST` | BOOT-POOLS | `8c050c80` `mov.l @(0x38,PC),r14`, `8c050ce8` `mov.l @(0x1e,PC),r0` |
| 15 | `0x1a2d60` | `8c050d68` | `0xa05f7004` | `NAOMI_ROM_OFFSETL` | BOOT-POOLS | `8c050c88` `mov.l @(0x37,PC),r2` |
| 16 | `0x1a2d68` | `8c050d70` | `0xa05f7000` | `NAOMI_ROM_OFFSETH` | BOOT-POOLS | `8c050c90` `mov.l @(0x37,PC),r3` |
| 17 | `0x1a2d6c` | `8c050d74` | `0xa05f7014` | `NAOMI_DMA_COUNT` | BOOT-POOLS | `8c050c9a` `mov.l @(0x36,PC),r1` |
| 18 | `0x1a2d70` | `8c050d78` | `0xa05f7010` | `NAOMI_DMA_OFFSETL` | BOOT-POOLS | `8c050ca2` `mov.l @(0x35,PC),r2` |
| 19 | `0x1a2d7c` | `8c050d84` | `0xa05f700c` | `NAOMI_DMA_OFFSETH` | BOOT-POOLS | `8c050cb4` `mov.l @(0x33,PC),r3`, `8c050cdc` `mov.l @(0x29,PC),r2`, `8c050cf4` `mov.l @(0x23,PC),r2` |
| 20 | `0x1a2d80` | `8c050d88` | `0xa05f7404` | `SB_GDSTAR` | BOOT-POOLS | `8c050cbc` `mov.l @(0x32,PC),r2` |
| 21 | `0x1a2d84` | `8c050d8c` | `0xa05f7408` | `SB_GDLEN` | BOOT-POOLS | `8c050cc0` `mov.l @(0x32,PC),r3` |
| 22 | `0x1a2d88` | `8c050d90` | `0xa05f740c` | `SB_GDDIR` | BOOT-POOLS | `8c050cc4` `mov.l @(0x32,PC),r1` |
| 23 | `0x1a32b4` | `8c0512bc` | `0xa05f700c` | `NAOMI_DMA_OFFSETH` | BOOT-POOLS | `8c0511bc` `mov.l @(0x3f,PC),r0` |
| 24 | `0x1a419c` | `8c0521a4` | `0xa05f7418` | `SB_GDST` | CART-WAIT | `8c052010` `mov.l @(0x64,PC),r4`, `8c0520d4` `mov.l @(0x33,PC),r5`, `8c0520f8` `mov.l @(0x2a,PC),r4`, `8c052124` `mov.l @(0x1f,PC),r4` |
| 25 | `0x1a4308` | `8c052310` | `0xa05f7418` | `SB_GDST` | CART-WAIT | `8c0521ec` `mov.l @(0x48,PC),r4`, `8c052206` `mov.l @(0x42,PC),r4` |
| 26 | `0x1a432c` | `8c052334` | `0xa05f7068` | `NAOMI_LED` | BOOT-POOLS | `8c052234` `mov.l @(0x3f,PC),r3` |
| 27 | `0x1a4470` | `8c052478` | `0xa05f7418` | `SB_GDST` | CART-WAIT | `8c05242c` `mov.l @(0x12,PC),r4` |
| 28 | `0x1a4640` | `8c052648` | `0xa05f7418` | `SB_GDST` | CART-WAIT | `8c0525e6` `mov.l @(0x18,PC),r2` |
| 29 | `0x1b247c` | `8c060484` | `0xa05f7418` | `SB_GDST` | BOOT-POOLS | — (data-table entry, no pc-relative loader) |
| 30 | `0x1b2544` | `8c06054c` | `0xa05f7404` | `SB_GDSTAR` | *exempt* | — (data-table entry, no pc-relative loader) |
| 31 | `0x1b2548` | `8c060550` | `0xa05f7408` | `SB_GDLEN` | *exempt* | — (data-table entry, no pc-relative loader) |
| 32 | `0x1b254c` | `8c060554` | `0xa05f740c` | `SB_GDDIR` | *exempt* | — (data-table entry, no pc-relative loader) |

Test-image hook sites, same four functions:

| Hook | test `dat_offset` | test RAM | evidence |
| --- | --- | --- | --- |
| CART-WAIT-A | `0x179e56` | `8c027e5e` | body bytes identical to main `0x007e5e` |
| CART-WAIT-B | `0x179e2c` | `8c027e34` | body bytes identical to main `0x007e34` |
| CART-BOOT-DMA | `0x1a2c6c` | `8c050c74` | prologue `2fe6 7ffc`; body `0x1a2c6c`–`0x1a2ce0` byte-identical to main `0x046440`–`0x0464b4` |
| CART-PIO-READ | `0x1a2c12` | `8c050c1a` | preceded by `rts`/`nop` (`000b`/`0009` at `0x1a2c0e`/`0x1a2c10`); body `0x1a2c12`–`0x1a2c41` byte-identical to main `0x0463e6`–`0x046415`; no caller, same as main |

Test entries 29–32 sit in the same two tables (`0x8c060488` = `0` is entry
29's paired value; `0x8c06054c`–`0x8c060554` are consecutive entries of the
flat crash-dump list starting `0x8c060544` = `0xa05f6c04`), so they take the
same disposition: 29 repointed, 30–32 exempt.

### Handed to Task 4 — the maple words this scan also saw

Out of scope here (`MAPLE_MIRROR`, spec P4/Task 4), listed so nothing is
dropped. **20 words in each image**, same 1:1 correspondence. Test-image
`dat_offset` / value:

`0x178b50`=`0xa05f6c00` (the maple base constant, `FUN_8c026b30`'s analog —
the maple counterpart of CART-BASE), `0x1a2e78`/`0x1a32ec`=`0xa05f6c14`,
`0x1a2fb8`/`0x1a3058`/`0x1a3184`/`0x1a3304`=`0xa05f6c04`,
`0x1a32f4`=`0xa05f6c8c`, `0x1a32fc`=`0xa05f6c80`, `0x1a3300`=`0xa05f6c10`,
`0x1a3308`=`0xa05f6c18`, `0x1b22f4`/`0x1b253c`=`0xa05f6c04`,
`0x1b22fc`/`0x1b2540`=`0xa05f6c10`, `0x1b2304`=`0xa05f6c14`,
`0x1b230c`=`0xa05f6c80`, `0x1b2314`=`0xa05f6c8c`, `0x1b231c`=`0xa05f6ce8`,
`0x1b2474`=`0xa05f6c18`. The main image's 20 are the 11 code pools
`FindMmioXrefs` reports as `block=maple` (`0x8c026b58`, `0x8c06664c`,
`0x8c06678c`, `0x8c06682c`, `0x8c066958`, `0x8c066ac0`, `0x8c066ac8`,
`0x8c066ad0`, `0x8c066ad4`, `0x8c066ad8`, `0x8c066adc` —
`tools/mmio-xrefs.txt:52,66-69,71-76`) plus 9 data-table words the raw scan
adds (`0x8c15c4c8`, `4d0`, `4d8`, `4e0`, `4e8`, `4f0` in the init-pair list;
`0x8c15c648` likewise; `0x8c15c710`, `0x8c15c714` in the crash-dump list).
Reproduce with `--words a05f6c00-a05f6cff`. **All 20 are dispositioned in
§Maple-patch sites below** (Task 4): 1 base repoint, 17 own entries, 2
exemptions.

### Completeness accounting

| | main | test |
| --- | --- | --- |
| Words with phys in `0x5f7000`–`0x5f77ff` (raw scan) | 32 | 32 |
| … covered by the CART-BASE repoint (entry 1) | 1 | 1 |
| … own `pool()` patch entries (2–29) | 28 | 28 |
| … written exemptions (30–32) | 3 | 3 |
| Entry hooks | 4 | 4 |
| `tools/mmio-xrefs.txt` hits in this range | 13 | n/a |
| … of those, unaccounted for | **0** | — |

The 13 `mmio-xrefs.txt` lines in range (`:53` `0x8c0275e8`; `:58`–`:62`
`0x8c066368`–`0x8c066378`; `:63` `0x8c066424`; `:64` `0x8c066530`; `:65`
`0x8c066550`; `:70` `0x8c066a88`; `:77`–`:79` `0x8c067970`/`0x8c067adc`/
`0x8c067c44`) are entries 1, 5–9, 10, 14, 19, 23, 24, 25, 27 — all present.
The other 19 raw-scan words were invisible to `FindMmioXrefs` for the reasons
that doc already gives (undefined data spans, data tables). No cart/G1 site
in either image is left without a patch entry, a hook, or an exemption.

Additionally, the steady path contributes **zero** whole-address constants —
its registers are all `obj->[0x58] + disp16` — which is why entry 1 alone
carries it and why a constant scan could never have found it (blind spot (2),
`docs/kb/boot-binary.md`).

### Residual risks — for Task 9/10 to close, not silently inherit

1. **A G1 base derived by arithmetic from another base.** The mirror layout
   does not preserve hardware's relative distances: on hardware
   `0x5f7000 − 0x5f6c00 = +0x400`, in the shim
   `G1_MIRROR − MAPLE_MIRROR = −0x800`. Any code computing the G1 base as
   `maple_base + 0x400` (or the reverse) would break. Nothing in the scans
   suggests it exists — the only `0xa05f7000` in the image is entry 1's, and
   Phase 3's dynamic evidence puts **all 672** logged kicks at the one PC
   `0x8c027f72` — but the scans structurally cannot rule it out. The cheap
   check is Task 10's: a dry run with the real G1 registers left unmapped or
   watched will surface any access that escapes the mirror.
2. **`FUN_8c027d7e`'s kick has never been observed.** All 672 logged kicks
   are `FUN_8c027f54`'s. Its only call site is indirect: `FUN_8c027798`
   (`0x8c027798`–`0x8c0277c5`) loads the pointer word `0x8c02780c` at
   `0x8c0277c2` and jumps through it, and that word is byte-verified to hold
   `0x8c027d7e`. So it is live code, but its
   interaction with the service hook (kick without an immediate wait) is
   reasoned from the listing, not measured. CART-WAIT-B exists because of it.
3. **The boot cart DMA routine likewise.** See CART-BOOT-DMA above.
4. **`SB_GDAPRO` values differ between the two drivers** — `0x8843407f`
   (steady, pools `0x8c027bdc`/`0x8c027e30`) vs `0x8843007f` (boot, pool
   `0x8c066364`), both byte-verified. Neither reaches hardware after the
   repoint; noted only so a reader does not treat one as a typo for the other.

### Reproduction

```sh
# 1. raw word scan of both load entries (the completeness bar)
python3 scripts/scan_dat_constants.py senkosp.dat --range 0x0:0x171ff8 \
        --words a05f7000-a05f77ff,a05f6c00-a05f6cff      # 52 hits: 32 cart/G1 + 20 maple
python3 scripts/scan_dat_constants.py senkosp.dat --range 0x171ff8:0x1bfc38 \
        --words a05f7000-a05f77ff,a05f6c00-a05f6cff      # 52 hits: 32 cart/G1 + 20 maple
cd scripts && python3 test_scan_dat_constants.py         # -> OK scan_dat_constants self-check

# 2. old-value + loader-instruction verification, straight from the image
python3 - <<'EOF'
import struct
d=open("senkosp.dat","rb"); d.seek(0); img=d.read(0x171ff8)   # 0x171ff8/0x4dc40 for test
B=0x8c020000
for o in range(0,len(img)-3,4):
    v=struct.unpack_from("<I",img,o)[0]
    if not (0x5f7000 <= (v & 0x1fffffff) <= 0x5f77ff): continue
    a=B+o; r=[]
    for q in range(0,len(img)-1,2):                 # every pc-relative pool load
        i=struct.unpack_from("<H",img,q)[0]; p=B+q
        t=((p+4)&~3)+(i&0xff)*4 if i>>12==0xD else (p+4+(i&0xff)*2 if i>>12==9 else None)
        if t==a: r.append("%08x"%p)
    print("off=0x%06x addr=%08x old=0x%08x loaders=%s"%(o,a,v,",".join(r) or "-"))
EOF

# 3. semantics (Ghidra 12.1.2 headless, program senkosp3 — docs/kb/tooling.md §Ghidra)
scripts/ghidra/run.sh script ListPoolWords.java 0x005f7000 0x005f7800
scripts/ghidra/run.sh script Decomp.java 0x8c027f54 0x8c027a66 0x8c02751a 0x8c027d7e \
        0x8c027e5e 0x8c027e34 0x8c027f9a 0x8c027fe4 0x8c027894 0x8c066288 0x8c0664b4 \
        0x8c02c584
scripts/ghidra/run.sh script DisasmRange.java 0x8c027894 0x8c0278d8
scripts/ghidra/run.sh script DisasmRange.java 0x8c027f54 0x8c028020
scripts/ghidra/run.sh script DisasmRange.java 0x8c0663e6 0x8c066418 force
scripts/ghidra/run.sh script DisasmRange.java 0x8c066444 0x8c0664b4 force
```

`DisasmRange … force` writes to the project DB (monotonic — it only adds
instructions); `run.sh import` rebuilds from scratch if that ever needs
undoing.

## Maple-patch sites — spec pin P4

**Question (spec `2026-08-22-phase4-conversion-design.md` §Maple/MIE shim, plan
pin P4; task brief
`.superpowers/sdd/2026-08-22-phase4-conversion/task-4-brief.md`):** which exact
`.dat` words must be rewritten, and which sites hooked, so that every maple
MMIO access senkosp performs lands in the shim's RAM mirror, and what contract
the shim's service routine has to honour once it does.

### Conventions used below

- **`dat_offset`** — same rule as §Cart-patch sites. Main image
  `dat_offset = addr − 0x8c020000`; test image
  `dat_offset = 0x171ff8 + (addr − 0x8c020000)`.
- **`MAPLE_MIRROR`** = `0x8c015000`, `0x100` bytes, faking physical
  `0x5f6c00`–`0x5f6cff`; `MAPLE_MIRROR_P2` = `0xac015000`
  (`docs/superpowers/plans/2026-08-22-phase4-conversion.md`). It sits inside the
  shim home `0x8c010000`–`0x8c018000` this doc's §Shim home found clean, and
  `0x100` covers every offset either image reaches: the largest is `+0xe8`
  (`SB_MMSEL`, entry 17).
- **`new` values are symbolic**: every repoint below is
  `new = MAPLE_MIRROR_P2 + (old & 0xff)`. Task 9 computes the literals from
  `shim_iface.h`.
- Every `old` value in every table was read byte-for-byte out of `senkosp.dat`
  at the stated `dat_offset` (test image) or out of `tools/boot.bin` at
  `addr − 0x8c020000` (main image) by the generators quoted under
  §Reproduction — not copied from a decompiler listing.
- Register names/addresses throughout:
  `../flycast4naomi2dreamcast/core/hw/holly/sb.h:115-142` — `SB_MDSTAR`
  `0x005F6C04`, `SB_MDTSEL` `0x005F6C10`, `SB_MDEN` `0x005F6C14`, `SB_MDST`
  `0x005F6C18`, `SB_MSYS` `0x005F6C80`, `SB_MDAPRO` `0x005F6C8C`, `SB_MMSEL`
  `0x005F6CE8`.

### R5 — the "second maple call site" is the **Naomi BIOS**, not game code

Phase 3 and Phase 4 Task 1 left an open item: a second, register-triggered
(`trig=reg`) maple call site at PC `0c03161e` (+5 siblings in
`0c031xxx`/`0c032xxx`), issuing 745 `MAPLEPC` events in the attract leg and
carrying **all 16** of Phase 3's sub-`0x0b` EEPROM writes, whose function this
project had never identified (`docs/kb/boot-binary.md` §Addendum 2026-08-22 —
Phase 4 Task 1). It is identified here, and it is not a function in either
image: **it is the Naomi BIOS, running its own maple/JVS driver out of RAM
before it hands the machine to the game.**

Four independent lines of evidence, all from `captures/phase4/pc2.log`:

1. **Chronology.** The fork emits a one-shot `MAINHANDOFF` marker at the first
   bulk cart→RAM transfer, i.e. when the BIOS starts loading the game image
   (`cartlog_handoff()`,
   `../flycast4naomi2dreamcast/core/hw/naomi/naomi.cpp:334-352`; PIO trigger
   `:354-360`) — specifically once cumulative PIO `ROM_DATA` reads cross
   **32 KB** (`if (cartlog_pio_bytes >= (32 << 10)) cartlog_handoff("pio")`,
   `naomi.cpp:363-365`). Its ARAM/VRAM/MAIN triple lands at log lines
   11150–11152 (1-based, as `grep -n` counts). Every one of the six `0c03…`
   `MDODMA` PCs occurs **before** it (first 175, last 11103); every one of the
   six `8c0…` PCs occurs **after** it (11201 … 340956). The two families do
   not overlap by a single event. The 32 KB threshold makes the inference
   *stronger*, not weaker: at the marker the BIOS had loaded only ~32 KB of
   the image, i.e. up to ≈`0x0c028000`, whereas `0x0c03161e` is `0x1161e`
   ≈ 71 KB in — so the game bytes at that address had not even been written
   yet when the marker fired, let alone when those PCs executed earlier.
2. **The whole P0/P1 split is the BIOS/game split.** Pre-handoff, all 26
   `PCSAMPLE` lines are P0-form (`0c03`×19, `0c04`×5, `0c05`×1, `0c02`×1) plus
   one `a000` ROM sample; post-handoff, all 271 are P1-form
   (`8c02`/`8c03`/`8c04`/`8c05`/`8c06`/`8c08`–`8c12`). The `SOFWR` probe splits
   the same way: its four P0 PCs (`0c0548da`/`0c0548e4`/`0c054da8` at
   383/384/384 events and `0c0558ea` at 4) are all pre-handoff; its single
   P1 PC `8c032146` is all post-handoff. **senkosp never executes at a P0/U0 address** — which
   retires this doc's sibling claim in `boot-binary.md` §The `+2` rule that
   "senkosp genuinely executes from both mirrors".
3. **The `+2` store test was never failing; it was reading the wrong bytes.**
   `0x8c03161c` holds `4b08` `shll2 r11` in `tools/boot.bin` because
   `tools/boot.bin` is the *game* image, which the BIOS had not yet loaded when
   those transactions ran. Ghidra confirms the game bytes there are unrelated
   code: `0x8c03161c` is inside `FUN_8c031560` (`8c031560`–`8c031aef`), an
   FPU/matrix routine called from `FUN_8c02e300`; the five siblings land in
   `FUN_8c031560`, `FUN_8c031c20` (render-target setup), `FUN_8c031f00` (an
   8-byte-aligned `fmov` memcpy) and `FUN_8c031fee`. A brute-force search for
   *any* uniform virtual→physical page delta (1 K / 4 K / 64 K / 1 M
   granularity, whole image) that makes even 5 of the 6 PCs land two bytes
   after a store instruction returns **zero** candidates — there is no mapping
   of those PCs into this image, because they were never in it.
4. **Separate buffers, separate stack.** The BIOS-era transactions use
   `SB_MDSTAR = 0x0c296a20` with the MIE reply address `0x0c296220`, against
   the game's `0x0dfe7f40`/`0x0dfeaf40` (steady, double-buffered) and
   `0x0c1bfa80` (the game's boot driver). Their `sp=0x0cbffdc4`-`0x0cbfff9c` is
   the BIOS's stack, not a third game task stack.
5. **The same PC, the same counts and the same buffer appear in a
   *different game*.** `../cleopatra/docs/kb/phase4-conversion.md:847-849`
   records, for Cleopatra Fortune Plus, interpreter-exact PCs from its own
   Phase 3 capture: sub `0x15` **369× `pc=0c03161e`**, sub `0x27` **360×
   `pc=0c03161e`**, sub `0x01` and `0x03` **1× `0c03161e`** each. senkosp's
   `pc2.log` measures **369 / 360 / 1 / 1 at the identical PC**. And
   `:906` records that game's MIE reply address as **`0x0c296220`** — the
   identical buffer. Two unrelated 2006-era Naomi titles cannot produce the
   same program counter, the same per-subcommand counts *and* the same RAM
   buffer from their own code; the only thing they share is the machine's
   BIOS. Shared middleware cannot explain it either: middleware links to
   different addresses in the two images (senkosp's steady engine is
   `FUN_8c02532a`, Cleopatra's is `FUN_8c03c2c6`), and senkosp's bytes at
   `0x8c03161c` are `4b08`, unrelated code.

   > **Corollary, recorded here and not acted on there.** Cleopatra's KB
   > attributes those same events to a routine of *its* game image,
   > `0x8c0315ce` (`:847-848`, `:900-906`) — the same misattribution
   > senkosp's Phase 3/Task 1 made from the same PC-only evidence, and now
   > explained. The sibling repo is not edited from here; flagged for the
   > human.

> **R5 verdict — no patch entry, and one open item closes.** The site is BIOS
> code that the Dreamcast port replaces wholesale (there is no Naomi BIOS on
> the target; the shim's loader owns pre-game bring-up), so it contributes
> **no** `.dat` word, no hook, and no exemption to the accounting below: it is
> not in either image. Its *function* — JVS I/O-board negotiation and EEPROM
> access before the game runs — is a **shim boot-path** obligation and is
> recorded under MAPLE-BOOT-STRATEGY, which is the anchor Tasks 11/12 consume
> for it. Three consequences:
>
> - **The EEPROM *write* call site is named:** the Naomi BIOS. senkosp itself
>   was never observed writing the EEPROM in any leg. This upholds, with a
>   reason, `boot-binary.md`'s standing ruling that free-play must be forced by
>   **subcommand filtering in the shim** plus a baked EEPROM image, never by
>   patching a game call site — there is no game call site to patch.
> - **`FUN_8c02532a`'s range was right all along.** `input_pc_in_input_fn` and
>   `eeprom_read_seen` were failing on BIOS traffic charged against a
>   game-image range, not on a missing range. No range is widened; the parser
>   learns to drop pre-handoff events instead (§Check lines Run D in
>   `boot-binary.md`).
> - **The "unmeasured third stack region" flag dissolves.** `boot-binary.md`
>   §SP water-mark carried `sp≈0x0cbffdc4` as an unidentified region whose
>   depth Phase 4 RAM planning had to worry about. It is the Naomi BIOS's
>   stack, dead before the game's first instruction. Nothing to reserve.

**Also settled in passing: senkosp does enable the SH-4 MMU.** `MMUCR` is
written `0x00040005` (`AT=1`) at log line 12580 — *after* the handoff, so it is
the game, not the BIOS — and `FUN_8c02d638` (`8c02d638`–`8c02d6c9`) is a UTLB
entry writer: it scans up to `0x40` entries, then stores into
`DAT_8c02d730 + n*0x100` and `DAT_8c02d744 + n*0x100` (the SH-4 UTLB address
and data arrays, `0x100`-byte stride), with the free-entry search seeded from
`*DAT_8c02d72c >> 0x12 & 0x3f` (`MMUCR.URB`). Callers `FUN_8c02c43c`,
`FUN_8c02e0e0`. This is **not** load-bearing for the maple model — every
post-handoff PC and both game stacks are P1-form, i.e. untranslated — but it is
recorded here because it was the hypothesis that had to be eliminated before
the BIOS explanation could be trusted, and because a shim that reprograms the
TLB would collide with it.

### MAPLE-BASE — one word, and the middleware it belongs to

`FUN_8c026b30` (`8c026b30`–`8c026b3b`) is the maple counterpart of CART-BASE.
Verbatim `DisasmRange.java 0x8c026b30 0x8c026b60`, byte-verified halfwords in
the margin:

```
8c026b30  mov.l 0x8c026b4c,r2      ; d206   r2 = 0x8c1938dc  (the global base-ptr cell)
8c026b32  mov.w 0x8c026b3e,r0      ; 9004   r0 = 0x10f4      (field offset)
8c026b34  mov.l 0x8c026b58,r1      ; d108   r1 = 0xa05f6c00  <== THE MAPLE BASE CONSTANT
8c026b36  mov.l @r2,r3             ; 6322   r3 = *(0x8c1938dc)
8c026b38  rts                      ; 000b
8c026b3a  _mov.l r1,@(r0,r3)       ; 0316   base->[0x10f4] = 0xa05f6c00   <== THE BASE STORE
```

(`Decomp.java 0x8c026b30` renders the same store as
`*(undefined4 *)((int)DAT_8c026b3e + *DAT_8c026b4c) = DAT_8c026b58`.) The
confirmed steady engine `FUN_8c02532a` reads exactly that field — verbatim
`DisasmRange.java 0x8c025400 0x8c025480`, abridged to the two loads:

```
8c025368  mov.w 0x8c02548e,r0      ; r0 = 0x10f4          (entry guard)
8c02536a  mov.l @r14,r2            ; r14 = 0x8c1938dc
8c02536c  mov.l @(r0,r2),r3        ; r3 = base->[0x10f4] = maple base
8c02536e  mov.l @(0x18,r3),r1      ; read SB_MDST
8c025370  tst r12,r1               ; r12 = 1
8c025372  bt 0x8c025378            ; busy -> return -1 at 8c025376
```

Byte-verified: `[0x8c026b3e]` = `0x10f4` = `[0x8c02548e]` (same field offset),
`[0x8c026b4c]` = `0x8c1938dc` = `[0x8c025364]` (same base-pointer cell),
`[0x8c026b58]` = `0xa05f6c00`. Every steady-path register is then
*base + a literal displacement*, and the whole set is small: `+0x04`
(`SB_MDSTAR`, written at `8c02543a`), `+0x14` (`SB_MDEN`, cleared then set,
`Decomp.java 0x8c02532a`), `+0x18` (`SB_MDST`, guard at `8c02536e`,
kick at `8c025446`) and `+0x80` (`SB_MSYS`, `[0x8c025496]` = `0x0080`,
`SB_MSYS = base->[0x10c0] | base->[0x10d0]`). All inside the `0x100` mirror.

**This is the same middleware Cleopatra ported.** Cleopatra's steady MIE engine
`FUN_8c03c2c6` uses the *identical* structure offsets — `[base+0x10f4]` for the
register base, `[base+0x10b8]` for the double-buffer index, `[base+0x10a8+idx*4]`
for the command-list pointers, and the same `mov.l r12,@(0x18,r2)` kick
(`../cleopatra/docs/kb/phase4-conversion.md` §Site B — steady builder). senkosp
reproduces all four: `[0x8c025498]` = `0x10b8`, `[0x8c02549a]` = `0x10a8`,
`0x8c025446` = `12c6`. The `.dat`-side conclusion follows Cleopatra's: one word.

> **MAPLE-BASE verdict — 1 patch entry.**
> `pool(dat_offset=0x006b58, old=0xa05f6c00, new=MAPLE_MIRROR_P2 + 0x00)`
> (main image; test image `0x178b50`, same value, same RAM address
> `0x8c026b58`, same loader instruction — see §Test image). It carries the
> entire steady path, whose registers are all `base->[0x10f4] + disp` and which
> therefore contributes **zero** whole-address constants of its own (blind spot
> (2), `docs/kb/boot-binary.md`).

### MAPLE-KICK-HOOK — a pool repoint, not a thunk

The steady kick, verbatim `DisasmRange.java 0x8c025400 0x8c025480` with
byte-verified halfwords:

```
8c025436  jsr @r2                  ; 420b   r2 = [0x8c0254bc] = 0x8c026b26  (P1->phys)
8c025438  _mov.l @r4,r4            ; 6442   r4 = base->[0x10a8 + idx*4] = the command list
8c02543a  mov.l r0,@r8             ; 2802   SB_MDSTAR = list & 0x0fffffff   (r8 = base+0x04)
8c02543c  mov.w 0x8c02548e,r0      ; 9027   r0 = 0x10f4
8c02543e  mov.l @r14,r3            ; 63e2   r3 = *(0x8c1938dc)
8c025440  mov.l @(r0,r3),r2        ; 023e   r2 = maple base
8c025442  mov.l 0x8c0254c0,r3      ; d31f   r3 = [0x8c0254c0] = 0x8c02a17e
8c025444  jsr @r3                  ; 430b
8c025446  _mov.l r12,@(0x18,r2)    ; 12c6   SB_MDST = 1   <== THE KICK (delay slot; r12 = 1)
8c025448  mov.l 0x8c0254c4,r2      ; d21e   r2 = [0x8c0254c4] = 0x8c19268c
8c02544a  mov.l r0,@r2             ; 2202   *(0x8c19268c) = the jsr's return value
```

`FUN_8c026b26` (`8c026b26`–`8c026b2b`) is `return 0x0fffffff & param`
(`d00b 000b 2049`, `[0x8c026b54]` = `0x0fffffff`) — the P1→physical mask, i.e.
Cleopatra's `FUN_8c030fba`. `FUN_8c02a17e` (`8c02a17e`–`8c02a187`) is
`d244 e0ff 6322 000b 3038` = `return -1 - *(u32 *)0xffd8000c` — a read of SH-4
**TMU `TCNT0`** (`[0x8c02a290]` = `0xffd8000c`;
`../flycast4naomi2dreamcast/core/hw/sh4/sh4_mmr.h:324-325`), i.e. a
timestamp; **17 pool words across the image hold its address** (byte-verified
scan), and it exists identically on Dreamcast.

**What a 6-byte thunk at `0x8c025446` would cost.** The kick is *in the delay
slot of the `jsr` at `0x8c025444`*, so the only contiguous 6-byte window
containing it is `0x8c025442`–`0x8c025447` (`d31f 430b 12c6`). A
`mov.l @(d,PC),rN / jsr @rN / nop` thunk there clobbers **r3** (dead — rewritten
at `0x8c02544e`), **PR** (already clobbered by the `jsr` it replaces, and
`FUN_8c02532a` saved PR in its prologue, `8c025338 sts.l PR,@-r15`) and **r0**,
which is *not* free: `0x8c02544a` stores r0 into `*(0x8c19268c)`, so the thunk
target must still return `FUN_8c02a17e()`'s value.

**But no thunk is needed.** That window's first instruction already loads its
target from a pool word, `[0x8c0254c0]`, and that pool word has **exactly one
loader** (`0x8c025442`; verified by a whole-image pc-relative loader scan) even
though `0x8c02a17e` itself appears in 17 pool words. Repointing that single
word turns the existing `jsr` into the hook, with zero instructions rewritten
and nothing clobbered that the original did not already clobber:

> **MAPLE-KICK-HOOK verdict — 1 pool repoint, hook kind = fn-ptr slot.**
>
> | Hook | `dat_offset` (main / test) | patch | contract |
> | --- | --- | --- | --- |
> | **MAPLE-KICK-HOOK** | `0x0054c0` / `0x1774b8` | `pool(old=0x8c02a17e, new=shim_maple_service)` | see box below |
>
> `shim_maple_service` is entered **after** the kick store has already run (SH-4
> executes the delay slot before the branch), with the mirror fully programmed:
> `mirror[0x04]` = the physical command-list address, `mirror[0x18]` = 1. It
> must (a) walk that list and synthesize each reply into the block's own recv
> address per §MIE-DESC, (b) **clear `mirror[0x18]` to 0** — the same mirror
> invariant §Cart-patch sites states for `SB_GDST`; `FUN_8c02532a`'s entry guard
> at `0x8c02536e` returns `-1` forever otherwise — and (c) **return
> `FUN_8c02a17e()`'s value in r0**, either by tail-calling `0x8c02a17e` or by
> recomputing `-1 - *(volatile u32 *)0xffd8000c`. A plain SH-4 C function
> satisfies the rest of the ABI: `FUN_8c02532a` needs r8/r12/r13/r14 across the
> call and those are callee-saved.
>
> Rejected alternative: entry-hooking `FUN_8c02532a` itself. It would have to
> reimplement the descriptor build (double-buffer index toggle, `SB_MDSTAR`
> programming, the `tas.b` semaphore reached through `[0x8c0254a8]` =
> `0x8c026b5c`, the 24-slot bookkeeping loop and the `0`/`-1`/`-2`/`-3`
> return codes) — many reimplemented semantics for no gain. The pool repoint
> reimplements none.

### MIE-DESC — the descriptor the shim must walk

The game programs `SB_MDSTAR` (mirror `+0x04`) with the **physical** address of
a maple command list (`& 0x0fffffff`, `FUN_8c026b26` above) and sets `SB_MDST`
(mirror `+0x18`). Everything downstream is defined by the emulator's walk, which
is the primary source for what real Holly does — `maple_DoDma()`,
`../flycast4naomi2dreamcast/core/hw/maple/maple_if.cpp:150-373`:

| word | field | decode | citation |
| --- | --- | --- | --- |
| `+0x00` | `header_1` | `bit31` = last block; `bits[7:0]+1` = `plen`, frame length in 32-bit words; `bits[10:8]` = pattern (`0` = START); `bits[17:16]` = bus | `maple_if.cpp:208`, `:211-214` |
| `+0x04` | `header_2` | **recv address**, masked `& 0x1FFFFFE0` — the reply is DMA'd here | `:209` |
| `+0x08` | `frame_header` | `bits[7:0]` = command (`0x86` = `MDC_JVSCommand`), `bits[15:8]` = recipient, `bits[23:16]` = sender, `bits[31:24]` = extra word count | `:233`, `:241-250` |
| `+0x0c` | `payload[0]` | **low byte = the MIE subcommand** (`sub = ((const u8 *)p_data)[4]`) | `:307` |
| `+0x10…` | `payload[1…]` | JVS command bytes | `:233` |

Next block at `addr += (2 + plen) * 4` (`:325`); the walk ends on the block whose
`header_1` bit 31 is set (`:211`, loop `:198`). This is byte-for-byte the
descriptor `../cleopatra/docs/kb/phase4-conversion.md` §Shared descriptor
records, and senkosp's live `MDODMA enter` lines corroborate the header decode:
`hdr0=80000003` (last block, 4-word frame), `hdr0=00000003`/`80000007`/
`00010001` (multi-block lists, and one on bus 1).

Three details the shim must not get wrong:

- **No byte swap.** `swap_msb = (SB_MMSEL == 0)` (`maple_if.cpp:180`), and
  senkosp initialises `SB_MMSEL = 1` — byte-verified in the boot init-pair table,
  `[0x8c15c4f0]` = `0xa05f6ce8` paired with `[0x8c15c4f4]` = `0x00000001`
  (entry 17). So frames are little-endian as stored; no `SWAP32` on either
  direction.
- **Completion is asynchronous on hardware, and must be synchronous in the
  shim.** Flycast defers the reply copy and the `SB_MDST` clear to a scheduled
  callback (`mapleDmaOut.emplace_back(header_2, …)` `:314`; `maple_schd()`
  `memcpy` + `SB_MDST = 0` + `asic_RaiseInterrupt(holly_MAPLE_DMA)` `:375-401`).
  The shim has no such scheduler: it writes the reply and clears `mirror[0x18]`
  inline, before returning to `0x8c025448`. That is *stronger* than the hardware
  contract (the reply is ready earlier), and `FUN_8c02532a` only ever tests
  `SB_MDST` bit 0, never the ASIC interrupt, so nothing observes the difference.
- **`SB_MDTSEL` is 0 in both writers** — `FUN_8c066964` stores `r7 = 0` to it at
  `0x8c0669e2`, and the init-pair table sets it to `0` (entry 13). senkosp never
  arms the hardware vblank maple trigger, which is the *static* confirmation of
  Task 1's dynamic measurement (17 445/17 445 transactions `trig=reg`, zero
  `trig=vbl`) and of `maple_vblank()`'s `SB_MDTSEL == 1` branch never being
  taken (`maple_if.cpp:59-90`).

### MAPLE-BOOT-STRATEGY — five kicks, five self-contained detours

The `0x8c066xxx` boot driver reaches its registers by absolute pool, so every
word is its own patch entry (entries 2–11). It has **five** `SB_MDST` kick
sites, and Task 1's per-PC data attributes each of them: `0x8c066726` (341
events in `pc2.log`, 1023 in the Phase 3 leg), `0x8c066810`, `0x8c0668a2`,
`0x8c066926` (1 each) in `FUN_8c0665fe` (`8c0665fe`–`8c06694b`), and
`0x8c066a5e` (1) in `FUN_8c066964` (`8c066964`–`8c066b0f`).

`FUN_8c066964` is the init + one-shot scan; it programs the block from pools
(`DisasmRange.java 0x8c066964 0x8c066a70`, verbatim):

```
8c0669d2  mov.l 0x8c066ac0,r12     ; r12 = 0xa05f6c14  SB_MDEN
8c0669d4  mov.l r7,@r12            ;   <- 0            (r7 = 0)
8c0669d6  mov.l 0x8c066ac8,r0      ; r0  = 0xa05f6c8c  SB_MDAPRO
8c0669d8  mov.l 0x8c066ac4,r3      ; d33a  r3 = 0x6155407f
8c0669da  mov.l r3,@r0             ;   -> SB_MDAPRO
8c0669dc  mov.l 0x8c066ad0,r3      ; r3  = 0xa05f6c80  SB_MSYS
8c0669de  mov.l 0x8c066acc,r2      ; d23b  r2 = 0x3a980000
8c0669e0  mov.l r2,@r3             ;   -> SB_MSYS
8c0669e2  mov.l 0x8c066ad4,r1      ; r1  = 0xa05f6c10  SB_MDTSEL
8c0669e4  mov.l r7,@r1             ;   <- 0            (no vblank trigger)
8c0669e6  mov.l 0x8c066ad8,r0      ; r0  = 0xa05f6c04  SB_MDSTAR
8c0669ea  mov.l r2,@r0             ;   <- *(0x8c1bfe6c)
8c0669ec  mov.l 0x8c066adc,r4      ; r4  = 0xa05f6c18  SB_MDST
8c0669ee  mov.l r7,@r4             ;   <- 0
```

and its kick, with the poll that follows every one of the five:

```
8c066a54  mov.l 0x8c066ad8,r2      ; d220   r2 = SB_MDSTAR
8c066a56  mov.l @r14,r3            ; 63e2
8c066a58  mov.l r3,@r2             ; 2232   SB_MDSTAR <- list
8c066a5a  mov #0x1,r5              ; e501
8c066a5c  mov.l r5,@r12            ; 2c52   SB_MDEN   <- 1
8c066a5e  mov.l r5,@r4             ; 2452   SB_MDST   <- 1   <== kick
8c066a60  mov.l @r4,r2             ; 6242 \
8c066a62  tst r2,r2                ; 2228  |  poll until SB_MDST reads 0
8c066a64  bf 0x8c066a60            ; 8bfc /
8c066a66  mov.l r7,@r12            ; 2c72   SB_MDEN   <- 0
```

The four sites in `FUN_8c0665fe` are the same shape with `r5` = `SB_MDST`
(`r14` = `SB_MDEN` from pool `0x8c06664c`, `add #0x4,r5` at `0x8c066632`), all
byte-identical:

```
8c066726 / 8c066810 / 8c0668a2 / 8c066926   2572   mov.l r7,@r5   ; SB_MDST <- 1
       +2 / +2 / +2 / +2                    6252   mov.l @r5,r2   \
       +4                                   2228   tst r2,r2       |  the poll
       +6                                   8bfc   bf (-4)        /
```

After the repoint that poll reads RAM and spins forever unless something clears
it — the mirror invariant again. Two ways out were considered:

- **(a) Entry-hook `FUN_8c066964` and `FUN_8c0665fe`** and reimplement their
  contract in the shim. Cost: the whole JVS/maple enumeration, including
  everything `FUN_8c0665fe` writes back into game RAM through `[0x8c1bfe6c]`
  and friends — an unbounded reverse-engineering job, and exactly the kind of
  reimplementation §CART-WAIT avoided.
- **(b) Detour each kick.** There is no innermost kick+poll helper — the
  sequence is inlined at all five sites — but the **`SB_MDEN=1` / kick / poll**
  run is the window: contiguous, and every byte of it is dead work once the
  shim has serviced the transaction (its stores go to RAM; the loop's exit
  condition is already true). The driver's own code then parses the replies, so
  **nothing is reimplemented** beyond two mirror stores.

> **MAPLE-BOOT-STRATEGY verdict — option (b): 5 detour hooks, plus the pool
> repoints (entries 2–11) and the init-table repoints (entries 12–18).**
>
> Every window starts **two bytes before the kick**, at the `SB_MDEN = 1` store
> that precedes all five (`2e72 mov.l r7,@r14` at A–D, `2c52 mov.l r5,@r12` at
> E), so the literal the detour needs fits **inside the window itself** at
> `d = 0x01` — no external pool slot, no reachability question, no
> dead-word argument. Every byte below was read out of `tools/boot.bin`
> (main) and `senkosp.dat` (test); the two images are byte-identical over all
> five windows.
>
> | Hook | main window (RAM) | main `dat_offset` | test `dat_offset` | replaced halfwords | literal slot | resume |
> | --- | --- | --- | --- | --- | --- | --- |
> | **MAPLE-BOOT-A** | `8c066724`–`8c06672f` | `0x046724`–`0x04672f` | `0x1a2f50`–`0x1a2f5b` | `2e72 2572 6252 2228 8bfc 2ec2` | `8c06672c` / `0x04672c` / `0x1a2f58` | `8c066730` (`e318`) |
> | **MAPLE-BOOT-B** | `8c06680e`–`8c066817` | `0x04680e`–`0x046817` | `0x1a303a`–`0x1a3043` | `2e72 2572 6252 2228 8bfc` | `8c066814` / `0x046814` / `0x1a3040` | `8c066818` (`2ec2`) |
> | **MAPLE-BOOT-C** | `8c0668a0`–`8c0668ab` | `0x0468a0`–`0x0468ab` | `0x1a30cc`–`0x1a30d7` | `2e72 2572 6252 2228 8bfc 2ec2` | `8c0668a8` / `0x0468a8` / `0x1a30d4` | `8c0668ac` (`60d2`) |
> | **MAPLE-BOOT-D** | `8c066924`–`8c06692f` | `0x046924`–`0x04692f` | `0x1a3150`–`0x1a315b` | `2e72 2572 6252 2228 8bfc 2ec2` | `8c06692c` / `0x04692c` / `0x1a3158` | `8c066930` (`62d2`) |
> | **MAPLE-BOOT-E** | `8c066a5c`–`8c066a67` | `0x046a5c`–`0x046a67` | `0x1a3288`–`0x1a3293` | `2c52 2452 6242 2228 8bfc 2c72` | `8c066a64` / `0x046a64` / `0x1a3290` | `8c066a68` (`d31e`) |
>
> Emitted content, identical at all five (only the literal differs):
>
> ```
> +0x00  d201   mov.l @(0x01,PC),r2   ; r2 = the site's trampoline address
> +0x02  422b   jmp @r2
> +0x04  0009   _nop                  ; delay slot
> +0x06  0009   (pad; unreachable — B has no pad, its literal starts here)
> +0x08  <32-bit trampoline address>  ; 4-aligned by construction
> ```
>
> `((window_start + 4) & ~3) + 0x01 * 4` lands exactly on the literal slot at
> every site — verified per row above. B is 10 bytes with no pad because its
> window starts 2-mod-4; the other four are 12.
>
> **Hook kind: `jmp` detour, not `jsr`.** `FUN_8c0665fe`'s prologue
> (`0x8c0665fe`–`0x8c06660c`, byte-verified) saves r8–r14 but **not PR**, so a
> `jsr` in its body would destroy the return address to `0x8c066aea`.
>
> > **Register contract — a mid-body detour is NOT a call, and the C ABI does
> > NOT apply to it.** The driver does not know the detour happened, so **every
> > register must come back unchanged** except the ones the replaced
> > instructions themselves clobbered. Reading the five windows above, the
> > original code clobbers exactly **`r2`** (the poll temp, `mov.l @r5,r2` /
> > `mov.l @r4,r2`) and **`T`** (from `tst r2,r2`) — nothing else; the other
> > four instructions are stores. Therefore the trampoline **must save and
> > restore `r0`, `r1`, `r3`–`r7`, `PR`, and `MACL`/`MACH`** around its call
> > into C (`r8`–`r15` the C ABI preserves for us; `r2` and `T` are free).
> > This is not academic: detour E's resume instruction is
> > `8c066a66 2c72 mov.l r7,@r12` — it **reads r7**, and r7 is caller-saved, so
> > a trampoline that let C clobber it would corrupt the very first instruction
> > the driver executes on return. A–D are the same shape: `r5` is set once
> > (`add #0x4,r5` at `0x8c066632`) and reused by all four kicks, and `r7` = 1
> > throughout, so both are live across A, B and C. Contrast MAPLE-KICK-HOOK
> > above, where the ABI genuinely does apply because that site is a real
> > `jsr` and the game consumes the return value.
>
> **What the shim replays.** The window swallows `SB_MDEN = 1`, the kick, and
> (at A/C/D/E) `SB_MDEN = 0` — all mirror stores. The uniform contract is:
> on return **`mirror[0x14] = 0` and `mirror[0x18] = 0`**. Site B's window ends
> before its `SB_MDEN = 0`, so B's resume instruction writes the same 0 again;
> harmless.
>
> **What the shim owes the boot path beyond these five sites (the R5 fold-in).**
> The Naomi BIOS's own JVS negotiation — everything the `0c03161e` family did
> before `MAINHANDOFF` — has no equivalent on Dreamcast and no code in either
> image to hook. Its observable effect on the game is that by the time
> `FUN_8c066964` runs, the MIE answers device-enumeration subcommands and the
> EEPROM holds valid, free-play settings. The shim must therefore have its
> baked EEPROM image and its MIE reply synthesiser live **before the first game
> maple kick**, not lazily on first use. Cleopatra needed the same thing and
> serviced it separately (`shim_cfg_tx`/`shim_cfg_rx`, "the board reports
> node-count ≥ 1 — required before the game emits the per-frame input poll",
> `../cleopatra/docs/kb/phase4-conversion.md` §C).

### TESTBIT-INJECT

The synthesized JVS word's Test / Service / Coin placement is an ABI question,
not a patch-site question: after MAPLE-KICK-HOOK and the five boot detours,
**every** MIE reply in the game is written by the shim, so there is no game
instruction to patch for it. The offsets are pinned in §Input ABI below —
Test → reply byte `+0x1f` bit 7, Service → reply byte `+0x20` bit 6, Coin →
the counter at `+0x25`/`+0x26`, checksum at `+0x3a` recomputed.

### The full patch table — main image

Anchor column: `MAPLE-BASE`, `MAPLE-BOOT` (boot-driver pools and the boot
register init-pair table, both consumed by MAPLE-BOOT-STRATEGY), `*exempt*`.
Every row is `pool(dat_offset, old, new = MAPLE_MIRROR_P2 + (old & 0xff))`
unless exempted.

| # | `dat_offset` | RAM addr | old u32 | register | anchor | loader instruction(s) |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `0x006b58` | `8c026b58` | `0xa05f6c00` | block base | MAPLE-BASE | `8c026b34` `mov.l @(0x08,PC),r1` |
| 2 | `0x04664c` | `8c06664c` | `0xa05f6c14` | `SB_MDEN` | MAPLE-BOOT | `8c066616` `mov.l @(0x0d,PC),r14` |
| 3 | `0x04678c` | `8c06678c` | `0xa05f6c04` | `SB_MDSTAR` | MAPLE-BOOT | `8c06671e` `mov.l @(0x1b,PC),r0` |
| 4 | `0x04682c` | `8c06682c` | `0xa05f6c04` | `SB_MDSTAR` | MAPLE-BOOT | `8c066808` `mov.l @(0x08,PC),r0` |
| 5 | `0x046958` | `8c066958` | `0xa05f6c04` | `SB_MDSTAR` | MAPLE-BOOT | `8c06689a` `mov.l @(0x2f,PC),r0`, `8c06691e` `mov.l @(0x0e,PC),r0` |
| 6 | `0x046ac0` | `8c066ac0` | `0xa05f6c14` | `SB_MDEN` | MAPLE-BOOT | `8c0669d2` `mov.l @(0x3b,PC),r12` |
| 7 | `0x046ac8` | `8c066ac8` | `0xa05f6c8c` | `SB_MDAPRO` | MAPLE-BOOT | `8c0669d6` `mov.l @(0x3c,PC),r0` |
| 8 | `0x046ad0` | `8c066ad0` | `0xa05f6c80` | `SB_MSYS` | MAPLE-BOOT | `8c0669dc` `mov.l @(0x3c,PC),r3` |
| 9 | `0x046ad4` | `8c066ad4` | `0xa05f6c10` | `SB_MDTSEL` | MAPLE-BOOT | `8c0669e2` `mov.l @(0x3c,PC),r1` |
| 10 | `0x046ad8` | `8c066ad8` | `0xa05f6c04` | `SB_MDSTAR` | MAPLE-BOOT | `8c0669e6` `mov.l @(0x3c,PC),r0`, `8c066a54` `mov.l @(0x20,PC),r2` |
| 11 | `0x046adc` | `8c066adc` | `0xa05f6c18` | `SB_MDST` | MAPLE-BOOT | `8c0669ec` `mov.l @(0x3b,PC),r4` |
| 12 | `0x13c4c8` | `8c15c4c8` | `0xa05f6c04` | `SB_MDSTAR` | MAPLE-BOOT | — (init-pair table entry, no pc-relative loader) |
| 13 | `0x13c4d0` | `8c15c4d0` | `0xa05f6c10` | `SB_MDTSEL` | MAPLE-BOOT | — (same) |
| 14 | `0x13c4d8` | `8c15c4d8` | `0xa05f6c14` | `SB_MDEN` | MAPLE-BOOT | — (same) |
| 15 | `0x13c4e0` | `8c15c4e0` | `0xa05f6c80` | `SB_MSYS` | MAPLE-BOOT | — (same) |
| 16 | `0x13c4e8` | `8c15c4e8` | `0xa05f6c8c` | `SB_MDAPRO` | MAPLE-BOOT | — (same) |
| 17 | `0x13c4f0` | `8c15c4f0` | `0xa05f6ce8` | `SB_MMSEL` | MAPLE-BOOT | — (same) |
| 18 | `0x13c648` | `8c15c648` | `0xa05f6c18` | `SB_MDST` | MAPLE-BOOT | — (same) |
| 19 | `0x13c710` | `8c15c710` | `0xa05f6c04` | `SB_MDSTAR` | *exempt* | — (crash-dump table entry) |
| 20 | `0x13c714` | `8c15c714` | `0xa05f6c10` | `SB_MDTSEL` | *exempt* | — (crash-dump table entry) |

**The nine data-table words (12–20).** They sit in the same two tables
§Cart-patch sites already dissected:

- Entries 12–18 are in the `(register, value)` init-pair list based at
  `0x8c15c3e8` (pointer pool `0x8c02c5e8`), walked by `FUN_8c02c584` —
  `for (p = table; *p != 0; p += 2) *(int *)p[0] = p[1];`. Their paired values,
  byte-verified: `SB_MDSTAR ← 0x0cff0000`, `SB_MDTSEL ← 0`, `SB_MDEN ← 0`,
  `SB_MSYS ← 0xc3500000`, `SB_MDAPRO ← 0x61557f00`, `SB_MMSEL ← 1`,
  `SB_MDST ← 0`. Repointed, they become a free, correct zero-init of the
  mirror — including `mirror[0x18] = 0`, which is the invariant's initial
  state, and `SB_MMSEL = 1`, which §MIE-DESC depends on.
- Entries 19–20 are consecutive words of the flat register-address list based
  at `0x8c15c6c0` (pointer pool `0x8c02c884`) inside `FUN_8c02c5ec`, the serial
  **crash dump** — the same table entries 30–32 of the cart accounting come
  from, reachable only from an exception-vector stub.

> **Exemption (2 words, entries 19–20).** `0x13c710` / `0x13c714` —
> `SB_MDSTAR` / `SB_MDTSEL` in the crash-dump register list. Read-only, from a
> developer trap handler, never from game logic; and **reading** `SB_MDSTAR` /
> `SB_MDTSEL` is side-effect free
> (`../flycast4naomi2dreamcast/core/hw/holly/sb.h:115-119` — plain RW
> registers, and `maple_Init()` registers write handlers only, never a read
> handler, `.../core/hw/maple/maple_if.cpp:410-418`; contrast `SB_MDST`, whose *write* starts the DMA,
> `maple_SB_MDST_Write`, `.../core/hw/maple/maple_if.cpp:98-109`, registered by
> `hollyRegs.setWriteHandler<SB_MDST_addr>` at `maple_if.cpp:412`). Patching
> them would only change which zeros a crash dump prints. Left alone — the same
> disposition, for the same reason, as cart entries 30–32.

### Test image — the same 20 words, the same shape

Scanned with the committed scanner (`--words a05f6c00-a05f6cff`): **20 hits**,
mapping 1:1 onto the main image's 20, in the same order, with the same values
and the same register roles. As with the cart words, MAPLE-BASE is at the *same*
RAM address in both (`0x8c026b58`) and `FUN_8c026b30` is byte-identical; the
boot driver sits `0x157cc` lower in the test image.

| # | `dat_offset` | RAM addr | old u32 | register | anchor | loader instruction(s) |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `0x178b50` | `8c026b58` | `0xa05f6c00` | block base | MAPLE-BASE | `8c026b34` `mov.l @(0x08,PC),r1` |
| 2 | `0x1a2e78` | `8c050e80` | `0xa05f6c14` | `SB_MDEN` | MAPLE-BOOT | `8c050e4a` `mov.l @(0x0d,PC),r14` |
| 3 | `0x1a2fb8` | `8c050fc0` | `0xa05f6c04` | `SB_MDSTAR` | MAPLE-BOOT | `8c050f52` `mov.l @(0x1b,PC),r0` |
| 4 | `0x1a3058` | `8c051060` | `0xa05f6c04` | `SB_MDSTAR` | MAPLE-BOOT | `8c05103c` `mov.l @(0x08,PC),r0` |
| 5 | `0x1a3184` | `8c05118c` | `0xa05f6c04` | `SB_MDSTAR` | MAPLE-BOOT | `8c0510ce` `mov.l @(0x2f,PC),r0`, `8c051152` `mov.l @(0x0e,PC),r0` |
| 6 | `0x1a32ec` | `8c0512f4` | `0xa05f6c14` | `SB_MDEN` | MAPLE-BOOT | `8c051206` `mov.l @(0x3b,PC),r12` |
| 7 | `0x1a32f4` | `8c0512fc` | `0xa05f6c8c` | `SB_MDAPRO` | MAPLE-BOOT | `8c05120a` `mov.l @(0x3c,PC),r0` |
| 8 | `0x1a32fc` | `8c051304` | `0xa05f6c80` | `SB_MSYS` | MAPLE-BOOT | `8c051210` `mov.l @(0x3c,PC),r3` |
| 9 | `0x1a3300` | `8c051308` | `0xa05f6c10` | `SB_MDTSEL` | MAPLE-BOOT | `8c051216` `mov.l @(0x3c,PC),r1` |
| 10 | `0x1a3304` | `8c05130c` | `0xa05f6c04` | `SB_MDSTAR` | MAPLE-BOOT | `8c05121a` `mov.l @(0x3c,PC),r0`, `8c051288` `mov.l @(0x20,PC),r2` |
| 11 | `0x1a3308` | `8c051310` | `0xa05f6c18` | `SB_MDST` | MAPLE-BOOT | `8c051220` `mov.l @(0x3b,PC),r4` |
| 12 | `0x1b22f4` | `8c0602fc` | `0xa05f6c04` | `SB_MDSTAR` | MAPLE-BOOT | — (init-pair table entry) |
| 13 | `0x1b22fc` | `8c060304` | `0xa05f6c10` | `SB_MDTSEL` | MAPLE-BOOT | — (same) |
| 14 | `0x1b2304` | `8c06030c` | `0xa05f6c14` | `SB_MDEN` | MAPLE-BOOT | — (same) |
| 15 | `0x1b230c` | `8c060314` | `0xa05f6c80` | `SB_MSYS` | MAPLE-BOOT | — (same) |
| 16 | `0x1b2314` | `8c06031c` | `0xa05f6c8c` | `SB_MDAPRO` | MAPLE-BOOT | — (same) |
| 17 | `0x1b231c` | `8c060324` | `0xa05f6ce8` | `SB_MMSEL` | MAPLE-BOOT | — (same) |
| 18 | `0x1b2474` | `8c06047c` | `0xa05f6c18` | `SB_MDST` | MAPLE-BOOT | — (same) |
| 19 | `0x1b253c` | `8c060544` | `0xa05f6c04` | `SB_MDSTAR` | *exempt* | — (crash-dump table entry) |
| 20 | `0x1b2540` | `8c060548` | `0xa05f6c10` | `SB_MDTSEL` | *exempt* | — (crash-dump table entry) |

Test-image hook sites: MAPLE-KICK-HOOK's pool is `0x1774b8` (RAM `0x8c0254c0`,
same value `0x8c02a17e`), and the kick region `0x8c02543a`–`0x8c02544c` is
**byte-identical** across the two images (`2802 9027 63e2 023e d31f 430b 12c6
d21e 2202 9027`); only the two link-dependent pool values differ
(`[0x8c0254c4]` = `0x8c19268c` main / `0x8c06e2d4` test; the base-ptr cell
`[0x8c025364]` = `[0x8c026b4c]` = `0x8c1938dc` main / `0x8c06f524` test — both
outside the image, so neither is patched). The five boot detour windows are
byte-identical too, listed in the MAPLE-BOOT-STRATEGY table above.

### Completeness accounting

| | main | test |
| --- | --- | --- |
| Words with phys in `0x5f6c00`–`0x5f6cff` (raw scan) | 20 | 20 |
| … covered by the MAPLE-BASE repoint (entry 1) | 1 | 1 |
| … own `pool()` patch entries (2–18) | 17 | 17 |
| … written exemptions (19–20) | 2 | 2 |
| Hooks (1 fn-ptr pool + 5 detours) | 6 | 6 |
| `tools/mmio-xrefs.txt` hits in this range | 11 | n/a |
| … of those, unaccounted for | **0** | — |
| Naomi-BIOS maple sites (R5) | 0 — not in either image | 0 |

The 11 `mmio-xrefs.txt` lines in range (`:52` `0x8c026b58`; `:66`–`:69`
`0x8c06664c`/`0x8c06678c`/`0x8c06682c`/`0x8c066958`; `:71`–`:76`
`0x8c066ac0`–`0x8c066adc`) are entries 1–11 — all present. The other 9 raw-scan
words are the two data tables, invisible to `FindMmioXrefs` for the reasons
`docs/kb/boot-binary.md` §Coverage limits gives. Independently confirmed with
`ListPoolWords.java 0x005f6c00 0x005f6d00`, which reports the same 20 addresses
and attributes all 11 code pools to `FUN_8c026b30`, `FUN_8c0665fe` and
`FUN_8c066964` and none to any other function — i.e. **there is no third maple
driver in either image**, which is what makes the R5 verdict (the third
*observed* driver is the BIOS) the only remaining explanation.

As with the cart path, the steady maple path contributes **zero** whole-address
constants — its registers are all `base->[0x10f4] + disp` — which is why entry 1
alone carries it.

### Residual risks — for Task 9/10/11 to close, not silently inherit

1. **Interrupt-side completion is not modelled.** Real Holly raises
   `holly_MAPLE_DMA` on completion (`maple_if.cpp:391`). Nothing in
   `FUN_8c02532a` or the boot driver reads `SB_ISTNRM` on the maple path in the
   decompiles above — both use the `SB_MDST`-reads-0 test — but the ASIC
   interrupt block (`0x005f6900`–`0x005f690c`) is outside both mirrors and was
   never scanned. `0xa05f6908` does appear as a literal at 8 addresses in the
   main image. On Dreamcast those registers exist at the same addresses with
   the same semantics, so an unmirrored access is harmless *if* the shim also
   raises the maple-DMA interrupt when the game expects it. Cheapest check:
   Task 10's dry run with the real maple registers watched.
2. **`FUN_8c02532a`'s `SB_MSYS` write is computed, not constant.**
   `SB_MSYS = base->[0x10c0] | base->[0x10d0]`, where `[0x10c0]` is either
   `0xc3500000` (`[0x8c0254b8]`, byte-verified) or a TMU-derived value shifted
   left 16. It lands in the mirror either way, but a shim that *reads* mirror
   `+0x80` expecting the init-table constant `0xc3500000` will sometimes see
   something else.
3. **The five boot kicks were observed 345 times in `pc2.log` and 1035 times in
   the Phase 3 leg — they are a hot path, not insurance.** Unlike
   CART-BOOT-DMA, getting MAPLE-BOOT wrong hangs the boot, visibly and
   immediately. That is the good failure mode, but it means the five detours
   must be in the very first patched build, not deferred.
4. **The BIOS's pre-handoff JVS state is inferred, not enumerated.** R5 proves
   *who* did it; it does not enumerate *what* the BIOS left behind that the
   game depends on. The observable surface is the EEPROM contents (§Input ABI)
   and the MIE's willingness to answer enumeration subcommands. Cleopatra
   needed one extra forcing patch here (I/O-spec check, node count); senkosp
   may too, and that is a Task 11/12 discovery, not something this scan can
   close.

### Reproduction

```sh
# 1. raw word scan of both load entries (the completeness bar)
python3 scripts/scan_dat_constants.py senkosp.dat --range 0x0:0x171ff8 \
        --words a05f6c00-a05f6cff                      # 20 hits
python3 scripts/scan_dat_constants.py senkosp.dat --range 0x171ff8:0x1bfc38 \
        --words a05f6c00-a05f6cff                      # 20 hits

# 2. old-value + loader-instruction verification, straight from the image
#    (same generator as §Cart-patch sites §Reproduction step 2, with the
#     range 0x5f6c00..0x5f6cff)

# 3. semantics (Ghidra 12.1.2 headless, program senkosp3 — docs/kb/tooling.md §Ghidra)
scripts/ghidra/run.sh script ListPoolWords.java 0x005f6c00 0x005f6d00
scripts/ghidra/run.sh script Decomp.java 0x8c026b30 0x8c02532a 0x8c0665fe \
        0x8c066964 0x8c02a17e 0x8c026b26 0x8c02d638
scripts/ghidra/run.sh script DisasmRange.java 0x8c026b30 0x8c026b60
scripts/ghidra/run.sh script DisasmRange.java 0x8c025400 0x8c025480
scripts/ghidra/run.sh script DisasmRange.java 0x8c02532a 0x8c025400
scripts/ghidra/run.sh script DisasmRange.java 0x8c066964 0x8c066a70
scripts/ghidra/run.sh script FindRefsTo.java 0x8c0254c0 0x8c0254c4 0x8c026b58

# 4. R5 — the BIOS/game split, straight from the capture
python3 - <<'EOF'
import re
H = None
fam = {}
for i, l in enumerate(open("captures/phase4/pc2.log", errors="ignore"), 1):
    if l.startswith("MAINHANDOFF"):
        H = i
    if l.startswith("MDODMA enter") or l.startswith("PCSAMPLE") or l.startswith("SOFWR"):
        m = re.search(r"pc=([0-9a-f]+)", l)
        if m:
            fam.setdefault((l.split()[0], m.group(1)[:4]), [0, 0])[H is not None] += 1
print("MAINHANDOFF at line", H)
for k in sorted(fam):
    print(k, "pre=%d post=%d" % tuple(fam[k]))       # every 0c.. is pre, every 8c.. is post
EOF

# 5. R5 evidence 3 -- no page mapping puts those PCs after a store in this image
python3 - <<'EOF'
import struct
img = open("tools/boot.bin", "rb").read()
B = 0x0c020000                      # physical base of the loaded main image
stores = [0x0c03161c, 0x0c03179c, 0x0c03185a, 0x0c031c7e, 0x0c031f34, 0x0c03204a]
def is_store(h):                    # SH-4 store forms that can write SB_MDST
    t = h >> 12
    return ((t == 2 and (h & 0xf) in (0, 1, 2, 4, 5, 6)) or t == 1
            or (t == 0 and (h & 0xf) in (4, 5, 6))
            or (t == 8 and ((h >> 8) & 0xf) in (0, 1))
            or (t == 0xc and ((h >> 8) & 0xf) in (0, 1, 2)))
def hw(a):
    o = a - B
    return None if o < 0 or o + 1 >= len(img) else struct.unpack_from("<H", img, o)[0]
for shift, name in ((10, "1K"), (12, "4K"), (16, "64K"), (20, "1M")):
    hits = [D for D in range(-0x2000000, 0x2000000, 1 << shift)
            if all((h := hw(s - D)) is not None and is_store(h) for s in stores)]
    print(name, "page: candidate deltas:", [hex(d) for d in hits])   # all empty
EOF
```

## Input ABI — spec pin P4

**Question:** what byte stream must `shim_maple_service` synthesize for each
MIE subcommand, and where in it do senkosp's controls, the Test/Service bits
and the JVS checksum live?

### The frame is the same one Cleopatra decoded

senkosp's steady-state has-data reply, taken verbatim from a post-handoff
`MIERESP sub=33` line in `captures/phase4/pc2.log` (all idle, 15 800 of them in
the leg):

```
8700200f 16 ffffff 00ffffff 00000000 00000000 0000 8e 01 00 21
e0 00 1e 01 01 00 0000 0000 01 00000000 01 8000 8000 8000 8000
8000 8000 8000 8000 22 00 87002001
```

It is **byte-for-byte** the frame `../cleopatra/docs/kb/phase4-conversion.md`
§input-ABI decoded, which is expected: both games talk to the same emulated
MIE, so the emitter is the same code. Offsets, re-verified against **this**
fork:

| off | bytes | meaning | emitter (`../flycast4naomi2dreamcast/core/hw/maple/maple_jvs.cpp`) |
| --- | --- | --- | --- |
| `0x00` | `87 00 20 0f` | maple reply header, `0x0f` words | `reply()`, `:1726` |
| `0x04` | `16` | subresp `0x16` = has JVS data (`0x32` = cold/no scan) | `:1727` (`:1723` cold) |
| `0x05` | `ff ff ff` | placeholder | `:1729-1731` |
| `0x08` | `00 ff ff ff` | `w32(0xffffff00)` | `:1732` |
| `0x0c` | `00 ×8` | `w32(0) ×2` | `:1733-1734` |
| `0x14` | `00 00 8e` | 0, channel, sense line | — |
| `0x17` | `01 00 21` | node 1, status ok, out length `0x21` | — |
| `0x1a` | `e0 00 1e` | JVS sync, master node id, length | `:2095-2096` |
| `0x1d` | `01` | overall status | `JVS_STATUS1()`, `:2231` |
| `0x1e` | `01` | report byte — cmd `0x20` digital read | `:2238` |
| **`0x1f`** | `00` | **TEST byte** — `(inputs[0] & NAOMI_TEST_KEY) ? 0x80 : 0x00` | **`:2243`** |
| **`0x20`** | `00 00` | **P1 buttons, hi then lo** (big-endian) | **`:2248`, `:2252`** |
| `0x22` | `00 00` | P2 buttons, hi then lo (same loop, `player = 1`) | `:2245-2253` |
| `0x24` | `01` | report byte — cmd `0x21` read coins | `:2261` |
| **`0x25`** | `00 00` | **coin slot 1**: `(count >> 8) & 0x3f` then `count` | **`:2276-2278`** |
| `0x27` | `00 00` | coin slot 2 | same loop |
| `0x29` | `01` | report byte — cmd `0x22` read analog | — |
| `0x2a` | `80 00` ×8 | 8 analog channels, idle `0x8000` | — |
| **`0x3a`** | `22` | **JVS checksum** | **`:2487-2491`** |

### Checksum rule

`calc_crc = Σ buffer_out[1 … length-1] & 0xff` (`:2487-2489`), and
`buffer_out[0]` is the `0xE0` sync at frame offset `0x1a`. In frame
coordinates:

> **`frame[0x3a] = (Σ frame[0x1b … 0x39]) & 0xff`, recomputed whenever any
> button, Test or coin byte changes.**

Verified arithmetically on the observed idle frame: `0x1e + 0x01 + 0x01 + 0x01
+ 0x01 + 8 × 0x80 = 0x422`, `& 0xff = 0x22` = the logged byte.

### Where senkosp's controls land

`docs/kb/input-map.md` has the measured JVS word for every control; combined
with the offsets above:

| control | JVS word bit | frame byte | bit |
| --- | --- | --- | --- |
| Start | `0x8000` | `0x20` | 7 |
| **Service** | `0x4000` | `0x20` | **6** |
| Up / Down / Left / Right | `0x2000`/`0x1000`/`0x0800`/`0x0400` | `0x20` | 5 / 4 / 3 / 2 |
| M (Main) / S (Sub) | `0x0200` / `0x0100` | `0x20` | 1 / 0 |
| Barrage | `0x0080` | `0x21` | 7 |
| A (Action) | `0x0040` | `0x21` | 6 |
| OverDrive | `0x0020` | `0x21` | 5 |
| **Test** | `1 << 18` (`NAOMI_TEST_KEY`, `maple_devs.h:97`) | `0x1f` | **7** |
| **Coin** | `1 << 19` (`NAOMI_COIN_KEY`, `maple_devs.h:98`) | `0x25`/`0x26` | counter, not a bit |

P2 is the same layout at `0x22`/`0x23`. Active-high, idle `0x0000`
(`docs/kb/input-map.md`). Note that eight of senkosp's nine game controls sit
in the **hi** byte `0x20`; only Barrage, Action and OverDrive are in `0x21`.

> **TESTBIT-INJECT verdict.** Test is **not** a bit of the button word — it is
> bit 7 of its own byte at frame `+0x1f` (`maple_jvs.cpp:2243`), and Coin is
> **not** a bit at all but an increment of the 16-bit slot-1 counter at
> `+0x25`/`+0x26` with the top two bits reserved for slot status
> (`:2276-2278`). Service *is* a bit: `0x4000` → byte `+0x20` bit 6. All three
> require the `+0x3a` checksum to be recomputed. A shim that sets `1 << 18` or
> `1 << 19` somewhere in a 16-bit word would be silently wrong.

### EEPROM replies

Sub `0x03` (read) returns a `0x20`-word maple reply whose 128-byte EEPROM image
starts at frame offset **`0x04`** — `reply(MDRS_JVSReply, sizeof(eeprom) / 4)`
then `memcpy(dma_buffer_out, eeprom + address, size)`
(`maple_jvs.cpp:1931-1940`); sub `0x01` is a 1-word ack (`87 00 20 01 02 …`),
and sub `0x0b` (write) replies with the first 4 EEPROM bytes (`:1899`,
`:1924-1927`). senkosp's own game-era sub-`0x03` reply, from `pc2.log`:

```
87002020 9d6e 1042 4d50 3009 101a 01010100 11111111
         9d6e 1042 4d50 3009 101a 01010100 11111111
         1c1e1010 1c1e1010 23511703 00010102 0200
```

Two identical 18-byte system copies at `0x04` and `0x16` (the dual-CRC layout),
then the game section. The coin/credit byte is at `0x0d` (and `0x1f` in the
second copy) and reads **`0x1a`** — the value Cleopatra decoded as free-play
(`../cleopatra/docs/kb/phase4-conversion.md` §input-ABI, citing
`tools/netboot/docs/naomi.md:180`; second-hand here, confirm when Task 11 bakes
the image). So the shim's baked EEPROM can be built from this observed frame:
it is already a valid, free-play, correct-serial image for this board, and it
is the only EEPROM state senkosp was ever seen to read.

Sub `0x0b` (write) never has to persist anything: the only writer observed in
this project is the Naomi BIOS (§R5), which does not exist on the target. Ack
it and drop the payload.

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
8c0278a8  add r14,r1               ; r1 = obj + 0x58
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

### CART-WAIT — three entry hooks and one invariant

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

Three entry hooks, and why each is needed:

| Hook | `dat_offset` (main / test) | Function | Contract | Why |
| --- | --- | --- | --- | --- |
| **CART-WAIT-A** | `0x007e5e` / `0x179e56` | `FUN_8c027e5e` | wait for DMA completion | the steady-path completion wait; where the service runs |
| **CART-WAIT-B** | `0x007e34` / `0x179e2c` | `FUN_8c027e34` | settle/abort | `FUN_8c027d7e` kicks and returns without waiting; if this runs first its inner `while (GDST & 1)` spins on RAM forever |
| **CART-BOOT-DMA** | `0x046440` / `0x1a2c6c` | boot cart DMA (below) | blocking cart read | it sets *and then polls* the mirrored `SB_GDST` itself |

A single shim helper (`shim_cart_service` per the spec) satisfies all three:
service whatever the mirror describes, then clear `mirror[0x418]`.
CART-WAIT-B and CART-BOOT-DMA degenerate to "nothing pending → return".

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

```
8c027d86  mov #0x74,r0 ; 8c027d8c mov.l @(r0,r14),r2 ; 8c027d8e mov.l @(0x4,r13),r3
8c027d90  cmp/hs r3,r2 ; bf 8c027d9e                   ; fail if obj->[0x74] < desc[1]
8c027da4  mov.w 0x8c027e04,r3   ; +0x4b8  SB_GDAPRO  <- 0x8843407f (pool 0x8c027e30)
8c027db0  mov.w 0x8c027e06,r2   ; +0x404  SB_GDSTAR  <- desc[0]   (mov.l @r13,r3)
8c027dba  mov.w 0x8c027e08,r3   ; +0x408  SB_GDLEN   <- desc[1]   (mov.l @(0x4,r13),r2)
8c027dc8  mov.w 0x8c027e0a,r2   ; r2 = 0x040c
8c027dcc  mov.l r4,@r1          ; +0x40c  SB_GDDIR   <- 1  (r4 = 1, set at 8c027dc6)
8c027dd6  mov.w 0x8c027e0c,r3   ; r3 = 0x0414
8c027dd8  mov.l r1,@(r0,r14)    ;         obj->[0x74] -= desc[1]
8c027dde  add r3,r0             ; r0 = base + 0x414
8c027de0  mov.l r4,@r0          ; +0x414  SB_GDEN    <- 1
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
8c0663ea  mov.l r3,@r2          ; <- offset & 0xffff        (extu.w r4,r3)
8c0663f8  mov.l 0x8c06642c,r3   ; r3 = 0xa05f7000  NAOMI_ROM_OFFSETH
8c0663fe  mov.l r4,@r3          ; <- ((offset & 0xffff0000) >> 16)
                                ;    | *(u32 *)0x8c1bf18c | 0x00008000
8c066400  mov.l 0x8c06643c,r4   ; r4 = 0xa05f7008  NAOMI_ROM_DATA
8c066406  mov.l @r4,r2          ; <== the PIO read
8c066408  mov.w r2,@r5          ; store 16 bits, r5 += 2, repeat r6 times
```

(mask `0xffff0000` = pool `0x8c066434`, mode bit `0x00008000` = pool
`0x8c066438`, base pointer `0x8c1bf18c` = pool `0x8c066428`; all four
byte-verified.)

Its three pool words are entries 11/12/13 — repointed like the rest, so a PIO
read lands in the mirror and the shim serves it from `NAOMI_ROM_OFFSETH/L`.
This matches the Phase 2 streaming map — *"1,590 unique DMA tuples + 2 PIO
seeks"* over the whole merged campaign (`docs/kb/cart-streaming-map.md:12`,
`:78`): PIO is a boot-time path only, and the steady path is pure DMA.

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
> §Target: cart-read function), so the hook is insurance, not a hot path.

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
> the transfer, `.../core/hw/naomi/naomi.cpp:452-470`). Patching them would
> only change which zeros a crash dump prints. Left alone.

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

Test-image hook sites, same three functions:

| Hook | test `dat_offset` | test RAM | evidence |
| --- | --- | --- | --- |
| CART-WAIT-A | `0x179e56` | `8c027e5e` | body bytes identical to main `0x007e5e` |
| CART-WAIT-B | `0x179e2c` | `8c027e34` | body bytes identical to main `0x007e34` |
| CART-BOOT-DMA | `0x1a2c6c` | `8c050c74` | prologue `2fe6 7ffc`; body `0x1a2c6c`–`0x1a2ce0` byte-identical to main `0x046440`–`0x0464b4` |

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
Reproduce with `--words a05f6c00-a05f6cff`.

### Completeness accounting

| | main | test |
| --- | --- | --- |
| Words with phys in `0x5f7000`–`0x5f77ff` (raw scan) | 32 | 32 |
| … covered by the CART-BASE repoint (entry 1) | 1 | 1 |
| … own `pool()` patch entries (2–29) | 28 | 28 |
| … written exemptions (30–32) | 3 | 3 |
| Entry hooks | 3 | 3 |
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

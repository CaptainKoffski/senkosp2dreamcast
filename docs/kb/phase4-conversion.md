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

### Verdict — **CLEAN** (upgraded from PARTIAL, 2026-08-23)

**Covered, regime (a):** boot → attract (unattended, ~660 s, dynarec ON) —
`shim_home_clean: PASS`, zero `SHIMWATCH2` lines (leg `shimwatch`, above).

**Covered, regimes (b)+(c): operator leg `phase4/shimwatch-play`
(2026-08-23).** Naomi profile, instrumented Flycast, dynarec ON. The
operator's **first** launch of this leg crashed (a known Flycast flake, not
a shim/game fault — no `.log` was produced by that attempt, nothing to
parse or distrust); the landed `captures/phase4/shimwatch-play.log`
(17 MB, 458,748 lines) is the **second, clean** run. Sanity-checked for
completeness before trusting it: starts with the standard SH-4 reset-vector
boot ladder (`MMUCRWR pc=a0000018` / `pc=a0000440` at lines 1–2), carries
exactly one `MAINHANDOFF` (line 10,928 — a single boot, no mid-log
crash-restart), and ends on a well-formed, in-sequence `MDODMA
enter/rawdma_call/rawdma_ret/frame_done` block immediately followed by a
normal `TAREG`/`TAEND`/`C2D` render triplet — i.e. the capture ends at a
clean quit, not mid-line or mid-transaction. 564 `CARTDMA` events / 26.0 MB
streamed (vs. the attract-only leg's 205 events / 31.9 MB — more
*transactions*, mostly small, consistent with menu/UI assets rather than
attract's larger stage loads) and 33 `WATERMARK region=main` sample ticks
(~330 s of coverage at the ~10 s cadence) — enough ticks to cover a played
match plus a test-menu visit, per the operator's own leg (a full match +
test-menu visit + quit, per the brief).

```
$ python3 scripts/parse_cartlog.py captures/phase4/shimwatch-play.log
...
CHECK no_bios_exec: PASS — 0 BIOSEXEC lines (expect 0)
CHECK shim_home_clean: PASS — 0 SHIMWATCH2 lines (expect 0)
```

**Merged, both legs together (the doc's own reproduction command, run
verbatim):**

```
$ python3 scripts/parse_cartlog.py captures/phase4/shimwatch*.log
== per leg ==
shimwatch-play: 282 DMA events, 26001408 B, pio_bytes=0x172a78, main_hw=0x1fe7520
shimwatch: 205 DMA events, 31858688 B, pio_bytes=0x172538, main_hw=0x1fe7520
== merged ==
unique DMA tuples: 349  PIO seeks: 1
...
CHECK shim_home_clean: PASS — 0 SHIMWATCH2 lines (expect 0)
```
exit=0. `cd scripts && python3 test_parse_cartlog.py` → `ok` (incl. its own
`shim_home_clean self-check`).

**Every later Phase 4 task's CLEAN assumption is now positive evidence, not
absence of evidence.** Zero bytes in `0x8c010000`–`0x8c018000` changed from
baseline across attract, a full played 1P match, and a test-menu visit —
the three regimes the brief's step 4 called for are all covered. The
`shimwatch-play` leg additionally logged **0 `MIERESP sub=0b`** (EEPROM
write) events — this particular operator session didn't change a setting
during its test-menu visit (see §Operator legs — gate closure below,
`pc2-testmenu`, for why that's the expected shape, not a coverage gap) —
so O1's CLEAN verdict rests on the write-watch content scan itself, not on
incidentally having also caught an EEPROM write-back in flight.
Sampling caveat (verbatim from V2, reused above) still applies: a write
fully reverted between two 64-DMA samples would evade the scan. The
fallback (heap-top carve + dry-run re-campaign) is not needed.

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
8c0669e8  mov.l @r14,r2            ; 62e2  r2 = *(0x8c1bfe6c), the command list
8c0669ea  mov.l r2,@r0             ;   -> SB_MDSTAR
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
8c066724 / 8c06680e / 8c0668a0 / 8c066924   2e72   mov.l r7,@r14  ; SB_MDEN <- 1
       +2                                   2572   mov.l r7,@r5   ; SB_MDST <- 1
       +4                                   6252   mov.l @r5,r2   \
       +6                                   2228   tst r2,r2       |  the poll
       +8                                   8bfc   bf (-4)        /
       +10                                  2ec2   mov.l r12,@r14 ; SB_MDEN <- 0
```

Those bounds — `SB_MDEN = 1` through the poll — are the detour window chosen
below; the table under MAPLE-BOOT-STRATEGY is authoritative for each site's
exact extent (B stops at `+8`, its `SB_MDEN <- 0` survives).

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
> > This is not academic. `r7` is set once, `mov #0x1,r7` at `0x8c066618`, and
> > `r5` once, `add #0x4,r5` at `0x8c066632`; both are then reused by all four
> > `FUN_8c0665fe` kicks, so both are live **across** windows A, B and C.
> > Byte-verified example just past window C (which resumes at `0x8c0668ac`):
> > `8c0668ac 60d2` / `8c0668ae 6002` / `8c0668b0 88ff` / `8c0668b2 8900` /
> > **`8c0668b4 6b73 mov r7,r11`** — nothing in between writes r7, so that
> > `mov` **reads a caller-saved register the trampoline must have preserved**;
> > it is byte-identical in the test image at `0x8c0510e8`. A trampoline that
> > let C clobber r7 would corrupt it. Contrast MAPLE-KICK-HOOK
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

---

## Restart stub — spec pin P5

**Question (spec `2026-08-22-phase4-conversion-design.md` §Open questions,
P5: "the restart stub's location in the test image"; plan §Patch table &
build system: "restart-stub jump → reboot (locate in both images — the
stub's offset fits inside the test load; plan pin P5)"; task brief
`.superpowers/sdd/2026-08-22-phase4-conversion/task-5-brief.md`):** where do
both images' copies of `FUN_8c067e18` (`docs/kb/relocation-map.md
§Deliberately not patched` — copies `0x60c` B from `0x8c180904` to
`0xadfff000` via pool `0x8c067e3c`, then jumps to `0x8dfff000` via pool
`0x8c067e4c`, which is a Naomi-BIOS re-entry that "is not there" on DC) put
the one word Phase 4 must own to turn "restart" into a DC reboot?

### Main image — old value verified

```
main pool 0x8c067e3c (dest ptr)   -> dat 0x47e3c = 0xadfff000
main pool 0x8c067e4c (jump target) -> dat 0x47e4c = 0x8dfff000
```

Both read byte-for-byte out of `senkosp.dat` (`struct.unpack_from("<I", d,
0x47e3c/0x47e4c)`). `0x47e4c`'s value matches the brief's expected old value
exactly.

### Test image — the brief's needle search failed; a refined search found it

The brief's literal check (`d.find(needle, 0x171ff8, 0x1bfc38)` with
`needle = d[0x47e18:0x47e58]`, the 64-byte main-image stub head) returned
**`NOT FOUND`**. Snippet assumption that failed: the needle bakes in two
`mov.l @(disp,PC),Rn` loader instructions whose displacement encodes the
pool's position *relative to the loading instruction* — those two bytes
necessarily change when the function is relocated to a different address, so
a byte-identical 64-byte needle can never match a relocated copy even when
every pool *value* and every other opcode is identical.

Adapted method: search shrinking sub-chunks of the needle inside the test
range. A 32-byte prefix (`d[0x47e18:0x47e38]`) hit at **dat `0x1a4644`**
(the head of the function, before the first pool word). Growing a full-word
comparison from there (`struct.unpack_from` over the same index offsets used
for the main image) gives:

| word (idx from head) | role | main (dat `0x47e18`+idx) | test (dat `0x1a4644`+idx) | same? |
| --- | --- | --- | --- | --- |
| `0x1c` | `mov.w`/length insn, contains `0x060c` | `0x060c4f26` | `0x060c4f26` | same |
| `0x20` | source ptr (copy-from) | `0x8c180904` (dat `0x47e38`) | `0x8c06a004` (dat `0x1a4664`) | **differs** — each image's own copy of the `0x60c`-B payload, at its own address |
| `0x24` | dest ptr (pool `…e3c`) | `0xadfff000` (dat `0x47e3c`) | `0xadfff000` (dat **`0x1a4668`**) | **same** |
| `0x28` | fn ptr (memcpy-helper call target) | `0x8c069754` | `0x8c053ec4` (dat `0x1a466c`) | differs — shared helper linked at a different address in the smaller test build |
| `0x2c` | P1→P2 OR-mask constant | `0xa0000000` | `0xa0000000` | same |
| `0x30` | fn ptr (icache-flush-ish call target) | `0x8c02b320` | `0x8c02b208` (dat `0x1a4674`) | differs — same reason as `0x28` |
| `0x34` | **jump target (pool `…e4c`)** | `0x8dfff000` (dat `0x47e4c`) | `0x8dfff000` (dat **`0x1a4678`**) | **same** |
| `0x38` | first body instruction after the pool | `0xe500d26b` | `0xe500d26b` | same |

**Every opcode byte is identical between the two images except the four
words that legitimately vary with relocation** (two image-relative data
pointers, two called-function addresses); the two words that matter for
Phase 4 — the copy destination and the jump target — are **the same
physical-page constants in both images**, because they are fixed absolute
RAM addresses, not PC-relative or link-time values. **The test image does
have the stub** (P5 answered: it is *not* absent, it is a relocated
byte-identical copy), so the "test-exit path must be re-derived from its own
exit code" fallback in the brief does not apply.

> **Test-image stub location.** `FUN_8c067e18`'s test-image twin starts at
> dat `0x1a4644` (RAM `0x8c05264c`, via `dat_offset = 0x171ff8 + (addr −
> 0x8c020000)`, `docs/kb/game.md` §Parsed `.dat` header). Its jump-target
> pool word is at dat `0x1a4678` (RAM `0x8c052680`), old value `0x8dfff000`
> — byte-verified.

### `0x8c067e3c` (dest pool) — value and role, and why patching only `…e4c` suffices

Disassembled the full head of the main-image function
(`scripts/ghidra/run.sh script DisasmRange.java 0x8c067e18 0x8c067e80 force`,
program `senkosp3`; verbatim, PR/delay-slot markers as emitted):

```
8c067e18  sts.l PR,@-r15
8c067e1a  mov.l 0x8c067e3c,r4      ; r4 = 0xadfff000  (dest ptr)
8c067e1c  mov.l 0x8c067e40,r3      ; r3 = 0x8c069754   (fn ptr)
8c067e1e  mov.w 0x8c067e36,r6      ; r6 = 0x060c        (byte count)
8c067e20  mov.l 0x8c067e38,r5      ; r5 = 0x8c180904   (source ptr)
8c067e22  jsr @r3                  ; CALL #1 — copies 0x60c B, 0x8c180904 -> 0xadfff000
8c067e24  _nop
8c067e26  mov.l 0x8c067e48,r2      ; r2 = 0x8c02b320
8c067e28  mov.l 0x8c067e44,r3      ; r3 = 0xa0000000
8c067e2a  or r3,r2                 ; r2 = 0xac02b320   (P2 alias of 0x8c02b320)
8c067e2c  jsr @r2                  ; CALL #2 — via the P2 (uncached) alias, before the jump
8c067e2e  _nop
8c067e30  mov.l 0x8c067e4c,r1      ; r1 = 0x8dfff000   (jump target)   <== ONLY use of pool "…e4c"
8c067e32  jmp @r1                  ; THE escape — unconditional, no other branch in the function
8c067e34  _lds.l @r15+,PR          ; delay slot
```

**This is decisive.** `FUN_8c067e18` contains exactly **one** unconditional
control-transfer instruction — the `jmp @r1` at `8c067e32` — and `r1` is
loaded from pool `0x8c067e4c` in the immediately preceding instruction, with nothing between
the load and the jump that could redirect it. `0x8c067e3c` (loaded into `r4`
at entry) is consumed only as an *argument* to `CALL #1` (the memcpy-style
helper) and never referenced again; it has no bearing on where control ends
up. **Patching only `0x47e4c`/`0x1a4678` (main/test) is sufficient**: the
memcpy (`CALL #1`, using the `…e3c` dest ptr) and the P2-aliased helper call
(`CALL #2`) still run — harmless leftover writes into the fixed physical
page `0x0dfff000`, already flagged acceptable in `relocation-map.md`
("acceptable only because the path is a reboot anyway") — but the jump
itself lands wherever the patched `…e4c`/`0x1a4678` word points, so the
Naomi-BIOS re-entry (`0xa0082262` etc., baked *inside* the copied `0x60c`-B
payload, never reached once the jump is redirected) is never executed. The
same reasoning applies unchanged to the test image: its opcode bytes at
`8c05264c`–`8c052688` (dat `0x1a4644`–`0x1a4680`) are byte-identical to the
main image's at this span except the four relocation-dependent pool words
already tabulated, so its control-flow shape — one `jsr`, one `jsr`, one
`jmp` through the same relative pool slot — is identical.

### RESET-PATCH — pin

> **RESET-PATCH.** Two entries, one per image, `new` symbolic (Task 9/10
> compute the shim reboot routine's literal address; kept symbolic here so
> the two can never drift, same convention as §Cart-patch sites'
> `G1_MIRROR_P2`):
>
> | image | dat_offset | old (verified) | new |
> | --- | --- | --- | --- |
> | main | `0x47e4c` | `0x8dfff000` | `SHIM_REBOOT_ENTRY` |
> | test | `0x1a4678` | `0x8dfff000` | `SHIM_REBOOT_ENTRY` |
>
> Both `old` values byte-identical — the physical landing page is shared
> between images, so both patches target the same conceptual "restart"
> escape hatch with the same literal `new` once Task 10 defines it.
> `0x8c067e3c`/its test-image twin at dat `0x1a4668` (both `0xadfff000`,
> both **not** patched) are recorded for completeness: they are the copy
> destination, consumed only by `CALL #1`, never by the jump.

### Residual risks — for Task 9/10 to close, not silently inherit

`CALL #1` (pool `…e40`, `0x8c069754` main / `0x8c053ec4` test) and `CALL #2`
(pool `…e48` OR'd with the P2 mask, `0x8c02b320` main / `0x8c02b208` test —
see the word table above) were identified only by their *role in the
control flow* (a memcpy-shaped call, then a P2-aliased call right before the
jump) — their own bodies were not disassembled or decompiled. This task's
claim that both are side-effect-only (memcpy into a fixed unused page,
icache-flush-shaped) is inferred from the calling convention and from
`relocation-map.md`'s prior finding, not independently proven per-instruction.
If Task 10's shim reboot routine turns out to be reached with caches or
memory state that behaves unexpectedly, decompiling these two callees is the
first thing to check.

### Reproduction

```
python3 - <<'EOF'
import struct
d = open("senkosp.dat","rb").read()
main_stub, test_stub = 0x47e18, 0x1a4644
def w32(base, idx): return struct.unpack_from("<I", d, base+idx)[0]
assert w32(main_stub, 0x24) == 0xadfff000 and w32(main_stub, 0x34) == 0x8dfff000
assert w32(test_stub, 0x24) == 0xadfff000 and w32(test_stub, 0x34) == 0x8dfff000
print("RESET-PATCH pins verified: main dat 0x47e4c, test dat 0x1a4678, both old=0x8dfff000")
EOF
```

---

## Low-RAM placements — spec pin P6 (KERNEL-SLICE), BLOB-CHECK

**Question (plan Task 5: "kernel slice (P6), blob sanity"; spec §RAM map:
`0x8c000600`–`0x8c007xxx` "Naomi RTOS kernel slice from the user's BIOS
dump (byte-identity recipe: `tooling.md` §Phase 3: RAM snapshot)"; task
brief):** exactly which BIOS-ROM (and, where ROM has no source, snapshot)
bytes does the loader `dd` into `0x8c000600` so that the placed image
matches what a real Naomi BIOS boot leaves there — and does the pre-placed
`0x60000` BIOS blob's own internal vector table ever point into the shim's
home window?

### KERNEL-SLICE — run bounds

Grew the identical run from the anchor exactly as specified
(`tools/ram-snapshot.bin` vs `bios/naomi/epr-21576h.ic27`, identity
`ROM_off = RAM_off − 0x800`, anchor RAM `0x1004` = ROM `0x804`,
`docs/kb/tooling.md` §Phase 3: RAM snapshot):

```
identical run: RAM 0x1000 - 0x3800  ROM 0x800 - 0x3000
0x600-0x800 in ROM at: -0x1
```

**The run is shorter than the spec's rough `0x8c007xxx` upper bound, and it
does not reach down to the RAM-`0x800` floor either — both ends investigated
byte-by-byte before pinning anything (the brief's escalation trigger:
"identical-run comes out surprisingly short"):**

- **Low end (RAM `0x800`–`0x1000`, 0x800 B): snapshot is all-zero.**
  `ram[0x800:0x1000]` — 2048/2048 bytes zero, verified
  (`all(b==0 for b in ram[0x800:0x1000])` → `True`). This is not a broken
  identity; it is simply RAM the resident kernel had not written by
  snapshot time (post-`~150s`-attract, per `tooling.md`'s capture
  provenance) — the loader reproduces it by leaving it zeroed, which is the
  no-op the ROM comparison was never going to give a "match" for anyway
  (ROM's corresponding bytes at `0x0`–`0x800` are real, non-zero BIOS-header
  content — this is a different structure, not a mis-scoped copy).
- **High end (RAM `0x3800` onward): a `0xff`→`0x00` transition, not a
  broken run.** `ram[0x37f0:0x3800]` is 16 bytes of `0xff` (stack-poison
  fill, a standard uninitialized-stack pattern) immediately followed by
  zero at `0x3800`; `rom[0x2ff0:0x3020]` stays `0xff` past that point (the
  ROM's own static copy of the same poisoned-stack template is longer than
  what the live kernel had actually touched). Scanned RAM `[0x3800,0x4200)`
  against `ROM−0x800`: only 5/2560 bytes coincidentally match — confirms
  this is genuinely dynamic/untouched RAM from `0x3800` on (heading toward
  the `0x0c004000` per-task TCB region `tooling.md` already names), not
  kernel content the loader needs to source from anywhere. **`hi = 0x3800`
  is a real boundary** (0xff-poison template ends exactly where the
  identical run ends), confirming the run is short *because the kernel
  blob's true static extent is 0x2800 B*, not because the ROM−0x800
  identity is unreliable.
- **`0x600`–`0x800` (the brief's flagged sub-window): the brief's own
  full-block search (`rom.find(ram[0x600:0x800])`) returns `-1`.** Chunked
  sub-searches (`select:` down to 8/16/32-byte windows) find only two small
  fragments elsewhere in ROM at *non-uniform* offsets (`0x1494` for the
  window's first ~20 B, `0x1e74` for ~60 B starting at window-relative
  `0x180`), with ~300 B of pure zero between them — evidence this is a
  small boot-time-constructed vector-stub/table (consistent with
  `tooling.md`'s "VBR+0x600 stub at `0x0c000600`" — the SH4 hardware
  interrupt-vector offset is a fixed CPU convention, not something that has
  to live at a fixed ROM address too), **not** a single contiguous ROM
  copy. No clean single-source recipe exists for it — per the brief's
  explicit fallback, taken as **snapshot-only content**.

### KERNEL-SLICE — the pin (three pieces, not one)

The plan's draft loader Makefile (`docs/superpowers/plans/2026-08-22-phase4-conversion.md`
§Loader Makefile deltas) sketches a single
`dd if=$(BIOS) skip=$(KERNEL_ROM_OFF) count=$(KERNEL_LEN)` starting exactly
at `KERNEL_DST=0x8c000600`. **That single-slice recipe cannot work**: a ROM
offset for RAM `0x600` would be `0x600 − 0x800 = −0x200` (the brief's own
"negative offset" warning, confirmed). The real recipe needs **three**
pieces to cover `[0x600, 0x3800)`:

| piece | mem_b range | len | source | ROM `skip`/snapshot slice |
| --- | --- | --- | --- | --- |
| A | `0x600`–`0x800` | `0x200` (512) | **snapshot-only** (no ROM source found) | `tools/ram-snapshot.bin[0x600:0x800]`, re-derivable via `tooling.md` §Phase 3: RAM snapshot's documented capture recipe |
| B | `0x800`–`0x1000` | `0x800` (2048) | **zero-fill** (`bzero`/`memset`, no bytes needed) | — |
| C | `0x1000`–`0x3800` | `0x2800` (10240) | **BIOS ROM**, `KERNEL_ROM_OFF=0x800` (2048), `KERNEL_LEN=0x2800` (10240) | `dd if=$(BIOS) bs=1 skip=2048 count=10240` |

> **KERNEL-SLICE pin.** `KERNEL_DST=0x8c000600` (per spec/brief);
> `KERNEL_ROM_OFF=0x800`, `KERNEL_LEN=0x2800` for piece C only (the literal
> two numbers Task 6's Makefile needs); pieces A and B are **not** a ROM
> `dd` — Task 6's Makefile draft must gain a `zero-fill 0x800 B` step and a
> `cat` of a committed-recipe-but-not-committed-bytes 512 B snapshot slice
> ahead of the existing single `dd`, or the placed image will be wrong over
> `[0x600,0x1000)`. Flagged for Task 6.

### KERNEL-SLICE — byte-compare verdict + digests

Piece C (the only piece with an independent ROM source to check against the
snapshot) byte-compared in full:

```
Piece C byte-compare ROM[0x800:0x3000) == RAM[0x1000:0x3800): True
  ROM slice: md5 ea73283fdfebdc2d0546e41af2da356d  sha256 7c0f310e80ca29297befe174c862cc0dbff29966dde6d1dbe0716422bf7fcd28  len 0x2800
  RAM slice: md5 ea73283fdfebdc2d0546e41af2da356d  sha256 7c0f310e80ca29297befe174c862cc0dbff29966dde6d1dbe0716422bf7fcd28  len 0x2800
Piece B all-zero: True  md5 c99a74c555371a433d121f551d6c6398  len 0x800
Piece A (snapshot-only): md5 7fa62b3351e5e47cba9086973c4560a4  len 0x200
full reconstruction [0x600,0x3800) == snapshot: True  len 0x3200
```

(digests only — no BIOS/snapshot bytes committed, per the global gitignore
rule.) **Acceptance bar met**: `piece_A + piece_B + piece_C ==
ram[0x600:0x3800]` byte-for-byte, verified by direct comparison, for the
full pinned window.

### BLOB-CHECK

```
python3 - <<'EOF'
import struct
rom = open("bios/naomi/epr-21576h.ic27","rb").read()
ws = struct.unpack_from("<8I", rom, 0x60000)
print([hex(w) for w in ws], all((w & 0x0fff0000) == 0x0c010000 for w in ws))
EOF
```

```
vectors: ['0xc018374', '0xc01837a', '0xc018398', '0xc01839e', '0xc018436', '0xc018422', '0xc01862c', '0xc0185dc']
signature (w & 0x0fff0000)==0x0c010000 for all 8: True
vectors landing in shim window 0x0c010000-0x0c017fff: []
range: 0xc018374 - 0xc01862c
```

> **BLOB-CHECK verdict — PASS, no shim collision.** All 8 vectors satisfy
> the signature and fall in `0xc018374`–`0xc01862c` — entirely inside the
> `0x60000`-blob's own destination window `BIOS60000_DST=0x8c018000`,
> len `0x7000` (plan `shim_iface.h` draft), i.e. `0x8c018374`–`0x8c01862c`
> in P1 terms. **None land below `0x8c018000`**, so none touch the shim
> home `0x8c010000`–`0x8c017fff` (`docs/kb/phase4-conversion.md` §Shim home
> found clean over that exact span). The map does not need to shrink;
> `FUN_8c065ff0`'s consumers are satisfied by pre-placement as designed.

### Residual risks — for Task 6 to close, not silently inherit

Piece A (`0x600`–`0x800`, 512 B) is pinned as **snapshot-only content**
because no clean single-source ROM recipe exists for it, but this task did
not determine *what it is* beyond "boot-time-constructed, not a straight
ROM copy" — the fragment evidence (two ~20–60 B chunks matching ROM at
non-uniform offsets `0x1494`/`0x1e74`, separated by zero) is consistent with
a hand-assembled vector stub/table, not proven to be one. If Task 6's
snapshot re-derivation ever produces a *different* 512 bytes for this
window (e.g. a value that varies boot-to-boot, such as an RTC seed or a
computed jump-table entry), the "one fixed 512 B slice" plan breaks and the
window needs its own targeted disassembly before Task 6 bakes it in.

### Reproduction

```
python3 - <<'EOF'
import hashlib, struct
ram = open("tools/ram-snapshot.bin","rb").read()
rom = open("bios/naomi/epr-21576h.ic27","rb").read()
assert rom[0x800:0x3000] == ram[0x1000:0x3800]
assert all(b==0 for b in ram[0x800:0x1000])
assert (ram[0x600:0x800] + ram[0x800:0x1000] + rom[0x800:0x3000]) == ram[0x600:0x3800]
ws = struct.unpack_from("<8I", rom, 0x60000)
assert all((w & 0x0fff0000) == 0x0c010000 for w in ws)
assert all(w >= 0x0c018000 for w in ws)
print("KERNEL-SLICE + BLOB-CHECK pins verified")
EOF
```

## GD driver — raw-ATA runtime path (Task 7)

**Question (plan Task 7):** the shim cannot use the DC BIOS GD syscall — the
loader places the Naomi RTOS kernel slice over `0x8c000600`–`0x8c003800`
(§Low-RAM placements), which is the BIOS's own low-RAM home for the GD driver
state and syscall vectors. So the shim drives the GD-ROM's ATA task file
directly. **Which registers, which packet, and what does the DRQ/BSY handshake
actually look like in the emulator that will run this code?**

Everything below was read out of the sources, not a wiki. Implementation:
`shims/src/gd.c` (same citations, in-line). Emulator = the fork this port runs
(`../flycast4naomi2dreamcast`); KOS = the tree `../cleopatra/tools/kos`.

### Register map (verified twice, independently)

| addr | read | write | flycast `gdromv3.h` | KOS `g1ata.c` |
| --- | --- | --- | --- | --- |
| `0xa05f7018` | alt status | device control | `:321-322` | `:83-84` |
| `0xa05f7080` | data (16-bit only) | data (16-bit only) | `:324` | `:85` |
| `0xa05f7084` | error / sense | features (bit0 = DMA) | `:326-327` | `:86-87` |
| `0xa05f7088` | interrupt reason | sector count / xfer mode | `:329-330` | `:88-89` |
| `0xa05f7090` | byte count low | byte count low | `:334` | `:91` (`LBA_MID`) |
| `0xa05f7094` | byte count high | byte count high | `:335` | `:92` (`LBA_HIGH`) |
| `0xa05f7098` | device select | device select | `:337` | `:96` |
| `0xa05f709c` | status (**acks INTRQ**) | command | `:339-340` | `:97-98` |

The brief's register sketch was correct in full. Two properties that are not in
the sketch and that the driver depends on:

- **`0x709c` is not `0x7018`.** Reading the status register cancels the GD
  interrupt (`gdromv3.cpp:1046-1047`, `asic_CancelInterrupt(holly_GDROM_CMD)`);
  reading alternate status does not (`:1054-1056`, a pure read). So all polling
  goes through `0x7018` and the single end-of-command verdict read goes through
  `0x709c` — which also leaves nothing latched.
- **Device select must name the master.** Flycast returns `0` from the status
  register whenever bit 4 of device select is set (`:1048-1050`, "slave drive
  doesn't exist") — a selected slave is indistinguishable from a hung drive.
  `0xa0` is the reset default (`:1410`) and what the driver writes.

Status bits `CHECK=0x01 / DRQ=0x08 / BSY=0x80`: `gdromv3.h:39-46`.
`ATA_SPI_PACKET=0xa0`: `gdromv3.h:347`. `SPI_CD_READ=0x30`: `gdromv3.h:366`.

### The SPI packet (command `0x30`, 2048-byte data sectors)

Written as **six little-endian 16-bit words** to `0xa05f7080`: flycast
accumulates exactly 6 words into the `u8[12]`/`u16[6]` union and only then
executes the command (`gdromv3.cpp:1139-1145`); the byte order inside a word is
the one KOS uses for every task-file word (`g1ata.c:541`,
`word = ptr[0] | (ptr[1] << 8)`).

| byte | value | why (source) |
| --- | --- | --- |
| 0 | `0x30` | `SPI_CD_READ` (`gdromv3.cpp:747`) |
| 1 | `0x20` | bit5 `data`=1 → 2048-byte sectors; bit0 `prmtype`=0 → FAD, not MSF (bitfield `gdromv3.h:148-155`; type selection `gdromv3.cpp:753-761`; `GetFAD` `:762` + `:357-363`) |
| 2–4 | start FAD, MSB first | `GetFAD` non-MSF branch, `gdromv3.cpp:362` |
| 5–7 | `0` | unused |
| 8–10 | sector count, MSB first | `gdromv3.cpp:764` |
| 11 | `0` | unused |

Byte 1 = `0x20` exactly: with `head/subh/other=0` and `expdtype=0`, both the
2340 and the 2352 branches fall through and `sector_type` stays `2048`
(`gdromv3.cpp:753-761`) — matching track04's 2048-byte data sectors in the B5
GDI layout. The count field is what separates `0x30` from `0x31`
(`SPI_CD_READ2` reads a 16-bit count at bytes 6–7, `gdromv3.cpp:766`), so the
command byte and the count field have to agree; they do.

`FEATURES=0` selects PIO: flycast branches to DMA only on `Features.CDRead.DMA
== 1` (`gdromv3.cpp:770`, bit0 per `gdromv3.h:75`).

### DRQ/BSY handshake — two corrections to the brief's sketch

1. **A DRQ block is not a sector.** The brief sketched "per sector: wait DRQ,
   read 1024 u16". Flycast delivers **up to 31 sectors (63,488 B) per DRQ
   block** — `maxSectors = (PioBuffer::Capacity - 1) / sector_type` with a 64 KB
   buffer (`gdromv3.cpp:255-266`) — and publishes the block's size in the byte
   count registers (`:229`, `ByteCount.full = pio_buff.getSize()`), ignoring the
   limit the host wrote. Real hardware honours the host's 2048-byte limit
   instead. The driver therefore **reads the byte count at the top of every
   block and consumes exactly that many bytes**, which is correct on both. It
   samples the count once per block because flycast decrements it by 2 on every
   data read (`:1079`).
2. **The status register is stale for ~400 ns after a phase change** (ATA
   requirement; flycast is synchronous and never shows it). Polling DRQ
   immediately after writing the command, or right after the last word of a
   block, samples the *previous* phase's DRQ — on real hardware that reads the
   data FIFO before the drive has filled it. The driver discards four alternate
   status reads (>100 ns each on the G1 bus) before every DRQ poll. Free on
   flycast (`gdromv3.cpp:1054-1056`: a pure read).
3. **"Wait for DRQ" is a three-way answer, not a two-way one.** A command that
   fails never enters a data phase: it goes straight to `gds_procpacketdone`
   with `CHECK=1`, `DRQ=0` and a sense key (`gdromv3.cpp:1030-1037` for an
   unhandled/illegal request, `:282-301` for the completion state). A wait that
   only looks for DRQ would burn the whole 50M-poll budget and report a stall,
   throwing the drive's own verdict away. `gd_wait_drq` therefore returns
   *ready* (BSY clear **and** DRQ set — status bits are invalid while BSY is
   asserted, and KOS polls the same pair, `g1ata.c:193-195`), *idle* (BSY and
   DRQ both clear → fall through to the status read and report `CHECK` plus the
   `ERROR` byte), or *timeout*. This is also why the 400 ns settle is
   load-bearing rather than merely defensive: a stale pre-BSY sample would read
   as "idle" and end the transfer early. A transfer that ends short without
   `CHECK` is still a failure (site 3) — the driver never returns success on a
   partial buffer.

Command completion raises the GD interrupt on every block and at the end
(`gdromv3.cpp:237,297`). That is `SB_ISTEXT` bit 0 (`holly_intc.h:43`,
`holly_GDROM_CMD = holly_ext | 0x00`), so the driver masks it once in
`SB_IML2/4/6EXT` = `0x5f6914/24/34` (`sb.h:87,94,101`) — the game runs with its
Naomi-legacy ASIC handler armed and no concept of a GD-ROM drive. Cleopatra hit
the same class with the *GD-DMA* interrupt (`ISTNRM` bit 14) on real hardware,
where masking it was what made cart streaming work. Shim only (`#if
!GD_LOADER_BUILD`): in the loader, KOS owns the interrupt policy — it programs
the IML registers from its own event table (`cdrom.c:805-813`) — and there is no
game handler to protect yet.

### Cache contract (the C1 lesson, restated for this driver)

`gd_read_fad` **always** writes its destination through the P2 uncached alias,
whatever alias the caller passed. That is what the game needs (it reads streamed
cart bytes uncached or hands them to hardware DMA), but it forces a rule on the
*reader* side: anything that reads those bytes back must read them uncached too,
or invalidate first. Two consequences, both live:

- `cart.c`'s bounce buffer is now addressed through P2 (`cart_read`). It used to
  be P1 — correct under Cleopatra's BIOS syscall, which wrote whichever alias it
  was handed, and **silently wrong** here: the driver's P2 write bypasses the
  cache, so a P1 read of the bounce can hit the line left over from the previous
  partial read and hand the game the *previous* sector's bytes. Intermittent,
  and invisible under emulation (flycast has no cache).
- the loader's rehearsal buffer is `dcache_inval_range`d before the read
  (discard, not write-back — a write-back would land stale zeroes on top of the
  incoming sector).

### Brief-vs-source: KOS `cdrom.c` is not a packet-protocol reference

The task brief asked for a cross-check of the packet protocol against KOS
`kernel/arch/dreamcast/hardware/cdrom.c`. **In this KOS, `cdrom.c` never
touches the task file**: it is a BIOS-syscall driver
(`syscall_gdrom_send_command` / `syscall_gdrom_exec_server`, `cdrom.c:96-100`) —
i.e. exactly the path this port cannot use after handoff. KOS's raw task-file
driver is `g1ata.c` (plain ATA for the IDE/HDD mod, not ATAPI packets), and it
is the citation used above for the register map, the 16-bit word order, and the
polled-PIO shape (`g1ata.c:190-197` wait macros, `:541` word packing).

Same class of substitution on the emulator side: the brief pointed at
`gdrom_response.cpp` for "command 0x30 parsing: FAD and length byte order".
That file is 51 lines of canned reply tables for the `0xa1` (IDENTIFY) and
`0x71` commands — it contains no command parsing at all. All of it lives in
`gdromv3.cpp` (`gd_process_spi_cmd`, `:708-1039`), which is what the citations
above point at.

### Failure sites

The driver never spins unbounded: every wait is capped at 50M polls (each poll
an uncached G1 read, >200 ns on hardware → a >10 s ceiling, far past any GD
seek; flycast answers in one poll). Every failure records the same site number
in three places — the negative return value, `gd_last_err` as
`0xda<site><ALTSTAT><ERROR>`, and `SHIM_ERR` as code `0x6<site>` with the FAD in
`e[1]` (field order per `util.c shim_die`). `cart.c`'s `gd_or_die` then paints
the red screen with `shim_die(4, fad, gd_last_err)`, so the TV shows the site
and the drive's own status/sense bytes.

| site | meaning |
| --- | --- |
| 1 | drive never went idle before the command |
| 2 | `PACKET` accepted but DRQ for the 12 command bytes never came |
| 3 | DRQ for a data block never came, or the drive stopped short of the requested bytes with no `CHECK` |
| 4 | drive offered an impossible byte count for a block |
| 5 | transfer done but the drive never went idle |
| 6 | drive raised `CHECK`; the `ERROR` register holds the sense key |
| 7 | caller bug (null dest / zero sectors) |
| 8 | `gd_read_cart` request runs past `CART_SIZE` |

The `SHIM_ERR` store is compiled out of the **loader's** copy of `gd.c`
(`-DGD_LOADER_BUILD=1`, `loader/Makefile`): KOS's naomi `LOAD_OFFSET` is
`0x8c010000` — the same address as `SHIM_BASE` — so `SHIM_ERR` (`0x8c014000`)
and `SHIM_BOUNCE` (`0x8c015800`) sit *inside the running loader's own image*
(`loader.elf .text` = `0x8c010000`–`0x8c03ab18`). The loader reads the negative
return value and `gd_last_err` instead, and rehearses `gd_read_fad` only —
`gd_read_cart` (the bounce-buffer user) is compiled out of that build entirely,
so it is unlinkable there rather than merely documented as unsafe.

### Verification status

Host-tested: the pure splitter `gd_plan` (`shims/test/test_gd_math.c`, wired
into `make test`) — the FAD/offset/alignment math, including zero length, both
partial paths, and the `CART_SIZE` boundary. The MMIO half cannot be exercised
until a disc exists: **the first end-to-end proof is Task 8's boot**, where the
loader's raw-ATA rehearsal reads `CART_FAD` and byte-compares it against the
same sector read through KOS. Reproduce the source claims with:

```
F=../flycast4naomi2dreamcast/core/hw/gdrom
sed -n '321,340p' $F/gdromv3.h        # register map
sed -n '747,777p' $F/gdromv3.cpp      # SPI_CD_READ parsing (FAD, count, sector type)
sed -n '244,268p' $F/gdromv3.cpp      # PIO blocks: up to 31 sectors each
sed -n '1135,1145p' $F/gdromv3.cpp    # 6x u16 packet write
sed -n '1041,1060p' $F/gdromv3.cpp    # 0x709c acks INTRQ, 0x7018 does not
sed -n '83,98p'  ../cleopatra/tools/kos/kernel/arch/dreamcast/hardware/g1ata.c
```

---

## First DC boot — GDI mastering + raw-ATA proof (Task 8)

**Question (task brief `task-8-brief.md`):** master the B5 donor-clone GDI for
senkosp and boot it in Flycast's DC profile — the first bootable disc for
this project, and the first emulator proof of the whole Phase 4 stack (KOS
loader → raw-ATA rehearsal → halt).

### GDI mastering — `scripts/make_gdi.py`

Adapted from `../cleopatra/scripts/make_gdi.py` byte-for-byte except the
brief's deltas: cart source `senkosp.dat` (asserted `len == 251342848`),
IP.BIN `IP_PRODUCT="T-SRS001M"` / `IP_TITLE="SENKO NO RONDE SPECIAL"` /
`IP_DATE="20260822"` / `IP_COMPANY` unchanged (`"SEGA LC-T-99"`, fan-port
convention), track04 = loader zero-padded to the donor's 3,538,944 B boot
region + `senkosp.dat`. The B5 max-clone structure itself (tracks 1–3 +
`disc.gdi` = donor Dolphin Blue, verbatim) is untouched.

**Finding — `CART_SIZE` was wrong in `shims/include/shim_iface.h`.** The
cross-check this script inherits from Cleopatra (`assert _csz == CART_SIZE`,
comparing the script's own `CART_SIZE` against the value parsed out of the
shim header) caught a real bug on the first `make gdi` run: the header had
`#define CART_SIZE 0x0efb0000` with a comment claiming
`/* 251,342,848 = len(senkosp.dat) */` — but `0x0efb0000` = 251,330,560, not
251,342,848 (`python3 -c "print(0x0efb0000)"` → `251330560`; `stat -f%z
senkosp.dat` → `251342848`; diff `0x3000` = 12,288 B). The correct hex is
`0x0efb3000`. Fixed in `shims/include/shim_iface.h` and the matching literal
in `shims/test/test_shim_iface.c`'s self-test; `make test` re-run green
after the fix. This is exactly the failure mode the cross-check exists to
catch (its own comment: "a donor swap or header edit could master the cart
at one FAD while the shim streams from another, with no error at any build
stage") — caught before any boot attempt, not diagnosed after one. The bug
was functionally inert until now: the only reader of `CART_SIZE` is
`gd_read_cart`'s range check (site 8), which is compiled out of the loader
build (`GD_LOADER_BUILD`), so it never affected Task 6/7's builds or tests.

**Donor:** `[GDI] Dolphin Blue.7z` copied from `../cleopatra/` to the repo
root (44 MB, gitignored — `*.7z` added to `.gitignore`; `git check-ignore -v`
confirms). Extraction is cached in `build/donor/` by `make_gdi.py` itself
(`/opt/homebrew/bin/7zz`, same as Cleopatra's recipe).

**Build:** `make gdi` (new top-level target: `loader` then
`python3 scripts/make_gdi.py`). Exit 0, asserts passing:

```
$ make gdi
...
note: 0GDTEX.png absent -> disc art stays the donor's (Dolphin Blue)
OK disc.gdi (B5 max-clone: tracks 1-3 + gdi = donor verbatim; track4 = loader + cart at LBA 451728 / FAD 451878)
```

**Determinism** — run twice from clean (`rm build/{disc.gdi,track0{1,2,3,4}.*}`
between runs), md5 identical both times, and identical again across two more
runs made later in this task (four runs total, same source):

```
MD5 (build/disc.gdi)   = c527f1ec937b56caa65084d436f8c0a0
MD5 (build/track01.iso) = 681fa4c8daa058ce2df8ea1b604d6e91
MD5 (build/track02.raw) = 03c796f60db2e9ef0b65a42a47a9d321
MD5 (build/track03.iso) = b05c578ec5bbe6e39731848b99df73e8
MD5 (build/track04.iso) = f34602293d259cf68237e1cc4a46aae6
```

### Boot result — **raw-ATA verified**

`scripts/capture_dc_leg.sh phase4/loader-alive` (brief's exact command, the
committed release build — `LOADER_SERIAL=0`, no guest serial output by
design) against the mastered `build/disc.gdi`, Flycast's **DREAMCAST**
profile (no Naomi ROM argument — the `.gdi` path is the CLI argument).
`captures/phase4/loader-alive.log` (cartlog, 140,562 lines) shows continuous
`MDODMA` background maple-poll activity for the whole run with no gap and no
`SHIMWATCH2`/error tag — the guest CPU never stalls. The release build is
silent on serial by design (`LOADER_SERIAL=0` kill-switch,
`loader/main.c`), so this leg alone does not show the loader's own text.

**Definitive text proof — diagnostic leg.** Per the debug-loop protocol
(get unambiguous evidence before concluding), `LOADER_SERIAL` was flipped to
`1` **temporarily** (`loader/main.c`, the code's own documented debug
switch), rebuilt, remastered, and booted twice
(`captures/phase4/loader-alive-diag.stdout.log`,
`captures/phase4/loader-alive-shot2.stdout.log` — two independent captures,
identical result). Flycast's `Debug.SerialConsoleEnabled = yes`
(`~/Library/Application Support/Flycast/emu.cfg`, already set) forwards
guest SCIF to Flycast's stdout. Both captures show the full success sequence
verbatim, in program order, with no error line before or after:

```
SENKOSP LOADER PHASE4 TASK6
GD init OK
cart read OK (KOS)
cart read OK (raw ATA)
patches OK
```

Tracing `loader/main.c` (Task 6/7's code, unchanged by this task): `"cart
read OK (KOS)"` only prints if `cdrom_read_sectors` succeeded and the image
starts `"NAOMI"`; `"cart read OK (raw ATA)"` only prints if
`gd_read_fad(CART_FAD, rawbuf, 1)` returned `0` **and**
`memcmp(rawbuf, stage, 2048) == 0` — i.e. the raw-ATA driver's read matches
KOS's own read of the same sector, byte for byte. This is the Task 7 driver's
first end-to-end proof (its own report, §8, named this exact test as the
open item). `"patches OK"` is unconditional (`PATCH_COUNT == 0`, Task 6
stub) and is unconditionally followed by
`halt("PHASE4 TASK6: loader alive, image verified")` — the `#if 0` block
between them never compiles in, so reaching `"patches OK"` on serial
**guarantees** that exact halt call ran next; no other code path exists.
`LOADER_SERIAL` was reverted to `0` and the loader/GDI rebuilt before the
final commit (`git diff loader/main.c` → empty; md5s above are the
**release**-build artifacts).

**Why the diagnostic build's text is trustworthy evidence, not just a
different run:** `LOADER_SERIAL`'s only effect is which `dbgio_init` gets
linked — `loader/main.c:52-55`, `#if !LOADER_SERIAL` strong-overrides KOS's
weak `dbgio_init` with a no-op that keeps `dbgio_enabled` at `0`. It gates
nothing else: no branch of the cart-read/verify/rehearse/patch/halt control
flow reads `LOADER_SERIAL`, so flipping it changes only whether `dbglog`'s
existing calls reach the serial port, not what code executes or in what
order. The diagnostic build is therefore the exact same control flow as the
release build, with a debug-only speaker turned on.

**Screenshot — `docs/kb/img/phase4-loader-alive.png`.** Two capture
mechanisms were tried; both hit environment-level limits in this session,
documented here so a future run knows what to expect:

- `screencapture -x` (the brief's specified method): `could not create image
  from display`, exit 1/2, reproducible even with the sandbox disabled — a
  macOS Screen Recording TCC permission this session's controlling process
  does not hold (a human must grant it in System Settings; out of this
  agent's reach).
- `FLYCAST_SHOT`/`kill -USR1` (`tools/flycast-src/core/ui/gui.cpp:508-545`,
  documented in this file's §Instrumented Flycast — built specifically to
  need no TCC permission, reading the GL/Vulkan offscreen framebuffer
  directly): produced a flat, unchanging mid-grey 9.6 KB PNG at first,
  identical byte-for-byte in content to a **control-test** capture of
  `../cleopatra/build/disc.gdi` (Cleopatra's own real-HW-verified disc)
  taken the same way — proving the flatness was the capture path stalling in
  this session, not this disc/loader (the debug-loop protocol's "control
  test to split my artifact from the process," applied to the screenshot
  tooling rather than the GDI itself, since the GDI's own control test
  (booting) was never in question here). Longer waits (up to several
  minutes) showed the render/present pipeline **is** alive but severely
  throttled for this backgrounded/occluded window — it delivered a handful
  of real frames (Flycast's own DC "swirl" boot animation, then its NAOMI
  license-screen animation, both frames confirmed non-grey and content-
  correct) over roughly two minutes, then stalled again. One captured frame
  lands mid-tear: the top of the framebuffer already solid red (our
  `halt()`'s pixel-fill loop, `loader/main.c`) with the previous frame's
  NAOMI logo still visible in the untouched bottom portion — captured from
  `loader-alive-shot2`, the same run whose stdout log (quoted above) shows
  the full success sequence through `"patches OK"` immediately before this
  frame. The committed PNG is this frame: genuine captured pixels, not
  fabricated, showing the halt screen's red fill actively in progress,
  time-correlated with the serial proof of the same run. A fully painted,
  static red+text frame was not obtained despite an extended wait and one
  `open -a`-triggered re-activation attempt — the render pipeline did not
  advance again afterward in the time available.

### Verdict

**Raw-ATA GD driver verified end-to-end on Flycast's DREAMCAST profile.**
KOS's `cdrom_read_sectors` and Task 7's `gd_read_fad` independently read the
same sector at `CART_FAD` and agree byte-for-byte; the loader reached its
Task 6/7 halt with no failure at any of the eight `gd.c` sites
(`docs/kb/phase4-conversion.md` §GD driver, §Failure sites). No driver code
was touched by this task — the only source fix was the `CART_SIZE` header
typo above, caught by `make_gdi.py`'s own cross-check before boot.

**Reproduction:**
```
make gdi
scripts/capture_dc_leg.sh phase4/loader-alive & sleep 90; pkill -9 -f "flycast-src.*Flycast"
grep -c MDODMA captures/phase4/loader-alive.log   # continuous background activity, no gap
```
For the text proof (temporary diagnostic only — do not commit with
`LOADER_SERIAL=1`): flip `loader/main.c`'s `LOADER_SERIAL` to `1`, `make gdi`,
capture, `grep -E "cart read OK|PHASE4|FAIL|ABORT|MISMATCH"
captures/phase4/<leg>.stdout.log`, then revert and rebuild.

---

## Integration v1 — first game entry (Task 10)

**Question (plan Task 10):** with the shim, the BIOS-derived blocks and the
patched image all placed by a copy-record handoff, and the cart/G1 mirror
serviced, does senkosp's own code run on a Dreamcast and stream from the
disc?

Legs live under `captures/phase4/entry*`. All Task 10 legs are **diagnostic
builds** (`LOADER_SERIAL=1` in `loader/main.c`, `make -C shims
DEFS='-DSHIM_SERIAL=1 -DSHIM_TRACE=1'`) — the same temporary-flip recipe Task
8 used and documented, reverted before commit. Nothing about the code path
differs; the flags only decide whether `dbglog`/`scif_puts` reach Flycast's
stdout (`Debug.SerialConsoleEnabled = yes`).

### `entry1` — no leg (Flycast startup failure, not ours)

```
⚠️ ui/gui.cpp:1596 E[COMMON]: Verify Failed  : &mem_b[0] == ((u8*)getContext()->sq_buffer + sizeof(Sh4Context) + 0x0C000000)
 in Init -> .../core/hw/sh4/dyna/driver.cpp : 349
```
Flycast's dynarec memory-layout assertion at VMEM init; the emulator never
reached the disc (`entry1.log` was never created — only the 695-byte
`entry1.stdout.log`). Host-side flake, reproduced zero times in the following
legs. Kept because capture legs are primary data and are never deleted.

### `entry2` — **the game enters, streams, and then reboots the console**

Loader side, verbatim from `captures/phase4/entry2.stdout.log`:

```
SENKOSP LOADER PHASE4 TASK10
boot: MAIN image
GD init OK
cart read OK (KOS)
cart read OK (raw ATA)
patched Heap-top seed, MAIN image: ... @dat:00065b50 (4)
...
patched CART-WAIT-A main: FUN_8c027e5e DMA-completion wait @dat:00007e5e (10)
patched CART-WAIT-B main: FUN_8c027e34 settle/abort @dat:00007e34 (12)
patched CART-BOOT-DMA main: boot cart DMA 0x8c066440 @dat:00046440 (12)
patched CART-PIO-READ main: boot PIO reader 0x8c0663e6 @dat:000463e6 (10)
patched RESET-PATCH main: restart -> DC reboot @dat:00047e4c (4)
patches OK
records=5 img=8cd00000/171ff8 shim=8c010000/8000 kern=8c000600/3200 blob=8c018000/7000
staged: shim + BIOS data + records
HANDOFF -> game
```

All 36 main-image entries applied — every `old`-byte compare passed against
the real staged image, so the pins transcribed into
`scripts/build_patch_table.py` are correct at runtime as well as at build
time.

Game side, immediately after the handoff (same file, verbatim):

```
CLEO-CCR write = 00000000 (was 00000105) pc=ac0210b8
CLEO-CCR write = 00000105 (was 00000000) pc=ac02b24c
CART off=00800000 len=00000800 dst=0c193f60 n=00000002
CART off=00808000 len=00000800 dst=0cfe6d20 n=00000003
CART off=0080a000 len=00000800 dst=0cfe6d20 n=00000004
...
CART off=00815000 len=00000800 dst=0cfe6d20 n=0000001a
CART off=03456000 len=0000d800 dst=0ce7dc00 n=0000001b
CLEO-CCR write = 00000000 (was 00000105) pc=ac02b2a4
SB/HOLLY: System reset requested
CLEO-CCR write = 00000929 (was 00000000) pc=a0000018
CLEO-GPIO PCTRA = 000a03f0 (was 00000000) pc=8c00b87c
```

Read off that:

- **The game is executing its own code.** `pc=ac0210b8` is 0x8c0210b8 through
  its P2 alias — 0xb8 bytes past `GAME_ENTRY` (0x8c021000). The game
  reprogrammed CCR itself as its first act.
- **Cart streaming works.** 26 services per boot cycle, each one a real
  raw-ATA disc read of the mirrored `SB_GDSTAR`/`SB_GDLEN`/`NAOMI_DMA_OFFSET*`
  request. No `SHIMERR` line anywhere in the log (`grep -c SHIMERR` → 0), so
  no destination fence trip and no GD failure at any of `gd.c`'s eight sites.
- **The relocation patches took.** Destinations `0x0cfe6d20` and `0x0ce7dc00`
  are corridor c5 (`0x0cfe6d20`) and corridor c4 (`0x0ce4dbe0`–`0x0ce8b480`)
  of `docs/kb/relocation-map.md` — i.e. the Naomi 32 MB addresses shifted down
  by exactly 0x1000000 as the heap-top seed intends. Un-relocated, the first
  of these would have been `0x0dfe6d20`, past the DC's 16 MB line.
- **The stop is a full console reboot**, and it repeats: 4 complete
  loader→game→reset cycles in a 120 s leg, **26 cart services in every single
  one** (`awk '/^HANDOFF/{c++} /^CART off/{n[c]++}'` → `1 26, 2 26, 3 26,
  4 26`). Fully deterministic.

Operator observation of the Flycast window during this leg (screen evidence,
recorded as given): "DC BIOS swirl → Sega TM screen → what looks like a
Naomi-style logo for ~1 second → black → the same logo screen but BLUE-tinted
and shifted left → black → swirl again, repeating indefinitely." So the game
also gets far enough to program video and present at least two frames.

`captures/phase4/entry2.log` (fork cartlog) corroborates how far it gets:
`MMUCRWR val=00040005 pc=8c02d630` — **senkosp turns the MMU on by design**,
same store-queue-mapper pattern Cleopatra's round 13 found in its own game
(the loader's `MMUCR = 0` before handoff is therefore only an initial state,
not a policy) — followed much later by `MMUCRWR val=00000000 pc=8c02d712` and
then the BIOS's own `pc=a0000018`. The log also carries 33,059 `MDODMA` and
220 `MIERESP` lines: the game drives **real** Dreamcast maple hardware
(nothing maple-side is patched yet — Task 11) and Flycast answers with
Dreamcast controller frames, not Naomi MIE frames.

### Where the reboot comes from — static trace

`grep`ing the main image for the restart stub's address (`0x8c067e18`) finds
no `bsr`/`bra` at all and exactly two pointer words, `0x8c02b210` and
`0x8c071714`. The first is loaded 4 bytes before a `jsr`, in this fragment
(decoded straight from `senkosp.dat`):

```
8c02b1f8  4f22   sts.l PR,@-r15
8c02b1fa  d105   mov.l @(0x5,PC),r1   ; r1 = [8c02b210] = 8c067e18   (restart stub)
8c02b1fc  d203   mov.l @(0x3,PC),r2   ; r2 = [8c02b20c] = a05f811c
8c02b1fe  9304   mov.w @(0x4,PC),r3   ; r3 = 0x00ff
8c02b200  410b   jsr @r1              ; -> the restart stub
8c02b202  2232   _mov.l r3,@r2        ; delay slot: *(0xa05f811c) = 0xff
8c02b204  d303   mov.l @(0x3,PC),r3   ; (dead: the stub never returns)
8c02b206  432b   jmp @r3
8c02b208  4f26   _lds.l @r15+,PR
```

and that wrapper (`0x8c02b1f8`) is itself reached through one pointer word,
`0x8c085c60`, loaded at `0x8c085c30` — the tail of a shutdown sequence that
first calls six teardown routines (`0x8c02bc26`, `0x8c06fd24`, `0x8c071798`,
`0x8c0716c0`, `0x8c06fe0c`, `0x8c02c3fc`) and then the reboot wrapper. The
neighbourhood is the system layer: `FUN_8c085b00`, ~0xf0 bytes earlier, is
the system-init routine that creates the game's heap
(`scripts/reloc_patchset.json`, heap-top seed).

So the chain is **deliberate game-initiated shutdown → restart stub →
(RESET-PATCH) → `shim_reboot` → 0xa0000000 → DC BIOS → the disc boots again**.
This is the patched path behaving exactly as designed; the open question is
what makes the game decide to shut down ~13 s and 26 cart streams into its
boot. Static scanning stops here: the shutdown function's own entry has no
static references, i.e. it is reached indirectly, so the trigger has to come
from a dynamic probe rather than another `grep`.

> **Note for anyone reading a future leg:** the reboot loop is a *consequence*
> of RESET-PATCH being live. Without it the same trigger would jump to
> `0x8dfff000` — a Naomi-BIOS re-entry that does not exist on a Dreamcast —
> and the console would wedge or crash instead, which is strictly less
> diagnosable. The loop is the good failure mode.

### `entry3` — freeze-frame: the game says why

`shim_reboot` gained a `SHIM_REBOOT_FREEZE` diagnostic (default 0,
`shims/src/main.c`): instead of jumping to `0xa0000000` it dumps the caller's
return address and 64 words of its stack over serial and spins, so the reboot
stops destroying its own evidence. Built with
`DEFS='-DSHIM_SERIAL=1 -DSHIM_TRACE=1 -DSHIM_REBOOT_FREEZE=1'`. One cycle,
26 cart services, zero resets, then verbatim from
`captures/phase4/entry3.stdout.log`:

```
SHIM REBOOT ra=8c02b204 sp=8c00deb0
STACK
 +00000000: 8c02b204 ffff0000 ffffff00 00000000 00000000 00000000 8c085c36 8c085c76
 +00000020: 8c0ad7a0 00010040 00000000 00000000 204f2f49 49204442 4f4e2053 4f432054
 +00000040: 43454e4e 20444554 4e204f54 494d4f41 2e444220 4147000a 41474553 41474553
 +00000060: 41474553 41474553 41474553 41474553 41474553 41474553 41474553 41474553
...
FROZEN
```

Two things fall out of that dump.

**The call chain, confirmed dynamically.** `ra = 0x8c02b204` is the
instruction after the `jsr @r1` at `0x8c02b200` (the reboot wrapper);
`[sp+0x18] = 0x8c085c36` is the instruction after the `jsr @r0` at
`0x8c085c30` (the shutdown sequence); `[sp+0x1c] = 0x8c085c76` is the return
address into whatever called the shutdown sequence — the frame the static
scan could not reach, because the shutdown function's entry has no static
references.

**The reason, in the game's own words.** The little-endian words from
`+0x30` decode to ASCII:

```
204f2f49 49204442 4f4e2053 4f432054 43454e4e 20444554 4e204f54 494d4f41 2e444220 4147000a
 "I/O "   "BD I"   "S NO"   "T CO"   "NNEC"   "TED "   "TO N"   "AOMI"   " BD."   "\n\0GA"
```

= **`I/O BD IS NOT CONNECTED TO NAOMI BD.\n`** — a string that lives in the
image at dat `0x168619` (RAM `0x8c188619`), between `MEMORY ALLOCATE ERROR
!\nHEAP:%p\nSIZE:%d\n` and `I/O BD CONNECTED TO NAOMI BD DOES NOT FULFILL\nTHE
GAME SPECS.` — i.e. the standard Naomi fatal I/O-board error pair. (The
second of those two is the same failure Cleopatra's port hit as "specs=1".)

> **Verdict — the stop is the maple/MIE boot driver, exactly as Task 10's
> brief predicted, expressed as the driver's *failure* path rather than a
> hang.** Nothing maple-side is patched yet (Task 11 owns MAPLE-BASE, the
> kick hook and the five boot detours), so the game's JVS enumeration talks to
> real Dreamcast maple, gets Dreamcast controller frames back, concludes there
> is no I/O board, formats this message, runs its six teardown routines and
> restarts. That the message is composed at all is itself proof the game got
> through system init, heap creation, video init and asset streaming.
>
> This closes the "unexpected PC" question: the stuck state is not an
> exception, not a wild jump and not a shim fault — it is the game's own
> documented error handler. `SHIM_ERR` was never written in any leg
> (`grep -c SHIMERR` → 0 in every capture).

### `entry4` — release configuration, same behaviour

Rebuilt with the committed defaults (`LOADER_SERIAL 0`, no shim `DEFS`) to
confirm the diagnostic flags change nothing but visibility. 100 s leg:

```
grep -c "^CART off\|^SENKOSP" entry4.stdout.log        -> 0     (silent, as a release build must be)
grep -c "System reset requested" entry4.stdout.log      -> 3
grep -c "MMUCRWR val=00000000 pc=a0000018" entry4.log   -> 4     (BIOS boots = loop cycles)
grep -c "MMUCRWR val=00040005 pc=8c02d630" entry4.log   -> 4     (game enables its MMU, every cycle)
grep -c "MMUCRWR val=00000000 pc=8c02d712" entry4.log   -> 3     (restart path, every cycle)
```

Identical behaviour to `entry2`/`entry3` with zero guest serial output — the
flags gate visibility only, exactly as `LOADER_SERIAL`'s Task 8 analysis says.

### Task 10 findings worth carrying forward

1. **senkosp runs MMU-ON by design.** `MMUCRWR val=00040005 pc=8c02d630`
   (`entry2.log`) — the same store-queue-mapper pattern Cleopatra's round 13
   found in its own game. The loader's `MMUCR = 0` immediately before the
   handoff is only an initial state; the game owns MMUCR from `0x8c02d630`
   onward, and nothing in the shim may force it back.
2. **The four cart hooks need four entry points, not one.** The KB's
   §CART-PIO line "Task 10 may implement all four hooks with one helper" does
   not survive contact with the ABIs: `FUN_8c027e5e` takes `(flag, obj)` in
   `r4/r5`, `FUN_8c027e34` takes `obj` in **`r4`** (byte-verified: its entry
   is `e058 mov #0x58,r0` followed by `004e mov.l @(r0,r4),r0`), and the two
   boot sites take `(cart_off, dest, len[, async])`. One helper reading `r5`
   as `obj` would write the game's completion flags through a destination
   pointer at the boot sites. `shims/src/cart.c` therefore has four entries
   over one shared `cart_stream()` core.
3. **CART-BOOT-DMA is implemented as a real read, not a no-op.** The KB's
   "CART-WAIT-B and CART-BOOT-DMA degenerate to *nothing pending → return*"
   is right for CART-WAIT-B (a pending transfer there is one the game still
   wants, so it drains) but wrong for CART-BOOT-DMA: an *entry* hook means the
   native body never programs the registers, so a mirror-driven no-op would
   hand the caller an unfilled buffer — the silent-corruption mode the KB
   itself wants avoided. It calls `gd_read_cart(off & ~0x1f, dest, len)`.
4. **The mirrored-destination fence is a FLOOR in this port, not a ceiling.**
   Cleopatra's shim lived at `0x8cfc0000` and fenced `dest + len` below it;
   senkosp's shim, its mirrors and the 0x60000 blob are all at the BOTTOM of
   RAM, so `cart.c`'s guard rejects `dest < 0x0c01f000` (and `dest + len >
   0x0d000000`, the DC's 16 MB line — a destination above it means the
   heap-top relocation seed did not take). Carrying Cleopatra's ceiling over
   verbatim would have rejected every legitimate stream.
5. **Nothing may be placed at its final address by loader C code.** KOS links
   the loader over `0x8c010000`–`0x8c0eef38`, which contains `SHIM_BASE`,
   `BIOS60000_DST` and `GAME_LOAD_ADDR`. Everything is staged in
   `0x8ce80000`–`0x8ce94000` and moved by `handoff.S`'s record walker running
   uncached from `HANDOFF_SCRATCH = 0x8ce94000`. The shim record covers the
   whole `[SHIM_BASE, SHIM_END)` window (0x8000), not just `shim.bin`, so the
   mirrors/`SHIM_ERR`/`SHIM_STATE`/bounce/GD-stack region is zero-filled by
   construction — which is also what establishes the mirror invariant
   (`mirror[0x418] == 0`) before the game's first `SB_GDST` poll.

### Reproduction

```sh
make -C shims && make gdi
scripts/capture_dc_leg.sh phase4/<leg> & sleep 120; pkill -9 -f "flycast-src.*Flycast"
# diagnostic build (temporary; revert before commit -- Task 8's recipe):
#   loader/main.c: LOADER_SERIAL -> 1
#   make -C shims clean && make -C shims DEFS='-DSHIM_SERIAL=1 -DSHIM_TRACE=1'
#   ... add -DSHIM_REBOOT_FREEZE=1 to halt at the restart instead of rebooting
grep -c "^CART off" captures/phase4/<leg>.stdout.log      # cart services
grep -c SHIMERR    captures/phase4/<leg>.stdout.log       # must stay 0
grep -c "System reset requested" captures/phase4/<leg>.stdout.log
```

### `entry5` — review-fix confirmation, and two latent boot-hook bugs closed

Task 10's review found two Important latent defects, both on the two boot
hooks that have never yet fired (`shim_cart_boot_dma`, `shim_cart_pio`) —
i.e. neither could show up in `entry2`–`entry4`, and neither would have been
caught by any leg until the day one of those paths actually ran.

**1. The boot hooks dropped the native offset's high-half base.** Both native
bodies compose their cart offset as
`(r4 >> 16) | *(u32 *)0x8c1bf18c | mode_bit` into `NAOMI_DMA_OFFSETH` /
`NAOMI_ROM_OFFSETH` (§CART-BOOT-POOLS `8c06645c`/`8c066480`, §CART-PIO
`8c0663fe`, byte-verified in both). The hardware **keeps** the low bits of
that word as real cart-offset bits 16..30:

```
naomi_cart.cpp:1032-1034   DmaOffset    |= (data & 0x7fff) << 16;      // DMA side
naomi_cart.cpp:1010-1013   RomPioOffset |= (data << 16) & 0x7fff0000;  // PIO side
```

so `r4` alone is the whole offset only while that word's low half is zero.
`0x8c1bf18c` sits past the main image's end — written at runtime, unknowable
statically. `cart_stream` is unaffected: it reads the mirror the game has
already OR'd.

> **Disposition: `shim_die`, not a silent OR.** Neither boot path has ever
> been observed executing (all 672 Phase 3 kicks are the steady path's
> `0x8c027f72`), so a non-zero base would mean the offset model for these
> hooks is *unvalidated* — that word could be a board-window base that does
> not map onto a flat `.dat` offset at all, in which case ORing it in reads
> the wrong region silently, which is precisely the failure mode §CART-PIO
> says these hooks exist to prevent. `boot_base_or_die()` dies on
> `base & 0x7fff` (the bits both hardware paths fold into the offset) and
> paints the value, landing the operator in the debug-loop protocol with the
> one number needed to decide. Upgrade path: decode `0x8c1bf18c`'s writer,
> then OR or translate.

**2. The destination fence was not applied on the boot hooks.** `cart_stream`
fenced `dest` against `DEST_LO`/`DEST_HI`, but both boot entries handed the
game-supplied `dst` straight to `gd_read_cart`, which validates only the cart
offset (`gd.c:319-321`) and never the destination — so a wild `dst` could
write over the shim, its mirrors or the 0x60000 blob. Fixed by factoring the
check into `fence_or_die(off, dest, len)` and calling it from all three read
paths. `len == 0` stays a caller-side early return, not a die: both native
bodies return early on it, so dying there would be a regression, not a catch.

Also folded in, matching the hardware more exactly (no-ops on every request
observed so far, all 32-byte aligned): `dest` is rounded down with
`& 0x1fffffe0` on the DMA paths (`SB_GDSTARD = SB_GDSTAR & 0x1FFFFFE0`,
`naomi.cpp:517`) and `SB_GDLEND` completes at `(len + 31) & ~31` rather than
`len` (`naomi.cpp:131-134` — the engine moves whole 32-byte bursts). The PIO
hook gets neither: its native loop stores half-words at whatever address it is
handed.

**Confirmation leg.** Same diagnostic build, one 120 s leg:

```
grep -c SHIMERR                         entry5.stdout.log -> 0
grep -c "^HANDOFF -> game"              entry5.stdout.log -> 4
grep -c "System reset requested"        entry5.stdout.log -> 4
awk '/^HANDOFF/{c++} /^CART off/{n[c]++}'                 -> 1 26, 2 26, 3 26, 4 26
CART off=00800000 len=00000800 dst=0c193f60 n=00000002     (first, identical to entry2)
CART off=03456000 len=0000d800 dst=0ce7dc00 n=0000001b     (26th, identical to entry2)
```

and the strongest form of "the live path was not disturbed": `entry2.log` and
`entry5.log` have **identical cartlog class histograms** (`diff <(awk '{print
$1}' entry2.log | sort | uniq -c) <(… entry5.log …)` → no output) and diverge
on exactly one field in 79,205 lines — a KOS-side maple descriptor address,
`mdstar=0c0f0b40` vs `0c0f0bc0`, shifted because the shim blob grew 140 bytes
(2,912 → 3,052 B) and moved a loader-side allocation.

---

## Attract — maple/MIE service live (Task 11)

**Question (plan Task 11, gate criterion 1):** with the maple registers
mirrored and the boot driver's five kicks detoured, does senkosp's I/O-board
handshake succeed on a Dreamcast, and does the game reach its title/attract
cycle?

**Answer: yes.** The five boot detours service the MIE's Z80 firmware upload
ladder exactly as the Naomi machine does (345 transactions, the same 345 the
Naomi capture records), the JVS I/O-board enumeration completes, the game's
per-frame input poll (MIE sub `0x33`) starts, and the game streams attract
assets and renders continuously. Legs live under `captures/phase4/attract*`.

### What the boot driver actually asks for — measured, not assumed

Before writing any reply synthesizer, the five kick sites were attributed to
their transactions in the Naomi-mode reference leg `captures/phase4/pc2.log`
(post-`MAINHANDOFF`, i.e. senkosp's own traffic, §R5). The fork logs the
kicking PC on every `MDODMA enter`, so each of the five detour sites maps 1:1
onto the maple commands it issues:

| site | kick PC (logged as +2) | frames | maple cmd | what it is |
| --- | --- | --- | --- | --- |
| **E** `8c066a5e` | `8c066a60` | 1 | — (`hdr0=80000300`, pattern 3 = RESET) | bus reset; no transfer, no reply |
| **A** `8c066726` | `8c066728` | **341** | `0x80`, `plen=8` | JVS/Z80 firmware upload, 0x1c bytes per chunk |
| **B** `8c06680e` | `8c066812` | 1 | `0x80`, `plen=2` | upload finalize (`dma_buffer_in[1] == 0xff`) |
| **C** `8c0668a2` | `8c0668a4` | 1 | `0x01`, `plen=1` | `MDC_DeviceRequest` |
| **D** `8c066926` | `8c066928` | 1 | `0x86`, `plen=1` | a 0x86 frame with **no payload** |

Two consequences that a subcommand-table-only shim would have got wrong:

- **The boot driver never sends a single MIE *subcommand*.** It uploads
  firmware and probes the device. Every reply it needs is computable from the
  request — `BaseMIE::RawDma`,
  `../flycast4naomi2dreamcast/core/hw/maple/maple_jvs.cpp:1291-1405` — so the
  boot path consumes exactly one captured blob (site D's, 4 bytes).
- **Site D's frame carries no payload**, and Flycast answers it before it ever
  reads a subcommand byte (`if (dma_count_in == 0) { reply(MDRS_JVSReply);
  return; }`, `maple_jvs.cpp:1758-1761`). The capture labels that reply
  `sub=ff` only because the fork's MIERESP logger reads `p_data[4]`
  (`maple_if.cpp:299`), which for a 1-word frame is *past the frame*. The shim
  therefore keys on `plen`, not on that byte; the blob is named `mie_86empty`.

### The I/O-board gate is on the STEADY engine, not the boot driver

The Task 10 stop (`I/O BD IS NOT CONNECTED TO NAOMI BD.`) is decided at
`0x8c0acf44`, disassembled from `senkosp.dat` (main image, dat `0x8cf44`):

```
8c0acf44  mov.l 0x8c0acf74,r0   ; r0 = 0x8c06fbf8
8c0acf48  jsr @r0               ; FUN_8c06fbf8 = `return *(u32 *)0x8c1c013c`
8c0acf4c  tst r0,r0
8c0acf4e  bf 0x8c0acf56         ; non-zero -> board present, skip the fatal
8c0acf50  mov.l 0x8c0acf78,r0   ; = 0x8c0ad6a0 -> prints str+0x29 =
8c0acf52  jsr @r0               ;    "I/O BD IS NOT CONNECTED TO NAOMI BD.\n"
8c0acf56  mov.l 0x8c0acf7c,r0   ; = 0x8c06fc04, spec check(r4=1, r5=10, r6=1)
8c0acf5c  jsr @r0               ;    board[0x94] >= 1 players, [0x95] >= 10
8c0acf5e  mov #10,r5            ;    switches, [0x97] >= 1 coin slots
8c0acf62  tst r0,r0
8c0acf64  bf 0x8c0acf6c
8c0acf66  mov.l 0x8c0acf80,r0   ; = 0x8c0ad6c0 -> prints str+0x4f =
8c0acf68  jsr @r0               ;    "...DOES NOT FULFILL THE GAME SPECS."
```

`0x8c1c013c` is the JVS **node count**, written by the node scan at
`0x8c068da6` (`mov.l 0x8c068dd8,r4 ; ... ; mov.l r13,@r4`, r13 = the probe's
result), and the spec bytes come from the parsed board-info struct at
`*(0x8c1c0144) + 0xac + 0x94…0x98`. **That scan transacts on the steady maple
engine, not on the boot driver**: in `pc2.log` every enumeration frame
(sub `0x17` transmit / sub `0x15` receive carrying JVS `F1,10,11,12,13,14`) is
logged with `pc=8c025448` — the steady kick site — and they all occur *after*
the boot driver's last kick.

> **Consequence for the task split, recorded as a deviation.** Criterion 1
> (attract) is unreachable with the boot detours alone, and leg `attract1`
> proves it empirically (below). MAPLE-KICK-HOOK — a pinned mechanism this doc
> already specifies in full (§MAPLE-KICK-HOOK) but which the plan assigned to
> Task 12 — was therefore wired in Task 11. Task 12 keeps its actual substance
> (live pad input through `dc_to_jvs`, TESTBIT-INJECT, free-play/EEPROM).

### Blob provenance

`scripts/extract_mie_blobs.py` harvests **15** reply classes from
`captures/phase4/pc2.log`, post-`MAINHANDOFF` only (pre-handoff maple traffic
is the Naomi BIOS's, §R5, and goes to the BIOS's own buffer `0x0c296220`).
Output is `shims/build/mie_blobs.c` — generated at build time by the shim
Makefile, **gitignored**: it is captured game/BIOS traffic.

- **Lengths are measured, not modelled.** The fork prints `MDODMA rawdma_ret
  outlen=` immediately before each `MIERESP` (`maple_if.cpp:283-306`), so each
  blob is trimmed to the byte count the emulator actually returned. This is
  not cosmetic: JVS data frames *declare one 32-bit word more than they write*
  (`dword_length = (len + 22) / 4 + 1`, `maple_jvs.cpp:1716-1727`), so
  Cleopatra's `(hdr[3]+1)*4` rule overshoots them by 4 bytes.
- **Byte-stability is asserted** across every occurrence of each class in the
  leg (sub `0x17` 9×, sub `0x31` 2×, the rest 1×). The steady sub-`0x33` poll
  is exempt by nature — it carries live input, and its first occurrence is the
  cold/no-scan variant (subresp `0x32`); the shim replays the has-data variant
  (subresp `0x16`), which is byte-identical across all 15,799 occurrences.
- **Three classes exceed the 0x40-byte MIERESP dump and are reconstructed**,
  each with an assert tying the reconstruction to bytes the capture *does*
  contain:
  - `mie_sub33` (68 B) = the 64 captured bytes + the 4-byte tail of the
    trailing ack frame (`w8(0x18); w8(channel); w8(sense_line); w8(0)`,
    `maple_jvs.cpp:1888-1893`). The splice is checked: captured bytes 60..63
    must equal the separately captured sub-`0x17` ack's header.
  - `mie_jvs10` (92 B) = the board-ID string (`get_id()`,
    `maple_jvs.cpp:1105`) spliced onto the captured prefix (33-byte prefix
    match asserted) with the JVS checksum recomputed — Cleopatra's method,
    unchanged.
  - `mie_sub03` (132 B) = 4-byte header + the 128-byte EEPROM image, rebuilt
    from the captured first 60 bytes using the Naomi dual-copy layout (system
    section twice at `0x00`/`0x12`, game header twice at `0x24`/`0x28`, game
    data twice from `0x2c`, zero tail). Every copy the capture contains is
    asserted equal to its twin before the tail is derived. **Independently
    verified**: the reconstruction is byte-identical to the 128-byte EEPROM
    Flycast itself saved for this ROM (`~/Library/Application
    Support/Flycast/data/senkosp.zip.eeprom`, not part of this repo) — a file
    written by a different code path than the capture.

### The five detours, as built

`shims/src/mtramp.S` — ten stubs (five sites × two images) over one shared
body. Each stub loads its site's resume address into **r2** (free: the
original window clobbers exactly r2 and T) and falls into the common body,
which pushes r2 first and pops it last straight into the `jmp`. The body
saves and restores **r0, r1, r3–r7, PR, MACL, MACH** around the call into C,
per the register contract at :1261-1280 (r8–r15 the C ABI preserves).

Resume address = window RAM address + window length, and both numbers now
exist in two places (this doc's table → `scripts/build_patch_table.py`'s
`MAPLE_BOOT_SITES`, and `mtramp.S`), so the generator **asserts them equal**
(`_resume_check`) and refuses to emit a table that disagrees with the
trampolines. Negative-checked: perturbing one resume address by 2 bytes fails
the build with
`MAPLE-BOOT-C test: mtramp.S resumes at 0x8c0510e2, window 0x8c0510d4+12 ends
at 0x8c0510e0`.

Generated detour bytes, verified against the table above per site per image
(main A shown; the other nine differ only in the literal):

```
old  72 2e 72 25 52 62 28 22 fc 8b c2 2e   = 2e72 2572 6252 2228 8bfc 2ec2
new  01 d2 2b 42 09 00 09 00 cc 10 01 8c   = d201 422b 0009 0009 .long 8c0110cc
```

All 120 generated entries (60 per image) pass their old-byte verify against
`senkosp.dat`.

### Leg chain

| leg | build | what it establishes |
| --- | --- | --- |
| `attract1` | boot detours + MAPLE-BASE + pools; **kick-hook OFF** | boot ladder complete, error path never taken, stop = the unserviced steady engine |
| `attract2` | + MAPLE-KICK-HOOK | enumeration completes; game streams and renders |
| `attract3`/`attract6` | same, + sub-level tracing | reproduced; `MIE skip` = 0 (no reply ever undelivered) |
| `attract4` | same | 14,336 maple transactions serviced, 89 cart streams — the game runs indefinitely |
| `attract7` | + a real maple DMA per service (experiment) | 18,432 transactions, 89 streams, same handshake — raising `holly_MAPLE_DMA` changed nothing observable → residual risk 1 closed; the experiment was reverted |
| `attract8` | reverted to the plain service | 5,537 frames rendered, 1,383 display lists > 4 KB, AICA ARM sound driver booted |
| `attract10-release` | release config (no serial, no trace) | the shipped build behaves identically |

**`attract1` — the boot ladder alone.** Verbatim serial tail:

```
MB n=00000157 star=0c1bfa80 h1=80000001
MB n=00000158 star=0c1bfa80 h1=80000000
MB n=00000159 star=0c1bfa80 h1=80000000
```

`0x159 = 345` transactions = 1 (site E reset) + 341 (site A chunks) + 1
(site B finalize) + 1 (site C DeviceRequest) + 1 (site D empty 0x86) — the
Naomi count, exactly. `System reset requested` = **0** (Task 10's reboot loop
is gone: the I/O-board error path never fires), `SHIMERR` = 0, `MIE odd` = 0.
`CART off` = **0**: the game now stops *before* the asset streaming Task 10
reached, because the JVS enumeration it needs sits earlier in the boot than
the first asset load. The game-side cartlog is 24 lines long (PVR soft reset,
interrupt masks, its own MMU enable at `8c02d630`, SPG video-mode program) and
then silent — the steady engine kicks into the mirror and polls forever.

**`attract2`+ — the enumeration, verbatim** (`MIE sub=` lines are
change-gated, so this *is* the whole handshake):

```
MIE sub=00000031 jvs=00000000 rcv=0cff9f60 n=0000015c   DIP switches
MIE sub=00000001 jvs=00000000 rcv=0cff9f60 n=00000161   EEPROM ready
MIE sub=00000003 jvs=00000000 rcv=0cff9f60 n=00000163   EEPROM read (128 B)
MIE sub=00000017 jvs=000000f0 rcv=...      n=00000166   JVS reset
MIE sub=00000017 jvs=000000f1 rcv=...      n=000001a4   JVS set address
MIE sub=00000015 ...                       n=000001a5   -> mie_jvsf1
MIE sub=00000017 jvs=00000010 / sub=15     n=000001a7   -> mie_jvs10 (board ID)
MIE sub=00000017 jvs=00000011 / sub=15     n=000001aa   -> mie_jvs11
MIE sub=00000017 jvs=00000012 / sub=15     n=000001ad   -> mie_jvs12
MIE sub=00000017 jvs=00000013 / sub=15     n=000001b0   -> mie_jvs13
MIE sub=00000017 jvs=00000014 / sub=15     n=000001b3   -> mie_jvs14 (features)
MIE sub=00000013 jvs=00000000              n=000001b6
MIE sub=00000021 jvs=00000022              n=000001b7
MIE sub=00000017 jvs=00000021 / sub=15     n=000001b8
MIE sub=00000033 jvs=00000000 rcv=0cff3f60 n=000001bb   <== the per-frame poll
```

**Sub `0x33` starting is the gate opening.** It is the same signal Cleopatra
used (`../cleopatra/docs/kb/phase4-conversion.md` §Task 15c: "node-count ≥ 1 →
specs = 0 → JVS-board slot registered → engine emits sub-0x33"). Neither
fatal string is ever printed, and `System reset requested` stays 0 in every
leg. The recv addresses (`0x0cff9f60` / `0x0cff3f60`) are the Naomi
`0x0dff9f60` / `0x0dff3f60` double-buffer shifted down by the relocation
patches — the maple path confirms the relocation seeds independently of the
cart path.

**Attract reached.** `attract8` (~6 min, plain service):

```
MB n=345 (boot ladder)   MIE sub= 21 (the handshake above)   MIE skip= 0
MS n=... heartbeats every 512 services, climbing to the end of the leg
CART off= 77 streams     System reset= 0     SHIMERR= 0     MIE odd= 0
post-handoff: 5,537 STARTRENDER, 11,076 C2D list transfers of which
              1,383 are > 4 KB (real geometry), first at 63% into the leg
CLEO-ARMRST(w) VREG=03 ARMRST=00 ram0=ea00003e ram4=ea000089   (AICA ARM booted)
```

And the streams are *attract's* streams, not arbitrary ones: of the 83 cart
transfers in `attract3` (and the identical 83 in `attract6`), **82 match a
`(cart_offset, length)` pair the Phase 2 Naomi capture recorded** and 54 of
them appear in the Phase 2 **attract** leg specifically
(`docs/kb/cart-streaming-map.csv`); 72 of the 83 land in the relocated
above-16 MB corridors. The longer legs extend the same sequence rather than
diverging from it — `attract4`/`attract7` reach 89 streams, 87 matched, 57 in
the attract leg, the same 72 in-corridor. The tail of the sequence is the attract demo
battle's asset load (`0x0b496800 len=0x3be800` → `0x0c7b8d40`, corridor 1's
`0x0c271000`, etc.).

**And the picture.** `docs/kb/img/phase4-dc-attract.png`, grabbed from leg
`attract11-shot` (release configuration, unattended, no input): senkosp's
attract **DEMONSTRATION** running on the DC profile — both mechs, both
health / OD / MAX gauges, the 99 timer, the button-legend overlay with its
Japanese barrier tutorial text, `PRESS 1P OR 2P START BUTTON`, and
**`FREE PLAY`** on the bottom line (the captured EEPROM's coin byte reaching
the attract credit display, which answers half of Task 12's free-play question
before it is asked). Capture method: macOS `screencapture` is TCC-blocked in
this session, so the frame comes from the fork's own headless
framebuffer→PNG dump (`$FLYCAST_SHOT` + `kill -USR1`, `gui_dumpFramebuffer`,
`../flycast4naomi2dreamcast/core/ui/gui.cpp:510-545`) — the Task 8 precedent,
which reads the GL offscreen buffer and needs no screen-capture permission.
That leg is otherwise identical to `attract10-release`: 11,009 frames rendered
post-handoff, **0** `MDODMA` from any game PC.

### Findings worth carrying forward

1. **Residual risk 1 (maple-DMA interrupt) is closed empirically.** The game
   *does* enable `holly_MAPLE_DMA`: its boot builds `IML4NRM` to `0x0007f000`
   (the DMA-end group, bits 12–18; `holly_intc.h:27` puts maple at bit 12),
   and the `0x1000` step is logged at `pc=8c02bd0a pr=8c023bd8` in every leg.
   Leg `attract7` raised that interrupt for real — a single pattern-3 maple
   DMA on the true registers after each service, which makes Flycast's
   `maple_schd()` run `asic_RaiseInterrupt(holly_MAPLE_DMA)`
   (`maple_if.cpp:375-401`) — and the game behaved the same as without it:
   same enumeration, same 89-stream cart sequence, same absence of errors, and
   it kept servicing to the end of the leg either way (`attract4` 14,336
   transactions without, `attract7` 18,432 with). No *rate* claim is made from
   these legs: the kill command did not actually stop the emulator (finding 4),
   so each leg ran until the next one started and the durations are not
   comparable. The synchronous mirror completion is sufficient; the experiment
   was reverted rather than shipped.
2. **Non-MIE maple frames are answered "no device."** The steady engine polls
   buses 1 and 2 (`cmd 09`, recipients `0x60`/`0xa0`) roughly once per frame,
   and Flycast's *Naomi* profile answers them with real Dreamcast controller
   replies because it keeps controllers attached there. A real Naomi cabinet
   has only the MIE on the bus, so the shim replies with the no-response
   marker `0xffffffff` — Flycast's own answer for a missing device
   (`maple_if.cpp:315-320`). Attract is unaffected. Task 12 should re-check
   this when live pad input goes in.
3. **`MIE odd` never fired.** No unmodelled maple command and no unmodelled
   0x86 subcommand was seen in any leg — the modelled set (`0x01`, `0x02`,
   `0x03`/`0x04`, `0x80`, `0x82`, `0x86`, and subs `0x01`, `0x03`, `0x0b`,
   `0x13`, `0x15`, `0x17`/`0x19`/`0x21`, `0x31`, `0x33`) covers boot + attract
   completely.
4. **Reading a leg's stdout too early lies.** Flycast's stdout is block
   buffered and the capture recipe's `pkill -9` discards the last block; worse,
   `pkill -9 -f "flycast-src.*Flycast"` did **not** match the process in this
   session (the next leg's own startup pkill is what ended the previous one),
   so a log read right after a "kill" can be both truncated *and* still
   growing. Kill by PID (`pgrep -f "Flycast.app/Contents/MacOS/Flycast"`) and
   re-read after the size settles. Three intermediate readings in this task
   suggested a stall that did not exist.

### Reproduction

```sh
# blobs (regenerated by the shim Makefile; gitignored output)
python3 scripts/extract_mie_blobs.py                    # 15 classes, all asserts

# build + leg (diagnostic: LOADER_SERIAL=1 in loader/main.c, reverted before commit)
make -C shims clean && make -C shims DEFS='-DSHIM_SERIAL=1 -DSHIM_TRACE=1'
make gdi && scripts/capture_dc_leg.sh phase4/attractN &
# ... let it run, then:  kill -9 $(pgrep -f "Flycast.app/Contents/MacOS/Flycast")
# ... wait for the .stdout.log size to settle before reading it

# what to grep for
tr '\r' '\n' < captures/phase4/attractN.stdout.log > /tmp/a.txt
grep -c '^MB n='      /tmp/a.txt     # 345 = the boot ladder, complete
grep    '^MIE sub='   /tmp/a.txt     # the enumeration; must end at sub=33
grep -c '^MIE skip\|^MIE odd\|SHIMERR\|System reset requested'  /tmp/a.txt   # 0
grep -c '^CART off'   /tmp/a.txt     # attract asset streams
grep -c '^MS n='      /tmp/a.txt     # steady-service heartbeats, must keep climbing

# no real maple DMA may come from a game PC (Cleopatra's lesson (b))
grep 'MDODMA enter' captures/phase4/attractN.log | sed 's/.*pc=\([0-9a-f]*\).*/\1/' \
  | sort -u          # only loader/KOS PCs, and only before the handoff line
                     # (the loader's own MMUCR=0 store: `grep MMUCRWR` and take
                     #  the LAST 8c01xxxx one -- its PC moves with the loader
                     #  build, 8c01057c diagnostic / 8c010580 release)
```

---

## Steady input — live DC pads + EEPROM (Task 12)

**Question:** with the maple/MIE transport live (§Attract), what does the shim
put *in* the per-frame reply, and where do the game's settings come from?

Task 11 left the steady sub-`0x33` poll **replaying** the captured idle frame,
so the game saw a controller that never moved. This section is what replaced
that replay: a real Dreamcast GetCondition on maple ports A and B, mapped
through `dc_to_jvs`, built into the JVS has-data frame at the §Input ABI
offsets with the checksum recomputed; plus an EEPROM served out of a RAM copy
that accepts the game's own writes.

### The path, end to end

| stage | code | contract |
| --- | --- | --- |
| real DC transaction | `shims/src/maple.c` `maple_getcond(port)` | one synchronous GetCondition DMA per port on the **real** maple registers (`0xa05f6c04`…), TX/RX in shim home, one retry, `0` on no reply |
| normalize | `shims/src/jvs.c` `dc_cond_to_pressed(w2, w3)` | reply words 2–3 = `cont_cond_t` → pressed mask: buttons inverted, R trigger thresholded, analog stick folded into the D-pad bits |
| map | `shims/src/jvs.c` `dc_to_jvs(mask)` | pressed mask → senkosp's measured JVS digital word (`input-map.md`) |
| build | `shims/src/main.c` `mie_poll(rcv)` | copy the captured frame, overwrite `+0x20`/`+0x22`, recompute `+0x3a`, write to the block's recv address |

`cont_cond_t` is the wire form of the reply, one word past the function code —
`u16 buttons; u8 rtrig; u8 ltrig; u8 joyx, joyy, joy2x, joy2y`
(`../cleopatra/tools/kos/kernel/arch/dreamcast/hardware/maple/controller.c:28-36`,
and `:171` `raw = respbuf + 1`, i.e. our `rx[2]`/`rx[3]`). The emulator's own
controller emits exactly that order — `w16(getButtonState(pjs))` then six
analog axes R, L, X, Y, –, –
(`../flycast4naomi2dreamcast/core/hw/maple/maple_devs.cpp:185-200`, axis
assignment `:96-114`).

Three normalizations, each cited in `jvs.c`:

1. **Buttons are active-low** on the wire and active-high in JVS. KOS performs
   the same inversion (`cooked->buttons = (~raw->buttons) & 0xffff`,
   `controller.c:176`). Unused bits come back as 1 (released) because the
   device ORs them in (`return kcode | 0xF901`, `maple_devs.cpp:93`), so the
   inverse carries no stray set bits.
2. **R trigger is analog**, 0–255, not a button — thresholded at **128** (half
   press) into the synthetic `CONT_RTRIG` bit (`1 << 16`, just past the real
   0–15 button field) that Task 6's `dc_to_jvs` already expected. L trigger is
   deliberately unmapped (`input-map.md` §DC pad layout: "L trigger | unbound").
3. **The analog stick is OR'd into the D-pad bits**, because the port's control
   layout binds *both* to the 8-way stick (`input-map.md` §DC pad layout: "D-pad
   + analog (both) | Stick (8-way)"). Axes are 0–255, 128-centred, low = up/left
   (`controller.c:178-179` `((int)raw->joyx) - 128`; direction taken from the
   emulator's own analog→D-pad conversion, `maple_devs.cpp:1483-1513`, which
   presses UP for a `joyy` below centre). The neutral band **`0x40`…`0xc0`** is
   that same conversion's band, not an invented number.
4. **Opposed directions cancel.** Because the stick and the D-pad are OR'd they
   can disagree — stick left while the D-pad is held right — which no arcade
   lever can do, and which would otherwise put `LEFT|RIGHT` (`0x0c00`) on the
   wire. The fold therefore ends with the **mutual exclusion the emulator
   applies at both of its own sites**: if both of an opposed pair are pressed,
   *neither* is reported.
   - `maple_devs.cpp:67-71` `mutualExclusion(kcode, mask)` — on the active-low
     `kcode`, "if both bits are 0 (both pressed), set both" — invoked at `:91-92`
     immediately before the controller reply is built.
   - `maple_jvs.cpp:2224-2228` — the same rule on the active-high JVS word:
     `if ((button & (UP|DOWN)) == (UP|DOWN)) button &= ~(UP|DOWN);`
   Host-tested both ways: D-pad-right + stick-left reports nothing, and the
   cancellation is per axis (a simultaneous UP survives an L/R cancellation).

**Deviation from Cleopatra, deliberate.** Cleopatra's `maple_getcond` returned
the raw active-low word and its `dc_to_jvs` inverted internally. This port's
`dc_to_jvs` was written in Task 6 to take an already-normalized *pressed* mask,
and it has a trigger bit Cleopatra's game had no use for — so `maple_getcond`
returns the normalized mask here, and `dc_cond_to_pressed` (pure, host-tested)
is the single owner of that contract. Keeping Cleopatra's split verbatim would
have left `maple.c`'s own comment false: `dc_to_jvs(0xffff)` under this port's
`dc_to_jvs` is *every button pressed*, not idle.

### What the built frame overwrites — and what it must not

`mie_poll` copies the captured 68-byte reply and touches exactly five bytes:

| off | field | source |
| --- | --- | --- |
| `+0x20`/`+0x21` | P1 buttons, hi then lo | `dc_to_jvs(maple_getcond(0))` |
| `+0x22`/`+0x23` | P2 buttons, hi then lo | `dc_to_jvs(maple_getcond(1))` |
| `+0x3a` | JVS checksum | `jvs_checksum()` = `Σ frame[0x1b…0x39] & 0xff` |

Big-endian on the wire, per player, is the emitter's own order —
`JVS_OUT(inputs[player] >> 8)` then `JVS_OUT(inputs[player])`
(`maple_jvs.cpp:2248`, `:2252`). The checksum rule is
`for (i = 1; i < length; i++) calc_crc += buffer_out[i]` with `buffer_out[0]` =
the `0xE0` sync at frame `+0x1a` (`maple_jvs.cpp:2487-2491`).

Everything else is replayed byte-for-byte, including the three fields
TESTBIT-INJECT names but this port does **not** drive:

- `+0x1f` **Test** (bit 7) — stays `0x00`. Test and Service have no pad binding
  (`input-map.md` §DC pad layout: "the access mechanism … is a Phase 4 loader
  decision, not a pad binding"), so the shim never sets them. The wire bits are
  known and pinned if a later task wants a boot combo: Test = `+0x1f` bit 7,
  Service = `+0x20` bit 6.
- `+0x25`/`+0x26`, `+0x27`/`+0x28` **coin counters** — stay `0`. Free play is
  baked (below), so Coin needs no binding.
- both maple frame headers, the JVS sync/node/length/status bytes, the eight
  idle `0x8000` analog channels, and the **trailing ack frame at `+0x3c`**
  (`87 00 20 01 | 18 00 8e 00` — a sub-`0x33` reply is two maple frames,
  `maple_jvs.cpp:1888-1893`).

### IDLE-FRAME EQUIVALENCE — the check that makes this provable without a pad

The build transform must be the **identity** on the captured all-idle frame:
zero player words in, the captured bytes out. That is asserted at blob
generation time, so a wrong offset or a wrong checksum span fails the *build*
rather than a leg nobody can debug without a controller
(`scripts/extract_mie_blobs.py` `rebuild_sub33`):

```python
built = bytearray(out)
built[0x20:0x24] = b"\x00\x00\x00\x00"
built[0x3a] = sum(built[0x1b:0x3a]) & 0xFF
assert bytes(built) == out
```

It passes: **built == captured, all 68 bytes, zero differing fields.** There is
no counter or echo field in this frame to explain away — the reply carries no
sequence number (the double-buffered *recv address* alternates, but that is the
game's descriptor, not the frame).

Negative-tested: moving the player words to `+0x21` makes the assert bite. The
same negative test found a real gap and it is now closed — an all-idle frame
**cannot** discriminate the checksum's upper bound (`frame[0x39]` is `0x00`, so
`Σ 0x1b…0x38` gives the same `0x22`). Two extra asserts pin it against the
frame's *own* self-describing header instead: `frame[0x1a] == 0xE0` (the sync)
and `0x1c + frame[0x1c] == 0x3a` (the length field puts the checksum exactly
where the shim writes it).

Live confirmation, leg `steady1`, the one change-gated `IN` line of the run:

```
IN p1=00000000 p2=00000000 crc=00000022 n=000001bb
```

`crc=0x22` is the captured idle frame's own checksum byte, recomputed at
runtime by the shim from a real (idle) pad read — and it never changed for the
rest of the leg.

### `dc_to_jvs` re-verified against `input-map.md`

Bit for bit, before wiring (`shims/src/jvs.c`, `shims/test/test_host.c`):

| DC pad (`input-map.md` §DC pad layout) | `CONT_*` (KOS `controller.h:102-112`) | JVS word (measured, `input-map.md`) |
| --- | --- | --- |
| Start | `BIT(3)` | `0x8000` |
| D-pad / analog Up, Down, Left, Right | `BIT(4)`…`BIT(7)` | `0x2000`, `0x1000`, `0x0800`, `0x0400` |
| A | `BIT(2)` | `0x0200` M (Main) |
| X | `BIT(10)` | `0x0100` S (Sub) |
| Y | `BIT(9)` | `0x0080` Barrage |
| B | `BIT(1)` | `0x0040` A (Action) |
| R trigger ≥ 128 | `BIT(16)` (synthetic) | `0x0020` OverDrive |
| L trigger | — | unbound |
| — | — | `0x4000` Service: defined, no binding |

All ten mapped rows are `input-map.md`'s **measured** bits (11 of its 13 rows
are measured; the two source-derived ones, Test and Coin, are the two this port
does not drive).

### EEPROM — a RAM copy, session-only

`mie_86` now serves sub `0x03` from a 132-byte RAM copy of the baked reply
(4-byte maple header + the 128-byte image) and applies sub-`0x0b` writes into
it, so a write is visible to the next read:

- **sub `0x03` (read).** `address` is a byte offset, `dma_buffer_in[1] % 128`,
  and only `128 - address` bytes are written while the declared word count
  stays `0x20` (`maple_jvs.cpp:1931-1940`). The shim reproduces that; every
  read in the capture asks for `0`.
- **sub `0x0b` (write).** Payload in descriptor coordinates (Flycast's
  `dma_buffer_in` = `desc + 0x0c`, `maple_jvs.cpp:1899-1908`): `[+0x0d]` byte
  address, `[+0x0e]` size, `[+0x10…]` data. **Bounded exactly as the emitter
  bounds it** — `address % 128`, `size` clamped to the end of the image — so a
  malformed frame cannot walk off the 128-byte copy. The ack is
  `87 00 20 01` + the image's first 4 bytes (`:1924-1927`).
- **sub `0x01`** stays a canned blob: it is a fixed `87 00 20 01 | 02 00 00 00`
  ready-ACK, image-independent (`maple_jvs.cpp:1972-1978`).

**Session-only, by construction.** There is no backing store on this port — the
EEPROM lives on the MIE, which does not exist on a Dreamcast, and the shim has
no VMU/flash writer — so settings changed in the game's own test menu hold
until power-off and then revert to the baked image. That is acceptable because
the one setting the port depends on (free play) is baked in.

**The reconstruction caveat still applies.** Bytes 60…127 of the baked image
are *derived* from the Naomi dual-copy layout, not captured (Task 11,
`extract_mie_blobs.py` `rebuild_sub03`); they were verified byte-identical
against the EEPROM Flycast itself saved for this ROM, which is a different code
path but not a capture. Every claim below about image **bytes 0…59** — which is
where the whole system section, and free play, live — rests on captured bytes.

### FREE PLAY — the evidence chain

The plan's step 3 (an operator Naomi leg that *sets* Free Play in the test
menu, then re-bake the post-write image) was **not run, and is not needed**:
the baked image already carries free play, and the DC build already shows it.

1. **The byte.** Image byte **`9` = `0x1a`** (and its dual-copy twin, byte
   `27`) — read straight out of the shim's baked image, whose source is the
   captured sub-`0x03` reply in `captures/phase4/pc2.log` (§EEPROM replies
   decodes the same frame).
2. **What that byte is.** The Naomi system section is
   `[0..1] CRC | [2] attract-sound | [3..6] 4-char game serial | [7..17] 11
   bytes of settings`, duplicated at `+18`. The **third** of those 11 settings
   bytes — image byte `9` — is the coin assignment, zero-indexed:
   > "It is zero-indexed, so coin assignment #1 is mapped to `0x00` and coin
   > assignment **#27 (free-play) is mapped to `0x1A`**."
   > — `../cleopatra/tools/netboot/docs/naomi.md:180` (layout verified there
   > against nulldc/demul/MAME and one de-soldered MIE EEPROM dump)
   Corroborated by the emulator's own layout comment
   (`../flycast4naomi2dreamcast/core/hw/naomi/naomi_flashrom.cpp:96-114`), whose
   line for this byte is quoted here **in full**:
   > ```
   > // 8	b0: coin chute type (0 common, 1 individual)
   > //      b4-5: cabinet type (0: 1P, 10: 2P, 20: 2P, 30: 4P)
   > // 9	coin setting (-1), 27 is manual
   > // 10   coin to credit
   > ```
   > and the writer `write_naomi_eeprom` at `:117`, which keeps both copies and
   > the CRC in sync.
   >
   > **The two sources agree on the encoding and disagree on the label for
   > setting 27.** Both say byte `9` is the coin setting stored zero-indexed
   > (`setting − 1`), so `0x1a` = setting **27** either way. `naomi.md` calls
   > setting 27 *free-play* (twice: `:180` and `:40` "1-27 correspond to
   > standard coin settings and 28 corresponds to manual coin setting. Just
   > like in the system settings, 27 is free-play"); the emulator comment's
   > "27 is manual" reads either as *stored* 27 (`0x1b`) = manual — which
   > matches `naomi.md:40`'s setting 28 exactly, both sources then agreeing —
   > or as *setting* 27 = manual, which contradicts it. The comment alone
   > cannot settle which it means, so **this KB does not treat it as
   > independent confirmation of the word "free-play"** — only of the encoding.
   > What settles the meaning is `naomi.md`'s explicitness, its
   > game-side mechanism (item 3), and item 7: `FREE PLAY` on the target's own
   > screen.
   senkosp's image decodes cleanly against that layout regardless: serial
   `"BMP0"` at `[3..6]`, `0x10` attract-sound-on at `[2]`, `0x10` = 2P cabinet +
   common chute at `[8]`, `0x1a` at `[9]`, `01 01 01` at `[10..12]`.
3. **The game reads it.** The same document names the mechanism: the game
   parses the EEPROM into a settings struct and "loads this and compares it
   against `0x1A` at some point to see if the system is in free-play mode"
   (`naomi.md:202`).
4. **On the target, through THIS build's EEPROM path.**
   `docs/kb/img/phase4-dc-steady.png` — the headless framebuffer grab from the
   **release** leg `steady3-release` — shows **`PRESS 1P OR 2P START BUTTON`**
   and **`FREE PLAY`** on senkosp's attract screen. That is the load-bearing
   one: this section rewrote the sub-`0x03` handler to serve a *RAM copy*, and
   this screenshot is free play arriving through the rewrite.
   `docs/kb/img/phase4-dc-attract.png` (Task 11, the canned-blob path) shows
   the same string from the same image and is the earlier, independent
   instance. The chain is closed on the real target, not on paper.
5. **The image is internally valid, so the game has no reason to reset it.**
   Both Naomi EEPROM CRCs recompute correctly against the emulator's own
   `eeprom_crc` (`naomi_flashrom.cpp:26-51`, CRC-16 seeded `0xdebdeb00` with a
   trailing round):

   ```
   system section  CRC over image[2..17]  = 0x6e9d ; stored copy1 = 0x6e9d, copy2 = 0x6e9d
   game section    CRC over image[0x2c..0x3b] (len 16, from the header at 0x24)
                                          = 0x1e1c ; stored = 0x1e1c
   ```

   Both match, both copies agree, and the serial at `[3..6]` is `"BMP0"` —
   which is exactly the state `naomi.md:172` says stops the wipe-and-re-init
   path (bad CRC on both copies, or a serial that does not match the game).
   The rest of the section decodes cleanly too: `[2]` `0x10` attract sound on,
   `[8]` `0x10` = 2P cabinet + common chute, `[10..12]` `01 01 01`, `[13]` `00`,
   `[14..17]` `11 11 11 11`.
6. **The game does not overwrite it.** Legs `steady1`/`steady2` record **zero**
   sub-`0x0b` writes (`EE WR` count 0) — senkosp read the image and accepted
   it.

**Residual risk, and it is the operator's leg to close.** The *display* and the
*credit gate* need not be the same flag. Cleopatra's Task 18 found precisely
that split — the free-play flag its credit display **and** its
credit-decrement gate read was a settings-struct field at `+0xc`, while the raw
coin byte landed at `+0x10` (`../cleopatra/docs/kb/phase4-conversion.md`
§Task 18), matching `naomi.md:202`'s "4 longs into the settings structure".
senkosp's attract shows the free-play *string*, which is strong evidence the
parse produced free play, but only pressing Start with no credit proves the
gate. That is criterion 5 and it needs a controller — see §Pending operator
verifications.

A control test (flip byte 9 to a coin setting, confirm the attract line
changes) was considered and **not run**: bytes 2…17 are CRC-protected — the
recomputation above proves it concretely — so a flip is not a one-byte edit.
It needs the CRC recomputed in both copies, or the game re-initialises the
section and the experiment measures the wrong thing. The two independent
layout sources, the validated CRC, and the on-target screenshot already carry
the claim; the one thing none of them can carry is the *gate*, which is the
operator's leg.

### Buses 1 and 2 stay "no device" — decided, with the reason

Task 11's finding 2 asked Task 12 to re-check this once real pads existed.
**Answer: unchanged, and now positively justified.** The game's steady engine
polls buses 1 and 2 (`cmd 09`, recipients `0x60`/`0xa0`) about once per frame;
the shim answers `0xffffffff`, Flycast's own missing-device marker
(`maple_if.cpp:315-320`).

- **A real Naomi has nothing there.** The emulator attaches
  `MDT_NaomiJamma` on bus 0 and *then*, for Naomi 1 games only, a
  `MDT_SegaController` + `MDT_SegaVMU` pair on buses 1 and 2 under the comment
  "Connect VMU B1 / Connect VMU C1"
  (`../flycast4naomi2dreamcast/core/hw/maple/maple_cfg.cpp:236`, `:265-272`) —
  emulator scaffolding so memory-card devices can exist, not Naomi hardware.
  The game shipped on cabinets where those buses answer nothing, so it cannot
  depend on them.
- **The game reads input from JVS, not from those buses.** Every control
  senkosp uses arrives inside the MIE's JVS frame (§Input ABI, `input-map.md`).
  The shim's own GetCondition transactions are a *different* conversation on
  the real DC maple bus, invisible to the game.
- Attract is unaffected in every leg, with the tripwires silent.

Correcting this would mean *feeding the game DC controller replies it never
sees on real hardware* — strictly more risk, zero gain. One line
(`maple_frame`'s `bus != 0 || reci != 0x20` gate) if evidence ever demands it.

### Sub `0x15` keeps its canned reply — measured, not assumed

An unmatched sub-`0x15` receive is a JVS digital read too (`mie_jvsdflt`
decodes as `E0 00 07 | status 01 | report 01 | test 00 | P1 00 00 | 00 | crc
09`), and Cleopatra built that one live. senkosp does not need it: in
`captures/phase4/pc2.log` the **last** sub-`0x15` is at line 14,071 and the
**first** sub-`0x33` at line 14,104 — the poll switches once, at enumeration's
end, and sub-`0x33` then runs to the end of the leg (15,800 of them, through
attract). `input-map.md` §"Why no MIE sub=15 byte.bit" measured the same thing
from the other side: zero sub-`0x15` across every button hold. The one context
that revives sub-`0x15` is a **Test-menu** re-handshake, and Test has no
binding on this port. Upgrade path if that changes: the same `+0x1f`/`+0x20`
offsets apply, with the checksum at `0x1c + frame[0x1c]` (7 → `+0x23` for that
frame), not the fixed `+0x3a`.

### Generator entries

**None added.** Task 11 wired the whole maple table — MAPLE-BASE, the 17 pool
repoints, the five detour hooks and MAPLE-KICK-HOOK's two `ptr()` rows — for
both images: `120 entries, 60 per image`, unchanged here. There is no
steady-path word left pending; the steady engine reaches every register
through `base->[0x10f4] + disp`, so entry 1 alone carries it (§Completeness
accounting). `make test` still reports `OK (a) old-byte fidelity (120 rows)`.

### Leg chain

Diagnostic legs are Task 8's recipe (`LOADER_SERIAL=1`, shim
`DEFS='-DSHIM_SERIAL=1 -DSHIM_TRACE=1'`), reverted before commit. Both legs
below are **unattended and input-free** — the operator was away, so no leg here
presses anything. That is by design: an idle pad is precisely the control that
proves the real-pad path did not disturb attract.

| leg | build | outcome |
| --- | --- | --- |
| `steady1` | diagnostic, real pads live | attract cycles unchanged; the numbers below |
| `steady2` | + `hdrA`/`hdrB` in the `IN` trace | reproduction; both pad reply headers healthy |
| `steady3-release` | **release config** + `FLYCAST_SHOT` | 10,169 frames, 0 resets, 0 game-PC maple DMA; the `FREE PLAY` screenshot |
| `steady4` | + opposed-direction mutual exclusion (review fix) | idle behaviour unchanged: same `IN` line, same `crc=0x22`, 0 resets |

`steady1`, verbatim counters (handoff at cartlog line 14,332, all figures
post-handoff):

```
345      MB boot transactions          (the Naomi count, exactly, as Task 11)
14,336   maple services (MS n=3800)
15,202   frames rendered
30,406   C2D list transfers, 8,822 of them > 4 KB   (real geometry)
89       CART streams                  (attract4/attract7's 89, same sequence)
 1       IN line   -> IN p1=00000000 p2=00000000 crc=00000022 n=000001bb
 0       EE WR     (the game never wrote the EEPROM)
 0       MIE skip / MIE odd / SHIMERR / System reset requested
```

**The pad transactions, from the emulator's own side of the wire** (the same
leg's cartlog, post-handoff):

```
MDODMA enter … pc=8c011274   2       probe_devinfo  (one DEVINFO per port, once)
MDODMA enter … pc=8c0112ec   25,585  } maple_getcond — two dynarec blocks of
MDODMA enter … pc=8c01132c      981  }   the same function
                             ------
                             26,568  = 2 (DEVINFO) + 26,566 GetConditions

rawdma_call cmd=09 reci=20 bus=0   13,283   port A
rawdma_call cmd=09 reci=60 bus=1   13,283   port B      <- exactly equal
rawdma_ret  outlen=10              26,566   ALL of them  <- 16 B = 4 words
```

Three things that reads off, none of them assumed:

1. **Every GetCondition succeeded.** `maple_getcond` retries once on a
   non-`DATATRF` reply, so a failure would show as *unequal* per-port counts
   and a doubled DMA total. The counts are exactly equal and exactly
   `2 × 13,283`, and every single reply is `outlen=0x10` — 4 words: header,
   function code, and the two `cont_cond_t` words `dc_cond_to_pressed` reads.
   **Zero retries in 13,283 polls per port.**
2. **The two DEVINFO probes both answered** (`outlen=0x74`, a full device
   status), so Flycast's DC profile has a pad on A *and* B — which is why the
   P2 slot is exercised in this leg too, not just P1.
3. **No real maple DMA from any game PC.** Every post-handoff `MDODMA` PC is a
   shim symbol (`shim.map`: `8c011274 probe_devinfo`, `8c0112ec maple_getcond`);
   the loader/KOS PCs (`8c0152fc`, `8c015584`, `8c0c10ae`) all stop before the
   handoff line. Cleopatra's lesson (b) still passes with live pads — the
   game's maple accesses land in the mirror, and the only traffic on the real
   bus is the shim's own.

**Task 11's residual risk 1 is closed a second time, for free.** These are real
maple DMAs on the true registers, so Flycast's `maple_schd()` raises
`holly_MAPLE_DMA` (`maple_if.cpp:375-401`) 26,568 times in this leg, into a
game that has the interrupt enabled (`IML4NRM` bit 12). Nothing observable
changed — same 89 streams, same attract, zero resets. `attract7` predicted this
with a deliberate experiment; the input path now demonstrates it as a
by-product.

### `steady3-release` — the release configuration, and the screenshot

Committed defaults (`LOADER_SERIAL 0`, no shim `DEFS`), unattended, no input.
Its stdout carries **zero** shim serial output, so everything below is from the
cartlog alone (handoff at line 14,136):

```
10,169  frames rendered post-handoff
20,340  C2D list transfers, 5,784 of them > 4 KB
     0  System reset requested
post-handoff MDODMA PCs:  8c010fb8 (2)   = probe_devinfo   } shim.map, release
                          8c011030 (20,076) \ maple_getcond} build addresses
                          8c011070    (362) /
pre-handoff  MDODMA PCs:  8c015300, 8c015588 (loader), 8c0c10ae (KOS)
GetCondition frames: 10,219 port A / 10,219 port B, all 20,438 replies outlen=10
```

Again: **no game PC ever touches the real maple registers**, in the shipping
configuration, with live pads.

**`docs/kb/img/phase4-dc-steady.png` (committed)** is a headless framebuffer
grab from this leg (`FLYCAST_SHOT` + one `kill -USR1`, `gui_dumpFramebuffer`,
`../flycast4naomi2dreamcast/core/ui/gui.cpp:510-545` — no macOS screen-capture
permission needed; the Task 8/11 precedent). It shows senkosp's attract
prologue with **`PRESS 1P OR 2P START BUTTON`** and **`FREE PLAY`** — i.e. the
EEPROM the game parsed came from the shim's *RAM copy* (this section's rewrite
of the sub-`0x03` handler), not from Task 11's canned blob, and free play
survived that rewrite.

### Pending operator verifications

**Resolved 2026-08-23 — criteria 2/3/5 all MET.** Legs `play1`, `play1-revert`,
`play2p` run and evidenced; full results, per-leg log evidence and operator
attestations: §Operator legs — gate closure (2026-08-23) below. This
subsection's commands are left as-is below (historical — they specify the
diagnostic-build procedure; the operator legs that actually ran used the
**release** build instead, per the note in the results section).

None of the following can run unattended — each needs a human at the controls.
Commands are exact; run them from the repo root with the diagnostic build
(`loader/main.c` `LOADER_SERIAL 1`, `make -C shims clean && make -C shims
DEFS='-DSHIM_SERIAL=1 -DSHIM_TRACE=1'`, `make gdi`), and **kill by PID**
(`kill -9 $(pgrep -f "Flycast.app/Contents/MacOS/Flycast")`), then wait for the
`.stdout.log` size to settle before reading it — `pkill -f "flycast-src.*Flycast"`
does not match the process (§Attract, finding 4).

| # | leg | what to do | evidence it yields |
| --- | --- | --- | --- |
| 1 | `scripts/capture_dc_leg.sh phase4/play1` | Start, then a full 1P match; press **every** control at least once (D-pad **and** analog stick, A, X, B, Y, R, Start) | criterion 2. Each press must produce an `IN p1=…` line whose `p1` word matches `input-map.md`'s measured bit for that control; `hdrA` must read `…08` on every line |
| 2 | `scripts/capture_dc_leg.sh phase4/play2p` | second pad in port B: 2P entry + a match | criterion 3. `IN … p2=…` lines with the same bit table; `hdrB` `…08` |
| 3 | (inside leg 1) | at the title screen press **Start only**, no coin | criterion 5. A game must start. This is the one claim the free-play evidence chain cannot close on its own — see §FREE PLAY residual risk |
| 4 | (inside leg 1) | after the match, quit and relaunch | confirms the session-only EEPROM is acceptable: settings revert to the baked image, free play still on |

Per-leg greps:

```sh
tr '\r' '\n' < captures/phase4/play1.stdout.log > /tmp/p.txt
grep '^IN '  /tmp/p.txt          # one line per input change; p1/p2 = the JVS word
grep -c 'MIE odd\|MIE skip\|SHIMERR\|System reset requested' /tmp/p.txt   # must be 0
```

If a control produces no `IN` line at all, `hdrA`/`hdrB` on the surrounding
lines split the two failure modes: `…08` = the pad was read and the mapping is
wrong (fix `dc_to_jvs`); `ffffffff` or `00000000` = the transaction failed
(fix `maple.c`).

**Not run, and deliberately not needed:** the plan's step-3 Naomi leg where the
operator sets Free Play in the test menu and the post-write image is re-baked.
The baked image already carries free play (§FREE PLAY) and the game never
writes the EEPROM (`EE WR` 0 in every leg), so that leg would re-bake bytes
identical to the ones already shipped.

### Findings worth carrying forward

1. **Both DC maple ports answer in Flycast's DC profile**, so P2 is live in
   unattended legs whether or not a second human is present — an idle port-B
   pad reads as `p2=0`, indistinguishable from "no pad", which is why the
   `hdrB` field exists.
2. **The EEPROM is session-only** and nothing has asked it not to be. If a
   later task wants persistence, the write path is already the single choke
   point (`mie_86` case `0x0b`) and a VMU or flash writer plugs in there.
3. **An analog stick that reports `0x00` on unused axes would read as a
   permanent up+left.** Every DC pad reports `0x80`-centred axes and Flycast's
   own controller does (`maple_devs.cpp:96-114`), so this is a real-hardware
   (Phase 5) risk with a clone-pad, not an emulator one. Upgrade path if it
   bites: `probe_devinfo` already fetches the device's capability word — gate
   the analog fold on the "has analog axes" bit rather than always folding.
4. **The `IN` trace is change-gated**, so a leg with a stuck button prints once
   and goes quiet. That is the intended shape (it makes a 4-minute leg readable),
   but "no `IN` lines" means "nothing changed", not "nothing was pressed".
5. **PHASE 5, REAL HARDWARE: the per-poll pad read is unthrottled, and Cleopatra
   already hit exactly this.** `mie_poll` issues **two blocking** GetCondition
   DMAs on every sub-`0x33`, unconditionally. In Flycast that is free — the
   emulator's memory and maple are instant, which is why no Phase 4 leg can
   ever observe the cost — but on the wire each transaction is real: ~0.5–1 ms
   at the DC bus's 2 Mbps plus fixed per-transaction overhead. Measured rate
   here: **13,283 polls / 15,202 frames = 0.87 polls per frame × 2 ports**, so
   roughly **1–2 ms of blocking per 16.6 ms frame**, spent inside the game's own
   maple service.
   The sibling port found this the hard way and its fix is sitting `#if 0`'d in
   `shims/src/main.c` (the Cleopatra reference block, `jvs_digital`): a
   **TCNT0-keyed ~8 ms cache** —
   ```c
   u32 now = TCNT0;
   if (in_tcnt - now > pad_thresh) {        /* down-counter: elapsed = last - now */
       in_tcnt = now;
       raw_cache_a = maple_getcond(0);
       raw_cache_b = maple_getcond(1);
   }
   ```
   with `pad_thresh` derived from `TCR0`'s prescaler (`(50000000 >> shift) / 125`
   = ticks per 8 ms). Its recorded symptom was "2P mode very slow on real HW
   only" — instant in Flycast, visible on hardware.
   **Not applied now, deliberately**: it is a hardware mitigation with no
   observable effect on this phase's target, and adding it blind would ship
   untested timing code plus a second input-latency behaviour that no leg here
   can compare against. It is the *first* thing to try if the Phase 5 hardware
   round reports input lag or slow 2P, and the code to copy is in this repo.
6. **A future EEPROM re-bake must use the PADDED record size.** The game
   section's header is `[0x24..0x25] CRC | [0x26] record size | [0x27] record
   padded size`, and the emulator annotates 39 (`= 0x27`) with "crc is done on
   this" and uses `EEPROM[39]` for *both* the duplication stride and the CRC
   span (`naomi_flashrom.cpp:86-94`, `:127-134`).
   `scripts/extract_mie_blobs.py` originally duplicated with `[0x26]`; it now
   uses `[0x27]` and asserts `[0x27] >= [0x26]`. In senkosp's image both are
   `0x10`, so the emitted blob is **byte-identical either way** (verified by
   diffing the generated file across the change) — this is a correctness point
   for a re-bake against some other image, not a change to what ships today.

### Reproduction

```sh
python3 scripts/extract_mie_blobs.py     # incl. the idle-frame equivalence assert
make test                                # incl. dc_cond_to_pressed host tests

# diagnostic build + unattended leg (revert LOADER_SERIAL before committing)
make -C shims clean && make -C shims DEFS='-DSHIM_SERIAL=1 -DSHIM_TRACE=1'
make gdi && scripts/capture_dc_leg.sh phase4/steadyN &
# ... then: kill -9 $(pgrep -f "Flycast.app/Contents/MacOS/Flycast")
# ... and wait for the .stdout.log size to settle before reading it

tr '\r' '\n' < captures/phase4/steadyN.stdout.log > /tmp/s.txt
grep    '^IN '      /tmp/s.txt   # idle pad must show crc=00000022, hdrA/hdrB …08
grep -c '^MB n='    /tmp/s.txt   # 345
grep -c 'MIE odd\|MIE skip\|SHIMERR\|System reset requested' /tmp/s.txt   # 0

# the pad transactions, from the emulator's side (post-handoff lines only)
H=$(grep -n MMUCRWR captures/phase4/steadyN.log | grep -o '^[0-9]*:.*pc=8c01[0-9a-f]*' \
      | tail -1 | cut -d: -f1)
awk -v h=$H 'NR>h && /MDODMA enter/' captures/phase4/steadyN.log \
  | sed 's/.*pc=\([0-9a-f]*\).*/\1/' | sort | uniq -c      # shim PCs ONLY
awk -v h=$H 'NR>h' captures/phase4/steadyN.log \
  | grep -c 'rawdma_call cmd=09 reci=20 bus=0'             # == the reci=60 count
awk -v h=$H 'NR>h' captures/phase4/steadyN.log \
  | grep -A1 'rawdma_call cmd=09' | grep rawdma_ret | sort | uniq -c   # all outlen=10
```

## Test menu — round trip (Task 13, criterion 4)

**Criterion 4:** combo boot → test menu renders and navigates → exit →
console reboot → main boot to attract. The operator was AFK for the whole
task, so this section proves everything that does not need hands: the
input mapping, the test-image sub-table's completeness, the exit path's
readiness, and — via a transient diagnostic build — that the test image
boots and its own menu renders. The hold/navigate/exit leg itself is handed
to the operator below.

### Test-mode input mapping

`shim_maple_service`'s per-frame poll (`mie_poll`, `shims/src/main.c`) now
branches on `SHIM_STATE[0]` (seeded by Task 10's boot combo,
`loader/main.c`'s `*(uint32 *)(STAGE_SHIM + (SHIM_STATE - SHIM_BASE)) =
(uint32)test_boot`, unchanged this task — verified live before writing any
code):

```c
if (UW(SHIM_STATE) == 1u) {         /* test boot: P1 Start->Test, A->Service */
    unsigned test_bit;
    j1 = dc_to_jvs_test(maple_getcond(0), &test_bit);
    f[0x1f] = (u8)(test_bit ? 0x80 : 0x00);
} else {
    j1 = dc_to_jvs(maple_getcond(0));   /* DC port A -> P1 */
}
j2 = dc_to_jvs(maple_getcond(1));       /* DC port B -> P2, unchanged in both modes */
```

`dc_to_jvs_test` (`shims/src/jvs.c`, pure, host-tested) is the whole new
policy:

```c
unsigned dc_to_jvs_test(unsigned dc_buttons, unsigned *test_bit) {
    *test_bit = (dc_buttons & CONT_START) ? 1u : 0u;
    return dc_to_jvs(dc_buttons & ~(CONT_START | CONT_A))
         | ((dc_buttons & CONT_A) ? JVS_SERVICE : 0u);
}
```

Three decisions, each pinned against §Input ABI / §TESTBIT-INJECT rather
than the brief's shorthand:

1. **Test is not folded into the 16-bit P1/P2 word.** The brief names it
   "bit 18" because that is the emulator's *internal* kcode constant
   (`NAOMI_TEST_KEY == 1<<18`, `maple_devs.h:97`) — a bit position in
   Flycast's own digital-input abstraction, not a wire offset. The actual
   has-data frame carries Test in its own byte, `+0x1f` bit 7
   (`maple_jvs.cpp:2243`), which is exactly what §TESTBIT-INJECT's verdict
   already warned about: "a shim that sets `1 << 18` … somewhere in a
   16-bit word would be silently wrong." So `dc_to_jvs_test` reports Test
   through an out-param, and `mie_poll` places it at the pinned frame byte
   itself — never OR'd into `j1`.
2. **Service genuinely is a word bit** (`0x4000`, byte `+0x20` bit 6, the
   same byte Start's `0x8000` lives in — input-map.md's measured bit,
   §TESTBIT-INJECT: "Service *is* a bit") — so unlike Test it is folded
   into the returned word like any other control.
3. **P1 only, and only Start/A change.** `dc_buttons & ~(CONT_START |
   CONT_A)` is passed straight through the *existing* `dc_to_jvs`, so
   D-pad/X/B/Y/R keep their live game bindings in test mode too ("leave the
   rest of the layout live" per the task brief) — reusing the one function
   Task 12 already host-tested rather than duplicating its table. P2 is not
   touched at all: `j2 = dc_to_jvs(maple_getcond(1))` is the exact Task 12
   line, unconditional, in both modes. This is a P1-only decision, not
   proven from a source — arcade Test/Service buttons are operator-panel
   hardware, one pair per cabinet, not per player, and pad 1 is the same
   pad the boot combo itself reads — recorded as a decision, not a citation.

**Normal-mode regression is by construction, not just by test:** the
`else` branch is the literal line Task 12 shipped, so a normal boot takes
an *identical* instruction path to before this task — the only new
runtime cost is the `SHIM_STATE[0]` read itself. `make test`'s idle-frame
equivalence assert (`scripts/extract_mie_blobs.py`) does not exercise
`SHIM_STATE` at all (it asserts the *build-time* transform on the captured
blob) and still passes; the live confirmation is the `teststatic1` leg
below.

Seven new host asserts (`shims/test/test_host.c`) pin `dc_to_jvs_test`
directly: idle, Start-only (Test, no `JVS_START` leak), A-only (Service, no
`JVS_M` leak), both held, a D-pad control alone (rest of the layout live),
Start layered on a D-pad press (Start still doesn't leak into the word),
and X/B/Y/R together (unaffected). `make test`: `PASS test_host dc_to_jvs +
jvs_checksum`.

### Test-image sub-table completeness audit

The brief asked for an audit against the KB's own accounting, not new
generator code, and that is what this found: **both images' test columns
were already fully dispositioned before this task touched anything.**

| table | main | test | disposition |
| --- | --- | --- | --- |
| §Cart-patch sites, 32 raw words | 32/32 | 32/32 | 1 CART-BASE repoint + 28 own `pool()` entries + 3 written exemptions, both images (§Cart-patch sites Completeness accounting) |
| §Cart-patch sites, entry hooks | 4/4 | 4/4 | CART-WAIT-A/B, CART-BOOT-DMA, CART-PIO-READ, both images |
| §Maple-patch sites, 20 raw words | 20/20 | 20/20 | 1 MAPLE-BASE repoint + 17 own `pool()` entries + 2 written exemptions, both images (§Maple-patch sites Completeness accounting) |
| §Maple-patch sites, hooks | 6/6 | 6/6 | MAPLE-KICK-HOOK `ptr()` + 5 boot detours, both images |
| §Restart stub, RESET-PATCH | 1/1 | 1/1 | `scripts/build_patch_table.py:470-471` — main dat `0x47e4c`, **test dat `0x1a4678`** (§Restart stub's pin, Task 10 wired both, re-verified present by line number above) |

Cross-checked against the generator's own output, unchanged by this task:

```
OK patch_table.h: 60 main + 60 test patches (reloc seeds + CART-* repoints/hooks
+ MAPLE-* repoints/detours + RESET-PATCH); G1_MIRROR_P2=0xac014800
MAPLE_MIRROR_P2=0xac015000
```

60 = 60 across both images, and `make test`'s own accounting agrees: `OK (a)
old-byte fidelity (120 rows), (b) img tagging (60 test-image rows)`. **No
entry was missing; `scripts/build_patch_table.py` was not modified.** The
audit's job was to *prove* completeness, not assume it from Task 9–11's
prose — done by re-reading both Completeness accounting tables and the
RESET-PATCH pin line-by-line above, and independently by the diagnostic
leg below, which applies all 60 test-image entries at runtime with zero
`PATCH MISMATCH`/`PATCH IMG MISMATCH` (`patches OK`, `patch table: 60 main
/ 60 test entries (applied: test)`).

### Exit-path readiness

The test menu's SYSTEM MENU EXIT drives senkosp's own restart stub
(`FUN_8c067e18`'s test-image twin, §Restart stub) → the patched jump target
(RESET-PATCH, dat `0x1a4678`) → `shim_reboot()` → `((void
(*)(void))0xa0000000)()`, i.e. the SH-4 reset vector through P2 — the same
mechanism Task 10 proved fires (`entry2`/`entry3`'s reboot loop, `entry3`'s
freeze-frame naming the exact restart call chain). Nothing about this path
is test-image-specific: §Restart stub already established that the restart
stub's opcode bytes, including the one `jmp` that matters, are
byte-identical between images except four relocation-dependent pool words,
none of which is the jump target. **This task did not need to add
anything to make the exit path work — it was already wired by Task 10 —
only to confirm, for the operator, what "it worked" will look like.**

**The honesty note the brief asked for, restated precisely:** on real
Naomi hardware, "restart" re-enters the BIOS, which re-runs the Naomi boot
sequence and lands back at whichever image the operator's DIP switches (or
last boot combo) select. On this Dreamcast conversion, "restart" is a jump
to `0xa0000000` — the DC BIOS ROM entry, exactly where the CPU lands out of
a real hardware reset. **What the operator should expect and both count as
success:**

- **Most likely (matches Task 10's four observed reboot cycles):** the
  screen goes black, the DC BIOS runs its own boot sequence (swirl / Sega
  TM screen), and it re-boots the GD-ROM — landing back at the loader,
  which re-reads pad state fresh. If A+Start is not still held at that
  point (it should not be — the operator already exited the combo to
  navigate the menu), the loader selects the **main** image, and the game
  proceeds to attract. This is the literal criterion: "exit → console
  reboot → main boot to attract."
- **Also acceptable (the brief's named fallback):** Flycast's DC profile
  parks in its own BIOS file-manager/menu screen instead of immediately
  re-invoking the GDI's `1ST_READ.BIN`. If the disc is bootable from that
  screen (as Task 8's GDI mastering verified — a plain DC-profile boot
  already reaches the loader once), that still satisfies the reboot
  contract: the console left the game and came back through the BIOS, the
  same reset instruction real hardware would take. The note travels to
  Phase 5 rather than blocking this criterion, per the brief.
- **Failure, not either of the above:** a hang, a black screen that never
  recovers, or a crash signature (Flycast's `Verify Failed` class of
  message). That is a real finding, not a variant of success — apply the
  debug-loop protocol and record it.

### Diagnostic-leg evidence

Two unattended legs, both diagnostic builds (`LOADER_SERIAL=1`, shim
`DEFS='-DSHIM_SERIAL=1 -DSHIM_TRACE=1'`), both reverted before commit and
re-verified by a clean release rebuild + `make test` afterward.

**`teststatic1` — regression: normal (no-combo) boot is unaffected.**
Same evidence standard as Task 12's `steady4`:

```
boot: MAIN image
IN p1=00000000 p2=00000000 crc=00000022 hdrA=03230008 hdrB=03634008 n=000001bb
345   MB boot transactions      (the Naomi count, exactly, as every prior task)
0     MIE odd / MIE skip / SHIMERR / System reset requested
1     HANDOFF -> game
49    CART off= streams observed in the ~85s window (attract asset loads)
```

Post-handoff, from the emulator's side of the wire (`H` = the loader's own
final MMU-off `MMUCRWR`, the same marker Task 12's reproduction recipe
uses):

```
post-handoff MDODMA PCs: 8c0112d4 (probe_devinfo, x2), 8c01134c (maple_getcond,
  x5,323), 8c01138c (maple_getcond's second dynarec block, x317) -- shim.map
  symbols only, no game PC (Cleopatra's lesson (b) still holds)
rawdma_call cmd=09 reci=20 bus=0: 2,820  ==  reci=60 bus=1: 2,820   (0 retries)
rawdma_ret outlen=10: 5,640                                        (ALL of them)
TAEND (frames presented): 5,594
```

Byte-for-byte the same idle line Task 12's `steady1`/`steady4` legs
produced (`crc=0x22`, `345`, `0` tripwires) — the strongest form of "the
test-mode branch did not perturb normal mode" available without a second
diff tool: the *output*, not just the source diff, is unchanged.

**`testboot-diag1` — the test image boots and renders its own menu.** A
transient diagnostic define, `LOADER_FORCE_TEST_BOOT` (`loader/main.c`,
same shape and same revert discipline as `LOADER_SERIAL`), forces
`test_boot = 1` with no operator holding anything — sanctioned by the
brief as the `LOADER_SERIAL` precedent (Task 8), one leg, reverted, honestly
documented. The live combo check still runs underneath it unmodified (it
can only ever *set* `test_boot = 1`, never clear the forced value), so a
real A+Start hold keeps working in every other build.

```
boot combo: TEST image
records=5 img=8cd007f8/4dc40 shim=8c010000/8000 kern=8c000600/3200 blob=8c018000/7000
patches OK
patch table: 60 main / 60 test entries (applied: test)
HANDOFF -> game                                          (x1 -- no PATCH ABORT)
IN p1=00000000 p2=00000000 crc=00000022 hdrA=03230008 hdrB=03634008 n=000001bc
MB n=00000159                                            (345 decimal -- same
                                                           boot-transaction count
                                                           as the main image)
MS n=00001a00                                            (6,656 steady maple
                                                           services -- stayed up
                                                           through the whole leg)
0     MIE odd / MIE skip / SHIMERR / System reset requested (whole cartlog)
```

Post-handoff, same shim-only-PC shape as `teststatic1`, larger counts
because this leg ran longer (extended to reach and hold the menu, plus one
`kill -USR1` for the screenshot):

```
post-handoff MDODMA PCs: 8c0112d4 (x2), 8c01134c (x12,113), 8c01138c (x871)
rawdma_call bus=0: 6,492  ==  bus=1: 6,492                          (0 retries)
TAEND (frames presented): 12,982
```

**The screenshot is the decisive piece of evidence**
(`docs/kb/img/phase4-dc-testmenu.png`, `FLYCAST_SHOT` + `kill -USR1`, the
Task 8/11/12 mechanism): senkosp's own **GAME TEST MENU**, listing `INPUT
TEST`, `GAME ASSIGNMENTS`, `BOOKKEEPING`, `BACKUP DATA CLEAR`, `-> EXIT`,
with the game's own instruction line at the bottom —

> **`SELECT WITH SERVICE BUTTON AND PRESS TEST BUTTON`**

— which is independent, in-game confirmation of the exact convention this
task wired (Test advances the cursor, Service selects the highlighted
entry): the game names its own controls, in its own on-screen text,
matching `dc_to_jvs_test`'s Start→Test / A→Service mapping without this
task having asserted anything about menu semantics beyond the brief's
"arcade convention" line. The idle `IN` line (`crc=0x22`, same as normal
mode) is the frame the menu was rendered from: `SHIM_STATE[0]==1` was live,
`dc_to_jvs_test`'s idle output (`test_bit=0`, `j1=0`) is identical to
`dc_to_jvs`'s idle output, so the checksum did not move — confirming the
test-mode branch produces a well-formed frame even before this leg's
screenshot proved the menu draws from it.

Symbol confirmation (`shims/build/shim.map`, this build):
`8c011204 T _dc_to_jvs_test` — compiled in, sized normally (`shim.bin`
6.8 KB / 16 KB budget in both the regression and diagnostic builds, no
change from Task 12).

### Pending operator round trip (criterion 4)

**Resolved 2026-08-23 — criterion 4 MET.** Leg `testmenu-rt` run and
evidenced: combo boot → TEST image → operator navigation → EXIT → full
SH-4 reset → second boot → MAIN image → attract, all in one capture. Full
results: §Operator legs — gate closure (2026-08-23) below. This
subsection's procedure is left as-is below (historical — it is exactly what
the operator followed).

**Not run, and cannot be run without a human**: holding a combo, navigating
a menu by feel, and confirming a reboot lands somewhere specific are all
judgment/timing actions. Exact procedure:

1. **Build** (release is fine — this leg needs no serial output, the
   screen tells the whole story): `make gdi`.
2. **Boot holding A+Start on pad 1** from power-on (or console reset) until
   the test menu appears — `docs/kb/img/phase4-dc-testmenu.png` is exactly
   what to expect (this leg proved the render; only the *hold* is
   untested).
3. **Navigate**: press **Start** to advance the cursor (`-> ` moves down
   the list — `INPUT TEST` / `GAME ASSIGNMENTS` / `BOOKKEEPING` / `BACKUP
   DATA CLEAR` / `EXIT`), **A** to select the highlighted entry (Service).
   Optionally descend into one submenu and back out, to exercise Test
   navigating *inside* a submenu too — not required by the criterion, but
   cheap confirmation that the mapping holds beyond the top menu.
4. **Exit**: navigate to `EXIT` (or the `SYSTEM MENU EXIT` submenu entry
   below the top level, per what the game actually presents) and select it
   with A/Service.
5. **Expect**: the screen goes to the DC BIOS boot sequence (see §Exit-path
   readiness above for the two outcomes that both count as success), then
   the loader runs again with no combo held, selects the **main** image,
   and the game reaches attract — the same attract Task 11/12 already
   proved (`docs/kb/img/phase4-dc-attract.png` /
   `phase4-dc-steady.png` for what "back to attract" looks like).
6. **Evidence to capture**: a screenshot (or phone photo) at three points —
   the test menu on entry, the moment EXIT is selected, and attract after
   the reboot — plus a plain description of what appeared in between (BIOS
   swirl? Flycast's own file-manager screen? anything else?). No serial
   capture is required for this leg; if something goes wrong, *then* switch
   to the diagnostic build (`LOADER_SERIAL=1`, shim
   `DEFS='-DSHIM_SERIAL=1 -DSHIM_TRACE=1'`) and re-run with
   `scripts/capture_dc_leg.sh phase4/testmenu-roundtrip1` for an `IN`/`MB`/
   `MS` trace of exactly where it diverged.

### Findings worth carrying forward

1. **The audit closed clean because Tasks 9–11 already closed it.** This
   task's "sub-table completeness" step found zero gaps — worth recording
   explicitly so a future reader does not re-derive the same 32/32, 20/20,
   1/1 tables from scratch: they are cited above, not re-scanned.
2. **P1-only Test/Service is a decision, not a citation** (§Test-mode input
   mapping, point 3) — if a future task finds the real cabinet wires
   Service to P2 as well (twin-cabinet convention), the fix is one more
   line in `mie_poll`'s test-mode branch, not a redesign.
3. **The reboot's landing screen is genuinely unverified**, same class of
   gap as Task 10's honesty note about the DC profile's reset handling —
   this task added the expected-behavior note per the brief but did not
   (could not) observe which of the two acceptable outcomes actually
   happens.

### Reproduction

```sh
make test                                # incl. 7 new dc_to_jvs_test host asserts

# regression leg (diagnostic build, revert LOADER_SERIAL before committing)
make -C shims clean && make -C shims DEFS='-DSHIM_SERIAL=1 -DSHIM_TRACE=1'
# loader/main.c: LOADER_SERIAL -> 1
make gdi && scripts/capture_dc_leg.sh phase4/teststaticN &
# ... then: kill -9 $(pgrep -f "Flycast.app/Contents/MacOS/Flycast")
# ... and wait for the .stdout.log size to settle before reading it

# diagnostic test-boot leg (same shim; loader/main.c: LOADER_FORCE_TEST_BOOT -> 1)
make gdi
FLYCAST_SHOT=docs/kb/img/phase4-dc-testmenu.png scripts/capture_dc_leg.sh phase4/testboot-diagN &
# ... let it reach the menu, kill -USR1 <pid> for the screenshot, then
# ... kill -9 <pid>; wait for .stdout.log to settle
# revert BOTH LOADER_SERIAL and LOADER_FORCE_TEST_BOOT to 0, rebuild release,
# re-run `make test` before committing

tr '\r' '\n' < captures/phase4/teststaticN.stdout.log > /tmp/t.txt
grep '^IN '   /tmp/t.txt      # idle: crc=00000022, hdrA/hdrB ...08
grep -c 'MIE odd\|MIE skip\|SHIMERR\|System reset requested' /tmp/t.txt   # 0
grep -m1 'boot:\|boot combo' /tmp/t.txt   # confirms which image this leg selected
```

---

## Operator legs — gate closure (criteria 2/3/4/5, O1 upgrade, eeprom_write_seen) (2026-08-23)

**What this closes:** the six operator legs named in
`.superpowers/sdd/2026-08-22-phase4-conversion/task-ops-brief.md` — the
evidence gate criteria 2 (1P play), 3 (2P play), 4 (test-menu round trip)
and 5 (free play) were waiting on. §Shim home above documents the
`shimwatch-play` leg (O1 upgrade to CLEAN). This section documents the
four DC-profile legs and the `pc2-testmenu` Naomi-profile leg.

**Deviation from the diagnostic-build procedure, noted up front.** §Steady
input's and §Test menu's pending-operator sections specify (for `play1`/
`play2p`) or permit (for `testmenu-rt`) a diagnostic shim build
(`LOADER_SERIAL=1`, `DEFS='-DSHIM_SERIAL=1 -DSHIM_TRACE=1'`) so the `IN`/
`MB`/`MS` serial trace can be read from `.stdout.log`. The operator instead
ran all four DC legs against the **committed release build** (HEAD
`1d68ccc`, `LOADER_SERIAL 0`, confirmed by `git show HEAD:loader/main.c |
grep define`) — confirmed independently by grepping every leg's
`.stdout.log`: 0 lines match `^IN |^MB n=|^MS n=` in any of the four
(`play1`/`play1-revert`/`play2p`: 101-line Flycast-boilerplate stdout only;
`testmenu-rt`: 178 lines, same shape). This is **not a defect** — release
is exactly what ships, and criteria 2/3/4/5 ask for "the built GDI"/"the
approved pad layout" (spec §Exit criteria) — but it does mean the per-press
JVS-bit cross-check against `input-map.md` that Task 12's pending-verification
table specified (`hdrA`/`hdrB` `…08`, per-control `IN` lines) **could not be
extracted from these captures**: that level of proof now rests on the
operator's own attestation (quoted below), not a log-level bit decode. The
Flycast-fork cartlog (`FLYCAST_CARTLOG`) is independent of the shim's own
serial output, though, and it **does** show maple/JVS transaction-level
activity (`MDODMA`) regardless of build — which is what the structural
evidence below is built from.

### play1 — criterion 2 (1P full match, free play)

`captures/phase4/play1.log`, 803,325 lines / 24 MB; `.stdout.log` 101 lines
(Flycast's own boot-time HW-register log, silent from 00:17:51 to 00:29:50
— see §Texture-error hang below).

**Boot image, confirmed by a cross-validated PC signature.** The final
`MMUCRWR val=00040005` in every boot ladder — the MMU-on write that ends
loader handoff — carries a PC that differs between images: `pc=8c02d630`
for MAIN, `pc=8c02d518` for TEST (the boot driver sits at a different
address because the two images are separately linked and differently
sized — the same fact §Test menu's own audit already established for
other pools). Calibrated against Task 13's own confirmed-truth legs:
`captures/phase4/teststatic1.log` (confirmed MAIN by its own `boot: MAIN
image` stdout line) ends its boot ladder at `pc=8c02d630`;
`captures/phase4/testboot-diag1.log` (`LOADER_FORCE_TEST_BOOT=1`, confirmed
TEST) ends at `pc=8c02d518`. `play1`'s boot ladder (lines
1/14,032/14,136/14,141) ends at **`pc=8c02d630` — MAIN image**, as expected
for a plain boot with no combo held.

**Structural health, boot → hang:**
```
MMUCRWR: 4 (single boot ladder, lines 1/14,032/14,136/14,141 — no reset until the hang)
MDODMA enter: 36,945, lines 14,141-431,747 (continuous; 0 after line 431,747)
rawdma_call cmd=09 bus=0: 18,749 ≈ bus=1: 18,746 (both ports polled throughout)
rawdma_ret outlen=10: 37,495 (all well-formed GetCondition replies)
TAEND (frames): 87,950 total — 38,406 through line 431,747, 49,544 after
error/abort/mismatch/fail (case-insensitive): 0 matches, whole file
```

No per-leg parser `CHECK` line exists for DC-profile legs (that machinery —
`shim_home_clean`, `dma_pc_in_cart_fn`, etc. — is Naomi-profile-only), so
this is a structural read of the raw markers, consistent with Task 11/12's
established steady-state shape (both ports always polled, well-formed
replies, one clean boot).

**Operator attestation (2026-08-23), quoted verbatim:**
> 1P beginner match played win-lose-win with all controls: dpad, analog,
> A(Main), X(Sub), B(Action), Y(Barrage), R(OverDrive). Initial stick
> up/left dead — operator's own Flycast binding config, fixed by the
> operator, NOT our bug (verified fine in play2p).
>
> dpad⊕analog conflicting directions → character stops, neither direction
> dominates (the mutual-exclusion fix behaving as designed).

**Criterion 2 — MET.** Full win-lose-win match, every control exercised
(operator report), correct image booted, continuous dual-port JVS polling
throughout play, zero resets, zero error strings. The one residual gap (no
per-press bit-level log decode — see the deviation note above) is a
proof-*method* gap, not a functional one: the operator's own report is
direct evidence of the same fact a bit decode would have shown.

### §Texture-error hang (play1)

**Symptom (operator attestation, 2026-08-23):** immediately after winning
the final round of the match, the game hung on a black screen with its own
yellow error text. Screenshot: `docs/kb/img/phase4-dc-texerror.png` — read
directly, confirms **`ERROR !!` / `TEXTURE LOAD ERROR !`**, in senkosp's own
bitmap font, as a small fixed-position 2D overlay (top-left corner) — this
is the *game's own* error-handler text, not a Flycast crash dialog or a
driver panic message. Reported as **intermittent, once in ~6 sessions**.

**What the log shows.** The last `MDODMA` line (maple/JVS activity of any
kind — GetCondition, device probes, everything) is at line 431,747 of
803,325; there are **zero** `MDODMA` lines in the remaining 371,578 lines
(46% of the capture) up to the operator's kill. Over that same tail the
render loop does **not** stop: `PVRW STARTRENDER` fires 24,771 more times
(vs. 18,660 before the freeze — a *higher* rate, consistent with the tail
covering more wall-clock time, corroborated by the `.stdout.log` gap
below) and `TAEND` (frame-complete) fires 49,544 more times. Every
post-freeze frame submits the **identical** pair of TA display lists —
`C2D src=0c17e360 dst=00000000 len=20 w0=00000000` (list `cl=2`) and `C2D
src=0cedbc00 dst=00000000 len=40 w0=808c0002` (list `cl=0`). **This pair is
not hang-specific**: scanning every `C2D` line in the file shows no
`src=` value other than these two appears anywhere after line 14,025 — it
is simply the constant per-frame background/overlay submission for the
*entire* game (a first pass mistook the collapse-to-2-values as evidence of
the hang; it is not, and is not used as evidence below). What *is*
hang-specific is the disappearance of `MDODMA` and, from the `.stdout.log`
timeline, of every other HW-register-write class (AICA `ARMRST`,
`SPG`/`FB_R_CTRL`) — the CPU stopped doing anything except re-triggering
the tile-accelerator/present path each vblank. **Audio register writes
(`SOFWR`) are not usable as freeze evidence**: the whole file has only
1,602, the last at line 20,505 — long before the freeze at 431,747 — so
`SOFWR` is simply rare in normal play, not something that stops *at* the
freeze.

`.stdout.log`'s own timeline corroborates the same freeze point
independently: the last HW-register-write log line (AICA `ARMRST`) is at
**00:17:51.347**; the next and last line in the file is **00:29:50.670**
(`SDL: Joystick … disconnected`, the process-kill signal) — a **12-minute
33-second silent gap** with no PVR/AICA/SH4 register-write log lines at
all, i.e. Flycast's own diagnostic logging independently confirms nothing
interesting happened at the hardware-write level for the entire tail — the
same tail the cartlog shows spinning on one static frame.

**No reset was attempted:** `MMUCRWR` stays at exactly 4 for the whole
file (the one boot ladder) — the game never reached its own restart stub,
consistent with the operator having to kill the process rather than the
game recovering or rebooting on its own.

**"Alive in its error loop" or "fully wedged" — both, in different
senses.** The render/present path is alive (SH-4 still executing, still
kicking `STARTRENDER` every vblank with well-formed TA opcode words); the
maple/input service path is dead (no more `MDODMA` of any kind, not even
the idle poll). This is consistent with the game's own error handler
catching a fault, drawing its fixed error text once, and spinning in a
tight loop that re-presents the same frame without ever returning to the
main per-frame update (which is what would call the maple service again)
— **not** a Flycast-level render-pipeline crash (Flycast's own renderer
keeps accepting and completing display lists throughout) and **not** a
full CPU lockup (the CPU is still issuing well-formed register writes,
just not the input-service ones).

**Evidence this log cannot supply.** This DC-profile capture carries **no**
GD-ROM/cart-stream marker at all — `grep -c '^CARTDMA'` is 0 in every DC
profile leg captured this task. `FLYCAST_CARTLOG`'s cart-DMA probe is
Naomi-cart-specific; on the DC profile the shim's raw-ATA GD-ROM reads
route through Flycast's ordinary IDE/GD-ROM emulation, which this
instrumentation does not tap. **The brief's prime-suspect question — do
the last N cart streams before the hang map to a plausible asset region —
cannot be answered from this log; this is a genuine evidence gap, not a
null result.** Likewise no `SHIMERR`-class marker is available (release
build, no shim serial).

**Candidate causes, ranked, with what would discriminate:**
1. **Cart-stream data integrity under some access pattern** (the brief's
   prime suspect). Textually favored by the fact that the error text is
   senkosp's *own* validated error path (a generic Flycast/driver fault
   would not produce the game's in-fiction error string — reaching it
   requires the game's own code to have detected a bad texture load and
   jumped to its own handler) — but this is an inference from the
   message's provenance, not a proof of *where* the bad data came from.
   **What would discriminate:** a diagnostic-build recapture with a
   cart-read/ATA-transfer probe wired (none exists yet), or the operator's
   offered follow-up leg — a 2P run-all-stages session, which would
   multiply exposure to whatever access pattern triggers this and either
   reproduce it against a loggable read, or fail to reproduce it at all
   (useful either way).
2. **Flycast-side texture cache** (the alternative). Less favored by the
   same reasoning as (1) — a pure emulator-side cache bug would not route
   through the game's own error text — but not excluded: the game's error
   handler could just as easily be reacting correctly to a texture request
   the emulator answered wrong. A cart-read CRC diagnostic (hash the bytes
   the shim's ATA driver actually returns for the streams active in this
   window, compare against the source GDI) would separate "the shim handed
   the game bad bytes" from "the game got the right bytes and Flycast's
   GPU-side cache mishandled them."

**One repro only — do not overclaim.** This is a single intermittent
occurrence (operator: "once in ~6 sessions"); nothing here establishes a
trigger condition, only what the one captured occurrence looked like at
the log level. Phase 5 item — no fix attempted (out of this task's scope
by the brief).

### play1-revert — relaunch check (criterion 5 support)

`captures/phase4/play1-revert.log`, 434,467 lines / 15 MB — a **separate
Flycast process** (PID 37313 vs. `play1`'s 36774; launched 00:34:17, killed
00:39:43, its own fresh "Existing state will not be touched" stdout line),
i.e. a genuine relaunch, not a continuation of `play1`'s session.

```
MMUCRWR: 4, boot ladder at the same line numbers as play1 (1/14,032/14,136/14,141), final pc=8c02d630 — MAIN image
MDODMA enter: continuous from boot to line 434,455 of 434,467 (12 lines from EOF — no hang)
rawdma bus=0: 18,858 ≈ bus=1: 18,855; rawdma_ret outlen=10: 37,713
error/abort/mismatch/fail: 0
```

**Operator attestation:** free play confirmed — Start alone starts a
match, no coin; **FREE PLAY visible on attract after relaunch.**

**Criterion 5 — MET.** The coin-free start itself is attested inside the
`play1` session (brief item 3: "at the title screen press Start only, no
coin — a game must start"); `play1-revert` is the accompanying persistence
check — a fresh process, same baked GDI, reaches a healthy steady state
again with no hang and (per the operator) `FREE PLAY` still showing on
screen. This is exactly the expected shape for a **session-only EEPROM by
design**: free play is baked into the shipped image at build time (§FREE
PLAY, Task 12), not written back by any run, so a relaunch reading the same
GDI trivially reproduces it — the log confirms the relaunch is real and
healthy, the operator confirms what appeared on screen.

### play2p — criterion 3 (2P, port B)

`captures/phase4/play2p.log`, 592,106 lines / 20 MB.

```
MMUCRWR: 4, same boot-ladder line numbers again, final pc=8c02d630 — MAIN image
MDODMA enter: continuous from boot to line 592,089 of 592,106 (17 lines from EOF — no hang)
rawdma bus=0: 25,756 ≈ bus=1: 25,753 (port B traffic at parity with port A throughout)
rawdma_ret outlen=10: 51,509
error/abort/mismatch/fail: 0
```

Port-B `GetCondition` traffic runs at the same rate as port A for the whole
session — structurally consistent with 2P being live, though (per the
deviation note above) a release-mode cartlog cannot distinguish an *idle*
port-B pad from a *pressed* one; both ports answer every poll whether or
not a human is on the pad (Task 12's own finding — an idle port reads as
`p2=0`, indistinguishable from "no pad" at the transaction-count level).

**Operator attestation:** entry, play, and **mid-game join** (Start on
controller 2 during a CPU battle) all work; both players' controls fine;
the `play1` dead-zone note is explicitly re-confirmed fixed here ("verified
fine in play2p").

**Criterion 3 — MET.** Healthy single boot, no hang, no resets, port-B
maple traffic present throughout, operator confirms 2P entry + mid-game
join + both players' controls. Same residual proof-method gap as criterion
2 (no per-press bit decode available in a release-mode capture).

### testmenu-rt — criterion 4 (round trip)

`captures/phase4/testmenu-rt.log`, 703,202 lines / 23 MB. **Release
build** — per §Test menu's own Pending operator round trip note ("release
is fine — this leg needs no serial output, the screen tells the whole
story"), so this is not a deviation for this leg, it is what was specified.

**Two full boot ladders, cross-validated by the same PC signature used
above, with a reset in between:**

```
Boot #1  lines 1-8,137       final MMUCRWR pc=8c02d518  -> TEST image (matches testboot-diag1's confirmed-TEST signature)
Reset    lines 258,672-673   MMUCRWR val=00000000 pc=8c02d5fa, then pc=a0000018 (the literal SH-4 reset vector -- byte-identical marker to line 1 of every boot ladder in this project)
Boot #2  lines 271,243-351   final MMUCRWR pc=8c02d630  -> MAIN image (matches teststatic1's confirmed-MAIN signature)
```

The reset context (lines 258,660-673) is a clean video-mode teardown
(`IMLWR`/`PVRW` shutdown sequence) immediately followed by `MMUCRWR
val=00000000 pc=8c02d5fa` then `pc=a0000018` — then the **exact same**
`LOWRAMWR`/`PVRW SOFTRESET` sequence that opens line 1 of the file repeats
verbatim. This is `shim_reboot()`'s documented mechanism firing exactly as
predicted (§Exit-path readiness: "a jump to `0xa0000000` — the DC BIOS ROM
entry, exactly where the CPU lands out of a real hardware reset") — read
directly off the two adjacent `MMUCRWR` lines, not inferred.

```
MMUCRWR: 9 total (4 + 4 for the two boot ladders, +1 for the reset's own MMU-off write)
TAEND during the test-menu-visit span (lines 8,137-258,672): 21,630 frames -- the menu was rendering continuously, not stalled
TAEND after boot #2 (lines 271,351-EOF): 37,510 frames -- attract resumed and kept rendering to the kill point
MDODMA/rawdma traffic: healthy and continuous in both spans; the file's last lines are a well-formed MDODMA block (GetCondition, both buses) -- no hang this leg
error/abort/mismatch/fail (case-insensitive), whole 703,202-line file: 0 matches
```

**Operator attestation:** A+Start from boot → cyan-tinted Naomi splash ~1s
→ GAME TEST MENU; navigation per the on-screen footer (Service moves
cursor, Test confirms) works; controls test screen shows inputs correctly;
difficulty changed; EXIT → full console reboot (swirl seen) → attract.

**Criterion 4 — MET, the cleanest evidence chain of the six legs.** The
combo was read and honored (TEST image selected — provable independently
of the operator report, from the boot-ladder PC signature alone), the
operator navigated and exited, the reset fired through the documented
mechanism, the loader re-selected MAIN (no combo held on the second boot,
as expected once the operator has released the buttons to navigate the
menu), and attract resumed and stayed healthy through the kill point.
Matches §Exit-path readiness's **"most likely"** predicted outcome exactly
(full DC BIOS reboot → loader → main image → attract), not the named
fallback.

### pc2-testmenu — eeprom_write_seen closure (criterion 2's Phase-3 carry)

`captures/phase4/pc2-testmenu.log`, Naomi profile, instrumented Flycast,
**interpreter** (dynarec off for this leg, restored after — operator
attestation on the build config; not independently loggable). 139,759
lines / 7 MB. Single boot (`MAINHANDOFF` once, line 11,154). Operator
procedure: enter test menu, wait ~60 s, change nothing, exit.

```
$ python3 scripts/parse_cartlog.py captures/phase4/pc2-testmenu.log \
    --cart-fn 8c027f54-8c027f99 --input-fn 8c02532a-8c025505 \
    --eeprom-fn 8c02532a-8c025505 --stack 8c000000-8c00f000 --pc-report
...
CHECK eeprom_read_seen: FAIL — 8 sub=01/03 trig=reg PCs vs eeprom fn
CHECK eeprom_write_seen: FAIL — 0 sub=0b trig=reg PCs vs eeprom fn
```

**Zero `sub=0b` (EEPROM write) events, anywhere in the file, BIOS era
included** (`grep -c 'MIERESP sub=0b'` and a raw `grep -ci 'sub=0b'` both
return 0, with or without `--since-handoff`). This needs to be read
against Phase 2's own prior finding, not in isolation:
`docs/kb/phase2-measurements.md:126` records that of Phase 2's two
test-menu legs, only `testmenu2` (where the operator **flipped a
setting** — Advertise Sound OFF, then exited) produced `sub=0b` traffic (32
events); the sibling leg `testmenu` (visited, nothing changed) produced
**zero**, same as every non-test-menu leg. **`pc2-testmenu`'s zero count is
therefore the expected, consistent result for its exact procedure ("changes
nothing"), not a contradiction or a coverage gap** — it reproduces
`testmenu`'s zero-write shape under the current instrumented-fork commit,
and additionally confirms (a fact not separately nailed down before) that
merely *entering* the test menu triggers no EEPROM write on its own; a
write requires an actual setting change.

**A more precise read of `eeprom_read_seen`'s FAIL is worth recording,
because it refines the BIOS-attribution story rather than just repeating
it.** Listing the individual sub-`0x01`/`0x03` `trig=reg` PCs (not just the
`CHECK` count) — 8 total with no filter, 6 with `--since-handoff`:
```
no filter:        0xc03161e ×4, 0x8c025448 ×2, 0xc03161e ×2   (8 total)
--since-handoff:   0x8c025448 ×2, 0xc03161e ×4                (6 total)
```
Even **after** excluding the pre-`MAINHANDOFF` BIOS era, **4 of the 6
remaining PCs are still `0xc03161e`** — the same Naomi-BIOS PC Task 4
identified — because they fire *after* the handoff too. This is new: Run
D's model (`docs/kb/boot-binary.md` §Addendum 2026-08-22 — Phase 4 Task 4)
established `0xc03161e` as pre-handoff BIOS traffic; this leg shows the
same PC executing again, post-handoff, once the operator enters the test
menu — because the test menu itself is largely **BIOS-hosted UI**, invoked
by the game but not part of it, so `MAINHANDOFF`'s one-shot "game's first
instruction" marker does not mean "BIOS code never runs again." Only 2 of
the 6 game-era events are the confirmed game PC (`0x8c025448` =
`FUN_8c02532a`), which is why `eeprom_read_seen` still FAILs even
since-handoff — not a range error, the same BIOS-vs-game split Run D
already found, just now shown to persist past the handoff in the specific
test-menu regime.

**What this means for criterion 2's `eeprom_write_seen` sub-check.** No new
*write* PC evidence was produced by this leg — there is nothing to
attribute, because nothing was written. But the refined read above
strengthens, not weakens, the standing BIOS-attribution: the same PC
family (`0xc03161e`) this leg would expect to perform a write, had a write
occurred, is confirmed **live and executing in this exact test-menu
session** (via its read traffic). The standing evidence for **who** writes
the EEPROM when a write does happen is unchanged and remains Phase 2/3/4's
own: all 32 (Phase 2's `testmenu2`) / 16 (the Phase 3 recount) `sub=0b`
events ever observed in this project carry PC `0c03161e`, `trig=reg`, and
land in the BIOS's own pre-handoff era on those legs (Task 4's finding;
Ruling R6, `progress.md:74`). Since the only EEPROM writer ever observed in
this title is the BIOS, and BIOS code is by definition excluded from a
game-PC range check, `eeprom_write_seen` **cannot pass as a game-PC check
in this title regardless of leg** — that is a closed **decision** (R6), not
an open question this leg was trying to resolve. `pc2-testmenu`'s role was
confirmatory: a clean **negative control** showing the write path stays
silent under the one condition (test-menu visit, no change) most likely to
produce an unexpected game-PC write if one existed, and it didn't.
**Closed** — on the standing BIOS attribution plus this leg's
negative-control confirmation and the refined post-handoff-BIOS-traffic
read above. No game-PC write exists to find, and the DC build's own EEPROM
path (session-only RAM copy accepting the game's `sub=0b` writes
unconditionally, §EEPROM — a RAM copy, session-only, Task 12) does not
depend on this sub-check either way: it services whatever `sub=0b` traffic
arrives, from either image, without needing to know who would have sent it
on Naomi.

### Findings for Phase 5

1. **The texture-error hang** (play1, intermittent, once in ~6 sessions):
   see §Texture-error hang (play1) above for the full characterization,
   screenshot, and ranked candidate causes. Not fixed this task (explicitly
   out of scope per the brief).
2. **The cyan-tinted Naomi splash** (cosmetic, every boot, ~1 s, operator
   attestation) is recorded as **unexplained**. It occurs somewhere in the
   boot-to-handoff window (the same general timeframe as the loader's
   copy-record handoff and the video-mode transitions visible in every
   `.stdout.log`, e.g. `play1.stdout.log` lines 35-53), but nothing in this
   task's evidence ties it to a specific write, register, or KERNEL-SLICE
   placement — that would need a frame-by-frame framebuffer capture across
   the boot window, which this task did not do. Recorded as observation
   only, not diagnosed; not to be confused with the *fine* boot splash at
   the very start of boot, which matches Cleopatra (§Attract, finding 4).
3. **Feature request (Phase 5+, not a defect):** persist test-menu settings
   (difficulty, round length, etc.) to VMU via the shim's maple driver,
   instead of the current session-only RAM copy; a custom settings screen
   would be a later step on top of that. No code exists for this yet — the
   EEPROM write path Task 12 built (`mie_86` case `0x0b`) is already the
   single choke point a VMU/flash writer would plug into (§Steady input,
   Findings worth carrying forward, item 2).

### Contradictions

None found. Every operator attestation is consistent with, and in most
cases directly corroborated by, the log evidence above (image-selection PC
signatures, reset-vector re-entry, continuous vs. stopped `MDODMA`, zero
error strings). The one place log and attestation could in principle have
conflicted — whether `testmenu-rt`'s reboot actually lands back at a
healthy attract, per §Exit-path readiness's two-outcome honesty note —
resolved to the **better** of the two named-acceptable outcomes (a full
reboot to MAIN + attract, not Flycast's own BIOS-menu fallback).

### Reproduction

```sh
# DC-profile legs (play1, play1-revert, play2p, testmenu-rt) -- structural read, no per-leg parser
for f in play1 play1-revert play2p testmenu-rt; do
  F=captures/phase4/$f.log
  grep -c '^MMUCRWR' "$F"; grep -n '^MMUCRWR' "$F"        # boot-ladder line#s + final pc (8c02d630=MAIN, 8c02d518=TEST)
  grep -n 'MDODMA enter' "$F" | tail -1                    # last JVS activity vs. file length -- hang check
  grep -c 'rawdma_call cmd=09 reci=20 bus=0' "$F"           # port A
  grep -c 'rawdma_call cmd=09 reci=60 bus=1' "$F"           # port B
  grep -ci 'error\|abort\|mismatch\|fail' "$F"              # 0 expected
done

# Naomi-profile legs
python3 scripts/parse_cartlog.py captures/phase4/shimwatch-play.log            # -> shim_home_clean: PASS
python3 scripts/parse_cartlog.py captures/phase4/shimwatch*.log                # merged, both regimes
python3 scripts/parse_cartlog.py captures/phase4/pc2-testmenu.log \
    --cart-fn 8c027f54-8c027f99 --input-fn 8c02532a-8c025505 \
    --eeprom-fn 8c02532a-8c025505 --stack 8c000000-8c00f000 --pc-report      # eeprom_write_seen: 0, always
```

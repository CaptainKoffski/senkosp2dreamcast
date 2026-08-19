# Phase 3 — Reverse Engineering: design spec

**Date:** 2026-08-19
**Status:** approved (design), pending implementation plan
**Predecessor:** Phase 2 instrumented analysis
(`docs/superpowers/specs/2026-08-19-phase2-instrumented-analysis-design.md`;
gate green 2026-08-19, `docs/kb/00-status.md`)
**Precedent:** the Cleopatra Phase 3 spec
(`../cleopatra/docs/superpowers/specs/2026-07-18-phase3-reverse-engineering-design.md`)
— method reused; senkosp-specific targets added.
**Project:** static binary conversion of *Senko no Ronde Special*
(Naomi GD-ROM → Dreamcast). See `CLAUDE.md`, `docs/kb/00-status.md`.

## Purpose

Phase 2 recorded *what* the game does at runtime: the cart-streaming map
with its 5 above-16m main-RAM corridors, the region write-truth verdicts,
the 13/13 input map, and the device verdicts (serial/RTC/watchdog silent;
EEPROM BIOS-path). Phase 3 finds *which code and data* produce that
behavior — the addresses Phase 4 patches — and settles the port's central
strategic question: **can the above-cap content be relocated below the
Dreamcast's caps by patching its placement provenance?** The phase ends
with that strategy *proven in the emulator* (relocation dry run on the
Naomi profile), not just argued on paper.

Feasibility numbers from Phase 2 (`docs/kb/phase2-measurements.md`
§Region verdicts, `docs/kb/cart-streaming-map.md`):

- **Main RAM:** content below 16 MB is only ~1.59 MB (13,014,015 total nz
  − 11,428,714 above-16m — essentially the 1.5 MB boot load plus scraps).
  Relocating the 11.64 MB corridor footprint below the line totals
  ~13.2 MB, leaving ~3.5 MB slack. Fits as volume; the open question is
  purely pointer provenance.
- **VRAM:** content + 2×FB is 7.24 MB vs the 8 MB cap, but ~4.96 MB of
  FB-masked content sits at addresses above 8 MB (raw watermark
  14,571,136 B), and ~535 KB of framebuffer scan-out traffic above the
  line shows the FB registers themselves sometimes point above 8 MB.
  Free space below the line ≈ 6.1 MB vs ~4.96 MB to move — fits with
  ~1.1 MB slack. Tight, as Phase 2 warned.
- **ARAM:** fits, confirmed (u 0.643). Not a Phase 3 concern.

Every address claim is proven two ways — statically (Ghidra
cross-reference) and, where the code path runs during capture, dynamically
(guest PC logged at the moment the hardware access happens).

## Approach

**Static Ghidra analysis as the spine, dynamic PC logging as the proof
(chosen)** — the method Cleopatra's Phase 3 designed and validated, now
with precedent. SH-4 code materializes MMIO addresses and data pointers
through PC-relative literal pools, so distinctive constants (register
blocks, corridor base addresses) are findable statically; the instrumented
Flycast fork logs the guest PC at each cart-DMA kick and Maple
transaction as ground truth that the statically identified code is what
actually runs. Each side covers the other's blind spot: static-only
leaves patch addresses unproven until Phase 4 (expensive); dynamic-only
cannot prove the negatives this phase owes — the BIOS-call verdict and
the RTC/SCIF dead-code verdicts concern code that *never executes*, which
only disassembly can rule dead.

Alternatives considered and rejected:

- **Dynamic-first** (Ghidra only around logged PCs): cheaper start,
  attractive for corridor provenance — but cannot resolve the BIOS/RTC/
  SCIF negatives; the static pass gets added anyway. Rejected.
- **Pure static**: no rebuild, but addresses stay unproven and the dry
  run needs the dynamic anchor to trust its patch sites. Rejected — same
  verdict as Cleopatra.

## The nine targets

### 1. BIOS-call verdict

Does the binary call into Naomi BIOS ROM after entry (`0x8c021000`,
`docs/kb/game.md`)? Static: enumerate every branch whose resolved target
lies in BIOS ROM under any SH-4 mirror (compare on the 29-bit physical
address). `bsr`/`bra` are PC-relative ±4 KB and cannot reach BIOS from
game addresses, so only register-indirect `jsr @rN`/`jmp @rN` matter,
and their targets come from literal pools — scan pool constants
resolving into BIOS range and check whether any flows into a branch
register. Dynamic backstop: `BIOSEXEC` logs any guest execution inside
BIOS range after the first hit of the entrypoint. Expected: zero, both
ways. Caveat recorded honestly: a computed (non-pool) branch target
could evade the static scan; the dynamic backstop covers executed paths
only. Both clean ⇒ "no BIOS dependency observed statically or
dynamically" — sufficient to proceed, revisited only if Phase 4 hits an
unexplained crash.

### 2. Cart-read function

The code that fills the cart DMA registers and kicks transfers, plus the
thin PIO path (2 PIO seeks observed in Phase 2). Static: literal-pool
references to the cart register block (`0x5f7000`+) and G1 DMA channel
registers (`0x5f7400`+; exact offsets from primary sources during
implementation, not guessed). Expect one low-level "issue cart DMA
(offset, count, dest)" routine plus the PIO path; identify callers far
enough to name a clean Phase 4 patch boundary. Dynamic: `CARTDMAPC`
pc/sp at every kick — every logged PC must fall inside the identified
function.

### 3. Placement provenance (main corridors + VRAM) — the phase's center

**(a) Main-RAM corridors.** For each of the 5 above-16m spans
(`docs/kb/cart-streaming-map.md` §above-16m map): where does the DMA
`dest` value come from? Backward-slice from the logged kick PCs to the
dest source; classify as literal-pool base pointers, a descriptor/asset
table in the `.dat`, or computed addresses. Output: the exact patch set
that moves all 5 corridors below 16 MB into the ~14.4 MB of free space
below the line. Along the way, name span 4's hot ring (1,263 requests
into 252 KB — likely a per-round buffer) by owner.

**(b) VRAM placement.** Cart DMA never writes VRAM (Phase 2: all 1,590
DMA dests are main RAM; VRAM fills by CPU copy/TA from there), so VRAM
addresses come from the game's texture-allocation path — senkosp is
built on Ninja2 (`docs/kb/game.md`, SDK stack), whose texture manager
typically hands out addresses from a configurable base. Hypothesis to
verify: the display-list texture-control words referencing those
textures are computed from the same allocation source, so a coherent
base/table patch moves uploads *and* references together. Plus the
FB-register placement (`FB_W_SOF1/2`, `FB_R_SOF`) as its own small item
— Phase 2's bucket data shows scan-out traffic above 8 MB.

### 4. Relocation dry run — the capstone

Apply the target-3 patch set to a copy of `senkosp.dat` (via a committed,
deterministic script; the patched artifact stays gitignored). Run the
*Naomi* profile in the instrumented fork (16 MB VRAM there, so both
relocations can be proven safely): boot → attract → one played match.
Dynarec is fine here — the dry run needs watermarks and stream shape,
not instruction-exact PCs. Gate checks (see Cross-checks):
main high-water < 16 MB, FB-masked VRAM content watermark and FB
registers < 8 MB, and the attract leg's `(cart_offset, len)` stream
shape identical to Phase 2's anchor. Result: the relocation strategy
**proven or falsified before Phase 4 spends anything on it**. If
falsified, the fallback — shim-side streaming retarget plus
consumer-read patching — is decided and documented instead; either way
the phase exits with a proven or consciously chosen strategy.

Honest limit, stated here as it will be in the KB: the dry run proves
the *game tolerates relocation* on Naomi emulation. It proves nothing
about DC behavior — that is Phases 4–5.

### 5. Input-decode function

The Maple `0x86`/sub=`0x15` request builder and the JVS-word decoder.
Static: references to the Maple block (`0x5f6c00`+) and code testing the
11 measured bit masks (`docs/kb/input-map.md`: Start `0x8000`, Service
`0x4000`, stick `0x2000/0x1000/0x0800/0x0400`, M `0x0200`, S `0x0100`,
Barrage `0x0080`, A `0x0040`, OverDrive `0x0020`) near the Maple
response buffer. Dynamic: `MAPLEPC` lines tagged cmd/sub — every
sub=`0x15` PC must lie in the identified path.

### 6. EEPROM path

The sub=`0x0b` write handler (Phase 2: 32 ops, all in the test-menu leg,
0 elsewhere — BIOS-path confirmed) and the boot-time `0x01`/`0x03` read
plus the settings parser. Locate the function boundary Phase 4 patches
to force free-play defaults. Dynamic: tagged `MAPLEPC` lines — the boot
read appears in every leg; the write PC comes from the PC-capture
pass's test-menu entry.

### 7. Stack-pointer verdict

Walk the entry chain from `0x8c021000` to the `r15` setup and read the
value. SP below 16 MB above RAM base ⇒ main RAM safe as-is; SP near
32 MB ⇒ a one-constant Phase 4 patch, noted for the Phase 4 plan.
Dynamic: SP rides along in every `CARTDMAPC` line.

### 8. RTC / SCIF / watchdog static verdicts

Phase 2 measured 0 runtime pokes for all three across all 14 legs; the
static guts scan flagged 3 RTC MMIO refs and SCIF refs. Trace each ref
to a verdict: dead code, compile-time gated, or reachable — deciding
shim vs ignore for Phase 4. Watchdog: confirm zero refs (expected).
These two targets are static-only by nature: the code never fires, so
only disassembly can rule it dead.

### 9. Control layout (decided in this design)

User-approved 2026-08-19, recorded here and to be added to
`docs/kb/input-map.md`:

| DC pad | Game control |
|---|---|
| D-pad + analog (both) | Stick (8-way) |
| A | M — Main |
| X | S — Sub |
| B | A — Action |
| Y | Barrage |
| R trigger | OverDrive |
| L trigger | unbound (Phase 4 may duplicate Barrage if playtest wants it) |
| Start | Start |

Coin needs no binding — free-play is baked in per the charter; Start
alone starts a credit. Test/Service: wire bits known
(`docs/kb/input-map.md`), but the access mechanism (e.g. boot-time
combo) is a Phase 4 loader decision, not a pad binding.

## Instrumentation (dynamic side)

**Verify-then-extend, not rebuild.** The fork at `f014a410c`
(`../flycast4naomi2dreamcast`, source of truth) already emits more than
Cleopatra's Phase 3 had to plan for: `MAPLEPC cmd/sub` exists (Phase 2's
input-map.md counts its lines one-for-one against `MIERESP`), and
`VRAMPROFILE`/`VRAMREGS` (with FB-register values) are logged. First
step: audit what `f014a410c` emits. Expected gaps to add:

```
CARTDMAPC pc=%08x sp=%08x   # at cart-DMA kick, paired with the CARTDMA tuple line — if absent
BIOSEXEC  pc=%08x           # guest PC entered BIOS range post-entry, gate = senkosp entry 0x8c021000
```

The `BIOSEXEC` gate address must be parameterized, not hardcoded to
Cleopatra's entry. Fork changes are committed in
`../flycast4naomi2dreamcast`; the rebuild is recorded in
`docs/kb/tooling.md` per the tooling rule.

**Interpreter mode for the PC-logging pass** — dynarec PCs are
block-granular, not instruction-exact. The pass is short: boot → attract
→ one played match, plus a brief test-menu entry (for the EEPROM write
PC). If interpreter-mode capture proves unworkable, fallback is dynarec
block-start PC + static confirmation the block belongs to the candidate
function — recorded as such, not silently substituted.

## Static-analysis harness

- Working image: the 1,515,512-byte main load (`.dat` offset 0 →
  `0x8c020000`, entry `0x8c021000` — matches the assessment's code size
  exactly), extracted to a gitignored file. ROM content: **never
  committed, never uploaded**, same rule as the `.dat`.
- Import: Ghidra 12 headless, `SuperH4:LE:32:default`, BinaryLoader,
  base `0x8c020000` — the Phase 1-proven invocation
  (`docs/kb/tooling.md` §Ghidra), now with full auto-analysis.
- Committed, headlessly re-runnable Java scripts under `scripts/ghidra/`
  (Ghidra 12 dropped Jython):
  1. **MMIO xref reporter** — literal pools resolving into: cart
     `0x5f7000`+, G1 DMA `0x5f7400`+, Maple `0x5f6c00`+, PVR regs
     `0x5f8000`+ (incl. FB_W_SOF/FB_R_SOF), RTC `0x710000`+, SCIF —
     each hit with its referencing function.
  2. **BIOS-range branch-target scan** (target 1).
  3. **Entry-chain / SP-setup walk** from `0x8c021000` (target 7).
  4. **Placement-constant scan** — literal-pool *and* data-section
     values decoding to the 5 corridor ranges (under any SH-4 mirror) or
     to above-8m VRAM texture addresses. A plain Python scan over the
     full `.dat` backs it up for tables outside the boot slice.
- **Contingency, stated upfront:** if logged kick PCs or provenance
  chains land outside the boot image (code streamed in later — Cleopatra
  never needed this), the static image is extended from an emulator RAM
  snapshot at a known moment. Evidence-driven; recorded in `tooling.md`
  if triggered.
- The Ghidra project itself stays gitignored (it embeds ROM bytes);
  script output is text that feeds the KB writeup.

## Cross-checks (the self-check layer)

Encoded as asserts in `scripts/parse_cartlog.py`, extending the Phase 2
pattern. A static/dynamic disagreement is a stop-and-debug event
(systematic-debugging skill), never papered over — one side is wrong and
Phase 4 depends on knowing which.

- `dma_pc_in_cart_fn` — every `CARTDMAPC` PC inside the identified
  cart-read function's range.
- `input_pc_in_input_fn` — every `MAPLEPC` sub=`0x15` PC inside the
  identified input path.
- `eeprom_read_seen` / `eeprom_write_seen` — boot-time `0x01`/`0x03`
  and test-menu `0x0b` PCs captured, inside the identified EEPROM path.
- `no_bios_exec` — zero `BIOSEXEC` lines.
- `sp_consistent` — every logged SP inside the statically read stack
  region.
- Dry-run gate checks:
  - `dryrun_main_below_16m` — merged main high-water < `0x1000000`.
  - `dryrun_vram_below_8m` — FB-masked VRAM content watermark *and* FB
    registers < `0x800000`.
  - `dryrun_stream_shape` — the dry run's attract-leg
    `(cart_offset, len)` multiset matches Phase 2's attract anchor
    exactly; dest excluded (dests are deliberately moved). Offsets and
    lengths identical ⇒ game logic undisturbed.
  - Playability itself is operator-observed (boot → attract → one played
    match), like Phase 2's legs.

## Deliverables

- **`docs/kb/boot-binary.md`** — the annotated map: entry chain, SP
  verdict, every target's answer with address range, static + dynamic
  evidence, Phase 4 patch implication. Every claim cited by address, per
  the project's citation rule.
- **`docs/kb/relocation-map.md`** — Phase 4's direct input: placement
  provenance (5 corridors + VRAM/FB), the full patch set (address, old
  value, new value, provenance per entry), the below-cap free-space
  layout it relocates into, dry-run evidence.
- `scripts/ghidra/*.java` — committed, headlessly re-runnable.
- The patch-set applier script producing the dry-run `.dat`
  (deterministic; artifact gitignored, regenerable).
- `scripts/parse_cartlog.py` — extended with new line types + checks.
- Fork changes committed in `../flycast4naomi2dreamcast`; rebuild
  recorded in `docs/kb/tooling.md`.
- `docs/kb/input-map.md` — approved control layout added.
- `docs/kb/00-status.md` — Phase 3 done, Phase 4 next; key facts updated.

## Scope boundaries

- **In:** the nine targets, instrumentation audit/extension, static
  harness, the relocation dry run, the KB writeup.
- **Out — Phase 4:** loader, shim, patch table, GDI mastering,
  DC-profile boot. The dry run proves relocation tolerance on Naomi
  emulation only.
- **Out — Phase 5:** real hardware.
- **Out entirely:** ARAM (fits, confirmed), asset cutting (not
  triggered — all content fits as volume), the RAM TEST fork hang
  (emulator artifact — recorded in Phase 2, not chased), full-binary
  comprehension beyond the targets and their immediate callers.

## Exit criteria

Phase 3 is done when:

1. All nine targets are answered in `boot-binary.md` /
   `relocation-map.md` with static + dynamic evidence where
   runtime-reachable (RTC/SCIF static-only by nature).
2. All parser cross-checks PASS on the PC-capture run.
3. The dry run passes (patched `.dat` plays boot → attract → one match
   on the Naomi profile; `dryrun_main_below_16m`, `dryrun_vram_below_8m`,
   `dryrun_stream_shape` all green) — **or** falsification is recorded
   and the fallback strategy (shim-side streaming retarget +
   consumer-read patching) is decided and documented instead.
4. The Ghidra scripts re-run headlessly from a fresh checkout (given the
   gitignored ROM) and reproduce the reported addresses.
5. The control layout is recorded in `input-map.md`.
6. `00-status.md` is advanced to Phase 4.

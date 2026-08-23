# Phase 5 — hardware bring-up results

Analysis and bring-up results for Phase 5 (spec
`docs/superpowers/specs/2026-08-23-phase5-hardware-design.md`, plan
`docs/superpowers/plans/2026-08-23-phase5-hardware.md`). Phase 4 is closed
(`docs/kb/00-status.md`, `docs/kb/phase4-conversion.md`); Phase 5's first
gate is the texture-load-error hang (spec §Work item 1).

Every claim below is cited to an instruction/pool-word address in the boot
binary, a Ghidra decompilation of a named function, or a byte offset in
`senkosp.dat`, per this project's citation rule (primary sources outrank
wikis — `CLAUDE.md`). Addresses are P1 (`0x8c…`); `.dat` file offset =
address − `0x8c020000` (the main load entry, `0x171ff8` bytes —
`docs/kb/boot-binary.md`). Re-runnable tooling:
`scripts/ghidra/FindTexErrXrefs.java`, `Decomp.java`, `DisasmRange.java`
via `scripts/ghidra/run.sh script <Name.java> [addr…]`.

---

## Texture-error handler — static characterization

**Question (spec §Work item 1; task brief
`.superpowers/sdd/2026-08-23-phase5-hardware/task-4-brief.md`):** Phase 4
observed the game's own `ERROR !! / TEXTURE LOAD ERROR !` handler fire once
in ~6 sessions (`docs/kb/phase4-conversion.md` §Texture-error hang (play1);
screenshot `docs/kb/img/phase4-dc-texerror.png`). Which conditions can
reach that message — bad loaded bytes, an allocation/arena failure, or a
lookup failure? The answer decides how Task 7 reads the CRC evidence.

### Anchors — the error-string block

The strings sit in one contiguous block at the tail of the main image,
verified by direct byte read of `senkosp.dat` (`dd`/`xxd`, file offset =
address − `0x8c020000`):

| Address | `.dat` offset | String |
|---|---|---|
| `0x8c1885f0` | `0x1685f0` | `MEMORY ALLOCATE ERROR !\nHEAP:%p\nSIZE:%d\n` |
| `0x8c188619` | `0x168619` | `I/O BD IS NOT CONNECTED TO NAOMI BD.\n` |
| `0x8c18863f` | `0x16863f` | `I/O BD CONNECTED TO NAOMI BD DOES NOT FULFILL…` |
| `0x8c18871b` | `0x16871b` | `ERROR !!` |
| `0x8c18890c` | `0x16890c` | `COMMON.PAK` — **the base of the PAK-name/message region** |
| `0x8c188b6a` | `0x168b6a` | `FILE LOAD ERROR !\nFILE NAME:%s\n` |
| **`0x8c188b8a`** | **`0x168b8a`** | **`TEXTURE LOAD ERROR !\n`** |
| `0x8c188ba0` | `0x168ba0` | `PACKTEX MALLOC FAILED %s\n` |
| `0x8c188bba` | `0x168bba` | `PACKTEX DECODE ERROR\n` |
| `0x8c188bd0` | `0x168bd0` | `PACKTEX LOAD ERROR\n` |
| `0x8c188be4` | `0x168be4` | `LOADPACKSTEX LIST MALLOC FAILED %s\n` |
| `0x8c188c08` | `0x168c08` | `LOADPACKSTEX WORK MALLOC FAILED %s\n` |
| `0x8c188c2c` | `0x168c2c` | `LOADPACKSTEX DECODE ERROR\n` |
| `0x8c188c47` | `0x168c47` | `LOADPACKSTEX LOAD ERROR\n` |

**Correction to the task brief's anchor list.** The brief recorded the
`TEXTURE LOAD ERROR !` string as "preceded by a `…!\nFILE NAME:%s\n` format
string" and guessed its start at `0x8c188b7a`. The byte read shows the
preceding item is **one** NUL-terminated string,
`FILE LOAD ERROR !\nFILE NAME:%s\n` starting at `0x8c188b6a` (`0x8c188b7b`
is its embedded `\n`, `0x8c188b89` its NUL) — it belongs to the **file**
loader, not the texture one. **`TEXTURE LOAD ERROR !\n` contains no `%s`
and prints no filename** — confirmed by the Phase 4 screenshot, which shows
exactly two lines and no filename (`docs/kb/img/phase4-dc-texerror.png`,
read directly).

**Test-image twin (recorded, not analysed, per the brief).** Second copies
of `TEXTURE LOAD ERROR !` at `.dat` `0x1bf8ae` and of `ERROR !!` at `.dat`
`0x1bd17f` — both outside the `0x171ff8`-byte main load entry, i.e. in the
separately-linked test image (`docs/kb/phase4-conversion.md` §Texture-error
hang establishes that the two images are separately linked). `play1` booted
**MAIN** (`pc=8c02d630`, same section), so the observed occurrence came
from the main-image copy characterized here.

### Why a raw pointer scan finds nothing — the addressing idiom

No 32-bit word anywhere in the 251 MB `senkosp.dat` equals `0x8c188b8a`
(exhaustive byte-stride scan). The address is **computed at runtime** as
region base + immediate. Disassembly of the call site
(`run.sh script DisasmRange.java 0x8c0b6340 0x8c0b6372`):

```
8c0b634c  mov.l 0x8c0b637c,r0     ; r0 = FUN_8c070ebc      (pool 0x8c0b637c = 0x8c070ebc)
8c0b634e  mov   r8,r4             ; r4 = the texture-list struct
8c0b6350  jsr   @r0
8c0b6352  _mov  #0x1,r5           ; r5 = 1
8c0b6354  mov   #-0x1,r1
8c0b6356  cmp/eq r1,r0            ; returned -1 ?
8c0b6358  bt    0x8c0b635e        ;   yes -> print
8c0b635a  bra   0x8c0b6788        ;   no  -> carry on
8c0b635e  mov   #0x2,r0
8c0b6360  shll8 r0                ; r0 = 0x200
8c0b6362  mov.l 0x8c0b6380,r1     ; r1 = 0x8c18890c  (region base "COMMON.PAK")
8c0b6364  or    #0x7e,r0          ; r0 = 0x27e
8c0b6366  add   r0,r1             ; r1 = 0x8c188b8a  "TEXTURE LOAD ERROR !\n"
8c0b6368  mov.l r1,@-r15          ; push as the printer's format argument
8c0b636a  mov.l 0x8c0b6384,r0     ; r0 = FUN_8c0ad720  (pool 0x8c0b6384 = 0x8c0ad720)
8c0b636c  jsr   @r0
```

Ghidra's SH-4 constant propagation resolves this to a DATA reference from
`0x8c0b6368`, which is how `FindTexErrXrefs.java` finds it.

### The xref chain — string → pool → function → callers

`scripts/ghidra/run.sh script FindTexErrXrefs.java` (no args = the whole
block above; every target resolves, no `NOREF` at hop 0):

```
TARGET 0x8c188b8a  "TEXTURE LOAD ERROR !\n"
  XREF hop=0 to=8c188b8a from=8c0b6368 fn=FUN_8c0b5fc8@8c0b5fc8
```

Exactly **one** site. Cross-check that this is complete rather than a
resolution artefact: a 4-byte-aligned scan of the whole main image finds
only four *code* pool words holding the region base `0x8c18890c`
(`0x8c0b5c78`, `0x8c0b6380`, `0x8c0b64a8`, `0x8c0b696c` — plus
`0x8c18880c`, which is the PAK-name table's own first entry, not code), and
the nine resolved `base + imm` sites they feed account for all nine
messages in the block, one site each — table below. There is no second
producer of this string.

| Print site (`jsr`) | Offset | Message | Enclosing function |
|---|---|---|---|
| `0x8c0b5c28` | `+0x25e` | `FILE LOAD ERROR !\nFILE NAME:%s\n` | `FUN_8c0b5be8` |
| **`0x8c0b636c`** | **`+0x27e`** | **`TEXTURE LOAD ERROR !\n`** | **`FUN_8c0b5fc8`** (`TXTR` chunk) |
| `0x8c0b642c` | `+0x294` | `PACKTEX MALLOC FAILED %s\n` | `FUN_8c0b5fc8` (`PKTX`) |
| `0x8c0b6454` | `+0x2ae` | `PACKTEX DECODE ERROR\n` | `FUN_8c0b5fc8` (`PKTX`) |
| `0x8c0b6496` | `+0x2c4` | `PACKTEX LOAD ERROR\n` | `FUN_8c0b5fc8` (`PKTX`) |
| `0x8c0b680a` | `+0x2d8` | `LOADPACKSTEX LIST MALLOC FAILED %s\n` | `FUN_8c0b67d4` |
| `0x8c0b68c4` | `+0x2fc` | `LOADPACKSTEX WORK MALLOC FAILED %s\n` | `FUN_8c0b67d4` |
| `0x8c0b68ec` | `+0x320` | `LOADPACKSTEX DECODE ERROR\n` | `FUN_8c0b67d4` |
| `0x8c0b691e` | `+0x33b` | `LOADPACKSTEX LOAD ERROR\n` | `FUN_8c0b67d4` |

Print-site addresses are the `jsr` to `FUN_8c0ad720`, taken from that
function's caller list (`Decomp.java 0x8c0ad720`); the string-materialising
`mov.l …,@-r15` sits exactly 4 bytes earlier at each site — that earlier
address is what `FindTexErrXrefs.java` reports (e.g. `0x8c0b6368` →
`jsr 0x8c0b636c`). A second, independently-linked file-loader module carries
its own `FILE LOAD ERROR !\nFILE NAME:%s\n` copy at `0x8c18700a`, printed
from `0x8c08736a` (push at `0x8c087366`); the main-RAM heap OOM message
`MEMORY ALLOCATE ERROR !\nHEAP:%p\nSIZE:%d\n` (`0x8c1885f0`) is printed from
`0x8c0ad68c` (push at `0x8c0ad688`), with a second site at `0x8c0ad69c`
using the same base. Neither is the texture message. Ghidra's auto-analysis
did not recover containing functions for those sites (`fn=?`); they are
recorded, not characterized, because neither can produce the observed text.

### The printer is a terminal loop — this is the hang

`FUN_8c0ad720` (`0x8c0ad720`–`0x8c0ad803`, decompiled via `Decomp.java`) is
the game's fatal-error display. It is variadic (`vsprintf`-style formatting
via `PTR_FUN_8c0ad810` = `0x8c0695e4` into a stack buffer) and **never
returns** — its body is a `do { … } while(true)` with no exit path and no
`rts` reachable from the loop. Each iteration:

- prints the header `ERROR !!` (`0x8c1885f0 + 299` = `0x8c18871b`, loaded at
  `0x8c0ad7e8`/`0x8c0ad7ec`) at text position `(4, 8)` — gated on
  `uVar7 & 0x10`, i.e. it blinks;
- prints the caller's formatted message at text position `(4, 10)`; the
  colour is set once per iteration before both lines, `0xffffff00` (yellow)
  or `0xffff0000` (red), alternating on `uVar7 & 0x20`;
- calls the frame/present pair `PTR_FUN_8c0ad834` (`0x8c03df34`) and
  `PTR_thunk_FUN_8c034ba0_8c0ad838` (`0x8c03dd22`) every iteration;
- polls input through `FUN_8c06fb78` (`jsr` at `0x8c0ad77a`), which derives
  its button mask from a **latched RAM byte** at `[0x8c1bf190 + 5]` (bits
  `0x10`→`0x10000`, `0x20`→`0x40`, active-low), not from an MMIO read; if
  bit `0x10000` stays set for more than 5 iterations (counter at
  `0x8c1d8d98`) it calls `FUN_8c085c68` (`jsr` at `0x8c0ad79c`), a
  three-call sequence (`0x8c06ed6c`, `0x8c085be8`, `0x8c071700`). The gating
  call inside `FUN_8c06fb78` (`0x8c067546`, in the Phase 3 input/EEPROM
  block) was not traced further, so whether any transport still runs beneath
  it is **not** established here — the capture evidence, not this read, is
  what shows maple stopped.

This matches the Phase 4 capture exactly: render loop alive and
re-presenting every vblank, `MDODMA` (maple) dead, no reset attempted
(`docs/kb/phase4-conversion.md` §Texture-error hang (play1)). The two
yellow lines in `docs/kb/img/phase4-dc-texerror.png` are this function's
`(4,8)` + `(4,10)` output. **The hang is not a crash — it is the game
deliberately parking in its own error display forever.**

### The failure chain behind the one call site

`FUN_8c0b5fc8` (`0x8c0b5fc8`–`0x8c0b67cd`) is the PAK chunk dispatcher: it
walks a loaded PAK's chunks and switches on the 4-byte chunk tag. The
`TXTR` branch (tag compare `uStack_38 == 0x54585452`) builds a texture list
of 12-byte entries and then calls the loader:

- entry allocation: `jsr` at `0x8c0b6326` → `FUN_8c06fe80`, size
  `count * 0xc`, arena handle `*0x8c1d9400` (pool `0x8c0b6374`);
  `0x8c06fe80` sits immediately after the heap-create pair
  `0x8c06fd60`/`0x8c06fda8` recorded in `scripts/ghidra/WhichFunc.java`, so
  it is a main-RAM heap allocator, not a VRAM one. The `TXTR` branch stores
  its result unchecked (`mov.l r0,@r8` at `0x8c0b632a`) — unlike the `PKTX`
  branch, which null-checks and prints `PACKTEX MALLOC FAILED %s`. A heap
  failure here would therefore fault or corrupt, **not** produce this
  message;
- per entry: `[0] = texture data pointer`, `[1] = 0x40000000` (store at
  `0x8c0b6344`; the constant is built `mov #0x40 / shll16 / shll8` at
  `0x8c0b6032`–`0x8c0b6038`), `[2] = 0`;
- `jsr` at `0x8c0b6350` → **`FUN_8c070ebc(list, 1)`**;
- `cmp/eq #-1` at `0x8c0b6356` → on `-1`, print (above).

`FUN_8c070ebc` (`0x8c070ebc`–`0x8c070ee9`):

```
if (list->count == 0) { *(0x8c1a20a0 + 8) = 1; return -1; }     // empty TXTR chunk
else                    return FUN_8c070da8(list);               // arg2 = 1 -> pool 0x8c070ef0
//                        ^ pool DAT_8c070eec = 0x8c1a20a0, so "+ 8" is 0x8c1a20a8 --
//                          the SAME cell the KAMUI2 leaves use for their error code.
```

`FUN_8c070da8` (`0x8c070da8`–`0x8c070ddb`) loops the list; the first entry
whose per-texture load returns false records its index at `*0x8c1a20a0` and
returns `-1`. The per-texture load is `FUN_8c070d4c` (`0x8c070d4c`), which
masks the entry's flags with `0x5c000000` and dispatches through the table
at `0x8c1813e4` — flags `0x40000000` selects **slot 1 = `0x8c070ae4`**
(slots: `0`→`0x8c0708cc`, `1`→`0x8c070ae4`, `2`→`0x8c070bec`,
`3`→`0x8c070c90`). Because the `TXTR` branch writes the flag word as a
constant `0x40000000`, slot 1 is the only reachable loader for this path.

Slot 1 (`0x8c070ae4`–`0x8c070bcc`, read as disassembly) returns **false**
— the value that becomes `TEXTURE LOAD ERROR !` — from exactly three
places:

| Return-false site | Callee (pool) | Callee |
|---|---|---|
| `0x8c070b0c`–`0x8c070b14` | `0x8c070bd4` | `FUN_8c03e8ec` — reuse/alias an existing surface |
| `0x8c070b7a`–`0x8c070b82` | `0x8c070bdc` | `FUN_8c0407ba` — find-or-create the texture surface |
| `0x8c070b8c`–`0x8c070bb0` | `0x8c070be0` | `FUN_8c04074a` — upload the texture data to the surface |

All three are KAMUI2 (NEC PVR library) entry points — the same library
block as `kmInitDevice` at `0x8c031fee` (`scripts/ghidra/WhichFunc.java`,
`docs/kb/relocation-map.md`). They share one error-code global,
**`0x8c1a20a8`**, and one surface-table set:
`*0x8c1a2088` = surface array base (stride `0x18`), `*0x8c1a208c` = its
capacity, `*0x8c1a2090` = VRAM-block descriptor array (stride `0x28`),
`*0x8c1a2094` = its capacity, `*0x8c1a2098` = live-surface counter.

Descending each branch:

- **`FUN_8c0407ba`** (`0x8c0407ba`) → `FUN_8c040648` (`0x8c040648`) →
  - `FUN_8c03fb58` (`0x8c03fb58`, call at `0x8c04065a`): linear scan for a
    free surface slot and a free VRAM-block descriptor; if either table is
    full → `*0x8c1a20a8 = 7; return -1` (`0x8c03fbae`).
  - `FUN_8c03ff38` (`0x8c03ff38`, call at `0x8c04066e`) → `FUN_8c03f38c`
    (`0x8c03f38c`); any nonzero → `*0x8c1a20a8 = 6; return -1`.
    - `FUN_8c03ea1c` (`0x8c03ea1c`, call at `0x8c03f39e`): validates the
      texture's declared width/height/format and computes the byte size into
      `param_1[5]`; returns **4** for a width or height outside
      `{8,16,32,64,128,256,512,1024}`, for an unknown format code, or for a
      non-square texture in a format that requires square
      (`0x8c03eba8`, `param_2 != param_3`).
    - `FUN_8c034e60` (`0x8c034e60`, call at `0x8c03f400`) → `FUN_8c03c46e`
      (`0x8c03c46e`): the VRAM texture-arena allocator. Rounds the request
      up to 32 bytes, best-fit-walks the free list rooted at
      `[PTR_DAT_8c03c4c0 + bank*0x10 + 0x2c]`, and returns **3** when no
      free block is large enough (`0x8c03c542`, reached from the
      `puVar2 == 0` test) or when the block-descriptor pool
      (`FUN_8c03c764`) is empty.
- **`FUN_8c03e8ec`** (`0x8c03e8ec`) returns `-1` only when its own
  `FUN_8c03fb58` call (`0x8c03e94e`) fails — the same table-exhaustion
  condition (`*0x8c1a20a8 = 7`).
- **`FUN_8c04074a`** (`0x8c04074a`) returns `-1` when the surface has no
  texture buffer (`*0x8c1a20a8 = 1`), or when the upload
  `FUN_8c03fdc6` (`0x8c03fdc6`) returns nonzero → `*0x8c1a20a8 = 8`.
  `FUN_8c03fdc6` returns `7` when the source offset reaches or exceeds the
  allocated surface size (`param_1[5] <= uVar4`) — i.e. the texture's
  declared data extent does not fit the surface its own header asked for.

### Trigger taxonomy

| # | Proximate cause | Category | Evidence (addresses) |
|---|---|---|---|
| T1 | VRAM texture-arena has no free block ≥ the requested size (or the block-descriptor pool is empty) | **(b) allocation / arena-space** | `FUN_8c03c46e` returns 3 at `0x8c03c542` → `FUN_8c03f38c` `0x8c03f400` → `FUN_8c03ff38` sets `*0x8c1a20a8 = 6`, returns −1 → `FUN_8c040648` → `FUN_8c0407ba` → false at `0x8c070b7a` → `FUN_8c070da8` −1 → print `0x8c0b636c` |
| T2 | KAMUI2 surface-slot table or VRAM-block-descriptor table full | **(b) allocation / arena-space** | `FUN_8c03fb58` sets `*0x8c1a20a8 = 7`, returns −1 at `0x8c03fbae`; reached from `0x8c04065a` (`FUN_8c040648`), `0x8c04057a` (`FUN_8c04052a`), `0x8c03e94e` (`FUN_8c03e8ec`) — all on the slot-1 path |
| T3 | Surface exists but carries no texture buffer | **(b) allocation / arena-space** | `FUN_8c04074a` `*0x8c1a20a8 = 1`, `return -1`; checked at `0x8c070b8c`. **Writes the same cell and the same value as T6** — see the classifier caveat |
| T4 | Texture header declares an illegal width, height, or format code | **(a) data integrity** | `FUN_8c03ea1c` returns 4 (`0x8c03eafe`, `0x8c03eba8`) → `FUN_8c03f38c` nonzero → `*0x8c1a20a8 = 6` → same chain as T1 |
| T5 | Texture's declared data extent does not fit the surface its header asked for | **(a) data integrity** | `FUN_8c03fdc6` returns 7 (`param_1[5] <= uVar4`) → `FUN_8c04074a` `*0x8c1a20a8 = 8`, −1; checked at `0x8c070b8c` |
| T6 | `TXTR` chunk declares zero entries | **(a) data integrity** (structural) | `FUN_8c070ebc` `*(DAT_8c070eec + 8) = 1; return -1`, and `DAT_8c070eec` = `0x8c1a20a0`, so this writes **`0x8c1a20a8` = 1 — the same cell and value as T3**. The `-1` is produced without ever calling the loader |
| — | lookup / filename failure | **(c) — NOT reachable** | see below |

**Category (c) is excluded, with evidence.** The texture path never sees a
filename: `FUN_8c0b5fc8`'s `TXTR` branch operates on an already-resident
buffer and passes no `%s` argument (`0x8c0b6368` pushes the format string
and nothing else; `TEXTURE LOAD ERROR !\n` has no conversion specifier).
Lookup and open failures print their own, different messages —
`FILE LOAD ERROR !\nFILE NAME:%s\n` from `FUN_8c0b5be8` at `0x8c0b5c28`
(when the open/lookup call `PTR_FUN_8c0b5c74` = `0x8c07136c` returns
nonzero), and the `*MALLOC FAILED %s` variants. A lookup that returns the
*wrong* data rather than failing outright would surface as T4/T5, i.e. as
category (a).

**Category (b) here means VRAM, not main RAM.** Main-RAM heap exhaustion
has its own message and its own printer — `MEMORY ALLOCATE ERROR !\nHEAP:%p\nSIZE:%d\n`
(`0x8c1885f0`, printed from `0x8c0ad688`) — and the PAK-level heap failures
print `PACKTEX MALLOC FAILED %s` / `LOADPACKSTEX … MALLOC FAILED %s`. So
`TEXTURE LOAD ERROR !` on its own indicts the **KAMUI2 VRAM texture arena**
(and its fixed-size surface/block tables), not the relocated main-RAM heap.
Both seeds are ours to get right — the 8 MB VRAM seed and the heap top are
the two patched constants (`docs/kb/relocation-map.md`) — but this message
points at the VRAM one.

### What this means for the Task 7 verdict

**The handler can fire on an allocation/arena failure that has nothing to do
with the bytes on the disc (T1/T2/T3). Therefore clean CRCs do NOT, on
their own, exonerate the port.** Stated as Task 7 must apply it:

> Clean CRCs exonerate the emulator **only if** the captured occurrence's
> path is (a) or (c)-with-good-bytes; **path (b) is our fit bug** — the VRAM
> texture arena derived from the patched 8 MB seed — and blocks hardware per
> the spec's hard gate.

Because six of the six reachable triggers split 3-(b) / 3-(a) and **both
groups produce byte-identical screen text**, the screenshot alone cannot
classify an occurrence. The classifier must read the KAMUI2 state:

| Read at the marked hang | Meaning | Category |
|---|---|---|
| `*0x8c1a20a8 == 6` and the VRAM free list has no block ≥ the request | out of VRAM arena | (b) — T1 |
| `*0x8c1a20a8 == 6` with free VRAM available | illegal header w/h/format | (a) — T4 |
| `*0x8c1a20a8 == 7` | surface/block table full | (b) — T2 |
| `*0x8c1a20a8 == 1` **and** `0x8c1a20a0` was written this occurrence | surface without buffer | (b) — T3 |
| `*0x8c1a20a8 == 1` **and** `0x8c1a20a0` was *not* written | empty `TXTR` chunk | (a) — T6 |
| `*0x8c1a20a8 == 8` | data extent overruns the surface | (a) — T5 |

**Two rows of this table are not separable by the error code alone**, and
both collisions cross the (a)/(b) line that decides the gate:

- **`6` is T1 or T4** — hence the free-list condition in the first two rows.
- **`1` is T3 or T6, at the same address with the same value.**
  `FUN_8c070ebc`'s empty-chunk write is `*(DAT_8c070eec + 8) = 1` with
  `DAT_8c070eec` = `0x8c1a20a0`, i.e. `0x8c1a20a8`; `FUN_8c04074a`'s
  no-buffer write is `*DAT_8c040844 = 1` with `DAT_8c040844` = `0x8c1a20a8`.
  One cell, one value, opposite verdicts.

**Auxiliary discriminator for the `1` collision — verified against the
decompilation.** `FUN_8c070da8` writes the failing list index to
`*DAT_8c070de0` = **`0x8c1a20a0`** (offset 0, a *different* cell from the
error code at +8), and it does so only on the loop-break path — i.e. only
when a per-texture load actually returned false. T6 short-circuits inside
`FUN_8c070ebc` at the `list->count == 0` test and returns `-1` **without
ever calling `FUN_8c070da8`** (the only call is at `0x8c070ed6`), so it
cannot reach that store. Therefore:

> a write to `0x8c1a20a0` between the texture-list submission and the
> marker ⇒ **not T6**; its absence ⇒ **T6**.

This must be instrumented as a **write-watch, not a value read**: the index
is legitimately `0` when the first entry fails, which is indistinguishable
by value from a stale or zeroed cell. Both cells are shared by every
texture-list load in the game (`FUN_8c070ebc` has 15 call sites, including
the `PKTX` and `LOADPACKSTEX` paths at `0x8c0b647e`, `0x8c0b64b4`,
`0x8c0b6908`), so the watch must be scoped to the marked occurrence.

`*0x8c1a20a0` additionally holds the **index within the texture list** of
the entry that failed, and `*0x8c1a2098` the live-surface count — both worth
sampling at the marker. Note `*0x8c1a20a8` is a shared KAMUI2 global with no
clear-on-read semantics observed here, so a value present at the hang may be
stale from an earlier benign call; treat it as corroborating evidence
alongside the CRC streams, not as a sole verdict.

### Hang marker — the PC to watch (spec §Instrumentation)

The spec's hang marker wants one address. Use the `jsr` at **`0x8c0b636c`**
— texture-path-specific, one site, no false positives from the sibling
messages. If the fork's marker uses the same `Sh4cntx.pc` convention as the
existing `CARTDMAPC`/`PCSAMPLE` taps, the logged value is the instruction
address **+ 2** (`scripts/ghidra/WhichFunc.java`, citing
`core/hw/sh4/interpr/sh4_interpreter.cpp` `ctx->pc = addr + 2`), i.e. watch
for **`0x8c0b636e`** and record `0x8c0b636c` as the true site. A broader
alternative is the printer entry `0x8c0ad720` plus `PR` (return address
`0x8c0b6370` for the texture site) — that catches all nine messages and
discriminates them by `PR` against the call-site table above, which is
strictly more informative if the fork can log `PR`.

### Operator note

**Photograph the full error text, every time.** Not because it names the
asset — it does not; `TEXTURE LOAD ERROR !\n` carries no `%s`, and the
Phase 4 screenshot correctly shows only two lines. Photograph it because
**the exact wording selects which failure fired**, and the nine sibling
messages are visually similar:

- `TEXTURE LOAD ERROR !` — the `TXTR` path characterized here (this gate).
- `PACKTEX LOAD ERROR` / `LOADPACKSTEX LOAD ERROR` — the same
  `FUN_8c070ebc` loader failing on a *packed*-texture chunk; same taxonomy,
  different chunk type.
- `PACKTEX DECODE ERROR` / `LOADPACKSTEX DECODE ERROR` — decompression
  failed: category (a), bad bytes, a much stronger indictment of the
  cart-stream path.
- `PACKTEX MALLOC FAILED %s` / `LOADPACKSTEX … MALLOC FAILED %s` /
  `MEMORY ALLOCATE ERROR ! HEAP:%p SIZE:%d` — **main-RAM heap** exhaustion,
  not VRAM. These *do* carry a filename or a size; capture it.
- `FILE LOAD ERROR !` + `FILE NAME:<name>` — file open/lookup failed;
  **this** is the message whose second line names the failing asset.

Also record whether the header line is blinking and note that the machine
will sit in this loop indefinitely (it never resets itself — consistent
with Phase 4's `MMUCRWR == 4` for the whole capture), so a kill/power-cycle
by the operator is expected, not a second symptom.

### Limits of this analysis

- Static only. Which of T1–T6 fired in the `play1` occurrence is **not**
  decidable from the image; it needs the runtime reads listed above plus
  the Task 5/6 CRC streams.
- **The error code alone does not separate T1 from T4, nor T3 from T6** —
  and each of those pairs straddles the (a)/(b) line. T1/T4 collide on the
  *value* `6`; T3/T6 collide on the same *address* `0x8c1a20a8` **and** the
  same value `1`. Neither pair can be classified by sampling
  `*0x8c1a20a8` on its own. Each needs its own auxiliary signal: the VRAM
  free-list state for T1/T4, and a write-watch on `0x8c1a20a0` for T3/T6
  (both specified above). If Tasks 5/6 ship neither, the honest Task 7
  finding is "the captured evidence cannot separate T1 from T4" and/or
  "…T3 from T6" — which, since each pair contains one (b), means the gate
  cannot be closed by exoneration on that evidence.
- `FUN_8c03c46e`'s free-list root (`PTR_DAT_8c03c4c0`) and the bank
  selection in `FUN_8c034e60` were read but not traced to the patched VRAM
  seed; that link (arena size ← 8 MB seed) is asserted in
  `docs/kb/relocation-map.md`, not re-derived here.
- Two print sites for non-texture messages (`0x8c087366`/`0x8c08736a` and
  `0x8c0ad686`/`0x8c0ad688`) sit in code Ghidra's auto-analysis left without
  a containing function; they are recorded, not characterized.

## Instrument control test (Task 5)

**Question:** does the Wave A instrument pipeline — shim `SHIMCRC` (Task 1),
fork `GDPIO`/`GDDMA` (Task 2), `scripts/check_stream_crc.py` (Task 3) —
verify clean on a real DC-profile leg before any operator time is spent on
the texture-error hang? Extension (controller ruling,
`.superpowers/sdd/2026-08-23-phase5-hardware/task-5-brief.md`): can a
periodic sampler of the three classifier cells named above
(`0x8c1a20a0`/`0x8c1a20a8`/`0x8c1a2098`) run continuously on the DC profile
without flooding the log?

### Step 1 — `capture_dc_leg.sh` pass-through

Exec line changed exactly per the brief, so later tasks can pass
`-config Debug:SerialConsoleEnabled=yes` and similar flags through to
Flycast:

```
FLYCAST_CARTLOG="$log" exec "$bin" -config config:rend.vsync=no "${@:3}" "$gdi" \
    > "${log%.log}.stdout.log" 2>&1
```

`bash -n scripts/capture_dc_leg.sh` → syntax OK. The refuse-to-overwrite
check and the pre-launch `pkill` are unchanged.

### Step 2 — diagnostic disc, and a `make`/`DEFS` hazard found along the way

First attempt: `make gdi DEFS='-DSHIM_SERIAL=1 -DSHIM_CRC=1'` from a
not-freshly-cleaned tree printed `make[1]: Nothing to be done for 'all'.`
for `shims/` and exited 0 — looked like success. `strings
shims/build/shim.bin | grep SHIMCRC` came back **empty**: the disc was
silently non-diagnostic. Root cause: `shims/Makefile`'s `CFLAGS +=
$(DEFS)` is not a tracked prerequisite of `$(B)/shim.bin` — `make`'s
mtime-based check only sees that the sources didn't change, not that the
*flags* did, so a `shim.bin` left over from an earlier, differently-flagged
build (12:12 that session) satisfied the rule and was reused unmodified.
Fix: `make clean && make gdi DEFS='-DSHIM_SERIAL=1 -DSHIM_CRC=1'` — `strings`
afterward found `SHIMCRC o=` in both `shims/build/shim.bin` and
`build/1ST_READ.BIN`, confirming the flags actually compiled in this time.
**Any future diagnostic (or release) rebuild in this repo must `make clean`
first, or verify the requested flags landed with `strings`/`nm`** — `make`'s
exit code and "up to date" message do not prove it (`docs/kb/tooling.md`
carries this as a standing gotcha for later tasks).

### Fork change — TEXERR classifier-cell sampler (extension)

`../flycast4naomi2dreamcast` (canonical) commits `8b1d45f2e` (sampler) +
`a13662ff1` (`INSTRUMENTATION.md` row), cherry-picked clean into the
launched tree `../cleopatra/tools/flycast-src` as `875aea8ff` + `b4763c1e8`,
rebuilt (`docs/kb/tooling.md` has the full recipe/output). `cartlog_texerr_tick()`
(`core/hw/naomi/naomi.cpp`) reads three `mem_b`-offset words — the same
direct-array-read idiom `cartlog_shimwatch2`/`WATERMARK` already use in this
file, not a new mechanism — at P1 `0x8c1a20a0` (failing index), `0x8c1a20a8`
(KAMUI2 error code), `0x8c1a2098` (live-surface count), and is called from
`core/hw/pvr/pvr_regs.cpp`'s existing `STARTRENDER`-write `cartlog()` site
(the one that already emits `PVRW STARTRENDER=...` every vblank on the DC
profile — device/MMIO write dispatch, fires regardless of
interpreter/dynarec). The call throttles itself to every 64th invocation and
only prints on the first sample or a value change:

```c
cartlog("TEXERR idx=%08x code=%08x d98=%08x\n", idx, code, cnt);
```

### Step 3 — unattended control leg

```
scripts/capture_dc_leg.sh phase5/instrument-ctl build/disc.gdi \
    -config Debug:SerialConsoleEnabled=yes & sleep 300; \
FPID=$(pgrep -f "Flycast.app/Contents/MacOS/Flycast" | head -1); \
kill -USR1 $FPID; sleep 5; kill -9 $FPID; wait
```

`captures/phase5/instrument-ctl.log` — 367,518 lines, 12 MB.
`captures/phase5/instrument-ctl.stdout.log` — 186 lines (89 `SHIMCRC`
lines). Duration bounded by file mtimes (the one-shot PVR-engine dump this
build also emits, `pvr_regs.cpp:200-214`, to `13:33:23`; the cartlog's own
last write to `13:38:19`) at **~296 s** — inside the brief's "~5 min" ask.
**Anomaly, recorded not rationalized:** the final `kill -9 $FPID` reported
"no such process" — the emulator had already exited (cleanly: the log's last
line is a complete, non-truncated `TAEND`, and `grep -i
"abort|crash|signal|disconnected"` on the `.stdout.log` finds nothing) a few
seconds before the scripted kill sequence should have reached it. Neither
this leg's data (checked below) nor the checker's verdict depend on the
exact kill timing, so this did not block the task, but it is flagged for
whoever runs the next unattended DC leg — the `kill -USR1`/`kill -9` pattern
may not always need its second step.

### Step 4 — checker + TEXERR baseline + perf sanity

```
$ python3 scripts/check_stream_crc.py --stdout captures/phase5/instrument-ctl.stdout.log \
    --cartlog captures/phase5/instrument-ctl.log --dat senkosp.dat --track04 build/track04.iso
== lowfad (4 record(s), fad < 450150) ==
  GDDMA fad=0000b05e secs=7 type=800 crc=cef5f730 -> lowfad
  GDDMA fad=0000b065 secs=9 type=800 crc=15af9f55 -> lowfad
  GDDMA fad=0000b06e secs=1 type=800 crc=b5b9fe9f -> lowfad
  GDDMA fad=0000b072 secs=1 type=800 crc=0a2960f6 -> lowfad
CHECK shimcrc_match: PASS — 89 SHIMCRC record(s), 0 mismatch(es)
CHECK gdread_match: PASS — 420 verified (fad>=base,type=0x800), 4 lowfad, 0 typeskip, 0 mismatch(es)
CHECK coverage_nonzero: PASS — shim=89 record(s), drive=424 record(s)
```

**All three CHECKs PASS.** Every delivered (`SHIMCRC`) and drive
(`GDPIO`/`GDDMA`) record verified against ground truth (`senkosp.dat` /
`build/track04.iso`); both streams non-empty; the 4 `lowfad` records are the
expected sub-`base_fad` TOC/low-track reads, never a fail condition (same
ruling as every prior leg using this checker's drive-side logic).

`grep -c 'PVRW STARTRENDER' captures/phase5/instrument-ctl.log` → **16,958**
over ~296 s ≈ **57.3/s**. Phase 4 references, same order of magnitude (tens
of Hz, not a collapse to single digits nor an explosion to thousands):
`attract8` (Naomi profile, unattended, ~360 s) — 5,537 STARTRENDER ≈ 15.4/s
(`docs/kb/phase4-conversion.md` §Attract — maple/MIE service live); `play1`
post-freeze error loop (DC profile, operator leg) — 24,771 STARTRENDER over
the documented 719.3 s stdout gap ≈ 34.4/s (`docs/kb/phase4-conversion.md`
§Texture-error hang (play1)). This leg's 57.3/s is *higher* than both
references — no stutter class, no perf collapse.

`grep -c TEXERR captures/phase5/instrument-ctl.log` → **8** lines over 265
throttled samples (16,958 STARTRENDER ÷ 64) — not runaway repetition, and
one of the 8 is the intended cold-start baseline:

```
128:   TEXERR idx=e1800401 code=e5830000 d98=e20220ff   (pre-boot mem_b garbage — the first
                                                          sample, before the game's own image
                                                          has initialized this RAM region)
15368: TEXERR idx=ffffffff code=00000000 d98=00000015   (post-init baseline: code=0, healthy)
31800: TEXERR idx=ffffffff code=00000000 d98=00000017
43654: TEXERR idx=ffffffff code=00000000 d98=00000019
90872: TEXERR idx=ffffffff code=00000000 d98=00000022
148429:TEXERR idx=ffffffff code=00000000 d98=00000035
160387:TEXERR idx=ffffffff code=00000000 d98=00000066
319549:TEXERR idx=00000002 code=00000006 d98=00000054    <-- see finding below
```

**Refinement to the extension's own prediction.** The brief expected "on a
healthy attract leg... exactly one baseline line (all cells expected
stable)". That assumption does not hold: `0x8c1a2098` (the live-surface
counter) legitimately climbs during attract (`0x15→0x17→0x19→0x22→0x35→0x66`,
21→23→25→34→53→102 decimal) as the demo loop streams in new textures — real
signal, not noise, and not the flood the "cap or reconsider" acceptance
clause was guarding against (8 lines across a 367K-line/296 s capture).

### Finding — this control leg independently reproduced the texture-error hang

The last `TEXERR` line, at cartlog line 319,549, is `code=00000006` — a
live, in-the-wild occurrence of the T1/T4 class (§Texture-error handler
above: `*0x8c1a20a8 == 6` is either "out of VRAM arena" (T1, category (b),
our bug) or "illegal texture header" (T4, category (a))), with `idx=2` (the
3rd texture-list entry). This happened during a **fully unattended,
input-free attract-mode leg** — not an operator-played match, the only
context Phase 4's `play1` observed it in (`docs/kb/phase4-conversion.md`
§Texture-error hang: "once in ~6 sessions"). This is the **second recorded
occurrence overall, and the first with any classifier-cell evidence
attached**.

The log signature matches `play1`'s confirmed (screenshot-verified) hang
exactly, checked mechanically, not eyeballed:

```
awk 'NR<=319549 && /MDODMA/{a++} NR>319549 && /MDODMA/{b++} END{print a, b}' \
    captures/phase5/instrument-ctl.log
# -> 110334 0   -- MDODMA (maple/JVS activity) never appears again after the TEXERR line

awk 'NR>319549 && /^C2D/{t++} NR>319549 && /C2D src=0c17e360/{a++} \
     NR>319549 && /C2D src=0cedbc00/{b++} END{print t, a, b}' \
    captures/phase5/instrument-ctl.log
# -> 6396 3198 3198  -- every single post-TEXERR C2D submission, to EOF, is the
#                       SAME two src addresses play1 documented as its frozen-frame pair
```

`0c17e360`/`0cedbc00` are the identical `C2D src=` values
`docs/kb/phase4-conversion.md` §Texture-error hang (play1) names as the
constant per-frame background/overlay pair the game keeps re-submitting once
its own fatal-error display loop (`FUN_8c0ad720`, never returns) takes over
— render loop alive, maple/input dead, exactly reproduced here. STARTRENDER
itself does not stall either: 13,761 before the marker vs. 3,197 after,
both healthy nonzero rates, matching `play1`'s "the render loop does not
stop" finding.

**What this does and does not establish.** It does **not** by itself decide
T1 vs. T4 — that requires the VRAM free-list read the extension scoped out
("savestate forensics covers those"), a Task 6/7 item. It does **not** carry
a screenshot (no `FLYCAST_SHOT` was set for this leg) — the log-signature
match to `play1` is strong but indirect corroboration, not a visual
confirmation. What it *does* establish: the hang Task 4 characterized as
rare and operator-triggered can fire with **zero player input**, inside a
~5-minute attract-mode window, which is a materially different rarity/
reproducibility picture than "once in ~6 played sessions" — worth carrying
into Task 6/7's evidence base as a second, differently-obtained data point,
not a replacement for `play1`'s.

### Step 5 — release rebuild + md5 check against criterion 7

`make clean && make gdi` (no `DEFS`, release defaults) — exit 0. `strings
build/1ST_READ.BIN | grep SHIMCRC` → no match, confirming the diagnostic
flags do not linger in the shipping build.

```
MD5 (build/track01.iso) = 681fa4c8daa058ce2df8ea1b604d6e91   == criterion 7
MD5 (build/track02.raw) = 03c796f60db2e9ef0b65a42a47a9d321   == criterion 7
MD5 (build/track03.iso) = b05c578ec5bbe6e39731848b99df73e8   == criterion 7
MD5 (build/track04.iso) = 126e587e977315febaac0c833ed86777   != criterion 7 (89ccb3e02522a8bd802f762ee1f74a2f)
MD5 (build/disc.gdi)    = c527f1ec937b56caa65084d436f8c0a0   == criterion 7
```

Four of five match byte-identically. `track04.iso` (the loader+cart track)
legitimately differs. Confirmed deterministic, not a build flake first: two
consecutive `make clean && make gdi` runs in this session produced the
identical `126e587e977315febaac0c833ed86777` both times.

**Root cause — empirically isolated (fix round 1), not just inferred from
reading the diff.** `git log --oneline -- shims/src/gd.c` shows Phase 5 Task
1's `dc64fbb` ("SHIM_CRC delivered-bytes probe in gd_read_cart") landed
**after** Phase 4 Task 14 captured the criterion-7 baseline, and its diff
adds `shim_crc32()` **unconditionally** — only the call site inside
`gd_read_cart` is `#if SHIM_CRC`-gated, the function definition is not. That
reading only proves the source *could* be the cause; it doesn't rule out the
unreferenced function being dead-code-eliminated at `-Os`, which would make
the diff a no-op for the compiled bytes. Isolated with a single-variable
before/after rebuild of `shims/` alone (same toolchain, same `mie_blobs.c`
generation, no `DEFS` in either run — everything held constant except
`gd.c`'s content):

```
$ git checkout 3bb4d05 -- shims/src/gd.c   # pre-Task-1 gd.c (9994370, last Phase 4 commit)
$ make -C shims clean && make -C shims
$ wc -c < shims/build/shim.bin; md5 shims/build/shim.bin
5896
MD5 (shims/build/shim.bin) = adce0a3702b701ec7eb41feb1f809eac

$ git checkout HEAD -- shims/src/gd.c      # restore Task 1's gd.c
$ make -C shims clean && make -C shims
$ wc -c < shims/build/shim.bin; md5 shims/build/shim.bin
5948
MD5 (shims/build/shim.bin) = 035d3537024c0b39c7b7f0615cede0a7
```

Pre-Task-1 `gd.c` reproduces exactly the **5,896 B** Phase 4 artifact;
restoring Task 1's `gd.c` reproduces exactly **5,948 B**, a **+52 B**
delta with no other variable changed. This both root-causes the divergence
(the only changed input is `gd.c`) and confirms `shim_crc32()` is **not**
dead-code-eliminated under `SHIM_CRC=0` at `-Os` — the assumption the first
pass of this section made silently is now measured, not asserted. Because
`shim.bin` is embedded byte-for-byte into `shim_blob.o` → linked into
`loader.elf` → `objcopy`'d into `1ST_READ.BIN` → placed into `track04.iso`
by `make_gdi.py` (all deterministic, unchanged steps — §GDI mastering,
`docs/kb/tooling.md`), this +52 B at the shim layer is sufficient to explain
`track04.iso`'s md5 divergence without needing to isolate any further link
in that chain. Working tree left at HEAD (`git checkout HEAD --
shims/src/gd.c`, confirmed via `git diff --stat` = no output) and the
release disc rebuilt clean afterward (`make clean && make gdi`,
`track04.iso` reproduces the same `126e587e977315febaac0c833ed86777`
recorded above; `strings build/1ST_READ.BIN | grep SHIMCRC` → no match);
`git status` clean except this doc edit.

The disc mastered by this task is the correct, current release output;
criterion 7's `track04.iso` entry in `docs/kb/phase4-conversion.md` is now
stale as a byte-reproducibility check (superseded by Task 1's landed code,
not by anything in this task) and would need a fresh baseline capture to be
useful again — not done here, out of this task's scope.

### Verdict

**Instrument control test: PASS.** All three `check_stream_crc.py` CHECKs
pass on a live DC-profile leg; both delivered and drive-truth streams verify
against ground truth; no perf collapse (57.3 STARTRENDER/s, above both Phase
4 reference rates). The TEXERR extension performed exactly as designed —
one baseline line, a few legitimate content-driven lines, no flood — and,
unplanned, caught a second live occurrence of the texture-error hang with
its first classifier-cell evidence (`code=6`, `idx=2`), which is now part of
the evidence base for Task 6/7 rather than a control-leg defect.

## Auto-savestate capture (Task 6)

**Question (controller re-scope, superseding the Task 6 brief's
operator-legs plan):** Task 5's control leg proved the hang reproduces
unattended, but carries no RAM state — the classifier table above (§What
this means for the Task 7 verdict) needs the VRAM free-list / `TXTR` chunk
structures at the hang to separate T1 (VRAM-arena exhaustion, category (b),
our bug) from T4 (illegal header, category (a)). Task: extend the fork so
the next occurrence auto-saves a savestate, then capture one.

### Fork change — one-shot TEXERR auto-savestate

`../flycast4naomi2dreamcast` (canonical) commits `167661363` (sampler
extension) + `afc25186f` (`INSTRUMENTATION.md` row), cherry-picked clean
into `../cleopatra/tools/flycast-src` as `631e7b9d6` + `c3d0c8451`, rebuilt
(`docs/kb/tooling.md` §Phase 5 Task 6 fork commits has the full recipe).

**Threading finding, not assumed.** `cartlog_texerr_tick()` runs on the
`"Flycast-emu"` thread (`core/emulator.cpp` `Emulator::start()`,
`std::async` with `ThreadName _("Flycast-emu")`, driven by the STARTRENDER
MMIO write during SH4 execution). `dc_savestate()`'s only existing callers
(`core/sdl/sdl.cpp`, `core/ui/gui.cpp`) all run on the `"Flycast-rend"`
thread (`core/ui/mainui.cpp` `mainui_loop()`, `ThreadName _("Flycast-rend")`)
via `mainui_rend_frame()` → `os_UpdateInputState()` → `input_sdl_handle()`.
Calling `dc_savestate()` (or the `emu.stop()`/`emu.start()` wrapper
`gui_saveState()` already uses for its own `AutoSaveState` path,
`core/ui/gui.cpp:1635`) directly from the emu thread would self-join-deadlock:
`Emulator::stop()` calls `checkStatus(true)` to wait on its own
`std::async` result (`core/emulator.cpp`), and a thread cannot join itself.
**Decision: split arm/execute across the two threads**, not a direct call.
`cartlog_texerr_tick()` (emu thread) only flips a one-shot
`std::atomic<bool>` latch (`g_texerrSavePending`, plus `g_texerrSaveCode`
for the log line) on the classifier cell `0x8c1a20a8`'s 0→nonzero
transition. A new `cartlog_texerr_save_poll()` (`core/hw/naomi/naomi.cpp`),
called once per frame from `mainui_rend_frame()` (render thread), checks
the latch and — precisely mirroring `gui_saveState(stopRestart=true)` —
runs `emu.stop(); dc_savestate(0); emu.start();`, then emits
`TEXERRSAVE code=<hex> slot=0 <path>`. Index 0 (default slot, no user
`SavestatePath` configured) resolves through `hostfs::getSavestatePath(0,
true)` to `~/Library/Application Support/Flycast/data/<basename>.state`;
the poll function queries that exact path before saving rather than
reconstructing it, so the logged path is ground truth, not a guess.

**Sanity leg** (`phase5/task6-sanity`, 90 s unattended, one-call foreground
pattern): 5 `TEXERR` lines, all `code=00000000` after the cold-start
baseline — healthy, no transition, as expected (`docs/kb/tooling.md` §Phase
5 Task 6 fork commits has the counts). The trigger path itself was **not**
exercised by this leg (it can't be — a healthy leg never sees the
transition); the arm/poll split and the deadlock reasoning above were
verified by code read, per this task's scope, not by a forced firing. All
three `check_stream_crc.py` CHECKs PASS on this leg too.

### Repro campaign (Task 6 — unattended soak, supersedes the Task 6 brief's
operator-legs plan per the controller's re-scope)

One 600 s unattended leg (`phase5/soak-1`, one-call foreground pattern,
`-config Debug:SerialConsoleEnabled=yes`, killed by PID) — the campaign
stopped after leg 1 under the SUCCESS condition:

| Leg | Duration | TEXERR lines | Transition? | TEXERRSAVE? | Checker | Notes |
|---|---|---|---|---|---|---|
| `phase5/soak-1` | 600 s (log spans to line 636,994) | 8 (`captures/phase5/soak-1.log` lines 128, 15368, 31800, 43654, 90872, 148429, 160387, 319549) | **YES** — line 319549, `code=00000006` (was `00000000` at line 160387, the immediately preceding sample) | **YES** — line 319564, `code=00000006 slot=0 .../data/disc.state` | `shimcrc_match` PASS (89/0), `gdread_match` PASS (420 verified, 4 lowfad, 0 mismatch), `coverage_nonzero` PASS (shim=89, drive=424) | Hang signature confirmed mechanically (below); savestate preserved |

**Hang-signature cross-check**, same method as the Task 5 control leg:

```
awk 'NR<=319549 && /MDODMA/{a++} NR>319549 && /MDODMA/{b++} END{printf "before=%d after=%d\n", a, b+0}' captures/phase5/soak-1.log
# -> before=110334 after=0        -- maple dead after the marker, same as instrument-ctl

awk 'NR>319549 && /^C2D/{t++} NR>319549 && /C2D src=0c17e360/{a++} NR>319549 && /C2D src=0cedbc00/{b++} END{print t, a, b}' captures/phase5/soak-1.log
# -> 42326 21163 21163            -- every post-marker C2D is the same frozen-frame pair (21163+21163=42326)
```

`grep -i 'abort|crash|signal|disconnected|fatal' captures/phase5/soak-1.stdout.log` → no matches. Same
log signature as `play1` (`docs/kb/phase4-conversion.md` §Texture-error
hang) and `instrument-ctl` (§Instrument control test above): render loop
alive, maple/input dead, no reset attempted — this is the same hang, not a
new failure mode.

### The capture

`TEXERRSAVE code=00000006 slot=0 /Users/captainkoffski/Library/Application
Support/Flycast/data/disc.state` (`captures/phase5/soak-1.log:319564`, 15
cartlog lines after the marker at line 319549 — one TA-list/PVR-register
cycle in between, `captures/phase5/soak-1.log:319550-319563`: two
`SOFTRESET`/`TA_ALLOC_CTRL`/`TA_LIST_INIT` sequences and one
`TAREG`/`C2D`/`TAEND` render, i.e. the save fired within the same or the
next rendered frame after detection, not a multi-second delay). `disc.state`
(not
`senkosp.state`): `hostfs::getSavestatePath()`'s basename comes from
`settings.content.fileName` (`core/oslib/oslib.cpp`), and
`capture_dc_leg.sh` loads `build/disc.gdi` directly — a different content
path than the Phase 3 canary-snapshot's `AutoSaveState` route, hence the
different basename; **both are index 0, same file-naming logic, no
divergence in the mechanism itself.**

**Preserved immediately** (savestates are overwritten by later runs, per
this task's rule) to `captures/phase5/soak-1-texerr.state`:

```
$ ls -la captures/phase5/soak-1-texerr.state
-rw-r--r--  8554748  captains  ...  captures/phase5/soak-1-texerr.state
$ md5 captures/phase5/soak-1-texerr.state
MD5 (captures/phase5/soak-1-texerr.state) = 1d3a3c6d943ec93292732f17dd7704d4
```

8,554,748 bytes (nonzero, RZip-compressed — same format as the Phase 3
canary-snapshot, `docs/kb/tooling.md` §Phase 3: RAM snapshot; the
`Flycast[...] N[SAVESTATE]: Saved state to .../disc.state size 28106129`
line in `captures/phase5/soak-1.stdout.log` records the pre-compression
serialized size). **Carving this state (locating the VRAM free-list and
`TXTR` chunk structures to decide T1 vs. T4) is out of this task's
re-scoped goal** ("make the next captured occurrence carry a RAM snapshot,
then capture one") and is left for Task 7, using the same carve procedure
Phase 3 established (RZip magic scan → inflate chunks → locate by
plaintext/known-offset landmark).

### Verdict

**SUCCESS on the first soak leg.** The one-shot auto-savestate fired
exactly as designed on a live, unattended, independently-reproduced
occurrence of the texture-error hang (`code=6`, `idx=2` — the same T1/T4
class the Task 5 control leg caught without RAM evidence); the resulting
`disc.state` is preserved outside the emulator's overwrite-prone savestate
directory, nonzero-size, and md5-recorded. Both the sanity leg and the
capture leg pass all three `check_stream_crc.py` CHECKs, so the delivered-
and drive-truth streams remain verified on every leg this task ran. No
BLOCKED symptoms observed (no TEXERR flood — 8 lines over a 636,994-line
capture; no checker mismatches; the save/stop/start sequence did not crash
or hang the emulator — the process continued logging `SHIMCRC`/`GDPIO`
records and the render loop stayed alive per the C2D evidence above). The
soak campaign's BUDGET ceiling (8 legs) was never approached.

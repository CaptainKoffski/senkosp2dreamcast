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

> **Correction 2026-08-23 (Task 7).** `*0x8c1a2090` is the **texture-object**
> array, not the VRAM-block descriptor array. The real block descriptors are a
> third pool at `[0x8c170eb8 + 0x20]`, stride `0x18`. Evidence and the
> decompilation that shows it: §Texture-error hang verdict, Step 3. Every
> other address in this paragraph verified correct against the Task 6 RAM
> image.

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
      > **Correction 2026-08-23 (Task 7).** It is **first-fit**, not
      > best-fit. The walk breaks on the *first* node with
      > `size >= request` (`FUN_8c03c46e`, `Decomp.java`), and the free list
      > is not size-ordered: its insert helper `FUN_8c03c830`
      > (`0x8c03c830`) is an unconditional **head-insert** with no size
      > comparison. Immaterial to the Task 7 verdict (one free node), but
      > material to any fix that reasons about placement or fragmentation.
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

**Anomaly, recorded not rationalized — Bash-tool timeout hard cap cut the
kill sequence.** The one-call foreground pattern's `timeout` parameter was
set to 700000 ms (leg length + 100 s margin, per the ≥leg-length+60s rule),
but the tool clamped actual execution to a **600000 ms (10 min) hard cap**
and returned exit 143 ("Command timed out after 10m 0s") — cutting the
`sleep 5; kill -9 $FPID; wait` tail of the compound command before it could
report a clean exit, even though the leg itself (launch → 600 s sleep →
`kill -USR1`) had already run to completion inside that window. Not a
corruption: `captures/phase5/soak-1.log`/`.stdout.log` are complete (both
end past the marker, no truncation), and `pgrep -fl Flycast` found no
orphaned process afterward, so the SIGTERM the tool sends on timeout
evidently reached the backgrounded Flycast child too. **Standing rule for
future soak legs:** the one-call foreground pattern cannot safely fit a leg
whose `sleep` alone is ≥ 600 s, because the pattern's own kill tail
(`kill -USR1`, `sleep 5`, `kill -9`, `wait`) needs headroom inside the same
600000 ms ceiling the tool enforces regardless of a larger requested
`timeout` value. **Keep unattended-leg `sleep` ≤ ~550 s under this
pattern, or split the launch and the kill sequence across two separate
tool calls (PID captured from the first, passed to the second) for a leg
that genuinely needs to run longer.**

Two smaller caveats, noted while in this section:

- The `TEXERRSAVE` path contains a space (`.../Application Support/...`) —
  fine for a human reading the log line, but unparsed today: any future
  tooling that whitespace-splits a `TEXERRSAVE` line to extract the path
  will break on it. Read the remainder of the line after `slot=0 ` verbatim
  instead.
- The savestate is one-shot by design (`armed_once` latch,
  `core/hw/naomi/naomi.cpp`): if `emu.stop()`/`dc_savestate()`/`emu.start()`
  ever throws inside `cartlog_texerr_save_poll()`, the pending flag was
  already consumed before the `try` block ran, so that occurrence is burned
  — no retry, no second savestate later in the same process. Accepted
  tradeoff for this task (it matches "one-shot per process" from the
  dispatch), not a bug; a future task wanting retry-on-failure would need
  to re-arm the latch from the `catch` block instead.

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

## Texture-error hang verdict (Task 7)

**Question (spec §Work item 1, task brief
`.superpowers/sdd/2026-08-23-phase5-hardware/task-7-brief.md`, refined by the
controller's re-scope):** the Task 6 soak leg captured a savestate at the
hang. Which of T1–T6 fired, and therefore which of the brief's four verdicts
applies? The two Task 4 collisions matter here: `code == 6` is **T1** (VRAM
texture-arena exhaustion, category (b), our fit bug) **or T4** (illegal
texture header, category (a)) — see §Trigger taxonomy and §Limits above.

**Verdict, up front: T1 — VRAM texture-arena exhaustion. Brief verdict 2:
our fit bug. NOT exoneration; the hard gate is not satisfied and a fix is
required.** T4 is excluded by six independent cell reads, T2/T3/T5/T6 by the
error code and the table occupancies. Delivered and drive CRCs are clean on
this leg and the failing asset's bytes in RAM are byte-identical to the
ground-truth cart image — the bytes were never the problem. The evidence
follows.

### The evidence set

- `captures/phase5/soak-1.log` — 636,994 lines. `TEXERR idx=00000002
  code=00000006 d98=00000054` at line 319,549; `TEXERRSAVE code=00000006
  slot=0 …/disc.state` at line 319,564.
- `captures/phase5/soak-1-texerr.state` — 8,554,748 B, md5
  `1d3a3c6d943ec93292732f17dd7704d4` (§The capture above). **Never
  committed** (ROM-derived); the carve recipe is in `docs/kb/tooling.md`
  §Phase 5: DC-profile RAM snapshot from a TEXERR savestate.
- Checker on the same leg, re-run first-hand for this verdict:

```
$ python3 scripts/check_stream_crc.py --stdout captures/phase5/soak-1.stdout.log \
    --cartlog captures/phase5/soak-1.log --dat senkosp.dat --track04 build/track04.iso
CHECK shimcrc_match: PASS — 89 SHIMCRC record(s), 0 mismatch(es)
CHECK gdread_match: PASS — 420 verified (fad>=base,type=0x800), 4 lowfad, 0 typeskip, 0 mismatch(es)
CHECK coverage_nonzero: PASS — shim=89 record(s), drive=424 record(s)
```

**New finding — the hang is deterministic, not a 1-in-6 race.** The Task 5
control leg (`instrument-ctl`) and the Task 6 soak leg (`soak-1`) are two
independently launched processes, and their cartlogs are **byte-identical for
all 319,549 lines up to and including the marker**:

```
$ head -319549 captures/phase5/instrument-ctl.log | md5   # 19cf13c13575cb7908b398fde0ddb833
$ head -319549 captures/phase5/soak-1.log          | md5   # 19cf13c13575cb7908b398fde0ddb833
```

Same eight `TEXERR` lines at the same line numbers, same `idx=2 code=6
d98=0x54`. Phase 4's "once in ~6 sessions" (`docs/kb/phase4-conversion.md`
§Texture-error hang) described *operator-played* sessions; on the input-free
attract path this failure is reproducible to the log line. That makes the
forensics below a reading of a repeatable state, not of a one-off accident.

### Step 1 — carving main RAM (recipe: `docs/kb/tooling.md`)

The savestate is **RZip**, not zstd: `FLYSAVE1` header, then the magic
`#RZIPv\x01#` at file offset `0x18`, `maxChunkSize = 0x00100000`,
`totalSize = 28,106,129` — which equals the `size 28106129` the fork logged
in `captures/phase5/soak-1.stdout.log`. 27 zlib chunks inflate to exactly
28,106,129 B, consuming the file to its last byte.

Main RAM located by the **marker scan** Phase 3 established
(`docs/kb/tooling.md` §Phase 3: RAM snapshot) — layout-independent, no
serializer parsing — using two markers that must agree:

| Marker | Stream offset | Implied RAM base |
|---|---|---|
| `"\nsyMalloc Ver 2.01"` (RAM `0x8c15c980`) | `0xc28d94` | `0xacc414` |
| boot-image head, `senkosp.dat[0:0x1000]` (RAM `0x8c020000`) | `0xaec414` | `0xacc414` |

Both give `0xacc414`, and `0xacc414 + 16 MB = 0x1acc414` lands 6,525 B short
of the stream end — i.e. the DC profile's 16 MB main RAM is the last large
block in the stream, an independent corroboration of the base. (A second
`syMalloc` banner copy at stream `0x1908d94` is *inside* the same 16 MB
window, at RAM offset `0xe3c980` (= `0x1908d94 - 0xacc414`); it is a data copy, not a second RAM
region — the boot-image head does not match there.)

**Carve control tests** (Phase 3's list, run against the extracted 16 MB):

| Test | Result |
|---|---|
| `ram[0x15c980..]` = syMalloc banner | ✓ |
| `ram[0x15b2c4..]` = GDFS error strings (`E00000009:`, `Illegal File Name`) | ✓ |
| `ram[0x20000:0x21000] == senkosp.dat[0:0x1000]` | ✓ |
| `ram[0x85b00:0x85bb4] == senkosp.dat[0x65b00:0x65bb4]` (heap-create code) | **1 word differs — expected** |
| loaded-image span diff (`0x171ff8` B) | 1,350 B (Phase 3 Naomi snapshot: 907 B) |

The single word that breaks the fourth test is `0x8c085b50`: RAM
`0x4028cb8d` vs `.dat` `0x4028cb8e` — **exactly** this port's heap-top
relocation patch (`scripts/reloc_patchset.json`, `dat_offset 0x65b50`,
`0x4028cb8e → 0x4028cb8d`). The control test therefore passes in its
corrected DC form: the only divergence is a patch we authored. All addresses
below are P1 (`0x8c…`); RAM offset = `(addr & 0x1fffffff) − 0x0c000000`.

### Step 2 — the relocation seeds are live in this image

| Cell | Value at the hang | Meaning |
|---|---|---|
| `0x8c19e4bc` | `0x00010000` | `kmInitDevice` device word — still the Naomi device id the game passes |
| `0x8c19e4bc + 0x7f8` = `0x8c19ecb4` | `0x00800000` | KAMUI2 total-VRAM-size state — **8 MB**, i.e. our patch took |
| `0x8c170ebc` (config block + 4) | `0x00800000` | same value in the KAMUI2 config block |

For contrast, Phase 3's *Naomi* RAM snapshot recorded `state+0x7f8 =
0x01000000` and the config block runtime-overwritten to `0x01000000`
(`scripts/reloc_patchset.json`, `dat_offset 0x1203c` rationale). The 16 MB →
8 MB VRAM-size patch is confirmed **live at the moment of the hang** — this
is the DC-shaped arena, not the Naomi one.

### Step 3 — the classifier cells

Read straight out of the RAM image; they reproduce the log line exactly.

```
8c1a2080: 00000000 37800080 8ce95d20 00000100
8c1a2090: 8ce93500 00000100 00000054 00000000
8c1a20a0: 00000002 ffffffff 00000006 00000000
```

| Cell | Value | Meaning (pool word verified in this image) |
|---|---|---|
| `0x8c1a20a0` | `0x00000002` | failing texture-list index = 2 (`DAT_8c070de0` = `0x8c1a20a0` ✓) |
| `0x8c1a20a8` | `0x00000006` | KAMUI2 error code (`DAT_8c03ffe4` = `DAT_8c03fc74` = `DAT_8c040844` = `0x8c1a20a8` ✓) |
| `0x8c1a2098` | `0x00000054` = 84 | live-surface counter (`DAT_8c040838` = `DAT_8c03fc78` = `0x8c1a2098` ✓) |
| `0x8c1a2088` / `0x8c1a208c` | `0x8ce95d20` / `256` | surface array base / capacity |
| `0x8c1a2090` / `0x8c1a2094` | `0x8ce93500` / `256` | texture-object array base / capacity |

**Correction to §Texture-error handler's structure names (2026-08-23; a
dated pointer to this correction is filed in place at that section).** That section
called `*0x8c1a2090` the "VRAM-block descriptor array (stride `0x28`)". The
decompilation of `FUN_8c03fb58` (`Decomp.java 0x8c03fb58`) shows it is the
**texture-object** array — `FUN_8c03fb58` scans it at `piVar2 + 10`
(int-stride 10 = `0x28` bytes) for `*entry == -1` (free) — and the real
**VRAM-block descriptor** pool is a *third* table, rooted in the KAMUI2
config block at `[PTR_DAT_8c03c7c0 + 0x20]`, stride `0x18`, capacity
`[+8]`. Both `PTR_DAT_8c03c7c0` and `PTR_DAT_8c03c4c0` resolve to the same
config block `0x8c170eb8` in this image. The stride-`0x18`/`0x28`
attribution in the earlier section was therefore swapped; every other claim
in it (cell addresses, error codes, call chain) verified unchanged.

### Step 4 — structure layouts, derived from decompilation

All layouts below come from `scripts/ghidra/run.sh script Decomp.java <fn>`
against the committed harness, not from guesswork; the RAM image then
confirms each one.

**VRAM-block descriptor** (`FUN_8c03c46e`, `0x8c03c46e`; pointer arithmetic
in the decompilation is `ushort*`, so `+n` = byte `+2n`):

| Byte offset | Field | Decompiler expression |
|---|---|---|
| `+0x00` (u16) | flags: `1` = allocated, `\|0x10` bank 0, `\|0x20` bank 1, `\|param_1` type | `*puVar2 = 1; … \| 0x10 … \| param_1` |
| `+0x04` | prev link | — |
| `+0x08` | next link | `puVar4 = *(ushort **)(puVar1 + 4)` |
| `+0x0c` | VRAM byte address | `*param_3 = *(undefined4 *)(puVar2 + 6)` |
| `+0x10` | block size | `*(uint *)(puVar1 + 8) < param_2` |
| `+0x14` | owner (back-pointer to the requester's address slot) | `*(undefined4 **)(puVar2 + 10) = param_3` |

Node stride `0x18` (confirmed: consecutive live nodes are `0x18` apart).

**Config block `0x8c170eb8`** (from `FUN_8c03c46e` / `FUN_8c03c764`, values
read at the hang):

| Offset | Value | Meaning |
|---|---|---|
| `+0x04` | `0x00800000` | total VRAM size (the patched seed) |
| `+0x08` | `0x105` = 261 | block-descriptor pool capacity (`FUN_8c03c764`'s loop bound) |
| `+0x20` | `0x8ced7d80` | block-descriptor pool base, stride `0x18` |
| `+0x24` / `+0x28` | `0x8ced85a8` / `0x8ced7d98` | bank-0 **allocated** list head / tail |
| `+0x2c` / `+0x30` | `0x8ced7d80` / `0x8ced7d80` | bank-0 **free** list head / tail |
| `+0x34…+0x40` | all `0` | bank 1 — unused |

**Texture object** (stride `0x28`; `FUN_8c03ff38` passes `texobj + 4` as
`FUN_8c03ea1c`'s `param_1`, so `param_1[k]` = byte `texobj + 4 + 4k`):

| Byte offset | Field | Written by |
|---|---|---|
| `+0x00` | name / global index; `-1` = slot free | `FUN_8c040648`, `**(int **)(local_1c+0xc) = local_14` |
| `+0x04` | `format << 16 \| 2` (or `\|3`) | `FUN_8c03ea1c` `*param_1` |
| `+0x08` | `1` | `param_1[1] = 1` |
| `+0x0c` | format-class value | `param_1[2]` |
| `+0x10` | declared width | `param_1[3] = param_2` |
| `+0x14` | declared height | `param_1[4] = param_3` |
| `+0x18` | computed VRAM byte size | `param_1[5] = FUN_8c03ed78(param_1)` |
| `+0x1c` | derived flag word (low 6 bits = the w/h codes) | `param_1[6]` |
| `+0x20` | **VRAM address slot** — the allocator's `param_3` | `param_1 + 7` in `FUN_8c03f38c` |
| `+0x24` | `1` once the surface is complete | `FUN_8c040648` |

Confirmed against the arena, with the exceptions stated: **83 of the 87**
allocated blocks have `owner` = `0x8ce93500 + 0x20 + n*0x28` — exactly
`&texobj[n].vram_addr`. The four that do not are:

| vaddr | size | flags | owner | reading |
|---|---|---|---|---|
| `0x00000000` | 262,144 | `0x0043` | `0x8c00ee4c` | region/TA block, owned by a non-texture caller |
| `0x00040000` | 1,228,800 | `0x0013` | `0x8c00ee3c` | scan-out framebuffer pair, same |
| `0x00179000` | 6,144 | `0x0011` | `0x8c1a219c` | **KAMUI2-internal**, not a game texture — `0x8c1a219c` is the `vaddr` slot of a 4-word global struct at `0x8c1a2190` = `{0x80, 0x1800, 0x40000024, 0x179000}` (count `0x80`, size `0x1800` = the block's own size, flags, vaddr). Carries the texture type nibble (`0x0011`) but no texobj owns it. |
| `0x0053bc20` | 4,096 | `0x0015` | `0x8ced9600` | owner outside the texobj array; this is the block §Step 5 lists as the unattributed `0x1000` allocation — see below |

**The missing index is 45, and it explains the `0x1000` block.** The set of
referenced texobj indices is `{0…83} \ {45}`. `texobj[45]` (`0x8ce93c08`) is
`name 0xbd`, **32×32**, computed size **512 B**, `vaddr = 0x0053bc20` — the
*same* VRAM address as the 4,096 B `flags=0x0015` block, which is owned by
something else. So that block is best read as a **sub-allocated page that
small textures are carved out of**, with `texobj[45]` a tenant rather than
the owner. Stated as evidence, not mechanism: the sub-allocator itself
(`0x8ced9600`'s struct) was **not** traced, so "page for small textures" is
the reading, not a derived fact.

**Do not read the four 84s as one four-way confirmation.** `*0x8c1a2098` =
84, texobj slots in use = 84 and surfaces in use = 84 *are* a genuine
three-way agreement — all three count live surfaces. The count of
`flags=0x0011` VRAM blocks is also 84, but that is a **coincidence**: only
83 of them belong to texture objects, the 84th is the KAMUI2-internal
6,144 B block above, and `texobj[45]` holds no block of its own at all.

**Surface** (stride `0x18`): `+0x0c` = texture-object pointer, `0` = slot
free (`FUN_8c03fb58` scans for `*(int *)(iVar4 + 0xc) == 0`); `+0x10` = 1 on
success.

### Step 5 — the VRAM arena at the hang

Walking both bank-0 lists from the config block:

```
BANK 0: alloc_head=8ced85a8 alloc_tail=8ced7d98 free_head=8ced7d80 free_tail=8ced7d80
BANK 1: alloc_head=00000000 alloc_tail=00000000 free_head=00000000 free_tail=00000000

FREE list (1 node):
  @8ced7d80 flags=0001 prev=00000000 next=00000000 vaddr=007dcc20 size=144352 (0x233e0)

ALLOC list: 87 nodes, total 8,244,256 B
```

| Quantity | Value |
|---|---|
| Free, bank 0 | **144,352 B (0x233E0)** — one node, `next = NULL` |
| Allocated, bank 0 | 8,244,256 B across 87 nodes |
| **Total** | **8,388,608 B = 0x800000 = exactly 8 MB** |
| Blocks sorted by `vaddr`, gap check | 88 blocks, span `0x000000…0x800000`, **0 bytes of gap** |

The arithmetic closes on the nose: the arena *is* the whole 8 MB the patched
seed configured, and it is **98.28 % full**. The single free node sits at the
very top (`0x7dcc20 + 0x233e0 = 0x800000`), so there is **no fragmentation
loss whatsoever** — a coalescing or defrag fix would recover exactly zero
bytes. Breakdown of the allocated side by flag word:

| Flags | Count | Bytes | What |
|---|---|---|---|
| `0x0011` | 83 | 6,743,072 | **game textures** — the blocks owned by texobj slots |
| `0x0011` | 1 | 6,144 | **KAMUI2-internal**, `vaddr 0x179000`, owned by the global struct at `0x8c1a2190`, not by any texture object (§Step 4) |
| `0x0013` | 1 | 1,228,800 | scan-out framebuffer pair at `vaddr 0x40000` (= 2 × 640×480×2) |
| `0x0043` | 1 | 262,144 | region/TA block at `vaddr 0x00000000` |
| `0x0015` | 1 | 4,096 | sub-allocated page at `vaddr 0x53bc20`; `texobj[45]` (32×32, 512 B) lives inside it (§Step 4) |

**T2 excluded numerically here:** 84 of 256 surfaces and 84 of 256 texture
objects are in use — neither table is close to full, and a full table would
have written `7`, not `6`, to `0x8c1a20a8` (`FUN_8c03fb58` `0x8c03fbae`).

**`FUN_8c03c46e`'s *other* return-3 cause is also excluded.** It returns 3
either when no free block is large enough **or** when `FUN_8c03c764` finds no
free block descriptor. The descriptor pool is `0x105` = 261 entries
(`0x8c170eb8 + 8`) with **88 in use** (= the 87 allocated + 1 free block),
leaving 173 spare. The pool was not the constraint; the free *space* was.

### Step 6 — the failing request

`FUN_8c03fb58` claims a surface slot and a texture object *before*
`FUN_8c03ff38` runs, and `FUN_8c040648`'s failure path only clears the
**surface** (`*(local_1c + 0xc) = 0`) — it does not scrub the texture
object. So the in-flight descriptor survives the failure. It is the one slot
in the whole table that is marked free yet fully populated:

```
texobj[84] @8ce94220:
  +00 name  = ffffffff   (never claimed - the allocation failed)
  +04 fmt   = 03010002   (= 0x0301 << 16 | 2)
  +08       = 00000001
  +0c       = 08000000
  +10 width = 1024
  +14 heigh = 1024
  +18 size  = 264192  (0x40800)   <-- the request
  +1c flags = 4000003f
  +20 vaddr = 00000000   (never allocated)
  +24       = 00000000   (never completed)

texobj[82] @8ce941d0: name=00000286 fmt=03010002 1024x1024 size=264192 vaddr=0075bc20  (succeeded)
texobj[83] @8ce941f8: name=00000287 fmt=03010002 1024x1024 size=264192 vaddr=0079c420  (succeeded)
surf[84]   @8ce96500: 00000000 00000000 ffffffff 00000000 00000000 00000000   (free)
```

**`surf[84]` proves nothing — recorded, not relied on.** It is
byte-identical to the never-touched `surf[85]` and `surf[86]`, so "cleared by
`FUN_8c040648`'s failure path" and "never used" are indistinguishable here.
It is consistent with the failure path, not evidence of it. The load-bearing
observation is `texobj[84]`: the **only** slot in 256 that is marked free
(`name = -1`) yet carries a fully-populated descriptor, which no other path
produces.

**The request was 264,192 B. The arena's largest — and only — free block was
144,352 B. Shortfall: 119,840 B (117.0 KB).**

`FUN_8c03c46e`'s free-list walk (`while (puVar1 != 0) { if (size < param_2)
next; else { candidate; break; } }`) therefore never found a candidate,
fell to `LAB_8c03c542` and returned **3** → `FUN_8c03f38c` returned 3 →
`FUN_8c03ff38` set `*0x8c1a20a8 = 6` and returned `-1`. That is **T1**,
exactly as §Trigger taxonomy predicted it would look.

### Step 7 — the whole call chain, recovered from the live stack

The boot stack (`0x8c000000`–`0x8c00f000`, `docs/kb/00-status.md`) still
holds the failing frame at the hang, because the error loop `FUN_8c0ad720`
runs *deeper* and never overwrote it:

```
8c00e940: 8ce94220 00000288 8c00e980 00000000
8c00e950: 8c0407f0 8c00e978 8ce92c6c 00000002
8c00e960: 00000288 00000000 8c070b78 8ce92a38
8c00e970: 8c00e980 8c00e978 ffffffff 00000288
8c00e980: 00000301 04000400 00000000 ffffffff
8c00e990: 8c070dbc 40000000 00000000 000000ff
8c00e9a0: 8c0b6370 00000000 000000ff 8c1d9d5c
8c00e9b0: 8c188b33 8c188b8a 8c00ea80 000000ff
```

Every word of the statically-derived chain is present, as return addresses
(each = `jsr` address + 4) and arguments:

| Stack word | Value | What it is |
|---|---|---|
| `8c00e940` | `8ce94220` | **texobj[84]** — the abandoned descriptor above |
| `8c00e944`, `8c00e960`, `8c00e97c` | `00000288` | the texture's name/global index (siblings were `0x286`, `0x287`) |
| `8c00e948`, `8c00e970` | `8c00e980` | pointer to the header struct below |
| `8c00e950` | `8c0407f0` | PR from `FUN_8c0407ba`'s `jsr` to `FUN_8c040648` at `0x8c0407ec` |
| `8c00e958` | `8ce92c6c` | the texture-list struct |
| `8c00e95c` | `00000002` | **the list index — matches `*0x8c1a20a0`** |
| `8c00e968` | `8c070b78` | PR from the slot-1 loader's `jsr` to `FUN_8c0407ba` at `0x8c070b74` — §Texture-error handler's return-false site #2 (that section quoted the range `0x8c070b7a`–`0x8c070b82`, i.e. the store/return tail; the `jsr` itself is at `0x8c070b74` per Ghidra's caller list for `FUN_8c0407ba`, and `PR = jsr + 4`) |
| `8c00e96c` | `8ce92a38` | `&entries[2]` (see below) |
| `8c00e980` | `00000301 04000400` | the header: format `0x0301`, w `0x0400`, h `0x0400` |
| `8c00e990` | `8c070dbc` | PR from `FUN_8c070da8`'s `jsr` to `FUN_8c070d4c` at `0x8c070db8` |
| `8c00e994` | `40000000` | the list entry's flag word — the constant the `TXTR` branch writes |
| `8c00e9a0` | `8c0b6370` | PR from the **print site `jsr` at `0x8c0b636c`** |
| `8c00e9b4` | `8c188b8a` | the address of `"TEXTURE LOAD ERROR !\n"` |

The chain the Task 4 static analysis derived is confirmed end to end by
runtime state, not merely by decompiler inference.

**The texture list.** `*0x8ce92c6c = 0x8ce92a20` (entry array), `[+4] = 4`
(count = 4). Entries are the documented 12 bytes `{data ptr, 0x40000000, 0}`:

| # | data ptr | flags | outcome |
|---|---|---|---|
| 0 | `8c9d84e0` | `40200000` | loaded → texobj[82] (`name 0x286`, VRAM `0x75bc20`) |
| 1 | `8ca18d00` | `40200000` | loaded → texobj[83] (`name 0x287`, VRAM `0x79c420`) |
| 2 | `8ca59520` | `40000000` | **FAILED** — `*0x8c1a20a0 = 2` |
| 3 | `8ca99d40` | `40000000` | never attempted (`FUN_8c070da8` breaks on the first failure) |

(The `0x00200000` bit distinguishes the two that completed from the two that
did not — an incidental corroboration, not a cited primitive.)

### Step 8 — the failing asset, and its bytes

The entry-2 pointer resolves to a standard GBIX+PVRT texture (bytes shown in
file order, grouped by four — not word values):

```
8ca59520: 47424958 08000000 88020000 00000000   "GBIX" len=8 index=0x00000288
8ca59530: 50565254 08080400 01030000 00040004   "PVRT" datalen=264200 pixfmt=01 datatype=03 1024x1024
```

The GBIX global index `0x288` is the same `0x288` on the stack and the next
value in the `0x286`/`0x287` naming sequence. The header word
`FUN_8c03ff38` reads (`*param_2`, at `0x8ca59538`) is `0x00000301` with
`w = h = 1024` at `+4`/`+6` — matching the stack copy at `0x8c00e980`.

**The size the game computed is arithmetically correct**: a 1024×1024 VQ
texture is a 2,048-byte codebook plus one index byte per 2×2 texel =
`2048 + 1024*1024/4` = **264,192 B**, exactly `texobj[84]+0x18`. The
library's own size computation (`FUN_8c03ed78`) is not at fault either. The
`PVRT` `datalen` field reads 264,200, eight more: that field counts the eight
bytes of header info that follow it (`pixfmt`, `datatype`, pad, `w`, `h`)
plus the payload, so `264,200 − 8 = 264,192` — the same number, no
discrepancy. Whole-record size `0x40820` = GBIX `0x10` + `PVRT` tag/len `8` +
264,200.

**Delivered bytes are provably correct — a direct byte comparison, not a
CRC sample.** The complete in-RAM body of the failing texture (header +
264,192 B payload = `0x40820` B) is **byte-identical** to
`senkosp.dat` at file offset `0xb736fe0`, and its 256-byte head occurs
exactly once in the 251 MB image. The three sibling entries likewise:

| entry | RAM | found in `senkosp.dat` at | occurrences |
|---|---|---|---|
| 0 | `8c9d84e0` | `0xb6b5fa0` | 1 |
| 1 | `8ca18d00` | `0xb6f67c0` | 1 |
| 2 (failing) | `8ca59520` | `0xb736fe0` | 1 — full `0x40820` B **IDENTICAL** |
| 3 | `8ca99d40` | `0xb777800` | 1 |

Consecutive, `0x40820` apart: this PAK chunk is four back-to-back 1024×1024
VQ textures, 1,056,768 B of VRAM for the set. This is the strongest form of
the Task 5/6 CRC result — for *this specific asset* the delivered bytes are
not merely CRC-equal at sampled points, they are equal everywhere.

### Step 9 — T4 excluded, branch by branch

`FUN_8c03ea1c` (`0x8c03ea1c`) has exactly three sites that set its return to
`4`. Each writes a distinguishable trace into `texobj+4…+0x1c`, and all
three are excluded by the observed values (`param_4 = 0x00000301`, so
`uVar4 = param_4 & DAT_8c03eae0(0xff00) = 0x0300`):

| `uVar5 = 4` site | Condition | Observed | Excluded because |
|---|---|---|---|
| format switch (joins at `0x8c03eafe`) | `param_4 & 0xff` not in `{0,1,2,3,4}` after the `uVar4` table misses | `texobj+0x0c = 0x08000000` | `0x0300` misses the `DAT_8c03ead0…eade` set (`0500 0600 1300 1400 0700 0800 1500 1600`) → falls to the `param_4 & 0xff` switch; `0x01` takes the `uVar1 == 1` arm, writing `DAT_8c03eaec = 0x08000000`. Observed exactly. The error arm writes nothing here. |
| width / height table | `param_2` or `param_3` not in `{8,16,32,64,128,256,512,1024}` | `texobj+0x1c = 0x4000003f` | width `1024` → `uVar6 = 0x38`; height `1024` → `uVar6 \|= 7` → `0x3f`. A width miss leaves `0x07`, a height miss leaves `0x38` (it `goto`s past the OR). Only both-legal produces `0x3f`. |
| `0x8c03eba8` (square) | `uVar4` outside `{0900,0b00,0d00,0500,0700}` **and** `param_2 != param_3` | `1024 == 1024` | the second conjunct is false regardless of `uVar4`. |

Also consistent: `texobj+0x04 = 0x03010002` is the `else` arm (`| 2`), and
`texobj+0x08 = 1` is `param_1[1] = 1` — both on the normal path.
`FUN_8c03ea1c` returned **0**. **T4 did not fire.**

For completeness against the rest of the taxonomy: T3 and T6 write `1` to
`0x8c1a20a8` (observed `6`); T5 writes `8`; T2 writes `7` and would need one
of the two 256-entry tables full (both at 84). **T1 is the only surviving
trigger**, and the free-list state independently confirms it rather than
merely permitting it.

### Step 10 — the relocation math, cross-checked

The verdict has to be numerically coherent with the port's own VRAM budget,
not just cell-consistent.

| Quantity | Bytes | Source |
|---|---|---|
| DC VRAM arena (patched seed) | 8,388,608 | `0x8c19ecb4` = `0x00800000`; arena walk sums to `0x800000` |
| Naomi arena (unpatched seed) | 16,777,216 | `scripts/reloc_patchset.json` `dat_offset 0x1203c`, `0x01000000` |
| Non-texture reservations at the hang | 1,501,184 | FB pair 1,228,800 + region 262,144 + sub-page 4,096 + KAMUI2-internal 6,144 |
| Game textures resident at the hang | 6,743,072 | 83 texobj-owned blocks (§Step 5) |
| Arena high-water at the hang | 8,244,256 (`0x7dcc20`) | free block base |
| Free | 144,352 | free-list walk |
| **Failing request** | **264,192** | `texobj[84]+0x18`; VQ 1024×1024 |
| **Shortfall (this texture)** | **119,840** | 264,192 − 144,352 |
| Shortfall to place the whole 4-texture chunk | 384,032 | 1,056,768 − (144,352 + 2×264,192) |
| Demand implied at this instant | 8,508,448 (`0x81d420`) | high-water + request = **1.43 % over the 8 MB cap** |

> **Both shortfall figures are FLOORS, not the scene's peak demand.** 119,840 B
> is what the *next instruction* needed. 384,032 B is what the rest of *this
> `TXTR` chunk* needs — and even that is a floor: entry 3 was never attempted
> (`FUN_8c070da8` breaks on the first failure), and **nothing that would have
> run after this chunk ran at all**, because the game parked in
> `FUN_8c0ad720` forever. The true peak VRAM demand of this scene — let alone
> of a played match, which Phase 3 measured as a *higher*-demand context than
> attract — is **unbounded by this evidence**. A fix sized to 384 KB is not
> shown to be sufficient; it is only shown to be necessary. Sizing a fix
> needs a separate measurement (e.g. an instrumented run with a deliberately
> over-large arena, recording the true high-water) — not done here.

On the unpatched Naomi seed the same scene has `16,777,216 − 8,244,256` =
8,532,960 B free — **32× the failing request**, so this failure cannot occur
on the original hardware configuration. The deficit is created by the port's
own 16 MB → 8 MB VRAM-size patch: **category (b), our fit bug**, per
§What this means for the Task 7 verdict.

**Against the Phase 3 dry-run margin.** `docs/kb/00-status.md` records
`dryrun_vram_below_8m` green with "**~680 KB VRAM headroom** at the match
peak (`content_high 0x756120` vs the 8 MB cap = 696,032 B free)". The arena
high-water measured here is `0x7dcc20` — **551,680 B above** the dry run's
peak. The 14-leg Phase 3 campaign therefore never reached this scene's VRAM
demand, and its "680 KB headroom" was not the game's true peak; the real
peak (this instant) *exceeds* the cap by 119,840 B. Two honest notes on that
comparison: the dry run's `content_high` is a **write** high-water (a
texture that fails to allocate is never written, so a failing run would read
*lower*, not higher), and it was taken on the Naomi profile — whether the
dry-run legs ever entered this particular attract segment is **not**
established by anything in this task. What *is* established is that the
gate's margin figure did not bound the peak.

(Suggestive but not cited as evidence: `0x756120` sits 23,296 B below
`0x75bc20`, where this scene's first 1024×1024 texture landed.)

### Verdict

**T1 — VRAM texture-arena exhaustion. Brief verdict 2: OUR fit bug. The
hard gate is NOT satisfied by exoneration; a fix is required before hardware
rounds.**

Applying the brief's decision table with the KB taxonomy:

- delivered == GDI: **yes** (`shimcrc_match` PASS, 89/0, plus a full-body
  byte-identity check on the exact failing asset).
- drive == GDI: **yes** (`gdread_match` PASS, 420 verified / 0 mismatch).
- trigger path: **allocation failure**, category (b) — `FUN_8c03c46e`
  returned 3 with a 144,352-byte largest free block against a 264,192-byte
  request.

That is verdict 2 verbatim: *"delivered == GDI ∧ trigger path is allocation
failure → our fit bug (VRAM arena / heap pressure at the transition). NOT
exoneration. Fix required."* Verdicts 1, 3 and 4 are all excluded: the bytes
are clean on both streams (rules out 3 and 4) and the trigger is category
(b), not (a)/(c)-with-good-bytes (rules out 1).

**Per the Task 7 hard boundary, no fix is designed or implemented here.** The
fix scope goes to the user with this evidence. For whoever authors it, the
forensics constrain it sharply:

- **Not fragmentation.** Zero gaps across the whole `0x800000`; the free
  space is one contiguous tail block. Compaction recovers nothing.
- **Not a leak.** The live counter fell `0x66 → 0x54` (102 → 84) across the
  preceding scene transition, so the previous scene's surfaces *were*
  released and coalesced.
- **Not the loader or the bytes.** Both CRC streams clean, and the failing
  asset is byte-identical to the cart image over its full `0x40820` B.
- **Not the size computation.** 264,192 B is arithmetically exact for a
  1024×1024 VQ texture.
- It is a **budget deficit of at least 119,840 B (117 KB) at this instant**,
  at least 384,032 B if the whole 4-texture chunk must fit — against a hard
  8 MB cap that the DC cannot raise. **Both numbers are floors** (§Step 10):
  neither bounds the scene's peak demand, so neither is a fix-sizing target.

### Limits of this verdict

- **The deficit figures are floors, not the peak.** Everything downstream of
  the failure is invisible to this evidence: list entry 3 was never
  attempted, and the game parked in its error loop instead of continuing the
  scene. 119,840 B is what the next instruction needed; 384,032 B is what
  this one chunk needs. A fix sized at 384 KB could still fail later in the
  same scene, and a played match is a higher-demand context than the attract
  path this was captured on. Sizing any fix requires a fresh measurement of
  the true high-water, which this task did not take.
- **One savestate.** Three occurrences are on record (Phase 4 `play1` with a
  screenshot, Task 5 `instrument-ctl`, Task 6 `soak-1`); only `soak-1`
  carries RAM state. The `instrument-ctl` leg is byte-identical to `soak-1`
  up to the marker, so those two are the same event; `play1` was an
  operator-played match and is matched only by log signature
  (`MDODMA` dead, the same frozen `C2D src=` pair) — **not** proven to be the
  same trigger. A played match could still hit T4 or another trigger.
- **Unattended, no screenshot.** This leg set no `FLYCAST_SHOT`; the on-screen
  text is inferred from `0x8c188b8a` on the stack and from `play1`'s
  screenshot, not photographed here.
- **Sampling latency.** `cartlog_texerr_tick()` samples every 64th
  `STARTRENDER` write, so the marker's *log position* can trail the actual
  failure by up to ~64 render submissions (~1.1 s at this leg's 57 Hz). The
  savestate's *content* is unaffected by that: the abandoned `texobj[84]`,
  the cleared `surf[84]` and the intact stack frame all show the failing call
  and nothing after it.
- **The error loop ran before the save.** `FUN_8c0ad720` re-presents every
  frame between the failure and `TEXERRSAVE` (15 cartlog lines later). It
  prints with already-resident font surfaces and the arena state is
  self-consistent with the in-flight descriptor, but a strict reading is
  "the arena as it stood a frame or two after the failure", not "at the
  instruction".
- **Not re-derived here:** whether the KAMUI2 arena would be laid out
  differently by a different bank/placement strategy, and whether the Phase 3
  dry-run legs ever entered this attract segment (§Step 10).
- **No fix, no hardware claim.** Nothing in this task ran on real silicon;
  the verdict is about the port's VRAM budget, which is profile-independent
  (the arena is the game's own bookkeeping, not the emulator's).

## High-water measurement (fix-scoping, user-approved 2026-08-23)

**Question:** the Task 7 verdict left fix sizing open — both deficit figures
(119,840 B / 384,032 B) are floors, and "the true peak VRAM demand … is
unbounded by this evidence" (§Step 10). What is the game's actual peak
texture-arena demand across attract *and* played matches, and therefore how
big is the deficit a fix must close?

### Method — measure on the Naomi profile, translate to the DC budget

Demand was measured on the **Naomi profile with the original ROM** (the
unpatched 16 MB seed), not on a big-arena DC disc variant, for two reasons:

- **Fidelity:** texture demand is a property of the game content and code,
  which the port shares byte-for-byte outside the patched seeds; the 16 MB
  arena gives the allocator 32× the failing request (§Step 10), so no load
  ever fails and the walk sees the true demand, not a truncated one.
- **Playability:** Flycast's DC profile maps 8 MB of VRAM
  (`core/hw/mem/addrspace.cpp:626`, both lines captured in this leg's own
  stdout: `VRAM64(8 MB)` on DC init, `VRAM64(16 MB)` after the Naomi
  platform switch — `captures/phase5/arenahw-op1.stdout.log`). A DC-profile
  arena seeded past 8 MB would wrap every above-8M texture write at the
  8 MB mask onto low VRAM — stomping the region array, framebuffer and
  resident textures — so the screen degrades exactly when the measurement
  gets interesting, and the operator's match leg becomes unplayable. The
  Naomi profile renders everything correctly.

**Instrument — `ARENAHW` walker** (fork canonical `10de83124`, cherry-pick
`b5a275a11` into the launched tree, rebuilt; `INSTRUMENTATION.md` row
added). `cartlog_arena_tick()` (`core/hw/naomi/naomi.cpp`) walks the KAMUI2
arena block lists — config block P1 `0x8c170eb8`, both banks' alloc + free
lists, node stride `0x18`, the exact layout the Task 7 savestate verified
(§Steps 4–5) — on every `STARTRENDER` write (same site and dynarec-safety
argument as `cartlog_texerr_tick`), and prints only when a running max
(total allocated bytes, or texture-class bytes) increases. Texture-class =
blocks with flag bit `0x02` clear: at the hang, every non-texture
reservation carried `0x02` (FB pair `0x0013`, region/TA `0x0043`) and every
texture-class block did not (`0x0011` game textures, `0x0015` sub-page,
KAMUI2-internal `0x0011`) — §Step 5's flag table. That split is what makes
the number transfer across profiles: **required DC arena = peak tex +
1,490,944 B** (the DC profile's own `flags&2` reservations, measured live
at the hang: FB pair 1,228,800 + region 262,144).

Guards: the walker no-ops until config`+4` reads `0x800000` or
`0x1000000`; a non-RAM link stops that list; node count capped at 512
(pool capacity is `0x105`).

### Legs

| Leg | Profile | Duration | Lines | ARENAHW | TEXERR |
|---|---|---|---|---|---|
| `phase5/arenahw-smoke` | Naomi, unattended | 150 s | 233,590 | 7 | baseline only |
| `phase5/arenahw-op1` | Naomi, **operator** | ~2 h 15 m (23:47–02:02) | 13,548,793 (507 MB) | 11 | `code=0` throughout |

**Smoke validation:** on every line `alloc + free = total = 0x1000000`
exactly, one free node, zero fragmentation — the same closed arithmetic the
Task 7 walk found; `alloc − tex = 0x700000` constant across all samples
(the Naomi-mode reservations), confirming the `flags&2` split is stable.

**Operator coverage (operator-attested, 2026-08-24):** ~11 min attract
pre-roll untouched; 2P mode through **all stages** (each at least once,
characters varied); Score Mode to a stage-2 death; 1P beginner+novice
(Mika) stages 1–8 including the boss's two observed forms (big robot, then
a bird/insect second form — not beaten; a third form and the ending remain
unseen); post-play attract until the kill. The `TEXERR` sampler stayed
`code=0` for the entire leg — **no texture-load error anywhere on the
16 MB arena**, as the Task 7 arithmetic predicted.

### Result

Peak sample (`captures/phase5/arenahw-op1.log:2290180`, set in the early 2P
window; ~11.2 M subsequent lines — the rest of the 2P sweep, Score Mode,
the whole 1P run and the boss — never exceeded it):

```
ARENAHW total=01000000 alloc=00dd73e0 tex=006d73e0 nblk=55 free=00228c20 maxfree=00228c20 nfree=1
```

| Quantity | Bytes | Source |
|---|---|---|
| **Peak texture-class demand** | **7,173,088** (`0x6d73e0`) | ARENAHW max, whole leg |
| DC `flags&2` reservations | 1,490,944 (`0x16c000`) | Task 7 §Step 5 (FB pair + region) |
| **Required DC arena (measured)** | **8,664,032** (`0x843260`) | sum |
| 8 MB cap | 8,388,608 (`0x800000`) | patched seed |
| **Deficit (measured coverage)** | **275,424** (`0x433e0`) | vs the cap |
| DC-evidence floor (Task 7) | 8,772,640 (`0x85e020`) → deficit **384,032** | hang alloc 8,244,256 + the chunk's 2 unplaced textures 528,384 |

Attract cross-check: ARENAHW #8 (`arenahw-op1.log:388130`, ~4.2 min in,
attract) reads `tex=0x688660` = 6,850,144 — within 1.5 % of the DC hang
instant's texture-class total 6,753,312 (§Step 5), i.e. the Naomi attract
reaches the same demand class at the same point in its loop.

**Reconciliation — the DC floor stays binding.** The measured Naomi peak
(8,664,032 DC-equivalent) sits 108,608 B *below* the Task 7 floor
(8,772,640). So this leg never held the exact resident set the DC attract
held at its failing instant — the attract demo rotation is not guaranteed
identical across profiles (plausibly EEPROM/play-history-driven; **a
reading, not a derived fact**), and the walker samples at frame boundaries
(an alloc-then-free inside one frame is invisible). Neither gap changes the
conclusion; it means the honest sizing number is the **larger** of the two:

> **The fix must recover at least 384,032 B (the DC-evidence floor);
> measured full-game coverage puts the true requirement within ~110 KB of
> that floor. Recommended engineering target: ≥ 512 KB (0x80000) recovered,
> covering both numbers with margin.**

### Limits

- Unseen contexts: a possible third boss form, the 1P ending/credits, and
  Score Mode past stage 2. The walker now rides along free in every future
  instrumented leg (including fix-verification soaks), so coverage keeps
  accruing; a completed 1P run would close the ending gap.
- Frame-boundary sampling (above): a strictly intra-frame transient peak
  would be missed. No mechanism for one is known in this allocator (scene
  textures persist across frames), but it is unproven.
- The 1,490,944 B DC reservation figure is the hang-instant value; the FB
  pair and region block are allocated once at init and were stable across
  every observation, but no leg has watched them across a video-mode change.

## Fix scoping (2026-08-24, user-directed)

User direction on the measurement verdict: scope **option 1** (shrink the
framebuffer reservation) first, but "if there will be flickering, I would
like to continue with other options"; if option 1 fails, identify the
offender textures ("grab and save the textures … which stage it is").

### Option 1 — FB reservation: REJECTED under the no-flicker constraint

The verdict is arithmetic, not archaeology. The scan-out reservation at the
hang is one arena block of **1,228,800 B = exactly 2 × (640 × 480 × 2)** —
a double-buffered 16-bit 640×480 pair (§Step 5). Every way to shrink it
gives up one of those three factors:

| Shrink | Saves | Visual cost |
|---|---|---|
| 2 buffers → 1 | 614,400 | rendering into the displayed buffer — tearing/flicker. **Vetoed.** |
| 480 → 240 lines | 614,400 | half vertical resolution (240p), or field-rendered interlace — whose *characteristic artifact is flicker* on static art. **Vetoed / quality loss.** |
| 640 → 512 columns | 245,760 | aspect distortion, and alone under the 384,032 B floor anyway |
| 16 bpp → less | — | no smaller DC scan-out format exists (555/565 are both 16-bit) |

The other `flags&2` reservation (region/TA block, 262,144 B) is below the
floor even at zero. **Option 1 cannot recover the deficit without a visual
cost the user has excluded.** Supporting archaeology, recorded for reuse:
`FUN_8c038aa0` (called only from `FUN_8c02e300`, `jsr 0x8c02e352`) is the
**arena initializer** — `PTR_DAT_8c038b44` = the config block `0x8c170eb8`,
and it builds the initial free list with an optional top-of-VRAM reserve
from config`+0x4c` (zero in our runs; the 16 MB/8 MB duality is the
`DAT_8c038b48`/`DAT_8c038b50` compare, with any non-16 MB size falling to
the hardcoded 8 MB arm — an intermediate seed would waste space above
8 MB). The scan-out FB *size* is computed in `FUN_8c031b60`
(bytes-per-line × (lines+1 & ~1), from the game's config struct passed
down `FUN_8c06ed98` → `FUN_8c03d9d8` → `FUN_8c02e300`). `FUN_8c042b44`
(callers `0x8c08636c`) is the creator of the **6,144 B KAMUI2-internal
block** — its descriptor is the global `0x8c1a2180` (whose `+0x1c` is the
`0x8c1a219c` owner slot §Step 4 found), and its content is the system
debug font (`"0123456789ABCDEF"` glyph bitmap at `0x8c171008`).

### The offenders identified — STAGE08.PAK, a selectable arena

> **Correction (2026-08-24).** An earlier revision titled this section
> "the boss stage" — wrong, caught by the operator. STAGE08.PAK is a
> regular *selectable* arena (the operator fought on it in 2P, and the
> attract demo plays on it); the 1P campaign's 8th-stage boss fight
> loads `STAGE10.PAK` + `P11.PAK` (see load-timeline attribution below).
> Campaign position and `STAGEnn` file number do not map 1:1.

The flat image is an **ISO9660 filesystem**: PVD at `.dat 0x808000`
(`\x01CD001`), root LBA 45,020, mapping `dat_off = (LBA − 40904) × 2048`.
Walking it yields 1,001 files; the four failing textures all fall inside
**`/STAGE08.PAK`** (dat `0xb496800`, 3,925,728 B) at `+0x21f7a0`,
`+0x25ffc0`, `+0x2a07e0` (the failing one), `+0x2e1000` — a 4-entry `TXTR`
chunk (tag at `+0x21f788`: size `0x102094`, count 4, offset table
`{0x14, 0x40834, 0x81054, 0xc1874}` — **explicit per-texture offsets**,
which is what makes an in-place shrink structurally safe). Decoded to PNG
(`scripts/decode_pvr_vq.py`, pure-stdlib VQ decoder;
`captures/phase5/textures/stage08-*.png`, gitignored — ROM-derived):
crisp mechanical hull/station panel atlases — girders, X-braced trusses,
vents, hatch and window arrays, red accent squares — the arena's
battleship-architecture set. Three are RGB565 VQ, the fourth ARGB4444 VQ
(alpha decals).

> **Decoder bug found and fixed (2026-08-24), control-tested.** The
> first decode run read the VQ codebook 16 B late (a 32-byte header read
> against the 16-byte `PVRT` header shifted the palette by two entries
> and the index stream by 16 B), producing speckled "mixed-pixel" images
> the operator flagged. Control test per the working rules: decoding
> `/FONT.PAK`'s 256×256 ARGB4444 VQ sheet (dat `0x345e05c`) with the
> fixed decoder yields a pristine A–Z/0–9 glyph grid — a known-content
> reference that would scramble under any morton/codebook-order error.
> This also confirms the documented conventions (y-in-LSB morton,
> codebook texel order (0,0),(0,1),(1,0),(1,1)) empirically; the earlier
> A/B against the stage art could not discriminate. Texture *sizes* and
> the arena arithmetic never depended on the decode — only the pictures
> did.

**Load-timeline attribution** (cartlog `CARTDMA src=` mapped through the
ISO table, `captures/phase5/arenahw-op1.log`): the attract rotation is
stage-4 title demo → stage-1 tutorial → **stage-8 demo** → stage-10
ranking card, cycling through `OP_P12/34/56/78` character-intro pairs. The
ARENAHW running max was set, after boot, **only ever by STAGE08 scenes**:
the attract stage-8 demo (`load /STAGE08.PAK` at line 387,940 →
ARENAHW #8 at 388,130 — the same scene class that kills the DC build),
then the operator's two 2P matches on stage 8 (lines 1,094,833 and
2,023,598 → maxima #9/#10 and the all-time peak #11). The 1P boss fight
is `P11.PAK` + `STAGE10.PAK` (line 6,920,700; d98=0x30) — small, never
near the peak.

**Per-PAK texture census** (`PVRT` header scan, VRAM size by the KAMUI2
formula — VQ = 2048 + w·h/4):

| PAK | Textures | VRAM if all resident | Note |
|---|---|---|---|
| STAGE08 | 40 | **3,280,896** | the four 1024×1024 VQs are 1,056,768 of it |
| STAGE09 | 47 | 2,807,808 | biggest *file* (6.6 MB) but max texture 512×512 |
| STAGE07 | 50 | 2,310,144 | played, never set a max |
| STAGE06 | 43 | 1,740,800 | played, never set a max |
| others | — | ≤ 1,376,256 | STAGE10's two 512×512 non-VQ (dt01) are its bulk |

STAGE08 is the heaviest stage **because of** the four big VQs. Shrinking
them 1024×1024 → 512×512 (264,192 → 67,584 each) saves **786,432 B**:
the DC-floor scene drops 8,772,640 → 7,986,208 (headroom 402,400) and the
measured peak drops 8,664,032 → 7,877,600 (headroom 511,008) — both
comfortably under the 8 MB cap, from a change to four background textures
in one PAK. Mechanically: same GBIX index, PVRT header rewritten
512×512, re-encoded VQ payload, rest of the record left as dead padding —
the chunk's explicit offset table and every other byte of the PAK
unchanged; KAMUI2 reads dims from the PVRT header (§Step 9) and PVR UVs
are normalized, so the art simply renders softer. The patch bytes are
ROM-derived (never committed; regenerated by script from `senkosp.dat` at
GDI build time).

### Fix decision (2026-08-24) — option 2 approved, all four textures

Operator approved the in-place 1024×1024 → 512×512 VQ shrink of all four
STAGE08.PAK offenders (four, not fewer: two clears the 384,032 B floor by
only 9,184 B; three leaves 205,792 B, under the ≥512 KB target; four
leaves 402,400 B — and uniform softening beats mixed-sharpness panels in
one atlas family). Format analysis confirmed shrinking is the only size
lever: VQ has no quality/size dial (codebook fixed at 2048 B, index
exactly w·h/4 — `core/rend/TexCache.cpp` VQ path in the Flycast source,
`size = width * height / 4`, codebook `VQ_CODEBOOK_SIZE` = 2048), and
every other PVR format is larger per texel (8bpp CLUT = 4× VQ's index
bytes, 16bpp = 8×). Non-square VQ (e.g. 1024×512, saves 131,072 each) is
emulator-supported for non-mipmapped textures but the game ships **zero**
non-square VQs (scan of all PAKs: 1,167 square, 0 non-square), so its
loader is unproven on them — kept as fallback only if the 512×512 A/B
fails.

**Amendment (2026-08-25) — operator re-ruling: shrink three, 0b777810
ships full-size.** After the art-quality campaign on 0b777810 (masks,
sharpening rounds, ARGB1555/565/CLUT format ladder — §Final freeze
art-override), the operator ruled that this texture — the most
on-screen-visible of the four and the only one with semi-transparent
elements — reverts to the **original 1024×1024 ARGB4444 record,
untouched** (best possible quality: zero re-encode loss), while the other
three stay 512×512. Arithmetic on the measured killer scene:
8,772,640 − 3 × 196,608 = **8,182,816 B predicted peak, 205,792 B
headroom** — under the earlier ≥512 KB target, accepted deliberately
because (a) the added 196,608 B lands entirely on the stage-8 scene
class, the best-measured scene in the project (fix prediction previously
closed to the byte), and (b) unmeasured-scene risk (STAGE09/P09/P10,
ending) is unchanged: those scenes do not reference the STAGE08 atlas.
This supersedes the uniform-softening argument above (operator accepts
mixed sharpness given 0b777810's visibility) and moots the ARGB1555
re-encode of 0b777810 for shipping (the format findings stand as
knowledge). Verification bar for the next stage-8 leg: ARENAHW peak
8,182,816 / free 205,792 byte-exact, TEXERR clean. "Shrink only two" was
re-examined and vetoed: 9,184 B headroom is smaller than one 64×64
16-bit texture, against unmeasured character-pair variance, with the T1
hard hang as the failure mode.

**Amendment 2 (2026-08-25) — operator re-ruling after the Ernula-mirror
stress leg: shrink two, ship config.** The character-PAK census
(game.md §Character ↔ PAK mapping) flagged Ernula (P07, 309,408 B) as
the heaviest texture set, and an upper-bound argument said an Ernula
mirror match could exceed shrink-2's headroom. Measured instead
(`captures/ernula-s2.log`, build track04 `0bd49391`, shrink-2 config:
0b6b5fb0 + 0b736ff0 re-encoded 512² from the operator's tuned edits,
0b6f67d0 + 0b777810 original 1024²): Ernula vs Ernula (P07A + P07E
loaded, then STAGE08.PAK) peaked at ARENAHW alloc 8,180,736 / free
207,872 — set at match load, never exceeded across the remaining ~355k
log lines of the fight (reconfirming load-time-only texture
allocation); TEXERR 9/9 clean + the known boot artifact.

> **Correction (2026-08-25, same evening) — the attract-demo check leg
> (`captures/attract-s2.log`) overturned two claims in this amendment
> as written.** (1) Leg B's 8,372,576 peak was NOT the attract demo:
> load attribution shows `STGSEL.PAK` then P06E + P07E + STAGE08 — it
> was the operator's own **Sakurako vs Ernula 2P match**. (2) The
> attract rotation is **randomized**, not fixed: each cycle plays a
> fixed Changpo-vs-Mika demo plus a second demo with random pair and
> random stage (observed across 5 cycles: P06B+P07B on STAGE08,
> P06D+P05E and P01F+P02C on STAGE03, P04F+P04E mirror on STAGE04,
> P04C+P05B on STAGE01 …). The attract-s2 leg's stage-8 demo
> (Sakurako P06B + Ernula P07B) peaked at **alloc 8,379,424 / free
> 9,184** — worse than the stated bar — and survived, TEXERR clean.
>
> **Byte-exact demand model (DC, shrink-2 build).** Three direct
> measurements fit `peak = 7,854,880 (stage-8 scene base, identical
> for attract demo and 2P match) + Σ census(character variant)`,
> census = Σ(PVRT datalen−8) per PAK: leg-B match 7,854,880 + 208,288
> (P06E) + 309,408 (P07E) = 8,372,576 exact; attract demo 7,854,880 +
> 215,136 (P06B) + 309,408 (P07B) = 8,379,424 exact; Ernula mirror
> 8,180,736 → P07A∪P07E resident 325,856 ≈ one set + 16,448 (variant
> PAKs share nearly all textures, so mirrors are cheap — the census
> table lives in game.md). Model residual ≤ ~16 KB. Predicted worst
> distinct pair **Ernula (309,408) + Lili (226,688) on stage 8 =
> 8,390,976 — 2,368 B OVER the 8,388,608 arena**, within model
> residual: shrink-2's fate on the worst pair is genuinely
> undecidable by model and needs a direct measurement (Ernula vs Lili,
> stage 8, this build). Second-worst (P01C–F + P07 = 8,381,504, free
> 7,104) fits. The attract rolls random pairs, so a worst-pair stage-8
> demo occurs unattended sooner or later — if it overflows, that is a
> T1 hard hang in attract mode. The shrink-2 ship ruling is therefore
> **suspended pending the Ernula-vs-Lili measurement**; shrink-3's
> worst-pair prediction under the same model is 8,194,368 / free
> 194,240. The older derived "killer demand 8,772,640" and the
> shrink-3 bar 8,182,816 derived from it were pair-naive and are
> superseded by this model; the FB-derivation discrepancy (~124 KB) is
> noted, unexplained, and moot — direct DC measurement outranks it.

**Binding verification requirements (operator-set):**

1. **A/B visual gate is mandatory.** Before hardware: paired emulator
   screenshots of the same STAGE08 scene, patched vs unpatched — the
   operator must be able to clearly see the difference (or its absence)
   and accept it. **Operator amendment (2026-08-24): screenshots are not
   sufficient — the operator plays both builds back to back** (A/B/A
   allowed). The unpatched side is the **Naomi original** (true reference
   art; the unpatched DC build cannot display the scene — loading stage 8
   is exactly what hangs it, so it can't serve as the play reference). Preview so far: sips 1024→512→1024 round trip
   (`captures/phase5/textures/stage08-0b736fe0-shrunk-preview.png` vs
   the unsuffixed original — same 1024² resolution on purpose: downscaled
   then stretched back, simulating what bilinear sampling of the 512²
   texture does over the same screen area).
2. **The fix-verification operator batch must include one
   savestate-assisted 1P completion leg** (easiest difficulty via test
   menu; savestate before the level-8 boss; retry the bird form until
   past it): closes the last coverage holes — STAGE09/P09/P10, a
   possible third boss form, the ending — with ARENAHW measuring for
   free. Savestates are fine for measurement/coverage legs (never
   committed — gitignored, ROM-derived); the *deterministic attract*
   verification evidence must still come from clean boots, since a
   savestate carries pre-fix VRAM/arena state.
3. Standard evidence: deterministic DC attract through the stage-8 demo
   scene clean, ≥6 operator sessions, ≥30-min instrumented soak, all
   checkers PASS, ARENAHW riding along in every leg.

### Fix implementation + first evidence (2026-08-24)

**Encoder** — `scripts/shrink_vq.py` (needs `tools/pyenv`, see tooling.md):
per texture, decode 1024² through the control-tested
`decode_pvr_vq.decode()`, 2×2 box downscale (gamma-naive on purpose — the
same space the PVR filters in; linearize is the knob if the A/B gate
finds it dark), weighted k-means++ (256 codes, 30 Lloyd iters, fixed
seed → byte-reproducible), centroids quantized to the target pixel
format *before* final assignment, indices packed in y-LSB morton.
**Every produced record is decoded back through the proven decoder and
gated on PSNR vs the downscaled reference** (floor 26 dB). Measured:
38.2 / 37.1 / 39.3 dB (RGB565) and 33.8 dB (ARGB4444). Runtime ~10 s
for all four.

**Patch path** — blobs in `build/texpatch/` (67,600 B replacement PVRT
records + `manifest.json`; ROM-derived → gitignored, regenerated from
`senkosp.dat`). `make_gdi.py` splices them into the in-memory cart image
before writing track04, guarded by md5 of both the source record and the
blob; `--no-texpatch` produces the unpatched reference build for the A/B
gate. `senkosp.dat` on disk is never modified.

**Smoke leg `phase5/fix-smoke-1`** (patched DC attract, 555 s,
481,900 lines): **the killer scene completes, and the arithmetic closes
to the byte.** ARENAHW peak `alloc=0079dc20` = 7,986,208 B = the Task 7
DC floor 8,772,640 − the 786,432 saved, with `free=000623e0` =
402,400 B — exactly the predicted headroom. The peak fires at line
319,286; the unpatched `soak-1` hung at line 319,549 of the same leg
shape — same scene, now surviving. `TEXERR code=00000000` on every
post-boot sample (line-128 boot-garbage sample as in every leg), and the
`d98` scene-counter values repeat across the log (0x17/0x19/0x22 seen
twice) — the attract rotation finished a full cycle past the stage-8
demo and started a second one. First DC build ever to survive the scene.
**Soak leg `phase5/fix-soak-1`** (patched DC attract, 31 min,
2,527,726 lines): **clean.** ~6–7 full attract rotations (`d98` 0x17
seen 7×); all 46 post-boot TEXERR samples `code=0`; the ARENAHW all-time
max never moved past the first rotation's stage-8 demo (`alloc=0079dc20`
at line 319,286 — byte-deterministic with `fix-smoke-1`, same line
number from clean boot). Checkers: `shimcrc_match` PASS (vacuous — 0
records, SHIM_CRC diag flag off by policy on release-shaped builds),
`gdread_match` **PASS — 1,742 reads verified against the patched
track04, 0 mismatches** (4 lowfad, same donor-region reads as soak-1),
`coverage_nonzero` FAIL-by-config (its shim half presumes a diagnostic
leg; ruling in the ledger: it applies to SHIM_CRC-enabled legs only —
see the texpatch caveat now in `check_stream_crc.py`'s docstring).
This closes the ≥30-min-soak half of the task-18 standard.

Remaining for the gate: A/B visual + play-both-builds (task 17), ≥6
operator sessions + savestate-assisted 1P completion (task 18).

### A/B gate result (2026-08-24) — PASS, plus a v2 polish pass

Operator played both builds back to back (`phase5/ab-naomi` 17:28–17:44,
`phase5/ab-dc-patched` 17:46–17:51; curated grabs in
`captures/phase5/ab-keep-*.png`, gitignored). **Verdict: stills show a
clear but "not very critical" difference; in motion the builds are
"indistinguishable at all"** (the arena structure circles constantly).
Whole-texture compression accepted. Residual complaint: several
high-contrast elements (lit window strips, red truss markings) look poor
in stills.

- **Stage-select correction:** the patched arena is **slot 3** of the
  stage-select grid (left→right, top→bottom), not slot 8 — `STAGEnn`
  file numbers match neither campaign-level number nor select position.
  (The operator initially played select-slot 8 — a different arena — and
  pruned those grabs.)
- Leg evidence: DC leg TEXERR 12/12 clean post-boot; ARENAHW peak during
  the operator's real 2P match on the patched arena **7,604,192 B**
  (headroom 783,392). Naomi leg tex peak 7,097,344 — consistent with the
  op1 measurement.
- **v2 encoder polish** — the answer to "can the contrast elements be
  fixed separately": yes, encoder-side at zero size cost. Knobs
  (shrink_vq.py): `UNSHARP=0.5` post-downscale (recovers the 1–2 px
  contrast the box average smears), `EDGE_W=3.0` edge-weighted codebook
  training (variance-weighted k-means — flat repeats stop hogging
  codes), and for the ARGB4444 decal texture `ALPHA_W=2.0` +
  visible-RGB dilation into fully-transparent texels (bilinear fringe
  control; stops wasting codebook fidelity on invisible bytes). v2
  PSNRs 36.2/35.5/37.3/31.8 dB are measured against the *sharpened*
  reference and are not comparable to v1's 38.2/37.1/39.3/33.8 against
  the plain one. Side-by-sides for the operator:
  `captures/phase5/textures/compare-v1v2-*.png` (left v1, right v2).
- v2 bytes → GDI rebuilt; deterministic smoke re-run **`fix-smoke-2`:
  CLEAN** — TEXERR 14/14 `code=0` post-boot, ARENAHW peak
  `alloc=0079dc20` at line 319,286: byte-identical position and value to
  `fix-smoke-1` (expected — v2 only redistributes codebook quality, the
  record sizes are unchanged). Verification batch (task 18) runs on the
  bytes the operator freezes (v2, or v1 by re-encoding with the v1
  knobs `UNSHARP=0 EDGE_W=0 ALPHA_W=1`).
- **v2a regression, operator-caught:** small red indicator lights
  missing in the ARGB4444 texture's bottom-left corner. Root cause:
  `ALPHA_W=2.0` skewed both the k-means metric and the edge weight
  toward alpha, so small *opaque* color features (alpha-flat blocks)
  lost their codes to gray. **v2b fix:** `ALPHA_W=1.0` (the RGB
  dilation is kept — it is the real pf2 win) and the edge weight is
  measured in unscaled space. Corner proof
  `captures/phase5/textures/corner-v1-v2b.png` — reds restored; the
  three RGB565 blobs are byte-identical to v2a. Lesson recorded: a
  channel-emphasis scale must never feed the block-importance measure.

### Final freeze (2026-08-24) — v1, operator-decided

The operator played a third leg on v2b (`phase5/ab-dc-v2b`, TEXERR
19/19 clean, ARENAHW peak 7,967,712 during the session) and compared
all three screenshot sets. **Verdict: v2/v2b rejected** — no real
improvement on the elements that mattered, *more* noise overall, and
stray green dots (probable mechanism: per-channel unsharp shifts
chroma, RGB565's green channel has one more bit than red/blue so
sharpened near-grays round greenish, and the edge-weighted codebook
then spends codes preserving that noise). **v1 is the frozen version.**

Freeze evidence: encoder knobs zeroed (`UNSHARP=0 EDGE_W=0 ALPHA_W=1
DILATE=0`); the knobs-off encoder output verified **byte-identical** to
the archived commit-`b32114e` encoder (control run of the archived
script); rebuilt `track04.iso` md5 `382b161d83fc205ca45eed49d23b939a` —
the exact build `fix-smoke-1` and the 31-min `fix-soak-1` validated, so
that evidence covers the frozen build verbatim, no re-runs needed.

**Art-override pipeline** (operator asked for an editable export/import
path — it exists now): export any texture to PNG with
`scripts/decode_pvr_vq.py`; produce a 512×512 8-bit RGB/RGBA PNG by
hand or with an image AI; drop it as
`captures/phase5/textures/edit/<pvrt-off>.png` (e.g. `0b777810.png` —
that one needs RGBA for the decals); rerun `shrink_vq.py` +
`make_gdi.py`. The encoder VQ-encodes the override as-is (256-code VQ
still applies, PSNR-gated, `source:` recorded in the manifest, preview
regenerated). Everything stays gitignored. **Importance masks
(2026-08-24):** an optional `edit/<pvrt-off>-mask.png` (512×512,
white = important) reweights codebook training toward the marked
regions (`MASK_W`, default 4.0 → white blocks count 5×); composes with
an edit PNG or the plain downscale, and cannot introduce noise (pixels
untouched, only code allocation shifts). Control-verified: no mask ⇒
byte-identical blobs; synthetic corner mask on `0b777810` moved the
masked region 28.9→30.6 dB for −0.3 dB globally. Contour-preservation ideas
if ever revisited encoder-side: luma-only mild unsharp (avoids chroma
noise), sqrt-count weighting (frees codes from flat repeats without
sharpening). Any post-verification art change re-validates cheaply: the
deterministic smoke + unattended soak, both operator-free.

**Alternative VQ encoders assessed (2026-08-24)** — operator asked
whether texconv / KOS vqenc / Sega's official tool could beat
`shrink_vq.py`. Source-level check of the two open ones:

- **KOS `vqenc`** (KallistiOS `utils/vqenc/vqenc.c`): LBG — starts from
  one code, `split()` doubles the book by perturbing high-error entries,
  Lloyd-style `place()`/`clean_codebook()` refinement, 8 rounds (3× in
  `-hq` mode). Plain Euclidean ARGB distance, no weighting, no dither.
- **texconv** (tvspelsfreak/texconv `vqtools.h`): same LBG splitting
  (`splitCode()` perturbs by 0.01 toward the max-distance vector), three
  `place()` refinement passes, RLE-deduped count weighting,
  `findClosest()` Euclidean assignment. No dither, no perceptual metric.
- **Sega Katana tool**: copyrighted SDK, no legitimate source access —
  unverifiable, and it optimizes the same MSE objective regardless.

All three solve the identical problem — 256 codes × 2×2 texels ×
16-bit — with the same algorithm family (LBG/Lloyd) and the same
Euclidean objective as our weighted k-means. `shrink_vq.py` runs *more*
refinement (k-means++ init + ≤30 Lloyd iters vs 8 LBG rounds) and has
one edge neither tool has: final assignment against the
*quantized-as-stored* codebook (`finish()`, "assign against what will
actually be stored"), where both tools assign against float centroids
and quantize afterward. **Conclusion: switching tools cannot help; the
ceiling is the format, not the encoder.** The only thing a tool could
add is error-diffusion dithering — rejected here, it manufactures
exactly the pixel noise the v2 verdict threw out. The quality levers
remain input-side (bolder source edits than the ~2-4/255 VQ noise
floor) and allocation policy (the recorded knobs).

### Limits / residual risk

- **`STAGE09.PAK` never loaded in the entire 2¼ h leg** (neither did
  `P09`/`P10.PAK`) — unreached content, possibly a true-final-boss or
  ending sequence. Census puts its all-resident worst case ≈
  8,190,944 B with stage-8-like overhead — under the cap by ~198 KB, but
  that is a heuristic (all-resident assumption), not a measurement. Any
  future leg that reaches it will be measured for free by the walker.
  **Content identified (2026-08-24):** decoded samples
  (`captures/phase5/textures/stage09-*.png`, gitignored) are
  **Earth-from-orbit backdrops** — planet horizon against space, ocean
  and cloud surface tiles — consistent with a finale/ending setting.
  Its largest texture is 512×512 (34 of them), so if it ever measures
  over the cap the shrink lever is many 512→256 steps, weaker per
  texture than STAGE08's 1024→512.
- The stage-8 2P peak and the attract-demo floor bound every scene
  *observed*; the ending/credits and a possible third boss form remain
  unobserved (§High-water measurement, Limits).
- The census skips ~40 textures with unrecognized `PVRT` datatypes
  (marked `unk`) — small formats in the observed PAKs; their omission
  biases the census low by small amounts.

## HUD kit — operator field guide (Task 8)

**For:** the operator at the TV during Task 10 hardware rounds. No source
access needed to use this table — just eyes on the screen (or a photo of
it). "HUD" below always means the shim's on-screen breadcrumb system
(`shim_mark`/`shim_hex`/`hex_paint`, `shims/src/util.c`), shipped **ON by
default** (`SHIM_HUD 1`, `shims/include/shim_iface.h:81`).

### How the HUD shows up

The shim paints small 16×8 px colored blocks ("marks") into the *live*
scanout framebuffer and force-unblanks the display (clears the DC's
VO_CONTROL blank bit) whenever it paints one — so even a screen the game
itself never turns on will show something (`shims/src/util.c:20-33`
comment block). Two kinds of marks appear on a healthy run:

- **One-shot milestones** — paint once, the first time some boot step is
  reached (`HUD_ONCE` macro, `shims/src/main.c:507-508`), then never
  again. These are only visible in the brief window **before** the game
  starts drawing its own full-screen graphics every frame — once real
  rendering starts, the GPU's own frame overwrites that memory and the
  marks vanish for good. Confirmed by direct capture: `docs/kb/img/phase5-hud-heartbeat.png`
  shows several boot-time marks (including this task's new slot 24) still
  visible over the mid-boot NAOMI splash; by the attract/title screen a few
  seconds later (`docs/kb/img/phase5-hud-smoke-attract.png`) every mark is
  gone, painted over by the game's own credits screen — **this is normal**,
  not a fault.
- **Repeating/blinking marks** — repainted continuously (every N events),
  so they keep winning the redraw race against the game as long as the
  activity they track keeps happening. These are the ones worth watching
  *during play*, not just at boot.

### Slot map

Row 1 is slots 0-15 at the very top of the screen (y=0-7, x = slot×24 px).
Row 2 is slots 16+, 4 px below row 1 (y=12-19, x = (slot−16)×24 px) —
`shims/src/util.c:42-45`. Every slot below is cited to its paint site.

| Slot | Row | Color(s) | Meaning | Kind |
|---|---|---|---|---|
| 0 | 1 | white | First EEPROM/config contact (`shim_ee_read`) | one-shot |
| 1 | 1 | green | First MIE (maple) service reached | one-shot |
| 2 | 1 | cyan | JVS config-enum reached | one-shot |
| 3 | 1 | yellow | Input poll live (first `jvs_digital` call) | one-shot |
| 4 | 1 | magenta | First cart/disc stream serviced | one-shot |
| 5 | 1 | green↔blue blink | Cart streaming activity (toggles every 32 streams) | repeating |
| 6 | 1 | green (boot) **or** blue→yellow→white (steady) | Boot: cart boot-DMA path fired, once. Steady: EEPROM-write byte count reached 1/8/16 words. Same slot, two different call sites (`cart.c:208`, `main.c:761-764`) — context (boot vs. in-game) tells you which. | mixed |
| 7 | 1 | cyan (boot) **or** orange (steady) | Boot: cart PIO-read path fired, once. Steady: JVS config-enum transmit reached, once. Same slot, two call sites (`cart.c:227`, `main.c:1330`). | one-shot (either) |
| 8 | 1 | green/red/blue/yellow, repainted ~1×/s | Maple/DMA engine health this window: red/green = alive, no DMA triggered; blue/yellow = alive AND triggering | repeating |
| 9 | 1 | white↔grey-green blink | MIE replies still flowing (toggles every 16 replies) | repeating |
| 10 | 1 | white/grey ↔ solid red, ~1×/s | Engine verdict: toggling white/grey = returned OK at least once this window; **solid red = every call this window came back "busy"** | repeating |
| 11 | 1 | white | EEPROM-write-skip kicker reached | one-shot |
| 12 | 1 | green | EEPROM-lib decode-commit reached (former real-HW blocker) | one-shot |
| 13 | 1 | yellow | Post-kicker EEPROM trio reached | one-shot |
| 14 | 1 | cyan | EEPROM index-read thunk **or** settings-skip hook reached | one-shot |
| 15 | 1 | white | Restart path taken — visible only 1-2 frames before the BIOS blanks the screen for reboot | one-shot, transient |
| 16 | 2 | red/green/yellow, per DMA trigger | Triggered maple list base sanity: red = null pointer, green = in RAM, yellow = elsewhere | repeating |
| 17 | 2 | red/green, per trigger | First descriptor word null? | repeating |
| 18 | 2 | red/green, per trigger | Any MP_Start frames in the walked list? | repeating |
| 19 | 2 | red/green, per trigger | Any MIE (`0x86`) commands in the list? | repeating |
| 20 | 2 | red/yellow/green, per trigger | List entries walked: 0 / 1-3 / 4+ | repeating |
| 21 | 2 | yellow | **Fault flag:** an unmodelled MIE sub-command was seen | one-shot |
| 22 | 2 | yellow | **Fault flag:** an unmodelled MIE top-level command was seen | one-shot |
| 23 | 2 | red | **Fault flag:** a maple list pointer or reply address landed outside RAM (undeliverable reply) | one-shot |
| 24 | 2 | green↔blue blink | **New, Task 8:** GD-ROM drive poll heartbeat (`gd_wait_drq`/`gd_wait_clear`, `shims/src/gd.c`) — see below | repeating |

Full per-slot source citations: `shims/src/cart.c`, `shims/src/main.c`,
`shims/src/gd.c` (grep `shim_mark(` in `shims/src/`).

### The new heartbeat (slot 24)

`gd_wait_drq` and `gd_wait_clear` (`shims/src/gd.c`) are the shim's raw-ATA
polling loops — every disc access spins in one of these until the drive
answers or ~50M polls time out (`GD_SPIN`, `gd.c:114`). Task 8 adds one
`GD_HEARTBEAT(i)` call at the top of each loop body — a macro
(`shims/src/gd.c`, right before `gd_wait_clear`) so both loops share one
definition; its core logic, stride-gated so it costs nothing on the fast
path:

```c
if (!(i & 0xffffu))                                  /* every 64K polls */
    shim_mark(24, (i & 0x10000u) ? 0x07e0 : 0x001f);  /* green<->blue blink */
```

**Slot 24, not the brief's sketched slot 6**: every slot 0-23 was already
claimed by another HUD user before this task (cart.c, main.c — full map
above), so 24 is the first free slot, row 2. Gated `#if !GD_LOADER_BUILD`
(`shim_mark` lives in `util.c`, which the loader's `gd.o` build does not
link — same reason `gd_fail`'s `SHIM_ERR` store is loader-gated,
`gd.c:202-212`).

**How to read it on a TV:**
- **Blinking green↔blue** = the drive is being polled and answering —
  healthy, including during a long real seek (climbs through many polls
  before the color flips).
- **Frozen on one color** while you know a disc access should be
  happening (e.g. mid-load, or during a level/character-select transition)
  = the shim is stuck inside `gd_wait_drq` or `gd_wait_clear`, spinning on
  the drive with no answer — **this is the exact real-hardware GD-wedge
  failure mode the emulator cannot show** (Flycast answers in one poll, so
  under emulation this mark is normally a single-color flash per disc
  access, never a sustained climb — Cleopatra's equivalent diagnostic,
  `../cleopatra/shims/src/gd.c:47`, documents the same asymmetry).
- If the wait then times out (~10 s), the shim does not hang forever — it
  reports the failure and the screen goes to the red death screen (below).

**Evidence this paints correctly:** `docs/kb/img/phase5-hud-heartbeat.png`,
a mid-boot capture (leg `phase5/hud-smoke-scan`, ~19 s post-launch, during
the loader's NAOMI-splash-overlay window before the game's own rendering
starts) shows a clean 16×8 solid-blue block at the calculated slot-24
position; pixel-sampled at (192,15) = `srgb(0,0,248)`, matching
`shim_mark`'s 0x001f (RGB565 blue) exactly.

### Healthy boot vs. wedged — what the operator actually sees

- **Healthy:** screen may show a brief full-black flash with a
  handful of colored 16×8 blocks in the top-left corner for well under a
  second right at handoff — that's the one-shot milestones (slots 0-15)
  painting before the game's real graphics start. Then the screen fills
  with the game's own NAOMI/SEGA/ADX splash chain and normal boot proceeds
  — this is expected and is **not** something to photograph or report; the
  marks did their job already. Once the game is running, the only marks
  that can still be seen are the repeating ones (5, 6/steady, 8, 9, 10,
  16-20, 24) and only for the instant before the next game-rendered frame
  covers them again — do not expect to *see* them steadily during normal
  play; their absence is not itself a bad sign.
- **Wedged (hang):** the picture simply **stops changing** — whatever was
  on screen (game frame, splash, or a HUD mark) stays frozen indefinitely.
  If you can still make out a HUD mark in the freeze, that slot's last
  color is diagnostic: e.g. slot 24 frozen mid-blink pins the hang inside
  the GD poll loops; slots 8/10 frozen solid red mean the maple/DMA engine
  stopped returning "OK"; slot 15 that then goes dark with the whole
  screen fading to the BIOS gray/black means a reboot loop, not a wedge.
- **Fatal (death screen):** the screen goes to a **solid color fill**
  with three rows of white-on-fill hex digits burned in around
  screen-center (`shim_die`, `shims/src/util.c:180-204`, unconditional —
  paints even in a `SHIM_HUD 0` release build). This is not a hang; the
  shim detected a specific bad condition and stopped on purpose. Decode
  it below.

### Death-screen decode

`shim_die(code, a, b)` fills the whole visible framebuffer with a
code-selected color, then burns in three hex numbers top-to-bottom at
screen coordinates (20,100)/(20,114)/(20,128): **code**, **a**, **b**, in
that order (`util.c:180-202`). The record is also written to `SHIM_ERR`
(`shim_iface.h:12`, four words: `code, a, b, 0xdeadcafe` — the last word
is a magic sentinel confirming the record is a live write, not stale
memory).

| Fill color | `code` | Meaning | `a` | `b` |
|---|---|---|---|---|
| cyan (default) | anything not listed below | Unmatched/unused code | — | — |
| yellow | `2` | Cart-service handed a bad destination address | cart byte offset | destination that failed the fence |
| magenta | `3` | Unmodelled maple frame (unknown MIE sub-command reached `shim_die`, not just the yellow HUD flag) | sub-command | recv address |
| **red** | **`4`** | **GD-ROM read error** — every `gd_read_cart` failure surfaces here, from every one of gd.c's 8 failure sites (below) | cart byte offset being read (same value across cart.c's three read paths — steady, boot-DMA, boot-PIO) | `gd_last_err` — decode this field for the site (below) |
| blue | `5` | Reserved for "GD poll hang" in `shim_die`'s own color comment (`util.c:189`) — **defined but not currently wired to any call site**; a GD poll timeout today still reaches the screen as code `4` (red), not `5` | — | — |

**On a red (`code=4`) screen, decode field `b`.** It is `gd_last_err`
(`gd.c:119,201`), formatted `0xda SS TT EE`:

- `0xda` — fixed marker byte (always present, confirms this is a gd.c
  record).
- `SS` — the **failure site**, 1-8, table below. This is where "which
  step of the disc read failed" actually lives — not in the top-level
  `code` (which is always `4`).
- `TT` — the ATA Alternate Status register at the moment of failure
  (`GD_ALTSTAT`, `gd.c:89`). Bit `0x80` = BSY (drive busy), `0x08` = DRQ
  (data request), `0x01` = CHECK (drive raised an error).
- `EE` — the ATA Error register (`GD_ERRREG`, `gd.c:91`) — the drive's own
  sense/error code, only meaningful when `TT` has `CHECK` (`0x01`) set.

| Site `SS` | Name | Meaning |
|---|---|---|
| `01` | `GD_E_IDLE` | Drive never went idle before the command was issued |
| `02` | `GD_E_PACKET` | PACKET command accepted, but DRQ for the 12-byte SPI packet never came |
| `03` | `GD_E_DATA` | DRQ for a data block never came (seek/read failed, or bad media) |
| `04` | `GD_E_COUNT` | Drive offered an impossible byte count for a data block |
| `05` | `GD_E_END` | Transfer completed but the drive never returned to idle |
| `06` | `GD_E_CHECK` | Drive raised CHECK — `EE` (Error register) holds the sense key |
| `07` | `GD_E_ARG` | Caller bug: null or oversized request (shim-internal, not a drive fault) |
| `08` | `GD_E_RANGE` | Requested read runs past the end of the cart image (shim-internal) |

(`GD_E_*` definitions: `shims/src/gd.c:190-197`; site is written into
`gd_last_err`'s bits 23:16 by `gd_fail`, `gd.c:199-217`.)

**Loader-boot variant (before the game ever starts):** if the *loader's*
own one-time disc rehearsal read fails (`loader/main.c:221-226`), the
runtime shim isn't installed yet, so this isn't a `shim_die` screen — it's
KOS's own `halt()` (`loader/main.c:84-89`): also a solid-red full-screen
fill, but with the message drawn as **literal readable text**, no hex
decode needed: `RAW-ATA READ FAIL r=<site, negative> err=<gd_last_err,
same 0xda-encoding>`. Same site table and same `gd_last_err` format apply
to the `err=` field; only the presentation is friendlier (plain ASCII, not
burned-in hex digits) because KOS's font routine is still available at
this boot stage.

**A transient, not-on-screen detail:** `gd_fail` also writes an
intermediate code `0x60 | site` (`0x61`-`0x68`) to `SHIM_ERR` the instant
it detects the failure (`gd.c:212`) — this is what the brief's "`0x6<site>`"
convention refers to. In the runtime shim path, cart.c's `shim_die(4, ...)`
call immediately overwrites that same record with the red-screen version
above, so an operator watching the TV only ever sees `code=4`; the `0x6x`
value is reachable only via a live RAM watch faster than the overwrite, not
via the death screen itself.

### PACKTEX post-match constraint (2026-08-25 — legs ernula-lili, modesel-probe)

**Second texture loader characterized.** The binary carries a packed
(non-PVRT) texture path — strings at dat `0x168ba0`, adjacent to
`TEXTURE LOAD ERROR !`: `PACKTEX MALLOC FAILED %s`, `PACKTEX DECODE
ERROR`, `PACKTEX LOAD ERROR`, `LOADPACKSTEX LIST MALLOC FAILED %s`.
`MODESEL.PAK` (87,920 B) contains **zero** PVRT records — all its art
goes through this loader. It shares the instrumented error handler:
the probe fired `code=00000006` (clean samples are 0) and the
auto-savestate hook captured the failure state (TEXERRSAVE slot 0).
MODESEL.PAK is the mode-select screen (beginner/score selector —
operator-identified on sight); the game returns there after **every**
match, loading it while the match's textures are still resident.

**Observed failure** (`captures/ernula-lili.log`): P01C + P07E stage-8
match, peak 8,282,464 / free 106,144 — match completed fine, then
MODESEL loaded → `PACKTEX LOAD ERROR`, frozen error screen (T1-class).
Note P01C resident 118,176 vs census 217,216: per-character residency
is NOT census; the linear demand model is a rough estimator only
(±~100 KB observed), direct measurement rules.

**Demand measured** (`captures/modesel-probe.log`): Fabian mirror
(P04E+P04A) stage-8 match peak 7,702,112 / free 686,496; MODESEL
transition set a new max 8,064,608 → **D = 362,496 B** net on top of
the match peak; survived clean. Caveat: D possibly winner/content
dependent; one measurement.

**Binding constraint: stage match peak + 362,496 ≤ 8,388,608**, i.e.
match-peak budget 8,026,112. Measured stage-8 match peaks (shrink-2
build) vs that budget: Fabian mirror 7,702,112 PASS (measured
end-to-end); Ernula mirror 8,180,736 over by 154,624; Changpo-C +
Ernula 8,282,464 over by 256,352 (= the observed failure);
Sakurako + Ernula 8,372,576 over by 346,464.

**Config re-pricing** (savings vs the shrink-2 measurements: third
1024² −196,608; fourth 1024² −196,608; each 512²→256² −49,152 —
STAGE08 carries 32× 512² VQs, same explicit-offset TXTR chunk, same
in-place method):
- shrink-3: worst measured pair still ~149,856 over → **fails
  post-match**. The former shrink-3 bar is obsolete.
- shrink-4: worst measured free 46,752 → fits, but thinner than the
  observed residency variance.
- Composable options, art cost vs margin (operator's call):
  shrink-3 + 7×512² ≈ 194 KB margin (0b777810 stays full);
  10×512² alone ≈ 145 KB margin (both 1024² heroes stay full);
  shrink-4 + 2×512² ≈ 145 KB margin.

**Stage-9 disposition (same evening).** MODESEL follows every match,
and STAGE09 (census 2,807,808, no 1024² lever) is only 79,872 lighter
than shrink-2-patched STAGE08 — but STAGE09 is **not VS-selectable**:
load attribution across all five DC legs (ab-b, ernula-s2, attract-s2,
ernula-lili, modesel-probe — VS matches on STAGE01/02/03/04/08,
attract demos on 01/03/04/08) shows STAGE09 loaded zero times; it is
1P-campaign content, covered by the planned savestate-assisted
campaign-completion leg (Task 18). If it overflows there, the same
in-place 512²→256² lever applies to STAGE09.PAK (47 textures). A
follow-up probe (Sakurako+Ernula on STAGE03 through mode-select, same
session) set no new maximum — heavy pair + light stage + MODESEL fits.
The shrink-2 ruling (Amendment 2) is dead; the VS-side ship config is
decidable now from the stage-8 numbers above, with the campaign leg as
remaining coverage.

## Ghidra + savestate recon (2026-08-26, operator-directed: "run the recon for D, E, and STGSEL")

Static session on the `senkosp3` DB (`scripts/ghidra/run.sh`; new committed
script `CallTree.java`) plus an offline post-mortem of the TEXERRSAVE
savestate. No emulator runs. Three questions, three answers.

### 1. The PKTX compressor is stock Okumura LZSS — cracked and validated

The PKTX entry decoder is `FUN_8c0b6980` (pool `0x8c0b64b0` in the
dispatcher's PKTX branch; `Decomp.java 0x8c0b6980`): 4096-byte ring buffer
zero-initialized, write pointer starts at 0xFEE; flag bytes LSB-first,
bit=1 literal, bit=0 match; match = 2 bytes, ring position
`b1 | (b2&0xF0)<<4`, length `(b2&0xF)+3`; returns success when the source
is consumed, error when the output would overrun. Called as
`decode(src=entry+8, csize, dst, dsize)`; the entry header is simply
`u32 decompressed size, u32 compressed size` (the earlier "0x20 byte" was
the low byte of the size — every record ends in 0x20 because of the 32 B
GBIX+PVRT headers).

Validation: a python re-implementation decompressed **every PKTX chunk on
the disc** (all root PAKs) into well-formed GBIX+PVRT records;
MODESEL.PAK's four entries sum to the measured D = 362,496 to the byte
(`scratchpad/lzss_pktx.py`, logic now embedded in
`scripts/texerrsave_postmortem.py`). Authoring streams is trivial: an
all-literal stream (flag 0xFF + 8 literals, 9/8 of payload) is always
decodable, and VQ payloads are ~8× smaller than the raw entries they
replace, so repacked entries always fit the original chunk extents — the
offset table need not move (slack after each entry is dead bytes).

**Census correction that falls out:** every character PAK carries a PKTX
chunk the TXTR-only census never saw — P01–P06/P08: 655,360 B
(one 512² raw 16bpp sheet + one 256² raw), P07: 917,504 B (512² + 3× 256²
raw). These are the select/VS cut-in portrait sheets.

### 2. The free path and the post-match mechanism (option E's question)

Bottom-up from the allocator (all decompiled via `Decomp.java`):

- `FUN_8c03749c` = **arena free with coalescing** (unlink from alloc list
  at cfg+0x24 via `FUN_8c03c870`, merge adjacent free blocks, insert into
  free list at cfg+0x2c via `FUN_8c03c830`); single public wrapper
  `FUN_8c037440`. `FUN_8c03c46e` and `FUN_8c03c59e` are two allocator
  variants (plain first-fit and alignment-aware); `FUN_8c035144` is the
  sub-page allocator (block type 0x15); `FUN_8c02eb20` is texture-buffer
  allocation, not free.
- Texture-list free lives beside texture-list load: `FUN_8c070e6c` /
  `FUN_8c070ef8` next to `FUN_8c070ebc`. The **PAK unloader is
  `FUN_8c0b5cf4(resource_array, type_mask)`** (right after the by-name
  loader `FUN_8c0b5be8`): bit 0 frees each texture list entry via
  `0x8c070ef8` (VRAM textures freed) then the list via heap-free
  `0x8c06e10c`.
- **Scene structure: coroutine tasks.** The mode-select scene is one large
  non-functionized code region (`0x8c1592xx–0x8c1599ee`,
  `DisasmRange … force`): it loads `MODESEL.PAK` by name at entry (pool
  `0x8c159308` → string `0x8c1918ec`, loader ptr `0x8c15930c` →
  `FUN_8c0b5be8`), runs its per-frame loop, and at its own exit tail calls
  `FUN_8c0b5cf4(&resources, 9)` + buffer free (`jsr` at `0x8c1599c2`,
  pools `0x8c159a20/24`). STGSEL's scene (`0x8c15adxx`, string
  `0x8c191a28`) has the same shape. Every scene frees its own PAKs at its
  own task exit — so the post-match overlap is the mode-select task
  starting (and loading) before the match task has run its teardown tail.
  A queued command manager (`0x8c087780` jump-table dispatcher, cmds
  0x0b–0x12: `FUN_8c087484` load-slot / `FUN_8c08750c` free-slot) also
  services PAK slots; loads resolve through the PAK-name table at
  `0x8c18880c` (0 = COMMON, 1–48 = P01A–P08F, 49–51 = P09–P11,
  52–61 = STAGE01–10, 62 = PLSEL, 63 = TUTO).
- An E-style patch is therefore a task-ordering change (hoist the match
  task's teardown above the successor spawn, or delay the menu task's
  load), not a two-instruction swap. **Priced but not needed** — see the
  post-mortem below.

### 3. TEXERRSAVE post-mortem — full residency attribution (STGSEL answer)

`scripts/texerrsave_postmortem.py` (offline; no emulator) decompresses the
crash savestate (`~/Library/Application Support/Flycast/data/disc.state`,
2026-08-25 22:22, the ernula-lili PACKTEX failure), locates guest RAM by
boot-code signature and guest VRAM by anchoring STAGE08's 32 VQ codebooks
(32/32 anchor at stream +0x2bb765; VRAM is stored 64-bit-view linear),
walks the arena lists at `0x8c170eb8`, and byte-matches every block
against every TXTR record and every LZSS-decompressed PKTX entry on the
disc. Result: alloc 8,282,464 B in 87 blocks + free 106,144 — equal to
the leg's logged maximum — with **83/87 blocks matched byte-exactly**;
the four unmatched are the runtime-composed 699,072 B atlas (texobj #7,
built at boot, in no PAK), the KAMUI2-internal 6,144 B texture, and our
two shrunk hero re-encodes (absent from the unpatched .dat by
construction).

Residency at the post-match MODESEL load (Changpo-C vs Ernula-E, STAGE08):

| Owner | Resident content | Bytes |
|---|---|---|
| TA/region + FB reservations | flags 0x43 + 0x13 | 1,490,944 |
| FONT.PAK | 3 textures (1 already VQ) | 53,248 |
| COMMON.PAK | 14 textures: 5× 256² raw, 1× 256×512 raw rect, 3× 256×128 raw rect, small | 1,155,936 |
| runtime atlas (no PAK) | 512² raw+mips, texobj #7 | 699,072 |
| P01C.PAK | TXTR VQ-mips 137,984 + **PKTX raw portraits 655,360** | 793,344 |
| P07E.PAK | TXTR VQ-mips 174,848 + **PKTX raw portraits 917,504** | 1,092,352 |
| STAGE08.PAK | 32× 512² VQ + 2 heroes (full) + 2 heroes (shrunk) + small | 2,991,616 |
| MODESEL.PAK | **zero** — texobj #84 created, its 131,072 alloc failed | 0 |

(The crash detail: MODESEL's first entry needed 131,072 against 106,144
free — texobj #84 exists with id 0xffffffff and no arena block.)

**Rulings this evidence forces:**

- **STGSEL is NOT resident during matches** (nor PLSLTX, nor PLSEL). The
  STGSEL lever is dead. Stage-select's own textures are freed by its
  scene task before the match runs — the per-scene unload works exactly
  as §2 describes for menus; only the *overlap at the handoff* bites.
- **The character PKTX portrait sheets ARE resident through the whole
  match** — 655,360–917,504 B per player of raw 16bpp art. Converting
  them to VQ (256² raw 131,072→18,432; 512² raw 524,288→67,584) saves
  **1,363,968 B on the worst measured pair** — data-only, loader-proven
  (VQ-in-PKTX ships in the game's own PLSLTX), an order of magnitude
  above every panel-shrink lever. This supersedes options A/B/C/E; the
  updated decision menu is `arena-fit-options.md` §6 (option F).
- COMMON's five 256² raw squares are a further −563,200 reserve
  (rectangles can't VQ — PVR VQ is square-only). The runtime atlas is
  not patchable by repacking.

## F-zero build (2026-08-26)

Operator config choice: **F-zero** (`arena-fit-options.md` §6 — portraits
only; all four 1024² stage textures and MODESEL ship as original bytes;
worst-measured-pair margin 624,288 B). Built entirely offline; no
emulator run (operator AFK by instruction).

- Tool: `scripts/pktx_vq.py`. Discovers every raw 16bpp square PKTX
  entry (dt 01/09, 256²/512², pf 0–2) in P01A–P08F + P09–P11, VQ-encodes
  at the same resolution through `shrink_vq.finish()` (the A/B-gated
  k-means encoder; PSNR tripwire relaxed 26→20 dB — it guards against
  encoder garbage, art quality is the operator preview gate), keeps each
  entry's GBIX verbatim, wraps in an **all-literal LZSS stream**
  (flag 0xFF + 8 literals — always decodable by `FUN_8c0b6980`; csize =
  9/8·dsize, still ~7× under each slot), and emits splice blobs +
  manifest for `make_gdi.py`'s existing texpatch step. The manifest
  REPLACES the shrink config wholesale — no hero records means the
  stage textures ship untouched from `senkosp.dat`.
- Result: **112 entries repacked, 58 unique sheets** (512² pilot
  cut-ins are per-variant recolors — 48 unique; the 256² cockpit sheet
  is shared across a character's six variants — 8 unique; the two
  glow-ring sheets are shared by all P07 variants + P10/P11). PSNR
  25.4–41.8 dB; lowest is P05's glitter-background cockpit (visible
  speckle in the sparkle field, figure clean); rings 40.9/41.8 dB — the
  §6 banding caveat is resolved. 29,130,752 B of VRAM allocations
  removed disc-wide.
- Offline controls, all passed: every produced stream decompressed with
  the python LZSS decoder (itself validated against every PKTX chunk on
  disc) and byte-compared; every record round-tripped through
  `decode_pvr_vq.decode()`; manifest applied to an in-memory cart copy
  and **every PKTX entry of all 51 PAKs re-decompressed clean — 112 VQ,
  0 raw squares remaining**.
- Operator previews: `captures/phase5/textures/portraits-vq/`
  (`<label>-before.png` = decoded original raw, `-after.png` = decoded
  shipped VQ; INDEX.txt maps labels to PAKs and PSNR).
- Mastered `build/disc.gdi`; track04.iso md5
  `42ab245b905fa51ec9b32396918d07b7` (criterion-7 md5 set re-records at
  the Task 13 re-audit). Emulator verification legs = Task 18.

## F-2 build (2026-08-26)

The F-zero build above was rejected at the art gate (`arena-fit-options.md`
§7: cockpit VQ visually unacceptable; new operator rule — never compress
textures containing text). Operator config choice: **F-2** with the shrink
target amended to **0b736ff0** (margin unchanged at 312,320 — all three
STAGE08 heroes are co-resident at the stage-8 peak, so −196,608 applies
whichever shrinks). Built entirely offline; no emulator run.

- `scripts/pktx_vq.py` (F-2 policy): 512² pilot cut-ins always VQ; a 256²
  is VQ'd only when its PVRT content md5 also appears in P10.PAK/P11.PAK
  (the pure ring PAKs) — that classifies the two shared glow-ring sheets
  as rings and leaves all 48 per-character cockpit entries RAW. Result:
  **64 entries repacked, 50 unique sheets** (48 pilots + 2 rings);
  self-check re-walked all 51 PAKs — 64 VQ, 48 raw squares, exactly the
  skipped cockpits. Pilot/ring encodes are content-seeded, so they are
  byte-identical to the F-zero build and the existing
  `portraits-vq/` previews remain the operator-gated evidence (ignore the
  256² cockpit `-after` previews there — those sheets now ship raw).
- `scripts/shrink_vq.py` (TARGETS = 0b736ff0 only) now runs AFTER
  pktx_vq.py and APPENDS to its manifest. Encode from the operator-tuned
  edit (`textures/edit/0b736ff0.png` + params), PSNR 39.3 dB.
- Mastered `build/disc.gdi`: 65-record texpatch; track04.iso md5
  `b056f4605662aab04bbff48609f891b6` (criterion-7 md5 set re-records at
  the Task 13 re-audit). Verification legs (§4 suite, full rerun) = Task 18.

## Task 18 — F-2 verification legs (2026-08-26, operator)

**Leg 1 (`captures/phase5/f2-vs.log`, 3,512,031 lines): PASS.** Operator
played beyond the asked scope — Ernula mirror + many 2P matches across
characters + a 1P set. TEXERR: 71 post-boot samples all clean (line 128 =
known pre-boot sampler junk). ARENAHW all-time peak **7,718,528** (free
670,080) vs the F-2 prediction 7,713,792 (= measured F-zero mirror
baseline 7,685,120 + cockpits-raw 225,280 − hero shrink 196,608) —
model within 4,736 B despite the wider matchup pool. Every mode-select
transition clean. CRC: 4,631/4,631 drive reads verified, 0 mismatches
(coverage FAIL = expected no-shim condition on release discs). Operator
art verdict: everything looks fine. 49 operator F12 screenshots archived
in `captures/phase5/f2-shots/`.

**1P between-stage splash identified (`f2-splash` leg + frame capture).**
Operator asked whether the between-stage splash uses compressed art.
Evidence: (1) disc has no dedicated splash/loading file; (2) the leg's
read log shows only opponent P##.PAK + STAGEnn.PAK loading between 1P
stages; (3) continuous framebuffer capture (FLYCAST_SHOT_EVERY=4 + a
copy-on-change archiver, ~15 fps, 10,512 frames in
`captures/phase5/f2-splash-frames/`) caught both transitions: the splash
is **"STAGE n" FONT text on black** (frames 01596, 08865–08868), entered
and exited by a diagonal wipe of live scene renders — the incoming wipe
corner already shows the next arena rendering, i.e. the wipe starts only
after the load completes. No portrait/pilot art appears; FONT and COMMON
are untouched in F-2, so the splash ships bit-identical art. Slow media
lengthens the black card, never exposes partially-loaded textures (loads
go PAK→RAM→decompress→VRAM; nothing draws before upload). Splash-leg
health: TEXERR clean, peak 6,020,128.

**Leg 2 — unattended attract soak (`captures/phase5/f2-soak.log`,
2,486,771 lines): PASS.** Clean boot (no savestate — deterministic-repro
compliant), zero input, ended by watcher at 1,808 s (30.1 min) with
**3 stage-8 demo loads** observed (criterion: ≥30 min AND ≥2; STAGE08.PAK
first-sector reads at fad=0x84e53). TEXERR: 46 post-boot samples all
clean (line 128 = known pre-boot junk). ARENAHW peak 7,448,928 (free
939,680) — attract demos sit under the VS-leg peak as expected. CRC:
1,739/1,739 drive reads verified, 0 mismatches (coverage FAIL = expected
no-shim condition). Remaining §4 item: savestate-assisted 1P campaign
completion with the END1–END4 PKTX overlap check (operator leg).

**Leg 3 prep — easy-difficulty leg build (2026-08-26).** The campaign
leg needs the easiest difficulty (operator can't reliably beat the
level-8 boss's bird form otherwise). A DC-side test-menu change cannot
work: the shim's EEPROM is session-only (`shims/src/main.c` §EEPROM —
RAM copy, no backing store) and test-menu exit is a full reboot that
reloads the baked image. So the setting is **baked**, free-play
precedent: operator flipped the settings once in the Naomi-profile
Flycast (stock build; writes
`~/Library/Application Support/Flycast/data/senkosp.zip.eeprom` on
quit), and the changed game area (EEPROM 0x24..0x4B, both CRC headers
`1c1e`→`0868` + both record copies, CRCs computed by the Naomi BIOS
writer itself) was spliced verbatim into the sub-0x03 blob via a new
default-off env hook in `scripts/extract_mie_blobs.py`
(`EEPROM_GAME_HEX`, 40 hex bytes, asserts dual-copy consistency).
Settings decoded from the diff: difficulty byte[6] `01`→`00` (Easy,
numeric floor), round time vs Human u16@[10] 70→120, vs CPU u16@[14]
70→110, CPU-story u16@[12] 150 unchanged (was already default).
**Leg-only build** (`LOADER_FORCE_TEST_BOOT` precedent): track04 md5
`ec3dba3c79e544843fb7d12be44a8c03`; the shipping F-2 build stays
`b056f4605662aab04bbff48609f891b6` and is rebuilt (env unset) after the
leg. Texpatch manifest confirmed 65 records before mastering.

# Arena-fit options — root cause, case history, and the decision menu

*2026-08-25. Status: operator decision pending. All numbers measured on
the instrumented Flycast DC profile unless marked estimate. Evidence
logs under `captures/` (gitignored); KB details in
`phase5-hardware.md` (§Fix scoping, §Amendments, §PACKTEX post-match
constraint) and `game.md` (§Character ↔ PAK mapping).*

## 1. Root cause

The Naomi hardware gives the game a **16 MB** texture arena; the
Dreamcast port has **8 MB** (`ARENAHW total=00800000`). The game
manages this arena with its own allocator and loads textures only at
scene boundaries (PAK loads) — never during play (verified repeatedly:
every ARENAHW maximum in every leg sits within ~250 log lines of a
PAK load; bullet-heavy fights advance the arena by zero bytes).

Two loaders feed the arena:

1. **TXTR/PVRT loader** (`TEXTURE LOAD ERROR !`) — plain PVRT records
   (raw twiddled, VQ, VQ+mips). Stage and character art.
2. **PACKTEX loader** (`PACKTEX MALLOC FAILED %s` / `PACKTEX DECODE
   ERROR` / `PACKTEX LOAD ERROR`, strings at dat `0x168ba0`) — PKTX
   chunks holding **LZ-compressed standard GBIX+PVRT records**
   (literal `GBIX`/`PVRT` strings survive in the streams; per-entry
   header = 8 B with decompressed size and compressed length). Menu
   art: MODESEL, PLSLTX, STGSEL, BG, TUTO, LCNS, COMMON.

Both loaders share one error handler (our TEXERR probe hooks it;
clean heartbeat `code=0`, PACKTEX failure fired `code=6`). On
allocation failure the game shows a frozen error screen — on real
hardware that is a hang requiring a power cycle.

**The killing combination:** a stage-8 match leaves the arena nearly
full, and after *every* match the game returns to the mode-select
screen, loading `MODESEL.PAK` **while the match textures are still
resident**. That transition needs 362,496 B on top of the match peak.

## 2. Case history — what each leg proved

| # | Leg (log) | Scenario | Result | What it proved |
|---|---|---|---|---|
| 1 | `ab-a-tuned` | shrink-3 build, play | clean, peak 7,799,808 | tuned art OK (visual gate passed) |
| 2 | `ab-b-shrink2` | shrink-2 build, play | clean, peak 8,372,576 / free 16,032 | later reattributed: peak was the operator's **Sakurako+Ernula stage-8 match**, session ended before mode-select |
| 3 | `ernula-s2` | Ernula vs Ernula, stage 8 | clean, peak 8,180,736 / free 207,872 | mirrors are cheap — variant PAKs share nearly all textures (~one set + 16 KB) |
| 4 | `attract-s2` | unattended attract, 5+ rotations | clean, stage-8 demo peak 8,379,424 / free 9,184 | attract demos randomize pair AND stage; demo scene base equals match base; 16,032 was not the cliff |
| 5 | `ernula-lili` | Changpo-C vs Ernula, stage 8, played to end | **PACKTEX LOAD ERROR after the match** (peak 8,282,464 / free 106,144) | the post-match MODESEL transition exists and kills; also P01C resident 118,176 vs census 217,216 → **residency ≠ census, ±100 KB variance** |
| 6 | `modesel-probe` | Fabian mirror stage 8, through mode-select | clean; match 7,702,112 → MODESEL max 8,064,608 | **D(MODESEL) = 362,496 B**, +4 arena blocks = its 4 textures |
| 7 | same session | Sakurako+Ernula on STAGE03 through mode-select | clean, no new max | heavy pair + light stage + MODESEL fits; "first stage in list" = STAGE03 file |

Stage-9 disposition: STAGE09 (6.6 MB file, biggest, max texture 512²)
loaded **zero times** across all five VS/attract legs — it is
1P-campaign content. The campaign-completion leg (Task 18) covers it;
the same levers apply to STAGE09.PAK if needed.

## 3. The binding constraint

```
stage-8 match peak  +  D(MODESEL) 362,496  ≤  8,388,608
⇒ match-peak budget = 8,026,112
```

Measured stage-8 match peaks (shrink-2 build) vs that budget:

| Pair | Match peak | +MODESEL | Verdict |
|---|---|---|---|
| Fabian mirror | 7,702,112 | 8,064,608 | PASS (measured end-to-end) |
| Ernula mirror | 8,180,736 | 8,543,232 | over by 154,624 |
| Changpo-C + Ernula | 8,282,464 | 8,644,960 | **the observed crash** |
| Sakurako + Ernula | 8,372,576 | 8,735,072 | over by 346,464 |

Worst *measured* pair: Sakurako+Ernula. Worst *possible* pair by
census is Ernula+Lili (536,096), ~18 KB above Sakurako+Ernula — but
residency variance is ±100 KB, so any chosen config needs an
Ernula+Lili verification match. Margins below are quoted against the
worst measured pair.

**Levers and their prices** (all in-place splices, proven method —
the TXTR chunk's explicit per-texture offset table lets a smaller
record replace a bigger one with the rest of the PAK untouched):

| Lever | Saves | Notes |
|---|---|---|
| 1024²→512² VQ re-encode (per texture) | 196,608 | the original fix; tuner workflow exists |
| 512²→256² VQ re-encode (per texture) | 49,152 | STAGE08 has 32× 512² VQs; same method, needs a small `shrink_vq.py` generalization |
| MODESEL PKTX raw→VQ (option D) | up to 251,904 off D | see §4-D |

## 4. The options

Verification suite required for whichever option wins: Ernula+Lili
stage-8 match through mode-select, Ernula-mirror re-check, attract
soak with ≥2 stage-8 demos, ≥30-min soak, campaign-completion leg
(covers STAGE09/P09/P10/ending), TEXERR clean everywhere.

### A. shrink-3 + 7×512² panels — margin ≈ 194 KB

`0b777810` (decals, ARGB4444) ships as the untouched original.
`0b6f67d0` ships as the operator's tuned 512² edit (already passed
the leg-A visual gate). Seven of the 32 background 512² panels drop
to 256². Arithmetic: 8,372,576 − 196,608 − 7×49,152 + 362,496 =
8,194,400 → free 194,208.

- Art cost: one 1024² halved (already accepted once) + 7 panels
  quarter-area. Operator picks which panels (contact sheet on demand).
- Risk: lowest margin-risk of the no-reverse-engineering options.
- Effort: small — extend `shrink_vq.py` TARGETS to per-record sizes,
  tuner already handles the encode path.

### B. shrink-2 + 10×512² panels — margin ≈ 145 KB

Both hero 1024²s (`0b777810` AND `0b6f67d0`) ship full-size original;
ten panels drop to 256². 8,372,576 − 10×49,152 + 362,496 = 8,243,552
→ free 145,056.

- Art cost: zero on the heroes, ten panels quartered.
- Risk: 49 KB less margin than A; ten quartered panels may be more
  visible than one halved 1024² (they tile the arena surfaces).
- Effort: same as A.

### C. shrink-4 + 2×512² panels — margin ≈ 145 KB

All four 1024²s halved (including `0b777810`) + two panels.
Dominated by A and B on art at equal-or-worse margin. Listed for
completeness; not recommended.

### D. Repack MODESEL's textures as VQ — cuts D itself by ~252 KB

**Evidence (2026-08-25 investigation):**

- `MODESEL.PAK` = `DRES` container, `PKTX` chunk, 4 entries.
  Per-entry 8-byte header: `0x20` byte, u24/u32 **decompressed size**,
  u32 compressed length (matches entry spacing).
- The four decompressed sizes: 131,104 + 32,800 + 131,104 + 67,616
  (each = record + 32 B of GBIX/PVRT headers) → texture data
  131,072 + 32,768 + 131,072 + 67,584 = **362,496 = measured D to
  the byte**, and the arena gained exactly +4 blocks at the
  transition. Inventory: two 256² raw 16bpp, one 128² raw, one
  512² VQ.
- **The loader accepts VQ inside PKTX — proven by the game's own
  content:** `PLSLTX.PAK` PKTX entries decompress to 18,464-byte
  records = 256² VQ (+32 header). No loader-capability risk.
- Compression looks like LZSS with per-8-token flag bytes (streams
  open `df 'GBIX' …` — flag `11011111`, LSB-first literals). Not yet
  fully reversed.

**The change:** re-encode the two 256² raw → 256² VQ (18,432 each)
and the 128² raw → VQ (6,144); keep the existing 512² VQ. New
D = 110,592 (−251,904). Optionally the 512² VQ → 256² VQ too
(D = 61,440), if the mode-select background tolerates it.

**Combinations (against worst measured pair):**

| Config | Arithmetic | Margin |
|---|---|---|
| shrink-3 + D | 8,372,576−196,608+110,592 | 102,048 |
| shrink-3 + D + 2×512² | above −98,304 | 200,352 |
| **shrink-2 + D + 5×512²** | 8,372,576+110,592−245,760 | **151,200 — both heroes full-size** |
| shrink-2 + D alone | 8,372,576+110,592 | −94,560 (insufficient) |

**Effort & risks (why D is not free):**

1. Reverse the LZ enough to *author* streams. Two paths: (a) full
   reverse of the decoder (Ghidra, function near the `0x168ba0`
   string xrefs) — then repack compressed; (b) the all-literal
   shortcut: if flag semantics are as they appear, an all-literal
   stream (`FF` + 8 literals, repeated) is trivially authorable
   without understanding match encoding — costs 9/8 of the payload
   in on-disc bytes.
2. In-place footprint: new entries must fit the original PKTX chunk
   extents. With VQ payloads (≈18 KB vs 131 KB) even all-literal
   streams fit MODESEL's chunk comfortably.
3. Art: mode-select background gains VQ artifacts (menus are
   gradients/flat UI — VQ is usually kind to flat art, and the
   tuner previews it before committing).
4. Control tests required: decode our authored stream with the
   game's own path (emulator leg), byte-compare a repacked-unmodified
   entry round trip first (control), then the VQ versions.
5. One measurement of D so far (Fabian winner); winner-dependent
   variance unquantified — margins should absorb ~±20 KB.

**Related lead (unpriced):** `STGSEL.PAK`'s PKTX holds a **512² raw
16bpp sheet — 524,288 B decoded** (the stage-select screen). If that
sheet stays resident through the match (unknown — needs the
savestate block-list post-mortem or a probe), converting it to VQ
would cut ~456 KB off *every* match peak, dwarfing every other
lever. Worth one investigation before final config choice.

## 5. Recommendation

Two paths depending on appetite for the PKTX work:

- **No reverse-engineering:** Option A (shrink-3 + 7 panels,
  ~194 KB margin). Ships with known tooling this week.
- **Best art:** investigate the STGSEL residency question (one probe
  / savestate post-mortem), then Option D as **shrink-2 + D +
  5×512²** (~151 KB margin, both hero textures untouched) — or
  better if the STGSEL lead pays off.

Either way the panel-selection and any VQ menu art go through the
existing vq_tuner preview flow, and the verification suite in §4
gates the ship ruling.

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

### E. Patch the game: release match textures before the menu load

*(Added 2026-08-26 on the operator's question. The first code patch
in the menu — A–D touch only data; E edits game logic.)*

**Why the game holds the memory:** at the post-match transition the
arena gained exactly +4 blocks and freed none — the game loads the
next scene's textures *before* releasing the old scene's. Frees do
happen (across attract rotations the arena returns to baseline), just
after the next load, not before. On Naomi's 16 MB this is a free
seamless-transition trick; on 8 MB it is the binding constraint.
A plausible precise cause: the free-old-scene step may live in the
**TXTR loader's** preamble (free-then-load) and be missing from the
**PACKTEX loader** — matches (TXTR) never crash, menus (PACKTEX) do.
Ghidra can confirm by comparing the two loaders' entry paths.

**The change:** reorder the game's own teardown, don't write a new
free. Anchors are good: the `MODESEL.PAK` filename-string xref finds
the post-match load call site; the allocator addresses are already
known (the ARENAHW instrumentation hooks them); and the fork can log
the caller PC at the moment arena free-space jumps, locating the
release routine empirically in one leg. Patch = call the game's own
scene-release before the PACKTEX load (move/nop the original call).
Code-injection toolchain already exists (the Cleopatra shim). If the
missing-free-in-PACKTEX theory confirms, the patch is one mirrored
call.

**Effect on the constraint:** removes the +362,496 term entirely —
match-peak budget returns to 8,388,608, and at *every*
menu-after-scene transition (TUTO, ranking, STGSEL — not just
MODESEL), fixing the class of bug rather than the instance. Pure
shrink-2 still fails (worst measured 8,372,576 → 16 KB margin, inside
the ±100 KB residency variance), but e.g. **shrink-2 + E + 3×512²
→ margin 163,488** with both heroes full-size and no menu art touched.

**Risks, ranked:**

1. VRAM side is benign: "freeing" is allocator bookkeeping — texel
   data stays in VRAM until overwritten, so the old scene keeps
   rendering; worst case is transient artifacts on the transition
   frames while the menu's 362 KB lands somewhere in 8 MB.
2. CPU side is the real risk: if the teardown also destroys
   structures the result-screen code still reads (texlists, PAK RAM
   buffers), early teardown crashes. Only reading the code answers
   this.
3. Shared-path: if the reorder lands in a transition routine common
   to all scene changes, ordering changes everywhere — mostly a
   feature (headroom at every transition), but any transition that
   legitimately renders old art during a load gets artifacts.

**Effort:** Ghidra work of the same scale as D's LZ reverse (days,
with good anchors). The same session answers the STGSEL residency
question and the two-loader theory for free.

## 5. Recommendation (superseded — see §6)

Two paths depending on appetite for the PKTX work:

- **No reverse-engineering:** Option A (shrink-3 + 7 panels,
  ~194 KB margin). Ships with known tooling this week.
- **Best art:** investigate the STGSEL residency question (one probe
  / savestate post-mortem), then Option D as **shrink-2 + D +
  5×512²** (~151 KB margin, both hero textures untouched) — or
  better if the STGSEL lead pays off.
- **Best engineering:** one Ghidra recon session prices D, E, and the
  STGSEL lead together (same anchors, same code region). If E's
  two-loader theory confirms, **shrink-2 + E + 3×512²** (~163 KB
  margin) beats every data-only config on art at comparable margin.

## 6. Recon results (2026-08-26) and the revised menu — option F

The recon ran (evidence: `phase5-hardware.md` §Ghidra + savestate recon;
tool: `scripts/texerrsave_postmortem.py`, an offline byte-exact
attribution of every arena block in the crash savestate against the
disc). Three findings restructure the menu:

1. **The PKTX compressor is stock Okumura LZSS** (4096-byte ring,
   LSB-first flags, pos `b1|(b2&0xF0)<<4`, len `(b2&0xF)+3`) —
   re-implemented in python and validated against every PKTX chunk on
   the disc. Authoring repacked entries is trivial (all-literal streams
   always decode; VQ payloads are ~8× smaller than the raw entries they
   replace, so they fit in place with the offset table untouched).
   Option D's only real cost is gone.
2. **STGSEL (and PLSLTX, PLSEL) are NOT resident during matches** — the
   stage-select scene frees its own textures at its task exit. The
   STGSEL lever is dead. (The two resident 512² raw sheets that
   suggested it belong to the characters — see next.)
3. **Every character PAK ships raw 16bpp cut-in portrait art in a PKTX
   chunk, and it stays resident through the whole match**: one 512² raw
   (524,288 B) + one to three 256² raw (131,072 B each) per character —
   655,360 B for P01–P06/P08, 917,504 B for P07 (Ernula). The TXTR-only
   census never saw these. Savestate-proven for both players
   (P01C + P07E at the crash).

**What the portraits are (decoded 2026-08-26, operator eyes-on):** all
22 character-PAK PKTX entries decoded to PNG at
`captures/phase5/textures/portraits/` (gitignored — ROM-derived;
scratchpad `portraits.py`, reuses `scripts/decode_pvr_vq.py`
primitives). Per character: the 512² (ARGB1555, linear) is the **big
pilot cut-in on an alpha cutout** — in-match flash art; the 256²
(ARGB4444, twiddled) is a **full-frame cockpit illustration**. P07's
extra chunk and P10/P11's only PKTX entries are **glow-ring effect
sheets**, not portraits; P09 has no PKTX at all. These are **not** the
character-select portraits: the select screen owns a separate 8.3 MB
PLSEL.PAK with 240 textures of its own — nearly all **already VQ**
(dt=03/04), the game's own precedent for VQ portrait-class art. So the
resident raws are in-match cut-in art, loaded by the match scene from
the character PAK.

### Option F — convert the character portrait PKTX raws to VQ

512² raw → 512² VQ saves 456,704; 256² raw → 256² VQ saves 112,640.
Worst measured pair (Sakurako+Ernula): **−1,363,968 B**. Data-only, the
same splice class as everything else shipped so far; VQ-inside-PKTX is
proven by the game's own PLSLTX content. 48 PAK variants patched by one
script (portrait sheets are shared or per-variant; the repack handles
each PAK independently).

| Config | Arithmetic (worst measured pair) | Margin |
|---|---|---|
| **F-full: portraits + MODESEL→VQ + ALL FOUR 1024² heroes restored to original** | 8,372,576 + 393,216 − 1,363,968 + 110,592 | **876,192** |
| F-lite: portraits only, keep shrink-2, MODESEL untouched | 8,372,576 − 1,363,968 + 362,496 | 1,017,504 |
| F-zero: portraits only + ALL 1024² heroes restored, MODESEL untouched (only the cut-in raws differ from the original disc) | 8,372,576 + 393,216 − 1,363,968 + 362,496 | 624,288 |
| F-full + COMMON's five 256² raw squares | above − 563,200 | 1,439,392 |

Attract worst demo (8,379,424) enjoys the same portrait savings — the
demos load the same character PAKs. The post-match MODESEL constraint is
absorbed by margin alone in every row.

- Art cost: portrait/menu sheets gain VQ artifacts (tuner previews
  before commit; fallback per sheet = 512²→256² **raw**, still −393,216,
  zero VQ artifacts, softer image). **No gameplay texture is reduced
  below original anywhere in F-full** — the operator's tuned 512² heroes
  are no longer needed.
- Not convertible: raw rectangles (256×512, 256×128 — PVR VQ is
  square-only) and the runtime-composed 699 KB atlas. They stay.
- Campaign flag: END1–END4 PAKs carry 0.26–1.05 MB of PKTX art each; if
  the campaign-completion leg shows an END-load overlap like MODESEL's,
  the same converter handles them.
- Stub-out variant (asked 2026-08-26): the same repacker could replace
  a portrait entry with a tiny fully-transparent stub texture instead
  of a VQ re-encode — the loader reads the self-describing record, so
  a 128 B stub loads cleanly and the cut-in simply never appears.
  Saves the full raw size (more than VQ) — but since these are
  in-match cut-ins, not select-screen duplicates, stubbing deletes a
  visible gameplay moment where VQ only softens it. Kept as a
  per-sheet fallback (e.g. if a ring sheet bands badly under VQ), not
  the default.
- Glow-ring caveat: the P07/P10/P11 256² ring sheets are smooth alpha
  gradients — the VQ A/B preview gates them like everything else; if
  they band, excluding P07's two rings costs 2×112,640 per Ernula
  side (only Ernula pairs affected; F-full worst-case margin stays
  positive at 876,192 − 450,560 = 425,632).
- Option E (code patch) is documented in the KB for posterity but
  unnecessary at these margins.

### Recommendation (revised)

**F-full**: repack the 48 character PAKs' PKTX portraits + MODESEL as
VQ, restore all four 1024² stage textures to the untouched originals,
leave COMMON as reserve. ~876 KB margin (~10% of the arena), best art of
any option, one new tool (PKTX repacker with LZSS all-literal writer +
round-trip control test), then the §4 verification suite.

Either way the panel-selection and any VQ menu art go through the
existing vq_tuner preview flow, and the verification suite in §4
gates the ship ruling.

### Decision: F-zero (operator, 2026-08-26) — BUILT, then rejected at the art gate (§7)

The operator chose **F-zero** and the build shipped the same day
(`scripts/pktx_vq.py` + `make_gdi.py`; build record in
`phase5-hardware.md` §F-zero build). 112 PKTX entries repacked across
P01A–P08F + P10/P11 (58 unique sheets — the 512² pilot cut-ins are
**per-variant recolors**, the 256² cockpit sheet is shared across a
character's six variants, the two ring sheets are shared by all P07
variants and P10/P11). PSNR 25.4–41.8 dB; the ring caveat above is
**resolved** — the rings encoded at 40.9/41.8 dB, no banding. Operator
before/after previews: `captures/phase5/textures/portraits-vq/`
(INDEX.txt maps sheets to PAKs). No hero shrink records, MODESEL
untouched. Verification legs (§4 suite, Task 18) pending — no emulator
run at build time by operator instruction.

## 7. The F-zero verification round, the art gate, and the revised F-family (2026-08-26)

### What the F-zero legs measured (evidence: `captures/phase5/fzero-vs.log`)

The F-zero build passed every technical check and produced the first
measurement of the theoretical worst pair:

- Operator VS leg: Ernula(P07C)+Lili(P05F) on STAGE08, then the
  **Ernula mirror** (P07E+P07A) on STAGE08, each played through the
  post-match mode-select transition. TEXERR 49/49 clean post-boot;
  both MODESEL transitions clean; gdread CRC 3,012/3,012 vs the
  F-zero track04.
- **Ernula-mirror peak (first measurement ever): ARENAHW alloc
  7,685,120**, free 703,488, set mid-mirror (log line 924,334). With
  MODESEL's raw 362,496 on top the transition demand is 8,047,616 →
  free 340,992. Every §6 margin model is now replaced by this measured
  baseline: `transition = 7,685,120 + Δ(config) + 362,496 ≤ 8,388,608`.
- Campaign leg aborted mid-run by the operator (partial log kept,
  `fzero-campaign.log`) — see verdict below. END-PAK overlap remains
  unmeasured.

### The art gate verdict (operator, in-game)

1. **The 256² cockpit sheets look awful as VQ in game** — the busy
   glitter/detail content speckles (they were the lowest PSNR family,
   25.4–29.8 dB). Cockpit VQ is rejected.
2. **New rule: textures containing text are not compressed.**

Decoded evidence gathered for the rule
(`captures/phase5/textures/common-modesel/`):

- MODESEL's three raw sheets are **the mode-select menu buttons with
  text** ("VS CPU モード", "ストーリーモード") — the §4-D MODESEL→VQ
  lever is **excluded** by the rule.
- COMMON's five always-resident 256² raw sheets: **four are textless
  effect-sprite atlases** (muzzle flashes, glow orbs, beams; cyan +
  orange variants — VQ previews 30.0–33.8 dB, visually clean) and
  **one carries button icons + the "SP" logo** — excluded.
- The 512² pilot cut-ins (31.5–40.4 dB) and the three glow-ring
  sheets (40.9/41.8 dB) drew no operator objection in the played
  build; both are textless.

### The revised config family (all margins = worst measured point, the Ernula-mirror mode-select transition)

Deltas from the measured F-zero baseline: cockpits back to raw
+225,280 (mirror; +112,640/side); pilots back to raw +913,408 (mirror;
+456,704/side = raw 524,304 − VQ 67,600); rings back to raw +450,560
(mirror); 4 COMMON atlases →VQ −450,560 (global, always resident);
each 1024² STAGE08 hero shrunk to A/B-gated 512² −196,608 (stage-8
scenes — exactly where every ARENAHW all-time max was set; all three
on-disc records verified 2026-08-26: PVRT dt=0x03 pf01 1024², record
264,208 → 67,600, so −196,608 each is exact).

| Config | VQ'd sheets | Also shrunk | Transition demand | Margin |
|---|---|---|---|---|
| F-zero (built, rejected) | pilots + cockpits + rings | — | 8,047,616 | 340,992 |
| 512-only (asked 2026-08-26) | pilots only | — | 8,723,456 | **−334,848 — not viable** (mid-match alone leaves 27,648) |
| pilots+rings only | pilots + rings | — | 8,272,896 | 115,712 — viable on paper, inside the residency-variance band; not recommended |
| **F-1** | pilots + rings + 4 COMMON atlases | — | 7,822,336 | **566,272** |
| **F-2** | pilots + rings | 0b6f67d0 → tuned 512² | 8,076,288 | **312,320** |
| F-1 + shrink-1 | pilots + rings + 4 COMMON atlases | 0b6f67d0 | 7,625,728 | 762,880 (margin-maximizing; likely overkill) |
| **F-3** (all portraits raw) | rings + 4 COMMON atlases | all three heroes (0b6b5fb0, 0b6f67d0, 0b736ff0) | 8,145,920 | **242,688** |

Common to every F-row: all cockpits raw, MODESEL raw, COMMON SP-logo
sheet raw, no text sheet anywhere near VQ. F-2 additionally leaves all
of COMMON raw — the only art delta vs the original disc beyond the
pilot/ring VQ is the one stage texture already through the operator's
own tuned-edit visual gate (§Fix decision era).

### Why partial portrait exemption is impossible (asked 2026-08-26)

The operator judged some VQ'd 512² pilot sheets worse than others and
asked how many could stay raw under F-2. Answer: **zero — and the
count is all-or-nothing, not a budget of N sheets.** Portrait
residency is per-match: only the two in-match sheets occupy the arena
at the transition, so a raw sheet costs nothing globally and
+456,704/side in matches where its character appears. But VS mode
allows any character to face itself, and the measured mirror delta
counted the per-character-shared cockpit sheet **twice** — each side
loads its own copy, no dedup. So exempting even one sheet means its
own mirror match demands +913,408 over baseline; F-2's 312,320 margin
covers not even one raw side. No subset of raw portraits is safe under
F-1/F-2/F-1+shrink-1 — the smallest margin that tolerates raw
portraits at all is 913,408, at which point **every** portrait can be
raw (a match never holds more than two).

**F-3** buys that margin with the two remaining 1024² STAGE08 hero
shrinks (0b6b5fb0, 0b736ff0 — same records already through the Task-17
A/B visual gate alongside 0b6f67d0): pilots raw + cockpits raw + rings
VQ + 4 COMMON atlases VQ + shrink-3 = 7,685,120 + 913,408 + 225,280
− 450,560 − 589,824 + 362,496 = **8,145,920, margin 242,688**. Both
extra shrinks are load-bearing: without them the row is over by
150,528. Cost: thinnest viable margin (~2× the variance band vs F-2's
~3×). Benefit: zero VQ on anything the operator has flagged — every
pilot cut-in and cockpit ships untouched; VQ touches only effect
atlases and glow rings (30.0–41.8 dB, no objections).

Alternative kept in reserve: stay on F-2 and re-encode the worst
sheets harder (P07C 31.5 / P07E 31.6 / P07A 32.2 / P04B 32.7 dB —
single k-means pass, fixed seed today); costs no VRAM, outcome
unproven until previewed.

### Recommendation

**F-3** if the pilot-sheet VQ quality is a no-go (per the operator's
2026-08-26 reaction, it likely is) — everything anyone looks at ships
untouched, at the cost of the thinnest viable margin (242,688, ~2×
band) and two more stage-texture shrinks that already passed their
visual gate. **F-2** if the pilot VQ is tolerable after a second look —
smallest touched-art surface, ~3× band. **F-1** if ~566 KB of cushion
is preferred over leaving COMMON untouched (its four converted atlases
are soft glow sprites, the content class VQ is kindest to; previews on
disk). Verification suite (§4) reruns in full for whichever ships,
including the campaign leg with the END-PAK overlap check.

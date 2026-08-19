# Cart-streaming map — senkosp (Phase 2, measured)

Captured 2026-08-19 (single-day campaign), 14 legs: attract; roster sweep
char-{mika,baek,cuilan,fabian,sakurako,lili,ernula,karel} (char-baek run
with novice=yes); 2p-stages (all 8 stages, one round each); input;
service-retest; testmenu + testmenu2 (service/test-menu walk — RAM TEST
hangs the instrumented fork, see phase2-measurements.md incidents; testmenu2
is the clean re-walk with RAM test skipped) (recipe: tooling.md §Phase 2
capture harness; fork @ `f014a410c`).
Machine-readable: `cart-streaming-map.csv`
(columns `leg,cart_offset,length,dest,mode,above_16m` — append-friendly; top-ups merge+dedup via
`parse_cartlog.py`). 1,592 rows: 1,590 unique DMA tuples + 2 PIO seeks.

## The above-16m map (the port's central problem)

Five contiguous main-RAM corridors sit above the Dreamcast's 16 MB line
(offsets are `dest & 0x1fffffff − 0x0c000000`, the Naomi 32 MB main-RAM
window):

| # | Extent (main offset) | Span size | Bytes streamed (incl. re-streams) | Requests | Cart-offset range | Legs | Character |
|---|---|---|---|---|---|---|---|
| 1 | `0x1244c20`–`0x1d73e00` | 11,727,328 B (11.18 MB) | 201,312,256 B | 151 | `0x00a3a000`–`0x0c271000` | 2p-stages, attract, char-baek, char-cuilan, char-ernula, char-fabian, char-karel, char-lili, char-mika, char-sakurako | Dominant streaming corridor — every roster leg + attract's demo battles. `2p-stages`'s 8-stage sweep extended the floor from `0x145bd20` to `0x1244c20` (+2,191,616 B / ~2.1 MB of new territory the character-only legs never reached). |
| 2 | `0x1d7d020`–`0x1d92020` | 86,016 B | 1,480,704 B | 59 | `0x0095c800`–`0x0c213000` | 2p-stages + all 8 char-* legs (**no attract**) | In-play only — absent from attract's two scripted demo fights, present in every user-played match. |
| 3 | `0x1dc2960`–`0x1de3960` | 135,168 B | 2,666,496 B | 91 | `0x00956000`–`0x0c26d800` | 2p-stages, attract, char-baek, char-cuilan, char-ernula, char-fabian, char-karel, char-lili, char-mika, char-sakurako | Same shape as #1 (in-play + attract), smaller. |
| 4 | `0x1e4dbe0`–`0x1e8b480` | 252,064 B | 47,591,424 B | 1,263 | `0x01ac0800`–`0x0c676000` | 2p-stages, attract, char-baek, char-cuilan, char-ernula, char-lili, char-mika, testmenu2 | Hot re-write ring — 1,263 requests into a 252 KB window (~189× average reuse of the same footprint), the highest request count of any span. 6 of 8 roster legs plus testmenu2's shared boot path; char-fabian/karel/sakurako absent — looks match-length/RNG dependent, not character-gated. |
| 5 | `0x1fe6d20`–`0x1fe7520` | 2,048 B | 49,152 B | 24 | `0x00808000`–`0x00815000` | 2p-stages (dedup artifact — see note) | Boot-time/common load, not leg-specific. |

**Attribution note (span 5, and any span whose leg list looks too short):**
`parse_cartlog.py`'s `merge()` dedups `(src, dest, len)` DMA tuples globally,
first-leg-wins in the order the CLI processes the log files
(`scripts/parse_cartlog.py:146–166`) — this run's `captures/*.log` glob orders legs
alphabetically, so `2p-stages` is parsed first. Span 5 (`0x1fe6d20`–
`0x1fe7520`) is a load every single leg performs at boot; it is credited to
`2p-stages` only because that leg's copy of each tuple is the one that
survived dedup, not because `2p-stages` is special. Read any short "legs:"
list on a low-request-count, small-footprint span as **boot-time/common**,
not leg-specific, unless the span's request count and cart-offset spread
also look boot-sized.

**Narrative:** the unique above-16m destination footprint is 11.64 MB across
the 5 spans, but 253,100,032 B (241.4 MB) of cart-DMA landed in that
footprint over the full campaign — roughly 20.7× the footprint size,
confirming these are genuine re-streamed buffers (assets paged in and out
repeatedly during play), not one-shot boot loads. Spans 2–3 are gameplay-only
(never touched by attract's two scripted demo fights), directly answering
"does real play reach further than the assessment's attract-only capture" —
yes. Span 4's request density shows a small, hot streaming ring rewritten far
more often than its footprint would suggest — likely a per-round or
per-frame buffer, worth identifying by address in Phase 3. Span 1, by far
the largest (11.18 MB, ~201 MB streamed through it), is where the `2p-stages`
leg's stage sweep found real new territory the roster-only legs missed.

## Streaming behavior

Per leg (from the final merged parse):

| Leg | DMA events | DMA bytes | PIO bytes (cumulative) | Main high-water |
|---|---|---|---|---|
| 2p-stages | 727 | 131,260,416 | 0x172538 | 0x1fe7520 |
| attract | 205 | 28,870,656 | 0x172538 | 0x1fe7520 |
| char-baek | 606 | 60,354,560 | 0x172538 | 0x1fe7520 |
| char-cuilan | 493 | 45,985,792 | 0x172538 | 0x1fe7520 |
| char-ernula | 552 | 50,956,288 | 0x172538 | 0x1fe7520 |
| char-fabian | 391 | 53,147,648 | 0x172538 | 0x1fe7520 |
| char-karel | 395 | 42,407,936 | 0x172538 | 0x1fe7520 |
| char-lili | 538 | 49,242,112 | 0x172538 | 0x1fe7520 |
| char-mika | 613 | 69,181,440 | 0x172538 | 0x1fe7520 |
| char-sakurako | 470 | 50,018,304 | 0x172538 | 0x1fe7520 |
| input | 57 | 13,418,496 | 0x172a78 | 0x1fe7520 |
| service-retest | 60 | 5,230,592 | 0x172538 | 0x1fe7520 |
| testmenu | 27 | 1,652,736 | 0x172a78 | 0x1fe7520 |
| testmenu2 | 102 | 6,408,192 | 0x334b70 | 0x1fe7520 |

Every leg's main high-water reads exactly `0x1fe7520` — no leg's peak
destination address exceeded what `attract` alone already reached (only the
low end / floor of span 1 moved, via `2p-stages`; the ceiling never did).

Merged: **1,590 unique DMA tuples**, 2 PIO seeks (1,592 CSV rows). All 1,590
DMA destinations land in the `main` region (0 in vram/aram/ta) — the Naomi
cart interface DMAs into main RAM only; VRAM/ARAM fill via CPU copy from
there, not direct cart DMA. Merged main high-water: `0x1fe7520`
(33,453,344 B / 31.9 MiB) vs the DC's 16 MB line.

**Re-read behavior vs the assessment's attract-only figures:** the v9
assessment's attract capture (`../naomi2dreamcast/assessments/senkosp.md`)
recorded `dma_high_water` 33,453,344 — this campaign's `attract` leg
reproduces it byte-identically (205 events, 28,870,656 B / 27.53 MiB). Summed
across all 14 legs (raw, not deduped — the actual bytes moved over the cart
interface during the whole campaign): 5,236 DMA events, 608,135,168 B
(579.96 MiB) — ~21× attract's own volume. The deduped unique-tuple count
(1,590) is only ~7.8× attract's 205, so most of the extra volume is
re-streaming into already-seen destinations (span 4 above is the clearest
example), not newly discovered content.

## Checks

```
CHECK dest_known: PASS — every DMA dest in a known window (main/vram/aram/ta); 0 outside
CHECK len_aligned_32: PASS — every DMA len a whole number of 0x20-byte DMA_COUNT units
CHECK beyond_boot_read: PASS — at least one cart read past the 1 MB boot region (runtime streaming)
CHECK main_watermark_boot: PASS — main watermark 0x1ffffa5 >= boot-load end 0x191ff8
CHECK attract_anchor: PASS — attract-leg high-water 0x1fe7520 == assessment 0x1fe7520
CHECK merged_hw_bounds: PASS — merged high-water 0x1fe7520 in [attract figure, 32 MB]
```

Command (reproducible from the repo root):

```
python3 scripts/parse_cartlog.py captures/*.log \
    --attract-leg attract --csv docs/kb/cart-streaming-map.csv \
    --hw-report > /tmp/phase2-final-summary.txt; echo "exit=$?"
```

`exit=0`.

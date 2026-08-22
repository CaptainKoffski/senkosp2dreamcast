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

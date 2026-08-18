# Phase 2 — Instrumented Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture senkosp's runtime ground truth — the per-request cart-streaming map with the above-16 MB destination map, gameplay write-truth per RAM region, the input bit map, and serial/RTC/watchdog verdicts — from per-leg instrumented-Flycast runs, parsed into committed KB deliverables.

**Architecture:** Each capture leg is one launch of the already-built instrumented fork with `FLYCAST_CARTLOG=captures/<leg>.log`; a thin wrapper names legs; one stdlib-Python parser merges all legs into the CSV/summaries and enforces the sanity asserts. No fork changes; the user plays all interactive legs, the agent runs the harness and parses between legs.

**Tech Stack:** bash, Python 3 stdlib, instrumented Flycast fork `f014a410c` (prebuilt at `../cleopatra/tools/flycast-src/build/Flycast.app/Contents/MacOS/Flycast`).

**Spec:** `docs/superpowers/specs/2026-08-19-phase2-instrumented-analysis-design.md`

## Global Constraints

- **Fork frozen at `f014a410c`.** No rebuild, no instrumentation changes; a capture gap needing new instrumentation is a spec amendment, not a commit to the fork.
- **Raw logs never committed:** `captures/` is gitignored. Parsed measurements (CSV, md) are committed. Never commit ROMs/BIOS/`.dat`/extracted assets.
- **Python is stdlib-only**; no new dependencies anywhere.
- **Launch gotchas** (from `docs/kb/tooling.md` §Instrumented Flycast) apply to every run: absolute ROM path; `defaults write com.flyinghead.Flycast ApplePersistenceIgnoreState -bool YES`; `-config config:rend.vsync=no`; `pkill -9 -f "flycast-src.*Flycast"` before relaunch.
- **Key constants** (verbatim from spec/assessment): attract-leg main-RAM DMA high-water anchor **33,453,344** (`0x1fe7520`); DC caps main 16 MB / VRAM 8 MB / ARAM 2 MB; carve base `0x8c020000` + 1,515,512 B ⇒ boot-load end at main-RAM offset `0x191ff8`; DMA lengths are whole `0x20`-byte units.

---

### Task 1: Capture-leg launcher + gitignore

**Files:**
- Create: `scripts/capture_leg.sh`
- Modify: `.gitignore` (append one line)

**Interfaces:**
- Produces: `scripts/capture_leg.sh <leg-name>` → runs the fork with `FLYCAST_CARTLOG=$REPO/captures/<leg-name>.log`, refusing to overwrite an existing leg log. All later tasks launch captures only through this script. Extra env (`FLYCAST_SHOT`, `FLYCAST_SHOT_EVERY`) passes through untouched.

- [ ] **Step 1: Write the script**

```bash
#!/bin/bash
# Phase 2 capture-leg launcher: one leg = one instrumented run -> captures/<leg>.log
# Launch gotchas per docs/kb/tooling.md §"Instrumented Flycast".
set -euo pipefail
leg="${1:?usage: capture_leg.sh <leg-name>}"
repo="$(cd "$(dirname "$0")/.." && pwd)"
bin="$repo/../cleopatra/tools/flycast-src/build/Flycast.app/Contents/MacOS/Flycast"
rom="$repo/roms/senkosp.zip"
log="$repo/captures/$leg.log"
mkdir -p "$repo/captures"
# ponytail: legs are primary data — never clobber; rename/delete a bad leg by hand
[ -e "$log" ] && { echo "refusing to overwrite existing $log" >&2; exit 1; }
defaults write com.flyinghead.Flycast ApplePersistenceIgnoreState -bool YES
pkill -9 -f "flycast-src.*Flycast" 2>/dev/null || true
sleep 1
FLYCAST_CARTLOG="$log" exec "$bin" -config config:rend.vsync=no "$rom"
```

- [ ] **Step 2: Gitignore the raw logs**

Append to `.gitignore`:

```
/captures/
```

- [ ] **Step 3: Verify script behavior without launching**

Run: `bash -n scripts/capture_leg.sh && scripts/capture_leg.sh 2>&1; echo "exit=$?"`
Expected: no syntax errors; usage message; `exit=1`.
Then: `chmod +x scripts/capture_leg.sh`, `touch captures/guard-test.log && scripts/capture_leg.sh guard-test; echo "exit=$?"`
Expected: `refusing to overwrite existing .../captures/guard-test.log`, `exit=1`. Clean up: `rm captures/guard-test.log`.

- [ ] **Step 4: Commit**

```bash
git add scripts/capture_leg.sh .gitignore
git commit -m "Phase 2: capture-leg launcher + gitignored captures/"
```

---

### Task 2: Cartlog parser (TDD)

**Files:**
- Create: `scripts/test_parse_cartlog.py` (assert-based, `python3 scripts/test_parse_cartlog.py` prints `ok`)
- Create: `scripts/parse_cartlog.py`

**Interfaces:**
- Consumes: `captures/<leg>.log` files (leg name = basename minus `.log`).
- Produces the CLI every later task uses:
  `python3 scripts/parse_cartlog.py captures/*.log [--csv OUT.csv] [--attract-leg NAME] [--input-report] [--hw-report]`
  — prints the summary to stdout, exits nonzero if any CHECK fails.
- Produces functions the test consumes: `parse_leg(name: str, text: str) -> dict`, `merge(legs: list) -> list[dict]` (row dicts: `leg,src,len,dest,mode,region,above_16m`), `main_hw(dmas) -> int`, `checks(legs, rows, attract=None) -> list[(name, ok, detail)]`, `high_map(rows) -> list`, `input_report(legs) -> str`, `write_csv(rows, path)`.
- Adapted from `../cleopatra/scripts/parse_cart_log.py`; line formats are ground truth from the fork source (cited in the docstring below). Not copied wholesale: Cleopatra's Phase 3/4 checks (SHIMWATCH, fn-range PC checks) don't apply here.

- [ ] **Step 1: Write the failing test**

`scripts/test_parse_cartlog.py`:

```python
#!/usr/bin/env python3
"""Self-check for parse_cartlog.py — synthetic two-leg logs, every line type."""
import os
import tempfile

import parse_cartlog as P

# Attract leg: high-water lands exactly on the assessment anchor 33,453,344
# (0x0dfe0000 -> main offset 0x1fe0000; + len 0x7520 = 0x1fe7520 = 33,453,344).
ATTRACT = """\
MAINHANDOFF baselined size=2000000 trigger=dma
CARTDMA src=00100000 dest=0c020000 len=100000
CARTDMA src=00200000 dest=0dfe0000 len=7520
CARTDMA src=00300000 dest=04400000 len=20
CARTPIO offset=00000000
CARTPIO offset=00150000
CARTPIOCNT bytes=100
CARTPIOCNT bytes=8000
WATERMARK region=main used=192100 size=2000000
WATERMARK region=main used=1920f8 size=2000000
MAINPROFILE high=1fe7520 nz=100 nz_below16m=60 nz_above16m=40 size=2000000
MAINPROFILE high=1fe7520 nz=90 nz_below16m=60 nz_above16m=30 size=2000000
MAINHIST a 0 5
MAINHIST 1 7 2
ARAMPROFILE high=50 nz=50 nz_below2m=50 nz_above2m=0 content_high=40 content_below2m=40 content_above2m=0 size=800000
ARAMREBASE armrst size=800000
ARAMPROFILE high=10 nz=10 nz_below2m=10 nz_above2m=0 content_high=8 content_below2m=8 content_above2m=0 size=800000
VRAMPROFILE high=900000 nz=200 nz_below8m=150 nz_above8m=50 content_high=880000 content_below8m=140 content_above8m=40 fb_bytes=96000 fb_masked_nz=20 size=1000000
VRAMHIST 3 0 0 9
VRAMREGS isp_base=400000 isp_limit=6200e0 ol_base=6d5680 ol_limit=6201e0 fb_w_sof1=6ea000 fb_w_sof2=c00000 fb_r_sof1=6ea000
SERIALPOKE addr=1fe80004 data=00000041
HWW pc=0c021230 addr=00710004 val=00000001
HWR pc=0c021230 addr=00710004 val=00000001
HWW pc=0c021230 addr=00710004 val=00000001
"""

# Second leg: a duplicate DMA tuple (must dedup), a new above-16m DMA, and an
# overlap with the attract anchor span (must merge in high_map).
PLAY = """\
CARTDMA src=00200000 dest=0dfe0000 len=7520
CARTDMA src=00400000 dest=0d000000 len=40
CARTDMA src=00500000 dest=0dfe0000 len=8000
JVSREPORT buttons=0000
JVSREPORT buttons=0040
JVSREPORT buttons=0000
MIERESP sub=15 addr=0c30fe00 data=00ffff
MIERESP sub=15 addr=0c30fe00 data=00ffff
MIERESP sub=15 addr=0c30fe00 data=00fffe
MIERESP sub=15 addr=0c30fe00 data=00ffff
MIERESP sub=01 addr=0c30fe00 data=aa55
"""

a = P.parse_leg("attract", ATTRACT)
b = P.parse_leg("play", PLAY)

# per-leg parse
assert len(a["dma"]) == 3 and a["pio"] == {0x0, 0x150000}
assert a["pio_bytes"] == 0x8000                      # CARTPIOCNT: last wins
assert a["wm"]["main"] == 0x192100                   # watermark: max wins
assert a["prof"]["main"]["nz"] == 0x100              # profile fields (hex): running max
assert a["hist"]["main"] == [10, 7, 5]               # hist: elementwise max
assert a["prof"]["aram"]["nz"] == 0x10               # ARAMREBASE restarts running max
assert a["prof"]["vram"]["fb_bytes"] == 0x96000
assert a["regs"].startswith("isp_base=400000")
assert len(a["serial"]) == 1
assert a["hw"] == {("W", 0x710004): 2, ("R", 0x710004): 1}
assert [m["sub"] for m in b["mie"]] == [0x15] * 4 + [0x01]

# merge + flags
rows = P.merge([a, b])
dma_rows = [r for r in rows if r["mode"] == "DMA"]
assert len(dma_rows) == 5                            # dup tuple deduped
anchor = [r for r in dma_rows if r["src"] == 0x200000][0]
assert anchor["leg"] == "attract" and anchor["above_16m"]
assert [r for r in dma_rows if r["src"] == 0x400000][0]["above_16m"]  # 0x1000000+0x40 crosses
assert not [r for r in dma_rows if r["src"] == 0x100000][0]["above_16m"]
vram_row = [r for r in dma_rows if r["src"] == 0x300000][0]
assert vram_row["region"] == "vram" and not vram_row["above_16m"]
assert len([r for r in rows if r["mode"] == "PIO"]) == 2

# high-water + anchor checks
assert P.main_hw(a["dma"]) == 33453344
cks = dict((n, ok) for n, ok, _ in P.checks([a, b], rows, attract=a))
assert cks["dest_known"] and cks["len_aligned_32"] and cks["beyond_boot_read"]
assert cks["main_watermark_boot"]                    # 0x192100 >= 0x191ff8
assert cks["attract_anchor"] and cks["merged_hw_bounds"]

# broken data must fail the right checks
bad = P.parse_leg("bad", "CARTDMA src=00000000 dest=0c000000 len=21\n"
                          "CARTDMA src=00000000 dest=1e000000 len=20\n")
bck = dict((n, ok) for n, ok, _ in P.checks([bad], P.merge([bad])))
assert not bck["len_aligned_32"] and not bck["dest_known"]
assert not bck["beyond_boot_read"] and not bck["main_watermark_boot"]

# high-address map: distinct spans stay separate; overlapping spans merge
# (0x1fe0000+0x7520 and 0x1fe0000+0x8000 collapse into one 0x1fe0000..0x1fe8000)
hm = P.high_map(rows)
assert len(hm) == 2 and hm[0][0] == 0x1000000
assert hm[1][0] == 0x1fe0000 and hm[1][1] == 0x1fe8000
assert hm[1][2] == 0x7520 + 0x8000 and hm[1][3] == {"attract", "play"}

# input report: exactly one changed bit per transition, popcount visible
rep = P.input_report([b])
assert "leg play" in rep and "byte2 bit0-" in rep and "bits-vs-baseline: 1" in rep
assert "JVS" in rep and "0040" in rep

# CSV
with tempfile.TemporaryDirectory() as d:
    path = os.path.join(d, "map.csv")
    P.write_csv(rows, path)
    lines = open(path).read().splitlines()
    assert lines[0] == "leg,cart_offset,length,dest,mode,above_16m"
    assert "attract,0x00200000,0x7520,0x0dfe0000,DMA,1" in lines

print("ok")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scripts && python3 test_parse_cartlog.py`
Expected: `ModuleNotFoundError: No module named 'parse_cartlog'`

- [ ] **Step 3: Write the parser**

`scripts/parse_cartlog.py`:

```python
#!/usr/bin/env python3
"""Phase 2 cartlog parser — merges per-leg capture logs into the cart-streaming
map (+ above-16m flags), region write-truth, and device verdicts.

Adapted from ../cleopatra/scripts/parse_cart_log.py. Line formats are ground
truth from the instrumented fork (../flycast4naomi2dreamcast @ f014a410c):
  CARTDMA src=%08x dest=%08x len=%x          core/hw/naomi/naomi.cpp
  CARTPIO offset=%08x                        core/hw/naomi/naomi_cart.cpp:1020
  CARTPIOCNT bytes=%llx                      cumulative PIO bytes, per ~10 s sample
  WATERMARK region=%s used=%x size=%x        content scan (stale-data prone)
  MAINPROFILE high= nz= nz_below16m= nz_above16m= size=          write-truth
  MAINHIST <hex per 256 KB bucket>           bucket 64+ = past 16 MB
  VRAMPROFILE ... content_* fb_bytes= fb_masked_nz= size=
  VRAMHIST <hex>                             bucket 32+ = past 8 MB
  VRAMREGS isp_base= ... fb_r_sof1=
  ARAMPROFILE ... content_* size=
  ARAMHIST <hex>                             bucket 8+ = past 2 MB
  ARAMREBASE armrst size=%x                  running max restarts here (fork v4)
  SERIALPOKE addr=%08x data=%08x             naomi.cpp:120
  MIERESP sub=%02x addr=%08x data=<hex>      maple_if.cpp:292
  JVSREPORT buttons=%04x                     maple_jvs.cpp:2241 (P1 digital word)
  HW[RW] pc=%08x addr=%08x val=%08x          addrspace.cpp:136 (game-code MMIO)

Usage:
  parse_cartlog.py captures/*.log [--csv OUT.csv] [--attract-leg NAME]
                   [--input-report] [--hw-report]
Exit: nonzero if any CHECK fails.
"""
import argparse
import os
import re
import sys

MAIN_LO, MAIN_HI = 0x0c000000, 0x0e000000   # Naomi 32 MB main-RAM window (phys)
DC_MAIN_CAP = 0x01000000                    # DC 16 MB line (offset in window)
VRAM_LO, VRAM_HI = 0x04000000, 0x06000000   # PVR VRAM, 64-bit + 32-bit windows
ARAM_LO, ARAM_HI = 0x00800000, 0x01000000   # AICA sound RAM window
TA_LO, TA_HI = 0x10000000, 0x10800000       # TA FIFO
BOOT_END = 0x00100000                       # 1 MB cart boot region
CARVE_END = 0x00020000 + 1515512            # boot-load end, main offset (game.md)
ATTRACT_HW = 33453344                       # assessment dma_high_water (senkosp.md §4)
BUCK = 0x40000                              # 256 KB histogram buckets (fork naomi.cpp)

# device tags, physical (addr & 0x1FFFFFFF) — same ranges as the static guts
# scan (../naomi2dreamcast/tools/assess/ghidra/GutsMetrics.java)
DEVICES = (("rtc", 0x00710000, 0x0071FFFF), ("scif", 0x1FE80000, 0x1FE8FFFF))

_DMA = re.compile(r"^CARTDMA src=([0-9a-f]+) dest=([0-9a-f]+) len=([0-9a-f]+)", re.I)
_PIO = re.compile(r"^CARTPIO offset=([0-9a-f]+)", re.I)
_PIOCNT = re.compile(r"^CARTPIOCNT bytes=([0-9a-f]+)", re.I)
_WM = re.compile(r"^WATERMARK region=(\w+) used=([0-9a-f]+) size=([0-9a-f]+)", re.I)
_PROF = re.compile(r"^(MAIN|VRAM|ARAM)PROFILE (.+)$")
_HIST = re.compile(r"^(MAIN|VRAM|ARAM)HIST (.*)$")
_REGS = re.compile(r"^VRAMREGS (.+)$")
_SER = re.compile(r"^SERIALPOKE addr=([0-9a-f]+) data=([0-9a-f]+)", re.I)
_MIE = re.compile(r"^MIERESP sub=([0-9a-f]+) addr=([0-9a-f]+) data=([0-9a-f]*)", re.I)
_JVS = re.compile(r"^JVSREPORT buttons=([0-9a-f]+)", re.I)
_HW = re.compile(r"^HW([A-Z]) pc=([0-9a-f]+) addr=([0-9a-f]+) val=([0-9a-f]+)", re.I)


def _kv(s):
    return {k: int(v, 16) for k, v in (p.split("=") for p in s.split())}


def region_of(dest):
    p = dest & 0x1fffffff
    if MAIN_LO <= p < MAIN_HI:
        return "main", p - MAIN_LO
    if VRAM_LO <= p < VRAM_HI:
        return "vram", p - VRAM_LO
    if ARAM_LO <= p < ARAM_HI:
        return "aram", p - ARAM_LO
    if TA_LO <= p < TA_HI:
        return "ta", p - TA_LO
    return "other", p


def parse_leg(name, text):
    leg = {"name": name, "dma": [], "pio": set(), "pio_bytes": 0, "wm": {},
           "prof": {}, "hist": {}, "regs": None, "serial": [], "mie": [],
           "jvs": [], "hw": {}}
    for line in text.splitlines():
        m = _DMA.match(line)
        if m:
            src, dest, ln = (int(g, 16) for g in m.groups())
            leg["dma"].append({"src": src, "dest": dest, "len": ln})
            continue
        m = _PIO.match(line)
        if m:
            leg["pio"].add(int(m.group(1), 16))
            continue
        m = _PIOCNT.match(line)
        if m:
            leg["pio_bytes"] = int(m.group(1), 16)   # cumulative: last wins
            continue
        m = _WM.match(line)
        if m:
            r, used = m.group(1), int(m.group(2), 16)
            leg["wm"][r] = max(leg["wm"].get(r, 0), used)
            continue
        if line.startswith("ARAMREBASE"):
            # fork v4: baseline re-snapshotted at an AICA ARM reset; samples
            # before the LAST rebase measured BIOS test residue — restart max
            leg["prof"].pop("aram", None)
            leg["hist"].pop("aram", None)
            continue
        m = _PROF.match(line)
        if m:
            r, fields = m.group(1).lower(), _kv(m.group(2))
            prev = leg["prof"].get(r, {})
            leg["prof"][r] = {k: max(v, prev.get(k, 0)) for k, v in fields.items()}
            continue
        m = _HIST.match(line)
        if m:
            r = m.group(1).lower()
            counts = [int(x, 16) for x in m.group(2).split()]
            prev = leg["hist"].get(r, [])
            prev += [0] * (len(counts) - len(prev))
            leg["hist"][r] = [max(c, p) for c, p in zip(counts, prev)]
            continue
        m = _REGS.match(line)
        if m:
            leg["regs"] = m.group(1)
            continue
        m = _SER.match(line)
        if m:
            leg["serial"].append((int(m.group(1), 16), int(m.group(2), 16)))
            continue
        m = _MIE.match(line)
        if m:
            leg["mie"].append({"sub": int(m.group(1), 16),
                               "data": bytes.fromhex(m.group(3)) if m.group(3) else b""})
            continue
        m = _JVS.match(line)
        if m:
            leg["jvs"].append(int(m.group(1), 16))
            continue
        m = _HW.match(line)
        if m:
            key = (m.group(1).upper(), int(m.group(3), 16))
            leg["hw"][key] = leg["hw"].get(key, 0) + 1
            continue
    return leg


def merge(legs):
    """Dedup DMA tuples across legs (first leg wins attribution) + PIO rows."""
    rows, seen = [], set()
    for leg in legs:
        for d in leg["dma"]:
            key = (d["src"], d["dest"], d["len"])
            if key in seen:
                continue
            seen.add(key)
            reg, off = region_of(d["dest"])
            rows.append({"leg": leg["name"], "src": d["src"], "len": d["len"],
                         "dest": d["dest"], "mode": "DMA", "region": reg,
                         "above_16m": reg == "main" and off + d["len"] > DC_MAIN_CAP})
    pio_first = {}
    for leg in legs:
        for off in sorted(leg["pio"]):
            pio_first.setdefault(off, leg["name"])
    for off, name in sorted(pio_first.items()):
        rows.append({"leg": name, "src": off, "len": 0, "dest": 0, "mode": "PIO",
                     "region": "", "above_16m": False})
    return rows


def main_hw(dmas):
    return max((region_of(d["dest"])[1] + d["len"] for d in dmas
                if region_of(d["dest"])[0] == "main"), default=0)


def checks(legs, rows, attract=None):
    dma_rows = [r for r in rows if r["mode"] == "DMA"]
    other = [r for r in dma_rows if r["region"] == "other"]
    out = [("dest_known", bool(dma_rows) and not other,
            f"every DMA dest in a known window (main/vram/aram/ta); {len(other)} outside"),
           ("len_aligned_32", bool(dma_rows) and all(r["len"] % 0x20 == 0 for r in dma_rows),
            "every DMA len a whole number of 0x20-byte DMA_COUNT units"),
           ("beyond_boot_read", any(r["src"] >= BOOT_END for r in rows),
            "at least one cart read past the 1 MB boot region (runtime streaming)")]
    wm_main = max((l["wm"].get("main", 0) for l in legs), default=0)
    out.append(("main_watermark_boot", wm_main >= CARVE_END,
                f"main watermark 0x{wm_main:x} >= boot-load end 0x{CARVE_END:x}"))
    if attract is not None:
        a_hw = main_hw(attract["dma"])
        merged_hw = main_hw(dma_rows)
        out.append(("attract_anchor", a_hw == ATTRACT_HW,
                    f"attract-leg high-water 0x{a_hw:x} == assessment 0x{ATTRACT_HW:x}"))
        out.append(("merged_hw_bounds", ATTRACT_HW <= merged_hw <= 0x02000000,
                    f"merged high-water 0x{merged_hw:x} in [attract figure, 32 MB]"))
    return out


def high_map(rows):
    """Above-16m main-RAM placements merged into contiguous [lo, hi) intervals:
    [lo, hi, total_bytes, {legs}, [cart_offsets]]."""
    spans = sorted([region_of(r["dest"])[1], region_of(r["dest"])[1] + r["len"],
                    r["len"], {r["leg"]}, [r["src"]]]
                   for r in rows if r["above_16m"])
    merged = []
    for s in spans:
        if merged and s[0] <= merged[-1][1]:
            m = merged[-1]
            m[1] = max(m[1], s[1])
            m[2] += s[2]
            m[3] |= s[3]
            m[4].extend(s[4])
        else:
            merged.append(s)
    return merged


def input_report(legs):
    """Collapse consecutive identical MIE sub=15 payloads / JVS words; print
    transitions with changed bits — the input map reads straight off this."""
    lines = []
    for leg in legs:
        payloads = [m["data"] for m in leg["mie"] if m["sub"] == 0x15 and m["data"]]
        if payloads:
            base = prev = payloads[0]
            lines.append(f"== input report: leg {leg['name']} "
                         f"({len(payloads)} MIE polls, baseline {base.hex()})")
            for p in payloads[1:]:
                if p == prev:
                    continue
                n = min(len(p), len(prev), len(base))
                diff = [f"byte{i} bit{b}" + ("+" if p[i] >> b & 1 else "-")
                        for i in range(n) for b in range(8)
                        if (p[i] ^ prev[i]) >> b & 1]
                nbits = sum(bin(p[i] ^ base[i]).count("1") for i in range(n))
                lines.append(f"{p.hex()}  vs-prev: {' '.join(diff)}  "
                             f"bits-vs-baseline: {nbits}")
                prev = p
        if leg["jvs"]:
            base = prev = leg["jvs"][0]
            lines.append(f"== JVS report: leg {leg['name']} "
                         f"({len(leg['jvs'])} words, baseline {base:04x})")
            for w in leg["jvs"][1:]:
                if w == prev:
                    continue
                lines.append(f"{w:04x}  changed-vs-prev: {w ^ prev:04x}  "
                             f"bits-vs-baseline: {bin(w ^ base).count('1')}")
                prev = w
    return "\n".join(lines)


def hw_report(legs):
    """Game-code MMIO pokes grouped by (rw, addr), device-tagged."""
    agg = {}
    for leg in legs:
        for key, n in leg["hw"].items():
            agg[key] = agg.get(key, 0) + n
    lines = []
    for (rw, addr), n in sorted(agg.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        p = addr & 0x1fffffff
        tag = next((name for name, lo, hi in DEVICES if lo <= p <= hi), "other")
        lines.append(f"HW{rw} addr=0x{addr:08x} [{tag}] x{n}")
    serial = sum(len(l["serial"]) for l in legs)
    lines.append(f"SERIALPOKE lines: {serial}")
    return "\n".join(lines)


def write_csv(rows, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write("leg,cart_offset,length,dest,mode,above_16m\n")
        for r in sorted(rows, key=lambda r: (r["mode"], r["src"], r["dest"])):
            f.write(f"{r['leg']},0x{r['src']:08x},0x{r['len']:x},0x{r['dest']:08x},"
                    f"{r['mode']},{int(r['above_16m'])}\n")


def summary(legs, rows, check_list):
    dma_rows = [r for r in rows if r["mode"] == "DMA"]
    lines = ["== per leg =="]
    for l in legs:
        lines.append(f"{l['name']}: {len(l['dma'])} DMA events, "
                     f"{sum(d['len'] for d in l['dma'])} B, "
                     f"pio_bytes=0x{l['pio_bytes']:x}, "
                     f"main_hw=0x{main_hw(l['dma']):x}")
    lines.append("== merged ==")
    lines.append(f"unique DMA tuples: {len(dma_rows)}  "
                 f"PIO seeks: {len(rows) - len(dma_rows)}")
    per_reg = {}
    for r in dma_rows:
        per_reg[r["region"]] = per_reg.get(r["region"], 0) + 1
    lines.append("DMA dests by region: "
                 + ", ".join(f"{k}={v}" for k, v in sorted(per_reg.items())))
    lines.append(f"merged main high-water: 0x{main_hw(dma_rows):x} "
                 f"({main_hw(dma_rows) / 1048576:.1f} MB) vs DC 16 MB")
    lines.append("== above-16m map (main-RAM offsets) ==")
    for lo, hi, total, legset, srcs in high_map(rows):
        lines.append(f"0x{lo:07x}..0x{hi:07x}  {total} B in {len(srcs)} requests  "
                     f"cart 0x{min(srcs):08x}..0x{max(srcs):08x}  "
                     f"legs: {','.join(sorted(legset))}")
    lines.append("== regions (write-truth, merged running max) ==")
    caps = {"main": ("nz_above16m", 16), "vram": ("content_above8m", 8),
            "aram": ("content_above2m", 2)}
    for reg, (above_key, cap_mb) in caps.items():
        best = {}
        for l in legs:
            for k, v in l["prof"].get(reg, {}).items():
                best[k] = max(v, best.get(k, 0))
        if best:
            lines.append(f"{reg}: " + " ".join(f"{k}=0x{v:x}" for k, v in best.items())
                         + f"  [{above_key} vs {cap_mb} MB cap]")
        hist = []
        for l in legs:
            h = l["hist"].get(reg, [])
            hist = [max(a, b) for a, b in
                    zip(h + [0] * (len(hist) - len(h)),
                        hist + [0] * (len(h) - len(hist)))]
        cap_bucket = cap_mb * 1048576 // BUCK
        above = [(i, n) for i, n in enumerate(hist) if i >= cap_bucket and n]
        lines.append(f"{reg} above-cap buckets (256 KB each): "
                     + (", ".join(f"#{i}(0x{i * BUCK:x})={n}" for i, n in above)
                        if above else "none"))
    lines.append("== checks ==")
    for name, ok, detail in check_list:
        lines.append(f"CHECK {name}: {'PASS' if ok else 'FAIL'} — {detail}")
    return "\n".join(lines)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--csv")
    ap.add_argument("--attract-leg")
    ap.add_argument("--input-report", action="store_true")
    ap.add_argument("--hw-report", action="store_true")
    args = ap.parse_args(argv)
    legs = [parse_leg(os.path.splitext(os.path.basename(p))[0],
                      open(p, encoding="utf-8", errors="replace").read())
            for p in args.logs]
    rows = merge(legs)
    attract = next((l for l in legs if l["name"] == args.attract_leg), None)
    if args.attract_leg and attract is None:
        print(f"attract leg '{args.attract_leg}' not among logs", file=sys.stderr)
        return 2
    check_list = checks(legs, rows, attract=attract)
    if args.csv:
        write_csv(rows, args.csv)
    print(summary(legs, rows, check_list))
    if args.input_report:
        print(input_report(legs))
    if args.hw_report:
        print(hw_report(legs))
    return 0 if all(ok for _, ok, _ in check_list) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scripts && python3 test_parse_cartlog.py`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add scripts/parse_cartlog.py scripts/test_parse_cartlog.py
git commit -m "Phase 2: cartlog parser + self-check (above-16m map, anchors)"
```

---

### Task 3: Attract leg — capture, anchor check, recipe recorded

No player needed — the agent runs this leg alone, end to end.

**Files:**
- Create: `captures/attract.log` (gitignored, stays local)
- Modify: `docs/kb/tooling.md` (append capture recipe section)

**Interfaces:**
- Consumes: `scripts/capture_leg.sh`, `scripts/parse_cartlog.py` (Tasks 1–2).
- Produces: the attract leg log that every later parse includes; the recorded capture recipe.

- [ ] **Step 1: Launch the attract leg in the background**

```bash
scripts/capture_leg.sh attract &
```

Optional visual check: prefix with `FLYCAST_SHOT=$PWD/captures/attract-shot.png FLYCAST_SHOT_EVERY=600` (env passes through).

- [ ] **Step 2: Wait out one full attract cycle, then stop**

Boot-to-handoff is ~20 s and the full attract cycle fits in 600 s (assessment v9 observed the whole loop in a 600 s capture). Wait 660 s total, then:

```bash
sleep 660
pkill -9 -f "flycast-src.*Flycast"
```

- [ ] **Step 3: Parse and verify the anchor**

Run: `python3 scripts/parse_cartlog.py captures/attract.log --attract-leg attract; echo "exit=$?"`
Expected: summary with `CHECK attract_anchor: PASS`, all other checks PASS, `exit=0`.
If `attract_anchor` FAILs low, the attract cycle wasn't complete — delete the log and re-run with a longer wait; if it FAILs high, stop and investigate (the capture saw more than v9's attract did — do NOT loosen the check).

- [ ] **Step 4: Record the capture recipe in tooling.md**

Append to `docs/kb/tooling.md`:

```markdown
### Phase 2 capture harness

- **One leg = one run:** `scripts/capture_leg.sh <leg-name>` →
  `captures/<leg-name>.log` (gitignored; primary data — the script refuses
  to overwrite an existing leg). Instrumentation is env-gated
  (`FLYCAST_CARTLOG`, `core/hw/naomi/cartlog.cpp`); same build as Phase 1,
  fork frozen at `f014a410c`.
- **Parse/merge:** `python3 scripts/parse_cartlog.py captures/*.log
  [--csv docs/kb/cart-streaming-map.csv] [--attract-leg attract]
  [--input-report] [--hw-report]` — exits nonzero on any failed CHECK.
  Self-check: `cd scripts && python3 test_parse_cartlog.py` → `ok`.
- **Attract leg (2026-08-19):** 660 s unattended (`sleep 660; pkill -9 -f
  "flycast-src.*Flycast"`), anchor `attract_anchor` PASS — attract
  high-water reproduces the assessment's 33,453,344.
- Profile scans (32 MB main + 16 MB VRAM + 8 MB ARAM byte-diffs) fire every
  ~600 vblanks (~10 s, `core/hw/naomi/naomi.cpp` cartlog_sample) — a brief
  periodic stutter during play is the instrument, not the game.
```

- [ ] **Step 5: Commit**

```bash
git add docs/kb/tooling.md
git commit -m "Phase 2: attract leg captured, anchor reproduced; capture recipe recorded"
```

---

### Task 4: Input leg + input-map.md

**User at the controls** for the press sequence; agent launches, parses, writes the map.

**Files:**
- Create: `captures/input.log` (local), `docs/kb/input-map.md`

**Interfaces:**
- Consumes: Tasks 1–2 tooling.
- Produces: `docs/kb/input-map.md` — the Phase 3/4 input-shim ground truth.

- [ ] **Step 1: Confirm control bindings in Flycast**

Before capturing, open Flycast Settings → Controls and note the physical keys/pad buttons bound to: stick directions, the 5 game buttons, Start, Coin (Insert Card/Coin), Test, Service. Record the bindings — they go into input-map.md so the leg is reproducible.

- [ ] **Step 2: Launch and run the press sequence**

```bash
scripts/capture_leg.sh input &
```

User protocol (on the title/attract screen, ~1 s hold, ~1 s gap, this order):
**Up, Down, Left, Right, M, S, A, Barrage (C), OverDrive, Start, Coin, Test, Service.**
Test enters the test menu — that's fine, it's last; exit the menu, then close Flycast (or agent runs `pkill -9 -f "flycast-src.*Flycast"`).
Note: Coin adds a credit and Start (pressed before Coin) does nothing without one — intended; the order keeps the game on the attract screen for the whole sequence.

- [ ] **Step 3: Parse and read the mapping**

Run: `python3 scripts/parse_cartlog.py captures/input.log --input-report`
Expected: a transition list where each held control shows `bits-vs-baseline: 1` (plus its release back to 0). A control that flips zero or many bits ⇒ the decode is wrong — re-run the leg before writing anything.

- [ ] **Step 4: Write docs/kb/input-map.md**

Structure (values filled from the report — 13 control rows, MIE byte/bit and JVS bit per row):

```markdown
# Input map — senkosp (Phase 2, measured)

Captured 2026-08-19, leg `captures/input.log` (recipe: tooling.md §Phase 2
capture harness). Source lines: `MIERESP sub=15` (MIE input response,
maple_if.cpp:292) cross-checked against `JVSREPORT` (P1 JVS digital word,
maple_jvs.cpp:2241), instrumented fork @ f014a410c.

Neutral MIE sub=15 baseline: `<hex>`

| Control | Flycast binding used | MIE sub=15 byte.bit | JVS word bit |
|---|---|---|---|
| Up | ... | byteN bitM | 0x0040 |
| ... (13 rows: U, D, L, R, M, S, A, Barrage/C, OverDrive, Start, Coin, Test, Service) |

Sanity: every row = exactly one changed bit vs neutral (input leg report,
`bits-vs-baseline: 1` per hold).
```

- [ ] **Step 5: Commit**

```bash
git add docs/kb/input-map.md
git commit -m "Phase 2: input map measured — 13 controls to MIE/JVS bits"
```

---

### Task 5: Roster sweep legs + coverage checklist

**User plays**; agent launches each leg, parses after each, reports coverage and new above-16m spans. Spans multiple sittings — the per-leg files make that free.

**Files:**
- Create: `captures/char-<name>.log` per character, `captures/novice.log` (local)
- Create: `docs/kb/phase2-measurements.md` (started here: coverage checklist; completed in Task 7)

**Interfaces:**
- Consumes: Tasks 1–2 tooling.
- Produces: the play-leg logs; the coverage checklist that gates the phase.

- [ ] **Step 1: Enumerate the roster and stages from the game itself**

Launch the first sweep leg (`scripts/capture_leg.sh char-<first> &`). At the character-select screen, the user reads out (or screenshots via `FLYCAST_SHOT`) the full roster; same for the stage-select list. Agent creates `docs/kb/phase2-measurements.md` with:

```markdown
# Phase 2 measurements — senkosp

## Coverage checklist (gate)

Roster (from the character-select screen, leg char-<first>, 2026-08-19):
- [ ] <character 1> (leg char-<slug>)
- [ ] ... one row per character shown on the select screen
Stages (from stage select): one row per stage, checked when seen in any leg.
- [ ] Novice-mode run (leg novice)
- [ ] Test-menu leg (Task 6)
- [ ] Input leg (Task 4)

(Region verdicts + device verdicts land here in Task 7.)
```

- [ ] **Step 2: Play the sweep, one leg per character**

Per character: `scripts/capture_leg.sh char-<slug> &`; user picks that character, plays to game over including the continue screen, varying the stage/music pick each run; agent pkills, then parses all legs so far:

```bash
python3 scripts/parse_cartlog.py captures/*.log --attract-leg attract
```

After each leg: tick the character (and any newly seen stage/opponents) in the checklist; report any new above-16m spans to the user. Repeat until every roster row and stage row is ticked. One of the runs is `captures/novice.log` played in Novice mode.

- [ ] **Step 3: Commit the growing checklist as sittings complete**

```bash
git add docs/kb/phase2-measurements.md
git commit -m "Phase 2: roster sweep progress — coverage checklist updated"
```

(One commit per sitting is fine; the raw legs stay local.)

---

### Task 6: Test-menu leg

**User drives the menu walk**; agent parses for device evidence.

**Files:**
- Create: `captures/testmenu.log` (local)

**Interfaces:**
- Consumes: Tasks 1–2 tooling.
- Produces: the EEPROM/RTC/serial runtime evidence Task 7 records as verdicts.

- [ ] **Step 1: Capture the menu walk**

```bash
scripts/capture_leg.sh testmenu &
```

User: press Test to enter the service menu; walk every screen including bookkeeping and game settings; flip ONE harmless setting (e.g. demo sound), exit (which persists settings), re-enter to confirm, restore the original value, exit. Agent pkills.

- [ ] **Step 2: Parse for device activity**

Run: `python3 scripts/parse_cartlog.py captures/testmenu.log --hw-report`
Expected: the HW/serial report — rtc/scif-tagged pokes if the game touches them, MIE EEPROM subcommands visible in the summary's MIERESP list (sub 0x01/0x03/0x0B are EEPROM ops — Cleopatra parser note). Record raw counts; interpretation is Task 7's verdict lines, decisions are Phase 3.

- [ ] **Step 3: Tick the checklist and commit**

Tick "Test-menu leg" in `docs/kb/phase2-measurements.md`; commit as in Task 5 Step 3.

---

### Task 7: Final merge — deliverables, gate, status

**Files:**
- Create: `docs/kb/cart-streaming-map.md`, `docs/kb/cart-streaming-map.csv`
- Modify: `docs/kb/phase2-measurements.md` (complete it), `docs/kb/00-status.md`

**Interfaces:**
- Consumes: all leg logs + parser.
- Produces: the Phase 2 gate evidence; Phase 3's inputs.

- [ ] **Step 1: Final full parse — everything must PASS**

```bash
python3 scripts/parse_cartlog.py captures/*.log \
    --attract-leg attract --csv docs/kb/cart-streaming-map.csv \
    --hw-report > /tmp/phase2-final-summary.txt; echo "exit=$?"
```

Expected: `exit=0` (every CHECK PASS). A FAIL here blocks the gate — fix the capture (or find the real cause), never the assert.

- [ ] **Step 2: Write cart-streaming-map.md**

From the final summary, leading with the high-address map (spec: "summary leads with the high-address map"):

```markdown
# Cart-streaming map — senkosp (Phase 2, measured)

Captured 2026-08-19..<end date>, legs: attract, char-*, novice, testmenu,
input (recipe: tooling.md §Phase 2 capture harness; fork @ f014a410c).
Machine-readable: cart-streaming-map.csv (leg,cart_offset,length,dest,mode,
above_16m — append-friendly; top-ups merge+dedup via parse_cartlog.py).

## The above-16m map (the port's central problem)

<the "above-16m map" summary section verbatim: each contiguous main-RAM
interval past 0x1000000 — extent, bytes, request count, cart-offset range,
contributing legs — plus 2-3 sentences of narrative: how many streams,
boot-time vs in-play, which matchups pull them in>

## Streaming behavior

<per-leg + merged tables from the summary: events, bytes, high-water,
PIO volume; re-read behavior vs the assessment's attract-only figures>

## Checks

<the CHECK lines, all PASS, verbatim>
```

- [ ] **Step 3: Complete phase2-measurements.md**

Fill the remaining sections from the final summary + hw-report:

```markdown
## Region verdicts (write-truth, all legs merged)

| Region | Attract-only (assessment v9) | Full campaign | DC cap | Verdict |
|---|---|---|---|---|
| main nz / above-16m | 5,850,229 / 4,266,292 | <measured> | 16 MB | <fits as content / relocation needed for N streams> |
| vram content+2×fb / above-8m | 4,786,768 / 3,017,926 | <measured> | 8 MB | <...> |
| aram content / above-2m | 1,348,105 / 0 | <measured> | 2 MB | <expected: still fits> |

Above-cap bucket maps (256 KB buckets, offsets): <the "above-cap buckets"
lines — the relocation source map for Phase 3>

## Device verdicts (runtime)

| Device | Evidence | Verdict |
|---|---|---|
| serial (SCIF) | SERIALPOKE + scif-tagged HW lines: <counts, legs> | <touched/not; shim or ignore — decision Phase 3> |
| RTC | rtc-tagged HW lines: <counts, which legs (test menu?)> | <...> |
| watchdog | <any non-main/other-tagged pokes or none> | <...> |
| EEPROM | MIERESP sub 0x01/0x03/0x0B seen in: <legs> | <BIOS-path confirmed; Phase 3 traces the fn> |
```

Every number copied from parser output, none typed from memory. Tick the last checklist rows.

- [ ] **Step 4: Advance 00-status.md**

Update `docs/kb/00-status.md`: Phase 2 marked DONE with date; "Key facts" gains the headline numbers (merged high-water, count + total size of above-16m streams, region verdicts, device verdicts); "Next step" becomes Phase 3 (reverse engineering: touchpoint addresses + relocation strategy, brainstorm + spec first), pointing at the three new KB files as its inputs.

- [ ] **Step 5: Gate check against the spec's exit criteria**

Verify each of the six exit criteria in the spec (§Exit criteria) is met, quoting evidence (file + check line) for each. Any miss ⇒ back to the relevant task.

- [ ] **Step 6: Commit**

```bash
git add docs/kb/cart-streaming-map.md docs/kb/cart-streaming-map.csv \
        docs/kb/phase2-measurements.md docs/kb/00-status.md
git commit -m "Phase 2 complete: gate green — streaming/memory/input/device ground truth captured"
```

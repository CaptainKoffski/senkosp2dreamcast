#!/usr/bin/env python3
"""Phase 2 cartlog parser — merges per-leg capture logs into the cart-streaming
map (+ above-16m flags), region write-truth, and device verdicts.

Adapted from ../cleopatra/scripts/parse_cart_log.py. Line formats are ground
truth from the instrumented fork (../flycast4naomi2dreamcast @ 6e3522822):
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
  CARTDMAPC pc=%08x sp=%08x                  naomi.cpp:468-470, follows CARTDMA
  MAPLEPC cmd=86 sub=%02x pc=%08x trig=%s sp=%08x   maple_jvs.cpp caller PC + r15 +
                                              DoDma trigger ("reg" guest SB_MDST store,
                                              attributable; "vbl" hardware vblank
                                              trigger, not), Phase 3/4
  SPWATER min=%08x max=%08x                  naomi.cpp, r15 water-mark across maple
                                              transactions (MDODMA/MAPLEPC), ~10s cadence,
                                              Phase 4. Whole-run aggregate — may include
                                              activity from unidentified call sites outside
                                              any confirmed function; not load-bearing for
                                              sp_consistent (see pc_checks), kept for
                                              diagnostics/summary.
  BIOSEXEC pc=%08x                           PC observed executing in BIOS window
  SHIMWATCH2 addr=%08x was=%02x now=%02x     naomi.cpp cartlog_shimwatch2(), senkosp shim-home
                                              (0x8c010000-0x8c018000) baseline-vs-content diff,
                                              same 64-DMA/10s cadence, Phase 4 Task 2

Usage:
  parse_cartlog.py captures/*.log [--csv OUT.csv] [--attract-leg NAME]
                   [--input-report] [--hw-report]
                   [--cart-fn LO-HI[,LO-HI]] [--input-fn LO-HI[,LO-HI]]
                   [--eeprom-fn LO-HI[,LO-HI]] [--stack LO-HI[,LO-HI]]
                   [--pc-report] [--dryrun ANCHOR.log]
Exit: nonzero if any CHECK fails.
"""
import argparse
import collections
import os
import re
import sys

MAIN_LO, MAIN_HI = 0x0c000000, 0x0e000000   # Naomi 32 MB main-RAM window (phys)
DC_MAIN_CAP = 0x01000000                    # DC 16 MB line (offset in window)
DC_VRAM_CAP = 0x00800000                    # DC 8 MB VRAM line (content_high / SOF regs)
VRAM_SOF_MASK = 0x00fffffc                  # SOF regs carry low-bit flags — mask before compare
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
_DMAPC = re.compile(r"^CARTDMAPC pc=([0-9a-f]+) sp=([0-9a-f]+)", re.I)
# trig=/sp= are optional so pre-Phase-4 logs (no trigger tag, no SP) still
# parse; missing trig groups to "?", not "reg" — an untagged line must never
# silently count as an attributable one.
_MPC = re.compile(
    r"^MAPLEPC cmd=86 sub=([0-9a-f]+) pc=([0-9a-f]+)(?: trig=(\w+))?(?: sp=([0-9a-f]+))?", re.I)
_SPWATER = re.compile(r"^SPWATER min=([0-9a-f]+) max=([0-9a-f]+)", re.I)
_BIOS = re.compile(r"^BIOSEXEC pc=([0-9a-f]+)", re.I)
_SHIM2 = re.compile(r"^SHIMWATCH2 addr=([0-9a-f]+) was=([0-9a-f]+) now=([0-9a-f]+)", re.I)
_SOFWR = re.compile(r"^SOFWR (\w+) val=([0-9a-f]+)", re.I)


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
           "prof": {}, "hist": {}, "regs": None, "vramregs": [], "serial": [],
           "mie": [], "jvs": [], "hw": {}, "dmapc": [], "pcpairs": [],
           "maplepc": [], "biosexec": [], "sofwr": collections.Counter(),
           "spwater": None, "shimwatch2": []}
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
            leg["regs"] = m.group(1)          # last-wins (kept for back-compat)
            leg["vramregs"].append(m.group(1))   # every snapshot, in order
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
        m = _DMAPC.match(line)
        if m:
            pc, sp = int(m.group(1), 16), int(m.group(2), 16)
            leg["dmapc"].append((pc, sp))
            if leg["dma"]:   # CARTDMAPC immediately follows its CARTDMA (naomi.cpp:468-470)
                d = leg["dma"][-1]
                leg["pcpairs"].append((d["src"], d["dest"], d["len"], pc, sp))
            continue
        m = _MPC.match(line)
        if m:
            leg["maplepc"].append((int(m.group(1), 16), int(m.group(2), 16),
                                   m.group(3) or "?",
                                   int(m.group(4), 16) if m.group(4) else None))
            continue
        m = _SPWATER.match(line)
        if m:
            lo, hi = int(m.group(1), 16), int(m.group(2), 16)
            if leg["spwater"] is None:
                leg["spwater"] = (lo, hi)
            else:
                leg["spwater"] = (min(leg["spwater"][0], lo), max(leg["spwater"][1], hi))
            continue
        m = _BIOS.match(line)
        if m:
            leg["biosexec"].append(int(m.group(1), 16))
            continue
        m = _SHIM2.match(line)
        if m:
            leg["shimwatch2"].append((int(m.group(1), 16), int(m.group(2), 16), int(m.group(3), 16)))
            continue
        m = _SOFWR.match(line)
        if m:
            leg["sofwr"][m.group(1).lower()] += 1
            continue
    return leg


def merge(legs):
    """Dedup DMA tuples across legs (first leg wins attribution) + PIO rows.

    Attribution of a deduped tuple = whichever leg is first in `legs`, i.e.
    first on the CLI (glob order) — keep leg naming/glob order stable across
    top-up captures, or shared-tuple attribution in the CSV will churn.
    """
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


def _ranges(s):
    """Parse 'LO-HI[,LO-HI]' (P1 hex, no 0x) into [(lo, hi), ...]."""
    out = []
    for part in s.split(","):
        lo, hi = part.split("-")
        out.append((int(lo, 16), int(hi, 16)))
    return out


def _in(ranges, pc):
    return any(lo <= pc <= hi for lo, hi in ranges)


def _bios_check(legs):
    bios = [p for l in legs for p in l["biosexec"]]
    return ("no_bios_exec", not bios, f"{len(bios)} BIOSEXEC lines (expect 0)")


# O1 (spec): the planned senkosp shim home 0x8c010000-0x8c018000 must stay
# clean of game-runtime writes (cartlog_shimwatch2(), naomi.cpp). Safety
# tripwire like no_bios_exec — unconditional, no flags needed.
def _shimwatch_check(legs):
    hits = [h for l in legs for h in l["shimwatch2"]]
    return ("shim_home_clean", not hits, f"{len(hits)} SHIMWATCH2 lines (expect 0)")


# boot-binary.md "SP — two stacks, not one" / "Why three checks cannot pass
# as written": maple_DoDma() has two callers — a guest SB_MDST store (trig=
# reg, Sh4cntx.pc is the attributable call-site PC) and the hardware vblank
# trigger (trig=vbl, Sh4cntx.pc is just wherever the main loop was that tick).
# Only trig=reg lines carry a PC worth checking against a function range.
#
# TASK_SP_FLOOR / sp_consistent provenance (Phase 4 Task 1 fork-probe capture,
# captures/phase4/pc2.log, cross-checked against a 45s per-event-sp diagnostic
# capture — docs/kb/boot-binary.md §SP water-mark, Task 1 follow-up): a naive
# whole-run SPWATER aggregate does NOT cleanly bound the task cluster — it is
# dragged down by an unidentified additional PC family (phys ~0x0c0316xx-
# 0x0c0320xx, all trig=reg) running at SP ~0x0cbffdc4-0x0cbfff9c, a THIRD
# region distinct from both confirmed stacks. Per-PC correlation (same
# diagnostic capture) shows the CONFIRMED input/eeprom function
# (FUN_8c02532a, pc=8c025448) samples at a constant sp=8c1d4a1c, and the
# CONFIRMED boot-time device-scan function (FUN_8c0665fe, pc=8c066728 et al.)
# samples inside the confirmed boot-stack range (0x8c00efa4-0x8c00efd8) — so
# the sound floor check is the one scoped to events already independently
# confirmed by input_pc_in_input_fn/eeprom_*_seen (trig=reg, pc in
# input_fn/eeprom_fn), not the unscoped SPWATER min. SPWATER itself is still
# emitted/parsed (kept for diagnostics — see the SPWATER docstring entry
# above) but is not load-bearing here.
TASK_SP_FLOOR = 0x8c1c0000   # second-stack floor; boot-binary.md §SP, Task 10 resolution


def pc_checks(legs, cart_fn, input_fn, eeprom_fn, stack):
    out = [_bios_check(legs)]
    dmapc = [p for l in legs for p, _ in l["dmapc"]]
    if cart_fn:
        out.append(("dma_pc_in_cart_fn", all(_in(cart_fn, p) for p in dmapc),
                    f"{len(dmapc)} DMA-kick PCs vs cart fn"))
    if input_fn:
        pcs = [p for l in legs for s, p, trig, _ in l["maplepc"] if s == 0x15 and trig == "reg"]
        out.append(("input_pc_in_input_fn", bool(pcs) and all(_in(input_fn, p) for p in pcs),
                    f"{len(pcs)} sub=15 trig=reg PCs vs input fn"))
    if eeprom_fn:
        rd = [p for l in legs for s, p, trig, _ in l["maplepc"] if s in (0x01, 0x03) and trig == "reg"]
        wr = [p for l in legs for s, p, trig, _ in l["maplepc"] if s == 0x0b and trig == "reg"]
        out.append(("eeprom_read_seen", bool(rd) and all(_in(eeprom_fn, p) for p in rd),
                    f"{len(rd)} sub=01/03 trig=reg PCs vs eeprom fn"))
        out.append(("eeprom_write_seen", bool(wr) and all(_in(eeprom_fn, p) for p in wr),
                    f"{len(wr)} sub=0b trig=reg PCs vs eeprom fn"))
    # sp_consistent: two-stack model (boot-binary.md §SP). Boot cluster = dmapc
    # SPs (CARTDMAPC, cart-kick events) below the task-stack floor; must sit in
    # the static stack region. Task cluster = SPs sampled at trig=reg MAPLEPC
    # events whose PC is already confirmed by input_fn/eeprom_fn (see provenance
    # note above) — its floor must never dip below TASK_SP_FLOOR.
    sps = [sp for l in legs for _, sp in l["dmapc"]]
    if sps:
        if stack:
            boot_sps = [sp for sp in sps if sp < TASK_SP_FLOOR]
            fn_ranges = (input_fn or []) + (eeprom_fn or [])
            task_sps = [sp for l in legs for s, p, trig, sp in l["maplepc"]
                       if trig == "reg" and sp is not None and _in(fn_ranges, p)]
            task_min = min(task_sps) if task_sps else None
            ok = (bool(boot_sps) and all(_in(stack, sp) for sp in boot_sps)
                  and task_min is not None and task_min >= TASK_SP_FLOOR)
            det = (f"{len(boot_sps)} boot-cluster SPs vs {stack}; "
                   f"{len(task_sps)} task-cluster (fn-confirmed) SPs, min="
                   + (f"0x{task_min:x}" if task_min is not None else "(none)")
                   + f" vs floor 0x{TASK_SP_FLOOR:x}")
        else:
            ok = max(sps) - min(sps) < 0x100000
            det = f"SP spread {max(sps) - min(sps):#x} (< 1 MB heuristic)"
        out.append(("sp_consistent", ok, det))
    return out


# FB_W_SOF2's never-written BIOS default (relocation-map.md §Dry-run evidence
# ruling; cites ../cleopatra/tools/flycast-src/core/hw/naomi/naomi.cpp:256-258:
# "31 kHz progressive parks the field-2 pointer at 0xc00000" — masked, so
# this exact value costs nothing when nothing was ever written there).
FB_W_SOF2_BIOS_DEFAULT = 0x00c00000


def dryrun_checks(legs, rows, anchor):
    """Phase 3 dry-run gate checks (--dryrun ANCHOR.log): run against the
    CLI-provided legs/rows, judged against an anchor leg parsed the same way
    but never merged in. Reuses the Phase 2 prof/regs/rows structures — no
    re-regexing."""
    main_over = [r for r in rows if r["mode"] == "DMA" and r["above_16m"]]
    main_high = max((l["prof"].get("main", {}).get("high", 0) for l in legs), default=0)
    out = [("dryrun_main_below_16m",
            not main_over and main_high < DC_MAIN_CAP,
            f"{len(main_over)} main DMA(s) with dest+len above 16m; "
            f"MAINPROFILE high=0x{main_high:x} (cap 0x{DC_MAIN_CAP:x})")]

    vram_high = max((l["prof"].get("vram", {}).get("content_high", 0) for l in legs), default=0)
    sof_bad = []
    for l in legs:
        # Every VRAMREGS snapshot in leg order, not just the last (the old
        # last-value read was an accidental under-sample: a leg that starts
        # above cap and settles could still spuriously FAIL or PASS purely
        # on which sample happened to land last).
        series_by_reg = {}
        for snap in l["vramregs"]:
            for k, v in _kv(snap).items():
                if k in ("fb_w_sof1", "fb_w_sof2", "fb_r_sof1"):
                    series_by_reg.setdefault(k, []).append(v & VRAM_SOF_MASK)
        above8m = l["prof"].get("vram", {}).get("nz_above8m", 0) != 0
        for k, series in series_by_reg.items():
            if max(series) < DC_VRAM_CAP:
                continue   # never above cap for this register in this leg
            above_idx = [i for i, v in enumerate(series) if v >= DC_VRAM_CAP]
            below_idx = [i for i, v in enumerate(series) if v < DC_VRAM_CAP]
            # Ruling A (relocation-map.md): FB_W_SOF2 stuck at the never-
            # written BIOS default for the WHOLE leg is exempt iff it was
            # written exactly once (no genuine placement re-targeted it) and
            # nothing was ever written above 8m. naomi.cpp:256-258.
            ruling_a = (k == "fb_w_sof2" and set(series) == {FB_W_SOF2_BIOS_DEFAULT}
                       and l["sofwr"].get("fb_w_sof2", 0) == 1 and not above8m)
            # Boot-transient ruling (mirrors ruling A): a one-way handoff —
            # every above-cap snapshot comes strictly before every below-cap
            # snapshot (settles once, never regresses back above cap) — is
            # exempt iff nothing was ever written above 8m. Evidence: the
            # pre-handoff VRAMREGS snapshots are a deterministic boot
            # artifact (identical file lines across all three dry-run legs)
            # that a single FB_W_SOF1/FB_R_SOF1 write pair (pc=8c032140)
            # supersedes for the rest of the leg — see relocation-map.md
            # §Dry-run evidence. A late/regressed above-cap snapshot (any
            # above-cap index after the first below-cap one) is NOT exempt.
            settles = bool(below_idx) and max(above_idx) < min(below_idx)
            if ruling_a or (settles and not above8m):
                continue
            sof_bad.append(f"{l['name']}:{k}=0x{max(series):x} "
                           f"({len(above_idx)}/{len(series)} snapshots above cap)")
    out.append(("dryrun_vram_below_8m",
                vram_high < DC_VRAM_CAP and not sof_bad,
                f"VRAMPROFILE content_high=0x{vram_high:x} (cap 0x{DC_VRAM_CAP:x}); "
                f"{len(sof_bad)} SOF reg(s) above cap and not exempt {sof_bad[:5]}"))

    # Shape (ruling B): the multiset comparison is like-for-like only against
    # the FIRST leg on the CLI (the dry-run attract leg, same 660 s window as
    # the anchor) — same "first leg" convention merge() already uses for CLI
    # order. Any further legs (e.g. the play leg) have no anchor to compare
    # against — interactive play has no fixed shape — so they're reported
    # informationally only and never fail this check. A capture-truncation
    # multiset mismatch is NOT auto-passed here — the plan's own provision
    # ("record the set-equality result + the boundary explanation... rather
    # than forcing a re-run loop") is a manual judgment call a human makes
    # in relocation-map.md on a FAIL, not something the gate silently waves
    # through.
    shape_leg = legs[0] if legs else None   # tolerate an empty legs list
    exempt_legs = legs[1:]
    shape_name = shape_leg["name"] if shape_leg else "(no legs)"
    prov = collections.Counter((d["src"], d["len"]) for d in (shape_leg["dma"] if shape_leg else []))
    anc = collections.Counter((d["src"], d["len"]) for d in anchor["dma"])
    shape_ok = prov == anc
    if shape_ok:
        detail = (f"{shape_name}: {sum(anc.values())} (src,len) events match "
                  f"the anchor leg's multiset")
    else:
        extra = [(f"0x{s:x}", f"0x{n:x}", c) for (s, n), c in list((prov - anc).items())[:5]]
        missing = [(f"0x{s:x}", f"0x{n:x}", c) for (s, n), c in list((anc - prov).items())[:5]]
        detail = (f"{shape_name}: multiset differs vs anchor '{anchor['name']}': "
                  f"provided-only(first5 src,len,count)={extra} "
                  f"anchor-only(first5 src,len,count)={missing}")
    if exempt_legs:
        detail += ("; exempt from shape (no anchor for interactive play, caps-only): "
                   + ", ".join(l["name"] for l in exempt_legs))
    out.append(("dryrun_stream_shape", shape_ok, detail))
    return out


def pc_report(legs):
    """Merged: dedup on the printed (dest, pc, sp) triple, first occurrence wins
    (Task 10's corridor->PC join needs unique pairs, not raw per-leg duplicates)."""
    seen = set()
    lines = []
    for l in legs:
        for _, dest, _, pc, sp in l["pcpairs"]:
            key = (dest, pc, sp)
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"PCPAIR dest={dest:08x} pc={pc:08x} sp={sp:08x}")
    return "\n".join(lines)


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
    ap.add_argument("--cart-fn", help="LO-HI[,LO-HI] P1 hex, no 0x")
    ap.add_argument("--input-fn", help="LO-HI[,LO-HI] P1 hex, no 0x")
    ap.add_argument("--eeprom-fn", help="LO-HI[,LO-HI] P1 hex, no 0x")
    ap.add_argument("--stack", help="LO-HI[,LO-HI] P1 hex, no 0x")
    ap.add_argument("--pc-report", action="store_true")
    ap.add_argument("--dryrun", metavar="ANCHOR.log",
                    help="parse ANCHOR.log as an extra leg (not merged) and add the "
                         "dryrun_main_below_16m/dryrun_vram_below_8m/dryrun_stream_shape "
                         "checks, run against the logs given on the command line")
    args = ap.parse_args(argv)
    legs = [parse_leg(os.path.splitext(os.path.basename(p))[0],
                      open(p, encoding="utf-8", errors="replace").read())
            for p in args.logs]
    rows = merge(legs)
    attract = next((l for l in legs if l["name"] == args.attract_leg), None)
    if args.attract_leg and attract is None:
        print(f"attract leg '{args.attract_leg}' not among logs", file=sys.stderr)
        return 2
    cart_fn = _ranges(args.cart_fn) if args.cart_fn else None
    input_fn = _ranges(args.input_fn) if args.input_fn else None
    eeprom_fn = _ranges(args.eeprom_fn) if args.eeprom_fn else None
    stack = _ranges(args.stack) if args.stack else None
    check_list = checks(legs, rows, attract=attract)
    # no_bios_exec / shim_home_clean are safety tripwires: they run on every
    # parse, flags or not.
    check_list.append(_bios_check(legs))
    check_list.append(_shimwatch_check(legs))
    if cart_fn or input_fn or eeprom_fn or stack:
        # The other PC checks stay flag-gated: sp_consistent's 1 MB heuristic
        # false-FAILs on merged dynarec-relocated PCs across ordinary legs, and
        # the fn-range checks are meaningless without a range to test against.
        check_list += [c for c in pc_checks(legs, cart_fn, input_fn, eeprom_fn, stack)
                       if c[0] != "no_bios_exec"]
    if args.dryrun:
        anchor_leg = parse_leg(os.path.splitext(os.path.basename(args.dryrun))[0],
                               open(args.dryrun, encoding="utf-8", errors="replace").read())
        check_list += dryrun_checks(legs, rows, anchor_leg)
    all_pass = all(ok for _, ok, _ in check_list)
    if args.csv:
        if all_pass:
            write_csv(rows, args.csv)
        else:
            print(f"CHECK failure — not writing {args.csv} "
                  f"(a committed CSV must never be overwritten with bad data)",
                  file=sys.stderr)
    print(summary(legs, rows, check_list))
    if args.input_report:
        print(input_report(legs))
    if args.hw_report:
        print(hw_report(legs))
    if args.pc_report:
        print(pc_report(legs))
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

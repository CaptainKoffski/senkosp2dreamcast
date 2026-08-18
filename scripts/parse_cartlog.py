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

#!/usr/bin/env python3
"""Digest SHIMTIME lines from a serial (or emulator) leg -- phase-7 T2.

The shim (shims/src/gd.c, SHIM_TIME=1) prints one line per delivered cart
read:

    SHIMTIME tcr=00000002                       # once, and on any change
    SHIMTIME o=<cart off> l=<len> s=<TCNT0 at entry> d=<entry - exit ticks>

TCNT0 is the game's own TMU0: a free-running DOWN-counter, TCOR0=0xFFFFFFFF
(~92 min wrap at TCR0=2 -- docs/kb/phase7-polishing.md §T1 measurements, TMU0
verdict). This script rebuilds the read timeline and answers the T2
attribution questions:

  - per read: when (ms from first read), in-driver ms, implied KB/s;
  - gaps between reads = game-side time (unpack/render), so bursts of reads
    separated by >GAP_MS ms become "windows" with a driver duty cycle;
  - re-read churn: identical (offset,len) tuples delivered more than once =
    the eviction-then-reload signature (a texture the game re-streams).

Usage: parse_shimtime.py <leg.log> [--gap-ms N]
"""
import re
import sys

MASK = 0xFFFFFFFF
RESET_S = 3600          # a gap this long = TMU0 was reprogrammed, re-anchor
GAP_MS = 250.0          # burst boundary: game-side gap longer than this

# SH-4 TMU TCR.TPSC -> peripheral-clock (50 MHz) divider. 5..7 are
# external/reserved clocks the DC never uses for TMU0 here.
TPSC_DIV = {0: 4, 1: 16, 2: 64, 3: 256, 4: 1024}

LINE = re.compile(r"SHIMTIME o=([0-9a-f]{8}) l=([0-9a-f]{8})"
                  r" s=([0-9a-f]{8}) d=([0-9a-f]{8})")
TCR = re.compile(r"SHIMTIME tcr=([0-9a-f]{8})")


def parse(text):
    """-> (tick_hz, reads); reads = [(off, ln, s, d), ...] in log order."""
    tick_hz, reads = None, []
    for line in text.splitlines():
        m = TCR.search(line)
        if m:
            tpsc = int(m.group(1), 16) & 7
            if tpsc not in TPSC_DIV:
                sys.exit(f"TCR0 TPSC={tpsc}: external/reserved clock, "
                         "cannot convert ticks")
            tick_hz = 50_000_000 / TPSC_DIV[tpsc]
            continue
        m = LINE.search(line)
        if m:
            reads.append(tuple(int(g, 16) for g in m.groups()))
    return tick_hz, reads


def timeline(tick_hz, reads):
    """-> [{off,len,start_ms,dur_ms,gap_ms}, ...]; gap_ms None on re-anchor.

    start_ms is elapsed from the first read. Down-counter: later stamps are
    SMALLER, so elapsed-between = (earlier - later) & MASK, wrap-safe."""
    out, t_ms = [], 0.0
    per_ms = tick_hz / 1000.0
    reset_ticks = RESET_S * tick_hz
    prev_s = prev_d = None
    for off, ln, s, d in reads:
        gap = None
        if prev_s is not None:
            dt = (prev_s - s) & MASK              # entry-to-entry ticks
            if dt < reset_ticks:
                t_ms += dt / per_ms
                gap = (dt - prev_d) / per_ms      # minus prev in-driver time
            # else: TMU0 reprogram (or >1 h idle) -- re-anchor, gap unknown
        out.append({"off": off, "len": ln, "start_ms": t_ms,
                    "dur_ms": d / per_ms, "gap_ms": gap})
        prev_s, prev_d = s, d
    return out


def bursts(tl, gap_ms=GAP_MS):
    """Group reads whose game-side gap <= gap_ms (None starts a new group)."""
    groups, cur = [], []
    for r in tl:
        if cur and (r["gap_ms"] is None or r["gap_ms"] > gap_ms):
            groups.append(cur)
            cur = []
        cur.append(r)
    if cur:
        groups.append(cur)
    return groups


def churn(tl):
    """-> {(off,len): count} for tuples delivered more than once."""
    seen = {}
    for r in tl:
        seen[(r["off"], r["len"])] = seen.get((r["off"], r["len"]), 0) + 1
    return {k: n for k, n in seen.items() if n > 1}


def report(tick_hz, tl, gap_ms):
    if not tl:
        print("no SHIMTIME read lines found")
        return
    total_b = sum(r["len"] for r in tl)
    drv_ms = sum(r["dur_ms"] for r in tl)
    span_ms = tl[-1]["start_ms"] + tl[-1]["dur_ms"] - tl[0]["start_ms"]
    print(f"tick rate {tick_hz:,.0f} Hz | {len(tl)} reads | "
          f"{total_b:,} B | span {span_ms/1000:.1f} s | "
          f"in-driver {drv_ms/1000:.2f} s"
          + (f" (duty {100*drv_ms/span_ms:.1f}%)" if span_ms else ""))

    print(f"\nbursts (game-side gap > {gap_ms:.0f} ms splits):")
    print("   start_s  wall_ms  drv_ms  duty%   reads      bytes   drvKB/s")
    for g in bursts(tl, gap_ms):
        wall = g[-1]["start_ms"] + g[-1]["dur_ms"] - g[0]["start_ms"]
        drv = sum(r["dur_ms"] for r in g)
        byt = sum(r["len"] for r in g)
        kbs = byt / 1024 / (drv / 1000) if drv else 0
        duty = 100 * drv / wall if wall else 100.0
        print(f"  {g[0]['start_ms']/1000:8.1f} {wall:8.0f} {drv:7.0f} "
              f"{duty:6.1f} {len(g):7d} {byt:10,} {kbs:9,.0f}")

    ch = churn(tl)
    rep_b = sum(off_len[1] * (n - 1) for off_len, n in ch.items())
    print(f"\nre-read churn: {len(ch)} tuples re-delivered, "
          f"{rep_b:,} repeated bytes")
    for (off, ln), n in sorted(ch.items(), key=lambda kv: -kv[0][1] * (kv[1]-1))[:10]:
        print(f"  o={off:08x} l={ln:08x} x{n}")


def main(argv):
    if not argv or len(argv) > 3:
        sys.exit(__doc__)
    gap_ms = GAP_MS
    if "--gap-ms" in argv:
        i = argv.index("--gap-ms")
        gap_ms = float(argv[i + 1])
        del argv[i:i + 2]
    with open(argv[0], errors="replace") as f:
        tick_hz, reads = parse(f.read())
    if tick_hz is None:
        sys.exit("no SHIMTIME tcr= line -- is this a SHIM_TIME=1 leg?")
    report(tick_hz, timeline(tick_hz, reads), gap_ms)


if __name__ == "__main__":
    main(sys.argv[1:])

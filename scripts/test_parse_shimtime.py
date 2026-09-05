#!/usr/bin/env python3
"""Self-check for parse_shimtime.py -- synthetic log, exact tick math.

TCR0=2 -> P/64 = 781,250 Hz -> 781.25 ticks/ms. The counter counts DOWN.
"""
import parse_shimtime as p


def hexline(o, ln, s, d):
    return f"SHIMTIME o={o:08x} l={ln:08x} s={s:08x} d={d:08x}"


HZ = 781_250
T = HZ * 4 // 1000          # 3125 ticks = 4 ms exactly

s1 = 0xF0000000
s2 = (s1 - T - 25 * T) & 0xFFFFFFFF          # gap 100 ms after read1's end
s3 = (s2 - T - 2 * T) & 0xFFFFFFFF           # gap 8 ms after read2's end
s4 = 0x00000100                               # near zero...
s5 = (s4 - T - 2 * T) & 0xFFFFFFFF           # ...so read5's stamp wraps

LOG = "\n".join([
    "noise line",
    "SHIMTIME tcr=00000002",
    hexline(0x1000, 0x800, s1, T),            # read1: 4 ms
    hexline(0x2000, 0x800, s2, T),            # read2: gap 100 ms
    hexline(0x1000, 0x800, s3, T),            # read3: gap 8 ms, churn of read1
    hexline(0x9000, 0x800, s4, T),            # read4: huge dt -> re-anchor
    hexline(0xa000, 0x800, s5, T),            # read5: stamp wrapped past 0
])

tick_hz, reads = p.parse(LOG)
assert tick_hz == HZ, tick_hz
assert len(reads) == 5, reads

tl = p.timeline(tick_hz, reads)
assert abs(tl[0]["dur_ms"] - 4.0) < 1e-9
assert tl[0]["gap_ms"] is None                       # first read anchors
assert abs(tl[1]["gap_ms"] - 100.0) < 1e-9
assert abs(tl[2]["gap_ms"] - 8.0) < 1e-9
assert tl[3]["gap_ms"] is None                       # re-anchor on reset
assert abs(tl[4]["gap_ms"] - 8.0) < 1e-9             # wrap-safe delta
assert abs(tl[2]["start_ms"] - (4 + 100 + 4 + 8)) < 1e-9
assert tl[3]["start_ms"] == tl[2]["start_ms"]        # reset adds no time

# burst grouping: gap 100 ms splits at threshold 50, joins at 250; the
# re-anchor before read4 always splits.
assert [len(g) for g in p.bursts(tl, 250.0)] == [3, 2]
assert [len(g) for g in p.bursts(tl, 50.0)] == [1, 2, 2]

ch = p.churn(tl)
assert ch == {(0x1000, 0x800): 2}, ch

print("ok")

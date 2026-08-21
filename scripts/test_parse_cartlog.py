#!/usr/bin/env python3
"""Self-check for parse_cartlog.py — synthetic two-leg logs, every line type."""
import contextlib
import io
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

# PC layer: CARTDMAPC/MAPLEPC/BIOSEXEC lines + pc_checks() + --pc-report join
PCLEG = """\
CARTDMA src=00200000 dest=0dfe0000 len=7520
CARTDMAPC pc=8c03bd28 sp=8cffff00
CARTDMA src=00300000 dest=0d244c20 len=100
CARTDMAPC pc=8c03bd30 sp=8cfffef0
MAPLEPC cmd=86 sub=15 pc=8c031600
MAPLEPC cmd=86 sub=01 pc=8c032000
MAPLEPC cmd=86 sub=0b pc=8c032100
"""

legs = [P.parse_leg("pc", PCLEG)]
cks = dict((n, ok) for n, ok, _ in P.pc_checks(
    legs,
    cart_fn=[(0x8C03BD00, 0x8C03BE00)],
    input_fn=[(0x8C031000, 0x8C031FFF)],
    eeprom_fn=[(0x8C032000, 0x8C032200)],
    stack=[(0x8CFF0000, 0x8D000000)]))
assert cks == {"no_bios_exec": True, "dma_pc_in_cart_fn": True,
               "input_pc_in_input_fn": True, "eeprom_read_seen": True,
               "eeprom_write_seen": True, "sp_consistent": True}, cks

# cart-fn range excluding 8c03bd30 -> dma_pc_in_cart_fn fails
cks = dict((n, ok) for n, ok, _ in P.pc_checks(
    legs, cart_fn=[(0x8C03BD00, 0x8C03BD28)], input_fn=None,
    eeprom_fn=None, stack=None))
assert cks["dma_pc_in_cart_fn"] is False

# a BIOSEXEC line fails no_bios_exec
bad = [P.parse_leg("pc", PCLEG + "BIOSEXEC pc=8c000100\n")]
cks = dict((n, ok) for n, ok, _ in P.pc_checks(bad, None, None, None, None))
assert cks["no_bios_exec"] is False

# SP outside the static stack region fails sp_consistent
cks = dict((n, ok) for n, ok, _ in P.pc_checks(
    legs, None, None, None, stack=[(0x8C000000, 0x8C100000)]))
assert cks["sp_consistent"] is False

# no PC lines at all -> no dmapc-derived checks fire (Phase 2 legs untouched)
cks = dict((n, ok) for n, ok, _ in P.pc_checks(
    [a, b], cart_fn=[(0x8C03BD00, 0x8C03BE00)], input_fn=None,
    eeprom_fn=None, stack=None))
assert cks["no_bios_exec"] is True         # no BIOSEXEC lines -> vacuous pass
assert cks["dma_pc_in_cart_fn"] is True    # no dmapc lines -> vacuous pass (all() on empty)
assert "sp_consistent" not in cks          # no dmapc lines -> heuristic/region test skipped

# pcpairs: CARTDMAPC attaches to the immediately preceding CARTDMA
assert legs[0]["pcpairs"] == [
    (0x00200000, 0x0dfe0000, 0x7520, 0x8c03bd28, 0x8cffff00),
    (0x00300000, 0x0d244c20, 0x100, 0x8c03bd30, 0x8cfffef0),
]

# --pc-report: merged/deduped on the printed (dest, pc, sp) triple, not raw
# per-leg concatenation — two legs with the same pcpairs collapse to 2 lines,
# not 4, order-preserving first occurrence.
dup_legs = [P.parse_leg("pc1", PCLEG), P.parse_leg("pc2", PCLEG)]
rep_lines = P.pc_report(dup_legs).splitlines()
assert rep_lines == [
    "PCPAIR dest=0dfe0000 pc=8c03bd28 sp=8cffff00",
    "PCPAIR dest=0d244c20 pc=8c03bd30 sp=8cfffef0",
], rep_lines

print("OK pc_checks self-check")

# no_bios_exec is unconditional: a flagless CLI parse must still print it
# (it's a safety tripwire), while the flag-gated PC checks stay silent.
with tempfile.TemporaryDirectory() as d:
    logpath = os.path.join(d, "attract.log")
    with open(logpath, "w", encoding="utf-8") as f:
        f.write(ATTRACT + "CARTDMAPC pc=8c027f54 sp=8c00ee38\n")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = P.main([logpath, "--attract-leg", "attract"])
    out = buf.getvalue()
assert rc == 0
assert out.count("CHECK no_bios_exec:") == 1
assert "CHECK no_bios_exec: PASS — 0 BIOSEXEC lines (expect 0)" in out
assert "dma_pc_in_cart_fn" not in out       # still flag-gated, no --cart-fn given
assert "sp_consistent" not in out           # still flag-gated, no PC-range flag given
assert "dryrun_" not in out                 # still flag-gated, no --dryrun given

# regression: Phase 2 fixtures (no PC lines) still parse identically —
# re-assert the existing ATTRACT/PLAY expectations after the change.
assert a["dmapc"] == [] and a["maplepc"] == [] and a["biosexec"] == [] and a["pcpairs"] == []
assert P.main_hw(a["dma"]) == 33453344
cks2 = dict((n, ok) for n, ok, _ in P.checks([a, b], rows, attract=a))
assert cks2["dest_known"] and cks2["len_aligned_32"] and cks2["beyond_boot_read"]
assert cks2["attract_anchor"] and cks2["merged_hw_bounds"]

# Dry-run gate checks (Task 11): synthetic anchor + matching/mismatching legs.
# Anchor: parsed like any leg but never merged (Step 6 wiring) — its (src,len)
# multiset and profile fields are the reference the dry-run leg is judged against.
ANCHOR = """\
CARTDMA src=00100000 dest=0c020000 len=100000
CARTDMA src=00200000 dest=0c030000 len=200
CARTDMA src=00200000 dest=0c030200 len=200
MAINPROFILE high=800000 nz=10 nz_below16m=10 nz_above16m=0 size=2000000
VRAMPROFILE high=100000 nz=10 nz_below8m=10 nz_above8m=0 content_high=100000 content_below8m=10 content_above8m=0 fb_bytes=1000 fb_masked_nz=1 size=1000000
VRAMREGS isp_base=400000 isp_limit=6200e0 ol_base=6d5680 ol_limit=6201e0 fb_w_sof1=100000 fb_w_sof2=100000 fb_r_sof1=100000
"""

# Matches the anchor's shape and stays under both caps -> all three PASS.
DRYRUN_GOOD = """\
CARTDMA src=00100000 dest=0c020000 len=100000
CARTDMA src=00200000 dest=0c030000 len=200
CARTDMA src=00200000 dest=0c030200 len=200
MAINPROFILE high=800000 nz=10 nz_below16m=10 nz_above16m=0 size=2000000
VRAMPROFILE high=100000 nz=10 nz_below8m=10 nz_above8m=0 content_high=100000 content_below8m=10 content_above8m=0 fb_bytes=1000 fb_masked_nz=1 size=1000000
VRAMREGS isp_base=400000 isp_limit=6200e0 ol_base=6d5680 ol_limit=6201e0 fb_w_sof1=100000 fb_w_sof2=100000 fb_r_sof1=100000
"""

# Above-16m main DMA, above-8m VRAM content_high + a bad SOF reg, and a
# different (src,len) shape (0x500000 replaces one of the anchor's 0x200000
# pair) -> all three FAIL.
DRYRUN_BAD = """\
CARTDMA src=00100000 dest=0dfe0000 len=7520
CARTDMA src=00500000 dest=0c030000 len=200
MAINPROFILE high=1fe7520 nz=10 nz_below16m=5 nz_above16m=5 size=2000000
VRAMPROFILE high=900000 nz=10 nz_below8m=5 nz_above8m=5 content_high=900000 content_below8m=5 content_above8m=5 fb_bytes=1000 fb_masked_nz=1 size=1000000
VRAMREGS isp_base=400000 isp_limit=6200e0 ol_base=6d5680 ol_limit=6201e0 fb_w_sof1=900000 fb_w_sof2=100000 fb_r_sof1=100000
"""

anchor_leg = P.parse_leg("anchor", ANCHOR)
good_dr = P.parse_leg("good_dr", DRYRUN_GOOD)
bad_dr = P.parse_leg("bad_dr", DRYRUN_BAD)

good_rows = P.merge([good_dr])
dr_cks = dict((n, ok) for n, ok, _ in P.dryrun_checks([good_dr], good_rows, anchor_leg))
assert dr_cks == {"dryrun_main_below_16m": True, "dryrun_vram_below_8m": True,
                   "dryrun_stream_shape": True}, dr_cks

bad_rows = P.merge([bad_dr])
dr_cks = dict((n, ok) for n, ok, _ in P.dryrun_checks([bad_dr], bad_rows, anchor_leg))
assert dr_cks == {"dryrun_main_below_16m": False, "dryrun_vram_below_8m": False,
                   "dryrun_stream_shape": False}, dr_cks

# stream_shape failure detail names the differing tuples on each side
dr_detail = dict((n, d) for n, _, d in
                 P.dryrun_checks([bad_dr], bad_rows, anchor_leg))["dryrun_stream_shape"]
assert "0x500000" in dr_detail          # provided-only tuple surfaced
assert "0x200000" in dr_detail          # anchor-only tuple surfaced

# --dryrun CLI wiring: checks appear only when the flag is given
with tempfile.TemporaryDirectory() as d:
    logpath = os.path.join(d, "attract.log")
    with open(logpath, "w", encoding="utf-8") as f:
        f.write(ATTRACT)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        P.main([logpath, "--attract-leg", "attract", "--dryrun", logpath])
    out_dr = buf.getvalue()
assert "CHECK dryrun_main_below_16m:" in out_dr
assert "CHECK dryrun_vram_below_8m:" in out_dr
assert "CHECK dryrun_stream_shape:" in out_dr
# self-anchor (same file) -> stream shape trivially matches itself
assert "CHECK dryrun_stream_shape: PASS" in out_dr

print("OK dryrun_checks self-check")

# Task 12 ruling A: the narrow FB_W_SOF2 BIOS-default exemption.
# Base leg: same shape as ANCHOR (so dryrun_stream_shape is not the thing
# under test here) plus one FB_W_SOF2 SOFWR write and a VRAMREGS snapshot
# parked at the BIOS default (0xc00000) with nz_above8m=0 throughout.
EXEMPT_BASE = """\
CARTDMA src=00100000 dest=0c020000 len=100000
CARTDMA src=00200000 dest=0c030000 len=200
CARTDMA src=00200000 dest=0c030200 len=200
SOFWR FB_W_SOF2 val=00c00000 was=00000000 pc=0c0558e4 pr=0c045c94
MAINPROFILE high=800000 nz=10 nz_below16m=10 nz_above16m=0 size=2000000
VRAMPROFILE high=100000 nz=10 nz_below8m=10 nz_above8m=0 content_high=100000 content_below8m=10 content_above8m=0 fb_bytes=1000 fb_masked_nz=1 size=1000000
VRAMREGS isp_base=400000 isp_limit=6200e0 ol_base=6d5680 ol_limit=6201e0 fb_w_sof1=100000 fb_w_sof2=c00000 fb_r_sof1=100000
"""

exempt_leg = P.parse_leg("exempt", EXEMPT_BASE)
assert exempt_leg["sofwr"]["fb_w_sof2"] == 1
exempt_rows = P.merge([exempt_leg])
dr_cks = dict((n, ok) for n, ok, _ in P.dryrun_checks([exempt_leg], exempt_rows, anchor_leg))
assert dr_cks["dryrun_vram_below_8m"] is True, dr_cks   # exemption applies: all 3 conditions hold

# Direction 1: a second FB_W_SOF2 write (any value) breaks condition 2 -> not exempt.
SECOND_WRITE = EXEMPT_BASE + "SOFWR FB_W_SOF2 val=00d00000 was=00c00000 pc=0c0558e4 pr=0c045c94\n"
leg2 = P.parse_leg("second_write", SECOND_WRITE)
assert leg2["sofwr"]["fb_w_sof2"] == 2
rows2 = P.merge([leg2])
dr_cks2 = dict((n, ok) for n, ok, _ in P.dryrun_checks([leg2], rows2, anchor_leg))
assert dr_cks2["dryrun_vram_below_8m"] is False, dr_cks2   # second write -> exemption void

# Direction 2: nonzero nz_above8m anywhere breaks condition 3 -> not exempt, even
# with a single FB_W_SOF2 write at the exact BIOS-default value.
ABOVE8M = EXEMPT_BASE.replace(
    "VRAMPROFILE high=100000 nz=10 nz_below8m=10 nz_above8m=0 content_high=100000 content_below8m=10 content_above8m=0 fb_bytes=1000 fb_masked_nz=1 size=1000000",
    "VRAMPROFILE high=900000 nz=15 nz_below8m=10 nz_above8m=5 content_high=100000 content_below8m=10 content_above8m=0 fb_bytes=1000 fb_masked_nz=1 size=1000000")
leg3 = P.parse_leg("above8m", ABOVE8M)
assert leg3["prof"]["vram"]["nz_above8m"] == 5
rows3 = P.merge([leg3])
dr_cks3 = dict((n, ok) for n, ok, _ in P.dryrun_checks([leg3], rows3, anchor_leg))
assert dr_cks3["dryrun_vram_below_8m"] is False, dr_cks3   # nz_above8m>0 -> exemption void

# A non-fb_w_sof2 register at the same masked value, or fb_w_sof2 at a
# different value, is never exempt (narrow to the one cell).
OTHER_REG = EXEMPT_BASE.replace("fb_w_sof1=100000", "fb_w_sof1=c00000")
leg4 = P.parse_leg("other_reg", OTHER_REG)
rows4 = P.merge([leg4])
dr_cks4 = dict((n, ok) for n, ok, _ in P.dryrun_checks([leg4], rows4, anchor_leg))
assert dr_cks4["dryrun_vram_below_8m"] is False, dr_cks4   # fb_w_sof1 above cap -> not exempt

print("OK dryrun ruling-A (FB_W_SOF2 exemption) self-check")

# Task 12 ruling B: stream-shape scoped to the first (attract) leg only; any
# further legs (the play leg) are exempt/informational, never fail the check.
PLAY_LIKE = """\
CARTDMA src=00900000 dest=0c040000 len=40
CARTDMA src=00900040 dest=0c040040 len=40
MAINPROFILE high=800000 nz=10 nz_below16m=10 nz_above16m=0 size=2000000
VRAMPROFILE high=100000 nz=10 nz_below8m=10 nz_above8m=0 content_high=100000 content_below8m=10 content_above8m=0 fb_bytes=1000 fb_masked_nz=1 size=1000000
VRAMREGS isp_base=400000 isp_limit=6200e0 ol_base=6d5680 ol_limit=6201e0 fb_w_sof1=100000 fb_w_sof2=100000 fb_r_sof1=100000
"""
play_leg = P.parse_leg("play_like", PLAY_LIKE)
shape_rows = P.merge([good_dr, play_leg])
dr_cks = dict((n, ok) for n, ok, _ in P.dryrun_checks([good_dr, play_leg], shape_rows, anchor_leg))
assert dr_cks["dryrun_stream_shape"] is True, dr_cks   # play leg's mismatch does not fail the check
shape_detail = dict((n, d) for n, _, d in
                    P.dryrun_checks([good_dr, play_leg], shape_rows, anchor_leg))["dryrun_stream_shape"]
assert "good_dr" in shape_detail and "match the anchor" in shape_detail
assert "exempt from shape" in shape_detail and "play_like" in shape_detail

# Reversed leg order: the play-shaped leg is now first -> IT is judged
# against the anchor and correctly fails (order, not name, decides the role).
dr_cks_rev = dict((n, ok) for n, ok, _ in
                  P.dryrun_checks([play_leg, good_dr], P.merge([play_leg, good_dr]), anchor_leg))
assert dr_cks_rev["dryrun_stream_shape"] is False, dr_cks_rev

# Capture-window truncation: multiset counts differ but the unique (src,len)
# set matches exactly -> PASS with the boundary explanation, not a FAIL
# (relocation-map.md's own set-equality provision).
TRUNCATED = """\
CARTDMA src=00100000 dest=0c020000 len=100000
CARTDMA src=00200000 dest=0c030000 len=200
CARTDMA src=00200000 dest=0c030200 len=200
CARTDMA src=00200000 dest=0c030200 len=200
"""
trunc_leg = P.parse_leg("truncated", TRUNCATED)
dr_cks = dict((n, ok) for n, ok, _ in
             P.dryrun_checks([trunc_leg], P.merge([trunc_leg]), anchor_leg))
assert dr_cks["dryrun_stream_shape"] is True, dr_cks
trunc_detail = dict((n, d) for n, _, d in
                    P.dryrun_checks([trunc_leg], P.merge([trunc_leg]), anchor_leg))["dryrun_stream_shape"]
assert "truncation boundary" in trunc_detail

print("OK dryrun ruling-B (stream-shape scoping) self-check")

print("ok")

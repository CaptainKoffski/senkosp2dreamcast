#!/usr/bin/env python3
"""pak_coverage.py <log|log.zst> [more logs...] — map drive-truth fad= lines
to ISO files of the flat cart image and report, per log, the chronological
first-load order of .PAK files, plus a cumulative observed/missing summary.

Mapping (docs/kb/phase5-hardware.md §Ending system decoded): root dir walked
from the PVD at senkosp.dat 0x808000, fad = LBA + 410974, validated by the
STAGE08.PAK fad==0x84e53 assert. This is the fixed mapper that superseded the
2026-08-28 census (the old one missed END3_P07/END4_P07 on both sides).
"""
import bisect, re, struct, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
data = open(REPO / "senkosp.dat", "rb").read()
PVD, LBA0 = 0x808000, 40904
root = data[PVD + 156:PVD + 156 + 34]
r_lba = struct.unpack_from("<I", root, 2)[0]
r_size = struct.unpack_from("<I", root, 10)[0]
d = data[(r_lba - LBA0) * 2048:(r_lba - LBA0) * 2048 + r_size]
ivals, i = [], 0
while i < len(d):
    rl = d[i]
    if rl == 0:
        i = (i // 2048 + 1) * 2048
        continue
    nl = d[i + 32]
    nm = d[i + 33:i + 33 + nl].decode("ascii", "replace").split(";")[0].upper()
    if nm not in ("\x00", "\x01", ""):
        lba = struct.unpack_from("<I", d, i + 2)[0]
        size = struct.unpack_from("<I", d, i + 10)[0]
        ivals.append((lba + 410974, lba + 410974 + (size + 2047) // 2048, nm))
    i += rl
ivals.sort()
starts = [v[0] for v in ivals]
assert any(n == "STAGE08.PAK" and s == 0x84e53 for s, _, n in ivals)

rx = re.compile(rb"fad=([0-9a-f]{8})")
cumulative = set()
for arg in sys.argv[1:]:
    f = (subprocess.Popen(["zstdcat", arg], stdout=subprocess.PIPE).stdout
         if arg.endswith(".zst") else open(arg, "rb"))
    seen, order = set(), []
    for ln, line in enumerate(f, 1):
        m = rx.search(line)
        if not m:
            continue
        fad = int(m.group(1), 16)
        j = bisect.bisect_right(starts, fad) - 1
        if j >= 0 and fad < ivals[j][1]:
            nm = ivals[j][2]
            if nm.endswith(".PAK") and nm not in seen:
                seen.add(nm)
                order.append((ln, nm))
    f.close()
    cumulative |= seen
    print(f"== {arg}")
    for ln, nm in order:
        print(f"{ln:>10}  {nm}")
allpaks = sorted(n for _, _, n in ivals if n.endswith(".PAK"))
missing = [n for n in allpaks if n not in cumulative]
print(f"\ncumulative: {len(cumulative)}/{len(allpaks)} PAKs observed; "
      f"missing {len(missing)}: {' '.join(missing)}")

#!/usr/bin/env python3
"""Self-check for build_patch_table.py (TDD step 1, task-9-brief.md).

Brief's step-1 test: run the generator (currently wires only the 4
scripts/reloc_patchset.json reloc entries -- cart/maple/reset land in Tasks
10-13), parse the emitted build/patch_table.h, and assert:
  (a) every `old` matches senkosp.dat at dat_off
  (b) the two test-image entries carry img == 1
  (c) re-running is deterministic (identical output)

Plus (controller's binding requirements): the jmp-detour hook kind's math
at both W%4 alignments, and that a deliberately wrong `old` fails the build.
"""
import pathlib
import re
import struct
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
GEN = ROOT / "scripts" / "build_patch_table.py"
HDR = ROOT / "build" / "patch_table.h"
DAT = ROOT / "senkosp.dat"


def run_gen():
    r = subprocess.run([sys.executable, str(GEN)], cwd=str(ROOT / "scripts"),
                        capture_output=True, text=True)
    assert r.returncode == 0, f"generator exited {r.returncode}:\n{r.stdout}\n{r.stderr}"
    return HDR.read_text()


ROW = re.compile(
    r'\{0x([0-9a-fA-F]+)u,\s*(\d+)u,\s*(\d+)u,\s*'
    r'\{([^}]*)\},\s*\{([^}]*)\},\s*"')


def parse_rows(text):
    out = []
    for off_s, img_s, len_s, old_s, new_s in ROW.findall(text):
        off, img, ln = int(off_s, 16), int(img_s), int(len_s)
        old_bytes = bytes(int(b, 16) for b in old_s.split(","))[:ln]
        new_bytes = bytes(int(b, 16) for b in new_s.split(","))[:ln]
        out.append((off, img, ln, old_bytes, new_bytes))
    return out


# ---- (a) + (b): one run, check old-byte fidelity + img tagging -----------
text = run_gen()
dat = DAT.read_bytes()
rows = parse_rows(text)
assert len(rows) == 4, f"expected 4 reloc-only entries, found {len(rows)}"

test_img_rows = 0
for off, img, ln, old, _new in rows:
    assert dat[off:off + ln] == old, (
        f"old mismatch @dat:{off:#x}: header has {old.hex()}, "
        f"senkosp.dat has {dat[off:off + ln].hex()}")
    assert img in (0, 1), (off, img)
    if img == 1:
        test_img_rows += 1
assert test_img_rows == 2, f"expected 2 img==1 (test-image) rows, found {test_img_rows}"
print("OK (a) old-byte fidelity, (b) img==1 tagging (2 test-image entries)")

# ---- (c): determinism across independent runs ------------------------------
text2 = run_gen()
assert text2 == text, "generator output is not byte-identical across runs"
print("OK (c) deterministic output across runs")

# ---- detour()-kind math: both W%4 alignments, literal inside window --------
sys.path.insert(0, str(ROOT / "scripts"))
import build_patch_table as BPT  # noqa: E402  (after sys.path setup)

for w, want_lit_off, want_len in ((0x001000, 8, 12), (0x001002, 6, 10)):
    code = BPT._detour_code(w, 0x8C010ABC)
    assert len(code) == want_len, (w, len(code), want_len)
    lit_off = (((w + 4) & ~3) + 4) - w          # KB's own formula, re-derived
    assert lit_off == want_lit_off, (w, lit_off, want_lit_off)
    assert lit_off + 4 <= len(code), "literal does not land inside the window"
    assert code[0:6] == struct.pack("<HHH", 0xD201, 0x422B, 0x0009), code[0:6].hex()
    assert code[lit_off:lit_off + 4] == struct.pack("<I", 0x8C010ABC)
print("OK detour() kind: both W%4 alignments, literal lands inside the window")

# ---- old-byte verification must reject a deliberately wrong `old` ----------
before = len(BPT.patches)
try:
    BPT.pool(0x0, 0xDEADBEEF, 0, "deliberately wrong old (self-check)")
    raise SystemExit("FAIL: wrong `old` did not raise")
except AssertionError:
    pass
assert len(BPT.patches) == before, "failed verification polluted patches[]"
print("OK old-byte verification rejects a wrong `old`")

print("ok")

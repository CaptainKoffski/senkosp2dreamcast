#!/usr/bin/env python3
"""Master a dcload-serial boot GDI for GDEMU (Task 25, serial-link control).

Same B5 donor-clone trick as make_gdi.py, minus the cart: tracks 1-3 +
disc.gdi are the donor's bytes verbatim, track04 is dcload-serial's
UNSCRAMBLED 1st_read loader (linked at 0x8c010000, exactly where the donor
bootstrap loads 1ST_READ.BIN) zero-padded to the donor's boot region. The
scrambled 1st_read.bin the dcload Makefile fails to produce is for burned
MIL-CDs only -- GD-area boot binaries are plain (same fact make_gdi.py
relies on for our own loader).

Output: build/dcload/ (5 files, deploy to a GDEMU card folder of its own).
Build dcload first: docs/kb/tooling.md §dcload-serial.
"""
import pathlib, shutil, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import make_gdi as g   # module-level asserts re-verify shim constants; harmless here

LOADER = pathlib.Path("tools/dcload-serial/target-src/1st_read/loader.bin")
OUT = pathlib.Path("build/dcload")

def main():
    assert LOADER.exists(), f"{LOADER} missing -- build dcload-serial first"
    OUT.mkdir(parents=True, exist_ok=True)
    donor = g.donor_tracks(pathlib.Path("build"))   # reuses build/donor/ cache
    for f in ("track01.iso", "track02.raw", "track03.iso", "disc.gdi"):
        shutil.copyfile(donor / f, OUT / f)
    g.IP_PRODUCT, g.IP_DATE = "T-DCL001M", "20260902"
    g.IP_TITLE = "DCLOAD-SERIAL 1.0.7"
    g.brand_ip(OUT / "track03.iso")   # GDmenu shows this title
    ldr = LOADER.read_bytes()
    assert len(ldr) <= g.BOOT_FILE_SIZE, "dcload loader outgrew donor boot region"
    (OUT / "track04.iso").write_bytes(ldr + b"\0" * (g.BOOT_REGION - len(ldr)))
    print(f"OK {OUT}/disc.gdi (donor clone, track04 = dcload loader "
          f"{len(ldr)} B + padding)")

if __name__ == "__main__":
    main()

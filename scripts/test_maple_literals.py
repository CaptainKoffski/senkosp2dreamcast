#!/usr/bin/env python3
"""VMU-safety static tripwire (spec: docs/superpowers/specs/2026-07-26-vmu-safety-design.md).

A VMU is only reachable via Maple-bus frames; game code reaches the Maple
DMA registers through u32 literals in the block 0x5f6c00-0x5f6cff (any
P0/P1/P2 mirror). This scan checks that set of literals in every executable
byte source on the disc:

  - full cart image + build/bios_data.bin (Naomi ROM/BIOS-library bytes):
    INFORMATIONAL ONLY for senkosp right now. Cleopatra had these fully
    classified (RE'd offset-by-offset) so an exact-baseline-match could gate
    the build; senkosp's own classification hasn't happened yet (later-task
    RE work, docs/kb/phase4-conversion.md's Cart-patch-sites pattern). A
    permanently-empty baseline that still gated the exit code would make
    `make test` red from Task 6 onward for a reason nobody could act on --
    exactly the "everyone learns to ignore the red" failure mode this
    tripwire exists to prevent. Findings still print (classify before
    editing anything they flag), they just don't fail `make test`.
  - loader/main.o + handoff.o (our loader code): GATES the build. Zero
    vmu/maple references is fully knowable and enforceable right now (the
    KOS libs linked into loader.elf legitimately contain both, and are
    covered by the dynamic canary test instead, so only our own two objects
    are scanned) -- this is the one check Task 6 actually owns.

The shim (shims/src/maple.c) is excluded by design: it is the one authorized
Maple user, TX limited to DEVICE REQUEST + GETCOND to main devices.

Once senkosp's cart/bios_data literals are classified (patched or proven
dead -- scripts/ghidra FindMmioXrefs.java gives xrefs), populate
CART_BASELINE/BIOS_DATA_BASELINE with the classified set and move their
checks back into the gating path (flip informational=False in check()).
Same failure class as the 19 unpatched G1 0x5f7xxx literals of HW round 10
(docs/kb/00-status.md).
"""
import pathlib, struct, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CART = ROOT / "senkosp.dat"
BIOS_DATA = ROOT / "build" / "bios_data.bin"
LOADER_OBJS = [ROOT / "loader" / "main.o", ROOT / "loader" / "handoff.o"]

STREAM_FLOOR = 0x100000    # 1 MB boot region (BOOT_END, scripts/parse_cartlog.py) --
                           # rest of senkosp.dat is streamed asset data
BASE_VA = 0x8C020000       # cart offset 0 loads here (docs/kb/game.md)

# Phase 4 Task 6: senkosp's own maple literals are NOT classified yet (that
# RE work -- which offsets, what they mean, whether Cleopatra's "mirrored
# boot region" cart-layout quirk even applies here -- is a later task, akin
# to the Cart-patch sites P1/P2/P3 work in docs/kb/phase4-conversion.md).
# Empty baseline is deliberate: any hit the scan finds must be classified
# before it's added here (spec's whole point), not carried over guessed
# from a different ROM.
CART_BASELINE = set()
BIOS_DATA_BASELINE = set()

def scan(data):
    """Aligned u32 literals with (v & 0x1fffff00) == 0x005f6c00.
    find()-driven: every candidate contains the byte pair 6c 5f at u32
    bytes 1-2 (LE layout lo,6c,5f,hi) -- ~1 s over the 109 MB cart."""
    hits = set()
    pos = data.find(b"\x6c\x5f")
    while pos != -1:
        off = pos - 1
        if off >= 0 and off % 4 == 0 and off + 4 <= len(data):
            v = struct.unpack_from("<I", data, off)[0]
            if (v & 0x1FFFFF00) == 0x005F6C00:
                hits.add((off, v))
        pos = data.find(b"\x6c\x5f", pos + 1)
    return hits

def selftest():
    planted = b"\0" * 4 + struct.pack("<I", 0xA05F6C18) + b"\0" * 8
    assert scan(planted) == {(4, 0xA05F6C18)}, "self-test: planted literal missed"
    assert scan(b"\0" * 16) == set(), "self-test: false hit on zeros"
    assert scan(b"\0" + planted) == set(), "self-test: unaligned literal must not match"

def check(name, got, want, informational=False):
    """Returns True iff got==want. `informational`: findings still print in
    full (classify before touching anything), but the caller must NOT let a
    False here fail the build -- see module docstring."""
    tag = "INFO" if informational else "FAIL"
    if got == want:
        print(f"OK   {name}: {len(got)} literals match baseline")
        return True
    for off, v in sorted(want - got):
        print(f"{tag} {name}: baseline literal GONE  off 0x{off:07x} = 0x{v:08x}")
    for off, v in sorted(got - want):
        print(f"{tag} {name}: NEW maple literal     off 0x{off:07x} = 0x{v:08x}"
              f"  (VA 0x{BASE_VA + off:08x} if boot code -- no known mirroring for senkosp yet)")
    print("     classify before touching the baseline (patch or prove dead;"
          " scripts/ghidra FindMmioXrefs.java) -- see the spec"
          + (" [informational -- does not fail make test, see module docstring]"
             if informational else ""))
    return False

def main():
    selftest()
    for p in (CART, BIOS_DATA, *LOADER_OBJS):
        if not p.exists():
            sys.exit(f"missing {p} -- ROM at repo root + a normal 'make disc' first")

    # Informational: senkosp's cart/BIOS-data maple literals aren't
    # classified yet (module docstring). Findings print but never fail the
    # build -- only loader_ok below gates `make test`'s exit code.
    cart_hits = scan(CART.read_bytes())
    check("cart", cart_hits, CART_BASELINE, informational=True)
    streamed = {h for h in cart_hits if h[0] >= STREAM_FLOOR}
    if streamed:
        for off, v in sorted(streamed):
            print(f"INFO streamed region: maple literal off 0x{off:07x} = 0x{v:08x}")
    else:
        print("OK   streamed region (>= 0x100000): zero maple literals")
    check("bios_data.bin", scan(BIOS_DATA.read_bytes()), BIOS_DATA_BASELINE, informational=True)

    # Gating: loader/main.o + handoff.o are Task 6's own build output, and
    # "zero vmu/maple symbol references" is fully knowable right now.
    nm = subprocess.run(["nm", *map(str, LOADER_OBJS)],
                        capture_output=True, text=True, check=True)
    bad = [l for l in nm.stdout.splitlines()
           if "vmu" in l.lower() or "maple" in l.lower()]
    if bad:
        loader_ok = False
        for l in bad:
            print(f"FAIL loader objects reference VMU/Maple: {l}")
    else:
        loader_ok = True
        print("OK   loader main.o/handoff.o: no vmu/maple references")
    sys.exit(0 if loader_ok else 1)

if __name__ == "__main__":
    main()

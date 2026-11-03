"""senkosp's Maple-literal allow-list, read by kit/scripts/test_maple_literals.py
(kitpath.port_module("maple_allowlist")): every u32 literal in the
0x5f6c00-0x5f6cff Maple-register block that the tripwire finds in senkosp.dat
and in build/bios_data.bin (BIOS_DATA_BASELINE, at the end), classified. A
literal found but not listed here (or listed but gone) fails `make test`.

History (moved from the tripwire's docstring at the kit extraction): through
Phase 4 Task 6 the cart/bios_data scans were INFORMATIONAL ONLY for senkosp.
Cleopatra had these fully classified (RE'd offset-by-offset) so an
exact-baseline-match could gate the build; senkosp's own classification
hadn't happened yet (later-task RE work, docs/kb/phase4-conversion.md's
Cart-patch-sites pattern), and a permanently-empty baseline that still gated
the exit code would have made `make test` red for a reason nobody could act
on -- exactly the "everyone learns to ignore the red" failure mode the
tripwire exists to prevent. Phase 4 Task 14 classified every hit (below);
since the kit extraction the cart and bios_data checks gate `make test`.
Same failure class as the 19 unpatched G1 0x5f7xxx literals of HW round 10
(docs/kb/00-status.md).
"""

# Phase 4 Task 14 (gate criterion 6, 2026-08-23): every hit test_maple_literals
# finds against senkosp.dat (md5 6283cf5c75d7fc32740a8e8e54d10aa8, tooling.md
# "senkosp.dat") and build/bios_data.bin has now been individually classified.
# Three buckets, one justification per bucket (the trap-table bucket also gets
# a per-register name -- it is the one bucket that needed real investigation):
#
# (a) MAPLE-mirror patches, 36 = 18 main-image + 18 test-image entries. Each
#     tuple is the PRE-PATCH `old` word of a build/patch_table.h entry that
#     the loader repoints to the shim's MAPLE_MIRROR/G1_MIRROR before the
#     game ever runs (docs/kb/phase4-conversion.md §Maple-patch sites P4).
#     Justification: cross-matched every hit's (dat_off, value) against
#     patch_table.h byte-for-byte -- 36/36 exact matches (dat_off AND old
#     word), Task 14 session 2026-08-23. Already gated by the real check:
#     scripts/test_build_patch_table.py's old-byte fidelity assert.
CART_MAPLE_PATCHED = {
    (0x0006b58, 0xa05f6c00), (0x004664c, 0xa05f6c14), (0x004678c, 0xa05f6c04),
    (0x004682c, 0xa05f6c04), (0x0046958, 0xa05f6c04), (0x0046ac0, 0xa05f6c14),
    (0x0046ac8, 0xa05f6c8c), (0x0046ad0, 0xa05f6c80), (0x0046ad4, 0xa05f6c10),
    (0x0046ad8, 0xa05f6c04), (0x0046adc, 0xa05f6c18), (0x013c4c8, 0xa05f6c04),
    (0x013c4d0, 0xa05f6c10), (0x013c4d8, 0xa05f6c14), (0x013c4e0, 0xa05f6c80),
    (0x013c4e8, 0xa05f6c8c), (0x013c4f0, 0xa05f6ce8), (0x013c648, 0xa05f6c18),
    (0x0178b50, 0xa05f6c00), (0x01a2e78, 0xa05f6c14), (0x01a2fb8, 0xa05f6c04),
    (0x01a3058, 0xa05f6c04), (0x01a3184, 0xa05f6c04), (0x01a32ec, 0xa05f6c14),
    (0x01a32f4, 0xa05f6c8c), (0x01a32fc, 0xa05f6c80), (0x01a3300, 0xa05f6c10),
    (0x01a3304, 0xa05f6c04), (0x01a3308, 0xa05f6c18), (0x01b22f4, 0xa05f6c04),
    (0x01b22fc, 0xa05f6c10), (0x01b2304, 0xa05f6c14), (0x01b230c, 0xa05f6c80),
    (0x01b2314, 0xa05f6c8c), (0x01b231c, 0xa05f6ce8), (0x01b2474, 0xa05f6c18),
}
# (b) SDK "ADDRESS CHECKER TRAP" register-dump table, 4 = 2 main + 2 test.
#     Ghidra-confirmed: the table's own base pointer (dat 0xc884 -> VA
#     0x8c02c884) is read by FUN_8c02c5ec (`run.sh script FindRefsTo.java
#     0x8c02c884` -> 1 ref; `run.sh script Decomp.java 0x8c02c5ec`), an SH-4
#     address/bus-error exception handler: it PRINTS the CPU's FR/R/MAC/VBR/
#     GBR/DBR/PR/PC/SR regs, then walks a 0x45-entry table of hardware
#     register addresses (SH-4 on-chip, G1, maple, cart) and PIO-*reads* +
#     prints each ("ADDRESS CHECKER TRAP", dat 0x13c7db / 0x1b2607 verbatim
#     in both images) before blocking on a keypress. Read-only diagnostic
#     dump, not a maple-frame builder -- no write reaches a VMU -- and it
#     only runs on an actual CPU bus/address-error fault, which this port
#     has never observed. Two entries per image are SB_MDSTAR (+0x04) and
#     SB_MDTSEL (+0x10) inside that table; unpatched (reads the real HW
#     register, not the mirror) but that is fine for a read-only trap the
#     DC's own Holly exposes the same registers to.
CART_TRAP_TABLE = {
    (0x013c710, 0xa05f6c04), (0x013c714, 0xa05f6c10), (0x01b253c, 0xa05f6c04),
    (0x01b2540, 0xa05f6c10),
}
# (c) Streamed asset-data noise, 42, all at dat_offset >= 0x1bfc38 (past both
#     boot images -- test-image end, docs/kb/phase4-conversion.md's
#     "Test-image range 0x171ff8:0x1bfc38" -- inside GD-ROM-streamed
#     texture/audio/model content this port never executes as code).
#     Justification: expected by chance alone. The scan mask
#     `(v & 0x1fffff00)==0x005f6c00` matches 2048/2**32 possible u32 values
#     (~4.77e-7 per aligned word); ~249.5 MB of streamed bytes / 4 predicts
#     ~30 hits from uniform noise, 42 observed is the same order of
#     magnitude (real asset data is not perfectly uniform). Spot-checked 4
#     samples byte-for-byte (Task 14 session): ordinary compressed-asset
#     bytes on both sides, no register-table structure (contrast bucket b).
CART_STREAMED_NOISE = {
    (0x08317a8, 0x205f6c7c), (0x0d59918, 0x205f6c50), (0x21382d4, 0x805f6c91),
    (0x2680a20, 0x205f6c29), (0x2e263a4, 0x205f6c9e), (0x3fe39d4, 0x005f6c0a),
    (0x571be80, 0x805f6c00), (0x5a0e0d8, 0x005f6c52), (0x5b24c84, 0x005f6c5f),
    (0x5b25074, 0x005f6c5f), (0x6063768, 0x405f6c6c), (0x640b8cc, 0xc05f6c90),
    (0x6c70c74, 0x205f6c29), (0x6c7c2ac, 0x205f6c29), (0x7d22fbc, 0x805f6c5f),
    (0x7da689c, 0x005f6c5f), (0x7e4bfbc, 0x805f6c5f), (0x7eca700, 0x005f6c5f),
    (0x7f6ffbc, 0x805f6c5f), (0x7ff283c, 0x005f6c5f), (0x8097fbc, 0x805f6c5f),
    (0x809d30c, 0x805f6c5f), (0x8117e9c, 0x005f6c5f), (0x81bd7bc, 0x805f6c5f),
    (0x81cd010, 0x805f6c5f), (0x8241c98, 0x005f6c5f), (0x82e77bc, 0x805f6c5f),
    (0x83648e4, 0x005f6c5f), (0x8806164, 0x005f6ce4), (0x8c32c9c, 0x005f6c5f),
    (0x8c9bc9c, 0x005f6c5f), (0x971984c, 0x205f6c29), (0x9e40958, 0x405f6cf2),
    (0x9e5add8, 0xe05f6c79), (0xaf7b02c, 0x605f6c50), (0xb5f6224, 0x605f6c50),
    (0xb9b4a24, 0x605f6c50), (0xcf5240c, 0xe05f6cfd), (0xd230c80, 0xc05f6cf6),
    (0xd5b14b4, 0xc05f6cfb), (0xeb305d0, 0xa05f6c02), (0xec832c4, 0x405f6c04),
}
# bios_data.bin's one hit (Naomi BIOS ROM 0x60000-0x67000 library blob,
# offset 0x14d4 = ROM offset 0x614d4): same byte signature (repeating
# `XX 5f a0 00000000` runs) immediately preceding it as a game boot image's
# ADDRESS-CHECKER-TRAP table (the CART_TRAP_TABLE bucket of the first port's
# maple_allowlist.py) -- high-confidence same Sega
# SDK table, shared low-level library code Sega links into both the BIOS
# ROM and the game image. NOT Ghidra-xref-confirmed (this project's Ghidra
# DB covers the boot image only, not the raw BIOS ROM blob) -- classified by
# byte-pattern match, one confidence notch below that Ghidra-confirmed bucket, still
# read-only-diagnostic in nature and not a maple-frame builder.
BIOS_DATA_BASELINE = {(0x00014d4, 0xa05f6c18)}

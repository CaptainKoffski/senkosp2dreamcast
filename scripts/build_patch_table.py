#!/usr/bin/env python3
"""Generate build/patch_table.h from patch definitions + senkosp.dat +
shims/build/shim.map + shims/include/shim_iface.h.

Adapted from ../cleopatra/scripts/build_patch_table.py. Two differences from
Cleopatra's generator, both spec pins for this port (task-9-brief.md):

  1. Addressing is a raw `.dat` OFFSET, not a boot.bin RAM address. senkosp's
     patch sites span BOTH images (main load entry at .dat 0x0, test load
     entry at .dat TEST_DAT_OFF -- docs/kb/game.md §Parsed .dat header), and
     the old-byte verification source is senkosp.dat itself, not boot.bin
     (Phase 4 flag 7: boot.bin only covers the main image). Every dat_offset
     used below therefore has the SAME mod-4 parity as the real RAM address
     it patches, because both GAME_LOAD_ADDR and TEST_DAT_OFF are 4-aligned
     (shim_iface.h) -- the hook()/detour() SH-4 PC-relative math (which only
     cares about parity, never the absolute value) carries over unchanged.
  2. Each entry carries an `img` tag (0 = main, 1 = test), inferred from
     dat_offset alone (img_of() below) -- never hand-classified, so a
     mis-tagged image is structurally impossible.

Patch kinds (little-endian; `new`/`target` values are symbolic where they
depend on the shim -- computed from shim.map/shim_iface.h so the KB doc and
this generator never drift, same convention as Cleopatra's MIRROR_P2):
  pool(dat_off, expect, value)   u32 config-time literal: assert cur==expect, write value
  ptr (dat_off, expect, target)  u32 fn-pointer slot: assert cur==expect, write target
  hook(dat_off, expect, target)  overwrite a 2-byte-verified fn entry with a
                                  6-byte SH-4 thunk + pooled target (Cleopatra's kind)
  detour(dat_off, expect, target) NEW for this port -- a self-contained 10-12 B
                                  jmp-detour window (docs/kb/phase4-conversion.md
                                  §maple-patch-sites MAPLE-BOOT-STRATEGY): unlike
                                  hook(), the replaced code is mid-body, not a
                                  function entry, so nothing may call into it --
                                  it must carry its own literal inline.

Sources (all cited in docs/kb/phase4-conversion.md):
  §Cart-patch sites  -> 32-row main/test tables + 4 entry hooks (Task 10)
  §Maple-patch sites -> 20-row main/test tables, MAPLE-KICK-HOOK, 5 boot detours (Task 11)
  §Restart stub      -> RESET-PATCH, 1 word per image (Task 10)
  scripts/reloc_patchset.json -> the 4 relocation words (Task 9, wired below;
                                  single source -- values live ONLY in that
                                  file, never duplicated here)
"""
import json
import pathlib
import re
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# ---- shim_iface.h: single source of truth for Phase 4 addresses ----------
IFACE_PATH = ROOT / "shims/include/shim_iface.h"
iface = IFACE_PATH.read_text()


def _hexdef(name):
    m = re.search(rf"#define\s+{name}\s+(0x[0-9a-fA-F]+)", iface)
    if not m:
        sys.exit(f"{name} not in {IFACE_PATH} as a plain #define hex literal")
    return int(m.group(1), 16)


def _sb_off(name):     # "#define NAME (SHIM_BASE + 0xNNNN)" -> abs address
    m = re.search(rf"#define\s+{name}\s+\(SHIM_BASE\s*\+\s*(0x[0-9a-fA-F]+)\)", iface)
    if not m:
        sys.exit(f"{name} not in {IFACE_PATH} as (SHIM_BASE + 0xNNNN)")
    return SHIM_BASE + int(m.group(1), 16)


SHIM_BASE = _hexdef("SHIM_BASE")
TEST_DAT_OFF = _hexdef("TEST_DAT_OFF")     # main/test boundary, raw .dat offset

# Register mirrors (P2/uncached, matching the game's original access mode) --
# not consumed by any entry wired in THIS task (only the 4 reloc words are
# active below), but parsed now per task-9-brief.md step 3 ("mirror addresses
# parsed from shim_iface.h") so Tasks 10/11 add definitions, not plumbing.
G1_MIRROR_P2 = _sb_off("G1_MIRROR") | 0xA0000000        # Task 10 cart/G1 patches
MAPLE_MIRROR_P2 = _sb_off("MAPLE_MIRROR") | 0xA0000000  # Task 11 maple patches

# ---- shim entry points from shim.map --------------------------------------
# Symbols carry a leading _ (__USER_LABEL_PREFIX__=_); look up with or without.
symtab = {}
for line in (ROOT / "shims/build/shim.map").read_text().splitlines():
    p = line.split()
    if len(p) == 3:
        symtab[p[2]] = int(p[0], 16)


def sym(name):
    v = symtab.get(name)
    if v is None:
        v = symtab.get("_" + name)          # C name -> asm label _name
    if v is None:
        sys.exit(f"symbol {name!r} not in shim.map (rebuild: make -C shims)")
    return v            # code entries run cached (P1); jmp/jsr targets want P1

# ---- senkosp.dat: the old-byte verification source for EVERY entry --------
# NOT boot.bin (Cleopatra's source): entries span both the main and test load
# images, and dat_offset is uniformly a raw .dat offset (task-9-brief.md
# Interfaces block, Phase 4 flag 7).
DAT_PATH = ROOT / "senkosp.dat"
if not DAT_PATH.exists():
    sys.exit(f"{DAT_PATH} missing (gitignored, regenerable -- docs/kb/tooling.md)")
DAT = DAT_PATH.read_bytes()


def img_of(dat_off):
    """0 = main image, 1 = test image (docs/kb/phase4-conversion.md
    §Cart-patch-sites Conventions: dat_offset >= TEST_DAT_OFF -> test)."""
    return 1 if dat_off >= TEST_DAT_OFF else 0


def rd(dat_off, n):
    assert 0 <= dat_off <= len(DAT) - n, hex(dat_off)
    return DAT[dat_off:dat_off + n]


patches = []   # (dat_off, img, old-bytes, new-bytes, comment)


def _append(dat_off, old, new, comment):
    assert len(old) == len(new), (dat_off, len(old), len(new))
    assert len(old) <= 12, f"@dat:{dat_off:#x}: {len(old)} B exceeds the 12 B old/neu capacity"
    patches.append((dat_off, img_of(dat_off), old, new, comment))


def pool(dat_off, expect, value, comment=""):
    old = rd(dat_off, 4)
    got = struct.unpack("<I", old)[0]
    assert got == expect, f"pool @dat:{dat_off:#x}: found {got:#010x}, expected {expect:#010x}"
    _append(dat_off, old, struct.pack("<I", value), comment)


def ptr(dat_off, expect, target, comment=""):
    old = rd(dat_off, 4)
    got = struct.unpack("<I", old)[0]
    assert got == expect, f"ptr @dat:{dat_off:#x}: found {got:#010x}, expected {expect:#010x}"
    _append(dat_off, old, struct.pack("<I", target), comment)


def hook(dat_off, expect, target, comment=""):
    """SH-4 entry thunk (Cleopatra's kind, math unchanged -- see module
    docstring point 1): mov.l @(disp,PC),r0 ; jmp @r0 ; nop ; [pad] ; .long target.
    `expect` = the first opcode (u16) at dat_off (entry-point guard)."""
    old0 = struct.unpack("<H", rd(dat_off, 2))[0]
    assert old0 == expect, f"hook @dat:{dat_off:#x}: found {old0:#06x}, expected {expect:#06x}"
    slot = (dat_off + 6 + 3) & ~3            # 4-align the pooled .long
    pad = slot - (dat_off + 6)
    disp = (slot - ((dat_off & ~3) + 4)) // 4
    assert 0 <= disp <= 255, hex(dat_off)
    code = struct.pack("<HHH", 0xD000 | disp, 0x402B, 0x0009)
    code += struct.pack("<H", 0x0009) * (pad // 2) + struct.pack("<I", target)
    _append(dat_off, rd(dat_off, len(code)), code, comment)


def _detour_code(w, target):
    """jmp-detour kind (new for this port; no Cleopatra analog -- Task 11's
    MAPLE-BOOT-STRATEGY needs a self-contained mid-body detour, not an entry
    hook). Layout (docs/kb/phase4-conversion.md §maple-patch-sites):

        +0x00  d201   mov.l @(0x01,PC),r2   ; r2 = the trampoline address
        +0x02  422b   jmp @r2
        +0x04  0009   nop                    ; delay slot
        +0x06  0009   [pad -- only if w%4==0, to 4-align the literal]
        +0x06/8  <32-bit trampoline address>

    `w` = window-start dat_offset. SH-4 `mov.l @(1,PC),r2` at address A reads
    EA = ((A+4)&~3)+4 (PC-relative load; PC = insn addr + 4). Substituting
    A=w gives the literal's offset from w; both w%4 cases (0 and 2 -- SH-4
    code is only ever 2-aligned) are exercised by
    scripts/test_build_patch_table.py. Returns the code bytes (10 or 12 B);
    the caller is responsible for old-byte verification.
    """
    lit_off = 8 if w % 4 == 0 else 6
    total = lit_off + 4
    # The KB's own math, re-derived and asserted per entry (not just trusted
    # from the table) -- this is the literal-lands-inside-the-window guarantee.
    assert lit_off == (((w + 4) & ~3) + 4) - w, (hex(w), lit_off)
    assert lit_off + 4 <= total <= 12, (hex(w), lit_off, total)
    code = struct.pack("<HHH", 0xD201, 0x422B, 0x0009)
    if lit_off == 8:
        code += struct.pack("<H", 0x0009)
    code += struct.pack("<I", target & 0xFFFFFFFF)
    assert len(code) == total
    return code


def detour(dat_off, expect, target, comment=""):
    code = _detour_code(dat_off, target)
    old = rd(dat_off, len(code))
    assert old == expect, (
        f"detour @dat:{dat_off:#x}: found {old.hex()}, expected {expect.hex()}")
    _append(dat_off, old, code, comment)


def _selftest():
    # Money path: the old-byte verify is worthless unless a wrong expectation
    # raises. dat_off 0x0 is senkosp.dat's own header (never 0xdeadbeef in any
    # real image), so this needs no reloc/KB value and can run before any
    # definitions are loaded.
    n = len(patches)
    try:
        pool(0x0, 0xDEADBEEF, 0, "selftest (deliberately wrong expect)")
    except AssertionError:
        assert len(patches) == n, "selftest polluted the patch list"
        return
    sys.exit("SELFTEST FAILED: bad expectation did not raise")


# ---- definitions ------------------------------------------------------
_selftest()

# §Task 9: heap-top + KAMUI2-VRAM relocation seeds. scripts/reloc_patchset.json
# is the SINGLE SOURCE for these 4 words (Phase 3 dry-run-proven) -- every
# field (dat_offset/old/new/why) is read from the file, never re-typed here,
# so the two can never drift.
_RELOC = json.loads((ROOT / "scripts/reloc_patchset.json").read_text())
for _r in _RELOC:
    _off, _old, _new = int(_r["dat_offset"], 16), int(_r["old"], 16), int(_r["new"], 16)
    _why = _r["why"]
    _comment = _why if len(_why) <= 96 else _why[:96].rstrip() + "..."
    pool(_off, _old, _new, _comment)

# ---- CART-* (Task 10, docs/kb/phase4-conversion.md §Cart-patch sites) -----
# Every cart/G1 register constant in either image is repointed into G1_MIRROR,
# so the game's DMA programming writes shim RAM instead of Dreamcast G1 regs.
#
# Rows are (KB entry #, dat_offset, old u32, register, anchor) transcribed from
# the KB's two 32-row tables -- §"The full patch table — main image" and
# §"Test image — the same 32 words, the same shape". `new` is never written
# here: it is G1_MIRROR_P2 + (old & 0x7ff), the KB's own symbolic rule, so the
# doc and this file cannot drift. Entries 30-32 of each image are the KB's
# written exemptions (crash-dump register list, read-only from a trap handler,
# and reads of SB_GDSTAR/GDLEN/GDDIR are side-effect free) and are listed here
# as comments only -- see the KB's Exemption block.
#
# Entry 29 IS repointed although it is a data-table word: it lives in the
# (register, value) init-pair list walked by FUN_8c02c584, and its paired value
# is 0, so repointing turns it into a free zero-init of mirror[0x418] -- the
# mirror invariant's initial state.
_CART_ROWS = [
    # main image
    (1,  0x0075e8, 0xA05F7000, "NAOMI_ROM_OFFSETH", "CART-BASE"),
    (2,  0x04626c, 0xA05F7418, "SB_GDST",           "BOOT-POOLS"),
    (3,  0x046274, 0xA05F703C, "NAOMI_DIMM_COMMAND", "BOOT-POOLS"),
    (4,  0x04627c, 0xA05F7014, "NAOMI_DMA_COUNT",   "BOOT-POOLS"),
    (5,  0x046368, 0xA05F74B8, "SB_GDAPRO",         "G1-TIMING"),
    (6,  0x04636c, 0xA05F7480, "SB_G1RRC",          "G1-TIMING"),
    (7,  0x046370, 0xA05F7484, "SB_G1RWC",          "G1-TIMING"),
    (8,  0x046374, 0xA05F7490, "SB_G1CRC",          "G1-TIMING"),
    (9,  0x046378, 0xA05F74A4, "SB_G1GDWC",         "G1-TIMING"),
    (10, 0x046424, 0xA05F7418, "SB_GDST",           "BOOT-POOLS"),
    (11, 0x04642c, 0xA05F7000, "NAOMI_ROM_OFFSETH", "CART-PIO"),
    (12, 0x046430, 0xA05F7004, "NAOMI_ROM_OFFSETL", "CART-PIO"),
    (13, 0x04643c, 0xA05F7008, "NAOMI_ROM_DATA",    "CART-PIO"),
    (14, 0x046530, 0xA05F7418, "SB_GDST",           "BOOT-POOLS"),
    (15, 0x046534, 0xA05F7004, "NAOMI_ROM_OFFSETL", "BOOT-POOLS"),
    (16, 0x04653c, 0xA05F7000, "NAOMI_ROM_OFFSETH", "BOOT-POOLS"),
    (17, 0x046540, 0xA05F7014, "NAOMI_DMA_COUNT",   "BOOT-POOLS"),
    (18, 0x046544, 0xA05F7010, "NAOMI_DMA_OFFSETL", "BOOT-POOLS"),
    (19, 0x046550, 0xA05F700C, "NAOMI_DMA_OFFSETH", "BOOT-POOLS"),
    (20, 0x046554, 0xA05F7404, "SB_GDSTAR",         "BOOT-POOLS"),
    (21, 0x046558, 0xA05F7408, "SB_GDLEN",          "BOOT-POOLS"),
    (22, 0x04655c, 0xA05F740C, "SB_GDDIR",          "BOOT-POOLS"),
    (23, 0x046a88, 0xA05F700C, "NAOMI_DMA_OFFSETH", "BOOT-POOLS"),
    (24, 0x047970, 0xA05F7418, "SB_GDST",           "CART-WAIT"),
    (25, 0x047adc, 0xA05F7418, "SB_GDST",           "CART-WAIT"),
    (26, 0x047b00, 0xA05F7068, "NAOMI_LED",         "BOOT-POOLS"),
    (27, 0x047c44, 0xA05F7418, "SB_GDST",           "CART-WAIT"),
    (28, 0x047e14, 0xA05F7418, "SB_GDST",           "CART-WAIT"),
    (29, 0x13c650, 0xA05F7418, "SB_GDST",           "BOOT-POOLS"),
    # 30-32 exempt: 0x13c718 SB_GDSTAR / 0x13c71c SB_GDLEN / 0x13c720 SB_GDDIR
    # test image (same 32 words, same order, same values -- KB §Test image)
    (1,  0x1795e0, 0xA05F7000, "NAOMI_ROM_OFFSETH", "CART-BASE"),
    (2,  0x1a2a98, 0xA05F7418, "SB_GDST",           "BOOT-POOLS"),
    (3,  0x1a2aa0, 0xA05F703C, "NAOMI_DIMM_COMMAND", "BOOT-POOLS"),
    (4,  0x1a2aa8, 0xA05F7014, "NAOMI_DMA_COUNT",   "BOOT-POOLS"),
    (5,  0x1a2b94, 0xA05F74B8, "SB_GDAPRO",         "G1-TIMING"),
    (6,  0x1a2b98, 0xA05F7480, "SB_G1RRC",          "G1-TIMING"),
    (7,  0x1a2b9c, 0xA05F7484, "SB_G1RWC",          "G1-TIMING"),
    (8,  0x1a2ba0, 0xA05F7490, "SB_G1CRC",          "G1-TIMING"),
    (9,  0x1a2ba4, 0xA05F74A4, "SB_G1GDWC",         "G1-TIMING"),
    (10, 0x1a2c50, 0xA05F7418, "SB_GDST",           "BOOT-POOLS"),
    (11, 0x1a2c58, 0xA05F7000, "NAOMI_ROM_OFFSETH", "CART-PIO"),
    (12, 0x1a2c5c, 0xA05F7004, "NAOMI_ROM_OFFSETL", "CART-PIO"),
    (13, 0x1a2c68, 0xA05F7008, "NAOMI_ROM_DATA",    "CART-PIO"),
    (14, 0x1a2d5c, 0xA05F7418, "SB_GDST",           "BOOT-POOLS"),
    (15, 0x1a2d60, 0xA05F7004, "NAOMI_ROM_OFFSETL", "BOOT-POOLS"),
    (16, 0x1a2d68, 0xA05F7000, "NAOMI_ROM_OFFSETH", "BOOT-POOLS"),
    (17, 0x1a2d6c, 0xA05F7014, "NAOMI_DMA_COUNT",   "BOOT-POOLS"),
    (18, 0x1a2d70, 0xA05F7010, "NAOMI_DMA_OFFSETL", "BOOT-POOLS"),
    (19, 0x1a2d7c, 0xA05F700C, "NAOMI_DMA_OFFSETH", "BOOT-POOLS"),
    (20, 0x1a2d80, 0xA05F7404, "SB_GDSTAR",         "BOOT-POOLS"),
    (21, 0x1a2d84, 0xA05F7408, "SB_GDLEN",          "BOOT-POOLS"),
    (22, 0x1a2d88, 0xA05F740C, "SB_GDDIR",          "BOOT-POOLS"),
    (23, 0x1a32b4, 0xA05F700C, "NAOMI_DMA_OFFSETH", "BOOT-POOLS"),
    (24, 0x1a419c, 0xA05F7418, "SB_GDST",           "CART-WAIT"),
    (25, 0x1a4308, 0xA05F7418, "SB_GDST",           "CART-WAIT"),
    (26, 0x1a432c, 0xA05F7068, "NAOMI_LED",         "BOOT-POOLS"),
    (27, 0x1a4470, 0xA05F7418, "SB_GDST",           "CART-WAIT"),
    (28, 0x1a4640, 0xA05F7418, "SB_GDST",           "CART-WAIT"),
    (29, 0x1b247c, 0xA05F7418, "SB_GDST",           "BOOT-POOLS"),
    # 30-32 exempt: 0x1b2544 SB_GDSTAR / 0x1b2548 SB_GDLEN / 0x1b254c SB_GDDIR
]
for _n, _off, _old, _reg, _anchor in _CART_ROWS:
    pool(_off, _old, G1_MIRROR_P2 + (_old & 0x7FF),
         f"#{_n} {_reg} -> G1 mirror ({_anchor})")
assert len(_CART_ROWS) == 58, "cart pool rows: 29 per image, KB entries 1-29"

# The four entry hooks (§Cart-patch sites "Four entry hooks" + §Test image
# "Test-image hook sites"). `expect` is the entry's first opcode, byte-read
# from senkosp.dat and cross-checked against the KB's own disassembly:
#   0x2fe6 mov.l r14,@-r15   (FUN_8c027e5e prologue; boot_cart_dma prologue is
#                             byte-verified as 2fe6 in the KB)
#   0xe058 mov #0x58,r0      (FUN_8c027e34's first insn -- it loads obj->[0x58]
#                             via `mov.l @(r0,r4),r0`, which is also the
#                             evidence that r4, not r5, is `obj` here)
#   0xd212 mov.l @(0x12,PC),r2 (the PIO reader's first insn, quoted verbatim in
#                             §CART-PIO's DisasmRange listing)
# ABIs differ per site, so each gets its own shim entry (shims/src/cart.c).
for _off, _exp, _fn, _what in [
    (0x007e5e, 0x2FE6, "shim_cart_service",  "CART-WAIT-A main: FUN_8c027e5e DMA-completion wait"),
    (0x179e56, 0x2FE6, "shim_cart_service",  "CART-WAIT-A test: FUN_8c027e5e DMA-completion wait"),
    (0x007e34, 0xE058, "shim_cart_settle",   "CART-WAIT-B main: FUN_8c027e34 settle/abort"),
    (0x179e2c, 0xE058, "shim_cart_settle",   "CART-WAIT-B test: FUN_8c027e34 settle/abort"),
    (0x046440, 0x2FE6, "shim_cart_boot_dma", "CART-BOOT-DMA main: boot cart DMA 0x8c066440"),
    (0x1a2c6c, 0x2FE6, "shim_cart_boot_dma", "CART-BOOT-DMA test: boot cart DMA 0x8c050c74"),
    (0x0463e6, 0xD212, "shim_cart_pio",      "CART-PIO-READ main: boot PIO reader 0x8c0663e6"),
    (0x1a2c12, 0xD212, "shim_cart_pio",      "CART-PIO-READ test: boot PIO reader 0x8c050c1a"),
]:
    hook(_off, _exp, sym(_fn), _what)

# ---- MAPLE-* (Task 11, docs/kb/phase4-conversion.md §Maple-patch sites) ---
# NOT WIRED YET: shim_maple_service / the 5 boot-detour trampolines aren't in
# shim.map. Scaffolding for Task 11 to fill in:
#
#   20-row main + 20-row test tables (1 base repoint + 17 pool/init-table
#   repoints + 2 *exempt* each):
#     pool(dat_off, old_u32, MAPLE_MIRROR_P2 + (old_u32 & 0xff), "...")
#   MAPLE-KICK-HOOK (fn-ptr slot, main/test dat 0x0054c0 / 0x1774b8):
#     ptr(dat_off, 0x8C02A17E, sym("shim_maple_service"), "MAPLE-KICK-HOOK")
#   5 boot detours (MAPLE-BOOT-A..E; §MAPLE-BOOT-STRATEGY table gives each
#   site's exact `expect` bytes -- the "replaced halfwords" column -- and its
#   dat_offset per image):
#     detour(dat_off, bytes.fromhex("..."), sym("shim_maple_boot_a"), "MAPLE-BOOT-A")

# ---- RESET-PATCH (docs/kb/phase4-conversion.md §Restart stub) -------------
# FUN_8c067e18's single `jmp @r1` loads r1 from this pool word one instruction
# earlier and nothing between can redirect it, so rewriting this one word per
# image turns the Naomi-BIOS re-entry (0x8dfff000, not there on a DC) into the
# shim's reboot routine. Wired in Task 10 (not 13): the shim entry exists now,
# and a live restart path is safer than one that jumps into nothing the moment
# any code reaches it. The copy-destination pool (0x47e3c / 0x1a4668,
# 0xadfff000) stays unpatched -- it is only CALL #1's argument.
ptr(0x047e4c, 0x8DFFF000, sym("shim_reboot"), "RESET-PATCH main: restart -> DC reboot")
ptr(0x1a4678, 0x8DFFF000, sym("shim_reboot"), "RESET-PATCH test: restart -> DC reboot")

# ---- emit -------------------------------------------------------------
def _row(dat_off, img, old, new, what):
    old_b = list(old) + [0] * (12 - len(old))
    new_b = list(new) + [0] * (12 - len(new))
    old_s = ",".join(f"0x{b:02x}" for b in old_b)
    new_s = ",".join(f"0x{b:02x}" for b in new_b)
    what_s = what.replace("\\", "\\\\").replace('"', '\\"')
    return (f'  {{0x{dat_off:08x}u, {img}u, {len(old)}u, '
            f'{{{old_s}}}, {{{new_s}}}, "{what_s}"}}')


def _emit_array(arr_name, plist, count_name):
    if plist:
        rows = ",\n".join(_row(*p) for p in plist)
        body = f"static const patch_t {arr_name}[] = {{\n{rows}\n}};"
    else:
        body = f"static const patch_t {arr_name}[1] = {{{{0}}}};"
    return body + f"\nenum {{ {count_name} = {len(plist)} }};"


main_patches = [p for p in patches if p[1] == 0]
test_patches = [p for p in patches if p[1] == 1]

out = [
    "/* GENERATED by scripts/build_patch_table.py - do not edit, do not commit",
    " * (embeds original .dat bytes read at generation time). */",
    "typedef struct {",
    "  unsigned int dat_off;",
    "  unsigned char img;      /* 0 = main image, 1 = test image */",
    "  unsigned char len;",
    "  unsigned char old[12];",
    "  unsigned char neu[12];",
    "  const char *what;",
    "} patch_t;",
    _emit_array("senkosp_patches_main", main_patches, "N_PATCHES_MAIN"),
    _emit_array("senkosp_patches_test", test_patches, "N_PATCHES_TEST"),
]
(ROOT / "build").mkdir(exist_ok=True)
(ROOT / "build/patch_table.h").write_text("\n".join(out) + "\n")
print(f"OK patch_table.h: {len(main_patches)} main + {len(test_patches)} test patches "
      f"(reloc seeds + CART-* repoints/hooks + RESET-PATCH; maple scaffolded, not "
      f"wired -- Task 11); G1_MIRROR_P2={G1_MIRROR_P2:#010x} "
      f"MAPLE_MIRROR_P2={MAPLE_MIRROR_P2:#010x}")

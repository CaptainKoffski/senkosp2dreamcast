#!/usr/bin/env python3
"""Generate build/patch_table.h from patch definitions + senkosp.dat +
shims/build/shim.map + shims/include/shim_iface.h.

senkosp's rows only. The mechanism -- raw-.dat-offset addressing, img tags,
the pool/ptr/hook/detour/carve kinds and their old-byte verification, the
self-test, the header emission -- is the kit's kit/scripts/patchgen.py.

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
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "kit/scripts"))
from patchgen import Gen  # noqa: E402  (after sys.path setup)
import port_def  # noqa: E402  (scripts/port_def.py, same directory)

DAT_PATH = ROOT / port_def.DAT
if not DAT_PATH.exists():
    sys.exit(f"{DAT_PATH} missing (gitignored, regenerable -- docs/kb/tooling.md)")

g = Gen(dat=DAT_PATH.read_bytes(),
        iface_text=(ROOT / "shims/include/shim_iface.h").read_text(),
        shim_map_text=(ROOT / "shims/build/shim.map").read_text(),
        reloc=json.loads((ROOT / "scripts/reloc_patchset.json").read_text()),
        tramp_text=(ROOT / "shims/src/mtramp.S").read_text())

# ---- definitions ------------------------------------------------------
# §Task 9: heap-top + KAMUI2-VRAM relocation seeds. scripts/reloc_patchset.json
# is the SINGLE SOURCE for these 4 words (Phase 3 dry-run-proven) -- every
# field (dat_offset/old/new/why) is read from the file, never re-typed here,
# so the two can never drift.
for _r in g.reloc:
    _off, _old, _new = int(_r["dat_offset"], 16), int(_r["old"], 16), int(_r["new"], 16)
    _why = _r["why"]
    _comment = _why if len(_why) <= 96 else _why[:96].rstrip() + "..."
    g.pool(_off, _old, _new, _comment)

# ---- HEAP-CARVE (Task 6, task-3b-report.md §FIX ROUND 1) ------------------
# Conditional heap-top carve: applied by the loader ONLY when backend ==
# syscall (isoldr preset), AFTER the unconditional table above. A dedicated
# helper because this is the first entry whose window OVERLAPS an already-
# emitted reloc word (dat 0x65b50/0x1af894, the heap-top seed) -- pool()'s
# `old` comes from the pristine DAT via rd() and would trip its own assert
# against the post-reloc byte. carve() instead derives the post-reloc `old`
# by overlaying every intersecting reloc word from g.reloc (single source, no
# hand-typed second copy), so its memcmp sees what the runtime loader's
# unconditional table has already written by the time this table runs.

# soft-reset-menu (2026-10-10): UNCONDITIONAL and 64 KB deeper. New top
# 0x8cfe0000: `mov #-0x73,r0; shll8; add #-2; shll16` (was add #-1 ->
# 0x8cff0000). [0x8cfe0000,0x8cff0000) = BIOSRAM_SNAP (shim_iface.h), the
# loader's pre-handoff copy of the DC BIOS syscall RAM that the shim's
# pad-combo warm boot restores; [0x8cff0000,0x8d000000) stays isoldr's.
g.carve(0x65b4e, "00e08ecb28401840", "8de01840fe702840",
        "HEAP-CARVE main: top 0x8d000000 -> 0x8cfe0000 (BIOSRAM_SNAP + isoldr preset)")
g.carve(0x1af892, "00e08ecb28401840", "8de01840fe702840",
        "HEAP-CARVE test: twin window, same bytes")

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
    g.pool(_off, _old, g.G1_MIRROR_P2 + (_old & 0x7FF),
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
    g.hook(_off, _exp, g.sym(_fn), _what)

# ---- MAPLE-* (Task 11, docs/kb/phase4-conversion.md §Maple-patch sites) ---
# Every maple register constant in either image is repointed into MAPLE_MIRROR,
# so the game's maple programming writes shim RAM instead of Dreamcast maple
# registers. Rows are (KB entry #, dat_offset, old u32, register) transcribed
# from the KB's two 20-row tables -- §"The full patch table — main image" and
# §"Test image — the same 20 words, the same shape". `new` is never written
# here: it is MAPLE_MIRROR_P2 + (old & 0xff), the KB's own symbolic rule.
# Entries 19-20 of each image are the KB's written exemption (the crash-dump
# register list: read-only, from a trap handler, and reading SB_MDSTAR /
# SB_MDTSEL is side-effect free) and appear as comments only.
#
# Entries 12-18 ARE repointed although they are data-table words: they live in
# the (register, value) init-pair list walked by FUN_8c02c584, so repointing
# turns them into a free, correct zero-init of the mirror -- including
# mirror[0x18] = 0 (the completion invariant's initial state) and SB_MMSEL = 1,
# which §MIE-DESC's "no byte swap" conclusion depends on.
_MAPLE_ROWS = [
    # main image
    (1,  0x006b58, 0xA05F6C00, "block base",  "MAPLE-BASE"),
    (2,  0x04664c, 0xA05F6C14, "SB_MDEN",     "MAPLE-BOOT"),
    (3,  0x04678c, 0xA05F6C04, "SB_MDSTAR",   "MAPLE-BOOT"),
    (4,  0x04682c, 0xA05F6C04, "SB_MDSTAR",   "MAPLE-BOOT"),
    (5,  0x046958, 0xA05F6C04, "SB_MDSTAR",   "MAPLE-BOOT"),
    (6,  0x046ac0, 0xA05F6C14, "SB_MDEN",     "MAPLE-BOOT"),
    (7,  0x046ac8, 0xA05F6C8C, "SB_MDAPRO",   "MAPLE-BOOT"),
    (8,  0x046ad0, 0xA05F6C80, "SB_MSYS",     "MAPLE-BOOT"),
    (9,  0x046ad4, 0xA05F6C10, "SB_MDTSEL",   "MAPLE-BOOT"),
    (10, 0x046ad8, 0xA05F6C04, "SB_MDSTAR",   "MAPLE-BOOT"),
    (11, 0x046adc, 0xA05F6C18, "SB_MDST",     "MAPLE-BOOT"),
    (12, 0x13c4c8, 0xA05F6C04, "SB_MDSTAR",   "MAPLE-BOOT init-pair"),
    (13, 0x13c4d0, 0xA05F6C10, "SB_MDTSEL",   "MAPLE-BOOT init-pair"),
    (14, 0x13c4d8, 0xA05F6C14, "SB_MDEN",     "MAPLE-BOOT init-pair"),
    (15, 0x13c4e0, 0xA05F6C80, "SB_MSYS",     "MAPLE-BOOT init-pair"),
    (16, 0x13c4e8, 0xA05F6C8C, "SB_MDAPRO",   "MAPLE-BOOT init-pair"),
    (17, 0x13c4f0, 0xA05F6CE8, "SB_MMSEL",    "MAPLE-BOOT init-pair"),
    (18, 0x13c648, 0xA05F6C18, "SB_MDST",     "MAPLE-BOOT init-pair"),
    # 19-20 exempt: 0x13c710 SB_MDSTAR / 0x13c714 SB_MDTSEL (crash-dump list)
    # test image (same 20 words, same order, same values -- KB §Test image)
    (1,  0x178b50, 0xA05F6C00, "block base",  "MAPLE-BASE"),
    (2,  0x1a2e78, 0xA05F6C14, "SB_MDEN",     "MAPLE-BOOT"),
    (3,  0x1a2fb8, 0xA05F6C04, "SB_MDSTAR",   "MAPLE-BOOT"),
    (4,  0x1a3058, 0xA05F6C04, "SB_MDSTAR",   "MAPLE-BOOT"),
    (5,  0x1a3184, 0xA05F6C04, "SB_MDSTAR",   "MAPLE-BOOT"),
    (6,  0x1a32ec, 0xA05F6C14, "SB_MDEN",     "MAPLE-BOOT"),
    (7,  0x1a32f4, 0xA05F6C8C, "SB_MDAPRO",   "MAPLE-BOOT"),
    (8,  0x1a32fc, 0xA05F6C80, "SB_MSYS",     "MAPLE-BOOT"),
    (9,  0x1a3300, 0xA05F6C10, "SB_MDTSEL",   "MAPLE-BOOT"),
    (10, 0x1a3304, 0xA05F6C04, "SB_MDSTAR",   "MAPLE-BOOT"),
    (11, 0x1a3308, 0xA05F6C18, "SB_MDST",     "MAPLE-BOOT"),
    (12, 0x1b22f4, 0xA05F6C04, "SB_MDSTAR",   "MAPLE-BOOT init-pair"),
    (13, 0x1b22fc, 0xA05F6C10, "SB_MDTSEL",   "MAPLE-BOOT init-pair"),
    (14, 0x1b2304, 0xA05F6C14, "SB_MDEN",     "MAPLE-BOOT init-pair"),
    (15, 0x1b230c, 0xA05F6C80, "SB_MSYS",     "MAPLE-BOOT init-pair"),
    (16, 0x1b2314, 0xA05F6C8C, "SB_MDAPRO",   "MAPLE-BOOT init-pair"),
    (17, 0x1b231c, 0xA05F6CE8, "SB_MMSEL",    "MAPLE-BOOT init-pair"),
    (18, 0x1b2474, 0xA05F6C18, "SB_MDST",     "MAPLE-BOOT init-pair"),
    # 19-20 exempt: 0x1b253c SB_MDSTAR / 0x1b2540 SB_MDTSEL (crash-dump list)
]
for _n, _off, _old, _reg, _anchor in _MAPLE_ROWS:
    g.pool(_off, _old, g.MAPLE_MIRROR_P2 + (_old & 0xFF),
           f"#{_n} {_reg} -> maple mirror ({_anchor})")
assert len(_MAPLE_ROWS) == 36, "maple pool rows: 18 per image, KB entries 1-18"

# The five boot detours (§MAPLE-BOOT-STRATEGY). Each window is the
# `SB_MDEN = 1 / kick / poll` run (+ the trailing `SB_MDEN = 0` at A/C/D/E);
# `expect` is the KB's "replaced halfwords" column, byte-verified against
# senkosp.dat by detour() itself. The two images are byte-identical over all
# five windows, so only the dat_offset and the trampoline differ.
#
# WINDOW LENGTH IS NOT FREE: it is 10 or 12 bytes purely from the window's
# alignment (detour() derives the literal slot from dat_offset % 4 and asserts
# the KB's own formula), and the trampoline's resume address must be
# window_ram + that length. src/mtramp.S bakes the resume addresses;
# scripts/test_build_patch_table.py cross-checks them against this table so
# the two cannot drift.
MAPLE_BOOT_SITES = [
    # (site, main dat_off, test dat_off, expect halfwords)
    ("a", 0x046724, 0x1a2f50, "2e72 2572 6252 2228 8bfc 2ec2"),
    ("b", 0x04680e, 0x1a303a, "2e72 2572 6252 2228 8bfc"),
    ("c", 0x0468a0, 0x1a30cc, "2e72 2572 6252 2228 8bfc 2ec2"),
    ("d", 0x046924, 0x1a3150, "2e72 2572 6252 2228 8bfc 2ec2"),
    ("e", 0x046a5c, 0x1a3288, "2c52 2452 6242 2228 8bfc 2c72"),
]
# MAPLE-KICK-HOOK (§MAPLE-KICK-HOOK verdict: "1 pool repoint, hook kind =
# fn-ptr slot"). [0x8c0254c0] = 0x8c02a17e has exactly one pc-relative loader
# (0x8c025442), so this word alone converts the steady engine's existing
# `jsr @r3` into the service hook. Wired in Task 11, not 12: the JVS
# enumeration the boot I/O-board gate tests runs on THIS engine (see
# shim_maple_service's comment + the Task 11 report's leg chain).
g.ptr(0x0054c0, 0x8C02A17E, g.sym("shim_maple_service"), "MAPLE-KICK-HOOK main")
g.ptr(0x1774b8, 0x8C02A17E, g.sym("shim_maple_service"), "MAPLE-KICK-HOOK test")

for _site, _main, _test, _hw in MAPLE_BOOT_SITES:
    # The KB writes the window as big-endian halfwords ("2e72 2572 ..."); the
    # image stores them little-endian, so each pair is byte-swapped here --
    # one transcription of the KB's own column, no second hand-typed form.
    _hw = _hw.replace(" ", "")
    _exp = bytes.fromhex("".join(_hw[i + 2:i + 4] + _hw[i:i + 2]
                                 for i in range(0, len(_hw), 4)))
    assert len(_exp) == len(g.detour_code(_main, 0)) == len(g.detour_code(_test, 0)), (
        f"MAPLE-BOOT-{_site.upper()}: KB window is {len(_exp)} B but the detour "
        f"needs {len(g.detour_code(_main, 0))} B at this alignment")
    g.detour(_main, _exp, g.sym(f"shim_mb_{_site}_main"),
             f"MAPLE-BOOT-{_site.upper()} main: kick+poll detour")
    g.detour(_test, _exp, g.sym(f"shim_mb_{_site}_test"),
             f"MAPLE-BOOT-{_site.upper()} test: kick+poll detour")
    g.resume_check(_site, "main", _main, len(_exp))
    g.resume_check(_site, "test", _test, len(_exp))

# ---- RESET-PATCH (docs/kb/phase4-conversion.md §Restart stub) -------------
# FUN_8c067e18's single `jmp @r1` loads r1 from this pool word one instruction
# earlier and nothing between can redirect it, so rewriting this one word per
# image turns the Naomi-BIOS re-entry (0x8dfff000, not there on a DC) into the
# shim's reboot routine. Wired in Task 10 (not 13): the shim entry exists now,
# and a live restart path is safer than one that jumps into nothing the moment
# any code reaches it. The copy-destination pool (0x47e3c / 0x1a4668,
# 0xadfff000) stays unpatched -- it is only CALL #1's argument.
g.ptr(0x047e4c, 0x8DFFF000, g.sym("shim_reboot"), "RESET-PATCH main: restart -> DC reboot")
g.ptr(0x1a4678, 0x8DFFF000, g.sym("shim_reboot"), "RESET-PATCH test: restart -> DC reboot")

# (BOOT-UNBLANK op16 patches lived here 2026-09-01 for a few hours: three
# `or #8,r0` blank-set sites suppressed so the boot gap showed the splash.
# ROLLED BACK same day on operator hardware verdict -- the gap looked
# unchanged on the real setup and a glitch row flashed at the mode switch.
# The full recon (gap scanout content, the three sites, the change-only-
# logging census lesson) is preserved in docs/kb/phase5-hardware.md
# §Black-gap decorate + §Loading bar rollback; resurrect from git history
# commit 7476d47 if ever wanted again.)

# ---- G-CARVE (r8, docs/kb/phase5-hardware.md §Round 6 prep) ---------------
# Reloc entry 4's -0x11A000 TA total makes the library's own 3/4 carve set
# ISP to 0x5a4e0 = 369,888 -- below the measured demand max 0x664e0 -- so the
# KAMUI2 init chain's stage-7 pool word (FUN_8c02e300, dat 0xe4ec ->
# FUN_8c031af0) is repointed at shim_g_carve, which runs the original stage
# then stomps ispl/oll dev words + descriptor copies to the operator-accepted
# +10% layout (ispl=0x711e0, oll=0x712e0). Main image only: the test image
# has no reloc-entry-4 twin (it keeps stock -0x40000 TA, where the stock
# carve is correct).
g.ptr(0x00e4ec, 0x8C031AF0, g.sym("shim_g_carve"), "G-CARVE main: KAMUI2 carve stomp")

# ---- E-PREFREE (r8, docs/kb/phase5-hardware.md §Round 6 prep) -------------
# Mode-select's task entry loads MODESEL.PAK before the match task's teardown
# tail has freed the match textures (+362,496 transition spike = the T1
# binding term). Repoint the scene's by-name-loader pool word at the shim
# wrapper, which first calls the game's own PAK unloader FUN_8c0b5cf4 on the
# match scene's static resource array (0x8c1cfb50, teardown site 0x8c08498e)
# with mask 1 (VRAM textures only), then runs the original load. Idempotent:
# the unloader nulls slots it frees and skips null slots.
g.ptr(0x13930c, 0x8C0B5BE8, g.sym("shim_e_prefree"), "E-PREFREE main: MODESEL load frees match textures first")

# ---- MONITOR-SENSE-HOOK (Task 31, composite sync fix) ---------------------
# The game's one display init uses mode 0x80000038 bit31 "auto": the SDK
# wrapper FUN_8c03d48e queries the monitor sense FUN_8c02a0ea and picks the
# class itself (0 -> 31 kHz, 1 -> the SDK's own 15 kHz builder, 2 -> PAL);
# explicit-class requests are validated against the same sense. The sense
# reads a cached monitor code (0x8c170d88) only Naomi BIOS/DIP init ever
# populates -- post-BIOS-bypass it always says 31 kHz, so a TV cable never
# syncs (operator composite leg 2026-09-03: black screen, game alive).
# Repointing the sense's single fn-ptr pool word per image (whole-.dat u32
# scan: exactly one each; the SDK core links at the same address in both
# images) makes the SDK's own auto+validate logic run against the real DC
# cable. A mode-word hook at the call site instead trips the wrapper's
# `return -1` validation (measured, comp-dbg leg). Full RE:
# docs/kb/phase6-release.md §composite fix.
g.ptr(0x01d5a8, 0x8C02A0EA, g.sym("shim_monitor_sense"), "MONITOR-SENSE-HOOK main: monitor sense -> DC cable")
g.ptr(0x18f020, 0x8C02A0EA, g.sym("shim_monitor_sense"), "MONITOR-SENSE-HOOK test: monitor sense -> DC cable")

# ---- VIDEO-GEOM-HOOK (Task 31 round 2, TV centering) ----------------------
# The SDK's 15 kHz builder programs arcade-monitor geometry (536-line frame,
# active start 0x17): picture sits ~10% low on a consumer TV (operator photo,
# docs/kb/img/phase6-composite-shift.jpeg). Wrap the game's one display-init
# call (single fn-ptr pool word per image, same scan as the sense hook) and,
# on non-VGA cables only, restore the six SPG/VO geometry regs to KOS's
# DC-native NTSC-IL values after the SDK's own mode-set completes. Mode word
# passes through untouched (bit30 lesson). VGA: pure pass-through.
g.ptr(0x04edcc, 0x8C03D48E, g.sym("shim_vid_init_main"), "VIDEO-GEOM-HOOK main: display init + TV geometry fixup")
g.ptr(0x1aa9c0, 0x8C03CF0E, g.sym("shim_vid_init_test"), "VIDEO-GEOM-HOOK test: display init + TV geometry fixup")

# ---- VBL-SPIN (Phase 7 T7 round 4, boot-gap spinner) ----------------------
# The game's interrupt-callback registrar (0x8c039060) loads its callback fn
# 0x8c038f00 from one literal-pool word and registers it for every source it
# handles -- the vblank among them, and the vblank ISR runs all through the
# ~3.4 s boot gap (fork GAPISR probe: 203 acks ~60 Hz, all via the
# list-walker dispatch at 0x8c02bf12, pr=8c02bf18). Repointing the literal
# makes the game install the shim's wrapper (spinner tick self-gated on the
# splash side-buffer scanout, then tail-jump to the original). Whole-.dat
# u32 scan: exactly ONE hit (main image; the test image does not carry the
# literal and keeps the stock callback -- no spinner in test mode, fine).
g.ptr(0x0191cc, 0x8C038F00, g.sym("shim_int_spin"), "VBL-SPIN main: interrupt callback -> gap spinner wrapper")

# ---- VIDINIT-WRITEFILTER (Phase 7 T7 round 8, splash continuity) ----------
# The game's vid-init disturbs the LIVE video signal (t8-pin-vga census:
# FB_R_CTRL read-enable off ~9 ms, SPG H/V totals changed ~2 ms, blank set
# x3) -- the boot blink no restore-after can hide from a real monitor.
# Every such write goes through the single two-insn write helper 0x8c032140
# (r4 = PVR reg offset, r5 = value); exactly FOUR functions fire inside the
# vid-init window (census prs 8c03890e/8c038914, 8c036c1a..8c036cea,
# 8c03625a..8c036292, 8c035378..8c0353a0), each loading the helper address
# from ONE literal-pool word with a single load site (boot.dis scan).
# Repoint those four literals to the shim filter: while vid_init_pinned has
# the game's vid-init on the stack it drops the signal-shaping writes
# (end-states provably equal the loader's values today) and defers
# FB_R_SIZE to the wrapper exit; window closed -> pure pass-through (the
# gap-end display-on arm and all later calls are byte-identical). The 25
# OTHER pool words holding 0x8c032140 (whole-.dat scan) stay stock: their
# callers never fire in-window, and pass-through-always needs no filter.
# Test image: its own copies of these functions keep stock literals.
# NB the fb-off fn runs BEFORE the wrapped vid-init call (t7r8-comp census:
# its FB_R_CTRL=0 landed at .168, window opened .17x) -- it gets the
# unconditional variant; the other three are callees of the wrapped entry.
g.ptr(0x018954, 0x8C032140, g.sym("shim_pvr_write_pre"), "VIDINIT-WRITEFILTER: fb-off/size-clear fn, pre-window (pr=8c03890e)")
g.ptr(0x016c80, 0x8C032140, g.sym("shim_pvr_write"), "VIDINIT-WRITEFILTER: raster apply fn (pr=8c036cea)")
g.ptr(0x0162b4, 0x8C032140, g.sym("shim_pvr_write"), "VIDINIT-WRITEFILTER: fb-config fn (pr=8c036292)")
g.ptr(0x0153c4, 0x8C032140, g.sym("shim_pvr_write"), "VIDINIT-WRITEFILTER: display-arm fn (pr=8c035398)")

# ---- emit -------------------------------------------------------------
(ROOT / "build").mkdir(exist_ok=True)
(ROOT / "build/patch_table.h").write_text(g.emit(port_def.PATCH_PREFIX))


def _count(plist, img):
    return sum(p[1] == img for p in plist)


print(f"OK patch_table.h: {_count(g.patches, 0)} main + {_count(g.patches, 1)} test patches "
      f"(reloc seeds + CART-* repoints/hooks + MAPLE-* repoints/detours + "
      f"RESET-PATCH); {_count(g.carves, 0)} main + {_count(g.carves, 1)} test carve "
      f"entries (backend==syscall only); G1_MIRROR_P2={g.G1_MIRROR_P2:#010x} "
      f"MAPLE_MIRROR_P2={g.MAPLE_MIRROR_P2:#010x}")

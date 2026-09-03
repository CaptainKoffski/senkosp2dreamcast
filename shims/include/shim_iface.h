/* Single source of truth for Phase 4 addresses. Consumed by shim (freestanding),
 * loader (KOS), and scripts/build_patch_table.py (parses the #defines).
 * RAM map: spec 2026-08-22 §RAM map (corrected shim home 0x8c010000). */
#ifndef SHIM_IFACE_H
#define SHIM_IFACE_H

#define SHIM_BASE       0x8c010000  /* low window; Task 2 write-watch verified */
#define SHIM_CODE_MAX   0x00004000  /* 16 KB code+rodata+data+bss budget */
#define SHIM_END        0x8c018000  /* exclusive: BIOS blob home starts here */

/* Fixed data blocks (offsets from SHIM_BASE, accessed via P2) */
#define SHIM_ERR        (SHIM_BASE + 0x4000)  /* u32[4]: code, a, b, magic */
#define G1_MIRROR       (SHIM_BASE + 0x4800)  /* 0x800: fake 0x5f7000-0x5f77ff */
#define MAPLE_MIRROR    (SHIM_BASE + 0x5000)  /* 0x100: fake 0x5f6c00-0x5f6cff */
#define MAPLE_MIRROR_LEN 0x100
#define MAPLE_TX        (SHIM_BASE + 0x5100)  /* 32-byte aligned descriptor+frame */
#define MAPLE_RX        (SHIM_BASE + 0x5140)
#define SHIM_STATE      (SHIM_BASE + 0x5200)  /* u32[8]: [0]=boot mode 0=main 1=test */
#define SHIM_BOUNCE     (SHIM_BASE + 0x5800)  /* 2048-byte sector bounce */
#define GD_STACK_BOTTOM (SHIM_BASE + 0x6000)  /* 8 KB reserved/spare (gdstack.S deleted Task 10) */
#define GD_STACK_TOP    (SHIM_BASE + 0x8000)  /* = SHIM_END */

/* Phase 7 T1: dual-backend GD dispatch. SHIM_STATE[SHIM_STATE_GD_BACKEND]
 * = 0 raw ATA (real-BIOS boots, GDEMU/optical) / 1 BIOS-syscall (DreamShell
 * isoldr). Seeded by the loader after the rehearsal probe (main.c). */
#define SHIM_STATE_GD_BACKEND 1
/* Canary at the bottom of the private syscall stack (gdstack.S swaps r15 to
 * GD_STACK_TOP; isoldr's FatFs+SPI runs on it -- Cleopatra measured >2 KB,
 * we reserve 8 KB and VERIFY instead of hoping; spec decision 5). Seeded by
 * the loader at staging (nonzero: the window memset would zero it). */
#define GD_STACK_CANARY 0x57ac6a2d

/* Loader-placed BIOS-derived blocks (outside shim home).
 *
 * KERNEL-SLICE pin (docs/kb/phase4-conversion.md §"Low-RAM placements — spec
 * pin P6 (KERNEL-SLICE), BLOB-CHECK"): the plan's single-`dd` recipe (one
 * contiguous ROM copy starting at KERNEL_DST) does not work -- a ROM offset
 * for RAM 0x600 would be negative. The window [0x600,0x3800) is THREE
 * pieces, byte-compare verified against tools/ram-snapshot.bin:
 *   A 0x600-0x800 (0x200 B): snapshot-only (no ROM source; boot-time-
 *     constructed vector stub, per the pin's residual-risk note)
 *   B 0x800-0x1000 (0x800 B): zero-fill (snapshot reads all-zero here)
 *   C 0x1000-0x3800 (0x2800 B): BIOS ROM, ROM_OFF=0x800 -- byte-identical,
 *     md5 ea73283fdfebdc2d0546e41af2da356d (both sides)
 * bios_data.bin layout (loader/Makefile): [BIOS60000_LEN][KERNEL_A_LEN]
 * [KERNEL_B_LEN][KERNEL_C_LEN] concatenated; offsets computed below so the
 * loader indexes by name, not magic numbers. */
#define KERNEL_DST      0x8c000600  /* Naomi RTOS kernel slice; len = Task 5 KERNEL-SLICE */
#define KERNEL_A_LEN    0x00000200  /* snapshot-only piece */
#define KERNEL_B_LEN    0x00000800  /* zero-fill piece */
#define KERNEL_C_LEN    0x00002800  /* BIOS ROM piece, ROM skip=0x800 */
#define KERNEL_TOTAL_LEN (KERNEL_A_LEN + KERNEL_B_LEN + KERNEL_C_LEN)  /* 0x3200 */
#define BIOS60000_DST   0x8c018000  /* 28,672 B blob; FUN_8c065ff0 contract */
#define BIOS60000_LEN   0x7000

/* bios_data.bin byte offsets (blob first, then the three kernel pieces). */
#define BIOS_DATA_60000_OFF 0
#define BIOS_DATA_KERNEL_A_OFF (BIOS_DATA_60000_OFF + BIOS60000_LEN)
#define BIOS_DATA_KERNEL_B_OFF (BIOS_DATA_KERNEL_A_OFF + KERNEL_A_LEN)
#define BIOS_DATA_KERNEL_C_OFF (BIOS_DATA_KERNEL_B_OFF + KERNEL_B_LEN)
#define BIOS_DATA_TOTAL        (BIOS_DATA_KERNEL_C_OFF + KERNEL_C_LEN)  /* 0xa200 */

/* Game images (docs/kb/game.md §Parsed .dat header) */
#define GAME_LOAD_ADDR  0x8c020000
#define GAME_ENTRY      0x8c021000
#define MAIN_DAT_OFF    0x00000000
#define MAIN_LEN        0x00171ff8
#define TEST_DAT_OFF    0x00171ff8
#define TEST_LEN        0x0004dc40

#define STAGING_ADDR    0x8cd00000  /* 3 MB to RAM top; images are 1.5 MB / 311 KB */

/* GDI geometry — B5 donor-clone layout (make_gdi.py):
 * track04 = [loader zero-padded to the donor 3,538,944 B boot region][.dat] */
#define CART_FAD        451878      /* = donor CART_LBA 451728 + 150 */
/* Task 8 finding: was 0x0efb0000 (251,330,560) -- 0x3000 short of the
 * comment's own claimed value. 251,342,848 = 0xefb3000; caught by
 * make_gdi.py's CART_SIZE cross-check against len(senkosp.dat) before any
 * boot attempt (the assert it exists for). Functionally inert until now --
 * only gd_read_cart's range check (site 8) reads it, and that path is
 * compiled out of the loader build (GD_LOADER_BUILD). */
#define CART_SIZE       0x0efb3000  /* 251,342,848 = len(senkosp.dat) */

#define P2ADDR(a)       ((a) | 0xa0000000)
#ifndef HOST_TEST
#define P2(a)           ((volatile unsigned int *)P2ADDR(a))
#endif

/* HUD/diag toggles — same semantics as Cleopatra (util.c) */
#ifndef SHIM_HUD
#define SHIM_HUD 0              /* on-screen breadcrumbs+digits OFF (operator
                                 * request 2026-08-30: distracting during play;
                                 * serial carries the same data, and each paint
                                 * is a slow uncached VRAM write -- util.c:25).
                                 * shim_die fatal screens stay unconditional.
                                 * Re-enable per-build with -DSHIM_HUD=1. */
#endif
#ifndef SHIM_TEXHUD
#define SHIM_TEXHUD 0           /* HW round 3 texture autopsy + IEE edge logger
                                 * (main.c texhud block). Default OFF: with the
                                 * screen HUD dark it is a pure serial
                                 * instrument, and its SB_ISTERR write-1-clear
                                 * must not leak into silent release builds
                                 * (release = hands-off). SERIAL=1 builds turn
                                 * it back on via the top-level Makefile. */
#endif
#ifndef SHIM_GD_DIAG
#define SHIM_GD_DIAG 0          /* on-screen GD-syscall tracer (Cleopatra
                                 * G12): send/status/heartbeat/phase cells +
                                 * stack low-water. TV-debuggable, serial-
                                 * silent. NEVER ship 1 (paints over play). */
#endif

#endif

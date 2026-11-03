/* senkosp's game values in shim_iface.h (run by `make test`); the
 * game-agnostic arithmetic and region-map invariants are the kit's
 * shims/test/test_shim_iface.c. Split out of that file at afab584; the
 * BIOS-blob structure asserts below the game images followed at the kit's
 * final review (C1: the bios_data.bin composition is per game). */
#include <assert.h>
#include <stdio.h>
#include "shim_iface.h"

int main(void) {
    assert(CART_SIZE == 0x0efb3000u);                 /* 251,342,848 = len(senkosp.dat); Task 8 fixed a 0x3000 typo here */
    assert(CART_FAD  == 320150);                      /* CART_LBA 320000 + 150 (cart opens track04) */
    assert(KERNEL_TOTAL_LEN == 0x3200u);
    assert(KERNEL_DST + KERNEL_TOTAL_LEN == 0x8c003800u);            /* pinned upper bound */
    assert(BIOS_DATA_TOTAL == 0xa200u);

    /* Game images (docs/kb/game.md §Parsed .dat header). */
    assert(GAME_LOAD_ADDR == 0x8c020000u);
    assert(GAME_ENTRY     == 0x8c021000u);
    assert(MAIN_LEN == 0x00171ff8u);
    assert(TEST_DAT_OFF == MAIN_LEN);
    assert(TEST_LEN == 0x0004dc40u);

    assert(GD_STACK_TOP == BIOS60000_DST);                           /* ... where the BIOS blob home starts */

    /* Loader-placed BIOS-derived blocks: outside shim home, disjoint from it
     * and from each other (KERNEL-SLICE pin, docs/kb/phase4-conversion.md). */
    assert(KERNEL_DST + KERNEL_TOTAL_LEN <= SHIM_BASE);              /* kernel slice | shim home */
    assert(KERNEL_A_LEN + KERNEL_B_LEN + KERNEL_C_LEN == KERNEL_TOTAL_LEN);

    /* bios_data.bin layout: blob then the three kernel pieces, concatenated,
     * offsets computed (not independently duplicated) so a length edit can't
     * silently desync loader and Makefile. */
    assert(BIOS_DATA_60000_OFF == 0u);
    assert(BIOS_DATA_KERNEL_A_OFF == BIOS60000_LEN);
    assert(BIOS_DATA_KERNEL_B_OFF == BIOS_DATA_KERNEL_A_OFF + KERNEL_A_LEN);
    assert(BIOS_DATA_KERNEL_C_OFF == BIOS_DATA_KERNEL_B_OFF + KERNEL_B_LEN);
    assert(BIOS_DATA_TOTAL == BIOS60000_LEN + KERNEL_TOTAL_LEN);

    printf("ok\n");
    return 0;
}

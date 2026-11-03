/* senkosp's game values in shim_iface.h (run by `make test`); the
 * game-agnostic arithmetic and region-map invariants are the kit's
 * shims/test/test_shim_iface.c. Split out of that file at afab584. */
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

    printf("ok\n");
    return 0;
}

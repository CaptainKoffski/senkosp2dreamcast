/* Host-compilable self-test for shim_iface.h's pure address-arithmetic macros
 * AND the shim-home region map (run by `make test`).
 * (The freestanding half is checked by the cross-build + the shim.ld ASSERT,
 * which bounds code+data+bss size; the region-map invariants below are pure
 * macros the linker never sees, so they are enforced HERE.) */
#include <assert.h>
#include <stdio.h>
#include "shim_iface.h"

int main(void) {
    assert(P2ADDR(0x8c010000u) == 0xac010000u);      /* P2 = physical | 0xa0000000 */
    assert(P2ADDR(0x00000000u) == 0xa0000000u);
    assert(SHIM_ERR       == 0x8c014000u);            /* SHIM_BASE + 0x4000 */
    assert(SHIM_CODE_MAX  == 0x4000u);
    assert(SHIM_END       == 0x8c018000u);
    assert(CART_SIZE == 0x0efb3000u);                 /* 251,342,848 = len(senkosp.dat); Task 8 fixed a 0x3000 typo here */
    assert(CART_FAD  == 451878);                      /* donor CART_LBA 451728 + 150 (B5 layout) */

    /* Region map: ordered, disjoint, and clear of the KOS stack (a length
     * bump would silently overlap the next slice; nothing else checks
     * these). */
    assert(SHIM_BASE + SHIM_CODE_MAX <= SHIM_ERR);                   /* code+bss | err */
    assert(SHIM_ERR + 16 <= G1_MIRROR);                              /* err (u32[4]) | G1 mirror */
    assert(G1_MIRROR + 0x800 <= MAPLE_MIRROR);                       /* G1 mirror | maple mirror */
    assert(MAPLE_MIRROR + MAPLE_MIRROR_LEN <= MAPLE_TX);             /* maple mirror | tx */
    assert(MAPLE_TX + 0x40 <= MAPLE_RX);                             /* tx | rx */
    assert(MAPLE_RX + 132 <= SHIM_STATE);                            /* rx (DEVINFO reply 132B) | state */
    assert(SHIM_STATE + 32 <= SHIM_BOUNCE);                          /* state (u32[8]) | bounce */
    assert(SHIM_BOUNCE + 2048 <= GD_STACK_BOTTOM);                   /* bounce | GD stack */
    assert(GD_STACK_BOTTOM + 0x1000 <= GD_STACK_TOP);                /* >= 4 KB of stack */
    assert(GD_STACK_TOP == SHIM_END);                                /* shim home ends exactly at SHIM_END */
    assert(GD_STACK_TOP == BIOS60000_DST);                           /* ... where the BIOS blob home starts */

    /* Loader-placed BIOS-derived blocks: outside shim home, disjoint from it
     * and from each other (KERNEL-SLICE pin, docs/kb/phase4-conversion.md). */
    assert(KERNEL_DST + KERNEL_TOTAL_LEN <= SHIM_BASE);              /* kernel slice | shim home */
    assert(KERNEL_A_LEN + KERNEL_B_LEN + KERNEL_C_LEN == KERNEL_TOTAL_LEN);
    assert(KERNEL_TOTAL_LEN == 0x3200u);
    assert(KERNEL_DST + KERNEL_TOTAL_LEN == 0x8c003800u);            /* pinned upper bound */

    /* bios_data.bin layout: blob then the three kernel pieces, concatenated,
     * offsets computed (not independently duplicated) so a length edit can't
     * silently desync loader and Makefile. */
    assert(BIOS_DATA_60000_OFF == 0u);
    assert(BIOS_DATA_KERNEL_A_OFF == BIOS60000_LEN);
    assert(BIOS_DATA_KERNEL_B_OFF == BIOS_DATA_KERNEL_A_OFF + KERNEL_A_LEN);
    assert(BIOS_DATA_KERNEL_C_OFF == BIOS_DATA_KERNEL_B_OFF + KERNEL_B_LEN);
    assert(BIOS_DATA_TOTAL == BIOS60000_LEN + KERNEL_TOTAL_LEN);
    assert(BIOS_DATA_TOTAL == 0xa200u);

    /* Game images (docs/kb/game.md §Parsed .dat header). */
    assert(GAME_LOAD_ADDR == 0x8c020000u);
    assert(GAME_ENTRY     == 0x8c021000u);
    assert(MAIN_LEN == 0x00171ff8u);
    assert(TEST_DAT_OFF == MAIN_LEN);
    assert(TEST_LEN == 0x0004dc40u);

    printf("shim_iface host self-test: OK (incl. region map)\n");
    return 0;
}

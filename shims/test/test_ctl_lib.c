/* Host test of the controls-library model (loader/ctl_lib.c): per-class
 * stock layouts + custom slots, per-port selection, fork-on-edit, delete,
 * pack. Stock ids come from the generated loader/menu_layout.h. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "ctl_lib.h"

int main(void) {
    enum { P = 0, S = 1 };
    ctl_lib_t L;
    memset(&L, 0, sizeof L);

    /* defaults */
    assert(ctl_slot(&L, P, 0) == -1 && ctl_pack(&L, P, 0) == 0x343210u && ctl_pack(&L, S, 1) == 0x421063u);
    assert(memcmp(ctl_funcs(&L, P, 1), CTL_STOCK_FUNC[P][0], 6) == 0);
    /* cycle without customs */
    ctl_cycle(&L, P, 0, +1); assert(L.sel[P][0] == 1 && ctl_pack(&L, P, 0) == 0x432130u);
    ctl_cycle(&L, P, 0, +1); assert(L.sel[P][0] == 0);
    ctl_cycle(&L, P, 0, -1); assert(L.sel[P][0] == 1);
    ctl_cycle(&L, S, 0, -1); assert(L.sel[S][0] == 0);           /* single stock: stays */
    /* keep: same value never forks; first change forks a copy and selects it */
    assert(ctl_keep(&L, P, 1, 0, 0) == CTL_KEEP_SAME && ctl_slot(&L, P, 1) == -1 && L.used[P][0] == 0);
    assert(ctl_keep(&L, P, 1, 5, 5) == CTL_KEEP_FORKED && ctl_slot(&L, P, 1) == 0 && L.used[P][0] == 1);
    assert(ctl_funcs(&L, P, 1)[5] == 5 && ctl_funcs(&L, P, 1)[0] == 0);        /* B.O.S.S. on R, rest Tournament */
    assert(memcmp(CTL_STOCK_FUNC[P][0], (unsigned char[]){0,1,2,3,4,3}, 6) == 0);  /* stock untouched */
    assert(ctl_keep(&L, P, 1, 5, 6) == CTL_KEEP_WRITTEN && ctl_slot(&L, P, 1) == 0);
    assert(ctl_pack(&L, P, 1) == 0x643210u);
    /* shared object: port 0 (on Old, sel 1) steps onto slot 0 and sees the edit */
    ctl_cycle(&L, P, 0, +1); assert(ctl_slot(&L, P, 0) == 0 && ctl_funcs(&L, P, 0)[5] == 6);
    /* cycle order with a hole: fork slot 1 from Old, delete slot 0, cycle skips it */
    ctl_cycle(&L, P, 0, -1); assert(L.sel[P][0] == 1);                /* back on Old */
    assert(ctl_keep(&L, P, 0, 0, 1) == CTL_KEEP_FORKED && ctl_slot(&L, P, 0) == 1);
    ctl_delete(&L, P, 0); assert(L.used[P][0] == 0 && L.sel[P][1] == 0 && ctl_slot(&L, P, 0) == 1);
    ctl_cycle(&L, P, 1, +1); ctl_cycle(&L, P, 1, +1); assert(ctl_slot(&L, P, 1) == 1);  /* 0 -> 1 -> slot 1 */
    ctl_cycle(&L, P, 1, +1); assert(L.sel[P][1] == 0);
    assert(ctl_free_slot(&L, P) == 0);                                 /* freed number reused */
    /* classes independent */
    assert(ctl_keep(&L, S, 0, 1, 0) == CTL_KEEP_FORKED && L.used[S][0] == 1);
    ctl_delete(&L, P, 1); assert(L.used[S][0] == 1 && ctl_slot(&L, S, 0) == 0);
    /* full: 8 forks then refusal; editing a custom row still allowed */
    memset(&L, 0, sizeof L);
    for (int i = 0; i < 8; i++) { L.sel[P][0] = 0; assert(ctl_keep(&L, P, 0, 0, 1) == CTL_KEEP_FORKED && ctl_slot(&L, P, 0) == i); }
    assert(ctl_free_slot(&L, P) == -1);
    L.sel[P][0] = 0; assert(ctl_keep(&L, P, 0, 0, 1) == CTL_KEEP_FULL && ctl_slot(&L, P, 0) == -1);
    L.sel[P][0] = 2 + 7; assert(ctl_keep(&L, P, 0, 1, 2) == CTL_KEEP_WRITTEN);

    /* backward wrap from stock 0 lands on the last used slot */
    memset(&L, 0, sizeof L);
    for (int i = 0; i < 2; i++) { L.sel[P][0] = 0; assert(ctl_keep(&L, P, 0, 0, 1) == CTL_KEEP_FORKED); }
    L.sel[P][0] = 0; ctl_cycle(&L, P, 0, -1); assert(ctl_slot(&L, P, 0) == 1);
    /* delete leaves a port on a different slot alone */
    L.sel[P][0] = 2 + 1; L.sel[P][1] = 2 + 0;
    ctl_delete(&L, P, 0); assert(ctl_slot(&L, P, 0) == 1 && L.sel[P][1] == 0);
    /* FULL leaves sel and used untouched */
    memset(&L, 0, sizeof L);
    for (int i = 0; i < 8; i++) { L.sel[P][0] = 0; assert(ctl_keep(&L, P, 0, 0, 1) == CTL_KEEP_FORKED); }
    L.sel[P][0] = 0;
    unsigned char used_snap[CTL_N_CUSTOM];
    memcpy(used_snap, L.used[P], CTL_N_CUSTOM);
    assert(ctl_keep(&L, P, 0, 0, 1) == CTL_KEEP_FULL && L.sel[P][0] == 0 && memcmp(used_snap, L.used[P], CTL_N_CUSTOM) == 0);
    /* delete of stock (-1) is a no-op; port 1 on stock Old (sel 1 == N_STOCK + -1) is the canary */
    L.sel[P][1] = 1;
    ctl_lib_t before = L;
    ctl_delete(&L, P, -1);
    assert(memcmp(&before, &L, sizeof L) == 0);

    printf("test_ctl_lib: PASS\n");
    return 0;
}

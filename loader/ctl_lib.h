/* Controls library: the pre-game menu's shared custom controller layouts.
 * Pure C, no KOS -- host-tested by shims/test/test_ctl_lib.c.
 *
 * Two device classes (pad, arcade stick), each with its stock layouts
 * (menu_layout.h CTL_STOCK_FUNC) and CTL_N_CUSTOM user slots. A layout is
 * CTL_N_BUTTONS function ids. Each (class, port) selects one layout:
 * sel < CTL_N_STOCK[cls] is a stock id, otherwise a custom slot
 * (sel - CTL_N_STOCK[cls]). Ports on the same slot share the object. */
#ifndef CTL_LIB_H
#define CTL_LIB_H

#include "menu_layout.h"

typedef struct {
    unsigned char custom[CTL_N_CLASS][CTL_N_CUSTOM][CTL_N_BUTTONS];
    unsigned char used[CTL_N_CLASS][CTL_N_CUSTOM];
    unsigned char sel[CTL_N_CLASS][CTL_PORTS];   /* < CTL_N_STOCK[cls]: stock id; else CTL_N_STOCK[cls] + slot */
} ctl_lib_t;

extern ctl_lib_t ctl_lib;                        /* the session instance; all-zero == defaults (KOS clears .bss: arch_main memset of _bss_start, tools/kos/kernel/arch/dreamcast/kernel/init.c:299) */

#define CTL_KEEP_FULL    (-1)
#define CTL_KEEP_SAME    0
#define CTL_KEEP_WRITTEN 1
#define CTL_KEEP_FORKED  2

int  ctl_slot(const ctl_lib_t *L, int cls, int port);                    /* custom slot or -1 (stock) */
const unsigned char *ctl_funcs(const ctl_lib_t *L, int cls, int port);   /* the six ids the row shows */
void ctl_cycle(ctl_lib_t *L, int cls, int port, int dir);                /* dir +1/-1; stock ids, then used slots ascending; wraps */
int  ctl_free_slot(const ctl_lib_t *L, int cls);                         /* lowest unused slot or -1 */
/* Set one button's function. Same value: CTL_KEEP_SAME, nothing written.
 * Stock selection: fork the stock ids into the lowest free slot, select it,
 * write the value -> CTL_KEEP_FORKED (no free slot -> CTL_KEEP_FULL, nothing
 * changed). Custom selection: write in place -> CTL_KEEP_WRITTEN. */
int  ctl_keep(ctl_lib_t *L, int cls, int port, int button, unsigned char value);
void ctl_delete(ctl_lib_t *L, int cls, int slot);                        /* free it; every port selecting it -> 0. slot is a ctl_slot() result: -1 (stock) or out of range is a no-op */
unsigned ctl_pack(const ctl_lib_t *L, int cls, int port);                /* nibble i = funcs[i] */

#endif

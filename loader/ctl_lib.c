/* Controls library model -- see ctl_lib.h. No allocation, no KOS. */
#include "ctl_lib.h"

ctl_lib_t ctl_lib;   /* .bss: all-zero == every port on stock layout 0, no customs */

int ctl_slot(const ctl_lib_t *L, int cls, int port) {
    int s = L->sel[cls][port] - CTL_N_STOCK[cls];
    return s >= 0 ? s : -1;
}

const unsigned char *ctl_funcs(const ctl_lib_t *L, int cls, int port) {
    int s = ctl_slot(L, cls, port);
    return s < 0 ? CTL_STOCK_FUNC[cls][L->sel[cls][port]] : L->custom[cls][s];
}

void ctl_cycle(ctl_lib_t *L, int cls, int port, int dir) {
    /* ponytail: linear scan over the ordered selection list (CTL_MAX_STOCK +
     * CTL_N_CUSTOM = 10 entries max); a cursor structure is not worth it. */
    unsigned char list[CTL_MAX_STOCK + CTL_N_CUSTOM];
    int n = 0, at = 0, i;
    for (i = 0; i < CTL_N_STOCK[cls]; i++) list[n++] = i;
    for (i = 0; i < CTL_N_CUSTOM; i++)
        if (L->used[cls][i]) list[n++] = CTL_N_STOCK[cls] + i;
    for (i = 0; i < n; i++)
        if (list[i] == L->sel[cls][port]) at = i;   /* not found (impossible via the API) -> 0 */
    L->sel[cls][port] = list[(at + (dir < 0 ? n - 1 : 1)) % n];
}

int ctl_free_slot(const ctl_lib_t *L, int cls) {
    for (int i = 0; i < CTL_N_CUSTOM; i++)
        if (!L->used[cls][i]) return i;
    return -1;
}

int ctl_keep(ctl_lib_t *L, int cls, int port, int button, unsigned char value) {
    if (ctl_funcs(L, cls, port)[button] == value) return CTL_KEEP_SAME;
    int s = ctl_slot(L, cls, port), r = CTL_KEEP_WRITTEN;
    if (s < 0) {
        const unsigned char *stock = CTL_STOCK_FUNC[cls][L->sel[cls][port]];
        if ((s = ctl_free_slot(L, cls)) < 0) return CTL_KEEP_FULL;
        for (int i = 0; i < CTL_N_BUTTONS; i++) L->custom[cls][s][i] = stock[i];
        L->used[cls][s] = 1;
        L->sel[cls][port] = CTL_N_STOCK[cls] + s;
        r = CTL_KEEP_FORKED;
    }
    L->custom[cls][s][button] = value;
    return r;
}

void ctl_delete(ctl_lib_t *L, int cls, int slot) {
    if (slot < 0 || slot >= CTL_N_CUSTOM) return;
    L->used[cls][slot] = 0;
    for (int p = 0; p < CTL_PORTS; p++)
        if (L->sel[cls][p] == CTL_N_STOCK[cls] + slot) L->sel[cls][p] = 0;
}

unsigned ctl_pack(const ctl_lib_t *L, int cls, int port) {
    const unsigned char *f = ctl_funcs(L, cls, port);
    unsigned v = 0;
    for (int i = 0; i < CTL_N_BUTTONS; i++) v |= (unsigned)(f[i] & 0xfu) << (4 * i);
    return v;
}

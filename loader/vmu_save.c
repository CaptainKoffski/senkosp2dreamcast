/* VMU persistence. See vmu_save.h. The pure half below is host-tested
 * (shims/test/test_vmu_save.c); the KOS half is compiled out under HOST_TEST
 * (pattern: shims/src/gd.c). */
#include <string.h>
#include "vmu_save.h"

void vmu_payload_build(unsigned char out[VMU_PAYLOAD_LEN], const unsigned char rec[16], const ctl_lib_t *L) {
    memset(out, 0, 8);
    memcpy(out, "SKSP", 4);
    out[4] = 1;
    memcpy(out + 8, rec, 16);
    memcpy(out + 24, L, sizeof *L);
}

/* Validate everything into locals; touch rec/L only once the whole file passed. */
int vmu_payload_parse(const unsigned char *buf, unsigned len, unsigned char rec[16], ctl_lib_t *L) {
    static const unsigned char def[16] = MENU_DEFAULT_RECORD;
    ctl_lib_t t;
    int i, k, j, cls, s, b;

    if (len != VMU_PAYLOAD_LEN || memcmp(buf, "SKSP", 4) != 0 || buf[4] != 1) return -1;
    /* record: a setting byte is one of its table values, every other byte is the default */
    for (i = 0; i < 16; i++) {
        int ok = buf[8 + i] == def[i];
        for (k = 0; k < MENU_N_SETTINGS; k++) {
            if (MENU_SET_IDX[k] != i) continue;
            ok = 0;
            for (j = 0; j < MENU_SET_NVAL[k]; j++) ok |= buf[8 + i] == MENU_SET_BYTE[k][j];
        }
        if (!ok) return -1;
    }
    memcpy(&t, buf + 24, sizeof t);
    for (cls = 0; cls < CTL_N_CLASS; cls++) {
        for (s = 0; s < CTL_N_CUSTOM; s++) {
            if (t.used[cls][s] > 1) return -1;
            for (b = 0; b < CTL_N_BUTTONS; b++)
                if (t.custom[cls][s][b] >= CTL_N_FUNC) return -1;
        }
        for (i = 0; i < CTL_PORTS; i++) {
            int v = t.sel[cls][i];
            if (v >= CTL_N_STOCK[cls] + CTL_N_CUSTOM) return -1;
            if (v >= CTL_N_STOCK[cls] && !t.used[cls][v - CTL_N_STOCK[cls]]) return -1;
        }
    }
    memcpy(rec, buf + 8, 16);
    *L = t;
    return 0;
}

static unsigned le16(const unsigned char *r, int off) { return r[off] | (unsigned)r[off + 1] << 8; }

/* Offsets: vmu_save.h. Bounds: dir_size/fat_size feed KOS mallocs, blk_cnt
 * and the *_loc fields index the 256-block card / 256-entry FAT. */
int vmu_root_ok(const unsigned char root[512]) {
    int i;
    for (i = 0; i < 16; i++) if (root[i] != 0x55) return 0;
    return le16(root, 0x48) == 1 && le16(root, 0x4c) >= 1 && le16(root, 0x4c) <= 13 &&
           le16(root, 0x50) <= 256 && le16(root, 0x46) < 256 && le16(root, 0x4a) < 256;
}

int vmu_decide(const vmu_home_t *home, int declined, const vmu_card_t *cards, int n) {
    int i;
    if (n <= 0) return VMU_NO_CARD;
    if (home->valid)
        for (i = 0; i < n; i++)
            if (cards[i].port == home->port && cards[i].unit == home->unit && memcmp(cards[i].fp, home->fp, VMU_FP_LEN) == 0)
                return i;
    return declined ? VMU_DECLINED : VMU_ASK;
}

#ifndef HOST_TEST
/* KOS half (vmu_scan / vmu_load / vmu_write): Task 3. */
#endif

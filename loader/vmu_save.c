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
#include <stdlib.h>
#include <kos.h>
#include "menu_layout.h"   /* VMU_ICON_PAL, VMU_ICON, VMU_DESC_*, VMU_APP_ID */

/* KOS paths below are under tools/kos/kernel/arch/dreamcast. The file is a
 * 780-byte VMS image: vmu_hdr_t 128 + 1 icon 512 + payload 140
 * (include/dc/vmu_pkg.h:67-80, util/vmu_pkg.c:85). */
#define VMU_BLOCKS 2   /* 780 bytes -> 2 x 512 on the card */

/* vmu_pkg_build copies the descriptions with an unchecked memcpy/strcpy into
 * 16/32/16-byte header fields (util/vmu_pkg.c:108-110). */
_Static_assert(sizeof VMU_DESC_SHORT <= 17 && sizeof VMU_DESC_LONG <= 33 && sizeof VMU_APP_ID <= 16,
               "VMU description strings overflow the vmu_hdr_t fields");
_Static_assert(sizeof(vmu_hdr_t) + 512 + VMU_PAYLOAD_LEN <= VMU_BLOCKS * 512, "VMS image exceeds VMU_BLOCKS");

/* Our dirent among the cnt entries of a vmufs_readdir result, or NULL. Same
 * match as vmufs_dir_find (fs/vmufs.c:205-220): filetype != 0, strncmp over
 * the 12-byte unterminated name. */
static const vmu_dir_t *find_ours(const vmu_dir_t *dir, int cnt) {
    int i;
    for (i = 0; i < cnt; i++)
        if (dir[i].filetype != 0 && strncmp(dir[i].filename, VMU_FILE_NAME, 12) == 0) return dir + i;
    return NULL;
}

/* Block 255 is the root (KOS assumes it too: fs/vmufs.c:79-82). Read it raw
 * and apply vmu_root_ok BEFORE any vmufs_* call: those trust the root's
 * sizes (the header comment). */
static int read_root(maple_device_t *dev, unsigned char root[512]) {
    return vmu_block_read(dev, 255, root) == 0 && vmu_root_ok(root);
}

/* Read-only. Units 1 and 2 of each port only (the menu's 8-slot table). */
int vmu_scan(vmu_card_t out[8]) {
    unsigned char root[512];
    maple_device_t *dev;
    int n = 0, i;

    for (i = 0; n < 8 && (dev = maple_enum_type(i, MAPLE_FUNC_MEMCARD)) != NULL; i++) {
        vmu_dir_t *dir = NULL;   /* vmufs_readdir mallocs it (fs/vmufs.c:564-): caller frees; NULL on failure */
        int cnt = 0;
        if ((dev->unit != 1 && dev->unit != 2) || !read_root(dev, root)) continue;
        out[n].port = dev->port;
        out[n].unit = dev->unit;
        memcpy(out[n].fp, root + VMU_ROOT_FP_OFF, VMU_FP_LEN);
        out[n].has_file = vmufs_readdir(dev, &dir, &cnt) == 0 && find_ours(dir, cnt) != NULL;
        free(dir);
        n++;
    }
    return n;
}

/* rec/L are written only by vmu_payload_parse, which touches them only once
 * the whole payload validated. */
int vmu_load(const vmu_card_t *c, unsigned char rec[16], ctl_lib_t *L) {
    maple_device_t *dev = maple_enum_dev(c->port, c->unit);
    void *buf;
    int size, rc = -1;
    vmu_pkg_t pkg;

    /* vmufs_read mallocs dirent->filesize * 512 bytes (fs/vmufs.c:616-617) and
     * leaves buf NULL on failure; a zero-block dirent yields an empty buffer. */
    if (!dev || vmufs_read(dev, VMU_FILE_NAME, &buf, &size) != 0) return -1;
    /* vmu_pkg_parse reads the header before it looks at data_size
     * (util/vmu_pkg.c:149-154), so demand a whole block first. It then
     * bounds the payload by the buffer and verifies the CRC16 over the whole
     * file (util/vmu_pkg.c:154-171). */
    if (size >= 512 && vmu_pkg_parse(buf, size, &pkg) == 0)
        rc = vmu_payload_parse(pkg.data, pkg.data_len, rec, L);
    free(buf);
    return rc;
}

/* Consent was decided by the caller; this only re-proves the card is the one
 * that was consented to, then writes. */
int vmu_write(const vmu_card_t *c, const unsigned char rec[16], const ctl_lib_t *L) {
    maple_device_t *dev = maple_enum_dev(c->port, c->unit);
    unsigned char root[512], payload[VMU_PAYLOAD_LEN], blk[VMU_BLOCKS * 512];
    const vmu_dir_t *ours;
    vmu_dir_t *dir = NULL;
    vmu_pkg_t pkg;
    uint8_t *vms;
    int cnt, vms_len, existing = 0, avail, rc;

    /* Closes the swap window after a consented-but-failed first write: the
     * card in the slot must still carry the fingerprint the user agreed to. */
    if (!dev || !read_root(dev, root) || memcmp(root + VMU_ROOT_FP_OFF, c->fp, VMU_FP_LEN) != 0)
        return VMU_WRITE_FAIL;

    /* VMUFS_OVERWRITE deletes our old file first (fs/vmufs.c:711-727), so its
     * blocks count as available. */
    if (vmufs_readdir(dev, &dir, &cnt) != 0) return VMU_WRITE_FAIL;
    ours = find_ours(dir, cnt);
    if (ours) existing = ours->filesize;
    free(dir);
    avail = vmufs_free_blocks(dev);
    if (avail < 0) return VMU_WRITE_FAIL;
    if (avail + existing < VMU_BLOCKS) return VMU_WRITE_FULL;

    vmu_payload_build(payload, rec, L);
    memset(&pkg, 0, sizeof pkg);   /* zeroed: the strncpys below keep their NULs */
    strncpy(pkg.desc_short, VMU_DESC_SHORT, sizeof pkg.desc_short - 1);
    strncpy(pkg.desc_long, VMU_DESC_LONG, sizeof pkg.desc_long - 1);
    strncpy(pkg.app_id, VMU_APP_ID, sizeof pkg.app_id - 1);
    pkg.icon_cnt = 1;
    pkg.icon_anim_speed = 0;
    pkg.eyecatch_type = VMUPKG_EC_NONE;
    pkg.data_len = VMU_PAYLOAD_LEN;
    memcpy(pkg.icon_pal, VMU_ICON_PAL, sizeof pkg.icon_pal);
    pkg.icon_data = (uint8_t *)VMU_ICON;
    pkg.data = payload;
    if (vmu_pkg_build(&pkg, &vms, &vms_len) < 0) return VMU_WRITE_FAIL;

    /* vmufs_write rounds only the SIZE up to a 512 multiple (780 -> 1024,
     * fs/vmufs.c:695-699); the block loop then reads insize/512 whole blocks
     * from the caller's buffer (fs/vmufs.c:366,376). Hand it a zero-padded
     * 1024-byte copy so the tail is not 244 bytes of heap. */
    memset(blk, 0, sizeof blk);
    memcpy(blk, vms, vms_len);
    free(vms);
    rc = vmufs_write(dev, VMU_FILE_NAME, blk, sizeof blk, VMUFS_OVERWRITE);
    return rc < 0 ? VMU_WRITE_FAIL : VMU_WRITE_OK;
}
#endif

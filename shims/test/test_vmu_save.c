/* Host test of the pure half of loader/vmu_save.c: payload v1 build/parse
 * with validation, the root-block guard, the consent decision (16-byte card
 * identity: root timestamp + our dirent's timestamp). The KOS half
 * (card scan/load/write) is compiled out under HOST_TEST. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../../loader/vmu_save.h"

static void good(unsigned char out[VMU_PAYLOAD_LEN], unsigned char rec[16], ctl_lib_t *L) {
    static const unsigned char def[16] = MENU_DEFAULT_RECORD;
    static const unsigned char btns[CTL_N_BUTTONS] = {3, 5, 2, 4, 0, 6};
    memset(L, 0, sizeof *L);
    memcpy(L->custom[0][0], btns, sizeof btns);
    L->used[0][0] = 1;
    L->sel[0][1] = CTL_N_STOCK[0];
    memcpy(rec, def, 16);
    rec[MENU_SET_IDX[0]] = MENU_SET_BYTE[0][2];
    vmu_payload_build(out, rec, L);
}

/* parse must reject buf[0..len) and leave rec2/L2 untouched */
static void rejects(const unsigned char *buf, unsigned len) {
    unsigned char rec2[16];
    ctl_lib_t L2;
    ctl_lib_t ref;
    memset(rec2, 0xEE, sizeof rec2);
    memset(&L2, 0xEE, sizeof L2);
    memcpy(&ref, &L2, sizeof L2);
    assert(vmu_payload_parse(buf, len, rec2, &L2) == -1);
    for (int i = 0; i < 16; i++) assert(rec2[i] == 0xEE);
    assert(memcmp(&L2, &ref, sizeof L2) == 0);
}

/* fp = root timestamp (8) + our dirent's timestamp (8, zeros: no file); NULL dir = no file */
static void fp16(unsigned char fp[VMU_FP_LEN], const char *root8, const char *dir8) {
    memset(fp, 0, VMU_FP_LEN);
    memcpy(fp, root8, 8);
    if (dir8) memcpy(fp + 8, dir8, 8);
}

static vmu_card_t card(int port, int unit, const char *root8, const char *dir8) {
    vmu_card_t c = {port, unit, dir8 != NULL, {0}};
    fp16(c.fp, root8, dir8);
    return c;
}

static vmu_home_t home(int valid, int port, int unit, const char *root8, const char *dir8) {
    vmu_home_t h = {valid, port, unit, {0}};
    fp16(h.fp, root8, dir8);
    return h;
}

static void put16(unsigned char *r, int off, unsigned v) { r[off] = v & 0xff; r[off + 1] = v >> 8; }

static void root(unsigned char r[512]) {
    memset(r, 0, 512);
    memset(r, 0x55, 16);
    put16(r, 0x46, 254); put16(r, 0x48, 1); put16(r, 0x4a, 253); put16(r, 0x4c, 13); put16(r, 0x50, 200);
}

int main(void) {
    unsigned char out[VMU_PAYLOAD_LEN], rec[16], rec2[16], buf[VMU_PAYLOAD_LEN];
    ctl_lib_t L, L2;

    /* Payload v1 schema pin: sel is an offset from CTL_N_STOCK[cls], ids index
     * FUNC_WORDS (pinned in scripts/test_vmu_decode.py), and the 116 bytes are
     * these dimensions. Changing any of them = bump the payload version
     * (vmu_payload_build/parse buf[4]), or old saves load remapped. */
    assert(sizeof(ctl_lib_t) == 116);
    assert(CTL_N_CLASS == 2 && CTL_PORTS == 2 && CTL_N_CUSTOM == 8 && CTL_N_FUNC == 7 && CTL_N_BUTTONS == 6);
    assert(CTL_N_STOCK[0] == 2 && CTL_N_STOCK[1] == 1);
    good(out, rec, &L);
    /* build layout */
    assert(memcmp(out, "SKSP", 4) == 0 && out[4] == 1 && out[5] == 0 && out[6] == 0 && out[7] == 0);
    assert(memcmp(out + 8, rec, 16) == 0 && memcmp(out + 24, &L, 116) == 0);
    /* roundtrip */
    assert(vmu_payload_parse(out, 140, rec2, &L2) == 0 && memcmp(rec2, rec, 16) == 0 && memcmp(&L2, &L, 116) == 0);
    {   /* unused slots carry zeros, not ctl_delete's leftovers (a create-then-delete is not dirty) */
        ctl_lib_t Ld = L;
        unsigned char o2[VMU_PAYLOAD_LEN];
        memcpy(Ld.custom[0][3], "\1\2\3\4\5\6", CTL_N_BUTTONS);   /* slot 3 bytes left behind, used[0][3] == 0 */
        assert(Ld.used[0][3] == 0);
        vmu_payload_build(o2, rec, &Ld);
        for (int i = 0; i < CTL_N_BUTTONS; i++) assert(o2[24 + 3 * CTL_N_BUTTONS + i] == 0);
        assert(memcmp(o2, out, sizeof o2) == 0);                          /* same payload as without the leftovers */
        assert(vmu_payload_parse(o2, 140, rec2, &L2) == 0 && memcmp(&L2, &L, 116) == 0);
    }

    /* rejects: each on a fresh good() buffer */
    rejects(out, 139);
    rejects(out, 141);
    memcpy(buf, out, sizeof buf); buf[3] = 'Q';                          rejects(buf, 140);
    memcpy(buf, out, sizeof buf); buf[4] = 2;                            rejects(buf, 140);
    memcpy(buf, out, sizeof buf); buf[24] = CTL_N_FUNC;                  rejects(buf, 140);   /* id 7 */
    memcpy(buf, out, sizeof buf); buf[24 + 96] = 2;                      rejects(buf, 140);   /* used */
    memcpy(buf, out, sizeof buf); buf[24 + 112] = CTL_N_STOCK[0] + CTL_N_CUSTOM; buf[24 + 96 + CTL_N_CUSTOM] = 1;
                                                                         rejects(buf, 140);   /* sel out of range (the used[] read past the class would otherwise pass) */
    memcpy(buf, out, sizeof buf); buf[24 + 112] = CTL_N_STOCK[0] + 3;    rejects(buf, 140);   /* sel names unused slot 3 */
    memcpy(buf, out, sizeof buf); buf[8 + 0] ^= 1;                       rejects(buf, 140);   /* fixed record byte */
    memcpy(buf, out, sizeof buf); buf[8 + MENU_SET_IDX[0]] = 0x7f;       rejects(buf, 140);   /* setting byte off-table */
    memcpy(buf, out, sizeof buf); buf[8 + MENU_SET_IDX[4]] = 0x00;      rejects(buf, 140);   /* padding slot 7 of MENU_SET_BYTE[4] (NVAL 7) */
    {   /* stick class: sel names unused custom slot 3 (CTL_N_STOCK[1] + 3) */
        ctl_lib_t Ls = L;
        assert(Ls.used[1][3] == 0);
        Ls.sel[1][0] = CTL_N_STOCK[1] + 3;
        vmu_payload_build(buf, rec, &Ls);                                rejects(buf, 140);
    }

    /* root guard */
    unsigned char r[512];
    root(r); assert(vmu_root_ok(r) == 1);
    root(r); put16(r, 0x50, 241); assert(vmu_root_ok(r) == 1);
    root(r); put16(r, 0x50, 255); assert(vmu_root_ok(r) == 1);   /* fat[255] is the FAT's last entry */
    root(r); put16(r, 0x50, 256); assert(vmu_root_ok(r) == 0);   /* KOS vmufs_file_delete lets a chain entry == blk_cnt through (fs/vmufs.c:425): fat[256] is past the 512-B FAT */
    memset(r, 0xA5, 512);        assert(vmu_root_ok(r) == 0);
    root(r); r[3] = 0x54;        assert(vmu_root_ok(r) == 0);
    root(r); put16(r, 0x48, 2);   assert(vmu_root_ok(r) == 0);
    root(r); put16(r, 0x4c, 0);   assert(vmu_root_ok(r) == 0);
    root(r); put16(r, 0x4c, 14);  assert(vmu_root_ok(r) == 0);
    root(r); put16(r, 0x50, 257); assert(vmu_root_ok(r) == 0);
    root(r); put16(r, 0x46, 256); assert(vmu_root_ok(r) == 0);
    root(r); put16(r, 0x4a, 256); assert(vmu_root_ok(r) == 0);

    /* decide */
    vmu_card_t cards[2] = {card(0, 0, "11111111", "aaaaaaaa"), card(1, 0, "22222222", "bbbbbbbb")};   /* A1, B1 */
    vmu_home_t h = home(0, 0, 0, "00000000", NULL);
    assert(vmu_decide(&h, 0, cards, 2) == VMU_ASK);
    h = home(1, 0, 0, "11111111", "aaaaaaaa");
    assert(vmu_decide(&h, 0, cards, 0) == VMU_NO_CARD);
    assert(vmu_decide(&h, 0, cards, 2) == 0);
    h = home(1, 1, 0, "22222222", "bbbbbbbb");
    assert(vmu_decide(&h, 0, cards, 2) == 1);
    h = home(1, 0, 0, "33333333", "aaaaaaaa");
    assert(vmu_decide(&h, 0, cards, 2) == VMU_ASK);                        /* same slot, other card */
    h = home(1, 0, 0, "11111111", "aaaaaaaa");
    assert(vmu_decide(&h, 0, cards + 1, 1) == VMU_ASK);                    /* home's card gone */
    h = home(1, 0, 0, "1111111X", "aaaaaaaa");
    assert(vmu_decide(&h, 0, cards, 2) == VMU_ASK);                        /* only the last root byte differs */
    h = home(1, 0, 0, "11111111", "aaaaaaaX");
    assert(vmu_decide(&h, 0, cards, 2) == VMU_ASK);                        /* same root (dead-RTC twin), other save: dirent ts differs */
    h = home(1, 0, 0, "11111111", NULL);
    assert(vmu_decide(&h, 0, cards, 2) == VMU_ASK);                        /* home had no file, the card in its slot has one */
    {   /* no-file card: the dirent half is zeros, and a home taken from it matches */
        vmu_card_t nf = card(0, 0, "11111111", NULL);
        for (int i = 8; i < VMU_FP_LEN; i++) assert(nf.fp[i] == 0);
        h = home(1, 0, 0, "11111111", NULL);
        assert(vmu_decide(&h, 0, &nf, 1) == 0);
        h = home(1, 0, 0, "11111111", "aaaaaaaa");
        assert(vmu_decide(&h, 0, &nf, 1) == VMU_ASK);                      /* home's file deleted since */
    }
    h = home(0, 0, 0, "11111111", "aaaaaaaa");
    assert(vmu_decide(&h, 0, cards, 2) == VMU_ASK);                        /* invalid home never matches */
    vmu_card_t dup[2] = {card(1, 0, "11111111", "aaaaaaaa"), card(0, 1, "11111111", "aaaaaaaa")};  /* B1, A2: A1's fingerprint, wrong slot */
    h = home(1, 0, 0, "11111111", "aaaaaaaa");
    assert(vmu_decide(&h, 0, dup, 2) == VMU_ASK);
    h = home(0, 0, 0, "00000000", NULL);
    assert(vmu_decide(&h, 1, cards, 2) == VMU_DECLINED);
    h = home(1, 0, 0, "11111111", "aaaaaaaa");
    assert(vmu_decide(&h, 1, cards, 2) == 0);                              /* home outranks declined */

    printf("test_vmu_save: PASS\n");
    return 0;
}

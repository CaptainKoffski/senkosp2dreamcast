/* Host test of the pure half of loader/vmu_save.c: payload v1 build/parse
 * with validation, the root-block guard, the consent decision. The KOS half
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

static vmu_card_t card(int port, int unit, const char *fp) {
    vmu_card_t c = {port, unit, 0, {0}};
    memcpy(c.fp, fp, VMU_FP_LEN);
    return c;
}

static vmu_home_t home(int valid, int port, int unit, const char *fp) {
    vmu_home_t h = {valid, port, unit, {0}};
    memcpy(h.fp, fp, VMU_FP_LEN);
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

    assert(sizeof(ctl_lib_t) == 116);
    good(out, rec, &L);
    /* build layout */
    assert(memcmp(out, "SKSP", 4) == 0 && out[4] == 1 && out[5] == 0 && out[6] == 0 && out[7] == 0);
    assert(memcmp(out + 8, rec, 16) == 0 && memcmp(out + 24, &L, 116) == 0);
    /* roundtrip */
    assert(vmu_payload_parse(out, 140, rec2, &L2) == 0 && memcmp(rec2, rec, 16) == 0 && memcmp(&L2, &L, 116) == 0);

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
    memset(r, 0xA5, 512);        assert(vmu_root_ok(r) == 0);
    root(r); r[3] = 0x54;        assert(vmu_root_ok(r) == 0);
    root(r); put16(r, 0x48, 2);   assert(vmu_root_ok(r) == 0);
    root(r); put16(r, 0x4c, 0);   assert(vmu_root_ok(r) == 0);
    root(r); put16(r, 0x4c, 14);  assert(vmu_root_ok(r) == 0);
    root(r); put16(r, 0x50, 257); assert(vmu_root_ok(r) == 0);
    root(r); put16(r, 0x46, 256); assert(vmu_root_ok(r) == 0);
    root(r); put16(r, 0x4a, 256); assert(vmu_root_ok(r) == 0);

    /* decide */
    vmu_card_t cards[2] = {card(0, 0, "11111111"), card(1, 0, "22222222")};   /* A1, B1 */
    vmu_home_t h = home(0, 0, 0, "00000000");
    assert(vmu_decide(&h, 0, cards, 2) == VMU_ASK);
    h = home(1, 0, 0, "11111111");
    assert(vmu_decide(&h, 0, cards, 0) == VMU_NO_CARD);
    assert(vmu_decide(&h, 0, cards, 2) == 0);
    h = home(1, 1, 0, "22222222");
    assert(vmu_decide(&h, 0, cards, 2) == 1);
    h = home(1, 0, 0, "33333333");
    assert(vmu_decide(&h, 0, cards, 2) == VMU_ASK);                        /* same slot, other card */
    h = home(1, 0, 0, "11111111");
    assert(vmu_decide(&h, 0, cards + 1, 1) == VMU_ASK);                    /* home's card gone */
    h = home(1, 0, 0, "1111111X");
    assert(vmu_decide(&h, 0, cards, 2) == VMU_ASK);                        /* only the last fingerprint byte differs */
    h = home(0, 0, 0, "11111111");
    assert(vmu_decide(&h, 0, cards, 2) == VMU_ASK);                        /* invalid home never matches */
    vmu_card_t dup[2] = {card(1, 0, "11111111"), card(0, 1, "11111111")};  /* B1, A2: A1's fingerprint, wrong slot */
    h = home(1, 0, 0, "11111111");
    assert(vmu_decide(&h, 0, dup, 2) == VMU_ASK);
    h = home(0, 0, 0, "00000000");
    assert(vmu_decide(&h, 1, cards, 2) == VMU_DECLINED);
    h = home(1, 0, 0, "11111111");
    assert(vmu_decide(&h, 1, cards, 2) == 0);                              /* home outranks declined */

    printf("test_vmu_save: PASS\n");
    return 0;
}

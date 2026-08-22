/* Host-side test of the pure split math + JVS bit table. Build: cc -DHOST_TEST. */
#include <assert.h>
#include <stdio.h>
#include "../include/shim_iface.h"
#include "../src/cart.c"     /* pure part only (guards out SH-4 code) */
#include "../src/jvs.c"      /* pure: CONT_ and JVS_ tables, dc_to_jvs, jvs_checksum */

int main(void) {
    split_t s;
    /* aligned, exact sectors: no head/tail */
    cart_split(0, 4096, &s);
    assert(s.head_take == 0 && s.body_sect == 2 && s.body_fad == 0 && s.tail_take == 0);
    /* unaligned start, within one sector (head only, no body/tail) */
    cart_split(100, 50, &s);
    assert(s.head_fad == 0 && s.head_skip == 100 && s.head_take == 50);
    assert(s.body_sect == 0 && s.tail_take == 0);
    /* unaligned start crossing into full sectors + tail */
    cart_split(2048 + 32, 2048 * 3, &s);
    assert(s.head_fad == 1 && s.head_skip == 32 && s.head_take == 2048 - 32);
    assert(s.body_fad == 2 && s.body_sect == 2);
    assert(s.tail_fad == 4 && s.tail_take == 32);
    /* head fills to boundary exactly, then body only */
    cart_split(2048 - 64, 64 + 2048, &s);
    assert(s.head_take == 64 && s.body_sect == 1 && s.tail_take == 0);
    /* head + tail with NO body (crosses exactly one boundary) */
    cart_split(2048 - 32, 32 + 100, &s);
    assert(s.head_fad == 0 && s.head_take == 32);
    assert(s.body_sect == 0);
    assert(s.tail_fad == 1 && s.tail_take == 100);
    /* zero-length read: no head/body/tail => no I/O issued */
    cart_split(1000, 0, &s);
    assert(s.head_take == 0 && s.body_sect == 0 && s.tail_take == 0);

    /* dc_to_jvs: takes an already-normalized PRESSED mask (unlike Cleopatra's
       version, which inverted DC's active-low word internally) -- the CONT_*
       bits below match KOS controller.h numbering (jvs.c comment). JVS word
       (docs/kb/input-map.md, measured): Start 0x8000 Up 0x2000 Down 0x1000
       Left 0x0800 Right 0x0400 M(A) 0x0200 S(X) 0x0100 Barrage(Y) 0x0080
       Action(B) 0x0040 OverDrive(Rtrig) 0x0020. */
    assert(dc_to_jvs(0) == 0x0000);                              /* nothing pressed */
    assert(dc_to_jvs(CONT_START) == JVS_START);
    assert(dc_to_jvs(CONT_DPAD_UP) == JVS_UP);
    assert(dc_to_jvs(CONT_DPAD_DOWN) == JVS_DOWN);
    assert(dc_to_jvs(CONT_DPAD_LEFT) == JVS_LEFT);
    assert(dc_to_jvs(CONT_DPAD_RIGHT) == JVS_RIGHT);
    assert(dc_to_jvs(CONT_A) == JVS_M);
    assert(dc_to_jvs(CONT_X) == JVS_S);
    assert(dc_to_jvs(CONT_Y) == JVS_BARRAGE);
    assert(dc_to_jvs(CONT_B) == JVS_A);
    assert(dc_to_jvs(CONT_RTRIG) == JVS_OD);
    assert(dc_to_jvs(CONT_START | CONT_DPAD_UP) == (JVS_START | JVS_UP));   /* chord */
    assert(dc_to_jvs(CONT_C) == 0);                              /* C has no JVS mapping */

    /* jvs_checksum: pure mod-256 sum over frame[0x1b..0x39] -- sanity on a
       trivial buffer (senkosp's own golden reply frame is a later task's
       capture; jvs_hasdata is Cleopatra-specific and #if 0'd out here). */
    {
        unsigned char f[0x40];
        int i;
        for (i = 0; i < 0x40; i++) f[i] = 0;
        f[0x1b] = 0x10; f[0x39] = 0x02;
        assert(jvs_checksum(f) == 0x12);
    }

    printf("PASS test_host cart_split + dc_to_jvs + jvs_checksum\n");
    return 0;
}

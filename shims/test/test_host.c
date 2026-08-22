/* Host-side test of the JVS bit table. Build: cc -DHOST_TEST.
 * The cart split math moved out in Task 10: cart.c's private copy of the
 * head/body/tail splitter was deleted (the shim now calls gd.c's gd_plan via
 * gd_read_cart -- one implementation), so the split cases live in
 * test_gd_math.c against that one. */
#include <assert.h>
#include <stdio.h>
#include "../include/shim_iface.h"
#include "../src/jvs.c"      /* pure: CONT_ and JVS_ tables, dc_to_jvs, jvs_checksum */

int main(void) {
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

    /* dc_cond_to_pressed: raw GetCondition words 2/3 -> the pressed mask above.
       w2 = buttons | rtrig<<16 | ltrig<<24 (buttons ACTIVE-LOW), w3 = joyx |
       joyy<<8 | ... (0-255, 128 centred, low = up/left). */
    {
        const unsigned NEUTRAL3 = 0x80808080u;      /* all four axes centred */
        assert(dc_cond_to_pressed(0xffff, NEUTRAL3) == 0);          /* idle pad */
        /* one button held: its wire bit goes to 0 */
        assert(dc_to_jvs(dc_cond_to_pressed(0xffff & ~CONT_START, NEUTRAL3))
               == JVS_START);
        assert(dc_to_jvs(dc_cond_to_pressed(0xffff & ~CONT_Y, NEUTRAL3))
               == JVS_BARRAGE);
        /* R trigger is analog: below 128 idle, at/above 128 -> OverDrive */
        assert(dc_to_jvs(dc_cond_to_pressed(0xffff | (127u << 16), NEUTRAL3)) == 0);
        assert(dc_to_jvs(dc_cond_to_pressed(0xffff | (128u << 16), NEUTRAL3))
               == JVS_OD);
        assert(dc_to_jvs(dc_cond_to_pressed(0xffff | (255u << 16), NEUTRAL3))
               == JVS_OD);
        /* L trigger (bits 24-31) is unbound -- a full press changes nothing */
        assert(dc_cond_to_pressed(0xffff | (255u << 24), NEUTRAL3) == 0);
        /* analog stick drives the same 8-way as the D-pad; neutral band
           0x40..0xc0 inclusive stays idle */
        assert(dc_to_jvs(dc_cond_to_pressed(0xffff, 0x8080803fu)) == JVS_LEFT);
        assert(dc_to_jvs(dc_cond_to_pressed(0xffff, 0x808080c1u)) == JVS_RIGHT);
        assert(dc_to_jvs(dc_cond_to_pressed(0xffff, 0x80803f80u)) == JVS_UP);
        assert(dc_to_jvs(dc_cond_to_pressed(0xffff, 0x8080c180u)) == JVS_DOWN);
        assert(dc_cond_to_pressed(0xffff, 0x80804080u) == 0);        /* band edge */
        assert(dc_cond_to_pressed(0xffff, 0x8080c080u) == 0);        /* band edge */
        assert(dc_to_jvs(dc_cond_to_pressed(0xffff, 0x80803f3fu))
               == (JVS_UP | JVS_LEFT));                              /* diagonal */
        /* D-pad and analog OR together, and coexist with buttons */
        assert(dc_to_jvs(dc_cond_to_pressed(0xffff & ~(CONT_DPAD_UP | CONT_A),
                                            0x808080c1u))
               == (JVS_UP | JVS_M | JVS_RIGHT));
    }

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

    printf("PASS test_host dc_to_jvs + jvs_checksum\n");
    return 0;
}

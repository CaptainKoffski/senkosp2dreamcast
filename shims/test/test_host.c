/* Host-side test of the JVS bit table. Build: cc -DHOST_TEST.
 * The cart split math moved out in Task 10: cart.c's private copy of the
 * head/body/tail splitter was deleted (the shim now calls gd.c's gd_plan via
 * gd_read_cart -- one implementation), so the split cases live in
 * test_gd_math.c against that one. */
#include <assert.h>
#include <stdio.h>
#include "../include/shim_iface.h"
#include "jvs.c"      /* pure: CONT_ and JVS_ tables, dc_to_jvs_word, jvs_checksum */

int main(void) {
    /* dc_to_jvs_word: takes an already-normalized PRESSED mask (unlike Cleopatra's
       version, which inverted DC's active-low word internally) -- the CONT_*
       bits below match KOS controller.h numbering (jvs.c comment). JVS word
       (docs/kb/input-map.md, measured): Start 0x8000 Up 0x2000 Down 0x1000
       Left 0x0800 Right 0x0400 M(A) 0x0200 S(X) 0x0100 Barrage(Y) 0x0080
       Action(B) 0x0040 OverDrive(Rtrig) 0x0020. */
    assert(dc_to_jvs_word(0, JVS_CLASS_PAD, JVS_WORD_OLD) == 0x0000);                              /* nothing pressed */
    assert(dc_to_jvs_word(CONT_START, JVS_CLASS_PAD, JVS_WORD_OLD) == JVS_START);
    assert(dc_to_jvs_word(CONT_DPAD_UP, JVS_CLASS_PAD, JVS_WORD_OLD) == JVS_UP);
    assert(dc_to_jvs_word(CONT_DPAD_DOWN, JVS_CLASS_PAD, JVS_WORD_OLD) == JVS_DOWN);
    assert(dc_to_jvs_word(CONT_DPAD_LEFT, JVS_CLASS_PAD, JVS_WORD_OLD) == JVS_LEFT);
    assert(dc_to_jvs_word(CONT_DPAD_RIGHT, JVS_CLASS_PAD, JVS_WORD_OLD) == JVS_RIGHT);
    assert(dc_to_jvs_word(CONT_A, JVS_CLASS_PAD, JVS_WORD_OLD) == JVS_M);
    assert(dc_to_jvs_word(CONT_X, JVS_CLASS_PAD, JVS_WORD_OLD) == JVS_S);
    assert(dc_to_jvs_word(CONT_Y, JVS_CLASS_PAD, JVS_WORD_OLD) == JVS_BARRAGE);
    assert(dc_to_jvs_word(CONT_B, JVS_CLASS_PAD, JVS_WORD_OLD) == JVS_A);
    assert(dc_to_jvs_word(CONT_RTRIG, JVS_CLASS_PAD, JVS_WORD_OLD) == JVS_OD);
    assert(dc_to_jvs_word(CONT_LTRIG, JVS_CLASS_PAD, JVS_WORD_OLD) == JVS_A);                      /* L duplicates B (block) */
    assert(dc_to_jvs_word(CONT_LTRIG | CONT_B, JVS_CLASS_PAD, JVS_WORD_OLD) == JVS_A);             /* both held: still one bit */
    assert(dc_to_jvs_word(CONT_START | CONT_DPAD_UP, JVS_CLASS_PAD, JVS_WORD_OLD) == (JVS_START | JVS_UP));   /* chord */
    assert(dc_to_jvs_word(CONT_C, JVS_CLASS_PAD, JVS_WORD_OLD) == 0);                              /* C has no JVS mapping */

    /* One resolved word per port per device class (controls-library plan, Task
       1): the shim holds no presets, only six 4-bit function ids per word
       (nibble i = JVS_CLASS_BUTTON[cls][i]); the generated JVS_WORD_* are the
       stock Tournament / Old / Arcade layouts packed into that form. */
    /* stock words reproduce the three tables */
    assert(dc_to_jvs_word(CONT_A, JVS_CLASS_PAD, JVS_WORD_TOURNAMENT) == JVS_M);
    assert(dc_to_jvs_word(CONT_B, JVS_CLASS_PAD, JVS_WORD_TOURNAMENT) == JVS_S);
    assert(dc_to_jvs_word(CONT_X, JVS_CLASS_PAD, JVS_WORD_TOURNAMENT) == JVS_BARRAGE);
    assert(dc_to_jvs_word(CONT_Y, JVS_CLASS_PAD, JVS_WORD_TOURNAMENT) == JVS_A);
    assert(dc_to_jvs_word(CONT_LTRIG, JVS_CLASS_PAD, JVS_WORD_TOURNAMENT) == JVS_OD);
    assert(dc_to_jvs_word(CONT_RTRIG, JVS_CLASS_PAD, JVS_WORD_TOURNAMENT) == JVS_A);
    assert(dc_to_jvs_word(CONT_B, JVS_CLASS_PAD, JVS_WORD_OLD) == JVS_A);
    assert(dc_to_jvs_word(CONT_X, JVS_CLASS_PAD, JVS_WORD_OLD) == JVS_S);
    assert(dc_to_jvs_word(CONT_LTRIG | CONT_B, JVS_CLASS_PAD, JVS_WORD_OLD) == JVS_A);
    assert(dc_to_jvs_word(CONT_Z, JVS_CLASS_STICK, JVS_WORD_ARCADE) == JVS_BARRAGE);
    assert(dc_to_jvs_word(CONT_C, JVS_CLASS_STICK, JVS_WORD_ARCADE) == JVS_OD);
    assert(dc_to_jvs_word(CONT_B, JVS_CLASS_STICK, JVS_WORD_ARCADE) == 0);
    assert(dc_to_jvs_word(CONT_Z, JVS_CLASS_PAD, JVS_WORD_ARCADE) == 0);        /* class picks the button list */
    assert(dc_to_jvs_word(CONT_RTRIG | CONT_LTRIG, JVS_CLASS_STICK, JVS_WORD_ARCADE) == 0); /* no trigger ghosts */
    /* Start + 8-way are layout-blind; chords OR */
    assert(dc_to_jvs_word(CONT_START | CONT_DPAD_LEFT, JVS_CLASS_PAD, 0xffffffu) == (JVS_START | JVS_LEFT));
    assert(dc_to_jvs_word(CONT_A | CONT_X, JVS_CLASS_PAD, JVS_WORD_TOURNAMENT) == (JVS_M | JVS_BARRAGE));
    /* B.O.S.S. on B (nibble 1), NONE on R (nibble 5), junk nibble */
    assert(JVS_FUNC_MASK[JVS_FUNC_BOSS] == (JVS_M | JVS_S | JVS_A));            /* the macro: 3 bits, 1 poll */
    assert(JVS_FUNC_MASK[JVS_FUNC_NONE] == 0);
    assert(dc_to_jvs_word(CONT_B, JVS_CLASS_PAD, (JVS_WORD_TOURNAMENT & ~(0xfu << 4)) | ((unsigned)JVS_FUNC_BOSS << 4)) == (JVS_M | JVS_S | JVS_A));
    assert(dc_to_jvs_word(CONT_RTRIG, JVS_CLASS_PAD, (JVS_WORD_TOURNAMENT & ~(0xfu << 20)) | ((unsigned)JVS_FUNC_NONE << 20)) == 0);
    assert(dc_to_jvs_word(CONT_A, JVS_CLASS_PAD, 0xfu) == 0);
    /* classifier (measured caps words: PAD/STICK as in the block below,
       flycast maple_devs.cpp:85/:292) */
    assert(jvs_pick_class(0xfe060f00u) == JVS_CLASS_PAD);
    assert(jvs_pick_class(0xff070000u) == JVS_CLASS_STICK);
    /* staged-flag rule */
    assert(jvs_layout_word(1u, 0u, JVS_CLASS_PAD) == 0u);
    assert(jvs_layout_word(0u, 0x111111u, JVS_CLASS_PAD) == JVS_WORD_TOURNAMENT);
    assert(jvs_layout_word(2u, 0x111111u, JVS_CLASS_STICK) == JVS_WORD_ARCADE);
    assert(jvs_layout_word(0xffffffffu, 0x111111u, JVS_CLASS_STICK) == JVS_WORD_ARCADE);
    /* test boot: Start -> test bit, A -> Service, everything else live */
    { unsigned tb; assert(dc_to_jvs_test(CONT_START | CONT_X, JVS_CLASS_PAD, JVS_WORD_OLD, &tb) == JVS_S && tb == 1u);
      assert(dc_to_jvs_test(CONT_A, JVS_CLASS_PAD, JVS_WORD_OLD, &tb) == JVS_SERVICE && tb == 0u); }

    /* dc_cond_to_pressed: raw GetCondition words 2/3 -> the pressed mask above.
       w2 = buttons | rtrig<<16 | ltrig<<24 (buttons ACTIVE-LOW), w3 = joyx |
       joyy<<8 | ... (0-255, 128 centred, low = up/left). caps = the DEVINFO
       function-data word: an axis byte is only trusted if the device declares
       that axis (tester bug 2026-09-26: the Arcade Stick declares none and
       fills all six bytes with 0x80 -- threshold 128 read that as both
       triggers held). PAD = standard controller 0xfe060f00, STICK = Ascii
       Stick 0xff070000 (flycast maple_devs.cpp:85/:292; bit meanings KOS
       dc/maple/controller.h:258-263). */
    {
        const unsigned NEUTRAL3 = 0x80808080u;      /* all four axes centred */
        const unsigned PAD   = 0xfe060f00u;         /* rtrig|ltrig|X|Y axes */
        const unsigned STICK = 0xff070000u;         /* no analog axes at all */
        assert(dc_cond_to_pressed(0xffff, NEUTRAL3, PAD) == 0);     /* idle pad */
        /* one button held: its wire bit goes to 0 */
        assert(dc_to_jvs_word(dc_cond_to_pressed(0xffff & ~CONT_START, NEUTRAL3, PAD), JVS_CLASS_PAD, JVS_WORD_OLD)
               == JVS_START);
        assert(dc_to_jvs_word(dc_cond_to_pressed(0xffff & ~CONT_Y, NEUTRAL3, PAD), JVS_CLASS_PAD, JVS_WORD_OLD)
               == JVS_BARRAGE);
        /* R trigger is analog: below 128 idle, at/above 128 -> OverDrive */
        assert(dc_to_jvs_word(dc_cond_to_pressed(0xffff | (127u << 16), NEUTRAL3, PAD), JVS_CLASS_PAD, JVS_WORD_OLD) == 0);
        assert(dc_to_jvs_word(dc_cond_to_pressed(0xffff | (128u << 16), NEUTRAL3, PAD), JVS_CLASS_PAD, JVS_WORD_OLD)
               == JVS_OD);
        assert(dc_to_jvs_word(dc_cond_to_pressed(0xffff | (255u << 16), NEUTRAL3, PAD), JVS_CLASS_PAD, JVS_WORD_OLD)
               == JVS_OD);
        /* L trigger (bits 24-31) duplicates B/Action: same 128 threshold as R */
        assert(dc_to_jvs_word(dc_cond_to_pressed(0xffff | (127u << 24), NEUTRAL3, PAD), JVS_CLASS_PAD, JVS_WORD_OLD) == 0);
        assert(dc_to_jvs_word(dc_cond_to_pressed(0xffff | (128u << 24), NEUTRAL3, PAD), JVS_CLASS_PAD, JVS_WORD_OLD)
               == JVS_A);
        assert(dc_to_jvs_word(dc_cond_to_pressed(0xffff | (255u << 24), NEUTRAL3, PAD), JVS_CLASS_PAD, JVS_WORD_OLD)
               == JVS_A);
        /* analog stick drives the same 8-way as the D-pad; neutral band
           0x40..0xc0 inclusive stays idle */
        assert(dc_to_jvs_word(dc_cond_to_pressed(0xffff, 0x8080803fu, PAD), JVS_CLASS_PAD, JVS_WORD_OLD) == JVS_LEFT);
        assert(dc_to_jvs_word(dc_cond_to_pressed(0xffff, 0x808080c1u, PAD), JVS_CLASS_PAD, JVS_WORD_OLD) == JVS_RIGHT);
        assert(dc_to_jvs_word(dc_cond_to_pressed(0xffff, 0x80803f80u, PAD), JVS_CLASS_PAD, JVS_WORD_OLD) == JVS_UP);
        assert(dc_to_jvs_word(dc_cond_to_pressed(0xffff, 0x8080c180u, PAD), JVS_CLASS_PAD, JVS_WORD_OLD) == JVS_DOWN);
        assert(dc_cond_to_pressed(0xffff, 0x80804080u, PAD) == 0);   /* band edge */
        assert(dc_cond_to_pressed(0xffff, 0x8080c080u, PAD) == 0);   /* band edge */
        assert(dc_to_jvs_word(dc_cond_to_pressed(0xffff, 0x80803f3fu, PAD), JVS_CLASS_PAD, JVS_WORD_OLD)
               == (JVS_UP | JVS_LEFT));                              /* diagonal */
        /* D-pad and analog OR together, and coexist with buttons */
        assert(dc_to_jvs_word(dc_cond_to_pressed(0xffff & ~(CONT_DPAD_UP | CONT_A),
                                            0x808080c1u, PAD), JVS_CLASS_PAD, JVS_WORD_OLD)
               == (JVS_UP | JVS_M | JVS_RIGHT));
        /* ... but an opposed pair reports NEITHER, the same mutual exclusion
           the emulator applies (maple_devs.cpp:67-71/:91-92 on the active-low
           kcode, maple_jvs.cpp:2224-2228 on the JVS word). Reachable here
           because stick and D-pad are OR'd and can disagree. */
        assert(dc_to_jvs_word(dc_cond_to_pressed(0xffff & ~CONT_DPAD_RIGHT,
                                            0x8080803fu, PAD), JVS_CLASS_PAD, JVS_WORD_OLD) == 0);   /* dpad R + stick L */
        assert(dc_to_jvs_word(dc_cond_to_pressed(0xffff & ~CONT_DPAD_UP,
                                            0x8080c180u, PAD), JVS_CLASS_PAD, JVS_WORD_OLD) == 0);   /* dpad U + stick D */
        /* the exclusion is per axis and takes nothing else with it */
        assert(dc_to_jvs_word(dc_cond_to_pressed(0xffff & ~(CONT_DPAD_RIGHT | CONT_A),
                                            0x80803f3fu, PAD), JVS_CLASS_PAD, JVS_WORD_OLD)
               == (JVS_UP | JVS_M));                               /* L/R cancel, UP lives */

        /* Arcade Stick regression (tester report 2026-09-26): the exact idle
           frame flycast's maple_ascii_stick sends -- buttons all released,
           every axis byte 0x80 (getAnalogAxis returns 0x80 unconditionally,
           maple_devs.cpp:313) -- must read as NOTHING pressed, not
           shield+OverDrive held. */
        assert(dc_cond_to_pressed(0xffffu | (0x80u << 16) | (0x80u << 24),
                                  NEUTRAL3, STICK) == 0);
        /* undeclared axes are ignored whatever the filler value (real HKT-7300
           filler bytes unverified -- gate on the declaration, not the value) */
        assert(dc_cond_to_pressed(0xffffu | (0xffu << 16) | (0xffu << 24),
                                  0x00000000u, STICK) == 0);
        /* buttons still live on a stick, including the ones only it has */
        assert(dc_to_jvs_word(dc_cond_to_pressed((0xffffu & ~CONT_START)
                                            | (0x80u << 16) | (0x80u << 24),
                                            NEUTRAL3, STICK), JVS_CLASS_PAD, JVS_WORD_OLD) == JVS_START);
        assert(dc_to_jvs_word(dc_cond_to_pressed((0xffffu & ~CONT_DPAD_LEFT)
                                            | (0x80u << 16) | (0x80u << 24),
                                            NEUTRAL3, STICK), JVS_CLASS_PAD, JVS_WORD_OLD) == JVS_LEFT);
    }

    /* dc_to_jvs_test (Task 13): P1-only test-mode remap -- Start->Test
       (reported via *test_bit, NOT folded into the word: §TESTBIT-INJECT),
       A->Service (0x4000, folded into the word like any other control);
       everything else keeps its normal dc_to_jvs_word() binding. */
    {
        unsigned tb;
        assert(dc_to_jvs_test(0, JVS_CLASS_PAD, JVS_WORD_OLD, &tb) == 0 && tb == 0);                /* idle */
        assert(dc_to_jvs_test(CONT_START, JVS_CLASS_PAD, JVS_WORD_OLD, &tb) == 0 && tb == 1);       /* Start: Test only, no JVS_START */
        assert(dc_to_jvs_test(CONT_A, JVS_CLASS_PAD, JVS_WORD_OLD, &tb) == JVS_SERVICE && tb == 0); /* A: Service only, no JVS_M */
        assert(dc_to_jvs_test(CONT_START | CONT_A, JVS_CLASS_PAD, JVS_WORD_OLD, &tb)
               == JVS_SERVICE && tb == 1);                             /* both held: both fire */
        assert(dc_to_jvs_test(CONT_DPAD_UP, JVS_CLASS_PAD, JVS_WORD_OLD, &tb)
               == JVS_UP && tb == 0);                                  /* rest of the layout live */
        assert(dc_to_jvs_test(CONT_START | CONT_DPAD_UP, JVS_CLASS_PAD, JVS_WORD_OLD, &tb)
               == JVS_UP && tb == 1);                                  /* Start doesn't leak into the word */
        assert(dc_to_jvs_test(CONT_X | CONT_B | CONT_Y | CONT_RTRIG, JVS_CLASS_PAD, JVS_WORD_OLD, &tb)
               == (JVS_S | JVS_A | JVS_BARRAGE | JVS_OD) && tb == 0);  /* X/B/Y/R unaffected */
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

    /* dc_reset_combo: A+B+X+Y+Start, all five held (KOS CONT_RESET_BUTTONS). */
    {
        unsigned all = CONT_A | CONT_B | CONT_X | CONT_Y | CONT_START;
        assert(dc_reset_combo(all));
        assert(dc_reset_combo(all | CONT_DPAD_UP | CONT_RTRIG));   /* extras don't block it */
        assert(!dc_reset_combo(all & ~CONT_Y));                    /* any one missing: no reset */
        assert(!dc_reset_combo(all & ~CONT_START));
        assert(!dc_reset_combo(0));                                /* idle / no pad */
    }

    printf("PASS test_host dc_to_jvs + jvs_checksum\n");
    return 0;
}

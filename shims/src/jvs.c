/* Pure JVS translation. Host-compiled by test/test_host.c and linked into
 * the freestanding shim (no MMIO, no fences). */

/* DC Maple GetCondition button bits (kernel/arch/dreamcast/include/dc/maple/
 * controller.h, KOS tools/kos -- primary source, not copied from any
 * Cleopatra file: Cleopatra's own dc_to_jvs used raw (1u<<N) shifts inline,
 * no named CONT_* constants). cont_state_t.buttons is ACTIVE-LOW (0=pressed);
 * dc_to_jvs below takes the already-inverted PRESSED mask (see its comment).
 * CONT_RTRIG has no bit here -- ltrig/rtrig are separate 0-255 analog bytes
 * in cont_state_t, not part of .buttons -- so bit 16 (just past the real
 * 0-15 button field) is a shim-synthesized "digital rtrig" flag, set by
 * dc_cond_to_pressed() below (Task 12 wired the maple_getcond call site). */
#define CONT_C          (1u << 0)
#define CONT_B          (1u << 1)
#define CONT_A          (1u << 2)
#define CONT_START      (1u << 3)
#define CONT_DPAD_UP    (1u << 4)
#define CONT_DPAD_DOWN  (1u << 5)
#define CONT_DPAD_LEFT  (1u << 6)
#define CONT_DPAD_RIGHT (1u << 7)
#define CONT_Y          (1u << 9)
#define CONT_X          (1u << 10)
#define CONT_RTRIG      (1u << 16)  /* synthetic: rtrig>=128, not a real KOS button bit */
#define CONT_LTRIG      (1u << 17)  /* synthetic: ltrig>=128, same scheme as CONT_RTRIG */

/* DC pad -> senkosp JVS P1 digital word (input-map.md §DC pad layout, measured bits) */
#define JVS_START  0x8000
#define JVS_SERVICE 0x4000
#define JVS_UP     0x2000
#define JVS_DOWN   0x1000
#define JVS_LEFT   0x0800
#define JVS_RIGHT  0x0400
#define JVS_M      0x0200   /* BTN0 "MAIN"   <- DC A */
#define JVS_S      0x0100   /* BTN1 "SUB"    <- DC X */
#define JVS_BARRAGE 0x0080  /* BTN2          <- DC Y */
#define JVS_A      0x0040   /* BTN3 "ACTION" <- DC B */
#define JVS_OD     0x0020   /* BTN4          <- DC R trigger */
/* Test = bit 18, Coin = bit 19 of the 32-bit word (source-derived) */
#define JVS_TEST   (1u << 18)
#define JVS_COIN   (1u << 19)

unsigned dc_to_jvs(unsigned dc_buttons) {
    unsigned w = 0;
    /* Fill from the live GetCondition struct in maple.c; this fn takes the
     * already-normalized pressed-mask. */
    if (dc_buttons & CONT_START)         w |= JVS_START;
    if (dc_buttons & CONT_DPAD_UP)       w |= JVS_UP;
    if (dc_buttons & CONT_DPAD_DOWN)     w |= JVS_DOWN;
    if (dc_buttons & CONT_DPAD_LEFT)     w |= JVS_LEFT;
    if (dc_buttons & CONT_DPAD_RIGHT)    w |= JVS_RIGHT;
    if (dc_buttons & CONT_A)             w |= JVS_M;
    if (dc_buttons & CONT_X)             w |= JVS_S;
    if (dc_buttons & CONT_B)             w |= JVS_A;
    if (dc_buttons & CONT_Y)             w |= JVS_BARRAGE;
    if (dc_buttons & CONT_RTRIG)         w |= JVS_OD;   /* R as digital: see dc_cond_to_pressed */
    if (dc_buttons & CONT_LTRIG)         w |= JVS_A;    /* L duplicates B (Action/block) --
                                                         * operator request 2026-08-30, barrier-shot
                                                         * ease; input-map.md §DC pad layout */
    return w;
}

/* Test-mode remap (Task 13, criterion 4): when SHIM_STATE[0]==1 (combo boot
 * into the test image, loader/main.c seeds it), the MIE test menu takes over
 * pad 1's Start and A -- Start advances (Test), A selects (Service), the
 * arcade convention (docs/kb/phase4-conversion.md §TESTBIT-INJECT). Only P1
 * (port 0, the same pad the boot combo itself reads) is remapped; P2 keeps
 * calling plain dc_to_jvs() untouched in src/main.c, and every OTHER P1
 * control (D-pad, X, B, Y, R) keeps its normal game binding here too --
 * "leave the rest of the layout live" per the task brief.
 *
 * Test is NOT a bit of the 16-bit P1/P2 button word. The emulator's internal
 * kcode constant NAOMI_TEST_KEY == 1<<18 (maple_devs.h:97) names a bit
 * position in Flycast's *own* digital-input abstraction, not a wire offset;
 * the actual has-data frame carries Test in its own byte, +0x1f bit 7
 * (maple_jvs.cpp:2243, confirmed by this port's §TESTBIT-INJECT verdict).
 * OR-ing 1<<18 into this 16-bit word would be exactly the "silently wrong"
 * mistake that verdict exists to prevent, so Test is reported through
 * *test_bit instead, for the caller (src/main.c mie_poll) to place at its
 * own pinned frame byte. Service, unlike Test, genuinely IS bit 0x4000 of
 * the button word -- the same byte Start's 0x8000 lives in (input-map.md's
 * measured bit, §TESTBIT-INJECT: "Service *is* a bit") -- so it is folded
 * into the returned word like any other control. */
unsigned dc_to_jvs_test(unsigned dc_buttons, unsigned *test_bit) {
    *test_bit = (dc_buttons & CONT_START) ? 1u : 0u;
    return dc_to_jvs(dc_buttons & ~(CONT_START | CONT_A))
         | ((dc_buttons & CONT_A) ? JVS_SERVICE : 0u);
}

/* Raw DC GetCondition reply words -> the PRESSED mask dc_to_jvs() takes above.
 * This is the whole hardware-shaped half of the input path; keeping it here
 * (pure, no MMIO) is what lets test/test_host.c cover it.
 *
 * w2/w3 are reply words 2 and 3, i.e. the `cont_cond_t` the DC controller
 * returns one word past the function code (KOS
 * ../cleopatra/tools/kos/kernel/arch/dreamcast/hardware/maple/controller.c:
 * 28-36 raw struct, :171 `raw = respbuf + 1`):
 *   w2 = u16 buttons | rtrig << 16 | ltrig << 24
 *   w3 = joyx | joyy << 8 | joy2x << 16 | joy2y << 24
 * Same order the emulator's own controller emits -- w16(buttons) then axes
 * R, L, X, Y, -, - (../flycast4naomi2dreamcast/core/hw/maple/maple_devs.cpp:
 * 185-200, :96-114).
 *
 * Three normalizations, each with its source:
 *  1. Buttons are ACTIVE-LOW on the wire; JVS is active-high. KOS does the
 *     same inversion (`cooked->buttons = (~raw->buttons) & 0xffff`,
 *     controller.c:176). Unused bits come back as 1 (released) because the
 *     device ORs them in (`return kcode | 0xF901`, maple_devs.cpp:93), so the
 *     inverse has no stray set bits.
 *  2. R trigger is an analog 0-255 byte, not a button. Threshold 128 (half
 *     press) -> the synthetic CONT_RTRIG bit -> JVS OverDrive.
 *  3. The analog stick is OR'd into the D-pad bits: the port's control layout
 *     binds BOTH to the 8-way stick (docs/kb/input-map.md §DC pad layout).
 *     Axes are 0-255, 128 centred, low = up/left (KOS controller.c:178-179
 *     `((int)raw->joyx) - 128`; direction from the emulator's own analog->DPad
 *     conversion, maple_devs.cpp:1483-1513, which presses UP for joyy below
 *     centre). The neutral band 0x40..0xc0 is that same conversion's band.
 *     Because the stick and the D-pad are OR'd, they can disagree (stick left
 *     + D-pad right), which an arcade lever cannot do -- so the fold ends with
 *     the same MUTUAL EXCLUSION the emulator applies at both of its own sites:
 *     both of an opposed pair pressed => NEITHER is reported.
 *       maple_devs.cpp:67-71  `mutualExclusion(kcode, mask)` = if both bits are
 *                             0 (active-low: both pressed) set both (release
 *                             both), applied at :91-92 right before the reply
 *       maple_jvs.cpp:2224-2228  the same rule on the active-high JVS word:
 *                             `if ((button & (UP|DOWN)) == (UP|DOWN))
 *                                  button &= ~(UP|DOWN);`
 * L trigger duplicates B (JVS Action = block/barrier): operator request
 * 2026-08-30 after hardware play -- barrier-shots need block held while the
 * face buttons fire. Same threshold-128 digital scheme as R/OverDrive.
 * (input-map.md §DC pad layout row updated; the old "unbound, may duplicate
 * Barrage" reservation is superseded.) */
#define DC_TRIG_ON  128     /* R trigger digital threshold, 0-255 */
#define DC_AXIS_LO  0x40    /* analog neutral band (maple_devs.cpp:1494-1512) */
#define DC_AXIS_HI  0xc0
unsigned dc_cond_to_pressed(unsigned w2, unsigned w3) {
    unsigned p = (~w2) & 0xffffu;                       /* active-low -> pressed */
    unsigned x = w3 & 0xffu, y = (w3 >> 8) & 0xffu;
    if (((w2 >> 16) & 0xffu) >= DC_TRIG_ON) p |= CONT_RTRIG;
    if (((w2 >> 24) & 0xffu) >= DC_TRIG_ON) p |= CONT_LTRIG;
    if (y < DC_AXIS_LO) p |= CONT_DPAD_UP;
    if (y > DC_AXIS_HI) p |= CONT_DPAD_DOWN;
    if (x < DC_AXIS_LO) p |= CONT_DPAD_LEFT;
    if (x > DC_AXIS_HI) p |= CONT_DPAD_RIGHT;
    /* opposed pair both pressed -> report neither (see the header comment) */
    if ((p & (CONT_DPAD_UP | CONT_DPAD_DOWN)) == (CONT_DPAD_UP | CONT_DPAD_DOWN))
        p &= ~(CONT_DPAD_UP | CONT_DPAD_DOWN);
    if ((p & (CONT_DPAD_LEFT | CONT_DPAD_RIGHT)) == (CONT_DPAD_LEFT | CONT_DPAD_RIGHT))
        p &= ~(CONT_DPAD_LEFT | CONT_DPAD_RIGHT);
    return p;
}

/* JVS checksum = (sum of frame bytes [0x1b..0x39]) & 0xff, stored at [0x3a].
 * Mirrors the emitter's calc_crc (maple_jvs.cpp:2487-2491, re-read in Task 12:
 * `for (i = 1; i < length; i++) calc_crc += buffer_out[i]`, then JVS_OUT writes
 * it at buffer_out[length]; buffer_out[0] is the 0xE0 sync at frame +0x1a). So
 * the sum runs over everything after the sync, up to but excluding the checksum
 * -- for senkosp's own has-data frame, 0x1b..0x39 with the byte at 0x3a, which
 * the frame's own length field independently confirms (0x1c + frame[0x1c] ==
 * 0x3a; asserted in scripts/extract_mie_blobs.py). Must be recomputed whenever
 * a button byte changes; src/main.c mie_poll() does that every poll. */
unsigned char jvs_checksum(const unsigned char *f) {
    unsigned int s = 0;
    int i;
    for (i = 0x1b; i <= 0x39; i++) s += f[i];
    return (unsigned char)s;
}

/* Cleopatra Fortune Plus's golden 64-byte has-data JVS digital-read reply,
 * byte-captured from THAT game's steady-state sub-0x33 frame -- not valid
 * for senkosp (different JVS I/O board enumeration, different idle frame).
 * #if 0'd, not deleted: same structural role, needs senkosp's own capture
 * (Tasks 10-12) before it can be replaced in place. */
#if 0  /* re-enabled per-task: see plan Tasks 10-12 */
const unsigned char jvs_hasdata[64] = {
    0x87,0x00,0x20,0x0f, 0x16,0xff,0xff,0xff, 0x00,0xff,0xff,0xff, 0x00,0x00,0x00,0x00,
    0x00,0x00,0x00,0x00, 0x00,0x00,0x8e,0x01, 0x00,0x21,0xe0,0x00, 0x1e,0x01,0x01,0x00,
    0x00,0x00,0x00,0x00, 0x01,0x00,0x00,0x00, 0x00,0x01,0x80,0x00, 0x80,0x00,0x80,0x00,
    0x80,0x00,0x80,0x00, 0x80,0x00,0x80,0x00, 0x80,0x00,0x22,0x00, 0x00,0x00,0x00,0x00,
};
#endif /* re-enabled per-task: see plan Tasks 10-12 */

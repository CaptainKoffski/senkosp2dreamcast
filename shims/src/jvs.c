/* Pure JVS translation. Host-compiled by test/test_host.c and linked into
 * the freestanding shim (no MMIO, no fences). */

/* DC Maple GetCondition button bits (kernel/arch/dreamcast/include/dc/maple/
 * controller.h, KOS tools/kos -- primary source, not copied from any
 * Cleopatra file: Cleopatra's own dc_to_jvs used raw (1u<<N) shifts inline,
 * no named CONT_* constants). cont_state_t.buttons is ACTIVE-LOW (0=pressed);
 * dc_to_jvs below takes the already-inverted PRESSED mask (see its comment).
 * CONT_RTRIG has no bit here -- ltrig/rtrig are separate 0-255 analog bytes
 * in cont_state_t, not part of .buttons -- so bit 16 (just past the real
 * 0-15 button field) is a shim-synthesized "digital rtrig" flag the future
 * caller sets from cont_state.rtrig > 128 before calling dc_to_jvs (Tasks
 * 10-12 wire the actual maple_getcond call site; this only needs to compile
 * and be internally consistent for Task 6). */
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
#define CONT_RTRIG      (1u << 16)  /* synthetic: rtrig>128, not a real KOS button bit */

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
    if (dc_buttons & CONT_RTRIG)         w |= JVS_OD;   /* R as digital: rtrig > 128 mapped by caller */
    return w;
}

/* JVS checksum = (sum of frame bytes [0x1b..0x39]) & 0xff, stored at [0x3a].
 * Mirrors the Flycast emitter's calc_crc (maple_jvs.cpp:2476-2478): the sum runs
 * over everything after the E0 sync. Must be recomputed whenever a button byte
 * changes. Protocol-generic (not Cleopatra-specific); kept live for whichever
 * task captures senkosp's own golden reply frame. */
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

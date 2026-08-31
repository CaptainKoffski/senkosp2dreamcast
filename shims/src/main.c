/* Cleopatra Fortune Plus's async-Maple MIE service, config-time JVS enum,
 * EEPROM read/write-skip and settings-orchestrator hooks -- every function
 * below keys off THAT game's Ghidra-RE'd pool/RAM addresses (0x8c0e6400,
 * 0x8c1c9528/954c, 0x8c081224, 0x8c034020, ...), none of which apply to
 * Senko no Ronde Special (different ROM, different layout). #if 0'd whole,
 * not deleted or trimmed: it is the proven STRUCTURE for the same problem
 * class (Naomi MIE/JVS transport has no real Maple hardware match on DC),
 * kept in this file -- not just git history -- for Tasks 10-12 to re-derive
 * senkosp's own addresses/blobs against and re-enable piece by piece. */
#include "shim_iface.h"

/* ---- live shim entry points (Task 10) ----------------------------------- */
void shim_mark(unsigned int slot, unsigned short color);   /* util.c */

/* RESET-PATCH target (docs/kb/phase4-conversion.md §Restart stub). The game's
 * restart stub FUN_8c067e18 ends in `jmp @r1` with r1 loaded from pool
 * 0x8c067e4c = 0x8dfff000 -- a Naomi-BIOS re-entry that is not there on a
 * Dreamcast. The generator rewrites that one pool word (both images) to point
 * here, so "restart" becomes a DC reboot: 0xa0000000 is the SH-4 reset vector
 * through P2, i.e. the start of the DC BIOS ROM, entered uncached exactly as
 * the CPU does out of reset. The stub's two preceding calls still run (a
 * memcpy into the unused fixed page 0x0dfff000 and an icache-flush-shaped
 * call) -- harmless leftovers on a path that reboots anyway; only the jump is
 * redirected, which is why patching the single pool word suffices.
 * slot15 white = the restart path was taken (visible for the frame or two
 * before the BIOS blanks the screen). */
/* SHIM_REBOOT_FREEZE (diagnostic builds only, default 0): instead of
 * rebooting, dump the caller's return address and a slice of its stack over
 * serial and spin. The reboot destroys the very evidence a reboot loop needs
 * -- log tail, HUD, RAM -- so this converts the loop into one readable halt.
 * Every 0x8c0xxxxx-looking word in the dump is a candidate saved PR, i.e. the
 * call chain that decided to restart. */
#ifndef SHIM_REBOOT_FREEZE
#define SHIM_REBOOT_FREEZE 0
#endif
void shim_reboot(void);
void shim_reboot(void) {
    shim_mark(15, 0xffff);
#if SHIM_REBOOT_FREEZE
    {
        void scif_puts(const char *); void scif_puthex(unsigned int);
        unsigned int sp; __asm__ volatile ("mov r15,%0" : "=r"(sp));
        scif_puts("SHIM REBOOT ra="); scif_puthex((unsigned int)__builtin_return_address(0));
        scif_puts(" sp="); scif_puthex(sp); scif_puts("\nSTACK");
        for (unsigned int i = 0; i < 64u; i++) {
            if ((i & 7u) == 0) { scif_puts("\n +"); scif_puthex(i * 4u); scif_puts(":"); }
            scif_puts(" "); scif_puthex(*(volatile unsigned int *)(sp + i * 4u));
        }
        scif_puts("\nFROZEN\n");
        for (;;) ;
    }
#endif
    ((void (*)(void))0xa0000000)();
}

/* G-CARVE (r8, docs/kb/phase5-hardware.md §Round 6 prep). The patch table
 * repoints the KAMUI2 init chain's stage-7 pool word (FUN_8c02e300, dat
 * 0xe4ec -> FUN_8c031af0) here. Reloc entry 4's -0x11A000 TA total would let
 * the library's own carve (ispl = olb*3/4) set ISP to 0x5a4e0 = 369,888 --
 * below the measured demand max 0x664e0 -- so after running the original
 * stage this stomps the ispl/oll dev words (base 0x8c19e4bc, +0x844/+0x848)
 * and their absolute frame-descriptor copies (bank A 0x8c1a18bc/c0, bank B
 * 0x8c1a1948/4c, located via the rndreg-dc2 RAM dump) to the operator-
 * accepted +10%-over-demand layout: ispl=0x711e0, oll=0x712e0. olb/nopbi are
 * per-bank-size-derived and stay library-computed. One serial line so both
 * emulator and hardware legs can confirm the hook fired. */
void shim_g_carve(void);
void shim_g_carve(void) {
    ((void (*)(void))0x8c031af0)();       /* original init-chain stage 7 */
    *(volatile unsigned int *)0x8c19ed00 = 0x000711e0;  /* dev+0x844 ispl */
    *(volatile unsigned int *)0x8c19ed04 = 0x000712e0;  /* dev+0x848 oll  */
    *(volatile unsigned int *)0x8c1a18bc = 0x000711e0;  /* desc bank A ispl */
    *(volatile unsigned int *)0x8c1a18c0 = 0x000712e0;  /* desc bank A oll  */
    *(volatile unsigned int *)0x8c1a1948 = 0x004711e0;  /* desc bank B ispl */
    *(volatile unsigned int *)0x8c1a194c = 0x004712e0;  /* desc bank B oll  */
    { void scif_puts(const char *); scif_puts("GCARVE\n"); }
}

/* ======================================================================
 * Maple/MIE service (Task 11) -- the shim half of the maple mirror.
 *
 * The patch table repoints every maple register constant in senkosp's image
 * into MAPLE_MIRROR (docs/kb/phase4-conversion.md §Maple-patch sites), so the
 * game's maple programming writes shim RAM instead of Dreamcast maple
 * registers, and its `SB_MDST reads 0` completion poll would spin forever.
 * Five mid-body detours (§MAPLE-BOOT-STRATEGY) land in src/mtramp.S, which
 * calls shim_maple_boot() below with every register preserved.
 *
 * What this file does per kick: walk the command list the game programmed
 * into mirror SB_MDSTAR exactly as real Holly does (§MIE-DESC, transcribed
 * from maple_DoDma, ../flycast4naomi2dreamcast/core/hw/maple/maple_if.cpp:
 * 198-360), synthesize each frame's reply into that frame's own recv address
 * with UNCACHED stores (it stands in for a DMA-to-RAM write), and clear the
 * mirror's SB_MDST so the poll exits. Synchronous where hardware is
 * asynchronous, which is strictly stronger: the reply is ready earlier and
 * nothing in either driver reads the maple-DMA interrupt (§MIE-DESC).
 * ====================================================================== */
typedef unsigned int u32;
typedef unsigned char u8;

void scif_puts(const char *); void scif_puthex(unsigned int);   /* src/scif.c */

#ifndef SHIM_TRACE
#define SHIM_TRACE 0            /* per-transaction serial; see cart.c */
#endif

/* Captured MIE replies (scripts/extract_mie_blobs.py -> shims/build/mie_blobs.c,
 * gitignored: captured traffic). Provenance: captures/phase4/pc2.log, the
 * Naomi-mode leg, post-MAINHANDOFF only -- i.e. senkosp's own transactions,
 * never the Naomi BIOS's (§R5). */
extern const unsigned char mie_sub01[];   extern const unsigned int mie_sub01_len;
extern const unsigned char mie_sub03[];   extern const unsigned int mie_sub03_len;
extern const unsigned char mie_sub13[];   extern const unsigned int mie_sub13_len;
extern const unsigned char mie_sub17[];   extern const unsigned int mie_sub17_len;
extern const unsigned char mie_sub21[];   extern const unsigned int mie_sub21_len;
extern const unsigned char mie_sub31[];   extern const unsigned int mie_sub31_len;
extern const unsigned char mie_sub33[];   extern const unsigned int mie_sub33_len;
extern const unsigned char mie_86empty[]; extern const unsigned int mie_86empty_len;
extern const unsigned char mie_jvsf1[];   extern const unsigned int mie_jvsf1_len;
extern const unsigned char mie_jvs10[];   extern const unsigned int mie_jvs10_len;
extern const unsigned char mie_jvs11[];   extern const unsigned int mie_jvs11_len;
extern const unsigned char mie_jvs12[];   extern const unsigned int mie_jvs12_len;
extern const unsigned char mie_jvs13[];   extern const unsigned int mie_jvs13_len;
extern const unsigned char mie_jvs14[];   extern const unsigned int mie_jvs14_len;
extern const unsigned char mie_jvsdflt[]; extern const unsigned int mie_jvsdflt_len;

/* Live pad path (Task 12): src/maple.c does the real DC GetCondition DMA and
 * returns the normalized pressed mask; src/jvs.c maps it to the JVS word and
 * owns the frame checksum. */
unsigned int  maple_getcond(unsigned int port);         /* src/maple.c */
unsigned      dc_to_jvs(unsigned dc_buttons);           /* src/jvs.c */
unsigned      dc_to_jvs_test(unsigned dc_buttons, unsigned *test_bit); /* src/jvs.c, Task 13 */
unsigned char jvs_checksum(const unsigned char *f);     /* src/jvs.c */
void *xmemcpy(void *, const void *, u32);               /* src/util.c */

#define MMIR(o) (*(volatile u32 *)P2ADDR(MAPLE_MIRROR + (o)))   /* mirror cell */
#define UW(a)   (*(volatile u32 *)P2ADDR(a))    /* DMA-source view: uncached */
#define UB(a)   (*(volatile u8  *)P2ADDR(a))

/* .data (non-zero) per house style -- the loader zero-fills the shim window,
 * so a .bss counter could not tell "never ran" from "ran zero times". */
u32 maple_count = 0x10000;      /* transactions serviced (+ sentinel) */
static u8 pending_jvs = 0xff;   /* last transmitted JVS cmd; 0xff = none */
static u8 odd_seen = 0x80;      /* bitmap of unmodelled cmds/subs met, once each */

static void put(u32 rcv, const unsigned char *b, u32 n) {
    volatile u8 *rx = (volatile u8 *)P2ADDR(rcv);
    while (n--) *rx++ = *b++;
}
static void put1(u32 rcv, u32 w) { *(volatile u32 *)P2ADDR(rcv) = w; }

/* ---- the steady per-frame input poll (sub 0x33) ------------------------- *
 * The captured blob IS senkosp's idle has-data frame, so the shim builds each
 * poll by copying it and overwriting only the live fields: the two player
 * words and the checksum they feed. Offsets and the checksum rule are pinned
 * in docs/kb/phase4-conversion.md §Input ABI / §TESTBIT-INJECT, re-derived
 * from the emitter:
 *   +0x1f  Test byte (bit 7)  -- left as captured (0x00) in NORMAL mode, no
 *          pad binding on this port for the live game (input-map.md §DC pad
 *          layout). In TEST mode (SHIM_STATE[0]==1, Task 13) P1's Start is
 *          remapped to it -- see dc_to_jvs_test() in src/jvs.c.
 *   +0x20  P1 buttons, hi then lo   (maple_jvs.cpp:2248, :2252 -- JVS_OUT of
 *   +0x22  P2 buttons, hi then lo    inputs[player]>>8 then inputs[player],
 *                                    once per player, big-endian on the wire)
 *   +0x25/+0x27 coin counters -- left as captured (free play, no coin binding)
 *   +0x3a  JVS checksum = sum(frame[0x1b..0x39]) & 0xff (maple_jvs.cpp:
 *          2487-2491: `for (i = 1; i < length; i++) calc_crc += buffer_out[i]`
 *          with buffer_out[0] = the 0xE0 sync at frame +0x1a).
 * Everything else -- both maple frame headers, the JVS sync/length/status, the
 * eight idle 0x8000 analog channels, and the trailing ack frame at +0x3c -- is
 * replayed byte-for-byte, which is what makes an idle-pad build byte-identical
 * to the captured idle frame (the equivalence check in the Task 12 report).
 *
 * TEST mode (Task 13, criterion 4): SHIM_STATE[0] is seeded by the loader's
 * boot combo (loader/main.c, Task 10). Only P1's word/branch changes -- P2
 * always takes the plain dc_to_jvs() path below, live in both modes -- and
 * the else-branch for P1 is untouched from Task 12, so a NORMAL boot (the
 * idle-frame equivalence assert's own regime) executes the exact same
 * instructions it always did. */
static void mie_poll(u32 rcv) {
    u8 f[68] = {0};                     /* = mie_sub33_len by capture; zeroed so
                                         * a short blob can never feed the
                                         * checksum uninitialized bytes */
    u32 n = mie_sub33_len, j1, j2;
    if (n > sizeof f) n = sizeof f;     /* bounded: never read past the blob */
    xmemcpy(f, mie_sub33, n);
    if (UW(SHIM_STATE) == 1u) {         /* test boot: P1 Start->Test, A->Service */
        unsigned test_bit;
        j1 = dc_to_jvs_test(maple_getcond(0), &test_bit);
        f[0x1f] = (u8)(test_bit ? 0x80 : 0x00);
    } else {
        j1 = dc_to_jvs(maple_getcond(0));   /* DC port A -> P1 */
    }
    j2 = dc_to_jvs(maple_getcond(1));   /* DC port B -> P2 (no pad -> 0 = idle) */
    f[0x20] = (u8)(j1 >> 8); f[0x21] = (u8)j1;
    f[0x22] = (u8)(j2 >> 8); f[0x23] = (u8)j2;
    f[0x3a] = jvs_checksum(f);
    if (SHIM_TRACE) {                   /* change-gated: one line per press */
        static u32 in_last = 0xffffffffu;
        u32 key = (j1 << 16) | j2;
        if (key != in_last) {
            /* hdrA/hdrB are the raw maple reply headers of the two
             * GetConditions (src/maple.c). Low byte 8 = DATATRF, i.e. the pad
             * answered; ffffffff = no device; 0 = the DMA never wrote the
             * buffer. Printed with every input change so an operator leg
             * reporting "button X does nothing" separates a dead transaction
             * from a wrong mapping without opening the cartlog. */
            extern u32 maple_hdr[2];
            in_last = key;
            scif_puts("IN p1=");  scif_puthex(j1);
            scif_puts(" p2=");    scif_puthex(j2);
            scif_puts(" crc=");   scif_puthex(f[0x3a]);
            scif_puts(" hdrA=");  scif_puthex(maple_hdr[0]);
            scif_puts(" hdrB=");  scif_puthex(maple_hdr[1]);
            scif_puts(" n=");     scif_puthex(maple_count & 0xffffu);
            scif_puts("\n");
        }
    }
    put(rcv, f, n);
}

/* ---- EEPROM ------------------------------------------------------------- *
 * The shim serves the baked image (the captured sub-0x03 reply: 4-byte maple
 * header + the 128-byte EEPROM, maple_jvs.cpp:1931-1940) out of a RAM copy, so
 * that a sub-0x0b write is visible to the next read. SESSION-ONLY: there is no
 * backing store on this port -- the EEPROM lives on the MIE, which does not
 * exist on a Dreamcast, and the shim has no VMU/flash writer -- so anything
 * changed in the game's own test menu holds until power-off and then reverts
 * to the baked image. Free play is baked in (image byte 9 = 0x1a, KB §Steady
 * input), so the one setting the port depends on survives a reset regardless.
 *
 * Bytes 60..127 of the baked image are RECONSTRUCTED from the Naomi dual-copy
 * layout, not captured (Task 11, scripts/extract_mie_blobs.py rebuild_sub03;
 * verified byte-identical against the EEPROM Flycast itself saved for this ROM,
 * which is a different code path but not a capture). */
static u8 ee[132];                  /* 4-byte reply header + the 128-B image */
static u8 ee_state = 0xff;          /* 0xff = not yet loaded (.data sentinel) */
static void ee_load(void) {
    u32 n = mie_sub03_len;
    if (ee_state != 0xff) return;
    ee_state = 0;
    if (n > sizeof ee) n = sizeof ee;
    xmemcpy(ee, mie_sub03, n);
}

/* BaseMIE's JVSGetId body, verbatim: two frames, 28 + 20 bytes of a 56-byte
 * literal (maple_jvs.cpp:1391-1400). Only the first 48 bytes are ever sent. */
static const char mie_id48[48] __attribute__((nonstring)) =
    "315-6149    COPYRIGHT SEGA ENTERPRISES CO,LTD.  ";

/* MIE subcommand replies (maple frame cmd 0x86). `plen` is the frame's word
 * count: plen <= 1 means the frame carries NO payload, which Flycast answers
 * with a bare JVS ack before it ever looks at a subcommand byte
 * (`if (dma_count_in == 0) { reply(MDRS_JVSReply); return; }`,
 * maple_jvs.cpp:1758-1761) -- that is exactly the boot driver's site-D frame,
 * and the reason the capture logs its subcommand as "ff" (the logger reads
 * p_data[4], which is past the frame). */
static void mie_86(u32 desc, u32 rcv, u32 plen) {
    u32 sub;
    if (plen <= 1u) { put(rcv, mie_86empty, mie_86empty_len); return; }
    sub = UB(desc + 0x0c);
    /* Diagnostic: log every CHANGE of subcommand (and of the JVS command a
     * transmit carries). The boot enumeration is a short burst of distinct
     * subs, the steady state is a single repeated sub -- so change-gating
     * prints the whole handshake once and then goes quiet, which is exactly
     * the evidence a leg needs. Same trick as Cleopatra's `in_last`. */
    if (SHIM_TRACE) {
        static u32 last_key = 0xffffffffu;
        u32 key = (sub << 8) | (sub == 0x17 || sub == 0x19 || sub == 0x21
                                ? UB(desc + 0x14) : 0u);
        if (key != last_key) {
            last_key = key;
            scif_puts("MIE sub="); scif_puthex(key >> 8);
            scif_puts(" jvs=");    scif_puthex(key & 0xffu);
            scif_puts(" rcv=");    scif_puthex(rcv);
            scif_puts(" n=");      scif_puthex(maple_count & 0xffffu);
            scif_puts("\n");
        }
    }
    switch (sub) {
    case 0x17: case 0x19: case 0x21:        /* transmit: latch the JVS command */
        /* cmd = dma_buffer_in[8] = frame byte 12 = descriptor word 5
         * (maple_jvs.cpp:1783-1788, the `dma_count_in >= 8` branch). */
        pending_jvs = UB(desc + 0x14);
        if (sub == 0x21) put(rcv, mie_sub21, mie_sub21_len);
        else             put(rcv, mie_sub17, mie_sub17_len);
        break;
    case 0x15:                              /* receive: the enumeration reply */
        switch (pending_jvs) {
        case 0xf1: put(rcv, mie_jvsf1, mie_jvsf1_len); break;
        case 0x10: put(rcv, mie_jvs10, mie_jvs10_len); break;
        case 0x11: put(rcv, mie_jvs11, mie_jvs11_len); break;
        case 0x12: put(rcv, mie_jvs12, mie_jvs12_len); break;
        case 0x13: put(rcv, mie_jvs13, mie_jvs13_len); break;
        case 0x14: put(rcv, mie_jvs14, mie_jvs14_len); break;
        default:   put(rcv, mie_jvsdflt, mie_jvsdflt_len); break;
        }
        break;
    case 0x33: mie_poll(rcv); break;        /* per-frame poll: live DC pads */
    case 0x03:                              /* EEPROM read. `address` is a byte
                                             * offset (dma_buffer_in[1] % 128,
                                             * maple_jvs.cpp:1931-1940); the
                                             * declared word count is always
                                             * 0x20 but only 128-address bytes
                                             * are written. Every read in the
                                             * capture asks for 0. */
        {   u32 a = UB(desc + 0x0d) & 0x7fu;
            ee_load();
            put(rcv, ee, 4);
            put(rcv + 4, ee + 4 + a, 128u - a);
        }
        break;
    case 0x01: put(rcv, mie_sub01, mie_sub01_len); break;  /* ready ACK: fixed
                                             * `87 00 20 01 | 02 00 00 00`,
                                             * image-independent
                                             * (maple_jvs.cpp:1972-1978) */
    case 0x13: put(rcv, mie_sub13, mie_sub13_len); break;  /* store repeat req */
    case 0x31: put(rcv, mie_sub31, mie_sub31_len); break;  /* DIP switches */
    case 0x0b:                              /* EEPROM write. Payload, in
                                             * descriptor coordinates (Flycast's
                                             * dma_buffer_in = desc + 0x0c,
                                             * maple_jvs.cpp:1899-1908):
                                             * [+0x0d] byte address, [+0x0e]
                                             * size, [+0x10..] data. Both are
                                             * clamped exactly as the emitter
                                             * clamps them (address % 128, size
                                             * to the end of the image), so a
                                             * malformed frame cannot walk off
                                             * the 128-byte copy. The ack echoes
                                             * the image's first 4 bytes
                                             * (:1924-1927). */
        {   u32 a = UB(desc + 0x0d) & 0x7fu, n = UB(desc + 0x0e), k;
            ee_load();
            if (n > 128u - a) n = 128u - a;
            for (k = 0; k < n; k++) ee[4 + a + k] = UB(desc + 0x10 + k);
            put1(rcv, 0x01200087u);         /* `87 00 20 01`: reply(…, 1 word) */
            put(rcv + 4, ee + 4, 4);
            if (SHIM_TRACE) {
                scif_puts("EE WR a="); scif_puthex(a);
                scif_puts(" n=");      scif_puthex(n);
                scif_puts(" cn=");     scif_puthex(ee[4 + 9]);  /* coin setting */
                scif_puts("\n");
            }
        }
        break;
    default:
        put(rcv, mie_86empty, mie_86empty_len);
        if (!(odd_seen & 1u)) {             /* one-shot: an unmodelled sub is a
                                             * finding, not a silent ack */
            odd_seen |= 1u;
            shim_mark(21, 0xffe0);
            scif_puts("MIE odd sub="); scif_puthex(sub); scif_puts("\n");
        }
        break;
    }
}

/* One maple frame. `desc` points at the command block, `rcv` is its (already
 * range-checked) physical recv address. Non-MIE commands are answered exactly
 * as BaseMIE::RawDma does (maple_jvs.cpp:1291-1405) -- reply word =
 * resp | sender_in << 8 | reci_in << 16 | words << 24. */
static void maple_frame(u32 desc, u32 rcv, u32 plen, u32 bus) {
    u32 fh = UW(desc + 8);
    u32 cmd = fh & 0xffu, reci = (fh >> 8) & 0xffu, sender = (fh >> 16) & 0xffu;
    u32 echo = (sender << 8) | (reci << 16);
    u32 k;
    if (bus != 0u || reci != 0x20u) {       /* nothing else on a Naomi bus: the
                                             * MIE is the only device. Flycast
                                             * answers a missing device with the
                                             * no-response marker
                                             * (maple_if.cpp:315-320). */
        put1(rcv, 0xffffffffu);
        return;
    }
    /* Replies below that hardcode the `00 20` sender/recipient pair (the 0x80
     * and 0x82 cases) copy BaseMIE::reply()'s literal `w8(code); w8(0x00);
     * w8(0x20); w8(sizew)` -- it hardcodes them too. Safe here only because of
     * the gate above: the sole recipient that reaches this switch is 0x20, the
     * MIE, and its sender is the host (0). The `echo` form is used wherever
     * Flycast itself echoes (`resp | sender << 8 | reci << 16`). */
    switch (cmd) {
    case 0x01: put1(rcv, 0x05u | echo); break;   /* DeviceRequest -> status, 0 words */
    case 0x02: put1(rcv, 0x06u | echo); break;   /* AllStatusReq */
    case 0x03: case 0x04: put1(rcv, 0x07u | echo); break;   /* Reset/Kill */
    case 0x82:                                   /* JVSGetId: two frames */
        put1(rcv, 0x07200083u);
        put(rcv + 4, (const unsigned char *)mie_id48, 28);
        put1(rcv + 32, 0x05200083u);
        put(rcv + 36, (const unsigned char *)mie_id48 + 28, 20);
        break;
    case 0x80:                                   /* JVS firmware upload (Z80) */
        if (UB(desc + 0x0d) == 0xffu) {          /* finalize marker */
            put1(rcv, 0x00200007u);              /* 07 00 20 00 DeviceReply */
            break;
        }
        {   u32 sum = 0;
            for (k = 0; k < 0x1cu; k++) sum += UB(desc + 0x0c + k);
            put1(rcv, 0x01200080u);              /* 80 00 20 01 */
            put1(rcv + 4, sum & 0xffu);          /* the additive checksum */
            put1(rcv + 8, 0x00200007u);          /* 07 00 20 00 */
        }
        break;
    case 0x86: mie_86(desc, rcv, plen); break;
    default:
        put1(rcv, 0xffffffffu);
        if (!(odd_seen & 2u)) {
            odd_seen |= 2u;
            shim_mark(22, 0xffe0);
            scif_puts("MIE odd cmd="); scif_puthex(cmd); scif_puts("\n");
        }
        break;
    }
}

/* Walk the command list at mirror SB_MDSTAR and complete the transaction.
 * Header decode and the address arithmetic are maple_DoDma's, cell for cell
 * (maple_if.cpp:211-214 header_1, :209 recv addr, :325 next block, and the
 * one-word advance every non-START pattern takes, :340-357). */
static void maple_service(void) {
    u32 addr = MMIR(0x04) & 0x1fffffe0u;
    u32 i;
    /* The list base is game-controlled. Walk it only if it points at DC RAM:
     * a stale/garbage pointer would otherwise feed uncached reads to MMIO and
     * let the reply writes below spray registers or live code. */
    if (addr - 0x0c000000u >= 0x01000000u && !(odd_seen & 8u)) {
        odd_seen |= 8u;
        shim_mark(23, 0xf800);
        scif_puts("MIE skip list="); scif_puthex(addr);
        scif_puts(" n="); scif_puthex(maple_count & 0xffffu); scif_puts("\n");
    }
    if (addr - 0x0c000000u < 0x01000000u)
        for (i = 0; i < 64u; i++) {          /* cap: a list with no terminator
                                              * must not walk RAM forever */
            u32 h1 = UW(addr);
            u32 plen = (h1 & 0xffu) + 1u;
            if (((h1 >> 8) & 7u) == 0u) {    /* pattern 0 = START = a transfer */
                u32 rcv = UW(addr + 4) & 0x1fffffe0u;
                if (rcv - 0x0c000000u < 0x01000000u)
                    maple_frame(addr, rcv, plen, (h1 >> 16) & 3u);
                else if (!(odd_seen & 4u)) {  /* a reply we could not deliver is
                                               * a silent stall -- say so once */
                    odd_seen |= 4u;
                    shim_mark(23, 0xf800);
                    scif_puts("MIE skip rcv="); scif_puthex(rcv);
                    scif_puts(" n="); scif_puthex(maple_count & 0xffffu);
                    scif_puts("\n");
                }
                addr += (2u + plen) * 4u;
            } else {
                addr += 4u;                  /* RESET/NOP/occupy: no transfer */
            }
            if (h1 >> 31) break;             /* last-transfer bit */
        }
    maple_count++;
    MMIR(0x18) = 0;                          /* SB_MDST = 0: the poll's exit */
}

/* MAPLE-BOOT-A..E (src/mtramp.S). The detour window swallowed `SB_MDEN = 1`,
 * the kick, the poll, and -- at A/C/D/E -- the trailing `SB_MDEN = 0`. All
 * four are mirror stores, so the uniform contract the KB pins (:1282-1286) is
 * simply: on return mirror[0x14] = 0 and mirror[0x18] = 0. Site B's window
 * ends before its own `SB_MDEN = 0`, so B's resume instruction writes the
 * same 0 again; harmless. */
/* MAPLE-KICK-HOOK (KB :1077-1093). The steady engine FUN_8c02532a reaches its
 * registers through base->[0x10f4], which MAPLE-BASE (entry 1) repoints, so
 * its kick lands in the mirror and its `SB_MDST reads 0` guard at 0x8c02536e
 * would return -1 forever. The KB's hook is a pool repoint, not a thunk: the
 * `jsr @r3` at 0x8c025444 loads r3 from [0x8c0254c0] (one loader in the whole
 * image), so pointing that word here turns the existing call into the hook,
 * with zero instructions rewritten. We are entered AFTER the kick store (it is
 * that jsr's delay slot), so the mirror is fully programmed.
 *
 * Contract, all three parts: (a) walk the list and synthesize each reply,
 * (b) clear mirror SB_MDST, (c) return what FUN_8c02a17e returned -- the value
 * is stored to [0x8c19268c] two instructions later. That routine is
 * `d244 e0ff 6322 000b 3038` = `return -1 - *(u32 *)0xffd8000c`, a read of
 * SH-4 TMU TCNT0 (../flycast4naomi2dreamcast/core/hw/sh4/sh4_mmr.h:324-325),
 * which exists identically on Dreamcast -- so recompute it rather than
 * tail-calling into the game. SB_MDEN is deliberately untouched here: unlike
 * the five boot windows, this site's instructions never wrote it.
 *
 * WHY IN TASK 11 (deviation from the task split, evidence in the report):
 * senkosp's JVS I/O-board enumeration -- the thing the boot gate
 * `if (*(u32 *)0x8c1c013c == 0) fatal("I/O BD IS NOT CONNECTED...")` at
 * 0x8c0acf44 tests -- is transacted by THIS engine, not by the boot driver
 * (captures/phase4/pc2.log: every sub-0x17/0x15 enumeration frame is
 * pc=8c025448; the boot driver only uploads the MIE's Z80 firmware). Leg
 * attract1 confirmed it live: 345/345 boot transactions serviced, the error
 * path never taken, and the game then stopped dead at the first steady kick. */
#if SHIM_TEXHUD
/* HW round 3: texture-error autopsy (docs/kb/phase5-hardware.md §Hardware
 * rounds Round 2). Round-2 photos show whole asset classes missing on real
 * HW (stage bg, opponent, meter fills) + flicker; the game's own KAMUI2
 * error cell 0x8c1a20a8 (§Texture-error handler: 6 = arena-alloc fail OR
 * bad header, 7 = surface/descriptor table full, 8 = data extent mismatch,
 * 1 = zero-entry TXTR/no buffer) says WHICH failure family is live. Painted
 * per steady kick (the legacy block's round-13 lesson: sub-frame-rate paints
 * are overdrawn and unreadable). All reads passive; P1 reads of game-written
 * RAM, same CPU. Rows x=20:
 *   y240 live error cell   y254 nonzero transitions
 *   y268 count code 6      y282 count code 7
 *   y296 cnt8<<16|cnt1     y310 gd_diag[0] (GD idle-gap recoveries)
 *   y324 arena-init VRAM size passed (config 0x8c170eb8+4: 0x800000 = DC
 *        8 MB arm, 0x1000000 = Naomi 16 MB arm)  y338 chosen size (+0x18)
 * Slot 26: green = error cell clean since boot; red sticky = fired.
 * Painted via shim_hex (SHIM_HUD-gated): operator request 2026-08-30 --
 * on-screen digits distract during play and the serial mirror below
 * carries every value; SHIM_HUD now defaults 0 (shim_iface.h), which
 * also removes the uncached-VRAM paint cost util.c:25-32 documents.
 * shim_die's fatal screens stay verbose unconditionally. */
void shim_hex(u32 x, u32 y, u32 val);                   /* util.c, HUD-gated */
static void texhud_tick(void) {
    static u32 tex_prev = 0, tex_trans = 0, tex_c6 = 0, tex_c7 = 0,
               tex_c8 = 0, tex_c1 = 0, tex_ever = 0;
    extern unsigned int gd_diag[8];
    u32 cur = *(volatile u32 *)0x8c1a20a8;
    u32 fired = (cur != 0 && tex_prev == 0);
    if (fired) {
        tex_trans++; tex_ever = 1;
        if (cur == 6) tex_c6++;
        else if (cur == 7) tex_c7++;
        else if (cur == 8) tex_c8++;
        else if (cur == 1) tex_c1++;
    }
    tex_prev = cur;
    /* SB_ISTERR (0xa05f6908): PVR error-interrupt latches. Round-4
     * hypothesis rows: bit 2 = TA ISP/TSP parameter overflow, bit 3 = TA
     * object list pointer overflow (holly_intc.h:52-53) -- real TA drops
     * geometry when these fire; Flycast does not model the limits, which
     * would explain hardware-only missing/flickering objects with a clean
     * KAMUI2 error cell (round 3b). ie_acc ORs every per-kick sample = the
     * all-time sticky mask (kept meaningful even now that the IEE block
     * below write-1-clears the live register after logging each edge). */
    static u32 ie_acc = 0;
    u32 isterr = *(volatile u32 *)0xa05f6908;
    ie_acc |= isterr;
    /* IEE edge logger (soak build, operator request 2026-08-30: "isp errors
     * from time to time -- catch the reason"). The latch is sticky and the
     * game never clears it (hw-round8: iea constant from sample 11 on), so a
     * passive read only ever shows the FIRST occurrence. Instead: whenever
     * any error bit is latched at a kick, log it with the TA fill state --
     * TA_ITP_CURRENT vs TA_ISP_LIMIT (pvr_regs.h:480-483; a genuine
     * parameter-space overflow, bit 2, lands at/over the limit; bit 0 "ISP
     * out of cache" is PER-TILE complexity, holly_intc.h:50-53, and shows
     * itp well under lim), TA_NEXT_OPB vs TA_OL_LIMIT (OPB pool draw), and
     * the carve word (0x5a4e0 = inside the stale library-carve window that
     * gcarve_tick closes) -- then WRITE-1-CLEAR exactly the observed bits
     * (holly_intc.cpp:144-146: SB_ISTERR &= ~data) so the NEXT occurrence
     * latches fresh and recurrence becomes countable. Registers are sampled
     * at the maple kick, up to ~1 frame after the actual latch -- conditions,
     * not a point-in-time capture. First 16 occurrences get a detail line;
     * the count keeps flowing in the TEXHUD summary (iee=). Diagnostic
     * builds only (whole fn is SHIM_TEXHUD; release stays hands-off). */
    /* hw-soak1 upgrade: the 16-line cap was exhausted inside the first bit-0
     * burst (33,033 bit-0 latches/session -- saturated in attract-demo and
     * credits scenes, itp at 22% of lim, characterized-benign), which
     * swallowed the ONE interesting event: a bit-2 TA param overflow (iea
     * 1->5, ~24 min in). So: always detail-print a mask containing a bit
     * never detailed before, and count bit 2 separately (ie2= in the
     * summary) -- the bit-2 rate vs the razor-thin ISP limit is the open
     * question (docs/kb/phase5-hardware.md SS Round 7 soak verdict). */
    static u32 ie_edges = 0, ie_bit2 = 0, ie_detailed = 0;
    if (isterr != 0) {
        ie_edges++;
        if (isterr & 4u) ie_bit2++;
        if (ie_edges <= 16u || (isterr & ~ie_detailed)) {
            ie_detailed |= isterr;
            scif_puts("IEE cnt=");  scif_puthex(ie_edges);
            scif_puts(" ie=");      scif_puthex(isterr);
            scif_puts(" itp=");     scif_puthex(*(volatile u32 *)0xa05f8138);
            scif_puts(" lim=");     scif_puthex(*(volatile u32 *)0xa05f8130);
            scif_puts(" opb=");     scif_puthex(*(volatile u32 *)0xa05f8134);
            scif_puts(" oll=");     scif_puthex(*(volatile u32 *)0xa05f812c);
            scif_puts(" carve=");   scif_puthex(*(volatile u32 *)0x8c19ed00);
            scif_puts(" ms=");      scif_puthex(maple_count & 0xffffffu);
            scif_puts("\n");
        }
        *(volatile u32 *)0xa05f6908 = isterr;   /* W1C the observed bits only */
    }
    /* Serial mirror (SERIAL=1 builds; scif_putc is a no-op otherwise): one
     * TEXERR line per 0->nonzero transition (event-exact), one TEXHUD
     * summary every 512 kicks (~8.5 s) so a quiet log still proves liveness. */
    if (fired || (maple_count & 0x1ffu) == 0u) {
        scif_puts(fired ? "TEXERR cur=" : "TEXHUD cur="); scif_puthex(cur);
        scif_puts(" tr=");  scif_puthex(tex_trans);
        scif_puts(" c6=");  scif_puthex(tex_c6);
        scif_puts(" c7=");  scif_puthex(tex_c7);
        scif_puts(" c8=");  scif_puthex(tex_c8);
        scif_puts(" c1=");  scif_puthex(tex_c1);
        scif_puts(" gd=");  scif_puthex(gd_diag[0]);
        scif_puts(" a4=");  scif_puthex(*(volatile u32 *)0x8c170ebc);
        scif_puts(" a18="); scif_puthex(*(volatile u32 *)0x8c170ed0);
        scif_puts(" ie=");  scif_puthex(isterr);
        scif_puts(" iea="); scif_puthex(ie_acc);
        scif_puts(" iee="); scif_puthex(ie_edges);
        scif_puts(" ie2="); scif_puthex(ie_bit2);
        scif_puts("\n");
    }
    shim_hex(20, 352, ie_acc);
    shim_hex(20, 240, cur);
    shim_hex(20, 254, tex_trans);
    shim_hex(20, 268, tex_c6);
    shim_hex(20, 282, tex_c7);
    shim_hex(20, 296, (tex_c8 << 16) | (tex_c1 & 0xffffu));
    shim_hex(20, 310, gd_diag[0]);
    shim_hex(20, 324, *(volatile u32 *)0x8c170ebc);
    shim_hex(20, 338, *(volatile u32 *)0x8c170ed0);
    shim_mark(26, tex_ever ? 0xf800 : 0x07e0);
}
#else
#define texhud_tick() ((void)0)
#endif /* SHIM_TEXHUD */

/* G-CARVE per-frame re-stomp (r8b). The init-thunk stomp (shim_g_carve)
 * verifiably lands and is then reverted to the library carve by a writer no
 * static path explains (r8a leg: all six words back to 0x5a4e0-family by
 * render 1500; those six are the ONLY RAM cells that ever hold carve values
 * -- whole-dump search). So re-assert per maple kick (~per frame), guarded
 * on the exact library value so it can never fire pre-init, in test mode,
 * or in any unexpected state, and count reverts: rv=1 means a one-shot
 * post-init rewriter (converged); a growing rv means a per-frame fight
 * (would show as register flapping in RNDREG). */
static unsigned int gcarve_reverts;
static void gcarve_tick(void) {
    if (*(volatile u32 *)0x8c19ed00 != 0x0005a4e0u)
        return;                          /* not the library-carve state */
    *(volatile u32 *)0x8c19ed00 = 0x000711e0u;  /* dev+0x844 ispl */
    *(volatile u32 *)0x8c19ed04 = 0x000712e0u;  /* dev+0x848 oll  */
    *(volatile u32 *)0x8c1a18bc = 0x000711e0u;  /* desc bank A ispl */
    *(volatile u32 *)0x8c1a18c0 = 0x000712e0u;  /* desc bank A oll  */
    *(volatile u32 *)0x8c1a1948 = 0x004711e0u;  /* desc bank B ispl */
    *(volatile u32 *)0x8c1a194c = 0x004712e0u;  /* desc bank B oll  */
    gcarve_reverts++;
    if (gcarve_reverts <= 4u) {
        scif_puts("GCARVE rv="); scif_puthex(gcarve_reverts); scif_puts("\n");
    }
}

/* E-PREFREE (r8, docs/kb/phase5-hardware.md §Round 6 prep + §2 free path).
 * The mode-select scene loads MODESEL.PAK at task entry BEFORE the match
 * task's teardown tail has freed the match textures -- the +362,496
 * transition spike that is the T1 binding term. The patch table repoints the
 * scene's loader pool word (dat 0x13930c -> by-name loader FUN_8c0b5be8)
 * here: free the match scene's VRAM texture list first, then run the load.
 * Safe by construction: FUN_8c0b5cf4 skips null slots and NULLS each slot it
 * frees (Decomp), so from-boot entries (slot still 0) are no-ops and the
 * real teardown's later 0x19-mask call finds bit-0 already null. Mask 1
 * (textures only): the teardown's unguarded inline heap-frees read the +4/+8
 * slots, which mask 1 never touches. Args passed through untouched (by-name
 * loader takes (name[, flags]) in r4/r5; r6/r7 forwarded for safety). */
int shim_e_prefree(int a, int b, int c, int d);
int shim_e_prefree(int a, int b, int c, int d) {
    ((void (*)(unsigned int *, unsigned int))0x8c0b5cf4)
        ((unsigned int *)0x8c1cfb50, 1u);
    scif_puts("EPREFREE\n");
    return ((int (*)(int, int, int, int))0x8c0b5be8)(a, b, c, d);
}

int shim_maple_service(void);
int shim_maple_service(void) {
    maple_service();
    gcarve_tick();
    texhud_tick();
    if (SHIM_TRACE && (maple_count & 0x1ffu) == 0u) {   /* ~8 s heartbeat */
        scif_puts("MS n="); scif_puthex(maple_count & 0xffffu); scif_puts("\n");
    }
    return -1 - (int)*(volatile u32 *)0xffd8000c;      /* TMU TCNT0 */
}

void shim_maple_boot(void);
void shim_maple_boot(void) {
    if (maple_count == 0x10000u) shim_mark(1, 0x07e0);   /* slot1 green: first */
    maple_service();
    MMIR(0x14) = 0;                          /* SB_MDEN = 0 (replayed) */
    if (SHIM_TRACE) {
        scif_puts("MB n=");   scif_puthex(maple_count & 0xffffu);
        scif_puts(" star=");  scif_puthex(MMIR(0x04));
        scif_puts(" h1=");    scif_puthex(UW(MMIR(0x04) & 0x1fffffe0u));
        scif_puts("\n");
    }
}

#if 0  /* re-enabled per-task: see plan Tasks 10-12 */
typedef unsigned short u16;
void shim_die(u32, u32, u32);
void *xmemcpy(void *, const void *, u32);
void shim_mark(u32 slot, unsigned short color);   /* util.c: real-HW breadcrumb HUD */
void shim_hex(u32 x, u32 y, u32 val);             /* util.c: on-screen hex printer */
int  shim_cable_is_vga(void);                     /* util.c: DC cable sense (PDTRA) */
static void mie_probe_reply(u32 cmd, u32 fh, u32 rcv, u32 frame);  /* MIE init ladder */
/* shim_cart_service lives in src/cart.c (Task 10) */

/* Per-frame/per-event serial trace (LISTDIAG, IN-raw, CART-off). Default OFF:
 * real-HW SCIF spin cost (see round-18 note at the LISTDIAG site). */
#ifndef SHIM_TRACE
#define SHIM_TRACE 0
#endif

/* HUD paint-once bitmask. .data (bit7 sentinel non-zero) per house style. */
static u8 hud_marks = 0x80;
#define HUD_ONCE(bit, slot, color) \
    do { if (!(hud_marks & (bit))) { hud_marks |= (bit); shim_mark(slot, color); } } while (0)

/* Fine-grained forensics for the real-HW hang window (EEPROM write-back ->
 * JVS enum). .data non-zero inits per house style; low 16 bits = counters. */
static u32 ee_wr_count = 0x10000;    /* sub-0x0b service count */
static u32 steady_beat = 0x10000;    /* shim_maple_steady call count (heartbeat) */
static u32 trig_seen   = 0x10000;    /* mirror-DMA triggers in current beat window */
static u32 rc_ok_seen  = 0x10000;    /* engine rc==0 (not busy) in current window */
static u32 reply_ticks = 0x10000;    /* total maple_reply invocations */

unsigned short maple_getcond(unsigned int port);   /* DC Maple GetCondition: port A=0, B=1 */
unsigned short dc_to_jvs(unsigned short);
unsigned char  jvs_checksum(const unsigned char *);
extern const unsigned char jvs_hasdata[];               /* src/jvs.c */
void scif_puts(const char *); void scif_puthex(unsigned int); void scif_putc(char);  /* src/scif.c */

/* MIE reply templates + free-play EEPROM, embedded at build (Makefile xxd rules;
 * gitignored source blobs). Verbatim ACKs replayed as captured (§input-ABI 4a). */
extern const unsigned char eeprom_img[];
extern const unsigned char mie_sub01[]; extern const u32 mie_sub01_len;
extern const unsigned char mie_sub13[]; extern const u32 mie_sub13_len;
extern const unsigned char mie_sub17[]; extern const u32 mie_sub17_len;
extern const unsigned char mie_sub27[]; extern const u32 mie_sub27_len;
extern const unsigned char mie_sub31[]; extern const u32 mie_sub31_len;
extern const unsigned char mie_subff[]; extern const u32 mie_subff_len;

/* JVS I/O-board enumeration replies (scripts/extract_jvs_replies.py). Keyed on
 * the JVS command the game transmits; the matching one is replayed on the
 * following receive so the board passes enumeration (M3). */
extern const unsigned char mie_jvsf1[]; extern const u32 mie_jvsf1_len;  /* F1 set-addr */
extern const unsigned char mie_jvs10[]; extern const u32 mie_jvs10_len;  /* 10 board ID */
extern const unsigned char mie_jvs11[]; extern const u32 mie_jvs11_len;  /* 11 cmd rev  */
extern const unsigned char mie_jvs12[]; extern const u32 mie_jvs12_len;  /* 12 JVS rev  */
extern const unsigned char mie_jvs13[]; extern const u32 mie_jvs13_len;  /* 13 comm rev */
extern const unsigned char mie_jvs14[]; extern const u32 mie_jvs14_len;  /* 14 features */

/* Last JVS command transmitted (sub 0x17/0x19/0x21) -> selects the enumeration
 * reply the next receive (sub 0x15) returns. 0xff = "not an enumeration command"
 * (digital read). Initialised non-zero so it lands in .data (the loader copies
 * .data but does NOT zero .bss). */
static u8 pending_jvs = 0xff;

/* Task 15c: last JVS command the CONFIG-TIME enumeration transmitted through
 * FUN_8c081562 -> selects the reply FUN_8c081626 returns. .data (non-zero). */
static u8 pending_cfg = 0xf1;
static u8 cfg_seen    = 0;               /* one-shot SCIF log bitmap of served cmds */

/* Task 15 instrumentation state. ALL forced non-zero so they land in .data
 * (the loader copies .data but does NOT zero .bss -- see pending_jvs above; a
 * .bss static would boot with garbage and break the rate-limit / one-shot). */
static unsigned int in_last = 0xffffffffu;   /* last (raw<<16 | jvs); sentinel forces first log */
static unsigned int in_hb   = 1;             /* sub-0x33/0x15 poll heartbeat counter */
static u8 ee_logged = 1;                     /* 1 = still need to log the sub-0x03 EEPROM deliver */
static u8 wr_left   = 32;                     /* remaining sub-0x0b (EEPROM write / re-init) log budget */

#define SB_MDST (*(volatile u32 *)0xa05f6c18)
#define GW(a)   (*(volatile u32 *)((a) | 0x80000000u))  /* cached word: game control state */
#define GB(a)   (*(volatile u8  *)((a) | 0x80000000u))  /* cached byte */
#define UW(a)   (*(volatile u32 *)((a) | 0xa0000000u))  /* uncached word: DMA descriptor view */
#define UB(a)   (*(volatile u8  *)((a) | 0xa0000000u))  /* uncached byte */

/* Live DC GetCondition -> JVS digital-read has-data frame at recvaddr.
 * Task 15: rate-limited SCIF trace ("IN raw=<getcond> jvs=<jvsword> sub=<sub>")
 * on CHANGE or every 256th poll, so a user press is visible on serial without
 * flooding the ~60Hz poll. raw=0000ffff idle = controller all-released or no pad;
 * a Start press flips raw (bit3 low) and yields jvs=00008000. */
/* Pad cache (HW rounds 15-16: 2P mode "very slow" on real HW only). The game
 * requests input PER PLAYER; each live request = a real Maple bus busy-wait
 * (instant in Flycast, ~0.5-1 ms on the wire; a pad re-polled back-to-back
 * often misses its reply, adding retry+timeout). Round-15 keyed the cache on
 * steady_beat -- insufficient (2P ticks the engine per player, invalidating
 * the cache mid-frame). Round-16: key on TCNT0 (BIOS-left-running, ~12.5 MHz
 * down-counter, the same timer the game uses) with an ~8 ms window -- immune
 * to how often the engine ticks. .data nonzero inits. */
#define TCNT0 (*(volatile u32 *)0xffd8000c)
#define TCR0  (*(volatile unsigned short *)0xffd80010)
static u32 in_tcnt = 1;
static u32 raw_cache_a = 0xffff, raw_cache_b = 0xffff;
u32 getcond_total = 1;                       /* rate probe, ++ in cache refresh */
static u32 gc_rate = 1, cc_rate = 1;         /* last 1s-window rates (heartbeat-updated) */
/* Round-17 fix: round-16 hardcoded "TCNT0 = 12.5 MHz" -- wrong if the BIOS
 * left a bigger prescaler (rate meter showed refreshes ~7/s instead of ~60/s
 * = the "clunky controls"). Compute the ~8 ms window from TCR0.TPSC. */
static u32 pad_thresh = 1;                   /* 1 = not yet computed (.data) */

/* ---- post-handoff init timeline (SHIM_LOADSTAT, part A) ------------------
 * The ~3 s black screen BEFORE cart streaming: pre-frame-loop game CPU, or a
 * hooked init stage (config JVS enum / EEPROM / video)? shim_maple_steady is
 * vblank-driven and runs from early init, so it is our clock: la_ticks =
 * reload-safe elapsed (per-frame TCNT0 deltas, clamped) from the FIRST maple
 * tick; la_beat = frame count (reload-immune cross-check). ls_stampA latches
 * the clock at each milestone's first fire -> the timeline, painted (x=340) next
 * to the cart counters (x=20). Time BEFORE the first maple tick is the stopwatch
 * gap before this clock appears on-screen. Reuses TCNT0/TCR0 (defined above). */
#if SHIM_LOADSTAT
void hex_paint_c(u32, u32, u32, unsigned short, unsigned short);   /* util.c */
#define LS_A_FG 0x0000                                             /* black digits ... */
#define LS_A_BG 0xffff                                             /* ... on a white box */
static u32 la_ticks = 0, la_last = 0, la_beat = 0, la_sh = 0xff;   /* la_sh: .data sentinel */
static u32 la_stamp[5];        /* first-fire ticks: 0=maple 1=cfg 2=ee 3=vid 4=cart */
static u8  la_seen = 0;
static u32 mie_count = 0;       /* maple_reply calls = MIE transactions serviced (ladder probe) */
static u32 la_mie[5];           /* mie_count latched at each milestone (parallel to la_stamp) */
static u32 la2ms(u32 t) { return (t << la_sh) / 50000u; }   /* la_sh set on 1st tick */
void ls_stampA(u32 slot);
void ls_stampA(u32 slot) {
    if (la_sh != 0xff && !(la_seen & (1u << slot))) {
        la_seen |= 1u << slot; la_stamp[slot] = la_ticks; la_mie[slot] = mie_count;
    }
}
static void la_tick(void) {                 /* once per maple frame */
    if (la_sh == 0xff) {                     /* first tick: latch prescaler + t0 */
        static const u32 sh[8] = {2, 4, 6, 8, 10, 10, 10, 10};
        la_sh = sh[TCR0 & 7u]; la_last = TCNT0; la_seen |= 1u;     /* slot0 = 0 ms */
    } else {
        u32 now = TCNT0, dt = la_last - now; la_last = now;        /* down-counter */
        if (dt < (50000000u >> la_sh)) la_ticks += dt;            /* clamp reload wrap */
    }
    la_beat++;
    hex_paint_c(340, 152, la2ms(la_ticks),    LS_A_FG, LS_A_BG);  /* live clock, ms */
    hex_paint_c(340, 166, la_beat,            LS_A_FG, LS_A_BG);  /* frames (reload-immune) */
    hex_paint_c(340, 180, la2ms(la_stamp[1]), LS_A_FG, LS_A_BG);  /* cfg JVS-enum first, ms */
    hex_paint_c(340, 194, la2ms(la_stamp[2]), LS_A_FG, LS_A_BG);  /* EEPROM read first, ms */
    hex_paint_c(340, 208, la2ms(la_stamp[3]), LS_A_FG, LS_A_BG);  /* video init first, ms */
    hex_paint_c(340, 222, la2ms(la_stamp[4]), LS_A_FG, LS_A_BG);  /* first cart stream, ms */
    hex_paint_c(470, 152, mie_count,          LS_A_FG, LS_A_BG);  /* live MIE txn count */
    hex_paint_c(470, 166, la_mie[2],          LS_A_FG, LS_A_BG);  /* MIE count @ EEPROM read */
    hex_paint_c(470, 180, la_mie[1],          LS_A_FG, LS_A_BG);  /* MIE count @ JVS enum */
}
#else
#define ls_stampA(x) ((void)0)
#define la_tick()    ((void)0)
#endif

static void jvs_digital(u32 sub, void *rx) {
    HUD_ONCE(0x08, 3, 0xffe0);                           /* slot3 yellow: input poll live */
    if (pad_thresh == 1) {
        static const u32 shifts[8] = {2, 4, 6, 8, 10, 10, 10, 10}; /* TPSC: /4 /16 /64 /256 /1024 */
        pad_thresh = (50000000u >> shifts[TCR0 & 7u]) / 125u;      /* Pck 50 MHz; ticks per 8 ms */
    }
    u32 now = TCNT0;
    if (in_tcnt - now > pad_thresh) {        /* down-counter: elapsed = last - now */
        in_tcnt = now;
        getcond_total += 2;
        raw_cache_a = maple_getcond(0);                  /* port A -> P1 */
        raw_cache_b = maple_getcond(1);                  /* port B -> P2 (0xffff=no pad -> idle) */
    }
    unsigned short raw  = (unsigned short)raw_cache_a;
    unsigned short j    = dc_to_jvs(raw);
    unsigned short raw2 = (unsigned short)raw_cache_b;
    unsigned short j2   = dc_to_jvs(raw2);
    unsigned int   key  = ((unsigned int)raw << 16) | raw2;   /* log on either pad's change */
    /* HW input diagnostics, repainted EVERY poll (the game overdraws each
     * frame, so change-gated paints flashed unreadably; per-poll shim_hex is
     * video-safe -- the y26-54 rows already do it in attract-green builds).
     * y96: [P1raw|P2raw] | [port-A reply header]. Idle FFFFFFFF; a Start
     * press must flip a bit on the left; hdr low byte 8 = healthy DATATRF,
     * 0 = the DMA never wrote the buffer (bus/transaction dead). */
    {
        extern u32 maple_hdr[2];
        shim_hex(20, 96, key);
        shim_hex(120, 96, maple_hdr[0]);
        /* y110 rate meters: values refresh 1/s (heartbeat), painted per poll
         * so they stay readable over the game's per-frame redraw. */
        shim_hex(20, 110, gc_rate);
        shim_hex(120, 110, cc_rate);
    }
    if (SHIM_TRACE && (key != in_last || (++in_hb & 0xffu) == 0u)) {
        in_last = key;
        scif_puts("IN raw=");   scif_puthex(raw);
        scif_puts(" jvs=");     scif_puthex(j);
        scif_puts(" p2raw=");   scif_puthex(raw2);
        scif_puts(" p2jvs=");   scif_puthex(j2);
        scif_puts(" sub=");     scif_puthex(sub);
        scif_puts("\n");
    }
    u8 f[64];
    xmemcpy(f, jvs_hasdata, 64);
    f[0x20] = (u8)(j >> 8);                 /* BTN_OFF: P1 word big-endian (hi) */
    f[0x21] = (u8)(j & 0xff);              /*          (lo; this game: 0)      */
    f[0x22] = (u8)(j2 >> 8);               /* P2 word big-endian (hi) -- emitter maple_jvs.cpp:2237/2241 */
    f[0x23] = (u8)(j2 & 0xff);            /*          (lo)                    */
    f[0x3a] = jvs_checksum(f);              /* recompute JVS checksum @0x3a (now covers P2 bytes) */
    xmemcpy(rx, f, 64);
}

/* Shared reply synthesizer for both MIE sites. recvaddr is a game main-RAM phys
 * address; the reply is written UNCACHED (P2) because it stands in for a Maple
 * DMA-to-RAM write -- the game's reply reader treats recvaddr as a DMA buffer
 * (reads it uncached / post-invalidate), so an uncached store is what it sees. */
static void maple_reply(u32 sub, u32 recvaddr, u32 frame) {
#if SHIM_LOADSTAT
    mie_count++;                                         /* count MIE transactions (ladder probe) */
#endif
    HUD_ONCE(0x02, 1, 0x07e0);                           /* slot1 green: first MIE service */
    if (((++reply_ticks) & 15u) == 0)                    /* slot9: replies still flowing? */
        shim_mark(9, (reply_ticks & 16u) ? 0xffff : 0x39e7);
    void *rx = (void *)P2ADDR(recvaddr);
    switch (sub) {
    case 0x33:                              /* steady per-frame poll: always live */
        jvs_digital(0x33, rx);
        break;
    case 0x15:                              /* boot receive: enumeration reply or live */
        switch (pending_jvs) {              /* keyed on the last transmitted JVS cmd */
        case 0xf1: xmemcpy(rx, mie_jvsf1, mie_jvsf1_len); break;
        case 0x10: xmemcpy(rx, mie_jvs10, mie_jvs10_len); break;
        case 0x11: xmemcpy(rx, mie_jvs11, mie_jvs11_len); break;
        case 0x12: xmemcpy(rx, mie_jvs12, mie_jvs12_len); break;
        case 0x13: xmemcpy(rx, mie_jvs13, mie_jvs13_len); break;
        case 0x14: xmemcpy(rx, mie_jvs14, mie_jvs14_len); break;
        default:   jvs_digital(0x15, rx);   break;  /* digital read (0x20/0x21/0x22/none) */
        }
        break;
    case 0x03: {                            /* EEPROM read: 1-word hdr + 128 B @ EE_OFF=4 */
        u8 hdr[4] = { 0x87, 0x00, 0x20, 0x20 };   /* 0x20 words */
        xmemcpy(rx, hdr, 4);
        xmemcpy((u8 *)rx + 4, eeprom_img, 128);
        if (ee_logged) {                    /* Task 15: confirm free-play EEPROM is delivered (once) */
            ee_logged = 0;
            scif_puts("EE deliver rcv="); scif_puthex(recvaddr);
            scif_puts(" coin09=");   scif_puthex(eeprom_img[9]);   /* 0x1a = FREE PLAY */
            scif_puts(" coin27=");   scif_puthex(eeprom_img[27]);
            scif_puts("\n");
        }
        break;
    }
    case 0x01: xmemcpy(rx, mie_sub01, mie_sub01_len); break;   /* EEPROM ready ACK */
    case 0x13: xmemcpy(rx, mie_sub13, mie_sub13_len); break;   /* store repeat req ACK */
    case 0x17: case 0x19: case 0x21:
               xmemcpy(rx, mie_sub17, mie_sub17_len); break;   /* transmit ACK
                          (0x19 = transmit-with-repeat: never seen in captures,
                          but both latch sites treat 0x17/0x19/0x21 as the
                          transmit trio and Flycast's reply shape is identical
                          to 0x21 -- final review: ACK it, don't shim_die) */
    case 0x27: xmemcpy(rx, mie_sub27, mie_sub27_len); break;   /* kick-scan ACK */
    case 0x31:                              /* DIP switches. Reply byte 10 = Flycast
                                               in(5) (maple_jvs.cpp:1959), bit0 =
                                               Naomi SW1:1 monitor freq: 1 = 31 kHz
                                               VGA, 0 = 15 kHz NTSCi (MAME
                                               naomi.cpp:1486). Header 0x42a = 0 ->
                                               game supports both; key the DIP off
                                               the real DC cable so composite/RGB
                                               TVs get the game's native 15 kHz
                                               mode (the canned capture hardwired
                                               31 kHz -> out-of-sync on AV out). */
        xmemcpy(rx, mie_sub31, mie_sub31_len);
        if (!shim_cable_is_vga())
            ((u8 *)rx)[10] &= 0xfeu;
        break;
    case 0xff: xmemcpy(rx, mie_subff, mie_subff_len); break;   /* broadcast/reset ACK */
    case 0x0b: {                            /* EEPROM write: MIE sub-0x0b. Payload (Flycast
                                               maple_jvs.cpp:1888-1896, dma_buffer_in=frame+0xc):
                                               [+0x0d]=byte addr, [+0x0e]=size, [+0x10..]=data. */
        u32 n = (++ee_wr_count) & 0xffffu;  /* slot6: EE-write progress 1=blue 8=yellow 16=white */
        if (n == 1)       shim_mark(6, 0x001f);
        else if (n == 8)  shim_mark(6, 0xffe0);
        else if (n == 16) shim_mark(6, 0xffff);
        u32 ee_addr = UB(frame + 0x0d);      /* frame = descriptor block: DMA-source memory,
                                                uncached view (see the walk below) */
        u32 ee_size = UB(frame + 0x0e);
        u8 ack[8] = { 0x87, 0x00, 0x20, 0x01, 0x0c, 0x00, 0x8e, 0x00 };
        xmemcpy(rx, ack, 8);
        if (SHIM_TRACE && wr_left) {        /* Task 16 decode; SHIM_TRACE-gated per the
                                               round-18 serial rule (final review: this
                                               per-event block had escaped the gate) */
            wr_left--;
            scif_puts("EE WR a="); scif_puthex(ee_addr);
            scif_puts(" n=");     scif_puthex(ee_size);
            scif_puts(" d=");
            for (u32 k = 0; k < ee_size && k < 32u; k++) {
                u8 b = UB(frame + 0x10 + k);
                scif_putc("0123456789abcdef"[b >> 4]);
                scif_putc("0123456789abcdef"[b & 15]);
            }
            scif_puts("\n");
        }
        break;
    }
    default:   shim_die(3, sub, recvaddr);
    }
}

/* ponytail: currently UNHOOKED (Task 14d). pool[0x8c027618] feeds the generic
 * dispatcher FUN_8c027584 (160+ callers), not an MIE-only site, so hooking it made
 * the shim shim_die on the first post-check NON-MIE frame (cmd 0xf6, recv 0xc8000000).
 * Kept as the documented boot-MIE ABI + re-hook target once a MIE-only call site is
 * isolated. See scripts/build_patch_table.py §Task 14d + phase4-conversion.md §Task 14d.
 *
 * Boot MIE builder (0x8c0315ce, reached via fn-ptr pool[0x8c027618]). Sub +
 * recvaddr are read from the command block *0x8c0e6400 (word3 low byte = sub,
 * word1 = recvaddr). Completion: leave the Maple DMA observably done, i.e.
 * SB_MDST reads 0. [KB §input-ABI site A -- boot completion is M4-gated.]
 *
 * arg0 = r4 = the transmit payload block the dispatcher passes to the builder
 * (FUN_8c027584 @0x8c0275ee, jsr @r3 with r4 = pool 0x8c0e62c8 / 0x8c0a27f4).
 * On a transmit (sub 0x17/0x19/0x21) the JVS command byte lives at arg0+4
 * (descriptor word5 byte0 -> maple frame byte 12 -> Flycast dma_buffer_in[8],
 * maple_jvs.cpp:1780); we latch it so the following receive (sub 0x15) returns
 * the matching enumeration reply. sub 0x27 (transmit-with-repeat) is only ever
 * the digital-read setup -> latch "not enumeration". */
void shim_maple_boot(u32 arg0) {
    u32 cmdblk = GW(0x8c0e6400);
    u32 sub    = GB(cmdblk + 0x0c);
    u32 recv   = GW(cmdblk + 0x04);
    switch (sub) {
    case 0x17: case 0x19: case 0x21: pending_jvs = GB(arg0 + 4); break;
    case 0x27:                       pending_jvs = 0xff;         break;
    }
    maple_reply(sub, recv, cmdblk);
    SB_MDST = 0;
}

/* Steady per-frame MIE builder (FUN_8c03c2c6, reached via pool[0x8c02ed6c]).
 * Always sub 0x33 (real GetCondition every frame). Reproduces the game's own
 * recvaddr computation from the input double buffer, writes it to descriptor
 * word1, then clears the [desc+0x18] pending bit so the caller sees "done".
 * Caller treats return >= 0 as OK. [KB §input-ABI site B -- M4-gated.] */
int shim_maple_entry(void) {
    u32 base = GW(0x8c0e8410);
    if (GW(base + 0x0fc0) != 1) return -3;         /* input subsystem not ready */
    u32 raw  = GW(base + 0x10b8);                  /* double-buffer index */
    u32 recv = GW(base + 0x10a8 + (raw & 1) * 4) & 0x0fffffff;  /* FUN_8c030fba: P1->phys */
    u32 desc = GW(base + 0x10f4);
    GW(desc + 0x04) = recv;                        /* descriptor word1 = recvaddr */
    GW(base + 0x10b8) = raw ^ 1u;                  /* toggle index (as the game does) */
    maple_reply(0x33, recv, 0);                     /* 0x33 only: no EEPROM write payload */
    GW(desc + 0x18) &= ~1u;                        /* clear pending bit0 = completion */
    return 0;
}

/* Task 14f: async-Maple MIE service -- the input+EEPROM transport (M3/M4).
 *
 * The steady engine FUN_8c03c2c6 (0x8c03c2c6-0x8c03c4a1) is reached via two
 * fn-ptr slots (pool[0x8c02ed6c] Mode A, pool[0x8c02ee88] Mode B); both are
 * repointed here. The sole live maple-base pool word 0x8c030fec (0xa05f6c00) is
 * repointed to MAPLE_MIRROR, so the engine's SB_MDSTAR/MDEN/MDST accesses hit
 * shim RAM, not real maple regs -> the game path triggers NO real controller DMA.
 *
 * Per-frame ordering, verified against DisasmRange 0x8c03c2c6-0x8c03c4a2:
 *   0x8c03c30a  read [desc+0x18]=mirror_SB_MDST; bit0 set (busy) -> return -1,
 *               bit0 clear -> proceed (0x8c03c30e).
 *   0x8c03c396  bsr FUN_8c03c1c2  -- the per-frame pump/state machine (MUST run;
 *               14b: replacing the builder skips it -> 0 cart reads).
 *   0x8c03c3d6  mov.l r0,@r8      -- mirror_SB_MDSTAR := phys(descriptor list).
 *   0x8c03c3e2  mov.l r12,@(0x18,r2) -- mirror_SB_MDST := 1 (trigger); returns 0.
 * So we call the REAL engine first (pump + build + trigger into the mirror), then
 * -- if it triggered (mirror_SB_MDST bit0 set) -- walk the descriptor list it just
 * programmed, synthesize each MIE reply into its recv addr, and clear
 * mirror_SB_MDST so next frame's cross-frame poll (0x8c03c30a) sees completion.
 * The reply is ready the same frame; the pump reads it on the following frame,
 * exactly as the real async DMA-to-recv-buffer would land it (double-buffered
 * recv addrs alternate 0x0c0fd8e0/0x0c1038e0 -- taken live from the descriptor).
 *
 * Descriptor list = maple command list (Flycast maple_DoDma, maple_if.cpp:184-311):
 *   +0x00 header_1 : bit31=last, [7:0]=plen-1, [10:8]=maple_op (0=MP_Start), [17:16]=bus
 *   +0x04 header_2 : recv addr (& 0x1fffffe0)
 *   +0x08 frame_hdr: [7:0]=cmd (0x86=MIE), [15:8]=reci (0x20=MIE)
 *   +0x0c payload[0] low byte = subcommand
 *   +0x14 frame byte 12 = JVS command (transmit subs; = boot builder arg0+4)
 *   next frame at +(2+plen)*4. Reuses maple_reply + blobs unchanged. */
extern int shim_maple_steady(void);   /* both fn-ptr slots point here (ptr patches) */
#define MMIR(off) (*(volatile u32 *)P2ADDR(MAPLE_MIRROR + (off)))   /* mirror reg (uncached, game view) */

int shim_maple_steady(void) {
    la_tick();                                     /* SHIM_LOADSTAT: phase-A clock (no-op if off) */
    /* Task18 (M5, SUPERSEDES Task16's coin-byte pin): force FREE PLAY every frame.
     * PROVEN by screenshot (task-18-report): the free-play flag the credit display
     * AND the credit-decrement read is the settings-struct field at +0xc =
     * 0x8c1c9790 (base 0x8c1c9784 + 0xc), NOT the coin byte at +0x10 (0x8c1c9794)
     * Task16 pinned. The decrement gate FUN_8c081efc @0x8c081f48-52 skips the
     * `sub` (credit -= cost) when *(+0xc)==1; the attract/title credit display
     * shows "FREE PLAY" instead of "CREDIT(S) N" on the same flag. On DC the game
     * re-derives coin-mode at settings-init so +0xc lands 0 (coin mode); the coin
     * byte +0x10=0x1a alone does NOT flip it (the free-play decision is cached at
     * init, not re-read from the coin byte). shim_maple_steady runs once per frame
     * in the scene loop, so re-stamping +0xc=1 holds free-play. build_patch_table
     * asserts pool 0x8c081d14==0x8c1c9784 so a ROM shift fails the build. */
    *(volatile u32 *)0x8c1c9790 = 1;               /* settings+0xc = FREE PLAY */
    int rc = ((int (*)(void))0x8c03c2c6)();        /* real engine: pump + build + trigger into mirror */
    if (rc == 0) rc_ok_seen++;
    /* Row y68: interrupted-context PC. The heartbeat blinks through the stall,
     * so this runs from ISR context -- SPC = the PC of the spinning main
     * thread, readable off the TV. Names the hang loop without guessing.
     * Left: live per-tick sample. Right: 1 Hz latch (coherent single read). */
    /* MMU protection (the round-8/9 root cause: KOS hands off with the MMU
     * configured; a Naomi game assumes AT=0 forever) lives in the LOADER's
     * handoff (MMUCR=0 just before the jump). No per-tick guard here: the
     * round-12 screenshot bisect showed even a bare per-tick MMUCR READ from
     * this path kills Flycast's video present (v4_final black vs v5 attract);
     * nothing re-enables the MMU post-handoff, the loader clear suffices. */
#ifndef SHIM_PROBES
#define SHIM_PROBES 0   /* round-12 verdict: per-tick probes kill Flycast's video
                         * present. Retired -- the mystery they were built for is
                         * solved (MMU). Flip to 1 only for a new HW stall hunt. */
#endif
#if SHIM_PROBES
    /* DreamShell round 6: probes revived for the serial-SD wedge hunt.
     * Painter switched shim_hex -> hex_paint (shim_hex is SHIM_HUD-gated and
     * the HUD stays off); y68-right paints EXPEVT (classifies a
     * fault-restart pin: 0x040/0x060 TLB miss r/w, 0x0e0/0x100
     * address error r/w).   y68: SPC | EXPEVT     y82: TEA | VBR */
    void hex_paint(unsigned int, unsigned int, unsigned int);
    u32 spc; __asm__ volatile ("stc spc,%0" : "=r"(spc));
    hex_paint(20, 68, spc);
    /* HW round 4 (ra came back 8c02ed8c = the NORMAL service call site, both
     * worlds). Call graph (Ghidra): pump site lives in service FUN_8c02ec08,
     * whose ONLY caller is per-frame callback FUN_8c02e7d8 (vblank-registered
     * via FUN_8c02ea14; also called by engine-RESET routine FUN_8c02f082).
     * FUN_8c02e7d8 has a WATCHDOG: consecutive-fail counter [0x8c0e6134]
     * (incremented in the service when the pump returns rc<0, zeroed on
     * success) > 60 -> reset + [0x8c0e6138]++ (total reset count). Doom-loop
     * hypothesis: a transaction never completes on HW -> endless 60-frame
     * reset cycles while the parked main thread waits. Probes:
     *   y68 right: WHO invoked FUN_8c02e7d8 -- its saved PR, found by scanning
     *     the stack for the service's known return address 0x8c02e7e8; the
     *     word +0x1c above is the callback's saved PR (frame layouts fixed:
     *     service pushes r14,r13,r12,r11,r10,r9,PR; callback pushes r14,PR).
     *     Vblank-dispatcher address = normal; 0x8c02f0f4 = reset-loop.
     *   y82: [0x8c0e6134] fail counter | [0x8c0e6138] reset count (climbing
     *     reset count = watchdog cycling confirmed). */
    /* HW round 5 exonerated the engine (disc=8c02abd8 normal dispatcher, fail
     * counter ~0, reset count 0 forever). Only two mechanisms can pin a
     * context at one PC while interrupts run normally:
     *   (a) the CODE at 8c081224 was overwritten with a self-branch -- prime
     *       suspect: our own MIE-ladder reply writes to descriptor-provided
     *       rcv pointers (the ladder only runs on real HW; a bogus pointer
     *       sprays a reply over game code, invisible in Flycast);
     *   (b) the insn genuinely never retires (fault-restart loop).
     * Probes: y68-right = LIVE code word at 0x8c081224 (healthy 0x6162 =
     * mov.l @r6,r1); y82 = SGR (interrupted context's r15) | the parked
     * frame's saved PR at [SGR+0x40] (must read 0x8c081b7c if genuinely
     * parked mid-FUN_8c0811f2: push r14+PR then add #-0x40 puts PR there). */
    /* HW round 6 pinned it hard: code word INTACT (6162), SGR frozen at
     * 0x8c00ef84 (main stack), [SGR+0x40]=0x8c081b7c -- every vblank catches
     * the SAME context on the SAME intact instruction. An intact insn that
     * never retires while interrupts flow = eternal fault-restart. The SH4
     * logs the confession: EXPEVT (0xff000024) = last exception cause,
     * TEA (0xff00000c) = last faulting data address.
     *   y68: SPC | EXPEVT     y82: TEA | SGR  */
    /* HW round 8 saw EXPEVT=0x040 (TLB MISS read) and prescribed "force
     * MMUCR=0 every tick". Round 13 retracts that medicine: THIS GAME RUNS
     * MMU-ON BY DESIGN -- it maps RAM through the store-queue window via
     * UTLB entries (SQ-mapper 0x8c0311a4, gated on MMUCR.AT; enable write
     * 0x40005 at 0x8c03b1c0). Forcing AT=0 has two failure masks, both
     * observed on HW: if the clear lands before the game's SQ-mapper runs,
     * the mapper SKIPS loading its TLB entries and the later SQ PREF
     * fault-restarts forever (round 8's eternal TLB-miss pin); if AT stays
     * cleared past the enable, SQ writes silently fall back to QACR area 0
     * and vanish -- the load->title closer buffers stay zero and the DMA
     * queue pins on the never-raised modifier-list-end event (rounds 9-12).
     * MMUCR is now owned by the game; gdc_call save/clears/restores it
     * around each isoldr syscall (gdstack.S). Read-only observation kept for
     * the serial log.  y68: SPC | EXPEVT  y82: TEA | VBR */
    u32 mmucr = *(volatile u32 *)0xff000010;
    hex_paint(120, 68, *(volatile u32 *)0xff000024);   /* EXPEVT */
    u32 vbr; __asm__ volatile ("stc vbr,%0" : "=r"(vbr));
    u32 sgr; __asm__ volatile ("stc sgr,%0" : "=r"(sgr));
    hex_paint(20, 82, *(volatile u32 *)0xff00000c);
    hex_paint(120, 82, vbr);
    /* DreamShell round 8/9: SDK sound-driver liveness. The game's SDRV boot
     * (FUN_8c02a4f4) keeps [0x8c0e6894]=init flag (1 = up) and
     * [0x8c0e6898]=sound ctx; the driver heartbeat word sits in ARAM at
     * OFFSET [ctx+0x98] + 0x18 -- an offset, not a pointer: reader
     * FUN_8c03a3a4 passes it to ARAM-word-reader FUN_8c039688, whose pool
     * holds bound 0x00200000 (2 MB ARAM) and base 0xa0800000 (boot.bin
     * 0x196cc/0x196d0). Round 8 wrongly demanded an absolute 0x008xxxxx
     * pointer here and painted BAD1 over a healthy offset 0x0001xxxx.
     * y96: ctx | heartbeat -- a TICKING right cell = ARM driver alive;
     * frozen = dead; 0xBADxxxxx = chain not valid yet. */
    {
        u32 sfl = *(volatile u32 *)0xac0e6894;
        u32 sct = *(volatile u32 *)0xac0e6898;
        hex_paint(20, 96, sct);
        u32 hb = 0xbad00000u | (sfl & 0xffffu);
        if (sfl == 1 && (sct & 0x1f000000u) == 0x0c000000u) {
            u32 sb = *(volatile u32 *)(0xa0000000u | ((sct & 0x1fffffffu) + 0x98u));
            if (sb < 0x00200000u && (sb & 3u) == 0)     /* ARAM offset, FUN_8c039688's checks */
                hb = *(volatile u32 *)(0xa0800000u + sb + 0x18u);
            else
                hb = 0xbad10000u | (sb >> 16);
        }
        hex_paint(120, 96, hb);
    }
    /* DreamShell round 10: transfer-queue autopsy. Round 9 proved the ARM
     * driver ALIVE (heartbeat counting) while the main thread spins in
     * FUN_8c033c50 waiting for its queued command to leave the 3x32-slot
     * DMA-request rings (head 0x8c0fb8e0; allocator FUN_8c032e00, pump
     * FUN_8c033400, transport FUN_8c033160). Slots are freed ONLY by the
     * DMA-end interrupt callback (0x8c0473c0, registered in FUN_8c0400e0
     * for Holly events; five consecutive IDs 0x15-0x19 get bits
     * 0x10,8,4,2,1 = ISTNRM bits 15-19 AICA/Ext1/Ext2/Dev/ch2-DMA;
     * 0x11=PVR-DMA), and only when arrived-mask (slot+0x1e) covers
     * expected-mask (slot+0x1c). Engines used: SH4 DMAC ch2 DDT
     * (SAR2/DMATCR2/CHCR2=0x12c1/DMAOR=0x8201) + Holly ch2-DMA
     * (SB_C2DSTAT/LEN/ST) and PVR-DMA (SB_PD*, SB_PDAPRO=0x6702007f).
     * Rows (below the GD diag):
     *   y162: ISTNRM | DMAOR<<16 . C2DST<<8 . PDST<<4 . ADST
     *   y176: DMATCR2 | CHCR2
     *   y190: in-flight slot ptr | expected<<16|arrived
     *         (no slot: 0 | 0xC0.c0.c1.c2 ring counts) */
    /* DreamShell round 12: pinned-slot AUTOPSY. Round 10/11 proved: DMA
     * engines idle+drained, ch2-DMA-end arrived (0x8000), but the TA closed
     * an OPAQUE list (arrived 0x1 = ISTNRM bit 7) where the slot expected
     * OPAQUE-MODIFIER end (0x2 = bit 8) -- and a handoff TA SOFTRESET
     * changed nothing (round 11). The TA picks the end interrupt from the
     * list type REGISTERED by the first global param's PCW (flycast ta.cpp
     * ta_handle_cmd: cl==7 -> cl=pcw.ListType; EOL -> int[cl]) -- so either
     * the game BUILT an opaque-typed list while wiring a modifier
     * descriptor, or the DMA source was recycled/clobbered before flight.
     * Read the actual bytes: PCW bits 31:29 = para type (4=global poly/
     * modvol), bits 26:24 = list type (0=OP, 1=OP-MOD).
     *   y162: ISTNRM | slot ptr
     *   y176: mode<<24|flags<<16|chunks | expected<<16|arrived
     *   y190: src | dst          y204: PCW@src | PCW@(src+len-0x20)
     *   y218: len | TA_ALLOC_CTRL */
    /* DreamShell round 15: VIDEO-OUTPUT autopsy. Round 14 killed the boot
     * pin (patch #36) and HW now reaches the post-transition world: main
     * thread cycling healthily (SPC 8c02xxxx), zero exceptions, ARM sound
     * heartbeat ticking, cart streams flowing, TA in title alloc 00121213,
     * transfer rings drained -- yet the DISPLAY stays black while the probe
     * text flickers at flip rate (= the game presents frames, their content
     * is black). Flycast shows the real title art on the same build
     * (r14-post10.png) -- the divergence is in the video-output plumbing,
     * plausibly isoldr-left video state the game's init doesn't fully
     * reprogram. One photo of the PVR output registers decides:
     *   y162: FB_R_SOF1 | FB_W_SOF1   (scanout field 1 vs render target)
     *   y176: FB_R_SOF2 | FB_W_SOF2   (field 2)
     *   y190: FB_R_CTRL | FB_W_CTRL   (fb enable bit0 / formats)
     *   y204: VO_CONTROL | SPG_CONTROL (blank bit3 | interlace bit4 etc.)
     *   y218: SPG_STATUS | ISP_BACKGND_T (field/sync | background plane tag)
     * The round-12 transfer-queue autopsy rows this replaces are preserved
     * in git history (proven healthy in the round-13/14 photos). */
    /* Round 18: TA-output ground truth. Round 17 proved renders are ISSUED
     * repeatedly (director retry loop, pending=1/state=5, ctx alternating
     * registry entries 0/4) and NEVER complete -- the CORE hangs walking
     * its inputs, or gets no inputs. Read back what the TA actually built:
     *   y162: FB_R_SOF1 | FB_W_SOF1        (issue/flip activity, kept)
     *   y176: PARAM_BASE | REGION_BASE     (CORE input pointers, 5F8020/2C)
     *   y190: VRAM[REGION_BASE+0] | +4     (region-array entry 0 via the
     *         32-bit path -- sane = tile control word + list pointer;
     *         zeros/garbage = the CORE walks junk)
     *   y204: TA_ITP_CURRENT | TA_ISP_BASE (5F8138/5F8128: cursor past
     *         base = the TA stored geometry this frame)
     *   y218: TA_NEXT_OPB | TA_OL_BASE     (5F8134/5F8124: OPB alloc
     *         cursor vs base -- same test for object-pointer blocks) */
    /* Round 18 HW verdict: CORE inputs SANE (PARAM_BASE=0=TA_ISP_BASE,
     * REGION_BASE=B03C8 under the FB, region-array entry 0 = 10000000 |
     * 80000000 = valid control word + EMPTY opaque pointer) -- but
     * TA_ITP_CURRENT frozen at 0x6C (108 bytes of geometry EVER) and
     * ist_seen=B038: no TA list-end, no ch2-DMA-end, ever. The CORE
     * renders an empty/unterminated scene every frame; the geometry
     * stream to the TA is what's dead. Round 19: resurrect the round-10
     * transfer-queue autopsy (proven rows, git 0c5f0a4) to split "ch2
     * DMA wedged in flight" from "game never submits":
     *   y162: ISTNRM | DMAOR<<16 . C2DST<<8 . PDST<<4 . ADST
     *   y176: DMATCR2 | CHCR2              (SH4 DMAC ch2: count left, cfg)
     *   y190: in-flight slot ptr | expected<<16|arrived
     *         (no slot: 0 | 0xC0.c0.c1.c2 ring counts)
     *   y204: SAR2 | SB_C2DSTAT            (source / Holly dest cursors --
     *         how far the wedged transfer got)
     *   y218: TA_ITP_CURRENT | SB_C2DLEN   (TA store cursor kept | len reg) */
    {
        u32 istnrm = *(volatile u32 *)0xa05f6900;
        u32 dmaor  = *(volatile u32 *)0xffa00040;
        u32 c2dst  = *(volatile u32 *)0xa05f6808;
        u32 pdst   = *(volatile u32 *)0xa05f7c18;
        u32 adst   = *(volatile u32 *)0xa05f7818;
        hex_paint(20, 162, istnrm);
        hex_paint(120, 162, (dmaor << 16) | ((c2dst & 0xfu) << 8)
                          | ((pdst & 0xfu) << 4) | (adst & 0xfu));
        hex_paint(20, 176, *(volatile u32 *)0xffa00028);   /* DMATCR2 */
        hex_paint(120, 176, *(volatile u32 *)0xffa0002c);  /* CHCR2 */
        /* P1 reads: ring is game-written through the cache, same CPU. */
        u32 h = 0x8c0fb8e0u;
        u32 s = *(volatile u32 *)(h + 0x20);
        if (!s) s = *(volatile u32 *)(h + 0x24);
        if (!s) s = *(volatile u32 *)(h + 0x28);
        hex_paint(20, 190, s);
        u32 r;
        if (s && (s & 0x1f000000u) == 0x0c000000u)
            r = ((u32)*(volatile u16 *)(s + 0x1c) << 16)
              | *(volatile u16 *)(s + 0x1e);
        else
            r = 0xc0000000u
              | ((*(volatile u16 *)(h + 0x30) & 0x3fu) << 16)
              | ((*(volatile u16 *)(h + 0x36) & 0x3fu) << 8)
              |  (*(volatile u16 *)(h + 0x3c) & 0x3fu);
        hex_paint(120, 190, r);
        hex_paint(20, 204, *(volatile u32 *)0xffa00020);   /* SAR2 */
        hex_paint(120, 204, *(volatile u32 *)0xa05f6800);  /* SB_C2DSTAT */
        hex_paint(20, 218, *(volatile u32 *)0xa05f8138);   /* TA_ITP_CURRENT */
        hex_paint(120, 218, *(volatile u32 *)0xa05f6804);  /* SB_C2DLEN */
    }
    /* Round 16 HW verdict: Holly masks HEALTHY (IML4/6 match the green
     * world exactly, incl. render-done + list-end on level 6; IML2=0 is
     * BIOS-internal, absent under isoldr by design) and ISTNRM settles at
     * 0x10 -- render-done NEVER LATCHES. So the chip-side switchboard is
     * fine; the failure is in the render issue/complete state machine.
     * Round 17: paint the frame director's own state (FUN_8c036220 sets
     * [0x8c0eb72c]=active render ctx, [0x8c0eb728]=1 render-pending,
     * ctx+0x14=5 "rendering" -- the render-done path must clear/advance
     * these; pools resolved from file 0x16550/0x16554).
     *   y232: active render ctx | render-pending flag
     *   y246: ctx->state (+0x14; ffffffff = no valid ctx) | ISTNRM
     *         OR-accumulator since boot (catches transiently latched bits;
     *         render-done=bit2, list-ends=bits 7-10,21) */
    {
        static u32 ist_seen = 0;
        ist_seen |= *(volatile u32 *)0xa05f6900;
        u32 rctx = *(volatile u32 *)0x8c0eb72c;
        hex_paint(20, 232, rctx);
        hex_paint(120, 232, *(volatile u32 *)0x8c0eb728);
        u32 rstate = 0xffffffffu;
        if ((rctx & 0x1f000000u) == 0x0c000000u)
            rstate = *(volatile u32 *)(rctx + 0x14);
        hex_paint(20, 246, rstate);
        hex_paint(120, 246, ist_seen);
    }
#endif /* SHIM_PROBES */
    if ((++steady_beat & 63u) == 0) {              /* forensic heartbeats, ~1 Hz at 60 fps */
        u32 ph = steady_beat & 64u;
        /* Round-16 rate windows: values update 1/s here; PAINTED every poll
         * in jvs_digital (a 1/s paint is overdrawn by the game for 59 of 60
         * frames -- unreadable, round-13 lesson relearned). */
        {
            extern u32 cart_count, getcond_total;
            static u32 last_gc = 1, last_cc = 1;
            gc_rate = getcond_total - last_gc;
            cc_rate = cart_count - last_cc;
            last_gc = getcond_total; last_cc = cart_count;
        }
#if SHIM_PROBES
        scif_puts("SPC=");    scif_puthex(spc);           /* stall-PC in Flycast log */
        scif_puts(" expevt=");scif_puthex(*(volatile u32 *)0xff000024);
        scif_puts(" tea=");   scif_puthex(*(volatile u32 *)0xff00000c);
        scif_puts(" mmucr="); scif_puthex(mmucr);
        scif_puts(" vbr=");   scif_puthex(vbr);
        scif_puts(" sgr=");   scif_puthex(sgr);
        scif_puts("\n");
#endif
        /* slot8: engine pumped. red/green = alive but NO DMA triggers this
         * window; blue/yellow = alive AND triggering (frames being issued). */
        shim_mark(8, (trig_seen & 0xffffu) ? (ph ? 0x001f : 0xffe0)
                                           : (ph ? 0xf800 : 0x07e0));
        /* slot10: engine verdict. white/gray toggle = returned OK at least
         * once this window; solid red = every call came back "busy" (-1). */
        shim_mark(10, (rc_ok_seen & 0xffffu) ? (ph ? 0xffff : 0x8410) : 0xf800);
        trig_seen = 0x10000; rc_ok_seen = 0x10000;
    }
    if (MMIR(0x18) & 1u) {                          /* mirror_SB_MDST bit0 = a DMA was triggered this frame */
        trig_seen++;
        u32 addr = MMIR(0x04) & 0x1fffffe0u;        /* mirror_SB_MDSTAR = phys(descriptor list) */
        u32 i;
        /* Row-2 forensic indicators: classify the triggered list AS SEEN on
         * this hardware (the walk found no MIE frames on real DC via cached
         * AND uncached reads -- so report what IS there). Repainted per
         * trigger; red=bad green=good yellow=odd. */
        u32 dg_frames = 0, dg_mpstart = 0, dg_cmd86 = 0, dg_h1first = 0;
        u32 dg_fh1 = 0, dg_rcv1 = 0, dg_pay1 = 0, dg_fh2 = 0;
        shim_mark(16, addr == 0 ? 0xf800 :
                      (addr >= 0x0c000000u && addr < 0x0d000000u) ? 0x07e0 : 0xffe0);
        /* Final review: the list base is game-controlled (mirror_SB_MDSTAR).
         * Only walk it if it points at RAM (32 MB window: covers Naomi-style
         * 0x0d addresses, which a 16 MB DC mirrors back into RAM; excludes
         * MMIO/VRAM). A garbage/stale pointer would otherwise feed the walk's
         * uncached reads side-effectful MMIO (e.g. the GD data FIFO 0x5f7080,
         * popping an in-flight cart stream) and let the reply writes below
         * spray registers or live code. Skip the walk but still complete the
         * transaction: the engine rebuilds its list next frame; a spray never
         * self-heals. Never fires in normal play (two compares per frame). */
        if (addr - 0x0c000000u < 0x02000000u)
        for (i = 0; i < 32u; i++) {                 /* walk cmd list (<=24 slots); cap guards a runaway list */
            /* UNCACHED walk. The pump writes this list as DMA-SOURCE memory
             * (real maple hardware reads it from RAM, so the game keeps it out
             * of / flushed past the D-cache); a cached read hit stale lines on
             * real DC -- engine triggering every frame yet the walk finding no
             * MIE frames (HUD forensics 2026-07-21). Flycast has no cache, so
             * cached reads worked there and masked this, same class as the
             * Task 20 cart-dest bug. */
            u32 h1   = UW(addr + 0x00);             /* transfer control */
            u32 rcv  = UW(addr + 0x04) & 0x1fffffe0u;   /* recv addr (phys) */
            u32 plen = (h1 & 0xffu) + 1u;
            if (i == 0) dg_h1first = h1;
            dg_frames++;
            if (((h1 >> 8) & 7u) == 0u) {           /* MP_Start command frame */
                dg_mpstart++;
                u32 fh = UW(addr + 0x08);           /* frame header */
                if (dg_mpstart == 1) { dg_fh1 = fh; dg_rcv1 = rcv; dg_pay1 = UW(addr + 0x0c); }
                else if (dg_mpstart == 2) dg_fh2 = fh;
                if ((fh & 0xffu) == 0x86u) dg_cmd86++;
                if ((fh & 0xffu) == 0x86u && ((fh >> 8) & 0xffu) == 0x20u) {  /* MIE: cmd 0x86 / reci 0x20 */
                    u32 sub = UB(addr + 0x0c);      /* payload[0] low byte = subcommand */
                    switch (sub) {                  /* transmit subs: latch JVS cmd (frame byte 12 = desc+0x14) */
                    case 0x17: case 0x19: case 0x21: pending_jvs = UB(addr + 0x14); break;
                    case 0x27:                       pending_jvs = 0xff;            break;
                    }
                    if (rcv - 0x0c000000u < 0x02000000u)  /* recv sane (see list-base guard) */
                        maple_reply(sub, rcv, addr);/* synthesize reply; addr=frame base (EEPROM write payload) */
                } else if (rcv - 0x0c000000u < 0x02000000u) {  /* non-0x86: the MIE init ladder (real HW only) */
                    mie_probe_reply(fh & 0xffu, fh, rcv, addr);
                }
            }
            if (h1 >> 31) break;                    /* last-transfer bit -> end of list */
            addr += (2u + plen) * 4u;
        }
        shim_mark(17, dg_h1first == 0 ? 0xf800 : 0x07e0);            /* first desc word null? */
        shim_mark(18, dg_mpstart ? 0x07e0 : 0xf800);                 /* any MP_Start frames? */
        shim_mark(19, dg_cmd86 ? 0x07e0 : 0xf800);                   /* any MIE (0x86) cmds? */
        shim_mark(20, dg_frames == 0 ? 0xf800 :
                      dg_frames < 4 ? 0xffe0 : 0x07e0);              /* entries walked: 0/-4/4+ */
        /* Row 3-5: the stuck transaction in actual hex, repainted per trigger.
         *   y26: [list ptr]      [first desc word h1]
         *   y40: [frame header]  [recv addr]
         *   y54: [payload word0] [2nd frame header]  */
        shim_hex(20, 26, MMIR(0x04));  shim_hex(120, 26, dg_h1first);
        shim_hex(20, 40, dg_fh1);      shim_hex(120, 40, dg_rcv1);
        shim_hex(20, 54, dg_pay1);     shim_hex(120, 54, dg_fh2);
        /* Round-18: SHIM_TRACE gates all per-frame/per-event serial. On real
         * HW a ~75-char line overflows the 16-byte SCIF FIFO and spin-waits
         * ~5 ms at 115200 baud -- EVERY frame (the wr_left==32 "one-shot"
         * fires forever now that the EEPROM lib is stubbed and wr_left never
         * decrements). Free in Flycast (instant drain) = the last 2P drag +
         * the rare 1P hiccups (IN-raw printed per button press). */
        if (SHIM_TRACE && wr_left == 32) {
            scif_puts("LISTDIAG star="); scif_puthex(MMIR(0x04));
            scif_puts(" h1=");     scif_puthex(dg_h1first);
            scif_puts(" frames="); scif_puthex(dg_frames);
            scif_puts(" mp=");     scif_puthex(dg_mpstart);
            scif_puts(" c86=");    scif_puthex(dg_cmd86);
            scif_puts("\n");
        }
        MMIR(0x18) = 0;                             /* completion: next frame's poll sees SB_MDST bit0 clear */
    }
    return rc;
}

/* MIE maple-protocol init ladder (real-HW hang fix, 2026-07-21). On real DC the
 * engine runs the FULL device bring-up before any 0x86 MIE subcommand:
 *   DeviceReset(03) -> DeviceRequest(01) -> JVSGetId(82) -> JVSUploadFirmware
 *   (80, ~600 Z80-firmware chunks each ACKed with a checksum) -> 0x86 traffic.
 * (Naomi-mode Flycast capture fly23n.log: CLEO-MIE lines; the DC-mode HLE boot
 * never entered this ladder, so the shim only spoke 0x86 and the engine
 * re-probed forever -- row-2 HUD: valid lists, zero 0x86 frames.) Replies are
 * byte-exact to Flycast's BaseMIE (maple_jvs.cpp:1291-1400): reply word0 =
 * resp | sender_in<<8 | reci_in<<16 | words<<24. The firmware payload itself
 * is discarded -- there is no Z80; only the additive checksum is echoed. */
static const char mie_id48[] = "315-6149    COPYRIGHT SEGA ENTERPRISES CO,LTD.  ";  /* 48 used */

static void mie_probe_reply(u32 cmd, u32 fh, u32 rcv, u32 frame) {
    volatile u32 *rx  = (volatile u32 *)P2ADDR(rcv);
    volatile u8  *rx8 = (volatile u8  *)P2ADDR(rcv);
    u32 hdr = ((fh >> 16) & 0xffu) << 8 | ((fh >> 8) & 0xffu) << 16;  /* sender/reci echo */
    u32 k;
    switch (cmd) {
    case 0x01: rx[0] = hdr | 0x05; break;            /* DeviceRequest -> empty DeviceStatus */
    case 0x02: rx[0] = hdr | 0x06; break;            /* AllStatusReq  -> empty */
    case 0x03: case 0x04:
               rx[0] = hdr | 0x07; break;            /* DeviceReset/Kill -> DeviceReply */
    case 0x82:                                        /* JVSGetId -> dual frame + ID */
        rx[0] = hdr | 0x83 | (7u << 24);
        for (k = 0; k < 28; k++) rx8[4 + k] = mie_id48[k];
        rx[8] = hdr | 0x83 | (5u << 24);
        for (k = 0; k < 20; k++) rx8[36 + k] = mie_id48[28 + k];
        break;
    case 0x80:                                        /* firmware upload chunk / finalize */
        if (UB(frame + 0x0d) == 0xffu) { rx[0] = hdr | 0x07; break; }
        {
            u32 sum = 0;
            for (k = 0; k < 0x1c; k++) sum += UB(frame + 0x0c + k);
            rx[0] = hdr | 0x80 | (1u << 24);
            rx[1] = sum & 0xffu;
            rx[2] = hdr | 0x07;
        }
        break;
    default:                                          /* unknown probe: benign ACK */
        rx[0] = hdr | 0x07;
        break;
    }
}

/* Task 15c: service the CONFIG-TIME JVS enumeration so node-count [0x8c1ca474]>=1
 * and the board struct [0x8c1ca47c] populates -> the runtime engine registers a
 * JVS-board slot and emits sub-0x33 (the per-frame input poll 14f already routes
 * to jvs_digital). This UNBLOCKS input (M4).
 *
 * ROOT CAUSE (re-RE'd; corrects the Task-15b/task-brief premise). The config JVS
 * probe FUN_8c082bc4 does NOT drive raw maple by absolute literal, and it does
 * NOT use the Z80-firmware-upload path FUN_8c080d18/FUN_8c0809b2 (that path is the
 * dead-result Z80 upload -- Task 14b was right; its result vars are write-only).
 * The probe/parser/per-node-builder (FUN_8c082bc4 / FUN_8c082c98 / FUN_8c082aa4,
 * all reached from the node-count commit FUN_8c082fd8) transmit via FUN_8c081562
 * and receive via FUN_8c081626, which funnel through FUN_8c03000c / FUN_8c02f158
 * on the SHARED maple engine struct *0x8c0e8410 -- the SAME struct the runtime
 * engine FUN_8c03c2c6 uses, whose base [struct+0x10f4]=0xa05f6c00 is ALREADY
 * mirrored (patch #16). So the config DMA never hit real DC maple; mirroring more
 * literals does nothing. Yet node-count stays 0 (capture-14f.log: all 61 IOCHK
 * specs=1) because the config frames are queued (FUN_8c03000c) and only flushed by
 * the async engine across a cooperative yield (FUN_8c082a96 -> FUN_8c0342c0) --
 * which does not deliver the reply at the probe's synchronous read time on DC.
 *
 * FIX (parallels 14f -- hook the transport, synthesize the reply, at the CONFIG
 * layer). build_patch_table repoints the 7 pool words that hold FUN_8c081562 (TX,
 * 4 words) and FUN_8c081626 (RX, 3 words) -- used ONLY by the enum cluster
 * 0x8c082aa4..0x8c082e4c (boot.bin scan) -- to these routines. shim_cfg_tx latches
 * the JVS command (payload[0]); shim_cfg_rx returns the matching captured Naomi
 * reply at +0x15 (FUN_8c081626 returns *(slot+8)+0x15; probe/parser read
 * reply[k]=frame[0x15+k]). This reproduces the EXACT Naomi 1-board enumeration:
 *   F1  -> mie_jvsf1 : reply[3]=0,reply[8]=1,reply[4]!=0,reply[1]=0x8e
 *          => probe FUN_8c082bc4 returns 1 => node-count=1.
 *   10..14 -> mie_jvs10..14 : parser FUN_8c082c98 fills the board struct; the
 *          mie_jvs14 feature list (2 players / 13 switches / 2 coin / 8 analog)
 *          satisfies spec-compute (byte0>=2, byte1>=8) => specs=0.
 *   default (incl. cmd 0x21 from FUN_8c082aa4) -> mie_jvsf1 : validator
 *          FUN_8c082654 passes for node 1 (reply[2]=0x01==node, reply[3]=0,
 *          reply[8]=1, reply[4]!=0); its result does not gate node-count/spec.
 * All blobs have [0x17]=0x01 so reply[2]==node(1). 14c specs-force (patch #19)
 * becomes redundant (specs=0 naturally) but is harmless -- left in place. */
int shim_cfg_tx(u32 node, u32 arg1, u32 len, u32 payload);   /* FUN_8c081562 replacement */
const unsigned char *shim_cfg_rx(void);                      /* FUN_8c081626 replacement */

int shim_cfg_tx(u32 node, u32 arg1, u32 len, u32 payload) {
    (void)node; (void)arg1; (void)len;
    HUD_ONCE(0x10, 7, 0xfc00);          /* slot7 orange: config-enum transmit reached */
    ls_stampA(1);                        /* SHIM_LOADSTAT: config JVS enum reached */
    pending_cfg = GB(payload);          /* payload[0] = JVS command byte */
    return 0;                            /* callers ignore r0 */
}

const unsigned char *shim_cfg_rx(void) {
    const unsigned char *b;
    u8 bit;
    HUD_ONCE(0x04, 2, 0x07ff);                           /* slot2 cyan: JVS config enum */
    switch (pending_cfg) {
    case 0x10: b = mie_jvs10; bit = 0x01; break;
    case 0x11: b = mie_jvs11; bit = 0x02; break;
    case 0x12: b = mie_jvs12; bit = 0x04; break;
    case 0x13: b = mie_jvs13; bit = 0x08; break;
    case 0x14: b = mie_jvs14; bit = 0x10; break;
    case 0xf1: b = mie_jvsf1; bit = 0x20; break;
    default:   b = mie_jvsf1; bit = 0x40; break;   /* cmd 0x21 per-node builder etc. */
    }
    if (!(cfg_seen & bit)) {            /* one-shot serial trace per command */
        cfg_seen |= bit;
        scif_puts("CFG enum cmd="); scif_puthex(pending_cfg); scif_puts("\n");
    }
    return b + 0x15;                     /* reply base: game reads reply[k]=frame[0x15+k] */
}

/* Task 16 (M5): config-time EEPROM read for the settings validator FUN_8c080094.
 *
 * ROOT CAUSE of "9 CREDITS" (instrumented DC boot + Ghidra RE). The validator
 * FUN_8c080094 reads the 93C46 via FUN_8c080f50 (hooked here), recomputes both
 * system-section CRC copies, and on a double mismatch re-inits the system section
 * to ROM coin-mode defaults (coin byte 0x00) via FUN_8c07ffee -> writes it back
 * (the observed EE WR x16, coin=0x00), discarding our delivered free-play (0x1a).
 * FUN_8c080f50 issues the read through the SHARED async engine (FUN_8c03000c queue
 * / FUN_8c02f158 result / FUN_8c0342c0 flush) whose reply is delivered a-frame-
 * later by shim_maple_steady -- AFTER the validator has already read its buffers.
 * So on DC the validator always sees garbage -> both CRCs fail -> re-init. This is
 * the SAME synchronous-vs-async config-read gap Task 15c fixed for JVS enum; the
 * EEPROM read hits it too because it uses the raw engine funcs, not the FUN_8c081562
 * /FUN_8c081626 wrappers 15c hooked. Naomi never showed this (0x 0x0b): real MIE
 * delivers synchronously (KB §V-EEPROM).
 *
 * FIX (parallels 15c -- hook the config transport, synthesize the reply
 * synchronously): replace FUN_8c080f50 with a direct fill of its three output
 * buffers from the baked free-play image, so the validator sees valid free-play
 * (both copies' CRC = 0x50cb) -> returns 0 (both valid), no re-init, no write.
 * Buffer layout is from the FUN_8c080f50 disasm (pool words 0x8c08107c/1080/1084;
 * validator pool 0x8c080184/0188): full 128 B at 0x8c1c954c, system copy1 (bytes
 * 0..17) at 0x8c1c9528, system copy2 (bytes 18..35) at 0x8c1c953a. These are
 * ordinary game-RAM work buffers read cached, so cached writes are coherent. The
 * async transport is intentionally skipped (its late reply was the bug); the game
 * section (bytes 36..127) is copied through verbatim, matching Naomi. build_patch_
 * table asserts these buffer pool words so a ROM shift fails the build. */
/* Settings write-back skip (real-HW hang fix, 2026-07-21). The orchestrator
 * FUN_8c081aee calls the write kicker via pool 0x8c081d20 (FUN_8c080446 = a
 * thunk into the Naomi BIOS 0x60000 library, which bit-bangs the cart-board
 * EEPROM through G1 registers a DC doesn't have -- 19 unpatched 0x5f7xxx
 * literals in that subtree; on real DC it spins forever on drive status while
 * the ISR-driven maple engine keeps polling ports B/C, matching the HUD hex
 * forensics). r0==0 from the kicker makes the game NATIVELY skip the whole
 * write+wait sequence (0x8c081b8c-8e: tst/bt). Persistence is meaningless on
 * DC: reads deliver the baked free-play image (shim_ee_read) and free-play is
 * re-stamped every frame (Task 18), so "nothing to write" is correct. */
int shim_ee_write_skip(void);
int shim_ee_write_skip(void) {
    shim_mark(11, 0xffff);   /* slot11 white = kicker WAS reached (HW forensics) */
    return 0;
}

/* HW stall #2 (2026-07-21, SPC row): with #29 in place the HUD was unchanged and
 * slot 11 never painted -- the main thread pins at SPC=0x8c081224, inside the
 * settings-decode helper FUN_8c0811f2, which ENDS in `bsr 0x8c0803f8`: another
 * thunk into the SAME Naomi BIOS 0x60000 library (fn-table [0x8c0804d0] slot
 * +0x10) that bit-bangs cart-board EEPROM -- the thread dives in ~50 insns after
 * the pin and never returns. The orchestrator FUN_8c081aee then calls three more
 * table thunks unconditionally AFTER the kicker (0x8c080418@bac, 0x8c080426@bb4,
 * 0x8c080456@bc0) -- same library, next landmines. All callers of all five
 * thunks are settings/credit EEPROM flows (orchestrator, settings-save
 * FUN_8c081c76, credit gate FUN_8c081efc), fully neutralized in this port
 * (reads = baked free-play image; free-play re-stamped per frame). Fix: hook
 * the THUNK BODIES (covers pool + bsr callers alike) with return-0 stubs;
 * slot 0x10's return feeds a changed-count accumulator, the trio's returns are
 * ignored, so 0 = the native nothing-changed path everywhere.
 *   slot12 green  = decode-commit (0x8c0803f8) reached -- the former blocker
 *   slot13 yellow = any of the post-kicker trio reached */
int shim_ee_lib_decode(void);
int shim_ee_lib_decode(void) { shim_mark(12, 0x07e0); return 0; }

/* VGA-blur regression fix (2026-08-16, patch #37 -- replaces the deleted,
 * never-firing patch #34). The game's video mode is chosen by ITS OWN chain:
 * boot scene FUN_8c04b2cc -> monitor getter FUN_8c025886 ([0x8c0c4518]==1 ?
 * [0x8c0c4524] : -1); monitor 0 -> mode 0x31 (31 kHz, sharp), 1 ->
 * 0x80000038 (NTSC 480i), invalid -> hardcoded 0x80000038 at 0x8c04ae98.
 * The globals' native writer FUN_8c0257f4 keys them on field +0x0c of the
 * settings record served by FUN_8c081432 -- selected by the settings INDEX
 * that patch #36 deterministically stubs to 0, whose record has +0x0c == 0
 * = 15 kHz -> interlace on every cable (r26 trace: native writer sets
 * monitor=1 at pc 8c025826 BEFORE the choice; our late settings-flow writes
 * can't win the race). Main-GDEMU was sharp because the un-stubbed lib read
 * yielded a record with +0x0c != 0. Fix: replace the native writer, mirror
 * its exact store set keyed on the real DC cable, and let the game's own
 * chooser + class-vs-monitor validation do the rest.
 *   31 kHz (VGA):   451c=0, 4524=0, 4520=0, 4518=1  (native r3!=0 arm)
 *   15 kHz (TV):    451c=2, 4524=1, 4520=0, 4518=1  (native r3==0 arm)
 * Return 0 = the native "wrote it" path (-1 = already-valid early-out). */
int shim_monitor_set(void);
int shim_monitor_set(void) {
    unsigned int vga = shim_cable_is_vga() ? 1u : 0u;
    *(volatile u32 *)0x8c0c451c = vga ? 0u : 2u;
    *(volatile u32 *)0x8c0c4524 = vga ? 0u : 1u;
    *(volatile u32 *)0x8c0c4520 = 0;
    *(volatile u32 *)0x8c0c4518 = 1;
#if SHIM_LOADBAR
    /* Task 26: empty bar at the earliest boot-scene hook, over the loader's
     * splash (FB_R_SOF1 still points there pre-takeover), so the bar's track
     * shows before the first cart stream instead of a black gap (Cleopatra's
     * vid-init paint, same purpose). ONE-SHOT, unlike Cleopatra's: this
     * writer can re-fire from the test menu's video settings, and a bar-0
     * splat over live play would be the exact overshoot failure the cart.c
     * undershoot rule guards against. .data non-zero init (house style). */
    {
        extern void loadbar_paint(unsigned int);
        static u32 lb0_todo = 1;
        if (lb0_todo) { lb0_todo = 0; loadbar_paint(0); }
    }
#endif
    return 0;
}
int shim_ee_lib_post(void);
int shim_ee_lib_post(void)   { shim_mark(13, 0xffe0); return 0; }

/* DreamShell round 14: the rounds-1..13 bar-0% pin was NEVER a spin inside the
 * EE library -- it is the wild read at 0x8c081224. Chain: patch #15 makes the
 * game's Naomi-BIOS fingerprint check pass (FUN_8c081438, 112 B @0xa01ffd00 vs
 * obfuscated table 0x8c0d7ed9 -> gate [0x8c1c9768]=1; REQUIRED, task-13: gate=0
 * dead-ends boot) -> orchestrator FUN_8c081aee trusts the lib-read path -> its
 * wrapper FUN_8c081bf0 calls READ thunk FUN_8c080484 (fn-table [[0x8c1c9764]]
 * slot +40 -- the un-stubbed sixth sibling of the five write-path stubs above)
 * to fill [0x8c1c9770], then passes that word to parser FUN_8c0811f2 as an
 * INDEX into a 32-byte stack table (r6 = SP + idx*4 at 0x8c081224). On the
 * tester's DC the lib read returns without writing, the word keeps DreamShell
 * boot residue (round 13 TEA 0x10667424, round 8 TEA 0x58c1fc94 = SP + 4*junk),
 * and -- with the game's designed early MMU-on state now preserved (gdstack.S
 * round 13) -- the wild address is unmapped: eternal TLB-miss restart, no
 * handler at VBR+0x400. Flycast/GDEMU are green because THEIR residue at
 * 0x8c1c9770 is zero (Flycast zeroes RAM; BIOS boot leaves it benign), i.e.
 * the proven-green worlds already run with index 0. Stub = deterministic
 * index 0 + return 0 (r0 ignored at the 8c081c04 call site).
 *   slot14 cyan = the read thunk was reached (HW breadcrumb) */
int shim_ee_idx_read(volatile u32 *out);
int shim_ee_idx_read(volatile u32 *out) {
    *out = 0;                /* ponytail: index 0 = flycast/GDEMU-residue behavior;
                              * revisit only if a settings variant needs 1-7 */
    shim_mark(14, 0x07ff);
    return 0;
}

/* HW round 7: skip the ENTIRE settings orchestrator FUN_8c081aee (entry hook).
 * The main thread is proven pinned (fault-restart) on an intact instruction
 * inside its decode helper -- mechanism still under investigation via
 * EXPEVT/TEA, but nothing the orchestrator does is needed in this port:
 * validation is satisfied by shim_ee_read's baked image (Task 16), writes are
 * stubbed (the five lib thunks), and free-play is re-stamped every frame
 * (Task 18). Return 0 = the value the orchestrator already returns through
 * its no-change path in the green Flycast runs. Sole caller: FUN_8c081bf0
 * tail-jumps here (bra 0x8c081aee @0x8c081c1a); its preamble still runs.
 * slot14 cyan = skip hook reached. */
int shim_settings_skip(void);
int shim_settings_skip(void) { shim_mark(14, 0x07ff); return 0; }

void shim_ee_read(void);
static u8 eeread_logged = 1;
void shim_ee_read(void) {
    HUD_ONCE(0x01, 0, 0xffff);                          /* slot0 white: first config contact */
    ls_stampA(2);                                       /* SHIM_LOADSTAT: EEPROM read reached */
    xmemcpy((void *)0x8c1c954c, eeprom_img, 128);      /* full 128-B image */
    xmemcpy((void *)0x8c1c9528, eeprom_img, 18);       /* system copy1 (CRC+data) */
    xmemcpy((void *)0x8c1c953a, eeprom_img + 18, 18);  /* system copy2 (CRC+data) */
    if (eeread_logged) {                                /* one-shot proof the sync read ran */
        eeread_logged = 0;
        scif_puts("EE READ sync: coin09="); scif_puthex(*(volatile u8 *)(0x8c1c9528 + 9));
        scif_puts("\n");
    }
}
#endif /* re-enabled per-task: see plan Tasks 10-12 */

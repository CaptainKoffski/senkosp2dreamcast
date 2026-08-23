/* Raw-ATA GD-ROM PIO driver -- the shim's runtime disc path.
 *
 * WHY raw ATA and not the DC BIOS GD syscall (vector 0x8c0000bc, the path the
 * Cleopatra port used): at runtime the loader places the Naomi RTOS kernel
 * slice over 0x8c000600-0x8c003800 (shim_iface.h KERNEL_DST/KERNEL_TOTAL_LEN,
 * docs/kb/phase4-conversion.md §Low-RAM placements), which is exactly the low
 * RAM the DC BIOS keeps its GD driver state and syscall vectors in. Every BIOS
 * syscall -- the GD entrypoint included -- is dead after handoff, so the shim
 * drives the G1 ATA task file itself. Polled, no IRQs.
 *
 * Primary sources for every register/protocol claim below (file:line), and
 * docs/kb/phase4-conversion.md §GD driver -- raw-ATA runtime path:
 *   ../flycast4naomi2dreamcast/core/hw/gdrom/gdromv3.h    register map, bits,
 *                                                         ATA/SPI command codes
 *   ../flycast4naomi2dreamcast/core/hw/gdrom/gdromv3.cpp  the state machine that
 *                                                         will actually run this
 *   ../cleopatra/tools/kos/kernel/arch/dreamcast/hardware/g1ata.c
 *                                                         KOS's own G1 task-file
 *                                                         driver (same map, same
 *                                                         polled PIO shape)
 * (KOS cdrom.c does NOT carry a packet-protocol reference: in this KOS it is a
 * BIOS-syscall driver -- syscall_gdrom_send_command/exec_server, cdrom.c:96-100.
 * The raw task-file reference in KOS is g1ata.c. See the KB section.)
 *
 * ponytail: PIO only. G1-DMA would be faster, but the shim mirrors the game's
 * G1 registers to RAM and a real DMA also needs its completion IRQ masked
 * (the Cleopatra lesson below) -- add it if real-hardware streaming stutters,
 * not before.
 */
#include "shim_iface.h"

#ifndef SHIM_CRC
#define SHIM_CRC 0      /* diagnostic: CRC every delivered cart read over serial */
#endif
#if SHIM_CRC
void scif_puts(const char *); void scif_puthex(unsigned int);
#endif

/* ---- pure splitter (host-tested: test/test_gd_math.c) -------------------
 * Decompose a (cart byte offset, byte length) request into a partial head, a
 * whole-sector body and a partial tail. Same members/order as the test's own
 * declaration -- keep the two in sync.
 *
 * fad is the ABSOLUTE fad of the first sector touched. The body starts at
 * fad + (head_len ? 1 : 0), the tail at that + body_secs (gd_read_cart walks
 * it that way). head_skip is the byte offset INTO the head sector; it is
 * nonzero exactly when the request is not sector-aligned, and a zero-length
 * request yields no head/body/tail at all (no I/O). */
struct plan { unsigned fad, head_skip, head_len, body_secs, tail_len; };

struct plan gd_plan(unsigned cart_off, unsigned len) {
    struct plan p;
    p.fad = CART_FAD + cart_off / 2048u;
    p.head_skip = cart_off % 2048u;
    p.head_len = 0;
    if (p.head_skip) {
        unsigned take = 2048u - p.head_skip;
        if (take > len) take = len;
        p.head_len = take;
        len -= take;
    }
    p.body_secs = len / 2048u;
    p.tail_len = len % 2048u;
    return p;
}

/* CRC-32/IEEE (reflected, poly 0xEDB88320) -- matches Python zlib.crc32 and
 * the fork's GDPIO/GDDMA probe. Diagnostic (SHIM_CRC) only. Caller passes the
 * alias it wants read (the hook passes P2 -- uncached, the C1 rule).
 * ponytail: bitwise ~50 cycles/byte; switch to a 1 KB table if diag legs drag. */
unsigned int shim_crc32(const void *p, unsigned len) {
    const unsigned char *s = (const unsigned char *)p;
    unsigned int c = 0xffffffffu;
    while (len--) {
        c ^= *s++;
        for (int k = 0; k < 8; k++)
            c = (c >> 1) ^ (0xedb88320u & (0u - (c & 1u)));
    }
    return ~c;
}

#ifndef HOST_TEST
/* ---- G1 ATA task file ---------------------------------------------------
 * Verified identical in the emulator that will run this code and in KOS's own
 * G1 driver: gdromv3.h:321-340 and g1ata.c:83-98.
 * Access widths: DATA is 16-bit -- real hardware needs it, and flycast logs a
 * complaint on any other size (it does not drop the access: gdromv3.cpp:1067-1068
 * read / :1137-1138 write); the rest are 8-bit task-file regs. */
#define GD_ALTSTAT  (*(volatile unsigned char  *)0xa05f7018)  /* R  status, no INTRQ ack (gdromv3.cpp:1054) */
#define GD_DATA     (*(volatile unsigned short *)0xa05f7080)  /* RW 16-bit data port */
#define GD_ERRREG   (*(volatile unsigned char  *)0xa05f7084)  /* R  error/sense (gdromv3.cpp:1099) */
#define GD_FEATURES (*(volatile unsigned char  *)0xa05f7084)  /* W  bit0 = DMA (gdromv3.h:75) */
#define GD_SECCNT   (*(volatile unsigned char  *)0xa05f7088)  /* W  transfer mode (gdromv3.h:329-330) */
#define GD_BCLO     (*(volatile unsigned char  *)0xa05f7090)  /* RW byte count low  (gdromv3.cpp:1058,1124) */
#define GD_BCHI     (*(volatile unsigned char  *)0xa05f7094)  /* RW byte count high (gdromv3.cpp:1062,1130) */
#define GD_DRVSEL   (*(volatile unsigned char  *)0xa05f7098)  /* RW device select */
#define GD_STATCMD  (*(volatile unsigned char  *)0xa05f709c)  /* R  status (ACKS INTRQ, gdromv3.cpp:1046) / W command */

/* Status bits (gdromv3.h:39-46) */
#define ST_CHECK 0x01
#define ST_DRQ   0x08
#define ST_BSY   0x80

#define ATA_SPI_PACKET 0xa0   /* gdromv3.h:347 */
#define SPI_CD_READ    0x30   /* gdromv3.h:366 */
#define GD_SECSZ       2048u  /* track04 data sectors (B5 GDI layout, make_gdi.py) */

/* Bounded waits: ~50M polls. Each poll is an uncached G1 register read (well
 * over 200 ns on real hardware), so the ceiling is >10 s -- far past the worst
 * GD seek, and it fires instead of hanging black. Flycast answers in one poll.
 * ponytail: no retry/soft-reset ladder yet (Cleopatra needed one only for the
 * BIOS command queue, which this path does not use). Add ATA_SOFT_RESET(0x08,
 * gdromv3.h:345) + retry here if real hardware ever reports a CHECK. */
#define GD_SPIN 50000000u

/* Raw status of the last hard failure: 0xda<site><ALTSTAT><ERROR>, painted by
 * cart.c's death screen. .data nonzero init per house style (the shim's .bss
 * is only zeroed by the loader's Tasks 10-12 block). */
unsigned int gd_last_err = 0xcafe0000;

/* ATA "400 ns settle": for up to 400 ns after a command write or the last word
 * of a data block, the status register still reads the PREVIOUS phase -- poll
 * DRQ too early and you sample the packet phase's DRQ as if it were the data
 * phase's, then read the FIFO before the drive filled it. The classic fix is
 * to discard four Alternate Status reads (each G1 access is >100 ns) before the
 * first meaningful poll. Free on flycast, where ALTSTAT is a pure read with no
 * side effects (gdromv3.cpp:1054-1056) and every transition is synchronous.
 * Load-bearing for gd_wait_drq below, which treats "BSY clear, DRQ clear" as a
 * finished command -- a stale pre-BSY sample would end the transfer early. */
static void gd_settle(void) {
    (void)GD_ALTSTAT; (void)GD_ALTSTAT; (void)GD_ALTSTAT; (void)GD_ALTSTAT;
}

static int gd_wait_clear(unsigned char mask) {
    for (unsigned i = 0; i < GD_SPIN; i++)
        if (!(GD_ALTSTAT & mask)) return 0;
    return -1;
}

/* Wait for the next DRQ block. 0 = data ready, 1 = the drive went idle without
 * offering data (command finished or FAILED -- read the verdict), -1 = timeout.
 *
 * Ready means BSY clear AND DRQ set: ATA status bits are not valid while BSY is
 * asserted, and KOS polls the same pair (g1ata.c:193-195).
 *
 * The idle exit is what keeps a failed command cheap: a rejected packet never
 * enters a data phase at all -- flycast lands it in gds_procpacketdone with
 * CHECK=1, DRQ=0 and a sense key (gdromv3.cpp:1030-1037, :282-301). Waiting for
 * a DRQ that will never come would burn the whole 50M-poll budget and report a
 * stall, throwing away the drive's own verdict; instead we fall straight through
 * to the status read. */
static int gd_wait_drq(void) {
    gd_settle();
    for (unsigned i = 0; i < GD_SPIN; i++) {
        unsigned char st = GD_ALTSTAT;
        if (st & ST_BSY) continue;
        return (st & ST_DRQ) ? 0 : 1;
    }
    return -1;
}

/* One record per failure site: site number in the return value (negative), in
 * gd_last_err's high half, and in SHIM_ERR's code -- so a serial log, a death
 * screen and a memory watch all name the same spot. */
#define GD_E_IDLE   1   /* drive never went idle before the command */
#define GD_E_PACKET 2   /* PACKET accepted but DRQ for the 12 command bytes never came */
#define GD_E_DATA   3   /* DRQ for a data block never came (seek/read failed, or media) */
#define GD_E_COUNT  4   /* drive offered an impossible byte count for a block */
#define GD_E_END    5   /* transfer done but the drive never went idle */
#define GD_E_CHECK  6   /* drive raised CHECK: ERROR register holds the sense key */
#define GD_E_ARG    7   /* caller bug: null/oversized request */
#define GD_E_RANGE  8   /* gd_read_cart: request runs past CART_SIZE */

static int gd_fail(unsigned site, unsigned fad) {
    unsigned st = GD_ALTSTAT, er = GD_ERRREG;
    gd_last_err = 0xda000000u | (site << 16) | ((st & 0xffu) << 8) | (er & 0xffu);
#if !GD_LOADER_BUILD
    /* Same field order as util.c shim_die (code written last, magic before it).
     * Code 0x6<site> is this driver's own; cart.c's gd_or_die then overwrites
     * the record with shim_die(4, fad, gd_last_err) for the red screen.
     * NOT in the loader build: KOS's naomi LOAD_OFFSET is 0x8c010000 == the
     * shim's SHIM_BASE, so SHIM_ERR (0x8c014000) sits inside the running
     * loader's own image -- writing it there would corrupt the loader that is
     * about to draw the error. The loader reads the negative return value and
     * gd_last_err instead (loader/main.c rehearsal). */
    volatile unsigned int *e = P2(SHIM_ERR);
    e[1] = fad; e[2] = gd_last_err; e[3] = 0xdeadcafe; e[0] = 0x60u | site;
#else
    (void)fad;
#endif
    return -(int)site;
}

/* One-time hardware setup: mask the GD-ROM command interrupt in all three ASIC
 * IRQ levels. Every DRQ block and every command completion raises it
 * (gdromv3.cpp:237,297); it is SB_ISTEXT bit 0 (holly_intc.h:43
 * "holly_GDROM_CMD = holly_ext | 0x00"), so the masks are SB_IML2/4/6EXT =
 * 0x5f6914/24/34 (sb.h:87,94,101). The game we hand control to has its
 * Naomi-legacy ASIC handler armed and no concept of a GD-ROM drive; Cleopatra
 * hit exactly this class with the GD-DMA interrupt (ISTNRM bit 14) on real
 * hardware, where masking it was what made cart streaming work
 * (../cleopatra/shims/src/gd.c, its G1-DMA read path). We ack the interrupt
 * anyway by reading GD_STATCMD at the end of every command (gdromv3.cpp:1047
 * asic_CancelInterrupt), so nothing stays latched.
 * Shim only: in the loader, KOS owns the interrupt policy (it programs the IML
 * registers from its own event table, cdrom.c:805-813) and nothing masks the
 * game's handler because there is no game yet -- the loader's rehearsal has no
 * reason to touch them.
 * .data sentinel, not .bss (house style -- see gd_last_err). */
#if !GD_LOADER_BUILD
static unsigned gd_inited = 0xff;
static void gd_hw_init(void) {
    if (gd_inited != 0xff) return;
    gd_inited = 0;
    *(volatile unsigned int *)0xa05f6914 &= ~1u;
    *(volatile unsigned int *)0xa05f6924 &= ~1u;
    *(volatile unsigned int *)0xa05f6934 &= ~1u;
}
#else
#define gd_hw_init() ((void)0)
#endif

/* Read `sectors` 2048-byte data sectors starting at absolute `fad` into `dst`.
 * 0 = ok, negative = failure site (also in SHIM_ERR + gd_last_err).
 *
 * dst is ALWAYS written through its P2 (uncached) alias -- the C1 lesson: the
 * game reads streamed cart bytes uncached or hands them to hardware DMA, so
 * nothing may sit dirty in the D-cache over them (cart.c cart_read carries the
 * full reasoning). P2ADDR is idempotent, so any alias may be passed in, but
 * note the direction this forces on the CALLER: whatever reads those bytes back
 * must read them uncached too (P2, or a dcache_inval first). A P1 read of a
 * buffer this function filled can hit a stale cache line -- that is the whole
 * C1 bug. cart.c's bounce and the loader's rehearsal buffer both follow it. */
int gd_read_fad(unsigned fad, void *dst, unsigned sectors) {
    /* 0x1fffff caps both the packet's 24-bit count field and `sectors * 2048`
     * below (4 GB); the whole cart image is 122,720 sectors. */
    if (!sectors || !dst || sectors > 0x1fffffu) return gd_fail(GD_E_ARG, fad);
    gd_hw_init();

    /* Device select: the GD drive is the master. Flycast keeps the fixed high
     * bits and takes bit 4 as the device number (gdromv3.cpp:1168; its reset
     * default is 0xa0, :1410), and returns 0 from the status register while a
     * slave is selected (:1048-1050) -- which would look exactly like a hung
     * drive. Write the canonical master value. */
    GD_DRVSEL = 0xa0;
    if (gd_wait_clear(ST_BSY | ST_DRQ)) return gd_fail(GD_E_IDLE, fad);

    GD_FEATURES = 0;                    /* PIO, not DMA (gdromv3.cpp:770 tests bit 0) */
    GD_SECCNT = 0;                      /* transfer mode: unused for a packet read */
    GD_BCLO = (unsigned char)(GD_SECSZ & 0xffu);   /* byte-count limit per DRQ block */
    GD_BCHI = (unsigned char)(GD_SECSZ >> 8);
    GD_STATCMD = ATA_SPI_PACKET;
    /* Either failure mode lands here: no DRQ within the budget, or the drive
     * rejecting PACKET outright (idle with CHECK) -- gd_fail records ALTSTAT +
     * ERROR either way. */
    if (gd_wait_drq()) return gd_fail(GD_E_PACKET, fad);

    /* The 12-byte SPI packet, written as 6 little-endian 16-bit words -- the
     * only shape the drive accepts (flycast collects exactly 6 words into the
     * u8/u16 union and then executes, gdromv3.cpp:1139-1145), and the byte
     * order KOS uses for every task-file word (g1ata.c:541 `ptr[0] | ptr[1]<<8`).
     *   b0    0x30 SPI_CD_READ                                (gdromv3.cpp:747)
     *   b1    0x20: bit5 "data" = 1, everything else 0 -> 2048-byte data
     *         sectors and bit0 prmtype=0 = FAD (not MSF) addressing
     *         (bit layout gdromv3.h:148-155; sector-type selection
     *         gdromv3.cpp:753-761 -- data=1 alone falls through to 2048;
     *         GetFAD(&b[2], prmtype) gdromv3.cpp:762 + :357-363)
     *   b2-b4 start FAD, MSB first                            (gdromv3.cpp:362)
     *   b5-b7 zero
     *   b8-b10 sector count, MSB first                        (gdromv3.cpp:764)
     *   b11   zero
     * Brief-vs-source: the brief sketched b1 as "flags(data=1)" without a value
     * and put the count at b[8..10] -- both confirmed; the count field is what
     * separates 0x30 from 0x31 (SPI_CD_READ2 reads it as a 16-bit b[6..7],
     * gdromv3.cpp:766), so the command byte and the count field must agree. */
    GD_DATA = (unsigned short)(SPI_CD_READ | (0x20u << 8));
    GD_DATA = (unsigned short)(((fad >> 16) & 0xffu) | (((fad >> 8) & 0xffu) << 8));
    GD_DATA = (unsigned short)(fad & 0xffu);
    GD_DATA = 0;
    GD_DATA = (unsigned short)(((sectors >> 16) & 0xffu) | (((sectors >> 8) & 0xffu) << 8));
    GD_DATA = (unsigned short)(sectors & 0xffu);

    /* Data phase. The drive delivers the sectors in DRQ blocks and announces
     * each block's size in the byte-count registers -- do NOT assume one block
     * per sector: flycast hands over up to 31 sectors (63,488 B) at a time
     * (gdromv3.cpp:255-266, PioBuffer::Capacity 64 KB / 2048) and sets the byte
     * count from the buffer size (:229), while real hardware honours the
     * 2048-byte limit written above. Reading the count per block is correct for
     * both. Flycast decrements it by 2 on every data read (:1079), so it is
     * sampled once, at the top of the block. */
    unsigned char *p = (unsigned char *)P2ADDR((unsigned long)dst);
    int odd = (int)((unsigned long)p & 1u);
    unsigned left = sectors * GD_SECSZ;
    while (left) {
        int wait = gd_wait_drq();
        if (wait < 0) return gd_fail(GD_E_DATA, fad);
        if (wait > 0) break;            /* drive ended the command early: verdict below */
        unsigned n = ((unsigned)GD_BCHI << 8) | (unsigned)GD_BCLO;
        if (!n || (n & 1u) || n > left) return gd_fail(GD_E_COUNT, fad);
        left -= n;
        if (odd) {
            /* SH-4 faults on a 16-bit store to an odd address, and an unaligned
             * body dest is reachable (cart_read advances the dest by a partial
             * head). Split the word instead of bouncing the whole block. */
            for (n >>= 1; n; n--) {
                unsigned short w = GD_DATA;
                *p++ = (unsigned char)w;
                *p++ = (unsigned char)(w >> 8);
            }
        } else {
            unsigned short *q = (unsigned short *)p;
            for (n >>= 1; n; n--) *q++ = GD_DATA;
            p = (unsigned char *)q;
        }
    }

    if (gd_wait_clear(ST_BSY | ST_DRQ)) return gd_fail(GD_E_END, fad);
    /* Read the real status register, not ALTSTAT: this is the read that acks
     * INTRQ (gdromv3.cpp:1046-1047) and carries the command's verdict. */
    if (GD_STATCMD & ST_CHECK) return gd_fail(GD_E_CHECK, fad);
    /* Ended early with CHECK clear: the drive simply stopped delivering. Short
     * data is still a failed read -- never report success on a partial buffer. */
    if (left) return gd_fail(GD_E_DATA, fad);
    return 0;
}

/* Cart-image read: byte offset -> FAD, with the partial head/tail bounced
 * through SHIM_BOUNCE. 0 = ok, negative = failure site.
 *
 * Both the destination and the bounce buffer are addressed through P2
 * (uncached): mixing a P2 write with a P1 read of the same bytes is the C1
 * bug in miniature, and the head/tail copies are at most 2 KB each.
 * Unaligned destinations need no bounce -- gd_read_fad splits the words
 * itself (see its data phase).
 * Compiled out of the loader build: SHIM_BOUNCE lives inside the loader's own
 * image (see gd_fail), so this must be unlinkable there, not merely unused.
 * The loader rehearses gd_read_fad only. */
#if !GD_LOADER_BUILD
int gd_read_cart(unsigned cart_off, void *dst, unsigned len) {
    if (!len) return 0;
    if (cart_off > (unsigned)CART_SIZE || len > (unsigned)CART_SIZE - cart_off)
        return gd_fail(GD_E_RANGE, cart_off);

    struct plan pl = gd_plan(cart_off, len);
    unsigned char *d = (unsigned char *)P2ADDR((unsigned long)dst);
    unsigned char *b = (unsigned char *)P2ADDR(SHIM_BOUNCE);
    unsigned fad = pl.fad, i;
    int r;

    if (pl.head_len) {
        if ((r = gd_read_fad(fad, b, 1)) < 0) return r;
        for (i = 0; i < pl.head_len; i++) d[i] = b[pl.head_skip + i];
        d += pl.head_len;
        fad++;
    }
    if (pl.body_secs) {
        if ((r = gd_read_fad(fad, d, pl.body_secs)) < 0) return r;
        d += pl.body_secs * GD_SECSZ;
        fad += pl.body_secs;
    }
    if (pl.tail_len) {
        if ((r = gd_read_fad(fad, b, 1)) < 0) return r;
        for (i = 0; i < pl.tail_len; i++) d[i] = b[i];
    }
#if SHIM_CRC
    scif_puts("SHIMCRC o="); scif_puthex(cart_off);
    scif_puts(" l=");        scif_puthex(len);
    scif_puts(" c=");        scif_puthex(shim_crc32(
                                 (const void *)P2ADDR((unsigned long)dst), len));
    scif_puts("\n");
#endif
    return 0;
}
#endif /* !GD_LOADER_BUILD */
#endif /* !HOST_TEST */

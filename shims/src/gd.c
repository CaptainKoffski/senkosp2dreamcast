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
#ifndef SHIM_TIME
#define SHIM_TIME 0     /* diagnostic: TMU0-stamped SHIMTIME line per cart read
                         * (phase-7 T2 profiling; digest: parse_shimtime.py) */
#endif
#ifndef SHIM_FRAMEGAP
#define SHIM_FRAMEGAP 0 /* diagnostic: count gd_read_cart calls for main.c's
                         * frame-gap HUD (phase-7 T2b dwell-hitch leg) */
#endif
#if SHIM_CRC || SHIM_TIME || SHIM_PF_VERIFY
void scif_puts(const char *); void scif_puthex(unsigned int);
#endif
#if SHIM_TIME
/* SH-4 TMU0 -- the game's own timer, read-only here. The game reprograms it
 * to TCR0=2 (P/64 = 781.25 kHz), TCOR0=TCNT0=0xFFFFFFFF: a free-running
 * down-counter, ~92 min wrap (docs/kb/phase7-polishing.md §T1 measurements,
 * TMU0 verdict; register map ../flycast4naomi2dreamcast/core/hw/sh4/
 * sh4_mmr.h:324-325). TCR0 is echoed to the parser so the tick rate is
 * measured, not assumed. */
#define TIME_TCNT0 (*(volatile unsigned int   *)0xffd8000c)
#define TIME_TCR0  (*(volatile unsigned short *)0xffd80010)
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

/* ---- prefetch window math (pure, host-tested: test/test_gd_math.c) -------
 * The T3 ring holds the cart-byte window [lo, hi) at ring index
 * (byte & (PF_RING_SZ-1)) -- PF_RING_SZ is a power of two, so the mapping
 * needs no anchor state and any window <= PF_RING_SZ maps injectively.
 * Returns 1 and fills `cut` when [off, off+len) lies whole inside the
 * window: idx = ring index of off, first = bytes up to the ring edge (a
 * wrapped request is copied in two segments -- `first` from idx, then
 * len-first from index 0). Guard order is load-bearing: off <= hi must be
 * established before hi - off is formed (unsigned underflow would turn a
 * far-past-window off into a "hit"), and len == 0 is a miss by fiat
 * (gd_read_cart returns before ever asking). */
struct pf_cut { unsigned idx, first; };

int pf_hit_plan(unsigned lo, unsigned hi, unsigned off, unsigned len,
                struct pf_cut *c) {
    if (!len || off < lo || off > hi || hi - off < len) return 0;
    c->idx = off & (PF_RING_SZ - 1u);
    c->first = PF_RING_SZ - c->idx;
    if (c->first > len) c->first = len;
    return 1;
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

/* Hardware-round forensics, painted by shim_die below the code/a/b rows
 * (util.c). [0] idle-gap recoveries survived (cumulative -- the count of
 * times the pre-round-1 code would have died, see gd_wait_drq), [1] max poll
 * iterations any successful wait needed (cumulative -- measures GDEMU's
 * block-staging latency), [2] DRQ blocks this read, [3]/[4] min/max announced
 * byte count this read, [5] bytes drained off the drive after a GD_E_END
 * (how far ahead of us it really was), [6] spare, [7] .data-forcing tag
 * (nonzero init per house style, same reason as gd_last_err). */
unsigned int gd_diag[8] = {0, 0, 0, 0, 0, 0, 0, 0xd1a6d1a6u};

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

/* HUD poll heartbeat: same idea as Cleopatra's gd.c row-134 climbing mark
 * (../cleopatra/shims/src/gd.c:47 -- "climbing = polling, frozen = wedged
 * inside a syscall") but through this port's shim_mark slot HUD instead of a
 * raw hex row, since gd.c here has no SHIM_GD_DIAG of its own. A live drive
 * blinks the slot every 64K polls; a wedge freezes it on whichever color it
 * last painted -- exactly the real-HW failure mode flycast can't reproduce
 * (it answers in one poll, so this code path never spins there). Slot 24:
 * every slot 0-23 is already claimed by another HUD user (cart.c, main.c --
 * see docs/kb/phase5-hardware.md §HUD kit for the full map), so this is the
 * first free one, row 2 (util.c shim_mark: slot>=16 = second row).
 * #if !GD_LOADER_BUILD: shim_mark lives in util.c, which the loader's gd.o
 * link does NOT include (loader/Makefile OBJS has no util.o) -- same reason
 * gd_fail's SHIM_ERR store below is loader-gated. */
#if !GD_LOADER_BUILD
void shim_mark(unsigned int slot, unsigned short color);   /* util.c: breadcrumb HUD */
#define GD_HEARTBEAT(i) \
    do { if (!((i) & 0xffffu))                   /* every 64K polls: cheap, visible */ \
             shim_mark(24, ((i) & 0x10000u) ? 0x07e0 : 0x001f); } while (0)  /* green<->blue */
/* Slot 25 (next free after Task 8's 24, §HUD kit): sticky yellow = at least
 * one mid-transfer idle window was survived this session, i.e. the
 * pre-round-1 code would have red-screened by now. */
#define GD_RECOVERY_MARK() shim_mark(25, 0xffe0)
#else
#define GD_HEARTBEAT(i) ((void)0)
#define GD_RECOVERY_MARK() ((void)0)
#endif

static int gd_wait_clear(unsigned char mask) {
    for (unsigned i = 0; i < GD_SPIN; i++) {
        GD_HEARTBEAT(i);
        if (!(GD_ALTSTAT & mask)) return 0;
    }
    return -1;
}

/* Wait for the next DRQ block. 0 = data ready, 1 = the drive ended the command
 * with a verdict waiting (CHECK set -- read the status register), -1 = timeout.
 *
 * Ready means BSY clear AND DRQ set: ATA status bits are not valid while BSY is
 * asserted, and KOS polls the same pair (g1ata.c:193-195).
 *
 * Hardware round 1 (docs/kb/phase5-hardware.md §Hardware rounds): the old
 * version returned 1 on ANY idle sample. On GDEMU that is a race: between DRQ
 * blocks its firmware stages the next chunk, and status can float idle
 * (BSY=0, DRQ=0) for longer than gd_settle covers. The loop then broke
 * mid-transfer with bytes still owed, and the end-of-command wait timed out
 * against the re-raised DRQ of the block the drive went on to offer --
 * GD_E_END, ALTSTAT 0x58 (DRDY|DSC|DRQ), at three unrelated cart offsets,
 * probabilistic per block boundary. Flycast cannot exhibit the window: its
 * status transitions are synchronous with the last data-register read
 * (gdromv3.cpp:1079), which is why every emulator leg was green.
 *
 * Policy now: idle is trusted only when CHECK is set -- the one state a
 * rejected command actually presents (flycast gds_procpacketdone: CHECK=1,
 * DRQ=0, sense key set, gdromv3.cpp:1030-1037, :282-301; both call sites owe
 * data at every call, so a CHECK-less idle mid-command has no legitimate
 * reading). Idle without CHECK keeps polling; DRQ reappearing resumes the
 * transfer (counted in gd_diag[0], sticky slot-25 mark -- each one is a boot
 * the old code would have red-screened). A genuinely dead drive still fails,
 * one full GD_SPIN (~10 s) slower, on a path that is fatal either way. The
 * same policy closes the packet-accept race the settle comment above
 * describes: a stale pre-BSY idle sample now waits instead of dying. */
static int gd_wait_drq(void) {
    gd_settle();
    unsigned gap = 0;
    for (unsigned i = 0; i < GD_SPIN; i++) {
        GD_HEARTBEAT(i);
        unsigned char st = GD_ALTSTAT;
        if (st & ST_BSY) continue;
        if (st & ST_DRQ) {
            if (gap) { gd_diag[0]++; GD_RECOVERY_MARK(); }
            if (i > gd_diag[1]) gd_diag[1] = i;
            return 0;
        }
        if (st & ST_CHECK) return 1;
        gap = 1;
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
    gd_diag[2] = 0; gd_diag[3] = 0xffffffffu; gd_diag[4] = 0; gd_diag[5] = 0;
    while (left) {
        int wait = gd_wait_drq();
        if (wait < 0) return gd_fail(GD_E_DATA, fad);
        if (wait > 0) break;            /* drive ended with CHECK: verdict below */
        unsigned n = ((unsigned)GD_BCHI << 8) | (unsigned)GD_BCLO;
        if (!n || (n & 1u) || n > left) return gd_fail(GD_E_COUNT, fad);
        gd_diag[2]++;
        if (n < gd_diag[3]) gd_diag[3] = n;
        if (n > gd_diag[4]) gd_diag[4] = n;
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

    if (gd_wait_clear(ST_BSY | ST_DRQ)) {
        /* Forensics before dying: pull whatever the drive still holds and
         * count it (gd_diag[5], painted on the death screen). The leftover
         * size says HOW the accounting desynced: a few whole sectors = block
         * boundary, odd/huge = counter desync. Fatal path only. */
        for (unsigned i = 0; i < GD_SPIN && gd_diag[5] < 0x400000u; i++) {
            unsigned char st = GD_ALTSTAT;
            if (st & ST_BSY) continue;
            if (!(st & ST_DRQ)) break;
            (void)GD_DATA; gd_diag[5] += 2;
        }
        return gd_fail(GD_E_END, fad);
    }
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
int gd_sys_read_sectors(void *dst, unsigned fad, unsigned n);
/* Phase 7 T1 dispatch: backend chosen once by the loader's rehearsal probe
 * (main.c), 0 = raw ATA / 1 = BIOS-syscall (DreamShell isoldr). The raw
 * path below this line is untouched. */
static int gd_read(unsigned fad, void *dst, unsigned secs) {
    if (P2(SHIM_STATE)[SHIM_STATE_GD_BACKEND])
        return gd_sys_read_sectors(dst, fad, secs);
    return gd_read_fad(fad, dst, secs);
}

/* ---- T3 prefetch ring (docs/kb/phase7-polishing.md §T3) ------------------
 * The game's steady streaming is kick -> wait in one call chain, and the
 * shim only learns of a kick when the wait hook fires -- so the blocking
 * drip read (T2b: 15 ms GDEMU / ~50 ms serial-SD, one hitch per second on
 * the dwell screen and stage 8) cannot be deferred, only PREDICTED. The T2
 * log shows the drip is perfectly sequential (every read starts where the
 * previous ended), so: a 64 KB ring at PF_RING_BASE (stolen from the game
 * heap's bottom, reloc entry "0x13ae68") chases the stream one sector per
 * frame from shim_maple_service, and a request whole inside the window is
 * served as a RAM copy instead of a disc read. A miss is served exactly as
 * before (no regression path) and re-aims the window at the request's end.
 *
 * Never fatal by design: prefetch is speculative I/O, so every failure
 * DISARMS it (pf_state=0 sticky, site in pf_stat[3]) instead of dying --
 * including a slice read error, whose gd_fail record (SHIM_ERR/gd_last_err)
 * is left behind as forensics but not acted on. Arming is gated on two
 * runtime tripwires (pf_armed): the heap-base pool word must read back
 * PATCHED (else the game's heap still covers the ring) and the boot must be
 * main-mode (the test image's heap is deliberately unpatched). cart.c's
 * fence additionally disarms on any game dest overlapping the ring.
 * Known ceiling, ponytail: one window -- two interleaved streams would
 * ping-pong reset it and degrade to exactly today's blocking behavior
 * (visible as pf_stat[1] misses climbing with [0] flat); second window only
 * if a leg ever shows that. */
#if SHIM_PREFETCH
static unsigned pf_lo = 0x800, pf_hi = 0x800; /* window [lo,hi), cart bytes; .data
                                          * nonzero + sector-aligned (fill
                                          * math relies on hi's alignment) */
static unsigned pf_state = 0xa5;     /* 0xa5 unprobed / 1 armed / 0 sticky off */
unsigned int pf_stat[4] = {0, 0, 0, 0x9f9f9f9f}; /* [0] hits [1] misses [2] fills
                                         * [3] disarm site (sentinel = armed);
                                         * painted by main.c's FRAMEGAP HUD */

static int pf_armed(void) {
    if (pf_state == 1) return 1;
    if (pf_state == 0) return 0;
    if (*P2(PF_HEAP_BASE_WORD) != PF_HEAP_BASE_NEW) { pf_state = 0; pf_stat[3] = 1; return 0; }
    if (P2(SHIM_STATE)[0] != 0)                     { pf_state = 0; pf_stat[3] = 2; return 0; }
    pf_state = 1;
    return 1;
}

/* cart.c fence: a game DMA dest overlapping the ring (site 4). */
void gd_prefetch_off(unsigned site);
void gd_prefetch_off(unsigned site) { pf_state = 0; pf_stat[3] = site; }

/* Both sides P2 (uncached, the C1 rule end to end: gd_read filled the ring
 * through P2, the game reads its dest uncached). u32 fast path when
 * co-aligned -- every observed stream is sector-aligned to a 32-aligned
 * dest; the byte tail is correctness for the rest. */
static void pf_copy(unsigned char *d, const unsigned char *s, unsigned n) {
    if ((((unsigned long)d | (unsigned long)s) & 3u) == 0)
        for (; n >= 4; n -= 4) { *(unsigned *)(void *)d = *(const unsigned *)(const void *)s; d += 4; s += 4; }
    while (n--) *d++ = *s++;
}

/* One sector per frame, called from shim_maple_service (main.c). Bounded:
 * ~0.7 ms on GDEMU PIO, ~2.6 ms on the serial-SD dongle -- inside frame
 * slack, and 120 KB/s of fill against the drip's ~37 KB/s consumption, so
 * the window stays ahead after one miss. Never runs while a blocking read
 * is in flight (hooks do not nest; loads simply starve the tick). */
void gd_prefetch_tick(void);
void gd_prefetch_tick(void) {
    if (!pf_armed()) return;
    if (pf_hi - pf_lo >= PF_RING_SZ) return;            /* window full */
    if (pf_hi >= (unsigned)CART_SIZE) return;                /* image end */
    unsigned char *slot = (unsigned char *)
        P2ADDR(PF_RING_BASE + (pf_hi & (PF_RING_SZ - 1u)));
    if (gd_read(CART_FAD + pf_hi / GD_SECSZ, slot, 1) < 0) {
        gd_prefetch_off(3);         /* speculative -- disarm, never die */
        return;
    }
    pf_hi += GD_SECSZ;
    pf_stat[2]++;
}

#if SHIM_PF_VERIFY
/* Control instrument: re-read every served hit from disc through the bounce
 * and byte-compare against what the ring delivered. One PFVFY line per hit;
 * any mismatch disarms (site 5). Emulator legs only -- doubles hit traffic. */
static void pf_verify(unsigned off, const unsigned char *dst_p2, unsigned len) {
    unsigned char *b = (unsigned char *)P2ADDR(SHIM_BOUNCE);
    unsigned pos = off & ~(GD_SECSZ - 1u), bad = 0;
    while (pos < off + len) {
        if (gd_read(CART_FAD + pos / GD_SECSZ, b, 1) < 0) { bad = 0xffffffffu; break; }
        unsigned s = pos > off ? pos : off;
        unsigned e = pos + GD_SECSZ < off + len ? pos + GD_SECSZ : off + len;
        for (unsigned i = s; i < e; i++)
            if (b[i - pos] != dst_p2[i - off]) bad++;
        pos += GD_SECSZ;
    }
    scif_puts("PFVFY o="); scif_puthex(off);
    scif_puts(" l=");      scif_puthex(len);
    scif_puts(" bad=");    scif_puthex(bad);
    scif_puts("\n");
    if (bad) gd_prefetch_off(5);
}
#endif
#endif /* SHIM_PREFETCH */

#if SHIM_FRAMEGAP
unsigned int gd_calls = 1;      /* .data nonzero (house style); main.c paints it */
#endif

int gd_read_cart(unsigned cart_off, void *dst, unsigned len) {
    if (!len) return 0;
#if SHIM_FRAMEGAP
    gd_calls++;
#endif
    if (cart_off > (unsigned)CART_SIZE || len > (unsigned)CART_SIZE - cart_off)
        return gd_fail(GD_E_RANGE, cart_off);

    struct plan pl = gd_plan(cart_off, len);
    unsigned char *d = (unsigned char *)P2ADDR((unsigned long)dst);
    unsigned char *b = (unsigned char *)P2ADDR(SHIM_BOUNCE);
    unsigned fad = pl.fad, i;
    int r;
#if SHIM_TIME
    unsigned t_in = TIME_TCNT0;
#endif

#if SHIM_PREFETCH
    /* T3 hit path: the whole request is in the ring window -- serve it as a
     * RAM copy (the C1 rule holds: ring filled via P2, copied out via P2),
     * consume the window up to the request's end, and fall through to the
     * same TIME/CRC tail as a real read (a hit's SHIMTIME d= is the copy
     * cost; a CRC leg validates ring bytes for free). */
    struct pf_cut cut;
    if (pf_armed() && pf_hit_plan(pf_lo, pf_hi, cart_off, len, &cut)) {
        pf_copy(d, (const unsigned char *)P2ADDR(PF_RING_BASE + cut.idx), cut.first);
        if (cut.first < len)
            pf_copy(d + cut.first,
                    (const unsigned char *)P2ADDR(PF_RING_BASE), len - cut.first);
        pf_lo = cart_off + len;
        pf_stat[0]++;
#if SHIM_PF_VERIFY
        pf_verify(cart_off, d, len);
#endif
        goto pf_served;
    }
#endif

    if (pl.head_len) {
        if ((r = gd_read(fad, b, 1)) < 0) return r;      /* head */
        for (i = 0; i < pl.head_len; i++) d[i] = b[pl.head_skip + i];
        d += pl.head_len;
        fad++;
    }
    if (pl.body_secs) {
        if ((r = gd_read(fad, d, pl.body_secs)) < 0) return r;  /* body */
        d += pl.body_secs * GD_SECSZ;
        fad += pl.body_secs;
    }
    if (pl.tail_len) {
        if ((r = gd_read(fad, b, 1)) < 0) return r;      /* tail */
        for (i = 0; i < pl.tail_len; i++) d[i] = b[i];
    }
#if SHIM_PREFETCH
    if (pf_state == 1) {            /* miss: re-aim the window at the stream's
                                     * new position, sector-rounded DOWN so a
                                     * chained unaligned stream still lands
                                     * inside next time (<= 2047 B refetched) */
        pf_stat[1]++;
        pf_lo = pf_hi = (cart_off + len) & ~(GD_SECSZ - 1u);
    }
pf_served:;
#endif
#if SHIM_TIME
    {
        /* Exit stamp sampled BEFORE any serial output (one line is ~4 ms at
         * 115200 -- lighter than the hardware-proven SHIMCRC instrument, which
         * adds ~50 cycles/byte of CRC on top of its line). d = entry - exit:
         * down-counter, unsigned wrap-safe. Failed reads print nothing (they
         * halt loud already). */
        unsigned t_out = TIME_TCNT0;
        static unsigned short tcr_seen = 0xffffu;  /* .data nonzero per house
                                                    * style; 0xffff is not a
                                                    * readable TCR0 value
                                                    * (bits 15:9 read 0) */
        unsigned short tcr = TIME_TCR0;
        if (tcr != tcr_seen) {
            tcr_seen = tcr;
            scif_puts("SHIMTIME tcr="); scif_puthex(tcr); scif_puts("\n");
        }
        scif_puts("SHIMTIME o="); scif_puthex(cart_off);
        scif_puts(" l=");         scif_puthex(len);
        scif_puts(" s=");         scif_puthex(t_in);
        scif_puts(" d=");         scif_puthex(t_in - t_out);
        scif_puts("\n");
    }
#endif
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

/* T10b: transparent LZ4 pak delivery. Included by gd.c (immediately before
 * gd_read_cart) under SHIM_LZ4 && SHIM_G1DMA, so it uses gd.c's static
 * helpers and register defines without widening any interface -- and so a
 * knob-off build's preprocessed gd.c is byte-identical (gate 5).
 *
 * One ATA PACKET DMA lands the whole compressed blob right-justified inside
 * the game's own destination buffer; the CPU then inflates chunk i (64 KB
 * plain) into dst + i*64K while the engine is still delivering chunk i+1.
 * In-place is safe because mastering enforces align32(csize) <= usize per
 * chunk (spec §Safety invariants) -- except for the innermost kept-LZ4
 * chunk, where the in-place margin is structurally absent: that one is
 * flagged LZ4PAK_BOUNCE and decoded into the disjoint 64 KB T3 prefetch
 * ring, then copied home (spec §Runtime read path, amended 2026-09-23).
 *
 * The DMA arm/kick/epilogue sequences MIRROR gd_read_fad's DMA path
 * (gd.c) rather than share extracted helpers -- extraction would change
 * knob-off codegen. KEEP IN SYNC with gd_read_fad; each mirrored block
 * cites its source lines.
 *
 * Spec: docs/superpowers/specs/2026-09-23-t10b-lz4-pak-load-design.md
 * (in-place invariant + margin proof there; enforced by pack_paks). */
#include "lz4_lay.h"
#include "lz4pak_map.h"          /* generated: build/ via -I../build */

int LZ4_decompress_safe(const char *src, char *dst, int csz, int usz); /* lz4_dec.o */

#ifndef SHIM_LZ4CRC
#define SHIM_LZ4CRC 0
#endif
#if SHIM_LZ4CRC
void scif_puts(const char *); void scif_puthex(unsigned int);
#endif

#define GD_E_LZ4 10   /* decode/CRC failure on a compressed chunk (fell back) */

#if SHIM_TIME
/* T10b diagnostic (operator-authorized 2026-09-23): split a served window's
 * in-driver time into link-wait ticks (decoder ahead, spinning on GDLEND)
 * vs CPU-work ticks (decode + copies + ocbp). Printed as one SHIMLZ4 row
 * by gd_read_cart's SHIMTIME tail, same TMU0 ticks as its d= field.
 * Nonzero inits keep them in .data (house style -- no .bss clear); both
 * counters are re-zeroed per serve and lz4_served is a sentinel
 * (1 = row pending, else idle), so load-time values are never trusted. */
static unsigned lz4_t_wait = 1, lz4_t_work = 1;
static unsigned lz4_served = 2;
#endif

/* Wait for the DMA frontier to cover `target` bytes. Progress-rearmed
 * budget, same policy as gd_read_fad's GDST poll (gd.c:481-486): only a
 * STALLED GDLEND burns budget; GDST clearing ends the transfer either way
 * (it clears only when GDLEND reaches GDLEN, gdromv3.cpp:1333-1336), so
 * re-read GDLEND on that exit before calling it short. */
static int lz4_wait_lend(unsigned target) {
    unsigned seen = 0;
    for (unsigned i = 0; i < GD_SPIN; i++) {
        GD_HEARTBEAT(i);
        unsigned now = SB_GDLEND;
        if (now >= target) return 0;
        if (!(SB_GDST & 1u)) return SB_GDLEND >= target ? 0 : -1;
        if (now != seen) { seen = now; i = 0; }
    }
    return -1;
}

/* Write-back + invalidate a finished output chunk so the game's uncached
 * reads (the C1 rule, cart.c) see it. Both bounds are 32-multiples:
 * out_off is a 64 K multiple, usize a 32-multiple (pack_paks asserts). */
static void lz4_ocbp(unsigned phys, unsigned n) {
    for (unsigned a = phys | 0x80000000u, e = a + n; a < e; a += 32u)
        __asm__ __volatile__("ocbp @%0" : : "r"(a) : "memory");
}

/* Stored chunk: forward copy. src/dst both 32-aligned (layout), n a
 * 4-multiple, dst <= src by the layout invariant -- overlap-safe forward. */
static void lz4_copy32(unsigned char *d, const unsigned char *s, unsigned n) {
    if (d == s) return;
    for (; n >= 4; n -= 4) {
        *(unsigned *)(void *)d = *(const unsigned *)(const void *)s;
        d += 4; s += 4;
    }
}

/* Drain the engine + settle the drive after a mid-stream failure, so the
 * follow-up read (fallback or death screen) meets an idle drive. The
 * remaining bytes are ours to discard -- bounded by the transfer itself. */
static int lz4_settle_engine(void) {
    unsigned i, seen = 0;
    for (i = 0; i < GD_SPIN && (SB_GDST & 1u); i++) {
        GD_HEARTBEAT(i);
        unsigned now = SB_GDLEND;
        if (now != seen) { seen = now; i = 0; }
    }
    *(volatile unsigned int *)0xa05f6900 = 1u << 14;    /* ack GD-DMA status */
    if (SB_GDST & 1u) { SB_GDEN = 0; return -1; }       /* wedged: abort */
    if (gd_wait_clear(ST_BSY | ST_DRQ)) return -1;
    (void)GD_STATCMD;                                    /* ack INTRQ + verdict */
    return 0;
}

/* 0 delivered / 1 not ours / 2 decode-failed (recorded; caller re-serves
 * uncompressed) / negative transport failure (caller propagates = dies,
 * today's envelope -- spec amendment 2026-09-23). */
static int gd_read_lz4(unsigned cart_off, void *dst, unsigned len) {
    const struct lz4pak_entry *e = 0;
    for (unsigned k = 0; k < LZ4PAK_NPAK; k++)
        if (lz4pak_map[k].cart_off == cart_off && lz4pak_map[k].ulen == len)
            e = &lz4pak_map[k];
    if (!e) return 1;
    if (P2(SHIM_STATE)[SHIM_STATE_GD_BACKEND]) return 1;   /* raw ATA only */

    /* ring-bounce prerequisites: the heap-base steal must have taken (the
     * 64 KB ring RAM at PF_RING_BASE is really reserved) and the boot must
     * be main-mode. pf_armed (gd.c) is exactly those two tripwires PLUS the
     * sticky disarm, so ask IT rather than re-implement the pair: cart.c's
     * fence disarms at site 4 precisely when a game DMA dest overlapped the
     * ring -- i.e. the ring RAM is demonstrably live game memory, which a
     * bounce decode must not touch. (pf_armed may arm prefetch as a side
     * effect of probing; that is the same probe gd_read_cart already runs a
     * few lines above.) Scribbling an ARMED ring is safe: the pf miss
     * re-aim empties the window after every mapped read, and prefetch ticks
     * cannot interleave with a read (hooks do not nest). */
#if SHIM_PREFETCH
    if (!pf_armed()) return 1;
#else
    if (*P2(PF_HEAP_BASE_WORD) != PF_HEAP_BASE_NEW) return 1;
    if (P2(SHIM_STATE)[0] != 0) return 1;
#endif

    unsigned phys = (unsigned)(unsigned long)dst & 0x1fffffffu;
    /* same qualifier shape as gd_read_fad's dma test (gd.c:415-416) */
    if ((phys & 31u) || phys < 0x0c000000u || 0x0d000000u - phys < len)
        return 1;
    /* ...plus one this path needs and gd_read_fad does not: the bounce
     * ring must be DISJOINT from the served region, or decoding the
     * bounced chunk would scribble the middle of the very buffer we are
     * filling (silent corruption -- the one failure class the fallback
     * cannot catch). Same overlap test cart.c's fence uses (cart.c:93-95);
     * dest bounds make it reachable in principle (DEST_LO 0x0c01f000, a
     * 8.3 MB pak). Falls back to the uncompressed read, never worse. */
    if (phys < (PF_RING_BASE & 0x1fffffffu) + PF_RING_SZ &&
        phys + len > (PF_RING_BASE & 0x1fffffffu))
        return 1;

    unsigned base = phys + e->ulen - e->r_bytes;
    unsigned secs = e->r_bytes / GD_SECSZ;
    unsigned f = e->blob_fad;

    /* ---- arm + packet: mirror of gd_read_fad's DMA path (KEEP IN SYNC:
     * gd.c:383-391 gd_hw_init/DRVSEL/idle, :418-423 OCBI + SB_* arm,
     * :425-433 FEATURES..BCHI + PACKET, :437 DRQ wait, :457-462 the six
     * command words, :466 GDST kick). Sole deviation: SB_GDEN = 0 on the
     * packet-wait failure -- the engine is already armed here, whereas in
     * gd_read_fad that failure site is shared with the PIO path. ---- */
#if SHIM_TIME
    lz4_t_wait = lz4_t_work = 0;
#endif
    gd_hw_init();
    GD_DRVSEL = 0xa0;
    if (gd_wait_clear(ST_BSY | ST_DRQ)) return gd_fail(GD_E_IDLE, f);
    for (unsigned a = base | 0x80000000u, en = a + e->r_bytes; a < en; a += 32u)
        __asm__ __volatile__("ocbi @%0" : : "r"(a) : "memory");
    SB_GDSTAR = base;
    SB_GDLEN  = e->r_bytes;
    SB_GDDIR  = 1;
    SB_GDEN   = 1;
    GD_FEATURES = 1;                     /* DMA data phase */
    GD_SECCNT = 0;
    GD_BCLO = (unsigned char)(GD_SECSZ & 0xffu);
    GD_BCHI = (unsigned char)(GD_SECSZ >> 8);
    GD_STATCMD = ATA_SPI_PACKET;
    if (gd_wait_drq()) { SB_GDEN = 0; return gd_fail(GD_E_PACKET, f); }
    GD_DATA = (unsigned short)(SPI_CD_READ | (0x20u << 8));
    GD_DATA = (unsigned short)(((f >> 16) & 0xffu) | (((f >> 8) & 0xffu) << 8));
    GD_DATA = (unsigned short)(f & 0xffu);
    GD_DATA = 0;
    GD_DATA = (unsigned short)(((secs >> 16) & 0xffu) | (((secs >> 8) & 0xffu) << 8));
    GD_DATA = (unsigned short)(secs & 0xffu);
    SB_GDST = 1;

    /* ---- chunk loop: inflate chasing the DMA frontier, i = 0...126 ---- */
    unsigned char *out = (unsigned char *)(phys | 0x80000000u);        /* P1 cached */
    const unsigned char *inb = (const unsigned char *)(base | 0x80000000u);
    struct lz4_lay L;
    for (unsigned i = 0; i < e->nchunk; i++) {
        lz4pak_lay(e, i, &L);
#if SHIM_TIME
        unsigned tw0 = TIME_TCNT0;
#endif
        if (lz4_wait_lend(L.lend_target)) {
            SB_GDEN = 0;
            *(volatile unsigned int *)0xa05f6900 = 1u << 14;
            return gd_fail(GD_E_DMA, f);
        }
#if SHIM_TIME
        unsigned tw1 = TIME_TCNT0;          /* down-counter: elapsed = old - new */
        lz4_t_wait += tw0 - tw1;
#endif
        if (L.stored) {
            lz4_copy32(out + L.out_off, inb + L.in_off, L.usize);
        } else if (L.bounced) {
            /* innermost LZ4 chunk: in-place margin is structurally
             * absent (spec amendment 2026-09-23) -- decode into the
             * disjoint 64 KB T3 ring instead, then copy home. */
            int rb = LZ4_decompress_safe((const char *)(inb + L.in_off),
                                         (char *)PF_RING_BASE,
                                         (int)L.csize, (int)L.usize);
            if (rb == (int)L.usize)
                lz4_copy32(out + L.out_off,
                           (const unsigned char *)PF_RING_BASE, L.usize);
            /* ring lines are dirty P1 now; discard them so a later P2
             * prefetch fill can't be clobbered by a stale writeback
             * (the C1 rule). Runs BEFORE the verdict, so the failure exit
             * cleans up too: a partial decode's write extent is unknown,
             * so discard the whole span it could have touched -- leaking
             * dirty ring lines into gd_prefetch_tick's next P2 fill would
             * corrupt prefetch-served cart bytes on eviction. */
            for (unsigned a2 = PF_RING_BASE, e2 = a2 + L.usize; a2 < e2; a2 += 32u)
                __asm__ __volatile__("ocbi @%0" : : "r"(a2) : "memory");
            if (rb != (int)L.usize) goto lz4_bad;
        } else if (LZ4_decompress_safe((const char *)(inb + L.in_off),
                                       (char *)(out + L.out_off),
                                       (int)L.csize, (int)L.usize) != (int)L.usize) {
            goto lz4_bad;
        }
#if SHIM_LZ4CRC
        if (shim_crc32(out + L.out_off, L.usize) != e->chunks[i].crc32)
            goto lz4_bad;
#endif
        lz4_ocbp(phys + L.out_off, L.usize);
#if SHIM_TIME
        lz4_t_work += tw1 - TIME_TCNT0;
#endif
    }

    /* ---- epilogue: mirror of gd_read_fad's DMA end (KEEP IN SYNC:
     * gd.c:481-494 GDST poll/gd_diag[6]/ISTNRM ack/GDST+GDLEND verdict,
     * :540-555 the shared end-of-command verdict -- minus its :545-550
     * drain-forensics loop, which counts leftover PIO DRQ bytes and says
     * nothing on a path that just asserted GDLEND == r_bytes) ---- */
#if SHIM_TIME
    unsigned tw2 = TIME_TCNT0;
#endif
    if (lz4_wait_lend(e->r_bytes)) {
        SB_GDEN = 0;
        *(volatile unsigned int *)0xa05f6900 = 1u << 14;
        return gd_fail(GD_E_DMA, f);
    }
    {
        unsigned i2, seen2 = 0;
        for (i2 = 0; i2 < GD_SPIN && (SB_GDST & 1u); i2++) {
            GD_HEARTBEAT(i2);
            unsigned now = SB_GDLEND;
            if (now != seen2) { seen2 = now; i2 = 0; }
        }
    }
#if SHIM_TIME
    lz4_t_wait += tw2 - TIME_TCNT0;         /* engine-drain tail is link wait */
#endif
    unsigned lend = SB_GDLEND;
    gd_diag[6] = lend;
    *(volatile unsigned int *)0xa05f6900 = 1u << 14;
    if (SB_GDST & 1u) { SB_GDEN = 0; return gd_fail(GD_E_DMA, f); }
    if (lend != e->r_bytes) return gd_fail(GD_E_DMA, f);
    if (gd_wait_clear(ST_BSY | ST_DRQ)) return gd_fail(GD_E_END, f);
    if (GD_STATCMD & ST_CHECK) return gd_fail(GD_E_CHECK, f);
#if SHIM_LZ4CRC
    scif_puts("LZ4OK o="); scif_puthex(cart_off);
    scif_puts(" l=");      scif_puthex(len);
    scif_puts("\n");
#endif
#if SHIM_TIME
    lz4_served = 1;         /* SHIMTIME tail prints + clears the SHIMLZ4 row */
#endif
    return 0;

lz4_bad:
    /* Decode-stage failure: transport may still be moving -- drain it so
     * the drive is idle, record forensics, then hand back for the
     * uncompressed re-read of the untouched original (never worse than
     * today). A wedged drain is a transport failure: propagate. */
    if (lz4_settle_engine()) return gd_fail(GD_E_DMA, f);
#if SHIM_LZ4CRC
    scif_puts("LZ4FAIL o="); scif_puthex(cart_off); scif_puts("\n");
#endif
    gd_fail(GD_E_LZ4, f);       /* record only; the read is still served */
    return 2;
}

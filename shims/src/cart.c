#include "shim_iface.h"
typedef unsigned int u32;

typedef struct {
    u32 head_fad, head_skip, head_take;   /* fads are cart-relative sector indices */
    u32 body_fad, body_sect;
    u32 tail_fad, tail_take;
} split_t;

/* Pure: decompose (byte offset, byte len) into partial-head / whole-sector
 * body / partial-tail. Compiled on host for the unit test (test/test_host.c). */
void cart_split(u32 off, u32 len, split_t *s) {
    u32 sec = off / 2048, skip = off % 2048;
    s->head_fad = s->head_skip = s->head_take = 0;
    s->body_fad = s->body_sect = 0;
    s->tail_fad = s->tail_take = 0;
    if (skip) {
        u32 take = 2048 - skip; if (take > len) take = len;
        s->head_fad = sec; s->head_skip = skip; s->head_take = take;
        len -= take; sec++;
    }
    s->body_fad = sec;
    s->body_sect = len / 2048;
    sec += s->body_sect; len %= 2048;
    if (len) { s->tail_fad = sec; s->tail_take = len; }
}

#ifndef HOST_TEST
void shim_die(u32, u32, u32);
void *xmemcpy(void *, const void *, u32);
int gd_read_fad(unsigned fad, void *dst, unsigned sectors);  /* gd.c: raw-ATA PIO read */
#if SHIM_GD_DMA
int gd_read_fad_dma(unsigned fad, u32 phys, unsigned sectors); /* gd.c: G1-DMA body reads (not written yet) */
#endif
void scif_puts(const char *); void scif_puthex(u32);
void shim_mark(u32 slot, unsigned short color);   /* util.c: real-HW breadcrumb HUD */

/* .data (non-zero init, house style): first-read flag + activity blink counter.
 * cart_count is non-static: main.c paints a reads/sec rate from it (round 16). */
static u32 cart_first = 1;
u32 cart_count = 1;

/* ---- HW load-time measurement (SHIM_LOADSTAT) --------------------------
 * The post-handoff black screen is dominated by the boot asset preload
 * streamed through this shim's synchronous PIO GD path (watch-item I1; the
 * loader clocked PIO at 1 MiB / 378 ms). Paint cumulative stream bytes,
 * request count, and time-in-GD (ms) LIVE, so the TV shows the counters climb
 * during the black screen and settle when the title presents -- streaming vs
 * other-init cost, read off the peak values + a stopwatch. Per-read VRAM paint
 * blacks Flycast's present (round 12; HW-only, like SHIM_HUD). Set 0 to remove. */
#if SHIM_LOADSTAT
void hex_paint_c(unsigned int, unsigned int, unsigned int,
                 unsigned short, unsigned short);           /* util.c (unconditional) */
void ls_stampA(unsigned int);                               /* main.c: init-timeline stamp */
#define LS_FG 0x0000                                        /* black digits ... */
#define LS_BG 0xffff                                        /* ... on a white box (splash-readable) */
#define LS_TCNT0 (*(volatile u32 *)0xffd8000c)               /* BIOS-left free-running timer */
#define LS_TCR0  (*(volatile unsigned short *)0xffd80010)
static u32 ls_bytes = 0, ls_reads = 0, ls_ticks = 0, ls_sh = 0xff; /* ls_sh: .data sentinel */
#endif

#if SHIM_LOADBAR
void loadbar_paint(unsigned int fill);                      /* util.c: 320-px bar */
/* Boot-preload byte countdown. 10 MiB (= 320px << 15, so fill = bytes >> 15,
 * no divide) is deliberately UNDER the HW-measured ~11.4 MiB boot preload:
 * the bar hits 100% and painting stops for good BEFORE the title presents --
 * an overshoot would leave the bar short of full and let the first
 * stage-boundary stream repaint it over live gameplay.
 * ponytail: knob -- retune only if the boot preload ever shrinks below 10 MiB. */
#define PB_TOTAL (320u << 15)
static u32 pb_left = PB_TOTAL;         /* .data non-zero init (house style) */
#endif

extern u32 gd_last_err;                       /* gd.c: 0xda<site><status><error> of last failure */
/* ponytail: cart_split + cart_read below duplicate gd.c's gd_plan/gd_read_cart
 * (the same head/body/tail decomposition). Task 7 reconciled the CALL SITES to
 * the new interface only -- collapsing cart_read into a single gd_read_cart()
 * call is Task 10's job, when the SHIM_GD_DMA body split and this file's
 * instrumentation get re-enabled and can be re-decided together. */
static void gd_or_die(void *dst, u32 rel_fad, u32 n) {
    int r = gd_read_fad(CART_FAD + rel_fad, dst, n);
    if (r < 0) shim_die(4, rel_fad, gd_last_err);
}
#if SHIM_GD_DMA
static void gd_or_die_dma(u32 phys, u32 rel_fad, u32 n) {   /* body via G1-DMA (32-aligned phys) */
    int r = gd_read_fad_dma(CART_FAD + rel_fad, phys, n);
    if (r < 0) shim_die(4, rel_fad, gd_last_err);
}
#endif

/* dest_phys is a main-RAM phys addr (0x0c......). The game reads streamed cart
 * assets UNCACHED (P2, 0xa0......) or via hardware DMA (PVR/TA/AICA) -- real-DMA
 * semantics, matching the original FUN_8c03bc12 which does NO cache op. So the
 * bytes must land in RAM with nothing stale left in the D-cache. We therefore
 * write the dest through the P2 UNCACHED alias (0xa0......): the xmemcpy head/
 * tail stores AND the gd_read_fad PIO body stores all go straight to RAM,
 * bypassing the cache, so the game's P2 read (or a downstream DMA) sees current
 * data on real hardware. (Via P1 cached the bytes would sit in D-cache while RAM
 * stayed stale -> garbage graphics on real DC; Flycast has no cache so it masked
 * this.) This mirrors maple_reply + the register mirror, which are all P2.
 * The bounce buffer stays cached (shim home, P1): it is pure CPU scratch -- the
 * BIOS PIO writes it and xmemcpy reads it back through the same cached view, so
 * they are mutually coherent; only the FINAL dest must be uncached. */
void cart_read(u32 off, u32 len, u32 dest_phys) {
    split_t s;
    if (cart_first) { cart_first = 0; shim_mark(4, 0xf81f); }   /* slot4 magenta: first cart read */
    if ((++cart_count & 31u) == 0)                              /* slot5: activity blinker */
        shim_mark(5, (cart_count & 32u) ? 0xffe0 : 0x001f);
    unsigned char *dst = (unsigned char *)(dest_phys | 0xa0000000); /* P2 uncached */
    unsigned char *bounce = (unsigned char *)SHIM_BOUNCE;
    cart_split(off, len, &s);
    if (s.head_take) {
        gd_or_die(bounce, s.head_fad, 1);
        xmemcpy(dst, bounce + s.head_skip, s.head_take);
        dst += s.head_take;
    }
    if (s.body_sect) {
#if SHIM_GD_DMA
        /* dest_phys is a physical addr (0x0c..); the head bytes are already
         * written, so the body starts head_take further in. G1-DMA needs a
         * 32-byte-aligned dest -- off is usually sector-aligned (no head), so
         * the body qualifies; the rare unaligned body falls back to PIO. */
        u32 body_phys = dest_phys + s.head_take;
        if ((body_phys & 31u) == 0)
            gd_or_die_dma(body_phys, s.body_fad, s.body_sect);
        else
#endif
            gd_or_die(dst, s.body_fad, s.body_sect);
        dst += s.body_sect * 2048;
    }
    if (s.tail_take) {
        gd_or_die(bounce, s.tail_fad, 1);
        xmemcpy(dst, bounce, s.tail_take);
    }
}

/* Entry hooked onto the game's DMA-completion wait FUN_8c03bc12 (KB §V3, patch
 * via Task 12). Reads the mirrored register values the game already wrote
 * (KB §patch-sites: MIRROR+0xYYY stands in for cart/G1 reg 0x5f7YYY).
 *   off  = DMA_OFFSETH(0x700c)<<16 | DMA_OFFSETL(0x7010), cart-relative bytes
 *   len  = SB_GDLEN(0x7408) bytes (sole length source; DMA_COUNT unwritten here)
 *   dest = SB_GDSTAR(0x7404) phys ; SB_GDST(0x7418) cleared => game's poll exits */
void shim_cart_service(void) {
    volatile u32 *m = P2(G1_MIRROR);
    u32 off = (((m[0x0c/4] & 0xffff) << 16) | (m[0x10/4] & 0xffff)) & 0x0fffffff;
    u32 len = m[0x408/4];               /* SB_GDLEN mirror (bytes), sole length */
    /* ponytail: length is SB_GDLEN; DMA_COUNT (mirror+0x14) is never written by
     * this game's arm path (FUN_8c03b81a) -- cross-check dropped */
    u32 dest = m[0x404/4] & 0x1fffffff; /* SB_GDSTAR mirror; game programs it
                                         * P1-aliased (0x8c..) -- mask P0/P1/P2
                                         * region bits to physical 0x0c.. */
    /* len sanity (>16MB is impossible for a legit cart read) BEFORE the +len
     * comparisons so an absurd SB_GDLEN can't u32-wrap past them. Upper bound is
     * fenced to shim home (SHIM_BASE phys 0x0cfc0000): a DMA reaching there would
     * clobber the running shim / BIOS-data blocks -- last line protecting it. */
    if (!len || len > 0x01000000 || off + len > CART_SIZE ||
        (dest & 0x1f000000) != 0x0c000000 || dest + len > (SHIM_BASE & 0x1fffffff))
        shim_die(2, off, dest);
#ifndef SHIM_TRACE
#define SHIM_TRACE 0
#endif
    if (SHIM_TRACE) {   /* per-read serial: ~2-3 ms SCIF spin each on real HW */
        scif_puts("CART off="); scif_puthex(off);
        scif_puts(" len="); scif_puthex(len);
        scif_puts(" dst="); scif_puthex(dest); scif_puts("\n");
    }
#if SHIM_GD_DIAG
    /* Phase marker (x=220,y=134): 0xA|count = stream requested, 0xB = data
     * delivered + checksummed, 0xE = stream done, back to game code. A photo
     * frozen at E pins the hang inside the game itself (data suspect). */
    void hex_paint_c(unsigned int, unsigned int, unsigned int,
                     unsigned short, unsigned short);
    hex_paint_c(220, 134, 0xA0000000u | (cart_count & 0x00ffffffu), 0xffff, 0x001f);
#endif
#if SHIM_LOADSTAT
    if (ls_sh == 0xff) {                   /* TCR0.TPSC -> prescaler shift (Pck 50 MHz) */
        static const u32 sh[8] = {2, 4, 6, 8, 10, 10, 10, 10};
        ls_sh = sh[LS_TCR0 & 7u];
    }
    u32 ls_t0 = LS_TCNT0;
#endif
    cart_read(off, len, dest);
    m[0x418/4] = 0;                     /* SB_GDST mirror reads "done" */
#if SHIM_GD_DIAG
    {   /* Position-sensitive checksum (rotl1-xor) of the delivered bytes,
         * read back uncached, painted at (220,120) -- compare against the
         * ROM-derived expected value for this stream to prove/disprove
         * data corruption on the wire (isoldr serve path). */
        volatile unsigned char *p = (volatile unsigned char *)(dest | 0xa0000000u);
        u32 ck = 0;
        for (u32 i = 0; i < len; i++) ck = ((ck << 1) | (ck >> 31)) ^ p[i];
        hex_paint_c(220, 120, ck, 0xffff, 0x001f);
        hex_paint_c(220, 134, 0xB0000000u | (cart_count & 0x00ffffffu), 0xffff, 0x001f);
    }
#endif
#if SHIM_LOADBAR
    if (pb_left) {                      /* boot preload only; 0 = done forever */
        pb_left = (len >= pb_left) ? 0 : pb_left - len;
        loadbar_paint((PB_TOTAL - pb_left) >> 15);
    }
#endif
#if SHIM_GD_DIAG
    hex_paint_c(220, 134, 0xE0000000u | (cart_count & 0x00ffffffu), 0xffff, 0x001f);
#endif
#if SHIM_LOADSTAT
    u32 ls_dt = ls_t0 - LS_TCNT0;          /* down-counter: elapsed = start - now */
    if (ls_dt < (50000000u >> ls_sh)) ls_ticks += ls_dt;  /* skip a reload-wrap sample (>1 s) */
    ls_bytes += len; ls_reads++;
    ls_stampA(4);                          /* latch "streaming started" on the init timeline */
    /* ms = ticks/rate*1000 = (ticks<<sh)/50000 -- variable shift + CONSTANT divide,
     * so no libgcc __udivsi3 (this shim is -nostdlib). */
    hex_paint_c(20, 152, ls_bytes,              LS_FG, LS_BG);  /* cumulative cart-stream bytes (hex) */
    hex_paint_c(20, 166, ls_reads,             LS_FG, LS_BG);  /* cumulative stream requests */
    hex_paint_c(20, 180, (ls_ticks << ls_sh) / 50000u, LS_FG, LS_BG);  /* time in GD path, ms */
#endif
}
#endif /* !HOST_TEST */

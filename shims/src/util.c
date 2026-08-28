#include "shim_iface.h"
#include <stddef.h>
void scif_puts(const char *); void scif_puthex(unsigned int);
#if SHIM_LOADSTAT
void ls_stampA(unsigned int);                  /* main.c: init-timeline stamp */
#endif
/* Freestanding -Os lets GCC lower sized array copies/inits to memcpy/memset
 * calls, so the runtime must supply them. xmemcpy stays for explicit callers. */
void *memcpy(void *d, const void *s, size_t n) {
    unsigned char *dd = d; const unsigned char *ss = s;
    while (n--) *dd++ = *ss++;
    return d;
}
void *memset(void *d, int c, size_t n) {
    unsigned char *dd = d;
    while (n--) *dd++ = (unsigned char)c;
    return d;
}
void *xmemcpy(void *d, const void *s, unsigned int n) { return memcpy(d, s, n); }
/* Real-HW breadcrumb HUD: paint a small block near the top of the LIVE scanout
 * framebuffer (base read from FB_R_SOF1) and clear the VO_CONTROL blank bit --
 * the game blanks video during init and unblanks only after its first rendered
 * frame, so on a hang the screen stays black with zero information. Each
 * milestone paints once; which blocks appear names the phase that hung. */
/* Round-17: HUD is ON by default (shim_iface.h:81 defines SHIM_HUD 1 --
 * intended this phase per the spec's observability-early rule). On real HW
 * every painted pixel is a slow uncached VRAM bus write -- the full HUD
 * (marks + classifiers + 6 hex rows per trigger + 4 per poll) burns
 * milliseconds of the 16.7 ms frame, invisible in Flycast (instant memory).
 * Prime suspect for the 2P-only slowdown (heavier frames, no headroom
 * left). Flip SHIM_HUD to 0 in shim_iface.h for release; shim_die's fatal
 * paints stay unconditional. */

void shim_mark(unsigned int slot, unsigned short color) {
#if !SHIM_HUD
    (void)slot; (void)color; return;
#endif
    *(volatile unsigned int *)0xa05f80e8 &= ~8u;            /* unblank video */
    unsigned int base = *(volatile unsigned int *)0xa05f8050 & 0x00fffffcu;
    volatile unsigned short *fb =
        (volatile unsigned short *)(0xa5000000u + base);
    if (slot >= 16u)                       /* slots 16+ = second row, below row 1 */
        fb += 12u * 640u + (slot - 16u) * 24u;
    else
        fb += slot * 24u;
    for (unsigned int y = 0; y < 8; y++)
        for (unsigned int x = 0; x < 16; x++)
            fb[y * 640u + x] = color;
}

/* On-screen hex printer (real-HW forensics): 8 nibbles, 3x5 font scaled x2,
 * drawn into the live scanout FB. Readable from a photo of the TV. */
static const unsigned char hexfont[16][5] = {
    {7,5,5,5,7},{2,6,2,2,7},{7,1,7,4,7},{7,1,7,1,7},
    {5,5,7,1,1},{7,4,7,1,7},{7,4,7,5,7},{7,1,2,2,2},
    {7,5,7,5,7},{7,5,7,1,7},{2,5,7,5,5},{6,5,6,5,6},
    {7,4,4,4,7},{6,5,5,5,6},{7,4,7,4,7},{7,4,7,4,4},
};
/* fg/bg-parameterized core (non-static: cart.c's SHIM_LOADSTAT paint calls it
 * directly for dark-on-white -- readable over the white Naomi splash where the
 * cyan default washes out; unconditional, unlike SHIM_HUD-gated shim_hex).
 * Every glyph cell is written (set->fg, unset->bg), so bg is a solid box behind
 * each digit. hex_paint keeps the classic cyan-on-black for death screen + HUD. */
void hex_paint_c(unsigned int x, unsigned int y, unsigned int val,
                 unsigned short fg, unsigned short bg) {
    *(volatile unsigned int *)0xa05f80e8 &= ~8u;            /* unblank video */
    unsigned int base = *(volatile unsigned int *)0xa05f8050 & 0x00fffffcu;
    volatile unsigned short *fb = (volatile unsigned short *)(0xa5000000u + base);
    for (unsigned int d = 0; d < 8; d++) {
        unsigned int nib = (val >> ((7u - d) * 4u)) & 0xfu;
        for (unsigned int r = 0; r < 5; r++)
            for (unsigned int c = 0; c < 3; c++) {
                unsigned short px = ((hexfont[nib][r] >> (2u - c)) & 1u) ? fg : bg;
                unsigned int px_x = x + d * 10u + c * 2u, px_y = y + r * 2u;
                fb[px_y * 640u + px_x]        = px;
                fb[px_y * 640u + px_x + 1u]   = px;
                fb[(px_y + 1u) * 640u + px_x] = px;
                fb[(px_y + 1u) * 640u + px_x + 1u] = px;
            }
    }
}
void hex_paint(unsigned int x, unsigned int y, unsigned int val) {
    hex_paint_c(x, y, val, 0x07ff, 0x0000);                 /* cyan on black */
}

#if SHIM_LOADBAR
/* Boot-preload progress bar over the loader's Naomi splash: 320x6 px orange
 * fill + black track in a black 1-px outline, centered, low on screen. Same
 * live-scanout idiom as hex_paint_c (unblank + FB_R_SOF1 base).
 * COLOR: the game scans the FB as RGB0555 (FB_R_CTRL=1 -- HW round-15
 * register photo 2026-08-16), and the LOADER now displays the splash in that
 * same format (loader/main.c PM_RGB555), so the splash bytes are already
 * right at takeover and this function touches only the bar's own pixels.
 * (The first cut repacked the whole buffer 565->0555 here instead: 307k
 * uncached 16-bit VRAM reads inside the takeover blank window = ~1.2 s of
 * solid black, Flycast CLEO-SPG timestamps + HW 2026-08-18. Never read
 * VRAM in the blank window.) Bar colors are 0555 literals; black/white are
 * format-invariant. fill is the lit width in px; cost irrelevant during load. */
void loadbar_paint(unsigned int fill) {
    if (fill > 320u) fill = 320u;
    unsigned int base = *(volatile unsigned int *)0xa05f8050 & 0x00fffffcu;
    volatile unsigned short *fb = (volatile unsigned short *)(0xa5000000u + base);
    /* Bar row, all cables. The old per-cable row (200 on TV) modeled the
     * deleted patch-#34 path's 240-line scan (ysize=236, modulus=1,
     * SOF1==SOF2, measured 2026-08-02) and put the bar mid-screen on the
     * game's REAL NTSC mode (HW composite 2026-08-17). That mode scans the
     * FB as a full 480-line frame -- FB_R_SIZE=1413b53f: ysize=237,
     * modulus=321 (skip-one-line interlace), SOF2=SOF1+0x500 (Flycast
     * CLEO-SPG/SOFWR r30, Cable=3, 2026-08-17) -- so linear row N shows at
     * screen line N on every cable. 417..428 = same ~10% bottom margin
     * inside NTSC overscan that the old TV row aimed for. */
    unsigned int yb = 417u;
    /* Outline + track every paint, not one-shot: the game flips the scanout
     * base between two buffers each vblank even during load (CLEO-SPG: SOF1
     * 0xfd000<->0x4fd000 on TV cable), so a once-painted outline lives in
     * one flip buffer and vanishes every other frame. Repainting converges
     * both buffers; cost irrelevant during load. Black outline + track and
     * orange fill (0x7984 = #F26522 in 0555) per the tester mockup; the
     * splash-white rows between outline and track are left as the gap. */
    for (unsigned int x = 158u; x < 483u; x++)              /* outline: top/bottom */
        fb[yb * 640u + x] = fb[(yb + 11u) * 640u + x] = 0x0000u;
    for (unsigned int y = yb + 1u; y < yb + 11u; y++)       /* outline: sides */
        fb[y * 640u + 158u] = fb[y * 640u + 482u] = 0x0000u;
    for (unsigned int y = yb + 3u; y < yb + 9u; y++)
        for (unsigned int x = 0; x < 320u; x++)             /* fill + black track */
            fb[y * 640u + 160u + x] = x < fill ? 0x7984u : 0x0000u;
    *(volatile unsigned int *)0xa05f80e8 &= ~8u;            /* unblank video */
}
#endif

void shim_hex(unsigned int x, unsigned int y, unsigned int val) {
#if !SHIM_HUD
    (void)x; (void)y; (void)val; return;
#endif
    hex_paint(x, y, val);
}

/* DC video-cable sense, KOS-identical RMW (tools/kos .../hardware/video.c:211
 * vid_check_cable): PCTRA bits 19:16 := 0xa (ports 8/9 input), then PDTRA
 * bits 9:8 = 0 VGA / 2 RGB / 3 composite. Latched once (.data non-zero init
 * per house style -- loader does not zero .bss); safe: the game never touches
 * PCTRA/PDTRA (zero CLEO-GPIO lines across all captures). */
static unsigned int cable_latch = 0xff;    /* >3 = not yet read */
int shim_cable_is_vga(void) {
    if (cable_latch > 3u) {
        volatile unsigned int *pctra = (volatile unsigned int *)0xff80002c;
        *pctra = (*pctra & 0xfff0ffffu) | 0x000a0000u;
        cable_latch = (*(volatile unsigned short *)0xff800030 >> 8) & 3u;
    }
    return cable_latch == 0;
}

/* Composite/RGB sync fix -- Cleopatra Fortune Plus SDK hook (FUN_8c034020 /
 * FUN_8c0409e0 / pool 0x8c026570 are THAT game's Ghidra-RE'd addresses, not
 * senkosp's). Kept as reference for the same problem class (Naomi DIP-1
 * monitor choice never reaching the game post-BIOS-bypass); Tasks 10-12
 * re-derive senkosp's own SDK video-init hook once RE'd. #if 0, not deleted,
 * so a live-compiled call into another game's hardcoded address can't slip
 * into the shim by accident while it sits unused. */
#if 0  /* re-enabled per-task: see plan Tasks 10-12 */
int shim_vid_init(unsigned int mode, unsigned int b, unsigned int c, unsigned int d) {
#if SHIM_LOADSTAT
    ls_stampA(3);                              /* video init reached, on the init timeline */
#endif
    if (!shim_cable_is_vga())
        mode &= ~3u;               /* class 1 (VGA 31k) -> class 0 (NTSC 480i) */
    int r = ((int (*)(unsigned int, unsigned int, unsigned int, unsigned int))
             0x8c034020)(mode, b, c, d);
#if SHIM_LOADBAR
    /* Empty bar right at video takeover (the SDK init above just programmed
     * the FB regs this paint reads), not at the first cart stream ~1 s later
     * -- kills the splash->bar solid-black gap (HW round 3). Re-entry safe:
     * the paint is stateless (bar pixels only). */
    loadbar_paint(0);
#endif
    return r;
}
#endif /* re-enabled per-task: see plan Tasks 10-12 */

void shim_die(unsigned int code, unsigned int a, unsigned int b) {
    volatile unsigned int *e = P2(SHIM_ERR);
    e[1] = a; e[2] = b; e[3] = 0xdeadcafe; e[0] = code;
    scif_puts("SHIMERR code="); scif_puthex(code);
    scif_puts(" a="); scif_puthex(a); scif_puts(" b="); scif_puthex(b); scif_puts("\n");
    /* Paint VRAM so real HW shows the failure instead of a silent black hang
     * (serial is invisible there). The visible framebuffer sits inside the
     * first 1 MB of VRAM regardless of scanout base. RGB565 pairs:
     * 2=yellow (cart-service bad dest)  3=magenta (unknown maple frame)
     * 4=red (GD read error)  5=blue (GD poll hang)  else cyan. */
    unsigned int px = 0x07ff07ff;
    if (code == 2) px = 0xffe0ffe0;
    else if (code == 3) px = 0xf81ff81f;
    else if (code == 4) px = 0xf800f800;
    else if (code == 5) px = 0x001f001f;
    volatile unsigned int *v = (volatile unsigned int *)0xa5000000;
    for (unsigned int i = 0; i < 0x100000 / 4; i++) v[i] = px;
    /* Round-9 lesson: a mute color is half a diagnosis. Paint code/a/b as hex
     * ON the fill (cyan digits read fine on every fill color) so the TV shows
     * e.g. the failing FAD and error code, not just "red". */
    hex_paint(20, 100, code);        /* unconditional: fatal screens stay verbose */
    hex_paint(20, 114, a);
    hex_paint(20, 128, b);
    /* GD forensics block (gd.c gd_diag, hardware round 1): recoveries,
     * max-wait polls, blocks/nmin/nmax of the last read, bytes drained after
     * a GD_E_END. Meaning table: docs/kb/phase5-hardware.md §HUD kit. */
    {
        extern unsigned int gd_diag[8];
        for (unsigned int i = 0; i < 6; i++)
            hex_paint(20, 156 + 14 * i, gd_diag[i]);
    }
    for (;;) ;
}

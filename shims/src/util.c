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

/* No loadbar_paint (Task 26, rolled back entirely 2026-09-01): the shim never
 * has a screen it owns -- senkosp blanks and reprograms video before its first
 * cart read, and the boot burst lands under the game's own NOW LOADING screen
 * (cart.c note; docs/kb/phase5-hardware.md §Loading bar rollback). */

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

/* Composite/RGB sync fix (Task 31) -- Cleopatra's problem class, senkosp's
 * own mechanism (Ghidra RE 2026-09-03, docs/kb/phase6-release.md). The
 * game's one display init passes mode 0x80000038: bit31 = "auto" -- the
 * SDK display wrapper FUN_8c03d48e queries the monitor sense FUN_8c02a0ea
 * and picks the class itself (0 -> class 1 = 31 kHz, 1 -> class 0 = the
 * SDK's own 15 kHz builder, 2 -> class 2 = PAL; explicit-class calls are
 * VALIDATED against the same sense, so hooking the mode word instead
 * trips `return -1` paths -- measured, comp-dbg leg). The sense reads a
 * cached monitor code at 0x8c170d88 that only Naomi BIOS/DIP init ever
 * populates meaningfully; post-BIOS-bypass it always says 31 kHz and a TV
 * cable never syncs. MONITOR-SENSE-HOOK repoints the sense's single
 * fn-ptr pool word per image (main dat 0x1d5a8, test dat 0x18f020;
 * whole-.dat u32 scan = exactly one each) here, so the SDK's own auto
 * and validation logic runs against the real DC cable. VGA -> 0 keeps
 * the 31 kHz path byte-identical (Cable=0 census leg). */
int shim_monitor_sense(void) {
    int r = shim_cable_is_vga() ? 0 : 1;
    scif_puts("SENSE ->"); scif_puthex((unsigned int)r); scif_puts("\n");
    return r;
}

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

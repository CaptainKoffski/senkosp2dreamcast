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

/* SPG-GEOMETRY-PIN (phase 7 T8; generalizes the Task 31 round-2 15 kHz
 * geometry override). The game's one-time takeover mode-set rewrites the
 * six SPG/VO geometry regs FOR REAL on every cable -- on VGA it moves the
 * raster from KOS's 525x858 to the arcade 529x852 (SPG_LOAD
 * 020c0359->02110353 etc., captures/phase6/geo-vga0 + phase7 t8 census) --
 * a genuine sync-frequency change, so VGA monitors drop signal and relock
 * ~1 s at NOW LOADING on every boot (operator report; the arcade class-0
 * builder did the same to TVs: picture ~10% low, phase6-composite-shift
 * .jpeg). Fix: snapshot the live raster -- the one the monitor has been
 * locked to since the loader splash -- right before the SDK display-mode
 * entry, restore it right after. The wrong-timing excursion shrinks to
 * ~2 ms / one partial frame (census: the old post-fixup already landed
 * there and TVs rode through it). Everything the SDK computed for itself
 * stays game-owned: FB layout (FB_R_SIZE), vclk_div + fb enable
 * (FB_R_CTRL), blank (VO_CONTROL); SPG_CONTROL is measured pre==post on
 * both cables (0x100 VGA / 0x150 NTSC, geo-vga0 + t8-same-attract) so it
 * is not pinned. On composite the live pre-call values ARE the old
 * hardcoded vid_geom_ntsc table (KOS's boot writes, pc=8c00b87c), so this
 * is byte-equivalent there; on the dcload path it preserves dcload's
 * raster (fixes that drop too). VIDEO-GEOM-HOOK wraps the game's one
 * display-init call (fn-ptr pool word per image, main dat 0x4edcc, test
 * dat 0x1aa9c0); mode word passes through UNTOUCHED (the bit30 lesson,
 * §composite fix). Reg offsets per Flycast core/hw/pvr/pvr_regs.h.
 * Record: docs/kb/phase7-polishing.md §T8. */
/* Round 7: open from the wrapper-exit unblank to the side-buffer repoint,
 * so the ISR re-assert also covers the copy window (SOF1 still = loader FB
 * there, so the SOF1==0x260000 gate alone misses it). volatile: main-line
 * sets it, the interrupt wrapper reads it. */
static volatile unsigned int splash_live;

/* T7 ROUND 8: SPLASH-CONTINUITY (operator round-7 verdict: blink still
 * there, localized to the START -- splash -> spinner). Rounds 6-7 removed
 * OUR blank windows; what remains is the game's vid-init disturbing the
 * LIVE signal itself, and no after-the-fact restore can hide that from a
 * real monitor. The t8-pin-vga census (pcs are the write helper
 * 0x8c032140, prs identify the callers) gives the complete in-window
 * damage: FB_R_CTRL read-enable OFF for ~9 ms (pr=8c03890e), the SPG
 * H/V totals actually CHANGED for ~2 ms (pr=8c036cb6..8c036cde:
 * SPG_HBLANK/LOAD/VBLANK/WIDTH + VO_STARTX/Y), and VO_CONTROL blank set
 * three times (pr=8c036cea/8c036292/8c035398) -- ~10 ms of dark plus a
 * sync glitch that a VGA monitor/scaler stretches into a visible blink
 * (same class the rolled-back BOOT-UNBLANK v5 exposed as glitch rows).
 *
 * Every one of those writes flows through the game's single two-insn
 * write helper at 0x8c032140 (r4 = PVR reg offset, r5 = value), which
 * exactly four vid-init functions reach via one literal-pool word each
 * (dat 0x18954 fb-off/size-clear, 0x16c80 raster apply, 0x162b4
 * fb-config, 0x153c4 display-arm; single load site per literal, callers
 * verified to reload args per call and rely only on callee-saved regs).
 * Patch VIDINIT-WRITEFILTER repoints those four literals here. While
 * vid_init_pinned has the game's vid-init on the stack (vidinit_pin),
 * writes to the signal-shaping regs are DROPPED -- safe because their
 * end-states already equal the loader's values today (the T8 restore
 * forced them back; FB_R_CTRL's end value 00800005 is byte-identical,
 * census n=... "same" lines). FB_R_SIZE is DEFERRED, not dropped: the
 * game's scenes scan with its value (00177 53f vs loader d3f), so the
 * last written value is applied once at wrapper exit. Everything else
 * (SOFTRESET, SDRAM, TEXT_CONTROL 0xe4, FB_W path, clips, scaler,
 * burstctrl) passes through live -- those land under blank today and
 * the round-5 hardware PASS proves the splash scans fine with them.
 * Window closed -> pure pass-through: the gap-end display-on arm
 * (pr=8c03538e/8c035398/8c0353a0) and every later call behave as
 * today. The test image's own copies of these functions are NOT
 * patched (stock, same as VBL-SPIN); vidinit_pin being set during the
 * test image's wrapped vid-init is therefore inert. */
static volatile unsigned int vidinit_pin;
static volatile unsigned int fbrsize_defer, fbrsize_val;
void shim_pvr_write(unsigned int off, unsigned int val);
void shim_pvr_write(unsigned int off, unsigned int val) {
    volatile unsigned int *pvr = (volatile unsigned int *)0xa05f8000;
    if (vidinit_pin) {
        switch (off) {
        case 0x44:                                  /* FB_R_CTRL */
        case 0xe8:                                  /* VO_CONTROL (blank) */
        case 0xd0: case 0xd4: case 0xd8:            /* SPG_CONTROL/HBLANK/LOAD */
        case 0xdc: case 0xe0:                       /* SPG_VBLANK/WIDTH */
        case 0xec: case 0xf0:                       /* VO_STARTX/Y */
            return;
        case 0x5c:                                  /* FB_R_SIZE: defer */
            fbrsize_val = val;
            fbrsize_defer = 1;
            return;
        }
    }
    pvr[off / 4] = val;
}
/* The teardown fn (dat 0x18954, census pr=8c03890e) runs BEFORE the
 * wrapped vid-init call -- t7r8-comp census: its FB_R_CTRL=0 landed at
 * .168 while the wrapper's window opened at .17x -- so vidinit_pin cannot
 * cover it. Its display-offs exist only to pair with an init that is now
 * always filtered (every re-init goes through the same wrapped entry), so
 * drop them UNCONDITIONALLY; its FB_R_SIZE write is just the 0-clear (the
 * real value arrives via the fbcfg defer above). Everything else it does
 * (SOFTRESET, SDRAM cfg, TEXT_CONTROL, FB_W_CTRL, clips) passes live. */
void shim_pvr_write_pre(unsigned int off, unsigned int val);
void shim_pvr_write_pre(unsigned int off, unsigned int val) {
    switch (off) {
    case 0x44: case 0x5c: case 0xe8:
    case 0xd0: case 0xd4: case 0xd8: case 0xdc: case 0xe0:
    case 0xec: case 0xf0:
        return;
    }
    volatile unsigned int *pvr = (volatile unsigned int *)0xa05f8000;
    pvr[off / 4] = val;
}

static int vid_init_pinned(int (*entry)(unsigned int, unsigned int,
                                        unsigned int, unsigned int),
                           unsigned int mode, unsigned int b,
                           unsigned int c, unsigned int d) {
    /* SPG_HBLANK, SPG_LOAD, SPG_VBLANK, SPG_WIDTH, VO_STARTX, VO_STARTY */
    static const unsigned char off[6] = { 0xd4, 0xd8, 0xdc, 0xe0, 0xec, 0xf0 };
    volatile unsigned int *pvr = (volatile unsigned int *)0xa05f8000;
    unsigned int save[6];
    for (unsigned int i = 0; i < 6; i++) save[i] = pvr[off[i] / 4];
    vidinit_pin = 1;                    /* round 8: filter drops signal writes */
    int r = entry(mode, b, c, d);
    vidinit_pin = 0;
    for (unsigned int i = 0; i < 6; i++) pvr[off[i] / 4] = save[i];
    if (fbrsize_defer) {                /* round 8: game's FB_R_SIZE, once */
        pvr[0x5c / 4] = fbrsize_val;
        fbrsize_defer = 0;
    }
    /* SPLASH-PERSIST round 2: SPLASH-SIDE-BUFFER (phase 7 T7 revival,
     * operator hardware round 1 FAIL 2026-09-07). Round 1 unblanked here
     * and kept scanning the game's own framebuffer -- but the game
     * pre-composes its NOW LOADING scene into that framebuffer during the
     * gap tail (gauge ticks + tiles copied from then-uninitialized memory:
     * white-on-white in the emulator, garbage on real RAM -- operator
     * captures 11.52.49/11.53.03 PM), which the blank used to hide. So:
     * copy the splash to an otherwise-unused VRAM region and scan THAT.
     * The game composes at its own base unseen, and its first scene flip
     * (a real FB_R_SOF write, ~+3.4 s) moves scanout off our copy by
     * itself -- proper double-buffering, no execution needed at gap end.
     * Placement 0x260000 (32-bit-path) is MEASURED free, not assumed: the
     * first try (0x100000) collided -- the game's boot allocator packs
     * VRAM upward from its scan buffer at 0x08d000 and had written
     * 0x123000+ before its flip (t7r2-comp flip-off dump diff). Usage map
     * (vram_usage_map, unblank->flip and flip->attract dumps): boot writes
     * [0x08d000..0x140000), reaching 0x200000 by early attract; bank-1
     * mirror [0x48d000..0x600000). Quiet band both windows =
     * [0x200000,0x460000); 0x260000 leaves ~768 KB margin below. Only the
     * boot window matters -- after the game's flip the copy is off-scan
     * and reuse is harmless. Copy via the P2 32-bit path (0xa5000000 --
     * same address space FB_R_SOF uses, no bank-interleave math);
     * ~0x96000 bytes once, under blank, ~ms.
     * Blank-clear rationale unchanged from round 1: all three blank-set
     * sites (pr=8c036cea/8c036292/8c035398) fire INSIDE entry(), the gap
     * interior has zero VO writes (t8-pin-vga census), and the game's
     * gap-end unblank degrades to a same-value no-op. Blank stays ON
     * through the mode-set transient only.
     *
     * T7 round 6 (operator: "remove the blink between the initial splash
     * and the spinner"): the blink was OUR blank window -- rounds 2-5 held
     * blank through this copy too (~0.2-0.4 s of P2 traffic on hardware).
     * Needless: at this point scanout is still the LOADER's framebuffer at
     * VRAM 0x0 (t7r5-comp SOFWR timeline: the game's early vid-init sets
     * SOF1=0x00000000 at pc=8c0199f2 and never repoints before we do), so
     * the copy SOURCE is the very frame on screen. Unblank FIRST, copy the
     * visible splash while it is being scanned, then repoint to the
     * pixel-identical copy -- an invisible switch. Remaining blank =
     * the SDK mode-set span only (+3 ms to this unblank, t7-persist-comp
     * timeline -- sub-frame, invisible; game-owned, escalation = patch the
     * blank-set sites).
     *
     * T7 round 7 (operator round-6 verdict: blink STILL there): the
     * round-6 residual came true. The unblank below is one-shot, and
     * round 4 proved hardware re-blanks after exactly that (mechanism
     * emulator-invisible); the per-vblank re-assert armed only after the
     * repoint, leaving the copy window (~0.2-0.4 s of P2 traffic on real
     * hardware) undefended = the blink. During the copy the CPU is here,
     * so any re-blank can only come from an interrupt path (~60 Hz);
     * defend in-loop every 1024 words (~1-3 ms cadence, conditional
     * writes, normally zero) and open the ISR wrapper's re-assert arm for
     * the whole window via splash_live -- if the re-blank rides the
     * game's own vblank callback, the wrapper corrects it in the SAME
     * interrupt, before the frame ever scans out blanked. */
    {
        unsigned int sof1 = pvr[0x50 / 4];              /* FB_R_SOF1 (= 0x0, loader FB, holds splash) */
        unsigned int fdel = pvr[0x54 / 4] - sof1;       /* field-2 delta (0x500 both cables) */
        volatile unsigned int *s =
            (volatile unsigned int *)(0xa5000000u + (sof1 & 0x007ffffcu));
        volatile unsigned int *t = (volatile unsigned int *)0xa5260000u;
        splash_live = 1;
        pvr[0xe8 / 4] &= ~8u;                           /* unblank BEFORE the copy (round 6) */
        for (unsigned int i = 0; i < (640u * 480u * 2u) / 4u; i++) {
            t[i] = s[i];
            if ((i & 1023u) == 0) {                     /* round 7: defend the copy window */
                unsigned int vo = pvr[0xe8 / 4];
                if (vo & 8u) pvr[0xe8 / 4] = vo & ~8u;
                unsigned int fbc = pvr[0x44 / 4];
                if (!(fbc & 1u)) pvr[0x44 / 4] = fbc | 1u;
            }
        }
        pvr[0x50 / 4] = 0x00260000u;
        pvr[0x54 / 4] = 0x00260000u + fdel;
        splash_live = 0;                                /* SOF1 gate takes over seamlessly */
    }
    scif_puts("VIDPIN load="); scif_puthex(save[1]);
    scif_puts(" ret="); scif_puthex((unsigned int)r); scif_puts("\n");
    return r;
}
/* T7 ROUND 4: VBL-SPIN -- boot-gap spinner driven by the game's own
 * interrupt callback. Round 2's cart-read spinner was design-dead (the gap
 * has no cart reads; first read lands ~0.1 s before the game's first scene
 * flip -- phase5-hardware.md loadbar-v1 timeline). But the vblank ISR IS
 * live all gap: fork GAPISR probe measured 203 ISTNRM vblank acks across
 * the ~3.4 s window (~60 Hz), every one through the callback fn 0x8c038f00
 * called by the list-walker dispatcher at 0x8c02bf12 (jsr @r3 / r4 =
 * node->arg; return pr=8c02bf18). The game registers that fn through a
 * SINGLE literal-pool word (0x8c0391cc, whole-.dat scan: one hit, main
 * image only -- test image links its own copy without the literal, left
 * stock). Patch VBL-SPIN repoints it here, so the game installs THIS
 * wrapper as its interrupt callback at its own registration site.
 *
 * Contract: dispatcher passes only r4 (the C arg); the original callee
 * proves it (reads r4, sets r5 itself first thing). Plain C keeps that
 * contract -- GCC preserves idx across the tick and tail-jumps to the
 * original. Strictly integer code: ISR context, and the SDK's callback
 * convention saves no FPU state for us (same rule as mtramp.S).
 *
 * The tick self-gates on FB_R_SOF1 == 0x260000 (our splash copy on scan):
 * active from the side-buffer repoint above until the game's first scene
 * flip, then permanently inert (one PVR read + compare per interrupt).
 * Draws only into OUR copy -- can never deface a game frame. One step per
 * 8 calls ~= 60 Hz vblank / 8 = 1.07 s per rotation; ~3 rotations per gap.
 * Statics may start as garbage if .bss init ever changes -- harmless: pos
 * is masked, the counter only paces the rotation.
 *
 * T7 ROUND 5 (operator round-4 verdict: gap BLACK ~3 s, splash+ring only
 * FLASHES right before the game's scene): on real hardware the one-shot
 * wrapper-exit unblank does not stick -- what the operator saw was the
 * game's own display-on arm (the round-1 "former unblank moment",
 * pr=8c03538e) revealing our copy for the last fraction of a second.
 * Mechanism unidentified: the emulator shows no VO_CONTROL/FB_R_CTRL
 * writes in the gap interior (blank-edge census identical rounds 2-4),
 * so whatever re-blanks is hardware-path-only. HINDSIGHT: the round-2/3
 * hardware reports ("I see the text on the second splash") are equally
 * consistent with this end-of-gap flash -- "splash persists on HW" was
 * never operator-confirmed, only inferred. Defense, since we now own
 * per-vblank execution: run the ORIGINAL handler first, then, while the
 * window is open, RE-ASSERT display-on every vblank -- clear VO_CONTROL
 * bit3 (blank) if set, set FB_R_CTRL bit0 (fb read enable) if clear.
 * Whatever turns the display off is corrected within one frame, one-shot
 * or periodic; after the game's flip the re-assert arm is inert like the
 * spinner. Writes are conditional (normally zero extra PVR writes per
 * vblank). The game's own gap-end 5->4->5 FB toggle stays untouched
 * in-line; worst interleave is our bit0 set between its 4 and 5 writes --
 * same final state. */
static void spinner_vbl(void) {
    static unsigned int spin_calls, spin_last;
    volatile unsigned int *pvr = (volatile unsigned int *)0xa05f8000;
    unsigned int on_copy = (pvr[0x50 / 4] == 0x00260000u);
    if (!on_copy && !splash_live) return;        /* round 7: copy window counts too */
    unsigned int vo = pvr[0xe8 / 4];             /* VO_CONTROL */
    if (vo & 8u) pvr[0xe8 / 4] = vo & ~8u;       /* re-assert unblank */
    unsigned int fbc = pvr[0x44 / 4];            /* FB_R_CTRL */
    if (!(fbc & 1u)) pvr[0x44 / 4] = fbc | 1u;   /* re-assert fb read on */
    if (!on_copy) return;                        /* draw only into OUR copy */
    unsigned int pos = (++spin_calls >> 3) & 7u;
#if SHIM_VBLROW
    /* diag knob: one 2x2 dot per tick along row 470 of the copy -- a flash
     * photo then reads out how many ticks ran on hardware. Never ship. */
    {
        volatile unsigned short *rp = (volatile unsigned short *)0xa5260000u
            + 470 * 640 + ((spin_calls * 2u) % 636u);
        rp[0] = rp[1] = rp[640] = rp[641] = 0xf345;
    }
#endif
    if (pos == spin_last) return;
    spin_last = pos;
    /* 8 dots on a radius-14 ring centered (320,410) -- lifted from 445 in
     * round 6, operator: too close to the screen bottom on a real CRT --
     * 4x4 px each, sized/toned to survive 480i flicker + composite blur */
    static const signed char dx[8] = { 0, 10, 14, 10, 0, -10, -14, -10 };
    static const signed char dy[8] = { -14, -10, 0, 10, 14, 10, 0, -10 };
    for (unsigned int i = 0; i < 8; i++) {
        unsigned short c = (i == pos) ? 0xf345 : 0xad55; /* orange / gray */
        volatile unsigned short *fb = (volatile unsigned short *)0xa5260000u
            + (410 + dy[i]) * 640 + (320 + dx[i]);
        for (unsigned int y = 0; y < 4; y++)
            for (unsigned int x = 0; x < 4; x++) fb[y * 640 + x] = c;
    }
}
void shim_int_spin(unsigned int idx);
void shim_int_spin(unsigned int idx) {
    /* round 5: original FIRST -- if anything in the game's own vblank path
     * turns the display off, our re-assert runs after it, not before. */
    ((void (*)(unsigned int))0x8c038f00)(idx);
    spinner_vbl();
}

int shim_vid_init_main(unsigned int mode, unsigned int b, unsigned int c, unsigned int d) {
    return vid_init_pinned((int (*)(unsigned int, unsigned int, unsigned int,
                                    unsigned int))0x8c03d48e, mode, b, c, d);
}
int shim_vid_init_test(unsigned int mode, unsigned int b, unsigned int c, unsigned int d) {
    return vid_init_pinned((int (*)(unsigned int, unsigned int, unsigned int,
                                    unsigned int))0x8c03cf0e, mode, b, c, d);
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

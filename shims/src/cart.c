/* Cart/G1 service -- the shim half of the register mirror (Task 10).
 *
 * The patch table repoints every cart/G1 register constant in senkosp's image
 * to G1_MIRROR (docs/kb/phase4-conversion.md §Cart-patch sites), so the game's
 * DMA programming writes shim RAM instead of Dreamcast G1 registers. Nothing
 * traps a RAM store, so four function entries are hooked to turn those mirrored
 * writes back into real work; the four sites and their ABIs are pinned in the
 * KB's "Four entry hooks" table, and the ABIs DIFFER (r4/r5 mean different
 * things at each site), which is why this file has four entry points over one
 * shared core rather than the single helper §CART-PIO floats:
 *
 *   CART-WAIT-A  FUN_8c027e5e(r4=snapshot flag, r5=obj)  -> shim_cart_service
 *   CART-WAIT-B  FUN_8c027e34(r4=obj)                    -> shim_cart_settle
 *   CART-BOOT-DMA boot_cart_dma(r4=off,r5=dst,r6=len,r7=async) -> shim_cart_boot_dma
 *   CART-PIO-READ pio_read(r4=off, r5=dst, r6=len)       -> shim_cart_pio
 *
 * A single helper reading r5 as `obj` would read a scratch register at
 * CART-WAIT-B and a destination pointer at the two boot sites -- i.e. it would
 * write the game's completion flags through whatever happened to be in r5.
 *
 * All four are ENTRY hooks (generator `hook()` kind): the thunk sits at the
 * function's first instruction and jumps, so the original body never runs and
 * the plain SH-4 ABI applies (r0 clobbered by the thunk, r4-r7 = the args, PR
 * = the caller's return address). No mid-body detour discipline is involved.
 */
#include "shim_iface.h"
typedef unsigned int u32;

/* Mirror cell offsets. G1_MIRROR fakes physical 0x5f7000-0x5f77ff, so
 * mirror + (reg & 0x7ff) is the cell for register 0x5f7xxx -- the same rule
 * the generator computes `new = G1_MIRROR_P2 + (old & 0x7ff)` with. */
#define M_DMA_OFFH  0x00c   /* NAOMI_DMA_OFFSETH: cart source, high half + mode bits */
#define M_DMA_OFFL  0x010   /* NAOMI_DMA_OFFSETL: cart source, low half */
#define M_GDSTAR    0x404   /* SB_GDSTAR: destination */
#define M_GDLEN     0x408   /* SB_GDLEN:  byte length (sole length source) */
#define M_GDST      0x418   /* SB_GDST:   1 = transfer outstanding, 0 = done */
#define M_GDLEND    0x4f8   /* SB_GDLEND: bytes transferred so far */

/* Fence for a mirrored destination. The shim window, its register mirrors and
 * the pre-placed Naomi BIOS 0x60000 library all sit at the BOTTOM of RAM in
 * this port (shim_iface.h), so the guard is a FLOOR -- not Cleopatra's ceiling,
 * whose shim lived at 0x8cfc0000. Upper bound is the DC's 16 MB line; the
 * relocation patches (scripts/reloc_patchset.json) put every streaming corridor
 * under it, so a destination above it means the heap-top seed did not take. */
#define DEST_LO  ((BIOS60000_DST + BIOS60000_LEN) & 0x1fffffff)   /* 0x0c01f000 */
#define DEST_HI  0x0d000000u

void shim_die(u32, u32, u32);
int gd_read_cart(unsigned cart_off, void *dst, unsigned len);   /* gd.c: the tested path */
extern u32 gd_last_err;                       /* gd.c: 0xda<site><status><error> */
void scif_puts(const char *); void scif_puthex(u32);
void shim_mark(u32 slot, unsigned short color);   /* util.c: breadcrumb HUD */

#ifndef SHIM_TRACE
#define SHIM_TRACE 0            /* per-read serial; ~2-3 ms SCIF spin each on real HW */
#endif

/* .data (non-zero init, house style: the loader zero-fills the shim window, so
 * a .bss counter would also start at 0 -- but the convention keeps every shim
 * counter's "never ran" value distinguishable from "ran zero times"). */
u32 cart_count = 1;             /* streams completed + 1 (HUD slot 4/5 blinker) */

/* No progress-bar paints here (Task 26 v2): senkosp blanks + reprograms video
 * BEFORE its first cart read (KAMUI2 writer pc=8c032140 blanks at
 * loadbar-smoke2 21:48:00.003; first cart stream 21:48:03.319), and the boot
 * burst then lands under the game's own FB-drawn NOW LOADING screen -- HW
 * 2026-08-31: per-read paints splat a bar on top of it. Cleopatra streamed its
 * preload before touching video; this game inverts the order, so the bar
 * lives in loader/main.c (the loader's own disc load), not in the shim. */

/* Request fence, on EVERY read path. gd_read_cart validates the cart offset
 * (gd.c:319-321) but never the destination, so this is the last line
 * protecting the shim window, its register mirrors and the pre-placed 0x60000
 * blob from a wild game-supplied `dest`. Length sanity comes FIRST so an
 * absurd length cannot u32-wrap past the `+ len` comparisons. Callers handle
 * len == 0 themselves (both native boot bodies return early on it, so a die
 * there would be a regression, not a catch). */
static void fence_or_die(u32 off, u32 dest, u32 len) {
    if (!len || len > 0x01000000u || off + len > (u32)CART_SIZE ||
        (dest & 0x1f000000u) != 0x0c000000u ||
        dest < DEST_LO || dest + len > DEST_HI)
        shim_die(2, off, dest);
}

/* Both boot bodies compose their cart offset as
 *   (r4 >> 16) | *(u32 *)0x8c1bf18c | mode_bit
 * into NAOMI_DMA_OFFSETH / NAOMI_ROM_OFFSETH (docs/kb/phase4-conversion.md
 * §CART-BOOT-POOLS 8c06645c/8c066480 and §CART-PIO 8c0663fe, both
 * byte-verified there). The hardware keeps the low bits of that word as real
 * cart-offset bits 16..30 -- naomi_cart.cpp:1032-1034 (`DmaOffset |= (data &
 * 0x7fff) << 16`) and :1010-1013 (`RomPioOffset |= (data << 16) &
 * 0x7fff0000`) -- so `r4` alone is only the whole offset while that runtime
 * word's low half is zero. It lives at 0x8c1bf18c, past the main image's end,
 * i.e. it is written at runtime and unknowable statically.
 *
 * ponytail: die rather than OR it in. Neither boot path has ever been observed
 * executing (all 672 Phase 3 kicks are the steady path's 0x8c027f72), so a
 * non-zero base would mean the offset model for these hooks is unvalidated --
 * this word could be a board-window base that does not map onto a flat .dat
 * offset at all. ORing would silently read the wrong region on a guess; the
 * die paints the value and lands the operator in the debug-loop protocol with
 * the one number needed to decide. Upgrade path: if a leg ever trips this,
 * decode 0x8c1bf18c's writer, then OR (or translate) here.
 * cart_stream is unaffected -- it reads the mirror the game already OR'd. */
#define CART_BASE_WORD (*(volatile u32 *)0x8c1bf18c)
static void boot_base_or_die(u32 off) {
    u32 base = CART_BASE_WORD;
    if (base & 0x7fffu) shim_die(2, off, base);   /* bits the HW folds into the offset */
}

/* The one place a mirrored DMA turns into a disc read. Returns immediately if
 * nothing is outstanding, which is what makes it safe at the two settle/boot
 * sites as well as the steady wait.
 *
 * Destination is written UNCACHED (gd_read_cart writes its dst through P2):
 * the game reads streamed assets uncached or hands them to PVR/TA/AICA DMA --
 * real-DMA semantics, matching the original path, which does no cache op. Via
 * P1 the bytes would sit dirty in the D-cache while RAM stayed stale.
 */
static void cart_stream(void) {
    volatile u32 *m = P2(G1_MIRROR);
    if (!(m[M_GDST / 4] & 1u)) return;       /* no DMA outstanding -> nothing to do */

    /* Cart-relative byte offset. The high half carries mode bits the hardware
     * masks off (naomi_cart.cpp:1032-1034 keeps only DmaOffset bits 16..30,
     * and GetDmaPtr uses `DmaOffset & 0x1fffffff` as a BYTE offset,
     * naomi_cart.cpp:912-919), e.g. the boot driver's 0xa000 and the PIO
     * reader's 0x8000; 0x0fffffff drops them and still spans the 251 MB
     * image. Any base word the game OR'd in is already part of this value. */
    u32 off  = (((m[M_DMA_OFFH / 4] & 0xffffu) << 16)
                | (m[M_DMA_OFFL / 4] & 0xffffu)) & 0x0fffffffu;
    u32 len  = m[M_GDLEN / 4];               /* SB_GDLEN is the sole length source */
    /* Game programs SB_GDSTAR P1-aliased -> physical; hardware then transfers
     * to `SB_GDSTAR & 0x1FFFFFE0` (naomi.cpp:507), so round down the same way.
     * A no-op on every request observed so far (all 0x20-aligned). */
    u32 dest = m[M_GDSTAR / 4] & 0x1fffffe0;

    fence_or_die(off, dest, len);

    if (cart_count == 1) shim_mark(4, 0xf81f);          /* slot4 magenta: first stream */
    if ((++cart_count & 31u) == 0)                      /* slot5: activity blinker */
        shim_mark(5, (cart_count & 32u) ? 0xffe0 : 0x001f);
    if (SHIM_TRACE) {
        scif_puts("CART off="); scif_puthex(off);
        scif_puts(" len=");     scif_puthex(len);
        scif_puts(" dst=");     scif_puthex(dest);
        scif_puts(" n=");       scif_puthex(cart_count);
        scif_puts("\n");
    }

    if (gd_read_cart(off, (void *)(dest | 0xa0000000u), len) < 0)
        shim_die(4, off, gd_last_err);

    /* Completion, in the order a poller can safely observe it: the transfer
     * counter first, then the busy flag the game spins on. SB_GDLEND is reset
     * to 0 at kick and converges to `(SB_GDLEN + 31) & ~31` -- the hardware
     * moves whole 32-byte bursts (naomi.cpp:508, :131-134) -- so that, not
     * `len`, is the finished value. Identical for every request observed so
     * far (all 32-byte-aligned lengths). */
    m[M_GDLEND / 4] = (len + 31u) & ~31u;
    m[M_GDST / 4] = 0;
}

/* Plausibility guard for a game object pointer handed to us in a register: P1
 * main RAM only. A hook fired with a wild pointer must not write completion
 * flags into MMIO or over the shim. */
static int obj_ok(u32 o) { return (o - 0x8c000000u) < 0x01000000u && (o & 3u) == 0; }

/* CART-WAIT-A: replaces FUN_8c027e5e, "wait until this DMA is done"
 * (r4 = snapshot flag, r5 = obj). This is where the steady path's streaming
 * actually happens -- it is reached from both kick paths (directly from the
 * confirmed kick FUN_8c027f54, and from the drain loop FUN_8c027f9a).
 * The original's observable effects, reproduced: obj->[0x5c] takes SB_GDLEND
 * when the caller asked for a progress snapshot, and obj->[0x60] (the
 * "waiting" latch it sets on entry) is left clear on return.
 * Deliberately NOT reproduced: the native early-out on the obj->[0x70]
 * error/abort latch. It only decides whether the original loops again; this
 * hook never loops -- it services once and returns -- and its exit state
 * (obj->[0x60] = 0) is the same on both native branches. */
void shim_cart_service(u32 flag, u32 obj);
void shim_cart_service(u32 flag, u32 obj) {
    cart_stream();
    if (obj_ok(obj)) {
        volatile u32 *o = (volatile u32 *)obj;
        if (flag) o[0x5c / 4] = *P2(G1_MIRROR + M_GDLEND);
        o[0x60 / 4] = 0;
    }
}

/* CART-WAIT-B: replaces FUN_8c027e34, "settle/abort the current DMA"
 * (r4 = obj). Needed because its native body clears the mirrored SB_GDEN and
 * then spins on the mirrored SB_GDST -- on hardware clearing GDEN aborts the
 * transfer and clears GDST (Naomi_DmaEnable, naomi.cpp:533-542), in RAM that
 * write does nothing and the spin never ends. Draining rather than aborting is
 * deliberate: FUN_8c027d7e kicks without waiting, so a pending transfer here is
 * one whose data the game still expects. */
void shim_cart_settle(u32 obj);
void shim_cart_settle(u32 obj) {
    cart_stream();
    if (obj_ok(obj)) ((volatile u32 *)obj)[0x7c / 4] = 0;
}

/* CART-BOOT-DMA: replaces the boot cart DMA routine at 0x8c066440
 * (r4 = cart offset rounded down to 0x20, r5 = destination, r6 = byte length,
 * r7 != 0 = fire-and-forget). Not observed executing in any Phase 3 leg (all
 * 672 logged kicks are the steady path's 0x8c027f72) but genuinely reachable --
 * two bsr callers. Implemented as a real read rather than the KB's suggested
 * "nothing pending -> return": the entry hook means the native body never
 * programs anything, so a mirror-driven no-op would hand the caller an
 * unfilled buffer, which is the silent-corruption failure mode the KB itself
 * wants avoided. Leaves the mirror untouched -- it never kicked. */
void shim_cart_boot_dma(u32 off, u32 dst, u32 len, u32 async);
void shim_cart_boot_dma(u32 off, u32 dst, u32 len, u32 async) {
    (void)async;                                        /* we are always synchronous */
    if (!len) return;                                   /* native: tst r6,r6 ; bt/s 8c0664ae */
    shim_mark(6, 0x07e0);                               /* slot6 green: boot DMA path fired */
    off &= ~0x1fu;                                      /* native: and r2,r4 at 8c06644a */
    dst &= 0x1fffffe0u;                                 /* native: SB_GDSTAR & 0x1FFFFFE0 */
    boot_base_or_die(off);
    fence_or_die(off, dst, len);
    if (gd_read_cart(off, (void *)(dst | 0xa0000000u), len) < 0)
        shim_die(4, off, gd_last_err);
}

/* CART-PIO-READ: replaces the boot PIO reader at 0x8c0663e6
 * (r4 = cart offset, r5 = destination, r6 = byte length). Its native loop
 * re-reads mirror[0x008] expecting the hardware's read-side auto-increment
 * (naomi_cart.cpp:953-955), which RAM does not do: unhooked it would fill the
 * buffer with one repeated half-word. Statically unreachable (no bsr and no
 * 32-bit word in either image targets it), kept because that failure mode is
 * silent. */
void shim_cart_pio(u32 off, u32 dst, u32 len);
void shim_cart_pio(u32 off, u32 dst, u32 len) {
    if (!len) return;                                   /* native: r6>>1 == 0 exits at once */
    shim_mark(7, 0x07ff);                               /* slot7 cyan: PIO path fired */
    boot_base_or_die(off);
    /* dst is a CPU address here (the native loop does `mov.w r2,@r5`), not a
     * DMA physical -- mask to physical for the fence, and no 32-byte rounding:
     * the PIO path stores half-words at whatever address it is handed. */
    fence_or_die(off, dst & 0x1fffffffu, len);
    if (gd_read_cart(off, (void *)(dst | 0xa0000000u), len) < 0)
        shim_die(4, off, gd_last_err);
}

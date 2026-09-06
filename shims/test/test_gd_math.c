/* Host test of gd.c's pure splitter math (gd_plan): byte offset into the cart
 * image -> (first FAD, head skip/len, whole-sector body, tail len).
 * Build (shims/Makefile `test`):
 *   cc -DHOST_TEST -Iinclude -o build/test_gd_math test/test_gd_math.c src/gd.c
 * gd.c compiles its MMIO half out under HOST_TEST, so this links against the
 * REAL function the shim runs -- not a copy. */
#define HOST_TEST 1
#include "../include/shim_iface.h"
#include <assert.h>
#include <stdio.h>

/* Same members, same order as gd.c's definition (they are separate TUs; gd.c's
 * copy carries the matching "keep in sync" note). */
struct plan { unsigned fad, head_skip, head_len, body_secs, tail_len; };
struct plan gd_plan(unsigned cart_off, unsigned len);   /* from gd.c, pure */
unsigned int shim_crc32(const void *p, unsigned len);   /* from gd.c, pure */
struct pf_cut { unsigned idx, first; };                 /* keep in sync (gd.c) */
int pf_hit_plan(unsigned lo, unsigned hi, unsigned off, unsigned len,
                struct pf_cut *c);                      /* from gd.c, pure */

int main(void) {
    /* --- the task brief's three cases ---------------------------------- */
    struct plan p = gd_plan(0, 2048);                 /* aligned single sector */
    assert(p.fad == CART_FAD && p.head_len == 0 && p.body_secs == 1 && p.tail_len == 0);
    p = gd_plan(100, 100);                            /* inside one sector */
    assert(p.fad == CART_FAD && p.head_skip == 100 && p.head_len == 100 && p.body_secs == 0);
    p = gd_plan(2048 + 10, 4096);                     /* head + body + tail */
    assert(p.fad == CART_FAD + 1 && p.head_skip == 10 && p.head_len == 2038
        && p.body_secs == 1 && p.tail_len == 10);

    /* --- edge cases ----------------------------------------------------- */
    /* zero length: no head, no body, no tail => gd_read_cart issues no I/O */
    p = gd_plan(1000, 0);
    assert(p.head_len == 0 && p.body_secs == 0 && p.tail_len == 0);
    /* sector-aligned sub-sector read: no head, the partial goes to the TAIL
       (both partial paths run through SHIM_BOUNCE, so this costs nothing) */
    p = gd_plan(4096, 100);
    assert(p.fad == CART_FAD + 2 && p.head_skip == 0 && p.head_len == 0
        && p.body_secs == 0 && p.tail_len == 100);
    /* head fills exactly to the sector boundary, then whole sectors */
    p = gd_plan(2048 - 64, 64 + 2048);
    assert(p.fad == CART_FAD && p.head_len == 64 && p.body_secs == 1 && p.tail_len == 0);
    /* head + tail, no body (crosses exactly one boundary) */
    p = gd_plan(2048 - 32, 32 + 100);
    assert(p.head_skip == 2016 && p.head_len == 32 && p.body_secs == 0 && p.tail_len == 100);
    /* single byte, last byte of a sector */
    p = gd_plan(2047, 1);
    assert(p.fad == CART_FAD && p.head_skip == 2047 && p.head_len == 1
        && p.body_secs == 0 && p.tail_len == 0);
    /* multi-sector aligned run: pure body, no bounce */
    p = gd_plan(4096, 4096);
    assert(p.fad == CART_FAD + 2 && p.head_len == 0 && p.body_secs == 2 && p.tail_len == 0);
    /* 1 MB stream (the boot-preload shape): 512 sectors, no partials, and the
       sector count must not overflow on the way */
    p = gd_plan(0, 0x100000);
    assert(p.body_secs == 512 && p.head_len == 0 && p.tail_len == 0);

    /* --- the far end of the cart --------------------------------------- */
    /* CART_SIZE is a whole number of sectors, so the last legal read ends on a
       sector boundary; the FAD must not run past the image's last sector.
       (gd_read_cart -- not gd_plan -- rejects off+len > CART_SIZE; it cannot be
       tested here because it drives MMIO. See gd.c §gd_read_cart.) */
    assert(CART_SIZE % 2048 == 0);
    p = gd_plan(CART_SIZE - 2048, 2048);
    assert(p.fad == CART_FAD + CART_SIZE / 2048 - 1);
    assert(p.head_len == 0 && p.body_secs == 1 && p.tail_len == 0);
    p = gd_plan(CART_SIZE - 1, 1);                    /* last byte of the image */
    assert(p.fad == CART_FAD + CART_SIZE / 2048 - 1 && p.head_skip == 2047
        && p.head_len == 1 && p.body_secs == 0 && p.tail_len == 0);

    printf("PASS test_gd_math gd_plan\n");

    /* CRC-32/IEEE check vector (zlib.crc32 compatible) */
    assert(shim_crc32("123456789", 9) == 0xcbf43926u);
    assert(shim_crc32("", 0) == 0u);

    printf("PASS test_gd_math shim_crc32\n");

    /* --- pf_hit_plan (phase 7 T3 prefetch window math) ------------------- */
    struct pf_cut c;
    /* whole request inside the window, no ring wrap */
    assert(pf_hit_plan(0x10000, 0x20000, 0x10800, 0x9800, &c) == 1
        && c.idx == 0x0800 && c.first == 0x9800);
    /* exact window: [lo, hi) fully consumed */
    assert(pf_hit_plan(0x10000, 0x19800, 0x10000, 0x9800, &c) == 1
        && c.idx == 0x0000 && c.first == 0x9800);
    /* the T2 drip shape at a ring-wrapping position: request straddles the
       64 KB ring edge -> two segments, first up to the edge */
    assert(pf_hit_plan(0x1c000, 0x2c000, 0x1c800, 0x9800, &c) == 1
        && c.idx == 0xc800 && c.first == 0x3800);   /* 0x10000 - 0xc800 */
    /* misses: before the window, past the window, overrunning hi */
    assert(pf_hit_plan(0x10000, 0x20000, 0x0f800, 0x800, &c) == 0);
    assert(pf_hit_plan(0x10000, 0x20000, 0x20000, 0x800, &c) == 0);
    assert(pf_hit_plan(0x10000, 0x20000, 0x1f000, 0x1800, &c) == 0);
    /* off far past hi: hi - off would underflow -- the guard-order case */
    assert(pf_hit_plan(0x10000, 0x20000, 0xf0000000u, 0x800, &c) == 0);
    /* empty window never hits; len 0 is a miss by fiat */
    assert(pf_hit_plan(0x800, 0x800, 0x800, 0x800, &c) == 0);
    assert(pf_hit_plan(0x10000, 0x20000, 0x10000, 0, &c) == 0);
    /* 1-byte request at the last window byte */
    assert(pf_hit_plan(0x10000, 0x20000, 0x1ffff, 1, &c) == 1
        && c.idx == 0xffff && c.first == 1);

    printf("PASS test_gd_math pf_hit_plan\n");
    return 0;
}

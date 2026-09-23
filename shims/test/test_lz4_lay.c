/* Host test of the T10b chunk-layout math (lz4_lay.c, pure -- no MMIO).
 * Build (shims/Makefile `test`):
 *   cc -Iinclude -o build/test_lz4_lay test/test_lz4_lay.c src/lz4_lay.c
 * Links the REAL function the shim runs (same idiom as test_gd_math.c). */
#include "../include/lz4_lay.h"
#include <assert.h>
#include <stdio.h>

/* Invariant checked for every chunk (spec §Safety invariants): output
 * through chunk i must end at or below the start of the not-yet-consumed
 * compressed input, both expressed as offsets into the ulen-sized dest. */
static void check_entry(const struct lz4pak_entry *e) {
    unsigned base_off = e->ulen - e->r_bytes;    /* dest offset of the DMA window */
    struct lz4_lay L, N;
    for (unsigned i = 0; i < e->nchunk; i++) {
        assert(lz4pak_lay(e, i, &L) == 0);
        unsigned a = (L.csize + 31u) & ~31u;
        assert(L.lend_target == L.in_off + a);           /* target = own input end */
        assert(L.out_off == i * LZ4PAK_CHUNK);
        assert(L.usize <= LZ4PAK_CHUNK && L.usize > 0);
        if (L.stored) assert(L.csize == L.usize);        /* stored = raw bytes */
        assert(a <= L.usize);                            /* the mastering rule */
        if (i + 1 < e->nchunk) {
            assert(lz4pak_lay(e, i + 1, &N) == 0);
            assert(N.in_off == L.in_off + a);            /* stream is contiguous */
            /* in-place safety: output end <= next unconsumed input start */
            assert(L.out_off + L.usize <= base_off + N.in_off);
        } else {
            assert(L.out_off + L.usize == e->ulen);      /* last chunk lands flush */
        }
    }
    assert(lz4pak_lay(e, e->nchunk, &L) == -1);          /* index off the end */
}

int main(void) {
    /* Case 1: two LZ4 chunks + one stored tail, hand-computed layout.
     * u = {131072, 131072, 30720}; c = {1000, 131040, 30720(stored)}
     * a = {1024, 131040, 30720}; S = 162784; R = 163840; front_pad = 1056 */
    static const struct lz4pak_chunk c1[3] = {
        {1000u, 0x11111111u}, {131040u, 0x22222222u},
        {30720u | LZ4PAK_STORED, 0x33333333u},
    };
    struct lz4pak_entry e1 = { 0x0935a800u, 292864u, 574604u,
                               163840u, 1056u, 3u, c1 };
    check_entry(&e1);
    struct lz4_lay L;
    lz4pak_lay(&e1, 0, &L);
    assert(L.in_off == 1056u && L.out_off == 0 && L.usize == 131072u
        && L.csize == 1000u && !L.stored && L.lend_target == 1056u + 1024u);
    lz4pak_lay(&e1, 2, &L);
    assert(L.stored && L.csize == 30720u && L.usize == 30720u
        && L.in_off == 1056u + 1024u + 131040u);

    /* Case 2: everything stored (worst case: incompressible pak).
     * a_i = u_i, S = ulen, R = ulen (already sector-aligned), front_pad 0.
     * Every in_off must equal its out_off: copy is src == dst, a no-op. */
    static const struct lz4pak_chunk c2[2] = {
        {131072u | LZ4PAK_STORED, 0}, {131072u | LZ4PAK_STORED, 0},
    };
    struct lz4pak_entry e2 = { 0u, 262144u, 574604u, 262144u, 0u, 2u, c2 };
    check_entry(&e2);
    lz4pak_lay(&e2, 1, &L);
    assert(L.in_off == L.out_off);

    /* Case 3: single full chunk, heavy compression, big front pad.
     * c = 100; a = 128; S = 128; R = 2048; front_pad = 1920 */
    static const struct lz4pak_chunk c3[1] = { {100u, 0} };
    struct lz4pak_entry e3 = { 0u, 131072u, 574604u, 2048u, 1920u, 1u, c3 };
    check_entry(&e3);

    printf("test_lz4_lay: all invariants PASS\n");
    return 0;
}

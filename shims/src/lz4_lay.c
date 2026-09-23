/* T10b chunk-layout math -- pure, host-tested (test/test_lz4_lay.c).
 * The in-place safety argument (spec §Safety invariants): the mastering
 * rule align32(csize) <= usize per chunk makes output-through-chunk-N end
 * at or below the start of the unconsumed compressed input, so the CPU
 * never overruns bytes the DMA has not delivered and never clobbers input
 * it has not consumed. This file only computes; the pack tool enforces. */
#include "lz4_lay.h"

static unsigned a32(unsigned c) { return (c + 31u) & ~31u; }

int lz4pak_lay(const struct lz4pak_entry *e, unsigned i, struct lz4_lay *L) {
    if (i >= e->nchunk) return -1;
    unsigned pos = e->front_pad, out = 0, j;
    /* ponytail: O(i) rescan per call, O(n^2) over 64 chunks -- microseconds
     * against a 0.77 s transfer; a running cursor would add caller state. */
    for (j = 0; j < i; j++) {
        pos += a32(e->chunks[j].csize_flags & LZ4PAK_CSIZE_MASK);
        out += LZ4PAK_CHUNK;
    }
    L->csize = e->chunks[i].csize_flags & LZ4PAK_CSIZE_MASK;
    L->stored = (e->chunks[i].csize_flags & LZ4PAK_STORED) != 0;
    L->bounced = (e->chunks[i].csize_flags & LZ4PAK_BOUNCE) != 0;
    L->in_off = pos;
    L->out_off = out;
    L->usize = e->ulen - out < LZ4PAK_CHUNK ? e->ulen - out : LZ4PAK_CHUNK;
    L->lend_target = pos + a32(L->csize);
    return 0;
}

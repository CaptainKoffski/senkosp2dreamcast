/* LZ4-PRIVATE memcpy/memmove/memset for build/lz4_dec.o (the vendored
 * LZ4_decompress_safe): gcc lowers variable-length __builtin_memcpy to a
 * libc call and the shim links -nostdlib, so the symbols must exist here.
 * Word fast path when co-aligned -- LZ4 literal runs are the hot caller;
 * the fixed-size (8/16 B) wildcopy calls inline and never reach these.
 *
 * Named lz4_* and NOT memcpy/memset on purpose: src/util.c:9-18 already
 * defines shim-wide byte-loop memcpy/memset, so the plain names would
 * collide at link -- and util.c's must not change, or a knob-off build's
 * bytes move and gate 5's A/B fails. lz4.c's calls are redirected onto
 * these by --redefine-sym in the shims/Makefile lz4_dec.o recipe.
 * SHIM_LZ4 builds only (shims/Makefile conditional SRCS). */
#include <stddef.h>

void *lz4_memcpy(void *d, const void *s, size_t n) {
    unsigned char *dp = (unsigned char *)d;
    const unsigned char *sp = (const unsigned char *)s;
    if ((((unsigned)dp | (unsigned)sp) & 3u) == 0)
        for (; n >= 4; n -= 4) {
            *(unsigned *)(void *)dp = *(const unsigned *)(const void *)sp;
            dp += 4; sp += 4;
        }
    while (n--) *dp++ = *sp++;
    return d;
}

void *lz4_memmove(void *d, const void *s, size_t n) {
    unsigned char *dp = (unsigned char *)d;
    const unsigned char *sp = (const unsigned char *)s;
    if (dp <= sp) return lz4_memcpy(d, s, n);
    dp += n; sp += n;
    while (n--) *--dp = *--sp;
    return d;
}

void *lz4_memset(void *d, int c, size_t n) {
    unsigned char *dp = (unsigned char *)d;
    while (n--) *dp++ = (unsigned char)c;
    return d;
}

/* T10b Amendment 4: span copy for the patched LZ4_wildCopy8 (lz4.c:465,
 * -DLZ4_SH4_WILDCOPY on the lz4_dec.o compile). The decode hot path was a
 * jsr-per-8-bytes loop plus an allocate-read RAM fetch on every output
 * line write-miss (OC = 16 KB direct-mapped copy-back write-allocate,
 * tools/kos/.../arch/cache.h:39-45); movca.l allocates the line WITHOUT
 * the fetch (SH7750 manual 4.2.5; KOS wraps the same instruction as
 * arch_dcache_alloc_line, arch/cache.h:83).
 *
 * Contract vs stock wildCopy8: copies exactly [d,e) -- NO 8-byte overrun
 * (strictly safer for the in-place margins). Callers guarantee effective
 * |d-s| >= 8; forward byte copy is overlap-safe for any distance >= 1.
 *
 * movca.l is issued only on 32-byte lines fully inside [d,e), so no byte
 * outside the requested span is ever touched. Distance >= 32 guarantees
 * the bytes read while filling a line never come from that line (matches
 * read >= 32 behind the write frontier -- already final; literals read
 * >= 32 ahead -- beyond the line). Mid-line interrupt eviction is
 * self-healing: the resuming store misses and allocate-reads the
 * written-back words before overwriting the rest; nothing reads decoder
 * output mid-decode. Dest is always P1 copy-back (game buffer or T3
 * ring; CCR_CB set, dc/cache.h:42 -- and the GAME's CCR governs after
 * handoff: P1 copy-back there is evidenced by this project's C1
 * dirty-writeback bug class itself, impossible under write-through),
 * the mode movca requires.
 * Spec: docs/superpowers/specs/...-t10b-lz4-pak-load-design.md Amd. 4. */
void lz4_sh4_wildcopy(void *dv, const void *sv, void *ev) {
    unsigned char *d = (unsigned char *)dv;
    const unsigned char *s = (const unsigned char *)sv;
    unsigned char *e = (unsigned char *)ev;
    unsigned dist = (d > s) ? (unsigned)(d - s) : (unsigned)(s - d);
    if (dist >= 32u && (unsigned)(e - d) >= 64u) {
        while ((unsigned)d & 31u) *d++ = *s++;           /* 32-align dst */
        if (((unsigned)s & 3u) == 0) {                   /* co-aligned */
            while ((unsigned)(e - d) >= 32u) {
                const unsigned *sw = (const unsigned *)(const void *)s;
                unsigned *dw = (unsigned *)(void *)d;
                __asm__ __volatile__("movca.l r0,@%1"
                    : : "z"(sw[0]), "r"(dw) : "memory");
                dw[1] = sw[1]; dw[2] = sw[2]; dw[3] = sw[3];
                dw[4] = sw[4]; dw[5] = sw[5]; dw[6] = sw[6]; dw[7] = sw[7];
                d += 32; s += 32;
            }
        } else {                          /* shift-merge from aligned words.
                                           * The word loads floor s to a
                                           * 4-byte boundary (read up to 3 B
                                           * below s, 3 B past the last src
                                           * byte): floor4(s) can never cross
                                           * below a source region's base,
                                           * because every base is 32-aligned
                                           * -- compressed-input starts
                                           * (align32 layout, lz4_lay.c),
                                           * match windows (chunk outputs at
                                           * 64 K multiples of the 32-aligned
                                           * dest), the ring (PF_RING_BASE).
                                           * Tail over-read stays inside the
                                           * span's own buffer. Out-of-span
                                           * bytes never land in a stored
                                           * word. */
            unsigned sa = (unsigned)s & 3u;
            unsigned shr = sa << 3, shl = 32u - shr;
            const unsigned *sw = (const unsigned *)(const void *)(s - sa);
            unsigned prev = *sw++;
            while ((unsigned)(e - d) >= 32u) {
                unsigned *dw = (unsigned *)(void *)d;
                unsigned c0 = sw[0], c1 = sw[1], c2 = sw[2], c3 = sw[3];
                unsigned c4 = sw[4], c5 = sw[5], c6 = sw[6], c7 = sw[7];
                __asm__ __volatile__("movca.l r0,@%1"
                    : : "z"((prev >> shr) | (c0 << shl)), "r"(dw) : "memory");
                dw[1] = (c0 >> shr) | (c1 << shl);
                dw[2] = (c1 >> shr) | (c2 << shl);
                dw[3] = (c2 >> shr) | (c3 << shl);
                dw[4] = (c3 >> shr) | (c4 << shl);
                dw[5] = (c4 >> shr) | (c5 << shl);
                dw[6] = (c5 >> shr) | (c6 << shl);
                dw[7] = (c6 >> shr) | (c7 << shl);
                prev = c7; sw += 8;
                d += 32; s += 32;
            }
        }
    }
    while (d < e) *d++ = *s++;                           /* exact tail */
}

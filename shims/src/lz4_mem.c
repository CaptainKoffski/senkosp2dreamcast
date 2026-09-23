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

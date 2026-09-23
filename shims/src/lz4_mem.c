/* Freestanding memcpy/memmove/memset for build/lz4_dec.o (the vendored
 * LZ4_decompress_safe): gcc lowers variable-length __builtin_memcpy to a
 * libc call and the shim links -nostdlib, so the symbols must exist here.
 * Word fast path when co-aligned -- LZ4 literal runs are the hot caller;
 * the fixed-size (8/16 B) wildcopy calls inline and never reach these.
 * SHIM_LZ4 builds only (shims/Makefile conditional SRCS). */
#include <stddef.h>

void *memcpy(void *d, const void *s, size_t n) {
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

void *memmove(void *d, const void *s, size_t n) {
    unsigned char *dp = (unsigned char *)d;
    const unsigned char *sp = (const unsigned char *)s;
    if (dp <= sp) return memcpy(d, s, n);
    dp += n; sp += n;
    while (n--) *--dp = *--sp;
    return d;
}

void *memset(void *d, int c, size_t n) {
    unsigned char *dp = (unsigned char *)d;
    while (n--) *dp++ = (unsigned char)c;
    return d;
}

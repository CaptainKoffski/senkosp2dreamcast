/* T10b transparent LZ4 pak load -- pure chunk-layout math, shared by the
 * shim (gd_lz4.inc.c), the host pack tool (tools/lz4pak/pack_paks.c) and
 * the host test. One implementation, three consumers -- a divergence is a
 * link failure, not a copy (the test_gd_math.c idiom).
 * Spec: docs/superpowers/specs/2026-09-23-t10b-lz4-pak-load-design.md */
#ifndef LZ4_LAY_H
#define LZ4_LAY_H

#define LZ4PAK_CHUNK   65536u         /* 64 KB -- exact T3-ring fit (execution
                                        * ruling 2026-09-23, spike's 131072
                                        * margin-pass was defective) */
#define LZ4PAK_STORED  0x80000000u    /* csize_flags bit: raw chunk, no LZ4 */
#define LZ4PAK_BOUNCE  0x40000000u    /* csize_flags bit: decode via T3 ring
                                        * (innermost kept-LZ4 chunk -- output
                                        * disjoint from input, no in-place
                                        * margin needed) */
#define LZ4PAK_CSIZE_MASK 0x3fffffffu

struct lz4pak_chunk {
    unsigned csize_flags;   /* exact compressed size | LZ4PAK_STORED | LZ4PAK_BOUNCE */
    unsigned crc32;         /* shim_crc32 of the PLAIN chunk (diag legs) */
};

struct lz4pak_entry {
    unsigned cart_off;      /* the (off,len) tuple this entry serves */
    unsigned ulen;
    unsigned blob_fad;      /* absolute FAD of the blob's first sector */
    unsigned r_bytes;       /* DMA length: sector-rounded padded stream */
    unsigned front_pad;     /* r_bytes - sum(align32(csize)) -- garbage head */
    unsigned nchunk;
    const struct lz4pak_chunk *chunks;
};

/* Chunk i's placement inside the served read: in_off/lend_target are
 * offsets into the r_bytes DMA window, out_off into the ulen dest. */
struct lz4_lay {
    unsigned in_off;        /* chunk's compressed stream start */
    unsigned out_off;       /* chunk's decompressed output start */
    unsigned usize;         /* plain size (LZ4PAK_CHUNK, short last chunk) */
    unsigned csize;         /* exact compressed size (== usize when stored) */
    unsigned stored;        /* 1 = raw copy, 0 = LZ4_decompress_safe */
    unsigned bounced;       /* 1 = decode via the T3 ring, not in-place */
    unsigned lend_target;   /* SB_GDLEND must reach this before decoding */
};

int lz4pak_lay(const struct lz4pak_entry *e, unsigned i, struct lz4_lay *L);

#endif

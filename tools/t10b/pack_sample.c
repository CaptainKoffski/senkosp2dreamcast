/* T10b spike (THROWAWAY): build the LZ4 benchmark sample blob.
 *
 * Carves NCHUNK stripes of CHUNK bytes from the T10 stage pak
 * (senkosp.dat 0x0935a800 + 0x7e7800 -- the window-B whole-pak tuple,
 * docs/kb/phase7-polishing.md par. T10), compresses each as an independent
 * LZ4-HC block (level 9), round-trip verifies with the SAME vendored
 * lz4.c the SH4 build uses, and emits a container the loader benchmark
 * (loader/lz4bench.c) walks.
 *
 * Container layout, all little-endian (SH4 on DC is LE):
 *   u32 magic 'L4B1'  u32 nchunk
 *   per chunk: u32 usize, u32 csize, u32 crc16 (naomi_eeprom_crc of plain)
 *   concatenated compressed blocks
 *
 * Build+run (host): see Makefile rule `t10b-sample`.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "lz4/lz4.h"
#include "lz4/lz4hc.h"
#include "../../loader/naomi_crc.h"

#define PAK_OFF 0x0935a800u
#define PAK_LEN 0x007e7800u
#define NCHUNK  8
#define CHUNK   (128 * 1024)

static void put32(FILE *f, unsigned v) {
    unsigned char b[4] = { v, v >> 8, v >> 16, v >> 24 };
    fwrite(b, 1, 4, f);
}

int main(int argc, char **argv) {
    if (argc != 3) { fprintf(stderr, "usage: pack_sample senkosp.dat out.bin\n"); return 2; }
    FILE *in = fopen(argv[1], "rb");
    if (!in) { perror(argv[1]); return 1; }

    static unsigned char plain[NCHUNK][CHUNK];
    static unsigned char comp[NCHUNK][CHUNK + CHUNK / 16];
    static unsigned char back[CHUNK];
    int csize[NCHUNK]; unsigned crc[NCHUNK];
    unsigned stride = ((PAK_LEN / NCHUNK) / 2048) * 2048;   /* stripe across the pak */
    long total_c = 0;

    for (int i = 0; i < NCHUNK; i++) {
        unsigned off = PAK_OFF + i * stride;
        if (fseek(in, off, SEEK_SET) || fread(plain[i], 1, CHUNK, in) != CHUNK) {
            fprintf(stderr, "read fail chunk %d @0x%x\n", i, off); return 1;
        }
        csize[i] = LZ4_compress_HC((char *)plain[i], (char *)comp[i], CHUNK, sizeof comp[i], 9);
        if (csize[i] <= 0) { fprintf(stderr, "compress fail chunk %d\n", i); return 1; }
        int u = LZ4_decompress_safe((char *)comp[i], (char *)back, csize[i], CHUNK);
        if (u != CHUNK || memcmp(plain[i], back, CHUNK)) {
            fprintf(stderr, "ROUND-TRIP FAIL chunk %d\n", i); return 1;
        }
        crc[i] = naomi_eeprom_crc(plain[i], CHUNK);
        total_c += csize[i];
        printf("chunk %d @0x%08x  %d -> %d (%.1f%%)  crc16=0x%04x\n",
               i, off, CHUNK, csize[i], 100.0 * csize[i] / CHUNK, crc[i]);
    }
    fclose(in);

    FILE *out = fopen(argv[2], "wb");
    if (!out) { perror(argv[2]); return 1; }
    put32(out, 0x3142344cu);            /* 'L4B1' */
    put32(out, NCHUNK);
    for (int i = 0; i < NCHUNK; i++) { put32(out, CHUNK); put32(out, csize[i]); put32(out, crc[i]); }
    for (int i = 0; i < NCHUNK; i++) fwrite(comp[i], 1, csize[i], out);
    fclose(out);

    printf("sample: %d x %d KB, total %ld -> ratio %.1f%%, ROUND-TRIP PASS\n",
           NCHUNK, CHUNK / 1024, total_c, 100.0 * total_c / (NCHUNK * (long)CHUNK));
    return 0;
}

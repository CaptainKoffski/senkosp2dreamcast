/* T10b spike (THROWAWAY, branch t10b-spike): SH4 LZ4-decompress benchmark.
 *
 * Question it answers: what is the real-hardware LZ4 block decompress rate
 * on this SH4, on real stage-pak data? The T10 window-B wall is 8.4 MB at
 * the measured 6.7 MB/s GDEMU DMA ceiling; shim-side transparent
 * compression only wins if decompress (overlapped with DMA) sustains
 * >= uncompressed_bytes / compressed_transfer_time ~= 10.9 MB/s.
 *
 * Runs at loader main() entry (before menu/handoff, RAM free, KOS live),
 * walks the embedded t10b_sample blob (8 x 128 KB real pak stripes,
 * LZ4-HC-9, built by tools/t10b/pack_sample.c): one correctness pass
 * (size + CRC16 per chunk, same naomi_eeprom_crc host and target), then
 * REPS timed walks, then a memcpy control of the same uncompressed volume.
 * One L4BENCH line on serial; emulator numbers are NOT evidence (Flycast
 * SH4 timing is a model) -- only the hardware leg's line counts.
 */
#ifdef LOADER_LZ4BENCH
#include <kos.h>
#include "naomi_crc.h"
#include "../tools/t10b/lz4/lz4.h"

extern uint8 t10b_sample[];         /* objcopy-embedded, see Makefile */
extern uint8 t10b_sample_end[];

#define REPS 4

static uint32 rd32(const uint8 *p) {
    return p[0] | (p[1] << 8) | (p[2] << 16) | ((uint32)p[3] << 24);
}

static uint8 dest[128 * 1024];
static uint8 dest2[128 * 1024];

void lz4bench_run(void) {
    const uint8 *p = t10b_sample;
    if (rd32(p) != 0x3142344cu) { dbglog(DBG_INFO, "L4BENCH bad magic\n"); return; }
    unsigned n = rd32(p + 4);
    const uint8 *tab = p + 8, *data = tab + n * 12;
    unsigned total_u = 0, total_c = 0, fail = 0;

    /* correctness pass: every chunk must decode to its host-recorded CRC */
    const uint8 *d = data;
    for (unsigned i = 0; i < n; i++) {
        unsigned us = rd32(tab + i * 12), cs = rd32(tab + i * 12 + 4);
        unsigned crc = rd32(tab + i * 12 + 8);
        int r = LZ4_decompress_safe((const char *)d, (char *)dest, cs, sizeof dest);
        if (r != (int)us || naomi_eeprom_crc(dest, us) != (unsigned short)crc) fail++;
        total_u += us; total_c += cs; d += cs;
    }

    uint64 t0 = timer_us_gettime64();
    for (int rep = 0; rep < REPS; rep++) {
        d = data;
        for (unsigned i = 0; i < n; i++) {
            unsigned cs = rd32(tab + i * 12 + 4);
            LZ4_decompress_safe((const char *)d, (char *)dest, cs, sizeof dest);
            d += cs;
        }
    }
    unsigned long lz4_us = (unsigned long)(timer_us_gettime64() - t0);

    /* sink defeats dead-store elimination -- without it -O2 deletes the
     * whole control loop (first smoke leg measured mc_us=0). */
    static volatile unsigned mc_sink;
    t0 = timer_us_gettime64();
    for (int rep = 0; rep < REPS; rep++)
        for (unsigned i = 0; i < n; i++) {
            memcpy(dest2, dest, sizeof dest);
            mc_sink += dest2[(rep * 37 + i) & 0xffff];
        }
    unsigned long mc_us = (unsigned long)(timer_us_gettime64() - t0);

    uint64 vol = (uint64)total_u * REPS * 1000000u / 1024u;
    dbglog(DBG_INFO,
           "L4BENCH n=%u u=%u c=%u fail=%u reps=%d lz4_us=%lu mc_us=%lu "
           "lz4=%lu KB/s memcpy=%lu KB/s\n",
           n, total_u, total_c, fail, REPS, lz4_us, mc_us,
           (unsigned long)(vol / (lz4_us ? lz4_us : 1)),
           (unsigned long)(vol / (mc_us ? mc_us : 1)));
}
#endif

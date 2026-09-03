/* GD_TEST_SERVER: a stand-in for isoldr's GD-ROM syscall server, installed
 * at the syscall vector by the loader's TESTSRV=1 build (loader/main.c,
 * right before handoff) instead of a real DreamShell card. TESTSRV builds
 * are test-only -- never shipped (top Makefile).
 *
 * Why this exists (task-6-report.md DEBUG ROUND 1 -> FIX ROUND 2): the
 * FORCE_SYSCALL leg's hang turned out to be environmental, not a gdstack.S
 * bug -- Flycast's real BIOS vector, after this port's own KERNEL-SLICE
 * stomp (shims/include/shim_iface.h KERNEL_DST/KERNEL_TOTAL_LEN), no longer
 * serves a real GD-ROM driver at all (E1/E3, task-6-report.md). This file
 * plugs a fake one back in at a resident-loader-shaped RAM offset (>=
 * 0x10000, installed at 0x8c0000bc/-c0 by the loader) so gdstack.S's own
 * isoldr-fingerprint probe reads it as isoldr-class and applies its MMU
 * AT=0 window -- giving gdc_call's private-stack/FPU-quarantine/MMU-window
 * trampoline its first genuine end-to-end exercise.
 *
 * ponytail: this is NOT a model of isoldr -- no FatFs, no coroutine, no SPI
 * timing, no CISO, one request in flight. It exists purely to give OUR
 * calling machinery (gdc_call) something to call that actually completes a
 * real read, on the real cart image, via the real gd_read_fad. Build a
 * fuller stand-in only if this one stops being enough to trust the
 * trampoline.
 *
 * ABI (matches gd_sys.c's header comment exactly -- same vector, same call
 * shape, real isoldr and this stand-in are interchangeable callees):
 * (r4,r5,r6=0,r7=func); func SEND=0 CHECK=1 EXEC=2 SYSINIT=3;
 * CMD_PIOREAD=16 param {fad, n, dst, 0}; CHECK status NOT_FOUND=0
 * PROCESSING=1 COMPLETED=2. */
#include "shim_iface.h"

#if GD_TEST_SERVER

typedef unsigned int u32;
extern int gd_read_fad(unsigned fad, void *dst, unsigned sectors);

#define CMD_PIOREAD   16
#define CMD_INIT      24
#define GD_SEND       0
#define GD_CHECK      1
#define GD_EXEC       2
#define GD_SYSINIT    3
#define GD_NOT_FOUND  0
#define GD_PROCESSING 1
#define GD_COMPLETED  2

/* Zero is the correct boot state here (no request stashed, no pump yet) --
 * unlike gd_last_err/gd_diag's nonzero .data sentinels elsewhere, a real
 * zero-init is exactly right, so no house-style nonzero forcing needed. */
static u32 pend_fad, pend_n, pend_dst;
static int pending;
static int pumped;

int gd_test_server(unsigned r4, unsigned r5, unsigned r6, unsigned r7) {
    (void)r6;
    switch ((int)r7) {
    case GD_SEND:
        if ((int)r4 == CMD_PIOREAD) {
            const u32 *param = (const u32 *)(unsigned long)r5;
            pend_fad = param[0];
            pend_n   = param[1];
            pend_dst = param[2];
            pending = 1;
            pumped = 0;
        }
        /* CMD_INIT (or anything else): nothing to stash, just accept --
         * gd_sys.c's gd_init_drive only checks req > 0. */
        (void)CMD_INIT;
        return 1;                     /* req id: only ever one in flight */
    case GD_CHECK:
        if (!pending)
            return GD_NOT_FOUND;
        if (!pumped)
            return GD_PROCESSING;
        gd_read_fad(pend_fad, (void *)(unsigned long)pend_dst, pend_n);
        pending = 0;
        ((u32 *)(unsigned long)r5)[0] = 0;    /* stat[0]: no sense error */
        return GD_COMPLETED;
    case GD_EXEC:
        pumped = 1;
        return 0;
    case GD_SYSINIT:
        pending = 0;
        pumped = 0;
        return 0;
    default:
        return 0;
    }
}

#endif /* GD_TEST_SERVER */

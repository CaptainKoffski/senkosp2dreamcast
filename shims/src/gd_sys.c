/* GD-ROM via the DC BIOS GD syscall vector 0x8c0000bc -- the DreamShell
 * isoldr backend (Phase 7 T1). Port of the Cleopatra port's hardware-proven
 * loop (../cleopatra/shims/src/gd.c; their KB HW rounds 9-13 carry the
 * evidence for every hardening choice). Polling only, no IRQs. PIOREAD, not
 * DMAREAD: no G1-DMA side effects in game context (same reasoning as gd.c's
 * raw path being PIO-only).
 *
 * ABI (cross-checked against KOS syscalls.c and isoldr 0.8.4
 * gdc_syscall.s:242-279 -- docs/kb/tooling.md §Phase 7): call
 * (r4,r5,r6=0,r7=func); func SEND=0 CHECK=1 EXEC=2 SYSINIT=3;
 * CMD_PIOREAD=16 param {start_fad, num_sec, buffer, 0}; CHECK status
 * FAILED=-1 NOT_FOUND=0 PROCESSING=1 COMPLETED=2 STREAMING=3 BUSY=4. */
#include "shim_iface.h"
typedef unsigned int u32;
typedef int (*gdc_t)(u32, u32, u32, u32);

#ifndef GD_LOADER_BUILD
#define GD_LOADER_BUILD 0
#endif
#ifndef GD_SYS_FIRST_LADDER
#define GD_SYS_FIRST_LADDER 0   /* PINNED 0 by Task 3's TMU verdict (spec
                                 * decision 6 revised): the game reprograms
                                 * TMU0, and isoldr's CMD_INIT path
                                 * spin-sleeps on a BIOS-rate TMU0 -- no
                                 * unconditional post-handoff ladder. The
                                 * probe exercises the backend pre-handoff;
                                 * the between-attempt retry ladder stays
                                 * (residual mis-time risk = dies loud). */
#endif

#if GD_LOADER_BUILD
/* Loader context: KOS stack is deep, FPSCR is the KOS default, MMU is off --
 * exactly the world isoldr assumes. Direct live-vector call; gdc_call's
 * stack swap would land INSIDE the running loader image (GD_STACK_TOP
 * 0x8c018000 < loader end 0x8c0dc000). */
#define GDC ((gdc_t)(*(volatile u32 *)0x8c0000bc))
#else
int gdc_call(u32, u32, u32, u32);   /* gdstack.S: private stack + FPU
                                     * quarantine + MMUCR window */
#define GDC gdc_call
void shim_die(u32, u32, u32);
#endif

#define CMD_PIOREAD  16
#define CMD_INIT     24
#define GD_SEND      0
#define GD_CHECK     1
#define GD_EXEC      2
#define GD_SYSINIT   3
#define GD_NOT_FOUND 0
#define GD_COMPLETED 2
#define GD_FAILED   -1
#define GD_E_SYS     9   /* this backend's failure site (gd.c sites end at 8);
                          * gd_last_err disambiguates: raw CHECK stat[0], or
                          * 0xcafe0001 = NOT_FOUND timeout, 0xcafe0002 = SEND
                          * refused on every attempt, 0xcafe0003 = canary. */

extern unsigned int gd_last_err;    /* defined in gd.c (both builds) */

#if SHIM_GD_DIAG && !GD_LOADER_BUILD
/* diag is shim-only: hex_paint_c lives in util.c, which the loader never
 * links -- a GDDIAG=1 build must not break the loader link. */
void hex_paint_c(unsigned int, unsigned int, unsigned int,
                 unsigned short, unsigned short);
#define GD_DIAG(x, y, v) hex_paint_c((x), (y), (v), 0xffff, 0x001f)
#define GD_PHASE(n) GD_DIAG(20, 148, 0xAAAA0000u | (n))
#define GD_RET(n)   GD_DIAG(120, 148, 0xAAAA8000u | (n))
#else
#define GD_DIAG(x, y, v) ((void)0)
#define GD_PHASE(n) ((void)0)
#define GD_RET(n)   ((void)0)
#endif

/* Hang guard: on hardware ~100M pumps >> any PIO read (Cleopatra G-loop);
 * die loud in the shim, return the site in the loader (it halts red). */
static int gd_sys_wedge(unsigned fad, unsigned n) {
#if GD_LOADER_BUILD
    (void)fad; (void)n;
    return -GD_E_SYS;
#else
    shim_die(5, fad, n);            /* same code-5 blue as a raw-path wedge */
    return -GD_E_SYS;               /* unreachable */
#endif
}

static void gd_sys_reinit(void) { GD_PHASE(6); GDC(0, 0, 0, GD_SYSINIT); GD_RET(6); }

static int gd_init_drive(void) {
    u32 stat[4], guard = 0;
    GD_PHASE(4);
    int req = GDC((u32)CMD_INIT, 0, 0, GD_SEND);
    GD_RET(4);
    if (req <= 0) return 0;
    for (;;) {
        GD_PHASE(5);
        GDC(0, 0, 0, GD_EXEC);
        int s = GDC((u32)req, (u32)stat, 0, GD_CHECK);
        GD_RET(5);
        if (s == GD_COMPLETED || s <= GD_FAILED) return 0;
        if (s == GD_NOT_FOUND && guard > 1000000u) return 0;
        if (++guard > 100000000u) return gd_sys_wedge(0xdead1217, 0);
    }
}

/* nonzero .data init, house style (see gd.c gd_last_err) */
static int gd_sys_virgin = 1;

/* Read `n` 2048-byte data sectors at absolute `fad` into dst (pass the P2
 * alias -- isoldr stores through exactly the pointer given, and PIOREAD does
 * NOT purge caches (0.8.4 syscalls.c:517); P2 makes that moot).
 * 0 = ok; negative = -GD_E_SYS with the verdict in gd_last_err. */
int gd_sys_read_sectors(void *dst, unsigned fad, unsigned n) {
#if GD_SYS_FIRST_LADDER
    /* We overwrite BIOS low RAM at handoff; Cleopatra's record says budget
     * the rebuild as the mechanism, not the rare exception (their HW round
     * 11/12). Under isoldr the state lives in the resident blob and this is
     * cheap insurance; under a real BIOS this backend never runs. */
    if (gd_sys_virgin) {
        gd_sys_virgin = 0;
        gd_sys_reinit();
        if (gd_init_drive() < 0) return -GD_E_SYS;
    }
#endif
    for (u32 attempt = 0; attempt < 4; attempt++) {
        if (attempt) { gd_sys_reinit(); if (gd_init_drive() < 0) return -GD_E_SYS; }
        u32 param[4], stat[4], guard = 0;
        param[0] = fad; param[1] = n; param[2] = (u32)dst; param[3] = 0;
        GD_DIAG(120, 134, fad);
        GD_PHASE(1);
        int req = GDC((u32)CMD_PIOREAD, (u32)param, 0, GD_SEND);
        GD_RET(1);
        GD_DIAG(20, 120, (u32)req);
        if (req <= 0) { gd_last_err = 0xcafe0002u; continue; }  /* send refused: ladder+retry */
        for (;;) {
            GD_PHASE(2);
            GDC(0, 0, 0, GD_EXEC);          /* pump isoldr's coroutine */
            GD_RET(2);
            GD_PHASE(3);
            int s = GDC((u32)req, (u32)stat, 0, GD_CHECK);
            GD_RET(3);
            if ((guard & 0xffffu) == 0) { GD_DIAG(120, 120, (u32)s); GD_DIAG(20, 134, guard); }
            if (s == GD_COMPLETED) goto done;
            if (s <= GD_FAILED) { gd_last_err = stat[0]; break; }       /* hard error: retry */
            if (s == GD_NOT_FOUND && guard > 1000000u) { gd_last_err = 0xcafe0001u; break; }
            /* PROCESSING/STREAMING/BUSY/early NOT_FOUND: keep pumping */
            if (++guard > 100000000u) return gd_sys_wedge(fad, n);
        }
    }
    return -GD_E_SYS;
done:
#if !GD_LOADER_BUILD
    /* 8 KB stack sufficiency is VERIFIED, not assumed (spec decision 5). */
    if (*P2(GD_STACK_BOTTOM) != GD_STACK_CANARY) {
        gd_last_err = 0xcafe0003u;
        shim_die(5, fad, GD_STACK_CANARY);
    }
#if SHIM_GD_DIAG
    {   /* stack low-water: first non-zero word above the canary (window was
         * staged zero); painted as bytes-used-from-top. Diag builds only. */
        volatile u32 *w = P2(GD_STACK_BOTTOM) + 1;
        while (w < P2(GD_STACK_TOP) && *w == 0) w++;
        GD_DIAG(220, 148, GD_STACK_TOP - (((u32)w & 0x1fffffffu) | 0x80000000u));
    }
#endif
#endif
    return 0;
}

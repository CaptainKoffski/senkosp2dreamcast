#include <kos.h>
#include <arch/timer.h>         /* arch_timer_gettime() -- load-stage timing */
#include "shim_iface.h"
#include "patch_table.h"        /* Task 6 stub (build/); Task 9 generates the real table */

extern uint8 shim_bin[];        /* objcopy-embedded shim.bin, see Makefile */
extern uint8 shim_bin_end[];
extern uint8 bios_data[];       /* objcopy-embedded: [BIOS60000_LEN][KERNEL_A/B/C_LEN], see shim_iface.h offsets */
extern void handoff(uint32 src, uint32 dst, uint32 len, uint32 entry);
/* ../shims/src/gd.c, compiled into the loader too (Makefile) -- the loader
 * rehearses the shim's runtime raw-ATA read before handoff. */
extern int gd_read_fad(unsigned fad, void *dst, unsigned sectors);
extern unsigned int gd_last_err;
extern uint8 handoff_end[];     /* end-of-stub label in handoff.S (stub is PIC) */

/* Whole-sector ceiling: MAIN_LEN (1,515,512 B) is not sector-aligned (739
 * sectors + 2040 B) -- the last sector's trailing bytes belong to the test
 * image that follows it in the same track (docs/kb/game.md §Parsed .dat
 * header), harmless padding for this read-and-verify pass. */
#define GAME_SECTORS   ((MAIN_LEN + 2047) / 2048)   /* 740 */

/* PIC handoff stub runs here: outside the game copy target
 * [GAME_LOAD_ADDR, GAME_LOAD_ADDR+MAIN_LEN) (else it overwrites itself
 * mid-copy), above the staged image, below the KOS stack top (0x8d000000).
 * STAGING_ADDR + MAIN_LEN ends at 0x8ce71ff8 (senkosp's image is ~1.44 MB
 * vs Cleopatra's 1 MB, so Cleopatra's fixed 0x8ce00000 would collide here);
 * 0x8ce80000 leaves 0x180000 (1.5 MB) of headroom below RAM top. Currently
 * dead code (see #if 0 below) -- NOT re-verified against the real SP/heap
 * placement Tasks 10-12 will need (open concern, task-6-report.md). */
#define HANDOFF_SCRATCH  0x8ce80000u

/* Real-HW visibility: serial is invisible on a TV, so every stage is drawn to
 * the framebuffer (KOS init already set 640x480). A stuck screen names the
 * stage that hung; halt() turns the screen red with the reason. */
#define LOADER_QUIET 1
extern uint8 splash_bin[];      /* objcopy-embedded 640x480 RGB565 (Makefile) */

/* RGB565 -> RGB0555 repack (Cleopatra's loader/shim_iface.h, not in
 * senkosp's -- senkosp's own takeover FB format is an unpinned later task;
 * kept local here rather than added to the shared header, which must stay
 * the brief's content plus only the sanctioned kernel-piece additions).
 * R and the top 5 bits of G shift down one; B stays; bit 15 (K) lands 0. */
#define RGB565_TO_0555(p) ((unsigned short)((((p) & 0xffc0u) >> 1) | ((p) & 0x1fu)))

/* Serial kill-switch (release default 0): serial-SD dongles (DreamShell
 * isoldr) drive their SD card over the SCIF pins, so a release build must
 * never transmit. KOS's dbgio_init is weak (kernel/debug/dbgio.c:110);
 * overriding it with a no-op means no dbgio device is ever selected and
 * dbgio_enabled stays 0, killing all dbglog/printf output from before the
 * KOS boot banner (every dbgio_write_* is guarded, dbgio.c:162-169). Flip to
 * 1 for serial diagnostics (debug builds). */
#define LOADER_SERIAL 0
#if !LOADER_SERIAL
int dbgio_init(void) { return 0; }   /* strong override of KOS weak symbol */
#endif

static int say_row = 0;
static void say(const char *s) {
    dbglog(DBG_INFO, "%s\n", s);
    if (LOADER_QUIET) return;
    bfont_draw_str(vram_s + (40 + say_row * 26) * 640 + 20, 640, 1, s);
    say_row++;
}

static void halt(const char *msg) {
    dbglog(DBG_INFO, "%s", msg);
    for (int i = 0; i < 640 * 480; i++) vram_s[i] = 0xf800;   /* red */
    bfont_draw_str(vram_s + 100 * 640 + 20, 640, 1, msg);
    for(;;) thd_sleep(1000);
}

static int apply_patches(uint8 *img) {
    for (unsigned i = 0; i < PATCH_COUNT; i++) {
        const patch_t *p = &patches[i];
        uint8 *at = img + (p->addr - GAME_LOAD_ADDR);
        if (memcmp(at, p->old, p->len)) {
            dbglog(DBG_INFO, "PATCH MISMATCH %s @%08lx\n", p->what, (unsigned long)p->addr);
            return -1;
        }
        memcpy(at, p->neu, p->len);
        dbglog(DBG_INFO, "patched %s @%08lx (%lu)\n", p->what,
               (unsigned long)p->addr, (unsigned long)p->len);
    }
    return 0;
}

int main(void) {
    dbglog(DBG_INFO, "SENKOSP LOADER PHASE4 TASK6\n");

    /* Naomi BIOS splash (arcade boot feel): shown for the whole load. On the
     * real Naomi the BIOS draws this screen, not the game -- our conversion
     * bypasses that BIOS, so the loader stands in for it. Displayed as
     * RGB0555, the format the GAME scans at takeover (Cleopatra HW round-15
     * register photo, carried over -- senkosp's own takeover format is a
     * later task's pin). KOS picks the cable-correct 640x480 variant. */
    if (LOADER_QUIET) {
        vid_set_mode(DM_640x480, PM_RGB555);
        const uint16 *s = (const uint16 *)splash_bin;   /* blob stays RGB565 */
        for (unsigned i = 0; i < 640u * 480u; i++)
            vram_s[i] = RGB565_TO_0555(s[i]);
    }

    say("SENKOSP LOADER PHASE4 TASK6");
    cdrom_reinit();             /* inits the GD subsystem */
    say("GD init OK");

    uint8 *stage = (uint8 *)STAGING_ADDR;
    if (cdrom_read_sectors(stage, CART_FAD, GAME_SECTORS) != ERR_OK)
        halt("KOS GD READ FAIL");
    if (memcmp(stage, "NAOMI", 5)) {
        dbglog(DBG_INFO, "bad image: %02x %02x %02x %02x %02x %02x %02x %02x @FAD %d\n",
               stage[0], stage[1], stage[2], stage[3],
               stage[4], stage[5], stage[6], stage[7], CART_FAD);
        halt("BAD IMAGE (KOS READ)");
    }
    say("cart read OK (KOS)");

    /* Rehearse the shim's exact runtime GD path before handing the game to it
     * (replaces Cleopatra's syscall rehearsal -- our runtime path is raw ATA,
     * because the kernel slice this loader places lands on the BIOS's low-RAM
     * GD state; see shims/src/gd.c's header). Same sector KOS just read, so a
     * mismatch is the driver's fault, not the disc's. Runs BEFORE
     * apply_patches, which mutates `stage`. */
    {
        static uint8 rawbuf[2048] __attribute__((aligned(32)));
        char msg[64];
        /* The driver writes rawbuf through its P2 (uncached) alias. KOS's
         * startup zeroed this .bss buffer through the CACHED alias, so its
         * lines may still be in the D-cache and dirty -- invalidate (discard,
         * no write-back: a write-back would land stale zeroes on top of the
         * incoming sector) so the memcmp below reads what the drive delivered. */
        dcache_inval_range((uintptr_t)rawbuf, sizeof(rawbuf));
        /* KOS is live here: its cdrom driver pumps the BIOS GD server from a
         * vblank handler whenever a DMA is outstanding (KOS cdrom.c:691-708).
         * None is outstanding after a blocking cdrom_read_sectors, but a raw
         * task-file transaction must not be interleaved with one under any
         * timing -- so take the whole ~1 ms transfer with IRQs off. */
        irq_mask_t old = irq_disable();
        int r = gd_read_fad(CART_FAD, rawbuf, 1);
        irq_restore(old);
        if (r != 0) {
            sprintf(msg, "RAW-ATA READ FAIL r=%d err=%08lx", r, (unsigned long)gd_last_err);
            halt(msg);                    /* err = 0xda<site><status><error>, gd.c */
        }
        if (memcmp(rawbuf, stage, 2048))
            halt("RAW-ATA MISMATCH VS KOS READ");
        say("cart read OK (raw ATA)");
    }

    if (apply_patches(stage))   /* verify old bytes then patch; abort on mismatch (0 patches, Task 6) */
        halt("PATCH ABORT");
    say("patches OK");

    /* Combo/test-image handoff, the real shim/BIOS-data placement, and the
     * jump to GAME_ENTRY land in Tasks 10-12 (this task only proves the
     * loader itself compiles and can read+verify the cart image). Kept as
     * Cleopatra's proven single-copy handoff structure, #if 0'd whole so it
     * still compiles (and still gets the shim.bin/bios_data.bin/splash.bin/
     * handoff.S blobs linked in) without running -- the memcpy to SHIM_BASE
     * below has NOT been re-verified against where this loader.elf itself
     * actually runs (KOS's naomi/pristine LOAD_OFFSET is 0x8c010000, the
     * SAME address as senkosp's SHIM_BASE -- see task-6-report.md); do not
     * re-enable without checking that first. */
#if 0  /* re-enabled per-task: see plan Tasks 10-12 */
    /* KOS-stack-collision probe: &probe ~= current SP. */
    volatile int probe = 0;
    dbglog(DBG_INFO, "SP~%08lx memtop=%08lx shim=%08x..%08x scratch=%08x\n",
           (unsigned long)&probe, (unsigned long)_arch_mem_top,
           (unsigned)SHIM_BASE, (unsigned)SHIM_END,
           (unsigned)HANDOFF_SCRATCH);

    uint32 shim_len = (uint32)(shim_bin_end - shim_bin);
    memcpy((void *)SHIM_BASE, shim_bin, shim_len);
    /* Zero the shim's .bss (NOBITS -- absent from shim.bin, so uninitialised on
     * real DC where RAM boots as garbage; Flycast happens to zero RAM, masking
     * it). */
    memset((void *)(SHIM_BASE + shim_len), 0, SHIM_CODE_MAX - shim_len);

    /* Place the BIOS-derived blocks the game reads via patched P2 pointers:
     * the 0x60000 verify+copy library, and the three-piece Naomi RTOS kernel
     * slice (KERNEL-SLICE pin, docs/kb/phase4-conversion.md). bios_data.bin
     * layout (loader/Makefile) matches these offsets exactly. */
    memcpy((void *)BIOS60000_DST, bios_data + BIOS_DATA_60000_OFF, BIOS60000_LEN);
    memcpy((void *)(KERNEL_DST),
           bios_data + BIOS_DATA_KERNEL_A_OFF, KERNEL_A_LEN);
    memcpy((void *)(KERNEL_DST + KERNEL_A_LEN),
           bios_data + BIOS_DATA_KERNEL_B_OFF, KERNEL_B_LEN);
    memcpy((void *)(KERNEL_DST + KERNEL_A_LEN + KERNEL_B_LEN),
           bios_data + BIOS_DATA_KERNEL_C_OFF, KERNEL_C_LEN);
    dbglog(DBG_INFO, "bios-data placed 60000=%08x/%x kernel=%08x/%x\n",
           (unsigned)BIOS60000_DST, (unsigned)BIOS60000_LEN,
           (unsigned)KERNEL_DST, (unsigned)KERNEL_TOTAL_LEN);

    /* Zero the G1 mirror block (uncached P2) so config-time SB_GDST pollers
     * don't spin on stale RAM before the first DMA. */
    volatile uint32 *mir = (volatile uint32 *)P2ADDR(G1_MIRROR);
    for (unsigned i = 0; i < 0x800 / 4; i++) mir[i] = 0;

    /* Zero the async-Maple register mirror so the steady engine's first
     * cross-frame SB_MDST poll sees "not busy" (bit0=0) and triggers,
     * instead of spinning forever on stale RAM. */
    volatile uint32 *mmir = (volatile uint32 *)P2ADDR(MAPLE_MIRROR);
    for (unsigned i = 0; i < MAPLE_MIRROR_LEN / 4; i++) mmir[i] = 0;

    /* Relocate the PIC handoff stub out of the copy target and flush it to RAM. */
    uint32 ho_len = (uint32)((uint8 *)handoff_end - (uint8 *)handoff);
    memcpy((void *)HANDOFF_SCRATCH, (void *)handoff, ho_len);

    /* Write-back the CPU stores (patched image, shim code, stub) to RAM: handoff
     * reads staging via P2 and the game/shim read the shim region freshly cached. */
    dcache_purge_range(STAGING_ADDR, MAIN_LEN);
    dcache_purge_range(SHIM_BASE, SHIM_CODE_MAX);
    dcache_purge_range(HANDOFF_SCRATCH, ho_len);
    dcache_purge_range(BIOS60000_DST, BIOS60000_LEN);
    dcache_purge_range(KERNEL_DST, KERNEL_TOTAL_LEN);

    say("shim + BIOS data placed");
    dbglog(DBG_INFO, "jumping to %08x\n", GAME_ENTRY);
    say("HANDOFF -> game");
    irq_disable();
    /* Deliberately NO TMU stop / ARM reset here (Cleopatra's proven reasoning
     * carried over -- the game reads TCNT0 for delay loops and resets the
     * AICA ARM itself as its first action). */

    /* MMU OFF for the game. */
    *(volatile uint32 *)0xff000010 = 0;            /* MMUCR: AT=0, TLB invalid */

    /* TA/PVR to BIOS-fresh state (Cleopatra DreamShell round 11, carried over
     * -- see Cleopatra's loader/main.c for the full HW-round citation). */
    *(volatile uint32 *)0xa05f8008 = 3;
    (void)*(volatile uint32 *)0xa05f8008;          /* posted-write flush */
    *(volatile uint32 *)0xa05f8008 = 0;
    *(volatile uint32 *)0xa05f6900 = 0xffffffff;   /* ISTNRM: clear latches */
    *(volatile uint32 *)0xa05f690c = 0xffffffff;   /* ISTERR: clear latches */

    void (*ho)(uint32, uint32, uint32, uint32) =
        (void *)P2ADDR(HANDOFF_SCRATCH);           /* run the stub uncached */
    ho(P2ADDR(STAGING_ADDR), P2ADDR(GAME_LOAD_ADDR), MAIN_LEN, GAME_ENTRY);
#endif /* re-enabled per-task: see plan Tasks 10-12 */

    halt("PHASE4 TASK6: loader alive, image verified");
    return 0; /* unreachable */
}

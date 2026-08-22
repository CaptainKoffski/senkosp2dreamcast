/* GD-ROM via DC BIOS syscall vector 0x8c0000bc -- STUBBED for Phase 4 Task 6
 * (skeleton compile only; no BIOS syscalls run yet). Cleopatra's real body
 * (polled PIO/DMA, retry+reinit hardening, gdstack.S private-stack call) is
 * proven working method but keys off Cleopatra-specific tuning; Task 7
 * implements the senkosp version once the loader's kernel-slice placement
 * (this task's Makefile amendment) is on real hardware to test against.
 *
 * Brief-vs-reality note (task-6-report.md): the task brief sketched a
 * placeholder `gd_read_fad(fad, dst, sectors)`, but the live caller in
 * cart.c (kept verbatim -- it has no Cleopatra-specific addresses) already
 * calls `gd_read_sectors(dst, fad, n)`. Kept the real name/argument order
 * so cart.c needs no edit; a rename would be a no-op churn.
 */
#include "shim_iface.h"
typedef unsigned int u32;

/* Raw CHECK status of the last hard failure -- read by cart.c's death
 * screen. .data nonzero init per house style (cart.c's gd_or_die reads
 * this on a stub -1 too, so it stays defined even though nothing sets it
 * yet). */
u32 gd_last_err = 0xcafe0000;

int gd_read_sectors(void *dst, u32 fad, u32 n) {
    (void)dst; (void)fad; (void)n;
    return -1;   /* Task 7 implements: BIOS syscall vector 0x8c0000bc, polled PIO */
}

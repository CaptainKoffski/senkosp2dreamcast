/* gdc_call(r4=cmd, r5=param, r6=superfn, r7=func) -> r0
 *
 * Calls the live GD syscall vector [0x8c0000bc] with the caller's execution
 * environment SANITIZED, for backends that -- unlike the real BIOS GD
 * driver -- assume a KOS-like world (DreamShell isoldr):
 *
 * 1. PRIVATE STACK: isoldr runs its whole read path (FatFs + SPI bit-bang +
 *    a coroutine that parks continuation frames) on the CALLER's stack. The
 *    game's Naomi stack is ~2 KB (floor 0x8c00e6e8, boot-binary.md §3) --
 *    deep enough for the real BIOS's shallow driver (18 green GDEMU
 *    rounds), not for isoldr. Swap r15 to GD_STACK_TOP (shim_iface.h) --
 *    this port reserves 8 KB there, not Cleopatra's 16 KB, and gd_sys.c
 *    VERIFIES a canary at the boundary after every read instead of
 *    assuming the smaller budget holds (spec decision 5).
 *
 * 2. FPU QUARANTINE: isoldr links KOS memcpy.S, whose big-block path
 *    (kos/src/memcpy.S:499-560 in the dreamshell tree) clobbers dr0-dr14
 *    AND xd0-xd14 -- both FPU banks, only fr12-15 saved -- and switches
 *    FPSCR to paired precision assuming the KOS baseline. The real BIOS GD
 *    driver is integer-only, so GDEMU never exposed this. Save the game's
 *    complete FPU context, run the syscall under the KOS-default FPSCR the
 *    emu was written against, restore everything on the way out.
 *    Assumes SR.FD=0 at the call site (the game is an FPU user and calls
 *    from its main thread; with FD=1 isoldr's own memcpy would trap first).
 *
 * ABI: r8-r14 are callee-saved by the C target either way; pr/r15/FPU are
 * handled manually here. Not reentrant (single static SP save) -- fine:
 * every GDC call sits sequentially in the game main thread, nothing else in
 * the shim calls GD. The vector is re-read per call (live deref, matching
 * the old GDC macro). */
#include "shim_iface.h"

    .section .text
    .globl  _gdc_call
    .align  2
_gdc_call:
    sts.l   pr, @-r15
    mov.l   .Lsp_save_k, r0
    mov.l   r15, @r0            /* stash caller SP (after pr push) */
    mov.l   .Lstack_top_k, r15  /* switch to the private GD stack */

    sts.l   fpscr, @-r15        /* game's FPSCR (incl. FR bank-select bit) */
    sts.l   fpul, @-r15
    mov.l   .Lfpscr_kos_k, r1
    lds     r1, fpscr           /* SZ=0 PR=0 FR=0: single moves, bank 0 front */
    fmov.s  fr0,  @-r15         /* physical bank 0 */
    fmov.s  fr1,  @-r15
    fmov.s  fr2,  @-r15
    fmov.s  fr3,  @-r15
    fmov.s  fr4,  @-r15
    fmov.s  fr5,  @-r15
    fmov.s  fr6,  @-r15
    fmov.s  fr7,  @-r15
    fmov.s  fr8,  @-r15
    fmov.s  fr9,  @-r15
    fmov.s  fr10, @-r15
    fmov.s  fr11, @-r15
    fmov.s  fr12, @-r15
    fmov.s  fr13, @-r15
    fmov.s  fr14, @-r15
    fmov.s  fr15, @-r15
    frchg                       /* front = physical bank 1 */
    fmov.s  fr0,  @-r15
    fmov.s  fr1,  @-r15
    fmov.s  fr2,  @-r15
    fmov.s  fr3,  @-r15
    fmov.s  fr4,  @-r15
    fmov.s  fr5,  @-r15
    fmov.s  fr6,  @-r15
    fmov.s  fr7,  @-r15
    fmov.s  fr8,  @-r15
    fmov.s  fr9,  @-r15
    fmov.s  fr10, @-r15
    fmov.s  fr11, @-r15
    fmov.s  fr12, @-r15
    fmov.s  fr13, @-r15
    fmov.s  fr14, @-r15
    fmov.s  fr15, @-r15
    frchg                       /* back to bank 0 for the call */

    /* MMU off DURING the syscall, game's MMUCR restored after (round 13).
     * The old permanent clear ("games assume AT=0 forever") was wrong for
     * this game: it runs AT=1 and maps RAM through the store-queue window
     * via UTLB entries (SQ-mapper 0x8c0311a4 -- gated on MMUCR.AT).  The
     * permanent clear left AT=0 after the last load syscall, so the
     * load->title transition's SQ-emitted display-list closers fell back to
     * QACR mapping (area 0 -- writes vanish, no fault): buffer stayed zero,
     * the transfer queue pinned waiting for the modifier-list-end event =
     * the 18-round "hang at bar 100%".  Clearing only AROUND the call keeps
     * isoldr in the AT=0 world it needs (rounds 2-5) while the game's
     * SQ translation survives; a plain 0-store leaves TI=0 so the game's
     * UTLB entries are NOT invalidated and AT restore fully revives them. */
    /* ...but ONLY for isoldr (2026-08-18 flycast 0.6.0 regression). The
     * real BIOS driver never needed AT=0 -- 18 GDEMU-green rounds and the
     * whole 0.5.0 era called it with the game's AT=1 intact -- and on a
     * BIOS-style boot this game runs MMU-ON from EARLY boot (round 14), so
     * an unconditional clear/restore toggles MMUCR.AT twice per syscall.
     * Real silicon shrugs; flycast wipes its entire dynarec block cache on
     * every AT flip (ccn.cpp CCN_MMUCR_write: AT change -> ResetCache) --
     * thousands of full retranslations across the boot preload = the
     * "load bar crawls / never starts / Windows breakpoint" 0.6.0 reports
     * on vanilla flycast with a real BIOS. Backend probe, two signatures
     * (either -> isoldr-class, apply the window):
     *  1. gdc_redir PAIR: isoldr installs BOTH GD vectors, and its
     *     gdc_redir_c0 stub sits exactly 4 insns = 8 bytes after
     *     gdc_redir_bc (dreamshell firmware/isoldr/loader/gdc_syscall.s,
     *     _gdc_syscall_enable + the two labels), so [0x8c0000c0] ==
     *     [0x8c0000bc] + 8 at ANY Memory placement -- including the ISO
     *     Loader defaults 0x8c004000 / 0x8ce00000 (isoldr.h:35-43,
     *     iso_loader module.c:1018), which sit below any usable address
     *     threshold. Real BIOS holds 0x8c001000/0x8c0010f0 (diff 0xf0),
     *     reios 0x8c001006/0x8c0010f0 (diff 0xea; reios.cpp:651-652) --
     *     both measured live (MMUCRWR vecbc/vecc0 watch, 2026-08-18).
     *  2. GD entry RAM offset >= 0x10000: definitionally not the stock
     *     BIOS/reios (their entries live in the 0x8c0010xx syscall RAM) =
     *     some resident loader's image -- keeps the window for any future
     *     isoldr whose stub layout drifts from signature 1, as long as it
     *     is placed high (the round-20 prescription).
     * Probe per call (cheap), decision latched for the restore side. */
    mov.l   .Lvec_k, r1
    mov.l   @r1, r2             /* [0xbc] = GD entry */
    mov.l   .Lvec2_k, r1
    mov.l   @r1, r1             /* [0xc0] = GD2 entry */
    add     #-8, r1
    cmp/eq  r2, r1              /* T = gdc_redir pair -> isoldr */
    movt    r3
    mov.l   .Loffmask_k, r1
    and     r2, r1              /* GD entry's RAM offset */
    mov.l   .Lbios_top_k, r2
    cmp/hs  r2, r1              /* T = above the BIOS syscall RAM */
    movt    r1
    or      r1, r3
    mov.l   .Lmmu_gate_k, r2
    mov.l   r3, @r2
    tst     r3, r3
    bt      .Lmmu_skip_clear
    mov.l   .Lmmucr_k, r1
    mov.l   @r1, r2             /* game's MMUCR (AT=1: SQ-via-TLB) */
    mov.l   .Lmmucr_save_k, r3
    mov.l   r2, @r3
    mov     #0, r2
    mov.l   r2, @r1
.Lmmu_skip_clear:

    mov.l   .Lvec_k, r0
    mov.l   @r0, r0             /* live syscall vector */
    jsr     @r0
    nop

    mov.l   .Lmmu_gate_k, r1    /* r0 = result -- keep it */
    mov.l   @r1, r1
    tst     r1, r1
    bt      .Lmmu_skip_restore  /* non-isoldr: MMUCR never touched */
    mov.l   .Lmmucr_save_k, r3  /* restore the game's MMUCR */
    mov.l   @r3, r2
    mov.l   .Lmmucr_k, r1
    mov.l   r2, @r1
.Lmmu_skip_restore:

    mov.l   .Lfpscr_kos_k, r1   /* known move width/bank for the restore */
    lds     r1, fpscr
    frchg                       /* front = physical bank 1 */
    fmov.s  @r15+, fr15
    fmov.s  @r15+, fr14
    fmov.s  @r15+, fr13
    fmov.s  @r15+, fr12
    fmov.s  @r15+, fr11
    fmov.s  @r15+, fr10
    fmov.s  @r15+, fr9
    fmov.s  @r15+, fr8
    fmov.s  @r15+, fr7
    fmov.s  @r15+, fr6
    fmov.s  @r15+, fr5
    fmov.s  @r15+, fr4
    fmov.s  @r15+, fr3
    fmov.s  @r15+, fr2
    fmov.s  @r15+, fr1
    fmov.s  @r15+, fr0
    frchg                       /* front = physical bank 0 */
    fmov.s  @r15+, fr15
    fmov.s  @r15+, fr14
    fmov.s  @r15+, fr13
    fmov.s  @r15+, fr12
    fmov.s  @r15+, fr11
    fmov.s  @r15+, fr10
    fmov.s  @r15+, fr9
    fmov.s  @r15+, fr8
    fmov.s  @r15+, fr7
    fmov.s  @r15+, fr6
    fmov.s  @r15+, fr5
    fmov.s  @r15+, fr4
    fmov.s  @r15+, fr3
    fmov.s  @r15+, fr2
    fmov.s  @r15+, fr1
    fmov.s  @r15+, fr0
    lds.l   @r15+, fpul
    lds.l   @r15+, fpscr        /* game's original FPSCR (restores its FR too) */

    mov.l   .Lsp_save_k, r1
    mov.l   @r1, r15            /* back to the caller stack */
    lds.l   @r15+, pr
    rts
    nop

    .align  2
.Lsp_save_k:    .long _gdc_saved_sp
.Lstack_top_k:  .long GD_STACK_TOP
.Lvec_k:        .long 0x8c0000bc
.Lvec2_k:       .long 0x8c0000c0
.Lmmucr_k:      .long 0xff000010
.Lmmucr_save_k: .long _gdc_saved_mmucr
.Lmmu_gate_k:   .long _gdc_mmu_gate
.Loffmask_k:    .long 0x00ffffff    /* RAM offset (16 MB), drops the 0x0c base */
.Lbios_top_k:   .long 0x00010000
.Lfpscr_kos_k:  .long 0x00040001    /* KOS default: DN=1, RM=chop, SZ=PR=FR=0 */

    .section .data
    .globl  _gdc_saved_sp
    .align  2
_gdc_saved_sp:  .long 0
_gdc_saved_mmucr: .long 0
_gdc_mmu_gate:  .long 0             /* 1 = isoldr backend: AT=0 window applied */

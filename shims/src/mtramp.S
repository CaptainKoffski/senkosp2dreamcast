! MAPLE-BOOT-A..E detour trampolines (Phase 4 Task 11).
!
! docs/kb/phase4-conversion.md §Maple-patch sites §MAPLE-BOOT-STRATEGY pins
! five 10/12-byte windows in the boot maple driver -- each one the
! `SB_MDEN = 1 / kick / poll` run, plus (A/C/D/E) the trailing `SB_MDEN = 0`.
! The generator overwrites each window with
!     d201  mov.l @(0x01,PC),r2 ; 422b  jmp @r2 ; 0009 nop ; [pad] ; .long here
! so control arrives HERE mid-body, with the mirror already programmed.
!
! REGISTER CONTRACT (KB :1261-1280, verbatim): "a mid-body detour is NOT a
! call, and the C ABI does NOT apply to it. The driver does not know the
! detour happened, so every register must come back unchanged except the ones
! the replaced instructions themselves clobbered." Reading the five windows,
! the original code clobbers exactly r2 (the poll temp, `mov.l @r5,r2` /
! `mov.l @r4,r2`) and T (from `tst r2,r2`) -- the other instructions are
! stores. So this trampoline saves and restores r0, r1, r3-r7, PR and
! MACL/MACH around the call into C; r8-r15 the C ABI preserves for us. Not
! academic: r7 (`mov #0x1,r7` @0x8c066618) and r5 (`add #0x4,r5` @0x8c066632)
! are set once and live ACROSS windows A, B and C -- `8c0668b4 6b73 mov r7,r11`
! reads r7 four instructions after window C resumes.
!
! `jmp`, never `jsr`: FUN_8c0665fe's prologue saves r8-r14 but NOT PR, so a
! jsr in its body would destroy its return address to 0x8c066aea (KB :1257).
!
! INTEGER-ONLY, deliberately: GBR, FPSCR, FPUL and fr0-fr15 are NOT saved. The
! service is integer C (no float, no store-queue, no GBR-relative access), and
! the five swallowed windows are integer stores plus one `tst` -- so nothing on
! either side of the detour touches those. If the service ever grows a float or
! a GBR user, this body has to grow `sts.l fpul` / `sts.l fpscr` / `fmov.s` for
! fr0-fr7 (the caller-saved half) and `stc.l gbr` too.
!
! Per-site stubs exist only because the RESUME address differs; r2 is free
! (the original clobbers it), so each stub loads its resume address into r2
! and falls into the shared body, which pushes r2 first and pops it last.
! Ten stubs, not five: the boot driver sits 0x157cc lower in the test image
! (KB §Test image), so each site has a main and a test resume address --
! window RAM address + window length, per the KB's own table. Cross-checked
! against the generator's own window table by scripts/test_build_patch_table.py.

    .text
    .align 2

! r2 = resume address on entry.
_mb_common:
    mov.l   r2,@-r15            ! resume (restored last, straight into the jmp)
    mov.l   r0,@-r15
    mov.l   r1,@-r15
    mov.l   r3,@-r15
    mov.l   r4,@-r15
    mov.l   r5,@-r15
    mov.l   r6,@-r15
    mov.l   r7,@-r15
    sts.l   pr,@-r15
    sts.l   macl,@-r15
    sts.l   mach,@-r15
    mov.l   .Lcore,r2
    jsr     @r2
    nop
    lds.l   @r15+,mach
    lds.l   @r15+,macl
    lds.l   @r15+,pr
    mov.l   @r15+,r7
    mov.l   @r15+,r6
    mov.l   @r15+,r5
    mov.l   @r15+,r4
    mov.l   @r15+,r3
    mov.l   @r15+,r1
    mov.l   @r15+,r0
    mov.l   @r15+,r2
    jmp     @r2
    nop
    .align 2
.Lcore:
    .long   _shim_maple_boot

.macro  MBSITE name, resume
    .globl  _shim_mb_\name
    .align  2
_shim_mb_\name:
    mov.l   9f,r2
    bra     _mb_common
    nop
    .align  2
9:  .long   \resume
.endm

! site   main window       resume        test window       resume
MBSITE  a_main, 0x8c066730          ! 8c066724 +12
MBSITE  b_main, 0x8c066818          ! 8c06680e +10 (window ends before SB_MDEN=0)
MBSITE  c_main, 0x8c0668ac          ! 8c0668a0 +12
MBSITE  d_main, 0x8c066930          ! 8c066924 +12
MBSITE  e_main, 0x8c066a68          ! 8c066a5c +12
MBSITE  a_test, 0x8c050f64          ! 8c050f58 +12
MBSITE  b_test, 0x8c05104c          ! 8c051042 +10
MBSITE  c_test, 0x8c0510e0          ! 8c0510d4 +12
MBSITE  d_test, 0x8c051164          ! 8c051158 +12
MBSITE  e_test, 0x8c05129c          ! 8c051290 +12

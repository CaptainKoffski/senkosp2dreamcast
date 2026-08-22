! handoff(records_p2 r4, entry r5)
!
! Walks a NULL-terminated copy-record list, then jumps into the game.
!   record: .long src_p2, dst_p2, len    ; list ends with a record whose len == 0
!
! v2 (Task 10). v1 copied ONE range (the game image) and was written when the
! shim/BIOS-data placement still happened from live loader C code. It cannot:
! KOS links this loader at 0x8c010000 (naomi LOAD_OFFSET, ../cleopatra/tools/kos/
! utils/ldscripts/shlelf.xc:10) with a ~838 KB text+data+bss footprint, i.e. the
! running loader occupies 0x8c010000-0x8c0dc000 -- which IS senkosp's SHIM_BASE
! (0x8c010000), the 0x60000-blob home (0x8c018000) and GAME_LOAD_ADDR
! (0x8c020000) all at once (task-6-report.md §loader/shim load-address
! collision). So NOTHING may be written to its final home while loader code or
! data is live: the loader stages every piece high (STAGING_ADDR tail) and this
! stub -- running relocated and uncached, outside every destination -- is the
! only code that final-places anything.
!
! Position-independent (PC-relative literal pool + register jumps only). The
! loader relocates it to HANDOFF_SCRATCH and calls it through that region's P2
! (uncached) alias, so no cache line being executed is in a region being
! rewritten, and no store lands in the D-cache instead of RAM.
!
! r4 and every record's src/dst are P2 aliases (0xa0......) so the copy neither
! dirties nor reads stale cache. All lengths are multiples of 4 by construction
! (shim_iface.h: 0x171ff8 / 0x4dc40 / 0x8000 / 0x7000 / 0x3200) -- `shlr2`
! truncates, so a non-multiple would silently short-copy.
!
! After the last record, writing CCR invalidates both caches (dropping the
! loader's stale I/D lines for every region just rewritten) before the jump to
! the game's P1 entry.
    .globl _handoff
    .globl _handoff_end
    .align 2
_handoff:
0:  mov.l   @(8,r4),r0      ! len
    tst     r0,r0
    bt      2f
    mov.l   @r4+,r1         ! src
    mov.l   @r4+,r2         ! dst
    add     #4,r4           ! skip len (already in r0)
    shlr2   r0              ! longwords (all records 4-aligned by construction)
1:  mov.l   @r1+,r3
    mov.l   r3,@r2
    add     #4,r2
    dt      r0
    bf      1b
    bra     0b
    nop
2:  mov.l   ccr_a,r1        ! invalidate+enable both caches, copy-back P1
    mov.l   ccr_v,r2
    mov.l   r2,@r1
    nop; nop; nop; nop; nop; nop; nop; nop
    jmp     @r5
    nop
    .align 2
ccr_a:  .long 0xff00001c    ! CCR addr -- matches KOS cache.s ccr_addr
ccr_v:  .long 0x0000090d    ! ICI|ICE|OCI|CB|OCE -- matches KOS dc/cache.h CCR_DEFAULT
_handoff_end:

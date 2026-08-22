! handoff(src_p2 r4, dst_p2 r5, len r6, entry r7)
!
! Copies the patched game image staging->GAME_LOAD_ADDR and jumps into it.
!
! Position-independent (PC-relative literal pool + register jump only). The loader
! relocates this stub to a scratch address OUTSIDE the game copy target and runs it
! from that scratch region's P2 (uncached) alias: the loader's own .text lives above
! GAME_LOAD_ADDR (0x8c020000), so an in-place stub would overwrite its own running
! instructions as the copy loop sweeps past it. Running uncached from a relocated
! copy also means no cache line being executed is in the region being rewritten.
!
! r4/r5 are P2 aliases (0xa0......) so the copy neither dirties nor reads stale
! cache. After the copy, writing CCR invalidates both caches (dropping the loader's
! stale I/D lines for the game region) before the jump to the game's P1 entry.
    .globl _handoff
    .globl _handoff_end
    .align 2
_handoff:
    mov     r6,r0
    shlr2   r0              ! len -> longwords (GAME_LEN is 4-aligned)
1:  mov.l   @r4+,r1
    mov.l   r1,@r5
    add     #4,r5
    dt      r0
    bf      1b
    mov.l   ccr_a,r1        ! invalidate+enable both caches, copy-back P1
    mov.l   ccr_v,r2
    mov.l   r2,@r1
    nop; nop; nop; nop; nop; nop; nop; nop
    jmp     @r7
    nop
    .align 2
ccr_a:  .long 0xff00001c    ! CCR addr -- matches KOS cache.s ccr_addr
ccr_v:  .long 0x0000090d    ! ICI|ICE|OCI|CB|OCE -- matches KOS dc/cache.h CCR_DEFAULT
_handoff_end:

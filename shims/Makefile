KIT ?= $(abspath ../kit)
DAT ?= senkosp.dat
INC = -Iinclude -Isrc
# Task 11: the MIE reply blobs ARE embedded, as generated C ($(B)/mie_blobs.c,
# rule in kit/shims/rules.mk), not Cleopatra's xxd-embedded .bin blobs. Since
# 2026-10 they come from kit/scripts/gen_mie_blobs.py (no capture); generated,
# never committed.
# gdstack.S revived in Phase 7 Task 5 (2026-09-03-phase7-t1-dreamshell spec +
# plan): DreamShell's isoldr backend needs the private-stack/FPU-quarantine/
# MMUCR-window trampoline gd_sys.c calls as gdc_call -- raw ATA (src/gd.c)
# stays the default backend (SHIM_STATE_GD_BACKEND selects at runtime,
# shim_iface.h); gdstack.S is dead weight only when the syscall backend is
# never probed into, which the dispatch task (Task 6) still owes.
SRCS = src/main.c $(KIT)/shims/src/scif.c src/util.c $(KIT)/shims/src/gd.c $(KIT)/shims/src/gd_sys.c \
       $(KIT)/shims/src/gd_testsrv.c src/cart.c $(KIT)/shims/src/maple.c $(KIT)/shims/src/jvs.c \
       src/mtramp.S $(KIT)/shims/src/gdstack.S $(B)/mie_blobs.c $(KIT)/loader/handoff.S
# $(KIT)/loader/handoff.S (soft-reset-menu): the loader's PIC copy-record walker,
# linked into the shim too -- the pad-combo warm boot final-places the
# re-read loader image + BIOS syscall-RAM snapshot with it (src/main.c).
# gd_testsrv.c is always compiled (unconditionally in SRCS) but its whole
# body is `#if GD_TEST_SERVER` -- an empty translation unit on every normal
# build, live only under the top Makefile's TESTSRV=1 (fix round 2,
# task-6-report.md).
include $(KIT)/shims/rules.mk
$(B)/shim.elf: include/shim_iface.h src/layouts.h
$(B)/mie_blobs.c: ../scripts/menu_def.py ../scripts/port_def.py include/shim_iface.h

# T10b (SHIM_LZ4 builds only): vendored LZ4 decoder, decompressor-only.
# lz4.c compiles with -ffunction-sections, then a partial link keeps just
# _LZ4_decompress_safe's call graph -- the compressor (~8-10 KB) would blow
# the 16 KB shim window (shim.ld ASSERT). LZ4_FREESTANDING=1: no libc
# includes; variable-length builtins land on src/lz4_mem.c's symbols.
# Two deviations from the vendored source's own defaults, discovered building
# this: (1) lz4.h's LZ4_FREESTANDING guard checks LZ4_memcpy/memmove/memset
# are already #defined at the top of lz4.c's own #include "lz4.h" -- before
# lz4.c's later (line ~347) __builtin_* fallback runs -- so they must be
# supplied here as function-like -D macros or the build errors out.
# (2) sh-elf-ld's bare default emulation is big-endian; our -ml object needs
# -m shlelf or it refuses to merge ("incompatible instructions").
# (3) -DLZ4_FORCE_SW_BITCOUNT: lz4.c's default ctz path is __builtin_ctz, which
# gcc lowers to a libgcc ___ctzsi2 call on SH4 (no count-trailing-zeros
# instruction). We link -nostdlib with no libgcc, so force the source's own
# software bit-count instead of supplying the helper (Task-4 review).
# (4) --redefine-sym: lz4.c's variable-length builtins land on memcpy/memmove/
# memset, but src/util.c already owns those names shim-wide (and must keep
# them byte-for-byte -- gate 5). Rewrite the three undefined refs in the
# partial-linked object onto src/lz4_mem.c's word-fast lz4_* versions.
# Leading underscores are this toolchain's C symbol prefix; the loader blob
# recipe uses the same --redefine-sym trick.
ifneq (,$(findstring SHIM_LZ4,$(DEFS)))
LD = /opt/toolchains/dc/sh-elf/bin/sh-elf-ld
SRCS += src/lz4_lay.c src/lz4_mem.c $(B)/lz4_dec.o
CFLAGS += -I../build
$(B)/lz4_dec.o: ../tools/t10b/lz4/lz4.c ../tools/t10b/lz4/lz4.h
	mkdir -p $(B)
	$(CC) $(CFLAGS) -DLZ4_FREESTANDING=1 -DLZ4_FORCE_SW_BITCOUNT \
	  -DLZ4_SH4_WILDCOPY=1 \
	  -D'LZ4_memcpy(d,s,n)=__builtin_memcpy(d,s,n)' \
	  -D'LZ4_memmove(d,s,n)=__builtin_memmove(d,s,n)' \
	  -D'LZ4_memset(d,c,n)=__builtin_memset(d,c,n)' \
	  -ffunction-sections -fdata-sections \
	  -c $< -o $(B)/lz4_full.o
	$(LD) -m shlelf -r --gc-sections -u _LZ4_decompress_safe $(B)/lz4_full.o -o $@
	$(OBJCOPY) --redefine-sym _memcpy=_lz4_memcpy \
	  --redefine-sym _memmove=_lz4_memmove \
	  --redefine-sym _memset=_lz4_memset $@
$(B)/shim.elf: $(B)/lz4_dec.o ../build/lz4pak_map.h src/gd_lz4.inc.c include/lz4_lay.h \
              src/lz4_lay.c src/lz4_mem.c
endif

.PHONY: test
test: shim-tests
	cc -DHOST_TEST -Iinclude -I$(KIT)/shims/src -Isrc -o $(B)/test_host test/test_host.c && $(B)/test_host
	cc -I$(KIT)/loader -I../loader -o $(B)/test_ctl_lib test/test_ctl_lib.c $(KIT)/loader/ctl_lib.c && $(B)/test_ctl_lib
	cc -Iinclude -o $(B)/test_lz4_lay test/test_lz4_lay.c src/lz4_lay.c && $(B)/test_lz4_lay
	cc -Iinclude -o $(B)/test_game_values test/test_game_values.c && $(B)/test_game_values
# Fresh clone: senkosp.dat is gitignored (your own romset, README step 1).
# Say so instead of make's "no rule to make target".
../$(DAT):
	$(error ../$(DAT) missing -- README step 1 (generate it from your own romset))

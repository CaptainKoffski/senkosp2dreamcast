CC = /opt/toolchains/dc/sh-elf/bin/sh-elf-gcc
NM = /opt/toolchains/dc/sh-elf/bin/sh-elf-nm
OBJCOPY = /opt/toolchains/dc/sh-elf/bin/sh-elf-objcopy
CFLAGS = -ml -m4-single-only -ffreestanding -nostdlib -Os -Wall -Wextra -fno-tree-loop-distribute-patterns -Iinclude
CFLAGS += $(DEFS)   # debug toggles, e.g. make DEFS='-DSHIM_SERIAL=1 -DSHIM_TRACE=1'
B = build
# Task 11: the MIE reply blobs ARE embedded now, but as generated C
# ($(B)/mie_blobs.c below), not Cleopatra's xxd-embedded .bin blobs -- they
# are captured traffic, so they are regenerated at build time and never
# committed.
# gdstack.S revived in Phase 7 Task 5 (2026-09-03-phase7-t1-dreamshell spec +
# plan): DreamShell's isoldr backend needs the private-stack/FPU-quarantine/
# MMUCR-window trampoline gd_sys.c calls as gdc_call -- raw ATA (src/gd.c)
# stays the default backend (SHIM_STATE_GD_BACKEND selects at runtime,
# shim_iface.h); gdstack.S is dead weight only when the syscall backend is
# never probed into, which the dispatch task (Task 6) still owes.
SRCS = src/main.c src/scif.c src/util.c src/gd.c src/gd_sys.c src/gd_testsrv.c \
       src/cart.c src/maple.c src/jvs.c src/mtramp.S src/gdstack.S $(B)/mie_blobs.c
# gd_testsrv.c is always compiled (unconditionally in SRCS) but its whole
# body is `#if GD_TEST_SERVER` -- an empty translation unit on every normal
# build, live only under the top Makefile's TESTSRV=1 (fix round 2,
# task-6-report.md).
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
$(B)/lz4_dec.o: ../tools/t10b/lz4/lz4.c
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
$(B)/shim.elf: $(B)/lz4_dec.o ../build/lz4pak_map.h src/gd_lz4.inc.c include/lz4_lay.h
endif

.PHONY: all test clean
# Pin the default goal: under SHIM_LZ4 the conditional block above contributes
# the first explicit rule ($(B)/lz4_dec.o), which would otherwise BE the
# default goal and a bare `make -C shims` would stop after the decoder object.
.DEFAULT_GOAL := all
all: $(B)/shim.bin $(B)/shim.map

test:
	mkdir -p $(B)
	cc -DHOST_TEST -Iinclude -o $(B)/test_host test/test_host.c && $(B)/test_host
	cc -Iinclude -o $(B)/test_iface test/test_shim_iface.c && $(B)/test_iface
	# gd.c compiles its MMIO half out under HOST_TEST -- the test links the real
	# gd_plan the shim runs, so a divergence is a link/assert failure, not a copy.
	cc -DHOST_TEST -Iinclude -o $(B)/test_gd_math test/test_gd_math.c src/gd.c && $(B)/test_gd_math
	cc -o $(B)/test_naomi_crc test/test_naomi_crc.c ../loader/naomi_crc.c && $(B)/test_naomi_crc
	cc -Iinclude -o $(B)/test_lz4_lay test/test_lz4_lay.c src/lz4_lay.c && $(B)/test_lz4_lay
# MIE reply blobs: captured traffic, so they are GENERATED at build time from a
# capture log (never committed -- same rule as bios_data.bin in loader/Makefile).
# Task 11; provenance note in docs/kb/phase4-conversion.md §Attract.
CAPTURE = ../captures/phase4/pc2.log
$(B)/mie_blobs.c: ../scripts/extract_mie_blobs.py $(CAPTURE)
	mkdir -p $(B)
	python3 ../scripts/extract_mie_blobs.py
# Fresh clone: captures/ is gitignored (same rule as senkosp.dat in
# scripts/build_patch_table.py). Say so instead of make's "no rule to make".
$(CAPTURE):
	$(error $(CAPTURE) missing -- recapture a Naomi-profile leg with \
	  scripts/capture_leg.sh, docs/kb/tooling.md §Phase 2 capture harness)

$(B)/shim.elf: $(SRCS) shim.ld include/shim_iface.h
	mkdir -p $(B)
	$(CC) $(CFLAGS) -Wl,-T,shim.ld -Wl,-Map,$(B)/shim.map.tmp -o $@ $(SRCS)
$(B)/shim.bin: $(B)/shim.elf
	$(OBJCOPY) -O binary $< $@
$(B)/shim.map: $(B)/shim.elf
	$(NM) $< > $@
clean:
	rm -rf $(B)

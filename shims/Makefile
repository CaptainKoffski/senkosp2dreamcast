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
SRCS = src/main.c src/scif.c src/util.c src/gd.c src/gd_sys.c src/cart.c \
       src/maple.c src/jvs.c src/mtramp.S src/gdstack.S $(B)/mie_blobs.c

.PHONY: all test clean
all: $(B)/shim.bin $(B)/shim.map

test:
	mkdir -p $(B)
	cc -DHOST_TEST -Iinclude -o $(B)/test_host test/test_host.c && $(B)/test_host
	cc -Iinclude -o $(B)/test_iface test/test_shim_iface.c && $(B)/test_iface
	# gd.c compiles its MMIO half out under HOST_TEST -- the test links the real
	# gd_plan the shim runs, so a divergence is a link/assert failure, not a copy.
	cc -DHOST_TEST -Iinclude -o $(B)/test_gd_math test/test_gd_math.c src/gd.c && $(B)/test_gd_math
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

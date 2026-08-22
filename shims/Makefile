CC = /opt/toolchains/dc/sh-elf/bin/sh-elf-gcc
NM = /opt/toolchains/dc/sh-elf/bin/sh-elf-nm
OBJCOPY = /opt/toolchains/dc/sh-elf/bin/sh-elf-objcopy
CFLAGS = -ml -m4-single-only -ffreestanding -nostdlib -Os -Wall -Wextra -fno-tree-loop-distribute-patterns -Iinclude
CFLAGS += $(DEFS)   # debug toggles, e.g. make DEFS='-DSHIM_SERIAL=1 -DSHIM_TRACE=1'
B = build
# Phase 4 Task 6: no embedded MIE/EEPROM data blobs yet -- main.c's service
# ladder that consumed them (Cleopatra's mie_subXX/mie_jvsXX/eeprom_img) is
# #if 0'd (Cleopatra-address bodies, Tasks 10-12 re-enable). Cleopatra's
# DATA_SRCS + xxd-embed rules return here once senkosp captures its own
# blobs.
# gdstack.S deleted in Task 10: it trampolines into the DC BIOS GD syscall
# vector, and this port's runtime disc path is raw ATA by design (the kernel
# slice the loader places lands on the BIOS's own low-RAM GD state -- see
# src/gd.c's header). Provably dead, not merely unused.
SRCS = src/main.c src/scif.c src/util.c src/gd.c src/cart.c src/maple.c src/jvs.c

.PHONY: all test clean
all: $(B)/shim.bin $(B)/shim.map

test:
	mkdir -p $(B)
	cc -DHOST_TEST -Iinclude -o $(B)/test_host test/test_host.c && $(B)/test_host
	cc -Iinclude -o $(B)/test_iface test/test_shim_iface.c && $(B)/test_iface
	# gd.c compiles its MMIO half out under HOST_TEST -- the test links the real
	# gd_plan the shim runs, so a divergence is a link/assert failure, not a copy.
	cc -DHOST_TEST -Iinclude -o $(B)/test_gd_math test/test_gd_math.c src/gd.c && $(B)/test_gd_math
$(B)/shim.elf: $(SRCS) shim.ld include/shim_iface.h
	mkdir -p $(B)
	$(CC) $(CFLAGS) -Wl,-T,shim.ld -Wl,-Map,$(B)/shim.map.tmp -o $@ $(SRCS)
$(B)/shim.bin: $(B)/shim.elf
	$(OBJCOPY) -O binary $< $@
$(B)/shim.map: $(B)/shim.elf
	$(NM) $< > $@
clean:
	rm -rf $(B)

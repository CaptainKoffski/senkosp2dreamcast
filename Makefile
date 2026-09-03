# Senko no Ronde Special -- Naomi->DC port. Top-level build (Phase 4).
#
#   make shims   = shim.bin + shim.map (shims/build/)
#   make loader  = 1ST_READ.BIN (build/) -- sources KOS via ../cleopatra
#                  (this repo has no local KOS checkout; docs/kb/tooling.md)
#   make gdi     = build/disc.gdi -- B5 donor-clone mastering (make_gdi.py);
#                  needs the donor archive at repo root, docs/kb/tooling.md
#                  §GDI mastering (Task 8)
#   make disc    = alias for gdi (Cleopatra's name for the same thing)
#   make release = disc + "build/[GDI] Senko no Ronde Special.zip"
#                  (gdi + 4 tracks, the exact set GDMENUCardManager wants).
#                  CONTAINS THE FULL COMMERCIAL ROM — local use only, never
#                  upload/commit (build/ is gitignored for this reason).
#   make test    = shims host tests + the maple-literal scan
#   make deploy  = copy the five disc files to a GDEMU card entry + dot_clean
#                  (the playbook's AppleDouble boot trap). Override target:
#                  make deploy CARD=/Volumes/GDEMU/03
#
# Requires: sh-elf toolchain at /opt/toolchains/dc, KOS via
# ../cleopatra/tools/kos, BIOS at bios/naomi/epr-21576h.ic27 (gitignored).

# SERIAL=1 (e.g. make gdi SERIAL=1): debug build with the SCIF voice on --
# shim SHIM_SERIAL + loader LOADER_SERIAL. Coder's-cable sessions only; a
# release build must stay silent (serial-SD dongles drive SD over these pins).
ifeq ($(SERIAL),1)
DEFS += -DSHIM_SERIAL=1 -DLOADER_SERIAL=1 -DSHIM_TEXHUD=1
endif
# CRC=1 (needs SERIAL=1 to be audible): SHIMCRC line per delivered cart read;
# verify with scripts/check_stream_crc.py (texpatch caveat in its docstring).
ifeq ($(CRC),1)
DEFS += -DSHIM_CRC=1
endif
# FORCE_SYSCALL=1: loader skips the raw rehearsal and seeds the syscall
# backend -- the whole game then streams via BIOS GD syscalls. RETIRED as a
# verification leg (task-6-report.md DEBUG ROUND 1): against this emulator's
# real BIOS + this port's own KERNEL-SLICE stomp, the vector serves no real
# GD driver at all, so a FORCE_SYSCALL-only leg proves nothing about
# gdc_call. Kept as the underlying "skip raw, force backend=1" primitive --
# TESTSRV=1 below reuses it and adds a server actually worth calling. Never
# a release knob.
ifeq ($(FORCE_SYSCALL),1)
DEFS += -DGD_FORCE_SYSCALL=1
endif
# GDDIAG=1: on-screen GD-syscall tracer + stack low-water (TV-debuggable,
# serial-silent -- the DreamShell debugging instrument). Never ship.
ifeq ($(GDDIAG),1)
DEFS += -DSHIM_GD_DIAG=1
endif
# TESTSRV=1 (fix round 2, task-6-report.md): the real syscall-backend
# verification leg, replacing FORCE_SYSCALL's retired one. Shim gets its own
# GD_TEST_SERVER stand-in (shims/src/gd_testsrv.c) built in; loader skips
# the raw rehearsal (LOADER_TESTSRV, same idea as GD_FORCE_SYSCALL) and
# installs the stand-in's address at the syscall vector just before handoff
# -- gdc_call's trampoline (gdstack.S) gets a real callee for the first
# time. Emulator + hardware control legs only; test-only, never shipped.
ifeq ($(TESTSRV),1)
DEFS += -DGD_TEST_SERVER=1 -DLOADER_TESTSRV=1
endif
# FORCE_CARVE=1 (fix round 2): apply the heap-carve tables even on the raw
# backend -- one-variable isolation of the carve from backend selection.
# Test-only, never shipped.
ifeq ($(FORCE_CARVE),1)
DEFS += -DFORCE_CARVE=1
endif
export DEFS

CARD ?= /Volumes/GDEMU/03
DISC_FILES = build/disc.gdi build/track01.iso build/track02.raw \
             build/track03.iso build/track04.iso
ZIP = build/[GDI] Senko no Ronde Special.zip

.PHONY: shims loader gdi disc release test test-vmu test-vmu-play deploy deploy-dcload clean

shims:
	$(MAKE) -C shims

loader: shims
	. ../cleopatra/tools/kos/environ.sh && $(MAKE) -C loader

gdi: loader
	python3 scripts/make_gdi.py

disc: gdi

release: disc
	rm -f "$(ZIP)"
	cd build && zip -j "../$(ZIP)" disc.gdi track01.iso track02.raw \
	  track03.iso track04.iso
	@echo "NOTE: archive embeds the commercial ROM -- do not upload."

test:
	$(MAKE) -C shims test
	python3 scripts/test_build_patch_table.py
	python3 scripts/test_maple_literals.py

# VMU-safety canary runs (Cleopatra's harness ported; design spec:
# ../cleopatra/docs/superpowers/specs/2026-07-26-vmu-safety-design.md):
# test-vmu = unattended 150 s attract; test-vmu-play = headed, tester plays then quits.
test-vmu:
	scripts/test_vmu_untouched.sh attract

test-vmu-play:
	scripts/test_vmu_untouched.sh play

# Cleopatra's deploy recipe verbatim (../cleopatra/Makefile): copy, dot_clean,
# then fail loudly if any ._* AppleDouble sidecar survived -- GDEMU reads the
# junk `.gdi` first (the 2026-07-20 boot blocker).
deploy: gdi
	test -d "$(CARD)"   # card entry mounted?
	cp $(DISC_FILES) "$(CARD)/"
	dot_clean -m "$(CARD)"
	@ls -a "$(CARD)" | grep '^\._' && { echo "AppleDouble junk survived!"; exit 1; } || true
	@# ponytail: eject the whole volume, not the slot dir -- diskutil wants a
	@# mount point. NOEJECT=1 to stage several slots in one card session.
	$(if $(NOEJECT),@echo "deployed to $(CARD) -- NOT ejected",\
	  diskutil eject "$$(df '$(CARD)' | tail -1 | awk '{print $$NF}')")

# Task 25: dcload-serial boot disc for the serial-link control test — its own
# card slot so the game disc stays untouched. Same AppleDouble guard as deploy.
# Build dcload first: docs/kb/tooling.md §dcload-serial.
DCLOAD_CARD ?= /Volumes/GDEMU/04
deploy-dcload:
	python3 scripts/make_dcload_gdi.py
	test -d "$(dir $(DCLOAD_CARD))"   # GDEMU volume mounted?
	mkdir -p "$(DCLOAD_CARD)"
	cp build/dcload/disc.gdi build/dcload/track01.iso build/dcload/track02.raw \
	  build/dcload/track03.iso build/dcload/track04.iso "$(DCLOAD_CARD)/"
	dot_clean -m "$(DCLOAD_CARD)"
	@ls -a "$(DCLOAD_CARD)" | grep '^\._' && { echo "AppleDouble junk survived!"; exit 1; } || true
	$(if $(NOEJECT),@echo "deployed to $(DCLOAD_CARD) -- NOT ejected",\
	  diskutil eject "$$(df '$(DCLOAD_CARD)' | tail -1 | awk '{print $$NF}')")

clean:
	$(MAKE) -C shims clean
	. ../cleopatra/tools/kos/environ.sh && $(MAKE) -C loader clean

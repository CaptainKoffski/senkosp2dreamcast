# Senko no Ronde Special -- Naomi->DC port. Top-level build (Phase 4).
#
#   make shims   = shim.bin + shim.map (shims/build/)
#   make loader  = 1ST_READ.BIN (build/) -- sources KOS via ../cleopatra
#                  (this repo has no local KOS checkout; docs/kb/tooling.md)
#   make gdi     = build/disc.gdi -- B5 donor-clone mastering (make_gdi.py);
#                  needs the donor archive at repo root, docs/kb/tooling.md
#                  §GDI mastering (Task 8)
#   make test    = shims host tests + the maple-literal scan
#   make deploy  = copy the five disc files to a GDEMU card entry + dot_clean
#                  (the playbook's AppleDouble boot trap). Override target:
#                  make deploy CARD=/Volumes/GDEMU/03
#
# Requires: sh-elf toolchain at /opt/toolchains/dc, KOS via
# ../cleopatra/tools/kos, BIOS at bios/naomi/epr-21576h.ic27 (gitignored).

CARD ?= /Volumes/GDEMU/03
DISC_FILES = build/disc.gdi build/track01.iso build/track02.raw \
             build/track03.iso build/track04.iso

.PHONY: shims loader gdi test deploy clean

shims:
	$(MAKE) -C shims

loader: shims
	. ../cleopatra/tools/kos/environ.sh && $(MAKE) -C loader

gdi: loader
	python3 scripts/make_gdi.py

test:
	$(MAKE) -C shims test
	python3 scripts/test_build_patch_table.py
	python3 scripts/test_maple_literals.py

# Cleopatra's deploy recipe verbatim (../cleopatra/Makefile): copy, dot_clean,
# then fail loudly if any ._* AppleDouble sidecar survived -- GDEMU reads the
# junk `.gdi` first (the 2026-07-20 boot blocker).
deploy: gdi
	test -d "$(CARD)"   # card entry mounted?
	cp $(DISC_FILES) "$(CARD)/"
	dot_clean -m "$(CARD)"
	@ls -a "$(CARD)" | grep '^\._' && { echo "AppleDouble junk survived!"; exit 1; } || true
	@echo "deployed to $(CARD) -- eject the card cleanly before pulling it"

clean:
	$(MAKE) -C shims clean
	. ../cleopatra/tools/kos/environ.sh && $(MAKE) -C loader clean

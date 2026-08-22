# Senko no Ronde Special -- Naomi->DC port. Top-level build (Phase 4).
#
#   make shims   = shim.bin + shim.map (shims/build/)
#   make loader  = 1ST_READ.BIN (build/) -- sources KOS via ../cleopatra
#                  (this repo has no local KOS checkout; docs/kb/tooling.md)
#   make gdi     = build/disc.gdi -- B5 donor-clone mastering (make_gdi.py);
#                  needs the donor archive at repo root, docs/kb/tooling.md
#                  §GDI mastering (Task 8)
#   make test    = shims host tests + the maple-literal scan
#
# Requires: sh-elf toolchain at /opt/toolchains/dc, KOS via
# ../cleopatra/tools/kos, BIOS at bios/naomi/epr-21576h.ic27 (gitignored).
# No `release`/`deploy` targets yet.

.PHONY: shims loader gdi test clean

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

clean:
	$(MAKE) -C shims clean
	. ../cleopatra/tools/kos/environ.sh && $(MAKE) -C loader clean

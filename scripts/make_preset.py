#!/usr/bin/env python3
"""Emit the DreamShell isoldr auto-preset into build/release-extras/.

Stock isoldr auto-applies a per-image preset when the file
DS/apps/iso_loader/presets/<dev>_<md5>.cfg exists on the tester's SD card
(4.0.4 `applications/iso_loader/modules/module.c:1758` isoLoader_LoadPreset
on image select -> `modules/isoldr/preset.c:191` isoldr_find_preset, user
file wins over the built-in romdisk pack).  <md5> is the md5 of the image's
2048-byte boot sector = the first sector of the data track
(`modules/isofs/fs_iso9660.c:1386` reads session_base-150), i.e. the first
2048 bytes of our track03.iso -- IP.BIN donor bytes, so the name is stable
across shim/loader rebuilds.  With this file shipped, testers boot the
game with ISO Loader defaults untouched; without it, default placement
0x8c004000 is measured-fatal (docs/kb/phase7-polishing.md §T1 hardware
round) and the loader's preset_note() screen explains the fix.

Values below = the T1-proven pinned preset (memory/heap,
docs/kb/tooling.md §Phase 7 preset recipe) + the 4.0.4 GUI defaults the
operator's hardware round saved (async=8 / OS auto / mode 0: app.xml
checked= states; save format: preset.c:433 isoldr_save_preset).  `sd` dev
prefix only -- the heap pin is sized against the measured `sd` blob; an
ide_ twin is deliberately not shipped (unverified blob size).

Run from repo root (make release does): needs build/track03.iso.
"""

import hashlib
import pathlib
import sys

TRACK03 = pathlib.Path("build/track03.iso")
OUT_ROOT = pathlib.Path("build/release-extras")

CFG = """\
title = SENKO NO RONDE SPECIAL
device = auto
dma = 0
async = 8
cdda = 00000000
irq = 0
low = 0
heap = 8cff7a00
fastboot = 0
type = 0
mode = 0
memory = 8cff0000
vmu = 0
scrhotkey = 0
altread = 0
gpio = 0
region = 0
pa1 = 00000000
pv1 = 00000000
pa2 = 00000000
pv2 = 00000000
"""

README = """\
SENKO NO RONDE SPECIAL -- Dreamcast port
=========================================

GDEMU / ODE:
  Copy the "Senko no Ronde Special" folder onto your card, as usual.

DreamShell (SD card on the serial port):
  1. Copy the "Senko no Ronde Special" folder onto your SD card.
  2. Copy the DS folder from this zip to the ROOT of the SD card,
     keeping its folder structure (merge with an existing DS folder if
     you have one). This part must be at the root; the game folder can
     be anywhere.
  3. In DreamShell, open ISO Loader, select the game, press Play.
     No settings needed -- the file from step 2 applies them for you.

  If you skip step 2 the game shows a blue screen with these same
  instructions instead of starting.  (Manual alternative: in ISO Loader
  set Boot memory to 0x8cff0000 and Heap memory to 0x8cff7a00.)

  Tested with DreamShell 4.0.4 / ISO Loader firmware "sd".
"""


def main():
    if not TRACK03.is_file():
        sys.exit("make_preset.py: build/track03.iso missing -- run make gdi first")
    with TRACK03.open("rb") as f:
        boot_sector = f.read(2048)
    if len(boot_sector) != 2048 or not boot_sector.startswith(b"SEGA SEGAKATANA"):
        sys.exit("make_preset.py: track03.iso boot sector is not IP.BIN -- refusing")
    md5 = hashlib.md5(boot_sector).hexdigest()

    presets = OUT_ROOT / "DS" / "apps" / "iso_loader" / "presets"
    presets.mkdir(parents=True, exist_ok=True)
    cfg = presets / f"sd_{md5}.cfg"
    # One preset per build: drop any stale sibling from an older boot sector.
    for old in presets.glob("sd_*.cfg"):
        old.unlink()
    cfg.write_text(CFG)
    (OUT_ROOT / "README.txt").write_text(README)
    print(f"preset: {cfg}")


if __name__ == "__main__":
    main()

# Senko no Ronde Special — Naomi → Dreamcast

A static binary conversion of **Senko no Ronde Special** (G.Rev, 2006, Sega
Naomi GD-ROM, GDL-0038) to the **Sega Dreamcast** — no game source code,
following the method proven by the [Cleopatra Fortune Plus
port](https://github.com/CaptainKoffski/cfp2dreamcast), done with AI heavy-lifting (Claude Code) driving the
reverse engineering and conversion, with a human running the
real-hardware test loop.

**Status: complete — fully playable on real hardware** (release v16 —
the 16th build sent to hardware — git tag `0.9.0`). 1P and 2P at full speed with 2P hot-plug, free-play, pre-game
settings menu with a controls pad-diagram page, NAOMI logo on the boot TM
screen, loads at the measured GDEMU DMA ceiling (6.7 MB/s). Verified on a
real Dreamcast with a GDEMU-class SD ODE over both VGA and composite, and
in Flycast; DreamShell serial-SD boots as a courtesy path (slower loads).
Honest limit: single-rig evidence — one console, one GDEMU, one SD card.

The game was picked via
the [naomi2dreamcast](https://github.com/CaptainKoffski/naomi2dreamcast)
umbrella project — the portability assessment of the whole Naomi library.
The complete investigation — every dead end included — is documented in
`docs/kb/`; `docs/kb/00-status.md` is the narrative index.

## What this repository contains — and does not

This repo contains **only original work**: the loader, the freestanding SH-4
shims, the patch generators, mastering/capture scripts, and the knowledge
base.

It contains **no copyrighted game data**. To build the disc you must supply
your own legally-obtained copies of:

| Input | Path expected | What it is |
|---|---|---|
| Game ROM | `senkosp.dat` (repo root) | flat decrypted 251,342,848-byte Naomi GD-ROM image, regenerated from your `senkosp` romset (`senkosp.zip` + `gdl-0038.chd`) — recipe in `docs/kb/tooling.md`. The romset itself is *also* needed at `roms/senkosp.zip` + `roms/senkosp/gdl-0038.chd` — the Flycast capture steps below boot from there |
| Naomi BIOS | `bios/naomi/epr-21576h.ic27` (extracted from your `bios/naomi.zip`) | Japan bios0; kernel/data slices are embedded at build time |
| Donor disc | `[GDI] Dolphin Blue.7z` (repo root) | the megavolt85 Atomiswave port GDI as distributed by its release (~44 MB archive), used as a proven-bootable disc skeleton (tracks 1–3 + TOC cloned verbatim; only IP.BIN metadata is re-branded) |

Three more gitignored inputs are needed at build time, but there is
nothing to hunt for — you generate each one from the inputs above in
the numbered steps below:

| Generated input | Path | Made in |
|---|---|---|
| MIE capture | `captures/phase4/pc2.log` | step 2 — instrumented-Flycast capture the shim's MIE reply blobs are extracted from at build time |
| RAM snapshot | `tools/ram-snapshot.bin` | step 3 — 32 MB Naomi RAM dump from the instrumented emulator (BIOS kernel slice source); recipe also in `docs/kb/tooling.md` §"Phase 3: RAM snapshot" |
| Boot splash | `loader/splash.png` | step 4 — NAOMI boot-logo frame captured from your BIOS |

Optional, also gitignored: `0GDTEX.png`/`.pvr` (disc art for the DC BIOS /
GDEMU menu) and `iplogo.mr` (license-screen logo).

**Do not redistribute built images.** The mastered disc embeds the inputs
above — G.Rev's game, Sega's BIOS data, and the donor's tracks. Share this
source repo, not the output.

## Requirements

Built and tested on macOS (the build uses `dot_clean`, BSD tools; Linux
would need minor Makefile tweaks). You need:

- **Sibling checkouts** — build and capture scripts reach into neighbor
  repos by fixed relative path; clone them next to this repo with exactly
  these directory names:

  ```sh
  cd ..    # siblings sit NEXT TO this repo, not inside it
  git clone https://github.com/CaptainKoffski/naomi2dreamcast
  git clone https://github.com/CaptainKoffski/flycast4naomi2dreamcast
  ```
- **sh-elf toolchain** at `/opt/toolchains/dc` and **KallistiOS** at
  `tools/kos` — a gitignored checkout *inside this repo*, pinned to the
  verified-build commit:

  ```sh
  git clone https://github.com/KallistiOS/KallistiOS.git tools/kos
  git -C tools/kos checkout 705c8629      # v2.2.0-932, the verified pin
  # write tools/kos/environ.sh (KOS_BASE = absolute path of tools/kos;
  # everything else stock) and build KOS -- exact recipe in
  # docs/kb/tooling.md §"Decoupling from ../cleopatra"
  ```
- **python3**, **7zz** (Homebrew `sevenzip`), **chdman** (Homebrew
  `rom-tools`), **cmake** (Homebrew), **clang** (Xcode command-line
  tools), **git**
- **Instrumented Flycast** — build the `flycast4naomi2dreamcast` sibling
  you cloned above: submodule init, apply the Syphon patch shipped in its
  `patches/`, then cmake (exact flags in `docs/kb/tooling.md`
  §"Instrumented Flycast"). The capture scripts expect the built app at
  `../flycast4naomi2dreamcast/build/Flycast.app`; needed for the
  one-time capture harvest and for emulator testing. Copy
  `bios/naomi.zip` to `~/Library/Application Support/Flycast/data/` so
  Naomi mode boots.

## Building from a fresh clone

One-time data preparation (all outputs are gitignored, derived from *your*
inputs — full recipes with validation steps in `docs/kb/tooling.md`):

```sh
# 1. Flat decrypted cart image from your romset (senkosp.zip + gdl-0038.chd),
#    via the dat-extract toolset in the umbrella repo. The romset lives in
#    TWO places: ../naomi2dreamcast/naomi/senkosp.zip +
#    ../naomi2dreamcast/naomi/senkosp/gdl-0038.chd (chd2dat input), and
#    roms/senkosp.zip + roms/senkosp/gdl-0038.chd in THIS repo (the
#    Flycast capture legs of steps 2-3 boot from there).
( cd ../naomi2dreamcast/tools/dat-extract && ./chd2dat.sh senkosp )
cp ../naomi2dreamcast/tools/dat-extract/out/senkosp.dat .
head -c 16 senkosp.dat            # must start with the "NAOMI" magic

# 2. Run the game once in instrumented Flycast (Naomi mode, interpreter,
#    fork commit 0d55a1812+) to capture the MIE/JVS traffic the shim
#    replays on DC. The script runs Flycast in the foreground; let it sit
#    ~300 s (unattended boot -> attract), then FROM A SECOND TERMINAL:
#    pkill -TERM -f "flycast4naomi2dreamcast.*Flycast"
#    The shim build extracts the reply blobs from this log automatically.
#    Botched run? The script refuses to overwrite an existing leg log --
#    delete captures/<leg>.log first, then rerun.
scripts/capture_leg.sh phase4/pc2

# 3. Naomi RAM snapshot -> tools/ram-snapshot.bin (the loader needs one
#    512-byte kernel window that exists in RAM only, not in the BIOS ROM).
#    Enable Flycast's AutoSaveState, run ~150 s of attract in Naomi mode,
#    quit Flycast (it auto-saves), carve + validate, set AutoSaveState
#    back to no. (If the sed matches nothing -- fresh Flycast install
#    without the key -- toggle Auto Save State in Flycast's UI instead.)
sed -i '' 's/AutoSaveState = no/AutoSaveState = yes/' ~/Library/Application\ Support/Flycast/emu.cfg
scripts/capture_leg.sh canary-snapshot   # ~150 s, then: pkill -TERM -f "flycast4naomi2dreamcast.*Flycast"
python3 scripts/carve_ram_snapshot.py    # 4 control tests -> tools/ram-snapshot.bin
sed -i '' 's/AutoSaveState = yes/AutoSaveState = no/' ~/Library/Application\ Support/Flycast/emu.cfg

# 4. Capture the NAOMI boot splash (BIOS-drawn; the script boots your
#    senkosp.dat). Pick the full-logo frame:
scripts/capture_naomi_splash.sh                # emits naomi_boot_s*.png
cp naomi_boot_s6.png loader/splash.png         # frame number may vary

# 5. Optional: disc cover art (DC BIOS menu / GDEMU menu) — drop a 256x256
#    PNG as 0GDTEX.png (or a ready PVR as 0GDTEX.pvr) at the repo root.
#    Optional: iplogo.mr (Sega MR format, <=8 KB) for the boot TM screen.
#    Absent, the donor's art / a blank logo slot are kept.
#    Both contributed by stuart2773 for the release build.

# 6. Texture VQ pass (VRAM arena fit) -- `make gdi` splices
#    build/texpatch/ into the cart image at mastering time and FAILS
#    without it. Needs numpy, hence the one-off venv. ORDER MATTERS:
#    pktx_vq.py wipes build/texpatch/, shrink_vq.py appends to it.
#    (Unpatched reference disc instead: source the KOS env first -- see
#    the next block -- then `make loader`, then
#    python3 scripts/make_gdi.py --no-texpatch.)
python3 -m venv tools/pyenv && tools/pyenv/bin/pip install numpy
tools/pyenv/bin/python3 scripts/pktx_vq.py
tools/pyenv/bin/python3 scripts/shrink_vq.py
```

Then, and on every rebuild after:

```sh
source tools/kos/environ.sh
make gdi        # shims -> patch table -> loader -> mastered GDI in build/
make test       # host-runnable shim tests + the static maple-literal scan
make release    # build/[GDI] Senko no Ronde Special.zip (disc folder + DS/ preset tree + tester README)
make deploy     # copy to SD card (CARD=/Volumes/GDEMU/NN) + dot_clean guard
```

Debug knobs (`make gdi SERIAL=1 CRC=1 ...`) are documented at the top of
the `Makefile`. `build/disc.gdi` runs directly in Flycast's DC profile. On
real hardware, feed the release zip to GDMENUCardManager (the disc
identifies as `T-SRS001M`, "SENKO NO RONDE SPECIAL").

**DreamShell / serial-SD users (isoldr):** use the preset shipped in the
release zip — merge the `DS/` folder into your card root and launch;
touch nothing. Bare isoldr defaults are a characterized known-fail: the
default load address `0x8c004000` sits inside the game's live RTOS task
table, and the console reboots at the first 3D scene
(`docs/kb/phase7-polishing.md` §T1). Expect long load bars at serial
speeds.

## How it works (short version)

A KOS-based loader boots from the disc, shows a settings menu, then
applies an old-byte-verified patch table to the game image: a four-word
relocation (one heap-top seed and one VRAM-size seed, per image) pulls
every above-cap allocation under the DC's 16 MB main RAM / 8 MB VRAM —
the game's own allocator and its KAMUI2 library re-derive the entire
layout from those seeds. Every Naomi-specific touchpoint (GD-DIMM/cart
reads, Maple/MIE/JVS input, EEPROM) is repointed at freestanding shims
placed high in RAM; a monitor-sense hook makes the game's SDK build its
own native 15 kHz mode on TV cables, and a repatched TA budget stops the
real CORE from dropping geometry the emulator happily drew. At runtime
the shims stream the game's cart reads from GD-ROM via G1 DMA behind a
prefetch ring, answer the MIE/JVS input protocol with real Maple
controller reads, and serve EEPROM from a RAM copy with free-play baked
in. A small set of textures is VQ-compressed at mastering time to fit the
8 MB VRAM arena (no text, no stage art touched).

The "works in the emulator, breaks on silicon" divergences this port
surfaced — GDEMU's inter-block DRQ idle gap, the real CORE's per-tile ISP
cache limits, TV sync vs arcade-monitor geometry — are written up in
`docs/kb/00-status.md` and the phase files it indexes.
`docs/kb/tooling.md` rebuilds the environment from scratch.

## Credits

- **megavolt85, YZB, Sonic3D** — the Atomiswave→DC ports that proved the
  approach and provided the donor disc structure.
- **Flycast** — the emulator whose source code answered a hundred hardware
  questions (and, instrumented, produced every capture).
- **KallistiOS** — loader runtime and Maple/GD reference.
- **DragonMinded's netboot tools** — Naomi ROM/EEPROM format documentation.
- **stuart2773** — disc cover art, Sega TM-screen art, alpha-testing.

Not affiliated with or endorsed by Sega or G.Rev. NAOMI, Dreamcast, and
all game titles are trademarks of their respective owners. This project is
for preservation and interoperability; buy the games and support the
rights holders where possible.

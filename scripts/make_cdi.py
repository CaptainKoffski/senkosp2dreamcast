#!/usr/bin/env python3
"""Master a burnable data/data MIL-CD CDI for testers with CD-Rs.

A GDI->CDI file-level conversion cannot work for this port: the shim streams
the cart image from a BAKED absolute FAD (shim_iface.h CART_FAD), and the
cart is raw sectors past the filesystem, not a file -- any generic converter
drops it or relocates it. So the CDI is mastered fresh, from the same donor
IP.BIN and the same cart-append math as make_gdi.py, just at CD geometry:

  data track (session 1, MSINFO 0 -- file offset == LBA exactly):
    sectors 0..15          IP.BIN (donor track03 head, branded, media string
                           GD-ROM1/1 -> CD-ROM1/1 -- the CD device string,
                           makeip src/field.c:39)
    sectors 16..FS_SECTORS ISO9660 FS (mkisofs) holding 1ST_READ.BIN, zero-
                           padded to the fixed region -- the CD analogue of
                           the GDI donor's 3,538,944 B boot region
    FS_SECTORS..           senkosp.dat cart image (texpatched), then the
                           optional --lz4 blob, same layout as GDI track04
  session 2: written by cdi4dc -d -- IP.BIN + PVD copies (the MIL-CD boot
  session; the DC boots the LAST session, whose descriptors point back into
  session 1's 0-based extents -- cdi4dc cdidata.c write_data_header_boot_track)

CART_FAD on CD = 150 + FS_SECTORS = 1942; the Makefile bakes it into shim +
loader via `make cdi` (CDI=1 -> -DCART_FAD). BLOB_FAD derives from CART_FAD
in shim_iface.h, so the LZ4 math tracks automatically.

The loader passed in MUST be the CD-FAD build: this script byte-scans it for
the CD FAD constant and refuses a GDI-FAD loader (the knob-flip stale-object
trap, docs/kb/tooling.md). Always build via `make cdi`, not by hand.

Status: emulator-verified only (Flycast + real BIOS boot leg); first tester
CD-R burn is the hardware verdict. docs/kb/tooling.md §CDI mastering.
"""
import argparse, json, pathlib, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import make_gdi  # donor cache, IP branding, texpatch, CART_SIZE + asserts

SECTOR = 2048
FS_SECTORS = 1792                    # keep in sync with Makefile CD_CART_FAD
CART_FAD_CD = 150 + FS_SECTORS       # 1942
CDI4DC = pathlib.Path("tools/img4dc/build/cdi4dc/cdi4dc")
SCRAMBLE = pathlib.Path("tools/kos/utils/scramble/scramble")

README = """\
SENKO NO RONDE SPECIAL -- Dreamcast port, CD-R (CDI) build
==========================================================

senkosp.cdi is a self-booting data/data MIL-CD image. Burn it as a
DISC IMAGE with a CDI-aware burner (Padus DiscJuggler, Alcohol 120%);
do not extract it or burn its contents as files. Older Dreamcast
lasers like slow burns: 8x or lower on a quality CD-R.

Late-2000+ Dreamcasts that block MIL-CD cannot boot any burned CD --
that is the console, not the disc. GDEMU/ODE and DreamShell users:
use the [GDI] release instead (smaller loads, tested preset).

This CDI mastering path is newer than the GDI one -- if the disc
fails to boot or dies mid-game where the GDI works, please report it.
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", default="senkosp.dat")
    ap.add_argument("--loader", default="build/1ST_READ.BIN")
    ap.add_argument("--out", default="build/cdi")
    ap.add_argument("--no-texpatch", action="store_true")
    ap.add_argument("--lz4", action="store_true",
                    help="append build/lz4paks.bin past the cart image")
    a = ap.parse_args()
    build = pathlib.Path("build")
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    assert CDI4DC.exists(), \
        "cdi4dc missing -- build it first: docs/kb/tooling.md §CDI mastering"
    assert SCRAMBLE.exists(), \
        "KOS scramble tool missing -- tools/kos checkout incomplete?"

    # same deploy tripwire as make_gdi: an LZ4=1 tree's shim routes window B
    # to BLOB_FAD -- mastering without the blob ships a mid-game death
    if not a.lz4 and (build / "lz4paks.bin").exists():
        sys.exit("make_cdi: build/lz4paks.bin present but --lz4 not passed -- "
                 "stale LZ4 build? repeat LZ4=1 on this invocation or make clean")

    ldr = pathlib.Path(a.loader).read_bytes()
    # refuse a GDI-FAD loader (knob-flip stale-object trap; see the helper)
    make_gdi.check_fad_mark(ldr, CART_FAD_CD, "CDI")

    # IP.BIN: donor track03 head + the exact make_gdi branding, then the CD
    # media string (device-info CRC at 0x20 covers 0x40..0x4f only -- ip_crc16)
    donor = make_gdi.donor_tracks(build)
    ip = out / "ip.bin"
    ip.write_bytes((donor / "track03.iso").read_bytes()[:16 * SECTOR])
    make_gdi.brand_ip(ip)
    make_gdi.patch_iplogo(ip)
    hdr = bytearray(ip.read_bytes())
    assert hdr[0x25:0x2E] == b"GD-ROM1/1", "donor device string moved? refusing"
    hdr[0x25:0x2E] = b"CD-ROM1/1"
    ip.write_bytes(hdr)

    # FS region: mkisofs (MSINFO 0 -- no -C offsets needed for data/data),
    # 1ST_READ.BIN as the only file, IP.BIN as the 16-sector system area.
    # The FS copy is SCRAMBLED (Marcus Comstedt's tool, prebuilt in the KOS
    # checkout): the boot ROM descrambles 1ST_READ.BIN when loading it from
    # a burned CD -- the cdi/boot-smoke leg pair is the control test (plain
    # copy: bootstrap reads the whole file, then dead, no loader cart reads;
    # scrambled: boots). GD-area boot takes the plain binary (tooling.md
    # §dcload-serial notes the same split). The raw cart region at
    # CART_FAD_CD is not a BIOS file load and stays plain.
    fsroot = out / "fsroot"; fsroot.mkdir(exist_ok=True)
    make_gdi.run([str(SCRAMBLE), a.loader, str(fsroot / "1ST_READ.BIN")])
    base = out / "base.iso"
    make_gdi.run(["mkisofs", "-quiet", "-iso-level", "1", "-V", "SENKOSP",
                  "-G", str(ip), "-o", str(base), str(fsroot)])
    fs = base.read_bytes()
    assert len(fs) <= FS_SECTORS * SECTOR, \
        f"FS+loader {len(fs)} B exceeds the {FS_SECTORS}-sector CD region"

    rom = pathlib.Path(a.rom).read_bytes()
    assert len(rom) == make_gdi.CART_SIZE, \
        f"cart size {len(rom):#x} != {make_gdi.CART_SIZE:#x}"
    if a.no_texpatch:
        print("texpatch: DISABLED -- unpatched reference build")
    else:
        rom = make_gdi.apply_texpatch(rom)
        assert len(rom) == make_gdi.CART_SIZE

    iso = out / "disc.iso"
    with open(iso, "wb") as f:
        f.write(fs)
        f.write(b"\0" * (FS_SECTORS * SECTOR - len(fs)))
        f.write(rom)
        if a.lz4:
            mj = json.loads((build / "lz4pak_map.json").read_text())
            blob = (build / "lz4paks.bin").read_bytes()
            assert len(mj) == 1, "multi-pak append math not wired yet"
            assert len(blob) == mj[0]["r_bytes"] and len(blob) % SECTOR == 0
            # shim reads the blob at BLOB_FAD = CART_FAD + cart sectors; this
            # write puts byte 0 exactly there (the json's blob_fad field is
            # GDI-absolute -- pack_paks compiles with the default CART_FAD --
            # so it is deliberately NOT asserted here)
            if not a.no_texpatch:
                for t in json.loads((build / "texpatch/manifest.json").read_text()):
                    assert not (t["pvrt_off"] < mj[0]["cart_off"] + mj[0]["ulen"] and
                                t["pvrt_off"] + t["orig_len"] > mj[0]["cart_off"]), \
                        f"texpatch record {t['pvrt_off']:#x} intersects the LZ4 pak"
            f.write(blob)
            print(f"lz4pak: {len(blob)} B appended at CD FAD "
                  f"{CART_FAD_CD + make_gdi.CART_SIZE // SECTOR}")

    make_gdi.run([str(CDI4DC), str(iso), str(out / "disc.cdi"), "-d"])
    iso.unlink()   # 255 MB intermediate; the .cdi is the artifact
    base.unlink()
    (out / "README.txt").write_text(README)
    print(f"OK disc.cdi (data/data MIL-CD: FS region {FS_SECTORS} sectors, "
          f"cart at FAD {CART_FAD_CD}; burn notes in {out}/README.txt)")


if __name__ == "__main__":
    main()

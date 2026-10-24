#!/usr/bin/env python3
"""Deploy fresh builds to a GDEMU SD card and refresh its GDMenu list.

  [CARD=/Volumes/X] [NOEJECT=1] python3 gdemu_deploy.py "Game Name" game.gdi game.cdi

Each image (.gdi with its tracks, or .cdi) replaces the contents of the card
folder whose name.txt reads "<name> [GDI]" / "<name> [CDI]" -- or a bare
"<name>" holding that format, as Katana leaves it. A missing one gets the next
free number. Then LIST.INI inside the GDMenu in 01/ is rewritten from every
folder, the way Katana builds it. No CARD = the one mounted volume with a
01/*.gdi. Self-contained on purpose, so sibling ports can copy it as is.
"""
import contextlib, glob, mmap, os, re, shlex, shutil, struct, subprocess, sys

SECTOR = 2048


def gdi_tracks(gdi):
    """[(lba, path, sector_size)] from a .gdi track sheet."""
    rows = [shlex.split(l) for l in open(gdi).read().splitlines()[1:] if l.strip()]
    return [(int(r[1]), os.path.join(os.path.dirname(gdi), r[4]), int(r[3])) for r in rows]


def image_files(img):
    return [img] + [p for _, p, _ in gdi_tracks(img)] if img.endswith(".gdi") else [img]


def ip_header(img):
    """The 256-byte IP.BIN header. GDI: first high-density track on (LBA 45000)."""
    files = [p for lba, p, _ in gdi_tracks(img) if lba >= 45000] if img.endswith(".gdi") else [img]
    for path in files:
        with open(path, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as m:
            i = m.find(b"SEGA SEGAKATANA ")
            if i >= 0:
                return m[i:i + 256]
    sys.exit(f"no IP.BIN in {img}")


def list_entry(num, name, ip):
    # IP.BIN field offsets and the VGA flag: makeip src/field.c fields[] and
    # _check_peripherals (github.com/sizious/makeip). Format matches Katana's.
    s = lambda a, b: ip[a:b].decode("ascii", "replace").strip(" \0")
    return (f"{num}.name={name}\n{num}.disc={s(0x20, 0x30).partition('ROM')[2].strip()}\n"
            f"{num}.vga={1 if ip[0x38 + 5:0x38 + 6] == b'1' else 0}\n{num}.region={s(0x30, 0x38)}\n"
            f"{num}.version={s(0x4a, 0x50)}\n{num}.date={s(0x50, 0x58)}\n\n")


def folder_image(d):
    imgs = sorted(glob.glob(os.path.join(d, "*.gdi")) + glob.glob(os.path.join(d, "*.cdi")))
    return imgs[0] if imgs else None


def read_name(d):
    try:
        return open(os.path.join(d, "name.txt")).read().strip()
    except FileNotFoundError:
        return os.path.basename(d)


def write_list(card):
    """Rewrite LIST.INI in 01/'s GDMenu. Katana gives the menu two ISO 9660
    volumes: high density (PVD in track 3 at LBA 45000, file data in the last
    track), which the BIOS boots 1ST_READ.BIN from, and low density (track 1),
    which GDMenu reads: KOS fs_iso9660.c mounts /cd from the last data track of
    cdrom_read_toc(&toc, false), the low-density TOC. In both the list is kept
    last in its track -- moved past later files once, old copy left dead -- and
    its dir record repointed, so reruns land on the same sectors."""
    slots = sorted(d for d in glob.glob(os.path.join(card, "[0-9]*")) if re.fullmatch(r"\d+", os.path.basename(d)))
    text = "[GDMENU]\n" + "".join(list_entry(os.path.basename(d), read_name(d), ip_header(img))
                                  for d in slots if (img := folder_image(d)))
    data = text.encode()
    n, data = len(data), data + bytes(-len(data) % SECTOR)
    tracks = gdi_tracks(folder_image(os.path.join(card, "01")))

    def track(lba):  # (start, path) of the track holding lba, and the next track's start
        i = max(i for i, t in enumerate(tracks) if t[0] <= lba)
        assert tracks[i][2] == SECTOR, f"{tracks[i][1]}: not a 2048-byte data track"
        return tracks[i][:2], tracks[i + 1][0] if i + 1 < len(tracks) else float("inf")

    def open_at(lba, mode="rb"):
        (start, path), _ = track(lba)
        f = open(path, mode)
        f.seek((lba - start) * SECTOR)
        return f

    low = max(t[0] for t in tracks if t[0] < 45000 and t[2] == SECTOR)
    for base in (low, 45000):
        with open_at(base + 16) as f:
            pvd = f.read(SECTOR)
        assert pvd[1:6] == b"CD001", f"01/: no ISO 9660 volume at LBA {base + 16}"
        root, root_size = struct.unpack_from("<I", pvd, 158)[0], struct.unpack_from("<I", pvd, 166)[0]
        with open_at(root) as f:
            d = f.read(root_size)
        p, rec, files = 0, None, []
        while p < len(d):
            if d[p] == 0:  # records never straddle sectors; skip the pad
                p = (p // SECTOR + 1) * SECTOR
                continue
            ext, size = struct.unpack_from("<I", d, p + 2)[0], struct.unpack_from("<I", d, p + 10)[0]
            name = d[p + 33:p + 33 + d[p + 32]]
            if name.upper().split(b";")[0] == b"LIST.INI":
                rec, old = p, ext
            elif name not in (b"\0", b"\1"):
                files.append((ext, size))
            p += d[p]
        if rec is None:
            sys.exit("01/ has no LIST.INI -- only GDMenu is supported (not openMenu)")
        (start, _), nxt = track(old)
        lba = max([old] + [e + -(-s // SECTOR) for e, s in files if start <= e < nxt])
        assert lba + len(data) // SECTOR <= nxt, "LIST.INI would run into the next track"
        with open_at(lba, "r+b") as f:  # data first: a crash leaves the old record valid
            f.write(data)
        with open_at(root, "r+b") as f:
            f.seek(rec + 2, os.SEEK_CUR)
            f.write(struct.pack("<I", lba) + struct.pack(">I", lba) + struct.pack("<I", n) + struct.pack(">I", n))
    print(text, end="")


def deploy(card, name, img):
    fmt = "GDI" if img.endswith(".gdi") else "CDI"
    slots = [d for d in glob.glob(os.path.join(card, "[0-9]*")) if re.fullmatch(r"\d+", os.path.basename(d))]
    mine = [d for d in slots if read_name(d) in (name, f"{name} [{fmt}]")
            and (folder_image(d) or "").endswith("." + fmt.lower())]
    if mine:
        slot = sorted(mine)[0]
        # Katana's .sha/.sha256 sidecars go stale too. name.txt stays, so a run
        # cut short still finds this slot; on FAT, macOS drops a ._ AppleDouble
        # file along with its parent, so it can be gone by its turn.
        for f in os.listdir(slot):
            if f != "name.txt":
                with contextlib.suppress(FileNotFoundError):
                    os.remove(os.path.join(slot, f))
        print(f"update {slot}")
    else:
        # GDEMU hides every folder past a gap in the numbering (hardware, user
        # report 2026-10-24), so fill the first hole rather than append.
        used = {int(os.path.basename(d)) for d in slots}
        slot = os.path.join(card, f"{min(set(range(1, len(used) + 2)) - used):02d}")
        os.mkdir(slot)
        print(f"create {slot}")
    for f in image_files(img):
        shutil.copyfile(f, os.path.join(slot, os.path.basename(f)))  # data only: no xattrs
    open(os.path.join(slot, "name.txt"), "w").write(f"{name} [{fmt}]")
    open(os.path.join(slot, "serial.txt"), "w").write(ip_header(img)[0x40:0x4a].decode().strip())
    return slot


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    name, imgs = sys.argv[1], sys.argv[2:]
    for img in imgs:
        assert img.endswith((".gdi", ".cdi")), f"{img}: expected .gdi or .cdi"
        for f in image_files(img):
            assert os.path.isfile(f), f"missing {f} -- build first"
    card = os.environ.get("CARD")
    if not card:
        cards = sorted({os.path.dirname(os.path.dirname(g)) for g in glob.glob("/Volumes/*/01/*.gdi")})
        if len(cards) != 1:
            sys.exit(f"found GDEMU cards {cards} -- pass CARD=/Volumes/<card>")
        card = cards[0]
    assert os.path.isdir(os.path.join(card, "01")), f"{card}: no 01/ menu folder"
    touched = [deploy(card, name, img) for img in imgs] + [os.path.join(card, "01")]
    write_list(card)
    # Sibling recipe (../senkosp2dreamcast/Makefile, from ../cleopatra): GDEMU
    # reads a junk ._*.gdi AppleDouble sidecar first, so none may survive.
    for d in touched:
        subprocess.run(["dot_clean", "-m", d], check=True)
        junk = glob.glob(os.path.join(d, "._*"))
        assert not junk, f"AppleDouble junk survived: {junk}"
    if os.environ.get("NOEJECT"):
        print(f"deployed to {card} -- NOT ejected")
    else:
        subprocess.run(["diskutil", "eject", card], check=True)


if __name__ == "__main__":
    main()

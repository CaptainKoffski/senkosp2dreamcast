#!/usr/bin/env python3
"""Self-check for gdemu_deploy.py on a fake card in a temp dir: python3 test_gdemu_deploy.py
Needs mkisofs/isoinfo (cdrtools) to build and independently read the fake menu."""
import os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def ip(product):  # a 256-byte IP.BIN header, makeip field layout
    return (b"SEGA SEGAKATANA SEGA ENTERPRISES0000 GD-ROM1/1  J       E000F10 "
            + product.ljust(10) + b"V1.00020261024        ").ljust(256, b" ")


def put(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").write(data)


def gdi(d, product, junk):  # two tracks: low-density junk + IP.BIN at LBA 45000
    put(f"{d}/game.gdi", b"2\n1 0 4 2352 track01.bin 0\n2 45000 4 2048 track03.iso 0\n")
    put(f"{d}/track01.bin", junk * 2352)
    put(f"{d}/track03.iso", ip(product) + junk * 4000)


def iso_file(card, track, lba, name):  # read back with cdrtools, not our own parser
    return subprocess.run(["isoinfo", "-N", lba, "-i", f"{card}/01/{track}", "-x", f"/{name};1"],
                          capture_output=True, check=True, text=True).stdout


def menu_list(card):  # GDMenu reads track 1's copy (KOS mounts the low-density TOC); BIOS boots track 3's
    low, high = iso_file(card, "track01.iso", "0", "LIST.INI"), iso_file(card, "track03.iso", "45000", "LIST.INI")
    assert low == high, (low, high)
    return low


def sizes(card):
    return [os.path.getsize(f"{card}/01/{t}") for t in ("track01.iso", "track03.iso")]


def deploy(card, src):
    subprocess.run([sys.executable, f"{HERE}/gdemu_deploy.py", "Game", f"{src}/game.gdi", f"{src}/game.cdi"],
                   env={**os.environ, "CARD": card, "NOEJECT": "1"}, check=True, stdout=subprocess.DEVNULL)


with tempfile.TemporaryDirectory() as t:
    card, src, m = f"{t}/card", f"{t}/src", f"{t}/menu"
    put(f"{m}/ip.bin", ip(b"GDMENU").ljust(32768, b"\0"))
    put(f"{m}/data/1ST_READ.BIN", b"\x09" * 5000)
    put(f"{m}/data/LIST.INI", b"[GDMENU]\n01.name=GDMENU\n")
    put(f"{m}/low/LIST.INI", b"[GDMENU]\n01.name=GDMENU\n")
    put(f"{m}/low/ZZZ.TXT", b"after the list")  # sorts after LIST.INI: the list must move past it
    put(f"{card}/01/disc.gdi", b"3\n1 0 4 2048 track01.iso 0\n2 450 0 2352 track02.raw 0\n"
                               b"3 45000 4 2048 track03.iso 0\n")
    put(f"{card}/01/track02.raw", bytes(2352))
    for out, lba, tree in (("track01.iso", "0", "low"), ("track03.iso", "45000", "data")):
        subprocess.run(["mkisofs", "-quiet", "-C", f"0,{lba}", "-V", "GDMENU", "-G", f"{m}/ip.bin", "-l",
                        "-o", f"{card}/01/{out}", f"{m}/{tree}"], check=True, stderr=subprocess.DEVNULL)
    put(f"{card}/01/name.txt", b"GDMENU")
    gdi(f"{card}/02", b"T0000M", b"o")                       # Katana-style bare name
    put(f"{card}/02/name.txt", b"Game")
    put(f"{card}/02/katana.sha", b"stale")
    put(f"{card}/04/other.cdi", ip(b"OTHER") * 2)              # 03 free: GDEMU hides folders past a gap
    put(f"{card}/04/name.txt", b"Other [CDI]")
    gdi(src, b"T0000M", b"n")
    put(f"{src}/game.cdi", b"\0" * 4096 + ip(b"T0000M"))

    deploy(card, src)
    assert sorted(os.listdir(f"{card}/02")) == ["game.gdi", "name.txt", "serial.txt", "track01.bin", "track03.iso"]
    assert open(f"{card}/02/track03.iso", "rb").read() == open(f"{src}/track03.iso", "rb").read()
    assert open(f"{card}/02/name.txt").read() == "Game [GDI]"
    assert open(f"{card}/03/name.txt").read() == "Game [CDI]" and os.path.exists(f"{card}/03/game.cdi")
    first, size = menu_list(card), sizes(card)
    assert iso_file(card, "track01.iso", "0", "ZZZ.TXT") == "after the list"
    assert first == ("[GDMENU]\n" + "".join(f"{n}.name={x}\n{n}.disc=1/1\n{n}.vga=1\n{n}.region=J\n"
                     f"{n}.version=V1.000\n{n}.date=20261024\n\n" for n, x in
                     [("01", "GDMENU"), ("02", "Game [GDI]"), ("03", "Game [CDI]"), ("04", "Other [CDI]")])), first

    deploy(card, src)                                         # redeploy: same slots, same sectors
    assert sorted(os.listdir(card)) == ["01", "02", "03", "04"]
    assert menu_list(card) == first and sizes(card) == size
print("OK")

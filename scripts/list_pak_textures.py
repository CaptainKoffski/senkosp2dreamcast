#!/usr/bin/env python3
"""list_pak_textures.py <senkosp.dat> <NAME.PAK> — list PVRT textures in one
ISO9660 file of the flat cart image, or with no NAME list all root files.

Mapping (docs/kb/phase5-hardware.md §Fix scoping): PVD at .dat 0x808000,
dat_off = (LBA - 40904) * 2048. Texture rows print the absolute dat offset
of each PVRT header (feed it to scripts/decode_pvr_vq.py), dimensions,
pixel format, datatype, and the KAMUI2 VRAM size for VQ (2048 + w*h/4).
"""
import struct, sys

data = open(sys.argv[1], "rb").read()
PVD = 0x808000
LBA0 = 40904

def dat_off(lba):
    return (lba - LBA0) * 2048

root = data[PVD + 156:PVD + 156 + 34]
r_lba = struct.unpack_from("<I", root, 2)[0]
r_size = struct.unpack_from("<I", root, 10)[0]

d = data[dat_off(r_lba):dat_off(r_lba) + r_size]
files = {}
i = 0
while i < len(d):
    rl = d[i]
    if rl == 0:
        i = (i // 2048 + 1) * 2048  # records don't cross sector boundaries
        continue
    nl = d[i + 32]
    name = d[i + 33:i + 33 + nl].decode("ascii", "replace").split(";")[0]
    if name not in ("\x00", "\x01"):
        files[name.upper()] = (struct.unpack_from("<I", d, i + 2)[0],
                               struct.unpack_from("<I", d, i + 10)[0])
    i += rl

if len(sys.argv) < 3:
    for n, (ext, size) in sorted(files.items()):
        print("%-16s dat 0x%08x  %9d B" % (n, dat_off(ext), size))
    sys.exit(0)

want = sys.argv[2].upper()
if want not in files:
    sys.exit("not found: " + want)
ext, size = files[want]
o0 = dat_off(ext)
print("%s: dat 0x%x size %d" % (want, o0, size))
blob = data[o0:o0 + size]
j = 0
while True:
    j = blob.find(b"PVRT", j)
    if j < 0:
        break
    pf, dt = blob[j + 8], blob[j + 9]
    w, h = struct.unpack_from("<HH", blob, j + 12)
    sane = pf <= 6 and dt in (0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x09, 0x0d) \
        and w in (8, 16, 32, 64, 128, 256, 512, 1024) \
        and h in (8, 16, 32, 64, 128, 256, 512, 1024)
    if sane:
        vram = 2048 + w * h // 4 if dt == 3 else w * h * 2
        print("  +0x%06x  abs 0x%08x  %4dx%-4d pf=%02x dt=%02x  ~%d B" %
              (j, o0 + j, w, h, pf, dt, vram))
    j += 4

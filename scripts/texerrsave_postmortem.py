#!/usr/bin/env python3
"""texerrsave_postmortem.py [savestate] [senkosp.dat] — attribute every VRAM
texture-arena block in a TEXERRSAVE Flycast savestate to its source texture
on disc, by exact content match.

Method (docs/kb/phase5-hardware.md §TEXERRSAVE post-mortem, 2026-08-26):
- Savestate = "FLYSAVE1" header + RZIP container ('#RZIPv\\x01#', u32 chunk
  size, u64 total, then [u32 len][zlib] chunks).
- Guest RAM located by boot-binary signature (the PKTX LZSS decoder bytes,
  RAM 0x8c0b6980 = boot.bin+0x96980); guest VRAM (64-bit-view linear)
  located by solving base against STAGE08's 512^2 VQ codebooks, which are
  uploaded verbatim to their arena block addresses.
- Arena config P1 0x8c170eb8: +0x04 total, +0x24/+0x2c bank0 alloc/free
  heads; node stride 0x18: +0x00 u16 flags, +0x08 next, +0x0c block addr,
  +0x10 size, +0x14 requester backptr (points into the texobj array
  *0x8c1a2090, stride 0x28, when the block is a game texture).
- Library = every TXTR-visible PVRT payload + every LZSS-decompressed PKTX
  entry payload in every root PAK; key (size, md5 of first 4 KB), then a
  full byte-compare ('=' exact, '~' head-only).
LZSS (FUN_8c0b6980): 4096-byte zero ring, r=0xFEE, LSB-first flags
(1=literal, 0=match), match pos = b1|(b2&0xF0)<<4, len = (b2&0xF)+3.
"""
import struct, zlib, hashlib, pathlib, sys

REPO = pathlib.Path(__file__).resolve().parent.parent
STATE = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else \
    pathlib.Path.home() / "Library/Application Support/Flycast/data/disc.state"
DAT = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else REPO / "senkosp.dat"

# ---- ISO walk (same mapping as list_pak_textures.py) ----
data = open(DAT, "rb").read()
PVD, LBA0 = 0x808000, 40904
dat_off = lambda lba: (lba - LBA0) * 2048
root = data[PVD + 156:PVD + 156 + 34]
d = data[dat_off(struct.unpack_from("<I", root, 2)[0]):]
d = d[:struct.unpack_from("<I", root, 10)[0]]
files, i = {}, 0
while i < len(d):
    rl = d[i]
    if rl == 0:
        i = (i // 2048 + 1) * 2048
        continue
    nl = d[i + 32]
    name = d[i + 33:i + 33 + nl].decode("ascii", "replace").split(";")[0]
    if name not in ("\x00", "\x01"):
        files[name.upper()] = (struct.unpack_from("<I", d, i + 2)[0],
                               struct.unpack_from("<I", d, i + 10)[0])
    i += rl

def lzss(src, dstlen):
    ring, r, out, flags, ip = bytearray(4096), 0xFEE, bytearray(), 0, 0
    while True:
        flags >>= 1
        if not (flags & 0x100):
            if ip >= len(src): return bytes(out)
            flags = src[ip] | 0xFF00; ip += 1
        if flags & 1:
            if ip >= len(src): return bytes(out)
            b = src[ip]; ip += 1
            if len(out) >= dstlen: return None
            out.append(b); ring[r] = b; r = (r + 1) & 0xFFF
        else:
            if ip + 1 >= len(src): return bytes(out)
            b1, b2 = src[ip], src[ip + 1]; ip += 2
            pos = b1 | ((b2 & 0xF0) << 4)
            for k in range((b2 & 0x0F) + 3):
                c = ring[(pos + k) & 0xFFF]
                if len(out) >= dstlen: return None
                out.append(c); ring[r] = c; r = (r + 1) & 0xFFF

# ---- decompress savestate ----
raw = open(STATE, "rb").read()
assert raw[:8] == b"FLYSAVE1", "not a Flycast savestate"
o = raw.find(b"#RZIPv")
total = struct.unpack_from("<Q", raw, o + 12)[0]
p, out = o + 20, bytearray()
while p < len(raw) and len(out) < total:
    clen = struct.unpack_from("<I", raw, p)[0]; p += 4
    out += zlib.decompress(raw[p:p + clen]); p += clen
out = bytes(out)

boot_sig = data[0x96980:0x969c0]      # main image is .dat offset 0
ram = out.find(boot_sig) - 0xb6980
assert ram > 0, "guest RAM not found"
def rd32(a): return struct.unpack_from("<I", out, ram + (a & 0x1fffffff) - 0x0c000000)[0]
def rd16(a): return struct.unpack_from("<H", out, ram + (a & 0x1fffffff) - 0x0c000000)[0]

CFG = 0x8c170eb8
print("arena total = 0x%x" % rd32(CFG + 4))
nodes, node = [], rd32(CFG + 0x24)
while node:
    nodes.append((rd32(node + 0xc), rd32(node + 0x10), rd16(node), rd32(node + 0x14)))
    node = rd32(node + 0x08)
free, node = 0, rd32(CFG + 0x2c)
while node:
    free += rd32(node + 0x10); node = rd32(node + 0x08)
print("alloc %s B in %d blocks, free %s B" %
      (format(sum(n[1] for n in nodes), ","), len(nodes), format(free, ",")))
tex, texcap = rd32(0x8c1a2090), rd32(0x8c1a2094)

# ---- texture library ----
lib = {}
def add(pak, kind, idx, pay):
    lib.setdefault((len(pay), hashlib.md5(pay[:4096]).digest()), []).append((pak, kind, idx, pay))
for name in sorted(files):
    ext, size = files[name]
    blob = data[dat_off(ext):dat_off(ext) + size]
    j = 0
    while True:
        j = blob.find(b"PVRT", j)
        if j < 0: break
        datalen = struct.unpack_from("<I", blob, j + 4)[0]
        pf, dt = blob[j + 8], blob[j + 9]
        w, h = struct.unpack_from("<HH", blob, j + 12)
        legal = {8, 16, 32, 64, 128, 256, 512, 1024}
        if pf <= 6 and dt in (1, 2, 3, 4, 5, 6, 7, 9, 0xd, 0x11, 0x12) and \
           w in legal and h in legal and 8 < datalen <= len(blob) - j - 8:
            add(name, "TXTR", j, blob[j + 16:j + 8 + datalen])
        j += 4
    j = blob.find(b"PKTX")
    while j >= 0:
        pay = j + 8
        cnt = struct.unpack_from("<I", blob, pay)[0]
        if 0 < cnt < 256 and pay + 4 + 4 * cnt < len(blob):
            offs = struct.unpack_from("<%dI" % cnt, blob, pay + 4)
            if all(pay + off + 8 <= len(blob) and
                   0 < struct.unpack_from("<II", blob, pay + off)[1]
                     <= struct.unpack_from("<II", blob, pay + off)[0] < 0x400000
                   for off in offs):
                for k, off in enumerate(offs):
                    e = pay + off
                    dsz, csz = struct.unpack_from("<II", blob, e)
                    rec = lzss(blob[e + 8:e + 8 + csz], dsz)
                    if rec is None: continue
                    o2 = 8 + struct.unpack_from("<I", rec, 4)[0] if rec[:4] == b"GBIX" else 0
                    if rec[o2:o2 + 4] == b"PVRT":
                        dl = struct.unpack_from("<I", rec, o2 + 4)[0]
                        add(name, "PKTX", k, rec[o2 + 16:o2 + 8 + dl])
        j = blob.find(b"PKTX", j + 4)

# ---- solve VRAM base: STAGE08 codebooks land at their block addrs ----
ext, size = files["STAGE08.PAK"]
blob = data[dat_off(ext):dat_off(ext) + size]
books, j = [], 0
while True:
    j = blob.find(b"PVRT", j)
    if j < 0: break
    pf, dt = blob[j + 8], blob[j + 9]
    w, h = struct.unpack_from("<HH", blob, j + 12)
    if dt == 3 and w == h == 512:
        books.append(blob[j + 16:j + 16 + 2048])
    j += 4
cand = [n[0] for n in nodes if n[1] == 67584]
best, VB = 0, None
h = out.find(books[0])
while h >= 0:
    for a in cand:
        vb = h - a
        if vb < 0: continue
        score = sum(1 for b in books
                    if any(out[vb + a2:vb + a2 + 2048] == b for a2 in cand))
        if score > best:
            best, VB = score, vb
    h = out.find(books[0], h + 1)
assert VB is not None and best >= len(books) // 2, "VRAM base not solved (%s)" % best
print("VRAM base: stream +0x%x (%d/%d codebooks anchor)" % (VB, best, len(books)))

# ---- attribute ----
for addr, sz, fl, bp in sorted(nodes):
    if fl in (0x13, 0x43):
        print("addr=%06x size=%8d flags=%04x  %s" %
              (addr, sz, fl, "(FB)" if fl == 0x13 else "(TA/region)"))
        continue
    s = out[VB + addr:VB + addr + sz]
    m = lib.get((sz, hashlib.md5(s[:4096]).digest()), [])
    full = [(pk, kd, ix) for pk, kd, ix, pay in m if pay == s]
    use, mark = (full, "=") if full else ([(pk, kd, ix) for pk, kd, ix, _ in m], "~")
    ti = (bp - tex) // 0x28 if tex <= bp < tex + texcap * 0x28 else -1
    lab = "%s %s" % (mark, " | ".join("%s:%s#%d" % u for u in use[:4])) if use else "?? unmatched"
    if len(use) > 4:
        lab += " (+%d)" % (len(use) - 4)
    print("addr=%06x size=%8d flags=%04x tex=%3d  %s" % (addr, sz, fl, ti, lab))

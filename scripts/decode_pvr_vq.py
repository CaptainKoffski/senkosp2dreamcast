#!/usr/bin/env python3
"""decode_pvr_vq.py <dat> <offset-hex> <out.png>

Decode one GBIX+PVRT texture (VQ, RGB565/ARGB1555/ARGB4444, square,
twiddled) from a flat cart image to PNG. Written for the Phase 5
fix-scoping work: turning the STAGE08.PAK offender textures into
something a human can look at (docs/kb/phase5-hardware.md §High-water
measurement). Pure stdlib (zlib PNG writer) — no PIL.

Format facts (primary source: the PVRT header layout already verified
byte-for-byte against RAM in docs/kb/phase5-hardware.md §Step 8, and the
KAMUI2 size arithmetic 2048 + w*h/4 confirmed there):
  GBIX: "GBIX" u32len u32index [pad to len]
  PVRT: "PVRT" u32datalen  u8 pixfmt  u8 datatype  u16 pad  u16 w  u16 h
  VQ (datatype 0x03): 256-entry codebook of 4 texels (8 B each, the 2x2
  block twiddled: [0]=(0,0) [1]=(0,1) [2]=(1,0) [3]=(1,1)), then one
  index byte per 2x2 block, morton/twiddled over the (w/2)x(h/2) grid
  with y in the LSB.
"""
import struct, sys, zlib


def unpack565(v):
    return ((v >> 11) << 3 & 0xf8, (v >> 5) << 2 & 0xfc, (v << 3) & 0xf8, 255)


def unpack1555(v):
    return ((v >> 10) << 3 & 0xf8, (v >> 5) << 3 & 0xf8, (v << 3) & 0xf8,
            255 if v & 0x8000 else 0)


def unpack4444(v):
    return ((v >> 8& 0xf) * 17, (v >> 4 & 0xf) * 17, (v & 0xf) * 17,
            (v >> 12) * 17)


UNPACK = {0x00: unpack1555, 0x01: unpack565, 0x02: unpack4444}


def morton_xy(n):
    # ponytail: bit-by-bit deinterleave, y in the LSB (PVR twiddle order)
    x = y = 0
    for b in range(16):
        y |= ((n >> (2 * b)) & 1) << b
        x |= ((n >> (2 * b + 1)) & 1) << b
    return x, y


def write_png(path, w, h, rgba):
    raw = b''.join(b'\x00' + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))
    def chunk(tag, data):
        c = tag + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c))
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n')
        f.write(chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)))
        f.write(chunk(b'IDAT', zlib.compress(raw, 6)))
        f.write(chunk(b'IEND', b''))


def main():
    dat, off, out = sys.argv[1], int(sys.argv[2], 16), sys.argv[3]
    f = open(dat, 'rb')
    f.seek(off)
    head = f.read(32)
    if head[:4] == b'GBIX':
        glen = struct.unpack_from('<I', head, 4)[0]
        f.seek(off + 8 + glen)
        head = f.read(32)
    assert head[:4] == b'PVRT', head[:4]
    pixfmt, datatype = head[8], head[9]
    w, h = struct.unpack_from('<HH', head, 12)
    assert datatype == 0x03, 'only VQ supported, got 0x%02x' % datatype
    unpack = UNPACK[pixfmt]
    book = [struct.unpack('<4H', f.read(8)) for _ in range(256)]
    idx = f.read((w // 2) * (h // 2))
    px = bytearray(w * h * 4)
    for n, ci in enumerate(idx):
        bx, by = morton_xy(n)
        t = book[ci]
        for k, (dx, dy) in enumerate(((0, 0), (0, 1), (1, 0), (1, 1))):
            x, y = bx * 2 + dx, by * 2 + dy
            px[(y * w + x) * 4:(y * w + x) * 4 + 4] = bytes(unpack(t[k]))
    write_png(out, w, h, bytes(px))
    print('%s: %dx%d pixfmt=%02x -> %s' % (hex(off), w, h, pixfmt, out))


if __name__ == '__main__':
    main()

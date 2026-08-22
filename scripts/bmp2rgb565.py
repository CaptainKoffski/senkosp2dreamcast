#!/usr/bin/env python3
"""BMP -> raw RGB565 little-endian (Dreamcast framebuffer format).

Feeds the loader's splash screen (loader/Makefile: sips converts the
gitignored loader/splash.png to BMP, this turns it into the blob objcopy
embeds) and the 0GDTEX disc-art pixels (scripts/make_gdi.py). Stdlib-only on
purpose: the build must not grow a PIL dependency for one image. Handles
what sips emits: uncompressed 24/32bpp bottom-up.

Usage: bmp2rgb565.py SRC DST [WIDTH HEIGHT]   (size check defaults 640x480)
"""
import struct, sys

def main():
    src, dst = sys.argv[1], sys.argv[2]
    ew, eh = (int(sys.argv[3]), int(sys.argv[4])) if len(sys.argv) > 4 else (640, 480)
    b = open(src, "rb").read()
    assert b[:2] == b"BM", "not a BMP"
    (off,) = struct.unpack_from("<I", b, 0x0A)
    w, h = struct.unpack_from("<ii", b, 0x12)
    (bpp,) = struct.unpack_from("<H", b, 0x1C)
    (comp,) = struct.unpack_from("<I", b, 0x1E)
    assert comp == 0 and bpp in (24, 32), f"unsupported BMP: bpp={bpp} comp={comp}"
    assert (w, abs(h)) == (ew, eh), f"expected {ew}x{eh}, got {w}x{abs(h)}"
    px = bpp // 8
    stride = (w * px + 3) & ~3
    rows = range(h - 1, -1, -1) if h > 0 else range(-h)   # bottom-up unless h<0
    out = bytearray()
    for y in rows:
        r0 = off + y * stride
        for x in range(w):
            bl, g, r = b[r0 + x * px], b[r0 + x * px + 1], b[r0 + x * px + 2]
            out += struct.pack("<H", (r >> 3) << 11 | (g >> 2) << 5 | bl >> 3)
    open(dst, "wb").write(out)

if __name__ == "__main__":
    main()

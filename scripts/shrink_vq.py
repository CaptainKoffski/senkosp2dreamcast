#!/usr/bin/env python3
"""shrink_vq.py [senkosp.dat] — re-encode the four STAGE08.PAK 1024x1024 VQ
textures at 512x512 and write patch blobs for make_gdi.py to splice into
track04 (the option-2 VRAM fix, docs/kb/phase5-hardware.md §Fix decision;
saves 4 x 196,608 B of texture arena).

Outputs (ROM-derived, gitignored):
  build/texpatch/<pvrt-off>.bin   full replacement PVRT record (67,600 B)
  build/texpatch/manifest.json    offsets + md5s make_gdi.py verifies
  captures/phase5/textures/patched-<pvrt-off>.png   operator previews

Requires tools/pyenv (numpy — docs/kb/tooling.md):
  tools/pyenv/bin/python scripts/shrink_vq.py

Every produced record is decoded back through scripts/decode_pvr_vq.py's
decode() — the path control-tested against /FONT.PAK — and gated on PSNR
vs the downscaled reference, so an encoder bug cannot ship silently.
"""
import hashlib, importlib.util, io, json, pathlib, struct, sys
import numpy as np

REPO = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("dec", REPO / "scripts/decode_pvr_vq.py")
dec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dec)

# The four offenders: PVRT header offsets in senkosp.dat + expected pixfmt
# (docs/kb/phase5-hardware.md §Fix scoping; GBIX headers precede, untouched).
TARGETS = [(0x0b6b5fb0, 0x01), (0x0b6f67d0, 0x01),
           (0x0b736ff0, 0x01), (0x0b777810, 0x02)]
SRC = 1024
DST = 512
OLD_RECORD = 16 + 2048 + (SRC // 2) ** 2   # 264,208
NEW_RECORD = 16 + 2048 + (DST // 2) ** 2   #  67,600
KMEANS_ITERS = 30
PSNR_FLOOR = 26.0
# decoder texel order within a 2x2 block, as (dx, dy) — must match decode()
TEXELS = ((0, 0), (0, 1), (1, 0), (1, 1))


def morton_compact(n):
    # even bits of n (vectorized); y = compact(n), x = compact(n >> 1)
    n = n & 0x55555555
    n = (n | (n >> 1)) & 0x33333333
    n = (n | (n >> 2)) & 0x0f0f0f0f
    n = (n | (n >> 4)) & 0x00ff00ff
    return (n | (n >> 8)) & 0x0000ffff


def pack_texels(v, pixfmt):
    """v: (..., 4) float RGBA 0..255 -> u16, inverse of decode()'s UNPACK."""
    r, g, b, a = (np.clip(np.round(v[..., i]), 0, 255).astype(np.uint32)
                  for i in range(4))
    if pixfmt == 0x01:          # RGB565
        return ((r >> 3 << 11) | (g >> 2 << 5) | (b >> 3)).astype('<u2')
    if pixfmt == 0x02:          # ARGB4444, nibble*17 on decode
        q = lambda c: np.clip(np.round(c / 17.0), 0, 15).astype(np.uint32)
        return ((q(a) << 12) | (q(r) << 8) | (q(g) << 4) | q(b)).astype('<u2')
    raise SystemExit("unsupported pixfmt %02x" % pixfmt)


def unpack_texels(u, pixfmt):
    """u16 -> (..., 4) float RGBA, exactly decode()'s UNPACK arithmetic."""
    u = u.astype(np.uint32)
    if pixfmt == 0x01:
        return np.stack([(u >> 11 << 3) & 0xf8, (u >> 5 << 2) & 0xfc,
                         (u << 3) & 0xf8, np.full_like(u, 255)],
                        -1).astype(np.float32)
    return np.stack([(u >> 8 & 0xf) * 17, (u >> 4 & 0xf) * 17,
                     (u & 0xf) * 17, (u >> 12) * 17], -1).astype(np.float32)


def kmeans(vecs, counts, k, rng):
    """Weighted k-means++ then Lloyd. vecs (N,16) float32, counts (N,)."""
    n = len(vecs)
    w = counts.astype(np.float64)
    cent = np.empty((k, vecs.shape[1]), np.float32)
    cent[0] = vecs[rng.integers(n)]
    d2 = ((vecs - cent[0]) ** 2).sum(1)
    for j in range(1, k):
        p = d2 * w
        cent[j] = vecs[rng.choice(n, p=p / p.sum())]
        d2 = np.minimum(d2, ((vecs - cent[j]) ** 2).sum(1))
    prev = None
    for _ in range(KMEANS_ITERS):
        d = (vecs ** 2).sum(1)[:, None] - 2 * vecs @ cent.T + (cent ** 2).sum(1)
        assign = d.argmin(1)
        if prev is not None and (assign == prev).all():
            break
        prev = assign
        for j in range(k):
            m = assign == j
            if m.any():
                cent[j] = np.average(vecs[m], 0, w[m])
            else:   # dead centroid: reseed on the worst-served vector
                cent[j] = vecs[(d.min(1) * w).argmax()]
    return cent


def encode_one(rom, off, pixfmt, rng):
    hdr = rom[off:off + 16]
    assert hdr[:4] == b"PVRT" and hdr[8] == pixfmt and hdr[9] == 0x03, hdr.hex()
    assert struct.unpack_from("<HH", hdr, 12) == (SRC, SRC), hdr.hex()
    assert struct.unpack_from("<I", hdr, 4)[0] == 8 + 2048 + (SRC // 2) ** 2

    # source decode through the control-tested decoder
    w, h, pf, rgba = dec.decode(io.BytesIO(rom), off)
    assert (w, h, pf) == (SRC, SRC, pixfmt)
    img = np.frombuffer(rgba, np.uint8).reshape(SRC, SRC, 4).astype(np.float32)

    # 2x2 box downscale. ponytail: gamma-naive average — same space the PVR
    # filters in; linearize first if the A/B gate finds it too dark.
    ref = img.reshape(DST, 2, DST, 2, 4).mean((1, 3))

    # 2x2 blocks as 16-vectors in decoder texel order (dx-major, dy fastest)
    vecs = ref.reshape(DST // 2, 2, DST // 2, 2, 4) \
              .transpose(0, 2, 3, 1, 4).reshape(-1, 16).copy()
    uniq, inv, counts = np.unique(vecs, axis=0, return_inverse=True,
                                  return_counts=True)
    cent = kmeans(uniq, counts, 256, rng)

    # store quantized, then assign against what will actually be stored
    packed = pack_texels(cent.reshape(256, 4, 4), pixfmt)          # (256,4)
    stored = unpack_texels(packed, pixfmt).reshape(256, 16)
    d = (uniq ** 2).sum(1)[:, None] - 2 * uniq @ stored.T + (stored ** 2).sum(1)
    assign = d.argmin(1).astype(np.uint8)[inv]                     # per block

    nblk = np.arange((DST // 2) ** 2)
    by, bx = morton_compact(nblk), morton_compact(nblk >> 1)
    indices = assign.reshape(DST // 2, DST // 2)[by, bx]           # morton order

    new = struct.pack("<4sIBBHHH", b"PVRT", 8 + 2048 + (DST // 2) ** 2,
                      pixfmt, 0x03, 0, DST, DST) \
        + packed.tobytes() + indices.tobytes()
    assert len(new) == NEW_RECORD

    # roundtrip gate: proven decoder on the produced record, PSNR vs ref
    w2, h2, pf2, out_rgba = dec.decode(io.BytesIO(new), 0)
    assert (w2, h2, pf2) == (DST, DST, pixfmt)
    got = np.frombuffer(out_rgba, np.uint8).reshape(DST, DST, 4).astype(np.float32)
    mse = ((got - ref) ** 2).mean()
    psnr = 10 * np.log10(255.0 ** 2 / mse)
    assert psnr >= PSNR_FLOOR, "PSNR %.1f under floor %.1f" % (psnr, PSNR_FLOOR)
    return new, out_rgba, psnr


def main():
    dat = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else REPO / "senkosp.dat")
    rom = dat.read_bytes()
    outdir = REPO / "build/texpatch"
    prevdir = REPO / "captures/phase5/textures"
    outdir.mkdir(parents=True, exist_ok=True)
    prevdir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(0x53454e4b)   # fixed seed: reproducible bytes
    manifest = []
    for off, pixfmt in TARGETS:
        new, out_rgba, psnr = encode_one(rom, off, pixfmt, rng)
        blob = outdir / ("%08x.bin" % off)
        blob.write_bytes(new)
        dec.write_png(str(prevdir / ("patched-%08x.png" % off)), DST, DST, out_rgba)
        manifest.append({
            "pvrt_off": off,
            "blob": blob.name,
            "orig_len": OLD_RECORD,
            "orig_md5": hashlib.md5(rom[off:off + OLD_RECORD]).hexdigest(),
            "blob_md5": hashlib.md5(new).hexdigest(),
            "psnr_db": round(float(psnr), 2),
        })
        print("0x%08x: PSNR %.1f dB -> %s" % (off, psnr, blob.name))
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print("manifest: %d records, %d B saved in-arena" %
          (len(manifest), len(manifest) * ((SRC // 2) ** 2 - (DST // 2) ** 2)))


if __name__ == "__main__":
    main()

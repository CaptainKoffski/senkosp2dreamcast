#!/usr/bin/env python3
"""shrink_vq.py [senkosp.dat] — re-encode TARGETS (STAGE08.PAK 1024x1024 VQ
textures) at 512x512 and write patch blobs for make_gdi.py to splice into
track04 (196,608 B of texture arena each). Config F-2 (arena-fit-options.md
§7, operator 2026-08-26): one target, 0b736ff0. Runs AFTER pktx_vq.py —
appends to its manifest rather than replacing it.

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
import hashlib, importlib.util, io, json, pathlib, struct, sys, zlib
import numpy as np

REPO = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("dec", REPO / "scripts/decode_pvr_vq.py")
dec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dec)

# The shrink targets: PVRT header offsets in senkosp.dat + expected pixfmt
# (docs/kb/phase5-hardware.md §Fix scoping; GBIX headers precede, untouched).
# The fourth offender, 0b777810 (pf02), ships full-size per the 2026-08-25
# amendment. Config F-2 (arena-fit-options.md §7, operator 2026-08-26):
# exactly one hero shrinks, and the operator picked 0b736ff0 (not 0b6f67d0);
# the other two ship full-size.
TARGETS = [(0x0b736ff0, 0x01)]
# Output-format override, {pvrt_off: out_pixfmt}: re-encode in a different
# 16-bit texel format, same record size. Path proven by the 0b777810
# pf02->pf00 (ARGB1555) experiment; loader precedent for VQ-1555 is
# STAGE10.PAK (PVRT 0x0bfe6394 / 0x0bfe9c18).
OUT_PF = {}
SRC = 1024
DST = 512
OLD_RECORD = 16 + 2048 + (SRC // 2) ** 2   # 264,208
NEW_RECORD = 16 + 2048 + (DST // 2) ** 2   #  67,600
KMEANS_ITERS = 30
PSNR_FLOOR = 26.0
# v2 quality knobs (operator A/B feedback 2026-08-24: high-contrast 1-2px
# elements — lit window strips, red truss markings — smeared in stills):
# Quality knobs. Operator A/B verdict 2026-08-24: v1 (all off) IS the frozen
# version — the v2 experiments (UNSHARP 0.5 + EDGE_W 3.0) added visible
# noise (chroma shifts from per-channel sharpening + RGB565's extra green
# bit produced stray green dots) without improving the elements that
# mattered. Kept as knobs for future experiments only.
UNSHARP = 0.0   # unsharp after downscale. If ever re-tried: luma-only.
EDGE_W = 0.0    # extra codebook pull toward high-variance (edge) blocks
ALPHA_W = 1.0   # pf2 alpha emphasis. 2.0 regressed (merged small opaque
                # color features into gray codes — the red lights).
DILATE = 0      # pf2 RGB dilation into transparent texels. Off = exact v1.
MASK_W = 4.0    # importance-mask boost: a block under pure white counts
                # (1+MASK_W)x in codebook training. No mask file = exact v1.
# decoder texel order within a 2x2 block, as (dx, dy) — must match decode()
TEXELS = ((0, 0), (0, 1), (1, 0), (1, 1))


# Per-texture art override: drop a 512x512 8-bit RGB/RGBA PNG named
# <pvrt-off>.png (e.g. 0b777810.png) here and the encoder VQ-encodes it
# instead of box-downscaling the original — the export/edit/import path
# (decode with scripts/decode_pvr_vq.py, edit or AI-process, re-import).
# An optional <pvrt-off>-mask.png (512x512, white = important) reweights
# codebook training toward the marked regions (MASK_W); it composes with
# an edit PNG or with the plain downscale. Pixels are never touched —
# only code allocation shifts, so a mask cannot introduce noise.
# A <pvrt-off>-params.json ({"edge_w": .., "mask_w": ..}) overrides the
# encoder knobs per texture — written by scripts/vq_tuner.py's Save.
# ROM-derived art -> the directory stays under gitignored captures/.
EDIT_DIR = REPO / "captures/phase5/textures/edit"


def box3(img):
    """3x3 edge-padded box mean over the leading two axes."""
    h, w = img.shape[:2]
    p = np.pad(img, ((1, 1), (1, 1), (0, 0)), mode="edge")
    return sum(p[y:y + h, x:x + w] for y in (0, 1, 2) for x in (0, 1, 2)) / 9.0


def load_png_rgba(path):
    """Minimal PNG reader: 8-bit RGB/RGBA, filters 0-4. Returns (w, h, img)
    with img float32 (h, w, 4)."""
    b = path.read_bytes()
    assert b[:8] == b"\x89PNG\r\n\x1a\n", path
    o, idat = 8, b""
    while o < len(b):
        ln = struct.unpack_from(">I", b, o)[0]
        tag = b[o + 4:o + 8]
        if tag == b"IHDR":
            w, h, depth, ctype = struct.unpack_from(">IIBB", b, o + 8)
            assert depth == 8 and ctype in (2, 6), \
                "%s: need 8-bit RGB or RGBA (no palette/16-bit)" % path
            nch = 3 if ctype == 2 else 4
        elif tag == b"IDAT":
            idat += b[o + 8:o + 8 + ln]
        o += 12 + ln
    raw = zlib.decompress(idat)
    stride = w * nch
    out = np.empty((h, stride), np.uint8)
    prev = np.zeros(stride, np.int32)
    pos = 0
    for y in range(h):
        f = raw[pos]; pos += 1
        row = np.frombuffer(raw, np.uint8, stride, pos).astype(np.int32)
        pos += stride
        if f == 0:
            cur = row
        elif f == 2:
            cur = (row + prev) & 0xff
        else:               # Sub / Average / Paeth need a serial pass
            cur = np.empty(stride, np.int32)
            for i in range(stride):
                a = cur[i - nch] if i >= nch else 0
                up = prev[i]
                c = prev[i - nch] if i >= nch else 0
                if f == 1:
                    p = a
                elif f == 3:
                    p = (a + up) >> 1
                else:
                    pa, pb, pc = abs(up - c), abs(a - c), abs(a + up - 2 * c)
                    p = a if (pa <= pb and pa <= pc) else (up if pb <= pc else c)
                cur[i] = (row[i] + p) & 0xff
        out[y] = cur
        prev = cur
    img = out.reshape(h, w, nch).astype(np.float32)
    if nch == 3:
        img = np.concatenate([img, np.full((h, w, 1), 255.0, np.float32)], -1)
    return w, h, img


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
    if pixfmt == 0x00:          # ARGB1555, alpha thresholded at 128
        return (((a >= 128).astype(np.uint32) << 15)
                | (r >> 3 << 10) | (g >> 3 << 5) | (b >> 3)).astype('<u2')
    if pixfmt == 0x01:          # RGB565
        return ((r >> 3 << 11) | (g >> 2 << 5) | (b >> 3)).astype('<u2')
    if pixfmt == 0x02:          # ARGB4444, nibble*17 on decode
        q = lambda c: np.clip(np.round(c / 17.0), 0, 15).astype(np.uint32)
        return ((q(a) << 12) | (q(r) << 8) | (q(g) << 4) | q(b)).astype('<u2')
    raise SystemExit("unsupported pixfmt %02x" % pixfmt)


def unpack_texels(u, pixfmt):
    """u16 -> (..., 4) float RGBA, exactly decode()'s UNPACK arithmetic."""
    u = u.astype(np.uint32)
    if pixfmt == 0x00:
        return np.stack([(u >> 10 << 3) & 0xf8, (u >> 5 << 3) & 0xf8,
                         (u << 3) & 0xf8, (u >> 15) * 255],
                        -1).astype(np.float32)
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
    # per-texture knob overrides saved by scripts/vq_tuner.py (Save button)
    pjson = EDIT_DIR / ("%08x-params.json" % off)
    params = json.loads(pjson.read_text()) if pjson.exists() else {}
    param_note = "+params" if params else ""

    out_pf = params.get("out_pf", OUT_PF.get(off, pixfmt))
    fmt_note = "" if out_pf == pixfmt else "->pf%02x" % out_pf

    # optional importance mask: per-2x2-block training weight 1+mask_w*luma
    mask = EDIT_DIR / ("%08x-mask.png" % off)
    blk_w = None
    mask_note = ""
    if mask.exists():
        mw, mh, mimg = load_png_rgba(mask)
        assert (mw, mh) == (DST, DST), "%s: must be %dx%d" % (mask, DST, DST)
        m = mimg[..., :3].mean(-1) / 255.0
        blk_w = 1.0 + params.get("mask_w", MASK_W) \
            * m.reshape(DST // 2, 2, DST // 2, 2).mean((1, 3)).ravel()
        mask_note = "+mask"

    edit = EDIT_DIR / ("%08x.png" % off)
    if edit.exists():
        # art override: VQ-encode the edited/AI-processed image as-is
        ew, eh, ref = load_png_rgba(edit)
        assert (ew, eh) == (DST, DST), "%s: must be %dx%d" % (edit, DST, DST)
        src_note = "edit/" + edit.name + mask_note + param_note + fmt_note
        return finish(ref, out_pf, rng, blk_w, params.get("edge_w")) + (src_note,)

    # source decode through the control-tested decoder
    w, h, pf, rgba = dec.decode(io.BytesIO(rom), off)
    assert (w, h, pf) == (SRC, SRC, pixfmt)
    img = np.frombuffer(rgba, np.uint8).reshape(SRC, SRC, 4).astype(np.float32)

    # 2x2 box downscale. ponytail: gamma-naive average — same space the PVR
    # filters in; linearize first if the A/B gate finds it too dark.
    ref = img.reshape(DST, 2, DST, 2, 4).mean((1, 3))

    if DILATE and pixfmt == 0x02:
        # Dilate visible RGB into fully-transparent texels: their RGB is
        # invisible, but bilinear sampling still reads it (fringe control),
        # and undilated noise wastes codebook fidelity on hidden bytes.
        a = ref[..., 3]
        m = (a > 0).astype(np.float32)[..., None]
        col = ref[..., :3] * m
        for _ in range(4):
            ns, nm = box3(col), box3(m)
            fill = (m == 0) & (nm > 0)
            col = np.where(fill, ns / np.maximum(nm, 1e-9), col)
            m = np.where(fill, 1.0, m)
        ref = ref.copy()
        ref[..., :3] = np.where(a[..., None] > 0, ref[..., :3], col)

    if UNSHARP:
        ref = np.clip(ref + UNSHARP * (ref - box3(ref)), 0.0, 255.0)

    return finish(ref, out_pf, rng, blk_w, params.get("edge_w")) \
        + ("box-downscale" + mask_note + param_note + fmt_note,)


def finish(ref, pixfmt, rng, blk_w=None, edge_w=None):
    """VQ-encode a prepared 512x512 float RGBA target into a PVRT record."""
    # 2x2 blocks as 16-vectors in decoder texel order (dx-major, dy fastest).
    # Training runs in a per-channel scaled space (alpha boosted for pf2);
    # the scaling is uniform across blocks, so Euclidean distance stays valid.
    scale = np.ones(16, np.float32)
    if pixfmt == 0x02:
        scale[3::4] = ALPHA_W
    vecs = ref.reshape(DST // 2, 2, DST // 2, 2, 4) \
              .transpose(0, 2, 3, 1, 4).reshape(-1, 16).copy()
    uniq, inv, counts = np.unique(vecs, axis=0, return_inverse=True,
                                  return_counts=True)
    # edge measured in UNSCALED space — a channel-emphasis scale must not
    # skew which blocks count as high-contrast (the ALPHA_W=2.0 regression)
    edge = uniq.std(1)
    if blk_w is None:
        base = counts
    else:   # mask: sum per-block importance instead of a flat count per block
        base = np.bincount(inv, weights=blk_w, minlength=len(uniq))
    ew = EDGE_W if edge_w is None else float(edge_w)
    wgt = base * (1.0 + ew * edge / max(float(edge.max()), 1e-9))
    uniq = uniq * scale
    cent = kmeans(uniq, wgt, 256, rng)

    # store quantized, then assign against what will actually be stored
    packed = pack_texels((cent / scale).reshape(256, 4, 4), pixfmt)  # (256,4)
    stored = unpack_texels(packed, pixfmt).reshape(256, 16) * scale
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
    # F-2 merge: pktx_vq.py runs first and writes the portrait/ring manifest
    # wholesale; this script appends its shrink records (idempotent — its own
    # offsets are dropped before re-adding).
    mf = outdir / "manifest.json"
    manifest = json.loads(mf.read_text()) if mf.exists() else []
    manifest = [m for m in manifest if m["pvrt_off"] not in {o for o, _ in TARGETS}]
    for off, pixfmt in TARGETS:
        # per-texture seed: reproducible AND independent of target-list order,
        # so a vq_tuner.py preview byte-matches the build for every texture
        rng = np.random.default_rng(0x53454e4b ^ off)
        new, out_rgba, psnr, src_note = encode_one(rom, off, pixfmt, rng)
        blob = outdir / ("%08x.bin" % off)
        blob.write_bytes(new)
        dec.write_png(str(prevdir / ("patched-%08x.png" % off)), DST, DST, out_rgba)
        manifest.append({
            "pvrt_off": off,
            "blob": blob.name,
            "source": src_note,
            "orig_len": OLD_RECORD,
            "orig_md5": hashlib.md5(rom[off:off + OLD_RECORD]).hexdigest(),
            "blob_md5": hashlib.md5(new).hexdigest(),
            "psnr_db": round(float(psnr), 2),
        })
        print("0x%08x: PSNR %.1f dB (%s) -> %s" % (off, psnr, src_note, blob.name))
    mf.write_text(json.dumps(manifest, indent=1))
    print("manifest: %d records total, %d B saved in-arena by shrink" %
          (len(manifest), len(TARGETS) * ((SRC // 2) ** 2 - (DST // 2) ** 2)))


if __name__ == "__main__":
    main()

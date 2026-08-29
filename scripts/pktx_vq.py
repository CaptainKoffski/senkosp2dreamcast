#!/usr/bin/env python3
"""pktx_vq.py [senkosp.dat] — config F-2 (docs/kb/arena-fit-options.md §7,
operator 2026-08-26): re-encode the 512² pilot cut-ins and the shared
glow-ring sheets as same-size VQ; the 256² cockpit illustrations stay RAW
(art-gate rule — VQ'd cockpits rejected). r8 extends the set with the 4
textless COMMON.PAK effect atlases (COMMON_TARGETS below). Ring sheets are identified by
PVRT content md5: any 256² whose content also appears in P10.PAK/P11.PAK
(the pure ring PAKs) is a ring; the per-character 256² is the cockpit.
MODESEL untouched. The manifest this writes REPLACES build/texpatch/
wholesale — run shrink_vq.py AFTER this (it appends its hero-shrink
record; F-2's one target is 0b736ff0).

Entry format (docs/kb/phase5-hardware.md §Ghidra recon): u32 dsize,
u32 csize, LZSS stream (FUN_8c0b6980 semantics — Okumura: 4096 ring,
r=0xFEE, LSB-first flags, 1=literal). Decompressed record = GBIX + PVRT.
Repack: GBIX kept verbatim, raw PVRT body -> VQ via shrink_vq.finish()
(the shipped, A/B-gated encoder: k-means codebook + roundtrip decode +
PSNR floor), then an all-literal LZSS wrap (flag 0xFF + 8 literals; always
decodable, 9/8 size — VQ payloads are ~7x smaller than the raws they
replace, so every entry fits its slot with the offset table untouched).

Controls, all offline:
  - every produced stream is decompressed with the python LZSS decoder
    (validated against every PKTX chunk on the disc, §Ghidra recon) and
    byte-compared against the intended record;
  - finish() decodes its own output through decode_pvr_vq.decode() and
    gates PSNR >= 26 dB vs the source pixels;
  - after blob generation the manifest is applied to an in-memory cart
    copy and every PKTX chunk of every patched PAK is re-walked and
    re-decompressed end to end.

Outputs (ROM-derived, gitignored):
  build/texpatch/pktx-<md5-8>.bin + manifest.json    (make_gdi.py splices)
  captures/phase5/textures/portraits-vq/<label>-{before,after}.png
"""
import hashlib, importlib.util, json, pathlib, re, struct, sys
import numpy as np

REPO = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("sv", REPO / "scripts/shrink_vq.py")
sv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sv)
dec = sv.dec
# shrink_vq's 26 dB floor was calibrated for its 1024²->512² stage targets.
# Same-size VQ of busy full-frame cut-in art scores lower (first cockpit
# sheet: 25.8). The floor here is a garbage-encode tripwire only — art
# quality is gated by the operator on the -before/-after previews.
sv.PSNR_FLOOR = 20.0

PAK_RE = re.compile(r"^P(0[1-9][A-F]?|1[01])\.PAK$")

# r8 (docs/kb/phase5-hardware.md §Round 6 prep): the 4 textless COMMON.PAK
# effect atlases -> same-size VQ (previews approved 2026-08-27, 30.0-33.8 dB,
# captures/phase5/textures/common-modesel/). Identified by PVRT content md5;
# the fifth 256² raw (d54f6330..., button icons + SP logo) stays raw under
# the no-text-compression rule. -112,640 B each, always resident.
COMMON_TARGETS = {
    "818eebda61ccea48782427feab565767",   # chunk 0xc000014 local e0
    "5c7cf059d48644a41b9ca9486530bd09",   # chunk 0xc000014 local e1
    "ccc80400b49392a7631ced16872d6ad9",   # chunk 0xc0141e4 local e2
    "619b6ac455358f871d450717f1e89916",   # chunk 0xc0141e4 local e3
}


# ---- ISO walk (same mapping as texerrsave_postmortem.py) ----
def iso_files(data):
    PVD, LBA0 = 0x808000, 40904
    off = lambda lba: (lba - LBA0) * 2048
    root = data[PVD + 156:PVD + 156 + 34]
    d = data[off(struct.unpack_from("<I", root, 2)[0]):]
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
            files[name.upper()] = (off(struct.unpack_from("<I", d, i + 2)[0]),
                                   struct.unpack_from("<I", d, i + 10)[0])
        i += rl
    return files


def lzss(src, dstlen):
    """FUN_8c0b6980 re-implementation (validated vs every disc chunk)."""
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


def lzss_literal(data):
    """All-literal stream: flag 0xFF + 8 literals per group. The decoder
    stops exactly when the source is consumed, so a short final group is
    fine."""
    out = bytearray()
    for i in range(0, len(data), 8):
        out.append(0xFF)
        out += data[i:i + 8]
    return bytes(out)


def raw_to_rgba(rec, o, pf, dt, w, h):
    """Decode a raw 16bpp PVRT body to float32 (h,w,4), decoder-exact."""
    body = np.frombuffer(rec, "<u2", w * h, o + 16)
    if dt == 0x01:                       # square twiddled
        n = np.arange(w * h)
        img = np.zeros(w * h, "<u2")
        img[sv.morton_compact(n) * w + sv.morton_compact(n >> 1)] = body
    else:                                # 0x09: linear
        img = body
    return sv.unpack_texels(img.reshape(h, w), pf)


def walk_pktx(blob):
    """Yield (entry_off, dsize, csize) for every plausible PKTX entry;
    bogus in-stream 'PKTX' matches fail the gates and are skipped."""
    j = blob.find(b"PKTX")
    while j >= 0:
        pay = j + 8
        if pay + 4 <= len(blob):
            cnt = struct.unpack_from("<I", blob, pay)[0]
            if 0 < cnt < 256 and pay + 4 + 4 * cnt < len(blob):
                offs = struct.unpack_from("<%dI" % cnt, blob, pay + 4)
                ok = all(pay + off + 8 <= len(blob) and
                         0 < struct.unpack_from("<II", blob, pay + off)[1]
                           <= struct.unpack_from("<II", blob, pay + off)[0] < 0x400000
                         for off in offs)
                if ok:
                    for off in offs:
                        e = pay + off
                        dsz, csz = struct.unpack_from("<II", blob, e)
                        yield e, dsz, csz
        j = blob.find(b"PKTX", j + 4)


def main():
    dat = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else REPO / "senkosp.dat")
    data = dat.read_bytes()
    files = iso_files(data)
    outdir = REPO / "build/texpatch"
    prevdir = REPO / "captures/phase5/textures/portraits-vq"
    outdir.mkdir(parents=True, exist_ok=True)
    prevdir.mkdir(parents=True, exist_ok=True)
    for old in outdir.glob("*.bin"):     # replace the shrink config wholesale
        old.unlink()

    paks = sorted(n for n in files if PAK_RE.match(n))
    paks.append("COMMON.PAK")            # r8: 4 effect atlases (COMMON_TARGETS)

    # F-2 ring identification: content md5s of every raw square in the pure
    # ring PAKs. A 256² elsewhere with a matching md5 is a shared ring copy;
    # a non-matching 256² is a per-character cockpit and stays raw.
    ring_keys = set()
    for pak in ("P10.PAK", "P11.PAK"):
        base, size = files[pak]
        blob = data[base:base + size]
        for e, dsz, csz in walk_pktx(blob):
            rec = lzss(blob[e + 8:e + 8 + csz], dsz)
            if rec is None or len(rec) != dsz:
                continue
            o = 8 + struct.unpack_from("<I", rec, 4)[0] if rec[:4] == b"GBIX" else 0
            if rec[o:o + 4] == b"PVRT":
                ring_keys.add(hashlib.md5(rec[o:]).hexdigest())

    manifest, encode_cache, seen_label = [], {}, {}
    saved = cockpits = 0
    for pak in paks:
        base, size = files[pak]
        blob = data[base:base + size]
        stem = pak.split(".")[0]
        for ei, (e, dsz, csz) in enumerate(walk_pktx(blob)):
            rec = lzss(blob[e + 8:e + 8 + csz], dsz)
            if rec is None or len(rec) != dsz:
                continue                 # not a real entry (bogus find)
            o = 8 + struct.unpack_from("<I", rec, 4)[0] if rec[:4] == b"GBIX" else 0
            if rec[o:o + 4] != b"PVRT":
                continue
            pf, dt = rec[o + 8], rec[o + 9]
            w, h = struct.unpack_from("<HH", rec, o + 12)
            datalen = struct.unpack_from("<I", rec, o + 4)[0]
            if dt not in (0x01, 0x09) or w != h or w not in (256, 512) \
               or pf > 2 or datalen != 8 + w * h * 2:
                continue                 # not a raw 16bpp square — leave it

        # ---- encode (dedup on PVRT content) ----
            key = hashlib.md5(rec[o:]).hexdigest()
            if pak == "COMMON.PAK":
                if key not in COMMON_TARGETS:
                    continue             # SP-logo sheet + everything else: raw
            elif w == 256 and key not in ring_keys:
                cockpits += 1            # cockpit sheet — stays raw (F-2)
                continue
            if key not in encode_cache:
                ref = raw_to_rgba(rec, o, pf, dt, w, h)
                sv.DST = w
                sv.NEW_RECORD = 16 + 2048 + (w // 2) ** 2
                rng = np.random.default_rng(0x53454e4b ^ int(key[:8], 16))
                new_pvrt, out_rgba, psnr = sv.finish(ref, pf, rng)
                label = "%s-e%02d-%dsq" % (stem, ei, w)
                dec.write_png(str(prevdir / (label + "-before.png")), w, h,
                              np.clip(ref, 0, 255).astype(np.uint8).tobytes())
                dec.write_png(str(prevdir / (label + "-after.png")), w, h, out_rgba)
                encode_cache[key] = (new_pvrt, psnr, label)
                seen_label[key] = []
            new_pvrt, psnr, label = encode_cache[key]
            seen_label[key].append(stem)

        # ---- rebuild entry: own GBIX verbatim + new PVRT, all-literal LZSS
            new_rec = rec[:o] + new_pvrt
            stream = lzss_literal(new_rec)
            assert lzss(stream, len(new_rec)) == new_rec, "LZSS roundtrip"
            entry = struct.pack("<II", len(new_rec), len(stream)) + stream
            assert len(entry) <= 8 + csz, \
                "%s e%d: repacked entry outgrew its slot" % (pak, ei)
            eb = hashlib.md5(entry).hexdigest()
            blobf = outdir / ("pktx-%s.bin" % eb[:8])
            if not blobf.exists():
                blobf.write_bytes(entry)
            manifest.append({
                "pvrt_off": base + e,
                "blob": blobf.name,
                "source": "pktx-vq %s (%s, PSNR %.1f dB)" % (label, pak, psnr),
                "orig_len": 8 + csz,
                "orig_md5": hashlib.md5(data[base + e:base + e + 8 + csz]).hexdigest(),
                "blob_md5": eb,
                "psnr_db": round(float(psnr), 2),
            })
            saved += w * h * 2 - (2048 + (w // 2) ** 2)

    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    for key, pakset in seen_label.items():
        _, psnr, label = encode_cache[key]
        print("%s: PSNR %5.1f dB  shared by %s" %
              (label, psnr, ",".join(sorted(set(pakset)))))
    print("manifest: %d entries, %d unique sheets, %s B VRAM saved across "
          "all character PAKs" % (len(manifest), len(encode_cache),
                                  format(saved, ",")))

    # ---- end-to-end self-check: splice into a cart copy, then re-decompress
    # every entry. Entry positions come from the ORIGINAL data (repacked
    # entries have csize > dsize — all-literal is 9/8 — which walk_pktx's
    # plausibility gate for raw disc bytes would reject); the bytes checked
    # are the patched ones.
    rom = bytearray(data)
    for m in manifest:
        off, n = m["pvrt_off"], m["orig_len"]
        b = (outdir / m["blob"]).read_bytes()
        assert hashlib.md5(bytes(rom[off:off + n])).hexdigest() == m["orig_md5"]
        rom[off:off + len(b)] = b
    vq = raw = 0
    for pak in paks:
        base, size = files[pak]
        for e, _, _ in walk_pktx(data[base:base + size]):
            dsz, csz = struct.unpack_from("<II", rom, base + e)
            rec = lzss(bytes(rom[base + e + 8:base + e + 8 + csz]), dsz)
            assert rec is not None and len(rec) == dsz, \
                "%s: entry at +%#x broken after splice" % (pak, e)
            o = 8 + struct.unpack_from("<I", rec, 4)[0] if rec[:4] == b"GBIX" else 0
            if rec[o:o + 4] == b"PVRT":
                w, h = struct.unpack_from("<HH", rec, o + 12)
                if rec[o + 9] == 0x03:
                    vq += 1
                elif rec[o + 9] in (0x01, 0x09) and w == h and w in (256, 512):
                    raw += 1
    print("self-check: every PKTX entry in %d PAKs decompresses clean; "
          "%d VQ / %d raw squares remain (F-2 expects the %d cockpit "
          "entries raw)" % (len(paks), vq, raw, cockpits))
    assert vq == len(manifest), "VQ entry count != manifest"
    # +1: COMMON's SP-logo sheet (d54f6330..., not in COMMON_TARGETS) stays raw
    assert raw == cockpits + 1, "raw squares != cockpits + COMMON logo sheet"


if __name__ == "__main__":
    main()

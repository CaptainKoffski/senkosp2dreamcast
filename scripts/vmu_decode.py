#!/usr/bin/env python3
"""Decode the SENKOSP_SYS save file out of a Flycast VMU image (vmu_save_*.bin).

    vmu_decode.py <vmu_save.bin> [--icon out.png]

Prints header fields (key value, one per line), crc_ok, the payload hex and
the payload decoded by name (menu_def.py). Exit 1 when the card has no
SENKOSP_SYS file (or no valid root).

Sources (primary):
  - Image = 256 blocks x 512 B; a block write lands at Block*512 (Flycast
    core/hw/maple/maple_devs.cpp:679-707, write_adr = Block*512 + ...).
  - Root at block 255, vmu_root_t (KOS tools/kos/kernel/arch/dreamcast/
    include/dc/vmufs.h:55-70): magic[16]=0x55 @0, fat_loc u16 @0x46,
    fat_size @0x48, dir_loc @0x4a, dir_size @0x4c, icon_shape @0x4e,
    blk_cnt @0x50 (little-endian).
  - Directory entry 32 B, vmu_dir_t (vmufs.h:71-86): filetype @0, firstblk
    u16 @2, filename[12] @4 (no NUL), filesize u16 @24, hdroff u16 @26.
  - FAT = one u16 per block at fat_loc; the directory (from dir_loc) and a
    file (from its firstblk) are chains through it, 0xfffa = last block,
    0xfffc = free.
  - VMS header, vmu_hdr_t (tools/kos/kernel/arch/dreamcast/include/dc/
    vmu_pkg.h:70-80): desc_short[16] @0, desc_long[32] @16, app_id[16] @48,
    icon_cnt u16 @64, icon_anim_speed @66, eyecatch_type @68, crc u16 @70,
    data_len u32 @72, reserved[20], icon_pal[16] u16 ARGB4444 @96; then
    512 B per icon, the eyecatch (none here), the payload.
  - CRC: net_crc16ccitt (tools/kos/kernel/net/net_crc.c:52-63; poly 0x1021,
    init 0, unreflected) over header+icons+eyecatch+payload with the crc
    field zeroed -- total_size, not the block-padded file (vmu_pkg.c:149-166).
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import menu_def as M    # noqa: E402

IMG_SIZE = 256 * 512
FAT_END = 0xFFFA


def crc16ccitt(data, start=0):
    rv = start
    for b in data:
        tmp = (rv >> 8) ^ b
        tmp ^= tmp >> 4
        rv = ((rv << 8) ^ (tmp << 12) ^ (tmp << 5) ^ tmp) & 0xFFFF
    return rv


def read_image(path):
    img = open(path, "rb").read()
    if len(img) != IMG_SIZE:
        raise ValueError(f"{path}: {len(img)} bytes, want {IMG_SIZE}")
    return img


def _chain(img, fat_loc, first):
    """Concatenated blocks of the FAT chain starting at `first`."""
    out, b = b"", first
    for _ in range(256):                       # a loop in a corrupt FAT must not hang us
        if b >= 256:
            break
        out += img[b * 512:(b + 1) * 512]
        b = struct.unpack_from("<H", img, fat_loc * 512 + 2 * b)[0]
        if b == FAT_END:
            return out
    raise ValueError("FAT chain does not end")


def find_file(img, name):
    """The file's blocks (whole 512-B blocks, filesize of them) or None. ValueError on a bad root."""
    if len(img) != IMG_SIZE:
        raise ValueError(f"image is {len(img)} bytes, want {IMG_SIZE}")
    root = img[255 * 512:256 * 512]
    if root[:16] != b"\x55" * 16:
        raise ValueError("block 255 is not a VMU root (magic != 0x55 x16)")
    fat_loc, _fat_size, dir_loc, _dir_size = struct.unpack_from("<4H", root, 0x46)
    d = _chain(img, fat_loc, dir_loc)
    for i in range(0, len(d), 32):
        ftype, _prot, first, fname = struct.unpack_from("<BBH12s", d, i)
        size = struct.unpack_from("<H", d, i + 24)[0]
        if ftype and fname.rstrip(b"\0") == name.encode():       # KOS compares 12 bytes with strncmp (vmufs.c:205-220)
            return _chain(img, fat_loc, first)[:size * 512]
    return None


def parse_vms(f):
    desc_short, desc_long, app_id, icon_cnt, anim, ec, crc, data_len = struct.unpack_from("<16s32s16sHHHHI", f, 0)
    pal = struct.unpack_from("<16H", f, 96)
    if ec != 0:
        raise ValueError(f"eyecatch type {ec} unsupported (ours is none)")
    hdr = 128 + 512 * icon_cnt
    total = hdr + data_len
    if total > len(f):
        raise ValueError(f"header says {total} bytes, file has {len(f)}")
    z = bytearray(f[:total]); z[70:72] = b"\0\0"
    crc_calc = crc16ccitt(bytes(z), 0)
    txt = lambda b: b.rstrip(b" \0").decode("ascii", "replace")   # noqa: E731
    return {"desc_short": txt(desc_short), "desc_long": txt(desc_long), "app_id": txt(app_id),
            "icon_cnt": icon_cnt, "icon_anim_speed": anim, "eyecatch_type": ec, "crc": crc,
            "crc_calc": crc_calc, "crc_ok": crc == crc_calc,
            "data_len": data_len, "icon_pal": pal, "icon": f[128:128 + 512 * min(icon_cnt, 1)],
            "payload": f[hdr:total]}


def decode_payload(p):
    """Payload v1 = "SKSP", version, 3 reserved, 16-byte record, 116-byte ctl_lib_t
    (loader/vmu_save.h; ctl_lib_t = custom[2][8][6] @0, used[2][8] @96, sel[2][2] @112)."""
    if len(p) != 140 or p[:4] != b"SKSP":
        raise ValueError("not a SKSP payload (need 140 bytes starting SKSP)")
    rec, lib = p[8:24], p[24:]
    d = {"version": p[4], "record": rec.hex(), "settings": {}}
    for name, idx, vals, *_ in M.SETTINGS:
        d["settings"][name] = next((lbl for lbl, b in vals if b == rec[idx]), f"?0x{rec[idx]:02x}")
    for cls, (cname, buttons, layouts, _anchors) in enumerate(M.CTL_CLASSES):
        slots = []
        for s in range(M.CTL_N_CUSTOM):
            ids = lib[(cls * M.CTL_N_CUSTOM + s) * 6:][:6]
            word = lambda i: M.FUNC_WORDS[i] if i < len(M.FUNC_WORDS) else f"?{i}"   # noqa: E731
            slots.append(dict(zip(buttons, map(word, ids))) if lib[96 + cls * M.CTL_N_CUSTOM + s] else None)
        sel = []
        for port in range(M.CTL_PORTS):
            n = lib[112 + cls * M.CTL_PORTS + port]
            sel.append(layouts[n][0] if n < len(layouts) else f"CUSTOM {n - len(layouts) + 1}")
        d[cname.lower()] = {"slots": slots, "sel": sel}
    return d


def icon_png(vms, out):
    """The 32x32 4bpp icon (high nibble = left pixel, ARGB4444 palette), scaled 8x."""
    from PIL import Image
    pal = [tuple(((c >> sh) & 0xF) * 17 for sh in (8, 4, 0)) for c in vms["icon_pal"]]
    im = Image.new("RGB", (32, 32))
    im.putdata([pal[n] for b in vms["icon"] for n in (b >> 4, b & 15)])
    im.resize((256, 256), Image.NEAREST).save(out)


def main(argv):
    args = [a for a in argv[1:] if a != "--icon"]
    icon_out = argv[argv.index("--icon") + 1] if "--icon" in argv else None
    if icon_out:
        args.remove(icon_out)
    if len(args) != 1:
        print("usage: vmu_decode.py <vmu_save.bin> [--icon out.png]", file=sys.stderr)
        return 2
    try:
        f = find_file(read_image(args[0]), M.VMU_FILE["name"])
    except ValueError as e:
        print(f"ERROR {e}")
        return 1
    if f is None:
        print(f"ERROR no {M.VMU_FILE['name']} on {args[0]}")
        return 1
    v = parse_vms(f)
    print(f"file {M.VMU_FILE['name']} bytes {len(f)}")
    for k in ("desc_short", "desc_long", "app_id", "icon_cnt", "eyecatch_type", "data_len"):
        print(f"{k} {v[k]}")
    print(f"crc 0x{v['crc']:04x}")
    print(f"crc_ok {1 if v['crc_ok'] else 0}")
    print(f"payload {v['payload'].hex()}")
    if icon_out:
        icon_png(v, icon_out)
        print(f"icon {icon_out}")
    d = decode_payload(v["payload"])
    print(f"version {d['version']}")
    for name, label in d["settings"].items():
        print(f"setting {name} = {label}")
    for cname, _b, _l, _a in M.CTL_CLASSES:
        c = d[cname.lower()]
        for s, lay in enumerate(c["slots"]):
            if lay:
                print(f"{cname.lower()} slot {s} = " + " ".join(f"{b}={w}" for b, w in lay.items()))
        for port, sel in enumerate(c["sel"]):
            print(f"P{port + 1} {cname} = {sel}")
    return 0 if v["crc_ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

#!/usr/bin/env python3
"""Self-check for check_stream_crc.py -- synthetic dat/track04 fixtures run
through the real CLI via subprocess (CHECK lines, exit code), same house
style as test_parse_cartlog.py (plain asserts, 'ok' on success)."""
import os
import subprocess
import sys
import tempfile
import zlib

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "check_stream_crc.py")


def crc(buf):
    return zlib.crc32(buf) & 0xffffffff


def run(*args):
    p = subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


with tempfile.TemporaryDirectory() as d:
    # -- ground-truth fixtures ------------------------------------------
    # 16 KiB fake cart image (senkosp.dat stand-in).
    dat = bytes(range(256)) * 64
    dat_path = os.path.join(d, "senkosp.dat")
    with open(dat_path, "wb") as f:
        f.write(dat)

    # Fake track04.iso: boot region (2 sectors, mirrors the real
    # BOOT_REGION=3538944 scaled down) + the fake dat as the cart payload.
    # Layout is expressed purely via --track04-base-fad + this file's bytes
    # -- BASE_FAD deliberately != the real 450150 default, to prove the flag
    # is actually read, not hardcoded.
    BASE_FAD = 200
    BOOT_SECTORS = 2
    boot = b"\0" * (BOOT_SECTORS * 2048)
    track04 = boot + dat
    track04_path = os.path.join(d, "track04.iso")
    with open(track04_path, "wb") as f:
        f.write(track04)
    CART_FAD = BASE_FAD + BOOT_SECTORS   # fad where the fake dat begins

    # -- SHIMCRC fixtures: offsets straight into `dat` -------------------
    o1, l1 = 0, 100
    o2, l2 = 4096, 512
    o3, l3 = 8000, 40
    c1, c2 = crc(dat[o1:o1 + l1]), crc(dat[o2:o2 + l2])
    c3_right = crc(dat[o3:o3 + l3])
    c3_wrong = c3_right ^ 0xffffffff

    # One line carries a Flycast-style prefix (timestamp/logger text) --
    # proves the unanchored re.search survives it. \r\n line endings mirror
    # what the serial layer actually emits.
    PREFIX = "2026-08-23-12:22:43.232-Flycast[1:1]-N[TEST]: "

    def stdout_log(c3):
        return (
            f"SHIMCRC o={o1:08x} l={l1:08x} c={c1:08x}\r\n"
            f"{PREFIX}SHIMCRC o={o2:08x} l={l2:08x} c={c2:08x}\r\n"
            f"SHIMCRC o={o3:08x} l={l3:08x} c={c3:08x}\r\n"
        )

    stdout_wrong = os.path.join(d, "wrong.stdout.log")
    with open(stdout_wrong, "w", newline="") as f:
        f.write(stdout_log(c3_wrong))
    stdout_ok = os.path.join(d, "ok.stdout.log")
    with open(stdout_ok, "w", newline="") as f:
        f.write(stdout_log(c3_right))

    # -- GDPIO/GDDMA fixtures --------------------------------------------
    # One correct record in the cart region; one fad < base (TOC/low-track
    # read -- must be listed, must never fail); one type != 0x800 (raw/TOC
    # read -- must be listed, must never fail).
    gd_secs, gd_type = 1, 0x800
    gd_crc = crc(dat[0:gd_secs * gd_type])
    lowfad_fad = BASE_FAD - 50
    typeskip_fad = CART_FAD
    cartlog = (
        f"GDPIO fad={CART_FAD:08x} secs={gd_secs:x} type={gd_type:x} crc={gd_crc:08x}\n"
        f"GDDMA fad={lowfad_fad:08x} secs=4 type=800 crc=deadbeef\n"
        f"GDPIO fad={typeskip_fad:08x} secs=4 type=400 crc=deadbeef\n"
    )
    cartlog_path = os.path.join(d, "ok.log")
    with open(cartlog_path, "w") as f:
        f.write(cartlog)

    common = ["--dat", dat_path, "--track04", track04_path,
              "--track04-base-fad", str(BASE_FAD)]

    # -- wrong CRC -> exit 1, shimcrc_match FAIL --------------------------
    rc, out, err = run("--stdout", stdout_wrong, "--cartlog", cartlog_path, *common)
    assert rc == 1, (rc, out, err)
    assert "CHECK shimcrc_match: FAIL" in out, out
    assert "CHECK gdread_match: PASS" in out, out

    # -- corrected -> exit 0 -----------------------------------------------
    rc, out, err = run("--stdout", stdout_ok, "--cartlog", cartlog_path, *common)
    assert rc == 0, (rc, out, err)
    assert "CHECK shimcrc_match: PASS" in out, out
    assert "CHECK gdread_match: PASS" in out, out
    assert "CHECK coverage_nonzero: PASS" in out, out

    # -- low-fad: listed under `lowfad`, never a failure --------------------
    assert "== lowfad" in out, out
    assert f"fad={lowfad_fad:08x}" in out, out

    # -- type-skip: listed under `typeskip`, never a failure ----------------
    assert "== typeskip" in out, out
    assert f"fad={typeskip_fad:08x}" in out, out

    # -- empty logs on both streams -> coverage_nonzero FAIL, exit 1 --------
    empty_stdout = os.path.join(d, "empty.stdout.log")
    empty_cartlog = os.path.join(d, "empty.log")
    open(empty_stdout, "w").close()
    open(empty_cartlog, "w").close()
    rc, out, err = run("--stdout", empty_stdout, "--cartlog", empty_cartlog, *common)
    assert rc == 1, (rc, out, err)
    assert "CHECK coverage_nonzero: FAIL" in out, out
    # vacuous PASS on the other two -- nothing to compare, nothing mismatches
    assert "CHECK shimcrc_match: PASS" in out, out
    assert "CHECK gdread_match: PASS" in out, out

    # -- byte range past end of track04.iso -> FAIL, not a skip -------------
    oor_fad = CART_FAD + (len(dat) // 2048) + 100
    oor_log = os.path.join(d, "oor.log")
    with open(oor_log, "w") as f:
        f.write(f"GDPIO fad={oor_fad:08x} secs=1 type=800 crc=deadbeef\n")
    rc, out, err = run("--stdout", stdout_ok, "--cartlog", oor_log, *common)
    assert rc == 1, (rc, out, err)
    assert "CHECK gdread_match: FAIL" in out, out

    # -- in-range GDPIO with a corrupted crc= -> FAIL via the byte-compare
    # itself, distinct from the out-of-range guard above (must exercise the
    # actual got == c comparison, not just the off + length > size check).
    badcrc_log = os.path.join(d, "badcrc.log")
    with open(badcrc_log, "w") as f:
        f.write(f"GDPIO fad={CART_FAD:08x} secs={gd_secs:x} type={gd_type:x} "
                 f"crc={gd_crc ^ 0xffffffff:08x}\n")
    rc, out, err = run("--stdout", stdout_ok, "--cartlog", badcrc_log, *common)
    assert rc == 1, (rc, out, err)
    assert "CHECK gdread_match: FAIL" in out, out

    # -- --tail N: last N records of EACH stream, with verify status --------
    rc, out, err = run("--stdout", stdout_ok, "--cartlog", cartlog_path,
                        "--tail", "2", *common)
    assert rc == 0, (rc, out, err)
    assert "== tail: last 2 shim record" in out, out
    assert "== tail: last 2 drive record" in out, out
    assert "-> PASS" in out, out

print("ok")

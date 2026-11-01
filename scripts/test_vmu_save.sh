#!/bin/sh
# VMU persistence emulator legs (plan 2026-11-01-vmu-persistence, Task 5).
# Launch/quit idiom and the redirected-VMU-dir flags are test_vmu_untouched.sh's
# (that script's header cites the Flycast source for each); everything lands in
# captures/vmu-save/ (gitignored).
#
#   diag [vmudir]  needs the `make gdi VMUDIAG=1 SERIAL=1` disc as build/disc.gdi.
#                  boot1: blank VMU A1 -> the menu forces a known state and
#                         writes it (VMUSAVE load=-1 / write=0 slot=A1); the
#                         file is decoded (vmu_decode.py) against menu_def.py.
#                  boot2: same dir -> VMUSAVE load=0 home=A1, payload == the
#                         decoder's payload hex; A1 not rewritten.
#                  boot3: nocard (no VMU on A1, fresh dir) -> load=-1 home=-0
#                         cards=0 and the game still boots (boot: MAIN image).
#   show <vmudir>  needs the plain `make gdi` disc. Boots with the dir from `diag`,
#                  dumps the scan-out framebuffer of the pre-game menu
#                  (FLYCAST_SHOT_RAWFB + kill -USR2, docs/kb/tooling.md §RAWFB,
#                  capture_rawfb_leg.sh header) to menu_fb.png; A1 must stay
#                  byte-identical (a menu sitting with no input does not write).
#
# Each launch is a direct child ($! is Flycast itself), reaped after SIGTERM --
# stdout is block-buffered when redirected, so a graceful quit is what flushes the
# VMUSAVE lines (never SIGKILL first). Secs per boot: VMU_LEG_SECS (default 60).
set -eu

MODE="${1:-}"; DIR="${2:-}"
case "$MODE" in diag|show) ;; *) echo "usage: $0 diag [vmudir] | show <vmudir>" >&2; exit 2 ;; esac
REPO="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$REPO/../flycast4naomi2dreamcast/build/Flycast.app/Contents/MacOS/Flycast"
DISC="$REPO/build/disc.gdi"
OUT="$REPO/captures/vmu-save"
SECS="${VMU_LEG_SECS:-60}"
[ -x "$BIN" ]  || { echo "ERROR: Flycast not built (sibling repo): $BIN" >&2; exit 1; }
[ -f "$DISC" ] || { echo "ERROR: disc not built: $DISC" >&2; exit 1; }
mkdir -p "$OUT"
cd "$REPO"

defaults write com.flyinghead.Flycast ApplePersistenceIgnoreState -bool YES 2>/dev/null || true
defaults write com.flyinghead.Flycast NSQuitAlwaysKeepsWindows -bool false 2>/dev/null || true
# Headless: hidden window, app never activated (no Dock icon / focus steal), null audio; GL still renders
# offscreen so the RAWFB dump works -- ../flycast4naomi2dreamcast/core/sdl/sdl.cpp:841-843,965-975.
export FLYCAST_HEADLESS=1

# fly <name> <secs> <a1dev> <vmudir> [usr2_at]
# Pad on port A with VMU A1 only (a1dev 1 = MDT_SegaVMU, 10 = MDT_None; NOT 0,
# which is MDT_SegaController): MapleDeviceType values at
# ../flycast4naomi2dreamcast/core/hw/maple/maple_cfg.h:8 (SegaController = 0),
# :9 (SegaVMU = 1), :18 (MDT_None = 10). Ports B..D and A2 are pinned to None so
# the card count is the leg's, not emu.cfg's (which has a pad + two VMUs on B).
# pvr.rend=0: a leftover Vulkan setting segfaults this bundle (tooling.md §RAWFB).
# Serial console: Option "Debug.SerialConsoleEnabled" lives in the default
# `config` section (fork core/cfg/option.cpp:132, option.h:107), hence
# config:Debug.SerialConsoleEnabled -- not a "Debug:" section.
# Log: $OUT/<name>.stdout.log; a startup SH4 vmem "Verify Failed" (known host
# flake) is set aside as <name>.flakeN.stdout.log and relaunched, up to 3 tries.
# usr2_at: seconds after launch to send SIGUSR2 (RAWFB dump) -- once the fork's
# handler is installed (a poke before that kills Flycast).
fly() {
    name="$1"; secs="$2"; a1="$3"; vdir="$4"; usr2="${5:-}"
    case "$vdir" in *" "*) echo "ERROR: VMU dir with spaces: $vdir" >&2; exit 1 ;; esac
    cfg="-config config:Dreamcast.VMUPath=$vdir -config config:PerGameVmu=no \
 -config config:UsePhysicalVmuMemory=no -config config:rend.vsync=no \
 -config config:Debug.SerialConsoleEnabled=yes -config config:pvr.rend=0 \
 -config input:device1=0 -config input:device1.1=$a1 -config input:device1.2=10 \
 -config input:device2=10 -config input:device2.1=10 -config input:device2.2=10 \
 -config input:device3=10 -config input:device4=10"
    try=1
    while :; do
        if pgrep -x Flycast >/dev/null; then echo "ERROR: another Flycast is running" >&2; exit 2; fi
        log="$OUT/$name.stdout.log"
        if [ -e "$log" ]; then mkdir -p "$OUT/prev"; mv "$log" "$OUT/prev/$name.$(date +%H%M%S).stdout.log"; fi   # fresh log per attempt, old one kept
        "$BIN" $cfg "$DISC" > "$log" 2>&1 &
        pid=$!
        echo "launch $name (try $try, PID $pid, ${secs}s) A1dev=$a1 dir=$vdir"
        t=0; sent=0
        while [ "$t" -lt "$secs" ] && kill -0 "$pid" 2>/dev/null; do
            sleep 1; t=$((t+1))
            if [ -n "$usr2" ] && [ "$sent" = 0 ] && [ "$t" -ge "$usr2" ]; then kill -USR2 "$pid" 2>/dev/null || true; sent=1; fi
        done
        kill -TERM "$pid" 2>/dev/null || true
        n=0
        while kill -0 "$pid" 2>/dev/null && [ "$n" -lt 20 ]; do sleep 1; n=$((n+1)); done
        if kill -0 "$pid" 2>/dev/null; then
            echo "WARN: graceful quit failed; SIGKILL (buffered stdout may be lost)"
            kill -9 "$pid" 2>/dev/null || true
        fi
        rc=0; wait "$pid" 2>/dev/null || rc=$?
        echo "  $name: Flycast exit rc=$rc, alive ${t}s of ${secs}s"
        if grep -q "Verify Failed" "$log" && [ "$try" -lt 3 ]; then
            echo "flake: SH4 vmem Verify Failed -- log kept as $name.flake$try.stdout.log, relaunching"
            mv "$log" "$OUT/$name.flake$try.stdout.log"
            try=$((try+1)); continue
        fi
        if [ "$t" -lt "$secs" ]; then
            echo "FAIL $name: Flycast exited on its own after ${t}s, before the ${secs}s window"
            FAILS=$((FAILS+1))
        fi
        break
    done
}

FAILS=0
require() {   # <logfile> <fixed string> <what> [x]  (x: whole-line match; the serial log is CRLF)
    if tr -d '\r' < "$1" | grep -qF${4:-} -- "$2"; then echo "OK   $3"; else echo "FAIL $3 (missing: $2 in $1)"; FAILS=$((FAILS+1)); fi
}
sum() { shasum -a 256 "$1" | cut -d' ' -f1; }
blank_vmu() { head -c 131072 /dev/zero > "$1/vmu_save_A1.bin"; }   # Flycast auto-formats an all-zero image (maple_devs.cpp:469-475 -> initializeVmu :420-431)

if [ "$MODE" = show ]; then
    [ -d "$DIR" ] && [ -f "$DIR/vmu_save_A1.bin" ] || { echo "usage: $0 show <vmudir from diag>" >&2; exit 2; }
    PNG="$OUT/menu_fb.png"
    rm -f "$PNG"
    BEFORE="$(sum "$DIR/vmu_save_A1.bin")"
    export FLYCAST_SHOT_RAWFB="$PNG"
    fly show 40 1 "$DIR" 35   # USR2 at 35 s, quit 5 s later
    unset FLYCAST_SHOT_RAWFB
    [ -s "$PNG" ] && echo "OK   menu_fb.png written ($PNG)" || { echo "FAIL no framebuffer dump at $PNG"; FAILS=$((FAILS+1)); }
    [ "$(sum "$DIR/vmu_save_A1.bin")" = "$BEFORE" ] && echo "OK   A1 unchanged by the idle menu" || { echo "FAIL A1 was rewritten by the idle menu"; FAILS=$((FAILS+1)); }
    [ "$FAILS" = 0 ] && echo "PASS show" || echo "FAIL show"
    exit "$FAILS"
fi

# ---- diag ------------------------------------------------------------------
if [ -n "$DIR" ]; then mkdir -p "$DIR"; else DIR="$(mktemp -d /tmp/vmu-save.XXXXXX)"; fi
blank_vmu "$DIR"
A1="$DIR/vmu_save_A1.bin"

echo "== boot1: blank A1 -> forced state written"
fly boot1 "$SECS" 1 "$DIR"
L1="$OUT/boot1.stdout.log"
require "$L1" "VMUSAVE load=-1" "boot1 load=-1 (nothing on the card)"
require "$L1" "VMUSAVE write=0 slot=A1" "boot1 write=0 slot=A1"
cp "$A1" "$OUT/vmu_save_A1.bin"
if python3 "$REPO/scripts/vmu_decode.py" "$A1" --icon "$OUT/icon.png" > "$OUT/decode.txt"; then echo "OK   vmu_decode.py exit 0"; else echo "FAIL vmu_decode.py exit $?"; FAILS=$((FAILS+1)); fi
cat "$OUT/decode.txt"
python3 - > "$OUT/expect.txt" <<'EOF' || { echo "FAIL could not build the expected lines from menu_def.py"; FAILS=$((FAILS+1)); }
import sys; sys.path.insert(0, "scripts"); import menu_def as M
f = M.VMU_FILE; name, _, labels, *_ = M.SETTINGS[0]
print(f"file {f['name']} bytes 1024")                           # 2 blocks (loader/vmu_save.c VMU_BLOCKS)
print(f"desc_short {f['short']}"); print(f"desc_long {f['long']}"); print(f"app_id {f['app']}")
print("data_len 140"); print("crc_ok 1")
print(f"setting {name} = {labels[2][0]}")                      # MENU_SET_BYTE[0][2] = the third value
print("pad slot 0 = " + " ".join(f"{b}={M.CUSTOM_DEMO[b]}" for b in M.PAD_BUTTONS))
print(f"P1 PAD = {M.CTL_CUSTOM_NAMES[0]}")
EOF
while IFS= read -r line; do
    if grep -qxF -- "$line" "$OUT/decode.txt"; then echo "OK   decoded: $line"; else echo "FAIL decoded: $line"; FAILS=$((FAILS+1)); fi
done < "$OUT/expect.txt"
HEX="$(sed -n 's/^payload //p' "$OUT/decode.txt")"
[ "${#HEX}" = 280 ] && echo "OK   decoder payload is 280 hex chars" || { echo "FAIL decoder payload hex length ${#HEX}"; FAILS=$((FAILS+1)); }
SUM1="$(sum "$A1")"

echo "== boot2: same dir -> loaded back"
fly boot2 "$SECS" 1 "$DIR"
L2="$OUT/boot2.stdout.log"
require "$L2" "VMUSAVE load=0 home=A1" "boot2 load=0 home=A1"
require "$L2" "VMUSAVE payload=$HEX" "boot2 payload == decoder payload hex" x
[ "$(sum "$A1")" = "$SUM1" ] && echo "OK   boot2 left A1 byte-identical" || { echo "FAIL boot2 rewrote A1"; FAILS=$((FAILS+1)); }

echo "== boot3: no card"
NODIR="$(mktemp -d /tmp/vmu-nocard.XXXXXX)"
fly nocard "$SECS" 10 "$NODIR"
L3="$OUT/nocard.stdout.log"
require "$L3" "VMUSAVE load=-1 home=-0 cards=0" "nocard load=-1 home=-0 cards=0"
require "$L3" "boot: MAIN image" "nocard: game still boots"
rm -rf "$NODIR"

echo "VMU dir (kept): $DIR"
[ "$FAILS" = 0 ] && echo "PASS diag" || echo "FAIL diag ($FAILS)"
exit "$FAILS"

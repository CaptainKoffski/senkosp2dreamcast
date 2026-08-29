#!/bin/bash
# Serial capture leg over the coder's cable. Start BEFORE powering/booting the
# console so the loader banner lands in the log; ctrl-C when the scene is done.
# Output echoes live AND lands in captures/<leg>.log (legs are never
# overwritten -- same rule as capture_dc_leg.sh).
# Baud: 115200 = KOS dbgio scif default (kos .../include/dc/scif.h:38); the
# shim inherits the loader's SCIF state (shims/src/scif.c header).
set -euo pipefail
leg="${1:?usage: capture_serial.sh <leg-name> [device] [baud]}"
repo="$(cd "$(dirname "$0")/.." && pwd)"
dev="${2:-$(ls /dev/cu.usbserial* 2>/dev/null | head -1)}"
baud="${3:-115200}"
[ -n "$dev" ] || { echo "no /dev/cu.usbserial* found -- cable plugged in?" >&2; exit 1; }
log="$repo/captures/$leg.log"
mkdir -p "$(dirname "$log")"
[ -e "$log" ] && { echo "refusing to overwrite existing $log" >&2; exit 1; }
if lsof "$dev" >/dev/null 2>&1; then
    echo "port busy -- close whatever holds it (screen?). Holder:" >&2
    lsof "$dev" >&2; exit 1
fi
# macOS resets termios when the LAST fd on the device closes, so a bare
# `stty -f` (open-set-close) is silently undone before the capture opens the
# port -- that reverts to the 9600 driver default and logs baud garbage
# (hw-round3 lesson). Hold fd 3 open across the stty AND the read.
exec 3< "$dev"
stty -f "$dev" raw "$baud" cs8 -parenb -cstopb clocal
echo "capturing $dev @ $baud -> $log  (ctrl-C to stop)"
exec tee "$log" <&3

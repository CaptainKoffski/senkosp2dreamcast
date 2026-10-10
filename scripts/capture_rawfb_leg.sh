#!/bin/bash
# Bounded unattended Flycast-fork leg with periodic RAWFB (scan-out framebuffer)
# dumps -- the loader-era screens (splash, pre-game menu) that FLYCAST_SHOT
# never sees (docs/kb/tooling.md §RAWFB). Wraps capture_dc_leg.sh; kills by
# PID (operator-leg protocol), SIGINT first so the fork's buffered stdout
# flushes, SIGKILL as the backstop.
#   capture_rawfb_leg.sh <leg-name> [seconds=160] [every=4] [disc=build/disc.gdi] [first=every]
# first: seconds before the FIRST USR2 -- a poke before the fork installs its
# handler kills Flycast (default action); a 296 MB CDI loads slower than the GDI.
# Dumps land next to the log as shot-<leg>-NNN-t<T>s.png.
set -u
leg="${1:?usage: capture_rawfb_leg.sh <leg-name> [seconds] [every] [gdi]}"
dur="${2:-160}"; every="${3:-4}"; first="${5:-$every}"
repo="$(cd "$(dirname "$0")/.." && pwd)"
gdi="${4:-$repo/build/disc.gdi}"
shots="$repo/captures/$(dirname "$leg")"; mkdir -p "$shots"
base="$(basename "$leg")"
raw="$shots/rawfb-$base.png"
cd "$repo" || exit 1
if pgrep -x Flycast >/dev/null; then echo "another Flycast is running; abort" >&2; exit 2; fi
# pvr.rend=0: a leftover Vulkan renderer setting segfaults this bundle (tooling.md §RAWFB).
FLYCAST_SHOT_RAWFB="$raw" scripts/capture_dc_leg.sh "$leg" "$gdi" \
    -config Debug:SerialConsoleEnabled=yes -config config:pvr.rend=0 &
FPID=$!    # capture_dc_leg.sh execs Flycast, so this IS Flycast
echo "flycast pid=$FPID"
t=0; n=0
while [ "$t" -lt "$dur" ] && kill -0 "$FPID" 2>/dev/null; do
  if [ "$n" -eq 0 ]; then sleep "$first"; t=$((t+first)); else sleep "$every"; t=$((t+every)); fi
  kill -USR2 "$FPID" 2>/dev/null; sleep 1; t=$((t+1))
  n=$((n+1))
  [ -f "$raw" ] && cp "$raw" "$shots/shot-$base-$(printf %03d "$n")-t${t}s.png"
done
kill -INT "$FPID" 2>/dev/null; sleep 5
kill -9 "$FPID" 2>/dev/null; wait "$FPID" 2>/dev/null
echo "leg done t=${t}s shots=$n"

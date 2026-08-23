#!/bin/bash
set -euo pipefail
leg="${1:?usage: capture_dc_leg.sh <leg-name> [gdi-path]}"
repo="$(cd "$(dirname "$0")/.." && pwd)"
bin="$repo/../cleopatra/tools/flycast-src/build/Flycast.app/Contents/MacOS/Flycast"
gdi="${2:-$repo/build/disc.gdi}"
log="$repo/captures/$leg.log"
mkdir -p "$(dirname "$log")"
[ -e "$log" ] && { echo "refusing to overwrite existing $log" >&2; exit 1; }
defaults write com.flyinghead.Flycast ApplePersistenceIgnoreState -bool YES
pkill -9 -f "flycast-src.*Flycast" 2>/dev/null || true
sleep 1
FLYCAST_CARTLOG="$log" exec "$bin" -config config:rend.vsync=no "${@:3}" "$gdi" \
    > "${log%.log}.stdout.log" 2>&1

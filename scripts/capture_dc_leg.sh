#!/bin/bash
set -euo pipefail
leg="${1:?usage: capture_dc_leg.sh <leg-name> [gdi-path]}"
repo="$(cd "$(dirname "$0")/.." && pwd)"
bin="$repo/../flycast4naomi2dreamcast/build/Flycast.app/Contents/MacOS/Flycast"
gdi="${2:-$repo/build/disc.gdi}"
log="$repo/captures/$leg.log"
mkdir -p "$(dirname "$log")"
[ -e "$log" ] && { echo "refusing to overwrite existing $log" >&2; exit 1; }
defaults write com.flyinghead.Flycast ApplePersistenceIgnoreState -bool YES
# exec: caller's $! is Flycast's PID -- kill that, never by name (other projects run Flycast too)
FLYCAST_CARTLOG="$log" exec "$bin" -config config:rend.vsync=no "${@:3}" "$gdi" \
    > "${log%.log}.stdout.log" 2>&1

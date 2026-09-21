#!/bin/bash
# Phase 2 capture-leg launcher: one leg = one instrumented run -> captures/<leg>.log
# Launch gotchas per docs/kb/tooling.md §"Instrumented Flycast".
set -euo pipefail
leg="${1:?usage: capture_leg.sh <leg-name> [rom-path]}"
repo="$(cd "$(dirname "$0")/.." && pwd)"
bin="$repo/../flycast4naomi2dreamcast/build/Flycast.app/Contents/MacOS/Flycast"
rom="${2:-$repo/roms/senkosp.zip}"
log="$repo/captures/$leg.log"
mkdir -p "$(dirname "$log")"
# ponytail: legs are primary data — never clobber; rename/delete a bad leg by hand
[ -e "$log" ] && { echo "refusing to overwrite existing $log" >&2; exit 1; }
defaults write com.flyinghead.Flycast ApplePersistenceIgnoreState -bool YES
pkill -9 -f "flycast4naomi2dreamcast.*Flycast" 2>/dev/null || true
sleep 1
# senkosp entry arms the BIOSEXEC watch; an exported override wins (canary use)
FLYCAST_ENTRYPC="${FLYCAST_ENTRYPC:-8c021000}" FLYCAST_CARTLOG="$log" \
    exec "$bin" -config config:rend.vsync=no "$rom"

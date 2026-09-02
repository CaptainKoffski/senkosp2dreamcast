#!/bin/sh
# VMU-canary test — ported from ../cleopatra/scripts/test_vmu_untouched.sh
# (design: ../cleopatra/docs/superpowers/specs/2026-07-26-vmu-safety-design.md;
# this port's wiring recorded in docs/kb/tooling.md §VMU canary).
#
#   attract [secs]  -- unattended: boot + attract, auto-quit after secs
#                      (default 150 -- senkosp's BIOS anim + NOW LOADING
#                      stream is slower than Cleopatra's 90 s window).
#   play            -- headed: tester plays as long as they like, quits Flycast;
#                      the longer/wider the session, the more paths observed.
#
# Oracle (Flycast source, ../cleopatra/tools/flycast-src -- the same build we run):
#   - VMU flash writes hit the backing vmu_save_*.bin immediately
#     (core/hw/maple/maple_devs.cpp:679-707, MDCF_BlockWrite -> fwrite).
#   - Startup rewrites a VMU file ONLY if missing or all-zero (auto-format,
#     maple_devs.cpp:436-474). So: 0xA5 canaries must stay byte-identical,
#     and the all-zero control file MUST change -- proving the VMUPath
#     redirect, VMU attachment, and hash logic are wired (control test).
# The user's real VMU saves are never touched: everything runs in a temp dir
# via transient CLI config (-config goes through setTransient(), never saved
# back -- cfg/cl.cpp:163; the graceful quit does rewrite emu.cfg's normal
# bookkeeping (recents/window state), same as any manual Flycast session).
set -eu

MODE="${1:-attract}"
SECS="${2:-150}"
case "$MODE" in attract|play) ;; *) echo "usage: $0 [attract|play] [secs]" >&2; exit 2 ;; esac

REPO="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$REPO/../cleopatra/tools/flycast-src/build/Flycast.app/Contents/MacOS/Flycast"
DISC="$REPO/build/disc.gdi"
[ -x "$BIN" ]  || { echo "ERROR: Flycast not built (sibling repo): $BIN" >&2; exit 1; }
[ -f "$DISC" ] || { echo "ERROR: disc not built (make disc): $DISC" >&2; exit 1; }

# Launch gotchas: stale instance wedges SH4 vmem; macOS relaunch modal blocks
# boot forever (docs/kb/tooling.md).
pkill -9 -f "flycast-src.*Flycast" 2>/dev/null || true
defaults write com.flyinghead.Flycast ApplePersistenceIgnoreState -bool YES 2>/dev/null || true
defaults write com.flyinghead.Flycast NSQuitAlwaysKeepsWindows -bool false 2>/dev/null || true

VMUDIR="$(mktemp -d /tmp/vmu-canary.XXXXXX)"    # no spaces: unquoted in $CFG below
head -c 131072 /dev/zero | tr '\0' '\245' > "$VMUDIR/canary.ref"   # 128 KB of 0xA5
for f in vmu_save_A1.bin vmu_save_A2.bin vmu_save_B2.bin; do
    cp "$VMUDIR/canary.ref" "$VMUDIR/$f"
done
head -c 131072 /dev/zero > "$VMUDIR/vmu_save_B1.bin"   # control: MUST get auto-formatted
REF_SUM="$(shasum -a 256 "$VMUDIR/canary.ref" | cut -d' ' -f1)"
ZERO_SUM="$(shasum -a 256 "$VMUDIR/vmu_save_B1.bin" | cut -d' ' -f1)"

# Transient config (cfg keys: flycast core/cfg/option.cpp:145,201-215,234,238):
# VMU dir redirect, no per-game VMU, no MapleLink physical VMU, vsync off
# (unfocused-window deadlock), controller+VMUs pinned on ports A and B.
CFG="-config config:Dreamcast.VMUPath=$VMUDIR -config config:PerGameVmu=no \
 -config config:UsePhysicalVmuMemory=no -config config:rend.vsync=no \
 -config input:device1=0 -config input:device1.1=1 -config input:device1.2=1 \
 -config input:device2=0 -config input:device2.1=1 -config input:device2.2=1"

echo "Mode: $MODE  VMU dir: $VMUDIR"
if [ "$MODE" = play ]; then
    echo "Play as long as you like; quit Flycast when done."
    "$BIN" $CFG "$DISC" || true
else
    "$BIN" $CFG "$DISC" &
    PID=$!
    echo "Attract run ${SECS}s (PID $PID)..."
    sleep "$SECS"
    # Graceful quit, NOT kill -9: VMU fwrites are stdio-buffered and only
    # guaranteed on-disk after clean fclose (maple_devs.cpp fullSave/BlockWrite
    # have no fflush) -- a SIGKILL could hide a small write = false PASS.
    osascript -e 'quit app "Flycast"' 2>/dev/null || true
    n=0
    while kill -0 "$PID" 2>/dev/null && [ "$n" -lt 20 ]; do sleep 1; n=$((n+1)); done
    if kill -0 "$PID" 2>/dev/null; then
        echo "WARN: graceful quit failed; SIGKILL (a buffered VMU write could be lost)"
        kill -9 "$PID" 2>/dev/null || true
    fi
    wait "$PID" 2>/dev/null || true
fi

FAIL=0
for f in vmu_save_A1.bin vmu_save_A2.bin vmu_save_B2.bin; do
    SUM="$(shasum -a 256 "$VMUDIR/$f" | cut -d' ' -f1)"
    if [ "$SUM" = "$REF_SUM" ]; then
        echo "OK   $f unchanged"
    else
        echo "FAIL $f WAS WRITTEN"
        FAIL=1
    fi
done
B1_SUM="$(shasum -a 256 "$VMUDIR/vmu_save_B1.bin" | cut -d' ' -f1)"
if [ "$B1_SUM" != "$ZERO_SUM" ]; then
    echo "OK   control B1 auto-formatted (harness wired)"
else
    echo "FAIL control B1 unchanged: VMUPath redirect NOT wired -- run proves nothing"
    FAIL=1
fi
if [ "$FAIL" = 0 ]; then
    echo "PASS: no VMU writes"
    rm -rf "$VMUDIR"
else
    echo "FAIL: kept $VMUDIR for forensics"
fi
exit "$FAIL"

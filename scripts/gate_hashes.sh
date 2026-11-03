#!/bin/sh
# Kit-extraction gate: sha256 listing of a build-artifact set, or a diff of it
# against docs/kb/kit-gate-baseline.txt.
#   gate_hashes.sh <gd|cd|cdi>          print "<sha256>  <path>" lines, sorted by path
#   gate_hashes.sh check <gd|cd|cdi>    diff live listing vs baseline section; silent + 0 if equal
# Run from the port root. Missing artifact: message on stderr, exit 1.
BASELINE=${BASELINE:-docs/kb/kit-gate-baseline.txt}

list() {
	case "$1" in
	gd) files="shims/build/shim.bin shims/build/shim.map shims/build/mie_blobs.c build/patch_table.h build/1ST_READ.BIN build/track01.iso build/track02.raw build/track03.iso build/track04.iso build/disc.gdi" ;;
	cd) files="shims/build/shim.bin build/1ST_READ.BIN" ;;
	cdi) files="build/cdi/disc.cdi" ;;
	*) echo "usage: $0 [check] <gd|cd|cdi>" >&2; exit 2 ;;
	esac
	for f in $files; do
		[ -f "$f" ] || { echo "gate_hashes: missing artifact: $f" >&2; exit 1; }
	done
	shasum -a 256 $files | sort -k2
}

if [ "$1" = check ]; then
	set=$2
	live=$(list "$set") || exit 1
	want=$(awk -v s="== $set" '/^== /{on=($0==s);next} on && !/^#/' "$BASELINE")
	[ -n "$want" ] || { echo "gate_hashes: no '== $set' section in $BASELINE" >&2; exit 1; }
	t=$(mktemp -d) || exit 1
	trap 'rm -rf "$t"' EXIT
	echo "$want" > "$t/want"
	echo "$live" > "$t/live"
	diff -u "$t/want" "$t/live"
else
	list "$1"
fi

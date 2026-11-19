#!/bin/sh
# Build a self-contained zip for the desktop: code at HEAD + Poly Haven asset cache.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CACHE="${CINESCENE_CACHE:-$HOME/.cache/cinescene}"
OUT="${1:-$HOME/Desktop/cinescene_desktop_pack.zip}"
TMP="$(mktemp -d)"
git -C "$ROOT" archive --format=tar --prefix=cinescene/ HEAD | tar -x -C "$TMP"
mkdir -p "$TMP/cinescene/asset_cache"
cp -R "$CACHE/polyhaven" "$TMP/cinescene/asset_cache/"
find "$TMP/cinescene/asset_cache" -name "*.part" -delete
rm -f "$OUT"
(cd "$TMP" && zip -qr "$OUT" cinescene)
rm -rf "$TMP"
echo "pack: $OUT ($(du -h "$OUT" | cut -f1))"

#!/bin/bash
# Rebuild BtbN's pinned win64 GPL 8.1 FFmpeg release without DVD support, so
# libdvdcss, libdvdread and libdvdnav are not linked. Every other dependency
# comes from the same pinned dependency image. Requires Linux with Docker; the
# GitHub workflow .github/workflows/ffmpeg-nodvd.yml runs this script.
set -euo pipefail

RECIPES_REPO="https://github.com/BtbN/FFmpeg-Builds.git"
RECIPES_COMMIT="63ac3265b0789ea16c7b1f8351cd2ad195a28722"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="${1:?usage: build-nodvd.sh <new work directory>}"

if [[ -e "$WORK/recipes" ]]; then
    echo "Use a new work directory: $WORK/recipes already exists."
    exit 1
fi
mkdir -p "$WORK"
git init -q "$WORK/recipes"
git -C "$WORK/recipes" fetch -q --depth 1 "$RECIPES_REPO" "$RECIPES_COMMIT"
git -C "$WORK/recipes" checkout -q --detach FETCH_HEAD
test "$(git -C "$WORK/recipes" rev-parse HEAD)" = "$RECIPES_COMMIT"
git -C "$WORK/recipes" apply "$HERE/btbn-nodvd.patch"

cd "$WORK/recipes"
./build.sh win64 gpl 8.1
ls -l artifacts

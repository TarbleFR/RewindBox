#!/bin/sh
# Compile against the patched S2Arm tree, then exercise on-disk state in new processes.
set -eu
engine=${1:?patched S2Arm checkout required}
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
xcrun --sdk macosx clang -std=gnu11 -O1 -fobjc-arc -fblocks \
    -mmacosx-version-min=13.0 -Werror=implicit-function-declaration \
    -I"$engine/graphics/nvn/gfx/nvn" -I"$engine/graphics/nvn/tests" -I"$engine/runtime/include" \
    "$here/test_metal_archive.m" -framework Foundation -framework Metal -o "$work/archive-test"
if "$work/archive-test" --probe; then
    sh "$engine/graphics/nvn/tests/t_rb_archive_relaunch.sh" "$work/archive-test"
    mkdir "$work/resume" "$work/close"
    "$work/archive-test" --held "$work/resume" resume
    "$work/archive-test" --held "$work/close" close
else
    rc=$?
    if [ "$rc" -ne 77 ]; then exit "$rc"; fi
    echo 'SKIP Metal archive execution: MTLCreateSystemDefaultDevice returned nil (standalone host compiled)'
fi

#!/bin/sh
# Compile against the patched S2Arm tree, then exercise on-disk state in new processes.
set -eu
engine=${1:?patched S2Arm checkout required}
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
build_host() {
    xcrun --sdk macosx clang -std=gnu11 -O1 -fobjc-arc -fblocks \
        -mmacosx-version-min=13.0 -Werror=implicit-function-declaration "$@" \
        -I"$engine/graphics/nvn/gfx/nvn" -I"$engine/graphics/nvn/tests" -I"$engine/runtime/include" \
        "$here/test_metal_archive.m" -framework Foundation -framework Metal
}
build_host -o "$work/archive-test"
if "$work/archive-test" --probe; then
    before="$work/before"
    patch="$here/../patches/0127-guest-synchronize-thermal-admission-and-pause-archive-batches.patch"
    python3 "$here/prepare_archive_793_control.py" "$engine" "$patch" "$before"
    build_host -DRB_ARCHIVE_TEST_793_CONTROL -I"$before/graphics/nvn/gfx/nvn" -o "$work/archive-793"
    mkdir "$work/game-793"
    old_rc=0
    "$work/archive-793" --mid-batch "$work/game-793" hold || old_rc=$?
    if [ "$old_rc" -ne 86 ]; then
        echo "IPA 793 negative control did not reproduce the excess admissions (status $old_rc)" >&2
        exit 1
    fi
    sh "$engine/graphics/nvn/tests/t_rb_archive_relaunch.sh" "$work/archive-test"
    result=0
    for mode in resume close shared retry fail expire-retry; do
        mkdir "$work/$mode"
        "$work/archive-test" --held "$work/$mode" "$mode" write || result=1
        # A miss in one process stays a failure even if the other probe succeeds.
        "$work/archive-test" --held "$work/$mode" "$mode" replay || result=1
    done
    for tier in hold one expire; do
        mkdir "$work/$tier"
        "$work/archive-test" --mid-batch "$work/$tier" "$tier" || result=1
    done
    exit "$result"
else
    rc=$?
    if [ "$rc" -ne 77 ]; then exit "$rc"; fi
    echo 'Metal archive checks require a working Mac GPU (MTLCreateSystemDefaultDevice returned nil)' >&2
    exit 77
fi

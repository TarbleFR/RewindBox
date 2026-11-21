#!/bin/sh
# Exercise the Mac producer with the iPhoneOS Metal compiler, then map its iOS
# slices on macOS through the same C reader as the device.
set -eu
engine=$1
builder=$(dirname "$0")/../../build_nvn2_shader_pack.py
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
key=0011223344556677
title=0100000000000001
build=11223344556677889900aabbccddeeff
chain=$(awk '/^#define DMSH_CHAIN / {gsub(/"/, "", $3); print $3}' "$engine/graphics/nvn/gfx/nvn/dmsh_chain.h")
mkdir "$work/shaders"
cat > "$work/shaders/${key}_b.msl" <<'METAL'
#include <metal_stdlib>
using namespace metal;
kernel void main0(device uint *out [[buffer(0)]], uint i [[thread_position_in_grid]]) { out[i] = i; }
METAL
printf '{"key":"%s_b","chain":"%s","xfp":"0123456789abcdef","stage":"cs","entry":"main0"}\n' "$key" "$chain" > "$work/shaders/${key}_b.json"
printf 'C\t%s_b\n' "$key" > "$work/pso_user.tsv"
python3 -B "$builder" "$work/shaders" --history "$work/pso_user.tsv" --title-id "$title" --build-id "$build" \
    --engine-source "$engine" --out "$work/export"
direct="$work/export/pack/shaders/direct"
grep -Fx "$(printf 'C\t%s_b' "$key")" "$direct/pso_manifest.tsv"
grep -Fx "$(printf 'capture\t0\tcompute\t%s' "$key")" "$direct/shader_map.tsv"
cmp "$work/shaders/${key}_b.msl" "$direct/b-$chain/${key}_b.metal"
cat > "$work/check.c" <<'C'
#include <stdio.h>
#include <stdint.h>
#include <dispatch/dispatch.h>
#define LP_LOG(...) ((void)0)
#define LP_HI_RANGE(lo, hi) (-1)
#include "lib_pack.inc"
#include "rb_capture_identity.h"

int main(int argc, char **argv) {
    lp_pack pack;
    if (argc != 5 || lp_open(&pack, argv[1], argv[2]) != 1 || pack.n != 2 || pack.nshard != 1)
        return 1;
    if (!rb_capture_index_matches(pack.idx, argv[4]) || rb_capture_index_matches(pack.idx, NULL) ||
        rb_capture_index_matches(pack.idx, "different title/build/translator")) return 5;
    uint8_t legacy[48] = {0};
    if (!rb_capture_index_matches(legacy, NULL) || rb_capture_index_matches(legacy, argv[4])) return 6;
    dispatch_data_t lib = lp_get(&pack, argv[3], LP_K_B);
    dispatch_data_t json = lp_get(&pack, argv[3], LP_K_BJSON);
    if (!lib || !json) return 2;
    const void *bytes;
    size_t size;
    dispatch_data_t map = dispatch_data_create_map(lib, &bytes, &size);
    if (!map || size < 4 || memcmp(bytes, "MTLB", 4)) return 3;
    dispatch_data_t reflection = dispatch_data_create_map(json, &bytes, &size);
    if (!reflection || !memmem(bytes, size, "\"entry\":\"main0\"", 15)) return 4;
    puts("Loaded iPhoneOS metallib and reflection from S2ALIB using the engine reader");
    return 0;
}
C
xcrun --sdk macosx clang -std=gnu11 -D_DARWIN_C_SOURCE -fblocks -I"$engine/graphics/nvn" -I"$engine/graphics/nvn/gfx/nvn" "$work/check.c" -o "$work/check"
stamp=$(sed -n 's/^# //p' "$direct/shader_map.tsv")
"$work/check" "$direct/b-$chain" "$chain" "$key" "$stamp"

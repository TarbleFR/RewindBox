#!/bin/bash
# Builds S2ArmPrepare.xcframework (iOS arm64, static): native/s2arm/prepare with
# S2Arm's rewriter, Capstone and LZ4 inside, only the rb_s2arm_* symbols visible.
# Usage: build_prepare_xcframework.sh <s2arm checkout> <rewriter deps dir> <output dir>
# The S2Arm checkout and the dependencies are fetched at the pins of
# tools/s2arm_prototype/pin.json by the caller; nothing of them is stored here.
set -euo pipefail
s2arm=$1; deps=$2; out=$3
here=$(cd "$(dirname "$0")/../.." && pwd)
minimum=17.4
sdk=$(xcrun --sdk iphoneos --show-sdk-path)
rm -rf "$out"; mkdir -p "$out/objects" "$out/headers"

cmake -S "$s2arm/runtime/rewriter" -B "$out/rewriter" -DS2A_REWRITER_DEPS="$deps" -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_SYSTEM_NAME=iOS -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_OSX_DEPLOYMENT_TARGET=$minimum \
  -DCMAKE_OSX_SYSROOT=iphoneos -DCMAKE_SYSTEM_PROCESSOR=arm64 -DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY
cmake --build "$out/rewriter" --target s2a_rewriter --parallel 4
rewriter_lib=$(find "$out/rewriter" -name 'libs2a_rewriter.a' -print -quit)
# In this build Capstone is an object library: its objects are archived inside
# libs2a_rewriter.a itself (run 42943537788: 139 duplicate symbols when added again),
# and there is no separate libcapstone.a (run 42942912304).
echo "rewriter: $rewriter_lib"
test -n "$rewriter_lib"
xcrun nm -g "$rewriter_lib" 2> /dev/null | grep -q ' T _cs_open$' || { echo "Capstone is not inside the rewriter library" >&2; exit 1; }

sources=("$here"/native/s2arm/prepare/s2arm_*.c)
objects=()
for source in "${sources[@]}"; do
  case $source in *_cli.c) continue ;; esac
  object="$out/objects/$(basename "${source%.c}").o"
  xcrun --sdk iphoneos clang -arch arm64 -miphoneos-version-min=$minimum -isysroot "$sdk" -O2 -Wall -Wextra -Werror \
    -I "$here/native/s2arm/prepare" -I "$s2arm/runtime/rewriter" -I "$deps/lz4-4.4.5/lz4libs" -c "$source" -o "$object"
  objects+=("$object")
done

# One relocatable object in which everything but rb_s2arm_* is local, so that Capstone
# and LZ4 cannot collide with copies in other engines of the app.
xcrun --sdk iphoneos clang -arch arm64 -miphoneos-version-min=$minimum -isysroot "$sdk" -r -nostdlib \
  -Wl,-exported_symbol,'_rb_s2arm_*' -Wl,-force_load,"$rewriter_lib" \
  "${objects[@]}" -o "$out/objects/S2ArmPrepare.o"
xcrun libtool -static -o "$out/libS2ArmPrepare.a" "$out/objects/S2ArmPrepare.o"

cp "$here"/native/s2arm/prepare/s2arm_prepare.h "$out/headers/"
[ ! -f "$here/native/s2arm/prepare/s2arm_addr_need.h" ] || cp "$here/native/s2arm/prepare/s2arm_addr_need.h" "$out/headers/"
xcodebuild -create-xcframework -library "$out/libS2ArmPrepare.a" -headers "$out/headers" -output "$out/S2ArmPrepare.xcframework"

# Checks: architecture, platform, visible symbols, nothing undefined beyond the system.
lipo -info "$out/libS2ArmPrepare.a"
xcrun vtool -show-build "$out/objects/S2ArmPrepare.o" | grep -E 'platform|minos' || true
visible=$(xcrun nm -gU "$out/libS2ArmPrepare.a" | awk 'NF == 3 { print $3 }' | sort)
echo "visible symbols:"; echo "$visible"
test -n "$visible"
if echo "$visible" | grep -v '^_rb_s2arm_'; then echo "unexpected visible symbols" >&2; exit 1; fi
echo "$visible" | grep -qx '_rb_s2arm_prepare_rewrite'
echo "undefined symbols:"; xcrun nm -u "$out/libS2ArmPrepare.a" | awk 'NF { print $NF }' | sort -u | tee "$out/undefined.txt"
(cd "$out" && zip -qry S2ArmPrepare.xcframework.zip S2ArmPrepare.xcframework && shasum -a 256 S2ArmPrepare.xcframework.zip libS2ArmPrepare.a | tee sha256.txt)

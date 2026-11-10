#!/usr/bin/env bash
# Builds XeniaCore.framework from the pinned XeniOS checkout.
# Usage: build_core.sh <xenios-checkout> <iphoneos-libmetalirconverter.dylib>
# Expects: Xcode with the iOS 27 SDK selected, the Metal toolchain, CMake,
# Ninja, Python with meson/mako/pyyaml/packaging, the checkout's submodules
# (DirectXShaderCompiler excluded) and `./xenia-build.py slang msc fetchdata`
# already run in it — the steps of XeniOS's own apple-publish.yml.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE="$(cd "${1:?Expected the XeniOS checkout}" && pwd)"
MSC="${2:?Expected the iPhoneOS libmetalirconverter.dylib}"
BUILD="$ROOT/build/xenia-core"
DIST="$ROOT/dist/xenia"
REVISION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["revision"])' "$ROOT/build-utils/xenia/source.json")"
mkdir -p "$BUILD" "$DIST"

# The converter: structure, exports and one of the two pinned digests, then
# Apple's own signature (the mirror) or an ad-hoc/third-party one (refused).
python3 "$ROOT/build-utils/xenia/validate_shader_converter.py" "$MSC" --require-pinned-digest \
  | tee "$BUILD/shader-converter.json"
codesign --verify --strict "$MSC"
codesign -dv --verbose=2 "$MSC" 2>&1 | tee "$BUILD/shader-converter-signature.txt" \
  | grep -q "Authority=Apple" || { echo "libmetalirconverter.dylib is not signed by Apple"; exit 1; }

python3 "$ROOT/build-utils/xenia/prepare_source.py" "$SOURCE"

# Host shader compiler of this revision (the iOS configure runs it).
cmake -S "$SOURCE" -B "$BUILD/host" -G Ninja -DCMAKE_BUILD_TYPE=Release 2>&1 | tee "$BUILD/host-configure.log"
cmake --build "$BUILD/host" --target xenia-shader-cc 2>&1 | tee "$BUILD/host-build.log"
SHADER_CC="$(find "$BUILD/host" -type f -name xenia-shader-cc -perm -u+x -print -quit)"
[ -n "$SHADER_CC" ] || { echo "xenia-shader-cc was not built"; exit 1; }

PREFIX_MAP="-ffile-prefix-map=$ROOT=/rewindbox -ffile-prefix-map=$SOURCE=/xenios -ffile-prefix-map=$BUILD=/build"
cmake -S "$SOURCE" -B "$BUILD/ios" -G "Ninja Multi-Config" \
  -DCMAKE_SYSTEM_NAME=iOS \
  -DCMAKE_OSX_SYSROOT=iphoneos \
  -DCMAKE_OSX_ARCHITECTURES=arm64 \
  -DCMAKE_OSX_DEPLOYMENT_TARGET=26.0 \
  -DCMAKE_CONFIGURATION_TYPES=Release \
  -DCMAKE_C_FLAGS="$PREFIX_MAP" -DCMAKE_CXX_FLAGS="$PREFIX_MAP" \
  -DCMAKE_OBJC_FLAGS="$PREFIX_MAP" -DCMAKE_OBJCXX_FLAGS="$PREFIX_MAP" \
  -DXENIA_BUILD_IOS_TRACE_APP=OFF \
  -DXENIA_IOS_CRASH_REPORTER=OFF \
  -DXENIA_IOS_COMPATIBILITY_DATA_DIR="$SOURCE/build/data_repos/game-compatibility" \
  -DXENIA_IOS_HOST_SHADER_COMPILER="$SHADER_CC" \
  -DXENIA_IOS_SHADER_CONVERTER_LIBRARY="$MSC" \
  -DNEO_XENIA_ADAPTER_DIR="$ROOT/packages/xenia_internal_bridge" \
  -DNEO_XENIA_SOURCE_REVISION="$REVISION" \
  2>&1 | tee "$BUILD/configure.log"
cmake --build "$BUILD/ios" --config Release --target XeniaCore 2>&1 | tee "$BUILD/compile.log"
python3 "$ROOT/build-utils/xenia/verify_core.py" "$BUILD/ios" "$DIST"

#!/bin/bash
# Run after S2Arm's two Mac GPU host binaries and the IPA 793 stage fixture were built.
set -euo pipefail
root=$(cd "$1" && pwd)
dsh_stats=$2
tests=$(cd "$(dirname "$0")" && pwd)
case_dir=$(mktemp -d "${TMPDIR:-/tmp}/rb-native-stage.XXXXXXXX")
cd "$root"
# The negative controls compile and link the archived 793 guest sources and headers.
# The only shared build output is the unchanged, managed host Widen dependency.
red="$case_dir/793"
trap 'rm -rf "$case_dir"' EXIT
mkdir -p "$red"
git -C "$root" archive --format=tar HEAD | tar -xf - -C "$red"
for patch in "$tests"/../patches/*.patch; do
  number=$(basename "$patch")
  (( 10#${number:0:4} <= 126 )) || break
  git -C "$red" apply --whitespace=nowarn "$patch"
done
# Keep the archived fixture before installing the current live-input controls.
cp "$red/graphics/nvn/tests/t_dsh_stats.c" "$case_dir/stats-126.c"
# Copy the test program (including its known paravirtual-device adapter);
# engine compilation still includes headers and links libnvn.a strictly from 793.
cp graphics/nvn/tests/{t_dsh_stats.c,t_nvn_shader_flight.m} "$red/graphics/nvn/tests/"
xcrun --sdk macosx clang -x objective-c -std=gnu11 -fblocks -pthread -framework Foundation \
  "$red/graphics/nvn/tests/t_dsh_stats.c" -o "$case_dir/dsh-793"
mkdir -p "$red/build/tests/nvn"
ln -s "$root/build/tests/nvn/widen" "$red/build/tests/nvn/widen"
make -s -C "$red" -j4 -f Makefile -f "$tests/host-tests.mk" NVN_TEST_PREBUILT=1 \
  build/tests/t_nvn_shader_flight
expect_status() {
  local expected=$1 actual=0
  shift
  "$@" || actual=$?
  if [[ $actual != "$expected" ]]; then echo "Expected exit $expected, got $actual" >&2; exit 1; fi
}
make -s -C graphics/dsx -j4 "$root/build/dsx/libdsx.dylib"
dotnet publish graphics/tools/direct/dsh/S2A.Dsh.csproj -c Release -r osx-arm64 \
  --artifacts-path "$case_dir/aot" -o "$case_dir/translator" -p:PublishAot=true -p:NativeLib=Shared \
  -p:InvariantGlobalization=true -p:UseSharedCompilation=false -nodeReuse:false
translator="$case_dir/translator/S2A.Dsh.dylib"
test -s "$translator" && test -s "$root/build/dsx/libdsx.dylib"
cp "$root/build/dsx/libdsx.dylib" "$case_dir/translator/"
export DYLD_LIBRARY_PATH="$case_dir/translator${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
build/tests/t_nvn_warmbump --reference-padded "$translator"
export S2A_GAME_DATA="$case_dir/game"
data="$case_dir/fallback"
mkdir -p "$data/empty-bundle" "$S2A_GAME_DATA/shaders/direct"
key=$(python3 - "$data" "$S2A_GAME_DATA/shaders/direct" <<'PY'
import hashlib
import importlib.util
import sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("ampere", "tests/ampere_isa/cases.py")
ampere = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ampere)
code, ctl = ampere.shader([ampere.MOVI(i, v) for i, v in enumerate([42,7,99,1])])
key = hashlib.sha256(ctl[:0x48] + code).hexdigest()[:16]
data = Path(sys.argv[1])
(data / "fixture.ctl").write_bytes(ctl)
(data / "fixture.code").write_bytes(code)
facts = Path(sys.argv[2])
(facts / "shader_facts.tsv").write_text(key + '\t{"fout":{"0":"uint"}}\n')
(facts / "shader_pairs.tsv").write_text("")
print(key)
PY
)
test -n "$key"
msl="$data/${key}_b.metal"
mkdir "$case_dir/red-cache"
cp "$data/fixture.ctl" "$data/fixture.code" "$case_dir/red-cache/"
expect_status 71 "$case_dir/dsh-793" --rb-native-input cold "$case_dir/red-cache" "$key" "$translator"
"$dsh_stats" --rb-native-input cold "$data" "$key" "$translator"
cp "$msl" "$data/expected.metal"
rm "$msl" "$data/fixture.code" "$data/fixture.ctl"
"$dsh_stats" --rb-native-input restore "$data" "$key" "$translator"
cmp "$msl" "$data/expected.metal"

# Keep the original bytes through the opening brace of the genuine fragment
# entry point. Ending inside that definition is a deterministic syntax error.
python3 - "$data/expected.metal" "$data/truncated.metal" <<'PYTHON'
import re
import sys
from pathlib import Path
source = Path(sys.argv[1]).read_bytes()
entry = re.search(rb"(?m)^[ \t]*(?:\[\[[^\n]*?\]\][ \t]*)*fragment\b[^;{}]*?\bmain0\s*\([^;{}]*\)[^;{}]*\{", source)
if entry is None or entry.end() >= len(source):
    raise SystemExit("missing main0 fragment definition in the published translation")
Path(sys.argv[2]).write_bytes(source[:entry.end()])
PYTHON
cp "$data/truncated.metal" "$msl"
expect_status 72 "$red/build/tests/t_nvn_shader_flight" --rb-native-msl repair "$data" "$key" "$translator"
build/tests/t_nvn_shader_flight --rb-native-msl repair "$data" "$key" "$translator"
cmp "$msl" "$data/expected.metal"
xcrun --sdk macosx clang -O1 -fobjc-arc -Igraphics/nvn/gfx/nvn -o "$case_dir/fragment" \
  tests/ampere_isa/frag_run.m graphics/nvn/gfx/nvn/nvn_tex.c -framework Metal -framework Foundation
pixel=$("$case_dir/fragment" "$msl")
test "$pixel" = '0000002a 00000007 00000063 00000001' || { echo "Unexpected native fragment output $pixel" >&2; exit 1; }
echo "PASS exact RGBA32Uint from repaired production NVN2 fragment $pixel"
# Reuse this published translator, shader host and Metal renderer.
xcrun --sdk macosx clang -O2 -dynamiclib "$tests/../../../../native/s2arm/prepare/s2arm_zstd.c" -o "$case_dir/prepare-zstd.dylib"
# Build each historical stage preparer forward from the verified 793 tree.
# Later changes to the production scanner cannot affect either negative control.
build_stage_control() {
  local last=$1 output=$2 tree="$case_dir/stage-$1" patch name number
  mkdir -p "$tree/graphics" "$tree/runtime"
  cp -R "$red/graphics/nvn" "$tree/graphics/"
  cp -R "$red/runtime/include" "$tree/runtime/"
  cp "$case_dir/stats-126.c" "$tree/graphics/nvn/tests/t_dsh_stats.c"
  for patch in "$tests"/../patches/*.patch; do
    name=$(basename "$patch"); number=$((10#${name:0:4}))
    (( number > 126 )) || continue
    (( number <= last )) || break
    git -C "$tree" apply --whitespace=nowarn --include='graphics/nvn/host/*' --include='graphics/nvn/gfx/nvn/*' \
      --include='graphics/nvn/tests/t_dsh_stats.c' --include='runtime/include/*' "$patch"
  done
  # The pre-priority engine uses its real eight-argument preparer. Give its
  # fixture the same cancellation callback added in 0134, with the host untouched.
  if (( last == 133 )); then
    git -C "$tree" apply --include='graphics/nvn/tests/t_dsh_stats.c' "$tests"/../patches/0134-*.patch
  fi
  xcrun --sdk macosx clang -x objective-c -std=gnu11 -fblocks -pthread -framework Foundation \
    "$tree/graphics/nvn/tests/t_dsh_stats.c" -o "$output"
}
build_stage_control 139 "$case_dir/dsh-795-no-aliases"
build_stage_control 133 "$case_dir/dsh-before-priority"
python3 "$tests/test_local_stage_recovery.py" "$root" "$dsh_stats" "$translator" "$case_dir/prepare-zstd.dylib" "$case_dir/fragment" "$case_dir/dsh-before-priority" "$case_dir/dsh-795-no-aliases"
rm "$data/${key}_b.in"
cp "$data/truncated.metal" "$msl"
# A valid path with repeated separators must address the very same refusal record.
build/tests/t_nvn_shader_flight --rb-native-msl unrecoverable "$case_dir//fallback/" "$key" "$translator"

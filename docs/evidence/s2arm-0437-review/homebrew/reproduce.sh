#!/usr/bin/env bash
# Linux x86_64. Dependencies are supplied by the caller, no installation.
set -euo pipefail
if [ "$#" != 4 ]; then
    echo "Usage: $0 ENGINE_TREE EMPTY_OUTPUT UAM COLOR_FSH_GLSL" >&2
    exit 2
fi
scripts=$(cd "$(dirname "$0")" && pwd)
engine=$(cd "$1" && pwd)
mkdir "$2"
work=$(cd "$2" && pwd)
uam=$(realpath "$3")
glsl=$(realpath "$4")
: "${VK_DRIVER_FILES:=/usr/share/vulkan/icd.d/lvp_icd.json}"
export VK_DRIVER_FILES PYTHONDONTWRITEBYTECODE=1 LP_NUM_THREADS=1
mkdir "$work/objects" "$work/bin"
python3 - "$engine" "$work/model" <<'PYTHON'
from pathlib import Path
from shutil import copytree, ignore_patterns
import sys
src, dst = map(Path, sys.argv[1:])
for rel in ["tests/shader_cases", *["compat/tree/src/" + name for name in
            ("Ryujinx.Graphics.Shader", "Ryujinx.Common", "Spv.Generator")]]:
    copytree(src/rel, dst/rel, ignore=ignore_patterns("bin","obj","__pycache__"))
PYTHON
dotnet build "$work/model/tests/shader_cases/ShaderCases.csproj" -c Release --nologo \
   --configfile "$work/model/tests/shader_cases/NuGet.Config" -o "$work/dll"
src="$engine/graphics/third_party/spirv_cross"
for unit in spirv_cross spirv_cfg spirv_parser spirv_cross_parsed_ir spirv_glsl spirv_msl spirv_hlsl spirv_cpp spirv_reflect spirv_cross_util main; do
    "${CXX:-clang++}" -std=c++14 -O0 -DHAVE_SPIRV_CROSS_GIT_VERSION -I"$src" -I"$engine/translator/spvc_cli" \
        -c "$src/$unit.cpp" -o "$work/objects/$unit.o"
done
"${CXX:-clang++}" "$work"/objects/*.o -o "$work/bin/spirv-cross"
export PATH="$work/bin:$PATH"
spirv-cross --revision
inc=()
if [ -n "${VULKAN_HEADERS:-}" ]; then inc=(--include "$VULKAN_HEADERS"); fi
python3 "$scripts/build_runners.py" "$engine" "$work" "${inc[@]}"
python3 "$scripts/replay.py" "$engine" "$work/initial" --translator "$work/dll/ShaderCases.dll" \
    --runner "$work/vulkan-runner" --surface-runner "$work/vulkan-surface-runner" --glsl "$glsl" --uam "$uam"
python3 "$scripts/repeat.py" "$engine" "$work" "$work/initial" "$glsl" "$work/five"
cmp "$work/initial/report.json" "$work/five/run-5/report.json"

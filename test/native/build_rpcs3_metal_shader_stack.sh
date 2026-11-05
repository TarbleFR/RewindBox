#!/usr/bin/env bash
# REWINDBOX_METAL_NATIVE (M2): build and run the host test of the native Metal renderer's shader stack.
#
#   build_rpcs3_metal_shader_stack.sh <materialized RPCS3 source> <work dir> <MSL output dir>
#
# Fetches glslang, yaml-cpp and asmjit at the commits the RPCS3 source pins (its submodule gitlinks are not
# materialized), builds glslang and yaml-cpp with the options RPCS3 uses, compiles the Metal shader sources
# and the RPCS3 sources they need, links them with test/native/rpcs3_metal_host_stubs.cpp and runs
# test/native/rpcs3_metal_shader_stack_test.cpp, which writes one .metal file per translated program.
set -euo pipefail

SOURCE=$(cd "$1" && pwd)
WORK=$(mkdir -p "$2" && cd "$2" && pwd)
MSL_OUT=$(mkdir -p "$3" && cd "$3" && pwd)
HERE=$(cd "$(dirname "$0")" && pwd)
CXX=${CXX:-clang++}
CC=${CC:-clang}
JOBS=${JOBS:-4}

pinned_commit() {
	# The gitlink commit of a submodule path, read from the upstream commit recorded by the canonical source.
	python3 - "$SOURCE" "$1" <<'PY'
import json, subprocess, sys
source, path = sys.argv[1], sys.argv[2]
out = subprocess.run(['git', '-C', source, 'ls-tree', 'HEAD', path], check=True, capture_output=True, text=True).stdout.split()
assert len(out) >= 3 and out[1] == 'commit', f'no gitlink for {path}: {out}'
print(out[2])
PY
}

fetch() { # <dir> <url> <commit>
	if [ ! -d "$WORK/$1/.git" ]; then
		git init -q "$WORK/$1"
		git -C "$WORK/$1" remote add origin "$2"
	fi
	git -C "$WORK/$1" fetch -q --depth 1 origin "$3"
	git -C "$WORK/$1" checkout -q --detach FETCH_HEAD
	echo "$1 $(git -C "$WORK/$1" rev-parse HEAD)"
}

fetch glslang https://github.com/KhronosGroup/glslang.git "$(pinned_commit 3rdparty/glslang/glslang)"
fetch yaml-cpp https://github.com/RPCS3/yaml-cpp.git "$(pinned_commit 3rdparty/yaml-cpp/yaml-cpp)"
fetch asmjit https://github.com/asmjit/asmjit.git "$(pinned_commit 3rdparty/asmjit/asmjit)"

# glslang with RPCS3's options (3rdparty/glslang/CMakeLists.txt).
cmake -S "$WORK/glslang" -B "$WORK/glslang-build" -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER="$CC" -DCMAKE_CXX_COMPILER="$CXX" \
	-DENABLE_PCH=OFF -DBUILD_EXTERNAL=OFF -DSKIP_GLSLANG_INSTALL=ON -DENABLE_SPVREMAPPER=OFF -DENABLE_GLSLANG_BINARIES=OFF \
	-DENABLE_HLSL=OFF -DENABLE_OPT=OFF -DENABLE_CTEST=OFF -DGLSLANG_TESTS=OFF > "$WORK/glslang-cmake.log" 2>&1
cmake --build "$WORK/glslang-build" -j "$JOBS" > "$WORK/glslang-build.log" 2>&1 || { tail -40 "$WORK/glslang-build.log"; exit 1; }
cmake -S "$WORK/yaml-cpp" -B "$WORK/yaml-build" -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER="$CXX" \
	-DYAML_CPP_BUILD_TESTS=OFF -DYAML_CPP_BUILD_TOOLS=OFF -DYAML_CPP_BUILD_CONTRIB=OFF > "$WORK/yaml-cmake.log" 2>&1
cmake --build "$WORK/yaml-build" -j "$JOBS" > "$WORK/yaml-build.log" 2>&1 || { tail -40 "$WORK/yaml-build.log"; exit 1; }

ARCH_FLAGS=()
case "$(uname -m)" in
	x86_64) ARCH_FLAGS=(-march=native) ;;
	arm64|aarch64) [ "$(uname -s)" = Darwin ] && ARCH_FLAGS=(-march=armv8.4-a) ;;
esac

FLAGS=(-std=gnu++20 -O1 -g -Wall -Wno-unused-parameter -Wno-missing-braces "${ARCH_FLAGS[@]}"
	-I "$SOURCE/rpcs3" -I "$SOURCE" -I "$SOURCE/rpcs3/Emu" -I "$SOURCE/3rdparty" -I "$SOURCE/3rdparty/rewindbox-spirv-cross"
	-I "$WORK/glslang" -I "$WORK/yaml-cpp/include" -I "$WORK/asmjit/src"
	-DSPIRV_CROSS_NAMESPACE_OVERRIDE=rbx_spirv_cross -DSPIRV_CROSS_SPV_HEADER_NAMESPACE_OVERRIDE=rbx_spv)

R="$SOURCE/rpcs3"
UNITS=(
	"$HERE/rpcs3_metal_shader_stack_test.cpp"
	"$HERE/rpcs3_metal_host_stubs.cpp"
	"$R/Emu/RSX/Metal/MTLCommonDecompiler.cpp"
	"$R/Emu/RSX/Metal/MTLVertexProgram.cpp"
	"$R/Emu/RSX/Metal/MTLFragmentProgram.cpp"
	"$R/Emu/RSX/Metal/MTLShaderTranslator.cpp"
	"$R/Emu/RSX/Program/VertexProgramDecompiler.cpp"
	"$R/Emu/RSX/Program/FragmentProgramDecompiler.cpp"
	"$R/Emu/RSX/Program/GLSLCommon.cpp"
	"$R/Emu/RSX/Program/SPIRVCommon.cpp"
	"$R/Emu/RSX/Program/program_util.cpp"
	"$R/Emu/RSX/Program/Assembler/FPToCFG.cpp"
	"$R/Emu/RSX/Program/Assembler/FPOpcodes.cpp"
	"$R/Emu/RSX/Program/Assembler/Passes/FP/RegisterAnnotationPass.cpp"
	"$R/Emu/RSX/Program/Assembler/Passes/FP/RegisterDependencyPass.cpp"
	"$R/Emu/system_config.cpp"
	"$R/Emu/system_config_types.cpp"
	"$R/util/yaml.cpp"
	"$SOURCE/Utilities/StrFmt.cpp"
	"$SOURCE/Utilities/Config.cpp"
	"$SOURCE/3rdparty/rewindbox-spirv-cross/spirv_cfg.cpp"
	"$SOURCE/3rdparty/rewindbox-spirv-cross/spirv_cross.cpp"
	"$SOURCE/3rdparty/rewindbox-spirv-cross/spirv_cross_parsed_ir.cpp"
	"$SOURCE/3rdparty/rewindbox-spirv-cross/spirv_glsl.cpp"
	"$SOURCE/3rdparty/rewindbox-spirv-cross/spirv_msl.cpp"
	"$SOURCE/3rdparty/rewindbox-spirv-cross/spirv_parser.cpp"
)

mkdir -p "$WORK/obj"
printf '%s\n' "${FLAGS[@]}" > "$WORK/flags.txt"
compile_unit() { # <unit> -> object path on stdout
	local unit="$1"
	local obj="$WORK/obj/$(echo "${unit#"$SOURCE"/}" | sed 's#[/.]#_#g').o"
	local flags=()
	while IFS= read -r flag; do flags+=("$flag"); done < "$WORK/flags.txt"
	if ! "$CXX" "${flags[@]}" -c "$unit" -o "$obj" > "$obj.log" 2>&1; then
		echo "compile failed: $unit" >&2
		cat "$obj.log" >&2
		return 1
	fi
}
export -f compile_unit
export WORK SOURCE CXX
printf '%s\n' "${UNITS[@]}" | xargs -P "$JOBS" -I{} bash -c 'compile_unit "$1"' _ {}
OBJECTS=()
for unit in "${UNITS[@]}"; do
	OBJECTS+=("$WORK/obj/$(echo "${unit#"$SOURCE"/}" | sed 's#[/.]#_#g').o")
done

G="$WORK/glslang-build"
GLSLANG_LIBS=()
for lib in SPIRV/libSPIRV.a glslang/libglslang.a glslang/libMachineIndependent.a glslang/libGenericCodeGen.a \
	glslang/OSDependent/Unix/libOSDependent.a glslang/libglslang-default-resource-limits.a; do
	[ -f "$G/$lib" ] && GLSLANG_LIBS+=("$G/$lib")
done

"$CXX" "${OBJECTS[@]}" "${GLSLANG_LIBS[@]}" "${GLSLANG_LIBS[@]}" "$WORK/yaml-build/libyaml-cpp.a" -lpthread -o "$WORK/metal_shader_stack_test"
"$WORK/metal_shader_stack_test" "$MSL_OUT"

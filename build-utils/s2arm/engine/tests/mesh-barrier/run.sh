#!/usr/bin/env bash
# Run in the reconstructed engine checkout on macOS.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
proof="${1:?proof output directory}"
mkdir -p "$proof"
proof=$(cd "$proof" && pwd)
dotnet build graphics/tools/direct/tests/dsh_cmp/dsh_cmp.csproj -c Release --nologo
export DSH_CMP_DLL="$PWD/graphics/tools/direct/tests/dsh_cmp/bin/Release/net10.0/dsh_cmp.dll"
export DOTNET="$(command -v dotnet)"
python3 "$here/mesh_sources.py" "$PWD" "$proof" | tee "$proof/sources.jsonl"
for mode in 0 1; do
  for shader in "$proof/$mode"/*.metal; do
    xcrun -sdk iphoneos metal -c -mios-version-min=18.0 -fmetal-math-mode=relaxed -fpreserve-invariance "$shader" -o "${shader%.metal}.ios.air"
    xcrun -sdk iphoneos metal -O2 -mios-version-min=18.0 -fmetal-math-mode=relaxed -fpreserve-invariance -c -emit-llvm -S "$shader" -o "${shader%.metal}.ios.ll"
    xcrun -sdk macosx metal -fpreserve-invariance "$shader" -o "${shader%.metal}.metallib"
  done
done
python3 - "$proof" <<'PYTHON'
from pathlib import Path
import re, sys
for ll in sorted(Path(sys.argv[1]).glob('*/*.ios.ll')):
    calls = [l.strip() for l in ll.read_text().splitlines()
             if re.search(r'\bcall\b.*@[^ (]*barrier', l, re.I)]
    print(f'{ll.parent.name}/{ll.name} barrier_calls={len(calls)}')
    ll.with_suffix('.barriers.txt').write_text('\n'.join(calls) + '\n')
PYTHON
make -C graphics/nvn mac
make -j4 -f Makefile -f "$GITHUB_WORKSPACE/build-utils/s2arm/engine/tests/host-tests.mk" -f "$here/mesh_raster.mk" build/tests/rb_mesh_raster
for mode in 0 1; do
  status=0
  build/tests/rb_mesh_raster "$proof/$mode" | tee "$proof/$mode/raster.txt" || status=$?
  if [[ $status == 77 ]]; then echo "Mesh drawing unsupported on this GPU" | tee "$proof/gpu-status.txt"; exit 77; fi
  if [[ $status != 0 ]]; then exit "$status"; fi
done

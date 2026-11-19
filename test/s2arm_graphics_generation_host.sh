#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
classes="$root/packages/s2arm_engine_bridge/ios/Classes"
job=$(mktemp -d)
trap 'rm -rf "$job"' EXIT
xcrun --sdk macosx clang -fobjc-arc -fblocks -Wall -Werror -framework Foundation \
  -I "$classes" "$classes/S2ArmGraphicsGeneration.m" "$root/test/s2arm_graphics_generation_host.m" \
  -o "$job/host"
"$job/host"

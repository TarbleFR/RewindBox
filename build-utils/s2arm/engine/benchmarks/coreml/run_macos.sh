#!/bin/bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT_DIR="${1:-${TMPDIR:-/tmp}/rewindbox-reconstruction-bench}"
mkdir -p "$OUTPUT_DIR"
MAC_SDK="$(xcrun --sdk macosx --show-sdk-path)"
ARCH="$(uname -m)"
xcrun swiftc -O -swift-version 5 -parse-as-library -target "$ARCH-apple-macos14.4" \
  -sdk "$MAC_SDK" -framework Foundation -framework Metal -framework CoreVideo \
  -framework CoreML -framework QuartzCore \
  "$ROOT_DIR/ReconstructionBench.swift" "$ROOT_DIR/Main.swift" \
  -o "$OUTPUT_DIR/ReconstructionBench"
# Verify the same implementation and the optional app compile for physical iOS.
IOS_SDK="$(xcrun --sdk iphoneos --show-sdk-path)"
xcrun swiftc -swift-version 5 -parse-as-library -typecheck \
  -target arm64-apple-ios17.4 -sdk "$IOS_SDK" \
  "$ROOT_DIR/ReconstructionBench.swift" "$ROOT_DIR/IOSApp.swift" \
  > "$OUTPUT_DIR/ios-typecheck.log" 2>&1
"$OUTPUT_DIR/ReconstructionBench" \
  --model "$ROOT_DIR/model/ReconstructionProbe.mlpackage" \
  --output "$OUTPUT_DIR/results-320x180.json" --iterations 90 --warmup 10
"$OUTPUT_DIR/ReconstructionBench" \
  --model "$ROOT_DIR/model/ReconstructionProbe960x540.mlpackage" \
  --output "$OUTPUT_DIR/results-960x540.json" --iterations 30 --warmup 5

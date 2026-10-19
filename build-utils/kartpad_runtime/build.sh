#!/usr/bin/env bash
# Build the KartPad 0.8.3 runtime from its public sources, without game code.
#
#   build.sh fetch     WORK   clone the pinned sources and dependencies
#   build.sh discio    WORK   build Dolphin's DiscIO for iphoneos (disc import)
#   build.sh pristine  WORK   upstream's own publishable-app build, unmodified
#   build.sh embedded  WORK   the same runtime as NeoStation's KartPadCore
#
# Inputs are only public source code, the Dawn and SDL prebuilt/pinned
# packages and the official game-free KartPad IPA used as a comparison
# reference. No disc image, extracted game file, Retro Rewind file or
# translated game code is read or produced at any step.
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
PINS="$ROOT/build-utils/kartpad_runtime/source.json"
command="${1:-}"
WORK="${2:-}"
[[ -n "$command" && -n "$WORK" ]] || { echo "usage: $0 fetch|discio|pristine|embedded WORK" >&2; exit 64; }
mkdir -p "$WORK"
WORK="$(CDPATH= cd -- "$WORK" && pwd)"
KP="$WORK/kp"
DISCIO_KEY="033d03b1a65200dd"
DISCIO_SOURCE="$KP/build/builder-dependencies/discio-iphoneos-${DISCIO_KEY}-source"
DISCIO_BUILD="$KP/build/builder-dependencies/discio-iphoneos-${DISCIO_KEY}-build"

pin() {
  python3 -c 'import json,sys
value=json.load(open(sys.argv[1]))
for key in sys.argv[2].split("."):
    value=value[key]
print(value)' "$PINS" "$1"
}

fetch_commit() {  # repository directory commit
  local repository="$1" directory="$2" commit="$3"
  rm -rf "$directory"
  mkdir -p "$directory"
  git -C "$directory" init -q
  git -C "$directory" remote add origin "$repository"
  git -C "$directory" fetch -q --depth 1 origin "$commit"
  git -C "$directory" checkout -q --detach FETCH_HEAD
  [[ "$(git -C "$directory" rev-parse HEAD)" == "$commit" ]] || {
    echo "ERROR: $repository is not at $commit" >&2; exit 65; }
}

download() {  # url destination sha256
  local url="$1" destination="$2" sha="$3"
  if [[ ! -f "$destination" ]]; then
    mkdir -p "$(dirname "$destination")"
    curl -fL --retry 4 --retry-delay 3 -o "$destination.part" "$url"
    mv "$destination.part" "$destination"
  fi
  echo "$sha  $destination" | shasum -a 256 -c -
}

case "$command" in
  fetch)
    fetch_commit "$(pin kartpad.repository)" "$KP" "$(pin kartpad.commit)"
    python3 - "$PINS" "$KP" <<'PY'
import json, subprocess, sys
pins = json.load(open(sys.argv[1]))["kartpad"]["submodules"]
staged = subprocess.check_output(["git", "-C", sys.argv[2], "ls-files", "--stage", *pins]).decode().split("\n")
found = {line.split("\t")[1]: line.split()[1] for line in staged if line}
assert found == pins, (found, pins)
print("KartPad gitlinks match the pins:", ", ".join(sorted(pins)))
PY
    git -C "$KP" submodule update --init --depth 1 --jobs 5
    git -C "$KP" submodule status
    fetch_commit "$(pin sunpad.repository)" "$KP/ref/sunpad" "$(pin sunpad.commit)"
    DOLPHIN="$KP/ref/upstream/dolphin"
    fetch_commit "$(pin dolphin_discio.repository)" "$DOLPHIN" "$(pin dolphin_discio.commit)"
    for skipped in $(python3 -c 'import json,sys; print(" ".join(json.load(open(sys.argv[1]))["dolphin_discio"]["skipped_submodules"]))' "$PINS"); do
      git -C "$DOLPHIN" config "submodule.$skipped.update" none
    done
    git -C "$DOLPHIN" submodule update --init --depth 1 --jobs 8
    [[ -z "$(git -C "$DOLPHIN" status --porcelain)" ]] || { echo "ERROR: Dolphin checkout is not clean" >&2; exit 65; }
    download "$(pin dawn.url)" "$KP/build/dependency-cache/$(pin dawn.archive_name)" "$(pin dawn.sha256)"
    download "$(pin official_game_free_ipa.url)" "$WORK/reference/KartPad-official-game-free.ipa" \
      "$(pin official_game_free_ipa.sha256)"
    # The official reference must itself be game-free before it is used.
    python3 "$ROOT/build-utils/game_content_gate.py" "$WORK/reference/KartPad-official-game-free.ipa"
    ;;
  discio)
    command -v ninja >/dev/null && command -v rg >/dev/null || brew install ninja ripgrep
    if [[ -f "$DISCIO_BUILD/Source/Core/DiscIO/libdiscio.a" && -f "$DISCIO_SOURCE/Source/Core/DiscIO/DiscExtractor.h" ]]; then
      echo "Reusing the cached DiscIO build for key $DISCIO_KEY"
    else
      rm -rf "$DISCIO_SOURCE" "$DISCIO_BUILD"
      (cd "$KP" && scripts/build-ios-discio-probe.sh ref/upstream/dolphin "$DISCIO_SOURCE" "$DISCIO_BUILD" iphoneos)
    fi
    ;;
  pristine)
    command -v ninja >/dev/null && command -v rg >/dev/null || brew install ninja ripgrep
    rm -rf "$WORK/pristine"
    (cd "$KP" && KARTPAD_DISCIO_SOURCE_DIR="$DISCIO_SOURCE" KARTPAD_DISCIO_BUILD_DIR="$DISCIO_BUILD" \
      scripts/build-ios-app.sh "$WORK/pristine")
    ipa="$(find "$WORK/pristine" -name 'KartPad-v*-ios-unsigned.ipa' | head -n 1)"
    [[ -f "$ipa" ]] || { echo "ERROR: the pristine build produced no IPA" >&2; exit 65; }
    python3 "$ROOT/build-utils/kartpad_runtime/check_runtime.py" pristine \
      --built "$ipa" --official "$WORK/reference/KartPad-official-game-free.ipa" \
      --report "$WORK/pristine-identity.json"
    ;;
  embedded)
    echo "ERROR: the embedded stage is defined by build-utils/kartpad_runtime/embedded.sh" >&2
    exit 64
    ;;
  *)
    echo "usage: $0 fetch|discio|pristine|embedded WORK" >&2
    exit 64
    ;;
esac

# Sourced by build_core.sh. Explicit opt-in; a missing optional tool builds cold.
# Only C/C++ compiler invocations are cached; the two build trees and links are fresh.
XENIA_CMAKE_CACHE_ARGS=()
if [ "${XENIA_CCACHE:-0}" = 1 ] && command -v ccache >/dev/null 2>&1; then
  export CCACHE_COMPILERCHECK=content
  export CCACHE_SLOPPINESS=''
  export CCACHE_BASEDIR="$ROOT"
  export CCACHE_DIR="${CCACHE_DIR:-${RUNNER_TEMP:-$ROOT/build}/xenia-ccache}"
  mkdir -p "$CCACHE_DIR"
  XENIA_CMAKE_CACHE_ARGS=("-DCMAKE_C_COMPILER_LAUNCHER=$(command -v ccache)" "-DCMAKE_CXX_COMPILER_LAUNCHER=$(command -v ccache)")
  ccache --zero-stats || true
  xenia_cache_started=$SECONDS
  xenia_cache_report() {
    local status=$?
    echo "Xenia compile elapsed seconds: $((SECONDS - xenia_cache_started)); status: $status"
    ccache --show-stats || true
    return "$status"
  }
  trap xenia_cache_report EXIT
else
  echo 'Xenia C/C++ cache unavailable or disabled; compiling cold.'
fi

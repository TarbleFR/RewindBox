#!/usr/bin/env bash
# Syntax-checks the C++ parts of RewindBox's XeniOS facade
# (packages/xenia_internal_bridge/core/XeniaCoreInput.h) against the pinned
# upstream headers, with the upstream warning policy (-Werror).
# Usage: test/xenia_core_cpp_test.sh <xenios-checkout with third_party/{tomlplusplus,fmt,cxxopts}>
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE="$(cd "${1:?Expected the XeniOS checkout}" && pwd)"
# CXX may be a command with arguments (the workflow passes "xcrun clang++").
read -r -a CXX_COMMAND <<< "${CXX:-clang++}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cat > "$TMP/check.cc" <<'CC'
#include "XeniaCoreInput.h"
using namespace xe;  // the X_ERROR_* macros expand to X_RESULT.
int main() {
  xe::hid::X_INPUT_STATE state{};
  xe::hid::X_INPUT_CAPABILITIES caps{};
  neo_xenia::NeoXeniaInputDriver driver(nullptr, 0);
  neo_xenia::g_buttons.store(xe::hid::X_INPUT_GAMEPAD_A);
  // The InputSystem binds slot 0 only to an enumerated, auto-bound device.
  const auto devices = driver.EnumerateDevices();
  const bool bound = devices.size() == 1 && devices[0].driver_slot == 0 &&
                     devices[0].preferred_slot == 0 && devices[0].auto_bind &&
                     !devices[0].stable_id.empty();
  const bool ok = bound && driver.GetState(0, &state) == X_ERROR_SUCCESS &&
                  driver.GetCapabilities(0, 0, &caps) == X_ERROR_SUCCESS &&
                  driver.GetState(1, &state) == X_ERROR_DEVICE_NOT_CONNECTED &&
                  neo_xenia::Axis(2.f) == 32767 && neo_xenia::Trigger(-1.f) == 0;
  // Rumble reaches the facade's sink (the pad of player 1 only).
  static uint32_t forwarded = 0;
  neo_xenia::g_vibration_sink = [](uint16_t, uint16_t) { ++forwarded; };
  xe::hid::X_INPUT_VIBRATION vibration{};
  vibration.left_motor_speed = 0x8000;
  const bool rumble = driver.SetState(0, &vibration) == X_ERROR_SUCCESS &&
                      driver.SetState(1, &vibration) == X_ERROR_DEVICE_NOT_CONNECTED;
  return ok && rumble && !neo_xenia::SetCvar("not_a_cvar", "1") ? 0 : 1;
}
CC
"${CXX_COMMAND[@]}" -std=c++20 -fsyntax-only -Werror \
  -I "$ROOT/packages/xenia_internal_bridge/core" -I "$SOURCE/src" -I "$SOURCE" -I "$SOURCE/third_party" \
  "$TMP/check.cc"
echo "xenia core C++ parts: OK"

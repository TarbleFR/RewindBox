// SPDX-License-Identifier: BSD-3-Clause
// C++ parts of RewindBox's XeniOS facade (no Objective-C): the host pad of
// user 0, its Xenia input driver and cvar application. Included by
// XeniaCore.mm; syntax-checked on its own against the pinned upstream
// headers by test/xenia_core_cpp_test.sh.
#pragma once

#include <atomic>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "xenia/base/cvar.h"
#include "xenia/hid/input.h"
#include "xenia/hid/input_driver.h"
#include "xenia/xbox.h"

namespace neo_xenia {

using namespace xe;  // X_STATUS, X_RESULT and their values (xenia/xbox.h).

// Host pad of user 0.
inline std::atomic<uint32_t> g_buttons{0};
inline std::atomic<int16_t> g_lx{0}, g_ly{0}, g_rx{0}, g_ry{0};
inline std::atomic<uint8_t> g_lt{0}, g_rt{0};
inline std::atomic<uint32_t> g_packet{0};


// Applies one cvar the way the engine's own config loader does
// (IConfigVar::LoadConfigValue from a TOML node).
inline bool SetCvar(const std::string& key, const std::string& value) {
  if (!cvar::ConfigVars) return false;
  auto it = cvar::ConfigVars->find(key);
  if (it == cvar::ConfigVars->end()) return false;
  if (value == "true" || value == "false") {
    toml::value<bool> node(value == "true");
    it->second->LoadConfigValue(&node);
    return true;
  }
  char* end = nullptr;
  const long long number = std::strtoll(value.c_str(), &end, 10);
  if (!value.empty() && end && *end == '\0') {
    toml::value<int64_t> node(static_cast<int64_t>(number));
    it->second->LoadConfigValue(&node);
    return true;
  }
  toml::value<std::string> node(value);
  it->second->LoadConfigValue(&node);
  return true;
}


// Input driver of user 0.
class NeoXeniaInputDriver final : public xe::hid::InputDriver {
 public:
  NeoXeniaInputDriver(xe::ui::Window* window, size_t z_order)
      : InputDriver(window, z_order) {}

  X_STATUS Setup() override { return X_STATUS_SUCCESS; }

  X_RESULT GetCapabilities(uint32_t user_index, uint32_t /*flags*/,
                           xe::hid::X_INPUT_CAPABILITIES* out_caps) override {
    if (!out_caps) return X_ERROR_BAD_ARGUMENTS;
    if (user_index != 0) return X_ERROR_DEVICE_NOT_CONNECTED;
    std::memset(out_caps, 0, sizeof(*out_caps));
    out_caps->type = xe::hid::XINPUT_DEVTYPE_GAMEPAD;
    out_caps->sub_type = xe::hid::XINPUT_DEVSUBTYPE_GAMEPAD;
    out_caps->flags = 0;
    out_caps->gamepad.buttons = 0xF3FF;
    out_caps->gamepad.left_trigger = 0xFF;
    out_caps->gamepad.right_trigger = 0xFF;
    out_caps->gamepad.thumb_lx = static_cast<int16_t>(0xFFFFu);
    out_caps->gamepad.thumb_ly = static_cast<int16_t>(0xFFFFu);
    out_caps->gamepad.thumb_rx = static_cast<int16_t>(0xFFFFu);
    out_caps->gamepad.thumb_ry = static_cast<int16_t>(0xFFFFu);
    return X_ERROR_SUCCESS;
  }

  X_RESULT GetState(uint32_t user_index, xe::hid::X_INPUT_STATE* out_state) override {
    if (user_index != 0) return X_ERROR_DEVICE_NOT_CONNECTED;
    if (!out_state) return X_ERROR_BAD_ARGUMENTS;
    out_state->packet_number = g_packet.load(std::memory_order_acquire);
    out_state->gamepad.buttons = static_cast<uint16_t>(g_buttons.load(std::memory_order_relaxed));
    out_state->gamepad.left_trigger = g_lt.load(std::memory_order_relaxed);
    out_state->gamepad.right_trigger = g_rt.load(std::memory_order_relaxed);
    out_state->gamepad.thumb_lx = g_lx.load(std::memory_order_relaxed);
    out_state->gamepad.thumb_ly = g_ly.load(std::memory_order_relaxed);
    out_state->gamepad.thumb_rx = g_rx.load(std::memory_order_relaxed);
    out_state->gamepad.thumb_ry = g_ry.load(std::memory_order_relaxed);
    return X_ERROR_SUCCESS;
  }

  X_RESULT SetState(uint32_t user_index, xe::hid::X_INPUT_VIBRATION* /*vibration*/) override {
    // Rumble is not forwarded yet; the pad stays connected.
    return user_index == 0 ? X_ERROR_SUCCESS : X_ERROR_DEVICE_NOT_CONNECTED;
  }

  X_RESULT GetKeystroke(uint32_t /*user_index*/, uint32_t /*flags*/,
                        xe::hid::X_INPUT_KEYSTROKE* /*out_keystroke*/) override {
    return X_ERROR_EMPTY;
  }

  xe::hid::InputType GetInputType() const override { return xe::hid::InputType::Controller; }

  // XeniOS's InputSystem reaches a driver only through the guest-slot
  // bindings it builds from the devices drivers enumerate (ReconcileBindings,
  // first at InputSystem::Setup). The host pad is one device, bound to slot 0
  // as the XeniOS touch overlay is (touch_input_driver_ios.cc). Without it no
  // touch or controller input reached the title (first booted device run).
  std::vector<xe::hid::InputDeviceInfo> EnumerateDevices() override {
    xe::hid::InputDeviceInfo info = {};
    info.driver_slot = 0;
    info.stable_id = "rewindbox-host-pad";
    info.display_name = "RewindBox";
    info.subtype = xe::hid::XINPUT_DEVSUBTYPE_GAMEPAD;
    info.preferred_slot = 0;
    info.auto_bind = true;
    return {std::move(info)};
  }
};

inline int16_t Axis(float value) {
  const float clamped = value < -1.f ? -1.f : (value > 1.f ? 1.f : value);
  return static_cast<int16_t>(clamped * 32767.f);
}

inline uint8_t Trigger(float value) {
  const float clamped = value < 0.f ? 0.f : (value > 1.f ? 1.f : value);
  return static_cast<uint8_t>(clamped * 255.f);
}


}  // namespace neo_xenia

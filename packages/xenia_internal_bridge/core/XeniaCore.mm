// SPDX-License-Identifier: BSD-3-Clause
// RewindBox facade of the XeniOS Core (docs/xenios-playlist.md § Core
// adaptation plan). Implements NeoXeniaAPI (ios/Classes/XeniaCoreABI.h) over
// XeniOS's own EmulatorAppIOS, driven only through IOSWindowedAppContext's
// public API (LaunchGame, SetEmulationPaused, TerminateCurrentGame and its
// exit/failure callbacks), so XeniOS keeps its pause protocol, stop watchdog
// and ResetTitle teardown. Compiled with ARC (this file only); the upstream
// sources stay manual-retain-release.
//
// Lifetime: one IOSWindowedAppContext, one EmulatorAppIOS (and so one
// xe::Emulator), one XeniaMetalView and one host view controller per
// process, never destroyed: Xenia's cvars, logging, JIT mapping and signal
// handlers are process-wide, and iOSWindow keeps raw pointers to the view
// and its controller. A session is one title between boot() and shutdown().
#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstring>
#include <mutex>
#include <string>
#include <utility>
#include <vector>

#include "XeniaCoreABI.h"
#include "neo_xenia_core_hooks.h"
#include "XeniaCoreInput.h"

#include "xenia/base/cvar.h"
#include "xenia/cpu/backend/jit_memory_ios.h"
#include "xenia/base/logging.h"
#include "xenia/hid/input.h"
#include "xenia/hid/input_driver.h"
#include "xenia/ui/ios/app/windowed_app_context_ios.h"
#import "xenia/ui/ios/game/ios_metal_view.h"
#include "xenia/ui/ios/shared/ios_system_utils.h"
#include "xenia/ui/windowed_app.h"
#include "xenia/xbox.h"

#ifndef NEO_XENIA_SOURCE_REVISION
#error "NEO_XENIA_SOURCE_REVISION is defined by core/target.cmake"
#endif

namespace {

using namespace neo_xenia;
using Reason = xe::ui::IOSWindowedAppContext::EmulationPauseReason;

// Keys RewindBox may set (lib/services/xenia_settings_service.dart and the
// bridge's XeniaManagedKeys); anything else is refused.
const char* const kManagedKeys[] = {
    "framerate_limit", "guest_display_refresh_cap", "present_letterbox",
    "use_50Hz_mode", "async_shader_compilation", "apu_max_queued_frames",
    "xma_decoder", "mount_cache", "user_language", "user_country"};

// Forced for every RewindBox session: the host has no microphone usage
// description, no head-pose entitlement and no XeniOS account services.
const std::pair<const char*, const char*> kEmbeddedPolicy[] = {
    {"voice_chat", "false"},
    {"apu_phase_head_tracking", "false"},
};

std::mutex g_mutex;
xe::ui::IOSWindowedAppContext* g_context = nullptr;
std::unique_ptr<xe::ui::WindowedApp> g_app;
XeniaMetalView* g_view = nil;
UIViewController* g_host_controller = nil;
bool g_initialized = false;
std::string g_storage_root;
std::vector<std::pair<std::string, std::string>> g_overrides;

uint64_t g_transaction = 0;
NeoXeniaEvent g_event = nullptr;
void* g_event_context = nullptr;

// Title state, guarded by g_state_mutex.
std::mutex g_state_mutex;
std::condition_variable g_state_changed;
enum class TitleState { kIdle, kBooting, kRunning, kFailed };
TitleState g_title_state = TitleState::kIdle;
std::string g_failure;

void Copy(char* out, size_t capacity, const std::string& text) {
  if (!out || capacity == 0) return;
  const size_t n = std::min(capacity - 1, text.size());
  std::memcpy(out, text.data(), n);
  out[n] = '\0';
}

void Emit(const char* event, const std::string& message) {
  NeoXeniaEvent callback;
  void* context;
  uint64_t transaction;
  {
    std::lock_guard<std::mutex> lock(g_mutex);
    callback = g_event;
    context = g_event_context;
    transaction = g_transaction;
  }
  if (callback && transaction) callback(context, transaction, event, message.c_str());
}

bool IsManaged(const std::string& key) {
  for (const char* managed : kManagedKeys) {
    if (key == managed) return true;
  }
  return false;
}

void SetTitleState(TitleState state, const std::string& failure = {}) {
  {
    std::lock_guard<std::mutex> lock(g_state_mutex);
    g_title_state = state;
    if (!failure.empty()) g_failure = failure;
  }
  g_state_changed.notify_all();
}

// ---------------------------------------------------------------- ABI calls

void* CreateRenderView(char* error, size_t capacity) {
  if (![NSThread isMainThread]) {
    Copy(error, capacity, "create_render_view must run on the main thread");
    return nullptr;
  }
  if (!g_view) {
    g_view = [[XeniaMetalView alloc] initWithFrame:UIScreen.mainScreen.bounds];
    g_view.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
  }
  return (__bridge void*)g_view;
}

void ReleaseRenderView(void) {
  // The view lives for the process (iOSWindow keeps it); a stopped session
  // only takes it out of the host controller's hierarchy.
  if (g_view) [g_view removeFromSuperview];
}

bool InitializeOnMain(std::string* failure) {
  // dispatch_sync from the caller's queue: main never waits on that queue.
  __block bool ok = false;
  __block std::string reason;
  dispatch_sync(dispatch_get_main_queue(), ^{
    if (!g_host_controller) g_host_controller = [[UIViewController alloc] init];
    g_context = new xe::ui::IOSWindowedAppContext();
    g_context->set_metal_view(g_view);
    g_context->set_view_controller(g_host_controller);
    g_context->set_game_exited_callback([]() {
      SetTitleState(TitleState::kIdle);
      Emit("stopped", "");
    });
    g_context->set_game_launch_failed_callback([](const std::string& why) {
      SetTitleState(TitleState::kFailed, why);
      Emit("error", why);
    });
    g_context->set_game_stop_stuck_callback([]() { Emit("stopStuck", ""); });
    // The steps of XeniaAppDelegate (ui/ios/app/ios_app_delegate.mm:95-268)
    // that the Core needs, without its launcher, JIT hand-off or crash log.
    [g_view layoutIfNeeded];
    g_app = NeoXeniaCreateEmulatorApp(*g_context);
    if (g_app) {
      xe::InitializeLogging(g_app->GetName());
      ok = g_app->OnInitialize();
    }
    if (!ok) reason = "EmulatorAppIOS::OnInitialize failed";
  });
  if (!ok && failure) *failure = reason;
  return ok;
}

int Prepare(const NeoXeniaConfiguration* configuration, uint32_t /*timeout_ms*/, char* error,
            size_t capacity) {
  if (!configuration || configuration->size < sizeof(NeoXeniaConfiguration) ||
      !configuration->storage_root || !configuration->content_root ||
      !configuration->cache_root) {
    Copy(error, capacity, "invalid configuration");
    return 0;
  }
  if (!g_view) {
    Copy(error, capacity, "create_render_view was not called");
    return 0;
  }
  std::vector<std::pair<std::string, std::string>> overrides;
  for (uint32_t index = 0; index < configuration->settings_count; ++index) {
    const NeoXeniaSetting& setting = configuration->settings[index];
    if (!setting.key || !setting.value || !IsManaged(setting.key)) {
      Copy(error, capacity, std::string("unmanaged setting: ") + (setting.key ? setting.key : "?"));
      return 0;
    }
    overrides.emplace_back(setting.key, setting.value);
  }
  {
    std::lock_guard<std::mutex> lock(g_mutex);
    if (g_initialized && g_storage_root != configuration->storage_root) {
      Copy(error, capacity, "storage root changed within the process");
      return 0;
    }
    g_transaction = configuration->transaction;
    g_event = configuration->event;
    g_event_context = configuration->context;
    g_overrides = std::move(overrides);
  }
  if (!g_initialized) {
    if ([NSThread isMainThread]) {
      Copy(error, capacity, "prepare must not run on the main thread");
      return 0;
    }
    // XeniaAppDelegate parses (empty) launch arguments first.
    static char arg0[] = "rewindbox";
    static char* argv[] = {arg0, nullptr};
    int argc = 1;
    char** argv_ptr = argv;
    cvar::ParseLaunchArguments(argc, argv_ptr, "", {});
    // Read by EmulatorAppIOS::OnInitialize before config::SetupConfig.
    SetCvar("storage_root", configuration->storage_root);
    SetCvar("content_root", configuration->content_root);
    SetCvar("cache_root", configuration->cache_root);
    // The engine log goes to its storage root, never to stdout (a debugger
    // console would otherwise render every line).
    SetCvar("log_file", std::string(configuration->storage_root) + "/xenia.log");
    SetCvar("log_to_stdout", "false");
    std::string failure;
    if (!InitializeOnMain(&failure)) {
      Copy(error, capacity, failure);
      return 0;
    }
    std::lock_guard<std::mutex> lock(g_mutex);
    g_storage_root = configuration->storage_root;
    g_initialized = true;
  }
  for (const auto& policy : kEmbeddedPolicy) SetCvar(policy.first, policy.second);
  return 1;
}

uint32_t JitState(void) {
  using xe::cpu::backend::IOSJitMemory;
  uint32_t state = 0;
  if (IOSJitMemory::NeedsAttachedTool()) state |= NEO_XENIA_JIT_NEEDS_TOOL;
  if (IOSJitMemory::ToolAttached()) state |= NEO_XENIA_JIT_TOOL_ATTACHED;
  if (xe_is_cs_debugged()) state |= NEO_XENIA_JIT_CS_DEBUGGED;
  if (IOSJitMemory::PacksCode()) state |= NEO_XENIA_JIT_BROKER_PATH;
  return state;
}

int ValidateJit(char* error, size_t capacity) {
  // Before the one-time prepare, a tool that set CS_DEBUGGED and left would
  // turn the Core's prepare brk into a fatal "JIT was turned off" error.
  const uint32_t state = JitState();
  if ((state & NEO_XENIA_JIT_NEEDS_TOOL) && !(state & NEO_XENIA_JIT_TOOL_ATTACHED)) {
    Copy(error, capacity,
         "JIT unavailable: the JIT helper must stay attached until the first game prepares "
         "its code region (iOS 26 TXM)");
    return 0;
  }
  if (xe_check_jit_available()) return 1;
  Copy(error, capacity,
       xe_ios_requires_debugger_broker()
           ? "JIT unavailable: no attached debugger broker (iOS 26 TXM)"
           : "JIT unavailable: the process is not CS_DEBUGGED");
  return 0;
}

int Boot(const char* absolute_path, uint32_t kind, uint32_t timeout_ms, char* error,
         size_t capacity) {
  if (!g_initialized || !absolute_path || !*absolute_path) {
    Copy(error, capacity, "boot before prepare or without a path");
    return 0;
  }
  if (kind != NEO_XENIA_CONTENT_DISC_IMAGE && kind != NEO_XENIA_CONTENT_ZAR &&
      kind != NEO_XENIA_CONTENT_EXECUTABLE) {
    Copy(error, capacity, "unsupported content kind");
    return 0;
  }
  {
    std::lock_guard<std::mutex> lock(g_state_mutex);
    if (g_title_state == TitleState::kBooting || g_title_state == TitleState::kRunning) {
      Copy(error, capacity, "a title is already running");
      return 0;
    }
    g_title_state = TitleState::kBooting;
    g_failure.clear();
  }
  const std::string path(absolute_path);
  dispatch_async(dispatch_get_main_queue(), ^{
    g_context->LaunchGame(path);
  });
  std::unique_lock<std::mutex> lock(g_state_mutex);
  const bool settled = g_state_changed.wait_for(
      lock, std::chrono::milliseconds(timeout_ms),
      []() { return g_title_state != TitleState::kBooting; });
  if (settled && g_title_state == TitleState::kRunning) return 1;
  const std::string reason =
      !settled ? "boot timed out" : (g_failure.empty() ? "the title exited during boot" : g_failure);
  lock.unlock();
  if (!settled) {
    dispatch_async(dispatch_get_main_queue(), ^{
      g_context->TerminateCurrentGame();
    });
  }
  Copy(error, capacity, reason);
  return 0;
}

void SetPaused(int paused) {
  if (!g_context) return;
  const bool value = paused != 0;
  dispatch_async(dispatch_get_main_queue(), ^{
    g_context->SetEmulationPaused(Reason::kUser, value);
  });
}

void RequestStop(void) {
  if (!g_context) return;
  dispatch_async(dispatch_get_main_queue(), ^{
    g_context->SetEmulationPaused(Reason::kUser, false);
    g_context->TerminateCurrentGame();
  });
}

int Shutdown(uint32_t timeout_ms, char* error, size_t capacity) {
  bool idle;
  {
    std::lock_guard<std::mutex> lock(g_state_mutex);
    idle = g_title_state == TitleState::kIdle || g_title_state == TitleState::kFailed;
  }
  if (!idle) RequestStop();
  std::unique_lock<std::mutex> lock(g_state_mutex);
  const bool stopped = g_state_changed.wait_for(
      lock, std::chrono::milliseconds(timeout_ms), []() {
        return g_title_state == TitleState::kIdle || g_title_state == TitleState::kFailed;
      });
  lock.unlock();
  // No callback of this session after shutdown returns.
  {
    std::lock_guard<std::mutex> guard(g_mutex);
    g_transaction = 0;
    g_event = nullptr;
    g_event_context = nullptr;
  }
  g_buttons.store(0);
  if (!stopped) {
    Copy(error, capacity, "the title did not stop in time");
    return 0;
  }
  return 1;
}

void SetButtons(uint32_t buttons) {
  if (g_buttons.exchange(buttons & 0xFFFFu, std::memory_order_relaxed) != (buttons & 0xFFFFu)) {
    g_packet.fetch_add(1, std::memory_order_release);
  }
}

void SetAxes(float left_x, float left_y, float right_x, float right_y, float left_trigger,
             float right_trigger) {
  g_lx.store(Axis(left_x), std::memory_order_relaxed);
  g_ly.store(Axis(left_y), std::memory_order_relaxed);
  g_rx.store(Axis(right_x), std::memory_order_relaxed);
  g_ry.store(Axis(right_y), std::memory_order_relaxed);
  g_lt.store(Trigger(left_trigger), std::memory_order_relaxed);
  g_rt.store(Trigger(right_trigger), std::memory_order_relaxed);
  g_packet.fetch_add(1, std::memory_order_release);
}

const NeoXeniaAPI kAPI = {
    sizeof(NeoXeniaAPI),
    NEO_XENIA_ABI_VERSION,
    NEO_XENIA_SOURCE_REVISION,
    CreateRenderView,
    ReleaseRenderView,
    Prepare,
    ValidateJit,
    Boot,
    SetPaused,
    RequestStop,
    Shutdown,
    SetButtons,
    SetAxes,
    JitState,
};

}  // namespace

// ---------------------------------------------------------- upstream hooks

void NeoXeniaApplyLaunchOverrides() {
  std::vector<std::pair<std::string, std::string>> overrides;
  {
    std::lock_guard<std::mutex> lock(g_mutex);
    overrides = g_overrides;
  }
  for (const auto& entry : overrides) {
    if (!SetCvar(entry.first, entry.second)) {
      XELOGW("RewindBox: cvar {} is not registered in this Core", entry.first);
    }
  }
  for (const auto& policy : kEmbeddedPolicy) SetCvar(policy.first, policy.second);
  XELOGI("RewindBox: {} launch override(s) applied", overrides.size());
}

void NeoXeniaNotifyTitleLaunched() {
  SetTitleState(TitleState::kRunning);
  Emit("firstFrame", "title launched");
}

std::unique_ptr<xe::hid::InputDriver> NeoXeniaCreateInputDriver(xe::ui::Window* window,
                                                                size_t window_z_order) {
  return std::make_unique<neo_xenia::NeoXeniaInputDriver>(window, window_z_order);
}

extern "C" __attribute__((visibility("default"))) const NeoXeniaAPI* NeoXenia_GetAPI(
    uint32_t version) {
  return version == NEO_XENIA_ABI_VERSION ? &kAPI : nullptr;
}

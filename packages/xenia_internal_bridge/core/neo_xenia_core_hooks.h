// SPDX-License-Identifier: BSD-3-Clause
// Hooks between XeniOS's EmulatorAppIOS (src/xenia/app/xenia_main_ios.mm,
// compiled with XE_NEO_EMBEDDED_CORE=1 through build-utils/xenia/
// rewindbox-core.patch) and RewindBox's facade (core/XeniaCore.mm).
#pragma once

#include <cstddef>
#include <memory>

namespace xe {
namespace hid {
class InputDriver;
}  // namespace hid
namespace ui {
class Window;
class WindowedApp;
class WindowedAppContext;
}  // namespace ui
}  // namespace xe

// Main thread, in EmulatorAppIOS::OnInitialize right after
// config::SetupConfig: sets the host's storage, content and cache roots and log
// path again over the saved config, whose absolute paths name the container
// that wrote it (iOS gives the app a new container on every update).
void NeoXeniaApplyHostRoots();

// Emulator thread, right after config::LoadGameConfigForFile: applies the
// effective RewindBox settings of the title being booted.
void NeoXeniaApplyLaunchOverrides();

// Emulator thread, after Emulator::LaunchPath succeeded.
void NeoXeniaNotifyTitleLaunched();

// GPU command processor thread, once per guest swap
// (MetalCommandProcessor::IssueSwap, a weak reference added by the patch).
extern "C" void NeoXeniaNotifyGuestSwap(void);

// Defined by the patch in jit_memory_ios.cc: hands the host's code-region
// reservation to IOSJitMemory when its own found no room below 8 GB.
// Returns a NEO_XENIA_CODE_REGION_* value (XeniaCoreABI.h).
extern "C" int NeoXeniaAdoptExecuteRegion(void* reservation, size_t size);

// The only input driver of the embedded Core: user 0, fed by the host.
std::unique_ptr<xe::hid::InputDriver> NeoXeniaCreateInputDriver(
    xe::ui::Window* window, size_t window_z_order);

// Defined by the patch in xenia_main_ios.mm (replaces XE_DEFINE_WINDOWED_APP).
std::unique_ptr<xe::ui::WindowedApp> NeoXeniaCreateEmulatorApp(
    xe::ui::WindowedAppContext& app_context);

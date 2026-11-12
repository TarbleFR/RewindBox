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
#include <fcntl.h>
#include <mutex>
#include <string>
#include <time.h>
#include <unistd.h>
#include <utility>
#include <vector>

#include "XeniaCoreABI.h"
#include "neo_xenia_core_hooks.h"
#include "XeniaCoreInput.h"

#include "xenia/base/cvar.h"
#include "xenia/cpu/backend/jit_memory_ios.h"
#include "xenia/base/logging.h"
#include "xenia/base/system_ios.h"
#include "xenia/hid/input.h"
#include "xenia/hid/input_driver.h"
#include "xenia/ui/ios/app/ios_lifecycle_audio_session.h"
#include "xenia/ui/ios/app/windowed_app_context_ios.h"
#import "xenia/ui/ios/game/ios_metal_view.h"
#import "xenia/ui/ios/shared/ios_alert_actions.h"
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
    "xma_decoder", "mount_cache", "user_language", "user_country",
    "widescreen", "internal_display_resolution"};

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

// Guest swaps of the running title (NeoXeniaNotifyGuestSwap), for get_stats.
std::atomic<uint64_t> g_guest_frames{0};

// A code region below 8 GB is held for the one-time JIT prepare (set once by
// adopt_code_region, which the bridge calls right after loading the Core).
std::atomic<bool> g_code_region_held{false};

// Where a FatalError's reason is kept (Documents/XeniOS/Engine), written once
// by the first prepare before the hooks are installed.
std::string g_fatal_record_path;

// The roots the first prepare passed (Documents/XeniOS/Engine and Content,
// Library/Caches/XeniOS), set again after config::SetupConfig
// (NeoXeniaApplyHostRoots). Written once, before OnInitialize.
std::string g_host_storage_root;
std::string g_host_content_root;
std::string g_host_cache_root;

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

NSString* ToNS(const std::string& text) {
  NSString* value = text.empty() ? nil : [NSString stringWithUTF8String:text.c_str()];
  return value ?: @"";
}

// UIKit's own translation of a standard button title (Cancel, OK), so a
// guest prompt follows the device language without an English fallback in
// the Core; the key itself when UIKit has none.
NSString* SystemButtonTitle(NSString* key) {
  return [[NSBundle bundleForClass:UIApplication.class] localizedStringForKey:key
                                                                       value:key
                                                                       table:nil];
}

// The guest's prompts (message boxes, keyboard) are presented on the window
// that shows the render view, i.e. on top of the bridge's session; never on
// the host controller, which is in no window (XeniaPresentGuestPrompt answers
// a prompt it cannot show as cancelled: the title-screen sign-in of the first
// booted run). Main thread.
UIViewController* PromptRoot() {
  UIWindow* window = g_view.window;
  if (!window) {
    for (UIScene* scene in UIApplication.sharedApplication.connectedScenes) {
      if (![scene isKindOfClass:UIWindowScene.class]) continue;
      for (UIWindow* candidate in ((UIWindowScene*)scene).windows) {
        if (candidate.isKeyWindow) {
          window = candidate;
          break;
        }
      }
      if (window) break;
    }
  }
  return window.rootViewController;
}

// IOSWindowedAppContext::PromptMessageBoxUI (windowed_app_context_ios.mm)
// on PromptRoot(): the first Cancel/No/Back of several buttons gets the
// cancel style, the guest's default is the preferred action, and an alert
// that cannot be shown or is dismissed (B on a controller) is cancelled.
bool PromptMessageBox(const std::string& title, const std::string& text,
                      const std::vector<std::string>& buttons, uint32_t default_button,
                      uint32_t* selected_out) {
  NSMutableArray<NSString*>* names = [NSMutableArray array];
  for (const auto& button : buttons) [names addObject:button.empty() ? @"OK" : ToNS(button)];
  if (!names.count) [names addObject:@"OK"];
  const uint32_t preferred = std::min<uint32_t>(default_button, uint32_t(names.count - 1));
  if (selected_out) *selected_out = preferred;
  // The answer cannot be waited for on main; the guest asks from a worker.
  if ([NSThread isMainThread]) return false;
  NSString* titleNS = ToNS(title);
  NSString* textNS = ToNS(text);
  dispatch_semaphore_t done = dispatch_semaphore_create(0);
  __block uint32_t picked = preferred;
  __block BOOL answered = NO;
  dispatch_async(dispatch_get_main_queue(), ^{
    UIAlertController* alert =
        [UIAlertController alertControllerWithTitle:titleNS.length ? titleNS : nil
                                            message:textNS.length ? textNS : nil
                                     preferredStyle:UIAlertControllerStyleAlert];
    BOOL hasCancel = NO;
    for (NSUInteger index = 0; index < names.count; ++index) {
      UIAlertActionStyle style = UIAlertActionStyleDefault;
      if (!hasCancel && names.count > 1) {
        for (NSString* cancel in @[ @"Cancel", @"No", @"Back" ]) {
          if ([names[index] caseInsensitiveCompare:cancel] == NSOrderedSame) {
            style = UIAlertActionStyleCancel;
            hasCancel = YES;
            break;
          }
        }
      }
      UIAlertAction* action = [UIAlertAction actionWithTitle:names[index]
                                                       style:style
                                                     handler:^(UIAlertAction*) {
                                                       picked = uint32_t(index);
                                                       answered = YES;
                                                       dispatch_semaphore_signal(done);
                                                     }];
      [alert addAction:action];
      if (index == preferred) alert.preferredAction = action;
    }
    XeniaAlertSetCancelHandler(alert, ^{
      dispatch_semaphore_signal(done);
    });
    XeniaPresentGuestPrompt(PromptRoot(), alert, ^{
      dispatch_semaphore_signal(done);
    });
  });
  dispatch_semaphore_wait(done, DISPATCH_TIME_FOREVER);
  if (selected_out) *selected_out = picked;
  return answered;
}

// The guest keyboard (XamShowKeyboardUI), as XeniOS's
// presentSystemKeyboardPromptWithTitle (ios_main_view_controller.mm) on
// PromptRoot(): the default text, the guest's length limit, Cancel and OK.
bool PromptKeyboard(const std::string& title, const std::string& description,
                    const std::string& default_text, size_t max_length, std::string* text_out,
                    bool* cancelled_out) {
  if (cancelled_out) *cancelled_out = true;
  if ([NSThread isMainThread]) return false;
  NSString* titleNS = ToNS(title);
  NSString* descriptionNS = ToNS(description);
  NSString* defaultNS = ToNS(default_text);
  dispatch_semaphore_t done = dispatch_semaphore_create(0);
  __block BOOL cancelled = YES;
  __block NSString* typed = @"";
  dispatch_async(dispatch_get_main_queue(), ^{
    UIAlertController* alert =
        [UIAlertController alertControllerWithTitle:titleNS.length ? titleNS : nil
                                            message:descriptionNS.length ? descriptionNS : nil
                                     preferredStyle:UIAlertControllerStyleAlert];
    [alert addTextFieldWithConfigurationHandler:^(UITextField* field) {
      field.text = defaultNS;
      field.autocapitalizationType = UITextAutocapitalizationTypeNone;
      field.autocorrectionType = UITextAutocorrectionTypeNo;
      field.clearButtonMode = UITextFieldViewModeWhileEditing;
      if (max_length) XeniaLimitTextFieldLength(field, max_length);
    }];
    __weak UIAlertController* weakAlert = alert;
    [alert addAction:[UIAlertAction actionWithTitle:SystemButtonTitle(@"Cancel")
                                              style:UIAlertActionStyleCancel
                                            handler:^(UIAlertAction*) {
                                              dispatch_semaphore_signal(done);
                                            }]];
    UIAlertAction* ok = [UIAlertAction actionWithTitle:SystemButtonTitle(@"OK")
                                                 style:UIAlertActionStyleDefault
                                               handler:^(UIAlertAction*) {
                                                 typed = weakAlert.textFields.firstObject.text ?: @"";
                                                 cancelled = NO;
                                                 dispatch_semaphore_signal(done);
                                               }];
    [alert addAction:ok];
    alert.preferredAction = ok;
    XeniaPresentGuestPrompt(PromptRoot(), alert, ^{
      dispatch_semaphore_signal(done);
    });
  });
  dispatch_semaphore_wait(done, DISPATCH_TIME_FOREVER);
  if (text_out) *text_out = std::string(typed.UTF8String ?: "");
  if (cancelled_out) *cancelled_out = cancelled;
  return true;
}

// A title's sign-in (XamShowSigninUI) and the start of every title: RewindBox
// has no profile screen, so a profile is signed in to the asking player's slot
// without a prompt: one already there, else the first profile signed in
// nowhere, else a new one ("RewindBox", then "RewindBox 2"...). XeniOS's
// ProfileManager then keeps it signed in for the next launches
// (logged_profile_slot_N_xuid). Without it the first booted titles stayed on
// their title screen: no profile existed and the sign-in prompt was answered
// as cancelled. Main thread, as XeniOS's own profile picker, or the emulator
// thread before any title runs (NeoXeniaNotifyKernelReady).
bool SignInProfileOnMain(uint32_t user_index) {
  if (!g_context) return false;
  const uint32_t slot = user_index < 4 ? user_index : 0;
  const auto profiles = g_context->ListProfiles();
  for (const auto& profile : profiles) {
    if (profile.signed_in && uint32_t(profile.signed_in_slot) == slot) return true;
  }
  uint64_t xuid = 0;
  for (const auto& profile : profiles) {
    if (!profile.signed_in) {
      xuid = profile.xuid;
      break;
    }
  }
  for (size_t number = 1; !xuid && number <= profiles.size() + 1; ++number) {
    const std::string gamertag =
        number == 1 ? std::string("RewindBox") : "RewindBox " + std::to_string(number);
    bool taken = false;
    for (const auto& profile : profiles) taken = taken || profile.gamertag == gamertag;
    if (taken) continue;
    xuid = g_context->CreateProfile(gamertag);
    if (!xuid) XELOGW("RewindBox: the profile {} could not be created", gamertag);
    break;
  }
  const bool signed_in = xuid && g_context->SignInProfile(xuid, slot);
  XELOGI("RewindBox: profile sign-in for player {}: {}", slot + 1, signed_in ? "done" : "failed");
  return signed_in;
}

bool SignInProfile(uint32_t user_index) {
  if ([NSThread isMainThread]) return SignInProfileOnMain(user_index);
  __block bool signed_in = false;
  dispatch_sync(dispatch_get_main_queue(), ^{
    signed_in = SignInProfileOnMain(user_index);
  });
  return signed_in;
}

// Rumble of player 1 when it changes (NeoXeniaInputDriver::SetState):
// "left,right" motor speeds 0..65535, played by the bridge on the pad.
void ForwardVibration(uint16_t left, uint16_t right) {
  Emit("vibration", std::to_string(left) + "," + std::to_string(right));
}

// What XeniOS's lifecycle observer (ios_lifecycle_observer.mm, app layer, not
// in this Core) adds to the bridge's own pause: a background task until the
// pause has settled (no GPU or JIT work in flight when iOS suspends the app)
// and the audio session's background note and restore (a call or Siri that
// ended without "should resume" left the game silent).
void InstallLifecycleObservers() {
  NSNotificationCenter* center = NSNotificationCenter.defaultCenter;
  [center addObserverForName:UIApplicationDidEnterBackgroundNotification
                      object:nil
                       queue:NSOperationQueue.mainQueue
                  usingBlock:^(NSNotification*) {
                    xe::ui::IOSAudioSessionNoteBackgrounded();
                    if (!g_context) return;
                    UIApplication* application = UIApplication.sharedApplication;
                    __block UIBackgroundTaskIdentifier task = UIBackgroundTaskInvalid;
                    void (^end)(void) = ^{
                      if (task == UIBackgroundTaskInvalid) return;
                      [application endBackgroundTask:task];
                      task = UIBackgroundTaskInvalid;
                    };
                    task = [application beginBackgroundTaskWithName:@"rewindbox.xenia.pause"
                                                  expirationHandler:end];
                    if (task == UIBackgroundTaskInvalid) return;
                    g_context->RunWhenEmulationPauseSettled([end]() {
                      dispatch_async(dispatch_get_main_queue(), end);
                    });
                    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, int64_t(4 * NSEC_PER_SEC)),
                                   dispatch_get_main_queue(), end);
                  }];
  [center addObserverForName:UIApplicationDidBecomeActiveNotification
                      object:nil
                       queue:NSOperationQueue.mainQueue
                  usingBlock:^(NSNotification*) {
                    xe::ui::IOSAudioSessionRestoreIfNeeded("app became active");
                  }];
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

// XeniOS's FatalError ends the process (quick_exit) after its iOS hooks: the
// XeniOS app records the session and shows the reason (ios_crash_reporting.mm).
// RewindBox has neither, so the reason is kept for the host's next start.
void NoteFatalError(std::string_view message) {
  if (g_fatal_record_path.empty()) return;
  std::string text = xe::strip_pii(message);
  if (text.size() > 4096) text.resize(4096);
  text += '\n';
  const int fd = open(g_fatal_record_path.c_str(), O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0600);
  if (fd < 0) return;
  (void)write(fd, text.data(), text.size());
  fsync(fd);
  close(fd);
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
    // The app-layer prompts of XeniaAppDelegate that a title can wait on.
    g_context->set_signin_ui_prompt_callback(
        [](uint32_t user_index, uint32_t /*users_needed*/) { return SignInProfile(user_index); });
    g_context->set_message_box_prompt_callback(PromptMessageBox);
    g_context->set_keyboard_prompt_callback(PromptKeyboard);
    g_vibration_sink = ForwardVibration;
    InstallLifecycleObservers();
    // The steps of XeniaAppDelegate (ui/ios/app/ios_app_delegate.mm:95-268)
    // that the Core needs, without its launcher, JIT hand-off or crash log.
    [g_view layoutIfNeeded];
    g_app = NeoXeniaCreateEmulatorApp(*g_context);
    if (g_app) {
      xe::InitializeLogging(g_app->GetName());
#if __IPHONE_OS_VERSION_MAX_ALLOWED < 270000
      // Built with an iOS 26 SDK (GitHub's runners have no Xcode 27):
      // rewindbox-core.patch compiles StateReporting and the external-display
      // scene accessory out of this Core, so they are absent even on iOS 27.
      XELOGI("RewindBox XeniaCore: iOS SDK {}; StateReporting and the external-display "
             "scene accessory are compiled out (absent on iOS 27 too)",
             __IPHONE_OS_VERSION_MAX_ALLOWED);
#endif
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
    // Before any Xenia thread exists (system_ios.h).
    g_fatal_record_path = std::string(configuration->storage_root) + "/last-fatal.txt";
    xe::IOSSystemHooks hooks = {};
    hooks.note_fatal_error = NoteFatalError;
    xe::SetIOSSystemHooks(hooks);
    g_host_storage_root = configuration->storage_root;
    g_host_content_root = configuration->content_root;
    g_host_cache_root = configuration->cache_root;
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
  if (g_code_region_held.load(std::memory_order_acquire)) state |= NEO_XENIA_JIT_CODE_REGION_HELD;
  return state;
}

int ValidateJit(char* error, size_t capacity) {
  // Before the one-time prepare, a tool that set CS_DEBUGGED and left would
  // turn the Core's prepare brk into a fatal "JIT was turned off" error.
  const uint32_t state = JitState();
  // Without room below 8 GB that prepare is a FatalError, which would close
  // RewindBox (jit_memory_ios.cc RequestExternalJitPrepare).
  if ((state & NEO_XENIA_JIT_NEEDS_TOOL) && !(state & NEO_XENIA_JIT_CODE_REGION_HELD)) {
    Copy(error, capacity,
         "JIT unavailable: no address space below 8 GB is held for the code region; restart "
         "RewindBox (iOS 26 TXM)");
    return 0;
  }
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
  // Emulator::LaunchPath picks the device from the file's magic; the kind
  // only bounds what RewindBox hands over (an XContent header is mounted by
  // XContentContainerDevice, its SVOD data found in "<header>.data").
  if (kind != NEO_XENIA_CONTENT_DISC_IMAGE && kind != NEO_XENIA_CONTENT_ZAR &&
      kind != NEO_XENIA_CONTENT_EXECUTABLE && kind != NEO_XENIA_CONTENT_PACKAGE) {
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
  g_guest_frames.store(0, std::memory_order_relaxed);
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
    // A guest waiting on a prompt would hold its thread through the stop.
    XeniaCancelGuestAlerts(PromptRoot());
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

int GetStats(NeoXeniaStats* out) {
  if (!out || out->size < sizeof(NeoXeniaStats)) return 0;
  out->guest_frames = g_guest_frames.load(std::memory_order_relaxed);
  out->sample_ns = clock_gettime_nsec_np(CLOCK_UPTIME_RAW);
  return 1;
}

static_assert(NEO_XENIA_CODE_REGION_SIZE ==
                  xe::cpu::backend::IOSJitMemory::kExecuteRegionReserveSize,
              "the host reserves the size IOSJitMemory holds");

int AdoptCodeRegion(void* reservation, size_t size) {
  const int result = NeoXeniaAdoptExecuteRegion(reservation, size);
  g_code_region_held.store(result != NEO_XENIA_CODE_REGION_NONE, std::memory_order_release);
  return result;
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
    GetStats,
    AdoptCodeRegion,
};

}  // namespace

// ---------------------------------------------------------- upstream hooks

// XeniOS keeps its code region below 8 GB because StikDebug 3.1.x drops the
// high bits of the address it prepares (jit_memory_ios.cc). RewindBox's
// helpers use its patched StikJIT (build-utils/patch_stikjit_rpcs3.py: 16 hex
// digits per address; validate_stikjit_ipa.py requires that patch's marker in
// the IPA), which prepares any address, as RPCS3's arena at 0x7000000000
// shows. With the 8 GB limit the region often found no room (device runs:
// 36 to 687 MiB free below 8 GB). Called from static initializers: no state.
extern "C" uintptr_t NeoXeniaExecuteRegionLimit(void) { return uintptr_t(1) << 47; }

void NeoXeniaApplyHostRoots() {
  // IPA 728: the config saved under IPA 727 named the previous container's
  // Content folder; create_directories on it threw and RewindBox aborted.
  SetCvar("storage_root", g_host_storage_root);
  SetCvar("content_root", g_host_content_root);
  SetCvar("cache_root", g_host_cache_root);
  SetCvar("log_file", g_host_storage_root + "/xenia.log");
}

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

void NeoXeniaNotifyKernelReady() {
  // On the emulator thread, before any guest thread: XeniOS's profile calls
  // only reach the ProfileManager here (the picture cache is synchronized),
  // and a later title start in this process signs in again below.
  SignInProfileOnMain(0);
}

void NeoXeniaNotifyTitleLaunched() {
  // A title of a later launch in this process (the kernel is kept): player 1
  // is signed in again if a title signed them out.
  neo_xenia::g_vibration.store(0, std::memory_order_relaxed);
  dispatch_async(dispatch_get_main_queue(), ^{
    SignInProfileOnMain(0);
  });
  SetTitleState(TitleState::kRunning);
  Emit("firstFrame", "title launched");
}

extern "C" void NeoXeniaNotifyGuestSwap(void) {
  g_guest_frames.fetch_add(1, std::memory_order_relaxed);
}

std::unique_ptr<xe::hid::InputDriver> NeoXeniaCreateInputDriver(xe::ui::Window* window,
                                                                size_t window_z_order) {
  return std::make_unique<neo_xenia::NeoXeniaInputDriver>(window, window_z_order);
}

extern "C" __attribute__((visibility("default"))) const NeoXeniaAPI* NeoXenia_GetAPI(
    uint32_t version) {
  return version == NEO_XENIA_ABI_VERSION ? &kAPI : nullptr;
}

// SPDX-License-Identifier: BSD-3-Clause
// In-process XeniOS session host (docs/xenios-playlist.md § Native boundary).
//
// Ownership rules:
// - XeniaCore.framework is dlopen'ed lazily, RTLD_LOCAL, only on iOS 26+,
//   never at plugin registration: the app keeps launching on iOS 18-25 and
//   other engines never see Xenia's symbols.
// - One session at a time. Each launch gets a new transaction; events from
//   an older transaction are dropped, so a late callback never closes the
//   next game.
// - UIKit only on main; prepare/boot/shutdown only on the session queue.
#import "XeniaInternalBridgePlugin.h"
#import "XeniaCoreABI.h"
#import "XeniaJitBridgePlugin.h"
#import "XeniaTouchControls.h"
#include <cmath>

#import <Foundation/Foundation.h>
#import <GameController/GameController.h>
#import <QuartzCore/QuartzCore.h>
#import <UIKit/UIKit.h>
#import <dlfcn.h>
#include <atomic>
#include <string>
#include <vector>

static NSString* const kXeniaChannel = @"rewindbox/xenia_internal";
static const uint32_t kXeniaPrepareTimeoutMs = 30000;
static const uint32_t kXeniaBootTimeoutMs = 60000;
static const uint32_t kXeniaShutdownTimeoutMs = 15000;
// The Core issues its prepare (x16=1) and detach (x16=0) inside
// Emulator::Setup, which boot waits for: the helper's confirmation follows
// at once. The wait still holds the session queue while the title runs and
// the menu is not offered yet, so it stays short.
static const NSTimeInterval kXeniaDetachTimeout = 30.0;

// Settings keys the Core accepts (mirrors XeniaSettingsService.managedKeys).
static NSSet<NSString*>* XeniaManagedKeys(void) {
  static NSSet<NSString*>* keys;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    keys = [NSSet setWithArray:@[
      @"framerate_limit", @"guest_display_refresh_cap", @"present_letterbox",
      @"use_50Hz_mode", @"async_shader_compilation", @"apu_max_queued_frames",
      @"xma_decoder", @"mount_cache", @"user_language", @"user_country"
    ]];
  });
  return keys;
}

static NSString* XeniaFrameworkPath(void) {
  NSString* frameworks = NSBundle.mainBundle.privateFrameworksPath;
  return [frameworks stringByAppendingPathComponent:@"XeniaCore.framework/XeniaCore"];
}

// Apple's Metal Shader Converter runtime, a non-weak dependency of the Core
// (`@rpath/libmetalirconverter.dylib`): Xenia's Metal backend cannot render
// without it (docs/xenios-playlist.md § Shader converter). It ships in the
// app's Frameworks folder, authenticated at packaging time by
// build-utils/xenia/validate_shader_converter.py; it is never downloaded.
static NSString* XeniaShaderConverterPath(void) {
  NSString* frameworks = NSBundle.mainBundle.privateFrameworksPath;
  return [frameworks stringByAppendingPathComponent:@"libmetalirconverter.dylib"];
}

static BOOL XeniaSupportedOS(void) {
  NSOperatingSystemVersion minimum = {(NSInteger)NEO_XENIA_MINIMUM_IOS_MAJOR, 0, 0};
  return [NSProcessInfo.processInfo isOperatingSystemAtLeastVersion:minimum];
}

static UIViewController* XeniaTopViewController(void) {
  UIWindow* keyWindow = nil;
  for (UIScene* scene in UIApplication.sharedApplication.connectedScenes) {
    if (![scene isKindOfClass:UIWindowScene.class] ||
        scene.activationState != UISceneActivationStateForegroundActive) continue;
    for (UIWindow* window in ((UIWindowScene*)scene).windows) {
      if (window.isKeyWindow) { keyWindow = window; break; }
    }
    if (keyWindow) break;
  }
  UIViewController* controller = keyWindow.rootViewController;
  while (controller.presentedViewController) controller = controller.presentedViewController;
  return controller;
}

@class RBXeniaSessionController;

@interface XeniaInternalBridgePlugin ()
@property(nonatomic, strong) FlutterMethodChannel* channel;
@property(nonatomic, strong) dispatch_queue_t sessionQueue;
@property(nonatomic, strong) RBXeniaSessionController* session;
@property(nonatomic, assign) const NeoXeniaAPI* api;
@property(nonatomic, copy) NSString* loadDetail;
- (void)deliverEvent:(NSString*)event transaction:(uint64_t)transaction message:(NSString*)message;
- (void)requestStopFromMenu;
- (void)setUserPaused:(BOOL)paused;
/// The launch reported success and no teardown runs: the menu, quit and
/// pause act only then (a Quit during the presentation would queue a
/// shutdown before prepare and boot).
- (BOOL)sessionRunning;
@end

static std::atomic<uint64_t> gXeniaTransaction{0};
static __weak XeniaInternalBridgePlugin* gXeniaPlugin;

static void XeniaEventCallback(void* /*context*/, uint64_t transaction,
                               const char* event, const char* message) {
  NSString* name = event ? @(event) : @"unknown";
  NSString* detail = message ? @(message) : @"";
  dispatch_async(dispatch_get_main_queue(), ^{
    [gXeniaPlugin deliverEvent:name transaction:transaction message:detail];
  });
}

// Full-screen host of the Core's render view, RewindBox's Xbox 360 touch
// controls (shared touch-layout layer), a Menu button (Resume / touch
// controls / Quit) and the game-controller relay. No XeniOS launcher,
// library or onboarding.
@interface RBXeniaSessionController : UIViewController
@property(nonatomic, weak) XeniaInternalBridgePlugin* owner;
@property(nonatomic, assign) const NeoXeniaAPI* api;
@property(nonatomic, strong) UIView* renderView;
@property(nonatomic, copy) NSString* gameTitle;
@property(nonatomic, copy) NSString* touchGameKey;
@property(nonatomic, copy) NSString* locale;
/// Localized by Dart (XeniaLocale): menu, resume, quit.
@property(nonatomic, copy) NSDictionary<NSString*, NSString*>* texts;
@property(nonatomic, assign) BOOL menuOpen;
@property(nonatomic, readonly) BOOL editingTouchControls;
@end

// One pad of the RewindBox session (XInput bits, sticks Y up, triggers 0..1).
struct XeniaPadState {
  uint32_t buttons = 0;
  float lx = 0, ly = 0, rx = 0, ry = 0, lt = 0, rt = 0;
};

// The RPCS3 merge policy (RPCS3PadMerge.h): buttons OR, triggers maximum,
// each stick takes the larger deflection.
static XeniaPadState XeniaMergePads(const XeniaPadState& a, const XeniaPadState& b) {
  XeniaPadState merged;
  merged.buttons = a.buttons | b.buttons;
  merged.lt = MAX(a.lt, b.lt);
  merged.rt = MAX(a.rt, b.rt);
  const bool leftA = hypotf(a.lx, a.ly) >= hypotf(b.lx, b.ly);
  merged.lx = leftA ? a.lx : b.lx;
  merged.ly = leftA ? a.ly : b.ly;
  const bool rightA = hypotf(a.rx, a.ry) >= hypotf(b.rx, b.ry);
  merged.rx = rightA ? a.rx : b.rx;
  merged.ry = rightA ? a.ry : b.ry;
  return merged;
}

@implementation RBXeniaSessionController {
  CADisplayLink* _input;
  UIButton* _menuButton;
  RBXeniaTouchControlsView* _touch;
  NeoTouchControllerMonitor* _monitor;
  NeoTouchLayoutEditor* _editor;
}

- (BOOL)prefersStatusBarHidden { return YES; }
- (BOOL)prefersHomeIndicatorAutoHidden { return YES; }

- (NSString*)text:(NSString*)key fallback:(NSString*)fallback {
  NSString* value = self.texts[key];
  return value.length ? value : fallback;
}

- (void)viewDidLoad {
  [super viewDidLoad];
  self.view.backgroundColor = UIColor.blackColor;
  if (self.renderView) {
    self.renderView.frame = self.view.bounds;
    self.renderView.autoresizingMask =
        UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    [self.view addSubview:self.renderView];
  }
  _touch = [[RBXeniaTouchControlsView alloc] initWithLocale:self.locale];
  _touch.frame = self.view.bounds;
  _touch.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
  _touch.gameKey = self.touchGameKey;
  [self.view addSubview:_touch];
  __weak RBXeniaSessionController* weakSelf = self;
  _monitor = [[NeoTouchControllerMonitor alloc] initWithChangeHandler:^(BOOL) {
    [weakSelf updateTouchVisibility];
  }];
  [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(controllerPreferenceChanged:)
                                             name:NeoTouchControllerPreferenceDidChangeNotification
                                           object:nil];

  _menuButton = [UIButton buttonWithType:UIButtonTypeSystem];
  [_menuButton setImage:[UIImage systemImageNamed:@"line.3.horizontal.circle"]
               forState:UIControlStateNormal];
  _menuButton.tintColor = [UIColor colorWithWhite:1 alpha:0.7];
  _menuButton.accessibilityLabel = [self text:@"menu" fallback:@"Menu"];
  _menuButton.translatesAutoresizingMaskIntoConstraints = NO;
  [_menuButton addTarget:self action:@selector(openMenu) forControlEvents:UIControlEventTouchUpInside];
  [self.view addSubview:_menuButton];
  UILayoutGuide* safe = self.view.safeAreaLayoutGuide;
  [NSLayoutConstraint activateConstraints:@[
    [_menuButton.topAnchor constraintEqualToAnchor:safe.topAnchor constant:8],
    [_menuButton.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor constant:-8],
    [_menuButton.widthAnchor constraintEqualToConstant:44],
    [_menuButton.heightAnchor constraintEqualToConstant:44],
  ]];
  [self updateTouchVisibility];
}

- (void)dealloc {
  [NSNotificationCenter.defaultCenter removeObserver:self];
  [_monitor invalidate];
}

- (void)controllerPreferenceChanged:(NSNotification*)notification {
  [self updateTouchVisibility];
}

- (BOOL)editingTouchControls {
  return _editor != nil;
}

// The rule shared by every engine (NeoTouchControlsShouldHide): hidden under
// a menu, or with a compatible controller while the console's preference
// is on; never while editing. Hiding releases every held control first.
- (void)updateTouchVisibility {
  const BOOL hide = NeoTouchControlsShouldHide(XeniaTouchLayoutKey, _monitor.connected, YES,
                                               self.menuOpen, self.editingTouchControls);
  if (hide && !_touch.hidden) [_touch releaseAllInput];
  _touch.hidden = hide;
  [self.view bringSubviewToFront:_menuButton];
}

- (void)viewDidAppear:(BOOL)animated {
  [super viewDidAppear:animated];
  if (!_input) {
    _input = [CADisplayLink displayLinkWithTarget:self selector:@selector(pollInput)];
    [_input addToRunLoop:NSRunLoop.mainRunLoop forMode:NSRunLoopCommonModes];
  }
}

- (void)stopInput {
  [_input invalidate];
  _input = nil;
  [_touch releaseAllInput];
  [_monitor invalidate];
}

- (void)sendNeutralPad {
  if (!self.api) return;
  self.api->set_buttons(0);
  self.api->set_axes(0, 0, 0, 0, 0, 0);
}

// X_INPUT_GAMEPAD_* (xenia/hid/input.h).
- (void)pollInput {
  const NeoXeniaAPI* api = self.api;
  if (!api) return;
  if (self.menuOpen || self.editingTouchControls) {
    // RPCS3's rule: a connected, neutral pad while a menu or the editor covers the game.
    [self sendNeutralPad];
    return;
  }
  XeniaPadState controller;
  GCExtendedGamepad* pad = GCController.current.extendedGamepad;
  if (pad) {
    if (pad.buttonHome.pressed) {
      [self openMenu];
      return;
    }
    if (pad.dpad.up.pressed) controller.buttons |= 0x0001;
    if (pad.dpad.down.pressed) controller.buttons |= 0x0002;
    if (pad.dpad.left.pressed) controller.buttons |= 0x0004;
    if (pad.dpad.right.pressed) controller.buttons |= 0x0008;
    if (pad.buttonMenu.pressed) controller.buttons |= 0x0010;  // Start
    if (pad.buttonOptions.pressed) controller.buttons |= 0x0020;  // Back
    if (pad.leftThumbstickButton.pressed) controller.buttons |= 0x0040;
    if (pad.rightThumbstickButton.pressed) controller.buttons |= 0x0080;
    if (pad.leftShoulder.pressed) controller.buttons |= 0x0100;
    if (pad.rightShoulder.pressed) controller.buttons |= 0x0200;
    if (pad.buttonA.pressed) controller.buttons |= 0x1000;
    if (pad.buttonB.pressed) controller.buttons |= 0x2000;
    if (pad.buttonX.pressed) controller.buttons |= 0x4000;
    if (pad.buttonY.pressed) controller.buttons |= 0x8000;
    controller.lx = pad.leftThumbstick.xAxis.value;
    controller.ly = pad.leftThumbstick.yAxis.value;
    controller.rx = pad.rightThumbstick.xAxis.value;
    controller.ry = pad.rightThumbstick.yAxis.value;
    controller.lt = pad.leftTrigger.value;
    controller.rt = pad.rightTrigger.value;
  }
  XeniaPadState state = controller;
  if (!_touch.hidden) {
    XeniaPadState touch;
    touch.buttons = _touch.buttons;
    touch.lx = _touch.leftX;
    touch.ly = _touch.leftY;
    touch.rx = _touch.rightX;
    touch.ry = _touch.rightY;
    touch.lt = _touch.leftTrigger;
    touch.rt = _touch.rightTrigger;
    state = XeniaMergePads(controller, touch);
  }
  api->set_buttons(state.buttons);
  api->set_axes(state.lx, state.ly, state.rx, state.ry, state.lt, state.rt);
}

- (void)openMenu {
  if (self.menuOpen || self.editingTouchControls || !self.owner.sessionRunning) return;
  self.menuOpen = YES;
  [self updateTouchVisibility];
  [self sendNeutralPad];
  [self.owner setUserPaused:YES];
  UIAlertController* menu =
      [UIAlertController alertControllerWithTitle:self.gameTitle
                                          message:nil
                                   preferredStyle:UIAlertControllerStyleAlert];
  __weak RBXeniaSessionController* weakSelf = self;
  [menu addAction:[UIAlertAction actionWithTitle:[self text:@"resume" fallback:@"Resume"]
                                           style:UIAlertActionStyleCancel
                                         handler:^(UIAlertAction*) {
    weakSelf.menuOpen = NO;
    [weakSelf updateTouchVisibility];
    [weakSelf.owner setUserPaused:NO];
  }]];
  [menu addAction:[UIAlertAction actionWithTitle:NeoTouchLayoutText(@"editTouchControls", self.locale)
                                           style:UIAlertActionStyleDefault
                                         handler:^(UIAlertAction*) {
    [weakSelf beginTouchEditing];
  }]];
  [menu addAction:[UIAlertAction actionWithTitle:[self text:@"quit" fallback:@"Quit"]
                                           style:UIAlertActionStyleDestructive
                                         handler:^(UIAlertAction*) {
    [weakSelf.owner requestStopFromMenu];
  }]];
  [self presentViewController:menu animated:YES completion:nil];
}

// The shared editor over the real controls; the game stays paused and the
// Core receives a neutral pad until it closes (Build 484 contract).
- (void)beginTouchEditing {
  if (_editor) return;
  [_touch releaseAllInput];
  // As ARMSX2: the real controls stay drawn under the editor but receive no touch.
  _touch.userInteractionEnabled = NO;
  _editor = [[NeoTouchLayoutEditor alloc] initWithHost:_touch
                                             layoutKey:XeniaTouchLayoutKey
                                               gameKey:_touch.gameKey
                                                 title:self.gameTitle
                                                locale:self.locale
                                                 store:NeoTouchLayoutStore.sharedStore];
  _editor.controllerConnected = _monitor.connected;
  __weak RBXeniaSessionController* weakSelf = self;
  _editor.finished = ^(BOOL) {
    RBXeniaSessionController* strongSelf = weakSelf;
    if (!strongSelf) return;
    [strongSelf->_touch endEditingOverride];
    strongSelf->_touch.userInteractionEnabled = YES;
    strongSelf->_editor = nil;  // The editor removed itself.
    strongSelf.menuOpen = NO;
    [strongSelf updateTouchVisibility];
    [strongSelf.owner setUserPaused:NO];
  };
  [self updateTouchVisibility];
  [_editor presentOverCanvas];
  [self.view bringSubviewToFront:_editor];
}

- (void)viewWillTransitionToSize:(CGSize)size
       withTransitionCoordinator:(id<UIViewControllerTransitionCoordinator>)coordinator {
  [super viewWillTransitionToSize:size withTransitionCoordinator:coordinator];
  // The controls release on their own orientation change; the editor follows it.
  [coordinator animateAlongsideTransition:nil completion:^(id) {
    [self updateTouchVisibility];
  }];
}

@end

@implementation XeniaInternalBridgePlugin {
  uint64_t _transaction;
  BOOL _userPaused;
  BOOL _backgroundPaused;
  BOOL _stopping;
  // Set when a title did not shut down within its deadline: the Core may
  // still own its threads and view, so no new session starts in this
  // process (the same rule as MeloNX's quarantine).
  BOOL _quarantined;
  NSString* _endReason;
  // Between presenting the session and the launch result: the result alone
  // reports the outcome, so a Core stop/error event of this window is kept
  // for it instead of being reported a second time as `ended`.
  BOOL _launchPending;
  NSString* _pendingEndReason;
  NSString* _pendingEndDetail;
  // A Core that cannot be used (ABI mismatch, dlopen failure) stays refused
  // for the process: it is not opened again on every call.
  NSString* _loadFailure;
}

- (BOOL)sessionRunning {
  return self.session != nil && !_launchPending && !_stopping;
}

// Every launch that fails ends the JIT transaction Dart opened for it, as
// ARMSX2 does (Armsx2InternalBridgePlugin failTransaction): otherwise the
// helper session stays registered and every later prepareJit is refused
// until RewindBox restarts. A launch still in flight keeps its own.
- (void)failLaunch:(NSDictionary*)report result:(FlutterResult)result {
  if (!_launchPending) XeniaJitAbortTransaction();
  result(report);
}

+ (void)registerWithRegistrar:(NSObject<FlutterPluginRegistrar>*)registrar {
  XeniaInternalBridgePlugin* plugin = [[XeniaInternalBridgePlugin alloc] init];
  plugin.channel = [FlutterMethodChannel methodChannelWithName:kXeniaChannel
                                               binaryMessenger:registrar.messenger];
  plugin.sessionQueue = dispatch_queue_create("rewindbox.xenia.session", DISPATCH_QUEUE_SERIAL);
  gXeniaPlugin = plugin;
  [registrar addMethodCallDelegate:plugin channel:plugin.channel];
  // Dedicated XeniOS JIT helper transaction (channel neostation/xenia_jit),
  // derived from the ARMSX2 helper by tools/xenia/derive_jit_helper.py.
  [XeniaJitBridgePlugin registerWithRegistrar:registrar];
  // Settings › Systems › Xbox 360 opens the touch-controls editor on a
  // non-interactive preview, without a session.
  XeniaTouchControlsRegisterPreview();
  NSNotificationCenter* center = NSNotificationCenter.defaultCenter;
  [center addObserver:plugin selector:@selector(applicationWillResignActive)
                 name:UIApplicationWillResignActiveNotification object:nil];
  [center addObserver:plugin selector:@selector(applicationDidBecomeActive)
                 name:UIApplicationDidBecomeActiveNotification object:nil];
}

- (void)handleMethodCall:(FlutterMethodCall*)call result:(FlutterResult)result {
  if ([call.method isEqualToString:@"availability"]) {
    result([self availability]);
  } else if ([call.method isEqualToString:@"isSessionActive"]) {
    result(@(self.session != nil));
  } else if ([call.method isEqualToString:@"jitState"]) {
    result([self jitState]);
  } else if ([call.method isEqualToString:@"launch"]) {
    [self launch:call.arguments result:result];
  } else if ([call.method isEqualToString:@"abortJit"]) {
    // Dart could not reach `launch` after preparing JIT (docs/xenios-playlist.md § JIT helper).
    if (!self.session) XeniaJitAbortTransaction();
    result(nil);
  } else {
    result(FlutterMethodNotImplemented);
  }
}

- (NSDictionary*)availability {
  NSString* os = NSProcessInfo.processInfo.operatingSystemVersionString ?: @"";
  if (!XeniaSupportedOS()) return @{@"state" : @"requiresIOS26", @"osVersion" : os};
  if (![NSFileManager.defaultManager fileExistsAtPath:XeniaFrameworkPath()]) {
    return @{@"state" : @"engineMissing", @"osVersion" : os};
  }
  if (![NSFileManager.defaultManager fileExistsAtPath:XeniaShaderConverterPath()]) {
    return @{@"state" : @"shaderConverterMissing", @"osVersion" : os};
  }
  if (_loadFailure) {
    return @{@"state" : _loadFailure, @"osVersion" : os, @"detail" : self.loadDetail ?: @""};
  }
  NSMutableDictionary* state = [@{@"state" : @"ready", @"osVersion" : os} mutableCopy];
  if (self.api && self.api->source_revision) state[@"sourceRevision"] = @(self.api->source_revision);
  return state;
}

// What the next launch needs from the JIT helper, decided by the Core itself
// (NeoXeniaAPI jit_state). Loads the Core, which only runs static
// initializers (a PROT_NONE reservation of the code region): no emulator.
- (NSDictionary*)jitState {
  NSString* loadError = [self loadCore];
  if (loadError) return @{@"error" : loadError, @"detail" : self.loadDetail ?: @""};
  const uint32_t state = self.api->jit_state();
  return @{
    @"needsTool" : @((state & NEO_XENIA_JIT_NEEDS_TOOL) != 0),
    @"toolAttached" : @((state & NEO_XENIA_JIT_TOOL_ATTACHED) != 0),
    @"debugged" : @((state & NEO_XENIA_JIT_CS_DEBUGGED) != 0),
    @"brokerPath" : @((state & NEO_XENIA_JIT_BROKER_PATH) != 0),
    @"handshakeActive" : @(XeniaJitHasActiveCoreHandshake()),
  };
}

// Loads the Core once per process. RTLD_LOCAL keeps its symbols private;
// the framework is never unloaded (Xenia's globals, JIT mapping and signal
// handlers are process-lifetime, XeniOS jit_memory_ios.cc:100-113).
- (NSString*)loadCore {
  if (self.api) return nil;
  if (_loadFailure) return _loadFailure;
  if (!XeniaSupportedOS()) return @"requiresIOS26";
  NSString* path = XeniaFrameworkPath();
  if (![NSFileManager.defaultManager fileExistsAtPath:path]) return @"engineMissing";
  // Without it dlopen fails inside dyld with a bare "Library not loaded".
  if (![NSFileManager.defaultManager fileExistsAtPath:XeniaShaderConverterPath()]) {
    return @"shaderConverterMissing";
  }
  void* handle = dlopen(path.fileSystemRepresentation, RTLD_NOW | RTLD_LOCAL);
  if (!handle) {
    const char* reason = dlerror();
    self.loadDetail = reason ? @(reason) : @"";
    _loadFailure = @"coreLoadFailed";
    return _loadFailure;
  }
  NeoXeniaGetAPI getAPI = (NeoXeniaGetAPI)dlsym(handle, "NeoXenia_GetAPI");
  const NeoXeniaAPI* api = getAPI ? getAPI(NEO_XENIA_ABI_VERSION) : nullptr;
  if (!api || api->version != NEO_XENIA_ABI_VERSION || api->size < sizeof(NeoXeniaAPI)) {
    // The image stays mapped (its initializers ran); it is never used.
    self.loadDetail = api ? [NSString stringWithFormat:@"ABI %u, bridge %u", api->version,
                                                       NEO_XENIA_ABI_VERSION]
                          : @"NeoXenia_GetAPI missing or refused the bridge ABI";
    _loadFailure = @"abiMismatch";
    return _loadFailure;
  }
  self.api = api;
  return nil;
}

- (void)launch:(id)arguments result:(FlutterResult)result {
  if (_quarantined) {
    [self failLaunch:@{@"success" : @NO, @"error" : @"restartRequired"} result:result];
    return;
  }
  if (self.session || _stopping) {
    // failLaunch keeps the transaction of a launch still in flight.
    [self failLaunch:@{@"success" : @NO, @"error" : @"sessionActive"} result:result];
    return;
  }
  NSDictionary* args = [arguments isKindOfClass:NSDictionary.class] ? arguments : @{};
  NSString* gamePath = args[@"gamePath"];
  NSString* storage = args[@"storageRoot"];
  NSString* content = args[@"contentRoot"];
  NSString* cache = args[@"cacheRoot"];
  NSNumber* kind = args[@"contentKind"];
  if (![gamePath isKindOfClass:NSString.class] || ![storage isKindOfClass:NSString.class] ||
      ![content isKindOfClass:NSString.class] || ![cache isKindOfClass:NSString.class] ||
      ![kind isKindOfClass:NSNumber.class]) {
    [self failLaunch:@{@"success" : @NO, @"error" : @"invalidArguments"} result:result];
    return;
  }
  if (![NSFileManager.defaultManager isReadableFileAtPath:gamePath]) {
    [self failLaunch:@{@"success" : @NO, @"error" : @"gameUnreadable"} result:result];
    return;
  }
  NSString* loadError = [self loadCore];
  if (loadError) {
    [self failLaunch:@{@"success" : @NO, @"error" : loadError, @"detail" : self.loadDetail ?: @""}
              result:result];
    return;
  }
  NSDictionary* rawSettings = [args[@"settings"] isKindOfClass:NSDictionary.class] ? args[@"settings"] : @{};
  NSMutableArray<NSString*>* keys = [NSMutableArray array];
  NSMutableArray<NSString*>* values = [NSMutableArray array];
  for (id key in rawSettings) {
    id value = rawSettings[key];
    if (![key isKindOfClass:NSString.class] || ![value isKindOfClass:NSString.class] ||
        ![XeniaManagedKeys() containsObject:key]) continue;
    [keys addObject:key];
    [values addObject:value];
  }
  NSString* title = [args[@"title"] isKindOfClass:NSString.class] ? args[@"title"] : @"";
  const NeoXeniaAPI* api = self.api;
  const uint64_t transaction = ++gXeniaTransaction;
  _transaction = transaction;
  _userPaused = NO;
  _backgroundPaused = NO;
  _endReason = nil;
  _pendingEndReason = nil;
  _pendingEndDetail = nil;

  char error[512] = {0};
  UIView* render = (__bridge UIView*)api->create_render_view(error, sizeof error);
  if (!render) {
    [self failLaunch:@{@"success" : @NO, @"error" : @"renderViewFailed", @"detail" : @(error)}
              result:result];
    return;
  }
  RBXeniaSessionController* controller = [[RBXeniaSessionController alloc] init];
  controller.owner = self;
  controller.api = api;
  controller.renderView = render;
  controller.gameTitle = title;
  controller.touchGameKey = [args[@"touchGameKey"] isKindOfClass:NSString.class] ? args[@"touchGameKey"] : nil;
  controller.locale = [args[@"locale"] isKindOfClass:NSString.class] ? args[@"locale"] : @"en";
  controller.texts = [args[@"texts"] isKindOfClass:NSDictionary.class] ? args[@"texts"] : @{};
  controller.modalPresentationStyle = UIModalPresentationFullScreen;
  self.session = controller;
  UIViewController* presenter = XeniaTopViewController();
  if (!presenter) {
    self.session = nil;
    api->release_render_view();
    [self failLaunch:@{@"success" : @NO, @"error" : @"noPresenter"} result:result];
    return;
  }

  _launchPending = YES;
  [presenter presentViewController:controller animated:YES completion:^{
    dispatch_async(self.sessionQueue, ^{
      std::vector<std::string> storageKeys, storageValues;
      std::vector<NeoXeniaSetting> settings;
      for (NSUInteger index = 0; index < keys.count; index++) {
        storageKeys.emplace_back(keys[index].UTF8String);
        storageValues.emplace_back(values[index].UTF8String);
      }
      for (size_t index = 0; index < storageKeys.size(); index++) {
        settings.push_back({storageKeys[index].c_str(), storageValues[index].c_str()});
      }
      NeoXeniaConfiguration configuration = {};
      configuration.size = sizeof configuration;
      configuration.transaction = transaction;
      configuration.storage_root = storage.fileSystemRepresentation;
      configuration.content_root = content.fileSystemRepresentation;
      configuration.cache_root = cache.fileSystemRepresentation;
      configuration.settings = settings.data();
      configuration.settings_count = (uint32_t)settings.size();
      configuration.event = XeniaEventCallback;
      configuration.context = nullptr;
      char failure[512] = {0};
      NSString* stage = nil;
      NSString* jitDetail = nil;
      // A helper attached for the Core's handshake must answer the host
      // nonce probe (brk #0xf00d, x16=3) before the Core runs: a tool that
      // set CS_DEBUGGED and left would make the Core's prepare fatal.
      const BOOL handshake = XeniaJitHasActiveCoreHandshake();
      if (handshake && !XeniaJitConfirmCoreLoadHandoff()) {
        stage = @"jitHandshakeFailed";
      } else if (!api->prepare(&configuration, kXeniaPrepareTimeoutMs, failure, sizeof failure)) {
        stage = @"prepareFailed";
      } else if (!api->validate_jit(failure, sizeof failure)) {
        stage = @"jitUnavailable";
      } else if (!api->boot(gamePath.fileSystemRepresentation, kind.unsignedIntValue,
                            kXeniaBootTimeoutMs, failure, sizeof failure)) {
        stage = @"bootFailed";
      } else if (handshake) {
        // Emulator::Setup ran the Core's one-time prepare (x16=1) and detach
        // (x16=0): the helper must confirm it detached with CS_DEBUGGED kept.
        NSString* message = nil;
        if (!XeniaJitWaitForDetach(kXeniaDetachTimeout, &message)) {
          stage = @"jitDetachFailed";
          jitDetail = message;
        }
      }
      // Any failure ends this launch's transaction, the detach failure
      // included (ARMSX2's rule). A debugger the helper left attached then
      // shows as toolAttached without a live handshake, which Dart refuses
      // with restartRequired instead of answering the Core's requests
      // with a closed helper (XeniaJitService.planFor).
      if (stage) XeniaJitAbortTransaction();
      NSString* detail = jitDetail ?: @(failure);
      dispatch_async(dispatch_get_main_queue(), ^{
        NSString* outcome = stage;
        NSString* outcomeDetail = detail;
        if (!outcome && self->_pendingEndReason) {
          // The title stopped or failed between boot and this result.
          outcome = @"bootFailed";
          outcomeDetail = self->_pendingEndDetail ?: self->_pendingEndReason;
          XeniaJitAbortTransaction();
        }
        self->_launchPending = NO;
        self->_pendingEndReason = nil;
        self->_pendingEndDetail = nil;
        if (outcome) {
          [self teardownWithReason:outcome detail:outcomeDetail notify:NO];
          result(@{@"success" : @NO, @"error" : outcome, @"detail" : outcomeDetail ?: @""});
        } else {
          result(@{@"success" : @YES});
          [self.channel invokeMethod:@"sessionEvent" arguments:@{@"event" : @"launched"}];
          [self applyPause];  // the app may have gone to the background during boot
        }
      });
    });
  }];
}

- (void)deliverEvent:(NSString*)event transaction:(uint64_t)transaction message:(NSString*)message {
  if (transaction != _transaction || !self.session) return;  // late callback
  if (_launchPending) {
    // Reported once, by the launch result (see _launchPending).
    if ([event isEqualToString:@"stopped"] || [event isEqualToString:@"error"]) {
      _pendingEndReason = event;
      _pendingEndDetail = message;
    }
    return;
  }
  if ([event isEqualToString:@"stopped"] || [event isEqualToString:@"error"]) {
    [self teardownWithReason:([event isEqualToString:@"error"] ? @"error" : @"stopped")
                      detail:message
                      notify:YES];
    return;
  }
  [self.channel invokeMethod:@"sessionEvent" arguments:@{@"event" : event, @"detail" : message ?: @""}];
}

- (void)setUserPaused:(BOOL)paused {
  _userPaused = paused;
  [self applyPause];
}

- (void)applyPause {
  if (self.api && self.sessionRunning) self.api->set_paused(_userPaused || _backgroundPaused);
}

- (void)applicationWillResignActive {
  _backgroundPaused = YES;
  [self applyPause];
}

- (void)applicationDidBecomeActive {
  _backgroundPaused = NO;
  [self applyPause];
}

- (void)requestStopFromMenu {
  if (!self.api || !self.sessionRunning) return;
  self.api->request_stop();
  [self teardownWithReason:@"userQuit" detail:@"" notify:YES];
}

// Stops the title off main, then releases the view and dismisses on main.
// The transaction is retired first so no event of this session reaches the
// next one.
- (void)teardownWithReason:(NSString*)reason detail:(NSString*)detail notify:(BOOL)notify {
  if (_stopping || !self.session) return;
  _stopping = YES;
  _transaction = 0;
  RBXeniaSessionController* controller = self.session;
  [controller stopInput];
  const NeoXeniaAPI* api = self.api;
  dispatch_async(self.sessionQueue, ^{
    char failure[512] = {0};
    const int clean = api ? api->shutdown(kXeniaShutdownTimeoutMs, failure, sizeof failure) : 1;
    NSString* shutdownDetail = @(failure);
    dispatch_async(dispatch_get_main_queue(), ^{
      void (^finish)(void) = ^{
        if (clean == 0) {
          self->_quarantined = YES;
        } else if (api) {
          api->release_render_view();
        }
        self.session = nil;
        self->_stopping = NO;
        if (notify) {
          [self.channel invokeMethod:@"sessionEvent"
                           arguments:@{
                             @"event" : @"ended",
                             @"reason" : reason,
                             @"detail" : detail ?: @"",
                             @"cleanShutdown" : @(clean != 0),
                             @"requiresRestart" : @(clean == 0),
                             @"shutdownDetail" : shutdownDetail,
                           }];
        }
      };
      if (controller.presentingViewController) {
        [controller.presentingViewController dismissViewControllerAnimated:YES completion:finish];
      } else {
        finish();
      }
    });
  });
}

@end

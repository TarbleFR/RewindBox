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

@class XeniaSessionController;

@interface XeniaInternalBridgePlugin ()
@property(nonatomic, strong) FlutterMethodChannel* channel;
@property(nonatomic, strong) dispatch_queue_t sessionQueue;
@property(nonatomic, strong) XeniaSessionController* session;
@property(nonatomic, assign) const NeoXeniaAPI* api;
@property(nonatomic, copy) NSString* loadDetail;
- (void)deliverEvent:(NSString*)event transaction:(uint64_t)transaction message:(NSString*)message;
- (void)requestStopFromMenu;
- (void)setUserPaused:(BOOL)paused;
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

// Full-screen host of the Core's render view, a Menu button (Resume/Quit)
// and the game-controller relay. No XeniOS launcher, library or onboarding.
@interface XeniaSessionController : UIViewController
@property(nonatomic, weak) XeniaInternalBridgePlugin* owner;
@property(nonatomic, assign) const NeoXeniaAPI* api;
@property(nonatomic, strong) UIView* renderView;
@property(nonatomic, copy) NSString* gameTitle;
@property(nonatomic, assign) BOOL menuOpen;
@end

@implementation XeniaSessionController {
  CADisplayLink* _input;
  UIButton* _menuButton;
}

- (BOOL)prefersStatusBarHidden { return YES; }
- (BOOL)prefersHomeIndicatorAutoHidden { return YES; }

- (void)viewDidLoad {
  [super viewDidLoad];
  self.view.backgroundColor = UIColor.blackColor;
  if (self.renderView) {
    self.renderView.frame = self.view.bounds;
    self.renderView.autoresizingMask =
        UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    [self.view addSubview:self.renderView];
  }
  _menuButton = [UIButton buttonWithType:UIButtonTypeSystem];
  [_menuButton setImage:[UIImage systemImageNamed:@"line.3.horizontal.circle"]
               forState:UIControlStateNormal];
  _menuButton.tintColor = [UIColor colorWithWhite:1 alpha:0.7];
  _menuButton.accessibilityLabel = @"Menu";
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
}

// X_INPUT_GAMEPAD_* (xenia/hid/input.h).
- (void)pollInput {
  const NeoXeniaAPI* api = self.api;
  if (!api || self.menuOpen) return;
  GCExtendedGamepad* pad = GCController.current.extendedGamepad;
  if (!pad) {
    api->set_buttons(0);
    api->set_axes(0, 0, 0, 0, 0, 0);
    return;
  }
  if (pad.buttonHome.pressed) {
    [self openMenu];
    return;
  }
  uint32_t buttons = 0;
  if (pad.dpad.up.pressed) buttons |= 0x0001;
  if (pad.dpad.down.pressed) buttons |= 0x0002;
  if (pad.dpad.left.pressed) buttons |= 0x0004;
  if (pad.dpad.right.pressed) buttons |= 0x0008;
  if (pad.buttonMenu.pressed) buttons |= 0x0010;  // Start
  if (pad.buttonOptions.pressed) buttons |= 0x0020;  // Back
  if (pad.leftThumbstickButton.pressed) buttons |= 0x0040;
  if (pad.rightThumbstickButton.pressed) buttons |= 0x0080;
  if (pad.leftShoulder.pressed) buttons |= 0x0100;
  if (pad.rightShoulder.pressed) buttons |= 0x0200;
  if (pad.buttonA.pressed) buttons |= 0x1000;
  if (pad.buttonB.pressed) buttons |= 0x2000;
  if (pad.buttonX.pressed) buttons |= 0x4000;
  if (pad.buttonY.pressed) buttons |= 0x8000;
  api->set_buttons(buttons);
  api->set_axes(pad.leftThumbstick.xAxis.value, pad.leftThumbstick.yAxis.value,
                pad.rightThumbstick.xAxis.value, pad.rightThumbstick.yAxis.value,
                pad.leftTrigger.value, pad.rightTrigger.value);
}

- (void)openMenu {
  if (self.menuOpen) return;
  self.menuOpen = YES;
  if (self.api) {
    self.api->set_buttons(0);
    self.api->set_axes(0, 0, 0, 0, 0, 0);
  }
  [self.owner setUserPaused:YES];
  UIAlertController* menu =
      [UIAlertController alertControllerWithTitle:self.gameTitle
                                          message:nil
                                   preferredStyle:UIAlertControllerStyleAlert];
  __weak XeniaSessionController* weakSelf = self;
  [menu addAction:[UIAlertAction actionWithTitle:@"▶︎"
                                           style:UIAlertActionStyleCancel
                                         handler:^(UIAlertAction*) {
    weakSelf.menuOpen = NO;
    [weakSelf.owner setUserPaused:NO];
  }]];
  [menu addAction:[UIAlertAction actionWithTitle:@"✕"
                                           style:UIAlertActionStyleDestructive
                                         handler:^(UIAlertAction*) {
    [weakSelf.owner requestStopFromMenu];
  }]];
  menu.actions.firstObject.accessibilityLabel = @"Resume";
  menu.actions.lastObject.accessibilityLabel = @"Quit";
  [self presentViewController:menu animated:YES completion:nil];
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
}

+ (void)registerWithRegistrar:(NSObject<FlutterPluginRegistrar>*)registrar {
  XeniaInternalBridgePlugin* plugin = [[XeniaInternalBridgePlugin alloc] init];
  plugin.channel = [FlutterMethodChannel methodChannelWithName:kXeniaChannel
                                               binaryMessenger:registrar.messenger];
  plugin.sessionQueue = dispatch_queue_create("rewindbox.xenia.session", DISPATCH_QUEUE_SERIAL);
  gXeniaPlugin = plugin;
  [registrar addMethodCallDelegate:plugin channel:plugin.channel];
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
  } else if ([call.method isEqualToString:@"launch"]) {
    [self launch:call.arguments result:result];
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
  NSMutableDictionary* state = [@{@"state" : @"ready", @"osVersion" : os} mutableCopy];
  if (self.api && self.api->source_revision) state[@"sourceRevision"] = @(self.api->source_revision);
  return state;
}

// Loads the Core once per process. RTLD_LOCAL keeps its symbols private;
// the framework is never unloaded (Xenia's globals, JIT mapping and signal
// handlers are process-lifetime, XeniOS jit_memory_ios.cc:100-113).
- (NSString*)loadCore {
  if (self.api) return nil;
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
    return @"coreLoadFailed";
  }
  NeoXeniaGetAPI getAPI = (NeoXeniaGetAPI)dlsym(handle, "NeoXenia_GetAPI");
  const NeoXeniaAPI* api = getAPI ? getAPI(NEO_XENIA_ABI_VERSION) : nullptr;
  if (!api || api->version != NEO_XENIA_ABI_VERSION || api->size < sizeof(NeoXeniaAPI)) {
    return @"abiMismatch";
  }
  self.api = api;
  return nil;
}

- (void)launch:(id)arguments result:(FlutterResult)result {
  if (_quarantined) {
    result(@{@"success" : @NO, @"error" : @"restartRequired"});
    return;
  }
  if (self.session || _stopping) {
    result(@{@"success" : @NO, @"error" : @"sessionActive"});
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
    result(@{@"success" : @NO, @"error" : @"invalidArguments"});
    return;
  }
  if (![NSFileManager.defaultManager isReadableFileAtPath:gamePath]) {
    result(@{@"success" : @NO, @"error" : @"gameUnreadable"});
    return;
  }
  NSString* loadError = [self loadCore];
  if (loadError) {
    result(@{@"success" : @NO, @"error" : loadError, @"detail" : self.loadDetail ?: @""});
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

  char error[512] = {0};
  UIView* render = (__bridge UIView*)api->create_render_view(error, sizeof error);
  if (!render) {
    result(@{@"success" : @NO, @"error" : @"renderViewFailed", @"detail" : @(error)});
    return;
  }
  XeniaSessionController* controller = [[XeniaSessionController alloc] init];
  controller.owner = self;
  controller.api = api;
  controller.renderView = render;
  controller.gameTitle = title;
  controller.modalPresentationStyle = UIModalPresentationFullScreen;
  self.session = controller;
  UIViewController* presenter = XeniaTopViewController();
  if (!presenter) {
    self.session = nil;
    api->release_render_view();
    result(@{@"success" : @NO, @"error" : @"noPresenter"});
    return;
  }

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
      if (!api->prepare(&configuration, kXeniaPrepareTimeoutMs, failure, sizeof failure)) {
        stage = @"prepareFailed";
      } else if (!api->validate_jit(failure, sizeof failure)) {
        stage = @"jitUnavailable";
      } else if (!api->boot(gamePath.fileSystemRepresentation, kind.unsignedIntValue,
                            kXeniaBootTimeoutMs, failure, sizeof failure)) {
        stage = @"bootFailed";
      }
      NSString* detail = @(failure);
      dispatch_async(dispatch_get_main_queue(), ^{
        if (stage) {
          [self teardownWithReason:stage detail:detail notify:NO];
          result(@{@"success" : @NO, @"error" : stage, @"detail" : detail});
        } else {
          result(@{@"success" : @YES});
          [self.channel invokeMethod:@"sessionEvent" arguments:@{@"event" : @"launched"}];
        }
      });
    });
  }];
}

- (void)deliverEvent:(NSString*)event transaction:(uint64_t)transaction message:(NSString*)message {
  if (transaction != _transaction || !self.session) return;  // late callback
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
  if (self.api && self.session && !_stopping) self.api->set_paused(_userPaused || _backgroundPaused);
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
  if (!self.api || !self.session || _stopping) return;
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
  XeniaSessionController* controller = self.session;
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

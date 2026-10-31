#import <achievement_translation/RBAchievementTranslation.h>
#import <objc/message.h>
#include <vector>
#import "Armsx2InternalBridgePlugin.h"
#import "Armsx2JitBridgePlugin.h"
#import "ARMSX2CoreABI.h"
#import "Armsx2RetroAchievementsMenu.h"
#import "Armsx2SessionMenu.h"
#include "NeoCheatStore.h"
#include "NeoUnifiedNativeImport.h"
#import "ARMSX2InGameLocalization.h"
#import "Armsx2TextureBridge.h"
#import "Armsx2TouchControls.h"
// Build 447: the Core's render view is a NeoExternalRenderHost of the
// external_display pod (docs/external-display-universal.md § 5, row ARMSX2).
#import <external_display/NeoExternalDisplayCoordinator.h>

#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <dlfcn.h>
#import <os/lock.h>
#include <cmath>

static NSString* const kARMSX2Channel = @"neostation/armsx2_internal";
static const uint32_t kARMSX2ExpectedABI = NEO_ARMSX2_ABI_VERSION;

static UIViewController* ARMSX2RootViewController(void) {
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


// Build 484: the touch controls (and the virtual stick) live in
// Armsx2TouchControls.mm as movable elements of the "ps2" layout.

// NEOSTATION_ARMSX2_EXTERNAL_DISPLAY_V1: the bridge's NeoExternalRenderHost.
// The render view is the view the Core created (`coreView`), the placeholder
// the game controller's root view, where the coordinator puts it back at
// index 0 (below the touch controls, which stay on the iPhone). The Core
// sized its surface for the iPhone and the bridge never resizes that view:
// the coordinator keeps its bounds and scale and maps it to the TV with a
// transform only. The adapter owns no window, screen, transform or observer.
@interface Armsx2ExternalRenderHost : NSObject <NeoExternalRenderHost>
/// YES while the core view is in the external window (set on the main
/// thread by the coordinator through externalDisplayDidChange:). The
/// controller's layout pass leaves the view alone while this is set.
@property(nonatomic, readonly) BOOL attached;
- (instancetype)initWithRenderView:(UIView*)render placeholder:(UIView*)placeholder;
@end

@implementation Armsx2ExternalRenderHost {
  // The Core owns its render view (`coreView` is assign, released by
  // release_render_view after the dismissal): the adapter never retains it.
  __weak UIView* _renderView;
  __weak UIView* _placeholderView;
}

- (instancetype)initWithRenderView:(UIView*)render placeholder:(UIView*)placeholder {
  self = [super init];
  if (self) {
    _renderView = render;
    _placeholderView = placeholder;
  }
  return self;
}

- (UIView*)renderView { return _renderView; }
- (UIView*)placeholderView { return _placeholderView; }
- (BOOL)fixedDrawable { return YES; }

// Main thread, after the coordinator moved the view to the TV (YES) or
// returned it to index 0 of the placeholder with its iPhone frame (NO).
- (void)externalDisplayDidChange:(BOOL)active {
  _attached = active;
  NSLog(@"[ARMSX2] External display active=%d (render view transform only, drawable fixed).", active);
}
@end

@interface Armsx2GameViewController : UIViewController
@property(nonatomic, assign) const NeoARMSX2API* api;
@property(nonatomic, assign) UIView* coreView;
/// The external-display adapter while the session is attached to the
/// coordinator, nil otherwise; its `attached` flag guards the layout pass.
@property(nonatomic, strong) Armsx2ExternalRenderHost* externalRenderHost;
@property(nonatomic, copy) dispatch_block_t closeHandler;
@property(nonatomic, copy) dispatch_block_t menuHandler;
@property(nonatomic, strong) Armsx2TouchControlsView* controlsView;
@property(nonatomic, strong) UIButton* menuButton;
@property(nonatomic, strong) UILabel* statusLabel;
/// The Touch Controls switch of the in-game Controls page.
@property(nonatomic, assign) BOOL touchControlsVisible;
// Build 484: controller policy, stored layout and on-screen editor.
@property(nonatomic, strong) NeoTouchControllerMonitor* controllerMonitor;
@property(nonatomic, assign) BOOL touchEditing;
@property(nonatomic, copy, nullable) NSString* touchGameKey;
@property(nonatomic, assign) BOOL menuReady;
@property(nonatomic, assign) float upscaleMultiplier;
@property(nonatomic, assign) uint32_t aspectRatio;
@property(nonatomic, assign) BOOL cheatsEnabled;
@property(nonatomic, assign) uint32_t saveStateMask;
@property(nonatomic, assign) BOOL closing;
@property(nonatomic, copy) NSString* uiLocale;
- (void)updateRuntimeMenuWithUpscale:(float)upscale
                              aspect:(uint32_t)aspect
                              cheats:(BOOL)cheats
                       saveStateMask:(uint32_t)mask;
- (void)showStatus:(NSString*)message;
- (void)resetInput;
- (void)applyTouchVisibility;
- (void)beginTouchLayoutEditing:(dispatch_block_t)completion;
@end

@implementation Armsx2GameViewController
- (instancetype)init {
  self = [super init];
  if (self) {
    self.modalPresentationStyle = UIModalPresentationFullScreen;
    self.modalTransitionStyle = UIModalTransitionStyleCrossDissolve;
    self.touchControlsVisible = YES;
    self.upscaleMultiplier = 1.0f;
    self.aspectRatio = 0;
  }
  return self;
}

- (void)dealloc {
  [self.controllerMonitor invalidate];
  [NSNotificationCenter.defaultCenter removeObserver:self];
}

- (NSString*)en:(NSString*)english fr:(NSString*)french {
  return ARMSX2LocalizedText(english, french, self.uiLocale);
}

- (void)loadView {
  UIView* root = [[UIView alloc] initWithFrame:UIScreen.mainScreen.bounds];
  root.backgroundColor = UIColor.blackColor;
  self.view = root;
  char error[512] = {};
  void* raw = self.api ? self.api->create_render_view(error, sizeof(error)) : NULL;
  if (raw) {
    UIView* render = (__bridge UIView*)raw;
    render.frame = root.bounds;
    render.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    [root addSubview:render];
    self.coreView = render;
  }

  // Build 484: the same controls as before, each one a movable element of
  // the "ps2" touch layout (Armsx2TouchControls.mm).
  self.controlsView = [[Armsx2TouchControlsView alloc] initWithLocale:self.uiLocale];
  self.controlsView.frame = root.bounds;
  self.controlsView.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
  self.controlsView.accessibilityIdentifier = @"armsx2-touch-controls";
  self.controlsView.gameKey = self.touchGameKey;
  [root addSubview:self.controlsView];

  __weak Armsx2GameViewController* weakSelf = self;
  self.controlsView.buttonChanged = ^(uint32_t button, BOOL pressed) {
    Armsx2GameViewController* strongSelf = weakSelf;
    if (strongSelf.api && strongSelf.api->set_button && button < 16) strongSelf.api->set_button(button, pressed ? 1 : 0);
  };
  self.controlsView.sticksChanged = ^(float leftX, float leftY, float rightX, float rightY) {
    Armsx2GameViewController* strongSelf = weakSelf;
    if (strongSelf.api && strongSelf.api->set_sticks) strongSelf.api->set_sticks(leftX, leftY, rightX, rightY);
  };
  self.controllerMonitor = [[NeoTouchControllerMonitor alloc] initWithChangeHandler:^(__unused BOOL connected) {
    [weakSelf applyTouchVisibility];
  }];
  [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(touchPreferenceChanged:)
      name:NeoTouchControllerPreferenceDidChangeNotification object:nil];

  // Match Dolphin's entry point: one hamburger opens the full session
  // navigator. There is deliberately no direct-close X and no contextual
  // settings button; Quit lives inside the session menu.
  self.menuButton = [UIButton buttonWithType:UIButtonTypeSystem];
  self.menuButton.translatesAutoresizingMaskIntoConstraints = NO;
  self.menuButton.tintColor = UIColor.whiteColor;
  self.menuButton.backgroundColor = [UIColor colorWithWhite:0 alpha:0.55];
  self.menuButton.layer.cornerRadius = 18;
  self.menuButton.accessibilityLabel = [self en:@"ARMSX2 game menu" fr:@"Menu du jeu ARMSX2"];
  self.menuButton.accessibilityIdentifier = @"armsx2-game-menu";
  [self.menuButton setImage:[UIImage systemImageNamed:@"line.3.horizontal"] forState:UIControlStateNormal];
  self.menuButton.showsMenuAsPrimaryAction = NO;
  [self.menuButton addTarget:self action:@selector(menuPressed) forControlEvents:UIControlEventTouchUpInside];
  [root addSubview:self.menuButton];

  self.statusLabel = [UILabel new];
  self.statusLabel.translatesAutoresizingMaskIntoConstraints = NO;
  self.statusLabel.textColor = UIColor.whiteColor;
  self.statusLabel.backgroundColor = [UIColor colorWithWhite:0 alpha:0.68];
  self.statusLabel.font = [UIFont systemFontOfSize:12 weight:UIFontWeightSemibold];
  self.statusLabel.textAlignment = NSTextAlignmentCenter;
  self.statusLabel.numberOfLines = 2;
  self.statusLabel.layer.cornerRadius = 8;
  self.statusLabel.clipsToBounds = YES;
  self.statusLabel.alpha = 0;
  [root addSubview:self.statusLabel];

  [NSLayoutConstraint activateConstraints:@[
    [self.menuButton.leadingAnchor constraintEqualToAnchor:root.safeAreaLayoutGuide.leadingAnchor constant:12],
    [self.menuButton.topAnchor constraintEqualToAnchor:root.safeAreaLayoutGuide.topAnchor constant:12],
    [self.menuButton.widthAnchor constraintEqualToConstant:44],
    [self.menuButton.heightAnchor constraintEqualToConstant:44],
    [self.statusLabel.centerXAnchor constraintEqualToAnchor:root.centerXAnchor],
    [self.statusLabel.topAnchor constraintEqualToAnchor:root.safeAreaLayoutGuide.topAnchor constant:14],
    [self.statusLabel.widthAnchor constraintLessThanOrEqualToAnchor:root.widthAnchor multiplier:0.62],
  ]];
  [self refreshMenu];
  [self applyTouchVisibility];
}

- (void)viewDidLayoutSubviews {
  [super viewDidLayoutSubviews];
  // While the coordinator shows the core view on the TV, that view is not a
  // subview of this controller and keeps the bounds, scale and transform the
  // coordinator gave it: only the iPhone layout sizes it. The touch controls
  // always follow the iPhone.
  if (!self.externalRenderHost.attached) self.coreView.frame = self.view.bounds;
  self.controlsView.frame = self.view.bounds;
}

- (void)setTouchGameKey:(NSString*)touchGameKey {
  _touchGameKey = [touchGameKey copy];
  self.controlsView.gameKey = touchGameKey;
}

- (void)touchPreferenceChanged:(NSNotification*)notification {
  NSString* console = notification.userInfo[@"console"];
  if (!console || [console isEqualToString:@"ps2"]) [self applyTouchVisibility];
}

// Build 484: the touch controls show when the Touch Controls switch is on
// and, while the PS2 preference allows it (default), no compatible
// controller is connected. Hiding releases every held control; the menu
// button is not part of the controls and stays available. The editor shows
// them whatever the controller or the switch.
- (void)applyTouchVisibility {
  if (!NSThread.isMainThread) {
    dispatch_async(dispatch_get_main_queue(), ^{ [self applyTouchVisibility]; });
    return;
  }
  if (!self.controlsView) return;
  const BOOL hidden = NeoTouchControlsShouldHide(@"ps2", self.controllerMonitor.connected, self.touchControlsVisible,
                                                 self.closing, self.touchEditing);
  if (hidden && !self.controlsView.hidden) [self resetInput];
  self.controlsView.hidden = hidden;
}

- (void)beginTouchLayoutEditing:(dispatch_block_t)completion {
  if (self.touchEditing || !self.controlsView || self.closing) {
    if (completion) completion();
    return;
  }
  self.touchEditing = YES;
  [self resetInput];
  self.controlsView.userInteractionEnabled = NO;
  self.controlsView.hidden = NO;
  NeoTouchLayoutEditor* editor = [[NeoTouchLayoutEditor alloc] initWithHost:self.controlsView
      layoutKey:NeoTouchLayoutKeyPlayStation2 gameKey:self.controlsView.gameKey title:self.title
      locale:self.uiLocale store:NeoTouchLayoutStore.sharedStore];
  editor.controllerConnected = self.controllerMonitor.connected;
  __weak Armsx2GameViewController* weakSelf = self;
  editor.finished = ^(__unused BOOL saved) {
    Armsx2GameViewController* strongSelf = weakSelf;
    if (!strongSelf) return;
    strongSelf.touchEditing = NO;
    [strongSelf.controlsView endEditingOverride];
    [strongSelf applyTouchVisibility];
    if (completion) completion();
  };
  [editor presentOverCanvas];
}

- (void)resetInput {
  // Visuals first (sticks back to the centre, buttons released), then every
  // ARMSX2 button up and both sticks neutral, as before.
  [self.controlsView releaseAllInput];
  if(self.api && self.api->set_button)
    for(uint32_t i=0;i<16;i++) self.api->set_button(i,0);
  if(self.api && self.api->set_sticks) self.api->set_sticks(0,0,0,0);
}
- (void)closePressed {
  if (self.closing) return;
  self.closing=YES;
  [self resetInput];
  if (self.closeHandler) self.closeHandler();
}
- (void)menuPressed {
  if (self.closing || !self.menuReady || self.touchEditing) return;
  [self resetInput];
  if (self.menuHandler) self.menuHandler();
}

- (void)refreshMenu {
  // The old contextual UIMenu is intentionally retired. The slider button
  // opens Armsx2SessionMenu, matching Dolphin's full navigation architecture.
  self.menuButton.menu = nil;
}
- (void)updateRuntimeMenuWithUpscale:(float)upscale
                              aspect:(uint32_t)aspect
                              cheats:(BOOL)cheats
                       saveStateMask:(uint32_t)mask {
  self.upscaleMultiplier=upscale;
  self.aspectRatio=aspect;
  self.cheatsEnabled=cheats;
  self.saveStateMask=mask;
  self.menuReady=YES;
  [self refreshMenu];
}

- (void)showStatus:(NSString*)message {
  if(message.length==0) return;
  self.statusLabel.text=[NSString stringWithFormat:@"  %@  ",message];
  [UIView animateWithDuration:0.15 animations:^{ self.statusLabel.alpha=1; }];
  __weak Armsx2GameViewController* weakSelf=self;
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW,(int64_t)(2.2*NSEC_PER_SEC)),dispatch_get_main_queue(),^{
    Armsx2GameViewController* strongSelf=weakSelf; if(!strongSelf) return;
    [UIView animateWithDuration:0.25 animations:^{ strongSelf.statusLabel.alpha=0; }];
  });
}
@end


@interface Armsx2InternalBridgePlugin ()
@property(nonatomic, strong) FlutterMethodChannel* channel;
@property(nonatomic, strong) Armsx2GameViewController* gameController;
@property(nonatomic, assign) void* coreHandle;
@property(nonatomic, assign) const NeoARMSX2API* api;
@property(nonatomic, assign) BOOL operationBusy;
@property(nonatomic, assign) BOOL stopInProgress;
@property(nonatomic, strong) NSURLSessionDownloadTask* shaderDownload;
@property(nonatomic, assign) uint64_t shaderDownloadGeneration;
@property(nonatomic, strong) UINavigationController* sessionMenu;
@property(nonatomic, assign) BOOL menuOpening;
@property(nonatomic, copy) NSString* activeDataDirectory;
// Build 485: HD texture packs (library methods, in-game page, boot choices).
@property(nonatomic, strong) Armsx2TextureBridge* textures;
@property(nonatomic, copy) NSString* activeGamePath;
@property(nonatomic, assign) uint32_t activeBootKind;
@property(nonatomic, weak) Armsx2GameViewController* achievementPrefetchOwner;
@property(nonatomic, assign) NSUInteger achievementPrefetchGameID;
@property(nonatomic, assign) BOOL achievementPrefetchPending;
@end

@implementation Armsx2InternalBridgePlugin {
  dispatch_queue_t _runtimeQueue;
}

+ (void)registerWithRegistrar:(NSObject<FlutterPluginRegistrar>*)registrar {
  // Build 484: the PS2 controls for the editor opened from the settings.
  Armsx2TouchControlsRegisterPreview();
  FlutterMethodChannel* channel = [FlutterMethodChannel
      methodChannelWithName:kARMSX2Channel
            binaryMessenger:registrar.messenger];
  Armsx2InternalBridgePlugin* instance = [Armsx2InternalBridgePlugin new];
  instance.channel = channel;
  __weak Armsx2InternalBridgePlugin* weakInstance = instance;
  instance.textures = [[Armsx2TextureBridge alloc] initWithChannel:channel sessionActive:^BOOL {
    Armsx2InternalBridgePlugin* plugin = weakInstance;
    return plugin && (plugin.operationBusy || plugin.gameController != nil);
  }];
  [registrar addMethodCallDelegate:instance channel:channel];
  [Armsx2JitBridgePlugin registerWithRegistrar:registrar];
}

- (instancetype)init {
  self = [super init];
  if (self) {
    _runtimeQueue = dispatch_queue_create(
        "com.neogamelab.neostation.armsx2.runtime",
        DISPATCH_QUEUE_SERIAL);
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(presentAchievementNotification:)
        name:@"ARMSX2RetroAchievementsNotification" object:nil];
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(prefetchAchievementSources:)
        name:@"ARMSX2RetroAchievementsStateChanged" object:nil];
  }
  return self;
}

// The pinned core owns award/authentication state; these public ObjC methods
// only copy presentation data. Resolve them dynamically because its C ABI hides
// the upstream ObjC symbols from direct linking.
- (NSArray<NSDictionary*>*)achievementSources {
  Class bridge = NSClassFromString(@"ARMSX2Bridge");
  SEL selector = NSSelectorFromString(@"retroAchievementsForCurrentGame");
  if (!bridge || ![bridge respondsToSelector:selector]) return @[];
  id rows = ((id (*)(id, SEL))objc_msgSend)(bridge, selector);
  return [rows isKindOfClass:NSArray.class] ? rows : @[];
}

- (void)prefetchAchievementSources:(NSNotification*)notification {
  if (!NSThread.isMainThread) {
    dispatch_async(dispatch_get_main_queue(), ^{ [self prefetchAchievementSources:notification]; });
    return;
  }
  Armsx2GameViewController* owner = self.gameController;
  if (!owner || self.stopInProgress || owner.closing || self.achievementPrefetchPending) return;
  // The core posts this event when the game's state becomes available, even
  // when its optional summary toast is disabled. Rich presence also posts it;
  // copy the full list only once per loaded game and controller.
  self.achievementPrefetchPending = YES;
  __weak Armsx2InternalBridgePlugin* weakSelf = self;
  __weak Armsx2GameViewController* weakOwner = owner;
  [self readRetroAchievementsForController:owner completion:^(NSDictionary<NSString*, id>* state) {
    Armsx2InternalBridgePlugin* active = weakSelf;
    active.achievementPrefetchPending = NO;
    if (!active || !weakOwner || active.gameController != weakOwner || active.stopInProgress || weakOwner.closing) return;
    NSUInteger gameID = [state[@"gameId"] unsignedIntegerValue];
    if (![state[@"hasActiveGame"] boolValue] || ![state[@"hasAchievements"] boolValue] || gameID == 0) {
      active.achievementPrefetchOwner = nil;
      active.achievementPrefetchGameID = 0;
      return;
    }
    if (active.achievementPrefetchOwner == weakOwner && active.achievementPrefetchGameID == gameID) return;
    NSArray<NSDictionary*>* sources = [active achievementSources];
    if (sources.count == 0) return;
    RBAchievementPrefetch(sources);
    active.achievementPrefetchOwner = weakOwner;
    active.achievementPrefetchGameID = gameID;
  }];
}

- (void)presentAchievementNotification:(NSNotification*)notification {
  if (!NSThread.isMainThread) {
    dispatch_async(dispatch_get_main_queue(), ^{ [self presentAchievementNotification:notification]; });
    return;
  }
  Armsx2GameViewController* owner = self.gameController;
  if (!owner || self.stopInProgress || owner.closing) return;
  Class bridge = NSClassFromString(@"ARMSX2Bridge");
  SEL consume = NSSelectorFromString(@"consumePendingRetroAchievementsNotification");
  if (!bridge || ![bridge respondsToSelector:consume]) return;
  id toast = ((id (*)(id, SEL))objc_msgSend)(bridge, consume);
  if (!toast || ![toast respondsToSelector:@selector(title)] ||
      ![toast respondsToSelector:NSSelectorFromString(@"message")]) return;
  NSString* title = [toast valueForKey:@"title"] ?: @"";
  NSString* message = [toast valueForKey:@"message"] ?: @"";
  NSArray<NSDictionary*>* sources = [self achievementSources];
  RBAchievementPrefetch(sources);
  NSMutableArray<NSDictionary*>* matches = [NSMutableArray array];
  for (id value in sources) {
    if (![value isKindOfClass:NSDictionary.class]) continue;
    NSDictionary* row = value;
    NSString* rawTitle = [row[@"title"] isKindOfClass:NSString.class] ? row[@"title"] : @"";
    BOOL unofficial = [row[@"category"] integerValue] == 2 &&
        [title isEqual:[rawTitle stringByAppendingString:@" (Unofficial)"]];
    if (([rawTitle isEqual:title] || unofficial) && [row[@"description"] isEqual:message]) [matches addObject:row];
  }
  // No guessed ID: a summary/game title or an ambiguous toast stays original.
  NSInteger achievementID = matches.count == 1 ? [matches.firstObject[@"id"] integerValue] : 0;
  if (matches.count == 0) { [owner showStatus:[NSString stringWithFormat:@"%@\n%@", title, message]]; return; }
  NSTimeInterval duration = [toast respondsToSelector:NSSelectorFromString(@"duration")]
      ? [[toast valueForKey:@"duration"] doubleValue] : 4.0;
  __weak Armsx2InternalBridgePlugin* weakSelf = self;
  __weak Armsx2GameViewController* weakOwner = owner;
  NSString* sourceTitle = achievementID > 0 ? matches.firstObject[@"title"] : title;
  NSString* marker = achievementID > 0 && ![sourceTitle isEqual:title] ? @"(Unofficial)" : @"";
  RBAchievementPresent(owner, achievementID, sourceTitle, message, marker, duration, 1, ^UIView* {
        UIViewController* controller = weakOwner;
        NeoExternalDisplayCoordinator* display = NeoExternalDisplayCoordinator.shared;
        if (controller && display.renderHost.placeholderView == controller.view && !display.window.hidden &&
            display.renderHost.renderView.window == display.window && display.window != nil)
          return display.window.rootViewController.view;
        return controller.view;
      }, ^BOOL {
    Armsx2InternalBridgePlugin* active = weakSelf;
    return active && weakOwner && active.gameController == weakOwner && !active.stopInProgress && !weakOwner.closing;
  });
}

- (void)dealloc {
  [NSNotificationCenter.defaultCenter removeObserver:self];
}

- (NSString*)corePath {
  NSString* frameworks = NSBundle.mainBundle.privateFrameworksPath ?: @"";
  return [frameworks stringByAppendingPathComponent:@"ARMSX2Core.framework/ARMSX2Core"];
}

- (NSString*)resourcePath {
  NSString* frameworkPath = [[self corePath] stringByDeletingLastPathComponent];
  NSBundle* bundle = [NSBundle bundleWithPath:frameworkPath];
  return bundle.resourcePath ?: frameworkPath;
}

- (BOOL)loadCore:(NSString**)error {
  const BOOL coreAlreadyLoaded = self.api != NULL;

  // iOS 26+ requires a fresh nonce-bound debugger proof for EVERY JIT
  // transaction, not only the first dlopen. ARMSX2Core intentionally remains
  // process-lifetime; therefore the second and later launches enter here with
  // self.api already populated. Returning before this handshake left the new
  // StikJIT session attached but unproven and broke Core re-initialization.
  if (@available(iOS 26.0, *)) {
    if (!ARMSX2JitConfirmCoreLoadHandoff()) {
      if (error) {
        *error = coreAlreadyLoaded
            ? @"ARMSX2 debugger nonce proof failed at the Core reuse boundary."
            : @"ARMSX2 debugger nonce proof failed at the Core load boundary.";
      }
      return NO;
    }
  }

  if (coreAlreadyLoaded) {
    NSLog(@"[ARMSX2] Reusing process-lifetime Core after fresh JIT nonce proof.");
    return YES;
  }
  NSString* path = [self corePath];
  if (![NSFileManager.defaultManager isReadableFileAtPath:path]) {
    if (error) *error = [NSString stringWithFormat:@"Embedded ARMSX2 Core is missing: %@", path];
    return NO;
  }
  dlerror();
  void* handle = dlopen(path.fileSystemRepresentation, RTLD_NOW | RTLD_LOCAL);
  if (!handle) {
    const char* detail = dlerror();
    if (error) *error = [NSString stringWithFormat:@"ARMSX2 Core dlopen failed: %s", detail ?: "unknown"];
    return NO;
  }
  auto getAPI = reinterpret_cast<NeoARMSX2GetAPI>(dlsym(handle, "NeoARMSX2_GetAPI"));
  const NeoARMSX2API* api = getAPI ? getAPI(kARMSX2ExpectedABI) : NULL;
  if (!api || api->version != kARMSX2ExpectedABI ||
      api->size < sizeof(NeoARMSX2API) || !api->prepare ||
      !api->request_jit_detach || !api->validate_jit || !api->boot ||
      !api->set_button || !api->set_sticks ||
      !api->get_upscale_multiplier || !api->get_aspect_ratio ||
      !api->get_cheats_enabled || !api->set_upscale_multiplier ||
      !api->set_aspect_ratio || !api->set_cheats_enabled ||
      !api->reload_cheats || !api->get_available_patches_json ||
      !api->set_patch_state || !api->has_save_state ||
      !api->save_state || !api->load_state ||
      !api->get_retroachievements_state_json ||
      !api->set_retroachievements_option ||
      !api->login_retroachievements || !api->logout_retroachievements ||
      !api->get_graphics_hacks_json || !api->set_graphics_hack ||
      !api->get_graphics_assets_json || !api->set_shader_preset ||
      !api->set_performance_overlay || !api->install_shader_pack ||
      !api->get_blending_accuracy_json || !api->set_blending_accuracy ||
      !api->get_texture_replacements_json || !api->set_texture_replacements ||
      !api->reload_texture_replacements || !api->set_texture_boot_preferences ||
      !api->expand_texture_archive) {
    if (error) *error = @"Embedded ARMSX2 Core ABI is incompatible.";
    return NO;
  }
  self.coreHandle = handle; // Intentionally process-lifetime; never dlclose Objective-C classes.
  self.api = api;
  return YES;
}

// NEOSTATION_ARMSX2_EXTERNAL_DISPLAY_V1
// Attaches the Core's render view to the external display coordinator once
// the game controller is presented and the Core booted: the Core sized its
// surface for the iPhone before the view may move, and a launch that fails
// never had a host to detach. Without a TV the coordinator only remembers
// the host and moves the view when a screen comes. Main thread (the
// coordinator asserts it); a caller on another queue is hopped there.
- (void)attachExternalDisplayForController:(Armsx2GameViewController*)controller {
  if (!NSThread.isMainThread) {
    dispatch_async(dispatch_get_main_queue(), ^{ [self attachExternalDisplayForController:controller]; });
    return;
  }
  if (!controller || !controller.coreView || controller != self.gameController || self.stopInProgress) return;
  [self detachExternalDisplayFromController:controller];
  Armsx2ExternalRenderHost* host =
      [[Armsx2ExternalRenderHost alloc] initWithRenderView:controller.coreView placeholder:controller.view];
  controller.externalRenderHost = host;
  [NeoExternalDisplayCoordinator.shared attachRenderHost:host];
}

// Returns the Core's render view to index 0 of the game view on the iPhone,
// with its iPhone frame and scale, before the Core stops and before the game
// view is dismissed. Harmless when nothing is attached. Main thread only.
- (void)detachExternalDisplayFromController:(Armsx2GameViewController*)controller {
  Armsx2ExternalRenderHost* host = controller.externalRenderHost;
  if (!host) return;
  controller.externalRenderHost = nil;
  [NeoExternalDisplayCoordinator.shared detachRenderHost:host];
}

- (void)dismissGameControllerWithCompletion:(dispatch_block_t)completion {
  NSAssert(NSThread.isMainThread, @"ARMSX2 UIKit teardown must run on main");
  Armsx2GameViewController* controller = self.gameController;
  self.gameController = nil;
  self.sessionMenu = nil;
  self.menuOpening = NO;
  // Every teardown path ends here: the render view is back on the iPhone
  // before the presentation is dismissed and before the Core releases it.
  [self detachExternalDisplayFromController:controller];
  if (controller) {
    controller.menuHandler = nil;
    [controller resetInput];
  }

  __weak Armsx2InternalBridgePlugin* weakSelf = self;
  void (^releaseView)(void) = ^{
    Armsx2InternalBridgePlugin* strongSelf = weakSelf;
    if (strongSelf.api && strongSelf.api->release_render_view)
      strongSelf.api->release_render_view();
    controller.coreView = nil;
    if (completion) completion();
  };

  // Dismiss from the presenter so any child settings/account controller is
  // removed with the game surface. Only release g_gameRenderView after UIKit
  // confirms that the presentation hierarchy no longer owns it.
  UIViewController* presenter = controller.presentingViewController;
  if (presenter) {
    [presenter dismissViewControllerAnimated:NO completion:releaseView];
  } else if (controller.presentedViewController) {
    [controller dismissViewControllerAnimated:NO completion:releaseView];
  } else {
    releaseView();
  }
}

- (void)dismissGameController {
  [self dismissGameControllerWithCompletion:nil];
}

- (void)stopActiveSessionWithCompletion:(void (^)(BOOL success, NSString* message))completion {
  // NEOSTATION_ARMSX2_EXTERNAL_DISPLAY_V1: the Core's render view returns to
  // index 0 of the game view on the iPhone BEFORE the Core stops (the
  // external display contract); the detach belongs to the main thread, so
  // the stop hops there first and queues the Core stop from there.
  if (!NSThread.isMainThread) {
    dispatch_async(dispatch_get_main_queue(), ^{ [self stopActiveSessionWithCompletion:completion]; });
    return;
  }
  [self detachExternalDisplayFromController:self.gameController];
  dispatch_async(_runtimeQueue, ^{
    if (self.stopInProgress) {
      dispatch_async(dispatch_get_main_queue(), ^{
        if (completion) completion(NO, @"ARMSX2 shutdown is already in progress.");
      });
      return;
    }
    self.stopInProgress = YES;
    ++self.shaderDownloadGeneration;
    [self.shaderDownload cancel];
    self.shaderDownload = nil;
    self.operationBusy = YES;
    const BOOL hadPresentedSession = self.gameController != nil;
    BOOL ok = YES;
    NSString* message = @"";
    if (self.api) {
      char error[512] = {};
      self.api->request_stop();
      ok = self.api->shutdown(30000, error, sizeof(error)) != 0;
      if (!ok && error[0]) message = [NSString stringWithUTF8String:error] ?: @"";
    }
    ARMSX2JitAbortTransaction();
    dispatch_async(dispatch_get_main_queue(), ^{
      if (!ok) {
        self.operationBusy = NO;
        self.stopInProgress = NO;
        self.gameController.closing = NO;
        [self.gameController showStatus:message.length ? message :
            @"ARMSX2 shutdown did not complete."];
        // The Core still runs and the session goes on: the game returns to
        // the TV as well.
        [self attachExternalDisplayForController:self.gameController];
        if (completion) completion(NO, message);
        return;
      }
      [self dismissGameControllerWithCompletion:^{
        self.operationBusy = NO;
        self.stopInProgress = NO;
        if (hadPresentedSession) {
          [self.channel invokeMethod:@"sessionEnded" arguments:@{
            @"reason": @"user_exit",
            @"success": @YES,
          }];
        }
        if (completion) completion(YES, message);
      }];
    });
  });
}

- (void)failTransaction:(NSString*)message result:(FlutterResult)result {
  if (self.api) {
    char ignored[256] = {};
    self.api->request_stop();
    self.api->shutdown(30000, ignored, sizeof(ignored));
  }
  ARMSX2JitAbortTransaction();
  self.operationBusy = NO;
  dispatch_async(dispatch_get_main_queue(), ^{
    [self dismissGameController];
    result(@{@"success": @NO, @"message": message ?: @"ARMSX2 launch failed."});
  });
}

- (void)publishMenuStateForController:(Armsx2GameViewController*)controller
                                   message:(NSString*)message {
  if (!self.api || !controller) return;
  const float upscale = self.api->get_upscale_multiplier();
  const uint32_t aspect = self.api->get_aspect_ratio();
  const BOOL cheats = self.api->get_cheats_enabled() != 0;
  uint32_t mask = 0;
  for (uint32_t slot = 1; slot <= 5; slot++) {
    if (self.api->has_save_state(slot)) mask |= (1u << (slot - 1));
  }
  dispatch_async(dispatch_get_main_queue(), ^{
    if (self.gameController != controller) return;
    [controller updateRuntimeMenuWithUpscale:upscale
                                      aspect:aspect
                                      cheats:cheats
                               saveStateMask:mask];
    if (message.length) [controller showStatus:message];
  });
}

- (NSDictionary<NSString*, id>*)decodeRetroAchievementsState {
  if (!self.api || !self.api->get_retroachievements_state_json) return nil;
  char json[32768] = {};
  if (!self.api->get_retroachievements_state_json(json, sizeof(json))) return nil;
  NSData* data = [NSData dataWithBytes:json length:strlen(json)];
  id decoded = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
  return [decoded isKindOfClass:NSDictionary.class] ? decoded : nil;
}

- (void)readRetroAchievementsForController:(Armsx2GameViewController*)controller
                                completion:(void (^)(NSDictionary<NSString*, id>* state))completion {
  dispatch_async(_runtimeQueue, ^{
    NSDictionary* state = self.gameController == controller ? [self decodeRetroAchievementsState] : nil;
    dispatch_async(dispatch_get_main_queue(), ^{ if (completion) completion(state); });
  });
}

- (void)performRetroAchievementsCommand:(NSString*)command
                                  value:(id)value
                             controller:(Armsx2GameViewController*)controller
                             completion:(void (^)(BOOL success, NSString* message))completion {
  dispatch_async(_runtimeQueue, ^{
    if (!self.api || self.gameController != controller) {
      dispatch_async(dispatch_get_main_queue(), ^{
        if (completion) completion(NO, @"ARMSX2 session is no longer active.");
      });
      return;
    }

    char error[1024] = {};
    BOOL ok = NO;
    NSString* success = @"";
    uint32_t option = 0;
    if ([command isEqualToString:@"enabled"]) option = NEO_ARMSX2_RA_ENABLED;
    else if ([command isEqualToString:@"hardcore"]) option = NEO_ARMSX2_RA_HARDCORE;
    else if ([command isEqualToString:@"notifications"]) option = NEO_ARMSX2_RA_NOTIFICATIONS;
    else if ([command isEqualToString:@"leaderboards"]) option = NEO_ARMSX2_RA_LEADERBOARDS;
    else if ([command isEqualToString:@"overlays"]) option = NEO_ARMSX2_RA_OVERLAYS;

    if (option) {
      ok = self.api->set_retroachievements_option(option, [value boolValue] ? 1 : 0,
                                                   5000, error, sizeof(error)) != 0;
      success = [controller en:@"RetroAchievements setting updated."
                            fr:@"Paramètre RetroAchievements mis à jour."];
    } else if ([command isEqualToString:@"login"] && [value isKindOfClass:NSDictionary.class]) {
      NSString* username = [value[@"username"] isKindOfClass:NSString.class] ? value[@"username"] : @"";
      NSString* password = [value[@"password"] isKindOfClass:NSString.class] ? value[@"password"] : @"";
      ok = self.api->login_retroachievements(username.UTF8String, password.UTF8String,
                                              30000, error, sizeof(error)) != 0;
      success = [controller en:@"RetroAchievements account linked."
                            fr:@"Compte RetroAchievements lié."];
    } else if ([command isEqualToString:@"logout"]) {
      ok = self.api->logout_retroachievements(5000, error, sizeof(error)) != 0;
      success = [controller en:@"RetroAchievements account unlinked."
                            fr:@"Compte RetroAchievements déconnecté."];
    }

    NSString* message = ok ? success :
        (error[0] ? [NSString stringWithUTF8String:error] : @"RetroAchievements operation failed.");
    dispatch_async(dispatch_get_main_queue(), ^{
      if (completion) completion(ok, message ?: @"");
    });
  });
}

- (void)readGraphicsHacksForController:(Armsx2GameViewController*)controller
                              completion:(void (^)(NSDictionary<NSString*, id>* state))completion {
  dispatch_async(_runtimeQueue, ^{
    NSDictionary* state=nil;
    if (self.api && self.gameController==controller && !self.stopInProgress) {
      char json[65536] = {};
      if (self.api->get_graphics_hacks_json(json,sizeof(json))) {
        NSData* data=[NSData dataWithBytes:json length:strlen(json)];
        id decoded=[NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
        if ([decoded isKindOfClass:NSDictionary.class]) state=decoded;
      }
    }
    dispatch_async(dispatch_get_main_queue(), ^{ if (completion) completion(state); });
  });
}

- (void)performGraphicsHack:(NSString*)key
                      value:(NSInteger)value
                 controller:(Armsx2GameViewController*)controller
                 completion:(void (^)(BOOL success, NSString* message))completion {
  dispatch_async(_runtimeQueue, ^{
    if (!self.api || self.gameController!=controller || self.stopInProgress) {
      dispatch_async(dispatch_get_main_queue(), ^{
        if (completion) completion(NO,@"ARMSX2 session is no longer active.");
      });
      return;
    }
    char error[1024] = {};
    BOOL ok=self.api->set_graphics_hack(key.UTF8String,(int)value,error,sizeof(error))!=0;
    NSString* message=ok
        ? [controller en:@"Graphics hack updated for this game."
                      fr:@"Hack graphique mis à jour pour ce jeu."]
        : (error[0] ? [NSString stringWithUTF8String:error] : @"Graphics hack update failed.");
    dispatch_async(dispatch_get_main_queue(), ^{
      if (completion) completion(ok,message ?: @"");
    });
  });
}

- (void)readAvailablePatchesForController:(Armsx2GameViewController*)controller
                                  completion:(void (^)(NSDictionary<NSString*, id>* state))completion {
  dispatch_async(_runtimeQueue, ^{
    NSDictionary* state=nil;
    if (self.api && self.gameController==controller && !self.stopInProgress) {
      char json[262144] = {};
      if (self.api->get_available_patches_json(json,sizeof(json))) {
        NSData* data=[NSData dataWithBytes:json length:strlen(json)];
        id decoded=[NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
        if ([decoded isKindOfClass:NSDictionary.class]) state=decoded;
      }
    }
    dispatch_async(dispatch_get_main_queue(), ^{ if (completion) completion(state); });
  });
}

- (void)performPatchCommand:(NSString*)name
                      value:(NSInteger)value
                 controller:(Armsx2GameViewController*)controller
                 completion:(void (^)(BOOL success, NSString* message))completion {
  dispatch_async(_runtimeQueue, ^{
    if (!self.api || self.gameController!=controller || self.stopInProgress) {
      dispatch_async(dispatch_get_main_queue(), ^{
        if (completion) completion(NO,@"ARMSX2 session is no longer active.");
      });
      return;
    }
    char error[1024] = {};
    BOOL ok=self.api->set_patch_state(name.UTF8String,(int)value,error,sizeof(error))!=0;
    NSString* message=ok
        ? [controller en:@"Patch setting updated for this game."
                      fr:@"Réglage du patch mis à jour pour ce jeu."]
        : (error[0] ? [NSString stringWithUTF8String:error] : @"Patch update failed.");
    dispatch_async(dispatch_get_main_queue(), ^{
      if (completion) completion(ok,message ?: @"");
    });
  });
}

- (void)readSessionSnapshotForController:(Armsx2GameViewController*)controller
                                   completion:(void (^)(NSDictionary<NSString*, id>* snapshot))completion {
  dispatch_async(_runtimeQueue, ^{
    if (!self.api || self.gameController != controller || self.stopInProgress) {
      dispatch_async(dispatch_get_main_queue(), ^{ if (completion) completion(nil); });
      return;
    }
    const float upscale = self.api->get_upscale_multiplier();
    const uint32_t aspect = self.api->get_aspect_ratio();
    const BOOL cheats = self.api->get_cheats_enabled() != 0;
    uint32_t mask = 0;
    for (uint32_t slot = 1; slot <= 5; slot++)
      if (self.api->has_save_state(slot)) mask |= (1u << (slot - 1));
    std::vector<char> assetJSON(2 * 1024 * 1024);
    NSDictionary* assets = nil;
    if (self.api->get_graphics_assets_json(assetJSON.data(),assetJSON.size())) {
      NSData* data = [[NSString stringWithUTF8String:assetJSON.data()] dataUsingEncoding:NSUTF8StringEncoding];
      id decoded = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
      if ([decoded isKindOfClass:NSDictionary.class]) assets = decoded;
    }
    // ABI 7: blending accuracy layers of the running game (Build 482).
    NSDictionary* blending = nil;
    char blendingJSON[2048] = {};
    if (self.api->get_blending_accuracy_json(blendingJSON, sizeof(blendingJSON))) {
      NSData* data = [NSData dataWithBytes:blendingJSON length:strlen(blendingJSON)];
      id decoded = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
      if ([decoded isKindOfClass:NSDictionary.class]) blending = decoded;
    }
    dispatch_async(dispatch_get_main_queue(), ^{
      if (self.gameController != controller || self.stopInProgress) {
        if (completion) completion(nil);
        return;
      }
      if (completion) completion(@{
        @"upscale": @(upscale),
        @"aspect": @(aspect),
        @"cheats": @(cheats),
        @"saveStateMask": @(mask),
        @"touch": @(controller.touchControlsVisible),
        @"touchHideWithController": @(NeoTouchHidesControlsWithController(@"ps2")),
        @"touchLayoutEditable": @YES,
        @"graphicsAssets": assets ?: @{},
        @"blending": blending ?: @{},
      });
    });
  });
}

- (void)downloadShaderPackForController:(Armsx2GameViewController*)controller
                              completion:(void (^)(BOOL, NSString*))completion {
  dispatch_async(_runtimeQueue, ^{
    if (!self.api || self.gameController != controller || self.stopInProgress || self.shaderDownload) {
      dispatch_async(dispatch_get_main_queue(), ^{ if (completion) completion(NO,@"ARMSX2 shader download is unavailable."); });
      return;
    }
    // Same official RetroArch pack endpoint used by ARMSX2 iOS 2.6.
    NSURL* url=[NSURL URLWithString:@"https://buildbot.libretro.com/assets/frontend/shaders_slang.zip"];
    NSURLRequest* request=[NSURLRequest requestWithURL:url cachePolicy:NSURLRequestReloadIgnoringLocalCacheData timeoutInterval:240];
    const uint64_t generation=++self.shaderDownloadGeneration;
    self.shaderDownload=[NSURLSession.sharedSession downloadTaskWithRequest:request
        completionHandler:^(NSURL* temporary, NSURLResponse* response, NSError* failure) {
      // NSURLSession removes its temporary file after this callback returns.
      // Move it before handing extraction to the background runtime queue.
      NSString* staged=[NSTemporaryDirectory() stringByAppendingPathComponent:
          [NSString stringWithFormat:@"armsx2-shaders-%@.zip",NSUUID.UUID.UUIDString]];
      NSHTTPURLResponse* http=[response isKindOfClass:NSHTTPURLResponse.class] ? (id)response : nil;
      NSNumber* bytes=nil;
      [temporary getResourceValue:&bytes forKey:NSURLFileSizeKey error:nil];
      NSError* diskError=nil;
      BOOL downloaded=!failure && http.statusCode==200 && temporary && bytes.unsignedLongLongValue>0 &&
          bytes.unsignedLongLongValue<=128ULL*1024*1024 &&
          [NSFileManager.defaultManager moveItemAtPath:temporary.path toPath:staged error:&diskError];
      dispatch_async(self->_runtimeQueue, ^{
        if (self.shaderDownloadGeneration==generation) self.shaderDownload=nil;
        char error[2048]={};
        BOOL active=self.shaderDownloadGeneration==generation && self.api && self.gameController==controller && !self.stopInProgress;
        BOOL ok=downloaded && active && self.api->install_shader_pack(staged.UTF8String,error,sizeof(error));
        [NSFileManager.defaultManager removeItemAtPath:staged error:nil];
        NSString* message=ok ? [controller en:@"Shader pack installed." fr:@"Pack de shaders installé."] :
            (error[0] ? [NSString stringWithUTF8String:error] :
             (failure.localizedDescription ?: diskError.localizedDescription ?: @"ARMSX2 shader download failed or session ended."));
        dispatch_async(dispatch_get_main_queue(), ^{ if (completion) completion(ok,message); });
      });
    }];
    [self.shaderDownload resume];
  });
}

- (void)performGameCommand:(NSString*)command
                     value:(id)value
                controller:(Armsx2GameViewController*)controller
                completion:(void (^)(BOOL success, NSString* message))completion {
  if ([command isEqualToString:@"touch"]) {
    dispatch_async(dispatch_get_main_queue(), ^{
      if (self.gameController != controller || self.stopInProgress) {
        if (completion) completion(NO, @"ARMSX2 session is no longer active.");
        return;
      }
      controller.touchControlsVisible = [value boolValue];
      if (!controller.touchControlsVisible) [controller resetInput];
      [controller applyTouchVisibility];
      if (completion) completion(YES,
          [controller en:@"Touch controls updated." fr:@"Commandes tactiles mises à jour."]);
    });
    return;
  }

  // Build 484: "Hide touch controls when a controller is connected" (PS2).
  if ([command isEqualToString:@"touchHideWithController"]) {
    dispatch_async(dispatch_get_main_queue(), ^{
      if (self.gameController != controller || self.stopInProgress) {
        if (completion) completion(NO, @"ARMSX2 session is no longer active.");
        return;
      }
      NeoTouchSetHidesControlsWithController(@"ps2", [value boolValue]);
      [controller applyTouchVisibility];
      if (completion) completion(YES, @"");
    });
    return;
  }

  // Build 484: the touch-controls editor replaces the menu; the game stays
  // paused until the editor closes.
  if ([command isEqualToString:@"editTouchLayout"]) {
    dispatch_async(dispatch_get_main_queue(), ^{
      if (self.gameController != controller || self.stopInProgress || !self.sessionMenu || self.menuOpening) {
        if (completion) completion(NO, @"ARMSX2 session is no longer active.");
        return;
      }
      if (completion) completion(YES, @"");
      [self openTouchEditorForController:controller];
    });
    return;
  }

  if ([command isEqualToString:@"downloadShaders"]) {
    [self downloadShaderPackForController:controller completion:completion];
    return;
  }
  dispatch_async(_runtimeQueue, ^{
    if (!self.api || self.gameController != controller || self.stopInProgress) {
      dispatch_async(dispatch_get_main_queue(), ^{
        if (completion) completion(NO, @"ARMSX2 session is no longer active.");
      });
      return;
    }
    char error[1024] = {};
    BOOL ok = NO;
    NSString* success = @"";

    if ([command isEqualToString:@"upscale"]) {
      ok = self.api->set_upscale_multiplier([value floatValue], error, sizeof(error)) != 0;
      NSString* format = [controller en:@"Internal resolution: %.0f×"
                                      fr:@"Résolution interne : %.0f×"];
      success = [NSString stringWithFormat:format, [value floatValue]];
    } else if ([command isEqualToString:@"aspect"]) {
      ok = self.api->set_aspect_ratio([value unsignedIntValue], error, sizeof(error)) != 0;
      success = [controller en:@"Screen format updated." fr:@"Format d’écran mis à jour."];
    } else if ([command isEqualToString:@"shader"]) {
      ok = [value isKindOfClass:NSString.class] && self.api->set_shader_preset([value UTF8String], error, sizeof(error));
      success = [controller en:@"Shader selection saved for this game." fr:@"Shader enregistré pour ce jeu."];
    } else if ([command isEqualToString:@"overlay"]) {
      ok = self.api->set_performance_overlay([value unsignedIntValue], error, sizeof(error)) != 0;
      success = [controller en:@"Performance overlay updated for this game." fr:@"Overlay de performances mis à jour pour ce jeu."];
    } else if ([command isEqualToString:@"blending"]) {
      // This game's INI: -1 removes the game's choice (default + GameDB apply again).
      const int level = [value isKindOfClass:NSNumber.class] ? [value intValue] : NEO_ARMSX2_BLENDING_INHERIT - 1;
      ok = self.api->set_blending_accuracy(NEO_ARMSX2_BLENDING_SCOPE_GAME, level, error, sizeof(error)) != 0;
      success = level == NEO_ARMSX2_BLENDING_INHERIT
          ? [controller en:@"Blending accuracy follows the default for all PS2 games again."
                        fr:@"La précision du blending suit de nouveau la valeur par défaut des jeux PS2."]
          : [controller en:@"Blending accuracy updated for this game."
                        fr:@"Précision du blending mise à jour pour ce jeu."];
    } else if ([command isEqualToString:@"blendingDefault"]) {
      // PCSX2.ini: the default every PS2 game without its own choice follows.
      const int level = [value isKindOfClass:NSNumber.class] ? [value intValue] : NEO_ARMSX2_BLENDING_INHERIT - 1;
      ok = self.api->set_blending_accuracy(NEO_ARMSX2_BLENDING_SCOPE_DEFAULT, level, error, sizeof(error)) != 0;
      success = [controller en:@"Default blending accuracy updated for all PS2 games."
                            fr:@"Précision du blending par défaut mise à jour pour tous les jeux PS2."];
    } else if ([command isEqualToString:@"cheats"]) {
      ok = self.api->set_cheats_enabled([value boolValue] ? 1 : 0, error, sizeof(error)) != 0;
      success = [value boolValue]
          ? [controller en:@"Cheats enabled." fr:@"Cheats activés."]
          : [controller en:@"Cheats disabled." fr:@"Cheats désactivés."];
    } else if ([command isEqualToString:@"reloadCheats"]) {
      ok = self.api->reload_cheats(error, sizeof(error)) != 0;
      success = [controller en:@"Cheats and patches reloaded." fr:@"Cheats et patches rechargés."];
    } else if ([command isEqualToString:@"saveState"]) {
      const uint32_t slot = [value unsignedIntValue];
      ok = self.api->save_state(slot, 60000, error, sizeof(error)) != 0;
      NSString* format = [controller en:@"State saved in slot %u."
                                      fr:@"État sauvegardé dans le slot %u."];
      success = [NSString stringWithFormat:format, slot];
    } else if ([command isEqualToString:@"loadState"]) {
      const uint32_t slot = [value unsignedIntValue];
      ok = self.api->load_state(slot, 60000, error, sizeof(error)) != 0;
      NSString* format = [controller en:@"State loaded from slot %u."
                                      fr:@"État chargé depuis le slot %u."];
      success = [NSString stringWithFormat:format, slot];
    }

    NSString* message = ok ? success :
        (error[0] ? [NSString stringWithUTF8String:error] : @"ARMSX2 command failed.");
    [self publishMenuStateForController:controller message:message ?: @""];
    dispatch_async(dispatch_get_main_queue(), ^{
      if (completion) completion(ok, message ?: @"");
    });
  });
}

- (void)openTouchEditorForController:(Armsx2GameViewController*)controller {
  UINavigationController* navigation = self.sessionMenu;
  if (!navigation || self.menuOpening) return;
  self.menuOpening = YES;
  __weak Armsx2InternalBridgePlugin* weakSelf = self;
  [navigation dismissViewControllerAnimated:YES completion:^{
    Armsx2InternalBridgePlugin* bridge = weakSelf;
    if (!bridge) return;
    bridge.sessionMenu = nil;
    bridge.menuOpening = NO;
    if (bridge.gameController != controller || bridge.stopInProgress) return;
    NSLog(@"[ARMSX2] Touch controls editor opened; the game stays paused.");
    [controller beginTouchLayoutEditing:^{
      if (bridge.gameController != controller || bridge.stopInProgress) return;
      controller.controlsView.userInteractionEnabled = YES;
      [controller applyTouchVisibility];
      NSLog(@"[ARMSX2] Touch controls editor closed; the game resumes.");
      dispatch_async(bridge->_runtimeQueue, ^{
        if (bridge.api && bridge.gameController == controller && !bridge.stopInProgress)
          bridge.api->set_paused(0);
      });
    }];
  }];
}

- (void)presentSessionMenuForController:(Armsx2GameViewController*)controller {
  if (!controller || self.gameController != controller || self.stopInProgress ||
      self.menuOpening || self.sessionMenu || controller.touchEditing) return;
  self.menuOpening = YES;
  [controller resetInput];
  controller.controlsView.userInteractionEnabled = NO;

  dispatch_async(_runtimeQueue, ^{
    if (self.api && self.gameController == controller && !self.stopInProgress)
      self.api->set_paused(1);
    dispatch_async(dispatch_get_main_queue(), ^{
      if (self.gameController != controller || self.stopInProgress) {
        self.menuOpening = NO;
        controller.controlsView.userInteractionEnabled = YES;
        return;
      }

      Armsx2SessionMenu* menu = [Armsx2SessionMenu new];
      menu.gameTitle = controller.title.length ? controller.title : @"ARMSX2";
      menu.localeIdentifier = controller.uiLocale;
      if (self.activeBootKind == NEO_ARMSX2_BOOT_DISC && self.activeGamePath.length && self.activeDataDirectory.length) {
        __weak Armsx2InternalBridgePlugin* weakBridge = self;
        __weak Armsx2GameViewController* weakOwner = controller;
        menu.textureHost = [self.textures sessionHostForAPI:self.api gamePath:self.activeGamePath
            dataPath:self.activeDataDirectory alive:^BOOL {
              Armsx2InternalBridgePlugin* bridge = weakBridge;
              return bridge && bridge.api && bridge.gameController == weakOwner && weakOwner && !bridge.stopInProgress;
            }];
      }
      __weak Armsx2InternalBridgePlugin* weakSelf = self;
      __weak Armsx2GameViewController* weakController = controller;

      menu.readSnapshot = ^(void (^completion)(NSDictionary<NSString*, id>* snapshot)) {
        Armsx2InternalBridgePlugin* bridge = weakSelf;
        Armsx2GameViewController* owner = weakController;
        if (!bridge || !owner) { if (completion) completion(nil); return; }
        [bridge readSessionSnapshotForController:owner completion:completion];
      };
      menu.performCommand = ^(NSString* command, id value,
                              void (^completion)(BOOL success, NSString* message)) {
        Armsx2InternalBridgePlugin* bridge = weakSelf;
        Armsx2GameViewController* owner = weakController;
        if (!bridge || !owner) {
          if (completion) completion(NO, @"ARMSX2 session is no longer active.");
          return;
        }
        [bridge performGameCommand:command value:value controller:owner completion:completion];
      };
      menu.readRetroAchievements = ^(void (^completion)(NSDictionary<NSString*, id>* state)) {
        Armsx2InternalBridgePlugin* bridge = weakSelf;
        Armsx2GameViewController* owner = weakController;
        if (!bridge || !owner) { if (completion) completion(nil); return; }
        [bridge readRetroAchievementsForController:owner completion:completion];
      };
      menu.performRetroAchievementsCommand = ^(NSString* command, id value,
                                                void (^completion)(BOOL success, NSString* message)) {
        Armsx2InternalBridgePlugin* bridge = weakSelf;
        Armsx2GameViewController* owner = weakController;
        if (!bridge || !owner) {
          if (completion) completion(NO, @"ARMSX2 session is no longer active.");
          return;
        }
        [bridge performRetroAchievementsCommand:command value:value controller:owner completion:completion];
      };
      menu.readGraphicsHacks = ^(void (^completion)(NSDictionary<NSString*, id>* state)) {
        Armsx2InternalBridgePlugin* bridge=weakSelf;
        Armsx2GameViewController* owner=weakController;
        if (!bridge || !owner) { if (completion) completion(nil); return; }
        [bridge readGraphicsHacksForController:owner completion:completion];
      };
      menu.performGraphicsHack = ^(NSString* key, NSInteger value,
                                   void (^completion)(BOOL success, NSString* message)) {
        Armsx2InternalBridgePlugin* bridge=weakSelf;
        Armsx2GameViewController* owner=weakController;
        if (!bridge || !owner) {
          if (completion) completion(NO,@"ARMSX2 session is no longer active.");
          return;
        }
        [bridge performGraphicsHack:key value:value controller:owner completion:completion];
      };
      menu.readPatches = ^(void (^completion)(NSDictionary<NSString*, id>* state)) {
        Armsx2InternalBridgePlugin* bridge=weakSelf;
        Armsx2GameViewController* owner=weakController;
        if (!bridge || !owner) { if (completion) completion(nil); return; }
        [bridge readAvailablePatchesForController:owner completion:completion];
      };
      menu.performPatchCommand = ^(NSString* name, NSInteger value,
                                   void (^completion)(BOOL success, NSString* message)) {
        Armsx2InternalBridgePlugin* bridge=weakSelf;
        Armsx2GameViewController* owner=weakController;
        if (!bridge || !owner) {
          if (completion) completion(NO,@"ARMSX2 session is no longer active.");
          return;
        }
        [bridge performPatchCommand:name value:value controller:owner completion:completion];
      };
      menu.importCheats = ^(NSDictionary* request,void (^completion)(NSDictionary*)) {
        Armsx2InternalBridgePlugin* bridge=weakSelf;
        Armsx2GameViewController* owner=weakController;
        if(!bridge || !owner){completion(NeoCheatFailure(@"sessionChanged"));return;}
        dispatch_async(bridge->_runtimeQueue,^{
          NSDictionary* result=NeoCheatFailure(@"sessionChanged");
          if(bridge.api && bridge.gameController==owner && !bridge.stopInProgress) {
            char json[262144]={};
            if(bridge.api->get_available_patches_json(json,sizeof(json))) {
              NSData* data=[NSData dataWithBytes:json length:strlen(json)];
              id state=[NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
              if([state isKindOfClass:NSDictionary.class]) {
                if([request[@"kind"] isEqual:@"delete"]) {
                  NSDictionary* item=nil;
                  for(NSDictionary* candidate in state[@"items"])
                    if([candidate[@"cheat"] boolValue] && [NeoField(candidate,@"id") isEqual:NeoField(request,@"id")] && [NeoField(candidate,@"name") isEqual:NeoField(request,@"name")]){item=candidate;break;}
                  NSDictionary* plan=item?NeoCheatRemovalPlan(bridge.activeDataDirectory,request,state,YES):NeoCheatFailure(@"notRemovable");
                  result=plan;
                  if([plan[@"success"] boolValue]) {
                    char error[512]={};
                    if(!bridge.api->set_patch_state([request[@"id"] UTF8String],0,error,sizeof(error)) || !NeoCommitCheatRemoval(plan)) result=NeoCheatFailure(@"writeFailed");
                    else if(!bridge.api->reload_cheats(error,sizeof(error))) {
                      [plan[@"previous"] writeToFile:plan[@"file"] options:NSDataWritingAtomic error:nil];
                      result=NeoCheatFailure(@"writeFailed");
                    } else result=@{@"success":@YES};
                  }
                  dispatch_async(dispatch_get_main_queue(),^{completion(result);});return;
                }
                NSDictionary* prepared=NeoUnifiedResolveNativeName(bridge.activeDataDirectory,request,state,YES);
                result=NeoIdentityMatches(prepared,state,YES) && NeoUnifiedNativeReceipt(bridge.activeDataDirectory,prepared)
                    ? NeoPnachImport(bridge.activeDataDirectory,prepared,state) : NeoCheatFailure(@"writeFailed");
                if ([result[@"success"] boolValue] && prepared[@"unifiedDisplayName"]) {
                  NSMutableDictionary* named=[result mutableCopy]; named[@"unifiedDisplayName"]=prepared[@"unifiedDisplayName"]; result=named;
                }
                if([result[@"success"] boolValue] && [result[@"added"] integerValue]>0) {
                  char error[512]={};
                  if(!bridge.api->reload_cheats(error,sizeof(error))) {
                    [NSFileManager.defaultManager removeItemAtPath:result[@"file"] error:nil];
                    result=NeoCheatFailure(@"writeFailed");
                  }
                }
              }
            }
          }
          dispatch_async(dispatch_get_main_queue(),^{completion(result);});
        });
      };
      menu.resumeGame = ^{
        Armsx2InternalBridgePlugin* bridge = weakSelf;
        Armsx2GameViewController* owner = weakController;
        if (!bridge || !owner || bridge.stopInProgress || bridge.menuOpening || !bridge.sessionMenu) return;
        bridge.menuOpening = YES;
        UINavigationController* navigation = bridge.sessionMenu;
        [navigation dismissViewControllerAnimated:YES completion:^{
          bridge.sessionMenu = nil;
          bridge.menuOpening = NO;
          if (bridge.gameController != owner || bridge.stopInProgress) return;
          owner.controlsView.userInteractionEnabled = YES;
          dispatch_async(bridge->_runtimeQueue, ^{
            if (bridge.api && bridge.gameController == owner && !bridge.stopInProgress)
              bridge.api->set_paused(0);
          });
        }];
      };
      menu.quitGame = ^{
        Armsx2InternalBridgePlugin* bridge = weakSelf;
        if (!bridge || bridge.stopInProgress) return;
        bridge.menuOpening = YES;
        bridge.sessionMenu.view.userInteractionEnabled = NO;
        [bridge stopActiveSessionWithCompletion:^(BOOL success, NSString* message) {
          if (!success) {
            bridge.menuOpening = NO;
            bridge.sessionMenu.view.userInteractionEnabled = YES;
          }
        }];
      };

      UINavigationController* navigation = [[UINavigationController alloc] initWithRootViewController:menu];
      navigation.modalPresentationStyle = UIModalPresentationOverFullScreen;
      navigation.modalInPresentation = YES;
      self.sessionMenu = navigation;
      controller.title = controller.title.length ? controller.title : @"ARMSX2";
      [controller presentViewController:navigation animated:YES completion:^{
        self.menuOpening = NO;
      }];
    });
  });
}

- (void)handleMethodCall:(FlutterMethodCall*)call result:(FlutterResult)result {
  if ([call.method isEqualToString:@"diagnostics"]) {
    NSString* path = [self corePath];
    result(@{
      @"corePresent": @([NSFileManager.defaultManager isReadableFileAtPath:path]),
      @"coreLoaded": @(self.api != NULL),
      @"busy": @(self.operationBusy),
      @"abi": @(self.api ? self.api->version : 0),
      @"sourceRevision": self.api && self.api->source_revision
          ? [NSString stringWithUTF8String:self.api->source_revision] : @"",
    });
    return;
  }

  if ([call.method isEqualToString:@"stop"]) {
    [self stopActiveSessionWithCompletion:^(BOOL success, NSString* message) {
      result(@{@"success": @(success), @"message": message ?: @""});
    }];
    return;
  }

  // Build 485: HD texture packs of a PS2 game (library side, no Core needed).
  if ([self.textures handleMethodCall:call result:result]) return;

  if (![call.method isEqualToString:@"launch"]) {
    result(FlutterMethodNotImplemented);
    return;
  }

  if (self.operationBusy) {
    result(@{@"success": @NO, @"message": @"An ARMSX2 transaction is already active."});
    return;
  }
  NSDictionary* args = [call.arguments isKindOfClass:NSDictionary.class] ? call.arguments : @{};
  NSNumber* transactionNumber = [args[@"transaction"] isKindOfClass:NSNumber.class] ? args[@"transaction"] : nil;
  NSString* gamePath = [args[@"gamePath"] isKindOfClass:NSString.class] ? args[@"gamePath"] : @"";
  BOOL biosBoot = [args[@"bootBios"] boolValue];
  NSString* dataPath = [args[@"dataPath"] isKindOfClass:NSString.class] ? args[@"dataPath"] : @"";
  NSString* biosDirectory = [args[@"biosDirectory"] isKindOfClass:NSString.class] ? args[@"biosDirectory"] : @"";
  NSString* biosFilename = [args[@"biosFilename"] isKindOfClass:NSString.class] ? args[@"biosFilename"] : @"";
  NSString* uiLocale = [args[@"uiLocale"] isKindOfClass:NSString.class]
      ? ARMSX2CanonicalLocale(args[@"uiLocale"]) : @"en";
  if (!transactionNumber || transactionNumber.unsignedLongLongValue == 0 ||
      (!biosBoot && ![gamePath hasPrefix:@"/"]) || (biosBoot && gamePath.length != 0) ||
      ![dataPath hasPrefix:@"/"] || ![biosDirectory hasPrefix:@"/"]) {
    result(@{@"success": @NO, @"message": @"Invalid ARMSX2 launch parameters."});
    return;
  }
  if (!biosBoot && ![NSFileManager.defaultManager isReadableFileAtPath:gamePath]) {
    result(@{@"success": @NO, @"message": @"The selected PS2 game is not readable."});
    return;
  }

  self.operationBusy = YES;
  dispatch_async(_runtimeQueue, ^{
    NSString* loadError = nil;
    if (![self loadCore:&loadError]) {
      [self failTransaction:loadError result:result];
      return;
    }

    __block Armsx2GameViewController* controller = nil;
    dispatch_sync(dispatch_get_main_queue(), ^{
      UIViewController* root = ARMSX2RootViewController();
      if (!root || root.view.window == nil) return;
      controller = [Armsx2GameViewController new];
      controller.api = self.api;
      controller.uiLocale = uiLocale;
      controller.title = biosBoot ? [controller en:@"PS2 BIOS" fr:@"BIOS PS2"] :
          (gamePath.lastPathComponent.stringByDeletingPathExtension ?: @"ARMSX2");
      // Build 484: per-game touch layout key (the game file; none for the BIOS).
      controller.touchGameKey = biosBoot ? nil : gamePath.lastPathComponent;
      __weak Armsx2InternalBridgePlugin* weakSelf = self;
      __weak Armsx2GameViewController* weakController = controller;
      controller.closeHandler = ^{
        [weakSelf stopActiveSessionWithCompletion:^(BOOL success, NSString* message) {}];
      };
      controller.menuHandler = ^{
        Armsx2InternalBridgePlugin* strongSelf = weakSelf;
        Armsx2GameViewController* strongController = weakController;
        if (!strongSelf || !strongController) return;
        [strongSelf presentSessionMenuForController:strongController];
      };
      [controller loadViewIfNeeded];
      if (!controller.coreView) { controller = nil; return; }
      [root presentViewController:controller animated:NO completion:nil];
      self.gameController = controller;
    });
    if (!controller) {
      [self failTransaction:@"ARMSX2 render view could not be created." result:result];
      return;
    }

    NSFileManager* fm = NSFileManager.defaultManager;
    [fm createDirectoryAtPath:dataPath withIntermediateDirectories:YES attributes:nil error:nil];

    char error[2048] = {};
    NeoARMSX2Configuration config = {};
    config.size = sizeof(config);
    config.transaction = transactionNumber.unsignedLongLongValue;
    config.data_directory = dataPath.fileSystemRepresentation;
    self.activeDataDirectory = dataPath;
    self.activeGamePath = biosBoot ? @"" : gamePath;
    NSString* resources = [self resourcePath];
    config.resource_directory = resources.fileSystemRepresentation;
    config.bios_directory = biosDirectory.fileSystemRepresentation;
    config.bios_filename = biosFilename.length ? biosFilename.fileSystemRepresentation : "";
    config.event = NULL;
    config.context = NULL;

    if (!self.api->prepare(&config, 120000, error, sizeof(error))) {
      NSString* message = error[0] ? [NSString stringWithUTF8String:error] : @"ARMSX2 Core preparation failed.";
      [self failTransaction:message result:result];
      return;
    }
    memset(error, 0, sizeof(error));
    if (!self.api->request_jit_detach(error, sizeof(error))) {
      NSString* message = error[0] ? [NSString stringWithUTF8String:error] : @"ARMSX2 debugger detach request failed.";
      [self failTransaction:message result:result];
      return;
    }

    NSString* detachMessage = nil;
    if (!ARMSX2JitWaitForDetach(120.0, &detachMessage)) {
      [self failTransaction:detachMessage ?: @"ARMSX2 helper did not confirm debugger detach." result:result];
      return;
    }

    memset(error, 0, sizeof(error));
    if (!self.api->validate_jit(error, sizeof(error))) {
      NSString* message = error[0] ? [NSString stringWithUTF8String:error] : @"ARMSX2 post-detach JIT validation failed.";
      [self failTransaction:message result:result];
      return;
    }

    NSString* ext = gamePath.pathExtension.lowercaseString;
    uint32_t kind = biosBoot ? NEO_ARMSX2_BOOT_BIOS :
        ([ext isEqualToString:@"elf"] ? NEO_ARMSX2_BOOT_ELF : NEO_ARMSX2_BOOT_DISC);
    memset(error, 0, sizeof(error));
    // HD textures chosen in the library reach the game's INI once the Core has
    // identified the disc, before its first frame. Not fatal: the INI stays as is.
    if (kind == NEO_ARMSX2_BOOT_DISC &&
        !self.api->set_texture_boot_preferences([self.textures bootPreferencesJSONForDataPath:dataPath].UTF8String,
                                                error, sizeof(error)))
      NSLog(@"[ARMSX2] HD texture choices not passed to the Core: %s", error);
    self.activeBootKind = kind;
    memset(error, 0, sizeof(error));
    const char* bootPath = biosBoot ? "" : gamePath.fileSystemRepresentation;
    if (!self.api->boot(bootPath, kind, 120000, error, sizeof(error))) {
      NSString* message = error[0] ? [NSString stringWithUTF8String:error] : @"ARMSX2 boot failed.";
      [self failTransaction:message result:result];
      return;
    }

    self.operationBusy = NO;
    if (kind == NEO_ARMSX2_BOOT_DISC) [self.textures recordBootForAPI:self.api gamePath:gamePath dataPath:dataPath];
    [self publishMenuStateForController:controller message:
        [controller en:@"ARMSX2 ready." fr:@"ARMSX2 prêt."]];
    NSString* revision = self.api->source_revision
        ? [NSString stringWithUTF8String:self.api->source_revision] : @"";
    dispatch_async(dispatch_get_main_queue(), ^{
      // Presented earlier and booted with the surface the Core sized for the
      // iPhone: from here the render view may be shown on the TV.
      [self attachExternalDisplayForController:controller];
      result(@{
        @"success": @YES,
        @"transaction": transactionNumber,
        @"bootKind": kind == NEO_ARMSX2_BOOT_BIOS ? @"bios" :
            (kind == NEO_ARMSX2_BOOT_ELF ? @"elf" : @"disc"),
        @"sourceRevision": revision ?: @"",
        @"message": @"ARMSX2 entered Running.",
      });
    });
  });
}

@end

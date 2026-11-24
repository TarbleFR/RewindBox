// RewindBox's in-game menu for the Switch 2 engine. See S2ArmSessionMenu.h.
#import "S2ArmSessionMenu.h"
#import "S2ArmSettings.h"
#import "S2ArmGuestABI.h"

#import <GameController/GameController.h>
#import <dlfcn.h>
#include <string.h>

static NSString *const kMenuButtonIdentifier = @"rewindbox.s2arm.menu";
// The engine's brief overlay (S2Arm hud.m s2a_hud_brief_show): a UILabel added to the game view with this identifier.
static NSString *const kEngineOverlayIdentifier = @"hud.brief";
static NSTimeInterval const kTick = 0.1;

static NSDictionary<NSString *, NSString *> *EnglishStrings(void) {
  return @{
    @"menu.title" : @"Switch 2",
    @"menu.resume" : @"Resume",
    @"menu.performanceOn" : @"Show performance overlay",
    @"menu.performanceOff" : @"Hide performance overlay",
    @"menu.settings" : @"Settings",
    @"menu.benchmark" : @"Benchmark",
    @"menu.benchmarkInstructions" : @"180 seconds on the same route, from the same starting point. Use a cool, unplugged phone with Low Power Mode off and a route already played once. Keep settings and brightness unchanged. The measurement starts when this dialog closes; do not reopen the menu until it ends.",
    @"menu.benchmarkScenario" : @"Route and starting point",
    @"menu.benchmarkStart" : @"Confirm conditions and start",
    @"menu.benchmarkFailed" : @"Could not start. Enter a scenario, cool and unplug the phone, then turn off Low Power Mode and screen recording and try again.",
    @"menu.benchmarkInterrupted" : @"Opening the menu interrupted the comparison. Let this measurement finish before starting another one.",
    @"menu.benchmarkSaved" : @"The last measurement is complete. Results are in the game diagnostics.",
    @"menu.benchmarkInvalid" : @"The last measurement is incomplete or its conditions changed. It cannot establish a performance improvement; details are in the game diagnostics.",
    @"menu.resolution" : @"Resolution",
    @"menu.antiAliasing" : @"Anti-aliasing",
    @"menu.scalingFilter" : @"Scaling filter",
    @"menu.frameRateLimit" : @"Frame rate limit",
    @"menu.frameInterpolation" : @"Frame Generation",
    @"menu.mode" : @"Console mode",
    @"menu.imageFormat" : @"Image format",
    @"menu.gameLanguage" : @"Game language",
    @"menu.nextLaunch" : @"Applies the next time a Switch 2 game starts, after RewindBox is restarted.",
    @"menu.liveNow" : @"Applies at once to this game.",
    @"menu.frameInterpolationUnavailable" : @"Frame Generation is not available on this device.",
    @"menu.quit" : @"Quit game",
    @"menu.quitTitle" : @"Quit the game?",
    @"menu.quitMessage" : @"The game saves are written before it closes.",
    @"menu.cancel" : @"Cancel",
    @"menu.back" : @"Back",
    @"menu.res050" : @"0.5× (faster)",
    @"menu.res075" : @"0.75×",
    @"menu.res100" : @"1× (native)",
    @"menu.aaNone" : @"None",
    @"menu.aaSmaaMedium" : @"SMAA medium",
    @"menu.aaSmaaHigh" : @"SMAA high",
    @"menu.filterBilinear" : @"Smooth (bilinear)",
    @"menu.filterNearest" : @"Sharp (nearest)",
    @"menu.fps60" : @"60 FPS",
    @"menu.fps120" : @"120 FPS",
    @"menu.fpsUnlimited" : @"No limit",
    @"menu.frameInterpolationOff" : @"Off",
    @"menu.frameInterpolationOn" : @"On",
    @"menu.modeHandheld" : @"Handheld",
    @"menu.modeDocked" : @"Docked",
    @"menu.formatWide" : @"Widescreen (fills the screen)",
    @"menu.format169" : @"16:9 with black bars",
    @"menu.languageAuto" : @"Automatic (iPhone language)",
  };
}

// The settings the menu offers: the snapshot key, the title key and the value labels.
static NSArray<NSString *> *SettingKeys(void) {
  return @[ @"resolutionScale", @"antiAliasing", @"scalingFilter", @"frameRateLimit", @"frameInterpolation", @"docked", @"widescreen",
            @"gameLanguage" ];
}

static NSString *TitleKey(NSString *setting) {
  NSDictionary *titles = @{
    @"resolutionScale" : @"menu.resolution",
    @"antiAliasing" : @"menu.antiAliasing",
    @"scalingFilter" : @"menu.scalingFilter",
    @"frameRateLimit" : @"menu.frameRateLimit",
    @"frameInterpolation" : @"menu.frameInterpolation",
    @"docked" : @"menu.mode",
    @"widescreen" : @"menu.imageFormat",
    @"gameLanguage" : @"menu.gameLanguage",
  };
  return titles[setting] ?: setting;
}

static NSArray *Choices(NSString *setting) {
  if ([setting isEqualToString:@"docked"]) return @[ @NO, @YES ];
  if ([setting isEqualToString:@"widescreen"]) return @[ @YES, @NO ];
  if ([setting isEqualToString:@"frameInterpolation"]) return @[ @NO, @YES ];
  return S2ArmSettingsValues(setting);
}

@interface S2ArmSessionMenu ()
@property(nonatomic, weak) UIViewController *viewController;
@property(nonatomic, copy) NSDictionary<NSString *, NSString *> *strings;
@property(nonatomic, copy) void (^stop)(void);
@property(nonatomic, strong, nullable) UIButton *button;
@property(nonatomic, strong, nullable) NSTimer *timer;
@property(nonatomic, strong, nullable) id controllerConnected;
@property(nonatomic, weak, nullable) UIView *overlay;
@property(nonatomic, weak, nullable) UIViewController *presented;
@property(nonatomic, assign) BOOL comboHeld;
@property(nonatomic, assign) BOOL stopping;
@end

@implementation S2ArmSessionMenu

- (instancetype)initWithViewController:(UIViewController *)viewController
                               strings:(NSDictionary<NSString *, NSString *> *)strings
                                  stop:(void (^)(void))stop {
  if ((self = [super init])) {
    _viewController = viewController;
    _strings = [strings isKindOfClass:NSDictionary.class] ? [strings copy] : @{};
    _stop = [stop copy];
  }
  return self;
}

- (NSString *)text:(NSString *)key {
  id value = self.strings[key];
  if ([value isKindOfClass:NSString.class] && [value length]) return value;
  return EnglishStrings()[key] ?: key;
}

#pragma mark - attach

- (void)attach {
  UIView *root = self.viewController.view;
  if (!root || self.button) return;
  UIButton *button = [UIButton buttonWithType:UIButtonTypeSystem];
  button.translatesAutoresizingMaskIntoConstraints = NO;
  button.accessibilityIdentifier = kMenuButtonIdentifier;
  button.accessibilityLabel = [self text:@"menu.title"];
  [button setImage:[UIImage systemImageNamed:@"line.3.horizontal"] forState:UIControlStateNormal];
  button.tintColor = UIColor.whiteColor;
  button.backgroundColor = [UIColor colorWithWhite:0 alpha:0.45];
  button.layer.cornerRadius = 18;
  button.layer.zPosition = 10001;   // above the engine's overlays (z 10000)
  button.alpha = 0.6;
  [button addTarget:self action:@selector(showMenu) forControlEvents:UIControlEventTouchUpInside];
  [root addSubview:button];
  // Top right, below the engine's brief overlay pill (safe area top + 6, 20 high).
  [NSLayoutConstraint activateConstraints:@[
    [button.widthAnchor constraintEqualToConstant:36],
    [button.heightAnchor constraintEqualToConstant:36],
    [button.topAnchor constraintEqualToAnchor:root.safeAreaLayoutGuide.topAnchor constant:32],
    [button.trailingAnchor constraintEqualToAnchor:root.safeAreaLayoutGuide.trailingAnchor constant:-8],
  ]];
  self.button = button;
  __weak S2ArmSessionMenu *weakSelf = self;
  self.controllerConnected = [NSNotificationCenter.defaultCenter addObserverForName:GCControllerDidConnectNotification
      object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note) { [weakSelf watchControllerCombo]; }];
  [self watchControllerCombo];
  [self applyOverlay];
}

- (void)detach {
  if (self.controllerConnected) [NSNotificationCenter.defaultCenter removeObserver:self.controllerConnected];
  self.controllerConnected = nil;
  [self.timer invalidate];
  self.timer = nil;
  self.comboHeld = NO;
  self.overlay = nil;
  [self.button removeFromSuperview];
  self.button = nil;
  if (self.presented && self.presented.presentingViewController) [self.presented dismissViewControllerAnimated:NO completion:nil];
  self.presented = nil;
}

- (void)watchControllerCombo {
  if (!self.button || self.timer) return;
  for (GCController *controller in GCController.controllers) {
    if (!controller.extendedGamepad.buttonOptions) continue;
    __weak S2ArmSessionMenu *weakSelf = self;
    self.timer = [NSTimer timerWithTimeInterval:kTick repeats:YES block:^(NSTimer *timer) { [weakSelf tick]; }];
    [NSRunLoop.mainRunLoop addTimer:self.timer forMode:NSRunLoopCommonModes];
    break;
  }
}

- (void)tick {
  // − and + together on any controller opens the menu (read-only polling: the engine's own input handlers are untouched).
  BOOL held = NO, canOpenMenu = NO;
  for (GCController *controller in GCController.controllers) {
    GCExtendedGamepad *pad = controller.extendedGamepad;
    if (!pad.buttonOptions) continue;
    canOpenMenu = YES;
    if (pad.buttonOptions.isPressed && pad.buttonMenu.isPressed) held = YES;
  }
  if (!canOpenMenu) {
    [self.timer invalidate];
    self.timer = nil;
  }
  if (held && !self.comboHeld) [self showMenu];
  self.comboHeld = held;
}

#pragma mark - performance overlay

static UIView *FindView(UIView *view, NSString *identifier) {
  if ([view.accessibilityIdentifier isEqualToString:identifier]) return view;
  for (UIView *child in view.subviews) {
    UIView *found = FindView(child, identifier);
    if (found) return found;
  }
  return nil;
}

- (nullable UIView *)engineOverlay {
  UIView *root = self.viewController.view;
  UIView *scope = root.window ?: root;
  UIView *overlay = self.overlay;
  if (scope && (!overlay || ![overlay isDescendantOfView:scope])) {
    self.overlay = overlay = FindView(scope, kEngineOverlayIdentifier);
  }
  return scope ? overlay : nil;
}

- (void)applyOverlay {
  UIView *overlay = [self engineOverlay];
  BOOL hidden = !S2ArmSettingsPerformanceOverlay();
  if (overlay && overlay.hidden != hidden) overlay.hidden = hidden;
}

#pragma mark - menus

- (BOOL)present:(UIViewController *)controller {
  UIViewController *host = self.viewController;
  if (!host || self.stopping) return NO;
  if (host.presentedViewController) {
    // One of ours is up: replace it. Something of the engine is up (its own settings, saves): leave it alone.
    if (host.presentedViewController != self.presented) return NO;
    [host dismissViewControllerAnimated:NO completion:nil];
  }
  UIPopoverPresentationController *popover = controller.popoverPresentationController;
  if (popover) {   // iPad: anchor the action sheet on the button
    popover.sourceView = self.button ?: host.view;
    popover.sourceRect = self.button ? self.button.bounds : CGRectMake(CGRectGetMidX(host.view.bounds), 0, 1, 1);
  }
  self.presented = controller;
  [host presentViewController:controller animated:YES completion:nil];
  return YES;
}

- (void)showMenu {
  // An overlay changes the measured scenario. Keep the game running and retain
  // the partial evidence, but never silently compare this window with a clean one.
  s2a_rb_guest_benchmark_fn benchmark = (s2a_rb_guest_benchmark_fn)dlsym(RTLD_DEFAULT, S2A_RB_GUEST_BENCHMARK);
  if (benchmark) (void)benchmark(3, NULL, NULL, 0);
  UIAlertController *sheet = [UIAlertController alertControllerWithTitle:[self text:@"menu.title"]
                                                                 message:nil
                                                          preferredStyle:UIAlertControllerStyleActionSheet];
  __weak S2ArmSessionMenu *weakSelf = self;
  BOOL overlayOn = S2ArmSettingsPerformanceOverlay();
  [sheet addAction:[UIAlertAction actionWithTitle:[self text:overlayOn ? @"menu.performanceOff" : @"menu.performanceOn"]
                                            style:UIAlertActionStyleDefault
                                          handler:^(UIAlertAction *action) {
                                            S2ArmSettingsSetPerformanceOverlay(!overlayOn);
                                            [weakSelf applyOverlay];
                                          }]];
  [sheet addAction:[UIAlertAction actionWithTitle:[self text:@"menu.settings"]
                                            style:UIAlertActionStyleDefault
                                          handler:^(UIAlertAction *action) { [weakSelf showSettings]; }]];
  if (benchmark && [[self benchmarkStatus][@"available"] boolValue]) {
    [sheet addAction:[UIAlertAction actionWithTitle:[self text:@"menu.benchmark"]
                                              style:UIAlertActionStyleDefault
                                            handler:^(UIAlertAction *action) { [weakSelf showBenchmark]; }]];
  }
  [sheet addAction:[UIAlertAction actionWithTitle:[self text:@"menu.quit"]
                                            style:UIAlertActionStyleDestructive
                                          handler:^(UIAlertAction *action) { [weakSelf confirmQuit]; }]];
  [sheet addAction:[UIAlertAction actionWithTitle:[self text:@"menu.resume"] style:UIAlertActionStyleCancel handler:nil]];
  [self present:sheet];
}

#pragma mark - reproducible benchmark (optional engine entry point)

- (NSDictionary *)benchmarkStatus {
  s2a_rb_guest_benchmark_fn benchmark = (s2a_rb_guest_benchmark_fn)dlsym(RTLD_DEFAULT, S2A_RB_GUEST_BENCHMARK);
  if (!benchmark) return @{};
  char output[32768] = {0};
  if (benchmark(0, NULL, output, sizeof output) != 0) return @{};
  NSData *data = [NSData dataWithBytes:output length:strnlen(output, sizeof output)];
  id result = [NSJSONSerialization JSONObjectWithData:data options:0 error:NULL];
  return [result isKindOfClass:NSDictionary.class] ? result : @{};
}

- (void)benchmarkMessage:(NSString *)message {
  UIAlertController *alert = [UIAlertController alertControllerWithTitle:[self text:@"menu.benchmark"]
                                                                 message:message preferredStyle:UIAlertControllerStyleAlert];
  [alert addAction:[UIAlertAction actionWithTitle:[self text:@"menu.back"] style:UIAlertActionStyleCancel handler:nil]];
  [self present:alert];
}

- (void)showBenchmark {
  NSDictionary *status = [self benchmarkStatus];
  if ([status[@"active"] boolValue]) {
    [self benchmarkMessage:[self text:@"menu.benchmarkInterrupted"]];
    return;
  }
  NSString *message = [self text:@"menu.benchmarkInstructions"];
  NSDictionary *last = [status[@"lastsummary"] isKindOfClass:NSDictionary.class] ? status[@"lastsummary"] : nil;
  if (last) {
    NSString *result = [self text:[last[@"comparable"] boolValue] ? @"menu.benchmarkSaved" : @"menu.benchmarkInvalid"];
    message = [NSString stringWithFormat:@"%@\n\n%@", result, message];
  }
  UIAlertController *alert = [UIAlertController alertControllerWithTitle:[self text:@"menu.benchmark"]
                                                                 message:message preferredStyle:UIAlertControllerStyleAlert];
  NSString *scenarioKey = [@"rewindbox.s2arm.benchmark.scenario." stringByAppendingString:self.benchmarkContext[@"game_id"] ?: @"unknown"];
  [alert addTextFieldWithConfigurationHandler:^(UITextField *field) {
    field.placeholder = [self text:@"menu.benchmarkScenario"];
    field.text = [NSUserDefaults.standardUserDefaults stringForKey:scenarioKey];
    field.autocorrectionType = UITextAutocorrectionTypeNo;
    field.returnKeyType = UIReturnKeyDone;
  }];
  __weak S2ArmSessionMenu *weakSelf = self;
  __weak UIAlertController *weakAlert = alert;
  [alert addAction:[UIAlertAction actionWithTitle:[self text:@"menu.cancel"] style:UIAlertActionStyleCancel handler:nil]];
  [alert addAction:[UIAlertAction actionWithTitle:[self text:@"menu.benchmarkStart"] style:UIAlertActionStyleDefault
                                          handler:^(UIAlertAction *action) {
    S2ArmSessionMenu *menu = weakSelf;
    UIAlertController *dialog = weakAlert;
    NSString *scenario = [dialog.textFields.firstObject.text stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    if (!menu || menu.stopping) return;
    NSMutableDictionary *metadata = [menu.benchmarkContext mutableCopy] ?: [NSMutableDictionary dictionary];
    metadata[@"protocol_id"] = @"rb-switch2-bench-v1";
    metadata[@"duration_seconds"] = @180;
    metadata[@"scenario"] = scenario ?: @"";
    metadata[@"cold_confirmed"] = @YES;
    metadata[@"cache_protocol"] = @"warm-route-v1";
    // The overlay is a live host setting, unlike the graphics preferences.
    NSMutableDictionary *settings = [metadata[@"settings"] mutableCopy] ?: [NSMutableDictionary dictionary];
    settings[@"performanceOverlay"] = @(S2ArmSettingsPerformanceOverlay());
    metadata[@"settings"] = settings;
    NSData *data = [NSJSONSerialization dataWithJSONObject:metadata options:0 error:NULL];
    NSString *json = data ? [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] : nil;
    void (^start)(void) = ^{
      S2ArmSessionMenu *current = weakSelf;
      if (!current || current.stopping || !current.viewController.view.window) return;
      s2a_rb_guest_benchmark_fn benchmark = (s2a_rb_guest_benchmark_fn)dlsym(RTLD_DEFAULT, S2A_RB_GUEST_BENCHMARK);
      if (!json || !benchmark || benchmark(1, json.UTF8String, NULL, 0) != 0) {
        [current benchmarkMessage:[current text:@"menu.benchmarkFailed"]];
      } else {
        [NSUserDefaults.standardUserDefaults setObject:scenario forKey:scenarioKey];
      }
    };
    UIViewController *presenter = dialog.presentingViewController;
    if (presenter) [presenter dismissViewControllerAnimated:YES completion:start];
    else dispatch_async(dispatch_get_main_queue(), ^{
      // A missing presenter is not proof that the dismissal animation ended.
      // Refuse this attempt if its dialog still covers the game.
      if (!dialog.viewIfLoaded.window) start();
      else [weakSelf benchmarkMessage:[weakSelf text:@"menu.benchmarkFailed"]];
    });
  }]];
  [self present:alert];
}

- (NSString *)label:(NSString *)setting value:(id)value {
  if ([setting isEqualToString:@"docked"]) return [self text:[value boolValue] ? @"menu.modeDocked" : @"menu.modeHandheld"];
  if ([setting isEqualToString:@"widescreen"]) return [self text:[value boolValue] ? @"menu.formatWide" : @"menu.format169"];
  if ([setting isEqualToString:@"frameInterpolation"])
    return [self text:[value boolValue] ? @"menu.frameInterpolationOn" : @"menu.frameInterpolationOff"];
  NSDictionary *keys = @{
    @"resolutionScale" : @{@"0.5" : @"menu.res050", @"0.75" : @"menu.res075", @"1" : @"menu.res100"},
    @"antiAliasing" : @{@"None" : @"menu.aaNone", @"SmaaMedium" : @"menu.aaSmaaMedium", @"SmaaHigh" : @"menu.aaSmaaHigh"},
    @"scalingFilter" : @{@"Bilinear" : @"menu.filterBilinear", @"Nearest" : @"menu.filterNearest"},
    @"frameRateLimit" : @{@"60" : @"menu.fps60", @"120" : @"menu.fps120", @"0" : @"menu.fpsUnlimited"},   // no 30 (engine patch 0319)
  };
  if ([setting isEqualToString:@"gameLanguage"]) {
    if ([value isEqual:@"auto"]) return [self text:@"menu.languageAuto"];
    NSString *name = self.strings[[@"lang." stringByAppendingString:value]];
    return name.length ? name : value;
  }
  NSString *key = keys[setting][value];
  return key ? [self text:key] : [value description];
}

- (void)showSettings {
  NSDictionary *settings = S2ArmSettingsSnapshot();
  UIAlertController *sheet = [UIAlertController alertControllerWithTitle:[self text:@"menu.settings"]
                                                                 message:[self text:@"menu.nextLaunch"]
                                                          preferredStyle:UIAlertControllerStyleActionSheet];
  __weak S2ArmSessionMenu *weakSelf = self;
  for (NSString *setting in SettingKeys()) {
    NSString *title = [NSString stringWithFormat:@"%@ : %@", [self text:TitleKey(setting)], [self label:setting value:settings[setting]]];
    [sheet addAction:[UIAlertAction actionWithTitle:title
                                              style:UIAlertActionStyleDefault
                                            handler:^(UIAlertAction *action) { [weakSelf showChoices:setting]; }]];
  }
  [sheet addAction:[UIAlertAction actionWithTitle:[self text:@"menu.back"]
                                            style:UIAlertActionStyleCancel
                                          handler:^(UIAlertAction *action) { [weakSelf showMenu]; }]];
  [self present:sheet];
}

- (void)showChoices:(NSString *)setting {
  id current = S2ArmSettingsSnapshot()[setting];
  // Patch 0078: the frame-rate limit applies at once when the engine can take it (applyNow), the other settings at the next start
  BOOL live = self.applyNow != nil && [setting isEqualToString:@"frameRateLimit"];
  // Patch 0345: frame generation at once in a session started with it on; the next start otherwise; never where the engine cannot
  BOOL frameInterpolation = [setting isEqualToString:@"frameInterpolation"];
  if (frameInterpolation) live = self.applyNow != nil && self.frameInterpolationLive;
  NSString *message = frameInterpolation && self.frameInterpolationUnavailable ? @"menu.frameInterpolationUnavailable"
                      : live ? @"menu.liveNow" : @"menu.nextLaunch";
  UIAlertController *sheet = [UIAlertController alertControllerWithTitle:[self text:TitleKey(setting)]
                                                                 message:[self text:message]
                                                          preferredStyle:UIAlertControllerStyleActionSheet];
  __weak S2ArmSessionMenu *weakSelf = self;
  for (id value in Choices(setting)) {
    NSString *label = [self label:setting value:value];
    if ([value isEqual:current]) label = [@"✓ " stringByAppendingString:label];
    [sheet addAction:[UIAlertAction actionWithTitle:label
                                              style:UIAlertActionStyleDefault
                                            handler:^(UIAlertAction *action) {
                                              S2ArmSettingsApply(@{setting : value});
                                              S2ArmSessionMenu *menu = weakSelf;
                                              if (menu.applyNow) (void)menu.applyNow(setting, value);   // stored above for the next start too
                                              // Patch 0345: the engine cannot interpolate here; the choice stays stored, the player is told
                                              if (frameInterpolation && menu.frameInterpolationUnavailable) [menu showFrameInterpolationUnavailable];
                                              else [menu showSettings];
                                            }]];
  }
  [sheet addAction:[UIAlertAction actionWithTitle:[self text:@"menu.back"]
                                            style:UIAlertActionStyleCancel
                                          handler:^(UIAlertAction *action) { [weakSelf showSettings]; }]];
  [self present:sheet];
}

// Patch 0345: the engine answered -2 (this device or its graphics backend cannot interpolate frames). Back returns to the settings.
- (void)showFrameInterpolationUnavailable {
  UIAlertController *alert = [UIAlertController alertControllerWithTitle:[self text:@"menu.frameInterpolation"]
                                                                 message:[self text:@"menu.frameInterpolationUnavailable"]
                                                          preferredStyle:UIAlertControllerStyleAlert];
  __weak S2ArmSessionMenu *weakSelf = self;
  [alert addAction:[UIAlertAction actionWithTitle:[self text:@"menu.back"]
                                            style:UIAlertActionStyleCancel
                                          handler:^(UIAlertAction *action) { [weakSelf showSettings]; }]];
  [self present:alert];
}

- (void)confirmQuit {
  UIAlertController *alert = [UIAlertController alertControllerWithTitle:[self text:@"menu.quitTitle"]
                                                                 message:[self text:@"menu.quitMessage"]
                                                          preferredStyle:UIAlertControllerStyleAlert];
  __weak S2ArmSessionMenu *weakSelf = self;
  [alert addAction:[UIAlertAction actionWithTitle:[self text:@"menu.cancel"] style:UIAlertActionStyleCancel handler:nil]];
  [alert addAction:[UIAlertAction actionWithTitle:[self text:@"menu.quit"]
                                            style:UIAlertActionStyleDestructive
                                          handler:^(UIAlertAction *action) {
                                            S2ArmSessionMenu *menu = weakSelf;
                                            if (!menu || menu.stopping) return;
                                            menu.stopping = YES;   // no further menu: the session ends, then the host dismisses
                                            if (menu.stop) menu.stop();
                                          }]];
  [self present:alert];
}

@end

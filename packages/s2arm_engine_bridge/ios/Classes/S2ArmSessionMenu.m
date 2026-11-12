// RewindBox's in-game menu for the Switch 2 engine. See S2ArmSessionMenu.h.
#import "S2ArmSessionMenu.h"
#import "S2ArmSettings.h"

#import <GameController/GameController.h>

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
    @"menu.resolution" : @"Resolution",
    @"menu.antiAliasing" : @"Anti-aliasing",
    @"menu.scalingFilter" : @"Scaling filter",
    @"menu.frameRateLimit" : @"Frame rate limit",
    @"menu.mode" : @"Console mode",
    @"menu.imageFormat" : @"Image format",
    @"menu.gameLanguage" : @"Game language",
    @"menu.nextLaunch" : @"Applies the next time a Switch 2 game starts, after RewindBox is restarted.",
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
    @"menu.fps30" : @"30 FPS",
    @"menu.fps60" : @"60 FPS",
    @"menu.fps120" : @"120 FPS",
    @"menu.fpsUnlimited" : @"No limit",
    @"menu.modeHandheld" : @"Handheld",
    @"menu.modeDocked" : @"Docked",
    @"menu.formatWide" : @"Widescreen (fills the screen)",
    @"menu.format169" : @"16:9 with black bars",
    @"menu.languageAuto" : @"Automatic (iPhone language)",
  };
}

// The settings the menu offers: the snapshot key, the title key and the value labels.
static NSArray<NSString *> *SettingKeys(void) {
  return @[ @"resolutionScale", @"antiAliasing", @"scalingFilter", @"frameRateLimit", @"docked", @"widescreen", @"gameLanguage" ];
}

static NSString *TitleKey(NSString *setting) {
  NSDictionary *titles = @{
    @"resolutionScale" : @"menu.resolution",
    @"antiAliasing" : @"menu.antiAliasing",
    @"scalingFilter" : @"menu.scalingFilter",
    @"frameRateLimit" : @"menu.frameRateLimit",
    @"docked" : @"menu.mode",
    @"widescreen" : @"menu.imageFormat",
    @"gameLanguage" : @"menu.gameLanguage",
  };
  return titles[setting] ?: setting;
}

static NSArray *Choices(NSString *setting) {
  if ([setting isEqualToString:@"docked"]) return @[ @NO, @YES ];
  if ([setting isEqualToString:@"widescreen"]) return @[ @YES, @NO ];
  return S2ArmSettingsValues(setting);
}

@interface S2ArmSessionMenu ()
@property(nonatomic, weak) UIViewController *viewController;
@property(nonatomic, copy) NSDictionary<NSString *, NSString *> *strings;
@property(nonatomic, copy) void (^stop)(void);
@property(nonatomic, strong, nullable) UIButton *button;
@property(nonatomic, strong, nullable) NSTimer *timer;
@property(nonatomic, weak, nullable) UIViewController *presented;
@property(nonatomic, assign) BOOL comboHeld;
@property(nonatomic, assign) NSUInteger ticks;
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
  self.timer = [NSTimer timerWithTimeInterval:kTick repeats:YES block:^(NSTimer *timer) { [weakSelf tick]; }];
  [NSRunLoop.mainRunLoop addTimer:self.timer forMode:NSRunLoopCommonModes];
  [self applyOverlay];
}

- (void)detach {
  [self.timer invalidate];
  self.timer = nil;
  [self.button removeFromSuperview];
  self.button = nil;
  if (self.presented && self.presented.presentingViewController) [self.presented dismissViewControllerAnimated:NO completion:nil];
  self.presented = nil;
}

- (void)tick {
  // − and + together on any controller opens the menu (read-only polling: the engine's own input handlers are untouched).
  BOOL held = NO;
  for (GCController *controller in GCController.controllers) {
    GCExtendedGamepad *pad = controller.extendedGamepad;
    if (pad && pad.buttonOptions.isPressed && pad.buttonMenu.isPressed) held = YES;
  }
  if (held && !self.comboHeld) [self showMenu];
  self.comboHeld = held;
  // The engine adds its overlay label when the game view is set up; keep it in the state the player chose.
  if (++self.ticks % 5 == 0) [self applyOverlay];
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
  return root ? FindView(root.window ?: root, kEngineOverlayIdentifier) : nil;
}

- (void)applyOverlay {
  UIView *overlay = [self engineOverlay];
  overlay.hidden = !S2ArmSettingsPerformanceOverlay();
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
  [sheet addAction:[UIAlertAction actionWithTitle:[self text:@"menu.quit"]
                                            style:UIAlertActionStyleDestructive
                                          handler:^(UIAlertAction *action) { [weakSelf confirmQuit]; }]];
  [sheet addAction:[UIAlertAction actionWithTitle:[self text:@"menu.resume"] style:UIAlertActionStyleCancel handler:nil]];
  [self present:sheet];
}

- (NSString *)label:(NSString *)setting value:(id)value {
  if ([setting isEqualToString:@"docked"]) return [self text:[value boolValue] ? @"menu.modeDocked" : @"menu.modeHandheld"];
  if ([setting isEqualToString:@"widescreen"]) return [self text:[value boolValue] ? @"menu.formatWide" : @"menu.format169"];
  NSDictionary *keys = @{
    @"resolutionScale" : @{@"0.5" : @"menu.res050", @"0.75" : @"menu.res075", @"1" : @"menu.res100"},
    @"antiAliasing" : @{@"None" : @"menu.aaNone", @"SmaaMedium" : @"menu.aaSmaaMedium", @"SmaaHigh" : @"menu.aaSmaaHigh"},
    @"scalingFilter" : @{@"Bilinear" : @"menu.filterBilinear", @"Nearest" : @"menu.filterNearest"},
    @"frameRateLimit" : @{@"30" : @"menu.fps30", @"60" : @"menu.fps60", @"120" : @"menu.fps120", @"0" : @"menu.fpsUnlimited"},
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
  UIAlertController *sheet = [UIAlertController alertControllerWithTitle:[self text:TitleKey(setting)]
                                                                 message:[self text:@"menu.nextLaunch"]
                                                          preferredStyle:UIAlertControllerStyleActionSheet];
  __weak S2ArmSessionMenu *weakSelf = self;
  for (id value in Choices(setting)) {
    NSString *label = [self label:setting value:value];
    if ([value isEqual:current]) label = [@"✓ " stringByAppendingString:label];
    [sheet addAction:[UIAlertAction actionWithTitle:label
                                              style:UIAlertActionStyleDefault
                                            handler:^(UIAlertAction *action) {
                                              S2ArmSettingsApply(@{setting : value});
                                              [weakSelf showSettings];
                                            }]];
  }
  [sheet addAction:[UIAlertAction actionWithTitle:[self text:@"menu.back"]
                                            style:UIAlertActionStyleCancel
                                          handler:^(UIAlertAction *action) { [weakSelf showSettings]; }]];
  [self present:sheet];
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

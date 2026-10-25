#import "RPCS3GameInputController.h"
#import "RPCS3TouchControls.h"
#include "RPCS3EmbeddedMenuInput.h"
#include "RPCS3PadMerge.h"

#import <GameController/GameController.h>
#import <QuartzCore/QuartzCore.h>
#import <neo_touch_layout/NeoTouchLayout.h>
#include <math.h>
#include <stddef.h>

static const char* const kRPCS3InputMarker = "NEOSTATION_RPCS3_INPUT_V1";

static_assert(sizeof(rpcs3_ios_pad_state) == 40, "RPCS3 iOS pad ABI size drift");
static_assert(offsetof(rpcs3_ios_pad_state, size) == 0, "RPCS3 iOS pad struct_size offset drift");
static_assert(offsetof(rpcs3_ios_pad_state, connected) == 4, "RPCS3 iOS pad connected offset drift");
static_assert(offsetof(rpcs3_ios_pad_state, buttons) == 8, "RPCS3 iOS pad buttons offset drift");
static_assert(offsetof(rpcs3_ios_pad_state, left_x) == 16, "RPCS3 iOS pad left stick offset drift");
static_assert(offsetof(rpcs3_ios_pad_state, l2) == 32, "RPCS3 iOS pad trigger offset drift");

static inline float RPCS3Clamp(float value, float minimum, float maximum) {
  return fminf(maximum, fmaxf(minimum, value));
}

static inline void RPCS3SetBit(uint64_t* bits, uint64_t bit, BOOL pressed) {
  if (pressed) *bits |= bit;
  else *bits &= ~bit;
}

@interface RPCS3GameInputController () {
  RPCS3EmbeddedMenuInput _menuInput;
  rpcs3_ios_pad_state _touchState;
  rpcs3_ios_pad_state _physicalState;
}
@property(nonatomic, weak) UIView* hostView;
@property(nonatomic, assign) rpcs3_ios_api* api;
@property(nonatomic, strong) RPCS3TouchControlsView* touchOverlay;
@property(nonatomic, strong, nullable) GCController* physicalController;
@property(nonatomic, strong, nullable) NeoTouchControllerMonitor* controllerMonitor;
@property(nonatomic, assign) BOOL started;
@property(nonatomic, assign, readwrite, getter=isEditingTouchLayout) BOOL editingTouchLayout;
@property(nonatomic, weak, readwrite, nullable) UIView* activeEditor;
@property(nonatomic, copy) NSString* locale;
@end

@implementation RPCS3GameInputController

- (instancetype)initWithHostView:(UIView*)hostView api:(rpcs3_ios_api*)api {
  return [self initWithHostView:hostView api:api locale:nil];
}

- (instancetype)initWithHostView:(UIView*)hostView api:(rpcs3_ios_api*)api locale:(NSString*)locale {
  self = [super init];
  if (self) {
    _hostView = hostView;
    _api = api;
    _locale = [locale copy] ?: NSLocale.preferredLanguages.firstObject ?: @"en";
    memset(&_touchState, 0, sizeof(_touchState));
    _touchState.size = sizeof(_touchState);
    _touchState.connected = 1;
    memset(&_physicalState, 0, sizeof(_physicalState));
    _physicalState.size = sizeof(_physicalState);
    _touchControlsEnabled = YES;
    [self installTouchOverlay];
  }
  return self;
}

- (RPCS3TouchControlsView*)touchControls {
  return self.touchOverlay;
}

- (void)installTouchOverlay {
  UIView* host = self.hostView;
  if (!host) return;

  // Build 484: the controls are the elements of the "ps3" touch layout
  // (RPCS3TouchControls.mm); this controller keeps the pad state.
  self.touchOverlay = [[RPCS3TouchControlsView alloc] initWithLocale:self.locale];
  self.touchOverlay.frame = host.bounds;
  self.touchOverlay.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
  [host addSubview:self.touchOverlay];

  __weak RPCS3GameInputController* weakSelf = self;
  self.touchOverlay.buttonChanged = ^(uint64_t bit, BOOL pressed) {
    RPCS3GameInputController* strongSelf = weakSelf;
    if (!strongSelf) return;
    if (pressed) [strongSelf touchButtonDown:bit];
    else [strongSelf touchButtonUp:bit];
  };
  self.touchOverlay.stickChanged = ^(NSInteger stick, float x, float y) {
    RPCS3GameInputController* strongSelf = weakSelf;
    if (!strongSelf) return;
    if (stick == 0) {
      strongSelf->_touchState.left_x = x;
      strongSelf->_touchState.left_y = y;
    } else {
      strongSelf->_touchState.right_x = x;
      strongSelf->_touchState.right_y = y;
    }
    [strongSelf sendTouchState];
  };
}

- (void)setGameKey:(NSString*)gameKey {
  _gameKey = [gameKey copy];
  self.touchOverlay.gameKey = gameKey;
}

- (void)start {
  if (self.started) return;
  self.started = YES;
  NSLog(@"%s: direct RPCS3 physical/touch input active", kRPCS3InputMarker);
  NSNotificationCenter* center = NSNotificationCenter.defaultCenter;
  [center addObserver:self selector:@selector(controllerDidConnect:) name:GCControllerDidConnectNotification object:nil];
  [center addObserver:self selector:@selector(controllerDidDisconnect:) name:GCControllerDidDisconnectNotification object:nil];
  [center addObserver:self selector:@selector(touchPreferenceChanged:)
                 name:NeoTouchControllerPreferenceDidChangeNotification object:nil];
  __weak RPCS3GameInputController* weakSelf = self;
  self.controllerMonitor = [[NeoTouchControllerMonitor alloc] initWithChangeHandler:^(__unused BOOL connected) {
    [weakSelf updateTouchVisibility];
  }];
  [self selectFirstPhysicalController];
  [self updateTouchVisibility];
}

- (void)stop {
  if (!self.started) return;
  self.started = NO;
  [NSNotificationCenter.defaultCenter removeObserver:self name:GCControllerDidConnectNotification object:nil];
  [NSNotificationCenter.defaultCenter removeObserver:self name:GCControllerDidDisconnectNotification object:nil];
  [NSNotificationCenter.defaultCenter removeObserver:self name:NeoTouchControllerPreferenceDidChangeNotification
                                              object:nil];
  [self.controllerMonitor invalidate];
  self.controllerMonitor = nil;
  [self unbindPhysicalController];
  [self releaseTouchInput];
  [self clearCorePadState];
  self.touchOverlay.hidden = YES;
}

- (BOOL)isUsableController:(GCController*)controller {
  return controller.extendedGamepad != nil || controller.microGamepad != nil;
}

- (void)selectFirstPhysicalController {
  if (self.physicalController) return;
  for (GCController* controller in [GCController controllers]) {
    if ([self isUsableController:controller]) {
      [self bindPhysicalController:controller];
      return;
    }
  }
}

- (void)controllerDidConnect:(NSNotification*)notification {
  GCController* controller = [notification.object isKindOfClass:GCController.class] ? notification.object : nil;
  if (!controller || self.physicalController || ![self isUsableController:controller]) return;
  [self bindPhysicalController:controller];
}

- (void)controllerDidDisconnect:(NSNotification*)notification {
  GCController* controller = [notification.object isKindOfClass:GCController.class] ? notification.object : nil;
  if (!controller || controller != self.physicalController) return;
  [self unbindPhysicalController];
  [self clearCorePadState];
  [self selectFirstPhysicalController];
  [self updateTouchVisibility];
}

- (void)touchPreferenceChanged:(NSNotification*)notification {
  NSString* console = notification.userInfo[@"console"];
  if (!console || [console isEqualToString:@"ps3"]) [self updateTouchVisibility];
}

- (void)bindPhysicalController:(GCController*)controller {
  [self unbindPhysicalController];
  self.physicalController = controller;
  memset(&_physicalState, 0, sizeof(_physicalState));
  _physicalState.size = sizeof(_physicalState);
  _physicalState.connected = 1;
  [self clearCorePadState];

  __weak RPCS3GameInputController* weakSelf = self;
  if (controller.extendedGamepad) {
    GCExtendedGamepad* pad = controller.extendedGamepad;
    pad.valueChangedHandler = ^(GCExtendedGamepad* gamepad, GCControllerElement* element) {
      dispatch_async(dispatch_get_main_queue(), ^{
        RPCS3GameInputController* strongSelf = weakSelf;
        if (strongSelf && strongSelf.physicalController == controller) {
          [strongSelf updateFromExtendedGamepad:gamepad];
        }
      });
    };
    [self updateFromExtendedGamepad:pad];
  } else if (controller.microGamepad) {
    GCMicroGamepad* pad = controller.microGamepad;
    pad.valueChangedHandler = ^(GCMicroGamepad* gamepad, GCControllerElement* element) {
      dispatch_async(dispatch_get_main_queue(), ^{
        RPCS3GameInputController* strongSelf = weakSelf;
        if (strongSelf && strongSelf.physicalController == controller) {
          [strongSelf updateFromMicroGamepad:gamepad];
        }
      });
    };
    [self updateFromMicroGamepad:pad];
  }
  [self updateTouchVisibility];
}

- (void)unbindPhysicalController {
  GCController* controller = self.physicalController;
  if (!controller) return;
  if (controller.extendedGamepad) controller.extendedGamepad.valueChangedHandler = nil;
  if (controller.microGamepad) controller.microGamepad.valueChangedHandler = nil;
  self.physicalController = nil;
  memset(&_physicalState, 0, sizeof(_physicalState));
  _physicalState.size = sizeof(_physicalState);
}

- (GCControllerButtonInput*)optionalButtonOnProfile:(id)profile key:(NSString*)key {
  @try {
    id value = [profile valueForKey:key];
    return [value isKindOfClass:GCControllerButtonInput.class] ? value : nil;
  } @catch (__unused NSException* exception) {
    return nil;
  }
}

- (void)updateFromExtendedGamepad:(GCExtendedGamepad*)pad {
  if (!self.started || !pad || !self.physicalController) return;
  rpcs3_ios_pad_state state = {};
  state.size = sizeof(state);
  state.connected = 1;

  RPCS3SetBit(&state.buttons, rpcs3_ios_pad_up, pad.dpad.up.isPressed);
  RPCS3SetBit(&state.buttons, rpcs3_ios_pad_down, pad.dpad.down.isPressed);
  RPCS3SetBit(&state.buttons, rpcs3_ios_pad_left, pad.dpad.left.isPressed);
  RPCS3SetBit(&state.buttons, rpcs3_ios_pad_right, pad.dpad.right.isPressed);
  RPCS3SetBit(&state.buttons, rpcs3_ios_pad_cross, pad.buttonA.isPressed);
  RPCS3SetBit(&state.buttons, rpcs3_ios_pad_circle, pad.buttonB.isPressed);
  RPCS3SetBit(&state.buttons, rpcs3_ios_pad_square, pad.buttonX.isPressed);
  RPCS3SetBit(&state.buttons, rpcs3_ios_pad_triangle, pad.buttonY.isPressed);
  RPCS3SetBit(&state.buttons, rpcs3_ios_pad_l1, pad.leftShoulder.isPressed);
  RPCS3SetBit(&state.buttons, rpcs3_ios_pad_r1, pad.rightShoulder.isPressed);

  state.l2 = RPCS3Clamp(pad.leftTrigger.value, 0.0f, 1.0f);
  state.r2 = RPCS3Clamp(pad.rightTrigger.value, 0.0f, 1.0f);
  RPCS3SetBit(&state.buttons, rpcs3_ios_pad_l2, pad.leftTrigger.isPressed || state.l2 > 0.01f);
  RPCS3SetBit(&state.buttons, rpcs3_ios_pad_r2, pad.rightTrigger.isPressed || state.r2 > 0.01f);

  state.left_x = RPCS3Clamp(pad.leftThumbstick.xAxis.value, -1.0f, 1.0f);
  state.left_y = RPCS3Clamp(pad.leftThumbstick.yAxis.value, -1.0f, 1.0f);
  state.right_x = RPCS3Clamp(pad.rightThumbstick.xAxis.value, -1.0f, 1.0f);
  state.right_y = RPCS3Clamp(pad.rightThumbstick.yAxis.value, -1.0f, 1.0f);

  GCControllerButtonInput* leftThumb = [self optionalButtonOnProfile:pad key:@"leftThumbstickButton"];
  GCControllerButtonInput* rightThumb = [self optionalButtonOnProfile:pad key:@"rightThumbstickButton"];
  GCControllerButtonInput* options = [self optionalButtonOnProfile:pad key:@"buttonOptions"];
  GCControllerButtonInput* menu = [self optionalButtonOnProfile:pad key:@"buttonMenu"];
  GCControllerButtonInput* home = [self optionalButtonOnProfile:pad key:@"buttonHome"];
  RPCS3SetBit(&state.buttons, rpcs3_ios_pad_l3, leftThumb.isPressed);
  RPCS3SetBit(&state.buttons, rpcs3_ios_pad_r3, rightThumb.isPressed);
  RPCS3SetBit(&state.buttons, rpcs3_ios_pad_select, options.isPressed);
  RPCS3SetBit(&state.buttons, rpcs3_ios_pad_start, menu.isPressed);
  RPCS3SetBit(&state.buttons, rpcs3_ios_pad_ps, home.isPressed);

  _physicalState = state;
  [self sendMergedState];
}

- (void)updateFromMicroGamepad:(GCMicroGamepad*)pad {
  if (!self.started || !pad || !self.physicalController) return;
  rpcs3_ios_pad_state state = {};
  state.size = sizeof(state);
  state.connected = 1;
  RPCS3SetBit(&state.buttons, rpcs3_ios_pad_up, pad.dpad.up.isPressed);
  RPCS3SetBit(&state.buttons, rpcs3_ios_pad_down, pad.dpad.down.isPressed);
  RPCS3SetBit(&state.buttons, rpcs3_ios_pad_left, pad.dpad.left.isPressed);
  RPCS3SetBit(&state.buttons, rpcs3_ios_pad_right, pad.dpad.right.isPressed);
  RPCS3SetBit(&state.buttons, rpcs3_ios_pad_cross, pad.buttonA.isPressed);
  RPCS3SetBit(&state.buttons, rpcs3_ios_pad_square, pad.buttonX.isPressed);
  _physicalState = state;
  [self sendMergedState];
}

- (void)touchButtonDown:(uint64_t)bit {
  if (!self.started || self.editingTouchLayout) return;
  _touchState.buttons |= bit;
  if (bit == rpcs3_ios_pad_l2) _touchState.l2 = 1.0f;
  if (bit == rpcs3_ios_pad_r2) _touchState.r2 = 1.0f;
  [self sendTouchState];
}

- (void)touchButtonUp:(uint64_t)bit {
  _touchState.buttons &= ~bit;
  if (bit == rpcs3_ios_pad_l2) _touchState.l2 = 0.0f;
  if (bit == rpcs3_ios_pad_r2) _touchState.r2 = 0.0f;
  [self sendTouchState];
}

- (void)sendTouchState {
  _touchState.size = sizeof(_touchState);
  _touchState.connected = 1;
  [self sendMergedState];
}

- (BOOL)touchActive {
  return !self.touchOverlay.hidden && self.touchOverlay.userInteractionEnabled && !self.editingTouchLayout;
}

/// Touch and physical controller feed one pad (RPCS3PadMerge.h). While the
/// editor is open the pad stays connected with nothing pressed.
- (void)sendMergedState {
  if (!self.started) return;
  rpcs3_ios_pad_state gameplay = {};
  gameplay.size = sizeof(gameplay);
  gameplay.connected = 1;
  if (!self.editingTouchLayout) {
    gameplay = RPCS3MergePadStates(&_touchState, [self touchActive] ? 1 : 0,
                                   &_physicalState, self.physicalController != nil ? 1 : 0);
  }
  [self sendState:&gameplay];
}

- (void)sendState:(const rpcs3_ios_pad_state*)state {
  if (!state || !_api || !_api->set_pad_state) return;
  rpcs3_ios_pad_state gameplayState = *state;
  const bool openMenu = _menuInput.consume(gameplayState);
  _api->set_pad_state(0, &gameplayState);
  if (openMenu && self.started && self.menuRequested) self.menuRequested();
}

- (void)clearCorePadState {
  _menuInput.reset();
  rpcs3_ios_pad_state state = {};
  state.size = sizeof(state);
  state.connected = 0;
  [self sendState:&state];
}

/// Every touch control released (visuals and pad state).
- (void)releaseTouchInput {
  [self.touchOverlay releaseAllInput];
  memset(&_touchState, 0, sizeof(_touchState));
  _touchState.size = sizeof(_touchState);
  _touchState.connected = 1;
}

- (void)setTouchControlsEnabled:(BOOL)touchControlsEnabled {
  if (_touchControlsEnabled == touchControlsEnabled) return;
  _touchControlsEnabled = touchControlsEnabled;
  [self updateTouchVisibility];
}

// Build 484: hidden (and released) while a compatible controller is connected
// if the PS3 preference says so (default), or when the Touch Controls switch
// is off; always shown while the editor is open, without input.
- (void)updateTouchVisibility {
  const BOOL showTouch = !NeoTouchControlsShouldHide(@"ps3", self.controllerMonitor.connected,
                                                     self.touchControlsEnabled, !self.started,
                                                     self.editingTouchLayout);
  if (!showTouch && !self.touchOverlay.hidden) [self releaseTouchInput];
  self.touchOverlay.hidden = !showTouch;
  self.touchOverlay.userInteractionEnabled = showTouch && !self.editingTouchLayout;
  [self sendMergedState];
}

- (void)beginTouchLayoutEditingWithTitle:(NSString*)title completion:(dispatch_block_t)completion {
  if (self.editingTouchLayout || !self.touchOverlay || !self.started) {
    if (completion) completion();
    return;
  }
  self.editingTouchLayout = YES;
  [self releaseTouchInput];
  [self updateTouchVisibility];
  NeoTouchLayoutEditor* editor = [[NeoTouchLayoutEditor alloc] initWithHost:self.touchOverlay
      layoutKey:NeoTouchLayoutKeyPlayStation3 gameKey:self.touchOverlay.gameKey title:title
      locale:self.locale store:NeoTouchLayoutStore.sharedStore];
  editor.controllerConnected = self.controllerMonitor.connected;
  __weak RPCS3GameInputController* weakSelf = self;
  editor.finished = ^(__unused BOOL saved) {
    RPCS3GameInputController* strongSelf = weakSelf;
    if (!strongSelf) return;
    strongSelf.editingTouchLayout = NO;
    [strongSelf.touchOverlay endEditingOverride];
    [strongSelf updateTouchVisibility];
    if (completion) completion();
  };
  self.activeEditor = editor;
  [editor presentOverCanvas];
}

- (void)layoutControlsInBounds:(CGRect)bounds safeAreaInsets:(UIEdgeInsets)insets {
  if (!self.touchOverlay) return;
  // The overlay places the stock controls from its own safe area (the host's)
  // and adds the stored layout.
  self.touchOverlay.frame = bounds;
  [self.touchOverlay setNeedsLayout];
}

- (void)dealloc {
  [self stop];
}

@end

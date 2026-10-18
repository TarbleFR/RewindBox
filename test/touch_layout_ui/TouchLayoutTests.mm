// SPDX-License-Identifier: GPL-3.0-or-later
// Build 484: UIKit behaviour of the touch-controls editor and of the
// controller policy on the real touch controls of the three embedded engines:
// Dolphin's DolphiniOS controls with the original compiled nibs of the
// validated Build 350 donor (GameCube, Wii Remote + Nunchuk, Classic
// Controller), the ARMSX2 controls (PS2) and the RPCS3 controls driven by the
// production RPCS3GameInputController (PS3). Run by
// test/touch_layout_ui_test.py in the iOS Simulator: no emulator core runs.
// Dolphin's touch events are recorded by TouchLayoutTestSupport.mm, the RPCS3
// pad reaches a stand-in rpcs3_ios_api, ARMSX2 reports through the control
// view's callbacks as the session does.
//
// Touches are synthesised without private API: a control under a point is
// found with UIKit hit testing (through every layout transform) and pressed
// with its control events, sticks and the Dolphin D-pad receive stand-in
// gesture recognisers, the editor receives stand-in UITouch objects. The
// interface really rotates (UIWindowScene geometry request).
#import <XCTest/XCTest.h>
#import <UIKit/UIKit.h>
#import <UIKit/UIGestureRecognizerSubclass.h>
#import <neo_touch_layout/NeoTouchLayout.h>
#import <dolphin_internal_bridge/dolphin_internal_bridge-Swift.h>
#import "DOLTouchLayout.h"
#import "Armsx2TouchControls.h"
#import "RPCS3TouchControls.h"
#import "RPCS3GameInputController.h"
#include "Rpcs3CoreABI.h"
#include <cmath>
#include <unistd.h>

extern "C" NSDictionary<NSString*, NSNumber*>* TLDolphinInputs(void);
extern "C" NSUInteger TLDolphinEventCount(void);
extern "C" void TLDolphinResetInputs(void);

// Gesture handlers of the original controls (Swift @objc, Objective-C private).
@interface UIView (TLDolphinGestures)
- (void)handleLongPressWithGesture:(UILongPressGestureRecognizer*)gesture;
- (void)handlePanWithGesture:(UIPanGestureRecognizer*)gesture;
@end
@interface Armsx2VirtualStickView (TLGestures)
- (void)handlePan:(UIPanGestureRecognizer*)pan;
@end
@interface RPCS3TouchStickView (TLGestures)
- (void)updateFromPoint:(CGPoint)point;
@end

static NSArray<NSString*>* TLKeys(void) {
  return @[@"gc", @"wii", @"wii-classic", @"ps2", @"ps3"];
}

#pragma mark Stand-in touches and gestures

@interface TLFakeTouch : UITouch
@property(nonatomic) CGPoint point;
@property(nonatomic, weak) UIView* reference;
@end
@implementation TLFakeTouch
- (CGPoint)locationInView:(UIView*)view {
  UIView* reference = self.reference;
  return reference && view ? [reference convertPoint:self.point toView:view] : self.point;
}
- (CGPoint)previousLocationInView:(UIView*)view {
  return [self locationInView:view];
}
- (UIView*)view {
  return nil;
}
@end

@interface TLFakePan : UIPanGestureRecognizer
@property(nonatomic) UIGestureRecognizerState fakeState;
@property(nonatomic, weak) UIView* fakeView;
@property(nonatomic, weak) UIView* locationView;
@property(nonatomic) CGPoint location;
@property(nonatomic) CGPoint translation;
@end
@implementation TLFakePan
- (UIGestureRecognizerState)state {
  return self.fakeState;
}
- (UIView*)view {
  return self.fakeView;
}
- (CGPoint)locationInView:(UIView*)view {
  return [self.locationView convertPoint:self.location toView:view];
}
- (CGPoint)translationInView:(UIView*)view {
  return self.translation;
}
@end

@interface TLFakeLongPress : UILongPressGestureRecognizer
@property(nonatomic) UIGestureRecognizerState fakeState;
@property(nonatomic, weak) UIView* fakeView;
@property(nonatomic) CGPoint location;
@end
@implementation TLFakeLongPress
- (UIGestureRecognizerState)state {
  return self.fakeState;
}
- (UIView*)view {
  return self.fakeView;
}
- (CGPoint)locationInView:(UIView*)view {
  return [self.fakeView convertPoint:self.location toView:view];
}
@end

#pragma mark Helpers

static UIWindow* TLWindow(void) {
  return [(id)UIApplication.sharedApplication.delegate window];
}

static void TLSpin(NSTimeInterval seconds) {
  [NSRunLoop.mainRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:seconds]];
}

static BOOL TLLandscape(UIView* view) {
  return view.bounds.size.width > view.bounds.size.height;
}

/// Rotates the interface like the device would (iOS 16 geometry request).
static BOOL TLRotate(BOOL landscape) {
  UIWindow* window = TLWindow();
  if (TLLandscape(window) == landscape) return YES;
  [window.rootViewController setNeedsUpdateOfSupportedInterfaceOrientations];
  UIWindowSceneGeometryPreferencesIOS* preferences = [[UIWindowSceneGeometryPreferencesIOS alloc]
      initWithInterfaceOrientations:landscape ? UIInterfaceOrientationMaskLandscapeRight
                                              : UIInterfaceOrientationMaskPortrait];
  __block NSError* failure = nil;
  [window.windowScene requestGeometryUpdateWithPreferences:preferences errorHandler:^(NSError* error) {
    failure = error;
  }];
  for (NSInteger step = 0; step < 200 && TLLandscape(window) != landscape && !failure; step++) TLSpin(0.05);
  TLSpin(0.3);
  [window layoutIfNeeded];
  if (failure) NSLog(@"[TouchLayoutTests] rotation refused: %@", failure);
  return TLLandscape(window) == landscape;
}

static CGPoint TLMid(CGRect rect) {
  return CGPointMake(CGRectGetMidX(rect), CGRectGetMidY(rect));
}

static CGRect TLFrame(UIView* view, UIView* target) {
  return [view convertRect:view.bounds toView:target];
}

static BOOL TLNear(CGFloat a, CGFloat b, CGFloat tolerance) {
  return std::fabs(a - b) <= tolerance;
}

static BOOL TLRectNear(CGRect a, CGRect b, CGFloat tolerance) {
  return TLNear(a.origin.x, b.origin.x, tolerance) && TLNear(a.origin.y, b.origin.y, tolerance) &&
         TLNear(a.size.width, b.size.width, tolerance) && TLNear(a.size.height, b.size.height, tolerance);
}

static UIControl* TLControlAt(UIView* container, CGPoint point) {
  UIView* hit = [container hitTest:point withEvent:nil];
  for (UIView* view = hit; view && view != container; view = view.superview)
    if ([view isKindOfClass:UIControl.class]) return (UIControl*)view;
  return nil;
}

/// A finger lands on `point` (container coordinates) and stays: the control
/// UIKit hit-tests there is tracked (highlighted) and receives Touch Down.
static UIControl* TLPress(UIView* container, CGPoint point) {
  UIControl* control = TLControlAt(container, point);
  if (!control) return nil;
  control.highlighted = YES;
  [control sendActionsForControlEvents:UIControlEventTouchDown];
  return control;
}

static void TLLift(UIControl* control) {
  if (!control) return;
  control.highlighted = NO;
  [control sendActionsForControlEvents:UIControlEventTouchUpInside];
}

static void TLResetStore(void) {
  [NSFileManager.defaultManager removeItemAtPath:NeoTouchLayoutStore.defaultDirectory error:nil];
  for (NSString* console in @[@"gc", @"wii", @"ps2", @"ps3"])
    [NSUserDefaults.standardUserDefaults removeObjectForKey:NeoTouchHideWithControllerDefaultsKey(console)];
}

static BOOL TLHasButtonTitled(UIView* root, NSString* title) {
  if ([root isKindOfClass:UIButton.class]) {
    UIButton* button = (UIButton*)root;
    if ([[button titleForState:UIControlStateNormal] isEqualToString:title] ||
        [button.configuration.title isEqualToString:title] || [button.accessibilityLabel isEqualToString:title])
      return YES;
  }
  for (UIView* child in root.subviews)
    if (TLHasButtonTitled(child, title)) return YES;
  return NO;
}

static NeoTouchElement* TLElement(NSArray<NeoTouchElement*>* elements, NSString* identifier) {
  for (NeoTouchElement* element in elements)
    if ([element.identifier isEqualToString:identifier]) return element;
  return nil;
}

static NeoTouchElement* TLFirstOfKind(NSArray<NeoTouchElement*>* elements, NeoTouchElementKind kind,
                                      NSArray<NSString*>* excluding) {
  for (NeoTouchElement* element in elements) {
    if (element.kind != kind || !element.view || element.view.hidden) continue;
    if ([excluding containsObject:element.identifier]) continue;
    if (kind == NeoTouchElementKindButton && ![element.view isKindOfClass:UIControl.class]) continue;
    return element;
  }
  return nil;
}

static NSInteger TLSuffix(NSString* identifier) {
  return [[identifier componentsSeparatedByString:@"."].lastObject integerValue];
}

#pragma mark Fixtures

/// One engine's real touch controls in a full-window container.
@interface TLFixture : NSObject
@property(nonatomic, copy, readonly) NSString* key;
@property(nonatomic, strong, readonly) UIView* container;
@property(nonatomic) NSUInteger orientationChanges;
+ (TLFixture*)fixtureForKey:(NSString*)key;
- (instancetype)initWithKey:(NSString*)key;
- (UIView*)canvas;
- (id<NeoTouchLayoutEditorHost>)host;
- (NSArray<NeoTouchElement*>*)elements;
- (void)layout;
- (void)setGameKey:(NSString*)game;
- (void)endEditing;
/// Inputs the engine currently receives as non-neutral, with their values.
- (NSDictionary<NSString*, NSNumber*>*)values;
- (NSSet<NSString*>*)active;
/// The engine's own "release everything" path (hide, rotation, editor).
- (void)releaseAll;
- (NSString*)inputForButton:(NeoTouchElement*)button;
- (void)deflect:(NeoTouchElement*)stick toward:(CGPoint)containerPoint;
- (void)endStick:(NeoTouchElement*)stick;
- (NSString*)rightInputForStick:(NeoTouchElement*)stick;
- (NSSet<NSString*>*)pressUpLeft:(NeoTouchElement*)dpad;
- (void)endDPad:(NeoTouchElement*)dpad;
- (void)remove;
@end

@interface TLDolphinFixture : TLFixture
@property(nonatomic, strong) DOLTouchOverlay* overlay;
@property(nonatomic, strong) DOLTouchLayout* touchLayout;
@property(nonatomic) NSInteger port;
@end

@interface TLArmsx2Fixture : TLFixture
@property(nonatomic, strong) Armsx2TouchControlsView* controls;
@property(nonatomic, strong) NSMutableDictionary<NSString*, NSNumber*>* state;
@property(nonatomic, strong) NSMutableArray<UIControl*>* heldDPad;
@end

@interface TLRpcs3Fixture : TLFixture
@property(nonatomic, strong) RPCS3GameInputController* controller;
@property(nonatomic, strong) NSMutableArray<UIControl*>* heldDPad;
@end

static rpcs3_ios_pad_state gTLPad;
static NSUInteger gTLPadCalls;
static rpcs3_ios_status TLSetPad(uint32_t port, const rpcs3_ios_pad_state* state) {
  if (port == 0 && state) gTLPad = *state;
  gTLPadCalls++;
  return 0;
}

@implementation TLFixture

+ (TLFixture*)fixtureForKey:(NSString*)key {
  if ([key isEqualToString:@"ps2"]) return [[TLArmsx2Fixture alloc] initWithKey:key];
  if ([key isEqualToString:@"ps3"]) return [[TLRpcs3Fixture alloc] initWithKey:key];
  return [[TLDolphinFixture alloc] initWithKey:key];
}

- (instancetype)initWithKey:(NSString*)key {
  self = [super init];
  if (self) {
    _key = [key copy];
    UIView* root = TLWindow().rootViewController.view;
    _container = [[UIView alloc] initWithFrame:root.bounds];
    _container.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    [root addSubview:_container];
  }
  return self;
}

- (UIView*)canvas { return nil; }
- (id<NeoTouchLayoutEditorHost>)host { return nil; }
- (NSArray<NeoTouchElement*>*)elements { return [[self host] touchLayoutElements]; }
- (void)layout {
  [TLWindow() layoutIfNeeded];
  [self.container layoutIfNeeded];
  [[self canvas] setNeedsLayout];
  [[self canvas] layoutIfNeeded];
}
- (void)setGameKey:(NSString*)game {}
- (void)endEditing {}
- (NSDictionary<NSString*, NSNumber*>*)values { return @{}; }
- (NSSet<NSString*>*)active {
  NSMutableSet* active = [NSMutableSet set];
  [[self values] enumerateKeysAndObjectsUsingBlock:^(NSString* key, NSNumber* value, BOOL*) {
    if (std::fabs(value.doubleValue) > 0.05) [active addObject:key];
  }];
  return active;
}
- (void)releaseAll {}
- (NSString*)inputForButton:(NeoTouchElement*)button { return @"b" @"?"; }
- (void)deflect:(NeoTouchElement*)stick toward:(CGPoint)containerPoint {}
- (void)endStick:(NeoTouchElement*)stick {}
- (NSString*)rightInputForStick:(NeoTouchElement*)stick { return @"?"; }
- (NSSet<NSString*>*)pressUpLeft:(NeoTouchElement*)dpad { return [NSSet set]; }
- (void)endDPad:(NeoTouchElement*)dpad {}
- (void)remove { [self.container removeFromSuperview]; }
@end

@implementation TLDolphinFixture

- (instancetype)initWithKey:(NSString*)key {
  self = [super initWithKey:key];
  if (self) {
    const BOOL wii = ![key isEqualToString:NeoTouchLayoutKeyGameCube];
    _port = wii ? 4 : 0;
    _overlay = [[DOLTouchOverlay alloc] initWithWii:wii];
    if ([key isEqualToString:NeoTouchLayoutKeyWiiClassic]) [_overlay updateExtension:@"Classic"];
    _overlay.frame = self.container.bounds;
    _overlay.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    [self.container addSubview:_overlay];
    _touchLayout = [[DOLTouchLayout alloc] initWithOverlay:_overlay locale:@"fr"];
    __weak TLDolphinFixture* weakSelf = self;
    _touchLayout.orientationChanged = ^{ weakSelf.orientationChanges++; };
    [self layout];
    TLDolphinResetInputs();
  }
  return self;
}

- (UIView*)canvas { return self.overlay; }
- (id<NeoTouchLayoutEditorHost>)host { return self.touchLayout; }
- (void)setGameKey:(NSString*)game { self.touchLayout.gameKey = game; }
- (void)endEditing { [self.touchLayout endEditingOverride]; }

- (NSDictionary<NSString*, NSNumber*>*)values {
  return TLDolphinInputs();
}

- (void)releaseAll { [self.overlay cancelTouchInteractions]; }

- (NSString*)inputForButton:(NeoTouchElement*)button {
  const NSInteger control = TLSuffix(button.identifier);
  return [NSString stringWithFormat:@"%@%ld.%ld", button.kind == NeoTouchElementKindTrigger ? @"a" : @"b",
                                    (long)self.port, (long)control];
}

- (void)driveStick:(NeoTouchElement*)stick state:(UIGestureRecognizerState)state point:(CGPoint)containerPoint {
  UIView* joystick = stick.view;
  TLFakePan* pan = [[TLFakePan alloc] initWithTarget:nil action:NULL];
  pan.fakeState = state;
  pan.fakeView = joystick.subviews.lastObject;
  pan.locationView = joystick;
  pan.location = [self.container convertPoint:containerPoint toView:joystick];
  [joystick handlePanWithGesture:pan];
}

- (void)deflect:(NeoTouchElement*)stick toward:(CGPoint)containerPoint {
  [self driveStick:stick state:UIGestureRecognizerStateChanged point:containerPoint];
}

- (void)endStick:(NeoTouchElement*)stick {
  [self driveStick:stick state:UIGestureRecognizerStateEnded point:CGPointZero];
}

- (NSString*)rightInputForStick:(NeoTouchElement*)stick {
  // TCJoystick sends up, down, left, right halves on joystickType + 1...4.
  return [NSString stringWithFormat:@"a%ld.%ld", (long)self.port, (long)(TLSuffix(stick.identifier) + 4)];
}

- (UIImageView*)dpadImage:(NeoTouchElement*)dpad {
  for (UIView* child in dpad.view.subviews)
    if ([child isKindOfClass:UIImageView.class]) return (UIImageView*)child;
  return nil;
}

- (NSSet<NSString*>*)pressUpLeft:(NeoTouchElement*)dpad {
  UIImageView* image = [self dpadImage:dpad];
  if (!image) return [NSSet setWithObject:@"no D-pad image"];
  TLFakeLongPress* press = [[TLFakeLongPress alloc] initWithTarget:nil action:NULL];
  press.fakeState = UIGestureRecognizerStateBegan;
  press.fakeView = image;
  press.location = CGPointMake(image.bounds.size.width * 0.12, image.bounds.size.height * 0.12);
  [dpad.view handleLongPressWithGesture:press];
  const NSInteger base = TLSuffix(dpad.identifier);
  return [NSSet setWithObjects:[NSString stringWithFormat:@"b%ld.%ld", (long)self.port, (long)base],
                               [NSString stringWithFormat:@"b%ld.%ld", (long)self.port, (long)(base + 2)], nil];
}

- (void)endDPad:(NeoTouchElement*)dpad {
  UIImageView* image = [self dpadImage:dpad];
  TLFakeLongPress* press = [[TLFakeLongPress alloc] initWithTarget:nil action:NULL];
  press.fakeState = UIGestureRecognizerStateEnded;
  press.fakeView = image;
  [dpad.view handleLongPressWithGesture:press];
}

@end

@implementation TLArmsx2Fixture

- (instancetype)initWithKey:(NSString*)key {
  self = [super initWithKey:key];
  if (self) {
    _state = [NSMutableDictionary dictionary];
    _heldDPad = [NSMutableArray array];
    _controls = [[Armsx2TouchControlsView alloc] initWithLocale:@"fr"];
    _controls.frame = self.container.bounds;
    _controls.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    [self.container addSubview:_controls];
    __weak TLArmsx2Fixture* weakSelf = self;
    _controls.buttonChanged = ^(uint32_t button, BOOL pressed) {
      weakSelf.state[[NSString stringWithFormat:@"b%u", button]] = @(pressed ? 1 : 0);
    };
    _controls.sticksChanged = ^(float lx, float ly, float rx, float ry) {
      TLArmsx2Fixture* fixture = weakSelf;
      fixture.state[@"lx"] = @(lx);
      fixture.state[@"ly"] = @(ly);
      fixture.state[@"rx"] = @(rx);
      fixture.state[@"ry"] = @(ry);
    };
    _controls.orientationChanged = ^{ weakSelf.orientationChanges++; };
    [self layout];
  }
  return self;
}

- (UIView*)canvas { return self.controls; }
- (id<NeoTouchLayoutEditorHost>)host { return self.controls; }
- (void)setGameKey:(NSString*)game { self.controls.gameKey = game; }
- (void)endEditing { [self.controls endEditingOverride]; }
- (NSDictionary<NSString*, NSNumber*>*)values { return [self.state copy]; }
- (void)releaseAll { [self.controls releaseAllInput]; }

- (NSString*)inputForButton:(NeoTouchElement*)button {
  return [NSString stringWithFormat:@"b%ld", (long)button.view.tag];
}

- (void)driveStick:(NeoTouchElement*)stick state:(UIGestureRecognizerState)state point:(CGPoint)containerPoint {
  Armsx2VirtualStickView* view = (Armsx2VirtualStickView*)stick.view;
  const CGPoint local = [self.container convertPoint:containerPoint toView:view];
  TLFakePan* pan = [[TLFakePan alloc] initWithTarget:nil action:NULL];
  pan.fakeState = state;
  pan.fakeView = view;
  pan.locationView = view;
  pan.location = local;
  pan.translation = CGPointMake(local.x - CGRectGetMidX(view.bounds), local.y - CGRectGetMidY(view.bounds));
  [view handlePan:pan];
}

- (void)deflect:(NeoTouchElement*)stick toward:(CGPoint)containerPoint {
  [self driveStick:stick state:UIGestureRecognizerStateChanged point:containerPoint];
}

- (void)endStick:(NeoTouchElement*)stick {
  [self driveStick:stick state:UIGestureRecognizerStateEnded point:CGPointZero];
}

- (NSString*)rightInputForStick:(NeoTouchElement*)stick {
  return [stick.identifier isEqualToString:@"stick.left"] ? @"lx" : @"rx";
}

- (NSSet<NSString*>*)pressUpLeft:(NeoTouchElement*)dpad {
  // Two fingers on the four-button D-pad: Up (0) and Left (2).
  NSMutableSet* expected = [NSMutableSet set];
  for (UIView* child in dpad.view.subviews) {
    if (![child isKindOfClass:UIButton.class] || (child.tag != 0 && child.tag != 2)) continue;
    UIControl* control = TLPress(self.container, [child convertPoint:TLMid(child.bounds) toView:self.container]);
    if (control) [self.heldDPad addObject:control];
    [expected addObject:[NSString stringWithFormat:@"b%ld", (long)child.tag]];
  }
  return expected;
}

- (void)endDPad:(NeoTouchElement*)dpad {
  for (UIControl* control in self.heldDPad) TLLift(control);
  [self.heldDPad removeAllObjects];
}

@end

@implementation TLRpcs3Fixture {
  rpcs3_ios_api _api;
}

- (instancetype)initWithKey:(NSString*)key {
  self = [super initWithKey:key];
  if (self) {
    memset(&_api, 0, sizeof(_api));
    _api.set_pad_state = TLSetPad;
    memset(&gTLPad, 0, sizeof(gTLPad));
    gTLPadCalls = 0;
    _heldDPad = [NSMutableArray array];
    _controller = [[RPCS3GameInputController alloc] initWithHostView:self.container api:&_api locale:@"fr"];
    __weak TLRpcs3Fixture* weakSelf = self;
    _controller.touchControls.orientationChanged = ^{ weakSelf.orientationChanges++; };
    [_controller start];
    [self layout];
  }
  return self;
}

- (UIView*)canvas { return self.controller.touchControls; }
- (id<NeoTouchLayoutEditorHost>)host { return self.controller.touchControls; }
- (void)setGameKey:(NSString*)game { self.controller.gameKey = game; }
- (void)endEditing { [self.controller.touchControls endEditingOverride]; }

- (NSDictionary<NSString*, NSNumber*>*)values {
  NSMutableDictionary* values = [NSMutableDictionary dictionary];
  if (!gTLPad.connected) return values;
  for (int bit = 0; bit < 17; bit++)
    if (gTLPad.buttons & (1ull << bit)) values[[NSString stringWithFormat:@"b%llu", 1ull << bit]] = @1;
  values[@"lx"] = @(gTLPad.left_x);
  values[@"ly"] = @(gTLPad.left_y);
  values[@"rx"] = @(gTLPad.right_x);
  values[@"ry"] = @(gTLPad.right_y);
  values[@"l2"] = @(gTLPad.l2);
  values[@"r2"] = @(gTLPad.r2);
  return values;
}

- (void)releaseAll { [self.controller.touchControls releaseAllInput]; }

- (NSString*)inputForButton:(NeoTouchElement*)button {
  return [NSString stringWithFormat:@"b%llu", (unsigned long long)button.view.tag];
}

- (void)deflect:(NeoTouchElement*)stick toward:(CGPoint)containerPoint {
  RPCS3TouchStickView* view = (RPCS3TouchStickView*)stick.view;
  view.trackingTouch = YES;
  [view updateFromPoint:[self.container convertPoint:containerPoint toView:view]];
}

- (void)endStick:(NeoTouchElement*)stick {
  [(RPCS3TouchStickView*)stick.view endTracking];
}

- (NSString*)rightInputForStick:(NeoTouchElement*)stick {
  return [stick.identifier isEqualToString:@"stick.left"] ? @"lx" : @"rx";
}

- (NSSet<NSString*>*)pressUpLeft:(NeoTouchElement*)dpad {
  NSMutableSet* expected = [NSMutableSet set];
  for (NSString* identifier in @[@"dpad.up", @"dpad.left"]) {
    UIView* button = [self.controller.touchControls controlForIdentifier:identifier];
    UIControl* control = TLPress(self.container, [button convertPoint:TLMid(button.bounds) toView:self.container]);
    if (control) [self.heldDPad addObject:control];
    [expected addObject:[NSString stringWithFormat:@"b%llu", (unsigned long long)button.tag]];
  }
  return expected;
}

- (void)endDPad:(NeoTouchElement*)dpad {
  for (UIControl* control in self.heldDPad) TLLift(control);
  [self.heldDPad removeAllObjects];
}

- (void)remove {
  [self.controller stop];
  [super remove];
}

@end

#pragma mark Shared policy

@interface TLPolicyTests : XCTestCase
@end

@implementation TLPolicyTests

- (void)setUp {
  [super setUp];
  TLResetStore();
}

- (void)tearDown {
  NeoTouchControllerMonitorSetTestingCount(-1);
  TLResetStore();
  [super tearDown];
}

- (void)testPreferenceIsOnByDefaultPerConsoleAndNotifies {
  for (NSString* console in @[@"gc", @"wii", @"ps2", @"ps3"]) XCTAssertTrue(NeoTouchHidesControlsWithController(console));
  __block NSDictionary* info = nil;
  id token = [NSNotificationCenter.defaultCenter addObserverForName:NeoTouchControllerPreferenceDidChangeNotification
      object:nil queue:nil usingBlock:^(NSNotification* note) { info = note.userInfo; }];
  NeoTouchSetHidesControlsWithController(@"wii", NO);
  [NSNotificationCenter.defaultCenter removeObserver:token];
  XCTAssertEqualObjects(info[@"console"], @"wii");
  XCTAssertEqualObjects(info[@"hide"], @NO);
  XCTAssertFalse(NeoTouchHidesControlsWithController(@"wii"));
  // Separate per console: GameCube, PS2 and PS3 keep their default.
  XCTAssertTrue(NeoTouchHidesControlsWithController(@"gc"));
  XCTAssertTrue(NeoTouchHidesControlsWithController(@"ps2"));
  XCTAssertTrue(NeoTouchHidesControlsWithController(@"ps3"));
}

- (void)testVisibilityRuleOfTheThreeEngines {
  NeoTouchSetHidesControlsWithController(@"ps3", NO);
  for (NSString* console in @[@"gc", @"wii", @"ps2", @"ps3"]) {
    const BOOL preference = NeoTouchHidesControlsWithController(console);
    // No controller: shown unless switched off or covered.
    XCTAssertFalse(NeoTouchControlsShouldHide(console, NO, YES, NO, NO), @"%@", console);
    XCTAssertTrue(NeoTouchControlsShouldHide(console, NO, NO, NO, NO), @"%@", console);
    XCTAssertTrue(NeoTouchControlsShouldHide(console, NO, YES, YES, NO), @"%@", console);
    // A controller hides them only while the console's preference is on.
    XCTAssertEqual(NeoTouchControlsShouldHide(console, YES, YES, NO, NO), preference, @"%@", console);
    // The editor always shows them.
    XCTAssertFalse(NeoTouchControlsShouldHide(console, YES, NO, YES, YES), @"%@", console);
  }
}

- (void)testMonitorFollowsConnectionsBeforeAndDuringASession {
  NeoTouchControllerMonitorSetTestingCount(1);
  NSMutableArray<NSNumber*>* changes = [NSMutableArray array];
  NeoTouchControllerMonitor* monitor = [[NeoTouchControllerMonitor alloc] initWithChangeHandler:^(BOOL connected) {
    [changes addObject:@(connected)];
  }];
  // Connected before the session: known at once, no change reported.
  XCTAssertTrue(monitor.connected);
  NeoTouchControllerMonitorSetTestingCount(0);
  [NSNotificationCenter.defaultCenter postNotificationName:GCControllerDidDisconnectNotification object:nil];
  XCTAssertFalse(monitor.connected);
  NeoTouchControllerMonitorSetTestingCount(2);
  [NSNotificationCenter.defaultCenter postNotificationName:GCControllerDidConnectNotification object:nil];
  NeoTouchControllerMonitorSetTestingCount(1);
  // One of two controllers leaves: still connected, nothing reported.
  [NSNotificationCenter.defaultCenter postNotificationName:GCControllerDidDisconnectNotification object:nil];
  [monitor refresh];
  XCTAssertEqualObjects(changes, (@[@NO, @YES]));
  NeoTouchControllerMonitorSetTestingCount(0);
  [NSNotificationCenter.defaultCenter postNotificationName:GCControllerDidDisconnectNotification object:nil];
  XCTAssertEqualObjects(changes, (@[@NO, @YES, @NO]));
  [monitor invalidate];
  NeoTouchControllerMonitorSetTestingCount(1);
  [NSNotificationCenter.defaultCenter postNotificationName:GCControllerDidConnectNotification object:nil];
  XCTAssertEqual(changes.count, 3U);
  // Keyboards, mice and other accessories are not GCControllers.
  XCTAssertFalse([NeoTouchControllerMonitor isCompatibleController:nil]);
  XCTAssertFalse([NeoTouchControllerMonitor isCompatibleController:(GCController*)[NSObject new]]);
}

@end

#pragma mark Editor and controls on the five layouts

@interface TLLayoutTests : XCTestCase
@property(nonatomic, strong) TLFixture* fixture;
@end

@implementation TLLayoutTests

+ (void)setUp {
  [super setUp];
  [UIView setAnimationsEnabled:NO];
  DOLTouchLayoutRegisterPreviews();
  Armsx2TouchControlsRegisterPreview();
  RPCS3TouchControlsRegisterPreview();
}

- (void)setUp {
  [super setUp];
  self.continueAfterFailure = NO;
  TLResetStore();
  NeoTouchControllerMonitorSetTestingCount(0);
  TLDolphinResetInputs();
  XCTAssertTrue(TLRotate(YES), @"the interface could not turn to landscape");
}

- (void)tearDown {
  [self.fixture remove];
  self.fixture = nil;
  NeoTouchControllerMonitorSetTestingCount(-1);
  TLResetStore();
  [super tearDown];
}

- (TLFixture*)open:(NSString*)key {
  [self.fixture remove];
  self.fixture = [TLFixture fixtureForKey:key];
  NSArray* elements = self.fixture.elements;
  XCTAssertGreaterThan(elements.count, 4U, @"%@ has no touch controls (nibs or images missing?)", key);
  return self.fixture;
}

- (NeoTouchLayoutEditor*)editorFor:(TLFixture*)fixture game:(NSString*)game finished:(NSMutableArray*)finished {
  NeoTouchLayoutEditor* editor = [[NeoTouchLayoutEditor alloc] initWithHost:fixture.host layoutKey:fixture.key
                                                                     gameKey:game title:@"Test" locale:@"fr"
                                                                       store:NeoTouchLayoutStore.sharedStore];
  __weak TLFixture* weakFixture = fixture;
  editor.finished = ^(BOOL saved) {
    [finished addObject:@(saved)];
    // As the engines do when the editor closes.
    [weakFixture endEditing];
  };
  [editor presentOverCanvas];
  [fixture layout];
  [editor layoutIfNeeded];
  return editor;
}

- (CGPoint)safePoint:(TLFixture*)fixture x:(CGFloat)x y:(CGFloat)y {
  const CGRect safe = [NeoTouchLayoutApplier safeRectOfCanvas:fixture.canvas];
  return [fixture.canvas convertPoint:CGPointMake(CGRectGetMinX(safe) + safe.size.width * x,
                                                  CGRectGetMinY(safe) + safe.size.height * y)
                               toView:fixture.container];
}

/// The visible control and its touch area: the frame matches the stored
/// layout, the points just inside the scaled frame reach the control.
- (void)assertElement:(NeoTouchElement*)element of:(TLFixture*)fixture layout:(NeoTouchLayout*)layout {
  UIView* view = element.view;
  const CGRect expected = [NeoTouchLayoutApplier frameOfElement:element layout:layout canvas:fixture.canvas];
  const CGRect actual = TLFrame(view, fixture.canvas);
  XCTAssertTrue(TLRectNear(actual, expected, 1.0), @"%@ %@: drawn %@, layout %@", fixture.key, element.identifier,
                NSStringFromCGRect(actual), NSStringFromCGRect(expected));
  if (![view isKindOfClass:UIControl.class] || view.hidden) return;
  const CGRect frame = TLFrame(view, fixture.container);
  const CGPoint mid = TLMid(frame);
  const CGFloat dx = frame.size.width * 0.42, dy = frame.size.height * 0.42;
  for (NSValue* offset in @[[NSValue valueWithCGPoint:CGPointZero], [NSValue valueWithCGPoint:CGPointMake(dx, 0)],
                            [NSValue valueWithCGPoint:CGPointMake(-dx, 0)], [NSValue valueWithCGPoint:CGPointMake(0, dy)],
                            [NSValue valueWithCGPoint:CGPointMake(0, -dy)]]) {
    const CGPoint point = CGPointMake(mid.x + offset.CGPointValue.x, mid.y + offset.CGPointValue.y);
    XCTAssertEqual(TLControlAt(fixture.container, point), view, @"%@ %@: no touch at %@ inside %@", fixture.key,
                   element.identifier, NSStringFromCGPoint(point), NSStringFromCGRect(frame));
  }
  for (NSValue* offset in @[[NSValue valueWithCGPoint:CGPointMake(frame.size.width * 0.62, 0)],
                            [NSValue valueWithCGPoint:CGPointMake(-frame.size.width * 0.62, 0)]]) {
    const CGPoint point = CGPointMake(mid.x + offset.CGPointValue.x, mid.y + offset.CGPointValue.y);
    XCTAssertNotEqual(TLControlAt(fixture.container, point), view, @"%@ %@: touch outside its drawing at %@",
                      fixture.key, element.identifier, NSStringFromCGPoint(point));
  }
}

#pragma mark Move, resize, opacity, hide, save, restore, cancel

- (void)runEditScenario:(NSString*)key {
  TLFixture* fixture = [self open:key];
  NSArray<NeoTouchElement*>* elements = fixture.elements;
  NeoTouchElement* button = TLFirstOfKind(elements, NeoTouchElementKindButton, @[]);
  NeoTouchElement* stick = TLFirstOfKind(elements, NeoTouchElementKindStick, @[]);
  NeoTouchElement* other = TLFirstOfKind(elements, NeoTouchElementKindButton, @[button.identifier ?: @""]);
  XCTAssertNotNil(button);
  XCTAssertNotNil(stick, @"%@ has no stick", key);
  XCTAssertNotNil(other);
  NSDictionary<NSString*, NSValue*>* stock = ^{
    NSMutableDictionary* frames = [NSMutableDictionary dictionary];
    for (NeoTouchElement* element in elements) frames[element.identifier] = [NSValue valueWithCGRect:TLFrame(element.view, fixture.canvas)];
    return frames;
  }();
  const CGPoint buttonTarget = [self safePoint:fixture x:0.40 y:0.38];
  const CGPoint stickTarget = [self safePoint:fixture x:0.64 y:0.62];

  NSMutableArray* finished = [NSMutableArray array];
  NeoTouchLayoutEditor* editor = [self editorFor:fixture game:nil finished:finished];
  XCTAssertEqual(editor.superview, fixture.canvas.superview);
  XCTAssertEqualObjects(editor.orientation, NeoTouchLayoutOrientationLandscape);
  XCTAssertEqual(editor.scope, NeoTouchLayoutScopeGeneral);
  XCTAssertTrue(TLHasButtonTitled(editor, NeoTouchLayoutText(@"save", @"fr")), @"French Save button");
  // While editing every control is under the editor: nothing reaches the game.
  const NSUInteger eventsBefore = TLDolphinEventCount();
  for (NeoTouchElement* element in elements) {
    const CGPoint center = TLMid(TLFrame(element.view, fixture.container));
    UIView* hit = [fixture.container hitTest:center withEvent:nil];
    XCTAssertTrue([hit isDescendantOfView:editor], @"%@ %@ reachable while editing", key, element.identifier);
  }

  // Drag the button through the editor's own touch handling.
  TLFakeTouch* touch = [TLFakeTouch new];
  touch.reference = fixture.container;
  touch.point = TLMid(TLFrame(button.view, fixture.container));
  [editor touchesBegan:[NSSet setWithObject:touch] withEvent:nil];
  XCTAssertEqualObjects(editor.selectedIdentifier, button.identifier);
  touch.point = CGPointMake(touch.point.x + (buttonTarget.x - touch.point.x) * 0.5,
                            touch.point.y + (buttonTarget.y - touch.point.y) * 0.5);
  [editor touchesMoved:[NSSet setWithObject:touch] withEvent:nil];
  touch.point = buttonTarget;
  [editor touchesMoved:[NSSet setWithObject:touch] withEvent:nil];
  [editor touchesEnded:[NSSet setWithObject:touch] withEvent:nil];
  CGRect draft = [editor frameOfElement:button.identifier];
  const CGPoint draftCenter = [editor convertPoint:TLMid(draft) toView:fixture.container];
  XCTAssertTrue(TLNear(draftCenter.x, buttonTarget.x, 1.5) && TLNear(draftCenter.y, buttonTarget.y, 1.5),
                @"%@ dragged to %@, expected %@", key, NSStringFromCGPoint(draftCenter), NSStringFromCGPoint(buttonTarget));
  // The real control follows the draft while editing (same rectangle).
  XCTAssertTrue(TLRectNear(TLFrame(button.view, editor), draft, 1.0));

  // Resize from the bottom-right corner handle: +60 % of the half diagonal.
  const CGPoint corner = CGPointMake(CGRectGetMaxX(draft), CGRectGetMaxY(draft));
  TLFakeTouch* handle = [TLFakeTouch new];
  handle.reference = editor;
  handle.point = corner;
  [editor touchesBegan:[NSSet setWithObject:handle] withEvent:nil];
  handle.point = CGPointMake(CGRectGetMidX(draft) + (corner.x - CGRectGetMidX(draft)) * 1.6,
                             CGRectGetMidY(draft) + (corner.y - CGRectGetMidY(draft)) * 1.6);
  [editor touchesMoved:[NSSet setWithObject:handle] withEvent:nil];
  [editor touchesEnded:[NSSet setWithObject:handle] withEvent:nil];
  XCTAssertEqualWithAccuracy([editor.draftLayout stateForIdentifier:button.identifier].scale, 1.6, 0.02);

  // Undo restores the size, redoing it through the slider API.
  [editor undo];
  XCTAssertEqualWithAccuracy([editor.draftLayout stateForIdentifier:button.identifier].scale, 1.0, 0.001);
  [editor setScale:1.6 forElement:button.identifier];
  [editor setOpacity:0.5 forElement:button.identifier];
  // Sticks move and resize on their own.
  [editor moveElement:stick.identifier toCenter:[fixture.container convertPoint:stickTarget toView:fixture.canvas]];
  [editor setScale:0.7 forElement:stick.identifier];
  [editor setHidden:YES forElement:other.identifier];
  // A hidden control stays visible faintly while editing so it can be shown again.
  XCTAssertFalse(other.view.hidden);
  XCTAssertLessThan(other.view.alpha, 0.5);
  XCTAssertTrue(editor.hasChanges);
  XCTAssertEqual(TLDolphinEventCount(), eventsBefore, @"editing sent Dolphin input");

  XCTAssertTrue([editor save]);
  XCTAssertEqualObjects(finished, @[@YES]);
  XCTAssertNil(editor.superview);
  [fixture layout];

  NeoTouchLayout* stored = [NeoTouchLayoutStore.sharedStore layoutForKey:key
      orientation:NeoTouchLayoutOrientationLandscape game:nil];
  XCTAssertNotNil(stored);
  XCTAssertEqualWithAccuracy([stored stateForIdentifier:button.identifier].scale, 1.6, 0.001);
  XCTAssertEqualWithAccuracy([stored stateForIdentifier:button.identifier].opacity, 0.5, 0.001);
  XCTAssertEqualWithAccuracy([stored stateForIdentifier:stick.identifier].scale, 0.7, 0.001);
  XCTAssertTrue([stored stateForIdentifier:other.identifier].hidden);
  XCTAssertNil([NeoTouchLayoutStore.sharedStore layoutForKey:key orientation:NeoTouchLayoutOrientationPortrait game:nil]);

  // Playing: drawing and touch area together.
  elements = fixture.elements;
  button = TLElement(elements, button.identifier);
  stick = TLElement(elements, stick.identifier);
  other = TLElement(elements, other.identifier);
  [self assertElement:button of:fixture layout:stored];
  [self assertElement:stick of:fixture layout:stored];
  const CGRect buttonFrame = TLFrame(button.view, fixture.container);
  XCTAssertTrue(TLNear(CGRectGetMidX(buttonFrame), buttonTarget.x, 1.5) && TLNear(CGRectGetMidY(buttonFrame), buttonTarget.y, 1.5));
  XCTAssertEqualWithAccuracy(buttonFrame.size.width, button.defaultSize.width * 1.6, 1.0);
  XCTAssertEqualWithAccuracy(button.view.alpha, button.defaultAlpha * 0.5, 0.01);
  XCTAssertEqualWithAccuracy(TLFrame(stick.view, fixture.canvas).size.width, stick.defaultSize.width * 0.7, 1.0);
  XCTAssertTrue(other.view.hidden);
  const CGPoint otherStock = [fixture.canvas convertPoint:TLMid(stock[other.identifier].CGRectValue) toView:fixture.container];
  XCTAssertNotEqual(TLControlAt(fixture.container, otherStock), other.view, @"a hidden control still takes touches");
  const CGPoint buttonStock = [fixture.canvas convertPoint:TLMid(stock[button.identifier].CGRectValue) toView:fixture.container];
  if (!CGRectContainsPoint(CGRectInset(buttonFrame, -2, -2), buttonStock))
    XCTAssertNotEqual(TLControlAt(fixture.container, buttonStock), button.view, @"the old place still presses it");

  // The moved control presses its own input and releases it.
  NSString* input = [fixture inputForButton:button];
  UIControl* pressed = TLPress(fixture.container, buttonTarget);
  XCTAssertEqual(pressed, button.view);
  XCTAssertTrue([fixture.active containsObject:input], @"%@: %@ not sent (%@)", key, input, fixture.active);
  TLLift(pressed);
  XCTAssertFalse([fixture.active containsObject:input]);
  // The resized stick: its travel follows the drawing (30 % of the drawn width = 0.83+).
  const CGRect stickFrame = TLFrame(stick.view, fixture.container);
  [fixture deflect:stick toward:CGPointMake(CGRectGetMidX(stickFrame) + stickFrame.size.width * 0.3, CGRectGetMidY(stickFrame))];
  NSString* right = [fixture rightInputForStick:stick];
  XCTAssertGreaterThan([fixture.values[right] doubleValue], 0.75, @"%@ %@", key, fixture.values);
  [fixture endStick:stick];
  XCTAssertEqual(fixture.active.count, 0U, @"%@ stuck: %@", key, fixture.active);

  // Restore the default layout: stock frames, nothing stored.
  finished = [NSMutableArray array];
  editor = [self editorFor:fixture game:nil finished:finished];
  [editor restoreDefaultLayout];
  XCTAssertTrue([editor save]);
  [fixture layout];
  XCTAssertNil([NeoTouchLayoutStore.sharedStore layoutForKey:key orientation:NeoTouchLayoutOrientationLandscape game:nil]);
  XCTAssertFalse([NeoTouchLayoutStore.sharedStore hasCustomLayoutForKey:key]);
  for (NeoTouchElement* element in fixture.elements) {
    if (!stock[element.identifier]) continue;
    XCTAssertTrue(TLRectNear(TLFrame(element.view, fixture.canvas), stock[element.identifier].CGRectValue, 0.5),
                  @"%@ %@ not back to stock", key, element.identifier);
    XCTAssertFalse(element.view.hidden);
  }

  // Cancel: the draft is dropped, nothing is stored.
  finished = [NSMutableArray array];
  editor = [self editorFor:fixture game:nil finished:finished];
  [editor moveElement:button.identifier toCenter:[fixture.container convertPoint:buttonTarget toView:fixture.canvas]];
  [editor cancel];
  XCTAssertEqualObjects(finished, @[@NO]);
  [fixture layout];
  XCTAssertFalse([NeoTouchLayoutStore.sharedStore hasCustomLayoutForKey:key]);
  button = TLElement(fixture.elements, button.identifier);
  XCTAssertTrue(TLRectNear(TLFrame(button.view, fixture.canvas), stock[button.identifier].CGRectValue, 0.5));
}

- (void)testEditGameCube { [self runEditScenario:@"gc"]; }
- (void)testEditWiiRemoteNunchuk { [self runEditScenario:@"wii"]; }
- (void)testEditWiiClassic { [self runEditScenario:@"wii-classic"]; }
- (void)testEditPlayStation2 { [self runEditScenario:@"ps2"]; }
- (void)testEditPlayStation3 { [self runEditScenario:@"ps3"]; }

#pragma mark Orientation

- (void)runOrientationScenario:(NSString*)key {
  TLFixture* fixture = [self open:key];
  NeoTouchElement* button = TLFirstOfKind(fixture.elements, NeoTouchElementKindButton, @[]);
  NeoTouchElement* held = TLFirstOfKind(fixture.elements, NeoTouchElementKindButton, @[button.identifier]);
  NSString* identifier = button.identifier;
  const CGPoint landscapeTarget = [self safePoint:fixture x:0.36 y:0.40];
  NSMutableArray* finished = [NSMutableArray array];
  NeoTouchLayoutEditor* editor = [self editorFor:fixture game:nil finished:finished];
  [editor moveElement:identifier toCenter:[fixture.container convertPoint:landscapeTarget toView:fixture.canvas]];
  XCTAssertTrue([editor save]);
  [fixture layout];

  // A finger held across a rotation must not keep its button pressed.
  NSString* heldInput = [fixture inputForButton:held];
  UIControl* control = TLPress(fixture.container, TLMid(TLFrame(held.view, fixture.container)));
  XCTAssertNotNil(control);
  XCTAssertTrue([fixture.active containsObject:heldInput]);
  const NSUInteger changes = fixture.orientationChanges;
  XCTAssertTrue(TLRotate(NO), @"the interface could not turn to portrait");
  [fixture layout];
  XCTAssertGreaterThan(fixture.orientationChanges, changes);
  XCTAssertEqual(fixture.active.count, 0U, @"%@ held input survived the rotation: %@", key, fixture.active);
  XCTAssertFalse(control.highlighted);

  // Portrait has its own layout: still the stock one.
  NeoTouchElement* portraitButton = TLElement(fixture.elements, identifier);
  XCTAssertTrue(TLRectNear(TLFrame(portraitButton.view, fixture.canvas),
                           [NeoTouchLayoutApplier frameOfElement:portraitButton layout:nil canvas:fixture.canvas], 0.5));
  const CGPoint portraitTarget = [self safePoint:fixture x:0.62 y:0.30];
  editor = [self editorFor:fixture game:nil finished:finished];
  XCTAssertEqualObjects(editor.orientation, NeoTouchLayoutOrientationPortrait);
  [editor moveElement:identifier toCenter:[fixture.container convertPoint:portraitTarget toView:fixture.canvas]];
  [editor setScale:1.3 forElement:identifier];
  XCTAssertTrue([editor save]);
  [fixture layout];
  NeoTouchLayout* portrait = [NeoTouchLayoutStore.sharedStore layoutForKey:key
      orientation:NeoTouchLayoutOrientationPortrait game:nil];
  NeoTouchLayout* landscape = [NeoTouchLayoutStore.sharedStore layoutForKey:key
      orientation:NeoTouchLayoutOrientationLandscape game:nil];
  XCTAssertNotNil(portrait);
  XCTAssertNotNil(landscape);
  XCTAssertEqualWithAccuracy([landscape stateForIdentifier:identifier].scale, 1.0, 0.001);
  portraitButton = TLElement(fixture.elements, identifier);
  [self assertElement:portraitButton of:fixture layout:portrait];
  CGPoint center = TLMid(TLFrame(portraitButton.view, fixture.container));
  XCTAssertTrue(TLNear(center.x, portraitTarget.x, 1.5) && TLNear(center.y, portraitTarget.y, 1.5));

  // Back to landscape: the landscape layout, safe area included.
  XCTAssertTrue(TLRotate(YES));
  [fixture layout];
  NeoTouchElement* again = TLElement(fixture.elements, identifier);
  [self assertElement:again of:fixture layout:landscape];
  center = TLMid(TLFrame(again.view, fixture.container));
  const CGPoint expected = [self safePoint:fixture x:0.36 y:0.40];
  XCTAssertTrue(TLNear(center.x, expected.x, 1.5) && TLNear(center.y, expected.y, 1.5),
                @"%@ landscape position lost: %@ vs %@", key, NSStringFromCGPoint(center), NSStringFromCGPoint(expected));

  // The editor follows a rotation: it edits the new orientation's layout.
  editor = [self editorFor:fixture game:nil finished:finished];
  XCTAssertEqualObjects(editor.orientation, NeoTouchLayoutOrientationLandscape);
  XCTAssertTrue(TLRotate(NO));
  [fixture layout];
  [editor layoutIfNeeded];
  XCTAssertEqualObjects(editor.orientation, NeoTouchLayoutOrientationPortrait);
  XCTAssertEqualWithAccuracy([editor.draftLayout stateForIdentifier:identifier].scale, 1.3, 0.001);
  [editor cancel];
  XCTAssertTrue(TLRotate(YES));
}

- (void)testOrientationGameCube { [self runOrientationScenario:@"gc"]; }
- (void)testOrientationWiiRemoteNunchuk { [self runOrientationScenario:@"wii"]; }
- (void)testOrientationWiiClassic { [self runOrientationScenario:@"wii-classic"]; }
- (void)testOrientationPlayStation2 { [self runOrientationScenario:@"ps2"]; }
- (void)testOrientationPlayStation3 { [self runOrientationScenario:@"ps3"]; }

#pragma mark Multitouch, diagonals, sticks and release

- (void)runMultitouchScenario:(NSString*)key {
  TLFixture* fixture = [self open:key];
  NSArray<NeoTouchElement*>* elements = fixture.elements;
  NeoTouchElement* first = TLFirstOfKind(elements, NeoTouchElementKindButton, @[]);
  NeoTouchElement* second = TLFirstOfKind(elements, NeoTouchElementKindButton, @[first.identifier]);
  NeoTouchElement* stick = TLFirstOfKind(elements, NeoTouchElementKindStick, @[]);
  NeoTouchElement* dpad = TLFirstOfKind(elements, NeoTouchElementKindDirectionalPad, @[]);
  XCTAssertNotNil(dpad, @"%@ has no D-pad", key);
  // Move and enlarge the D-pad first: the diagonal goes through the stored transform.
  NSMutableArray* finished = [NSMutableArray array];
  NeoTouchLayoutEditor* editor = [self editorFor:fixture game:nil finished:finished];
  [editor moveElement:dpad.identifier toCenter:[fixture.container convertPoint:[self safePoint:fixture x:0.30 y:0.55]
                                                                         toView:fixture.canvas]];
  [editor setScale:1.25 forElement:dpad.identifier];
  XCTAssertTrue([editor save]);
  [fixture layout];
  elements = fixture.elements;
  first = TLElement(elements, first.identifier);
  second = TLElement(elements, second.identifier);
  stick = TLElement(elements, stick.identifier);
  dpad = TLElement(elements, dpad.identifier);

  UIControl* a = TLPress(fixture.container, TLMid(TLFrame(first.view, fixture.container)));
  UIControl* b = TLPress(fixture.container, TLMid(TLFrame(second.view, fixture.container)));
  XCTAssertEqual(a, first.view);
  XCTAssertEqual(b, second.view);
  NSSet* diagonal = [fixture pressUpLeft:dpad];
  const CGRect stickFrame = TLFrame(stick.view, fixture.container);
  [fixture deflect:stick toward:CGPointMake(CGRectGetMidX(stickFrame) + stickFrame.size.width, CGRectGetMidY(stickFrame))];
  NSSet* active = fixture.active;
  XCTAssertTrue([active containsObject:[fixture inputForButton:first]], @"%@ %@", key, active);
  XCTAssertTrue([active containsObject:[fixture inputForButton:second]], @"%@ %@", key, active);
  XCTAssertTrue([diagonal isSubsetOfSet:active], @"%@ diagonal %@ not in %@", key, diagonal, active);
  XCTAssertGreaterThan([fixture.values[[fixture rightInputForStick:stick]] doubleValue], 0.9);

  // One finger lifts: the others stay pressed.
  TLLift(a);
  active = fixture.active;
  XCTAssertFalse([active containsObject:[fixture inputForButton:first]]);
  XCTAssertTrue([active containsObject:[fixture inputForButton:second]]);
  XCTAssertTrue([diagonal isSubsetOfSet:active]);

  // The engine's release path (used when the controls hide, the surface turns,
  // the editor opens or the session closes) leaves nothing pressed.
  [fixture releaseAll];
  XCTAssertEqual(fixture.active.count, 0U, @"%@ stuck after release: %@", key, fixture.active);
  XCTAssertFalse(b.highlighted);
  // The fingers lifting afterwards change nothing.
  TLLift(b);
  [fixture endDPad:dpad];
  [fixture endStick:stick];
  XCTAssertEqual(fixture.active.count, 0U);
}

- (void)testMultitouchGameCube { [self runMultitouchScenario:@"gc"]; }
- (void)testMultitouchWiiRemoteNunchuk { [self runMultitouchScenario:@"wii"]; }
- (void)testMultitouchWiiClassic { [self runMultitouchScenario:@"wii-classic"]; }
- (void)testMultitouchPlayStation2 { [self runMultitouchScenario:@"ps2"]; }
- (void)testMultitouchPlayStation3 { [self runMultitouchScenario:@"ps3"]; }

#pragma mark General layout and per-game layout

- (void)runGameScenario:(NSString*)key {
  TLFixture* fixture = [self open:key];
  NSString* identifier = TLFirstOfKind(fixture.elements, NeoTouchElementKindButton, @[]).identifier;
  NSString* game = @"  TEST-Game-01 ";
  const CGPoint general = [self safePoint:fixture x:0.35 y:0.35];
  const CGPoint specific = [self safePoint:fixture x:0.60 y:0.45];
  NSMutableArray* finished = [NSMutableArray array];
  NeoTouchLayoutEditor* editor = [self editorFor:fixture game:nil finished:finished];
  [editor moveElement:identifier toCenter:[fixture.container convertPoint:general toView:fixture.canvas]];
  XCTAssertTrue([editor save]);
  [fixture setGameKey:game];
  [fixture layout];
  // A game without its own layout follows the general one.
  CGPoint center = TLMid(TLFrame(TLElement(fixture.elements, identifier).view, fixture.container));
  XCTAssertTrue(TLNear(center.x, general.x, 1.5) && TLNear(center.y, general.y, 1.5));

  editor = [self editorFor:fixture game:game finished:finished];
  XCTAssertEqualObjects(editor.gameKey, @"test-game-01");
  [editor selectScope:NeoTouchLayoutScopeGame];
  XCTAssertEqual(editor.scope, NeoTouchLayoutScopeGame);
  [editor moveElement:identifier toCenter:[fixture.container convertPoint:specific toView:fixture.canvas]];
  XCTAssertTrue([editor save]);
  [fixture layout];
  XCTAssertTrue([NeoTouchLayoutStore.sharedStore hasGameLayoutForKey:key game:@"test-game-01"]);
  center = TLMid(TLFrame(TLElement(fixture.elements, identifier).view, fixture.container));
  XCTAssertTrue(TLNear(center.x, specific.x, 1.5) && TLNear(center.y, specific.y, 1.5));
  // Another session (no game key, or another game) keeps the general layout.
  [fixture setGameKey:nil];
  [fixture layout];
  center = TLMid(TLFrame(TLElement(fixture.elements, identifier).view, fixture.container));
  XCTAssertTrue(TLNear(center.x, general.x, 1.5) && TLNear(center.y, general.y, 1.5));
  [fixture setGameKey:@"other-game"];
  [fixture layout];
  center = TLMid(TLFrame(TLElement(fixture.elements, identifier).view, fixture.container));
  XCTAssertTrue(TLNear(center.x, general.x, 1.5) && TLNear(center.y, general.y, 1.5));

  // Back to the general layout for this game.
  [fixture setGameKey:game];
  [fixture layout];
  editor = [self editorFor:fixture game:game finished:finished];
  [editor selectScope:NeoTouchLayoutScopeGame];
  [editor useGeneralLayout];
  XCTAssertTrue([editor save]);
  [fixture layout];
  XCTAssertFalse([NeoTouchLayoutStore.sharedStore hasGameLayoutForKey:key game:@"test-game-01"]);
  center = TLMid(TLFrame(TLElement(fixture.elements, identifier).view, fixture.container));
  XCTAssertTrue(TLNear(center.x, general.x, 1.5) && TLNear(center.y, general.y, 1.5));
  XCTAssertEqualObjects(finished, (@[@YES, @YES, @YES]));
}

- (void)testGameLayoutGameCube { [self runGameScenario:@"gc"]; }
- (void)testGameLayoutWiiRemoteNunchuk { [self runGameScenario:@"wii"]; }
- (void)testGameLayoutWiiClassic { [self runGameScenario:@"wii-classic"]; }
- (void)testGameLayoutPlayStation2 { [self runGameScenario:@"ps2"]; }
- (void)testGameLayoutPlayStation3 { [self runGameScenario:@"ps3"]; }

#pragma mark Editor opened from the settings (no game)

- (void)runSettingsEditorScenario:(NSString*)key {
  NeoTouchControllerMonitorSetTestingCount(1);  // the editor still opens with a controller
  UIViewController* root = TLWindow().rootViewController;
  NeoTouchLayoutEditorController* controller = [[NeoTouchLayoutEditorController alloc] initWithLayoutKey:key locale:@"de"];
  XCTAssertNotNil(controller, @"%@ has no registered preview", key);
  // Only the orientations the engine's sessions use: Dolphin and RPCS3 run in landscape.
  XCTAssertEqual(controller.supportedInterfaceOrientations,
                 [key isEqualToString:@"ps2"] ? UIInterfaceOrientationMaskAllButUpsideDown
                                              : UIInterfaceOrientationMaskLandscape);
  __block NSNumber* result = nil;
  controller.finished = ^(BOOL saved) { result = @(saved); };
  [root presentViewController:controller animated:NO completion:nil];
  for (NSInteger step = 0; step < 100 && !controller.editor; step++) TLSpin(0.02);
  NeoTouchLayoutEditor* editor = controller.editor;
  XCTAssertNotNil(editor);
  XCTAssertTrue(editor.controllerConnected);
  XCTAssertNil(editor.gameKey);
  XCTAssertTrue(TLHasButtonTitled(editor, NeoTouchLayoutText(@"save", @"de")), @"German Save button");
  const NSUInteger events = TLDolphinEventCount();
  UIView* rootView = controller.view;
  NSArray<NeoTouchElement*>* elements = [editor valueForKey:@"elements"];
  XCTAssertGreaterThan(elements.count, 4U);
  for (NeoTouchElement* element in elements) {
    UIView* hit = [rootView hitTest:[element.view convertPoint:TLMid(element.view.bounds) toView:rootView] withEvent:nil];
    XCTAssertTrue([hit isDescendantOfView:editor], @"%@ preview control %@ reachable", key, element.identifier);
  }
  NeoTouchElement* button = TLFirstOfKind(elements, NeoTouchElementKindButton, @[]);
  [editor setScale:1.4 forElement:button.identifier];
  XCTAssertTrue([editor save]);
  for (NSInteger step = 0; step < 100 && !result; step++) TLSpin(0.02);
  XCTAssertEqualObjects(result, @YES);
  XCTAssertNil(root.presentedViewController);
  XCTAssertEqual(TLDolphinEventCount(), events, @"the preview sent input");
  NeoTouchLayout* stored = [NeoTouchLayoutStore.sharedStore layoutForKey:key
      orientation:NeoTouchLayoutOrientationLandscape game:nil];
  XCTAssertEqualWithAccuracy([stored stateForIdentifier:button.identifier].scale, 1.4, 0.001);
  // A session opened afterwards uses it.
  TLFixture* fixture = [self open:key];
  NeoTouchElement* playing = TLElement(fixture.elements, button.identifier);
  XCTAssertEqualWithAccuracy(TLFrame(playing.view, fixture.canvas).size.width, playing.defaultSize.width * 1.4, 1.0);
}

- (void)testSettingsEditorGameCube { [self runSettingsEditorScenario:@"gc"]; }
- (void)testSettingsEditorWiiRemoteNunchuk { [self runSettingsEditorScenario:@"wii"]; }
- (void)testSettingsEditorWiiClassic { [self runSettingsEditorScenario:@"wii-classic"]; }
- (void)testSettingsEditorPlayStation2 { [self runSettingsEditorScenario:@"ps2"]; }
- (void)testSettingsEditorPlayStation3 { [self runSettingsEditorScenario:@"ps3"]; }

#pragma mark Dolphin specifics

- (void)testWiiShakeIsAMovableElementThatCanBeHidden {
  TLDolphinFixture* fixture = (TLDolphinFixture*)[self open:@"wii"];
  NeoTouchElement* shake = TLElement(fixture.elements, @"shake");
  XCTAssertNotNil(shake);
  XCTAssertFalse(shake.view.hidden);
  NSMutableArray* finished = [NSMutableArray array];
  NeoTouchLayoutEditor* editor = [self editorFor:fixture game:nil finished:finished];
  [editor moveElement:@"shake" toCenter:[fixture.container convertPoint:[self safePoint:fixture x:0.5 y:0.3]
                                                                  toView:fixture.canvas]];
  [editor setHidden:YES forElement:@"shake"];
  XCTAssertFalse(fixture.overlay.touchLayoutShakeControl.hidden, @"shown faintly while editing");
  XCTAssertTrue([editor save]);
  [fixture layout];
  XCTAssertTrue(fixture.overlay.touchLayoutShakeControl.hidden);
  // The Classic Controller and the GameCube have no Shake control.
  TLFixture* classic = [self open:@"wii-classic"];
  XCTAssertNil(TLElement(classic.elements, @"shake"));
  TLFixture* gamecube = [self open:@"gc"];
  XCTAssertNil(TLElement(gamecube.elements, @"shake"));
}

- (void)testDolphinLayoutsAreSeparate {
  TLFixture* gamecube = [self open:@"gc"];
  NSString* identifier = TLFirstOfKind(gamecube.elements, NeoTouchElementKindButton, @[]).identifier;
  NSMutableArray* finished = [NSMutableArray array];
  NeoTouchLayoutEditor* editor = [self editorFor:gamecube game:nil finished:finished];
  [editor setScale:2.0 forElement:identifier];
  XCTAssertTrue([editor save]);
  XCTAssertTrue([NeoTouchLayoutStore.sharedStore hasCustomLayoutForKey:@"gc"]);
  for (NSString* key in @[@"wii", @"wii-classic", @"ps2", @"ps3"])
    XCTAssertFalse([NeoTouchLayoutStore.sharedStore hasCustomLayoutForKey:key], @"%@", key);
  TLFixture* wii = [self open:@"wii"];
  for (NeoTouchElement* element in wii.elements)
    XCTAssertTrue(CGAffineTransformIsIdentity(element.view.transform) ||
                  TLNear(element.view.transform.a, 1.0, 0.001), @"%@ scaled by the GameCube layout", element.identifier);
}

@end

#pragma mark PS3: controller policy through the production input controller

@interface TLRpcs3ControllerTests : XCTestCase
@property(nonatomic, strong) TLRpcs3Fixture* fixture;
@end

@implementation TLRpcs3ControllerTests

- (void)setUp {
  [super setUp];
  self.continueAfterFailure = NO;
  [UIView setAnimationsEnabled:NO];
  TLResetStore();
  XCTAssertTrue(TLRotate(YES));
}

- (void)tearDown {
  [self.fixture remove];
  self.fixture = nil;
  NeoTouchControllerMonitorSetTestingCount(-1);
  TLResetStore();
  [super tearDown];
}

- (UIView*)cross {
  return [self.fixture.controller.touchControls controlForIdentifier:@"cross"];
}

- (void)pressCross {
  UIView* cross = [self cross];
  TLPress(self.fixture.container, [cross convertPoint:TLMid(cross.bounds) toView:self.fixture.container]);
}

- (void)testControllerConnectedBeforeAndDuringTheSession {
  NeoTouchControllerMonitorSetTestingCount(1);
  self.fixture = (TLRpcs3Fixture*)[TLFixture fixtureForKey:@"ps3"];
  RPCS3TouchControlsView* touch = self.fixture.controller.touchControls;
  // Connected at launch: hidden, no touch area, a connected neutral pad.
  XCTAssertTrue(touch.hidden);
  XCTAssertNil(TLControlAt(self.fixture.container, [[self cross] convertPoint:TLMid([self cross].bounds)
                                                                        toView:self.fixture.container]));
  XCTAssertEqual(gTLPad.connected, 1U);
  XCTAssertEqual(gTLPad.buttons, 0ULL);
  // The last controller disconnects: the controls come back.
  NeoTouchControllerMonitorSetTestingCount(0);
  [NSNotificationCenter.defaultCenter postNotificationName:GCControllerDidDisconnectNotification object:nil];
  XCTAssertFalse(touch.hidden);
  XCTAssertTrue(touch.userInteractionEnabled);
  [self pressCross];
  XCTAssertEqual(gTLPad.buttons, (uint64_t)rpcs3_ios_pad_cross);
  // A controller connects during the game while Cross is held: hidden and released.
  NeoTouchControllerMonitorSetTestingCount(1);
  [NSNotificationCenter.defaultCenter postNotificationName:GCControllerDidConnectNotification object:nil];
  XCTAssertTrue(touch.hidden);
  XCTAssertEqual(gTLPad.buttons, 0ULL);
  XCTAssertFalse(((UIControl*)[self cross]).highlighted);
  // The finger lifting later sends nothing new.
  const uint64_t before = gTLPad.buttons;
  TLLift((UIControl*)[self cross]);
  XCTAssertEqual(gTLPad.buttons, before);
  // The Touch Controls switch still applies without a controller.
  NeoTouchControllerMonitorSetTestingCount(0);
  [NSNotificationCenter.defaultCenter postNotificationName:GCControllerDidDisconnectNotification object:nil];
  XCTAssertFalse(touch.hidden);
  self.fixture.controller.touchControlsEnabled = NO;
  XCTAssertTrue(touch.hidden);
  self.fixture.controller.touchControlsEnabled = YES;
  XCTAssertFalse(touch.hidden);
}

- (void)testPreferenceOffKeepsTouchUsableWithAController {
  NeoTouchControllerMonitorSetTestingCount(1);
  self.fixture = (TLRpcs3Fixture*)[TLFixture fixtureForKey:@"ps3"];
  RPCS3TouchControlsView* touch = self.fixture.controller.touchControls;
  XCTAssertTrue(touch.hidden);
  NeoTouchSetHidesControlsWithController(@"ps3", NO);
  XCTAssertFalse(touch.hidden);
  XCTAssertTrue(touch.userInteractionEnabled);
  [self pressCross];
  XCTAssertEqual(gTLPad.buttons, (uint64_t)rpcs3_ios_pad_cross);
  TLLift((UIControl*)[self cross]);
  XCTAssertEqual(gTLPad.buttons, 0ULL);
  // Another console's preference does not affect PS3.
  NeoTouchSetHidesControlsWithController(@"ps2", YES);
  XCTAssertFalse(touch.hidden);
  NeoTouchSetHidesControlsWithController(@"ps3", YES);
  XCTAssertTrue(touch.hidden);
}

- (void)testEditorWithAControllerShowsTheControlsAndSendsANeutralPad {
  NeoTouchControllerMonitorSetTestingCount(1);
  self.fixture = (TLRpcs3Fixture*)[TLFixture fixtureForKey:@"ps3"];
  RPCS3GameInputController* controller = self.fixture.controller;
  __block BOOL closed = NO;
  [controller beginTouchLayoutEditingWithTitle:@"BLES00000" completion:^{ closed = YES; }];
  NeoTouchLayoutEditor* editor = (NeoTouchLayoutEditor*)controller.activeEditor;
  XCTAssertNotNil(editor);
  XCTAssertTrue(controller.editingTouchLayout);
  XCTAssertTrue(editor.controllerConnected);
  XCTAssertFalse(controller.touchControls.hidden);
  XCTAssertFalse(controller.touchControls.userInteractionEnabled);
  // A press that reaches the control anyway is not sent to the game.
  [(UIControl*)[self cross] sendActionsForControlEvents:UIControlEventTouchDown];
  XCTAssertEqual(gTLPad.buttons, 0ULL);
  XCTAssertEqual(gTLPad.connected, 1U);
  [editor cancel];
  XCTAssertTrue(closed);
  XCTAssertFalse(controller.editingTouchLayout);
  XCTAssertTrue(controller.touchControls.hidden);
}

@end

#pragma mark Persistence across launches

static NSString* TLMarkerPath(void) {
  NSString* library = NSSearchPathForDirectoriesInDomains(NSLibraryDirectory, NSUserDomainMask, YES).firstObject;
  return [library stringByAppendingPathComponent:@"touch-layout-persistence.json"];
}

@interface TLPersistenceTests : XCTestCase
@end

@implementation TLPersistenceTests

- (void)setUp {
  [super setUp];
  self.continueAfterFailure = NO;
  [UIView setAnimationsEnabled:NO];
  NeoTouchControllerMonitorSetTestingCount(0);
  XCTAssertTrue(TLRotate(YES));
}

- (void)tearDown {
  NeoTouchControllerMonitorSetTestingCount(-1);
  [super tearDown];
}

/// First process: saves a layout of each key and a preference.
- (void)testPersistenceWrite {
  TLResetStore();
  [NSFileManager.defaultManager removeItemAtPath:TLMarkerPath() error:nil];
  NSMutableDictionary* expected = [NSMutableDictionary dictionary];
  for (NSString* key in TLKeys()) {
    TLFixture* fixture = [TLFixture fixtureForKey:key];
    NeoTouchElement* button = TLFirstOfKind(fixture.elements, NeoTouchElementKindButton, @[]);
    NeoTouchLayoutEditor* editor = [[NeoTouchLayoutEditor alloc] initWithHost:fixture.host layoutKey:key gameKey:nil
                                                                         title:nil locale:@"en"
                                                                         store:NeoTouchLayoutStore.sharedStore];
    __weak TLFixture* weakFixture = fixture;
    editor.finished = ^(BOOL saved) { [weakFixture endEditing]; };
    [editor presentOverCanvas];
    const CGRect safe = [NeoTouchLayoutApplier safeRectOfCanvas:fixture.canvas];
    [editor moveElement:button.identifier toCenter:CGPointMake(CGRectGetMinX(safe) + safe.size.width * 0.45,
                                                               CGRectGetMinY(safe) + safe.size.height * 0.33)];
    [editor setScale:1.5 forElement:button.identifier];
    XCTAssertTrue([editor save]);
    [fixture layout];
    const CGRect frame = TLFrame(TLElement(fixture.elements, button.identifier).view, fixture.canvas);
    expected[key] = @{@"id": button.identifier, @"frame": NSStringFromCGRect(frame)};
    [fixture remove];
  }
  NeoTouchSetHidesControlsWithController(@"wii", NO);
  NSDictionary* marker = @{@"pid": @(getpid()), @"expected": expected};
  XCTAssertTrue([[NSJSONSerialization dataWithJSONObject:marker options:0 error:nil] writeToFile:TLMarkerPath()
                                                                                         atomically:YES]);
}

/// Second process (run separately): the layouts and the preference are back.
- (void)testPersistenceRead {
  NSData* data = [NSData dataWithContentsOfFile:TLMarkerPath()];
  XCTAssertNotNil(data, @"run testPersistenceWrite in a first process");
  NSDictionary* marker = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
  XCTAssertNotEqualObjects(marker[@"pid"], @(getpid()), @"must run in another process");
  for (NSString* key in TLKeys()) {
    NSDictionary* entry = marker[@"expected"][key];
    TLFixture* fixture = [TLFixture fixtureForKey:key];
    NeoTouchElement* element = TLElement(fixture.elements, entry[@"id"]);
    XCTAssertNotNil(element);
    XCTAssertTrue(TLRectNear(TLFrame(element.view, fixture.canvas), CGRectFromString(entry[@"frame"]), 0.5),
                  @"%@ %@ not restored: %@ vs %@", key, entry[@"id"],
                  NSStringFromCGRect(TLFrame(element.view, fixture.canvas)), entry[@"frame"]);
    [fixture remove];
  }
  XCTAssertFalse(NeoTouchHidesControlsWithController(@"wii"));
  XCTAssertTrue(NeoTouchHidesControlsWithController(@"gc"));
  XCTAssertTrue(NeoTouchHidesControlsWithController(@"ps2"));
  XCTAssertTrue(NeoTouchHidesControlsWithController(@"ps3"));
  TLResetStore();
  [NSFileManager.defaultManager removeItemAtPath:TLMarkerPath() error:nil];
}

@end

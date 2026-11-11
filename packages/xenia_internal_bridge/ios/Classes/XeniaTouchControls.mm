// SPDX-License-Identifier: BSD-3-Clause
// Xbox 360 touch controls of the XeniOS session, modelled on the ARMSX2
// controls of Build 484 (Armsx2TouchControls.mm): same stick behaviour, same
// layout/editor contract, Xbox 360 legends and XInput conventions.
#import "XeniaTouchControls.h"
#include <cmath>

NSString* const XeniaTouchLayoutKey = @"xbox360";

// X_INPUT_GAMEPAD_* (xenia/hid/input.h).
enum : uint32_t {
  kXeniaUp = 0x0001, kXeniaDown = 0x0002, kXeniaLeft = 0x0004, kXeniaRight = 0x0008,
  kXeniaStart = 0x0010, kXeniaBack = 0x0020, kXeniaL3 = 0x0040, kXeniaR3 = 0x0080,
  kXeniaLB = 0x0100, kXeniaRB = 0x0200, kXeniaA = 0x1000, kXeniaB = 0x2000,
  kXeniaX = 0x4000, kXeniaY = 0x8000,
};
// Analog triggers are buttons on the screen, full press when held.
static const NSInteger kXeniaTagLeftTrigger = 1 << 20;
static const NSInteger kXeniaTagRightTrigger = 1 << 21;

static NSString* const kXeniaDPad = @"dpad";
static NSString* const kXeniaLeftStick = @"stick.left";
static NSString* const kXeniaRightStick = @"stick.right";

/// A virtual stick: a pan relative to where the finger started, measured in
/// the stick's own coordinates so a layout transform scales drawing, touch
/// area and travel together (ARMSX2's stick, Y reported positive up).
@interface RBXeniaVirtualStickView : UIView
@property(nonatomic, copy, nullable) void (^valueChanged)(float x, float y);
@property(nonatomic, strong) UIView* knob;
- (void)recenter;
@end

@implementation RBXeniaVirtualStickView
- (instancetype)init {
  self = [super initWithFrame:CGRectZero];
  if (self) {
    self.backgroundColor = [UIColor colorWithWhite:0 alpha:0.34];
    self.layer.borderColor = [UIColor colorWithWhite:1 alpha:0.48].CGColor;
    self.layer.borderWidth = 1.0;
    self.knob = [[UIView alloc] initWithFrame:CGRectZero];
    self.knob.backgroundColor = [UIColor colorWithWhite:1 alpha:0.38];
    self.knob.userInteractionEnabled = NO;
    [self addSubview:self.knob];
    UIPanGestureRecognizer* pan = [[UIPanGestureRecognizer alloc] initWithTarget:self action:@selector(handlePan:)];
    pan.maximumNumberOfTouches = 1;
    [self addGestureRecognizer:pan];
  }
  return self;
}
- (void)layoutSubviews {
  [super layoutSubviews];
  self.layer.cornerRadius = MIN(self.bounds.size.width, self.bounds.size.height) * 0.5;
  const CGFloat knobSize = MIN(self.bounds.size.width, self.bounds.size.height) * 0.42;
  if (CGRectEqualToRect(self.knob.frame, CGRectZero)) {
    self.knob.frame = CGRectMake(0, 0, knobSize, knobSize);
    self.knob.center = CGPointMake(CGRectGetMidX(self.bounds), CGRectGetMidY(self.bounds));
  }
  self.knob.layer.cornerRadius = knobSize * 0.5;
}
- (void)handlePan:(UIPanGestureRecognizer*)pan {
  const CGFloat radius = MAX(1.0, MIN(self.bounds.size.width, self.bounds.size.height) * 0.36);
  CGPoint delta = [pan translationInView:self];
  CGFloat x = delta.x / radius;
  CGFloat y = delta.y / radius;
  const CGFloat magnitude = hypot(x, y);
  if (magnitude > 1.0) { x /= magnitude; y /= magnitude; }
  const BOOL ended = pan.state == UIGestureRecognizerStateEnded ||
      pan.state == UIGestureRecognizerStateCancelled ||
      pan.state == UIGestureRecognizerStateFailed;
  if (ended) { x = 0; y = 0; }
  self.knob.center = CGPointMake(CGRectGetMidX(self.bounds) + x * radius * 0.58,
                                 CGRectGetMidY(self.bounds) + y * radius * 0.58);
  // Screen Y grows downwards; XInput's thumb Y is positive up.
  if (self.valueChanged) self.valueChanged((float)x, (float)-y);
}
- (void)recenter {
  for (UIGestureRecognizer* recognizer in self.gestureRecognizers) {
    if (!recognizer.isEnabled) continue;
    recognizer.enabled = NO;
    recognizer.enabled = YES;
  }
  self.knob.center = CGPointMake(CGRectGetMidX(self.bounds), CGRectGetMidY(self.bounds));
  if (self.valueChanged) self.valueChanged(0, 0);
}
@end

@implementation RBXeniaTouchControlsView {
  NSString* _locale;
  UIView* _dpad;
  NSDictionary<NSString*, UIButton*>* _buttonViews;
  uint32_t _buttonsState;
  NSArray<NSString*>* _order;
  RBXeniaVirtualStickView* _leftStick;
  RBXeniaVirtualStickView* _rightStick;
  NSArray<NeoTouchElement*>* _elements;
  NeoTouchLayout* _stored;
  NSString* _storedKey;
  BOOL _overriding;
  BOOL _ghostHidden;
  NeoTouchLayout* _overrideLayout;
  BOOL _laidOut;
}

- (instancetype)initWithLocale:(NSString*)locale {
  self = [super initWithFrame:UIScreen.mainScreen.bounds];
  if (self) {
    _locale = NeoTouchLayoutCanonicalLocale(locale);
    _orientation = NeoTouchLayoutOrientationLandscape;
    _elements = @[];
    self.backgroundColor = UIColor.clearColor;
    self.multipleTouchEnabled = YES;
    self.accessibilityIdentifier = @"xenia-touch-controls";
    [self buildControls];
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(storeChanged:)
                                               name:NeoTouchLayoutStoreDidChangeNotification object:nil];
  }
  return self;
}

- (void)dealloc {
  [NSNotificationCenter.defaultCenter removeObserver:self];
}

- (UIButton*)padButton:(NSString*)title tag:(NSInteger)tag {
  UIButton* button = [UIButton buttonWithType:UIButtonTypeSystem];
  button.tag = tag;
  button.backgroundColor = [UIColor colorWithWhite:0 alpha:0.48];
  button.tintColor = UIColor.whiteColor;
  [button setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
  button.titleLabel.font = [UIFont systemFontOfSize:15 weight:UIFontWeightBold];
  button.layer.borderWidth = 1.0;
  button.layer.borderColor = [UIColor colorWithWhite:1 alpha:0.42].CGColor;
  button.layer.cornerRadius = 20;
  button.accessibilityLabel = title;
  [button setTitle:title forState:UIControlStateNormal];
  [button addTarget:self action:@selector(padDown:) forControlEvents:UIControlEventTouchDown];
  [button addTarget:self action:@selector(padUp:) forControlEvents:
      UIControlEventTouchUpInside | UIControlEventTouchUpOutside | UIControlEventTouchCancel];
  return button;
}

- (void)buildControls {
  // D-pad: four buttons in one element (112 x 112), as on the other engines.
  _dpad = [[UIView alloc] initWithFrame:CGRectMake(0, 0, 112, 112)];
  _dpad.accessibilityIdentifier = @"xenia-dpad";
  UIButton* up = [self padButton:@"↑" tag:kXeniaUp];
  UIButton* down = [self padButton:@"↓" tag:kXeniaDown];
  UIButton* left = [self padButton:@"←" tag:kXeniaLeft];
  UIButton* right = [self padButton:@"→" tag:kXeniaRight];
  for (UIButton* button in @[up, down, left, right]) [_dpad addSubview:button];
  up.frame = CGRectMake(37, 0, 38, 38);
  down.frame = CGRectMake(37, 74, 38, 38);
  left.frame = CGRectMake(0, 37, 38, 38);
  right.frame = CGRectMake(74, 37, 38, 38);
  [self addSubview:_dpad];

  UIButton* a = [self padButton:@"A" tag:kXeniaA];
  UIButton* b = [self padButton:@"B" tag:kXeniaB];
  UIButton* x = [self padButton:@"X" tag:kXeniaX];
  UIButton* y = [self padButton:@"Y" tag:kXeniaY];
  UIButton* lb = [self padButton:@"LB" tag:kXeniaLB];
  UIButton* rb = [self padButton:@"RB" tag:kXeniaRB];
  UIButton* lt = [self padButton:@"LT" tag:kXeniaTagLeftTrigger];
  UIButton* rt = [self padButton:@"RT" tag:kXeniaTagRightTrigger];
  for (UIButton* button in @[lb, rb, lt, rt]) button.layer.cornerRadius = 12;
  UIButton* l3 = [self padButton:@"L3" tag:kXeniaL3];
  UIButton* r3 = [self padButton:@"R3" tag:kXeniaR3];
  UIButton* back = [self padButton:@"BACK" tag:kXeniaBack];
  UIButton* start = [self padButton:@"START" tag:kXeniaStart];
  for (UIButton* button in @[l3, r3, back, start]) {
    button.titleLabel.font = [UIFont systemFontOfSize:10 weight:UIFontWeightSemibold];
    button.layer.cornerRadius = 12;
  }
  _leftStick = [RBXeniaVirtualStickView new];
  _rightStick = [RBXeniaVirtualStickView new];
  _leftStick.accessibilityIdentifier = @"xenia-left-stick";
  _rightStick.accessibilityIdentifier = @"xenia-right-stick";
  _buttonViews = @{@"a": a, @"b": b, @"x": x, @"y": y, @"lb": lb, @"rb": rb, @"lt": lt, @"rt": rt,
               @"l3": l3, @"r3": r3, @"back": back, @"start": start};
  _order = @[kXeniaDPad, @"y", @"a", @"x", @"b", kXeniaLeftStick, kXeniaRightStick,
             @"l3", @"r3", @"lb", @"lt", @"rb", @"rt", @"back", @"start"];
  for (NSString* identifier in _order) {
    UIView* view = [self viewForIdentifier:identifier];
    if (view.superview != self) [self addSubview:view];
  }
  __weak RBXeniaTouchControlsView* weakSelf = self;
  _leftStick.valueChanged = ^(float sx, float sy) {
    RBXeniaTouchControlsView* strongSelf = weakSelf;
    if (!strongSelf) return;
    strongSelf->_leftX = sx;
    strongSelf->_leftY = sy;
  };
  _rightStick.valueChanged = ^(float sx, float sy) {
    RBXeniaTouchControlsView* strongSelf = weakSelf;
    if (!strongSelf) return;
    strongSelf->_rightX = sx;
    strongSelf->_rightY = sy;
  };
}

- (UIView*)viewForIdentifier:(NSString*)identifier {
  if ([identifier isEqualToString:kXeniaDPad]) return _dpad;
  if ([identifier isEqualToString:kXeniaLeftStick]) return _leftStick;
  if ([identifier isEqualToString:kXeniaRightStick]) return _rightStick;
  return _buttonViews[identifier];
}

- (NSString*)nameForIdentifier:(NSString*)identifier {
  if ([identifier isEqualToString:kXeniaDPad]) return NeoTouchLayoutText(@"dpad", _locale);
  if ([identifier isEqualToString:kXeniaLeftStick]) return NeoTouchLayoutText(@"leftStick", _locale);
  if ([identifier isEqualToString:kXeniaRightStick]) return NeoTouchLayoutText(@"rightStick", _locale);
  // Button legends are product legends, never translated.
  return [_buttonViews[identifier] titleForState:UIControlStateNormal] ?: identifier;
}

- (NeoTouchElementKind)kindForIdentifier:(NSString*)identifier {
  if ([identifier isEqualToString:kXeniaDPad]) return NeoTouchElementKindDirectionalPad;
  if ([identifier hasPrefix:@"stick."]) return NeoTouchElementKindStick;
  if ([@[@"lb", @"rb", @"lt", @"rt"] containsObject:identifier]) return NeoTouchElementKindTrigger;
  if ([@[@"back", @"start"] containsObject:identifier]) return NeoTouchElementKindSystem;
  return NeoTouchElementKindButton;
}

#pragma mark Stock layout

- (NSDictionary<NSString*, NSValue*>*)stockFramesForBounds:(CGRect)bounds safeArea:(UIEdgeInsets)safe {
  const CGFloat w = bounds.size.width;
  const CGFloat h = bounds.size.height;
  const BOOL portrait = h > w;
  const CGFloat bottom = safe.bottom + 14;
  NSMutableDictionary* frames = [NSMutableDictionary dictionary];
  frames[kXeniaDPad] = [NSValue valueWithCGRect:CGRectMake(safe.left + 12, h - bottom - 112, 112, 112)];
  // Xbox 360 face buttons: Y top, A bottom, X left, B right.
  const CGRect face = CGRectMake(w - safe.right - 124, h - bottom - 112, 112, 112);
  frames[@"y"] = [NSValue valueWithCGRect:CGRectMake(face.origin.x + 37, face.origin.y + 0, 38, 38)];
  frames[@"a"] = [NSValue valueWithCGRect:CGRectMake(face.origin.x + 37, face.origin.y + 74, 38, 38)];
  frames[@"x"] = [NSValue valueWithCGRect:CGRectMake(face.origin.x + 0, face.origin.y + 37, 38, 38)];
  frames[@"b"] = [NSValue valueWithCGRect:CGRectMake(face.origin.x + 74, face.origin.y + 37, 38, 38)];
  CGRect leftStick, rightStick, leftShoulders, rightShoulders;
  if (portrait) {
    leftStick = CGRectMake(safe.left + 24, h - bottom - 222, 92, 92);
    rightStick = CGRectMake(w - safe.right - 116, h - bottom - 222, 92, 92);
    leftShoulders = CGRectMake(safe.left + 12, h - bottom - 276, 108, 40);
    rightShoulders = CGRectMake(w - safe.right - 120, h - bottom - 276, 108, 40);
  } else {
    leftStick = CGRectMake(safe.left + 136, h - bottom - 96, 88, 88);
    rightStick = CGRectMake(w - safe.right - 224, h - bottom - 96, 88, 88);
    leftShoulders = CGRectMake(safe.left + 12, h - bottom - 160, 108, 40);
    rightShoulders = CGRectMake(w - safe.right - 120, h - bottom - 160, 108, 40);
  }
  frames[kXeniaLeftStick] = [NSValue valueWithCGRect:leftStick];
  frames[kXeniaRightStick] = [NSValue valueWithCGRect:rightStick];
  // Stick clicks: a small button above each stick (the stick itself pans).
  frames[@"l3"] = [NSValue valueWithCGRect:CGRectMake(CGRectGetMidX(leftStick) - 20, leftStick.origin.y - 38, 40, 32)];
  frames[@"r3"] = [NSValue valueWithCGRect:CGRectMake(CGRectGetMidX(rightStick) - 20, rightStick.origin.y - 38, 40, 32)];
  // Bumper and trigger pairs: 50 x 40 buttons 58 pt apart, the bumper outside.
  frames[@"lb"] = [NSValue valueWithCGRect:CGRectMake(leftShoulders.origin.x, leftShoulders.origin.y, 50, 40)];
  frames[@"lt"] = [NSValue valueWithCGRect:CGRectMake(leftShoulders.origin.x + 58, leftShoulders.origin.y, 50, 40)];
  frames[@"rt"] = [NSValue valueWithCGRect:CGRectMake(rightShoulders.origin.x, rightShoulders.origin.y, 50, 40)];
  frames[@"rb"] = [NSValue valueWithCGRect:CGRectMake(rightShoulders.origin.x + 58, rightShoulders.origin.y, 50, 40)];
  const CGFloat centerY = h - bottom - 42;
  frames[@"back"] = [NSValue valueWithCGRect:CGRectMake(w * 0.5 - 98, centerY, 78, 36)];
  frames[@"start"] = [NSValue valueWithCGRect:CGRectMake(w * 0.5 + 20, centerY, 78, 36)];
  return frames;
}

#pragma mark Layout

- (NeoTouchLayout*)currentLayout {
  if (_overriding) return _overrideLayout;
  NSString* cacheKey = [NSString stringWithFormat:@"%@|%@", _orientation, _gameKey ?: @""];
  if (!_stored || ![_storedKey isEqualToString:cacheKey]) {
    _stored = [NeoTouchLayoutStore.sharedStore effectiveLayoutForKey:XeniaTouchLayoutKey
                                                         orientation:_orientation game:_gameKey gameSpecific:NULL];
    _storedKey = cacheKey;
  }
  return _stored;
}

- (void)layoutSubviews {
  [super layoutSubviews];
  if (self.bounds.size.width <= 0 || self.bounds.size.height <= 0) return;
  NSString* orientation = NeoTouchLayoutOrientationForSize(self.bounds.size);
  if (![orientation isEqualToString:_orientation]) {
    _orientation = orientation;
    _stored = nil;
    if (_laidOut) {
      // A finger held across a rotation must not keep a control pressed.
      [self releaseAllInput];
      if (self.orientationChanged) self.orientationChanged();
    }
  }
  _laidOut = YES;
  NSDictionary<NSString*, NSValue*>* frames = [self stockFramesForBounds:self.bounds safeArea:self.safeAreaInsets];
  NSMutableArray<NeoTouchElement*>* elements = [NSMutableArray array];
  for (NSString* identifier in _order) {
    UIView* view = [self viewForIdentifier:identifier];
    const CGRect frame = frames[identifier].CGRectValue;
    view.transform = CGAffineTransformIdentity;
    view.bounds = CGRectMake(0, 0, frame.size.width, frame.size.height);
    view.center = CGPointMake(CGRectGetMidX(frame), CGRectGetMidY(frame));
    NeoTouchElement* element = [[NeoTouchElement alloc] initWithIdentifier:identifier
                                                                       name:[self nameForIdentifier:identifier]
                                                                       kind:[self kindForIdentifier:identifier]
                                                                       view:view];
    [element captureDefaultGeometryInCanvas:self];
    [elements addObject:element];
  }
  _elements = elements;
  [NeoTouchLayoutApplier applyLayout:[self currentLayout] elements:elements canvas:self editing:_ghostHidden];
}

- (void)storeChanged:(NSNotification*)notification {
  NSString* key = notification.userInfo[@"key"];
  if (!key || [key isEqualToString:XeniaTouchLayoutKey]) [self reloadFromStore];
}

- (void)setGameKey:(NSString*)gameKey {
  _gameKey = [NeoTouchLayoutGameKey(gameKey) copy];
  [self reloadFromStore];
}

- (void)reloadFromStore {
  _stored = nil;
  _storedKey = nil;
  [self setNeedsLayout];
  [self layoutIfNeeded];
}

- (BOOL)editing {
  return _overriding;
}

- (void)endEditingOverride {
  _overriding = NO;
  _ghostHidden = NO;
  _overrideLayout = nil;
  [self reloadFromStore];
}

#pragma mark Input

- (void)padDown:(UIButton*)sender {
  if (sender.tag == kXeniaTagLeftTrigger) {
    _leftTrigger = 1.f;
  } else if (sender.tag == kXeniaTagRightTrigger) {
    _rightTrigger = 1.f;
  } else {
    _buttonsState |= (uint32_t)sender.tag & 0xFFFFu;
  }
}

- (void)padUp:(UIButton*)sender {
  if (sender.tag == kXeniaTagLeftTrigger) {
    _leftTrigger = 0.f;
  } else if (sender.tag == kXeniaTagRightTrigger) {
    _rightTrigger = 0.f;
  } else {
    _buttonsState &= ~((uint32_t)sender.tag & 0xFFFFu);
  }
}

- (uint32_t)buttons {
  return _buttonsState;
}

- (void)releaseAllInput {
  NSMutableArray<UIButton*>* buttons = [NSMutableArray arrayWithArray:_buttonViews.allValues];
  for (UIView* child in _dpad.subviews)
    if ([child isKindOfClass:UIButton.class]) [buttons addObject:(UIButton*)child];
  for (UIButton* button in buttons) {
    if (button.isTracking || button.isHighlighted) [button cancelTrackingWithEvent:nil];
    button.highlighted = NO;
  }
  [_leftStick recenter];
  [_rightStick recenter];
  _buttonsState = 0;
  _leftTrigger = _rightTrigger = 0.f;
  _leftX = _leftY = _rightX = _rightY = 0.f;
}

#pragma mark NeoTouchLayoutEditorHost

- (UIView*)touchLayoutCanvas {
  return self;
}

- (NSArray<NeoTouchElement*>*)touchLayoutElements {
  return _elements;
}

- (void)touchLayoutApplyLayout:(NeoTouchLayout*)layout editing:(BOOL)editing {
  _overriding = YES;
  _ghostHidden = editing;
  _overrideLayout = [layout copy] ?: [NeoTouchLayout new];
  [self setNeedsLayout];
  [self layoutIfNeeded];
}

- (UIInterfaceOrientationMask)touchLayoutSupportedInterfaceOrientations {
  // The XeniOS session turns with the phone; both orientations have a stock layout.
  return UIInterfaceOrientationMaskAllButUpsideDown;
}

@end

void XeniaTouchControlsRegisterPreview(void) {
  [NeoTouchLayoutRegistry registerPreviewFactory:^UIView<NeoTouchLayoutEditorHost>*(NSString* key, NSString* locale) {
    RBXeniaTouchControlsView* preview = [[RBXeniaTouchControlsView alloc] initWithLocale:locale];
    // A preview never receives a touch and has no session to send input to.
    preview.userInteractionEnabled = NO;
    return preview;
  } forLayoutKeys:@[XeniaTouchLayoutKey]];
}

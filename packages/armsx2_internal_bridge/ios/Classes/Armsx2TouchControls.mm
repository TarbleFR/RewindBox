// SPDX-License-Identifier: GPL-3.0-or-later
#import "Armsx2TouchControls.h"
#include <cmath>

@implementation Armsx2VirtualStickView
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
  // Measured in the stick's own coordinates: a layout transform scales the
  // drawing, the touch area and the travel together.
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
  self.knob.center = CGPointMake(
      CGRectGetMidX(self.bounds) + x * radius * 0.58,
      CGRectGetMidY(self.bounds) + y * radius * 0.58);
  if (self.valueChanged) self.valueChanged((float)x, (float)y);
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

// Element identifiers of the "ps2" layout and the ARMSX2PadButton of each button.
static NSString* const kArmsx2DPad = @"dpad";
static NSString* const kArmsx2LeftStick = @"stick.left";
static NSString* const kArmsx2RightStick = @"stick.right";

@implementation Armsx2TouchControlsView {
  NSString* _locale;
  UIView* _dpad;
  NSDictionary<NSString*, UIButton*>* _buttons;
  NSArray<NSString*>* _order;
  Armsx2VirtualStickView* _leftStick;
  Armsx2VirtualStickView* _rightStick;
  float _leftX, _leftY, _rightX, _rightY;
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
    self.accessibilityIdentifier = @"armsx2-touch-controls";
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
  [button setTitle:title forState:UIControlStateNormal];
  [button addTarget:self action:@selector(padDown:) forControlEvents:UIControlEventTouchDown];
  [button addTarget:self action:@selector(padUp:) forControlEvents:
      UIControlEventTouchUpInside | UIControlEventTouchUpOutside | UIControlEventTouchCancel];
  return button;
}

- (void)buildControls {
  // D-pad: four buttons in one element, placed as before (112 x 112).
  _dpad = [[UIView alloc] initWithFrame:CGRectMake(0, 0, 112, 112)];
  _dpad.accessibilityIdentifier = @"armsx2-dpad";
  UIButton* up = [self padButton:@"↑" tag:0];
  UIButton* down = [self padButton:@"↓" tag:1];
  UIButton* left = [self padButton:@"←" tag:2];
  UIButton* right = [self padButton:@"→" tag:3];
  for (UIButton* button in @[up, down, left, right]) [_dpad addSubview:button];
  up.frame = CGRectMake(37, 0, 38, 38);
  down.frame = CGRectMake(37, 74, 38, 38);
  left.frame = CGRectMake(0, 37, 38, 38);
  right.frame = CGRectMake(74, 37, 38, 38);
  [self addSubview:_dpad];

  UIButton* triangle = [self padButton:@"△" tag:7];
  UIButton* cross = [self padButton:@"×" tag:4];
  UIButton* square = [self padButton:@"□" tag:6];
  UIButton* circle = [self padButton:@"○" tag:5];
  _leftStick = [Armsx2VirtualStickView new];
  _rightStick = [Armsx2VirtualStickView new];
  _leftStick.accessibilityIdentifier = @"armsx2-left-stick";
  _rightStick.accessibilityIdentifier = @"armsx2-right-stick";
  UIButton* l1 = [self padButton:@"L1" tag:8];
  UIButton* l2 = [self padButton:@"L2" tag:10];
  UIButton* r1 = [self padButton:@"R1" tag:9];
  UIButton* r2 = [self padButton:@"R2" tag:11];
  for (UIButton* button in @[l1, l2, r1, r2]) button.layer.cornerRadius = 12;
  UIButton* start = [self padButton:@"START" tag:12];
  start.accessibilityIdentifier = @"armsx2-start";
  UIButton* select = [self padButton:@"SELECT" tag:13];
  select.accessibilityIdentifier = @"armsx2-select";
  start.titleLabel.font = select.titleLabel.font = [UIFont systemFontOfSize:10 weight:UIFontWeightSemibold];
  start.layer.cornerRadius = select.layer.cornerRadius = 12;
  _buttons = @{@"triangle": triangle, @"cross": cross, @"square": square, @"circle": circle,
               @"l1": l1, @"l2": l2, @"r1": r1, @"r2": r2, @"start": start, @"select": select};
  // Drawing order of the earlier sessions: D-pad, face buttons, sticks, shoulders, START/SELECT.
  _order = @[kArmsx2DPad, @"triangle", @"cross", @"square", @"circle", kArmsx2LeftStick, kArmsx2RightStick,
             @"l1", @"l2", @"r1", @"r2", @"start", @"select"];
  for (NSString* identifier in _order) {
    UIView* view = [self viewForIdentifier:identifier];
    if (view.superview != self) [self addSubview:view];
  }

  __weak Armsx2TouchControlsView* weakSelf = self;
  _leftStick.valueChanged = ^(float x, float y) {
    Armsx2TouchControlsView* strongSelf = weakSelf;
    if (!strongSelf) return;
    strongSelf->_leftX = x;
    strongSelf->_leftY = y;
    [strongSelf sendSticks];
  };
  _rightStick.valueChanged = ^(float x, float y) {
    Armsx2TouchControlsView* strongSelf = weakSelf;
    if (!strongSelf) return;
    strongSelf->_rightX = x;
    strongSelf->_rightY = y;
    [strongSelf sendSticks];
  };
}

- (UIView*)viewForIdentifier:(NSString*)identifier {
  if ([identifier isEqualToString:kArmsx2DPad]) return _dpad;
  if ([identifier isEqualToString:kArmsx2LeftStick]) return _leftStick;
  if ([identifier isEqualToString:kArmsx2RightStick]) return _rightStick;
  return _buttons[identifier];
}

- (NSString*)nameForIdentifier:(NSString*)identifier {
  if ([identifier isEqualToString:kArmsx2DPad]) return NeoTouchLayoutText(@"dpad", _locale);
  if ([identifier isEqualToString:kArmsx2LeftStick]) return NeoTouchLayoutText(@"leftStick", _locale);
  if ([identifier isEqualToString:kArmsx2RightStick]) return NeoTouchLayoutText(@"rightStick", _locale);
  NSDictionary* names = @{@"triangle": @"△", @"cross": @"✕", @"square": @"□", @"circle": @"○"};
  return names[identifier] ?: [_buttons[identifier] titleForState:UIControlStateNormal] ?: identifier;
}

- (NeoTouchElementKind)kindForIdentifier:(NSString*)identifier {
  if ([identifier isEqualToString:kArmsx2DPad]) return NeoTouchElementKindDirectionalPad;
  if ([identifier hasPrefix:@"stick."]) return NeoTouchElementKindStick;
  if ([identifier hasPrefix:@"l"] || [identifier hasPrefix:@"r"]) return NeoTouchElementKindTrigger;
  if ([identifier isEqualToString:@"start"] || [identifier isEqualToString:@"select"]) return NeoTouchElementKindSystem;
  return NeoTouchElementKindButton;
}

#pragma mark Stock layout (identical to the earlier sessions)

- (NSDictionary<NSString*, NSValue*>*)stockFramesForBounds:(CGRect)bounds safeArea:(UIEdgeInsets)safe {
  const CGFloat w = bounds.size.width;
  const CGFloat h = bounds.size.height;
  const BOOL portrait = h > w;
  const CGFloat bottom = safe.bottom + 14;
  NSMutableDictionary* frames = [NSMutableDictionary dictionary];
  frames[kArmsx2DPad] = [NSValue valueWithCGRect:CGRectMake(safe.left + 12, h - bottom - 112, 112, 112)];
  const CGRect face = CGRectMake(w - safe.right - 124, h - bottom - 112, 112, 112);
  frames[@"triangle"] = [NSValue valueWithCGRect:CGRectMake(face.origin.x + 37, face.origin.y + 0, 38, 38)];
  frames[@"cross"] = [NSValue valueWithCGRect:CGRectMake(face.origin.x + 37, face.origin.y + 74, 38, 38)];
  frames[@"square"] = [NSValue valueWithCGRect:CGRectMake(face.origin.x + 0, face.origin.y + 37, 38, 38)];
  frames[@"circle"] = [NSValue valueWithCGRect:CGRectMake(face.origin.x + 74, face.origin.y + 37, 38, 38)];
  CGRect leftShoulders, rightShoulders;
  if (portrait) {
    frames[kArmsx2LeftStick] = [NSValue valueWithCGRect:CGRectMake(safe.left + 24, h - bottom - 222, 92, 92)];
    frames[kArmsx2RightStick] = [NSValue valueWithCGRect:CGRectMake(w - safe.right - 116, h - bottom - 222, 92, 92)];
    leftShoulders = CGRectMake(safe.left + 12, h - bottom - 276, 108, 40);
    rightShoulders = CGRectMake(w - safe.right - 120, h - bottom - 276, 108, 40);
  } else {
    frames[kArmsx2LeftStick] = [NSValue valueWithCGRect:CGRectMake(safe.left + 136, h - bottom - 96, 88, 88)];
    frames[kArmsx2RightStick] = [NSValue valueWithCGRect:CGRectMake(w - safe.right - 224, h - bottom - 96, 88, 88)];
    leftShoulders = CGRectMake(safe.left + 12, h - bottom - 160, 108, 40);
    rightShoulders = CGRectMake(w - safe.right - 120, h - bottom - 160, 108, 40);
  }
  // The former L1/L2 and R1/R2 pairs: 50 x 40 buttons 58 pt apart.
  frames[@"l1"] = [NSValue valueWithCGRect:CGRectMake(leftShoulders.origin.x, leftShoulders.origin.y, 50, 40)];
  frames[@"l2"] = [NSValue valueWithCGRect:CGRectMake(leftShoulders.origin.x + 58, leftShoulders.origin.y, 50, 40)];
  frames[@"r1"] = [NSValue valueWithCGRect:CGRectMake(rightShoulders.origin.x, rightShoulders.origin.y, 50, 40)];
  frames[@"r2"] = [NSValue valueWithCGRect:CGRectMake(rightShoulders.origin.x + 58, rightShoulders.origin.y, 50, 40)];
  const CGFloat centerY = h - bottom - 42;
  frames[@"select"] = [NSValue valueWithCGRect:CGRectMake(w * 0.5 - 98, centerY, 78, 36)];
  frames[@"start"] = [NSValue valueWithCGRect:CGRectMake(w * 0.5 + 20, centerY, 78, 36)];
  return frames;
}

#pragma mark Layout

- (NeoTouchLayout*)currentLayout {
  if (_overriding) return _overrideLayout;
  NSString* cacheKey = [NSString stringWithFormat:@"%@|%@", _orientation, _gameKey ?: @""];
  if (!_stored || ![_storedKey isEqualToString:cacheKey]) {
    _stored = [NeoTouchLayoutStore.sharedStore effectiveLayoutForKey:NeoTouchLayoutKeyPlayStation2
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
      // A finger held across a rotation must not keep a button pressed.
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
  if (!key || [key isEqualToString:NeoTouchLayoutKeyPlayStation2]) [self reloadFromStore];
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
  if (sender.tag >= 0 && sender.tag < 16 && self.buttonChanged) self.buttonChanged((uint32_t)sender.tag, YES);
}

- (void)padUp:(UIButton*)sender {
  if (sender.tag >= 0 && sender.tag < 16 && self.buttonChanged) self.buttonChanged((uint32_t)sender.tag, NO);
}

- (void)sendSticks {
  if (self.sticksChanged) self.sticksChanged(_leftX, _leftY, _rightX, _rightY);
}

- (void)releaseAllInput {
  NSMutableArray<UIButton*>* buttons = [NSMutableArray arrayWithArray:_buttons.allValues];
  for (UIView* child in _dpad.subviews)
    if ([child isKindOfClass:UIButton.class]) [buttons addObject:(UIButton*)child];
  for (UIButton* button in buttons) {
    if (button.isTracking || button.isHighlighted) [button cancelTrackingWithEvent:nil];
    button.highlighted = NO;
  }
  // The pan recognizers end; both report a centred stick.
  [_leftStick recenter];
  [_rightStick recenter];
  _leftX = _leftY = _rightX = _rightY = 0;
  if (self.buttonChanged)
    for (uint32_t index = 0; index < 16; index++) self.buttonChanged(index, NO);
  [self sendSticks];
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

@end

void Armsx2TouchControlsRegisterPreview(void) {
  [NeoTouchLayoutRegistry registerPreviewFactory:^UIView<NeoTouchLayoutEditorHost>*(NSString* key, NSString* locale) {
    Armsx2TouchControlsView* preview = [[Armsx2TouchControlsView alloc] initWithLocale:locale];
    // A preview never receives a touch and has no session to send input to.
    preview.userInteractionEnabled = NO;
    return preview;
  } forLayoutKeys:@[NeoTouchLayoutKeyPlayStation2]];
}

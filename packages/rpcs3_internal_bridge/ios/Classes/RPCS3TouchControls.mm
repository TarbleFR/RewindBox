// SPDX-License-Identifier: GPL-3.0-or-later
#import "RPCS3TouchControls.h"
#include "Rpcs3CoreABI.h"

#include <math.h>

static inline float RPCS3TouchClamp(float value, float minimum, float maximum) {
  return fminf(maximum, fmaxf(minimum, value));
}

@implementation RPCS3InputPassthroughView
- (BOOL)pointInside:(CGPoint)point withEvent:(UIEvent*)event {
  if (self.hidden || self.alpha <= 0.01 || !self.userInteractionEnabled) return NO;
  for (UIView* child in self.subviews.reverseObjectEnumerator) {
    if (child.hidden || child.alpha <= 0.01 || !child.userInteractionEnabled) continue;
    // convertPoint follows the child's layout transform: the touch area is
    // the drawn control wherever it was moved or resized.
    CGPoint childPoint = [self convertPoint:point toView:child];
    if ([child pointInside:childPoint withEvent:event]) return YES;
  }
  return NO;
}
@end

@implementation RPCS3TouchStickView
- (instancetype)initWithFrame:(CGRect)frame {
  self = [super initWithFrame:frame];
  if (self) {
    self.multipleTouchEnabled = NO;
    self.backgroundColor = [UIColor colorWithWhite:0.08 alpha:0.34];
    self.layer.borderWidth = 1.5;
    self.layer.borderColor = [UIColor colorWithWhite:1 alpha:0.42].CGColor;
    self.clipsToBounds = NO;

    _knob = [[UIView alloc] initWithFrame:CGRectZero];
    _knob.userInteractionEnabled = NO;
    _knob.backgroundColor = [UIColor colorWithWhite:1 alpha:0.28];
    _knob.layer.borderWidth = 1.0;
    _knob.layer.borderColor = [UIColor colorWithWhite:1 alpha:0.55].CGColor;
    [self addSubview:_knob];
  }
  return self;
}

- (void)layoutSubviews {
  [super layoutSubviews];
  CGFloat side = MIN(self.bounds.size.width, self.bounds.size.height);
  self.layer.cornerRadius = side * 0.5;
  CGFloat knobSide = side * 0.43;
  self.knob.bounds = CGRectMake(0, 0, knobSide, knobSide);
  self.knob.layer.cornerRadius = knobSide * 0.5;
  if (!self.trackingTouch) {
    self.knob.center = CGPointMake(CGRectGetMidX(self.bounds), CGRectGetMidY(self.bounds));
  }
}

- (void)updateFromPoint:(CGPoint)point {
  CGPoint center = CGPointMake(CGRectGetMidX(self.bounds), CGRectGetMidY(self.bounds));
  CGFloat side = MIN(self.bounds.size.width, self.bounds.size.height);
  CGFloat radius = MAX(1.0, side * 0.36);
  CGFloat dx = point.x - center.x;
  CGFloat dy = point.y - center.y;
  CGFloat distance = hypot(dx, dy);
  if (distance > radius) {
    dx = dx / distance * radius;
    dy = dy / distance * radius;
  }
  self.knob.center = CGPointMake(center.x + dx, center.y + dy);
  float x = RPCS3TouchClamp((float)(dx / radius), -1.0f, 1.0f);
  // UIKit Y grows down. GameController/RPCS3 frontend convention is positive up.
  float y = RPCS3TouchClamp((float)(-dy / radius), -1.0f, 1.0f);
  if (self.valueChanged) self.valueChanged(x, y);
}

- (void)touchesBegan:(NSSet<UITouch*>*)touches withEvent:(UIEvent*)event {
  self.trackingTouch = YES;
  UITouch* touch = touches.anyObject;
  if (touch) [self updateFromPoint:[touch locationInView:self]];
}

- (void)touchesMoved:(NSSet<UITouch*>*)touches withEvent:(UIEvent*)event {
  UITouch* touch = touches.anyObject;
  if (touch) [self updateFromPoint:[touch locationInView:self]];
}

- (void)endTracking {
  self.trackingTouch = NO;
  self.knob.center = CGPointMake(CGRectGetMidX(self.bounds), CGRectGetMidY(self.bounds));
  if (self.valueChanged) self.valueChanged(0.0f, 0.0f);
}

- (void)touchesEnded:(NSSet<UITouch*>*)touches withEvent:(UIEvent*)event { [self endTracking]; }
- (void)touchesCancelled:(NSSet<UITouch*>*)touches withEvent:(UIEvent*)event { [self endTracking]; }
@end

static NSString* const kRPCS3DPad = @"dpad";
static NSString* const kRPCS3LeftStick = @"stick.left";
static NSString* const kRPCS3RightStick = @"stick.right";

@implementation RPCS3TouchControlsView {
  NSString* _locale;
  RPCS3InputPassthroughView* _dpad;
  NSDictionary<NSString*, UIButton*>* _buttons;
  NSArray<NSString*>* _order;
  RPCS3TouchStickView* _leftStick;
  RPCS3TouchStickView* _rightStick;
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
    self.accessibilityIdentifier = @"rpcs3.touch.controls";
    [self buildControls];
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(storeChanged:)
                                               name:NeoTouchLayoutStoreDidChangeNotification object:nil];
  }
  return self;
}

- (void)dealloc {
  [NSNotificationCenter.defaultCenter removeObserver:self];
}

- (UIButton*)makeButton:(NSString*)title bit:(uint64_t)bit accessibility:(NSString*)accessibility {
  UIButton* button = [UIButton buttonWithType:UIButtonTypeSystem];
  button.tag = (NSInteger)bit;
  button.tintColor = UIColor.whiteColor;
  button.titleLabel.font = [UIFont systemFontOfSize:18 weight:UIFontWeightSemibold];
  button.backgroundColor = [UIColor colorWithWhite:0.06 alpha:0.38];
  button.layer.borderWidth = 1.0;
  button.layer.borderColor = [UIColor colorWithWhite:1 alpha:0.38].CGColor;
  button.layer.cornerRadius = 22;
  button.accessibilityLabel = accessibility;
  [button setTitle:title forState:UIControlStateNormal];
  [button setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
  [button addTarget:self action:@selector(touchButtonDown:) forControlEvents:UIControlEventTouchDown];
  [button addTarget:self action:@selector(touchButtonUp:)
      forControlEvents:UIControlEventTouchUpInside | UIControlEventTouchUpOutside | UIControlEventTouchCancel];
  return button;
}

- (void)buildControls {
  // The four D-pad buttons move and scale as one element.
  _dpad = [[RPCS3InputPassthroughView alloc] initWithFrame:CGRectZero];
  _dpad.backgroundColor = UIColor.clearColor;
  _dpad.accessibilityIdentifier = @"rpcs3.touch.dpad";
  NSMutableDictionary* buttons = [NSMutableDictionary dictionary];
  buttons[@"dpad.up"] = [self makeButton:@"▲" bit:rpcs3_ios_pad_up accessibility:@"D-pad Up"];
  buttons[@"dpad.down"] = [self makeButton:@"▼" bit:rpcs3_ios_pad_down accessibility:@"D-pad Down"];
  buttons[@"dpad.left"] = [self makeButton:@"◀" bit:rpcs3_ios_pad_left accessibility:@"D-pad Left"];
  buttons[@"dpad.right"] = [self makeButton:@"▶" bit:rpcs3_ios_pad_right accessibility:@"D-pad Right"];
  for (NSString* key in @[@"dpad.up", @"dpad.down", @"dpad.left", @"dpad.right"]) [_dpad addSubview:buttons[key]];
  [self addSubview:_dpad];

  buttons[@"square"] = [self makeButton:@"□" bit:rpcs3_ios_pad_square accessibility:@"Square"];
  buttons[@"cross"] = [self makeButton:@"✕" bit:rpcs3_ios_pad_cross accessibility:@"Cross"];
  buttons[@"circle"] = [self makeButton:@"○" bit:rpcs3_ios_pad_circle accessibility:@"Circle"];
  buttons[@"triangle"] = [self makeButton:@"△" bit:rpcs3_ios_pad_triangle accessibility:@"Triangle"];
  buttons[@"l1"] = [self makeButton:@"L1" bit:rpcs3_ios_pad_l1 accessibility:@"L1"];
  buttons[@"l2"] = [self makeButton:@"L2" bit:rpcs3_ios_pad_l2 accessibility:@"L2"];
  buttons[@"r1"] = [self makeButton:@"R1" bit:rpcs3_ios_pad_r1 accessibility:@"R1"];
  buttons[@"r2"] = [self makeButton:@"R2" bit:rpcs3_ios_pad_r2 accessibility:@"R2"];
  buttons[@"select"] = [self makeButton:@"SELECT" bit:rpcs3_ios_pad_select accessibility:@"Select"];
  buttons[@"start"] = [self makeButton:@"START" bit:rpcs3_ios_pad_start accessibility:@"Start"];
  _buttons = buttons;
  // Drawing order of the earlier sessions.
  for (NSString* key in @[@"square", @"cross", @"circle", @"triangle", @"l1", @"l2", @"r1", @"r2", @"select", @"start"])
    [self addSubview:buttons[key]];

  _leftStick = [[RPCS3TouchStickView alloc] initWithFrame:CGRectZero];
  _leftStick.accessibilityLabel = @"Left analog stick";
  [self addSubview:_leftStick];
  _rightStick = [[RPCS3TouchStickView alloc] initWithFrame:CGRectZero];
  _rightStick.accessibilityLabel = @"Right analog stick";
  [self addSubview:_rightStick];
  _order = @[kRPCS3DPad, @"square", @"cross", @"circle", @"triangle", @"l1", @"l2", @"r1", @"r2", @"select",
             @"start", kRPCS3LeftStick, kRPCS3RightStick];

  __weak RPCS3TouchControlsView* weakSelf = self;
  _leftStick.valueChanged = ^(float x, float y) {
    RPCS3TouchControlsView* strongSelf = weakSelf;
    if (strongSelf.stickChanged) strongSelf.stickChanged(0, x, y);
  };
  _rightStick.valueChanged = ^(float x, float y) {
    RPCS3TouchControlsView* strongSelf = weakSelf;
    if (strongSelf.stickChanged) strongSelf.stickChanged(1, x, y);
  };
}

- (UIView*)controlForIdentifier:(NSString*)identifier {
  if ([identifier isEqualToString:kRPCS3DPad]) return _dpad;
  if ([identifier isEqualToString:kRPCS3LeftStick]) return _leftStick;
  if ([identifier isEqualToString:kRPCS3RightStick]) return _rightStick;
  return _buttons[identifier];
}

- (NSString*)nameForIdentifier:(NSString*)identifier {
  if ([identifier isEqualToString:kRPCS3DPad]) return NeoTouchLayoutText(@"dpad", _locale);
  if ([identifier isEqualToString:kRPCS3LeftStick]) return NeoTouchLayoutText(@"leftStick", _locale);
  if ([identifier isEqualToString:kRPCS3RightStick]) return NeoTouchLayoutText(@"rightStick", _locale);
  return [_buttons[identifier] titleForState:UIControlStateNormal] ?: identifier;
}

- (NeoTouchElementKind)kindForIdentifier:(NSString*)identifier {
  if ([identifier isEqualToString:kRPCS3DPad]) return NeoTouchElementKindDirectionalPad;
  if ([identifier hasPrefix:@"stick."]) return NeoTouchElementKindStick;
  if ([identifier hasPrefix:@"l"] || [identifier hasPrefix:@"r"]) return NeoTouchElementKindTrigger;
  if ([identifier isEqualToString:@"start"] || [identifier isEqualToString:@"select"]) return NeoTouchElementKindSystem;
  return NeoTouchElementKindButton;
}

#pragma mark Stock layout (identical to the earlier sessions)

static CGRect RPCS3Centered(CGPoint center, CGFloat width, CGFloat height) {
  return CGRectMake(center.x - width * 0.5, center.y - height * 0.5, width, height);
}

- (NSDictionary<NSString*, NSValue*>*)stockFramesForBounds:(CGRect)bounds safeArea:(UIEdgeInsets)insets {
  const CGFloat width = CGRectGetWidth(bounds);
  const CGFloat height = CGRectGetHeight(bounds);
  const CGFloat shortSide = MIN(width, height);
  const CGFloat button = MIN(56.0, MAX(42.0, shortSide * 0.12));
  const CGFloat miniWidth = MIN(74.0, MAX(58.0, button * 1.35));
  const CGFloat miniHeight = MIN(40.0, MAX(32.0, button * 0.72));
  const CGFloat stick = MIN(116.0, MAX(86.0, shortSide * 0.24));
  const CGFloat edge = 14.0;
  const CGFloat left = insets.left + edge;
  const CGFloat right = insets.right + edge;
  const CGFloat bottom = insets.bottom + edge;
  const CGFloat top = insets.top + edge;
  const CGFloat d = button * 0.88;
  NSMutableDictionary* frames = [NSMutableDictionary dictionary];

  // The D-pad element spans its four buttons; inside it they keep their places.
  const CGPoint dpadCenter = CGPointMake(left + button * 1.55, height - bottom - button * 1.55);
  const CGFloat dpadSide = 2.0 * d + button;
  frames[kRPCS3DPad] = [NSValue valueWithCGRect:RPCS3Centered(dpadCenter, dpadSide, dpadSide)];
  const CGPoint middle = CGPointMake(dpadSide * 0.5, dpadSide * 0.5);
  frames[@"dpad.up"] = [NSValue valueWithCGRect:RPCS3Centered(CGPointMake(middle.x, middle.y - d), button, button)];
  frames[@"dpad.down"] = [NSValue valueWithCGRect:RPCS3Centered(CGPointMake(middle.x, middle.y + d), button, button)];
  frames[@"dpad.left"] = [NSValue valueWithCGRect:RPCS3Centered(CGPointMake(middle.x - d, middle.y), button, button)];
  frames[@"dpad.right"] = [NSValue valueWithCGRect:RPCS3Centered(CGPointMake(middle.x + d, middle.y), button, button)];

  const CGPoint faceCenter = CGPointMake(width - right - button * 1.55, height - bottom - button * 1.55);
  frames[@"triangle"] = [NSValue valueWithCGRect:RPCS3Centered(CGPointMake(faceCenter.x, faceCenter.y - d), button, button)];
  frames[@"cross"] = [NSValue valueWithCGRect:RPCS3Centered(CGPointMake(faceCenter.x, faceCenter.y + d), button, button)];
  frames[@"square"] = [NSValue valueWithCGRect:RPCS3Centered(CGPointMake(faceCenter.x - d, faceCenter.y), button, button)];
  frames[@"circle"] = [NSValue valueWithCGRect:RPCS3Centered(CGPointMake(faceCenter.x + d, faceCenter.y), button, button)];

  const CGFloat stickY = height - bottom - stick * 0.58;
  const CGFloat leftStickX = MIN(width * 0.39, left + button * 4.35);
  const CGFloat rightStickX = MAX(width * 0.61, width - right - button * 4.35);
  frames[kRPCS3LeftStick] = [NSValue valueWithCGRect:RPCS3Centered(CGPointMake(leftStickX, stickY), stick, stick)];
  frames[kRPCS3RightStick] = [NSValue valueWithCGRect:RPCS3Centered(CGPointMake(rightStickX, stickY), stick, stick)];

  const CGFloat shoulderY = top + miniHeight * 0.5;
  frames[@"l2"] = [NSValue valueWithCGRect:RPCS3Centered(CGPointMake(left + 82.0, shoulderY), miniWidth, miniHeight)];
  frames[@"l1"] = [NSValue valueWithCGRect:RPCS3Centered(CGPointMake(left + 82.0 + miniWidth + 8.0, shoulderY),
                                                         miniWidth, miniHeight)];
  frames[@"r2"] = [NSValue valueWithCGRect:RPCS3Centered(CGPointMake(width - right - 82.0, shoulderY), miniWidth, miniHeight)];
  frames[@"r1"] = [NSValue valueWithCGRect:RPCS3Centered(CGPointMake(width - right - 82.0 - miniWidth - 8.0, shoulderY),
                                                         miniWidth, miniHeight)];
  const CGFloat centerY = top + miniHeight * 0.5;
  frames[@"select"] = [NSValue valueWithCGRect:RPCS3Centered(CGPointMake(width * 0.5 - miniWidth - 12.0, centerY),
                                                             miniWidth, miniHeight)];
  frames[@"start"] = [NSValue valueWithCGRect:RPCS3Centered(CGPointMake(width * 0.5 + miniWidth + 12.0, centerY),
                                                            miniWidth, miniHeight)];
  return frames;
}

#pragma mark Layout

- (NeoTouchLayout*)currentLayout {
  if (_overriding) return _overrideLayout;
  NSString* cacheKey = [NSString stringWithFormat:@"%@|%@", _orientation, _gameKey ?: @""];
  if (!_stored || ![_storedKey isEqualToString:cacheKey]) {
    _stored = [NeoTouchLayoutStore.sharedStore effectiveLayoutForKey:NeoTouchLayoutKeyPlayStation3
                                                         orientation:_orientation game:_gameKey gameSpecific:NULL];
    _storedKey = cacheKey;
  }
  return _stored;
}

- (void)placeView:(UIView*)view frame:(CGRect)frame {
  view.transform = CGAffineTransformIdentity;
  view.bounds = CGRectMake(0, 0, frame.size.width, frame.size.height);
  view.center = CGPointMake(CGRectGetMidX(frame), CGRectGetMidY(frame));
  if ([view isKindOfClass:UIButton.class])
    view.layer.cornerRadius = MIN(frame.size.width, frame.size.height) * 0.46;
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
  for (NSString* key in @[@"dpad.up", @"dpad.down", @"dpad.left", @"dpad.right"])
    [self placeView:_buttons[key] frame:frames[key].CGRectValue];
  NSMutableArray<NeoTouchElement*>* elements = [NSMutableArray array];
  for (NSString* identifier in _order) {
    UIView* view = [self controlForIdentifier:identifier];
    [self placeView:view frame:frames[identifier].CGRectValue];
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
  if (!key || [key isEqualToString:NeoTouchLayoutKeyPlayStation3]) [self reloadFromStore];
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

- (void)touchButtonDown:(UIButton*)sender {
  sender.backgroundColor = [UIColor colorWithWhite:1 alpha:0.34];
  if (self.buttonChanged) self.buttonChanged((uint64_t)sender.tag, YES);
}

- (void)touchButtonUp:(UIButton*)sender {
  sender.backgroundColor = [UIColor colorWithWhite:0.06 alpha:0.38];
  if (self.buttonChanged) self.buttonChanged((uint64_t)sender.tag, NO);
}

- (void)releaseAllInput {
  for (UIButton* button in _buttons.allValues) {
    const BOOL held = button.isTracking || button.isHighlighted;
    if (held) [button cancelTrackingWithEvent:nil];
    button.highlighted = NO;
    button.backgroundColor = [UIColor colorWithWhite:0.06 alpha:0.38];
    if (self.buttonChanged) self.buttonChanged((uint64_t)button.tag, NO);
  }
  [_leftStick endTracking];
  [_rightStick endTracking];
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

void RPCS3TouchControlsRegisterPreview(void) {
  [NeoTouchLayoutRegistry registerPreviewFactory:^UIView<NeoTouchLayoutEditorHost>*(NSString* key, NSString* locale) {
    RPCS3TouchControlsView* preview = [[RPCS3TouchControlsView alloc] initWithLocale:locale];
    // A preview never receives a touch and has no session to send input to.
    preview.userInteractionEnabled = NO;
    return preview;
  } forLayoutKeys:@[NeoTouchLayoutKeyPlayStation3]];
}

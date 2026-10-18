// SPDX-License-Identifier: GPL-3.0-or-later
#import "DOLTouchLayout.h"
#import <dolphin_internal_bridge/dolphin_internal_bridge-Swift.h>
#include <cmath>

@implementation DOLTouchLayout {
  NSString* _locale;
  // Effective stored layout of _storedKey (layout key, orientation, game).
  NeoTouchLayout* _stored;
  NSString* _storedKey;
  // While the editor or its preview drives the controls.
  BOOL _overriding;
  BOOL _ghostHidden;
  NeoTouchLayout* _overrideLayout;
  NSArray<NeoTouchElement*>* _controls;
  NeoTouchElement* _shake;
  BOOL _hasLaidOut;
  // The nibs place the controls with Auto Layout, which can settle a control
  // after the overlay's layout pass (intrinsic sizes, safe area). A placement
  // check on the next turn of the run loop lays the overlay out again when a
  // control moved since it was measured, a bounded number of times in a row.
  BOOL _checkScheduled;
  NSUInteger _corrections;
}

- (instancetype)initWithOverlay:(DOLTouchOverlay*)overlay locale:(NSString*)locale {
  self = [super init];
  if (self) {
    _overlay = overlay;
    _locale = NeoTouchLayoutCanonicalLocale(locale);
    _orientation = NeoTouchLayoutOrientationLandscape;
    _controls = @[];
    __weak DOLTouchLayout* weakSelf = self;
    overlay.layoutPassHandler = ^(BOOL shakePhase) { [weakSelf layoutPass:shakePhase]; };
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(storeChanged:)
                                               name:NeoTouchLayoutStoreDidChangeNotification object:nil];
  }
  return self;
}

- (void)dealloc {
  [NSNotificationCenter.defaultCenter removeObserver:self];
}

- (NSString*)layoutKey {
  return self.overlay.touchLayoutKey ?: NeoTouchLayoutKeyGameCube;
}

- (BOOL)editing {
  return _overriding;
}

- (void)setGameKey:(NSString*)gameKey {
  _gameKey = [NeoTouchLayoutGameKey(gameKey) copy];
  [self reloadFromStore];
}

- (void)storeChanged:(NSNotification*)notification {
  NSString* key = notification.userInfo[@"key"];
  if (!key || [key isEqualToString:self.layoutKey]) [self reloadFromStore];
}

- (void)reloadFromStore {
  _stored = nil;
  _storedKey = nil;
  DOLTouchOverlay* overlay = self.overlay;
  [overlay setNeedsLayout];
  [overlay layoutIfNeeded];
}

- (NeoTouchLayout*)currentLayout {
  if (_overriding) return _overrideLayout;
  NSString* cacheKey = [NSString stringWithFormat:@"%@|%@|%@", self.layoutKey, _orientation, _gameKey ?: @""];
  if (!_stored || ![_storedKey isEqualToString:cacheKey]) {
    _stored = [NeoTouchLayoutStore.sharedStore effectiveLayoutForKey:self.layoutKey orientation:_orientation
                                                                game:_gameKey gameSpecific:NULL];
    _storedKey = cacheKey;
  }
  return _stored;
}

- (NeoTouchElement*)elementForControl:(UIView*)control {
  DOLTouchOverlay* overlay = self.overlay;
  NSString* name = [overlay touchLayoutName:control];
  if ([name hasPrefix:@"@"]) name = NeoTouchLayoutText([name substringFromIndex:1], _locale);
  NeoTouchElement* element =
      [[NeoTouchElement alloc] initWithIdentifier:[overlay touchLayoutIdentifier:control]
                                             name:name
                                             kind:(NeoTouchElementKind)[overlay touchLayoutKind:control]
                                             view:control];
  [element captureDefaultGeometryInCanvas:overlay];
  return element;
}

- (void)layoutPass:(BOOL)shakePhase {
  DOLTouchOverlay* overlay = self.overlay;
  if (!overlay || overlay.bounds.size.width <= 0 || overlay.bounds.size.height <= 0) return;
  if (!shakePhase) {
    NSString* orientation = NeoTouchLayoutOrientationForSize(overlay.bounds.size);
    if (![orientation isEqualToString:_orientation]) {
      _orientation = orientation;
      _stored = nil;
      if (_hasLaidOut) {
        // A finger held across a rotation must not stay pressed.
        [overlay cancelTouchInteractions];
        if (self.orientationChanged) self.orientationChanged();
      }
    }
    _hasLaidOut = YES;
    NSMutableArray* controls = [NSMutableArray array];
    for (UIView* control in [overlay touchLayoutControls]) [controls addObject:[self elementForControl:control]];
    _controls = controls;
    [NeoTouchLayoutApplier applyLayout:[self currentLayout] elements:controls canvas:overlay editing:_ghostHidden];
    [self schedulePlacementCheck];
    return;
  }
  UIView* shake = overlay.touchLayoutShakeControl;
  if (!shake) {
    _shake = nil;
    return;
  }
  NeoTouchLayout* layout = [self currentLayout];
  const BOOL hidden = [layout stateForIdentifier:@"shake"].hidden;
  if (overlay.shakeHiddenByLayout != hidden) overlay.shakeHiddenByLayout = hidden;
  // The automatic placement just computed (identity transform) is its stock place.
  _shake = [self elementForControl:shake];
  [NeoTouchLayoutApplier applyLayout:layout elements:@[_shake] canvas:overlay editing:_ghostHidden];
}

- (void)schedulePlacementCheck {
  if (_checkScheduled) return;
  _checkScheduled = YES;
  __weak DOLTouchLayout* weakSelf = self;
  dispatch_async(dispatch_get_main_queue(), ^{ [weakSelf checkPlacement]; });
}

- (void)checkPlacement {
  _checkScheduled = NO;
  DOLTouchOverlay* overlay = self.overlay;
  if (!overlay) return;
  BOOL moved = NO;
  for (NeoTouchElement* element in _controls) {
    UIView* view = element.view;
    if (!view) continue;
    UIView* parent = view.superview ?: overlay;
    const CGPoint center = parent == overlay ? view.center : [parent convertPoint:view.center toView:overlay];
    if (fabs(center.x - element.defaultCenter.x) > 0.5 || fabs(center.y - element.defaultCenter.y) > 0.5 ||
        fabs(view.bounds.size.width - element.defaultSize.width) > 0.5 ||
        fabs(view.bounds.size.height - element.defaultSize.height) > 0.5) {
      moved = YES;
      break;
    }
  }
  if (!moved) {
    _corrections = 0;
    return;
  }
  if (++_corrections > 3) return;
  [overlay setNeedsLayout];
  [overlay layoutIfNeeded];
  [NSNotificationCenter.defaultCenter postNotificationName:NeoTouchLayoutHostDidRelayoutNotification object:overlay];
}

- (void)endEditingOverride {
  _overriding = NO;
  _ghostHidden = NO;
  _overrideLayout = nil;
  self.overlay.touchLayoutEditing = NO;
  [self reloadFromStore];
}

#pragma mark NeoTouchLayoutEditorHost

- (UIView*)touchLayoutCanvas {
  return self.overlay;
}

- (NSArray<NeoTouchElement*>*)touchLayoutElements {
  return _shake ? [_controls arrayByAddingObject:_shake] : _controls;
}

- (void)touchLayoutApplyLayout:(NeoTouchLayout*)layout editing:(BOOL)editing {
  _overriding = YES;
  _ghostHidden = editing;
  _overrideLayout = [layout copy] ?: [NeoTouchLayout new];
  DOLTouchOverlay* overlay = self.overlay;
  overlay.touchLayoutEditing = editing;
  [overlay setNeedsLayout];
  [overlay layoutIfNeeded];
}

@end

@implementation DOLTouchLayoutPreviewView {
  DOLTouchOverlay* _overlay;
  DOLTouchLayout* _layout;
}

- (instancetype)initWithLayoutKey:(NSString*)layoutKey locale:(NSString*)locale {
  self = [super initWithFrame:UIScreen.mainScreen.bounds];
  if (self) {
    self.backgroundColor = UIColor.clearColor;
    _overlay = [[DOLTouchOverlay alloc] initWithWii:![layoutKey isEqualToString:NeoTouchLayoutKeyGameCube]];
    if ([layoutKey isEqualToString:NeoTouchLayoutKeyWiiClassic]) [_overlay updateExtension:@"Classic"];
    _overlay.frame = self.bounds;
    _overlay.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    // A preview never receives a touch and never runs a session.
    _overlay.userInteractionEnabled = NO;
    _overlay.accessibilityIdentifier = @"dolphin.touchLayout.preview";
    [self addSubview:_overlay];
    _layout = [[DOLTouchLayout alloc] initWithOverlay:_overlay locale:locale];
  }
  return self;
}

- (UIView*)touchLayoutCanvas {
  return [_layout touchLayoutCanvas];
}

- (NSArray<NeoTouchElement*>*)touchLayoutElements {
  return [_layout touchLayoutElements];
}

- (void)touchLayoutApplyLayout:(NeoTouchLayout*)layout editing:(BOOL)editing {
  [_layout touchLayoutApplyLayout:layout editing:editing];
}

- (UIInterfaceOrientationMask)touchLayoutSupportedInterfaceOrientations {
  // DOLDolphinViewController runs the GameCube and Wii sessions in landscape.
  return UIInterfaceOrientationMaskLandscape;
}

@end

void DOLTouchLayoutRegisterPreviews(void) {
  [NeoTouchLayoutRegistry registerPreviewFactory:^UIView<NeoTouchLayoutEditorHost>*(NSString* key, NSString* locale) {
    return [[DOLTouchLayoutPreviewView alloc] initWithLayoutKey:key locale:locale];
  } forLayoutKeys:@[NeoTouchLayoutKeyGameCube, NeoTouchLayoutKeyWii, NeoTouchLayoutKeyWiiClassic]];
}

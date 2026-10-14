#import "LibretroTouchOverlay.h"

#import <QuartzCore/QuartzCore.h>

#import "LibretroInputState.h"

#include <math.h>
#include <string.h>

static double LibretroOverlayNumber(id value, double fallback) {
  if (![value isKindOfClass:[NSNumber class]]) return fallback;
  double number = [(NSNumber *)value doubleValue];
  return isfinite(number) ? number : fallback;
}

static BOOL LibretroOverlayContains(LibretroRect rect, CGPoint point) {
  if (!(rect.w > 0) || !(rect.h > 0)) return NO;
  return point.x >= rect.x && point.y >= rect.y && point.x <= rect.x + rect.w && point.y <= rect.y + rect.h;
}

/// Key of a finger in the tracker: the UITouch object, which UIKit keeps
/// for the whole touch.
static NSValue *LibretroOverlayKey(UITouch *touch) {
  return [NSValue valueWithNonretainedObject:touch];
}

@implementation LibretroTouchOverlay {
  LibretroInputState *_input;
  LibretroTouchTracker *_tracker;
  LibretroSkinLayoutResult *_layout;
  NSSet<NSNumber *> *_activeActions;
  NSSet<NSString *> *_pressedItems;
  NSDictionary<NSString *, NSNumber *> *_dpadDirections;
  NSDictionary<NSString *, NSValue *> *_stickVectors;
  BOOL _pointerPressed;
  int16_t _pointerX;
  int16_t _pointerY;
  // Layout editing.
  NSMutableArray<UITouch *> *_editTouches;
  NSString *_selectedItem;
  NSString *_editItem;
  LibretroSkinItem *_editBaseItem;
  LibretroSkinRepresentation *_editRepresentation;
  double _editStartDX;
  double _editStartDY;
  double _editStartScale;
  BOOL _dragging;
  CGPoint _dragStart;
  BOOL _pinching;
  double _pinchStartDistance;
  NSMutableDictionary<NSString *, LibretroSkinItem *> *_editBases;
  NSArray<LibretroSkinItem *> *_editObstacleItems;
  NSArray<LibretroSkinScreen *> *_editScreens;
  CGSize _editCacheSize;
}

- (instancetype)initWithInput:(LibretroInputState *)input {
  self = [super initWithFrame:CGRectZero];
  if (self) {
    _input = input;
    _tracker = [LibretroTouchTracker new];
    _activeActions = [NSSet set];
    _pressedItems = [NSSet set];
    _stickVectors = @{};
    _editTouches = [NSMutableArray array];
    _editBases = [NSMutableDictionary dictionary];
    self.multipleTouchEnabled = YES;
    self.backgroundColor = UIColor.clearColor;
    self.opaque = NO;
    // The game itself cannot be played with VoiceOver: the laid-out items
    // are not accessibility elements, only the overlay is identified.
    self.accessibilityIdentifier = @"libretro-touch-overlay";
  }
  return self;
}

#pragma mark - Configuration

- (void)applyLayout:(LibretroSkinLayoutResult *)layout
           inputMap:(LibretroInputMap *)inputMap
         touchRemap:(NSDictionary<NSString *, NSArray<NSString *> *> *)touchRemap {
  _layout = layout;
  [_tracker applyLayout:layout inputMap:inputMap touchRemap:touchRemap];
  [self publish];
}

- (void)setControlsDisabled:(BOOL)controlsDisabled {
  if (_controlsDisabled == controlsDisabled) return;
  _controlsDisabled = controlsDisabled;
  _tracker.controlsDisabled = controlsDisabled;
  [self publish];
}

- (void)setEditing:(BOOL)editing {
  if (_editing == editing) return;
  _editing = editing;
  // Game input stops while the layout is edited, and editing gestures and
  // the selection end with the mode.
  [_tracker endAllTouches];
  [self resetEditingGestures];
  _selectedItem = nil;
  [_editBases removeAllObjects];
  _editObstacleItems = nil;
  _editScreens = nil;
  _editCacheSize = CGSizeZero;
  [self publish];
}

- (void)clearEditSelection {
  _selectedItem = nil;
  [self resetEditingGestures];
  // Original frames are taken again from the next layout (the overrides
  // the caller sets after a Reset).
  [_editBases removeAllObjects];
}

- (void)setEditOverrides:(NSDictionary<NSString *, NSDictionary *> *)editOverrides {
  _editOverrides = [editOverrides isKindOfClass:[NSDictionary class]] ? [editOverrides copy] : nil;
}

- (NSArray<NSValue *> *)touchScreenMappings {
  return _tracker.touchScreenMappings;
}

- (void)setTouchScreenMappings:(NSArray<NSValue *> *)touchScreenMappings {
  _tracker.touchScreenMappings = touchScreenMappings;
  // A held stylus may have followed or left the touch screen.
  if (_tracker.touchCount > 0) [self publish];
}

- (BOOL)recordsContacts {
  return _tracker.recordsContacts;
}

- (void)setRecordsContacts:(BOOL)recordsContacts {
  _tracker.recordsContacts = recordsContacts;
  [self publish];
}

#pragma mark - Publishing

/// Sends what every finger produces to the input state (RetroPad of port
/// 0, pointer), then reports highlighted items, knobs and frontend action
/// edges. Only items that really send an input are highlighted: a button
/// whose inputs this console cannot use stays dark, so a lit button always
/// means a command was sent.
- (void)publish {
  LibretroTouchResolution *resolution = nil;
  if (self.editing) {
    // No game input while the layout is edited.
    [_tracker endAllTouches];
  }
  resolution = [_tracker resolve];
  [_input setTouchInput:resolution.coreInput];
  if (resolution.pointerPressed != _pointerPressed || resolution.pointerX != _pointerX ||
      resolution.pointerY != _pointerY) {
    _pointerPressed = resolution.pointerPressed;
    _pointerX = resolution.pointerX;
    _pointerY = resolution.pointerY;
    [_input setPointerX:_pointerX y:_pointerY pressed:_pointerPressed];
  }

  NSSet<NSString *> *pressed = resolution.pressedItems;
  if (![pressed isEqualToSet:_pressedItems]) {
    _pressedItems = [pressed copy];
    if (self.pressedItemsChanged != nil) self.pressedItemsChanged(_pressedItems);
  }
  NSMutableDictionary<NSString *, NSValue *> *vectors = [NSMutableDictionary dictionary];
  [resolution.stickVectors enumerateKeysAndObjectsUsingBlock:^(NSString *identifier, NSValue *value, BOOL *stop) {
    LibretroSize vector = {0, 0};
    [value getValue:&vector size:sizeof(vector)];
    vectors[identifier] = [NSValue valueWithCGPoint:CGPointMake(vector.w, vector.h)];
  }];
  if (![vectors isEqualToDictionary:_stickVectors]) {
    _stickVectors = [vectors copy];
    if (self.stickVectorsChanged != nil) self.stickVectorsChanged(_stickVectors);
  }
  if (![resolution.dpadDirections isEqualToDictionary:_dpadDirections]) {
    _dpadDirections = resolution.dpadDirections;
    if (self.dpadDirectionsChanged != nil) self.dpadDirectionsChanged(_dpadDirections);
  }
  if (self.resolutionChanged != nil) self.resolutionChanged(resolution);

  NSSet<NSNumber *> *previous = _activeActions;
  NSSet<NSNumber *> *current = [resolution.actions copy];
  _activeActions = current;
  void (^handler)(LibretroFrontendAction, BOOL) = self.actionHandler;
  if (handler == nil) return;
  // A handler may release every touch (the menu opens): each edge is
  // checked against the latest state before it is reported.
  for (NSNumber *action in previous) {
    if ([current containsObject:action] || [_activeActions containsObject:action]) continue;
    handler((LibretroFrontendAction)action.integerValue, NO);
  }
  for (NSNumber *action in current) {
    if ([previous containsObject:action] || ![_activeActions containsObject:action]) continue;
    handler((LibretroFrontendAction)action.integerValue, YES);
  }
}

#pragma mark - Game touches

- (void)touchesBegan:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event {
  if (self.editing) {
    [self editTouchesBegan:touches];
    return;
  }
  CFTimeInterval now = CACurrentMediaTime();
  for (UITouch *touch in touches) {
    CGPoint point = [touch locationInView:self];
    [_tracker beginTouch:LibretroOverlayKey(touch) x:point.x y:point.y];
    // How long iOS held the touch before delivering it (screen-edge
    // gestures delay touches near the edges): measured, not guessed.
    if (self.touchDelivered != nil) self.touchDelivered(point, MAX(0.0, now - touch.timestamp));
  }
  [self publish];
}

- (void)touchesMoved:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event {
  if (self.editing) {
    [self editTouchesMoved];
    return;
  }
  for (UITouch *touch in touches) {
    CGPoint point = [touch locationInView:self];
    [_tracker moveTouch:LibretroOverlayKey(touch) x:point.x y:point.y];
  }
  [self publish];
}

- (void)endTouches:(NSSet<UITouch *> *)touches {
  if (self.editing) {
    [self editTouchesEnded:touches];
    return;
  }
  for (UITouch *touch in touches) [_tracker endTouch:LibretroOverlayKey(touch)];
  [self publish];
}

- (void)touchesEnded:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event {
  [self endTouches:touches];
}

- (void)touchesCancelled:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event {
  [self endTouches:touches];
}

- (void)releaseAllTouches {
  [_tracker endAllTouches];
  [self resetEditingGestures];
  [_input reset];
  [self publish];
}

- (NSSet<NSString *> *)deadItemIdentifiers {
  return [_tracker deadItemIdentifiers];
}

#pragma mark - Layout editing

- (void)resetEditingGestures {
  [_editTouches removeAllObjects];
  _dragging = NO;
  _pinching = NO;
  _editItem = nil;
  _editBaseItem = nil;
  _editRepresentation = nil;
}

- (LibretroLaidOutItem *)laidOutItemWithIdentifier:(NSString *)identifier {
  if (identifier.length == 0) return nil;
  for (LibretroLaidOutItem *laidOut in _layout.items) {
    if ([laidOut.item.identifier isEqualToString:identifier]) return laidOut;
  }
  return nil;
}

/// Topmost movable item under `point` (its frame first, then its touch area).
- (LibretroLaidOutItem *)movableItemAtPoint:(CGPoint)point {
  NSArray<LibretroLaidOutItem *> *items = _layout.items ?: @[];
  for (int pass = 0; pass < 2; pass++) {
    for (LibretroLaidOutItem *laidOut in items.reverseObjectEnumerator) {
      LibretroSkinItem *item = laidOut.item;
      if (!item.movable || item.kind == LibretroSkinItemKindTouchScreen || item.identifier.length == 0) continue;
      if (LibretroOverlayContains(pass == 0 ? laidOut.frame : laidOut.hitFrame, point)) return laidOut;
    }
  }
  return nil;
}

- (void)selectItem:(NSString *)identifier {
  if ((identifier == nil && _selectedItem == nil) || [identifier isEqualToString:_selectedItem]) return;
  _selectedItem = [identifier copy];
  if (self.editSelectionChanged != nil) self.editSelectionChanged(_selectedItem);
}

/// Overrides are clamped by +[LibretroSkinLayout clampOverride:...] against
/// the item's original place. The original frame is the laid-out frame
/// with the stored override undone, placed in a generated representation
/// of the overlay size that also holds the touch screens (screens and
/// touch-screen items), the obstacles a moved control must avoid.
/// Original frames and obstacles do not move while editing: they are
/// computed once per item and overlay size, so a re-layout that arrives
/// after an editChanged report cannot skew them.
- (BOOL)prepareEditingForItem:(NSString *)identifier {
  if (identifier.length == 0) return NO;
  CGSize size = self.bounds.size;
  if (size.width < 1 || size.height < 1) return NO;
  if (!CGSizeEqualToSize(size, _editCacheSize)) {
    [_editBases removeAllObjects];
    _editObstacleItems = nil;
    _editScreens = nil;
    _editCacheSize = size;
  }
  NSDictionary *stored = _editOverrides[identifier];
  if (![stored isKindOfClass:[NSDictionary class]]) stored = nil;
  double dx = LibretroOverlayNumber(stored[@"dx"], 0);
  double dy = LibretroOverlayNumber(stored[@"dy"], 0);
  double scale = MIN(MAX(LibretroOverlayNumber(stored[@"scale"], 1), 0.5), 2.0);

  LibretroSkinItem *base = _editBases[identifier];
  if (base == nil) {
    LibretroLaidOutItem *target = [self laidOutItemWithIdentifier:identifier];
    if (target == nil || !target.item.movable) return NO;
    LibretroRect frame = target.frame;
    double width = frame.w / scale, height = frame.h / scale;
    double offsetX = dx * size.width, offsetY = dy * size.height;
    double centerX = frame.x + frame.w / 2 - offsetX;
    double centerY = frame.y + frame.h / 2 - offsetY;
    base = [target.item copy];
    base.frame = LibretroRectMake(centerX - width / 2, centerY - height / 2, width, height);
    // The real touch area, override undone the same way (it moves and
    // scales around the frame centre): the clamp keeps it off the touch
    // screen too.
    LibretroRect hit = target.hitFrame;
    base.hitFrame = hit.w > 0 && hit.h > 0 ? LibretroRectMake(centerX + (hit.x - offsetX - centerX) / scale,
                                                              centerY + (hit.y - offsetY - centerY) / scale,
                                                              hit.w / scale, hit.h / scale)
                                           : base.frame;
    base.assetFrame = base.frame;
    _editBases[identifier] = base;
  }

  if (_editObstacleItems == nil || _editScreens == nil) {
    NSMutableArray<LibretroSkinItem *> *obstacles = [NSMutableArray array];
    for (LibretroLaidOutItem *laidOut in _layout.items) {
      if (laidOut.item.kind != LibretroSkinItemKindTouchScreen) continue;
      LibretroSkinItem *touch = [laidOut.item copy];
      touch.frame = laidOut.frame;
      touch.hitFrame = laidOut.hitFrame;
      touch.assetFrame = laidOut.frame;
      [obstacles addObject:touch];
    }
    NSMutableArray<LibretroSkinScreen *> *screens = [NSMutableArray array];
    for (LibretroLaidOutScreen *laidOut in _layout.screens) {
      LibretroSkinScreen *screen = [LibretroSkinScreen new];
      screen.outputFrame = laidOut.container;
      screen.hasOutputFrame = YES;
      screen.source = laidOut.source;
      screen.role = laidOut.role ?: @"full";
      screen.touchScreen = laidOut.touchScreen;
      [screens addObject:screen];
    }
    _editObstacleItems = obstacles;
    _editScreens = screens;
  }
  NSMutableArray<LibretroSkinItem *> *items = [NSMutableArray arrayWithObject:base];
  [items addObjectsFromArray:_editObstacleItems];
  NSArray<LibretroSkinScreen *> *screens = _editScreens;
  LibretroSkinRepresentation *representation = [LibretroSkinRepresentation new];
  representation.generated = YES;
  representation.mappingSize = (LibretroSize){size.width, size.height};
  representation.orientation =
      size.width > size.height ? LibretroSkinOrientationLandscape : LibretroSkinOrientationPortrait;
  representation.items = items;
  representation.screens = screens;

  _editItem = [identifier copy];
  _editBaseItem = base;
  _editRepresentation = representation;
  _editStartDX = dx;
  _editStartDY = dy;
  _editStartScale = scale;
  return YES;
}

- (void)reportEditDX:(double)dx dy:(double)dy scale:(double)scale {
  if (_editItem == nil || _editBaseItem == nil || _editRepresentation == nil) return;
  CGSize size = self.bounds.size;
  UIEdgeInsets safe = self.safeAreaInsets;
  LibretroInsets insets = {safe.top, safe.left, safe.bottom, safe.right};
  NSDictionary<NSString *, NSNumber *> *proposed = @{@"dx" : @(dx), @"dy" : @(dy), @"scale" : @(scale)};
  NSMutableDictionary<NSString *, NSDictionary *> *overrides =
      _editOverrides != nil ? [_editOverrides mutableCopy] : [NSMutableDictionary dictionary];
  NSDictionary *previous = overrides[_editItem];
  if (![previous isKindOfClass:[NSDictionary class]]) previous = nil;
  BOOL fitted = NO;
  NSDictionary<NSString *, NSNumber *> *clamped =
      [LibretroSkinLayout clampOverride:proposed
                               previous:previous
                                forItem:_editBaseItem
                         representation:_editRepresentation
                               viewSize:(LibretroSize){size.width, size.height}
                             safeInsets:insets
                                 fitted:&fitted];
  // Nowhere to put it (a pinch too large for the room beside the touch
  // screen): the item keeps its last valid place and size.
  if (!fitted) return;
  if ([previous isEqual:clamped]) return;
  overrides[_editItem] = clamped;
  _editOverrides = [overrides copy];
  if (self.editChanged != nil) self.editChanged(_editItem, clamped);
}

- (double)pinchDistance {
  if (_editTouches.count < 2) return 0;
  CGPoint first = [_editTouches[0] locationInView:self];
  CGPoint second = [_editTouches[1] locationInView:self];
  return hypot(first.x - second.x, first.y - second.y);
}

- (void)editTouchesBegan:(NSSet<UITouch *> *)touches {
  for (UITouch *touch in touches) {
    if (![_editTouches containsObject:touch]) [_editTouches addObject:touch];
  }
  if (_editTouches.count == 1) {
    // One finger: select and drag the movable item under it.
    CGPoint point = [_editTouches[0] locationInView:self];
    LibretroLaidOutItem *laidOut = [self movableItemAtPoint:point];
    _dragging = NO;
    _pinching = NO;
    if (laidOut != nil) {
      [self selectItem:laidOut.item.identifier];
      if ([self prepareEditingForItem:laidOut.item.identifier]) {
        _dragging = YES;
        _dragStart = point;
      }
    }
  } else if (!_pinching) {
    // Two fingers anywhere: pinch the selected item (a 44-point button
    // rarely holds two fingers).
    _dragging = NO;
    double distance = [self pinchDistance];
    if (_selectedItem != nil && distance > 1 && [self prepareEditingForItem:_selectedItem]) {
      _pinching = YES;
      _pinchStartDistance = distance;
    }
  }
}

- (void)editTouchesMoved {
  CGSize size = self.bounds.size;
  if (size.width < 1 || size.height < 1) return;
  if (_pinching) {
    double distance = [self pinchDistance];
    if (distance <= 1 || _pinchStartDistance <= 1) return;
    double scale = MIN(MAX(_editStartScale * distance / _pinchStartDistance, 0.5), 2.0);
    [self reportEditDX:_editStartDX dy:_editStartDY scale:scale];
  } else if (_dragging && _editTouches.count == 1) {
    CGPoint point = [_editTouches[0] locationInView:self];
    double dx = _editStartDX + (point.x - _dragStart.x) / size.width;
    double dy = _editStartDY + (point.y - _dragStart.y) / size.height;
    [self reportEditDX:dx dy:dy scale:_editStartScale];
  }
}

- (void)editTouchesEnded:(NSSet<UITouch *> *)touches {
  for (UITouch *touch in touches) [_editTouches removeObject:touch];
  if (_editTouches.count < 2) _pinching = NO;
  // After a pinch the remaining finger does not start a drag; lifting every
  // finger ends the gesture.
  _dragging = NO;
  if (_editTouches.count == 0) {
    _editItem = nil;
    _editBaseItem = nil;
    _editRepresentation = nil;
  }
}

@end

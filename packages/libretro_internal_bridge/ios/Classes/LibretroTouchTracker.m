#import "LibretroTouchTracker.h"

#include <math.h>
#include <string.h>

@interface LibretroTouchContact ()
@property(nonatomic, readwrite) NSUInteger serial;
@property(nonatomic, readwrite) LibretroTouchMode mode;
@property(nonatomic, readwrite) double x;
@property(nonatomic, readwrite) double y;
@property(nonatomic, readwrite, copy) NSArray<NSString *> *itemIdentifiers;
@property(nonatomic, readwrite, copy) NSArray<NSString *> *sentInputs;
@property(nonatomic, readwrite, copy) NSArray<NSString *> *inertInputs;
@end

@implementation LibretroTouchContact
@end

@interface LibretroTouchResolution ()
@property(nonatomic, readwrite) LibretroCoreInput coreInput;
@property(nonatomic, readwrite) BOOL pointerPressed;
@property(nonatomic, readwrite) int16_t pointerX;
@property(nonatomic, readwrite) int16_t pointerY;
@property(nonatomic, readwrite, copy) NSSet<NSString *> *pressedItems;
@property(nonatomic, readwrite, copy) NSSet<NSString *> *inertItems;
@property(nonatomic, readwrite, copy) NSSet<NSNumber *> *actions;
@property(nonatomic, readwrite, copy) NSDictionary<NSString *, NSValue *> *stickVectors;
@property(nonatomic, readwrite, copy) NSArray<LibretroTouchContact *> *contacts;
@end

@implementation LibretroTouchResolution
@end

@interface LibretroTouchTrack : NSObject
@property(nonatomic, assign) NSUInteger serial;
@property(nonatomic, assign) LibretroTouchMode mode;
@property(nonatomic, copy) NSArray<LibretroLaidOutItem *> *items;
@property(nonatomic, strong, nullable) LibretroLaidOutItem *bound;
@property(nonatomic, assign) double x;
@property(nonatomic, assign) double y;
@property(nonatomic, assign) LibretroScreenMapping mapping;
@property(nonatomic, assign) int16_t pointerX;
@property(nonatomic, assign) int16_t pointerY;
@end

@implementation LibretroTouchTrack

- (instancetype)init {
  self = [super init];
  if (self) {
    _items = @[];
  }
  return self;
}

@end

/// What one finger sends while it is resolved.
typedef struct {
  LibretroCoreInput *state;
  __unsafe_unretained NSMutableSet<NSNumber *> *actions;
  __unsafe_unretained NSMutableArray<NSString *> *sent;   // nil unless contacts are recorded
  __unsafe_unretained NSMutableArray<NSString *> *inert;  // nil unless contacts are recorded
} LibretroTouchSink;

static BOOL TrackerContains(LibretroRect rect, double x, double y) {
  if (!(rect.w > 0) || !(rect.h > 0)) return NO;
  return x >= rect.x && y >= rect.y && x <= rect.x + rect.w && y <= rect.y + rect.h;
}

static double TrackerDistance(LibretroRect rect, double x, double y) {
  double dx = MAX(MAX(rect.x - x, 0.0), x - (rect.x + rect.w));
  double dy = MAX(MAX(rect.y - y, 0.0), y - (rect.y + rect.h));
  return hypot(dx, dy);
}

/// Items a sliding finger may press: buttons and D-pads (sticks and the
/// touch screen are only taken when a finger lands on them).
static NSArray<LibretroLaidOutItem *> *TrackerSlidable(NSArray<LibretroLaidOutItem *> *hits) {
  NSMutableArray<LibretroLaidOutItem *> *items = [NSMutableArray array];
  for (LibretroLaidOutItem *laidOut in hits) {
    LibretroSkinItemKind kind = laidOut.item.kind;
    if (kind == LibretroSkinItemKindButton || kind == LibretroSkinItemKindDPad) [items addObject:laidOut];
  }
  return items;
}

@implementation LibretroTouchTracker {
  LibretroSkinLayoutResult *_layout;
  LibretroInputMap *_inputMap;
  NSDictionary<NSString *, NSArray<NSString *> *> *_touchRemap;
  NSMutableDictionary<id<NSCopying>, LibretroTouchTrack *> *_tracks;
  NSUInteger _nextSerial;
  int16_t _lastPointerX;
  int16_t _lastPointerY;
}

- (instancetype)init {
  self = [super init];
  if (self) {
    _inputMap = [LibretroInputMap mapForConsole:@"nes"];
    _tracks = [NSMutableDictionary dictionary];
    _touchScreenMappings = @[];
  }
  return self;
}

#pragma mark - Configuration

- (void)applyLayout:(LibretroSkinLayoutResult *)layout
           inputMap:(LibretroInputMap *)inputMap
         touchRemap:(NSDictionary<NSString *, NSArray<NSString *> *> *)touchRemap {
  _layout = layout;
  if ([inputMap isKindOfClass:[LibretroInputMap class]]) _inputMap = inputMap;
  _touchRemap = [touchRemap isKindOfClass:[NSDictionary class]] ? [touchRemap copy] : nil;
  // Fingers already down follow their items to the new places.
  NSMutableDictionary<NSString *, LibretroLaidOutItem *> *byIdentifier = [NSMutableDictionary dictionary];
  for (LibretroLaidOutItem *laidOut in layout.items) {
    NSString *identifier = laidOut.item.identifier;
    if (identifier.length > 0 && byIdentifier[identifier] == nil) byIdentifier[identifier] = laidOut;
  }
  for (LibretroTouchTrack *track in _tracks.allValues) {
    if (track.mode == LibretroTouchModeDPad || track.mode == LibretroTouchModeStick) {
      LibretroLaidOutItem *replacement = byIdentifier[track.bound.item.identifier ?: @""];
      track.bound = replacement;
      if (replacement == nil) track.mode = LibretroTouchModeIgnored;
    } else if (track.mode == LibretroTouchModeFree) {
      NSMutableArray<LibretroLaidOutItem *> *items = [NSMutableArray array];
      for (LibretroLaidOutItem *laidOut in track.items) {
        LibretroLaidOutItem *replacement = byIdentifier[laidOut.item.identifier ?: @""];
        if (replacement != nil) [items addObject:replacement];
      }
      track.items = items;
    }
  }
  // A held stylus follows the touch screen to its new place (or is
  // released); with published mappings this waits for the next ones.
  [self reresolvePointerTracks];
}

- (void)setTouchScreenMappings:(NSArray<NSValue *> *)touchScreenMappings {
  NSArray<NSValue *> *mappings = [touchScreenMappings isKindOfClass:[NSArray class]] ? [touchScreenMappings copy] : @[];
  if (_touchScreenMappings != nil && [mappings isEqualToArray:_touchScreenMappings]) return;
  _touchScreenMappings = mappings;
  [self reresolvePointerTracks];
}

- (NSUInteger)touchCount {
  return _tracks.count;
}

#pragma mark - Inputs

- (NSArray<NSString *> *)inputsForItem:(LibretroSkinItem *)item {
  id remap = item.identifier.length > 0 ? _touchRemap[item.identifier] : nil;
  if ([remap isKindOfClass:[NSArray class]]) {
    NSMutableArray<NSString *> *inputs = [NSMutableArray array];
    for (id input in (NSArray *)remap) {
      [inputs addObject:[input isKindOfClass:[NSString class]] ? input : @""];
    }
    BOOL directional = item.kind == LibretroSkinItemKindDPad || item.kind == LibretroSkinItemKindThumbstick;
    // A D-pad or stick remap names its four directions; anything else keeps
    // the skin's inputs.
    if (!directional || inputs.count == 4) return inputs;
  }
  return item.inputs ?: @[];
}

/// YES when `input` has a target the core (or the frontend) receives for
/// this console: a supported, unblocked button, an analog axis or an
/// action. The touch screen is handled by the pointer, not by items.
- (BOOL)inputHasEffect:(NSString *)input {
  if (![input isKindOfClass:[NSString class]] || input.length == 0) return NO;
  LibretroInputTarget target = [_inputMap targetForInput:input];
  switch (target.kind) {
    case LibretroInputTargetButton:
    case LibretroInputTargetAnalog:
      return YES;
    case LibretroInputTargetAction:
      return target.action != LibretroFrontendActionNone;
    case LibretroInputTargetPointer:
    case LibretroInputTargetNone:
      return NO;
  }
  return NO;
}

/// Adds one logical input. Digital targets (buttons, actions) need at
/// least half a deflection; analog targets take the magnitude. Returns YES
/// when the input reached the state or the actions.
- (BOOL)applyInput:(NSString *)input magnitude:(double)magnitude sink:(LibretroTouchSink)sink {
  if (![self inputHasEffect:input]) {
    if (input.length > 0 && ![sink.inert containsObject:input]) [sink.inert addObject:input];
    return NO;
  }
  LibretroInputTarget target = [_inputMap targetForInput:input];
  BOOL applied = NO;
  switch (target.kind) {
    case LibretroInputTargetButton:
      if (magnitude >= 0.5) {
        [_inputMap applyInput:input magnitude:1.0 toState:sink.state];
        applied = YES;
      }
      break;
    case LibretroInputTargetAnalog:
      if (magnitude > 0.001) {
        [_inputMap applyInput:input magnitude:MIN(magnitude, 1.0) toState:sink.state];
        applied = YES;
      }
      break;
    case LibretroInputTargetAction:
      if (magnitude >= 0.5) {
        [sink.actions addObject:@(target.action)];
        applied = YES;
      }
      break;
    case LibretroInputTargetPointer:
    case LibretroInputTargetNone:
      break;
  }
  if (applied && sink.sent != nil && ![sink.sent containsObject:input]) [sink.sent addObject:input];
  return applied;
}

/// D-pad directions of the point on `laidOut`, mapped to its four inputs.
/// Returns YES when at least one direction reached the core (NO in the
/// dead zone or when no direction is supported).
- (BOOL)applyDPad:(LibretroLaidOutItem *)laidOut x:(double)x y:(double)y sink:(LibretroTouchSink)sink {
  LibretroDirection directions = LibretroDPadDirections(laidOut.frame, x, y);
  if (directions == 0) return NO;
  NSArray<NSString *> *inputs = [self inputsForItem:laidOut.item];
  const LibretroDirection bits[4] = {LibretroDirectionUp, LibretroDirectionDown, LibretroDirectionLeft,
                                     LibretroDirectionRight};
  BOOL sent = NO;
  for (NSUInteger index = 0; index < 4 && index < inputs.count; index++) {
    if ((directions & bits[index]) == 0) continue;
    if ([self applyInput:inputs[index] magnitude:1.0 sink:sink]) sent = YES;
  }
  return sent;
}

/// Stick deflection mapped to its up / down / left / right inputs with
/// their magnitudes (libretro y: positive downward). Returns YES when the
/// stick drives at least one supported input (centred or not), so a held
/// working stick stays highlighted.
- (BOOL)applyStick:(LibretroLaidOutItem *)laidOut x:(double)x y:(double)y sink:(LibretroTouchSink)sink {
  double stickX = 0, stickY = 0;
  LibretroStickVector(laidOut.frame, x, y, &stickX, &stickY);
  NSArray<NSString *> *inputs = [self inputsForItem:laidOut.item];
  if (inputs.count < 4) return NO;
  BOOL functional = NO;
  for (NSUInteger index = 0; index < 4; index++) {
    if ([self inputHasEffect:inputs[index]]) functional = YES;
  }
  if (stickY < 0) {
    [self applyInput:inputs[0] magnitude:-stickY sink:sink];
  } else if (stickY > 0) {
    [self applyInput:inputs[1] magnitude:stickY sink:sink];
  }
  if (stickX < 0) {
    [self applyInput:inputs[2] magnitude:-stickX sink:sink];
  } else if (stickX > 0) {
    [self applyInput:inputs[3] magnitude:stickX sink:sink];
  }
  return functional;
}

- (LibretroTouchResolution *)resolve {
  LibretroCoreInput state;
  memset(&state, 0, sizeof(state));
  NSMutableSet<NSNumber *> *actions = [NSMutableSet set];
  NSMutableSet<NSString *> *pressed = [NSMutableSet set];
  NSMutableSet<NSString *> *inert = [NSMutableSet set];
  NSMutableDictionary<NSString *, NSValue *> *vectors = [NSMutableDictionary dictionary];
  NSMutableArray<LibretroTouchContact *> *contacts = self.recordsContacts ? [NSMutableArray array] : nil;
  LibretroTouchTrack *pointer = nil;

  NSArray<LibretroTouchTrack *> *tracks =
      [_tracks.allValues sortedArrayUsingComparator:^NSComparisonResult(LibretroTouchTrack *a, LibretroTouchTrack *b) {
        if (a.serial == b.serial) return NSOrderedSame;
        return a.serial < b.serial ? NSOrderedAscending : NSOrderedDescending;
      }];
  BOOL controls = !self.controlsDisabled;
  for (LibretroTouchTrack *track in tracks) {
    NSMutableArray<NSString *> *sent = contacts != nil ? [NSMutableArray array] : nil;
    NSMutableArray<NSString *> *inertInputs = contacts != nil ? [NSMutableArray array] : nil;
    NSMutableArray<NSString *> *touched = contacts != nil ? [NSMutableArray array] : nil;
    LibretroTouchSink sink = {&state, actions, sent, inertInputs};
    double x = track.x, y = track.y;
    switch (track.mode) {
      case LibretroTouchModeFree:
        if (!controls) break;
        for (LibretroLaidOutItem *laidOut in track.items) {
          LibretroSkinItem *item = laidOut.item;
          NSString *identifier = item.identifier ?: @"";
          if (identifier.length > 0) [touched addObject:identifier];
          if (item.kind == LibretroSkinItemKindDPad) {
            if (LibretroDPadDirections(laidOut.frame, x, y) == 0) continue;  // dead zone
            BOOL sentAny = [self applyDPad:laidOut x:x y:y sink:sink];
            if (identifier.length > 0) [(sentAny ? pressed : inert) addObject:identifier];
          } else if (item.kind == LibretroSkinItemKindButton) {
            BOOL sentAny = NO;
            for (NSString *input in [self inputsForItem:item]) {
              if ([self applyInput:input magnitude:1.0 sink:sink]) sentAny = YES;
            }
            // The skin's names NeoStation could not use explain a dead button.
            if (!sentAny) [inertInputs addObjectsFromArray:item.unsupportedInputs ?: @[]];
            if (identifier.length > 0) [(sentAny ? pressed : inert) addObject:identifier];
          }
        }
        break;
      case LibretroTouchModeDPad:
        if (!controls || track.bound == nil) break;
        {
          NSString *identifier = track.bound.item.identifier ?: @"";
          if (identifier.length > 0) [touched addObject:identifier];
          if (LibretroDPadDirections(track.bound.frame, x, y) == 0) break;  // dead zone
          BOOL sentAny = [self applyDPad:track.bound x:x y:y sink:sink];
          if (identifier.length > 0) [(sentAny ? pressed : inert) addObject:identifier];
        }
        break;
      case LibretroTouchModeStick:
        if (!controls || track.bound == nil) break;
        {
          NSString *identifier = track.bound.item.identifier ?: @"";
          if (identifier.length > 0) [touched addObject:identifier];
          BOOL functional = [self applyStick:track.bound x:x y:y sink:sink];
          if (identifier.length > 0) {
            if (functional) {
              [pressed addObject:identifier];
              double stickX = 0, stickY = 0;
              LibretroStickVector(track.bound.frame, x, y, &stickX, &stickY);
              LibretroSize vector = {stickX, stickY};
              vectors[identifier] = [NSValue valueWithBytes:&vector objCType:@encode(LibretroSize)];
            } else {
              [inert addObject:identifier];
            }
          }
        }
        break;
      case LibretroTouchModePointer:
        if (pointer == nil) pointer = track;
        if (sent != nil) [sent addObject:@"touchScreen"];
        break;
      case LibretroTouchModeIgnored:
        break;
    }
    if (contacts != nil) {
      LibretroTouchContact *contact = [LibretroTouchContact new];
      contact.serial = track.serial;
      contact.mode = track.mode;
      contact.x = x;
      contact.y = y;
      contact.itemIdentifiers = touched;
      contact.sentInputs = sent;
      contact.inertInputs = inertInputs;
      [contacts addObject:contact];
    }
  }
  // An item pressed by one finger is not inert because another finger
  // touches it in a way that sends nothing.
  [inert minusSet:pressed];

  LibretroTouchResolution *resolution = [LibretroTouchResolution new];
  resolution.coreInput = state;
  if (pointer != nil) {
    _lastPointerX = pointer.pointerX;
    _lastPointerY = pointer.pointerY;
  }
  resolution.pointerPressed = pointer != nil;
  resolution.pointerX = _lastPointerX;
  resolution.pointerY = _lastPointerY;
  resolution.pressedItems = pressed;
  resolution.inertItems = inert;
  resolution.actions = actions;
  resolution.stickVectors = vectors;
  resolution.contacts = contacts ?: @[];
  return resolution;
}

#pragma mark - Pointer

- (BOOL)pointerInUse {
  for (LibretroTouchTrack *track in _tracks.allValues) {
    if (track.mode == LibretroTouchModePointer) return YES;
  }
  return NO;
}

- (NSArray<NSValue *> *)pointerMappings {
  NSMutableArray<NSValue *> *mappings = [NSMutableArray array];
  for (NSValue *value in _touchScreenMappings) {
    if (![value isKindOfClass:[NSValue class]]) continue;
    NSUInteger size = 0;
    NSGetSizeAndAlignment(value.objCType, &size, NULL);
    if (size != sizeof(LibretroScreenMapping)) continue;
    [mappings addObject:value];
  }
  if (mappings.count > 0) return mappings;
  // No picture published yet: the laid-out touch-screen containers.
  for (LibretroLaidOutScreen *screen in _layout.screens) {
    if (!screen.touchScreen) continue;
    LibretroScreenMapping mapping;
    memset(&mapping, 0, sizeof(mapping));
    mapping.output = screen.container;
    mapping.source = screen.source;
    mapping.rotation = 0;
    [mappings addObject:[NSValue valueWithBytes:&mapping objCType:@encode(LibretroScreenMapping)]];
  }
  return mappings;
}

/// Starts the pointer for `track` when the point is on a drawn touch
/// screen, or anywhere on a touch-screen item (`onTouchItem`: the nearest
/// screen, clamped). One pointer at a time.
- (BOOL)beginPointer:(LibretroTouchTrack *)track onTouchItem:(BOOL)onTouchItem {
  if ([self pointerInUse]) return NO;
  double x = track.x, y = track.y;
  BOOL found = NO;
  double nearest = INFINITY;
  LibretroScreenMapping chosen;
  memset(&chosen, 0, sizeof(chosen));
  for (NSValue *value in [self pointerMappings]) {
    LibretroScreenMapping mapping;
    [value getValue:&mapping size:sizeof(mapping)];
    if (TrackerContains(mapping.output, x, y)) {
      chosen = mapping;
      found = YES;
      break;
    }
    if (onTouchItem) {
      double distance = TrackerDistance(mapping.output, x, y);
      if (distance < nearest) {
        nearest = distance;
        chosen = mapping;
      }
    }
  }
  if (!found && !(onTouchItem && isfinite(nearest))) return NO;
  int16_t pointerX = 0, pointerY = 0;
  if (!LibretroPointerFromPoint(chosen, x, y, YES, &pointerX, &pointerY)) return NO;
  track.mode = LibretroTouchModePointer;
  track.mapping = chosen;
  track.pointerX = pointerX;
  track.pointerY = pointerY;
  return YES;
}

- (void)movePointer:(LibretroTouchTrack *)track {
  int16_t pointerX = track.pointerX, pointerY = track.pointerY;
  // Clamped while held: a finger leaving the screen keeps touching its edge.
  if (!LibretroPointerFromPoint(track.mapping, track.x, track.y, YES, &pointerX, &pointerY)) return;
  track.pointerX = pointerX;
  track.pointerY = pointerY;
}

/// After the touch screens moved (new mappings or layout): a held pointer
/// keeps its mapping while that screen is still drawn at the same place,
/// follows the touch screen now under the finger, or is released.
- (void)reresolvePointerTracks {
  NSArray<NSValue *> *mappings = nil;
  for (LibretroTouchTrack *track in _tracks.allValues) {
    if (track.mode != LibretroTouchModePointer) continue;
    if (mappings == nil) mappings = [self pointerMappings];
    LibretroScreenMapping resolved;
    memset(&resolved, 0, sizeof(resolved));
    if (![LibretroSkinLayout resolvePointerMapping:track.mapping
                                               atX:track.x
                                                 y:track.y
                                          mappings:mappings
                                            result:&resolved]) {
      // No touch screen under the finger any more (screens swapped): the
      // pointer is released where it was last seen.
      _lastPointerX = track.pointerX;
      _lastPointerY = track.pointerY;
      track.mode = LibretroTouchModeIgnored;
      continue;
    }
    track.mapping = resolved;
    [self movePointer:track];
  }
}

/// Where the touch screens are really drawn (NSValue of LibretroRect): the
/// presenter's mappings, else the laid-out containers.
- (NSArray<NSValue *> *)touchAreas {
  NSMutableArray<NSValue *> *areas = [NSMutableArray array];
  for (NSValue *value in [self pointerMappings]) {
    LibretroScreenMapping mapping;
    [value getValue:&mapping size:sizeof(mapping)];
    LibretroRect output = mapping.output;
    [areas addObject:[NSValue valueWithBytes:&output objCType:@encode(LibretroRect)]];
  }
  return areas;
}

- (NSArray<LibretroLaidOutItem *> *)itemsAtX:(double)x y:(double)y {
  if (_layout == nil) return @[];
  return [LibretroSkinLayout itemsAtX:x y:y inLayout:_layout touchAreas:[self touchAreas]];
}

#pragma mark - Fingers

- (LibretroTouchTrack *)trackAtX:(double)x y:(double)y {
  LibretroTouchTrack *track = [LibretroTouchTrack new];
  track.x = x;
  track.y = y;
  track.serial = _nextSerial++;
  // On the drawn touch screen, controls answer only inside their frames.
  NSArray<LibretroLaidOutItem *> *hits = [self itemsAtX:x y:y];
  BOOL touchItemOnly = hits.count > 0;
  for (LibretroLaidOutItem *laidOut in hits) {
    if (laidOut.item.kind != LibretroSkinItemKindTouchScreen) touchItemOnly = NO;
  }
  if (!self.controlsDisabled && !touchItemOnly && hits.count > 0) {
    LibretroLaidOutItem *first = hits.firstObject;
    if (hits.count == 1 && first.item.kind == LibretroSkinItemKindThumbstick) {
      track.mode = LibretroTouchModeStick;
      track.bound = first;
      return track;
    }
    if (hits.count == 1 && first.item.kind == LibretroSkinItemKindDPad) {
      track.mode = LibretroTouchModeDPad;
      track.bound = first;
      return track;
    }
    track.mode = LibretroTouchModeFree;
    track.items = TrackerSlidable(hits);
    return track;
  }
  // A touch-screen item alone, or nothing but a drawn touch screen.
  if ([self beginPointer:track onTouchItem:touchItemOnly]) return track;
  // Controls stay off with a controller or the setting; elsewhere an empty
  // finger may still slide onto a button.
  track.mode = self.controlsDisabled ? LibretroTouchModeIgnored : LibretroTouchModeFree;
  return track;
}

- (void)beginTouch:(id<NSCopying>)key x:(double)x y:(double)y {
  if (key == nil) return;
  // A key reused without an end (lost event) starts a new finger.
  _tracks[key] = [self trackAtX:x y:y];
}

- (void)moveTouch:(id<NSCopying>)key x:(double)x y:(double)y {
  LibretroTouchTrack *track = key != nil ? _tracks[key] : nil;
  if (track == nil) return;
  track.x = x;
  track.y = y;
  switch (track.mode) {
    case LibretroTouchModePointer:
      [self movePointer:track];
      break;
    case LibretroTouchModeFree:
      track.items = TrackerSlidable([self itemsAtX:x y:y]);
      break;
    case LibretroTouchModeDPad:
    case LibretroTouchModeStick:
    case LibretroTouchModeIgnored:
      break;
  }
}

- (void)endTouch:(id<NSCopying>)key {
  LibretroTouchTrack *track = key != nil ? _tracks[key] : nil;
  if (track == nil) return;
  if (track.mode == LibretroTouchModePointer) {
    // Released where it was last seen.
    _lastPointerX = track.pointerX;
    _lastPointerY = track.pointerY;
  }
  [_tracks removeObjectForKey:key];
}

- (void)endAllTouches {
  for (LibretroTouchTrack *track in _tracks.allValues) {
    if (track.mode != LibretroTouchModePointer) continue;
    _lastPointerX = track.pointerX;
    _lastPointerY = track.pointerY;
  }
  [_tracks removeAllObjects];
}

@end

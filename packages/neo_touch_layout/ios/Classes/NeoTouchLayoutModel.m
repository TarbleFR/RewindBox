// SPDX-License-Identifier: GPL-3.0-or-later
#import "Public/NeoTouchLayoutModel.h"
#import "Public/NeoTouchLayoutGeometry.h"

NSString* const NeoTouchLayoutKeyGameCube = @"gc";
NSString* const NeoTouchLayoutKeyWii = @"wii";
NSString* const NeoTouchLayoutKeyWiiClassic = @"wii-classic";
NSString* const NeoTouchLayoutKeyPlayStation2 = @"ps2";
NSString* const NeoTouchLayoutKeyPlayStation3 = @"ps3";
NSString* const NeoTouchLayoutOrientationLandscape = @"landscape";
NSString* const NeoTouchLayoutOrientationPortrait = @"portrait";

NSString* NeoTouchLayoutOrientationForSize(CGSize size) {
  return NeoTouchIsPortrait(size.width, size.height) ? NeoTouchLayoutOrientationPortrait
                                                     : NeoTouchLayoutOrientationLandscape;
}

NSString* NeoTouchLayoutConsoleForKey(NSString* key) {
  if ([key isEqualToString:NeoTouchLayoutKeyWiiClassic]) return NeoTouchLayoutKeyWii;
  return key ?: @"";
}

BOOL NeoTouchLayoutKeyIsValid(NSString* key) {
  if (![key isKindOfClass:NSString.class] || key.length == 0 || key.length > 32) return NO;
  NSCharacterSet* allowed = [NSCharacterSet characterSetWithCharactersInString:@"abcdefghijklmnopqrstuvwxyz0123456789-"];
  return [key rangeOfCharacterFromSet:allowed.invertedSet].location == NSNotFound;
}

NSString* NeoTouchLayoutGameKey(NSString* raw) {
  if (![raw isKindOfClass:NSString.class]) return nil;
  NSString* key = [[raw stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet]
      lowercaseString];
  if (key.length == 0) return nil;
  if (key.length > 200) key = [key substringToIndex:200];
  return key;
}

@implementation NeoTouchElement

- (instancetype)initWithIdentifier:(NSString*)identifier name:(NSString*)name kind:(NeoTouchElementKind)kind
                              view:(UIView*)view {
  self = [super init];
  if (self) {
    _identifier = [identifier copy];
    _name = [name copy];
    _kind = kind;
    _view = view;
    _defaultAlpha = 1.0;
  }
  return self;
}

- (void)captureDefaultGeometryInCanvas:(UIView*)canvas {
  UIView* view = self.view;
  if (!view) return;
  // center and bounds do not include the view's own transform.
  UIView* parent = view.superview ?: canvas;
  self.defaultCenter = parent == canvas ? view.center : [parent convertPoint:view.center toView:canvas];
  self.defaultSize = view.bounds.size;
}

- (NSString*)description {
  return [NSString stringWithFormat:@"<NeoTouchElement %@ %@ center=%@ size=%@>", self.identifier, self.name,
                                    NSStringFromCGPoint(self.defaultCenter), NSStringFromCGSize(self.defaultSize)];
}

@end

static double NeoTouchNumber(id value, double fallback) {
  return [value isKindOfClass:NSNumber.class] ? [value doubleValue] : fallback;
}

@implementation NeoTouchControlState

- (instancetype)init {
  self = [super init];
  if (self) {
    _scale = 1.0;
    _opacity = 1.0;
  }
  return self;
}

+ (instancetype)stateFromDictionary:(NSDictionary*)dictionary {
  NeoTouchControlState* state = [self new];
  if (![dictionary isKindOfClass:NSDictionary.class]) return state;
  const double x = NeoTouchNumber(dictionary[@"x"], NAN);
  const double y = NeoTouchNumber(dictionary[@"y"], NAN);
  if (NeoTouchValidNormalized(x) && NeoTouchValidNormalized(y)) {
    state.hasPosition = YES;
    state.x = x;
    state.y = y;
  }
  state.scale = NeoTouchClampScale(NeoTouchNumber(dictionary[@"scale"], 1.0));
  state.opacity = NeoTouchClampOpacity(NeoTouchNumber(dictionary[@"opacity"], 1.0));
  id hidden = dictionary[@"hidden"];
  state.hidden = [hidden isKindOfClass:NSNumber.class] && [hidden boolValue];
  return state;
}

- (id)copyWithZone:(NSZone*)zone {
  NeoTouchControlState* copy = [[NeoTouchControlState allocWithZone:zone] init];
  copy.hasPosition = self.hasPosition;
  copy.x = self.x;
  copy.y = self.y;
  copy.scale = self.scale;
  copy.opacity = self.opacity;
  copy.hidden = self.hidden;
  return copy;
}

- (BOOL)isDefault {
  return !self.hasPosition && fabs(self.scale - 1.0) < 0.0005 && fabs(self.opacity - 1.0) < 0.0005 && !self.hidden;
}

// Four decimals of the safe area (< 0.1 pt on any screen) keep the files
// stable and readable without changing a placement.
static NSNumber* NeoTouchRounded(double value) {
  return @(round(value * 10000.0) / 10000.0);
}

- (NSDictionary<NSString*, id>*)dictionaryRepresentation {
  if (self.isDefault) return nil;
  NSMutableDictionary* result = [NSMutableDictionary dictionary];
  if (self.hasPosition) {
    result[@"x"] = NeoTouchRounded(self.x);
    result[@"y"] = NeoTouchRounded(self.y);
  }
  if (fabs(self.scale - 1.0) >= 0.0005) result[@"scale"] = NeoTouchRounded(NeoTouchClampScale(self.scale));
  if (fabs(self.opacity - 1.0) >= 0.0005) result[@"opacity"] = NeoTouchRounded(NeoTouchClampOpacity(self.opacity));
  if (self.hidden) result[@"hidden"] = @YES;
  return result;
}

- (BOOL)isEqual:(id)object {
  if (![object isKindOfClass:NeoTouchControlState.class]) return NO;
  NSDictionary* mine = [self dictionaryRepresentation] ?: @{};
  NSDictionary* theirs = [object dictionaryRepresentation] ?: @{};
  return [mine isEqualToDictionary:theirs];
}

- (NSUInteger)hash {
  return [([self dictionaryRepresentation] ?: @{}) hash];
}

@end

@implementation NeoTouchLayout {
  NSMutableDictionary<NSString*, NeoTouchControlState*>* _states;
}

- (instancetype)init {
  self = [super init];
  if (self) _states = [NSMutableDictionary dictionary];
  return self;
}

+ (instancetype)layoutFromDictionary:(NSDictionary*)dictionary {
  NeoTouchLayout* layout = [self new];
  NSDictionary* elements = [dictionary isKindOfClass:NSDictionary.class] ? dictionary[@"elements"] : nil;
  if (![elements isKindOfClass:NSDictionary.class]) return layout;
  for (id identifier in elements) {
    if (![identifier isKindOfClass:NSString.class] || [identifier length] == 0 || [identifier length] > 64) continue;
    [layout setState:[NeoTouchControlState stateFromDictionary:elements[identifier]] forIdentifier:identifier];
  }
  return layout;
}

- (id)copyWithZone:(NSZone*)zone {
  NeoTouchLayout* copy = [[NeoTouchLayout allocWithZone:zone] init];
  for (NSString* identifier in _states) [copy setState:_states[identifier] forIdentifier:identifier];
  return copy;
}

- (NeoTouchControlState*)stateForIdentifier:(NSString*)identifier {
  NeoTouchControlState* state = identifier ? _states[identifier] : nil;
  return state ? [state copy] : [NeoTouchControlState new];
}

- (void)setState:(NeoTouchControlState*)state forIdentifier:(NSString*)identifier {
  if (identifier.length == 0) return;
  if (!state || state.isDefault) [_states removeObjectForKey:identifier];
  else _states[identifier] = [state copy];
}

- (NSArray<NSString*>*)customizedIdentifiers {
  return [_states.allKeys sortedArrayUsingSelector:@selector(compare:)];
}

- (BOOL)isEmpty {
  return _states.count == 0;
}

- (NSDictionary<NSString*, id>*)dictionaryRepresentation {
  NSMutableDictionary* elements = [NSMutableDictionary dictionary];
  for (NSString* identifier in _states) {
    NSDictionary* value = [_states[identifier] dictionaryRepresentation];
    if (value) elements[identifier] = value;
  }
  return @{@"elements": elements};
}

- (BOOL)isEqualToLayout:(NeoTouchLayout*)other {
  NSDictionary* mine = [self dictionaryRepresentation];
  NSDictionary* theirs = other ? [other dictionaryRepresentation] : [[NeoTouchLayout new] dictionaryRepresentation];
  return [mine isEqualToDictionary:theirs];
}

- (BOOL)isEqual:(id)object {
  return [object isKindOfClass:NeoTouchLayout.class] && [self isEqualToLayout:object];
}

- (NSUInteger)hash {
  return [[self dictionaryRepresentation] hash];
}

@end

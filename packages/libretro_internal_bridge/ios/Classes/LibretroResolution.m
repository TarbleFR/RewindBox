#import "LibretroResolution.h"

#import "LibretroCoreOptions.h"

#include <math.h>

@interface LibretroResolutionChoice ()
- (instancetype)initWithValue:(NSString *)value factor:(double)factor width:(NSUInteger)width height:(NSUInteger)height;
@end

@implementation LibretroResolutionChoice

- (instancetype)initWithValue:(NSString *)value factor:(double)factor width:(NSUInteger)width height:(NSUInteger)height {
  self = [super init];
  if (self) {
    _value = [value copy];
    _factor = factor;
    _width = width;
    _height = height;
  }
  return self;
}

- (BOOL)isNative {
  return fabs(_factor - 1.0) < 0.005;
}

- (NSString *)description {
  return [NSString stringWithFormat:@"%@ x%g %lux%lu", _value, _factor, (unsigned long)_width, (unsigned long)_height];
}

@end

@interface LibretroResolutionCapability ()
- (instancetype)initWithOption:(LibretroCoreOption *)option
                         apply:(LibretroResolutionApply)apply
                        source:(NSString *)source
                       choices:(NSArray<LibretroResolutionChoice *> *)choices;
@end

@implementation LibretroResolutionCapability

- (instancetype)initWithOption:(LibretroCoreOption *)option
                         apply:(LibretroResolutionApply)apply
                        source:(NSString *)source
                       choices:(NSArray<LibretroResolutionChoice *> *)choices {
  self = [super init];
  if (self) {
    _key = [option.key copy];
    _coreDescription = [option.coreDescription copy] ?: @"";
    _apply = apply;
    _source = [source copy];
    _choices = [choices copy];
    _coreDefault = [option.defaultValue copy] ?: @"";
    for (LibretroResolutionChoice *choice in choices) {
      if (choice.isNative) {
        _nativeChoice = choice;
        break;
      }
    }
  }
  return self;
}

- (LibretroResolutionChoice *)choiceForValue:(NSString *)value {
  if (value == nil) return nil;
  for (LibretroResolutionChoice *choice in _choices) {
    if ([choice.value isEqualToString:value]) return choice;
  }
  return nil;
}

- (NSDictionary<NSString *, id> *)snapshot {
  NSMutableArray<NSDictionary *> *choices = [NSMutableArray array];
  for (LibretroResolutionChoice *choice in _choices) {
    [choices addObject:@{
      @"value" : choice.value,
      @"factor" : @(choice.factor),
      @"width" : @(choice.width),
      @"height" : @(choice.height),
    }];
  }
  return @{
    @"key" : _key,
    @"description" : _coreDescription,
    @"apply" : _apply == LibretroResolutionApplyLive ? @"live" : @"relaunch",
    @"source" : _source,
    @"coreDefault" : _coreDefault,
    @"native" : _nativeChoice.value ?: (id)NSNull.null,
    @"choices" : choices,
  };
}

@end

#pragma mark - Values

static NSRegularExpression *Pattern(NSString *pattern, NSRegularExpressionOptions options) {
  return [NSRegularExpression regularExpressionWithPattern:pattern options:options error:nil];
}

/// "1,5" and "1.5" alike; NSString doubleValue ignores the locale.
static double NumberText(NSString *text) {
  return [[text stringByReplacingOccurrencesOfString:@"," withString:@"."] doubleValue];
}

static NSTextCheckingResult *FirstMatch(NSRegularExpression *expression, NSString *text) {
  if (expression == nil) return nil;
  return [expression firstMatchInString:text options:0 range:NSMakeRange(0, text.length)];
}

static NSString *Group(NSTextCheckingResult *match, NSString *text, NSUInteger group) {
  NSRange range = [match rangeAtIndex:group];
  return range.location == NSNotFound ? @"" : [text substringWithRange:range];
}

BOOL LibretroResolutionParseValue(NSString *raw, double *factor, NSUInteger *width, NSUInteger *height) {
  // The patterns of Dart's LibretroResolution.token, in the same order.
  static NSRegularExpression *leadingSize, *leadingMultiplier, *leadingTimes, *bareNumber, *innerMultiplier,
      *native;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    leadingSize = Pattern(@"^(\\d{2,5})\\s*[xX\\u00D7*]\\s*(\\d{2,5})(?!\\d)", 0);
    leadingMultiplier = Pattern(@"^(\\d+(?:[.,]\\d+)?)\\s*[xX\\u00D7](?!\\s*\\d)", 0);
    leadingTimes = Pattern(@"^[xX\\u00D7]\\s*(\\d+(?:[.,]\\d+)?)(?![\\d.,]|\\s*[xX\\u00D7]\\s*\\d)", 0);
    bareNumber = Pattern(@"^(\\d+(?:[.,]\\d+)?)$", 0);
    innerMultiplier = Pattern(@"(?<![\\d.,])(\\d+(?:[.,]\\d+)?)\\s*[xX\\u00D7](?!\\s*\\d)", 0);
    native = Pattern(@"native|original", NSRegularExpressionCaseInsensitive);
  });
  if (factor != NULL) *factor = 0;
  if (width != NULL) *width = 0;
  if (height != NULL) *height = 0;
  if (![raw isKindOfClass:NSString.class]) return NO;
  NSString *value = [raw stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
  if (value.length == 0) return NO;
  NSTextCheckingResult *size = FirstMatch(leadingSize, value);
  if (size != nil) {
    NSInteger w = [Group(size, value, 1) integerValue];
    NSInteger h = [Group(size, value, 2) integerValue];
    if (w <= 0 || h <= 0) return NO;
    if (width != NULL) *width = (NSUInteger)w;
    if (height != NULL) *height = (NSUInteger)h;
    return YES;
  }
  NSTextCheckingResult *match = FirstMatch(leadingMultiplier, value);
  if (match == nil) match = FirstMatch(leadingTimes, value);
  if (match == nil) match = FirstMatch(bareNumber, value);
  if (match != nil) {
    double number = NumberText(Group(match, value, 1));
    if (!(number > 0)) return NO;
    if (factor != NULL) *factor = number;
    return YES;
  }
  if (FirstMatch(native, value) != nil) {
    NSTextCheckingResult *inner = FirstMatch(innerMultiplier, value);
    double number = inner == nil ? 1.0 : NumberText(Group(inner, value, 1));
    if (!(number > 0)) return NO;
    if (factor != NULL) *factor = number;
    return YES;
  }
  return NO;
}

static double Rounded(double factor) {
  return round(factor * 100.0) / 100.0;
}

NSArray<LibretroResolutionChoice *> *LibretroResolutionChoices(NSArray<NSString *> *values, NSArray<NSString *> *labels,
                                                               NSArray<NSNumber *> *nativeSize, double consoleWidth,
                                                               double consoleHeight, double maxFactor,
                                                               NSInteger maxDimension) {
  // Value -> (factor, width, height), first declaration of each value.
  NSMutableArray<NSString *> *order = [NSMutableArray array];
  NSMutableDictionary<NSString *, NSArray<NSNumber *> *> *tokens = [NSMutableDictionary dictionary];
  for (NSUInteger index = 0; index < values.count; index++) {
    NSString *value = values[index];
    if (![value isKindOfClass:NSString.class] || tokens[value] != nil) continue;
    double factor = 0;
    NSUInteger width = 0, height = 0;
    BOOL parsed = LibretroResolutionParseValue(value, &factor, &width, &height);
    if (!parsed && index < labels.count) parsed = LibretroResolutionParseValue(labels[index], &factor, &width, &height);
    if (!parsed) continue;
    tokens[value] = @[ @(factor), @(width), @(height) ];
    [order addObject:value];
  }
  double baseWidth = 0, baseHeight = 0;
  if (nativeSize.count == 2 && [nativeSize[0] isKindOfClass:NSNumber.class] &&
      [nativeSize[1] isKindOfClass:NSNumber.class]) {
    baseWidth = nativeSize[0].doubleValue;
    baseHeight = nativeSize[1].doubleValue;
  } else {
    for (NSString *value in order) {
      NSArray<NSNumber *> *token = tokens[value];
      if (token[0].doubleValue > 0) continue;
      if (baseWidth <= 0 || token[1].doubleValue < baseWidth) {
        baseWidth = token[1].doubleValue;
        baseHeight = token[2].doubleValue;
      }
    }
  }
  NSMutableArray<LibretroResolutionChoice *> *result = [NSMutableArray array];
  NSMutableSet<NSNumber *> *seen = [NSMutableSet set];
  for (NSString *value in order) {
    NSArray<NSNumber *> *token = tokens[value];
    double factor = token[0].doubleValue;
    NSUInteger width = token[1].unsignedIntegerValue, height = token[2].unsignedIntegerValue;
    if (!(factor > 0)) {
      if (baseWidth <= 0 || baseHeight <= 0) continue;
      double horizontal = (double)width / baseWidth;
      double vertical = (double)height / baseHeight;
      if (fabs(horizontal - vertical) > 0.02 * fmax(horizontal, vertical)) continue;
      factor = Rounded(horizontal);
    } else {
      factor = Rounded(factor);
      width = 0;
      height = 0;
    }
    if (factor < 0.995) continue;
    if (maxFactor > 0 && factor > maxFactor + 0.005) continue;
    if (maxDimension > 0 && consoleWidth > 0 && consoleHeight > 0 &&
        fmax(consoleWidth, consoleHeight) * factor > (double)maxDimension + 0.5) {
      continue;
    }
    NSNumber *key = @(factor);
    if ([seen containsObject:key]) continue;
    [seen addObject:key];
    [result addObject:[[LibretroResolutionChoice alloc] initWithValue:value factor:factor width:width height:height]];
  }
  [result sortUsingComparator:^NSComparisonResult(LibretroResolutionChoice *a, LibretroResolutionChoice *b) {
    if (a.factor < b.factor) return NSOrderedAscending;
    if (a.factor > b.factor) return NSOrderedDescending;
    return NSOrderedSame;
  }];
  return result;
}

#pragma mark - Rules

@implementation LibretroResolutionRules {
  NSArray<NSDictionary *> *_profiles;
  NSRegularExpression *_keyPattern;
  NSRegularExpression *_descriptionPattern;
  NSInteger _maxDimension;
}

static NSArray<NSString *> *StringArray(id object) {
  if (![object isKindOfClass:NSArray.class]) return @[];
  NSMutableArray<NSString *> *strings = [NSMutableArray array];
  for (id item in object) {
    if ([item isKindOfClass:NSString.class] && [item length] > 0) [strings addObject:item];
  }
  return strings;
}

- (instancetype)initWithDictionary:(NSDictionary *)rules {
  self = [super init];
  if (self) {
    NSDictionary *source = [rules isKindOfClass:NSDictionary.class] ? rules : @{};
    NSMutableArray<NSDictionary *> *profiles = [NSMutableArray array];
    id list = source[@"profiles"];
    for (id entry in ([list isKindOfClass:NSArray.class] ? list : @[])) {
      if (![entry isKindOfClass:NSDictionary.class]) continue;
      NSArray<NSString *> *keys = StringArray(entry[@"keys"]);
      if (keys.count == 0) continue;
      NSMutableDictionary *profile = [NSMutableDictionary dictionaryWithObject:keys forKey:@"keys"];
      profile[@"apply"] = @([entry[@"apply"] isEqual:@"live"] ? LibretroResolutionApplyLive
                                                               : LibretroResolutionApplyRelaunch);
      NSArray *native = entry[@"nativeSize"];
      if ([native isKindOfClass:NSArray.class] && native.count == 2 && [native[0] isKindOfClass:NSNumber.class] &&
          [native[1] isKindOfClass:NSNumber.class] && [native[0] doubleValue] > 0 && [native[1] doubleValue] > 0) {
        profile[@"nativeSize"] = native;
      }
      id maxFactor = entry[@"maxFactor"];
      profile[@"maxFactor"] = [maxFactor isKindOfClass:NSNumber.class] ? maxFactor : @0;
      NSMutableDictionary<NSString *, NSArray<NSString *> *> *requires = [NSMutableDictionary dictionary];
      id conditions = entry[@"requires"];
      if ([conditions isKindOfClass:NSDictionary.class]) {
        for (id key in conditions) {
          if ([key isKindOfClass:NSString.class]) requires[key] = StringArray(conditions[key]);
        }
      }
      profile[@"requires"] = requires;
      [profiles addObject:profile];
    }
    _profiles = profiles;
    id keyPattern = source[@"keyPattern"];
    id descriptionPattern = source[@"descriptionPattern"];
    _keyPattern = [keyPattern isKindOfClass:NSString.class] && [keyPattern length] > 0
                      ? Pattern(keyPattern, NSRegularExpressionCaseInsensitive)
                      : nil;
    _descriptionPattern = [descriptionPattern isKindOfClass:NSString.class] && [descriptionPattern length] > 0
                              ? Pattern(descriptionPattern, NSRegularExpressionCaseInsensitive)
                              : nil;
    id maxDimension = source[@"maxDimension"];
    _maxDimension = [maxDimension isKindOfClass:NSNumber.class] ? [maxDimension integerValue] : 0;
  }
  return self;
}

- (LibretroResolutionCapability *)capabilityForOptions:(NSArray<LibretroCoreOption *> *)options
                                           valueForKey:(NSString * (^)(NSString *key))valueForKey
                                          consoleWidth:(double)consoleWidth
                                         consoleHeight:(double)consoleHeight {
  NSMutableDictionary<NSString *, LibretroCoreOption *> *declared = [NSMutableDictionary dictionary];
  for (LibretroCoreOption *option in options) declared[option.key] = option;
  // Keys named by a profile: never recognized generically, even when no
  // profile of theirs applies (PPSSPP's software rendering forces 1x).
  NSMutableSet<NSString *> *claimed = [NSMutableSet set];
  for (NSDictionary *profile in _profiles) [claimed addObjectsFromArray:profile[@"keys"]];
  for (NSDictionary *profile in _profiles) {
    BOOL met = YES;
    NSDictionary<NSString *, NSArray<NSString *> *> *requires = profile[@"requires"];
    for (NSString *key in requires) {
      if (declared[key] == nil) continue;
      NSString *current = valueForKey != nil ? valueForKey(key) : nil;
      if (current == nil || ![requires[key] containsObject:current]) {
        met = NO;
        break;
      }
    }
    if (!met) continue;
    for (NSString *key in profile[@"keys"]) {
      LibretroCoreOption *option = declared[key];
      if (option == nil || !option.visible) continue;
      NSArray<LibretroResolutionChoice *> *choices =
          LibretroResolutionChoices(option.values, option.valueLabels, profile[@"nativeSize"], consoleWidth,
                                    consoleHeight, [profile[@"maxFactor"] doubleValue], _maxDimension);
      if (choices.count < 2) continue;
      return [[LibretroResolutionCapability alloc] initWithOption:option
                                                            apply:(LibretroResolutionApply)[profile[@"apply"] integerValue]
                                                           source:@"profile"
                                                          choices:choices];
    }
  }
  if (_keyPattern == nil && _descriptionPattern == nil) return nil;
  for (LibretroCoreOption *option in options) {
    if (!option.visible || [claimed containsObject:option.key]) continue;
    BOOL named = FirstMatch(_keyPattern, option.key) != nil ||
                 (option.coreDescription.length > 0 && FirstMatch(_descriptionPattern, option.coreDescription) != nil);
    if (!named) continue;
    NSArray<LibretroResolutionChoice *> *choices = LibretroResolutionChoices(
        option.values, option.valueLabels, nil, consoleWidth, consoleHeight, 0, _maxDimension);
    if (choices.count < 2 || !choices.firstObject.isNative) continue;
    return [[LibretroResolutionCapability alloc] initWithOption:option
                                                          apply:LibretroResolutionApplyRelaunch
                                                         source:@"generic"
                                                        choices:choices];
  }
  return nil;
}

- (LibretroResolutionCapability *)capabilityForCoreOptions:(LibretroCoreOptions *)options
                                               consoleWidth:(double)consoleWidth
                                              consoleHeight:(double)consoleHeight {
  if (options == nil) return nil;
  return [self capabilityForOptions:options.options
                        valueForKey:^NSString *(NSString *key) {
                          return [options currentValueForKey:key];
                        }
                       consoleWidth:consoleWidth
                      consoleHeight:consoleHeight];
}

@end

#pragma mark - Choices

NSString *LibretroResolutionApplyNativeDefault(LibretroResolutionCapability *capability, LibretroCoreOptions *options) {
  LibretroResolutionChoice *native = capability.nativeChoice;
  if (native == nil || options == nil || [capability.coreDefault isEqualToString:native.value]) return nil;
  if ([options assignedValueForKey:capability.key] != nil) return nil;
  [options applyDefaultsBeforeInit:@{capability.key : native.value}];
  return native.value;
}

BOOL LibretroResolutionSelect(LibretroResolutionCapability *capability, LibretroCoreOptions *options, NSString *value,
                              BOOL game) {
  if (capability == nil || options == nil || [capability choiceForValue:value] == nil) return NO;
  return [options setValue:value
                    forKey:capability.key
                      game:game
                  applyNow:capability.apply == LibretroResolutionApplyLive];
}

BOOL LibretroResolutionClear(LibretroResolutionCapability *capability, LibretroCoreOptions *options, BOOL game) {
  if (capability == nil || options == nil) return NO;
  return [options removeValueForKey:capability.key game:game applyNow:capability.apply == LibretroResolutionApplyLive];
}

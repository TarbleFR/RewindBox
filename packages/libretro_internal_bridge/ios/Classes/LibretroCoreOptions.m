#import "LibretroCoreOptions.h"

@interface LibretroCoreOption ()
@property(nonatomic, copy, readwrite) NSString *key;
@property(nonatomic, copy, readwrite) NSString *coreDescription;
@property(nonatomic, copy, readwrite) NSArray<NSString *> *values;
@property(nonatomic, copy, readwrite) NSArray<NSString *> *valueLabels;
@property(nonatomic, copy, readwrite) NSString *defaultValue;
@end

@implementation LibretroCoreOption
@end

static NSString *StringOrEmpty(const char *value) {
  if (value == NULL) return @"";
  NSString *string = [NSString stringWithUTF8String:value];
  return string ?: @"";
}

/// Top-level JSON object of a file, nil when absent or unreadable.
static NSDictionary *JSONDictionaryAtPath(NSString *path) {
  if (path.length == 0) return nil;
  NSData *data = [NSData dataWithContentsOfFile:path];
  if (data == nil) return nil;
  id json = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
  return [json isKindOfClass:[NSDictionary class]] ? json : nil;
}

/// {String: String} entries of a JSON object; others are ignored, as Dart's
/// LibretroCoreOptionStore does.
static NSMutableDictionary<NSString *, NSString *> *StringValues(id object) {
  NSMutableDictionary<NSString *, NSString *> *values = [NSMutableDictionary dictionary];
  if (![object isKindOfClass:[NSDictionary class]]) return values;
  NSDictionary *source = object;
  for (id key in source) {
    id value = source[key];
    if ([key isKindOfClass:[NSString class]] && [value isKindOfClass:[NSString class]]) values[key] = value;
  }
  return values;
}

static NSString *const kGamesKey = @"games";

@implementation LibretroCoreOptions {
  NSString *_storePath;
  NSString *_gameStorePath;
  NSMutableArray<LibretroCoreOption *> *_options;
  NSMutableDictionary<NSString *, NSString *> *_stored;
  // Values of the running game (Config/Games/<core>.json).
  NSMutableDictionary<NSString *, NSString *> *_game;
  // Values in effect when a change was made for the next launch only.
  NSMutableDictionary<NSString *, NSString *> *_pinned;
  NSMutableDictionary<NSString *, NSString *> *_overrides;
  NSMutableDictionary<NSString *, NSString *> *_defaults;
  NSMutableSet<NSString *> *_locked;
  NSMutableDictionary<NSString *, NSData *> *_cStrings;
  BOOL _updatePending;
}

- (instancetype)initWithStorePath:(NSString *)storePath {
  return [self initWithStorePath:storePath gameStorePath:nil gameKey:nil];
}

- (instancetype)initWithStorePath:(NSString *)storePath
                    gameStorePath:(NSString *)gameStorePath
                          gameKey:(NSString *)gameKey {
  self = [super init];
  if (self) {
    _storePath = [storePath copy];
    BOOL perGame = gameStorePath.length > 0 && gameKey.length > 0;
    _gameStorePath = perGame ? [gameStorePath copy] : nil;
    _gameKey = perGame ? [gameKey copy] : nil;
    _options = [NSMutableArray array];
    _overrides = [NSMutableDictionary dictionary];
    _defaults = [NSMutableDictionary dictionary];
    _pinned = [NSMutableDictionary dictionary];
    _locked = [NSMutableSet set];
    _cStrings = [NSMutableDictionary dictionary];
    _stored = StringValues(JSONDictionaryAtPath(storePath)[@"values"]);
    _game = [NSMutableDictionary dictionary];
    if (perGame) {
      id games = JSONDictionaryAtPath(_gameStorePath)[kGamesKey];
      if ([games isKindOfClass:[NSDictionary class]]) _game = StringValues(((NSDictionary *)games)[_gameKey]);
    }
  }
  return self;
}

- (NSArray<LibretroCoreOption *> *)options {
  @synchronized(self) {
    return [_options copy];
  }
}

- (BOOL)updatePending {
  @synchronized(self) {
    return _updatePending;
  }
}

/// Merges `values` into `target` (session overrides or NeoStation defaults).
/// Values given before the core declares its options are kept and resolved
/// once declared. Only keys whose effective value changes lose their cached
/// C string, and a change of a declared option is flagged for the core.
- (void)mergeValuesLocked:(NSDictionary<NSString *, NSString *> *)values
                     into:(NSMutableDictionary<NSString *, NSString *> *)target
                   locked:(BOOL)locked
               flagUpdate:(BOOL)flagUpdate {
  for (id key in values) {
    id value = values[key];
    if (![key isKindOfClass:[NSString class]] || ![value isKindOfClass:[NSString class]]) continue;
    NSString *previous = [self effectiveValueLocked:key pinned:YES];
    target[key] = value;
    if (locked) [_locked addObject:key];
    [self noteChangeLocked:key from:previous flagUpdate:flagUpdate];
  }
}

- (void)mergeValuesLocked:(NSDictionary<NSString *, NSString *> *)values
                     into:(NSMutableDictionary<NSString *, NSString *> *)target
                   locked:(BOOL)locked {
  [self mergeValuesLocked:values into:target locked:locked flagUpdate:YES];
}

/// After a layer changed: a new value in effect loses its cached C string
/// and, for a declared option, is flagged for the core.
- (void)noteChangeLocked:(NSString *)key from:(NSString *)previous flagUpdate:(BOOL)flagUpdate {
  NSString *current = [self effectiveValueLocked:key pinned:YES];
  if (current == previous || [current isEqualToString:previous]) return;
  [_cStrings removeObjectForKey:key];
  if (flagUpdate && [self optionForKeyLocked:key] != nil) _updatePending = YES;
}

- (void)applySessionOverrides:(NSDictionary<NSString *, NSString *> *)overrides {
  @synchronized(self) {
    [self mergeValuesLocked:overrides into:_overrides locked:NO];
  }
}

- (void)lockSessionOverrides:(NSDictionary<NSString *, NSString *> *)overrides {
  @synchronized(self) {
    [self mergeValuesLocked:overrides into:_overrides locked:YES];
  }
}

- (void)applyDefaults:(NSDictionary<NSString *, NSString *> *)defaults {
  @synchronized(self) {
    [self mergeValuesLocked:defaults into:_defaults locked:NO];
  }
}

- (void)applyDefaultsBeforeInit:(NSDictionary<NSString *, NSString *> *)defaults {
  @synchronized(self) {
    [self mergeValuesLocked:defaults into:_defaults locked:NO flagUpdate:NO];
  }
}

- (BOOL)isLockedKey:(NSString *)key {
  @synchronized(self) {
    return [_locked containsObject:key];
  }
}

- (LibretroCoreOption *)optionForKeyLocked:(NSString *)key {
  for (LibretroCoreOption *option in _options) {
    if ([option.key isEqualToString:key]) return option;
  }
  return nil;
}

- (void)addOptionLocked:(LibretroCoreOption *)option {
  LibretroCoreOption *existing = [self optionForKeyLocked:option.key];
  if (existing != nil) [_options removeObject:existing];
  [_options addObject:option];
  [_cStrings removeObjectForKey:option.key];
}

- (BOOL)declareVariables:(const struct retro_variable *)variables {
  if (variables == NULL) return NO;
  @synchronized(self) {
    for (const struct retro_variable *variable = variables; variable->key != NULL; variable++) {
      NSString *key = StringOrEmpty(variable->key);
      NSString *spec = StringOrEmpty(variable->value);
      NSRange separator = [spec rangeOfString:@"; "];
      NSString *description = separator.location == NSNotFound ? spec : [spec substringToIndex:separator.location];
      NSString *list = separator.location == NSNotFound ? @"" : [spec substringFromIndex:NSMaxRange(separator)];
      NSArray<NSString *> *values = list.length > 0 ? [list componentsSeparatedByString:@"|"] : @[];
      if (key.length == 0 || values.count == 0) continue;
      LibretroCoreOption *option = [LibretroCoreOption new];
      option.key = key;
      option.coreDescription = description;
      option.values = values;
      option.valueLabels = values;
      option.defaultValue = values.firstObject;
      option.visible = YES;
      [self addOptionLocked:option];
    }
  }
  return YES;
}

static LibretroCoreOption *OptionFromValues(NSString *key, const char *desc, const struct retro_core_option_value *values,
                                            const char *defaultValue, const struct retro_core_option_value *localValues,
                                            const char *localDesc) {
  NSMutableArray<NSString *> *names = [NSMutableArray array];
  NSMutableArray<NSString *> *labels = [NSMutableArray array];
  for (unsigned i = 0; i < RETRO_NUM_CORE_OPTION_VALUES_MAX && values[i].value != NULL; i++) {
    NSString *value = StringOrEmpty(values[i].value);
    NSString *label = values[i].label != NULL ? StringOrEmpty(values[i].label) : value;
    if (localValues != NULL) {
      for (unsigned j = 0; j < RETRO_NUM_CORE_OPTION_VALUES_MAX && localValues[j].value != NULL; j++) {
        if (strcmp(localValues[j].value, values[i].value) == 0 && localValues[j].label != NULL) {
          label = StringOrEmpty(localValues[j].label);
          break;
        }
      }
    }
    [names addObject:value];
    [labels addObject:label];
  }
  if (names.count == 0) return nil;
  LibretroCoreOption *option = [LibretroCoreOption new];
  option.key = key;
  option.coreDescription = StringOrEmpty(localDesc != NULL ? localDesc : desc);
  option.values = names;
  option.valueLabels = labels;
  NSString *fallback = defaultValue != NULL ? StringOrEmpty(defaultValue) : names.firstObject;
  option.defaultValue = [names containsObject:fallback] ? fallback : names.firstObject;
  option.visible = YES;
  return option;
}

- (BOOL)declareDefinitions:(const struct retro_core_option_definition *)definitions
                     local:(const struct retro_core_option_definition *)local {
  if (definitions == NULL) return NO;
  @synchronized(self) {
    for (const struct retro_core_option_definition *definition = definitions; definition->key != NULL; definition++) {
      const struct retro_core_option_definition *translated = NULL;
      for (const struct retro_core_option_definition *candidate = local; candidate != NULL && candidate->key != NULL;
           candidate++) {
        if (strcmp(candidate->key, definition->key) == 0) {
          translated = candidate;
          break;
        }
      }
      LibretroCoreOption *option =
          OptionFromValues(StringOrEmpty(definition->key), definition->desc, definition->values,
                           definition->default_value, translated ? translated->values : NULL,
                           translated ? translated->desc : NULL);
      if (option != nil) [self addOptionLocked:option];
    }
  }
  return YES;
}

- (BOOL)declareV2:(const struct retro_core_options_v2 *)options local:(const struct retro_core_options_v2 *)local {
  if (options == NULL || options->definitions == NULL) return NO;
  @synchronized(self) {
    for (const struct retro_core_option_v2_definition *definition = options->definitions; definition->key != NULL;
         definition++) {
      const struct retro_core_option_v2_definition *translated = NULL;
      if (local != NULL && local->definitions != NULL) {
        for (const struct retro_core_option_v2_definition *candidate = local->definitions; candidate->key != NULL;
             candidate++) {
          if (strcmp(candidate->key, definition->key) == 0) {
            translated = candidate;
            break;
          }
        }
      }
      LibretroCoreOption *option =
          OptionFromValues(StringOrEmpty(definition->key), definition->desc, definition->values,
                           definition->default_value, translated ? translated->values : NULL,
                           translated ? translated->desc : NULL);
      if (option != nil) [self addOptionLocked:option];
    }
  }
  return YES;
}

- (void)setDisplay:(const struct retro_core_option_display *)display {
  if (display == NULL || display->key == NULL) return;
  @synchronized(self) {
    LibretroCoreOption *option = [self optionForKeyLocked:StringOrEmpty(display->key)];
    option.visible = display->visible;
  }
}

/// First layer value the core offers (any value while the option is not
/// declared yet), nil when only the core's default is left. `pinned` NO
/// leaves out the values kept for this session (next launch).
- (NSString *)assignedValueLocked:(NSString *)key pinned:(BOOL)pinned {
  LibretroCoreOption *option = [self optionForKeyLocked:key];
  NSString *layers[5] = {pinned ? _pinned[key] : nil, _overrides[key], _game[key], _stored[key], _defaults[key]};
  for (int index = 0; index < 5; index++) {
    NSString *value = layers[index];
    if (value != nil && (option == nil || [option.values containsObject:value])) return value;
  }
  return nil;
}

- (NSString *)effectiveValueLocked:(NSString *)key pinned:(BOOL)pinned {
  NSString *assigned = [self assignedValueLocked:key pinned:pinned];
  if (assigned != nil) return assigned;
  return [self optionForKeyLocked:key].defaultValue;
}

- (NSString *)assignedValueForKey:(NSString *)key {
  @synchronized(self) {
    return [self assignedValueLocked:key pinned:YES];
  }
}

- (NSString *)storedValueForKey:(NSString *)key {
  @synchronized(self) {
    return _stored[key];
  }
}

- (NSString *)gameValueForKey:(NSString *)key {
  @synchronized(self) {
    return _game[key];
  }
}

- (NSString *)valueForEveryGameForKey:(NSString *)key {
  @synchronized(self) {
    LibretroCoreOption *option = [self optionForKeyLocked:key];
    for (NSString *value in @[ _stored[key] ?: @"", _defaults[key] ?: @"" ]) {
      if (value.length > 0 && (option == nil || [option.values containsObject:value])) return value;
    }
    return option.defaultValue;
  }
}

- (NSString *)currentValueForKey:(NSString *)key {
  @synchronized(self) {
    return [self effectiveValueLocked:key pinned:YES];
  }
}

- (NSString *)nextLaunchValueForKey:(NSString *)key {
  @synchronized(self) {
    return [self effectiveValueLocked:key pinned:NO];
  }
}

- (const char *)valueForKey:(const char *)key {
  if (key == NULL) return NULL;
  @synchronized(self) {
    NSString *name = StringOrEmpty(key);
    NSData *cached = _cStrings[name];
    if (cached != nil) return cached.bytes;
    NSString *value = [self effectiveValueLocked:name pinned:YES];
    if (value == nil) return NULL;
    const char *utf8 = value.UTF8String;
    NSData *storage = [NSData dataWithBytes:utf8 length:strlen(utf8) + 1];
    _cStrings[name] = storage;
    return storage.bytes;
  }
}

- (BOOL)setValue:(NSString *)value forKey:(NSString *)key persist:(BOOL)persist {
  @synchronized(self) {
    // NeoStation needs these values for the whole session (DS / 3DS screens).
    if ([_locked containsObject:key]) return NO;
    LibretroCoreOption *option = [self optionForKeyLocked:key];
    if (option != nil && ![option.values containsObject:value]) return NO;
    NSString *previous = [self effectiveValueLocked:key pinned:YES];
    [_overrides removeObjectForKey:key];
    [_pinned removeObjectForKey:key];
    _stored[key] = value;
    [_cStrings removeObjectForKey:key];
    NSString *current = [self effectiveValueLocked:key pinned:YES];
    if (![previous isEqualToString:current]) _updatePending = YES;
  }
  if (persist) [self save];
  return YES;
}

/// Shared by setValue:forKey:game:applyNow: (value) and
/// removeValueForKey:game:applyNow: (nil).
- (BOOL)changeValue:(NSString *)value forKey:(NSString *)key game:(BOOL)game applyNow:(BOOL)applyNow {
  NSDictionary *gameValues = nil;
  @synchronized(self) {
    if (key.length == 0 || [_locked containsObject:key]) return NO;
    if (game && _gameKey == nil) return NO;
    LibretroCoreOption *option = [self optionForKeyLocked:key];
    if (value != nil && option != nil && ![option.values containsObject:value]) return NO;
    NSString *previous = [self effectiveValueLocked:key pinned:YES];
    if (applyNow) {
      [_pinned removeObjectForKey:key];
    } else if (_pinned[key] == nil && previous != nil) {
      // The running core keeps what it has; the next launch reads the choice.
      _pinned[key] = previous;
    }
    // A user choice wins over a session override, as setValue:forKey:persist:.
    [_overrides removeObjectForKey:key];
    NSMutableDictionary<NSString *, NSString *> *layer = game ? _game : _stored;
    if (value != nil) {
      layer[key] = value;
    } else {
      [layer removeObjectForKey:key];
    }
    [self noteChangeLocked:key from:previous flagUpdate:YES];
    if (game) gameValues = [_game copy];
  }
  if (game) {
    [self saveGameValues:gameValues];
  } else {
    [self save];
  }
  return YES;
}

- (BOOL)setValue:(NSString *)value forKey:(NSString *)key game:(BOOL)game applyNow:(BOOL)applyNow {
  if (![value isKindOfClass:[NSString class]]) return NO;
  return [self changeValue:value forKey:key game:game applyNow:applyNow];
}

- (BOOL)removeValueForKey:(NSString *)key game:(BOOL)game applyNow:(BOOL)applyNow {
  return [self changeValue:nil forKey:key game:game applyNow:applyNow];
}

- (BOOL)consumeUpdate {
  @synchronized(self) {
    BOOL pending = _updatePending;
    _updatePending = NO;
    return pending;
  }
}

- (void)save {
  NSDictionary *snapshot;
  @synchronized(self) {
    snapshot = @{@"values" : [_stored copy]};
  }
  NSData *data = [NSJSONSerialization dataWithJSONObject:snapshot options:NSJSONWritingPrettyPrinted error:nil];
  if (data == nil) return;
  [[NSFileManager defaultManager] createDirectoryAtPath:[_storePath stringByDeletingLastPathComponent]
                            withIntermediateDirectories:YES
                                             attributes:nil
                                                  error:nil];
  [data writeToFile:_storePath atomically:YES];
}

/// Rewrites the running game's entry of the per-game file, read again
/// first: other games and unknown keys stay as they are; a game left with
/// no value loses its entry.
- (void)saveGameValues:(NSDictionary<NSString *, NSString *> *)values {
  if (_gameStorePath == nil || _gameKey == nil) return;
  @synchronized([LibretroCoreOptions class]) {
    NSMutableDictionary *document = [JSONDictionaryAtPath(_gameStorePath) mutableCopy] ?: [NSMutableDictionary dictionary];
    id existing = document[kGamesKey];
    NSMutableDictionary *games =
        [existing isKindOfClass:[NSDictionary class]] ? [existing mutableCopy] : [NSMutableDictionary dictionary];
    if (values.count > 0) {
      games[_gameKey] = values;
    } else {
      [games removeObjectForKey:_gameKey];
    }
    document[kGamesKey] = games;
    document[@"version"] = @1;
    NSData *data = [NSJSONSerialization dataWithJSONObject:document
                                                   options:NSJSONWritingPrettyPrinted | NSJSONWritingSortedKeys
                                                     error:nil];
    if (data == nil) return;
    [[NSFileManager defaultManager] createDirectoryAtPath:[_gameStorePath stringByDeletingLastPathComponent]
                              withIntermediateDirectories:YES
                                               attributes:nil
                                                    error:nil];
    [data writeToFile:_gameStorePath atomically:YES];
  }
}

@end

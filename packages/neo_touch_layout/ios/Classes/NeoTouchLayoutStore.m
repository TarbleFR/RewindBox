// SPDX-License-Identifier: GPL-3.0-or-later
#import "Public/NeoTouchLayoutStore.h"

NSNotificationName const NeoTouchLayoutStoreDidChangeNotification = @"NeoTouchLayoutStoreDidChangeNotification";
NSNotificationName const NeoTouchControllerPreferenceDidChangeNotification =
    @"NeoTouchControllerPreferenceDidChangeNotification";

static const NSInteger kNeoTouchLayoutFormat = 1;

NSString* NeoTouchHideWithControllerDefaultsKey(NSString* console) {
  return [NSString stringWithFormat:@"NeoStation.TouchControls.%@.HideWhenControllerConnected", console ?: @""];
}

BOOL NeoTouchHidesControlsWithController(NSString* console) {
  id value = [NSUserDefaults.standardUserDefaults objectForKey:NeoTouchHideWithControllerDefaultsKey(console)];
  return [value isKindOfClass:NSNumber.class] ? [value boolValue] : YES;
}

void NeoTouchSetHidesControlsWithController(NSString* console, BOOL hide) {
  if (!NeoTouchLayoutKeyIsValid(console)) return;
  [NSUserDefaults.standardUserDefaults setBool:hide forKey:NeoTouchHideWithControllerDefaultsKey(console)];
  dispatch_block_t post = ^{
    [NSNotificationCenter.defaultCenter postNotificationName:NeoTouchControllerPreferenceDidChangeNotification
                                                      object:nil
                                                    userInfo:@{@"console": console, @"hide": @(hide)}];
  };
  if (NSThread.isMainThread) post();
  else dispatch_async(dispatch_get_main_queue(), post);
}

static NSError* NeoTouchStoreError(NSString* message) {
  return [NSError errorWithDomain:@"NeoTouchLayoutStore" code:1 userInfo:@{NSLocalizedDescriptionKey: message}];
}

static BOOL NeoTouchOrientationIsValid(NSString* orientation) {
  return [orientation isEqualToString:NeoTouchLayoutOrientationLandscape] ||
         [orientation isEqualToString:NeoTouchLayoutOrientationPortrait];
}

@implementation NeoTouchLayoutStore

+ (NSString*)defaultDirectory {
  NSURL* support = [NSFileManager.defaultManager URLsForDirectory:NSApplicationSupportDirectory
                                                        inDomains:NSUserDomainMask].firstObject;
  NSString* base = support.path ?: [NSHomeDirectory() stringByAppendingPathComponent:@"Library/Application Support"];
  return [[base stringByAppendingPathComponent:@"NeoStation"] stringByAppendingPathComponent:@"TouchControls"];
}

+ (NeoTouchLayoutStore*)sharedStore {
  static NeoTouchLayoutStore* store;
  static dispatch_once_t once;
  dispatch_once(&once, ^{ store = [[NeoTouchLayoutStore alloc] initWithDirectory:self.defaultDirectory]; });
  return store;
}

- (instancetype)initWithDirectory:(NSString*)directory {
  self = [super init];
  if (self) _directory = [directory copy];
  return self;
}

- (NSString*)pathForKey:(NSString*)key {
  return [self.directory stringByAppendingPathComponent:[key stringByAppendingPathExtension:@"json"]];
}

/// The file as mutable containers; an empty document when absent. A file that
/// is not a JSON object is set aside once (never silently overwritten).
- (NSMutableDictionary*)documentForKey:(NSString*)key {
  NSString* path = [self pathForKey:key];
  NSData* data = [NSData dataWithContentsOfFile:path];
  if (data.length) {
    id decoded = [NSJSONSerialization JSONObjectWithData:data options:NSJSONReadingMutableContainers error:nil];
    if ([decoded isKindOfClass:NSMutableDictionary.class]) return decoded;
    NSString* aside = [path stringByAppendingFormat:@".unreadable-%lld", (long long)NSDate.date.timeIntervalSince1970];
    [NSFileManager.defaultManager moveItemAtPath:path toPath:aside error:nil];
    NSLog(@"[NeoTouchLayout] Unreadable layout file set aside: %@", aside.lastPathComponent);
  }
  return [NSMutableDictionary dictionary];
}

- (BOOL)writeDocument:(NSMutableDictionary*)document key:(NSString*)key error:(NSError**)error {
  document[@"format"] = @(kNeoTouchLayoutFormat);
  NSError* failure = nil;
  if (![NSFileManager.defaultManager createDirectoryAtPath:self.directory withIntermediateDirectories:YES
                                                attributes:nil error:&failure]) {
    if (error) *error = failure;
    return NO;
  }
  NSData* data = [NSJSONSerialization dataWithJSONObject:document
                                                 options:NSJSONWritingPrettyPrinted | NSJSONWritingSortedKeys
                                                   error:&failure];
  if (!data || ![data writeToFile:[self pathForKey:key] options:NSDataWritingAtomic error:&failure]) {
    if (error) *error = failure;
    return NO;
  }
  NSDictionary* info = @{@"key": key};
  dispatch_block_t post = ^{
    [NSNotificationCenter.defaultCenter postNotificationName:NeoTouchLayoutStoreDidChangeNotification
                                                      object:self
                                                    userInfo:info];
  };
  if (NSThread.isMainThread) post();
  else dispatch_async(dispatch_get_main_queue(), post);
  return YES;
}

static NSMutableDictionary* NeoTouchChild(NSMutableDictionary* parent, NSString* key, BOOL create) {
  id value = parent[key];
  if ([value isKindOfClass:NSMutableDictionary.class]) return value;
  if (!create) return nil;
  NSMutableDictionary* child = [NSMutableDictionary dictionary];
  parent[key] = child;
  return child;
}

- (NSMutableDictionary*)scopeIn:(NSMutableDictionary*)document game:(NSString*)game create:(BOOL)create {
  if (!game) return NeoTouchChild(document, @"general", create);
  NSMutableDictionary* games = NeoTouchChild(document, @"games", create);
  return games ? NeoTouchChild(games, game, create) : nil;
}

- (NeoTouchLayout*)layoutForKey:(NSString*)key orientation:(NSString*)orientation game:(NSString*)game {
  if (!NeoTouchLayoutKeyIsValid(key) || !NeoTouchOrientationIsValid(orientation)) return nil;
  NSString* gameKey = NeoTouchLayoutGameKey(game);
  if (game && !gameKey) return nil;
  NSMutableDictionary* scope = [self scopeIn:[self documentForKey:key] game:gameKey create:NO];
  NSDictionary* entry = scope[orientation];
  if (![entry isKindOfClass:NSDictionary.class]) return nil;
  return [NeoTouchLayout layoutFromDictionary:entry];
}

- (NeoTouchLayout*)effectiveLayoutForKey:(NSString*)key orientation:(NSString*)orientation game:(NSString*)game
                            gameSpecific:(BOOL*)gameSpecific {
  if (gameSpecific) *gameSpecific = NO;
  if (NeoTouchLayoutGameKey(game)) {
    NeoTouchLayout* layout = [self layoutForKey:key orientation:orientation game:game];
    if (layout) {
      if (gameSpecific) *gameSpecific = YES;
      return layout;
    }
  }
  return [self layoutForKey:key orientation:orientation game:nil] ?: [NeoTouchLayout new];
}

- (BOOL)saveLayout:(NeoTouchLayout*)layout forKey:(NSString*)key orientation:(NSString*)orientation
              game:(NSString*)game error:(NSError**)error {
  NSString* gameKey = NeoTouchLayoutGameKey(game);
  if (!NeoTouchLayoutKeyIsValid(key) || !NeoTouchOrientationIsValid(orientation) || (game && !gameKey) || !layout) {
    if (error) *error = NeoTouchStoreError(@"Invalid touch layout scope.");
    return NO;
  }
  if (!gameKey && layout.isEmpty) return [self removeLayoutForKey:key orientation:orientation game:nil error:error];
  NSMutableDictionary* document = [self documentForKey:key];
  NSMutableDictionary* scope = [self scopeIn:document game:gameKey create:YES];
  NSMutableDictionary* entry = NeoTouchChild(scope, orientation, YES);
  // Unknown keys of the entry survive; the controls are replaced as a whole.
  entry[@"elements"] = [layout dictionaryRepresentation][@"elements"];
  return [self writeDocument:document key:key error:error];
}

- (BOOL)removeLayoutForKey:(NSString*)key orientation:(NSString*)orientation game:(NSString*)game
                     error:(NSError**)error {
  NSString* gameKey = NeoTouchLayoutGameKey(game);
  if (!NeoTouchLayoutKeyIsValid(key) || !NeoTouchOrientationIsValid(orientation) || (game && !gameKey)) {
    if (error) *error = NeoTouchStoreError(@"Invalid touch layout scope.");
    return NO;
  }
  if (![NSFileManager.defaultManager fileExistsAtPath:[self pathForKey:key]]) return YES;
  NSMutableDictionary* document = [self documentForKey:key];
  NSMutableDictionary* scope = [self scopeIn:document game:gameKey create:NO];
  if (!scope[orientation]) return YES;
  [scope removeObjectForKey:orientation];
  if (gameKey && scope.count == 0) [NeoTouchChild(document, @"games", NO) removeObjectForKey:gameKey];
  return [self writeDocument:document key:key error:error];
}

- (BOOL)hasGameLayoutForKey:(NSString*)key game:(NSString*)game {
  NSString* gameKey = NeoTouchLayoutGameKey(game);
  if (!NeoTouchLayoutKeyIsValid(key) || !gameKey) return NO;
  NSMutableDictionary* scope = [self scopeIn:[self documentForKey:key] game:gameKey create:NO];
  for (NSString* orientation in @[NeoTouchLayoutOrientationLandscape, NeoTouchLayoutOrientationPortrait])
    if ([scope[orientation] isKindOfClass:NSDictionary.class]) return YES;
  return NO;
}

- (BOOL)hasCustomLayoutForKey:(NSString*)key {
  if (!NeoTouchLayoutKeyIsValid(key)) return NO;
  NSMutableDictionary* document = [self documentForKey:key];
  NSMutableDictionary* general = NeoTouchChild(document, @"general", NO);
  for (NSString* orientation in @[NeoTouchLayoutOrientationLandscape, NeoTouchLayoutOrientationPortrait])
    if (![[NeoTouchLayout layoutFromDictionary:general[orientation]] isEmpty]) return YES;
  NSMutableDictionary* games = NeoTouchChild(document, @"games", NO);
  return games.count > 0;
}

@end

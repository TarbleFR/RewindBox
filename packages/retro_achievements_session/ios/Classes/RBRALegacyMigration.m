#import "RBRALegacyMigration.h"

static NSString *RBRALegacyString(id value) {
  return [value isKindOfClass:NSString.class] ? [value copy] : @"";
}

static BOOL RBRALegacyFlag(id value) {
  if ([value isKindOfClass:NSNumber.class]) return [value boolValue];
  NSString *text = [[RBRALegacyString(value)
    stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet] lowercaseString];
  return [@[@"true", @"yes", @"1", @"on"] containsObject:text];
}

@implementation RBRALegacyMigration
+ (NSDictionary<NSString *, NSString *> *)achievementValuesAtPath:(NSString *)path error:(NSError **)error {
  NSFileManager *files = NSFileManager.defaultManager;
  NSError *readError = nil;
  if (error) *error = nil;
  NSDictionary *attributes = [files attributesOfItemAtPath:path error:&readError];
  if (!attributes) {
    if ([readError.domain isEqualToString:NSCocoaErrorDomain] &&
        (readError.code == NSFileNoSuchFileError || readError.code == NSFileReadNoSuchFileError)) {
      return @{};
    }
    if (error) *error = readError;
    return nil;
  }
  if (![attributes[NSFileType] isEqualToString:NSFileTypeRegular] ||
      [attributes[NSFileSize] unsignedLongLongValue] > 4 * 1024 * 1024) {
    if (error) *error = [NSError errorWithDomain:NSCocoaErrorDomain code:NSFileReadCorruptFileError userInfo:nil];
    return nil;
  }
  NSString *contents = [NSString stringWithContentsOfFile:path encoding:NSUTF8StringEncoding error:error];
  if (!contents) return nil;
  NSMutableDictionary *values = [NSMutableDictionary dictionary];
  __block BOOL achievements = NO;
  [contents enumerateLinesUsingBlock:^(NSString *line, BOOL *stop) {
    NSString *trimmed = [line stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    if ([trimmed hasPrefix:@"\uFEFF"]) trimmed = [trimmed substringFromIndex:1];
    if (!trimmed.length || [trimmed hasPrefix:@";"] || [trimmed hasPrefix:@"#"]) return;
    if ([trimmed hasPrefix:@"["]) {
      // Every new header closes the previous section, including malformed
      // headers. Never mistake another section's credentials for RA values.
      achievements = NO;
      NSRange close = [trimmed rangeOfString:@"]"];
      if (close.location == NSNotFound) return;
      NSString *suffix = [[trimmed substringFromIndex:close.location + 1]
        stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet];
      if (suffix.length && ![suffix hasPrefix:@";"] && ![suffix hasPrefix:@"#"]) return;
      NSString *section = [[trimmed substringWithRange:NSMakeRange(1, close.location - 1)]
        stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet];
      achievements = [section caseInsensitiveCompare:@"Achievements"] == NSOrderedSame;
      return;
    }
    if (!achievements) return;
    NSRange equals = [trimmed rangeOfString:@"="];
    if (equals.location == NSNotFound) return;
    NSString *key = [[[trimmed substringToIndex:equals.location]
      stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet] lowercaseString];
    NSString *value = [[trimmed substringFromIndex:equals.location + 1]
      stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet];
    if (value.length >= 2 && [value hasPrefix:@"\""] && [value hasSuffix:@"\""]) {
      value = [value substringWithRange:NSMakeRange(1, value.length - 2)];
    }
    if (key.length) values[key] = value;
  }];
  return [values copy];
}

+ (NSArray<NSDictionary *> *)candidatesWithLibretro:(NSDictionary *)libretro
                                  libretroEnabled:(id)libretroEnabled
                                          dolphin:(NSDictionary *)dolphin
                                    dolphinValues:(NSDictionary *)dolphinValues
                                     armsx2Values:(NSDictionary *)armsx2Values
                                    armsx2Secrets:(NSDictionary *)armsx2Secrets {
  NSMutableArray<NSDictionary *> *inputs = [NSMutableArray array];
  void (^add)(NSString *, NSDictionary *, BOOL, BOOL) = ^(NSString *source, NSDictionary *credentials, BOOL enabled, BOOL hardcore) {
    NSString *username = [RBRALegacyString(credentials[@"username"])
      stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    NSString *token = RBRALegacyString(credentials[@"token"]);
    if (!username.length || !token.length) return;
    [inputs addObject:@{@"username": username, @"token": token, @"enabled": @(enabled),
                       @"hardcore": @(hardcore), @"sources": @[source]}];
  };
  // Missing defaults are not an explicit opt-in. In particular libretro's old
  // enabled getter defaulted to YES even on installations that never used RA.
  add(@"libretro", libretro ?: @{}, RBRALegacyFlag(libretroEnabled), NO);
  NSDictionary *dolphinAccount = dolphin ?: @{@"username": RBRALegacyString(dolphinValues[@"username"]),
                                               @"token": RBRALegacyString(dolphinValues[@"apitoken"])};
  add(@"Dolphin", dolphinAccount, RBRALegacyFlag(dolphinValues[@"enabled"]),
      RBRALegacyFlag(dolphinValues[@"hardcoreenabled"]));
  NSString *dolphinINIUser = RBRALegacyString(dolphinValues[@"username"]);
  if (dolphin && dolphinINIUser.length &&
      [dolphinINIUser caseInsensitiveCompare:RBRALegacyString(dolphin[@"username"])] != NSOrderedSame) {
    add(@"Dolphin", @{@"username": dolphinINIUser, @"token": RBRALegacyString(dolphinValues[@"apitoken"])},
        RBRALegacyFlag(dolphinValues[@"enabled"]), RBRALegacyFlag(dolphinValues[@"hardcoreenabled"]));
  }
  NSString *armsToken = RBRALegacyString(armsx2Secrets[@"token"]);
  if (!armsToken.length) armsToken = RBRALegacyString(armsx2Values[@"token"]);
  add(@"ARMSX2", @{@"username": RBRALegacyString(armsx2Values[@"username"]), @"token": armsToken},
      RBRALegacyFlag(armsx2Values[@"enabled"]), RBRALegacyFlag(armsx2Values[@"challengemode"]));

  NSMutableArray<NSDictionary *> *merged = [NSMutableArray array];
  for (NSDictionary *candidate in inputs) {
    NSUInteger index = [merged indexOfObjectPassingTest:^BOOL(NSDictionary *previous, NSUInteger idx, BOOL *stop) {
      return [previous[@"username"] caseInsensitiveCompare:candidate[@"username"]] == NSOrderedSame &&
        [previous[@"enabled"] isEqual:candidate[@"enabled"]] &&
        [previous[@"hardcore"] isEqual:candidate[@"hardcore"]];
    }];
    if (index == NSNotFound) {
      [merged addObject:candidate];
    } else {
      NSMutableDictionary *combined = [merged[index] mutableCopy];
      combined[@"sources"] = [combined[@"sources"] arrayByAddingObjectsFromArray:candidate[@"sources"]];
      merged[index] = [combined copy];
    }
  }
  // Different identities OR different policies require a choice in the main
  // RA tab. There is no arbitrary priority between emulator accounts/settings.
  return [merged copy];
}
@end

// SPDX-License-Identifier: GPL-3.0-or-later
#import "NeoTextureSupport.h"
#include <sys/mount.h>
#include <sys/stat.h>

NSString *const NeoTexManifestName = @"NeoStation-pack.json";

NSString *NeoTexString(id value) { return [value isKindOfClass:NSString.class] ? value : @""; }

BOOL NeoTexSafeToken(id value, NSUInteger limit) {
  NSString *s = NeoTexString(value);
  if (!s.length || s.length > limit || [s isEqualToString:@"."] || [s isEqualToString:@".."]) return NO;
  static NSCharacterSet *invalid;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    invalid = [NSCharacterSet characterSetWithCharactersInString:@"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"].invertedSet;
  });
  return [s rangeOfCharacterFromSet:invalid].location == NSNotFound;
}

BOOL NeoTexSafeRelativePath(id value, NSUInteger limit, NSUInteger components) {
  NSString *s = NeoTexString(value);
  if (!s.length || s.length > limit || [s hasPrefix:@"/"] || [s hasSuffix:@"/"]) return NO;
  static NSCharacterSet *invalid;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    NSMutableCharacterSet *set = [NSMutableCharacterSet controlCharacterSet];
    [set addCharactersInString:@"\\:*?\"<>|"];
    invalid = set;
  });
  if ([s rangeOfCharacterFromSet:invalid].location != NSNotFound) return NO;
  NSArray *parts = [s componentsSeparatedByString:@"/"];
  if (parts.count > components) return NO;
  for (NSString *part in parts)
    if (!part.length || [part isEqualToString:@"."] || [part isEqualToString:@".."] || [part hasPrefix:@" "] || [part hasSuffix:@" "]) return NO;
  return YES;
}

BOOL NeoTexHTTPS(id value) {
  NSString *s = NeoTexString(value);
  if (!s.length || s.length > 2048) return NO;
  NSURL *url = [NSURL URLWithString:s];
  return [url.scheme.lowercaseString isEqualToString:@"https"] && url.host.length && !url.user.length && !url.password.length;
}

BOOL NeoTexSHA256(id value) {
  NSString *s = NeoTexString(value);
  static NSCharacterSet *invalid;
  static dispatch_once_t once;
  dispatch_once(&once, ^{ invalid = [NSCharacterSet characterSetWithCharactersInString:@"0123456789abcdef"].invertedSet; });
  return s.length == 64 && [s rangeOfCharacterFromSet:invalid].location == NSNotFound;
}

BOOL NeoTexPositive(id value, unsigned long long limit) {
  if (![value isKindOfClass:NSNumber.class]) return NO;
  const double d = [value doubleValue];
  return d >= 1 && d == (double)[value unsignedLongLongValue] && [value unsignedLongLongValue] <= limit;
}

NSCharacterSet *NeoTexIdentityCharacters(void) {
  static NSCharacterSet *set;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    set = [NSCharacterSet characterSetWithCharactersInString:@"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_."];
  });
  return set;
}

NSString *NeoTexCanonicalSystem(id value) {
  NSString *s = NeoTexString(value).lowercaseString;
  if ([s isEqualToString:@"pspminis"]) return @"psp";
  if ([s isEqualToString:@"n3ds"] || [s isEqualToString:@"nintendo 3ds"]) return @"3ds";
  if ([s isEqualToString:@"gamecube"] || [s isEqualToString:@"ngc"]) return @"gc";
  return s;
}

NSString *NeoTexN64RomName(NSString *hex) {
  if (hex.length < 2 || hex.length > 40 || hex.length % 2) return nil;
  NSMutableString *name = [NSMutableString string];
  for (NSUInteger i = 0; i < hex.length; i += 2) {
    unsigned value = 0;
    NSScanner *scanner = [NSScanner scannerWithString:[hex substringWithRange:NSMakeRange(i, 2)]];
    if (![scanner scanHexInt:&value] || !scanner.isAtEnd || value < 0x20 || value > 0x7E) return nil;
    [name appendFormat:@"%c", (char)value];
  }
  // GLideN64 drops trailing spaces; the name is one folder below hires_texture.
  return NeoTexSafeRelativePath(name, 20, 1) && ![name hasPrefix:@"."] ? name : nil;
}

NSString *NeoTexEngineForSystem(NSString *system) {
  NSString *s = NeoTexCanonicalSystem(system);
  if ([s isEqualToString:@"ps2"]) return @"armsx2";
  if ([s isEqualToString:@"gc"] || [s isEqualToString:@"wii"]) return @"dolphin";
  if ([s isEqualToString:@"psp"]) return @"ppsspp";
  if ([s isEqualToString:@"3ds"]) return @"azahar";
  if ([s isEqualToString:@"n64"]) return @"mupen64plus";
  return nil;
}

NSDictionary *NeoTexTypedIdentities(id identities) {
  NSMutableDictionary *result = [NSMutableDictionary dictionary];
  if (![identities isKindOfClass:NSArray.class]) return result;
  for (NSDictionary *identity in identities) {
    if (![identity isKindOfClass:NSDictionary.class]) continue;
    NSString *type = NeoTexString(identity[@"type"]), *scheme = NeoTexString(identity[@"scheme"]);
    NSString *value = NeoTexString(identity[@"value"]).uppercaseString;
    if ([scheme isEqualToString:@"ps2-disc-serial"]) {
      value = [[[value stringByReplacingOccurrencesOfString:@"-" withString:@""]
                stringByReplacingOccurrencesOfString:@"_" withString:@""] stringByReplacingOccurrencesOfString:@"." withString:@""];
    }
    if (!type.length || !scheme.length || !value.length) continue;
    NSString *key = [NSString stringWithFormat:@"%@|%@", type, scheme];
    NSMutableSet *set = result[key] ?: [NSMutableSet set];
    [set addObject:value];
    result[key] = set;
  }
  return result;
}

NSSet *NeoTexRegions(id regions) {
  NSMutableSet *set = [NSMutableSet set];
  if (![regions isKindOfClass:NSArray.class]) return set;
  for (id region in regions) {
    NSString *s = NeoTexString(region).lowercaseString;
    if ([s isEqualToString:@"usa"] || [s isEqualToString:@"us"] || [s isEqualToString:@"ntsc-u"] || [s isEqualToString:@"north america"]) s = @"usa";
    else if ([s isEqualToString:@"europe"] || [s isEqualToString:@"eur"] || [s isEqualToString:@"pal"] || [s isEqualToString:@"eu"]) s = @"europe";
    else if ([s isEqualToString:@"japan"] || [s isEqualToString:@"jpn"] || [s isEqualToString:@"ntsc-j"] || [s isEqualToString:@"jp"]) s = @"japan";
    if (s.length) [set addObject:s];
  }
  // "World" packs declare compatibility with every region.
  if ([set containsObject:@"world"]) return [NSSet set];
  return set;
}

NSString *NeoTexFoldTitle(id value) {
  NSString *title = NeoTexString(value);
  if (!title.length) return @"";
  static NSRegularExpression *brackets;
  static dispatch_once_t once;
  dispatch_once(&once, ^{ brackets = [NSRegularExpression regularExpressionWithPattern:@"[\\(\\[][^\\)\\]]*[\\)\\]]" options:0 error:nil]; });
  title = [brackets stringByReplacingMatchesInString:title options:0 range:NSMakeRange(0, title.length) withTemplate:@" "];
  title = [title stringByFoldingWithOptions:NSDiacriticInsensitiveSearch | NSCaseInsensitiveSearch locale:[NSLocale localeWithLocaleIdentifier:@"en_US_POSIX"]].lowercaseString;
  NSMutableString *out = [NSMutableString string];
  BOOL space = NO;
  for (NSUInteger i = 0; i < title.length; i++) {
    unichar c = [title characterAtIndex:i];
    if ([[NSCharacterSet alphanumericCharacterSet] characterIsMember:c]) {
      if (space && out.length) [out appendString:@" "];
      [out appendFormat:@"%C", c];
      space = NO;
    } else {
      space = YES;
    }
  }
  return out;
}

NSData *NeoTexReadBounded(NSString *path, NSUInteger limit) {
  struct stat st;
  if (!path.length || lstat(path.fileSystemRepresentation, &st) != 0 || !S_ISREG(st.st_mode) || (unsigned long long)st.st_size > limit) return nil;
  NSData *data = [NSData dataWithContentsOfFile:path options:0 error:nil];
  return data.length <= limit ? data : nil;
}

BOOL NeoTexWriteAtomic(NSData *data, NSString *path, NSError **error) {
  if (!data) return NO;
  NSString *folder = path.stringByDeletingLastPathComponent;
  if (![NSFileManager.defaultManager createDirectoryAtPath:folder withIntermediateDirectories:YES attributes:nil error:error]) return NO;
  struct stat st;
  if (lstat(path.fileSystemRepresentation, &st) == 0 && !S_ISREG(st.st_mode)) return NO;
  return [data writeToFile:path options:NSDataWritingAtomic error:error];
}

NSData *NeoTexJSONData(id object) {
  return [NSJSONSerialization dataWithJSONObject:object options:NSJSONWritingSortedKeys | NSJSONWritingPrettyPrinted error:nil] ?: [NSData data];
}

NSDictionary *NeoTexJSONDictionary(NSData *data) {
  if (!data.length) return nil;
  id json = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
  return [json isKindOfClass:NSDictionary.class] ? json : nil;
}

@interface NeoTexDataRequest : NSObject <NSURLSessionDataDelegate>
@property(nonatomic) NSUInteger maximum;
@property(nonatomic, strong) NSMutableData *bytes;
@property(nonatomic, strong) NSError *failure;
@property(nonatomic, copy) void (^completion)(NSData *, NSError *);
@end

static NSError *FetchError(NSString *key, NSString *message) {
  return [NSError errorWithDomain:@"NeoTextureCatalog" code:5 userInfo:@{NSLocalizedDescriptionKey: message, @"key": key}];
}

@implementation NeoTexDataRequest
- (void)URLSession:(NSURLSession *)session dataTask:(NSURLSessionDataTask *)task didReceiveResponse:(NSURLResponse *)response
 completionHandler:(void (^)(NSURLSessionResponseDisposition))completionHandler {
  NSHTTPURLResponse *http = [response isKindOfClass:NSHTTPURLResponse.class] ? (NSHTTPURLResponse *)response : nil;
  NSString *type = [http valueForHTTPHeaderField:@"Content-Type"].lowercaseString ?: @"";
  if (!http || http.statusCode != 200) {
    self.failure = FetchError(@"catalogueUnavailable", [NSString stringWithFormat:@"HTTP %ld", (long)http.statusCode]);
  } else if ([type hasPrefix:@"text/html"]) {
    self.failure = FetchError(@"catalogueInvalid", @"The server returned a web page");
  } else if (response.expectedContentLength > 0 && (unsigned long long)response.expectedContentLength > self.maximum) {
    self.failure = FetchError(@"catalogueInvalid", @"Download is too large");
  }
  completionHandler(self.failure ? NSURLSessionResponseCancel : NSURLSessionResponseAllow);
}
- (void)URLSession:(NSURLSession *)session dataTask:(NSURLSessionDataTask *)task didReceiveData:(NSData *)data {
  if (data.length > self.maximum - self.bytes.length) {
    self.failure = FetchError(@"catalogueInvalid", @"Download is too large");
    [task cancel];
    return;
  }
  [self.bytes appendData:data];
}
- (void)URLSession:(NSURLSession *)session task:(NSURLSessionTask *)task willPerformHTTPRedirection:(NSHTTPURLResponse *)response
        newRequest:(NSURLRequest *)request completionHandler:(void (^)(NSURLRequest *))completionHandler {
  completionHandler([request.URL.scheme.lowercaseString isEqualToString:@"https"] ? request : nil);
}
- (void)URLSession:(NSURLSession *)session task:(NSURLSessionTask *)task didCompleteWithError:(NSError *)error {
  NSError *failure = self.failure ?: (error ? FetchError(@"catalogueUnavailable", error.localizedDescription) : nil);
  void (^completion)(NSData *, NSError *) = self.completion;
  self.completion = nil;
  if (completion) completion(failure ? nil : [self.bytes copy], failure);
  [session finishTasksAndInvalidate];
}
@end

void NeoTexFetchData(NSURL *url, NSUInteger maximum, void (^completion)(NSData *, NSError *)) {
  if (![url.scheme.lowercaseString isEqualToString:@"https"]) {
    completion(nil, FetchError(@"catalogueUnavailable", @"Only HTTPS is allowed"));
    return;
  }
  NeoTexDataRequest *request = [NeoTexDataRequest new];
  request.maximum = maximum;
  request.bytes = [NSMutableData data];
  request.completion = completion;
  NSURLSessionConfiguration *configuration = NSURLSessionConfiguration.ephemeralSessionConfiguration;
  configuration.timeoutIntervalForRequest = 30;
  configuration.timeoutIntervalForResource = 90;
  configuration.URLCache = nil;
  NSURLSession *session = [NSURLSession sessionWithConfiguration:configuration delegate:request delegateQueue:nil];
  NSMutableURLRequest *get = [NSMutableURLRequest requestWithURL:url];
  [get setValue:@"NeoStation-iOS" forHTTPHeaderField:@"User-Agent"];
  [[session dataTaskWithRequest:get] resume];
}

BOOL NeoTexNoLinksBelow(NSString *root, NSString *path) {
  NSString *base = root.stringByStandardizingPath, *target = path.stringByStandardizingPath;
  if (![target isEqualToString:base] && ![target hasPrefix:[base stringByAppendingString:@"/"]]) return NO;
  NSString *current = target;
  while (current.length >= base.length) {
    struct stat st;
    if (lstat(current.fileSystemRepresentation, &st) == 0 && S_ISLNK(st.st_mode)) return NO;
    if ([current isEqualToString:base]) return YES;
    current = current.stringByDeletingLastPathComponent;
  }
  return NO;
}

BOOL NeoTexEnsureDirectory(NSString *root, NSString *path) {
  if (!NeoTexNoLinksBelow(root, path)) return NO;
  BOOL directory = NO;
  if ([NSFileManager.defaultManager fileExistsAtPath:path isDirectory:&directory]) return directory;
  return [NSFileManager.defaultManager createDirectoryAtPath:path withIntermediateDirectories:YES attributes:nil error:nil] &&
         NeoTexNoLinksBelow(root, path);
}

unsigned long long NeoTexFreeBytes(NSString *path) {
  NSString *existing = path;
  while (existing.length > 1 && ![NSFileManager.defaultManager fileExistsAtPath:existing]) existing = existing.stringByDeletingLastPathComponent;
  NSURL *url = [NSURL fileURLWithPath:existing];
  NSNumber *important = nil;
  // Important-usage capacity counts space iOS can free from caches for the user.
  if ([url getResourceValue:&important forKey:NSURLVolumeAvailableCapacityForImportantUsageKey error:nil] && important.longLongValue > 0)
    return important.unsignedLongLongValue;
  struct statfs fs;
  if (statfs(existing.fileSystemRepresentation, &fs) == 0) return (unsigned long long)fs.f_bavail * fs.f_bsize;
  return 0;
}

NSString *NeoTexFormatBytes(unsigned long long bytes) {
  return [NSByteCountFormatter stringFromByteCount:(long long)bytes countStyle:NSByteCountFormatterCountStyleFile];
}

#pragma mark - Installed-pack registry

static NSString *RegistryOverride;

NSString *NeoTexRegistryPath(void) {
  @synchronized([NSFileManager class]) {
    if (RegistryOverride) return RegistryOverride;
  }
  NSString *support = NSSearchPathForDirectoriesInDomains(NSApplicationSupportDirectory, NSUserDomainMask, YES).firstObject ?: NSTemporaryDirectory();
  return [support stringByAppendingPathComponent:@"NeoStation/Textures/installed.json"];
}

void NeoTexSetRegistryPath(NSString *path) {
  @synchronized([NSFileManager class]) { RegistryOverride = [path copy]; }
}

static NSString *RegistryKey(NSString *engine, NSString *folder) { return [NSString stringWithFormat:@"%@:%@", engine, folder]; }

static NSObject *RegistryLock(void) {
  static NSObject *lock;
  static dispatch_once_t once;
  dispatch_once(&once, ^{ lock = [NSObject new]; });
  return lock;
}

NSDictionary *NeoTexRegistryEntry(NSString *engine, NSString *folder) {
  if (!engine.length || !folder.length) return nil;
  @synchronized(RegistryLock()) {
    NSDictionary *entries = NeoTexJSONDictionary(NeoTexReadBounded(NeoTexRegistryPath(), 4 << 20))[@"entries"];
    id entry = [entries isKindOfClass:NSDictionary.class] ? entries[RegistryKey(engine, folder)] : nil;
    return [entry isKindOfClass:NSDictionary.class] ? entry : nil;
  }
}

void NeoTexRegistrySet(NSString *engine, NSString *folder, NSDictionary *entry) {
  if (!engine.length || !folder.length) return;
  @synchronized(RegistryLock()) {
    NSString *path = NeoTexRegistryPath();
    NSMutableDictionary *document = [NeoTexJSONDictionary(NeoTexReadBounded(path, 4 << 20)) mutableCopy] ?: [NSMutableDictionary dictionary];
    NSMutableDictionary *entries = [document[@"entries"] isKindOfClass:NSDictionary.class] ? [document[@"entries"] mutableCopy] : [NSMutableDictionary dictionary];
    if (entry) entries[RegistryKey(engine, folder)] = entry;
    else [entries removeObjectForKey:RegistryKey(engine, folder)];
    // Bounded: a library of several thousand games still fits.
    while (entries.count > 8000) [entries removeObjectForKey:[entries.allKeys sortedArrayUsingSelector:@selector(compare:)].firstObject];
    document[@"entries"] = entries;
    document[@"schema"] = @1;
    NeoTexWriteAtomic(NeoTexJSONData(document), path, nil);
  }
}

// SPDX-License-Identifier: GPL-3.0-or-later
#import "NeoShaderCatalog.h"

#include <string>

#include "NeoShaderPaths.hpp"

static NSString *const kCatalogErrorDomain = @"NeoShaderCatalog";

static NSString *StringValue(id value) { return [value isKindOfClass:NSString.class] ? value : @""; }

static NSUInteger UnsignedValue(id value) {
  if (![value isKindOfClass:NSNumber.class]) return 0;
  const double number = [value doubleValue];
  return number > 0 && number < 1e12 ? (NSUInteger)number : 0;
}

static BOOL SafePath(NSString *path) {
  return path.length > 0 && neoshader::isSafeRelativePath(std::string(path.UTF8String ?: ""));
}

static BOOL HexDigest(NSString *value) {
  if (value.length != 64) return NO;
  NSCharacterSet *hex = [NSCharacterSet characterSetWithCharactersInString:@"0123456789abcdef"];
  return [value rangeOfCharacterFromSet:hex.invertedSet].location == NSNotFound;
}

/// An https URL made of `base` and the percent-encoded segments of `path`.
static NSURL *JoinURL(NSString *base, NSString *path) {
  if (base.length == 0 || !SafePath(path)) return nil;
  NSMutableArray<NSString *> *segments = [NSMutableArray array];
  NSCharacterSet *allowed = NSCharacterSet.URLPathAllowedCharacterSet;
  NSMutableCharacterSet *segmentAllowed = [allowed mutableCopy];
  [segmentAllowed removeCharactersInString:@"/;?#"];
  for (NSString *segment in [path componentsSeparatedByString:@"/"]) {
    NSString *encoded = [segment stringByAddingPercentEncodingWithAllowedCharacters:segmentAllowed];
    if (encoded == nil) return nil;
    [segments addObject:encoded];
  }
  NSURL *url = [NSURL URLWithString:[base stringByAppendingString:[segments componentsJoinedByString:@"/"]]];
  return [url.scheme isEqualToString:@"https"] && url.host.length > 0 ? url : nil;
}

@interface NeoShaderCatalogFile ()
@property(nonatomic, copy, readwrite) NSString *path;
@property(nonatomic, readwrite) unsigned long long size;
@property(nonatomic, copy, readwrite) NSString *sha256;
@end

@implementation NeoShaderCatalogFile

+ (instancetype)fileFromJSON:(id)json {
  if (![json isKindOfClass:NSArray.class] || [json count] != 3) return nil;
  NSString *path = StringValue(json[0]);
  NSString *sha = StringValue(json[2]);
  if (!SafePath(path) || !HexDigest(sha) || ![json[1] isKindOfClass:NSNumber.class]) return nil;
  const long long size = [json[1] longLongValue];
  if (size < 0 || size > (64LL << 20)) return nil;
  NeoShaderCatalogFile *file = [NeoShaderCatalogFile new];
  file.path = path;
  file.size = (unsigned long long)size;
  file.sha256 = sha;
  return file;
}

@end

@interface NeoShaderCatalogEntry ()
@property(nonatomic, copy, readwrite) NSString *identifier;
@property(nonatomic, copy, readwrite) NSString *name;
@property(nonatomic, copy, readwrite) NSString *category;
@property(nonatomic, copy, readwrite) NSString *family;
@property(nonatomic, copy, readwrite) NeoShaderFormat format;
@property(nonatomic, copy, readwrite) NSArray<NeoShaderCatalogFile *> *files;
@property(nonatomic, readwrite) unsigned long long downloadBytes;
@property(nonatomic, readwrite) BOOL bundled;
@property(nonatomic, readwrite) NSUInteger passCount;
@property(nonatomic, readwrite) NSUInteger textureCount;
@property(nonatomic, readwrite) NSUInteger parameterCount;
@property(nonatomic, readwrite) NSUInteger historyDepth;
@property(nonatomic, readwrite) NSUInteger feedbackCount;
@property(nonatomic, readwrite) NSUInteger floatFramebufferCount;
@property(nonatomic, readwrite) double samplesPerPixel;
@property(nonatomic, readwrite) BOOL samplesInLoop;
@property(nonatomic, readwrite) NeoShaderCostTier costTier;
@property(nonatomic, strong, readwrite, nullable) NeoShaderCatalogFile *preview;
@property(nonatomic, copy, readwrite) NSArray<NSString *> *authorMentions;
@property(nonatomic, copy, readwrite) NSString *licenseMention;
@property(nonatomic, copy, readwrite) NSString *validation;
@property(nonatomic, copy, readwrite) NSArray<NSDictionary<NSString *, id> *> *options;
@property(nonatomic, copy, readwrite) NSArray<NSString *> *notes;
@end

@implementation NeoShaderCatalogEntry
@end

@interface NeoShaderCatalog ()
@property(nonatomic, copy, readwrite) NSString *engine;
@property(nonatomic, copy, readwrite) NeoShaderFormat format;
@property(nonatomic, copy, readwrite) NSString *sourceName;
@property(nonatomic, copy, readwrite) NSString *sourceRepository;
@property(nonatomic, copy, readwrite) NSString *sourceRevision;
@property(nonatomic, copy, readwrite) NSString *rawBaseURL;
@property(nonatomic, copy, readwrite) NSString *previewSourceName;
@property(nonatomic, copy, readwrite) NSString *previewRevision;
@property(nonatomic, copy, readwrite) NSString *previewRawBaseURL;
@property(nonatomic, strong, readwrite, nullable) NeoShaderCatalogFile *previewReference;
@property(nonatomic, readwrite) NSUInteger previewScale;
@property(nonatomic, copy, readwrite) NSString *compilerDescription;
@property(nonatomic, copy, readwrite) NSArray<NSString *> *categories;
@property(nonatomic, copy, readwrite) NSArray<NeoShaderCatalogEntry *> *entries;
@property(nonatomic, copy) NSDictionary<NSString *, NeoShaderCatalogEntry *> *byIdentifier;
@end

static NeoShaderCostTier TierFromString(NSString *value) {
  if ([value isEqualToString:@"performance"]) return NeoShaderCostTierPerformance;
  if ([value isEqualToString:@"balanced"]) return NeoShaderCostTierBalanced;
  if ([value isEqualToString:@"quality"]) return NeoShaderCostTierQuality;
  return NeoShaderCostTierUnknown;
}

static NSArray<NSString *> *StringArray(id value, NSUInteger limit) {
  NSMutableArray<NSString *> *strings = [NSMutableArray array];
  if (![value isKindOfClass:NSArray.class]) return strings;
  for (id item in (NSArray *)value) {
    if ([item isKindOfClass:NSString.class] && strings.count < limit) [strings addObject:item];
  }
  return strings;
}

@implementation NeoShaderCatalog

+ (instancetype)catalogWithData:(NSData *)data error:(NSError **)error {
  id json = data.length > 0 ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
  if (![json isKindOfClass:NSDictionary.class] || ![json[@"schema"] isEqual:@1]) {
    if (error != NULL) *error = [NSError errorWithDomain:kCatalogErrorDomain code:1 userInfo:nil];
    return nil;
  }
  NeoShaderCatalog *catalog = [NeoShaderCatalog new];
  catalog.engine = StringValue(json[@"engine"]);
  catalog.format = StringValue(json[@"format"]);
  NSDictionary *source = [json[@"source"] isKindOfClass:NSDictionary.class] ? json[@"source"] : @{};
  catalog.sourceName = StringValue(source[@"name"]);
  catalog.sourceRepository = StringValue(source[@"repository"]);
  catalog.sourceRevision = StringValue(source[@"commit"]);
  catalog.rawBaseURL = StringValue(source[@"raw"]);
  if (catalog.rawBaseURL.length > 0 && (![catalog.rawBaseURL hasPrefix:@"https://"] || ![catalog.rawBaseURL hasSuffix:@"/"])) {
    if (error != NULL) *error = [NSError errorWithDomain:kCatalogErrorDomain code:2 userInfo:nil];
    return nil;
  }
  catalog.compilerDescription = StringValue(json[@"compiler"]);

  NSMutableArray<NeoShaderCatalogFile *> *files = [NSMutableArray array];
  for (id item in [json[@"files"] isKindOfClass:NSArray.class] ? json[@"files"] : @[]) {
    NeoShaderCatalogFile *file = [NeoShaderCatalogFile fileFromJSON:item];
    if (file == nil) {
      if (error != NULL) *error = [NSError errorWithDomain:kCatalogErrorDomain code:3 userInfo:nil];
      return nil;
    }
    [files addObject:file];
  }
  NSMutableArray<NeoShaderCatalogFile *> *previewFiles = [NSMutableArray array];
  NSDictionary *previews = [json[@"previews"] isKindOfClass:NSDictionary.class] ? json[@"previews"] : @{};
  catalog.previewSourceName = StringValue(previews[@"name"]);
  catalog.previewRevision = StringValue(previews[@"commit"]);
  catalog.previewRawBaseURL = StringValue(previews[@"raw"]);
  if (catalog.previewRawBaseURL.length > 0 && ![catalog.previewRawBaseURL hasPrefix:@"https://"]) {
    catalog.previewRawBaseURL = @"";
  }
  for (id item in [previews[@"files"] isKindOfClass:NSArray.class] ? previews[@"files"] : @[]) {
    NeoShaderCatalogFile *file = [NeoShaderCatalogFile fileFromJSON:item];
    if (file != nil) [previewFiles addObject:file];
  }
  const NSUInteger reference = UnsignedValue(previews[@"reference"]);
  if ([previews[@"reference"] isKindOfClass:NSNumber.class] && reference < previewFiles.count) {
    catalog.previewReference = previewFiles[reference];
  }
  catalog.previewScale = UnsignedValue(previews[@"scale"]);

  NSMutableArray<NeoShaderCatalogEntry *> *entries = [NSMutableArray array];
  NSMutableDictionary<NSString *, NeoShaderCatalogEntry *> *byIdentifier = [NSMutableDictionary dictionary];
  NSMutableOrderedSet<NSString *> *categories = [NSMutableOrderedSet orderedSet];
  for (NSString *category in StringArray(json[@"categories"], 64)) [categories addObject:category];
  for (id item in [json[@"entries"] isKindOfClass:NSArray.class] ? json[@"entries"] : @[]) {
    if (![item isKindOfClass:NSDictionary.class]) continue;
    NSDictionary *value = item;
    NeoShaderCatalogEntry *entry = [NeoShaderCatalogEntry new];
    entry.identifier = StringValue(value[@"id"]);
    entry.name = StringValue(value[@"name"]);
    entry.category = StringValue(value[@"category"]);
    entry.family = StringValue(value[@"family"]);
    entry.format = StringValue(value[@"format"]).length > 0 ? StringValue(value[@"format"]) : catalog.format;
    if (entry.identifier.length == 0 || entry.name.length == 0 || entry.category.length == 0 ||
        byIdentifier[entry.identifier] != nil) {
      continue;
    }
    NSMutableArray<NeoShaderCatalogFile *> *entryFiles = [NSMutableArray array];
    BOOL valid = YES;
    unsigned long long bytes = 0;
    for (id index in [value[@"files"] isKindOfClass:NSArray.class] ? value[@"files"] : @[]) {
      if (![index isKindOfClass:NSNumber.class] || [index integerValue] < 0 ||
          (NSUInteger)[index integerValue] >= files.count) {
        valid = NO;
        break;
      }
      NeoShaderCatalogFile *file = files[(NSUInteger)[index integerValue]];
      [entryFiles addObject:file];
      bytes += file.size;
    }
    entry.bundled = [value[@"bundled"] boolValue];
    if (!valid || (!entry.bundled && entryFiles.count == 0)) continue;
    entry.files = entryFiles;
    entry.downloadBytes = entry.bundled ? 0 : bytes;
    entry.passCount = UnsignedValue(value[@"passes"]);
    entry.textureCount = UnsignedValue(value[@"luts"]);
    entry.parameterCount = UnsignedValue(value[@"parameters"]);
    entry.historyDepth = UnsignedValue(value[@"history"]);
    entry.feedbackCount = UnsignedValue(value[@"feedback"]);
    entry.floatFramebufferCount = UnsignedValue(value[@"floatPasses"]);
    NSDictionary *cost = [value[@"cost"] isKindOfClass:NSDictionary.class] ? value[@"cost"] : @{};
    entry.samplesPerPixel = [cost[@"samples"] isKindOfClass:NSNumber.class] ? [cost[@"samples"] doubleValue] : 0;
    entry.samplesInLoop = [cost[@"loop"] boolValue];
    entry.costTier = TierFromString(StringValue(cost[@"tier"]));
    if ([value[@"preview"] isKindOfClass:NSNumber.class] && [value[@"preview"] integerValue] >= 0 &&
        (NSUInteger)[value[@"preview"] integerValue] < previewFiles.count) {
      entry.preview = previewFiles[(NSUInteger)[value[@"preview"] integerValue]];
    }
    entry.authorMentions = StringArray(value[@"mentions"], 8);
    entry.licenseMention = StringValue(value[@"license"]);
    entry.validation = StringValue(value[@"validation"]);
    NSMutableArray<NSDictionary *> *options = [NSMutableArray array];
    for (id option in [value[@"options"] isKindOfClass:NSArray.class] ? value[@"options"] : @[]) {
      if ([option isKindOfClass:NSDictionary.class]) [options addObject:option];
    }
    entry.options = options;
    entry.notes = StringArray(value[@"notes"], 16);
    [entries addObject:entry];
    byIdentifier[entry.identifier] = entry;
    [categories addObject:entry.category];
  }
  catalog.entries = entries;
  catalog.byIdentifier = byIdentifier;
  catalog.categories = categories.array;
  return catalog;
}

- (NeoShaderCatalogEntry *)entryWithIdentifier:(NSString *)identifier {
  return [identifier isKindOfClass:NSString.class] ? self.byIdentifier[identifier] : nil;
}

- (NSArray<NeoShaderCatalogEntry *> *)entriesInCategory:(NSString *)category {
  NSMutableArray<NeoShaderCatalogEntry *> *result = [NSMutableArray array];
  for (NeoShaderCatalogEntry *entry in self.entries) {
    if ([entry.category isEqualToString:category]) [result addObject:entry];
  }
  return result;
}

- (NSArray<NeoShaderCatalogEntry *> *)entriesMatching:(NSString *)query {
  NSString *needle = [query stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
  if (needle.length == 0) return self.entries;
  NSMutableArray<NeoShaderCatalogEntry *> *result = [NSMutableArray array];
  const NSStringCompareOptions options = NSCaseInsensitiveSearch | NSDiacriticInsensitiveSearch;
  for (NeoShaderCatalogEntry *entry in self.entries) {
    if ([entry.name rangeOfString:needle options:options].location != NSNotFound ||
        [entry.family rangeOfString:needle options:options].location != NSNotFound ||
        [entry.identifier rangeOfString:needle options:options].location != NSNotFound) {
      [result addObject:entry];
    }
  }
  return result;
}

- (NSURL *)downloadURLForFile:(NeoShaderCatalogFile *)file {
  return JoinURL(self.rawBaseURL, file.path);
}

- (NSURL *)previewURLForFile:(NeoShaderCatalogFile *)file {
  return JoinURL(self.previewRawBaseURL, file.path);
}

@end

@implementation NeoShaderCatalogManager {
  NSMutableDictionary<NSString *, NeoShaderCatalog *> *_catalogs;
  NSMutableDictionary<NSString *, NSArray *> *_diagnostics;
  NSString *_directory;
  NSLock *_lock;
}

+ (instancetype)sharedManager {
  static NeoShaderCatalogManager *manager;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    manager = [NeoShaderCatalogManager new];
  });
  return manager;
}

- (instancetype)init {
  self = [super init];
  if (self) {
    _catalogs = [NSMutableDictionary dictionary];
    _diagnostics = [NSMutableDictionary dictionary];
    _lock = [NSLock new];
  }
  return self;
}

- (void)setCatalogDirectory:(NSString *)directory {
  [_lock lock];
  _directory = [directory copy];
  [_catalogs removeAllObjects];
  [_diagnostics removeAllObjects];
  [_lock unlock];
}

/// The pod's resources are copied either into its framework or into the
/// application bundle, depending on how CocoaPods links it.
- (NSString *)pathForResource:(NSString *)name {
  if (_directory.length > 0) return [_directory stringByAppendingPathComponent:[name stringByAppendingString:@".json"]];
  for (NSBundle *bundle in @[ [NSBundle bundleForClass:NeoShaderCatalogManager.class], NSBundle.mainBundle ]) {
    NSString *path = [bundle pathForResource:name ofType:@"json"];
    if (path.length > 0) return path;
  }
  return nil;
}

static NSString *ResourceName(NSString *engine, BOOL diagnostics) {
  NSString *base = [engine isEqualToString:@"dolphin"] ? @"dolphin-catalog" : @"slang-catalog";
  return diagnostics ? [base stringByAppendingString:@"-diagnostics"] : base;
}

- (NeoShaderCatalog *)catalogForEngine:(NSString *)engine {
  if (![engine isKindOfClass:NSString.class]) return nil;
  [_lock lock];
  NeoShaderCatalog *catalog = _catalogs[engine];
  if (catalog == nil) {
    NSString *path = [self pathForResource:ResourceName(engine, NO)];
    NSData *data = path != nil ? [NSData dataWithContentsOfFile:path options:NSDataReadingMappedIfSafe error:nil] : nil;
    NSError *error = nil;
    catalog = data != nil ? [NeoShaderCatalog catalogWithData:data error:&error] : nil;
    if (catalog == nil) NSLog(@"[ShaderKit] catalog %@ unavailable (%@)", engine, error);
    if (catalog != nil) _catalogs[engine] = catalog;
  }
  [_lock unlock];
  return catalog;
}

- (NSArray<NSDictionary<NSString *, NSString *> *> *)diagnosticsForEngine:(NSString *)engine {
  if (![engine isKindOfClass:NSString.class]) return @[];
  [_lock lock];
  NSArray *list = _diagnostics[engine];
  if (list == nil) {
    NSMutableArray *parsed = [NSMutableArray array];
    NSString *path = [self pathForResource:ResourceName(engine, YES)];
    NSData *data = path != nil ? [NSData dataWithContentsOfFile:path] : nil;
    id json = data != nil ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
    for (id item in [json isKindOfClass:NSDictionary.class] && [json[@"excluded"] isKindOfClass:NSArray.class]
                        ? json[@"excluded"]
                        : @[]) {
      if (![item isKindOfClass:NSArray.class] || [item count] < 2) continue;
      [parsed addObject:@{
        @"identifier" : StringValue(item[0]),
        @"code" : StringValue(item[1]),
        @"detail" : [item count] > 2 ? StringValue(item[2]) : @"",
      }];
    }
    list = parsed;
    _diagnostics[engine] = list;
  }
  [_lock unlock];
  return list;
}

@end

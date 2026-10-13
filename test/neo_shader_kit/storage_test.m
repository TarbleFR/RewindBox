// SPDX-License-Identifier: GPL-3.0-or-later
// Behaviour tests of the shader kit's storage (NeoShaderStorage.m) and
// catalog parsing on macOS: verified downloads served by a fake network,
// shared files, removal, refusals (hash, size, HTTP, network, busy,
// cancelled, too large), previews, favourites, profiles and the storage
// report. With RESOURCES_DIRECTORY, the catalog the application bundles
// (slang-catalog.json and its diagnostics) is read through the catalog
// manager the in-game menu uses. No Metal involved.
//
//   neoshader-kit-tests FIXTURES_DIRECTORY [RESOURCES_DIRECTORY]
#import <CommonCrypto/CommonDigest.h>
#include <math.h>
#import <Foundation/Foundation.h>

#import "NeoDolphinShader.h"
#import "NeoShaderCatalog.h"
#import "NeoShaderStorage.h"

static int gChecks = 0;
static int gFailures = 0;

#define CHECK(condition, ...)                                     \
  do {                                                            \
    gChecks++;                                                    \
    if (!(condition)) {                                           \
      gFailures++;                                                \
      fprintf(stderr, "FAILED %s:%d: ", __FILE__, __LINE__);      \
      fprintf(stderr, __VA_ARGS__);                               \
      fprintf(stderr, "\n");                                      \
    }                                                             \
  } while (0)

static NSString *const kRevision = @"0123456789abcdef0123456789abcdef01234567";
static NSString *const kBase = @"https://shaders.invalid/repo/";
static NSString *const kPreviewBase = @"https://previews.invalid/repo/";

static NSString *SHA256Hex(NSData *data) {
  unsigned char digest[CC_SHA256_DIGEST_LENGTH];
  CC_SHA256(data.bytes, (CC_LONG)data.length, digest);
  NSMutableString *hex = [NSMutableString string];
  for (int index = 0; index < CC_SHA256_DIGEST_LENGTH; index++) [hex appendFormat:@"%02x", digest[index]];
  return hex;
}

/// Runs the main run loop until `done` or 10 seconds.
static BOOL Wait(BOOL (^done)(void)) {
  NSDate *limit = [NSDate dateWithTimeIntervalSinceNow:10];
  while (!done() && [limit timeIntervalSinceNow] > 0) {
    [[NSRunLoop currentRunLoop] runMode:NSDefaultRunLoopMode beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.01]];
  }
  return done();
}

/// Fake network: serves fixture files by URL path, counts requests and can
/// corrupt, shorten, refuse, fail or delay a path.
@interface FakeNetwork : NSObject
@property(nonatomic, copy) NSString *fixtures;
@property(nonatomic, strong) NSMutableDictionary<NSString *, NSNumber *> *requests;
@property(nonatomic, strong) NSMutableDictionary<NSString *, NSString *> *faults;  // path -> corrupt|short|404|error|slow
- (NeoShaderDataLoader)loader;
- (NSUInteger)requestsFor:(NSString *)path;
@end

@implementation FakeNetwork

- (instancetype)init {
  self = [super init];
  if (self) {
    _requests = [NSMutableDictionary dictionary];
    _faults = [NSMutableDictionary dictionary];
  }
  return self;
}

- (NSUInteger)requestsFor:(NSString *)path {
  @synchronized(self) {
    return self.requests[path].unsignedIntegerValue;
  }
}

- (NeoShaderDataLoader)loader {
  __weak FakeNetwork *weakSelf = self;
  return ^(NSURL *url, void (^completion)(NSData *, NSInteger, NSError *)) {
    FakeNetwork *network = weakSelf;
    NSString *absolute = url.absoluteString;
    NSString *path = nil;
    if ([absolute hasPrefix:kBase]) path = [absolute substringFromIndex:kBase.length];
    if ([absolute hasPrefix:kPreviewBase]) path = [@"previews/" stringByAppendingString:[absolute substringFromIndex:kPreviewBase.length]];
    path = path.stringByRemovingPercentEncoding;
    NSString *fault = nil;
    @synchronized(network) {
      if (path != nil) network.requests[path] = @(network.requests[path].unsignedIntegerValue + 1);
      fault = path != nil ? network.faults[path] : nil;
    }
    NSData *data = path != nil ? [NSData dataWithContentsOfFile:[network.fixtures stringByAppendingPathComponent:path]] : nil;
    const double delay = [fault isEqualToString:@"slow"] ? 0.5 : 0.0;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(delay * NSEC_PER_SEC)),
                   dispatch_get_global_queue(QOS_CLASS_DEFAULT, 0), ^{
                     if (data == nil || [fault isEqualToString:@"404"]) {
                       completion([NSData data], 404, nil);
                     } else if ([fault isEqualToString:@"error"]) {
                       completion(nil, 0, [NSError errorWithDomain:NSURLErrorDomain code:NSURLErrorNotConnectedToInternet userInfo:nil]);
                     } else if ([fault isEqualToString:@"corrupt"]) {
                       NSMutableData *changed = [data mutableCopy];
                       ((uint8_t *)changed.mutableBytes)[0] ^= 0xFF;
                       completion(changed, 200, nil);
                     } else if ([fault isEqualToString:@"short"]) {
                       completion([data subdataWithRange:NSMakeRange(0, data.length - 1)], 200, nil);
                     } else {
                       completion(data, 200, nil);
                     }
                   });
  };
}

@end

static NSArray *FileRecord(NSString *fixtures, NSString *path) {
  NSData *data = [NSData dataWithContentsOfFile:[fixtures stringByAppendingPathComponent:path]];
  return @[ path, @(data.length), SHA256Hex(data ?: [NSData data]) ];
}

/// Catalog of three entries over the fixture files: stock and stock-smooth
/// share stock.slang; lut has a texture; stock has a preview.
static NeoShaderCatalog *MakeCatalog(NSString *fixtures) {
  NSArray *files = @[
    FileRecord(fixtures, @"stock.slangp"), FileRecord(fixtures, @"stock.slang"),
    FileRecord(fixtures, @"stock-smooth.slangp"), FileRecord(fixtures, @"lut.slangp"), FileRecord(fixtures, @"lut.slang"),
    FileRecord(fixtures, @"textures/palette.png")
  ];
  NSData *previewData = [NSData dataWithContentsOfFile:[fixtures stringByAppendingPathComponent:@"previews/stock.png"]];
  NSDictionary *json = @{
    @"schema" : @1,
    @"engine" : @"libretro",
    @"format" : @"slang",
    @"source" : @{@"name" : @"test", @"repository" : @"https://example.invalid", @"commit" : kRevision, @"raw" : kBase},
    @"previews" : @{
      @"name" : @"previews",
      @"commit" : kRevision,
      @"raw" : kPreviewBase,
      @"reference" : @0,
      @"scale" : @0,
      @"files" : @[ @[ @"stock.png", @(previewData.length), SHA256Hex(previewData) ] ]
    },
    @"compiler" : @"test",
    @"categories" : @[ @"crt", @"other" ],
    @"files" : files,
    @"entries" : @[
      @{@"id" : @"stock.slangp", @"name" : @"stock", @"category" : @"other", @"family" : @".", @"files" : @[ @0, @1 ],
        @"passes" : @1, @"preview" : @0, @"validation" : @"rendered"},
      @{@"id" : @"stock-smooth.slangp", @"name" : @"stock-smooth", @"category" : @"other", @"family" : @".",
        @"files" : @[ @2, @1 ], @"passes" : @1, @"preview" : @-1, @"validation" : @"rendered"},
      @{@"id" : @"lut.slangp", @"name" : @"lut", @"category" : @"crt", @"family" : @".", @"files" : @[ @3, @4, @5 ],
        @"passes" : @1, @"luts" : @1, @"preview" : @-1, @"validation" : @"rendered"},
    ],
  };
  NSError *error = nil;
  NeoShaderCatalog *catalog = [NeoShaderCatalog catalogWithData:[NSJSONSerialization dataWithJSONObject:json options:0 error:nil]
                                                          error:&error];
  if (catalog == nil) fprintf(stderr, "catalog: %s\n", error.description.UTF8String);
  return catalog;
}

static NeoShaderResult *Install(NeoShaderStorage *storage, NeoShaderCatalog *catalog, NSString *identifier) {
  __block NeoShaderResult *result = nil;
  [storage installEntry:[catalog entryWithIdentifier:identifier]
                catalog:catalog
               progress:nil
             completion:^(NeoShaderResult *outcome) {
               result = outcome;
             }];
  Wait(^BOOL {
    return result != nil;
  });
  return result;
}

static BOOL Exists(NSString *path) { return [NSFileManager.defaultManager fileExistsAtPath:path]; }

static void TestCatalogParsing(NeoShaderCatalog *catalog) {
  CHECK(catalog != nil && catalog.entries.count == 3, "catalog: three entries");
  NeoShaderCatalogEntry *stock = [catalog entryWithIdentifier:@"stock.slangp"];
  CHECK(stock.files.count == 2 && stock.preview != nil, "catalog: stock has two files and a preview");
  NSURL *url = [catalog downloadURLForFile:stock.files[0]];
  CHECK([url.absoluteString isEqualToString:[kBase stringByAppendingString:@"stock.slangp"]],
        "catalog: download URL at the pinned revision (%s)", url.absoluteString.UTF8String);
  // A file entry leaving the repository is refused, whatever the rest.
  NSDictionary *bad = @{
    @"schema" : @1, @"engine" : @"libretro", @"format" : @"slang",
    @"source" : @{@"commit" : kRevision, @"raw" : kBase},
    @"files" : @[ @[ @"../escape.slang", @1, [@"" stringByPaddingToLength:64 withString:@"a" startingAtIndex:0] ] ],
    @"entries" : @[ @{@"id" : @"x.slangp", @"files" : @[ @0 ]} ]
  };
  NeoShaderCatalog *refused = [NeoShaderCatalog catalogWithData:[NSJSONSerialization dataWithJSONObject:bad options:0 error:nil]
                                                          error:nil];
  CHECK(refused == nil, "catalog: a file path with \"..\" refuses the whole catalog");
}

static void TestInstallAndRemove(NSString *root, NSString *fixtures, NeoShaderCatalog *catalog) {
  FakeNetwork *network = [FakeNetwork new];
  network.fixtures = fixtures;
  NeoShaderStorage *storage = [[NeoShaderStorage alloc] initWithRoot:root engine:@"libretro"];
  storage.dataLoader = [network loader];
  NSString *files = [storage filesDirectoryForRevision:kRevision];

  NeoShaderResult *result = Install(storage, catalog, @"stock.slangp");
  CHECK(result.success, "install stock: %s %s", result.code.UTF8String ?: "", result.detail.UTF8String ?: "");
  CHECK(Exists([files stringByAppendingPathComponent:@"stock.slangp"]) &&
            Exists([files stringByAppendingPathComponent:@"stock.slang"]),
        "install stock: files in files/<revision>");
  NeoShaderInstallation *installation = [storage installationWithIdentifier:@"stock.slangp"];
  CHECK(installation != nil && [installation.revision isEqualToString:kRevision] && installation.files.count == 2 &&
            [storage installationIsComplete:installation],
        "install stock: registered with its revision and files");

  result = Install(storage, catalog, @"stock-smooth.slangp");
  CHECK(result.success, "install stock-smooth");
  CHECK([network requestsFor:@"stock.slang"] == 1, "shared stock.slang verified on disk, not downloaded again (%lu)",
        (unsigned long)[network requestsFor:@"stock.slang"]);

  // A new instance (next launch) reads the same registry.
  NeoShaderStorage *reopened = [[NeoShaderStorage alloc] initWithRoot:root engine:@"libretro"];
  CHECK(reopened.installations.count == 2, "registry persists (%lu)", (unsigned long)reopened.installations.count);

  CHECK([storage removeInstallationWithIdentifier:@"stock.slangp" error:nil], "remove stock");
  CHECK(!Exists([files stringByAppendingPathComponent:@"stock.slangp"]) &&
            Exists([files stringByAppendingPathComponent:@"stock.slang"]),
        "remove stock: its own file deleted, the shared source kept");
  CHECK([storage removeInstallationWithIdentifier:@"stock-smooth.slangp" error:nil], "remove stock-smooth");
  CHECK(!Exists([files stringByAppendingPathComponent:@"stock.slang"]), "remove the last user: shared source deleted");
  CHECK(![storage removeInstallationWithIdentifier:@"stock.slangp" error:nil], "removing twice reports failure");

  result = Install(storage, catalog, @"lut.slangp");
  CHECK(result.success && Exists([files stringByAppendingPathComponent:@"textures/palette.png"]),
        "install lut with its texture");
  CHECK([storage removeInstallationWithIdentifier:@"lut.slangp" error:nil] &&
            !Exists([files stringByAppendingPathComponent:@"textures"]),
        "remove lut: empty texture folder removed");
}

static void TestRefusals(NSString *root, NSString *fixtures, NeoShaderCatalog *catalog) {
  FakeNetwork *network = [FakeNetwork new];
  network.fixtures = fixtures;
  NeoShaderStorage *storage = [[NeoShaderStorage alloc] initWithRoot:root engine:@"libretro"];
  storage.dataLoader = [network loader];
  NSString *files = [storage filesDirectoryForRevision:kRevision];
  NSDictionary<NSString *, NSString *> *expected = @{
    @"corrupt" : @"DOWNLOAD_HASH", @"short" : @"DOWNLOAD_SIZE", @"404" : @"DOWNLOAD_HTTP", @"error" : @"DOWNLOAD_NETWORK"
  };
  for (NSString *fault in expected) {
    network.faults[@"lut.slang"] = fault;
    NeoShaderResult *result = Install(storage, catalog, @"lut.slangp");
    CHECK(!result.success && [result.code isEqualToString:expected[fault]], "%s file refused with %s (got %s)",
          fault.UTF8String, expected[fault].UTF8String, result.code.UTF8String ?: "success");
    CHECK([storage installationWithIdentifier:@"lut.slangp"] == nil &&
              !Exists([files stringByAppendingPathComponent:@"lut.slangp"]) &&
              !Exists([files stringByAppendingPathComponent:@"textures/palette.png"]),
          "%s: nothing installed, not even the verified files", fault.UTF8String);
  }
  [network.faults removeAllObjects];
  NSArray *staging = [NSFileManager.defaultManager contentsOfDirectoryAtPath:[root stringByAppendingPathComponent:@"staging"]
                                                                       error:nil];
  CHECK(staging.count == 0, "refused downloads leave no staging folder (%lu)", (unsigned long)staging.count);

  storage.maximumEntryBytes = 10;
  NeoShaderResult *large = Install(storage, catalog, @"lut.slangp");
  CHECK(!large.success && [large.code isEqualToString:@"ENTRY_TOO_LARGE"], "an entry over the limit is refused");
  storage.maximumEntryBytes = 64ULL << 20;

  // Busy, then cancelled.
  network.faults[@"lut.slang"] = @"slow";
  __block NeoShaderResult *first = nil;
  [storage installEntry:[catalog entryWithIdentifier:@"lut.slangp"]
                catalog:catalog
               progress:nil
             completion:^(NeoShaderResult *outcome) {
               first = outcome;
             }];
  CHECK([storage isInstallingIdentifier:@"lut.slangp"], "an installation is reported in progress");
  NeoShaderResult *second = Install(storage, catalog, @"lut.slangp");
  CHECK(!second.success && [second.code isEqualToString:@"DOWNLOAD_BUSY"], "the same entry twice: DOWNLOAD_BUSY");
  [storage cancelInstallationOfIdentifier:@"lut.slangp"];
  Wait(^BOOL {
    return first != nil;
  });
  CHECK(first != nil && !first.success && [first.code isEqualToString:@"DOWNLOAD_CANCELLED"],
        "cancelled installation reports DOWNLOAD_CANCELLED (%s)", first.code.UTF8String ?: "success");
  CHECK([storage installationWithIdentifier:@"lut.slangp"] == nil, "cancelled: nothing installed");
  [network.faults removeAllObjects];

  // Progress reaches the expected total.
  __block unsigned long long lastReceived = 0, lastExpected = 0;
  __block NeoShaderResult *done = nil;
  [storage installEntry:[catalog entryWithIdentifier:@"lut.slangp"]
                catalog:catalog
               progress:^(unsigned long long received, unsigned long long expectedBytes) {
                 lastReceived = received;
                 lastExpected = expectedBytes;
               }
             completion:^(NeoShaderResult *outcome) {
               done = outcome;
             }];
  Wait(^BOOL {
    return done != nil;
  });
  CHECK(done.success && lastExpected > 0 && lastReceived == lastExpected, "progress ends at %llu of %llu", lastReceived,
        lastExpected);
}

static void TestPreviewsFavoritesProfiles(NSString *root, NSString *fixtures, NeoShaderCatalog *catalog) {
  FakeNetwork *network = [FakeNetwork new];
  network.fixtures = fixtures;
  NeoShaderStorage *storage = [[NeoShaderStorage alloc] initWithRoot:root engine:@"libretro"];
  storage.dataLoader = [network loader];
  NeoShaderCatalogFile *preview = [catalog entryWithIdentifier:@"stock.slangp"].preview;
  __block NSData *data = nil;
  __block BOOL answered = NO;
  [storage previewDataForFile:preview
                      catalog:catalog
                   completion:^(NSData *bytes) {
                     data = bytes;
                     answered = YES;
                   }];
  Wait(^BOOL {
    return answered;
  });
  CHECK(data.length == preview.size, "preview downloaded and verified");
  answered = NO;
  [storage previewDataForFile:preview
                      catalog:catalog
                   completion:^(NSData *bytes) {
                     data = bytes;
                     answered = YES;
                   }];
  Wait(^BOOL {
    return answered;
  });
  CHECK(data != nil && [network requestsFor:@"previews/stock.png"] == 1, "preview served from the cache the second time");

  [storage setFavorite:YES identifier:@"slang:crt/a.slangp"];
  [storage setFavorite:YES identifier:@"slang:crt/b.slangp"];
  [storage setFavorite:NO identifier:@"slang:crt/a.slangp"];
  NeoShaderStorage *reopened = [[NeoShaderStorage alloc] initWithRoot:root engine:@"libretro"];
  CHECK([reopened.favorites isEqualToArray:@[ @"slang:crt/b.slangp" ]], "favourites persist");

  NSError *error = nil;
  NeoShaderProfile *profile = [storage saveProfileWithName:@"  Salon CRT  "
                                                    shader:@"slang:crt/a.slangp"
                                                parameters:@{@"MASK" : @0.5, @"BAD" : @(NAN)}
                                                     error:&error];
  CHECK(profile != nil && [profile.name isEqualToString:@"Salon CRT"] && profile.parameters.count == 1,
        "profile saved with a trimmed name, non-finite values dropped");
  NeoShaderProfile *replaced = [storage saveProfileWithName:@"salon crt"
                                                     shader:@"crt-lottes-fast"
                                                 parameters:@{}
                                                      error:nil];
  CHECK(replaced != nil && storage.profiles.count == 1 && [storage.profiles.firstObject.shader isEqualToString:@"crt-lottes-fast"],
        "a profile with the same name (any case) is replaced");
  CHECK([storage saveProfileWithName:@"   " shader:@"x" parameters:@{} error:&error] == nil &&
            [error.userInfo[NSDebugDescriptionErrorKey] isEqualToString:@"PROFILE_NAME"],
        "an empty name is refused with PROFILE_NAME");
  CHECK([storage removeProfileWithIdentifier:replaced.identifier] && storage.profiles.count == 0, "profile removed");

  // Corrupted files are read as empty, never crash.
  [@"{not json" writeToFile:[root stringByAppendingPathComponent:@"profiles.json"] atomically:YES encoding:NSUTF8StringEncoding error:nil];
  [@"[1,2" writeToFile:[root stringByAppendingPathComponent:@"installed.json"] atomically:YES encoding:NSUTF8StringEncoding error:nil];
  CHECK(storage.profiles.count == 0 && storage.installations.count == 0, "corrupted JSON is read as empty");
}

static void TestStorageReport(NSString *root, NSString *fixtures, NeoShaderCatalog *catalog) {
  FakeNetwork *network = [FakeNetwork new];
  network.fixtures = fixtures;
  NeoShaderStorage *storage = [[NeoShaderStorage alloc] initWithRoot:root engine:@"libretro"];
  storage.dataLoader = [network loader];
  CHECK(Install(storage, catalog, @"stock.slangp").success, "report: stock installed");
  NSString *orphan = [[storage filesDirectoryForRevision:kRevision] stringByAppendingPathComponent:@"left/over.slang"];
  [NSFileManager.defaultManager createDirectoryAtPath:orphan.stringByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:nil];
  [@"0123456789" writeToFile:orphan atomically:YES encoding:NSUTF8StringEncoding error:nil];
  NSDictionary *report = [storage storageReport];
  CHECK([report[@"installed"] integerValue] == 1 && [report[@"orphanFiles"] integerValue] == 1 &&
            [report[@"orphanBytes"] integerValue] == 10,
        "report: one installed preset, one orphan file of 10 bytes (%s)", report.description.UTF8String);
  const unsigned long long freed = [storage cleanCaches];
  CHECK(freed >= 10 && !Exists(orphan) && [storage installationIsComplete:[storage installationWithIdentifier:@"stock.slangp"]],
        "cleanCaches removes the orphan and keeps the installed preset");
  CHECK([[storage storageReport][@"orphanFiles"] integerValue] == 0, "report after cleaning: no orphan");
}

/// The bundled libretro catalog as the in-game menu reads it: every entry
/// parsed with its files, rendered by the CI's Metal gate (Build 450:
/// tools/shaders/slang-metal-results.json), reachable by category, search
/// and identifier, downloadable from the pinned commit; the presets left
/// out keep their reason.
static void TestBundledCatalog(NSString *resources) {
  NSData *data = [NSData dataWithContentsOfFile:[resources stringByAppendingPathComponent:@"slang-catalog.json"]];
  NSDictionary *json = data != nil ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
  CHECK([json isKindOfClass:NSDictionary.class], "bundled catalog: slang-catalog.json is JSON");
  if (![json isKindOfClass:NSDictionary.class]) return;
  NeoShaderCatalogManager *manager = NeoShaderCatalogManager.sharedManager;
  [manager setCatalogDirectory:resources];
  NeoShaderCatalog *catalog = [manager catalogForEngine:@"libretro"];
  CHECK(catalog != nil, "bundled catalog: the manager reads it");
  if (catalog == nil) return;
  NSArray *rawEntries = json[@"entries"];
  NSString *commit = json[@"source"][@"commit"];
  CHECK(catalog.entries.count == rawEntries.count && rawEntries.count > 900,
        "bundled catalog: %lu entries parsed of %lu", (unsigned long)catalog.entries.count,
        (unsigned long)rawEntries.count);
  CHECK([catalog.sourceRevision isEqualToString:commit] && commit.length == 40,
        "bundled catalog: pinned at its commit (%s)", catalog.sourceRevision.UTF8String);
  CHECK([catalog.engine isEqualToString:@"libretro"] && [catalog.format isEqualToString:NeoShaderFormatSlang],
        "bundled catalog: libretro slang presets");
  NSUInteger notRendered = 0, emptyFiles = 0, wrongBytes = 0, unknownCategory = 0, unknownTier = 0, lost = 0;
  NSSet<NSString *> *categories = [NSSet setWithArray:catalog.categories];
  for (NeoShaderCatalogEntry *entry in catalog.entries) {
    if (![entry.validation isEqualToString:@"rendered"]) notRendered++;
    if (entry.files.count == 0 || entry.passCount == 0) emptyFiles++;
    unsigned long long bytes = 0;
    for (NeoShaderCatalogFile *file in entry.files) bytes += file.size;
    if (bytes != entry.downloadBytes || bytes == 0) wrongBytes++;
    if (![categories containsObject:entry.category]) unknownCategory++;
    if (entry.costTier == NeoShaderCostTierUnknown) unknownTier++;
    if ([catalog entryWithIdentifier:entry.identifier] != entry) lost++;
  }
  CHECK(notRendered == 0, "bundled catalog: %lu entries not rendered by the Metal gate", (unsigned long)notRendered);
  CHECK(emptyFiles == 0 && wrongBytes == 0, "bundled catalog: %lu entries without files, %lu with a wrong size",
        (unsigned long)emptyFiles, (unsigned long)wrongBytes);
  CHECK(unknownCategory == 0 && unknownTier == 0 && lost == 0,
        "bundled catalog: %lu unknown categories, %lu unknown cost tiers, %lu not found by identifier",
        (unsigned long)unknownCategory, (unsigned long)unknownTier, (unsigned long)lost);
  NSUInteger listed = 0;
  for (NSString *category in catalog.categories) listed += [catalog entriesInCategory:category].count;
  CHECK(listed == catalog.entries.count, "bundled catalog: the categories list every entry once (%lu)",
        (unsigned long)listed);
  BOOL royale = NO;
  for (NeoShaderCatalogEntry *entry in [catalog entriesMatching:@"  CRT-ROYALE "]) {
    royale = royale || [entry.identifier isEqualToString:@"crt/crt-royale.slangp"];
  }
  CHECK(royale, "bundled catalog: a search ignores case and spaces (crt-royale)");
  NeoShaderCatalogFile *spaced = nil;
  for (NeoShaderCatalogEntry *entry in catalog.entries) {
    for (NeoShaderCatalogFile *file in entry.files) {
      if ([file.path containsString:@" "]) spaced = file;
    }
  }
  NSString *expected = [NSString stringWithFormat:@"https://raw.githubusercontent.com/libretro/slang-shaders/%@/", commit];
  NSURL *url = spaced != nil ? [catalog downloadURLForFile:spaced] : nil;
  CHECK(url != nil && [url.absoluteString hasPrefix:expected] && ![url.absoluteString containsString:@" "] &&
            [url.path hasSuffix:spaced.path],
        "bundled catalog: a file whose path has spaces downloads from the pinned commit (%s)",
        url.absoluteString.UTF8String);
  BOOL excludedWithReason = NO;
  for (NSDictionary<NSString *, NSString *> *item in [manager diagnosticsForEngine:@"libretro"]) {
    if ([item[@"identifier"] isEqualToString:@"deinterlacing/nnedi3-nns256-deinterlacing.slangp"]) {
      excludedWithReason = [item[@"code"] isEqualToString:@"GPU_ERROR"] && [catalog entryWithIdentifier:item[@"identifier"]] == nil;
    }
  }
  CHECK(excludedWithReason, "bundled catalog: the preset the Metal gate could not render is left out with its reason");
  [manager setCatalogDirectory:nil];
}

/// The Dolphin API the post-processing page uses: options as Dolphin reads
/// them, credit lines quoted as written, translation like the core, refusals
/// with stable codes, and the bundled catalog of Dolphin's official shaders.
static void TestDolphinShader(NSString *resources) {
  NSString *code = @"// CRT Emulation\n// by Mattias\n// https://www.shadertoy.com/view/lsB3DV\n"
                   @"/*\n[configuration]\n[OptionRangeFloat]\nGUIName = Curvature\nOptionName = M_CURVATURE\n"
                   @"MinValue = 0.0\nMaxValue = 1.0\nDefaultValue = 0.5\nStepAmount = 0.05\n\n[OptionBool]\n"
                   @"GUIName = Glow\nOptionName = A_GLOW\nDefaultValue = true\n[/configuration]\n*/\n"
                   @"void main()\n{\n  float4 c = Sample();\n  if (OptionEnabled(A_GLOW)) c.rgb *= 1.0 + "
                   @"GetOption(M_CURVATURE);\n  SetOutput(c);\n}\n";
  NSArray<NeoDolphinShaderOption *> *options = [NeoDolphinShader optionsOfCode:code];
  CHECK(options.count == 2 && [options[0].name isEqualToString:@"A_GLOW"] && [options[1].name isEqualToString:@"M_CURVATURE"],
        "Dolphin options in Dolphin's order (sorted by name)");
  NeoDolphinShaderOption *curvature = options.count == 2 ? options[1] : nil;
  // Dolphin reads option numbers as float: 0.05 is 0.0500000007.
  CHECK(curvature.type == NeoDolphinOptionTypeFloat && [curvature.guiName isEqualToString:@"Curvature"] &&
            [curvature.defaultValues isEqualToArray:@[ @0.5 ]] && [curvature.maximums isEqualToArray:@[ @1 ]] &&
            curvature.steps.count == 1 && fabs(curvature.steps.firstObject.doubleValue - 0.05) < 1e-6,
        "float option parsed");
  CHECK(options.count == 2 && options[0].type == NeoDolphinOptionTypeBool && options[0].defaultValues.firstObject.boolValue,
        "bool option parsed");
  NSArray<NSString *> *credits = [NeoDolphinShader creditLinesOfCode:code];
  CHECK([credits containsObject:@"by Mattias"] && [credits containsObject:@"https://www.shadertoy.com/view/lsB3DV"],
        "credit lines quoted as written (%s)", credits.description.UTF8String);
  NSError *error = nil;
  NeoDolphinShader *shader = [NeoDolphinShader shaderWithCode:code error:&error];
  CHECK(shader != nil && shader.fragmentMSL.length > 0 && shader.vertexMSL.length > 0 && shader.options.count == 2,
        "translated like the core (%s)", [error.userInfo[NSDebugDescriptionErrorKey] UTF8String] ?: "");
  error = nil;
  CHECK([NeoDolphinShader shaderWithCode:@"float4 nothing;" error:&error] == nil &&
            [error.userInfo[NeoDolphinShaderErrorCodeKey] isEqualToString:@"DOLPHIN_NO_MAIN"],
        "a file without main is refused with its code");
  error = nil;
  CHECK([NeoDolphinShader shaderWithCode:@"void main() { SetOutput(Sampel()); }" error:&error] == nil &&
            [error.userInfo[NeoDolphinShaderErrorCodeKey] isEqualToString:@"GLSL_FRAGMENT_FAILED"] &&
            [error.userInfo[NSDebugDescriptionErrorKey] length] > 0,
        "a shader that does not compile is refused, the compiler log kept for the log");

  if (resources == nil) return;
  NeoShaderCatalogManager *manager = NeoShaderCatalogManager.sharedManager;
  [manager setCatalogDirectory:resources];
  NeoShaderCatalog *catalog = [manager catalogForEngine:@"dolphin"];
  NSUInteger unbundled = 0, wrongFormat = 0, unrendered = 0;
  for (NeoShaderCatalogEntry *entry in catalog.entries) {
    if (!entry.bundled || entry.downloadBytes != 0 || entry.files.count != 1) unbundled++;
    if (![entry.format isEqualToString:NeoShaderFormatDolphinGLSL] || ![entry.identifier hasPrefix:@"sys/"]) wrongFormat++;
    if (![entry.validation isEqualToString:@"rendered"]) unrendered++;
  }
  CHECK(catalog != nil && catalog.entries.count >= 40 && unbundled == 0 && wrongFormat == 0,
        "Dolphin catalog: official shaders shipped with the core, nothing to download (%lu entries)",
        (unsigned long)catalog.entries.count);
  CHECK(unrendered == 0, "Dolphin catalog: every entry offered was drawn visibly by the CI (%lu not)",
        (unsigned long)unrendered);
  CHECK([catalog entryWithIdentifier:@"sys/FXAA"] != nil && [catalog entryWithIdentifier:@"sys/default_pre_post_process"] == nil,
        "Dolphin catalog: Dolphin's default pass is not offered");
  BOOL stereo = NO, hdr = NO;
  for (NSDictionary<NSString *, NSString *> *item in [manager diagnosticsForEngine:@"dolphin"]) {
    stereo = stereo || ([item[@"identifier"] hasPrefix:@"Anaglyph/"] && [item[@"code"] isEqualToString:@"STEREOSCOPIC_ONLY"]);
    hdr = hdr || ([item[@"identifier"] isEqualToString:@"AutoHDR.glsl"] && [item[@"code"] isEqualToString:@"NO_VISIBLE_EFFECT"]);
  }
  CHECK(stereo, "Dolphin catalog: stereoscopic shaders left out with their reason");
  // DolphiniOS has no HDR output on iPhone: an HDR-only shader would change nothing.
  CHECK(hdr && [catalog entryWithIdentifier:@"sys/AutoHDR"] == nil,
        "Dolphin catalog: HDR-only shaders left out with their reason");
  [manager setCatalogDirectory:nil];
}

int main(int argc, const char *argv[]) {
  @autoreleasepool {
    if (argc != 2 && argc != 3) {
      fprintf(stderr, "usage: neoshader-kit-tests FIXTURES_DIRECTORY [RESOURCES_DIRECTORY]\n");
      return 2;
    }
    NSString *fixtures = [NSString stringWithUTF8String:argv[1]];
    if (argc == 3) TestBundledCatalog([NSString stringWithUTF8String:argv[2]]);
    TestDolphinShader(argc == 3 ? [NSString stringWithUTF8String:argv[2]] : nil);
    NeoShaderCatalog *catalog = MakeCatalog(fixtures);
    TestCatalogParsing(catalog);
    if (catalog != nil) {
      NSString *base = [NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
      TestInstallAndRemove([base stringByAppendingPathComponent:@"a"], fixtures, catalog);
      TestRefusals([base stringByAppendingPathComponent:@"b"], fixtures, catalog);
      TestPreviewsFavoritesProfiles([base stringByAppendingPathComponent:@"c"], fixtures, catalog);
      TestStorageReport([base stringByAppendingPathComponent:@"d"], fixtures, catalog);
      [NSFileManager.defaultManager removeItemAtPath:base error:nil];
    }
    printf("%d checks, %d failures\n", gChecks, gFailures);
    return gFailures == 0 ? 0 : 1;
  }
}

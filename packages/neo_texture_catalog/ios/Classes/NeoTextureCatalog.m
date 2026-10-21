// SPDX-License-Identifier: GPL-3.0-or-later
#import "Public/NeoTextureCatalog.h"
#import "NeoTextureSupport.h"
#import "NeoTextureHostResolver.h"
#import "NeoTextureMega.h"
#import <zlib.h>

NSString *const NeoTextureCatalogErrorDomain = @"NeoTextureCatalog";
NSNotificationName const NeoTextureCatalogDidChangeNotification = @"NeoTextureCatalogDidChangeNotification";

static const NSUInteger IndexLimit = 16 * 1024 * 1024;
static const NSUInteger IndexCompressedLimit = 4 * 1024 * 1024;
static const NSUInteger PackCountLimit = 5000;

static NSError *CatalogError(NSInteger code, NSString *key, NSString *message) {
  return [NSError errorWithDomain:NeoTextureCatalogErrorDomain code:code
                         userInfo:@{NSLocalizedDescriptionKey: message ?: @"HD texture catalogue unavailable", @"key": key ?: @"catalogueFailed"}];
}

static NSData *Gunzip(NSData *data, NSUInteger limit, NSError **error) {
  const unsigned char *bytes = data.bytes;
  if (data.length < 18 || data.length > IndexCompressedLimit || bytes[0] != 0x1f || bytes[1] != 0x8b) {
    if (error) *error = CatalogError(2, @"catalogueInvalid", @"Compressed index is invalid or too large");
    return nil;
  }
  z_stream stream = {0};
  if (inflateInit2(&stream, 16 + MAX_WBITS) != Z_OK) return nil;
  NSMutableData *out = [NSMutableData data];
  unsigned char buffer[65536];
  stream.next_in = (Bytef *)bytes;
  stream.avail_in = (uInt)data.length;
  int status = Z_OK;
  while (status == Z_OK) {
    stream.next_out = buffer;
    stream.avail_out = sizeof(buffer);
    status = inflate(&stream, Z_NO_FLUSH);
    if (status != Z_OK && status != Z_STREAM_END) break;
    const size_t produced = sizeof(buffer) - stream.avail_out;
    if (out.length + produced > limit) { status = Z_DATA_ERROR; break; }
    [out appendBytes:buffer length:produced];
    if (!produced && !stream.avail_in) break;
  }
  inflateEnd(&stream);
  if (status != Z_STREAM_END) {
    if (error) *error = CatalogError(2, @"catalogueInvalid", @"Compressed index could not be expanded");
    return nil;
  }
  return out;
}

static BOOL ValidIdentity(id value) {
  if (![value isKindOfClass:NSDictionary.class]) return NO;
  NSString *type = NeoTexString(value[@"type"]), *scheme = NeoTexString(value[@"scheme"]), *text = NeoTexString(value[@"value"]);
  return NeoTexSafeToken(type, 40) && NeoTexSafeToken(scheme, 60) && text.length && text.length <= 40 &&
         [text rangeOfCharacterFromSet:NeoTexIdentityCharacters().invertedSet].location == NSNotFound;
}

static BOOL ValidFolders(id value) {
  if (![value isKindOfClass:NSArray.class] || ![value count] || [value count] > 16) return NO;
  NSMutableSet *targets = [NSMutableSet set];
  for (id folder in value) {
    if (![folder isKindOfClass:NSDictionary.class]) return NO;
    NSString *from = NeoTexString(folder[@"from"]), *to = NeoTexString(folder[@"to"]);
    if (from.length && (![from hasSuffix:@"/"] || !NeoTexSafeRelativePath([from substringToIndex:from.length - 1], 512, 12))) return NO;
    if (!NeoTexSafeRelativePath(to, 160, 2) || [targets containsObject:to.lowercaseString]) return NO;
    [targets addObject:to.lowercaseString];
    id exclude = folder[@"exclude"];
    if (exclude && (![exclude isKindOfClass:NSArray.class] || [exclude count] > 32)) return NO;
    for (id prefix in exclude ?: @[])
      if (![prefix isKindOfClass:NSString.class] || ![prefix hasSuffix:@"/"] ||
          !NeoTexSafeRelativePath([prefix substringToIndex:[prefix length] - 1], 512, 12)) return NO;
  }
  return YES;
}

static BOOL ValidDownload(NSDictionary *download, NSString *availability, BOOL nativeCapability) {
  if (![download isKindOfClass:NSDictionary.class]) return NO;
  if (![download[@"automatable"] boolValue]) return ![availability isEqualToString:@"available"];
  NSArray *parts = download[@"parts"];
  NSString *format = NeoTexString(download[@"format"]);
  if (![(nativeCapability ? @[@"zip", @"7z", @"rar"] : @[@"zip", @"7z"]) containsObject:format] ||
      ![parts isKindOfClass:NSArray.class] || !parts.count || parts.count > 16) return NO;
  unsigned long long total = 0;
  for (id part in parts) {
    if (![part isKindOfClass:NSDictionary.class] || !NeoTexHTTPS(part[@"url"]) || !NeoTexSHA256(part[@"sha256"]) ||
        !NeoTexPositive(part[@"size"], 64ULL << 30)) return NO;
    if (part[@"provider"]) {
      if (!nativeCapability) return NO;
      NSString *provider = NeoTexString(part[@"provider"]);
      if ([provider isEqualToString:@"mega"]) {
        if (!NeoTexMegaPublicFileURL(NeoTexString(part[@"url"])) || !NeoTexPositive(part[@"size"], 16ULL << 30)) return NO;
      } else if (![@[@"gdrive", @"yandex"] containsObject:provider] || !NeoTexValidHostPart(part)) {
        return NO;
      }
    }
    total += [part[@"size"] unsignedLongLongValue];
  }
  if (parts.count > 1 && (!NeoTexSHA256(download[@"sha256"]) || !NeoTexPositive(download[@"size"], 64ULL << 30) ||
                        [download[@"size"] unsignedLongLongValue] != total)) return NO;
  if (parts.count == 1 && ((download[@"size"] && (!NeoTexPositive(download[@"size"], 64ULL << 30) ||
                           [download[@"size"] unsignedLongLongValue] != total)) ||
                          (download[@"sha256"] && ![download[@"sha256"] isEqual:parts[0][@"sha256"]]))) return NO;
  return total <= (64ULL << 30);
}

// The base manifest is still usable by older app builds: they see a verified
// manual pack and do not accidentally fetch a Drive/MEGA page as an archive.
// Only a client implementing the native provider/RAR capability expands this
// opt-in descriptor, and only when it describes the same exact verified file.
static NSDictionary *ExpandedNativePack(NSDictionary *pack, BOOL *expanded) {
  *expanded = NO;
  NSDictionary *download = [pack[@"download"] isKindOfClass:NSDictionary.class] ? pack[@"download"] : nil;
  id candidate = download[@"in_app"];
  if (!candidate) return pack;
  NSMutableDictionary *fallback = [pack mutableCopy], *manual = [download mutableCopy];
  [manual removeObjectForKey:@"in_app"];
  fallback[@"download"] = manual;
  NSDictionary *file = NeoTexVerifiedFile(pack);
  if (![pack[@"availability"] isEqual:@"manual"] || [download[@"automatable"] boolValue] || !file ||
      ![candidate isKindOfClass:NSDictionary.class] || ![candidate[@"automatable"] isEqual:@YES] ||
      ![candidate[@"format"] isEqual:file[@"format"]] || ![candidate[@"file_name"] isEqual:file[@"file_name"]] ||
      !ValidDownload(candidate, @"available", YES)) return fallback;
  NSArray *parts = candidate[@"parts"];
  const unsigned long long size = parts.count > 1 ? [candidate[@"size"] unsignedLongLongValue] : [parts[0][@"size"] unsignedLongLongValue];
  NSString *digest = parts.count > 1 ? NeoTexString(candidate[@"sha256"]) : NeoTexString(parts[0][@"sha256"]);
  if (size != [file[@"size"] unsignedLongLongValue] || ![digest isEqualToString:file[@"sha256"]]) return fallback;
  fallback[@"availability"] = @"available";
  fallback[@"download"] = candidate;
  *expanded = YES;
  return fallback;
}

// The consoles a pack serves: "system", or "systems" when one download for
// one engine serves several (GameCube discs and Wii Virtual Console titles).
static NSArray<NSString *> *PackSystems(NSDictionary *pack) {
  NSArray *systems = [pack[@"systems"] isKindOfClass:NSArray.class] ? pack[@"systems"] : nil;
  return systems.count ? systems : @[NeoTexString(pack[@"system"])];
}

static BOOL ValidSystems(NSDictionary *pack, NSString *engine) {
  id systems = pack[@"systems"];
  if (!systems) return YES;
  if (![systems isKindOfClass:NSArray.class] || ![systems count] || [systems count] > 4 || ![systems containsObject:pack[@"system"]] ||
      [NSSet setWithArray:systems].count != [systems count]) return NO;
  for (id system in systems)
    if (![system isKindOfClass:NSString.class] || ![NeoTexCanonicalSystem(system) isEqualToString:system] ||
        ![NeoTexEngineForSystem(system) isEqualToString:engine]) return NO;
  return YES;
}

static NSDictionary *ValidatedPack(id value) {
  if (![value isKindOfClass:NSDictionary.class]) return nil;
  BOOL nativeCapability = NO;
  NSDictionary *pack = ExpandedNativePack(value, &nativeCapability);
  NSString *system = NeoTexString(pack[@"system"]), *engine = NeoTexString(pack[@"engine"]);
  NSString *availability = NeoTexString(pack[@"availability"]);
  if (!NeoTexSafeToken(pack[@"id"], 120) || !NeoTexString(pack[@"version"]).length || NeoTexString(pack[@"version"]).length > 64 ||
      !NeoTexString(pack[@"title"]).length || NeoTexString(pack[@"title"]).length > 200 ||
      ![NeoTexEngineForSystem(system) isEqualToString:engine] || !ValidSystems(pack, engine) ||
      ![@[@"available", @"manual", @"unavailable"] containsObject:availability] || !NeoTexHTTPS(pack[@"page_url"]) ||
      ![pack[@"authors"] isKindOfClass:NSArray.class] || ![pack[@"authors"] count] ||
      ![pack[@"games"] isKindOfClass:NSArray.class] || ![pack[@"games"] count] || [pack[@"games"] count] > 64 ||
      ![pack[@"licence"] isKindOfClass:NSDictionary.class] || !ValidDownload(pack[@"download"], availability, nativeCapability))
    return nil;
  for (id author in pack[@"authors"]) if (!NeoTexString(author).length || NeoTexString(author).length > 120) return nil;
  for (id game in pack[@"games"]) {
    if (![game isKindOfClass:NSDictionary.class] || !NeoTexString(game[@"title"]).length ||
        (game[@"confirm"] && ![game[@"confirm"] isKindOfClass:NSNumber.class]) ||
        ![game[@"identities"] isKindOfClass:NSArray.class] || ![game[@"identities"] count] || [game[@"identities"] count] > 16)
      return nil;
    for (id identity in game[@"identities"]) if (!ValidIdentity(identity)) return nil;
  }
  NSDictionary *install = pack[@"install"];
  const BOOL validInstall = [install isKindOfClass:NSDictionary.class] && NeoTexPositive(install[@"files"], 2000000) &&
                            NeoTexPositive(install[@"bytes"], 256ULL << 30) && ValidFolders(install[@"folders"]);
  if ([availability isEqualToString:@"available"] && !validInstall) return nil;
  if ([availability isEqualToString:@"manual"] && pack[@"download"][@"verified"]) {
    // A manual pack whose author's file was verified on CI: installed when the user
    // imports that exact file. A malformed record leaves a plain page link.
    if (!validInstall || !NeoTexVerifiedFile(pack)) {
      NSMutableDictionary *plain = [pack mutableCopy];
      NSMutableDictionary *download = [pack[@"download"] mutableCopy];
      [download removeObjectForKey:@"verified"];
      plain[@"download"] = download;
      [plain removeObjectForKey:@"install"];
      return plain;
    }
  }
  return pack;
}

@interface NeoTextureCatalog () {
  dispatch_queue_t _queue;
  NSDictionary *_index;
  NSString *_origin;  // bundled | downloaded
  NSDictionary *_state;
  BOOL _refreshing;
  NSMutableArray *_refreshWaiters;
}
@end

@implementation NeoTextureCatalog

+ (instancetype)sharedCatalog {
  static NeoTextureCatalog *catalog;
  static dispatch_once_t once;
  dispatch_once(&once, ^{ catalog = [self new]; });
  return catalog;
}

- (instancetype)init {
  if (!(self = [super init])) return nil;
  _queue = dispatch_queue_create("org.neostation.textures.catalogue", DISPATCH_QUEUE_SERIAL);
  _manifestURL = [NSURL URLWithString:@"https://raw.githubusercontent.com/TarbleFR/RewindBox/Claude/native/textures/catalogue/manifest.json.gz"];
  NSString *support = NSSearchPathForDirectoriesInDomains(NSApplicationSupportDirectory, NSUserDomainMask, YES).firstObject ?: NSTemporaryDirectory();
  _storageDirectory = [support stringByAppendingPathComponent:@"NeoStation/Textures/Catalogue"];
  for (NSBundle *bundle in @[[NSBundle bundleForClass:self.class], NSBundle.mainBundle]) {
    NSURL *url = [bundle URLForResource:@"NeoTextureCatalog" withExtension:@"bundle"];
    NSBundle *resources = url ? [NSBundle bundleWithURL:url] : nil;
    if ([resources URLForResource:@"manifest.json" withExtension:@"gz"] || [resources URLForResource:@"manifest" withExtension:@"json"]) {
      _bundledDirectory = resources.resourcePath;
      break;
    }
  }
  _refreshWaiters = [NSMutableArray array];
  return self;
}

+ (NSDictionary *)validatedIndex:(NSData *)data error:(NSError **)error {
  if (!data.length || data.length > IndexLimit) {
    if (error) *error = CatalogError(1, @"catalogueInvalid", @"Index missing or too large");
    return nil;
  }
  const unsigned char *bytes = data.bytes;
  if (data.length >= 2 && bytes[0] == 0x1f && bytes[1] == 0x8b) {
    data = Gunzip(data, IndexLimit, error);
    if (!data) return nil;
  }
  id json = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
  if (![json isKindOfClass:NSDictionary.class] || ![json[@"schema_version"] isEqual:@1] ||
      ![json[@"catalogue_id"] isEqual:@"neostation-hd-textures"] || !NeoTexString(json[@"revision"]).length ||
      ![json[@"packs"] isKindOfClass:NSArray.class] || [json[@"packs"] count] > PackCountLimit) {
    if (error) *error = CatalogError(1, @"catalogueInvalid", @"Unsupported or invalid HD texture index");
    return nil;
  }
  NSMutableArray *packs = [NSMutableArray array];
  NSMutableSet *ids = [NSMutableSet set];
  NSUInteger rejected = 0;
  for (id value in json[@"packs"]) {
    NSDictionary *pack = ValidatedPack(value);
    if (!pack || [ids containsObject:pack[@"id"]]) { rejected++; continue; }
    [ids addObject:pack[@"id"]];
    [packs addObject:pack];
  }
  NSMutableArray *sources = [NSMutableArray array];
  for (id source in [json[@"sources"] isKindOfClass:NSArray.class] ? json[@"sources"] : @[])
    if ([source isKindOfClass:NSDictionary.class]) [sources addObject:source];
  NSMutableDictionary *result = [json mutableCopy];
  result[@"packs"] = packs;
  result[@"sources"] = sources;
  result[@"rejected_packs"] = @(rejected);
  return result;
}

#pragma mark - Index storage (serial queue)

- (NSString *)cachedIndexPath { return [self.storageDirectory stringByAppendingPathComponent:@"manifest.json"]; }
- (NSString *)statePath { return [self.storageDirectory stringByAppendingPathComponent:@"state.json"]; }

- (NSDictionary *)bundledIndex {
  if (!self.bundledDirectory) return nil;
  for (NSString *name in @[@"manifest.json", @"manifest.json.gz"]) {
    NSData *data = NeoTexReadBounded([self.bundledDirectory stringByAppendingPathComponent:name], IndexLimit);
    NSDictionary *index = data ? [NeoTextureCatalog validatedIndex:data error:nil] : nil;
    if (index) return index;
  }
  return nil;
}

// The newer of the bundled and the cached index wins: an app update brings
// newer data without discarding a later remote refresh.
- (void)loadLocked {
  if (_index) return;
  _state = NeoTexJSONDictionary(NeoTexReadBounded(self.statePath, 65536)) ?: @{};
  NSDictionary *cached = [NeoTextureCatalog validatedIndex:NeoTexReadBounded(self.cachedIndexPath, IndexLimit) ?: [NSData data] error:nil];
  NSDictionary *bundled = [self bundledIndex];
  if (cached && (!bundled || [NeoTexString(cached[@"generated_at"]) compare:NeoTexString(bundled[@"generated_at"])] != NSOrderedAscending)) {
    _index = cached;
    _origin = @"downloaded";
  } else if (bundled) {
    _index = bundled;
    _origin = @"bundled";
  }
}

- (NSDictionary *)snapshotLocked {
  NSMutableDictionary *snapshot = [NSMutableDictionary dictionary];
  snapshot[@"state"] = _index ? _origin : @"missing";
  snapshot[@"refreshing"] = @(_refreshing);
  if (_index) {
    snapshot[@"revision"] = NeoTexString(_index[@"revision"]);
    snapshot[@"generated_at"] = NeoTexString(_index[@"generated_at"]);
    snapshot[@"pack_count"] = @([_index[@"packs"] count]);
    NSMutableDictionary *systems = [NSMutableDictionary dictionary];
    NSMutableDictionary *available = [NSMutableDictionary dictionary];
    for (NSDictionary *pack in _index[@"packs"])
      for (NSString *system in PackSystems(pack)) {
        systems[system] = @([systems[system] integerValue] + 1);
        if ([pack[@"availability"] isEqual:@"available"]) available[system] = @([available[system] integerValue] + 1);
      }
    snapshot[@"systems"] = systems;
    snapshot[@"available"] = available;
    snapshot[@"sources"] = _index[@"sources"] ?: @[];
  }
  if (_state[@"refreshed_at"]) snapshot[@"refreshed_at"] = _state[@"refreshed_at"];
  if (_state[@"refresh_error"]) snapshot[@"refresh_error"] = _state[@"refresh_error"];
  if (_state[@"failed_at"]) snapshot[@"failed_at"] = _state[@"failed_at"];
  return snapshot;
}

- (NSDictionary *)snapshot {
  __block NSDictionary *snapshot;
  dispatch_sync(_queue, ^{ [self loadLocked]; snapshot = [self snapshotLocked]; });
  return snapshot;
}

- (void)loadWithCompletion:(void (^)(NSDictionary *, NSError *))completion {
  dispatch_async(_queue, ^{
    [self loadLocked];
    NSDictionary *snapshot = [self snapshotLocked];
    NSError *error = self->_index ? nil : CatalogError(3, @"catalogueMissing", @"No HD texture catalogue yet");
    dispatch_async(dispatch_get_main_queue(), ^{ completion(snapshot, error); });
  });
}

- (void)writeState:(NSDictionary *)state {
  _state = state;
  NeoTexWriteAtomic(NeoTexJSONData(state), self.statePath, nil);
}

- (void)refreshWithCompletion:(void (^)(NSDictionary *, NSError *))completion {
  dispatch_async(_queue, ^{
    [self loadLocked];
    [self->_refreshWaiters addObject:[completion copy]];
    if (self->_refreshing) return;
    self->_refreshing = YES;
    [self announce:@{@"catalogue": @YES}];
    NSURL *url = self.manifestURL;
    void (^finish)(NSData *, NSError *) = ^(NSData *data, NSError *fetchError) {
      dispatch_async(self->_queue, ^{
        NSError *error = fetchError;
        NSDictionary *index = error ? nil : [NeoTextureCatalog validatedIndex:data error:&error];
        NSMutableDictionary *state = [self->_state mutableCopy] ?: [NSMutableDictionary dictionary];
        if (index) {
          // Preserve the validated source descriptor, not the in-memory
          // capability expansion. A later launch must validate/expand it
          // again, and an older app must still see its manual fallback.
          // validatedIndex accepts either source JSON or gzip on reload.
          if (!NeoTexWriteAtomic(data, self.cachedIndexPath, &error)) index = nil;
        }
        if (index) {
          self->_index = index;
          self->_origin = @"downloaded";
          state[@"refreshed_at"] = @((long long)NSDate.date.timeIntervalSince1970);
          [state removeObjectForKey:@"refresh_error"];
          [state removeObjectForKey:@"failed_at"];
        } else {
          // Keep the last valid index; remember why this attempt failed.
          state[@"refresh_error"] = error.userInfo[@"key"] ?: @"catalogueUnavailable";
          state[@"failed_at"] = @((long long)NSDate.date.timeIntervalSince1970);
          if (!error) error = CatalogError(4, @"catalogueUnavailable", @"Refresh failed");
        }
        [self writeState:state];
        self->_refreshing = NO;
        NSDictionary *snapshot = [self snapshotLocked];
        NSArray *waiters = [self->_refreshWaiters copy];
        [self->_refreshWaiters removeAllObjects];
        NSError *reported = index ? nil : error;
        dispatch_async(dispatch_get_main_queue(), ^{
          for (void (^waiter)(NSDictionary *, NSError *) in waiters) waiter(snapshot, reported);
          [[NSNotificationCenter defaultCenter] postNotificationName:NeoTextureCatalogDidChangeNotification object:self userInfo:@{@"catalogue": @YES}];
        });
      });
    };
    if (self.fetch) self.fetch(url, IndexCompressedLimit, finish);
    else NeoTexFetchData(url, IndexCompressedLimit, finish);
  });
}

- (void)announce:(NSDictionary *)info {
  dispatch_async(dispatch_get_main_queue(), ^{
    [[NSNotificationCenter defaultCenter] postNotificationName:NeoTextureCatalogDidChangeNotification object:self userInfo:info];
  });
}

#pragma mark - Queries

- (NSArray *)packsLocked {
  [self loadLocked];
  return _index[@"packs"] ?: @[];
}

- (NSArray<NSDictionary *> *)packsForSystem:(NSString *)system engine:(NSString *)engine {
  __block NSArray *packs;
  dispatch_sync(_queue, ^{ packs = [self packsLocked]; });
  NSString *wanted = NeoTexCanonicalSystem(system);
  NSMutableArray *rows = [NSMutableArray array];
  for (NSDictionary *pack in packs)
    if ([PackSystems(pack) containsObject:wanted] && [pack[@"engine"] isEqual:engine]) [rows addObject:pack];
  [rows sortUsingComparator:^NSComparisonResult(NSDictionary *a, NSDictionary *b) {
    NSComparisonResult order = [NeoTexString([a[@"games"] firstObject][@"title"]) localizedCaseInsensitiveCompare:NeoTexString([b[@"games"] firstObject][@"title"])];
    return order != NSOrderedSame ? order : [NeoTexString(a[@"title"]) localizedCaseInsensitiveCompare:NeoTexString(b[@"title"])];
  }];
  return rows;
}

- (NSArray<NSDictionary *> *)packsForIdentity:(NSDictionary *)identity engine:(NSString *)engine {
  NSMutableArray *exact = [NSMutableArray array], *candidates = [NSMutableArray array];
  for (NSDictionary *pack in [self packsForSystem:NeoTexString(identity[@"system"]) engine:engine]) {
    NSDictionary *row = [NeoTextureCatalog pack:pack matchedTo:identity];
    NSString *match = row[@"match"];
    if (!match) continue;
    [[match isEqualToString:@"exact"] ? exact : candidates addObject:row];
  }
  [exact addObjectsFromArray:candidates];
  return exact;
}

+ (NSDictionary *)pack:(NSDictionary *)pack matchedTo:(NSDictionary *)identity {
  NSMutableDictionary *row = [pack mutableCopy];
  NSString *match = [NeoTextureCatalog matchPack:pack identity:identity];
  // An identifier taken from a file name never makes a pack "compatible" on its own.
  if (match && [identity[@"uncertain"] boolValue]) match = @"candidate";
  row[@"match"] = match;
  return row;
}

- (NSDictionary *)packWithID:(NSString *)packID {
  __block NSDictionary *found;
  dispatch_sync(_queue, ^{
    for (NSDictionary *pack in [self packsLocked]) if ([pack[@"id"] isEqual:packID]) { found = pack; break; }
  });
  return found;
}

+ (NSString *)matchPack:(NSDictionary *)pack identity:(NSDictionary *)identity {
  if (![pack isKindOfClass:NSDictionary.class] || ![identity isKindOfClass:NSDictionary.class]) return nil;
  if (![PackSystems(pack) containsObject:NeoTexCanonicalSystem(identity[@"system"])]) return nil;
  NSDictionary *wanted = NeoTexTypedIdentities(identity[@"identities"]);
  NSString *gameRevision = NeoTexString(identity[@"revision"]);
  NSSet *gameRegions = NeoTexRegions(identity[@"regions"]);
  NSString *gameTitle = NeoTexFoldTitle(identity[@"title"]);
  BOOL candidate = NO;
  for (NSDictionary *entry in pack[@"games"]) {
    NSDictionary *declared = NeoTexTypedIdentities(entry[@"identities"]);
    NSString *revision = NeoTexString(entry[@"revision"]);
    NSSet *regions = NeoTexRegions(entry[@"regions"]);
    BOOL revisionConflict = revision.length && gameRevision.length && ![revision isEqualToString:gameRevision];
    BOOL regionConflict = regions.count && gameRegions.count && ![regions intersectsSet:gameRegions];
    BOOL sameID = NO, differentID = NO;
    for (NSString *key in declared) {
      NSSet *values = declared[key];
      // A region-free Dolphin folder (3 characters) serves every region of the family.
      if ([key isEqualToString:@"game_id|dolphin-region-free-id"]) {
        for (NSString *value in wanted[@"game_id|dolphin-disc-game-id"] ?: [NSSet set])
          if (value.length == 6 && [values containsObject:[value substringToIndex:3]]) sameID = YES;
        continue;
      }
      NSSet *requested = wanted[key];
      if (!requested) continue;
      if ([values intersectsSet:requested]) sameID = YES;
      else differentID = YES;
    }
    // "confirm": the identities come from a games database, not from the author:
    // never an exact match, only offered for an explicit confirmation.
    if (sameID && !revisionConflict && !regionConflict && ![entry[@"confirm"] boolValue]) return @"exact";
    // The same game in another region or revision: never assumed compatible,
    // only offered for an explicit confirmation when the titles agree.
    NSString *title = NeoTexFoldTitle(entry[@"title"]);
    BOOL titleMatches = title.length >= 4 && gameTitle.length >= 4 &&
        ([title isEqualToString:gameTitle] || [title hasPrefix:gameTitle] || [gameTitle hasPrefix:title]);
    if (titleMatches || sameID) candidate = YES;
    (void)differentID;
  }
  return candidate ? @"candidate" : nil;
}

@end

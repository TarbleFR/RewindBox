// SPDX-License-Identifier: GPL-3.0-or-later
// HD texture packs of the embedded ARMSX2 engine (Build 485). See the header.
#import "ARMSX2TexturePackStore.h"
#import <Metal/Metal.h>
#include "ARMSX2TexturePackCore.h"

#include <atomic>

namespace T = NeoARMSX2Textures;

static NSString* const kStateName = @"NeoStation-textures.json";
static const NSUInteger kMaxIdentities = 4000;

static NSString* Str(const std::string& value) { return [NSString stringWithUTF8String:value.c_str()] ?: @""; }
static NSArray<NSString*>* Strs(const std::set<std::string>& values) {
  NSMutableArray* out = [NSMutableArray array];
  for (const std::string& value : values) [out addObject:Str(value)];
  return out;
}
static NSString* Field(id value) { return [value isKindOfClass:NSString.class] ? value : @""; }

static uint64_t FreeBytes(NSString* path) {
  // ARMSX2 creates <data>/textures at its first game: measure the nearest existing folder.
  while (path.length > 1 && ![NSFileManager.defaultManager fileExistsAtPath:path]) path = path.stringByDeletingLastPathComponent;
  NSNumber* important = nil;
  [[NSURL fileURLWithPath:path] getResourceValue:&important forKey:NSURLVolumeAvailableCapacityForImportantUsageKey error:nil];
  if (important.unsignedLongLongValue) return important.unsignedLongLongValue;
  NSDictionary* attributes = [NSFileManager.defaultManager attributesOfFileSystemForPath:path error:nil];
  return [attributes[NSFileSystemFreeSize] unsignedLongLongValue];
}

static NSString* Timestamp(void) {
  NSISO8601DateFormatter* formatter = [NSISO8601DateFormatter new];
  return [formatter stringFromDate:NSDate.date];
}

// PCSX2 INI booleans (INISettingsInterface: "true"/"false"), [EmuCore/GS] only.
static NSNumber* IniBool(NSString* path, NSString* key) {
  NSString* text = [NSString stringWithContentsOfFile:path encoding:NSUTF8StringEncoding error:nil];
  if (!text) return nil;
  BOOL inSection = NO;
  NSNumber* value = nil;
  for (NSString* raw in [text componentsSeparatedByCharactersInSet:NSCharacterSet.newlineCharacterSet]) {
    NSString* line = [raw stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet];
    if ([line hasPrefix:@"["]) { inSection = [line isEqualToString:@"[EmuCore/GS]"]; continue; }
    if (!inSection) continue;
    NSRange equals = [line rangeOfString:@"="];
    if (equals.location == NSNotFound) continue;
    NSString* name = [[line substringToIndex:equals.location] stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet];
    if (![name isEqualToString:key]) continue;
    NSString* setting = [[line substringFromIndex:equals.location + 1] stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet].lowercaseString;
    value = @([setting isEqualToString:@"true"] || [setting isEqualToString:@"1"] || [setting isEqualToString:@"yes"] || [setting isEqualToString:@"on"]);
  }
  return value;
}

@implementation ARMSX2TexturePackStore

+ (NSString*)texturesRootForDataPath:(NSString*)dataPath {
  return [dataPath stringByAppendingPathComponent:@"textures"];
}

+ (NSString*)statePathForDataPath:(NSString*)dataPath {
  return [[dataPath stringByAppendingPathComponent:@"inis"] stringByAppendingPathComponent:kStateName];
}

+ (NSLock*)stateLock {
  static NSLock* lock;
  static dispatch_once_t once;
  dispatch_once(&once, ^{ lock = [NSLock new]; });
  return lock;
}

// Caller holds the lock.
+ (NSMutableDictionary*)loadState:(NSString*)dataPath {
  NSData* data = [NSData dataWithContentsOfFile:[self statePathForDataPath:dataPath]];
  id decoded = data.length ? [NSJSONSerialization JSONObjectWithData:data options:NSJSONReadingMutableContainers error:nil] : nil;
  NSMutableDictionary* state = [decoded isKindOfClass:NSMutableDictionary.class] ? decoded : [NSMutableDictionary dictionary];
  if (![state[@"games"] isKindOfClass:NSMutableDictionary.class]) state[@"games"] = [NSMutableDictionary dictionary];
  if (![state[@"identities"] isKindOfClass:NSMutableDictionary.class]) state[@"identities"] = [NSMutableDictionary dictionary];
  state[@"schema"] = @1;
  return state;
}

+ (BOOL)saveState:(NSDictionary*)state dataPath:(NSString*)dataPath {
  NSString* path = [self statePathForDataPath:dataPath];
  [NSFileManager.defaultManager createDirectoryAtPath:path.stringByDeletingLastPathComponent
                          withIntermediateDirectories:YES attributes:nil error:nil];
  NSData* data = [NSJSONSerialization dataWithJSONObject:state options:NSJSONWritingSortedKeys error:nil];
  return data && [data writeToFile:path options:NSDataWritingAtomic error:nil];
}

static NSString* IdentityKey(NSString* gamePath) {
  NSDictionary* attributes = [NSFileManager.defaultManager attributesOfItemAtPath:gamePath error:nil];
  if (!attributes) return nil;
  return [NSString stringWithFormat:@"%@|%llu", gamePath.lastPathComponent, [attributes[NSFileSize] unsignedLongLongValue]];
}

+ (NSDictionary*)identifyGameAtPath:(NSString*)gamePath dataPath:(NSString*)dataPath {
  NSString* key = IdentityKey(gamePath);
  NSDictionary* recorded = nil;
  if (key) {
    [[self stateLock] lock];
    recorded = [[self loadState:dataPath][@"identities"][key] copy];
    [[self stateLock] unlock];
  }
  if (![recorded isKindOfClass:NSDictionary.class]) recorded = nil;
  NSString* serial = Field(recorded[@"serial"]);
  if (recorded && T::IsStoreSerial(serial.UTF8String)) {
    return @{@"serial": serial, @"crc": Field(recorded[@"crc"]), @"version": Field(recorded[@"version"]),
             @"title": Field(recorded[@"title"]), @"source": @"session", @"region": Str(T::RegionOfSerial(serial.UTF8String))};
  }
  NSString* extension = gamePath.pathExtension.lowercaseString;
  // Plain and raw CD/DVD images only: compressed containers are never decoded here.
  if ([@[@"iso", @"bin", @"img", @"mdf"] containsObject:extension]) {
    const auto identity = T::ReadDiscIdentity(gamePath.fileSystemRepresentation);
    if (identity && T::IsStoreSerial(identity->serial))
      return @{@"serial": Str(identity->serial), @"crc": @"", @"version": Str(identity->version), @"title": @"",
               @"source": @"disc", @"region": Str(T::RegionOfSerial(identity->serial))};
  }
  const std::string named = T::Normalized(TexturePackPaths::FindSerial(gamePath.lastPathComponent.UTF8String ?: ""));
  if (T::IsStoreSerial(named))
    return @{@"serial": Str(named), @"crc": @"", @"version": @"", @"title": @"", @"source": @"name",
             @"region": Str(T::RegionOfSerial(named))};
  return @{@"serial": @"", @"crc": @"", @"version": @"", @"title": @"", @"source": @"none", @"region": @""};
}

+ (void)recordIdentity:(NSDictionary*)identity forGamePath:(NSString*)gamePath dataPath:(NSString*)dataPath {
  NSString* serial = Field(identity[@"serial"]);
  NSString* key = IdentityKey(gamePath);
  if (!key || !T::IsStoreSerial(serial.UTF8String)) return;
  [[self stateLock] lock];
  NSMutableDictionary* state = [self loadState:dataPath];
  NSMutableDictionary* identities = state[@"identities"];
  identities[key] = @{@"serial": serial, @"crc": Field(identity[@"crc"]), @"version": Field(identity[@"version"]),
                      @"title": Field(identity[@"title"]), @"updated": Timestamp()};
  if (identities.count > kMaxIdentities) {
    NSArray* oldest = [identities keysSortedByValueUsingComparator:^NSComparisonResult(NSDictionary* a, NSDictionary* b) {
      return [Field(a[@"updated"]) compare:Field(b[@"updated"])];
    }];
    [identities removeObjectsForKeys:[oldest subarrayWithRange:NSMakeRange(0, identities.count - kMaxIdentities)]];
  }
  [self saveState:state dataPath:dataPath];
  [[self stateLock] unlock];
}

+ (NSDictionary*)statusForSerial:(NSString*)serial crc:(NSString*)crc dataPath:(NSString*)dataPath {
  NSMutableDictionary* status = [@{@"serial": serial ?: @"", @"installed": @NO, @"external": @NO} mutableCopy];
  if (!T::IsStoreSerial(serial.UTF8String ?: "")) return status;
  const T::fs::path root([self texturesRootForDataPath:dataPath].fileSystemRepresentation);
  const T::fs::path folder = root / serial.UTF8String, replacements = folder / T::kReplacements;
  status[@"folder"] = [NSString stringWithFormat:@"ARMSX2/textures/%@/replacements", serial];
  const bool installed = T::IsRealDirectory(replacements);
  status[@"installed"] = @(installed);
  NSData* data = [NSData dataWithContentsOfFile:Str((folder / T::kManifest).string())];
  id manifest = data.length && data.length < 1024 * 1024 ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
  if (installed && [manifest isKindOfClass:NSDictionary.class] && [manifest[@"serial"] isEqual:serial]) {
    for (NSString* key in @[@"files", @"bytes", @"named", @"mips", @"unsupported", @"formats", @"source", @"sourceKind",
                            @"installedAt", @"packSerial", @"match", @"regions", @"versions", @"crcs"])
      if (manifest[key]) status[key] = manifest[key];
  } else if (installed) {
    // Copied into ARMSX2/textures without NeoStation: describe what is there.
    const T::Inventory inventory = T::ScanInstalled(replacements);
    NSMutableDictionary* formats = [NSMutableDictionary dictionary];
    for (const auto& [format, count] : inventory.formats) formats[Str(format)] = @(count);
    [status addEntriesFromDictionary:@{@"external": @YES, @"files": @(inventory.files), @"bytes": @(inventory.bytes),
                                        @"named": @(inventory.named), @"mips": @(inventory.mips),
                                        @"unsupported": @(inventory.unsupported), @"formats": formats}];
  }
  [[self stateLock] lock];
  id enabled = [self loadState:dataPath][@"games"][serial];
  [[self stateLock] unlock];
  status[@"enabled"] = [enabled isKindOfClass:NSNumber.class] ? enabled : NSNull.null;
  NSString* inis = [dataPath stringByAppendingPathComponent:@"inis"];
  NSString* games = [dataPath stringByAppendingPathComponent:@"gamesettings"];
  if (crc.length == 8)
    status[@"iniEnabled"] = IniBool([games stringByAppendingPathComponent:
        [NSString stringWithFormat:@"%@_%@.ini", serial, crc.uppercaseString]], @"LoadTextureReplacements") ?: NSNull.null;
  status[@"globalEnabled"] = IniBool([inis stringByAppendingPathComponent:@"PCSX2.ini"], @"LoadTextureReplacements") ?: @NO;
  return status;
}

+ (BOOL)setEnabled:(BOOL)enabled serial:(NSString*)serial dataPath:(NSString*)dataPath {
  if (!T::IsStoreSerial(serial.UTF8String ?: "")) return NO;
  [[self stateLock] lock];
  NSMutableDictionary* state = [self loadState:dataPath];
  state[@"games"][serial] = @(enabled);
  const BOOL saved = [self saveState:state dataPath:dataPath];
  [[self stateLock] unlock];
  return saved;
}

+ (NSDictionary*)removeSerial:(NSString*)serial dataPath:(NSString*)dataPath {
  if (!T::IsStoreSerial(serial.UTF8String ?: "")) return @{@"success": @NO, @"error": @"invalid"};
  NSString* root = [self texturesRootForDataPath:dataPath];
  NSString* removing = [root stringByAppendingPathComponent:
      [NSString stringWithFormat:@"%s%@", T::kRemovingPrefix, NSUUID.UUID.UUIDString]];
  std::string error;
  if (!T::RemovePack(root.fileSystemRepresentation, serial.UTF8String, removing.fileSystemRepresentation, error))
    return @{@"success": @NO, @"error": Str(error)};
  // The engine is told to stop using the folder at the game's next start.
  [self setEnabled:NO serial:serial dataPath:dataPath];
  return @{@"success": @YES, @"removingPath": removing};
}

+ (NSString*)bootPreferencesJSONForDataPath:(NSString*)dataPath {
  [[self stateLock] lock];
  NSDictionary* games = [[self loadState:dataPath][@"games"] copy];
  [[self stateLock] unlock];
  NSData* data = [NSJSONSerialization dataWithJSONObject:@{@"games": games ?: @{}} options:0 error:nil];
  return [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] ?: @"{\"games\":{}}";
}

// Same queries as GSDeviceMTL::Create of the pinned engine: BC1-3/BC7 natively
// when the GPU samples BC, otherwise decoded to RGBA8 by the CPU; ASTC on Apple2+.
+ (NSDictionary*)deviceFormats {
  id<MTLDevice> device = MTLCreateSystemDefaultDevice();
  BOOL bc = NO;
  if (@available(iOS 16.4, *)) bc = device.supportsBCTextureCompression;
  return @{@"bcTextures": @(bc), @"astcTextures": @([device supportsFamily:MTLGPUFamilyApple2])};
}

+ (void)discardPath:(NSString*)path {
  if (!path.length) return;
  dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
    std::error_code ignored;
    T::fs::remove_all(path.fileSystemRepresentation, ignored);
  });
}

+ (void)sweepLeftoversInDataPath:(NSString*)dataPath {
  T::SweepLeftovers([self texturesRootForDataPath:dataPath].fileSystemRepresentation);
}

@end

@implementation ARMSX2TextureImport {
  NSURL* _url;
  BOOL _scoped;
  NSString* _dataPath;
  NSDictionary* _game;
  ARMSX2TextureExpander _expander;
  volatile int _cancel;
  volatile uint64_t _consumed;
  NSString* _kind;
  NSString* _sourceName;
  NSString* _expanded;
  T::Source _source;
  T::Plan _plan;
  T::Verdict _verdict;
  NSDictionary* _inspection;
  BOOL _catalogueExpansion;
}

- (instancetype)initWithURL:(NSURL*)url dataPath:(NSString*)dataPath game:(NSDictionary*)game
                   expander:(ARMSX2TextureExpander)expander {
  self = [super init];
  if (self) {
    _token = NSUUID.UUID.UUIDString;
    _url = url;
    _scoped = [url startAccessingSecurityScopedResource];
    _dataPath = [dataPath copy];
    _game = [game copy] ?: @{};
    _serial = Field(_game[@"serial"]);
    _expander = [expander copy];
    _sourceName = url.lastPathComponent ?: @"";
  }
  return self;
}

- (instancetype)initWithExpandedFolder:(NSString*)folder sourceName:(NSString*)sourceName
                              dataPath:(NSString*)dataPath game:(NSDictionary*)game {
  // Only a folder of this store's expanded kind, directly below its root.
  NSString* root = [ARMSX2TexturePackStore texturesRootForDataPath:dataPath];
  if (![folder.stringByDeletingLastPathComponent isEqualToString:root] ||
      ![folder.lastPathComponent hasPrefix:[NSString stringWithUTF8String:T::kExpandedPrefix]])
    return nil;
  self = [self initWithURL:[NSURL fileURLWithPath:folder isDirectory:YES] dataPath:dataPath game:game expander:nil];
  if (self) {
    _expanded = [folder copy];
    _sourceName = [sourceName copy] ?: @"";
    _catalogueExpansion = YES;
  }
  return self;
}

- (void)dealloc { [self close]; }

- (void)cancel { _cancel = 1; }

- (void)close {
  if (_scoped) { [_url stopAccessingSecurityScopedResource]; _scoped = NO; }
  if (_catalogueExpansion && _expanded.length) {
    // The catalogue also owns this folder. Finish before returning to its
    // worker so its cleanup cannot race an asynchronous walk of the same tree.
    std::error_code ignored;
    T::fs::remove_all(_expanded.fileSystemRepresentation, ignored);
  } else [ARMSX2TexturePackStore discardPath:_expanded];
  _expanded = nil;
}

- (NSString*)root { return [ARMSX2TexturePackStore texturesRootForDataPath:_dataPath]; }

static NSDictionary* Failure(NSString* error, NSString* detail) {
  return @{@"success": @NO, @"error": error, @"detail": detail ?: @""};
}

// Opens the chosen item. Called inside a coordinated read of _url.
- (NSString*)openAt:(NSURL*)url progress:(ARMSX2TextureProgress)progress {
  NSNumber* directory = nil;
  [url getResourceValue:&directory forKey:NSURLIsDirectoryKey error:nil];
  NSString* name = url.lastPathComponent.lowercaseString;
  _source = {};
  if (_catalogueExpansion) {
    // Expanded by the catalogue on this volume: moved like an expanded .tar.zst.
    _kind = @"catalogue";
    _source.kind = T::SourceKind::Folder;
    _source.moveFiles = true;
    _source.path = _expanded.fileSystemRepresentation;
    return T::OpenSource(_source) ? nil : Str(_source.error);
  }
  if (directory.boolValue) { _kind = @"folder"; _source.kind = T::SourceKind::Folder; }
  else if ([name hasSuffix:@".zip"]) { _kind = @"zip"; _source.kind = T::SourceKind::Zip; }
  else if ([name hasSuffix:@".tar"]) { _kind = @"tar"; _source.kind = T::SourceKind::Tar; }
  else if ([name hasSuffix:@".tar.zst"] || [name hasSuffix:@".tzst"] || [name hasSuffix:@".zst"]) {
    _kind = @"tarzst";
    if (!_expander) return @"zstdNeedsGame";
    if (!_expanded) {
      NSString* destination = [[self root] stringByAppendingPathComponent:
          [NSString stringWithFormat:@"%s%@", T::kExpandedPrefix, _token]];
      [NSFileManager.defaultManager createDirectoryAtPath:destination withIntermediateDirectories:YES attributes:nil error:nil];
      _expanded = destination;
      NSNumber* size = nil;
      [url getResourceValue:&size forKey:NSURLFileSizeKey error:nil];
      __block NSString* failure = nil;
      dispatch_semaphore_t done = dispatch_semaphore_create(0);
      ARMSX2TextureExpander expander = _expander;
      NSString* archive = url.path;
      const uint64_t available = FreeBytes([self root]);
      const volatile int* cancel = &_cancel;
      volatile uint64_t* consumed = &_consumed;
      dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        failure = expander(archive, destination, available, cancel, consumed);
        dispatch_semaphore_signal(done);
      });
      while (dispatch_semaphore_wait(done, dispatch_time(DISPATCH_TIME_NOW, 200 * NSEC_PER_MSEC)) != 0)
        if (progress) progress(size.unsignedLongLongValue ? std::min(1.0, (double)_consumed / size.doubleValue) : -1, @"expanding");
      if (failure) return failure;
    }
    _source.kind = T::SourceKind::Folder;
    _source.moveFiles = true;
    _source.path = _expanded.fileSystemRepresentation;
    return T::OpenSource(_source) ? nil : Str(_source.error);
  } else return @"format";
  _source.path = url.path.fileSystemRepresentation;
  return T::OpenSource(_source) ? nil : Str(_source.error);
}

- (NSDictionary*)inspectWithProgress:(ARMSX2TextureProgress)progress {
  __block NSString* failure = nil;
  NSError* coordination = nil;
  [[[NSFileCoordinator alloc] initWithFilePresenter:nil] coordinateReadingItemAtURL:_url options:0
      error:&coordination byAccessor:^(NSURL* url) { failure = [self openAt:url progress:progress]; }];
  if (coordination && !failure) failure = @"unreadable";
  if (failure) {
    NSString* detail = [failure isEqual:@"unsafe"] && !_source.entries.empty() ? Str(_source.entries.back().name) : @"";
    if ([failure hasPrefix:@"method:"]) { detail = [failure substringFromIndex:7]; failure = @"method"; }
    return _inspection = Failure(failure, detail);
  }
  const std::string serial = _serial.UTF8String ?: "";
  _plan = T::BuildPlan(_source.entries, _sourceName.UTF8String ?: "", serial);
  _verdict = T::Judge(_plan, serial);
  NSMutableDictionary* inspection = [@{
    @"success": @(_plan.error.empty()), @"token": _token, @"kind": _kind ?: @"", @"source": _sourceName,
    @"error": Str(_plan.error), @"detail": Str(_plan.detail),
    @"files": @(_plan.files.size()), @"bytes": @(_plan.bytes), @"skipped": @(_plan.skipped), @"excluded": @(_plan.excluded),
    @"packSerial": Str(_verdict.packSerial), @"packRegion": Str(T::RegionOfSerial(_verdict.packSerial)),
    @"packSerials": Strs(_plan.packSerials), @"match": Str(_verdict.match), @"regionConflict": @(_verdict.regionConflict),
    @"regions": Strs(_plan.hints.regions), @"versions": Strs(_plan.hints.versions), @"crcs": Strs(_plan.hints.crcs),
    @"gameSerial": _serial, @"gameRegion": Str(T::RegionOfSerial(serial)), @"gameVersion": Field(_game[@"version"]),
    @"gameCrc": Field(_game[@"crc"]), @"serialSource": Field(_game[@"source"]),
  } mutableCopy];
  if (_plan.error.empty() && _verdict.match != "gameUnknown") {
    // A pack naming a CRC other than the running game's, or a serial taken from a
    // file name, is explained like a different serial.
    NSString* crc = Field(_game[@"crc"]).uppercaseString;
    const BOOL crcConflict = crc.length == 8 && !_plan.hints.crcs.empty() && !_plan.hints.crcs.count(crc.UTF8String);
    const BOOL uncertain = [Field(_game[@"source"]) isEqual:@"name"];
    inspection[@"crcConflict"] = @(crcConflict);
    inspection[@"uncertain"] = @(uncertain);
    inspection[@"needsConfirmation"] = @(![Str(_verdict.match) isEqual:@"same"] || _verdict.regionConflict || crcConflict || uncertain);
    NSDictionary* existing = [ARMSX2TexturePackStore statusForSerial:_serial crc:nil dataPath:_dataPath];
    inspection[@"replacing"] = existing[@"installed"] ?: @NO;
    const uint64_t available = FreeBytes([self root]);
    inspection[@"available"] = @(available);
    inspection[@"needed"] = @(_plan.bytes + T::kSpareBytes);
    if (!_source.moveFiles && (available < _plan.bytes || available - _plan.bytes < T::kSpareBytes)) {
      inspection[@"success"] = @NO;
      inspection[@"error"] = @"space";
    }
  } else if (_plan.error.empty()) {
    inspection[@"success"] = @NO;
    inspection[@"error"] = @"gameUnknown";
  }
  return _inspection = inspection;
}

- (NSDictionary*)installAllowingMismatch:(BOOL)allow progress:(ARMSX2TextureProgress)progress {
  if (![_inspection[@"success"] boolValue]) return Failure(@"notInspected", nil);
  if ([_inspection[@"needsConfirmation"] boolValue] && !allow) return Failure(@"confirmationRequired", nil);
  NSString* root = [self root];
  NSString* staging = [root stringByAppendingPathComponent:[NSString stringWithFormat:@"%s%@", T::kStagingPrefix, _token]];
  __block std::string error;
  __block T::Inventory inventory;
  const uint64_t files = _plan.files.size(), bytes = _plan.bytes;
  void (^stage)(NSURL*) = ^(NSURL* url) {
    if (!self->_source.moveFiles) {
      // The pack is listed again inside this coordinated read: it must not have changed.
      self->_source.path = url.path.fileSystemRepresentation;
      if (!T::OpenSource(self->_source)) { error = self->_source.error; return; }
      self->_plan = T::BuildPlan(self->_source.entries, self->_sourceName.UTF8String ?: "", self->_serial.UTF8String ?: "");
      if (!self->_plan.error.empty() || self->_plan.files.size() != files || self->_plan.bytes != bytes) { error = "changed"; return; }
    }
    T::StageFiles(self->_source, self->_plan, staging.fileSystemRepresentation, FreeBytes(root), inventory,
                  [&](uint64_t done, uint64_t total) {
                    if (progress) progress(total ? (double)done / (double)total : 1.0, @"installing");
                    return self->_cancel == 0;
                  }, error);
  };
  if (_source.moveFiles) stage(nil);
  else {
    NSError* coordination = nil;
    [[[NSFileCoordinator alloc] initWithFilePresenter:nil] coordinateReadingItemAtURL:_url options:0
        error:&coordination byAccessor:stage];
    if (coordination && error.empty()) error = "unreadable";
  }
  if (!error.empty() || _cancel) {
    std::error_code ignored;
    T::fs::remove_all(staging.fileSystemRepresentation, ignored);
    NSString* key = _cancel ? @"cancelled" : Str(error);
    if ([key hasPrefix:@"method:"]) return Failure(@"method", [key substringFromIndex:7]);
    if ([key isEqual:@"space"])
      return @{@"success": @NO, @"error": key, @"detail": @"", @"needed": @(bytes + T::kSpareBytes), @"available": @(FreeBytes(root))};
    return Failure(key, nil);
  }
  const std::string manifest = T::ManifestJSON(_serial.UTF8String, _sourceName.UTF8String ?: "", _kind.UTF8String, _plan,
                                               _verdict, inventory, Timestamp().UTF8String);
  NSString* previous = [root stringByAppendingPathComponent:[NSString stringWithFormat:@"%s%@", T::kPreviousPrefix, _token]];
  bool hadPrevious = false;
  if (!T::CommitStaged(root.fileSystemRepresentation, _serial.UTF8String, staging.fileSystemRepresentation, manifest,
                       previous.fileSystemRepresentation, hadPrevious, error)) {
    std::error_code ignored;
    T::fs::remove_all(staging.fileSystemRepresentation, ignored);
    return Failure(Str(error), nil);
  }
  // A first pack turns HD textures on for the game; a replacement keeps its choice.
  if (!hadPrevious) [ARMSX2TexturePackStore setEnabled:YES serial:_serial dataPath:_dataPath];
  NSMutableDictionary* formats = [NSMutableDictionary dictionary];
  for (const auto& [format, count] : inventory.formats) formats[Str(format)] = @(count);
  NSMutableArray* samples = [NSMutableArray array];
  for (const std::string& sample : inventory.unsupportedSamples) [samples addObject:Str(sample)];
  return @{@"success": @YES, @"serial": _serial, @"replaced": @(hadPrevious),
           @"previousPath": hadPrevious ? previous : @"", @"files": @(inventory.files), @"bytes": @(inventory.bytes),
           @"named": @(inventory.named), @"mips": @(inventory.mips), @"unsupported": @(inventory.unsupported),
           @"unsupportedSamples": samples, @"formats": formats, @"excluded": @(_plan.excluded)};
}

@end

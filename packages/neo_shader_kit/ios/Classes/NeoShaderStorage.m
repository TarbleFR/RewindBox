// SPDX-License-Identifier: GPL-3.0-or-later
#import "NeoShaderStorage.h"

#import <CommonCrypto/CommonDigest.h>

NSString *const NeoShaderErrorEntryInvalid = @"ENTRY_INVALID";
NSString *const NeoShaderErrorEntryTooLarge = @"ENTRY_TOO_LARGE";
NSString *const NeoShaderErrorNoDownloadURL = @"DOWNLOAD_URL";
NSString *const NeoShaderErrorNetwork = @"DOWNLOAD_NETWORK";
NSString *const NeoShaderErrorHTTPStatus = @"DOWNLOAD_HTTP";
NSString *const NeoShaderErrorSizeMismatch = @"DOWNLOAD_SIZE";
NSString *const NeoShaderErrorHashMismatch = @"DOWNLOAD_HASH";
NSString *const NeoShaderErrorCancelled = @"DOWNLOAD_CANCELLED";
NSString *const NeoShaderErrorStorageSpace = @"STORAGE_SPACE";
NSString *const NeoShaderErrorStorageWrite = @"STORAGE_WRITE";
NSString *const NeoShaderErrorBusy = @"DOWNLOAD_BUSY";
NSString *const NeoShaderErrorProfileName = @"PROFILE_NAME";
NSString *const NeoShaderErrorProfileLimit = @"PROFILE_LIMIT";

static NSString *const kStorageErrorDomain = @"NeoShaderStorage";
/// Files downloaded at once for one entry.
static const NSUInteger kParallelDownloads = 4;
static const NSUInteger kMaximumProfiles = 200;
static const NSUInteger kMaximumProfileName = 64;

#pragma mark - Helpers

static NSString *HexDigest(const unsigned char *digest) {
  NSMutableString *hex = [NSMutableString stringWithCapacity:CC_SHA256_DIGEST_LENGTH * 2];
  for (int index = 0; index < CC_SHA256_DIGEST_LENGTH; index++) [hex appendFormat:@"%02x", digest[index]];
  return hex;
}

static NSString *DataSHA256(NSData *data) {
  unsigned char digest[CC_SHA256_DIGEST_LENGTH];
  CC_SHA256(data.bytes, (CC_LONG)data.length, digest);
  return HexDigest(digest);
}

/// SHA-256 of a regular file read in chunks; nil when unreadable.
static NSString *FileSHA256(NSString *path) {
  NSFileHandle *handle = [NSFileHandle fileHandleForReadingAtPath:path];
  if (handle == nil) return nil;
  CC_SHA256_CTX context;
  CC_SHA256_Init(&context);
  while (YES) {
    @autoreleasepool {
      NSData *chunk = [handle readDataUpToLength:1 << 20 error:nil];
      if (chunk == nil) {
        [handle closeFile];
        return nil;
      }
      if (chunk.length == 0) break;
      CC_SHA256_Update(&context, chunk.bytes, (CC_LONG)chunk.length);
    }
  }
  [handle closeFile];
  unsigned char digest[CC_SHA256_DIGEST_LENGTH];
  CC_SHA256_Final(digest, &context);
  return HexDigest(digest);
}

/// Size of a regular file (not a link), -1 otherwise.
static long long RegularFileSize(NSString *path) {
  NSDictionary *attributes = [NSFileManager.defaultManager attributesOfItemAtPath:path error:nil];
  if (attributes == nil || ![attributes.fileType isEqualToString:NSFileTypeRegular]) return -1;
  return (long long)attributes.fileSize;
}

static NSString *ISODate(NSDate *date) {
  static NSISO8601DateFormatter *formatter;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    formatter = [NSISO8601DateFormatter new];
  });
  return [formatter stringFromDate:date];
}

static NSDate *DateFromISO(id value) {
  if (![value isKindOfClass:NSString.class]) return [NSDate dateWithTimeIntervalSince1970:0];
  NSDate *date = [[NSISO8601DateFormatter new] dateFromString:value];
  return date ?: [NSDate dateWithTimeIntervalSince1970:0];
}

/// A repository-relative path as the catalog accepts them: no "..", no
/// absolute path, no empty or "." segment, no backslash or control byte.
static BOOL SafeRelativePath(NSString *path) {
  if (![path isKindOfClass:NSString.class] || path.length == 0 || path.length > 512) return NO;
  if ([path hasPrefix:@"/"] || [path rangeOfString:@"\\"].location != NSNotFound) return NO;
  for (NSString *segment in [path componentsSeparatedByString:@"/"]) {
    if (segment.length == 0 || [segment isEqualToString:@"."] || [segment isEqualToString:@".."]) return NO;
  }
  NSCharacterSet *control = [NSCharacterSet controlCharacterSet];
  return [path rangeOfCharacterFromSet:control].location == NSNotFound;
}

static BOOL SafeRevision(NSString *revision) {
  if (![revision isKindOfClass:NSString.class] || revision.length == 0 || revision.length > 64) return NO;
  NSCharacterSet *allowed = [NSCharacterSet characterSetWithCharactersInString:@"0123456789abcdefABCDEF"];
  return [revision rangeOfCharacterFromSet:allowed.invertedSet].location == NSNotFound;
}

static NeoShaderResult *Failure(NSString *code, NSString *detail) {
  return [NeoShaderResult failureWithCode:code detail:detail];
}

/// Writes JSON atomically (temporary file + rename).
static BOOL WriteJSON(id object, NSString *path) {
  NSData *data = [NSJSONSerialization dataWithJSONObject:object
                                                 options:NSJSONWritingPrettyPrinted | NSJSONWritingSortedKeys
                                                   error:nil];
  return data != nil && [data writeToFile:path options:NSDataWritingAtomic error:nil];
}

static NSDictionary *ReadJSONObject(NSString *path) {
  NSData *data = [NSData dataWithContentsOfFile:path];
  if (data == nil) return @{};
  id json = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
  return [json isKindOfClass:NSDictionary.class] ? json : @{};
}

#pragma mark - Records

@interface NeoShaderInstallation ()
@property(nonatomic, copy, readwrite) NSString *identifier;
@property(nonatomic, copy, readwrite) NSString *revision;
@property(nonatomic, copy, readwrite) NSArray<NSString *> *files;
@property(nonatomic, readwrite) unsigned long long bytes;
@property(nonatomic, strong, readwrite) NSDate *installedAt;
@end

@implementation NeoShaderInstallation

+ (nullable instancetype)installationFromJSON:(id)json {
  if (![json isKindOfClass:NSDictionary.class]) return nil;
  NeoShaderInstallation *installation = [NeoShaderInstallation new];
  installation.identifier = [json[@"id"] isKindOfClass:NSString.class] ? json[@"id"] : @"";
  installation.revision = [json[@"revision"] isKindOfClass:NSString.class] ? json[@"revision"] : @"";
  NSMutableArray<NSString *> *files = [NSMutableArray array];
  for (id file in [json[@"files"] isKindOfClass:NSArray.class] ? json[@"files"] : @[]) {
    if (!SafeRelativePath(file)) return nil;
    [files addObject:file];
  }
  if (!SafeRelativePath(installation.identifier) || !SafeRevision(installation.revision) || files.count == 0) return nil;
  installation.files = files;
  installation.bytes = [json[@"bytes"] isKindOfClass:NSNumber.class] ? [json[@"bytes"] unsignedLongLongValue] : 0;
  installation.installedAt = DateFromISO(json[@"installedAt"]);
  return installation;
}

- (NSDictionary *)JSONObject {
  return @{
    @"id" : self.identifier,
    @"revision" : self.revision,
    @"files" : self.files,
    @"bytes" : @(self.bytes),
    @"installedAt" : ISODate(self.installedAt)
  };
}

@end

@interface NeoShaderProfile ()
@property(nonatomic, copy, readwrite) NSString *identifier;
@property(nonatomic, copy, readwrite) NSString *name;
@property(nonatomic, copy, readwrite) NSString *shader;
@property(nonatomic, copy, readwrite) NSDictionary<NSString *, NSNumber *> *parameters;
@property(nonatomic, strong, readwrite) NSDate *createdAt;
@end

@implementation NeoShaderProfile

+ (nullable instancetype)profileFromJSON:(id)json {
  if (![json isKindOfClass:NSDictionary.class]) return nil;
  NeoShaderProfile *profile = [NeoShaderProfile new];
  profile.identifier = [json[@"id"] isKindOfClass:NSString.class] ? json[@"id"] : @"";
  profile.name = [json[@"name"] isKindOfClass:NSString.class] ? json[@"name"] : @"";
  profile.shader = [json[@"shader"] isKindOfClass:NSString.class] ? json[@"shader"] : @"";
  if (profile.identifier.length == 0 || profile.name.length == 0 || profile.shader.length == 0) return nil;
  NSMutableDictionary<NSString *, NSNumber *> *parameters = [NSMutableDictionary dictionary];
  NSDictionary *stored = [json[@"parameters"] isKindOfClass:NSDictionary.class] ? json[@"parameters"] : @{};
  for (id key in stored) {
    id value = stored[key];
    if ([key isKindOfClass:NSString.class] && [value isKindOfClass:NSNumber.class] && isfinite([value doubleValue])) {
      parameters[key] = value;
    }
  }
  profile.parameters = parameters;
  profile.createdAt = DateFromISO(json[@"created"]);
  return profile;
}

- (NSDictionary *)JSONObject {
  return @{
    @"id" : self.identifier,
    @"name" : self.name,
    @"shader" : self.shader,
    @"parameters" : self.parameters,
    @"created" : ISODate(self.createdAt)
  };
}

@end

#pragma mark - Storage

/// One running installation.
@interface NeoShaderInstallJob : NSObject
@property(nonatomic, copy) NSString *identifier;
@property(nonatomic, assign) BOOL cancelled;
@end

@implementation NeoShaderInstallJob
@end

@implementation NeoShaderStorage {
  dispatch_queue_t _queue;  // registry, favourites, profiles, jobs
  NSMutableDictionary<NSString *, NeoShaderInstallJob *> *_jobs;
}

+ (instancetype)sharedStorageWithRoot:(NSString *)root engine:(NSString *)engine {
  static NSMutableDictionary<NSString *, NeoShaderStorage *> *storages;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    storages = [NSMutableDictionary dictionary];
  });
  NSString *key = [root.stringByStandardizingPath stringByAppendingFormat:@"|%@", engine];
  @synchronized(storages) {
    NeoShaderStorage *storage = storages[key];
    if (storage == nil) {
      storage = [[NeoShaderStorage alloc] initWithRoot:root.stringByStandardizingPath engine:engine];
      storages[key] = storage;
    }
    return storage;
  }
}

- (instancetype)initWithRoot:(NSString *)root engine:(NSString *)engine {
  self = [super init];
  if (self) {
    _root = [root copy];
    _engine = [engine copy];
    _queue = dispatch_queue_create("neostation.shader-storage", DISPATCH_QUEUE_SERIAL);
    _jobs = [NSMutableDictionary dictionary];
    _maximumEntryBytes = 64ULL << 20;
    NSFileManager *files = NSFileManager.defaultManager;
    [files createDirectoryAtPath:root withIntermediateDirectories:YES attributes:nil error:nil];
    // Downloads interrupted by a previous run were never registered.
    [files removeItemAtPath:[self stagingRoot] error:nil];
    // Shader files are re-downloadable: not part of iCloud / iTunes backups.
    NSURL *url = [NSURL fileURLWithPath:root isDirectory:YES];
    [url setResourceValue:@YES forKey:NSURLIsExcludedFromBackupKey error:nil];
  }
  return self;
}

- (NSString *)stagingRoot {
  return [_root stringByAppendingPathComponent:@"staging"];
}

- (NSString *)previewsRoot {
  return [_root stringByAppendingPathComponent:@"previews"];
}

- (NSString *)filesRoot {
  return [_root stringByAppendingPathComponent:@"files"];
}

- (NSString *)filesDirectoryForRevision:(NSString *)revision {
  return [[self filesRoot] stringByAppendingPathComponent:SafeRevision(revision) ? revision : @"invalid"];
}

- (NSString *)registryPath {
  return [_root stringByAppendingPathComponent:@"installed.json"];
}

#pragma mark Registry (on _queue)

- (NSArray<NeoShaderInstallation *> *)readInstallations {
  NSMutableArray<NeoShaderInstallation *> *installations = [NSMutableArray array];
  NSDictionary *json = ReadJSONObject([self registryPath]);
  for (id item in [json[@"installations"] isKindOfClass:NSArray.class] ? json[@"installations"] : @[]) {
    NeoShaderInstallation *installation = [NeoShaderInstallation installationFromJSON:item];
    if (installation != nil) [installations addObject:installation];
  }
  return installations;
}

- (BOOL)writeInstallations:(NSArray<NeoShaderInstallation *> *)installations {
  NSMutableArray *items = [NSMutableArray arrayWithCapacity:installations.count];
  for (NeoShaderInstallation *installation in installations) [items addObject:[installation JSONObject]];
  return WriteJSON(@{@"schema" : @1, @"engine" : _engine, @"installations" : items}, [self registryPath]);
}

- (NSArray<NeoShaderInstallation *> *)installations {
  __block NSArray<NeoShaderInstallation *> *installations;
  dispatch_sync(_queue, ^{
    installations = [self readInstallations];
  });
  return installations;
}

- (nullable NeoShaderInstallation *)installationWithIdentifier:(NSString *)identifier {
  for (NeoShaderInstallation *installation in [self installations]) {
    if ([installation.identifier isEqualToString:identifier]) return installation;
  }
  return nil;
}

- (BOOL)installationIsComplete:(NeoShaderInstallation *)installation {
  NSString *directory = [self filesDirectoryForRevision:installation.revision];
  for (NSString *file in installation.files) {
    if (RegularFileSize([directory stringByAppendingPathComponent:file]) < 0) return NO;
  }
  return YES;
}

#pragma mark Installation

- (BOOL)isInstallingIdentifier:(NSString *)identifier {
  __block BOOL installing = NO;
  dispatch_sync(_queue, ^{
    installing = self->_jobs[identifier] != nil;
  });
  return installing;
}

- (void)cancelInstallationOfIdentifier:(NSString *)identifier {
  dispatch_sync(_queue, ^{
    self->_jobs[identifier].cancelled = YES;
  });
}

- (NeoShaderDataLoader)effectiveLoader {
  NeoShaderDataLoader loader = self.dataLoader;
  if (loader != nil) return loader;
  static NSURLSession *session;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    NSURLSessionConfiguration *configuration = [NSURLSessionConfiguration ephemeralSessionConfiguration];
    configuration.timeoutIntervalForRequest = 30;
    configuration.timeoutIntervalForResource = 300;
    configuration.HTTPShouldSetCookies = NO;
    configuration.URLCache = nil;
    session = [NSURLSession sessionWithConfiguration:configuration];
  });
  return ^(NSURL *url, void (^completion)(NSData *, NSInteger, NSError *)) {
    [[session dataTaskWithURL:url
            completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
              NSInteger status = [response isKindOfClass:NSHTTPURLResponse.class]
                                     ? ((NSHTTPURLResponse *)response).statusCode
                                     : 0;
              completion(data, status, error);
            }] resume];
  };
}

- (void)installEntry:(NeoShaderCatalogEntry *)entry
             catalog:(NeoShaderCatalog *)catalog
            progress:(void (^)(unsigned long long, unsigned long long))progress
          completion:(void (^)(NeoShaderResult *))completion {
  void (^finish)(NeoShaderResult *) = ^(NeoShaderResult *result) {
    dispatch_async(dispatch_get_main_queue(), ^{
      completion(result);
    });
  };
  NSString *identifier = [entry.identifier copy];
  NSString *revision = [catalog.sourceRevision copy];
  if (!SafeRelativePath(identifier) || !SafeRevision(revision) || entry.files.count == 0) {
    finish(Failure(NeoShaderErrorEntryInvalid, identifier));
    return;
  }
  if (catalog.rawBaseURL.length == 0) {
    finish(Failure(NeoShaderErrorNoDownloadURL, identifier));
    return;
  }
  unsigned long long total = 0;
  for (NeoShaderCatalogFile *file in entry.files) {
    if (!SafeRelativePath(file.path)) {
      finish(Failure(NeoShaderErrorEntryInvalid, file.path));
      return;
    }
    total += file.size;
  }
  if (total > self.maximumEntryBytes) {
    finish(Failure(NeoShaderErrorEntryTooLarge, [NSString stringWithFormat:@"%llu bytes", total]));
    return;
  }
  __block NeoShaderInstallJob *job = nil;
  dispatch_sync(_queue, ^{
    if (self->_jobs[identifier] != nil) return;
    job = [NeoShaderInstallJob new];
    job.identifier = identifier;
    self->_jobs[identifier] = job;
  });
  if (job == nil) {
    finish(Failure(NeoShaderErrorBusy, identifier));
    return;
  }
  NSArray<NeoShaderCatalogFile *> *files = [entry.files copy];
  NeoShaderDataLoader loader = [self effectiveLoader];
  dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
    NeoShaderResult *result = [self runInstallation:job
                                              files:files
                                           revision:revision
                                            catalog:catalog
                                              total:total
                                             loader:loader
                                           progress:progress];
    dispatch_sync(self->_queue, ^{
      [self->_jobs removeObjectForKey:identifier];
    });
    finish(result);
  });
}

/// Background queue. Missing files are downloaded into a staging folder and
/// verified; only when every file is verified are they moved into place and
/// the installation registered.
- (NeoShaderResult *)runInstallation:(NeoShaderInstallJob *)job
                               files:(NSArray<NeoShaderCatalogFile *> *)files
                            revision:(NSString *)revision
                             catalog:(NeoShaderCatalog *)catalog
                               total:(unsigned long long)total
                              loader:(NeoShaderDataLoader)loader
                            progress:(void (^)(unsigned long long, unsigned long long))progress {
  NSFileManager *manager = NSFileManager.defaultManager;
  NSString *target = [self filesDirectoryForRevision:revision];
  NSMutableArray<NeoShaderCatalogFile *> *missing = [NSMutableArray array];
  unsigned long long toReceive = 0;
  for (NeoShaderCatalogFile *file in files) {
    NSString *path = [target stringByAppendingPathComponent:file.path];
    if (RegularFileSize(path) == (long long)file.size && [FileSHA256(path) isEqualToString:file.sha256]) continue;
    [missing addObject:file];
    toReceive += file.size;
  }
  if (toReceive > 0) {
    NSDictionary *values = [[NSURL fileURLWithPath:_root] resourceValuesForKeys:@[
      NSURLVolumeAvailableCapacityForImportantUsageKey
    ] error:nil];
    NSNumber *available = values[NSURLVolumeAvailableCapacityForImportantUsageKey];
    // Twice the download: staging, then the final files.
    if (available != nil && available.unsignedLongLongValue > 0 &&
        available.unsignedLongLongValue < toReceive * 2 + (16ULL << 20)) {
      return Failure(NeoShaderErrorStorageSpace, [NSString stringWithFormat:@"%llu bytes needed", toReceive * 2]);
    }
  }
  NSString *staging = [[self stagingRoot] stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
  if (missing.count > 0 && ![manager createDirectoryAtPath:staging withIntermediateDirectories:YES attributes:nil error:nil]) {
    return Failure(NeoShaderErrorStorageWrite, staging);
  }

  __block NeoShaderResult *failure = nil;
  __block unsigned long long received = 0;
  NSObject *lock = [NSObject new];
  dispatch_semaphore_t slots = dispatch_semaphore_create(kParallelDownloads);
  dispatch_group_t group = dispatch_group_create();
  if (progress != nil) {
    dispatch_async(dispatch_get_main_queue(), ^{
      progress(0, toReceive);
    });
  }
  for (NeoShaderCatalogFile *file in missing) {
    dispatch_semaphore_wait(slots, DISPATCH_TIME_FOREVER);
    BOOL stop = NO;
    @synchronized(lock) {
      stop = failure != nil || job.cancelled;
    }
    if (stop) {
      dispatch_semaphore_signal(slots);
      break;
    }
    NSURL *url = [catalog downloadURLForFile:file];
    if (url == nil) {
      @synchronized(lock) {
        failure = Failure(NeoShaderErrorNoDownloadURL, file.path);
      }
      dispatch_semaphore_signal(slots);
      break;
    }
    dispatch_group_enter(group);
    loader(url, ^(NSData *data, NSInteger status, NSError *error) {
      NeoShaderResult *problem = nil;
      if (error != nil || data == nil) {
        problem = Failure(NeoShaderErrorNetwork,
                          [NSString stringWithFormat:@"%@: %@", file.path, error.localizedDescription ?: @"no data"]);
      } else if (status != 0 && status != 200) {
        problem = Failure(NeoShaderErrorHTTPStatus, [NSString stringWithFormat:@"%@: HTTP %ld", file.path, (long)status]);
      } else if (data.length != file.size) {
        problem = Failure(NeoShaderErrorSizeMismatch,
                          [NSString stringWithFormat:@"%@: %lu bytes, expected %llu", file.path,
                                                     (unsigned long)data.length, file.size]);
      } else if (![DataSHA256(data) isEqualToString:file.sha256]) {
        problem = Failure(NeoShaderErrorHashMismatch, file.path);
      } else {
        NSString *path = [staging stringByAppendingPathComponent:file.path];
        [manager createDirectoryAtPath:path.stringByDeletingLastPathComponent
            withIntermediateDirectories:YES
                             attributes:nil
                                  error:nil];
        if (![data writeToFile:path options:NSDataWritingAtomic error:nil]) {
          problem = Failure(NeoShaderErrorStorageWrite, file.path);
        }
      }
      unsigned long long now = 0;
      @synchronized(lock) {
        if (problem != nil && failure == nil) failure = problem;
        received += problem == nil ? file.size : 0;
        now = received;
      }
      if (problem == nil && progress != nil) {
        dispatch_async(dispatch_get_main_queue(), ^{
          progress(now, toReceive);
        });
      }
      dispatch_semaphore_signal(slots);
      dispatch_group_leave(group);
    });
  }
  dispatch_group_wait(group, DISPATCH_TIME_FOREVER);
  @synchronized(lock) {
    if (failure == nil && job.cancelled) failure = Failure(NeoShaderErrorCancelled, job.identifier);
  }
  if (failure != nil) {
    [manager removeItemAtPath:staging error:nil];
    return failure;
  }

  // Every file is verified: move them into place, then register.
  for (NeoShaderCatalogFile *file in missing) {
    NSString *source = [staging stringByAppendingPathComponent:file.path];
    NSString *destination = [target stringByAppendingPathComponent:file.path];
    [manager createDirectoryAtPath:destination.stringByDeletingLastPathComponent
        withIntermediateDirectories:YES
                         attributes:nil
                              error:nil];
    [manager removeItemAtPath:destination error:nil];
    if (![manager moveItemAtPath:source toPath:destination error:nil]) {
      [manager removeItemAtPath:staging error:nil];
      return Failure(NeoShaderErrorStorageWrite, file.path);
    }
  }
  [manager removeItemAtPath:staging error:nil];
  __block BOOL written = NO;
  dispatch_sync(_queue, ^{
    NSMutableArray<NeoShaderInstallation *> *installations = [[self readInstallations] mutableCopy];
    NSIndexSet *existing = [installations indexesOfObjectsPassingTest:^BOOL(NeoShaderInstallation *item, NSUInteger index, BOOL *stop) {
      return [item.identifier isEqualToString:job.identifier];
    }];
    [installations removeObjectsAtIndexes:existing];
    NeoShaderInstallation *installation = [NeoShaderInstallation new];
    installation.identifier = job.identifier;
    installation.revision = revision;
    NSMutableArray<NSString *> *paths = [NSMutableArray arrayWithCapacity:files.count];
    for (NeoShaderCatalogFile *file in files) [paths addObject:file.path];
    installation.files = paths;
    installation.bytes = total;
    installation.installedAt = [NSDate date];
    [installations addObject:installation];
    written = [self writeInstallations:installations];
  });
  return written ? [NeoShaderResult success] : Failure(NeoShaderErrorStorageWrite, [self registryPath]);
}

- (BOOL)removeInstallationWithIdentifier:(NSString *)identifier error:(NSError **)error {
  __block BOOL removed = NO;
  dispatch_sync(_queue, ^{
    NSMutableArray<NeoShaderInstallation *> *installations = [[self readInstallations] mutableCopy];
    NeoShaderInstallation *victim = nil;
    for (NeoShaderInstallation *installation in installations) {
      if ([installation.identifier isEqualToString:identifier]) victim = installation;
    }
    if (victim == nil) return;
    [installations removeObject:victim];
    if (![self writeInstallations:installations]) return;
    // Files still used by another installation of the same revision stay.
    NSMutableSet<NSString *> *kept = [NSMutableSet set];
    for (NeoShaderInstallation *installation in installations) {
      if ([installation.revision isEqualToString:victim.revision]) [kept addObjectsFromArray:installation.files];
    }
    NSString *directory = [self filesDirectoryForRevision:victim.revision];
    NSFileManager *manager = NSFileManager.defaultManager;
    for (NSString *file in victim.files) {
      if ([kept containsObject:file]) continue;
      NSString *path = [directory stringByAppendingPathComponent:file];
      [manager removeItemAtPath:path error:nil];
      // Empty parent folders up to the revision folder.
      NSString *parent = path.stringByDeletingLastPathComponent;
      while (parent.length > directory.length && [parent hasPrefix:directory]) {
        NSArray *contents = [manager contentsOfDirectoryAtPath:parent error:nil];
        if (contents == nil || contents.count > 0) break;
        [manager removeItemAtPath:parent error:nil];
        parent = parent.stringByDeletingLastPathComponent;
      }
    }
    removed = YES;
  });
  if (!removed && error != NULL) {
    *error = [NSError errorWithDomain:kStorageErrorDomain code:1 userInfo:@{NSDebugDescriptionErrorKey : identifier}];
  }
  return removed;
}

#pragma mark Previews

- (void)previewDataForFile:(NeoShaderCatalogFile *)file
                   catalog:(NeoShaderCatalog *)catalog
                completion:(void (^)(NSData *))completion {
  void (^finish)(NSData *) = ^(NSData *data) {
    dispatch_async(dispatch_get_main_queue(), ^{
      completion(data);
    });
  };
  NSURL *url = file != nil ? [catalog previewURLForFile:file] : nil;
  if (url == nil || file.sha256.length != 64) {
    finish(nil);
    return;
  }
  NSString *cached = [[self previewsRoot] stringByAppendingPathComponent:[file.sha256 stringByAppendingString:@".png"]];
  NeoShaderDataLoader loader = [self effectiveLoader];
  dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
    NSData *data = [NSData dataWithContentsOfFile:cached];
    if (data != nil && data.length == file.size && [DataSHA256(data) isEqualToString:file.sha256]) {
      finish(data);
      return;
    }
    loader(url, ^(NSData *downloaded, NSInteger status, NSError *error) {
      if (error != nil || downloaded == nil || (status != 0 && status != 200) || downloaded.length != file.size ||
          ![DataSHA256(downloaded) isEqualToString:file.sha256]) {
        finish(nil);
        return;
      }
      [NSFileManager.defaultManager createDirectoryAtPath:[self previewsRoot]
                              withIntermediateDirectories:YES
                                               attributes:nil
                                                    error:nil];
      [downloaded writeToFile:cached options:NSDataWritingAtomic error:nil];
      finish(downloaded);
    });
  });
}

#pragma mark Favourites

- (NSString *)favoritesPath {
  return [_root stringByAppendingPathComponent:@"favorites.json"];
}

- (NSArray<NSString *> *)readFavorites {
  NSMutableArray<NSString *> *favorites = [NSMutableArray array];
  NSDictionary *json = ReadJSONObject([self favoritesPath]);
  for (id item in [json[@"favorites"] isKindOfClass:NSArray.class] ? json[@"favorites"] : @[]) {
    if ([item isKindOfClass:NSString.class] && [item length] > 0 && [item length] <= 600 &&
        ![favorites containsObject:item]) {
      [favorites addObject:item];
    }
  }
  return favorites;
}

- (NSArray<NSString *> *)favorites {
  __block NSArray<NSString *> *favorites;
  dispatch_sync(_queue, ^{
    favorites = [self readFavorites];
  });
  return favorites;
}

- (BOOL)isFavorite:(NSString *)identifier {
  return [[self favorites] containsObject:identifier];
}

- (void)setFavorite:(BOOL)favorite identifier:(NSString *)identifier {
  if (![identifier isKindOfClass:NSString.class] || identifier.length == 0) return;
  dispatch_sync(_queue, ^{
    NSMutableArray<NSString *> *favorites = [[self readFavorites] mutableCopy];
    [favorites removeObject:identifier];
    if (favorite) [favorites addObject:identifier];
    WriteJSON(@{@"schema" : @1, @"favorites" : favorites}, [self favoritesPath]);
  });
}

#pragma mark Profiles

- (NSString *)profilesPath {
  return [_root stringByAppendingPathComponent:@"profiles.json"];
}

- (NSArray<NeoShaderProfile *> *)readProfiles {
  NSMutableArray<NeoShaderProfile *> *profiles = [NSMutableArray array];
  NSDictionary *json = ReadJSONObject([self profilesPath]);
  for (id item in [json[@"profiles"] isKindOfClass:NSArray.class] ? json[@"profiles"] : @[]) {
    NeoShaderProfile *profile = [NeoShaderProfile profileFromJSON:item];
    if (profile != nil) [profiles addObject:profile];
  }
  return profiles;
}

- (BOOL)writeProfiles:(NSArray<NeoShaderProfile *> *)profiles {
  NSMutableArray *items = [NSMutableArray arrayWithCapacity:profiles.count];
  for (NeoShaderProfile *profile in profiles) [items addObject:[profile JSONObject]];
  return WriteJSON(@{@"schema" : @1, @"engine" : _engine, @"profiles" : items}, [self profilesPath]);
}

- (NSArray<NeoShaderProfile *> *)profiles {
  __block NSArray<NeoShaderProfile *> *profiles;
  dispatch_sync(_queue, ^{
    profiles = [self readProfiles];
  });
  return profiles;
}

- (nullable NeoShaderProfile *)saveProfileWithName:(NSString *)name
                                            shader:(NSString *)shader
                                        parameters:(NSDictionary<NSString *, NSNumber *> *)parameters
                                             error:(NSError **)error {
  NSString *trimmed = [name isKindOfClass:NSString.class]
                          ? [name stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet]
                          : @"";
  NSString *code = nil;
  if (trimmed.length == 0 || trimmed.length > kMaximumProfileName ||
      [trimmed rangeOfCharacterFromSet:NSCharacterSet.controlCharacterSet].location != NSNotFound ||
      ![shader isKindOfClass:NSString.class] || shader.length == 0) {
    code = NeoShaderErrorProfileName;
  }
  __block NeoShaderProfile *saved = nil;
  if (code == nil) {
    dispatch_sync(_queue, ^{
      NSMutableArray<NeoShaderProfile *> *profiles = [[self readProfiles] mutableCopy];
      NSIndexSet *sameName = [profiles indexesOfObjectsPassingTest:^BOOL(NeoShaderProfile *item, NSUInteger index, BOOL *stop) {
        return [item.name compare:trimmed options:NSCaseInsensitiveSearch] == NSOrderedSame;
      }];
      [profiles removeObjectsAtIndexes:sameName];
      if (profiles.count >= kMaximumProfiles) return;
      NeoShaderProfile *profile = [NeoShaderProfile new];
      profile.identifier = NSUUID.UUID.UUIDString;
      profile.name = trimmed;
      profile.shader = shader;
      NSMutableDictionary<NSString *, NSNumber *> *values = [NSMutableDictionary dictionary];
      for (id key in parameters) {
        id value = parameters[key];
        if ([key isKindOfClass:NSString.class] && [value isKindOfClass:NSNumber.class] && isfinite([value doubleValue])) {
          values[key] = value;
        }
      }
      profile.parameters = values;
      profile.createdAt = [NSDate date];
      [profiles addObject:profile];
      if ([self writeProfiles:profiles]) saved = profile;
    });
    if (saved == nil) code = NeoShaderErrorProfileLimit;
  }
  if (saved == nil && error != NULL) {
    *error = [NSError errorWithDomain:kStorageErrorDomain code:2 userInfo:@{NSDebugDescriptionErrorKey : code ?: @""}];
  }
  return saved;
}

- (BOOL)removeProfileWithIdentifier:(NSString *)identifier {
  __block BOOL removed = NO;
  dispatch_sync(_queue, ^{
    NSMutableArray<NeoShaderProfile *> *profiles = [[self readProfiles] mutableCopy];
    NSIndexSet *matches = [profiles indexesOfObjectsPassingTest:^BOOL(NeoShaderProfile *item, NSUInteger index, BOOL *stop) {
      return [item.identifier isEqualToString:identifier];
    }];
    if (matches.count == 0) return;
    [profiles removeObjectsAtIndexes:matches];
    removed = [self writeProfiles:profiles];
  });
  return removed;
}

#pragma mark Storage report

/// Every regular file below `directory` (relative path -> size).
static NSDictionary<NSString *, NSNumber *> *FilesBelow(NSString *directory) {
  NSMutableDictionary<NSString *, NSNumber *> *files = [NSMutableDictionary dictionary];
  NSDirectoryEnumerator<NSString *> *enumerator = [NSFileManager.defaultManager enumeratorAtPath:directory];
  for (NSString *relative in enumerator) {
    NSDictionary *attributes = enumerator.fileAttributes;
    if ([attributes.fileType isEqualToString:NSFileTypeRegular]) files[relative] = @(attributes.fileSize);
  }
  return files;
}

/// Files below files/ that no installation lists ("<revision>/<path>").
- (NSDictionary<NSString *, NSNumber *> *)orphanFilesWithInstallations:(NSArray<NeoShaderInstallation *> *)installations {
  NSMutableSet<NSString *> *used = [NSMutableSet set];
  for (NeoShaderInstallation *installation in installations) {
    for (NSString *file in installation.files) {
      [used addObject:[installation.revision stringByAppendingPathComponent:file]];
    }
  }
  NSMutableDictionary<NSString *, NSNumber *> *orphans = [NSMutableDictionary dictionary];
  NSDictionary<NSString *, NSNumber *> *files = FilesBelow([self filesRoot]);
  for (NSString *relative in files) {
    if (![used containsObject:relative]) orphans[relative] = files[relative];
  }
  return orphans;
}

static unsigned long long SumOf(NSDictionary<NSString *, NSNumber *> *sizes) {
  unsigned long long total = 0;
  for (NSNumber *size in sizes.allValues) total += size.unsignedLongLongValue;
  return total;
}

- (NSDictionary<NSString *, id> *)storageReport {
  __block NSDictionary<NSString *, id> *report = nil;
  dispatch_sync(_queue, ^{
    NSArray<NeoShaderInstallation *> *installations = [self readInstallations];
    NSDictionary<NSString *, NSNumber *> *files = FilesBelow([self filesRoot]);
    NSDictionary<NSString *, NSNumber *> *orphans = [self orphanFilesWithInstallations:installations];
    NSDictionary<NSString *, NSNumber *> *staging = self->_jobs.count == 0 ? FilesBelow([self stagingRoot]) : @{};
    const unsigned long long orphanBytes = SumOf(orphans);
    report = @{
      @"engine" : self->_engine,
      @"installed" : @(installations.count),
      @"installedBytes" : @(SumOf(files) - orphanBytes),
      @"orphanFiles" : @(orphans.count),
      @"orphanBytes" : @(orphanBytes),
      @"staleDownloads" : @(staging.count),
      @"staleBytes" : @(SumOf(staging)),
      @"previewBytes" : @(SumOf(FilesBelow([self previewsRoot]))),
    };
  });
  return report;
}

- (unsigned long long)cleanCaches {
  __block unsigned long long freed = 0;
  dispatch_sync(_queue, ^{
    NSFileManager *manager = NSFileManager.defaultManager;
    NSDictionary<NSString *, NSNumber *> *orphans = [self orphanFilesWithInstallations:[self readInstallations]];
    for (NSString *relative in orphans) {
      if ([manager removeItemAtPath:[[self filesRoot] stringByAppendingPathComponent:relative] error:nil]) {
        freed += orphans[relative].unsignedLongLongValue;
      }
    }
    if (self->_jobs.count == 0) {
      freed += SumOf(FilesBelow([self stagingRoot]));
      [manager removeItemAtPath:[self stagingRoot] error:nil];
    }
    freed += SumOf(FilesBelow([self previewsRoot]));
    [manager removeItemAtPath:[self previewsRoot] error:nil];
  });
  return freed;
}

@end

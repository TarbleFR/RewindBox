// SPDX-License-Identifier: GPL-3.0-or-later
#import "Public/NeoTexturePackStore.h"
#import "Public/NeoTextureCatalog.h"
#import "NeoTextureSupport.h"
#import "NeoTextureHostResolver.h"
#import "NeoTextureMega.h"
#import <CommonCrypto/CommonDigest.h>
#include "NeoTextureInstall.h"
#include <atomic>
#include <cerrno>
#include <cstdlib>
#include <fcntl.h>
#include <memory>
#include <sys/stat.h>
#include <unistd.h>

NSString *const NeoTexturePackStoreErrorDomain = @"NeoTexturePackStore";

static const unsigned long long Headroom = 1ULL << 30;  // left free after an install
static NSString *const ManifestName = NeoTexManifestName;

static NSError *PackError(NeoTexturePackError code, NSString *key, NSDictionary *details) {
  NSMutableDictionary *info = [NSMutableDictionary dictionaryWithDictionary:details ?: @{}];
  info[@"key"] = key;
  info[NSLocalizedDescriptionKey] = key;
  return [NSError errorWithDomain:NeoTexturePackStoreErrorDomain code:code userInfo:info];
}

static NeoTextureInstall::Engine EngineKind(id<NeoTextureEngine> engine) {
  NSString *name = engine.engineID;
  if ([name isEqualToString:@"dolphin"]) return NeoTextureInstall::Engine::dolphin;
  if ([name isEqualToString:@"armsx2"]) return NeoTextureInstall::Engine::armsx2;
  if ([name isEqualToString:@"ppsspp"]) return NeoTextureInstall::Engine::ppsspp;
  if ([name isEqualToString:@"mupen64plus"]) return NeoTextureInstall::Engine::mupen64plus;
  if ([name isEqualToString:@"beetle"]) return NeoTextureInstall::Engine::beetle;
  if ([name isEqualToString:@"mesen"]) return NeoTextureInstall::Engine::mesen;
  return NeoTextureInstall::Engine::azahar;
}

static std::string Std(NSString *s) { return s.length ? std::string(s.fileSystemRepresentation) : std::string(); }

// A catalogue folder {from, to, exclude} as an installer rule installed as `to`.
static NeoTextureInstall::Rule RuleFor(NSDictionary *folder, const std::string &to) {
  NeoTextureInstall::Rule rule{NeoTexString(folder[@"from"]).UTF8String ?: "", to, {}};
  for (id prefix in [folder[@"exclude"] isKindOfClass:NSArray.class] ? folder[@"exclude"] : @[])
    if ([prefix isKindOfClass:NSString.class] && [prefix length]) rule.exclude.push_back([prefix UTF8String]);
  return rule;
}

static NSString *IdentityFolderID(id<NeoTextureEngine> engine, NSDictionary *identity) {
  NSString *folder = [engine folderForIdentity:identity];
  // ARMSX2 folders are <SERIAL>/replacements; imports detect against the serial.
  return [folder hasSuffix:@"/replacements"] ? folder.stringByDeletingLastPathComponent : folder;
}

static NSError *ArchiveError(NeoTextureArchive::Status status, const std::string &problem) {
  if (problem == "rar") return PackError(NeoTexturePackErrorArchive, @"rarUnsupported", nil);
  if (problem == "tooLarge") return PackError(NeoTexturePackErrorArchive, @"archiveTooLarge", nil);
  if (problem == "duplicate") return PackError(NeoTexturePackErrorArchive, @"archiveDuplicate", nil);
  if (problem == "link") return PackError(NeoTexturePackErrorArchive, @"archiveLink", nil);
  switch (status) {
    case NeoTextureArchive::Status::cancelled: return PackError(NeoTexturePackErrorCancelled, @"cancelled", nil);
    case NeoTextureArchive::Status::io: return PackError(NeoTexturePackErrorWrite, @"writeFailed", nil);
    case NeoTextureArchive::Status::limits: return PackError(NeoTexturePackErrorArchive, @"archiveTooLarge", nil);
    case NeoTextureArchive::Status::unsupported: return PackError(NeoTexturePackErrorArchive, @"archiveUnsupported", nil);
    case NeoTextureArchive::Status::crc: return PackError(NeoTexturePackErrorArchive, @"archiveDamaged", nil);
    default: return PackError(NeoTexturePackErrorArchive, @"archiveDamaged", nil);
  }
}

// The error of a game without a folder for this engine.
static NSString *NoFolderKey(id<NeoTextureEngine> engine, NSDictionary *identity) {
  NSString *key = identity && [engine respondsToSelector:@selector(folderProblemForIdentity:)] ? [engine folderProblemForIdentity:identity] : nil;
  return key.length ? key : @"noGameID";
}

static BOOL Delegates(id<NeoTextureEngine> engine) {
  return [engine respondsToSelector:@selector(installsPacks)] && [engine installsPacks];
}

// Error keys of an engine's own installer (ARMSX2TexturePackStore) as page labels.
static NSString *DelegateErrorKey(NSString *key) {
  static NSDictionary *map;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    map = @{@"space": @"space", @"cancelled": @"cancelled", @"noTextures": @"noTextures", @"noNamedTextures": @"noTextures",
            @"unsafe": @"archiveDamaged", @"invalid": @"archiveDamaged", @"duplicate": @"archiveDuplicate",
            @"multipleSerials": @"multipleSerials", @"fileTooLarge": @"archiveTooLarge", @"entries": @"archiveTooLarge",
            @"method": @"archiveUnsupported", @"format": @"archiveUnsupported", @"zstdNeedsGame": @"zstdNeedsGame",
            @"gameUnknown": @"noGameID", @"noGameID": @"noGameID", @"write": @"writeFailed", @"unreadable": @"unreadable",
            @"changed": @"changed", @"engineUnavailable": @"engineUnavailable", @"removeFailed": @"removeFailed",
            @"sessionActive": @"busy"};
  });
  return map[key] ?: @"failed";
}

static NSError *DelegateError(NSDictionary *outcome) {
  if ([outcome[@"needsConfirmation"] boolValue]) {
    NSString *source = NeoTexString(outcome[@"packSerial"]);
    return PackError(NeoTexturePackErrorRegion, @"otherRegion", @{@"sourceIDs": source.length ? @[source] : @[], @"engine": outcome});
  }
  NSString *key = DelegateErrorKey(NeoTexString(outcome[@"error"]));
  NeoTexturePackError code = [key isEqualToString:@"space"] ? NeoTexturePackErrorSpace
      : [key isEqualToString:@"cancelled"] ? NeoTexturePackErrorCancelled
      : [key isEqualToString:@"busy"] ? NeoTexturePackErrorBusy
      : [@[@"noTextures", @"multipleSerials", @"noGameID", @"zstdNeedsGame"] containsObject:key] ? NeoTexturePackErrorLayout
      : [key hasPrefix:@"archive"] || [key isEqualToString:@"unreadable"] ? NeoTexturePackErrorArchive : NeoTexturePackErrorWrite;
  NSMutableDictionary *details = [NSMutableDictionary dictionary];
  if (outcome[@"needed"]) details[@"required"] = outcome[@"needed"];
  if (outcome[@"available"]) details[@"free"] = outcome[@"available"];
  if (NeoTexString(outcome[@"detail"]).length) details[@"detail"] = outcome[@"detail"];
  return PackError(code, key, details);
}

@interface NeoTexturePackStore () <NSURLSessionDownloadDelegate, NSURLSessionDataDelegate> {
  dispatch_queue_t _queue;  // state
  dispatch_queue_t _work;   // hashing, extraction, file moves
  NSURLSession *_session;
  NSMutableDictionary<NSString *, NSMutableDictionary *> *_jobs;
  NSURLSessionTask *_task;
  NSString *_taskPack;
  NSUInteger _taskPart;
  void (^_taskFinished)(NSError *);
  unsigned long long _taskBase;
  id _partResolution;
  BOOL _taskStream;
  NSString *_streamPath;
  int _streamFD;
  unsigned long long _streamStart, _streamWritten, _streamExpected;
  NSError *_streamError;
  NSDictionary *_streamCrypto, *_streamPart;
  std::shared_ptr<std::atomic<bool>> _taskCancel;
  std::shared_ptr<std::atomic<bool>> _cancel;
  NSString *_busyPack;
  BOOL _discardOnFinish;
  NSTimeInterval _lastNotice;
}
@end

@implementation NeoTexturePackStore

+ (instancetype)sharedStore {
  static NeoTexturePackStore *store;
  static dispatch_once_t once;
  dispatch_once(&once, ^{ store = [self new]; });
  return store;
}

- (instancetype)init {
  if (!(self = [super init])) return nil;
  _queue = dispatch_queue_create("org.neostation.textures.store", DISPATCH_QUEUE_SERIAL);
  _work = dispatch_queue_create("org.neostation.textures.work",
                                dispatch_queue_attr_make_with_qos_class(DISPATCH_QUEUE_SERIAL, QOS_CLASS_UTILITY, 0));
  NSString *caches = NSSearchPathForDirectoriesInDomains(NSCachesDirectory, NSUserDomainMask, YES).firstObject ?: NSTemporaryDirectory();
  _downloadDirectory = [caches stringByAppendingPathComponent:@"NeoStation/Textures/Downloads"];
  _freeSpace = ^unsigned long long(NSString *path) { return NeoTexFreeBytes(path); };
  _jobs = [NSMutableDictionary dictionary];
  _streamFD = -1;
  return self;
}

- (NSURLSession *)session {
  if (!_session) {
    NSURLSessionConfiguration *configuration = NSURLSessionConfiguration.defaultSessionConfiguration;
    configuration.timeoutIntervalForRequest = 60;
    configuration.timeoutIntervalForResource = 6 * 60 * 60;
    configuration.URLCache = nil;
    configuration.HTTPCookieStorage = nil;
    configuration.HTTPShouldSetCookies = NO;
    configuration.URLCredentialStorage = nil;
    NSOperationQueue *delegates = [NSOperationQueue new];
    delegates.maxConcurrentOperationCount = 1;
    _session = [NSURLSession sessionWithConfiguration:configuration delegate:self delegateQueue:delegates];
  }
  return _session;
}

#pragma mark - Job state

- (NSDictionary *)jobForPack:(NSString *)packID {
  __block NSDictionary *job;
  dispatch_sync(_queue, ^{ job = [self->_jobs[packID] copy]; });
  if (job) return job;
  // A download interrupted in an earlier launch can be resumed.
  for (NSString *folder in [self downloadFoldersOf:packID]) {
    for (NSString *name in [NSFileManager.defaultManager contentsOfDirectoryAtPath:folder error:nil] ?: @[]) {
      if ([name hasPrefix:@"archive."] && ![name hasSuffix:@".joining"]) return @{@"state": @"downloaded", @"folder": folder};
      if ([name hasSuffix:@".resume"] || [name hasSuffix:@".partial"] || [name hasPrefix:@"part-"])
        return @{@"state": @"paused", @"resumable": @YES, @"folder": folder};
    }
  }
  return @{@"state": @"idle"};
}

- (BOOL)isBusy {
  __block BOOL busy;
  dispatch_sync(_queue, ^{ busy = self->_busyPack != nil; });
  return busy;
}

- (void)update:(NSString *)packID values:(NSDictionary *)values notify:(BOOL)force {
  NSMutableDictionary *job = _jobs[packID] ?: [NSMutableDictionary dictionary];
  [job addEntriesFromDictionary:values];
  _jobs[packID] = job;
  const NSTimeInterval now = NSDate.timeIntervalSinceReferenceDate;
  if (!force && now - _lastNotice < 0.25) return;
  _lastNotice = now;
  dispatch_async(dispatch_get_main_queue(), ^{
    [[NSNotificationCenter defaultCenter] postNotificationName:NeoTextureCatalogDidChangeNotification object:self userInfo:@{@"pack": packID}];
  });
}

- (void)finish:(NSString *)packID state:(NSString *)state error:(NSError *)error result:(NSDictionary *)result
    completion:(void (^)(NSDictionary *, NSError *))completion {
  dispatch_async(_queue, ^{
    BOOL discarded = [self->_busyPack isEqualToString:packID] && self->_discardOnFinish;
    if ([self->_busyPack isEqualToString:packID]) { self->_busyPack = nil; self->_discardOnFinish = NO; }
    NSMutableDictionary *values = [@{@"state": discarded ? @"idle" : state} mutableCopy];
    values[@"error"] = error.userInfo[@"key"] ?: [NSNull null];
    [self update:packID values:values notify:YES];
    if (discarded || [state isEqualToString:@"done"]) [self->_jobs removeObjectForKey:packID];
    dispatch_async(dispatch_get_main_queue(), ^{ completion(result, error); });
  });
}

+ (unsigned long long)requiredBytesForPack:(NSDictionary *)pack downloaded:(BOOL)downloaded {
  unsigned long long download = [pack[@"download"][@"size"] unsignedLongLongValue];
  if (!download) for (NSDictionary *part in pack[@"download"][@"parts"]) download += [part[@"size"] unsignedLongLongValue];
  return (downloaded ? 0 : download) + [pack[@"install"][@"bytes"] unsignedLongLongValue] + Headroom;
}

+ (NSString *)sha256OfFile:(NSString *)path size:(unsigned long long *)size {
  NeoTextureArchive::File file;
  if (!file.open(Std(path))) return nil;
  CC_SHA256_CTX context;
  CC_SHA256_Init(&context);
  std::unique_ptr<unsigned char[]> buffer(new unsigned char[1 << 20]);
  for (uint64_t at = 0; at < file.length();) {
    const size_t n = size_t(std::min<uint64_t>(1 << 20, file.length() - at));
    if (!file.read(at, buffer.get(), n)) return nil;
    CC_SHA256_Update(&context, buffer.get(), (CC_LONG)n);
    at += n;
  }
  unsigned char digest[CC_SHA256_DIGEST_LENGTH];
  CC_SHA256_Final(digest, &context);
  NSMutableString *hex = [NSMutableString stringWithCapacity:64];
  for (int i = 0; i < CC_SHA256_DIGEST_LENGTH; i++) [hex appendFormat:@"%02x", digest[i]];
  if (size) *size = file.length();
  return hex;
}

static BOOL LooksLikeHTML(NSString *path) {
  NSFileHandle *handle = [NSFileHandle fileHandleForReadingAtPath:path];
  NSData *head = [handle readDataOfLength:512];
  [handle closeFile];
  NSString *text = [[NSString alloc] initWithData:head encoding:NSISOLatin1StringEncoding].lowercaseString ?: @"";
  text = [text stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
  return [text hasPrefix:@"<!doctype html"] || [text hasPrefix:@"<html"] || [text rangeOfString:@"<head"].location != NSNotFound;
}

#pragma mark - Download

// One folder per published file: a catalogue update with a new archive never
// reuses bytes downloaded for the previous version.
- (NSString *)folderForPack:(NSDictionary *)pack {
  NSString *digest = NeoTexString(pack[@"download"][@"sha256"]);
  if (!digest.length) digest = NeoTexString([pack[@"download"][@"parts"] firstObject][@"sha256"]);
  return [self.downloadDirectory stringByAppendingPathComponent:
      [NSString stringWithFormat:@"%@@%@", pack[@"id"], digest.length >= 12 ? [digest substringToIndex:12] : @"unverified"]];
}

- (NSArray<NSString *> *)downloadFoldersOf:(NSString *)packID {
  NSMutableArray *folders = [NSMutableArray array];
  for (NSString *name in [NSFileManager.defaultManager contentsOfDirectoryAtPath:self.downloadDirectory error:nil] ?: @[])
    if ([name hasPrefix:[packID stringByAppendingString:@"@"]]) [folders addObject:[self.downloadDirectory stringByAppendingPathComponent:name]];
  return folders;
}

- (void)installPack:(NSDictionary *)pack engine:(id<NeoTextureEngine>)engine identity:(NSDictionary *)identity
            replace:(BOOL)replace completion:(void (^)(NSDictionary *, NSError *))completion {
  [self installPack:pack engine:engine identity:identity replace:replace confirmed:NO completion:completion];
}

// A manual pack with a CI-verified file, as the install path reads a pack: the
// verified file is its one part (folderForPack, size and SHA-256 checks).
static NSDictionary *VerifiedPack(NSDictionary *pack) {
  NSDictionary *file = NeoTexVerifiedFile(pack);
  if (!file || ![pack[@"availability"] isEqual:@"manual"] || ![pack[@"install"] isKindOfClass:NSDictionary.class]) return nil;
  NSMutableDictionary *effective = [pack mutableCopy];
  effective[@"download"] = @{@"automatable": @NO, @"format": file[@"format"], @"size": file[@"size"], @"sha256": file[@"sha256"],
                             @"parts": @[@{@"size": file[@"size"], @"sha256": file[@"sha256"]}]};
  return effective;
}

- (NSString *)archiveForPack:(NSDictionary *)pack {
  return [[self folderForPack:pack] stringByAppendingPathComponent:[@"archive" stringByAppendingPathExtension:NeoTexString(pack[@"download"][@"format"])]];
}

- (void)installPack:(NSDictionary *)pack engine:(id<NeoTextureEngine>)engine identity:(NSDictionary *)identity
            replace:(BOOL)replace confirmed:(BOOL)confirmed completion:(void (^)(NSDictionary *, NSError *))completion {
  // The catalogue's verdict for the game it is installed for, whatever the
  // caller passed: engine checks and target folders depend on it.
  pack = [NeoTextureCatalog pack:pack matchedTo:identity];
  // A verified file the user already imported for a manual pack installs like a download.
  NSDictionary *verified = VerifiedPack(pack);
  if (verified && [NSFileManager.defaultManager fileExistsAtPath:[self archiveForPack:verified]]) pack = verified;
  NSString *packID = NeoTexString(pack[@"id"]);
  NSDictionary *download = pack[@"download"];
  if (pack != verified && (![pack[@"availability"] isEqual:@"available"] || ![download[@"automatable"] boolValue])) {
    dispatch_async(dispatch_get_main_queue(), ^{ completion(nil, PackError(NeoTexturePackErrorManual, @"manualDownload", nil)); });
    return;
  }
  dispatch_async(_queue, ^{
    if (self->_busyPack) {
      dispatch_async(dispatch_get_main_queue(), ^{ completion(nil, PackError(NeoTexturePackErrorBusy, @"busy", nil)); });
      return;
    }
    // Ask before replacing another pack's folder.
    if (!replace) {
      NSDictionary *conflict = [self conflictForPack:pack engine:engine identity:identity];
      if (conflict) {
        dispatch_async(dispatch_get_main_queue(), ^{ completion(nil, PackError(NeoTexturePackErrorConflict, @"conflict", conflict)); });
        return;
      }
    }
    self->_busyPack = packID;
    self->_discardOnFinish = NO;
    self->_cancel = std::make_shared<std::atomic<bool>>(false);
    NSString *folder = [self folderForPack:pack];
    for (NSString *stale in [self downloadFoldersOf:packID])
      if (![stale isEqualToString:folder]) [NSFileManager.defaultManager removeItemAtPath:stale error:nil];
    NSString *archive = [folder stringByAppendingPathComponent:[@"archive" stringByAppendingPathExtension:NeoTexString(download[@"format"])]];
    BOOL downloaded = [NSFileManager.defaultManager fileExistsAtPath:archive];
    // Engines with their own installer check the space again for what they write.
    const unsigned long long needed = [NeoTexturePackStore requiredBytesForPack:pack downloaded:downloaded];
    const unsigned long long free = MIN(self.freeSpace(self.downloadDirectory), self.freeSpace(engine.texturesRoot));
    if (free < needed) {
      [self finish:packID state:@"failed" error:PackError(NeoTexturePackErrorSpace, @"space", @{@"required": @(needed), @"free": @(free)})
            result:nil completion:completion];
      return;
    }
    unsigned long long total = 0;
    for (NSDictionary *part in download[@"parts"]) total += [part[@"size"] unsignedLongLongValue];
    [self update:packID values:@{@"state": downloaded ? @"verifying" : @"downloading", @"received": @0, @"total": @(total), @"error": [NSNull null]} notify:YES];
    void (^install)(void) = ^{
      [self installArchive:archive pack:pack engine:engine identity:identity confirmed:confirmed completion:completion];
    };
    if (downloaded) { install(); return; }
    [self downloadParts:pack index:0 received:0 completion:^(NSError *error) {
      if (error) {
        BOOL cancelled = error.code == NeoTexturePackErrorCancelled;
        [self finish:packID state:cancelled ? @"paused" : @"failed" error:error result:nil completion:completion];
        return;
      }
      install();
    }];
  });
}

- (void)installPack:(NSDictionary *)pack fromFile:(NSURL *)url engine:(id<NeoTextureEngine>)engine identity:(NSDictionary *)identity
            replace:(BOOL)replace confirmed:(BOOL)confirmed completion:(void (^)(NSDictionary *, NSError *))completion {
  pack = VerifiedPack([NeoTextureCatalog pack:pack matchedTo:identity]);
  if (!pack || !url.isFileURL) {
    dispatch_async(dispatch_get_main_queue(), ^{ completion(nil, PackError(NeoTexturePackErrorManual, @"manualDownload", nil)); });
    return;
  }
  NSString *packID = NeoTexString(pack[@"id"]);
  dispatch_async(_queue, ^{
    if (self->_busyPack) {
      dispatch_async(dispatch_get_main_queue(), ^{ completion(nil, PackError(NeoTexturePackErrorBusy, @"busy", nil)); });
      return;
    }
    if (!replace) {
      NSDictionary *conflict = [self conflictForPack:pack engine:engine identity:identity];
      if (conflict) {
        dispatch_async(dispatch_get_main_queue(), ^{ completion(nil, PackError(NeoTexturePackErrorConflict, @"conflict", conflict)); });
        return;
      }
    }
    self->_busyPack = packID;
    self->_discardOnFinish = NO;
    self->_cancel = std::make_shared<std::atomic<bool>>(false);
    std::shared_ptr<std::atomic<bool>> cancel = self->_cancel;
    NSString *folder = [self folderForPack:pack], *archive = [self archiveForPack:pack];
    for (NSString *stale in [self downloadFoldersOf:packID])
      if (![stale isEqualToString:folder]) [NSFileManager.defaultManager removeItemAtPath:stale error:nil];
    const unsigned long long size = [pack[@"download"][@"size"] unsignedLongLongValue];
    const unsigned long long needed = [NeoTexturePackStore requiredBytesForPack:pack downloaded:NO];
    const unsigned long long free = MIN(self.freeSpace(self.downloadDirectory), self.freeSpace(engine.texturesRoot));
    if (free < needed) {
      [self finish:packID state:@"failed" error:PackError(NeoTexturePackErrorSpace, @"space", @{@"required": @(needed), @"free": @(free)})
            result:nil completion:completion];
      return;
    }
    [self update:packID values:@{@"state": @"verifying", @"received": @0, @"total": @(size), @"error": [NSNull null]} notify:YES];
    dispatch_async(self->_work, ^{
      const BOOL scoped = [url startAccessingSecurityScopedResource];
      NSError *error = [self copyVerifiedFile:url.path to:archive pack:pack cancel:cancel];
      if (scoped) [url stopAccessingSecurityScopedResource];
      if (error) {
        [self finish:packID state:@"failed" error:error result:nil completion:completion];
        return;
      }
      dispatch_async(self->_queue, ^{
        [self installArchive:archive pack:pack engine:engine identity:identity confirmed:confirmed completion:completion];
      });
    });
  });
}

// Copies the chosen file next to the downloads, hashing it on the way; only
// the verified size and SHA-256 are accepted (the user's file is never changed).
- (NSError *)copyVerifiedFile:(NSString *)source to:(NSString *)archive pack:(NSDictionary *)pack
                       cancel:(std::shared_ptr<std::atomic<bool>>)cancel {
  NSString *packID = NeoTexString(pack[@"id"]);
  const unsigned long long size = [pack[@"download"][@"size"] unsignedLongLongValue];
  NeoTextureArchive::File in;
  if (!in.open(Std(source))) return PackError(NeoTexturePackErrorArchive, @"unreadable", nil);
  if (in.length() != size) return PackError(NeoTexturePackErrorNotVerified, @"notVerifiedFile", nil);
  [NSFileManager.defaultManager createDirectoryAtPath:archive.stringByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:nil];
  NSString *temporary = [archive stringByAppendingPathExtension:@"copying"];
  [NSFileManager.defaultManager removeItemAtPath:temporary error:nil];
  CC_SHA256_CTX context;
  CC_SHA256_Init(&context);
  {
    NeoTextureArchive::Output out(Std(temporary));
    if (!out.good()) return PackError(NeoTexturePackErrorWrite, @"writeFailed", nil);
    std::unique_ptr<unsigned char[]> buffer(new unsigned char[1 << 20]);
    for (uint64_t at = 0; at < in.length();) {
      if (cancel && cancel->load()) {
        [NSFileManager.defaultManager removeItemAtPath:temporary error:nil];
        return PackError(NeoTexturePackErrorCancelled, @"cancelled", nil);
      }
      const size_t n = size_t(std::min<uint64_t>(1 << 20, in.length() - at));
      if (!in.read(at, buffer.get(), n) || !out.write(buffer.get(), n)) {
        [NSFileManager.defaultManager removeItemAtPath:temporary error:nil];
        return PackError(NeoTexturePackErrorWrite, @"writeFailed", nil);
      }
      CC_SHA256_Update(&context, buffer.get(), (CC_LONG)n);
      at += n;
      if ((at & ((64ULL << 20) - 1)) == 0 || at == in.length())
        dispatch_async(_queue, ^{ [self update:packID values:@{@"received": @(at)} notify:NO]; });
    }
    if (!out.commit()) return PackError(NeoTexturePackErrorWrite, @"writeFailed", nil);
  }
  unsigned char digest[CC_SHA256_DIGEST_LENGTH];
  CC_SHA256_Final(digest, &context);
  NSMutableString *hex = [NSMutableString stringWithCapacity:64];
  for (int i = 0; i < CC_SHA256_DIGEST_LENGTH; i++) [hex appendFormat:@"%02x", digest[i]];
  if (![hex isEqualToString:NeoTexString(pack[@"download"][@"sha256"])]) {
    [NSFileManager.defaultManager removeItemAtPath:temporary error:nil];
    return PackError(NeoTexturePackErrorNotVerified, @"notVerifiedFile", nil);
  }
  [NSFileManager.defaultManager removeItemAtPath:archive error:nil];
  return [NSFileManager.defaultManager moveItemAtPath:temporary toPath:archive error:nil] ? nil : PackError(NeoTexturePackErrorWrite, @"writeFailed", nil);
}

// Fetches part `index` (or verifies it when already complete), then the next.
- (void)downloadParts:(NSDictionary *)pack index:(NSUInteger)index received:(unsigned long long)received
           completion:(void (^)(NSError *))completion {
  NSArray *parts = pack[@"download"][@"parts"];
  NSString *folder = [self folderForPack:pack];
  if (index >= parts.count) {
    dispatch_async(_work, ^{ completion([self assemble:pack]); });
    return;
  }
  NSDictionary *part = parts[index];
  NSString *path = [folder stringByAppendingPathComponent:[NSString stringWithFormat:@"part-%lu", (unsigned long)index]];
  const unsigned long long size = [part[@"size"] unsignedLongLongValue];
  [NSFileManager.defaultManager createDirectoryAtPath:folder withIntermediateDirectories:YES attributes:nil error:nil];
  dispatch_async(_work, ^{
    if ([NSFileManager.defaultManager fileExistsAtPath:path]) {
      unsigned long long actual = 0;
      NSString *digest = [NeoTexturePackStore sha256OfFile:path size:&actual];
      if (actual == size && [digest isEqualToString:part[@"sha256"]]) {
        dispatch_async(self->_queue, ^{ [self downloadParts:pack index:index + 1 received:received + size completion:completion]; });
        return;
      }
      [NSFileManager.defaultManager removeItemAtPath:path error:nil];
    }
    dispatch_async(self->_queue, ^{
      if (self->_cancel && self->_cancel->load()) { completion(PackError(NeoTexturePackErrorCancelled, @"cancelled", nil)); return; }
      [self fetchPart:pack index:index into:path base:received completion:^(NSError *error) {
        if (error) { completion(error); return; }
        dispatch_async(self->_work, ^{
          unsigned long long actual = 0;
          NSString *digest = [NeoTexturePackStore sha256OfFile:path size:&actual];
          if (actual != size || ![digest isEqualToString:part[@"sha256"]]) {
            BOOL html = LooksLikeHTML(path);
            [NSFileManager.defaultManager removeItemAtPath:path error:nil];
            completion(html ? PackError(NeoTexturePackErrorHTML, @"htmlPage", nil)
                            : PackError(NeoTexturePackErrorChanged, @"changed", @{@"expected": part[@"sha256"], @"actual": digest ?: @""}));
            return;
          }
          dispatch_async(self->_queue, ^{ [self downloadParts:pack index:index + 1 received:received + size completion:completion]; });
        });
      }];
    });
  });
}

// Resolve only the provider explicitly declared by the validated catalogue.
// This private seam also lets the Store fixtures exercise cancellation without
// requiring a real provider account or changing the production resolver.
- (id)resolvePart:(NSDictionary *)part
       completion:(void (^)(NSURL *, NSDictionary *, NSError *))completion {
  if (NeoTexIsMegaPart(part)) return NeoTexResolveMegaPart(part, self.session, completion);
  return NeoTexResolveHostPart(part, ^(NSURL *url, NSError *error) { completion(url, nil, error); });
}

static NSError *ResolutionError(NSError *error) {
  NSString *key = NeoTexString(error.userInfo[@"key"]);
  NeoTexturePackError code = [key isEqual:@"cancelled"] ? NeoTexturePackErrorCancelled
      : [key isEqual:@"changed"] ? NeoTexturePackErrorChanged
      : [key isEqual:@"htmlPage"] ? NeoTexturePackErrorHTML : NeoTexturePackErrorNetwork;
  NSMutableDictionary *details = [NSMutableDictionary dictionary];
  for (NSString *name in @[@"status", @"provider_code"])
    if ([error.userInfo[name] isKindOfClass:NSNumber.class]) details[name] = error.userInfo[name];
  return PackError(code, code == NeoTexturePackErrorNetwork ? @"network" : key, details);
}

static BOOL UnsignedHeader(NSString *text, unsigned long long *value) {
  if (!text.length || text.length > 20 || [text rangeOfCharacterFromSet:
      NSCharacterSet.decimalDigitCharacterSet.invertedSet].location != NSNotFound) return NO;
  const char *begin = text.UTF8String;
  char *end = nullptr;
  errno = 0;
  unsigned long long parsed = std::strtoull(begin, &end, 10);
  if (errno || !end || end == begin || *end) return NO;
  if (value) *value = parsed;
  return YES;
}

// A suffix response must cover exactly the remaining verified byte interval.
// Reject mismatched ranges before opening/appending the cache file.
static BOOL MatchesRange(NSString *text, unsigned long long start, unsigned long long size) {
  static NSRegularExpression *expression;
  static dispatch_once_t once;
  dispatch_once(&once, ^{ expression = [NSRegularExpression regularExpressionWithPattern:
      @"^bytes ([0-9]+)-([0-9]+)/([0-9]+)$" options:0 error:nil]; });
  NSTextCheckingResult *match = [expression firstMatchInString:text ?: @"" options:0 range:NSMakeRange(0, text.length)];
  if (!match || !size) return NO;
  unsigned long long a = 0, b = 0, total = 0;
  return UnsignedHeader([text substringWithRange:[match rangeAtIndex:1]], &a) &&
      UnsignedHeader([text substringWithRange:[match rangeAtIndex:2]], &b) &&
      UnsignedHeader([text substringWithRange:[match rangeAtIndex:3]], &total) &&
      a == start && b == size - 1 && total == size && a <= b;
}

- (void)completeResolvedPart:(NSDictionary *)part crypto:(NSDictionary *)crypto partial:(NSString *)partial
                       into:(NSString *)path cancel:(std::shared_ptr<std::atomic<bool>>)cancel
                 completion:(void (^)(NSError *))completion {
  dispatch_async(_work, ^{
    NSError *failure = nil;
    NSString *candidate = partial;
    if (cancel && cancel->load()) failure = PackError(NeoTexturePackErrorCancelled, @"cancelled", nil);
    if (!failure && crypto) {
      // Once decryption starts this file can no longer be resumed as ciphertext.
      // Rename, then decrypt in place: no second archive-sized allocation on disk.
      candidate = [path stringByAppendingPathExtension:@"decrypting"];
      [NSFileManager.defaultManager removeItemAtPath:candidate error:nil];
      if (![NSFileManager.defaultManager moveItemAtPath:partial toPath:candidate error:nil])
        failure = PackError(NeoTexturePackErrorWrite, @"writeFailed", nil);
      else failure = NeoTexDecryptMegaFile(candidate, part, crypto, [cancel] { return cancel && cancel->load(); });
    }
    if (!failure && cancel && cancel->load()) failure = PackError(NeoTexturePackErrorCancelled, @"cancelled", nil);
    if (!failure && ![NSFileManager.defaultManager moveItemAtPath:candidate toPath:path error:nil])
      failure = PackError(NeoTexturePackErrorWrite, @"writeFailed", nil);
    // A failed/cancelled decryption must never leave mixed plaintext/ciphertext
    // that a later Range request could accidentally append to.
    if (crypto && failure && ![candidate isEqualToString:partial])
      [NSFileManager.defaultManager removeItemAtPath:candidate error:nil];
    dispatch_async(self->_queue, ^{ completion(failure); });
  });
}

- (void)fetchResolvedPart:(NSDictionary *)part URL:(NSURL *)url crypto:(NSDictionary *)crypto
                    pack:(NSDictionary *)pack index:(NSUInteger)index into:(NSString *)path
                    base:(unsigned long long)base cancel:(std::shared_ptr<std::atomic<bool>>)cancel
              completion:(void (^)(NSError *))completion {
  if (cancel && cancel->load()) { completion(PackError(NeoTexturePackErrorCancelled, @"cancelled", nil)); return; }
  if (![url.scheme.lowercaseString isEqual:@"https"] || url.user.length || url.password.length) {
    completion(PackError(NeoTexturePackErrorNetwork, @"network", nil)); return;
  }
  NSString *partial = [path stringByAppendingPathExtension:crypto ? @"cipher.partial" : @"host.partial"];
  // Dynamic signed URLs and NSURLSession resume plists are never persisted.
  [NSFileManager.defaultManager removeItemAtPath:[path stringByAppendingPathExtension:@"resume"] error:nil];
  [NSFileManager.defaultManager removeItemAtPath:[path stringByAppendingPathExtension:@"decrypting"] error:nil];
  const unsigned long long expected = [part[@"size"] unsignedLongLongValue];
  struct stat attributes {};
  unsigned long long offset = 0;
  if (::lstat(Std(partial).c_str(), &attributes) == 0) {
    if (!S_ISREG(attributes.st_mode) || attributes.st_size < 0 || (unsigned long long)attributes.st_size > expected) {
      [NSFileManager.defaultManager removeItemAtPath:partial error:nil];
    } else offset = (unsigned long long)attributes.st_size;
  }
  if (offset == expected) {
    [self completeResolvedPart:part crypto:crypto partial:partial into:path cancel:cancel completion:completion];
    return;
  }
  if (self.transport) {
    self.transport(url, partial, offset, ^(unsigned long long written) {
      dispatch_async(self->_queue, ^{
        if (cancel == self->_cancel && !cancel->load())
          [self update:pack[@"id"] values:@{@"received": @(base + MIN(written, expected))} notify:NO];
      });
    }, ^(NSString *contentType, NSError *error) {
      dispatch_async(self->_queue, ^{
        if (cancel->load()) { completion(PackError(NeoTexturePackErrorCancelled, @"cancelled", nil)); return; }
        if (error) { completion(PackError(NeoTexturePackErrorNetwork, @"network", @{@"resumable": @YES})); return; }
        if ([contentType.lowercaseString hasPrefix:@"text/html"]) {
          [NSFileManager.defaultManager removeItemAtPath:partial error:nil];
          completion(PackError(NeoTexturePackErrorHTML, @"htmlPage", nil)); return;
        }
        unsigned long long actual = [[NSFileManager.defaultManager attributesOfItemAtPath:partial error:nil] fileSize];
        if (actual != expected) {
          [NSFileManager.defaultManager removeItemAtPath:partial error:nil];
          completion(PackError(NeoTexturePackErrorChanged, @"changed", nil)); return;
        }
        [self completeResolvedPart:part crypto:crypto partial:partial into:path cancel:cancel completion:completion];
      });
    });
    return;
  }
  NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:url];
  [request setValue:@"NeoStation-iOS" forHTTPHeaderField:@"User-Agent"];
  [request setValue:@"identity" forHTTPHeaderField:@"Accept-Encoding"];
  if (offset) [request setValue:[NSString stringWithFormat:@"bytes=%llu-", offset] forHTTPHeaderField:@"Range"];
  _taskStream = YES;
  _streamPath = partial;
  _streamExpected = expected;
  _streamStart = offset;
  _streamWritten = 0;
  _streamFD = -1;
  _streamError = nil;
  _streamCrypto = crypto;
  _streamPart = part;
  _taskCancel = cancel;
  _taskPack = pack[@"id"];
  _taskPart = index;
  _taskBase = base;
  _taskFinished = [completion copy];
  _task = [self.session dataTaskWithRequest:request];
  _task.taskDescription = path;
  [_task resume];
}

- (void)fetchPart:(NSDictionary *)pack index:(NSUInteger)index into:(NSString *)path base:(unsigned long long)base
       completion:(void (^)(NSError *))completion {
  NSString *packID = pack[@"id"];
  NSDictionary *part = pack[@"download"][@"parts"][index];
  NSString *provider = NeoTexString(part[@"provider"]);
  if (provider.length) {
    if (!NeoTexIsMegaPart(part) && !NeoTexValidHostPart(part)) {
      completion(PackError(NeoTexturePackErrorChanged, @"changed", nil)); return;
    }
    std::shared_ptr<std::atomic<bool>> cancel = _cancel;
    _partResolution = [self resolvePart:part completion:^(NSURL *url, NSDictionary *crypto, NSError *error) {
      dispatch_async(self->_queue, ^{
        // Cancellation can race metadata completion; no late callback starts a download.
        if (cancel == self->_cancel) self->_partResolution = nil;
        if (cancel != self->_cancel || cancel->load() || ![self->_busyPack isEqual:packID]) {
          completion(PackError(NeoTexturePackErrorCancelled, @"cancelled", nil)); return;
        }
        if (error || !url || (NeoTexIsMegaPart(part) && !crypto)) {
          completion(error ? ResolutionError(error) : PackError(NeoTexturePackErrorNetwork, @"network", nil)); return;
        }
        [self fetchResolvedPart:part URL:url crypto:crypto pack:pack index:index into:path base:base cancel:cancel completion:completion];
      });
    }];
    return;
  }
  NSURL *url = [NSURL URLWithString:part[@"url"]];
  NSString *resumePath = [path stringByAppendingPathExtension:@"resume"];
  if (self.transport) {
    // Test transport: the partial file itself is the resume state.
    NSString *partial = [path stringByAppendingPathExtension:@"partial"];
    NSDictionary *attributes = [NSFileManager.defaultManager attributesOfItemAtPath:partial error:nil];
    const unsigned long long offset = attributes.fileSize;
    std::shared_ptr<std::atomic<bool>> cancel = _cancel;
    self.transport(url, partial, offset, ^(unsigned long long written) {
      dispatch_async(self->_queue, ^{ [self update:packID values:@{@"received": @(base + written)} notify:NO]; });
    }, ^(NSString *contentType, NSError *error) {
      dispatch_async(self->_queue, ^{
        if (cancel->load()) { completion(PackError(NeoTexturePackErrorCancelled, @"cancelled", nil)); return; }
        if (error) { completion(PackError(NeoTexturePackErrorNetwork, @"network", @{@"resumable": @YES})); return; }
        if ([contentType.lowercaseString hasPrefix:@"text/html"]) {
          [NSFileManager.defaultManager removeItemAtPath:partial error:nil];
          completion(PackError(NeoTexturePackErrorHTML, @"htmlPage", nil));
          return;
        }
        [NSFileManager.defaultManager moveItemAtPath:partial toPath:path error:nil];
        completion(nil);
      });
    });
    return;
  }
  NSData *resume = [NSData dataWithContentsOfFile:resumePath];
  [NSFileManager.defaultManager removeItemAtPath:resumePath error:nil];
  NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:url];
  [request setValue:@"NeoStation-iOS" forHTTPHeaderField:@"User-Agent"];
  _taskStream = NO;
  _task = resume.length ? [self.session downloadTaskWithResumeData:resume] : [self.session downloadTaskWithRequest:request];
  _taskPack = packID;
  _taskPart = index;
  _taskBase = base;
  _taskFinished = [completion copy];
  _task.taskDescription = path;
  [_task resume];
}

// Provider downloads are data tasks with a ciphertext/body-only partial file.
// Unlike NSURLSession resumeData, this state contains no expiring CDN URL/key.
- (void)URLSession:(NSURLSession *)session dataTask:(NSURLSessionDataTask *)task didReceiveResponse:(NSURLResponse *)response
 completionHandler:(void (^)(NSURLSessionResponseDisposition))completionHandler {
  dispatch_async(_queue, ^{
    if (task != self->_task || !self->_taskStream) { completionHandler(NSURLSessionResponseCancel); return; }
    NSHTTPURLResponse *http = [response isKindOfClass:NSHTTPURLResponse.class] ? (NSHTTPURLResponse *)response : nil;
    NSString *type = [http valueForHTTPHeaderField:@"Content-Type"].lowercaseString ?: @"";
    NSString *encoding = [http valueForHTTPHeaderField:@"Content-Encoding"].lowercaseString ?: @"";
    NSError *failure = nil;
    if (self->_taskCancel && self->_taskCancel->load()) failure = PackError(NeoTexturePackErrorCancelled, @"cancelled", nil);
    else if (!http || (http.statusCode != 200 && http.statusCode != 206))
      failure = PackError(NeoTexturePackErrorNetwork, @"network", @{@"status": @(http.statusCode)});
    else if ([type hasPrefix:@"text/html"])
      failure = PackError(NeoTexturePackErrorHTML, @"htmlPage", nil);
    else if ((encoding.length && ![encoding isEqual:@"identity"]) ||
             (http.statusCode == 206 && !MatchesRange([http valueForHTTPHeaderField:@"Content-Range"], self->_streamStart, self->_streamExpected)) ||
             (http.statusCode == 200 && [http valueForHTTPHeaderField:@"Content-Range"].length))
      failure = PackError(NeoTexturePackErrorChanged, @"changed", nil);
    // A server may legitimately ignore Range and send its full body. Truncate
    // this candidate before writing, rather than appending a second copy.
    if (!failure && http.statusCode == 200) self->_streamStart = 0;
    const unsigned long long remaining = self->_streamExpected - self->_streamStart;
    if (!failure && response.expectedContentLength >= 0 && (unsigned long long)response.expectedContentLength != remaining)
      failure = PackError(NeoTexturePackErrorChanged, @"changed", nil);
    if (!failure) {
      int flags = O_WRONLY | O_CREAT | O_NOFOLLOW | (self->_streamStart ? O_APPEND : O_TRUNC);
      self->_streamFD = ::open(Std(self->_streamPath).c_str(), flags, 0600);
      struct stat attributes {};
      if (self->_streamFD < 0 || ::fstat(self->_streamFD, &attributes) || !S_ISREG(attributes.st_mode) ||
          attributes.st_size < 0 || (unsigned long long)attributes.st_size != self->_streamStart)
        failure = PackError(NeoTexturePackErrorWrite, @"writeFailed", nil);
    }
    self->_streamError = failure;
    if (failure && failure.code != NeoTexturePackErrorNetwork && failure.code != NeoTexturePackErrorCancelled)
      [NSFileManager.defaultManager removeItemAtPath:self->_streamPath error:nil];
    completionHandler(failure ? NSURLSessionResponseCancel : NSURLSessionResponseAllow);
  });
}

- (void)URLSession:(NSURLSession *)session dataTask:(NSURLSessionDataTask *)task didReceiveData:(NSData *)data {
  // The serial delegate waits for each bounded write: NSData callbacks cannot
  // accumulate an archive-sized backlog on the state queue.
  dispatch_sync(_queue, ^{
    if (task != self->_task || !self->_taskStream || self->_streamError) return;
    if (self->_taskCancel && self->_taskCancel->load()) {
      self->_streamError = PackError(NeoTexturePackErrorCancelled, @"cancelled", nil); [task cancel]; return;
    }
    if (self->_streamFD < 0 || self->_streamStart + self->_streamWritten > self->_streamExpected ||
        data.length > self->_streamExpected - self->_streamStart - self->_streamWritten) {
      self->_streamError = PackError(NeoTexturePackErrorChanged, @"changed", nil); [task cancel]; return;
    }
    const unsigned char *bytes = (const unsigned char *)data.bytes;
    NSUInteger at = 0;
    while (at < data.length) {
      // Each write is bounded even when the networking stack coalesces chunks.
      ssize_t n = ::write(self->_streamFD, bytes + at, MIN(NSUInteger(1 << 20), data.length - at));
      if (n < 0 && errno == EINTR) continue;
      if (n <= 0) { self->_streamError = PackError(NeoTexturePackErrorWrite, @"writeFailed", nil); [task cancel]; return; }
      at += NSUInteger(n);
      self->_streamWritten += (unsigned long long)n;
    }
    [self update:self->_taskPack values:@{@"received": @(self->_taskBase + self->_streamStart + self->_streamWritten)} notify:NO];
  });
}

- (void)completeStreamTask:(NSURLSessionTask *)task error:(NSError *)error {
  NSError *failure = _streamError;
  if (_streamFD >= 0) {
    if (!failure && !error && ::fsync(_streamFD)) failure = PackError(NeoTexturePackErrorWrite, @"writeFailed", nil);
    ::close(_streamFD); _streamFD = -1;
  }
  std::shared_ptr<std::atomic<bool>> cancel = _taskCancel;
  if (cancel && cancel->load()) failure = PackError(NeoTexturePackErrorCancelled, @"cancelled", nil);
  if (!failure && error) failure = PackError(NeoTexturePackErrorNetwork, @"network", nil);
  if (!failure && _streamStart + _streamWritten != _streamExpected)
    failure = PackError(NeoTexturePackErrorChanged, @"changed", nil);
  NSString *partial = _streamPath, *path = task.taskDescription;
  NSDictionary *crypto = _streamCrypto, *part = _streamPart;
  void (^finished)(NSError *) = _taskFinished;
  _task = nil; _taskFinished = nil; _taskStream = NO;
  _streamPath = nil; _streamCrypto = nil; _streamPart = nil; _streamError = nil; _taskCancel.reset();
  if (failure) {
    if (failure.code != NeoTexturePackErrorNetwork && failure.code != NeoTexturePackErrorCancelled)
      [NSFileManager.defaultManager removeItemAtPath:partial error:nil];
    finished(failure);
    return;
  }
  [self completeResolvedPart:part crypto:crypto partial:partial into:path cancel:cancel completion:finished];
}

- (void)URLSession:(NSURLSession *)session downloadTask:(NSURLSessionDownloadTask *)task didWriteData:(int64_t)written
 totalBytesWritten:(int64_t)total totalBytesExpectedToWrite:(int64_t)expected {
  dispatch_async(_queue, ^{
    if (task != self->_task) return;
    [self update:self->_taskPack values:@{@"received": @(self->_taskBase + (unsigned long long)MAX(total, 0))} notify:NO];
  });
}

- (void)URLSession:(NSURLSession *)session downloadTask:(NSURLSessionDownloadTask *)task didFinishDownloadingToURL:(NSURL *)location {
  NSHTTPURLResponse *http = [task.response isKindOfClass:NSHTTPURLResponse.class] ? (NSHTTPURLResponse *)task.response : nil;
  NSString *path = task.taskDescription;
  NSString *type = [http valueForHTTPHeaderField:@"Content-Type"].lowercaseString ?: @"";
  // The file must be moved before this callback returns.
  if (http && (http.statusCode == 200 || http.statusCode == 206) && ![type hasPrefix:@"text/html"] && path.length) {
    [NSFileManager.defaultManager removeItemAtPath:path error:nil];
    [NSFileManager.defaultManager moveItemAtURL:location toURL:[NSURL fileURLWithPath:path] error:nil];
  } else if ([type hasPrefix:@"text/html"] && path.length) {
    [@"html" writeToFile:[path stringByAppendingPathExtension:@"html"] atomically:YES encoding:NSUTF8StringEncoding error:nil];
  }
}

- (void)URLSession:(NSURLSession *)session task:(NSURLSessionTask *)task didCompleteWithError:(NSError *)error {
  dispatch_async(_queue, ^{
    if (task != self->_task) return;
    if (self->_taskStream) { [self completeStreamTask:task error:error]; return; }
    void (^finished)(NSError *) = self->_taskFinished;
    NSString *path = task.taskDescription;
    self->_task = nil;
    self->_taskFinished = nil;
    NSData *resume = error.userInfo[NSURLSessionDownloadTaskResumeData];
    if (resume.length && path.length) [resume writeToFile:[path stringByAppendingPathExtension:@"resume"] atomically:YES];
    NSString *htmlMarker = [path stringByAppendingPathExtension:@"html"];
    if ([NSFileManager.defaultManager fileExistsAtPath:htmlMarker]) {
      [NSFileManager.defaultManager removeItemAtPath:htmlMarker error:nil];
      finished(PackError(NeoTexturePackErrorHTML, @"htmlPage", nil));
      return;
    }
    if (error) {
      const BOOL cancelled = [error.domain isEqualToString:NSURLErrorDomain] && error.code == NSURLErrorCancelled;
      finished(cancelled ? PackError(NeoTexturePackErrorCancelled, @"cancelled", @{@"resumable": @(resume.length > 0)})
                         : PackError(NeoTexturePackErrorNetwork, @"network", @{@"resumable": @(resume.length > 0)}));
      return;
    }
    NSHTTPURLResponse *http = [task.response isKindOfClass:NSHTTPURLResponse.class] ? (NSHTTPURLResponse *)task.response : nil;
    if (!http || (http.statusCode != 200 && http.statusCode != 206) || ![NSFileManager.defaultManager fileExistsAtPath:path]) {
      finished(PackError(NeoTexturePackErrorNetwork, @"network", @{@"status": @(http.statusCode)}));
      return;
    }
    finished(nil);
  });
}

- (void)URLSession:(NSURLSession *)session task:(NSURLSessionTask *)task willPerformHTTPRedirection:(NSHTTPURLResponse *)response
        newRequest:(NSURLRequest *)request completionHandler:(void (^)(NSURLRequest *))completionHandler {
  dispatch_async(_queue, ^{
    BOOL allowed = [request.URL.scheme.lowercaseString isEqualToString:@"https"];
    if (task == self->_task && self->_taskStream && (request.URL.user.length || request.URL.password.length)) allowed = NO;
    completionHandler(allowed ? request : nil);
  });
}

- (void)URLSession:(NSURLSession *)session task:(NSURLSessionTask *)task didReceiveChallenge:(NSURLAuthenticationChallenge *)challenge
 completionHandler:(void (^)(NSURLSessionAuthChallengeDisposition, NSURLCredential *))completionHandler {
  dispatch_async(_queue, ^{
    // Public provider files never authenticate an account. Keep the system's
    // normal TLS certificate validation and refuse HTTP/client credentials.
    BOOL provider = task == self->_task && self->_taskStream;
    BOOL trust = [challenge.protectionSpace.authenticationMethod isEqual:NSURLAuthenticationMethodServerTrust];
    completionHandler(provider && !trust ? NSURLSessionAuthChallengeCancelAuthenticationChallenge
                                        : NSURLSessionAuthChallengePerformDefaultHandling, nil);
  });
}

// One archive from verified parts (split archives are byte-concatenated).
- (NSError *)assemble:(NSDictionary *)pack {
  NSDictionary *download = pack[@"download"];
  NSArray *parts = download[@"parts"];
  NSString *folder = [self folderForPack:pack];
  NSString *archive = [folder stringByAppendingPathComponent:[@"archive" stringByAppendingPathExtension:NeoTexString(download[@"format"])]];
  NSString *first = [folder stringByAppendingPathComponent:@"part-0"];
  if (parts.count == 1) {
    [NSFileManager.defaultManager removeItemAtPath:archive error:nil];
    return [NSFileManager.defaultManager moveItemAtPath:first toPath:archive error:nil] ? nil : PackError(NeoTexturePackErrorWrite, @"writeFailed", nil);
  }
  NSString *temporary = [archive stringByAppendingPathExtension:@"joining"];
  [NSFileManager.defaultManager removeItemAtPath:temporary error:nil];
  {
    NeoTextureArchive::Output out(Std(temporary));
    if (!out.good()) return PackError(NeoTexturePackErrorWrite, @"writeFailed", nil);
    std::unique_ptr<unsigned char[]> buffer(new unsigned char[1 << 20]);
    for (NSUInteger i = 0; i < parts.count; i++) {
      NeoTextureArchive::File in;
      if (!in.open(Std([folder stringByAppendingPathComponent:[NSString stringWithFormat:@"part-%lu", (unsigned long)i]])))
        return PackError(NeoTexturePackErrorWrite, @"writeFailed", nil);
      for (uint64_t at = 0; at < in.length();) {
        const size_t n = size_t(std::min<uint64_t>(1 << 20, in.length() - at));
        if (!in.read(at, buffer.get(), n) || !out.write(buffer.get(), n)) return PackError(NeoTexturePackErrorWrite, @"writeFailed", nil);
        at += n;
      }
    }
    if (!out.commit()) return PackError(NeoTexturePackErrorWrite, @"writeFailed", nil);
  }
  if (![[NeoTexturePackStore sha256OfFile:temporary size:nil] isEqualToString:download[@"sha256"]]) {
    [NSFileManager.defaultManager removeItemAtPath:temporary error:nil];
    return PackError(NeoTexturePackErrorChanged, @"changed", nil);
  }
  for (NSUInteger i = 0; i < parts.count; i++)
    [NSFileManager.defaultManager removeItemAtPath:[folder stringByAppendingPathComponent:[NSString stringWithFormat:@"part-%lu", (unsigned long)i]] error:nil];
  return [NSFileManager.defaultManager moveItemAtPath:temporary toPath:archive error:nil] ? nil : PackError(NeoTexturePackErrorWrite, @"writeFailed", nil);
}

- (void)pausePack:(NSString *)packID {
  dispatch_async(_queue, ^{
    if (![self->_busyPack isEqualToString:packID]) return;
    if (self->_cancel) self->_cancel->store(true);
    [self->_partResolution cancel];
    if (self->_taskStream) [self->_task cancel];
    else if ([self->_task isKindOfClass:NSURLSessionDownloadTask.class])
      [(NSURLSessionDownloadTask *)self->_task cancelByProducingResumeData:^(NSData *resume) {}];
  });
}

- (void)cancelPack:(NSString *)packID {
  dispatch_async(_queue, ^{
    if ([self->_busyPack isEqualToString:packID]) {
      self->_discardOnFinish = YES;
      if (self->_cancel) self->_cancel->store(true);
      [self->_partResolution cancel];
      [self->_task cancel];
    }
    dispatch_async(self->_work, ^{
      for (NSString *folder in [self downloadFoldersOf:packID]) [NSFileManager.defaultManager removeItemAtPath:folder error:nil];
      dispatch_async(self->_queue, ^{
        [self->_jobs removeObjectForKey:packID];
        [self update:packID values:@{@"state": @"idle"} notify:YES];
        [self->_jobs removeObjectForKey:packID];
      });
    });
  });
}

#pragma mark - Install

- (NSDictionary *)manifestAt:(NSString *)folder {
  NSDictionary *manifest = NeoTexJSONDictionary(NeoTexReadBounded([folder stringByAppendingPathComponent:ManifestName], 1 << 16));
  return [manifest isKindOfClass:NSDictionary.class] ? manifest : nil;
}

// The engine folders a catalogue pack is installed into. "{id}" stands for
// the game's own folder: a pack published for several IDs of the same
// release (PPSSPP and Azahar read one folder per ID) is installed for the
// game it is chosen for. Nil when that game has no usable identifier.
- (NSArray<NSString *> *)targetsForPack:(NSDictionary *)pack engine:(id<NeoTextureEngine>)engine identity:(NSDictionary *)identity {
  NSArray *folders = pack[@"install"][@"folders"];
  NSMutableArray *targets = [NSMutableArray array];
  NSString *own = identity ? [engine folderForIdentity:identity] : nil;
  for (NSDictionary *folder in folders) {
    NSString *to = NeoTexString(folder[@"to"]);
    if ([to containsString:@"{id}"]) {
      if (!own.length) return nil;
      to = [to stringByReplacingOccurrencesOfString:@"{id}" withString:own];
    } else if ([pack[@"match"] isEqual:@"candidate"] && folders.count == 1 && own) {
      // A pack confirmed for another region of the game becomes this game's folder.
      to = own;
    }
    [targets addObject:to];
  }
  return targets;
}

- (NSDictionary *)conflictForPack:(NSDictionary *)pack engine:(id<NeoTextureEngine>)engine identity:(NSDictionary *)identity {
  if (Delegates(engine)) {
    // The engine's installer replaces the game's pack: ask first when it is another one.
    for (NSDictionary *installed in identity ? [engine installedPacksForIdentity:identity] : @[])
      if (![installed[@"pack_id"] isEqual:pack[@"id"]])
        return @{@"folder": NeoTexString(installed[@"folder"]), @"title": NeoTexString(installed[@"title"]), @"manual": @(!installed[@"pack_id"])};
    return nil;
  }
  for (NSString *target in [self targetsForPack:pack engine:engine identity:identity]) {
    NSString *path = [engine.texturesRoot stringByAppendingPathComponent:target];
    BOOL directory = NO;
    if (![NSFileManager.defaultManager fileExistsAtPath:path isDirectory:&directory] || !directory) continue;
    NSDictionary *manifest = [self manifestAt:path];
    if (![manifest[@"pack_id"] isEqual:pack[@"id"]])
      return @{@"folder": target, @"title": NeoTexString(manifest[@"title"]), @"manual": @(manifest == nil)};
  }
  return nil;
}

- (NSDictionary *)writeManifests:(const NeoTextureInstall::Staged &)staged targets:(NSArray<NSString *> *)targets
                            info:(NSDictionary *)info {
  for (size_t i = 0; i < staged.folders.size() && i < targets.count; i++) {
    NSString *folder = [NSString stringWithUTF8String:staged.folders[i].c_str()];
    if (!NeoTextureInstall::IsDirectory(staged.folders[i])) continue;
    NSMutableDictionary *manifest = [info mutableCopy];
    manifest[@"folder"] = targets[i];
    manifest[@"files"] = @(staged.files[i]);
    manifest[@"bytes"] = @(staged.bytes[i]);
    // The keys of Dolphin's earlier HD texture import (DOLTextureStore) stay
    // readable by it: gameId, count, sourceGameIds.
    manifest[@"gameId"] = targets[i];
    manifest[@"count"] = @(staged.files[i]);
    if (!manifest[@"sourceGameIds"]) manifest[@"sourceGameIds"] = info[@"games"] ?: @[];
    manifest[@"installed_at"] = @((long long)NSDate.date.timeIntervalSince1970);
    if (!NeoTexWriteAtomic(NeoTexJSONData(manifest), [folder stringByAppendingPathComponent:ManifestName], nil))
      return @{@"error": @"writeFailed"};
  }
  return nil;
}

- (void)installArchive:(NSString *)archive pack:(NSDictionary *)pack engine:(id<NeoTextureEngine>)engine
              identity:(NSDictionary *)identity confirmed:(BOOL)confirmed completion:(void (^)(NSDictionary *, NSError *))completion {
  if (Delegates(engine)) {
    [self delegateArchive:archive pack:pack engine:engine identity:identity confirmed:confirmed completion:completion];
    return;
  }
  NSString *packID = pack[@"id"];
  std::shared_ptr<std::atomic<bool>> cancel = _cancel;
  dispatch_async(_work, ^{
    NSArray<NSString *> *targets = [self targetsForPack:pack engine:engine identity:identity];
    if (!targets) {
      [self finish:packID state:@"downloaded" error:PackError(NeoTexturePackErrorLayout, NoFolderKey(engine, identity), nil) result:nil completion:completion];
      return;
    }
    std::vector<NeoTextureInstall::Rule> rules;
    for (NSUInteger i = 0; i < targets.count; i++) rules.push_back(RuleFor(pack[@"install"][@"folders"][i], Std(targets[i])));
    NSError *error = [self stageAndCommit:^NeoTextureInstall::Staged(const std::string &root, const NeoTextureArchive::Progress &progress) {
      return NeoTextureInstall::ExtractArchive(EngineKind(engine), root, Std(archive), rules, progress);
    } engine:engine targets:targets total:[pack[@"download"][@"size"] unsignedLongLongValue] packID:packID cancel:cancel
       info:@{@"pack_id": packID, @"version": NeoTexString(pack[@"version"]), @"title": NeoTexString(pack[@"title"]),
              @"system": NeoTexString(pack[@"system"]), @"engine": engine.engineID, @"source": NeoTexString(pack[@"source_id"]),
              @"authors": pack[@"authors"] ?: @[], @"sha256": NeoTexString(pack[@"download"][@"sha256"] ?: pack[@"download"][@"parts"][0][@"sha256"]),
              @"games": [self gameIDsOfPack:pack]}];
    if (error) {
      [self finish:packID state:error.code == NeoTexturePackErrorCancelled ? @"downloaded" : @"failed" error:error result:nil completion:completion];
      return;
    }
    // The archive is no longer needed once its textures are in place.
    [NSFileManager.defaultManager removeItemAtPath:[self folderForPack:pack] error:nil];
    NSDictionary *result = [self activate:engine identity:identity targets:targets];
    [self finish:packID state:@"done" error:nil result:result completion:completion];
  });
}

// Engines with their own installer: the verified archive (or the subtree the
// catalogue names, expanded on the engine's volume) is handed over as is.
- (void)delegateArchive:(NSString *)archive pack:(NSDictionary *)pack engine:(id<NeoTextureEngine>)engine
               identity:(NSDictionary *)identity confirmed:(BOOL)confirmed completion:(void (^)(NSDictionary *, NSError *))completion {
  NSString *packID = pack[@"id"];
  std::shared_ptr<std::atomic<bool>> cancel = _cancel;
  dispatch_async(_work, ^{
    NSArray *folders = pack[@"install"][@"folders"];
    NSString *from = NeoTexString([folders firstObject][@"from"]);
    // Handed over as downloaded only when nothing is left out (no subtree, no excluded folder).
    const BOOL direct = folders.count == 1 && !from.length && ![[folders firstObject][@"exclude"] count] &&
                        [engine readsArchiveFormat:NeoTexString(pack[@"download"][@"format"])];
    NSString *root = engine.texturesRoot;
    const unsigned long long total = MAX([pack[@"install"][@"bytes"] unsignedLongLongValue], 1ULL);
    dispatch_async(self->_queue, ^{ [self update:packID values:@{@"state": @"installing", @"received": @0, @"total": @(total)} notify:YES]; });
    NSString *source = archive, *expansion = nil;
    if (!direct) {
      if (folders.count != 1 || ![NSFileManager.defaultManager createDirectoryAtPath:root withIntermediateDirectories:YES attributes:nil error:nil]) {
        [self finish:packID state:@"failed" error:PackError(NeoTexturePackErrorWrite, @"writeFailed", nil) result:nil completion:completion];
        return;
      }
      unsigned long long processed = 0;  // read by the lambda only (a __block variable cannot be captured by one)
      NeoTextureArchive::Progress progress = [&](uint64_t n) {
        processed += n;
        const unsigned long long value = processed / 2;  // expansion is the first half
        dispatch_async(self->_queue, ^{ [self update:packID values:@{@"received": @(value)} notify:NO]; });
        return !(cancel && cancel->load());
      };
      const std::vector<NeoTextureInstall::Rule> rules{RuleFor(folders.firstObject, std::string())};
      NeoTextureInstall::Staged staged = NeoTextureInstall::ExtractArchive(EngineKind(engine), Std(root), Std(archive), rules, progress, {},
                                                                           engine.expansionPrefix.UTF8String, true);
      if (staged.staging.empty()) {
        [self finish:packID state:@"failed" error:PackError(NeoTexturePackErrorWrite, @"writeFailed", nil) result:nil completion:completion];
        return;
      }
      expansion = [NSString stringWithUTF8String:staged.staging.c_str()];
      NSError *failure = nil;
      if (staged.status != NeoTextureArchive::Status::ok || !staged.problem.empty()) failure = ArchiveError(staged.status, staged.problem);
      else if (!staged.files[0]) failure = PackError(NeoTexturePackErrorLayout, @"noTextures", nil);
      if (failure) {
        NeoTextureInstall::RemoveTree(staged.staging);
        [self finish:packID state:failure.code == NeoTexturePackErrorCancelled ? @"downloaded" : @"failed" error:failure result:nil completion:completion];
        return;
      }
      source = expansion;
    }
    const double base = direct ? 0 : 0.5;
    NSDictionary *outcome = [engine installSource:source expanded:!direct pack:pack identity:identity confirmed:confirmed
        progress:^(double fraction) {
          const unsigned long long value = (unsigned long long)((base + (1 - base) * MIN(MAX(fraction, 0.0), 1.0)) * total);
          dispatch_async(self->_queue, ^{ [self update:packID values:@{@"received": @(value)} notify:NO]; });
        }
        cancelled:^BOOL { return cancel && cancel->load(); }];
    if (expansion) NeoTextureInstall::RemoveTree(Std(expansion));
    if (![outcome[@"success"] boolValue]) {
      NSError *error = DelegateError(outcome ?: @{});
      // The verified download is kept: a confirmation or a retry installs it without downloading again.
      const BOOL keep = error.code == NeoTexturePackErrorCancelled || error.code == NeoTexturePackErrorRegion ||
                        error.code == NeoTexturePackErrorSpace || error.code == NeoTexturePackErrorBusy;
      [self finish:packID state:keep ? @"downloaded" : @"failed" error:error result:nil completion:completion];
      return;
    }
    NSString *folder = NeoTexString(outcome[@"folder"]);
    NeoTexRegistrySet(engine.engineID, folder, @{@"pack_id": packID, @"version": NeoTexString(pack[@"version"]), @"title": NeoTexString(pack[@"title"]),
                                                 @"sha256": NeoTexString(pack[@"download"][@"sha256"] ?: pack[@"download"][@"parts"][0][@"sha256"]),
                                                 @"source": NeoTexString(pack[@"source_id"]), @"engine_stamp": NeoTexString(outcome[@"engine_stamp"]),
                                                 @"installed_at": @((long long)NSDate.date.timeIntervalSince1970)});
    [NSFileManager.defaultManager removeItemAtPath:[self folderForPack:pack] error:nil];
    [self finish:packID state:@"done" error:nil
          result:@{@"installed": folder.length ? @[folder] : @[], @"activated": @([outcome[@"enabled"] boolValue]),
                   @"live": @([outcome[@"live"] boolValue])}
      completion:completion];
  });
}

- (NSArray *)gameIDsOfPack:(NSDictionary *)pack {
  NSMutableArray *ids = [NSMutableArray array];
  for (NSDictionary *game in pack[@"games"])
    for (NSDictionary *identity in game[@"identities"]) if (NeoTexString(identity[@"value"]).length) [ids addObject:identity[@"value"]];
  return ids;
}

- (NSDictionary *)activate:(id<NeoTextureEngine>)engine identity:(NSDictionary *)identity targets:(NSArray *)targets {
  NSMutableDictionary *result = [@{@"installed": targets} mutableCopy];
  if (!identity) return result;
  NSError *error = nil;
  const BOOL enabled = [engine setActivation:YES identity:identity error:&error];
  result[@"activated"] = @(enabled);
  if (!enabled) result[@"activation_error"] = error.userInfo[@"key"] ?: @"writeFailed";
  return result;
}

// Stages with `extract`, validates, writes manifests and swaps the folders in.
- (NSError *)stageAndCommit:(NeoTextureInstall::Staged (^)(const std::string &root, const NeoTextureArchive::Progress &progress))extract
                     engine:(id<NeoTextureEngine>)engine targets:(NSArray<NSString *> *)targets total:(unsigned long long)total
                     packID:(NSString *)packID cancel:(std::shared_ptr<std::atomic<bool>>)cancel info:(NSDictionary *)info {
  NSString *root = engine.texturesRoot;
  if (![NSFileManager.defaultManager createDirectoryAtPath:root withIntermediateDirectories:YES attributes:nil error:nil])
    return PackError(NeoTexturePackErrorWrite, @"writeFailed", nil);
  const std::string base = Std(root);
  NeoTextureInstall::Recover(base);
  unsigned long long processed = 0;  // read by the lambda only (a __block variable cannot be captured by one)
  dispatch_async(_queue, ^{ [self update:packID values:@{@"state": @"installing", @"received": @0, @"total": @(MAX(total, 1ULL))} notify:YES]; });
  NeoTextureArchive::Progress progress = [&](uint64_t n) {
    processed += n;
    const unsigned long long value = processed;
    dispatch_async(self->_queue, ^{ [self update:packID values:@{@"received": @(value)} notify:NO]; });
    return !(cancel && cancel->load());
  };
  NeoTextureInstall::Staged staged = extract(base, progress);
  struct Cleanup { std::string path; ~Cleanup() { if (!path.empty()) NeoTextureInstall::RemoveTree(path); } } cleanup{staged.staging};
  if (staged.staging.empty()) return PackError(NeoTexturePackErrorWrite, @"writeFailed", nil);
  if (staged.status != NeoTextureArchive::Status::ok || !staged.problem.empty()) return ArchiveError(staged.status, staged.problem);
  if (!NeoTextureInstall::VerifySignatures(staged).empty()) return PackError(NeoTexturePackErrorArchive, @"archiveDamaged", nil);
  BOOL any = NO;
  for (size_t i = 0; i < staged.folders.size(); i++) {
    if (!NeoTextureInstall::IsDirectory(staged.folders[i])) continue;
    any = YES;
    NSString *problem = [engine problemWithStagedFolder:[NSString stringWithUTF8String:staged.folders[i].c_str()] pack:nil];
    if (problem) return PackError(NeoTexturePackErrorLayout, problem, nil);
  }
  if (!any) return PackError(NeoTexturePackErrorLayout, @"noTextures", nil);
  if ([self writeManifests:staged targets:targets info:info]) return PackError(NeoTexturePackErrorWrite, @"writeFailed", nil);
  std::vector<std::string> moves;
  for (NSString *target in targets) moves.push_back(Std(target));
  std::string problem;
  if (!NeoTextureInstall::Commit(base, staged, moves, &problem))
    return PackError(problem == "noTextures" ? NeoTexturePackErrorLayout : NeoTexturePackErrorWrite,
                     problem == "noTextures" ? @"noTextures" : @"writeFailed", nil);
  cleanup.path.clear();
  if ([engine respondsToSelector:@selector(didChangePackFolder:)])
    for (NSString *target in targets) [engine didChangePackFolder:target];
  return nil;
}

#pragma mark - Import

// ARMSX2's original installer reads ZIP/folders. Expand an ordinary user RAR
// privately, then let that same installer inspect serial/CRC/region, ask for
// confirmation and perform its normal rollback. No installed folder is changed
// by this expansion, and no untrusted executable from the archive is copied.
- (NSError *)expandRARImport:(NSURL *)url engine:(id<NeoTextureEngine>)engine
                     cancel:(std::shared_ptr<std::atomic<bool>>)cancel expansion:(NSString **)expansion {
  __block NSError *failure = nil;
  __block NSString *expanded = nil;
  NSError *coordination = nil;
  const BOOL scoped = [url startAccessingSecurityScopedResource];
  NSFileCoordinator *coordinator = [[NSFileCoordinator alloc] initWithFilePresenter:nil];
  [coordinator coordinateReadingItemAtURL:url options:NSFileCoordinatorReadingWithoutChanges error:&coordination byAccessor:^(NSURL *source) {
    BOOL directory = NO;
    if (![NSFileManager.defaultManager fileExistsAtPath:source.path isDirectory:&directory]) {
      failure = PackError(NeoTexturePackErrorArchive, @"unreadable", nil); return;
    }
    if (directory) return;
    NeoTextureArchive::File probe;
    unsigned char magic[4]{};
    if (!probe.open(Std(source.path)) || probe.length() < sizeof(magic) || !probe.read(0, magic, sizeof(magic))) {
      failure = PackError(NeoTexturePackErrorArchive, @"unreadable", nil); return;
    }
    if (std::memcmp(magic, "Rar!", 4)) return;
    NeoTextureArchive::Progress progress = [cancel](uint64_t) { return !(cancel && cancel->load()); };
    NeoTextureArchive::Rar reader;
    auto status = reader.open(Std(source.path), NeoTextureArchive::Limits{}, progress);
    if (status != NeoTextureArchive::Status::ok) { failure = ArchiveError(status, reader.problem()); return; }
    unsigned long long bytes = 0, files = 0;
    const NeoTextureInstall::Limits limits;
    for (const auto &entry : reader.entries()) {
      if (entry.directory || !NeoTextureInstall::Accepts(EngineKind(engine), entry.name)) continue;
      if (++files > limits.maxFiles || entry.size > limits.maxBytes - bytes) {
        failure = PackError(NeoTexturePackErrorArchive, @"archiveTooLarge", nil); return;
      }
      bytes += entry.size;
    }
    if (!files) { failure = PackError(NeoTexturePackErrorLayout, @"noTextures", nil); return; }
    NSString *root = engine.texturesRoot;
    if (![NSFileManager.defaultManager createDirectoryAtPath:root withIntermediateDirectories:YES attributes:nil error:nil]) {
      failure = PackError(NeoTexturePackErrorWrite, @"writeFailed", nil); return;
    }
    const unsigned long long free = self.freeSpace(root), needed = bytes + Headroom;
    if (free < needed) {
      failure = PackError(NeoTexturePackErrorSpace, @"space", @{@"required": @(needed), @"free": @(free)}); return;
    }
    std::vector<NeoTextureInstall::Rule> rules{{"", "", {}}};
    const char *prefix = engine.expansionPrefix.length ? engine.expansionPrefix.UTF8String : NeoTextureInstall::kStagingPrefix;
    auto staged = NeoTextureInstall::ExtractArchive(EngineKind(engine), Std(root), Std(source.path), rules, progress, {}, prefix, true);
    if (staged.staging.empty()) failure = PackError(NeoTexturePackErrorWrite, @"writeFailed", nil);
    else if (staged.status != NeoTextureArchive::Status::ok || !staged.problem.empty()) failure = ArchiveError(staged.status, staged.problem);
    else if (!staged.files[0]) failure = PackError(NeoTexturePackErrorLayout, @"noTextures", nil);
    if (failure) { if (!staged.staging.empty()) NeoTextureInstall::RemoveTree(staged.staging); }
    else expanded = [NSString stringWithUTF8String:staged.staging.c_str()];
  }];
  if (scoped) [url stopAccessingSecurityScopedResource];
  if (coordination && !failure) failure = PackError(NeoTexturePackErrorArchive, @"unreadable", nil);
  if (failure && expanded) { NeoTextureInstall::RemoveTree(Std(expanded)); expanded = nil; }
  if (expansion) *expansion = expanded;
  return failure;
}

- (void)importURL:(NSURL *)url engine:(id<NeoTextureEngine>)engine identity:(NSDictionary *)identity
 allowOtherRegion:(BOOL)allowOtherRegion replace:(BOOL)replace completion:(void (^)(NSDictionary *, NSError *))completion {
  NSString *packID = @"import";
  dispatch_async(_queue, ^{
    if (self->_busyPack) {
      dispatch_async(dispatch_get_main_queue(), ^{ completion(nil, PackError(NeoTexturePackErrorBusy, @"busy", nil)); });
      return;
    }
    self->_busyPack = packID;
    self->_discardOnFinish = NO;
    self->_cancel = std::make_shared<std::atomic<bool>>(false);
    std::shared_ptr<std::atomic<bool>> cancel = self->_cancel;
    [self update:packID values:@{@"state": @"installing", @"received": @0, @"total": @1, @"error": [NSNull null]} notify:YES];
    if (Delegates(engine) && [engine respondsToSelector:@selector(importURL:identity:confirmed:progress:cancelled:)]) {
      dispatch_async(self->_work, ^{
        // The engine's installer replaces the game's pack: ask first.
        NSArray *existing = [engine installedPacksForIdentity:identity];
        if (!replace && existing.count) {
          NSDictionary *installed = existing.firstObject;
          [self finish:packID state:@"failed"
                 error:PackError(NeoTexturePackErrorConflict, @"conflict", @{@"folder": NeoTexString(installed[@"folder"]),
                                                                             @"title": NeoTexString(installed[@"title"]), @"manual": @(!installed[@"pack_id"])})
                result:nil completion:completion];
          return;
        }
        NSString *expansion = nil;
        if ([engine.engineID isEqual:@"armsx2"]) {
          NSError *error = [self expandRARImport:url engine:engine cancel:cancel expansion:&expansion];
          if (error) { [self finish:packID state:@"failed" error:error result:nil completion:completion]; return; }
        }
        // The original archive name supplies the same serial/region hints as a
        // normal import; this is not an exact catalogue match or a bypass.
        struct Cleanup { std::string path; ~Cleanup() { if (!path.empty()) NeoTextureInstall::RemoveTree(path); } } cleanup{Std(expansion)};
        void (^progress)(double) = ^(double fraction) {
          dispatch_async(self->_queue, ^{ [self update:packID values:@{@"received": @(MIN(MAX(fraction, 0.0), 1.0) * 1000), @"total": @1000} notify:NO]; });
        };
        BOOL (^cancelled)(void) = ^BOOL { return cancel && cancel->load(); };
        NSDictionary *outcome;
        if (expansion) outcome = [engine installSource:expansion expanded:YES
            pack:@{@"download": @{@"file_name": url.lastPathComponent ?: @""}} identity:identity
            confirmed:allowOtherRegion progress:progress cancelled:cancelled];
        else outcome = [engine importURL:url identity:identity confirmed:allowOtherRegion progress:progress cancelled:cancelled];
        // Completion can run on another queue before this worker block ends.
        // Remove the private expansion before publishing either outcome.
        if (expansion) NeoTextureInstall::RemoveTree(Std(expansion));
        cleanup.path.clear();
        if (![outcome[@"success"] boolValue]) {
          [self finish:packID state:@"failed" error:DelegateError(outcome ?: @{}) result:nil completion:completion];
          return;
        }
        NSString *folder = NeoTexString(outcome[@"folder"]);
        if (!folder.length && NeoTexString(outcome[@"serial"]).length) folder = [outcome[@"serial"] stringByAppendingPathComponent:@"replacements"];
        // An import is not a catalogue pack: forget any earlier catalogue record of this folder.
        NeoTexRegistrySet(engine.engineID, folder, nil);
        [self finish:packID state:@"done" error:nil
              result:@{@"installed": folder.length ? @[folder] : @[], @"activated": @([outcome[@"enabled"] boolValue])}
          completion:completion];
      });
      return;
    }
    dispatch_async(self->_work, ^{
      NSString *current = IdentityFolderID(engine, identity);
      if (!current.length) {
        [self finish:packID state:@"failed" error:PackError(NeoTexturePackErrorLayout, NoFolderKey(engine, identity), nil) result:nil completion:completion];
        return;
      }
      const BOOL scoped = [url startAccessingSecurityScopedResource];
      __block NSError *outcome = nil;
      __block NSDictionary *result = nil;
      NSError *coordination = nil;
      NSFileCoordinator *coordinator = [[NSFileCoordinator alloc] initWithFilePresenter:nil];
      [coordinator coordinateReadingItemAtURL:url options:NSFileCoordinatorReadingWithoutChanges error:&coordination byAccessor:^(NSURL *source) {
        outcome = [self importFrom:source.path engine:engine identity:identity current:current allowOtherRegion:allowOtherRegion
                           replace:replace cancel:cancel result:&result];
      }];
      if (scoped) [url stopAccessingSecurityScopedResource];
      if (coordination && !outcome && !result) outcome = PackError(NeoTexturePackErrorArchive, @"unreadable", nil);
      [self finish:packID state:outcome ? @"failed" : @"done" error:outcome result:result completion:completion];
    });
  });
}

- (NSError *)importFrom:(NSString *)path engine:(id<NeoTextureEngine>)engine identity:(NSDictionary *)identity current:(NSString *)current
       allowOtherRegion:(BOOL)allowOtherRegion replace:(BOOL)replace cancel:(std::shared_ptr<std::atomic<bool>>)cancel
                 result:(NSDictionary **)result {
  BOOL directory = NO;
  if (![NSFileManager.defaultManager fileExistsAtPath:path isDirectory:&directory]) return PackError(NeoTexturePackErrorArchive, @"unreadable", nil);
  std::vector<std::string> names;
  unsigned long long total = 0;
  NSString *prefix = directory ? [path.lastPathComponent stringByAppendingString:@"/"] : @"";
  if (directory) {
    NSDirectoryEnumerator *walker = [NSFileManager.defaultManager enumeratorAtURL:[NSURL fileURLWithPath:path]
        includingPropertiesForKeys:@[NSURLIsRegularFileKey, NSURLIsSymbolicLinkKey, NSURLFileSizeKey] options:0 errorHandler:nil];
    NSString *base = [path.stringByStandardizingPath.stringByResolvingSymlinksInPath stringByAppendingString:@"/"];
    for (NSURL *entry in walker) {
      if (names.size() > 400000) return PackError(NeoTexturePackErrorArchive, @"archiveTooLarge", nil);
      NSDictionary *values = [entry resourceValuesForKeys:@[NSURLIsRegularFileKey, NSURLIsSymbolicLinkKey, NSURLFileSizeKey] error:nil];
      if ([values[NSURLIsSymbolicLinkKey] boolValue]) return PackError(NeoTexturePackErrorArchive, @"archiveLink", nil);
      if (![values[NSURLIsRegularFileKey] boolValue]) continue;
      NSString *full = entry.path.stringByStandardizingPath.stringByResolvingSymlinksInPath;
      if (![full hasPrefix:base]) continue;
      names.push_back(Std([prefix stringByAppendingString:[full substringFromIndex:base.length]]));
      total += [values[NSURLFileSizeKey] unsignedLongLongValue];
    }
  } else {
    unsigned char magic[6] = {0};
    {
      NeoTextureArchive::File probe;
      if (!probe.open(Std(path)) || !probe.read(0, magic, std::min<uint64_t>(6, probe.length())))
        return PackError(NeoTexturePackErrorArchive, @"unreadable", nil);
    }
    auto collect = [&](auto &reader) -> NSError * {
      const auto status = reader.open(Std(path), NeoTextureArchive::Limits{});
      if (status != NeoTextureArchive::Status::ok) return ArchiveError(status, "");
      for (const auto &entry : reader.entries()) if (!entry.directory) { names.push_back(entry.name); total += entry.size; }
      return nil;
    };
    NSError *error = nil;
    if (!std::memcmp(magic, "7z\xbc\xaf\x27\x1c", 6)) { NeoTextureArchive::SevenZip reader; error = collect(reader); }
    else if (magic[0] == 'P' && magic[1] == 'K') { NeoTextureArchive::Zip reader; error = collect(reader); }
    else if (!std::memcmp(magic, "Rar!", 4)) {
      NeoTextureArchive::Rar reader;
      const auto status = reader.open(Std(path), NeoTextureArchive::Limits{}, [cancel](uint64_t) { return !(cancel && cancel->load()); });
      if (status != NeoTextureArchive::Status::ok) error = ArchiveError(status, reader.problem());
      else for (const auto &entry : reader.entries()) if (!entry.directory) { names.push_back(entry.name); total += entry.size; }
    }
    else return PackError(NeoTexturePackErrorArchive, @"archiveUnsupported", nil);
    if (error) return error;
  }
  const NeoTextureInstall::Layout layout = NeoTextureInstall::Detect(EngineKind(engine), names, Std(current));
  NSMutableArray *found = [NSMutableArray array];
  for (const auto &id : layout.found) [found addObject:[NSString stringWithUTF8String:id.c_str()]];
  if (layout.problem == "otherGame") return PackError(NeoTexturePackErrorLayout, @"otherGame", @{@"sourceIDs": found});
  if (!layout.problem.empty()) return PackError(NeoTexturePackErrorLayout, [NSString stringWithUTF8String:layout.problem.c_str()], nil);
  if (layout.otherRegion && !allowOtherRegion) return PackError(NeoTexturePackErrorRegion, @"otherRegion", @{@"sourceIDs": found});
  NSMutableArray<NSString *> *targets = [NSMutableArray array];
  for (const auto &rule : layout.rules) [targets addObject:[NSString stringWithUTF8String:rule.to.c_str()]];
  if (!replace) {
    for (NSString *target in targets) {
      NSString *existing = [engine.texturesRoot stringByAppendingPathComponent:target];
      BOOL isDirectory = NO;
      if ([NSFileManager.defaultManager fileExistsAtPath:existing isDirectory:&isDirectory] && isDirectory) {
        NSDictionary *manifest = [self manifestAt:existing];
        return PackError(NeoTexturePackErrorConflict, @"conflict", @{@"folder": target, @"title": NeoTexString(manifest[@"title"]), @"manual": @(manifest == nil)});
      }
    }
  }
  const unsigned long long free = self.freeSpace(engine.texturesRoot);
  if (free < total + Headroom) return PackError(NeoTexturePackErrorSpace, @"space", @{@"required": @(total + Headroom), @"free": @(free)});
  const std::string source = Std(path);
  const std::vector<NeoTextureInstall::Rule> rules = layout.rules;
  const BOOL folderSource = directory;
  NSString *title = path.lastPathComponent.stringByDeletingPathExtension;
  NSError *error = [self stageAndCommit:^NeoTextureInstall::Staged(const std::string &root, const NeoTextureArchive::Progress &progress) {
    if (folderSource) {
      // Folder entries were listed as "<picked folder>/<relative>": copy from its parent.
      const std::string parent = source.substr(0, source.rfind('/'));
      return NeoTextureInstall::CopyFolder(EngineKind(engine), root, parent, rules, progress);
    }
    return NeoTextureInstall::ExtractArchive(EngineKind(engine), root, source, rules, progress);
  } engine:engine targets:targets total:MAX(total, 1ULL) packID:@"import" cancel:cancel
     info:@{@"pack_id": [@"import:" stringByAppendingString:current], @"version": @"", @"title": title ?: @"", @"system": NeoTexString(identity[@"system"]),
            @"engine": engine.engineID, @"source": @"import", @"games": @[current], @"other_region": @(layout.otherRegion), @"found": found}];
  if (error) return error;
  if (result) *result = [self activate:engine identity:identity targets:targets];
  return nil;
}

#pragma mark - Installed packs

- (NeoTextureInstalled *)installedAt:(NSString *)relative engine:(id<NeoTextureEngine>)engine {
  NSString *path = [engine.texturesRoot stringByAppendingPathComponent:relative];
  BOOL directory = NO;
  if (![NSFileManager.defaultManager fileExistsAtPath:path isDirectory:&directory] || !directory) return nil;
  if (!NeoTexNoLinksBelow(engine.texturesRoot, path)) return nil;
  NSMutableDictionary *installed = [[self manifestAt:path] mutableCopy];
  if (!installed) installed = [@{@"manual": @YES, @"title": relative} mutableCopy];
  else installed[@"manual"] = @NO;
  if (!installed[@"pack_id"] && ![installed[@"manual"] boolValue]) {
    // Imported by Dolphin's earlier HD texture page: {gameId, revision, count, bytes, sourceGameIds}.
    installed[@"imported"] = @YES;
    if (!installed[@"files"] && installed[@"count"]) installed[@"files"] = installed[@"count"];
  }
  installed[@"folder"] = relative;
  return installed;
}

- (NSArray<NeoTextureInstalled *> *)installedForEngine:(id<NeoTextureEngine>)engine {
  if (Delegates(engine)) return [engine installedPacks];
  NSMutableArray *rows = [NSMutableArray array];
  NSArray *children = [[NSFileManager.defaultManager contentsOfDirectoryAtPath:engine.texturesRoot error:nil] sortedArrayUsingSelector:@selector(compare:)];
  for (NSString *child in children) {
    if ([child hasPrefix:@"."] || rows.count >= 4000) continue;
    NSString *relative = [engine.engineID isEqualToString:@"armsx2"] ? [child stringByAppendingPathComponent:@"replacements"] : child;
    NeoTextureInstalled *installed = [self installedAt:relative engine:engine];
    if (installed) [rows addObject:installed];
  }
  return rows;
}

- (NSArray<NeoTextureInstalled *> *)installedForIdentity:(NSDictionary *)identity engine:(id<NeoTextureEngine>)engine {
  if (Delegates(engine)) return [engine installedPacksForIdentity:identity];
  NSMutableArray *rows = [NSMutableArray array];
  NSMutableSet *seen = [NSMutableSet set];
  for (NSString *folder in [engine effectiveFoldersForIdentity:identity]) {
    NeoTextureInstalled *installed = [self installedAt:folder engine:engine];
    if (installed && ![seen containsObject:folder]) { [rows addObject:installed]; [seen addObject:folder]; }
  }
  return rows;
}

- (void)removeInstalled:(NeoTextureInstalled *)installed engine:(id<NeoTextureEngine>)engine completion:(void (^)(NSError *))completion {
  NSString *relative = NeoTexString(installed[@"folder"]);
  dispatch_async(_work, ^{
    const BOOL removed = Delegates(engine) ? [[engine removeInstalledPack:installed][@"success"] boolValue]
                                           : relative.length && NeoTexSafeRelativePath(relative, 160, 2) &&
                                                 NeoTextureInstall::Remove(Std(engine.texturesRoot), Std(relative));
    if (removed && [engine respondsToSelector:@selector(didChangePackFolder:)]) [engine didChangePackFolder:relative];
    NSError *error = removed ? nil : PackError(NeoTexturePackErrorWrite, @"removeFailed", nil);
    dispatch_async(dispatch_get_main_queue(), ^{
      completion(error);
      [[NSNotificationCenter defaultCenter] postNotificationName:NeoTextureCatalogDidChangeNotification object:self userInfo:@{@"pack": relative}];
    });
  });
}

@end

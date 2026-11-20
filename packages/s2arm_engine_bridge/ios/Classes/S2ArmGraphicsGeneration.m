#import "S2ArmGraphicsGeneration.h"
#import <CommonCrypto/CommonDigest.h>
#import <copyfile.h>
#import <errno.h>
#import <stdio.h>
#import <string.h>
#import <fcntl.h>
#import <sys/stat.h>
#import <sys/sysctl.h>
#import <unistd.h>

// Independent of the IPA, the CPU import format, and the engine producer run.
static const NSUInteger kMarioKartGraphicsRevision = 3;
static NSString *const kKart = @"0400C3F00006E000";
static NSString *const kKartBuild = @"9e244438c3d8ef1c703a6a85ef99c4f0";

static BOOL problem(NSError **error, NSString *why) {
  if (error) *error = [NSError errorWithDomain:@"S2ArmGraphicsPreparation" code:1
                                      userInfo:@{NSLocalizedDescriptionKey:why}];
  return NO;
}
static NSString *hex(const unsigned char *bytes, size_t count) {
  NSMutableString *value = [NSMutableString stringWithCapacity:count * 2];
  for (size_t i = 0; i < count; i++) [value appendFormat:@"%02x", bytes[i]];
  return value;
}
static NSString *digest(NSData *data) {
  unsigned char bytes[CC_SHA256_DIGEST_LENGTH];
  CC_SHA256(data.bytes, (CC_LONG)data.length, bytes);
  return hex(bytes, sizeof bytes);
}
static NSString *fileDigest(NSString *path) {
  int fd = open(path.fileSystemRepresentation, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
  if (fd < 0) return nil;
  struct stat st;
  if (fstat(fd, &st) || !S_ISREG(st.st_mode) || !st.st_size) { close(fd); return nil; }
  CC_SHA256_CTX hash; CC_SHA256_Init(&hash);
  unsigned char buf[32768]; ssize_t n;
  while ((n = read(fd, buf, sizeof buf)) != 0) {
    if (n < 0) { if (errno == EINTR) continue; close(fd); return nil; }
    CC_SHA256_Update(&hash, buf, (CC_LONG)n);
  }
  close(fd);
  unsigned char bytes[CC_SHA256_DIGEST_LENGTH]; CC_SHA256_Final(bytes, &hash);
  return hex(bytes, sizeof bytes);
}
static NSString *systemValue(const char *name) {
  char b[256]; size_t size = sizeof b;
  return sysctlbyname(name, b, &size, NULL, 0) == 0 && size && b[size-1] == 0 ? @(b) : nil;
}
static NSDictionary *json(NSString *path) {
  NSData *data = [NSData dataWithContentsOfFile:path];
  id value = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
  return [value isKindOfClass:NSDictionary.class] ? value : nil;
}
static BOOL atomicJSON(NSDictionary *value, NSString *path, NSError **error) {
  NSData *data = [NSJSONSerialization dataWithJSONObject:value options:0 error:error];
  return data && [data writeToFile:path options:NSDataWritingAtomic error:error];
}
static BOOL safeLeaf(id name) {
  return [name isKindOfClass:NSString.class] && [name length] > 0 &&
         [name isEqual:[name lastPathComponent]] && ![name hasPrefix:@"."];
}
static BOOL genID(id value) {
  return [value isKindOfClass:NSString.class] && [value length] == 64 &&
    [value rangeOfCharacterFromSet:[NSCharacterSet characterSetWithCharactersInString:@"0123456789abcdef"].invertedSet].location == NSNotFound;
}
@interface S2ArmGraphicsGeneration ()
- (NSDictionary *)outputsForCount:(uint64_t)expected;
@end

@implementation S2ArmGraphicsGeneration {
  NSString *_base, *_generation, *_source, *_slot, *_seedSlot;
  NSDictionary *_identity;
}
+ (instancetype)startupPlanInLibrary:(NSString *)library chain:(NSString *)chain {
  NSString *dir = [library stringByAppendingPathComponent:kKart];
  NSDictionary *prepared = json([dir stringByAppendingPathComponent:@"prepared.json"])[@"result"];
  if (![prepared isKindOfClass:NSDictionary.class] || ![prepared[@"gid"] isEqual:kKart] ||
      ![prepared[@"success"] isEqual:@YES] || !chain.length) return nil;
  // A committed current revision needs no upgrade at app startup. The game launch
  // still verifies the content, device identity and Metal archives before their use.
  NSDictionary *active = json([dir stringByAppendingPathComponent:@"graphics/active.json"]);
  NSDictionary *identity = active[@"identity"];
  if ([identity isKindOfClass:NSDictionary.class] && [identity[@"revision"] isEqual:@(kMarioKartGraphicsRevision)]) return nil;
  S2ArmGraphicsGeneration *plan = [self planForGame:kKart directory:dir root:[dir stringByAppendingPathComponent:@"root"]
                                              chain:chain reused:YES error:NULL];
  if (!plan || plan.active || [json([plan.wire stringByAppendingPathComponent:@".seeded.json"]) isEqual:plan->_identity]) return nil;
  return plan;
}
+ (instancetype)planForGame:(NSString *)gid directory:(NSString *)gameDir root:(NSString *)root
                      chain:(NSString *)chain reused:(BOOL)reused error:(NSError **)error {
  if ([gid caseInsensitiveCompare:kKart] != NSOrderedSame || ![chain isEqual:@"0be3f28548fd"]) return nil;
  NSString *main = [root stringByAppendingPathComponent:@"exefs/main"];
  NSFileHandle *nso = [NSFileHandle fileHandleForReadingAtPath:main];
  NSData *header = [nso readDataUpToLength:0x60 error:error]; [nso closeFile];
  if (header.length != 0x60 || memcmp(header.bytes, "NSO0", 4)) {
    problem(error, @"Could not read the prepared game's main NSO build ID."); return nil;
  }
  NSString *build = hex((const unsigned char *)header.bytes + 0x40, 16);
  if (![build isEqual:kKartBuild]) return nil;  // the reference belongs to this exact executable
  NSString *metadata = fileDigest([root stringByAppendingPathComponent:@"unpack.tsv"]);
  NSString *pack = [gameDir stringByAppendingPathComponent:@"pack"];
  NSString *applied = [NSString stringWithContentsOfFile:[pack stringByAppendingPathComponent:@".applied"]
                                                 encoding:NSASCIIStringEncoding error:NULL];
  NSDictionary *manifest = json([pack stringByAppendingPathComponent:@"manifest.json"]);
  // The pack writer hashes the complete per-file SHA inventory. Its two
  // independently published receipts must agree; no RomFS rescan at launch.
  if (!metadata || !genID(applied) || ![manifest[@"index_sha256"] isEqual:applied]) {
    problem(error, @"The prepared pack content identity is missing or inconsistent."); return nil;
  }
  NSString *content = [NSString stringWithFormat:@"%@:%@", metadata, applied];
  NSString *machine = systemValue("hw.machine"), *os = systemValue("kern.osversion");
  if (!content || !chain.length || !machine || !os) {
    problem(error, @"Missing graphics cache compatibility identity."); return nil;
  }
  return [[self alloc] initWithDirectory:gameDir gid:gid buildID:build content:content chain:chain
                                hardware:machine osBuild:os reuseLegacy:reused];
}
- (instancetype)initWithDirectory:(NSString *)directory gid:(NSString *)gid buildID:(NSString *)buildID
                          content:(NSString *)content chain:(NSString *)chain hardware:(NSString *)hardware
                          osBuild:(NSString *)osBuild reuseLegacy:(BOOL)reuseLegacy {
  if (!(self = [super init])) return nil;
  _gid = [gid copy]; _gameDir = [directory copy]; _buildID = [buildID copy];
  _identity = @{@"revision":@(kMarioKartGraphicsRevision), @"gid":gid, @"build":buildID, @"content":content,
                @"chain":chain, @"hardware":hardware, @"osBuild":osBuild};
  _generation = digest([NSJSONSerialization dataWithJSONObject:_identity options:NSJSONWritingSortedKeys error:nil]);
  _base = [directory stringByAppendingPathComponent:@"graphics"];
  NSDictionary *previous = json([_base stringByAppendingPathComponent:@"active.json"]);
  NSString *prior = previous[@"generation"], *slot = previous[@"slot"];
  BOOL safePrior = genID(prior) && safeLeaf(slot) && [slot hasPrefix:[prior stringByAppendingString:@"."]];
  if (safePrior && [previous[@"identity"] isEqual:_identity] && [prior isEqual:_generation]) {
    _slot = slot; _wire = [_base stringByAppendingPathComponent:slot];
    NSNumber *pipelines = previous[@"pipelines"];
    NSDictionary *stored = previous[@"outputs"];
    NSDictionary *present = [pipelines isKindOfClass:NSNumber.class] ? [self outputsForCount:pipelines.unsignedLongLongValue] : nil;
    // Additional compatible stage inputs learned during gameplay are valid.
    BOOL matches = present && [stored isKindOfClass:NSDictionary.class] && stored.count &&
                   stored[@"pso_reference.tsv"] && stored[@"pso_reference.archives.tsv"] && stored[@"pipelines/identity.json"];
    if (matches) for (NSString *file in stored) if (![stored[file] isEqual:present[file]]) { matches = NO; break; }
    if (matches) {
      _active = YES; return self;
    }
  }
  if (safePrior && [previous[@"gid"] isEqual:gid] && [previous[@"build"] isEqual:buildID] &&
      [previous[@"chain"] isEqual:chain])
    _source = [_base stringByAppendingPathComponent:slot];
  else if (reuseLegacy) _source = [[directory stringByAppendingPathComponent:@"docs/wire"] stringByAppendingPathComponent:gid];
  // A damaged active cache stays untouched until a different directory succeeds.
  // Persist the chosen slot before copying; a process killed during any later
  // phase finds exactly this work (even if an older receipt remains active).
  NSDictionary *pending = json([_base stringByAppendingPathComponent:@"pending.json"]);
  NSString *candidate = pending[@"slot"];
  // A previous version can store gameplay in a seeded, uncommitted slot.
  // Keep that learned history across the upgrade,
  // including a restart half-way through cloning it into the new generation.
  NSString *seed = [pending[@"identity"] isEqual:_identity] ? pending[@"seedSlot"] : candidate;
  if (safeLeaf(seed)) {
    NSString *folder = [_base stringByAppendingPathComponent:seed];
    NSDictionary *sealedSeed = json([folder stringByAppendingPathComponent:@".seeded.json"]);
    NSMutableDictionary *compatible = [_identity mutableCopy];
    if (sealedSeed && [sealedSeed[@"revision"] isKindOfClass:NSNumber.class]) {
      compatible[@"revision"] = sealedSeed[@"revision"];
      NSString *seedHash = digest([NSJSONSerialization dataWithJSONObject:sealedSeed options:NSJSONWritingSortedKeys error:NULL]);
      if ([seed hasPrefix:[seedHash stringByAppendingString:@"."]] && [sealedSeed isEqual:compatible] &&
          [sealedSeed[@"revision"] unsignedIntegerValue] < kMarioKartGraphicsRevision) {
        _source = folder; _seedSlot = seed;
      }
    }
  }
  if ([pending[@"identity"] isEqual:_identity] && safeLeaf(candidate) && ![slot isEqual:candidate] &&
      [candidate hasPrefix:[_generation stringByAppendingString:@"."]])
    _slot = candidate;
  else _slot = [NSString stringWithFormat:@"%@.%@", _generation, NSUUID.UUID.UUIDString];
  _wire = [_base stringByAppendingPathComponent:_slot];
  return self;
}
- (BOOL)stage:(BOOL (^)(void))cancel progress:(void (^)(NSUInteger))progress error:(NSError **)error {
  NSFileManager *fm = NSFileManager.defaultManager;
  if (![fm createDirectoryAtPath:_wire withIntermediateDirectories:YES attributes:nil error:error]) return NO;
  NSMutableDictionary *pending = [@{@"identity":_identity, @"slot":_slot} mutableCopy];
  if (_seedSlot) pending[@"seedSlot"] = _seedSlot;
  if (!atomicJSON(pending, [_base stringByAppendingPathComponent:@"pending.json"], error)) return NO;
  NSString *marker = [_wire stringByAppendingPathComponent:@".seeded.json"];
  if ([json(marker) isEqual:_identity]) return YES;
  NSUInteger count = 0;
  BOOL hasSource = _source && [fm fileExistsAtPath:_source];
  NSArray *roots = hasSource ? [fm contentsOfDirectoryAtPath:_source error:error] : nil;
  if (hasSource && !roots) return NO;
  for (NSString *name in roots) {
    BOOL stageIndex = [name isEqual:@"stage-index-v1.tsv"] ||
                      ([name hasPrefix:@"stage-index-external-v1-"] && [name hasSuffix:@".tsv"]);
    BOOL stageProducts = [name isEqual:@"priority-stages-v1"];
    if (!([name isEqual:@"shaders"] || [name isEqual:@"pipelines"] || [name isEqual:@"pso_user.tsv"] ||
          [name hasPrefix:@"pso_user.tsv."] || stageIndex || stageProducts)) continue;
    NSMutableArray *todo = [NSMutableArray arrayWithObject:name];
    while (todo.count) {
      if (cancel()) return problem(error, @"Graphics preparation interrupted.");
      NSString *relative = todo.lastObject; [todo removeLastObject];
      NSString *src = [_source stringByAppendingPathComponent:relative];
      NSString *dest = [_wire stringByAppendingPathComponent:relative];
      struct stat st;
      if (lstat(src.fileSystemRepresentation, &st)) return problem(error, @"Cannot inspect the previous graphics cache.");
      if (S_ISDIR(st.st_mode)) {
        if (![fm createDirectoryAtPath:dest withIntermediateDirectories:YES attributes:nil error:error]) return NO;
        NSArray *entries = [fm contentsOfDirectoryAtPath:src error:error]; if (!entries) return NO;
        for (NSString *entry in entries) if (safeLeaf(entry) && ![entry hasSuffix:@".tmp"] &&
                                            !(stageProducts && [entry hasSuffix:@".work"]))
          [todo addObject:[relative stringByAppendingPathComponent:entry]];
      } else if (S_ISREG(st.st_mode)) {
        // A leaf is published by rename only after its clone/copy completes.
        // A killed process resumes at the first missing leaf. Once seeded, the
        // engine owns its files and later resumes never overwrite its checkpoints.
        struct stat done;
        if (lstat(dest.fileSystemRepresentation, &done) || !S_ISREG(done.st_mode) ||
            done.st_size != st.st_size || done.st_mtimespec.tv_sec != st.st_mtimespec.tv_sec ||
            done.st_mtimespec.tv_nsec != st.st_mtimespec.tv_nsec) {
          NSString *tmp = [dest stringByAppendingString:@".seed.tmp"]; unlink(tmp.fileSystemRepresentation);
          if (copyfile(src.fileSystemRepresentation, tmp.fileSystemRepresentation, NULL, COPYFILE_ALL | COPYFILE_CLONE | COPYFILE_EXCL) ||
              rename(tmp.fileSystemRepresentation, dest.fileSystemRepresentation)) {
            unlink(tmp.fileSystemRepresentation); return problem(error, @"Could not copy a compatible graphics cache file.");
          }
        }
        if (!(++count % 64)) progress(count);
      }
    }
  }
  if (cancel()) return problem(error, @"Graphics preparation interrupted.");
  if (![fm createDirectoryAtPath:[_wire stringByAppendingPathComponent:@"shaders"] withIntermediateDirectories:YES attributes:nil error:error]) return NO;
  progress(count);
  return atomicJSON(_identity, marker, error);
}
- (NSDictionary *)outputsForCount:(uint64_t)expected {
  NSString *manifest = [_wire stringByAppendingPathComponent:@"pso_reference.archives.tsv"];
  NSString *text = [NSString stringWithContentsOfFile:manifest encoding:NSUTF8StringEncoding error:nil];
  NSMutableSet *ids = [NSMutableSet set], *files = [NSMutableSet setWithObjects:@"pso_reference.tsv", @"pso_external.tsv", @"pso_reference.archives.tsv",
                                                         @"pipelines/identity.json", nil];
  NSMutableDictionary *batch = [NSMutableDictionary dictionary];
  for (NSString *line in [text componentsSeparatedByString:@"\n"]) {
    if (!line.length) continue;
    NSArray *fields = [line componentsSeparatedByString:@"\t"];
    if (fields.count != 2 || !safeLeaf(fields[0]) || !safeLeaf(fields[1]) || ![fields[1] hasSuffix:@".metalarchive"] ||
        [ids containsObject:fields[0]]) return nil;
    if ([fields[1] hasPrefix:@"batch-"]) batch[fields[0]] = fields[1];
    else if (![fields[1] isEqual:[fields[0] stringByAppendingString:@".metalarchive"]]) return nil;
    [ids addObject:fields[0]]; [files addObject:[@"pipelines" stringByAppendingPathComponent:fields[1]]];
  }
  if (!expected || ids.count != expected) return nil;
  if (batch.count) {
    // The live archive index is append-only. Check the selected mappings
    // while permitting unrelated entries learned during subsequent gameplay.
    NSString *index = [_wire stringByAppendingPathComponent:@"pipelines/batches.tsv"];
    FILE *f = fopen(index.fileSystemRepresentation, "r");
    if (!f) return nil;
    NSMutableDictionary *matched = [NSMutableDictionary dictionary];
    char row[256];
    while (fgets(row, sizeof row, f)) {
      char *tab = strchr(row, '\t'), *end = strchr(row, '\n');
      if (!tab || !end) continue;
      *tab = 0; *end = 0;
      NSString *key = [NSString stringWithUTF8String:row], *name = [NSString stringWithUTF8String:tab + 1];
      if (key && name && batch[key] && [name hasPrefix:@"batch-"] && [name hasSuffix:@".metalarchive"] && safeLeaf(name))
        matched[key] = name;
    }
    BOOL ok = !ferror(f) && [batch isEqual:matched]; fclose(f);
    if (!ok) return nil;
  }
  NSString *profile = [NSString stringWithContentsOfFile:[_wire stringByAppendingPathComponent:@"pso_reference.tsv"]
                                                encoding:NSUTF8StringEncoding error:nil];
  for (NSString *line in [profile componentsSeparatedByString:@"\n"]) {
    if (![line hasPrefix:@"S\t"]) continue;
    NSArray *parts = [line componentsSeparatedByString:@"\t"];
    if (parts.count != 3 || !safeLeaf(parts[1])) return nil;
    NSString *base = [@"shaders" stringByAppendingPathComponent:parts[1]];
    // A packed stage can be supplied by the immutable prepared game. When
    // using an on-device translation, bind its source/library and reflection.
    for (NSString *suffix in @[@"metal", @"metallib", @"json", @"in"]) {
      NSString *leaf = [base stringByAppendingPathExtension:suffix];
      if ([NSFileManager.defaultManager fileExistsAtPath:[_wire stringByAppendingPathComponent:leaf]]) [files addObject:leaf];
    }
  }
  NSMutableDictionary *inventory = [NSMutableDictionary dictionary];
  for (NSString *name in files) {
    NSString *file = [_wire stringByAppendingPathComponent:name];
    NSString *hash;
    if ([name isEqual:@"pipelines/identity.json"]) {
      // The renderer also writes a localized OS display name. Its existing
      // compatibility check uses the OS build; changing system language does
      // not invalidate a strict archive hit.
      NSDictionary *stamp = json(file);
      if (![stamp[@"schema"] isKindOfClass:NSNumber.class] || ![stamp[@"gpu"] isKindOfClass:NSString.class] ||
          ![stamp[@"chain"] isEqual:_identity[@"chain"]] || ![stamp[@"osBuild"] isEqual:_identity[@"osBuild"]]) return nil;
      NSData *identity = [NSJSONSerialization dataWithJSONObject:@[stamp[@"schema"],stamp[@"gpu"],stamp[@"chain"],stamp[@"osBuild"]]
                                                         options:0 error:NULL];
      hash = digest(identity);
    } else hash = fileDigest(file);
    if (!hash) return nil;
    inventory[name] = hash;
  }
  return inventory;
}
// These engine-generated tables contain identifiers, descriptors and
// recovery results. Shader bytes, archive binaries and paths stay in Library.
static NSData *evidenceTable(NSString *path) {
  BOOL coverage = [path.lastPathComponent isEqual:@"stage-scan-coverage.plist"];
  const off_t limit = coverage ? 8192 : [path.lastPathComponent isEqual:@"stage-recovery.tsv"] ? 4 * 1024 * 1024 : 512 * 1024;
  int fd = open(path.fileSystemRepresentation, O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK);
  if (fd < 0) return nil;
  struct stat st;
  if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_size <= 0 || st.st_size > limit) { close(fd); return nil; }
  NSMutableData *data = [NSMutableData dataWithLength:(NSUInteger)st.st_size];
  unsigned char *bytes = data.mutableBytes;
  size_t have = 0;
  while (have < data.length) {
    ssize_t n = read(fd, bytes + have, data.length - have);
    if (n < 0 && errno == EINTR) continue;
    if (n <= 0) { close(fd); return nil; }
    have += (size_t)n;
  }
  unsigned char extra; ssize_t tail = read(fd,&extra,1); close(fd);
  if (tail) return nil;
  if ([path.lastPathComponent isEqual:@"external-profile-counts.plist"]) {
    id counters = [NSPropertyListSerialization propertyListWithData:data options:NSPropertyListImmutable format:NULL error:NULL];
    if (![counters isKindOfClass:NSDictionary.class]) return nil;
    return [NSPropertyListSerialization dataWithPropertyList:counters format:NSPropertyListXMLFormat_v1_0 options:0 error:NULL];
  }
  if (coverage) {
    // Export known counters and optional phase durations, including when
    // Foundation represents the source dictionary as a binary plist.
    id object = [NSPropertyListSerialization propertyListWithData:data options:NSPropertyListImmutable format:NULL error:NULL];
    if (![object isKindOfClass:NSDictionary.class]) return nil;
    NSMutableDictionary *counts = [NSMutableDictionary dictionary];
    for (NSString *key in @[@"spooled", @"unavailableDictionary", @"corrupt", @"resourceLimits", @"ioErrors", @"unlocatedRequestedKeys"]) {
      id value = object[key];
      if (![value isKindOfClass:NSNumber.class] || [value longLongValue] < 0) return nil;
      counts[key] = @([value unsignedLongLongValue]);
    }
    for (NSString *key in @[@"targetLookupMs", @"assetScanMs", @"stageRecoveryMs"]) {
      id value = object[key];
      if ([value isKindOfClass:NSNumber.class] && [value longLongValue] >= 0)
        counts[key] = @([value unsignedLongLongValue]);
    }
    return [NSPropertyListSerialization dataWithPropertyList:counts format:NSPropertyListXMLFormat_v1_0 options:0 error:NULL];
  }
  if (![[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding]) return nil;
  for (NSUInteger i=0; i<have; ++i)
    if (bytes[i] < 32 && bytes[i] != '\t' && bytes[i] != '\n' && bytes[i] != '\r') return nil;
  return data;
}
- (BOOL)writeEvidenceToDirectory:(NSString *)gameDiagnostics session:(NSString *)session phase:(NSString *)phase {
  BOOL verified = [phase isEqual:@"verified"] || [phase isEqual:@"reused"];
  BOOL inputs = verified || [phase isEqual:@"inputs"] || [phase isEqual:@"resumed"];
  if (!inputs && ![phase isEqual:@"starting"] && ![phase isEqual:@"incomplete"] && ![phase isEqual:@"interrupted"]) return NO;
  if (![[NSUUID alloc] initWithUUIDString:session] || ![gameDiagnostics.lastPathComponent isEqual:_gid]) return NO;
  NSFileManager *fm = NSFileManager.defaultManager;
  NSString *root = [gameDiagnostics stringByAppendingPathComponent:@"preparation"];
  NSString *dir = [root stringByAppendingPathComponent:session], *receipt = [dir stringByAppendingPathComponent:@"identity.json"];
  if (![fm createDirectoryAtPath:dir withIntermediateDirectories:YES attributes:nil error:NULL]) return NO;
  NSDictionary *previous = json(receipt);
  if (previous && (![previous[@"generation"] isEqual:_slot] || ![previous[@"gid"] isEqual:_gid] ||
      ![previous[@"session"] isEqual:session] || ![previous[@"gameBuild"] isEqual:_buildID])) return NO;
  NSMutableDictionary *copied = [previous[@"files"] isKindOfClass:NSDictionary.class] ? [previous[@"files"] mutableCopy] : [NSMutableDictionary dictionary];
  NSMutableArray *missing = [NSMutableArray array];
  NSArray *tables = !inputs ? @[] : verified ? @[@"stage-recovery.tsv",@"stage-scan-coverage.plist",@"pso_reference.tsv",@"pso_reference.archives.tsv"]
                                              : @[@"stage-recovery.tsv",@"stage-scan-coverage.plist",@"pso_reference.tsv"];
  NSMutableArray *available = [tables mutableCopy];
  for (NSString *name in @[@"pso_reference.progress.tsv", @"external-profile-counts.plist"]) {
    if ([fm fileExistsAtPath:[_wire stringByAppendingPathComponent:name]]) [available addObject:name];
  }
  for (NSString *name in available) {
    NSData *data = evidenceTable([_wire stringByAppendingPathComponent:name]);
    if (!data) { [missing addObject:name]; continue; }
    NSString *out = [dir stringByAppendingPathComponent:name];
    if (![data writeToFile:out options:NSDataWritingAtomic error:NULL]) return NO;
    copied[name] = @{@"bytes":@(data.length), @"sha256":digest(data)};
  }
  NSDictionary *info = @{@"gid":_gid, @"gameBuild":_buildID, @"generation":_slot, @"session":session,
    @"graphicsRevision":_identity[@"revision"], @"appBuild":NSBundle.mainBundle.infoDictionary[@"CFBundleVersion"] ?: @"-",
    @"phase":phase, @"files":copied, @"unavailable":missing, @"capturedAt":@([NSDate date].timeIntervalSince1970)};
  if (!atomicJSON(info, receipt, NULL)) return NO;
  if (!previous) {
    // Preserve the four most recent sessions for this game, at up to three
    // bounded tables and scan counters each. Only remove our exports.
    NSMutableDictionary<NSString *,NSNumber *> *older = [NSMutableDictionary dictionary];
    for (NSString *other in [fm contentsOfDirectoryAtPath:root error:NULL]) {
      if ([other isEqual:session] || ![[NSUUID alloc] initWithUUIDString:other]) continue;
      NSString *path = [[root stringByAppendingPathComponent:other] stringByAppendingPathComponent:@"identity.json"];
      NSDictionary *record = json(path);
      if ([record[@"gid"] isEqual:_gid] && [record[@"session"] isEqual:other] &&
          [record[@"capturedAt"] isKindOfClass:NSNumber.class]) older[other] = record[@"capturedAt"];
    }
    NSArray *ordered = [older keysSortedByValueUsingSelector:@selector(compare:)];
    for (NSUInteger i=0; i+3 < ordered.count; ++i)
      [fm removeItemAtPath:[root stringByAppendingPathComponent:ordered[i]] error:NULL];
  }
  return YES;
}
- (BOOL)activateWithGPU:(const uint64_t *)s error:(NSError **)error {
  if (!s[0] || s[0] != s[1] || !s[2] || s[2] != s[3] || s[2] != s[4])
    return problem(error, @"The complete GPU profile has not passed strict archive verification.");
  NSDictionary *outputs = [self outputsForCount:s[4]];
  if (!outputs) return problem(error, @"The verified pipeline files are missing or incomplete.");
  _active = atomicJSON(@{@"generation":_generation, @"slot":_slot, @"identity":_identity, @"gid":_gid, @"build":_buildID,
                      @"chain":_identity[@"chain"], @"stages":@(s[1]), @"pipelines":@(s[4]), @"deferredRecipes":@(s[5]), @"outputs":outputs},
                    [_base stringByAppendingPathComponent:@"active.json"], error);
  return _active;
}
@end

@implementation S2ArmGraphicsRetry {
  NSArray<NSString *> *_paths;
  void *_engine;
}
- (instancetype)initWithEngine:(void *)engine game:(NSString *)gid paths:(NSArray<NSString *> *)paths {
  if ((self = [super init])) { _gid = [gid copy]; _paths = [paths copy]; _engine = engine; }
  return self;
}
- (void *)engineForGame:(NSString *)gid paths:(NSArray<NSString *> *)paths {
  return _engine && [_gid isEqual:gid] && [_paths isEqual:paths] ? _engine : NULL;
}
- (void)consume { _engine = NULL; }
@end

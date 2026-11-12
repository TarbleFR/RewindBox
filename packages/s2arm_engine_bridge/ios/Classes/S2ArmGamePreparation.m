// See S2ArmGamePreparation.h. Runs native/s2arm/prepare's chain (S2ArmPrepareABI.h) into Library/S2Arm/<gid>.
#import "S2ArmGamePreparation.h"
#import "S2ArmGuestABI.h"
#import "S2ArmPrepareABI.h"
#import "S2ArmLaunchJournal.h"
#import "S2ArmCodePages.h"   // s2arm_code_now_ns

#import <CommonCrypto/CommonDigest.h>
#import <stdatomic.h>

NSString *const S2ArmErrorNotExportFolder = @"notExportFolder";
NSString *const S2ArmErrorExportInvalid = @"exportInvalid";
NSString *const S2ArmErrorGameUnsupported = @"gameUnsupported";
NSString *const S2ArmErrorRewriterFailed = @"rewriterFailed";
NSString *const S2ArmErrorIo = @"storageError";
NSString *const S2ArmErrorCancelled = @"cancelled";
NSString *const S2ArmErrorInsufficientSpace = @"insufficientSpace";
NSString *const S2ArmErrorSystemDataMissing = @"systemDataMissing";
NSString *const S2ArmErrorEngineChainMissing = @"engineChainMissing";
NSString *const S2ArmErrorPrepareFailed = @"prepareFailed";
NSString *const S2ArmErrorGameIdMismatch = @"gameIdMismatch";
NSString *const S2ArmErrorInvalidArguments = @"invalidArguments";

static NSString *S2ArmAppSupport(void) {
  // Library/Application Support is excluded from iCloud/iTunes backup differently from Documents; Library itself is private.
  NSArray *paths = NSSearchPathForDirectoriesInDomains(NSLibraryDirectory, NSUserDomainMask, YES);
  return paths.firstObject ?: NSTemporaryDirectory();
}

NSString *S2ArmLibraryRoot(void) {
  NSString *root = [S2ArmAppSupport() stringByAppendingPathComponent:@"S2Arm"];
  NSFileManager *files = NSFileManager.defaultManager;
  if (![files fileExistsAtPath:root]) {
    [files createDirectoryAtPath:root withIntermediateDirectories:YES attributes:nil error:nil];
    NSURL *url = [NSURL fileURLWithPath:root];
    [url setResourceValue:@YES forKey:NSURLIsExcludedFromBackupKey error:nil];
  }
  return root;
}

NSString *S2ArmGameDirectory(NSString *gid) {
  return [S2ArmLibraryRoot() stringByAppendingPathComponent:gid];
}

NSString *_Nullable S2ArmShippedDirectChain(void) {
  // Written beside the framework by the engine producer (guest.mk): the chain version the direct skeleton must carry.
  NSString *dir = NSBundle.mainBundle.privateFrameworksPath;
  if (dir.length == 0) return nil;
  NSString *path = [dir stringByAppendingPathComponent:@"S2ArmEngine.framework/S2ArmDirectChain.txt"];
  NSString *text = [[NSString stringWithContentsOfFile:path encoding:NSUTF8StringEncoding error:nil]
      stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
  return (text.length >= 1 && text.length <= 12) ? text : nil;
}

NSString *_Nullable S2ArmShippedSystemData(void) {
  // The delivery ships the whole system data tree as <app>/S2ArmSystemData (systemdata/, licenses/, SOURCES.tsv,
  // SHA256SUMS: docs/s2arm-engine-bridge.md). The engine reads a resource pack's systemdata/ folder (fonts/,
  // 010000000000080E/, <id>/), so that subfolder is the one linked into each game's pack.
  NSString *path = [NSBundle.mainBundle.resourcePath stringByAppendingPathComponent:@"S2ArmSystemData/systemdata"];
  BOOL directory = NO;
  return [NSFileManager.defaultManager fileExistsAtPath:path isDirectory:&directory] && directory ? path : nil;
}

NSDictionary *S2ArmDetectExport(NSString *folder) {
  if (folder.length == 0 || !folder.isAbsolutePath) {
    return @{@"success" : @NO, @"code" : S2ArmErrorInvalidArguments};
  }
  char dump[4096] = "";
  uint64_t programId = 0;
  char error[512] = "";
  int rc = rb_s2arm_ns2_detect(folder.fileSystemRepresentation, dump, sizeof dump, &programId, error, sizeof error);
  if (rc != RB_S2ARM_NS2_OK) {
    return @{@"success" : @NO, @"code" : S2ArmErrorNotExportFolder, @"diagnostic" : @(error)};
  }
  return @{
    @"success" : @YES,
    @"exportDir" : [NSString stringWithUTF8String:dump],
    @"programId" : [NSString stringWithFormat:@"%016llx", (unsigned long long)programId],
    @"gid" : [NSString stringWithFormat:@"%016llX", (unsigned long long)programId],
  };
}

// NACP (0x4000 bytes): ApplicationTitle[16] of 0x300 (name[0x200] + publisher[0x100]); DisplayVersion UTF-8 at 0x3060 (0x10).
static NSString *_Nullable nacpString(const uint8_t *nacp, int entry, int offset, int length) {
  const uint8_t *field = nacp + (size_t)entry * 0x300 + offset;
  int end = 0;
  while (end < length && field[end]) end++;
  if (end == 0) return nil;
  return [[NSString alloc] initWithBytes:field length:end encoding:NSUTF8StringEncoding];
}

static int localeLanguageIndex(NSString *localePref) {
  NSString *code = [[localePref ?: @"" componentsSeparatedByCharactersInSet:[NSCharacterSet characterSetWithCharactersInString:@"-_"]] firstObject].lowercaseString;
  NSString *region = @"";
  NSArray *parts = [localePref componentsSeparatedByCharactersInSet:[NSCharacterSet characterSetWithCharactersInString:@"-_"]];
  if (parts.count > 1) region = [parts.lastObject uppercaseString];
  NSDictionary *map = @{@"en" : @0, @"ja" : @2, @"fr" : @3, @"de" : @4, @"es" : @6, @"it" : @7, @"nl" : @8, @"pt" : @10, @"ru" : @11, @"ko" : @12};
  if ([code isEqualToString:@"zh"]) return ([region isEqualToString:@"TW"] || [region isEqualToString:@"HK"] || [region isEqualToString:@"MO"]) ? 13 : 14;
  NSNumber *index = map[code ?: @""];
  return index ? index.intValue : -1;
}

static NSString *_Nullable findControlNacp(NSString *root, NSString **iconOut, int depth) {
  if (depth > 3) return nil;
  NSFileManager *files = NSFileManager.defaultManager;
  NSString *control = [root stringByAppendingPathComponent:@"control.nacp"];
  if ([files fileExistsAtPath:control]) {
    NSString *icon = [root stringByAppendingPathComponent:@"icon.jpg"];
    if (iconOut && [files fileExistsAtPath:icon]) *iconOut = icon;
    return control;
  }
  for (NSString *name in [[files contentsOfDirectoryAtPath:root error:nil] sortedArrayUsingSelector:@selector(compare:)]) {
    if ([name isEqualToString:@"exefs"] || [name isEqualToString:@"romfs"]) continue;
    NSString *child = [root stringByAppendingPathComponent:name];
    BOOL directory = NO;
    if ([files fileExistsAtPath:child isDirectory:&directory] && directory) {
      NSString *found = findControlNacp(child, iconOut, depth + 1);
      if (found) return found;
    }
  }
  return nil;
}

NSDictionary *S2ArmGameInfo(NSString *folder, NSString *localePref) {
  NSDictionary *detected = S2ArmDetectExport(folder);
  if (![detected[@"success"] boolValue]) return detected;
  NSString *exportDir = detected[@"exportDir"];
  NSMutableDictionary *info = [@{
    @"success" : @YES,
    @"titleId" : detected[@"programId"],
    @"gid" : detected[@"gid"],
  } mutableCopy];
  NSString *icon = nil;
  NSString *control = findControlNacp(exportDir, &icon, 0);
  NSData *nacp = control ? [NSData dataWithContentsOfFile:control] : nil;
  if (nacp.length >= 0x4000) {
    const uint8_t *bytes = nacp.bytes;
    int preferred = localeLanguageIndex(localePref);
    NSString *title = preferred >= 0 ? nacpString(bytes, preferred, 0, 0x200) : nil;
    NSString *publisher = preferred >= 0 ? nacpString(bytes, preferred, 0x200, 0x100) : nil;
    for (int entry = 0; entry < 16 && title.length == 0; entry++) {
      title = nacpString(bytes, entry, 0, 0x200);
      publisher = nacpString(bytes, entry, 0x200, 0x100);
    }
    const uint8_t *dv = bytes + 0x3060;
    int dvLen = 0;
    while (dvLen < 0x10 && dv[dvLen]) dvLen++;
    if (title.length) info[@"title"] = title;
    if (publisher.length) info[@"publisher"] = publisher;
    if (dvLen) info[@"displayVersion"] = [[NSString alloc] initWithBytes:dv length:dvLen encoding:NSUTF8StringEncoding] ?: @"";
  }
  if (icon.length) info[@"iconPath"] = icon;
  return info;
}

// The steps of a preparation, as reported to Dart: unpack, code, caps, direct, module, pack, then done.
static const NSInteger kPrepareSteps = 6;

@implementation S2ArmGamePreparation {
  _Atomic int _cancelled;
  // Progress throttle (the work queue only): the last step, part and fraction sent, and when.
  NSString *_lastStep;
  NSString *_lastDetail;
  double _lastFraction;
  uint64_t _lastEmitNs;
  // The code stage's phases, journaled with their durations so that the bar's shares can follow measured costs.
  NSString *_phasePart;
  NSString *_phaseName;
  uint64_t _phaseStartNs;
  unsigned long long _phaseDone, _phaseTotal;
}

- (void)cancel {
  atomic_store(&_cancelled, 1);
}

static int prep_cancelled(void *context) {
  S2ArmGamePreparation *self = (__bridge S2ArmGamePreparation *)context;
  return atomic_load(&self->_cancelled) ? 1 : 0;
}

- (void)emit:(NSString *)step index:(NSInteger)index count:(NSInteger)count fraction:(double)fraction {
  [self emit:step index:index count:count fraction:fraction detail:nil work:nil];
}

- (void)emit:(NSString *)step index:(NSInteger)index count:(NSInteger)count fraction:(double)fraction detail:(NSString *_Nullable)detail {
  [self emit:step index:index count:count fraction:fraction detail:detail work:nil];
}

// Sends progress when the step or its part changes, at the end of a step, or after 1 % or 250 ms: the pack stage reports
// bytes far more often than the method channel needs.
- (void)emit:(NSString *)step
       index:(NSInteger)index
       count:(NSInteger)count
    fraction:(double)fraction
      detail:(NSString *_Nullable)detail
        work:(NSDictionary *_Nullable)work {
  if (!self.progress) return;
  uint64_t now = s2arm_code_now_ns();
  BOOL sameStep = [_lastStep isEqualToString:step] && ((_lastDetail == nil && detail == nil) || [_lastDetail isEqualToString:detail]);
  if (sameStep && fraction < 1 && fraction - _lastFraction < 0.01 && now - _lastEmitNs < 250000000ull) return;
  _lastStep = step;
  _lastDetail = detail;
  _lastFraction = fraction;
  _lastEmitNs = now;
  self.progress(step, index, count, fraction, detail, work);
}

// The code stage's steps (addr_need, nro, each module, tables). The bar itself comes from prep_code_work: this one
// only marks the step in the journal, so that two fractions of different meaning never alternate on screen.
static void prep_code_progress(void *context, const char *step, int index, int count) {
  (void)context;
  s2arm_journal("prepare", "codeStep", "\"step\":\"%s\",\"index\":%d,\"count\":%d", step ? step : "", index, count);
}

// Journals the duration of each phase of each part when the next one begins (rewriter passes included).
- (void)notePhase:(NSString *)phase part:(NSString *)part done:(unsigned long long)done total:(unsigned long long)total {
  uint64_t now = s2arm_code_now_ns();
  if ([_phasePart isEqualToString:part] && [_phaseName isEqualToString:phase]) {
    _phaseDone = done;
    _phaseTotal = total;
    return;
  }
  if (_phaseName.length && ![_phaseName isEqualToString:@"start"])
    s2arm_journal("prepare", "codePhase", "\"part\":\"%s\",\"phase\":\"%s\",\"ms\":%llu,\"done\":%llu,\"total\":%llu",
                  _phasePart.UTF8String, _phaseName.UTF8String, (unsigned long long)((now - _phaseStartNs) / 1000000ull),
                  _phaseDone, _phaseTotal);
  _phasePart = part;
  _phaseName = phase;
  _phaseStartNs = now;
  _phaseDone = done;
  _phaseTotal = total;
}

// The code stage's progress bar (rb_s2arm_code_request.work): IPA 728 showed "code · 0%" for minutes on Mario Kart World,
// since nothing reported inside the code stage. Now every pass of the rewriter moves the bar, with its own counts.
static void prep_code_work(void *context, const char *part, const char *phase, int attempt, unsigned long long done,
                           unsigned long long total, double fraction) {
  S2ArmGamePreparation *self = (__bridge S2ArmGamePreparation *)context;
  NSString *partName = part ? @(part) : @"";
  NSString *phaseName = phase ? @(phase) : @"";
  [self notePhase:phaseName part:partName done:done total:total];
  [self emit:@"code"
         index:1
         count:kPrepareSteps
      fraction:fraction
        detail:partName
          work:@{@"phase" : phaseName, @"attempt" : @(attempt), @"done" : @(done), @"total" : @(total)}];
}

// The resource pack stage, by bytes.
static void prep_pack_progress(void *context, uint64_t done, uint64_t total) {
  S2ArmGamePreparation *self = (__bridge S2ArmGamePreparation *)context;
  [self emit:@"pack" index:5 count:kPrepareSteps fraction:(total ? (double)done / (double)total : 0) detail:nil];
}

static NSString *sha256Hex(NSData *data) {
  unsigned char digest[CC_SHA256_DIGEST_LENGTH];
  CC_SHA256(data.bytes, (CC_LONG)data.length, digest);
  NSMutableString *hex = [NSMutableString stringWithCapacity:CC_SHA256_DIGEST_LENGTH * 2];
  for (int i = 0; i < CC_SHA256_DIGEST_LENGTH; i++) [hex appendFormat:@"%02x", digest[i]];
  return hex;
}

// A content fingerprint stable across preparations of the same export: SHA-256 of unpack.tsv (name, version, update, DLC).
// It is this host's own hash (the game has no NSP/XCI for S2Arm to hash), so it only has to bind saves to this content.
static NSString *_Nullable contentIdentity(NSString *root) {
  NSData *data = [NSData dataWithContentsOfFile:[root stringByAppendingPathComponent:@"unpack.tsv"]];
  if (data.length == 0) return nil;
  return sha256Hex(data);
}

// What a finished preparation depends on, kept in <game>/prepared.json:
// - this app build (engine and preparation code);
// - the direct library chain and the system data list;
// - the export as found: its folder, each top-level part (base, update, DLC) with its date, every ExeFS file by size and
//   date, and each RomFS root.
// Any change prepares again. The folder is part of it because the RomFS is read in place through links into the export.
static NSString *preparationFingerprint(NSString *exportDir, NSString *chain, NSString *systemData) {
  NSFileManager *files = NSFileManager.defaultManager;
  NSMutableString *text = [NSMutableString stringWithString:@"s2arm-prepared 1\n"];
  [text appendFormat:@"build %@\nchain %@\nexport %@\n", NSBundle.mainBundle.infoDictionary[@"CFBundleVersion"] ?: @"-", chain,
                     exportDir];
  for (NSString *part in [[files contentsOfDirectoryAtPath:exportDir error:nil] sortedArrayUsingSelector:@selector(compare:)]) {
    if ([part hasPrefix:@"."]) continue;
    NSString *partPath = [exportDir stringByAppendingPathComponent:part];
    [text appendFormat:@"part %@ %.0f\n", part, [[files attributesOfItemAtPath:partPath error:nil].fileModificationDate timeIntervalSince1970]];
    NSString *exefs = [partPath stringByAppendingPathComponent:@"exefs"];
    for (NSString *name in [[files contentsOfDirectoryAtPath:exefs error:nil] sortedArrayUsingSelector:@selector(compare:)]) {
      NSDictionary *file = [files attributesOfItemAtPath:[exefs stringByAppendingPathComponent:name] error:nil];
      [text appendFormat:@"exefs %@/%@ %llu %.0f\n", part, name, file.fileSize, [file.fileModificationDate timeIntervalSince1970]];
    }
    NSString *romfs = [partPath stringByAppendingPathComponent:@"romfs"];
    NSDictionary *romfsAttributes = [files attributesOfItemAtPath:romfs error:nil];
    if (romfsAttributes) {
      [text appendFormat:@"romfs %@ %.0f %lu\n", part, [romfsAttributes.fileModificationDate timeIntervalSince1970],
                         (unsigned long)[files contentsOfDirectoryAtPath:romfs error:nil].count];
    }
  }
  NSData *sums = [NSData dataWithContentsOfFile:[systemData stringByAppendingPathComponent:@"SHA256SUMS"]];
  [text appendFormat:@"systemdata %@\n", sums.length ? sha256Hex(sums) : @"-"];
  return sha256Hex([text dataUsingEncoding:NSUTF8StringEncoding]);
}

// The result of a finished preparation of the same inputs, still on disk, or nil. Before, every launch prepared the game
// again from scratch: minutes for a large game.
static NSDictionary *_Nullable reusablePreparation(NSString *stampPath, NSString *fingerprint, NSString *gid) {
  NSData *data = [NSData dataWithContentsOfFile:stampPath];
  id stamp = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
  if (![stamp isKindOfClass:NSDictionary.class] || ![stamp[@"fingerprint"] isEqual:fingerprint]) return nil;
  NSDictionary *result = stamp[@"result"];
  if (![result isKindOfClass:NSDictionary.class] || ![result[@"gid"] isEqual:gid] || ![result[@"success"] isEqual:@YES]) return nil;
  NSFileManager *files = NSFileManager.defaultManager;
  for (NSString *key in @[ @"root", @"moduleDir", @"imagesPath", @"gameData", @"docs" ]) {
    id path = result[key];
    if (![path isKindOfClass:NSString.class] || ![files fileExistsAtPath:path]) return nil;
  }
  if (![files fileExistsAtPath:[result[@"gameData"] stringByAppendingPathComponent:@".applied"]]) return nil;
  NSMutableDictionary *reused = [result mutableCopy];
  reused[@"reused"] = @YES;
  return reused;
}

static NSString *_Nullable unpackField(NSString *root, NSString *key) {
  NSString *text = [NSString stringWithContentsOfFile:[root stringByAppendingPathComponent:@"unpack.tsv"] encoding:NSUTF8StringEncoding error:nil];
  for (NSString *line in [text componentsSeparatedByString:@"\n"]) {
    NSRange tab = [line rangeOfString:@"\t"];
    if (tab.location != NSNotFound && [[line substringToIndex:tab.location] isEqualToString:key]) {
      return [line substringFromIndex:tab.location + 1];
    }
  }
  return nil;
}

- (NSDictionary *)fail:(NSString *)code stage:(NSString *)stage detail:(const char *)detail {
  s2arm_journal("prepare", "failed", "\"stage\":\"%s\",\"code\":\"%s\"", stage.UTF8String, code.UTF8String);
  return @{@"success" : @NO, @"code" : code, @"stage" : stage, @"diagnostic" : detail ? @(detail) : @""};
}

static NSString *mapPrepareCode(int rc) {
  switch (rc) {
    case RB_S2ARM_PREPARE_GAPS:
    case RB_S2ARM_PREPARE_UNSUPPORTED:
      return S2ArmErrorGameUnsupported;
    case RB_S2ARM_PREPARE_INVALID:
      return S2ArmErrorExportInvalid;
    case RB_S2ARM_PREPARE_CANCELLED:
      return S2ArmErrorCancelled;
    case RB_S2ARM_PREPARE_IO:
      return S2ArmErrorIo;
    default:
      return S2ArmErrorRewriterFailed;
  }
}

- (NSDictionary *)run {
  NSFileManager *files = NSFileManager.defaultManager;
  NSString *chain = self.directChain ?: S2ArmShippedDirectChain();
  if (chain.length < 1 || chain.length > 12) return [self fail:S2ArmErrorEngineChainMissing stage:@"setup" detail:"no direct library chain version"];
  NSString *systemData = self.systemDataFolder ?: S2ArmShippedSystemData();
  if (systemData.length == 0) return [self fail:S2ArmErrorSystemDataMissing stage:@"setup" detail:"no system data tree"];

  NSDictionary *detected = S2ArmDetectExport(self.exportFolder);
  if (![detected[@"success"] boolValue]) {
    return [self fail:detected[@"code"] stage:@"detect" detail:[detected[@"diagnostic"] UTF8String]];
  }
  NSString *gid = detected[@"gid"];
  NSString *exportDir = detected[@"exportDir"];
  NSString *gameDir = S2ArmGameDirectory(gid);
  NSString *root = [gameDir stringByAppendingPathComponent:@"root"];
  NSString *moduleDir = [gameDir stringByAppendingPathComponent:@"module"];
  NSString *imagesPath = [moduleDir stringByAppendingPathComponent:[NSString stringWithFormat:@"S2AImages-%@.dylib", gid]];
  NSString *packDir = [gameDir stringByAppendingPathComponent:@"pack"];
  NSString *docsDir = [gameDir stringByAppendingPathComponent:@"docs"];   // kept across preparations (saves)
  NSString *stampPath = [gameDir stringByAppendingPathComponent:@"prepared.json"];
  NSString *fingerprint = preparationFingerprint(exportDir, chain, systemData);
  NSDictionary *reused = reusablePreparation(stampPath, fingerprint, gid);
  if (reused) {
    s2arm_journal("prepare", "reused", "\"gid\":\"%s\"", gid.UTF8String);
    [self emit:@"done" index:kPrepareSteps count:kPrepareSteps fraction:1 detail:@"reused"];
    return reused;
  }
  s2arm_journal("prepare", "begin", "\"gid\":\"%s\"", gid.UTF8String);

  // The root, module and pack are rebuilt from scratch; docs is preserved. The stamp goes first, so an interrupted
  // preparation is never reused.
  [files removeItemAtPath:stampPath error:nil];
  for (NSString *path in @[ root, moduleDir, packDir ]) [files removeItemAtPath:path error:nil];
  for (NSString *path in @[ gameDir, docsDir, moduleDir ]) [files createDirectoryAtPath:path withIntermediateDirectories:YES attributes:nil error:nil];

  NSMutableDictionary *sizes = [NSMutableDictionary dictionary];
  NSMutableDictionary *durations = [NSMutableDictionary dictionary];
  char error[1024] = "";
  const NSInteger steps = kPrepareSteps;

  // 1. ns2-dump --reference: RomFS and DLC read in place through relative links.
  [self emit:@"unpack" index:0 count:steps fraction:0];
  uint64_t t0 = s2arm_code_now_ns();
  rb_s2arm_ns2_dump_request dump = {exportDir.fileSystemRepresentation, root.fileSystemRepresentation, NULL, 1, NULL, prep_cancelled, (__bridge void *)self, 0};
  int rc = rb_s2arm_ns2_dump(&dump, error, sizeof error);
  if (rc != RB_S2ARM_NS2_OK) {
    NSString *code = rc == RB_S2ARM_NS2_CANCELLED ? S2ArmErrorCancelled : rc == RB_S2ARM_NS2_IO ? S2ArmErrorIo : S2ArmErrorExportInvalid;
    return [self fail:code stage:@"unpack" detail:error];
  }
  durations[@"unpack"] = @((s2arm_code_now_ns() - t0) / 1000000ull);

  // 2. code stage (exefs, romfs -> root).
  [self emit:@"code" index:1 count:steps fraction:0];
  t0 = s2arm_code_now_ns();
  NSString *romfs = [root stringByAppendingPathComponent:@"romfs"];
  rb_s2arm_code_request code = {
      [root stringByAppendingPathComponent:@"exefs"].fileSystemRepresentation,
      [files fileExistsAtPath:romfs] ? romfs.fileSystemRepresentation : NULL,
      root.fileSystemRepresentation,
      prep_code_progress, prep_cancelled, (__bridge void *)self, prep_code_work};
  rc = rb_s2arm_prepare_code(&code, error, sizeof error);
  if (rc != RB_S2ARM_PREPARE_OK) return [self fail:mapPrepareCode(rc) stage:@"code" detail:error];
  durations[@"code"] = @((s2arm_code_now_ns() - t0) / 1000000ull);

  // 3. caps.
  [self emit:@"caps" index:2 count:steps fraction:0];
  t0 = s2arm_code_now_ns();
  rc = rb_s2arm_caps(root.fileSystemRepresentation, [root stringByAppendingPathComponent:@"s2a_caps.tsv"].fileSystemRepresentation,
                     [root stringByAppendingPathComponent:@"s2a_caps.all.tsv"].fileSystemRepresentation, NULL, error, sizeof error);
  if (rc != RB_S2ARM_CAPS_OK) return [self fail:(rc == RB_S2ARM_CAPS_IO ? S2ArmErrorIo : S2ArmErrorExportInvalid) stage:@"caps" detail:error];
  durations[@"caps"] = @((s2arm_code_now_ns() - t0) / 1000000ull);

  // 4. direct skeleton (empty shader library; shaders compile at first use).
  [self emit:@"direct" index:3 count:steps fraction:0];
  t0 = s2arm_code_now_ns();
  rc = rb_s2arm_direct_skeleton(root.fileSystemRepresentation, chain.UTF8String, "rewindbox-phone", "RewindBox: shaders compiled on device", error, sizeof error);
  if (rc != RB_S2ARM_PACK_OK) return [self fail:(rc == RB_S2ARM_PACK_IO ? S2ArmErrorIo : S2ArmErrorExportInvalid) stage:@"direct" detail:error];
  durations[@"direct"] = @((s2arm_code_now_ns() - t0) / 1000000ull);

  // 5. module directory with the image pack.
  [self emit:@"module" index:4 count:steps fraction:0];
  t0 = s2arm_code_now_ns();
  NSString *name = unpackField(root, @"name");
  NSString *contentId = contentIdentity(root);
  rb_s2arm_save_identity identity = {gid.UTF8String, name.length ? name.UTF8String : "RewindBox", 0, contentId.length == 64 ? contentId.UTF8String : NULL};
  rb_s2arm_module_request module = {root.fileSystemRepresentation, moduleDir.fileSystemRepresentation, imagesPath.fileSystemRepresentation,
                                    (name.length && contentId.length == 64) ? &identity : NULL, 0, NULL, NULL, NULL, NULL};
  rc = rb_s2arm_module_dir(&module, error, sizeof error);
  if (rc != RB_S2ARM_PACK_OK) return [self fail:(rc == RB_S2ARM_PACK_IO ? S2ArmErrorIo : S2ArmErrorExportInvalid) stage:@"module" detail:error];
  durations[@"module"] = @((s2arm_code_now_ns() - t0) / 1000000ull);
  sizes[@"imagePack"] = @([[files attributesOfItemAtPath:imagesPath error:nil][NSFileSize] unsignedLongLongValue]);

  // 6. resource pack (RomFS and DLC linked into the product root; system data copied; .applied).
  // The system data is copied (systemdata_link 0, ~20 MB per game), not linked: it lives in the app bundle, whose path
  // (/var/containers/Bundle/Application/<UUID>/...) changes with every app update, so a link from this data container
  // would dangle after an update. RomFS and DLC links stay inside the data container and survive updates.
  [self emit:@"pack" index:5 count:steps fraction:0];
  t0 = s2arm_code_now_ns();
  rb_s2arm_resource_request resource = {root.fileSystemRepresentation, packDir.fileSystemRepresentation, systemData.fileSystemRepresentation, 0, 1,
                                        prep_pack_progress, prep_cancelled, (__bridge void *)self};
  rc = rb_s2arm_resource_pack(&resource, error, sizeof error);
  if (rc != RB_S2ARM_PACK_OK) {
    NSString *mapped = rc == RB_S2ARM_PACK_CANCELLED ? S2ArmErrorCancelled : rc == RB_S2ARM_PACK_IO ? S2ArmErrorIo : S2ArmErrorExportInvalid;
    return [self fail:mapped stage:@"pack" detail:error];
  }
  durations[@"pack"] = @((s2arm_code_now_ns() - t0) / 1000000ull);

  [self emit:@"done" index:6 count:steps fraction:1];
  s2arm_journal("prepare", "passed", "\"gid\":\"%s\",\"imagePackBytes\":%llu", gid.UTF8String, [sizes[@"imagePack"] unsignedLongLongValue]);
  NSDictionary *result = @{
    @"success" : @YES,
    @"gid" : gid,
    @"programId" : detected[@"programId"],
    @"gameDir" : gameDir,
    @"root" : root,
    @"moduleDir" : moduleDir,
    @"imagesPath" : imagesPath,
    @"gameData" : packDir,
    @"docs" : docsDir,
    @"sizes" : sizes,
    @"durationsMs" : durations,
  };
  // The next launch of the same inputs reuses this preparation.
  NSData *stamp = [NSJSONSerialization dataWithJSONObject:@{@"fingerprint" : fingerprint, @"result" : result} options:0 error:nil];
  if (stamp && ![stamp writeToFile:stampPath atomically:YES]) s2arm_journal("prepare", "stamp", "\"written\":false");
  NSMutableDictionary *fresh = [result mutableCopy];
  fresh[@"reused"] = @NO;
  return fresh;
}

@end

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

@implementation S2ArmGamePreparation {
  _Atomic int _cancelled;
}

- (void)cancel {
  atomic_store(&_cancelled, 1);
}

static int prep_cancelled(void *context) {
  S2ArmGamePreparation *self = (__bridge S2ArmGamePreparation *)context;
  return atomic_load(&self->_cancelled) ? 1 : 0;
}

- (void)emit:(NSString *)step index:(NSInteger)index count:(NSInteger)count fraction:(double)fraction {
  if (self.progress) self.progress(step, index, count, fraction);
}

// A content fingerprint stable across preparations of the same export: SHA-256 of unpack.tsv (name, version, update, DLC).
// It is this host's own hash (the game has no NSP/XCI for S2Arm to hash), so it only has to bind saves to this content.
static NSString *_Nullable contentIdentity(NSString *root) {
  NSData *data = [NSData dataWithContentsOfFile:[root stringByAppendingPathComponent:@"unpack.tsv"]];
  if (data.length == 0) return nil;
  unsigned char digest[CC_SHA256_DIGEST_LENGTH];
  CC_SHA256(data.bytes, (CC_LONG)data.length, digest);
  NSMutableString *hex = [NSMutableString stringWithCapacity:CC_SHA256_DIGEST_LENGTH * 2];
  for (int i = 0; i < CC_SHA256_DIGEST_LENGTH; i++) [hex appendFormat:@"%02x", digest[i]];
  return hex;
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
  s2arm_journal("prepare", "begin", "\"gid\":\"%s\"", gid.UTF8String);

  // The root, module and pack are rebuilt from scratch; docs is preserved.
  for (NSString *path in @[ root, moduleDir, packDir ]) [files removeItemAtPath:path error:nil];
  for (NSString *path in @[ gameDir, docsDir, moduleDir ]) [files createDirectoryAtPath:path withIntermediateDirectories:YES attributes:nil error:nil];

  NSMutableDictionary *sizes = [NSMutableDictionary dictionary];
  NSMutableDictionary *durations = [NSMutableDictionary dictionary];
  char error[1024] = "";
  const NSInteger steps = 6;

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
      NULL, prep_cancelled, (__bridge void *)self};
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
                                        NULL, prep_cancelled, (__bridge void *)self};
  rc = rb_s2arm_resource_pack(&resource, error, sizeof error);
  if (rc != RB_S2ARM_PACK_OK) {
    NSString *mapped = rc == RB_S2ARM_PACK_CANCELLED ? S2ArmErrorCancelled : rc == RB_S2ARM_PACK_IO ? S2ArmErrorIo : S2ArmErrorExportInvalid;
    return [self fail:mapped stage:@"pack" detail:error];
  }
  durations[@"pack"] = @((s2arm_code_now_ns() - t0) / 1000000ull);

  [self emit:@"done" index:6 count:steps fraction:1];
  s2arm_journal("prepare", "passed", "\"gid\":\"%s\",\"imagePackBytes\":%llu", gid.UTF8String, [sizes[@"imagePack"] unsignedLongLongValue]);
  return @{
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
}

@end

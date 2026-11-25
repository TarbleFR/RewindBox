// Host-side transaction test. The engine's separate Metal tests supply real GPU
// verification. Counts below exercise only the host's acceptance of that proof.
#import "S2ArmGraphicsGeneration.h"
#import <stdio.h>
#import <CommonCrypto/CommonDigest.h>
#import <stdlib.h>
#import <string.h>

static NSString *const gid = @"0400C3F00006E000";
static NSString *const build = @"9e244438c3d8ef1c703a6a85ef99c4f0";
static NSString *const chain = @"0be3f28548fd";
static NSString *const key = @"0123456789012345678901234567890123456789";
static void require(BOOL ok, int line) {
  if (!ok) { fprintf(stderr, "host graphics transaction failed at line %d\n", line); exit(1); }
}
#define CHECK(x) require((x), __LINE__)
static NSString *child(NSString *root, NSString *name) { return [root stringByAppendingPathComponent:name]; }
static NSString *readText(NSString *root, NSString *name) {
  return [NSString stringWithContentsOfFile:child(root,name) encoding:NSUTF8StringEncoding error:NULL];
}
static void put(NSString *root, NSString *name, NSString *data) {
  NSString *path = child(root,name);
  CHECK([NSFileManager.defaultManager createDirectoryAtPath:path.stringByDeletingLastPathComponent
                                 withIntermediateDirectories:YES attributes:nil error:NULL]);
  CHECK([data writeToFile:path atomically:YES encoding:NSUTF8StringEncoding error:NULL]);
}
static S2ArmGraphicsGeneration *plan(NSString *dir) {
  return [[S2ArmGraphicsGeneration alloc] initWithDirectory:dir gid:gid buildID:build content:@"same-content"
                                                       chain:chain hardware:@"same-device" osBuild:@"same-os" reuseLegacy:YES];
}
static BOOL stage(S2ArmGraphicsGeneration *g) {
  return [g stage:^BOOL { return NO; } progress:^(NSUInteger count) { (void)count; } error:NULL];
}
int main(void) { @autoreleasepool {
  int engineMarker = 0;
  NSArray *launchPaths = @[@"/images",@"/module",@"/pack",@"/docs",@"slot-a"];
  S2ArmGraphicsRetry *retry = [[S2ArmGraphicsRetry alloc] initWithEngine:&engineMarker game:gid paths:launchPaths];
  CHECK([retry engineForGame:gid paths:launchPaths] == &engineMarker);
  CHECK([retry engineForGame:@"0100AAAA00000000" paths:launchPaths] == NULL);
  for (NSUInteger i=0; i<launchPaths.count; ++i) {
    NSMutableArray *changed = [launchPaths mutableCopy]; changed[i] = @"/other";
    CHECK([retry engineForGame:gid paths:changed] == NULL);
  }
  [retry consume]; // consumed before the first call to guest configure
  CHECK([retry engineForGame:gid paths:launchPaths] == NULL);
  // Reopen a partially verified 796 generation whose sole up-to-date personal
  // manifest and shaders live in the pending slot, never promoted to active.
  NSString *upgradeDir = child(NSTemporaryDirectory(), NSUUID.UUID.UUIDString);
  NSDictionary *oldIdentity = @{@"gid":gid,@"build":build,@"content":@"same-content",@"chain":chain,
                               @"hardware":@"same-device",@"osBuild":@"same-os",@"revision":@2};
  NSData *serialized = [NSJSONSerialization dataWithJSONObject:oldIdentity options:NSJSONWritingSortedKeys error:NULL];
  unsigned char sum[CC_SHA256_DIGEST_LENGTH]; CC_SHA256(serialized.bytes,(CC_LONG)serialized.length,sum);
  NSMutableString *oldSlot = [NSMutableString string];
  for (NSUInteger i=0; i<sizeof sum; ++i) [oldSlot appendFormat:@"%02x",sum[i]];
  [oldSlot appendFormat:@".%@",NSUUID.UUID.UUIDString];
  NSString *oldWire = child(child(upgradeDir,@"graphics"),oldSlot);
  put(oldWire,@".seeded.json",[[NSString alloc] initWithData:serialized encoding:NSUTF8StringEncoding]);
  put(oldWire,@"pso_user.tsv",@"796 raced here");
  put(oldWire,@"shaders/only-in-796.in",@"learned while incomplete");
  put(oldWire,@"stage-index-external-v1-example.tsv",@"796 scan checkpoint");
  NSDictionary *pending796=@{@"identity":oldIdentity,@"slot":oldSlot};
  put(upgradeDir,@"graphics/pending.json",[[NSString alloc] initWithData:[NSJSONSerialization dataWithJSONObject:pending796 options:0 error:NULL] encoding:NSUTF8StringEncoding]);
  S2ArmGraphicsGeneration *migration=plan(upgradeDir);
  CHECK(!migration.active && ![oldWire isEqual:migration.wire]);
  CHECK(![migration stage:^BOOL{ return YES; } progress:^(NSUInteger n){ (void)n; } error:NULL]);
  S2ArmGraphicsGeneration *again=plan(upgradeDir);
  CHECK([again.wire isEqual:migration.wire] && stage(again));
  CHECK([readText(again.wire,@"pso_user.tsv") isEqual:@"796 raced here"]);
  CHECK([readText(again.wire,@"shaders/only-in-796.in") isEqual:@"learned while incomplete"]);
  CHECK([readText(again.wire,@"stage-index-external-v1-example.tsv") isEqual:@"796 scan checkpoint"]);
  CHECK([readText(oldWire,@"pso_user.tsv") isEqual:@"796 raced here"]);
  [NSFileManager.defaultManager removeItemAtPath:upgradeDir error:NULL];
  NSString *library = child(NSTemporaryDirectory(), NSUUID.UUID.UUIDString);
  NSString *dir = child(library,gid);
  NSString *legacy = child(child(dir, @"docs/wire"), gid);
  NSString *marker = @"graphics/active.json";
  // Use the production title, NSO and direct-chain gate as well as the
  // injected-platform plans used below for deterministic receipt comparisons.
  NSString *root = child(dir, @"root");
  put(root, @"unpack.tsv", @"title_id\t0400c3f00006e000\n");
  put(root, @"exefs/main", @"placeholder");
  unsigned char header[0x60] = "NSO0";
  const unsigned char idBytes[16] = {0x9e,0x24,0x44,0x38,0xc3,0xd8,0xef,0x1c,0x70,0x3a,0x6a,0x85,0xef,0x99,0xc4,0xf0};
  memcpy(header + 0x40, idBytes, sizeof idBytes);
  CHECK([[NSData dataWithBytes:header length:sizeof header] writeToFile:child(root,@"exefs/main") atomically:YES]);
  NSString *id1 = [@"a" stringByPaddingToLength:64 withString:@"a" startingAtIndex:0];
  NSString *id2 = [@"b" stringByPaddingToLength:64 withString:@"b" startingAtIndex:0];
  put(dir,@"pack/.applied",id1);
  put(dir,@"pack/manifest.json",[NSString stringWithFormat:@"{\"index_sha256\":\"%@\"}",id1]);
  CHECK(![S2ArmGraphicsGeneration startupPlanInLibrary:library chain:chain]);
  put(dir,@"prepared.json",[NSString stringWithFormat:@"{\"result\":{\"success\":true,\"gid\":\"%@\"}}",gid]);
  S2ArmGraphicsGeneration *startup = [S2ArmGraphicsGeneration startupPlanInLibrary:library chain:chain];
  CHECK(startup && ![startup stage:^BOOL { return YES; } progress:^(NSUInteger n){ (void)n; } error:NULL]);
  S2ArmGraphicsGeneration *resumeStartup = [S2ArmGraphicsGeneration startupPlanInLibrary:library chain:chain];
  CHECK([resumeStartup.wire isEqual:startup.wire] && stage(resumeStartup));
  CHECK(![S2ArmGraphicsGeneration startupPlanInLibrary:library chain:chain]);
  S2ArmGraphicsGeneration *pack1 = [S2ArmGraphicsGeneration planForGame:gid directory:dir root:root chain:chain reused:YES error:NULL];
  CHECK(!pack1.active && [pack1.wire isEqual:startup.wire] && stage(pack1));
  put(dir,@"pack/.applied",id2);
  CHECK(![S2ArmGraphicsGeneration planForGame:gid directory:dir root:root chain:chain reused:YES error:NULL]);
  put(dir,@"pack/manifest.json",[NSString stringWithFormat:@"{\"index_sha256\":\"%@\"}",id2]);
  S2ArmGraphicsGeneration *pack2 = [S2ArmGraphicsGeneration planForGame:gid directory:dir root:root chain:chain reused:YES error:NULL];
  CHECK(pack2 && ![pack1.wire isEqual:pack2.wire]);
  // Reconstructing the original pack reopens its existing pending slot.
  put(dir,@"pack/.applied",id1);
  put(dir,@"pack/manifest.json",[NSString stringWithFormat:@"{\"index_sha256\":\"%@\"}",id1]);
  S2ArmGraphicsGeneration *pack1Again = [S2ArmGraphicsGeneration planForGame:gid directory:dir root:root chain:chain reused:YES error:NULL];
  CHECK([pack1Again.wire isEqual:pack1.wire]);
  CHECK([S2ArmGraphicsGeneration planForGame:@"0100000000000000" directory:dir root:root chain:chain reused:YES error:NULL] == nil);
  header[0x40] ^= 1;
  CHECK([[NSData dataWithBytes:header length:sizeof header] writeToFile:child(root,@"exefs/main") atomically:YES]);
  CHECK([S2ArmGraphicsGeneration planForGame:gid directory:dir root:root chain:chain reused:YES error:NULL] == nil);
  put(dir, @"prepared.json", @"794 CPU preparation");
  put(dir, @"save/profile", @"save"); put(dir, @"defaults", @"settings");
  put(legacy, @"shaders/0123456789abcdef_b.metal", @"source");
  put(legacy, @"shaders/0123456789abcdef_b.json", @"reflection");
  put(legacy, @"pso_user.tsv", @"prior game rows");
  NSString *batch = @"batch-31-42.metalarchive";
  NSString *rows = [NSString stringWithFormat:@"%@\t%@\n", key, batch];
  put(legacy, @"pipelines/identity.json", @"{\"schema\":1,\"gpu\":\"same-device\",\"chain\":\"0be3f28548fd\",\"osBuild\":\"same-os\"}");
  put(legacy, child(@"pipelines",batch), @"archive fixture");
  put(legacy, @"pipelines/batches.tsv", rows);
  S2ArmGraphicsGeneration *first = plan(dir);
  CHECK(!first.active && ![first.wire isEqual:legacy]);
  __block NSUInteger checks = 0;
  CHECK(![first stage:^BOOL { return ++checks >= 4; } progress:^(NSUInteger n) { (void)n; } error:NULL]);
  CHECK(readText(dir, marker) == nil && [readText(dir,@"prepared.json") isEqual:@"794 CPU preparation"]);
  S2ArmGraphicsGeneration *resumed = plan(dir);
  CHECK([first.wire isEqual:resumed.wire] && stage(resumed));
  CHECK([readText(resumed.wire,@"pso_user.tsv") isEqual:@"prior game rows"]);
  put(resumed.wire, @"shaders/0123456789abcdef_b.metal", @"new translation");
  CHECK(stage(plan(dir)) && [readText(resumed.wire,@"shaders/0123456789abcdef_b.metal") isEqual:@"new translation"]);
  put(resumed.wire, @"pso_external.tsv", @"# resolved external recipes\n");
  put(resumed.wire, @"pso_reference.tsv", @"S\t0123456789abcdef_b\t0\n");
  const uint64_t partial[] = {1,1,1,1,0,12}, valid[] = {1,1,1,1,1,12};
  CHECK(![resumed activateWithGPU:partial error:NULL] && ![resumed activateWithGPU:valid error:NULL]);
  CHECK(!readText(dir, marker));
  put(resumed.wire, @"pso_reference.archives.tsv", rows);
  CHECK([resumed activateWithGPU:valid error:NULL]);
  NSString *receipt = readText(dir, marker);
  S2ArmGraphicsGeneration *nextLaunch = plan(dir);
  CHECK(nextLaunch.active && [nextLaunch.wire isEqual:resumed.wire]);
  put(nextLaunch.wire, @"pipelines/batches.tsv", [rows stringByAppendingString:@"unrelated-row\n"]);
  CHECK(plan(dir).active);
  // Deleting the indexed membership cannot silently turn the strict archive
  // proof into metadata. The replacement must have its own directory.
  put(nextLaunch.wire, @"pipelines/batches.tsv", @"broken row\n");
  S2ArmGraphicsGeneration *replacement = plan(dir);
  CHECK(!replacement.active && ![replacement.wire isEqual:resumed.wire]);
  CHECK(stage(replacement) && ![replacement activateWithGPU:valid error:NULL]);
  CHECK([readText(dir, marker) isEqual:receipt] && [plan(dir).wire isEqual:replacement.wire]);
  put(replacement.wire, @"pso_external.tsv", @"# resolved external recipes\n");
  put(replacement.wire, @"pso_reference.tsv", @"S\t0123456789abcdef_b\t0\n");
  put(replacement.wire, @"pso_reference.archives.tsv", rows);
  put(replacement.wire, @"pipelines/batches.tsv", rows);
  CHECK([replacement activateWithGPU:valid error:NULL] && plan(dir).active);
  // Engine patches 0286 and 0301: a hosted title's archives live in a scoped
  // directory, which the manifest of the strict proof names. The proof binds
  // those files, not the read-only copies left in pipelines/.
  NSString *scoped = @"pipelines-v2/0123456789abcdef0123456789abcdef01234567";
  put(replacement.wire, @"pso_reference.archives.tsv", [@"D\t../pipelines\n" stringByAppendingString:rows]);
  CHECK(![replacement activateWithGPU:valid error:NULL]);
  put(replacement.wire, @"pso_reference.archives.tsv", [NSString stringWithFormat:@"D\t%@\n%@", scoped, rows]);
  CHECK(![replacement activateWithGPU:valid error:NULL]);
  put(replacement.wire, child(scoped,@"identity.json"),
      @"{\"schema\":2,\"gpu\":\"same-device\",\"chain\":\"0be3f28548fd\",\"osBuild\":\"same-os\",\"title\":\"0400c3f00006e000\"}");
  put(replacement.wire, child(scoped,batch), @"scoped archive fixture");
  put(replacement.wire, child(scoped,@"batches.tsv"), rows);
  CHECK([replacement activateWithGPU:valid error:NULL] && plan(dir).active);
  put(replacement.wire, child(@"pipelines",batch), @"an unrelated legacy copy");
  CHECK(plan(dir).active);
  put(replacement.wire, child(scoped,batch), @"damaged scoped archive");
  CHECK(!plan(dir).active);
  put(replacement.wire, child(scoped,batch), @"scoped archive fixture");
  put(replacement.wire, child(@"pipelines",batch), @"archive fixture");
  put(replacement.wire, @"pso_reference.archives.tsv", rows);
  CHECK([replacement activateWithGPU:valid error:NULL] && plan(dir).active);
  put(replacement.wire, child(@"pipelines",batch), @"damaged archive");
  CHECK(!plan(dir).active);
  put(replacement.wire, child(@"pipelines",batch), @"archive fixture");
  put(replacement.wire, @"shaders/0123456789abcdef_b.metal", @"damaged source");
  CHECK(!plan(dir).active);
  // A shader translator fingerprint change opens a new graphics generation on
  // Launch 1 while cloning learned inputs from the previous active generation.
  put(replacement.wire, @"shaders/0123456789abcdef_b.metal", @"new translation");
  CHECK(plan(dir).active);
  S2ArmGraphicsGeneration *xfp1 = [[S2ArmGraphicsGeneration alloc] initWithDirectory:dir gid:gid buildID:build content:@"same-content"
      chain:chain hardware:@"same-device" osBuild:@"same-os" shaderXfp:@"0123456789abcdef" reuseLegacy:YES];
  CHECK(!xfp1.active && ![xfp1.wire isEqual:replacement.wire] && stage(xfp1));
  CHECK([readText(xfp1.wire, @"pso_user.tsv") isEqual:@"prior game rows"]);
  put(xfp1.wire, @"pso_external.tsv", @"# resolved external recipes\n");
  put(xfp1.wire, @"pso_reference.tsv", @"S\t0123456789abcdef_b\t0\n");
  put(xfp1.wire, @"pso_reference.archives.tsv", rows);
  put(xfp1.wire, @"pipelines/batches.tsv", rows);
  CHECK([xfp1 activateWithGPU:valid error:NULL]);
  S2ArmGraphicsGeneration *xfp1Reuse = [[S2ArmGraphicsGeneration alloc] initWithDirectory:dir gid:gid buildID:build content:@"same-content"
      chain:chain hardware:@"same-device" osBuild:@"same-os" shaderXfp:@"0123456789abcdef" reuseLegacy:YES];
  CHECK(xfp1Reuse.active && [xfp1Reuse.wire isEqual:xfp1.wire]);
  S2ArmGraphicsGeneration *xfp2 = [[S2ArmGraphicsGeneration alloc] initWithDirectory:dir gid:gid buildID:build content:@"same-content"
      chain:chain hardware:@"same-device" osBuild:@"same-os" shaderXfp:@"fedcba9876543210" reuseLegacy:YES];
  CHECK(!xfp2.active && ![xfp2.wire isEqual:xfp1.wire] && stage(xfp2));
  // Restore replacement as active so the diagnostics check below remains unchanged.
  CHECK([replacement activateWithGPU:valid error:NULL]);
  NSString *diagnostics = child(child(dir,@"Diagnostics"),gid), *session = NSUUID.UUID.UUIDString;
  NSString *out = child(child(diagnostics,@"preparation"),session);
  put(replacement.wire,@"stage-recovery.tsv",@"stage\tcurrent\n");
  NSDictionary *scan = @{@"spooled":@3, @"unavailableDictionary":@1, @"corrupt":@2, @"resourceLimits":@4,
    @"ioErrors":@0, @"unlocatedRequestedKeys":@7, @"unexpectedPath":@"/never-export-this"};
  NSData *binary = [NSPropertyListSerialization dataWithPropertyList:scan format:NSPropertyListBinaryFormat_v1_0 options:0 error:NULL];
  CHECK([binary writeToFile:child(replacement.wire,@"stage-scan-coverage.plist") atomically:YES]);
  CHECK([replacement writeEvidenceToDirectory:diagnostics session:session phase:@"starting"]);
  CHECK(!readText(out,@"pso_reference.tsv"));
  CHECK([replacement writeEvidenceToDirectory:diagnostics session:session phase:@"inputs"]);
  CHECK([readText(out,@"stage-recovery.tsv") isEqual:@"stage\tcurrent\n"]);
  CHECK(!readText(out,@"pso_reference.archives.tsv"));
  CHECK([replacement writeEvidenceToDirectory:diagnostics session:session phase:@"verified"]);
  NSDictionary *proof = [NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:child(out,@"identity.json")] options:0 error:NULL];
  CHECK([proof[@"session"] isEqual:session] && [proof[@"generation"] isEqual:replacement.wire.lastPathComponent] &&
        [proof[@"gid"] isEqual:gid] && [proof[@"gameBuild"] isEqual:build] && [proof[@"files"] count] == 4);
  NSData *coverageData = [NSData dataWithContentsOfFile:child(out,@"stage-scan-coverage.plist")];
  NSDictionary *coverage = [NSPropertyListSerialization propertyListWithData:coverageData options:0 format:NULL error:NULL];
  CHECK(coverage.count == 6 && [coverage[@"unlocatedRequestedKeys"] isEqual:@7] && !coverage[@"unexpectedPath"]);
  CHECK(![first writeEvidenceToDirectory:diagnostics session:session phase:@"reused"]);
  CHECK(![replacement writeEvidenceToDirectory:child(dir,@"different-game") session:session phase:@"reused"]);
  CHECK(![NSFileManager.defaultManager fileExistsAtPath:child(out,child(@"shaders",@"0123456789abcdef_b.metal"))]);
  NSString *secondSession = NSUUID.UUID.UUIDString;
  put(replacement.wire,@"stage-recovery.tsv",[@"x" stringByPaddingToLength:4*1024*1024+1 withString:@"x" startingAtIndex:0]);
  CHECK([replacement writeEvidenceToDirectory:diagnostics session:secondSession phase:@"resumed"]);
  NSString *second = child(child(diagnostics,@"preparation"),secondSession);
  CHECK(!readText(second,@"stage-recovery.tsv") && !readText(second,@"pso_reference.archives.tsv"));
  CHECK([readText(out,@"stage-recovery.tsv") isEqual:@"stage\tcurrent\n"]);
  CHECK([readText(legacy,@"shaders/0123456789abcdef_b.metal") isEqual:@"source"]);
  CHECK([readText(dir,@"save/profile") isEqual:@"save"] && [readText(dir,@"defaults") isEqual:@"settings"]);
  CHECK([NSFileManager.defaultManager removeItemAtPath:library error:NULL]);
  puts("PASS legacy 794, interrupted copy, translation checkpoint, strict receipt, hot reuse, damaged index/archive/source and repair isolation");
  return 0;
} }

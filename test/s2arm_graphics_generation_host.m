// Host-side transaction test. The engine's separate Metal tests supply real GPU
// verification. Counts below exercise only the host's acceptance of that proof.
#import "S2ArmGraphicsGeneration.h"
#import <stdio.h>
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
  NSString *dir = child(NSTemporaryDirectory(), NSUUID.UUID.UUIDString);
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
  CHECK([S2ArmGraphicsGeneration planForGame:gid directory:dir root:root chain:chain reused:YES error:NULL] != nil);
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
  put(resumed.wire, @"pso_reference.tsv", @"S\t0123456789abcdef_b\t0\n");
  const uint64_t partial[] = {1,1,1,1,0,0}, valid[] = {1,1,1,1,1,0};
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
  put(replacement.wire, @"pso_reference.tsv", @"S\t0123456789abcdef_b\t0\n");
  put(replacement.wire, @"pso_reference.archives.tsv", rows);
  put(replacement.wire, @"pipelines/batches.tsv", rows);
  CHECK([replacement activateWithGPU:valid error:NULL] && plan(dir).active);
  put(replacement.wire, child(@"pipelines",batch), @"damaged archive");
  CHECK(!plan(dir).active);
  put(replacement.wire, child(@"pipelines",batch), @"archive fixture");
  put(replacement.wire, @"shaders/0123456789abcdef_b.metal", @"damaged source");
  CHECK(!plan(dir).active);
  CHECK([readText(legacy,@"shaders/0123456789abcdef_b.metal") isEqual:@"source"]);
  CHECK([readText(dir,@"save/profile") isEqual:@"save"] && [readText(dir,@"defaults") isEqual:@"settings"]);
  CHECK([NSFileManager.defaultManager removeItemAtPath:dir error:NULL]);
  puts("PASS legacy 794, interrupted copy, translation checkpoint, strict receipt, hot reuse, damaged index/archive/source and repair isolation");
  return 0;
} }

// SPDX-License-Identifier: GPL-3.0-or-later
// Controlled HTTP/resolver fixtures around the actual production Store.
#import <Foundation/Foundation.h>
#import "NeoTextureCatalog.h"
#import "NeoTextureEngine.h"
#import "NeoTexturePackStore.h"
#import "NeoTextureSupport.h"
#include <cstdio>

static int checks = 0, failures = 0;
#define CHECK(c, ...) do { checks++; if (!(c)) { failures++; fprintf(stderr, "FAIL line %d: ", __LINE__); fprintf(stderr, __VA_ARGS__); fprintf(stderr, "\n"); } } while (0)
static NSFileManager *FM(void) { return NSFileManager.defaultManager; }
static BOOL Exists(NSString *p) { return [FM() fileExistsAtPath:p]; }
static void PumpUntil(BOOL (^done)(void)) {
  NSDate *limit = [NSDate dateWithTimeIntervalSinceNow:15];
  while (!done() && limit.timeIntervalSinceNow > 0)
    [NSRunLoop.mainRunLoop runMode:NSDefaultRunLoopMode beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.01]];
  CHECK(done(), "native operation timed out");
}
static NSData *Hex(NSString *text) {
  NSMutableData *bytes = [NSMutableData data];
  for (NSUInteger i = 0; i + 1 < text.length; i += 2) {
    unsigned value = 0; sscanf([text substringWithRange:NSMakeRange(i, 2)].UTF8String, "%2x", &value);
    unsigned char byte = (unsigned char)value; [bytes appendBytes:&byte length:1];
  }
  return bytes;
}

static NSData *Body;
static NSString *Mode;
static NSMutableArray<NSURLRequest *> *Requests;
@interface FixtureProtocol : NSURLProtocol
@end
@implementation FixtureProtocol
+ (BOOL)canInitWithRequest:(NSURLRequest *)request { return [request.URL.host isEqual:@"fixture.invalid"]; }
+ (NSURLRequest *)canonicalRequestForRequest:(NSURLRequest *)request { return request; }
- (void)startLoading {
  @synchronized(FixtureProtocol.class) { [Requests addObject:self.request]; }
  NSString *mode = Mode;
  NSData *body = Body;
  NSString *range = [self.request valueForHTTPHeaderField:@"Range"];
  unsigned long long offset = 0;
  if (range.length) sscanf(range.UTF8String, "bytes=%llu-", &offset);
  BOOL suffix = range.length && ![mode isEqual:@"ignore-range"];
  NSInteger status = [mode isEqual:@"forbidden"] ? 403 : (suffix ? 206 : 200);
  NSMutableDictionary *headers = [@{@"Content-Type": [mode isEqual:@"html"] ? @"text/html" : @"application/octet-stream"} mutableCopy];
  if (suffix) {
    unsigned long long start = [mode isEqual:@"bad-range"] ? offset + 1 : offset;
    headers[@"Content-Range"] = [NSString stringWithFormat:@"bytes %llu-%lu/%lu", start, (unsigned long)body.length - 1, (unsigned long)body.length];
    body = [body subdataWithRange:NSMakeRange((NSUInteger)offset, body.length - (NSUInteger)offset)];
  }
  if ([mode isEqual:@"oversize"]) {
    NSMutableData *large = [body mutableCopy]; [large appendBytes:"!" length:1]; body = large;
    // Deliberately omit Content-Length to exercise the streaming byte bound.
  } else headers[@"Content-Length"] = @(body.length).stringValue;
  NSHTTPURLResponse *response = [[NSHTTPURLResponse alloc] initWithURL:self.request.URL statusCode:status HTTPVersion:@"HTTP/1.1" headerFields:headers];
  [self.client URLProtocol:self didReceiveResponse:response cacheStoragePolicy:NSURLCacheStorageNotAllowed];
  if ([mode isEqual:@"hold"] || [mode isEqual:@"network-cut"]) {
    [self.client URLProtocol:self didLoadData:[body subdataWithRange:NSMakeRange(0, MIN(NSUInteger(1024), body.length))]];
    if ([mode isEqual:@"network-cut"]) [self.client URLProtocol:self didFailWithError:
        [NSError errorWithDomain:NSURLErrorDomain code:NSURLErrorNetworkConnectionLost userInfo:nil]];
    return;
  }
  for (NSUInteger at = 0; at < body.length; at += 257)
    [self.client URLProtocol:self didLoadData:[body subdataWithRange:NSMakeRange(at, MIN(NSUInteger(257), body.length - at))]];
  [self.client URLProtocolDidFinishLoading:self];
}
- (void)stopLoading {}
@end

@interface FixtureResolution : NSObject
@property(nonatomic) BOOL cancelled;
- (void)cancel;
@end
@implementation FixtureResolution
- (void)cancel { self.cancelled = YES; }
@end

@interface FixtureStore : NeoTexturePackStore
@property(nonatomic, strong) NSURLSession *fixtureSession;
@property(nonatomic, strong) NSDictionary *crypto;
@property(nonatomic) NSUInteger resolutions;
@property(nonatomic) BOOL holdResolution;
@property(nonatomic, strong) FixtureResolution *resolution;
@property(nonatomic, copy) dispatch_block_t pendingResolution;
- (NSURLSession *)session;
@end
@implementation FixtureStore
- (NSURLSession *)session {
  if (!self.fixtureSession) {
    NSURLSessionConfiguration *config = NSURLSessionConfiguration.ephemeralSessionConfiguration;
    config.protocolClasses = @[FixtureProtocol.class];
    config.URLCache = nil; config.HTTPCookieStorage = nil; config.URLCredentialStorage = nil; config.HTTPShouldSetCookies = NO;
    NSOperationQueue *queue = [NSOperationQueue new]; queue.maxConcurrentOperationCount = 1;
    self.fixtureSession = [NSURLSession sessionWithConfiguration:config delegate:(id<NSURLSessionDelegate>)self delegateQueue:queue];
  }
  return self.fixtureSession;
}
- (id)resolvePart:(NSDictionary *)part completion:(void (^)(NSURL *, NSDictionary *, NSError *))completion {
  self.resolutions++;
  self.resolution = [FixtureResolution new];
  NSDictionary *crypto = [part[@"provider"] isEqual:@"mega"] ? self.crypto : nil;
  dispatch_block_t done = ^{ completion([NSURL URLWithString:@"https://fixture.invalid/file?signed-secret-do-not-persist"], crypto, nil); };
  if (self.holdResolution) self.pendingResolution = done;
  else dispatch_async(dispatch_get_global_queue(QOS_CLASS_DEFAULT, 0), done);
  return self.resolution;
}
@end

struct Outcome { NSDictionary *result; NSError *error; };
static Outcome Install(NeoTexturePackStore *store, NSDictionary *pack, id<NeoTextureEngine> engine, NSDictionary *identity) {
  __block Outcome result{}; __block BOOL done = NO;
  [store installPack:pack engine:engine identity:identity replace:YES confirmed:NO completion:^(NSDictionary *outcome, NSError *error) {
    result = {outcome, error}; done = YES;
  }];
  PumpUntil(^BOOL { return done; });
  return result;
}
static Outcome Import(NeoTexturePackStore *store, NSString *path, id<NeoTextureEngine> engine, NSDictionary *identity, BOOL confirmed) {
  __block Outcome result{}; __block BOOL done = NO;
  [store importURL:[NSURL fileURLWithPath:path] engine:engine identity:identity allowOtherRegion:confirmed replace:YES
      completion:^(NSDictionary *outcome, NSError *error) { result = {outcome, error}; done = YES; }];
  PumpUntil(^BOOL { return done; });
  return result;
}
static NSDictionary *Pack(NSString *provider, NSDictionary *metadata, BOOL wrongSHA) {
  NSString *url = [provider isEqual:@"mega"] ? @"https://mega.nz/file/AbCd1234#AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
      : [provider isEqual:@"gdrive"] ? @"https://drive.google.com/file/d/fixtureFile123456/view" : @"https://disk.yandex.ru/d/fixture123";
  NSString *sha = wrongSHA ? [@"" stringByPaddingToLength:64 withString:@"0" startingAtIndex:0] : metadata[@"sha256"];
  return @{@"id": @"fixture-provider", @"system": @"gc", @"engine": @"dolphin", @"title": @"Synthetic textures", @"version": @"1",
      @"availability": @"available", @"games": @[@{@"title": @"Synthetic game", @"identities": @[@{@"type": @"game_id", @"scheme": @"dolphin-disc-game-id", @"value": @"GALE01"}]}],
      @"download": @{@"automatable": @YES, @"format": @"zip", @"size": metadata[@"size"], @"sha256": sha,
          @"parts": @[@{@"provider": provider, @"url": url, @"size": metadata[@"size"], @"sha256": sha}]},
      @"install": @{@"files": @1, @"bytes": @20000, @"folders": @[@{@"from": @"GALE01/", @"to": @"GALE01"}]}};
}
static NSString *Partial(FixtureStore *store, NSDictionary *pack) {
  NSString *name = [NSString stringWithFormat:@"%@@%@/part-0.%@.partial", pack[@"id"], [pack[@"download"][@"sha256"] substringToIndex:12],
      [pack[@"download"][@"parts"][0][@"provider"] isEqual:@"mega"] ? @"cipher" : @"host"];
  return [store.downloadDirectory stringByAppendingPathComponent:name];
}
static void NoSecrets(NSString *folder) {
  for (NSString *name in [FM() enumeratorAtPath:folder]) {
    CHECK(![name hasSuffix:@".resume"] && ![name hasSuffix:@".decrypting"], "unsafe persisted state: %s", name.UTF8String);
    NSData *data = [NSData dataWithContentsOfFile:[folder stringByAppendingPathComponent:name]];
    NSData *needle = [@"signed-secret-do-not-persist" dataUsingEncoding:NSUTF8StringEncoding];
    CHECK(!data || [data rangeOfData:needle options:0 range:NSMakeRange(0, data.length)].location == NSNotFound, "signed URL persisted");
  }
}
static void NoStaging(id<NeoTextureEngine> engine) {
  for (NSString *name in [FM() contentsOfDirectoryAtPath:engine.texturesRoot error:nil])
    CHECK(![name hasPrefix:@".neostation-"], "expansion/staging left behind: %s", name.UTF8String);
}

int main(int argc, char **argv) {
  @autoreleasepool {
    if (argc != 3) return 64;
    NSString *fixture = [@(argv[1]) stringByDeletingLastPathComponent], *work = @(argv[2]);
    NSDictionary *metadata = [NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:@(argv[1])] options:0 error:nil];
    CHECK(metadata != nil, "fixture metadata missing");
    NSData *plain = [NSData dataWithContentsOfFile:[fixture stringByAppendingPathComponent:@"plain.zip"]];
    NSData *cipher = [NSData dataWithContentsOfFile:[fixture stringByAppendingPathComponent:@"cipher.bin"]];
    NSData *image = [NSData dataWithContentsOfFile:[fixture stringByAppendingPathComponent:@"texture.png"]];
    NSDictionary *identity = @{@"system": @"gc", @"identities": @[@{@"type": @"game_id", @"scheme": @"dolphin-disc-game-id", @"value": @"GALE01"}]};
    NeoTexSetRegistryPath([work stringByAppendingPathComponent:@"registry.json"]);
    NSArray *cases = @[@[@"gdrive", @"ok"], @[@"yandex", @"ok"], @[@"mega", @"ok"], @[@"mega", @"range"],
        @[@"mega", @"ignore-range"], @[@"mega", @"bad-range"], @[@"mega", @"wrong-sha"], @[@"gdrive", @"html"],
        @[@"gdrive", @"oversize"], @[@"gdrive", @"forbidden"]];
    NSUInteger index = 0;
    for (NSArray *scenario in cases) {
      NSString *provider = scenario[0], *mode = scenario[1];
      NSString *base = [work stringByAppendingPathComponent:[NSString stringWithFormat:@"case-%lu", (unsigned long)index++]];
      id<NeoTextureEngine> engine = [NeoTextureEngines dolphinWithUserDirectory:[base stringByAppendingPathComponent:@"dolphin"]];
      NSString *installed = [engine.texturesRoot stringByAppendingPathComponent:@"GALE01/tex1_fixture.png"];
      [FM() createDirectoryAtPath:installed.stringByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:nil];
      NSData *sentinel = [@"previous installed textures" dataUsingEncoding:NSUTF8StringEncoding]; [sentinel writeToFile:installed atomically:YES];
      FixtureStore *store = [FixtureStore new]; store.downloadDirectory = [base stringByAppendingPathComponent:@"downloads"];
      store.crypto = @{@"key": Hex(metadata[@"key"]), @"iv": Hex(metadata[@"iv"]), @"size": metadata[@"size"]};
      store.freeSpace = ^unsigned long long(NSString *) { return 100ULL << 30; };
      NSDictionary *pack = Pack(provider, metadata, [mode isEqual:@"wrong-sha"]);
      Body = [provider isEqual:@"mega"] ? cipher : plain; Mode = mode; Requests = [NSMutableArray array];
      BOOL resume = [@[@"range", @"ignore-range", @"bad-range"] containsObject:mode];
      if (resume) {
        NSString *partial = Partial(store, pack);
        [FM() createDirectoryAtPath:partial.stringByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:nil];
        [[Body subdataWithRange:NSMakeRange(0, 513)] writeToFile:partial atomically:YES];
      }
      Outcome result = Install(store, pack, engine, identity);
      BOOL expected = [@[@"ok", @"range", @"ignore-range"] containsObject:mode];
      CHECK(expected ? result.error == nil : result.error != nil, "%s/%s: %s", provider.UTF8String, mode.UTF8String, result.error.description.UTF8String);
      CHECK([[NSData dataWithContentsOfFile:installed] isEqualToData:expected ? image : sentinel], "%s changed installed bytes before validation", mode.UTF8String);
      CHECK(store.resolutions == 1 && Requests.count == 1, "unexpected retry/resolution count");
      CHECK([[Requests.firstObject valueForHTTPHeaderField:@"User-Agent"] isEqual:@"NeoStation-iOS"], "native User-Agent missing");
      CHECK(!resume || [[Requests.firstObject valueForHTTPHeaderField:@"Range"] isEqual:@"bytes=513-"], "resume interval incorrect");
      if ([mode isEqual:@"forbidden"]) CHECK([result.error.userInfo[@"status"] integerValue] == 403, "HTTP refusal not preserved");
      if ([mode isEqual:@"bad-range"] || [mode isEqual:@"wrong-sha"]) CHECK(!Exists(Partial(store, pack)), "unusable partial retained");
      NoSecrets(store.downloadDirectory); NoStaging(engine);
      [store.fixtureSession invalidateAndCancel];
    }

    // A real pause keeps ciphertext bytes only; the next attempt resolves afresh
    // and sends a Range matching precisely those bytes.
    FixtureStore *store = [FixtureStore new]; store.downloadDirectory = [work stringByAppendingPathComponent:@"pause/downloads"];
    store.crypto = @{@"key": Hex(metadata[@"key"]), @"iv": Hex(metadata[@"iv"]), @"size": metadata[@"size"]};
    store.freeSpace = ^unsigned long long(NSString *) { return 100ULL << 30; };
    id<NeoTextureEngine> engine = [NeoTextureEngines dolphinWithUserDirectory:[work stringByAppendingPathComponent:@"pause/dolphin"]];
    NSDictionary *pack = Pack(@"mega", metadata, NO);
    Body = cipher; Mode = @"hold"; Requests = [NSMutableArray array];
    __block BOOL finished = NO; __block NSError *pausedError = nil;
    [store installPack:pack engine:engine identity:identity replace:YES completion:^(NSDictionary *result, NSError *error) { pausedError = error; finished = YES; }];
    PumpUntil(^BOOL { return [[store jobForPack:pack[@"id"]][@"received"] unsignedLongLongValue] > 0; });
    [store pausePack:pack[@"id"]]; PumpUntil(^BOOL { return finished; });
    CHECK(pausedError.code == NeoTexturePackErrorCancelled, "pause did not cancel transfer");
    NSData *partial = [NSData dataWithContentsOfFile:Partial(store, pack)];
    CHECK(partial.length > 0 && partial.length < cipher.length && [partial isEqualToData:[cipher subdataWithRange:NSMakeRange(0, partial.length)]], "pause persisted nonciphertext bytes");
    CHECK(!Exists([engine.texturesRoot stringByAppendingPathComponent:@"GALE01"]), "pause touched installation"); NoSecrets(store.downloadDirectory);
    Mode = @"ok"; Outcome resumed = Install(store, pack, engine, identity);
    CHECK(!resumed.error && store.resolutions == 2 && Requests.count == 2, "pause/resume did not resolve afresh: %s", resumed.error.description.UTF8String);
    CHECK([[Requests.lastObject valueForHTTPHeaderField:@"Range"] isEqual:[NSString stringWithFormat:@"bytes=%lu-", (unsigned long)partial.length]], "resume did not use ciphertext length");
    [store.fixtureSession invalidateAndCancel];

    // Cancellation racing the final metadata callback must start no transfer.
    store = [FixtureStore new]; store.downloadDirectory = [work stringByAppendingPathComponent:@"cancel/downloads"];
    store.freeSpace = ^unsigned long long(NSString *) { return 100ULL << 30; }; store.holdResolution = YES;
    engine = [NeoTextureEngines dolphinWithUserDirectory:[work stringByAppendingPathComponent:@"cancel/dolphin"]];
    pack = Pack(@"gdrive", metadata, NO); Requests = [NSMutableArray array]; finished = NO;
    [store installPack:pack engine:engine identity:identity replace:YES completion:^(NSDictionary *result, NSError *error) { finished = YES; }];
    PumpUntil(^BOOL { return store.pendingResolution != nil; });
    [store cancelPack:pack[@"id"]]; PumpUntil(^BOOL { return store.resolution.cancelled; });
    store.pendingResolution(); store.pendingResolution = nil; PumpUntil(^BOOL { return finished; });
    CHECK(!Requests.count && !Exists([engine.texturesRoot stringByAppendingPathComponent:@"GALE01"]), "late resolution started transfer");
    PumpUntil(^BOOL { return [[store jobForPack:pack[@"id"]][@"state"] isEqual:@"idle"]; });
    CHECK(![FM() contentsOfDirectoryAtPath:store.downloadDirectory error:nil].count, "cancelled cache resurrected");

    // Both ordinary import paths use the shared RAR decoder. ARMSX2 still asks
    // before another serial and keeps its previous pack on damaged input.
    NeoTexturePackStore *imports = [NeoTexturePackStore new]; imports.freeSpace = ^unsigned long long(NSString *) { return 100ULL << 30; };
    engine = [NeoTextureEngines dolphinWithUserDirectory:[work stringByAppendingPathComponent:@"rar/dolphin"]];
    Outcome imported = Import(imports, [fixture stringByAppendingPathComponent:@"dolphin.rar"], engine, identity, NO);
    CHECK(!imported.error && [[NSData dataWithContentsOfFile:[engine.texturesRoot stringByAppendingPathComponent:@"GALE01/tex1_fixture.png"]] isEqualToData:image], "generic RAR import: %s", imported.error.description.UTF8String);
    CHECK(!Exists([engine.texturesRoot stringByAppendingPathComponent:@"GALE01/installer.exe"]), "executable imported"); NoStaging(engine);
    id<NeoTextureEngine> ps2 = [NeoTextureEngines armsx2WithDataDirectory:[work stringByAppendingPathComponent:@"rar/ps2"] gamePath:nil host:nil];
    NSDictionary *ps2Identity = @{@"system": @"ps2", @"identities": @[@{@"type": @"serial", @"scheme": @"ps2-disc-serial", @"value": @"SLUS-21137"}]};
    CHECK([ps2 installsPacks], "actual ARMSX2 installer not linked");
    imported = Import(imports, [fixture stringByAppendingPathComponent:@"ps2.rar"], ps2, ps2Identity, NO);
    NSString *ps2Image = [ps2.texturesRoot stringByAppendingPathComponent:@"SLUS-21137/replacements/ui/0123456789abcdef-00004a2d.png"];
    CHECK(!imported.error && [[NSData dataWithContentsOfFile:ps2Image] isEqualToData:image], "ARMSX2 RAR import: %s", imported.error.description.UTF8String); NoStaging(ps2);
    imported = Import(imports, [fixture stringByAppendingPathComponent:@"wrong-region.rar"], ps2, ps2Identity, NO);
    CHECK(imported.error.code == NeoTexturePackErrorRegion && [[NSData dataWithContentsOfFile:ps2Image] isEqualToData:image], "RAR serial confirmation bypassed"); NoStaging(ps2);
    imported = Import(imports, [fixture stringByAppendingPathComponent:@"damaged.rar"], ps2, ps2Identity, YES);
    CHECK(imported.error != nil && [[NSData dataWithContentsOfFile:ps2Image] isEqualToData:image], "damaged RAR changed previous pack"); NoStaging(ps2);
    printf("%s Store provider integration: %d checks, %d failures\n", failures ? "FAIL" : "PASS", checks, failures);
    return failures ? 1 : 0;
  }
}

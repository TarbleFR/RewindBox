// SPDX-License-Identifier: GPL-3.0-or-later
// Deterministic public-protocol fixtures. Actual production CommonCrypto code
// is compiled unchanged; HTTP responses are injected, not external transfers.
#import <Foundation/Foundation.h>
#import "NeoTextureMega.h"
#import "NeoTexturePackStore.h"
#include <atomic>
#include <cstdio>
#include <memory>
#include <unistd.h>

static int checks = 0, failures = 0;
#define CHECK(value, label) do { checks++; if (!(value)) { failures++; fprintf(stderr, "FAIL: %s\n", label); } } while (0)

@interface MegaFixtureTask : NSObject
@property(nonatomic, copy) dispatch_block_t run;
@property(atomic) BOOL cancelled;
@property(nonatomic, strong) id delegate;
@property(nonatomic, strong) NSURLResponse *response;
- (void)resume;
- (void)cancel;
@end
@implementation MegaFixtureTask
- (void)resume { dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), self.run); }
- (void)cancel { self.cancelled = YES; }
@end

// Only downloadTaskWithRequest:completionHandler: is used by the production
// resolver. A mock with that selector makes the API fixtures independent of
// platform NSURLProtocol support for download tasks.
@interface MegaFixtureSession : NSObject
@property(nonatomic, strong) NSArray *answers;
@property(nonatomic, strong) NSMutableArray *requests;
@property(nonatomic) NSInteger status;
@property(nonatomic, copy) NSString *responseURL;
@property(nonatomic) long long expectedLength;
@property(nonatomic) long long reportedBytes;
@property(nonatomic, copy) NSString *contentType;
- (NSURLSessionDownloadTask *)downloadTaskWithRequest:(NSURLRequest *)request
    completionHandler:(void (^)(NSURL *, NSURLResponse *, NSError *))completion;
@end
@implementation MegaFixtureSession
- (instancetype)init {
  if ((self = [super init])) { _requests = [NSMutableArray array]; _status = 200; _responseURL = @"https://g.api.mega.co.nz/cs";
    _expectedLength = -1; _reportedBytes = 1; _contentType = @"application/json"; }
  return self;
}
- (NSURLSessionDownloadTask *)downloadTaskWithRequest:(NSURLRequest *)request
    completionHandler:(void (^)(NSURL *, NSURLResponse *, NSError *))completion {
  id answer = self.requests.count < self.answers.count ? self.answers[self.requests.count] : @(-9);
  [self.requests addObject:request];
  MegaFixtureTask *task = [MegaFixtureTask new];
  __weak MegaFixtureTask *weakTask = task;
  task.run = ^{
    // Let a caller cancel immediately after obtaining its resolution object.
    usleep(2000);
    if (weakTask.cancelled) {
      completion(nil, nil, [NSError errorWithDomain:NSURLErrorDomain code:NSURLErrorCancelled userInfo:nil]); return;
    }
    NSString *path = [NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
    NSData *body = [NSJSONSerialization dataWithJSONObject:answer options:NSJSONWritingFragmentsAllowed error:nil];
    NSHTTPURLResponse *response = [[NSHTTPURLResponse alloc] initWithURL:[NSURL URLWithString:self.responseURL]
        statusCode:self.status HTTPVersion:@"HTTP/1.1" headerFields:@{@"Content-Type": self.contentType}];
    weakTask.response = response;
    [weakTask.delegate URLSession:(NSURLSession *)(id)self downloadTask:(NSURLSessionDownloadTask *)(id)weakTask
        didWriteData:self.reportedBytes totalBytesWritten:self.reportedBytes totalBytesExpectedToWrite:self.expectedLength];
    if (weakTask.cancelled) {
      completion(nil, response, [NSError errorWithDomain:NSURLErrorDomain code:NSURLErrorCancelled userInfo:nil]); return;
    }
    [body writeToFile:path atomically:YES];
    completion([NSURL fileURLWithPath:path], response, nil);
    [NSFileManager.defaultManager removeItemAtPath:path error:nil];
  };
  return (NSURLSessionDownloadTask *)(id)task;
}
@end

static NSData *Decode(NSString *text) {
  NSString *s = [[text stringByReplacingOccurrencesOfString:@"-" withString:@"+"] stringByReplacingOccurrencesOfString:@"_" withString:@"/"];
  while (s.length % 4) s = [s stringByAppendingString:@"="];
  return [[NSData alloc] initWithBase64EncodedString:s options:0];
}

struct Resolved { NSURL *url; NSDictionary *crypto; NSError *error; };
static Resolved Resolve(NSDictionary *part, MegaFixtureSession *session, BOOL cancel = NO) {
  __block Resolved output{};
  auto done = std::make_shared<std::atomic<bool>>(false);
  NeoTextureMegaRequest *request = NeoTexResolveMegaPart(part, (NSURLSession *)(id)session,
      ^(NSURL *url, NSDictionary *crypto, NSError *error) {
    output = {url, crypto, error}; done->store(true);
  });
  if (cancel) [request cancel];
  NSDate *end = [NSDate dateWithTimeIntervalSinceNow:5];
  while (!done->load() && end.timeIntervalSinceNow > 0) usleep(1000);
  CHECK(done->load(), "metadata resolution completes");
  return output;
}

int main(int argc, char **argv) {
  @autoreleasepool {
    if (argc != 2) return 64;
    NSString *root = @(argv[1]);
    NSFileManager *fm = NSFileManager.defaultManager;
    NSDictionary *fixture = [NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:
        [root stringByAppendingPathComponent:@"fixture.json"]] options:0 error:nil];
    NSDictionary *part = fixture[@"part"], *folderPart = fixture[@"folderPart"];
    NSDictionary *crypto = @{@"key": Decode(fixture[@"crypto"][@"key"]), @"iv": Decode(fixture[@"crypto"][@"iv"]),
                              @"size": part[@"size"]};
    CHECK(NeoTexMegaPublicFileURL(part[@"url"]), "current file link accepted");
    CHECK(NeoTexMegaPublicFileURL(fixture[@"legacy"]), "legacy file link accepted");
    CHECK(NeoTexMegaPublicFileURL(folderPart[@"url"]), "selected folder file accepted");
    for (NSString *url in @[@"http://mega.nz/file/ABCDEFGH#key", @"https://mega.nz.attacker.invalid/file/ABCDEFGH#key",
                            @"https://user@mega.nz/file/ABCDEFGH#key", @"https://mega.nz:8443/file/ABCDEFGH#key",
                            @"https://mega.nz/folder/FOLDERAB#ICEiIyQlJicoKSorLC0uLw", @"https://mega.nz/file/ABCDEFGH#missing",
                            [part[@"url"] stringByReplacingOccurrencesOfString:@"ABCDEFGH" withString:@"ABC"],
                            [part[@"url"] stringByReplacingOccurrencesOfString:@"#" withString:@"?account=1#"]])
      CHECK(!NeoTexMegaPublicFileURL(url), "invalid/private/whole-folder link refused");

    MegaFixtureSession *session = [MegaFixtureSession new]; session.answers = @[fixture[@"fileResponse"]];
    Resolved file = Resolve(part, session);
    CHECK(!file.error && file.url && [file.crypto[@"key"] isEqual:crypto[@"key"]] &&
          [file.crypto[@"iv"] isEqual:crypto[@"iv"]], "file link derives expected AES key and big endian IV");
    CHECK(session.requests.count == 1, "file metadata called once");
    NSDictionary *command = [NSJSONSerialization JSONObjectWithData:[session.requests[0] HTTPBody] options:0 error:nil][0];
    CHECK([command[@"p"] isEqual:@"ABCDEFGH"] && [command[@"ssl"] isEqual:@1], "public handle and HTTPS metadata request");
    CHECK(![command.allValues containsObject:[part[@"url"] componentsSeparatedByString:@"#"].lastObject], "file key never sent");

    session = [MegaFixtureSession new]; session.answers = @[fixture[@"folderResponse"], fixture[@"fileResponse"]];
    Resolved folder = Resolve(folderPart, session);
    CHECK(!folder.error && [folder.crypto[@"key"] isEqual:crypto[@"key"]] && session.requests.count == 2,
          "folder selected-node key unwrap and metadata resolution");
    command = [NSJSONSerialization JSONObjectWithData:[session.requests[1] HTTPBody] options:0 error:nil][0];
    CHECK([command[@"n"] isEqual:@"FILEABCD"] && !command[@"p"], "folder request selects exact node");
    for (NSNumber *code in @[@(-3), @(-4), @(-9), @(-11), @(-16), @(-17), @(-18)]) {
      session = [MegaFixtureSession new]; session.answers = @[@[code]];
      Resolved result = Resolve(part, session);
      CHECK(result.error && session.requests.count == 1, "provider refusal ends without retry");
      CHECK([result.error.userInfo[@"provider_code"] isEqual:code], "provider failure preserved without URL/key");
    }
    for (NSNumber *status in @[@401, @403, @429, @509]) {
      session = [MegaFixtureSession new]; session.answers = @[fixture[@"fileResponse"]]; session.status = status.integerValue;
      CHECK(Resolve(part, session).error && session.requests.count == 1, "HTTP access/quota refusal not retried");
    }
    session = [MegaFixtureSession new]; session.answers = @[fixture[@"fileResponse"]];
    CHECK(Resolve(part, session, YES).error.code == NeoTexturePackErrorCancelled, "cancel public metadata request");
    session = [MegaFixtureSession new]; session.answers = @[fixture[@"fileResponse"]]; session.expectedLength = 9 << 20;
    CHECK(Resolve(part, session).error != nil && session.requests.count == 1, "oversized metadata stopped at first progress");
    session = [MegaFixtureSession new]; session.answers = @[fixture[@"fileResponse"]]; session.reportedBytes = 9 << 20;
    CHECK(Resolve(part, session).error != nil && session.requests.count == 1, "unknown-length metadata stops at streaming bound");
    session = [MegaFixtureSession new]; session.answers = @[fixture[@"fileResponse"]]; session.contentType = @"text/html";
    CHECK(Resolve(part, session).error != nil && session.requests.count == 1, "HTML metadata refused before file read");
    NSMutableDictionary *wrong = [part mutableCopy];
    wrong[@"url"] = [part[@"url"] stringByReplacingOccurrencesOfString:@"AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8" withString:
        @"AQECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8"];
    session = [MegaFixtureSession new]; session.answers = @[fixture[@"fileResponse"]];
    CHECK(Resolve(wrong, session).error != nil, "wrong public key fails encrypted attributes");
    NSMutableDictionary *badAnswer = [fixture[@"fileResponse"][0] mutableCopy]; badAnswer[@"g"] = @"http://gfs000.userstorage.mega.co.nz/file";
    session = [MegaFixtureSession new]; session.answers = @[@[badAnswer]];
    CHECK(Resolve(part, session).error != nil, "non-HTTPS ciphertext URL refused");
    badAnswer[@"g"] = @"https://mega.co.nz.attacker.invalid/file";
    session = [MegaFixtureSession new]; session.answers = @[@[badAnswer]];
    CHECK(Resolve(part, session).error != nil, "foreign ciphertext URL refused");

    NSString *cipher = [root stringByAppendingPathComponent:@"cipher.bin"];
    NSString *plain = [root stringByAppendingPathComponent:@"plain.bin"];
    NSString *candidate = [root stringByAppendingPathComponent:@"candidate.bin"];
    void (^copy)(void) = ^{ [fm removeItemAtPath:candidate error:nil]; CHECK([fm copyItemAtPath:cipher toPath:candidate error:nil], "fixture copied"); };
    copy();
    CHECK(!NeoTexDecryptMegaFile(candidate, part, file.crypto, []{ return false; }), "independent AES CTR ciphertext verifies");
    CHECK([[NSData dataWithContentsOfFile:candidate] isEqual:[NSData dataWithContentsOfFile:plain]], "all plaintext bytes, counter rollover and odd tail match");
    copy(); NSMutableDictionary *wrongCrypto = [crypto mutableCopy];
    NSMutableData *wrongKey = [crypto[@"key"] mutableCopy]; ((uint8_t *)wrongKey.mutableBytes)[0] ^= 1; wrongCrypto[@"key"] = wrongKey;
    CHECK(NeoTexDecryptMegaFile(candidate, part, wrongCrypto, []{ return false; }).code == NeoTexturePackErrorChanged &&
          ![fm fileExistsAtPath:candidate], "wrong key fails exact SHA and removes candidate");
    copy(); wrong = [part mutableCopy]; wrong[@"sha256"] = [@"0" stringByPaddingToLength:64 withString:@"0" startingAtIndex:0];
    CHECK(NeoTexDecryptMegaFile(candidate, wrong, crypto, []{ return false; }).code == NeoTexturePackErrorChanged &&
          ![fm fileExistsAtPath:candidate], "changed plaintext digest rejected");
    copy(); int calls = 0;
    CHECK(NeoTexDecryptMegaFile(candidate, part, crypto, [&calls]{ return ++calls >= 2; }).code == NeoTexturePackErrorCancelled &&
          ![fm fileExistsAtPath:candidate], "mid-stream cancel removes mixed ciphertext/plaintext candidate");
    copy();
    CHECK(NeoTexDecryptMegaFile(candidate, part, crypto, []{ return true; }).code == NeoTexturePackErrorCancelled &&
          ![fm fileExistsAtPath:candidate], "pre-decrypt cancel removes candidate");
    copy();
    NSFileHandle *handle = [NSFileHandle fileHandleForWritingAtPath:candidate]; [handle truncateFileAtOffset:17]; [handle closeFile];
    CHECK(NeoTexDecryptMegaFile(candidate, part, crypto, []{ return false; }).code == NeoTexturePackErrorChanged &&
          ![fm fileExistsAtPath:candidate], "truncated ciphertext refused before decrypt");
    [fm createSymbolicLinkAtPath:candidate withDestinationPath:plain error:nil];
    NSData *original = [NSData dataWithContentsOfFile:plain];
    CHECK(NeoTexDecryptMegaFile(candidate, part, crypto, []{ return false; }).code == NeoTexturePackErrorWrite &&
          [[NSData dataWithContentsOfFile:plain] isEqual:original], "symlink cannot modify another file");
    printf("MEGA native protocol/crypto: %d checks, %d failures\n", checks, failures);
  }
  return failures ? 1 : 0;
}

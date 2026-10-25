// SPDX-License-Identifier: GPL-3.0-or-later
// The small public-link protocol below matches MEGA's public web client:
// no account, SDK, executable, hosted copy or persistent resolved URL.
#import "NeoTextureMega.h"
#import "Public/NeoTexturePackStore.h"
#import <CommonCrypto/CommonCryptor.h>
#import <CommonCrypto/CommonDigest.h>
#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fcntl.h>
#include <memory>
#include <sys/stat.h>
#include <unistd.h>

static constexpr unsigned long long MegaMaximum = 16ULL << 30;
static constexpr NSUInteger MegaJSONMaximum = 8U << 20;

static NSError *MegaError(NeoTexturePackError code, NSString *key, NSInteger detail = 0) {
  return [NSError errorWithDomain:@"NeoTexturePackStore" code:code
      userInfo:@{@"key": key, NSLocalizedDescriptionKey: key, @"provider": @"mega", @"provider_code": @(detail)}];
}

static BOOL MegaToken(id value, NSUInteger length) {
  if (![value isKindOfClass:NSString.class] || [value length] != length) return NO;
  static NSCharacterSet *bad;
  static dispatch_once_t once;
  dispatch_once(&once, ^{ bad = [[NSCharacterSet characterSetWithCharactersInString:
      @"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"] invertedSet]; });
  return [(NSString *)value rangeOfCharacterFromSet:bad].location == NSNotFound;
}

static NSData *MegaBase64(id value, NSUInteger bytes) {
  const NSUInteger length = (bytes * 8 + 5) / 6;
  if (!MegaToken(value, length)) return nil;
  NSString *text = [(NSString *)value stringByReplacingOccurrencesOfString:@"-" withString:@"+"];
  text = [text stringByReplacingOccurrencesOfString:@"_" withString:@"/"];
  while (text.length % 4) text = [text stringByAppendingString:@"="];
  NSData *data = [[NSData alloc] initWithBase64EncodedString:text options:0];
  if (data.length != bytes) return nil;
  NSString *canonical = [[[data base64EncodedStringWithOptions:0]
      stringByReplacingOccurrencesOfString:@"+" withString:@"-"] stringByReplacingOccurrencesOfString:@"/" withString:@"_"];
  canonical = [canonical stringByTrimmingCharactersInSet:[NSCharacterSet characterSetWithCharactersInString:@"="]];
  return [canonical isEqual:value] ? data : nil;
}

static unsigned long long MegaSize(id value) {
  if (![value isKindOfClass:NSNumber.class]) return 0;
  double number = [value doubleValue];
  return std::isfinite(number) && number >= 1 && number <= MegaMaximum && std::floor(number) == number
      ? [value unsignedLongLongValue] : 0;
}

// Public link keys are never sent to the API. Only handles are sent.
static NSDictionary *MegaLink(NSString *text) {
  if (![text isKindOfClass:NSString.class] || text.length > 512) return nil;
  NSURLComponents *url = [NSURLComponents componentsWithString:text];
  if (![url.scheme.lowercaseString isEqual:@"https"] || url.user || url.password || url.query.length ||
      (url.port && url.port.integerValue != 443) ||
      ![@[@"mega.nz", @"www.mega.nz", @"mega.co.nz", @"www.mega.co.nz", @"mega.io", @"www.mega.io"]
          containsObject:url.host.lowercaseString]) return nil;
  NSArray *path = [url.path componentsSeparatedByString:@"/"];
  NSArray *fragment = [url.fragment componentsSeparatedByString:@"/"];
  NSString *handle = nil, *file = nil, *key = nil;
  BOOL folder = NO;
  if (path.count == 3 && [path[0] isEqual:@""] && [path[1] isEqual:@"file"] && fragment.count == 1) {
    handle = path[2]; key = fragment[0];
  } else if (path.count == 3 && [path[0] isEqual:@""] && [path[1] isEqual:@"folder"] &&
             fragment.count == 3 && [fragment[1] isEqual:@"file"]) {
    folder = YES; handle = path[2]; key = fragment[0]; file = fragment[2];
  } else if ([url.path isEqual:@""] || [url.path isEqual:@"/"]) {
    NSArray *old = [url.fragment componentsSeparatedByString:@"!"];
    if (old.count == 3 && [old[0] isEqual:@""]) { handle = old[1]; key = old[2]; }
    else if (old.count == 4 && [old[0] isEqual:@"F"]) {
      folder = YES; handle = old[1]; key = old[2]; file = old[3];
    }
  }
  NSData *decoded = MegaBase64(key, folder ? 16 : 32);
  if (!MegaToken(handle, 8) || !decoded || (folder && !MegaToken(file, 8))) return nil;
  return @{@"handle": handle, @"file": file ?: handle, @"folder": @(folder), @"link_key": decoded};
}

BOOL NeoTexIsMegaPart(NSDictionary *part) { return [part[@"provider"] isEqual:@"mega"]; }
BOOL NeoTexMegaPublicFileURL(NSString *url) { return MegaLink(url) != nil; }

@interface NeoTextureMegaRequest () {
  NSLock *_lock;
  NSURLSessionTask *_active;
  BOOL _cancelled;
}
- (BOOL)cancelled;
- (void)acceptTask:(NSURLSessionTask *)task;
- (void)clearTask;
@end

@implementation NeoTextureMegaRequest
- (instancetype)init { if ((self = [super init])) _lock = [NSLock new]; return self; }
- (void)cancel {
  [_lock lock]; _cancelled = YES; NSURLSessionTask *task = _active; [_lock unlock];
  [task cancel];
}
- (BOOL)cancelled { [_lock lock]; BOOL value = _cancelled; [_lock unlock]; return value; }
- (void)acceptTask:(NSURLSessionTask *)task {
  [_lock lock]; _active = task; BOOL cancel = _cancelled; [_lock unlock];
  if (cancel) [task cancel];
}
- (void)clearTask { [_lock lock]; _active = nil; [_lock unlock]; }
@end

// Task-specific delegate: metadata progress never reaches the archive store's
// download delegate. A declared oversize body or non-JSON response is stopped
// at the first progress callback; unknown-length bodies stop at the same bound.
@interface NeoTextureMegaMetadataGuard : NSObject <NSURLSessionDownloadDelegate>
@property(atomic, strong) NSError *failure;
@end
@implementation NeoTextureMegaMetadataGuard
- (void)URLSession:(NSURLSession *)session downloadTask:(NSURLSessionDownloadTask *)task
    didWriteData:(int64_t)written totalBytesWritten:(int64_t)total totalBytesExpectedToWrite:(int64_t)expected {
  (void)session; (void)written;
  NSHTTPURLResponse *http = [task.response isKindOfClass:NSHTTPURLResponse.class] ? (NSHTTPURLResponse *)task.response : nil;
  NSString *type = [http valueForHTTPHeaderField:@"Content-Type"].lowercaseString ?: @"";
  if (expected > (int64_t)MegaJSONMaximum || total > (int64_t)MegaJSONMaximum ||
      !([type hasPrefix:@"application/json"] || [type hasPrefix:@"text/plain"])) {
    self.failure = MegaError(NeoTexturePackErrorNetwork, @"network");
    [task cancel];
  }
}
- (void)URLSession:(NSURLSession *)session downloadTask:(NSURLSessionDownloadTask *)task
    didFinishDownloadingToURL:(NSURL *)location { (void)session; (void)task; (void)location; }
- (void)URLSession:(NSURLSession *)session task:(NSURLSessionTask *)task
    willPerformHTTPRedirection:(NSHTTPURLResponse *)response newRequest:(NSURLRequest *)request
    completionHandler:(void (^)(NSURLRequest *))completionHandler {
  (void)session; (void)task; (void)response; (void)request;
  self.failure = MegaError(NeoTexturePackErrorNetwork, @"network");
  completionHandler(nil);  // the fixed canonical public API does not redirect
}
- (void)URLSession:(NSURLSession *)session task:(NSURLSessionTask *)task
    didReceiveChallenge:(NSURLAuthenticationChallenge *)challenge
    completionHandler:(void (^)(NSURLSessionAuthChallengeDisposition, NSURLCredential *))completionHandler {
  (void)session; (void)task;
  if ([challenge.protectionSpace.authenticationMethod isEqual:NSURLAuthenticationMethodServerTrust])
    completionHandler(NSURLSessionAuthChallengePerformDefaultHandling, nil);
  else
    completionHandler(NSURLSessionAuthChallengeCancelAuthenticationChallenge, nil);
}
@end

static void MegaAPI(NeoTextureMegaRequest *operation, NSURLSession *session, NSDictionary *command,
                    NSString *folder, void (^completion)(NSDictionary *, NSError *)) {
  NSURLComponents *components = [NSURLComponents componentsWithString:@"https://g.api.mega.co.nz/cs"];
  NSMutableArray *query = [NSMutableArray arrayWithObject:[NSURLQueryItem queryItemWithName:@"id" value:@"1"]];
  if (folder.length) [query addObject:[NSURLQueryItem queryItemWithName:@"n" value:folder]];
  components.queryItems = query;
  NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:components.URL];
  request.HTTPMethod = @"POST";
  request.HTTPShouldHandleCookies = NO;
  request.HTTPBody = [NSJSONSerialization dataWithJSONObject:@[command] options:0 error:nil];
  request.timeoutInterval = 60;
  request.cachePolicy = NSURLRequestReloadIgnoringLocalCacheData;
  [request setValue:@"application/json" forHTTPHeaderField:@"Content-Type"];
  [request setValue:@"NeoStation-iOS" forHTTPHeaderField:@"User-Agent"];
  // A metadata response is downloaded to a temporary file, not accumulated in
  // RAM. Only a bounded public-node list is subsequently decoded.
  NeoTextureMegaMetadataGuard *guard = [NeoTextureMegaMetadataGuard new];
  NSURLSessionDownloadTask *task = [session downloadTaskWithRequest:request completionHandler:
      ^(NSURL *location, NSURLResponse *response, NSError *error) {
    [operation clearTask];
    if ([operation cancelled]) { completion(nil, MegaError(NeoTexturePackErrorCancelled, @"cancelled")); return; }
    if (guard.failure) { completion(nil, guard.failure); return; }
    if (error) { completion(nil, MegaError(NeoTexturePackErrorNetwork, @"network", error.code)); return; }
    NSHTTPURLResponse *http = [response isKindOfClass:NSHTTPURLResponse.class] ? (NSHTTPURLResponse *)response : nil;
    NSString *type = [http valueForHTTPHeaderField:@"Content-Type"].lowercaseString ?: @"";
    if (!http || http.statusCode != 200 ||
        !([type hasPrefix:@"application/json"] || [type hasPrefix:@"text/plain"]) ||
        ![http.URL.scheme.lowercaseString isEqual:@"https"] ||
        ![http.URL.host.lowercaseString isEqual:@"g.api.mega.co.nz"]) {
      completion(nil, MegaError(NeoTexturePackErrorNetwork, @"network", http.statusCode)); return;
    }
    unsigned long long size = [NSFileManager.defaultManager attributesOfItemAtPath:location.path error:nil].fileSize;
    if (!size || size > MegaJSONMaximum) { completion(nil, MegaError(NeoTexturePackErrorNetwork, @"network")); return; }
    NSData *body = [NSData dataWithContentsOfURL:location options:0 error:nil];
    id answer = body.length <= MegaJSONMaximum ? [NSJSONSerialization JSONObjectWithData:body options:NSJSONReadingFragmentsAllowed error:nil] : nil;
    if ([answer isKindOfClass:NSArray.class]) answer = [(NSArray *)answer count] == 1 ? answer[0] : nil;
    if ([answer isKindOfClass:NSNumber.class]) {
      completion(nil, MegaError(NeoTexturePackErrorNetwork, @"network", [answer integerValue])); return;
    }
    if (![answer isKindOfClass:NSDictionary.class]) { completion(nil, MegaError(NeoTexturePackErrorNetwork, @"network")); return; }
    if ([answer[@"e"] isKindOfClass:NSNumber.class] && [answer[@"e"] integerValue] < 0) {
      completion(nil, MegaError(NeoTexturePackErrorNetwork, @"network", [answer[@"e"] integerValue])); return;
    }
    completion(answer, nil);
  }];
  task.delegate = guard;
  [operation acceptTask:task];
  [task resume];
}

static NSDictionary *MegaCrypto(NSData *raw, unsigned long long size) {
  if (raw.length != 32 || !size) return nil;
  const uint8_t *bytes = (const uint8_t *)raw.bytes;
  uint8_t key[16], iv[16] = {};
  for (NSUInteger i = 0; i < 16; i++) key[i] = bytes[i] ^ bytes[i + 16];
  std::copy(bytes + 16, bytes + 24, iv);
  return @{@"key": [NSData dataWithBytes:key length:16], @"iv": [NSData dataWithBytes:iv length:16], @"size": @(size)};
}

static NSData *MegaBlockDecrypt(NSData *data, NSData *key, BOOL ecb) {
  if (!data.length || data.length > 16384 || data.length % 16 || key.length != 16) return nil;
  NSMutableData *plain = [NSMutableData dataWithLength:data.length];
  uint8_t iv[16] = {};
  size_t written = 0;
  CCCryptorStatus status = CCCrypt(kCCDecrypt, kCCAlgorithmAES, ecb ? kCCOptionECBMode : 0,
      key.bytes, key.length, iv, data.bytes, data.length, plain.mutableBytes, plain.length, &written);
  return status == kCCSuccess && written == data.length ? plain : nil;
}

static BOOL MegaAttributes(id encoded, NSData *key) {
  if (![encoded isKindOfClass:NSString.class] || ![encoded length] || [encoded length] > 22000) return NO;
  NSUInteger bytes = [encoded length] * 6 / 8;
  NSData *plain = MegaBlockDecrypt(MegaBase64(encoded, bytes), key, NO);
  if (plain.length < 16 || memcmp(plain.bytes, "MEGA", 4) != 0) return NO;
  NSUInteger end = plain.length;
  const uint8_t *data = (const uint8_t *)plain.bytes;
  while (end > 4 && data[end - 1] == 0) end--;
  id json = [NSJSONSerialization JSONObjectWithData:[plain subdataWithRange:NSMakeRange(4, end - 4)] options:0 error:nil];
  return [json isKindOfClass:NSDictionary.class] && [json[@"n"] isKindOfClass:NSString.class] &&
      [json[@"n"] length] > 0 && [json[@"n"] length] <= 1024;
}

static NSURL *MegaDownloadURL(id value) {
  if (![value isKindOfClass:NSString.class] || [value length] > 8192) return nil;
  NSURLComponents *url = [NSURLComponents componentsWithString:value];
  NSString *host = url.host.lowercaseString;
  if (![url.scheme.lowercaseString isEqual:@"https"] || url.user || url.password || url.fragment ||
      (url.port && url.port.integerValue != 443) ||
      !([host isEqual:@"mega.nz"] || [host hasSuffix:@".mega.nz"] ||
        [host isEqual:@"mega.co.nz"] || [host hasSuffix:@".mega.co.nz"] ||
        [host isEqual:@"mega.io"] || [host hasSuffix:@".mega.io"])) return nil;
  return url.URL;
}

NeoTextureMegaRequest *NeoTexResolveMegaPart(NSDictionary *part, NSURLSession *session,
    void (^completion)(NSURL *, NSDictionary *, NSError *)) {
  NeoTextureMegaRequest *operation = [NeoTextureMegaRequest new];
  NSDictionary *link = MegaLink(part[@"url"]);
  unsigned long long size = MegaSize(part[@"size"]);
  if (!NeoTexIsMegaPart(part) || !link || !size) {
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
      completion(nil, nil, MegaError(NeoTexturePackErrorNetwork, @"network"));
    });
    return operation;
  }
  void (^resolve)(NSDictionary *) = ^(NSDictionary *crypto) {
    if ([operation cancelled]) { completion(nil, nil, MegaError(NeoTexturePackErrorCancelled, @"cancelled")); return; }
    NSDictionary *command = [link[@"folder"] boolValue]
        ? @{@"a": @"g", @"g": @1, @"n": link[@"file"], @"ssl": @1}
        : @{@"a": @"g", @"g": @1, @"p": link[@"handle"], @"ssl": @1};
    MegaAPI(operation, session, command, [link[@"folder"] boolValue] ? link[@"handle"] : nil,
        ^(NSDictionary *answer, NSError *error) {
      if (error) { completion(nil, nil, error); return; }
      NSURL *url = MegaDownloadURL(answer[@"g"]);
      if (!url || MegaSize(answer[@"s"]) != size || (!crypto && !MegaAttributes(answer[@"at"],
          MegaCrypto(link[@"link_key"], size)[@"key"]))) {
        completion(nil, nil, MegaError(NeoTexturePackErrorChanged, @"changed")); return;
      }
      completion(url, crypto ?: MegaCrypto(link[@"link_key"], size), nil);
    });
  };
  if (![link[@"folder"] boolValue]) { resolve(nil); return operation; }
  MegaAPI(operation, session, @{@"a": @"f", @"c": @1, @"ca": @1, @"r": @1}, link[@"handle"],
      ^(NSDictionary *answer, NSError *error) {
    if (error) { completion(nil, nil, error); return; }
    NSArray *nodes = [answer[@"f"] isKindOfClass:NSArray.class] ? answer[@"f"] : nil;
    if (!nodes || nodes.count > 10000) { completion(nil, nil, MegaError(NeoTexturePackErrorNetwork, @"network")); return; }
    for (id item in nodes) {
      if (![item isKindOfClass:NSDictionary.class] || ![item[@"h"] isEqual:link[@"file"]] ||
          ![item[@"t"] isKindOfClass:NSNumber.class] || [item[@"t"] integerValue] != 0) continue;
      if (MegaSize(item[@"s"]) != size || ![item[@"k"] isKindOfClass:NSString.class] || [item[@"k"] length] > 2048) break;
      NSArray *shares = [item[@"k"] componentsSeparatedByString:@"/"];
      if (shares.count > 16) break;
      for (NSString *share in shares) {
        NSData *encrypted = MegaBase64([[share componentsSeparatedByString:@":"] lastObject], 32);
        NSData *raw = MegaBlockDecrypt(encrypted, link[@"link_key"], YES);
        NSDictionary *crypto = MegaCrypto(raw, size);
        if (crypto && MegaAttributes(item[@"a"], crypto[@"key"])) { resolve(crypto); return; }
      }
      break;
    }
    completion(nil, nil, MegaError(NeoTexturePackErrorChanged, @"changed"));
  });
  return operation;
}

NSError *NeoTexDecryptMegaFile(NSString *path, NSDictionary *part, NSDictionary *crypto, std::function<bool()> cancelled) {
  const unsigned long long expected = MegaSize(part[@"size"]);
  NSData *key = [crypto[@"key"] isKindOfClass:NSData.class] ? crypto[@"key"] : nil;
  NSData *iv = [crypto[@"iv"] isKindOfClass:NSData.class] ? crypto[@"iv"] : nil;
  NSString *expectedSHA = [part[@"sha256"] isKindOfClass:NSString.class] ? [part[@"sha256"] lowercaseString] : @"";
  if (!NeoTexIsMegaPart(part) || !expected || MegaSize(crypto[@"size"]) != expected || key.length != 16 ||
      iv.length != 16 || expectedSHA.length != 64) return MegaError(NeoTexturePackErrorChanged, @"changed");
  int file = open(path.fileSystemRepresentation, O_RDWR | O_NOFOLLOW);
  if (file < 0) return MegaError(NeoTexturePackErrorWrite, @"writeFailed");
  struct stat statbuf = {};
  if (fstat(file, &statbuf) != 0 || !S_ISREG(statbuf.st_mode) || statbuf.st_size < 0 ||
      (unsigned long long)statbuf.st_size != expected) {
    close(file); unlink(path.fileSystemRepresentation); return MegaError(NeoTexturePackErrorChanged, @"changed");
  }
  CCCryptorRef cryptor = nullptr;
  CCCryptorStatus status = CCCryptorCreateWithMode(kCCDecrypt, kCCModeCTR, kCCAlgorithmAES, ccNoPadding,
      iv.bytes, key.bytes, key.length, nullptr, 0, 0, kCCModeOptionCTR_BE, &cryptor);
  NSError *failure = status == kCCSuccess ? nil : MegaError(NeoTexturePackErrorWrite, @"writeFailed");
  constexpr size_t chunk = 1U << 20;
  std::unique_ptr<uint8_t[]> input(new uint8_t[chunk]), output(new uint8_t[chunk]);
  CC_SHA256_CTX digest;
  CC_SHA256_Init(&digest);
  for (unsigned long long offset = 0; !failure && offset < expected;) {
    if (cancelled && cancelled()) { failure = MegaError(NeoTexturePackErrorCancelled, @"cancelled"); break; }
    size_t amount = (size_t)std::min<unsigned long long>(chunk, expected - offset), read = 0;
    while (read < amount) {
      ssize_t n = pread(file, input.get() + read, amount - read, (off_t)(offset + read));
      if (n < 0 && errno == EINTR) continue;
      if (n <= 0) { failure = MegaError(NeoTexturePackErrorWrite, @"writeFailed"); break; }
      read += (size_t)n;
    }
    if (failure) break;
    size_t produced = 0;
    if (CCCryptorUpdate(cryptor, input.get(), amount, output.get(), chunk, &produced) != kCCSuccess || produced != amount) {
      failure = MegaError(NeoTexturePackErrorWrite, @"writeFailed"); break;
    }
    size_t written = 0;
    while (written < produced) {
      ssize_t n = pwrite(file, output.get() + written, produced - written, (off_t)(offset + written));
      if (n < 0 && errno == EINTR) continue;
      if (n <= 0) { failure = MegaError(NeoTexturePackErrorWrite, @"writeFailed"); break; }
      written += (size_t)n;
    }
    CC_SHA256_Update(&digest, output.get(), (CC_LONG)produced);
    offset += amount;
  }
  if (!failure) {
    size_t tail = 0;
    if (CCCryptorFinal(cryptor, output.get(), chunk, &tail) != kCCSuccess || tail) failure = MegaError(NeoTexturePackErrorWrite, @"writeFailed");
  }
  if (cryptor) CCCryptorRelease(cryptor);
  unsigned char bytes[CC_SHA256_DIGEST_LENGTH];
  CC_SHA256_Final(bytes, &digest);
  NSMutableString *actual = [NSMutableString stringWithCapacity:64];
  for (NSUInteger i = 0; i < sizeof(bytes); i++) [actual appendFormat:@"%02x", bytes[i]];
  if (!failure && ![actual isEqual:expectedSHA]) failure = MegaError(NeoTexturePackErrorChanged, @"changed");
  if (!failure && cancelled && cancelled()) failure = MegaError(NeoTexturePackErrorCancelled, @"cancelled");
  if (!failure && fsync(file) != 0) failure = MegaError(NeoTexturePackErrorWrite, @"writeFailed");
  close(file);
  if (failure) unlink(path.fileSystemRepresentation);
  return failure;
}

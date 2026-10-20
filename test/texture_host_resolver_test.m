// Exercises the production anonymous host resolver through NSURLSession's real
// delegate path. Fixtures replace only network transport, not parsing/policy.
#import <Foundation/Foundation.h>
#import "NeoTextureHostResolver.h"
#include <stdio.h>

static int checks = 0, failures = 0;
#define CHECK(value, message) do { checks++; if (!(value)) { failures++; fprintf(stderr, "FAIL line %d: %s\n", __LINE__, message); } } while (0)

static NSArray<NSDictionary *> *Responses;
static NSMutableArray<NSURLRequest *> *Requests;
static NSUInteger SentBytes;

@interface HostFixtureProtocol : NSURLProtocol
@property(atomic) BOOL stopped;
@end

@implementation HostFixtureProtocol
+ (BOOL)canInitWithRequest:(NSURLRequest *)request { return YES; }
+ (NSURLRequest *)canonicalRequestForRequest:(NSURLRequest *)request { return request; }
- (void)startLoading {
  NSDictionary *fixture = nil;
  @synchronized(HostFixtureProtocol.class) {
    NSUInteger at = Requests.count;
    [Requests addObject:self.request];
    if (at < Responses.count) fixture = Responses[at];
  }
  if (!fixture) {
    [self.client URLProtocol:self didFailWithError:[NSError errorWithDomain:@"unexpected-fixture-request" code:1 userInfo:nil]];
    return;
  }
  if ([fixture[@"stall"] boolValue]) return;
  NSString *redirect = fixture[@"redirect"];
  if (redirect) {
    NSHTTPURLResponse *response = [[NSHTTPURLResponse alloc] initWithURL:self.request.URL statusCode:302 HTTPVersion:@"HTTP/1.1" headerFields:@{@"Location": redirect}];
    [self.client URLProtocol:self wasRedirectedToRequest:[NSURLRequest requestWithURL:[NSURL URLWithString:redirect]] redirectResponse:response];
    return;
  }
  NSData *body = fixture[@"body"] ?: [NSData data];
  NSMutableDictionary *headers = [NSMutableDictionary dictionaryWithDictionary:fixture[@"headers"] ?: @{}];
  headers[@"Content-Type"] = fixture[@"type"] ?: @"application/json";
  if (![fixture[@"unknownLength"] boolValue] && !headers[@"Content-Length"]) headers[@"Content-Length"] = [NSString stringWithFormat:@"%lu", (unsigned long)body.length];
  NSHTTPURLResponse *response = [[NSHTTPURLResponse alloc] initWithURL:self.request.URL statusCode:fixture[@"status"] ? [fixture[@"status"] integerValue] : 200 HTTPVersion:@"HTTP/1.1" headerFields:headers];
  [self.client URLProtocol:self didReceiveResponse:response cacheStoragePolicy:NSURLCacheStorageNotAllowed];
  // A binary response must be cancelled at headers before this body is sent.
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 30 * NSEC_PER_MSEC), dispatch_get_global_queue(QOS_CLASS_DEFAULT, 0), ^{
    if (self.stopped) return;
    NSArray *chunks = fixture[@"chunks"] ?: @[body];
    for (NSData *chunk in chunks) {
      if (self.stopped) return;
      @synchronized(HostFixtureProtocol.class) { SentBytes += chunk.length; }
      [self.client URLProtocol:self didLoadData:chunk];
    }
    if (!self.stopped) [self.client URLProtocolDidFinishLoading:self];
  });
}
- (void)stopLoading { self.stopped = YES; }
@end

@interface ResolutionResult : NSObject
@property(nonatomic, strong) NSURL *url;
@property(nonatomic, strong) NSError *error;
@property(nonatomic) NSUInteger calls;
@end
@implementation ResolutionResult
@end

static NSString *Digest(void) { return @"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"; }
static NSString *GoogleID(void) { return @"1FILEabcdefghijkL0123"; }
static NSDictionary *Google(void) {
  return @{@"provider": @"gdrive", @"url": [NSString stringWithFormat:@"https://drive.google.com/file/d/%@/view?resourcekey=0-Share_Key", GoogleID()], @"size": @100, @"sha256": Digest()};
}
static NSDictionary *Yandex(void) {
  return @{@"provider": @"yandex", @"url": @"https://disk.yandex.ru/d/abcdefgHIjk", @"size": @100, @"sha256": Digest()};
}
static NSDictionary *Changed(NSDictionary *part, NSString *key, id value) {
  NSMutableDictionary *out = [part mutableCopy]; out[key] = value; return out;
}
static NSDictionary *HTML(NSString *html) { return @{@"type": @"text/html; charset=utf-8", @"body": [html dataUsingEncoding:NSUTF8StringEncoding]}; }
static NSDictionary *JSON(id value) { return @{@"type": @"application/json", @"body": [NSJSONSerialization dataWithJSONObject:value options:0 error:nil]}; }
static NSDictionary *Binary(void) { return @{@"type": @"application/octet-stream", @"headers": @{@"Content-Length": @"100"}, @"body": [NSMutableData dataWithLength:100]}; }
static NSDictionary *Query(NSURL *url) {
  NSMutableDictionary *query = [NSMutableDictionary dictionary];
  for (NSURLQueryItem *item in [NSURLComponents componentsWithURL:url resolvingAgainstBaseURL:NO].queryItems) query[item.name] = item.value ?: @"";
  return query;
}
static NSString *Form(NSString *fileID, NSString *action, NSString *extra) {
  return [NSString stringWithFormat:@"<!doctype html><form method='get' action='%@' id='download-form'><input value='t' name='confirm' type='hidden'><input name='id' type='hidden' value='%@'><input type='hidden' name='export' value='download'><input type='hidden' value='test-uuid' name='uuid'>%@</form>", action, fileID, extra ?: @""];
}

static ResolutionResult *Run(NSDictionary *part, NSArray *responses, BOOL cancel) {
  @synchronized(HostFixtureProtocol.class) { Responses = responses; Requests = [NSMutableArray array]; SentBytes = 0; }
  ResolutionResult *result = [ResolutionResult new];
  dispatch_semaphore_t done = dispatch_semaphore_create(0);
  NSURLSessionConfiguration *configuration = NSURLSessionConfiguration.ephemeralSessionConfiguration;
  configuration.protocolClasses = @[HostFixtureProtocol.class];
  id<NeoTexHostResolution> operation = NeoTexResolveHostPartWithConfiguration(part, configuration, ^(NSURL *url, NSError *error) {
    result.url = url; result.error = error; result.calls++; dispatch_semaphore_signal(done);
  });
  if (cancel) [operation cancel];
  CHECK(dispatch_semaphore_wait(done, dispatch_time(DISPATCH_TIME_NOW, 10 * NSEC_PER_SEC)) == 0, "resolver timed out");
  // Let cancellation/late delegate events drain before checking exactly-once.
  dispatch_semaphore_t settled = dispatch_semaphore_create(0);
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 60 * NSEC_PER_MSEC), dispatch_get_global_queue(QOS_CLASS_DEFAULT, 0), ^{ dispatch_semaphore_signal(settled); });
  dispatch_semaphore_wait(settled, dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC));
  CHECK(result.calls == 1, "completion must run exactly once");
  for (NSURLRequest *request in Requests) {
    CHECK([request.URL.scheme isEqual:@"https"], "transport used non-HTTPS");
    CHECK(![request valueForHTTPHeaderField:@"Cookie"].length && ![request valueForHTTPHeaderField:@"Authorization"].length, "transport sent credentials");
  }
  return result;
}

int main(void) {
  @autoreleasepool {
    CHECK(NeoTexValidHostPart(Google()), "valid original Google sharing descriptor");
    CHECK(NeoTexValidHostPart(Yandex()), "valid original Yandex sharing descriptor");
    for (NSDictionary *part in @[
      Changed(Google(), @"url", @"https://drive.google.com.evil.example/file/d/1FILEabcdefghijkL0123/view"),
      Changed(Google(), @"url", @"http://drive.google.com/file/d/1FILEabcdefghijkL0123/view"),
      Changed(Google(), @"url", @"https://name:password@drive.google.com/file/d/1FILEabcdefghijkL0123/view"),
      Changed(Google(), @"url", @"https://drive.google.com:8443/file/d/1FILEabcdefghijkL0123/view"),
      Changed(Google(), @"url", @"https://drive.google.com/drive/folders/1FILEabcdefghijkL0123"),
      Changed(Google(), @"url", @"https://drive.google.com/file/d/1FILEabcdefghijkL0123/view?id=1OTHERabcdefghijkL0123"),
      Changed(Google(), @"url", @"https://drive.google.com/uc?id=1FILEabcdefghijkL0123&id=1FILEabcdefghijkL0123"),
      Changed(Google(), @"size", @YES), Changed(Google(), @"size", @0), Changed(Google(), @"size", @1.5),
      Changed(Google(), @"sha256", @"bad"), Changed(Google(), @"sha256", [Digest() stringByAppendingString:@"\n"]),
      Changed(Google(), @"url", @"https://drive.google.com/uc?id=1FILEabcdefghijkL0123%0A"),
      Changed(Yandex(), @"url", @"https://disk.yandex.ru.evil.example/d/abcdefgHIjk"),
      Changed(Yandex(), @"url", @"https://disk.yandex.ru/d/abcdefgHIjk?account=other")]) {
      CHECK(!NeoTexValidHostPart(part), "invalid descriptor accepted");
    }

    ResolutionResult *result = Run(Google(), @[Binary()], NO);
    CHECK(result.url && !result.error && Requests.count == 1, "Google binary should resolve without downloading its body");
    CHECK(SentBytes == 0, "Google binary body was downloaded by resolver");
    CHECK([Query(Requests.firstObject.URL)[@"resourcekey"] isEqual:@"0-Share_Key"], "sharing resourcekey lost on initial request");
    CHECK([Query(result.url)[@"id"] isEqual:GoogleID()], "Google exact file ID changed");

    NSString *publicForm = Form(GoogleID(), @"https://drive.usercontent.google.com/download", nil);
    result = Run(Google(), @[HTML(publicForm), Binary()], NO);
    CHECK(result.url && !result.error && Requests.count == 2, "public virus-scan download form not followed");
    CHECK([Query(result.url)[@"confirm"] isEqual:@"t"] && [Query(result.url)[@"resourcekey"] isEqual:@"0-Share_Key"], "confirmation fields/resourcekey not preserved");
    CHECK(SentBytes == [publicForm lengthOfBytesUsingEncoding:NSUTF8StringEncoding], "confirmation fetched archive bytes");

    NSString *publicWithNavigation = [@"<nav><a href='https://accounts.google.com/ServiceLogin?continue=https%3A%2F%2Fdrive.google.com'>Sign in</a><a href='https://accounts.google.com/signin'>Google account</a></nav>" stringByAppendingString:publicForm];
    result = Run(Google(), @[HTML(publicWithNavigation), Binary()], NO);
    CHECK(result.url && !result.error && Requests.count == 2, "generic sign-in navigation incorrectly treated as an access wall");
    result = Run(Google(), @[HTML(@"<!doctype html><h1>You need access</h1><a href='https://accounts.google.com/ServiceLogin'>Sign in</a><button>Request access</button>")], NO);
    CHECK(!result.url && result.error && Requests.count == 1, "actual private permission page followed");

    for (NSString *html in @[
      Form(@"1OTHERabcdefghijkL0123", @"https://drive.usercontent.google.com/download", nil),
      Form(GoogleID(), @"https://evil.example/download", nil),
      Form(GoogleID(), @"http://drive.usercontent.google.com/download", nil),
      Form(GoogleID(), @"https://drive.usercontent.google.com/download", @"<input type='hidden' name='resourcekey' value='wrong-key'>"),
      [publicForm stringByAppendingString:@"<p>Too many users have viewed or downloaded this file</p>"],
      [publicForm stringByAppendingString:@"<p>Sign in to continue</p>"],
      [publicForm stringByAppendingString:@"<h1>You need access</h1><button>Request access</button>"],
      [publicForm stringByAppendingString:@"<div class='g-recaptcha'></div>"],
      @"<html>No public download form</html>"
    ]) {
      result = Run(Google(), @[HTML(html)], NO);
      CHECK(!result.url && [result.error.userInfo[@"key"] isEqual:@"htmlPage"] && Requests.count == 1, "unsupported/protected/mismatched form followed");
    }
    for (NSNumber *status in @[@401, @403, @429, @509]) {
      result = Run(Google(), @[@{@"status": status}], NO);
      CHECK(!result.url && result.error && Requests.count == 1, "access denial/quota was retried");
      CHECK([result.error.userInfo[@"status"] isEqual:status], "HTTP refusal status missing from bounded error metadata");
    }
    result = Run(Google(), @[HTML(publicForm), HTML(publicForm)], NO);
    CHECK(!result.url && result.error && Requests.count == 2, "confirmation loop not stopped");
    result = Run(Google(), @[@{@"redirect": @"https://download.googleusercontent.com/public-file"}, Binary()], NO);
    CHECK([result.url.host isEqual:@"download.googleusercontent.com"] && !result.error && Requests.count == 2, "ordinary Google provider redirect refused");
    for (NSString *redirect in @[@"http://drive.usercontent.google.com/download", @"https://accounts.google.com/ServiceLogin", @"https://evil.example/file"]) {
      result = Run(Google(), @[@{@"redirect": redirect}], NO);
      CHECK(!result.url && result.error && Requests.count == 1, "off-provider, sign-in or HTTPS downgrade redirect followed");
    }
    result = Run(Google(), @[@{@"type": @"application/octet-stream", @"headers": @{@"Content-Length": @"101"}}], NO);
    CHECK([result.error.userInfo[@"key"] isEqual:@"changed"], "changed binary size not refused");
    result = Run(Google(), @[@{@"type": @"text/html", @"headers": @{@"Content-Length": @"1048577"}}], NO);
    CHECK(!result.url && result.error && SentBytes == 0, "oversized declared metadata body not stopped at headers");
    result = Run(Google(), @[@{@"type": @"text/html", @"unknownLength": @YES, @"chunks": @[[NSMutableData dataWithLength:800000], [NSMutableData dataWithLength:300000]]}], NO);
    CHECK(!result.url && [result.error.userInfo[@"key"] isEqual:@"htmlPage"], "chunked metadata exceeds limit without refusal");

    NSDictionary *metadata = @{@"type": @"file", @"size": @100, @"sha256": Digest(), @"name": @"pack.rar"};
    NSString *href = @"https://downloader.disk.yandex.ru/disk/public-file?filename=pack.rar&token=temporary";
    result = Run(Yandex(), @[JSON(metadata), JSON(@{@"href": href})], NO);
    CHECK([result.url.absoluteString isEqual:href] && !result.error && Requests.count == 2, "Yandex public file link not resolved");
    CHECK([Query(Requests.firstObject.URL)[@"public_key"] isEqual:Yandex()[@"url"]], "Yandex original public key changed");
    for (NSDictionary *bad in @[
      @{@"type": @"dir", @"size": @100}, @{@"type": @"file", @"size": @101},
      @{@"type": @"file", @"size": @100, @"sha256": @"wrong"}, @{@"error": @"DownloadLimitExceeded"}
    ]) {
      result = Run(Yandex(), @[JSON(bad)], NO);
      CHECK(!result.url && result.error && Requests.count == 1, "Yandex changed/folder/restricted object followed");
    }
    for (NSString *url in @[@"http://downloader.disk.yandex.ru/file", @"https://yandex.ru.evil.example/file", @"https://evil.example/file", @"https://user:password@downloader.disk.yandex.ru/file"]) {
      result = Run(Yandex(), @[JSON(metadata), JSON(@{@"href": url})], NO);
      CHECK(!result.url && result.error && Requests.count == 2, "Yandex untrusted download followed");
    }
    result = Run(Google(), @[@{@"stall": @YES}], YES);
    CHECK([result.error.userInfo[@"key"] isEqual:@"cancelled"], "explicit cancellation not reported");
    result = Run(Changed(Google(), @"provider", @"unknown"), @[], NO);
    CHECK(!result.url && result.error && Requests.count == 0, "invalid provider reached network");

    printf("Public host resolver: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
  }
}

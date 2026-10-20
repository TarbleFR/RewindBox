// SPDX-License-Identifier: GPL-3.0-or-later
#import "NeoTextureHostResolver.h"
#import <CoreFoundation/CoreFoundation.h>

static const NSUInteger MetadataLimit = 1 << 20;
static const unsigned long long MaximumArchiveBytes = 64ULL << 30;

static NSString *String(id value) {
  return [value isKindOfClass:NSString.class] ? value : @"";
}

static BOOL Matches(NSString *value, NSString *pattern) {
  NSRange range = [value rangeOfString:pattern options:NSRegularExpressionSearch];
  return range.location != NSNotFound && (![pattern hasPrefix:@"^"] ||
      (range.location == 0 && range.length == value.length));
}

static NSError *HostError(NSString *key, NSString *message) {
  return [NSError errorWithDomain:@"NeoTextureHostResolver" code:1
      userInfo:@{@"key": key, NSLocalizedDescriptionKey: message}];
}

static NSError *HTTPError(NSInteger status, NSString *message) {
  return [NSError errorWithDomain:@"NeoTextureHostResolver" code:1
      userInfo:@{@"key": @"network", @"status": @(status), NSLocalizedDescriptionKey: message}];
}

static BOOL HTTPS(NSURL *url) {
  return url && [url.scheme.lowercaseString isEqual:@"https"] && url.host.length &&
      !url.user.length && !url.password.length && (!url.port || url.port.integerValue == 443);
}

static BOOL GoogleSourceHost(NSString *host) {
  return [@[@"drive.google.com", @"docs.google.com", @"drive.usercontent.google.com"] containsObject:host.lowercaseString];
}

static BOOL GoogleTransportURL(NSURL *url) {
  NSString *host = url.host.lowercaseString;
  return HTTPS(url) && (GoogleSourceHost(host) || [host hasSuffix:@".googleusercontent.com"]);
}

static BOOL YandexDownloadURL(NSURL *url) {
  NSString *host = url.host.lowercaseString;
  return HTTPS(url) && ([host hasSuffix:@".yandex.ru"] || [host hasSuffix:@".yandex.net"]);
}

static NSString *QueryValue(NSURL *url, NSString *key, BOOL *valid) {
  NSString *value = nil;
  for (NSURLQueryItem *item in [NSURLComponents componentsWithURL:url resolvingAgainstBaseURL:NO].queryItems) {
    if (![item.name isEqual:key]) continue;
    if (value != nil || item.value == nil) { *valid = NO; return nil; }
    value = item.value;
  }
  return value;
}

static NSString *GoogleFileID(NSURL *url, NSString **resourceKey) {
  if (!HTTPS(url) || !GoogleSourceHost(url.host) || [url.path containsString:@"/folders/"]) return nil;
  BOOL valid = YES;
  NSString *queryID = QueryValue(url, @"id", &valid);
  NSString *key = QueryValue(url, @"resourcekey", &valid);
  if (!valid || (key && !Matches(key, @"^[A-Za-z0-9_-]{1,256}$"))) return nil;
  NSRegularExpression *pattern = [NSRegularExpression regularExpressionWithPattern:@"^/file/d/([A-Za-z0-9_-]{10,256})(?:/.*)?$" options:0 error:nil];
  NSTextCheckingResult *match = [pattern firstMatchInString:url.path options:0 range:NSMakeRange(0, url.path.length)];
  if (match && NSMaxRange(match.range) != url.path.length) return nil;
  NSString *pathID = match ? [url.path substringWithRange:[match rangeAtIndex:1]] : nil;
  NSString *fileID = pathID ?: queryID;
  // A path and query may not disagree about the shared file being requested.
  if (!Matches(fileID ?: @"", @"^[A-Za-z0-9_-]{10,256}$") ||
      (pathID && queryID && ![pathID isEqual:queryID])) return nil;
  if (!pathID && ![@[@"/uc", @"/u/0/uc", @"/open", @"/download"] containsObject:url.path]) return nil;
  if (resourceKey) *resourceKey = key;
  return fileID;
}

static BOOL ValidSize(id value) {
  if (![value isKindOfClass:NSNumber.class] || CFGetTypeID((__bridge CFTypeRef)value) == CFBooleanGetTypeID()) return NO;
  unsigned long long n = [value unsignedLongLongValue];
  return n > 0 && n <= MaximumArchiveBytes && [value doubleValue] == (double)n;
}

BOOL NeoTexValidHostPart(NSDictionary *part) {
  if (![part isKindOfClass:NSDictionary.class] || !ValidSize(part[@"size"]) ||
      !Matches(String(part[@"sha256"]), @"^[A-Fa-f0-9]{64}$")) return NO;
  NSURL *url = [NSURL URLWithString:String(part[@"url"])];
  if (!HTTPS(url)) return NO;
  NSString *provider = String(part[@"provider"]);
  if ([provider isEqual:@"gdrive"]) return GoogleFileID(url, NULL) != nil;
  if ([provider isEqual:@"yandex"]) {
    return [@[@"disk.yandex.ru", @"disk.yandex.com", @"yadi.sk"] containsObject:url.host.lowercaseString] &&
        Matches(url.path, @"^/[di]/[A-Za-z0-9_-]{6,256}/?$") && !url.query.length && !url.fragment.length;
  }
  return NO;
}

static NSURL *URLWithQuery(NSString *base, NSArray<NSURLQueryItem *> *items) {
  NSURLComponents *components = [NSURLComponents componentsWithString:base];
  components.queryItems = items;
  return components.URL;
}

static NSString *HTMLUnescape(NSString *value) {
  // The form fields are deliberately restricted ASCII tokens below. Decode only
  // ordinary attribute entities, then reject unknown/entity-bearing values.
  NSDictionary *entities = @{@"&amp;": @"&", @"&quot;": @"\"", @"&#39;": @"'", @"&#x27;": @"'", @"&lt;": @"<", @"&gt;": @">"};
  for (NSString *entity in entities) value = [value stringByReplacingOccurrencesOfString:entity withString:entities[entity]];
  return value;
}

static NSDictionary *Attributes(NSString *tag) {
  NSRegularExpression *regex = [NSRegularExpression regularExpressionWithPattern:
      @"([A-Za-z_:][A-Za-z0-9_.:-]*)\\s*=\\s*(?:\"([^\"]*)\"|'([^']*)')" options:0 error:nil];
  NSMutableDictionary *values = [NSMutableDictionary dictionary];
  for (NSTextCheckingResult *match in [regex matchesInString:tag options:0 range:NSMakeRange(0, tag.length)]) {
    NSString *name = [[tag substringWithRange:[match rangeAtIndex:1]] lowercaseString];
    NSRange range = [match rangeAtIndex:2].location != NSNotFound ? [match rangeAtIndex:2] : [match rangeAtIndex:3];
    if (values[name]) return nil; // ambiguous duplicate attributes are never followed
    values[name] = HTMLUnescape([tag substringWithRange:range]);
  }
  return values;
}

static BOOL ProtectedPage(NSString *html) {
  // Public download pages can include ordinary account-navigation links. A
  // ServiceLogin/signin URL alone is not an access wall: only a validated public
  // download form may be followed below, and actual denial/quota/challenge text
  // still ends resolution without a second request.
  return Matches(html, @"(?i)(cf-chl|challenge-platform|captcha|checking your browser|enable javascript and cookies|"
      "too many users have viewed or downloaded|download quota|quota exceeded|bandwidth limit exceeded|"
      "transfer quota|over quota|rate limit|sign in to continue|you need permission|you need access|"
      "you (?:do not|don't) have (?:permission|access)|access denied)");
}

static NSURL *GoogleConfirmation(NSString *html, NSString *fileID, NSString *resourceKey) {
  if (ProtectedPage(html)) return nil;
  NSRegularExpression *forms = [NSRegularExpression regularExpressionWithPattern:@"<form\\b([^>]*)>(.*?)</form\\s*>"
      options:NSRegularExpressionCaseInsensitive | NSRegularExpressionDotMatchesLineSeparators error:nil];
  NSDictionary *selected = nil;
  NSString *contents = nil;
  for (NSTextCheckingResult *match in [forms matchesInString:html options:0 range:NSMakeRange(0, html.length)]) {
    NSDictionary *attributes = Attributes([html substringWithRange:[match rangeAtIndex:1]]);
    if (![attributes[@"id"] isEqual:@"download-form"]) continue;
    if (selected) return nil;
    selected = attributes;
    contents = [html substringWithRange:[match rangeAtIndex:2]];
  }
  if (!selected || (String(selected[@"method"]).length && ![String(selected[@"method"]).lowercaseString isEqual:@"get"])) return nil;
  NSURL *action = [NSURL URLWithString:String(selected[@"action"])];
  if (!HTTPS(action) || ![action.host.lowercaseString isEqual:@"drive.usercontent.google.com"] ||
      ![action.path isEqual:@"/download"] || action.query.length || action.fragment.length) return nil;
  NSRegularExpression *inputs = [NSRegularExpression regularExpressionWithPattern:@"<input\\b[^>]*>"
      options:NSRegularExpressionCaseInsensitive error:nil];
  NSMutableDictionary *fields = [NSMutableDictionary dictionary];
  NSSet *allowed = [NSSet setWithArray:@[@"id", @"export", @"confirm", @"uuid", @"resourcekey"]];
  for (NSTextCheckingResult *match in [inputs matchesInString:contents options:0 range:NSMakeRange(0, contents.length)]) {
    NSDictionary *attributes = Attributes([contents substringWithRange:match.range]);
    if (![String(attributes[@"type"]).lowercaseString isEqual:@"hidden"]) continue;
    NSString *name = String(attributes[@"name"]), *value = String(attributes[@"value"]);
    if (![allowed containsObject:name]) continue;
    if (fields[name] || !Matches(value, @"^[A-Za-z0-9_-]{1,256}$")) return nil;
    fields[name] = value;
  }
  if (![fields[@"id"] isEqual:fileID] || ![fields[@"export"] isEqual:@"download"] || !String(fields[@"confirm"]).length) return nil;
  if (resourceKey.length) {
    if (fields[@"resourcekey"] && ![fields[@"resourcekey"] isEqual:resourceKey]) return nil;
    fields[@"resourcekey"] = resourceKey;
  }
  NSMutableArray *query = [NSMutableArray array];
  for (NSString *key in [[fields allKeys] sortedArrayUsingSelector:@selector(compare:)])
    [query addObject:[NSURLQueryItem queryItemWithName:key value:fields[key]]];
  return URLWithQuery(@"https://drive.usercontent.google.com/download", query);
}

typedef NS_ENUM(NSUInteger, HostPhase) { GoogleInitial, GoogleConfirmed, YandexMetadata, YandexLink };

@interface NeoTexPublicHostRequest : NSObject <NeoTexHostResolution, NSURLSessionDataDelegate>
@property(nonatomic, copy) NSDictionary *part;
@property(nonatomic, copy) void (^completion)(NSURL *, NSError *);
@property(nonatomic, strong) NSURLSession *session;
@property(nonatomic, strong) NSOperationQueue *queue;
@property(nonatomic, strong) NSURLSessionDataTask *task;
@property(nonatomic, strong) NSMutableData *body;
@property(nonatomic, copy) NSString *fileID;
@property(nonatomic, copy) NSString *resourceKey;
@property(nonatomic, strong) NSError *failure;
@property(nonatomic) HostPhase phase;
@property(nonatomic) NSUInteger redirects;
@property(nonatomic) BOOL finished;
- (void)start;
@end

@implementation NeoTexPublicHostRequest
- (void)finishURL:(NSURL *)url error:(NSError *)error {
  if (self.finished) return;
  self.finished = YES;
  void (^completion)(NSURL *, NSError *) = self.completion;
  self.completion = nil;
  [self.task cancel];
  self.task = nil;
  [self.session invalidateAndCancel];
  self.session = nil;
  if (completion) completion(url, error);
}

- (void)cancel {
  [self.queue addOperationWithBlock:^{
    [self finishURL:nil error:HostError(@"cancelled", @"Public-file resolution cancelled")];
  }];
}

- (void)get:(NSURL *)url {
  if (self.finished) return;
  self.failure = nil;
  self.body = [NSMutableData data];
  NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:url cachePolicy:NSURLRequestReloadIgnoringLocalCacheData timeoutInterval:30];
  [request setValue:@"NeoStation-iOS" forHTTPHeaderField:@"User-Agent"];
  [request setValue:@"identity" forHTTPHeaderField:@"Accept-Encoding"];
  self.task = [self.session dataTaskWithRequest:request];
  [self.task resume];
}

- (NSURL *)yandexURL:(BOOL)download {
  return URLWithQuery(download ? @"https://cloud-api.yandex.net/v1/disk/public/resources/download" : @"https://cloud-api.yandex.net/v1/disk/public/resources",
      @[[NSURLQueryItem queryItemWithName:@"public_key" value:self.part[@"url"]]]);
}

- (void)start {
  if (self.finished) return;
  if (!NeoTexValidHostPart(self.part)) {
    [self finishURL:nil error:HostError(@"network", @"Invalid public-file descriptor")];
    return;
  }
  if ([self.part[@"provider"] isEqual:@"gdrive"]) {
    NSString *resourceKey = nil;
    self.fileID = GoogleFileID([NSURL URLWithString:self.part[@"url"]], &resourceKey);
    self.resourceKey = resourceKey;
    self.phase = GoogleInitial;
    NSMutableArray *query = [NSMutableArray arrayWithArray:@[[NSURLQueryItem queryItemWithName:@"id" value:self.fileID],
        [NSURLQueryItem queryItemWithName:@"export" value:@"download"]]];
    if (resourceKey.length) [query addObject:[NSURLQueryItem queryItemWithName:@"resourcekey" value:resourceKey]];
    [self get:URLWithQuery(@"https://drive.usercontent.google.com/download", query)];
  } else {
    self.phase = YandexMetadata;
    [self get:[self yandexURL:NO]];
  }
}

- (void)URLSession:(NSURLSession *)session dataTask:(NSURLSessionDataTask *)task didReceiveResponse:(NSURLResponse *)response
 completionHandler:(void (^)(NSURLSessionResponseDisposition))completionHandler {
  if (self.finished) { completionHandler(NSURLSessionResponseCancel); return; }
  NSHTTPURLResponse *http = [response isKindOfClass:NSHTTPURLResponse.class] ? (NSHTTPURLResponse *)response : nil;
  NSString *type = [[http valueForHTTPHeaderField:@"Content-Type"] lowercaseString] ?: @"";
  BOOL google = self.phase == GoogleInitial || self.phase == GoogleConfirmed;
  BOOL providerURL = google ? GoogleTransportURL(response.URL) : HTTPS(response.URL) && [response.URL.host.lowercaseString isEqual:@"cloud-api.yandex.net"];
  if (!http || http.statusCode != 200 || !providerURL) {
    NSString *message = http ? [NSString stringWithFormat:@"Public file host refused the request (HTTP %ld)", (long)http.statusCode] : @"Invalid public-file response";
    self.failure = http ? HTTPError(http.statusCode, message) : HostError(@"network", message);
    completionHandler(NSURLSessionResponseCancel);
    [self finishURL:nil error:self.failure];
    return;
  }
  BOOL html = [type hasPrefix:@"text/html"] || [type hasPrefix:@"application/xhtml+xml"];
  if (google && !html) {
    if ([type hasPrefix:@"text/"] || [type containsString:@"json"]) {
      self.failure = HostError(@"htmlPage", @"The public file host returned a message instead of an archive");
    } else if (response.expectedContentLength >= 0 && (unsigned long long)response.expectedContentLength != [self.part[@"size"] unsignedLongLongValue]) {
      self.failure = HostError(@"changed", @"The public file size differs from the verified archive");
    }
    // Stop at headers: a resolver must not buffer or download a multi-GB archive.
    completionHandler(NSURLSessionResponseCancel);
    [self finishURL:self.failure ? nil : response.URL error:self.failure];
    return;
  }
  if ((!google && html) || (response.expectedContentLength >= 0 && (unsigned long long)response.expectedContentLength > MetadataLimit)) {
    self.failure = HostError(@"htmlPage", @"The host metadata is not a bounded public-file response");
    completionHandler(NSURLSessionResponseCancel);
    [self finishURL:nil error:self.failure];
    return;
  }
  completionHandler(NSURLSessionResponseAllow);
}

- (void)URLSession:(NSURLSession *)session dataTask:(NSURLSessionDataTask *)task didReceiveData:(NSData *)data {
  if (self.finished) return;
  if (data.length > MetadataLimit - self.body.length) {
    [self finishURL:nil error:HostError(@"htmlPage", @"The public host metadata exceeds its size limit")];
    return;
  }
  [self.body appendData:data];
}

- (void)URLSession:(NSURLSession *)session task:(NSURLSessionTask *)task willPerformHTTPRedirection:(NSHTTPURLResponse *)response
        newRequest:(NSURLRequest *)request completionHandler:(void (^)(NSURLRequest *))completionHandler {
  BOOL google = self.phase == GoogleInitial || self.phase == GoogleConfirmed;
  BOOL allowed = google ? GoogleTransportURL(request.URL) : HTTPS(request.URL) && [request.URL.host.lowercaseString isEqual:@"cloud-api.yandex.net"];
  if (self.finished || ++self.redirects > 8 || !allowed) {
    completionHandler(nil);
    [self finishURL:nil error:HostError(@"network", @"The public host redirected outside its HTTPS provider")];
    return;
  }
  completionHandler(request);
}

- (void)URLSession:(NSURLSession *)session task:(NSURLSessionTask *)task didReceiveChallenge:(NSURLAuthenticationChallenge *)challenge
 completionHandler:(void (^)(NSURLSessionAuthChallengeDisposition, NSURLCredential *))completionHandler {
  // TLS trust uses the operating system's ordinary certificate validation;
  // every account/password/client-certificate challenge is refused.
  if ([challenge.protectionSpace.authenticationMethod isEqual:NSURLAuthenticationMethodServerTrust])
    completionHandler(NSURLSessionAuthChallengePerformDefaultHandling, nil);
  else
    completionHandler(NSURLSessionAuthChallengeCancelAuthenticationChallenge, nil);
}

- (void)URLSession:(NSURLSession *)session task:(NSURLSessionTask *)task didCompleteWithError:(NSError *)error {
  if (self.finished) return;
  if (error) {
    [self finishURL:nil error:HostError(error.code == NSURLErrorCancelled ? @"cancelled" : @"network", error.localizedDescription)];
    return;
  }
  if (self.phase == GoogleInitial || self.phase == GoogleConfirmed) {
    NSString *html = [[NSString alloc] initWithData:self.body encoding:NSUTF8StringEncoding];
    NSURL *url = self.phase == GoogleInitial && html ? GoogleConfirmation(html, self.fileID, self.resourceKey) : nil;
    if (!url) {
      [self finishURL:nil error:HostError(@"htmlPage", @"The original public file requires access, quota or a supported download form")];
      return;
    }
    self.phase = GoogleConfirmed;
    [self get:url];
    return;
  }
  id parsed = [NSJSONSerialization JSONObjectWithData:self.body options:0 error:nil];
  NSDictionary *json = [parsed isKindOfClass:NSDictionary.class] ? parsed : nil;
  if (!json || json[@"error"]) {
    NSError *failure = HostError(@"htmlPage", @"The original public file is unavailable or restricted");
    NSString *providerCode = String(json[@"error"]);
    if (Matches(providerCode, @"^[A-Za-z0-9_-]{1,128}$")) {
      NSMutableDictionary *info = [failure.userInfo mutableCopy];
      info[@"provider_code"] = providerCode;
      failure = [NSError errorWithDomain:failure.domain code:failure.code userInfo:info];
    }
    [self finishURL:nil error:failure];
    return;
  }
  if (self.phase == YandexMetadata) {
    NSString *digest = String(json[@"sha256"]);
    if (![json[@"type"] isEqual:@"file"] || !ValidSize(json[@"size"]) ||
        [json[@"size"] unsignedLongLongValue] != [self.part[@"size"] unsignedLongLongValue] ||
        (digest.length && ![digest.lowercaseString isEqual:String(self.part[@"sha256"]).lowercaseString])) {
      [self finishURL:nil error:HostError(@"changed", @"Yandex metadata differs from the verified single archive")];
      return;
    }
    self.phase = YandexLink;
    [self get:[self yandexURL:YES]];
  } else {
    NSURL *url = [NSURL URLWithString:String(json[@"href"])];
    if (!YandexDownloadURL(url)) {
      [self finishURL:nil error:HostError(@"network", @"Yandex returned no HTTPS provider download")];
      return;
    }
    [self finishURL:url error:nil];
  }
}
@end

id<NeoTexHostResolution> NeoTexResolveHostPartWithConfiguration(NSDictionary *part, NSURLSessionConfiguration *configuration,
    void (^completion)(NSURL *, NSError *)) {
  NeoTexPublicHostRequest *request = [NeoTexPublicHostRequest new];
  request.part = [part copy];
  request.completion = completion;
  request.queue = [NSOperationQueue new];
  request.queue.maxConcurrentOperationCount = 1;
  NSURLSessionConfiguration *settings = [configuration copy];
  settings.timeoutIntervalForRequest = 30;
  settings.timeoutIntervalForResource = 90;
  settings.URLCache = nil;
  settings.HTTPCookieStorage = nil;
  settings.HTTPShouldSetCookies = NO;
  settings.URLCredentialStorage = nil;
  request.session = [NSURLSession sessionWithConfiguration:settings delegate:request delegateQueue:request.queue];
  [request.queue addOperationWithBlock:^{ [request start]; }];
  return request;
}

id<NeoTexHostResolution> NeoTexResolveHostPart(NSDictionary *part, void (^completion)(NSURL *, NSError *)) {
  return NeoTexResolveHostPartWithConfiguration(part, NSURLSessionConfiguration.ephemeralSessionConfiguration, completion);
}

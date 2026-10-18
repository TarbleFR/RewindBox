// SPDX-License-Identifier: GPL-3.0-or-later
#import "Public/NeoUnifiedCheatCatalog.h"
#import <CommonCrypto/CommonDigest.h>
#import <zlib.h>

NSString *const NeoUnifiedCheatCatalogErrorDomain = @"NeoUnifiedCheatCatalog";
NSNotificationName const NeoUnifiedCheatCatalogDidInstallNotification = @"NeoUnifiedCheatCatalogDidInstallNotification";
NSNotificationName const NeoUnifiedCheatCatalogProgressNotification = @"NeoUnifiedCheatCatalogProgressNotification";
static const NSUInteger ManifestLimit = 64 * 1024 * 1024;
static const NSUInteger ManifestCompressedLimit = 12 * 1024 * 1024;
static const NSUInteger PackLimit = 8 * 1024 * 1024;
static const NSUInteger ExpansionLimit = 16 * 1024 * 1024;
static const NSUInteger ChunkLimit = 2 * 1024 * 1024;

static NSError *Failure(NSInteger code, NSString *message) {
  return [NSError errorWithDomain:NeoUnifiedCheatCatalogErrorDomain code:code
                        userInfo:@{NSLocalizedDescriptionKey:message ?: @"Catalogue unavailable"}];
}
static NSString *String(id value) { return [value isKindOfClass:NSString.class] ? value : @""; }
static NSArray *Array(id value) { return [value isKindOfClass:NSArray.class] ? value : @[]; }
static BOOL SafeID(id value) {
  NSString *s = String(value);
  if (!s.length || s.length > 160) return NO;
  static NSCharacterSet *invalid;static dispatch_once_t once;
  dispatch_once(&once,^{invalid=[NSCharacterSet characterSetWithCharactersInString:
    @"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-."] .invertedSet;});
  return [s rangeOfCharacterFromSet:invalid].location == NSNotFound &&
    ![s isEqualToString:@"."] && ![s isEqualToString:@".."];
}
static BOOL SafePath(id value) {
  NSString *s = String(value);
  static NSCharacterSet *invalid;static dispatch_once_t once;
  dispatch_once(&once,^{invalid=[NSCharacterSet characterSetWithCharactersInString:@"\\%?#:"];});
  if (!s.length || s.length > 512 || [s hasPrefix:@"/"] ||
      [s rangeOfCharacterFromSet:invalid].location != NSNotFound ||
      [s rangeOfCharacterFromSet:NSCharacterSet.controlCharacterSet].location != NSNotFound) return NO;
  for (NSString *p in [s componentsSeparatedByString:@"/"]) if (!SafeID(p)) return NO;
  return YES;
}
static BOOL SHA(id value) {
  NSString *s = String(value);
  static NSCharacterSet *invalid;static dispatch_once_t once;
  dispatch_once(&once,^{invalid=[NSCharacterSet characterSetWithCharactersInString:@"0123456789abcdefABCDEF"].invertedSet;});
  return s.length == 64 && [s rangeOfCharacterFromSet:invalid].location == NSNotFound;
}
static BOOL NUCCatalogSizeIsValid(id value, NSUInteger limit, BOOL zero) {
  return [value isKindOfClass:NSNumber.class] && [value doubleValue] == [value unsignedLongLongValue] &&
    [value unsignedLongLongValue] <= limit && (zero || [value unsignedLongLongValue] > 0);
}
static NSString *Digest(NSData *data) {
  unsigned char digest[CC_SHA256_DIGEST_LENGTH];
  CC_SHA256(data.bytes, (CC_LONG)data.length, digest);
  NSMutableString *s = [NSMutableString stringWithCapacity:64];
  for (NSUInteger i=0; i<sizeof(digest); i++) [s appendFormat:@"%02x",digest[i]];
  return s;
}
static NSDictionary *JSON(NSData *data) {
  id j = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
  return [j isKindOfClass:NSDictionary.class] ? j : nil;
}
static NSData *JSONData(id object) {
  return [NSJSONSerialization dataWithJSONObject:object options:NSJSONWritingSortedKeys error:nil];
}
static BOOL RegularPath(NSString *path) {
  return [[NSFileManager.defaultManager attributesOfItemAtPath:path error:nil].fileType isEqualToString:NSFileTypeRegular];
}
/// Reject links anywhere below root. Content-addressed paths are otherwise
/// generated internally; manifest paths are never used as destination paths.
static BOOL EnsureDirectory(NSString *root) {
  NSString *path = root.stringByStandardizingPath;
  NSArray *parts = path.pathComponents;
  NSString *current = @"/";
  for (NSString *part in parts) {
    if ([part isEqualToString:@"/"]) continue;
    current = [current stringByAppendingPathComponent:part];
    NSDictionary *attrs = [NSFileManager.defaultManager attributesOfItemAtPath:current error:nil];
    if (attrs && ![attrs.fileType isEqualToString:NSFileTypeDirectory]) {
      // Apple's /var and /tmp are system links on macOS/iOS. Never permit
      // links inside the application-controlled catalogue tree.
      // Foundation path resolution may strip /private again, so inspect the
      // actual link text rather than comparing standardized/resolved paths.
      NSString *destination=[NSFileManager.defaultManager destinationOfSymbolicLinkAtPath:current error:nil];
      BOOL systemLink = destination.length && [attrs.fileType isEqualToString:NSFileTypeSymbolicLink] &&
        (([current isEqualToString:@"/var"] && ([@[@"private/var",@"/private/var"] containsObject:destination])) ||
         ([current isEqualToString:@"/tmp"] && ([@[@"private/tmp",@"/private/tmp"] containsObject:destination])));
      if (!systemLink) return NO;
    }
    if (!attrs && ![NSFileManager.defaultManager createDirectoryAtPath:current withIntermediateDirectories:NO attributes:nil error:nil]) {
      // Another bounded pack worker may have created the same directory.
      if (![[NSFileManager.defaultManager attributesOfItemAtPath:current error:nil].fileType isEqualToString:NSFileTypeDirectory]) return NO;
    }
  }
  return YES;
}
static NSData *ReadBounded(NSString *path, NSUInteger limit) {
  if (!RegularPath(path)) return nil;
  NSDictionary *attrs = [NSFileManager.defaultManager attributesOfItemAtPath:path error:nil];
  if (attrs.fileSize > limit) return nil;
  NSData *d = [NSData dataWithContentsOfFile:path options:0 error:nil];
  return d.length <= limit ? d : nil;
}
static BOOL WriteAtomic(NSData *data, NSString *path, NSError **error) {
  if (!data || !EnsureDirectory(path.stringByDeletingLastPathComponent)) {
    if (error) *error = Failure(10,@"Cannot create the shared cheat directory");
    return NO;
  }
  NSDictionary *existing = [NSFileManager.defaultManager attributesOfItemAtPath:path error:nil];
  if (existing && ![existing.fileType isEqualToString:NSFileTypeRegular]) {
    if (error) *error = Failure(10,@"Refusing a non-regular catalogue file");
    return NO;
  }
  return [data writeToFile:path options:NSDataWritingAtomic error:error];
}
static NSString *Fold(NSString *s) {
  static NSLocale *locale;static dispatch_once_t once;
  dispatch_once(&once,^{locale=[NSLocale localeWithLocaleIdentifier:@"en_US_POSIX"];});
  return [[s stringByFoldingWithOptions:NSDiacriticInsensitiveSearch|NSCaseInsensitiveSearch locale:
    locale] lowercaseString];
}
static NSString *IdentityValue(NSDictionary *identity) {
  NSString *value=String(identity[@"value"]).lowercaseString;
  if ([Fold(String(identity[@"type"])) isEqual:@"serial"] &&
      [Fold(String(identity[@"scheme"])) isEqual:@"ps2-disc-serial"]) {
    // PCSX2 reports SLUS-20655; the reviewed PNACH index stores SLUS20655.
    // Normalize only the documented disc-serial spelling, never hash values.
    static NSRegularExpression *serial; static dispatch_once_t once;
    dispatch_once(&once,^{serial=[NSRegularExpression regularExpressionWithPattern:@"^[a-z]{4}[-_.]?[0-9]{3}\\.?[0-9]{2}$" options:0 error:nil];});
    if ([serial firstMatchInString:value options:0 range:NSMakeRange(0,value.length)])
      for (NSString *separator in @[@"-",@"_",@"."]) value=[value stringByReplacingOccurrencesOfString:separator withString:@""];
  }
  return value;
}
static BOOL TitleContains(NSString *title, NSString *query) {
  NSString *haystack=Fold(title);
  NSArray *words=[Fold(query) componentsSeparatedByCharactersInSet:NSCharacterSet.alphanumericCharacterSet.invertedSet];
  BOOL any=NO;
  for(NSString *word in words)if(word.length){any=YES;if(![haystack containsString:word])return NO;}
  return any;
}
static NSArray *TitleWords(NSString *query) {
  NSMutableArray *words=[NSMutableArray array];
  for(NSString *word in [Fold(query) componentsSeparatedByCharactersInSet:NSCharacterSet.alphanumericCharacterSet.invertedSet])
    if(word.length)[words addObject:word];
  return words;
}
static BOOL FoldedTitleContains(NSString *title,NSArray *words) {
  if(!words.count)return NO;
  for(NSString *word in words)if(![title containsString:word])return NO;
  return YES;
}
/// Cheap allocation-free prefilter. Full semantic matching still decides the
/// result, including contradictory schemes, revisions and regions.
static BOOL RawIdentityOverlap(NSDictionary *game,NSArray *requested) {
  for(id left in Array(game[@"identities"])) {
    if(![left isKindOfClass:NSDictionary.class])continue;
    for(id right in requested) {
      if(![right isKindOfClass:NSDictionary.class])continue;
      if([String(left[@"type"]) caseInsensitiveCompare:String(right[@"type"])]==NSOrderedSame &&
         [String(left[@"scheme"]) caseInsensitiveCompare:String(right[@"scheme"])]==NSOrderedSame &&
         IdentityValue(left).length && [IdentityValue(left) isEqual:IdentityValue(right)])return YES;
    }
  }
  return NO;
}
static NSString *System(id value) {
  NSString *s = Fold(String(value));
  static NSDictionary *aliases;static dispatch_once_t once;
  dispatch_once(&once,^{aliases = @{@"gameboy":@"gb",@"gameboycolor":@"gbc",@"gameboyadvance":@"gba",
    @"nintendo_ds":@"nds",@"ds":@"nds",@"playstation":@"psx",@"ps1":@"psx",
    @"gamecube":@"gc",@"genesis":@"md",@"mega_drive":@"md",@"megadrive":@"md",
    @"master_system":@"sms",@"gamegear":@"gg",@"nintendo64":@"n64",@"n3ds":@"3ds"};});
  return aliases[s] ?: s;
}
static NSSet *Labels(id input, BOOL region) {
  NSArray *items = [input isKindOfClass:NSString.class] ? @[input] : Array(input);
  NSMutableSet *set = [NSMutableSet set];
  NSDictionary *aliases = region ? @{@"us":@"usa",@"u":@"usa",@"united states":@"usa",
    @"eur":@"europe",@"eu":@"europe",@"pal":@"europe",@"e":@"europe",
    @"fr":@"france",@"f":@"france",@"jp":@"japan",@"j":@"japan",@"jpn":@"japan",
    @"w":@"world",@"global":@"world"} : @{@"french":@"fr",@"francais":@"fr",@"fra":@"fr",
    @"english":@"en",@"eng":@"en",@"german":@"de",@"deu":@"de",@"japanese":@"ja",@"jpn":@"ja",
    @"spanish":@"es",@"italian":@"it"};
  for (id item in items) { NSString *s = Fold(String(item)); if (s.length && ![s isEqualToString:@"unknown"]) [set addObject:aliases[s] ?: s]; }
  return set;
}
static BOOL LabelConflict(NSSet *a, NSSet *b, BOOL region) {
  if (!a.count || !b.count) return NO;
  if ([a intersectsSet:b]) return NO;
  // France is a more precise European release, but Europe alone never proves
  // a French language. Language compatibility is evaluated independently.
  if (region && (([a containsObject:@"europe"] && [b containsObject:@"france"]) ||
                 ([b containsObject:@"europe"] && [a containsObject:@"france"]))) return NO;
  if (region && ([a containsObject:@"world"] || [b containsObject:@"world"])) return NO;
  return YES;
}
static NSString *Revision(id v) {
  NSString *s = [v isKindOfClass:NSNumber.class] ? [v stringValue] : Fold(String(v));
  s = [s stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
  if (!s.length || [s isEqualToString:@"unknown"] || [s isEqualToString:@"unspecified"]) return @"";
  static NSRegularExpression *cartridgeRevision;
  static dispatch_once_t once;
  dispatch_once(&once,^{cartridgeRevision=[NSRegularExpression regularExpressionWithPattern:@"^rev(?:ision)?[ ._-]*([0-9]+)$" options:0 error:nil];});
  NSTextCheckingResult *match=[cartridgeRevision firstMatchInString:s options:0 range:NSMakeRange(0,s.length)];
  if(match)return [s substringWithRange:[match rangeAtIndex:1]];
  return s;
}
static NSDictionary *Identities(id value) {
  NSMutableDictionary *result = [NSMutableDictionary dictionary];
  for (id row in Array(value)) {
    if (![row isKindOfClass:NSDictionary.class]) continue;
    NSString *type = Fold(String(row[@"type"])), *scheme = Fold(String(row[@"scheme"]));
    NSString *v = IdentityValue(row);
    if (!type.length || !scheme.length || !v.length || type.length>64 || scheme.length>100 || v.length>256) continue;
    NSString *key = [NSString stringWithFormat:@"%@|%@",type,scheme];
    if (!result[key]) result[key] = [NSMutableSet set];
    [result[key] addObject:v];
  }
  return result;
}
static NSData *InflateBounded(NSData *data, NSUInteger expected, NSUInteger limit, NSError **error) {
  if (!expected || expected > limit || data.length > (limit==ManifestLimit ? ManifestCompressedLimit : PackLimit)) {
    if (error) *error = Failure(6,@"Pack exceeds its expansion limit"); return nil;
  }
  z_stream stream = {0};
  stream.next_in = (Bytef *)data.bytes; stream.avail_in = (uInt)data.length;
  if (inflateInit2(&stream, 16+MAX_WBITS) != Z_OK) {
    if (error) *error = Failure(6,@"Cannot open gzip pack"); return nil;
  }
  NSMutableData *out = [NSMutableData dataWithLength:expected];
  stream.next_out = out.mutableBytes; stream.avail_out = (uInt)expected;
  int code = inflate(&stream, Z_FINISH);
  BOOL good = code == Z_STREAM_END && stream.total_out == expected && stream.avail_in == 0;
  inflateEnd(&stream);
  if (!good) { if (error) *error = Failure(6,@"Invalid gzip pack or expansion size"); return nil; }
  return out;
}
static NSData *Inflate(NSData *data, NSUInteger expected, NSError **error) {
  return InflateBounded(data,expected,ExpansionLimit,error);
}

#pragma mark - Bounded HTTPS transport
@interface NeoCheatHTTPSRequest : NSObject <NSURLSessionDataDelegate>
@property(nonatomic) NSUInteger maximum;
@property(nonatomic,strong) NSMutableData *bytes;
@property(nonatomic,strong) NSURLSession *session;
@property(nonatomic,copy) void (^completion)(NSData *,NSError *);
@property(nonatomic,strong) NSError *failure;
@end
@implementation NeoCheatHTTPSRequest
- (void)start:(NSURL *)url maximum:(NSUInteger)maximum completion:(void (^)(NSData *,NSError *))completion {
  self.maximum=maximum; self.bytes=[NSMutableData data]; self.completion=completion;
  NSURLSessionConfiguration *config=[NSURLSessionConfiguration ephemeralSessionConfiguration];
  config.timeoutIntervalForRequest=30; config.timeoutIntervalForResource=60;
  config.URLCache=nil; config.HTTPCookieStorage=nil;
  self.session=[NSURLSession sessionWithConfiguration:config delegate:self delegateQueue:nil];
  [[self.session dataTaskWithURL:url] resume];
}
- (void)URLSession:(NSURLSession *)session dataTask:(NSURLSessionDataTask *)task didReceiveResponse:(NSURLResponse *)response
 completionHandler:(void (^)(NSURLSessionResponseDisposition))completionHandler {
  NSHTTPURLResponse *http=[response isKindOfClass:NSHTTPURLResponse.class] ? (id)response : nil;
  if (!http || http.statusCode != 200 || (response.expectedContentLength>0 && (unsigned long long)response.expectedContentLength>self.maximum)) {
    self.failure=Failure(3,http.statusCode == 200 ? @"Download is too large" : [NSString stringWithFormat:@"Catalogue HTTP %ld",(long)http.statusCode]);
    completionHandler(NSURLSessionResponseCancel); return;
  }
  completionHandler(NSURLSessionResponseAllow);
}
- (void)URLSession:(NSURLSession *)session dataTask:(NSURLSessionDataTask *)task didReceiveData:(NSData *)data {
  if (data.length > self.maximum-self.bytes.length) { self.failure=Failure(3,@"Download is too large"); [task cancel]; return; }
  [self.bytes appendData:data];
}
- (void)URLSession:(NSURLSession *)session task:(NSURLSessionTask *)task willPerformHTTPRedirection:(NSHTTPURLResponse *)response
 newRequest:(NSURLRequest *)request completionHandler:(void (^)(NSURLRequest *))completionHandler {
  if (![request.URL.scheme.lowercaseString isEqualToString:@"https"] || request.URL.user.length || request.URL.password.length) {
    self.failure=Failure(3,@"Refusing an insecure catalogue redirect"); completionHandler(nil); return;
  }
  completionHandler(request);
}
- (void)URLSession:(NSURLSession *)session task:(NSURLSessionTask *)task didCompleteWithError:(NSError *)error {
  NSError *failure=self.failure ?: error;
  void (^completion)(NSData *,NSError *)=self.completion;
  self.completion=nil;
  if (completion) completion(failure ? nil : [self.bytes copy],failure);
  [session finishTasksAndInvalidate]; self.session=nil;
}
@end

@interface NeoUnifiedCheatCatalog () {
  dispatch_queue_t _queue;
  NSOperationQueue *_transportQueue;
  NSOperationQueue *_packQueue;
  NSOperationQueue *_readQueue;
  NSDictionary *_manifest;
  NSDictionary *_indexedManifest;
  NSDictionary *_gamesByID;
  NSDictionary *_packsByID;
  NSArray *_effectiveGames;
  NSDictionary *_effectiveByID;
  NSDictionary *_gamesBySystem;
  NSDictionary *_searchTitles;
  NSSet *_updates;
  NSSet *_archives;
  NSDictionary *_snapshotCache;
  NSMutableDictionary *_installed;
  NSMutableArray *_loadWaiters;
  NSMutableSet *_readyPacks;
  NSMutableArray *_installWaiters;
  NSMutableArray *_progressWaiters;
  NSMutableDictionary *_packJobs;
  BOOL _downloadRequested;
  NSDictionary *_installationProgress;
  NSTimeInterval _lastProgressNotification;
  BOOL _loading;
  BOOL _installing;
}
@end
@implementation NeoUnifiedCheatCatalog
+ (instancetype)sharedCatalog { static NeoUnifiedCheatCatalog *catalog; static dispatch_once_t once; dispatch_once(&once,^{catalog=[self new];}); return catalog; }
- (instancetype)init {
  if (!(self=[super init])) return nil;
  _queue=dispatch_queue_create("org.neostation.cheats.unified",
    dispatch_queue_attr_make_with_autorelease_frequency(DISPATCH_QUEUE_SERIAL,DISPATCH_AUTORELEASE_FREQUENCY_WORK_ITEM));
  _transportQueue=[NSOperationQueue new]; _transportQueue.maxConcurrentOperationCount=2;
  _transportQueue.qualityOfService=NSQualityOfServiceUtility;
  _packQueue=[NSOperationQueue new]; _packQueue.maxConcurrentOperationCount=2;
  _packQueue.qualityOfService=NSQualityOfServiceUtility;
  _readQueue=[NSOperationQueue new]; _readQueue.maxConcurrentOperationCount=2;
  _readQueue.qualityOfService=NSQualityOfServiceUtility;
  _manifestURL=[NSURL URLWithString:@"https://raw.githubusercontent.com/TarbleFR/neostation-ios/Claude/native/cheats/catalogue/manifest.json.gz"];
  NSString *documents=NSSearchPathForDirectoriesInDomains(NSDocumentDirectory,NSUserDomainMask,YES).firstObject ?: NSTemporaryDirectory();
  _storageDirectory=[documents stringByAppendingPathComponent:@"NeoStation/Cheats/Unified"];
  for (NSBundle *bundle in @[[NSBundle bundleForClass:self.class],NSBundle.mainBundle]) {
    NSURL *url=[bundle URLForResource:@"NeoCheatCatalog" withExtension:@"bundle"];
    NSBundle *resources=url ? [NSBundle bundleWithURL:url] : nil;
    if ([resources URLForResource:@"manifest" withExtension:@"json"] || [resources URLForResource:@"manifest.json" withExtension:@"gz"]) { _bundledDirectory=resources.resourcePath; break; }
    if ([bundle URLForResource:@"manifest" withExtension:@"json"] || [bundle URLForResource:@"manifest.json" withExtension:@"gz"]) { _bundledDirectory=bundle.resourcePath; break; }
  }
  _loadWaiters=[NSMutableArray array];
  _installWaiters=[NSMutableArray array];_progressWaiters=[NSMutableArray array];
  _packJobs=[NSMutableDictionary dictionary];
  return self;
}
+ (BOOL)gameHasConflict:(NSDictionary *)game identity:(NSDictionary *)identity {
  if (![game isKindOfClass:NSDictionary.class] || ![identity isKindOfClass:NSDictionary.class]) return YES;
  NSString *system=System(game[@"system"]), *requested=System(identity[@"system"]);
  if (system.length && requested.length && ![system isEqualToString:requested]) return YES;
  if (LabelConflict(Labels(game[@"regions"] ?: game[@"region"],YES),Labels(identity[@"regions"] ?: identity[@"region"],YES),YES) ||
      LabelConflict(Labels(game[@"languages"] ?: game[@"language"],NO),Labels(identity[@"languages"] ?: identity[@"language"],NO),NO)) return YES;
  NSString *gr=Revision(game[@"revision"]), *ir=Revision(identity[@"revision"]);
  if (gr.length && ir.length && ![gr isEqualToString:ir]) return YES;
  NSDictionary *left=Identities(game[@"identities"]), *right=Identities(identity[@"identities"]);
  for(NSString *key in left)if(right[key] && ![left[key] intersectsSet:right[key]])return YES;
  return NO;
}
+ (NSString *)matchGame:(NSDictionary *)game identity:(NSDictionary *)identity {
  if (![game isKindOfClass:NSDictionary.class] || ![identity isKindOfClass:NSDictionary.class]) return nil;
  NSString *system=System(game[@"system"]), *requested=System(identity[@"system"]);
  if (!system.length || !requested.length || ![system isEqualToString:requested] || [self gameHasConflict:game identity:identity]) return nil;
  NSString *gr=Revision(game[@"revision"]), *ir=Revision(identity[@"revision"]);
  NSDictionary *left=Identities(game[@"identities"]), *right=Identities(identity[@"identities"]);
  BOOL overlap=NO, strong=NO, serial=NO, ppu=NO, versionedID=NO, complete=YES;
  for (NSString *key in left) {
    NSSet *a=left[key], *b=right[key];
    if (!b) {complete=NO;continue;}
    if (![a intersectsSet:b]) return nil;
    overlap=YES;
    if ([key isEqualToString:@"serial|ps3-title-id"]) serial=YES;
    if ([key isEqualToString:@"serial|ps1-disc-serial"] || [key isEqualToString:@"serial|ps2-disc-serial"] ||
        [key isEqualToString:@"game_id|dolphin-disc-game-id"] || [key isEqualToString:@"game_id|psp-param-sfo-disc-id"] ||
        [key isEqualToString:@"title_id|3ds-title-id"] || [key isEqualToString:@"ds_game_code|nds-header-gamecode"]) versionedID=YES;
    if ([key isEqualToString:@"ppu_hash|rpcs3-ppu-hash"]) ppu=YES;
    if ([key isEqualToString:@"romset|fbneo-driver-name"] || [key isEqualToString:@"ps2_crc|pcsx2-executable-crc"] ||
        [key isEqualToString:@"n64_header|n64-crc1-crc2-country"] ||
        [key isEqualToString:@"executable_hash|duckstation-game-hash"] ||
        [key isEqualToString:@"md5|rom-full"] || [key isEqualToString:@"sha1|rom-full"] ||
        [key isEqualToString:@"sha256|rom-full"] || [key isEqualToString:@"crc32|rom-full"]) strong=YES;
    // Emulator-specific hashes only match the same explicitly named scheme.
    if ([key isEqualToString:@"sha1|nes-prg"] || [key isEqualToString:@"sha256|bsnes-cartridge"] ||
        [key isEqualToString:@"sha1|mesen-sha1-cheat"]) strong=YES;
  }
  if ([system isEqualToString:@"nds"] && [left[@"ds_game_code|nds-header-gamecode"] intersectsSet:right[@"ds_game_code|nds-header-gamecode"] ?: [NSSet set]] &&
      [left[@"ds_crc|r4-header512-crc32-inverted"] intersectsSet:right[@"ds_crc|r4-header512-crc32-inverted"] ?: [NSSet set]]) strong=YES;
  if ([system isEqualToString:@"ps3"]) return overlap ? ((complete && ppu && serial && gr.length && ir.length) ? @"exact" : @"candidate") : nil;
  if (complete && overlap && (strong || (versionedID && gr.length && ir.length))) return @"exact";
  if (overlap) return @"candidate";
  NSString *a=Fold(String(game[@"title"])), *b=Fold(String(identity[@"title"]));
  return a.length && b.length && (TitleContains(a,b) || TitleContains(b,a)) ? @"candidate" : nil;
}

#pragma mark - Manifest and disk index (serial I/O queue)
- (NSDictionary *)validatedManifest:(NSData *)data error:(NSError **)error {
  if (!data || data.length>ManifestLimit) { if(error)*error=Failure(1,@"Catalogue index missing or too large"); return nil; }
  const unsigned char *bytes=data.bytes;
  if(data.length>=2 && bytes[0]==0x1f && bytes[1]==0x8b) {
    if(data.length<18 || data.length>ManifestCompressedLimit){if(error)*error=Failure(1,@"Compressed catalogue index is invalid or too large");return nil;}
    NSUInteger end=data.length;
    uint32_t expanded=(uint32_t)bytes[end-4] | ((uint32_t)bytes[end-3]<<8) | ((uint32_t)bytes[end-2]<<16) | ((uint32_t)bytes[end-1]<<24);
    data=InflateBounded(data,expanded,ManifestLimit,error);
    if(!data)return nil;
  }
  NSDictionary *json=JSON(data);
  if (![json[@"schema_version"] isKindOfClass:NSNumber.class] || [json[@"schema_version"] integerValue]!=1 || !SafeID(json[@"catalogue_id"]) ||
      !String(json[@"revision"]).length || String(json[@"revision"]).length>160 ||
      ![json[@"games"] isKindOfClass:NSArray.class] || Array(json[@"games"]).count>250000 ||
      ![json[@"packs"] isKindOfClass:NSArray.class] || Array(json[@"packs"]).count>25000 || Array(json[@"sources"]).count>1024) {
    if(error)*error=Failure(1,@"Unsupported or invalid catalogue index"); return nil;
  }
  NSMutableArray *packs=[NSMutableArray array], *games=[NSMutableArray array];
  NSMutableSet *packIDs=[NSMutableSet set], *gameIDs=[NSMutableSet set];
  NSMutableDictionary *packGames=[NSMutableDictionary dictionary];
  NSUInteger rejected=0;
  for (id p in json[@"packs"]) {@autoreleasepool{
    if (![p isKindOfClass:NSDictionary.class] || !SafeID(p[@"id"]) || [packIDs containsObject:p[@"id"]] || !SafePath(p[@"path"]) ||
        !SHA(p[@"sha256"]) || !NUCCatalogSizeIsValid(p[@"size"],PackLimit,NO) || !NUCCatalogSizeIsValid(p[@"uncompressed_size"],ExpansionLimit,NO) ||
        ![p[@"game_ids"] isKindOfClass:NSArray.class] || Array(p[@"game_ids"]).count>250000) {rejected++;continue;}
    BOOL valid=YES; NSMutableSet *seen=[NSMutableSet set];
    for (id gameID in p[@"game_ids"]) {if(!SafeID(gameID)||[seen containsObject:gameID]){valid=NO;break;}[seen addObject:gameID];}
    if(!valid){rejected++;continue;}
    [packs addObject:p];[packIDs addObject:p[@"id"]];packGames[p[@"id"]]=seen;
  }}
  for (id g in json[@"games"]) {@autoreleasepool{
    NSString *pack=[g isKindOfClass:NSDictionary.class] ? String(g[@"pack_id"] ?: g[@"pack"]) : @"";
    if (![g isKindOfClass:NSDictionary.class] || !SafeID(g[@"id"]) || [gameIDs containsObject:g[@"id"]] ||
        !SafeID(g[@"system"]) || !String(g[@"title"]).length || String(g[@"title"]).length>1024 ||
        !SafePath(g[@"path"]) || !SHA(g[@"sha256"]) || !NUCCatalogSizeIsValid(g[@"size"],ChunkLimit,NO) || ![packIDs containsObject:pack] ||
        ![packGames[pack] containsObject:g[@"id"]]) {rejected++;continue;}
    NSMutableDictionary *copy=nil;
    if(![String(g[@"pack_id"]) isEqualToString:pack]){copy=[g mutableCopy];copy[@"pack_id"]=pack;}
    for(NSString *field in @[@"part",@"parts",@"cheat_count",@"available_count"])
      if(g[field] && !NUCCatalogSizeIsValid(g[field],100000000,YES)){if(!copy)copy=[g mutableCopy];[copy removeObjectForKey:field];}
    if([g[@"revision"] isKindOfClass:NSNumber.class]){if(!copy)copy=[g mutableCopy];copy[@"revision"]=[g[@"revision"] stringValue];}
    [games addObject:copy ? [copy copy] : g];[gameIDs addObject:g[@"id"]];
  }}
  NSMutableArray *sources=[NSMutableArray array];for(id row in Array(json[@"sources"]))if([row isKindOfClass:NSDictionary.class])[sources addObject:row];
  NSMutableDictionary *result=[json mutableCopy]; result[@"games"]=[games copy];result[@"packs"]=[packs copy];result[@"sources"]=[sources copy];result[@"rejected_entries"]=@(rejected);
  return [result copy];
}
- (NSDictionary *)bundledManifest {
  if(!self.bundledDirectory)return nil;
  NSDictionary *plain=[self validatedManifest:ReadBounded([self.bundledDirectory stringByAppendingPathComponent:@"manifest.json"],ManifestLimit) error:nil];
  return plain ?: [self validatedManifest:ReadBounded([self.bundledDirectory stringByAppendingPathComponent:@"manifest.json.gz"],ManifestCompressedLimit) error:nil];
}
- (NSData *)bundledIndexBytes {
  if (!self.bundledDirectory) return nil;
  return ReadBounded([self.bundledDirectory stringByAppendingPathComponent:@"manifest.json"],ManifestLimit) ?:
      ReadBounded([self.bundledDirectory stringByAppendingPathComponent:@"manifest.json.gz"],ManifestCompressedLimit);
}
- (void)rememberBundledIndex {
  NSData *bytes=[self bundledIndexBytes];
  if (bytes) WriteAtomic(JSONData(@{@"sha256":Digest(bytes)}),[self.storageDirectory stringByAppendingPathComponent:@"bundled-index.json"],nil);
}
- (NSDictionary *)localManifest {
  NSString *path=[self.storageDirectory stringByAppendingPathComponent:@"manifest.json"];
  NSData *bytes=[self bundledIndexBytes];
  NSString *fingerprint=bytes ? Digest(bytes) : nil;
  NSDictionary *previous=JSON(ReadBounded([self.storageDirectory stringByAppendingPathComponent:@"bundled-index.json"],4096));
  // A nonempty 474 cache must not conceal the new PS3 editions shipped in 475.
  // Remember the bundle generation separately so an explicit later remote
  // update is retained on subsequent launches of the same application.
  NSDictionary *bundled=nil;
  if (bytes && ![String(previous[@"sha256"]) isEqual:fingerprint]) {
    bundled=[self validatedManifest:bytes error:nil];
    if (Array(bundled[@"games"]).count) {
      // Do not parse and retain two full indexes during a memory-heavy game.
      WriteAtomic(JSONData(bundled),path,nil);
      WriteAtomic(JSONData(@{@"sha256":fingerprint}),[self.storageDirectory stringByAppendingPathComponent:@"bundled-index.json"],nil);
      return bundled;
    }
  }
  NSDictionary *cached=[self validatedManifest:ReadBounded(path,ManifestLimit) error:nil];
  if (Array(cached[@"games"]).count || !bytes) return cached;
  bundled=bundled ?: [self validatedManifest:bytes error:nil];
  return bundled ?: cached;
}
- (NSUInteger)manifestDownloadLimit {
  return self.fetch ? ManifestLimit : ([self.manifestURL.path hasSuffix:@".gz"] ? ManifestCompressedLimit : ManifestLimit);
}
- (void)invalidateViews {
  _effectiveGames=nil;_effectiveByID=nil;_gamesBySystem=nil;_searchTitles=nil;
  _updates=nil;_archives=nil;_snapshotCache=nil;
}
- (void)adoptManifest:(NSDictionary *)manifest {
  _manifest=manifest;
  _readyPacks=nil;
  NSDictionary *canonical=[self gamesByID:manifest];
  // A persisted install index contains repeated metadata. Reuse matching
  // current records so it does not retain a second full catalogue tree.
  for(NSString *gameID in [_installed.allKeys copy]){NSDictionary *game=canonical[gameID],*previous=_installed[gameID][@"game"];
    if(game && [String(game[@"sha256"]) isEqualToString:String(previous[@"sha256"])])_installed[gameID]=@{@"game":game};}
  NSMutableDictionary *packs=[NSMutableDictionary dictionaryWithCapacity:Array(manifest[@"packs"]).count];
  for(NSDictionary *pack in manifest[@"packs"])packs[pack[@"id"]]=pack;
  _packsByID=[packs copy];
  [self invalidateViews];
}
- (void)readInstallIndex {
  if (_installed) return;
  NSDictionary *json=JSON(ReadBounded([self.storageDirectory stringByAppendingPathComponent:@"installed.json"],ManifestLimit));
  _installed=[NSMutableDictionary dictionary];
  _downloadRequested=[JSON(ReadBounded([self.storageDirectory stringByAppendingPathComponent:@"installation.json"],4096))[@"requested"] boolValue];
  NSDictionary *records=[json[@"games"] isKindOfClass:NSDictionary.class] ? json[@"games"] : @{};
  for (NSString *key in records) {
    id row=records[key];
    if (SafeID(key) && [row isKindOfClass:NSDictionary.class] && [row[@"game"] isKindOfClass:NSDictionary.class] &&
        [String(row[@"game"][@"id"]) isEqualToString:key] && SHA(row[@"game"][@"sha256"]) && NUCCatalogSizeIsValid(row[@"game"][@"size"],ChunkLimit,NO)) {
      NSDictionary *canonical=_gamesByID[key],*saved=row[@"game"];
      _installed[key]=@{@"game":canonical && [String(canonical[@"sha256"]) isEqualToString:String(saved[@"sha256"])] ? canonical : saved};
    }
  }
  if(_installed.count)_downloadRequested=YES;
}
- (NSString *)chunkPath:(NSDictionary *)game {
  return [self.storageDirectory stringByAppendingPathComponent:[NSString stringWithFormat:@"files/%@.json",String(game[@"sha256"]).lowercaseString]];
}
- (BOOL)hasChunk:(NSDictionary *)game verify:(BOOL)verify {
  if (!SHA(game[@"sha256"]) || !NUCCatalogSizeIsValid(game[@"size"],ChunkLimit,NO)) return NO;
  NSString *path=[self chunkPath:game];
  NSDictionary *attrs=[NSFileManager.defaultManager attributesOfItemAtPath:path error:nil];
  if (![attrs.fileType isEqualToString:NSFileTypeRegular] || attrs.fileSize != [game[@"size"] unsignedLongLongValue]) return NO;
  return !verify || [Digest(ReadBounded(path,ChunkLimit)) isEqualToString:String(game[@"sha256"]).lowercaseString];
}
- (NSArray *)effectiveGames {
  if(_effectiveGames)return _effectiveGames;
  [self readInstallIndex];
  NSMutableArray *games=[NSMutableArray arrayWithCapacity:Array(_manifest[@"games"]).count];
  NSMutableDictionary *byID=[NSMutableDictionary dictionaryWithCapacity:Array(_manifest[@"games"]).count];
  NSMutableSet *updates=[NSMutableSet set],*archives=[NSMutableSet set];
  // The arrays/maps below hold references to the immutable parsed records.
  // Never clone every metadata dictionary for each menu or search request.
  for(NSDictionary *game in _manifest[@"games"]) {
    NSDictionary *previous=_installed[game[@"id"]][@"game"];
    BOOL same=previous && [String(previous[@"sha256"]) isEqualToString:String(game[@"sha256"])];
    NSDictionary *chosen=game;
    if(!same && previous && [self hasChunk:previous verify:NO]){chosen=previous;[updates addObject:game[@"id"]];}
    [games addObject:chosen];byID[game[@"id"]]=chosen;
  }
  for(NSString *key in _installed) {
    if(byID[key])continue;
    NSDictionary *previous=_installed[key][@"game"];
    if([self hasChunk:previous verify:NO]){[games addObject:previous];byID[key]=previous;[archives addObject:key];}
  }
  NSMutableDictionary *systems=[NSMutableDictionary dictionary],*titles=[NSMutableDictionary dictionaryWithCapacity:games.count];
  for(NSDictionary *game in games){@autoreleasepool{
    NSString *system=System(game[@"system"]);
    if(!systems[system])systems[system]=[NSMutableArray array];
    [systems[system] addObject:game];
    titles[game[@"id"]]=Fold(String(game[@"title"]));
  }}
  NSMutableDictionary *frozenSystems=[NSMutableDictionary dictionaryWithCapacity:systems.count];
  for(NSString *system in systems)frozenSystems[system]=[systems[system] copy];
  _effectiveGames=[games copy];_effectiveByID=[byID copy];_gamesBySystem=[frozenSystems copy];
  _searchTitles=[titles copy];_updates=[updates copy];_archives=[archives copy];
  return _effectiveGames;
}
- (NSDictionary *)decoratedGame:(NSDictionary *)game {
  NSMutableDictionary *row=[game mutableCopy];
  row[@"installed"]=@([self hasChunk:game verify:NO]);
  row[@"download_requested"]=@(_downloadRequested);
  NSDictionary *pack=_packsByID[String(game[@"pack_id"])];
  NSString *cached=[self.storageDirectory stringByAppendingPathComponent:[NSString stringWithFormat:@"packs/%@.gz",String(pack[@"sha256"]).lowercaseString]];
  NSDictionary *attributes=[NSFileManager.defaultManager attributesOfItemAtPath:cached error:nil];
  row[@"cached_pack"]=@([attributes.fileType isEqual:NSFileTypeRegular] &&
      pack && attributes.fileSize==[pack[@"size"] unsignedLongLongValue]);
  if([_updates containsObject:game[@"id"]])row[@"update_available"]=@YES;
  if([_archives containsObject:game[@"id"]])row[@"archived"]=@YES;
  return row;
}
// Recover the common installation from its content-addressed files, including
// chunks committed before an interrupted bulk operation wrote installed.json.
// Run once per index generation, on the catalogue I/O queue. SHA-256 is still
// verified by the chunk reader before any program can reach an emulator.
- (void)reconcileInstalledFiles {
  if(_readyPacks)return;
  [self readInstallIndex];
  _readyPacks=[NSMutableSet set];
  BOOL directory=NO;
  if(![NSFileManager.defaultManager fileExistsAtPath:[self.storageDirectory stringByAppendingPathComponent:@"files"] isDirectory:&directory] || !directory)return;
  BOOL changed=NO;
  for(NSDictionary *pack in Array(_manifest[@"packs"])) {
    BOOL ready=YES;
    for(NSString *gameID in Array(pack[@"game_ids"])) {@autoreleasepool{
      NSDictionary *game=_gamesByID[gameID];
      if(!game || ![self hasChunk:game verify:NO]){ready=NO;continue;}
      _downloadRequested=YES;
      if(![String(_installed[gameID][@"game"][@"sha256"]) isEqualToString:String(game[@"sha256"])]) {
        _installed[gameID]=@{@"game":game};changed=YES;
      }
    }}
    if(ready)[_readyPacks addObject:pack[@"id"]];
  }
  if(changed)[self invalidateViews];
}
- (NSDictionary *)snapshot {
  if(_snapshotCache)return _snapshotCache;
  [self reconcileInstalledFiles];
  [self effectiveGames];
  NSMutableDictionary *result=[_manifest mutableCopy] ?: [NSMutableDictionary dictionary];
  NSUInteger installed=0,installedPacks=0;unsigned long long bytes=0,installedBytes=0;
  // Counts reflect committed installation metadata; returned game rows check
  // actual files and their chunk reader verifies SHA-256 before any import.
  for(NSDictionary *game in _effectiveGames){NSDictionary *record=_installed[game[@"id"]][@"game"];
    if([String(record[@"sha256"]) isEqualToString:String(game[@"sha256"])])installed++;}
  for(NSDictionary *pack in _manifest[@"packs"]){BOOL ready=[_readyPacks containsObject:pack[@"id"]];bytes += [pack[@"size"] unsignedLongLongValue];
    if(ready){installedPacks++;installedBytes += [pack[@"size"] unsignedLongLongValue];}}
  result[@"installed_games"]=@(installed);result[@"installed_packs"]=@(installedPacks);result[@"total_packs"]=@(Array(_manifest[@"packs"]).count);
  result[@"total_bytes"]=@(bytes);result[@"installed_bytes"]=@(installedBytes);
  result[@"download_requested"]=@(_downloadRequested);
  result[@"installation_state"]=_installing ? @"installing" : (installedPacks==Array(_manifest[@"packs"]).count && installedPacks ? @"complete" : (installed ? @"partial" : @"missing"));
  if(_installationProgress)result[@"progress"]=_installationProgress;
  _snapshotCache=[result copy];return _snapshotCache;
}
- (void)loadWithCompletion:(void (^)(NSDictionary * _Nullable,NSError * _Nullable))completion {
  dispatch_async(_queue,^{
    if(self->_manifest){NSDictionary *snapshot=[self snapshot];dispatch_async(dispatch_get_main_queue(),^{completion(snapshot,nil);});return;}
    [self->_loadWaiters addObject:[completion copy]];
    if(self->_loading)return;self->_loading=YES;
    NSDictionary *local=[self localManifest];
    if(local){[self adoptManifest:local];[self finishLoading:nil];return;}
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY,0),^{
      NSError *fetchError=nil;NSData *data=[self download:self.manifestURL limit:[self manifestDownloadLimit] error:&fetchError];
      NSDictionary *manifest=[self validatedManifest:data error:&fetchError];
      dispatch_async(self->_queue,^{if(manifest){[self adoptManifest:manifest];WriteAtomic(JSONData(manifest),[self.storageDirectory stringByAppendingPathComponent:@"manifest.json"],nil);}[self finishLoading:manifest ? nil : fetchError];});
    });
  });
}
- (void)finishLoading:(NSError *)error {
  NSArray *waiters=[_loadWaiters copy];[_loadWaiters removeAllObjects];_loading=NO;
  NSDictionary *snapshot=_manifest ? [self snapshot] : nil;
  dispatch_async(dispatch_get_main_queue(),^{for(void(^callback)(NSDictionary*,NSError*) in waiters)callback(snapshot,error);});
}

#pragma mark - Transport and installation workers
- (NSData *)download:(NSURL *)url limit:(NSUInteger)limit error:(NSError **)error {
  if (![url.scheme.lowercaseString isEqualToString:@"https"] || !url.host.length || url.user.length || url.password.length) {
    if(error)*error=Failure(3,@"Catalogue downloads require HTTPS");return nil;
  }
  __block NSData *result=nil;__block NSError *failure=nil;
  dispatch_semaphore_t finished=dispatch_semaphore_create(0);
  NeoUnifiedCheatFetch injected=[self.fetch copy];
  [_transportQueue addOperationWithBlock:^{
    dispatch_semaphore_t response=dispatch_semaphore_create(0);
    NSObject *lock=[NSObject new];__block BOOL complete=NO;
    void(^done)(NSData*,NSError*)=^(NSData *data,NSError *problem){@synchronized(lock){if(complete)return;complete=YES;if(data.length>limit){failure=Failure(3,@"Download exceeds its limit");}else{result=data;failure=problem;}dispatch_semaphore_signal(response);}};
    if(injected)injected(url,limit,done);
    else{NeoCheatHTTPSRequest *request=[NeoCheatHTTPSRequest new];[request start:url maximum:limit completion:done];}
    // Retain the operation slot until its asynchronous request finishes.
    if(dispatch_semaphore_wait(response,dispatch_time(DISPATCH_TIME_NOW,65*NSEC_PER_SEC))!=0){@synchronized(lock){complete=YES;failure=Failure(3,@"Catalogue download timed out");}}
    dispatch_semaphore_signal(finished);
  }];
  // This method is only invoked from utility workers, never main or _queue.
  dispatch_semaphore_wait(finished,DISPATCH_TIME_FOREVER);
  if(error)*error=failure ?: (result ? nil : Failure(3,@"Catalogue download returned no data"));
  return result;
}
- (NSURL *)URLForPath:(NSString *)path {
  if(!SafePath(path))return nil;
  return [[self.manifestURL URLByDeletingLastPathComponent] URLByAppendingPathComponent:path];
}
- (NSDictionary *)gamesByID:(NSDictionary *)manifest {
  // Two pack workers share this immutable lookup for the entire generation.
  @synchronized(self){
    if(manifest==_indexedManifest && _gamesByID)return _gamesByID;
    NSMutableDictionary *games=[NSMutableDictionary dictionaryWithCapacity:Array(manifest[@"games"]).count];
    for(NSDictionary *game in manifest[@"games"])games[game[@"id"]]=game;
    _indexedManifest=manifest;_gamesByID=[games copy];return _gamesByID;
  }
}
- (NSArray *)validatedCheats:(NSData *)data game:(NSDictionary *)game error:(NSError **)error {
  NSDictionary *chunk=JSON(data);
  if(![chunk[@"schema_version"] isKindOfClass:NSNumber.class] || [chunk[@"schema_version"] integerValue]!=1 || ![chunk[@"game"] isKindOfClass:NSDictionary.class] ||
     ![String(chunk[@"game"][@"id"]) isEqualToString:String(game[@"id"])] ||
     ![System(chunk[@"game"][@"system"]) isEqualToString:System(game[@"system"])] || ![chunk[@"cheats"] isKindOfClass:NSArray.class] || Array(chunk[@"cheats"]).count>100000){if(error)*error=Failure(7,@"Invalid game chunk");return nil;}
  NSMutableArray *cheats=[NSMutableArray array];NSMutableSet *ids=[NSMutableSet set];
  NSSet *statuses=[NSSet setWithArray:@[@"available",@"requires_engine",@"unresolved",@"invalid"]];
  for(id row in chunk[@"cheats"]){
    if(![row isKindOfClass:NSDictionary.class] || !SafeID(row[@"id"]) || [ids containsObject:row[@"id"]] ||
       !String(row[@"name"]).length || String(row[@"name"]).length>1024 || String(row[@"code"]).length>ChunkLimit ||
       ![statuses containsObject:String(row[@"status"])] || Array(row[@"lines"]).count>100000)continue;
    NSMutableDictionary *copy=[row mutableCopy];copy[@"enabled"]=@NO;
    BOOL malformed=NO;
    for(NSString *field in @[@"dependencies",@"parameters",@"lines"])
      if(copy[field] && ![copy[field] isKindOfClass:NSArray.class])malformed=YES;
    for(id line in Array(copy[@"lines"]))if(![line isKindOfClass:NSString.class])malformed=YES;
    for(id dependency in Array(copy[@"dependencies"]))if(!SafeID(dependency))malformed=YES;
    if(malformed)copy[@"status"]=@"invalid";
    else if(Array(copy[@"parameters"]).count && [copy[@"status"] isEqual:@"available"])copy[@"status"]=@"unresolved";
    // Imported metadata cannot opt itself into a runtime activation route.
    if((![copy[@"handler"] isKindOfClass:NSNumber.class] || [copy[@"handler"] integerValue]!=0 ||
        String(copy[@"code"]).length>131072 || Array(copy[@"lines"]).count>4096) && [copy[@"status"] isEqual:@"available"])
      copy[@"status"]=@"requires_engine";
    [ids addObject:row[@"id"]];[cheats addObject:copy];
  }
  return cheats;
}
- (NSError *)recordInstalledGames:(NSArray *)games {
  __block NSError *error=nil;
  dispatch_sync(_queue,^{
    [self readInstallIndex];
    BOOL changed=NO;
    for(NSDictionary *game in games){NSDictionary *previous=self->_installed[game[@"id"]][@"game"];
      if(![String(previous[@"sha256"]) isEqualToString:String(game[@"sha256"])]){self->_installed[game[@"id"]]=@{@"game":game};changed=YES;}}
    if(changed){
      self->_snapshotCache=nil;
      // Keep the immutable discovery view stable throughout one bulk pass.
      // Otherwise live search while 494 packs finish would rebuild it 494 times.
      if(!self->_installing)[self invalidateViews];
    }
    if(!self->_installing)self->_readyPacks=nil;
    // The manifest already makes each committed chunk discoverable after an
    // interrupted bulk operation. Persist the metadata once at bulk completion.
    if(!self->_installing && games.count)
      WriteAtomic(JSONData(@{@"schema_version":@1,@"games":self->_installed}),[self.storageDirectory stringByAppendingPathComponent:@"installed.json"],&error);
  });
  return error;
}
- (NSError *)installPack:(NSDictionary *)pack manifest:(NSDictionary *)manifest {
  @autoreleasepool {
    NSDictionary *games=[self gamesByID:manifest];
    BOOL allCached=YES;NSMutableArray *cachedGames=[NSMutableArray array];
    for(NSString *gameID in pack[@"game_ids"]){NSDictionary *g=games[gameID];if(g){if(![self hasChunk:g verify:YES]){allCached=NO;break;}[cachedGames addObject:g];}}
    if(allCached)return [self recordInstalledGames:cachedGames];
    NSError *error=nil;
    NSString *packPath=[self.storageDirectory stringByAppendingPathComponent:[NSString stringWithFormat:@"packs/%@.gz",String(pack[@"sha256"]).lowercaseString]];
    NSData *bytes=ReadBounded(packPath,PackLimit);
    if(bytes.length != [pack[@"size"] unsignedIntegerValue] || ![Digest(bytes) isEqualToString:String(pack[@"sha256"]).lowercaseString])bytes=nil;
    if(!bytes && self.bundledDirectory)bytes=ReadBounded([self.bundledDirectory stringByAppendingPathComponent:pack[@"path"]],PackLimit);
    if(!bytes)bytes=[self download:[self URLForPath:pack[@"path"]] limit:[pack[@"size"] unsignedIntegerValue] error:&error];
    if(!bytes)return error ?: Failure(4,@"Pack is unavailable");
    if(bytes.length != [pack[@"size"] unsignedIntegerValue] || ![Digest(bytes) isEqualToString:String(pack[@"sha256"]).lowercaseString])return Failure(5,@"Pack size or SHA-256 mismatch");
    NSData *expanded=Inflate(bytes,[pack[@"uncompressed_size"] unsignedIntegerValue],&error);
    NSDictionary *json=JSON(expanded);
    if(!expanded)return error;
    if(![json[@"schema_version"] isKindOfClass:NSNumber.class] || [json[@"schema_version"] integerValue]!=1 || ![json[@"files"] isKindOfClass:NSArray.class] || Array(json[@"files"]).count>250000)return Failure(7,@"Invalid pack index");
    NSSet *expected=[NSSet setWithArray:Array(pack[@"game_ids"])];NSMutableSet *seen=[NSMutableSet set];
    NSMutableArray *installedGames=[NSMutableArray array];
    for(id file in json[@"files"]){@autoreleasepool{
      if(![file isKindOfClass:NSDictionary.class])continue;
      NSString *gameID=String(file[@"game_id"]);NSDictionary *game=games[gameID];
      if(![expected containsObject:gameID] || !game || ![String(game[@"pack_id"]) isEqualToString:String(pack[@"id"])])continue;
      if([seen containsObject:gameID]){error=Failure(7,@"Duplicate game in pack");continue;}
      [seen addObject:gameID];NSString *base64=String(file[@"data"]);
      if(base64.length > ((ChunkLimit+2)/3)*4){error=Failure(7,@"Game chunk is too large");continue;}
      NSData *chunk=[[NSData alloc] initWithBase64EncodedString:base64 options:0];
      if(chunk.length != [game[@"size"] unsignedIntegerValue] || ![Digest(chunk) isEqualToString:String(game[@"sha256"]).lowercaseString] ||
         ![self validatedCheats:chunk game:game error:&error]){error=error ?: Failure(5,@"Game chunk size or SHA-256 mismatch");continue;}
      NSError *writeError=nil;
      if(!WriteAtomic(chunk,[self chunkPath:game],&writeError)){error=writeError;continue;}
      [installedGames addObject:game];
    }}
    // Each verified game is committed independently: a bad sibling cannot
    // remove it or roll back successful packs from the same bulk operation.
    NSError *indexError=[self recordInstalledGames:installedGames];
    if(indexError)error=error ?: indexError;
    for(NSString *gameID in expected){NSDictionary *game=games[gameID];if(game && ![self hasChunk:game verify:YES])error=error ?: Failure(7,@"Pack is missing a valid game chunk");}
    if(!error && !WriteAtomic(bytes,packPath,&error))return error;
    return error;
  }
}
- (void)installAllWithProgress:(void (^ _Nullable)(NSDictionary * _Nonnull))progress completion:(void (^)(NSDictionary * _Nullable,NSError * _Nullable))completion {
  [self installRefreshingIndex:YES identity:nil progress:progress completion:completion];
}
// All bulk, in-game and repair requests for one immutable pack join one job.
// A newly opened game raises the queued job's priority without another fetch.
// Must be called on the catalogue I/O queue; completions return on that queue.
- (void)enqueuePack:(NSDictionary *)pack manifest:(NSDictionary *)manifest priority:(NSOperationQueuePriority)priority completion:(void (^)(NSError *))completion {
  NSString *key=String(pack[@"sha256"]);
  NSDictionary *existing=_packJobs[key];
  if(existing) {
    [existing[@"callbacks"] addObject:[completion copy]];
    NSOperation *operation=existing[@"operation"];
    if(priority>operation.queuePriority)operation.queuePriority=priority;
    return;
  }
  NSMutableArray *callbacks=[NSMutableArray arrayWithObject:[completion copy]];
  NSBlockOperation *operation=[NSBlockOperation blockOperationWithBlock:^{
    NSError *error=[self installPack:pack manifest:manifest];
    dispatch_async(self->_queue,^{
      NSArray *finished=[self->_packJobs[key][@"callbacks"] copy];[self->_packJobs removeObjectForKey:key];
      for(void(^callback)(NSError*) in finished)callback(error);
      if(!self->_installing) {
        self->_snapshotCache=nil;NSDictionary *state=[self snapshot];
        dispatch_async(dispatch_get_main_queue(),^{[NSNotificationCenter.defaultCenter postNotificationName:NeoUnifiedCheatCatalogProgressNotification object:self userInfo:state];});
      }
    });
  }];
  operation.queuePriority=priority;
  _packJobs[key]=@{@"operation":operation,@"callbacks":callbacks};[_packQueue addOperation:operation];
}
- (void)installAllForIdentity:(NSDictionary *)identity progress:(void (^ _Nullable)(NSDictionary * _Nonnull))progress completion:(void (^)(NSDictionary * _Nullable,NSError * _Nullable))completion {
  NSDictionary *requested=[identity copy];
  [self loadWithCompletion:^(NSDictionary *manifest,NSError *error) {
    if (!manifest) { completion(nil,error); return; }
    [self installRefreshingIndex:NO identity:requested progress:progress completion:completion];
  }];
}
- (void)publishInstallationProgress:(NSDictionary *)progress {
  _installationProgress=progress;_snapshotCache=nil;
  NSArray *callbacks=[_progressWaiters copy];
  NSTimeInterval now=NSDate.timeIntervalSinceReferenceDate;
  BOOL notify=now-_lastProgressNotification>=0.2 || [progress[@"phase"] isEqual:@"preparing"] ||
      [progress[@"completed_packs"] unsignedIntegerValue]==[progress[@"total_packs"] unsignedIntegerValue];
  if(notify)_lastProgressNotification=now;
  NSMutableDictionary *state=[progress mutableCopy];state[@"installation_state"]=@"installing";
  dispatch_async(dispatch_get_main_queue(),^{
    for(void(^callback)(NSDictionary*) in callbacks)callback(progress);
    if(notify)[NSNotificationCenter.defaultCenter postNotificationName:NeoUnifiedCheatCatalogProgressNotification object:self userInfo:state];
  });
}
- (void)finishInstallation:(NSDictionary *)result error:(NSError *)error {
  _installing=NO;_installationProgress=nil;_snapshotCache=nil;
  NSArray *callbacks=[_installWaiters copy];[_installWaiters removeAllObjects];[_progressWaiters removeAllObjects];
  NSDictionary *state=result ?: @{@"installation_state":@"missing"};
  dispatch_async(dispatch_get_main_queue(),^{
    for(void(^callback)(NSDictionary*,NSError*) in callbacks)callback(result,error);
    [NSNotificationCenter.defaultCenter postNotificationName:NeoUnifiedCheatCatalogProgressNotification object:self userInfo:state];
    [NSNotificationCenter.defaultCenter postNotificationName:NeoUnifiedCheatCatalogDidInstallNotification object:self userInfo:result];
  });
}
- (void)installRefreshingIndex:(BOOL)refresh identity:(NSDictionary *)identity progress:(void (^ _Nullable)(NSDictionary * _Nonnull))progress completion:(void (^)(NSDictionary * _Nullable,NSError * _Nullable))completion {
  dispatch_async(_queue,^{
    [self->_installWaiters addObject:[completion copy]];
    if(progress)[self->_progressWaiters addObject:[progress copy]];
    if(self->_installing){
      NSDictionary *current=self->_installationProgress;
      if(progress && current)dispatch_async(dispatch_get_main_queue(),^{progress(current);});
      return;
    }
    [self reconcileInstalledFiles];
    // Opening another console or pressing the completed action cannot start a
    // second pass, re-expand packs, write duplicate files or access the network.
    if(!refresh && self->_manifest && self->_readyPacks.count==Array(self->_manifest[@"packs"]).count && self->_readyPacks.count) {
      [self finishInstallation:[self snapshot] error:nil];return;
    }
    NSError *requestError=nil;
    if(!WriteAtomic(JSONData(@{@"schema_version":@1,@"requested":@YES}),[self.storageDirectory stringByAppendingPathComponent:@"installation.json"],&requestError)) {
      [self finishInstallation:nil error:requestError];return;
    }
    self->_downloadRequested=YES;
    self->_installing=YES;
    [self publishInstallationProgress:@{@"phase":@"preparing",@"completed_packs":@0,@"total_packs":@0,@"installed_packs":@0,@"failed_packs":@0,@"completed_bytes":@0,@"total_bytes":@0}];
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY,0),^{
      NSError *refreshError=nil;
      NSData *remote=refresh ? [self download:self.manifestURL limit:[self manifestDownloadLimit] error:&refreshError] : nil;
      NSDictionary *fresh=remote ? [self validatedManifest:remote error:&refreshError] : nil;
      __block NSDictionary *manifest=nil;__block NSSet *ready=nil;
      dispatch_sync(self->_queue,^{
        if(fresh){[self adoptManifest:fresh];WriteAtomic(JSONData(fresh),[self.storageDirectory stringByAppendingPathComponent:@"manifest.json"],nil);[self rememberBundledIndex];}
        if(!self->_manifest){NSDictionary *local=[self localManifest];
          if(local)[self adoptManifest:local];}
        manifest=self->_manifest;
        [self reconcileInstalledFiles];ready=[self->_readyPacks copy];
      });
      if(!manifest){dispatch_async(self->_queue,^{[self finishInstallation:nil error:refreshError ?: Failure(1,@"No catalogue index is available")];});return;}
      NSMutableSet *priority=[NSMutableSet set];
      if (identity) for (NSDictionary *game in Array(manifest[@"games"])) {
        if ([System(game[@"system"]) isEqual:System(identity[@"system"])] && [self.class matchGame:game identity:identity])
          [priority addObject:game[@"pack_id"]];
      }
      NSArray *packs=[Array(manifest[@"packs"]) sortedArrayUsingComparator:^NSComparisonResult(NSDictionary *a,NSDictionary *b) {
        BOOL first=[priority containsObject:a[@"id"]],second=[priority containsObject:b[@"id"]];
        return first==second ? NSOrderedSame : (first ? NSOrderedAscending : NSOrderedDescending);
      }];
      unsigned long long totalBytes=0,readyBytes=0;
      for(NSDictionary *p in packs){totalBytes += [p[@"size"] unsignedLongLongValue];if([ready containsObject:p[@"id"]])readyBytes += [p[@"size"] unsignedLongLongValue];}
      __block NSUInteger completed=ready.count,installed=ready.count;__block unsigned long long completedBytes=readyBytes;
      NSMutableArray *failed=[NSMutableArray array],*errors=[NSMutableArray array];
      void(^report)(void)=^{[self publishInstallationProgress:@{@"total_packs":@(packs.count),@"completed_packs":@(completed),@"installed_packs":@(installed),@"failed_packs":@(failed.count),@"total_bytes":@(totalBytes),@"completed_bytes":@(completedBytes)}];};
      dispatch_async(self->_queue,report);
      dispatch_group_t group=dispatch_group_create();
      for(NSDictionary *pack in packs){if([ready containsObject:pack[@"id"]])continue;
        dispatch_group_enter(group);dispatch_async(self->_queue,^{[self enqueuePack:pack manifest:manifest priority:NSOperationQueuePriorityNormal completion:^(NSError *error){
          completed++;if(error){[failed addObject:pack[@"id"]];[errors addObject:@{@"pack_id":pack[@"id"],@"message":error.localizedDescription ?: @"Pack failed"}];}else{installed++;completedBytes += [pack[@"size"] unsignedLongLongValue];[self->_readyPacks addObject:pack[@"id"]];}
          // Refresh only the current game's changed packs during this pass.
          // Other packs retain the shared frozen view until bulk completion.
          if ([priority containsObject:pack[@"id"]]) [self invalidateViews];
          report();dispatch_group_leave(group);}];});}
      dispatch_group_notify(group,self->_queue,^{self->_installing=NO;self->_installationProgress=nil;
        [self invalidateViews];
        [self readInstallIndex];NSError *storageError=nil;
        WriteAtomic(JSONData(@{@"schema_version":@1,@"games":self->_installed}),[self.storageDirectory stringByAppendingPathComponent:@"installed.json"],&storageError);
        NSMutableDictionary *result=[[self snapshot] mutableCopy];result[@"completed_packs"]=@(completed);result[@"installed_packs"]=@(installed);result[@"failed_packs"]=[failed copy];result[@"errors"]=[errors copy];result[@"completed_bytes"]=@(completedBytes);
        if(!fresh && refreshError)result[@"refresh_error"]=refreshError.localizedDescription;
        if(storageError)result[@"storage_error"]=storageError.localizedDescription;
        NSError *failure=failed.count ? Failure(8,@"Some catalogue packs could not be installed; successful downloads were preserved") : storageError;
        [self finishInstallation:[result copy] error:failure];
      });
    });
  });
}

#pragma mark - Queries
- (NSArray<NSDictionary *> *)installedProgramsForIdentity:(NSDictionary *)identity {
  if (NSThread.isMainThread) return @[];
  __block NSArray *result=@[];
  dispatch_sync(_queue,^{
    if (!self->_manifest) {
      NSDictionary *local=[self localManifest];
      if (local) [self adoptManifest:local];
    }
    [self effectiveGames]; NSMutableArray *found=[NSMutableArray array];
    for (NSDictionary *game in self->_gamesBySystem[System(identity[@"system"])]) {
      if (found.count>=64) break;
      if (![[self.class matchGame:game identity:identity] isEqual:@"exact"] || ![self hasChunk:game verify:NO]) continue;
      NSData *data=ReadBounded([self chunkPath:game],ChunkLimit);
      if (data.length!=[game[@"size"] unsignedIntegerValue] || ![Digest(data) isEqual:String(game[@"sha256"]).lowercaseString]) continue;
      NSArray *programs=[self validatedCheats:data game:game error:nil];
      if (programs) [found addObject:@{@"game":game,@"programs":programs}];
    }
    result=[found copy];
  });
  return result;
}

- (void)gamesForIdentity:(NSDictionary *)identity completion:(void (^)(NSArray<NSDictionary *> * _Nonnull,NSError * _Nullable))completion {
  NSDictionary *requested=[identity copy];
  [self loadWithCompletion:^(NSDictionary *manifest,NSError *error){if(!manifest){completion(@[],error);return;}
    dispatch_async(self->_queue,^{NSMutableArray *matches=[NSMutableArray array];
      [self effectiveGames];
      NSArray *pool=self->_gamesBySystem[System(requested[@"system"])] ?: @[];
      NSArray *words=TitleWords(String(requested[@"title"])),*ids=Array(requested[@"identities"]);
      for(NSDictionary *game in pool){@autoreleasepool{
        if(!RawIdentityOverlap(game,ids) && !FoldedTitleContains(self->_searchTitles[game[@"id"]],words))continue;
        NSString *match=[self.class matchGame:game identity:requested];
        if(match){NSMutableDictionary *row=[[self decoratedGame:game] mutableCopy];row[@"match"]=match;[matches addObject:row];}
      }}
      [matches sortUsingComparator:^NSComparisonResult(NSDictionary *a,NSDictionary *b){NSInteger x=[a[@"match"] isEqual:@"exact"]?0:1,y=[b[@"match"] isEqual:@"exact"]?0:1;return x==y ? [String(a[@"title"]) localizedStandardCompare:String(b[@"title"])] : (x<y ? NSOrderedAscending:NSOrderedDescending);}];
      NSArray *result=[matches copy];dispatch_async(dispatch_get_main_queue(),^{completion(result,nil);});
    });
  }];
}
- (void)searchGames:(NSString *)query system:(NSString *)system completion:(void (^)(NSArray<NSDictionary *> * _Nonnull,NSError * _Nullable))completion {
  NSArray *words=TitleWords(String(query));NSString *requested=System(system);
  [self loadWithCompletion:^(NSDictionary *manifest,NSError *error){if(!manifest){completion(@[],error);return;}
    dispatch_async(self->_queue,^{NSMutableArray *matches=[NSMutableArray array];
      [self effectiveGames];NSArray *pool=requested.length ? (self->_gamesBySystem[requested] ?: @[]) : self->_effectiveGames;
      for(NSDictionary *game in pool){if(words.count && !FoldedTitleContains(self->_searchTitles[game[@"id"]],words))continue;
        [matches addObject:[self decoratedGame:game]];if(matches.count>=500)break;}
      NSArray *result=[matches copy];dispatch_async(dispatch_get_main_queue(),^{completion(result,nil);});
    });
  }];
}
- (void)cheatsForGame:(NSDictionary *)game completion:(void (^)(NSArray<NSDictionary *> * _Nonnull,NSError * _Nullable))completion {
  NSDictionary *requested=[game copy];
  [self loadWithCompletion:^(NSDictionary *manifest,NSError *error){if(!manifest){completion(@[],error);return;}
    dispatch_async(self->_queue,^{
      [self effectiveGames];NSDictionary *canonical=self->_effectiveByID[String(requested[@"id"])];
      if(![String(canonical[@"sha256"]) isEqualToString:String(requested[@"sha256"])])canonical=nil;
      if(!canonical){dispatch_async(dispatch_get_main_queue(),^{completion(@[],Failure(7,@"The selected game is no longer in this catalogue"));});return;}
      NSDictionary *chosen=canonical,*snapshot=self->_manifest;
      NSDictionary *pack=self->_packsByID[String(chosen[@"pack_id"] ?: chosen[@"pack"])];
      void(^readWithError)(NSError*)=^(NSError *previous) {
        [self->_readQueue addOperationWithBlock:^{
          NSError *problem=previous;NSData *data=ReadBounded([self chunkPath:chosen],ChunkLimit);NSArray *cheats=nil;
          if(data.length==[chosen[@"size"] unsignedIntegerValue] && [Digest(data) isEqualToString:String(chosen[@"sha256"]).lowercaseString])cheats=[self validatedCheats:data game:chosen error:&problem];
          if(!cheats && !problem)problem=Failure(5,@"Cached game chunk failed verification");
          dispatch_async(dispatch_get_main_queue(),^{completion(cheats ?: @[],cheats ? nil : problem);});
        }];
      };
      void(^repair)(void)=^{
        if(pack)[self enqueuePack:pack manifest:snapshot priority:NSOperationQueuePriorityVeryHigh completion:readWithError];
        else readWithError(Failure(4,@"This game is not available offline"));
      };
      if ([self hasChunk:chosen verify:NO]) {
        // Ready codes must not wait behind every remaining bulk download.
        // These two bounded readers never fetch or expand packs. Corruption
        // is repaired only by the existing two pack workers below.
        [self->_readQueue addOperationWithBlock:^{
          NSData *data=ReadBounded([self chunkPath:chosen],ChunkLimit);
          if (data.length==[chosen[@"size"] unsignedIntegerValue] && [Digest(data) isEqualToString:String(chosen[@"sha256"]).lowercaseString]) {
            NSError *error=nil;NSArray *programs=[self validatedCheats:data game:chosen error:&error];
            if (programs) {dispatch_async(dispatch_get_main_queue(),^{completion(programs,nil);});return;}
          }
          dispatch_async(self->_queue,repair);
        }];
      } else repair();
    });
  }];
}
@end

#import "LibretroCheatCatalog.h"
#import "LibretroCheats.h"

static NSError *CatalogError(NSString *text) {
  return [NSError errorWithDomain:@"NeoStation.CheatCatalog" code:1 userInfo:@{NSLocalizedDescriptionKey:text}];
}
static NSString *Text(id value) { return [value isKindOfClass:NSString.class] ? value : @""; }
static BOOL SHA(NSString *text) {
  return [text rangeOfString:@"^[a-f0-9]{40}$" options:NSRegularExpressionSearch].location != NSNotFound;
}
static BOOL SafePath(NSString *path) {
  return path.length > 0 && !path.isAbsolutePath && ![path.pathComponents containsObject:@".."] &&
      [path rangeOfString:@"\\"].location == NSNotFound;
}

/// NSURLSession's completion-handler API buffers before delivering. Use incremental
/// receipt instead, so the byte limit is enforced during (not after) a download.
@interface LibretroCheatTransfer : NSObject <NSURLSessionDataDelegate>
@property(nonatomic, strong) NSMutableData *data;
@property(nonatomic, strong) NSError *error;
@property(nonatomic) NSUInteger limit;
@property(nonatomic, strong) dispatch_semaphore_t done;
@end
@implementation LibretroCheatTransfer
- (void)URLSession:(NSURLSession *)session dataTask:(NSURLSessionDataTask *)task didReceiveResponse:(NSURLResponse *)response
 completionHandler:(void (^)(NSURLSessionResponseDisposition))completion {
  NSInteger status = [(NSHTTPURLResponse *)response statusCode];
  BOOL allowed = status == 200 && response.expectedContentLength <= (int64_t)_limit;
  if (!allowed) _error = CatalogError([NSString stringWithFormat:@"HTTP %ld or resource exceeds limit", (long)status]);
  completion(allowed ? NSURLSessionResponseAllow : NSURLSessionResponseCancel);
}
- (void)URLSession:(NSURLSession *)session task:(NSURLSessionTask *)task willPerformHTTPRedirection:(NSHTTPURLResponse *)response
 newRequest:(NSURLRequest *)request completionHandler:(void (^)(NSURLRequest *_Nullable))completion {
  // The bundled repositories are stable. Do not follow a rename to an unreviewed owner.
  _error = CatalogError(@"Source redirected; catalogue review required"); completion(nil);
}
- (void)URLSession:(NSURLSession *)session dataTask:(NSURLSessionDataTask *)task didReceiveData:(NSData *)data {
  if (_data.length + data.length > _limit) { _error = CatalogError(@"Resource exceeds download limit"); [task cancel]; }
  else [_data appendData:data];
}
- (void)URLSession:(NSURLSession *)session task:(NSURLSessionTask *)task didCompleteWithError:(NSError *)error {
  if (_error == nil) _error = error;
  dispatch_semaphore_signal(_done);
}
@end

@implementation LibretroCheatCatalog {
  NSString *_directory;
  dispatch_queue_t _queue;
}
- (instancetype)initWithDirectory:(NSString *)directory {
  if ((self = [super init])) { _directory = [directory copy];
    _queue = dispatch_queue_create("neostation.cheat-catalog", DISPATCH_QUEUE_SERIAL); }
  return self;
}
+ (NSArray<NSDictionary *> *)sources {
  return @[
    @{@"id": @"libretro", @"name": @"libretro-database", @"repository": @"libretro/libretro-database", @"branch": @"master",
      @"revision": @"12c21cf79f1e20eff6ac68b80875816c717d0a7a", @"license": @"CC BY-SA 4.0",
      @"licenseSHA": @"7d4f96c54aa155a17387e64501c50b6a0469932c", @"format": @"cht"},
    @{@"id": @"openemu-community", @"name": @"OpenEmu — skyzyx", @"repository": @"skyzyx/openemu-cheat-database", @"branch": @"master",
      @"revision": @"5f1af6161ee30fddccc3942dfbcc20b253bcb152", @"license": @"Unlicense",
      @"licenseSHA": @"fdddb29aa445bf3d6a5d843d6dd77e10a9f99657", @"format": @"openemu"},
  ];
}
+ (NSString *)folderForConsole:(NSString *)console {
  return @{@"nes": @"Nintendo - Nintendo Entertainment System", @"snes": @"Nintendo - Super Nintendo Entertainment System",
    @"gb": @"Nintendo - Game Boy", @"gbc": @"Nintendo - Game Boy Color", @"gba": @"Nintendo - Game Boy Advance",
    @"nds": @"Nintendo - Nintendo DS", @"n64": @"Nintendo - Nintendo 64", @"psx": @"Sony - PlayStation", @"psp": @"Sony - PlayStation Portable",
    @"md": @"Sega - Mega Drive - Genesis", @"mcd": @"Sega - Mega-CD - Sega CD", @"32x": @"Sega - 32X",
    @"sms": @"Sega - Master System - Mark III", @"gg": @"Sega - Game Gear", @"sg1000": @"Sega - SG-1000",
    @"pce": @"NEC - PC Engine - TurboGrafx 16", @"tg16": @"NEC - PC Engine - TurboGrafx 16",
    @"pccd": @"NEC - PC Engine CD - TurboGrafx-CD", @"tgcd": @"NEC - PC Engine CD - TurboGrafx-CD",
    @"pcfx": @"NEC - PC-FX", @"ws": @"Bandai - WonderSwan", @"wsc": @"Bandai - WonderSwan Color",
    @"ngp": @"SNK - Neo Geo Pocket", @"ngpc": @"SNK - Neo Geo Pocket Color", @"lynx": @"Atari - Lynx",
    @"vb": @"Nintendo - Virtual Boy", @"2600": @"Atari - 2600", @"5200": @"Atari - 5200", @"7800": @"Atari - 7800",
    @"coleco": @"Coleco - ColecoVision", @"intv": @"Mattel - Intellivision", @"arcade": @"FBNeo - Arcade Games"}[console];
}
- (NSDictionary *)source:(NSString *)identifier {
  for (NSDictionary *source in self.class.sources) if ([source[@"id"] isEqual:identifier]) return source;
  return nil;
}
- (NSString *)folder:(NSString *)source console:(NSString *)console {
  if ([self source:source] == nil || [console rangeOfString:@"^[a-z0-9]{1,16}$" options:NSRegularExpressionSearch].location == NSNotFound) return nil;
  return [[_directory stringByAppendingPathComponent:source] stringByAppendingPathComponent:console];
}
- (NSData *)read:(NSURL *)url limit:(NSUInteger)limit error:(NSError **)error {
  if (error) *error = nil;
  if (![url.scheme isEqual:@"https"] || ![@[@"api.github.com", @"raw.githubusercontent.com"] containsObject:url.host]) {
    if (error) *error = CatalogError(@"Unexpected catalogue host"); return nil;
  }
  if (self.fetch != nil) return self.fetch(url, limit, error);
  LibretroCheatTransfer *transfer = [LibretroCheatTransfer new]; transfer.limit = limit;
  transfer.data = [NSMutableData data]; transfer.done = dispatch_semaphore_create(0);
  NSURLSessionConfiguration *configuration = NSURLSessionConfiguration.ephemeralSessionConfiguration;
  configuration.timeoutIntervalForRequest = 20; configuration.timeoutIntervalForResource = 30;
  configuration.HTTPAdditionalHeaders = @{@"User-Agent": @"NeoStation-CheatCatalog", @"Accept": @"application/vnd.github+json"};
  NSURLSession *session = [NSURLSession sessionWithConfiguration:configuration delegate:transfer delegateQueue:nil];
  NSURLSessionDataTask *task = [session dataTaskWithURL:url]; [task resume];
  BOOL timedOut = dispatch_semaphore_wait(transfer.done, dispatch_time(DISPATCH_TIME_NOW, 35 * NSEC_PER_SEC)) != 0;
  [session invalidateAndCancel];
  if (timedOut) { if (error) *error = CatalogError(@"Catalogue request timed out"); return nil; }
  if (error) *error = transfer.error;
  return transfer.error == nil ? [transfer.data copy] : nil;
}
- (NSDictionary *)json:(NSString *)url error:(NSError **)error {
  NSData *data = [self read:[NSURL URLWithString:url] limit:6u * 1024u * 1024u error:error];
  id json = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:error] : nil;
  if (![json isKindOfClass:NSDictionary.class]) { if (error && *error == nil) *error = CatalogError(@"Invalid catalogue response"); return nil; }
  return json;
}
- (NSArray *)tree:(NSString *)sha repository:(NSString *)repository recursive:(BOOL)recursive error:(NSError **)error {
  if (!SHA(sha)) { if (error) *error = CatalogError(@"Invalid tree revision"); return nil; }
  NSDictionary *json = [self json:[NSString stringWithFormat:@"https://api.github.com/repos/%@/git/trees/%@%@", repository, sha, recursive ? @"?recursive=1" : @""] error:error];
  if ([json[@"truncated"] boolValue] || ![json[@"tree"] isKindOfClass:NSArray.class]) {
    if (error && *error == nil) *error = CatalogError(@"Incomplete catalogue tree"); return nil;
  }
  return json[@"tree"];
}
- (NSDictionary *)entry:(NSString *)path tree:(NSArray *)tree {
  for (id entry in tree) if ([entry isKindOfClass:NSDictionary.class] && [entry[@"path"] isEqual:path]) return entry;
  return nil;
}
- (NSData *)raw:(NSString *)path repository:(NSString *)repository revision:(NSString *)revision limit:(NSUInteger)limit error:(NSError **)error {
  if (!SafePath(path) || !SHA(revision)) { if (error) *error = CatalogError(@"Invalid resource path"); return nil; }
  NSMutableCharacterSet *allowed = [NSCharacterSet.URLPathAllowedCharacterSet mutableCopy]; [allowed removeCharactersInString:@"?#%"];
  NSString *encoded = [path stringByAddingPercentEncodingWithAllowedCharacters:allowed];
  return [self read:[NSURL URLWithString:[NSString stringWithFormat:@"https://raw.githubusercontent.com/%@/%@/%@", repository, revision, encoded]] limit:limit error:error];
}
- (void)loadSource:(NSString *)source console:(NSString *)console completion:(void (^)(NSDictionary *))completion {
  dispatch_async(_queue, ^{
    NSString *folder = [self folder:source console:console];
    NSString *file = [folder stringByAppendingPathComponent:@"index.json"];
    NSDictionary *attributes = file ? [[NSFileManager defaultManager] attributesOfItemAtPath:file error:nil] : nil;
    NSData *data = attributes && [attributes fileSize] <= 16u * 1024u * 1024u ? [NSData dataWithContentsOfFile:file] : nil;
    id json = data.length <= 16u * 1024u * 1024u && data != nil ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
    NSDictionary *catalog = [json isKindOfClass:NSDictionary.class] && [json[@"games"] isKindOfClass:NSArray.class] ? json : nil;
    dispatch_async(dispatch_get_main_queue(), ^{ completion(catalog); });
  });
}
- (NSString *)latest:(NSDictionary *)source error:(NSError **)error {
  NSDictionary *json = [self json:[NSString stringWithFormat:@"https://api.github.com/repos/%@/commits/%@", source[@"repository"], source[@"branch"]] error:error];
  NSString *sha = Text(json[@"sha"]);
  if (!SHA(sha)) { if (error && *error == nil) *error = CatalogError(@"Invalid catalogue revision"); return nil; }
  return sha;
}
- (void)checkSource:(NSString *)source completion:(void (^)(NSString *, NSError *))completion {
  dispatch_async(_queue, ^{
    NSError *error = nil; NSDictionary *descriptor = [self source:source];
    NSString *revision = descriptor ? [self latest:descriptor error:&error] : nil;
    dispatch_async(dispatch_get_main_queue(), ^{ completion(revision, error); });
  });
}
- (void)installSource:(NSString *)source console:(NSString *)console update:(BOOL)update completion:(void (^)(NSDictionary *, NSError *))completion {
  dispatch_async(_queue, ^{
    NSError *error = nil; NSDictionary *descriptor = [self source:source];
    NSString *folder = [self folder:source console:console];
    if (descriptor == nil || folder == nil) { dispatch_async(dispatch_get_main_queue(), ^{ completion(nil, CatalogError(@"Unknown source/console")); }); return; }
    NSString *revision = update ? [self latest:descriptor error:&error] : descriptor[@"revision"];
    NSString *repository = descriptor[@"repository"];
    NSArray *root = revision ? [self tree:revision repository:repository recursive:NO error:&error] : nil;
    NSDictionary *license = [self entry:@"LICENSE" tree:root];
    // An upstream licence change requires app review; no automatic redistribution under stale terms.
    if (root != nil && ![license[@"sha"] isEqual:descriptor[@"licenseSHA"]]) error = CatalogError(@"Catalogue licence changed; source review required");
    NSData *licenseData = error == nil ? [self raw:@"LICENSE" repository:repository revision:revision limit:65536 error:&error] : nil;
    if (licenseData && ![[LibretroCheats gitBlobSHA:licenseData] isEqual:descriptor[@"licenseSHA"]]) error = CatalogError(@"Licence checksum mismatch");
    NSMutableArray *games = [NSMutableArray array];
    if (error == nil && [descriptor[@"format"] isEqual:@"openemu"]) {
      NSDictionary *file = [self entry:@"cheats-database.xml" tree:root];
      NSData *data = [self raw:@"cheats-database.xml" repository:repository revision:revision limit:4u * 1024u * 1024u error:&error];
      if (data && ![[LibretroCheats gitBlobSHA:data] isEqual:file[@"sha"]]) error = CatalogError(@"Catalogue checksum mismatch");
      NSArray *parsed = data && error == nil ? [LibretroCheats parseOpenEmu:data error:&error] : nil;
      for (NSDictionary *entry in parsed) if ([entry[@"console"] isEqual:console]) {
        NSMutableDictionary *game = [entry mutableCopy]; game[@"source"] = source; game[@"revision"] = revision;
        [games addObject:game];
      }
    } else if (error == nil) {
      NSString *system = [self.class folderForConsole:console];
      if (system != nil) {
        NSArray *systems = [self tree:[self entry:@"cht" tree:root][@"sha"] repository:repository recursive:NO error:&error];
        NSDictionary *directory = [self entry:system tree:systems];
        NSArray *files = directory != nil && error == nil ? [self tree:directory[@"sha"] repository:repository recursive:YES error:&error] : @[];
        for (id file in files) {
          if (![file isKindOfClass:NSDictionary.class]) { error = CatalogError(@"Invalid catalogue entry"); break; }
          NSString *path = Text(file[@"path"]);
          if (![file[@"type"] isEqual:@"blob"] || ![path.pathExtension.lowercaseString isEqual:@"cht"]) continue;
          if (!SafePath(path) || !SHA(Text(file[@"sha"])) || [file[@"size"] unsignedLongLongValue] > 4u * 1024u * 1024u) {
            error = CatalogError(@"Invalid cheat file metadata"); break;
          }
          [games addObject:@{@"title": path.lastPathComponent.stringByDeletingPathExtension, @"console": console,
            @"path": [NSString stringWithFormat:@"cht/%@/%@", system, path], @"sha": file[@"sha"],
            @"source": source, @"revision": revision, @"md5s": @[]}];
        }
      }
    }
    NSDictionary *catalog = nil;
    if (error == nil && licenseData != nil) {
      catalog = @{@"source": source, @"console": console, @"revision": revision, @"license": descriptor[@"license"],
        @"repository": repository, @"installed": @([NSDate.date timeIntervalSince1970]), @"games": games};
      [[NSFileManager defaultManager] createDirectoryAtPath:folder withIntermediateDirectories:YES attributes:nil error:&error];
      if (error == nil) [licenseData writeToFile:[folder stringByAppendingPathComponent:@"LICENSE"] options:NSDataWritingAtomic error:&error];
      NSData *data = [NSJSONSerialization dataWithJSONObject:catalog options:0 error:&error];
      if (data != nil && error == nil) [data writeToFile:[folder stringByAppendingPathComponent:@"index.json"] options:NSDataWritingAtomic error:&error];
    }
    if (error != nil) catalog = nil;
    dispatch_async(dispatch_get_main_queue(), ^{ completion(catalog, error); });
  });
}
- (void)downloadGame:(NSDictionary *)game completion:(void (^)(NSArray *, NSError *))completion {
  dispatch_async(_queue, ^{
    NSError *error = nil; NSDictionary *source = [self source:game[@"source"]];
    NSArray *cheats = nil;
    if ([game[@"cheats"] isKindOfClass:NSArray.class]) cheats = game[@"cheats"];
    else if (source != nil) {
      NSString *folder = [self folder:source[@"id"] console:Text(game[@"console"])];
      NSString *sha = Text(game[@"sha"]);
      NSString *file = folder && SHA(sha) ? [[folder stringByAppendingPathComponent:@"Files"] stringByAppendingPathComponent:[sha stringByAppendingPathExtension:@"cht"]] : nil;
      NSDictionary *attributes = file ? [[NSFileManager defaultManager] attributesOfItemAtPath:file error:nil] : nil;
      NSData *data = attributes && [attributes fileSize] <= 4u * 1024u * 1024u ? [NSData dataWithContentsOfFile:file] : nil;
      if (data && ![[LibretroCheats gitBlobSHA:data] isEqual:sha]) data = nil;
      if (!data && file) data = [self raw:Text(game[@"path"]) repository:source[@"repository"] revision:Text(game[@"revision"]) limit:4u * 1024u * 1024u error:&error];
      if (data && ![[LibretroCheats gitBlobSHA:data] isEqual:sha]) error = CatalogError(@"Cheat checksum mismatch");
      if (data && error == nil) cheats = [LibretroCheats parseCHT:data error:&error];
      if (cheats && file && error == nil) {
        [[NSFileManager defaultManager] createDirectoryAtPath:file.stringByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:&error];
        if (error == nil) [data writeToFile:file options:NSDataWritingAtomic error:&error];
      }
    }
    NSMutableArray *attributed = [NSMutableArray array];
    for (NSDictionary *record in cheats) {
      NSMutableDictionary *cheat = [record mutableCopy]; cheat[@"source"] = Text(game[@"source"]);
      cheat[@"revision"] = Text(game[@"revision"]); cheat[@"game"] = Text(game[@"title"]); cheat[@"enabled"] = @NO;
      cheat[@"license"] = source[@"license"] ?: @""; cheat[@"repository"] = source[@"repository"] ?: @"";
      cheat[@"licenseURL"] = [NSString stringWithFormat:@"https://github.com/%@/blob/%@/LICENSE", source[@"repository"], game[@"revision"]];
      [attributed addObject:cheat];
    }
    if (cheats == nil && error == nil) error = CatalogError(@"Cheat file unavailable");
    dispatch_async(dispatch_get_main_queue(), ^{ completion(error == nil ? attributed : nil, error); });
  });
}
- (void)removeSource:(NSString *)source console:(NSString *)console completion:(void (^)(void))completion {
  dispatch_async(_queue, ^{
    NSString *folder = [self folder:source console:console];
    if (folder) [[NSFileManager defaultManager] removeItemAtPath:folder error:nil];
    dispatch_async(dispatch_get_main_queue(), completion);
  });
}
@end

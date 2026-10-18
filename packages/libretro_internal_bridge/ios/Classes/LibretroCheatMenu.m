#import "LibretroCheatMenu.h"
#import "LibretroCheatCatalog.h"
#import "LibretroCheats.h"
#import "LibretroSessionMenu.h"
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>
#import <neo_cheat_catalog/NeoUnifiedCheatCatalog.h>
#import <neo_cheat_catalog/NeoUnifiedCheatBrowser.h>

static NSString *String(id value) { return [value isKindOfClass:NSString.class] ? value : @""; }
static NSString *GameKey(NSDictionary *game) {
  return [NSString stringWithFormat:@"%@|%@|%@|%@", game[@"source"], game[@"revision"], game[@"sha"] ?: @"", game[@"title"]];
}
@interface LibretroCheatMenu () <UIDocumentPickerDelegate>
- (void)refreshFBNeoSnapshot;
- (void)runFBNeoCommand:(NSDictionary *)request completion:(void (^)(NSDictionary *, NSError *))completion;
- (LibretroMenuPage *)fbneoRootPage;
@end
@implementation LibretroCheatMenu {
  NSString *_directory, *_console, *_core, *_preferencesPath;
  NSString *(^_text)(NSString *);
  void (^_apply)(NSArray<NSString *> *);
  LibretroCheatCatalog *_catalog;
  NSMutableArray<NSMutableDictionary *> *_records;
  NSMutableDictionary<NSString *, NSDictionary *> *_installed;
  NSMutableDictionary<NSString *, NSString *> *_updates;
  NSDictionary *_identity, *_matchKinds;
  BOOL _ready, _busy, _remember, _warned, _discovering;
  BOOL _unifiedDiscovering;
  NSUInteger _pendingSources, _discoveryGeneration;
  NSMutableSet *_automaticKeys, *_confirmedGames;
  NSString *_cheatSearch, *_gameSearch, *_status;
  __weak LibretroMenuPage *_visiblePage;
  __weak LibretroMenuPage *_rootPage;
  dispatch_queue_t _queue;
  id _unifiedObserver;
  NSDictionary *_fbneoSnapshot;
  NSError *_fbneoError;
  BOOL _fbneoLoading;
  NSUInteger _fbneoGeneration;
}
@synthesize diagnostic = _diagnostic;
@synthesize fbneoCommand = _fbneoCommand;
- (void)setDiagnostic:(void (^)(NSString *))diagnostic {
  _diagnostic = [diagnostic copy]; _catalog.diagnostic = diagnostic;
}
- (BOOL)usesFBNeoNativeCheats {
  return [_console isEqual:@"arcade"] && ([_core isEqual:@"fbneo"] || [_core isEqual:@"fbneo_libretro"]);
}
- (void)setFbneoCommand:(void (^)(NSDictionary *, void (^)(NSDictionary *, NSError *)))command {
  _fbneoCommand = [command copy];
  if (_ready && [self usesFBNeoNativeCheats]) [self refreshFBNeoSnapshot];
}
- (instancetype)initWithDirectory:(NSString *)directory console:(NSString *)console core:(NSString *)core
                     contentPath:(NSString *)contentPath legacy:(NSArray<NSDictionary *> *)legacy
                            text:(NSString *(^)(NSString *))text apply:(void (^)(NSArray<NSString *> *))apply {
  return [self initWithDirectory:directory console:console core:core contentPath:contentPath gameTitle:@"" legacy:legacy text:text apply:apply];
}
- (instancetype)initWithDirectory:(NSString *)directory console:(NSString *)console core:(NSString *)core
                     contentPath:(NSString *)contentPath gameTitle:(NSString *)gameTitle legacy:(NSArray<NSDictionary *> *)legacy
                            text:(NSString *(^)(NSString *))text apply:(void (^)(NSArray<NSString *> *))apply {
  if ((self = [super init])) {
    _directory = directory; _console = console; _core = core; _text = [text copy]; _apply = [apply copy]; _uiLocale = @"en";
    _catalog = [[LibretroCheatCatalog alloc] initWithDirectory:[directory stringByAppendingPathComponent:@"Catalogs"]];
    _records = [NSMutableArray array]; _installed = [NSMutableDictionary dictionary]; _updates = [NSMutableDictionary dictionary];
    _automaticKeys = [NSMutableSet set]; _confirmedGames = [NSMutableSet set];
    _pendingSources = LibretroCheatCatalog.sources.count;
    // Discovery serves the live menu. Utility work can be starved by the
    // user-interactive emulation thread even with tiny local indices.
    _queue = dispatch_queue_create("neostation.cheat-preferences", dispatch_queue_attr_make_with_qos_class(DISPATCH_QUEUE_SERIAL, QOS_CLASS_USER_INITIATED, 0));
    __weak LibretroCheatMenu *weakSelf = self;
    _unifiedObserver = [NSNotificationCenter.defaultCenter addObserverForName:NeoUnifiedCheatCatalogDidInstallNotification
      object:NeoUnifiedCheatCatalog.sharedCatalog queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note) {
        LibretroCheatMenu *menu = weakSelf; if (menu && menu->_ready) [menu discoverUnified];
      }];
    dispatch_async(_queue, ^{
      // Cache only an unchanged regular file. Changed content, inode or modification
      // time invalidates it; no hashing or index traversal blocks the launch queue.
      NSString *identityPath = [LibretroCheats identityContentPath:contentPath];
      NSDictionary *attributes = [NSFileManager.defaultManager attributesOfItemAtPath:identityPath error:nil];
      NSString *fingerprint = [NSString stringWithFormat:@"6|%@|%@|%@|%@|%@|%@", identityPath, console, core,
        attributes[NSFileSize], @([attributes[NSFileModificationDate] timeIntervalSince1970]), attributes[NSFileSystemFileNumber]];
      NSString *cacheKey = [LibretroCheats digest:[fingerprint dataUsingEncoding:NSUTF8StringEncoding]];
      NSString *cacheFile = [[directory stringByAppendingPathComponent:@"Identity"] stringByAppendingPathComponent:[cacheKey stringByAppendingPathExtension:@"json"]];
      NSDictionary *cacheAttributes = [NSFileManager.defaultManager attributesOfItemAtPath:cacheFile error:nil];
      NSData *cacheData = cacheAttributes && [cacheAttributes fileSize] <= 65536 ? [NSData dataWithContentsOfFile:cacheFile] : nil;
      id cached = cacheData ? [NSJSONSerialization JSONObjectWithData:cacheData options:0 error:nil] : nil;
      NSDictionary *identity = [cached isKindOfClass:NSDictionary.class] && [String(cached[@"sha256"]) length] == 64 &&
        [cached[@"console"] isEqual:console] && [cached[@"core"] isEqual:core] ? cached : nil;
      if (!identity) {
        identity = [LibretroCheats identityAtPath:contentPath console:console core:core];
        if (identity) {
          [NSFileManager.defaultManager createDirectoryAtPath:cacheFile.stringByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:nil];
          [[NSJSONSerialization dataWithJSONObject:identity options:0 error:nil] writeToFile:cacheFile atomically:YES];
        }
      }
      NSMutableDictionary *current = [identity mutableCopy] ?: [NSMutableDictionary dictionary];
      current[@"console"] = console; current[@"core"] = core;
      current[@"title"] = gameTitle.length ? gameTitle : contentPath.lastPathComponent.stringByDeletingPathExtension;
      current[@"titleHints"] = gameTitle.length ? @[gameTitle, contentPath.lastPathComponent.stringByDeletingPathExtension] : @[current[@"title"]];
      identity = [self->_catalog resolveIdentity:current];
      NSString *hash = String(identity[@"sha256"]);
      NSString *key = [LibretroCheats digest:[[NSString stringWithFormat:@"%@|%@|%@", console, core, hash] dataUsingEncoding:NSUTF8StringEncoding]];
      NSString *file = hash.length ? [[directory stringByAppendingPathComponent:@"Games"] stringByAppendingPathComponent:[key stringByAppendingPathExtension:@"json"]] : nil;
      NSDictionary *savedAttributes = file ? [[NSFileManager defaultManager] attributesOfItemAtPath:file error:nil] : nil;
      NSData *data = savedAttributes && [savedAttributes fileSize] <= 8u * 1024u * 1024u ? [NSData dataWithContentsOfFile:file] : nil;
      id saved = data && data.length <= 8u * 1024u * 1024u ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
      if (![saved isKindOfClass:NSDictionary.class]) saved = nil;
      if (!saved && ![identityPath isEqual:contentPath]) {
        // 463–465 keyed CUE preferences by descriptor bytes. Preserve those
        // choices while moving to actual track identity; keep the old file.
        NSDictionary *descriptorAttributes = [NSFileManager.defaultManager attributesOfItemAtPath:contentPath error:nil];
        NSData *descriptor = descriptorAttributes && [descriptorAttributes fileSize] <= 1024u*1024u ? [NSData dataWithContentsOfFile:contentPath] : nil;
        NSString *oldHash = descriptor ? [LibretroCheats digest:descriptor] : @"";
        NSString *oldKey = [LibretroCheats digest:[[NSString stringWithFormat:@"%@|%@|%@", console, core, oldHash] dataUsingEncoding:NSUTF8StringEncoding]];
        NSString *oldFile = [[directory stringByAppendingPathComponent:@"Games"] stringByAppendingPathComponent:[oldKey stringByAppendingPathExtension:@"json"]];
        NSDictionary *oldAttributes = [NSFileManager.defaultManager attributesOfItemAtPath:oldFile error:nil];
        NSData *oldData = oldAttributes && [oldAttributes fileSize] <= 8u*1024u*1024u ? [NSData dataWithContentsOfFile:oldFile] : nil;
        id old = oldData ? [NSJSONSerialization JSONObjectWithData:oldData options:0 error:nil] : nil;
        if ([old isKindOfClass:NSDictionary.class] && [old[@"identity"] isKindOfClass:NSDictionary.class] &&
            [old[@"identity"][@"sha256"] isEqual:oldHash] && [old[@"cheats"] isKindOfClass:NSArray.class]) {
          NSMutableDictionary *recovered = [old mutableCopy]; NSMutableArray *choices = [NSMutableArray array];
          for (id raw in old[@"cheats"]) if ([raw isKindOfClass:NSDictionary.class]) {
            NSMutableDictionary *record = [raw mutableCopy]; record[@"enabled"] = @NO; record[@"uncertain"] = @YES; record[@"automaticExact"] = @NO;
            if (!String(record[@"game"]).length) record[@"game"] = contentPath.lastPathComponent.stringByDeletingPathExtension;
            [choices addObject:record];
          }
          recovered[@"cheats"] = choices; recovered[@"confirmedGames"] = @[]; saved = recovered;
          NSLog(@"[Cheats] recovered %lu descriptor-keyed choices; current source matches must verify them", (unsigned long)choices.count);
        }
      }
      dispatch_async(dispatch_get_main_queue(), ^{
        LibretroCheatMenu *menu = weakSelf; if (!menu) return;
        menu->_identity = identity ?: @{@"console": console, @"core": core, @"title": contentPath.lastPathComponent.stringByDeletingPathExtension};
        menu->_preferencesPath = file; menu->_remember = [saved[@"remember"] isKindOfClass:NSNumber.class] ? [saved[@"remember"] boolValue] : YES;
        NSArray *records = menu->_remember && [saved[@"cheats"] isKindOfClass:NSArray.class] ? saved[@"cheats"] : legacy;
        if ([saved[@"confirmedGames"] isKindOfClass:NSArray.class]) for (id game in saved[@"confirmedGames"])
          if ([game isKindOfClass:NSString.class] && [game length] <= 2048) [menu->_confirmedGames addObject:game];
        [menu merge:records]; menu->_ready = YES;
        [menu discover];
        [menu refresh];
      });
    });
    for (NSDictionary *source in LibretroCheatCatalog.sources) {
      [_catalog loadSource:source[@"id"] console:console completion:^(NSDictionary *catalog) {
        LibretroCheatMenu *menu = weakSelf; if (!menu) return;
        if (catalog) menu->_installed[source[@"id"]] = catalog;
        if (menu->_pendingSources) menu->_pendingSources--;
        [menu discover];
        [menu refresh];
      }];
    }
  }
  return self;
}
- (void)dealloc {
  if (_unifiedObserver) [NSNotificationCenter.defaultCenter removeObserver:_unifiedObserver];
}
// Called after both identity and all source indices are ready, and after install/update.
// Only this worker traverses indices. All UI/model mutations stay on the main queue.
- (void)discover {
  if ([self usesFBNeoNativeCheats]) {
    if (_ready) [self refreshFBNeoSnapshot];
    return;
  }
  if (_ready) [self discoverUnified];
  if (!_ready || _pendingSources) return;
  NSUInteger generation = ++_discoveryGeneration; _discovering = YES; _status = nil;
  NSArray *catalogs = [_installed.allValues sortedArrayUsingComparator:^NSComparisonResult(NSDictionary *a, NSDictionary *b) {
    return [a[@"source"] compare:b[@"source"]]; }];
  NSDictionary *identity = _identity; __weak LibretroCheatMenu *weakSelf = self;
  dispatch_async(_queue, ^{
    NSMutableArray *exact = [NSMutableArray array], *candidates = [NSMutableArray array];
    NSMutableDictionary *kinds = [NSMutableDictionary dictionary];
    for (NSDictionary *catalog in catalogs) for (NSDictionary *game in catalog[@"games"]) {
      NSString *match = [LibretroCheats matchGame:game identity:identity];
      if (![match isEqual:@"none"]) kinds[GameKey(game)] = match;
      if ([match isEqual:@"hash"]) [exact addObject:game];
      else if ([match isEqual:@"candidate"]) [candidates addObject:game];
    }
    // Exact variants take priority; uncertain candidates remain individually labelled.
    NSArray *matches = [exact arrayByAddingObjectsFromArray:candidates];
    dispatch_async(dispatch_get_main_queue(), ^{
      LibretroCheatMenu *menu = weakSelf; if (!menu || generation != menu->_discoveryGeneration) return;
      menu->_matchKinds = [kinds copy];
      NSUInteger limit = MIN(matches.count, (NSUInteger)64);
      __block NSUInteger pending = 0, failed = 0;
      for (NSUInteger i = 0; i < limit; i++) {
        NSDictionary *game = matches[i];
        NSString *key = GameKey(game);
        if ([menu->_automaticKeys containsObject:key]) continue;
        pending++;
        [menu->_catalog downloadGame:game completion:^(NSArray *cheats, NSError *error) {
          LibretroCheatMenu *current = weakSelf; if (!current || generation != current->_discoveryGeneration) return;
          if (cheats) {
            BOOL uncertain = ![[LibretroCheats matchGame:game identity:identity] isEqual:@"hash"];
            NSMutableArray *records = [NSMutableArray array];
            for (NSDictionary *raw in cheats) { NSMutableDictionary *record = [raw mutableCopy]; record[@"uncertain"] = @(uncertain); record[@"automaticExact"] = @(!uncertain); [records addObject:record]; }
            [current merge:records]; [current->_automaticKeys addObject:key];
          } else failed++;
          pending--;
          if (!pending) {
            current->_discovering = NO;
            current->_status = failed ? [current t:@"cheatFailed"] : (matches.count > limit || current->_records.count >= 4096) ? [current t:@"cheatResultsLimited"] : nil;
            [current save];
          }
          [current refresh];
        }];
      }
      if (!pending) { menu->_discovering = NO; menu->_status = matches.count > limit ? [menu t:@"cheatResultsLimited"] : nil; }
      NSString *diagnostic = [NSString stringWithFormat:@"match console=%@ core=%@ sources=%lu exact=%lu candidates=%lu requested=%lu", menu->_console, menu->_core,
        (unsigned long)catalogs.count, (unsigned long)exact.count, (unsigned long)candidates.count, (unsigned long)pending];
      NSLog(@"[Cheats] %@", diagnostic); if (menu->_diagnostic) menu->_diagnostic(diagnostic);
      [menu refresh];
    });
  });
}
- (NSDictionary *)unifiedIdentity {
  NSMutableDictionary *identity = [_identity mutableCopy] ?: [NSMutableDictionary dictionary];
  identity[@"system"] = @{ @"tg16": @"pce", @"tgcd": @"pccd" }[_console] ?: _console;
  if ([self usesFBNeoNativeCheats] && String(_fbneoSnapshot[@"driver"]).length) {
    NSMutableArray *identities = [NSMutableArray array];
    for (id value in [identity[@"identities"] isKindOfClass:NSArray.class] ? identity[@"identities"] : @[]) {
      if (![value isKindOfClass:NSDictionary.class]) continue;
      if ([value[@"type"] isEqual:@"romset"] && [value[@"scheme"] isEqual:@"fbneo-driver-name"]) continue;
      [identities addObject:value];
    }
    [identities addObject:@{@"type": @"romset", @"value": _fbneoSnapshot[@"driver"], @"scheme": @"fbneo-driver-name"}];
    identity[@"identities"] = identities;
  }
  id revision = identity[@"gameRevision"] ?: identity[@"pspDiscVersion"];
  if ([revision isKindOfClass:NSString.class] || [revision isKindOfClass:NSNumber.class]) identity[@"revision"] = [revision description];
  return identity;
}
- (BOOL)allowsActivationProfile:(NSDictionary *)program {
  id profiles = program[@"activation_profiles"];
  if (!profiles) return YES;
  if (![profiles isKindOfClass:NSArray.class] || ![profiles count]) return NO;
  for (id profile in profiles) if (!String(profile).length) return NO;
  NSString *core = [_core hasSuffix:@"_libretro"] ? [_core substringToIndex:_core.length - 9] : _core;
  return [profiles containsObject:core];
}
- (BOOL)acceptsUnifiedProgram:(NSDictionary *)program {
  if ([self usesFBNeoNativeCheats])
    return [LibretroCheats canInstallFBNeoPrograms:@[program] game:[self unifiedIdentity]];
  if (![program[@"status"] isEqual:@"available"] ||
      (program[@"parameters"] && ![program[@"parameters"] isKindOfClass:NSArray.class]) ||
      (program[@"dependencies"] && ![program[@"dependencies"] isKindOfClass:NSArray.class]) ||
      [program[@"parameters"] count] || ![self allowsActivationProfile:program]) return NO;
  NSDictionary *dialects = @{
    @"nes": @[@"nes-gamegenie", @"nes-raw"], @"snes": @[@"snes-gamegenie", @"snes-par"],
    @"gb": @[@"gb-gamegenie", @"gb-gameshark"], @"gbc": @[@"gb-gamegenie", @"gb-gameshark"],
    @"gba": @[@"gba-gameshark-v1", @"gba-gameshark-v3", @"gba-codebreaker", @"gba-auto", @"gba-unknown", @"gba-vba-raw"],
    @"nds": @[@"ds-actionreplay"], @"psx": @[@"ps1-gameshark"],
    @"psp": @[@"cwcheat"], @"n64": @[@"n64-gameshark"],
    @"md": @[@"md-gamegenie", @"md-raw"], @"mcd": @[@"md-gamegenie", @"md-raw"],
    @"32x": @[@"md-gamegenie", @"md-raw"], @"pico": @[@"md-gamegenie", @"md-raw"],
    @"pce": @[@"pce-raw"], @"tg16": @[@"pce-raw"], @"pccd": @[@"pce-raw"], @"tgcd": @[@"pce-raw"],
    @"ws": @[@"wswan-raw"], @"wsc": @[@"wswan-raw"],
    @"sms": @[@"sega8-gamegenie", @"sega8-raw"], @"gg": @[@"sega8-gamegenie", @"sega8-raw"]};
  if (![dialects[_console] containsObject:String(program[@"dialect"])]) return NO;
  NSArray *parts = [LibretroCheats codesForCheat:program core:_core console:_console];
  return parts.count && parts.count <= 99;
}
// Resolve a complete program before creating one toggle: a master/condition
// cannot be silently omitted or activated separately from its dependent code.
- (BOOL)appendUnifiedProgram:(NSDictionary *)program index:(NSDictionary *)index
                     visited:(NSMutableSet *)visited visiting:(NSMutableSet *)visiting
                      result:(NSMutableArray *)result depth:(NSUInteger)depth {
  NSString *identifier = String(program[@"id"]);
  if (!identifier.length || depth > 128 || result.count >= 512 || [visiting containsObject:identifier]) return NO;
  if ([visited containsObject:identifier]) return YES;
  if (![self acceptsUnifiedProgram:program]) return NO;
  [visiting addObject:identifier];
  for (id dependency in program[@"dependencies"] ?: @[]) {
    if (![dependency isKindOfClass:NSString.class] || !index[dependency] ||
        ![self appendUnifiedProgram:index[dependency] index:index visited:visited visiting:visiting result:result depth:depth + 1]) return NO;
  }
  NSSet *exclusive = [NSSet setWithArray:[self exclusiveGroupsForRecord:program]];
  for (NSDictionary *previous in result) if ([exclusive intersectsSet:[NSSet setWithArray:[self exclusiveGroupsForRecord:previous]]]) return NO;
  [visiting removeObject:identifier]; [visited addObject:identifier]; [result addObject:program]; return YES;
}
- (NSDictionary *)unifiedRecordForGame:(NSDictionary *)game programs:(NSArray *)programs {
  if (!programs.count || [NeoUnifiedCheatCatalog gameHasConflict:game identity:[self unifiedIdentity]]) return nil;
  NSMutableArray *codes = [NSMutableArray array], *provenance = [NSMutableArray array];
  NSMutableOrderedSet *exclusiveGroups = [NSMutableOrderedSet orderedSet];
  NSMutableSet *activationProfiles = nil;
  BOOL isolatedAUTO = NO;
  for (NSDictionary *program in programs) {
    if (![self acceptsUnifiedProgram:program]) return nil;
    if (program[@"activation_profiles"]) {
      NSSet *profiles = [NSSet setWithArray:program[@"activation_profiles"]];
      if (activationProfiles) [activationProfiles intersectSet:profiles]; else activationProfiles = [profiles mutableCopy];
    }
    [codes addObject:String(program[@"code"])];
    NSArray *groups = [self exclusiveGroupsForRecord:program];
    for (NSString *group in groups) if ([exclusiveGroups containsObject:group]) return nil;
    [exclusiveGroups addObjectsFromArray:groups];
    if ([program[@"mgba_auto_isolated"] isKindOfClass:NSNumber.class] && [program[@"mgba_auto_isolated"] boolValue]) isolatedAUTO = YES;
    for (NSDictionary *origin in program[@"provenance"] ?: @[]) if (![provenance containsObject:origin]) [provenance addObject:origin];
  }
  NSDictionary *selected = programs.lastObject;
  NSMutableDictionary *record = [selected mutableCopy];
  record[@"code"] = [codes componentsJoinedByString:@"+"];
  record[@"handler"] = @0; record[@"enabled"] = @NO; record[@"selected"] = @NO;
  record[@"source"] = @"NeoStation Unified"; record[@"provenance"] = provenance;
  record[@"game"] = String(game[@"title"]); record[@"unifiedGameID"] = String(game[@"id"]);
  record[@"gameRevision"] = String(game[@"revision"]); record[@"regions"] = game[@"regions"] ?: @[];
  record[@"languages"] = game[@"languages"] ?: @[];
  record[@"uncertain"] = @(![[NeoUnifiedCheatCatalog matchGame:game identity:[self unifiedIdentity]] isEqual:@"exact"]);
  record[@"automaticExact"] = @(![record[@"uncertain"] boolValue]);
  record[@"programs"] = programs; // Original ordered programs retain formats, authors and dependencies.
  record[@"exclusive_groups"] = exclusiveGroups.array;
  record[@"mgba_auto_isolated"] = isolatedAUTO ? @YES : @NO;
  if (activationProfiles) record[@"activation_profiles"] = [[activationProfiles allObjects] sortedArrayUsingSelector:@selector(compare:)];
  NSArray *prepared = [LibretroCheats codesForCheat:record core:_core console:_console];
  return prepared.count && prepared.count <= 99 ? record : nil;
}
- (void)presentUnifiedFrom:(UIViewController *)page {
  __weak LibretroCheatMenu *weakSelf = self;
  [NeoUnifiedCheatBrowser presentFrom:page identity:[self unifiedIdentity] engine:[self usesFBNeoNativeCheats] ? @"fbneo" : @"libretro" locale:self.uiLocale
    accepts:^BOOL(NSDictionary *program) { return [weakSelf acceptsUnifiedProgram:program]; }
    importHandler:^(NSDictionary *game, NSArray *programs, void (^completion)(NSError *)) {
      LibretroCheatMenu *menu = weakSelf;
      if ([menu usesFBNeoNativeCheats]) {
        if (!menu.fbneoCommand || [NeoUnifiedCheatCatalog gameHasConflict:game identity:[menu unifiedIdentity]] ||
            ![LibretroCheats canInstallFBNeoPrograms:programs game:game]) {
          completion([NSError errorWithDomain:NeoUnifiedCheatCatalogErrorDomain code:10 userInfo:nil]); return;
        }
        [menu runFBNeoCommand:@{@"action": @"import", @"game": game, @"programs": programs}
          completion:^(NSDictionary *result, NSError *error) { completion(error); }];
        return;
      }
      NSDictionary *record = [menu unifiedRecordForGame:game programs:programs];
      if (!menu || !record || menu->_records.count >= 4096) {
        NSString *reason = menu ? [menu t:menu->_records.count >= 4096 ? @"cheatResultsLimited" : @"cheatCodeUnsupported"] : @"";
        completion([NSError errorWithDomain:NeoUnifiedCheatCatalogErrorDomain code:10 userInfo:@{NSLocalizedDescriptionKey:reason}]); return;
      }
      if ([game[@"edition_confirmed"] boolValue]) [menu->_confirmedGames addObject:String(game[@"id"])];
      [menu merge:@[record]]; [menu save]; [menu refresh]; completion(nil);
    }];
}
- (void)discoverUnified {
  // Installing native INI is always an explicit import. Merely discovering a
  // catalogue must not write a file or select a native FBNeo option.
  if ([self usesFBNeoNativeCheats]) return;
  if (_unifiedDiscovering) return;
  _unifiedDiscovering = YES; __weak LibretroCheatMenu *weakSelf = self;
  [NeoUnifiedCheatCatalog.sharedCatalog gamesForIdentity:[self unifiedIdentity] completion:^(NSArray *games, NSError *error) {
    LibretroCheatMenu *menu = weakSelf; if (!menu) return;
    NSMutableArray *pending = [NSMutableArray array];
    for (NSDictionary *game in games) {
      NSString *key = [@"unified|" stringByAppendingFormat:@"%@|%@", game[@"id"], game[@"sha256"]];
      // Automatic discovery reads installed data only. A download requires the
      // catalogue action, and an imported program always starts disabled.
      if (![game[@"installed"] boolValue] || [menu->_automaticKeys containsObject:key]) continue;
      if (pending.count >= 64 || menu->_records.count >= 4096) { menu->_status = [menu t:@"cheatResultsLimited"]; break; }
      [menu->_automaticKeys addObject:key]; [pending addObject:game];
    }
    if (!pending.count) { menu->_unifiedDiscovering = NO; [menu refresh]; return; }
    __block NSUInteger remaining = pending.count;
    for (NSDictionary *game in pending) [NeoUnifiedCheatCatalog.sharedCatalog cheatsForGame:game completion:^(NSArray *programs, NSError *problem) {
      LibretroCheatMenu *current = weakSelf; if (!current) return;
      if (problem) [current->_automaticKeys removeObject:[@"unified|" stringByAppendingFormat:@"%@|%@", game[@"id"], game[@"sha256"]]];
      else {
        NSMutableDictionary *index = [NSMutableDictionary dictionary];
        for (NSDictionary *program in programs) if (String(program[@"id"]).length) index[program[@"id"]] = program;
        NSMutableArray *records = [NSMutableArray array];
        for (NSDictionary *program in programs) {
          if (current->_records.count + records.count >= 4096) { current->_status = [current t:@"cheatResultsLimited"]; break; }
          NSMutableArray *ordered = [NSMutableArray array];
          if ([current appendUnifiedProgram:program index:index visited:[NSMutableSet set] visiting:[NSMutableSet set] result:ordered depth:0]) {
            NSDictionary *record = [current unifiedRecordForGame:game programs:ordered]; if (record) [records addObject:record];
          }
        }
        [current merge:records]; [current save];
      }
      if (--remaining == 0) current->_unifiedDiscovering = NO;
      [current refresh];
    }];
  }];
}
- (NSUInteger)enabledCount {
  if ([self usesFBNeoNativeCheats]) {
    NSUInteger count = 0;
    for (NSDictionary *option in [self fbneoOptions]) {
      if (String(option[@"value"]).length && ![option[@"value"] isEqual:option[@"off_value"]]) count++;
    }
    return count;
  }
  NSUInteger count = 0; for (NSDictionary *record in _records) if ([record[@"enabled"] boolValue]) count++;
  return count;
}
- (BOOL)verified:(NSDictionary *)record {
  return ![record[@"uncertain"] boolValue] || [_confirmedGames containsObject:String(record[@"unifiedGameID"] ?: record[@"game"])];
}
- (void)activate:(NSDictionary *)record page:(LibretroMenuPage *)page action:(dispatch_block_t)action {
  if ([self verified:record]) { [self warnOnPage:page action:action]; return; }
  [page rebuild];
  [page confirmWithTitle:String(record[@"game"]) message:[NSString stringWithFormat:@"%@\n%@", [self t:@"cheatVersionUncertain"], [self t:@"cheatSaveWarning"]]
    action:[self t:@"cheatActivate"] cancelTitle:[self t:@"cancel"] destructive:NO handler:^{
      [self->_confirmedGames addObject:String(record[@"unifiedGameID"] ?: record[@"game"])]; self->_warned = YES; action();
    }];
}
// Nested pages can be popped before a transfer finishes. Keep the actual root
// list current even when the last child controller no longer exists.
- (void)refresh {
  LibretroMenuPage *root = _rootPage, *visible = _visiblePage;
  [root rebuild]; if (visible != root) [visible rebuild];
}
- (NSString *)t:(NSString *)key { return _text(key); }
- (NSArray<NSString *> *)exclusiveGroupsForRecord:(NSDictionary *)record {
  NSMutableOrderedSet *groups = [NSMutableOrderedSet orderedSet];
  NSString *legacy = String(record[@"exclusive_group"]);
  if (legacy.length) [groups addObject:legacy];
  id stored = record[@"exclusive_groups"];
  if ([stored isKindOfClass:NSArray.class]) for (id value in stored) if (String(value).length) [groups addObject:value];
  return groups.array;
}
- (BOOL)isPureMGBAVBARecord:(NSDictionary *)record {
  // The source dialect alone is insufficient for a dependency closure: its
  // complete executable code must still be one valid ':' VBA program.
  return [String(record[@"dialect"]) isEqual:@"gba-vba-raw"] &&
    [LibretroCheats codesForCheat:record core:@"mgba" console:@"gba"].count > 0;
}
- (NSString *)activationConflict {
  NSMutableSet *activeGroups = [NSMutableSet set];
  BOOL mgba = [_console isEqual:@"gba"] && ([_core isEqual:@"mgba"] || [_core isEqual:@"mgba_libretro"]);
  BOOL isolatedAUTO = NO;
  NSUInteger nonVBA = 0;
  for (NSDictionary *record in _records) {
    if (![record[@"enabled"] boolValue]) continue;
    NSArray *groups = [self exclusiveGroupsForRecord:record];
    for (NSString *group in groups) {
      if ([activeGroups containsObject:group]) return @"exclusiveConflict";
      [activeGroups addObject:group];
    }
    if (mgba && ![self isPureMGBAVBARecord:record]) {
      nonVBA++;
      if ([record[@"mgba_auto_isolated"] isKindOfClass:NSNumber.class] && [record[@"mgba_auto_isolated"] boolValue]) isolatedAUTO = YES;
    }
  }
  return isolatedAUTO && nonVBA > 1 ? @"mgbaIsolationConflict" : nil;
}
- (void)showActivationFailure:(NSString *)conflict page:(LibretroMenuPage *)page {
  _status = conflict.length ? [NeoUnifiedCheatBrowser localizedText:conflict locale:self.uiLocale] : [self t:@"cheatFailed"];
  [self refresh]; [page rebuild];
}
- (BOOL)changeRecord:(NSMutableDictionary *)record enabled:(BOOL)enabled page:(LibretroMenuPage *)page {
  id previousEnabled = record[@"enabled"] ?: @NO, previousSelected = record[@"selected"] ?: @NO;
  record[@"enabled"] = enabled ? @YES : @NO;
  NSString *conflict = [self activationConflict];
  NSArray *codes = conflict ? nil : [self enabledCodes];
  if (!codes) {
    record[@"enabled"] = previousEnabled; record[@"selected"] = previousSelected;
    [self showActivationFailure:conflict page:page]; return NO;
  }
  record[@"selected"] = enabled ? @YES : @NO;
  _status = nil; _apply(codes); [self save]; [self refresh]; [page rebuild]; return YES;
}
- (BOOL)restoreSelectedOnPage:(LibretroMenuPage *)page {
  NSMutableArray *previous = [NSMutableArray arrayWithCapacity:_records.count];
  for (NSMutableDictionary *record in _records) {
    [previous addObject:record[@"enabled"] ?: @NO];
    record[@"enabled"] = [record[@"selected"] boolValue] && [self verified:record] &&
      [LibretroCheats codesForCheat:record core:_core console:_console] != nil ? @YES : @NO;
  }
  NSString *conflict = [self activationConflict];
  NSArray *codes = conflict ? nil : [self enabledCodes];
  if (!codes) {
    for (NSUInteger index = 0; index < _records.count; index++) _records[index][@"enabled"] = previous[index];
    [self showActivationFailure:conflict page:page]; return NO;
  }
  _status = nil; _apply(codes); [self save]; [self refresh]; [page rebuild]; return YES;
}
- (NSString *)fbneoText:(NSString *)key {
  return [NeoUnifiedCheatBrowser localizedText:key locale:self.uiLocale];
}
- (NSArray *)fbneoOptions {
  NSMutableArray *options = [NSMutableArray array];
  id records = _fbneoSnapshot[@"options"];
  if (![records isKindOfClass:NSArray.class]) return options;
  for (id option in records) {
    if (![option isKindOfClass:NSDictionary.class] || ![String(option[@"key"]) hasPrefix:@"fbneo-cheat-"] ||
        ![option[@"values"] isKindOfClass:NSArray.class] || ![option[@"labels"] isKindOfClass:NSArray.class] ||
        !String(option[@"off_value"]).length || ![option[@"values"] containsObject:option[@"off_value"]]) continue;
    BOOL valid = [option[@"values"] count] > 0;
    for (id value in option[@"values"]) if (!String(value).length) valid = NO;
    if (valid) [options addObject:option];
  }
  return options;
}
- (BOOL)fbneoOptionAvailable:(NSDictionary *)option {
  return [option[@"available"] isKindOfClass:NSNumber.class] && [option[@"available"] boolValue];
}
- (NSString *)fbneoUnavailableReason:(NSDictionary *)option {
  if ([String(option[@"reason_code"]) isEqual:@"nonzero_native_default"]) return [self fbneoText:@"fbneoUnsafeDefault"];
  return [self fbneoText:@"fbneoUnmanagedOption"];
}
- (void)refreshFBNeoSnapshot {
  if (![self usesFBNeoNativeCheats] || !_fbneoCommand || _fbneoLoading || _busy) return;
  _fbneoLoading = YES;
  NSUInteger generation = ++_fbneoGeneration;
  __weak LibretroCheatMenu *weakSelf = self;
  _fbneoCommand(@{@"action": @"snapshot"}, ^(NSDictionary *snapshot, NSError *error) {
    dispatch_async(dispatch_get_main_queue(), ^{
      LibretroCheatMenu *menu = weakSelf;
      if (!menu || generation != menu->_fbneoGeneration) return;
      menu->_fbneoLoading = NO;
      menu->_fbneoError = error;
      if ([snapshot isKindOfClass:NSDictionary.class]) menu->_fbneoSnapshot = [snapshot copy];
      [menu refresh];
    });
  });
}
- (void)runFBNeoCommand:(NSDictionary *)request completion:(void (^)(NSDictionary *, NSError *))completion {
  if (![self usesFBNeoNativeCheats] || !_fbneoCommand || _busy) {
    completion(nil, [NSError errorWithDomain:@"NeoStation.FBNeoCheats" code:9 userInfo:nil]); return;
  }
  _busy = YES; _fbneoLoading = NO; _fbneoError = nil;
  NSUInteger generation = ++_fbneoGeneration;
  [self refresh];
  __weak LibretroCheatMenu *weakSelf = self;
  __block BOOL finished = NO;
  _fbneoCommand(request, ^(NSDictionary *result, NSError *error) {
    dispatch_async(dispatch_get_main_queue(), ^{
      if (finished) return; finished = YES;
      LibretroCheatMenu *menu = weakSelf;
      if (menu && generation == menu->_fbneoGeneration) {
        menu->_busy = NO; menu->_fbneoError = error;
        if ([result isKindOfClass:NSDictionary.class]) {
          NSMutableDictionary *snapshot = [menu->_fbneoSnapshot mutableCopy] ?: [NSMutableDictionary dictionary];
          [snapshot addEntriesFromDictionary:result]; menu->_fbneoSnapshot = [snapshot copy];
        }
        [menu refresh];
        // Import validation can fail after the host has deliberately returned
        // existing native options to Off. Re-read their actual session state.
        if (error && !result) [menu refreshFBNeoSnapshot];
      }
      completion(result, error);
    });
  });
}
- (void)showFBNeoError:(NSError *)error page:(LibretroMenuPage *)page {
  if (!page.viewIfLoaded.window || page.presentedViewController) return;
  NSString *detail = [NSString stringWithFormat:@"%@\n%@ (%ld)\n%@", [self fbneoText:@"technicalDetails"],
    error.domain, (long)error.code, error.localizedDescription ?: @""];
  UIAlertController *alert = [UIAlertController alertControllerWithTitle:[self fbneoText:@"fbneoCommandFailed"]
    message:detail preferredStyle:UIAlertControllerStyleAlert];
  [alert addAction:[UIAlertAction actionWithTitle:[self fbneoText:@"close"] style:UIAlertActionStyleCancel handler:nil]];
  [page presentViewController:alert animated:YES completion:nil];
}
- (NSString *)fbneoValueLabel:(NSString *)value option:(NSDictionary *)option {
  if ([value isEqual:option[@"off_value"]]) return [self fbneoText:@"fbneoDisabled"];
  NSUInteger index = [option[@"values"] indexOfObject:value];
  NSArray *labels = option[@"labels"];
  return index != NSNotFound && index < labels.count && String(labels[index]).length ? labels[index] : value;
}
- (void)setFBNeoValue:(NSString *)value option:(NSDictionary *)option page:(LibretroMenuPage *)page pop:(BOOL)pop {
  if (_busy || _fbneoLoading || [_fbneoSnapshot[@"restart_required"] boolValue] || ![self fbneoOptionAvailable:option] ||
      ![option[@"values"] containsObject:value]) { [page rebuild]; return; }
  _visiblePage = page;
  __weak LibretroCheatMenu *weakSelf = self;
  __weak LibretroMenuPage *weakPage = page;
  void (^change)(void) = ^{
    LibretroCheatMenu *menu = weakSelf; if (!menu) return;
    [menu runFBNeoCommand:@{@"action": @"set", @"key": option[@"key"], @"value": value}
      completion:^(NSDictionary *result, NSError *error) {
        LibretroCheatMenu *current = weakSelf; LibretroMenuPage *visible = weakPage;
        if (error) [current showFBNeoError:error page:visible];
        else if (pop) [visible.navigationController popViewControllerAnimated:YES];
      }];
  };
  if ([value isEqual:option[@"off_value"]]) change();
  else [self warnOnPage:page action:change];
}
- (LibretroMenuPage *)fbneoChoicesPage:(NSDictionary *)option {
  __weak LibretroCheatMenu *weakSelf = self;
  LibretroMenuPage *page = [[LibretroMenuPage alloc] initWithTitle:String(option[@"name"]) builder:^NSArray<LibretroMenuSection *> * {
    LibretroCheatMenu *menu = weakSelf; if (!menu) return @[];
    NSMutableArray *rows = [NSMutableArray array];
    NSDictionary *current = option;
    for (NSDictionary *candidate in [menu fbneoOptions]) if ([candidate[@"key"] isEqual:option[@"key"]]) { current = candidate; break; }
    for (NSString *value in current[@"values"]) {
      LibretroMenuRow *row = [LibretroMenuRow rowWithTitle:[menu fbneoValueLabel:value option:current]
        action:^(LibretroMenuPage *page) { [weakSelf setFBNeoValue:value option:current page:page pop:YES]; }];
      row.checked = [value isEqual:current[@"value"]]; row.enabled = !menu->_busy && !menu->_fbneoLoading &&
        ![menu->_fbneoSnapshot[@"restart_required"] boolValue] && [menu fbneoOptionAvailable:current];
      [rows addObject:row];
    }
    LibretroMenuSection *section = [LibretroMenuSection sectionWithTitle:nil rows:rows];
    section.footer = [menu fbneoOptionAvailable:current] ? [menu fbneoText:@"fbneoSessionHelp"] : [menu fbneoUnavailableReason:current]; return @[section];
  }];
  _visiblePage = page; return page;
}
- (void)downloadUnifiedFrom:(LibretroMenuPage*)page {
  if (_busy) return; _busy=YES; __weak LibretroCheatMenu* weakSelf=self;
  [NeoUnifiedCheatCatalog.sharedCatalog installAllWithProgress:^(NSDictionary* progress) {
    LibretroCheatMenu* menu=weakSelf;if(!menu)return;
    menu->_status=[NSString stringWithFormat:@"%@ / %@",progress[@"completed_packs"],progress[@"total_packs"]];[menu refresh];
  } completion:^(NSDictionary* result,NSError* error) {
    LibretroCheatMenu* menu=weakSelf;if(!menu)return;menu->_busy=NO;
    menu->_status=[NeoUnifiedCheatBrowser localizedText:error?@"downloadFailed":@"ready" locale:menu.uiLocale];
    [menu discover];[menu refresh];
  }];
}
- (void)importFrom:(LibretroMenuPage*)page {
  _visiblePage=page;
  NSString* extension=[self usesFBNeoNativeCheats]?@"ini":@"cht";
  UTType* type=[UTType typeWithFilenameExtension:extension] ?: UTTypeData;
  UIDocumentPickerViewController* picker=[[UIDocumentPickerViewController alloc] initForOpeningContentTypes:@[type] asCopy:YES];
  picker.delegate=self;picker.allowsMultipleSelection=![self usesFBNeoNativeCheats];[page presentViewController:picker animated:YES completion:nil];
}
- (LibretroMenuPage *)fbneoRootPage {
  [self refreshFBNeoSnapshot];
  __weak LibretroCheatMenu *weakSelf = self;
  LibretroMenuPage *root = [[LibretroMenuPage alloc] initWithTitle:[self t:@"cheats"] builder:^NSArray<LibretroMenuSection *> * {
    LibretroCheatMenu *menu = weakSelf; if (!menu) return @[];
    NSMutableArray *actions = [NSMutableArray array];
    LibretroMenuRow *catalogue = [LibretroMenuRow rowWithTitle:[NeoUnifiedCheatBrowser localizedText:@"downloadAll" locale:menu.uiLocale]
      action:^(LibretroMenuPage *page) { [weakSelf downloadUnifiedFrom:page]; }];
    catalogue.enabled = menu->_ready && !menu->_busy; [actions addObject:catalogue];
    LibretroMenuRow *import = [LibretroMenuRow rowWithTitle:[NeoUnifiedCheatBrowser localizedText:@"directImport" locale:menu.uiLocale]
      action:^(LibretroMenuPage *page) { [weakSelf importFrom:page]; }];
    import.enabled = menu->_ready && !menu->_busy && !menu->_fbneoLoading; [actions addObject:import];
    NSMutableArray *rows = [NSMutableArray array];
    for (NSDictionary *option in [menu fbneoOptions]) {
      NSArray *values = option[@"values"];
      LibretroMenuRow *row;
      if (values.count == 2) {
        NSString *on = [values[0] isEqual:option[@"off_value"]] ? values[1] : values[0];
        row = [LibretroMenuRow toggleWithTitle:String(option[@"name"]) on:![option[@"value"] isEqual:option[@"off_value"]]
          toggle:^(LibretroMenuPage *page, BOOL enabled) { [weakSelf setFBNeoValue:enabled ? on : option[@"off_value"] option:option page:page pop:NO]; }];
      } else {
        row = [LibretroMenuRow rowWithTitle:String(option[@"name"]) action:^(LibretroMenuPage *page) { [page push:[weakSelf fbneoChoicesPage:option]]; }];
      }
      row.stackedText = YES;
      row.detail = [menu fbneoOptionAvailable:option] ? [menu fbneoValueLabel:String(option[@"value"]) option:option] : [menu fbneoUnavailableReason:option];
      row.enabled = menu->_ready && !menu->_busy && !menu->_fbneoLoading &&
        ![menu->_fbneoSnapshot[@"restart_required"] boolValue] && [menu fbneoOptionAvailable:option]; [rows addObject:row];
    }
    NSString *status = menu->_fbneoLoading ? [menu fbneoText:@"loading"] : rows.count ? nil : [menu fbneoText:@"fbneoNoCodes"];
    LibretroMenuSection *list = [LibretroMenuSection sectionWithTitle:status rows:rows];
    list.footer = [menu fbneoText:@"fbneoSessionHelp"];
    NSMutableArray *sections = [NSMutableArray arrayWithObjects:[LibretroMenuSection sectionWithTitle:nil rows:actions], list, nil];
    if ([menu->_fbneoSnapshot[@"restart_required"] boolValue]) {
      LibretroMenuRow *restart = [LibretroMenuRow rowWithTitle:[menu fbneoText:@"fbneoRestartRequired"] action:nil];
      restart.detail = [menu fbneoText:@"fbneoRestartHelp"]; restart.stackedText = YES;
      [sections addObject:[LibretroMenuSection sectionWithTitle:nil rows:@[restart]]];
    }
    if (menu->_fbneoError) {
      NSError *error = menu->_fbneoError;
      LibretroMenuRow *failure = [LibretroMenuRow rowWithTitle:[menu fbneoText:@"fbneoCommandFailed"]
        action:^(LibretroMenuPage *page) { [weakSelf showFBNeoError:error page:page]; }];
      failure.detail = [menu fbneoText:@"technicalDetails"]; failure.stackedText = YES;
      [sections addObject:[LibretroMenuSection sectionWithTitle:nil rows:@[failure]]];
    }
    return sections;
  }];
  _rootPage = root; _visiblePage = root; return root;
}
- (void)merge:(NSArray *)records {
  for (id raw in records) {
    if (![raw isKindOfClass:NSDictionary.class]) continue;
    NSString *code = String(raw[@"code"]), *name = String(raw[@"name"]);
    if (name.length == 0 || name.length > 2048 || code.length > 65536) continue;
    // Same session/game and exact code semantics: keep one toggle, retain every attribution.
    NSNumber *handler = [raw[@"handler"] isKindOfClass:NSNumber.class] ? raw[@"handler"] : @0;
    NSArray *prepared = [LibretroCheats codesForCheat:raw core:_core console:_console];
    NSString *semanticCode = prepared ? [prepared componentsJoinedByString:@"+"] : code.uppercaseString;
    if (handler.integerValue != 0) {
      // Memory-engine cheats commonly have an empty code string. Their address,
      // value and conditions must keep them distinct even while unsupported.
      NSDictionary *memoryFields = [raw[@"raw"] isKindOfClass:NSDictionary.class] ? raw[@"raw"] : @{@"name":name};
      NSData *fields = [NSJSONSerialization dataWithJSONObject:memoryFields options:NSJSONWritingSortedKeys error:nil];
      semanticCode = [LibretroCheats digest:fields ?: [NSData data]];
    }
    NSString *scope = [raw[@"uncertain"] boolValue] ? String(raw[@"unifiedGameID"] ?: raw[@"game"]) : @"";
    NSString *key = [NSString stringWithFormat:@"%@|%@|%@", handler, semanticCode, scope];
    NSMutableDictionary *existing = nil;
    for (NSMutableDictionary *record in _records) if ([record[@"dedup"] isEqual:key]) { existing = record; break; }
    if (!existing && scope.length == 0 && prepared != nil && [raw[@"automaticExact"] boolValue]) {
      // A recovered descriptor choice becomes verified only when its complete
      // code program also exists in an exact current-content source match.
      for (NSMutableDictionary *record in _records) if ([record[@"uncertain"] boolValue] &&
          [String(record[@"dedup"]) hasPrefix:key]) {
        existing = record; existing[@"uncertain"] = @NO; existing[@"dedup"] = key; existing[@"name"] = name; break;
      }
    }
    NSMutableArray *origins = [NSMutableArray array];
    NSArray *providedOrigins = [raw[@"origins"] isKindOfClass:NSArray.class] ? raw[@"origins"] : @[raw];
    for (id origin in providedOrigins) {
      if (![origin isKindOfClass:NSDictionary.class] || origins.count >= 16) continue;
      NSMutableDictionary *clean = [NSMutableDictionary dictionary];
      for (NSString *field in @[@"source", @"game", @"revision", @"license", @"licenseURL", @"repository"])
        clean[field] = [String(origin[field]) substringToIndex:MIN(String(origin[field]).length, (NSUInteger)2048)];
      [origins addObject:clean];
    }
    NSString *attribution = [NSString stringWithFormat:@"%@ · %@ · %@ · %@", String(raw[@"source"]), String(raw[@"game"]), String(raw[@"revision"]), String(raw[@"license"])];
    if (existing) {
      NSMutableOrderedSet *groups = [NSMutableOrderedSet orderedSetWithArray:[self exclusiveGroupsForRecord:existing]];
      [groups addObjectsFromArray:[self exclusiveGroupsForRecord:raw]]; existing[@"exclusive_groups"] = groups.array;
      if ([raw[@"mgba_auto_isolated"] isKindOfClass:NSNumber.class] && [raw[@"mgba_auto_isolated"] boolValue]) existing[@"mgba_auto_isolated"] = @YES;
      NSMutableOrderedSet *sources = [NSMutableOrderedSet orderedSetWithArray:existing[@"attributions"] ?: @[]];
      [sources addObject:attribution]; existing[@"attributions"] = sources.array;
      NSMutableOrderedSet *allOrigins = [NSMutableOrderedSet orderedSetWithArray:existing[@"origins"] ?: @[]];
      [allOrigins addObjectsFromArray:origins]; existing[@"origins"] = allOrigins.array;
      NSMutableOrderedSet *provenance = [NSMutableOrderedSet orderedSetWithArray:
        [existing[@"provenance"] isKindOfClass:NSArray.class] ? existing[@"provenance"] : @[]];
      if ([raw[@"provenance"] isKindOfClass:NSArray.class]) [provenance addObjectsFromArray:raw[@"provenance"]];
      if (provenance.count) existing[@"provenance"] = provenance.array;
      continue;
    }
    if (_records.count >= 4096) { _status = [self t:@"cheatResultsLimited"]; continue; }
    NSMutableDictionary *record = [raw mutableCopy]; record[@"enabled"] = @NO; record[@"dedup"] = key;
    record[@"exclusive_groups"] = [self exclusiveGroupsForRecord:raw];
    record[@"mgba_auto_isolated"] = [raw[@"mgba_auto_isolated"] isKindOfClass:NSNumber.class] && [raw[@"mgba_auto_isolated"] boolValue] ? @YES : @NO;
    record[@"handler"] = [raw[@"handler"] isKindOfClass:NSNumber.class] ? raw[@"handler"] : @0;
    record[@"selected"] = @([raw[@"selected"] isKindOfClass:NSNumber.class] && [raw[@"selected"] boolValue]);
    NSMutableArray *attributions = [NSMutableArray array];
    if ([raw[@"attributions"] isKindOfClass:NSArray.class]) for (id source in raw[@"attributions"])
      if ([source isKindOfClass:NSString.class] && [source length] <= 2048) [attributions addObject:source];
    record[@"attributions"] = attributions.count ? attributions : @[attribution];
    record[@"origins"] = origins;
    [_records addObject:record];
  }
}
- (NSArray<NSString *> *)enabledCodes {
  if ([self activationConflict]) return nil;
  NSMutableArray *codes = [NSMutableArray array];
  for (NSDictionary *record in _records) if ([record[@"enabled"] boolValue]) {
    if (![self allowsActivationProfile:record]) return nil;
    NSArray *parts = [LibretroCheats codesForCheat:record core:_core console:_console];
    if (parts == nil || codes.count + parts.count > 99) return nil;
    [codes addObjectsFromArray:parts];
  }
  return codes;
}
- (void)save {
  if (!_ready || _preferencesPath == nil) return;
  NSMutableArray *records = [NSMutableArray array];
  if (_remember) for (NSDictionary *record in _records) {
    NSMutableDictionary *copy = [record mutableCopy]; copy[@"enabled"] = @NO;
    // Exact source programs remain in the verified offline catalogue. Keep
    // their IDs and the combined executable code here without duplicating the
    // entire source/provenance document in the per-game preferences.
    if ([copy[@"programs"] isKindOfClass:NSArray.class]) {
      NSMutableArray *ids = [NSMutableArray array];
      for (NSDictionary *program in copy[@"programs"]) if (String(program[@"id"]).length) [ids addObject:program[@"id"]];
      copy[@"programIDs"] = ids; [copy removeObjectForKey:@"programs"];
    }
    [records addObject:copy];
  }
  NSDictionary *saved = @{@"version": @2, @"remember": @(_remember), @"identity": _identity, @"cheats": records, @"confirmedGames": _confirmedGames.allObjects};
  NSString *file = _preferencesPath; __weak LibretroCheatMenu *weakSelf = self;
  dispatch_async(_queue, ^{
    NSError *error = nil;
    [[NSFileManager defaultManager] createDirectoryAtPath:file.stringByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:&error];
    NSData *data = [NSJSONSerialization dataWithJSONObject:saved options:0 error:&error];
    if (data.length > 8u * 1024u * 1024u) error = [NSError errorWithDomain:NeoUnifiedCheatCatalogErrorDomain code:11 userInfo:nil];
    if (data && !error) [data writeToFile:file options:NSDataWritingAtomic error:&error];
    if (error) dispatch_async(dispatch_get_main_queue(), ^{ [weakSelf failed]; });
  });
}
- (void)failed { _status = [self t:@"cheatFailed"]; [self refresh]; }
- (void)applyAndSave {
  NSArray *codes = [self enabledCodes];
  if (codes == nil) { [self showActivationFailure:[self activationConflict] page:_visiblePage]; return; }
  _apply(codes); [self save]; [self refresh];
}
- (void)warnOnPage:(LibretroMenuPage *)page action:(dispatch_block_t)action {
  if (_warned) { action(); return; }
  // UISwitch has already toggled visually when its callback arrives. Restore
  // the still-disabled model before asking, including when the user cancels.
  [page rebuild];
  [page confirmWithTitle:[self t:@"cheats"] message:[self t:@"cheatSaveWarning"] action:[self t:@"cheatActivate"]
    cancelTitle:[self t:@"cancel"] destructive:NO handler:^{ self->_warned = YES; action(); }];
}
- (LibretroMenuRow *)searchRow:(BOOL)games {
  __weak LibretroCheatMenu *weakSelf = self;
  LibretroMenuRow *row = [LibretroMenuRow rowWithTitle:[self t:games ? @"cheatSearchGames" : @"cheatSearch"] action:^(LibretroMenuPage *page) {
    LibretroCheatMenu *menu = weakSelf; if (!menu) return;
    [page askWithTitle:[menu t:games ? @"cheatSearchGames" : @"cheatSearch"] fields:@[[menu t:games ? @"cheatSearchGames" : @"cheatSearch"]]
       secure:@[@NO] action:[menu t:games ? @"cheatFind" : @"cheatSearch"] cancelTitle:[menu t:@"cancel"] handler:^(NSArray<NSString *> *values) {
      if (games) menu->_gameSearch = values.firstObject; else menu->_cheatSearch = values.firstObject;
      [page rebuild];
    }];
  }];
  row.detail = games ? _gameSearch : _cheatSearch; return row;
}
- (NSString *)displayName:(NSDictionary *)record {
  NSString *name = String(record[@"name"]);
  // Some sources use the raw code as the name when no description exists.
  return name.length && ![name isEqual:String(record[@"code"])] ? name : [self t:@"cheats"];
}
- (NSString *)gameSubtitle:(NSDictionary *)record {
  return String(record[@"game"]).length ? String(record[@"game"]) : String(_identity[@"title"]);
}
- (LibretroMenuPage *)detailsPage:(NSDictionary *)record {
  __weak LibretroCheatMenu *weakSelf = self;
  return [[LibretroMenuPage alloc] initWithTitle:[self t:@"cheatDetails"] builder:^NSArray<LibretroMenuSection *> * {
    LibretroCheatMenu *menu = weakSelf; if (!menu) return @[];
    LibretroMenuRow *name = [LibretroMenuRow rowWithTitle:[menu displayName:record] action:nil];
    name.detail = [menu gameSubtitle:record]; name.stackedText = YES;
    NSMutableArray *warnings = [NSMutableArray array];
    if (![menu verified:record]) [warnings addObject:[menu t:@"cheatVersionUncertain"]];
    if (![menu allowsActivationProfile:record] || [LibretroCheats codesForCheat:record core:menu->_core console:menu->_console] == nil)
      [warnings addObject:[menu t:[record[@"handler"] integerValue] != 0 ? @"cheatMemoryUnsupported" : @"cheatCodeUnsupported"]];
    LibretroMenuSection *summary = [LibretroMenuSection sectionWithTitle:nil rows:@[name]];
    summary.footer = [warnings componentsJoinedByString:@"\n\n"];
    NSMutableArray *sections = [NSMutableArray arrayWithObject:summary];
    NSMutableDictionary *metadata = [record mutableCopy]; [metadata removeObjectForKey:@"code"];
    NSData *json = [NSJSONSerialization dataWithJSONObject:metadata options:NSJSONWritingPrettyPrinted | NSJSONWritingSortedKeys error:nil];
    NSArray *texts = @[String(record[@"code"]), json ? [[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding] : @""];
    NSArray *titles = @[[menu t:@"cheatCode"], [menu t:@"biosDetails"]];
    // Bound each cell, not the information: even a 64 KiB multi-line code or
    // attribution stays scrollable and is available in full without mutation.
    for (NSUInteger field = 0; field < texts.count; field++) {
      NSString *text = texts[field]; NSMutableArray *rows = [NSMutableArray array];
      for (NSUInteger offset = 0; offset < text.length;) {
        NSRange range = [text rangeOfComposedCharacterSequencesForRange:NSMakeRange(offset, MIN((NSUInteger)512, text.length - offset))];
        LibretroMenuRow *row = [LibretroMenuRow rowWithTitle:[text substringWithRange:range] action:nil];
        row.stackedText = YES; [rows addObject:row]; offset = NSMaxRange(range);
      }
      if (rows.count) [sections addObject:[LibretroMenuSection sectionWithTitle:titles[field] rows:rows]];
    }
    return sections;
  }];
}
- (LibretroMenuPage *)rootPage {
  if ([self usesFBNeoNativeCheats]) return [self fbneoRootPage];
  __weak LibretroCheatMenu *weakSelf = self;
  LibretroMenuPage *root = [[LibretroMenuPage alloc] initWithTitle:[self t:@"cheats"] builder:^NSArray<LibretroMenuSection *> * {
    LibretroCheatMenu *menu = weakSelf; if (!menu) return @[];
    NSMutableArray *actions = [NSMutableArray array];
    LibretroMenuRow *unified = [LibretroMenuRow rowWithTitle:[NeoUnifiedCheatBrowser localizedText:@"downloadAll" locale:menu.uiLocale]
      action:^(LibretroMenuPage *page) { [weakSelf downloadUnifiedFrom:page]; }];
    unified.enabled = menu->_ready && !menu->_busy; [actions addObject:unified];
    LibretroMenuRow *import = [LibretroMenuRow rowWithTitle:[NeoUnifiedCheatBrowser localizedText:@"directImport" locale:menu.uiLocale]
      action:^(LibretroMenuPage *page) { [weakSelf importFrom:page]; }];
    import.enabled = menu->_ready && !menu->_busy; [actions addObject:import];
    NSMutableArray *rows = [NSMutableArray array];
    for (NSMutableDictionary *record in menu->_records) {
      if (menu->_cheatSearch.length && [String(record[@"name"]) rangeOfString:menu->_cheatSearch options:NSCaseInsensitiveSearch | NSDiacriticInsensitiveSearch].location == NSNotFound) continue;
      BOOL supported = [menu allowsActivationProfile:record] && [LibretroCheats codesForCheat:record core:menu->_core console:menu->_console] != nil;
      LibretroMenuRow *row = [LibretroMenuRow toggleWithTitle:[menu displayName:record] on:[record[@"enabled"] boolValue] toggle:^(LibretroMenuPage *page, BOOL on) {
        menu->_visiblePage = page;
        void (^change)(void) = ^{
          [menu changeRecord:record enabled:on page:page];
        };
        if (on) [menu activate:record page:page action:change]; else change();
      }];
      row.enabled = supported && menu->_ready;
      row.stackedText = YES;
      NSMutableArray *subtitle = [NSMutableArray array];
      NSString *game = [menu gameSubtitle:record]; if (game.length) [subtitle addObject:game];
      if (![menu verified:record]) [subtitle addObject:[menu t:@"cheatVersionBadge"]];
      if (!supported) [subtitle addObject:[menu t:[record[@"handler"] integerValue] != 0 ? @"cheatMemoryBadge" : @"cheatFormatBadge"]];
      row.detail = [subtitle componentsJoinedByString:@" · "];
      row.detailsHint = [menu t:@"cheatDetailsHint"];
      row.detailsAction = ^(LibretroMenuPage *page) { [page push:[menu detailsPage:record]]; };
      row.remove = ^(LibretroMenuPage *page) { [menu->_records removeObjectIdenticalTo:record]; [menu applyAndSave]; [page rebuild]; };
      [rows addObject:row];
    }
    NSString *status = menu->_status ?: ((!menu->_ready || menu->_discovering) ? [menu t:@"cheatBusy"] : (rows.count ? nil : [menu t:@"cheatNone"]));
    LibretroMenuSection *list = [LibretroMenuSection sectionWithTitle:status rows:rows];
    list.footer = [NSString stringWithFormat:@"%@\n%@\n%@%@", [menu t:@"cheatDetailsHint"], [menu t:@"cheatPreferencesHelp"], [menu t:@"cheatEffectsHelp"],
      [LibretroCheats.supportedCoreIDs containsObject:menu->_core] ? @"" : [[@"\n" stringByAppendingString:[menu t:@"cheatCoreUnsupported"]] stringByAppendingFormat:@" (%@)", menu->_core]];
    // Keep the search and switches together on a phone. Import, editing and
    // preferences remain available after the results instead of hiding them
    // below a screenful of tools.
    return @[[LibretroMenuSection sectionWithTitle:nil rows:actions], list];
  }];
  _rootPage = root; _visiblePage = root; return root;
}
- (LibretroMenuPage *)catalogPage {
  __weak LibretroCheatMenu *weakSelf = self;
  LibretroMenuPage *page = [[LibretroMenuPage alloc] initWithTitle:[self t:@"cheatCatalog"] builder:^NSArray<LibretroMenuSection *> * {
    LibretroCheatMenu *menu = weakSelf; if (!menu) return @[];
    NSMutableArray *matches = [NSMutableArray array], *manual = [NSMutableArray array];
    NSArray *catalogs = [menu->_installed.allValues sortedArrayUsingComparator:^NSComparisonResult(NSDictionary *a, NSDictionary *b) { return [a[@"source"] compare:b[@"source"]]; }];
    for (NSDictionary *catalog in catalogs) for (NSDictionary *game in catalog[@"games"]) {
      NSString *match = menu->_matchKinds[GameKey(game)] ?: @"none";
      BOOL found = [match isEqual:@"hash"] || [match isEqual:@"candidate"];
      if (menu->_gameSearch.length) {
        if ([String(game[@"title"]) rangeOfString:menu->_gameSearch options:NSCaseInsensitiveSearch | NSDiacriticInsensitiveSearch].location == NSNotFound) continue;
      } else if (!found) continue;
      // Pagination/search prevents thousands of native rows and controls memory.
      if (matches.count + manual.count >= 150) break;
      LibretroMenuRow *row = [LibretroMenuRow rowWithTitle:game[@"title"] action:^(LibretroMenuPage *page) {
        menu->_visiblePage = page;
        dispatch_block_t download = ^{
          menu->_busy = YES; [page rebuild];
          [menu->_catalog downloadGame:game completion:^(NSArray<NSDictionary *> *cheats, NSError *error) {
            menu->_busy = NO;
            if (error) { [menu failed]; [page rebuild]; return; }
            NSMutableArray *records = [NSMutableArray array];
            for (NSDictionary *raw in cheats) {
              NSMutableDictionary *record = [raw mutableCopy]; record[@"uncertain"] = @(![match isEqual:@"hash"]); [records addObject:record];
            }
            [menu merge:records]; [menu save]; [menu refresh]; [page.navigationController popViewControllerAnimated:YES];
          }];
        };
        if ([match isEqual:@"hash"]) download();
        else [page confirmWithTitle:game[@"title"] message:[menu t:[match isEqual:@"mismatch"] ? @"cheatHashMismatch" : @"cheatVersionUncertain"]
          action:[menu t:@"cheatDownload"] cancelTitle:[menu t:@"cancel"] destructive:NO handler:download];
      }];
      row.detail = [NSString stringWithFormat:@"%@ · %@\n%@", game[@"source"], game[@"revision"],
          [menu t:[match isEqual:@"hash"] ? @"cheatHashMatch" : @"cheatVersionUncertain"]];
      row.stackedText = YES;
      row.enabled = menu->_ready && !menu->_busy; [(found ? matches : manual) addObject:row];
    }
    LibretroMenuRow *sources = [LibretroMenuRow rowWithTitle:[menu t:@"cheatSources"] action:^(LibretroMenuPage *page) { [page push:[menu sourcesPage]]; }];
    LibretroMenuSection *matchSection = [LibretroMenuSection sectionWithTitle:[menu t:@"cheatMatches"] rows:matches];
    matchSection.footer = menu->_status ?: ((!menu->_ready || menu->_discovering) ? [menu t:@"cheatBusy"] : (matches.count + manual.count ? [menu t:@"cheatCatalogHelp"] : [menu t:@"cheatNoVariant"]));
    return @[[LibretroMenuSection sectionWithTitle:menu->_identity[@"title"] rows:@[sources, [menu searchRow:YES]]],
      matchSection, [LibretroMenuSection sectionWithTitle:[menu t:@"cheatManual"] rows:manual]];
  }];
  _visiblePage = page; return page;
}
- (LibretroMenuPage *)sourcesPage {
  __weak LibretroCheatMenu *weakSelf = self;
  LibretroMenuPage *page = [[LibretroMenuPage alloc] initWithTitle:[self t:@"cheatSources"] builder:^NSArray<LibretroMenuSection *> * {
    LibretroCheatMenu *menu = weakSelf; if (!menu) return @[];
    NSMutableArray *sections = [NSMutableArray array];
    for (NSDictionary *source in LibretroCheatCatalog.sources) {
      NSString *identifier = source[@"id"]; NSDictionary *installed = menu->_installed[identifier];
      LibretroMenuRow *install = [LibretroMenuRow rowWithTitle:[menu t:installed ? @"cheatUpdate" : @"cheatInstall"] action:^(LibretroMenuPage *page) {
        menu->_visiblePage = page; menu->_busy = YES; [page rebuild];
        [menu->_catalog installSource:identifier console:menu->_console update:installed != nil completion:^(NSDictionary *catalog, NSError *error) {
          menu->_busy = NO;
          if (catalog) { menu->_installed[identifier] = catalog; menu->_status = nil; [menu discover]; } else [menu failed];
          [page rebuild];
        }];
      }]; install.enabled = !menu->_busy;
      NSString *latest = menu->_updates[identifier];
      install.detail = [NSString stringWithFormat:@"%@ · %@\n%@", source[@"license"], installed[@"revision"] ?: source[@"revision"],
          latest && ![latest isEqual:installed[@"revision"]] ? [menu t:@"cheatUpdateAvailable"] : @""];
      install.stackedText = YES;
      LibretroMenuRow *check = [LibretroMenuRow rowWithTitle:[menu t:@"cheatCheckUpdates"] action:^(LibretroMenuPage *page) {
        menu->_busy = YES; [page rebuild];
        [menu->_catalog checkSource:identifier completion:^(NSString *revision, NSError *error) {
          menu->_busy = NO; if (revision) menu->_updates[identifier] = revision; else [menu failed]; [page rebuild];
        }];
      }]; check.enabled = !menu->_busy;
      LibretroMenuRow *remove = [LibretroMenuRow rowWithTitle:[menu t:@"cheatRemoveData"] action:^(LibretroMenuPage *page) {
        [page confirmWithTitle:source[@"name"] message:[menu t:@"cheatRemoveData"] action:[menu t:@"cheatRemoveData"] cancelTitle:[menu t:@"cancel"] destructive:YES handler:^{
          menu->_busy = YES;
          [menu->_catalog removeSource:identifier console:menu->_console completion:^{
            menu->_busy = NO; [menu->_installed removeObjectForKey:identifier]; [menu discover]; [page rebuild];
          }];
        }];
      }]; remove.enabled = installed != nil && !menu->_busy; remove.destructive = YES;
      LibretroMenuSection *section = [LibretroMenuSection sectionWithTitle:source[@"name"] rows:@[install, check, remove]];
      section.footer = [NSString stringWithFormat:@"https://github.com/%@\n%@", source[@"repository"], menu->_status ?: [menu t:@"cheatSourceHelp"]];
      [sections addObject:section];
    }
    return sections;
  }];
  _visiblePage = page; return page;
}
- (void)importFBNeoPrograms:(NSArray*)programs game:(NSDictionary*)game index:(NSUInteger)index {
  if(index>=programs.count){[self refreshFBNeoSnapshot];return;}
  __weak LibretroCheatMenu* weakSelf=self;
  [self runFBNeoCommand:@{@"action":@"import",@"game":game,@"programs":@[programs[index]]} completion:^(NSDictionary* result,NSError* error){
    if(error){[weakSelf failed];return;}[weakSelf importFBNeoPrograms:programs game:game index:index+1];
  }];
}
- (void)documentPicker:(UIDocumentPickerViewController *)controller didPickDocumentsAtURLs:(NSArray<NSURL *> *)urls {
  if (!_ready || _busy || urls.count > 16) return;
  if ([self usesFBNeoNativeCheats]) {
    NSURL* url=urls.firstObject;NSString* driver=String(_fbneoSnapshot[@"driver"]);
    BOOL access=[url startAccessingSecurityScopedResource];
    NSDictionary* attrs=[NSFileManager.defaultManager attributesOfItemAtPath:url.path error:nil];
    NSData* data=attrs.fileSize<=1024*1024 ? [NSData dataWithContentsOfURL:url] : nil;
    if(access)[url stopAccessingSecurityScopedResource];
    NSString* text=data ? [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] : nil;
    if(urls.count!=1 || !driver.length || ![url.lastPathComponent.stringByDeletingPathExtension isEqual:driver] || !text){[self failed];return;}
    NSMutableArray* blocks=[NSMutableArray array];NSMutableString* block=nil;
    for(NSString* raw in [text componentsSeparatedByCharactersInSet:NSCharacterSet.newlineCharacterSet]){
      NSString* line=[raw stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet];
      if([line hasPrefix:@"cheat "]){block=[NSMutableString string];[blocks addObject:block];}
      if(block)[block appendFormat:@"%@\n",raw];
      else if(line.length && ![line hasPrefix:@"//"] && ![line hasPrefix:@";"] && ![line hasPrefix:@"#"]){[self failed];return;}
    }
    NSDictionary* game=@{@"system":@"arcade",@"identities":@[@{@"type":@"romset",@"value":driver,@"scheme":@"fbneo-driver-name"}]};
    NSMutableArray* programs=[NSMutableArray array];
    for(NSString* code in blocks){NSDictionary* program=@{@"code":code,@"dialect":@"fbneo-ini",@"status":@"available",@"enabled":@NO};
      if(![LibretroCheats canInstallFBNeoPrograms:@[program] game:game]){[self failed];return;}[programs addObject:program];}
    if(!programs.count || programs.count>4096){[self failed];return;}
    [self importFBNeoPrograms:programs game:game index:0];return;
  }
  _busy = YES; __weak LibretroCheatMenu *weakSelf = self;
  dispatch_async(_queue, ^{
    NSMutableArray *records = [NSMutableArray array]; BOOL failed = NO;
    for (NSURL *url in urls) {
      BOOL access = [url startAccessingSecurityScopedResource];
      NSDictionary *attributes = [[NSFileManager defaultManager] attributesOfItemAtPath:url.path error:nil];
      NSData *data = attributes && [attributes fileSize] <= 4u * 1024u * 1024u ? [NSData dataWithContentsOfURL:url] : nil;
      NSError *error = nil; NSArray *parsed = data ? [LibretroCheats parseCHT:data error:&error] : nil;
      if (access) [url stopAccessingSecurityScopedResource];
      if (parsed == nil) { failed = YES; break; }
      for (NSDictionary *raw in parsed) { NSMutableDictionary *record = [raw mutableCopy];
        record[@"source"] = url.lastPathComponent; [records addObject:record]; }
    }
    dispatch_async(dispatch_get_main_queue(), ^{
      LibretroCheatMenu *menu = weakSelf; if (!menu) return; menu->_busy = NO;
      if (failed) [menu failed]; else { [menu merge:records]; [menu save]; }
      [menu refresh];
    });
  });
}
@end

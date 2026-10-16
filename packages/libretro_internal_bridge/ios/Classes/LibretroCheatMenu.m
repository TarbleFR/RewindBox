#import "LibretroCheatMenu.h"
#import "LibretroCheatCatalog.h"
#import "LibretroCheats.h"
#import "LibretroSessionMenu.h"
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>

static NSString *String(id value) { return [value isKindOfClass:NSString.class] ? value : @""; }
static NSString *GameKey(NSDictionary *game) {
  return [NSString stringWithFormat:@"%@|%@|%@|%@", game[@"source"], game[@"revision"], game[@"sha"] ?: @"", game[@"title"]];
}
@interface LibretroCheatMenu () <UIDocumentPickerDelegate>
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
  NSUInteger _pendingSources, _discoveryGeneration;
  NSMutableSet *_automaticKeys, *_confirmedGames;
  NSString *_cheatSearch, *_gameSearch, *_status;
  __weak LibretroMenuPage *_visiblePage, *_rootPage;
  dispatch_queue_t _queue;
}
@synthesize diagnostic = _diagnostic;
- (void)setDiagnostic:(void (^)(NSString *))diagnostic {
  _diagnostic = [diagnostic copy]; _catalog.diagnostic = diagnostic;
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
    _directory = directory; _console = console; _core = core; _text = [text copy]; _apply = [apply copy];
    _catalog = [[LibretroCheatCatalog alloc] initWithDirectory:[directory stringByAppendingPathComponent:@"Catalogs"]];
    _records = [NSMutableArray array]; _installed = [NSMutableDictionary dictionary]; _updates = [NSMutableDictionary dictionary];
    _automaticKeys = [NSMutableSet set]; _confirmedGames = [NSMutableSet set];
    _pendingSources = LibretroCheatCatalog.sources.count;
    _queue = dispatch_queue_create("neostation.cheat-preferences", dispatch_queue_attr_make_with_qos_class(DISPATCH_QUEUE_SERIAL, QOS_CLASS_UTILITY, 0));
    __weak LibretroCheatMenu *weakSelf = self;
    dispatch_async(_queue, ^{
      // Cache only an unchanged regular file. Changed content, inode or modification
      // time invalidates it; no hashing or index traversal blocks the launch queue.
      NSString *identityPath = [LibretroCheats identityContentPath:contentPath];
      NSDictionary *attributes = [NSFileManager.defaultManager attributesOfItemAtPath:identityPath error:nil];
      NSString *fingerprint = [NSString stringWithFormat:@"5|%@|%@|%@|%@|%@|%@", identityPath, console, core,
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
// Called after both identity and all source indices are ready, and after install/update.
// Only this worker traverses indices. All UI/model mutations stay on the main queue.
- (void)discover {
  if (!_ready || _pendingSources) return;
  NSUInteger generation = ++_discoveryGeneration; _discovering = YES;
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
- (NSUInteger)enabledCount {
  NSUInteger count = 0; for (NSDictionary *record in _records) if ([record[@"enabled"] boolValue]) count++;
  return count;
}
- (BOOL)verified:(NSDictionary *)record {
  return ![record[@"uncertain"] boolValue] || [_confirmedGames containsObject:String(record[@"game"])];
}
- (void)activate:(NSDictionary *)record page:(LibretroMenuPage *)page action:(dispatch_block_t)action {
  if ([self verified:record]) { [self warnOnPage:page action:action]; return; }
  [page rebuild];
  [page confirmWithTitle:String(record[@"game"]) message:[NSString stringWithFormat:@"%@\n%@", [self t:@"cheatVersionUncertain"], [self t:@"cheatSaveWarning"]]
    action:[self t:@"cheatActivate"] cancelTitle:[self t:@"cancel"] destructive:NO handler:^{
      [self->_confirmedGames addObject:String(record[@"game"])]; self->_warned = YES; action();
    }];
}
// Nested pages can be popped before a transfer finishes. Keep the actual root
// list current even when the last child controller no longer exists.
- (void)refresh {
  LibretroMenuPage *root = _rootPage, *visible = _visiblePage;
  [root rebuild]; if (visible != root) [visible rebuild];
}
- (NSString *)t:(NSString *)key { return _text(key); }
- (void)merge:(NSArray *)records {
  for (id raw in records) {
    if (![raw isKindOfClass:NSDictionary.class] || _records.count >= 4096) continue;
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
    NSString *scope = [raw[@"uncertain"] boolValue] ? String(raw[@"game"]) : @"";
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
      NSMutableOrderedSet *sources = [NSMutableOrderedSet orderedSetWithArray:existing[@"attributions"] ?: @[]];
      [sources addObject:attribution]; existing[@"attributions"] = sources.array;
      NSMutableOrderedSet *allOrigins = [NSMutableOrderedSet orderedSetWithArray:existing[@"origins"] ?: @[]];
      [allOrigins addObjectsFromArray:origins]; existing[@"origins"] = allOrigins.array; continue;
    }
    NSMutableDictionary *record = [raw mutableCopy]; record[@"enabled"] = @NO; record[@"dedup"] = key;
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
  NSMutableArray *codes = [NSMutableArray array];
  for (NSDictionary *record in _records) if ([record[@"enabled"] boolValue]) {
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
    NSMutableDictionary *copy = [record mutableCopy]; copy[@"enabled"] = @NO; [records addObject:copy];
  }
  NSDictionary *saved = @{@"version": @2, @"remember": @(_remember), @"identity": _identity, @"cheats": records, @"confirmedGames": _confirmedGames.allObjects};
  NSString *file = _preferencesPath; __weak LibretroCheatMenu *weakSelf = self;
  dispatch_async(_queue, ^{
    NSError *error = nil;
    [[NSFileManager defaultManager] createDirectoryAtPath:file.stringByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:&error];
    NSData *data = [NSJSONSerialization dataWithJSONObject:saved options:0 error:&error];
    if (data && !error) [data writeToFile:file options:NSDataWritingAtomic error:&error];
    if (error) dispatch_async(dispatch_get_main_queue(), ^{ [weakSelf failed]; });
  });
}
- (void)failed { _status = [self t:@"cheatFailed"]; [self refresh]; }
- (void)applyAndSave {
  NSArray *codes = [self enabledCodes];
  if (codes == nil) { [self failed]; return; }
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
    [page askWithTitle:[menu t:games ? @"cheatSearchGames" : @"cheatSearch"] fields:@[[menu t:@"cheatSearch"]]
       secure:@[@NO] action:[menu t:@"cheatSearch"] cancelTitle:[menu t:@"cancel"] handler:^(NSArray<NSString *> *values) {
      if (games) menu->_gameSearch = values.firstObject; else menu->_cheatSearch = values.firstObject;
      [page rebuild];
    }];
  }];
  row.detail = games ? _gameSearch : _cheatSearch; return row;
}
- (LibretroMenuPage *)rootPage {
  __weak LibretroCheatMenu *weakSelf = self;
  LibretroMenuPage *root = [[LibretroMenuPage alloc] initWithTitle:[self t:@"cheats"] builder:^NSArray<LibretroMenuSection *> * {
    LibretroCheatMenu *menu = weakSelf; if (!menu) return @[];
    NSMutableArray *actions = [NSMutableArray array];
    LibretroMenuRow *find = [LibretroMenuRow rowWithTitle:[menu t:@"cheatFind"] action:^(LibretroMenuPage *page) {
      [menu discover];
      if (!menu->_records.count) {
        // One entry searches every source. The library title is a hint for
        // CHD/renamed files, never a claim of exact regional compatibility.
        menu->_gameSearch = [LibretroCheats searchTitle:String(menu->_identity[@"title"])];
        [page push:[menu catalogPage]];
      } else [page rebuild];
    }];
    find.enabled = menu->_ready && !menu->_busy;
    NSMutableArray *sourceNames = [NSMutableArray array];
    for (NSDictionary *source in LibretroCheatCatalog.sources) if ([menu->_installed[source[@"id"]][@"games"] count]) [sourceNames addObject:source[@"name"]];
    find.detail = sourceNames.count ? [sourceNames componentsJoinedByString:@" · "] : [menu t:@"cheatNoSources"];
    [actions addObject:find];
    [actions addObject:[LibretroMenuRow rowWithTitle:[menu t:@"cheatDisableAll"] action:^(LibretroMenuPage *page) {
      for (NSMutableDictionary *record in menu->_records) { record[@"enabled"] = @NO; record[@"selected"] = @NO; }
      [menu applyAndSave]; [page rebuild];
    }]];
    LibretroMenuRow *import = [LibretroMenuRow rowWithTitle:[menu t:@"cheatImport"] action:^(LibretroMenuPage *page) {
      menu->_visiblePage = page;
      UTType *type = [UTType typeWithFilenameExtension:@"cht"] ?: UTTypeData;
      UIDocumentPickerViewController *picker = [[UIDocumentPickerViewController alloc] initForOpeningContentTypes:@[type] asCopy:YES];
      picker.delegate = menu; picker.allowsMultipleSelection = YES; [page presentViewController:picker animated:YES completion:nil];
    }]; import.enabled = menu->_ready && !menu->_busy; [actions addObject:import];
    LibretroMenuRow *add = [LibretroMenuRow rowWithTitle:[menu t:@"addCheat"] action:^(LibretroMenuPage *page) {
      [page askWithTitle:[menu t:@"addCheat"] fields:@[[menu t:@"cheatName"], [menu t:@"cheatCode"]] secure:@[@NO,@NO]
        action:[menu t:@"add"] cancelTitle:[menu t:@"cancel"] handler:^(NSArray<NSString *> *values) {
          [menu merge:@[@{@"name": values.firstObject.length ? values.firstObject : values.lastObject,
            @"code": values.lastObject, @"handler": @0, @"source": [menu t:@"cheatManual"]}]];
          [menu save]; [page rebuild];
        }];
    }]; add.enabled = menu->_ready; [actions addObject:add];
    LibretroMenuRow *remember = [LibretroMenuRow toggleWithTitle:[menu t:@"cheatRemember"] on:menu->_remember toggle:^(LibretroMenuPage *page, BOOL on) {
      menu->_remember = on; [menu save]; [page rebuild];
    }]; remember.enabled = menu->_ready && menu->_preferencesPath != nil; [actions addObject:remember];
    if (menu->_remember) [actions addObject:[LibretroMenuRow rowWithTitle:[menu t:@"cheatRestore"] action:^(LibretroMenuPage *page) {
      [menu warnOnPage:page action:^{
        NSMutableArray *previous = [NSMutableArray array];
        for (NSMutableDictionary *record in menu->_records) {
          [previous addObject:record[@"enabled"] ?: @NO];
          record[@"enabled"] = @([record[@"selected"] boolValue] && [menu verified:record] && [LibretroCheats codesForCheat:record core:menu->_core console:menu->_console] != nil);
        }
        if ([menu enabledCodes] == nil) {
          for (NSUInteger i = 0; i < menu->_records.count; i++) menu->_records[i][@"enabled"] = previous[i];
          [menu failed];
        }
        [menu applyAndSave]; [page rebuild];
      }];
    }]];
    [actions addObject:[menu searchRow:NO]];
    [actions addObject:[LibretroMenuRow rowWithTitle:[menu t:@"cheatCatalog"] action:^(LibretroMenuPage *page) { [page push:[menu catalogPage]]; }]];
    NSMutableArray *rows = [NSMutableArray array];
    for (NSMutableDictionary *record in menu->_records) {
      if (menu->_cheatSearch.length && [String(record[@"name"]) rangeOfString:menu->_cheatSearch options:NSCaseInsensitiveSearch | NSDiacriticInsensitiveSearch].location == NSNotFound) continue;
      BOOL supported = [LibretroCheats codesForCheat:record core:menu->_core console:menu->_console] != nil;
      LibretroMenuRow *row = [LibretroMenuRow toggleWithTitle:String(record[@"name"]) on:[record[@"enabled"] boolValue] toggle:^(LibretroMenuPage *page, BOOL on) {
        menu->_visiblePage = page;
        void (^change)(void) = ^{
          record[@"enabled"] = @(on);
          if ([menu enabledCodes] == nil) { record[@"enabled"] = @NO; [menu failed]; [page rebuild]; return; }
          record[@"selected"] = @(on); [menu applyAndSave]; [page rebuild];
        };
        if (on) [menu activate:record page:page action:change]; else change();
      }];
      row.enabled = supported && menu->_ready;
      NSString *reason = [record[@"handler"] integerValue] != 0 ? [menu t:@"cheatMemoryUnsupported"] : [menu t:@"cheatCodeUnsupported"];
      row.detail = [NSString stringWithFormat:@"%@%@%@\n%@", [menu verified:record] ? @"" : [[menu t:@"cheatVersionUncertain"] stringByAppendingString:@"\n"], supported ? @"" : [reason stringByAppendingString:@"\n"],
        String(record[@"code"]).length > 512 ? [[String(record[@"code"]) substringToIndex:512] stringByAppendingString:@"…"] : String(record[@"code"]),
        [record[@"attributions"] componentsJoinedByString:@"\n"]];
      row.remove = ^(LibretroMenuPage *page) { [menu->_records removeObjectIdenticalTo:record]; [menu applyAndSave]; [page rebuild]; };
      [rows addObject:row];
    }
    NSString *status = menu->_status ?: ((!menu->_ready || menu->_discovering) ? [menu t:@"cheatBusy"] : (rows.count ? nil : [menu t:@"cheatNone"]));
    LibretroMenuSection *list = [LibretroMenuSection sectionWithTitle:status rows:rows];
    list.footer = [NSString stringWithFormat:@"%@\n%@%@", [menu t:@"cheatPreferencesHelp"], [menu t:@"cheatEffectsHelp"],
      [LibretroCheats.supportedCoreIDs containsObject:menu->_core] ? @"" : [[@"\n" stringByAppendingString:[menu t:@"cheatCoreUnsupported"]] stringByAppendingFormat:@" (%@)", menu->_core]];
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
- (void)documentPicker:(UIDocumentPickerViewController *)controller didPickDocumentsAtURLs:(NSArray<NSURL *> *)urls {
  if (!_ready || _busy || urls.count > 16) return;
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

#import "LibretroCheatMenu.h"
#import "LibretroCheatCatalog.h"
#import "LibretroCheats.h"
#import "LibretroSessionMenu.h"
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>

static NSString *String(id value) { return [value isKindOfClass:NSString.class] ? value : @""; }
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
  NSDictionary *_identity;
  BOOL _ready, _busy, _remember, _warned;
  NSString *_cheatSearch, *_gameSearch, *_status;
  __weak LibretroMenuPage *_visiblePage;
  dispatch_queue_t _queue;
}
- (instancetype)initWithDirectory:(NSString *)directory console:(NSString *)console core:(NSString *)core
                     contentPath:(NSString *)contentPath legacy:(NSArray<NSDictionary *> *)legacy
                            text:(NSString *(^)(NSString *))text apply:(void (^)(NSArray<NSString *> *))apply {
  if ((self = [super init])) {
    _directory = directory; _console = console; _core = core; _text = [text copy]; _apply = [apply copy];
    _catalog = [[LibretroCheatCatalog alloc] initWithDirectory:[directory stringByAppendingPathComponent:@"Catalogs"]];
    _records = [NSMutableArray array]; _installed = [NSMutableDictionary dictionary]; _updates = [NSMutableDictionary dictionary];
    _queue = dispatch_queue_create("neostation.cheat-preferences", DISPATCH_QUEUE_SERIAL);
    __weak LibretroCheatMenu *weakSelf = self;
    dispatch_async(_queue, ^{
      NSDictionary *identity = [LibretroCheats identityAtPath:contentPath console:console core:core];
      NSString *hash = String(identity[@"sha256"]);
      NSString *key = [LibretroCheats digest:[[NSString stringWithFormat:@"%@|%@|%@", console, core, hash] dataUsingEncoding:NSUTF8StringEncoding]];
      NSString *file = hash.length ? [[directory stringByAppendingPathComponent:@"Games"] stringByAppendingPathComponent:[key stringByAppendingPathExtension:@"json"]] : nil;
      NSDictionary *attributes = file ? [[NSFileManager defaultManager] attributesOfItemAtPath:file error:nil] : nil;
      NSData *data = attributes && [attributes fileSize] <= 8u * 1024u * 1024u ? [NSData dataWithContentsOfFile:file] : nil;
      id saved = data && data.length <= 8u * 1024u * 1024u ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
      if (![saved isKindOfClass:NSDictionary.class]) saved = nil;
      dispatch_async(dispatch_get_main_queue(), ^{
        LibretroCheatMenu *menu = weakSelf; if (!menu) return;
        menu->_identity = identity ?: @{@"console": console, @"core": core, @"title": contentPath.lastPathComponent.stringByDeletingPathExtension};
        menu->_preferencesPath = file; menu->_remember = [saved[@"remember"] boolValue];
        NSArray *records = menu->_remember && [saved[@"cheats"] isKindOfClass:NSArray.class] ? saved[@"cheats"] : legacy;
        [menu merge:records]; menu->_ready = YES;
        [menu->_visiblePage rebuild];
      });
    });
    for (NSDictionary *source in LibretroCheatCatalog.sources) {
      [_catalog loadSource:source[@"id"] console:console completion:^(NSDictionary *catalog) {
        LibretroCheatMenu *menu = weakSelf; if (!menu) return;
        if (catalog) menu->_installed[source[@"id"]] = catalog;
        [menu->_visiblePage rebuild];
      }];
    }
  }
  return self;
}
- (NSString *)t:(NSString *)key { return _text(key); }
- (void)merge:(NSArray *)records {
  for (id raw in records) {
    if (![raw isKindOfClass:NSDictionary.class] || _records.count >= 4096) continue;
    NSString *code = String(raw[@"code"]), *name = String(raw[@"name"]);
    if (name.length == 0 || name.length > 2048 || code.length > 8192) continue;
    // Same session/game and exact code semantics: keep one toggle, retain every attribution.
    NSString *key = [NSString stringWithFormat:@"%@|%@", raw[@"handler"] ?: @0, code.uppercaseString];
    NSMutableDictionary *existing = nil;
    for (NSMutableDictionary *record in _records) if ([record[@"dedup"] isEqual:key]) { existing = record; break; }
    NSString *attribution = [NSString stringWithFormat:@"%@ · %@ · %@", String(raw[@"source"]), String(raw[@"game"]), String(raw[@"revision"])];
    if (existing) {
      NSMutableOrderedSet *sources = [NSMutableOrderedSet orderedSetWithArray:existing[@"attributions"] ?: @[]];
      [sources addObject:attribution]; existing[@"attributions"] = sources.array; continue;
    }
    NSMutableDictionary *record = [raw mutableCopy]; record[@"enabled"] = @NO; record[@"dedup"] = key;
    record[@"attributions"] = [raw[@"attributions"] isKindOfClass:NSArray.class] ? raw[@"attributions"] : @[attribution];
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
  NSDictionary *saved = @{@"version": @2, @"remember": @(_remember), @"identity": _identity, @"cheats": records};
  NSString *file = _preferencesPath; __weak LibretroCheatMenu *weakSelf = self;
  dispatch_async(_queue, ^{
    NSError *error = nil;
    [[NSFileManager defaultManager] createDirectoryAtPath:file.stringByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:&error];
    NSData *data = [NSJSONSerialization dataWithJSONObject:saved options:0 error:&error];
    if (data && !error) [data writeToFile:file options:NSDataWritingAtomic error:&error];
    if (error) dispatch_async(dispatch_get_main_queue(), ^{ [weakSelf failed]; });
  });
}
- (void)failed { _status = [self t:@"cheatFailed"]; [_visiblePage rebuild]; }
- (void)applyAndSave {
  NSArray *codes = [self enabledCodes];
  if (codes == nil) { [self failed]; return; }
  _apply(codes); [self save]; [_visiblePage rebuild];
}
- (void)warnOnPage:(LibretroMenuPage *)page action:(dispatch_block_t)action {
  if (_warned) { action(); return; }
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
    [actions addObject:[LibretroMenuRow rowWithTitle:[menu t:@"cheatCatalog"] action:^(LibretroMenuPage *page) { [page push:[menu catalogPage]]; }]];
    [actions addObject:[menu searchRow:NO]];
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
        for (NSMutableDictionary *record in menu->_records) record[@"enabled"] = @([record[@"selected"] boolValue] && [LibretroCheats codesForCheat:record core:menu->_core console:menu->_console] != nil);
        if ([menu enabledCodes] == nil) { for (NSMutableDictionary *record in menu->_records) record[@"enabled"] = @NO; [menu failed]; }
        [menu applyAndSave]; [page rebuild];
      }];
    }]];
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
        if (on) [menu warnOnPage:page action:change]; else change();
      }];
      row.enabled = supported && menu->_ready;
      NSString *reason = [record[@"handler"] integerValue] != 0 ? [menu t:@"cheatMemoryUnsupported"] : [menu t:@"cheatCodeUnsupported"];
      row.detail = [NSString stringWithFormat:@"%@%@\n%@", supported ? @"" : [reason stringByAppendingString:@"\n"],
        String(record[@"code"]), [record[@"attributions"] componentsJoinedByString:@"\n"]];
      row.remove = ^(LibretroMenuPage *page) { [menu->_records removeObjectIdenticalTo:record]; [menu applyAndSave]; [page rebuild]; };
      [rows addObject:row];
    }
    LibretroMenuSection *list = [LibretroMenuSection sectionWithTitle:menu->_status ?: (menu->_ready ? nil : [menu t:@"cheatBusy"]) rows:rows];
    list.footer = [menu t:@"cheatPreferencesHelp"];
    return @[[LibretroMenuSection sectionWithTitle:nil rows:actions], list];
  }];
  _visiblePage = root; return root;
}
- (LibretroMenuPage *)catalogPage {
  __weak LibretroCheatMenu *weakSelf = self;
  LibretroMenuPage *page = [[LibretroMenuPage alloc] initWithTitle:[self t:@"cheatCatalog"] builder:^NSArray<LibretroMenuSection *> * {
    LibretroCheatMenu *menu = weakSelf; if (!menu) return @[];
    NSMutableArray *matches = [NSMutableArray array], *manual = [NSMutableArray array];
    NSArray *catalogs = [menu->_installed.allValues sortedArrayUsingComparator:^NSComparisonResult(NSDictionary *a, NSDictionary *b) { return [a[@"source"] compare:b[@"source"]]; }];
    for (NSDictionary *catalog in catalogs) for (NSDictionary *game in catalog[@"games"]) {
      NSString *match = [LibretroCheats matchGame:game identity:menu->_identity ?: @{}];
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
            [menu merge:cheats]; [menu save]; [page.navigationController popViewControllerAnimated:YES];
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
    matchSection.footer = menu->_status ?: [menu t:@"cheatCatalogHelp"];
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
          if (catalog) { menu->_installed[identifier] = catalog; menu->_status = nil; } else [menu failed];
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
            menu->_busy = NO; [menu->_installed removeObjectForKey:identifier]; [page rebuild];
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
      [menu->_visiblePage rebuild];
    });
  });
}
@end

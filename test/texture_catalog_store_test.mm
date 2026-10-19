// Foundation test of the unified HD texture catalogue (macOS): the production
// catalogue, pack store and engine adapters of packages/neo_texture_catalog,
// with the Build 485 ARMSX2 store linked as in the app (reached at run time).
//
//   texture_catalog_store_test <fixtures.json> <work folder>
//
// fixtures.json (written by test/texture_catalog_native_test.py): the real
// bundled manifest and its expected pack counts, plus local fixture packs
// described as catalogue entries (their archives served by the store's
// injectable transport, as the author's server would).
#import <Foundation/Foundation.h>
#import "NeoTextureCatalog.h"
#import "NeoTextureEngine.h"
#import "NeoTexturePackStore.h"
#import "NeoTextureIdentityReader.h"
#import "NeoTextureSupport.h"
#include <cstdio>

static int checks = 0, failures = 0;
#define CHECK(condition, ...) do { checks++; if (!(condition)) { failures++; fprintf(stderr, "FAIL %s:%d: ", __FILE__, __LINE__); fprintf(stderr, __VA_ARGS__); fprintf(stderr, "\n"); } } while (0)

static NSFileManager *FM(void) { return NSFileManager.defaultManager; }
static BOOL Exists(NSString *path) { return [FM() fileExistsAtPath:path]; }
static NSString *Text(NSString *path) { return [NSString stringWithContentsOfFile:path encoding:NSUTF8StringEncoding error:nil] ?: @""; }
static NSDictionary *JSON(NSString *path) {
  NSData *data = [NSData dataWithContentsOfFile:path];
  id value = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
  return [value isKindOfClass:NSDictionary.class] ? value : nil;
}

// Runs the main run loop until done() is called (completions arrive on main).
static void Wait(NSTimeInterval timeout, void (^start)(dispatch_block_t done)) {
  __block BOOL finished = NO;
  start(^{ finished = YES; });
  NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:timeout];
  while (!finished && [deadline timeIntervalSinceNow] > 0)
    [NSRunLoop.mainRunLoop runMode:NSDefaultRunLoopMode beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.05]];
  CHECK(finished, "operation did not finish within %.0f s", timeout);
}

struct Outcome { NSDictionary *result; NSError *error; };

static Outcome Install(NeoTexturePackStore *store, NSDictionary *pack, id<NeoTextureEngine> engine, NSDictionary *identity,
                       BOOL replace, BOOL confirmed) {
  __block Outcome outcome{};
  Wait(120, ^(dispatch_block_t done) {
    [store installPack:pack engine:engine identity:identity replace:replace confirmed:confirmed completion:^(NSDictionary *result, NSError *error) {
      CHECK(NSThread.isMainThread, "install completion off the main thread");
      outcome.result = result;
      outcome.error = error;
      done();
    }];
  });
  return outcome;
}

static NSError *Remove(NeoTexturePackStore *store, NSDictionary *installed, id<NeoTextureEngine> engine) {
  __block NSError *failure = nil;
  Wait(60, ^(dispatch_block_t done) {
    [store removeInstalled:installed engine:engine completion:^(NSError *error) { failure = error; done(); }];
  });
  return failure;
}

static NSDictionary *Identity(NSString *system, NSString *type, NSString *scheme, NSString *value, NSString *title) {
  return @{@"system": system, @"title": title, @"identities": @[@{@"type": type, @"scheme": scheme, @"value": value}]};
}

static NSArray<NSString *> *Files(NSString *folder) {
  NSMutableArray *files = [NSMutableArray array];
  for (NSString *path in [FM() enumeratorAtPath:folder]) {
    BOOL directory = NO;
    if ([FM() fileExistsAtPath:[folder stringByAppendingPathComponent:path] isDirectory:&directory] && !directory) [files addObject:path];
  }
  return [files sortedArrayUsingSelector:@selector(compare:)];
}

int main(int argc, char **argv) {
  @autoreleasepool {
    if (argc != 3) return 64;
    NSDictionary *fixtures = JSON(@(argv[1]));
    NSString *work = @(argv[2]);
    CHECK(fixtures != nil, "fixtures.json unreadable");
    NeoTexSetRegistryPath([work stringByAppendingPathComponent:@"registry/installed.json"]);

    // 1. The bundled index the IPA carries: every pack accepted by the app's validator.
    NSData *bundled = [NSData dataWithContentsOfFile:fixtures[@"bundledManifest"]];
    NSError *error = nil;
    NSDictionary *index = [NeoTextureCatalog validatedIndex:bundled error:&error];
    CHECK(index != nil, "bundled index refused: %s", error.description.UTF8String);
    CHECK([index[@"rejected_packs"] integerValue] == 0, "bundled index: %ld packs rejected", (long)[index[@"rejected_packs"] integerValue]);
    CHECK([index[@"packs"] count] == [fixtures[@"bundledPackCount"] unsignedIntegerValue], "bundled index: %lu packs",
          (unsigned long)[index[@"packs"] count]);
    NSUInteger available = 0;
    for (NSDictionary *pack in index[@"packs"]) available += [pack[@"availability"] isEqual:@"available"];
    CHECK(available == [fixtures[@"bundledAvailableCount"] unsignedIntegerValue], "bundled index: %lu available", (unsigned long)available);

    // 2. Offline use, failed refresh, successful refresh.
    NeoTextureCatalog *catalogue = [NeoTextureCatalog new];
    catalogue.storageDirectory = [work stringByAppendingPathComponent:@"catalogue"];
    catalogue.bundledDirectory = [fixtures[@"bundledManifest"] stringByDeletingLastPathComponent];
    NSDictionary *snapshot = catalogue.snapshot;
    CHECK([snapshot[@"state"] isEqual:@"bundled"] && [snapshot[@"pack_count"] isEqual:@([index[@"packs"] count])], "bundled snapshot %s",
          snapshot.description.UTF8String);
    catalogue.fetch = ^(NSURL *url, NSUInteger maximum, void (^completion)(NSData *, NSError *)) {
      completion(nil, [NSError errorWithDomain:NSURLErrorDomain code:NSURLErrorNotConnectedToInternet userInfo:nil]);
    };
    __block NSDictionary *refreshed = nil;
    __block NSError *refreshError = nil;
    Wait(30, ^(dispatch_block_t done) {
      [catalogue refreshWithCompletion:^(NSDictionary *value, NSError *failure) { refreshed = value; refreshError = failure; done(); }];
    });
    CHECK(refreshError != nil && [refreshed[@"state"] isEqual:@"bundled"] && [refreshed[@"pack_count"] isEqual:@([index[@"packs"] count])],
          "a failed refresh must keep the catalogue: %s", refreshed.description.UTF8String);
    CHECK(refreshed[@"refresh_error"] != nil, "a failed refresh is recorded");
    catalogue.fetch = ^(NSURL *url, NSUInteger maximum, void (^completion)(NSData *, NSError *)) {
      completion([@"<!DOCTYPE html><html><head></head></html>" dataUsingEncoding:NSUTF8StringEncoding], nil);
    };
    Wait(30, ^(dispatch_block_t done) {
      [catalogue refreshWithCompletion:^(NSDictionary *value, NSError *failure) { refreshed = value; refreshError = failure; done(); }];
    });
    CHECK(refreshError != nil && [refreshed[@"pack_count"] isEqual:@([index[@"packs"] count])], "a web page never replaces the index");
    catalogue.fetch = ^(NSURL *url, NSUInteger maximum, void (^completion)(NSData *, NSError *)) { completion(bundled, nil); };
    Wait(30, ^(dispatch_block_t done) {
      [catalogue refreshWithCompletion:^(NSDictionary *value, NSError *failure) { refreshed = value; refreshError = failure; done(); }];
    });
    CHECK(!refreshError && [refreshed[@"state"] isEqual:@"downloaded"] && !refreshed[@"refresh_error"], "refresh: %s", refreshed.description.UTF8String);
    NeoTextureCatalog *offline = [NeoTextureCatalog new];
    offline.storageDirectory = catalogue.storageDirectory;
    offline.bundledDirectory = nil;
    CHECK([offline.snapshot[@"state"] isEqual:@"downloaded"] && [offline.snapshot[@"pack_count"] isEqual:@([index[@"packs"] count])],
          "the downloaded index is read offline");

    // 3. Matching on the real catalogue: typed IDs, region-free Dolphin folders, never a title alone.
    for (NSDictionary *probe in fixtures[@"matches"]) {
      NSArray *rows = [catalogue packsForIdentity:probe[@"identity"] engine:probe[@"engine"]];
      NSMutableDictionary *found = [NSMutableDictionary dictionary];
      for (NSDictionary *row in rows) found[row[@"id"]] = row[@"match"];
      for (NSString *packID in probe[@"exact"]) CHECK([found[packID] isEqual:@"exact"], "%s should match %s exactly (got %s)",
                                                      packID.UTF8String, [probe[@"identity"] description].UTF8String, [found[packID] description].UTF8String);
      for (NSString *packID in probe[@"candidate"]) CHECK([found[packID] isEqual:@"candidate"], "%s should be a candidate for %s (got %s)",
                                                          packID.UTF8String, [probe[@"identity"] description].UTF8String, [found[packID] description].UTF8String);
      for (NSString *packID in probe[@"absent"]) CHECK(!found[packID], "%s must not match %s", packID.UTF8String, [probe[@"identity"] description].UTF8String);
    }

    // 4. Store with the local fixture packs, served by the injectable transport.
    NSDictionary *served = fixtures[@"served"];  // url -> local file
    NeoTexturePackStore *store = [NeoTexturePackStore new];
    store.downloadDirectory = [work stringByAppendingPathComponent:@"downloads"];
    __block NSUInteger requests = 0;
    store.transport = ^(NSURL *url, NSString *destination, unsigned long long offset, void (^progress)(unsigned long long),
                        void (^completion)(NSString *, NSError *)) {
      requests++;
      NSString *local = served[url.absoluteString];
      dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
        if (!local) { completion(nil, [NSError errorWithDomain:NSURLErrorDomain code:404 userInfo:nil]); return; }
        NSData *body = [NSData dataWithContentsOfFile:local];
        [body writeToFile:destination atomically:YES];
        progress(body.length);
        completion([local hasSuffix:@".html"] ? @"text/html; charset=utf-8" : @"application/octet-stream", nil);
      });
    };
    NSDictionary *packs = fixtures[@"packs"];

    // 4a. Dolphin: 7z with a subtree, per-game switch, effective folder, update, conflict, removal.
    NSString *dolphinUser = [work stringByAppendingPathComponent:@"Dolphin/User"];
    id<NeoTextureEngine> dolphin = [NeoTextureEngines dolphinWithUserDirectory:dolphinUser];
    NSString *textures = dolphin.texturesRoot;
    [FM() createDirectoryAtPath:[textures stringByAppendingPathComponent:@"OTHER1"] withIntermediateDirectories:YES attributes:nil error:nil];
    [@"keep" writeToFile:[textures stringByAppendingPathComponent:@"OTHER1/tex1_keep.png"] atomically:YES encoding:NSUTF8StringEncoding error:nil];
    [FM() createDirectoryAtPath:[dolphinUser stringByAppendingPathComponent:@"GameSettings"] withIntermediateDirectories:YES attributes:nil error:nil];
    NSString *settings = [dolphinUser stringByAppendingPathComponent:@"GameSettings/GZ2E01.ini"];
    [@"[Core]\nCPUThread = False\n# user comment\n" writeToFile:settings atomically:YES encoding:NSUTF8StringEncoding error:nil];
    NSDictionary *zelda = Identity(@"gc", @"game_id", @"dolphin-disc-game-id", @"GZ2E01", @"Synthetic Twilight");
    CHECK([[dolphin activationForIdentity:zelda][@"enabled"] isEqual:@NO], "HD textures off before a pack");
    Outcome outcome = Install(store, packs[@"dolphin7z"], dolphin, zelda, NO, NO);
    CHECK(!outcome.error, "dolphin 7z install: %s", outcome.error.description.UTF8String);
    CHECK([outcome.result[@"activated"] boolValue], "a first pack switches the game on: %s", outcome.result.description.UTF8String);
    NSArray *installedFiles = Files([textures stringByAppendingPathComponent:@"GZ2E01"]);
    CHECK([installedFiles isEqualToArray:(@[@"NeoStation-pack.json", @"sub/tex1_b.dds", @"tex1_a.png"])], "dolphin files %s", installedFiles.description.UTF8String);
    NSString *ini = Text(settings);
    CHECK([ini containsString:@"CPUThread = False"] && [ini containsString:@"# user comment"], "other GameSettings lines kept: %s", ini.UTF8String);
    CHECK([NeoTextureINIValue(ini, @"Video_Settings", @"HiresTextures") isEqualToString:@"True"], "HiresTextures written: %s", ini.UTF8String);
    CHECK([NeoTextureINIValue(ini, @"Video_Settings", @"CacheHiresTextures") isEqualToString:@"False"], "no preloading of the whole pack");
    CHECK([[dolphin activationForIdentity:zelda][@"enabled"] isEqual:@YES], "activation read back");
    CHECK([[dolphin effectiveFoldersForIdentity:zelda] isEqualToArray:@[@"GZ2E01"]], "effective folders %s",
          [dolphin effectiveFoldersForIdentity:zelda].description.UTF8String);
    NSArray *rows = [store installedForIdentity:zelda engine:dolphin];
    CHECK(rows.count == 1 && [rows[0][@"pack_id"] isEqual:packs[@"dolphin7z"][@"id"]] && ![rows[0][@"manual"] boolValue], "installed rows %s",
          rows.description.UTF8String);
    CHECK(Exists([textures stringByAppendingPathComponent:@"OTHER1/tex1_keep.png"]), "other folders untouched");
    // The verified archive is not kept once its textures are installed.
    CHECK(![FM() contentsOfDirectoryAtPath:store.downloadDirectory error:nil].count, "download folder emptied: %s",
          [FM() contentsOfDirectoryAtPath:store.downloadDirectory error:nil].description.UTF8String);
    // Switch off and on again through the adapter.
    CHECK([dolphin setActivation:NO identity:zelda error:nil] && [[dolphin activationForIdentity:zelda][@"enabled"] isEqual:@NO], "switch off");
    CHECK([dolphin setActivation:YES identity:zelda error:nil] && [[dolphin activationForIdentity:zelda][@"enabled"] isEqual:@YES], "switch on");
    // Another pack for the same folder: asked first, nothing changed until confirmed.
    outcome = Install(store, packs[@"dolphinOther"], dolphin, zelda, NO, NO);
    CHECK(outcome.error.code == NeoTexturePackErrorConflict, "conflict expected, got %s", outcome.error.description.UTF8String);
    CHECK([Files([textures stringByAppendingPathComponent:@"GZ2E01"]) isEqualToArray:installedFiles], "conflict left the folder unchanged");
    // The same pack's new version replaces the folder atomically.
    outcome = Install(store, packs[@"dolphin7zUpdate"], dolphin, zelda, NO, NO);
    CHECK(!outcome.error, "update: %s", outcome.error.description.UTF8String);
    CHECK([Files([textures stringByAppendingPathComponent:@"GZ2E01"]) isEqualToArray:(@[@"NeoStation-pack.json", @"tex1_c.png"])], "update replaced the files");
    rows = [store installedForIdentity:zelda engine:dolphin];
    CHECK(rows.count == 1 && [rows[0][@"version"] isEqual:packs[@"dolphin7zUpdate"][@"version"]], "updated version recorded");
    // A changed file on the author's server is refused before anything is written.
    outcome = Install(store, packs[@"dolphinChanged"], dolphin, zelda, YES, NO);
    CHECK(outcome.error.code == NeoTexturePackErrorChanged, "changed file: %s", outcome.error.description.UTF8String);
    outcome = Install(store, packs[@"dolphinHTML"], dolphin, zelda, YES, NO);
    CHECK(outcome.error.code == NeoTexturePackErrorHTML, "web page instead of an archive: %s", outcome.error.description.UTF8String);
    // Not enough free space: nothing is downloaded.
    NSUInteger before = requests;
    store.freeSpace = ^unsigned long long(NSString *path) { return 1024; };
    outcome = Install(store, packs[@"dolphinOther"], dolphin, zelda, YES, NO);
    CHECK(outcome.error.code == NeoTexturePackErrorSpace && requests == before, "space check first: %s", outcome.error.description.UTF8String);
    store.freeSpace = ^unsigned long long(NSString *path) { return 1ULL << 40; };
    CHECK([Files([textures stringByAppendingPathComponent:@"GZ2E01"]) isEqualToArray:(@[@"NeoStation-pack.json", @"tex1_c.png"])], "failures kept the pack");
    // Marker layout: the pack keeps its own folder and Load/<ID3>.txt; Dolphin reads it for every region.
    NSDictionary *kart = Identity(@"wii", @"game_id", @"dolphin-disc-game-id", @"RMCP01", @"Synthetic Kart");
    outcome = Install(store, packs[@"dolphinMarker"], dolphin, kart, NO, NO);
    CHECK(!outcome.error, "marker pack: %s", outcome.error.description.UTF8String);
    NSArray *markerFiles = Files([textures stringByAppendingPathComponent:@"Kart-HD"]);
    CHECK([markerFiles isEqualToArray:(@[@"Load/RMC.txt", @"NeoStation-pack.json", @"Regular/tex1_x.png"])], "marker files %s", markerFiles.description.UTF8String);
    CHECK([[dolphin effectiveFoldersForIdentity:kart] containsObject:@"Kart-HD"], "marker folder read for RMCP01: %s",
          [dolphin effectiveFoldersForIdentity:kart].description.UTF8String);
    CHECK(![[dolphin effectiveFoldersForIdentity:zelda] containsObject:@"Kart-HD"], "marker folder not read for another game");
    // Removal: only the pack's folder; the game settings and other folders stay.
    rows = [store installedForIdentity:zelda engine:dolphin];
    CHECK(!Remove(store, rows.firstObject, dolphin), "remove");
    CHECK(!Exists([textures stringByAppendingPathComponent:@"GZ2E01"]) && Exists(settings) &&
          Exists([textures stringByAppendingPathComponent:@"OTHER1/tex1_keep.png"]) && Exists([textures stringByAppendingPathComponent:@"Kart-HD"]),
          "removal limited to the pack folder");

    // 4b. PPSSPP: textures.ini at the root, folder named after the game's disc ID ({id}), per-game core option.
    NSString *saves = [work stringByAppendingPathComponent:@"Libretro/Saves"];
    NSString *config = [work stringByAppendingPathComponent:@"Libretro/Config"];
    id<NeoTextureEngine> ppsspp = [NeoTextureEngines ppssppWithSaveDirectory:[saves stringByAppendingPathComponent:@"PPSSPP"] configDirectory:config];
    NSMutableDictionary *gta = [Identity(@"psp", @"disc_id", @"psp-param-sfo-disc-id", @"ULES00151", @"Synthetic Stories") mutableCopy];
    gta[@"gameKey"] = @"psp/Synthetic Stories (Europe)";
    [FM() createDirectoryAtPath:[config stringByAppendingPathComponent:@"Games"] withIntermediateDirectories:YES attributes:nil error:nil];
    NSString *games = [config stringByAppendingPathComponent:@"Games/PPSSPP.json"];
    [@"{\"version\":1,\"games\":{\"psp/Other\":{\"ppsspp_internal_resolution\":\"2\"}},\"unknown\":true}" writeToFile:games atomically:YES encoding:NSUTF8StringEncoding error:nil];
    outcome = Install(store, packs[@"ppsspp"], ppsspp, gta, NO, NO);
    CHECK(!outcome.error, "ppsspp install: %s", outcome.error.description.UTF8String);
    NSString *pspFolder = [saves stringByAppendingPathComponent:@"PPSSPP/PSP/TEXTURES/ULES00151"];
    CHECK([Files(pspFolder) isEqualToArray:(@[@"NeoStation-pack.json", @"new/a.png", @"textures.ini"])], "ppsspp files %s", Files(pspFolder).description.UTF8String);
    NSDictionary *stored = JSON(games);
    CHECK([stored[@"games"][@"psp/Synthetic Stories (Europe)"][@"ppsspp_texture_replacement"] isEqual:@"enabled"], "per-game option: %s",
          stored.description.UTF8String);
    CHECK([stored[@"games"][@"psp/Other"][@"ppsspp_internal_resolution"] isEqual:@"2"] && [stored[@"unknown"] isEqual:@YES], "other games and keys kept");
    NSDictionary *activation = [ppsspp activationForIdentity:gta];
    CHECK([activation[@"enabled"] isEqual:@YES] && [activation[@"appliesAt"] isEqual:@"next-launch"], "ppsspp activation %s", activation.description.UTF8String);
    // During the game the running core's option store is used, never the file.
    __block NSString *liveValue = nil;
    [NeoTextureEngines setLibretroSessionReader:^NSString *(NSString *key, NSString *gameKey) { return liveValue ?: @"disabled"; }
                                         writer:^BOOL(NSString *key, NSString *value, NSString *gameKey) { liveValue = value; return YES; }
                                      forEngine:ppsspp];
    CHECK([ppsspp setActivation:NO identity:gta error:nil] && [liveValue isEqual:@"disabled"], "session write");
    CHECK([JSON(games)[@"games"][@"psp/Synthetic Stories (Europe)"][@"ppsspp_texture_replacement"] isEqual:@"enabled"], "file untouched in a session");
    [NeoTextureEngines setLibretroSessionReader:nil writer:nil forEngine:ppsspp];

    // 4c. Azahar: pack.json kept at the root of the title ID folder, option citra_custom_textures.
    id<NeoTextureEngine> azahar = [NeoTextureEngines azaharWithUserDirectory:[saves stringByAppendingPathComponent:@"Azahar/Azahar"] configDirectory:config];
    NSMutableDictionary *ocarina = [Identity(@"3ds", @"title_id", @"3ds-title-id", @"0004000000033500", @"Synthetic Ocarina") mutableCopy];
    ocarina[@"gameKey"] = @"3ds/Synthetic Ocarina";
    outcome = Install(store, packs[@"azahar"], azahar, ocarina, NO, NO);
    CHECK(!outcome.error, "azahar install: %s", outcome.error.description.UTF8String);
    NSString *n3dsFolder = [saves stringByAppendingPathComponent:@"Azahar/Azahar/load/textures/0004000000033500"];
    CHECK([Files(n3dsFolder) isEqualToArray:(@[@"NeoStation-pack.json", @"pack.json", @"tex1_8x8_0123456789ABCDEF_12.png"])], "azahar files %s",
          Files(n3dsFolder).description.UTF8String);
    CHECK([JSON([config stringByAppendingPathComponent:@"Games/Azahar.json"])[@"games"][@"3ds/Synthetic Ocarina"][@"citra_custom_textures"] isEqual:@"enabled"],
          "azahar per-game option");

    // 4c'. Mupen64Plus-Next (GLideN64): <System>/Mupen64plus/hires_texture/<ROM name>, per-game
    // core options True/False with the full alpha channel and the enhanced storage.
    NSString *libretroSystem = [work stringByAppendingPathComponent:@"Libretro/System"];
    id<NeoTextureEngine> mupen = [NeoTextureEngines mupen64plusWithSystemDirectory:libretroSystem configDirectory:config];
    [NeoTextureIdentityReader setCachePath:[work stringByAppendingPathComponent:@"identities-n64.json"]];
    NSString *romProblem = nil;
    NSMutableDictionary *kart64 = [[NeoTextureIdentityReader identityForPath:fixtures[@"n64Rom"] system:@"n64" title:@"Synthetic Kart 64"
                                                                     problem:&romProblem] mutableCopy];
    CHECK([kart64[@"identities"][0][@"scheme"] isEqual:@"n64-rom-name-hex"] && [[mupen folderForIdentity:kart64] isEqual:@"SYNTHETIC KART 64"] &&
          [kart64[@"regions"] isEqual:@[@"USA"]], "n64 identity %s (%s)", kart64.description.UTF8String, romProblem.UTF8String);
    kart64[@"gameKey"] = @"n64/Synthetic Kart 64 (USA)";
    CHECK([mupen supportsSystem:@"n64"] && ![mupen supportsSystem:@"psp"] && [mupen acceptsFile:@"a/SYNTHETIC KART 64#0123ABCD#0#2_all.png"] &&
          ![mupen acceptsFile:@"a/preview.png"], "mupen64plus filters");
    CHECK([[NeoTextureCatalog pack:packs[@"mupen64plus"] matchedTo:kart64][@"match"] isEqual:@"exact"], "n64 pack matched by the ROM name");
    // GLideNHQ's caches of this ROM name (and another game's, kept) from an earlier pack.
    NSString *n64Cache = [libretroSystem stringByAppendingPathComponent:@"Mupen64plus/cache"];
    NSArray<NSString *> *kartCaches = @[[n64Cache stringByAppendingPathComponent:@"SYNTHETIC KART 64_HIRESTEXTURES.hts"],
                                        [n64Cache stringByAppendingPathComponent:@"SYNTHETIC KART 64_HIRESTEXTURES.htc"]];
    NSString *otherCache = [n64Cache stringByAppendingPathComponent:@"SUPER MARIO 64_HIRESTEXTURES.hts"];
    [FM() createDirectoryAtPath:n64Cache withIntermediateDirectories:YES attributes:nil error:nil];
    for (NSString *path in [kartCaches arrayByAddingObject:otherCache]) [[NSData dataWithBytes:"old" length:3] writeToFile:path atomically:YES];
    outcome = Install(store, packs[@"mupen64plus"], mupen, kart64, NO, NO);
    CHECK(!outcome.error, "mupen64plus install: %s", outcome.error.description.UTF8String);
    CHECK(!Exists(kartCaches[0]) && !Exists(kartCaches[1]) && Exists(otherCache), "mupen64plus install drops the stale hi-res caches of its ROM only");
    NSString *n64Folder = [libretroSystem stringByAppendingPathComponent:@"Mupen64plus/hires_texture/SYNTHETIC KART 64"];
    CHECK([Files(n64Folder) isEqualToArray:(@[@"NeoStation-pack.json", @"ui/SYNTHETIC KART 64#0123ABCD#0#2_all.png"])], "mupen64plus files %s",
          Files(n64Folder).description.UTF8String);
    NSDictionary *n64Options = JSON([config stringByAppendingPathComponent:@"Games/Mupen64Plus-Next.json"])[@"games"][@"n64/Synthetic Kart 64 (USA)"];
    CHECK([n64Options[@"mupen64plus-txHiresEnable"] isEqual:@"True"] && [n64Options[@"mupen64plus-txHiresFullAlphaChannel"] isEqual:@"True"] &&
          [n64Options[@"mupen64plus-EnableEnhancedHighResStorage"] isEqual:@"True"], "mupen64plus per-game options %s", n64Options.description.UTF8String);
    activation = [mupen activationForIdentity:kart64];
    CHECK([activation[@"enabled"] isEqual:@YES] && [activation[@"setting"] isEqual:@"mupen64plus-txHiresEnable"], "mupen64plus activation %s",
          activation.description.UTF8String);
    CHECK([mupen setActivation:NO identity:kart64 error:nil] &&
          [JSON([config stringByAppendingPathComponent:@"Games/Mupen64Plus-Next.json"])[@"games"][@"n64/Synthetic Kart 64 (USA)"][@"mupen64plus-txHiresEnable"] isEqual:@"False"] &&
          ![[mupen activationForIdentity:kart64][@"enabled"] boolValue], "mupen64plus switched off");
    rows = [store installedForIdentity:kart64 engine:mupen];
    [[NSData dataWithBytes:"new" length:3] writeToFile:kartCaches[0] atomically:YES];
    CHECK(rows.count == 1 && !Remove(store, rows.firstObject, mupen) && !Exists(n64Folder) &&
          Exists([libretroSystem stringByAppendingPathComponent:@"Mupen64plus/hires_texture"]), "mupen64plus removal limited to the ROM folder");
    CHECK(!Exists(kartCaches[0]) && Exists(otherCache), "mupen64plus removal drops the hi-res cache built from the removed pack");

    // 4e. Beetle PSX HW: <Saves>/Beetle PSX HW/<content name>-texture-replacements (the
    // core's HD Texture Folder "save"), next to the game's memory cards; Track + Replace per game.
    NSString *beetleSaves = [saves stringByAppendingPathComponent:@"Beetle PSX HW"];
    id<NeoTextureEngine> beetle = [NeoTextureEngines beetleWithSaveDirectory:beetleSaves configDirectory:config];
    [FM() createDirectoryAtPath:beetleSaves withIntermediateDirectories:YES attributes:nil error:nil];
    NSData *card = [NSData dataWithBytes:"MC\0\0" length:4];
    for (NSString *name in @[@"Castle (USA).mcr", @"Castle (USA).1.mcr"]) [card writeToFile:[beetleSaves stringByAppendingPathComponent:name] atomically:YES];
    NSMutableDictionary *castle = [Identity(@"ps1", @"serial", @"ps1-disc-serial", @"SLUS-00067", @"Synthetic Castle") mutableCopy];
    castle[@"path"] = @"/Library/roms/psx/Castle (USA).cue";
    castle[@"gameKey"] = @"psx/Castle (USA).cue";
    CHECK([beetle supportsSystem:@"ps1"] && ![beetle supportsSystem:@"ps2"] && [[beetle folderForIdentity:castle] isEqual:@"Castle (USA)-texture-replacements"],
          "beetle folder %s", [beetle folderForIdentity:castle].UTF8String);
    NSMutableDictionary *zipped = [castle mutableCopy];
    zipped[@"path"] = @"/Library/roms/psx/Castle (USA).zip";
    CHECK(![beetle folderForIdentity:zipped] && [[beetle folderProblemForIdentity:zipped] isEqual:@"zipContent"], "a zipped game has no Beetle folder");
    CHECK([beetle acceptsFile:@"1a2b-0.png"] && [beetle acceptsFile:@"prefetch.journal"] && ![beetle acceptsFile:@"sub/1a2b-0.png"] &&
          ![beetle acceptsFile:@"readme.txt"], "beetle filters");
    CHECK([[beetle activationForIdentity:castle][@"enabled"] isEqual:@NO], "beetle replacement off before a pack");
    outcome = Install(store, packs[@"beetle"], beetle, castle, NO, NO);
    CHECK(!outcome.error && [outcome.result[@"activated"] boolValue], "beetle install: %s %s", outcome.error.description.UTF8String,
          outcome.result.description.UTF8String);
    NSString *beetleFolder = [beetleSaves stringByAppendingPathComponent:@"Castle (USA)-texture-replacements"];
    CHECK([Files(beetleFolder) isEqualToArray:(@[@"1a2b-0.png", @"3C4D-FF.dds", @"NeoStation-pack.json"])], "beetle files %s",
          Files(beetleFolder).description.UTF8String);
    NSString *beetleStore = [config stringByAppendingPathComponent:@"Games/Beetle PSX HW.json"];
    NSDictionary *beetleOptions = JSON(beetleStore)[@"games"][@"psx/Castle (USA).cue"];
    CHECK([beetleOptions[@"beetle_psx_hw_track_textures"] isEqual:@"enabled"] && [beetleOptions[@"beetle_psx_hw_replace_textures"] isEqual:@"enabled"],
          "beetle per-game options %s", beetleOptions.description.UTF8String);
    CHECK(!beetleOptions[@"beetle_psx_hw_dump_textures"], "dumping is never written by the switch");
    CHECK([beetle setActivation:NO identity:castle error:nil] && ![[beetle activationForIdentity:castle][@"enabled"] boolValue] &&
          [JSON(beetleStore)[@"games"][@"psx/Castle (USA).cue"][@"beetle_psx_hw_track_textures"] isEqual:@"disabled"],
          "beetle switched off (both options)");
    // Replacing needs both options: one alone reads as off.
    __block NSDictionary *beetleLive = @{@"beetle_psx_hw_track_textures": @"enabled", @"beetle_psx_hw_replace_textures": @"disabled"};
    [NeoTextureEngines setLibretroSessionReader:^NSString *(NSString *key, NSString *gameKey) { return beetleLive[key]; }
                                         writer:^BOOL(NSString *key, NSString *value, NSString *gameKey) {
                                           NSMutableDictionary *next = [beetleLive mutableCopy];
                                           next[key] = value;
                                           beetleLive = next;
                                           return YES;
                                         }
                                      forEngine:beetle];
    CHECK(![[beetle activationForIdentity:castle][@"enabled"] boolValue], "track alone is not replacement");
    CHECK([beetle setActivation:YES identity:castle error:nil] && [beetleLive[@"beetle_psx_hw_replace_textures"] isEqual:@"enabled"] &&
          [[beetle activationForIdentity:castle][@"enabled"] boolValue], "beetle session write");
    [NeoTextureEngines setLibretroSessionReader:nil writer:nil forEngine:beetle];
    rows = [store installedForIdentity:castle engine:beetle];
    CHECK(rows.count == 1 && !Remove(store, rows.firstObject, beetle) && !Exists(beetleFolder), "beetle removal");
    CHECK([[NSData dataWithContentsOfFile:[beetleSaves stringByAppendingPathComponent:@"Castle (USA).mcr"]] isEqualToData:card] &&
          [[NSData dataWithContentsOfFile:[beetleSaves stringByAppendingPathComponent:@"Castle (USA).1.mcr"]] isEqualToData:card],
          "memory cards kept byte for byte");

    // 4f. A manual pack whose author's file was verified on CI (download.verified): never
    // downloaded, installed only from that exact file chosen by the user; any other file refused.
    NSDictionary *verifiedIndex = @{@"catalogue_id": @"neostation-hd-textures", @"schema_version": @1, @"revision": @"test",
                                    @"packs": @[packs[@"verifiedManual"], packs[@"verifiedMalformed"]]};
    NSDictionary *checked = [NeoTextureCatalog validatedIndex:NeoTexJSONData(verifiedIndex) error:nil];
    CHECK([checked[@"packs"] count] == 2 && NeoTexVerifiedFile(checked[@"packs"][0]) && !checked[@"packs"][1][@"download"][@"verified"] &&
          !checked[@"packs"][1][@"install"], "verified manual pack kept, malformed record reduced to a page link: %s", checked.description.UTF8String);
    NSDictionary *melee = Identity(@"gc", @"game_id", @"dolphin-disc-game-id", @"GALE01", @"Synthetic Melee");
    NSUInteger beforeManual = requests;
    outcome = Install(store, packs[@"verifiedManual"], dolphin, melee, NO, NO);
    CHECK(outcome.error.code == NeoTexturePackErrorManual && requests == beforeManual, "a verified manual pack is never downloaded: %s",
          outcome.error.description.UTF8String);
    __block Outcome imported{};
    void (^importFile)(NSString *) = ^(NSString *path) {
      Wait(120, ^(dispatch_block_t done) {
        [store installPack:packs[@"verifiedManual"] fromFile:[NSURL fileURLWithPath:path] engine:dolphin identity:melee replace:NO confirmed:NO
                completion:^(NSDictionary *result, NSError *error) {
                  CHECK(NSThread.isMainThread, "import completion off the main thread");
                  imported.result = result;
                  imported.error = error;
                  done();
                }];
      });
    };
    importFile(fixtures[@"otherFile"]);
    CHECK(imported.error.code == NeoTexturePackErrorNotVerified && !Exists([textures stringByAppendingPathComponent:@"GALE01"]),
          "another file is refused before anything is installed: %s", imported.error.description.UTF8String);
    NSArray<NSString *> *(^verifiedCopies)(void) = ^NSArray<NSString *> *(void) {
      NSMutableArray *left = [NSMutableArray array];
      for (NSString *name in [FM() contentsOfDirectoryAtPath:store.downloadDirectory error:nil])
        if ([name hasPrefix:@"fixture-verified-manual@"])
          for (NSString *inner in [FM() contentsOfDirectoryAtPath:[store.downloadDirectory stringByAppendingPathComponent:name] error:nil])
            [left addObject:[name stringByAppendingPathComponent:inner]];
      return left;
    };
    CHECK(!verifiedCopies().count, "a refused import left %s", verifiedCopies().description.UTF8String);
    NSData *original = [NSData dataWithContentsOfFile:fixtures[@"hostedFile"]];
    importFile(fixtures[@"hostedFile"]);
    CHECK(!imported.error && [imported.result[@"activated"] boolValue], "verified file installed: %s", imported.error.description.UTF8String);
    CHECK([Files([textures stringByAppendingPathComponent:@"GALE01"]) isEqualToArray:(@[@"NeoStation-pack.json", @"tex1_m.png"])], "verified files %s",
          Files([textures stringByAppendingPathComponent:@"GALE01"]).description.UTF8String);
    rows = [store installedForIdentity:melee engine:dolphin];
    CHECK(rows.count == 1 && [rows[0][@"pack_id"] isEqual:@"fixture-verified-manual"] &&
          [rows[0][@"sha256"] isEqual:packs[@"verifiedManual"][@"download"][@"verified"][@"sha256"]], "installed as the catalogue pack: %s",
          rows.description.UTF8String);
    CHECK([[NSData dataWithContentsOfFile:fixtures[@"hostedFile"]] isEqualToData:original], "the user's file is left as it was");
    CHECK(!verifiedCopies().count, "the copy is dropped once installed: %s", verifiedCopies().description.UTF8String);
    CHECK(!Remove(store, rows.firstObject, dolphin), "verified pack removal");

    // 4d. ARMSX2: downloaded and verified here, installed by the Build 485 store (direct ZIP and expanded 7z).
    NSString *armsx2Data = [work stringByAppendingPathComponent:@"ARMSX2"];
    id<NeoTextureEngine> armsx2 = [NeoTextureEngines armsx2WithDataDirectory:armsx2Data gamePath:nil host:nil];
    CHECK([armsx2 respondsToSelector:@selector(installsPacks)] && [armsx2 installsPacks], "the ARMSX2 store is reachable");
    NSDictionary *ps2 = Identity(@"ps2", @"serial", @"ps2-disc-serial", @"SLUS-21137", @"Synthetic PS2");
    outcome = Install(store, packs[@"armsx2zip"], armsx2, ps2, NO, NO);
    CHECK(!outcome.error, "armsx2 zip: %s", outcome.error.description.UTF8String);
    NSString *ps2Folder = [armsx2Data stringByAppendingPathComponent:@"textures/SLUS-21137/replacements"];
    NSArray *ps2Files = Files(ps2Folder);
    CHECK([ps2Files containsObject:@"ui/0123456789abcdef-00004a2d.png"] && [ps2Files containsObject:@"fedcba9876543210-0000a1b2.dds"],
          "armsx2 files %s", ps2Files.description.UTF8String);
    rows = [store installedForIdentity:ps2 engine:armsx2];
    CHECK(rows.count == 1 && [rows[0][@"pack_id"] isEqual:packs[@"armsx2zip"][@"id"]], "armsx2 row recognised as the catalogue pack: %s",
          rows.description.UTF8String);
    activation = [armsx2 activationForIdentity:ps2];
    CHECK([activation[@"known"] boolValue] && [activation[@"enabled"] isEqual:@YES], "first PS2 pack switched on for the game: %s",
          activation.description.UTF8String);
    // Passed without "match", as a pack reopened from its installed row: the
    // store finds its exact match itself, so the subtree (named after no
    // serial) installs without a question.
    outcome = Install(store, packs[@"armsx27z"], armsx2, ps2, YES, NO);
    CHECK(!outcome.error, "armsx2 7z (expanded then handed over): %s", outcome.error.description.UTF8String);
    ps2Files = Files(ps2Folder);
    CHECK([ps2Files containsObject:@"1111222233334444-r64x32-0000c3d4.astc"] && ![ps2Files containsObject:@"fedcba9876543210-0000a1b2.dds"],
          "armsx2 replacement %s", ps2Files.description.UTF8String);
    // A caller's "exact" is not trusted: for a game the pack does not list, the engine's doubt is asked.
    NSMutableDictionary *claimed = [packs[@"armsx27z"] mutableCopy];
    claimed[@"match"] = @"exact";
    NSDictionary *otherPS2 = Identity(@"ps2", @"serial", @"ps2-disc-serial", @"SLES-50000", @"Another PS2");
    outcome = Install(store, claimed, armsx2, otherPS2, YES, NO);
    CHECK(outcome.error.code == NeoTexturePackErrorRegion && [outcome.error.userInfo[@"engine"][@"match"] isEqual:@"noSerial"],
          "a pack for another game must be confirmed: %s", outcome.error.description.UTF8String);
    CHECK(!Exists([armsx2Data stringByAppendingPathComponent:@"textures/SLES-50000"]) && [Files(ps2Folder) isEqualToArray:ps2Files],
          "nothing written before the confirmation");
    BOOL leftover = NO;
    for (NSString *name in [FM() contentsOfDirectoryAtPath:[armsx2Data stringByAppendingPathComponent:@"textures"] error:nil])
      if ([name hasPrefix:@".neostation-"]) leftover = YES;
    CHECK(!leftover, "no expansion or staging folder left behind");
    rows = [store installedForIdentity:ps2 engine:armsx2];
    CHECK(!Remove(store, rows.firstObject, armsx2) && !Exists(ps2Folder), "armsx2 removal through its store");

    // 5. Identity of a real disc header (the reader the page uses for a library file).
    [NeoTextureIdentityReader setCachePath:[work stringByAppendingPathComponent:@"identities.json"]];
    NSString *problem = nil;
    NSDictionary *read = [NeoTextureIdentityReader identityForPath:fixtures[@"gcDisc"] system:@"gc" title:@"Synthetic" problem:&problem];
    CHECK([read[@"identities"][0][@"value"] isEqual:@"GZ2E01"] && [read[@"revision"] isEqual:@"2"], "identity %s (%s)", read.description.UTF8String,
          problem.UTF8String);

    printf("%s texture catalogue store: %d checks, %d failures\n", failures ? "FAIL" : "PASS", checks, failures);
    return failures ? 1 : 0;
  }
}

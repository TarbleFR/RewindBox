#!/usr/bin/env python3
"""The unified HD textures page on UIKit (iOS Simulator), with the real catalogue.

The host application links the production page, catalogue, pack store,
engine adapters and identity reader of packages/neo_texture_catalog, the
Build 485 ARMSX2 store (reached at run time, as in the app), the generated
twelve-language labels and the catalogue bundled in the IPA. No emulator
core, GPU or device is involved: this proves what the page shows for real
library files and catalogue entries, which switch it writes, that a failed
refresh never turns into "no pack", and the twelve languages. It does not
prove that an engine displays a texture.
"""
from pathlib import Path
import json
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
POD = ROOT / 'packages/neo_texture_catalog/ios'
CLASSES = POD / 'Classes'
ARMSX2 = ROOT / 'packages/armsx2_internal_bridge/ios/Classes'
# The HD page shows the Liquid Glass progress view of neo_cheat_catalog
# (598d35d5): the host app compiles it and resolves <neo_cheat_catalog/...>.
CHEAT_CATALOG = ROOT / 'packages/neo_cheat_catalog/ios'
LANGUAGES = ['en', 'es', 'ru', 'zh', 'zh-Hant', 'pt', 'fr', 'de', 'it', 'id', 'ja', 'ko']

APP = r'''
#import <UIKit/UIKit.h>
@interface TextureTestDelegate : UIResponder <UIApplicationDelegate>
@property(nonatomic, strong) UIWindow *window;
@end
@implementation TextureTestDelegate
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)options {
  self.window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
  self.window.rootViewController = [UIViewController new];
  [self.window makeKeyAndVisible];
  return YES;
}
@end
int main(int argc, char **argv) {
  @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(TextureTestDelegate.class)); }
}
'''

TESTS = r'''
#import <XCTest/XCTest.h>
#import <UIKit/UIKit.h>
#import "NeoTextureHDPage.h"
#import "NeoTextureCatalog.h"
#import "NeoTextureEngine.h"
#import "NeoTextureIdentityReader.h"

// The page's model (file-private classes), read through key-value coding.
static NSArray *Sections(UIViewController *page) { return [page valueForKey:@"sections"]; }
static NSArray *Rows(UIViewController *page) {
  NSMutableArray *rows = [NSMutableArray array];
  for (id section in Sections(page)) [rows addObjectsFromArray:[section valueForKey:@"rows"]];
  return rows;
}
static id Row(UIViewController *page, NSString *identifier) {
  for (id row in Rows(page)) if ([[row valueForKey:@"identifier"] isEqual:identifier]) return row;
  return nil;
}
static NSArray<NSString *> *Headers(UIViewController *page) {
  NSMutableArray *headers = [NSMutableArray array];
  for (id section in Sections(page)) [headers addObject:[section valueForKey:@"header"] ?: @""];
  return headers;
}
static NSString *Fixtures(void) { return NSProcessInfo.processInfo.environment[@"TEXTURE_FIXTURES"] ?: @""; }

@interface TextureCatalogPageTests : XCTestCase
@property(nonatomic, copy) NSString *work;
@property(nonatomic, strong) NSDictionary *labels;
@end

@implementation TextureCatalogPageTests
- (void)setUp {
  [super setUp];
  self.work = [NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
  [NSFileManager.defaultManager createDirectoryAtPath:self.work withIntermediateDirectories:YES attributes:nil error:nil];
  NeoTextureCatalog *catalogue = NeoTextureCatalog.sharedCatalog;
  catalogue.bundledDirectory = NSBundle.mainBundle.resourcePath;
  catalogue.storageDirectory = [self.work stringByAppendingPathComponent:@"catalogue"];
  catalogue.fetch = nil;
  [NeoTextureIdentityReader setCachePath:[self.work stringByAppendingPathComponent:@"identities.json"]];
  NSData *data = [NSData dataWithContentsOfURL:[NSBundle.mainBundle URLForResource:@"labels" withExtension:@"json"]];
  self.labels = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
  XCTAssertEqual(self.labels.count, 12u);
}

- (NSString *)disc:(NSString *)gameID revision:(uint8_t)revision {
  NSMutableData *header = [NSMutableData dataWithLength:0x10440];
  unsigned char *bytes = header.mutableBytes;
  memcpy(bytes, gameID.UTF8String, 6);
  bytes[7] = revision;
  const unsigned char magic[4] = {0xC2, 0x33, 0x9F, 0x3D};
  memcpy(bytes + 0x1C, magic, 4);
  NSString *path = [self.work stringByAppendingPathComponent:[gameID stringByAppendingPathExtension:@"iso"]];
  [header writeToFile:path atomically:YES];
  return path;
}

- (UIViewController *)present:(NSDictionary *)options {
  UIViewController *controller = [NeoTextureHDPage textureViewControllerWithOptions:options];
  XCTAssertNotNil(controller);
  UIViewController *root = UIApplication.sharedApplication.windows.firstObject.rootViewController;
  XCTestExpectation *shown = [self expectationWithDescription:@"presented"];
  [root presentViewController:controller animated:NO completion:^{ [shown fulfill]; }];
  [self waitForExpectations:@[shown] timeout:10];
  UIViewController *page = [controller isKindOfClass:UINavigationController.class] ? ((UINavigationController *)controller).viewControllers.firstObject : controller;
  [page loadViewIfNeeded];
  return page;
}

- (void)dismiss {
  UIViewController *root = UIApplication.sharedApplication.windows.firstObject.rootViewController;
  XCTestExpectation *gone = [self expectationWithDescription:@"dismissed"];
  [root dismissViewControllerAnimated:NO completion:^{ [gone fulfill]; }];
  [self waitForExpectations:@[gone] timeout:10];
}

// Waits on the main run loop until the condition holds.
- (BOOL)until:(BOOL (^)(void))condition timeout:(NSTimeInterval)timeout {
  NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:timeout];
  while (!condition() && deadline.timeIntervalSinceNow > 0)
    [NSRunLoop.mainRunLoop runMode:NSDefaultRunLoopMode beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.05]];
  return condition();
}

- (NSString *)label:(NSString *)key language:(NSString *)language { return self.labels[language][key]; }

- (void)testGameCubeGameFromItsDiscListsExactPacksAndWritesTheSwitch {
  NSString *user = [self.work stringByAppendingPathComponent:@"Dolphin/User"];
  UIViewController *page = [self present:@{@"system": @"gc", @"dolphinUser": user, @"gamePath": [self disc:@"GMSE01" revision:0],
                                           @"title": @"Super Mario Sunshine", @"locale": @"fr", @"presentation": @"modal"}];
  XCTAssertEqualObjects(page.title, [self label:@"title" language:@"fr"]);
  XCTAssertTrue([self until:^BOOL { return Row(page, @"neoTexturePack.gc-sms-uhd-4k-dds-qashto") != nil; } timeout:20], @"%@", Rows(page));
  // The game's identifiers are the row's title (its detail only explains an uncertain one).
  NSString *ids = [Row(page, @"neoTextureGameID") valueForKey:@"title"];
  XCTAssertTrue([ids containsString:@"GMSE01"], @"%@", ids);
  NSString *detail = [Row(page, @"neoTexturePack.gc-sms-uhd-4k-dds-qashto") valueForKey:@"detail"];
  XCTAssertTrue([detail containsString:@"qashto"] && [detail containsString:[self label:@"matchExact" language:@"fr"]], @"%@", detail);
  XCTAssertNil(Row(page, @"neoTexturePack.gc-kirby-air-ride-uhd-qashto"), @"another game's pack is not offered");
  // The switch is Dolphin's own setting for this game, in the file of the disc's
  // revision (GameSettings/<ID>r<rev>.ini, layered last, as the Build 367 import).
  id toggle = Row(page, @"neoTextureEnable");
  XCTAssertNotNil(toggle);
  void (^switched)(BOOL) = [toggle valueForKey:@"switched"];
  switched(YES);
  NSString *ini = [user stringByAppendingPathComponent:@"GameSettings/GMSE01r0.ini"];
  XCTAssertTrue([self until:^BOOL {
    NSString *text = [NSString stringWithContentsOfFile:ini encoding:NSUTF8StringEncoding error:nil];
    return [text containsString:@"HiresTextures = True"] && [text containsString:@"CacheHiresTextures = False"];
  } timeout:10], @"%@", [NSString stringWithContentsOfFile:ini encoding:NSUTF8StringEncoding error:nil]);
  XCTAssertTrue([self until:^BOOL { return [[Row(page, @"neoTextureEnable") valueForKey:@"toggle"] boolValue]; } timeout:10],
                @"the page reads the switch back");
  // A pack page: author, version, size, formats, licence, source and an install action.
  void (^open)(void) = [Row(page, @"neoTexturePack.gc-sms-uhd-4k-dds-qashto") valueForKey:@"run"];
  open();
  XCTAssertTrue([self until:^BOOL { return page.navigationController.viewControllers.count == 2; } timeout:5]);
  UIViewController *packPage = page.navigationController.viewControllers.lastObject;
  [packPage loadViewIfNeeded];
  // Its rows follow the installed-folder lookup, made off the main thread.
  XCTAssertTrue([self until:^BOOL { return Rows(packPage).count > 0; } timeout:10]);
  NSMutableString *text = [NSMutableString string];
  for (id row in Rows(packPage)) [text appendFormat:@"%@ %@\n", [row valueForKey:@"title"] ?: @"", [row valueForKey:@"detail"] ?: @""];
  for (NSString *needle in @[@"qashto", @"2.1.1", @"DDS", @"github:qashto/Super_Mario_Sunshine_UHD_Texture_Pack"])
    XCTAssertTrue([text containsString:needle], @"%@ missing in %@", needle, text);
  XCTAssertNotNil(Row(packPage, @"neoTextureInstall"));
  [self dismiss];
}

- (void)testAnotherRegionIsOnlyACandidateAndATitleIsNeverExact {
  NSString *user = [self.work stringByAppendingPathComponent:@"Dolphin/User"];
  UIViewController *page = [self present:@{@"system": @"gc", @"dolphinUser": user, @"gameID": @"GP7E01", @"title": @"Mario Party 7", @"locale": @"en"}];
  XCTAssertTrue([self until:^BOOL { return Row(page, @"neoTexturePack.gc-mario-party-7-hd-najatski") != nil; } timeout:20], @"%@", Rows(page));
  NSString *detail = [Row(page, @"neoTexturePack.gc-mario-party-7-hd-najatski") valueForKey:@"detail"];
  XCTAssertTrue([detail containsString:[self label:@"matchCandidate" language:@"en"]], @"identities from a database must be confirmed: %@", detail);
  [self dismiss];
  page = [self present:@{@"system": @"gc", @"dolphinUser": user, @"gameID": @"GZ2E01", @"title": @"Super Mario Sunshine", @"locale": @"en"}];
  XCTAssertTrue([self until:^BOOL { return Row(page, @"neoTexturePack.gc-sms-uhd-4k-dds-qashto") != nil; } timeout:20]);
  detail = [Row(page, @"neoTexturePack.gc-sms-uhd-4k-dds-qashto") valueForKey:@"detail"];
  XCTAssertFalse([detail containsString:[self label:@"matchExact" language:@"en"]], @"a title alone is never exact: %@", detail);
  [self dismiss];
}

- (void)testConsolePageListsPacksForTheLibraryGames {
  NSString *user = [self.work stringByAppendingPathComponent:@"Dolphin/User"];
  NSArray *games = @[@{@"path": [self disc:@"GMSP01" revision:0], @"title": @"Super Mario Sunshine"},
                     @{@"path": [self disc:@"GALE01" revision:2], @"title": @"Super Smash Bros. Melee"}];
  UIViewController *page = [self present:@{@"system": @"gc", @"dolphinUser": user, @"games": games, @"locale": @"de"}];
  XCTAssertTrue([Headers(page) containsObject:[self label:@"libraryGamesSection" language:@"de"]], @"%@", Headers(page));
  XCTAssertTrue([self until:^BOOL {
    for (id row in Rows(page)) if ([[row valueForKey:@"title"] containsString:@"Super Mario Sunshine — "]) return YES;
    return NO;
  } timeout:30], @"%@", [Rows(page) valueForKey:@"title"]);
  [self dismiss];
}

- (void)testAFailedRefreshKeepsTheCatalogueAndIsNeverNoPack {
  NeoTextureCatalog.sharedCatalog.fetch = ^(NSURL *url, NSUInteger maximum, void (^completion)(NSData *, NSError *)) {
    completion(nil, [NSError errorWithDomain:NSURLErrorDomain code:NSURLErrorTimedOut userInfo:nil]);
  };
  NSString *data = [self.work stringByAppendingPathComponent:@"ARMSX2"];
  UIViewController *page = [self present:@{@"system": @"ps2", @"armsx2Data": data, @"gameID": @"SLUS-20554", @"title": @"Metal Gear Solid 2: Substance", @"locale": @"ja"}];
  XCTAssertTrue([self until:^BOOL { return Row(page, @"neoTexturePack.ps2-mgs2-hd-ui-nathanhigley") != nil; } timeout:20], @"%@", Rows(page));
  void (^refresh)(void) = [Row(page, @"neoTextureRefresh") valueForKey:@"run"];
  refresh();
  XCTAssertTrue([self until:^BOOL { return NeoTextureCatalog.sharedCatalog.snapshot[@"refresh_error"] != nil; } timeout:20]);
  XCTAssertTrue([self until:^BOOL { return Row(page, @"neoTexturePack.ps2-mgs2-hd-ui-nathanhigley") != nil; } timeout:10], @"packs kept after a failure");
  // The PS2 switch is the ARMSX2 store's per-game choice (Build 485), known in the library.
  id toggle = Row(page, @"neoTextureEnable");
  XCTAssertNotNil(toggle, @"%@", [Rows(page) valueForKey:@"identifier"]);
  [self dismiss];
}

- (void)testPSPAndThreeDSUseTheCoreOptionOfTheGame {
  NSString *saves = [self.work stringByAppendingPathComponent:@"Libretro/Saves"], *config = [self.work stringByAppendingPathComponent:@"Libretro/Config"];
  UIViewController *page = [self present:@{@"system": @"psp", @"libretroSaves": saves, @"libretroConfig": config, @"gameID": @"ULUS10160",
                                           @"gameKey": @"psp/Vice City Stories", @"title": @"Grand Theft Auto: Vice City Stories", @"locale": @"ko"}];
  XCTAssertTrue([self until:^BOOL { return Row(page, @"neoTexturePack.psp-gta-vcs-asi-factory") != nil; } timeout:20], @"%@", Rows(page));
  void (^switched)(BOOL) = [Row(page, @"neoTextureEnable") valueForKey:@"switched"];
  switched(YES);
  NSString *games = [config stringByAppendingPathComponent:@"Games/PPSSPP.json"];
  XCTAssertTrue([self until:^BOOL {
    NSData *json = [NSData dataWithContentsOfFile:games];
    NSDictionary *store = json ? [NSJSONSerialization JSONObjectWithData:json options:0 error:nil] : nil;
    return [store[@"games"][@"psp/Vice City Stories"][@"ppsspp_texture_replacement"] isEqual:@"enabled"];
  } timeout:10]);
  [self dismiss];
  page = [self present:@{@"system": @"3ds", @"libretroSaves": saves, @"libretroConfig": config, @"gameID": @"000400000017D800",
                         @"gameKey": @"3ds/Gaki", @"title": @"Gaki no Tsukai", @"locale": @"zh-Hant"}];
  XCTAssertTrue([self until:^BOOL { return Row(page, @"neoTexturePack.3ds-gaki-no-tsukai-english-sonofugly") != nil; } timeout:20], @"%@", Rows(page));
  XCTAssertEqualObjects(page.title, [self label:@"title" language:@"zh_Hant"]);
  [self dismiss];
}

- (void)testNintendo64UsesGLideN64OptionsOfTheGame {
  NSString *system = [self.work stringByAppendingPathComponent:@"Libretro/System"], *config = [self.work stringByAppendingPathComponent:@"Libretro/Config"];
  // The engine reports the ROM header name in hexadecimal (the identity reader's form): SUPER MARIO 64.
  UIViewController *page = [self present:@{@"system": @"n64", @"libretroSystem": system, @"libretroConfig": config,
                                           @"gameID": @"5355504552204D4152494F203634", @"gameKey": @"n64/Super Mario 64 (USA)",
                                           @"title": @"Super Mario 64", @"locale": @"fr"}];
  XCTAssertTrue([self until:^BOOL { return Row(page, @"neoTexturePack.n64-sm64-reloaded-png-hd") != nil; } timeout:20], @"%@", Rows(page));
  XCTAssertNil(Row(page, @"neoTexturePack.n64-mk64-reloaded-png-hd"), @"another game's pack is not offered: %@", Rows(page));
  void (^switched)(BOOL) = [Row(page, @"neoTextureEnable") valueForKey:@"switched"];
  switched(YES);
  NSString *games = [config stringByAppendingPathComponent:@"Games/Mupen64Plus-Next.json"];
  XCTAssertTrue([self until:^BOOL {
    NSData *json = [NSData dataWithContentsOfFile:games];
    NSDictionary *entry = (json ? [NSJSONSerialization JSONObjectWithData:json options:0 error:nil] : nil)[@"games"][@"n64/Super Mario 64 (USA)"];
    return [entry[@"mupen64plus-txHiresEnable"] isEqual:@"True"] && [entry[@"mupen64plus-txHiresFullAlphaChannel"] isEqual:@"True"] &&
           [entry[@"mupen64plus-EnableEnhancedHighResStorage"] isEqual:@"True"];
  } timeout:10]);
  [self dismiss];
}

- (void)testPS1BeetleShowsTheRunningEngineAndWritesBothOptions {
  NSString *saves = [self.work stringByAppendingPathComponent:@"Libretro/Saves"], *config = [self.work stringByAppendingPathComponent:@"Libretro/Config"];
  __block NSDictionary *report = @{@"renderer": @"software", @"replace": @NO, @"applied": @0};
  NSDictionary *(^status)(void) = ^NSDictionary *(void) { return report; };
  NSDictionary *options = @{@"system": @"ps1", @"libretroSaves": saves, @"libretroConfig": config, @"gameID": @"SLUS-00067",
                            @"gameKey": @"psx/Castle (USA).cue", @"title": @"Castlevania: Symphony of the Night", @"locale": @"fr",
                            @"inGame": @YES, @"engineStatus": status};
  UIViewController *page = [self present:options];
  // A software renderer is reported as such: never "HD active".
  XCTAssertTrue([self until:^BOOL { return Row(page, @"neoTextureEngineStatus") != nil; } timeout:20], @"%@", [Rows(page) valueForKey:@"identifier"]);
  id row = Row(page, @"neoTextureEngineStatus");
  XCTAssertEqualObjects([row valueForKey:@"title"], [self label:@"status.software" language:@"fr"]);
  XCTAssertEqualObjects([row valueForKey:@"detail"], [self label:@"status.softwareDetail" language:@"fr"]);
  // The switch writes Track + Replace Textures for this game only.
  void (^switched)(BOOL) = [Row(page, @"neoTextureEnable") valueForKey:@"switched"];
  XCTAssertNotNil(switched, @"%@", [Rows(page) valueForKey:@"identifier"]);
  switched(YES);
  NSString *games = [config stringByAppendingPathComponent:@"Games/Beetle PSX HW.json"];
  XCTAssertTrue([self until:^BOOL {
    NSData *json = [NSData dataWithContentsOfFile:games];
    NSDictionary *entry = (json ? [NSJSONSerialization JSONObjectWithData:json options:0 error:nil] : nil)[@"games"][@"psx/Castle (USA).cue"];
    return [entry[@"beetle_psx_hw_track_textures"] isEqual:@"enabled"] && [entry[@"beetle_psx_hw_replace_textures"] isEqual:@"enabled"] &&
           !entry[@"beetle_psx_hw_dump_textures"];
  } timeout:10], @"%@", [NSString stringWithContentsOfFile:games encoding:NSUTF8StringEncoding error:nil]);
  [self dismiss];
  // Vulkan with textures recognised and bound by the core.
  report = @{@"renderer": @"vulkan", @"replace": @YES, @"recognized": @12, @"applied": @3, @"folder": @"Castle (USA)-texture-replacements"};
  page = [self present:options];
  XCTAssertTrue([self until:^BOOL { return Row(page, @"neoTextureEngineStatus") != nil; } timeout:20]);
  row = Row(page, @"neoTextureEngineStatus");
  NSString *detail = [row valueForKey:@"detail"];
  XCTAssertEqualObjects([row valueForKey:@"title"], [self label:@"status.vulkan" language:@"fr"]);
  XCTAssertTrue([detail containsString:@"12"] && [detail containsString:@"3"] && [detail containsString:@"Castle (USA)-texture-replacements"], @"%@", detail);
  [self dismiss];
  // Replacement on, but the core found nothing in its folder.
  report = @{@"renderer": @"vulkan", @"replace": @YES, @"recognized": @0, @"applied": @0, @"folder": @"Castle (USA)-texture-replacements"};
  page = [self present:options];
  XCTAssertTrue([self until:^BOOL { return Row(page, @"neoTextureEngineStatus") != nil; } timeout:20]);
  XCTAssertEqualObjects([Row(page, @"neoTextureEngineStatus") valueForKey:@"detail"],
                        [[self label:@"status.noFiles" language:@"fr"] stringByReplacingOccurrencesOfString:@"{folder}" withString:@"Castle (USA)-texture-replacements"]);
  [self dismiss];
}

- (void)testNESPackSwitchStartsTheGameWithMesenOnlyWhenNeoStationRecordsIt {
  NSString *system = [self.work stringByAppendingPathComponent:@"Libretro/System"], *config = [self.work stringByAppendingPathComponent:@"Libretro/Config"];
  NSMutableArray<NSString *> *asked = [NSMutableArray array];
  __block BOOL accept = NO;
  BOOL (^selector)(NSString *, NSString *) = ^BOOL(NSString *gameKey, NSString *core) {
    @synchronized(asked) { [asked addObject:[NSString stringWithFormat:@"%@ %@", gameKey, core]]; }
    return accept;
  };
  // Contra (USA): the SHA-1 of the whole file (iNES header included) that Contra 80s names.
  UIViewController *page = [self present:@{@"system": @"nes", @"libretroSystem": system, @"libretroConfig": config,
                                           @"gameID": @"C9EA66BB7CB30AD5343F1721B1D4D3219859319B", @"gameKey": @"nes/Contra (USA)",
                                           @"libretroCore": @"nestopia", @"title": @"Contra", @"locale": @"fr", @"coreSelector": selector}];
  XCTAssertTrue([self until:^BOOL { return Row(page, @"neoTexturePack.nes-contra-80s-tastic") != nil; } timeout:20], @"%@", [Rows(page) valueForKey:@"identifier"]);
  XCTAssertNil(Row(page, @"neoTexturePack.nes-pac-man-4x-pepcodes"), @"another game's pack is not offered: %@", [Rows(page) valueForKey:@"identifier"]);
  // The game starts with Nestopia, which reads no HD pack: the switch is off and says why.
  NSString *reason = [self label:@"activation.mesenEngine" language:@"fr"];
  XCTAssertTrue([self until:^BOOL { return [[Row(page, @"neoTextureEnable") valueForKey:@"detail"] isEqual:reason]; } timeout:20],
                @"%@", [Row(page, @"neoTextureEnable") valueForKey:@"detail"]);
  id toggle = Row(page, @"neoTextureEnable");
  XCTAssertEqualObjects([toggle valueForKey:@"toggle"], @NO);
  BOOL explained = NO;
  for (id section in Sections(page)) explained |= [[section valueForKey:@"footer"] containsString:[self label:@"engineNotice.mesen" language:@"fr"]];
  XCTAssertTrue(explained, @"%@", [Sections(page) valueForKey:@"footer"]);
  NSString *games = [config stringByAppendingPathComponent:@"Games/Mesen.json"];
  NSDictionary *(^entry)(void) = ^NSDictionary *(void) {
    NSData *json = [NSData dataWithContentsOfFile:games];
    return (json ? [NSJSONSerialization JSONObjectWithData:json options:0 error:nil] : nil)[@"games"][@"nes/Contra (USA)"];
  };
  // NeoStation does not record Mesen for the game: nothing is written, the switch stays off, the error is shown.
  void (^switched)(BOOL) = [toggle valueForKey:@"switched"];
  switched(YES);
  XCTAssertTrue([self until:^BOOL { return [page.navigationController.presentedViewController ?: page.presentedViewController isKindOfClass:UIAlertController.class]; } timeout:10]);
  XCTAssertEqualObjects(asked, (@[@"nes/Contra (USA) mesen"]));
  XCTAssertNil(entry(), @"%@", [NSString stringWithContentsOfFile:games encoding:NSUTF8StringEncoding error:nil]);
  XCTAssertEqualObjects([Row(page, @"neoTextureEnable") valueForKey:@"toggle"], @NO);
  UIViewController *alert = page.navigationController.presentedViewController ?: page.presentedViewController;
  XCTestExpectation *closed = [self expectationWithDescription:@"alert closed"];
  [alert.presentingViewController dismissViewControllerAnimated:NO completion:^{ [closed fulfill]; }];
  [self waitForExpectations:@[closed] timeout:10];
  // Recorded: the game's own option is written (this game only) and the switch is on, with no reason left.
  accept = YES;
  switched = [Row(page, @"neoTextureEnable") valueForKey:@"switched"];
  switched(YES);
  XCTAssertTrue([self until:^BOOL { return [entry()[@"mesen_hdpacks"] isEqual:@"enabled"]; } timeout:10],
                @"%@", [NSString stringWithContentsOfFile:games encoding:NSUTF8StringEncoding error:nil]);
  XCTAssertTrue([self until:^BOOL { return [[Row(page, @"neoTextureEnable") valueForKey:@"toggle"] isEqual:@YES]; } timeout:10]);
  XCTAssertNil([Row(page, @"neoTextureEnable") valueForKey:@"detail"]);
  XCTAssertEqual(asked.count, 2u);
  [self dismiss];
}

- (void)testVerifiedManualPackInstallsOnlyFromItsImportedFile {
  // The bundled index plus one manual pack whose author's file was verified on CI.
  NSData *bundled = [NSData dataWithContentsOfURL:[NSBundle.mainBundle URLForResource:@"manifest.json" withExtension:@"gz"]];
  NSMutableDictionary *index = [[NeoTextureCatalog validatedIndex:bundled error:nil] mutableCopy];
  XCTAssertNotNil(index);
  NSDictionary *pack = @{@"id": @"ui-test-verified-melee", @"system": @"gc", @"engine": @"dolphin", @"title": @"Verified Melee", @"version": @"1.0",
                         @"games": @[@{@"title": @"Super Smash Bros. Melee", @"identities": @[@{@"type": @"game_id", @"scheme": @"dolphin-disc-game-id", @"value": @"GALE01"}],
                                       @"regions": @[@"USA"]}],
                         @"authors": @[@"Test author"], @"page_url": @"https://example.invalid/melee", @"source_id": @"test:melee",
                         @"licence": @{@"summary": @"Test", @"redistribution": @"Not redistributed"}, @"availability": @"manual",
                         @"download": @{@"automatable": @NO, @"verified": @{@"format": @"7z", @"file_name": @"Melee HD.7z", @"host": @"mega",
                                                                            @"size": @123456789, @"sha256": [@"" stringByPaddingToLength:64 withString:@"ab" startingAtIndex:0]}},
                         @"install": @{@"files": @10, @"bytes": @2000000, @"folders": @[@{@"from": @"GALE01/", @"to": @"GALE01"}], @"formats": @[@"png"]},
                         @"verified_at": @"2099-01-01"};
  NSMutableArray *packs = [index[@"packs"] mutableCopy];
  [packs addObject:pack];
  index[@"packs"] = packs;
  index[@"generated_at"] = @"2099-01-01";
  index[@"revision"] = @"2099-01-01.uitest";
  [index removeObjectForKey:@"rejected_packs"];
  NSData *data = [NSJSONSerialization dataWithJSONObject:index options:0 error:nil];
  NeoTextureCatalog.sharedCatalog.fetch = ^(NSURL *url, NSUInteger maximum, void (^completion)(NSData *, NSError *)) { completion(data, nil); };
  XCTestExpectation *refreshed = [self expectationWithDescription:@"refreshed"];
  [NeoTextureCatalog.sharedCatalog refreshWithCompletion:^(NSDictionary *snapshot, NSError *error) { [refreshed fulfill]; }];
  [self waitForExpectations:@[refreshed] timeout:30];
  NeoTextureCatalog.sharedCatalog.fetch = nil;
  NSString *user = [self.work stringByAppendingPathComponent:@"Dolphin/User"];
  UIViewController *page = [self present:@{@"system": @"gc", @"dolphinUser": user, @"gameID": @"GALE01", @"title": @"Super Smash Bros. Melee", @"locale": @"en",
                                           @"presentation": @"modal"}];
  XCTAssertTrue([self until:^BOOL { return Row(page, @"neoTexturePack.ui-test-verified-melee") != nil; } timeout:20], @"%@", [Rows(page) valueForKey:@"identifier"]);
  NSString *detail = [Row(page, @"neoTexturePack.ui-test-verified-melee") valueForKey:@"detail"];
  XCTAssertTrue([detail containsString:[self label:@"stateManualVerified" language:@"en"]], @"%@", detail);
  void (^open)(void) = [Row(page, @"neoTexturePack.ui-test-verified-melee") valueForKey:@"run"];
  open();
  XCTAssertTrue([self until:^BOOL { return page.navigationController.viewControllers.count == 2; } timeout:5]);
  UIViewController *packPage = page.navigationController.viewControllers.lastObject;
  [packPage loadViewIfNeeded];
  XCTAssertTrue([self until:^BOOL { return Row(packPage, @"neoTextureImportVerified") != nil; } timeout:10], @"%@", [Rows(packPage) valueForKey:@"identifier"]);
  XCTAssertNil(Row(packPage, @"neoTextureInstall"), @"a manual pack is never downloaded by the app");
  NSString *footer = nil;
  for (id section in Sections(packPage)) if ([[section valueForKey:@"footer"] containsString:@"Melee HD.7z"]) footer = [section valueForKey:@"footer"];
  XCTAssertTrue([footer containsString:@"MEGA"], @"%@", footer);
  [self dismiss];
}

- (void)testEveryLanguageNamesThePage {
  NSArray *languages = @[@"en", @"es", @"ru", @"zh", @"zh-Hant", @"pt", @"fr", @"de", @"it", @"id", @"ja", @"ko"];
  NSString *user = [self.work stringByAppendingPathComponent:@"Dolphin/User"];
  for (NSString *language in languages) {
    UIViewController *controller = [NeoTextureHDPage textureViewControllerWithOptions:@{@"system": @"wii", @"dolphinUser": user, @"locale": language}];
    [controller loadViewIfNeeded];
    NSString *key = [language isEqualToString:@"zh-Hant"] ? @"zh_Hant" : language;
    XCTAssertEqualObjects(controller.title, [self label:@"title" language:key], @"%@", language);
    XCTAssertTrue([Headers(controller) containsObject:[self label:@"sourcesSection" language:key]] ||
                  [Headers(controller) containsObject:[self label:@"availableConsoleSection" language:key]], @"%@ %@", language, Headers(controller));
  }
}
@end
'''


def native():
    sdk = subprocess.check_output(['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-version'], text=True).strip()
    runtime_key = 'com.apple.CoreSimulator.SimRuntime.iOS-' + sdk.replace('.', '-')
    devices = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', 'available', '-j']))['devices']
    candidates = [device for runtime, items in devices.items() if runtime == runtime_key
                  for device in items if device['name'].startswith('iPhone') and device.get('isAvailable')]
    if not candidates:
        raise RuntimeError(f'A simulator matching the selected Xcode SDK {sdk} is required; installed: {sorted(devices)}')
    device = candidates[0]
    print(f"Testing on {device['name']} / iOS {sdk} / {device['udid']}", flush=True)
    if device.get('state') != 'Booted':
        subprocess.run(['xcrun', 'simctl', 'boot', device['udid']], check=True, timeout=60)
    subprocess.run(['xcrun', 'simctl', 'bootstatus', device['udid'], '-b'], check=True, timeout=180)
    sources = sorted(str(p) for p in CLASSES.glob('*.m') if p.name != 'NeoTextureCatalogPlugin.m')
    sources += sorted(str(p) for p in CLASSES.glob('*.mm')) + [str(CLASSES / 'NeoTextureLZMA.c'), str(CLASSES / 'NeoTextureRARMemory.c'), str(ARMSX2 / 'ARMSX2TexturePackStore.mm')]
    sources += sorted(str(p) for p in (POD / 'ThirdParty/libarchive').glob('*.c'))
    sources += [str(CHEAT_CATALOG / 'Classes/RBLiquidProgressView.m')]
    with tempfile.TemporaryDirectory(prefix='texture-catalog-ui-') as folder:
        directory = Path(folder)
        from texture_catalog_ios_syntax_test import stage_cheat_catalog_headers
        cheat_include = stage_cheat_catalog_headers(directory)
        (directory / 'main.m').write_text(APP)
        (directory / 'TextureCatalogPageTests.m').write_text(TESTS)
        sdk_dependencies = [{'sdk': 'UIKit.framework'}, {'sdk': 'Foundation.framework'}, {'sdk': 'Metal.framework'},
                            {'sdk': 'libz.tbd'}, {'sdk': 'libiconv.tbd'}, {'sdk': 'libc++.tbd'}, {'sdk': 'UniformTypeIdentifiers.framework'},
                            {'sdk': 'QuartzCore.framework'}]
        search_paths = ' '.join(str(p) for p in (CLASSES, CLASSES / 'Public', POD / 'ThirdParty/lzma', POD / 'ThirdParty/libarchive', ARMSX2,
                                                 cheat_include))
        project = {
            'name': 'TextureCatalog486',
            'options': {'deploymentTarget': {'iOS': '17.4'}},
            'settings': {'base': {'CLANG_ENABLE_OBJC_ARC': 'YES', 'CLANG_ENABLE_MODULES': 'YES', 'CLANG_CXX_LANGUAGE_STANDARD': 'c++20',
                                  'CODE_SIGNING_ALLOWED': 'YES', 'CODE_SIGN_IDENTITY': '-', 'GENERATE_INFOPLIST_FILE': 'YES',
                                  'HEADER_SEARCH_PATHS': search_paths, 'GCC_PREPROCESSOR_DEFINITIONS': '$(inherited) HAVE_CONFIG_H=1'}},
            'targets': {
                'TextureCatalogHost': {'type': 'application', 'platform': 'iOS',
                    'sources': [str(directory / 'main.m')] + sources +
                               [{'path': str(POD / 'Resources/labels.json'), 'buildPhase': 'resources'},
                                {'path': str(POD / 'Resources/manifest.json.gz'), 'buildPhase': 'resources'}],
                    'dependencies': sdk_dependencies,
                    'settings': {'base': {'PRODUCT_BUNDLE_IDENTIFIER': 'org.neostation.texturecatalog.host',
                                          'INFOPLIST_KEY_UILaunchScreen_Generation': 'YES'}}},
                'TextureCatalogTests': {'type': 'bundle.unit-test', 'platform': 'iOS',
                    'sources': [str(directory / 'TextureCatalogPageTests.m')],
                    'dependencies': [{'target': 'TextureCatalogHost'}] + sdk_dependencies,
                    'settings': {'base': {'PRODUCT_BUNDLE_IDENTIFIER': 'org.neostation.texturecatalog.tests',
                                          'TEST_HOST': '$(BUILT_PRODUCTS_DIR)/TextureCatalogHost.app/TextureCatalogHost',
                                          'BUNDLE_LOADER': '$(TEST_HOST)'}}},
            },
            'schemes': {'TextureCatalog486': {'build': {'targets': {'TextureCatalogHost': 'all', 'TextureCatalogTests': 'test'}},
                                              'test': {'targets': ['TextureCatalogTests']}}},
        }
        spec = directory / 'project.json'
        spec.write_text(json.dumps(project))
        subprocess.run(['xcodegen', 'generate', '--spec', str(spec), '--project', str(directory)], check=True)
        result = ROOT / 'build/hdtex486/TextureCatalog486.xcresult'
        result.parent.mkdir(parents=True, exist_ok=True)
        if result.exists():
            subprocess.run(['rm', '-rf', str(result)], check=True)
        subprocess.run(['xcodebuild', 'test', '-project', str(directory / 'TextureCatalog486.xcodeproj'),
            '-scheme', 'TextureCatalog486', '-destination', 'platform=iOS Simulator,id=' + device['udid'],
            '-destination-timeout', '60', '-parallel-testing-enabled', 'NO',
            '-test-timeouts-enabled', 'YES', '-default-test-execution-time-allowance', '120',
            '-maximum-test-execution-time-allowance', '240', '-resultBundlePath', str(result),
            'CODE_SIGNING_ALLOWED=YES', 'CODE_SIGN_IDENTITY=-', 'DEVELOPMENT_TEAM='], check=True, timeout=1500)
    print('PASS: unified HD textures page on UIKit with the bundled catalogue (GameCube disc, candidate/exact matching, console '
          'library, failed refresh, PS2 store, PSP/3DS/N64 core options, PS1 Beetle engine report and options, NES switch through '
          'the Mesen engine choice, verified manual '
          'pack import, twelve languages)', flush=True)


if __name__ == '__main__':
    native()

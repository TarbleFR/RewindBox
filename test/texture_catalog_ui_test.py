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
    sources += sorted(str(p) for p in CLASSES.glob('*.mm')) + [str(CLASSES / 'NeoTextureLZMA.c'), str(ARMSX2 / 'ARMSX2TexturePackStore.mm')]
    with tempfile.TemporaryDirectory(prefix='texture-catalog-ui-') as folder:
        directory = Path(folder)
        (directory / 'main.m').write_text(APP)
        (directory / 'TextureCatalogPageTests.m').write_text(TESTS)
        sdk_dependencies = [{'sdk': 'UIKit.framework'}, {'sdk': 'Foundation.framework'}, {'sdk': 'Metal.framework'},
                            {'sdk': 'libz.tbd'}, {'sdk': 'libc++.tbd'}, {'sdk': 'UniformTypeIdentifiers.framework'}]
        search_paths = ' '.join(str(p) for p in (CLASSES, CLASSES / 'Public', POD / 'ThirdParty/lzma', ARMSX2))
        project = {
            'name': 'TextureCatalog486',
            'options': {'deploymentTarget': {'iOS': '17.4'}},
            'settings': {'base': {'CLANG_ENABLE_OBJC_ARC': 'YES', 'CLANG_ENABLE_MODULES': 'YES', 'CLANG_CXX_LANGUAGE_STANDARD': 'c++20',
                                  'CODE_SIGNING_ALLOWED': 'YES', 'CODE_SIGN_IDENTITY': '-', 'GENERATE_INFOPLIST_FILE': 'YES',
                                  'HEADER_SEARCH_PATHS': search_paths}},
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
          'library, failed refresh, PS2 store, PSP/3DS core options, twelve languages)', flush=True)


if __name__ == '__main__':
    native()

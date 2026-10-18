#!/usr/bin/env python3
"""Execute the actual ARMSX2 Graphics menu on UIKit (iOS Simulator), without a VM.

The host application links the production menu, its RetroAchievements page,
the native localization and the unified cheat catalogue classes the menu
imports since Build 474. No emulator core, GPU, JIT or device is involved:
this proves navigation, labels, the levels offered and the commands sent.
"""
from pathlib import Path
import json
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'test'))
from libretro_ios_syntax_test import stage_dependency_headers  # noqa: E402
from touch_layout_support import stage_touch_layout, CLASSES as TOUCH_CLASSES  # noqa: E402
TOUCH_STRINGS = TOUCH_CLASSES / 'NeoTouchLayoutStrings.m'

CLASSES = ROOT / 'packages/armsx2_internal_bridge/ios/Classes'
CATALOGUE = ROOT / 'packages/neo_cheat_catalog/ios/Classes'

APP = r'''
#import <UIKit/UIKit.h>
@interface ARMSX2GraphicsTestDelegate : UIResponder <UIApplicationDelegate>
@property(nonatomic, strong) UIWindow* window;
@end
@implementation ARMSX2GraphicsTestDelegate
- (BOOL)application:(UIApplication*)application didFinishLaunchingWithOptions:(NSDictionary*)options {
  self.window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
  self.window.rootViewController = [UIViewController new];
  [self.window makeKeyAndVisible];
  return YES;
}
@end
int main(int argc, char** argv) {
  @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(ARMSX2GraphicsTestDelegate.class)); }
}
'''

TESTS = r'''
#import <XCTest/XCTest.h>
#import <UIKit/UIKit.h>
#import "Armsx2SessionMenu.h"
@interface Armsx2SessionMenu (GraphicsTesting)
- (void)resumePressed;
- (void)updateSearchResultsForSearchController:(UISearchController*)search;
@end
@interface ARMSX2GraphicsTests : XCTestCase
@property(nonatomic, strong) NSMutableDictionary* snapshot;
@property(nonatomic, assign) NSUInteger snapshotReads;
@end
@implementation ARMSX2GraphicsTests
- (void)setUp {
 [super setUp];
 self.snapshotReads=0;
 self.snapshot=[@{@"upscale":@1,@"aspect":@0,
  @"graphicsAssets":@{@"supported":@YES,@"overlay":@0,@"selected":@"",@"presets":@[@{@"id":@"bundle:presets/crt.slangp",@"name":@"CRT"}],@"packInstalled":@NO,@"shaderError":@""},
  @"blending":@{@"available":@YES,@"global":@1,@"game":@(-1),@"effective":@1,@"gamedbMinimum":@(-1),@"gamedbMaximum":@(-1),@"gamedbRecommended":@(-1),@"levels":@[@0,@1,@3,@4,@5]}} mutableCopy];
}
- (void)setBlending:(NSDictionary*)values {
 NSMutableDictionary* blending=[self.snapshot[@"blending"] mutableCopy];
 [blending addEntriesFromDictionary:values];
 self.snapshot[@"blending"]=blending;
}
- (Armsx2SessionMenu*)menu:(__strong UINavigationController**)navigation {
 Armsx2SessionMenu* menu=[Armsx2SessionMenu new];menu.localeIdentifier=@"fr";
 __weak ARMSX2GraphicsTests* weakSelf=self;
 menu.readSnapshot=^(void (^done)(NSDictionary<NSString*, id>* _Nullable)){
  ARMSX2GraphicsTests* tests=weakSelf; if (tests) tests.snapshotReads++; done([tests.snapshot copy]);};
 *navigation=[[UINavigationController alloc] initWithRootViewController:menu];
 [*navigation loadViewIfNeeded];[menu loadViewIfNeeded];[menu viewWillAppear:NO];
 // Exercise production root navigation; no private enum constants are assumed.
 [menu tableView:menu.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:0 inSection:0]];
 Armsx2SessionMenu* graphics=(id)(*navigation).topViewController;[graphics loadViewIfNeeded];
 return graphics;
}
- (UITableViewCell*)cell:(UITableViewController*)page row:(NSInteger)row section:(NSInteger)section {
 return [page tableView:page.tableView cellForRowAtIndexPath:[NSIndexPath indexPathForRow:row inSection:section]];
}
- (NSString*)title:(UITableViewController*)page row:(NSInteger)row section:(NSInteger)section {
 return [self cell:page row:row section:section].textLabel.text;
}
- (Armsx2SessionMenu*)blendingPage:(UINavigationController*)nav from:(Armsx2SessionMenu*)graphics {
 [graphics tableView:graphics.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:2 inSection:0]];
 Armsx2SessionMenu* page=(id)nav.topViewController;[page loadViewIfNeeded];[page viewWillAppear:NO];
 XCTAssertNotEqual(page,graphics);
 return page;
}
- (void)testGraphicsRowsPlaceBlendingAfterScreenFormat {
 UINavigationController* nav=nil;Armsx2SessionMenu* graphics=[self menu:&nav];
 XCTAssertEqual([graphics numberOfSectionsInTableView:graphics.tableView],1);
 XCTAssertEqual([graphics tableView:graphics.tableView numberOfRowsInSection:0],7);
 XCTAssertEqualObjects([self title:graphics row:0 section:0],@"Résolution interne");
 XCTAssertEqualObjects([self title:graphics row:1 section:0],@"Format d’écran");
 XCTAssertEqualObjects([self title:graphics row:2 section:0],@"Précision du blending");
 XCTAssertEqualObjects([self cell:graphics row:2 section:0].detailTextLabel.text,@"Basique · Valeur par défaut de tous les jeux PS2");
 XCTAssertEqualObjects([self title:graphics row:3 section:0],@"Shaders");
 XCTAssertEqualObjects([self title:graphics row:4 section:0],@"Overlays de performances");
 XCTAssertEqualObjects([self title:graphics row:5 section:0],@"Hacks graphiques");
 XCTAssertTrue([self title:graphics row:6 section:0].length>0);
}
- (void)testBlendingPageOffersOnlyEngineLevelsAndSendsScopedCommands {
 UINavigationController* nav=nil;Armsx2SessionMenu* graphics=[self menu:&nav];
 Armsx2SessionMenu* page=[self blendingPage:nav from:graphics];
 XCTAssertEqualObjects(page.title,@"Précision du blending");
 XCTAssertEqual([page numberOfSectionsInTableView:page.tableView],2);
 XCTAssertEqual([page tableView:page.tableView numberOfRowsInSection:0],6);
 XCTAssertEqual([page tableView:page.tableView numberOfRowsInSection:1],5);
 XCTAssertEqualObjects([page tableView:page.tableView titleForHeaderInSection:0],@"Ce jeu");
 XCTAssertEqualObjects([page tableView:page.tableView titleForHeaderInSection:1],@"Valeur par défaut de tous les jeux PS2");
 NSArray* game=@[@"Automatique",@"Minimum",@"Basique",@"Élevée",@"Complet",@"Maximum"];
 NSArray* all=@[@"Minimum",@"Basique",@"Élevée",@"Complet",@"Maximum"];
 for (NSInteger row=0;row<6;row++) XCTAssertEqualObjects([self title:page row:row section:0],game[row]);
 for (NSInteger row=0;row<5;row++) XCTAssertEqualObjects([self title:page row:row section:1],all[row]);
 // Medium renders like Basic on iPhone: the engine does not list it, the menu never adds it.
 for (NSInteger section=0;section<2;section++)
  for (NSInteger row=0;row<[page tableView:page.tableView numberOfRowsInSection:section];row++)
   XCTAssertFalse([[self title:page row:row section:section] isEqualToString:@"Moyenne"]);
 XCTAssertEqual([self cell:page row:0 section:0].accessoryType,UITableViewCellAccessoryCheckmark);
 XCTAssertEqual([self cell:page row:2 section:0].accessoryType,UITableViewCellAccessoryNone);
 XCTAssertEqual([self cell:page row:1 section:1].accessoryType,UITableViewCellAccessoryCheckmark);
 XCTAssertEqualObjects([page tableView:page.tableView titleForFooterInSection:0],@"Appliquée actuellement : Basique · Valeur par défaut de tous les jeux PS2");
 XCTAssertTrue([[page tableView:page.tableView titleForFooterInSection:1] containsString:@"charge du GPU"]);
 __block NSMutableArray* commands=[NSMutableArray array];
 page.performCommand=^(NSString* c,id v,void (^done)(BOOL,NSString*)){[commands addObject:@[c,v]];done(YES,@"");};
 const NSUInteger reads=self.snapshotReads;
 [page tableView:page.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:3 inSection:0]];
 [page tableView:page.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:4 inSection:1]];
 [page tableView:page.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:0 inSection:0]];
 XCTAssertEqualObjects(commands,(@[@[@"blending",@3],@[@"blendingDefault",@5],@[@"blending",@(-1)]]));
 XCTAssertEqual(self.snapshotReads,reads+3);
 XCTAssertEqual(nav.topViewController,page);
}
- (void)testBlendingPageShowsPerGameChoiceAndGameDbAdvice {
 [self setBlending:@{@"game":@3,@"effective":@3,@"gamedbRecommended":@4}];
 UINavigationController* nav=nil;Armsx2SessionMenu* graphics=[self menu:&nav];
 XCTAssertEqualObjects([self cell:graphics row:2 section:0].detailTextLabel.text,@"Élevée · Réglée pour ce jeu");
 Armsx2SessionMenu* page=[self blendingPage:nav from:graphics];
 XCTAssertEqual([self cell:page row:0 section:0].accessoryType,UITableViewCellAccessoryNone);
 XCTAssertEqual([self cell:page row:3 section:0].accessoryType,UITableViewCellAccessoryCheckmark);
 NSString* footer=[page tableView:page.tableView titleForFooterInSection:0];
 XCTAssertTrue([footer containsString:@"Appliquée actuellement : Élevée · Réglée pour ce jeu"]);
 XCTAssertTrue([footer containsString:@"GameDB recommande Complet pour ce jeu"]);
 [self setBlending:@{@"game":@(-1),@"global":@4,@"effective":@1,@"gamedbMaximum":@1,@"gamedbRecommended":@(-1)}];
 UINavigationController* nav2=nil;Armsx2SessionMenu* graphics2=[self menu:&nav2];
 XCTAssertEqualObjects([self cell:graphics2 row:2 section:0].detailTextLabel.text,@"Basique · Ajustée par le profil ARMSX2/GameDB pour ce jeu");
 Armsx2SessionMenu* page2=[self blendingPage:nav2 from:graphics2];
 XCTAssertEqual([self cell:page2 row:0 section:0].accessoryType,UITableViewCellAccessoryCheckmark);
 XCTAssertEqual([self cell:page2 row:3 section:1].accessoryType,UITableViewCellAccessoryCheckmark);
 XCTAssertEqualObjects([page2 tableView:page2.tableView titleForFooterInSection:0],@"Appliquée actuellement : Basique · Ajustée par le profil ARMSX2/GameDB pour ce jeu");
}
- (void)testBlendingUnavailableWithoutEngineData {
 [self.snapshot removeObjectForKey:@"blending"];
 UINavigationController* nav=nil;Armsx2SessionMenu* graphics=[self menu:&nav];
 XCTAssertEqualObjects([self cell:graphics row:2 section:0].detailTextLabel.text,@"Indisponible");
 Armsx2SessionMenu* page=[self blendingPage:nav from:graphics];
 XCTAssertEqual([page tableView:page.tableView numberOfRowsInSection:0],0);
 XCTAssertEqual([page tableView:page.tableView numberOfRowsInSection:1],0);
 XCTAssertEqualObjects([page tableView:page.tableView titleForFooterInSection:0],@"La précision du blending n’est pas disponible pour cette session.");
}
- (void)testGraphicsGroupsBothFeaturesAndShaderSelectionUsesStableToken {
 UINavigationController* nav=nil;Armsx2SessionMenu* graphics=[self menu:&nav];
 __block NSString* command=nil;__block id value=nil;
 graphics.performCommand=^(NSString* c,id v,void (^done)(BOOL,NSString*)){command=c;value=v;done(YES,@"");};
 [graphics tableView:graphics.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:3 inSection:0]];
 Armsx2SessionMenu* shaders=(id)nav.topViewController;[shaders loadViewIfNeeded];
 XCTAssertEqual([shaders tableView:shaders.tableView numberOfRowsInSection:0],3);
 [shaders tableView:shaders.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:2 inSection:0]];
 XCTAssertEqualObjects(command,@"shader");XCTAssertEqualObjects(value,@"bundle:presets/crt.slangp");
 [shaders tableView:shaders.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:0 inSection:0]];
 XCTAssertEqualObjects(value,@"");
 [shaders tableView:shaders.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:1 inSection:0]];
 XCTAssertEqualObjects(command,@"downloadShaders");
}
- (void)testSearchFiltersByNameWithoutChangingTheStableSelection {
 UINavigationController* nav=nil;Armsx2SessionMenu* graphics=[self menu:&nav];
 __block id selected=nil;graphics.performCommand=^(NSString* c,id value,void (^done)(BOOL,NSString*)){selected=value;done(YES,@"");};
 [graphics tableView:graphics.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:3 inSection:0]];
 Armsx2SessionMenu* shaders=(id)nav.topViewController;[shaders loadViewIfNeeded];
 UISearchController* search=shaders.navigationItem.searchController;
 XCTAssertNotNil(search);XCTAssertEqualObjects(search.searchBar.placeholder,@"Rechercher un shader");
 search.searchBar.text=@"unknown";[shaders updateSearchResultsForSearchController:search];
 XCTAssertEqual([shaders tableView:shaders.tableView numberOfRowsInSection:0],2);
 search.searchBar.text=@"crt";[shaders updateSearchResultsForSearchController:search];
 XCTAssertEqual([shaders tableView:shaders.tableView numberOfRowsInSection:0],3);
 [shaders tableView:shaders.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:2 inSection:0]];
 XCTAssertEqualObjects(selected,@"bundle:presets/crt.slangp");
}
- (void)testDownloadDoesNotBlockResumeAndFailuresRemainVisible {
 UINavigationController* nav=nil;Armsx2SessionMenu* graphics=[self menu:&nav];
 __block NSUInteger resumed=0;graphics.resumeGame=^{++resumed;};
 __block void (^pending)(BOOL,NSString*)=nil;
 graphics.performCommand=^(NSString* command,id value,void (^done)(BOOL,NSString*)){pending=[done copy];};
 [graphics tableView:graphics.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:3 inSection:0]];
 Armsx2SessionMenu* shaders=(id)nav.topViewController;[shaders loadViewIfNeeded];
 [shaders tableView:shaders.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:1 inSection:0]];
 XCTAssertNotNil(pending);XCTAssertTrue(nav.view.userInteractionEnabled);
 XCTAssertFalse([shaders tableView:shaders.tableView cellForRowAtIndexPath:[NSIndexPath indexPathForRow:1 inSection:0]].userInteractionEnabled);
 [shaders resumePressed];XCTAssertEqual(resumed,1U);
 pending(NO,@"HTTP 503");
 NSString* footer=[shaders tableView:shaders.tableView titleForFooterInSection:0];
 XCTAssertTrue([footer containsString:@"HTTP 503"]);
 XCTAssertTrue([footer containsString:@"ARMSX2"]);
 XCTAssertTrue([shaders tableView:shaders.tableView cellForRowAtIndexPath:[NSIndexPath indexPathForRow:1 inSection:0]].userInteractionEnabled);
}
- (void)testOverlayChoicesReachNativeCommandAndPreserveResolution {
 UINavigationController* nav=nil;Armsx2SessionMenu* graphics=[self menu:&nav];
 __block NSString* command=nil;__block id value=nil;
 graphics.performCommand=^(NSString* c,id v,void (^done)(BOOL,NSString*)){command=c;value=v;done(YES,@"");};
 [graphics tableView:graphics.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:4 inSection:0]];
 UITableViewController* overlay=(id)nav.topViewController;[overlay loadViewIfNeeded];
 XCTAssertEqual([overlay tableView:overlay.tableView numberOfRowsInSection:0],4);
 [overlay tableView:overlay.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:3 inSection:0]];
 XCTAssertEqualObjects(command,@"overlay");XCTAssertEqualObjects(value,@3);
 XCTAssertEqualObjects([graphics valueForKey:@"snapshot"][@"upscale"],@1);
}
@end
'''


def native():
    # Do not select the newest installed OS: newer Xcode runtimes coexist on
    # hosted runners and can fail to connect to the older XCTest manager.
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
    catalogue = sorted(path for path in CATALOGUE.glob('*.m') if path.name != 'NeoCheatCatalogPlugin.m')
    with tempfile.TemporaryDirectory(prefix='armsx2-graphics-tests-') as folder:
        directory = Path(folder)
        (directory / 'main.m').write_text(APP)
        (directory / 'ARMSX2GraphicsTests.mm').write_text(TESTS)
        # <neo_cheat_catalog/...> and <external_display/...> as the pods publish them.
        include = stage_dependency_headers(directory)
        # Build 484: the menu's Touch controls page reads NeoTouchLayoutStrings.
        stage_touch_layout(include)
        sdk_dependencies = [{'sdk': 'UIKit.framework'}, {'sdk': 'QuartzCore.framework'}, {'sdk': 'Foundation.framework'},
                            {'sdk': 'Security.framework'}, {'sdk': 'MetalKit.framework'}, {'sdk': 'Metal.framework'},
                            {'sdk': 'libz.tbd'}, {'sdk': 'UniformTypeIdentifiers.framework'}]
        search_paths = ' '.join(str(p) for p in (CLASSES, include, CATALOGUE, CATALOGUE / 'Public'))
        project = {
            'name': 'ARMSX2Graphics26',
            'options': {'deploymentTarget': {'iOS': '17.4'}},
            'settings': {'base': {'CLANG_ENABLE_OBJC_ARC': 'YES', 'CLANG_ENABLE_MODULES': 'YES',
                                  'CLANG_CXX_LANGUAGE_STANDARD': 'c++20',
                                  'CODE_SIGNING_ALLOWED': 'YES', 'CODE_SIGN_IDENTITY': '-',
                                  'GENERATE_INFOPLIST_FILE': 'YES',
                                  'HEADER_SEARCH_PATHS': search_paths}},
            'targets': {
                'ARMSX2GraphicsHost': {'type': 'application', 'platform': 'iOS',
                    'sources': [str(directory / 'main.m'), str(CLASSES / 'Armsx2SessionMenu.mm'),
                                str(CLASSES / 'Armsx2RetroAchievementsMenu.mm'), str(CLASSES / 'ARMSX2InGameLocalization.mm')]
                               + [str(source) for source in catalogue]
                               + [str(TOUCH_STRINGS)],
                    'dependencies': sdk_dependencies,
                    'settings': {'base': {'PRODUCT_BUNDLE_IDENTIFIER': 'org.neostation.armsx2graphics.host',
                        'INFOPLIST_KEY_UILaunchScreen_Generation': 'YES'}}},
                'ARMSX2GraphicsTests': {'type': 'bundle.unit-test', 'platform': 'iOS',
                    'sources': [str(directory / 'ARMSX2GraphicsTests.mm')],
                    'dependencies': [{'target': 'ARMSX2GraphicsHost'}] + sdk_dependencies,
                    'settings': {'base': {'PRODUCT_BUNDLE_IDENTIFIER': 'org.neostation.armsx2graphics.tests',
                        'TEST_HOST': '$(BUILT_PRODUCTS_DIR)/ARMSX2GraphicsHost.app/ARMSX2GraphicsHost',
                        'BUNDLE_LOADER': '$(TEST_HOST)'}}},
            },
            'schemes': {'ARMSX2Graphics26': {'build': {'targets': {'ARMSX2GraphicsHost': 'all', 'ARMSX2GraphicsTests': 'test'}},
                                             'test': {'targets': ['ARMSX2GraphicsTests']}}},
        }
        spec = directory / 'project.json'
        spec.write_text(json.dumps(project))
        subprocess.run(['xcodegen', 'generate', '--spec', str(spec), '--project', str(directory)], check=True)
        result = ROOT / 'build/armsx2-validation/ARMSX2Graphics26.xcresult'
        result.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['xcodebuild', 'test', '-project', str(directory / 'ARMSX2Graphics26.xcodeproj'),
            '-scheme', 'ARMSX2Graphics26', '-destination', 'platform=iOS Simulator,id=' + device['udid'],
            '-destination-timeout', '60', '-parallel-testing-enabled', 'NO',
            '-test-timeouts-enabled', 'YES', '-default-test-execution-time-allowance', '60',
            '-maximum-test-execution-time-allowance', '120', '-resultBundlePath', str(result),
            'CODE_SIGNING_ALLOWED=YES', 'CODE_SIGN_IDENTITY=-', 'DEVELOPMENT_TEAM='], check=True, timeout=900)
    print(f'PASS: {len(catalogue)} catalogue classes linked; Graphics rows, blending page, shaders, search, download and overlays executed on UIKit', flush=True)


if __name__ == '__main__':
    native()

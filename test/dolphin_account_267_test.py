#!/usr/bin/env python3
"""Source contracts plus real UIKit/XCTest regression tests on an iOS simulator."""
from pathlib import Path
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/dolphin_internal_bridge/ios/Classes'
# Build 447: DolphinExternalDisplay.mm and DolphinFramePacing.mm import the
# external_display pod as <external_display/...> and call its coordinator and
# preferences. The host compiles the pod's Flutter-free sources and searches
# its public headers, staged by test/libretro_ios_syntax_test.py exactly as
# the pod publishes them. A harness derived from this one (exec/replace)
# empties EXTERNAL_SOURCES when it lists the pod sources itself.
EXTERNAL_CLASSES = ROOT / 'packages/external_display/ios/Classes'
EXTERNAL_SOURCES = [EXTERNAL_CLASSES / 'NeoExternalDisplayCoordinator.m',
                    EXTERNAL_CLASSES / 'NeoExternalDisplayPreferences.m']
# Build 474: DolphinSessionMenu.mm imports the unified cheat catalogue pod as
# <neo_cheat_catalog/...> and shows its list and browser. The host compiles
# the pod's Flutter-free sources (zlib, UniformTypeIdentifiers) and searches
# the public headers of every pod the bridge depends on, staged as the pods
# publish them. A derived harness that does not compile the menu empties
# CATALOGUE_SOURCES.
CATALOGUE_CLASSES = ROOT / 'packages/neo_cheat_catalog/ios/Classes'
CATALOGUE_SOURCES = sorted(path for path in CATALOGUE_CLASSES.glob('*.m') if path.name != 'NeoCheatCatalogPlugin.m')
CATALOGUE_SDKS = ('libz.tbd', 'UniformTypeIdentifiers.framework')
sys.path.insert(0, str(ROOT / 'test'))

TESTS = r'''
#import <XCTest/XCTest.h>
#import "DolphinSessionMenu.h"
#import "DolphinRetroAchievementsAccount.h"

@interface DolphinSessionMenu (AccountTesting)
- (NSArray<NSString*>*)rootKeys;
- (void)apply:(NSDictionary*)request thenReturn:(BOOL)returnToBindings;
@end
@interface DolphinAccountTests : XCTestCase
@end
@implementation DolphinAccountTests
- (DolphinSessionMenu*)rootMenu {
  DolphinSessionMenu* menu = [DolphinSessionMenu new];
  menu.labels = @{@"resume": @"Resume", @"back": @"Back", @"settingsFailed": @"Failed", @"close": @"Close"};
  [menu loadViewIfNeeded];
  return menu;
}
- (void)testRootKeepsGameControlsAndHasNoEngineAccountEntry {
  DolphinSessionMenu* menu = [self rootMenu];
  NSArray* keys = [menu rootKeys];
  for (NSString* key in @[@"graphics", @"hacks", @"cheats", @"controls", @"console", @"saveState", @"loadState", @"resume", @"quit"])
    XCTAssertTrue([keys containsObject:key], @"%@", key);
  XCTAssertFalse([keys containsObject:@"achievements"]);
  XCTAssertFalse([keys containsObject:@"raAccount"]);
}
- (void)testFormerAccountControllerAndHandlersAreAbsent {
  XCTAssertNil(NSClassFromString(@"DolphinRetroAchievementsAccount"));
  DolphinSessionMenu* menu = [self rootMenu];
  XCTAssertFalse([menu respondsToSelector:NSSelectorFromString(@"linkAccount")]);
  XCTAssertFalse([menu respondsToSelector:NSSelectorFromString(@"unlinkAccount")]);
}
- (void)testRetiredPageAndOutOfRangeTapsCannotOpenAccountOrApplySettings {
  DolphinSessionMenu* menu = [self rootMenu];
  __block NSUInteger calls = 0;
  menu.applySettings = ^(NSDictionary* request, void (^done)(BOOL)) { ++calls; done(YES); };
  UINavigationController* navigation = [[UINavigationController alloc] initWithRootViewController:menu];
  [navigation loadViewIfNeeded];
  for (NSNumber* page in @[@4, @99]) { // 4 was the removed achievements/account page.
    [menu setValue:page forKey:@"page"];
    XCTAssertEqual([menu tableView:menu.tableView numberOfRowsInSection:0], 0);
    for (NSNumber* row in @[@0, @99])
      XCTAssertNoThrow([menu tableView:menu.tableView didSelectRowAtIndexPath:
          [NSIndexPath indexPathForRow:row.integerValue inSection:0]]);
  }
  XCTAssertEqual(navigation.viewControllers.count, 1U);
  XCTAssertEqual(calls, 0U);
}
- (void)testSerializerRejectsNilNullWrongKindsAndNonJSONValues {
  XCTAssertNil(DOLSerializeMenuRequest(nil));
  XCTAssertNil(DOLSerializeMenuRequest(NSNull.null));
  XCTAssertNil(DOLSerializeMenuRequest(@[]));
  XCTAssertNil(DOLSerializeMenuRequest(@{}));
  XCTAssertNil(DOLSerializeMenuRequest(@{@"kind": NSNull.null}));
  XCTAssertNil(DOLSerializeMenuRequest(@{@"kind": @""}));
  XCTAssertNil(DOLSerializeMenuRequest(@{@"kind": @"hack", @"value": [NSObject new]}));
  XCTAssertNotNil(DOLSerializeMenuRequest(@{@"kind": @"hack", @"key": @"viSkip", @"value": @NO}));
}
- (void)testNilRequestCannotReachNativeSettingsCallback {
  DolphinSessionMenu* menu = [self rootMenu];
  __block NSUInteger calls = 0;
  menu.applySettings = ^(NSDictionary* request, void (^done)(BOOL)) { ++calls; done(YES); };
  XCTAssertNoThrow([menu apply:(id)nil thenReturn:NO]);
  XCTAssertEqual(calls, 0U);
}
- (void)testValidRequestStillReachesNativeSettingsCallback {
  DolphinSessionMenu* menu = [self rootMenu];
  __block NSUInteger calls = 0;
  NSDictionary* request = @{@"kind": @"hack", @"key": @"viSkip", @"value": @NO};
  menu.applySettings = ^(NSDictionary* received, void (^done)(BOOL)) {
    XCTAssertEqualObjects(received, request); ++calls; done(YES);
  };
  [menu apply:request thenReturn:NO];
  XCTAssertEqual(calls, 1U);
}
- (void)testHardcoreBlockedLoadCannotReachStateOperation {
  DolphinSessionMenu* menu = [self rootMenu];
  [menu setValue:@11 forKey:@"page"]; // DOLMenuLoadStates retains its prior value.
  NSDictionary* slot = @{@"slot": @1, @"exists": @YES, @"loadable": @NO,
      @"modified": @0, @"filename": @"GAME01.s01"};
  [menu setValue:@{@"slots": @[slot]} forKey:@"snapshot"];
  __block NSUInteger calls = 0;
  menu.performStateOperation = ^(NSInteger number, BOOL load, void (^done)(BOOL)) { ++calls; done(YES); };
  [menu tableView:menu.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:0 inSection:0]];
  XCTAssertEqual(calls, 0U);
}
- (void)testCreatingAStateRemainsAvailableWhenLoadingIsBlocked {
  DolphinSessionMenu* menu = [self rootMenu];
  [menu setValue:@10 forKey:@"page"]; // DOLMenuSaveStates.
  NSDictionary* snapshot = @{@"slots": @[@{@"slot": @1, @"exists": @NO,
      @"loadable": @NO, @"modified": @0, @"filename": @"GAME01.s01"}]};
  [menu setValue:snapshot forKey:@"snapshot"];
  menu.readStates = ^(void (^done)(NSDictionary*)) { done(snapshot); };
  __block NSUInteger calls = 0;
  menu.performStateOperation = ^(NSInteger slot, BOOL load, void (^done)(BOOL)) {
    XCTAssertEqual(slot, 1); XCTAssertFalse(load); ++calls; done(YES);
  };
  [menu tableView:menu.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:0 inSection:0]];
  XCTAssertEqual(calls, 1U);
}
@end
'''

APP = r'''
#import <UIKit/UIKit.h>
#import "TouchController/TCManagerInterface.h"
// The UIKit fixture does not link an emulator. Production motion routing is
// executed separately by dolphin_phone_shake_routing_test.py on macOS.
@implementation TCManagerInterface
+ (void)setButtonStateFor:(NSInteger)button controller:(NSInteger)controllerId state:(BOOL)state {}
+ (void)setAxisValueFor:(NSInteger)axis controller:(NSInteger)controllerId value:(float)value {}
+ (BOOL)preparePhoneShakeRouting { return YES; }
+ (NSInteger)phoneShakeRoutingStatus { return [NSUserDefaults.standardUserDefaults integerForKey:@"Test.PhoneShakeRouteStatus"]; }
+ (void)reportPhoneShakeSensorUnavailable { [NSUserDefaults.standardUserDefaults setInteger:3 forKey:@"Test.PhoneShakeRouteStatus"]; }
@end
@interface AccountTestDelegate : UIResponder <UIApplicationDelegate>
@property(nonatomic, strong) UIWindow* window;
@end
@implementation AccountTestDelegate
- (BOOL)application:(UIApplication*)application didFinishLaunchingWithOptions:(NSDictionary*)options {
  self.window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
  self.window.rootViewController = [UIViewController new];
  [self.window makeKeyAndVisible];
  return YES;
}
@end
int main(int argc, char** argv) {
  @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(AccountTestDelegate.class)); }
}
'''


def contracts():
    paths = [CLASSES / 'DolphinSessionMenu.mm', CLASSES / 'DolphinInternalBridgePlugin.mm',
             CLASSES / 'DolphinRetroAchievementsAccount.mm', CLASSES / 'DolphinRetroAchievementsAccount.h']
    before = [p.read_bytes() for p in paths]
    for _ in range(2):
        subprocess.run(['python3', str(ROOT / 'build-utils/patch_dolphin_build267_account.py')], check=True)
        assert before == [p.read_bytes() for p in paths], 'Compatibility build hook must not rewrite sources'
    menu, host, account, header = [p.read_text() for p in paths]
    assert 'DOLMenuAchievements' not in menu and '@"raAccount"' not in menu
    assert 'else if (self.page == DOLMenuChoices)' in menu
    assert 'if (!DOLSerializeMenuRequest(request))' in menu
    assert 'NSData* data = DOLSerializeMenuRequest(request)' in host
    assert 'RBRATakeLaunchConfiguration' in host
    assert '[DolphinRetroAchievementsAccount credentials]' not in host
    for forbidden in ('SecItem', 'NSURLSession', 'linkAccount', 'unlinkAccount', 'loginRequestForUsername',
                      'credentialsFromResponse', '@interface DolphinRetroAchievementsAccount'):
        assert forbidden not in account + header, forbidden
    assert 'DOLSerializeMenuRequest' in account and 'DOLSerializeMenuRequest' in header
    print('Dolphin central account ownership, retired UI and retained menu validation: source contracts passed', flush=True)


def native():
    from libretro_ios_syntax_test import stage_dependency_headers
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
    with tempfile.TemporaryDirectory(prefix='dolphin-account-tests-') as folder:
        directory = Path(folder)
        (directory / 'main.m').write_text(APP)
        (directory / 'DolphinAccountTests.mm').write_text(TESTS)
        include = stage_dependency_headers(directory)
        sdk_dependencies = [{'sdk': 'UIKit.framework'}, {'sdk': 'QuartzCore.framework'}, {'sdk': 'Foundation.framework'}, {'sdk': 'Security.framework'},
                            {'sdk': 'MetalKit.framework'}, {'sdk': 'Metal.framework'}]
        if CATALOGUE_SOURCES:
            sdk_dependencies += [{'sdk': name} for name in CATALOGUE_SDKS if {'sdk': name} not in sdk_dependencies]
        project = {
            'name': 'DolphinAccount267',
            'options': {'deploymentTarget': {'iOS': '18.0'}},
            'settings': {'base': {'CLANG_ENABLE_OBJC_ARC': 'YES', 'CLANG_ENABLE_MODULES': 'YES',
                                  'CODE_SIGNING_ALLOWED': 'YES', 'CODE_SIGN_IDENTITY': '-',
                                  'GENERATE_INFOPLIST_FILE': 'YES',
                                  'HEADER_SEARCH_PATHS': str(CLASSES) + ' ' + str(include)}},
            'targets': {
                'DolphinAccountHost': {'type': 'application', 'platform': 'iOS',
                    'sources': [str(directory / 'main.m'), str(CLASSES / 'DolphinSessionMenu.mm'),
                                str(CLASSES / 'DolphinRetroAchievementsAccount.mm'), str(CLASSES / 'DolphinFramePacing.mm'), str(CLASSES / 'DolphinExternalDisplay.mm'),
                                # Skins orientation (705e90c7): the session menu reads the session mask (DOLOrientation).
                                str(CLASSES / 'DOLOrientation.mm')]
                               + [str(source) for source in EXTERNAL_SOURCES]
                               + [str(source) for source in CATALOGUE_SOURCES],
                    'dependencies': sdk_dependencies,
                    'settings': {'base': {'PRODUCT_BUNDLE_IDENTIFIER': 'org.neostation.accounttests.host',
                        'INFOPLIST_KEY_UILaunchScreen_Generation': 'YES'}}},
                'DolphinAccountTests': {'type': 'bundle.unit-test', 'platform': 'iOS',
                    'sources': [str(directory / 'DolphinAccountTests.mm')],
                    'dependencies': [{'target': 'DolphinAccountHost'}] + sdk_dependencies,
                    'settings': {'base': {'PRODUCT_BUNDLE_IDENTIFIER': 'org.neostation.accounttests.tests',
                        'TEST_HOST': '$(BUILT_PRODUCTS_DIR)/DolphinAccountHost.app/DolphinAccountHost',
                        'BUNDLE_LOADER': '$(TEST_HOST)'}}},
            },
            'schemes': {'DolphinAccount267': {'build': {'targets': {'DolphinAccountHost': 'all', 'DolphinAccountTests': 'test'}},
                                            'test': {'targets': ['DolphinAccountTests']}}},
        }
        spec = directory / 'project.json'
        spec.write_text(json.dumps(project))
        subprocess.run(['xcodegen', 'generate', '--spec', str(spec), '--project', str(directory)], check=True)
        result = ROOT / 'build/rpcs3-ci/DolphinAccount267.xcresult'
        result.parent.mkdir(parents=True, exist_ok=True)
        # The derived harnesses share this bundle path: xcodebuild refuses an
        # existing one, so a bundle left by an earlier harness is replaced.
        if result.exists():
            shutil.rmtree(result)
        subprocess.run(['xcodebuild', 'test', '-project', str(directory / 'DolphinAccount267.xcodeproj'),
            '-scheme', 'DolphinAccount267', '-destination', 'platform=iOS Simulator,id=' + device['udid'],
            '-destination-timeout', '60', '-parallel-testing-enabled', 'NO',
            '-test-timeouts-enabled', 'YES', '-default-test-execution-time-allowance', '60',
            '-maximum-test-execution-time-allowance', '120', '-resultBundlePath', str(result),
            'CODE_SIGNING_ALLOWED=YES', 'CODE_SIGN_IDENTITY=-', 'DEVELOPMENT_TEAM='], check=True, timeout=600)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native', action='store_true')
    arguments = parser.parse_args()
    contracts()
    if arguments.native:
        native()

#!/usr/bin/env python3
"""Build 440 "120 Hz interface": the engine hook against the real Flutter.xcframework.

macOS only (Xcode, xcodegen, an iOS simulator and `flutter precache --ios`).
Builds a host app that compiles the production plugin sources with the test
seams enabled (NEO_UI_REFRESH_TESTING=1), links and embeds the pinned
Flutter.xcframework, and carries `CADisableMinimumFrameDurationOnPhone = YES`
like every NeoStation IPA. The XCTest bundle then checks, on the simulator:

- the seam `+[FlutterDisplayLinkManager displayRefreshRate]` exists with the
  validated encoding, and the hook was installed by `+load` before main();
- disabled caps the engine at 60 Hz, enabled is a pass-through of the real
  engine value;
- the engine's own FlutterMetalLayer display link gets 60/60/60 when disabled
  and 60/120/120 when enabled (with the original stubbed at 120 Hz);
- negative controls: a fresh CADisplayLink keeps the system default range,
  UIScreen keeps its maximum, the CADisplayLink/UIScreen/NSBundle methods
  still resolve to the system images and the Info.plist key is unchanged;
- the channel: getState fields, setEnabled stores NSUserDefaults without
  changing the running snapshot, BAD_ARGS and not-implemented answers.

Also compiles both production sources for an iPhone (arm64, iOS 17.4) with
-Wall -Werror against the device slice.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/ui_refresh_rate/ios/Classes'
SOURCES = [CLASSES / 'UiRefreshRatePlugin.m', CLASSES / 'UiRefreshRateEngineHook.m']

APP = r'''
#import <UIKit/UIKit.h>
#import "UiRefreshRateEngineHook.h"

// Hook status observed at the very start of main(): only +load ran before.
NSInteger NeoUiTestStatusAtMain = -1;

@interface UiRefreshHostDelegate : UIResponder <UIApplicationDelegate>
@property(nonatomic, strong) UIWindow *window;
@end
@implementation UiRefreshHostDelegate
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)options {
  self.window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
  self.window.rootViewController = [UIViewController new];
  [self.window makeKeyAndVisible];
  return YES;
}
@end

int main(int argc, char *argv[]) {
  NeoUiTestStatusAtMain = NeoUiRefreshCurrentHookStatus();
  @autoreleasepool {
    return UIApplicationMain(argc, argv, nil, NSStringFromClass(UiRefreshHostDelegate.class));
  }
}
'''

TESTS = r'''
#import <XCTest/XCTest.h>
#import <QuartzCore/QuartzCore.h>
#import <UIKit/UIKit.h>
#import <dlfcn.h>
#import <math.h>
#import <objc/message.h>
#import <objc/runtime.h>
#import <string.h>
#import <Flutter/Flutter.h>
#import "UiRefreshRateEngineHook.h"
#import "UiRefreshRatePlugin.h"

extern NSInteger NeoUiTestStatusAtMain;

static double NeoStub120(id receiver, SEL selector) { return 120.0; }

static Class EngineClass(void) { return objc_getClass("FlutterDisplayLinkManager"); }
static SEL RateSelector(void) { return sel_registerName("displayRefreshRate"); }
static double EngineRate(void) {
  return ((double (*)(id, SEL))objc_msgSend)((id)EngineClass(), RateSelector());
}

/// Range the engine's own Metal layer gives its main-thread display link.
static CAFrameRateRange MetalLayerRange(void) {
  Class layerClass = NSClassFromString(@"FlutterMetalLayer");
  NSCAssert(layerClass != Nil, @"FlutterMetalLayer missing");
  id layer = [[layerClass alloc] init];
  Ivar ivar = class_getInstanceVariable(layerClass, "_displayLink");
  NSCAssert(ivar != NULL, @"FlutterMetalLayer._displayLink missing");
  CADisplayLink *link = object_getIvar(layer, ivar);
  NSCAssert(link != nil, @"FlutterMetalLayer has no display link");
  return link.preferredFrameRateRange;
}

static NSString *ImagePath(IMP implementation) {
  Dl_info info = {0};
  if (dladdr((const void *)implementation, &info) == 0 || info.dli_fname == NULL) return @"";
  return @(info.dli_fname);
}

@interface UiRefreshRateHookTests : XCTestCase
@end

@implementation UiRefreshRateHookTests {
  NeoUiRefreshRateFunction _original;
  BOOL _active;
}

- (void)setUp {
  _active = NeoUiRefreshActiveEnabled();
  _original = NeoUiRefreshTestingSwapOriginal(NULL);
  NeoUiRefreshTestingSwapOriginal(_original);
  [NSUserDefaults.standardUserDefaults removeObjectForKey:NeoUiRefreshPreferenceKey];
}

- (void)tearDown {
  NeoUiRefreshTestingSwapOriginal(_original);
  NeoUiRefreshTestingSetActiveEnabled(_active);
  [NSUserDefaults.standardUserDefaults removeObjectForKey:NeoUiRefreshPreferenceKey];
}

- (void)tick:(CADisplayLink *)link {}

- (void)testEngineSeamMatchesTheValidatedSignature {
  Class cls = EngineClass();
  XCTAssertNotNil(cls);
  Method method = class_getClassMethod(cls, RateSelector());
  XCTAssertTrue(method != NULL);
  XCTAssertEqual(strcmp(method_getTypeEncoding(method), NeoUiRefreshExpectedTypeEncoding), 0);
  // The host carries the ProMotion opt-in, like every NeoStation IPA.
  BOOL optIn = ((BOOL (*)(id, SEL))objc_msgSend)((id)cls, sel_registerName("maxRefreshRateEnabledOnIPhone"));
  XCTAssertTrue(optIn);
}

- (void)testHookWasInstalledByLoadBeforeMain {
  XCTAssertEqual(NeoUiTestStatusAtMain, (NSInteger)NeoUiRefreshHookStatusInstalled);
  XCTAssertEqual(NeoUiRefreshCurrentHookStatus(), NeoUiRefreshHookStatusInstalled);
  XCTAssertEqualObjects(NeoUiRefreshHookStatusName(NeoUiRefreshCurrentHookStatus()), @"installed");
  Method method = class_getClassMethod(EngineClass(), RateSelector());
  IMP installed = method_getImplementation(method);
  NSString *hookImage = ImagePath(installed);
  XCTAssertEqualObjects(hookImage, ImagePath((IMP)&NeoUiRefreshPolicy), @"replacement lives in the app");
  XCTAssertFalse([hookImage containsString:@"Flutter.framework"]);
  XCTAssertTrue([ImagePath((IMP)_original) containsString:@"Flutter.framework"], @"original kept");
  NeoUiRefreshInstallEngineHook();  // idempotent
  XCTAssertEqual(method_getImplementation(method), installed);
  XCTAssertEqual(NeoUiRefreshTestingSwapOriginal(_original), _original);
}

- (void)testPolicy {
  XCTAssertEqual(NeoUiRefreshPolicy(120, YES), 120);
  XCTAssertEqual(NeoUiRefreshPolicy(120, NO), 60);
  XCTAssertEqual(NeoUiRefreshPolicy(60, NO), 60);
  XCTAssertEqual(NeoUiRefreshPolicy(48, NO), 48);
  XCTAssertEqual(NeoUiRefreshPolicy(240, YES), 240);
  XCTAssertEqual(NeoUiRefreshPolicy(0, NO), 0);
  XCTAssertEqual(NeoUiRefreshPolicy(-1, NO), -1);
  XCTAssertTrue(isnan(NeoUiRefreshPolicy(NAN, NO)));
}

- (void)testEngineRequestIsCappedOnlyWhenDisabled {
  NeoUiRefreshTestingSwapOriginal(NeoStub120);
  NeoUiRefreshTestingSetActiveEnabled(NO);
  XCTAssertEqual(EngineRate(), 60.0);
  XCTAssertEqual(NeoUiRefreshEngineTargetHz(), 60.0);
  NeoUiRefreshTestingSetActiveEnabled(YES);
  XCTAssertEqual(EngineRate(), 120.0);
  XCTAssertEqual(NeoUiRefreshEngineTargetHz(), 120.0);
}

- (void)testEnabledIsAPassThroughOfTheRealEngineValue {
  double real = _original((id)EngineClass(), RateSelector());
  XCTAssertEqual(real, (double)UIScreen.mainScreen.maximumFramesPerSecond);
  NeoUiRefreshTestingSetActiveEnabled(YES);
  XCTAssertEqual(EngineRate(), real);
  NeoUiRefreshTestingSetActiveEnabled(NO);
  XCTAssertEqual(EngineRate(), MIN(real, 60.0));
}

- (void)testFlutterMetalLayerLinkFollowsThePolicy {
  NeoUiRefreshTestingSwapOriginal(NeoStub120);
  NeoUiRefreshTestingSetActiveEnabled(NO);
  CAFrameRateRange capped = MetalLayerRange();
  NSLog(@"FlutterMetalLayer disabled range %.0f/%.0f/%.0f", capped.minimum, capped.maximum, capped.preferred);
  XCTAssertEqual(capped.minimum, 60.0f);
  XCTAssertEqual(capped.maximum, 60.0f);
  XCTAssertEqual(capped.preferred, 60.0f);
  NeoUiRefreshTestingSetActiveEnabled(YES);
  CAFrameRateRange full = MetalLayerRange();
  NSLog(@"FlutterMetalLayer enabled range %.0f/%.0f/%.0f", full.minimum, full.maximum, full.preferred);
  XCTAssertEqual(full.minimum, 60.0f);
  XCTAssertEqual(full.maximum, 120.0f);
  XCTAssertEqual(full.preferred, 120.0f);
}

- (void)testEmulatorFacingApisAreUntouched {
  NSInteger screenMax = UIScreen.mainScreen.maximumFramesPerSecond;
  XCTAssertGreaterThan(screenMax, 0);
  // An emulator's own display link is the same whatever the option says.
  BOOL haveBaseline = NO;
  CAFrameRateRange baseline = CAFrameRateRangeDefault;
  for (NSNumber *enabled in @[ @NO, @YES, @NO ]) {
    NeoUiRefreshTestingSetActiveEnabled(enabled.boolValue);
    CADisplayLink *link = [CADisplayLink displayLinkWithTarget:self selector:@selector(tick:)];
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    XCTAssertEqual(link.preferredFramesPerSecond, 0);
#pragma clang diagnostic pop
    CAFrameRateRange range = link.preferredFrameRateRange;
    NSLog(@"fresh CADisplayLink range %.0f/%.0f/%.0f (option %@)", range.minimum, range.maximum,
          range.preferred, enabled);
    if (!haveBaseline) {
      baseline = range;
      haveBaseline = YES;
    }
    XCTAssertTrue(CAFrameRateRangeIsEqualToRange(range, baseline));
    link.preferredFrameRateRange = CAFrameRateRangeMake(120, 120, 120);  // an emulator's request
    XCTAssertEqual(link.preferredFrameRateRange.maximum, 120.0f);
    [link invalidate];
    XCTAssertEqual(UIScreen.mainScreen.maximumFramesPerSecond, screenMax);
  }
  XCTAssertEqualObjects([NSBundle.mainBundle objectForInfoDictionaryKey:@"CADisableMinimumFrameDurationOnPhone"], @YES);
  NSString *app = ImagePath((IMP)&NeoUiRefreshPolicy);
  NSArray<NSArray *> *systemMethods = @[
    @[ CADisplayLink.class, @"setPreferredFrameRateRange:" ],
    @[ CADisplayLink.class, @"preferredFrameRateRange" ],
    @[ CADisplayLink.class, @"setPreferredFramesPerSecond:" ],
    @[ object_getClass(CADisplayLink.class), @"displayLinkWithTarget:selector:" ],
    @[ UIScreen.class, @"maximumFramesPerSecond" ],
    @[ NSBundle.class, @"objectForInfoDictionaryKey:" ],
  ];
  for (NSArray *entry in systemMethods) {
    IMP implementation = class_getMethodImplementation((Class)entry[0], NSSelectorFromString(entry[1]));
    NSString *image = ImagePath(implementation);
    XCTAssertTrue([image containsString:@"/System/Library/"] || [image containsString:@"/usr/lib/"],
                  @"%@ resolves to %@", entry[1], image);
    XCTAssertNotEqualObjects(image, app, @"%@", entry[1]);
  }
}

- (void)testDefaultIsEnabledAndSetEnabledOnlyStoresForTheNextLaunch {
  NSUserDefaults *defaults = NSUserDefaults.standardUserDefaults;
  XCTAssertNil([defaults objectForKey:NeoUiRefreshPreferenceKey]);
  XCTAssertTrue(NeoUiRefreshStoredEnabled());
  BOOL active = NeoUiRefreshActiveEnabled();
  UiRefreshRatePlugin *plugin = [UiRefreshRatePlugin new];
  for (NSNumber *value in @[ @NO, @YES, @NO ]) {
    __block id answer = nil;
    [plugin handleMethodCall:[FlutterMethodCall methodCallWithMethodName:@"setEnabled"
                                                               arguments:@{@"enabled" : value}]
                      result:^(id result) { answer = result; }];
    XCTAssertTrue([answer isKindOfClass:NSDictionary.class], @"%@", answer);
    XCTAssertEqualObjects(answer[@"storedEnabled"], value);
    XCTAssertEqualObjects(answer[@"activeEnabled"], @(active));
    XCTAssertEqualObjects([defaults objectForKey:NeoUiRefreshPreferenceKey], value);
    XCTAssertEqual(NeoUiRefreshActiveEnabled(), active, @"the running process keeps its rate");
  }
  __block id error = nil;
  [plugin handleMethodCall:[FlutterMethodCall methodCallWithMethodName:@"setEnabled" arguments:@{}]
                    result:^(id result) { error = result; }];
  XCTAssertTrue([error isKindOfClass:FlutterError.class]);
  XCTAssertEqualObjects(((FlutterError *)error).code, @"BAD_ARGS");
  __block id unknown = nil;
  [plugin handleMethodCall:[FlutterMethodCall methodCallWithMethodName:@"other" arguments:nil]
                    result:^(id result) { unknown = result; }];
  XCTAssertEqual(unknown, FlutterMethodNotImplemented);
}

- (void)testGetStateReportsScreenHookAndSystemLimits {
  UiRefreshRatePlugin *plugin = [UiRefreshRatePlugin new];
  __block NSDictionary *state = nil;
  [plugin handleMethodCall:[FlutterMethodCall methodCallWithMethodName:@"getState" arguments:nil]
                    result:^(id result) { state = result; }];
  XCTAssertEqualObjects(state[@"hookStatus"], @"installed");
  XCTAssertEqualObjects(state[@"screenMaxHz"], @(UIScreen.mainScreen.maximumFramesPerSecond));
  XCTAssertEqualObjects(state[@"cappedHz"], @60);
  XCTAssertEqualObjects(state[@"engineTargetHz"], @(NeoUiRefreshEngineTargetHz()));
  XCTAssertEqualObjects(state[@"storedEnabled"], @YES);
  XCTAssertEqualObjects(state[@"activeEnabled"], @(NeoUiRefreshActiveEnabled()));
  XCTAssertEqualObjects(state[@"lowPowerMode"], @(NSProcessInfo.processInfo.lowPowerModeEnabled));
  XCTAssertEqualObjects(state[@"thermalState"], @((NSInteger)NSProcessInfo.processInfo.thermalState));
  XCTAssertEqual(state.count, (NSUInteger)8);
  XCTAssertEqualObjects([NSSet setWithArray:[plugin currentState].allKeys], [NSSet setWithArray:state.allKeys]);
}
@end
'''


def flutter_root() -> Path:
    if os.environ.get('FLUTTER_ROOT'):
        return Path(os.environ['FLUTTER_ROOT'])
    found = shutil.which('flutter')
    if not found:
        raise SystemExit('flutter is not on PATH and FLUTTER_ROOT is not set')
    return Path(found).resolve().parents[1]


def flutter_xcframework() -> Path:
    xcframework = flutter_root() / 'bin/cache/artifacts/engine/ios/Flutter.xcframework'
    if not (xcframework / 'Info.plist').is_file():
        raise SystemExit(f'{xcframework} missing: run `flutter precache --ios` first')
    return xcframework


def device_slice(xcframework: Path) -> Path:
    for candidate in sorted(xcframework.iterdir()):
        if candidate.is_dir() and candidate.name.startswith('ios-arm64') and 'simulator' not in candidate.name:
            return candidate
    raise SystemExit(f'no device slice in {xcframework}')


def compile_for_iphone(xcframework: Path) -> None:
    sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
    for source in SOURCES:
        subprocess.run([
            'xcrun', 'clang', '-x', 'objective-c', '-fobjc-arc', '-fmodules', '-fsyntax-only',
            '-Wall', '-Werror', '-target', 'arm64-apple-ios17.4', '-isysroot', sdk,
            '-F', str(device_slice(xcframework)), '-I', str(CLASSES), str(source),
        ], check=True)
    print('iPhone arm64 syntax check: OK', flush=True)


def simulator_device() -> dict:
    sdk = subprocess.check_output(['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-version'], text=True).strip()
    runtime_key = 'com.apple.CoreSimulator.SimRuntime.iOS-' + sdk.replace('.', '-')
    devices = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', 'available', '-j']))['devices']
    candidates = [device for runtime, items in devices.items() if runtime == runtime_key
                  for device in items if device['name'].startswith('iPhone') and device.get('isAvailable')]
    if not candidates:
        raise RuntimeError(f'A simulator matching the selected Xcode SDK {sdk} is required; installed: {sorted(devices)}')
    # Prefer a ProMotion model when one is installed (the result must not depend on it).
    candidates.sort(key=lambda device: ('Pro' not in device['name'], device['name']))
    device = candidates[0]
    print(f"Testing on {device['name']} / iOS {sdk} / {device['udid']}", flush=True)
    if device.get('state') != 'Booted':
        subprocess.run(['xcrun', 'simctl', 'boot', device['udid']], check=True, timeout=60)
    subprocess.run(['xcrun', 'simctl', 'bootstatus', device['udid'], '-b'], check=True, timeout=180)
    return device


def native() -> None:
    xcframework = flutter_xcframework()
    compile_for_iphone(xcframework)
    device = simulator_device()
    with tempfile.TemporaryDirectory(prefix='ui-refresh-rate-tests-') as folder:
        directory = Path(folder)
        (directory / 'main.m').write_text(APP)
        (directory / 'UiRefreshRateHookTests.m').write_text(TESTS)
        sdk_dependencies = [{'sdk': 'UIKit.framework'}, {'sdk': 'QuartzCore.framework'},
                            {'sdk': 'Foundation.framework'}]
        project = {
            'name': 'UiRefreshRate440',
            'options': {'deploymentTarget': {'iOS': '17.4'}},
            'settings': {'base': {
                'CLANG_ENABLE_OBJC_ARC': 'YES', 'CLANG_ENABLE_MODULES': 'YES',
                'CODE_SIGNING_ALLOWED': 'YES', 'CODE_SIGN_IDENTITY': '-',
                'HEADER_SEARCH_PATHS': str(CLASSES),
                'GCC_PREPROCESSOR_DEFINITIONS': '$(inherited) NEO_UI_REFRESH_TESTING=1',
            }},
            'targets': {
                'UiRefreshHost': {
                    'type': 'application', 'platform': 'iOS',
                    'sources': [str(directory / 'main.m')] + [str(source) for source in SOURCES],
                    'dependencies': [{'framework': str(xcframework), 'embed': True}] + sdk_dependencies,
                    'info': {'path': str(directory / 'HostInfo.plist'), 'properties': {
                        'CFBundleIdentifier': '$(PRODUCT_BUNDLE_IDENTIFIER)',
                        'CFBundleExecutable': '$(EXECUTABLE_NAME)',
                        'CFBundleName': '$(PRODUCT_NAME)',
                        'CFBundlePackageType': 'APPL',
                        'CFBundleShortVersionString': '1.0',
                        'CFBundleVersion': '1',
                        'UILaunchScreen': {},
                        # Same opt-in as the delivered IPA (Flutter template).
                        'CADisableMinimumFrameDurationOnPhone': True,
                    }},
                    'settings': {'base': {
                        'PRODUCT_BUNDLE_IDENTIFIER': 'org.neostation.uirefresh.host',
                        'GENERATE_INFOPLIST_FILE': 'NO',
                        # The test bundle links C functions of the host.
                        'DEAD_CODE_STRIPPING': 'NO',
                    }},
                },
                'UiRefreshTests': {
                    'type': 'bundle.unit-test', 'platform': 'iOS',
                    'sources': [str(directory / 'UiRefreshRateHookTests.m')],
                    'dependencies': [{'target': 'UiRefreshHost'},
                                     {'framework': str(xcframework), 'embed': False}] + sdk_dependencies,
                    'settings': {'base': {
                        'PRODUCT_BUNDLE_IDENTIFIER': 'org.neostation.uirefresh.tests',
                        'GENERATE_INFOPLIST_FILE': 'YES',
                        'TEST_HOST': '$(BUILT_PRODUCTS_DIR)/UiRefreshHost.app/UiRefreshHost',
                        'BUNDLE_LOADER': '$(TEST_HOST)',
                    }},
                },
            },
            'schemes': {'UiRefreshRate440': {
                'build': {'targets': {'UiRefreshHost': 'all', 'UiRefreshTests': 'test'}},
                'test': {'targets': ['UiRefreshTests']},
            }},
        }
        spec = directory / 'project.json'
        spec.write_text(json.dumps(project))
        subprocess.run(['xcodegen', 'generate', '--spec', str(spec), '--project', str(directory)], check=True)
        result = ROOT / 'build/ui-refresh-rate/UiRefreshRate440.xcresult'
        if result.exists():
            shutil.rmtree(result)
        result.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([
            'xcodebuild', 'test', '-project', str(directory / 'UiRefreshRate440.xcodeproj'),
            '-scheme', 'UiRefreshRate440', '-destination', 'platform=iOS Simulator,id=' + device['udid'],
            '-destination-timeout', '60', '-parallel-testing-enabled', 'NO',
            '-test-timeouts-enabled', 'YES', '-default-test-execution-time-allowance', '60',
            '-maximum-test-execution-time-allowance', '120', '-resultBundlePath', str(result),
            'CODE_SIGNING_ALLOWED=YES', 'CODE_SIGN_IDENTITY=-', 'DEVELOPMENT_TEAM=',
        ], check=True, timeout=900)
    print('UI refresh rate hook (simulator, real Flutter.xcframework): OK', flush=True)


if __name__ == '__main__':
    native()

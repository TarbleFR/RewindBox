#!/usr/bin/env python3
"""Source contracts of the external_display plugin, plus the placement policy
executed on macOS.

The contracts (docs/external-display-universal.md § 3 and § 8) are checked on
any OS: pure placement header holding the Build 442 arithmetic, Dolphin
header delegating to it, no makeKeyAndVisible on the external window,
render view returned before any stop or window release, legacy fallback
isolated in activateLegacyIfNeeded, iOS 27 scene accessory by selectors
(one registration per presented controller, released once dismissed),
menu engine never created while a game holds the TV, journal prefixes,
channel and preference names, dynamic podspec publishing every header a
bridge imports. On macOS the production NeoExternalDisplayLayout.h is then
compiled with Foundation and CoreGraphics only and
test/external_display_layout_test.mm compares it, number for number, with a
frozen copy of the Build 442 arithmetic (revision a221ae0c), as it compares
the delegating Dolphin header with the same copy. The window lifecycle runs
in the iOS Simulator through external_display_ui_test.py. No device claim.
"""
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'packages/external_display'
CLASSES = PACKAGE / 'ios/Classes'
DOLPHIN_CLASSES = ROOT / 'packages/dolphin_internal_bridge/ios/Classes'


def read(name: str) -> str:
    return (CLASSES / name).read_text(encoding='utf-8')


def code(text: str) -> str:
    """Source without comments (prose must not satisfy a contract)."""
    text = re.sub(r'/\*.*?\*/', ' ', text, flags=re.S)
    return re.sub(r'//[^\n]*', ' ', text)


def without_strings(text: str) -> str:
    return re.sub(r'@?"(?:\\.|[^"\\])*"', '""', text)


def method_body(source: str, signature: str) -> str:
    """The body of an Objective-C method, from its signature to the next
    method or @end at column zero."""
    start = source.index(signature)
    end = re.search(r'\n[-+@]', source[start + len(signature):])
    assert end is not None, signature
    return source[start:start + len(signature) + end.start()]


def check(condition: bool, label: str) -> None:
    assert condition, label


def layout_contracts() -> None:
    header = read('NeoExternalDisplayLayout.h')
    check('<UIKit/' not in header and '<MetalKit/' not in header, 'the placement policy stays executable without UIKit')
    for token in ('NeoExternalDisplayModeAutomatic = 0', 'NeoExternalDisplayModeFit = 1', 'NeoExternalDisplayModeFill = 2',
                  'NeoExternalDisplayModeOriginal = 3', 'NeoExternalContentNone = 0', 'NeoExternalContentMenu = 1',
                  'NeoExternalContentGame = 2'):
        check(token in header, token)
    for function in ('NeoExternalDisplayModeFromValue', 'NeoExternalDisplayEffectiveMode', 'NeoExternalDisplayUsableSize',
                     'NeoExternalDisplayScale', 'NeoExternalDisplayFrame', 'NeoExternalDisplaySurfaceSize',
                     'NeoExternalDisplayModeCrops'):
        check(re.search(r'static inline \w+ ' + function + r'\(', header) is not None, f'{function} is a static inline function')
    # Fit/Fill are the Build 442 math, kept number for number in this header
    # only. Retired assertion: the Dolphin header no longer holds a second
    # copy (it would drift from what the coordinator applies); it delegates
    # to this policy instead (test/dolphin_external_display_test.py checks the
    # rest of that adapter).
    for line in ('const CGFloat widescreen = source.height * 16.0 / 9.0;', 'const CGFloat fit = MIN(heightScale, screen.width / widescreen);',
                 'const CGFloat standard = source.height * 4.0 / 3.0;', 'const CGFloat fill = screen.width / standard;',
                 'return MAX(fit, MIN(fill, fit * 4.0 / 3.0));'):
        check(line in header, f'442 math kept: {line}')
    dolphin = code((DOLPHIN_CLASSES / 'DolphinExternalDisplayLayout.h').read_text(encoding='utf-8'))
    check('#import <external_display/NeoExternalDisplayLayout.h>' in dolphin, 'the Dolphin header imports this policy as the pod publishes it')
    for call in ('return NeoExternalDisplayScale(screen, source, DOLExternalDisplayGlobalMode(mode));',
                 'return NeoExternalDisplayFrame(screen, source, DOLExternalDisplayGlobalMode(mode));',
                 'NeoExternalDisplayEffectiveMode(mode, NeoExternalContentGame)'):
        check(call in dolphin, f'Dolphin delegates: {call}')
    check('16.0 / 9.0' not in dolphin and '4.0 / 3.0' not in dolphin, 'single copy of the 442 arithmetic')
    # The layout test compares the policy and the delegating Dolphin header
    # with a frozen copy of the 442 arithmetic (revision a221ae0c), never the
    # Dolphin header with the policy it delegates to (that would be f(x) == f(x)).
    layout_test = code((ROOT / 'test/external_display_layout_test.mm').read_text(encoding='utf-8'))
    for line in ('const CGFloat widescreen = source.height * 16.0 / 9.0;', 'const CGFloat fit = MIN(heightScale, screen.width / widescreen);',
                 'const CGFloat standard = source.height * 4.0 / 3.0;', 'const CGFloat fill = screen.width / standard;',
                 'return MAX(fit, MIN(fill, fit * 4.0 / 3.0));', 'mode == Build442ModeOff) return 1;'):
        check(line in layout_test, f'frozen 442 copy in the layout test: {line}')
    check('static inline CGFloat Build442Scale(' in layout_test and 'static inline CGRect Build442Frame(' in layout_test, 'frozen copy functions')
    check('NeoExternalDisplayScale(screen, source, NeoExternalDisplayModeFit) == Build442Scale(screen, source, Build442ModeFit)' in layout_test
          and 'NeoExternalDisplayFrame(screen, source, NeoExternalDisplayModeFill), Build442Frame(screen, source, Build442ModeFill)' in layout_test,
          'the policy is compared with the frozen copy')
    check('DOLExternalDisplayScale(screen, source, DOLExternalDisplayModeFit) == Build442Scale(screen, source, Build442ModeFit)' in layout_test
          and 'DOLExternalDisplayFrame(screen, source, DOLExternalDisplayModeFill), Build442Frame(screen, source, Build442ModeFill)' in layout_test,
          'the Dolphin delegation is compared with the frozen copy')
    check(re.search(r'NeoExternalDisplay(?:Scale|Frame)\([^;]*?==\s*DOLExternalDisplay(?:Scale|Frame)\(', layout_test) is None
          and re.search(r'CGRectEqualToRect\(NeoExternalDisplayFrame\([^;]*?,\s*DOLExternalDisplayFrame\(', layout_test) is None,
          'no tautological comparison of the policy with the header that delegates to it')


def host_protocol_contracts() -> None:
    protocol = read('NeoExternalRenderHost.h')
    for token in ('@protocol NeoExternalRenderHost <NSObject>', 'UIView *renderView;', 'UIView *placeholderView;',
                  'BOOL fixedDrawable;', '@optional', '- (void)externalSurfaceDidChange:(CGSize)pointSize scale:(CGFloat)scale;',
                  '- (void)externalDisplayDidChange:(BOOL)active;'):
        check(token in protocol, token)


def coordinator_contracts() -> None:
    source = read('NeoExternalDisplayCoordinator.m')
    header = read('NeoExternalDisplayCoordinator.h')
    stripped = without_strings(code(source))
    for name in ('ExternalDisplayPlugin.m', 'NeoExternalDisplayCoordinator.m', 'NeoExternalDisplaySceneDelegate.m',
                 'NeoExternalDisplayMenuEngine.m', 'NeoExternalDisplayPreferences.m'):
        check('makeKeyAndVisible' not in without_strings(code(read(name))), f'{name}: the external window is never made key')
    check('window.hidden = NO;' in source and 'window.windowLevel = UIWindowLevelNormal;' in source, 'shown, normal level')
    check('NeoExternalDisplayStateChangedNotification = @"NeoStation.ExternalDisplayStateChanged"' in source, 'state notification name')
    # Build 442 guarantees: transform only, drawable and scale kept, index 0 on return.
    for token in ('autoResizeDrawable = NO', 'CGAffineTransformMakeScale(scale, scale)', 'insertSubview:render atIndex:0',
                  'render.contentScaleFactor = self.savedContentScale', 'render.autoresizingMask = self.savedAutoresizing',
                  'autoResizeDrawable = self.savedAutoResizeDrawable'):
        check(token in source, token)
    check('drawableSize' not in stripped, 'the coordinator never resizes a drawable itself; a non-fixed host does it from externalSurfaceDidChange')
    # Return before stop / before the window is released.
    disconnect = method_body(source, '- (void)disconnectWindow {')
    check(disconnect.index('[self returnRenderViewToPlaceholder];') < disconnect.index('self.window = nil;')
          and disconnect.index('[self returnRenderViewToPlaceholder];') < disconnect.index('window.hidden = YES;'),
          'the render view returns to the iPhone before the window is released')
    check(disconnect.index('[self detachMenuViewControllerInternal];') < disconnect.index('destroyExternalMenuEngineForReason:@"disconnect"'),
          'the menu controller leaves the window before its engine is destroyed')
    detach = method_body(source, '- (void)detachRenderHost:(id<NeoExternalRenderHost>)host {')
    check(detach.index('[self returnRenderViewToPlaceholder];') < detach.index('self.renderHost = nil;'), 'detach returns the view first')
    attach = method_body(source, '- (void)attachRenderHost:(id<NeoExternalRenderHost>)host {')
    check('[self detachRenderHost:self.renderHost]' in attach, 'a second host detaches the first (no double placement)')
    # The menu engine is created only when it is about to be shown: never
    # while a game holds the TV (an engine that exists is hidden, not released).
    apply = method_body(code(source), '- (void)applyState {')
    check('if (usable && menuOnTV && !gameShown && !self.menuSuppressed && self.menuViewController == nil && provider != nil) {' in apply,
          'the menu engine is not created while the game is on the TV')
    check(apply.index('const BOOL gameShown = self.renderHost != nil && self.renderPlaced;') < apply.index('externalMenuViewControllerCreatingIfNeeded'),
          'gameShown is known before the creation')
    check('const BOOL menuShown = usable && self.menuViewController != nil && !gameShown;' in apply, 'an existing menu stays hidden behind the game')
    # Observation set of the contract, plus the window notifications that
    # re-read the presentation chain for the iOS 27 accessory.
    for name in ('UIScreenModeDidChangeNotification', 'UIApplicationDidBecomeActiveNotification', 'NeoExternalDisplayChangedNotification',
                 'UIScreenDidConnectNotification', 'UIScreenDidDisconnectNotification',
                 'UIWindowDidBecomeKeyNotification', 'UIWindowDidBecomeHiddenNotification'):
        check(f'name:{name}' in source, f'observes {name}')
    window_changed = method_body(code(source), '- (void)windowDidChange:(NSNotification *)notification {')
    check('if (notification.object != nil && notification.object == self.window) return;' in window_changed,
          "the external window's own hidden/visible changes are not a presentation change")
    check('[self refresh];' in window_changed and 'if (!NSThread.isMainThread)' in window_changed, 'window notifications re-apply on the main thread')
    # Legacy fallback: one method, deprecated API nowhere else, 1.5 s timer, journaled.
    legacy = method_body(code(source), '- (void)activateLegacyIfNeeded {')
    outside = code(source).replace(legacy, '')
    for api in ('UIScreen.screens', 'UIScreen.mainScreen', 'window.screen ='):
        check(api in legacy, f'legacy path uses {api}')
        check(api not in outside, f'{api} only in activateLegacyIfNeeded')
    check('#pragma clang diagnostic ignored "-Wdeprecated-declarations"' in legacy, 'legacy path silences its deprecations')
    check('if (self.window != nil || self.sceneEverConnected) return;' in legacy, 'legacy only without any scene ever delivered')
    check('NSLog(@"display.external_legacy' in legacy, 'legacy journal line')
    check('kNeoExternalLegacyDelaySeconds = 1.5;' in source, '1.5 s delay')
    connect = method_body(source, '- (void)screenDidConnect:(NSNotification *)notification {')
    check('scheduledTimerWithTimeInterval:kNeoExternalLegacyDelaySeconds' in connect and 'repeats:NO' in connect, 'NSTimer on the main run loop')
    check('if (self.window != nil || self.sceneEverConnected) return;' in connect, 'no timer once a scene was delivered')
    check('if (!NSThread.isMainThread)' in connect, 'notification hopped to the main thread')
    scene_connect = method_body(source, '- (void)sceneDidConnect:(UIWindowScene *)scene {')
    check('[self.legacyTimer invalidate];' in scene_connect and 'self.sceneEverConnected = YES;' in scene_connect, 'a scene cancels the fallback')
    check('self.windowFactory(scene, scene.screen)' in scene_connect and '[[UIWindow alloc] initWithWindowScene:scene]' in scene_connect, 'scene window')
    check('NSLog(@"display.external_scene_connected' in scene_connect, 'scene journal line')
    # iOS 27 accessory, selectors only: the documented Objective-C factory
    # (+externalNonInteractiveSceneAccessoryWithConfiguration:) first, the
    # contract's spelling kept as a fallback; the UISceneAccessoryRegistration
    # returned by registerSceneAccessory: kept and handed back to
    # unregisterSceneAccessory:; one registration per presented controller,
    # released only once the controller left the presentation chain.
    accessory = source[source.index('@implementation NeoExternalDisplaySceneAccessory'):source.index('@end', source.index('@implementation NeoExternalDisplaySceneAccessory'))]
    for token in ('NSClassFromString(@"UISceneAccessory")',
                  '@"externalNonInteractiveSceneAccessoryWithConfiguration:"', '@"externalNonInteractiveWithSceneConfiguration:"',
                  'NSSelectorFromString(@"registerSceneAccessory:")', 'NSSelectorFromString(@"unregisterSceneAccessory:")',
                  'respondsToSelector:', 'objc_msgSend',
                  'UIWindowSceneSessionRoleExternalDisplayNonInteractive', 'return @"unavailable";', 'return @"registered";',
                  'return @"failed:', 'id registration = ((id (*)(id, SEL, id))objc_msgSend)(controller, registerSelector, accessory);',
                  'objc_msgSend)(controller, unregisterSelector, entry.registration);',
                  'if ([self entryForViewController:controller] != nil) return @"registered";',
                  'NeoExternalControllerIsLive(controller, chain)', '[kept addObject:entry];'):
        check(token in accessory, f'accessory: {token}')
    check(accessory.index('externalNonInteractiveSceneAccessoryWithConfiguration:') < accessory.index('externalNonInteractiveWithSceneConfiguration:'),
          'the documented factory selector is tried first')
    check(re.search(r'\bUISceneAccessory(?:Registration)?\s*\*', stripped) is None and '[UISceneAccessory ' not in stripped,
          'no compile-time use of the iOS 27 types (CI SDK is iOS 26)')
    check('NSLog(@"display.external_accessory:%@"' in source, 'accessory journal line')
    check('UIWindowSceneSessionRoleApplication' in source, 'the accessory targets the application scene')
    register = method_body(code(source), '- (void)registerAccessoryIncludingPresented:(BOOL)includePresented {')
    check(register.index('releaseRegistrationsOutside:chain]') < register.index('registerOnViewController:chain.firstObject]'),
          'dismissed controllers are released, then the root is registered')
    check('if (includePresented && chain.count > 1' in register and 'registerOnViewController:chain.lastObject]' in register,
          'the presented controller is registered only when a bridge attached')
    check('self.registerPresentedController = YES;' in attach, 'attachRenderHost: asks for the presented controller')
    check('registerPresentedController' not in method_body(code(source), '- (void)refresh {'),
          'a refresh never registers a menu presented over the game')
    for prefix in ('display.external_attached:', 'display.external_detached:'):
        check(f'NSLog(@"{prefix}' in source, prefix)
    check(source.count('NSAssert(NSThread.isMainThread') >= 10, 'public entry points assert the main thread')
    # Public surface of the contract.
    for token in ('+ (instancetype)shared;', '- (void)attachRenderHost:(id<NeoExternalRenderHost>)host;',
                  '- (void)detachRenderHost:(id<NeoExternalRenderHost>)host;', '- (void)suspendForUnsupportedEngine;',
                  '- (void)resumeAfterUnsupportedEngine;', '- (void)attachMenuViewController:(UIViewController *)controller;',
                  '- (void)detachMenuViewController;', '- (void)destroyMenuEngineForMemory;', '- (void)refresh;',
                  'void (^stateChanged)(void);', 'windowFactory)(UIWindowScene *_Nullable scene,', 'NSArray<UIScreen *> *(^legacyScreens)(void);',
                  '- (void)sceneDidConnect:(UIWindowScene *)scene;', '- (void)sceneDidDisconnect:(UIWindowScene *)scene;',
                  'NSString *accessoryStatus;', 'NSString *sceneRole;', 'CGSize screenPointSize;'):
        check(token in header, f'coordinator header: {token}')
    check('<Flutter/' not in header and '<Flutter/' not in source, 'the coordinator is UIKit-only (simulator harness without Flutter)')


def scene_delegate_contracts() -> None:
    header = read('NeoExternalDisplaySceneDelegate.h')
    source = read('NeoExternalDisplaySceneDelegate.m')
    check('@interface NeoExternalDisplaySceneDelegate : UIResponder <UIWindowSceneDelegate>' in header, 'delegate class')
    check('UIWindowSceneSessionRoleExternalDisplayNonInteractive' in source, 'role check')
    check('[coordinator sceneDidConnect:(UIWindowScene *)scene];' in source, 'forwards connect')
    check('sceneDidDisconnect:(UIWindowScene *)scene];' in source, 'forwards disconnect')
    check('makeKeyAndVisible' not in source, 'never key')


def preference_contracts() -> None:
    source = read('NeoExternalDisplayPreferences.m')
    for token in ('NeoExternalDisplayEnabledKey = @"NeoStation.ExternalDisplay.Enabled"',
                  'NeoExternalDisplayModeKey = @"NeoStation.ExternalDisplay.Mode"',
                  'NeoExternalDisplayMenuOnTVKey = @"NeoStation.ExternalDisplay.MenuOnTV"',
                  'NeoExternalDisplayLegacyDolphinModeKey = @"NeoStation.Dolphin.ExternalDisplay.Mode"',
                  'NeoExternalDisplayChangedNotification = @"NeoStation.ExternalDisplayChanged"',
                  'case 1: return NeoExternalDisplayModeFit;', 'case 2: return NeoExternalDisplayModeFill;',
                  '[self legacyDolphinMode] == 0) return NO;'):
        check(token in source, token)
    store = method_body(source, '+ (BOOL)storeNumber:(NSNumber *)value forKey:(NSString *)key {')
    check(store.index('objectForKey:key') < store.index('postNotificationName:NeoExternalDisplayChangedNotification'),
          'the notification follows a verified write')
    check('return NO;' in store, 'a write iOS did not keep is reported (SAVE_FAILED)')
    check(re.search(r'set\w+:[^\n]*NeoExternalDisplayLegacyDolphinModeKey', source) is None, 'the 442 key is read only, never rewritten')


def plugin_contracts() -> None:
    source = read('ExternalDisplayPlugin.m')
    for token in ('kNeoExternalDisplayChannel = @"neostation/external_display"',
                  'kNeoExternalDisplayEventsChannel = @"neostation/external_display/events"',
                  'FlutterEventChannel eventChannelWithName:kNeoExternalDisplayEventsChannel',
                  'name:NeoExternalDisplayStateChangedNotification', '@"BAD_ARGS"', '@"SAVE_FAILED"',
                  'coordinator.menuProvider = NeoExternalDisplayMenuEngine.shared;'):
        check(token in source, token)
    # Stream handler lifetime: one observation per listen (hot restart sends
    # two listens in a row), removed on cancel and on dealloc.
    listen = method_body(source, '- (FlutterError *)onListenWithArguments:(id)arguments eventSink:(FlutterEventSink)events {')
    check(listen.index('removeObserver:self name:NeoExternalDisplayStateChangedNotification') < listen.index('addObserver:self'),
          'a second listen never doubles the observation')
    check('removeObserver:self' in method_body(source, '- (FlutterError *)onCancelWithArguments:(id)arguments {'), 'cancel removes the observation')
    check('removeObserver:self' in method_body(source, '- (void)dealloc {'), 'dealloc removes the observation')
    for method in ('getState', 'setEnabled', 'setMode', 'setMenuOnTV', 'configureMenuEngine', 'pushMenuState'):
        check(f'isEqualToString:@"{method}"' in source, f'method {method}')
    set_mode = source.split('isEqualToString:@"setMode"', 1)[1].split('isEqualToString:@"setMenuOnTV"', 1)[0]
    check('NeoExternalDisplayModeOriginal' in set_mode and 'NeoExternalBadArguments' in set_mode, 'setMode refuses out of 0..3')
    check('storeMode:' in set_mode and 'NeoExternalSaveFailed' in set_mode, 'setMode reports SAVE_FAILED')
    configure = source.split('isEqualToString:@"configureMenuEngine"', 1)[1].split('isEqualToString:@"pushMenuState"', 1)[0]
    check('configureWithEntrypoint:entrypoint libraryURI:libraryUri' in configure, 'configureMenuEngine stores the pair')
    push = source.split('isEqualToString:@"pushMenuState"', 1)[1]
    check('pushMenuState:json' in push and 'result(@YES);' in push, 'pushMenuState relays and answers true')
    # KartPad (§ 8 bis): its pinned bridge cannot call the coordinator, so
    # Flutter asks for the suspension around the native session.
    for method in ('suspendForUnsupportedEngine', 'resumeAfterUnsupportedEngine'):
        branch = source.split(f'isEqualToString:@"{method}"', 1)[1].split('return;', 1)[0]
        check(f'[coordinator {method}];' in branch and 'result(@YES);' in branch, f'{method} reaches the coordinator')
    check(source.index('isEqualToString:@"resumeAfterUnsupportedEngine"') < source.index('result(FlutterMethodNotImplemented);'),
          'the two coordinator calls are answered before the fallback')
    header = read('ExternalDisplayPlugin.h')
    check('@interface ExternalDisplayPlugin : NSObject <FlutterPlugin>' in header, 'plugin class')
    check('pluginClass: ExternalDisplayPlugin' in (PACKAGE / 'pubspec.yaml').read_text(encoding='utf-8'), 'pubspec plugin class')


def menu_engine_contracts() -> None:
    source = read('NeoExternalDisplayMenuEngine.m')
    for token in ('kNeoExternalMenuEngineGroupName = @"neostation-external"',
                  'kNeoExternalMenuChannelName = @"neostation/external_display/menu"',
                  '[[FlutterEngineGroup alloc] initWithName:kNeoExternalMenuEngineGroupName project:nil]',
                  'makeEngineWithEntrypoint:self.entrypoint libraryURI:self.libraryURI',
                  'codec:FlutterStringCodec.sharedInstance', 'NSClassFromString(name)',
                  'respondsToSelector:@selector(registerWithRegistrar:)', '[engine destroyContext];',
                  'engine.viewController = nil;', 'if (!self.configured) return nil;'):
        check(token in source, token)
    for name in sorted(p.name for p in CLASSES.iterdir()):
        check('GeneratedPluginRegistrant' not in code(read(name)), f'{name}: never GeneratedPluginRegistrant')
    destroy = method_body(source, '- (void)destroyExternalMenuEngineForReason:(NSString *)reason {')
    check(destroy.index('removeFromSuperview') < destroy.index('destroyContext'), 'the controller leaves the window before the engine dies')


def podspec_contracts() -> None:
    podspec = (PACKAGE / 'ios/external_display.podspec').read_text(encoding='utf-8')
    check('static_framework' not in podspec, 'dynamic framework (shared by the bridges)')
    for token in ("s.dependency 'Flutter'", "s.platform = :ios, '17.4'", "s.ios.deployment_target = '17.4'",
                  "s.frameworks = 'UIKit', 'Foundation', 'QuartzCore', 'MetalKit'", "s.source_files     = 'Classes/**/*.{h,m}'"):
        check(token in podspec, token)
    public = podspec.split('s.public_header_files', 1)[1].split("s.dependency", 1)[0]
    # The five headers of the contract (§ 3) plus the header-only label
    # catalog: the libretro bridge imports it as <external_display/…> for its
    # status line (§ 5), which the framework only resolves for a published
    # header (test/libretro_external_surface_test.py). Retired assertion: it
    # no longer "stays private".
    for name in ('ExternalDisplayPlugin.h', 'NeoExternalDisplayLayout.h', 'NeoExternalRenderHost.h',
                 'NeoExternalDisplayCoordinator.h', 'NeoExternalDisplayPreferences.h', 'NeoExternalDisplayLabels.h'):
        check(f"'Classes/{name}'" in public, f'public header {name}')
    for name in ('NeoExternalDisplayMenuEngine.h', 'NeoExternalDisplaySceneDelegate.h'):
        check(name not in public, f'{name} stays private')
    # Header-only: nothing of the catalog is exported by the framework, every
    # importing image keeps its own copy.
    check(re.search(r'^static NSString \*NeoExternalDisplayText\(', read('NeoExternalDisplayLabels.h'), re.M) is not None,
          'the label catalog is a static function of its header')
    # With use_frameworks! only the public headers exist as
    # <external_display/Name.h>: every header a bridge imports that way must
    # be published, or the cold Xcode build of that bridge fails.
    imported = set()
    for path in (ROOT / 'packages').glob('*/ios/Classes/**/*'):
        if path.suffix in {'.h', '.m', '.mm'} and path.is_file() and 'external_display' not in path.parts:
            imported.update(re.findall(r'<external_display/(\w+\.h)>', path.read_text(encoding='utf-8', errors='ignore')))
    check(bool(imported), 'at least one bridge imports the pod')
    for name in sorted(imported):
        check(f"'Classes/{name}'" in public, f'{name} is imported by a bridge as <external_display/{name}> and must be public')
        check((CLASSES / name).is_file(), f'{name} exists')


def execute_policy() -> None:
    if platform.system() != 'Darwin' or not shutil.which('clang++'):
        print('SKIP: external display placement execution requires macOS Foundation/CoreGraphics; source contracts checked')
        return
    with tempfile.TemporaryDirectory() as folder:
        binary = Path(folder) / 'external-display-layout'
        subprocess.run(['clang++', '-std=c++20', '-fobjc-arc', '-I' + str(CLASSES), '-I' + str(DOLPHIN_CLASSES),
                        str(ROOT / 'test/external_display_layout_test.mm'), '-framework', 'Foundation',
                        '-framework', 'CoreGraphics', '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    layout_contracts()
    host_protocol_contracts()
    coordinator_contracts()
    scene_delegate_contracts()
    preference_contracts()
    plugin_contracts()
    menu_engine_contracts()
    podspec_contracts()
    print('external_display source contracts: OK', flush=True)
    execute_policy()

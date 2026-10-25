#!/usr/bin/env python3
"""Source contracts of the external_display plugin, plus the placement policy
executed on macOS.

The contracts (docs/external-display-universal.md § 3 and § 8) are checked on
any OS: pure placement header holding the Build 442 arithmetic, Dolphin
header delegating to it, no makeKeyAndVisible on the external window,
render view returned before any stop or window release, the set of
connected external scenes (a second scene stands by, the shown one's
disconnection adopts a remaining one, UIApplication.connectedScenes
rescanned at every refresh), legacy fallback isolated in
activateLegacyIfNeeded and refused when its window is in no scene of the
screen, iOS 27 scene accessory by selectors only for a binary built with
SDK 27 or later and never beside an automatic scene (root and render-host
owner registrations, isEnabled, released once dismissed), the TV showing
nothing of NeoStation's own outside a game (Build 449: no menu engine is
created by the coordinator, the window leaves its scene so that iOS mirrors
the iPhone, and comes back to it before a game's render view moves in), the
menu engine still started with the language and theme as entrypoint
arguments by its own path, passes re-run for calls made during one,
journal prefixes, channel and preference names, dynamic podspec publishing
every header a bridge imports. On macOS the production NeoExternalDisplayLayout.h is then
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
                     'NeoExternalDisplayModeCrops', 'NeoExternalDisplayVersionMajor', 'NeoExternalDisplaySDKMajorVersion'):
        check(re.search(r'static inline \w+ ' + function + r'\(', header) is not None, f'{function} is a static inline function')
    # A host that draws at the TV's resolution (libretro, fixedDrawable NO)
    # gets the whole screen in every mode and places each game at its own
    # aspect (review of 12 October 2026, M3). Retired contract: the surface
    # no longer follows the Fit/Fill/Original frame of the phone's format
    # (a portrait phone gave a 498 x 1080 pillar); the formats apply to the
    # fixed drawables, whose view is only scaled.
    surface = code(header)[code(header).index('static inline CGSize NeoExternalDisplaySurfaceSize('):]
    surface = surface[:surface.index('\n}\n')]
    check('return screen;' in surface and 'NeoExternalDisplayScale(' not in surface and 'NeoExternalDisplayFrame(' not in surface,
          'the surface of a non-fixed host is the whole screen in every mode')
    check('if (!NeoExternalDisplayUsableSize(screen) || !NeoExternalDisplayUsableSize(source)) return CGSizeZero;' in surface,
          'an unusable screen or iPhone layout gives no surface')
    # iOS 27 regime: only a binary built with SDK 27 or later (Info.plist of
    # the main bundle); missing or unparsable is not active.
    check('static const NSInteger NeoExternalDisplayAccessorySDKMajor = 27;' in header, 'the accessory regime starts with SDK 27')
    sdk = code(header)[code(header).index('static inline NSInteger NeoExternalDisplaySDKMajorVersion('):]
    sdk = sdk[sdk.index('{'):sdk.index('\n}\n')]
    check(sdk.index('NeoExternalDisplayVersionMajor(platformVersion)') < sdk.index('substringFromIndex:letters'),
          'DTPlatformVersion first, then the version of DTSDKName')
    check('if (letters == 0 || letters == sdkName.length) return 0;' in sdk, 'an SDK name without letters or without version is unparsable')
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
    # A non-fixed host (libretro): the surface is recomputed at every pass
    # from the iPhone layout its placeholder has now (a rotation), and size
    # and scale are compared together (a mode change of the TV can change
    # the scale alone: m6).
    place = method_body(code(source), '- (void)placeRenderView {')
    check('CGSize source = host.placeholderView.bounds.size;' in place
          and 'if (!NeoExternalDisplayUsableSize(source)) source = self.savedBounds.size;' in place,
          'the surface follows the current iPhone layout, the bounds of the move only as a fallback')
    check('CGSize surface = NeoExternalDisplaySurfaceSize(screen, source, mode);' in place, 'the policy of the layout header')
    check('if (CGSizeEqualToSize(surface, self.lastSurface) && scale == self.lastSurfaceScale) return;' in place
          and 'self.lastSurfaceScale = scale;' in place, 'size and scale compared together')
    check(place.index('if (host.fixedDrawable) {') < place.index('NeoExternalDisplaySurfaceSize('), 'the fixed drawables keep the 442 scaling')
    scale = method_body(code(source), '- (CGFloat)currentScreenScale {')
    check('scale = self.screenScaleReader();' in scale and 'UIScreen *screen = self.scene != nil ? self.scene.screen : self.legacyScreen;' in scale
          and 'scale = screen.scale;' in scale and 'return isfinite(scale) && scale > 0 ? scale : self.screenScale;' in scale,
          "the external screen's scale is re-read (seam first), the last one kept when the screen does not tell")
    # Return before stop / before the window is released (every release
    # goes through releaseWindowKeepingMenuEngine:, the disconnection and
    # the adoption of another scene alike).
    release = method_body(source, '- (void)releaseWindowKeepingMenuEngine:(BOOL)keepMenuEngine {')
    check(release.index('[self returnRenderViewToPlaceholder];') < release.index('self.window = nil;')
          and release.index('[self returnRenderViewToPlaceholder];') < release.index('window.hidden = YES;'),
          'the render view returns to the iPhone before the window is released')
    check(release.index('[self detachMenuViewControllerInternal];') < release.index('destroyExternalMenuEngineForReason:@"disconnect"'),
          'the menu controller leaves the window before its engine is destroyed')
    check('if (!keepMenuEngine) [self.menuProvider destroyExternalMenuEngineForReason:@"disconnect"];' in release,
          'the menu engine survives only an adoption')
    check(release.index('window.hidden = YES;') < release.index('self.window = nil;'),
          "the window is hidden while still the coordinator's (its own UIWindowDidBecomeHidden is filtered)")
    disconnect = method_body(source, '- (void)disconnectWindow {')
    check(disconnect.index('[self releaseWindowKeepingMenuEngine:NO];') < disconnect.index('[self applyState];'),
          'a disconnection releases the window and its menu engine, then re-applies')
    detach = method_body(source, '- (void)detachRenderHost:(id<NeoExternalRenderHost>)host {')
    check(detach.index('[self returnRenderViewToPlaceholder];') < detach.index('self.renderHost = nil;'), 'detach returns the view first')
    attach = method_body(source, '- (void)attachRenderHost:(id<NeoExternalRenderHost>)host {')
    check('[self detachRenderHost:self.renderHost]' in attach, 'a second host detaches the first (no double placement)')
    # Build 449: outside a game the TV shows nothing of NeoStation's own and
    # iOS mirrors the iPhone, so the TV shows the NeoStation interface
    # itself. Retired contracts (Build 447/448): "the menu engine is
    # created only when it is about to be shown", "an existing menu stays
    # hidden behind the game", "the provider is told at every pass whether
    # the menu shows": the coordinator put the second engine's TV view (the
    # SecondaryScreen of Android handhelds, the selected console's logo) on
    # the TV instead of the interface.
    apply_pass = method_body(code(source), '- (void)applyStatePass {')
    implementation = code(source)[code(source).index('@implementation NeoExternalDisplayCoordinator\n'):]
    check('externalMenuViewControllerCreatingIfNeeded' not in implementation,
          'the coordinator never creates the menu engine')
    check('placeMenuViewControllerShown' not in stripped and 'externalMenuSetVisible:' not in apply_pass,
          'no menu is ever placed in the external window')
    menu_on_tv = method_body(code(source), '- (BOOL)menuOnTV {')
    check('return NO;' in menu_on_tv and 'NeoExternalDisplayPreferences' not in menu_on_tv,
          'menuOnTV is NO: the stored preference of Build 447 is no longer read')
    check('self.content = gameShown ? NeoExternalContentGame : NeoExternalContentNone;' in apply_pass,
          'the content is the game or nothing')
    check('[provider destroyExternalMenuEngineForReason:enabled ? @"menu_off" : @"disabled"];' in apply_pass
          and apply_pass.index('[self detachMenuViewControllerInternal];') < apply_pass.index('destroyExternalMenuEngineForReason:'),
          'a menu controller or engine an earlier state left is released, controller first')
    check('const BOOL shown = usable && gameShown;' in apply_pass and 'if (window != nil) window.hidden = !shown;' in apply_pass
          and 'if (!shown) [self placeWindowInScene:NO];' in apply_pass
          and apply_pass.index('window.hidden = !shown;') < apply_pass.index('[self placeWindowInScene:NO];'),
          'nothing to show: the window is hidden, then leaves its scene (iOS mirrors the iPhone)')
    check('if (usable && self.renderHost != nil) [self placeWindowInScene:YES];' in apply_pass
          and apply_pass.index('[self placeWindowInScene:YES];') < apply_pass.index('[self moveRenderViewToWindow];'),
          'a game going to the TV brings the window back into its scene before its render view moves in')
    # Apple: a window of the app in the external scene ends the mirroring,
    # taking it out of the scene (windowScene = nil) brings the mirroring
    # back; hiding it does not (Apple Developer Forums thread 766398).
    place_scene = method_body(code(source), '- (void)placeWindowInScene:(BOOL)inScene {')
    check("if (window == nil || scene == nil || ![self.sceneRole isEqualToString:kNeoExternalRoleScene]) return;" in place_scene,
          'only a window of the scene role moves in and out of its scene (legacy windows and test seams untouched)')
    leave = place_scene[place_scene.index('if (self.windowLeftScene || window.windowScene != scene) return;'):]
    check('window.windowScene = nil;' in leave and 'self.windowLeftScene = YES;' in leave
          and leave.index('[self giveWindow:nil toDelegateOfScene:scene];') < leave.index('window.windowScene = nil;'),
          'outside a game the window leaves its scene, its delegate no longer holds it')
    back = place_scene[place_scene.index('if (inScene) {'):place_scene.index('if (self.windowLeftScene || window.windowScene != scene) return;')]
    check('if (self.windowFollowsScene && NeoExternalDisplayUsableSize(bounds.size)) {' in back
          and back.index('window.windowScene = scene;') < back.index('window.frame = bounds;'),
          "back in its scene, the coordinator's own window takes the size the scene has now (a mode change of the TV while mirrored)")
    check('window.frame = self.frameBeforeLeavingScene;' in back and 'self.frameBeforeLeavingScene = window.frame;' in leave,
          'a window the factory seam built gets back its own frame (the test host stands the iPhone scene in for the TV)')
    show_window = method_body(code(source), '- (void)showWindowInScene:(UIWindowScene *)scene {')
    check('self.windowFollowsScene = window == nil;' in show_window
          and show_window.index('self.windowFollowsScene = window == nil;') < show_window.index('[[UIWindow alloc] initWithWindowScene:scene]'),
          'only a window built by the coordinator follows the scene bounds')
    check('self.windowFollowsScene = NO;' in release and 'self.frameBeforeLeavingScene = CGRectZero;' in release,
          'a released window forgets its scene geometry')
    check('if (!self.windowLeftScene) return;' in back and 'window.windowScene = scene;' in back
          and '[self giveWindow:window toDelegateOfScene:scene];' in back and 'self.windowLeftScene = NO;' in back,
          'only a window this coordinator took out goes back, to the same scene, and its delegate holds it again')
    check('NSLog(@"display.external_mirroring' in place_scene and 'NSLog(@"display.external_window_back_in_scene"' in place_scene,
          'journal lines of the mirroring and of the return')
    check('self.windowLeftScene = NO;' in release, 'a released window forgets that it left its scene')
    check(apply_pass[len('- (void)applyStatePass {'):].lstrip().startswith('self.screenScale = [self currentScreenScale];'),
          "every pass starts by re-reading the external screen's scale")
    check(apply_pass.index('[self registerAccessory];') > apply_pass.index('self.content ='), 'the accessory follows the content of the pass')
    # A call made during a pass (a host's or the provider's callback) asks
    # for one more pass instead of being lost (m5); bounded.
    apply = method_body(code(source), '- (void)applyState {')
    check(re.search(r'\{\s*if \(self\.applying\) \{\s*self\.needsReapply = YES;\s*return;\s*\}', apply) is not None,
          'a re-entrant applyState marks the pass to be run again')
    check('do {' in apply and '[self applyStatePass];' in apply
          and '} while (self.needsReapply && passes < kNeoExternalMaxApplyPasses);' in apply, 'passes re-run while asked, bounded')
    check(apply.index('self.needsReapply = NO;') < apply.index('[self applyStatePass];'), 'the flag is cleared before each pass')
    check(apply.index('} while (') < apply.index('self.applying = NO;') < apply.index('[self notifyIfChanged];'),
          'the state is reported once, after the last pass')
    check('kNeoExternalMaxApplyPasses = 4;' in source, 'at most four passes in a row')
    refresh = method_body(code(source), '- (void)refresh {')
    check('self.needsRescan = YES;' in refresh and 'self.needsReapply = YES;' in refresh, 'a refresh during a pass is kept for its end')
    check(refresh.index('[self rescanExternalScenes];') < refresh.index('[self applyState];'), 'a refresh rescans the connected scenes first')
    check('if (self.needsRescan) {' in apply and apply.index('[self rescanExternalScenes];') < apply.index('[self applyStatePass];'),
          'the rescan asked during a pass runs between passes')
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
    # Legacy fallback: one method, deprecated API nowhere else, 1.5 s timer,
    # journaled; a window that is in no scene of the screen is never used
    # (M2: in a scene-based app it would not be displayed and the iPhone
    # would lose its picture), a connected external scene of the screen is
    # adopted instead.
    legacy = method_body(code(source), '- (void)activateLegacyIfNeeded {')
    outside = code(source).replace(legacy, '')
    for api in ('UIScreen.screens', 'UIScreen.mainScreen', 'window.screen ='):
        check(api in legacy, f'legacy path uses {api}')
        check(api not in outside, f'{api} only in activateLegacyIfNeeded')
    check('#pragma clang diagnostic ignored "-Wdeprecated-declarations"' in legacy, 'legacy path silences its deprecations')
    check('if (self.window != nil || self.sceneEverConnected) return;' in legacy, 'legacy only without any scene ever delivered')
    check('NSLog(@"display.external_legacy' in legacy, 'legacy journal line')
    check('if (screen != nil) existing = NeoExternalConnectedSceneOnScreen(screen);' in legacy and '[self sceneDidConnect:existing];' in legacy,
          'a connected external scene of the screen is adopted rather than a window without scene')
    refusal = legacy[legacy.index('if (windowScene == nil || windowScene.screen != screen) {'):]
    refusal = refusal[:refusal.index('return;') + len('return;')]
    check('UIWindowScene *windowScene = window.windowScene;' in legacy and 'NSLog(@"display.legacy_unavailable' in refusal
          and 'window.hidden = YES;' in refusal and 'connectWindow' not in refusal and 'self.legacyScreen' not in refusal,
          'a window in no scene of the screen is refused: logged, hidden, nothing moves, iOS keeps mirroring')
    check(legacy.index('if (windowScene == nil || windowScene.screen != screen) {') < legacy.index('self.legacyScreen = screen;')
          < legacy.index('[self connectWindow:window role:kNeoExternalRoleLegacy];'), 'only a window in a scene of that screen is connected')
    check('kNeoExternalLegacyDelaySeconds = 1.5;' in source, '1.5 s delay')
    connect = method_body(source, '- (void)screenDidConnect:(NSNotification *)notification {')
    check('scheduledTimerWithTimeInterval:kNeoExternalLegacyDelaySeconds' in connect and 'repeats:NO' in connect, 'NSTimer on the main run loop')
    check('if (self.window != nil || self.sceneEverConnected) return;' in connect, 'no timer once a scene was delivered')
    check('if (!NSThread.isMainThread)' in connect, 'notification hopped to the main thread')
    # The connected external scenes are a set (M1): a second scene never
    # replaces the shown one's window (it stands by), the shown one's
    # disconnection adopts a remaining scene, and a scene the system offered
    # while no registration of ours was enabled is an automatic one.
    scene_connect = method_body(code(source), '- (void)sceneDidConnect:(UIWindowScene *)scene {')
    check('[self.legacyTimer invalidate];' in scene_connect and 'self.sceneEverConnected = YES;' in scene_connect, 'a scene cancels the fallback')
    check('if (![self.connectedExternalScenes containsObject:scene]) {' in scene_connect
          and '[self.connectedExternalScenes addObject:scene];' in scene_connect, 'every connected scene is tracked once')
    check('if (![NeoExternalDisplaySceneAccessory hasEnabledRegistration]) [self.automaticScenes addObject:scene];' in scene_connect,
          'a scene nobody registered for is an automatic one')
    check('NSLog(@"display.external_scene_standby' in scene_connect, 'standby journal line')
    check('disconnectWindow' not in scene_connect and 'releaseWindowKeepingMenuEngine:NO' not in scene_connect,
          "a connecting scene never drops the shown scene's window, menu engine or game")
    check('if (self.window != nil && [self.sceneRole isEqualToString:kNeoExternalRoleLegacy]) {' in scene_connect
          and '[self releaseWindowKeepingMenuEngine:YES];' in scene_connect, 'a legacy window gives way to a scene')
    check(scene_connect.rstrip().endswith('[self showWindowInScene:scene];\n}') or scene_connect.rstrip().endswith('[self showWindowInScene:scene];'),
          'the window is created last, only when no other scene shows it')
    show = method_body(source, '- (void)showWindowInScene:(UIWindowScene *)scene {')
    check('self.windowFactory(scene, scene.screen)' in show and '[[UIWindow alloc] initWithWindowScene:scene]' in show, 'scene window')
    check('NSLog(@"display.external_scene_connected' in show, 'scene journal line')
    check(show.index('self.connectingScene = scene;') < show.index('[self connectWindow:window role:kNeoExternalRoleScene];')
          < show.index('self.connectingScene = nil;'), 'the scene being connected is never dropped by a rescan')
    check('[self giveWindow:window toDelegateOfScene:scene];' in show, "the scene's delegate keeps the window of its own scene")
    give = method_body(code(source), '- (void)giveWindow:(UIWindow *_Nullable)window toDelegateOfScene:(UIWindowScene *_Nullable)scene {')
    check('if (delegate == nil || ours == Nil || ![delegate isKindOfClass:ours]) return;' in give, "only NeoStation's own scene delegate")
    scene_disconnect = method_body(code(source), '- (void)sceneDidDisconnect:(UIWindowScene *)scene {')
    check('[self.connectedExternalScenes removeObject:scene];' in scene_disconnect and '[self.automaticScenes removeObject:scene];' in scene_disconnect,
          'a disconnected scene leaves the set')
    check(scene_disconnect.index('if (self.window == nil || self.scene != scene || ![self.sceneRole isEqualToString:kNeoExternalRoleScene]) {')
          < scene_disconnect.index('UIWindowScene *next = [self adoptableExternalScene];'),
          "a standing-by scene's disconnection keeps the shown window")
    check(scene_disconnect.index('if (next == nil) {') < scene_disconnect.index('[self disconnectWindow];'), 'the last scene disconnects the window')
    check(scene_disconnect.index('[self releaseWindowKeepingMenuEngine:YES];') < scene_disconnect.index('[self showWindowInScene:next];')
          and 'NSLog(@"display.external_scene_adopted' in scene_disconnect, 'a remaining scene is adopted, the menu engine kept')
    adoptable = method_body(code(source), '- (UIWindowScene *_Nullable)adoptableExternalScene {')
    check('self.connectedExternalScenes.reverseObjectEnumerator' in adoptable and 'UISceneActivationStateUnattached' in adoptable,
          'the most recent scene still attached')
    rescan = method_body(code(source), '- (void)rescanExternalScenes {')
    check('UIApplication.sharedApplication.connectedScenes' in rescan and 'UIWindowSceneSessionRoleExternalDisplayNonInteractive' in rescan,
          "UIKit's own list of external scenes is the reference")
    check('if (tracked == self.connectingScene || [connected containsObject:tracked]) continue;' in rescan
          and '[self sceneDidDisconnect:tracked];' in rescan, 'a tracked scene UIKit no longer lists is a disconnection')
    check('[self sceneDidConnect:(UIWindowScene *)candidate];' in rescan
          and 'if (delegate != nil && (ours == Nil || ![delegate isKindOfClass:ours])) continue;' in rescan,
          "an external scene nobody reported is adopted, never another delegate's")
    # iOS 27 accessory, selectors only: the documented Objective-C factory
    # (+externalNonInteractiveSceneAccessoryWithConfiguration:) first, the
    # contract's spelling kept as a fallback; the UISceneAccessoryRegistration
    # returned by registerSceneAccessory: kept and handed back to
    # unregisterSceneAccessory:; one registration per controller, enabled
    # only while it has something to show (isEnabled through setEnabled:, an
    # unregistration when the registration has no setter), released once the
    # controller left the presentation chain.
    accessory = source[source.index('@implementation NeoExternalDisplaySceneAccessory'):source.index('@end', source.index('@implementation NeoExternalDisplaySceneAccessory'))]
    for token in ('NSClassFromString(@"UISceneAccessory")',
                  '@"externalNonInteractiveSceneAccessoryWithConfiguration:"', '@"externalNonInteractiveWithSceneConfiguration:"',
                  'NSSelectorFromString(@"registerSceneAccessory:")', 'NSSelectorFromString(@"unregisterSceneAccessory:")',
                  'respondsToSelector:', 'objc_msgSend',
                  'UIWindowSceneSessionRoleExternalDisplayNonInteractive', 'return @"unavailable";', 'return @"registered";',
                  'return @"failed:', 'id registration = ((id (*)(id, SEL, id))objc_msgSend)(controller, registerSelector, accessory);',
                  'objc_msgSend)(controller, unregisterSelector, entry.registration);',
                  'NeoExternalControllerIsLive(controller, chain)', '[kept addObject:entry];',
                  'NSSelectorFromString(@"setEnabled:")', '((void (*)(id, SEL, BOOL))objc_msgSend)(registration, setter, enabled);'):
        check(token in accessory, f'accessory: {token}')
    check(accessory.index('externalNonInteractiveSceneAccessoryWithConfiguration:') < accessory.index('externalNonInteractiveWithSceneConfiguration:'),
          'the documented factory selector is tried first')
    # Retired contract: "an existing registration answers registered"; it is
    # now enabled or disabled in place (isEnabled), still never registered a
    # second time.
    register_on = method_body(code(source), '+ (NSString *)registerOnViewController:(UIViewController *_Nullable)controller enabled:(BOOL)enabled {')
    existing = register_on[register_on.index('if (existing != nil) {'):register_on.index('if (!enabled) return @"disabled";', register_on.index('if (existing != nil) {') + 1)]
    check('NeoExternalAccessoryRegistration *existing = [self entryForViewController:controller];' in register_on
          and 'return existing.enabled ? @"registered" : @"disabled";' in existing and 'registerSelector' not in existing
          and 'objc_msgSend' not in existing, 'a controller keeps its one registration, enabled or disabled in place')
    check(register_on.index('if (!enabled) return @"disabled";') < register_on.index('id accessory = '),
          'no registration is made only to be turned off')
    disable = method_body(code(source), '+ (BOOL)disableEntry:(NeoExternalAccessoryRegistration *)entry {')
    check(disable.index('[self setRegistration:entry.registration enabled:NO]') < disable.index('[self unregisterEntry:entry];')
          and '[gNeoExternalRegistrations removeObject:entry];' in disable, 'isEnabled first, an unregistration without the setter')
    check(re.search(r'\bUISceneAccessory(?:Registration)?\s*\*', stripped) is None and '[UISceneAccessory ' not in stripped,
          'no compile-time use of the iOS 27 types (CI SDK is iOS 26)')
    check('NSLog(@"display.external_accessory:%@"' in source, 'accessory journal line')
    check('UIWindowSceneSessionRoleApplication' in source, 'the accessory targets the application scene')
    # The regime (M1, m10): only for a binary built with SDK 27 or later and
    # never while a scene the system offered by itself is connected; then a
    # registration on the application root (enabled while there is
    # something to show: since Build 449 a game on the TV only, retired
    # "or the menu on the TV") and one on the presented controller that owns the
    # attached render host (found from its placeholder view), never the
    # topmost controller as such, which can be a menu presented over the
    # game. Retired contract: "the presented controller (chain.lastObject)
    # is registered when a bridge attached" (registerPresentedController).
    register = method_body(code(source), '- (void)registerAccessory {')
    check(register.index('NSClassFromString(@"UISceneAccessory") == Nil') < register.index('[self buildSDKMajor] < NeoExternalDisplayAccessorySDKMajor')
          < register.index('self.automaticScenes.count > 0') < register.index('NeoExternalApplicationPresentationChain()'),
          'class, then build SDK, then automatic scene, before any registration')
    check(register.count('[NeoExternalDisplaySceneAccessory releaseAllRegistrations];') == 2
          and 'status = @"inactive:sdk";' in register and 'status = @"inactive:automatic_scene";' in register,
          'an inactive regime leaves no registration behind')
    check(register.index('releaseRegistrationsOutside:chain];') < register.index('registerOnViewController:root'),
          'dismissed controllers are released, then the root is registered')
    check('UIViewController *owner = [self presentedOwnerOfRenderHostInChain:chain];' in register and 'if (owner == root) owner = nil;' in register,
          'the second registration belongs to the controller owning the render host')
    check('chain.lastObject' not in register and 'registerPresentedController' not in stripped,
          'never the topmost controller as such (a menu presented over the game)')
    check(register.index('[NeoExternalDisplaySceneAccessory disableRegistrationsExcept:kept];') < register.index('registerOnViewController:root'),
          'a controller that no longer owns the host shows nothing')
    check('const BOOL usable = self.enabled && !self.suspended;' in register
          and 'enabled:usable && self.renderHost != nil]' in register
          and 'registerOnViewController:owner enabled:usable]' in register,
          'enabled only while the output is on, not suspended and has something to show')
    owner = method_body(code(source), '- (UIViewController *_Nullable)presentedOwnerOfRenderHostInChain:(NSArray<UIViewController *> *)chain {')
    check('NeoExternalOwningController(host.placeholderView)' in owner and 'node = node.parentViewController;' in owner
          and 'if ([chain containsObject:node]) return node;' in owner, "the owner is found from the host's placeholder view")
    sdk = method_body(code(source), '- (NSInteger)buildSDKMajor {')
    check('if (self.buildSDKMajorVersion != nil) return self.buildSDKMajorVersion();' in sdk
          and 'NSBundle.mainBundle.infoDictionary' in sdk and '@"DTPlatformVersion"' in sdk and '@"DTSDKName"' in sdk
          and 'NeoExternalDisplaySDKMajorVersion(' in sdk, 'the build SDK comes from the main bundle (test seam first)')
    for prefix in ('display.external_attached:', 'display.external_detached:'):
        check(f'NSLog(@"{prefix}' in source, prefix)
    check(source.count('NSAssert(NSThread.isMainThread') >= 10, 'public entry points assert the main thread')
    check('@"suspended" : @(self.suspended),' in source, 'the state reports the suspension (m2)')
    # Public surface of the contract.
    for token in ('+ (instancetype)shared;', '- (void)attachRenderHost:(id<NeoExternalRenderHost>)host;',
                  '- (void)detachRenderHost:(id<NeoExternalRenderHost>)host;', '- (void)suspendForUnsupportedEngine;',
                  '- (void)resumeAfterUnsupportedEngine;', '- (void)attachMenuViewController:(UIViewController *)controller;',
                  '- (void)detachMenuViewController;', '- (void)destroyMenuEngineForMemory;', '- (void)refresh;',
                  'void (^stateChanged)(void);', 'windowFactory)(UIWindowScene *_Nullable scene,', 'NSArray<UIScreen *> *(^legacyScreens)(void);',
                  '- (void)sceneDidConnect:(UIWindowScene *)scene;', '- (void)sceneDidDisconnect:(UIWindowScene *)scene;',
                  'NSString *accessoryStatus;', 'NSString *sceneRole;', 'CGSize screenPointSize;',
                  'NSArray<UIWindowScene *> *externalScenes;', 'NSInteger (^buildSDKMajorVersion)(void);',
                  'CGFloat (^screenScaleReader)(void);', 'BOOL suspended;', 'CGFloat screenScale;'):
        check(token in header, f'coordinator header: {token}')
    protocol = header[header.index('@protocol NeoExternalMenuProvider <NSObject>'):header.index('@end')]
    check(protocol.index('@optional') < protocol.index('- (void)externalMenuSetVisible:(BOOL)visible;'),
          'the visibility callback is optional (the simulator providers do not implement it)')
    check('<Flutter/' not in header and '<Flutter/' not in source, 'the coordinator is UIKit-only (simulator harness without Flutter)')


def scene_delegate_contracts() -> None:
    header = read('NeoExternalDisplaySceneDelegate.h')
    source = read('NeoExternalDisplaySceneDelegate.m')
    check('@interface NeoExternalDisplaySceneDelegate : UIResponder <UIWindowSceneDelegate>' in header, 'delegate class')
    check('UIWindowSceneSessionRoleExternalDisplayNonInteractive' in source, 'role check')
    check('[coordinator sceneDidConnect:(UIWindowScene *)scene];' in source, 'forwards connect')
    check('sceneDidDisconnect:(UIWindowScene *)scene];' in source, 'forwards disconnect')
    check('makeKeyAndVisible' not in source, 'never key')
    # A second external scene stands by: its delegate never holds the window
    # of the scene that shows NeoStation (retired: `self.window =
    # coordinator.window;` whatever the scene).
    check('self.window = coordinator.window.windowScene == scene ? coordinator.window : nil;' in source,
          'the delegate keeps the window of its own scene only')


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
    # The verified write moved to writeNumber:forKey: (shared with the
    # derived Enabled value of storeMode:); storeNumber: still notifies only
    # after it succeeded.
    write = method_body(source, '+ (BOOL)writeNumber:(NSNumber *)value forKey:(NSString *)key {')
    check(write.index('setObject:value forKey:key') < write.index('objectForKey:key'), 'written, then read back')
    check('return [stored isKindOfClass:NSNumber.class] && [(NSNumber *)stored isEqualToNumber:value];' in write,
          'a value iOS did not keep is reported')
    check('postNotificationName' not in write, 'a bare write tells nobody')
    store = method_body(source, '+ (BOOL)storeNumber:(NSNumber *)value forKey:(NSString *)key {')
    check(store.index('[self writeNumber:value forKey:key]') < store.index('postNotificationName:NeoExternalDisplayChangedNotification'),
          'the notification follows a verified write')
    check('if (![self writeNumber:value forKey:key]) return NO;' in store, 'a write iOS did not keep is reported (SAVE_FAILED)')
    # m1: storing a mode while the Enabled and Mode keys are both absent ends
    # the 442 fallback, so the derived Enabled value is persisted first,
    # without notification: choosing a format never turns the output on.
    store_mode = method_body(code(source), '+ (BOOL)storeMode:(NeoExternalDisplayMode)mode {')
    check('[defaults objectForKey:NeoExternalDisplayEnabledKey] == nil && [defaults objectForKey:NeoExternalDisplayModeKey] == nil' in store_mode
          and '![self writeNumber:@([self enabled]) forKey:NeoExternalDisplayEnabledKey]' in store_mode,
          'the derived Enabled value is persisted before the mode')
    check(store_mode.index('writeNumber:@([self enabled])') < store_mode.index('[self storeNumber:@((NSInteger)mode) forKey:NeoExternalDisplayModeKey]'),
          'before the Mode key ends the fallback')
    check(store_mode.count('return NO;') >= 2, 'a derived value iOS did not keep is a failed store')
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
    for method in ('getState', 'setEnabled', 'setMode', 'setMenuOnTV', 'configureMenuEngine', 'updateMenuEngine', 'pushMenuState'):
        check(f'isEqualToString:@"{method}"' in source, f'method {method}')
    set_mode = source.split('isEqualToString:@"setMode"', 1)[1].split('isEqualToString:@"setMenuOnTV"', 1)[0]
    check('NeoExternalDisplayModeOriginal' in set_mode and 'NeoExternalBadArguments' in set_mode, 'setMode refuses out of 0..3')
    check('storeMode:' in set_mode and 'NeoExternalSaveFailed' in set_mode, 'setMode reports SAVE_FAILED')
    # The TV engine never reads the database (review of 12 October 2026,
    # m11): configureMenuEngine also takes the language and the theme it
    # starts with (optional strings, any other type refused), and
    # updateMenuEngine forwards later changes. Retired contract: the call
    # stored the entrypoint pair only.
    configure = source.split('isEqualToString:@"configureMenuEngine"', 1)[1].split('isEqualToString:@"updateMenuEngine"', 1)[0]
    check(re.search(r'configureWithEntrypoint:entrypoint\s+libraryURI:libraryUri\s+languageCode:languageCode\s+themeName:themeName\]',
                    configure) is not None, 'configureMenuEngine stores the pair, the language and the theme')
    check('NeoExternalOptionalString(arguments, @"languageCode", &refused)' in configure
          and 'NeoExternalOptionalString(arguments, @"themeName", &refused)' in configure and '|| refused)' in configure,
          'a language or theme of another type is refused')
    check(configure.index('configureWithEntrypoint:') < configure.index('[coordinator refresh];'), 'a TV already connected gets its menu')
    update = source.split('isEqualToString:@"updateMenuEngine"', 1)[1].split('isEqualToString:@"pushMenuState"', 1)[0]
    check('[NeoExternalDisplayMenuEngine.shared updateLanguageCode:languageCode themeName:themeName];' in update
          and 'result(@YES);' in update and 'NeoExternalBadArguments(' in update, 'updateMenuEngine relays and answers true')
    optional = method_body(code(source), 'static NSString *_Nullable NeoExternalOptionalString(')
    check('if (value == nil || value == NSNull.null) return nil;' in optional and '*refused = YES;' in optional,
          'absent or null is no value; another type is refused')
    push = source.split('isEqualToString:@"pushMenuState"', 1)[1]
    check('pushMenuState:json' in push and 'result(@YES);' in push, 'pushMenuState relays and answers true')
    # § 8 bis: an engine whose bridge cannot call the coordinator (KartPad,
    # removed on 19 October 2026, was the last one) has Flutter ask for the
    # suspension.
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
    # Retired token: makeEngineWithEntrypoint:libraryURI:. The engine is now
    # made from FlutterEngineGroupOptions so that it receives the language
    # and the theme as entrypoint arguments (m11: it never reads the
    # database); the entrypoint and library stay those Dart named.
    for token in ('kNeoExternalMenuEngineGroupName = @"neostation-external"',
                  'kNeoExternalMenuChannelName = @"neostation/external_display/menu"',
                  'kNeoExternalMenuLocaleChannelName = @"neostation/external_display/menu_locale"',
                  'kNeoExternalMenuLanguageArgumentPrefix = @"language="', 'kNeoExternalMenuThemeArgumentPrefix = @"theme="',
                  '[[FlutterEngineGroup alloc] initWithName:kNeoExternalMenuEngineGroupName project:nil]',
                  'FlutterEngineGroupOptions *options = [[FlutterEngineGroupOptions alloc] init];',
                  'options.entrypoint = self.entrypoint;', 'options.libraryURI = self.libraryURI;',
                  'options.entrypointArgs = [self entrypointArguments];', '[self.group makeEngineWithOptions:options]',
                  'codec:FlutterStringCodec.sharedInstance', 'NSClassFromString(name)',
                  'respondsToSelector:@selector(registerWithRegistrar:)', '[engine destroyContext];',
                  'engine.viewController = nil;', 'if (!self.configured) return nil;'):
        check(token in source, token)
    check('makeEngineWithEntrypoint:' not in code(source), 'one way to make the engine: with its arguments')
    # The pinned Flutter engine declares the options API this file uses
    # (checked wherever the iOS engine artifacts are cached).
    flutter = shutil.which('flutter')
    group_header = (Path(flutter).resolve().parent / 'cache/artifacts/engine/ios/Flutter.xcframework/ios-arm64'
                    / 'Flutter.framework/Headers/FlutterEngineGroup.h') if flutter else None
    if group_header is not None and group_header.is_file():
        group = group_header.read_text(encoding='utf-8')
        for declared in ('@interface FlutterEngineGroupOptions', 'NSArray<NSString*>* entrypointArgs',
                         '- (FlutterEngine*)makeEngineWithOptions:(nullable FlutterEngineGroupOptions*)options;'):
            check(declared in group, f'FlutterEngineGroup.h of the pinned engine declares {declared}')
    arguments = method_body(code(source), '- (NSArray<NSString *> *)entrypointArguments {')
    check('[kNeoExternalMenuLanguageArgumentPrefix stringByAppendingString:self.languageCode]' in arguments
          and '[kNeoExternalMenuThemeArgumentPrefix stringByAppendingString:self.themeName]' in arguments,
          'language=<code> and theme=<name>, as ExternalDisplayMenuArgs parses them')
    update = method_body(code(source), '- (void)updateLanguageCode:(NSString *)languageCode themeName:(NSString *)themeName {')
    check('if (themeName.length > 0) self.themeName = themeName;' in update
          and update.index('self.languageCode = languageCode;') < update.index('[self.localeChannel sendMessage:languageCode];'),
          'the next engine starts with the new values, the running one is sent the language')
    # The TV menu stops drawing while it is hidden (a game holds the TV or
    # iOS mirrors): lifecycle `hidden`, `resumed` when it shows again, sent
    # again after an activation (the FlutterViewController sends `resumed`
    # itself then).
    for token in ('kNeoExternalLifecycleHidden = @"AppLifecycleState.hidden"', 'kNeoExternalLifecycleResumed = @"AppLifecycleState.resumed"',
                  '[engine.lifecycleChannel sendMessage:state];', 'kNeoExternalLifecycleReassertDelay = 0.1;',
                  'afterDelay:kNeoExternalLifecycleReassertDelay'):
        check(token in source, f'lifecycle: {token}')
    visible = method_body(code(source), '- (void)externalMenuSetVisible:(BOOL)visible {')
    check('self.menuVisible = visible;' in visible and '[self sendLifecycle];' in visible, 'the coordinator drives the lifecycle')
    destroy_lifecycle = method_body(code(source), '- (void)destroyExternalMenuEngineForReason:(NSString *)reason {')
    check('cancelPreviousPerformRequestsWithTarget:self selector:@selector(reassertLifecycle)' in destroy_lifecycle
          and 'removeObserver:self' in destroy_lifecycle, 'nothing of a destroyed engine stays scheduled')
    # Frozen registry, checked against the plugins the app pins: see
    # test/external_display_scope_test.py (EXPECTED_MENU_PLUGINS).
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

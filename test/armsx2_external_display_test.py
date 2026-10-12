#!/usr/bin/env python3
"""Source contracts of the ARMSX2 external-display adoption (Build 447,
docs/external-display-universal.md § 5, row ARMSX2).

The ARMSX2 bridge cannot run on Linux (Objective-C++, a Core loaded with
dlopen, UIKit), so these are source contracts in the pattern of
test/dolphin_external_display_test.py: each one pins a behaviour of the
bridge that the coordinator relies on, by the order of the statements that
implement it, never by prose. The coordinator's own guarantees (transform
only, scale kept, return to index 0 before a stop) are checked by
test/external_display_test.py on the external_display pod.

What this file pins:

* the view the Core created (`coreView`) is the render view and the game
  controller's root view the placeholder, with the touch controls, the menu
  button and the status label above it on the iPhone;
* the adapter is a fixed drawable (`fixedDrawable` YES): the Core sized its
  surface for the iPhone and the bridge never resizes, moves or transforms
  that view itself;
* `viewDidLayoutSubviews` does not resize the core view while the adapter is
  attached (the view is in the external window then) and always lays the
  controls out on the iPhone;
* the host attaches after the presentation and after a successful boot, and
  only for the current session;
* the host detaches before the Core stops (`request_stop`/`shutdown`), before
  the presentation is dismissed and before the Core releases the view; a
  stop that fails returns the game to the TV;
* the podspec depends on the external_display pod and the bridge imports
  only the headers that pod publishes.

No device claim: whether the ARMSX2 picture reaches an Apple TV is an
iPhone + Apple TV verification (contract § 9).
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / 'packages/armsx2_internal_bridge/ios'
CLASSES = BRIDGE / 'Classes'
PLUGIN = CLASSES / 'Armsx2InternalBridgePlugin.mm'
PODSPEC = BRIDGE / 'armsx2_internal_bridge.podspec'
EXTERNAL = ROOT / 'packages/external_display/ios'
EXTERNAL_POD = 'external_display'

ATTACH = '[self attachExternalDisplayForController:controller];'
DETACH_CURRENT = '[self detachExternalDisplayFromController:self.gameController];'


def code(text: str) -> str:
    """Source without comments (prose must not satisfy a contract)."""
    text = re.sub(r'/\*.*?\*/', ' ', text, flags=re.S)
    return re.sub(r'//[^\n]*', ' ', text)


def method_body(source: str, signature: str) -> str:
    """The method from its signature to the next method or directive (or the
    end of `source` when it closes an implementation body)."""
    start = source.index(signature)
    end = re.search(r'\n[-+@]', source[start + len(signature):])
    if end is None:
        return source[start:]
    return source[start:start + len(signature) + end.start()]


def implementation_body(source: str, name: str) -> str:
    start = source.index(f'@implementation {name}')
    return source[start:source.index('\n@end', start)]


def external_public_headers() -> list[str]:
    """The headers the external_display pod publishes (public_header_files):
    the only ones a bridge can import as <external_display/Name.h>."""
    podspec = (EXTERNAL / f'{EXTERNAL_POD}.podspec').read_text(encoding='utf-8')
    match = re.search(r"public_header_files\s*=\s*((?:'[^']*'\s*,?\s*)+)", podspec)
    assert match is not None, 'external_display.podspec declares public_header_files'
    names = [Path(name).name for name in re.findall(r"'([^']*)'", match.group(1))]
    assert names, 'external_display publishes at least one header'
    return names


class AdapterContracts(unittest.TestCase):
    def setUp(self) -> None:
        self.plugin = PLUGIN.read_text(encoding='utf-8')
        self.stripped = code(self.plugin)
        self.adapter = code(implementation_body(self.plugin, 'Armsx2ExternalRenderHost'))

    def test_bridge_imports_only_published_pod_headers(self) -> None:
        self.assertIn('#import <external_display/NeoExternalDisplayCoordinator.h>', self.plugin)
        public = external_public_headers()
        for path in sorted(CLASSES.iterdir()):
            if path.suffix not in {'.h', '.m', '.mm'}:
                continue
            for name in re.findall(r'#import <external_display/([^>]+)>', path.read_text(encoding='utf-8')):
                self.assertIn(name, public, f'{path.name} imports <external_display/{name}>, which the pod does not publish')

    def test_adapter_is_a_fixed_drawable_host_of_the_core_view(self) -> None:
        self.assertIn('@interface Armsx2ExternalRenderHost : NSObject <NeoExternalRenderHost>', self.plugin)
        self.assertIn('- (BOOL)fixedDrawable { return YES; }', self.adapter, 'the Core sized the drawable: transform only')
        # The Core owns the view (coreView is assign): the adapter never retains it.
        self.assertIn('__weak UIView* _renderView;', self.adapter)
        self.assertIn('__weak UIView* _placeholderView;', self.adapter)
        self.assertIn('- (UIView*)renderView { return _renderView; }', self.adapter)
        self.assertIn('- (UIView*)placeholderView { return _placeholderView; }', self.adapter)
        self.assertIn('@property(nonatomic, readonly) BOOL attached;', self.plugin)
        changed = method_body(self.adapter, '- (void)externalDisplayDidChange:(BOOL)active {')
        self.assertIn('_attached = active;', changed, 'the flag follows the coordinator: set after the move, cleared after the return')

    def test_adapter_owns_no_window_screen_transform_or_observer(self) -> None:
        # The coordinator moves, scales and returns the view (external_display_test.py);
        # the adapter is state only and never touches the iPhone controls.
        for forbidden in ('UIScreen', 'UIWindow', 'CGAffineTransform', 'insertSubview', 'removeFromSuperview',
                          'addSubview', 'addObserver', 'NSNotificationCenter', 'autoResizeDrawable',
                          'contentScaleFactor', 'drawableSize', '.frame', '.bounds', '.center',
                          'controlsView', 'menuButton', 'statusLabel', 'showStatus'):
            self.assertNotIn(forbidden, self.adapter, f'adapter: {forbidden} belongs to the coordinator or the controller')


class ControllerContracts(unittest.TestCase):
    def setUp(self) -> None:
        self.plugin = PLUGIN.read_text(encoding='utf-8')
        self.stripped = code(self.plugin)

    def test_core_view_is_the_render_view_below_the_controls_on_the_phone(self) -> None:
        load = code(method_body(self.plugin, '- (void)loadView {'))
        self.assertIn('self.coreView = render;', load)
        render_added = load.index('[root addSubview:render];')
        for overlay in ('[root addSubview:self.controlsView];', '[root addSubview:self.menuButton];',
                        '[root addSubview:self.statusLabel];'):
            self.assertLess(render_added, load.index(overlay), f'{overlay} is above the core view on the iPhone')
        attach = code(method_body(self.plugin, '- (void)attachExternalDisplayForController:(Armsx2GameViewController*)controller {'))
        self.assertIn('initWithRenderView:controller.coreView placeholder:controller.view', attach,
                      'render view = the core view, placeholder = the root view that keeps the controls')
        self.assertIn('@property(nonatomic, strong) Armsx2ExternalRenderHost* externalRenderHost;', self.plugin)

    def test_layout_pass_does_not_resize_the_core_view_while_attached(self) -> None:
        layout = code(method_body(self.plugin, '- (void)viewDidLayoutSubviews {'))
        self.assertIn('if (!self.externalRenderHost.attached) self.coreView.frame = self.view.bounds;', layout)
        self.assertEqual(layout.count('coreView.frame'), 1, 'no unguarded resize of the core view')
        self.assertIn('\n  self.controlsView.frame = self.view.bounds;', layout, 'the controls always follow the iPhone')

    def test_bridge_never_moves_or_transforms_the_core_view_itself(self) -> None:
        for forbidden in ('coreView.transform', 'coreView.bounds', 'coreView.center', 'removeFromSuperview',
                          'insertSubview', 'CGAffineTransform', 'contentScaleFactor', 'autoResizeDrawable',
                          'drawableSize', 'UIScreenDidConnect', 'UIScreenDidDisconnect', 'UIWindow alloc'):
            self.assertNotIn(forbidden, self.stripped, f'{forbidden}: moving the core view belongs to the coordinator')
        # The only other frame of the core view is its creation, before any adapter exists.
        load = code(method_body(self.plugin, '- (void)loadView {'))
        self.assertIn('render.frame = root.bounds;', load)
        self.assertEqual(self.stripped.count('render.frame ='), 1)


class LifecycleContracts(unittest.TestCase):
    def setUp(self) -> None:
        self.plugin = PLUGIN.read_text(encoding='utf-8')
        self.stripped = code(self.plugin)

    def test_attach_after_presentation_and_boot_for_the_current_session(self) -> None:
        launch = code(method_body(self.plugin, '- (void)handleMethodCall:(FlutterMethodCall*)call result:(FlutterResult)result {'))
        presented = launch.index('[root presentViewController:controller animated:NO completion:nil];')
        booted = launch.index('self.api->boot(bootPath, kind, 120000, error, sizeof(error))')
        attached = launch.index(ATTACH)
        self.assertLess(presented, booted)
        self.assertLess(booted, attached, 'the Core sized its surface for the iPhone before the view may move')
        self.assertLess(attached, launch.index('@"message": @"ARMSX2 entered Running."'), 'attached before the launch result')
        self.assertEqual(launch.count('attachExternalDisplayForController'), 1, 'one attach per launch')
        self.assertNotIn('attachExternalDisplay', code(method_body(self.plugin, '- (void)failTransaction:(NSString*)message result:(FlutterResult)result {')),
                         'a failed launch never had a host')
        attach = code(method_body(self.plugin, '- (void)attachExternalDisplayForController:(Armsx2GameViewController*)controller {'))
        self.assertIn('if (!NSThread.isMainThread) {', attach, 'the coordinator belongs to the main thread')
        self.assertIn('if (!controller || !controller.coreView || controller != self.gameController || self.stopInProgress) return;', attach)
        self.assertLess(attach.index('[self detachExternalDisplayFromController:controller];'), attach.index('alloc] initWithRenderView:'),
                        'attach once: a previous host is detached first')
        self.assertLess(attach.index('controller.externalRenderHost = host;'),
                        attach.index('[NeoExternalDisplayCoordinator.shared attachRenderHost:host];'))

    def test_detach_before_the_core_stops(self) -> None:
        stop = code(method_body(self.plugin, '- (void)stopActiveSessionWithCompletion:(void (^)(BOOL success, NSString* message))completion {'))
        hop = stop.index('if (!NSThread.isMainThread) {')
        detached = stop.index(DETACH_CURRENT)
        queued = stop.index('dispatch_async(_runtimeQueue, ^{')
        self.assertLess(hop, detached, 'the detach belongs to the main thread')
        self.assertLess(detached, queued, 'detached before the Core stop is even queued')
        self.assertLess(queued, stop.index('self.api->request_stop();'))
        self.assertLess(stop.index('self.api->request_stop();'), stop.index('self.api->shutdown(30000, error, sizeof(error))'))
        detach = code(method_body(self.plugin, '- (void)detachExternalDisplayFromController:(Armsx2GameViewController*)controller {'))
        self.assertIn('if (!host) return;', detach, 'harmless without a host')
        self.assertLess(detach.index('controller.externalRenderHost = nil;'),
                        detach.index('[NeoExternalDisplayCoordinator.shared detachRenderHost:host];'), 'detach once')

    def test_failed_stop_returns_the_game_to_the_tv(self) -> None:
        stop = code(method_body(self.plugin, '- (void)stopActiveSessionWithCompletion:(void (^)(BOOL success, NSString* message))completion {'))
        failure = stop[stop.index('if (!ok) {'):stop.index('[self dismissGameControllerWithCompletion:^{')]
        self.assertLess(failure.index('self.stopInProgress = NO;'), failure.index('[self attachExternalDisplayForController:self.gameController];'))
        self.assertLess(failure.index('[self attachExternalDisplayForController:self.gameController];'),
                        failure.index('if (completion) completion(NO, message);'))

    def test_every_teardown_detaches_before_dismissal_and_release(self) -> None:
        dismiss = code(method_body(self.plugin, '- (void)dismissGameControllerWithCompletion:(dispatch_block_t)completion {'))
        detached = dismiss.index('[self detachExternalDisplayFromController:controller];')
        self.assertLess(detached, dismiss.index('strongSelf.api->release_render_view();'), 'back on the iPhone before the Core releases the view')
        self.assertLess(detached, dismiss.index('[presenter dismissViewControllerAnimated:NO completion:releaseView];'))
        self.assertIn('[self dismissGameController];', code(method_body(self.plugin, '- (void)failTransaction:(NSString*)message result:(FlutterResult)result {')))
        self.assertIn('[self dismissGameControllerWithCompletion:nil];', code(method_body(self.plugin, '- (void)dismissGameController {')))
        self.assertEqual(self.stripped.count('release_render_view();'), 1, 'the Core releases its view once, after the dismissal')

    def test_the_menu_engine_is_not_destroyed_by_armsx2(self) -> None:
        # Contract § 5: only the RPCS3 bridge destroys the TV menu engine for memory.
        self.assertNotIn('destroyMenuEngineForMemory', self.stripped)


class DependencyContracts(unittest.TestCase):
    def test_podspec_depends_on_the_pod(self) -> None:
        podspec = PODSPEC.read_text(encoding='utf-8')
        self.assertIn("s.dependency 'external_display'", podspec)
        self.assertIn("s.dependency 'Flutter'", podspec)
        self.assertNotIn('vendored', podspec, 'the Core framework stays a preserved path, never linked at start')

    def test_retained_bridge_contracts(self) -> None:
        plugin = PLUGIN.read_text(encoding='utf-8')
        # neoplay_companion_contract_test.py markers and the touch surface used by the UI tests.
        for marker in ('Armsx2GameViewController', '@selector(menuPressed)', '@"armsx2-touch-controls"', '@"armsx2-game-menu"'):
            self.assertIn(marker, plugin)


if __name__ == '__main__':
    unittest.main(verbosity=2)

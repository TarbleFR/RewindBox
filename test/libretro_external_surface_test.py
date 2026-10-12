#!/usr/bin/env python3
"""Source contracts of the libretro bridge's external-display adoption
(docs/external-display-universal.md § 5, row "libretro"), on any OS.

- LibretroGameViewController adopts NeoExternalRenderHost with
  fixedDrawable NO, renderView = the Metal view, placeholderView = its own
  view; externalSurfaceDidChange:scale: stores the surface and relays out.
- performSkinLayoutIfNeeded draws into the external surface when the
  coordinator gave one (LibretroRenderSurface: drawable and scale from the
  TV) while the skin, the overlay and the chrome keep the iPhone bounds; the
  game areas of that iPhone layout are placed in the surface (scaled
  uniformly, centred, the black around them left out:
  LibretroRenderSurfacePlacement) and the session normalizes them by the
  surface's points; a touch screen comes back through the same placement
  to the phone's layout, where the overlay maps the touches. The Metal
  view's frame is left alone while it is in the external window.
- The status line "game shown on the external display" comes from the
  plugin's own twelve-language catalog (NeoExternalDisplayLabels) in the
  session's language, never from a Dart key (LibretroLocale.nativeKeys and
  LibretroRequiredUIText are unchanged) nor from a copy in the bridge.
- LibretroSession attaches once the game view appeared (presentation
  completion, before the emulation thread starts) and detaches before the
  core is asked to stop, and again before any dismissal.
- The bridge imports the plugin as a framework (<external_display/Name.h>):
  only headers the plugin podspec publishes, and the podspec depends on it;
  the iPhone syntax check stages those public headers the same way.
- The drawable rule is pure (no UIKit) and executed by the frontend harness
  (test/libretro_host/frontend/render_surface_test.m, macOS CI).
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / 'packages/libretro_internal_bridge/ios'
CLASSES = BRIDGE / 'Classes'
PLUGIN = ROOT / 'packages/external_display/ios'
PLUGIN_CLASSES = PLUGIN / 'Classes'
CONTROLLER_H = CLASSES / 'LibretroGameViewController.h'
CONTROLLER_M = CLASSES / 'LibretroGameViewController.m'
SESSION_M = CLASSES / 'LibretroSession.m'
SURFACE_H = CLASSES / 'LibretroRenderSurface.h'
PODSPEC = BRIDGE / 'libretro_internal_bridge.podspec'
FRONTEND_TEST = ROOT / 'test/libretro_host/frontend/render_surface_test.m'
SYNTAX_TEST = ROOT / 'test/libretro_ios_syntax_test.py'
LABEL_KEY = 'externalOnPhone'


def read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def code(text: str) -> str:
    """Source without comments (prose must not satisfy a contract)."""
    text = re.sub(r'/\*.*?\*/', ' ', text, flags=re.S)
    return re.sub(r'//[^\n]*', ' ', text)


def method_body(source: str, signature: str) -> str:
    """The body of an Objective-C method, from its signature to the next
    method or @end at column zero."""
    start = source.index(signature)
    end = re.search(r'\n[-+@]', source[start + len(signature):])
    assert end is not None, signature
    return source[start:start + len(signature) + end.start()]


def framework_imports(text: str) -> list[str]:
    return re.findall(r'#import\s*<external_display/([^>]+)>', text)


class ControllerAdoptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.header = code(read(CONTROLLER_H))
        self.source = code(read(CONTROLLER_M))

    def test_adopts_the_protocol_through_the_framework_header(self) -> None:
        self.assertIn('NeoExternalRenderHost.h', framework_imports(self.header))
        self.assertIn('@interface LibretroGameViewController : UIViewController <NeoExternalRenderHost>', self.header)
        self.assertIn('@property(nonatomic, copy) NSString *uiLocale;', self.header)

    def test_render_and_placeholder_views_and_a_non_fixed_drawable(self) -> None:
        render = method_body(self.source, '- (UIView *)renderView {')
        self.assertIn('return _metalView;', render)
        placeholder = method_body(self.source, '- (UIView *)placeholderView {')
        self.assertIn('return self.view;', placeholder)
        fixed = method_body(self.source, '- (BOOL)fixedDrawable {')
        self.assertIn('return NO;', fixed)
        self.assertNotIn('return YES;', fixed)

    def test_external_surface_is_stored_and_relaid_out(self) -> None:
        change = method_body(self.source, '- (void)externalSurfaceDidChange:(CGSize)pointSize scale:(CGFloat)scale {')
        self.assertIn('_externalSurface = pointSize;', change)
        self.assertIn('_externalScale = scale;', change)
        self.assertIn('[self setNeedsSkinLayout];', change)
        self.assertIn('CGSize _externalSurface;', self.source)
        self.assertIn('CGFloat _externalScale;', self.source)

    def test_drawable_follows_the_external_surface_while_skin_keeps_the_phone(self) -> None:
        layout = method_body(self.source, '- (void)performSkinLayoutIfNeeded {')
        self.assertIn('LibretroRenderSurfaceResolve(bounds.size, [self layoutScale], _externalSurface, _externalScale)', layout)
        self.assertIn('_metalView.contentScaleFactor = surface.scale;', layout)
        self.assertIn('CGSize drawableSize = LibretroRenderSurfaceDrawableSize(surface);', layout)
        # The skin layout, its orientation and the game areas are the iPhone view's.
        self.assertIn('CGRect bounds = self.view.bounds;', layout)
        self.assertIn('LibretroSize viewSize = [self layoutViewSize];', layout)
        self.assertIn('bounds.size.width > bounds.size.height ? LibretroSkinOrientationLandscape', layout)
        self.assertNotIn('viewSize:surface', layout)
        view_size = method_body(self.source, '- (LibretroSize)layoutViewSize {')
        self.assertIn('self.view.bounds.size', view_size)
        self.assertNotIn('_externalSurface', view_size)
        # No other drawable computation remains.
        self.assertNotIn('round(bounds.size.width * scale)', self.source)

    def test_picture_fills_the_external_surface_while_the_overlay_keeps_the_phone_layout(self) -> None:
        """The game areas laid out for the phone are placed in the TV's
        surface (scaled uniformly, centred, black around them left out) and
        the session normalizes them by the surface's points; the overlay
        receives the untouched iPhone layout. Replaces the earlier
        proportional placement (`points:bounds.size`), which left a portrait
        phone's picture in the upper part of a narrow pillar."""
        layout = method_body(self.source, '- (void)performSkinLayoutIfNeeded {')
        self.assertIn('_externalPlacement = LibretroRenderSurfacePlacementIdentity();', layout)
        self.assertIn('if (surface.external && layout != nil) {', layout)
        self.assertIn('_externalPlacement = LibretroRenderSurfacePlacementMake([self unionOfScreens:layout.screens], surface.points);', layout)
        self.assertIn('pictureScreens = [self screens:layout.screens placedBy:_externalPlacement];', layout)
        self.assertIn('screens:pictureScreens', layout)
        self.assertIn('points:surface.points]', layout)
        self.assertNotIn('points:bounds.size', layout)
        self.assertIn('_lastMappingSize = CGSizeZero;', layout)
        union = method_body(self.source, '- (CGRect)unionOfScreens:(NSArray<LibretroLaidOutScreen *> *)screens {')
        self.assertIn('CGRectUnion(areas, LibretroCGRectFromRect(screen.container))', union)
        placed = method_body(self.source, '- (NSArray<LibretroLaidOutScreen *> *)screens:(NSArray<LibretroLaidOutScreen *> *)screens')
        self.assertIn('LibretroRenderSurfacePlace(placement, LibretroCGRectFromRect(screen.container))', placed)
        for kept in ('entry.source = screen.source;', 'entry.role = screen.role;', 'entry.touchScreen = screen.touchScreen;'):
            self.assertIn(kept, placed)
        self.assertIn('LibretroRenderSurfacePlacement _externalPlacement;', self.source)
        header = code(read(CONTROLLER_H))
        self.assertIn('screens:(NSArray<LibretroLaidOutScreen *> *)screens', header)
        session = code(read(SESSION_M))
        did_layout = method_body(session, '- (void)gameViewDidLayout:(LibretroSkinLayoutResult *)layout')
        self.assertIn('screens:(NSArray<LibretroLaidOutScreen *> *)pictureScreens', did_layout)
        self.assertIn('for (LibretroLaidOutScreen *screen in pictureScreens) {', did_layout)
        self.assertNotIn('in layout.screens', did_layout)
        self.assertIn('[_controller.overlay applyLayout:layout inputMap:_inputMap', did_layout)

    def test_touch_screens_come_back_to_the_phone_layout(self) -> None:
        mappings = method_body(self.source, '- (void)refreshTouchScreenMappings:(NSArray<NSValue *> *)normalized {')
        self.assertIn('const BOOL external = [self onExternalDisplay];', mappings)
        self.assertIn('const CGSize picture = external ? _externalSurface : size;', mappings)
        self.assertIn('if (external) output = LibretroRenderSurfaceUnplace(_externalPlacement, output);', mappings)
        self.assertIn('mapping.output = LibretroRectFromCGRect(output);', mappings)
        change = method_body(self.source, '- (void)externalSurfaceDidChange:(CGSize)pointSize scale:(CGFloat)scale {')
        self.assertIn('_lastMappingSize = CGSizeZero;', change)

    def test_metal_view_frame_is_left_alone_on_the_tv(self) -> None:
        subviews = method_body(self.source, '- (void)viewDidLayoutSubviews {')
        self.assertIn('if (![self onExternalDisplay]) _metalView.frame = bounds;', subviews)
        on_external = method_body(self.source, '- (BOOL)onExternalDisplay {')
        self.assertIn('LibretroRenderSurfaceUsable(_externalSurface, _externalScale)', on_external)
        self.assertIn('"LibretroRenderSurface.h"', self.source)

    def test_status_line_comes_from_the_plugin_catalog(self) -> None:
        self.assertIn('NeoExternalDisplayLabels.h', framework_imports(self.source))
        change = method_body(self.source, '- (void)externalDisplayDidChange:(BOOL)active {')
        self.assertIn('if (!active) return;', change)
        self.assertIn(f'[self showStatus:NeoExternalDisplayText(@"{LABEL_KEY}", self.uiLocale)];', change)
        plugin_labels = read(PLUGIN_CLASSES / 'NeoExternalDisplayLabels.h')
        self.assertIn(f'@"{LABEL_KEY}":', plugin_labels)
        # No copy of the catalog and no English text of its own in the bridge.
        for path in sorted(CLASSES.glob('*.[hm]')):
            text = read(path)
            self.assertNotIn(f'@"{LABEL_KEY}": @"', text, path.name)
            self.assertNotIn('shown on the external display', text, path.name)


class SessionLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = code(read(SESSION_M))

    def test_coordinator_imported_as_a_framework_header(self) -> None:
        self.assertIn('NeoExternalDisplayCoordinator.h', framework_imports(self.source))

    def test_language_given_to_the_controller_before_presentation(self) -> None:
        start = method_body(self.source, '- (void)startFromViewController:(UIViewController *)presenter')
        self.assertLess(start.index('_controller.uiLocale = [self uiLocale];'), start.index('[presenter presentViewController:_controller'))

    def test_attach_after_the_view_appeared_and_before_the_thread(self) -> None:
        start = method_body(self.source, '- (void)startFromViewController:(UIViewController *)presenter')
        present = start.index('[presenter presentViewController:_controller')
        attach = start.index('[session attachExternalDisplay];')
        thread_start = start.index('[session->_thread start];')
        self.assertLess(present, attach)
        self.assertLess(attach, thread_start)
        self.assertEqual(self.source.count('attachRenderHost:'), 1)
        attach_body = method_body(self.source, '- (void)attachExternalDisplay {')
        self.assertIn('[NeoExternalDisplayCoordinator.shared attachRenderHost:controller];', attach_body)
        self.assertIn('if (controller == nil) return;', attach_body)

    def test_detach_before_the_core_is_asked_to_stop(self) -> None:
        stop = method_body(self.source, '- (void)stopWithCompletion:(dispatch_block_t)completion {')
        self.assertLess(stop.index('[self detachExternalDisplayFrom:_controller];'), stop.index('_stopRequested = YES;'))
        self.assertLess(stop.index('[self detachExternalDisplayFrom:_controller];'), stop.index('[self finishStop];'))
        detach = method_body(self.source, '- (void)detachExternalDisplayFrom:(LibretroGameViewController *)controller {')
        self.assertIn('[NeoExternalDisplayCoordinator.shared detachRenderHost:controller];', detach)
        self.assertEqual(self.source.count('detachRenderHost:'), 1)

    def test_detach_before_every_dismissal(self) -> None:
        for signature in ('- (void)finishStop {', '- (void)failStartWithResult:(NSDictionary<NSString *, id> *)result {'):
            body = method_body(self.source, signature)
            detach = body.index('[self detachExternalDisplayFrom:controller];')
            self.assertLess(detach, body.index('[controller stopInputPolling];'), signature)
            self.assertLess(detach, body.index('dismissViewControllerAnimated:NO'), signature)


class DartCatalogTests(unittest.TestCase):
    def test_label_is_not_a_dart_native_key(self) -> None:
        dart = read(ROOT / 'lib/l10n/libretro_locale.dart')
        native = dart[dart.index('nativeKeys = <String>['):]
        native = native[:native.index('];')]
        self.assertNotIn(f"'{LABEL_KEY}'", native)
        plugin = code(read(CLASSES / 'LibretroInternalBridgePlugin.m'))
        required = plugin[plugin.index('LibretroRequiredUIText(void) {'):]
        required = required[:required.index('];')]
        self.assertNotIn(f'@"{LABEL_KEY}"', required)


class PackageWiringTests(unittest.TestCase):
    def test_podspec_depends_on_the_plugin(self) -> None:
        podspec = read(PODSPEC)
        self.assertIn("s.dependency 'external_display'", podspec)
        self.assertIn("s.public_header_files = 'Classes/LibretroInternalBridgePlugin.h'", podspec)

    def test_only_published_plugin_headers_are_imported(self) -> None:
        podspec = read(PLUGIN / 'external_display.podspec')
        match = re.search(r"public_header_files\s*=\s*((?:'[^']*'\s*,?\s*)+)", podspec)
        self.assertIsNotNone(match)
        published = {Path(name).name for name in re.findall(r"'([^']*)'", match.group(1))}
        imported = set()
        for path in sorted(CLASSES.glob('*.[hm]')):
            imported.update(framework_imports(code(read(path))))
        self.assertTrue(imported, 'the bridge imports the plugin')
        for name in sorted(imported):
            self.assertTrue((PLUGIN_CLASSES / name).is_file(), name)
            self.assertIn(name, published,
                          f'{name} is imported as <external_display/{name}> but external_display.podspec does not publish it '
                          '(public_header_files): the framework CocoaPods builds would not expose it to the bridge')
        # Quoted imports never reach into the plugin's tree.
        for path in sorted(CLASSES.glob('*.[hm]')):
            self.assertNotRegex(code(read(path)), r'#import\s*"[^"]*external_display', path.name)


class PureRuleTests(unittest.TestCase):
    def test_render_surface_header_is_pure_and_executed(self) -> None:
        header = read(SURFACE_H)
        self.assertNotIn('<UIKit/', header)
        self.assertNotIn('<MetalKit/', header)
        for function in ('LibretroRenderSurfaceUsable', 'LibretroRenderSurfaceResolve', 'LibretroRenderSurfaceDrawableSize',
                         'LibretroRenderSurfacePlacementIdentity', 'LibretroRenderSurfacePlacementMake',
                         'LibretroRenderSurfacePlace', 'LibretroRenderSurfaceUnplace'):
            self.assertIsNotNone(re.search(r'static inline \w+ ' + function + r'\(', header), function)
        test = read(FRONTEND_TEST)
        self.assertIn('#import "LibretroRenderSurface.h"', test)
        self.assertIn('NeoExternalDisplaySurfaceSize(', test)
        self.assertIn('NeoExternalDisplayEffectiveMode(stored, NeoExternalContentGame)', test)
        # The placement is executed too: Fit at the TV's full height, Fill,
        # the portrait pillar, stacked 3DS screens, the way back for a
        # touch screen, degenerate inputs.
        for executed in ('LibretroRenderSurfacePlacementMake(', 'LibretroRenderSurfacePlace(', 'LibretroRenderSurfaceUnplace(',
                         'LibretroRenderSurfacePlacementIdentity()', 'CGRectMake(240, 0, 1440, 1080)', 'CGRectMake(0, 0, 1920, 1440)',
                         'CGRectMake(0, 353.25, 498, 373.5)', 'CGRectUnion(top, bottom)', 'CGRectMake(80, 500, 640, 480)'):
            self.assertIn(executed, test)

    def test_iphone_syntax_check_stages_the_published_headers(self) -> None:
        syntax = read(SYNTAX_TEST)
        self.assertIn('def stage_external_display(directory):', syntax)
        self.assertIn('public_header_files', syntax)
        self.assertIn("EXTERNAL_DISPLAY_POD = 'external_display'", syntax)
        self.assertIn('include = stage_external_display(directory)', syntax)
        self.assertIn('compile_sources(sdk, sources, directory, include)', syntax)


if __name__ == '__main__':
    unittest.main(verbosity=2)

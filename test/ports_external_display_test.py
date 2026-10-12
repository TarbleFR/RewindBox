#!/usr/bin/env python3
"""Source contracts of the Dusklight and KartPad bridges towards the external
display host (docs/external-display-universal.md § 5, last row).

Both engines draw in an SDL window created inside their locked core, so
NeoStation's external-display window cannot host them. Each bridge therefore
hides that window for the session, as the last statement before the native
handoff (`_api->start`), so iOS resumes mirroring the iPhone, and shows it
again on every end path: a start refused by the core, the end-of-session
event (clean return, language restart, runtime failure, crash, first-frame
timeout and Flutter `stop` all come back through `coreState:`), and the
plugin's own deallocation, where the core callback is cleared first. Only
`suspendForUnsupportedEngine` and `resumeAfterUnsupportedEngine` are used:
no render host, menu, scene or preference API, and nothing under native/
(the baseline manifest hashes of both cores are re-verified here).

Like test/dolphin_external_display_test.py this is a source contract: the
bridges compile on macOS CI only and the window hand-off runs only on an
iPhone with an Apple TV. No device claim.
"""
from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTERNAL = ROOT / 'packages/external_display/ios'
EXTERNAL_POD = 'external_display'
COORDINATOR_HEADER = 'NeoExternalDisplayCoordinator.h'
MANIFEST = ROOT / 'docs/retroarch-baseline-manifest.json'
NATIVE_TREES = ('native/dusklight', 'native/kartpad')
WINDOW_OWNERS = ('native/dusklight/core/NeoDusklightCore.mm', 'native/kartpad/donor/NeoKartPadDonorCore.mm')
SUSPEND = '[self suspendExternalDisplay];'
RESUME = '[self resumeExternalDisplay];'
ALLOWED_COORDINATOR_API = {'suspendForUnsupportedEngine', 'resumeAfterUnsupportedEngine'}
# Everything else the coordinator header offers (docs § 3.3) stays unused by
# these two bridges, strings included.
FORBIDDEN_TOKENS = (
    'attachRenderHost', 'detachRenderHost', 'attachMenuViewController', 'detachMenuViewController',
    'destroyMenuEngineForMemory', 'sceneDidConnect', 'sceneDidDisconnect', 'windowFactory', 'legacyScreens',
    'stateChanged', 'menuProvider', 'stateDictionary', 'NeoExternalRenderHost', 'NeoExternalDisplayPreferences',
    'NeoExternalDisplayLayout', 'NeoExternalDisplayLabels', 'NeoExternalDisplaySceneDelegate', 'ExternalDisplayPlugin',
    'NeoStation.ExternalDisplay',
)

BRIDGES = {
    'dusklight': dict(
        package='packages/dusklight_internal_bridge',
        plugin='DusklightInternalBridgePlugin.mm',
        # The method that hands the game to the core.
        handoff='- (void)handleMethodCall:',
        start='const int started = _api->start(gamePath.fileSystemRepresentation,',
        ended='} else if (state == NEO_DUSKLIGHT_ENDED || state == NEO_DUSKLIGHT_IDLE) {',
        session_ended='invokeMethod:@"sessionEnded"',
        stop_handler='if (_api != nullptr && _api->is_running()) _api->stop();',
    ),
    'kartpad': dict(
        package='packages/kartpad_internal_bridge',
        plugin='KartPadInternalBridgePlugin.mm',
        handoff='- (void)beginSessionForGamePath:(NSString*)gamePath hostWindow:(UIWindow*)hostWindow {',
        start='const int started = _api->start(\n      gamePath.fileSystemRepresentation, (__bridge void*)hostWindow,',
        ended='if (state != NEO_KARTPAD_IDLE && state != NEO_KARTPAD_ENDED) return;',
        session_ended='[self deliverSessionEndedForTransaction:endedTransaction',
        stop_handler='if (_api && _api->is_running()) _api->stop();',
    ),
}


def code(text: str) -> str:
    """Source without comments (prose must not satisfy a contract)."""
    text = re.sub(r'/\*.*?\*/', ' ', text, flags=re.S)
    return re.sub(r'//[^\n]*', ' ', text)


def without_strings(text: str) -> str:
    return re.sub(r'@?"(?:\\.|[^"\\])*"', '""', text)


def method_body(source: str, signature: str) -> str:
    start = source.index(signature)
    end = re.search(r'\n[-+@]', source[start + len(signature):])
    assert end is not None, signature
    return source[start:start + len(signature) + end.start()]


def external_public_headers() -> list[str]:
    """The headers the external_display pod publishes: the only ones a bridge
    can import as <external_display/Name.h>."""
    podspec = (EXTERNAL / f'{EXTERNAL_POD}.podspec').read_text(encoding='utf-8')
    match = re.search(r"public_header_files\s*=\s*((?:'[^']*'\s*,?\s*)+)", podspec)
    assert match is not None, 'external_display.podspec declares public_header_files'
    return [Path(name).name for name in re.findall(r"'([^']*)'", match.group(1))]


def classes_dir(spec: dict) -> Path:
    return ROOT / spec['package'] / 'ios/Classes'


def plugin_text(spec: dict) -> str:
    return (classes_dir(spec) / spec['plugin']).read_text(encoding='utf-8')


class PodWiringTests(unittest.TestCase):
    def test_dependency_and_guarded_import(self) -> None:
        public = external_public_headers()
        self.assertIn(COORDINATOR_HEADER, public)
        for name, spec in BRIDGES.items():
            with self.subTest(bridge=name):
                podspecs = list((ROOT / spec['package'] / 'ios').glob('*.podspec'))
                self.assertEqual(len(podspecs), 1, name)
                podspec = podspecs[0].read_text(encoding='utf-8')
                self.assertIn("s.dependency 'external_display'", podspec, f'{name}: the bridge depends on the pod')
                self.assertLess(podspec.index("s.dependency 'Flutter'"), podspec.index("s.dependency 'external_display'"))
                raw = plugin_text(spec)
                guarded = (f'#if __has_include(<{EXTERNAL_POD}/{COORDINATOR_HEADER}>)\n'
                           f'#import <{EXTERNAL_POD}/{COORDINATOR_HEADER}>\n'
                           f'#else\n#import "{COORDINATOR_HEADER}"\n#endif')
                self.assertIn(guarded, raw, f'{name}: the pod import with its plain fallback, as the Dolphin adapter does')
                self.assertEqual(raw.count(f'#import <{EXTERNAL_POD}/'), 1, f'{name}: the coordinator is the only pod header')
                self.assertEqual(raw.count('#import "NeoExternal'), 1, f'{name}: the plain import is only the fallback')
                for path in sorted(classes_dir(spec).iterdir()):
                    if path.name != spec['plugin'] and path.suffix in {'.h', '.m', '.mm'}:
                        self.assertNotIn('external_display', path.read_text(encoding='utf-8'), f'{path.name}: only the plugin talks to the pod')


class SuspendResumeTests(unittest.TestCase):
    def test_suspend_is_the_last_statement_before_the_native_handoff(self) -> None:
        for name, spec in BRIDGES.items():
            with self.subTest(bridge=name):
                source = code(plugin_text(spec))
                handoff = method_body(source, spec['handoff'])
                self.assertEqual(source.count(SUSPEND), 1, f'{name}: one suspend call site in the plugin')
                self.assertEqual(handoff.count(SUSPEND), 1, f'{name}: it is in the handoff method')
                self.assertIn(spec['start'], handoff)
                at = handoff.index(SUSPEND)
                between = handoff[at + len(SUSPEND):handoff.index(spec['start'])]
                self.assertEqual(between.strip(), '', f'{name}: nothing runs between the suspend and _api->start')
                self.assertLess(handoff.index('_sessionActive = YES;'), at, f'{name}: the session is accepted first')
                # Every refusal before the handoff (unreadable game, core
                # missing, session active, restart required, initialize, no
                # host view) returns without touching the TV.
                self.assertNotIn('ExternalDisplay', handoff[:at], f'{name}: no external-display call before the handoff')

    def test_resume_on_every_end_path(self) -> None:
        for name, spec in BRIDGES.items():
            with self.subTest(bridge=name):
                source = code(plugin_text(spec))
                handoff = method_body(source, spec['handoff'])
                # 1. The core refuses the start.
                refused = handoff[handoff.index('if (started <= 0) {'):]
                refused = refused[:refused.index('return;')]
                self.assertIn(RESUME, refused, f'{name}: a refused start restores the window')
                self.assertLess(refused.index('_sessionActive = NO;'), refused.index(RESUME))
                self.assertLess(refused.index(RESUME), refused.index('[self resolveLaunch:'), f'{name}: restored before Flutter is answered')
                # 2. The core reports the end of the session (every exit reason,
                # the first-frame timeout and Flutter `stop` end here).
                core_state = method_body(source, '- (void)coreState:(int)state message:(NSString*)message {')
                ended = core_state[core_state.index(spec['ended']):]
                self.assertIn(RESUME, ended, f'{name}: the end-of-session event restores the window')
                self.assertLess(ended.index('_sessionActive = NO;'), ended.index(RESUME))
                self.assertLess(ended.index(RESUME), ended.index('[self resolveLaunch:'), f'{name}: before a pending launch is answered')
                self.assertLess(ended.index(RESUME), ended.index(spec['session_ended']), f'{name}: before sessionEnded reaches Flutter')
                self.assertNotIn('ExternalDisplay', core_state[:core_state.index(spec['ended'])], f'{name}: the first frame never resumes')
                timer = handoff[handoff.index('_startupTimer = [NSTimer timerWithTimeInterval:90'):]
                self.assertIn('strongSelf->_api->stop();', timer, f'{name}: the timeout stops the core, which reports the end')
                self.assertIn(spec['stop_handler'], method_body(source, '- (void)handleMethodCall:'), f'{name}: Flutter stop goes through the core too')
                # 3. Deallocation clears the callback before stopping the core.
                dealloc = method_body(source, '- (void)dealloc {')
                self.assertIn(RESUME, dealloc, f'{name}: dealloc restores the window itself')
                self.assertLess(dealloc.index(RESUME), dealloc.index('set_event_callback(nullptr, nullptr)'))
                self.assertEqual(source.count(RESUME), 3, f'{name}: exactly the three end paths')

    def test_helpers_pair_and_belong_to_the_main_thread(self) -> None:
        for name, spec in BRIDGES.items():
            with self.subTest(bridge=name):
                raw = plugin_text(spec)
                source = code(raw)
                self.assertIn('BOOL _externalDisplaySuspended;', source)
                self.assertIn('- (void)suspendExternalDisplay;', source, f'{name}: declared in the class extension')
                self.assertIn('- (void)resumeExternalDisplay;', source)
                suspend = method_body(source, '- (void)suspendExternalDisplay {')
                resume = method_body(source, '- (void)resumeExternalDisplay {')
                self.assertIn('if (_externalDisplaySuspended) return;', suspend)
                self.assertIn('_externalDisplaySuspended = YES;', suspend)
                self.assertIn('[NeoExternalDisplayCoordinator.shared suspendForUnsupportedEngine];', suspend)
                self.assertIn('if (!_externalDisplaySuspended) return;', resume)
                self.assertIn('_externalDisplaySuspended = NO;', resume)
                self.assertIn('if (NSThread.isMainThread) {', resume, f'{name}: the coordinator is main-thread only')
                self.assertIn('dispatch_async(dispatch_get_main_queue(), ^{', resume, f'{name}: core events hop to the main thread')
                hop = resume[resume.index('dispatch_async('):]
                self.assertNotIn('self', hop, f'{name}: the hop captures nothing (dealloc-safe)')
                self.assertNotIn('_externalDisplaySuspended', hop)
                self.assertEqual(resume.count('[NeoExternalDisplayCoordinator.shared resumeAfterUnsupportedEngine];'), 2)
                # The coordinator selectors live only inside the two helpers.
                self.assertEqual(source.count('suspendForUnsupportedEngine'), 1, name)
                self.assertEqual(source.count('resumeAfterUnsupportedEngine'), 2, name)
                self.assertNotIn('UnsupportedEngine', source.replace(suspend, '').replace(resume, ''),
                                 f'{name}: the coordinator selectors appear nowhere else')


class ScopeTests(unittest.TestCase):
    def test_no_other_coordinator_api(self) -> None:
        for name, spec in BRIDGES.items():
            for path in sorted(classes_dir(spec).iterdir()):
                if path.suffix not in {'.h', '.m', '.mm'}:
                    continue
                with self.subTest(bridge=name, file=path.name):
                    raw = path.read_text(encoding='utf-8')
                    source = without_strings(code(raw))
                    uses = set(re.findall(r'NeoExternalDisplayCoordinator\.shared\s+(\w+)', source))
                    if path.name == spec['plugin']:
                        self.assertEqual(uses, ALLOWED_COORDINATOR_API, f'{path.name}: suspend/resume only')
                        self.assertEqual(set(re.findall(r'NeoExternal\w+', source)), {'NeoExternalDisplayCoordinator'})
                    else:
                        self.assertNotIn('NeoExternal', source, f'{path.name}: only the plugin talks to the coordinator')
                    self.assertIsNone(re.search(r'NeoExternalDisplayCoordinator\.shared\.\w', source), f'{path.name}: no property read')
                    self.assertNotIn('NeoExternalDisplayCoordinator alloc', source)
                    self.assertNotIn('[NeoExternalDisplayCoordinator ', source.replace('[NeoExternalDisplayCoordinator.shared ', ''))
                    # The SDL window belongs to the core: the bridge calls no SDL API.
                    self.assertNotIn('SDL_', source, f'{path.name}: SDL API')
                    for token in FORBIDDEN_TOKENS:
                        self.assertNotIn(token, raw, f'{path.name}: {token}')

    def test_locked_cores_untouched(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))['native_sha256']
        pinned = {path: digest for path, digest in manifest.items() if path.startswith(tuple(tree + '/' for tree in NATIVE_TREES))}
        for owner in WINDOW_OWNERS:
            self.assertIn(owner, pinned, f'{owner}: the window owner is pinned by the baseline manifest')
        for path, expected in sorted(pinned.items()):
            with self.subTest(path=path):
                self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), expected, f'{path} changed')
        # The cores never learn about the coordinator: the SDL window they
        # create, and the UIKit window hand-off around it, are not touched.
        for tree in NATIVE_TREES:
            for path in sorted((ROOT / tree).rglob('*')):
                if not path.is_file():
                    continue
                text = path.read_text(encoding='utf-8', errors='ignore')
                for token in ('NeoExternalDisplay', 'external_display', 'UnsupportedEngine'):
                    self.assertNotIn(token, text, f'{path.relative_to(ROOT)}: {token}')


if __name__ == '__main__':
    unittest.main(verbosity=2)

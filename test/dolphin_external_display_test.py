#!/usr/bin/env python3
"""Source contracts of the Dolphin external-display adapter, plus the Build
442 placement policy executed on macOS through its Build 447 delegation.

Build 442 gave DolphinExternalDisplay its own window, screens and placement.
Build 447 (docs/external-display-universal.md § 5, row Dolphin) moves all of
that to the external_display pod: DolphinExternalDisplay is now the bridge's
NeoExternalRenderHost (fixed drawable, render view = the Metal view,
placeholder = the session's container) that attaches to and detaches from
NeoExternalDisplayCoordinator, DolphinExternalDisplayLayout.h keeps the DOL
vocabulary but delegates to NeoExternalDisplayLayout.h, and the in-game
Display row reads and writes the global preference. The 442 guarantees
(autoResizeDrawable cut, scale kept, transform only, return to index 0
before the core stops) are therefore the coordinator's, checked by
test/external_display_test.py, while this file checks what stays the
bridge's: the ordering `externalDisplay stop` before `framePacing stop`, the
adapter shape, the delegation, the dependency and the public headers it
imports. Retired 442 assertions are named in comments at the place where
their replacement lives.

On macOS the policy header is then compiled with Foundation and CoreGraphics
only, the external_display headers staged as <external_display/…> exactly as
the pod publishes them, and test/dolphin_external_display_test.mm runs. The
window lifecycle (connect, modes, disconnect, stop) runs in the iOS Simulator
through dolphin_external_display_ui_test.py. No device claim.
"""
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/dolphin_internal_bridge/ios/Classes'
EXTERNAL = ROOT / 'packages/external_display/ios'
EXTERNAL_CLASSES = EXTERNAL / 'Classes'
EXTERNAL_POD = 'external_display'
LEGACY_KEY = 'NeoStation.Dolphin.ExternalDisplay.Mode'


def code(text: str) -> str:
    """Source without comments (prose must not satisfy a contract)."""
    text = re.sub(r'/\*.*?\*/', ' ', text, flags=re.S)
    return re.sub(r'//[^\n]*', ' ', text)


def method_body(source: str, signature: str) -> str:
    start = source.index(signature)
    end = re.search(r'\n[-+@]', source[start + len(signature):])
    assert end is not None, signature
    return source[start:start + len(signature) + end.start()]


def external_public_headers() -> list[str]:
    """The headers the external_display pod publishes (public_header_files):
    the only ones a bridge can import as <external_display/Name.h>."""
    podspec = (EXTERNAL / f'{EXTERNAL_POD}.podspec').read_text(encoding='utf-8')
    match = re.search(r"public_header_files\s*=\s*((?:'[^']*'\s*,?\s*)+)", podspec)
    assert match is not None, 'external_display.podspec declares public_header_files'
    names = [Path(name).name for name in re.findall(r"'([^']*)'", match.group(1))]
    assert names, 'external_display publishes at least one header'
    return names


def stage_external_display(directory: Path) -> Path:
    """<external_display/Name.h> resolves as the pod publishes it: a folder
    named after the pod holding its public headers and nothing else."""
    include = directory / 'include'
    staged = include / EXTERNAL_POD
    staged.mkdir(parents=True)
    for name in external_public_headers():
        shutil.copyfile(EXTERNAL_CLASSES / name, staged / name)
    return include


def layout_contracts() -> None:
    header = (CLASSES / 'DolphinExternalDisplayLayout.h').read_text(encoding='utf-8')
    stripped = code(header)
    assert '<UIKit/' not in header and '<MetalKit/' not in header, 'the placement policy stays executable without UIKit'
    # The 442 vocabulary stays for the 442 tests; Original is the Build 447 global format.
    for token in ('DOLExternalDisplayModeOff = 0', 'DOLExternalDisplayModeFit = 1', 'DOLExternalDisplayModeFill = 2',
                  'DOLExternalDisplayModeOriginal = 3'):
        assert token in header, token
    # Delegation: the policy is the external_display one, imported as the pod
    # publishes it (plain include path outside CocoaPods).
    assert '#import <external_display/NeoExternalDisplayLayout.h>' in header and '#import "NeoExternalDisplayLayout.h"' in header, \
        'the DOL header imports the global policy header'
    for call in ('return NeoExternalDisplayScale(screen, source, DOLExternalDisplayGlobalMode(mode));',
                 'return NeoExternalDisplayFrame(screen, source, DOLExternalDisplayGlobalMode(mode));'):
        assert call in header, call
    assert 'NeoExternalDisplayEffectiveMode(mode, NeoExternalContentGame)' in header, 'Automatic resolves as the coordinator does'
    # Retired 442 assertion: the 16/9 and 4/3 arithmetic lived here; it now
    # lives only in NeoExternalDisplayLayout.h (external_display_test.py keeps
    # it) and a copy here could drift from what the coordinator applies.
    assert '16.0 / 9.0' not in stripped and '4.0 / 3.0' not in stripped, 'no second copy of the placement arithmetic'
    assert 'DOLExternalDisplayModeFromValue' not in stripped, \
        'the 442 key is parsed by NeoExternalDisplayPreferences (legacy fallback), not here'


def adapter_contracts() -> None:
    header = (CLASSES / 'DolphinExternalDisplay.h').read_text(encoding='utf-8')
    implementation = (CLASSES / 'DolphinExternalDisplay.mm').read_text(encoding='utf-8')
    stripped = code(implementation)
    assert '@interface DolphinExternalDisplay : NSObject <NeoExternalRenderHost>' in header, 'the adapter is the render host'
    assert '#import <external_display/NeoExternalRenderHost.h>' in header, 'protocol imported from the pod'
    assert '- (BOOL)fixedDrawable { return YES; }' in implementation, 'Dolphin sized the drawable: transform only'
    for token in ('UIView* renderView;', 'UIView* placeholderView;'):
        assert token in implementation, token
    start = method_body(implementation, '- (void)start {')
    stop = method_body(implementation, '- (void)stop {')
    assert '[NeoExternalDisplayCoordinator.shared attachRenderHost:self];' in start, 'start attaches the host'
    assert '[NeoExternalDisplayCoordinator.shared detachRenderHost:self];' in stop, 'stop detaches the host'
    assert start.index('self.started = YES;') < start.index('attachRenderHost:') and 'if (self.started) return;' in start, 'attach once'
    assert stop.index('self.started = NO;') < stop.index('detachRenderHost:') and 'if (!self.started) return;' in stop, 'detach once'
    assert '[NeoExternalDisplayCoordinator.shared refresh];' in method_body(implementation, '- (void)refresh {')
    changed = method_body(implementation, '- (void)externalDisplayDidChange:(BOOL)active {')
    assert 'self.active = active;' in changed and 'self.stateChanged(active)' in changed, 'the session hint follows the coordinator'
    # Retired 442 assertions (autoResizeDrawable = NO, CGAffineTransformMakeScale,
    # insertSubview:render atIndex:0, UIScreenDidConnect/Disconnect and the
    # Dolphin notification): the adapter owns no window, screen, transform or
    # observer any more; external_display_test.py asserts them on the coordinator.
    for forbidden in ('UIScreen', 'UIWindow', 'CGAffineTransform', 'insertSubview', 'addObserver', 'NSNotificationCenter',
                      'autoResizeDrawable', 'contentScaleFactor', 'ResizeSurface', 'drawableSize', 'windowFactory', 'externalScreens'):
        assert forbidden not in stripped, f'adapter: {forbidden} belongs to the coordinator'
    # The global preference is read through the pod (442 key as read-only fallback), never written here.
    preference = method_body(implementation, 'DOLExternalDisplayMode DOLExternalDisplayPreference(void) {')
    assert 'NeoExternalDisplayPreferences.enabled' in preference and 'DOLExternalDisplayModeFromGlobal(NeoExternalDisplayPreferences.mode)' in preference
    for name in ('DolphinExternalDisplay.h', 'DolphinExternalDisplay.mm', 'DolphinFramePacing.mm', 'DolphinInternalBridgePlugin.mm'):
        text = (CLASSES / name).read_text(encoding='utf-8')
        assert LEGACY_KEY not in text and 'DOLExternalDisplayModeKey' not in text and 'DOLExternalDisplayChangedNotification' not in text, \
            f'{name}: the Build 442 Dolphin key is read by NeoExternalDisplayPreferences only and never rewritten'


def host_contracts() -> None:
    host = (CLASSES / 'DolphinInternalBridgePlugin.mm').read_text(encoding='utf-8')
    assert '[container addSubview:_metalView]' in host and 'self.view = container' in host, 'the Metal view is a movable subview'
    assert host.index('[self.dolphinController.externalDisplay stop]') < host.index('[self.dolphinController.framePacing stop]'), \
        'the Metal view returns to the iPhone before the core shuts down'
    launch = host[host.index('@"launch.authorized"'):host.index('[self startRunningMonitor];')]
    assert 'initWithRenderView:controller.metalView placeholder:controller.view' in launch, 'render view and placeholder of the host'
    assert launch.index('controller.externalDisplay = external;') < launch.index('[external start];'), 'attached after every launch gate'
    assert 'attachRenderHost' not in code(host) and 'NeoExternalDisplayCoordinator' not in code(host), 'the plugin goes through the adapter'
    prepare = method_body(host, '- (void)prepareSessionForStop {')
    assert prepare.index('[self.dolphinController.externalDisplay stop];') < prepare.index('[self.dolphinController.framePacing stop];')
    cleanup = method_body(host, '- (void)cleanupSharedResourcesAndUI {')
    assert '[controller.externalDisplay stop];' in cleanup, 'a stop that skipped prepare still detaches'


def display_row_contracts() -> None:
    pacing = (CLASSES / 'DolphinFramePacing.mm').read_text(encoding='utf-8')
    assert '#import <external_display/NeoExternalDisplayPreferences.h>' in pacing, 'the row reads the global preference'
    chooser = method_body(pacing, '- (void)chooseExternalDisplay:(UIView*)cell {')
    for token in ('[NeoExternalDisplayPreferences storeEnabled:NO]', 'storeMode:(NeoExternalDisplayMode)mode',
                  '[NeoExternalDisplayPreferences storeEnabled:YES]', '@"externalSaveFailed"',
                  '@[@"externalOff",@"externalAutomatic",@"externalFit",@"externalFill",@"externalOriginal"]'):
        assert token in chooser, token
    assert 'setObject' not in chooser and 'NSUserDefaults' not in chooser, 'the row writes through the pod (read back, notified)'
    assert '[self chooseExternalDisplay:cell]' in method_body(pacing, '- (void)tableView:(UITableView*)table didSelectRowAtIndexPath:(NSIndexPath*)path {')
    name = method_body(pacing, '- (NSString*)externalModeName {')
    assert 'NeoExternalDisplayPreferences.enabled' in name and 'NeoExternalDisplayPreferences.mode' in name
    summary = method_body(pacing, '- (NSDictionary*)summary {')
    for key in ('externalDisplayMode', 'externalDisplayEnabled', 'externalDisplayGlobalMode', 'externalDisplayActive'):
        assert f'@"{key}"' in summary, key
    labels = (CLASSES / 'DolphinPacingLabels.h').read_text(encoding='utf-8')
    languages = {}
    for line in labels.splitlines():
        match = re.match(r'@"(\w+)": @\{(.*)\},?$', line)
        if match:
            languages[match.group(1)] = dict(re.findall(r'@"(\w+)": @"((?:[^"\\]|\\.)*)"', match.group(2)))
    assert set(languages) == {'en', 'es', 'ru', 'zh', 'zh_Hant', 'pt', 'fr', 'de', 'it', 'id', 'ja', 'ko'}, sorted(languages)
    for key in ('external', 'externalOff', 'externalAutomatic', 'externalFit', 'externalFill', 'externalOriginal', 'externalHelp',
                'externalActive', 'externalNone', 'externalSaveFailed'):
        for language, values in languages.items():
            assert values.get(key), f'{language}: {key}'
            if language != 'en':
                assert values[key] != languages['en'][key], f'{language}: {key} is not the English text'
    assert languages['zh_Hant']['externalOriginal'] != languages['zh']['externalOriginal'], 'traditional Chinese is its own catalogue'


def dependency_contracts() -> None:
    podspec = (ROOT / 'packages/dolphin_internal_bridge/ios/dolphin_internal_bridge.podspec').read_text(encoding='utf-8')
    assert "s.dependency 'external_display'" in podspec, 'the bridge depends on the external display pod'
    assert "'Classes/DolphinExternalDisplayLayout.h'" in podspec and "'Classes/DolphinExternalDisplay.h'" in podspec, 'adapter headers stay private'
    public = external_public_headers()
    for path in sorted(CLASSES.glob('*')):
        if path.suffix not in {'.h', '.mm', '.m'}:
            continue
        for name in re.findall(r'#import <external_display/([^>]+)>', path.read_text(encoding='utf-8')):
            assert name in public, f'{path.name} imports <external_display/{name}>, which the pod does not publish'
        imported = re.findall(r'#import "(NeoExternal\w+\.h)"', path.read_text(encoding='utf-8'))
        for name in imported:
            assert f'#import <external_display/{name}>' in path.read_text(encoding='utf-8'), \
                f'{path.name}: the plain import of {name} is only the fallback of the pod import'


def execute_policy() -> None:
    if platform.system() != 'Darwin' or not shutil.which('clang++'):
        print('SKIP: external display placement execution requires macOS Foundation/CoreGraphics; source contracts checked')
        return
    with tempfile.TemporaryDirectory() as folder:
        include = stage_external_display(Path(folder))
        binary = Path(folder) / 'external-display'
        subprocess.run(['clang++', '-std=c++20', '-fobjc-arc', '-I' + str(CLASSES), '-I' + str(include),
                        str(ROOT / 'test/dolphin_external_display_test.mm'),
                        '-framework', 'Foundation', '-framework', 'CoreGraphics', '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    layout_contracts()
    adapter_contracts()
    host_contracts()
    display_row_contracts()
    dependency_contracts()
    print('Dolphin external display adapter source contracts: OK', flush=True)
    execute_policy()

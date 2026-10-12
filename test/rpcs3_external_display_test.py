#!/usr/bin/env python3
"""Source contracts of the RPCS3 external-display adoption (Build 447,
docs/external-display-universal.md § 5, row RPCS3).

The game view controller now has a black container as its root view and the
RPCS3MetalView as the container's subview at index 0, below the touch
controls, the action rail and the performance overlay; `metalLayer` returns
the subview's layer. The bridge exposes that Metal view to the external
display pod through a small NeoExternalRenderHost adapter
(RPCS3ExternalRenderHost, fixed drawable: the coordinator keeps the view's
iPhone bounds and scale and maps it to the TV with a transform only), attaches
it right after the game view is presented with a proven Metal surface, asks
the coordinator to destroy the TV menu's second Flutter engine at that moment
(memory for RPCS3 and NeoSwap), and detaches it on the main thread before any
session stop reaches the Core. Because the coordinator recreates that engine
as soon as the host detaches, the bridge holds the coordinator's suspension
(window hidden, iOS mirrors the iPhone) from before the detach until the Core
has stopped and the game view is dismissed, so no Flutter engine boots while
the Core still owns its memory. The Core ABI, the Core calls and the NeoSwap
bridge code are untouched: their lines are compared with the committed
version (git) and with the identity pinned at the Build 446 baseline.

Native code cannot run on Linux; the window lifecycle itself is the
coordinator's and is exercised by the external_display tests. No device claim.

    python3 -I test/rpcs3_external_display_test.py
    python3 -I test/rpcs3_external_display_test.py --print-pins   # identities
"""
from pathlib import Path
import hashlib
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = 'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm'
PODSPEC = 'packages/rpcs3_internal_bridge/ios/rpcs3_internal_bridge.podspec'
EXTERNAL = ROOT / 'packages/external_display/ios'
EXTERNAL_CLASSES = EXTERNAL / 'Classes'
EXTERNAL_POD = 'external_display'
LAUNCH_START = 'if ([call.method isEqualToString:@"launchGame"])'
LAUNCH_END = 'if ([call.method isEqualToString:@"isSessionActive"])'
SURFACE_GUARD = 'if (!controller || !controller.metalLayer.device)'
ATTACH_CALL = '[self attachExternalDisplayForController:controller];'

# Files whose committed content must be byte-identical to the working tree:
# the Core ABI, the input controller (controls untouched) and the NeoSwap
# usage policy. The adoption only restructures the view hierarchy of the
# bridge and adds the adapter around it.
UNTOUCHED_FILES = (
    'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3CoreABI.h',
    'packages/rpcs3_internal_bridge/ios/Classes/RPCS3GameInputController.h',
    'packages/rpcs3_internal_bridge/ios/Classes/RPCS3GameInputController.mm',
    'packages/rpcs3_internal_bridge/ios/Classes/NeoSwapUsagePolicy.h',
)

# Every line of the bridge that names NeoSwap, the Core ABI (`_api.`,
# `rpcs3_ios_`, `LOAD(`), the structs handed to the Core (`options.`,
# `surface.`), the dlopen/dlsym binding or the boot wrapper. Their ordered
# sequence is the identity of the Core/NeoSwap contract of the bridge.
PROTECTED_LINE = re.compile(
    r'neoswap|NeoSwap|NEOSWAP|_api\.|rpcs3_ios_|\bLOAD\(|dlsym\(|dlopen\(|dlclose\(|kExpectedAbi|'
    r'\boptions\.|\bsurface\.|'
    r'bootTitleForCore|RPCS3SampleNeoSwapGuestStats|RPCS3ProcessFootprintBytes|RPCS3ProcessResidentBytes')

# Identities at the Build 446 baseline of this bridge (the committed version
# before the Build 447 adoption). A NeoSwap or Core cycle that changes these
# lines on purpose updates the pins in its own review; the adoption never
# does. `--print-pins` prints the current values.
PINNED_IDENTITIES = {
    'protected_lines': '68df4b229a702aeea1a908fcf3808c7a009a76d3e9b10b91be9223859e00e8fa',
    'loadCoreWithExpandedJit': '1053076ac8a5d10de9ae88aa4598d732d9eb11925516eb91c6182e607cf833b1',
    'bootTitleForCore': '60749c2928bf7725d1690fb0b8a53a8f9e1c9d1272be6a7ac9fcdde98eea20c4',
}


def require(condition, message: str) -> None:
    if not condition:
        raise SystemExit(f'FAIL rpcs3_external_display_test: {message}')


def code(text: str) -> str:
    """Source without comments (prose must not satisfy a contract)."""
    text = re.sub(r'/\*.*?\*/', ' ', text, flags=re.S)
    return re.sub(r'//[^\n]*', ' ', text)


def method_body(source: str, signature: str) -> str:
    """From `signature` to the next method or @-directive; the last method of
    an implementation slice runs to the end of the slice."""
    require(source.count(signature) == 1, f'{signature!r} appears exactly once')
    start = source.index(signature)
    end = re.search(r'\n[-+@]', source[start + len(signature):])
    if end is None:
        return source[start:]
    return source[start:start + len(signature) + end.start()]


def implementation_body(source: str, name: str) -> str:
    marker = f'@implementation {name}\n'
    require(source.count(marker) == 1, f'{marker.strip()!r} appears exactly once')
    start = source.index(marker)
    return source[start:source.index('\n@end', start)]


def committed(path: str):
    """The committed content of `path`, or None when git is unavailable."""
    try:
        result = subprocess.run(['git', '-C', str(ROOT), 'show', f'HEAD:{path}'],
                                capture_output=True, check=False)
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.decode('utf-8')


def protected_lines(text: str) -> list:
    """The code lines (comments stripped: the adoption's own prose may name
    NeoSwap, its code never touches it) naming NeoSwap or the Core ABI."""
    return [line for line in code(text).splitlines() if PROTECTED_LINE.search(line)]


def identities(text: str) -> dict:
    load = method_body(text, '- (BOOL)loadCoreWithExpandedJit:(BOOL)expanded error:(NSString**)error {')
    boot = method_body(text, '- (rpcs3_ios_status)bootTitleForCore:(const char*)title savestate:(const char*)identifier {')
    return {
        'protected_lines': hashlib.sha256('\n'.join(protected_lines(text)).encode('utf-8')).hexdigest(),
        'loadCoreWithExpandedJit': hashlib.sha256(load.encode('utf-8')).hexdigest(),
        'bootTitleForCore': hashlib.sha256(boot.encode('utf-8')).hexdigest(),
    }


def external_public_headers() -> list:
    """The headers the external_display pod publishes (public_header_files):
    the only ones a bridge can import as <external_display/Name.h>."""
    podspec = (EXTERNAL / f'{EXTERNAL_POD}.podspec').read_text(encoding='utf-8')
    match = re.search(r"public_header_files\s*=\s*((?:'[^']*'\s*,?\s*)+)", podspec)
    require(match is not None, 'external_display.podspec declares public_header_files')
    names = [Path(name).name for name in re.findall(r"'([^']*)'", match.group(1))]
    require(bool(names), 'external_display publishes at least one header')
    return names


def view_controller_contracts(plugin: str) -> None:
    stripped = code(plugin)
    require('+ (Class)layerClass { return CAMetalLayer.class; }' in implementation_body(plugin, 'RPCS3MetalView'),
            'RPCS3MetalView keeps its CAMetalLayer')
    interface = plugin[plugin.index('@interface RPCS3GameViewController : UIViewController'):]
    interface = interface[:interface.index('@end')]
    require('@property(nonatomic, strong) RPCS3MetalView* metalView;' in interface,
            'the controller owns the Metal view as a subview')
    require('@property(nonatomic, readonly) CAMetalLayer* metalLayer;' in interface, 'metalLayer stays the Core surface')

    load = method_body(plugin, '- (void)loadView {')
    load_code = code(load)
    require('UIView* view = [[UIView alloc] initWithFrame:UIScreen.mainScreen.bounds];' in load,
            'the root view is a plain container')
    require('view.backgroundColor = UIColor.blackColor;' in load, 'the container is black')
    require('view.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;' in load,
            'the container follows the phone')
    require('RPCS3MetalView* metal = [[RPCS3MetalView alloc] initWithFrame:view.bounds];' in load,
            'the Metal view fills the container')
    require('metal.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;' in load,
            'the Metal view keeps the container size while on the phone')
    require('CAMetalLayer* layer = (CAMetalLayer*)metal.layer;' in load, 'the Metal layer is the subview layer')
    for token in ('layer.device = MTLCreateSystemDefaultDevice();', 'layer.pixelFormat = MTLPixelFormatBGRA8Unorm;',
                  'layer.framebufferOnly = NO;', 'layer.contentsScale = UIScreen.mainScreen.scale;'):
        require(token in load, f'Metal layer configuration kept: {token}')
    require('[view insertSubview:metal atIndex:0];' in load, 'the Metal view is the subview at index 0')
    require('self.metalView = metal;' in load and 'self.view = view;' in load, 'container root, Metal subview')
    require('(CAMetalLayer*)view.layer' not in load_code and 'RPCS3MetalView* view' not in load_code,
            'the root view is no longer the Metal view')
    # Controls above the Metal view: added to the container after it.
    insert = load.index('[view insertSubview:metal atIndex:0];')
    for control in ('[view addSubview:menu];', '[view addSubview:performance];', '[view addSubview:self.performanceOverlay];'):
        require(control in load and load.index(control) > insert, f'{control} is above the Metal view')
    require('self.view = view;' in load and load.index('self.view = view;') > insert, 'the hierarchy is built before it becomes the root')

    require('- (CAMetalLayer*)metalLayer { return (CAMetalLayer*)self.metalView.layer; }' in plugin,
            'metalLayer returns the layer of the subview')
    require('(CAMetalLayer*)self.view.layer' not in stripped, 'no cast of the container layer')
    layout = method_body(plugin, '- (void)viewDidLayoutSubviews {')
    for token in ('[self.view bringSubviewToFront:self.performanceOverlay];', '[self.view bringSubviewToFront:self.menuButton];',
                  '[self.view bringSubviewToFront:self.performanceButton];'):
        require(token in layout, f'the action rail stays above the pad and the returned Metal view: {token}')
    require('layoutControlsInBounds:self.view.bounds safeAreaInsets:self.view.safeAreaInsets' in layout,
            'the controls are laid out in the container')


def adapter_contracts(plugin: str) -> None:
    require('@interface RPCS3ExternalRenderHost : NSObject <NeoExternalRenderHost>' in plugin,
            'the adapter is the render host')
    extension = plugin[plugin.index('@interface RPCS3ExternalRenderHost ()'):]
    extension = extension[:extension.index('@end')]
    for token in ('UIView* renderView;', 'UIView* placeholderView;'):
        require(token in extension, f'adapter property: {token}')
    body = implementation_body(plugin, 'RPCS3ExternalRenderHost')
    stripped = code(body)
    require('- (BOOL)fixedDrawable { return YES; }' in body, 'RPCS3 sized the drawable: transform only')
    init = method_body(body, '- (instancetype)initWithRenderView:(UIView*)render placeholder:(UIView*)placeholder {')
    require('_renderView = render;' in init and '_placeholderView = placeholder;' in init, 'render view and placeholder of the host')
    changed = method_body(body, '- (void)externalDisplayDidChange:(BOOL)active {')
    require('RPCS3Diagnostic(@"external_display"' in changed, 'the move is written to the device diagnostics')
    # The coordinator owns the window, screen, transform, scale and observers
    # (test/external_display_test.py); the adapter has none of them.
    for forbidden in ('UIScreen', 'UIWindow', 'CGAffineTransform', 'insertSubview', 'addObserver', 'NSNotificationCenter',
                      'autoResizeDrawable', 'contentScaleFactor', 'drawableSize', 'windowFactory', 'makeKeyAndVisible'):
        require(forbidden not in stripped, f'adapter: {forbidden} belongs to the coordinator')
    require('makeKeyAndVisible' not in code(plugin) and 'CGAffineTransform' not in code(plugin),
            'the bridge never builds the TV window or the transform')


def attach_contracts(plugin: str) -> None:
    stripped = code(plugin)
    attach = method_body(plugin, '- (void)attachExternalDisplayForController:(RPCS3GameViewController*)controller {')
    require('if (!NSThread.isMainThread) {' in attach and 'dispatch_sync(dispatch_get_main_queue()' in attach,
            'attach runs on the main thread (the coordinator asserts it)')
    require('controller != self.gameController' in attach, 'only the presented session attaches')
    require('[[RPCS3ExternalRenderHost alloc] initWithRenderView:controller.metalView placeholder:controller.view]' in attach,
            'render view = the Metal subview, placeholder = the container')
    require('self.externalRenderHost = host;' in attach, 'the bridge keeps the adapter for the detach')
    destroy = '[coordinator destroyMenuEngineForMemory];'
    attach_host = '[coordinator attachRenderHost:host];'
    require(destroy in attach and attach_host in attach, 'destroyMenuEngineForMemory and attachRenderHost')
    require(attach.index(destroy) < attach.index(attach_host), 'the TV menu engine is destroyed before the game takes the screen')
    require(stripped.count('attachRenderHost:') == 1 and stripped.count('destroyMenuEngineForMemory') == 1,
            'the coordinator is attached from the adapter path only')

    launch = plugin[plugin.index(LAUNCH_START):plugin.index(LAUNCH_END)]
    require(launch.count(ATTACH_CALL) == 1, 'one attach per launch')
    guard = launch.index(SURFACE_GUARD)
    surface_read = launch.index('UIScreen* screen = controller.view.window.screen ?: UIScreen.mainScreen;')
    attach_call = launch.index(ATTACH_CALL)
    boot = launch.index('dispatch_async(_runtimeQueue, ^{')
    set_surface = launch.index('self->_api.set_display_surface(&surface)')
    require(launch.index('[root presentViewController:controller animated:NO completion:nil];') < guard,
            'the game view is presented before the surface is checked')
    require(guard < surface_read < attach_call < boot < set_surface,
            'attach after the presentation succeeded and the phone surface was read, before the Core boots')
    require('RPCS3_DISPLAY_SURFACE_FAILED' in launch[guard:attach_call] and
            '[controller dismissViewControllerAnimated:NO completion:nil];' in launch[guard:attach_call],
            'a failed surface is dismissed without any attach')
    require('attachExternalDisplayForController' not in launch[:guard], 'nothing attaches before the surface is proven')
    # The surface the Core receives is the phone's: size of the container,
    # scale and refresh rate of its window's screen (the container never moves).
    for token in ('CGSize size = controller.view.bounds.size;', 'CGFloat scale = screen.scale;',
                  'float refreshRate = (float)screen.maximumFramesPerSecond;',
                  'surface.metal_layer = (__bridge void*)controller.metalLayer;'):
        require(token in launch, f'phone surface kept: {token}')
    require('initWithHostView:controller.view api:&self->_api' in launch, 'the controls are hosted by the container')


def detach_contracts(plugin: str) -> None:
    stripped = code(plugin)
    detach = method_body(plugin, '- (void)detachExternalDisplay {')
    detach_host = '[NeoExternalDisplayCoordinator.shared detachRenderHost:host];'
    require(detach_host in detach and 'self.externalRenderHost = nil;' in detach, 'detach releases the adapter')
    require(detach.index('self.externalRenderHost = nil;') < detach.index(detach_host), 'detach once')
    require(stripped.count('detachRenderHost:') == 1, 'the coordinator is detached from the adapter path only')

    stop = method_body(plugin, '- (void)stopAndDismiss:(FlutterResult)result {')
    hop = 'if (!NSThread.isMainThread) {'
    require(hop in stop and '[self stopAndDismiss:result]' in stop, 'a stop requested off the main thread hops there first')
    require('[self detachExternalDisplay];' in stop, 'stopAndDismiss detaches')
    require(stop.index(hop) < stop.index('[self detachExternalDisplay];') < stop.index('dispatch_async(_runtimeQueue, ^{')
            < stop.index('self->_api.stop_emulation()'),
            'the Metal view returns to the iPhone before the Core stops')
    failed = stop[stop.index('if (!ok) {'):stop.index('return; // Keep Metal')]
    require('[self attachExternalDisplayForController:self.gameController];' in failed and
            failed.index('attachExternalDisplayForController') < failed.index('result(@NO)'),
            'a stop the save refused keeps the game on the TV as well')
    require(stop.index('[self detachExternalDisplay];') < stop.index('[controller dismissViewControllerAnimated:NO completion:nil];'),
            'the view is back on the phone before the game view is dismissed')
    # Every dismissal of the game view is either the pre-attach surface
    # failure or the detached stop; no third path lets the view go away
    # while it is on the TV.
    require(stripped.count('[controller dismissViewControllerAnimated:NO completion:nil];') == 2,
            'only the surface failure and stopAndDismiss dismiss the game view')
    # Internal restarts keep the same display surface: no detach, no flicker.
    for signature in ('- (void)performSessionCommand:(NSString*)command',
                      '- (void)performSessionStateAtSlot:(NSInteger)slot'):
        require('detachExternalDisplay' not in method_body(plugin, signature), f'{signature}: same surface, no detach')


def menu_hold_contracts(plugin: str) -> None:
    """The TV menu's second Flutter engine, destroyed at the attach, must
    not boot again while the Core still owns its memory: the coordinator
    recreates it as soon as the host detaches, and the detach precedes the
    Core stop. The bridge holds the coordinator's suspension (nothing of
    NeoStation's on the TV, iOS mirrors the iPhone) from before the detach
    until the Core has stopped and the game view is dismissed, or until the
    game is attached again after a refused stop; internal restarts never
    touch it."""
    stripped = code(plugin)
    hold = method_body(plugin, '- (void)holdExternalMenuWhileCoreStops {')
    release = method_body(plugin, '- (void)releaseExternalMenuAfterCoreStopped {')
    require('[NeoExternalDisplayCoordinator.shared suspendForUnsupportedEngine];' in hold, 'the hold is the coordinator suspension')
    require('[NeoExternalDisplayCoordinator.shared resumeAfterUnsupportedEngine];' in release, 'the release resumes it')
    require(stripped.count('suspendForUnsupportedEngine') == 1 and stripped.count('resumeAfterUnsupportedEngine') == 1,
            'the suspension is driven from the two helpers only')
    hold_call = '[self holdExternalMenuWhileCoreStops];'
    release_call = '[self releaseExternalMenuAfterCoreStopped];'
    require(stripped.count(hold_call) == 1, 'one hold: stopAndDismiss')
    require(stripped.count(release_call) == 2, 'two releases: the refused stop and the completed stop')

    stop = method_body(plugin, '- (void)stopAndDismiss:(FlutterResult)result {')
    detach = stop.index('[self detachExternalDisplay];')
    queue = stop.index('dispatch_async(_runtimeQueue, ^{')
    core_stop = stop.index('self->_api.stop_emulation()')
    require(stop.index('if (!NSThread.isMainThread) {') < stop.index(hold_call) < detach < queue < core_stop,
            'held on the main thread before the detach, which precedes the Core stop')
    failed = stop[stop.index('if (!ok) {'):stop.index('return; // Keep Metal')]
    require(failed.index('[self attachExternalDisplayForController:self.gameController];') < failed.index(release_call)
            < failed.index('result(@NO)'),
            'refused stop: the game is attached again before the hold is released, before the result')
    completed = stop[stop.index('return; // Keep Metal'):]
    dismiss = completed.index('[controller dismissViewControllerAnimated:NO completion:nil];')
    require(completed.index('NeoSwapStorage_EndSession();') < completed.index('self.gameController = nil;') < dismiss
            < completed.index(release_call) < completed.index('if (result) result(@(ok));'),
            'completed stop: released after the Core stopped and the game view was dismissed, before the result')
    for signature in ('- (void)performSessionCommand:(NSString*)command',
                      '- (void)performSessionStateAtSlot:(NSInteger)slot',
                      '- (void)attachExternalDisplayForController:(RPCS3GameViewController*)controller {',
                      '- (void)detachExternalDisplay {'):
        body = method_body(plugin, signature)
        require(hold_call not in body and release_call not in body, f'{signature}: no hold or release of its own')
    launch = plugin[plugin.index(LAUNCH_START):plugin.index(LAUNCH_END)]
    require(hold_call not in launch and release_call not in launch,
            'a launch never holds the menu itself: its failures go through stopAndDismiss')


def dependency_contracts(plugin: str) -> None:
    podspec = (ROOT / PODSPEC).read_text(encoding='utf-8')
    require("s.dependency 'external_display'" in podspec, 'the bridge depends on the external display pod')
    require("s.dependency 'neo_swap'" in podspec, 'the NeoSwap dependency stays')
    require('#import <external_display/NeoExternalDisplayCoordinator.h>' in plugin, 'the coordinator is imported from the pod')
    public = external_public_headers()
    for name in re.findall(r'#import <external_display/([^>]+)>', plugin):
        require(name in public, f'<external_display/{name}> is not published by the pod')
        require((EXTERNAL_CLASSES / name).is_file(), f'{name} exists in the pod')
    require('#import "NeoExternalDisplayCoordinator.h"' not in plugin, 'no plain import that CocoaPods could not resolve')


def untouched_contracts(plugin: str) -> None:
    current = identities(plugin)
    pinned = PINNED_IDENTITIES
    if 'PLACEHOLDER' in pinned.values():
        raise SystemExit('FAIL rpcs3_external_display_test: identities are not pinned (run with --print-pins)')
    for name, value in current.items():
        require(value == pinned[name],
                f'{name}: NeoSwap/Core identity {value} differs from the pinned baseline {pinned[name]} '
                '(a NeoSwap or Core cycle updates the pin in its own review; the external display adoption never does)')
    head = committed(PLUGIN)
    if head is None:
        print('NOTE: git unavailable, NeoSwap/Core lines checked against the pinned identities only', flush=True)
    else:
        require(protected_lines(head) == protected_lines(plugin),
                'the NeoSwap and Core API lines of the bridge are byte-identical to the committed version')
        for name in ('loadCoreWithExpandedJit', 'bootTitleForCore'):
            require(identities(head)[name] == current[name], f'{name} is byte-identical to the committed version')
    for path in UNTOUCHED_FILES:
        text = (ROOT / path).read_text(encoding='utf-8')
        require('NeoExternal' not in text and 'external_display' not in text, f'{path}: not part of the adoption')
        committed_text = committed(path)
        if committed_text is not None:
            require(committed_text == text, f'{path} is byte-identical to the committed version')
    # Everything the external display adds is marked; nothing of it reaches
    # the Core load, the boot wrapper or the NeoSwap bindings.
    for signature in ('- (BOOL)loadCoreWithExpandedJit:(BOOL)expanded error:(NSString**)error {',
                      '- (rpcs3_ios_status)bootTitleForCore:(const char*)title savestate:(const char*)identifier {'):
        body = method_body(plugin, signature)
        require('ExternalDisplay' not in body and 'externalRenderHost' not in body, f'{signature}: untouched by the adoption')


def main() -> None:
    plugin = (ROOT / PLUGIN).read_text(encoding='utf-8')
    if '--print-pins' in sys.argv[1:]:
        head = committed(PLUGIN)
        for label, text in (('working tree', plugin), ('HEAD', head)):
            if text is None:
                continue
            print(f'{label}:')
            for name, value in identities(text).items():
                print(f"    '{name}': '{value}',")
        return
    view_controller_contracts(plugin)
    adapter_contracts(plugin)
    attach_contracts(plugin)
    detach_contracts(plugin)
    menu_hold_contracts(plugin)
    dependency_contracts(plugin)
    untouched_contracts(plugin)
    print('RPCS3 external display adoption source contracts: OK', flush=True)


if __name__ == '__main__':
    main()

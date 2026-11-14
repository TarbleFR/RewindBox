#!/usr/bin/env python3
"""The XeniOS adaptation patch and the XeniaCore build inputs.

Without --upstream: structural checks (every change is behind
XE_NEO_EMBEDDED_CORE, nothing upstream is removed, hooks and facade agree).
With --upstream <checkout of the pinned revision>: also
build-utils/xenia/prepare_source.py --check (pin, upstream API files, patch
applies). docs/xenios-playlist.md § Core adaptation plan.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
XENIA = ROOT / 'build-utils' / 'xenia'
CORE = ROOT / 'packages' / 'xenia_internal_bridge' / 'core'


def fail(message: str) -> None:
    raise SystemExit('xenia core patch: ' + message)


# Built on GitHub's runners, which have no Xcode 27: the two iOS 27 SDK uses
# of xenia-ui-ios (StateReporting, scene accessories) are compiled only when
# the SDK has them. Upstream already calls both under @available(iOS 27.0, *);
# with an iOS 27 SDK every line here is a no-op.
SDK_FILES = ['src/xenia/ui/ios/CMakeLists.txt', 'src/xenia/ui/ios/app/ios_external_display.mm',
             'src/xenia/ui/ios/shared/ios_state_reporting.mm']
SDK_ALLOWED = re.compile(
    r'^(#if __has_include\(<StateReporting/StateReporting\.h>\)|#ifndef XE_NEO_HAS_STATE_REPORTING|'
    r'#define XE_NEO_HAS_STATE_REPORTING 1|#if __IPHONE_OS_VERSION_MAX_ALLOWED >= 270000|#else|#endif|'
    r'  \(void\)title_id;|//.*|#.*|execute_process\(COMMAND xcrun --sdk iphoneos --show-sdk-path|'
    r'  OUTPUT_VARIABLE XE_NEO_IOS_SDK_PATH OUTPUT_STRIP_TRAILING_WHITESPACE\)|'
    r'if\(EXISTS "\$\{XE_NEO_IOS_SDK_PATH\}/System/Library/Frameworks/StateReporting\.framework"\)|'
    r'endif\(\))$')


# The guest frame counter of the host's performance overlay (ABI 3): one weak
# declaration and one guarded call in MetalCommandProcessor::IssueSwap. The
# library is not compiled with XE_NEO_EMBEDDED_CORE, so the weak reference is
# the guard: undefined, it is a no-op outside XeniaCore.
SWAP_HOOK_FILES = ['src/xenia/gpu/metal/metal_command_processor.cc']
SWAP_HOOK_ALLOWED = {
    '// RewindBox embedded Core (build-utils/xenia): counts guest frames for the',
    "// host's performance overlay. Weak: undefined, so a no-op, outside XeniaCore.",
    'extern "C" __attribute__((weak)) void NeoXeniaNotifyGuestSwap(void);',
    '',
    '  if (NeoXeniaNotifyGuestSwap) NeoXeniaNotifyGuestSwap();',
}


# ABI 4: the host's code-region reservation (docs/xenios-playlist.md § Code
# region). XeniOS takes the 512 MB below 8 GB while its process loads; the
# embedded Core is dlopened late, so the host reserves it and this one function,
# after the anonymous namespace of jit_memory_ios.cc, hands it over. Nothing
# upstream changes: the function is unused outside XeniaCore.
JIT_REGION_FILES = ['src/xenia/cpu/backend/jit_memory_ios.cc']
JIT_LIMIT_ADDED = [
    '// RewindBox embedded Core (build-utils/xenia): its JIT tool, the patched',
    '// StikJIT, writes full 64-bit addresses, so XeniaCore lifts this limit. Weak:',
    '// undefined, so the limit above stands, outside XeniaCore. Declared outside',
    '// the anonymous namespace so the reference keeps external linkage.',
    '}  // namespace',
    'extern "C" __attribute__((weak)) uintptr_t NeoXeniaExecuteRegionLimit(void);',
    'namespace {',
    'uintptr_t NeoExecuteRegionLimit() {',
    '  return NeoXeniaExecuteRegionLimit ? NeoXeniaExecuteRegionLimit()',
    '                                    : kExecuteRegionLimit;',
    '}',
    '#define kExecuteRegionLimit NeoExecuteRegionLimit()',
]
JIT_REGION_ADDED = [
    '// RewindBox embedded Core (build-utils/xenia): the host app holds the code',
    '// region from its own launch and hands it over after its late dlopen of this',
    '// Core, when the reservation above found no room. Returns 2 when the Core',
    '// already holds one, 1 when it takes the host\'s, 0 when none is held.',
    'extern "C" int NeoXeniaAdoptExecuteRegion(void* reservation, size_t size) {',
    '  if (execute_region_reservation) {',
    '    return 2;',
    '  }',
    '  const uintptr_t base = reinterpret_cast<uintptr_t>(reservation);',
    '  if (!base || size != kExecuteRegionReserveSize ||',
    '      base + size > kExecuteRegionLimit) {',
    '    return 0;',
    '  }',
    '  execute_region_reservation = static_cast<uint8_t*>(reservation);',
    '  return 1;',
    '}',
    '',
]


# RewindBox's "hide my IP address" (docs/xenios-playlist.md § Online): one weak
# declaration and two guarded blocks in relay::RelayClient. The library is not
# compiled with XE_NEO_EMBEDDED_CORE, so the weak reference is the guard:
# undefined, nothing changes outside XeniaCore. Defined, the client takes no
# direct path (no probe from the player's address) and lists no address in the
# lobby; players reach it through its TURN allocation.
RELAY_HOOK_FILES = ['src/xenia/net/relay_client.cc']
RELAY_HOOK_ADDED = [
    '// RewindBox embedded Core (build-utils/xenia): true while the player keeps',
    '// their address from the other players (RewindBox\'s "hide my IP address"):',
    '// the lobby lists no address of this client, which sends every frame through',
    '// its TURN allocation. Weak: undefined, so false, outside XeniaCore.',
    'extern "C" __attribute__((weak)) bool NeoXeniaRelayOnly(void);',
    '',
    '  // RewindBox embedded Core: no direct path, so no probe from this address.',
    '  if (NeoXeniaRelayOnly && NeoXeniaRelayOnly()) {',
    '    config_.direct_paths = false;',
    '  }',
    '  // RewindBox embedded Core: no address in the lobby; players reach this one',
    '  // through its TURN allocation, which the lobby lists apart ("relay").',
    '  if (!config_.direct_paths && NeoXeniaRelayOnly && NeoXeniaRelayOnly()) {',
    '    return candidates;',
    '  }',
]


def check_relay_hook(patch: str) -> None:
    for name in RELAY_HOOK_FILES:
        hunk = patch.split(f'diff --git a/{name} ', 1)[1].split('\ndiff --git ', 1)[0]
        body = hunk.splitlines()[4:]
        if any(line.startswith('-') for line in body):
            fail(f'{name}: the relay hook removes upstream lines')
        added = [line[1:] for line in body if line.startswith('+')]
        if added != RELAY_HOOK_ADDED:
            fail(f'{name}: not exactly the relay-only hook: {added}')
        # The direct-path switch is the constructor's first statement; the
        # empty list returns before any candidate is added.
        if 'RelayClient::RelayClient(const Mac& mac, const RelayConfig& config)\n     : mac_(mac), config_(config) {\n+' \
                not in hunk:
            fail(f'{name}: the direct-path switch is not the first statement of the constructor')
        if 'std::vector<Endpoint> RelayClient::Candidates() const {\n   std::vector<Endpoint> candidates;\n+' \
                not in hunk:
            fail(f'{name}: the empty list does not open RelayClient::Candidates')


def check_code_region_hook(patch: str) -> None:
    for name in JIT_REGION_FILES:
        hunk = patch.split(f'diff --git a/{name} ', 1)[1].split('\ndiff --git ', 1)[0]
        body = hunk.splitlines()[4:]
        if any(line.startswith('-') for line in body):
            fail(f'{name}: the code-region hooks remove upstream lines')
        added = [line[1:] for line in body if line.startswith('+')]
        if added != JIT_LIMIT_ADDED + JIT_REGION_ADDED:
            fail(f'{name}: not exactly the code-region limit hook and adoption function: {added}')
        # The limit hook follows the 8 GB constant (every later use reads the
        # hook); the adoption function follows the anonymous namespace.
        before_limit = hunk.split('\n+' + JIT_LIMIT_ADDED[0], 1)[0]
        if not before_limit.rstrip().endswith('constexpr uintptr_t kExecuteRegionLimit = uintptr_t(1) << 33;'):
            fail(f'{name}: the limit hook must directly follow kExecuteRegionLimit')
        before_adopt = hunk.split('\n+' + JIT_REGION_ADDED[0], 1)[0]
        if not before_adopt.rstrip().endswith('}  // namespace'):
            fail(f'{name}: the adoption function must follow the anonymous namespace')


def check_swap_hook(patch: str) -> None:
    for name in SWAP_HOOK_FILES:
        hunk = patch.split(f'diff --git a/{name} ', 1)[1].split('\ndiff --git ', 1)[0]
        added = [line[1:] for line in hunk.splitlines()[4:] if line.startswith('+')]
        if any(line.startswith('-') for line in hunk.splitlines()[4:]):
            fail(f'{name}: the swap hook removes upstream lines')
        if set(added) - SWAP_HOOK_ALLOWED or added.count('  if (NeoXeniaNotifyGuestSwap) NeoXeniaNotifyGuestSwap();') != 1:
            fail(f'{name}: not exactly the weak guest-swap hook: {added}')
        context = hunk.split('\n+  if (NeoXeniaNotifyGuestSwap) NeoXeniaNotifyGuestSwap();', 1)[0]
        if not context.rstrip().endswith('SCOPE_profile_cpu_f("gpu");') or \
                'void MetalCommandProcessor::IssueSwap(uint32_t frontbuffer_ptr,' not in context:
            fail(f'{name}: the hook is not the first statement of MetalCommandProcessor::IssueSwap')


def check_sdk_hunks(patch: str) -> None:
    for name in SDK_FILES:
        hunk = patch.split(f'diff --git a/{name} ', 1)[1].split('\ndiff --git ', 1)[0]
        for line in hunk.splitlines()[4:]:
            if line.startswith('-'):
                fail(f'{name}: the SDK adaptation removes upstream lines')
            if line.startswith('+') and not SDK_ALLOWED.match(line[1:]):
                fail(f'{name}: not an SDK guard: {line[1:]!r}')
        added = [line[1:] for line in hunk.splitlines() if line.startswith('+')]
        if name.endswith('.mm') and sum(line.startswith('#if') for line in added) != added.count('#endif'):
            fail(f'{name}: unbalanced SDK guards')


def check_patch() -> None:
    patch = (XENIA / 'rewindbox-core.patch').read_text()
    files = re.findall(r'^diff --git a/(\S+) ', patch, re.M)
    if files != ['cmake/ios/App.cmake', 'src/xenia/app/xenia_main_ios.mm'] + SDK_FILES + SWAP_HOOK_FILES + \
            JIT_REGION_FILES + RELAY_HOOK_FILES:
        fail(f'unexpected patched files {files}')
    check_sdk_hunks(patch)
    check_swap_hook(patch)
    check_code_region_hook(patch)
    check_relay_hook(patch)
    removed = [line for line in patch.splitlines() if line.startswith('-') and not line.startswith('---')]
    if removed:
        fail(f'the patch must only add guarded lines, it removes {removed[:3]}')
    added = [line[1:] for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++')]
    main_hunks = patch.split('diff --git a/src/xenia/app/xenia_main_ios.mm', 1)[1].split('\ndiff --git ', 1)[0]
    opens = len(re.findall(r'^\+#if !?XE_NEO_EMBEDDED_CORE', main_hunks, re.M))
    closes = len(re.findall(r'^\+#endif', main_hunks, re.M))
    if opens == 0 or opens != closes:
        fail(f'unbalanced XE_NEO_EMBEDDED_CORE guards ({opens} #if, {closes} #endif)')
    for needed in ('NeoXeniaApplyHostRoots();', 'NeoXeniaApplyLaunchOverrides();', 'NeoXeniaNotifyTitleLaunched();',
                   'NeoXeniaNotifyKernelReady();',
                   'NeoXeniaCreateInputDriver(window, kZOrderHidInput)',
                   'NeoXeniaCreateEmulatorApp(', 'xe_ios_microphone_start();',
                   'xe_ios_live_social_install(std::move(live_host));'):
        if not any(needed in line for line in added) and needed not in main_hunks:
            fail(f'missing hook or guard: {needed}')
    # The saved config names the container that wrote it: the host's roots are
    # set again right after config::SetupConfig, before the roots are read.
    setup = main_hunks.index('config::SetupConfig(storage_root);')
    roots = main_hunks.index('+  NeoXeniaApplyHostRoots();')
    if not setup < roots < main_hunks.index('std::filesystem::path content_root = cvars::content_root;'):
        fail('NeoXeniaApplyHostRoots must follow config::SetupConfig and precede the content root')
    # Player 1 is signed in once the kernel exists and before the title runs.
    kernel = main_hunks.index('+    NeoXeniaNotifyKernelReady();')
    if not main_hunks.index('XELOGI("iOS: Emulator setup complete");') < kernel < \
            main_hunks.index('+    NeoXeniaNotifyTitleLaunched();'):
        fail('NeoXeniaNotifyKernelReady must follow the emulator setup and precede the title launch')
    if 'include("${NEO_XENIA_ADAPTER_DIR}/core/target.cmake")' not in patch:
        fail('App.cmake does not include the RewindBox target')
    hooks = (CORE / 'neo_xenia_core_hooks.h').read_text()
    facade = (CORE / 'XeniaCore.mm').read_text()
    for symbol in ('NeoXeniaApplyHostRoots', 'NeoXeniaApplyLaunchOverrides', 'NeoXeniaNotifyTitleLaunched',
                   'NeoXeniaNotifyKernelReady', 'NeoXeniaCreateInputDriver', 'NeoXeniaCreateEmulatorApp'):
        if symbol not in hooks:
            fail(f'{symbol} not declared in neo_xenia_core_hooks.h')
    if 'extern "C" void NeoXeniaNotifyGuestSwap(void);' not in hooks:
        fail('NeoXeniaNotifyGuestSwap is not declared extern "C" in neo_xenia_core_hooks.h')
    if 'extern "C" uintptr_t NeoXeniaExecuteRegionLimit(void);' not in hooks or \
            'extern "C" uintptr_t NeoXeniaExecuteRegionLimit(void) { return uintptr_t(1) << 47; }' not in facade:
        fail('the code-region limit hook is not declared and defined by the facade')
    if 'extern "C" int NeoXeniaAdoptExecuteRegion(void* reservation, size_t size);' not in hooks:
        fail('NeoXeniaAdoptExecuteRegion is not declared extern "C" in neo_xenia_core_hooks.h')
    if 'extern "C" bool NeoXeniaRelayOnly(void);' not in hooks or \
            'extern "C" bool NeoXeniaRelayOnly(void) {' not in facade:
        fail('the relay-only hook is not declared and defined by the facade')
    for symbol in ('void NeoXeniaApplyHostRoots() {', 'void NeoXeniaApplyLaunchOverrides()', 'void NeoXeniaNotifyTitleLaunched()',
                   'void NeoXeniaNotifyKernelReady() {',
                   'NeoXeniaCreateInputDriver(xe::ui::Window* window',
                   'extern "C" void NeoXeniaNotifyGuestSwap(void) {', 'int GetStats(NeoXeniaStats* out) {'):
        if symbol not in facade:
            fail(f'{symbol} not defined by XeniaCore.mm')
    # XeniOS binds guest slots only to enumerated devices: the host pad must be one.
    driver = (CORE / 'XeniaCoreInput.h').read_text()
    if 'std::vector<xe::hid::InputDeviceInfo> EnumerateDevices() override' not in driver or \
            'info.auto_bind = true;' not in driver or 'info.preferred_slot = 0;' not in driver:
        fail('NeoXeniaInputDriver does not enumerate the host pad for slot 0')
    if (CORE / 'exports.txt').read_text().split() != ['_NeoXenia_GetAPI']:
        fail('exports.txt must list only _NeoXenia_GetAPI')
    managed = re.search(r'kManagedKeys\[\] = \{(.*?)\};', facade, re.S).group(1)
    facade_keys = set(re.findall(r'"([a-z0-9_A-Z]+)"', managed))
    plugin = (ROOT / 'packages/xenia_internal_bridge/ios/Classes/XeniaInternalBridgePlugin.mm').read_text()
    bridge_keys = set(re.findall(r'@"([a-zA-Z0-9_]+)"', re.search(r'setWithArray:@\[(.*?)\]', plugin, re.S).group(1)))
    if facade_keys != bridge_keys:
        fail(f'facade and bridge accept different keys: {sorted(facade_keys ^ bridge_keys)}')
    target = (CORE / 'target.cmake').read_text()
    for needed in ('XE_NEO_EMBEDDED_CORE=1', '-exported_symbols_list', 'xenia-third-party-metal-shader-converter',
                   'FRAMEWORK TRUE', '"-fobjc-arc"', 'xe_target_defaults(XeniaCore)'):
        if needed not in target:
            fail(f'target.cmake lacks {needed}')
    # ABI 2: the JIT decision comes from the Core (IOSJitMemory).
    abi = (ROOT / 'packages/xenia_internal_bridge/ios/Classes/XeniaCoreABI.h').read_text()
    for needed in ('NEO_XENIA_JIT_NEEDS_TOOL', 'NEO_XENIA_JIT_TOOL_ATTACHED', 'uint32_t (*jit_state)(void);',
                   '#define NEO_XENIA_ABI_VERSION 4u', 'int (*get_stats)(NeoXeniaStats* out);',
                   'int (*adopt_code_region)(void* reservation, size_t size);',
                   '#define NEO_XENIA_JIT_CODE_REGION_HELD (1u << 4)',
                   '#define NEO_XENIA_CODE_REGION_SIZE ((size_t)1 << 29)',
                   '#define NEO_XENIA_CODE_REGION_LIMIT ((uintptr_t)1 << 33)'):
        if needed not in abi:
            fail(f'XeniaCoreABI.h lacks {needed}')
    for needed in ('IOSJitMemory::NeedsAttachedTool()', 'IOSJitMemory::ToolAttached()', 'JitState,',
                   '    GetStats,\n    AdoptCodeRegion,\n};', 'g_guest_frames.store(0, std::memory_order_relaxed);',
                   'NeoXeniaAdoptExecuteRegion(reservation, size)', 'IOSJitMemory::kExecuteRegionReserveSize',
                   'state |= NEO_XENIA_JIT_CODE_REGION_HELD;', 'hooks.note_fatal_error = NoteFatalError;',
                   'xe::SetIOSSystemHooks(hooks);', '"/last-fatal.txt"'):
        if needed not in facade:
            fail(f'XeniaCore.mm lacks {needed}')
    # The refusal comes before boot: a broker-path title without a held code
    # region would end in a FatalError that closes RewindBox.
    validate = facade.split('int ValidateJit(', 1)[1].split('\nint Boot(', 1)[0]
    if '!(state & NEO_XENIA_JIT_CODE_REGION_HELD)' not in validate:
        fail('ValidateJit does not refuse a title without a held code region')
    # Dedicated helper: derived from the ARMSX2 reference, no drift.
    subprocess.run([sys.executable, str(ROOT / 'tools/xenia/derive_jit_helper.py'), '--check'], check=True)
    # Bridge order: nonce probe before the Core runs, Core-issued detach
    # confirmed after boot, never the other way round.
    order = [plugin.index(token) for token in (
        'XeniaJitHasActiveCoreHandshake()', 'XeniaJitConfirmCoreLoadHandoff()',
        'api->prepare(&configuration', 'api->validate_jit(', 'api->boot(', 'XeniaJitWaitForDetach(')]
    if order != sorted(order):
        fail('the bridge must probe, prepare, validate, boot, then wait for the detach')
    if '[XeniaJitBridgePlugin registerWithRegistrar:registrar];' not in plugin:
        fail('the dedicated JIT channel is not registered')
    pin = json.loads((XENIA / 'source.json').read_text())
    if pin['abi_version'] != 4 or not re.fullmatch('[0-9a-f]{40}', pin['revision']):
        fail('source.json pin is malformed')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--upstream', type=Path)
    args = parser.parse_args()
    check_patch()
    if args.upstream:
        subprocess.run([sys.executable, str(XENIA / 'prepare_source.py'), str(args.upstream), '--check'],
                       check=True)
    print('xenia core patch: OK' + (' (applies to the pinned checkout)' if args.upstream else ''))


if __name__ == '__main__':
    main()

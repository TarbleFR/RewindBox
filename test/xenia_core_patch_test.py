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
    if files != ['cmake/ios/App.cmake', 'src/xenia/app/xenia_main_ios.mm'] + SDK_FILES:
        fail(f'unexpected patched files {files}')
    check_sdk_hunks(patch)
    removed = [line for line in patch.splitlines() if line.startswith('-') and not line.startswith('---')]
    if removed:
        fail(f'the patch must only add guarded lines, it removes {removed[:3]}')
    added = [line[1:] for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++')]
    main_hunks = patch.split('diff --git a/src/xenia/app/xenia_main_ios.mm', 1)[1].split('\ndiff --git ', 1)[0]
    opens = len(re.findall(r'^\+#if !?XE_NEO_EMBEDDED_CORE', main_hunks, re.M))
    closes = len(re.findall(r'^\+#endif', main_hunks, re.M))
    if opens == 0 or opens != closes:
        fail(f'unbalanced XE_NEO_EMBEDDED_CORE guards ({opens} #if, {closes} #endif)')
    for needed in ('NeoXeniaApplyLaunchOverrides();', 'NeoXeniaNotifyTitleLaunched();',
                   'NeoXeniaCreateInputDriver(window, kZOrderHidInput)',
                   'NeoXeniaCreateEmulatorApp(', 'xe_ios_microphone_start();',
                   'xe_ios_live_social_install(std::move(live_host));'):
        if not any(needed in line for line in added) and needed not in main_hunks:
            fail(f'missing hook or guard: {needed}')
    if 'include("${NEO_XENIA_ADAPTER_DIR}/core/target.cmake")' not in patch:
        fail('App.cmake does not include the RewindBox target')
    hooks = (CORE / 'neo_xenia_core_hooks.h').read_text()
    facade = (CORE / 'XeniaCore.mm').read_text()
    for symbol in ('NeoXeniaApplyLaunchOverrides', 'NeoXeniaNotifyTitleLaunched',
                   'NeoXeniaCreateInputDriver', 'NeoXeniaCreateEmulatorApp'):
        if symbol not in hooks:
            fail(f'{symbol} not declared in neo_xenia_core_hooks.h')
    for symbol in ('void NeoXeniaApplyLaunchOverrides()', 'void NeoXeniaNotifyTitleLaunched()',
                   'NeoXeniaCreateInputDriver(xe::ui::Window* window'):
        if symbol not in facade:
            fail(f'{symbol} not defined by XeniaCore.mm')
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
    for needed in ('NEO_XENIA_JIT_NEEDS_TOOL', 'NEO_XENIA_JIT_TOOL_ATTACHED', 'uint32_t (*jit_state)(void);'):
        if needed not in abi:
            fail(f'XeniaCoreABI.h lacks {needed}')
    for needed in ('IOSJitMemory::NeedsAttachedTool()', 'IOSJitMemory::ToolAttached()', 'JitState,'):
        if needed not in facade:
            fail(f'XeniaCore.mm lacks {needed}')
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
    if pin['abi_version'] != 2 or not re.fullmatch('[0-9a-f]{40}', pin['revision']):
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

"""Build 497: continuously owned PSP memory and the final verified HD catalogue.

Only the PSP memory contract and its core change. Reuse unrelated successful
496 delivery evidence, require the exact new native/core/session proof, and
retain all packaging, signature and payload integrity gates.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import psprelaunch496_delivery as previous

base = previous.base
DELIVERED = 'b332bc2e59e4f44d4e820aa4879520a058bfd76b'
DELIVERED_RUN = 39445610738
CATALOGUE = '730e065ffb5d1b66735f6e440cbdbedc886c8163'
TESTED = 'ab9361c29f7c9ab769c4263dd8b7427fc4f4c036'
TESTED_RUN = 39455712245
PRODUCT_PATHS = ['lib', 'assets', 'packages', 'native', 'ios', 'pubspec.yaml', 'pubspec.lock', 'build-utils/libretro']
MEMORY = 'packages/libretro_internal_bridge/ios/Classes/LibretroAddressSpace.m'
INDEX = 'native/textures/catalogue/manifest.json.gz'
BUNDLED = 'packages/neo_texture_catalog/ios/Resources/manifest.json.gz'
PRODUCT = {MEMORY, INDEX, BUNDLED, 'packages/libretro_internal_bridge/ios/Classes/LibretroAddressSpace.h',
           'packages/libretro_internal_bridge/ios/Classes/LibretroSession.m',
           'packages/libretro_internal_bridge/ios/Classes/NeoStationPSPMemory.h',
           'native/ppsspp/managed-memory.patch', 'native/ppsspp/source.json'}
DELIVERY_ONLY = {'.github/diagnostics/psprelaunch497_delivery.py', '.github/workflows/retroarch-delivery.yml',
                 'build-utils/delivery-497-recipient.pem', 'AGENTS.md'}

WORKFLOW_SHA256 = '88bc7ba800ecfd71ef506d8892da92e36bed3f45f804e416a9bd7151e077797c'

# Unchanged build-487 RPCS3 ABI and core pin validation; never rewrite a
# precompiled core's recorded identity to make it match a newer host.
rpc_core_input_view = previous.rpc_core_input_view
validate_rpc_core_identity = previous.validate_rpc_core_identity
validate_rpc_core_pin = previous.validate_rpc_core_pin


def validate_psp_core_identity(identity, root):
    pin = json.loads((base.ROOT / 'native/ppsspp/source.json').read_text())
    proof = identity['ppssppManagedMemory']
    assert proof['abi'] == 1 and proof['source'] == pin
    assert proof['originalCore']['sha256'] == pin['basePspSHA256']
    core = next(c for c in identity['cores'] if c['id'] == 'ppsspp')
    binary = Path(root) / 'Frameworks/ppsspp_libretro.framework/ppsspp_libretro'
    assert hashlib.sha256(binary.read_bytes()).hexdigest() == core['sha256'] == proof['compiledCoreSHA256']
    assert core['sourceRevision'] == pin['revision'] and core['sourcePatchSha256'] == pin['patchSHA256']
    assert '_neostation_ppsspp_set_memory_callbacks' in base.command(['nm', '-gU', str(binary)])


BUILD501_NATIVE = 'd83145a71709342e7d3b662ba00789b726bc3fb5'
BUILD501_RUN = 39760303355
BUILD502_UI = '69a514390fffb1389977ca8863f0bb03f756db84'
BUILD502_UI_RUN = 39769356204
BUILD502_DELIVERY_ONLY = {
    '.github/diagnostics/psprelaunch497_delivery.py',
    '.github/workflows/retroarch-delivery.yml',
    '.github/workflows/rpcs3-core.yml',
    'build-utils/delivery-502-chatgpt-recipient.pem',
    'build-utils/validate_no_dusklight_ipa.py',
    'docs/evidence/build502-branch-preservation.json',
    'test/stikjit_scoped_host_test.py',
    'test/stikjit_unified_build_test.py',
}


def source_closure():
    # Build 502 is a targeted UI/branding test delivery. The application state
    # must be byte-for-byte the UI-validated Claude candidate; only this guard
    # and the public recipient key may differ afterwards.
    changed_since_ui = set(base.command([
        'git', 'diff', '--name-only', BUILD502_UI, 'HEAD'
    ]).splitlines())
    if changed_since_ui != BUILD502_DELIVERY_ONLY:
        raise ValueError(
            'Build 502 candidate differs from validated UI state: ' +
            ', '.join(sorted(changed_since_ui ^ BUILD502_DELIVERY_ONLY))
        )

    # No emulator/core/native implementation may drift from the successful
    # Build 501 device delivery. The intended Build 502 changes are Flutter UI,
    # branding assets and icon-generation inputs only; historical JIT guards
    # normalize reviewed branding/external-link retirements, including the Dolphin JIT helper, before byte-equivalence checks.
    base.command([
        'git', 'diff', '--exit-code', BUILD501_NATIVE, 'HEAD', '--',
        'native', 'packages', 'build-utils/libretro'
    ])

    workflow = base.ROOT / '.github/workflows/retroarch-delivery.yml'
    workflow_text = workflow.read_text(encoding='utf-8')
    required_workflow_markers = (
        "name: RewindBox RetroArch • Build 502 • SideStore",
        "inputs.build_number || '502'",
        "build-utils/delivery-502-chatgpt-recipient.pem",
        "- .github/diagnostics/psprelaunch497_delivery.py",
    )
    missing = [marker for marker in required_workflow_markers if marker not in workflow_text]
    if missing:
        raise ValueError('Build 502 delivery workflow markers missing: ' + ', '.join(missing))

    data = (base.ROOT / INDEX).read_bytes()
    if data != (base.ROOT / BUNDLED).read_bytes():
        raise ValueError('Bundled and hosted catalogues differ')

    return {
        'baseline': BUILD501_NATIVE,
        'baselineRun': BUILD501_RUN,
        'testedSource': BUILD502_UI,
        'testedRun': BUILD502_UI_RUN,
        'catalogueSHA256': hashlib.sha256(data).hexdigest(),
        'changedAfterUITest': sorted(changed_since_ui),
        'nativeAndCoreInputsReused': True,
        'rebuiltCores': [],
    }


BUILD502_RPC_CORE = '28371bd12169af9bf506d9d2cff98e0c13d44f24'
BUILD502_RPC_CORE_RUN = '39788462742'

from contextlib import contextmanager


@contextmanager
def _build502_rpc_core_view(pin):
    """Require the newly completed Core's exact published recipe and inputs."""
    import subprocess
    import sys
    if pin != BUILD502_RPC_CORE:
        raise ValueError('Unexpected Build 502 RPCS3 Core pin: ' + str(pin))
    if os.environ.get('RPCS3_CORE_RUN_ID') != BUILD502_RPC_CORE_RUN:
        raise ValueError('Unexpected Build 502 RPCS3 Core workflow run')
    if os.environ.get('GITHUB_REF_NAME') != 'Claude':
        raise ValueError('Build 502 RPCS3 pin check invoked outside Claude')

    rel = '.github/workflows/rpcs3-core.yml'
    workflow = base.ROOT / rel
    current = workflow.read_bytes()
    pinned = subprocess.check_output(
        ['git', 'show', pin + ':' + rel], cwd=base.ROOT
    )
    if current != pinned:
        raise ValueError('Build 502 RPCS3 Core workflow differs from its completed build')

    sys.path.insert(0, str(base.ROOT / 'test'))
    import neo_swap_core_pin_test as core
    yield core


def validate_rpc_core_pin(pin, paths):
    with _build502_rpc_core_view(pin) as core:
        if len(paths) != len(core.CORE_INPUTS) or set(paths) != set(core.CORE_INPUTS):
            raise ValueError('Build 502 RPCS3 Core input list differs from published Core')
        # The historical scheduling assertion predates the host-only
        # delivery500 route and Claude push trigger. Validate its original
        # contract in that original recipe view, then restore the *published*
        # new recipe before checking every input/hash/mode against the new pin.
        import subprocess
        recipe = base.ROOT / '.github/workflows/rpcs3-core.yml'
        published = recipe.read_bytes()
        original = subprocess.check_output([
            'git', 'show', '0b18a23460b0a9840406fda2e3d6da4c5cdb7273:.github/workflows/rpcs3-core.yml'
        ], cwd=base.ROOT)
        try:
            recipe.write_bytes(original)
            core.validate_source_contract()
        finally:
            recipe.write_bytes(published)
        core.validate_exact_pin(pin, root=base.ROOT)
    print('PASS Build 502 RPCS3 Core: completed run 39788462742 and all published inputs')


def validate_rpc_core_identity(identity):
    with _build502_rpc_core_view(identity['host_commit']) as core:
        core.validate_core_input_identity(identity, root=base.ROOT)
    print('PASS Build 502 RPCS3 Core identity: exact new ABI 30 artifact and all published input hashes')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-only', action='store_true')
    p.add_argument('--dart-evidence', action='store_true')
    p.add_argument('--libretro-evidence', action='store_true')
    p.add_argument('--skin-session-evidence', action='store_true')
    p.add_argument('--scope', default='full', choices=['full'])
    p.add_argument('--output', default='build/delivery/reused-validation.json')
    p.add_argument('--rpc-core-inputs')
    p.add_argument('core_paths', nargs='*')
    a = p.parse_args()
    closure = source_closure()
    if a.rpc_core_inputs:
        validate_rpc_core_pin(a.rpc_core_inputs, a.core_paths)
        return
    if a.source_only:
        print('PASS exact Build 502 UI state + unchanged Build 501 native/core inputs')
        return
    records = [
        base.successful_run(
            BUILD501_RUN,
            BUILD501_NATIVE,
            ['checks', 'native', 'Release device build • cold'],
        ),
        base.successful_run(BUILD502_UI_RUN, BUILD502_UI, ['test']),
    ]
    record = {
        'result': 'passed',
        'testedSHA': BUILD502_UI,
        'candidateSHA': base.command(['git', 'rev-parse', 'HEAD']).strip(),
        'sourceClosure': closure,
        'reusedEvidence': records,
        'validationWasReused': True,
        'unchangedDartSource': BUILD502_UI,
        'deviceGameplayValidated': False,
        'rebuiltCores': [],
    }
    if a.dart_evidence:
        record.update(key=os.environ['DART_VALIDATION_KEY'], tool='Flutter 3.47.2, Ubuntu 24.04')
    if a.libretro_evidence:
        xcode = base.command(['xcodebuild', '-version'])
        sdk = base.command(['xcrun', '--sdk', 'iphoneos', '--show-sdk-version'])
        if xcode != 'Xcode 26.3\nBuild version 17C529' or sdk != '26.2':
            raise ValueError('Changed native toolchain')
        record.update(xcode=xcode, iphoneSDK=sdk)
    out = base.ROOT / a.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + '\n')
    print('PASS Build 502 targeted UI delivery closure')


if __name__ == '__main__':
    main()

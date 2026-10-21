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


def source_closure():
    for end in (['HEAD'], []):
        changed = set(base.command(['git', 'diff', '--name-only', DELIVERED, *end, '--', *PRODUCT_PATHS]).splitlines())
        if changed != PRODUCT:
            raise ValueError('Unexpected product change since 496: ' + ', '.join(sorted(changed ^ PRODUCT)))
        since = set(base.command(['git', 'diff', '--name-only', TESTED, *end]).splitlines())
        extra = {p for p in since - DELIVERY_ONLY if not p.startswith('docs/')}
        if extra:
            raise ValueError('Changed inputs since targeted proof: ' + ', '.join(sorted(extra)))
        base.command(['git', 'diff', '--exit-code', CATALOGUE, *end, '--', INDEX, BUNDLED, 'tools/textures'])
    workflow = base.ROOT / '.github/workflows/retroarch-delivery.yml'
    if hashlib.sha256(workflow.read_bytes()).hexdigest() != WORKFLOW_SHA256:
        raise ValueError('Unreviewed delivery pipeline change')
    data = (base.ROOT / INDEX).read_bytes()
    if data != (base.ROOT / BUNDLED).read_bytes():
        raise ValueError('Bundled and hosted catalogues differ')
    return {'baseline': DELIVERED, 'baselineRun': DELIVERED_RUN, 'testedSource': TESTED,
            'testedRun': TESTED_RUN, 'catalogueSource': CATALOGUE, 'changedProductPaths': sorted(PRODUCT),
            'catalogueSHA256': hashlib.sha256(data).hexdigest(), 'rebuiltCores': ['ppsspp']}


# Private Build 501: exact RewindBox source (NeoAssets System Art), isolated
# from the closed Build 497 evidence recipe. This branch does not alter the app.
BUILD_501_SOURCE = 'be9ea63b80a69249e418d35d4c52715e39db3961'
BUILD_501_TESTED = '06b1dea13aba3f4fc9c68183a0f53390a8436e96'
BUILD_501_TEST_RUN = 39660184247
BUILD_501_ALLOWED = {
    'build-utils/delivery-501-recipient.pem',
    '.github/diagnostics/psprelaunch497_delivery.py',
}
BUILD_501_PRODUCT_TESTED = (
    'lib/services/neo_assets_service.dart',
    'lib/providers/neo_assets_provider.dart',
    'lib/services/system_art/neoassets_public_catalog.dart',
    'test/services/neoassets_public_catalog_test.dart',
    'test/legal_credits_dialog_test.dart',
    'lib/screens/settings_screen/legal_credits_dialog.dart',
    'assets/legal/THIRD_PARTY_NOTICES.md',
    'THEMES.md',
)


def _private_501_evidence(a):
    """Recheck immutable code and successful focused CI; do not forge 497 reuse."""
    if os.environ.get('GITHUB_REF_NAME') != 'build-501-system-art':
        raise ValueError('Private 501 validation only allowed on its isolated branch')
    if os.environ.get('GITHUB_EVENT_NAME') != 'workflow_dispatch':
        raise ValueError('Build 501 must be explicitly dispatched')
    changed = set(base.command(['git', 'diff', '--name-only',
                                BUILD_501_SOURCE, 'HEAD']).splitlines())
    if changed != BUILD_501_ALLOWED:
        raise ValueError('Build 501 contains unexpected source changes: '
                         + ', '.join(sorted(changed ^ BUILD_501_ALLOWED)))
    # The exact System Art implementation was analyzed and tested before squash
    # merge: compare the actual files, not their commit description.
    base.command(['git', 'diff', '--exit-code', BUILD_501_TESTED,
                  BUILD_501_SOURCE, '--', *BUILD_501_PRODUCT_TESTED])
    import subprocess
    run = json.loads(subprocess.check_output([
        'gh', 'api',
        'repos/TarbleFR/RewindBox/actions/runs/' + str(BUILD_501_TEST_RUN)
    ], text=True))
    if (run.get('head_sha') != BUILD_501_TESTED or
            run.get('status') != 'completed' or
            run.get('conclusion') != 'success'):
        raise ValueError('Exact NeoAssets Flutter and legal checks not successful')
    jobs = json.loads(subprocess.check_output([
        'gh', 'api', 'repos/TarbleFR/RewindBox/actions/runs/'
        + str(BUILD_501_TEST_RUN) + '/jobs'
    ], text=True))['jobs']
    if not any(j.get('name') == 'Validate legal bundle and UI'
               and j.get('conclusion') == 'success' for j in jobs):
        raise ValueError('Missing successful Flutter/legal CI job')
    if a.rpc_core_inputs:
        validate_rpc_core_pin(a.rpc_core_inputs, a.core_paths)
        return
    if a.source_only:
        print('PASS Build 501 immutable RewindBox source; NeoAssets tests reused')
        return
    record = {
        'result': 'passed',
        'candidateSHA': base.command(['git','rev-parse','HEAD']),
        'testedSHA': BUILD_501_TESTED,
        'sourceClosure': {
            'fixedSourceSHA': BUILD_501_SOURCE,
            'modifiedSinceSource': sorted(changed),
            'validatedApiAndLegalRun': BUILD_501_TEST_RUN,
            'scope': 'NeoAssets System Art build only',
        },
        'reusedEvidence': [
            {'run': BUILD_501_TEST_RUN, 'source': BUILD_501_TESTED,
             'kind': 'Flutter analysis, System Art tests and legal checks'},
        ],
        'validationWasReused': True,
        'unchangedDartSource': BUILD_501_TESTED,
        'deviceGameplayValidated': False,
        'rebuiltCores': [],
    }
    if a.dart_evidence:
        record.update(key=os.environ['DART_VALIDATION_KEY'],
                      tool='Flutter 3.47.2, Ubuntu 24.04')
    if a.libretro_evidence:
        # Reuse native validation only for *unchanged* NeoSwap/core inputs.
        # The actual frontend is still freshly compiled in the cold IPA job.
        base.command(['git', 'diff', '--exit-code',
                      '9319dc98176dcfd89dca3489569b1dbf23fd3ba4',
                      'HEAD', '--', 'packages/neo_swap/ios/Classes',
                      'native/neoswap', 'native/neoswap-relay',
                      'native/neoswap-donation'])
        base.command(['git','diff','--exit-code',
                      'ab9361c29f7c9ab769c4263dd8b7427fc4f4c036',
                      'HEAD','--','build-utils/libretro/cores.json',
                      'native/ppsspp/source.json',
                      'packages/libretro_internal_bridge/ios/Classes/NeoStationPSPMemory.h',
                      'packages/libretro_internal_bridge/ios/Classes/LibretroAddressSpace.m',
                      'packages/libretro_internal_bridge/ios/Classes/LibretroAddressSpace.h'])
        xcode = base.command(['xcodebuild','-version'])
        sdk = base.command(['xcrun','--sdk','iphoneos','--show-sdk-version'])
        if xcode != 'Xcode 26.3\\nBuild version 17C529' or sdk != '26.2':
            raise ValueError('Changed iOS toolchain')
        record.update(xcode=xcode, iphoneSDK=sdk,
                      nativeCoreInputsUnchanged=True)
    out = base.ROOT / a.output
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(record,indent=2)+'\\n')
    print('PASS Build 501 exact source and verified NeoAssets checks, no release')


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
    if os.environ.get('GITHUB_REF_NAME') == 'build-501-system-art':
        _private_501_evidence(a)
        return
    closure = source_closure()
    if a.rpc_core_inputs:
        validate_rpc_core_pin(a.rpc_core_inputs, a.core_paths)
        return
    if a.source_only:
        print('PASS exact Build 496 product + tested PSP host/core managed memory')
        return
    records = [base.successful_run(DELIVERED_RUN, DELIVERED,
                                  ['checks', 'native', 'Release device build • cold']),
               base.successful_run(TESTED_RUN, TESTED, ['psp']),
               base.successful_run(39449348701, 'd6fa85695f219ad0b66ef71bc9429d11c8e8abd9',
                                   ['Packs published as repository archives (3ds)', 'Packs published as repository archives (psp)']),
               base.successful_run(39450675080, 'c6ebee7f407c2833e20914db9a16682228a13a92',
                                   ['Packs published as original GitHub archives (3ds)'])]
    record = {'result': 'passed', 'testedSHA': TESTED, 'candidateSHA': base.command(['git', 'rev-parse', 'HEAD']),
              'sourceClosure': closure, 'reusedEvidence': records, 'validationWasReused': True,
              'unchangedDartSource': DELIVERED, 'deviceGameplayValidated': False, 'rebuiltCores': ['ppsspp']}
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
    print('PASS reused unchanged Build 496 evidence + exact successful Build 497 native/core/session checks')


if __name__ == '__main__':
    main()

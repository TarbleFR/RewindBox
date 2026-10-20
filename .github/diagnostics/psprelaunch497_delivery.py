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

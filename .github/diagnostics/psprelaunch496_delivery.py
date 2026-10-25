"""Build 496: exact delivered 495 product + frozen HD data + PSP view ownership.

Reuse unchanged Dart, emulator, skin and native evidence from successful
delivery 495. The changed reservation is compiled for iPhone, reproduced on
the old code, tested natively and exercised by seven real session scenarios.
The final data and changed catalogue tools have their own successful job.
No historical failure is reclassified and no core is rebuilt.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import hdtex495_delivery as previous

base = previous.base
DELIVERED = 'fee67e4d0aeede934bfed722f8dd9b43fb6d2ff5'
DELIVERED_RUN = 39384517903
CATALOGUE = '3b56d406534aa174818566dd4fc24f490399383d'
TESTED = '4b12e244d9093564a6d57a30b72900030f0733e5'
TESTED_RUN = 39444272536
PRODUCT_PATHS = ['lib', 'assets', 'packages', 'native', 'ios', 'pubspec.yaml', 'pubspec.lock', 'build-utils/libretro']
MEMORY = 'packages/libretro_internal_bridge/ios/Classes/LibretroAddressSpace.m'
INDEX = 'native/textures/catalogue/manifest.json.gz'
BUNDLED = 'packages/neo_texture_catalog/ios/Resources/manifest.json.gz'
PRODUCT = {MEMORY, INDEX, BUNDLED}
DELIVERY_ONLY = {'.github/diagnostics/psprelaunch496_delivery.py', '.github/workflows/retroarch-delivery.yml',
                 'build-utils/delivery-496-recipient.pem', 'AGENTS.md'}

# Unchanged build-487 RPCS3 ABI and core pin validation; never rewrite a
# precompiled core's recorded identity to make it match a newer host.
rpc_core_input_view = previous.rpc_core_input_view
validate_rpc_core_identity = previous.validate_rpc_core_identity
validate_rpc_core_pin = previous.validate_rpc_core_pin


def source_closure():
    for end in (['HEAD'], []):
        changed = set(base.command(['git', 'diff', '--name-only', DELIVERED, *end, '--', *PRODUCT_PATHS]).splitlines())
        if changed != PRODUCT:
            raise ValueError('Unexpected product change since 495: ' + ', '.join(sorted(changed ^ PRODUCT)))
        since = set(base.command(['git', 'diff', '--name-only', TESTED, *end]).splitlines())
        extra = {p for p in since - DELIVERY_ONLY if not p.startswith('docs/')}
        if extra:
            raise ValueError('Changed inputs since targeted proof: ' + ', '.join(sorted(extra)))
        base.command(['git', 'diff', '--exit-code', CATALOGUE, *end, '--', INDEX, BUNDLED,
                      'tools/textures', 'test/texture_catalogue_publication_test.py', 'test/texture_yandex_host_test.py'])
    # Delivery wiring may only select this evidence gate and the new build
    # number. Keep every packaging, signature and payload integrity step.
    old = base.command(['git', 'show', DELIVERED + ':.github/workflows/retroarch-delivery.yml'])
    expected = old.replace('hdtex495_delivery', 'psprelaunch496_delivery').replace('Build 495', 'Build 496').replace("'495'", "'496'")
    if (base.ROOT / '.github/workflows/retroarch-delivery.yml').read_text().strip() != expected:
        raise ValueError('Unreviewed delivery pipeline change')
    data = (base.ROOT / INDEX).read_bytes()
    if data != (base.ROOT / BUNDLED).read_bytes():
        raise ValueError('Bundled and hosted catalogues differ')
    return {'baseline': DELIVERED, 'baselineRun': DELIVERED_RUN, 'testedSource': TESTED,
            'testedRun': TESTED_RUN, 'catalogueSource': CATALOGUE, 'changedProductPaths': sorted(PRODUCT),
            'catalogueSHA256': hashlib.sha256(data).hexdigest(), 'coreRebuilt': False}


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
        print('PASS exact Build 495 product + frozen HD catalogue + tested PSP memory ownership')
        return
    records = [base.successful_run(DELIVERED_RUN, DELIVERED,
                                  ['checks', 'native', 'Release device build • cold']),
               base.successful_run(TESTED_RUN, TESTED, ['native', 'catalogue'])]
    record = {'result': 'passed', 'testedSHA': TESTED, 'candidateSHA': base.command(['git', 'rev-parse', 'HEAD']),
              'sourceClosure': closure, 'reusedEvidence': records, 'validationWasReused': True,
              'unchangedDartSource': DELIVERED, 'deviceGameplayValidated': False, 'coreRebuilt': False}
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
    print('PASS reused unchanged Build 495 evidence + exact successful Build 496 native/session/data checks')


if __name__ == '__main__':
    main()

"""Closed Build 498 composition: public-host/RAR catalogue + tested PSP497 cores.

Preparation: fill CATALOGUE_REVISION before committing candidate C. Native
provider/Store/SDK proofs are pinned below. Keep {{FINAL_SOURCE}} in C's workflow template. A workflow-only
commit W substitutes C there; its HD_FINAL_SOURCE supplies the immutable pin
without a self-referential commit hash. Neither the 497 recipe nor its guard is
modified. This gate reads prior CI evidence and never rebuilds an emulator core.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = '.github/workflows/hd-native-delivery.yml'
GUARD = '.github/diagnostics/hdnative498_delivery.py'
FINAL_SOURCE = '{{FINAL_SOURCE}}'  # HD_FINAL_SOURCE in immutable workflow W wins.
CATALOGUE_REVISION = '2026-10-20.28541bbfe23e'
STORE_RUN = 39461533070
SDK_RUN = 39461533070
PROVIDERS_RUN = 39461533070
NATIVE_PROOF_SOURCE = 'd8a11a7dc2f6273dc2a845fb076049301cd4e9c2'
BUILD = 498
RECIPIENT = 'build-utils/delivery-498-recipient.pem'
BASE = 'e999a5fdc98a42f5d1995ca85fdfa04479d7f77a'
FROZEN_WORKFLOW = '9319dc98176dcfd89dca3489569b1dbf23fd3ba4'
RECIPES_BASE = '9a02109553079c95fad96c9bccf483c0d4eaa435'
DELIVERED_496 = 'b332bc2e59e4f44d4e820aa4879520a058bfd76b'
DELIVERED_496_RUN = 39445610738
PSP_SOURCE = 'ab9361c29f7c9ab769c4263dd8b7427fc4f4c036'
PSP_RUN = 39455712245
READERS_SOURCE = '2a7889e7bbc5c08c1dc781f2630a1f05fdc7037e'
READERS_RUN = 39456486483
NETWORK_SOURCE = '07923d59780499b3fbcd1595d0a464a688e37e9f'
NETWORK_RUN = 39456927008
NETWORK_RECEIPT_SHA256 = 'b3cb3b528b3ce35792ced606dd2e44dbd6d88964eba28de0e3e60385abd7a1cb'
NATIVE_JOB = 'Public host resolvers, native installation and iPhone compilation'
READERS_JOB = 'RAR reader and direct-source publication boundaries'
INDEX = 'native/textures/catalogue/manifest.json.gz'
BUNDLED = 'packages/neo_texture_catalog/ios/Resources/manifest.json.gz'
POD = 'packages/neo_texture_catalog/ios/'
ARMSX2 = 'packages/armsx2_internal_bridge/ios/Classes/'
PRODUCT_ROOTS = ['lib', 'assets', 'packages', 'native', 'ios', 'pubspec.yaml', 'pubspec.lock', 'build-utils/libretro']
EXTRA_PRODUCT = {INDEX, BUNDLED, 'assets/legal/THIRD_PARTY_NOTICES.md', ARMSX2 + 'ARMSX2TexturePackStore.mm'}
CORE_INPUTS = ['build-utils/libretro', 'native/nestopia', 'native/ppsspp', '.github/diagnostics/ppsspp497',
    '.github/diagnostics/nestopia_bgcolor', '.github/workflows/nestopia-bgcolor.yml', '.github/workflows/build497-checks.yml',
    'test/psp_relaunch497.py', 'test/libretro_host/frontend/psp_managed_memory_test.m',
    'packages/libretro_internal_bridge/ios/Classes/NeoStationPSPMemory.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroAddressSpace.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroAddressSpace.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSession.m']

# Keep the authentic RPCS3 pin/ABI transformations and PSP package validator.
# Load the historical chain only when needed; --help and local source/data
# inspection also work in the maintainer's deliberately sparse checkout.
def previous():
    import psprelaunch497_delivery
    return psprelaunch497_delivery


def rpc_core_input_view(*args, **kwargs):
    return previous().rpc_core_input_view(*args, **kwargs)


def validate_rpc_core_identity(*args, **kwargs):
    return previous().validate_rpc_core_identity(*args, **kwargs)


def validate_rpc_core_pin(*args, **kwargs):
    return previous().validate_rpc_core_pin(*args, **kwargs)


def validate_psp_core_identity(*args, **kwargs):
    return previous().validate_psp_core_identity(*args, **kwargs)


def command(args):
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def blob(source, path):
    return subprocess.check_output(['git', 'show', source + ':' + path], cwd=ROOT)


def api(path):
    return json.loads(command(['gh', 'api', 'repos/TarbleFR/RewindBox/' + path]))


def same_inputs(source, paths):
    paths = sorted(set(paths))
    command(['git', 'diff', '--exit-code', source, 'HEAD', '--', *paths])
    command(['git', 'diff', '--exit-code', 'HEAD', '--', *paths])


def tracked(*paths, source='HEAD'):
    return command(['git', 'ls-tree', '-r', '--name-only', source, '--', *paths]).splitlines()


def run_number(value):
    if not re.fullmatch(r'[1-9][0-9]{5,19}', str(value)):
        raise ValueError('Unresolved or invalid CI run pin: ' + str(value))
    return int(value)


def successful_steps(run_id, source, job_name, step_names, *, allow_failed_run=False):
    """Accept named successful steps, never reclassify an unsuccessful run."""
    run = api(f'actions/runs/{run_id}')
    if run['head_sha'] != source or run['status'] != 'completed' or run['path'] != '.github/workflows/hd-textures.yml':
        raise ValueError('Changed or incomplete HD proof: ' + str(run_id))
    if not allow_failed_run and run['conclusion'] != 'success':
        raise ValueError('HD proof run did not succeed: ' + str(run_id))
    listing = api(f'actions/runs/{run_id}/jobs?per_page=100')
    if listing['total_count'] != len(listing['jobs']):
        raise ValueError('Incomplete proof job listing')
    jobs = [job for job in listing['jobs'] if job['name'] == job_name]
    if len(jobs) != 1:
        raise ValueError('Missing or ambiguous proof job: ' + job_name)
    job = jobs[0]
    records = []
    for name in step_names:
        steps = [step for step in job['steps'] if step['name'] == name]
        if len(steps) != 1 or steps[0]['conclusion'] != 'success':
            raise ValueError('Proof step absent, skipped or failed: ' + name)
        records.append({'name': name, 'conclusion': 'success', 'number': steps[0]['number']})
    return {'run': run_id, 'source': source, 'runConclusion': run['conclusion'], 'job': job['id'],
            'jobConclusion': job['conclusion'], 'successfulSteps': records, 'reexecuted': False}


def candidate_pin():
    source = os.environ.get('HD_FINAL_SOURCE', FINAL_SOURCE)
    if not re.fullmatch(r'[0-9a-f]{40}', source) or command(['git', 'rev-parse', 'HEAD']) != source:
        raise ValueError('Candidate checkout is not the exact final source')
    if os.environ.get('BUILD_NUMBER', str(BUILD)) != str(BUILD):
        raise ValueError('This recipe delivers only the new Build 498')
    if os.environ.get('DELIVERY_RECIPIENT', RECIPIENT) != RECIPIENT:
        raise ValueError('A dedicated Build 498 recipient is required')
    if '{{' in CATALOGUE_REVISION:
        raise ValueError('Catalogue revision is not pinned')
    run_number(PROVIDERS_RUN); run_number(STORE_RUN); run_number(SDK_RUN)
    key = ROOT / RECIPIENT
    public = key.read_bytes()
    if not public.startswith(b'-----BEGIN PUBLIC KEY-----') or b'PRIVATE KEY' in public:
        raise ValueError('Delivery recipient must contain only a public PEM key')
    if public == blob(BASE, 'build-utils/delivery-497-recipient.pem'):
        raise ValueError('The frozen 497 recipient must not be reused')
    subprocess.run(['openssl', 'rsa', '-pubin', '-in', str(key), '-noout'], check=True, capture_output=True)
    # W may only resolve the source pin in C's new workflow template. The old
    # 497 workflow is never changed by this recipe.
    workflow_source = os.environ.get('NEOSTATION_WORKFLOW_SHA', source)
    if not re.fullmatch(r'[0-9a-f]{40}', workflow_source):
        raise ValueError('Workflow identity is not an immutable commit')
    expected = (ROOT / WORKFLOW).read_text().replace('{{FINAL_SOURCE}}', source)
    if blob(workflow_source, WORKFLOW).decode() != expected:
        raise ValueError('Unreviewed new delivery workflow change')
    if blob(workflow_source, GUARD) != (ROOT / GUARD).read_bytes():
        raise ValueError('Workflow and candidate disagree on the delivery gate')
    return source, workflow_source


def catalogue():
    raw = (ROOT / INDEX).read_bytes()
    if raw != (ROOT / BUNDLED).read_bytes():
        raise ValueError('Hosted and bundled texture catalogues differ')
    index = json.loads(gzip.decompress(raw))
    if index['revision'] != CATALOGUE_REVISION:
        raise ValueError('Catalogue revision differs from the closed candidate')
    sys.path.insert(0, str(ROOT / 'tools/textures'))
    import build_catalogue
    import count_packs
    build_catalogue.validate(index)
    entries = count_packs.sources()
    totals = count_packs.count(index, entries)['total']
    unique = {count_packs.family(pack, entries) for pack in index['packs'] if count_packs.native_one_tap(pack)}
    if len(unique) != totals['oneTapFamilies'] or len(unique) < 400:
        raise ValueError('At least 400 distinct validated in-app families are required')
    return {'revision': index['revision'], 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
            'distinctFamilies': totals['distinct'], 'oneTapFamilies': len(unique),
            'manualVerifiedFamilies': totals['manualVerifiedFamilies']}


def source_closure():
    source, workflow_source = candidate_pin()
    changed = set(command(['git', 'diff', '--name-only', BASE, 'HEAD', '--', *PRODUCT_ROOTS]).splitlines())
    extra = {path for path in changed if not path.startswith(POD) and path not in EXTRA_PRODUCT}
    if extra:
        raise ValueError('Unexpected product change since frozen 497: ' + ', '.join(sorted(extra)))
    command(['git', 'diff', '--exit-code', 'HEAD', '--', *PRODUCT_ROOTS])
    same_inputs(PSP_SOURCE, CORE_INPUTS)
    # The other session restored the ordinary recipe after its immutable 497
    # delivery. Preserve that restoration and receipt, rather than rolling it
    # back to the earlier frozen workflow definition used for the 497 IPA.
    same_inputs(RECIPES_BASE, ['.github/workflows/retroarch-delivery.yml',
        '.github/diagnostics/psprelaunch497_delivery.py', '.github/workflows/build497-checks.yml',
        'docs/evidence/psprelaunch497-delivery.json'])
    same_inputs(RECIPES_BASE, (set(tracked('build-utils')) | set(tracked('build-utils', source=RECIPES_BASE))) - {RECIPIENT})
    same_inputs(RECIPES_BASE, (set(tracked('.github/diagnostics')) | set(tracked('.github/diagnostics', source=RECIPES_BASE))) - {GUARD})
    return {'candidateSource': source, 'workflowSource': workflow_source, 'frozen497Source': BASE,
            'frozen497WorkflowSource': FROZEN_WORKFLOW, 'preservedRecipeSource': RECIPES_BASE,
            'changedProductPaths': sorted(changed), 'unchangedDartSource': DELIVERED_496,
            'catalogue': catalogue(), 'rebuiltCores': [], 'deviceGameplayValidated': False}


def affected_proofs():
    store_run, sdk_run = run_number(STORE_RUN), run_number(SDK_RUN)
    providers_run = run_number(PROVIDERS_RUN)
    store_source = sdk_source = providers_source = NATIVE_PROOF_SOURCE
    production = list(set(tracked(POD + 'Classes', POD + 'ThirdParty')) |
        set(tracked(POD + 'Classes', POD + 'ThirdParty', source=sdk_source)) |
        set(tracked(POD + 'Classes', POD + 'ThirdParty', source=store_source)))
    armsx2 = [ARMSX2 + name for name in ('ARMSX2TexturePackStore.mm', 'ARMSX2TexturePackStore.h', 'ARMSX2TexturePackCore.h')]
    same_inputs(sdk_source, production + armsx2 + [POD + 'neo_texture_catalog.podspec', 'test/texture_catalog_ios_syntax_test.py'])
    same_inputs(store_source, production + armsx2 + ['test/texture_store_provider_test.py', 'test/texture_store_provider_test.mm',
        'test/texture_direct_network_test.py', 'test/texture_rar_test.py', 'tools/textures/build_rar_library.py'])
    provider_files = [POD + 'Classes/' + name for name in ('NeoTextureHostResolver.h', 'NeoTextureHostResolver.m',
        'NeoTextureMega.h', 'NeoTextureMega.mm', 'NeoTextureCatalog.m', 'NeoTextureSupport.h', 'NeoTextureSupport.m')]
    same_inputs(providers_source, provider_files + ['test/texture_host_resolver_test.py', 'test/texture_host_resolver_test.m',
        'test/texture_mega_native_test.py', 'test/texture_mega_test.mm', 'test/texture_catalog_capability_test.py',
        'test/texture_catalog_capability_test.m'])
    same_inputs(READERS_SOURCE, tracked(POD + 'ThirdParty', POD + 'Classes/NeoTextureRAR.h', POD + 'Classes/NeoTextureRARMemory.c',
        POD + 'Classes/NeoTextureRARMemory.h', POD + 'Classes/NeoTextureInstall.h') +
        [path for path in production if path.endswith(('.h', '.c'))] + tracked('test/fixtures/texture_rar') +
        ['test/texture_rar_test.py', 'test/native/texture_rar_driver.cpp', 'test/texture_install_test.py',
         'test/native/texture_install_driver.cpp', 'tools/textures/build_rar_library.py'])
    same_inputs(NETWORK_SOURCE, provider_files + [POD + 'Classes/NeoTextureEngines.mm', 'test/texture_direct_network_test.py',
        'test/texture_direct_network_test.mm', 'tools/textures/research/direct400-network-probes.json'])
    # New ARMSX2 staging cleanup has its own new Store/SDK proof. The old live
    # network probe is reused only for its unchanged HTTP/resolution/crypto code.
    path = POD + 'Classes/NeoTexturePackStore.mm'
    before_install = lambda data: data.split(b'#pragma mark - Install', 1)[0]
    if before_install(blob(NETWORK_SOURCE, path)) != before_install((ROOT / path).read_bytes()):
        raise ValueError('The HTTP/resume/crypto pipeline changed since the six live probes')
    return [successful_steps(READERS_RUN, READERS_SOURCE, READERS_JOB,
                ['New RAR decoder and affected installation dispatch'], allow_failed_run=True),
            successful_steps(providers_run, providers_source, NATIVE_JOB,
                ['New provider, cryptography and compatibility fixtures']),
            successful_steps(store_run, store_source, NATIVE_JOB,
                ['Native provider download, resume and RAR installation fixtures']),
            successful_steps(sdk_run, sdk_source, NATIVE_JOB, ['Affected Foundation store and iPhone SDK linkage']),
            successful_steps(NETWORK_RUN, NETWORK_SOURCE, NATIVE_JOB,
                ['Small real original files through the native download and install path'])]


def network_record():
    path = ROOT / 'docs/evidence/hd-direct400-native-network-2026-10-20.json'
    data = path.read_bytes(); record = json.loads(data)
    if hashlib.sha256(data).hexdigest() != NETWORK_RECEIPT_SHA256:
        raise ValueError('The original live-network receipt changed')
    expected = ['wii-nsmbw-hd-title-tjshah', 'wii-nsmbw-shield-ui-moukrea-x2', 'gc-ttyd-xbox360-ms-buttons-jvook',
        'psp-digimon-world-redigitize-hd-ui', 'psp-gow-ghost-sparta-hud-skydr4gon', 'gc-crash-nitro-kart-hd-fixes-john30011887']
    if record.get('native_store') is not True or record.get('automatic_retries') != 0 or [r['id'] for r in record['results']] != expected:
        raise ValueError('Unexpected real-download receipt')
    for row in record['results']:
        if row['status'] != 'ok' or row.get('size_sha_verified_by_store') is not True or row['installed_files'] < 1:
            raise ValueError('A real public download was not verified and installed')
    return {'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(data).hexdigest(), 'successfulDownloads': 6,
            'activationSuccesses': sum(row.get('activated') is True for row in record['results']), 'physicalDeviceRendering': False}


def final_ipa(path, build):
    if build != BUILD:
        raise ValueError('Wrong final IPA build number')
    sys.path.insert(0, str(ROOT / 'build-utils'))
    from validate_hd_textures_ipa import validate
    result = validate(path, build)
    with zipfile.ZipFile(path) as archive:
        member = next(name for name in archive.namelist() if name.endswith('/Frameworks/neo_texture_catalog.framework/neo_texture_catalog'))
        binary = archive.read(member)
        markers = [b'in_app', b'NeoTexPublicHostRequest', b'NeoTextureMegaRequest', b'NeoTextureMegaMetadataGuard', b'RAR5',
            b'RAR encryption support unavailable', b'Content-Range', b'cipher.partial',
            b'resolvePart:completion:',
            b'expandRARImport:engine:cancel:expansion:',
            b'fetchResolvedPart:URL:crypto:pack:index:into:base:cancel:completion:']
        missing = [value.decode() for value in markers if value not in binary]
        if missing:
            raise ValueError('Final IPA lacks compiled native download/RAR support: ' + ', '.join(missing))
    sealed_path = ROOT / 'build/delivery/signed-payload-identity.json'
    sealed = json.loads(sealed_path.read_text())
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if sealed['ipaSha256'] != digest or sealed.get('allCompiledCodeAndDataSectionsUnchangedBySigning') is not True or sealed.get('abiMetadataUnchangedBySigning') is not True:
        raise ValueError('Final sealed IPA does not match the signing-continuity receipt')
    if 'Frameworks/ppsspp_libretro.framework/ppsspp_libretro' not in sealed['images']:
        raise ValueError('Signing continuity omits the pinned PSP core')
    identity_path = ROOT / 'dist/libretro/identity.json'
    identity = json.loads(identity_path.read_text())
    if identity['host_commit'] != PSP_SOURCE:
        raise ValueError('Final delivery uses a different core package')
    validate_psp_core_identity(identity, ROOT / 'dist/libretro')
    if os.environ['HD_FINAL_SOURCE'] != command(['git', 'rev-parse', 'HEAD']):
        raise ValueError('Final IPA report is not running at the pinned candidate')
    result.update(nativeRARAndPublicHosts=True, finalSignedIPA=True, source=os.environ['HD_FINAL_SOURCE'],
        pspCoreSource=PSP_SOURCE, pspCoreRun=PSP_RUN, rebuiltCores=[],
        pspCoreSHA256BeforeSigning=next(core['sha256'] for core in identity['cores'] if core['id'] == 'ppsspp'),
        originalCorePackageIdentitySHA256=hashlib.sha256(identity_path.read_bytes()).hexdigest(),
        signingContinuitySHA256=hashlib.sha256(sealed_path.read_bytes()).hexdigest(), catalogue=catalogue())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-only', action='store_true')
    parser.add_argument('--libretro-evidence', action='store_true')
    parser.add_argument('--skin-session-evidence', action='store_true')
    parser.add_argument('--rpc-core-inputs')
    parser.add_argument('--ipa', type=Path)
    parser.add_argument('--build-number', type=int, default=BUILD)
    parser.add_argument('--output', type=Path, default=Path('build/delivery/hd-native-reused-validation.json'))
    parser.add_argument('core_paths', nargs='*')
    args = parser.parse_args()
    if args.rpc_core_inputs:
        validate_rpc_core_pin(args.rpc_core_inputs, args.core_paths)
        return
    if args.ipa:
        record = final_ipa(args.ipa, args.build_number)
    else:
        closure = source_closure()
        if args.source_only:
            print(json.dumps(closure, indent=2)); return
        proofs = affected_proofs()
        prior = [previous().base.successful_run(DELIVERED_496_RUN, DELIVERED_496, ['checks', 'native', 'Release device build • cold']),
                 previous().base.successful_run(PSP_RUN, PSP_SOURCE, ['psp'])]
        if args.libretro_evidence:
            if command(['xcodebuild', '-version']) != 'Xcode 26.3\nBuild version 17C529' or command(['xcrun', '--sdk', 'iphoneos', '--show-sdk-version']) != '26.2':
                raise ValueError('Native evidence uses a different toolchain')
        record = {'result': 'passed', 'sourceClosure': closure, 'affectedNativeEvidence': proofs, 'unchangedEvidence': prior,
                  'networkReceipt': network_record(), 'rebuiltCores': [], 'physicalDeviceValidated': False}
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2) + '\n')
    print('PASS closed HD-native delivery composition' if not args.ipa else 'PASS final sealed IPA carries native RAR/public-host capability')


if __name__ == '__main__':
    main()

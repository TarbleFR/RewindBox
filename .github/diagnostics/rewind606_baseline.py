"""Preserve delivered605 and permit only the explicitly reviewed Hogwarts delta."""
import hashlib
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BUILD = 606
BASE = '5de451091208c13926ccdb373a0a34f35ec2ee2d'
BASE_TREE = '7ac3b39b311a8d7cfbdb1a373a83efc5510fdfda'
BASE_RECEIPT = 'docs/evidence/achievement-translation-ipa/delivery.json'
BASE_RECEIPT_SHA256 = 'aa09655c65c4668112a9506589343d7b481cb178a81ec311420bd9203c401bd5'
BASE_IPA_SHA256 = 'd51a4b138f54f5bbf88ab00a09856e3915a30ab71d9849b8aeaa9a7d8fb35337'
CONFIG = 'build-utils/rewind606-delivery.json'
PRODUCTS = ('lib', 'native', 'packages', 'assets', 'pubspec.yaml', 'pubspec.lock')
RPC_ROUTES = ('packages/rpcs3_internal_bridge/ios/Classes/Rpcs3Diagnostics.mm',
              'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3EarlyLoaderDiagnostics.h',
              'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm')
CONCURRENT_HOST_DELTA = dict(
    source='11ac3a3a9466e41a44ecfcd9f280e1e7dd20db8b',
    path=RPC_ROUTES[2],
    before='60f7140fd100aab0fab929864a171a027d05cd2d5b3523a51c471792225bce01',
    after='d6326d968f3552c5539d48a0933b41d3e61a3e61c0302972ec370e8df5bd3d16',
    scope='Host journal only: classify existing driver-cache boundaries and admit at most 16 milestone writes per second; no Core or MoltenVK runtime selection change.',
)
RECIPE = {
    CONFIG, '.github/diagnostics/rewind606_baseline.py',
    '.github/diagnostics/rewind606_engine.py', '.github/diagnostics/rewind606_delivery.py',
    '.github/diagnostics/rpcs3runtime606_core.py',
    '.github/workflows/rewind606-hogwarts-performance-delivery.yml',
    'build-utils/delivery-606-recipient.pem',
    'test/hogwarts606_delivery_contract_test.py',
    'test/hogwarts606_rpcs3_compatibility_test.py',
}
COMPONENTS = {
    'DOLPHIN_SHA': '7cac54161659421ed95c2cd1c0b0746539a4cd38',
    'DOLPHIN_CORE_HOST_SHA': 'af5b18e67864e6555f54b7b4b6f1452ed82f6982',
    'DOLPHIN_CORE_RUN_ID': '41209480072',
    'ARMSX2_CORE_HOST_SHA': '1343906f05e33b40f10f7026a1a6e2327c338d0e',
    'ARMSX2_CORE_RUN_ID': '39178893158',
    'RPCS3_CORE_HOST_SHA': 'a4d0c9a5e00ace8d2036c62ef1a653e50bb79a3a',
    'RPCS3_CORE_RUN_ID': '41117115264',
    'LIBRETRO_CORES_HOST_SHA': 'ab9361c29f7c9ab769c4263dd8b7427fc4f4c036',
    'LIBRETRO_CORES_VALIDATED_SHA': 'ab9361c29f7c9ab769c4263dd8b7427fc4f4c036',
    'LIBRETRO_CORES_RUN_ID': '39455712245',
}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, timeout=120).strip()


@lru_cache(maxsize=32)
def known_commit(root, ref):
    subprocess.run(['git', 'cat-file', '-e', ref + '^{commit}'], cwd=root, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def original(ref, path):
    require(not Path(path).is_absolute() and '..' not in Path(path).parts, 'Unsafe source path')
    known_commit(str(ROOT), ref)
    result = subprocess.run(['git', 'show', ref + ':' + path], cwd=ROOT,
                            capture_output=True, check=False)
    if result.returncode:
        require(subprocess.run(['git', 'cat-file', '-e', ref + ':' + path], cwd=ROOT,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0,
                'Cannot read source: ' + path)
        return None
    return result.stdout


def pins(ready=True):
    value = json.loads((ROOT / CONFIG).read_bytes())
    require(value['schema'] == 1 and value['build'] == BUILD, 'Wrong delivery config')
    base = value['baseline']
    require(base == dict(build=605, source=BASE, tree=BASE_TREE, run=41216465880,
        job=124584748706, attempt=1, receipt=BASE_RECEIPT,
        receiptSha256=BASE_RECEIPT_SHA256, ipaBytes=189643236,
        ipaSha256=BASE_IPA_SHA256), 'Wrong delivered605 baseline')
    require(value['concurrentHostDelta'] == CONCURRENT_HOST_DELTA,
            'Wrong reviewed concurrent RPCS3 host journal delta')
    if ready:
        require(value['status'] == 'verified-producers' and
                re.fullmatch('[0-9a-f]{40}', value.get('reviewedSource') or ''),
                'Exact successful Core/host producer pins are still pending')
        require(value['core'] and value['host'] and value['productDelta'] and value['sourceDelta'],
                'Missing reviewed source or producer inventories')
    return value


def baseline_receipt():
    raw = (ROOT / BASE_RECEIPT).read_bytes()
    require(sha(raw) == BASE_RECEIPT_SHA256, 'Delivered605 receipt drift')
    value = json.loads(raw)
    require(value['result'] == 'passed' and value['source'] == BASE and value['build'] == 605 and
            value['run'] == 41216465880 and value['job'] == 124584748706 and
            value['ipaSHA256'] == BASE_IPA_SHA256 and value['ipaBytes'] == 189643236,
            'Delivered605 provenance differs')
    return value


def reviewed_routing():
    value = pins()
    routes = value['rpcHostRouting']
    require(set(routes) == set(RPC_ROUTES), 'RPCS3 exception must cover exactly three host journal paths')
    concurrent = CONCURRENT_HOST_DELTA
    require(routes[concurrent['path']] == {key: concurrent[key] for key in ('before', 'after')},
            'Concurrent RPCS3 bridge change exceeds reviewed journal-only postimage')
    require(sha(original(concurrent['source'], concurrent['path'])) == concurrent['after'],
            'Concurrent RPCS3 journal source differs')
    for path, change in routes.items():
        require(change == value['productDelta'][path], 'RPCS3 routing lacks product delta binding')
        before = original(BASE, path)
        require(before is not None and sha(before) == change['before'], 'Wrong RPCS3 host preimage')
        require(sha((ROOT / path).read_bytes()) == change['after'], 'Unreviewed RPCS3 host postimage')
        require(sha(original(value['reviewedSource'], path)) == change['after'], 'RPCS3 reviewed source differs')
    return routes


def source_contract():
    value = pins()
    baseline_receipt()
    require(os.environ.get('BUILD_NUMBER', str(BUILD)) == str(BUILD), 'Wrong build number')
    require(os.environ.get('GITHUB_REF_NAME', 'Claude') == 'Claude', 'Wrong branch')
    require(not git('diff', '--name-only') and git('write-tree') == git('rev-parse', 'HEAD^{tree}'),
            'Tracked source changed after checkout')
    require(git('rev-parse', BASE + '^{tree}') == BASE_TREE, 'Delivered source tree differs')
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, value['reviewedSource']], cwd=ROOT, check=True)
    subprocess.run(['git', 'merge-base', '--is-ancestor', CONCURRENT_HOST_DELTA['source'],
                    value['reviewedSource']], cwd=ROOT, check=True)
    subprocess.run(['git', 'merge-base', '--is-ancestor', value['reviewedSource'], 'HEAD'], cwd=ROOT, check=True)
    changes = git('diff', '--name-only', BASE, 'HEAD', '--', *PRODUCTS).splitlines()
    require(set(changes) == set(value['productDelta']), 'Unreviewed product delta from delivered605')
    for path, change in value['productDelta'].items():
        before = original(BASE, path)
        require((sha(before) if before is not None else None) == change['before'], 'Wrong product preimage: ' + path)
        current = (ROOT / path).read_bytes() if (ROOT / path).is_file() else None
        require((sha(current) if current is not None else None) == change['after'], 'Wrong product postimage: ' + path)
    require({p: git('rev-parse', 'HEAD:' + p) for p in PRODUCTS} == value['productTrees'],
            'Product tree differs from reviewed candidate')
    require({p: git('rev-parse', value['reviewedSource'] + ':' + p) for p in PRODUCTS} == value['productTrees'],
            'Product tree differs from compiled/tested source')
    reviewed_changes = git('diff', '--name-only', BASE, value['reviewedSource']).splitlines()
    require(set(reviewed_changes) == set(value['sourceDelta']), 'Reviewed source closure changed')
    for path, expected in value['sourceDelta'].items():
        raw = original(value['reviewedSource'], path)
        require((sha(raw) if raw is not None else None) == expected, 'Reviewed source identity drift: ' + path)
    late = git('diff', '--name-only', value['reviewedSource'], 'HEAD').splitlines()
    require(all(p in RECIPE or p == 'AGENTS.md' or p.startswith('docs/') for p in late),
            'Non-recipe source changed after validation: ' + repr(late))
    # New source can never silently alter the delivered RA plugin or its menus.
    require(not git('diff', '--name-only', BASE, 'HEAD', '--',
        'packages/achievement_translation', 'lib/services/achievement_translation_service.dart',
        'lib/widgets/secondary_achievement_item.dart'), 'Unreviewed achievement implementation change')
    workflow = (ROOT / '.github/workflows/rewind606-hogwarts-performance-delivery.yml').read_text()
    for name, expected in COMPONENTS.items():
        matches = re.findall(r'^\s+' + re.escape(name) + r':\s*([^\r\n]+)$', workflow, re.MULTILINE)
        require(len(matches) == 1 and matches[0].strip().strip('\"\'') == expected, 'Wrong retained component pin: ' + name)
    from helper_initialization import verify as verify_helper
    verify_helper()
    reviewed_routing()
    return dict(result='passed', build=BUILD, source=git('rev-parse', 'HEAD'), tree=git('rev-parse', 'HEAD^{tree}'),
                reviewedSource=value['reviewedSource'], baseline=value['baseline'],
                concurrentHostDelta=value['concurrentHostDelta'],
                productTrees=value['productTrees'], productDelta=value['productDelta'],
                componentPins=COMPONENTS, rebuiltForDelivery=[], separateNewCore='MeloNX',
                physicalDeviceTested=False, gameTested=False, fpsGainProven=False)


def verify():
    sys.path[:0] = [str(ROOT / 'build-utils'), str(ROOT / 'build-utils/melonx')]
    from delivery_contract_memo import reuse
    return reuse('606-source', source_contract)

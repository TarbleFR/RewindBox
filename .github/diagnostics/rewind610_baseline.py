"""Build610: delivered609 plus the RA credentials fix, the Core 610 lot and its profile changes.

The scope is written by the integrator before committing, never by CI. It binds
every changed tracked byte and file mode to the delivered609 source
(3d92f19e). Product paths may differ only where the reviewed RetroAchievements
credentials fix (45d19d76, committed after IPA609) or the reviewed RPCS3 title
profile and GameDB publication changes touched them; the RPCS3 Core itself is
compiled by the separate Core 610 route from build-utils/rpcs3 (not by Xcode).
Dolphin, ARMSX2, libretro and MeloNX native inputs and their delivered
producers stay byte-identical, and so does the 609 delivery recipe.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BUILD = 610
BASE = '3d92f19ee9c1e37d0813bc4a44a775923ccc2f5a'
BASE_TREE = '5b8090c5cc3a7410c3bdece0888c6470acd4da20'
RA_FIX = '45d19d76'
CONFIG = 'build-utils/rewind610-source-scope.json'
INVENTORY = 'build-utils/rewind610-native-inventory.json'
PUBLIC_KEY = 'build-utils/delivery-610-recipient.pem'
RECEIPT609 = 'docs/evidence/rewind609/delivery.json'
PRODUCTS = ('lib', 'native', 'packages', 'assets', 'pubspec.yaml', 'pubspec.lock')
# Reviewed RPCS3 Dart changes of the Core 610 lot (AC profile, DW6 decoder, GameDB keys)
# and the guest-relay preparation before every RPCS3 boot.
RPCS3_PRODUCT_PATHS = ('lib/services/rpcs3_config_adapter.dart', 'lib/services/rpcs3_game_profile_service.dart',
                       'lib/services/rpcs3_internal_service.dart')
# Reviewed NeoSwap host change: the prepareGuestRelay request. Neither file is a
# Core input nor a MoltenVK dependency input; the NeoSwap headers the Core shares
# (NeoSwap.h, NeoSwapClientStats.h, NeoSwapCompilerAPI.h, NeoSwapCompilerBudget.h,
# NeoSwapRelay.h) and every other NeoSwap source stay byte-identical.
NEOSWAP_PRODUCT_PATHS = ('packages/neo_swap/ios/Classes/NeoSwapPlugin.mm', 'packages/neo_swap/lib/neo_swap.dart')
# Concurrent MeloNX diagnostics (another session) committed before this build:
# MeloNX Core preparation inputs only (compiled by the MeloNX Core producer,
# never by Xcode; the adapter is not wired yet). IPA610 retains the delivered609
# MeloNX Core, so these bytes are present in the source but not compiled into it.
CONCURRENT_UNCOMPILED = {
    'native/melonx/EmbeddedPerformanceDiagnostics.cs': '2e0793ac6f9fbf384cbd557f1a4575c4154c898f',
    'build-utils/melonx/adapt_gpu_work_diagnostics.py': '2e0793ac6f9fbf384cbd557f1a4575c4154c898f',
}
# Inputs of the retained engines, the delivered recipes and the MeloNX liveness
# Core; none may change for this build.
PRESERVED = ('native', 'assets', 'pubspec.yaml', 'pubspec.lock',
             'packages/dolphin_internal_bridge/core', 'packages/armsx2_internal_bridge/core',
             'packages/armsx2_internal_bridge/ios/Classes/ARMSX2CoreABI.h',
             'packages/dolphin_internal_bridge/ci/build_support.py', 'packages/dolphin_internal_bridge/ci/verify_ipa.py',
             'packages/rpcs3_internal_bridge', 'packages/neo_swap', 'packages/melonx_internal_bridge',
             'packages/melonx_jit_helper',
             'build-utils/armsx2', 'build-utils/libretro', 'build-utils/stikjit', 'build-utils/melonx',
             'build-utils/patch_dolphin_internal_core_v2.py', 'build-utils/delivery-609-recipient.pem',
             'build-utils/rewind609-native-inventory.json', 'build-utils/rewind609-source-scope.json',
             '.github/workflows/rewind609-hogwarts-liveness-delivery.yml',
             '.github/workflows/rewind608-retro-achievements-delivery.yml',
             '.github/workflows/melonx-core.yml', '.github/workflows/rpcs3-mvk-cache-core.yml',
             '.github/diagnostics/rewind609_baseline.py', '.github/diagnostics/rewind609_delivery.py',
             '.github/diagnostics/rewind609_engine.py',
             '.github/diagnostics/rewind608_baseline.py', '.github/diagnostics/rewind608_checks.py',
             '.github/diagnostics/rewind608_delivery.py', '.github/diagnostics/rewind608_producers.py',
             '.github/diagnostics/rewind608_reuse.py', '.github/diagnostics/rpcs3runtime607_core.py',
             '.github/diagnostics/rewind607_delivery.py', '.github/diagnostics/rewind606_engine.py',
             '.github/diagnostics/rewind606_baseline.py', '.github/diagnostics/rewind596_engine.py',
             '.github/diagnostics/rpcs3_mvk_cache_core.py', '.github/diagnostics/rpcs3_mvk_dependency_artifact.py')
BASELINE = dict(build=609, source=BASE, tree=BASE_TREE, run=41325785563, job=124905435858, attempt=1,
                ipaBytes=189813193, ipaSHA256='7908d1283f722e6b8ed7999c374aab073736740a4cb9f0ce588468bf95620f97')


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, timeout=120).strip()


def safe_path(name):
    path = Path(name)
    require(bool(name) and not path.is_absolute() and '..' not in path.parts and
            '\\' not in name and ':' not in name, 'Unsafe source path: ' + name)
    return ROOT / path


def original(path, source=BASE):
    entry = git('ls-tree', source, '--', path)
    if not entry:
        return None, None
    mode, kind, _ = entry.partition('\t')[0].split()
    require(kind == 'blob', 'Expected a baseline file: ' + path)
    raw = subprocess.check_output(['git', 'show', source + ':' + path], cwd=ROOT, timeout=120)
    return raw, mode


def current(path):
    target = safe_path(path)
    if not target.exists():
        return None, None
    require(target.is_file() and not target.is_symlink(), 'Non-regular delivery input: ' + path)
    return target.read_bytes(), '100755' if target.stat().st_mode & stat.S_IXUSR else '100644'


def change_record(path):
    before, before_mode = original(path)
    after, after_mode = current(path)
    return dict(before=sha(before) if before is not None else None,
                after=sha(after) if after is not None else None,
                modeBefore=before_mode, modeAfter=after_mode)


def changed_paths(include_untracked=False):
    paths = set(git('diff', '--no-renames', '--name-only', BASE, '--').splitlines())
    if include_untracked:
        paths.update(git('ls-files', '--others', '--exclude-standard').splitlines())
    paths.discard(CONFIG)
    return sorted(paths)


def is_product(path):
    return any(path == root or path.startswith(root + '/') for root in PRODUCTS)


def ra_fix_product_paths():
    """Product paths of the reviewed RA credentials fix, read from its own commit."""
    commit = git('rev-parse', RA_FIX + '^{commit}')
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, commit], cwd=ROOT, check=True)
    paths = git('diff-tree', '--no-commit-id', '--name-only', '-r', '--no-renames', commit).splitlines()
    return commit, sorted(p for p in paths if is_product(p))


def concurrent_uncompiled():
    """Exact bytes of the reviewed concurrent MeloNX diagnostics commit."""
    result = {}
    for path, commit in CONCURRENT_UNCOMPILED.items():
        subprocess.run(['git', 'merge-base', '--is-ancestor', commit, 'HEAD'], cwd=ROOT, check=True)
        result[path] = sha(subprocess.check_output(['git', 'show', commit + ':' + path], cwd=ROOT, timeout=60))
    return result


def check_product_delta(product):
    commit, ra_paths = ra_fix_product_paths()
    concurrent = {p: d for p, d in concurrent_uncompiled().items() if is_product(p)}
    for path, digest in concurrent.items():
        require(product.get(path, {}).get('after') == digest, 'Concurrent MeloNX input differs from its commit: ' + path)
    allowed = set(ra_paths) | set(RPCS3_PRODUCT_PATHS) | set(NEOSWAP_PRODUCT_PATHS) | set(concurrent)
    require(set(product) <= allowed, 'Unreviewed product change: ' + repr(sorted(set(product) - allowed)))
    require(set(ra_paths) <= set(product), 'The RA credentials fix is not fully contained')
    require(set(NEOSWAP_PRODUCT_PATHS) <= set(product), 'The reviewed NeoSwap relay change is not contained')
    for path in ra_paths:
        if path in RPCS3_PRODUCT_PATHS:
            continue
        # Each RA path carries exactly the fix's bytes (nothing else touched it since).
        fixed = subprocess.check_output(['git', 'show', commit + ':' + path], cwd=ROOT, timeout=60)
        require(product[path]['after'] == sha(fixed), 'RA path differs from the reviewed fix: ' + path)
    for record in product.values():
        require(record['modeAfter'] in (None, '100644'), 'Unexpected product file mode')
    return dict(raFix=commit, raProductPaths=len(ra_paths), rpcs3ProductPaths=sorted(set(product) & set(RPCS3_PRODUCT_PATHS)),
                neoswapProductPaths=sorted(NEOSWAP_PRODUCT_PATHS), concurrentUncompiledProductPaths=sorted(concurrent))


def check_preserved(target='HEAD'):
    concurrent = concurrent_uncompiled()
    reviewed = set(concurrent) | set(NEOSWAP_PRODUCT_PATHS)
    for path in PRESERVED:
        arguments = ('diff', '--name-only', BASE, target, '--', path) if target else ('diff', '--name-only', BASE, '--', path)
        changed = set(git(*arguments).splitlines())
        require(changed <= reviewed, 'Retained609 component changed: ' + path + ' ' + repr(sorted(changed - reviewed)))
        for name in changed & set(concurrent):
            require(sha(safe_path(name).read_bytes()) == concurrent[name], 'Concurrent MeloNX input changed again: ' + name)


def freeze():
    """Explicit local integration operation; CI must never call this."""
    require(not os.environ.get('CI') and not os.environ.get('GITHUB_ACTIONS'), 'The reviewed scope may not be generated in CI')
    require(git('branch', '--show-current') == 'Claude', 'Freeze only the Claude checkout')
    require(git('rev-parse', BASE + '^{tree}') == BASE_TREE, 'Delivered609 source tree differs')
    check_preserved(target=None)
    paths = changed_paths(include_untracked=True)
    require(all(p.startswith(('.github/', 'build-utils/', 'test/', 'docs/', 'lib/', 'packages/')) or p == 'AGENTS.md'
                or p in CONCURRENT_UNCOMPILED for p in paths), 'Unexpected source scope; inspect before freezing')
    source = {p: change_record(p) for p in paths}
    product = {p: v for p, v in source.items() if is_product(p)}
    review = check_product_delta(product)
    receipt = safe_path(RECEIPT609).read_bytes()
    value = dict(schema=1, build=BUILD, baseline=dict(BASELINE, receipt=RECEIPT609, receiptSHA256=sha(receipt)),
        sourceDelta=source, productDelta=product, productReview=review,
        nativeInventorySHA256=sha(safe_path(INVENTORY).read_bytes()),
        publicKeySHA256=sha(safe_path(PUBLIC_KEY).read_bytes()),
        scopeGeneratedInCI=False, physicalDeviceTested=False)
    safe_path(CONFIG).write_text(json.dumps(value, indent=2) + '\n')
    return dict(result='frozen-for-review', sourcePaths=len(source), productPaths=len(product), path=CONFIG)


def pins():
    value = json.loads(safe_path(CONFIG).read_bytes())
    require(value['schema'] == 1 and value['build'] == BUILD and value['scopeGeneratedInCI'] is False,
            'Missing reviewed610 source scope')
    receipt = safe_path(RECEIPT609).read_bytes()
    require(value['baseline'] == dict(BASELINE, receipt=RECEIPT609, receiptSHA256=sha(receipt)),
            'Wrong delivered609 product baseline')
    delivered = json.loads(receipt)
    require(delivered['result'] == 'delivered-and-verified' and delivered['build'] == 609 and
            delivered['execution']['runConclusion'] == delivered['execution']['jobConclusion'] == 'success' and
            delivered['execution']['source'] == BASE and delivered['execution']['tree'] == BASE_TREE and
            delivered['execution']['run'] == BASELINE['run'] and delivered['execution']['job'] == BASELINE['job'] and
            delivered['ipa']['sha256'] == BASELINE['ipaSHA256'] and delivered['ipa']['bytes'] == BASELINE['ipaBytes'],
            'Delivered609 receipt differs from the pinned baseline')
    require(value['sourceDelta'] and value['productDelta'], 'Empty reviewed610 delta')
    return value


def source_contract():
    value = pins()
    require(os.environ.get('BUILD_NUMBER', '610') == '610' and
            os.environ.get('GITHUB_REF_NAME', 'Claude') == 'Claude', 'Wrong delivery branch/build')
    require(git('rev-parse', 'HEAD') == os.environ.get('GITHUB_SHA', git('rev-parse', 'HEAD')),
            'Checkout differs from triggering source')
    require(not git('diff', '--name-only') and git('write-tree') == git('rev-parse', 'HEAD^{tree}'),
            'Tracked checkout changed after commit')
    require(git('rev-parse', BASE + '^{tree}') == BASE_TREE, 'Delivered609 source tree differs')
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, 'HEAD'], cwd=ROOT, check=True)
    require(set(changed_paths()) == set(value['sourceDelta']), 'Unreviewed source addition/deletion')
    for path, record in value['sourceDelta'].items():
        require(change_record(path) == record, 'Reviewed source bytes or file mode changed: ' + path)
    require(value['productDelta'] == {p: r for p, r in value['sourceDelta'].items() if is_product(p)},
            'Product delta does not cover the exact source changes')
    require(check_product_delta(value['productDelta']) == value['productReview'], 'Product review changed')
    check_preserved()
    for path, key in ((INVENTORY, 'nativeInventorySHA256'), (PUBLIC_KEY, 'publicKeySHA256')):
        require(sha(safe_path(path).read_bytes()) == value[key], 'Delivery review input changed: ' + path)
    require(safe_path(PUBLIC_KEY).read_text().startswith('-----BEGIN PUBLIC KEY-----'), 'Delivery610 needs the recipient public key')
    require(json.loads(safe_path('build-utils/armsx2/source.json').read_bytes())['abi_version'] == 9,
            'Build610 retains the ARMSX2 launch-policy ABI9')
    sys.path[:0] = [str(ROOT / 'build-utils'), str(ROOT / 'build-utils/melonx')]
    from helper_initialization import verify as verify_helper
    from collect_build_source_evidence import repository_inputs
    verify_helper()
    repository_inputs(ROOT)
    return dict(result='passed', build=BUILD, source=git('rev-parse', 'HEAD'),
        tree=git('rev-parse', 'HEAD^{tree}'), baseline=value['baseline'],
        productDelta=value['productDelta'], productReview=value['productReview'],
        reviewedSourceScopeSHA256=sha(safe_path(CONFIG).read_bytes()),
        productTrees={p: git('rev-parse', 'HEAD:' + p) for p in PRODUCTS},
        rebuiltForDelivery=['Flutter application', 'RPCS3 Core 610 (separate Core route)'],
        freshTests=['Flutter and source contracts', 'Xcode16.4 native tests'],
        retainedFrom609=['MeloNX liveness Core', 'Dolphin session Core', 'ARMSX2 ABI9 Core', 'libretro core binaries',
                         'MeloNX native dependencies'],
        physicalDeviceTested=False)


def verify():
    sys.path.insert(0, str(ROOT / 'build-utils'))
    from delivery_contract_memo import reuse
    return reuse('610-source', source_contract)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['freeze', 'verify'])
    args = parser.parse_args()
    print(json.dumps(globals()[args.operation](), indent=2))

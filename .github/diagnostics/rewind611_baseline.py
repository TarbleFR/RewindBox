"""Build611: exact delivered609 application plus the reviewed fragmented-read MeloNX Core.

The scope is written by the integrator before committing, never by CI. It binds
every changed tracked byte and file mode to the delivered609 source (3d92f19e).
The concurrent 610 lot (RetroAchievements credentials fix, RPCS3 Core 610 Dart
profiles and recipe, NeoSwap relay) was committed after IPA609 and is not built
into IPA611: every one of its paths that the application build, the retained
engines or the reused test evidence read is restored to its delivered609 bytes
in the build checkout before any check or compilation, and the source contract
proves the restored checkout equals delivered609 outside the reviewed delta.
The only product path that differs is the MeloNX Core preparation input
compiled by the frozen fragmented-read Core contract; Xcode never compiles it.
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
BUILD = 611
BASE = '3d92f19ee9c1e37d0813bc4a44a775923ccc2f5a'
BASE_TREE = '5b8090c5cc3a7410c3bdece0888c6470acd4da20'
CONFIG = 'build-utils/rewind611-source-scope.json'
INVENTORY = 'build-utils/rewind611-native-inventory.json'
PUBLIC_KEY = 'build-utils/delivery-611-recipient.pem'
CORE_CONTRACT = 'build-utils/melonx/reads-core-contract.json'
RECEIPT609 = 'docs/evidence/rewind609/delivery.json'
PRODUCTS = ('lib', 'native', 'packages', 'assets', 'pubspec.yaml', 'pubspec.lock')
# Compiled into Ryujinx.Library.dylib by the Core producer, never by Xcode.
CORE_PRODUCT_INPUTS = ('native/melonx/EmbeddedPerformanceDiagnostics.cs',)
# Everything the application build, the retained engines, the delivered609
# recipe this build reuses and the reused608 test evidence read from the
# repository. After restoration none may differ from delivered609.
PRESERVED = ('lib', 'assets', 'packages', 'pubspec.yaml', 'pubspec.lock',
             'native/armsx2_internal_helper', 'native/cheats', 'native/dolphin_internal_helper',
             'native/dolphin_motion', 'native/dolphin_shaders', 'native/dolphin_textures',
             'native/enhancements', 'native/import-memory-candidate.json', 'native/melonx_internal_helper',
             'native/neoswap', 'native/neoswap-donation', 'native/neoswap-relay', 'native/neoswap-storage',
             'native/nestopia', 'native/ppsspp', 'native/rpcs3_internal_helper', 'native/textures',
             'build-utils/rpcs3', 'build-utils/armsx2', 'build-utils/libretro', 'build-utils/stikjit',
             'build-utils/patch_dolphin_internal_core_v2.py', 'build-utils/delivery-608-recipient.pem',
             'build-utils/rewind608-native-inventory.json', 'build-utils/delivery-609-recipient.pem',
             'build-utils/rewind609-native-inventory.json', 'build-utils/rewind609-source-scope.json',
             '.github/workflows/rewind608-retro-achievements-delivery.yml',
             '.github/workflows/rewind609-hogwarts-liveness-delivery.yml',
             '.github/diagnostics/rewind609_baseline.py', '.github/diagnostics/rewind609_delivery.py',
             '.github/diagnostics/rewind609_engine.py',
             '.github/diagnostics/rewind608_baseline.py', '.github/diagnostics/rewind608_checks.py',
             '.github/diagnostics/rewind608_delivery.py', '.github/diagnostics/rewind608_producers.py',
             '.github/diagnostics/rewind608_reuse.py', '.github/diagnostics/rpcs3runtime607_core.py',
             '.github/diagnostics/rewind607_delivery.py', '.github/diagnostics/rewind606_engine.py',
             '.github/diagnostics/rewind606_baseline.py', '.github/diagnostics/rewind596_engine.py')
# Test paths the reused608 groups execute; the delta may add tests but not change these.
REUSED_TEST_ROOTS = ('test/support', 'test/rewind608_delivery_contract_test.py', 'test/rewind608_reuse_test.py')
# Prefixes a path may have when it changes after 609 and stays unrestored (it is not read by this build).
UNBUILT_PREFIXES = ('.github/', 'build-utils/', 'test/', 'docs/', 'native/melonx/')
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


def record(before, before_mode, after, after_mode):
    return dict(before=sha(before) if before is not None else None,
                after=sha(after) if after is not None else None,
                modeBefore=before_mode, modeAfter=after_mode)


def change_record(path, source=None):
    """BASE against the working tree, or against a commit when ``source`` is given."""
    before, before_mode = original(path)
    after, after_mode = original(path, source) if source else current(path)
    return record(before, before_mode, after, after_mode)


def changed_paths(include_untracked=False, target='HEAD'):
    """Paths that differ from BASE in ``target`` (a commit), or in the working tree when ``target`` is None."""
    arguments = ('diff', '--no-renames', '--name-only', BASE, target, '--') if target else \
                ('diff', '--no-renames', '--name-only', BASE, '--')
    paths = set(git(*arguments).splitlines())
    if include_untracked:
        paths.update(git('ls-files', '--others', '--exclude-standard').splitlines())
    paths.discard(CONFIG)
    return sorted(paths)


def is_product(path):
    return any(path == root or path.startswith(root + '/') for root in PRODUCTS)


def is_preserved(path):
    return any(path == root or path.startswith(root + '/') for root in PRESERVED)


def reused_test_paths():
    """The exact files the reused608 Flutter/native groups execute or import."""
    sys.path.insert(0, str(ROOT / '.github/diagnostics'))
    import rewind608_checks as checks
    paths = set(checks.FLUTTER_TESTS) | set(REUSED_TEST_ROOTS)
    for group in checks.GROUPS.values():
        for _, argv in group:
            paths.update(arg for arg in argv if arg.startswith('test/'))
    paths.update({'test/touch_layout_support.py', 'test/libretro_ios_syntax_test.py'})
    return sorted(paths)


def is_reused_test(path, reused):
    return any(path == root or path.startswith(root + '/') for root in reused)


def core_contract_inputs():
    frozen = json.loads(safe_path(CORE_CONTRACT).read_bytes())
    return frozen, frozen['preparationInputs']


def check_product_delta(product):
    require(set(product) == set(CORE_PRODUCT_INPUTS), 'Only the reviewed MeloNX Core input may change: ' + repr(sorted(product)))
    _, inputs = core_contract_inputs()
    for path, value in product.items():
        require(value['after'] is not None and value['after'] == inputs.get(path) and
                value['modeBefore'] == value['modeAfter'] == '100644',
                'Product change is not the frozen fragmented-read Core preparation input: ' + path)


def check_preserved():
    """The restored working tree: every preserved component and reused test equals delivered609."""
    for path in PRESERVED:
        require(not git('diff', '--name-only', BASE, '--', path), 'Retained609 component differs after restoration: ' + path)
    for path in reused_test_paths():
        require(not git('diff', '--name-only', BASE, '--', path), 'Reused608 test input differs after restoration: ' + path)
    require(not git('ls-files', '--others', '--exclude-standard', '--', *PRESERVED), 'Untracked file in a retained609 component')


def restoration_scope(paths):
    reused = reused_test_paths()
    return sorted(p for p in paths if p not in CORE_PRODUCT_INPUTS and
                  (is_preserved(p) or is_product(p) or is_reused_test(p, reused)))


def freeze():
    """Explicit local integration operation; CI must never call this."""
    require(not os.environ.get('CI') and not os.environ.get('GITHUB_ACTIONS'), 'The reviewed scope may not be generated in CI')
    require(git('branch', '--show-current') == 'Claude', 'Freeze only the Claude checkout')
    require(git('rev-parse', BASE + '^{tree}') == BASE_TREE, 'Delivered609 source tree differs')
    require(not git('status', '--porcelain', '--untracked-files=no', '--', *PRESERVED, *CORE_PRODUCT_INPUTS),
            'Freeze the committed application sources only')
    paths = changed_paths(include_untracked=True)
    restored = restoration_scope(paths)
    unbuilt = [p for p in paths if p not in restored]
    require(all(p.startswith(UNBUILT_PREFIXES) or p == 'AGENTS.md' for p in unbuilt),
            'Unexpected source scope; inspect before freezing: ' + repr([p for p in unbuilt if not p.startswith(UNBUILT_PREFIXES)]))
    require(not any(is_preserved(p) for p in unbuilt), 'A retained component would stay changed')
    source = {p: change_record(p) for p in paths}
    # Restoration only rewrites or removes tracked files; it never re-creates a deleted one.
    require(all(source[p]['after'] is not None for p in restored), 'A restored path was deleted after 609')
    product = {p: v for p, v in source.items() if is_product(p) and p not in restored}
    check_product_delta(product)
    previous = json.loads(safe_path(CONFIG).read_bytes()) if safe_path(CONFIG).is_file() else {}
    receipt = safe_path(RECEIPT609).read_bytes()
    value = dict(schema=1, build=BUILD, baseline=dict(BASELINE, receipt=RECEIPT609, receiptSHA256=sha(receipt)),
        sourceDelta=source, productDelta=product, restoredToBaseline=restored,
        coreContractSHA256=sha(safe_path(CORE_CONTRACT).read_bytes()),
        nativeInventorySHA256=sha(safe_path(INVENTORY).read_bytes()),
        publicKeySHA256=sha(safe_path(PUBLIC_KEY).read_bytes()),
        core=previous.get('core'), scopeGeneratedInCI=False, physicalDeviceTested=False)
    safe_path(CONFIG).write_text(json.dumps(value, indent=2) + '\n')
    return dict(result='frozen-for-review', sourcePaths=len(source), productPaths=len(product),
                restoredPaths=len(restored), path=CONFIG, corePinned=bool(value['core']))


def pins():
    value = json.loads(safe_path(CONFIG).read_bytes())
    require(value['schema'] == 1 and value['build'] == BUILD and value['scopeGeneratedInCI'] is False,
            'Missing reviewed611 source scope')
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
    require(value['sourceDelta'] and value['productDelta'], 'Empty reviewed611 delta')
    require(set(value['restoredToBaseline']) <= set(value['sourceDelta']) and
            all(value['sourceDelta'][p]['after'] is not None for p in value['restoredToBaseline']),
            'A restored path is not a reviewed tracked change')
    require(isinstance(value.get('core'), dict) and value['core'].get('source'), 'The fragmented-read Core producer pin is pending')
    return value


def restore():
    """CI and local: rewrite exactly the reviewed concurrent paths to their delivered609 bytes."""
    value = pins()
    require(git('rev-parse', BASE + '^{tree}') == BASE_TREE, 'Delivered609 source tree differs')
    require(not git('diff', '--name-only') and git('write-tree') == git('rev-parse', 'HEAD^{tree}'),
            'Restore only a clean checkout of the triggering commit')
    restored = {}
    for path in value['restoredToBaseline']:
        require(change_record(path, 'HEAD') == value['sourceDelta'][path], 'Restored path differs from the reviewed change: ' + path)
        before, mode = original(path)
        target = safe_path(path)
        if before is None:
            if target.exists():
                target.unlink()
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(before)
            target.chmod(0o755 if mode == '100755' else 0o644)
        restored[path] = dict(headSHA256=value['sourceDelta'][path]['after'], restoredSHA256=sha(before) if before is not None else None)
    return dict(result='restored', build=BUILD, baseline=BASE, restoredPaths=len(restored), paths=restored)


def source_contract():
    value = pins()
    require(os.environ.get('BUILD_NUMBER', '611') == '611' and
            os.environ.get('GITHUB_REF_NAME', 'Claude') == 'Claude', 'Wrong delivery branch/build')
    require(git('rev-parse', 'HEAD') == os.environ.get('GITHUB_SHA', git('rev-parse', 'HEAD')),
            'Checkout differs from triggering source')
    require(git('rev-parse', BASE + '^{tree}') == BASE_TREE, 'Delivered609 source tree differs')
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, 'HEAD'], cwd=ROOT, check=True)
    # The committed source is exactly the reviewed delta.
    require(git('write-tree') == git('rev-parse', 'HEAD^{tree}'), 'The index differs from the triggering commit')
    require(set(changed_paths()) == set(value['sourceDelta']), 'Unreviewed source addition/deletion')
    for path, expected in value['sourceDelta'].items():
        require(change_record(path, 'HEAD') == expected, 'Reviewed source bytes or file mode changed: ' + path)
    # The checkout differs from that commit only by the restoration, and each restored path is delivered609.
    restored = set(value['restoredToBaseline'])
    require(set(git('diff', '--name-only').splitlines()) == restored and
            not git('ls-files', '--others', '--exclude-standard', '--', *restored),
            'The checkout is not exactly the restored611 source')
    for path in restored:
        before, mode = original(path)
        after, after_mode = current(path)
        require(after == before and after_mode == mode, 'Path not restored to delivered609: ' + path)
    effective = {p: change_record(p) for p in changed_paths(target=None)}
    require(set(effective) == set(value['sourceDelta']) - restored, 'Restored checkout differs from the reviewed effective delta')
    product = {p: r for p, r in effective.items() if is_product(p)}
    require(product == value['productDelta'], 'Product delta does not cover the exact effective changes')
    check_product_delta(product)
    check_preserved()
    for path, key in ((CORE_CONTRACT, 'coreContractSHA256'), (INVENTORY, 'nativeInventorySHA256'),
                      (PUBLIC_KEY, 'publicKeySHA256')):
        require(sha(safe_path(path).read_bytes()) == value[key], 'Delivery review input changed: ' + path)
    require(value['core']['contractSha256'] == value['coreContractSHA256'], 'Core pin uses another contract')
    require(safe_path(PUBLIC_KEY).read_text().startswith('-----BEGIN PUBLIC KEY-----'), 'Delivery611 needs the recipient public key')
    require(json.loads(safe_path('build-utils/armsx2/source.json').read_bytes())['abi_version'] == 9,
            'Build611 retains the ARMSX2 launch-policy ABI9')
    sys.path[:0] = [str(ROOT / 'build-utils'), str(ROOT / 'build-utils/melonx')]
    from helper_initialization import verify as verify_helper
    from collect_build_source_evidence import repository_inputs
    verify_helper()
    repository_inputs(ROOT)
    return dict(result='passed', build=BUILD, source=git('rev-parse', 'HEAD'),
        tree=git('rev-parse', 'HEAD^{tree}'), baseline=value['baseline'],
        productDelta=value['productDelta'], restoredToBaseline=sorted(restored),
        reviewedSourceScopeSHA256=sha(safe_path(CONFIG).read_bytes()),
        productTrees={p: git('rev-parse', BASE + ':' + p) for p in PRODUCTS if p != 'native'},
        applicationSourceEqualsDelivered609ExceptCoreInput=True,
        rebuiltForDelivery=['Flutter application'], newCore='MeloNX fragmented-read Core',
        retainedFrom609=['RPCS3 ABI30', 'Dolphin session Core', 'ARMSX2 ABI9 Core', 'libretro core binaries',
                         'MeloNX native dependencies', 'Flutter and native test evidence (608)'],
        concurrent610LotBuilt=False, physicalDeviceTested=False)


def verify():
    sys.path.insert(0, str(ROOT / 'build-utils'))
    from delivery_contract_memo import reuse
    return reuse('611-source', source_contract)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['freeze', 'restore', 'verify'])
    args = parser.parse_args()
    print(json.dumps(globals()[args.operation](), indent=2))

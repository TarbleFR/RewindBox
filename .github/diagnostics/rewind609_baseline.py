"""Build609: exact delivered608 application plus the reviewed liveness MeloNX Core.

The scope is written by the integrator before committing, never by CI. It binds
every changed tracked byte and file mode to the delivered608 source. The only
product path allowed to differ is the MeloNX Core preparation input compiled by
the frozen liveness Core contract; Xcode never compiles it. Every other engine,
plugin, Dart source, asset and dependency lock must stay byte-identical.
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
BUILD = 609
BASE = '90a9e8fcaa9bf68e2f5a2270cab6b636d62fff07'
BASE_TREE = '067a0be8c34e44247f7abcdf6fd8bb4aeedf52f3'
CONFIG = 'build-utils/rewind609-source-scope.json'
INVENTORY = 'build-utils/rewind609-native-inventory.json'
PUBLIC_KEY = 'build-utils/delivery-609-recipient.pem'
CORE_CONTRACT = 'build-utils/melonx/liveness-core-contract.json'
RECEIPT608 = 'docs/evidence/rewind608/delivery.json'
PRODUCTS = ('lib', 'native', 'packages', 'assets', 'pubspec.yaml', 'pubspec.lock')
# Compiled into Ryujinx.Library.dylib by the Core producer, never by Xcode.
CORE_PRODUCT_INPUTS = ('native/melonx/EmbeddedPerformanceDiagnostics.cs',)
# Everything the application build, the retained engines and the reused608
# test evidence read from the repository. None may change for this Core-only build.
PRESERVED = ('lib', 'assets', 'packages', 'pubspec.yaml', 'pubspec.lock',
             'native/armsx2_internal_helper', 'native/cheats', 'native/dolphin_internal_helper',
             'native/dolphin_motion', 'native/dolphin_shaders', 'native/dolphin_textures',
             'native/enhancements', 'native/import-memory-candidate.json', 'native/melonx_internal_helper',
             'native/neoswap', 'native/neoswap-donation', 'native/neoswap-relay', 'native/neoswap-storage',
             'native/nestopia', 'native/ppsspp', 'native/rpcs3_internal_helper', 'native/textures',
             'build-utils/rpcs3', 'build-utils/armsx2', 'build-utils/libretro', 'build-utils/stikjit',
             'build-utils/patch_dolphin_internal_core_v2.py', 'build-utils/delivery-608-recipient.pem',
             'build-utils/rewind608-native-inventory.json',
             '.github/workflows/rewind608-retro-achievements-delivery.yml',
             '.github/diagnostics/rewind608_baseline.py', '.github/diagnostics/rewind608_checks.py',
             '.github/diagnostics/rewind608_delivery.py', '.github/diagnostics/rewind608_producers.py',
             '.github/diagnostics/rewind608_reuse.py', '.github/diagnostics/rpcs3runtime607_core.py',
             '.github/diagnostics/rewind607_delivery.py', '.github/diagnostics/rewind606_engine.py',
             '.github/diagnostics/rewind606_baseline.py', '.github/diagnostics/rewind596_engine.py')
# Test paths the reused608 groups execute; the delta may add tests but not change these.
REUSED_TEST_ROOTS = ('test/support', 'test/rewind608_delivery_contract_test.py', 'test/rewind608_reuse_test.py')
BASELINE = dict(build=608, source=BASE, tree=BASE_TREE, run=41303386398, job=124838986809, attempt=1,
                ipaBytes=189825138, ipaSHA256='575321ba6daed2678bedbb7da2a8412930bffb7f67c340980a235ee46c95450d')


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


def core_contract_inputs():
    frozen = json.loads(safe_path(CORE_CONTRACT).read_bytes())
    return frozen, frozen['preparationInputs']


def check_product_delta(product):
    require(set(product) == set(CORE_PRODUCT_INPUTS), 'Only the reviewed MeloNX Core input may change: ' + repr(sorted(product)))
    _, inputs = core_contract_inputs()
    for path, record in product.items():
        require(record['after'] is not None and record['after'] == inputs.get(path) and
                record['modeBefore'] == record['modeAfter'] == '100644',
                'Product change is not the frozen liveness Core preparation input: ' + path)


def check_preserved(target='HEAD'):
    for path in PRESERVED:
        arguments = ('diff', '--name-only', BASE, target, '--', path) if target else ('diff', '--name-only', BASE, '--', path)
        require(not git(*arguments), 'Retained608 component changed: ' + path)
    for path in reused_test_paths():
        arguments = ('diff', '--name-only', BASE, target, '--', path) if target else ('diff', '--name-only', BASE, '--', path)
        require(not git(*arguments), 'Reused608 test input changed: ' + path)


def freeze():
    """Explicit local integration operation; CI must never call this."""
    require(not os.environ.get('CI') and not os.environ.get('GITHUB_ACTIONS'), 'The reviewed scope may not be generated in CI')
    require(git('branch', '--show-current') == 'Claude', 'Freeze only the Claude checkout')
    require(git('rev-parse', BASE + '^{tree}') == BASE_TREE, 'Delivered608 source tree differs')
    check_preserved(target=None)
    paths = changed_paths(include_untracked=True)
    require(all(p.startswith(('.github/', 'build-utils/', 'test/', 'docs/', 'native/melonx/')) or p == 'AGENTS.md'
                for p in paths), 'Unexpected source scope; inspect before freezing')
    source = {p: change_record(p) for p in paths}
    product = {p: v for p, v in source.items() if is_product(p)}
    check_product_delta(product)
    previous = json.loads(safe_path(CONFIG).read_bytes()) if safe_path(CONFIG).is_file() else {}
    receipt = safe_path(RECEIPT608).read_bytes()
    value = dict(schema=1, build=BUILD, baseline=dict(BASELINE, receipt=RECEIPT608, receiptSHA256=sha(receipt)),
        sourceDelta=source, productDelta=product,
        coreContractSHA256=sha(safe_path(CORE_CONTRACT).read_bytes()),
        nativeInventorySHA256=sha(safe_path(INVENTORY).read_bytes()),
        publicKeySHA256=sha(safe_path(PUBLIC_KEY).read_bytes()),
        core=previous.get('core'), scopeGeneratedInCI=False, physicalDeviceTested=False)
    safe_path(CONFIG).write_text(json.dumps(value, indent=2) + '\n')
    return dict(result='frozen-for-review', sourcePaths=len(source), productPaths=len(product), path=CONFIG,
                corePinned=bool(value['core']))


def pins():
    value = json.loads(safe_path(CONFIG).read_bytes())
    require(value['schema'] == 1 and value['build'] == BUILD and value['scopeGeneratedInCI'] is False,
            'Missing reviewed609 source scope')
    receipt = safe_path(RECEIPT608).read_bytes()
    require(value['baseline'] == dict(BASELINE, receipt=RECEIPT608, receiptSHA256=sha(receipt)),
            'Wrong delivered608 product baseline')
    delivered = json.loads(receipt)
    require(delivered['result'] == 'delivered-and-verified' and delivered['build'] == 608 and
            delivered['execution']['runConclusion'] == delivered['execution']['jobConclusion'] == 'success' and
            delivered['execution']['source'] == BASE and delivered['execution']['tree'] == BASE_TREE and
            delivered['execution']['run'] == BASELINE['run'] and delivered['execution']['job'] == BASELINE['job'] and
            delivered['ipa']['sha256'] == BASELINE['ipaSHA256'] and delivered['ipa']['bytes'] == BASELINE['ipaBytes'],
            'Delivered608 receipt differs from the pinned baseline')
    require(value['sourceDelta'] and value['productDelta'], 'Empty reviewed609 delta')
    require(isinstance(value.get('core'), dict) and value['core'].get('source'), 'The liveness Core producer pin is pending')
    return value


def source_contract():
    value = pins()
    require(os.environ.get('BUILD_NUMBER', '609') == '609' and
            os.environ.get('GITHUB_REF_NAME', 'Claude') == 'Claude', 'Wrong delivery branch/build')
    require(git('rev-parse', 'HEAD') == os.environ.get('GITHUB_SHA', git('rev-parse', 'HEAD')),
            'Checkout differs from triggering source')
    require(not git('diff', '--name-only') and git('write-tree') == git('rev-parse', 'HEAD^{tree}'),
            'Tracked checkout changed after commit')
    require(git('rev-parse', BASE + '^{tree}') == BASE_TREE, 'Delivered608 source tree differs')
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, 'HEAD'], cwd=ROOT, check=True)
    require(set(changed_paths()) == set(value['sourceDelta']), 'Unreviewed source addition/deletion')
    for path, record in value['sourceDelta'].items():
        require(change_record(path) == record, 'Reviewed source bytes or file mode changed: ' + path)
    require(value['productDelta'] == {p: r for p, r in value['sourceDelta'].items() if is_product(p)},
            'Product delta does not cover the exact source changes')
    check_product_delta(value['productDelta'])
    check_preserved()
    for path, key in ((CORE_CONTRACT, 'coreContractSHA256'), (INVENTORY, 'nativeInventorySHA256'),
                      (PUBLIC_KEY, 'publicKeySHA256')):
        require(sha(safe_path(path).read_bytes()) == value[key], 'Delivery review input changed: ' + path)
    require(value['core']['contractSha256'] == value['coreContractSHA256'], 'Core pin uses another contract')
    require(safe_path(PUBLIC_KEY).read_text().startswith('-----BEGIN PUBLIC KEY-----'), 'Delivery609 needs the recipient public key')
    require(json.loads(safe_path('build-utils/armsx2/source.json').read_bytes())['abi_version'] == 9,
            'Build609 retains the ARMSX2 launch-policy ABI9')
    sys.path[:0] = [str(ROOT / 'build-utils'), str(ROOT / 'build-utils/melonx')]
    from helper_initialization import verify as verify_helper
    from collect_build_source_evidence import repository_inputs
    verify_helper()
    repository_inputs(ROOT)
    return dict(result='passed', build=BUILD, source=git('rev-parse', 'HEAD'),
        tree=git('rev-parse', 'HEAD^{tree}'), baseline=value['baseline'],
        productDelta=value['productDelta'], reviewedSourceScopeSHA256=sha(safe_path(CONFIG).read_bytes()),
        productTrees={p: git('rev-parse', 'HEAD:' + p) for p in PRODUCTS},
        applicationSourceUnchangedExceptCoreInput=True,
        rebuiltForDelivery=['Flutter application'], newCore='MeloNX liveness Core',
        retainedFrom608=['RPCS3 ABI30', 'Dolphin session Core', 'ARMSX2 ABI9 Core', 'libretro core binaries',
                         'MeloNX native dependencies', 'Flutter and native test evidence'],
        physicalDeviceTested=False)


def verify():
    sys.path.insert(0, str(ROOT / 'build-utils'))
    from delivery_contract_memo import reuse
    return reuse('609-source', source_contract)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['freeze', 'verify'])
    args = parser.parse_args()
    print(json.dumps(globals()[args.operation](), indent=2))

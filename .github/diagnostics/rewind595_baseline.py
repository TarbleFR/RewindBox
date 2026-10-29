"""Private 595: keep the current reviewed checkout and authenticate its inputs.

The six complete product roots equal delivered594, with exactly one reviewed
host delta: NeoSwap Store.cpp. Both native engines are separately bound to their
successful immutable artifacts. No old checkout is restored, no historical
recipe is imported, and no compiler or native suite runs in this contract.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BUILD = '595'
SOURCE = '08bc36c0032c52a34549ddbde11bb985ae611cbb'
BASE_SOURCE = '97365ce57f17499101e88d50019b6c63be554b83'
BASE_TREE = '1d43bbac26b3146d5d24afff0553d0c18d5bc20e'
BASE_IPA_SHA256 = '714021770922547c532e1439466d5725b4f8eb17c18ca629fe996d985124fe63'
BASE_PRODUCTS = {
    'lib': '9208336d76655b98972d11e519cd0d3337666e41',
    'native': '4b6eb4c74a7448e407fdf86dad4c11a26acc7c47',
    'packages': '6164ff03871a384267e5f20f6734225a1aaed5c4',
    'assets': 'fb15f670844075f22dd667b370961a69371d9589',
    'pubspec.yaml': '4060a4840b2332a4ef1b492bfb3c4bc4140acf26',
    'pubspec.lock': '719ea3b6767c10e60209e144a4e7793520a88b54',
}
PRODUCTS = dict(BASE_PRODUCTS, native='13f00cb5070d4bb08928be628c273ec21210b8e6')
STORE_PATH = 'native/neoswap-storage/Store.cpp'
STORE_BLOB = '6970415fe46a24e345b2900b3ed79fa20da42291'
STORE_SHA256 = '9a951454d7e5124bea4ca1ee5589b1e4429df637dc4377b6c7e3775fcb1c99e4'
RECIPE = {
    '.github/workflows/rewind595-baseline-delivery.yml',
    '.github/diagnostics/rewind595_baseline.py',
    '.github/diagnostics/rewind595_baseline_delivery.py',
    '.github/diagnostics/rewind595_engine.py',
    '.github/diagnostics/rpcs3runtime595_delivery_core.py',
    'build-utils/validate_melonx_engine595_ipa.py',
    'build-utils/validate_rpcs3_core595_ipa.py',
    'build-utils/delivery-595-recipient.pem',
}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT).decode().strip()


def products(ref):
    return {name: git('rev-parse', ref + ':' + name) for name in PRODUCTS}


def source_contract():
    assert os.environ.get('BUILD_NUMBER', BUILD) == BUILD, 'Wrong delivery number'
    assert not git('diff', '--name-only'), 'Tracked working source differs from the reviewed checkout'
    assert git('write-tree') == git('rev-parse', 'HEAD^{tree}'), 'Staged source differs from HEAD'
    subprocess.run(['git', 'merge-base', '--is-ancestor', SOURCE, 'HEAD'], cwd=ROOT, check=True)
    assert products(BASE_SOURCE) == BASE_PRODUCTS, 'Delivered594 source product roots changed'
    assert products(SOURCE) == PRODUCTS, 'Reviewed595 source product roots changed'
    actual = products('HEAD')
    assert actual == PRODUCTS, 'An unreviewed application product changed'
    delta = git('diff-tree', '--no-commit-id', '--name-only', '-r', BASE_SOURCE, 'HEAD', '--', *PRODUCTS).splitlines()
    assert delta == [STORE_PATH], 'Unexpected product change since delivered594'
    assert git('rev-parse', 'HEAD:' + STORE_PATH) == STORE_BLOB, 'Wrong NeoSwap Store source blob'
    assert hashlib.sha256((ROOT / STORE_PATH).read_bytes()).hexdigest() == STORE_SHA256, 'NeoSwap Store source bytes changed'

    # Every existing non-documentary input stays at the reviewed08bc source.
    # The only fresh implementation files are this delivery's explicit recipe.
    changes = git('diff-tree', '--no-commit-id', '--name-only', '-r', SOURCE, 'HEAD').splitlines()
    unexpected = [path for path in changes if path not in RECIPE and path != 'AGENTS.md' and not path.startswith('docs/')]
    assert not unexpected, 'Unreviewed build/tool/source delta: ' + repr(unexpected)
    missing = [path for path in RECIPE if not (ROOT / path).is_file()]
    assert not missing, 'Missing595 recipe input: ' + repr(missing)
    tracked = set(git('ls-files', '-z').split('\0'))
    assert RECIPE <= tracked, 'A595 recipe input is not committed'

    baseline_path = ROOT / 'docs/evidence/rewind594/host-tree594.json'
    baseline_bytes = baseline_path.read_bytes()
    assert hashlib.sha256(baseline_bytes).hexdigest() == 'a341610dafb8a8b6ea5f45a93e0ac2499bf34252edcec85bf94e6b63aacc6dfb'
    baseline = json.loads(baseline_bytes)
    assert baseline['build'] == 594 and baseline['head'] == BASE_SOURCE and baseline['tree'] == BASE_TREE
    assert baseline['productTrees'] == BASE_PRODUCTS, 'Delivered594 receipt product roots changed'
    receipt = json.loads((ROOT / 'docs/evidence/rewind594-delivery.json').read_bytes())
    assert receipt['result'] == 'passed' and receipt['source'] == BASE_SOURCE and receipt['deliveryTree'] == BASE_TREE
    assert receipt['run']['id'] == 40848076659 and receipt['run']['conclusion'] == 'success'
    assert receipt['ipa']['sha256'] == BASE_IPA_SHA256 and receipt['productTrees'] == BASE_PRODUCTS
    return dict(
        build=595, head=git('rev-parse', 'HEAD'), tree=git('write-tree'), reviewedSource=SOURCE,
        baseline=dict(build=594, source=BASE_SOURCE, tree=BASE_TREE, run=40848076659, ipaSHA256=BASE_IPA_SHA256),
        productTrees=actual, unchangedProductTrees=[name for name in PRODUCTS if name != 'native'],
        reviewedNativeProductDelta=[STORE_PATH], hostStore=dict(blob=STORE_BLOB, sha256=STORE_SHA256),
        recipeSHA256={path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in sorted(RECIPE)},
        existingBuildAndToolInputsUnchanged=True, restoredOlderCheckout=False,
        historicalContractsReplayed=False, nativeTestsReplayed=False,
    )


def verify():
    sys.path.insert(0, str(ROOT / 'build-utils'))
    from delivery_contract_memo import reuse
    return reuse(BUILD, source_contract)


def pin():
    # Retain the historical command-line entry point, but verify without mutation.
    result = verify()
    target = ROOT / 'build/delivery/host-tree595.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pin', action='store_true')
    args = parser.parse_args()
    print(json.dumps(pin() if args.pin else verify(), indent=2))

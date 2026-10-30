"""Private IPA597 from delivered596, with the verified RPCS3 continuation.

The five unaffected product roots remain identical to delivered596. The only
host product change is the reviewed NeoSwap Store.cpp; the new RPCS3 binary is
authenticated separately. This contract never rebuilds an engine or replays a
historical native test or delivery recipe.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BUILD = '597'
SOURCE = '36de8e57f13e37c201450eedc5a9b97c1e61e8ea'
BASE_SOURCE = 'd5c5f107f7b514980033d1b95218aa9d2f640609'
BASE_TREE = '1e50d20224dc1461d0e15b2530736688d1039cfa'
BASE_IPA_SHA256 = 'b8d665ab4503fc4f3492b80bb46ed582dcfed71e99982f82a8c2a8a04a842d07'
BASE_RECEIPT_SHA256 = '1965bfdf5ab2f93f26302ebb3314d6b0e42f574c71486e503f09a1bc8a079808'
BASE_PRODUCTS = {
    'lib': '9208336d76655b98972d11e519cd0d3337666e41',
    'native': '0d6ae6a8464a57fee8f32d7aecb2d9fccb12e34b',
    'packages': '6164ff03871a384267e5f20f6734225a1aaed5c4',
    'assets': 'fb15f670844075f22dd667b370961a69371d9589',
    'pubspec.yaml': '4060a4840b2332a4ef1b492bfb3c4bc4140acf26',
    'pubspec.lock': '719ea3b6767c10e60209e144a4e7793520a88b54',
}
PRODUCTS = dict(BASE_PRODUCTS, native='dafd731244ebcc35d6ab63a21ee77871ca080153')
STORE_PATH = 'native/neoswap-storage/Store.cpp'
STORE_BLOB = '05b8d725d89ad0c65559dd29305424585c025d6e'
STORE_SHA256 = '87df68227cf9e113af51ec2ea8968d8af88170834611d560ce711cf168f1ca46'
RECIPE = {
    '.github/workflows/rewind597-baseline-delivery.yml',
    '.github/diagnostics/rewind597_baseline.py',
    '.github/diagnostics/rewind597_baseline_delivery.py',
    '.github/diagnostics/rewind597_engine.py',
    '.github/diagnostics/rpcs3runtime597_delivery_core.py',
    'build-utils/validate_melonx_engine597_ipa.py',
    'build-utils/validate_rpcs3_core597_ipa.py',
    'build-utils/delivery-597-recipient.pem',
}
COMPONENT_PINS = {
    'DOLPHIN_SHA': '7cac54161659421ed95c2cd1c0b0746539a4cd38',
    'DOLPHIN_CORE_HOST_SHA': 'ae7d46f90dff64ce698b8c18e0c12510dbae96fe',
    'ARMSX2_CORE_HOST_SHA': '1343906f05e33b40f10f7026a1a6e2327c338d0e',
    'ARMSX2_CORE_RUN_ID': '39178893158',
    'RPCS3_CORE_HOST_SHA': '88cdc5e3e115a0b8587711d77147467baf38128b',
    'RPCS3_CORE_RUN_ID': '40981514937',
    'LIBRETRO_CORES_HOST_SHA': 'ab9361c29f7c9ab769c4263dd8b7427fc4f4c036',
    'LIBRETRO_CORES_VALIDATED_SHA': 'ab9361c29f7c9ab769c4263dd8b7427fc4f4c036',
    'LIBRETRO_CORES_RUN_ID': '39455712245',
}


def component_pins(workflow):
    for name, expected in COMPONENT_PINS.items():
        values = re.findall(r'^      ' + re.escape(name) + r':\s*([^\r\n]+)$', workflow, re.MULTILINE)
        assert len(values) == 1 and values[0].strip().strip("'\"") == expected, 'Wrong component pin: ' + name
    return dict(COMPONENT_PINS)


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT).decode().strip()


def products(ref):
    return {name: git('rev-parse', ref + ':' + name) for name in PRODUCTS}


def source_contract():
    assert os.environ.get('BUILD_NUMBER', BUILD) == BUILD, 'Wrong delivery number'
    assert not git('diff', '--name-only'), 'Tracked working source differs from the reviewed checkout'
    assert git('write-tree') == git('rev-parse', 'HEAD^{tree}'), 'Staged source differs from HEAD'
    subprocess.run(['git', 'merge-base', '--is-ancestor', SOURCE, 'HEAD'], cwd=ROOT, check=True)
    assert products(BASE_SOURCE) == BASE_PRODUCTS, 'Delivered596 product roots changed'
    assert products(SOURCE) == PRODUCTS, 'Reviewed continuation product roots changed'
    actual = products('HEAD')
    assert actual == PRODUCTS, 'An unreviewed application product changed'
    delta = git('diff-tree', '--no-commit-id', '--name-only', '-r', BASE_SOURCE, 'HEAD', '--', *PRODUCTS).splitlines()
    assert delta == [STORE_PATH], 'Unexpected product change since delivered596'
    assert git('rev-parse', 'HEAD:' + STORE_PATH) == STORE_BLOB, 'Wrong NeoSwap Store source blob'
    assert hashlib.sha256((ROOT / STORE_PATH).read_bytes()).hexdigest() == STORE_SHA256, 'NeoSwap Store source bytes changed'
    changes = git('diff-tree', '--no-commit-id', '--name-only', '-r', SOURCE, 'HEAD').splitlines()
    unexpected = [path for path in changes if path not in RECIPE and path != 'AGENTS.md' and not path.startswith('docs/')]
    assert not unexpected, 'Unreviewed build/tool/source delta: ' + repr(unexpected)
    assert all((ROOT / path).is_file() for path in RECIPE), 'Missing597 recipe input'
    assert RECIPE <= set(git('ls-files', '-z').split('\0')), 'A597 recipe input is not committed'
    pins = component_pins((ROOT / '.github/workflows/rewind597-baseline-delivery.yml').read_text())

    receipt_bytes = (ROOT / 'docs/evidence/rewind596-delivery.json').read_bytes()
    assert hashlib.sha256(receipt_bytes).hexdigest() == BASE_RECEIPT_SHA256, 'Delivered596 receipt changed'
    receipt = json.loads(receipt_bytes)
    assert receipt['result'] == 'passed' and receipt['source'] == BASE_SOURCE and receipt['deliveryTree'] == BASE_TREE
    assert receipt['build'] == 596 and receipt['run']['id'] == 40968162236 and receipt['run']['conclusion'] == 'success'
    assert receipt['ipa']['sha256'] == BASE_IPA_SHA256 and receipt['productTrees'] == BASE_PRODUCTS
    return dict(
        build=597, head=git('rev-parse', 'HEAD'), tree=git('write-tree'), reviewedSource=SOURCE,
        baseline=dict(build=596, source=BASE_SOURCE, tree=BASE_TREE, run=40968162236, ipaSHA256=BASE_IPA_SHA256),
        productTrees=actual, unchangedProductTrees=[name for name in PRODUCTS if name != 'native'],
        reviewedNativeProductDelta=[STORE_PATH], hostStore=dict(blob=STORE_BLOB, sha256=STORE_SHA256),
        componentPins=pins,
        recipeSHA256={path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in sorted(RECIPE)},
        existingBuildAndToolInputsUnchanged=True, restoredOlderCheckout=False,
        historicalContractsReplayed=False, nativeTestsReplayed=False,
    )


def verify():
    sys.path.insert(0, str(ROOT / 'build-utils'))
    from delivery_contract_memo import reuse
    return reuse(BUILD, source_contract)


def pin():
    result = verify()
    target = ROOT / 'build/delivery/host-tree597.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pin', action='store_true')
    args = parser.parse_args()
    print(json.dumps(pin() if args.pin else verify(), indent=2))

"""Private 596: keep the current reviewed checkout and authenticate its inputs.

The six complete product roots equal delivered595, with exactly one reviewed
host delta: NeoSwap Store.cpp. Both native engines are separately bound to their
successful immutable artifacts. No old checkout is restored, no historical
recipe is imported, and no compiler or native suite runs in this contract.
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
BUILD = '596'
SOURCE = 'e97137b1d907b4c0b0c102435d55b1f96d891d38'
BASE_SOURCE = 'd2e5029f8d7ca33eec279546d64a7f908285e804'
BASE_TREE = '67de75286e052332304f49b10b4f1cdff6750f0b'
BASE_IPA_SHA256 = 'cfc1079249e4168349896a69f34a150ddbc68e318aafbb954a06cb019b00374e'
BASE_PRODUCTS = {
    'lib': '9208336d76655b98972d11e519cd0d3337666e41',
    'native': '13f00cb5070d4bb08928be628c273ec21210b8e6',
    'packages': '6164ff03871a384267e5f20f6734225a1aaed5c4',
    'assets': 'fb15f670844075f22dd667b370961a69371d9589',
    'pubspec.yaml': '4060a4840b2332a4ef1b492bfb3c4bc4140acf26',
    'pubspec.lock': '719ea3b6767c10e60209e144a4e7793520a88b54',
}
PRODUCTS = dict(BASE_PRODUCTS, native='0d6ae6a8464a57fee8f32d7aecb2d9fccb12e34b')
STORE_PATH = 'native/neoswap-storage/Store.cpp'
STORE_BLOB = 'e68be3768ef043865112502ed02b446f9190955c'
STORE_SHA256 = 'a812b0834df8c7301d59ac780b84a4ecc7c306b7b55f7ab02178e5705dca8571'
RECIPE = {
    '.github/workflows/rewind596-baseline-delivery.yml',
    '.github/diagnostics/rewind596_baseline.py',
    '.github/diagnostics/rewind596_baseline_delivery.py',
    '.github/diagnostics/rewind596_engine.py',
    '.github/diagnostics/rpcs3runtime596_delivery_core.py',
    'build-utils/validate_melonx_engine596_ipa.py',
    'build-utils/validate_rpcs3_core596_ipa.py',
    'build-utils/delivery-596-recipient.pem',
}
COMPONENT_PINS = {
    'DOLPHIN_SHA': '7cac54161659421ed95c2cd1c0b0746539a4cd38',
    'DOLPHIN_CORE_HOST_SHA': 'ae7d46f90dff64ce698b8c18e0c12510dbae96fe',
    'ARMSX2_CORE_HOST_SHA': '1343906f05e33b40f10f7026a1a6e2327c338d0e',
    'ARMSX2_CORE_RUN_ID': '39178893158',
    'RPCS3_CORE_HOST_SHA': 'e97137b1d907b4c0b0c102435d55b1f96d891d38',
    'RPCS3_CORE_RUN_ID': '40963062736',
    'LIBRETRO_CORES_HOST_SHA': 'ab9361c29f7c9ab769c4263dd8b7427fc4f4c036',
    'LIBRETRO_CORES_VALIDATED_SHA': 'ab9361c29f7c9ab769c4263dd8b7427fc4f4c036',
    'LIBRETRO_CORES_RUN_ID': '39455712245',
}


def component_pins(workflow):
    """Reject altered immutable pins before expensive application compilation."""
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
    assert products(BASE_SOURCE) == BASE_PRODUCTS, 'Delivered595 source product roots changed'
    assert products(SOURCE) == PRODUCTS, 'Reviewed596 source product roots changed'
    actual = products('HEAD')
    assert actual == PRODUCTS, 'An unreviewed application product changed'
    delta = git('diff-tree', '--no-commit-id', '--name-only', '-r', BASE_SOURCE, 'HEAD', '--', *PRODUCTS).splitlines()
    assert delta == [STORE_PATH], 'Unexpected product change since delivered595'
    assert git('rev-parse', 'HEAD:' + STORE_PATH) == STORE_BLOB, 'Wrong NeoSwap Store source blob'
    assert hashlib.sha256((ROOT / STORE_PATH).read_bytes()).hexdigest() == STORE_SHA256, 'NeoSwap Store source bytes changed'

    # Every existing non-documentary input stays at the reviewed e97137b1 source.
    # The only fresh implementation files are this delivery's explicit recipe.
    changes = git('diff-tree', '--no-commit-id', '--name-only', '-r', SOURCE, 'HEAD').splitlines()
    unexpected = [path for path in changes if path not in RECIPE and path != 'AGENTS.md' and not path.startswith('docs/')]
    assert not unexpected, 'Unreviewed build/tool/source delta: ' + repr(unexpected)
    missing = [path for path in RECIPE if not (ROOT / path).is_file()]
    assert not missing, 'Missing596 recipe input: ' + repr(missing)
    tracked = set(git('ls-files', '-z').split('\0'))
    assert RECIPE <= tracked, 'A596 recipe input is not committed'
    pins = component_pins((ROOT / '.github/workflows/rewind596-baseline-delivery.yml').read_text())

    baseline_path = ROOT / 'docs/evidence/rewind595/apple-delivery/host-tree595.json'
    baseline_bytes = baseline_path.read_bytes()
    assert hashlib.sha256(baseline_bytes).hexdigest() == '0d8f63e60d1ddff68d646ef0d6d76b211dbab5fa638fd35698880303d65e7ea4'
    baseline = json.loads(baseline_bytes)
    assert baseline['build'] == 595 and baseline['head'] == BASE_SOURCE and baseline['tree'] == BASE_TREE
    assert baseline['productTrees'] == BASE_PRODUCTS, 'Delivered595 receipt product roots changed'
    receipt = json.loads((ROOT / 'docs/evidence/rewind595-delivery.json').read_bytes())
    assert receipt['result'] == 'passed' and receipt['source'] == BASE_SOURCE and receipt['deliveryTree'] == BASE_TREE
    assert receipt['run']['id'] == 40928805790 and receipt['run']['conclusion'] == 'success'
    assert receipt['ipa']['sha256'] == BASE_IPA_SHA256 and receipt['productTrees'] == BASE_PRODUCTS
    return dict(
        build=596, head=git('rev-parse', 'HEAD'), tree=git('write-tree'), reviewedSource=SOURCE,
        baseline=dict(build=595, source=BASE_SOURCE, tree=BASE_TREE, run=40928805790, ipaSHA256=BASE_IPA_SHA256),
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
    # Retain the historical command-line entry point, but verify without mutation.
    result = verify()
    target = ROOT / 'build/delivery/host-tree596.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pin', action='store_true')
    args = parser.parse_args()
    print(json.dumps(pin() if args.pin else verify(), indent=2))

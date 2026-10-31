"""Bind IPA607 to delivered IPA606 and the exact unchanged application source."""
import json
import os
from pathlib import Path
import subprocess
import sys
import rewind606_baseline as prior

ROOT = Path(__file__).resolve().parents[2]
BUILD = 607
BASE = prior.BASE  # Preserve achievement translation provenance from Build605.
COMPONENTS = prior.COMPONENTS
pins = prior.pins
original = prior.original
sha = prior.sha
git = prior.git
require = prior.require
SOURCE606 = 'a95654f4cb9a9fc04657c33773cc14d1d05b46af'
TREE606 = 'f0df5047d8ed8e7725788279c0ac9d55c43021e2'
RECEIPT606 = 'docs/evidence/rewind606/delivery.json'
RECEIPT606_SHA256 = '54bf56819e8f032a4bb33b9d1ab74ac96e0498971c64ae2c3dfff2ff484c198c'  # replaced by verified file digest
PREP_SOURCE = 'ed755c6e04b6f27b9c20e93961e4bc2382a75adb'
IPA606_SHA256 = '4610e26bdbfc84cac091cddac38941aeaf5a0219d625e70d998155bbe21aa5f1'
ALLOWED = {'.github/diagnostics/rewind607_baseline.py', '.github/diagnostics/rewind607_delivery.py',
           '.github/diagnostics/rpcs3runtime607_core.py', '.github/workflows/rewind607-rpcs3-core-delivery.yml',
           'build-utils/delivery-607-recipient.pem', 'test/rewind607_delivery_contract_test.py'}


def verify():
    receipt_bytes = (ROOT / RECEIPT606).read_bytes()
    require(sha(receipt_bytes) == RECEIPT606_SHA256, 'Delivered606 receipt bytes changed')
    receipt = json.loads(receipt_bytes)
    require(receipt['result'] == 'passed' and receipt['source'] == SOURCE606 and receipt['tree'] == TREE606 and
            receipt['build'] == 606 and receipt['run'] == 41242511117 and receipt['job'] == 124659230427 and
            receipt['ipaSHA256'] == IPA606_SHA256 and receipt['ipaBytes'] == 189838983,
            'Delivered606 baseline provenance differs')
    require(os.environ.get('BUILD_NUMBER', '607') == '607' and os.environ.get('GITHUB_REF_NAME', 'Claude') == 'Claude',
            'Wrong build number or branch')
    require(not git('diff', '--name-only') and git('write-tree') == git('rev-parse', 'HEAD^{tree}'),
            'Checkout changed after commit')
    require(git('rev-parse', SOURCE606 + '^{tree}') == TREE606, 'Delivered606 source tree differs')
    subprocess.run(['git', 'merge-base', '--is-ancestor', SOURCE606, 'HEAD'], cwd=ROOT, check=True)
    require(not git('diff', '--name-only', SOURCE606, 'HEAD', '--', *prior.PRODUCTS),
            'Application product source differs from delivered606')
    product_trees = {p: git('rev-parse', 'HEAD:' + p) for p in prior.PRODUCTS}
    require(product_trees == prior.pins()['productTrees'], 'Application product tree differs from reviewed606')
    subprocess.run(['git', 'merge-base', '--is-ancestor', PREP_SOURCE, 'HEAD'], cwd=ROOT, check=True)
    late = set(git('diff', '--name-only', PREP_SOURCE, 'HEAD').splitlines())
    require(late <= ALLOWED, 'Unreviewed Build607 source path: ' + repr(sorted(late - ALLOWED)))
    sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
    from helper_initialization import verify as verify_helper
    verify_helper()
    return dict(result='passed', build=607, source=git('rev-parse', 'HEAD'), tree=git('rev-parse', 'HEAD^{tree}'),
                delivered606=dict(source=SOURCE606, tree=TREE606, run=receipt['run'], job=receipt['job'],
                                  ipaSHA256=IPA606_SHA256), productTrees=product_trees,
                applicationSourceUnchanged=True, physicalDeviceTested=False, gameTested=False, fpsGainProven=False)

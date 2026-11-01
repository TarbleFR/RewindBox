#!/usr/bin/env python3
"""Pure source checks of the Build609 recipe; no network, build or old suite."""
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / '.github/diagnostics'), str(ROOT / 'build-utils'), str(ROOT / 'build-utils/melonx')]
import rewind609_baseline as tree
import rewind609_delivery as delivery
import rewind609_engine as engine

checks = 0


def check(ok, message):
    global checks
    assert ok, message
    checks += 1


def rejects(function, message):
    global checks
    try:
        function()
    except (AssertionError, ValueError, KeyError):
        checks += 1
        return
    raise AssertionError(message)


workflow608 = (ROOT / delivery.WORKFLOW608).read_text()
workflow = (ROOT / delivery.WORKFLOW).read_text()
check(workflow == delivery.expected_workflow(workflow608), 'Build609 workflow is not the exact reviewed608 transform')
rejects(lambda: delivery.expected_workflow(workflow608.replace(
            'Authenticate delivered607 and the exact reviewed608 source delta', 'Authenticate something else')),
        'A changed608 step anchor was accepted')
check(delivery.expected_workflow(workflow608.replace('Seal every executable', 'Sign some executables')) != workflow,
      'A changed unanchored608 step would not be detected by the committed transform')
operations = set(re.findall(r'rewind609_delivery\.py ([a-z0-9-]+)', workflow))
check(operations and operations <= {'contract', 'baseline', 'retained-ready', 'tests', 'download-core', 'component-runs',
      'download-components', 'engine-evidence', 'download-libretro', 'download-melonx-dependencies', 'dolphin',
      'armsx2', 'embed', 'structure', 'validate', 'seal'}, 'Workflow calls an unknown609 operation')
check('[rewind609-delivery]' in workflow and "BUILD_NUMBER: '609'" in workflow and
      'delivery-609-recipient.pem' in workflow and 'needs.reuse' not in workflow, 'Wrong609 trigger or recipient')

core_workflow = (ROOT / engine.WORKFLOW).read_text()
check(all(f'- name: {step}\n' in core_workflow for step in engine.CORE_STEPS), 'Pinned Core producer step names drifted')

receipt = json.loads((ROOT / tree.RECEIPT608).read_bytes())
archives = receipt['reusedEvidence']['originalArchives']
check(receipt['reusedEvidence']['execution'] == delivery.REUSED, 'Reused608 origin differs from the delivered receipt')
check(all(archives[kind]['job'] == pin['job'] and archives[kind]['artifact'] == pin['artifact'] and
          archives[kind]['archiveSHA256'] == pin['sha256'] for kind, pin in delivery.REUSED_ARTIFACTS.items()),
      'Reused archive pins differ from delivered608')
check(receipt['coreChecks']['dolphin']['fingerprint'] == delivery.RETAINED_CORES['dolphin'] and
      receipt['coreChecks']['armsx2']['fingerprint'] == delivery.RETAINED_CORES['armsx2'] and
      receipt['coreChecks']['rpcs3']['fingerprint'] == delivery.RPC607_FINGERPRINT, 'Retained Core fingerprints differ')
check(receipt['ipa']['sha256'] == tree.BASELINE['ipaSHA256'] and receipt['execution']['source'] == tree.BASE,
      'Wrong delivered608 baseline')

check(len(delivery.inventory()) == 90, 'Build609 must keep exactly the delivered608 images')
scope = tree.pins()
core = scope['core']
check(core['contractSha256'] == scope['coreContractSHA256'] ==
      __import__('hashlib').sha256((ROOT / tree.CORE_CONTRACT).read_bytes()).hexdigest(), 'Core pin uses another contract')
check(core['source'] != json.loads((ROOT / tree.CORE_CONTRACT).read_bytes())['baseline']['source'] and
      core['packagedFingerprint'] != receipt['coreChecks']['melonx']['fingerprint'], 'MeloNX Core was not replaced')
check(set(scope['productDelta']) == set(tree.CORE_PRODUCT_INPUTS), 'Product delta exceeds the reviewed Core input')
tree.check_product_delta(scope['productDelta'])
rejects(lambda: tree.check_product_delta({'lib/main.dart': dict(after='0' * 64, modeBefore='100644', modeAfter='100644')}),
        'An application source change was accepted')
check(not any(tree.is_product(path) for path in scope['sourceDelta'] if path not in tree.CORE_PRODUCT_INPUTS),
      'Unexpected product path in the source delta')
key = subprocess.run(['openssl', 'pkey', '-pubin', '-in', str(ROOT / tree.PUBLIC_KEY), '-noout', '-text'],
                     capture_output=True, text=True, check=True).stdout
check(key.startswith('Public-Key: (4096 bit)'), 'Build609 recipient must be an RSA-4096 public key')
check(all(path.startswith('test/') for path in tree.reused_test_paths()), 'Unexpected reused test path')
print(json.dumps(dict(result='passed', checks=checks, networkUsed=False, oldSuitesExecuted=False,
                      physicalDeviceTested=False)))

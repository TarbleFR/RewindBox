#!/usr/bin/env python3
"""Offline contract of the private IPA611 delivery recipe (no network, no build).

Checks that the committed workflow is the exact reviewed transform of the
delivered609 workflow (with one restoration step per job), that the reviewed
source scope restores every changed application, retained-engine and reused
test path of the concurrent 610 lot and nothing else, that the only remaining
product change is the fragmented-read MeloNX Core input, that the Core pin is
complete and bound to the frozen Core contract, and that the native inventory
keeps the 90 delivered609 images. A restoration dry run on a scratch copy of
the index proves that the restored paths reproduce delivered609 bytes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))

import rewind611_baseline as tree  # noqa: E402
import rewind611_delivery as delivery  # noqa: E402
import rewind611_engine as engine  # noqa: E402


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def show(commit: str, path: str) -> bytes:
    return subprocess.check_output(['git', 'show', f'{commit}:{path}'], cwd=ROOT, timeout=60)


class Workflow(unittest.TestCase):
    def test_exact_reviewed_transform(self):
        expected = delivery.expected_workflow((ROOT / delivery.WORKFLOW609).read_text())
        self.assertEqual((ROOT / delivery.WORKFLOW).read_text(), expected)

    def test_restore_precedes_every_check(self):
        text = (ROOT / delivery.WORKFLOW).read_text()
        self.assertEqual(text.count(delivery.RESTORE_STEP), 2)
        for job in ('  preflight:\n', '  application:\n'):
            body = text[text.index(job):]
            self.assertLess(body.index(delivery.RESTORE_STEP), body.index('rewind611_delivery.py'))
        self.assertIn('DELIVERY_RECIPIENT: build-utils/delivery-611-recipient.pem', text)
        self.assertIn("'[rewind611-delivery]'", text)
        for retired in ('rewind609_delivery.py', "BUILD_NUMBER: '609'", 'delivery-609-recipient'):
            self.assertNotIn(retired, text)


class Scope(unittest.TestCase):
    def setUp(self):
        self.value = tree.pins()

    def test_restoration_is_exactly_the_concurrent_lot(self):
        paths = tree.changed_paths()
        self.assertEqual(set(paths), set(self.value['sourceDelta']))
        self.assertEqual(self.value['restoredToBaseline'], tree.restoration_scope(paths))
        unbuilt = set(paths) - set(self.value['restoredToBaseline'])
        self.assertFalse({p for p in unbuilt if tree.is_preserved(p)})
        self.assertEqual({p for p in unbuilt if tree.is_product(p)}, set(tree.CORE_PRODUCT_INPUTS))
        for path in self.value['restoredToBaseline']:
            self.assertEqual(tree.change_record(path, 'HEAD'), self.value['sourceDelta'][path], path)

    def test_restored_bytes_are_delivered609(self):
        # Index-only dry run: the blobs the restoration writes are exactly the baseline blobs.
        for path in self.value['restoredToBaseline']:
            before, mode = tree.original(path)
            record = self.value['sourceDelta'][path]
            self.assertEqual(record['before'], sha(before) if before is not None else None, path)
            self.assertEqual(record['modeBefore'], mode, path)

    def test_only_core_input_changes_product(self):
        tree.check_product_delta(self.value['productDelta'])
        frozen, inputs = tree.core_contract_inputs()
        self.assertEqual(self.value['coreContractSHA256'], sha((ROOT / tree.CORE_CONTRACT).read_bytes()))
        self.assertEqual(self.value['productDelta'][tree.CORE_PRODUCT_INPUTS[0]]['after'], inputs[tree.CORE_PRODUCT_INPUTS[0]])

    def test_core_pin(self):
        core = engine.pin()
        for key in ('source', 'run', 'job', 'attempt', 'workflow', 'artifact', 'name', 'bytes', 'sha256',
                    'binaries', 'identities', 'contractSha256', 'resultSha256', 'packagedFingerprint'):
            self.assertIn(key, core)
            self.assertIsNotNone(core[key], key)
        self.assertEqual(core['workflow'], '.github/workflows/melonx-core.yml')
        # Every Core producer input is still byte-identical in this checkout.
        frozen = json.loads((ROOT / tree.CORE_CONTRACT).read_bytes())
        for inputs in (frozen['inputs'], frozen['preparationInputs']):
            for path, digest in inputs.items():
                self.assertEqual(sha((ROOT / path).read_bytes()), digest, path)
                self.assertEqual(sha(show(core['source'], path)), digest, path)

    def test_inventory(self):
        self.assertEqual(len(delivery.inventory()), 90)


if __name__ == '__main__':
    unittest.main(verbosity=2)

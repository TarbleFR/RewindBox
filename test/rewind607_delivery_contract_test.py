"""Offline regression for the recovered Core and Build607 packaging contract."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
import rpcs3runtime607_core as core
import rewind607_baseline as baseline


class Delivery607(unittest.TestCase):
    def test_recovered_binary_and_host(self):
        diagnostics = ROOT / 'build/rpcs3-core607/original-diagnostics.zip'
        if not diagnostics.is_file():
            self.skipTest('Original diagnostic archive is not locally available')
        original = core.core_run
        try:
            core.core_run = lambda: {'originalConclusion': 'failure', 'originalRun': core.CORE_RUN}
            binary = core.raw_core()
            self.assertEqual(hashlib.sha256(binary).hexdigest(), core.CORE_SHA256)
            self.assertEqual(core.compatibility()['abiVersion'], 30)
            self.assertEqual(core.validate_core_identity(binary, core.EVIDENCE / 'identity.json', core.CORE_SOURCE)['type'], core.CORE_TYPE)
            with self.assertRaises(ValueError):
                core.validate_core_identity(binary[:-1] + bytes([binary[-1] ^ 1]), core.EVIDENCE / 'identity.json', core.CORE_SOURCE)
        finally:
            core.core_run = original

    def test_receipt_and_product_tree_pins(self):
        self.assertEqual(hashlib.sha256((ROOT / baseline.RECEIPT606).read_bytes()).hexdigest(), baseline.RECEIPT606_SHA256)
        self.assertEqual({p: baseline.git('rev-parse', 'HEAD:' + p) for p in baseline.prior.PRODUCTS}, baseline.pins()['productTrees'])
        self.assertEqual(json.loads((core.EVIDENCE / 'identity.json').read_bytes())['original_ci_conclusion'], 'failure')


if __name__ == '__main__':
    unittest.main()

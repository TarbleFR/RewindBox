#!/usr/bin/env python3
"""Only three exact host journal paths may differ from the retained RPCS3 Core."""
import ast
import importlib
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = Path(os.environ.get('REWINDBOX_CONTRACT_REFERENCE_ROOT', ROOT))
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
tree = importlib.import_module('rewind606_baseline')


def functions(path):
    return {node.name: node for node in ast.parse(path.read_text()).body if isinstance(node, ast.FunctionDef)}


class RetainedCoreProof(unittest.TestCase):
    def test_all_core_authentication_guards_are_preserved_verbatim(self):
        before = functions(REFERENCE / '.github/diagnostics/rpcs3runtime604_core.py')
        after = functions(ROOT / '.github/diagnostics/rpcs3runtime606_core.py')
        self.assertEqual(before.keys(), after.keys())
        for name in before.keys() - {'compatibility', 'core_receipt', 'embed_compiled_source'}:
            with self.subTest(function=name):
                self.assertEqual(ast.dump(before[name]), ast.dump(after[name]))

    def test_compiled_legal_source_changes_only_honest_scope_metadata(self):
        before = functions(REFERENCE / '.github/diagnostics/rpcs3runtime604_core.py')['embed_compiled_source']
        after = functions(ROOT / '.github/diagnostics/rpcs3runtime606_core.py')['embed_compiled_source']
        removed = []
        for node in ast.walk(after):
            if isinstance(node, ast.Call):
                for keyword in node.keywords[:]:
                    if keyword.arg == 'coreRecompiledForDelivery':
                        self.assertIs(keyword.value.value, False)
                        node.keywords.remove(keyword); removed.append(keyword)
        self.assertEqual(len(removed), 1)
        self.assertEqual(ast.dump(before), ast.dump(after))


class HostJournalScope(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.routes = {}
        self.before, self.after = {}, {}
        self.corrupt_concurrent_source = False
        for path in tree.RPC_ROUTES:
            if path == tree.CONCURRENT_HOST_DELTA['path']:
                before = subprocess.check_output(['git', 'show', tree.BASE + ':' + path], cwd=REFERENCE)
                after = subprocess.check_output(['git', 'show', tree.CONCURRENT_HOST_DELTA['source'] + ':' + path], cwd=REFERENCE)
            else:
                before, after = b'compiled old routing', b'new routing'
            self.before[path], self.after[path] = before, after
            target = self.root / path; target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(after)
            self.routes[path] = dict(before=tree.sha(before), after=tree.sha(after))
        self.config = dict(rpcHostRouting=self.routes, productDelta=dict(self.routes), reviewedSource='reviewed')

    def tearDown(self):
        self.temp.cleanup()

    def validate(self):
        def original(ref, path):
            if ref == tree.CONCURRENT_HOST_DELTA['source']:
                return b'wrong concurrent source' if self.corrupt_concurrent_source else self.after[path]
            return self.after[path] if ref == 'reviewed' else self.before[path]
        with patch.object(tree, 'ROOT', self.root), patch.object(tree, 'pins', return_value=self.config), patch.object(tree, 'original', side_effect=original):
            return tree.reviewed_routing()

    def test_exact_three_preimages_and_postimages(self):
        self.assertEqual(set(self.validate()), set(tree.RPC_ROUTES))

    def test_unreviewed_fourth_path_is_never_an_exception(self):
        self.routes['native/neoswap/NeoSwapClient.h'] = next(iter(self.routes.values()))
        with self.assertRaises(ValueError): self.validate()

    def test_missing_early_loader_binding_rejected(self):
        del self.routes[tree.RPC_ROUTES[1]]
        with self.assertRaises(ValueError): self.validate()

    def test_mixed_old_and_new_reviewed_bytes_rejected(self):
        (self.root / tree.RPC_ROUTES[0]).write_bytes(b'compiled old routing')
        with self.assertRaises(ValueError): self.validate()

    def test_wrong_baseline_preimage_rejected(self):
        self.routes[tree.RPC_ROUTES[0]] = dict(before='f' * 64, after=tree.sha(b'new routing'))
        self.config['productDelta'] = dict(self.routes)
        with self.assertRaises(ValueError): self.validate()

    def test_exception_must_be_bound_to_product_delta(self):
        self.config['productDelta'][tree.RPC_ROUTES[0]] = dict(before='f' * 64, after='a' * 64)
        with self.assertRaises(ValueError): self.validate()

    def test_concurrent_plugin_cannot_change_outside_exact_milestone_delta(self):
        path = tree.CONCURRENT_HOST_DELTA['path']
        self.after[path] += b'\n// unrelated bridge change\n'
        (self.root / path).write_bytes(self.after[path])
        self.routes[path] = dict(before=tree.sha(self.before[path]), after=tree.sha(self.after[path]))
        self.config['productDelta'] = dict(self.routes)
        with self.assertRaises(ValueError): self.validate()

    def test_exact_concurrent_source_commit_is_required(self):
        self.corrupt_concurrent_source = True
        with self.assertRaises(ValueError): self.validate()


if __name__ == '__main__':
    unittest.main()

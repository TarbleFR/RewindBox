import base64
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.error import HTTPError

DIRECTORY = Path(__file__).resolve().parents[1] / 'build-utils/maintenance'
sys.path.insert(0, str(DIRECTORY))
spec = importlib.util.spec_from_file_location('consolidate', DIRECTORY / 'consolidate_branches.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
A, B, C = 'a' * 40, 'b' * 40, 'c' * 40


def plan():
    return {'version': 1, 'repository': m.REPO, 'base_sha': A, 'main_sha': A,
            'backup_sha': B, 'expires_at': '2050-01-01T00:00:00Z',
            'branches': [{'branch': 'work/old', 'sha': C}]}


class Fake:
    def __init__(self):
        self.head, self.backup, self.parent, self.manifest = C, B, C, C
        self.main, self.pr, self.protected, self.absent = A, False, False, None
        self.deleted = []
    def request(self, path, method='GET'):
        if method != 'GET': raise AssertionError('Unexpected mutation')
        if '/branches/Backup' in path: return {'commit': {'sha': self.backup}}
        if '/git/commits/' in path: return {'sha': B, 'parents': [{'sha': A}, {'sha': self.parent}]}
        if '/contents/' in path:
            d = {'version': 1, 'repository': m.REPO, 'branches': [{'branch': 'work/old', 'sha': self.manifest}]}
            return {'type': 'file', 'encoding': 'base64', 'content': base64.b64encode(json.dumps(d).encode()).decode()}
        if '/compare/' in path: return {'merge_base_commit': {'sha': A}}
        if '/branches/main' in path: return {'commit': {'sha': self.main}}
        if '/branches/Claude' in path: return {'commit': {'sha': A}}
        if '/branches/work%2Fold' in path:
            if self.absent: raise HTTPError('https://api.github.com' + path, self.absent, 'test', {}, None)
            return {'commit': {'sha': self.head}, 'protected': self.protected}
        if '/pulls?' in path: return [{'head': {'ref': 'work/old'}, 'base': {'ref': 'Claude'}}] if self.pr else []
        raise AssertionError(path)
    def delete_branch(self, name, expected): self.deleted.append((name, expected))


class Tests(unittest.TestCase):
    def test_changed_unarchived_manifest_backup_pr_protected_main_fail_closed(self):
        for attr, value in [('head', A), ('parent', A), ('manifest', A), ('backup', A), ('pr', True), ('protected', True), ('main', B)]:
            with self.subTest(attr=attr):
                api = Fake(); setattr(api, attr, value)
                with self.assertRaises(RuntimeError): m.run(api, plan(), {'operations': []}, True)
                self.assertEqual(api.deleted, [])
    def test_protected_names_and_bound_rejected(self):
        for name in ['main', 'Claude', 'Backup', 'backup/x', 'work/../main', 'work/backup-one']:
            p = plan(); p['branches'][0]['branch'] = name
            with self.assertRaises(RuntimeError): m.validate_plan(p)
        p = plan(); p['branches'] *= 41
        with self.assertRaises(RuntimeError): m.validate_plan(p)
    def test_dry_run_then_exact_leased_delete_and_atomic_receipts(self):
        api = Fake(); receipt = {'operations': []}
        m.run(api, plan(), receipt)
        self.assertEqual(api.deleted, []); self.assertEqual(receipt['operations'][0]['result'], 'eligible')
        receipt = {'operations': []}
        with tempfile.TemporaryDirectory() as directory:
            m.run(api, plan(), receipt, True, directory)
            self.assertEqual(api.deleted, [('work/old', C)])
            self.assertEqual(json.loads((Path(directory) / 'operation-001.json').read_text())['result'], 'deleted')
            self.assertEqual(json.loads((Path(directory) / 'branch-consolidation.json').read_text()), receipt)
            self.assertFalse(list(Path(directory).glob('*.tmp')))
    def test_absence_only_404_and_still_requires_archive(self):
        api = Fake(); api.absent = 404; receipt = {'operations': []}
        m.run(api, plan(), receipt, True)
        self.assertEqual(receipt['operations'][0]['result'], 'already_absent'); self.assertEqual(api.deleted, [])
        api.manifest = A
        with self.assertRaises(RuntimeError): m.run(api, plan(), {'operations': []}, True)
        api = Fake(); api.absent = 401
        with self.assertRaises(HTTPError): m.run(api, plan(), {'operations': []}, True)
        self.assertEqual(api.deleted, [])
    def test_exact_execution_boundary(self):
        env = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': m.REPO, 'GITHUB_REF': 'refs/heads/Claude', 'GITHUB_EVENT_NAME': 'push', 'GITHUB_SHA': C}
        event = {'ref': 'refs/heads/Claude', 'repository': {'full_name': m.REPO}, 'before': A, 'after': C}
        m.execution_context(plan(), env, event)
        for key, value in [('before', B), ('after', B), ('forced', True), ('created', True), ('deleted', True)]:
            broken = dict(event); broken[key] = value
            with self.assertRaises(RuntimeError): m.execution_context(plan(), env, broken)
    def test_mid_batch_archive_change_stops_remaining_deletes(self):
        p = plan(); p['branches'].append({'branch': 'work/second', 'sha': C})
        api = Fake()
        original = api.delete_branch
        def delete(name, sha):
            original(name, sha); api.backup = A
        api.delete_branch = delete
        # Add second manifest entry; it remains the exact reviewed archive.
        request = api.request
        def get(path, method='GET'):
            value = request(path, method)
            if '/contents/' in path:
                d = json.loads(base64.b64decode(value['content'])); d['branches'].append({'branch': 'work/second', 'sha': C})
                value['content'] = base64.b64encode(json.dumps(d).encode()).decode()
            return value
        api.request = get
        with self.assertRaises(RuntimeError): m.run(api, p, {'operations': []}, True)
        self.assertEqual(api.deleted, [('work/old', C)])


if __name__ == '__main__': unittest.main()

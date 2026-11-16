"""Fork gate of the standard recipe (standard_delivery.fork_gate, 16 November 2026).

Test IPAs are built only by the official repository; a fork's run may only rebuild a published release exactly.
Run locally: python3 -B .github/diagnostics/fork_gate_test.py (no network: GitHub answers are stubbed; git runs
on synthetic repositories in a temporary directory). Not part of any delivery command.
"""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import standard_delivery as sd  # noqa: E402

BUILD = 9721
OFFICIAL = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'TarbleFR/RewindBox', 'GITHUB_REPOSITORY_ID': '1329032710'}
FORK = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'someone/RewindBox', 'GITHUB_REPOSITORY_ID': '42'}
GIT_ENV = dict(os.environ, GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@example.invalid', GIT_COMMITTER_NAME='t',
               GIT_COMMITTER_EMAIL='t@example.invalid', GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
PEM_A = '-----BEGIN PUBLIC KEY-----\nAAAA\n-----END PUBLIC KEY-----\n'
PEM_B = '-----BEGIN PUBLIC KEY-----\nBBBB\n-----END PUBLIC KEY-----\n'


def no_network(endpoint):
    raise AssertionError('no GitHub request expected: ' + endpoint)


class Synthetic:
    """A git repository with one released trigger commit T of BUILD (frozen manifest + recipient key)."""

    def __init__(self, root):
        self.root = Path(root)
        self.git('init', '-q', '-b', 'main')
        self.write('lib/app.txt', 'product\n')
        self.write(f'build-utils/delivery-{BUILD}-recipient.pem', PEM_A)
        self.manifest = dict(schema=1, build=BUILD, status='frozen', product=dict(effectiveDigest='e' * 64),
                             components=dict(rpcs3=dict(pinSha256='1' * 64)),
                             recipient=dict(path=f'build-utils/delivery-{BUILD}-recipient.pem', sha256='a' * 64))
        self.write_manifest(self.manifest)
        self.commit('build(delivery): freeze')
        self.write('docs/x.md', 'trigger\n')
        self.release = self.commit(f'[ipa-delivery:{BUILD}] build(delivery): request the private IPA {BUILD}')
        self.repo = sd.Repo(self.root)

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.root, env=GIT_ENV, check=True, capture_output=True,
                              text=True).stdout.strip()

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def write_manifest(self, value):
        self.write(sd.manifest_path(BUILD), json.dumps(value, indent=1) + '\n')

    def commit(self, message):
        self.git('add', '-A')
        self.git('commit', '-q', '-m', message)
        return self.git('rev-parse', 'HEAD')

    def own_key(self, extra=None, manifest=None):
        """The fork's recipient commit on top of the release (optionally with another change)."""
        self.write(f'build-utils/delivery-{BUILD}-recipient.pem', PEM_B)
        value = json.loads(json.dumps(manifest or self.manifest))
        value['recipient']['sha256'] = 'b' * 64
        self.write_manifest(value)
        if extra:
            extra()
        return self.commit(f'[ipa-delivery:{BUILD}] build(delivery): rebuild release 9.9.9 with my key')


def releases(tag='9.9.9', commit=None, draft=False, prerelease=False):
    """A get() stub answering the official releases and tags."""
    def get(endpoint):
        if endpoint.startswith('releases?'):
            return [dict(tag_name=tag, draft=draft, prerelease=prerelease)] if endpoint.endswith('page=1') else []
        if endpoint.startswith('tags?'):
            return [dict(name=tag, commit=dict(sha=commit))] if endpoint.endswith('page=1') else []
        raise AssertionError('unexpected endpoint ' + endpoint)
    return get


class RunRepository(unittest.TestCase):
    def test_local_official_and_fork(self):
        self.assertEqual(sd.run_repository({}), 'local')
        self.assertEqual(sd.run_repository({'CI': 'true', 'GITHUB_REPOSITORY': 'someone/RewindBox'}), 'local')
        self.assertEqual(sd.run_repository(OFFICIAL), 'official')
        self.assertEqual(sd.run_repository({'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'tarblefr/rewindbox'}),
                         'official')
        # A renamed or transferred official repository keeps its id.
        self.assertEqual(sd.run_repository({'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'TarbleFR/Other',
                                            'GITHUB_REPOSITORY_ID': '1329032710'}), 'official')
        self.assertEqual(sd.run_repository(FORK), 'fork')
        self.assertEqual(sd.run_repository({'GITHUB_ACTIONS': 'true'}), 'fork')

    def test_official_and_local_runs_touch_neither_git_nor_network(self):
        for environ in ({}, OFFICIAL):
            self.assertEqual(sd.fork_gate(BUILD, '0' * 40, repo=None, environ=environ, get=no_network)['repository'],
                             sd.run_repository(environ))
        # A fork push without a delivery request compiles nothing: nothing to check.
        self.assertEqual(sd.fork_gate(None, '0' * 40, repo=None, environ=FORK, get=no_network),
                         dict(repository='fork'))


class ForkRebuild(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.s = Synthetic(self.temp.name)

    def gate(self, head, get=None):
        return sd.fork_gate(BUILD, head, self.s.repo, environ=FORK, get=get or releases(commit=self.s.release))

    def refused(self, head, get=None):
        with self.assertRaises(ValueError) as caught:
            self.gate(head, get)
        self.assertIn('built only by the official repository', str(caught.exception))
        self.assertIn('https://github.com/TarbleFR/RewindBox/releases', str(caught.exception))
        return str(caught.exception)

    def test_the_release_rebuilt_with_the_fork_key_is_allowed(self):
        head = self.s.own_key()
        self.assertEqual(self.gate(head), dict(repository='fork', release='9.9.9', releaseCommit=self.s.release,
                                               build=BUILD))

    def test_the_unchanged_release_commit_is_allowed(self):
        self.assertEqual(self.gate(self.s.release)['release'], '9.9.9')

    def test_unreleased_work_is_refused(self):
        self.s.write('lib/app.txt', 'unreleased feature\n')
        self.s.commit('feat: unreleased work')
        self.refused(self.s.own_key())

    def test_any_other_change_is_refused(self):
        self.refused(self.s.own_key(extra=lambda: self.s.write('lib/app.txt', 'patched\n')))

    def test_a_recipe_change_beside_the_key_is_refused(self):
        self.refused(self.s.own_key(extra=lambda: self.s.write('.github/diagnostics/x.py', 'print(1)\n')))

    def test_a_manifest_change_outside_the_recipient_is_refused(self):
        for key, value in (('product', dict(effectiveDigest='f' * 64)),
                           ('components', dict(rpcs3=dict(pinSha256='2' * 64))), ('status', 'draft')):
            with self.subTest(key=key):
                changed = dict(self.s.manifest, **{key: value})
                self.refused(self.s.own_key(manifest=changed))
                self.s.git('reset', '-q', '--hard', self.s.release)

    def test_a_recipient_outside_the_key_pattern_is_refused(self):
        def elsewhere():
            value = json.loads((self.s.root / sd.manifest_path(BUILD)).read_text())
            value['recipient']['path'] = 'lib/key.pem'
            self.s.write_manifest(value)
            self.s.write('lib/key.pem', PEM_B)
        self.refused(self.s.own_key(extra=elsewhere))

    def test_a_symlinked_recipient_is_refused(self):
        def link():
            target = self.s.root / f'build-utils/delivery-{BUILD}-recipient.pem'
            target.unlink()
            target.symlink_to('../lib/app.txt')
        self.refused(self.s.own_key(extra=link))

    def test_another_build_or_an_unrelated_tag_is_refused(self):
        head = self.s.own_key()
        with self.assertRaises(ValueError):
            sd.fork_gate(BUILD + 1, head, self.s.repo, environ=FORK, get=releases(commit=self.s.release))
        first = self.s.git('rev-list', '--max-parents=0', 'HEAD')
        self.refused(head, get=releases(commit=first))

    def test_draft_prerelease_or_missing_releases_are_refused(self):
        head = self.s.own_key()
        self.refused(head, get=releases(commit=self.s.release, draft=True))
        self.refused(head, get=releases(commit=self.s.release, prerelease=True))
        self.refused(head, get=releases(tag='9.9.9', commit=None))
        self.refused(head, get=releases(commit='9' * 40))

    def test_a_merge_or_a_side_line_is_refused(self):
        side = self.s.git('rev-parse', 'HEAD')
        self.s.git('checkout', '-q', '-b', 'side')
        self.s.write('docs/side.md', 'side\n')
        self.s.commit('docs: side')
        self.s.git('checkout', '-q', 'main')
        self.s.git('merge', '-q', '--no-ff', '-m', 'merge side', 'side')
        self.refused(self.s.own_key())
        # The release commit reached only through a second parent is not on the first-parent line.
        self.s.git('checkout', '-q', '-b', 'other', side + '~1')
        self.s.write('docs/other.md', 'other\n')
        self.s.commit('docs: other')
        self.s.git('merge', '-q', '--no-ff', '-m', 'merge release', side)
        self.refused(self.s.own_key())

    def test_unreadable_official_answers_fail_closed(self):
        def broken(endpoint):
            raise subprocess.CalledProcessError(1, ['gh', 'api', endpoint])
        head = self.s.own_key()
        message = self.refused(head, get=broken)
        self.assertIn('could not be read', message)
        self.refused(head, get=lambda endpoint: {'message': 'Not Found'})


class RecipeIntegration(unittest.TestCase):
    source = (HERE / 'standard_delivery.py').read_text()

    def test_materialize_gates_before_restoring_anything(self):
        function = next(node for node in ast.parse(self.source).body
                        if isinstance(node, ast.FunctionDef) and node.name == 'materialize')
        calls = [node.func.id for node in ast.walk(function)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
        self.assertIn('fork_gate', calls)
        text = ast.get_source_segment(self.source, function)
        self.assertLess(text.index('fork_gate('), text.index('load_manifest('))
        self.assertLess(text.index('fork_gate('), text.index('materialize_tree('))

    def test_the_s2arm_line_inventory_is_unchanged(self):
        sys.path.insert(0, str(HERE / 's2arm'))
        import standard_delivery_s2arm as line
        found = line.inventory(self.source)
        for name in ('run_repository', 'official_pages', 'published_release_commits', 'release_rebuild', 'fork_gate'):
            self.assertNotIn(name, found)
        self.assertEqual(found.get('materialize'), line.RECIPE_INVENTORY['materialize'])
        self.assertEqual(found.get('jobs_that_run'), line.RECIPE_INVENTORY['jobs_that_run'])
        self.assertEqual(found.get('<module>'), line.RECIPE_INVENTORY['<module>'])

    def test_the_push_simulation_runs_jobs_guarded_by_the_official_repository(self):
        spec = dict(jobs=dict(build=dict(**{'if': "${{ github.repository == 'TarbleFR/RewindBox' && "
                                                  "contains(github.event.head_commit.message, '[x]') }}"}),
                              plain=dict(**{'if': "github.repository == 'TarbleFR/RewindBox'"})))
        self.assertEqual(sd.jobs_that_run(spec, 'feat: [x]')[0], ['build', 'plain'])
        self.assertEqual(sd.jobs_that_run(spec, 'feat: y')[0], ['plain'])


class OfficialGuardChecker(unittest.TestCase):
    """.github/ipa-protection/check_official_guard.py on synthetic repositories and on this one."""

    RECIPE = ('def run_repository():\n    pass\n\ndef release_rebuild():\n    pass\n\ndef fork_gate():\n    pass\n\n'
              'def materialize():\n    fork_gate()\n    load_manifest()\n    materialize_tree()\n')

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(HERE.parent / 'ipa-protection'))
        import check_official_guard
        cls.checker = check_official_guard

    def root(self, workflows, recipe=None):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / '.github/workflows').mkdir(parents=True)
        (root / '.github/diagnostics').mkdir(parents=True)
        (root / '.github/diagnostics/standard_delivery.py').write_text(recipe or self.RECIPE)
        for name in self.checker.EXEMPT:
            (root / '.github/workflows' / name).write_text('on: push\njobs:\n  a:\n    runs-on: x\n')
        for name, text in workflows.items():
            (root / '.github/workflows' / name).write_text(text)
        return root

    def test_this_repository_passes(self):
        self.assertEqual(self.checker.errors(), [])

    def test_an_unguarded_ipa_job_is_reported(self):
        text = ('on: push\njobs:\n  build:\n    runs-on: macos-15\n    steps:\n      - run: zip -r app.ipa Payload\n'
                '  check:\n    if: ${{ github.repository == \'TarbleFR/RewindBox\' }}\n    runs-on: ubuntu-24.04\n')
        problems = self.checker.errors(self.root({'new.yml': text}))
        self.assertEqual(len(problems), 1)
        self.assertIn('new.yml', problems[0])
        self.assertIn('build', problems[0])
        self.assertNotIn('check', problems[0].split('job(s)')[1].split('lack')[0])

    def test_guarded_jobs_and_non_ipa_workflows_pass(self):
        guarded = ('on: push\njobs:\n  build:\n    if: ${{ github.repository == \'TarbleFR/RewindBox\' && '
                   '(contains(github.event.head_commit.message, \'[x]\')) }}\n    runs-on: macos-15\n    steps:\n'
                   '      - run: python3 build-utils/delivery_cipher.py artifact a b\n')
        plain = 'on: push\njobs:\n  test:\n    runs-on: ubuntu-24.04\n    steps:\n      - run: flutter test\n'
        self.assertEqual(self.checker.errors(self.root({'guarded.yml': guarded, 'plain.yml': plain})), [])

    def test_a_guard_that_is_not_the_first_conjunct_is_reported(self):
        text = ('on: push\njobs:\n  build:\n    if: ${{ always() || github.repository == \'TarbleFR/RewindBox\' }}\n'
                '    runs-on: macos-15\n    steps:\n      - run: gh release upload 1.0 app.ipa\n')
        self.assertEqual(len(self.checker.errors(self.root({'loose.yml': text}))), 1)

    def test_a_condition_that_an_or_can_bypass_is_reported(self):
        guard = "github.repository == 'TarbleFR/RewindBox'"
        step = '    runs-on: macos-15\n    steps:\n      - run: gh release upload 1.0 app.ipa\n'
        for condition in (f"${{{{ {guard} && (github.event_name == 'push') || (github.event_name == 'x') }}}}",
                          f"${{{{ {guard} && (github.event_name == 'push') }}}} || ${{{{ (true) }}}}",
                          f"${{{{ {guard} && github.event_name == 'push' }}}}",
                          f"\"${{{{ {guard} }}}}\""):
            with self.subTest(condition=condition):
                text = f'on: push\njobs:\n  build:\n    if: {condition}\n' + step
                self.assertEqual(len(self.checker.errors(self.root({'bypass.yml': text}))), 1)
        quoted = f"${{{{ {guard} && (contains(github.event.head_commit.message, 'a)b''(c')) }}}}"
        text = f'on: push\njobs:\n  build:\n    if: {quoted}\n' + step
        self.assertEqual(self.checker.errors(self.root({'quoted.yml': text})), [])

    def test_a_recipe_without_the_gate_is_reported(self):
        late = self.RECIPE.replace('    fork_gate()\n    load_manifest()\n', '    load_manifest()\n    fork_gate()\n')
        self.assertEqual(len(self.checker.errors(self.root({}, recipe=late))), 1)
        missing = self.RECIPE.replace('def fork_gate():\n    pass\n\n', '')
        self.assertEqual(len(self.checker.errors(self.root({}, recipe=missing))), 1)


if __name__ == '__main__':
    unittest.main()

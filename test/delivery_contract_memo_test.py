#!/usr/bin/env python3
"""delivery_contract_memo on a scratch repository: a second call reuses the report
only when nothing the contract read changed, and each change recomputes it."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build-utils'))
import delivery_contract_memo as memo  # noqa: E402


def git(root, *args):
    subprocess.run(['git', *args], cwd=root, check=True, capture_output=True)


def repository(root):
    git(root, 'init', '-q')
    git(root, 'config', 'user.email', 'test@example.invalid')
    git(root, 'config', 'user.name', 'test')
    (root / 'recipe.txt').write_text('pinned\n')
    (root / 'product').mkdir()
    (root / 'product/source.txt').write_text('shipped\n')
    git(root, 'add', '.')
    git(root, 'commit', '-qm', 'base')


def main():
    os.environ.update(BUILD_NUMBER='565', GITHUB_SHA='x', GITHUB_REF_NAME='Claude')
    os.environ.pop('GIT_INDEX_FILE', None)
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch).resolve()
        repository(root)
        calls = []

        def contract():
            calls.append(1)
            # Reads a tracked file, an untracked one, a directory listing and an existence test.
            text = (root / 'recipe.txt').read_text()
            try:
                extra = (root / 'build/evidence.json').read_text()
            except FileNotFoundError:
                extra = None
            listing = sorted(os.listdir(root / 'product'))
            installed = (root / 'dist/identity.json').exists()
            return dict(recipe=text, extra=extra, listing=listing, installed=installed, pair=(1, 2))

        def run(**kwargs):
            return memo.reuse('565', contract, declared=[root / 'dist/identity.json'], root=root, **kwargs)

        first = run()
        assert calls == [1] and first['pair'] == [1, 2], (calls, first)
        assert run() == first and calls == [1], 'unchanged bytes must reuse the report'
        checks = 0

        def changed(mutate, restore, why):
            nonlocal checks
            before = len(calls)
            mutate()
            report = run()
            assert len(calls) == before + 1, why
            assert run() == report and len(calls) == before + 1, why + ': the new record is reused'
            restore()
            run()
            checks += 1

        changed(lambda: (root / 'recipe.txt').write_text('edited\n'),
                lambda: (root / 'recipe.txt').write_text('pinned\n'), 'tracked file')
        changed(lambda: ((root / 'build').mkdir(exist_ok=True), (root / 'build/evidence.json').write_text('{}')),
                lambda: (root / 'build/evidence.json').unlink(), 'untracked file the contract opened')
        changed(lambda: (root / 'product/new.txt').write_text('new'),
                lambda: (root / 'product/new.txt').unlink(), 'listed directory')
        changed(lambda: ((root / 'dist').mkdir(exist_ok=True), (root / 'dist/identity.json').write_text('{}')),
                lambda: (root / 'dist/identity.json').unlink(), 'declared existence')
        changed(lambda: os.environ.update(BUILD_NUMBER='564'),
                lambda: os.environ.update(BUILD_NUMBER='565'), 'environment')
        changed(lambda: git(root, 'rm', '-q', '--cached', 'product/source.txt'),
                lambda: git(root, 'add', 'product/source.txt'), 'index')
        changed(lambda: (git(root, 'commit', '-q', '--allow-empty', '-m', 'next')),
                lambda: None, 'commit')

        # A contract that raises is never recorded.
        record = root / memo.STORE / '565.json'
        record.unlink()

        def failing():
            raise AssertionError('contract failed')
        try:
            memo.reuse('565', failing, root=root)
        except AssertionError:
            pass
        else:
            raise AssertionError('a failing contract must raise')
        assert not record.exists(), 'a failing contract must not be recorded'

        # A contract that leaves the checkout changed is not recorded.
        def leaves_change():
            (root / 'recipe.txt').write_text('left\n')
            return {}
        memo.reuse('565', leaves_change, root=root)
        assert not record.exists(), 'a contract that changes the checkout must not be recorded'
        (root / 'recipe.txt').write_text('pinned\n')

        # The memo never stages anything in the index in use.
        status = subprocess.run(['git', 'diff', '--cached', '--name-only'], cwd=root, capture_output=True, text=True).stdout
        assert status == '', status
        print(json.dumps({'passed': True, 'changeKindsRecomputed': checks, 'failingNotRecorded': True,
                          'changingNotRecorded': True, 'indexUntouched': True}))


if __name__ == '__main__':
    main()

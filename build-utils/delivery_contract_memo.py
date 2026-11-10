#!/usr/bin/env python3
"""Run a delivery's source contract once per job; later steps reuse it while everything it read is unchanged.

Each step of a delivery job that runs the delivery module starts with the same
source contract: the build's pin and parent contract, then the whole chain of
earlier recipes in their nested views. On the macOS runner it takes about two
minutes and runs six times per delivery (build 563). The contract is a pure
function of what it reads, so the first step records its report with a key,
and a later step of the same job reuses it only when the key is unchanged:

- the commit and the tree of the index in use;
- every tracked file as it is in the working tree (a scratch copy of the index
  refreshed from the working tree), which covers each tracked file the
  contract opens and each `git diff` it runs against the working tree;
- every untracked file the contract opened and every directory it listed or
  globbed (recorded with an audit hook), and the untracked paths the caller
  declares because the contract tests their existence;
- the environment the contracts assert (BUILD_NUMBER, GITHUB_SHA,
  GITHUB_REF_NAME, GIT_INDEX_FILE), the Python version and the platform.

Any difference recomputes the contract and replaces the record; the reason is
printed. A contract that raises, or that leaves the checkout changed, is never
recorded. The record lives under build/source-contract-memo/, which no step
uploads, so another job or machine never reuses it.

Use: report = delivery_contract_memo.reuse(BUILD, source_contract, declared=[INSTALLED])
The tree module of the build must list build-utils/delivery_contract_memo.py
in its recipe, or the pin removes it.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = 'build/source-contract-memo'
ENVIRONMENT = ('BUILD_NUMBER', 'GITHUB_SHA', 'GITHUB_REF_NAME', 'GIT_INDEX_FILE')


class _Reads:
    """What the contract opened, listed and globbed while recording is active."""
    active = False
    files: set[str] = set()
    dirs: set[str] = set()
    globs: set[str] = set()


def _audit(event: str, args: tuple) -> None:
    if not _Reads.active:
        return
    if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)):
        _Reads.files.add(os.path.abspath(os.fsdecode(args[0])))
    elif event in ('os.listdir', 'os.scandir'):
        target = args[0] if args and args[0] is not None else '.'
        if isinstance(target, (str, bytes, os.PathLike)):
            _Reads.dirs.add(os.path.abspath(os.fsdecode(target)))
    elif event == 'glob.glob' and args:
        _Reads.globs.add(os.path.abspath(os.fsdecode(args[0])))


sys.addaudithook(_audit)


def _git(root: Path, *args: str, env: dict | None = None) -> str:
    return subprocess.check_output(['git', *args], cwd=root, text=True, env=env).strip()


def _sha(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def tracked_tree(root: Path) -> str:
    """The tree of every tracked file as it is in the working tree, without touching the index in use."""
    index = Path(_git(root, 'rev-parse', '--git-path', 'index'))
    index = index if index.is_absolute() else root / index
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / 'index'
        # The copy keeps the stat cache, so only files changed since the index was written are hashed.
        shutil.copyfile(index, copy)
        env = dict(os.environ, GIT_INDEX_FILE=str(copy))
        _git(root, 'add', '--update', '--', '.', env=env)
        return _git(root, 'write-tree', env=env)


def checkout_state(root: Path) -> dict:
    return dict(head=_git(root, 'rev-parse', 'HEAD'), index=_git(root, 'write-tree'), worktree=tracked_tree(root))


def _relative(root: Path, path: str) -> str | None:
    resolved = Path(path)
    try:
        relative = resolved.relative_to(root)
    except ValueError:
        return None
    # Bytecode caches are derived from tracked sources, which the key covers; imports and views create and drop them.
    if relative.parts[:1] == ('.git',) or relative.parts[:2] == tuple(STORE.split('/')) or '__pycache__' in relative.parts:
        return None
    return relative.as_posix()


def key(root: Path, reads: dict, declared) -> dict:
    tracked = set(_git(root, 'ls-files', '-z').split('\0'))
    untracked = sorted((set(reads['files']) - tracked) | {p for p in declared})
    listings = {}
    for directory in reads['dirs']:
        target = root / directory
        listings[directory] = sorted(os.listdir(target)) if target.is_dir() else None
    globs = {pattern: sorted(_relative(root, hit) or hit for hit in glob.glob(str(root / pattern), recursive=True))
             for pattern in reads['globs']}
    return dict(checkout=checkout_state(root), environment={k: os.environ.get(k) for k in ENVIRONMENT},
                python=sys.version, platform=platform.platform(),
                untracked={p: _sha(root / p) for p in untracked}, listings=listings, globs=globs)


def _difference(root: Path, saved: dict, current: dict) -> str:
    parts = [name for name in current if saved.get(name) != current[name]]
    detail = ''
    if 'checkout' in parts and saved['checkout']['worktree'] != current['checkout']['worktree']:
        changed = _git(root, 'diff', '--name-only', saved['checkout']['worktree'], current['checkout']['worktree']).splitlines()
        detail = f'; tracked files changed since: {len(changed)} ({", ".join(changed[:8])}{", ..." if len(changed) > 8 else ""})'
    if 'untracked' in parts:
        changed = sorted(p for p in set(saved['untracked']) | set(current['untracked'])
                         if saved['untracked'].get(p) != current['untracked'].get(p))
        detail += f'; untracked files changed: {", ".join(changed[:8])}'
    return ', '.join(parts) + detail


def reuse(build: str, contract, declared=(), root: Path = ROOT):
    """The contract's report, computed once per job for the same bytes."""
    declared = {Path(p).resolve().relative_to(root).as_posix() if Path(p).is_absolute() else str(p) for p in declared}
    record = root / STORE / f'{build}.json'
    if record.is_file():
        saved = json.loads(record.read_text())
        current = key(root, saved['reads'], declared)
        if current == saved['key']:
            print(f'Source contract {build}: reused, computed earlier in this job on the same bytes', flush=True)
            return saved['report']
        print(f'Source contract {build}: recomputed, changed: {_difference(root, saved["key"], current)}', flush=True)
        record.unlink()
    before = checkout_state(root)
    _Reads.files, _Reads.dirs, _Reads.globs = set(), set(), set()
    _Reads.active = True
    try:
        report = contract()
    finally:
        _Reads.active = False
    report = json.loads(json.dumps(report))
    reads = dict(files=sorted(p for p in map(lambda f: _relative(root, f), _Reads.files) if p),
                 dirs=sorted(p for p in map(lambda d: _relative(root, d), _Reads.dirs) if p is not None),
                 globs=sorted(p for p in map(lambda g: _relative(root, g), _Reads.globs) if p))
    current = key(root, reads, declared)
    if current['checkout'] != before:
        print(f'Source contract {build}: not recorded, the contract left the checkout changed', flush=True)
        return report
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps(dict(build=build, key=current, reads=reads, report=report)) + '\n')
    return report

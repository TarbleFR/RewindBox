"""Batched existence checks for the recipe modules the 586 baseline recipe still imports.

The tree modules of 559 to 586 ask, path by path, whether a commit carries a
file (rpcs3cell559_tree.exists: one `git ls-tree` per call); importing
rewind586_tree makes about 3,400 such calls, 10 of its 11 seconds. Imported
first, this module answers the same question from one listing per commit (every
file and every directory above it), so the answers are unchanged.
"""
import functools
import subprocess

import rpcs3cell559_tree as leaf


@functools.lru_cache(maxsize=None)
def listing(commit):
    names = subprocess.check_output(['git', 'ls-tree', '-r', '-z', '--full-tree', '--name-only', commit],
                                    cwd=leaf.ROOT).decode('utf-8').split('\0')
    paths = set()
    for name in filter(None, names):
        parts = name.split('/')
        paths.update('/'.join(parts[:i]) for i in range(1, len(parts) + 1))
    return frozenset(paths)


def exists(commit, path):
    return path.strip('/') in listing(commit)


leaf.exists = exists

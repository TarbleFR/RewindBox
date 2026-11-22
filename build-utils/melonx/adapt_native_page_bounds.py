"""Bound host-tracked LightningJit page-table accesses on the prepared MeloNX source."""
import hashlib
import os
from pathlib import Path
import subprocess

BASELINE = {
    'src/Ryujinx.Cpu/Jit/HostTracked/NativePageTable.cs': '790d1af6e7b2cb3f83a510b9370b591bd4c87c1841a2ef80b06201e5453d99f0',
    'src/Ryujinx.Cpu/Jit/MemoryManagerHostTracked.cs': 'ffd48399d30caa34fec2088122ec6eb78c39c8d4e8305b55ca7e0f5c263bdea6',
    'src/Ryujinx.Cpu/LightningJit/Arm64/Target/Arm64/InstEmitMemory.cs': 'baec1f26f42e46272587c23c6c727762e369ec03daa42f75e5c0f35e98668fee',
}

CANDIDATE = {
    'src/Ryujinx.Cpu/Jit/HostTracked/NativePageTable.cs': '393f72e40818627b643425b9ec895b684a2aea2b8e7d68f7c42f8b46a3e4eb7c',
    'src/Ryujinx.Cpu/Jit/MemoryManagerHostTracked.cs': 'f849fdab3a321172100d0d3eabca208bb6f245d0f38ccfb3e10828bb55a8b019',
    'src/Ryujinx.Cpu/LightningJit/Arm64/Target/Arm64/InstEmitMemory.cs': 'fa5c5343e7c1aba0bdd4d3a1c34323c67b12d3db92183f70dde66eb5499b477c',
}

_PATCH = Path(__file__).resolve().with_name('native-page-bounds.patch')


def apply_selected(tree, names, reverse=False):
    before, after = (CANDIDATE, BASELINE) if reverse else (BASELINE, CANDIDATE)
    names = sorted(set(names))
    files = [tree / name for name in names]
    if not files:
        return []
    for name, file in zip(names, files):
        if hashlib.sha256(file.read_bytes()).hexdigest() != before[name]:
            raise ValueError(f'Unexpected page-bounds adapter input: {name}')
    command = ['git', 'apply', '--whitespace=nowarn']
    if reverse:
        command.append('--reverse')
    command.extend('--include=' + name for name in names)
    # Prepared fixture copies can be nested inside the host checkout without
    # their own .git. Apply relative to this source tree in either layout.
    env = {**os.environ, 'GIT_CEILING_DIRECTORIES': str(tree.resolve().parent)}
    subprocess.run([*command, str(_PATCH)], cwd=tree, env=env, check=True)
    for name, file in zip(names, files):
        if hashlib.sha256(file.read_bytes()).hexdigest() != after[name]:
            raise ValueError(f'Unexpected page-bounds adapter output: {name}')
    return files


def apply(tree):
    return apply_selected(tree, BASELINE)


def reverse(tree):
    return apply_selected(tree, BASELINE, reverse=True)

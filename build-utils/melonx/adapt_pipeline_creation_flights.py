"""Hydrate persisted Vulkan caches asynchronously and coalesce live program/pipeline variants."""
import hashlib
import os
from pathlib import Path
import subprocess


PATCH = Path(__file__).with_name("pipeline_creation_flights.patch")
HASHES = {
    'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs': (
        '1ef7f1e1d3a7f033f394e41a05dca8e088b227f0c28de9b968900e0bd1e8c0c6',
        '3ad14bfcd5d582ab0a4154d3297ff5556441eb2949050ec44d6200e14d20b49d',
    ),
    'src/Ryujinx.Graphics.Vulkan/PipelineState.cs': (
        '7ad152350e51618bf6bb0fae4778659068a212192fa06ee499ccd3dda4ccdbf7',
        '8920a473e5a7c6d7dfdf2bbba63f6c45dffd05d06e4a252b174b4868f4cc15ce',
    ),
    'src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs': (
        'ed428f163c2bedd653e9969b448056ad7b80b4574e1730aff9a0e9d73e212f0a',
        'a9a8be00a173f08b2b1077f12b347c224c08e796811916aceef9696600380b31',
    ),
}
BASELINE = {name: hashes[0] for name, hashes in HASHES.items()}


def apply_selected(tree, names, reverse=False):
    selected = [name for name in HASHES if names is None or name in names]
    if not selected:
        return []
    args = ["git", "apply", "--whitespace=nowarn", *(["--reverse"] if reverse else []),
            *("--include=" + name for name in selected)]
    # Check all inputs before writing any of them. Never guess which upstream
    # version to patch or overwrite another adapter's changes.
    for name in selected:
        expected = HASHES[name][int(reverse)]
        if hashlib.sha256((tree / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"unexpected pipeline adapter input: {name}")
    env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(tree.resolve().parent)}
    subprocess.run([*args, "--check", str(PATCH.resolve())], cwd=tree, env=env, check=True)
    subprocess.run([*args, str(PATCH.resolve())], cwd=tree, env=env, check=True)
    for name in selected:
        expected = HASHES[name][int(not reverse)]
        if hashlib.sha256((tree / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"unexpected pipeline adapter result: {name}")
    return [tree / name for name in selected]


def apply(source):
    return apply_selected(source, BASELINE)

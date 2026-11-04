"""Control tree of a fail-closed MeloNX adapter, rebuilt from a final preparation that already contains it.

The fixtures of adapt_pipeline_warmup_parity and adapt_device_short_trim compare the tree as prepared for Core 631
(control) with that tree plus the adapter (candidate). Once prepare_embedded.py runs the adapter, the Core gates hand
them the final preparation instead. control_source() then copies it, reverses exactly the adapter's own `once`
replacements in its files, requires every file to be the pinned Core 631 preparation's bytes again, and requires the
adapter re-applied to that control to reproduce the final preparation byte for byte. A tree that is neither the 631
preparation nor exactly it plus this adapter is refused.
"""
from __future__ import annotations

import hashlib
import importlib
from pathlib import Path
import shutil
import tempfile

BOM = b'\xef\xbb\xbf'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _NoDigests(dict):
    """The adapter's file list without its entry digests (apply() checks digests through items())."""

    def items(self):
        return []


def _reverse(module_name: str, tree: Path) -> None:
    module = importlib.import_module(module_name)
    original = module.once

    def undo(path, old, new):
        text = path.read_text(encoding='utf-8-sig')
        assert text.count(new) == 1, (str(path), new[:90], text.count(new))
        path.write_text(text.replace(new, old), encoding='utf-8')

    module.once = undo
    try:
        baseline = module.BASELINE
        module.BASELINE = _NoDigests(baseline)  # the files are adapted here; the caller checks both directions
        try:
            module.apply(tree)
        finally:
            module.BASELINE = baseline
    finally:
        module.once = original
    for name, expected in baseline.items():
        path = tree / name
        if sha(path) != expected and hashlib.sha256(BOM + path.read_bytes()).hexdigest() == expected:
            path.write_bytes(BOM + path.read_bytes())  # once() drops a byte order mark; the 631 bytes carry it


def control_source(source: Path, module_name: str, holder: list) -> tuple[Path, bool]:
    """Return (tree as prepared for Core 631, whether `source` already contained the adapter)."""
    module = importlib.import_module(module_name)
    if all(sha(source / name) == expected for name, expected in module.BASELINE.items()):
        return source, False
    temporary = tempfile.TemporaryDirectory(prefix='melonx-adapter-control-')
    holder.append(temporary)
    control = Path(temporary.name) / 'control'
    shutil.copytree(source, control, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    _reverse(module_name, control)
    for name, expected in module.BASELINE.items():
        assert sha(control / name) == expected, 'not the Core 631 preparation plus this adapter: ' + name
    forward = Path(temporary.name) / 'forward'
    for name in module.BASELINE:
        (forward / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(control / name, forward / name)
    module.apply(forward)
    for name in module.BASELINE:
        assert (forward / name).read_bytes() == (source / name).read_bytes(), 'the final preparation differs from the adapter: ' + name
    return control, True

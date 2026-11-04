"""Control tree of a fail-closed MeloNX adapter, rebuilt from a final preparation that already contains it.

The fixtures of adapt_pipeline_warmup_parity and adapt_device_short_trim compare the tree as prepared for Core 631
(control) with that tree plus the adapter (candidate); those of the PR #154 adapters do the same against the Core 639
preparation. Each adapter's BASELINE pins the preparation it applies to. Once prepare_embedded.py runs the adapter, the Core gates hand
them the final preparation instead. control_source() then copies it, reverses exactly the adapter's own `once`
replacements in its files, requires every file to be the adapter's pinned preparation bytes (BASELINE) again, and requires the
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
# The adapters prepare_embedded.py runs after every Core 631 step, in its order (checked by
# melonx_adapter_control_order_test.py). A later adapter that edits a file of an earlier one is reversed first.
ORDER = ('adapt_pipeline_warmup_parity', 'adapt_device_short_trim', 'adapt_moltenvk_barrier_ordering',
         'adapt_descriptor_scratch_all_titles', 'adapt_readback_occupied_attribution', 'adapt_pipeline_miss_context')


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


def later_sharing(module_name: str) -> list:
    """Adapters that run after `module_name` and edit one of its files (directly or through another such adapter)."""
    files = set(importlib.import_module(module_name).BASELINE)
    found = []
    for later in ORDER[ORDER.index(module_name) + 1:]:
        names = set(importlib.import_module(later).BASELINE)
        if names & files:
            found.append(later)
            files |= names
    return found


def control_source(source: Path, module_name: str, holder: list) -> tuple[Path, bool]:
    """Return (tree as prepared before this adapter (its BASELINE), whether `source` already contained the adapter).

    Later adapters sharing a file are reversed first (latest first) and re-applied in the forward check, so the
    control holds neither this adapter nor them in those files; the final preparation must be reproduced exactly."""
    module = importlib.import_module(module_name)
    if all(sha(source / name) == expected for name, expected in module.BASELINE.items()):
        return source, False
    later = later_sharing(module_name)
    temporary = tempfile.TemporaryDirectory(prefix='melonx-adapter-control-')
    holder.append(temporary)
    control = Path(temporary.name) / 'control'
    shutil.copytree(source, control, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    for name in reversed(later):
        _reverse(name, control)
        for file, expected in importlib.import_module(name).BASELINE.items():
            assert sha(control / file) == expected, 'not the pinned preparation plus ' + name + ': ' + file
    _reverse(module_name, control)
    for name, expected in module.BASELINE.items():
        assert sha(control / name) == expected, 'not the pinned preparation plus this adapter: ' + name
    forward = Path(temporary.name) / 'forward'
    files = set(module.BASELINE).union(*(importlib.import_module(name).BASELINE for name in later))
    for name in files:
        (forward / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(control / name, forward / name)
    module.apply(forward)
    for name in later:
        importlib.import_module(name).apply(forward)
    for name in sorted(files):
        assert (forward / name).read_bytes() == (source / name).read_bytes(), 'the final preparation differs from the adapter: ' + name
    return control, True


def apply_present(target: Path, module_name: str, only=None) -> list:
    """Apply the adapter to those of its files a composition holds, in preparation order (it runs after every Core 631
    step). Each such file must be exactly its pinned preparation bytes (BASELINE) first; files the composition lacks are skipped."""
    module = importlib.import_module(module_name)
    # `only`: the files the composition binds to the final source; other files it holds stay partial and untouched.
    present = [name for name in module.BASELINE if (target / name).exists() and (only is None or name in only)]
    for name in present:
        assert sha(target / name) == module.BASELINE[name], 'composition is not the pinned preparation: ' + name
    if not present:
        return []
    original = module.once

    def once_present(path, old, new):
        if path.exists() and (only is None or path.relative_to(target).as_posix() in only):
            original(path, old, new)

    baseline = module.BASELINE
    module.once, module.BASELINE = once_present, _NoDigests(baseline)
    try:
        module.apply(target)
    finally:
        module.once, module.BASELINE = original, baseline
    return present

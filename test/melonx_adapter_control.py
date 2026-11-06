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
         'adapt_descriptor_scratch_all_titles', 'adapt_readback_occupied_attribution', 'adapt_pipeline_miss_context',
         'adapt_readback_receivers', 'adapt_present_source_attribution', 'adapt_teardown_compile_cancel',
         'adapt_pause_guest_threads', 'adapt_teardown_phase_marks', 'adapt_binder_teardown', 'adapt_artifact_counters',
         'adapt_array_rebuild_allocations', 'adapt_present_pacing', 'adapt_present_drawable_residency',
         'adapt_present_pacer_fixes', 'adapt_shader_save_poll', 'adapt_warmup_key_parity', 'adapt_setprogram_warmup', 'adapt_teardown_cache', 'adapt_forced_syncpoint_wait', 'adapt_session_retention', 'adapt_memory_inventory', 'adapt_guest_fault_context', 'adapt_host_warning_trim', 'adapt_safe_point_compaction', 'adapt_cold_texture_release', 'adapt_bindless_retention', 'adapt_moltenvk_stage_ordering',
         'adapt_buffer_array_barriers', 'adapt_hogwarts_precise_math', 'adapt_shader_save_journal',
         'adapt_nan_scrub', 'adapt_main_cache_checkpoint',
         'adapt_checkpoint_side_cache')


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


def reverse_present(target: Path, module_name: str, only=None) -> list:
    """Undo the adapter's `once` replacements in those of its files a composition holds: the inverse of apply_present,
    without digest checks (the caller compares the result with its control). Files the composition lacks are skipped."""
    module = importlib.import_module(module_name)
    present = [name for name in module.BASELINE if (target / name).exists() and (only is None or name in only)]
    if not present:
        return []
    original = module.once

    def undo_present(path, old, new):
        if path.exists() and (only is None or path.relative_to(target).as_posix() in only):
            text = path.read_text(encoding='utf-8-sig')
            assert text.count(new) == 1, (str(path), new[:90], text.count(new))
            path.write_text(text.replace(new, old), encoding='utf-8')

    baseline = module.BASELINE
    module.once, module.BASELINE = undo_present, _NoDigests(baseline)
    try:
        module.apply(target)
    finally:
        module.once, module.BASELINE = original, baseline
    return present


def use_authenticated_libhac_feed(tree: Path, root: Path) -> bool:
    """A copied MeloNX tree that still declares the unreachable upstream LibHac feed (a prepared source build_libhac.py did
    not configure) uses the authenticated local package instead: dist/melonx/libhac-feed holding the pinned package whose
    SHA-256 is the build_libhac identity receipt's (build_libhac.configure_feed). Otherwise the tree is left unchanged.
    Returns whether the feed was switched; a present package with a wrong digest is refused."""
    import json
    import sys
    lock = json.loads((root / 'build-utils/melonx/source.json').read_text())['libHac']
    feed = root / 'dist/melonx/libhac-feed'
    package = feed / (lock['package'] + '.' + lock['version'] + '.nupkg')
    receipt = root / 'dist/melonx/libhac-identity.json'
    config = (tree / 'nuget.config').read_text(encoding='utf-8-sig')
    if 'https://starforgejo.dev/api/packages/Ryulynx/nuget/index.json' not in config or not package.is_file() or not receipt.is_file():
        return False
    identity = json.loads(receipt.read_text())
    assert identity['source'] == lock and sha(package) == identity['packageSha256'], 'the local LibHac package is not the authenticated one'
    if str(root / 'build-utils/melonx') not in sys.path:
        sys.path.insert(0, str(root / 'build-utils/melonx'))
    from build_libhac import configure_feed
    configure_feed(tree, feed, lock['package'])
    return True



def files_edited_later(module_name: str) -> set:
    """This adapter's files that a later adapter also edits. For those, a candidate (control plus this adapter) is not the
    final preparation's bytes; control_source() already proved, in its forward check, that control plus this adapter
    plus the later ones reproduces the final preparation exactly."""
    files = set(importlib.import_module(module_name).BASELINE)
    later = set().union(*(set(importlib.import_module(name).BASELINE) for name in later_sharing(module_name)))
    return files & later

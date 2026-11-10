#!/usr/bin/env python3
"""Authenticate the device597 source lot and reconstruct its recorded preimage.

Usage: SCRIPT SOURCE --repo APP --report JSON [--baseline-out DIRECTORY]

No compiler, CMake, native test, Apple build, emulator or network is invoked.
Receipt files are authenticated as recorded evidence, not reexecuted or
promoted to evidence for different source/harness inputs.
"""
from __future__ import annotations

import argparse
import ast
import configparser
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile

CONTRACT = 'docs/evidence/rpcs3-device597-20261030/contract.json'
MANIFEST = 'build-utils/rpcs3/canonical-source.json'
PATCH = 'build-utils/rpcs3/embedded-core.patch'
PIN = 'test/neo_swap_core_pin_test.py'
DELTA = 'test/rpcs3_device597/core-delta.patch'
BASELINE_APP = '293f7feba68eddb0dc7f4a5ec3940b209cc5de35'
BASELINE_PATCH = '099651cae54c7bc567ff325735acde0cf3e931ed6e25b2b5bbcc14e5f5ecf33b'
# SHA256 of the 319 files_sha256 entries at BASELINE_APP, serialized by
# json.dumps(map, sort_keys=True, separators=(',', ':')). No Git history is
# required at execution time to authenticate the recorded baseline map.
BASELINE_MAP = '7dcad46d5a1d132f49be7dca9d627097db071d8148599ae1795a252e9a5cdfb0'
UPSTREAM = '22f1152783cef1f7e04af7b1c895173e28fd5b03'


class ContractError(RuntimeError):
    pass


def checked(condition, message):
    if not condition:
        raise ContractError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def lf(data):
    return data.replace(b'\r\n', b'\n')


def canonical_map_hash(values):
    return sha(json.dumps(values, sort_keys=True, separators=(',', ':')).encode())


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        checked(key not in result, f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def read_json(data, name):
    try:
        value = json.loads(data, object_pairs_hook=unique_object)
    except (ValueError, UnicodeError) as error:
        raise ContractError(f'Invalid JSON {name}: {error}') from error
    checked(isinstance(value, dict), f'Expected JSON object: {name}')
    return value


def relative_path(name):
    checked(isinstance(name, str) and bool(name), 'Empty or non-string input path')
    path = PurePosixPath(name)
    checked(not path.is_absolute() and path.as_posix() == name and
            all(part not in ('.', '..', '.git') for part in path.parts) and
            '\\' not in name and '\x00' not in name,
            f'Unsafe or noncanonical relative path: {name!r}')
    return name


def checked_file(root, relative):
    relative_path(relative)
    path = root / relative
    cursor = path
    while cursor != root:
        checked(not cursor.is_symlink(), f'Authenticated input crosses a symlink: {relative}')
        cursor = cursor.parent
    checked(path.is_file(), f'Missing input file: {path}')
    return path


def digest_map(value, name, allow_empty=False):
    checked(isinstance(value, dict) and (allow_empty or value), f'Invalid digest map: {name}')
    for path, digest in value.items():
        relative_path(path)
        checked(isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest),
                f'Invalid SHA-256 in {name}: {path}')
    return dict(value)


def verify_files(root, expected, canonical_lf, label):
    actual = {}
    for relative, digest in sorted(expected.items()):
        data = checked_file(root, relative).read_bytes()
        actual[relative] = sha(lf(data) if canonical_lf else data)
        checked(actual[relative] == digest, f'{label} mismatch: {relative}')
    return actual


def pin_literals(text):
    tree = ast.parse(text, filename=PIN)
    values = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ('UPSTREAM', 'PATCH_SHA256'):
                    checked(target.id not in values, f'Duplicate pin assignment: {target.id}')
                    checked(isinstance(node.value, ast.Constant) and isinstance(node.value.value, str),
                            f'Pin must be a literal string: {target.id}')
                    values[target.id] = node.value.value
    checked(set(values) == {'UPSTREAM', 'PATCH_SHA256'}, 'Missing canonical pin assignments')
    return values


def git_apply(directory, arguments, patch):
    # A baseline exported below an application checkout must still be treated
    # as its own filesystem root. Do not discover a surrounding Git worktree.
    env = dict(os.environ)
    for name in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR'):
        env.pop(name, None)
    env['GIT_CEILING_DIRECTORIES'] = str(directory.parent)
    process = subprocess.run(['git', '-c', 'apply.whitespace=nowarn', 'apply', '--no-index',
                              *arguments, str(patch)], cwd=directory, env=env,
                             capture_output=True, timeout=60)
    checked(process.returncode == 0,
            f'git apply {arguments!r} failed: {process.stderr.decode(errors="replace").strip()}')
    return process.stdout


def patch_paths(directory, patch):
    raw = git_apply(directory, ['--reverse', '--numstat', '-z'], patch)
    paths = set()
    for entry in raw.split(b'\x00'):
        if not entry:
            continue
        parts = entry.split(b'\t', 2)
        checked(len(parts) == 3 and parts[2], 'Unsupported renamed or malformed delta path')
        path = parts[2].decode('utf-8')
        relative_path(path)
        checked(path not in paths, f'Duplicate delta file: {path}')
        paths.add(path)
    return paths


def submodule_paths(source):
    path = source / '.gitmodules'
    if not path.is_file():
        return []
    checked(not path.is_symlink(), 'Submodule manifest must not be a symlink')
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(path.read_text())
    result = []
    for section in parser.sections():
        if parser.has_option(section, 'path'):
            name = parser.get(section, 'path').strip()
            relative_path(name)
            result.append(name)
    checked(len(result) == len(set(result)), 'Duplicate submodule path')
    checked(not any(left != right and right.startswith(left + '/')
                    for left in result for right in result), 'Overlapping submodule paths')
    return sorted(result)


def copy_source_with_separate_submodules(source, destination, modules):
    module_set = set(modules)
    for module in modules:
        parent = (source / module).parent
        while parent != source:
            checked(not parent.is_symlink(), f'Submodule parent crosses a source symlink: {module}')
            parent = parent.parent

    def ignored(directory, names):
        relative = Path(directory).relative_to(source)
        return [name for name in names if name == '.git' or (relative / name).as_posix() in module_set]

    # Only ordinary source is duplicated. Populated LLVM/other dependencies
    # stay separate, so exporting a test baseline does not copy gigabytes of
    # unchanged submodule data. Neither the delta nor normalization may touch
    # those paths, and no command here runs inside a dependency target.
    shutil.copytree(source, destination, symlinks=True, ignore=ignored)
    linked = {}
    unavailable = []
    for module in modules:
        original = source / module
        if not original.is_dir():
            checked(not original.is_file(), f'Submodule path is an ordinary file: {module}')
            unavailable.append(module)
            continue
        target = destination / module
        target.parent.mkdir(parents=True, exist_ok=True)
        checked(not os.path.lexists(target), f'Submodule destination was unexpectedly copied: {module}')
        target.symlink_to(original, target_is_directory=True)
        linked[module] = str(original)
    return linked, unavailable


def protect_output(report, source, repo, input_paths, baseline_out):
    protected = {repo / relative for relative in input_paths}
    checked(report not in protected, 'Report would overwrite an authenticated repository input')
    checked(not report.is_relative_to(source), 'Report must be outside the source tree')
    if baseline_out is not None:
        checked(not baseline_out.is_relative_to(source) and not source.is_relative_to(baseline_out),
                'Baseline output must not overlap the source tree')
        checked(not repo.is_relative_to(baseline_out), 'Baseline output must not contain the repository')
        checked(not report.is_relative_to(baseline_out), 'Report must be outside the baseline output')
        if baseline_out.exists():
            checked(baseline_out.is_dir() and not any(baseline_out.iterdir()),
                    'Baseline output already exists and is not an empty directory')


def verify(args, result):
    source, repo = args.source.resolve(), args.repo.resolve()
    checked(source.is_dir() and repo.is_dir(), 'Source and repository directories must exist')
    report = args.report.resolve()
    baseline_out = args.baseline_out.resolve() if args.baseline_out else None
    protect_output(report, source, repo, [CONTRACT, MANIFEST, PATCH, PIN, DELTA], baseline_out)
    contract_bytes = checked_file(repo, CONTRACT).read_bytes()
    record = read_json(contract_bytes, CONTRACT)
    current = digest_map(record.get('files_sha256'), 'files_sha256')
    previous = digest_map(record.get('baseline_files_sha256'), 'baseline_files_sha256')
    upstream_previous = digest_map(record.get('baseline_upstream_files_sha256'),
                                   'baseline_upstream_files_sha256', allow_empty=True)
    repository_inputs = digest_map(record.get('repository_inputs'), 'repository_inputs')
    checked(CONTRACT not in repository_inputs, 'The contract cannot hash itself recursively')
    protect_output(report, source, repo,
                   set(repository_inputs) | {CONTRACT, MANIFEST, PATCH, PIN, DELTA}, baseline_out)
    result['report_path_validated'] = True
    checked(record.get('baseline_app_commit') == BASELINE_APP,
            'Unexpected baseline application commit')
    checked(record.get('baseline_patch_sha256') == BASELINE_PATCH,
            'Unexpected baseline canonical patch')
    checked(len(previous) == 319 and canonical_map_hash(previous) == BASELINE_MAP,
            'Baseline map differs from the authenticated 319-postimage IPA597 source')
    checked(set(previous) <= set(current), 'Baseline canonical paths were removed from the current manifest')
    new_paths = set(current) - set(previous)
    checked(set(upstream_previous) <= new_paths,
            'Upstream preimage digests must name newly canonical paths only')
    checked(record.get('delta_path') == DELTA, 'Unexpected delta path')

    raw_inputs = {relative:checked_file(repo, relative).read_bytes()
                  for relative in (MANIFEST, PATCH, PIN, DELTA)}
    manifest = read_json(raw_inputs[MANIFEST], MANIFEST)
    checked(manifest.get('files_sha256') == current, 'Canonical manifest postimages differ from contract')
    checked(manifest.get('upstream_commit') == record.get('upstream_commit') == UPSTREAM,
            'Canonical upstream revision mismatch')
    patch_digest = sha(raw_inputs[PATCH])
    checked(patch_digest == manifest.get('patch_sha256') == record.get('patch_sha256'),
            'Canonical patch SHA-256 mismatch')
    pins = pin_literals(raw_inputs[PIN].decode())
    checked(pins['UPSTREAM'] == UPSTREAM and pins['PATCH_SHA256'] == patch_digest,
            'Canonical source pin mismatch')
    delta_digest = sha(raw_inputs[DELTA])
    checked(delta_digest == record.get('delta_sha256'), 'Inverse delta SHA-256 mismatch')

    current_actual = verify_files(source, current, True, 'Current Core postimage')
    repository_actual = verify_files(repo, repository_inputs, False, 'Repository input')
    changed = sorted(path for path in previous if previous[path] != current[path])
    preserved = sorted(path for path in previous if previous[path] == current[path])
    created = sorted(new_paths - set(upstream_previous))
    modules = submodule_paths(source) if baseline_out is not None else []
    checked(not any(path == module or path.startswith(module + '/')
                    for module in modules for path in current),
            'Canonical postimages must not write through separate submodule paths')
    result.update({
        'contract_sha256':sha(contract_bytes), 'canonical_manifest_sha256':sha(raw_inputs[MANIFEST]),
        'canonical_patch_sha256':patch_digest, 'pin_sha256':sha(raw_inputs[PIN]),
        'delta_sha256':delta_digest, 'upstream_commit':UPSTREAM,
        'baseline_app_commit':BASELINE_APP, 'baseline_patch_sha256':BASELINE_PATCH,
        'baseline_map_sha256':BASELINE_MAP,
        'counts':{'current_postimages':len(current), 'baseline_postimages':len(previous),
                  'changed_existing':len(changed), 'new_canonical':len(new_paths),
                  'new_canonical_from_upstream':len(upstream_previous),
                  'new_created_files':len(created), 'preserved':len(preserved),
                  'repository_inputs':len(repository_inputs)},
        'changed':changed, 'new':sorted(new_paths), 'preserved':preserved,
        'new_created_files':created, 'new_canonical_from_upstream':sorted(upstream_previous),
        'repository_inputs':repository_actual,
        'core_hashes':{'current_lf_sha256':current_actual},
    })
    if baseline_out is not None:
        baseline_out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='rpcs3-device597-contract-',
                                     dir=baseline_out.parent if baseline_out else None) as temporary:
        work = Path(temporary)
        baseline = work / 'baseline'
        module_links, unavailable_modules = {}, []
        if baseline_out is None:
            baseline.mkdir()
        else:
            module_links, unavailable_modules = copy_source_with_separate_submodules(source, baseline, modules)
        # Authenticate/copy canonical text in Git's LF representation so the
        # same reviewed delta applies to LF and CRLF materializations.
        for relative in current:
            destination = baseline / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(lf(checked_file(source, relative).read_bytes()))
        delta_copy = work / 'core-delta.patch'
        delta_copy.write_bytes(lf(raw_inputs[DELTA]))
        touched = patch_paths(baseline, delta_copy)
        checked(touched == set(changed) | new_paths,
                'Delta paths differ from the changed/new canonical scope: '
                f'extra={sorted(touched - set(changed) - new_paths)}, '
                f'missing={sorted((set(changed) | new_paths) - touched)}')
        checked(not any(path == module or path.startswith(module + '/')
                        for module in modules for path in touched),
                'The inverse delta must not modify a separate submodule')
        git_apply(baseline, ['--reverse', '--check'], delta_copy)
        git_apply(baseline, ['--reverse'], delta_copy)
        baseline_actual = verify_files(baseline, previous, True, 'Reconstructed baseline Core postimage')
        upstream_actual = verify_files(baseline, upstream_previous, True, 'Reconstructed upstream preimage')
        for relative in created:
            checked(not os.path.lexists(baseline / relative), f'New file survived inverse delta: {relative}')
        result['core_hashes'].update(baseline_lf_sha256=baseline_actual,
                                     baseline_upstream_lf_sha256=upstream_actual)
        result['inverse_delta_verified'] = True
        result['delta_paths_verified'] = sorted(touched)
        # Do not export a reconstruction if reviewed inputs changed during it.
        verify_files(source, current, True, 'Current Core postimage changed during verification')
        verify_files(repo, repository_inputs, False, 'Repository input changed during verification')
        checked(checked_file(repo, CONTRACT).read_bytes() == contract_bytes, 'Contract changed during verification')
        for relative, data in raw_inputs.items():
            checked(checked_file(repo, relative).read_bytes() == data,
                    f'Canonical metadata changed during verification: {relative}')
        if baseline_out is not None:
            if baseline_out.exists():
                checked(baseline_out.is_dir() and not any(baseline_out.iterdir()),
                        'Baseline destination became nonempty during verification')
                baseline_out.rmdir()
            baseline.rename(baseline_out)
            result['baseline_export'] = {
                'path':str(baseline_out), 'full_source_copy':True,
                'git_metadata_copied':False, 'canonical_text_normalized_to_lf':True,
                'submodule_paths_preserved':modules,
                'baseline_submodule_links':module_links,
                'unavailable_submodule_paths':unavailable_modules,
                'submodule_scope':'Declared submodule directories linked to unchanged candidate dependency paths; no fetch, hard link or writes through those links; contents not globally authenticated by this Core contract.',
            }
        else:
            result['baseline_export'] = {'path':None, 'full_source_copy':False,
                                         'temporary_postimages_removed_after_verification':True}
    result['passed'] = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--baseline-out', type=Path)
    args = parser.parse_args()
    result = {
        'passed':False, 'scope':'Canonical Core/repository byte authentication and inverse delta only',
        'checker_sha256':sha(Path(__file__).read_bytes()),
        'source':str(args.source.resolve()), 'repository':str(args.repo.resolve()),
        'compiler_invoked':False, 'native_test_executed':False, 'harness_regenerated':False,
        'codegen_identities_computed':False,
        'apple_build':False, 'device_test':False, 'fps_claim':False,
        'receipt_scope':'Repository inputs authenticate recorded receipt bytes only. Historical Apple/host receipts retain their original source and harness scope; no new execution or applicability is inferred.',
        'reusability_scope':'Exact source/harness reuse and partial/stale receipt exclusions are documented separately in the authenticated review inputs.',
    }
    try:
        verify(args, result)
    except (ContractError, OSError, ValueError, SyntaxError, subprocess.SubprocessError) as error:
        result['failure'] = str(error)
    # Never overwrite a protected input in order to report an invalid request.
    if result.pop('report_path_validated', False):
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + '\n')
    elif not result.get('failure'):
        result['failure'] = 'Report path could not be validated'
    summary = {key:result[key] for key in ['passed', 'scope', 'failure', 'counts',
               'inverse_delta_verified', 'baseline_export', 'compiler_invoked', 'native_test_executed',
               'apple_build', 'device_test', 'fps_claim'] if key in result}
    print(json.dumps(summary, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())

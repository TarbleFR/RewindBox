#!/usr/bin/env python3
"""Preserve a compiled candidate after metadata failure without validating it.

This collector never replaces a gate, changes a binary or promotes an artifact.
It copies only regular files from explicit owned roots and labels recovery bytes
unverified. Missing/malformed proof leaves source inputs unavailable, never guessed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat

MAX_RSP_FILES = 20_000
MAX_RSP_BYTES = 128 * 1024 * 1024
MAX_INPUT_BYTES = 64 * 1024 * 1024


def fingerprint(path: Path) -> dict:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return {'bytes': path.stat().st_size, 'sha256': digest.hexdigest()}


def regular(path: Path, root: Path) -> bool:
    try:
        return (not path.is_symlink() and stat.S_ISREG(path.lstat().st_mode)
                and path.resolve(strict=True).is_relative_to(root.resolve(strict=True)))
    except (OSError, ValueError):
        return False


def load_proof(path: Path, warnings: list) -> dict:
    if path.is_symlink() or not path.is_file():
        warnings.append({'input': 'proof', 'reason': 'not_available_as_regular_file'})
        return {}
    try:
        value = json.loads(path.read_text())
        if not isinstance(value, dict):
            raise ValueError('proof is not an object')
        return value
    except (OSError, ValueError) as error:
        warnings.append({'input': 'proof', 'reason': 'unreadable', 'detail': str(error)})
        return {}


def copy_regular(source: Path, destination: Path, root: Path) -> dict:
    if not regular(source, root):
        raise ValueError('source is not a regular file inside its explicit root')
    before = fingerprint(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination, follow_symlinks=False)
    if fingerprint(destination) != before:
        raise ValueError('source changed during recovery capture')
    return before


def gate_identity_present(dist: Path, source: str, core_digest: dict) -> bool:
    identity = dist / 'identity.json'
    if not regular(identity, dist):
        return False
    try:
        item = json.loads(identity.read_text())
        return (item.get('type') == 'rpcs3-ios-mvk-deferred-cache-candidate'
                and item.get('host_commit') == source
                and item.get('abi_version') == 30 and item.get('architectures') == ['arm64']
                and item.get('actual_ios_syntax_compile_link_passed') is True
                and item.get('sha256') == core_digest['sha256']
                and item.get('bytes') == core_digest['bytes'])
    except (OSError, ValueError, AttributeError):
        return False


def owned_root(proof: dict, name: str, warnings: list) -> Path | None:
    value = proof.get(name)
    if not isinstance(value, str) or not value:
        warnings.append({'input': name, 'reason': 'not_recorded_in_proof'})
        return None
    root = Path(value)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        warnings.append({'input': name, 'reason': 'not_an_explicit_regular_directory'})
        return None
    return root.resolve(strict=True)


def collect(dist: Path, proof_path: Path, diagnostics: Path, source: str, run_id: str, *, job_status: str = "success") -> dict:
    diagnostics.mkdir(parents=True, exist_ok=True)
    manifest_path = diagnostics / 'unverified-core-manifest.json'
    if diagnostics.is_symlink() or manifest_path.exists() or manifest_path.is_symlink():
        raise ValueError('recovery diagnostics must be owned and the manifest must be new')
    result = {'schema': 1, 'collector_source_sha256': fingerprint(Path(__file__))['sha256'],
              'source_commit': source, 'run_id': run_id, 'validation_status': 'unverified',
              'prior_job_status': job_status, 'gate_identity_present': False,
              'status': 'no_core_available', 'full_dist_copied': False,
              'files': {}, 'captured_build_inputs': {}, 'warnings': [],
              'native_compilation_by_collector': False, 'binary_modified': False,
              'verified_core_claimed': False, 'device_tested': False, 'fps_gain_claimed': False}
    warnings = result['warnings']
    core = dist / 'libRPCS3Core.dylib'
    if dist.is_symlink() or not regular(core, dist):
        warnings.append({'input': 'core', 'reason': 'not_available_as_regular_file'})
    else:
        core_digest = fingerprint(core)
        identity_present = gate_identity_present(dist, source, core_digest)
        result['gate_identity_present'] = identity_present
        if identity_present and job_status != 'failure':
            result['status'] = 'gate_identity_present_recovery_not_needed'
        else:
            destination = diagnostics / 'unverified-core'
            inputs = diagnostics / 'captured-build-inputs'
            if destination.exists() or destination.is_symlink() or inputs.exists() or inputs.is_symlink():
                raise ValueError('refusing to overwrite existing recovery directories')
            destination.mkdir()
            result['status'] = ('unverified_capture_due_to_job_failure'
                                if job_status == 'failure' else 'captured_unverified_core')
            result['core'] = core_digest
            # Do not follow a symlink or copy a device/socket from an unexpected dist.
            for folder, directories, filenames in os.walk(dist, followlinks=False):
                parent = Path(folder)
                for name in list(directories):
                    child = parent / name
                    if child.is_symlink():
                        directories.remove(name)
                        warnings.append({'input': str(child.relative_to(dist)), 'reason': 'refused_symlink'})
                    else:
                        (destination / child.relative_to(dist)).mkdir(parents=True, exist_ok=True)
                for name in filenames:
                    child = parent / name
                    relative = child.relative_to(dist)
                    if not regular(child, dist):
                        warnings.append({'input': str(relative), 'reason': 'refused_non_regular_file'})
                        continue
                    result['files'][str(relative)] = copy_regular(child, destination / relative, dist)
            result['full_dist_copied'] = not warnings
            proof = load_proof(proof_path, warnings)
            native = owned_root(proof, 'compiled_source_root', warnings)
            if native is not None:
                header = native / 'rpcs3/git-version.h'
                if regular(header, native) and header.stat().st_size <= MAX_INPUT_BYTES:
                    result['captured_build_inputs']['git-version.h'] = dict(
                        copy_regular(header, inputs / 'git-version.h', native), source_path=str(header))
                else:
                    warnings.append({'input': 'git-version.h', 'reason': 'unavailable_or_outside_source_root'})
            build = owned_root(proof, 'build_root', warnings)
            count, total = 0, 0
            if build is not None:
                for folder, directories, filenames in os.walk(build, followlinks=False):
                    parent = Path(folder)
                    for name in list(directories):
                        if (parent / name).is_symlink():
                            directories.remove(name)
                            warnings.append({'input': str((parent/name).relative_to(build)), 'reason': 'refused_build_directory_symlink'})
                    for name in sorted(filenames):
                        if not name.endswith('.rsp'):
                            continue
                        response = parent / name
                        relative = response.relative_to(build)
                        if not regular(response, build):
                            warnings.append({'input': str(relative), 'reason': 'refused_response_non_regular_file'})
                            continue
                        size = response.stat().st_size
                        if count >= MAX_RSP_FILES or size > MAX_INPUT_BYTES or total + size > MAX_RSP_BYTES:
                            warnings.append({'input': str(relative), 'reason': 'response_capture_bound_exceeded'})
                            continue
                        key = str(Path('link-response') / relative)
                        result['captured_build_inputs'][key] = dict(
                            copy_regular(response, inputs / key, build), source_path=str(response))
                        count += 1
                        total += size
            result['captured_response_files'] = count
            result['captured_response_bytes'] = total
    manifest_path.write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, required=True)
    parser.add_argument('--proof', type=Path, required=True)
    parser.add_argument('--diagnostics', type=Path, required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--job-status', choices=('success', 'failure', 'cancelled'), default='success')
    args = parser.parse_args()
    result = collect(args.dist.absolute(), args.proof.absolute(), args.diagnostics.absolute(), args.source, args.run_id, job_status=args.job_status)
    print(json.dumps({key: result[key] for key in ('status', 'validation_status', 'full_dist_copied', 'verified_core_claimed')}))


if __name__ == '__main__':
    main()

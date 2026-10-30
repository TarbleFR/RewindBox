#!/usr/bin/env python3
"""Authenticate original Apple reuse bytes and reject corruptions; no native execution."""
import argparse
import copy
import json
from pathlib import Path
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
import rpcs3device601_reuse as reuse


class ChangedMember:
    def __init__(self, archive, name, raw):
        self.archive, self.name, self.raw = archive, name, raw

    def read(self, name):
        return self.raw if name == self.name else self.archive.read(name)


def audit(source, baseline, archive_path):
    manifest, record = reuse.support.load(ROOT / reuse.MANIFEST), reuse.support.load(ROOT / reuse.RECORD)
    upstream = reuse.support.upstream_dependencies(source, manifest)
    rejected = []

    def reject(name, function):
        try:
            function()
        except (ValueError, KeyError, AssertionError, RuntimeError):
            rejected.append(name)
        else:
            raise AssertionError('Accepted corrupt reuse input: ' + name)

    with zipfile.ZipFile(reuse.reference_archive(path=archive_path)) as archive:
        previous, _ = reuse.original_proof(archive)
        host = previous['host']
        specs = reuse.prior_specifications()
        plain = previous['tests']['tiny-vertex-plain']
        sanitized = previous['tests']['tiny-vertex-asan-ubsan']
        reuse.check_original_mode(archive, plain, specs['tiny-vertex-plain'], previous)
        reject('proof-bytes', lambda: reuse.original_proof(ChangedMember(
            archive, 'runtime592-proof.json', archive.read('runtime592-proof.json') + b'\n')))
        for member in ('report', 'output', 'compile_trace'):
            changed = ChangedMember(archive, plain[member], archive.read(plain[member]) + b'\n')
            reject(member + '-bytes', lambda changed=changed: reuse.check_original_mode(
                changed, plain, specs['tiny-vertex-plain'], previous))
        rows = [json.loads(line) for line in archive.read(plain['compile_trace']).decode().splitlines() if line.strip()]
        compilation = next(row for row in rows if row['units'])
        unit = compilation['units'][0]
        captured = reuse.captured_member(unit['saved'], plain)
        reject('captured-cpp-bytes', lambda: reuse.check_trace(
            ChangedMember(archive, captured, archive.read(captured) + b'\n'), plain,
            specs['tiny-vertex-plain'], host['compiler_argv']))
        changed_rows = copy.deepcopy(rows)
        next(row for row in changed_rows if row['units'])['args'].append('-DNDEBUG')
        changed_trace = ('\n'.join(json.dumps(row) for row in changed_rows) + '\n').encode()
        reject('NDEBUG-compiler-flag', lambda: reuse.check_trace(
            ChangedMember(archive, plain['compile_trace'], changed_trace), plain,
            specs['tiny-vertex-plain'], host['compiler_argv']))
        changed_rows = [json.loads(line) for line in archive.read(sanitized['compile_trace']).decode().splitlines() if line.strip()]
        next(row for row in changed_rows if row['units'])['args'].append('-fno-sanitize=alignment')
        changed_trace = ('\n'.join(json.dumps(row) for row in changed_rows) + '\n').encode()
        reject('disabled-sanitizer-compiler-flag', lambda: reuse.check_trace(
            ChangedMember(archive, sanitized['compile_trace'], changed_trace), sanitized,
            specs['tiny-vertex-asan-ubsan'], host['compiler_argv']))
        altered_host = dict(host, compiler='Homebrew clang version 22.1.9')
        reject('current-compiler-version', lambda: reuse.authenticate(
            source, baseline, manifest, record, altered_host, upstream, path=archive_path))
        altered_manifest = copy.deepcopy(manifest)
        altered_manifest['files_sha256']['rpcs3/Emu/RSX/rsx_cache.h'] = '0' * 64
        reject('extra-current-production-change', lambda: reuse.authenticate(
            source, baseline, altered_manifest, record, host, upstream, path=archive_path))
        altered_record = copy.deepcopy(record)
        next(job for job in altered_record['apple_validation_jobs'] if job['name'] == 'tiny-vertex-plain')['checks'] = []
        reject('changed-reused-job', lambda: reuse.authenticate(
            source, baseline, manifest, altered_record, host, upstream, path=archive_path))
        sys.path.insert(0, str(ROOT / 'test'))
        import rpcs3_device601_reuse_programs as programs
        report = json.loads(archive.read(plain['report']))
        changed_report = copy.deepcopy(report)
        changed_report['results'][1]['program_sha256'] = '0' * 64
        reject('generated-program-relevance', lambda: programs.audit_report(
            changed_report, specs['tiny-vertex-plain'], source, baseline, ROOT))
        with tempfile.TemporaryDirectory(prefix='device601-reuse-negative-') as tmp:
            scratch = Path(tmp).resolve()
            path = scratch / 'source/rpcs3/Emu/RSX/rsx_cache.h'
            path.parent.mkdir(parents=True)
            path.write_bytes((source / 'rpcs3/Emu/RSX/rsx_cache.h').read_bytes() + b'\n')
            reject('actual-current-production-input', lambda: programs.audit_report(
                report, specs['tiny-vertex-plain'], scratch / 'source', baseline, ROOT))
            previous_out = reuse.OUT
            reuse.OUT = scratch / 'installed'
            try:
                provenance, installed = reuse.authenticate(source, baseline, manifest, record, host, upstream,
                                                           path=archive_path, install=True)
                reuse.verify_installed(installed, installed)
                relabeled = copy.deepcopy(installed)
                relabeled['tiny-vertex-plain']['native_executed_now'] = True
                reject('reused-result-relabeled-new', lambda: reuse.verify_installed(relabeled, installed))
                item = installed['tiny-vertex-plain']
                member = next(iter(item['captured_input_sha256']))
                path = reuse.OUT / member
                raw = path.read_bytes()
                path.write_bytes(raw + b'\n')
                reject('installed-capture-bytes', lambda: reuse.verify_installed(installed, installed))
                path.write_bytes(raw)
                reuse.verify_installed(installed, installed)
            finally:
                reuse.OUT = previous_out
    return dict(passed=True, source=reuse.SOURCE, run=reuse.RUN, artifact=reuse.ARTIFACT,
                archive_sha256=reuse.ARCHIVE_SHA, reused_modes=len(reuse.REUSED), fresh_modes_required=len(reuse.FRESH),
                compiler_executed=False, native_executed=False, apple_executed=False,
                negative_controls_rejected=rejected, provenance=provenance)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.source.resolve(), args.baseline.resolve(), args.archive.resolve())
    reuse.support.save(args.report, result)
    print(json.dumps(result, indent=2))

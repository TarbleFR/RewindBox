#!/usr/bin/env python3
"""Reauthenticate Apple receipts on a different host without native execution.

Only the expected final --report output directory is relocated for command
comparison. The archived proof, original commands, sources, report bytes and
all source/semantic validators remain unchanged. The local output directory
must already contain the exact extracted diagnostic files.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import subprocess
import sys
import time

sys.dont_write_bytecode = True
APPLE_REPORTS = Path('/Users/runner/work/RewindBox/RewindBox/build/rpcs3-core-diagnostics')
SOURCE = '5b2a5614f634221ea896607b4686ad2afdd5ada3'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo', type=Path, required=True)
    ap.add_argument('--source-tree', type=Path, required=True)
    ap.add_argument('--proof', type=Path, required=True)
    ap.add_argument('--artifact-verification', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    repo = args.repo.resolve()
    assert Path.cwd() == repo
    assert not args.output.exists()
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == SOURCE
    sys.path[:0] = [str(repo / '.github/diagnostics'), str(repo / 'test')]
    import rpcs3runtime_global_core as gate
    import rpcs3runtime_bo2_warm_core as pipeline
    proof_bytes = args.proof.read_bytes()
    proof = json.loads(proof_bytes)
    artifact = json.loads(args.artifact_verification.read_bytes())
    assert proof['source'] == artifact['source'] == SOURCE
    assert artifact['passed'] and artifact['all_three_archive_bytes_verified']
    assert artifact['files_sha256']['runtime592-proof.json'] == sha(proof_bytes)
    assert gate.OUT == repo / 'build/rpcs3-core-diagnostics'
    recorded_roots = {k: Path(v) for k, v in proof['baseline_roots'].items()}
    relocations = {}
    original_commands = {}

    for name, (_, modes) in gate.all_tests().items():
        for mode in modes:
            key = name + '-' + mode
            state = proof['tests'][key]
            if 'reused_from' in state:
                continue
            original = gate.runner_command(name, mode, Path(proof['source_root']),
                                            recorded_roots, proof['host']['compilerCommand'])
            recorded = state['command']
            filename = key + '-result.json'
            assert original.count('--report') == recorded.count('--report') == 1, key
            assert original[-2:] == ['--report', str(gate.OUT / filename)], key
            assert recorded[-2:] == ['--report', str(APPLE_REPORTS / filename)], key
            assert len(original) == len(recorded) and original[:-1] == recorded[:-1], key
            assert sum(a != b for a, b in zip(original, recorded)) == 1, key
            assert sha((gate.OUT / filename).read_bytes()) == state['report_sha256'], key
            original_commands[key] = original
            relocations[key] = {'argument': '--report', 'local': original[-1],
                                'recordedApple': recorded[-1], 'allOtherArgumentsExact': True}
    assert len(relocations) == 12

    class PortableCommandView:
        def __getattr__(self, name):
            return getattr(gate, name)

        @staticmethod
        def runner_command(name, mode, source, roots, compiler):
            key = name + '-' + mode
            result = gate.runner_command(name, mode, source, roots, compiler)
            assert key in relocations and result == original_commands[key], key
            # No argument other than the verified output-directory token changes.
            return result[:-1] + [relocations[key]['recordedApple']]

    start = time.monotonic()
    checked = pipeline.verify(args.proof, args.source_tree, gate=PortableCommandView())
    elapsed = time.monotonic() - start
    assert checked == proof and args.proof.read_bytes() == proof_bytes
    result = {
        'passed': True, 'kind': 'portable-full-global-core-source-and-receipt-reverification',
        'source': SOURCE, 'command': [sys.executable, *sys.argv], 'elapsedSeconds': elapsed,
        'proofSHA256': sha(proof_bytes), 'verificationScriptSHA256': sha(Path(__file__).read_bytes()),
        'artifactVerificationSHA256': sha(args.artifact_verification.read_bytes()),
        'runtimeInputs': len(proof['input_sha256']),
        'nativePostimages': len(proof['native_source_sha256']),
        'nativeSupplements': len(proof['supplemental_native_sha256']),
        'appleModes': len(proof['tests']),
        'reusedModesFromPartialRuns': sum('reused_from' in s for s in proof['tests'].values()),
        'onlyRecordedOutputDirectoryRelocatedForCommandComparison': relocations,
        'fullRecordedCommandsAndSemanticCountersAuthenticated': True,
        'materializedSourceAuthenticated': True, 'originalPipelineVerifierCalled': True,
        'originalSourcesAndProofUnmodified': True,
        'nativeTestsExecuted': False, 'cmakeExecuted': False, 'nativeBinaryExecuted': False,
        'physicalDeviceTested': False, 'gameplayMeasured': False,
        'verifiedUTC': datetime.now(timezone.utc).isoformat(),
    }
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('passed', 'runtimeInputs', 'nativePostimages',
        'nativeSupplements', 'appleModes', 'reusedModesFromPartialRuns', 'nativeTestsExecuted')}))


if __name__ == '__main__':
    main()

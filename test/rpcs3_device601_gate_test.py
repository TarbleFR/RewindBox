#!/usr/bin/env python3
"""Seal/review the one-file device601 source lot; reject corrupted gate inputs.

This executes no native compiler and never dispatches CI. --seal writes only
this lot's small inverse delta and contract, leaving the canonical manifest to
the caller. Normal mode verifies the full source contract and negative controls
in a disposable repository with shared read-only Git objects.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
import rpcs3runtime_device601_core as gate

REL = 'rpcs3/Emu/RSX/rsx_cache.h'
RUNNER = 'test/rpcs3_tiny_vertex_cache_test.py'
RANGE = 'test/rpcs3_device597/renderer/test_vertex_upload_key.py'
FIXTURE = 'test/rpcs3_device597/renderer/fixtures/VKVertexBuffers.before.cpp'
CPU = 'test/rpcs3_spu_mfc_decrementer_test.py'
BOOT = 'test/rpcs3_exitspawn_worker601_test.py'
FEEDBACK = 'test/rpcs3_color_feedback_test.py'
STATUS = 'test/rpcs3_savestate_completion601_test.py'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def seal(source, baseline):
    manifest = gate.load(ROOT / gate.MANIFEST)
    original = json.loads(gate.at(gate.BASE, gate.MANIFEST))
    changes = {}
    for path in manifest['files_sha256']:
        before = (baseline / path).read_bytes().replace(b'\r\n', b'\n')
        after = (source / path).read_bytes().replace(b'\r\n', b'\n')
        if path in original['files_sha256']:
            assert digest(before) == original['files_sha256'][path], path
        else:
            assert before == subprocess.check_output(['git', '-C', str(source), 'show', 'HEAD:' + path]), path
        if before != after:
            changes[path] = dict(before=digest(before), after=digest(after))
            if path not in original['files_sha256']:
                changes[path]['upstream_preimage_blob'] = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD:' + path], text=True).strip()
    assert set(changes) == {REL, 'rpcs3/Emu/Cell/SPUThread.cpp', 'rpcs3/Emu/CPU/JITCacheCompatibility.cmake',
                            'rpcs3/Emu/Cell/lv2/sys_process.cpp', 'rpcs3/ios/IOSRestoreExecutor.h',
                            'rpcs3/ios/RPCS3IOS.cpp', 'rpcs3/ios/NeoStationSavestateStatus.h',
                            'rpcs3/Emu/RSX/VK/VKDraw.cpp'}, changes
    delta = (ROOT / gate.DELTA).read_bytes()
    jobs = []
    for mode in ['plain', 'asan-ubsan']:
        sanitized = mode == 'asan-ubsan'
        argv = ['python3', '{repo}/' + RUNNER, '--source', '{source}', '--baseline', '{baseline}', '--output', '{output}']
        index = 1
        if sanitized:
            argv += ['--sanitizer', '--variant', 'candidate-ios']
            index = 0
        jobs.append(dict(name='tiny-vertex-' + mode, mode=mode, argv=argv, report='{output}/result.json',
                         checks=[{'path': ['sanitizer'], 'equals': sanitized},
                                 {'path': ['results', index, 'result', 'stale_short'], 'equals': 0},
                                 {'path': ['results', index, 'result', 'guard_page_lengths'], 'equals': 7},
                                 {'path': ['gpu_executed'], 'equals': False}]))
        argv = ['python3', '{repo}/' + RANGE, '--source', '{source}', '--output', '{output}']
        if sanitized:
            argv += ['--sanitizer']
        jobs.append(dict(name='vertex-range-' + mode, mode=mode, argv=argv, report='{output}/result.json',
                         checks=[{'path': ['sanitizer'], 'equals': sanitized},
                                 {'path': ['variants', 'before', 'result', 'wrong_range_reuses'], 'equals': 300},
                                 {'path': ['variants', 'after', 'result', 'wrong_range_reuses'], 'equals': 0},
                                 {'path': ['variants', 'after', 'result', 'ordinary_mismatches'], 'equals': 0}]))
    for mode in ['plain', 'asan-ubsan']:
        sanitized = mode == 'asan-ubsan'
        argv = ['python3', '{repo}/' + CPU, '{source}', '--baseline', '{baseline}', '--report', '{output}/result.json']
        if sanitized:
            argv += ['--sanitizer', 'address,undefined']
        jobs.append(dict(name='mfc-decrementer-' + mode, mode=mode, argv=argv, report='{output}/result.json',
                         checks=[{'path': ['passed'], 'equals': True},
                                 {'path': ['results', 'baselineBlockedDueSchedules'], 'equals': 3},
                                 {'path': ['results', 'candidateDeadlineInterrupts'], 'equals': 3},
                                 {'path': ['results', 'commandsAcceptedExactlyOnce'], 'equals': 96},
                                 {'path': ['results', 'lateSnrPreserved'], 'equals': 4},
                                 {'path': ['results', 'maskedDisabledFrozenOrStale'], 'equals': 8},
                                 {'path': ['results', 'concurrentDeadlineInterrupts'], 'equals': 64}]))
        argv = ['python3', '{repo}/' + BOOT, '{source}', '--baseline', '{baseline}', '--report', '{output}/result.json']
        if sanitized:
            argv += ['--sanitize']
        jobs.append(dict(name='exitspawn-worker-' + mode, mode=mode, argv=argv, report='{output}/result.json',
                         checks=[{'path': ['passed'], 'equals': True},
                                 {'path': ['cases'], 'equals': 22},
                                 {'path': ['candidate_boots_on_worker'], 'equals': True},
                                 {'path': ['stop_and_cleanup_on_ui'], 'equals': True},
                                 {'path': ['ui_heartbeat_while_native_boot_blocked'], 'equals': True},
                                 {'path': ['api_stop_waits_without_native_overlap'], 'equals': True},
                                 {'path': ['failed_save_before_kill_resumes_self'], 'equals': True},
                                 {'path': ['successful_save_resumes_self_after_exact_replacement'], 'equals': True},
                                 {'path': ['failed_save_after_kill_reports_stopped_without_fxo_read'], 'equals': True},
                                 {'path': ['finish_registration_race_preserved'], 'equals': True},
                                 {'path': ['actual_savestate_operation'], 'equals': True},
                                 {'path': ['stale_stopped_incarnation_flags_untouched'], 'equals': True}]))
        argv = ['python3', '{repo}/' + STATUS, '{source}', '--baseline', '{baseline}', '--report', '{output}/result.json']
        if sanitized:
            argv += ['--sanitize']
        jobs.append(dict(name='savestate-completion-' + mode, mode=mode, argv=argv, report='{output}/result.json',
                         checks=[{'path': ['passed'], 'equals': True},
                                 {'path': ['actual_header_compiled'], 'equals': True},
                                 {'path': ['exceptions_disabled'], 'equals': True},
                                 {'path': ['results', 'callback_outside_mutex'], 'equals': True},
                                 {'path': ['results', 'callback_lifetime_released'], 'equals': True},
                                 {'path': ['results', 'registration_finish_races'], 'equals': 1200}]))
        argv = ['python3', '{repo}/' + FEEDBACK, '--source', '{source}', '--baseline', '{baseline}', '--output', '{output}']
        if sanitized:
            argv += ['--sanitizer']
        jobs.append(dict(name='color-feedback-' + mode, mode=mode, argv=argv, report='{output}/result.json',
                         checks=[{'path': ['sanitizer'], 'equals': sanitized},
                                 {'path': ['gpu_executed'], 'equals': False},
                                 {'path': ['variants', 0, 'result', 'order_dependent_cases'], 'equals': 2},
                                 {'path': ['variants', 1, 'result', 'order_dependent_cases'], 'equals': 0},
                                 {'path': ['variants', 2, 'result', 'order_dependent_cases'], 'equals': 2}]))
    inputs = [gate.GATE, gate.ROUTE, gate.support.GATE, gate.WORKFLOW, gate.BUILD, gate.DELTA, RUNNER, RANGE, FIXTURE,
              'test/rpcs3_device601_gate_test.py', gate.RECEIPT, gate.CODEGEN,
              'test/neo_swap_core_pin_test.py', 'packages/dolphin_internal_bridge/ci/verify_ipa.py',
              'build-utils/validate_single_ipa_distribution.py', 'build-utils/configure_neoswap_donor.py',
              'build-utils/configure_neoswap_relay.py', 'build-utils/embed_rpcs3_host_entitlements.py',
              'build-utils/configure_rpcs3_ios_v2.py', 'build-utils/rpcs3/llvm-aarch64-ghc-emergency-spill.patch',
              'build-utils/rpcs3/patch_moltenvk_compile_qos.py', 'build-utils/rpcs3/patch_moltenvk_exec_queue.py',
              'build-utils/validate_rpcs3_embedded_core.py', 'build-utils/validate_rpcs3_passive_dlopen.py']
    inputs += [CPU, BOOT, FEEDBACK, STATUS, gate.HOST_CODEGEN, gate.HOST_CODEGEN_REPORT,
               'test/rpcs3_device597/cpu/run_late_snr.py', 'test/rpcs3_device597/cpu/late_snr.cpp.in',
               'test/native/rpcs3_spu_mfc_decrementer.inc', 'test/native/rpcs3_exitspawn_worker601.cpp',
               'test/native/rpcs3_savestate_completion601.cpp']
    support = {}
    for path in ['Utilities/Thread.h', 'rpcs3/Emu/Cell/MFC.h']:
        assert path not in manifest['files_sha256']
        raw = (source / path).read_bytes()
        assert raw == subprocess.check_output(['git', '-C', str(source), 'show', 'HEAD:' + path])
        support[path] = dict(sha256=digest(raw), upstream_blob=subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD:' + path], text=True).strip())
    assert manifest['policy'].startswith(original['policy'])
    policy_append = manifest['policy'][len(original['policy']):]
    record = dict(phase='reboot-timer-feedback', policy_append=policy_append, schema=1, baseline_app_commit=gate.BASE, historical_core_source=gate.HIST,
                  canonical_patch_sha256=manifest['patch_sha256'], native_changes=changes,
                  delta_sha256=digest(delta), repository_inputs={p: gate.file_sha(ROOT / p) for p in sorted(inputs)},
                  baseline_support=support, host_codegen_audit={'runner': gate.HOST_CODEGEN, 'report': gate.HOST_CODEGEN_REPORT,
                  'report_sha256': gate.file_sha(ROOT / gate.HOST_CODEGEN_REPORT)}, apple_validation_jobs=jobs,
                  historical_scope='Original 28 Apple native modes remain historical; archived bytes authenticate only during an authorized native build.',
                  affected_historical_tests='Vertex, full-MFC-queue/decrementer, feedback and restart programs execute on changed production paths; no old generated-program equivalence is claimed.',
                  unchanged_scope='All native paths outside the eight recorded changes are exact. CPU emission inputs are unchanged except the two host bodies with an independently checked exact alias; exports/settings remain exact.')
    gate.save(ROOT / gate.RECORD, record)
    print(json.dumps({gate.KEY: {'source_contract': gate.RECORD, 'source_contract_sha256': gate.file_sha(ROOT / gate.RECORD)}}, indent=2))


def verify_with_negative_controls(source):
    gate.source_contract(source)
    current = gate.load(ROOT / gate.RECORD)
    paths = set(current['repository_inputs']) | {gate.RECORD, gate.MANIFEST, gate.PATCH}
    negatives = []
    with tempfile.TemporaryDirectory(prefix='device601-gate-mutations-') as tmp:
        scratch = Path(tmp)
        subprocess.run(['git', 'init', '-q', str(scratch)], check=True)
        alternate = scratch / '.git/objects/info/alternates'
        alternate.write_text(str(ROOT / '.git/objects') + '\n')
        subprocess.run(['git', '-C', str(scratch), 'update-ref', 'HEAD', gate.BASE], check=True)
        for name in paths:
            target = scratch / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        old_root, old_out, support_root = gate.ROOT, gate.OUT, gate.support.ROOT
        gate.ROOT, gate.OUT, gate.support.ROOT = scratch, scratch / 'output', scratch
        try:
            gate.source_contract(source)
            controls = [
                ('canonical-bytes', gate.PATCH, lambda b: b + b'\n'),
                ('native-manifest', gate.MANIFEST, lambda b: json.dumps(dict(json.loads(b), files_sha256={**json.loads(b)['files_sha256'], REL: '0' * 64})).encode()),
                ('missing-native-change', gate.RECORD, lambda b: json.dumps(dict(json.loads(b), native_changes={})).encode()),
                ('runner-input', RUNNER, lambda b: b + b'\n# changed\n'),
                ('recipe', gate.BUILD, lambda b: b + b'\n'),
                ('dispatcher', gate.ROUTE, lambda b: b.replace(b"if 'device601_20261030'", b"if 'unexpected_601'", 1)),
                ('historical-receipt', gate.RECEIPT, lambda b: b + b'\n'),
                ('codegen-evidence', gate.CODEGEN, lambda b: b + b'\n'),
                ('inverse-delta', gate.DELTA, lambda b: b + b'\n'),
            ]
            for name, relative, mutate in controls:
                path = scratch / relative
                before = path.read_bytes()
                path.write_bytes(mutate(before))
                try:
                    gate.source_contract(source)
                except (ValueError, KeyError, AssertionError, RuntimeError):
                    negatives.append(name)
                else:
                    raise AssertionError('Gate accepted corruption: ' + name)
                finally:
                    path.write_bytes(before)
        finally:
            gate.ROOT, gate.OUT, gate.support.ROOT = old_root, old_out, support_root
    assert len(negatives) == 9
    return dict(passed=True, phase=current['phase'], compiler_executed=False, apple_executed=False, changed_paths=sorted(current['native_changes']),
                postimages_checked=len(gate.load(ROOT / gate.MANIFEST)['files_sha256']),
                preserved_postimages=len(gate.load(ROOT / gate.MANIFEST)['files_sha256']) - len(current['native_changes']), negative_controls_rejected=negatives,
                native_jobs_scheduled=len(current['apple_validation_jobs']), historical_native_modes_replayed=0,
                historical_archives_verified_locally=False, abi_exports=88)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--seal', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.seal:
        assert args.baseline is not None
        seal(args.source.resolve(), args.baseline.resolve())
    else:
        report = verify_with_negative_controls(args.source.resolve())
        if args.report:
            gate.save(args.report, report)
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

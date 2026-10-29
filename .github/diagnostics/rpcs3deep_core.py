#!/usr/bin/env python3
"""Build the reviewed d6da80ad source, not the historical Build499 test snapshot.

Authenticate the delivered reference, all three source deltas, and exact native
programs already reviewed on Linux. Execute those programs on Apple ARM64, then
compile the actual iPhone Core. Historical fixtures/assertions are not changed.
"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'test'))
SOURCE = 'd6da80adf9f6a089c05ba79058a32ee0032d075f'
BASE0 = 'c0df3394d81d957eb7b28c85802278b69cc0f71b'
BASE1 = '543996ad1e79330fda81d086af27566dce0fd79e'
BASE2 = 'a363d92332657196fb3b6085a98c62e119310bcc'
HIST = 'f42573afc25842ca9a0068f4ad505bbfe5342623'
PATCH = 'build-utils/rpcs3/embedded-core.patch'
MANIFEST = 'build-utils/rpcs3/canonical-source.json'
BUILD = 'build-utils/build_rpcs3_embedded_core.sh'
GATE = '.github/diagnostics/rpcs3deep_core.py'
WORKFLOW = '.github/workflows/rpcs3-deep-audit-core.yml'
HISTORY = 'docs/evidence/rpcs3-runtime-refinement-20261029/apple-core/success-f42573af/'
EVIDENCE = 'docs/evidence/rpcs3-deep-audit-20261029/'
OUT = ROOT / 'build/rpcs3-core-diagnostics'
PROOF = OUT / 'deep-audit-proof.json'
PATCH_SHA = '5ba1424bcd40afc96f3263e236d84ed643cb7aac15cbcd1fb513e85d24e27ec8'
HOOK = '''if [[ -n "${RPCS3_DEEP_NATIVE_PROOF:-}" ]]; then
  python3 "$PWD/.github/diagnostics/rpcs3deep_core.py" --source "$SRC" --verify-reuse "$RPCS3_DEEP_NATIVE_PROOF"
elif [[ -n "${RPCS3_RUNTIME592_NATIVE_PROOF:-}" ]]; then'''
ANCHOR = 'if [[ -n "${RPCS3_RUNTIME592_NATIVE_PROOF:-}" ]]; then'
NATIVE_NAMES = ('array', 'temporary', 'address', 'coverage', 'timer', 'remap',
                'snr', 'mfc-irq', 'mfc-restore', 'shader', 'texture', 'async', 'arena', 'trim')
EXPECTED_KEYS = {n + '-' + m for n in NATIVE_NAMES for m in ('plain', 'asan-ubsan')} | {
    'barriers-plain', 'store-full-plain', 'store-full-asan-ubsan'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical_sha(data):
    """Use the canonical manifest's documented CRLF-only normalization."""
    return sha(data.replace(b'\r\n', b'\n'))


# These fields are emitted only by optional benchmarks, not the correctness
# matrix. Native programs run without benchmark arguments in this Apple gate.
BENCHMARK_FIELDS = {
    'address': {'benchmarks', 'indexHeadersBytes', 'hostAdapterSectionBytes'},
    'coverage': {'benchmarks', 'sink'},
    'shader': {'benchmarks'}, 'texture': {'copyBenchmarks'},
    'arena': {'benchmarks'}, 'trim': {'benchmarks'},
}


def validate_native_result(name, result, previous):
    """Check real output schemas and exact deterministic negative controls.

    Several original programs deliberately emit counters rather than a top-level
    `passed`. Their unchanged assertions plus these counters establish success.
    Timings remain preserved in the report but are never correctness thresholds.
    """
    assert isinstance(result, dict) and isinstance(previous, dict), name
    excluded = set(BENCHMARK_FIELDS.get(name, set()))
    if name == 'address':
        # Iteration counts depend on the host's C++ standard-library
        # container/layout behavior. They are not cross-platform reference
        # values. The old and indexed production paths must still perform
        # exactly the same positive number of predicate calls on this host.
        counters = ('baselineDirtyPredicateCalls', 'indexedDirtyPredicateCalls')
        for observed in (result, previous):
            assert all(type(observed.get(k)) is int and observed[k] > 0 for k in counters), (name, 'missing predicate count')
            assert observed[counters[0]] == observed[counters[1]], (name, 'old/new predicate calls differ')
        excluded.update(counters)
    current = {k: v for k, v in result.items() if k not in excluded}
    expected = {k: v for k, v in previous.items() if k not in excluded}
    assert current and current == expected, (name, 'native correctness output', current, expected)
    if name == 'coverage':
        assert result.get('sink') == 0, 'Coverage correctness run must not run benchmarks'
    for field in excluded - {'sink'}:
        assert field not in result or isinstance(result[field], (list, int)), (name, field)
    return current


def apple_host_program(name, original):
    """Adapt the isolated MFC restore test's global enum, not RPCS3 production.

    Darwin declares ::wait(int*) through sys/wait.h. This adapter historically
    declared the unscoped enumerator ::wait as well. Rename only the host-test
    enumerator and its qualified reads; keep the numeric flag 2. The original
    source program and its reviewed SHA256 remain separately authenticated.
    """
    if name == 'arena':
        # libc++'s mt19937_64 result_type and size_t are different typedefs.
        # Split only the fixture declarations; preserve types, RNG call order,
        # values and both complete production allocator classes.
        pairs = [
            ('const auto size=1+rng()%128, alignment=std::size_t{1} << (rng()%8);', 'const auto size=1+rng()%128; const auto alignment=std::size_t{1} << (rng()%8);'),
            ('const auto offset=rng()%(capacity+32), size=rng()%512, page=std::size_t{1}<<(rng()%9);', 'const auto offset=rng()%(capacity+32); const auto size=rng()%512; const auto page=std::size_t{1}<<(rng()%9);'),
        ]
        for before, after in pairs:
            assert original.count(before) == 1, 'Unexpected arena fixture declaration'
            original = original.replace(before, after, 1)
        return original
    if name == 'barriers':
        # Two constants belong to the isolated Vulkan boundary preamble; only
        # the color case consumes this test's aspect flags. Keep all values.
        line = 'constexpr u32 VK_IMAGE_ASPECT_COLOR_BIT=1,VK_IMAGE_ASPECT_DEPTH_BIT=2,VK_IMAGE_ASPECT_STENCIL_BIT=4,VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER=45;'
        assert original.count(line) == 1, 'Unexpected barrier test preamble'
        return original.replace(line, line.replace('VK_IMAGE_ASPECT_DEPTH_BIT=2', 'VK_IMAGE_ASPECT_DEPTH_BIT [[maybe_unused]]=2').replace('VK_IMAGE_ASPECT_STENCIL_BIT=4', 'VK_IMAGE_ASPECT_STENCIL_BIT [[maybe_unused]]=4'), 1)
    if name == 'shader':
        # Only the isolated test preamble has an unused sentinel on Darwin.
        # Keep its value and the entire canonical/extracted program intact.
        sentinel = 'constexpr auto umax=static_cast<usz>(-1);'
        assert original.count(sentinel) == 1, 'Unexpected shader test preamble'
        return original.replace(sentinel, '[[maybe_unused]] ' + sentinel, 1)
    if name != 'mfc-restore':
        return original
    enum = 'enum cpu_flag:u32 {pending=1,wait=2,temp=4};'
    old_flag = 'cpu_flag::wait'
    assert original.count(enum) == 1, 'Unexpected MFC restore enum source'
    assert original.count(old_flag) >= 2, 'Expected MFC restore flag reads'
    modified = original.replace(enum, 'enum cpu_flag:u32 {pending=1,rbx_wait=2,temp=4};', 1)
    modified = modified.replace(old_flag, 'cpu_flag::rbx_wait')
    assert old_flag not in modified
    return modified


def command(*args, cwd=ROOT, data=None):
    return subprocess.check_output([str(x) for x in args], cwd=cwd, input=data, timeout=240)


def at(commit, path):
    return command('git', 'show', commit + ':' + path)


def load(path):
    return json.loads(Path(path).read_bytes())


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def native_hashes(source, manifest):
    assert command('git', '-C', source, 'rev-parse', 'HEAD').decode().strip() == manifest['upstream_commit']
    for path, digest in manifest['files_sha256'].items():
        assert canonical_sha((source / path).read_bytes()) == digest, path


def inputs():
    import neo_swap_core_pin_test as pin
    paths = set(pin.CORE_INPUTS) | {GATE, WORKFLOW, '.github/diagnostics/rpcs3deep_resume.py', '.github/diagnostics/rpcs3deep_resume2.py', '.github/diagnostics/rpcs3deep_resume3.py', '.github/workflows/rpcs3-core.yml',
        '.github/workflows/rpcs3-runtime592-core.yml',
        '.github/diagnostics/rpcs3runtime592_core.py'}
    # Close the test/extraction dependency set, including historical adapters.
    paths.update(command('git', 'ls-files', 'test', 'native/neoswap-storage').decode().splitlines())
    for folder in [EVIDENCE, HISTORY, 'docs/evidence/rpcs3-device595-20261029/',
                   'docs/evidence/rpcs3-device595-followup-20261029/',
                   'docs/evidence/rpcs3-temporary-remap-20261029/']:
        paths.update(command('git', 'ls-files', folder).decode().splitlines())
    return {p: sha((ROOT / p).read_bytes()) for p in sorted(paths)}


def source_contract(source):
    manifest = load(ROOT / MANIFEST)
    for path in (MANIFEST, PATCH, 'native/neoswap-storage/Store.cpp'):
        assert (ROOT / path).read_bytes() == at(SOURCE, path), path
    assert manifest['patch_sha256'] == sha((ROOT / PATCH).read_bytes()) == PATCH_SHA
    assert len(manifest['files_sha256']) == 319
    native_hashes(source, manifest)
    # Protect the historically successful 592 recipe without changing it.
    # This candidate changes the validator dispatch, not the compiler steps.
    old_workflow = '.github/workflows/rpcs3-runtime592-core.yml'
    assert (ROOT / old_workflow).read_bytes() == at(SOURCE, old_workflow), 'Original runtime592 workflow modified'
    route = (ROOT / '.github/diagnostics/rpcs3runtime592_core.py').read_text()
    assert "if 'deep_audit_20261029' in manifest():" in route
    assert "deep.prepare(a.source.resolve())" in route
    assert "deep.verify(a.verify_reuse, a.source.resolve())" in route
    assert "deep.identity(a.write_core_identity)" in route
    assert "shutil.copyfile(deep.PROOF, OUT / 'runtime592-proof.json')" in route
    original = at(SOURCE, BUILD).decode()
    assert original.count(ANCHOR) == 1
    assert (ROOT / BUILD).read_text() == original.replace(ANCHOR, HOOK, 1), 'Unexpected recipe edits'
    import neo_swap_core_pin_test as pin
    for path in set(pin.CORE_INPUTS) - {BUILD, '.github/workflows/rpcs3-core.yml'}:
        assert (ROOT / path).read_bytes() == at(SOURCE, path), path
    command('git', 'merge-base', '--is-ancestor', SOURCE, 'HEAD')
    exports = sorted((source / 'rpcs3/ios/RPCS3IOS.exports').read_text().split())
    assert len(exports) == len(set(exports)) == 88
    return manifest, exports


def historical_reference():
    """Verify archived successful Apple evidence; never label it a new execution."""
    receipt = load(ROOT / (HISTORY + 'artifact-verification.json'))
    proof_raw = (ROOT / (HISTORY + 'preflight/runtime592-proof.json')).read_bytes()
    identity_raw = (ROOT / (HISTORY + 'core/identity.json')).read_bytes()
    proof, identity = json.loads(proof_raw), json.loads(identity_raw)
    assert receipt['passed'] and receipt['all_three_archive_bytes_verified']
    assert receipt['source'] == proof['source'] == identity['host_commit'] == HIST
    assert sha(proof_raw) == receipt['files_sha256']['runtime592-proof.json']
    assert sha(identity_raw) == receipt['files_sha256']['identity.json']
    assert proof['all_tests_passed'] and len(proof['tests']) == 11
    assert proof['host']['system'] == 'Darwin' and proof['host']['machine'] == 'arm64'
    base = json.loads(at(BASE0, MANIFEST))
    assert proof['native_source_sha256'] == identity['native_source_sha256'] == base['files_sha256']
    assert receipt['canonical_patch_sha256'] == base['patch_sha256']
    assert identity['sha256'] == receipt['core_sha256']
    for path, digest in proof['input_sha256'].items():
        assert sha(at(HIST, path)) == digest, path
    for key, state in proof['tests'].items():
        assert state['passed'] and state['returncode'] == 0
        for suffix, field in [('-result.json', 'report_sha256'), ('-output.txt', 'output_sha256')]:
            raw = (ROOT / (HISTORY + 'diagnostics/' + key + suffix)).read_bytes()
            assert sha(raw) == state[field], key
    return dict(source=HIST, run=receipt['run_id'], proofSHA256=sha(proof_raw),
                coreSHA256=receipt['core_sha256'], archivedAppleModes=11,
                historicalTestsReexecuted=False, oldBinaryReused=False)


def materialize(source, commit, target):
    manifest = json.loads(at(commit, MANIFEST))
    patch = at(commit, PATCH)
    assert sha(patch) == manifest['patch_sha256']
    command('git', 'clone', '-q', '--shared', '--no-checkout', source, target)
    command('git', '-C', target, 'checkout', '-q', '--detach', manifest['upstream_commit'])
    command('git', '-C', target, 'apply', '--whitespace=nowarn', '-', data=patch)
    native_hashes(target, manifest)
    return target


def control_copy(source, target, paths):
    for path in set(paths):
        dest = target / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / path, dest)
    return target


def programs(source, roots, work):
    """Extract current production bodies. Controls isolate only their old behavior."""
    import rpcs3_device595_test as allocations
    import rpcs3_texture_address_index_test as address
    import rpcs3_temporary_remap_test as remap
    import rpcs3_spu_timer_reuse_test as timer
    import rpcs3_surface_coverage_test as coverage
    import rpcs3_jit_arena_merge_test as arena
    import neoswap_trim_total_test as trim
    before, first, second = roots
    initial = 'docs/evidence/rpcs3-device595-20261029/'
    follow = 'docs/evidence/rpcs3-device595-followup-20261029/'
    result = {}

    def add(name, code, evidence, modes=('plain', 'asan-ubsan')):
        previous = load(ROOT / evidence)
        assert previous['passed'] and sha(code.encode()) == previous['harnessSHA256'], name
        result[name] = dict(program=code, modes=modes, evidence=evidence)

    for name in ('array', 'temporary'):
        add(name, getattr(allocations, 'make_' + name)(source, before)[0], initial + name + '-plain.json')
    add('address', address.harness(source, before), initial + 'address-plain.json')
    add('coverage', coverage.harness(source, first), follow + 'surface-coverage-plain.json')

    # Later SPU changes are unrelated to the timer worker; preserve them on both
    # sides of this isolated negative control. The resulting complete test program
    # must still have exactly the originally reviewed SHA256.
    runtime = timer.runtime
    old_worker = address.braced(runtime.timer(first), 'void operator()()')
    new_worker = address.braced(runtime.timer(source), 'void operator()()')
    assert new_worker == address.braced(runtime.timer(second), 'void operator()()')
    timer_before = control_copy(source, work / 'timer-control', runtime.SOURCE + runtime.SUPPORT)
    path = timer_before / runtime.CPP
    text = path.read_text()
    assert text.count(new_worker) == 1
    path.write_text(text.replace(new_worker, old_worker, 1))
    add('timer', timer.harness(source, timer_before), follow + 'spu-timer-reuse-plain.json')

    # Retain current pool/barrier fixes on both sides; remove only the old missing
    # remap wrapper in the negative control, not in production.
    remap_before = control_copy(source, work / 'remap-control', remap.SOURCE + remap.SUPPORT)
    wrapper = address.braced((source / remap.SOURCE[1]).read_text(), remap.SIGNATURE)
    assert wrapper == address.braced((second / remap.SOURCE[1]).read_text(), remap.SIGNATURE)
    for rel, block in [(remap.SOURCE[1], '#ifdef RPCS3_IOS\n\t' + wrapper + '\n#endif\n\n'),
                       (remap.SOURCE[0], '#ifdef RPCS3_IOS\n' + remap.DECLARATION + '\n#endif\n\n')]:
        path = remap_before / rel
        text = path.read_text()
        assert text.count(block) == 1
        path.write_text(text.replace(block, '', 1))
    add('remap', remap.harness(source, remap_before), 'docs/evidence/rpcs3-temporary-remap-20261029/plain.json')

    modules = [('snr', 'rpcs3_spu_snr_event_test', 'gow3-snr-plain.json'),
               ('mfc-irq', 'rpcs3_spu_mfc_full_irq_test', 'gow3-mfc-full-irq-plain.json'),
               ('mfc-restore', 'rpcs3_spu_mfc_restore_test', 'gow3-mfc-restore-plain.json'),
               ('shader', 'rpcs3_shader_token_test', 'shader-tokens-plain.json'),
               ('texture', 'rpcs3_texture_deep_test', 'texture-plain.json'),
               ('async', 'rpcs3_async_sync_pool_test', 'async-sync-pool-plain.json'),
               ('barriers', 'rpcs3_texture_barrier_test', 'texture-barriers.json')]
    for name, module, evidence in modules:
        code = importlib.import_module(module).harness(source, second)
        if isinstance(code, tuple):
            code = code[0]
        add(name, code, EVIDENCE + evidence, ('plain',) if name == 'barriers' else ('plain', 'asan-ubsan'))
    add('arena', arena.harness((second / arena.HEADER).read_text(), (source / arena.HEADER).read_text()), EVIDENCE + 'cpu-jit-arena-plain.json')
    add('trim', trim.harness(at(BASE2, trim.STORE).decode(), (ROOT / trim.STORE).read_text()), EVIDENCE + 'cpu-neoswap-trim-plain.json')
    assert len(result) == 15 and sum(len(x['modes']) for x in result.values()) == 29
    return result


def run_checked(argv, log, env=None):
    run = subprocess.run([str(x) for x in argv], cwd=ROOT, env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, timeout=300)
    log.write_bytes(run.stdout)
    if run.returncode:
        print(run.stdout.decode(errors='replace'), flush=True)
        raise RuntimeError(f'Command failed ({run.returncode}): {argv}; log: {log}')
    return run.stdout


def prepare(source):
    assert platform.system() == 'Darwin' and platform.machine() == 'arm64'
    manifest, exports = source_contract(source)
    OUT.mkdir(parents=True, exist_ok=True)
    current = inputs()
    compiler = shlex.split(os.environ['CXX'])
    version = command(*compiler, '--version').decode().splitlines()[0]
    assert re.search(r'clang version 22\.', version), version
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1', UBSAN_OPTIONS='halt_on_error=1')
    proof = dict(schema=1, source=command('git', 'rev-parse', 'HEAD').decode().strip(),
                 source_root=str(source), source_patch_sha256=PATCH_SHA,
                 input_sha256=current, native_source_sha256=manifest['files_sha256'],
                 exported_symbols=exports, host=dict(system='Darwin', machine='arm64', compiler=version),
                 historical=historical_reference(), tests={}, all_tests_passed=False,
                 physical_device_tested=False, gameplay_measured=False, public_release=False)
    save(PROOF, proof)
    with tempfile.TemporaryDirectory(prefix='rpcs3-deep-apple-') as directory:
        work = Path(directory)
        roots = [materialize(source, c, work / c[:8]) for c in (BASE0, BASE1, BASE2)]
        # Check each complete canonical delta independently, not only the last lot.
        stages = [(BASE0, roots[0]), (BASE1, roots[1]), (BASE2, roots[2]), (SOURCE, source)]
        for i, key in enumerate(('device595_allocations_20261029', 'device595_followup_20261029', 'deep_audit_20261029')):
            prior_commit, prior_tree = stages[i]
            next_commit, next_tree = stages[i + 1]
            old = json.loads(at(prior_commit, MANIFEST))
            new = json.loads(at(next_commit, MANIFEST))
            record = new[key]
            assert record['baseline_commit'] == prior_commit
            assert record['baseline_patch_sha256'] == old['patch_sha256']
            changed = {p for p, h in new['files_sha256'].items() if old['files_sha256'].get(p) != h}
            assert changed == set(record['files_after_sha256'])
            assert set(old['files_sha256']) <= set(new['files_sha256'])
            assert sha((ROOT / record['delta_fixture']).read_bytes()) == record['delta_sha256']
            for p in changed:
                actual_before = canonical_sha((prior_tree / p).read_bytes())
                actual_after = canonical_sha((next_tree / p).read_bytes())
                assert actual_before == record['files_before_sha256'][p], (key, p, 'before', actual_before)
                assert actual_after == record['files_after_sha256'][p], (key, p, 'after', actual_after)
        contract = OUT / 'deep-source-contract.json'
        run_checked(['python3', 'test/rpcs3_deep_audit_contract_test.py', source, '--baseline', roots[2], '--report', contract], OUT / 'deep-source-contract.log')
        assert load(contract)['reverseDeltaMatchesBaseline']
        proof['codegen'] = load(contract)['codegenIdentity']['after']
        proof['source_contract_sha256'] = sha(contract.read_bytes())
        import rpcs3deep_resume3 as resume
        prior = resume.authenticate(sys.modules[__name__], proof)
        proof['partial_reuse'] = resume.ORIGIN
        save(PROOF, proof)
        suites = programs(source, roots, work)
        for name, item in suites.items():
            cpp = OUT / (name + '-program.cpp')
            original_program = item['program']
            assert sha(original_program.encode()) == load(ROOT / item['evidence'])['harnessSHA256']
            cpp.write_text(apple_host_program(name, original_program))
            if name in ('mfc-restore', 'shader', 'barriers', 'arena'):
                (OUT / (name + '-canonical.cpp')).write_text(original_program)
            for mode in item['modes']:
                key = name + '-' + mode
                print('RUN ' + key, flush=True)
                flags = ['-std=c++20', '-UNDEBUG', '-Wall', '-Wextra', '-Werror', '-pthread',
                         '-isysroot', os.environ['HOST_MACOS_SDK'], '-O1' if mode != 'plain' else '-O3']
                if mode != 'plain':
                    flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-sanitize-recover=all']
                if key in resume.MODES:
                    proof['tests'][key] = resume.retain(sys.modules[__name__], prior, key, item, cpp, flags, version)
                    save(PROOF, proof)
                    print('REUSE ' + key + ' from failed run ' + str(resume.RUN) + '; not executed again', flush=True)
                    continue
                exe = work / key
                compile_log = OUT / (key + '-compile.txt')
                output_log = OUT / (key + '-output.txt')
                run_checked([*compiler, *flags, cpp, '-o', exe], compile_log, env)
                result = json.loads(run_checked([exe], output_log, env))
                validate_native_result(name, result, load(ROOT / item['evidence'])['results'])
                record = dict(passed=True, program_sha256=sha(cpp.read_bytes()), evidence=item['evidence'],
                              canonical_program_sha256=sha(original_program.encode()),
                              apple_host_adapter=(name in ('mfc-restore', 'shader', 'barriers', 'arena')),
                              compiler=version, flags=flags, results=result, mode=mode,
                              output_sha256=sha(output_log.read_bytes()), compile_sha256=sha(compile_log.read_bytes()),
                              physical_device_tested=False, gpu_executed=False, llvm_ir_builder_simulated=True)
                report = OUT / (key + '-result.json')
                save(report, record)
                proof['tests'][key] = dict(passed=True, report_sha256=sha(report.read_bytes()),
                                          program=cpp.name, program_sha256=record['program_sha256'])
                save(PROOF, proof)
        # The complete affected host Store suite, using Apple's compression API.
        for mode in ('plain', 'asan-ubsan'):
            key = 'store-full-' + mode
            flags = ['-std=c++20', '-pthread', '-UNDEBUG', '-Wall', '-Wextra', '-Wno-misleading-indentation',
                     '-isysroot', os.environ['HOST_MACOS_SDK'], '-O1' if mode != 'plain' else '-O2']
            if mode != 'plain':
                flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-sanitize-recover=all']
            exe = work / key
            run_checked([*compiler, *flags, '-DNEOSWAP_STORAGE_TESTING', '-Inative/neoswap-storage',
                         'native/neoswap-storage/Store.cpp', 'native/neoswap-storage/tests/store_test.cpp',
                         '-lcompression', '-lz', '-o', exe], OUT / (key + '-compile.txt'), env)
            raw = run_checked([exe, work / (key + '-cache')], OUT / (key + '-output.txt'), env)
            assert raw.startswith(b'PASS: real POSIX file round trips')
            proof['tests'][key] = dict(passed=True, output_sha256=sha(raw), flags=flags)
            save(PROOF, proof)
    assert current == inputs()
    proof['all_tests_passed'] = True
    save(PROOF, proof)
    print('PASS: 31 Apple modes, 25 authenticated unchanged modes reused, 6 executed; no device/FPS claim', flush=True)


def verify(path, source):
    proof = load(path)
    manifest, exports = source_contract(source)
    assert proof['schema'] == 1 and proof['all_tests_passed'] is True
    assert proof['source'] == command('git', 'rev-parse', 'HEAD').decode().strip()
    assert proof['source_patch_sha256'] == PATCH_SHA
    assert proof['input_sha256'] == inputs() and proof['native_source_sha256'] == manifest['files_sha256']
    assert proof['exported_symbols'] == exports and proof['physical_device_tested'] is False
    assert proof['host']['system'] == 'Darwin' and proof['host']['machine'] == 'arm64'
    assert re.search(r'clang version 22\.', proof['host']['compiler'])
    assert set(proof['tests']) == EXPECTED_KEYS and len(EXPECTED_KEYS) == 31
    assert sha((OUT / 'deep-source-contract.json').read_bytes()) == proof['source_contract_sha256']
    assert proof['codegen'] == load(ROOT / (EVIDENCE + 'gow3-source-and-proof-record.json'))['codegenIdentity']['after']
    reused = {key for key, state in proof['tests'].items() if 'reused_from' in state}
    if proof.get('partial_reuse'):
        import rpcs3deep_resume3 as resume
        previous = resume.authenticate(sys.modules[__name__], proof)
        assert proof['partial_reuse'] == resume.ORIGIN and reused == resume.MODES
        for key in reused:
            expected = resume.retained_state(previous['tests'][key])
            assert proof['tests'][key] == expected
    else:
        assert not reused
    for key, state in proof['tests'].items():
        assert state['passed'] is True
        if key.startswith('store-full-'):
            assert sha((OUT / (key + '-output.txt')).read_bytes()) == state['output_sha256']
        else:
            assert sha((OUT / state['program']).read_bytes()) == state['program_sha256']
            raw = (OUT / (key + '-result.json')).read_bytes()
            assert sha(raw) == state['report_sha256']
            report = json.loads(raw)
            assert report['passed'] and '-UNDEBUG' in report['flags']
            name = key.rsplit('-', 2)[0] if key.endswith('-asan-ubsan') else key[:-len('-plain')]
            validate_native_result(name, report['results'], load(ROOT / report['evidence'])['results'])
            assert report['program_sha256'] == state['program_sha256']
            assert report['compiler'] == proof['host']['compiler']
            canonical_sha = load(ROOT / report['evidence'])['harnessSHA256']
            assert report['canonical_program_sha256'] == canonical_sha
            assert report['apple_host_adapter'] is (name in ('mfc-restore', 'shader', 'barriers', 'arena'))
            if name in ('mfc-restore', 'shader', 'barriers', 'arena'):
                canonical_path = OUT / (name + '-canonical.cpp')
                canonical_bytes = canonical_path.read_bytes()
                assert sha(canonical_bytes) == canonical_sha
                adapted = apple_host_program(name, canonical_bytes.decode())
                assert adapted.encode() == (OUT / state['program']).read_bytes()
            else:
                assert report['program_sha256'] == canonical_sha
            assert ('-fsanitize=address,undefined' in report['flags']) == key.endswith('-asan-ubsan')
            assert not any(f.startswith('-DNDEBUG') for f in report['flags'])
            assert sha((OUT / (key + '-output.txt')).read_bytes()) == report['output_sha256']
            assert sha((OUT / (key + '-compile.txt')).read_bytes()) == report['compile_sha256']
    print('PASS: current Apple preflight bound to exact source and build inputs', flush=True)
    return proof


def identity(directory):
    proof = verify(PROOF, Path(load(PROOF)['source_root']))
    sys.path.insert(0, str(ROOT / 'packages/dolphin_internal_bridge/ci'))
    from verify_ipa import macho
    import neo_swap_core_pin_test as pin
    data = (directory / 'libRPCS3Core.dylib').read_bytes()
    image = macho(data)
    assert image['platform'] == 2 and set(image['definedSymbols']) == set(proof['exported_symbols'])
    log = (OUT / 'build.log').read_text()
    for kind, expected in proof['codegen'].items():
        assert re.findall('NeoStation ' + kind + r' codegen identity: ([0-9a-f]{16})', log) == [expected]
    for hook in ('MoltenVK compile QoS hook linked', 'MoltenVK encoding-queue hook linked'):
        assert hook in log
    manifest = load(ROOT / MANIFEST)
    archive = manifest['cell587']['moltenvk_archive']
    assert archive['input_sha256'] + ' -> ' + archive['patched_sha256'] in log
    assert not {'_rbx_mvk_compile_qos_queue', '_rbx_mvk_exec_q_create'} & set(
        command('nm', '-u', directory / 'libRPCS3Core.dylib').decode().split())
    assert command('lipo', '-archs', directory / 'libRPCS3Core.dylib').decode().strip() == 'arm64'
    assert (directory / 'RPCS3_SOURCE_COMMIT.txt').read_text().strip() == manifest['upstream_commit']
    assert (directory / 'RPCS3_IOS_ABI.txt').read_text().strip() == '30'
    record = dict(schema_version=1, type='rpcs3-ios-deep-audit-source-candidate',
                  host_commit=proof['source'], native_source_commit=SOURCE,
                  source_commit=manifest['upstream_commit'], sha256=sha(data), abi_version=30,
                  architectures=['arm64'], source_patch_sha256=PATCH_SHA,
                  core_input_sha256=pin.core_input_hashes(), deep_audit_input_sha256=proof['input_sha256'],
                  native_source_sha256=manifest['files_sha256'], exported_symbols=proof['exported_symbols'],
                  codegen=proof['codegen'], physical_device_tested=False, gameplay_measured=False, public_release=False)
    save(directory / 'identity.json', record)
    save(OUT / 'identity.json', record)
    shutil.copyfile(PROOF, directory / PROOF.name)
    print('PASS: actual iPhone ARM64 Core, ABI30, 88 exports, expected changed SPU identity', flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path)
    p.add_argument('--verify-reuse', type=Path)
    p.add_argument('--write-core-identity', type=Path)
    a = p.parse_args()
    if a.write_core_identity:
        identity(a.write_core_identity)
    elif a.verify_reuse and a.source:
        verify(a.verify_reuse, a.source.resolve())
    elif a.source:
        prepare(a.source.resolve())
    else:
        p.error('--source or --write-core-identity is required')

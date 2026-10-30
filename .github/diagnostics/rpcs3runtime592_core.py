"""Core592: authenticate delivered Core591 once, test only the seven-file runtime delta.

Historical receipts stay historical. Native tests execute on ARM64 macOS before
one actual iPhone Core build. No device gameplay or FPS gain is inferred.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'test'))
import neo_swap_core_pin_test as pin
import rpcs3_hotpaths_test as hot
import rpcs3_clock_scale_test as clock

OUT = ROOT / 'build/rpcs3-core-diagnostics'
SOURCE = '9938d918f73e6284697e50706aa8e36bba92e249'
PRIOR_SOURCE = '12dd45b2125485614d232dd05675ceebaa6c0a1e'
PRIOR_RUN = 40782533853
PRIOR_ARTIFACT = 12858556547
PRIOR_BYTES = 208765
PRIOR_SHA = '11e4b2146ec04489877b3f701bce257500775fcedfcfda92c7588d16c062b1dd'
PRIOR_CORE_SHA = '08903af6e8f2ff5ddf267c27fa3128df35d737037ec9fa359be024d5302d28f1'
PRIOR_IDENTITY_SHA = 'c7f24cf9d35f27dca77e99096b9221d26436d0dded74c2a8dba6727f5b0c20c3'
PRIOR_PROOF_SHA = 'ebe7465aa9d5b76f7ed1580d8b1f2b5a3cec184c04c3b09d80de7a9c429494c9'
TESTS = [('hotpaths', 'test/rpcs3_hotpaths_test.py'),
         ('clock', 'test/rpcs3_clock_scale_test.py'),
         ('descriptors', 'test/rpcs3_descriptor_reserve_test.py')]
FIXED = {'.github/diagnostics/rpcs3runtime592_core.py',
         '.github/workflows/rpcs3-runtime592-core.yml',
         'test/rpcs3_memory523_test.py', 'test/rpcs3_cell559_test.py',
         'test/rpcs3_cell538_test.py', 'test/fixtures/rpcs3_cell538.diff',
         'packages/dolphin_internal_bridge/ci/verify_ipa.py',
         'test/fixtures/rpcs3_hotpaths_20261029.diff'}
REVIEWED = set(hot.PATHS) | {clock.SOURCE,
    'rpcs3/Emu/RSX/VK/vkutils/descriptors.cpp', 'rpcs3/Emu/RSX/VK/vkutils/descriptors.h'}
RECIPE_DELTA = {'build-utils/build_rpcs3_embedded_core.sh',
    'test/neo_swap_core_pin_test.py', '.github/workflows/rpcs3-core.yml',
    'build-utils/rpcs3/canonical-source.json', 'build-utils/rpcs3/embedded-core.patch'}
MARKERS = (
    b"Automatic enables it for God of War III, Call of Duty: Black Ops II, Bladestorm and Assassin's Creed;",
    b'COREPROF OPT587', b'canary=%s confirmed=%u exec_queues=%u',
    b'MoltenVK asynchronous submits: encoding queue recorded; acquisitions wait for the last queued present',
    b'rewindbox-mvk-async-587.txt', b'MoltenVK asynchronous submits enabled for this boot',
    b'MoltenVK asynchronous submits stay off for %s: its last asynchronous boot did not finish (crash or forced exit)',
)


def command(*args):
    return subprocess.check_output(args, cwd=ROOT)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def at(commit, path):
    return command('git', 'show', commit + ':' + path)


def manifest():
    return json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())


def inputs():
    paths = set(pin.CORE_INPUTS) | FIXED
    for key in ('runtime_20261029', 'runtime_followup_20261029'):
        paths.update(manifest()[key]['tests'])
    for root in ('native/neoswap-storage', 'packages/libretro_internal_bridge/ios/ThirdParty/include/vulkan'):
        paths.update(command('git', 'ls-files', '--', root).decode().splitlines())
    return {path: sha((ROOT / path).read_bytes()) for path in sorted(paths)}


def source_contract(source=None):
    # These immutable blobs bind native source provenance to 9938, separately
    # from the recipe commit that actually runs CI and becomes host_commit.
    command('git', 'merge-base', '--is-ancestor', SOURCE, 'HEAD')
    for path in ('build-utils/rpcs3/canonical-source.json', 'build-utils/rpcs3/embedded-core.patch'):
        assert (ROOT / path).read_bytes() == at(SOURCE, path), path
    before, after = json.loads(at(PRIOR_SOURCE, 'build-utils/rpcs3/canonical-source.json')), manifest()
    assert len(after['files_sha256']) == 308
    assert sha((ROOT / 'build-utils/rpcs3/embedded-core.patch').read_bytes()) == after['patch_sha256']
    assert after['upstream_commit'] == before['upstream_commit'] == pin.UPSTREAM
    changed = {p for p, h in before['files_sha256'].items() if after['files_sha256'].get(p) != h}
    added = set(after['files_sha256']) - set(before['files_sha256'])
    assert changed == set(hot.PATHS) and changed | added == REVIEWED
    expected = dict(before, files_sha256=after['files_sha256'], patch_sha256=after['patch_sha256'],
                    runtime_20261029=after['runtime_20261029'],
                    runtime_followup_20261029=after['runtime_followup_20261029'])
    assert after == expected, 'Unrelated canonical metadata changed'
    assert after['runtime_20261029']['codegen'] == after['runtime_followup_20261029']['codegen'] == before['cell591']['codegen']
    current_tests = set(after['runtime_20261029']['tests']) | set(after['runtime_followup_20261029']['tests'])
    current_tests.add(after['runtime_20261029']['fixture'])
    for path in current_tests:
        assert (ROOT / path).read_bytes() == at(SOURCE, path), path
    for path in set(pin.CORE_INPUTS) - RECIPE_DELTA:
        assert (ROOT / path).read_bytes() == at(PRIOR_SOURCE, path), path
    scheduling = (ROOT / '.github/workflows/rpcs3-core.yml').read_text()
    assert "!contains(github.event.head_commit.message, '[rpcs3-runtime592-core]')" in scheduling
    assert 'RPCS3_RUNTIME592_NATIVE_PROOF' in (ROOT / 'build-utils/build_rpcs3_embedded_core.sh').read_text()
    if source:
        assert command('git', '-C', str(source), 'rev-parse', 'HEAD').decode().strip() == after['upstream_commit']
        hot.manifest_contract(source)
        for path, digest in after['files_sha256'].items():
            assert sha((source / path).read_bytes().replace(b'\r\n', b'\n')) == digest, path
        from rpcs3_cell538_test import cache_identities
        assert cache_identities(source) == before['cell591']['codegen']
    return inputs()


def reference():
    def api(path):
        return json.loads(command('gh', 'api', 'repos/TarbleFR/RewindBox/' + path))
    state = api(f'actions/runs/{PRIOR_RUN}')
    artifact = api(f'actions/artifacts/{PRIOR_ARTIFACT}')
    assert state['head_sha'] == PRIOR_SOURCE and state['path'] == '.github/workflows/rpcs3-cell591-core.yml'
    assert state['status'] == 'completed' and state['conclusion'] == 'success'
    assert artifact['workflow_run']['id'] == PRIOR_RUN and not artifact['expired']
    assert artifact['size_in_bytes'] == PRIOR_BYTES and artifact['digest'] == 'sha256:' + PRIOR_SHA
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / 'reference591.zip'
        with archive.open('wb') as handle:
            subprocess.run(['gh', 'api', f'repos/TarbleFR/RewindBox/actions/artifacts/{PRIOR_ARTIFACT}/zip'],
                           stdout=handle, check=True, timeout=240, cwd=ROOT)
        assert archive.stat().st_size == PRIOR_BYTES and sha(archive.read_bytes()) == PRIOR_SHA
        with zipfile.ZipFile(archive) as z:
            # Authenticate this one delivered Core's receipt, not older results.
            identity_bytes, proof_bytes = z.read('identity.json'), z.read('cell591-proof.json')
            assert sha(identity_bytes) == PRIOR_IDENTITY_SHA and sha(proof_bytes) == PRIOR_PROOF_SHA
            identity, proof = json.loads(identity_bytes), json.loads(proof_bytes)
            baseline = json.loads(at(PRIOR_SOURCE, 'build-utils/rpcs3/canonical-source.json'))
            assert identity['host_commit'] == proof['source'] == PRIOR_SOURCE
            assert identity['sha256'] == PRIOR_CORE_SHA and identity['abi_version'] == 30
            assert identity['source_patch_sha256'] == baseline['patch_sha256']
            assert identity['native_source_sha256'] == proof['native_source_sha256'] == baseline['files_sha256']
            assert identity['cell591_input_sha256'] == proof['input_sha256']
            assert proof['all_tests_passed'] is True and proof['physical_device_tested'] is False
            (OUT / 'reference591-identity.json').write_bytes(identity_bytes)
    metadata = dict(run=state, artifact=artifact)
    (OUT / 'reference591-metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    return dict(source=PRIOR_SOURCE, run=PRIOR_RUN, artifact=PRIOR_ARTIFACT,
                archiveSHA256=PRIOR_SHA, coreSHA256=PRIOR_CORE_SHA,
                historicalResults=True, historicalTestsReplayed=False, coreBinaryReused=False)


def clock_paths(assembly):
    """The pinned A18 walker, allowing only a flag-preserving scheduled MRS.

    LLVM22's armv8.4 iOS target can move the counter read between CMP and
    B.NE. Keep the actual instruction list/count and reject every other gap.
    No historical test or its accepted control flow is changed.
    """
    result = {}
    for helper in ['get_timebased_time', 'get_system_time']:
        paths = {}
        for namespace in ['before', 'after']:
            symbol = f'__ZN{len(namespace)}{namespace}{len(helper)}{helper}Ev'
            start = assembly.index(symbol + ':')
            body = assembly[start:assembly.index('\t.cfi_endproc', start)]
            instructions, labels = [], {}
            for line in body.splitlines():
                line = line.split(';', 1)[0].strip()
                if line.endswith(':'):
                    labels[line[:-1]] = len(instructions)
                elif line and not line.startswith('.'):
                    instructions.append(line)
            zero = next(i for i, line in enumerate(instructions) if line.startswith('cbz\t'))
            frequency_register = instructions[zero].split()[1].rstrip(',')
            compare, branch = None, None
            if namespace == 'after':
                compare = next(i for i, line in enumerate(instructions)
                               if line.startswith('cmp\t' + frequency_register + ','))
                branch = compare + 1
                while instructions[branch].startswith('mrs\t'):
                    branch += 1
                assert instructions[branch].startswith('b.ne\t'), 'frequency test must retain a branch'
                constant_register = instructions[compare].split(',')[1].strip()
                constants = {}
                for line in instructions[:compare]:
                    match = re.fullmatch(r'(mov|movk)\s+([xw]\d+), #(\d+)(?:, lsl #(\d+))?', line)
                    if not match:
                        continue
                    op, register, value, shift = match.groups()
                    key, value, shift = 'x' + register[1:], int(value), int(shift or 0)
                    constants[key] = value if op == 'mov' else ((constants[key] & ~(65535 << shift)) | (value << shift))
                assert constants[constant_register] == 1_000_000_000
                blocks = re.findall(r'; InlineAsm Start\n(.*?); InlineAsm End', body, re.S)
                assert len(blocks) == 2 and not blocks[1].strip(), 'branch-retention asm must emit nothing'
            for frequency in [1_000_000_000, 24_000_000]:
                pc, visited = 0, []
                for _ in range(len(instructions) * 2):
                    assert pc not in visited, 'unexpected loop on nonzero counter path'
                    visited.append(pc)
                    instruction = instructions[pc]
                    op = instruction.split()[0]
                    if op == 'ret':
                        break
                    if pc == zero:
                        pc += 1  # Both tested frequencies are nonzero.
                    elif pc == branch:
                        pc = pc + 1 if frequency == 1_000_000_000 else labels[instruction.split()[1]]
                    elif op == 'b':
                        pc = labels[instruction.split()[1]]
                    else:
                        assert op not in ['cbz', 'cbnz', 'tbz', 'tbnz'] and not op.startswith('b.'), instruction
                        assert op not in ['bl', 'blr', 'br', 'brk', 'dmb', 'dsb', 'isb'], instruction
                        pc += 1
                else:
                    raise AssertionError('nonzero counter path did not return')
                count = sum(instructions[i].startswith('udiv\t') for i in visited)
                expected = 0 if namespace == 'after' and frequency == 1_000_000_000 else 2
                assert count == expected, (namespace, helper, frequency, count)
                paths[f'{namespace}_{frequency}Hz'] = {'dynamicUDIV': count, 'instructionsToReturn': len(visited)}
        result[helper] = paths
    return result


def clock_assembly(source):
    llvm = Path(os.environ['LLVM_CONFIG']).resolve().parent
    version = command(str(llvm / 'llvm-config'), '--version').decode().strip()
    assert version.split('.')[0] == '22', version
    before = subprocess.check_output(['git', 'show', pin.UPSTREAM + ':' + clock.SOURCE], cwd=source).decode()
    cpp = OUT / 'runtime592-clock-result.cpp'
    cpp.write_text(clock.arm_code(before, (source / clock.SOURCE).read_text()))
    assembly = OUT / 'runtime592-clock-result.s'
    # ConfigureCompiler.cmake selects this baseline for the packaged Core.
    # A device-specific A18 tune is not the production native compiler target.
    flags = ['-std=c++20', '-target', 'arm64-apple-ios16.3', '-march=armv8.4-a', '-O3', '-g0', '-DRPCS3_IOS', '-S']
    subprocess.run([str(llvm / 'clang++'), *flags, str(cpp), '-o', str(assembly)], cwd=ROOT, check=True, timeout=90)
    return dict(compiler=command(str(llvm / 'clang++'), '--version').decode().splitlines()[0],
                llvmVersion=version, flags=flags, paths=clock_paths(assembly.read_text()),
                inputSHA256=sha(cpp.read_bytes()), assemblySHA256=sha(assembly.read_bytes()),
                physicalDeviceTested=False, linkedCoreCode=False)


def prepare(source):
    assert platform.system() == 'Darwin' and platform.machine() == 'arm64', 'Core592 native preflight requires Apple ARM64'
    OUT.mkdir(parents=True, exist_ok=True)
    current = source_contract(source)
    receipt = dict(source=command('git', 'rev-parse', 'HEAD').decode().strip(), native_source_commit=SOURCE,
                   input_sha256=current, native_source_sha256=manifest()['files_sha256'],
                   exported_symbols=sorted((source / 'rpcs3/ios/RPCS3IOS.exports').read_text().split()),
                   physical_device_tested=False, gameplay_measured=False, all_tests_passed=False,
                   historical=reference(), tests={})
    for name, script in TESTS:
        for mode, args in [('plain', []), ('asan-ubsan', ['--sanitize'])]:
            key = name + '-' + mode
            report = OUT / (key + '-result.json')
            report.unlink(missing_ok=True)
            argv = ['python3', script, str(source), *args, '--report', str(report)]
            proc = subprocess.run(argv, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300,
                                  env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1'))
            (OUT / (key + '-output.txt')).write_bytes(proc.stdout)
            print(proc.stdout.decode(errors='replace'), flush=True)
            state = dict(command=argv, returncode=proc.returncode, output_sha256=sha(proc.stdout))
            if report.exists():
                payload = json.loads(report.read_bytes())
                state.update(report_sha256=sha(report.read_bytes()), passed=payload.get('passed') is True)
                flags = payload.get('hostFlags', payload.get('compilerFlags', []))
                # hotpaths hardcodes -UNDEBUG and binds the test script in inputs.
                assert '-UNDEBUG' in flags or (name == 'hotpaths' and "'-UNDEBUG'" in (ROOT / script).read_text())
            receipt['tests'][key] = state
            (OUT / 'runtime592-proof.json').write_text(json.dumps(receipt, indent=2) + '\n')
            assert proc.returncode == 0 and state.get('passed'), key
    receipt['clockAssembly'] = clock_assembly(source)
    assert current == inputs(), 'Tracked build/test inputs changed during preflight'
    receipt['all_tests_passed'] = True
    (OUT / 'runtime592-proof.json').write_text(json.dumps(receipt, indent=2) + '\n')


def verify(path, source=None):
    proof = json.loads(path.read_bytes())
    assert proof['source'] == command('git', 'rev-parse', 'HEAD').decode().strip()
    assert proof['native_source_commit'] == SOURCE and proof['input_sha256'] == source_contract(source)
    assert proof['native_source_sha256'] == manifest()['files_sha256']
    assert proof['all_tests_passed'] is True and proof['physical_device_tested'] is False
    assert sha((OUT / 'reference591-identity.json').read_bytes()) == PRIOR_IDENTITY_SHA
    assert set(proof['tests']) == {name + '-' + mode for name, _ in TESTS for mode in ('plain', 'asan-ubsan')}
    for name, state in proof['tests'].items():
        assert state['passed'] is True and state['returncode'] == 0
        assert sha((OUT / (name + '-result.json')).read_bytes()) == state['report_sha256']
        assert sha((OUT / (name + '-output.txt')).read_bytes()) == state['output_sha256']
    assert sha((OUT / 'runtime592-clock-result.cpp').read_bytes()) == proof['clockAssembly']['inputSHA256']
    assert sha((OUT / 'runtime592-clock-result.s').read_bytes()) == proof['clockAssembly']['assemblySHA256']
    assert clock_paths((OUT / 'runtime592-clock-result.s').read_text()) == proof['clockAssembly']['paths']
    return proof


def identity(directory):
    proof = verify(OUT / 'runtime592-proof.json')
    sys.path.insert(0, str(ROOT / 'packages/dolphin_internal_bridge/ci'))
    from verify_ipa import macho
    data = (directory / 'libRPCS3Core.dylib').read_bytes()
    image = macho(data)
    assert image['platform'] == 2 and len(image['definedSymbols']) == 88
    expected_exports = set(proof['exported_symbols'])
    assert set(image['definedSymbols']) == expected_exports
    for marker in MARKERS:
        assert marker in data, marker
    log = (OUT / 'build.log').read_text()
    actual = {kind: re.findall(r'NeoStation ' + kind + r' codegen identity: ([0-9a-f]{16})', log) for kind in ('PPU', 'SPU')}
    assert actual == {kind: [value] for kind, value in manifest()['cell591']['codegen'].items()}, actual
    for hook in ('MoltenVK compile QoS hook linked', 'MoltenVK encoding-queue hook linked'):
        assert hook in log, hook
    archive = manifest()['cell587']['moltenvk_archive']
    assert archive['input_sha256'] + ' -> ' + archive['patched_sha256'] in log
    undefined = command('nm', '-u', str(directory / 'libRPCS3Core.dylib')).decode().split()
    assert not {'_rbx_mvk_compile_qos_queue', '_rbx_mvk_exec_q_create'} & set(undefined)
    item = json.loads((OUT / 'reference591-identity.json').read_bytes())
    for key in list(item):
        if key.startswith('cell') and key.endswith('_input_sha256'):
            del item[key]
    item.update(host_commit=proof['source'], native_source_commit=SOURCE, sha256=sha(data),
                source_patch_sha256=manifest()['patch_sha256'], core_input_sha256=pin.core_input_hashes(),
                runtime592_input_sha256=inputs(), native_source_sha256=manifest()['files_sha256'])
    assert item['source_commit'] == (directory / 'RPCS3_SOURCE_COMMIT.txt').read_text().strip() == manifest()['upstream_commit']
    assert item['abi_version'] == int((directory / 'RPCS3_IOS_ABI.txt').read_text().strip()) == 30
    for target in (directory, OUT):
        (target / 'identity.json').write_text(json.dumps(item, indent=2) + '\n')
    codegen = dict(actual=actual, unchangedFrom591=True, coldCompileRequiredByThisChange=False, physicalDeviceTested=False)
    (OUT / 'codegen-identities.json').write_text(json.dumps(codegen, indent=2) + '\n')
    print('PASS actual iPhone Core592: source9938, six targeted ARM64 checks, LLVM22 clock paths, 88 exact exports, passive loading and unchanged codegen identities')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path)
    p.add_argument('--verify-reuse', type=Path)
    p.add_argument('--write-core-identity', type=Path)
    a = p.parse_args()
    if 'continuation_20261030' in manifest():
        # Keep the established workflow and compiler recipe unchanged.
        import rpcs3continuation_core as continuation
        if a.write_core_identity:
            continuation.identity(a.write_core_identity)
        elif a.source and a.verify_reuse:
            continuation.verify(a.verify_reuse, a.source.resolve())
        elif a.source:
            continuation.prepare(a.source.resolve())
        else:
            p.error('continuation source requires --source or --write-core-identity')
        raise SystemExit
    if 'deep_audit_20261029' in manifest():
        # The original runtime592 workflow remains byte-for-byte unchanged.
        # Only the candidate validation is routed to its changed SPU/RSX
        # source contract; do not reuse old LLVM/SPU codegen identities.
        import shutil
        import rpcs3deep_core as deep
        if a.write_core_identity:
            deep.identity(a.write_core_identity)
        elif a.source and a.verify_reuse:
            deep.verify(a.verify_reuse, a.source.resolve())
        elif a.source:
            deep.prepare(a.source.resolve())
            # Preserve the original workflow's artifact/verify-reuse path.
            shutil.copyfile(deep.PROOF, OUT / 'runtime592-proof.json')
        else:
            p.error('deep-audit source requires --source or --write-core-identity')
        raise SystemExit
    if 'runtime_refinement_20261029' in manifest():
        from rpcs3runtime_refinement_core import main as refinement_main
        refinement_main(a)
        raise SystemExit
    if 'runtime_global_20261029' in manifest():
        from rpcs3runtime_global_core import main as global_main
        global_main(a)
        raise SystemExit
    if 'runtime_device594_followup_20261029' in manifest():
        from rpcs3runtime_device594_core import main as device594_main
        device594_main(a)
        raise SystemExit
    if 'runtime_bo2_exact_20261029' in manifest():
        from rpcs3runtime_bo2_exact_core import main as exact_main
        exact_main(a)
        raise SystemExit
    if 'runtime_bo2_warm_20261029' in manifest():
        from rpcs3runtime_bo2_warm_core import main as warm_main
        warm_main(a)
        raise SystemExit
    if 'runtime_bo2_followup_20261029' in manifest():
        from rpcs3runtime_bo2_core import main as bo2_main
        bo2_main(a)
        raise SystemExit
    if 'runtime_device593_followup_20261029' in manifest():
        from rpcs3runtime_device593_core import main as device593_main
        device593_main(a)
        raise SystemExit
    if 'runtime_log_followup_20261029' in manifest():
        from rpcs3runtime_log_followup_core import main as followup_main
        followup_main(a)
        raise SystemExit
    if a.write_core_identity:
        identity(a.write_core_identity)
    elif a.verify_reuse:
        verify(a.verify_reuse, a.source)
    elif a.source:
        prepare(a.source)
    else:
        source_contract()
        print('PASS592 source contract; no binary or device claim')

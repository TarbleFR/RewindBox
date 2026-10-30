#!/usr/bin/env python3
"""Validate the device597 source lot through the unchanged runtime592 recipe.

Every explicitly required new Apple job executes in this preflight. Reuse is
limited to its immediate build with the same commit, canonical source and full
repository-input closure. Older Apple modes retain their original provenance;
they are never relabeled as executions or validation of new production paths.
"""
import argparse
import hashlib
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
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/rpcs3-core-diagnostics'
PROOF = OUT / 'runtime592-proof.json'
KEY = 'device597_20261030'
GATE = '.github/diagnostics/rpcs3runtime_device597_core.py'
ROUTE = '.github/diagnostics/rpcs3runtime592_core.py'
WORKFLOW = '.github/workflows/rpcs3-runtime592-core.yml'
BUILD = 'build-utils/build_rpcs3_embedded_core.sh'
MANIFEST = 'build-utils/rpcs3/canonical-source.json'
PATCH = 'build-utils/rpcs3/embedded-core.patch'
DELTA = 'test/rpcs3_device597/core-delta.patch'
CONTRACT = 'test/rpcs3_device597_contract_test.py'
CONTRACT_RECORD = 'docs/evidence/rpcs3-device597-20261030/contract.json'
CODEGEN_REPORT = 'docs/evidence/rpcs3-device597-20261030/cpu/codegen-review-final.json'
CODEGEN_RUNNER = 'test/rpcs3_device597/cpu/audit_codegen.py'
HOST_RUNNER = 'test/rpcs3_causes_history_test.py'
HOST_LOGGER = 'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3Diagnostics.mm'
HOST_FIXTURE = 'test/native/rpcs3_causes_history_test.mm'
BASE = '293f7feba68eddb0dc7f4a5ec3940b209cc5de35'
HIST = '88cdc5e3e115a0b8587711d77147467baf38128b'
HIST_RUN = 40981514937
HIST_PATCH = '099651cae54c7bc567ff325735acde0cf3e931ed6e25b2b5bbcc14e5f5ecf33b'
HIST_CORE = 'cc7362544f922aebdc021b5dbe6ca68d9c0bfb15d79145606f71af584509edd1'
HIST_IDENTITY = '9f1b45a28fe4701bd9c1f62fa5a4a76f8c0f85dcaed7328c095c52214a817617'
HIST_PROOF = 'b74d89b8befc2f207d3d6db883738412889827a0379a4d7a5dd159d7dc98beaa'
HIST_RECEIPT = 'docs/evidence/rpcs3-continuation-20261030/apple-core.json'
HIST_RECEIPT_SHA = '4941b9e69de2684cb4ab3364179b31828826994e004d2b7f37a5030b54e1af28'
WORKFLOW_SHA = '7d6cd1d74e7503a406719932b8fddf13dd79ed0d67d775e1d49cafcc43ff036e'
BUILD_SHA = 'ec79fb073908151d8413a201ef61d242078d363eb317395b6c98f01421eb9a5d'
ARCHIVES = {
    'core': (12946200694, 29139881, '18f76b5e28187cf28c46047ad8b4b13a631420412bb6efad2e9a5e5c19aae989'),
    'diagnostics': (12945842056, 89819506, 'd03aa40178c59b6ea16c10dbfe3f9793687e635b38279fc5498c8f119b878de4'),
}
HIST_TESTS = {name + '-' + mode for name in (
    'dma-list', 'vm-mmio', 'dma-mmio', 'pipeline', 'pressure', 'depth',
    'atlas', 'atlas-area', 'neoswap-trim', 'store-full') for mode in ('plain', 'asan-ubsan')}
HIST_TESTS.update(('gpu-wait-asan-ubsan', 'dma-ownership-asan-ubsan',
                   'pressure-baseline-plain', 'depth-baseline-plain'))
ROUTE_BLOCK = '''    if 'device597_20261030' in manifest():
        # The workflow and compiler recipe stay unchanged; only this new lot runs.
        import rpcs3runtime_device597_core as device597
        if a.write_core_identity:
            device597.identity(a.write_core_identity)
        elif a.source and a.verify_reuse:
            device597.verify(a.verify_reuse, a.source.resolve())
        elif a.source:
            device597.prepare(a.source.resolve())
        else:
            p.error('device597 source requires --source or --write-core-identity')
        raise SystemExit
'''

# This wrapper observes the runner's real compiler command. It does not add,
# remove or reorder flags and never participates in the actual Core build.
WRAPPER_SOURCE = r'''#!/usr/bin/env python3
import fcntl, hashlib, json, os
from pathlib import Path
import subprocess, sys
args = sys.argv[1:]
compiler = json.loads(os.environ['RPCS3_DEVICE597_REAL_CXX'])
snapshots = Path(os.environ['RPCS3_DEVICE597_COMPILE_INPUTS'])
units = []
for arg in args:
    p = Path(arg)
    if p.suffix in ('.c', '.cc', '.cpp', '.cxx', '.C', '.m', '.mm') and p.is_file():
        raw = p.read_bytes(); digest = hashlib.sha256(raw).hexdigest()
        snapshots.mkdir(parents=True, exist_ok=True)
        saved = snapshots / (digest + p.suffix)
        if not saved.exists(): saved.write_bytes(raw)
        units.append({'path': str(p.resolve()), 'sha256': digest, 'saved': str(saved)})
result = subprocess.run(compiler + args)
event = {'compiler': compiler, 'args': args, 'cwd': str(Path.cwd()),
         'returncode': result.returncode, 'units': units}
with open(os.environ['RPCS3_DEVICE597_CXX_TRACE'], 'a', encoding='utf-8') as trace:
    fcntl.flock(trace, fcntl.LOCK_EX)
    trace.write(json.dumps(event, sort_keys=True) + '\n')
    trace.flush()
    fcntl.flock(trace, fcntl.LOCK_UN)
raise SystemExit(result.returncode)
'''


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    return sha(Path(path).read_bytes())


def load(path):
    return json.loads(Path(path).read_bytes())


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def command(*args, cwd=None):
    return subprocess.check_output([str(a) for a in args], cwd=ROOT if cwd is None else cwd, timeout=300)


def at(commit, path):
    return command('git', 'show', commit + ':' + path)


def relative_file(root, name):
    p = Path(name)
    require(isinstance(name, str) and not p.is_absolute() and '..' not in p.parts,
            'Unsafe relative file: ' + str(name))
    result = root / p
    require(result.is_file() and not result.is_symlink(), 'Missing regular input: ' + str(result))
    require(result.resolve().is_relative_to(root.resolve()), 'Input escapes root: ' + str(result))
    return result


def selected_jobs(manifest):
    plan = manifest[KEY]['apple_validation']
    require(isinstance(plan, dict), 'Missing Apple validation plan')
    jobs = plan.get('jobs')
    require(isinstance(jobs, list) and jobs, 'The new Apple job list must not be empty')
    seen = set()
    native = 0
    foundation_modes = set()
    codegen_jobs = []
    for job in jobs:
        require(isinstance(job, dict), 'Invalid job')
        name = job.get('name')
        require(isinstance(name, str) and re.fullmatch(r'[a-z0-9][a-z0-9_-]*', name), 'Invalid job name')
        require(name not in seen, 'Duplicate job: ' + name)
        seen.add(name)
        require(job.get('kind', 'native') in ('native', 'source'), 'Invalid job kind: ' + name)
        is_native = job.get('kind', 'native') == 'native'
        require(job.get('mode') in (('plain', 'asan-ubsan', 'tsan') if is_native else (None, 'plain')),
                'Missing/invalid explicit native mode: ' + name)
        native += is_native
        argv = job.get('argv')
        require(isinstance(argv, list) and len(argv) > 1 and all(isinstance(a, str) for a in argv), 'Invalid argv: ' + name)
        require(argv[0] in ('python3', sys.executable), 'Expected a reviewed Python runner: ' + name)
        require((argv[1].startswith('{repo}/test/rpcs3_device597/') or argv[1] == '{repo}/' + HOST_RUNNER)
                and argv[1].endswith('.py') and '..' not in Path(argv[1]).parts,
                'Runner must belong to this new lot: ' + name)
        require(isinstance(job.get('report'), str) and job['report'].startswith('{output}/')
                and '..' not in Path(job['report']).parts, 'Explicit safe report path required')
        require(isinstance(job.get('checks'), list) and job['checks'], 'Explicit output checks required: ' + name)
        for check in job['checks']:
            require(set(check) == {'path', 'equals'} and isinstance(check['path'], list) and check['path'],
                    'Each check needs a JSON path and expected value: ' + name)
        require(1 <= job.get('timeout_seconds', 300) <= 900, 'Invalid job timeout')
        if job.get('requires_foundation'):
            require(is_native and argv[1] == '{repo}/' + HOST_RUNNER, 'Foundation requires the actual host logger runner')
            foundation_modes.add(job['mode'])
        if argv[1] == '{repo}/' + CODEGEN_RUNNER:
            require(not is_native, 'Codegen audit is a separate source job')
            codegen_jobs.append(job)
    require(native > 0, 'At least one new native Apple job is required')
    require({'plain', 'asan-ubsan'} <= foundation_modes, 'Both real Foundation modes are required')
    require(len(codegen_jobs) == 1, 'Exactly one current codegen source audit is required')
    return jobs


def expand(value, substitutions):
    for key, replacement in substitutions.items():
        value = value.replace('{' + key + '}', replacement)
    require(not re.search(r'\{[^{}]+\}', value), 'Unknown placeholder: ' + value)
    return value


def check_report(report, job):
    for check in job['checks']:
        value = report
        for key in check['path']:
            value = value[key]
        require(type(value) is type(check['equals']) and value == check['equals'],
                'Failed result check for ' + job['name'] + ': ' + repr(check['path']))
    if job.get('requires_foundation'):
        foundation = report['foundation']
        require(foundation['executed'] is True and foundation['buildReturnCode'] == 0
                and foundation['runReturnCode'] == 0, 'The actual Foundation fixture did not execute successfully')


def compile_flags(args, mode):
    require(not any(a.startswith('@') for a in args), 'Unexpanded compiler response file')
    defines = [a[2:] for a in args if a.startswith('-D') and a != '-D']
    defines += [args[i + 1] for i, a in enumerate(args[:-1]) if a == '-D']
    require(not any(v.split('=', 1)[0] == 'NDEBUG' for v in defines), 'Assertions disabled by NDEBUG')
    require('-UNDEBUG' in args or any(a == '-U' and args[i + 1] == 'NDEBUG' for i, a in enumerate(args[:-1])),
            'Native checks must explicitly retain assertions with -UNDEBUG')
    require(not any(a.startswith('-Wp,') for a in args), 'Indirect preprocessor flags need explicit review')
    sanitizers = set()
    for flag in args:
        if flag.startswith('-fsanitize='):
            sanitizers.update(flag.split('=', 1)[1].split(','))
    wanted = {'plain': set(), 'asan-ubsan': {'address', 'undefined'}, 'tsan': {'thread'}}[mode]
    require(sanitizers == wanted, 'Wrong sanitizer mode: ' + repr(sanitizers))
    require(not any(a.startswith('-fno-sanitize=') for a in args), 'A sanitizer is selectively disabled')
    for i, flag in enumerate(args):
        if flag == '-arch':
            require(i + 1 < len(args) and args[i + 1] == 'arm64', 'Wrong native architecture')
        if flag in ('-target', '--target') or flag.startswith(('--target=', '-target=')):
            require('=' in flag or i + 1 < len(args), 'Missing target triple')
            target = flag.split('=', 1)[1] if '=' in flag else args[i + 1]
            require(target.startswith(('arm64-apple-macos', 'arm64-apple-darwin', 'aarch64-apple-darwin')),
                    'The native regression target must be Apple ARM64 macOS')


def check_compile_trace(path, job, compiler):
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    compiled = 0
    foundation = 0
    for row in rows:
        require(row['compiler'] == compiler, 'Runner substituted another compiler')
        args = row['args']
        if not row['units']:
            # Query or link-only commands cannot satisfy the native compile gate.
            continue
        require(row['returncode'] == 0, 'A native compiler invocation failed')
        require(not any(a in args for a in ('-E', '-S', '-fsyntax-only')), 'Native job did not build executable code')
        compile_flags(args, job['mode'])
        for unit in row['units']:
            saved = Path(unit['saved'])
            require(saved.resolve().is_relative_to(OUT.resolve()) and saved.is_file(), 'Missing captured compile input')
            require(file_sha(saved) == unit['sha256'], 'Captured compile input changed')
        compiled += 1
        links_foundation = any(a == '-framework' and args[i + 1] == 'Foundation'
                               for i, a in enumerate(args[:-1]))
        unit_paths = {unit['path'] for unit in row['units']}
        if links_foundation and {str(ROOT / HOST_LOGGER), str(ROOT / HOST_FIXTURE)} <= unit_paths:
            foundation += 1
    require(compiled > 0, 'The runner never invoked the selected CXX compiler')
    require(not job.get('requires_foundation') or foundation > 0, 'Missing real Objective-C++ Foundation compilation')
    return compiled


def current_inputs(contract):
    recorded = contract['repository_inputs']
    require(isinstance(recorded, dict) and recorded, 'Missing repository-input closure')
    paths = set(recorded)
    paths.update((GATE, ROUTE, WORKFLOW, BUILD, MANIFEST, PATCH, DELTA, CONTRACT, CONTRACT_RECORD,
                  CODEGEN_REPORT, HIST_RECEIPT,
                  'test/neo_swap_core_pin_test.py', 'packages/dolphin_internal_bridge/ci/verify_ipa.py',
                  'build-utils/validate_rpcs3_embedded_core.py', 'build-utils/validate_rpcs3_passive_dlopen.py'))
    paths.update(command('git', 'ls-files', '--', 'test/rpcs3_device597').decode().splitlines())
    result = {name: file_sha(relative_file(ROOT, name)) for name in sorted(paths)}
    for name, digest in recorded.items():
        require(result[name] == digest, 'Contract input changed: ' + name)
    return result


def upstream_dependencies(source, manifest):
    """Bind every ordinary noncanonical source file to the pinned Git tree.

    This includes native harness support headers such as xxhash3.h, Thread.h,
    MFC.h and RSX types. Git submodules retain their pinned commit identities;
    their content is the responsibility of the unchanged dependency recipe.
    """
    entries = command('git', '-C', source, 'ls-tree', '-rz', 'HEAD').split(b'\0')
    ordinary, links, modules = {}, {}, {}
    canonical = set(manifest['files_sha256'])
    for entry in entries:
        if not entry:
            continue
        metadata, raw_name = entry.split(b'\t', 1)
        mode, kind, blob = metadata.decode().split()
        name = raw_name.decode()
        if kind == 'commit':
            modules[name] = blob
            continue
        require(kind == 'blob', 'Unexpected upstream tree object: ' + name)
        if name in canonical:
            continue
        path = source / name
        if mode == '120000':
            require(path.is_symlink(), 'Missing upstream symlink: ' + name)
            raw = os.fsencode(os.readlink(path))
            links[name] = raw.decode()
        else:
            raw = relative_file(source, name).read_bytes()
        git_hash = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        require(git_hash == blob, 'Noncanonical source differs from pinned upstream: ' + name)
        ordinary[name] = sha(raw)
    untracked = {p.decode() for p in command('git', '-C', source, 'ls-files', '--others', '-z').split(b'\0') if p}
    require(untracked <= canonical, 'Unreviewed source files outside canonical patch: ' + repr(sorted(untracked - canonical)))
    return dict(files_sha256=ordinary, symlinks=links, submodule_commits=modules,
                submodule_contents_authenticated=False)


def source_contract(source, report_path, baseline=None):
    manifest = load(ROOT / MANIFEST)
    require(KEY in manifest, 'This validator accepts only the device597 lot')
    jobs = selected_jobs(manifest)
    require(file_sha(ROOT / PATCH) == manifest['patch_sha256'], 'Canonical patch changed')
    old = json.loads(at(BASE, MANIFEST))
    require(old['patch_sha256'] == HIST_PATCH and len(old['files_sha256']) == 319, 'Wrong baseline597 manifest')
    require(json.loads(at(HIST, MANIFEST))['files_sha256'] == old['files_sha256'], 'Baseline differs from the compiled Core597')
    require(manifest['upstream_commit'] == old['upstream_commit'], 'Upstream changed outside this lot')
    require(command('git', '-C', source, 'rev-parse', 'HEAD').decode().strip() == manifest['upstream_commit'], 'Wrong upstream checkout')
    for name, digest in manifest['files_sha256'].items():
        require(sha(relative_file(source, name).read_bytes().replace(b'\r\n', b'\n')) == digest, 'Wrong canonical postimage: ' + name)
    for name, digest in ((WORKFLOW, WORKFLOW_SHA), (BUILD, BUILD_SHA)):
        require(file_sha(ROOT / name) == digest and (ROOT / name).read_bytes() == at(HIST, name), 'Historical recipe changed: ' + name)
    anchor = "    if 'continuation_20261030' in manifest():\n"
    old_route = at(BASE, ROUTE).decode()
    require(old_route.count(anchor) == 1 and (ROOT / ROUTE).read_text() == old_route.replace(anchor, ROUTE_BLOCK + anchor, 1),
            'Dispatcher changed beyond the new leading branch')
    argv = [sys.executable, ROOT / CONTRACT, source, '--repo', ROOT, '--report', report_path]
    if baseline is not None:
        argv += ['--baseline-out', baseline]
    run(argv, OUT / 'device597-source-contract-output.txt')
    contract = load(report_path)
    require(contract['passed'] is True, 'New source contract failed')
    require(contract['baseline_app_commit'] == BASE, 'Source contract used another baseline')
    require(contract['inverse_delta_verified'] is True and contract['counts']['baseline_postimages'] == 319,
            'Inverse delta did not authenticate the delivered597 baseline')
    require(contract['core_hashes']['baseline_lf_sha256'] == old['files_sha256'], 'Inverse delta did not authenticate all 319 baseline files')
    require(contract['core_hashes']['current_lf_sha256'] == manifest['files_sha256'], 'Source contract checked different postimages')
    require(contract['canonical_patch_sha256'] == manifest['patch_sha256'], 'Source contract checked a different patch')
    require(contract['delta_sha256'] == file_sha(ROOT / DELTA), 'Wrong inverse delta')
    require(contract['codegen_identities_computed'] is False, 'Source authentication cannot substitute for the codegen audit')
    inputs = current_inputs(contract)
    for job in jobs:
        runner = job['argv'][1].replace('{repo}/', '', 1)
        require(runner in inputs, 'Runner is absent from input closure')
    exports = sorted((source / 'rpcs3/ios/RPCS3IOS.exports').read_text().split())
    require(len(exports) == len(set(exports)) == 88, 'Unexpected ABI export surface')
    return manifest, contract, inputs, exports


def check_codegen(report, manifest):
    """Bind the separately executed source audit to this exact source lot."""
    frozen = load(ROOT / CODEGEN_REPORT)
    # Only source-root paths vary between the Linux source review and Apple
    # preflight. All input hashes, recipes, alias cases and limits must agree.
    def comparable(value):
        value = json.loads(json.dumps(value))
        for entry in value['inputs'].values():
            entry.pop('source', None)
        return value
    require(report['passed'] is True and comparable(report) == comparable(frozen),
            'Current codegen audit differs from its reviewed source-equivalence proof')
    require(report['unmodifiedInputsBorrowedFromBaseline'] == [], 'Codegen audit borrowed a missing candidate input')
    require(report['scriptSHA256'] == file_sha(ROOT / CODEGEN_RUNNER), 'Codegen audit script changed')
    require(report['inputEvidenceSHA256'] == file_sha(ROOT / 'docs/evidence/rpcs3-continuation-20261030/codegen-identity.json'),
            'Codegen baseline evidence changed')
    for field, path in (('candidateSourceSHA256', 'rpcs3/Emu/Cell/SPUThread.cpp'),
                        ('candidateCompatibilitySHA256', 'rpcs3/Emu/CPU/JITCacheCompatibility.cmake'),
                        ('traceHeaderSHA256', 'rpcs3/ios/IOSSignalTrace.h')):
        require(report[field] == manifest['files_sha256'][path], 'Codegen proof belongs to another source: ' + field)
    codegen = report['candidateWithExactAlias']
    require(set(codegen) == {'PPU', 'SPU'} and all(re.fullmatch(r'[0-9a-f]{16}', v) for v in codegen.values()),
            'Missing current PPU/SPU identity proof')
    require(codegen == report['baselineIdentities'], 'The exact alias did not preserve delivered597 identities')
    if 'codegen_identities' in manifest[KEY]:
        require(codegen == manifest[KEY]['codegen_identities'], 'Declared and reproduced codegen identities differ')
    return codegen


def run(argv, log, env=None, timeout=300):
    p = subprocess.run([str(x) for x in argv], cwd=ROOT, env=env, capture_output=True, timeout=timeout)
    Path(log).parent.mkdir(parents=True, exist_ok=True)
    Path(log).write_bytes(p.stdout + p.stderr)
    if p.returncode:
        print((p.stdout + p.stderr).decode(errors='replace'), flush=True)
        raise RuntimeError('Command failed: ' + repr([str(x) for x in argv]))
    return p.stdout


def historical_reference(download=False):
    """Authenticate old artifacts against their original Git objects, not HEAD."""
    require(file_sha(ROOT / HIST_RECEIPT) == HIST_RECEIPT_SHA, 'Historical receipt changed')
    directory = OUT / 'reference-597'
    directory.mkdir(parents=True, exist_ok=True)
    if download:
        raw = command('gh', 'api', f'repos/TarbleFR/RewindBox/actions/runs/{HIST_RUN}')
        (directory / 'run.json').write_bytes(raw)
    state = load(directory / 'run.json')
    require(state['id'] == HIST_RUN and state['head_sha'] == HIST and state['path'] == WORKFLOW and
            state['status'] == 'completed' and state['conclusion'] == 'success', 'Wrong historical Core run')
    archives = {}
    for name, (artifact, size, digest) in ARCHIVES.items():
        path = directory / (name + '.zip')
        if download:
            metadata = json.loads(command('gh', 'api', f'repos/TarbleFR/RewindBox/actions/artifacts/{artifact}'))
            require(metadata['workflow_run']['id'] == HIST_RUN and not metadata['expired'] and
                    metadata['size_in_bytes'] == size and metadata['digest'] == 'sha256:' + digest, 'Wrong historical artifact metadata')
            save(directory / (name + '-metadata.json'), metadata)
            if not path.exists():
                with path.open('wb') as output:
                    subprocess.run(['gh', 'api', f'repos/TarbleFR/RewindBox/actions/artifacts/{artifact}/zip'],
                                   cwd=ROOT, stdout=output, check=True, timeout=300)
        require(path.stat().st_size == size and file_sha(path) == digest, 'Historical archive bytes changed: ' + name)
        archives[name] = path
    baseline = json.loads(at(HIST, MANIFEST))
    with zipfile.ZipFile(archives['core']) as core, zipfile.ZipFile(archives['diagnostics']) as diagnostics:
        identity_raw = core.read('identity.json')
        proof_raw = core.read('runtime592-proof.json')
        require(sha(identity_raw) == HIST_IDENTITY and sha(proof_raw) == HIST_PROOF, 'Historical identity/proof changed')
        require(diagnostics.read('identity.json') == identity_raw and diagnostics.read('runtime592-proof.json') == proof_raw,
                'Core and diagnostics do not share their proof')
        require(sha(core.read('libRPCS3Core.dylib')) == HIST_CORE, 'Historical Core bytes changed')
        identity, proof = json.loads(identity_raw), json.loads(proof_raw)
        require(identity['host_commit'] == proof['source'] == HIST and identity['sha256'] == HIST_CORE, 'Historical source identity mismatch')
        require(proof['all_tests_passed'] is True and set(proof['tests']) == HIST_TESTS, 'Historical Apple modes changed')
        require(proof['native_source_sha256'] == identity['native_source_sha256'] == baseline['files_sha256'], 'Historical native source changed')
        require(proof['source_patch_sha256'] == identity['source_patch_sha256'] == HIST_PATCH, 'Historical patch changed')
        for path, digest in proof['input_sha256'].items():
            require(sha(at(HIST, path)) == digest, 'Historical repository input differs from its original commit: ' + path)
        modes = {}
        for name, item in proof['tests'].items():
            raw = diagnostics.read(name + '-result.json')
            require(item['passed'] is True and sha(raw) == item['report_sha256'], 'Historical native report changed: ' + name)
            report = json.loads(raw)
            require(report['passed'] is True, 'Unsuccessful historical report')
            require(sha(diagnostics.read(name + '-output.txt')) == report['output_sha256'], 'Historical native output changed')
            require(sha(diagnostics.read(name + '-compile.txt')) == report['compile_sha256'], 'Historical compile output changed')
            if 'program' in report:
                require(sha(diagnostics.read(report['program'])) == report['program_sha256'], 'Historical program changed')
            modes[name] = dict(origin=item.get('reused_from', {'source': HIST, 'run': HIST_RUN}),
                               original_proof_entry=item,
                               report_sha256=item['report_sha256'], native_executed_now=False,
                               current_source_validated=False)
        require(len([v for v in proof['tests'].values() if 'reused_from' in v]) == 16, 'Historical execution split changed')
        older = proof['historical']['reused_current_modes']
        require(len(older) == 11 and all(v['native_executed_now'] is False for v in older.values()), 'Older history scope changed')
    return dict(source=HIST, run=HIST_RUN, core_sha256=HIST_CORE, proof_sha256=HIST_PROOF,
                receipt_sha256=HIST_RECEIPT_SHA, archive_sha256={k: v[2] for k, v in ARCHIVES.items()},
                targeted_modes=modes, older_historical_modes=older,
                modes_executed_now=0, old_binary_reused=False, validates_new_paths=False)


def compiler_identity():
    require(platform.system() == 'Darwin' and platform.machine() == 'arm64', 'New native modes require Apple ARM64')
    compiler = shlex.split(os.environ['CXX'])
    require(len(compiler) == 1, 'Expected the workflow selected compiler, without a wrapper')
    resolved = shutil.which(compiler[0])
    require(resolved is not None, 'Selected CXX is missing')
    compiler = [str(Path(resolved).resolve())]
    version = command(*compiler, '--version').decode().splitlines()[0]
    require(re.search(r'clang version 22\.', version), 'Expected LLVM22: ' + version)
    return compiler, version


def prepare(source):
    compiler, version = compiler_identity()
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='device597-baseline-') as temporary:
        baseline = Path(temporary) / 'baseline'
        contract_path = OUT / 'device597-source-contract.json'
        manifest, contract, inputs, exports = source_contract(source, contract_path, baseline)
        dependencies = upstream_dependencies(source, manifest)
        jobs = selected_jobs(manifest)
        wrapper = OUT / 'device597-cxx-wrapper.py'
        wrapper.write_text(WRAPPER_SOURCE)
        wrapper.chmod(0o755)
        proof = dict(schema=1, type='rpcs3-device597-20261030',
                     source=command('git', 'rev-parse', 'HEAD').decode().strip(),
                     source_root=str(source), baseline_root=str(baseline),
                     source_patch_sha256=manifest['patch_sha256'], native_source_sha256=manifest['files_sha256'],
                     input_sha256=inputs, source_contract_sha256=file_sha(contract_path),
                     codegen=None, exported_symbols=exports, upstream_dependencies=dependencies,
                     host=dict(system='Darwin', machine='arm64', compiler=version, compiler_argv=compiler,
                               macos_sdk=os.environ['HOST_MACOS_SDK']),
                     compiler_wrapper_sha256=sha(WRAPPER_SOURCE.encode()),
                     historical=historical_reference(download=True), tests={}, all_tests_passed=False,
                     physical_device_tested=False, gameplay_measured=False, public_release=False,
                     neoswap_host_component_packaged=False)
        save(PROOF, proof)
        for job in jobs:
            directory = OUT / 'device597' / job['name']
            directory.mkdir(parents=True, exist_ok=True)
            substitutions = dict(repo=str(ROOT), source=str(source), baseline=str(baseline), output=str(directory))
            argv = [expand(a, substitutions) for a in job['argv']]
            report_path = Path(expand(job['report'], substitutions))
            require(report_path.resolve().is_relative_to(directory.resolve()), 'Job report escapes its output directory')
            report_path.unlink(missing_ok=True)
            trace = directory / 'compiler.jsonl'
            trace.write_text('')
            env = dict(os.environ, CXX=shlex.quote(str(wrapper)), RPCS3_DEVICE597_REAL_CXX=json.dumps(compiler),
                       RPCS3_DEVICE597_CXX_TRACE=str(trace), RPCS3_DEVICE597_COMPILE_INPUTS=str(directory / 'compiled-inputs'),
                       ASAN_OPTIONS='detect_leaks=0:halt_on_error=1', UBSAN_OPTIONS='halt_on_error=1',
                       PYTHONDONTWRITEBYTECODE='1', PYTHONOPTIMIZE='0')
            log = directory / 'output.txt'
            run(argv, log, env, job.get('timeout_seconds', 300))
            report = load(report_path)
            check_report(report, job)
            compiled = check_compile_trace(trace, job, compiler) if job.get('kind', 'native') == 'native' else 0
            if job.get('kind', 'native') == 'source':
                require(not trace.read_text().strip(), 'A compiler-free source audit invoked the compiler')
            if job['argv'][1] == '{repo}/' + CODEGEN_RUNNER:
                proof['codegen'] = check_codegen(report, manifest)
            state = dict(passed=True, spec_sha256=sha(json.dumps(job, sort_keys=True).encode()),
                         kind=job.get('kind', 'native'), mode=job.get('mode'), argv=argv, returncode=0,
                         report=str(report_path.relative_to(OUT)), report_sha256=file_sha(report_path),
                         output=str(log.relative_to(OUT)), output_sha256=file_sha(log),
                         compile_trace=str(trace.relative_to(OUT)), compile_trace_sha256=file_sha(trace),
                         compile_count=compiled, native_executed_now=job.get('kind', 'native') == 'native')
            save(OUT / (job['name'] + '-result.json'), state)
            proof['tests'][job['name']] = state
            save(PROOF, proof)
        require(current_inputs(contract) == inputs, 'Repository inputs changed during preflight')
        require(upstream_dependencies(source, manifest) == dependencies, 'Upstream support inputs changed during preflight')
        require(proof['codegen'] is not None, 'The current codegen source audit did not run')
        proof['all_tests_passed'] = True
        save(PROOF, proof)
    verify(PROOF, source)


def verify(path, source):
    proof = load(path)
    manifest, contract, inputs, exports = source_contract(source, OUT / 'device597-source-contract-recheck.json')
    require(proof['schema'] == 1 and proof['type'] == 'rpcs3-device597-20261030', 'Wrong proof type')
    require(proof['all_tests_passed'] is True and proof['source'] == command('git', 'rev-parse', 'HEAD').decode().strip(), 'Incomplete or foreign proof')
    require(proof['source_patch_sha256'] == manifest['patch_sha256'] and proof['native_source_sha256'] == manifest['files_sha256'], 'Proof belongs to different native source')
    require(proof['input_sha256'] == inputs, 'Proof repository closure changed')
    require(proof['exported_symbols'] == exports, 'ABI exports changed')
    require(proof['upstream_dependencies'] == upstream_dependencies(source, manifest), 'Native support dependency closure changed')
    require(all(proof[k] is False for k in ('physical_device_tested', 'gameplay_measured', 'public_release', 'neoswap_host_component_packaged')), 'Mis-scoped proof')
    require(proof['host']['system'] == 'Darwin' and proof['host']['machine'] == 'arm64' and
            re.search(r'clang version 22\.', proof['host']['compiler']), 'Wrong native host/compiler')
    require(proof['compiler_wrapper_sha256'] == sha(WRAPPER_SOURCE.encode()), 'Compiler observation policy changed')
    require(file_sha(OUT / 'device597-source-contract.json') == proof['source_contract_sha256'], 'Initial source contract changed')
    require(proof['historical'] == historical_reference(), 'Historical provenance changed')
    jobs = selected_jobs(manifest)
    require(set(proof['tests']) == {j['name'] for j in jobs}, 'Missing/extra Apple jobs')
    for job in jobs:
        item = proof['tests'][job['name']]
        require(item['passed'] is True and item['returncode'] == 0 and item['mode'] == job.get('mode') and
                item['kind'] == job.get('kind', 'native') and item['spec_sha256'] == sha(json.dumps(job, sort_keys=True).encode()), 'Job definition changed')
        require(item['native_executed_now'] is (job.get('kind', 'native') == 'native'), 'Mis-scoped execution claim')
        substitutions = dict(repo=str(ROOT), source=proof['source_root'], baseline=proof['baseline_root'],
                             output=str(OUT / 'device597' / job['name']))
        require(item['argv'] == [expand(a, substitutions) for a in job['argv']], 'Executed job arguments changed')
        require(OUT / item['report'] == Path(expand(job['report'], substitutions)), 'Native report path changed')
        for member in ('report', 'output', 'compile_trace'):
            require(file_sha(relative_file(OUT, item[member])) == item[member + '_sha256'], 'Job artifact changed: ' + member)
        check_report(load(OUT / item['report']), job)
        if job.get('kind', 'native') == 'native':
            require(check_compile_trace(OUT / item['compile_trace'], job, proof['host']['compiler_argv']) == item['compile_count'], 'Native compilation count changed')
        else:
            require(item['compile_count'] == 0 and not (OUT / item['compile_trace']).read_text().strip(),
                    'Source audit is mislabeled as compiler-free')
        if job['argv'][1] == '{repo}/' + CODEGEN_RUNNER:
            require(proof['codegen'] == check_codegen(load(OUT / item['report']), manifest), 'Fresh source codegen proof changed')
    print('PASS device597 proof: exact current source, new Apple jobs, unchanged historical recipe; no tests replayed by verification', flush=True)
    return proof


def identity(directory):
    proof = verify(PROOF, Path(load(PROOF)['source_root']))
    sys.path.insert(0, str(ROOT / 'packages/dolphin_internal_bridge/ci'))
    from verify_ipa import macho
    sys.path.insert(0, str(ROOT / 'test'))
    import neo_swap_core_pin_test as pin
    data = (directory / 'libRPCS3Core.dylib').read_bytes()
    image = macho(data)
    require(image['platform'] == 2 and set(image['definedSymbols']) == set(proof['exported_symbols']), 'Wrong iPhone platform/exports')
    require(command('lipo', '-archs', directory / 'libRPCS3Core.dylib').decode().strip() == 'arm64', 'Wrong Core architecture')
    manifest = load(ROOT / MANIFEST)
    require((directory / 'RPCS3_SOURCE_COMMIT.txt').read_text().strip() == manifest['upstream_commit'], 'Wrong upstream identity file')
    require((directory / 'RPCS3_IOS_ABI.txt').read_text().strip() == '30', 'Wrong ABI')
    log = (OUT / 'build.log').read_text()
    for kind, expected in proof['codegen'].items():
        require(re.findall('NeoStation ' + kind + r' codegen identity: ([0-9a-f]{16})', log) == [expected], 'Compiled codegen identity differs: ' + kind)
    for hook in ('MoltenVK compile QoS hook linked', 'MoltenVK encoding-queue hook linked'):
        require(hook in log, 'Missing linked MoltenVK hook')
    archive = manifest['cell587']['moltenvk_archive']
    require(archive['input_sha256'] + ' -> ' + archive['patched_sha256'] in log, 'Wrong MoltenVK archive transform')
    require(not {'_rbx_mvk_compile_qos_queue', '_rbx_mvk_exec_q_create'} & set(
        command('nm', '-u', directory / 'libRPCS3Core.dylib').decode().split()), 'Unresolved MoltenVK hook')
    for marker in manifest[KEY]['apple_validation'].get('binary_markers', []):
        require(marker.encode() in data, 'New diagnostic marker absent from compiled Core: ' + marker)
    record = dict(schema_version=1, type='rpcs3-ios-device597-source-candidate',
                  host_commit=proof['source'], native_source_commit=proof['source'], source_commit=manifest['upstream_commit'],
                  sha256=sha(data), abi_version=30, architectures=['arm64'], source_patch_sha256=manifest['patch_sha256'],
                  core_input_sha256=pin.core_input_hashes(), device597_input_sha256=proof['input_sha256'],
                  native_source_sha256=manifest['files_sha256'], exported_symbols=proof['exported_symbols'], codegen=proof['codegen'],
                  physical_device_tested=False, gameplay_measured=False, public_release=False, neoswap_host_component_packaged=False)
    save(directory / 'identity.json', record)
    save(OUT / 'identity.json', record)
    shutil.copyfile(PROOF, directory / PROOF.name)
    print('PASS actual iPhone device597 source Core: current proof, ARM64, ABI30 and 88 exports; no delivery or device result', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--verify-reuse', type=Path)
    parser.add_argument('--write-core-identity', type=Path)
    args = parser.parse_args()
    if args.write_core_identity:
        identity(args.write_core_identity)
    elif args.source and args.verify_reuse:
        verify(args.verify_reuse, args.source.resolve())
    elif args.source:
        prepare(args.source.resolve())
    else:
        parser.error('--source or --write-core-identity is required')

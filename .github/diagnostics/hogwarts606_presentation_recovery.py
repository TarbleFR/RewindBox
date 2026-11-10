"""Reuse authenticated passed commands; execute the changed UIKit fixture.

The original job remains failed. Every reused command retains that job's
source, output hashes and complete input map. No product-source delta is allowed.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile

import hogwarts606_host as host

ROOT, OUT = host.ROOT, host.OUT
REPOSITORY = 'TarbleFR/RewindBox'
ORIGINAL_SOURCE = 'ae78b4be6aa3fbc2db3537fd0a17c9aad75b2284'
ORIGINAL_RUN, ORIGINAL_JOB, ORIGINAL_ARTIFACT = 41239330429, 124649711439, 13057550430
ORIGINAL_SIZE = 139443
ORIGINAL_SHA256 = '19fd19e819e3d4d31a159058bcdf6397427b813bb84af882c731a3d70231784e'
REUSED = ('flutter', 'analyzer', 'routing', 'standalone-parity', 'performance-journal')
FRESH = ('presentation', 'retained-achievement-integration')
VERIFIER = '.github/diagnostics/hogwarts606_presentation_recovery.py'
WORKFLOW = '.github/workflows/hogwarts606-host-recovery.yml'
# These two UIKit files affect only the fresh presentation command. The two
# Python files validate Core receipt JSON; none is imported/executed by host
# commands. All production, Dart, native journal and other test inputs match.
ALLOWED_INPUTS = {
    'test/melonx_presentation/App.swift': 'a73329b97e74702a546bfb8c06b9342855bf106828dc76cf8c85c390bac2d361',
    'test/melonx_presentation/Doubles.swift': '013df1f142949e781b6b2addeb69fbea7370d45bcc5551152a82ce8597e0d692',
    'test/melonx_performance_core_contract_test.py': 'e083077db50bc8e85bc2039425266421473def93055faba79678781277516689',
    'test/melonx_performance_finalization_test.py': '3e1d5f425982f361938931a0234343d046329d038fd661aaee523c5eb59310b4',
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2) + '\n').encode()


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


def gh(path):
    return json.loads(subprocess.check_output(['gh', 'api', 'repos/' + REPOSITORY + '/' + path], cwd=ROOT, timeout=120))


def authenticate_origin(origin):
    """Validate metadata fetched from GitHub, not a standalone annotation."""
    run, job, artifact = (origin[key] for key in ('run', 'job', 'artifact'))
    require(run['id'] == ORIGINAL_RUN and run['head_sha'] == ORIGINAL_SOURCE and
            run['head_branch'] == 'Claude' and run['run_attempt'] == 1 and
            run['path'] == '.github/workflows/hogwarts606-host.yml' and
            run['status'] == 'completed' and run['conclusion'] == 'failure', 'Wrong original run')
    require(job['id'] == ORIGINAL_JOB and job['run_id'] == ORIGINAL_RUN and
            job['head_sha'] == ORIGINAL_SOURCE and job['name'] == 'host' and
            job['status'] == 'completed' and job['conclusion'] == 'failure', 'Wrong original job')
    steps = {step['name']: step for step in job['steps']}
    require([step['name'] for step in job['steps'] if step.get('conclusion') == 'failure'] ==
            ['Exercise native journal routing and bounded output'], 'Different original failure')
    for name in ('Exercise console routing and retained-log safety',
                 'Analyze changed Dart sources and targeted tests', 'Preserve exact host checks and failures'):
        require(steps[name]['conclusion'] == 'success', 'Original prerequisite failed: ' + name)
    require(artifact['id'] == ORIGINAL_ARTIFACT and artifact['name'] == 'Hogwarts606-host-' + ORIGINAL_SOURCE and
            artifact['size_in_bytes'] == ORIGINAL_SIZE and not artifact['expired'] and
            artifact['digest'] == 'sha256:' + ORIGINAL_SHA256 and
            artifact['workflow_run']['id'] == ORIGINAL_RUN and
            artifact['workflow_run']['head_sha'] == ORIGINAL_SOURCE, 'Wrong original artifact')


def original_files(raw):
    require(len(raw) == ORIGINAL_SIZE and digest(raw) == ORIGINAL_SHA256, 'Original ZIP digest/size mismatch')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        require(len(infos) == len({entry.filename for entry in infos}) == 20 and
                sum(entry.file_size for entry in infos) < 16 * 1024 * 1024, 'Unexpected original archive bounds')
        require(all('/' not in entry.filename and '\\' not in entry.filename and
                    entry.filename not in {'.', '..'} and
                    ((entry.external_attr >> 16) & 0o170000) != 0o120000 for entry in infos), 'Unsafe original archive')
        files = {entry.filename: archive.read(entry) for entry in infos}
    expected = {'preflight.json', 'routing-native.json'} | {
        name + suffix for name in (*REUSED, 'presentation')
        for suffix in ('.execution.json', '.stdout', '.stderr')}
    require(set(files) == expected, 'Unexpected original output inventory')
    return files


def verify_commit_inputs(before):
    """Bind every old input to the source actually checked out by its job."""
    paths = sorted(before['inputs'])
    request = ''.join(ORIGINAL_SOURCE + ':' + path + '\n' for path in paths).encode()
    data = subprocess.check_output(['git', 'cat-file', '--batch'], input=request, cwd=ROOT)
    stream = io.BytesIO(data)
    for path in paths:
        header = stream.readline().split()
        require(len(header) == 3 and header[1] == b'blob', 'Missing original input: ' + path)
        raw = stream.read(int(header[2]))
        require(stream.read(1) == b'\n' and digest(raw) == before['inputs'][path], 'Original input digest mismatch: ' + path)
    require(not stream.read(), 'Unexpected git input bytes')


def recovery_record(before, current, files, origin, verifier_hashes):
    """Pure source/output checks, reused by the delivery verifier."""
    authenticate_origin(origin)
    require(before['execution'] == dict(source=ORIGINAL_SOURCE, run=ORIGINAL_RUN, attempt=1), 'Original preflight origin mismatch')
    require(before['environment']['system'] == 'Darwin' and before['environment']['machine'] == 'arm64', 'Original native host scope')
    delta = {path: {'from': before['inputs'].get(path), 'to': current['inputs'].get(path)}
             for path in before['inputs'].keys() | current['inputs'].keys()
             if before['inputs'].get(path) != current['inputs'].get(path)}
    require(set(delta) == set(ALLOWED_INPUTS) and
            all(value['to'] == ALLOWED_INPUTS[path] for path, value in delta.items()), 'Unreviewed input delta')
    require(before['analyzerPaths'] == current['analyzerPaths'], 'Analyzer scope changed')
    expected_commands = {
        'flutter': ['flutter', 'test', '--no-pub', '--concurrency=1', '--machine', *host.TESTS],
        'analyzer': ['dart', 'analyze', '--format=machine', '--fatal-warnings', *before['analyzerPaths']],
        **dict(host.NATIVE_COMMANDS),
    }
    reused = {}
    for name in (*REUSED, 'presentation'):
        record = json.loads(files[name + '.execution.json'])
        require(record['command'] == expected_commands[name], 'Original command changed: ' + name)
        for suffix in ('stdout', 'stderr'):
            require(record[suffix + 'SHA256'] == digest(files[name + '.' + suffix]), 'Original output changed: ' + name)
        require((record['exitCode'] == 0) == (name in REUSED), 'Original command verdict changed: ' + name)
        if name in REUSED:
            reused[name] = dict(source=ORIGINAL_SOURCE, run=ORIGINAL_RUN, attempt=1,
                job=ORIGINAL_JOB, artifact=ORIGINAL_ARTIFACT, execution=record,
                originalPreflightSHA256=digest(files['preflight.json']))
    host.flutter_result(files['flutter.stdout'])
    host.analyzer_result(files['analyzer.stdout'])
    routing = json.loads(files['routing-native.json'])
    require(routing['result'] == 'passed' and routing['actualFoundation'] is True and
            all(before['inputs'].get(path) == current['inputs'].get(path) == value
                for path, value in routing['inputs'].items()), 'Reused native writer inputs changed')
    for name, phrase in [('standalone-parity', 'Executed the stderr capture and MoltenVK preference on macOS.'),
                         ('performance-journal', 'Executed the performance journal on macOS.')]:
        require(phrase in files[name + '.stdout'].decode(), 'Native execution missing: ' + name)
    failure = json.loads(files['presentation.stdout'])
    require(failure['result'] == 'failed' and failure['detail'] ==
            'native performance sample/final persisted exactly once', 'Wrong original UIKit failure')
    require(set(verifier_hashes) == {VERIFIER, WORKFLOW}, 'Missing recovery source binding')
    return dict(schema=1,
        original=dict(repository=REPOSITORY, source=ORIGINAL_SOURCE, run=ORIGINAL_RUN, attempt=1,
                      job=ORIGINAL_JOB, conclusion='failure', artifact=ORIGINAL_ARTIFACT,
                      zip='original-host.zip', zipSize=ORIGINAL_SIZE, zipSHA256=ORIGINAL_SHA256,
                      metadata='reused-origin.json', metadataSHA256=digest(encoded(origin))),
        freshCommands=list(FRESH), reusedCommands=reused, inputDelta=dict(sorted(delta.items())),
        recoverySources=verifier_hashes,
        note='Original job remains failed. Only passed unaffected commands are reused with their original provenance.')


def prepare():
    current = host.prepare()
    origin = {name: gh(path) for name, path in {
        'run': 'actions/runs/' + str(ORIGINAL_RUN),
        'job': 'actions/jobs/' + str(ORIGINAL_JOB),
        'artifact': 'actions/artifacts/' + str(ORIGINAL_ARTIFACT)}.items()}
    authenticate_origin(origin)
    raw = subprocess.check_output(['gh', 'api', 'repos/' + REPOSITORY + '/actions/artifacts/' + str(ORIGINAL_ARTIFACT) + '/zip'], cwd=ROOT, timeout=180)
    files = original_files(raw)
    before = json.loads(files['preflight.json'])
    verify_commit_inputs(before)
    hashes = {path: digest((ROOT / path).read_bytes()) for path in (VERIFIER, WORKFLOW)}
    current['recovery'] = recovery_record(before, current, files, origin, hashes)
    (OUT / 'original-host.zip').write_bytes(raw)
    (OUT / 'reused-origin.json').write_bytes(encoded(origin))
    for name in REUSED:
        for suffix in ('.execution.json', '.stdout', '.stderr'):
            (OUT / (name + suffix)).write_bytes(files[name + suffix])
    (OUT / 'routing-native.json').write_bytes(files['routing-native.json'])
    host.write('preflight.json', current)
    return current['recovery']


def finalize():
    current = host.current()
    origin = json.loads((OUT / 'reused-origin.json').read_bytes())
    files = original_files((OUT / 'original-host.zip').read_bytes())
    hashes = {path: digest((ROOT / path).read_bytes()) for path in (VERIFIER, WORKFLOW)}
    expected = recovery_record(json.loads(files['preflight.json']), current, files, origin, hashes)
    require(current['recovery'] == expected, 'Recovery provenance changed')
    for name in REUSED:
        for suffix in ('.execution.json', '.stdout', '.stderr'):
            require((OUT / (name + suffix)).read_bytes() == files[name + suffix], 'Copied original output changed')
    return host.finalize()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'execute', 'finalize'))
    action = parser.parse_args().action
    if action == 'prepare':
        result = prepare()
    elif action == 'execute':
        commands = dict(host.NATIVE_COMMANDS)
        result = {name: host.run_command(name, commands[name]) for name in FRESH}
    else:
        result = finalize()
    print(json.dumps({key: value for key, value in result.items() if key != 'inputs'}, indent=2))

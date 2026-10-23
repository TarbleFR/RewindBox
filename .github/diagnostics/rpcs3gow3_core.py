"""Authenticate Core 510 proofs and execute the reviewed three-file restore delta."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
BASE = '50714fe0980d0b50ccd93c1c739c480b054a31b9'
BASE_RUN = 39888215155
BASE_JOB = 120201349645
PROOF_ARTIFACT = 12476405230
PROOF_SHA = '32adb6f8939b5b347407c91b394e0c52c5bbc5974313086f9742cdc060621a73'
OLD_PATCH = 'f31bf5f7d66c44dd3a02683a12a3b3ad6ac450d83bd66603e8c2010f7579198d'
NEW_PATCH = 'db839d645eee6dc8dabba55a1580cb41a8314cbac0cb6c5e26f6c8a1be0f4f61'
POLICY_NOTE = 'Build 513 bounds iOS TAR restore buffers and recognizes transient LLVM JIT threads; no PPU/SPU translation or settings policy change.'
CHANGED_CORE = {
    'rpcs3/Loader/TAR.cpp': '8a77b61d7a6bc292e22cb14170737a1780e9b30ba8b493c2bdbd041e671b4c8a',
    'rpcs3/ios/RPCS3IOSPerformance.cpp': 'a2b96ba798ec5a8cf946129dfea64ff8d7ae45d9f4e8be11e9d7928ad20aa800',
    'rpcs3/ios/RPCS3IOSProfilerHelpers.h': 'd11297d9ac5025a8335b4ff18215a0222f63a90f8f95c4c6bc4ee72bb740ea83',
}
SELF = '.github/diagnostics/rpcs3gow3_core.py'
NEW_TEST = 'test/rpcs3_gow3_restore_regression_test.py'
FIXTURE = 'test/fixtures/rpcs3_gow3_restore.diff'

def command(*args):
    return subprocess.check_output(args, cwd=ROOT)

def old(path):
    return command('git', 'show', BASE + ':' + path)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def pin_module():
    sys.path.insert(0, str(ROOT / 'test'))
    import neo_swap_core_pin_test as core
    return core

def blocks(data):
    matches = list(re.finditer(rb'^diff --git a/(.*?) b/\1\n', data, re.M))
    # Regenerator normalizes Git blob-id abbreviation only; retain every other byte.
    return {m[1].decode(): re.sub(rb'^index [0-9a-f]+\.\.[0-9a-f]+(.*)$', rb'index IDS\1',
        data[m.start():matches[i+1].start() if i+1<len(matches) else len(data)], flags=re.M)
        for i,m in enumerate(matches)}

def verify_source():
    core=pin_module()
    core.validate_source_contract()
    manifest_path='build-utils/rpcs3/canonical-source.json'
    before=json.loads(old(manifest_path))
    after=json.loads((ROOT/manifest_path).read_bytes())
    assert before['patch_sha256']==OLD_PATCH and after['patch_sha256']==NEW_PATCH
    assert after['device_runtime_tested'] is False
    assert set(after['files_sha256'])-set(before['files_sha256'])=={'rpcs3/Loader/TAR.cpp'}
    assert set(before['files_sha256'])-set(after['files_sha256'])==set()
    assert {k for k in before['files_sha256'] if before['files_sha256'][k]!=after['files_sha256'][k]}==set(CHANGED_CORE)-{'rpcs3/Loader/TAR.cpp'}
    for path,digest in CHANGED_CORE.items(): assert after['files_sha256'][path]==digest
    expected=dict(before)
    expected['files_sha256']=after['files_sha256']
    expected['patch_sha256']=NEW_PATCH
    expected['policy']=before['policy'].rstrip()+' '+POLICY_NOTE
    assert after==expected, 'Unreviewed manifest policy change'
    a=blocks(old('build-utils/rpcs3/embedded-core.patch'))
    b=blocks((ROOT/'build-utils/rpcs3/embedded-core.patch').read_bytes())
    assert set(b)-set(a)=={'rpcs3/Loader/TAR.cpp'} and not set(a)-set(b)
    assert {k for k in a if a[k]!=b[k]}==set(CHANGED_CORE)-{'rpcs3/Loader/TAR.cpp'}
    changed_inputs={SELF,NEW_TEST,FIXTURE,manifest_path,'build-utils/rpcs3/embedded-core.patch',
        '.github/workflows/rpcs3-memory-audit.yml','build-utils/rpcs3_core_syntax_gate.py','test/neo_swap_core_pin_test.py'}
    for path in core.CORE_INPUTS:
        if path not in changed_inputs:
            assert (ROOT/path).read_bytes()==old(path), 'Changed prior proof input: '+path
    path='test/neo_swap_core_pin_test.py'
    expected=old(path).decode().replace(OLD_PATCH,NEW_PATCH).replace('CORE_INPUTS = (\n',
        "CORE_INPUTS = (\n    'test/rpcs3_gow3_restore_regression_test.py',\n    'test/fixtures/rpcs3_gow3_restore.diff',\n")
    assert (ROOT/path).read_text()==expected
    path='build-utils/rpcs3_core_syntax_gate.py'
    assert (ROOT/path).read_text()==old(path).decode().replace("UNITS = {", "UNITS = {'TAR.cpp', ",1)
    return core.core_input_hashes()

def api(path):
    return json.loads(command('gh','api','repos/TarbleFR/RewindBox/'+path))

def prepare(source,output):
    inputs=verify_source()
    run=api('actions/runs/'+str(BASE_RUN))
    assert run['head_sha']==BASE and run['status']=='completed' and run['conclusion']=='success'
    jobs=api('actions/runs/'+str(BASE_RUN)+'/jobs?per_page=100')['jobs']
    assert any(j['id']==BASE_JOB and j['conclusion']=='success' for j in jobs)
    version=command(str(Path(command('brew','--prefix','llvm@22').decode().strip())/'bin/llvm-config'),'--version').decode().strip()
    assert version=='22.1.8',version
    archive=Path(os.environ['RUNNER_TEMP'])/'gow3-prior-proofs.zip'
    with archive.open('wb') as stream:
        subprocess.run(['gh','api',f'repos/TarbleFR/RewindBox/actions/artifacts/{PROOF_ARTIFACT}/zip'],stdout=stream,check=True)
    assert sha(archive.read_bytes())==PROOF_SHA
    diagnostics=ROOT/'build/rpcs3-core-diagnostics'
    diagnostics.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        for item in bundle.infolist():
            relative=PurePosixPath(item.filename)
            assert not relative.is_absolute() and '..' not in relative.parts
            if not item.is_dir():
                dest=diagnostics/'prior510'/relative
                dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_bytes(bundle.read(item))
    prior=json.loads((diagnostics/'prior510/gow3-reuse.json').read_bytes())
    identity=json.loads((diagnostics/'prior510/identity.json').read_bytes())
    assert prior['source']==BASE and identity['host_commit']==BASE
    assert identity['source_patch_sha256']==OLD_PATCH
    for path,digest in prior['core_input_sha256'].items(): assert sha(old(path))==digest,path
    assert identity['core_input_sha256']==prior['core_input_sha256']
    assert sha((diagnostics/'prior510/gow3-boot-proof.txt').read_bytes())==prior['new_targeted_log_sha256']
    assert 'PASS God of War III boot regressions' in (diagnostics/'prior510/gow3-boot-proof.txt').read_text()
    for name in ['memory-audit-proof.txt','spu-object-cache-proof.txt','llvm-pipeline-proof.txt',
        'build499-proof.txt','build487-core-proof.txt','build487-host-proof.txt']:
        assert 'PASS' in (diagnostics/'prior510/prior508'/name).read_text(),name
    for path,digest in CHANGED_CORE.items(): assert sha((source/path).read_bytes())==digest,path
    log=diagnostics/'gow3-restore-proof.txt'
    env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1')
    test=subprocess.run([sys.executable,str(ROOT/NEW_TEST),str(source),'--sanitize',
        '--report',str(diagnostics/'gow3-restore-cases.json')],env=env,stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,text=True,timeout=600)
    log.write_text(test.stdout)
    print(test.stdout,end='')
    test.check_returncode()
    # The syntax gate changed only by adding TAR; test actual command preservation.
    syntax=subprocess.run([sys.executable,str(ROOT/'test/rpcs3_core_syntax_gate_test.py')],
        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=180)
    (diagnostics/'syntax-gate-proof.txt').write_text(syntax.stdout)
    syntax.check_returncode()
    record={'schema':2,'source':command('git','rev-parse','HEAD').decode().strip(),
        'core_input_sha256':inputs,'prior_source':BASE,'prior_run':BASE_RUN,'prior_job':BASE_JOB,
        'prior_artifact':PROOF_ARTIFACT,'prior_archive_sha256':PROOF_SHA,'llvm':version,
        'changed_core':CHANGED_CORE,'new_targeted_test':NEW_TEST,'new_targeted_log':str(log.relative_to(ROOT)),
        'new_targeted_log_sha256':sha(log.read_bytes()),
        'scope':'Exact unchanged Core 510/508 proofs retained; new TAR/profiler ASan/UBSan tests; current Core still requires iPhone compilation and binary gates',
        'physical_device_tested':False}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(record,indent=2)+'\n')
    print('PASS authenticated Core 510 proofs and newly executed restore/profiler regressions')

def verify_receipt(path):
    record=json.loads(path.read_bytes())
    assert record['schema']==2 and record['source']==command('git','rev-parse','HEAD').decode().strip()
    assert record['core_input_sha256']==verify_source()
    assert record['prior_source']==BASE and record['prior_run']==BASE_RUN
    assert record['prior_archive_sha256']==PROOF_SHA and record['llvm']=='22.1.8'
    assert record['changed_core']==CHANGED_CORE
    log=ROOT/record['new_targeted_log']
    assert record['new_targeted_log_sha256']==sha(log.read_bytes())
    assert 'PASS God of War III restore/profiler regressions' in log.read_text()
    print('PASS source-bound restore reuse receipt; unchanged native campaigns retained')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'build/rpcs3-core-diagnostics/gow3-reuse.json')
    parser.add_argument('--verify-reuse',type=Path)
    args=parser.parse_args()
    if args.verify_reuse: verify_receipt(args.verify_reuse)
    elif args.source: prepare(args.source.resolve(),args.output.resolve())
    else:
        verify_source()
        print('PASS reviewed three-file restore delta and unchanged prior proof inputs')

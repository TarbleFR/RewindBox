"""Authenticate Core 513 proofs and execute the reviewed restore/freeze follow-up."""
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
BASE = 'c5e54c5817f848e6f667b757931f91364e9faeda'
BASE_RUN = 39968584447
BASE_JOB = 120464895339
PROOF_ARTIFACT = 12508761363
PROOF_SHA = '927221b7aa0b025a263df3ad8eba59f10dd00c54128e8101fad24b439b1ad143'
OLD_PATCH = 'db839d645eee6dc8dabba55a1580cb41a8314cbac0cb6c5e26f6c8a1be0f4f61'
NEW_PATCH = '388c5c37ed89c97d2b2aebd7642b611fd5a5ef2ed1d3c0cfa2be815357f66767'
POLICY_NOTE = 'Restore follow-up bounds the TAR reader by its declared chunk count, preserves unsatisfied RSX acquire dependencies with bounded host waits, and retains complete bounded freeze snapshots and restore phase diagnostics; save formats and PPU/SPU code generation remain unchanged.'
CHANGED_CORE = {'rpcs3/Loader/TAR.cpp': '47b9fca0855a3ac2d3a05699aa7857b94709540c6921968889deee98b70bf0cd', 'rpcs3/Emu/RSX/NV47/HW/nv406e.cpp': 'b8855f642f9a65ba83cf81f4ed09256a822555c45de20c43d7843793250c2dd1', 'rpcs3/Emu/System.cpp': '5fd1adfcd1f95c3ba063f3bc5ac9bd5b4137d2f4e7944b164f8cf58d9a8090d2', 'rpcs3/ios/RPCS3IOSFreezeDump.cpp': '68b30b9ebe8b869051d8d18f88ebc1aac36de25b940fc7b12c072625e3a815fc'}
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
    assert set(after['files_sha256'])==set(before['files_sha256'])
    assert {k for k in before['files_sha256'] if before['files_sha256'][k]!=after['files_sha256'][k]}==set(CHANGED_CORE)
    for path,digest in CHANGED_CORE.items(): assert after['files_sha256'][path]==digest
    expected=dict(before)
    expected['files_sha256']=after['files_sha256']
    expected['patch_sha256']=NEW_PATCH
    expected['policy']=before['policy'].rstrip()+' '+POLICY_NOTE
    assert after==expected, 'Unreviewed manifest policy change'
    a=blocks(old('build-utils/rpcs3/embedded-core.patch'))
    b=blocks((ROOT/'build-utils/rpcs3/embedded-core.patch').read_bytes())
    assert set(a)==set(b)
    assert {k for k in a if a[k]!=b[k]}==set(CHANGED_CORE)
    changed_inputs={SELF,NEW_TEST,FIXTURE,manifest_path,'build-utils/rpcs3/embedded-core.patch',
        '.github/workflows/rpcs3-memory-audit.yml','build-utils/rpcs3_core_syntax_gate.py','test/neo_swap_core_pin_test.py',
        'test/rpcs3_restore_eof_test.py','test/rpcs3_build265_core_test.py',
        'test/rpcs3_build487_host_diagnostics_test.py',
        'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm'}
    for path in core.CORE_INPUTS:
        if path not in changed_inputs:
            assert (ROOT/path).read_bytes()==old(path), 'Changed prior proof input: '+path
    path='test/neo_swap_core_pin_test.py'
    added=['test/rpcs3_restore_eof_test.py','test/native/rpcs3_savestate_harness.cpp',
        'test/rpcs3_build265_core_test.py','packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm']
    expected=old(path).decode().replace(OLD_PATCH,NEW_PATCH).replace('CORE_INPUTS = (\n',
        'CORE_INPUTS = (\n'+''.join('    '+repr(n)+',\n' for n in added),1)
    assert (ROOT/path).read_text()==expected
    path='build-utils/rpcs3_core_syntax_gate.py'
    assert (ROOT/path).read_text()==old(path).decode().replace("UNITS = {'TAR.cpp',", "UNITS = {'nv406e.cpp', 'TAR.cpp',",1)
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
                dest=diagnostics/'prior513'/relative
                dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_bytes(bundle.read(item))
    prior=json.loads((diagnostics/'prior513/gow3-reuse.json').read_bytes())
    identity=json.loads((diagnostics/'prior513/identity.json').read_bytes())
    assert prior['source']==BASE and identity['host_commit']==BASE
    assert identity['source_patch_sha256']==OLD_PATCH
    for path,digest in prior['core_input_sha256'].items(): assert sha(old(path))==digest,path
    assert identity['core_input_sha256']==prior['core_input_sha256']
    assert sha((diagnostics/'prior513/gow3-restore-proof.txt').read_bytes())==prior['new_targeted_log_sha256']
    assert 'PASS God of War III restore/profiler regressions' in (diagnostics/'prior513/gow3-restore-proof.txt').read_text()
    for name in ['memory-audit-proof.txt','spu-object-cache-proof.txt','llvm-pipeline-proof.txt',
        'build499-proof.txt','build487-core-proof.txt','build487-host-proof.txt']:
        assert 'PASS' in (diagnostics/'prior513/prior510/prior508'/name).read_text(),name
    for path,digest in CHANGED_CORE.items(): assert sha((source/path).read_bytes().replace(b'\r\n',b'\n'))==digest,path
    log=diagnostics/'freeze-followup-proof.txt'
    env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1')
    tests=[
        ['test/rpcs3_restore_eof_test.py',str(source),'--sanitize','--report',str(diagnostics/'restore-eof-cases.json')],
        [NEW_TEST,str(source),'--sanitize','--only-tar','--report',str(diagnostics/'tar-window-cases.json')],
        ['test/rpcs3_build265_core_test.py',str(source)],
        ['test/rpcs3_build487_host_diagnostics_test.py','--core',str(source)],
        ['test/rpcs3_core_syntax_gate_test.py'],
    ]
    with log.open('w') as stream:
        for command_line in tests:
            test=subprocess.run([sys.executable,*command_line],cwd=ROOT,env=env,stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,text=True,timeout=600)
            stream.write(test.stdout);stream.flush()
            print(test.stdout,end='')
            test.check_returncode()
        stream.write('PASS restore/freeze follow-up regressions\n')
    record={'schema':3,'source':command('git','rev-parse','HEAD').decode().strip(),
        'core_input_sha256':inputs,'prior_source':BASE,'prior_run':BASE_RUN,'prior_job':BASE_JOB,
        'prior_artifact':PROOF_ARTIFACT,'prior_archive_sha256':PROOF_SHA,'llvm':version,
        'changed_core':CHANGED_CORE,'new_targeted_tests':tests,'new_targeted_log':str(log.relative_to(ROOT)),
        'new_targeted_log_sha256':sha(log.read_bytes()),
        'scope':'Exact unchanged Core 513/510/508 proofs retained; real ZSTD TAR boundary negative control, bounded-memory TAR, delayed RSX producer and complete freeze snapshot tests; current Core still requires iPhone compilation and binary gates',
        'physical_device_tested':False}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(record,indent=2)+'\n')
    print('PASS authenticated Core 513 proofs and newly executed restore/freeze regressions')

def verify_receipt(path):
    record=json.loads(path.read_bytes())
    assert record['schema']==3 and record['source']==command('git','rev-parse','HEAD').decode().strip()
    assert record['core_input_sha256']==verify_source()
    assert record['prior_source']==BASE and record['prior_run']==BASE_RUN
    assert record['prior_archive_sha256']==PROOF_SHA and record['llvm']=='22.1.8'
    assert record['changed_core']==CHANGED_CORE
    log=ROOT/record['new_targeted_log']
    assert record['new_targeted_log_sha256']==sha(log.read_bytes())
    assert 'PASS restore/freeze follow-up regressions' in log.read_text()
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
        print('PASS reviewed four-file restore/freeze delta and unchanged prior proof inputs')

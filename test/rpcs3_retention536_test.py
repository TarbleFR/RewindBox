#!/usr/bin/env python3
"""Actual Foundation logger: retain per-writer and resilience evidence after errors."""
import hashlib,json,os,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE='35ed01854848d51a0b3f0b0f1c40a29960ad3331'
LOGGER='packages/rpcs3_internal_bridge/ios/Classes/Rpcs3Diagnostics.mm'
INPUTS=[LOGGER,'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3Diagnostics.h',
 'test/rpcs3_retention536_test.py','test/rpcs3_diagnostics_native_test.py',
 'test/native/rpcs3_diagnostics_test.mm','test/native/rpcs3_diagnostics_core_writer.mm','test/native/rpcs3_diagnostics_jit_writer.mm']
def input_hashes():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in INPUTS}
def main():
    assert sys.platform=='darwin','Actual Foundation execution is required'
    original=(ROOT/'test/native/rpcs3_diagnostics_test.mm').read_text()
    anchor='    for (unsigned i = 0; i < 1300; ++i)'
    assert original.count(anchor)==1
    case=original.replace(anchor,'''    RPCS3Diagnostic(@"core_log", @"RANGELOCKPROF session=7 marker=writer_before_restore");
    RPCS3Diagnostic(@"core_log", @"COREPROF_RESILIENCE marker=pressure_before_restore");
'''+anchor).replace('assert(history.count == 2);','''assert(history.count == 4);
    assert([history[1][@"message"] containsString:@"writer_before_restore"]);
    assert([history[2][@"message"] containsString:@"pressure_before_restore"]);''').replace('== 53);','== 55);')
    results={}
    with tempfile.TemporaryDirectory(prefix='retention536-') as td:
        work=Path(td);test=work/'test.mm';test.write_text(case)
        for name in ('before','after'):
            path=work/(name+'.mm')
            payload=subprocess.check_output(['git','show',BASE+':'+LOGGER],cwd=ROOT) if name=='before' else (ROOT/LOGGER).read_bytes()
            path.write_bytes(payload);exe=work/name;directory=work/(name+'-logs');directory.mkdir()
            subprocess.run(['xcrun','clang++','-fobjc-arc','-fblocks','-std=c++20','-DRPCS3_DIAGNOSTICS_TESTING=1','-framework','Foundation',
                '-I',str(ROOT),'-I',str((ROOT/LOGGER).parent),str(path),str(test),
                str(ROOT/'test/native/rpcs3_diagnostics_core_writer.mm'),str(ROOT/'test/native/rpcs3_diagnostics_jit_writer.mm'),'-o',str(exe)],check=True)
            run=subprocess.run([str(exe),str(directory)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
            if name=='before':assert run.returncode==-6 and b'history.count == 4' in run.stderr,(run.returncode,run.stderr)
            else:assert run.returncode==0,(run.returncode,run.stderr)
            results[name]=dict(returncode=run.returncode,loggerSHA256=hashlib.sha256(payload).hexdigest(),expectedOutcome=True)
    out=ROOT/'build/delivery/retention536-tests.json';out.parent.mkdir(parents=True,exist_ok=True)
    report=dict(passed=True,source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        run=os.environ.get('GITHUB_RUN_ID'),inputs=input_hashes(),results=results,generatedHarnessSHA256=hashlib.sha256(case.encode()).hexdigest(),
        physicalDeviceTested=False,scope='Actual Foundation logger, two producers, rotation/reopen, 1300 verbose restore records followed by missing-resource error. Both attribution records survive in the bounded performance history; old source loses them.')
    out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()

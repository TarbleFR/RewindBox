#!/usr/bin/env python3
"""Compare production decrementer workers across repeated expiration batches.

Reuses the established full-class deterministic host adapters; adds sustained
wakes, scratch growth and late allocation failures. No guest codegen, CPU
scheduler ordering or physical-device performance claim follows from this test.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import tempfile

import rpcs3_spu_timer_runtime_test as runtime
from rpcs3_texture_address_index_test import braced

ROOT=Path(__file__).resolve().parents[1]
EXTRA=ROOT/'test/native/rpcs3_spu_timer_reuse.inc'


def harness(source,baseline):
    old=(baseline/runtime.CPP).read_text();new=(source/runtime.CPP).read_text()
    old_worker=braced(runtime.timer(baseline),'void operator()()')
    new_worker=braced(runtime.timer(source),'void operator()()')
    assert old.replace(old_worker,'@WORKER@',1)==new.replace(new_worker,'@WORKER@',1)
    assert braced(old_worker,'const auto pending_end = std::remove_if(')==braced(new_worker,'const auto pending_end = std::remove_if(')
    assert braced(old_worker,'for (const auto& e : due_entries)')==braced(new_worker,'for (const auto& e : due_entries)')
    for relative in runtime.SUPPORT:
        assert (source/relative).read_bytes()==(baseline/relative).read_bytes()
    code=runtime.ADAPTER.read_text().split('int main() {',1)[0]
    code=code.replace('std::function<void()> inspect_pending;',
                      'std::function<void()> inspect_pending;\n    std::function<void(std::size_t)> on_wait;')
    code=code.replace('if(env.inspect_pending) env.inspect_pending();',
                      'if(env.on_wait) env.on_wait(env.waits.size());\n    if(env.inspect_pending) env.inspect_pending();')
    code=code.replace('@FLAGS@',braced((source/runtime.CPU).read_text(),'enum class cpu_flag : u32')+';\n')
    code=code.replace('@BEFORE@',runtime.program(baseline,'before')).replace('@AFTER@',runtime.program(source,'after'))
    return code+EXTRA.read_text()


def timing_program(source,baseline):
    # Same extracted sweeps and sample matrix as the prior test. Model the real
    # per-wake scratch lifetime instead of constructing both variants afresh.
    code=runtime.timing_program(source,baseline)
    code=code.replace('std::vector<entry> armed; armed.reserve(input.size());',
                      'std::vector<entry> armed; armed.reserve(input.size());\n    std::vector<entry> retained; const bool reuse=f==candidate;')
    code=code.replace('armed=input; std::vector<entry> due;',
                      'armed=input; std::vector<entry> fresh; auto& due=reuse?retained:fresh;')
    code=code.replace('sink+=f(armed,due,1000)+armed.size()+due.size();',
                      'sink+=f(armed,due,1000)+armed.size()+due.size(); due.clear();')
    return code


def expected(source,baseline):
    return dict(sourceSHA256={p:runtime.sha((source/p).read_bytes()) for p in runtime.SOURCE+runtime.SUPPORT},
                baselineSHA256={p:runtime.sha((baseline/p).read_bytes()) for p in runtime.SOURCE+runtime.SUPPORT},
                harnessSHA256=runtime.sha(harness(source,baseline).encode()),
                timingHarnessSHA256=runtime.sha(timing_program(source,baseline).encode()),
                adapterSHA256={str(p.relative_to(ROOT)):runtime.sha(p.read_bytes()) for p in [runtime.ADAPTER,EXTRA]})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--compiler',default=os.environ.get('CXX','c++'))
    p.add_argument('--sanitizer',choices=['address,undefined']);p.add_argument('--report',type=Path,required=True)
    a=p.parse_args();source=a.source.resolve();baseline=a.baseline.resolve();identities=expected(source,baseline)
    compiler=shlex.split(a.compiler)
    flags=['-std=c++20','-g','-Wall','-Wextra','-Werror','-UNDEBUG','-pthread','-O1' if a.sanitizer else '-O3']
    if a.sanitizer:
        flags+=['-fsanitize='+a.sanitizer,'-fno-omit-frame-pointer']
        if platform.system()=='Linux':flags+=['-fno-pie','-no-pie']
    if sdk:=os.environ.get('HOST_MACOS_SDK'):flags+=['-isysroot',sdk]
    timing=None
    with tempfile.TemporaryDirectory(prefix='rpcs3-timer-reuse-') as tmp:
        cpp=Path(tmp)/'test.cpp';exe=Path(tmp)/'test'
        cpp.write_text(harness(source,baseline));subprocess.run(compiler+flags+[str(cpp),'-o',str(exe)],check=True)
        result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=120,
                              env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1'))
        assert result.returncode==0 and not result.stderr,(result.returncode,result.stdout,result.stderr)
        data=json.loads(result.stdout)
        assert data['passed'] and data['matrixCases']==210 and data['candidateStableAllocations']==1
        if not a.sanitizer:
            cpp.write_text(timing_program(source,baseline));subprocess.run(compiler+flags+[str(cpp),'-o',str(exe)],check=True)
            timing=json.loads(subprocess.check_output([str(exe)],text=True,timeout=60))
    assert identities==expected(source,baseline)
    report=dict(passed=True,assertionsActive=True,**identities,results=data,hostSweepTiming=timing,
                compiler=subprocess.check_output(compiler+['--version'],text=True).splitlines()[0],compilerFlags=flags,
                sanitizer=a.sanitizer,host=platform.machine(),leakSanitizer=False,
                physicalDeviceTested=False,gameplayMeasured=False,concurrentMemoryOrderingTested=False)
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()

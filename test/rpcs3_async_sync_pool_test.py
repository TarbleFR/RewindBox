#!/usr/bin/env python3
"""Run the complete async scheduler before/after with explicit Vulkan boundaries.

Counts actual constructor requests made by the production scheduler, not driver
timing or iPhone FPS. Safe, fast and strict modes run through two pool wraps.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import tempfile
from rpcs3_texture_exact_index_test import stripped

ROOT=Path(__file__).resolve().parents[1]
FILES=['rpcs3/Emu/RSX/VK/VKAsyncScheduler.h','rpcs3/Emu/RSX/VK/VKAsyncScheduler.cpp']
ADAPTER=ROOT/'test/native/rpcs3_async_sync_pool.inc'
sha=lambda p:hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()

def harness(source,baseline):
    assert sha(source/FILES[0])==sha(baseline/FILES[0])
    old=(baseline/FILES[1]).read_text();new=(source/FILES[1]).read_text()
    # The entire desktop implementation must remain exactly the original.
    desktop=new
    while '#ifdef RPCS3_IOS' in desktop:
        a=desktop.index('#ifdef RPCS3_IOS');end=desktop.index('#endif',a)
        mid=desktop.find('#else',a,end)
        desktop=desktop[:a]+(desktop[mid+len('#else\n'):end] if mid!=-1 else '')+desktop[end+len('#endif\n'):]
    assert desktop==old
    variants=''
    for label,tree,ios in [('before',baseline,False),('after',source,True),('desktop',source,False)]:
        if ios:variants+='#define RPCS3_IOS\n'
        variants+='namespace '+label+' { namespace vk { using namespace boundary; }\n'
        variants+=stripped(tree/FILES[0])+ '\n'+stripped(tree/FILES[1])+'\n}\n'
        if ios:variants+='#undef RPCS3_IOS\n'
    return ADAPTER.read_text().replace('@VERSIONS@',variants)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--compiler',default=os.environ.get('CXX','c++'));p.add_argument('--sanitizer',choices=['address,undefined']);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    source=a.source.resolve();baseline=a.baseline.resolve();code=harness(source,baseline)
    flags=['-std=c++20','-Wall','-Wextra','-Werror','-UNDEBUG','-g','-O1' if a.sanitizer else '-O3']
    if a.sanitizer:
        flags+=['-fsanitize='+a.sanitizer,'-fno-omit-frame-pointer']
        if platform.system()=='Linux':flags+=['-fno-pie','-no-pie']
    if sdk:=os.environ.get('HOST_MACOS_SDK'):flags+=['-isysroot',sdk]
    compiler=shlex.split(a.compiler)
    with tempfile.TemporaryDirectory(prefix='rpcs3-sync-pool-') as tmp:
        cpp=Path(tmp)/'test.cpp';exe=Path(tmp)/'test';cpp.write_text(code)
        subprocess.run([*compiler,*flags,str(cpp),'-o',str(exe)],check=True)
        run=subprocess.run([str(exe)],text=True,capture_output=True,timeout=60,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'))
        assert run.returncode==0,(run.returncode,run.stdout,run.stderr)
        result=json.loads(run.stdout)
    report=dict(passed=True,sourceSHA256={p:sha(source/p) for p in FILES},baselineSHA256={p:sha(baseline/p) for p in FILES},
        harnessSHA256=hashlib.sha256(code.encode()).hexdigest(),adapterSHA256=sha(ADAPTER),compiler=subprocess.check_output([*compiler,'--version'],text=True).splitlines()[0],
        compilerFlags=flags,host=platform.machine(),results=result,physicalDeviceTested=False,gameplayMeasured=False)
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()

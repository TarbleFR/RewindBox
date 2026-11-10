#!/usr/bin/env python3
"""Compile actual reporter bodies with explicit host log/clock adapters."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import tempfile

HERE=Path(__file__).resolve().parent
def braced(text,marker):
    begin=text.index(marker);start=text.index('{',begin);depth=1
    for end in range(start+1,len(text)):
        depth+=(text[end]=='{')-(text[end]=='}')
        if not depth:return text[begin:end+1]
    raise AssertionError(marker)
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path)
    p.add_argument('--renderer',type=Path)
    p.add_argument('--cpu',type=Path)
    p.add_argument('--compiler',default=os.environ.get('CXX','g++'))
    p.add_argument('--sanitizer',default='')
    p.add_argument('--report',required=True,type=Path)
    a=p.parse_args();source=a.source.resolve();renderer=(a.renderer or a.source).resolve();cpu=(a.cpu or a.source).resolve()
    actual=source/'rpcs3/ios/RPCS3IOSPerformance.cpp';text=actual.read_text()
    reporters='\n'.join(braced(text,marker) for marker in ('void report_renderer_causes(', 'void report_signal_causes('))
    frame=braced(text,'{\n            const u64 anchor_before = utils::get_tsc();')
    adapter=HERE/'format_adapter.cpp.in'
    code=adapter.read_text().replace('@REPORTERS@',reporters).replace('@FRAME_BLOCK@',frame)
    compiler=shlex.split(a.compiler)
    flags=['-std=c++20','-O2','-UNDEBUG','-Wall','-Wextra','-Werror','-pthread','-fno-omit-frame-pointer']
    if a.sanitizer:flags+=['-fsanitize='+a.sanitizer,'-g']
    if sdk:=os.environ.get('HOST_MACOS_SDK'):flags+=['-isysroot',sdk]
    with tempfile.TemporaryDirectory(prefix='rpcs3-report-format-') as tmp:
        unit=Path(tmp)/'format.cpp';unit.write_text(code);exe=Path(tmp)/'format'
        includes=['-I'+str(root/'rpcs3') for root in (source,renderer,cpu)]
        subprocess.run(compiler+flags+includes+[str(unit),'-o',str(exe)],check=True)
        run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30,
            env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'))
        if run.returncode:raise RuntimeError((run.returncode,run.stdout,run.stderr))
        sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
        support={'ios/IOSFrameTrace.h':sha(source/'rpcs3/ios/IOSFrameTrace.h'),
                 'ios/IOSRendererCausality.h':sha(renderer/'rpcs3/ios/IOSRendererCausality.h'),
                 'ios/IOSSignalTrace.h':sha(cpu/'rpcs3/ios/IOSSignalTrace.h')}
        report={'passed':True,'host':platform.platform(),'compiler':subprocess.check_output(compiler+['--version'],text=True).splitlines()[0],
            'compilerFlags':flags,'sanitizer':a.sanitizer,'sourceSHA256':sha(actual),'adapterSHA256':sha(adapter),
            'harnessSHA256':hashlib.sha256(code.encode()).hexdigest(),'supportSHA256':support,'productionReportersExtractedVerbatim':True,
            'logBackend':'host snprintf adapter, production fmt/log sink not executed','fullCoreBuilt':False,
            'results':json.loads(run.stdout)}
        a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))
if __name__=='__main__':main()

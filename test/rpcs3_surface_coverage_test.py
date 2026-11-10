#!/usr/bin/env python3
"""Execute real surface overlap elimination and row coverage before/after.

Surface geometry and invalidation are explicit host boundaries. No GPU/iPhone
performance is inferred from the bitmap timing or storage measurements.
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
from rpcs3_texture_address_index_test import braced
from rpcs3_texture_exact_index_test import stripped

ROOT=Path(__file__).resolve().parents[1]
SOURCE='rpcs3/Emu/RSX/Common/surface_store.h'
RANGE='Utilities/address_range.h'
ADAPTER=ROOT/'test/native/rpcs3_surface_coverage.inc'
sha=lambda p:hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()

def harness(source,baseline):
    old=(baseline/SOURCE).read_text();new=(source/SOURCE).read_text()
    sig='void remove_duplicates_fallback_impl('
    old_fn=braced(old,sig);new_fn=braced(new,sig)
    assert old.replace(old_fn,'@FUNCTION@')==new.replace(new_fn,'@FUNCTION@')
    # Exact reference code remains the desktop branch of each changed block.
    desktop=new_fn
    while '#ifdef RPCS3_IOS' in desktop:
        a=desktop.index('#ifdef RPCS3_IOS');b=desktop.index('#else',a);c=desktop.index('#endif',b)
        desktop=desktop[:a]+desktop[b+len('#else\n'):c]+desktop[c+len('#endif\n'):]
    assert desktop==old_fn
    assert sha(source/RANGE)==sha(baseline/RANGE)
    code=ADAPTER.read_text().replace('@RANGE@',stripped(source/RANGE));versions=''
    for name,body,ios in [('before',old_fn,False),('after',new_fn,True),('desktop',new_fn,False)]:
        if ios:versions+='#define RPCS3_IOS\n'
        versions+='struct '+name+' : Boundary {\n'+body+'\n'
        a=body.index('constexpr u32 overrun_cookie_value');b=body.index('for (auto it = sections.crbegin()',a)
        helper=body[a:b].replace('u32 removed_count = 0;','[[maybe_unused]] u32 removed_count = 0;')
        versions+='Result rows(const address_range32& range,const std::vector<std::pair<u32,u32>>& spans){\n'+helper
        versions+='Result result;result.storageBytes=marker.size()*sizeof(marker[0]);for(auto [start,len]:spans)result.changed.push_back(compare_and_tag_row(start,len));\n'
        versions+='for(u32 i=0;i<range.length();++i){result.covered.push_back('
        versions+=('((marker[i/64]>>(i%64))&1)!=0' if ios else 'marker[i]!=0')+');}\nreturn result;}\n};\n'
        if ios:versions+='#undef RPCS3_IOS\n'
    return code.replace('@VERSIONS@',versions)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--compiler',default=os.environ.get('CXX','c++'))
    p.add_argument('--sanitizer',choices=['address,undefined']);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    source=a.source.resolve();baseline=a.baseline.resolve();code=harness(source,baseline)
    flags=['-std=c++20','-Wall','-Wextra','-Werror','-UNDEBUG','-g','-O1' if a.sanitizer else '-O3']
    if a.sanitizer:
        flags+=['-fsanitize='+a.sanitizer,'-fno-omit-frame-pointer']
        if platform.system()=='Linux':flags+=['-fno-pie','-no-pie']
    if sdk:=os.environ.get('HOST_MACOS_SDK'):flags+=['-isysroot',sdk]
    compiler=shlex.split(a.compiler)
    with tempfile.TemporaryDirectory(prefix='rpcs3-surface-coverage-') as tmp:
        cpp=Path(tmp)/'test.cpp';exe=Path(tmp)/'test';cpp.write_text(code)
        subprocess.run([*compiler,*flags,str(cpp),'-o',str(exe)],check=True)
        run=subprocess.run([str(exe)]+([] if a.sanitizer else ['benchmark']),text=True,capture_output=True,timeout=120,
            env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'))
        assert run.returncode==0,(run.returncode,run.stdout,run.stderr)
        result=json.loads(run.stdout)
    report=dict(passed=True,sourceSHA256={p:sha(source/p) for p in [SOURCE,RANGE]},baselineSHA256={p:sha(baseline/p) for p in [SOURCE,RANGE]},
        harnessSHA256=hashlib.sha256(code.encode()).hexdigest(),adapterSHA256=sha(ADAPTER),compiler=subprocess.check_output([*compiler,'--version'],text=True).splitlines()[0],
        compilerFlags=flags,host=platform.machine(),results=result,physicalDeviceTested=False,gameplayMeasured=False)
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()

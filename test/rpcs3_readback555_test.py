#!/usr/bin/env python3
"""Test fixed readback observations and prove transfer/synchronization code unchanged."""
import argparse, hashlib, json, os, re, shlex, subprocess, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
PREIMAGES = {
 'rpcs3/Emu/RSX/Common/texture_cache.h': '46ec6cc856397318e584f5588c4ff579690840a971d7fa166121c00fa6caeb1b',
 'rpcs3/Emu/RSX/VK/VKPresent.cpp': 'dadac00185ac425ad18039f33aa8d8338ecec0c08f2bfcdb0a540480bbb25046',
}
def sha(data): return hashlib.sha256(data).hexdigest()
def strip_observations(data):
    include=b'// CELL555_READBACK_INCLUDE\n#include "ios/IOSReadbackProfile.h"\n'
    # Standalone include block in texture_cache.h versus the existing iOS block
    # in VKPresent.cpp. Preserve every pre-existing byte, including blank lines.
    if b'\n#ifdef RPCS3_IOS\n'+include+b'#endif\n' in data:
        data=data.replace(b'\n#ifdef RPCS3_IOS\n'+include+b'#endif\n',b'',1)
    else:
        assert data.count(include)==1
        data=data.replace(include,b'',1)
    batch=rb'#ifdef RPCS3_IOS\n\t+// CELL555_READBACK_BATCH:(?:(?!#endif).)*#endif\n\n'
    data=re.sub(batch,b'',data,flags=re.S)
    origin=rb'#ifdef RPCS3_IOS\n\t+// CELL555_READBACK_ORIGIN\n(?:(?!#endif).)*#endif\n'
    return re.sub(origin,b'',data,flags=re.S)
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('--report',type=Path)
    args=parser.parse_args();source=args.source.resolve()
    controls={}
    for path,expected in PREIMAGES.items():
        actual=(source/path).read_bytes()
        restored=strip_observations(actual)
        assert sha(restored)==expected,(path,sha(restored))
        controls[path]=dict(beforeSHA256=expected,afterSHA256=sha(actual),behaviorBytesUnchanged=True)
    common=(source/'rpcs3/Emu/RSX/Common/texture_cache.h').read_text()
    present=(source/'rpcs3/Emu/RSX/VK/VKPresent.cpp').read_text()
    for name in ('texture_cpu','blit_source_cpu','blit_destination_dma'):
        assert common.count('readback::Origin::'+name+')')==1,name
    assert present.count('readback::Origin::presentation_cpu)')==1
    assert common.count('const rpcs3::ios::readback::BatchScope')==1
    performance=(source/'rpcs3/ios/RPCS3IOSPerformance.cpp').read_text()
    for marker in ('COREPROF READBACK555','parent_includes_gpu_fence=1','bytes_scope=confirmed_requested_not_dma_payload','window_boundary_approximate=1'):
        assert marker in performance,marker
    cxx=shlex.split(os.environ.get('CXX','c++'))
    if sdk:=os.environ.get('HOST_MACOS_SDK'):cxx+=['-isysroot',sdk]
    results={}
    with tempfile.TemporaryDirectory(prefix='rpcs3-readback555-') as td:
        work=Path(td);(work/'util').mkdir()
        (work/'util/tsc.hpp').write_text('#pragma once\n#include <cstdint>\nnamespace utils { inline thread_local std::uint64_t ticks=0, clock_reads=0; inline std::uint64_t get_tsc() { ++clock_reads; return ticks; } }\n')
        for mode,sanitizer in (('addressUndefined','address,undefined'),('thread','thread')):
            exe=work/mode
            subprocess.run(cxx+['-std=c++20','-O1','-g','-Wall','-Wextra','-Werror','-fno-exceptions','-pthread','-fno-omit-frame-pointer','-fsanitize='+sanitizer,'-I'+str(work),'-I'+str(source/'rpcs3'),'-x','c++',str(ROOT/'test/native/rpcs3_readback555.inc'),'-o',str(exe)],check=True)
            run=subprocess.run([str(exe)],capture_output=True,text=True,check=True,timeout=60,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1',TSAN_OPTIONS='halt_on_error=1'))
            results[mode]=json.loads(run.stdout);assert results[mode]['passed'] is True
    inputs=['test/rpcs3_readback555_test.py','test/native/rpcs3_readback555.inc']
    report=dict(passed=True,sourcePreimages=controls,scenarios=results,productionHeaderSHA256=sha((source/'rpcs3/ios/IOSReadbackProfile.h').read_bytes()),inputs={p:sha((ROOT/p).read_bytes()) for p in inputs},physicalDeviceTested=False,gameplayMeasured=False,scope='Observation correctness only; no GPU synchronization, data copies, buffer lifetime or rendering policy changed.')
    output=json.dumps(report,indent=2)+'\n'
    if args.report:args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(output)
    print(output,end='')
if __name__=='__main__':main()

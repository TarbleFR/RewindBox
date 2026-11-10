#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import tempfile
from run_late_snr import braced

HERE=Path(__file__).resolve().parent
REVIEW=HERE.parent
sha=lambda b:hashlib.sha256(b).hexdigest()

def generate_rsx(tree,baseline):
    code=(HERE/'signal_rsx.cpp.in').read_text()
    sources={}
    for label,path,sync in [('BEFORE',baseline/'rpcs3/Emu/RSX/NV47/HW/nv406e.cpp',baseline/'rpcs3/Emu/RSX/NV47/HW/nv47_sync.hpp'),
                            ('AFTER',tree/'rpcs3/Emu/RSX/NV47/HW/nv406e.cpp',tree/'rpcs3/Emu/RSX/NV47/HW/nv47_sync.hpp')]:
        cpp=path.read_text();header=sync.read_text()
        for token,body in [('ACQUIRE',braced(cpp,'void semaphore_acquire(')),('RELEASE',braced(cpp,'void semaphore_release(')),
                           ('SYNC',braced(header,'template <bool FlushDMA, bool FlushPipe>'))]:
            code=code.replace('@'+label+'_'+token+'@',body)
            sources[label+'_'+token]=sha(body.encode())
    assert '@' not in code
    return code,sources

def generate_dma(tree,baseline,repo,mode):
    fixtures=repo/'test/rpcs3_continuation/cpu'
    header='#include "ios/IOSSignalTrace.h"\n#include "ios/IOSDMACopy.h"\n#include <cassert>\nnamespace trace=rpcs3::ios::signal_trace;\n'
    if mode=='dma':
        code=(fixtures/'dma_mmio_prefix.cpp').read_text()
        code=code.replace('T v{};operator T()const{return v;}', 'T v{};T load()const{return v;}operator T()const{return v;}')
        code=code.replace('void __movsb(u8*d,const u8*s,usz n){std::memcpy(d,s,n);}',
            'static bool reset_on_copy=false;void __movsb(u8*d,const u8*s,usz n){std::memcpy(d,s,n);if(reset_on_copy)trace::reset(trace::current_session.load()+1,true);}')
        code=code.replace('u32 last_faddr=0,pc=0,raddr=0;', 'u32 id=0x2000001;bool ios_dma_copy_specialization=false;u32 last_faddr=0,pc=0x12340,raddr=0;')
        code=code.replace('namespace vm{','static bool fail_ranges=false;\nnamespace vm{',1)
        code=code.replace('(void)Size;++range_calls;','(void)Size;++range_calls;if(fail_ranges)throw access_fault("injected failed range lock");',1)
        code+='\ntemplate<class T>struct be_t{T raw;operator T()const{return __builtin_bswap32(raw);}};\nnamespace vm{template<class T>T& _ref(u32 address){return *_ptr<T>(address);}}\nu64 get_system_time(){return 100;}\n'
        signatures=['void spu_thread::do_dma_transfer(']
        renames=[('void spu_thread::do_dma_transfer(', 'void {label}_dma_transfer(')]
    else:
        code=(fixtures/'dma_list_harness_prefix.cpp').read_text()
        # This trace-only list harness does not execute MFC command decoding.
        # Keep the historical shared fixture immutable and omit its unused
        # command constants only from this generated translation unit.
        unused='constexpr u8 MFC_BARRIER_MASK=1,MFC_FENCE_MASK=2,MFC_LIST_MASK=4;'
        assert code.count(unused)==1
        code=code.replace(unused, '')
        code=code.replace('constexpr u32 MFC_TAG_UPDATE_IMMEDIATE=0,MFC_TAG_UPDATE_ANY=1,MFC_TAG_UPDATE_ALL=2,SPU_EVENT_SN=2;', 'constexpr u32 SPU_EVENT_SN=2;')
        code=code.replace('u32 ch_stall_mask=0,events=0;', 'u32 id=0x2000001;u32 ch_stall_mask=0,events=0;')
        code+='\ntemplate<class T>struct atomic_t{T value;T load()const{return value;}};\nnamespace vm{template<class T>T& _ref(u32 address){return *_ptr<T>(address);}}\n'
        signatures=['bool spu_thread::do_list_transfer(']
        renames=[('spu_thread::','spu_{label}::')]
    sources={}
    for label,source in [('old',(baseline/'rpcs3/Emu/Cell/SPUThread.cpp').read_text()),('new',(tree/'rpcs3/Emu/Cell/SPUThread.cpp').read_text())]:
        for signature in signatures:
            body=braced(source,signature);sources[label+'_'+signature]=sha(body.encode())
            for old,new in renames:body=body.replace(old,new.format(label=label))
            code+='\n'+body+'\n'
    code+='\n'+(HERE/f'signal_{mode}_suffix.cpp').read_text()
    return header+code,sources

def main():
    p=argparse.ArgumentParser();p.add_argument('tree',type=Path);p.add_argument('--baseline',type=Path,default=REVIEW/'baseline');p.add_argument('--repo',type=Path,default=REVIEW.parent/'device597-work');p.add_argument('--sanitizer',choices=['address,undefined','thread']);p.add_argument('--compiler',default=os.environ.get('CXX','c++'));p.add_argument('--report',type=Path,required=True);p.add_argument('--mode',choices=['helper','rsx','dma','list'],required=True);a=p.parse_args()
    compiler=shlex.split(a.compiler)
    assert compiler, "empty compiler command"
    tree=a.tree.resolve()
    def generate():
        if a.mode=='rsx':return generate_rsx(tree,a.baseline)
        if a.mode in ('dma','list'):return generate_dma(tree,a.baseline,a.repo,a.mode)
        return (HERE/'signal_trace_test.cpp').read_text(),{}
    code,sources=generate()
    trace_hash=sha((tree/'rpcs3/ios/IOSSignalTrace.h').read_bytes())
    flags=['-std=c++20','-Wall','-Wextra','-Werror','-UNDEBUG','-pthread','-g','-O1' if a.sanitizer else '-O3','-DRPCS3_IOS','-I',str(tree/'rpcs3')]
    if sdk:=os.environ.get('HOST_MACOS_SDK'):flags+=['-isysroot',sdk]
    if a.sanitizer:
        flags+=['-fsanitize='+a.sanitizer,'-fno-omit-frame-pointer']
        if platform.system()=='Linux':flags+=['-fno-pie','-no-pie']
    with tempfile.TemporaryDirectory(prefix='signal-trace-')as tmp:
        cpp,exe=Path(tmp)/'test.cpp',Path(tmp)/'test';cpp.write_text(code)
        subprocess.run([*compiler,*flags,str(cpp),'-o',str(exe)],check=True)
        run=subprocess.run([str(exe)],text=True,capture_output=True,timeout=30,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1'))
        assert run.returncode==0 and not run.stderr,(run.returncode,run.stdout,run.stderr)
    assert (code,sources)==generate()
    assert trace_hash==sha((tree/'rpcs3/ios/IOSSignalTrace.h').read_bytes())
    report=dict(passed=True,mode=a.mode,sanitizer=a.sanitizer,results=json.loads(run.stdout),sourceBodies=sources,
        traceHeaderSHA256=sha((tree/'rpcs3/ios/IOSSignalTrace.h').read_bytes()),programSHA256=sha(code.encode()),
        scriptSHA256=sha(Path(__file__).read_bytes()),compiler=subprocess.check_output([*compiler,'--version'],text=True).splitlines()[0],flags=flags,host=platform.machine(),
        physicalDeviceTested=False,gameplayMeasured=False,platformAtomicWaitBackendExecuted=False,
        scope='Real bounded trace header; complete acquire/release/write_gcm_label bodies for rsx mode; complete do_dma_transfer/do_list_transfer for dma/list modes. Guest memory, atomic reservation/locks, GPU backend, log formatting, clock and wait pump are explicit host adapters.')
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()

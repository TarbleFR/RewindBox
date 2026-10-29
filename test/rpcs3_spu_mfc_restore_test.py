#!/usr/bin/env python3
"""Exercise restored MFC work through real serialization, queue and channel bodies.

The host serializer, CPU scheduling flags and DMA/list effects are explicit
adapters. This is not a complete savestate-format, LLVM or device test.
"""
import argparse,hashlib,json,os,platform,shlex,subprocess,tempfile
from pathlib import Path
import rpcs3_spu_mfc_runtime_test as mfc
from rpcs3_texture_address_index_test import braced
ROOT=Path(__file__).resolve().parents[1]
ADAPTER=ROOT/'test/native/rpcs3_spu_mfc_restore.inc'
INPUTS=[mfc.CPP,mfc.HEADER,mfc.MFC,mfc.CONFIG,'rpcs3/Emu/CPU/CPUThread.h']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def harness(source,baseline):
    bodies={label:(tree/mfc.CPP).read_text() for label,tree in [('before',baseline),('after',source)]}
    ctor='spu_thread::spu_thread(utils::serial& ar, lv2_spu_group* group)'
    fragments={}
    for label,body in bodies.items():
        text=braced(body,ctor)
        fragments[label]=text[text.index('\tserialize_common(ar);'):text.index('\traddr = ::narrow<u32>')]
    # A separately tested full-queue IRQ fix changes process_mfc_cmd. This
    # restoration harness does not consume that method; all consumed bodies
    # remain exact and are compared below.
    scoped=[]
    for label,body in bodies.items():
        process=braced(body,'bool spu_thread::process_mfc_cmd()')
        scoped.append(body.replace(fragments[label],'@RESTORE@',1).replace(process,'@PROCESS_MFC@',1))
    assert scoped[0]==scoped[1]
    for sig in [*mfc.METHODS,'void spu_thread::serialize_common(','auto read_channel =']:
        assert braced(bodies['before'],sig)==braced(bodies['after'],sig)
    assert 'atomic_bs_t<cpu_flag> state{cpu_flag::stop + cpu_flag::wait};' in (source/'rpcs3/Emu/CPU/CPUThread.h').read_text()
    code=mfc.ADAPTER.read_text().split('@BEFORE@')[0]
    code=code.replace('#include <vector>','#include <vector>\n#include <span>\n#include <type_traits>\n#include <limits>')
    mfctext=(source/mfc.MFC).read_text()
    code=code.replace('@MFC@','\n'.join(braced(mfctext,s)+';' for s in ['enum MFC : u8','enum mfc_tag_update : u32','struct alignas(16) spu_mfc_cmd']))
    extra=ADAPTER.read_text()
    helpers,extra=extra.split('// @STATE_MEMBERS@\n')
    members,extra=extra.split('// @DRIVER@\n')
    code=code.replace('struct State;','struct State;\n'+helpers)
    code=code.replace('u32 value{}, count{};','union { struct { u32 value, count; }; u64 data{}; };\n    u32 get_count()const{return count;}\n    template<class T> s64 pop_wait(T&){if(!count)return -1;count=0;return value;}')
    code=code.replace('struct Value { bool count{}; } value;','struct Value { bool count{}; u64 all{}; } value;\n    Value& raw(){return value;}')
    code=code.replace('struct State {','using spu_channel=Channel;\nstruct State {\n'+members)
    for label,body in bodies.items():
        code+='namespace '+label+' { struct spu_thread:State { bool do_mfc(bool can_escape=true,bool must_finish=true);u32 get_mfc_completed()const;bool check_mfc_interrupts(u32);void serialize_common(utils::serial&);\n'
        code+='void restore(utils::serial& ar){'+fragments[label]+'}\n'
        code+='s64 read_tag(){'+braced(body,'auto read_channel =')+';return read_channel(ch_tag_stat);}\n};\n'
        code+='\n'.join(braced(body,s) for s in [*mfc.METHODS,'void spu_thread::serialize_common('])+'}\n'
    return code+extra

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--compiler',default=os.environ.get('CXX','c++'));p.add_argument('--sanitizer',choices=['address,undefined']);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    code=harness(a.source,a.baseline)
    flags=['-std=c++20','-Wall','-Wextra','-Werror','-UNDEBUG','-g','-O1' if a.sanitizer else '-O3']
    if a.sanitizer:
        flags+=['-fsanitize='+a.sanitizer,'-fno-omit-frame-pointer']
        if platform.system()=='Linux':flags+=['-fno-pie','-no-pie']
    if sdk:=os.environ.get('HOST_MACOS_SDK'):flags+=['-isysroot',sdk]
    compiler=shlex.split(a.compiler)
    with tempfile.TemporaryDirectory(prefix='rpcs3-mfc-restore-') as t:
        cpp=Path(t)/'main.cpp';exe=Path(t)/'test';cpp.write_text(code)
        subprocess.run(compiler+flags+[str(cpp),'-o',str(exe)],check=True)
        result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=60,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1'))
        assert result.returncode==0 and not result.stderr,(result.returncode,result.stdout,result.stderr)
        data=json.loads(result.stdout)
    proof=dict(passed=True,results=data,sourceSHA256={s:sha(a.source/s) for s in INPUTS},baselineSHA256={s:sha(a.baseline/s) for s in INPUTS},harnessSHA256=hashlib.sha256(code.encode()).hexdigest(),adapterSHA256=sha(ADAPTER),compilerFlags=flags,compiler=subprocess.check_output(compiler+['--version'],text=True).splitlines()[0],host=platform.machine(),physicalDeviceTested=False,gameplayMeasured=False,realDMATransfersTested=False,concurrentMemoryOrderingTested=False,completeSavestateFormatTested=False)
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof,indent=2))
if __name__=='__main__':main()

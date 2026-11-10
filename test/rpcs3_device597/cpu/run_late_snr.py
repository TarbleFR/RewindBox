#!/usr/bin/env python3
"""Native production extraction for late SNR while MFC_Cmd is blocked.

The MFC drain, event publication, channel implementation, IRQ dispatch and
thread notification/wait construction are extracted unmodified. Only the
process_mfc_cmd prefix is reached; its remaining command dispatcher is an
explicit acceptance counter because no command is accepted in the race.
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

HERE=Path(__file__).resolve().parent
REVIEW=HERE.parent
CPP='rpcs3/Emu/Cell/SPUThread.cpp'
HEADER='rpcs3/Emu/Cell/SPUThread.h'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def braced(source,signature):
    begin=source.index(signature)
    brace=source.index('{',begin)
    depth=1
    pos=brace+1
    while depth:
        if source[pos]=='{':depth+=1
        elif source[pos]=='}':depth-=1
        pos+=1
    return source[begin:pos]

def prefix(source):
    full=braced(source,'bool spu_thread::process_mfc_cmd()')
    return full[full.index('{')+1:full.index('\n\tspu::scheduler::concurrent_execution_watchdog')]

def harness(tree,baseline=None,support=None):
    baseline=baseline or REVIEW/'baseline'
    support=support or REVIEW/'support'
    before=(baseline/CPP).read_text()
    after=(tree/CPP).read_text()
    before_prefix,after_prefix=prefix(before),prefix(after)
    restored=after
    for signature in ['bool spu_thread::process_mfc_cmd()', 'void spu_thread::do_dma_transfer(', 'bool spu_thread::do_list_transfer(']:
        restored=restored.replace(braced(after,signature),braced(before,signature),1)
    helper=braced(after,'static void ios_publish_mfc_snapshot(')
    helper_start=restored.index('#ifdef RPCS3_IOS\n// Called only by the SPU owner')
    helper_end=restored.index('\n#endif\n\n',helper_start)+len('\n#endif\n\n')
    restored=restored[:helper_start]+restored[helper_end:]
    restored=restored.replace('#include "ios/IOSSignalTrace.h"\n','',1)
    assert restored==before
    methods=['bool spu_thread::do_mfc(', 'u32 spu_thread::get_mfc_completed() const',
             'bool spu_thread::check_mfc_interrupts(', 'void spu_thread::push_snr(',
             'void spu_thread::set_events(']
    for method in methods:
        assert braced(before,method)==braced(after,method)
    header=(tree/HEADER).read_text()
    mfc_path=baseline/'rpcs3/Emu/Cell/MFC.h'
    thread_path=baseline/'Utilities/Thread.h'
    if not mfc_path.is_file():mfc_path=support/'MFC.h'
    if not thread_path.is_file():thread_path=support/'Utilities/Thread.h'
    mfc=mfc_path.read_text()
    thread_header=thread_path.read_text()
    thread_cpp=(tree/'Utilities/Thread.cpp').read_text()
    code=(HERE/'late_snr.cpp.in').read_text()
    class_body=code.split('// @CLASS_BEGIN@\n')[1].split('// @CLASS_END@\n')[0]
    begin=code.index('// @CLASS_BEGIN@\n')
    end=code.index('// @CLASS_END@\n')+len('// @CLASS_END@\n')
    code=code[:begin]+code[end:]
    versions=''
    for name,source in [('before',before),('after',after)]:
        versions+='namespace '+name+' {\n'+class_body+'\n'+(helper+'\n' if name=='after' else '')
        versions+='\n'.join(braced(source,method) for method in methods)
        versions+='\nbool spu_thread::process_prefix(){'+prefix(source)+'\n++accepted;return true;}\n}\n'
    replacements={
        '@MFC@':'\n'.join(braced(mfc,sig)+';' for sig in ['enum MFC : u8','enum mfc_tag_update : u32','struct alignas(16) spu_mfc_cmd']),
        '@CHANNEL@':braced(header,'struct spu_channel_op_state\n')+';\n'+braced(header,'struct alignas(16) spu_channel\n')+';',
        '@NOTIFY@':braced(thread_cpp,'void thread_base::notify()'),
        '@WAIT_CUSTOM@':braced(thread_header,'template <uint Max, typename Func>'),
        '@WAIT_ON@':braced(thread_header,'template <typename T, typename U>\n\tstatic inline void wait_on('),
        '@VERSIONS@':versions,
    }
    for token,value in replacements.items():
        assert code.count(token)==1,token
        code=code.replace(token,value)
    assert '@' not in code
    return '#include "ios/IOSSignalTrace.h"\n'+code,dict(fullExtractedMethods=methods+['spu_channel','thread_base::notify','thread_ctrl::wait_on_custom','thread_ctrl::wait_on','ios_publish_mfc_snapshot'],
                     beforePrefixSHA256=sha(before_prefix.encode()),afterPrefixSHA256=sha(after_prefix.encode()))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tree',type=Path)
    parser.add_argument('--baseline',type=Path,default=REVIEW/'baseline')
    parser.add_argument('--support',type=Path,default=REVIEW/'support')
    parser.add_argument('--sanitizer',choices=['address,undefined','thread'])
    parser.add_argument('--compiler',default=os.environ.get('CXX','c++'))
    parser.add_argument('--report',required=True,type=Path)
    args=parser.parse_args()
    compiler=shlex.split(args.compiler)
    assert compiler, "empty compiler command"
    tree=args.tree.resolve()
    baseline,support=args.baseline.resolve(),args.support.resolve()
    code,scope=harness(tree,baseline,support)
    trace_hash=sha((tree/'rpcs3/ios/IOSSignalTrace.h').read_bytes())
    flags=['-std=c++20','-Wall','-Wextra','-Werror','-UNDEBUG','-g','-pthread','-O1' if args.sanitizer else '-O3','-DRPCS3_IOS','-I',str(tree/'rpcs3')]
    if sdk:=os.environ.get('HOST_MACOS_SDK'):flags+=['-isysroot',sdk]
    if args.sanitizer:
        flags+=['-fsanitize='+args.sanitizer,'-fno-omit-frame-pointer']
        if platform.system()=='Linux':flags+=['-fno-pie','-no-pie']
    with tempfile.TemporaryDirectory(prefix='rpcs3-late-snr-') as tmp:
        cpp,exe=Path(tmp)/'test.cpp',Path(tmp)/'test'
        cpp.write_text(code)
        subprocess.run([*compiler,*flags,str(cpp),'-o',str(exe)],check=True)
        run=subprocess.run([str(exe)],text=True,capture_output=True,timeout=30,
            env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1'))
        assert run.returncode==0 and not run.stderr,(run.returncode,run.stdout,run.stderr)
    assert (code,scope)==harness(tree,baseline,support)
    assert trace_hash==sha((tree/'rpcs3/ios/IOSSignalTrace.h').read_bytes())
    results=json.loads(run.stdout)
    assert results['baselineLostWakeSchedules']==4 and results['candidateInterruptDeliveries']==6
    assert results['concurrentProducerConsumerCases']==128
    report=dict(passed=True,**scope,results=results,sourceSHA256={name:sha((tree/name).read_bytes()) for name in [CPP,HEADER,'Utilities/Thread.cpp']},
        baselineSHA256=sha((baseline/CPP).read_bytes()),
        harnessSHA256=sha(code.encode()),scriptSHA256=sha(Path(__file__).read_bytes()),adapterSHA256=sha((HERE/'late_snr.cpp.in').read_bytes()),
        supportSHA256={name:sha((baseline/name if (baseline/name).is_file() else support/short).read_bytes())
                      for name,short in [('rpcs3/Emu/Cell/MFC.h','MFC.h'),('Utilities/Thread.h','Utilities/Thread.h')]},
        compiler=subprocess.check_output([*compiler,'--version'],text=True).splitlines()[0],flags=flags,host=platform.machine(),
        sanitizer=args.sanitizer,assertionsActive=True,platformAtomicWaitBackendExecuted=False,
        traceHeaderSHA256=sha((tree/'rpcs3/ios/IOSSignalTrace.h').read_bytes()),
        realDMATransfersTested=False,llvmCompiled=False,aarch64Executed=platform.machine().lower() in {'arm64','aarch64'},physicalDeviceTested=False,gameplayMeasured=False)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()

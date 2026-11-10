#!/usr/bin/env python3
"""Exercise final MFC enqueue CFG and the real full-queue drain/retry bodies.

Builds on the independently recorded tag-stage regression, authenticates that
intermediate source and reuses its driver in a new execution. The LLVM builder
is evaluated with explicit block reachability and bounded memory; this is not
a native LLVM/AArch64 compilation. DMA, waits and CPU flags are host adapters.
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
import rpcs3_spu_mfc_llvm_tag_test as tag

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT/'test/native/rpcs3_spu_mfc_full_queue.inc'
sha = lambda value: hashlib.sha256(value).hexdigest()


def guard(source):
    text = (source/tag.LLVM).read_text()
    begin = text.index('\n\t\t\t\t// A full queue is a blocking channel write')
    end = text.index('\t\t\t\tconst auto off0', begin)
    return text[begin:end]


def harness(source, baseline):
    cpp = (source/tag.runtime.CPP).read_text()
    llvm = (source/tag.LLVM).read_text()
    intermediate = llvm.replace(guard(source), '', 1)
    evidence = ROOT/'docs/evidence/rpcs3-deep-audit-20261029'
    reports = [json.loads((evidence/f'gow3-mfc-llvm-{mode}.json').read_text()) for mode in ('plain','asan')]
    assert all(report['sourceSHA256'][tag.LLVM] == sha(intermediate.encode()) for report in reports)
    with tempfile.TemporaryDirectory(prefix='mfc-authenticated-tag-stage-') as temp:
        stage = Path(temp)
        for name in (tag.LLVM, tag.runtime.CPP, tag.runtime.MFC):
            path = stage/name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(intermediate if name == tag.LLVM else (source/name).read_text())
        code = tag.harness(stage, baseline)
        assert all(report['harnessSHA256'] == sha(code.encode()) for report in reports)
        old_after = tag.enqueue(stage)
    code = code.replace(old_after, tag.enqueue(source), 1)
    declaration = 'bool do_mfc(bool can_escape = true, bool must_finish = true);'
    assert declaration in (source/tag.runtime.HEADER).read_text()
    code = code.replace('bool do_mfc(bool can_escape, bool must_finish);', declaration, 1)
    # Clock/DMA/list adapters remain the existing ones; add only stop/again and
    # deterministic wait delivery needed by the actual full-queue loop.
    support = '''
#include <functional>
#include <set>
constexpr u32 MFC_Cmd=21;
enum class cpu_flag { wait, again };
struct Flags {
 u32 bits{};
 u32 add_fetch(cpu_flag bit) { bits |= 1u<<u32(bit); return bits; }
 bool operator&(cpu_flag bit) const { return (bits & (1u<<u32(bit)))!=0; }
};
inline bool is_stopped(u32 value) { return (value&0x80000000u)!=0; }
std::function<void()> wait_action;
u64 wait_calls{};
namespace thread_ctrl { void wait_on(Flags&,u32) { ++wait_calls; assert(wait_action); wait_action(); } }
'''
    code = code.replace('struct State;', support+'\nstruct State;', 1)
    code = code.replace('struct State {', '''struct State {
    Flags state;
    bool stopped{};
    u32 stop_checks{};
    bool test_stopped() { ++stop_checks; return stopped; }
''', 1)
    process = braced(cpp, 'bool spu_thread::process_mfc_cmd()')
    prefix = process[process.index('{')+1:process.index('\n\tspu::scheduler::concurrent_execution_watchdog')]
    assert prefix == braced((baseline/tag.runtime.CPP).read_text(), 'bool spu_thread::process_mfc_cmd()').split('{',1)[1].split('\n\tspu::scheduler::concurrent_execution_watchdog',1)[0]
    channel = cpp[cpp.index('bool spu_thread::set_ch_value('):]
    command = braced(channel,'case MFC_Cmd:')
    methods = '\n bool process_mfc_cmd() {'+prefix+'\n return reference_enqueue(); }\n'
    methods += 'bool set_ch_value(u32 ch,u32 value) { switch(ch) { '+command+' default: throw Escaped{}; } }\n'
    code = code.replace('spu_mfc_cmd ch_mfc_cmd{};', 'spu_mfc_cmd ch_mfc_cmd{};'+methods, 1)
    helpers = '\nusing spu_thread=production::spu_thread;\n'
    helpers += braced(llvm,'static void exec_wrch_result(')+'\n'+braced(llvm,'static void exec_wrch(')+'\n'
    code = code.replace('#include <memory>', helpers+'\n#include <memory>',1)
    code = code.replace('struct Builder {', '''namespace llvm {
struct BasicBlock { static u64 Create(int,const char*,int) { static u64 id=2; return id++; } };
}
struct Builder {
    std::set<u64> reachable{0}; bool executing=true;
''', 1)
    code = code.replace('u64 bits{}; std::memcpy(&bits,checked(memory,width),width);',
                        'u64 bits{}; if(executing)std::memcpy(&bits,checked(memory,width),width);')
    code = code.replace('std::memcpy(checked(memory,input->width),&input->bits,input->width); ++writes;',
                        'if(!executing){return;} std::memcpy(checked(memory,input->width),&input->bits,input->width); ++writes;')
    code = code.replace('void SetInsertPoint(int) {}\n    void CreateBr(int) {}',
        'void SetInsertPoint(u64 block) { executing=reachable.contains(block); }\n'
        'void CreateBr(u64 block) { if(executing)reachable.insert(block); }\n'
        'void CreateCondBr(Value* condition,u64 yes,u64 no,int) { if(executing)reachable.insert(condition->bits?yes:no); }')
    code = code.replace('int fail{},next{};', '''
    int fail=0,next=1,m_context{},m_function{},m_md_likely{};
    Scalar val;
    ::spu_thread* thread{};
    u32 gpr_fences{},helper_calls{};
    void update_pc() { if(storage.executing)thread->pc=0x1240; }
    void ensure_gpr_stores() { ++gpr_fences; }
    void call(const char*,void(*function)(::spu_thread*,u32,u32),Memory,Value* ch,Value* command) {
        if(!storage.executing)return;
        assert(thread->pc==0x1240 && gpr_fences==1);
        ++helper_calls;active=thread;
        function(thread,static_cast<u32>(ch->bits),static_cast<u32>(command->bits));
    }
''',1)
    code = code.replace('tag.value=storage.value(desired_tag,1);',
        'thread=static_cast<::spu_thread*>(&state); val.value=storage.value(cmd,4);\n'
        '        thread->ch_mfc_cmd={cmd,desired_tag,16,0x40,0x60300510,0};\n'
        '        tag.value=storage.value(desired_tag,1);',1)
    code = code.replace('int main() {','int tag_cases() {',1)
    # The old guard is exercised only in the historical baseline. Full candidate
    # behavior is tested by the appended stop/retry/wait cases.
    code = code.replace('for(bool candidate:{false,true})','for(bool candidate:{false})',1)
    assert code.endswith('\n}\n')
    code = code[:-3]+'\n    return 0;\n}\n'
    return code + ADAPTER.read_text(), dict(
        intermediateSourceSHA256=sha(intermediate.encode()),
        authenticatedTagProofs={str((evidence/f'gow3-mfc-llvm-{mode}.json').relative_to(ROOT)):sha((evidence/f'gow3-mfc-llvm-{mode}.json').read_bytes()) for mode in ('plain','asan')},
        fullQueuePrefixSHA256=sha(prefix.encode()),
        helperBodiesSHA256=sha(helpers.encode()),
        guardSHA256=sha(guard(source).encode()))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path)
    p.add_argument('--baseline',type=Path,required=True);p.add_argument('--compiler',default=os.environ.get('CXX','c++'))
    p.add_argument('--sanitizer',choices=['address,undefined']);p.add_argument('--report',type=Path,required=True)
    a=p.parse_args();source=a.source.resolve();baseline=a.baseline.resolve();program,scope=harness(source,baseline)
    compiler=shlex.split(a.compiler);flags=['-std=c++20','-g','-Wall','-Wextra','-Werror','-UNDEBUG','-O1' if a.sanitizer else '-O3']
    if a.sanitizer:
        flags+=['-fsanitize='+a.sanitizer,'-fno-omit-frame-pointer']
        if platform.system()=='Linux':flags+=['-fno-pie','-no-pie']
    if sdk:=os.environ.get('HOST_MACOS_SDK'):flags+=['-isysroot',sdk]
    with tempfile.TemporaryDirectory(prefix='rpcs3-mfc-full-') as temp:
        cpp=Path(temp)/'test.cpp';exe=Path(temp)/'test';cpp.write_text(program)
        subprocess.run([*compiler,*flags,str(cpp),'-o',str(exe)],check=True)
        run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=120,
            env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1'))
        assert run.returncode==0 and not run.stderr,(run.returncode,run.stdout,run.stderr)
        result=json.loads(run.stdout)
    assert (program,scope)==harness(source,baseline)
    report=dict(passed=True,assertionsActive=True,**scope,results=result,
        sourceSHA256={name:sha((source/name).read_bytes()) for name in (tag.LLVM,tag.runtime.MFC)},
        runtimeBodySHA256={k:sha(v.encode()) for k,v in tag.bodies(source).items()},
        harnessSHA256=sha(program.encode()),scriptSHA256=sha(Path(__file__).read_bytes()),adapterSHA256=sha(ADAPTER.read_bytes()),
        compiler=subprocess.check_output([*compiler,'--version'],text=True).splitlines()[0],compilerFlags=flags,
        host=platform.machine(),sanitizer=a.sanitizer,llvmCompiled=False,aarch64Executed=False,physicalDeviceTested=False,
        gameplayMeasured=False,realDMATransfersTested=False,concurrentMemoryOrderingTested=False,leakSanitizer=False,scope=__doc__)
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()

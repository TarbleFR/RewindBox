#!/usr/bin/env python3
"""Verify MFC full-queue interrupts retry the unaccepted WRCH instruction.

Authenticates the preceding tag and full-queue proof stages without rerunning
their binaries, then exercises the final emitted CFG and real drain/interrupt/
IRET bodies. DMA, clock, CPU flags and interrupt-handler effects are explicit
host adapters; this does not compile LLVM or execute guest machine code.
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
import rpcs3_spu_mfc_full_queue_test as full

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT/'test/native/rpcs3_spu_mfc_full_irq.inc'
INTERPRETER = 'rpcs3/Emu/Cell/SPUInterpreter.cpp'
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def prefix(tree):
    body = braced((tree/full.tag.runtime.CPP).read_text(), 'bool spu_thread::process_mfc_cmd()')
    return body[body.index('{')+1:body.index('\n\tspu::scheduler::concurrent_execution_watchdog')]


def harness(source, baseline):
    old_prefix, new_prefix = prefix(baseline), prefix(source)
    old_drain = '\t\t// Process MFC commands\n\t\tdo_mfc();'
    new_drain = '''\t\t// The new channel command has not been accepted yet. If draining
\t\t// takes an interrupt, resume this WRCH rather than the next instruction.
\t\tdo_mfc(false);
\t\tif (check_mfc_interrupts(pc))
\t\t{
\t\t\tspu_runtime::g_escape(this);
\t\t}'''
    assert old_prefix.count(old_drain) == 1
    assert new_prefix == old_prefix.replace(old_drain, new_drain, 1)
    evidence = ROOT/'docs/evidence/rpcs3-deep-audit-20261029'
    reports = [json.loads((evidence/f'gow3-mfc-full-{mode}.json').read_text()) for mode in ('plain','asan')]
    with tempfile.TemporaryDirectory(prefix='mfc-authenticated-full-stage-') as temp:
        stage = Path(temp)
        for name in (full.tag.LLVM, full.tag.runtime.CPP, full.tag.runtime.HEADER, full.tag.runtime.MFC):
            contents = (source/name).read_text()
            if name == full.tag.runtime.CPP:
                assert contents.count(new_prefix) == 1
                contents = contents.replace(new_prefix, old_prefix, 1)
            path = stage/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(contents)
        code, previous_scope = full.harness(stage, baseline)
        assert all(report['harnessSHA256'] == sha(code.encode()) for report in reports)
        assert all(report['scriptSHA256'] == sha(Path(full.__file__).read_bytes()) for report in reports)
        assert all(report['adapterSHA256'] == sha(full.ADAPTER.read_bytes()) for report in reports)
        assert all(report['fullQueuePrefixSHA256'] == sha(old_prefix.encode()) for report in reports)
    assert code.count(old_prefix) == 1
    code = code.replace(old_prefix, new_prefix, 1)
    code = code.replace('bool set_ch_value(u32 ch,u32 value)',
        'bool process_mfc_cmd_before_irq() {'+old_prefix+'\n return reference_enqueue(); }\n'
        'bool set_ch_value(u32 ch,u32 value)', 1)
    # The counter observes entry into the real barrier dispatcher, after the
    # actual full-queue prefix. It does not cause or emulate acceptance.
    code = code.replace('struct State {', 'struct State {\n    u32 accepted_commands{};', 1)
    code = code.replace('bool reference_enqueue() { switch',
        'bool reference_enqueue() { ++accepted_commands; switch', 1)
    iret = braced((source/INTERPRETER).read_text(), 'bool IRET(spu_thread& spu, spu_opcode_t op)')
    assert iret == braced((baseline/INTERPRETER).read_text(), 'bool IRET(spu_thread& spu, spu_opcode_t op)')
    unstall = braced((source/full.tag.LLVM).read_text(), 'static void exec_list_unstall(')
    assert unstall == braced((baseline/full.tag.LLVM).read_text(), 'static void exec_list_unstall(')
    irq_helpers = '''
struct spu_opcode_t {};
namespace spu_interpreter {
// The handler acknowledges the modeled event before IRET; interrupt-control
// instruction flags are not emulated. The real IRET PC assignment is executed.
void set_interrupt_status(spu_thread& spu,spu_opcode_t) { assert(!spu.interrupts_enabled); }
}
'''+iret+'\n'+unstall+'\n'
    code = code.replace('#include <memory>', irq_helpers+'\n#include <memory>', 1)
    assert code.count('interrupt.srr0==0x1244') == 1
    code = code.replace('interrupt.srr0==0x1244', 'interrupt.srr0==0x1240', 1)
    code = code.rsplit('int main(){', 1)[0] + ADAPTER.read_text()
    return code, dict(
        authenticatedFullProofs={str((evidence/f'gow3-mfc-full-{mode}.json').relative_to(ROOT)):sha((evidence/f'gow3-mfc-full-{mode}.json').read_bytes()) for mode in ('plain','asan')},
        authenticatedFullHarnessSHA256=reports[0]['harnessSHA256'],
        historicalScope=previous_scope,
        previousFullQueuePrefixSHA256=sha(old_prefix.encode()),
        fullQueuePrefixSHA256=sha(new_prefix.encode()),
        iretBodySHA256=sha(iret.encode()),
        unstallBodySHA256=sha(unstall.encode()))


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
    with tempfile.TemporaryDirectory(prefix='rpcs3-mfc-full-irq-') as temp:
        cpp=Path(temp)/'test.cpp';exe=Path(temp)/'test';cpp.write_text(program)
        subprocess.run([*compiler,*flags,str(cpp),'-o',str(exe)],check=True)
        run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=120,
            env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1'))
        assert run.returncode==0 and not run.stderr,(run.returncode,run.stdout,run.stderr)
        result=json.loads(run.stdout)
    assert (program,scope)==harness(source,baseline)
    report=dict(passed=True,assertionsActive=True,**scope,results=result,
        sourceSHA256={name:sha((source/name).read_bytes()) for name in (full.tag.LLVM,full.tag.runtime.CPP,full.tag.runtime.MFC,INTERPRETER)},
        runtimeBodySHA256={k:sha(v.encode()) for k,v in full.tag.bodies(source).items()},
        harnessSHA256=sha(program.encode()),scriptSHA256=sha(Path(__file__).read_bytes()),adapterSHA256=sha(ADAPTER.read_bytes()),
        compiler=subprocess.check_output([*compiler,'--version'],text=True).splitlines()[0],compilerFlags=flags,
        host=platform.machine(),sanitizer=a.sanitizer,llvmCompiled=False,aarch64Executed=False,physicalDeviceTested=False,
        gameplayMeasured=False,realDMATransfersTested=False,concurrentMemoryOrderingTested=False,leakSanitizer=False,
        interruptControlFlagsEmulated=False,scope=__doc__)
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()

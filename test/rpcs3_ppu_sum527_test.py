#!/usr/bin/env python3
"""Validate three production PPU sum reductions and unchanged saturation/SAT.

The old and current PPU method bodies are compiled directly with lightweight
LLVM register/DSL adapters, then their generated ARM64 code is executed. This
is a kernel test, not a complete PPU, game, iPhone, frame-time or memory test.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OPS = ('VSUM4UBS', 'VSUM4SBS', 'VSUM4SHS')
BEFORE = ROOT / 'test/fixtures/rpcs3_ppu_sum527_before.inc'

def methods(text):
    result=[]
    for name in OPS:
        start=text.index('void PPUTranslator::'+name+'(ppu_opcode_t op)\n{')
        end=text.index('{',start)+1; depth=1
        while depth:
            depth+=(text[end]=='{')-(text[end]=='}'); end+=1
        result.append(text[start:end])
    return '\n\n'.join(result)+'\n'

def llvm_config(explicit):
    choices=[explicit,os.environ.get('LLVM_CONFIG')]
    if os.environ.get('HOST_LLVM_ROOT'): choices.append(str(Path(os.environ['HOST_LLVM_ROOT'])/'bin/llvm-config'))
    if shutil.which('brew'):
        got=subprocess.run(['brew','--prefix','llvm@22'],capture_output=True,text=True,timeout=60)
        if got.returncode==0: choices.append(str(Path(got.stdout.strip())/'bin/llvm-config'))
    choices.append(shutil.which('llvm-config'))
    return next((Path(p) for p in choices if p and Path(p).is_file()),None)

def scalar_proof():
    # Exhaust every signed/unsigned pair to prove the two partial sums and the
    # SADDLP grouping; independently check the saturating-add transition edges.
    signed=lambda n,bits: n-(1<<bits) if n&(1<<(bits-1)) else n
    cases=0
    for pair in range(65536):
        lo=pair&255; hi=pair>>8
        assert signed(((pair<<8)&65535),16)>>8 == signed(lo,8)
        assert signed(pair,16)>>8 == signed(hi,8)
        assert (pair&255)+(pair>>8)==lo+hi
        for other in (0,1,127,128,255,0x7fff,0x8000,0xffff):
            packed=pair|(other<<16)
            assert signed((packed<<16)&0xffffffff,32)>>16 == signed(pair,16)
            assert signed(packed,32)>>16 == signed(other,16)
            cases+=1
    for operation in range(3):
        sums=range(1021) if operation==0 else range(-512,509) if operation==1 else range(-65536,65535)
        low,high=(0,0xffffffff) if operation==0 else (-0x80000000,0x7fffffff)
        for total_sum in sums:
            for accumulator in (low,low+1,high-1,high,max(low,min(high,high-total_sum)),max(low,min(high,low-total_sum))):
                total=accumulator+total_sum
                saturated=min(high,max(low,total))&0xffffffff
                wrapped=total&0xffffffff
                changed=saturated^wrapped
                assert bool(changed)==(total<low or total>high)
                for sticky in (0,1,0x80000000,0xffffffff):
                    assert ((sticky|changed)!=0)==(sticky!=0 or total<low or total>high)
                cases+=1
    return {'scalar_cases':cases,'exhaustive_halfword_patterns':65536,'generated_arm64_executed':False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path); p.add_argument('--llvm-config'); p.add_argument('--require-llvm',action='store_true')
    p.add_argument('--sanitize',action='store_true'); p.add_argument('--report',type=Path); p.add_argument('--artifacts',type=Path)
    a=p.parse_args(); source=a.source.resolve()
    translator=source/'rpcs3/Emu/Cell/PPUTranslator.cpp'; helper=source/'rpcs3/Emu/CPU/Backends/AArch64/CellVectorLowering.h'
    after=methods(translator.read_text()); before=BEFORE.read_text()
    assert 'RPCS3 526 production reference' in before
    for name in OPS:
        body=methods_for(after,name)
        assert 'const auto r = add_sat(s, b);' in body and 'set_sat(r ^ (s + b));' in body
        if name!='VSUM4SHS':
            assert 'if (utils::has_dotprod())' in body
            assert methods_for(before,name).split('{',1)[1].rsplit('}',1)[0].strip() in body
        else: assert '#else' in body and 'signed_halfword_pair_sum' in body
    config=llvm_config(a.llvm_config)
    if config is None:
        if a.require_llvm: raise SystemExit('FAIL LLVM22 required; no generated-code validation performed')
        report=scalar_proof(); report.update(llvm_available=False,game_or_device_tested=False,limitations='Mathematical scalar proof only; generated code untested until Apple gate')
    else:
        if platform.machine().lower() not in ('aarch64','arm64'): raise SystemExit('FAIL generated NEON execution requires an ARM64 host')
        def flags(*opts): return shlex.split(subprocess.check_output([str(config),*opts],text=True))
        version=subprocess.check_output([str(config),'--version'],text=True).strip(); assert version.startswith('22.'),version
        assert 'AArch64' in flags('--targets-built')
        compiler=Path(flags('--bindir')[0])/'clang++'
        command=[str(compiler) if compiler.is_file() else os.environ.get('CXX','clang++')]
        if sdk:=os.environ.get('HOST_MACOS_SDK'):command+=['-isysroot',sdk]
        command+=['-std=c++20','-O2','-g','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-deprecated-declarations']
        command+=[f for f in flags('--cxxflags') if not f.startswith(('-std=','-O','-g','-W','-fno-exceptions','-fno-rtti'))]
        if a.sanitize:command+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
        with tempfile.TemporaryDirectory(prefix='ppu-sum527-') as d:
            work=Path(d); (work/'rpcs3_ppu_sum527_before.inc').write_text(before); (work/'rpcs3_ppu_sum527_after.inc').write_text(after)
            binary=work/'sum527'
            command+=['-I',str(source),'-I',str(work),str(ROOT/'test/native/rpcs3_ppu_sum527.cpp'),'-o',str(binary)]
            command+=flags('--ldflags')+flags('--libs','core','mcjit','native','aarch64','support','executionengine','runtimedyld','transformutils')+flags('--system-libs')+['-Wl,-rpath,'+flags('--libdir')[0]]
            env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1');env.pop('SDKROOT',None)
            subprocess.run(command,check=True,env=env,timeout=600)
            subprocess.run([str(binary),str(work/'result.json'),str(work)],check=True,env=env,timeout=240)
            report=json.loads((work/'result.json').read_text())
            assert len(report['operations'])==3
            assert all(op['bit_exact'] and op['sticky_sat_exact'] and op['big_endian_exact'] for op in report['operations'])
            report.update(llvm_version=version,sanitized_harness=a.sanitize,generated_code_sanitized=False,production_methods='three exact bodies; native builder unchanged; LLVM register/DSL adapters; full result and sticky SAT output checked',limitations='ARM64 host generated integer kernels; no full PPU pipeline, guest instruction trace, game, iPhone frame time, opcode runtime frequency, peak memory, or cold title-cache measurement')
            if a.artifacts:
                a.artifacts.mkdir(parents=True,exist_ok=True)
                for file in work.glob('*.s'):shutil.copy2(file,a.artifacts/file.name)
    report.update(production_translator_sha256=hashlib.sha256(translator.read_bytes()).hexdigest(),production_helper_sha256=hashlib.sha256(helper.read_bytes()).hexdigest(),before_fixture_sha256=hashlib.sha256(BEFORE.read_bytes()).hexdigest())
    if a.report:a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

def methods_for(text,name):
    start=text.index('void PPUTranslator::'+name+'(ppu_opcode_t op)\n{');end=text.find('\n\nvoid ',start)
    return text[start:end if end!=-1 else len(text)]
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Compare extracted production RSX methods and real v128/backend operations.

The old SSE adapter is included only by the differential reference harness on
ARM64. No Vulkan, Metal, emulated title, cold storage or device FPS is exercised.
"""
import argparse, hashlib, json, os, platform, re, shlex, subprocess, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
PATHS = ('rpcs3/Emu/RSX/Common/BufferUtils.cpp', 'rpcs3/Emu/RSX/Common/buffer_stream.hpp',
    'rpcs3/Emu/RSX/Program/ProgramStateCache.cpp', 'rpcs3/Emu/RSX/RSXTexture.cpp',
    'rpcs3/Emu/RSX/Program/Assembler/FPToCFG.cpp')

def block(s, marker):
    start=s.index(marker); end=s.index('{',start)+1; depth=1
    while depth:
        depth += (s[end]=='{')-(s[end]=='}'); end += 1
    return s[start:end]

def sha(b): return hashlib.sha256(b).hexdigest()
LEGACY_TOKEN = re.compile(r'\b(?:_mm_\w+|__m128\w*)\b')

def arm64_fragment_legacy_names_absent(preprocessed_fragment, dependencies):
    # Inspect only preprocessed production operations, with no SDK declarations
    # in this input. Every legacy intrinsic/type token is forbidden; no aliases
    # or other declarations receive an exception.
    offending = [line for line in preprocessed_fragment.splitlines() if LEGACY_TOKEN.search(line)]
    assert not offending, 'Legacy SIMD tokens in active production fragment:\n' + '\n'.join(offending[:12])
    assert 'sse2neon' not in preprocessed_fragment.lower(), 'Active fragment references legacy SIMD adapter'
    assert 'sse2neon' not in dependencies.lower(), 'Candidate depends on legacy SIMD adapter'


def hardware():
    record={'machine':platform.machine(),'system':platform.system()}
    if platform.system()=='Darwin':
        record.update(model=subprocess.check_output(['sysctl','-n','hw.model'],text=True).strip(),
            cpu=subprocess.check_output(['sysctl','-n','machdep.cpu.brand_string'],text=True).strip())
    elif Path('/proc/cpuinfo').exists():
        record['cpu']=next((line.partition(':')[2].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')), 'unreported')
    return record
def fragment(source):
    text={p:(source/p).read_text() for p in PATHS}
    border=block(text[PATHS[3]],'u32 fragment_texture::border_color(')
    border=border.replace('u32 fragment_texture::border_color(bool apply_colorspace_remapping) const',
        'u32 border_color(u32 raw, bool apply_colorspace_remapping, u32 sext)')
    border=border.replace('const u32 raw = registers[NV4097_SET_TEXTURE_BORDER_COLOR + (m_index * 8)];','')
    border=border.replace('const u32 sext = argb_signed();','')
    constants='write_fragment_constants_to_buffer_simd' if 'write_fragment_constants_to_buffer_simd' in text[PATHS[2]] else 'write_fragment_constants_to_buffer_sse2'
    constants=block(text[PATHS[2]],'static inline void '+constants+'(').replace(constants,'write_constants')
    return (block(text[PATHS[0]],'void iota16(')+'\n'+
        block(text[PATHS[1]],'namespace utils')+'\n'+
        block(text[PATHS[4]],'inline v128 decode_instruction(')+'\n'+border+'\n'+constants)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path)
    p.add_argument('--sanitize',action='store_true');p.add_argument('--report',type=Path)
    p.add_argument('--benchmark',action='store_true')
    p.add_argument('--require-core-compiler',action='store_true');a=p.parse_args();source=a.source.resolve()
    fixture=ROOT/'test/fixtures/rpcs3_rsx_simd526.diff'
    with tempfile.TemporaryDirectory(prefix='rsx-simd526-') as d:
        work=Path(d);previous=work/'previous'
        for name in PATHS:
            target=previous/name;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text((source/name).read_text())
            assert 'sse2neon.h' not in target.read_text(), name
        subprocess.run(['git','apply','--reverse',str(fixture)],cwd=previous,check=True)
        for label,path in [('before',previous),('after',source)]:
            (work/(label+'.inc')).write_text(fragment(path))
        common=(source/'rpcs3/util/simd.hpp').read_text()
        ops=('gv_or32','gv_shl16','gv_shr16','gv_byteswap16','gv_stream','gv_bcst16','gv_bcst32','gv_add16','gv_and32','gv_gts32')
        (work/'common.inc').write_text('\n'.join(block(common,'inline '+('void' if op=='gv_stream' else 'v128')+' '+op+'(') for op in ops))
        cxx=shlex.split(os.environ.get('CXX','c++'))
        core_llvm=None
        if a.require_core_compiler:
            config=os.environ.get('LLVM_CONFIG')
            assert config, 'LLVM_CONFIG for the actual Core toolchain is required'
            core_llvm=subprocess.check_output([config,'--version'],text=True).strip()
            assert core_llvm=='22.1.8',core_llvm
            compiler_path=Path(subprocess.check_output([config,'--bindir'],text=True).strip())/'clang++'
            assert compiler_path.is_file(),compiler_path
            cxx=[str(compiler_path)]
        if sdk:=os.environ.get('HOST_MACOS_SDK'): cxx+=['-isysroot',sdk]
        if platform.machine().lower() in ('arm64','aarch64'): cxx+=['-march=armv8.4-a']
        cmd=cxx+['-std=c++20','-O3','-g','-Wall','-Wextra','-Werror','-I'+str(work),'-I'+str(source/'rpcs3'),str(ROOT/'test/native/rpcs3_rsx_simd526.cpp'),'-o',str(work/'test')]
        if a.sanitize:cmd+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
        subprocess.run(cmd,check=True)
        # Compile and inspect an independent candidate-only translation unit
        # against the real headers. SDK declarations are retained in this proof;
        # active production operation tokens are checked separately below.
        probe = r'''#include "util/types.hpp"
#include "util/v128.hpp"
#include <algorithm>
#include <span>
#include <vector>
#if defined(ARCH_ARM64)
#include <arm_neon.h>
#define RPCS3_IOS 1
#else
#include <immintrin.h>
#endif
#include "common.inc"
struct RSXFragmentProgram { const void* data; const void* get_data() const { return data; } };
namespace candidate {
#include "after.inc"
}
extern "C" __attribute__((noinline)) v128 rsx526_decode_after(v128 x) { return candidate::decode_instruction(x); }
extern "C" __attribute__((noinline)) void rsx526_stream_after(void* p, v128 x) { gv_stream(p,x); }
extern "C" __attribute__((noinline)) void rsx526_copy_after(void* p, void* q) { candidate::utils::stream_vector_from_memory<2>(p,q); }
extern "C" __attribute__((noinline)) u32 rsx526_border_after(u32 x,u32 m) { return candidate::border_color(x,true,m); }
extern "C" __attribute__((noinline)) void rsx526_constants_after(const std::span<f32>& b,const RSXFragmentProgram& p,const std::vector<u32>& o,bool s) { candidate::write_constants(b,p,o,s); }
'''
        (work/'probe.cpp').write_text(probe)
        probe_flags=cxx+['-std=c++20','-O3','-Wall','-Wextra','-Werror','-I'+str(work),'-I'+str(source/'rpcs3')]
        preprocessed=subprocess.check_output(probe_flags+['-E','-P',str(work/'probe.cpp')],text=True)
        subprocess.run(probe_flags+['-S',str(work/'probe.cpp'),'-o',str(work/'probe.s')],check=True)
        assembly=(work/'probe.s').read_text()
        macros=subprocess.check_output(cxx+['-std=c++20','-dM','-E','-x','c++','-include',str(source/'rpcs3/util/types.hpp'),'/dev/null'],text=True).splitlines()
        arm='#define ARCH_ARM64 1' in macros
        x64='#define ARCH_X64 1' in macros
        assert arm != x64, 'Real-header architecture macros must identify exactly one supported target'
        dependencies=subprocess.check_output(probe_flags+['-M',str(work/'probe.cpp')],text=True)
        assert 'sse2neon' not in dependencies.lower(), 'Candidate depends on legacy SIMD adapter'
        preprocessed_fragment=''
        full_header_legacy_lines=[]
        full_header_substring_lines=[]
        probe_functions={}
        if arm:
            assert '#define ARCH_X64 1' not in macros
            # This second preprocessing step contains the exact extracted ten
            # common operations and all five migrated method bodies, without
            # any SDK/header declarations. It does not replace the real-header
            # compile, dependency or assembly proof above. The actual target's
            # ARCH_ARM64=1 and absent ARCH_X64 were verified independently.
            production_fragment=(work/'common.inc').read_text()+'\nnamespace candidate {\n'+(work/'after.inc').read_text()+'\n}\n'
            preprocessed_fragment=subprocess.check_output(cxx+['-std=c++20','-E','-P','-x','c++','-DARCH_ARM64=1','-UARCH_X64','-DRPCS3_IOS=1','-'],input=production_fragment,text=True)
            arm64_fragment_legacy_names_absent(preprocessed_fragment,dependencies)
            # Bounded factual diagnostics for SDK declarations; no assertion or
            # inferred origin is attached to incidental full-header substrings.
            full_header_legacy_lines=[line for line in preprocessed.splitlines() if LEGACY_TOKEN.search(line)]
            full_header_substring_lines=[line for line in preprocessed.splitlines() if '_mm_' in line or '__m128' in line]
            for symbol in ('rsx526_decode_after','rsx526_stream_after','rsx526_copy_after','rsx526_border_after'):
                label=re.search(r'^_?'+symbol+r':[^\n]*\n',assembly,re.M)
                assert label, 'Missing assembly symbol '+symbol
                body=assembly[label.end():]
                end=re.search(r'^\s*(?:\.cfi_endproc|\.size|\.globl|\.global)\b',body,re.M)
                body=body[:end.start()] if end else body
                assert not re.search(r'\b(?:bl|blr)\b',body), 'Unexpected helper call in '+symbol
                probe_functions[symbol]=body
            assert 'rev16' in probe_functions['rsx526_decode_after'].lower(), 'Native byte reversal missing'
            assert 'eor' in probe_functions['rsx526_border_after'].lower(), 'Native border-color XOR missing'
            assert re.search(r'\b(?:str|st1|stp)\b',probe_functions['rsx526_stream_after']), 'Native vector store missing'
        run=subprocess.run([str(work/'test')]+(['benchmark'] if a.benchmark else []),capture_output=True,text=True,timeout=240,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'))
        if run.returncode:print(run.stdout,run.stderr);run.check_returncode()
        record=json.loads(run.stdout)
        assert record['architecture'] == ('ARM64' if arm else 'x86_64'), 'Compiled harness/real-header target mismatch'
        record.update(fixtureSHA256=sha(fixture.read_bytes()),
            beforeSHA256={p:sha((previous/p).read_bytes()) for p in PATHS},
            afterSHA256={p:sha((source/p).read_bytes().replace(b'\r\n',b'\n')) for p in PATHS},
            backendSHA256=sha(common.encode()),sanitizers=a.sanitize,candidateOnlyProbe=True,arm64LegacyNamesAbsent=arm,architectureMacros={'ARCH_ARM64':arm,'ARCH_X64':x64},activeProductionFragmentSHA256=sha(preprocessed_fragment.encode()) if arm else None,fullHeaderLegacyTokenCount=len(full_header_legacy_lines),fullHeaderLegacyTokenLines=[line[:240] for line in full_header_legacy_lines[:12]],fullHeaderLegacySubstringCount=len(full_header_substring_lines),fullHeaderLegacySubstringLines=[line[:240] for line in full_header_substring_lines[:12]],candidateLegacyHeaderDependencyAbsent=True,candidateDependencySHA256=sha(dependencies.encode()),probeAssemblySHA256=sha(assembly.encode()),probeFunctions=probe_functions,
            scope='real v128 and extracted production operations/methods; RSX program register/data adapters; baseline-only sse2neon on ARM64',
            physicalDeviceTested=False,gpuTested=False,hostHardware=hardware(),coreCompilerLLVMVersion=core_llvm,compilerVersion=subprocess.check_output(cxx+['--version'],text=True).splitlines()[0])
        if a.report:a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(record,indent=2)+'\n')
        print(json.dumps(record,indent=2))
if __name__=='__main__':main()

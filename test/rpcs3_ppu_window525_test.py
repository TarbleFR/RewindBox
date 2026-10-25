#!/usr/bin/env python3
"""Exercise actual PPU buffer window/load/settings/owner code with bounded host adapters.

No LLVM linker, generated guest code, iPhone, title or cold-storage timing is
claimed. --require-llvm selects the pinned real LLVM MemoryBuffer for CI.
"""
import argparse, hashlib, json, os, shlex, shutil, subprocess, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def braced(text, marker):
    start = text.index(marker); end = text.index('{', start) + 1; depth = 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}'); end += 1
    return text[start:end]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path); p.add_argument('--require-llvm', action='store_true')
    p.add_argument('--sanitize', action='store_true'); p.add_argument('--benchmark', action='store_true')
    p.add_argument('--report', type=Path); a = p.parse_args(); core = a.source.resolve()
    ppu = (core/'rpcs3/Emu/Cell/PPUThread.cpp').read_text()
    jit = (core/'Utilities/JITLLVM.cpp').read_text()
    fixture = ROOT/'test/fixtures/rpcs3_ppu_window525.diff'
    llvm = os.environ.get('LLVM_CONFIG') or shutil.which('llvm-config')
    if a.require_llvm and not llvm: raise SystemExit('Pinned LLVM_CONFIG required')
    pipeline = braced(ppu, 'static ppu_llvm_pipeline_type ppu_effective_pipeline()')
    owner = braced(ppu, 'class ppu_object_window_scope') + ';'
    assert 'release_cached_object_buffers' not in pipeline
    assert 'ppu_object_window_scope object_window;' in braced(ppu, 'extern void ppu_initialize()\n{')
    assert 'ppu_object_window_scope object_window;' in braced(ppu, 'bool ppu_initialize(const ppu_module<lv2_obj>& info, bool check_only, u64 file_size)\n{')
    assert ppu.count('ppu_object_window_scope object_window;') == 2
    with tempfile.TemporaryDirectory(prefix='ppu-window525-') as d:
        work = Path(d); previous = work/'previous'; target = previous/'rpcs3/Emu/Cell/PPUThread.cpp'
        target.parent.mkdir(parents=True); target.write_text(ppu)
        subprocess.run(['git','apply','--reverse',str(fixture)],cwd=previous,check=True)
        before = target.read_text()
        pin = json.loads(subprocess.check_output(['git','show','1bdad6caf3848916e427e6b602b78e7fb42cb500:build-utils/rpcs3/canonical-source.json'],cwd=ROOT))
        assert hashlib.sha256(target.read_bytes()).hexdigest() == pin['files_sha256']['rpcs3/Emu/Cell/PPUThread.cpp']
        window = jit[jit.index('struct object_file_identity'):jit.index('\n}\n#endif',jit.index('struct object_file_identity'))]
        release = braced(jit, 'void jit_compiler::release_cached_object_buffers()')
        load = braced(jit, 'static std::unique_ptr<llvm::MemoryBuffer> load(')
        prefix = '''struct jit_compiler { static void release_cached_object_buffers(); };
struct ObjectCache {\n'''+load+'\n};\n'
        for variant, text in [('before',before),('after',ppu)]:
            setting = braced(text, 'static ppu_llvm_pipeline_type ppu_effective_pipeline()')
            scope = owner+'\nusing owner_scope = ppu_object_window_scope;' if variant == 'after' else 'struct owner_scope { ~owner_scope() {} };'
            (work/(variant+'.inc')).write_text(prefix+window+'\n'+release+'\n'+scope+'\n'+setting+'\n')
        cxx = shlex.split(os.environ.get('CXX','c++'))
        if sdk := os.environ.get('HOST_MACOS_SDK'): cxx += ['-isysroot',sdk]
        flags=[]; link=[]
        if llvm:
            raw_flags = shlex.split(subprocess.check_output([llvm,'--cxxflags'],text=True))
            for flag in raw_flags:
                flags += ['-isystem',flag[2:]] if flag.startswith('-I') else [flag]
            link = shlex.split(subprocess.check_output([llvm,'--ldflags','--libs','support','--system-libs'],text=True))
            flags += ['-DREAL_LLVM']
        cmd = cxx+flags+['-std=c++20','-O3','-g','-Wall','-Wextra','-Werror','-pthread','-DRPCS3_IOS','-I'+str(work),'-I'+str(core),str(ROOT/'test/native/rpcs3_ppu_window525.cpp'),'-lz',*link,'-o',str(work/'test')]
        if a.sanitize: cmd += ['-fsanitize=address,undefined','-fno-omit-frame-pointer']
        subprocess.run(cmd,check=True)
        run = subprocess.run([str(work/'test'),str(work)]+(['benchmark'] if a.benchmark else []),capture_output=True,text=True,timeout=180,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'))
        if run.returncode: print(run.stdout,run.stderr); run.check_returncode()
        result=json.loads(run.stdout); result.update(realLLVMMemoryBuffer=bool(llvm),sanitizers=a.sanitize,
          timingAllocator='pinned LLVM uninitialized buffers' if llvm else 'portable zero-initialized vector adapter; allocator timings are not production LLVM timings',
          production='actual window, identity, gzip load, settings and owner methods; host fs/clock adapters; no MCJIT/game/device',
          cache='new synthetic files for first pass; warm filesystem for alternated rounds; no OS-cache eviction or cold-storage claim',
          beforeSourceSHA256=hashlib.sha256(before.encode()).hexdigest(),afterSourceSHA256=hashlib.sha256(ppu.encode()).hexdigest(),fixtureSHA256=hashlib.sha256(fixture.read_bytes()).hexdigest())
        if a.report: a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))
if __name__=='__main__': main()

#!/usr/bin/env python3
"""Experimental raw FP preload candidate, withdrawn from production.

Execute exact raw FP loading, hash validation, unpacking and preload worker.

Uses real temporary files and production lf_fifo/FP ownership. Only the worker
launcher, filesystem facade, vertex hash and shader compiler are host adapters.
"""
import argparse, hashlib, importlib.util, json, os, platform, shlex, shutil, subprocess, tempfile
from contextlib import ExitStack
from pathlib import Path
from rpcs3_texture_address_index_test import braced
ROOT=Path(__file__).resolve().parents[1]
SOURCE='rpcs3/Emu/RSX/rsx_cache.h';FP='rpcs3/Emu/RSX/Program/RSXFragmentProgram.h';HASH='rpcs3/Emu/RSX/Program/ProgramStateCache.cpp';FIFO='Utilities/lockless.h'
ADAPTER=ROOT/'test/native/rpcs3_shader_raw_preload.inc'
sha=lambda p:hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()

def harness(source,baseline):
    for p in [FP,HASH,FIFO]:assert sha(source/p)==sha(baseline/p),p
    spec=importlib.util.spec_from_file_location('warmup',ROOT/'test/native/rpcs3_cell591_warmup.py');warm=importlib.util.module_from_spec(spec);spec.loader.exec_module(warm)
    prefix=warm.PREFIX.replace('#define RPCS3_IOS 1','').replace(' T& raw()', ' T operator++(int) {return fetch_add(1);}\n T operator--(int) {return fetch_add(static_cast<T>(-1));}\n T& raw()')
    text=prefix+ADAPTER.read_text();fp=(source/FP).read_text();hashtext=(source/HASH).read_text();fifo=(source/FIFO).read_text()
    text=text.replace('@DATA@',braced(fp,'struct data_storage_helper\n')+';').replace('@GET_DATA@',braced(fp,'void* get_data() const')).replace('@CLONE_DATA@',braced(fp,'void clone_data() const'))
    text=text.replace('@HASH@',braced(hashtext,'bool fragment_program_utils::is_any_src_constant(')+'\n'+braced(hashtext,'usz fragment_program_utils::get_fragment_program_ucode_hash('))
    helpers='template<class T,usz N>\n'+braced(fifo,'class lf_array\n')+';\ntemplate<class T,usz N>\n'+braced(fifo,'class lf_fifo : public lf_array<T, N>')+';'
    text=text.replace('@FIFO@',helpers)
    versions=''
    for name,root,ios in [('before',baseline,False),('after',source,True),('desktop',source,False)]:
        current=(root/SOURCE).read_text();versions+='namespace '+name+' {\n'
        if ios:versions+='#define RPCS3_IOS\n'
        cls=text[text.index('// BEGIN CACHE'):text.index('// END CACHE')]
        cls=cls.replace('@PIPELINE@',braced(current,'struct pipeline_data\n')+';')
        cls=cls.replace('@FP_CACHE@',braced(current,'struct raw_fragment_cache\n')+';' if ios else '')
        methods='\n'.join(braced(current,s) for s in ['RSXVertexProgram load_vp_raw(', 'RSXFragmentProgram load_fp_raw(', 'std::tuple<pipeline_storage_type, RSXVertexProgram, RSXFragmentProgram> unpack(', 'void load_shaders('])
        if ios:methods+=braced(current,'RSXFragmentProgram load_fp_raw_cached(')
        cls=cls.replace('@METHODS@',methods);versions+=cls+'\n'
        if ios:versions+='#undef RPCS3_IOS\n'
        versions+='}\n'
    a=text.index('// BEGIN CACHE');b=text.index('// END CACHE')+len('// END CACHE');text=text[:a]+versions+text[b:]
    # Bound the production change to the new pass-local cache, routing and helper.
    old=(baseline/SOURCE).read_text();new=(source/SOURCE).read_text()
    assert braced(old,'RSXFragmentProgram load_fp_raw(')==braced(new,'RSXFragmentProgram load_fp_raw(')
    assert braced(old,'RSXVertexProgram load_vp_raw(')==braced(new,'RSXVertexProgram load_vp_raw(')
    assert braced(old,'void load(shader_loading_dialog* dlg, Args&& ...args)')==braced(new,'void load(shader_loading_dialog* dlg, Args&& ...args)')
    return text

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--candidate-from-fixture',type=Path,help='Apply the withdrawn candidate only to a temporary copy of source inputs')
    p.add_argument('--compiler',default=os.environ.get('CXX','c++'));p.add_argument('--sanitizer',choices=['address,undefined','thread']);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    with ExitStack() as contexts:
        source=a.source.resolve();baseline=a.baseline.resolve()
        if a.candidate_from_fixture:
            experimental=Path(contexts.enter_context(tempfile.TemporaryDirectory(prefix='rpcs3-raw-candidate-')))
            for name in [SOURCE,FP,HASH,FIFO]:
                target=experimental/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/name,target)
            subprocess.run(['git','apply',str(a.candidate_from_fixture.resolve())],cwd=experimental,check=True)
            source=experimental
        code=harness(source,baseline)
        flags=['-std=c++20','-Wall','-Wextra','-Werror','-UNDEBUG','-g','-pthread','-O1' if a.sanitizer else '-O3']
        if a.sanitizer:
            flags+=['-fsanitize='+a.sanitizer,'-fno-omit-frame-pointer']
            if platform.system()=='Linux':flags+=['-fno-pie','-no-pie']
        if sdk:=os.environ.get('HOST_MACOS_SDK'):flags+=['-isysroot',sdk]
        compiler=shlex.split(a.compiler)
        with tempfile.TemporaryDirectory(prefix='rpcs3-raw-preload-') as tmp:
            cpp=Path(tmp)/'test.cpp';exe=Path(tmp)/'test';cpp.write_text(code)
            subprocess.run([*compiler,*flags,str(cpp),'-o',str(exe)],check=True)
            run=subprocess.run([str(exe),str(Path(tmp)/'files')],text=True,capture_output=True,timeout=120,
                env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1',TSAN_OPTIONS='halt_on_error=1'))
            assert run.returncode==0,(run.returncode,run.stdout,run.stderr)
            result=json.loads(run.stdout)
        paths=[SOURCE,FP,HASH,FIFO]
        report=dict(passed=True,sourceSHA256={p:sha(source/p) for p in paths},baselineSHA256={p:sha(baseline/p) for p in paths},
            harnessSHA256=hashlib.sha256(code.encode()).hexdigest(),adapterSHA256=sha(ADAPTER),compiler=subprocess.check_output([*compiler,'--version'],text=True).splitlines()[0],
            compilerFlags=flags,host=platform.machine(),results=result,physicalDeviceTested=False,gameplayMeasured=False,scope=__doc__)
        a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()

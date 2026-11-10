#!/usr/bin/env python3
"""Portable adapters for exact candidate gate/preparation source; no Metal/iPhone claim."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / 'build-utils/rpcs3/patch_moltenvk_deferred_cache.py'
spec = importlib.util.spec_from_file_location('mvk_candidate', ADAPTER)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def function(source, signature):
    start = source.index(signature)
    body = source.index('{', start)
    depth = 1
    pos = body + 1
    while depth:
        depth += (source[pos] == '{') - (source[pos] == '}')
        pos += 1
    return source[start:pos]


STUBS = r'''
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <future>
#include <iostream>
#include <mutex>
#include <map>
#include <string>
#include <thread>
#include <vector>
using namespace std;
using namespace std::chrono_literals;
struct SPIRVToMSLConversionResultInfo { int marker=1; };
struct SPIRVToMSLConversionConfiguration { int marker=1; void alignWith(const SPIRVToMSLConversionConfiguration& x) { marker=x.marker; } };
template<class T> struct MVKCompressor { T data="good"; void compress(const T& x, int) { data=x; } };
struct SPIRVToMSLConversionResult { string msl="fresh"; SPIRVToMSLConversionResultInfo resultInfo{9}; };
struct SPIRVToMSLConverter { vector<uint32_t> spv; atomic<int> active{0}; void setSPIRV(const vector<uint32_t>& x){spv=x;} };
struct MVKConfig { int shaderSourceCompressionAlgorithm=0; };
MVKConfig getMVKConfig(){return {};}
struct FakeLibrary { static atomic<int> live; FakeLibrary(){live++;} ~FakeLibrary(){live--;} }; atomic<int> FakeLibrary::live{0};
struct MVKDeferredShaderLibrary {
 FakeLibrary* library=nullptr; SPIRVToMSLConversionResultInfo resultInfo;
 MVKCompressor<string> compressedMSL; SPIRVToMSLConversionConfiguration shaderConfig;
 ~MVKDeferredShaderLibrary(){delete library;} explicit operator bool()const{return library;}
};
struct MVKPipeline {bool fail=false; bool shouldFailOnPipelineCompileRequired(){return fail;} };
atomic<int> compiles{0}, conversions{0}, converterRaces{0};
mutex compileMutex; condition_variable compileCV; bool blockCompile=false, releaseCompile=false; int entered=0;
mutex conversionMutex;condition_variable conversionCV;bool blockOrdinary=false,ordinaryEntered=false,freshEntered=false,releaseOrdinary=false;
FakeLibrary* compileImportedMSL(MVKPipeline*, const string& msl,const SPIRVToMSLConversionResultInfo&){
 compiles++;
 {unique_lock<mutex> lock(compileMutex); entered++; compileCV.notify_all(); if(blockCompile) compileCV.wait(lock,[]{return releaseCompile;});}
 return msl=="bad"||msl=="freshbad" ? nullptr : new FakeLibrary;
}
class MVKShaderModule {
public:
 vector<uint32_t> spirv{1,2}; SPIRVToMSLConverter ordinary; bool convertOK=true, freshOK=true;
 const vector<uint32_t>& getSPIRV(){return spirv;}
 bool convertWithConverter(SPIRVToMSLConversionConfiguration* cfg, SPIRVToMSLConversionResult& result,SPIRVToMSLConverter& cv){
  conversions++; if(cv.active.fetch_add(1)) converterRaces++;
  if(blockOrdinary){unique_lock<mutex> lock(conversionMutex);if(&cv==&ordinary){ordinaryEntered=true;conversionCV.notify_all();conversionCV.wait(lock,[]{return releaseOrdinary;});}else{freshEntered=true;conversionCV.notify_all();}}
  this_thread::sleep_for(1ms); cfg->marker=9; result.resultInfo.marker=9; result.msl=freshOK?"fresh":"freshbad";
  cv.active--; return convertOK;
 }
 bool convertFresh(SPIRVToMSLConversionConfiguration*,SPIRVToMSLConversionResult&);
 bool convert(SPIRVToMSLConversionConfiguration* cfg,SPIRVToMSLConversionResult& r){return convertWithConverter(cfg,r,ordinary);}
};
struct MVKVulkanAPIDeviceObject {int getDevice(){return 0;}};
struct MVKShaderMacroValue {int value=0;};
class MVKBaseDeviceObject {public:int _device=0;MVKBaseDeviceObject(int device=0):_device(device){}};
class MVKShaderLibrary : public MVKBaseDeviceObject {
public:
 MVKShaderLibrary():_deferredLibrary(make_shared<MVKDeferredCompilation<MVKDeferredShaderLibrary>>()){}
 MVKShaderLibrary(MVKVulkanAPIDeviceObject*,const SPIRVToMSLConversionResultInfo&, const MVKCompressor<string>,const vector<pair<uint32_t,MVKShaderMacroValue>>* =nullptr,bool=false);
 ~MVKShaderLibrary(){delete _mtlLibrary;}
 void compileLibrary(const string&,const vector<pair<uint32_t,MVKShaderMacroValue>>* = nullptr){compiles++;_mtlLibrary=new FakeLibrary;}
 MVKShaderLibrary(const MVKShaderLibrary&);
 MVKVulkanAPIDeviceObject* _owner=nullptr; bool _maySpecializeWithMacro=true; map<int,int*> _specializationVariants; FakeLibrary* _mtlLibrary=nullptr;
 shared_ptr<MVKDeferredCompilation<MVKDeferredShaderLibrary>> _deferredLibrary;
 SPIRVToMSLConversionResultInfo _shaderConversionResultInfo;
 MVKCompressor<string> _compressedMSL;
 void decompressMSL(string& x){x=_compressedMSL.data;}
 bool prepareDeferredLibrary(SPIRVToMSLConversionConfiguration*,MVKShaderModule*,MVKPipeline*);
};
void reset(){compiles=0;conversions=0;converterRaces=0;blockCompile=false;releaseCompile=false;entered=0;blockOrdinary=false;ordinaryEntered=false;freshEntered=false;releaseOrdinary=false;}
void awaitEntered(int target){unique_lock<mutex> lock(compileMutex); assert(compileCV.wait_for(lock,2s,[&]{return entered>=target;}));}
void releaseAll(){lock_guard<mutex> lock(compileMutex);releaseCompile=true;compileCV.notify_all();}
'''

CASES = r'''
int main(){int cases=0;
 // Same entry: 24 concurrent users produce exactly one compiled resource.
 {reset();MVKShaderLibrary lib;MVKShaderModule module;MVKPipeline pipe;vector<thread> workers;
  for(int i=0;i<24;i++)workers.emplace_back([&]{SPIRVToMSLConversionConfiguration cfg;assert(lib.prepareDeferredLibrary(&cfg,&module,&pipe));});
  for(auto& t:workers){t.join();}assert(compiles==1);cases++;}
 assert(FakeLibrary::live==0);
 // FAIL_ON before first use must not submit any work.
 {reset();MVKShaderLibrary lib;MVKShaderModule module;MVKPipeline pipe;pipe.fail=true;SPIRVToMSLConversionConfiguration cfg;
  assert(!lib.prepareDeferredLibrary(&cfg,&module,&pipe));assert(compiles==0);pipe.fail=false;assert(lib.prepareDeferredLibrary(&cfg,&module,&pipe));
  pipe.fail=true;assert(lib.prepareDeferredLibrary(&cfg,&module,&pipe));assert(compiles==1);cases++;}
 // FAIL_ON while another thread compiles returns before that compilation is released.
 {reset();blockCompile=true;MVKShaderLibrary lib;MVKShaderModule module;MVKPipeline pipe;
  auto active=async(launch::async,[&]{SPIRVToMSLConversionConfiguration cfg;return lib.prepareDeferredLibrary(&cfg,&module,&pipe);});awaitEntered(1);
  MVKPipeline noCompile;noCompile.fail=true;
  auto flag=async(launch::async,[&]{SPIRVToMSLConversionConfiguration cfg;return lib.prepareDeferredLibrary(&cfg,&module,&noCompile);});
  bool nonblocking=flag.wait_for(100ms)==future_status::ready;releaseAll();assert(nonblocking);assert(!flag.get());assert(active.get());assert(compiles==1);cases++;}
 // Independent entries reach the compiler together, with no global cache lock.
 {reset();blockCompile=true;MVKShaderLibrary a,b;MVKShaderModule module;MVKPipeline pipe;
  auto run=[&](MVKShaderLibrary& lib){SPIRVToMSLConversionConfiguration cfg;return lib.prepareDeferredLibrary(&cfg,&module,&pipe);};
  auto x=async(launch::async,[&]{return run(a);});auto y=async(launch::async,[&]{return run(b);});awaitEntered(2);releaseAll();assert(x.get()&&y.get());cases++;}
 // One bounded fresh conversion, with recovered metadata and immutable serialized input.
 {reset();MVKShaderLibrary lib;lib._compressedMSL.data="bad";MVKShaderModule module;MVKPipeline pipe;SPIRVToMSLConversionConfiguration cfg;
  assert(lib.prepareDeferredLibrary(&cfg,&module,&pipe));assert(compiles==2&&conversions==1);assert(cfg.marker==9);
  assert(lib._deferredLibrary->value().resultInfo.marker==9);assert(lib._deferredLibrary->value().compressedMSL.data=="fresh");assert(lib._compressedMSL.data=="bad");cases++;}
 // Cached and fresh Metal failures are terminal; repeated callers never retry.
 {reset();MVKShaderLibrary lib;lib._compressedMSL.data="bad";MVKShaderModule module;module.freshOK=false;MVKPipeline pipe;
  for(int i=0;i<10;i++){SPIRVToMSLConversionConfiguration cfg;assert(!lib.prepareDeferredLibrary(&cfg,&module,&pipe));}
  assert(compiles==2&&conversions==1);cases++;}
 // Conversion failure remains terminal and does not submit a second Metal compile.
 {reset();MVKShaderLibrary lib;lib._compressedMSL.data="bad";MVKShaderModule module;module.convertOK=false;MVKPipeline pipe;SPIRVToMSLConversionConfiguration cfg;
  assert(!lib.prepareDeferredLibrary(&cfg,&module,&pipe));assert(!lib.prepareDeferredLibrary(&cfg,&module,&pipe));assert(compiles==1&&conversions==1);cases++;}
 // No original SPIR-V: report failure without inventing a fallback source.
 {reset();MVKShaderLibrary lib;lib._compressedMSL.data="bad";MVKShaderModule module;module.spirv.clear();MVKPipeline pipe;SPIRVToMSLConversionConfiguration cfg;
  assert(!lib.prepareDeferredLibrary(&cfg,&module,&pipe));assert(compiles==1&&conversions==0);cases++;}
 // Merged cache instances share state; destruction of the source is safe.
 {reset();auto original=make_unique<MVKShaderLibrary>();auto merged=make_unique<MVKShaderLibrary>(*original);original.reset();
  MVKShaderModule module;MVKPipeline pipe;SPIRVToMSLConversionConfiguration cfg;assert(merged->prepareDeferredLibrary(&cfg,&module,&pipe));assert(compiles==1);cases++;}
 assert(FakeLibrary::live==0);
 // Copies after success share the completed resource; source destruction releases no live copy.
 {reset();auto original=make_unique<MVKShaderLibrary>();MVKShaderModule module;MVKPipeline pipe;SPIRVToMSLConversionConfiguration cfg;
  assert(original->prepareDeferredLibrary(&cfg,&module,&pipe));auto merged=make_unique<MVKShaderLibrary>(*original);original.reset();
  pipe.fail=true;assert(merged->prepareDeferredLibrary(&cfg,&module,&pipe));assert(compiles==1);assert(FakeLibrary::live==1);cases++;}
 assert(FakeLibrary::live==0);
 // Copies after terminal failure retain failure without retrying the bad entry.
 {reset();auto original=make_unique<MVKShaderLibrary>();original->_compressedMSL.data="bad";MVKShaderModule module;module.freshOK=false;MVKPipeline pipe;SPIRVToMSLConversionConfiguration cfg;
  assert(!original->prepareDeferredLibrary(&cfg,&module,&pipe));auto merged=make_unique<MVKShaderLibrary>(*original);original.reset();
  assert(!merged->prepareDeferredLibrary(&cfg,&module,&pipe));assert(compiles==2&&conversions==1);cases++;}
 // Fresh fallback and ordinary cache misses never share the mutable converter.
 {reset();MVKShaderLibrary lib;lib._compressedMSL.data="bad";MVKShaderModule module;MVKPipeline pipe;
  blockOrdinary=true;auto normal=async(launch::async,[&]{SPIRVToMSLConversionConfiguration cfg;SPIRVToMSLConversionResult r;return module.convert(&cfg,r);});
  {unique_lock<mutex> lock(conversionMutex);assert(conversionCV.wait_for(lock,2s,[]{return ordinaryEntered;}));}
  auto fallback=async(launch::async,[&]{SPIRVToMSLConversionConfiguration cfg;return lib.prepareDeferredLibrary(&cfg,&module,&pipe);});
  bool independent;{unique_lock<mutex> lock(conversionMutex);independent=conversionCV.wait_for(lock,2s,[]{return freshEntered;});releaseOrdinary=true;conversionCV.notify_all();}
  assert(normal.get()&&fallback.get());assert(independent);assert(converterRaces==0);assert(compiles==2);cases++;}
 assert(FakeLibrary::live==0);
 cout<<"{\"behavioral_cases\":"<<cases<<",\"same_entry_threads\":24,\"metal_execution\":false}"<<endl;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--sanitizers', action='store_true')
    parser.add_argument('--disable-lsan', action='store_true', help='Host under ptrace cannot enumerate threads for LeakSanitizer; retain ASan/UBSan')
    args = parser.parse_args()
    source = args.source.resolve()
    mod.apply(source, check=True)
    gpu = source / 'MoltenVK/MoltenVK/GPUObjects'
    mm = (gpu / 'MVKShaderModule.mm').read_text()
    header = (gpu / 'MVKShaderModule.h').read_text()
    # Real import alone requests deferral; macro variants retain the eager default.
    assert 'new MVKShaderLibrary(_owner, resultInfo, compressedMSL, nullptr, true)' in mm
    assert 'if (deferCacheImport && !specializationMacroDef)' in mm
    assert '#define RBX_MVK_DEFERRED_CACHE_IMPORT 0' in header
    prepare = function(mm, 'bool MVKShaderLibrary::prepareDeferredLibrary(')
    fresh = function(mm, 'bool MVKShaderModule::convertFresh(')
    constructor_at = mm.rfind('MVKShaderLibrary::MVKShaderLibrary(', 0, mm.index('bool deferCacheImport) :'))
    constructor = function(mm[constructor_at:], 'MVKShaderLibrary::MVKShaderLibrary(')
    copy_start = mm.index('MVKShaderLibrary::MVKShaderLibrary(const MVKShaderLibrary& other)')
    copy_end = mm.index('MVKShaderLibrary& MVKShaderLibrary::operator=', copy_start)
    copy = mm[copy_start:copy_end].replace('[other._mtlLibrary retain]', 'other._mtlLibrary')
    compiler_errors = function(mm, 'class MVKImportedShaderLibraryCompiler')
    assert 'setConfigurationResult' not in compiler_errors
    assert 'convertFresh(pShaderConfig, conversion)' in prepare
    assert '_accessLock' not in prepare
    with tempfile.TemporaryDirectory(prefix='rbx-mvk-test-') as temp:
        work = Path(temp)
        cpp = work / 'candidate.cpp'
        cpp.write_text('#include "' + str(gpu / 'MVKDeferredCompilation.h') + '"\n' + STUBS + prepare + '\n' + fresh + '\n' + copy + '\n' + constructor + '\n' + CASES)
        compiler = shutil.which('c++') or shutil.which('g++')
        if not compiler:
            raise RuntimeError('C++ compiler required; do not replace behavioral checks with source matching')
        subprocess.run([compiler, '-std=c++17', '-DRBX_MVK_DEFERRED_CACHE_IMPORT=1', '-O2', '-pthread', '-Wall', '-Wextra', '-Werror', str(cpp), '-o', str(work/'candidate')], check=True)
        run = subprocess.run([str(work/'candidate')], check=True, capture_output=True, text=True, timeout=30)
        behavioral = json.loads(run.stdout)
        sanitized = 'not_run'
        if args.sanitizers:
            subprocess.run([compiler, '-std=c++17', '-DRBX_MVK_DEFERRED_CACHE_IMPORT=1', '-O1', '-g', '-pthread',
                            '-fsanitize=address,undefined', '-fno-omit-frame-pointer', str(cpp), '-o', str(work/'candidate-sanitized')], check=True)
            sanit_env = os.environ.copy()
            if args.disable_lsan:
                sanit_env['ASAN_OPTIONS'] = 'detect_leaks=0'
            sanit_run = subprocess.run([str(work/'candidate-sanitized')], capture_output=True, text=True, timeout=30, env=sanit_env)
            if sanit_run.returncode:
                raise RuntimeError(f'ASan/UBSan adapter failure:\n{sanit_run.stdout}\n{sanit_run.stderr}')
            leak_check = ('disabled: host ptrace cannot enumerate /proc tasks' if args.disable_lsan
                          else 'not supported on Darwin' if platform.system() == 'Darwin'
                          else 'passed')
            sanitized = {'ASan':'passed','UBSan':'passed','LeakSanitizer':leak_check}
        constructor_results = []
        for enabled in (0, 1):
            ctor = work / f'constructor-{enabled}.cpp'
            ctor.write_text('#include "' + str(gpu/'MVKDeferredCompilation.h') + '"\n' + STUBS + constructor + r'''
int main(){reset();MVKVulkanAPIDeviceObject owner;SPIRVToMSLConversionResultInfo info;MVKCompressor<string> compressed;
 for(int i=0;i<64;i++){MVKShaderLibrary lib(&owner,info,compressed,nullptr,true);}
 int imported=compiles;assert(imported==(RBX_MVK_DEFERRED_CACHE_IMPORT?0:64));
 vector<pair<uint32_t,MVKShaderMacroValue>> macros;
 {MVKShaderLibrary variant(&owner,info,compressed,&macros);}
 assert(compiles==imported+1);assert(FakeLibrary::live==0);
 cout<<"{\"macro\":"<<RBX_MVK_DEFERRED_CACHE_IMPORT<<",\"imported_entries\":64,\"import_compiles\":"<<imported<<",\"variant_compiles\":1}"<<endl;
}
''')
            subprocess.run([compiler,'-std=c++17',f'-DRBX_MVK_DEFERRED_CACHE_IMPORT={enabled}','-O2','-pthread',str(ctor),'-o',str(work/f'constructor-{enabled}')],check=True)
            ctor_run=subprocess.run([str(work/f'constructor-{enabled}')],check=True,capture_output=True,text=True,timeout=30)
            constructor_results.append(json.loads(ctor_run.stdout))
        # Fresh checkout tests apply, idempotence, fail-closed drift and read-only verification.
        clone = work/'source'
        subprocess.run(['git', 'clone', '--shared', '--quiet', str(source), str(clone)], check=True, capture_output=True)
        first = mod.apply(clone)
        second = mod.apply(clone)
        assert first['status'] == 'applied' and second['status'] == 'already_applied'
        assert mod.apply(clone, check=True)['status'] == 'already_applied'
        target = clone/'MoltenVK/MoltenVK/GPUObjects/MVKShaderModule.mm'
        target.write_text(target.read_text()+'\n// drift\n')
        try:
            mod.apply(clone)
        except ValueError:
            pass
        else:
            raise AssertionError('Drift was silently accepted')
    result = {'schema':1, 'platform':platform.system() + ' C++17 source-extracted adapters',
              'host_machine':platform.machine(),
              'compiler':subprocess.check_output([compiler, '--version'], text=True).splitlines()[0],
              'upstream_commit':mod.UPSTREAM_COMMIT, 'source_postimages':mod.POSTIMAGES,
              'patch_sha256':hashlib.sha256(mod.PATCH.read_bytes()).hexdigest(),
              'behavior':behavioral, 'import_constructor_modes':constructor_results, 'sanitizers':sanitized, 'patch_contract_cases':4,
              'apple_objcxx_build':'not_run', 'real_metal_execution':'not_run',
              'iphone_bo2_multiplayer':'not_run', 'fps_gain_claimed':False}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, sort_keys=True))

if __name__ == '__main__':
    main()

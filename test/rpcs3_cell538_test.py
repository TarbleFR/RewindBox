#!/usr/bin/env python3
"""Execute the production cache-probe body and bounded shader recorder; no gameplay claim."""
import argparse, hashlib, json, os, re, shlex, subprocess, tempfile
from pathlib import Path
from rpcs3_memory523_test import braced
ROOT = Path(__file__).resolve().parents[1]
sha = lambda b: hashlib.sha256(b).hexdigest()

def cache_identities(source):
    manifest = json.loads((ROOT/'build-utils/rpcs3/canonical-source.json').read_bytes())
    baseline = manifest['cell538']['baseline']
    before = json.loads(subprocess.check_output(['git','show',baseline+':build-utils/rpcs3/canonical-source.json'],cwd=ROOT))
    cmake = (source/'rpcs3/Emu/CMakeLists.txt').read_text()
    old_cmake = (ROOT/'test/fixtures/rpcs3_cell538.diff').read_text()
    assert 'neostation_codegen_compatible_hash' in old_cmake
    script = 'include("'+str(source/'rpcs3/Emu/CPU/JITCacheCompatibility.cmake')+'")\n'
    paths = {}
    for kind in ('PPU','SPU'):
        names = re.search(r'foreach\(NEOSTATION_'+kind+r'_CODEGEN_SOURCE IN ITEMS\s+(.*?)\)',cmake,re.S).group(1).split()
        assert f'neostation_codegen_compatible_hash("${{NEOSTATION_{kind}_CODEGEN_SOURCE}}" "${{NEOSTATION_{kind}_CODEGEN_FILE_SHA256}}" NEOSTATION_{kind}_CODEGEN_FILE_SHA256)' in cmake
        paths[kind] = names
        script += 'set(parts "")\n'
        for name in names:
            digest = manifest['llvm_aarch64_ghc_patch']['postimage_sha256'] if name.endswith('/AArch64FrameLowering.cpp') else sha((source/'rpcs3/Emu'/name).read_bytes())
            script += f'neostation_codegen_compatible_hash("{name}" "{digest}" mapped)\nstring(APPEND parts "{name}:${{mapped}};")\n'
        script += f'string(SHA256 result "${{parts}}")\nstring(SUBSTRING "${{result}}" 0 16 result)\nmessage("{kind}=${{result}}")\n'
    current=sha((source/'Utilities/JITLLVM.cpp').read_bytes())
    old=before['files_sha256']['Utilities/JITLLVM.cpp']
    script += f'''neostation_codegen_compatible_hash("../../Utilities/JITLLVM.cpp" "{current}" same)
if(NOT same STREQUAL "{old}")
 message(FATAL_ERROR "exact reviewed source not compatible")
endif()
neostation_codegen_compatible_hash("../../Utilities/JITLLVM.cpp" "{sha((source/'Utilities/JITLLVM.cpp').read_bytes()+b' ')}" changed)
if(changed STREQUAL same)
 message(FATAL_ERROR "future edit must invalidate")
endif()
neostation_codegen_compatible_hash("other.cpp" "{current}" other)
if(NOT other STREQUAL "{current}")
 message(FATAL_ERROR "wrong path was aliased")
endif()
'''
    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/'verify.cmake';path.write_text(script)
        result=subprocess.check_output(['cmake','-P',str(path)],stderr=subprocess.STDOUT,text=True)
    ids=dict(re.findall(r'(PPU|SPU)=([0-9a-f]{16})',result))
    assert ids==before['cell536']['codegen']==manifest['cell538']['codegen'],ids
    return ids

def main():
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--report',type=Path);a=p.parse_args()
    source=a.source.resolve();manifest=json.loads((ROOT/'build-utils/rpcs3/canonical-source.json').read_bytes());record=manifest['cell538']
    cxx=shlex.split(os.environ.get('CXX','c++'))
    if sdk:=os.environ.get('HOST_MACOS_SDK'):cxx+=['-isysroot',sdk]
    flags=['-std=c++20','-O1','-g','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer']
    results={}
    with tempfile.TemporaryDirectory(prefix='cell538-') as td:
        w=Path(td);before=w/'before'
        for relative in record['modified_paths']+record['new_files']:
            target=before/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((source/relative).read_bytes())
        subprocess.run(['git','apply','--reverse',str(ROOT/'test/fixtures/rpcs3_cell538.diff')],cwd=before,check=True)
        for relative,digest in record['before_sha256'].items():assert sha((before/relative).read_bytes().replace(b'\r\n',b'\n'))==digest,relative
        # This proves the compatibility alias excludes all LLVM emission/ABI changes.
        old=(before/'Utilities/JITLLVM.cpp').read_text();new=(source/'Utilities/JITLLVM.cpp').read_text()
        delta=re.search(r'\n\t\t// CELL538_SPU_CACHE_PROBE:.*?\n\t\t}\n',new,re.S).group()
        assert new.replace(delta,'',1)==old
        assert new.count('ObjectCache cache{path_dir, this, true, std::move(preloaded.buffer), &outcome};')==1
        code='#include <cassert>\n#include <chrono>\n#include <filesystem>\n#include <fstream>\n#include <iostream>\n#include <memory>\n#include <string>\n#include <utility>\n'
        for name,text in [('before',old),('after',new)]:
            body=braced(text,'std::unique_ptr<llvm::MemoryBuffer> getObject(const llvm::Module* _module) override')
            adapter=(ROOT/'test/native/rpcs3_cache_probe538_adapter.inc').read_text().replace('// PRODUCTION_BODY',body)
            code+='namespace '+name+' {\n'+adapter+'\n}\n'
            results[name+'BodySHA256']=sha(body.encode())
        code+='''int main(int argc, char** argv) {
 assert(argc == 2); std::filesystem::path directory(argv[1]);
 before::test(directory/"before", false); after::test(directory/"after", true);
 const auto bench=[&](auto& cache, auto& module) {
   cache.m_spu=true; cache.m_path=directory.string()+"/absent/";
   const auto start=std::chrono::steady_clock::now();
   for(int i=0;i<5153;++i) assert(!cache.getObject(&module));
   return std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
 };
 before::Cache old; before::llvm::Module m1{"missing"}; after::Cache now; after::llvm::Module m2{"missing"};
 const auto old_ms=bench(old,m1), new_ms=bench(now,m2);
 assert(old.opens==10306 && now.opens==0);
 std::cout << "{\\"beforeExtraOpenAttempts\\":" << old.opens << ",\\"afterExtraOpenAttempts\\":" << now.opens
   << ",\\"misses\\":5153,\\"beforeHostMs\\":" << old_ms << ",\\"afterHostMs\\":" << new_ms << "}\\n";
}
'''
        cpp=w/'probe.cpp';cpp.write_text(code);exe=w/'probe'
        subprocess.run(cxx+flags+[str(cpp),'-o',str(exe)],check=True)
        env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1')
        output=subprocess.check_output([str(exe),str(w/'files')],text=True,env=env);results['probe']=json.loads(output)
        for name in ('rpcs3_shader_stall538','rpcs3_shader_configuration536','rpcs3_shader_timing534'):
            exe=w/name;subprocess.run(cxx+flags+['-I'+str(source/'rpcs3'),str(ROOT/'test/native'/f'{name}.cpp'),'-o',str(exe)],check=True)
            results[name]=subprocess.check_output([str(exe)],text=True,env=env,timeout=60).strip()
    result=dict(passed=True,sanitized=True,physicalDeviceTested=False,gameplayMeasured=False,codegen=cache_identities(source),results=results,
      scope='Actual getObject body with LLVM adapters and real filesystem misses; actual shader headers under concurrent producers. Host adapter timings with sanitizers do not measure iPhone gains or compilation cost.')
    if a.report:a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()

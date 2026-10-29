#!/usr/bin/env python3
"""Execute exact shader Format methods with host operand/declaration adapters.

All original literal strings and generated token edge cases are checked against
baseline. GPU execution and GLSL-to-SPIR-V compilation are not simulated.
"""
import argparse, ast, hashlib, json, os, platform, re, shlex, subprocess, tempfile
from pathlib import Path
from rpcs3_texture_address_index_test import braced
ROOT=Path(__file__).resolve().parents[1]
DIR='rpcs3/Emu/RSX/Program/'
PATHS=[DIR+'ShaderParam.h',DIR+'VertexProgramDecompiler.cpp',DIR+'FragmentProgramDecompiler.cpp','Utilities/StrUtil.h']
ADAPTER=ROOT/'test/native/rpcs3_shader_tokens.inc'
sha=lambda p:hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()

def harness(source,baseline):
    text=ADAPTER.read_text(); helper=braced((source/PATHS[0]).read_text(),'template <usz Count>')
    assert sha(source/PATHS[3])==sha(baseline/PATHS[3])
    util=(source/PATHS[3]).read_text()
    a=util.index('\ttemplate <usz list_size>');b=util.index('\n\tstatic inline',a)
    text=text.replace('@REPLACE@','namespace fmt {\n'+util[a:b]+'\n}')
    declarations=(baseline/PATHS[0]).read_text();a=declarations.index('enum ParamFlag');b=declarations.index('class ShaderVariable',a)
    text=text.replace('@PARAMS@',declarations[a:b])
    old=(baseline/PATHS[0]).read_text();new=(source/PATHS[0]).read_text()
    a=new.index('#ifdef RPCS3_IOS');b=new.index('#endif',a)+len('#endif\n\n')
    assert new[:a]+new[b:]==old
    text=text.replace('@HELPER@',helper)
    versions='';literals=set()
    for name,root,ios in [('before',baseline,True),('after',source,True),('desktop',source,False)]:
        if ios:versions+='#define RPCS3_IOS\n'
        versions+='namespace '+name+' {\n'+text[text.index('// BEGIN BOUNDARY'):text.index('// END BOUNDARY')]+'\n'
        for which in ['Vertex','Fragment']:
            cpp=(root/(DIR+which+'ProgramDecompiler.cpp')).read_text()
            functions=[f'std::string {which}ProgramDecompiler::Format(']
            if which=='Vertex':functions+=['void VertexProgramDecompiler::AddCode(']
            for sig in functions:versions+=braced(cpp,sig)+'\n'
            for literal in re.findall(r'"(?:[^"\\]|\\.)*"',cpp):
                try:value=ast.literal_eval(literal)
                except (SyntaxError,ValueError):continue
                if '$' in value:literals.add(value)
            # No hidden production edits outside the explicitly exercised bodies.
            if name=='after':
                oldcpp=(baseline/(DIR+which+'ProgramDecompiler.cpp')).read_text();newcpp=cpp
                for sig in functions:
                    oldcpp=oldcpp.replace(braced(oldcpp,sig),'@BODY@');newcpp=newcpp.replace(braced(newcpp,sig),'@BODY@')
                assert oldcpp==newcpp
        versions+='}\n'
        if ios:versions+='#undef RPCS3_IOS\n'
    a=text.index('// BEGIN BOUNDARY');b=text.index('// END BOUNDARY')+len('// END BOUNDARY')
    text=text[:a]+versions+text[b:]
    # Emit C++ literals without ambiguous non-ASCII or numeric escapes.
    text=text.replace('@CORPUS@',',\n'.join(json.dumps(s,ensure_ascii=False) for s in sorted(literals)))
    return text

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--compiler',default=os.environ.get('CXX','c++'));p.add_argument('--sanitizer',choices=['address,undefined']);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    source=a.source.resolve();baseline=a.baseline.resolve();code=harness(source,baseline)
    flags=['-std=c++20','-Wall','-Wextra','-Werror','-UNDEBUG','-g','-O1' if a.sanitizer else '-O3']
    if a.sanitizer:
        flags+=['-fsanitize='+a.sanitizer,'-fno-omit-frame-pointer']
        if platform.system()=='Linux':flags+=['-fno-pie','-no-pie']
    if sdk:=os.environ.get('HOST_MACOS_SDK'):flags+=['-isysroot',sdk]
    compiler=shlex.split(a.compiler)
    with tempfile.TemporaryDirectory(prefix='rpcs3-shader-tokens-') as tmp:
        cpp=Path(tmp)/'test.cpp';exe=Path(tmp)/'test';cpp.write_text(code)
        subprocess.run([*compiler,*flags,str(cpp),'-o',str(exe)],check=True)
        run=subprocess.run([str(exe)]+([] if a.sanitizer else ['benchmark']),text=True,capture_output=True,timeout=120,
            env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'))
        assert run.returncode==0,(run.returncode,run.stdout,run.stderr)
        result=json.loads(run.stdout)
    report=dict(passed=True,sourceSHA256={p:sha(source/p) for p in PATHS},baselineSHA256={p:sha(baseline/p) for p in PATHS},
        harnessSHA256=hashlib.sha256(code.encode()).hexdigest(),adapterSHA256=sha(ADAPTER),compiler=subprocess.check_output([*compiler,'--version'],text=True).splitlines()[0],
        compilerFlags=flags,host=platform.machine(),results=result,physicalDeviceTested=False,gameplayMeasured=False,
        scope=__doc__)
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()

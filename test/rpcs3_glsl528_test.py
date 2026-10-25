#!/usr/bin/env python3
"""Execute exact Vulkan shader compile bodies with source/storage/module adapters.

No GPU or compiler timing is inferred: this measures eligibility for cold text
archiving after a successful module creation, with the real ColdSource client.
"""
import argparse,hashlib,json,os,shlex,subprocess,tempfile
from pathlib import Path
from rpcs3_memory523_test import braced
ROOT=Path(__file__).resolve().parents[1];BASE='6c6604a70a6837b4d461618b90a791934d6c65b3';PATH='rpcs3/Emu/RSX/VK/VKProgramPipeline.cpp'
def main():
 p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--report',type=Path);a=p.parse_args();source=a.source.resolve();m=json.loads(subprocess.check_output(['git','show',BASE+':build-utils/rpcs3/canonical-source.json'],cwd=ROOT))
 cxx=shlex.split(os.environ.get('CXX','c++'))
 if sdk:=os.environ.get('HOST_MACOS_SDK'):cxx+=['-isysroot',sdk]
 with tempfile.TemporaryDirectory(prefix='glsl528-') as tmp:
  w=Path(tmp);old=w/'old';f=old/PATH;f.parent.mkdir(parents=True)
  f.write_bytes(subprocess.check_output(['git','show',m['upstream_commit']+':'+PATH],cwd=source));patch=w/'delta.patch';patch.write_bytes(subprocess.check_output(['git','show',BASE+':build-utils/rpcs3/embedded-core.patch'],cwd=ROOT));subprocess.run(['git','apply','--include',PATH,str(patch)],cwd=old,check=True)
  assert hashlib.sha256(f.read_bytes()).hexdigest()==m['files_sha256'][PATH]
  for variant,text in [('before',f.read_text()),('after',(source/PATH).read_text())]:(w/(variant+'.inc')).write_text(braced(text,'VkShaderModule shader::compile()'))
  results={}
  for variant in ['before','after']:
   cmd=cxx+['-std=c++20','-O1','-g','-Wall','-Wextra','-Werror','-pthread','-DRPCS3_IOS','-I'+str(w),'-I'+str(source/'rpcs3')]+(['-DGLSL_REFERENCE'] if variant=='before' else [])
   exe=w/variant;subprocess.run(cmd+[str(ROOT/'test/native/rpcs3_glsl528.cpp'),str(source/'rpcs3/ios/NeoSwapStorage/SourceClient.cpp'),'-fsanitize=address,undefined','-fno-omit-frame-pointer','-o',str(exe)],check=True)
   r=subprocess.run([str(exe)],capture_output=True,text=True,timeout=60,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'));assert r.returncode==0,(variant,r.stdout,r.stderr);results[variant]=json.loads(r.stdout)
   subprocess.run(cmd+[str(ROOT/'test/native/rpcs3_glsl528.cpp'),'-fno-exceptions','-fsyntax-only'],check=True)
  assert results['before']['admissions']==5 and results['after']['admissions']==2
  assert results['before']['moduleCalls']==results['after']['moduleCalls']==5
  report={'passed':True,'sanitized':True,'noExceptionsConsumerVerified':True,'physicalDeviceTested':False,'before':results['before'],'after':results['after'],'scope':'exact shader compile body, real source client; module/compiler/archive API adapters; no GPU/gameplay timing'}
 if a.report:a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Execute actual before/after release and STORE128 bodies with controlled boundaries."""
import argparse,hashlib,json,os,shlex,subprocess,tempfile
from pathlib import Path
from rpcs3_memory523_test import braced
ROOT=Path(__file__).resolve().parents[1]
BASE='2fa4ad668446b9166017b434e302836287d015b0'
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--report',type=Path);a=p.parse_args()
 source=a.source.resolve();path='rpcs3/Emu/Cell/SPUThread.cpp'
 manifest=json.loads(subprocess.check_output(['git','show',BASE+':build-utils/rpcs3/canonical-source.json'],cwd=ROOT))
 cxx=shlex.split(os.environ.get('CXX','c++'))
 if sdk:=os.environ.get('HOST_MACOS_SDK'):cxx+=['-isysroot',sdk]
 reports={}
 with tempfile.TemporaryDirectory(prefix='cell536-') as tmp:
  w=Path(tmp);old=w/'baseline'/path;old.parent.mkdir(parents=True)
  old.write_bytes(subprocess.check_output(['git','show',manifest['upstream_commit']+':'+path],cwd=source))
  patch=w/'baseline.patch';patch.write_bytes(subprocess.check_output(['git','show',BASE+':build-utils/rpcs3/embedded-core.patch'],cwd=ROOT))
  subprocess.run(['git','apply','--include',path,str(patch)],cwd=w/'baseline',check=True)
  assert sha(old.read_bytes())==manifest['files_sha256'][path]
  texts={'before':old.read_text(),'after':(source/path).read_text()}
  common='#include <atomic>\n#include <cassert>\n#include <cstdint>\n#include <cstring>\n#include <thread>\n#include <utility>\n#include <initializer_list>\n'
  for test,anchor in [('writer','writer_lock::~writer_lock() noexcept'),('store','void do_cell_atomic_128_store(u32 addr, const void* to_write)\n{')]:
   code=common+'#define RPCS3_IOS 1\n'
   extracted={}
   for mode,text in texts.items():
    body=braced(text,anchor);extracted[mode]=sha(body.encode())
    code+='namespace '+mode+' {\n'+(ROOT/f'test/native/rpcs3_{test}536_adapter.inc').read_text()+'\n'
    code+=('namespace vm {\n'+body+'\n}\n' if test=='writer' else body)+'\n}\n'
   code+='int main(){before::test(false);after::test(true);}\n'
   cpp=w/(test+'.cpp');cpp.write_text(code);exe=w/test
   flags=['-std=c++20','-O1','-g','-pthread','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer']
   subprocess.run(cxx+flags+[str(cpp),'-o',str(exe)],check=True)
   subprocess.run([str(exe)],check=True,timeout=30,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'))
   reports[test]=dict(passed=True,productionBodySHA256=extracted)
  exe=w/'configuration'
  subprocess.run(cxx+flags+['-I'+str(source/'rpcs3'),str(ROOT/'test/native/rpcs3_shader_configuration536.cpp'),'-o',str(exe)],check=True)
  subprocess.run([str(exe)],check=True,timeout=30,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'))
  reports['configuration']=dict(passed=True,concurrentPublications=10000)
 result=dict(passed=True,sanitized=True,baseline=BASE,physicalDeviceTested=False,gameplayMeasured=False,results=reports,scope='Production destructor and complete STORE128 body, controlled VM/RSX/CPU boundaries; actual concurrent atomics and configuration snapshot. No real GPU readback or guest timing.')
 if a.report:a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()

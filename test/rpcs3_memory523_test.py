#!/usr/bin/env python3
"""Compare the production VM serializer, byte for byte, with Build 522.

The portable adapter copies a serial byte stream and counts transfers. Timings
cover this component only, without storage, ZSTD, CELL execution or an iPhone.
"""
import argparse,json,os,shlex,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def braced(text,start):
 a=text.index(start);b=text.index('{',a)+1;depth=1
 while depth:depth+=(text[b]=='{')-(text[b]=='}');b+=1
 return text[a:b]
def main():
 p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--before',type=Path)
 p.add_argument('--report',type=Path);p.add_argument('--benchmark',action='store_true');p.add_argument('--sanitize',action='store_true');a=p.parse_args()
 source=(a.source/'rpcs3/Emu/Memory/vm.cpp').read_text()
 with tempfile.TemporaryDirectory(prefix='memory523-') as d:
  w=Path(d)
  if a.before:before=(a.before/'rpcs3/Emu/Memory/vm.cpp').read_text()
  else:
   import shutil
   previous=w/'previous'
   metadata=json.loads((ROOT/'build-utils/rpcs3/canonical-source.json').read_text())['cell523']
   for relative in metadata['paths']:
    target=previous/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(a.source/relative,target)
   subprocess.run(['git','apply','--unidiff-zero','--reverse',str(ROOT/'test/fixtures/rpcs3_restore523.diff')],cwd=previous,check=True)
   import hashlib
   for relative,expected in metadata['before_sha256'].items():assert hashlib.sha256((previous/relative).read_bytes()).hexdigest()==expected,relative
   before=(previous/'rpcs3/Emu/Memory/vm.cpp').read_text()
  for name,body in [('before',before),('after',source)]:
   (w/(name+'.inc')).write_text(braced(body,'static void serialize_memory_bytes(')+'\n')
  (w/'zero.inc').write_text(braced(source,'static bool check_cache_line_zero(')+'\n')
  cxx=shlex.split(os.environ.get('CXX','c++'))
  if sdk:=os.environ.get('HOST_MACOS_SDK'):cxx+=['-isysroot',sdk]
  cmd=cxx+['-std=c++20','-O3','-g','-Wall','-Wextra','-Werror','-DRPCS3_IOS','-I'+str(w),str(ROOT/'test/native/rpcs3_memory523.cpp'),'-o',str(w/'test')]
  if a.sanitize:cmd+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
  subprocess.run(cmd,check=True)
  r=subprocess.run([str(w/'test')]+(['benchmark'] if a.benchmark else []),capture_output=True,text=True,timeout=180,
    env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'))
  if r.returncode:print(r.stderr,flush=True);r.check_returncode()
  record=json.loads(r.stdout);record.update(sanitizers=a.sanitize,scope='production VM methods; portable serial copy adapter; no game/device/storage timing')
  subprocess.run(cxx+['-std=c++20','-O1','-DRPCS3_IOS','-fno-exceptions','-I'+str(w),'-fsyntax-only',str(ROOT/'test/native/rpcs3_memory523.cpp')],check=True)
  if a.report:a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(record,indent=2)+'\n')
  print(json.dumps(record,indent=2))
if __name__=='__main__':main()

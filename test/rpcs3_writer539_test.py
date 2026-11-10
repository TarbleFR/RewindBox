#!/usr/bin/env python3
"""Actual before/after writer counters: concurrent readers, overflow and retirement."""
import argparse,hashlib,json,os,shlex,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sha=lambda b:hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--report',type=Path);a=p.parse_args()
 manifest=json.loads((ROOT/'build-utils/rpcs3/canonical-source.json').read_bytes());rec=manifest['cell539']
 relative='rpcs3/ios/RPCS3IOSWriterCounters.h'
 cxx=shlex.split(os.environ.get('CXX','c++'))
 if sdk:=os.environ.get('HOST_MACOS_SDK'):cxx+=['-isysroot',sdk]
 with tempfile.TemporaryDirectory(prefix='writer539-') as td:
  w=Path(td);before=w/'before'
  for path in rec['modified_paths']:
   t=before/path;t.parent.mkdir(parents=True,exist_ok=True);t.write_bytes((a.source/path).read_bytes())
  subprocess.run(['git','apply','--reverse',str(ROOT/'test/fixtures/rpcs3_cell539.diff')],cwd=before,check=True)
  assert sha((before/relative).read_bytes())==rec['before_sha256'][relative]
  for label,tree in [('before',before),('after',a.source)]:
   text=(tree/relative).read_text().replace('namespace rpcs3::ios::diagnostics {','namespace '+label+' {')
   (w/(label+'.h')).write_text(text)
  common=cxx+['-std=c++20','-O2','-g','-Wall','-Wextra','-Werror','-pthread','-I'+str(w)]
  source=str(ROOT/'test/native/rpcs3_writer539.cpp');exe=w/'test'
  subprocess.run(common+['-fsanitize=address,undefined','-fno-omit-frame-pointer',source,'-o',str(exe)],check=True)
  run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=120,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'))
  if run.returncode:print(run.stderr);run.check_returncode()
  sanitized=json.loads(run.stdout)
  # Separate optimized timings from the correctness run with sanitizers.
  subprocess.run(common+[source,'-o',str(exe)],check=True)
  optimized=json.loads(subprocess.check_output([str(exe)],text=True,timeout=120))
  # Retain the actual target assembly; native CI compiles this on macOS ARM64.
  asm=w/'writers.cpp';asm.write_text('#include "before.h"\n#include "after.h"\nextern "C" void writer_before(before::WriterCounters* c,unsigned s,uint64_t a,uint64_t h){c->record(s,a,h);}\nextern "C" void writer_after(after::WriterCounters* c,unsigned s,uint64_t a,uint64_t h){c->record(s,a,h);}\n')
  assembly=w/'writers.s';subprocess.run(common+['-S',str(asm),'-o',str(assembly)],check=True)
  if a.report:assembly_target=a.report.with_suffix('.s');assembly_target.parent.mkdir(parents=True,exist_ok=True);assembly_target.write_bytes(assembly.read_bytes())
  result=dict(passed=True,sanitized=sanitized,optimized=optimized,assemblySHA256=sha(assembly.read_bytes()),counterSourceSHA256=sha((a.source/relative).read_bytes()),physicalDeviceTested=False,gameplayMeasured=False,
   scope='Actual header, 96 live writers and two reporters, exact aggregate counts/times/maxima, slot retirement, object recreation and unsigned wrap. Five-trial short host benchmark and seven-trial warmed persistent-worker benchmark with raw samples; not guest reservation or iPhone frame time.')
  if a.report:a.report.write_text(json.dumps(result,indent=2)+'\n')
  print(json.dumps(result,indent=2))
if __name__=='__main__':main()

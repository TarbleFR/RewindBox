#!/usr/bin/env python3
"""Supplement the immutable539 microtest with per-thread CPU time, outside the hot loop."""
import argparse,hashlib,json,os,platform,shlex,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CORE='5987bcfe9d9c3e5b746c09dfc5e8980b0af203d7'
sha=lambda b:hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
 inputs=['build-utils/rpcs3/canonical-source.json','test/fixtures/rpcs3_cell539.diff','test/native/rpcs3_writer539.cpp']
 for name in inputs:assert (ROOT/name).read_bytes()==subprocess.check_output(['git','show',CORE+':'+name],cwd=ROOT),name
 manifest=json.loads((ROOT/inputs[0]).read_bytes());rec=manifest['cell539'];relative='rpcs3/ios/RPCS3IOSWriterCounters.h'
 assert sha((a.source/relative).read_bytes())==manifest['files_sha256'][relative]
 cxx=shlex.split(os.environ.get('CXX','c++'))
 if sdk:=os.environ.get('HOST_MACOS_SDK'):cxx+=['-isysroot',sdk]
 with tempfile.TemporaryDirectory(prefix='writer539-cpu-') as td:
  w=Path(td);before=w/'before'
  for name in rec['modified_paths']:
   dest=before/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((a.source/name).read_bytes())
  subprocess.run(['git','apply','--reverse',str(ROOT/inputs[1])],cwd=before,check=True)
  assert sha((before/relative).read_bytes())==rec['before_sha256'][relative]
  for label,tree in [('before',before),('after',a.source)]:
   s=(tree/relative).read_text().replace('namespace rpcs3::ios::diagnostics {','namespace '+label+' {')
   (w/(label+'.h')).write_text(s)
  s=(ROOT/inputs[2]).read_text()
  s='#include <time.h>\n#include <numeric>\n'+s
  s=s.replace('void steady_bench(unsigned threads) {','uint64_t thread_cpu_ns(){timespec t{};const int rc=clock_gettime(CLOCK_THREAD_CPUTIME_ID,&t);assert(rc==0);return uint64_t(t.tv_sec)*1000000000+uint64_t(t.tv_nsec);}\nvoid steady_bench(unsigned threads) {')
  s=s.replace('std::array<double,trials> a{},b{};','std::array<double,trials> a{},b{},cpu_a{},cpu_b{};std::vector<double> worker_cpu(threads);')
  s=s.replace('start.arrive_and_wait();\n   const bool updated','start.arrive_and_wait();\n   const auto cpu_begin=thread_cpu_ns();\n   const bool updated')
  s=s.replace('   finish.arrive_and_wait();','   worker_cpu[t]=(thread_cpu_ns()-cpu_begin)/1000000.0;\n   finish.arrive_and_wait();')
  s=s.replace(' (updated?b:a)[trial]=',' (updated?cpu_b:cpu_a)[trial]=std::accumulate(worker_cpu.begin(),worker_cpu.end(),0.0);\n  (updated?b:a)[trial]=')
  s=s.replace('print("beforeSamplesMs",a);print("afterSamplesMs",b);','print("beforeSamplesMs",a);print("afterSamplesMs",b);print("beforeCpuSamplesMs",cpu_a);print("afterCpuSamplesMs",cpu_b);\n std::sort(cpu_a.begin(),cpu_a.end());std::sort(cpu_b.begin(),cpu_b.end());std::cout<<",\\\"beforeCpuMedianMs\\\":"<<cpu_a[trials/2]<<",\\\"afterCpuMedianMs\\\":"<<cpu_b[trials/2];')
  for token in ['const auto cpu_begin','worker_cpu[t]=','std::accumulate','beforeCpuMedianMs']:assert token in s,token
  source=w/'cpu.cpp';source.write_text(s);exe=w/'test'
  flags=['-std=c++20','-O2','-g','-Wall','-Wextra','-Werror','-pthread','-I'+str(w)]
  subprocess.run(cxx+flags+[str(source),'-o',str(exe)],check=True)
  result=json.loads(subprocess.check_output([str(exe)],text=True,timeout=180))
  assert result['accuracy'] and result['hardwareConcurrency']>0
  for case in result['steadyState']:
   assert len(case['beforeCpuSamplesMs'])==len(case['afterCpuSamplesMs'])==7
   assert all(v>0 for v in case['beforeCpuSamplesMs']+case['afterCpuSamplesMs'])
  inputs+=['test/rpcs3_writer539_cpu_test.py','.github/workflows/rpcs3-writer539-cpu.yml']
  report=dict(passed=True,coreSource=CORE,source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
   inputSHA256={p:sha((ROOT/p).read_bytes()) for p in inputs},counterSHA256=sha((a.source/relative).read_bytes()),
   beforeCounterSHA256=sha((before/relative).read_bytes()),generatedHarnessSHA256=sha(source.read_bytes()),
   compiler=subprocess.check_output(cxx[:1]+['--version'],text=True),platform=platform.platform(),machine=platform.machine(),
   measurements=result,physicalDeviceTested=False,gameplayMeasured=False,
   scope='Actual immutable before/after headers. Two CLOCK_THREAD_CPUTIME_ID calls per million-event worker loop, no timing in record. CPU samples sum all workers; wall windows still include scheduling. Original correctness/short benchmarks retained. CPU time does not measure gameplay or eliminate frequency/cache effects.')
  a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()

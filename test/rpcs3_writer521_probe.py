"""Measure relocating diagnostics after the unchanged CELL unlock/wakeup protocol."""
import argparse,hashlib,json,os,platform,shlex,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def braced(text,start):
 a=text.index(start);b=text.index('{',a)+1;depth=1
 while depth:depth+=int(text[b]=='{')-int(text[b]=='}');b+=1
 return text[a:b]
def variants(source):
 text=(source/'rpcs3/Emu/Cell/SPUThread.cpp').read_text();before=braced(text,'writer_lock::~writer_lock() noexcept')
 a=before.index('#ifdef RPCS3_IOS');b=before.index('#endif',a)+len('#endif');after=before[:a]+before[b:]
 for release in ['range_lock->release(0);','g_range_lock_bits[1].release(0);']:
  after=after.replace(release,release+'\n#ifdef RPCS3_IOS\n\t\tconst u64 released = utils::get_tsc();\n#endif')
 record='\n#ifdef RPCS3_IOS\n\t\trpcs3::ios::record_writer_lock(source, acquire_ticks, released >= acquired_tsc ? released - acquired_tsc : 0);\n#endif\n'
 after=after.replace('\t\t\treturn;',record+'\t\t\treturn;')
 a=after.rindex('\n\t}');after=after[:a]+record+after[a:]
 return before,after
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--sanitize',action='store_true');a=p.parse_args();source=a.source.resolve()
 before,after=variants(source);profile=(source/'rpcs3/ios/RPCS3IOSPerformance.cpp').read_text()
 recorder=braced(profile,'void record_writer_lock(u32 source, u64 acquire_ticks, u64 hold_ticks) noexcept')
 maximum=braced(profile,'static void update_max(std::atomic<u64>& target, u64 value) noexcept')
 out=ROOT/'build/rpcs3-writer521-probe';out.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory(prefix='writer521-') as directory:
  work=Path(directory)
  for name,body in [('before',before),('after',after),('recorder',recorder),('maximum',maximum)]:
   (work/('writer521-'+name+'.inc')).write_text(body+'\n')
  cxx=shlex.split(os.environ.get('CXX','c++'))
  if sdk:=os.environ.get('HOST_MACOS_SDK'):cxx+=['-isysroot',sdk]
  if platform.machine() in ('arm64','aarch64'):cxx+=['-march=armv8.4-a']
  flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if a.sanitize else []
  subprocess.run([*cxx,'-std=c++20','-O3','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-pthread','-DRPCS3_IOS',*flags,'-I',str(work),'-I',str(ROOT/'test/native'),str(ROOT/'test/native/rpcs3_writer521_probe.cpp'),'-o',str(work/'probe')],check=True)
  subprocess.run([str(work/'probe'),str(out/'measurements.json')],check=True,timeout=300,env=dict(os.environ,WRITER_PROBE_ITERATIONS='3000') if a.sanitize else None)
  (out/'candidate-destructor.txt').write_text(after+'\n')
 report=json.loads((out/'measurements.json').read_text());report.update(source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
  originalDestructorSHA256=hashlib.sha256(before.encode()).hexdigest(),candidateDestructorSHA256=hashlib.sha256(after.encode()).hexdigest(),
  recordMethodSHA256=hashlib.sha256(recorder.encode()).hexdigest(),maximumMethodSHA256=hashlib.sha256(maximum.encode()).hexdigest(),
  method='15 rotated three-variant rounds, discard first 3; median/min/max of 12 rounds; 300000 operations per thread (3000 with sanitizers); includes acquisition, protected payload and 3 atomic counters + maximum',
  platform=platform.platform(),hardware=subprocess.check_output(['sysctl','-n','machdep.cpu.brand_string'],text=True).strip() if platform.system()=='Darwin' else platform.machine(),
  sanitizer=a.sanitize,productionChanged=False,shardHeaderSHA256=hashlib.sha256((ROOT/'test/native/rpcs3_writer521_shards.h').read_bytes()).hexdigest())
 (out/'measurements.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))

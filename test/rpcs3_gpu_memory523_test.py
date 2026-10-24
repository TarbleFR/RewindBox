#!/usr/bin/env python3
"""Execute the actual nonblocking GPU pool snapshot against a portable registry."""
import argparse,json,os,shlex,subprocess,tempfile
from pathlib import Path
from rpcs3_memory523_test import braced
ROOT=Path(__file__).resolve().parents[1]
def run(source,report):
 text=(source/'rpcs3/Emu/RSX/VK/VKResourceManager.cpp').read_text()
 snapshot=braced(text,'rpcs3::ios::graphics_memory_snapshot rpcs3::ios::capture_graphics_memory_snapshot() noexcept')
 helper=braced(text,'u64 vmm_get_application_pool_usage_impl(')
 reset=braced(text,'void vmm_reset()');assert reset.index('std::lock_guard lock(g_vmm_stats.mutex);')<reset.index('g_vmm_stats.clear();')
 perf=(source/'rpcs3/ios/RPCS3IOSPerformance.cpp').read_text();assert perf.count('const auto gpu_memory = capture_graphics_memory_snapshot();')==1
 assert 'gpu_pool_scope=requested_allocation_bytes_not_physical_ram' in perf and 'gpu_pools_valid=%u' in perf
 with tempfile.TemporaryDirectory(prefix='gpu-memory523-') as d:
  w=Path(d);(w/'snapshot.inc').write_text(snapshot);(w/'helper.inc').write_text(helper)
  cxx=shlex.split(os.environ.get('CXX','c++'))
  if sdk:=os.environ.get('HOST_MACOS_SDK'):cxx+=['-isysroot',sdk]
  common=cxx+['-std=c++20','-O1','-g','-Wall','-Wextra','-Werror','-pthread','-I'+str(w),'-I'+str(source/'rpcs3'),str(ROOT/'test/native/rpcs3_gpu_memory523.cpp')]
  subprocess.run(common+['-fsanitize=address,undefined','-fno-omit-frame-pointer','-o',str(w/'test')],check=True)
  r=subprocess.run([str(w/'test')],capture_output=True,text=True,timeout=90,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'))
  if r.returncode:print(r.stderr,flush=True);r.check_returncode()
  subprocess.run(common+['-fno-exceptions','-fsyntax-only'],check=True)
  result=dict(passed=True,stdout=r.stdout.strip(),actualSnapshot=True,actualPoolLookup=True,sanitizers=True,
   scope='production snapshot/getter; portable registry/shared mutex; no GPU residency/device measurement')
  if report:report.parent.mkdir(parents=True,exist_ok=True);report.write_text(json.dumps(result,indent=2)+'\n')
  print(json.dumps(result,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--report',type=Path);a=p.parse_args();run(a.source.resolve(),a.report)

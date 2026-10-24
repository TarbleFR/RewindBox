"""Compile the actual sharded writer recorder and drain integration with sanitizers."""
import argparse,os,shlex,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def braced(text,start):
 a=text.index(start);b=text.index('{',a)+1;depth=1
 while depth:depth+=int(text[b]=='{')-int(text[b]=='}');b+=1
 return text[a:b]
def run(source):
 text=(source/'rpcs3/ios/RPCS3IOSPerformance.cpp').read_text()
 assert (source/'rpcs3/ios/RPCS3IOSWriterCounters.h').read_bytes()==(ROOT/'test/native/rpcs3_writer521_shards.h').read_bytes()
 record=braced(text,'void record_writer_lock(u32 source, u64 acquire_ticks, u64 hold_ticks) noexcept')
 start=text.index('const auto writer_totals = m_writer_counters.drain();');loop=text.index('for (usz source',start)
 drain=text[start:loop]+braced(text[loop:],'for (usz source')
 assert 'static_cast<void>(m_writer_counters.drain());' in text
 with tempfile.TemporaryDirectory(prefix='writer522-') as directory:
  work=Path(directory);(work/'record.inc').write_text(record+'\n');(work/'drain.inc').write_text(drain+'\n')
  cpp=work/'test.cpp';cpp.write_text(r'''
#include "ios/RPCS3IOSWriterCounters.h"
#include <atomic>
#include <array>
#include <cassert>
#include <thread>
#include <vector>
#include <iostream>
using u64=uint64_t;using u32=uint32_t;using usz=size_t;
struct Registry {
 static constexpr usz writer_lock_source_count=5;
 rpcs3::ios::diagnostics::WriterCounters m_writer_counters;
 std::array<std::atomic<u64>,5> m_writer_lock_avoided{};
 #include "record.inc"
 auto take(){
  std::array<u64,5> writer_count{},writer_acquire{},writer_hold{},writer_avoided{},writer_hold_max{};
  #include "drain.inc"
  std::array<rpcs3::ios::diagnostics::WriterCounters::Total,5> result{};
  for(usz i=0;i<5;++i)result[i]={writer_count[i],writer_acquire[i],writer_hold[i],writer_hold_max[i]};
  return result;
 }
};
int main(){
 Registry registry;
 std::atomic<bool> go{false};std::atomic<unsigned> done{0};std::vector<std::thread> workers;
 constexpr unsigned threads=96,iterations=3000;
 for(unsigned t=0;t<threads;++t)workers.emplace_back([&,t]{
  while(!go.load(std::memory_order_acquire))std::this_thread::yield();
  for(unsigned n=0;n<iterations;++n)registry.record_writer_lock(t%6,3,7);
  ++done;
 });
 u64 count=0,acquire=0,hold=0,maximum=0;go=true;
 const auto drain=[&]{for(auto total:registry.take()){count+=total.count;acquire+=total.acquire;hold+=total.hold;maximum=std::max(maximum,total.maximum);}};
 while(done!=threads){drain();std::this_thread::yield();}
 for(auto& worker:workers)worker.join();drain();
 assert(count==u64(threads)*iterations&&acquire==count*3&&hold==count*7&&maximum==7);
 for(auto total:registry.take())assert(!total.count&&!total.acquire&&!total.hold&&!total.maximum);
 registry.record_writer_lock(999,9,11);auto invalid=registry.take();assert(invalid[0].count==1&&invalid[0].acquire==9&&invalid[0].hold==11&&invalid[0].maximum==11);
 std::cout<<"PASS production recorder/drain, 96 threads, 64 bounded shards, collisions, concurrent snapshots, exact counts/sums/maxima, invalid source and empty reset\n";
}
''')
  cxx=shlex.split(os.environ.get('CXX','c++'))
  if sdk:=os.environ.get('HOST_MACOS_SDK'):cxx+=['-isysroot',sdk]
  common=[*cxx,'-std=c++20','-O1','-g','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-pthread','-I',str(work),'-I',str(source/'rpcs3'),str(cpp)]
  subprocess.run([*common,'-fsanitize=address,undefined','-o',str(work/'test')],check=True)
  subprocess.run([str(work/'test')],check=True,timeout=90,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'))
  subprocess.run([*common,'-fno-exceptions','-fsyntax-only'],check=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source',type=Path);a=p.parse_args();run(a.source.resolve())

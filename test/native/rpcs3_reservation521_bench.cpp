// SPDX-License-Identifier: GPL-2.0-only
#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <sys/mman.h>
#include <unistd.h>
#include <vector>
extern "C" bool baseline_compare(const uint8_t*,const uint8_t*);
extern "C" bool xor_compare(const uint8_t*,const uint8_t*);
extern "C" bool equality_compare(const uint8_t*,const uint8_t*);
using Fn=bool(*)(const uint8_t*,const uint8_t*);
static constexpr std::array<Fn,3> functions{baseline_compare,xor_compare,equality_compare};
static constexpr const char* names[]{"original_multiply_accumulate","xor_tree","equality_tree"};
struct alignas(128) Pair {std::array<uint8_t,128> a,b;};
static void check(bool b){if(!b)std::abort();}
static uint64_t seed=0x182547ac918e2211;
static uint8_t random_byte(){seed^=seed<<13;seed^=seed>>7;seed^=seed<<17;return uint8_t(seed);}
int main(int argc,char** argv){
 check(argc==2);
 Pair p{};unsigned checks=0;
 for(unsigned sample=0;sample<32;++sample){
  for(auto& v:p.a)v=random_byte();
  p.b=p.a;
  for(auto fn:functions){check(fn(p.a.data(),p.b.data()));++checks;}
  for(unsigned byte=0;byte<128;++byte)for(unsigned bit=0;bit<8;++bit){
   p.b[byte]^=uint8_t(1u<<bit);
   for(auto fn:functions){check(!fn(p.a.data(),p.b.data()));++checks;}
   p.b[byte]^=uint8_t(1u<<bit);
  }
 }
 for(unsigned sample=0;sample<65536;++sample){
  for(auto& v:p.a)v=random_byte();
  for(auto& v:p.b)v=random_byte();
  const bool expected=std::memcmp(p.a.data(),p.b.data(),128)==0;
  for(auto fn:functions){check(fn(p.a.data(),p.b.data())==expected);++checks;}
 }
 const auto page=static_cast<size_t>(sysconf(_SC_PAGESIZE));
 auto* guard=static_cast<uint8_t*>(mmap(nullptr,page*4,PROT_NONE,MAP_PRIVATE|MAP_ANON,-1,0));
 check(guard!=MAP_FAILED&&mprotect(guard,page,PROT_READ|PROT_WRITE)==0&&mprotect(guard+2*page,page,PROT_READ|PROT_WRITE)==0);
 auto* a=guard+page-128;auto* b=guard+3*page-128;
 for(unsigned i=0;i<128;++i)a[i]=b[i]=random_byte();
 for(auto fn:functions){check(fn(a,b));b[127]^=1;check(!fn(a,b));b[127]^=1;checks+=2;}
 check(munmap(guard,page*4)==0);
 std::vector<Pair> pairs(4096);
 std::ofstream out(argv[1]);out<<"{\"correctnessChecks\":"<<checks<<",\"guardPages\":true,\"results\":[";
 bool comma=false;volatile uint64_t sink=0;
 for(unsigned count:{1u,4096u})for(unsigned pattern=0;pattern<3;++pattern){
  for(auto& pair:pairs){for(auto& v:pair.a)v=random_byte();pair.b=pair.a;if(pattern)pair.b[pattern==1?0:127]^=1;}
  std::array<std::vector<double>,3> times;
  constexpr unsigned repeats=2'000'000;
  for(unsigned round=0;round<14;++round)for(unsigned order=0;order<3;++order){
   const auto mode=(round+order)%3;const Fn fn=functions[mode];uint64_t total=0;
   const auto start=std::chrono::steady_clock::now();
   for(unsigned rep=0;rep<repeats;++rep){const auto& pair=pairs[rep&(count-1)];total+=fn(pair.a.data(),pair.b.data());}
   const auto elapsed=std::chrono::duration<double,std::nano>(std::chrono::steady_clock::now()-start).count()/repeats;
   sink=total;check(total==(pattern?0u:repeats));if(round>=2)times[mode].push_back(elapsed);
  }
  for(unsigned mode=0;mode<3;++mode){auto v=times[mode];std::sort(v.begin(),v.end());
   if(comma)out<<',';
   comma=true;
   out<<"{\"function\":\""<<names[mode]<<"\",\"pairs\":"<<count<<",\"pattern\":"<<pattern
      <<",\"medianNs\":"<<(v[5]+v[6])/2<<",\"minimumNs\":"<<v.front()<<",\"maximumNs\":"<<v.back()<<"}";
  }
 }
 (void)sink;out<<"],\"physicalIPhoneTested\":false,\"gameplayTested\":false}\n";
 std::printf("PASS %u comparisons, every differing bit, random inputs and guard pages; native ARM64 component timings only\n",checks);
}

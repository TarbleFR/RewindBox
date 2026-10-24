// SPDX-License-Identifier: MIT
// Actual VM serialization methods; only the host serial I/O adapter is portable.
#include <algorithm>
#include <array>
#include <bit>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <span>
#include <vector>
#include <cstdlib>
using u8=std::uint8_t;using u32=std::uint32_t;using u64=std::uint64_t;using usz=std::size_t;
template<class T>using le_t=T;
#define ensure(x) do{if(!(x)){std::cerr<<__FILE__<<':'<<__LINE__<<" assertion "<<#x<<'\n';std::abort();}}while(false)
using v128=u64 __attribute__((vector_size(16)));
bool gv_testz(v128 value){return !(value[0]|value[1]);}
template<class T,class P> T read_from_ptr_unsafe(const P& p,usz offset){T v;std::memcpy(&v,reinterpret_cast<const u8*>(p)+offset,sizeof(v));return v;}
template<class T> T read_from_ptr(const std::vector<u8>& p,usz offset){ensure(offset+sizeof(T)<=p.size());return read_from_ptr_unsafe<T>(p.data(),offset);}
namespace utils {
struct serial {
 bool writing;std::vector<u8> data;usz pos=0,calls=0,payload_calls=0,max_payload=0,breaths=0;bool first_span=true;
 bool is_writing()const{return writing;}
 void breathe(){++breaths;}
 void operator()(std::span<u8> bytes){
  const bool header=first_span&&!writing;first_span=false;
  if(!header){++payload_calls;max_payload=std::max(max_payload,bytes.size());}
  ++calls;
  if(bytes.empty())return;
  if(writing){ensure(pos+bytes.size()<=data.size());std::memcpy(data.data()+pos,bytes.data(),bytes.size());}
  else{ensure(pos+bytes.size()<=data.size());std::memcpy(bytes.data(),data.data()+pos,bytes.size());}
  pos+=bytes.size();
 }
 void operator()(u8& value){
  ensure(pos<data.size());if(writing)data[pos]=value;else value=data[pos];++pos;++calls;
 }
};
}
#include "zero.inc"
namespace before {
#include "before.inc"
}
namespace after {
#include "after.inc"
}
using Fn=void(*)(utils::serial&,u8*,usz);
constexpr std::array<Fn,2> functions{before::serialize_memory_bytes,after::serialize_memory_bytes};
std::vector<u8> image(usz bytes,unsigned pattern,u64 seed){
 std::vector<u8> result(bytes);
 for(usz line=0;line<bytes/128;++line){
  seed^=seed<<13;seed^=seed>>7;seed^=seed<<17;
  const bool present=pattern==1||(pattern==2&&line%2)||(pattern==3&&(seed&31)==0)||
    (pattern==4&&line%257<256)||(pattern==5&&(line==0||line+1==bytes/128))||
    (pattern==6&&(line%37)>4);
  if(present)for(usz j=0;j<128;++j)result[line*128+j]=static_cast<u8>(1+((j*13+line*7+seed)%255));
 }
 return result;
}
utils::serial write(Fn fn,std::vector<u8>& input){
 utils::serial s{true, std::vector<u8>(input.size()+input.size()/1024)};
 fn(s,input.data(),input.size());s.data.resize(s.pos);return s;
}
usz cases=0;
void check(usz bytes,unsigned pattern,u64 seed){
 auto input=image(bytes,pattern,seed);auto a=write(functions[0],input),b=write(functions[1],input);
 ensure(a.data==b.data&&a.breaths==b.breaths&&b.max_payload<=65536);
 for(auto fn:functions){
  // Fresh guest backing is zeroed, including all absent cache lines.
  utils::serial read{false,a.data};std::vector<u8> output(bytes+32,0);std::fill(output.end()-32,output.end(),0xa5);
  fn(read,output.data(),bytes);ensure(read.pos==a.data.size());
  ensure(std::equal(input.begin(),input.end(),output.begin()));
  ensure(std::all_of(output.end()-32,output.end(),[](auto x){return x==0xa5;}));
 }
 ++cases;
}
double elapsed(Fn fn,bool writing,std::vector<u8>& input,const std::vector<u8>& stream){
 utils::serial s{writing,writing?std::vector<u8>(input.size()+input.size()/1024):stream};
 std::vector<u8> output(writing?0:input.size());
 const auto start=std::chrono::steady_clock::now();
 for(unsigned i=0;i<12;++i){s.pos=0;s.calls=0;s.first_span=true;fn(s,writing?input.data():output.data(),input.size());}
 const double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count()/12;
 if(writing)ensure(s.pos==stream.size()&&std::equal(stream.begin(),stream.end(),s.data.begin()));
 if(!writing)ensure(output==input);
 return ms;
}
int main(int argc,char**){
 static_assert(std::endian::native==std::endian::little,"Portable adapter requires little endian; production uses le_t");
 for(usz n:{usz{0},usz{4096},usz{8192},usz{65536},usz{65536+4096},usz{1048576},usz{1048576+4096},usz{8*1048576}})
  for(unsigned pattern=0;pattern<7;++pattern)check(n,pattern,0x12345678);
 for(u64 seed=1;seed<=96;++seed)check(4096*(1+seed%97),6,seed*0x9e3779b9);
 // Dense bitmaps and run boundaries crossing the 64 KiB transfer ceiling.
 for(usz n:{usz{16*1048576},usz{64*1048576}})for(unsigned pattern:{0u,1u,3u,4u})check(n,pattern,123);
 auto dense=image(8*1048576,1,123);auto old=write(functions[0],dense),now=write(functions[1],dense);
 std::cout<<"{\"passed\":true,\"cases\":"<<cases<<",\"sameUncompressedBytes\":true,\"sameBreatheBoundaries\":true,\"maxPayloadTransfer\":"<<now.max_payload<<",\"densePayloadTransfersBefore\":"<<old.payload_calls<<",\"densePayloadTransfersAfter\":"<<now.payload_calls<<",\"measurements\":[";
 bool comma=false;
 if(argc>1)for(unsigned pattern:{0u,1u,3u,4u}){
  auto input=image(32*1048576,pattern,123);auto stream=write(functions[0],input).data;
  for(bool writing:{true,false})for(unsigned round=0;round<12;++round){
   double values[2];
   for(unsigned j=0;j<2;++j){unsigned variant=(round+j)%2;values[variant]=elapsed(functions[variant],writing,input,stream);}
   if(comma)std::cout<<',';
   comma=true;
   std::cout<<"{\"pattern\":"<<pattern<<",\"writing\":"<<(writing?"true":"false")<<",\"round\":"<<round<<",\"beforeMs\":"<<values[0]<<",\"afterMs\":"<<values[1]<<'}';
  }
 }
 std::cout<<"]}\n";
}

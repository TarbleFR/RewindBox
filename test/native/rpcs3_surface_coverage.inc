#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <concepts>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <random>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>
using u8=std::uint8_t;using u16=std::uint16_t;using u32=std::uint32_t;using u64=std::uint64_t;
using usz=std::size_t;
struct max_value{template<class T>operator T()const{return static_cast<T>(~T{0});}};constexpr max_value umax{};
#define ensure(x,...) assert(x)
#define AUDIT(x) assert(x)
template<class C>u32 size32(const C& c){return static_cast<u32>(c.size());}
namespace fmt{template<class...A>std::string format(const char* f,A...v){int n=std::snprintf(nullptr,0,f,v...);std::vector<char>b(n+1);std::snprintf(b.data(),b.size(),f,v...);return std::string(b.data(),n);}}
namespace utils{constexpr u32 get_page_size(){return 4096;}u32 aligned_div(u32 a,u32 b){return (a+b-1)/b;}}
@RANGE@
using utils::address_range32;
template<class T,class C>T read_from_ptr(const C& c,u32 offset){T value;std::memcpy(&value,reinterpret_cast<const u8*>(c.data())+offset,sizeof(T));return value;}
template<class T,class C,class V>void write_to_ptr(C& c,u32 offset,V value){T cast=value;std::memcpy(reinterpret_cast<u8*>(c.data())+offset,&cast,sizeof(T));}
template<class C>void write_to_ptr(C& c,u32 offset,u32 value){write_to_ptr<u32>(c,offset,value);}
struct Logger{template<class...A>void warning(const char*,A...){}template<class...A>void notice(const char*,A...){}}rsx_log;
namespace rsx{enum class surface_metrics{bytes,samples};using utils::address_range32;template<class T>using simple_array=std::vector<T>;}
struct Surface{
 u32 address,width,pitch,height;
 address_range32 get_memory_range()const{return address_range32::start_length(address,(height-1)*pitch+width);}
 u32 get_rsx_pitch()const{return pitch;}
 template<rsx::surface_metrics>u32 get_surface_width()const{return width;}
 template<rsx::surface_metrics>u32 get_surface_height()const{return height;}
};
struct surface_overlap_info{Surface* surface;u32 base_address;bool is_depth;};
struct Boundary{
 std::vector<std::pair<u32,bool>> invalidated;
 Boundary(){invalidated.reserve(512);}
 void invalidate_surface_address(u32 address,bool depth){invalidated.emplace_back(address,depth);}
};
struct Result{std::vector<bool> changed,covered;size_t storageBytes;};
@VERSIONS@
u64 rowChecks=0,geometryChecks=0,sink=0;
void rows(u32 length,const std::vector<std::pair<u32,u32>>& spans){
 auto range=address_range32::start_length(0x100000,length);before a;after b;desktop c;
 auto x=a.rows(range,spans),y=b.rows(range,spans),z=c.rows(range,spans);
 assert(x.changed==y.changed&&x.covered==y.covered&&x.changed==z.changed&&x.covered==z.covered);rowChecks+=spans.size();
}
void geometry(std::vector<Surface>& surfaces,const address_range32& range){
 std::vector<surface_overlap_info> sections;for(auto& s:surfaces){assert(s.get_memory_range().overlaps(range));sections.push_back({&s,s.address,(s.address&4)!=0});}
 before a;after b;desktop c;a.remove_duplicates_fallback_impl(sections,range);b.remove_duplicates_fallback_impl(sections,range);c.remove_duplicates_fallback_impl(sections,range);
 assert(a.invalidated==b.invalidated&&a.invalidated==c.invalidated);++geometryChecks;
}
template<class T>double bench(u32 length,u32 width,u32 pitch){
 std::vector<Surface> surfaces(12,Surface{0x100000,width,pitch,(length-width)/pitch+1});std::vector<surface_overlap_info> sections;
 for(auto& s:surfaces){sections.push_back({&s,s.address,false});}
 auto range=surfaces.front().get_memory_range();
 std::vector<double> samples;T test;constexpr int iterations=8;
 for(int round=0;round<5;++round){auto start=std::chrono::steady_clock::now();for(int i=0;i<iterations;++i){test.invalidated.clear();test.remove_duplicates_fallback_impl(sections,range);sink+=test.invalidated.size();}samples.push_back(std::chrono::duration<double,std::micro>(std::chrono::steady_clock::now()-start).count()/iterations);}
 std::sort(samples.begin(),samples.end());return samples[2];
}
int main(int argc,char**){
 for(u32 length:{1u,7u,8u,63u,64u,65u,127u,128u,129u,257u}){
  std::vector<std::pair<u32,u32>> spans;
  for(u32 start=0;start<=length;++start)for(u32 n=0;n<=length-start;++n){
   spans.emplace_back(start,n);spans.emplace_back(start,n);
   // Fresh coverage keeps every pair observable instead of saturating the
   // bitmap before testing later offsets and trailing masks.
   rows(length,{{start,n},{start,n}});
  }
  rows(length,spans);
  for(u32 start=0;start<length;++start){rows(length,{{start,1},{0,start},{start+1,length-start-1},{0,length}});}
 }
 rows(129,{{1,127},{0,1},{128,1},{0,129}});
 constexpr u32 max_span=64u*1024u*1024u-1u;
 rows(max_span,{{0,1},{63,65},{max_span-129,128},{max_span-65,64},{max_span-1,1},{max_span,0}});
 std::mt19937 random(595);
 for(int i=0;i<2000;++i){u32 length=1+random()%4096;std::vector<std::pair<u32,u32>> spans;for(int j=0;j<64;++j){u32 start=random()%(length+1);spans.emplace_back(start,random()%(length-start+1));}rows(length,spans);}
 for(int i=0;i<10000;++i){
  std::vector<Surface> surfaces;u32 low=~u32{0},high=0;auto base=(i%2)?0x100000u:0xffff0000u;
  for(u32 j=0,n=1+random()%32;j<n;++j){u32 width=1+random()%192,pitch=width+random()%65,height=1+random()%24,address=base+random()%4096;surfaces.push_back({address,width,pitch,height});low=std::min(low,address);high=std::max(high,surfaces.back().get_memory_range().end);}
  geometry(surfaces,address_range32::start_end(low,high));
 }
 // Explicit partial rows outside the tested range and multi-byte boundaries.
 for(u32 offset=0;offset<128;++offset){std::vector<Surface>s{{1000,80,128,4},{1000+offset,70,128,4},{1120,45,64,5}};geometry(s,address_range32::start_length(1128,256));}
 before a;after b;std::vector<std::pair<u32,u32>> spans{{0,4194304},{7,131}};auto range=address_range32::start_length(0x100000,4194304);auto x=a.rows(range,spans),y=b.rows(range,spans);assert(x.covered==y.covered);
 std::cout<<"{\"rowChecks\":"<<rowChecks<<",\"surfaceGeometryCases\":"<<geometryChecks<<",\"sameInvalidationsAndOrder\":true,\"baseline4MiBMarkerBytes\":"<<x.storageBytes<<",\"candidate4MiBMarkerBytes\":"<<y.storageBytes;
 if(argc>1){std::cout<<",\"benchmarks\":[";bool first=true;for(u32 length:{65536u,1048576u,8388608u})for(u32 width:{16u,256u,4096u}){if(!first)std::cout<<',';first=false;std::cout<<"{\"spanBytes\":"<<length<<",\"rowBytes\":"<<width<<",\"baselineUs\":"<<bench<before>(length,width,width*2)<<",\"candidateUs\":"<<bench<after>(length,width,width*2)<<"}";}std::cout<<']';}
 std::cout<<",\"sink\":"<<sink<<"}";
}

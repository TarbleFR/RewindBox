#include <algorithm>
#include <array>
#include <cassert>
#include <concepts>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <iostream>
#include <iterator>
#include <random>
#include <type_traits>
#include <unordered_set>
#include <utility>
#include <vector>
using u8=std::uint8_t;using u32=std::uint32_t;using u64=std::uint64_t;
template<class C>u32 size32(const C& c){return static_cast<u32>(c.size());}
template<class T>concept UnsignedInt=std::is_unsigned_v<T>;
#define ensure(x,...) assert(x)
#define AUDIT(x) assert(x)
namespace adapters {
inline u64 allocations=0,bytes=0;
inline std::unordered_set<void*> live;
template<size_t Align>void* malloc(size_t n){
 ++allocations;bytes+=n;constexpr size_t align=std::max(Align,alignof(void*));
 auto* p=std::aligned_alloc(align,(n+align-1)/align*align);assert(p);assert(live.insert(p).second);return p;
}
inline void free(void* p){assert(live.erase(p)==1);std::free(p);}
template<size_t Align>void* realloc(void* p,size_t old,size_t n){auto* out=malloc<Align>(n);std::memcpy(out,p,old);free(p);return out;}
}
@VERSIONS@
template<size_t Size,size_t Align>struct alignas(Align) Value{
 std::array<u8,Size> bytes{};
 bool operator==(const Value&)const=default;
};
u64 checks=0;
template<class A>auto values(const A& a){return std::vector<typename A::value_type>(a.begin(),a.end());}
template<class A>void fill(A& a,u32 n,u32 salt){
 a.resize(n);for(u32 i=0;i<n;++i)for(size_t j=0;j<a[i].bytes.size();++j)a[i].bytes[j]=static_cast<u8>(i*31+j+salt);
}
template<class A,class B,class C>void same(const A& a,const B& b,const C& c){
 assert(values(a)==values(b));assert(values(a)==values(c));
 assert(a.capacity()>=a.size()&&b.capacity()>=b.size()&&c.capacity()>=c.size());
 assert(reinterpret_cast<uintptr_t>(b.data())%alignof(typename B::value_type)==0);++checks;
}
template<class T>void exercise(){
 using A=before::simple_array<T>;using B=after::simple_array<T>;using C=desktop::simple_array<T>;
 static_assert(sizeof(A)==sizeof(B)&&alignof(A)==alignof(B));
 constexpr u32 local=std::max<u32>(64/sizeof(T),1);
 for(u32 x:{0u,1u,local,local+1,local+17,257u})for(u32 y:{0u,1u,local,local+1,local+17,257u})
 for(u32 reserve=0;reserve<4;++reserve){
  A a,a2;B b,b2;C c,c2;
  if(reserve&1){a.reserve(300);b.reserve(300);c.reserve(300);}
  if(reserve&2){a2.reserve(300);b2.reserve(300);c2.reserve(300);}
  fill(a,x,17);fill(b,x,17);fill(c,x,17);fill(a2,y,29);fill(b2,y,29);fill(c2,y,29);
  for(int repeat=0;repeat<3;++repeat){
   auto prior=adapters::allocations;b.swap(b2);assert(adapters::allocations==prior);
   a.swap(a2);c.swap(c2);same(a,b,c);same(a2,b2,c2);
  }
  auto prior=adapters::allocations;B moved(std::move(b));assert(adapters::allocations==prior);
  A oldmove(std::move(a));C desktopmove(std::move(c));same(oldmove,moved,desktopmove);same(a,b,c);
  prior=adapters::allocations;b2=std::move(moved);assert(adapters::allocations==prior);
  a2=std::move(oldmove);c2=std::move(desktopmove);same(a2,b2,c2);same(oldmove,moved,desktopmove);
  fill(a,local+19,7);fill(b,local+19,7);fill(c,local+19,7);same(a,b,c);
 }
 // Interleaved allocation, copy, clear and move operations expose stale owners
 // and moved-from reuse; the reference and desktop execute the same sequence.
 std::array<A,9> old;std::array<B,9> now;std::array<C,9> desktop;std::mt19937 random(595);
 for(int i=0;i<20000;++i){
  auto a=random()%9,b=random()%9;auto n=random()%130;
  switch(random()%6){
   case 0:fill(old[a],n,i);fill(now[a],n,i);fill(desktop[a],n,i);break;
   case 1:old[a].clear();now[a].clear();desktop[a].clear();break;
   case 2:old[a]=old[b];now[a]=now[b];desktop[a]=desktop[b];break;
   case 3:{auto prior=adapters::allocations;now[a].swap(now[b]);assert(adapters::allocations==prior);old[a].swap(old[b]);desktop[a].swap(desktop[b]);break;}
   case 4:{auto prior=adapters::allocations;now[a]=std::move(now[b]);assert(adapters::allocations==prior);old[a]=std::move(old[b]);desktop[a]=std::move(desktop[b]);break;}
   case 5:old[a].reserve(n);now[a].reserve(n);desktop[a].reserve(n);break;
  }
  for(size_t j=0;j<9;++j)same(old[j],now[j],desktop[j]);
 }
}
int main(){
 exercise<Value<1,1>>();exercise<Value<4,4>>();exercise<Value<40,8>>();exercise<Value<128,64>>();
 assert(adapters::live.empty());
 u64 old_alloc,old_bytes,new_alloc,new_bytes;
 {
  before::simple_array<Value<40,8>> a;after::simple_array<Value<40,8>> b;
  fill(a,4096,1);fill(b,4096,1);auto* original=b.data();
  auto n=adapters::allocations,z=adapters::bytes;before::simple_array<Value<40,8>> oldmove(std::move(a));
  old_alloc=adapters::allocations-n;old_bytes=adapters::bytes-z;
  n=adapters::allocations;z=adapters::bytes;after::simple_array<Value<40,8>> newmove(std::move(b));
  new_alloc=adapters::allocations-n;new_bytes=adapters::bytes-z;
  assert(values(oldmove)==values(newmove)&&newmove.data()==original&&new_alloc==0);
 }
 assert(adapters::live.empty());
 std::cout<<"{\"contentAndAlignmentChecks\":"<<checks<<",\"doubleFreeOrLeak\":false,\"candidateSwapOrMoveAllocations\":0,\"baseline4096RegionMoveAllocations\":"<<old_alloc<<",\"baseline4096RegionMoveBytes\":"<<old_bytes<<",\"candidate4096RegionMoveAllocations\":"<<new_alloc<<",\"candidate4096RegionMoveBytes\":"<<new_bytes<<",\"heapOwnershipTransferred\":true}";
}

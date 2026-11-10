#include <array>
#include <bit>
#include <cassert>
#include <cstdint>
#include <functional>
#include <iostream>
#include <stdexcept>
#include <type_traits>
#include <utility>
using u8=std::uint8_t;using u16=std::uint16_t;using u32=std::uint32_t;using u64=std::uint64_t;using s64=std::int64_t;using usz=std::size_t;
constexpr u64 umax=~u64{0};
#define ensure(x,...) assert(x)
u64 channel_notifies=0,spu_notifies=0;
// Deterministic atomic-operation boundary: callbacks receive a copy, a simulated
// competing commit causes retry, and publication occurs only on successful CAS.
// These adapters do not prove hardware atomic ordering or scheduler behavior.
template<class T>struct atomic_t{
 T value{};u64 generation=0;std::function<void()> before_commit;
 T load()const{return value;}operator T()const{return load();}
 void release(T x){value=x;++generation;}
 T exchange(T x){T old=value;release(x);return old;}
 auto fetch_op(auto f){
  using R=decltype(f(value));
  for(;;){T old=value,next=old;const auto gen=generation;
   if constexpr(std::is_void_v<R>){f(next);if(before_commit){auto cb=std::move(before_commit);before_commit={};cb();}if(gen!=generation)continue;release(next);return old;}
   else{bool success=f(next);if(!success)return std::pair<T,bool>{old,false};if(before_commit){auto cb=std::move(before_commit);before_commit={};cb();}if(gen!=generation)continue;release(next);return std::pair<T,bool>{old,true};}
  }
 }
 auto atomic_op(auto f){
  using R=decltype(f(value));
  if constexpr(std::is_void_v<R>){f(value);++generation;}
  else{auto result=f(value);++generation;return result;}
 }
 bool compare_and_swap_test(T old,T next){if(value!=old)return false;release(next);return true;}
 T fetch_and(T mask){return exchange(value&mask);}
 void notify_one(){++channel_notifies;}
};
// Production notification aliases target the high word of a 64-bit channel.
// The deterministic adapter records that notification without aliasing storage.
namespace utils{template<class T> T* bless(void*){static T notification_sink[2];return notification_sink;}}
namespace fmt{template<class...A>[[noreturn]]void throw_exception(const char*,A...){throw std::runtime_error("unexpected production exception");}}
enum class cpu_flag{again};
struct cpu_thread{struct State{void operator+=(cpu_flag){}}state;static cpu_thread* get_current(){return nullptr;}};
void busy_wait(u32){throw std::runtime_error("unexpected event lock left held");}
constexpr u32 SPU_EVENT_LR=0x400,SPU_EVENT_S1=0x200,SPU_EVENT_S2=0x100,SPU_EVENT_TM=0x20,SPU_EVENT_SN=2;
constexpr u32 SPU_EVENT_IMPLEMENTED=SPU_EVENT_LR|SPU_EVENT_TM|SPU_EVENT_SN|SPU_EVENT_S1|SPU_EVENT_S2;
// @THREAD_BEGIN@
struct spu_thread{
 struct ch_events_t{u32 events{};u8 locks{};bool waiting{},count{};u32 mask{};};
 spu_channel ch_snr1,ch_snr2;u32 snr_config=0;atomic_t<ch_events_t> ch_events;
 u32 raddr=0;std::array<u8,128>rdata{};u64 ch_dec_start_timestamp=0;
 bool is_stopped()const{return false;}void notify(){++spu_notifies;}
 bool reservation_check(u32,const std::array<u8,128>&){throw std::runtime_error("reservation path outside SNR test");}
 std::pair<u32,u32>read_dec(){throw std::runtime_error("timer path outside SNR test");}
 void arm_dec_interrupt(){throw std::runtime_error("timer path outside SNR test");}
 void push_snr(u32,u32);void set_events(u32);
 ch_events_t get_events(u64 mask_hint=umax,bool waiting=false,bool reading=false);
};
// @THREAD_END@
@VERSIONS@
u64 cases=0,beforeMissing=0,beforeSpurious=0,payloadChecks=0,notificationChecks=0,retryCases=0;
struct Outcome{u32 event_bits,payload,count,locks;bool event_count;u64 host_notifies,channel_notifies;};
template<class S>Outcome signal(u32 number,bool filled,bool occupied,bool waiting,u32 mask,bool to_or,u32 initial,u32 value){
 channel_notifies=spu_notifies=0;S s;auto& ch=number?s.ch_snr2:s.ch_snr1;
 using C=std::remove_reference_t<decltype(ch)>;
 s.snr_config=to_or?(1u<<number):0;
 ch.data.release((filled?C::bit_count:0)|(occupied?C::bit_occupy|C::bit_wait:0)|initial);
 if(occupied)ch.jostling_value.release(C::bit_occupy);
 typename S::ch_events_t events{};events.mask=mask;events.waiting=waiting;s.ch_events.release(events);
 s.push_snr(number,value);
 auto e=s.get_events(mask,true,true);
 assert(s.ch_events.load().count==false);
 return{e.events,occupied?static_cast<u32>(ch.jostling_value.load()):ch.get_value(),ch.get_count(),e.locks,e.count,spu_notifies,channel_notifies};
}
template<class C>void direct_channel_cases(){
 for(bool occupied:{false,true})for(bool postponed:{false,true})for(bool to_or:{false,true}){
  C c;c.data.release(C::bit_wait|(occupied?C::bit_occupy:0));if(occupied)c.jostling_value.release(C::bit_occupy);
  channel_notifies=0;auto r=c.push(0x55aa,to_or,postponed);
  assert(r.old_count==0&&r.count==1&&r.op_done&&r.notify);
  assert(channel_notifies==(postponed?0u:1u));
  assert(static_cast<u32>(occupied?c.jostling_value.load():c.data.load())==0x55aa);
  if(postponed){c.notify();assert(channel_notifies==1);}++notificationChecks;
 }
}
template<class S>void retry(bool corrected){
 for(u32 number:{0u,1u})for(bool to_or:{false,true}){
  S s;auto& ch=number?s.ch_snr2:s.ch_snr1;const u32 bit=SPU_EVENT_S1>>number;
  typename S::ch_events_t events{};events.mask=bit;events.waiting=true;s.ch_events.release(events);s.snr_config=to_or?(1u<<number):0;
  spu_notifies=0;
  ch.data.before_commit=[&]{s.push_snr(number,0x0f);assert(s.ch_events.load().count==corrected);};
  s.push_snr(number,0xf0);
  assert(ch.get_value()==(to_or?0xffu:0xf0u));
  assert(s.ch_events.load().locks==0&&spu_notifies==1);
  // Both versions happen to emit once in this two-writer schedule; which writer
  // causes it differs. The baseline loses the first empty->full publication.
  assert(s.get_events(bit,true,true).count);
  if(corrected)++retryCases;
 }
}
int main(){
 for(u32 number:{0u,1u})for(bool filled:{false,true})for(bool occupied:{false,true})for(bool waiting:{false,true})for(bool to_or:{false,true})
 for(u32 initial:{0u,1u,0x55aa55aau,0xffffffffu})for(u32 value:{0u,1u,0xaa55aa55u,0xffffffffu}){
  if(occupied&&filled)continue;
  if(!filled&&initial)continue;
  const u32 bit=SPU_EVENT_S1>>number;
  for(u32 mask:{0u,bit,SPU_EVENT_S1|SPU_EVENT_S2,bit==SPU_EVENT_S1?SPU_EVENT_S2:SPU_EVENT_S1}){
   auto old=signal<before::spu_thread>(number,filled,occupied,waiting,mask,to_or,initial,value);
   auto fresh=signal<after::spu_thread>(number,filled,occupied,waiting,mask,to_or,initial,value);
   const bool should_event=!filled;const bool should_count=should_event&&(mask&bit);
   assert(fresh.event_bits==(should_event?bit:0));assert(fresh.event_count==should_count);
   assert(fresh.host_notifies==u64(should_count&&waiting));assert(fresh.locks==0&&old.locks==0);
   assert(old.payload==fresh.payload&&old.count==fresh.count&&old.channel_notifies==fresh.channel_notifies);
   assert(fresh.payload==((to_or&&!occupied)?initial|value:value));
   if(should_event&&!(old.event_bits&bit))++beforeMissing;
   if(!should_event&&(old.event_bits&bit))++beforeSpurious;
   ++cases;++payloadChecks;
  }
 }
 direct_channel_cases<after::spu_channel>();
 for(u32 number:{0u,1u})for(bool to_or:{false,true}){
  after::spu_thread s;auto& ch=number?s.ch_snr2:s.ch_snr1;const u32 bit=SPU_EVENT_S1>>number;s.snr_config=to_or?(1u<<number):0;
  for(u32 cycle=0;cycle<128;++cycle){
   typename after::spu_thread::ch_events_t e{};e.mask=bit;s.ch_events.release(e);
   assert(!s.get_events(bit,true,true).count);spu_notifies=0;s.push_snr(number,cycle);
   auto event=s.get_events(bit,true,true);assert(event.count&&(event.events&bit)&&spu_notifies==1);
   u32 out=~cycle;assert(ch.try_pop(out)&&out==cycle&&ch.get_count()==0);++payloadChecks;
  }
 }
 retry<before::spu_thread>(false);retry<after::spu_thread>(true);
 assert(beforeMissing&&beforeSpurious);
 std::cout<<"{\"matrixCases\":"<<cases<<",\"baselineMissingEvents\":"<<beforeMissing<<",\"baselineSpuriousEvents\":"<<beforeSpurious
 <<",\"candidateEventMismatches\":0,\"payloadComparisons\":"<<payloadChecks<<",\"postponedAndJostlingCases\":"<<notificationChecks
 <<",\"deterministicCasRetryCases\":"<<retryCases<<",\"repeatPopRepushCycles\":512,\"sameChannelPayloadAndNotify\":true,\"eventLocksReleased\":true}";
}

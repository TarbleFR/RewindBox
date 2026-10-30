#include <algorithm>
#include <array>
#include <atomic>
#include <cstdint>
#include <cstring>
#include <initializer_list>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <thread>
#include <tuple>
#include <utility>
using u8=std::uint8_t;using u16=std::uint16_t;using u32=std::uint32_t;using u64=std::uint64_t;using u128=__uint128_t;using usz=std::size_t;
constexpr u64 umax=~u64{};
constexpr u64 operator""_u64(const char*,usz){return 0;}
constexpr u64 operator""_u32(const char*,usz){return 0;}
template<u64>struct perf_meter{explicit perf_meter(void* = nullptr){}~perf_meter(){}void reset(){}};
template<class T,usz Align=alignof(T)>struct alignas(Align) atomic_t{
 T v{};operator T()const{return v;}void release(T x){v=x;}atomic_t& operator+=(T x){v+=x;return *this;}
 template<class F>std::pair<T,bool>fetch_op(F&&f){T old=v;return {old,f(v)};}
 template<class F>void atomic_op(F&&f){f(v);}
};
struct alignas(16)v128{u8 b[16];};
struct alignas(16)spu_rdata_t{u8 b[128];u8&operator[](usz i){return b[i];}};
void mov_rdata(spu_rdata_t&d,const spu_rdata_t&s){std::memcpy(&d,&s,128);}
bool cmp_rdata(const spu_rdata_t&a,const spu_rdata_t&b){return std::memcmp(&a,&b,128)==0;}
void __movsb(u8*d,const u8*s,usz n){std::memcpy(d,s,n);}
constexpr u32 s_rep_movsb_threshold=1024,RAW_SPU_BASE_ADDR=0xe0000000u,RAW_SPU_OFFSET=0x100000;
constexpr u32 SYS_SPU_THREAD_BASE_LOW=0xf0000000u,SYS_SPU_THREAD_OFFSET=0x100000,SPU_LS_SIZE=0x40000;
constexpr u32 SYS_SPU_THREAD_SNR1=0x5400c,SYS_SPU_THREAD_SNR2=0x5c00c;
constexpr u8 MFC_PUT_CMD=0x20,MFC_GET_CMD=0x40,MFC_SDCRZ_CMD=0x89,MFC_BARRIER_MASK=1,MFC_FENCE_MASK=2,MFC_START_MASK=8;
constexpr u32 SPU_EVENT_LR=1;
struct spu_mfc_cmd{u8 cmd=0,tag=0;u16 size=0;u32 lsa=0,eal=0,eah=0;};
struct{struct{bool spu_accurate_dma=false,mfc_debug=false,rsx_fifo_accuracy=false,accurate_cache_line_stores=false;}core;struct{bool strict_rendering_mode=false;}video;}g_cfg;
struct access_fault:std::runtime_error{using std::runtime_error::runtime_error;};
namespace fmt{template<class...T>[[noreturn]]void throw_exception(const char*s,T&&...){throw std::invalid_argument(s);}}
namespace cpu_flag{constexpr u32 wait=1,temp=2,pause=4;}
enum class thread_class{spu,ppu};
struct cpu_thread{
 u32 state=0;void check_state(){state=0;}thread_class get_class()const{return thread_class::spu;}
 template<unsigned,class F>static bool if_suspended(cpu_thread*,std::initializer_list<void*>,F&&f){f();return true;}
};
enum class spu_type{group,raw};
struct spu_thread;
struct spu_group{std::array<int,256>threads_map;std::array<spu_thread*,256>threads{};spu_group(){threads_map.fill(-1);}};
struct spu_thread:cpu_thread{
 alignas(64)std::array<u8,SPU_LS_SIZE>storage{};u8*ls=storage.data();spu_group*group=nullptr;spu_type type=spu_type::group;
 atomic_t<u64,128>slot;atomic_t<u64,128>*range_lock=&slot;u32 last_faddr=0,pc=0,raddr=0;u64 block_hash=0,rtime=0;spu_rdata_t rdata{};
 static constexpr u32 max_mfc_dump_idx=1;
 struct hist{spu_mfc_cmd cmd;u64 block_hash;u8 data[128];}mfc_history[1]{};u32 mfc_dump_idx=0;
 u32 snr[2]{},snr_calls=0,reg_value=0,read_calls=0,write_calls=0;bool reg_valid=false;
 spu_type get_type()const{return type;}
 template<class T>T&_ref(u32 a){return *reinterpret_cast<T*>(ls+a);}
 bool read_reg(u32,u32&v){++read_calls;v=reg_value;return reg_valid;}
 bool write_reg(u32,u32 v){++write_calls;reg_value=v;return reg_valid;}
 void push_snr(bool index,u32 value){snr[index]=value;++snr_calls;}
 void set_events(u32){}
};
template<class T>using named_thread=T;
static spu_thread*current_cpu=nullptr;
template<class T=cpu_thread>T*get_current_cpu_thread(){return static_cast<T*>(current_cpu);}
static std::array<spu_thread*,256>raw_threads{};
u32 find_raw_spu(u32 index){return index;}
namespace idm{template<class T>T*get_unlocked(u32 index){return index<raw_threads.size()?raw_threads[index]:nullptr;}}
static bool new_mode=false;
static u32 range_calls=0,atomic_calls=0,fault_calls=0;
alignas(64)static std::array<u8,0x200000>ordinary_ram{};
alignas(64)static std::array<u8,SPU_LS_SIZE>unmapped_placeholder{};
namespace vm{
 alignas(16)static std::array<u8,0x10000>reservation_storage{};
 static u8*g_reservations=reservation_storage.data();
 static std::array<atomic_t<u64>,512>reservations{};
 constexpr u64 rsrv_unique_lock=64;
 template<class T>T*_ptr(u32 a){
  if(a<ordinary_ram.size())return reinterpret_cast<T*>(ordinary_ram.data()+a);
  if(a>=RAW_SPU_BASE_ADDR&&a<SYS_SPU_THREAD_BASE_LOW){u32 i=(a-RAW_SPU_BASE_ADDR)/RAW_SPU_OFFSET,o=(a-RAW_SPU_BASE_ADDR)%RAW_SPU_OFFSET;if(i<raw_threads.size()&&raw_threads[i]&&o<SPU_LS_SIZE)return reinterpret_cast<T*>(raw_threads[i]->ls+o);}
  return reinterpret_cast<T*>(unmapped_placeholder.data());
 }
 auto&reservation_acquire(u32 a){return reservations[(a>>7)%reservations.size()];}
 void reservation_shared_lock_internal(atomic_t<u64>&r){r+=1;}
 template<unsigned Size=0>void range_lock(atomic_t<u64,128>*s,u32 a,u32 n){
  (void)Size;++range_calls;
  if(a>=RAW_SPU_BASE_ADDR&&!new_mode){++fault_calls;throw access_fault("MMIO rejected as unmapped ordinary page");}
  s->v=(u64(n)<<32)|a;
 }
}
namespace utils{
 template<class T>T*bless(void*p){return reinterpret_cast<T*>(p);}template<class T>void prefetch_write(T*){}
 template<class T>constexpr T align(T v,u32 a){return (v+a-1)&~T(a-1);}
}
namespace rsx{namespace constants{constexpr u32 local_mem_base=0xc0000000;}template<bool,unsigned>struct reservation_lock{reservation_lock(u32,u32,bool){}};}
void busy_wait(u32){throw std::runtime_error("unexpected contention in routing adapter");}
void atomic_fence_acquire(){std::atomic_thread_fence(std::memory_order_acquire);}
void do_cell_atomic_128_store(u32 a,const void*p){
 ++atomic_calls;
 // Production helper resolves addr with vm::get_super_ptr; group MMIO has
 // no ordinary mapped guest page and cannot recover the selected host LS.
 if(a>=SYS_SPU_THREAD_BASE_LOW){++fault_calls;throw access_fault("atomic store re-resolved synthetic group address");}
 std::memcpy(vm::_ptr<u8>(a),p,128);
}

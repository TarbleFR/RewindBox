#include <algorithm>
#include <array>
#include <atomic>
#include <bit>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <type_traits>
#include <vector>
using u8=std::uint8_t; using u16=std::uint16_t; using u32=std::uint32_t;
using u64=std::uint64_t; using usz=std::size_t;
constexpr u64 operator""_u64(const char*,std::size_t) { return 0; }
template<u64> struct perf_meter { explicit perf_meter(void* = nullptr) {} };
template<class T> struct be_t {
 T raw;
 static T swap(T v) { if constexpr(sizeof(T)==2) return __builtin_bswap16(v); else if constexpr(sizeof(T)==4) return __builtin_bswap32(v); else return __builtin_bswap64(v); }
 be_t()=default; be_t(T v):raw(swap(v)){} operator T() const {return swap(raw);}
 be_t& operator=(T v){raw=swap(v);return *this;}
};
struct alignas(16) v128 {
 union { u32 _u32[4]; u64 _u64[2]; };
 static v128 loadu(const void* p, usz n) {v128 x;std::memcpy(&x,static_cast<const u8*>(p)+n*16,16);return x;}
 static v128 from64p(u64 x) {v128 r; r._u64[0]=r._u64[1]=x;return r;}
 friend v128 operator|(v128 a,v128 b){a._u64[0]|=b._u64[0];a._u64[1]|=b._u64[1];return a;}
 friend v128 operator&(v128 a,v128 b){a._u64[0]&=b._u64[0];a._u64[1]&=b._u64[1];return a;}
 friend bool operator==(v128 a,v128 b){return a._u64[0]==b._u64[0]&&a._u64[1]==b._u64[1];}
};
struct alignas(16) spu_rdata_t {std::array<u8,128> bytes;};
static unsigned copy_calls=0,vm_calls=0,list_reads=0;
static bool deny_list=false,deny_copy=false;
alignas(64) static std::array<u8,0x80000> guest_memory;
void mov_rdata(spu_rdata_t& dst,const spu_rdata_t& src){++copy_calls;if(deny_copy)throw std::runtime_error("unexpected 128-byte copy");std::memcpy(&dst,&src,128);}
void __movsb(u8* dst,const u8* src,usz n){std::memcpy(dst,src,n);}
constexpr u32 s_rep_movsb_threshold=1024, RAW_SPU_BASE_ADDR=0xe0000000u;
enum MFC:u8 {MFC_PUT_CMD=0x20,MFC_PUTL_CMD=0x24,MFC_PUTLB_CMD=0x25,MFC_PUTLF_CMD=0x26,MFC_PUTRL_CMD=0x34,MFC_GET_CMD=0x40,MFC_GETL_CMD=0x44,MFC_GETLB_CMD=0x45,MFC_GETLF_CMD=0x46,MFC_BARRIER_CMD=0xc0,MFC_EIEIO_CMD=0xc8,MFC_SYNC_CMD=0xcc,MFC_PUTQLLUC_CMD=0xb8};
constexpr u8 MFC_BARRIER_MASK=1,MFC_FENCE_MASK=2,MFC_LIST_MASK=4;
constexpr u32 MFC_TAG_UPDATE_IMMEDIATE=0,MFC_TAG_UPDATE_ANY=1,MFC_TAG_UPDATE_ALL=2,SPU_EVENT_SN=2;
struct spu_mfc_cmd {MFC cmd;u8 tag;u16 size;u32 lsa,eal,eah;friend bool operator==(const spu_mfc_cmd&,const spu_mfc_cmd&)=default;};
struct log_flag {bool enabled=false;operator bool()const{return enabled;}template<class...T>void operator()(T&&...)const{}};
static struct {log_flag trace;} spu_log;
static struct {struct {bool spu_accurate_dma=false,mfc_debug=false,rsx_fifo_accuracy=false,mfc_shuffling_in_steps=false;u32 mfc_transfers_shuffling=0;}core;struct {bool strict_rendering_mode=false;}video;}g_cfg;
namespace utils {template<class T>constexpr T align(T v,u32 a){return (v+a-1)&~T(a-1);}inline u64 get_tsc(){return 0xffff;}}
template<class T,class U>T narrow(U x){return static_cast<T>(x);}
struct range_slot {unsigned releases=0;void release(u32){++releases;}};
namespace vm {template<class T>T* _ptr(u32 addr){++vm_calls;u32 off=addr&0x0fffffff;if(off>=guest_memory.size())throw std::runtime_error("VM out of range");return reinterpret_cast<T*>(guest_memory.data()+off);}inline void range_lock(range_slot*,u32,u32){}}
namespace rsx {namespace constants {constexpr u32 local_mem_base=0xc0000000;}template<bool,unsigned>struct reservation_lock{reservation_lock(u32,u32,bool){}void unlock(){}void update_if_enabled(u32,u32,range_slot*){}};}
inline void atomic_fence_seq_cst(){std::atomic_thread_fence(std::memory_order_seq_cst);}
inline u64 get_system_time(){return 1;}
namespace spu_runtime{inline void g_escape(void*){throw std::runtime_error("unexpected interrupt");}}
struct channel {u32 value=0;bool ready=false;u32 get_count()const{return ready;}u32 get_value()const{return value;}void set_value(u32 v){value=v;ready=true;}};
struct spu_common {
 alignas(64) std::array<u8,0x40000+96> local;
 u8* ls=local.data();spu_rdata_t rdata{};
 range_slot slot;range_slot* range_lock=&slot;
 u32 ch_stall_mask=0,events=0;channel ch_stall_stat;
 spu_mfc_cmd mfc_queue[16]{};u32 mfc_size=0,mfc_fence=0,mfc_barrier=0;
 u32 ch_tag_upd=0,ch_tag_mask=0,pc=0;u64 mfc_last_timestamp=0;channel ch_tag_stat;
 unsigned dma_calls=0;
 template<class T>T* _ptr(u32 addr){++list_reads;if(deny_list)throw std::runtime_error("empty list touched LS");if(addr>=0x40000)throw std::runtime_error("LS out of range");return reinterpret_cast<T*>(ls+addr);}
 void set_events(u32 bits){events|=bits;}
 u32 get_mfc_completed()const{return ch_tag_mask&~mfc_fence;}
 bool check_mfc_interrupts(u32){return false;}
 void do_putlluc(const spu_mfc_cmd&){throw std::runtime_error("unexpected atomic command");}
 static void do_dma_transfer(spu_common* spu,const spu_mfc_cmd& args,u8* ls){++spu->dma_calls;u8* mem=vm::_ptr<u8>(args.eal);if(args.cmd&MFC_GET_CMD)std::memcpy(ls+args.lsa,mem,args.size);else std::memcpy(mem,ls+args.lsa,args.size);}
};
struct spu_old:spu_common{bool do_list_transfer(spu_mfc_cmd&);bool do_mfc(bool,bool);};
struct spu_new:spu_common{bool do_list_transfer(spu_mfc_cmd&);bool do_mfc(bool,bool);};

// SPDX-License-Identifier: MIT
#include <functional>
#include <vector>
#include <span>
#include <iostream>
#include <thread>
#include <cstdlib>
#include "util/types.hpp"
namespace utils {
struct serial {
 bool writing=false;usz pos=0;std::vector<u8> data;usz reads=0;
 struct handler {bool is_valid()const{return true;}} file;
 handler* m_file_handler=&file;
 bool is_writing()const{return writing;}
 void operator()(u32& value){value=static_cast<u32>(++reads);pos+=4;}
};
template<class T>constexpr T align(T value,T alignment){return (value+alignment-1)&(0-alignment);}
}
#include "util/fixed_typemap.hpp"
namespace fmt {
[[noreturn]] void raw_verify_error(std::source_location,const char8_t*,usz){std::abort();}
[[noreturn]] void raw_verify_error(std::source_location,std::source_location,const char8_t*,usz){std::abort();}
}
thread_local std::string_view g_tls_serialize_name;
thread_local unsigned log_count=0;
struct Log {template<class... Args>void notice(const char*,Args&&...){++log_count;}} sys_log;
u64 get_system_time(){return 1'000'000;}
namespace stx {
u16 serial_breathe_and_tag(utils::serial& ar,std::string_view,bool){ar.pos+=2;return 0;}
#include "trace.inc"
}
namespace vm {
constexpr u8 page_readable=1;
constexpr u8 page_allocated=128;
u32 allowed_begin=0x10000,allowed_size=0x10000;u32 hole=0,unreadable=0;
unsigned calls=0;
bool check_addr(u32 begin,u8 flags,u32 length=1){
 ++calls;
 return begin>=allowed_begin&&length<=allowed_size&&u64(begin)+length<=u64(allowed_begin)+allowed_size&&
  (!hole||u64(begin)+length<=hole||begin>=hole+4096)&&
  (!(flags&page_readable)||!unreadable||u64(begin)+length<=unreadable||begin>=unreadable+4096);
}
}
#include "range.inc"
struct Saved {
 SAVESTATE_INIT_POS(1);
 u32 value=0;
 Saved()=default;Saved(utils::serial& ar){ar(value);}
 Saved(const Saved&)=delete;Saved& operator=(const Saved&)=delete;
 void save(utils::serial& ar){ar(value);}
};
struct Bulk {
 SAVESTATE_INIT_POS(2);
 u32 value=0;
 Bulk()=default;Bulk(utils::serial& ar){ar(value);}
 Bulk(const Bulk&)=delete;Bulk& operator=(const Bulk&)=delete;
 void save(utils::serial& ar){ar(value);}
};
struct Pointer {
 u32 value=0;
 explicit Pointer(utils::serial* ar){if(ar)(*ar)(value);}
 Pointer(const Pointer&)=delete;Pointer& operator=(const Pointer&)=delete;
 void save(utils::serial& ar){ar(value);}
};
struct Tag{};
int main(){
 stx::manual_typemap<Tag> map;utils::serial ar;map.reset();stx::serial_restore_trace_reset();
 ensure(map.init<Saved>(ar)->value==1);ensure(ar.pos==6&&log_count==2);
 ensure(!map.init<Saved>(ar));ensure(ar.pos==6&&log_count==2);
 ensure(map.init<Pointer>(&ar)->value==2);ensure(ar.pos==12&&log_count==4);
 map.init(false,&ar);ensure(map.get<Bulk>().value==3&&ar.pos==18&&log_count==6);
 ensure(g_tls_serialize_name.empty());map.clear();
 // Null archive and a writing archive must not emit restore diagnostics.
 map.reset();ensure(map.init<Pointer>(static_cast<utils::serial*>(nullptr)));ensure(log_count==6);map.clear();
 map.reset();ar.writing=true;ensure(map.init<Saved>(ar));ensure(log_count==6);map.clear();ar.writing=false;
 stx::serial_restore_trace_reset();log_count=0;
 for(unsigned i=0;i<1200;++i)stx::serial_restore_trace(ar,"fixture",i%2==0);
 ensure(log_count==513);ensure(ar.pos==24&&ar.reads==4);
 std::thread worker([&]{ensure(log_count==0);stx::serial_restore_trace_reset();stx::serial_restore_trace(ar,"thread",true);ensure(log_count==1);});worker.join();
 ensure(log_count==513);stx::serial_restore_trace_reset();stx::serial_restore_trace(ar,"next_restore",true);ensure(log_count==514);
 unsigned cases=0;
 for(u32 offset:{0u,4096u,32768u,61440u})for(u64 count:{1ull,100ull,512ull,4096ull,8192ull,8193ull,0x20000000ull,~0ull}){
  const u32 address=vm::allowed_begin+offset;vm::hole=0;
  const bool expected=count>0&&count<=(vm::allowed_size-offset)/8;
  ensure(ppu_restore_functions_fit(address,count)==expected);++cases;
 }
 for(u32 address:{0u,1u,0xfffff000u,0xffff0000u}){ensure(!ppu_restore_functions_fit(address,10000));++cases;}
 // Negative control: the original first-byte validation accepts a table
 // whose registration envelope crosses a missing saved page. The fix rejects it.
 vm::hole=vm::allowed_begin+32768;
 ensure(vm::check_addr(vm::allowed_begin,vm::page_readable));
 ensure(!ppu_restore_functions_fit(vm::allowed_begin,8192));++cases;
 vm::hole=0;vm::unreadable=vm::allowed_begin;
 ensure(ppu_restore_functions_fit(vm::allowed_begin+4096,512));++cases;
 ensure(!ppu_restore_functions_fit(vm::allowed_begin,512));++cases;
 std::cout<<"PASS actual FXO: reference/pointer/null/bulk/already-initialized, stream positions, no write/normal-boot tracing, per-restore cap/reset/thread isolation; HLE cases="<<cases<<", missing-page negative control\n";
}

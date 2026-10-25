// SPDX-License-Identifier: MIT
// Actual production FXO template, controlled archive and standby-thread adapters.
#include <functional>
#include <vector>
#include <iostream>
#include <thread>
#include <cstdlib>
#include "util/types.hpp"
#include "ios/IOSRestoreFailure.h"
namespace utils {
struct serial {
 usz pos=0,reads=0,tags=0;bool is_writing()const{return false;}
 void operator()(u32& value){value=static_cast<u32>(++reads);pos+=4;}
};
template<class T>constexpr T align(T value,T alignment){return (value+alignment-1)&(0-alignment);}
}
#include "util/fixed_typemap.hpp"
enum class thread_state:u32 {created=0,aborting=1};
namespace fmt {
[[noreturn]]void raw_verify_error(std::source_location loc,const char8_t*,usz){std::cerr<<"verify "<<loc.file_name()<<":"<<loc.line()<<"\n";std::abort();}
[[noreturn]]void raw_verify_error(std::source_location loc,std::source_location,const char8_t*,usz){std::cerr<<"verify "<<loc.file_name()<<":"<<loc.line()<<"\n";std::abort();}
}
thread_local std::string_view g_tls_serialize_name;
namespace stx {
u16 serial_breathe_and_tag(utils::serial& ar,std::string_view,bool){++ar.tags;ar.pos+=2;return 0;}
void serial_restore_trace_reset()noexcept{rpcs3::ios::restore_failure::reset();}
void serial_restore_trace(utils::serial&,std::string_view,bool)noexcept{}
}
static unsigned constructed=0,destroyed=0,launched=0,aborted=0,later=0,postponed=0;
struct Worker {
 SAVESTATE_INIT_POS(0.5);
 Worker(){++constructed;}Worker(utils::serial&):Worker(){}
 Worker(const Worker&)=delete;Worker&operator=(const Worker&)=delete;
 Worker&operator=(thread_state s){if(s==thread_state::created)++launched;else if(s==thread_state::aborting)++aborted;return *this;}
 ~Worker(){++destroyed;}void save(utils::serial&){}
};
struct Saved {
 SAVESTATE_INIT_POS(1);
 u32 value=0;Saved()=default;Saved(utils::serial& ar){ar(value);}
 Saved(const Saved&)=delete;Saved&operator=(const Saved&)=delete;void save(utils::serial& ar){ar(value);}
};
struct Missing {
 SAVESTATE_INIT_POS(2);
 u32 value=0;Missing()=default;
 Missing(utils::serial& ar){ar(value);rpcs3::ios::restore_failure::missing(5,0x80010006,"/dev_bdvd/PS3_GAME/USRDIR/missing.bin");}
 Missing(const Missing&)=delete;Missing&operator=(const Missing&)=delete;void save(utils::serial& ar){ar(value);}
};
struct Later {
 SAVESTATE_INIT_POS(3);
 u32 value=0;Later()=default;Later(utils::serial& ar){++later;ar(value);}
 Later(const Later&)=delete;Later&operator=(const Later&)=delete;void save(utils::serial& ar){ar(value);}
};
struct Tag{};
int main(){
 stx::manual_typemap<Tag> map;
 (void)map.try_get<Worker>();(void)map.try_get<Saved>();(void)map.try_get<Missing>();(void)map.try_get<Later>();
 map.reset();utils::serial ar;stx::serial_restore_trace_reset();map.init(false,&ar,[]{++postponed;});
#ifdef RESTORE_REFERENCE
 std::cout<<"REFERENCE_COUNTS later="<<later<<" postponed="<<postponed<<" launched="<<launched<<" reads="<<ar.reads<<" tags="<<ar.tags<<"\n";
 if(later==1&&postponed==1&&launched==1){std::cout<<"REPRO527 missing-resource flag ignored: later constructor, tag and thread launch executed\n";map.clear();return 17;}return 18;
#else
 ensure(rpcs3::ios::restore_failure::failed());ensure(ar.reads==2&&ar.tags==2);
 ensure(later==0&&postponed==0&&launched==0&&constructed==1&&destroyed==0);
 ensure(map.is_init<Missing>()&&!map.is_init<Later>()&&g_tls_serialize_name.empty());
 map.request_thread_state(thread_state::aborting);ensure(aborted==1&&launched==0);
 map.clear();ensure(destroyed==1);
 // The failure is isolated to the restore thread and reset on the next restore.
 std::thread other([]{ensure(!rpcs3::ios::restore_failure::failed());rpcs3::ios::restore_failure::missing(7,9,"/host_root/private/user-file");ensure(rpcs3::ios::restore_failure::current.disc_path[0]==0);});other.join();
 ensure(rpcs3::ios::restore_failure::current.id==5);
 stx::serial_restore_trace_reset();ensure(!rpcs3::ios::restore_failure::failed());
 map.reset();map.init(false,nullptr,[]{++postponed;});ensure(launched==1&&postponed==1&&later==0);map.clear();ensure(destroyed==2);
 std::cout<<"PASS actual FXO: failure registers destructor, skips subsequent archive tags/constructors/postponed work/thread launch, requests abort before gate release; clean destruction, thread-local cause, reset, normal boot\n";
#endif
}

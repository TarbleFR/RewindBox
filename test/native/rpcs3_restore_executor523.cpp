// SPDX-License-Identifier: MIT
#include "ios/IOSRestoreExecutor.h"
#include <cassert>
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>
#include <utility>
#ifdef __APPLE__
#include <pthread.h>
#endif
using u32=std::uint32_t;using u64=std::uint64_t;
#define ensure(x) do{if(!(x)){std::cerr<<__LINE__<<" assertion "<<#x<<'\n';std::abort();}}while(false)
const auto ui_thread=std::this_thread::get_id();
bool on_ui(){return std::this_thread::get_id()==ui_thread;}
#ifndef __APPLE__
int pthread_main_np(){return on_ui();}
#endif
struct Latch {
 std::mutex mutex;std::condition_variable cv;bool ready=false;
 void signal(){std::lock_guard lock(mutex);ready=true;cv.notify_all();}
 void wait(){std::unique_lock lock(mutex);ensure(cv.wait_for(lock,std::chrono::seconds(5),[&]{return ready;}));}
 void reset(){std::lock_guard lock(mutex);ready=false;}
};
struct ApiMutex {
 std::mutex mutex;Latch attempted;
 void lock(){if(!on_ui())attempted.signal();mutex.lock();}
 void unlock(){mutex.unlock();}
} g_api_mutex;
std::mutex logs_mutex;std::condition_variable logs_changed;std::vector<std::string> logs;
void emit_log(int,std::string_view text){std::lock_guard lock(logs_mutex);logs.emplace_back(text);logs_changed.notify_all();}
void wait_log(std::string_view text){std::unique_lock lock(logs_mutex);ensure(logs_changed.wait_for(lock,std::chrono::seconds(5),[&]{for(auto& s:logs)if(s.find(text)!=s.npos)return true;return false;}));}
namespace fmt {std::string format(const char*,unsigned main){return "SAVESTATE_RESTORE phase=worker_begin main_thread="+std::to_string(main);}}
namespace thread_base {void set_name(const char*){}}
constexpr int RPCS3_IOS_STATE_READY=1;
struct Lifecycle {std::atomic<int> value{1};int state()const{return value.load();}} g_lifecycle;
std::atomic<bool> g_accept_display_surfaces{true};
enum class system_state {stopped,stopping,running,paused};
enum class game_boot_result {no_errors,failed};
struct Emulator {
 std::atomic<system_state> state{system_state::running};std::atomic<unsigned> boots{0};
 std::atomic<bool> boot_on_ui{false},continuous{false};std::function<void()> after_kill_callback;
 std::string GetTitleID(){return "TEST00001";}std::string GetBoot(){return "legal-fixture";}
 system_state GetStatus(bool=false){return state.load();}bool IsRunning(){return GetStatus()==system_state::running;}
 void SetContinuousMode(bool value){continuous=value;}
 void GracefulShutdown(bool,bool,bool,bool){state=system_state::stopping;}
 game_boot_result BootGame(const std::string&,const std::string&,bool){boot_on_ui=on_ui();++boots;state=system_state::running;return game_boot_result::no_errors;}
} Emu;
namespace neostation::savestate {struct Status {std::atomic<unsigned> finishes{0};void finish(bool,std::string_view){++finishes;}} current;}
struct Cfg {struct Save {bool suspend_emu=false;struct Max {u32 get(){return 10;}} max_files;} savestate;} g_cfg;
namespace fs {bool is_file(const std::string&){return true;}}
std::string get_savestate_file(const std::string&,const std::string&,int){return "legal-state-fixture";}
struct Log {template<class... A>void trace(const char*,A&&...){}template<class... A>void success(const char*,A&&...){}template<class... A>void error(const char*,A&&...){}} sys_log;
rpcs3::ios::restore_executor* selected_jobs=nullptr;
rpcs3::ios::restore_executor& restore_jobs(){ensure(selected_jobs);return *selected_jobs;}
namespace rpcs3::ios {
#include "executor.inc"
#include "continuation.inc"
}
namespace before {
#include "before.inc"
}
namespace after {
#include "after.inc"
}
void reset(){
 Emu.state=system_state::running;Emu.boots=0;Emu.boot_on_ui=false;Emu.continuous=false;Emu.after_kill_callback={};
 g_lifecycle.value=1;g_accept_display_surfaces=true;neostation::savestate::current.finishes=0;
 g_api_mutex.attempted.reset();std::lock_guard lock(logs_mutex);logs.clear();
}
void finish_ui_cleanup(){
 Emu.state=system_state::stopped;
 auto callback=std::exchange(Emu.after_kill_callback,{});ensure(callback);callback();
}
int main(){
 unsigned cases=0;
 // Actual Build 522 negative control: heavy boot runs inside UIKit cleanup.
 reset();ensure(before::boot_current_game_savestate(false,1));finish_ui_cleanup();ensure(Emu.boots==1&&Emu.boot_on_ui);++cases;
 {
  reset();rpcs3::ios::restore_executor q;selected_jobs=&q;
  ensure(after::boot_current_game_savestate(true,1));ensure(!Emu.after_kill_callback);++cases;
  ensure(after::boot_current_game_savestate(false,1));
  g_api_mutex.lock();finish_ui_cleanup();g_api_mutex.attempted.wait();
  ensure(on_ui()&&Emu.boots==0); // UIKit continued while real worker awaited API ownership.
  ensure(!q.post([](u64){},q.generation()));++cases;
  g_api_mutex.unlock();wait_log("phase=worker_end");q.close();
  ensure(Emu.boots==1&&!Emu.boot_on_ui);wait_log("main_thread=0");++cases;
 }
 {
  reset();rpcs3::ios::restore_executor q;selected_jobs=&q;
  ensure(after::boot_current_game_savestate(false,1));g_api_mutex.lock();finish_ui_cleanup();g_api_mutex.attempted.wait();
  ensure(q.cancel());g_api_mutex.unlock();wait_log("phase=worker_cancelled");q.close();
  ensure(Emu.boots==0&&neostation::savestate::current.finishes==0);++cases;
 }
 {
  reset();rpcs3::ios::restore_executor q;selected_jobs=&q;
  ensure(after::boot_current_game_savestate(false,1));q.cancel();
  Emu.continuous=true;finish_ui_cleanup();q.close();
  ensure(Emu.boots==0&&Emu.continuous&&neostation::savestate::current.finishes==0);wait_log("cancelled_before_admission");++cases;
 }
 {
  reset();rpcs3::ios::restore_executor q;selected_jobs=&q;
  Emu.state=system_state::stopped;g_lifecycle.value=0;
  ensure(rpcs3::ios::defer_savestate_restore([]{++Emu.boots;},q.generation()));wait_log("state_rejected");q.close();
  ensure(!Emu.boots&&neostation::savestate::current.finishes==1);++cases;
 }
 for(bool missing_display:{false,true}){
  reset();rpcs3::ios::restore_executor q;selected_jobs=&q;
  if(missing_display){Emu.state=system_state::stopped;g_accept_display_surfaces=false;}
  ensure(rpcs3::ios::defer_savestate_restore([]{++Emu.boots;},q.generation()));wait_log("state_rejected");q.close();
  ensure(!Emu.boots&&neostation::savestate::current.finishes==1);++cases;
 }
 {
  reset();rpcs3::ios::restore_executor q;selected_jobs=&q;Emu.state=system_state::stopped;
  g_api_mutex.lock();ensure(rpcs3::ios::defer_savestate_restore([]{++Emu.boots;},q.generation()));g_api_mutex.attempted.wait();
  q.cancel();std::thread shutdown([&]{ensure(q.close());});
  g_api_mutex.unlock();shutdown.join();ensure(!Emu.boots&&neostation::savestate::current.finishes==0);++cases;
 }
 {
  reset();rpcs3::ios::restore_executor q;selected_jobs=&q;Emu.state=system_state::stopped;Emu.continuous=true;
  ensure(rpcs3::ios::defer_savestate_restore([]{throw std::runtime_error("fixture");},q.generation()));wait_log("phase=worker_end");q.close();
  ensure(!Emu.continuous&&neostation::savestate::current.finishes==1);++cases;
 }
 {
  reset();rpcs3::ios::restore_executor q;selected_jobs=&q;q.close();
  ensure(!rpcs3::ios::defer_savestate_restore([]{++Emu.boots;},q.generation()));ensure(!Emu.boots);++cases;
 }
 {
  rpcs3::ios::restore_executor q;Latch entered,release;std::atomic<unsigned> closed{0};
  ensure(q.post([&](u64){entered.signal();release.wait();},q.generation()));entered.wait();
  std::thread a([&]{ensure(q.close());++closed;}),b([&]{ensure(q.close());++closed;});
  ensure(!closed);release.signal();a.join();b.join();ensure(closed==2);++cases;
 }
 {
  rpcs3::ios::restore_executor q;Latch done;std::atomic<bool> rejected{false};
  ensure(q.post([&](u64){rejected=!q.close();done.signal();},q.generation()));done.wait();q.close();ensure(rejected);++cases;
 }
 {
  rpcs3::ios::restore_executor q;Latch entered,release;std::atomic<bool> rejected{false};const auto token=q.generation();
  ensure(q.post([&](u64){entered.signal();release.wait();rejected=!q.close();},token));entered.wait();
  std::thread closer([&]{ensure(q.close());});
  const auto limit=std::chrono::steady_clock::now()+std::chrono::seconds(5);
  while(q.current(token)){ensure(std::chrono::steady_clock::now()<limit);std::this_thread::yield();}
  release.signal();closer.join();ensure(rejected);++cases;
 }
 {
  rpcs3::ios::restore_executor q;Latch first,second;std::thread::id one,two;
  ensure(q.post([&](u64){one=std::this_thread::get_id();first.signal();},q.generation()));first.wait();
  const auto limit=std::chrono::steady_clock::now()+std::chrono::seconds(5);
  while(!q.post([&](u64){two=std::this_thread::get_id();second.signal();},q.generation())){ensure(std::chrono::steady_clock::now()<limit);std::this_thread::yield();}
  second.wait();q.close();ensure(one==two&&one!=ui_thread);++cases;
 }
 std::cout<<"PASS "<<cases<<" owned restore cases: actual old UIKit negative control; UI handoff, API serialization, bounded admission, stale-after-dequeue and late-cleanup cancellation, lifecycle reject, exception, closed queue, concurrent joins, self-join refusal, same-worker second restore\n";
}

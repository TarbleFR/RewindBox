// SPDX-License-Identifier: MIT
// Production exitspawn + owned worker; explicit Core/VFS/FXO/UIKit adapters.
#include "ios/IOSRestoreExecutor.h"
#include "ios/RPCS3IOSContract.h"
#include "ios/NeoStationSavestateStatus.h"
#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdlib>
#include <deque>
#include <exception>
#include <iostream>
#include <memory>
#include <string>
#include <string_view>
#include <utility>
#include <vector>
using u8=std::uint8_t;using u32=std::uint32_t;using u64=std::uint64_t;using u128=std::uint64_t;
template<class T>using shared_ptr=std::shared_ptr<T>;
using std::make_shared;
unsigned cases=0;
#define ensure(x) do { if(!(x)){std::cerr<<__LINE__<<" after "<<cases<<" cases assertion "<<#x<<'\n';std::abort();} } while(false)
const auto ui_id=std::this_thread::get_id();
bool on_ui(){return std::this_thread::get_id()==ui_id;}
std::atomic<bool> fxo_live{true};
#ifndef __APPLE__
int pthread_main_np(){return on_ui();}
#else
#include <pthread.h>
#endif
struct Latch {
 std::mutex mutex;std::condition_variable cv;bool value=false;
 void signal(){std::lock_guard lock(mutex);value=true;cv.notify_all();}
 void wait(){std::unique_lock lock(mutex);ensure(cv.wait_for(lock,std::chrono::seconds(5),[&]{return value;}));}
 void reset(){std::lock_guard lock(mutex);value=false;}
};
struct ApiMutex {
 std::mutex mutex;Latch attempted;
 void lock(){if(!on_ui())attempted.signal();mutex.lock();}
 void unlock(){mutex.unlock();}
} g_api_mutex;
std::mutex ui_mutex;std::condition_variable ui_changed;std::deque<std::function<void()>> ui_jobs;
void queue_ui(std::function<void()> fn){std::lock_guard lock(ui_mutex);ui_jobs.push_back(std::move(fn));ui_changed.notify_all();}
void pump_ui(){ensure(on_ui());std::function<void()> fn;{std::unique_lock lock(ui_mutex);ensure(ui_changed.wait_for(lock,std::chrono::seconds(5),[]{return !ui_jobs.empty();}));fn=std::move(ui_jobs.front());ui_jobs.pop_front();}fn();}
bool ui_empty(){std::lock_guard lock(ui_mutex);return ui_jobs.empty();}
std::mutex log_mutex;std::condition_variable log_changed;std::vector<std::string> messages;
void emit_log(int,std::string_view text){std::lock_guard lock(log_mutex);messages.emplace_back(text);log_changed.notify_all();}
void wait_log(std::string_view wanted){std::unique_lock lock(log_mutex);ensure(log_changed.wait_for(lock,std::chrono::seconds(5),[&]{for(auto& s:messages)if(s.find(wanted)!=s.npos)return true;return false;}));}
void set_error(std::string_view s){emit_log(1,s);}
namespace fmt {std::string format(const char*,unsigned main){return "CONTINUOUS_BOOT phase=worker_begin main_thread="+std::to_string(main);}}
namespace thread_base {void set_name(const char*){}}
struct Log {template<class... T>void success(const char*,T&&...){}template<class... T>void fatal(const char*,T&&...){ensure(false);}template<class... T>void error(const char*,T&&...){emit_log(1,"admission_failed");}} sys_process;
enum class cpu_flag:u32 {wait=1,exit=2};
struct PpuState {
 std::atomic<u32> value{0};Latch waiting;
 void operator+=(cpu_flag f){value.fetch_or(static_cast<u32>(f));}
 u32 operator+()const{return value.load();}
 void wait(u32 v){waiting.signal();value.wait(v);}
 void stop(){value.fetch_or(2);value.notify_all();}
};
bool is_stopped(u32 s){return s&2;}
struct ppu_thread {PpuState state;u64 gpr[32]{};};
std::atomic<ppu_thread*> selected_ppu{nullptr};
namespace utils {struct serial {void set_reading_state(){}};}
struct loaded_npdrm_keys {u128 last_key(){return 73;}};
struct lv2_memory_container {u32 size=128,used=1;lv2_memory_container()=default;explicit lv2_memory_container(u32 s):size(s){}};
namespace id_manager {std::mutex g_mutex;template<class T>struct id_map {id_map()=default;explicit id_map(utils::serial&){}void save(utils::serial&){} };}
struct reader_lock {std::unique_lock<std::mutex> lock;explicit reader_lock(std::mutex& m):lock(m){}};
namespace stx {void serial_breathe_and_tag(utils::serial&,const char*,bool){}}
namespace idm {template<class T,class F>void select(F fn){T item{16};fn(1,item);}}
struct Fxo {
 template<class T>T& get(){ensure(fxo_live);static T value;return value;}
 template<class T,class... A>T* init(A&&... args){get<T>()=T(std::forward<A>(args)...);return &get<T>();}
} fxo;
Fxo* g_fxo=&fxo;
namespace vfs {std::string get(const std::string& path){if(path=="/dev_bdvd/")return "disc/";if(path=="/dev_hdd1/")return "hdd1/";return "host:"+path;}}
void signal_system_cache_can_stay(){}
enum class system_state {stopped,stopping,running,ready};
enum class cfg_mode {continuous};
enum class game_boot_result {no_errors};
rpcs3::ios::lifecycle g_lifecycle;
std::atomic<bool> g_accept_display_surfaces{true};

Latch boot_entered,boot_release;std::atomic<bool> block_boot{false};
std::atomic<unsigned> native_active{0},native_peak{0};
struct Emulator {
 std::atomic<system_state> state{system_state::running};std::atomic<u64> identifier{1};
 std::atomic<unsigned> boots{0},kills{0};std::atomic<bool> boot_on_ui{false},kill_on_ui{false},continuous{false},force{false};
 std::vector<std::string> argv,envp;std::vector<u8> data;std::string disc,hdd1;std::vector<u128> klic;
 std::function<void(u32)> init_mem_containers;std::function<void()> after_kill_callback;
 std::vector<std::string> boot_paths;std::string category="DG",title="BLES01717";
 struct Callbacks {std::function<void(std::function<void()>,void*)> call_from_main_thread=[](std::function<void()> fn,void*){queue_ui(std::move(fn));};} callbacks;
 Callbacks& GetCallbacks(){return callbacks;}
 std::string GetCat(){return category;}std::string GetTitleID(){return title;}std::string GetDir(){return "/dev_bdvd/PS3_GAME/";}
 std::string GetUsedConfig(){return "existing-config";}std::string GetUsedDatabaseConfig(){return "existing-db-config";}
 u64 GetEmulationIdentifier(){return identifier.load();}
 system_state GetStatus(bool=false){return state.load();}bool IsStopped(){return state==system_state::stopped||state==system_state::stopping;}
 void SetContinuousMode(bool v){continuous=v;}void SetForceBoot(bool v){force=v;}
 void CallFromMainThread(std::function<void()> fn){const auto id=identifier.load();const bool stopped=state==system_state::stopped;queue_ui([this,id,stopped,fn=std::move(fn)]{if(identifier==id&&stopped==(state==system_state::stopped))fn();});}
 void Kill(bool){ensure(on_ui());kill_on_ui=true;++kills;state=system_state::stopping;if(auto* p=selected_ppu.load())p->state.stop();}
 game_boot_result BootGame(const std::string& path,const std::string&,bool,cfg_mode,const std::string& config,const std::string& db){
  ensure(config=="existing-config"&&db=="existing-db-config");boot_on_ui=on_ui();++boots;boot_paths.push_back(path);
  unsigned active=++native_active,peak=native_peak.load();while(peak<active&&!native_peak.compare_exchange_weak(peak,active)){}
  boot_entered.signal();if(block_boot)boot_release.wait();
  if(init_mem_containers){auto f=std::move(init_mem_containers);f(96);ensure(g_fxo->get<lv2_memory_container>().size==112);}
  state=system_state::running;--native_active;return game_boot_result::no_errors;
 }
} Emu;
rpcs3::ios::restore_executor* selected_jobs=nullptr;
rpcs3::ios::restore_executor& restore_jobs(){ensure(selected_jobs);return *selected_jobs;}
namespace rpcs3::ios {
#include "executor.inc"
#include "continuations.inc"
}
namespace before {
#include "before.inc"
}
namespace after {
#include "after.inc"
}
void reset(){
 ensure(ui_empty());Emu.state=system_state::running;Emu.identifier=1;Emu.boots=0;Emu.kills=0;Emu.boot_on_ui=false;Emu.kill_on_ui=false;Emu.continuous=false;Emu.force=false;
 Emu.argv={};Emu.envp={};Emu.data={};Emu.disc.clear();Emu.hdd1.clear();Emu.klic.clear();Emu.init_mem_containers={};Emu.after_kill_callback={};Emu.boot_paths.clear();Emu.title="BLES01717";
 g_lifecycle={};ensure(g_lifecycle.begin_initialize()==RPCS3_IOS_OK);g_lifecycle.finish_initialize(true);g_accept_display_surfaces=true;ensure(!neostation::savestate::current.read().active);fxo_live=true;
 boot_entered.reset();boot_release.reset();block_boot=false;native_active=0;native_peak=0;g_api_mutex.attempted.reset();g_fxo->get<lv2_memory_container>().size=128;
 {std::lock_guard lock(log_mutex);messages.clear();}
}
using exitspawn_fn=void(*)(ppu_thread&,std::vector<std::string>&,std::vector<std::string>&,std::vector<u8>&);
std::thread launch(ppu_thread& p,exitspawn_fn fn){selected_ppu=&p;std::thread guest([&p,fn]{std::vector<std::string> args{"/dev_bdvd/PS3_GAME/USRDIR/t6mp_ps3f.self","bots"},env{"LANG=fr"};std::vector<u8> data{1,2,3};fn(p,args,env,data);});p.state.waiting.wait();return guest;}
void finish_cleanup(){ensure(on_ui());Emu.argv.clear();Emu.envp.clear();Emu.data.clear();Emu.disc.clear();Emu.klic.clear();Emu.hdd1.clear();Emu.init_mem_containers={};++Emu.identifier;Emu.state=system_state::stopped;auto callback=std::exchange(Emu.after_kill_callback,{});ensure(callback);callback();}
void ensure_args(){ensure(Emu.argv.size()==2&&Emu.argv[0].ends_with("t6mp_ps3f.self")&&Emu.argv[1]=="bots");ensure(Emu.envp==std::vector<std::string>{"LANG=fr"});ensure(Emu.data==std::vector<u8>({1,2,3}));ensure(Emu.disc=="disc/"&&Emu.hdd1=="hdd1/"&&Emu.klic==std::vector<u128>{73});}
void quiet(rpcs3::ios::restore_executor& q){Latch done;const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(5);while(!q.post([&](u64){done.signal();},q.generation())){ensure(std::chrono::steady_clock::now()<deadline);std::this_thread::yield();}done.wait();}
int main(){cases=0;
 {reset();ppu_thread p;auto guest=launch(p,before::lv2_exitspawn);pump_ui();guest.join();finish_cleanup();ensure(Emu.boot_on_ui&&Emu.kill_on_ui&&Emu.boots==1);ensure_args();++cases;}
 {reset();rpcs3::ios::restore_executor q;selected_jobs=&q;ppu_thread p;auto guest=launch(p,after::lv2_exitspawn);pump_ui();guest.join();block_boot=true;finish_cleanup();boot_entered.wait();ensure(!Emu.boot_on_ui&&Emu.kill_on_ui&&native_active==1);
  bool heartbeat=false;queue_ui([&]{heartbeat=true;});pump_ui();ensure(heartbeat);Latch api_attempt,api_done;
  std::thread stop([&]{api_attempt.signal();std::lock_guard lock(g_api_mutex);q.cancel();Emu.SetContinuousMode(false);ensure(!native_active);Emu.state=system_state::stopped;api_done.signal();});
  api_attempt.wait();ensure(!api_done.value);boot_release.signal();stop.join();ensure(native_peak==1&&Emu.boots==1&&!Emu.continuous);ensure_args();q.close();++cases;}
 // Stop wins before a dequeued request gets the API lock: no UIKit mutation.
 {reset();rpcs3::ios::restore_executor q;selected_jobs=&q;g_api_mutex.lock();ppu_thread p;auto guest=launch(p,after::lv2_exitspawn);g_api_mutex.attempted.wait();q.cancel();Emu.title="NEW-TITLE";Emu.argv={"new-args"};g_api_mutex.unlock();q.close();p.state.stop();guest.join();ensure(!Emu.kills&&ui_empty()&&Emu.argv[0]=="new-args");++cases;}
 // Internal native restarts need the upstream emulation ID as well as API generation.
 {reset();rpcs3::ios::restore_executor q;selected_jobs=&q;ppu_thread p;auto guest=launch(p,after::lv2_exitspawn);{std::unique_lock lock(ui_mutex);ensure(ui_changed.wait_for(lock,std::chrono::seconds(5),[]{return !ui_jobs.empty();}));}++Emu.identifier;Emu.argv={"new-native-args"};pump_ui();quiet(q);p.state.stop();guest.join();q.close();ensure(!Emu.kills&&Emu.argv[0]=="new-native-args");++cases;}
 // Late UIKit cleanup after explicit stop/new title cannot apply any old arguments.
 {reset();rpcs3::ios::restore_executor q;selected_jobs=&q;ppu_thread p;auto guest=launch(p,after::lv2_exitspawn);pump_ui();guest.join();quiet(q);auto late=std::exchange(Emu.after_kill_callback,{});++Emu.identifier;Emu.state=system_state::stopped;
  {std::lock_guard lock(g_api_mutex);q.cancel();Emu.SetContinuousMode(false);Emu.title="NEW-TITLE";Emu.argv={"new-args"};Emu.state=system_state::running;}late();q.close();ensure(!Emu.boots&&!Emu.continuous&&Emu.argv[0]=="new-args");++cases;}
 // The stopped gap is closed by the real explicit-stop cancel/mode sequence.
 {reset();rpcs3::ios::restore_executor q;selected_jobs=&q;ppu_thread p;auto guest=launch(p,after::lv2_exitspawn);pump_ui();guest.join();quiet(q);auto late=std::exchange(Emu.after_kill_callback,{});++Emu.identifier;Emu.state=system_state::stopped;
  {std::lock_guard lock(g_api_mutex);q.cancel();Emu.SetContinuousMode(false);}late();q.close();ensure(!Emu.boots&&!Emu.continuous);++cases;}
 // Dequeued boot cancelled under the API lock has not yet applied captured argv.
 {reset();rpcs3::ios::restore_executor q;selected_jobs=&q;ppu_thread p;auto guest=launch(p,after::lv2_exitspawn);pump_ui();guest.join();quiet(q);g_api_mutex.lock();g_api_mutex.attempted.reset();finish_cleanup();g_api_mutex.attempted.wait();q.cancel();Emu.argv={"replacement"};g_api_mutex.unlock();q.close();ensure(!Emu.boots&&Emu.argv[0]=="replacement");++cases;}
 // A second SELF can request its stop before the first BootGame has returned.
 {reset();rpcs3::ios::restore_executor q;selected_jobs=&q;ppu_thread p;auto guest=launch(p,after::lv2_exitspawn);pump_ui();guest.join();block_boot=true;finish_cleanup();boot_entered.wait();ppu_thread next;auto recursive=launch(next,after::lv2_exitspawn);boot_release.signal();pump_ui();recursive.join();block_boot=false;boot_entered.reset();finish_cleanup();boot_entered.wait();quiet(q);q.close();ensure(Emu.boots==2&&native_peak==1&&Emu.kill_on_ui&&!Emu.boot_on_ui);ensure_args();++cases;}
 // Bounded backpressure, cancellation and legacy restore exclusivity stay intact.
 {reset();rpcs3::ios::restore_executor q;selected_jobs=&q;Latch entered,release;std::atomic<unsigned> second{0};auto token=q.generation();ensure(q.post([&](u64){entered.signal();release.wait();},token));entered.wait();ensure(!q.post([](u64){},token));ensure(q.post_continuation([&](u64){++second;},token));ensure(!q.post_continuation([](u64){},token));q.cancel();release.signal();q.close();ensure(!second);++cases;}
 {reset();rpcs3::ios::restore_executor q;selected_jobs=&q;Emu.state=system_state::stopped;ensure(rpcs3::ios::defer_continuous_stop([](u64){++Emu.kills;},q.generation(),1,"BLES01717"));wait_log("transition ended after");q.close();ensure(!Emu.kills);++cases;}
 for(unsigned mode=0;mode<3;mode++){reset();rpcs3::ios::restore_executor q;selected_jobs=&q;Emu.state=system_state::stopped;if(mode==0)g_accept_display_surfaces=false;if(mode==1)g_lifecycle.finish_initialize(false);if(mode==2)++Emu.identifier;ensure(rpcs3::ios::defer_continuous_boot([]{++Emu.boots;},q.generation(),1,"BLES01717"));wait_log("boot was no longer ready");q.close();ensure(!Emu.boots);++cases;}

 // A failed preparation still has a live original PPU: resume the exact SELF request.
 {reset();rpcs3::ios::restore_executor q;selected_jobs=&q;ensure(neostation::savestate::current.begin(2,1));bool old_save_callback=false;Emu.after_kill_callback=[&]{old_save_callback=true;};ppu_thread p;auto guest=launch(p,after::lv2_exitspawn);quiet(q);ensure(ui_empty()&&!Emu.kills&&!old_save_callback&&neostation::savestate::current.read().active);neostation::savestate::current.finish(false,"preparation fixture");pump_ui();guest.join();finish_cleanup();boot_entered.wait();quiet(q);q.close();ensure(Emu.boots==1&&!old_save_callback&&!neostation::savestate::current.read().active&&neostation::savestate::current.read().state==neostation::savestate::phase::failed);ensure_args();++cases;}
 // A successful save restored one process. Stop that replacement before switching SELF.
 {reset();rpcs3::ios::restore_executor q;selected_jobs=&q;ensure(neostation::savestate::current.begin(3,1));ppu_thread p;auto guest=launch(p,after::lv2_exitspawn);quiet(q);p.state.stop();guest.join();++Emu.identifier;Emu.state=system_state::running;ppu_thread restored;selected_ppu=&restored;neostation::savestate::current.finish(true);pump_ui();ensure(is_stopped(+restored.state));finish_cleanup();boot_entered.wait();quiet(q);q.close();ensure(Emu.boots==1&&Emu.identifier==3&&Emu.kills==1);ensure_args();++cases;}
 // A write/restore failure after Kill leaves no FXO. Report stopped, without touching it.
 {reset();rpcs3::ios::restore_executor q;selected_jobs=&q;ensure(neostation::savestate::current.begin(4,1));ppu_thread p;auto guest=launch(p,after::lv2_exitspawn);quiet(q);p.state.stop();guest.join();++Emu.identifier;Emu.state=system_state::stopped;Emu.continuous=true;Emu.force=true;fxo_live=false;neostation::savestate::current.finish(false,"write fixture");wait_log("transition ended after");q.close();ensure(!Emu.boots&&!Emu.kills&&!Emu.continuous&&!Emu.force);fxo_live=true;++cases;}
 // Stop/new boot between save completion and dequeued transition owns the new title.
 {reset();rpcs3::ios::restore_executor q;selected_jobs=&q;ensure(neostation::savestate::current.begin(5,1));ppu_thread p;auto guest=launch(p,after::lv2_exitspawn);quiet(q);g_api_mutex.lock();neostation::savestate::current.finish(false,"preparation fixture");q.cancel();Emu.title="NEW-TITLE";Emu.argv={"replacement"};Emu.SetContinuousMode(false);g_api_mutex.unlock();q.close();p.state.stop();guest.join();ensure(!Emu.boots&&!Emu.kills&&Emu.argv[0]=="replacement");++cases;}
 // finish can precede registration after the request has been queued behind the API lock.
 {reset();rpcs3::ios::restore_executor q;selected_jobs=&q;ensure(neostation::savestate::current.begin(6,1));g_api_mutex.lock();ppu_thread p;auto guest=launch(p,after::lv2_exitspawn);g_api_mutex.attempted.wait();p.state.stop();guest.join();++Emu.identifier;Emu.state=system_state::running;ppu_thread restored;selected_ppu=&restored;neostation::savestate::current.finish(true);g_api_mutex.unlock();pump_ui();finish_cleanup();boot_entered.wait();quiet(q);q.close();ensure(Emu.boots==1&&Emu.identifier==3);ensure_args();++cases;}
 // Old saved outcome is insufficient authority to alter a later stopped incarnation.
 {reset();rpcs3::ios::restore_executor q;selected_jobs=&q;ensure(neostation::savestate::current.begin(7,1));neostation::savestate::current.finish(false,"old preparation fixture");g_api_mutex.lock();g_api_mutex.attempted.reset();ensure(rpcs3::ios::defer_continuous_stop([](u64){++Emu.kills;},q.generation(),1,"BLES01717"));g_api_mutex.attempted.wait();Emu.identifier=3;Emu.state=system_state::stopped;Emu.continuous=true;Emu.force=true;Emu.argv={"quarantined-later-session"};fxo_live=false;g_api_mutex.unlock();quiet(q);q.close();ensure(!Emu.boots&&!Emu.kills&&Emu.continuous&&Emu.force&&Emu.argv[0]=="quarantined-later-session");{std::lock_guard lock(log_mutex);ensure(messages.empty());}fxo_live=true;++cases;}
 {reset();rpcs3::ios::restore_executor q;selected_jobs=&q;Emu.state=system_state::stopped;Emu.continuous=true;Emu.force=true;ensure(rpcs3::ios::defer_continuous_boot([]{throw std::runtime_error("fixture");},q.generation(),1,"BLES01717"));wait_log("process boot failed");q.close();ensure(!Emu.continuous&&!Emu.force);++cases;}
 {reset();rpcs3::ios::restore_executor q;selected_jobs=&q;ppu_thread p;auto guest=launch(p,after::lv2_exitspawn);pump_ui();guest.join();block_boot=true;finish_cleanup();boot_entered.wait();std::atomic<bool> joined{false};std::thread closer([&]{ensure(q.close());joined=true;});bool heartbeat=false;queue_ui([&]{heartbeat=true;});pump_ui();ensure(heartbeat&&!joined);boot_release.signal();closer.join();ensure(joined&&native_peak==1);++cases;}
 {reset();rpcs3::ios::restore_executor q;selected_jobs=&q;q.close();ensure(!rpcs3::ios::defer_continuous_stop([](u64){},q.generation(),1,"BLES01717"));ensure(!rpcs3::ios::defer_continuous_boot([]{},q.generation(),1,"BLES01717"));ensure(!rpcs3::ios::defer_continuous_stop({},q.generation(),1,"BLES01717"));ensure(!rpcs3::ios::defer_continuous_boot({},q.generation(),1,"BLES01717"));++cases;}
 ensure(ui_empty());std::cout<<"{\"passed\":true,\"cases\":"<<cases<<",\"baseline_boots_on_ui\":true,\"candidate_boots_on_worker\":true,\"stop_and_cleanup_on_ui\":true,\"ui_heartbeat_while_native_boot_blocked\":true,\"api_stop_waits_without_native_overlap\":true,\"late_callback_cancelled_before_argument_mutation\":true,\"native_emulation_identifier_preserved\":true,\"stale_stopped_incarnation_flags_untouched\":true,\"recursive_exitspawn\":true,\"bounded_pending_and_legacy_exclusive\":true,\"active_save_callback_not_overwritten\":true,\"failed_save_before_kill_resumes_self\":true,\"successful_save_resumes_self_after_exact_replacement\":true,\"failed_save_after_kill_reports_stopped_without_fxo_read\":true,\"finish_registration_race_preserved\":true,\"actual_savestate_operation\":true,\"physical_device_tested\":false}\n";
}

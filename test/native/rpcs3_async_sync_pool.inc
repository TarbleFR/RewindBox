#include <atomic>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <memory>
#include <mutex>
#include <utility>
#include <vector>
using u32=uint32_t;using u64=uint64_t;using usz=size_t;using VkBool32=bool;
template<class T>using atomic_t=std::atomic<T>;
using shared_mutex=std::mutex;
#define ensure(x) assert(x)
enum class video_renderer{vulkan,other};enum class vk_gpu_scheduler_mode{safe,fast};
struct {struct{video_renderer renderer=video_renderer::vulkan;struct{bool asynchronous_texture_streaming=true;}vk;bool strict_rendering_mode=false;}video;}g_cfg;
struct Log{template<class...T>void notice(T&&...){}template<class...T>void error(T&&...){assert(false);}}rsx_log;
struct VkDependencyInfoKHR{u32 identity=42;};
struct Counts{u32 sema=0,event=0,deadSema=0,deadEvent=0,pools=0,destroyPools=0,cb=0,destroyCb=0,reset=0,signal=0,submit=0;};
static Counts counts;
namespace boundary{
struct render_device{u32 get_transfer_queue_family()const{return 3;}u32 get_transfer_queue()const{return 11;}};
static const render_device device;
inline const render_device* get_current_renderer(){return &device;}
enum class sync_domain{gpu};
struct command_pool{void create(render_device&,u32 q){assert(q==3);++counts.pools;}void destroy(){++counts.destroyPools;}};
struct queue_submit_t{u32 queue=0;};
struct command_buffer{u32 id=0;bool open=false;void create(command_pool&){id=++counts.cb;}void destroy(){assert(!open);++counts.destroyCb;}
 void begin(){assert(!open);open=true;}void end(){assert(open);open=false;}void submit(queue_submit_t& q,VkBool32){assert(!open&&q.queue==11);++counts.submit;}};
struct event{u32 id;event(const render_device&,sync_domain):id(++counts.event){}~event(){++counts.deadEvent;}
 void reset(){++counts.reset;}void signal(const command_buffer& c,const VkDependencyInfoKHR& d){assert(c.open&&d.identity==42);++counts.signal;}};
struct semaphore{u32 id;semaphore(const render_device&):id(++counts.sema){}~semaphore(){++counts.deadSema;}};
}
@VERSIONS@
struct Result{std::vector<u32> ids;Counts final;u32 startupObjects=0,firstObjects=0,eightObjects=0;};
template<class Scheduler>Result run(bool host,bool strict=false){
 counts={};g_cfg.video.strict_rendering_mode=strict;Result r;
 {Scheduler s(host?vk_gpu_scheduler_mode::safe:vk_gpu_scheduler_mode::fast,{});
  assert(s.is_host_mode()==(host||strict));host=host||strict;
  for(u32 i=0;i<33000;++i){
   auto* cb=s.get_current();assert(s.get_current()==cb);cb->begin();assert(s.is_recording());
   if(i==0)r.startupObjects=counts.sema+counts.event;
   if(host){r.ids.push_back(s.get_sema()->id);}
   else{auto* ev=s.get_primary_sync_label();assert(ev);r.ids.push_back(ev->id);assert(!s.get_primary_sync_label());}
   if(i==0)r.firstObjects=counts.sema+counts.event;
   if(i==7)r.eightObjects=counts.sema+counts.event;
   boundary::queue_submit_t info;s.flush(info,i%2);assert(!s.is_recording());
   s.flush(info,false); // Empty flush must not submit or allocate.
  }
  if(!host){ // Flush may insert the event before a caller asks for its label.
   s.get_current()->begin();boundary::queue_submit_t info;s.flush(info,false);
   auto* ev=s.get_primary_sync_label();assert(ev&&ev->id==233);assert(!s.get_primary_sync_label());
  }
  s.destroy();
 }
 r.final=counts;assert(counts.sema==counts.deadSema&&counts.event==counts.deadEvent);
 assert(counts.cb==256&&counts.destroyCb==256&&counts.pools==1&&counts.destroyPools==1);
 assert(counts.submit==33000u+!host);assert(counts.signal==(!host?33001u:0u));
 return r;
}
int main(){
 u64 comparisons=0;
 for(auto mode:{0,1,2}){
  auto a=run<before::vk::AsyncTaskScheduler>(mode==1,mode==2);
  auto b=run<after::vk::AsyncTaskScheduler>(mode==1,mode==2);
  auto c=run<desktop::vk::AsyncTaskScheduler>(mode==1,mode==2);
  assert(a.ids==b.ids&&a.ids==c.ids);comparisons+=a.ids.size();
  assert(a.startupObjects==16384&&c.startupObjects==16384&&b.startupObjects==0);
  assert(a.firstObjects==16384&&b.firstObjects==1&&b.eightObjects==8);
  assert(a.final.sema==b.final.sema&&a.final.event==b.final.event);
  for(u32 i=0;i<a.ids.size();++i)assert(a.ids[i]==i%16384+1);
 }
 std::cout<<"{\"passed\":true,\"sameSlotIdentityChecks\":"<<comparisons
 <<",\"baselineStartupDriverObjects\":16384,\"candidateStartupDriverObjects\":0,\"candidateFirstUseObjects\":1,\"candidateAfterEightObjects\":8,\"fullCycleObjectsUnchanged\":16384,\"destroyedExactlyOnce\":true,\"desktopUnchanged\":true}\n";
}

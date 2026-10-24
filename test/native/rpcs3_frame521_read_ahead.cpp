// SPDX-License-Identifier: MIT
// Exercises the production ColdFrame and extracted VDEC prefetch method.
#include "ios/NeoSwapStorage/FrameClient.h"
#include <algorithm>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstring>
#include <deque>
#include <fstream>
#include <future>
#include <iostream>
#include <map>
#include <mutex>
#include <thread>
#include <vector>
using namespace neostation::source_client;
using usz=size_t;
struct picture {ColdFrame cold_pixels;};
struct producer {
 std::mutex mutex;
 std::deque<picture> out_queue;
 #include "prefetch-method.inc"
};
namespace {
std::atomic<uint64_t> epoch{77},reads{0};
std::atomic<unsigned> delay_ms{0};
std::atomic<int> failure{NS_SOURCE_OK};
std::mutex records_mutex,gate_mutex;
std::condition_variable gate_cv;
bool gate=false,started=false,release_read=false;
std::mutex* forbidden_queue_mutex=nullptr;
std::map<uint64_t,std::string> records;
uint64_t next_id=0;
uint64_t session(){return epoch.load();}
int admit(uint64_t e,uint32_t domain,const char* p,uint64_t n,uint64_t* id){
 assert(e==epoch&&domain==3&&n<=NEOSWAP_SOURCE_MAX_BYTES);
 std::lock_guard lock(records_mutex);*id=++next_id;records[*id]=std::string(p,n);return NS_SOURCE_OK;
}
int read(uint64_t e,uint64_t id,char* p,uint64_t n,int* error){
 ++reads;*error=0;
 if(forbidden_queue_mutex){assert(forbidden_queue_mutex->try_lock());forbidden_queue_mutex->unlock();}
 {
  std::unique_lock lock(gate_mutex);
  if(gate){started=true;gate_cv.notify_all();gate_cv.wait(lock,[]{return release_read;});}
 }
 if(e!=epoch)return NS_SOURCE_MISSING;
 if(auto code=failure.load();code!=NS_SOURCE_OK){*error=EIO;return code;}
 if(delay_ms)std::this_thread::sleep_for(std::chrono::milliseconds(delay_ms.load()));
 std::lock_guard lock(records_mutex);auto it=records.find(id);assert(it!=records.end()&&it->second.size()==n);
 std::memcpy(p,it->second.data(),n);return NS_SOURCE_OK;
}
void discard(uint64_t,uint64_t id){std::lock_guard lock(records_mutex);assert(records.erase(id)==1);}
void released(uint64_t,uint64_t){assert(false);}
const NeoSwapSourceAPI api{sizeof(api),NEOSWAP_SOURCE_ABI,session,admit,read,discard,released};
std::string payload(size_t bytes=1382400){std::string p(bytes,'\0');for(size_t i=0;i<bytes;++i)p[i]=char((i*131+7)%256);return p;}
ColdFrame archive(const std::string& p){ColdFrame f;assert(f.offload(p.data(),p.size()));return f;}
void empty(){assert(records.empty()&&frame_prefetch_payload_bytes==0&&frame_prefetch_count==0);}
void arm_gate(){std::lock_guard lock(gate_mutex);gate=true;started=release_read=false;}
void wait_started(){std::unique_lock lock(gate_mutex);assert(gate_cv.wait_for(lock,std::chrono::seconds(2),[]{return started;}));}
void open_gate(){std::lock_guard lock(gate_mutex);release_read=true;gate=false;gate_cv.notify_all();}
void queue_selection(){
 producer q;const auto data=payload();for(unsigned i=0;i<8;++i)q.out_queue.push_back({});
 q.out_queue.push_back({archive(data)});const auto before=reads.load();
 forbidden_queue_mutex=&q.mutex;q.prefetch_near_pixels();assert(reads==before);
 q.out_queue.pop_front();q.prefetch_near_pixels();assert(reads>before);
 std::string out;int error=-1;bool hit=false;
 assert(q.out_queue.back().cold_pixels.restore(out,error,&hit)==NS_SOURCE_OK&&hit&&out==data&&error==0);
 forbidden_queue_mutex=nullptr;
}
void bounded_budget(){
 const auto data=payload();std::vector<ColdFrame> frames;
 for(unsigned i=0;i<12;++i)frames.push_back(archive(data));
 unsigned accepted=0;for(auto& f:frames)accepted+=f.prefetch();
 assert(accepted==frame_prefetch_payload_limit/data.size());
 assert(frame_prefetch_payload_bytes==accepted*data.size()&&frame_prefetch_payload_bytes<=frame_prefetch_payload_limit);
 frames.clear();empty();
 // The count cap also bounds metadata and tiny-payload speculative work.
 for(unsigned i=0;i<12;++i)frames.push_back(archive(payload(4096)));
 accepted=0;for(auto& f:frames)accepted+=f.prefetch();assert(accepted==frame_prefetch_count_limit);
 frames.clear();empty();
}
void race_and_reset(){
 const auto data=payload();auto f=archive(data);arm_gate();
 auto preparing=std::async(std::launch::async,[f]{return f.prefetch();});wait_started();
 const auto before=reads.load();
 auto consuming=std::async(std::launch::async,[f,&data]{std::string out;int error=0;bool hit=false;
  assert(f.restore(out,error,&hit)==NS_SOURCE_OK&&hit&&out==data);});
 assert(consuming.wait_for(std::chrono::milliseconds(10))==std::future_status::timeout&&reads==before);
 open_gate();assert(preparing.get());consuming.get();f.reset();empty();
 f=archive(data);arm_gate();preparing=std::async(std::launch::async,[f]{return f.prefetch();});
 wait_started();f.reset();open_gate();assert(preparing.get());empty();
 f=archive(data);arm_gate();preparing=std::async(std::launch::async,[f]{return f.prefetch();});
 wait_started();++epoch;open_gate();assert(!preparing.get());
 std::string out="must clear";int error=0;assert(f.restore(out,error)==NS_SOURCE_MISSING&&out.empty());
 f.reset();empty();
}
void failure_fallback(){
 const auto data=payload();auto f=archive(data);failure=NS_SOURCE_IO;
 assert(!f.prefetch()&&frame_prefetch_payload_bytes==0&&!f.can_prefetch());
 std::string out="must clear";int error=0;
 assert(f.restore(out,error)==NS_SOURCE_IO&&out.empty()&&error==EIO);
 failure=NS_SOURCE_OK;bool hit=true;
 assert(f.restore(out,error,&hit)==NS_SOURCE_OK&&!hit&&out==data);f.reset();empty();
}
double millis(std::chrono::steady_clock::time_point start){return std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();}
}
int main(int argc,char** argv){
 assert(argc==2&&install(&api)==NS_SOURCE_OK);
 for(uint32_t queue=0;queue<80;++queue)for(uint32_t pos=0;pos<85;++pos){
  const bool expected=queue>=24&&pos>=8&&pos<queue&&queue-pos>8;
  assert(frame_can_cool(queue,pos,frame_cold_age_us,4096,true)==expected);
  assert(!frame_can_cool(queue,pos,frame_cold_age_us-1,4096,true));
  assert(!frame_can_cool(queue,pos,frame_cold_age_us,4096,false));
 }
 queue_selection();empty();bounded_budget();race_and_reset();failure_fallback();
 const auto data=payload();delay_ms=8;std::vector<double> cold,ready,prefetch;
 for(unsigned round=0;round<8;++round){
  auto f=archive(data);std::string out;int error=0;auto start=std::chrono::steady_clock::now();
  assert(f.restore(out,error)==NS_SOURCE_OK&&out==data);cold.push_back(millis(start));f.reset();
  f=archive(data);start=std::chrono::steady_clock::now();assert(f.prefetch());prefetch.push_back(millis(start));
  const auto before=reads.load();bool hit=false;start=std::chrono::steady_clock::now();
  assert(f.restore(out,error,&hit)==NS_SOURCE_OK&&out==data&&hit&&reads==before);ready.push_back(millis(start));f.reset();empty();
 }
 auto median=[](auto v){std::sort(v.begin(),v.end());return (v[3]+v[4])/2;};
 std::ofstream report(argv[1]);report<<"{\"result\":\"passed\",\"injectedSourceReadDelayMs\":8,\"payloadBytes\":"<<data.size()
  <<",\"coldConsumerMedianMs\":"<<median(cold)<<",\"readyConsumerMedianMs\":"<<median(ready)
  <<",\"producerPrefetchMedianMs\":"<<median(prefetch)<<",\"peakPrefetchPayloadBytes\":"<<frame_prefetch_peak_bytes
  <<",\"maximumPayloadBytes\":"<<frame_prefetch_payload_limit
  <<",\"readyConsumerStorageCalls\":0,\"physicalIPhoneTested\":false,\"gameplayMeasured\":false}\n";
 std::cout<<"PASS production read-ahead, warm FIFO head/tail, exact pixels, global byte/count limits, in-flight single read, failure retry, reset/epoch races; injected I/O experiment only\n";
}

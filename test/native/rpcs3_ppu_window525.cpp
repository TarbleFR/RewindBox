// SPDX-License-Identifier: MIT
// Production methods are extracted unchanged by rpcs3_ppu_window525_test.py.
#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <fstream>
#include <iostream>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <type_traits>
#include <unordered_map>
#include <vector>
#include <sys/stat.h>
#include "Utilities/JITObjectBuffer.h"
#ifdef REAL_LLVM
#include <llvm/Support/MemoryBuffer.h>
#else
// Portable ownership adapter only. CI uses the real pinned LLVM MemoryBuffer.
namespace llvm {
class MemoryBuffer {
protected: std::vector<char> data;
public: virtual ~MemoryBuffer()=default;
 explicit MemoryBuffer(std::size_t size):data(size){}
 std::size_t getBufferSize()const{return data.size();}
 const char* getBufferStart()const{return data.data();}
};
class WritableMemoryBuffer final:public MemoryBuffer {
public: using MemoryBuffer::MemoryBuffer;
 char* getBufferStart(){return data.data();}
 static std::unique_ptr<WritableMemoryBuffer> getNewUninitMemBuffer(std::size_t size){return std::make_unique<WritableMemoryBuffer>(size);}
};
}
#endif
using u32=std::uint32_t;using u64=std::uint64_t;
namespace fs {
constexpr int read=0;
class file {
 std::ifstream stream;std::uint64_t length=0;
public:
 file(const std::string& path,int):stream(path,std::ios::binary){if(stream){stream.seekg(0,std::ios::end);length=stream.tellg();stream.seekg(0);}}
 explicit operator bool()const{return stream.is_open();}
 std::uint64_t size()const{return length;}
 void seek(std::uint64_t offset){stream.clear();stream.seekg(offset);}
 std::size_t read(void* output,std::size_t count){stream.read(static_cast<char*>(output),count);return stream.gcount();}
};
}
namespace jit_phase {enum phase{ppu_cache_read};struct scope{std::uint64_t bytes=0;template<class T>scope(phase,T){}};}
namespace utils {u64 get_tsc(){return 0;}}
struct log_adapter{template<class...T>void error(const char*,T&&...){assert(false);}}jit_log;
enum class ppu_llvm_pipeline_type{upstream,early_cse,extended};
struct selected_setting{ppu_llvm_pipeline_type value=ppu_llvm_pipeline_type::upstream;auto get()const{return value;}};
struct flag_setting{bool value=false;operator bool()const{return value;}};
struct {struct {selected_setting ppu_llvm_pipeline;flag_setting ppu_llvm_ir_passes;}core;}g_cfg;
namespace before {
#include "before.inc"
}
namespace after {
#include "after.inc"
}
constexpr std::size_t MiB=1024*1024;
std::size_t cases=0;
std::unique_ptr<llvm::MemoryBuffer> buffer(std::size_t size,char value='q'){
 auto result=llvm::WritableMemoryBuffer::getNewUninitMemBuffer(size);std::memset(result->getBufferStart(),value,size);return result;
}
void write_gzip(const std::string& path,std::size_t size,unsigned seed){
 std::vector<unsigned char> data(size);u64 n=seed+1;
 for(auto& byte:data){n^=n<<13;n^=n>>7;n^=n<<17;byte=static_cast<unsigned char>(n);}
 gzFile out=gzopen((path+".gz").c_str(),"wb1");assert(out);assert(gzwrite(out,data.data(),size)==int(size));assert(gzclose(out)==Z_OK);
}
void cleanup(){before::jit_compiler::release_cached_object_buffers();after::jit_compiler::release_cached_object_buffers();}
void regressions(const std::string& base){
 const auto path=base+"/identity";write_gzip(path,1024,1);
 const auto identity=after::object_identity(path);
 assert(identity.valid);
 // Actual old getter destroys an admitted object; the fixed pure getter keeps it.
 before::validated_objects().remember(path,before::object_identity(path),buffer(1024));
 after::validated_objects().remember(path,identity,buffer(1024));
 for(auto pipeline:{ppu_llvm_pipeline_type::upstream,ppu_llvm_pipeline_type::early_cse,ppu_llvm_pipeline_type::extended})for(bool ir:{false,true}){
  g_cfg.core.ppu_llvm_pipeline.value=pipeline;g_cfg.core.ppu_llvm_ir_passes.value=ir;
  assert(before::ppu_effective_pipeline()==after::ppu_effective_pipeline());++cases;
 }
 assert(before::validated_objects().bytes==0);
 assert(after::validated_objects().bytes==1024);++cases;
 after::jit_compiler::release_cached_object_buffers();
 // Nested boot/module/compilation owners keep all buffers through setting queries.
 {
  after::ppu_object_window_scope boot;
  after::validated_objects().remember(path,identity,buffer(1024));
  {after::ppu_object_window_scope check;assert(after::validated_objects().checked(path,identity));}
  assert(after::validated_objects().bytes==1024);
  {after::ppu_object_window_scope load;auto taken=after::validated_objects().take(path,identity);assert(taken&&taken->getBufferSize()==1024);}
  assert(after::validated_objects().bytes==0);
  after::validated_objects().remember(path,identity,buffer(1024));
 }
 assert(after::validated_objects().bytes==0&&after::validated_objects().checked(path,identity));++cases;
 // Return, stop/abort and failure exits execute the same production destructor.
 for(unsigned outcome=0;outcome<4;++outcome){
  auto leave=[&]{after::ppu_object_window_scope scope;after::validated_objects().remember(path,identity,buffer(1024));if(outcome<3)return;};
  leave();assert(after::validated_objects().bytes==0);++cases;
 }
 // Real parallel owners: the first exiting thread must not clear a live peer.
 std::mutex mutex;std::condition_variable cv;bool entered=false,release=false;
 {
  after::ppu_object_window_scope outer;
  std::thread worker([&]{
   after::ppu_object_window_scope other;
   after::validated_objects().remember(path,identity,buffer(1024));
   for(unsigned i=0;i<1000;++i)(void)after::ppu_effective_pipeline();
   std::unique_lock lock(mutex);entered=true;cv.notify_all();cv.wait(lock,[&]{return release;});
  });
  {std::unique_lock lock(mutex);cv.wait(lock,[&]{return entered;});}
  {after::ppu_object_window_scope nested;}
  assert(after::validated_objects().bytes==1024);
  {std::lock_guard lock(mutex);release=true;}cv.notify_all();worker.join();
  assert(after::validated_objects().bytes==1024);
 }
 assert(after::validated_objects().bytes==0);++cases;
 // File mutation still rejects the saved immutable buffer.
 {
  after::ppu_object_window_scope scope;
  after::validated_objects().remember(path,identity,buffer(1024));write_gzip(path,4096,2);
  const auto changed=after::object_identity(path);assert(changed!=identity);
  assert(!after::validated_objects().take(path,changed));assert(after::validated_objects().bytes==0);
 }++cases;
 // Budget remains shared across parallel loading owners, never 32 MiB per thread.
 {
  after::ppu_object_window_scope scope;
  std::thread a([&]{after::ppu_object_window_scope nested;for(unsigned i=0;i<10;++i)after::validated_objects().remember("a"+std::to_string(i),identity,buffer(4*MiB));});
  std::thread b([&]{after::ppu_object_window_scope nested;for(unsigned i=0;i<10;++i)after::validated_objects().remember("b"+std::to_string(i),identity,buffer(4*MiB));});
  a.join();b.join();assert(after::validated_objects().bytes<=32*MiB);
 }
 assert(after::validated_objects().bytes==0);++cases;
 // LLVM ownership transferred out of the window survives the last-owner cleanup.
 auto transfer=[&]{after::ppu_object_window_scope scope;after::validated_objects().remember(path,identity,buffer(1024,'x'));return after::validated_objects().take(path,identity);};
 auto transferred=transfer();assert(transferred&&transferred->getBufferSize()==1024&&transferred->getBufferStart()[1023]=='x');assert(after::validated_objects().bytes==0);++cases;
 static_assert(!std::is_copy_constructible_v<after::ppu_object_window_scope>);
 static_assert(!std::is_copy_assignable_v<after::ppu_object_window_scope>);
 cleanup();
}
struct result{u64 reads=0,bytes=0,hits=0,peak=0;double ms=0,cpu_ms=0;};
#define WORKLOAD(NS) \
result workload_##NS(const std::vector<std::string>& paths){ \
 NS::jit_compiler::release_cached_object_buffers(); \
 NS::validated_objects().entries.clear(); \
 result out;const auto start=std::chrono::steady_clock::now();const auto cpu_start=std::clock(); \
 { NS::owner_scope boot; \
  { NS::owner_scope check; \
   for(const auto& path:paths){ \
    (void)NS::ppu_effective_pipeline();auto id=NS::object_identity(path); \
    auto data=NS::ObjectCache::load(path);assert(data);++out.reads;out.bytes+=data->getBufferSize(); \
    NS::validated_objects().remember(path,id,std::move(data));out.peak=std::max<u64>(out.peak,NS::validated_objects().bytes); \
   } \
  } \
  { NS::owner_scope load; \
   for(const auto& path:paths){(void)NS::ppu_effective_pipeline();assert(NS::validated_objects().checked(path,NS::object_identity(path)));} \
   for(const auto& path:paths){auto data=NS::validated_objects().take(path,NS::object_identity(path)); \
    if(data)++out.hits;else{data=NS::ObjectCache::load(path);++out.reads;out.bytes+=data->getBufferSize();} \
    assert(data&&data->getBufferSize()==MiB); \
   } \
  } \
 } \
 out.ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();out.cpu_ms=1000.0*(std::clock()-cpu_start)/CLOCKS_PER_SEC; \
 assert(NS::validated_objects().bytes==0);return out; \
}
WORKLOAD(before)
WORKLOAD(after)
void print_result(const result& r){std::cout<<"{\"objectLoads\":"<<r.reads<<",\"logicalDecompressedBytes\":"<<r.bytes<<",\"bufferHits\":"<<r.hits<<",\"peakRetainedBytes\":"<<r.peak<<",\"ms\":"<<r.ms<<",\"cpuMs\":"<<r.cpu_ms<<'}';}
int main(int argc,char**argv){
 assert(argc>=2);const std::string base=argv[1];regressions(base);
 std::vector<std::string> paths;
 for(unsigned i=0;i<40;++i){paths.push_back(base+"/object-"+std::to_string(i));write_gzip(paths.back(),MiB,i+10);}
 std::cout<<"{\"passed\":true,\"cases\":"<<cases<<",\"budgetBytes\":"<<32*MiB<<",\"measurements\":[";
 const unsigned rounds=argc>2?12:1;
 for(unsigned round=0;round<rounds;++round){
  result old,now;if(round%2){now=workload_after(paths);old=workload_before(paths);}else{old=workload_before(paths);now=workload_after(paths);}
  assert(old.reads==80&&old.hits==0&&now.reads==48&&now.hits==32&&now.peak<=32*MiB);
  if(round)std::cout<<',';
  std::cout<<"{\"round\":"<<round<<",\"before\":";print_result(old);std::cout<<",\"after\":";print_result(now);std::cout<<'}';
 }
 std::cout<<"]}\n";
}

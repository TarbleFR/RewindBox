#include "SourceArchive.h"
#include <chrono>
#include <iostream>
#include <string>
#include <vector>
#include <cstdlib>
#include <algorithm>
#include <numeric>
using namespace neostation;
#define C(x) do{if(!(x)){std::cerr<<"failure "<<__LINE__<<" " #x "\n";std::abort();}}while(0)
using clock_type=std::chrono::steady_clock;
uint64_t micros(clock_type::time_point p){return std::chrono::duration_cast<std::chrono::microseconds>(clock_type::now()-p).count();}
int main(int argc,char**argv){C(argc==2);const std::string dir=argv[1];
 const size_t bytes=691200;std::string pixels(bytes,' ');uint64_t rng=45;for(char& b:pixels){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;b=static_cast<char>(rng);}
 for(uint32_t chunk:{65536u,262144u,1048576u}){
  source_archive::Config c;c.domain_mask=15;c.managed.chunk_bytes=chunk;c.managed.store.max_blob=chunk;c.managed.store.ram_bytes=std::max<uint64_t>(1ULL<<20,2ULL*chunk);c.managed.store.free_disk_floor=0;c.managed.store.max_write_bytes_per_second=0;c.managed.store.compression=false;
  source_archive::Archive a(dir,chunk,c);std::vector<uint64_t> writes,reads;uint64_t checkpoints=0,restored_chunks=0;
  for(unsigned i=0;i<10;++i){auto id=a.admit(3,pixels.data(),pixels.size());C(id.code==NS_SOURCE_OK);auto t=clock_type::now();while(a.maintain(1,4)){}writes.push_back(micros(t));C(a.snapshot().pending==0);
   // Require actual disk-backed demand instead of counting a RAM snapshot copy.
   auto b=a.snapshot();C(b.staging_bytes==0&&b.managed.resident_mapped_bytes==0);std::string output(bytes,'\0');int error=0;t=clock_type::now();C(a.read(id.object,output.data(),bytes,error)==NS_SOURCE_OK);reads.push_back(micros(t));C(output==pixels&&error==0);
   for(;;){auto events=a.drain_operations();for(size_t k=0;k<events.count;++k){checkpoints+=events.events[k].operation==source_archive::Operation::checkpoint;restored_chunks+=events.events[k].operation==source_archive::Operation::restored_chunk;}C(!events.dropped);if(!events.pending)break;}
   a.discard(id.object);while(a.maintain(1,4)){}C(a.snapshot().sources==0);C(a.snapshot().managed.resident_mapped_peak<=c.managed.resident_bytes);C(a.snapshot().staging_peak<=c.staging_bytes);
  }
  C(checkpoints==10*((bytes+chunk-1)/chunk)&&restored_chunks==checkpoints);
  auto s=a.snapshot();const auto write_total=std::accumulate(writes.begin(),writes.end(),uint64_t{}),read_total=std::accumulate(reads.begin(),reads.end(),uint64_t{});std::sort(writes.begin(),writes.end());std::sort(reads.begin(),reads.end());
  std::cout<<"{\"chunkBytes\":"<<chunk<<",\"records\":10,\"recordBytes\":"<<bytes<<",\"checkpoints\":"<<checkpoints<<",\"restoredChunks\":"<<restored_chunks<<",\"writeCalls\":"<<s.managed.store.write_calls<<",\"readCalls\":"<<s.managed.store.read_calls<<",\"checkpointTotalUs\":"<<write_total<<",\"readTotalUs\":"<<read_total<<",\"checkpointMedianUs\":"<<writes[5]<<",\"checkpointMaxUs\":"<<writes.back()<<",\"readMedianUs\":"<<reads[5]<<",\"readMaxUs\":"<<reads.back()<<",\"managedPeakBytes\":"<<s.managed.resident_mapped_peak<<",\"managedLimitBytes\":"<<c.managed.resident_bytes<<",\"backendWorkspaceBoundBytes\":"<<s.managed.backend_workspace_bound_bytes<<",\"stagingPeakBytes\":"<<s.staging_peak<<",\"physicalDeviceTested\":false}"<<std::endl;
 }
}

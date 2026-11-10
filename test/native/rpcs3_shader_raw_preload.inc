#include <array>
#include <bit>
#include <bitset>
#include <iostream>
#include <set>
#include <limits>
#include <tuple>
using u16=std::uint16_t;
constexpr struct max_value{template<class T>constexpr operator T() const{return std::numeric_limits<T>::max();}} umax;
constexpr usz max_vertex_program_instructions=544;
template<usz N>void pack_bitset(std::bitset<N>& out,const u64* input){for(usz i=0;i<N;++i)out[i]=((input[i/64]>>(i%64))&1)!=0;}
struct RSXFragmentProgram{
 @DATA@
 mutable data_storage_helper data{};
 u32 ucode_length=0,ctrl=0,texcoord_control_mask=0,mrt_buffers_count=0;
 bool two_sided_lighting=false;
 struct{u32 texture_dimensions=0;u16 shadow_textures=0,redirected_textures=0,multisampled_textures=0;}texture_state;
 @GET_DATA@
 @CLONE_DATA@
};
union v128{u32 _u32[4];u64 _u64[2];static v128 loadu(const void* data,int index){v128 out;std::memcpy(&out,static_cast<const char*>(data)+index*16,16);return out;}};
namespace fragment_program_utils{bool is_any_src_constant(v128);usz get_fragment_program_ucode_hash(const RSXFragmentProgram&);}
@HASH@
struct RSXVertexProgram{
 std::vector<u32>data;u32 ctrl=0,output_mask=0,base_address=0,entry=0;
 std::bitset<max_vertex_program_instructions>instruction_mask;std::set<u32>jump_table;
 struct{u32 texture_dimensions=0;u16 multisampled_textures=0;}texture_state;
};
struct Storage{
 u64 get_hash(const RSXFragmentProgram& p){return fragment_program_utils::get_fragment_program_ucode_hash(p);}
 u64 get_hash(const RSXVertexProgram& p){return p.data.empty()?0:p.data[0];}
 void preload_programs(void*,const RSXVertexProgram&,const RSXFragmentProgram& fp){RSXFragmentProgram clone=fp;clone.clone_data();assert(clone.get_data()!=fp.get_data());}
};
namespace fs{
struct dir_entry{std::string name;};
inline std::atomic<u64> fp_reads{0},fp_bytes{0};
inline std::atomic<bool> short_read{false};
struct file{
 std::ifstream f;bool fp;
 explicit file(const std::string& p):f(p,std::ios::binary),fp(p.ends_with(".fp")){}
 explicit operator bool()const{return f.is_open();}
 u64 size(){auto p=f.tellg();f.seekg(0,std::ios::end);auto n=f.tellg();f.seekg(p);return static_cast<u64>(n);}
 u64 read(void* p,usz n){if(fp&&short_read.load())n/=2;f.read(static_cast<char*>(p),n);auto count=static_cast<u64>(f.gcount());if(fp){++fp_reads;fp_bytes+=count;}return count;}
 bool read(std::vector<u32>& out,usz count){out.resize(count);return read(out.data(),count*sizeof(u32))==count*sizeof(u32);}
 void close(){f.close();}
};
inline void remove_file(const std::string& p){std::filesystem::remove(p);}
}
namespace fmt{
inline const char* printable(const std::string& s){return s.c_str();}
template<class T>auto printable(T v){if constexpr(std::is_integral_v<T>)return static_cast<unsigned long long>(v);else return v;}
template<class... T>std::string format(const char* pattern,const T&... v){char out[2048];std::snprintf(out,sizeof(out),pattern,printable(v)...);return out;}
}
struct Log{void error(auto&&...){};};inline Log rsx_log;
inline struct{std::atomic<bool> stopped{false};bool IsStopped(){return stopped.load();}}Emu;
struct shader_loading_dialog{};
@FIFO@
// BEGIN CACHE
class Cache{
public:
 using pipeline_storage_type=u64;
 @PIPELINE@
 @FP_CACHE@
 using unpacked_type=lf_fifo<std::tuple<pipeline_storage_type,RSXVertexProgram,RSXFragmentProgram>,64>;
 Storage m_storage;std::string root_path;
 lf_fifo<std::unique_ptr<u8[]>,100>fragment_program_data;
 static constexpr u64 maximum_raw_shader_size=0x100000;
 explicit Cache(std::string path):root_path(std::move(path)){}
 void await_workers(unsigned workers,u8,std::function<void(u32)>& work,atomic_t<u32>& processed,u32 count,shader_loading_dialog*){
   std::vector<std::thread>group;for(unsigned i=0;i<workers;++i)group.emplace_back([&]{work(count);});for(auto& t:group)t.join();assert(processed.load()==count||Emu.IsStopped());
 }
 @METHODS@
 struct Result{u64 reads=0,bytes=0,held=0,records=0;std::vector<u64> values;double elapsedUs=0;};
 Result run(const std::vector<u64>& keys,unsigned workers){
   std::filesystem::create_directories(root_path+"/raw");std::filesystem::create_directories(root_path+"/pipelines");
   {std::ofstream f(root_path+"/raw/1.vp",std::ios::binary);const u32 word=1;f.write(reinterpret_cast<const char*>(&word),sizeof(word));}
   for(u64 key:keys){std::vector<u8>data(8192,0);std::memcpy(data.data(),&key,8);std::ofstream f(fmt::format("%s/raw/%llX.fp",root_path,key),std::ios::binary);f.write(reinterpret_cast<const char*>(data.data()),data.size());}
   std::vector<fs::dir_entry>entries;for(usz i=0;i<keys.size();++i){pipeline_data p{};p.vertex_program_hash=1;p.fragment_program_hash=keys[i];p.pipeline_properties=i;p.vp_ctrl0=i;p.fp_ctrl=static_cast<u32>(i+10);p.fp_mrt_count=static_cast<u8>(i%4);p.fp_texcoord_control=i*7;p.fp_lighting_flags=i&1;p.vp_jump_table[0]=u16{umax};std::string name=std::to_string(i)+".bin";std::ofstream f(root_path+"/pipelines/"+name,std::ios::binary);f.write(reinterpret_cast<const char*>(&p),sizeof(p));entries.push_back({name});}
   unpacked_type unpacked;std::string directory=root_path+"/pipelines";fs::fp_reads=0;fs::fp_bytes=0;
   auto start=std::chrono::steady_clock::now();load_shaders(workers,unpacked,directory,entries,size32(entries),nullptr);auto end=std::chrono::steady_clock::now();
   Result result;result.reads=fs::fp_reads;result.bytes=fs::fp_bytes;result.held=fragment_program_data.size();result.records=unpacked.size();result.elapsedUs=std::chrono::duration<double,std::micro>(end-start).count();
   for(u32 item_index=0;item_index<unpacked.size();++item_index){auto&[index,vp,fp]=unpacked[item_index];assert(vp.ctrl==index&&fp.ctrl==index+10&&fp.texcoord_control_mask==index*7&&fp.mrt_buffers_count==index%4&&fp.two_sided_lighting==bool(index&1));assert(m_storage.get_hash(fp)==keys[index]);result.values.push_back(index);}
   std::sort(result.values.begin(),result.values.end());
   fragment_program_data.for_each([](auto& p){p.reset();});fragment_program_data.pop_end(fragment_program_data.size());return result;
 }
};
// END CACHE
int main(int argc,char** argv){
 assert(argc==2);const std::string base=argv[1];std::filesystem::create_directories(base);
 u64 total=0;std::cout<<"{\"cases\":[";bool first=true;
 for(const std::string name:{"identical","distinct_slots","collisions","unique"})for(unsigned workers:{1u,8u}){
  std::vector<u64>keys;for(u64 i=0;i<256;++i)keys.push_back(name=="identical"?1:name=="distinct_slots"?i%8+1:name=="collisions"?(i%3)*64+1:i+1);
  before::Cache a(base+"/old"+name+std::to_string(workers));after::Cache b(base+"/new"+name+std::to_string(workers));desktop::Cache d(base+"/desktop"+name+std::to_string(workers));
  const auto old=a.run(keys,workers);const auto now=b.run(keys,workers);const auto desk=d.run(keys,workers);
  assert(old.values==now.values&&old.values==desk.values&&old.records==256);assert(old.reads==256&&desk.reads==256);assert(now.held==now.reads&&old.held==old.reads);
  if(name=="identical")assert(now.reads>=1&&now.reads<=256&&(workers!=1||now.reads==1));
  if(name=="distinct_slots")assert(now.reads>=8&&now.reads<=256&&(workers!=1||now.reads==8));
  if(name=="unique")assert(now.reads==256);
  // A second pass must reopen the files; no pointer survives the first pass.
  const auto repeat=b.run(keys,workers);assert(now.values==repeat.values);if(name=="identical")assert(repeat.reads>=1&&repeat.reads<=256&&(workers!=1||repeat.reads==1));
  total+=now.records+repeat.records;
  std::vector<double> old_samples{old.elapsedUs},new_samples{now.elapsedUs};
  for(int sample=1;sample<7;++sample){
    if(sample&1){const auto n=b.run(keys,workers);const auto o=a.run(keys,workers);new_samples.push_back(n.elapsedUs);old_samples.push_back(o.elapsedUs);assert(n.values==o.values);}
    else{const auto o=a.run(keys,workers);const auto n=b.run(keys,workers);new_samples.push_back(n.elapsedUs);old_samples.push_back(o.elapsedUs);assert(n.values==o.values);}
  }
  auto old_sorted=old_samples,new_sorted=new_samples;std::sort(old_sorted.begin(),old_sorted.end());std::sort(new_sorted.begin(),new_sorted.end());
  if(!first)std::cout<<",";
  first=false;
  std::cout<<"{\"name\":\""<<name<<"\",\"workers\":"<<workers<<",\"beforeReads\":"<<old.reads<<",\"afterReads\":"<<now.reads<<",\"beforeBytes\":"<<old.bytes<<",\"afterBytes\":"<<now.bytes<<",\"beforeScratchBytes\":"<<old.held*8192<<",\"afterScratchBytes\":"<<now.held*8192<<",\"beforeUs\":"<<old.elapsedUs<<",\"afterUs\":"<<now.elapsedUs<<",\"beforeMedianUs\":"<<old_sorted[3]<<",\"afterMedianUs\":"<<new_sorted[3]<<",\"beforeSamplesUs\":[";
  for(usz n=0;n<old_samples.size();++n){if(n)std::cout<<",";std::cout<<old_samples[n];}std::cout<<"],\"afterSamplesUs\":[";
  for(usz n=0;n<new_samples.size();++n){if(n)std::cout<<",";std::cout<<new_samples[n];}std::cout<<"]}";
 }
 after::Cache errors(base+"/errors");std::filesystem::create_directories(errors.root_path+"/raw");after::Cache::raw_fragment_cache cache;
 auto put=[&](u64 name,u64 contents,usz size){std::vector<u8>data(size,0);if(size>=8)std::memcpy(data.data(),&contents,8);std::ofstream f(fmt::format("%s/raw/%llX.fp",errors.root_path,name),std::ios::binary);f.write(reinterpret_cast<const char*>(data.data()),data.size());};
 // Missing, truncated, oversized and bad-hash payloads must not poison a slot.
 assert(!errors.load_fp_raw_cached(7,cache).ucode_length);put(7,7,16);assert(errors.load_fp_raw_cached(7,cache).ucode_length==16);
 put(8,8,8192);fs::short_read=true;assert(!errors.load_fp_raw_cached(8,cache).ucode_length);fs::short_read=false;put(8,8,16);assert(errors.load_fp_raw_cached(8,cache).ucode_length==16);
 put(9,9,0x100001);assert(!errors.load_fp_raw_cached(9,cache).ucode_length);put(9,9,16);assert(errors.load_fp_raw_cached(9,cache).ucode_length==16);
 put(10,11,16);auto wrong=errors.load_fp_raw_cached(10,cache);assert(errors.m_storage.get_hash(wrong)==11);put(10,10,16);assert(errors.m_storage.get_hash(errors.load_fp_raw_cached(10,cache))==10);
 // A slot collision must not invalidate already returned bytes.
 put(71,71,16);auto borrowed=errors.load_fp_raw_cached(7,cache);auto collision=errors.load_fp_raw_cached(71,cache);assert(errors.m_storage.get_hash(borrowed)==7&&errors.m_storage.get_hash(collision)==71);
 Emu.stopped=true;after::Cache cancelled(base+"/cancelled");const auto stop=cancelled.run({1,1,1},8);assert(stop.records==0&&stop.reads==0);Emu.stopped=false;
 std::cout<<"],\"recordsVerified\":"<<total<<",\"errorRecoveryCases\":4,\"passLifetimeChecked\":true,\"collisionLifetimeChecked\":true,\"cancellationChecked\":true,\"desktopUnchanged\":true}\n";
}

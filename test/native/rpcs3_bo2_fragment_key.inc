#include <algorithm>
#include <array>
#include <atomic>
#include <bit>
#include <bitset>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <concepts>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <iostream>
#include <memory>
#include <mutex>
#include <random>
#include <set>
#include <shared_mutex>
#include <span>
#include <source_location>
#include <string>
#include <thread>
#include <tuple>
#include <type_traits>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>
#ifdef NDEBUG
#error "This production harness requires active assertions. Pass -UNDEBUG after optimization flags."
#endif
using usz=std::size_t; using uchar=unsigned char;
using u64=std::uint64_t; using u32=std::uint32_t; using u16=std::uint16_t;
using u8=std::uint8_t; using f32=float;
namespace fmt {template<class... T>[[noreturn]]void raw_range_error(T&&...){std::abort();}}
template<class T>T format_object_simplified(T value){return value;}
template<class T> using atomic_t=std::atomic<T>;
using shared_mutex=std::shared_mutex;
struct reader_lock {
    shared_mutex& mutex; bool exclusive=false;
    explicit reader_lock(shared_mutex& m):mutex(m){mutex.lock_shared();}
    void upgrade(){mutex.unlock_shared();mutex.lock();exclusive=true;}
    ~reader_lock(){if(exclusive)mutex.unlock();else mutex.unlock_shared();}
};
#define ensure(condition, ...) assert(condition)
using uint32x4_t=std::array<u32,4>;
inline uint32x4_t veorq_u32(uint32x4_t a,uint32x4_t b){for(usz i=0;i<4;++i)a[i]^=b[i];return a;}
inline u32 vmaxvq_u32(uint32x4_t a){return *std::max_element(a.begin(),a.end());}
union v128 {
    __uint128_t _u; u64 _u64[2];u32 _u32[4];
    static v128 loadu(const void* p,usz index=0){v128 v;std::memcpy(&v,static_cast<const u8*>(p)+index*16,16);return v;}
    explicit operator uint32x4_t()const{return {_u32[0],_u32[1],_u32[2],_u32[3]};}
};
namespace rsx {inline constexpr u32 max_vertex_program_instructions=544; enum class texture_dimension_extended:u8 {texture_dimension_1d,texture_dimension_2d,texture_dimension_cubemap,texture_dimension_3d};}

#include <optional>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string_view>
#include <limits>
#include <new>
using s32=std::int32_t;
using namespace std::literals;
constexpr u32 umax=~u32{0};
template<class T>u32 size32(const T& value){return static_cast<u32>(value.size());}
namespace utils {template<class T>T* bless(void* p){return static_cast<T*>(p);}}
namespace fmt {
template<class... T> std::string format(const char* fmt,T... args) {
  int n=std::snprintf(nullptr,0,fmt,args...);assert(n>=0);
  std::vector<char> s(n+1);std::snprintf(s.data(),s.size(),fmt,args...);return std::string(s.data(),n);
}
template<class... T> [[noreturn]] void throw_exception(const char* msg,T...) {throw std::runtime_error(msg);}
std::string replace_all(std::string s,std::initializer_list<std::pair<std::string,std::string>> repl) {
 for(const auto& [a,b]:repl)for(usz i=0;(i=s.find(a,i))!=std::string::npos;i+=b.size())s.replace(i,a.size(),b);
 return s;
}
}

struct logger {template<class...T>void error(const char*,T...){} template<class...T>void fatal(const char*,T...){assert(false);}
 template<class...T>void trace(const char*,T...){} template<class...T>void notice(const char*,T...){} template<class...T>void success(const char*,T...){} } rsx_log;
namespace rsx::assembler {struct Instruction{u32 length=4,addr=0; std::array<u32,4> bytecode{};};}
constexpr u32 CELL_GCM_SHADER_CONTROL_32_BITS_EXPORTS=0x40;
constexpr u32 CELL_GCM_SHADER_CONTROL_DEPTH_EXPORT=0xE;
constexpr u32 RSX_SHADER_CONTROL_FLAT_SHADING=0x800;
constexpr u32 RSX_SHADER_CONTROL_ATTRIBUTE_INTERPOLATION=0x10000;
// @PRODUCTION_TYPES@

namespace rsx {
bool fragment_program_texture_state::operator==(const fragment_program_texture_state& p)const {
    return texture_dimensions==p.texture_dimensions&&redirected_textures==p.redirected_textures&&shadow_textures==p.shadow_textures&&multisampled_textures==p.multisampled_textures;
}
bool vertex_program_texture_state::operator==(const vertex_program_texture_state& p)const {
    return texture_dimensions==p.texture_dimensions&&multisampled_textures==p.multisampled_textures;
}
}

namespace rsx::assembler::FP {
// Annotation/lane boundary: enumerate every lane mask, independent of the
// dead properties being removed. This is not the complete decompiler.
thread_local u32 tested_lanes=15;
u32 get_src_vector_lane_mask_shuffled(const RSXFragmentProgram&,const Instruction*,u32){return tested_lanes;}
}
using namespace rsx::assembler;
// @PRODUCTION_HASHES@
// @PRODUCTION_HINTS@
struct FragmentProgramDecompiler {
 enum OPFLAGS {src_cast_f32=2};
 const RSXFragmentProgram& m_prog;
 OPDEST dst{};SRC0 src0{};SRC1 src1{};SRC2 src2{};
 u32 opflags=0,m_loop_count=0;
 bool m_is_valid_ucode=true;
 const Instruction* m_instruction=nullptr;
 std::unordered_map<u32,u32> m_constant_offsets;
 struct {u16 in_register_mask=0,common_access_sampler_mask=0,shadow_sampler_mask=0;
 bool has_w_access=false,has_dynamic_register_load=false,has_clamp=false;
 std::vector<u32> constant_offsets;} properties;
 struct {bool has_native_half_support=false;} device_props;
 ParamArray m_parr;
 explicit FragmentProgramDecompiler(const RSXFragmentProgram& p):m_prog(p){}
 static std::string getFloatTypeName(usz n){return n==1?"float":"vec"+std::to_string(n);}
 static std::string getHalfTypeName(usz n){return n==1?"float16_t":"f16vec"+std::to_string(n);}
 std::string AddReg(u32,bool);std::string AddConst();std::string ClampValue(const std::string&,u32);
 template<class T>std::string GetSRC(T);
};
// @PRODUCTION_DECOMPILER@
namespace glsl {struct two_sided_lighting_config {bool two_sided_color=false,two_sided_specular=false;};
// @PRODUCTION_INPUT_BLOCK@
}
struct VKFragmentDecompilerThread:FragmentProgramDecompiler {
 using FragmentProgramDecompiler::FragmentProgramDecompiler;
 enum {in_wpos=1,in_diff_color=2,in_spec_color=4,in_fogc=8,in_ssa=1<<14};
 void insertMainStart(std::stringstream&);
};
// @PRODUCTION_MAIN_START@
u32 decode_word(u32 x){return ((x&0xff00ffu)<<8)|((x&0xff00ff00u)>>8);}
std::array<u32,4> instruction(u32 opcode,u32 input,u32 srcidx=0,bool end=true) {
 OPDEST d{};d.opcode=opcode&63;d.src_attr_reg_num=input;d.end=end;d.write_mask=15;
 SRC0 s0{};s0.reg_type=0;s0.exec_if_lt=s0.exec_if_eq=s0.exec_if_gr=1;
 s0.swizzle_y=1;s0.swizzle_z=2;s0.swizzle_w=3;
 SRC1 s1{};s1.reg_type=0;s1.opcode_hi=opcode>>6;s1.swizzle_y=1;s1.swizzle_z=2;s1.swizzle_w=3;
 SRC2 s2{};s2.reg_type=0;s2.swizzle_y=1;s2.swizzle_z=2;s2.swizzle_w=3;
 std::array<u32,4> r{d.HEX,s0.HEX,s1.HEX,s2.HEX};
 r[srcidx+1]=(r[srcidx+1]&~3u)|RSX_FP_REGISTER_TYPE_INPUT;
 for(auto& x:r)x=decode_word(x);
 return r;
}
std::string generated(const RSXFragmentProgram& p,u32 srcidx,u32 lanes) {
 std::array<u32,4> raw;std::memcpy(raw.data(),p.get_data(),16);
 VKFragmentDecompilerThread d(p);d.dst.HEX=decode_word(raw[0]);d.src0.HEX=decode_word(raw[1]);
 d.src1.HEX=decode_word(raw[2]);d.src2.HEX=decode_word(raw[3]);
 Instruction inst{};inst.bytecode={d.dst.HEX,d.src0.HEX,d.src1.HEX,d.src2.HEX};d.m_instruction=&inst;
 FP::tested_lanes=lanes;
 const std::string expr=srcidx==0?d.GetSRC(d.src0):srcidx==1?d.GetSRC(d.src1):d.GetSRC(d.src2);
 std::stringstream s;
 s<<"#version 450\n";
 glsl::insert_fragment_shader_inputs_block(s,"EXT",p,d.m_parr.params[PF_PARAM_IN],
   {bool(d.properties.in_register_mask&2),bool(d.properties.in_register_mask&4)},
   [](std::string_view name){
    if(name=="diff_color"||name=="diff_color0")return 0;
    if(name=="spec_color"||name=="spec_color0")return 1;
    if(name=="diff_color1")return 2;
    if(name=="spec_color1")return 3;
    if(name=="fogc")return 4;
    return 5+std::stoi(std::string(name.substr(2)));
   });
 s<<"layout(location=0) out vec4 result;\nvec4 _saturate(vec4 x){return clamp(x,vec4(0),vec4(1));}\n";
 if(d.properties.in_register_mask&1)s<<"vec4 get_wpos(){return gl_FragCoord;}\n";
 if(d.properties.in_register_mask&8)s<<"const int fog_mode=0;vec4 fetch_fog_value(int mode){return fog_c;}\n";
 d.insertMainStart(s);
 s<<"result="<<expr<<";\n}\nvoid main(){fs_main();}\n";
 return s.str();
}

namespace rpcs3::ios::shader_timing {
struct BuildOriginScope{explicit BuildOriginScope(u32){}};
struct Profile{void record_origin(u32){} struct Recorder{void record(u64){}} pending_wait;std::atomic<u64> abandoned{0};};
inline Profile pipeline_profile;
}
namespace rpcs3::ios::compile_pressure {struct BlockingBuildScope{explicit BlockingBuildScope(bool){}};}
namespace rsx {inline void write_fragment_constants_to_buffer(std::span<f32>,const RSXFragmentProgram&,const std::vector<u32>&,bool){}}
struct TestShader {u32 id=0;std::string glsl;std::vector<u32> constant_offsets;};
struct TestPipeline{};
struct TestProps {u32 field=0;bool operator==(const TestProps&)const=default;};
struct Traits {
 using vertex_program_type=TestShader;using fragment_program_type=TestShader;
 using pipeline_type=TestPipeline;using pipeline_storage_type=std::unique_ptr<TestPipeline>;using pipeline_properties=TestProps;
 inline static std::atomic<u64> compilations{0};
 inline static bool compile_source=true;
 inline static std::atomic<bool> gate{false},entered{false};
 inline static std::function<void()> inspect;
 static void recompile_vertex_program(const RSXVertexProgram&,TestShader& s,usz id){s.id=static_cast<u32>(id);}
 static void recompile_fragment_program(const RSXFragmentProgram& p,TestShader& s,usz id){
  if(inspect)inspect();
  if(gate.load()){entered=true;while(gate.load())std::this_thread::yield();}
  s.id=static_cast<u32>(id);if(compile_source)s.glsl=generated(p,0,15);++compilations;
 }
};
// @PRODUCTION_CACHES@
// Allocation boundary pauses deep_copy before it mutates local_storage/data_ptr.
// Both versions resume only after the inspecting reader has released its lock.
// Thus the baseline demonstrates early publication without introducing a race.
namespace clone_probe {
thread_local bool armed=false;
inline std::atomic<bool> entered{false},hold{false};
inline std::atomic<usz> target{0};
}
[[gnu::noinline]] void* operator new(std::size_t bytes) {
 if(clone_probe::armed && bytes==clone_probe::target.load()){
  clone_probe::armed=false;clone_probe::entered=true;
  while(clone_probe::hold.load())std::this_thread::yield();
 }
 if(void* p=std::malloc(bytes?bytes:1)) return p;
 throw std::bad_alloc();
}
[[gnu::noinline]] void operator delete(void* p) noexcept {std::free(p);}
[[gnu::noinline]] void operator delete(void* p,std::size_t) noexcept {std::free(p);}
[[gnu::noinline]] void* operator new[](std::size_t bytes){return ::operator new(bytes);}
[[gnu::noinline]] void operator delete[](void* p) noexcept {std::free(p);}
[[gnu::noinline]] void operator delete[](void* p,std::size_t) noexcept {std::free(p);}

template<class Base>struct Exposed:Base {
 using Base::search_fragment_program;
 auto fragment(const RSXFragmentProgram& p,rsx::program_cache_hint_t* h=nullptr){return this->search_fragment_program(h,p);}
 void reset(){this->clear();}
 usz count()const{return this->m_fragment_shader_cache.size();}
 bool remembered()const{for(const auto& h:this->m_recent_fragment_shaders)if(h.load())return true;return false;}
 bool lock_free(){if(!this->m_fragment_mutex.try_lock_shared())return false;this->m_fragment_mutex.unlock_shared();return true;}
 bool observes_borrowed(const void* guest){
  if(!this->m_fragment_mutex.try_lock_shared())return false;
  bool found=false;for(const auto& x:this->m_fragment_shader_cache)found|=x.first.get_data()==guest;
  this->m_fragment_mutex.unlock_shared();return found;
 }
};
using Before=Exposed<before_cache<Traits>>;using After=Exposed<after_cache<Traits>>;
struct Hint:rsx::program_cache_hint_t {
 bool analysed()const{return m_fragment_input_mask.has_value();}
 u16 mask()const{assert(m_fragment_input_mask);return *m_fragment_input_mask;}
};
RSXFragmentProgram program(void* data,u32 bytes=16){RSXFragmentProgram p;p.data=data;p.ucode_length=bytes;p.total_length=bytes;p.texture_state.texture_dimensions=0x55555555u;return p;}
RSXFragmentProgram normalized(const RSXFragmentProgram& p) {
 auto result=fragment_program_utils::normalize_fragment_program_key(p,fragment_program_utils::get_fragment_program_input_mask(p));
 return result?*result:p;
}
void set_type(std::array<u32,4>& w,u32 source,u32 type){w[source+1]=(w[source+1]&~0x300u)|(type<<8);}
std::vector<u32> long_program(u32 count,bool input){
 std::vector<u32> words;words.reserve(count*4);
 for(u32 i=0;i<count;++i){auto w=instruction(RSX_FP_OPCODE_MAD,4,0,i==count-1);if(!input)set_type(w,0,0);words.insert(words.end(),w.begin(),w.end());}
 return words;
}
struct Results {u64 equivalent=0,live=0,fallback=0,parsers=0,unique=0;};
Results generator_tests(const std::filesystem::path& output) {
 Results r;std::set<std::string> outputs;
 for(u32 input=0;input<15;++input)for(u32 source=0;source<3;++source)for(u32 lanes=1;lanes<16;++lanes)for(u32 mode=0;mode<8;++mode){
  auto w=instruction(RSX_FP_OPCODE_MAD,input,source);auto raw=program(w.data());
  raw.texcoord_control_mask=(mode&1?0x3ffu:0)|(mode&2?0x3ff0000u:0);
  raw.two_sided_lighting=mode&4;raw.ctrl=mode&4?RSX_SHADER_CONTROL_FLAT_SHADING:0;
  auto key=normalized(raw);const auto a=generated(raw,source,lanes),b=generated(key,source,lanes);
  assert(a==b);outputs.insert(a);++r.equivalent;
  if(input>=4&&input<=13){auto live=key;live.texcoord_control_mask^=1u<<(input-4+16);assert(generated(live,source,lanes)!=b);++r.live;}
  if(input==1||input==2){auto live=key;live.two_sided_lighting=!key.two_sided_lighting;assert(generated(live,source,lanes)!=b);++r.live;}
 }
 r.unique=outputs.size();assert(r.equivalent==5400&&r.live==4320&&r.unique==67);
 if(!output.empty()){std::filesystem::create_directories(output);usz i=0;for(const auto& text:outputs){std::ofstream file(output/(std::to_string(i++)+".frag"));file<<text;}}
 // Independent cases derived from the full consumer instruction dispatch.
 for(const auto& [opcode,operands]:std::array<std::pair<u32,u32>,8>{{{RSX_FP_OPCODE_NOP,0},{RSX_FP_OPCODE_KIL,0},{RSX_FP_OPCODE_STR,0},{RSX_FP_OPCODE_SFL,0},{RSX_FP_OPCODE_MOV,1},{RSX_FP_OPCODE_MUL,2},{RSX_FP_OPCODE_MAD,3},{RSX_FP_OPCODE_TXD,3}}}){
  for(u32 source=0;source<3;++source){auto w=instruction(opcode,7,source);auto p=program(w.data());
   assert(fragment_program_utils::get_fragment_program_input_mask(p)==(source<operands?(1u<<7):0));++r.parsers;
  }
 }
 // In particular, TXD's gradient operands are real GLSL consumers even though
 // the assembler annotation reports only one coordinate operand.
 assert(FP::get_operand_count(RSX_FP_OPCODE_TXD)==1);
 for(u32 source:{1,2}){auto w=instruction(RSX_FP_OPCODE_TXD,7,source);auto p=program(w.data());p.texcoord_control_mask=0x3ff03ff;
  auto n=normalized(p);assert(n.texcoord_control_mask==((1u<<3)|(1u<<19)));assert(generated(n,source,15)==generated(p,source,15));++r.parsers;}
 for(u32 op:{u32(RSX_FP_OPCODE_BRK),u32(RSX_FP_OPCODE_CAL),u32(RSX_FP_OPCODE_IFE),u32(RSX_FP_OPCODE_LOOP),u32(RSX_FP_OPCODE_REP),u32(RSX_FP_OPCODE_RET),u32(RSX_FP_OPCODE_POW),u32(RSX_FP_OPCODE_BEM),u32(RSX_FP_OPCODE_TEXBEM),u32(RSX_FP_OPCODE_TXPBEM),u32(RSX_FP_OPCODE_BEMLUM),u32(RSX_FP_OPCODE_TIMESWTEX),0x30u,0x32u,0x3fu,127u}){
  for(bool input:{false,true}){auto w=instruction(op,4);if(!input)set_type(w,0,0);auto p=program(w.data());assert(fragment_program_utils::get_fragment_program_input_mask(p)==0xffff);++r.fallback;}
 }
 for(u32 source=0;source<3;++source){auto w=instruction(RSX_FP_OPCODE_MAD,4,source);w[3]=decode_word(decode_word(w[3])|(1u<<30));auto p=program(w.data());assert(fragment_program_utils::get_fragment_program_input_mask(p)==0xffff);++r.fallback;
  w=instruction(RSX_FP_OPCODE_MAD,15,source);p=program(w.data());assert(fragment_program_utils::get_fragment_program_input_mask(p)==0xffff);++r.fallback;
  w=instruction(RSX_FP_OPCODE_MAD,4,source);set_type(w,source,3);p=program(w.data());assert(fragment_program_utils::get_fragment_program_input_mask(p)==0xffff);++r.fallback;
 }
 auto good=instruction(RSX_FP_OPCODE_MOV,4);auto p=program(good.data());
 for(u32 len:{0u,1u,15u,17u}){p.ucode_length=len;assert(fragment_program_utils::get_fragment_program_input_mask(p)==0xffff);++r.fallback;}
 p=program(nullptr);assert(fragment_program_utils::get_fragment_program_input_mask(p)==0xffff);++r.fallback;
 good[0]&=~0x100u;p=program(good.data());assert(fragment_program_utils::get_fragment_program_input_mask(p)==0xffff);++r.fallback;
 good=instruction(RSX_FP_OPCODE_MAD,4);set_type(good,1,2);
 std::array<u32,8> constant{};std::copy(good.begin(),good.end(),constant.begin());
 // Literal bytes deliberately resemble flow/indirect INPUT words; never scan them.
 std::fill(constant.begin()+4,constant.end(),0xffffffffu);p=program(constant.data(),32);
 assert(fragment_program_utils::get_fragment_program_input_mask(p)==(1u<<4));++r.parsers;
 const auto metadata=fragment_program_utils::analyse_fragment_program(p.get_data());
 assert(metadata.program_ucode_length==32&&metadata.program_constants_buffer_length==16);
 p.ucode_length=16;assert(fragment_program_utils::get_fragment_program_input_mask(p)==0xffff);++r.fallback;
 std::array<u32,12> leading{};auto nop=instruction(RSX_FP_OPCODE_NOP,14,2,false);std::copy(nop.begin(),nop.end(),leading.begin());std::copy(constant.begin(),constant.end(),leading.begin()+4);
 p=program(leading.data(),48);assert(fragment_program_utils::get_fragment_program_input_mask(p)==(1u<<4));
 const auto shifted=fragment_program_utils::analyse_fragment_program(p.get_data());assert(shifted.program_start_offset==16&&shifted.program_ucode_length==32);
 auto view=program(leading.data()+4,shifted.program_ucode_length);assert(fragment_program_utils::get_fragment_program_input_mask(view)==fragment_program_utils::get_fragment_program_input_mask(p));++r.parsers;
 p=program(leading.data(),48);leading[0]|=0x100u;assert(fragment_program_utils::get_fragment_program_input_mask(p)==0xffff);++r.fallback;
 return r;
}
std::pair<u64,u64> variant_trace(){
 auto w=instruction(RSX_FP_OPCODE_MOV,4);auto p=program(w.data());
 Before before;After after;Traits::compilations=0;
 auto query=[&](auto& cache){for(u32 i=0;i<2048;++i){p.texcoord_control_mask=(i&511)<<1;p.two_sided_lighting=i&512;p.ctrl=i&1024?RSX_SHADER_CONTROL_FLAT_SHADING:0;
  auto result=cache.fragment(p);assert(std::get<0>(result).glsl==generated(p,0,15));}}
 ;query(before);const u64 old=Traits::compilations;Traits::compilations=0;query(after);const u64 now=Traits::compilations;
 assert(old==2048&&now==1&&after.count()==1&&before.count()==2048);
 p.texcoord_control_mask=1u<<16;const u32 live_id=std::get<0>(after.fragment(p)).id;assert(after.count()==2);
 p.ctrl^=CELL_GCM_SHADER_CONTROL_32_BITS_EXPORTS;assert(std::get<0>(after.fragment(p)).id!=live_id);
 p.mrt_buffers_count++;assert(!std::get<1>(after.fragment(p)));
 p.texture_state.multisampled_textures=1;assert(!std::get<1>(after.fragment(p)));
 // Equal canonical keys must use exactly the same existing hash and comparison.
 auto a=normalized(p);p.texcoord_control_mask^=2u;auto b=normalized(p);
 assert(fragment_program_compare{}(a,b)&&fragment_program_storage_hash{}(a)==fragment_program_storage_hash{}(b));
 // Both colour properties remain live, unlike texcoord bits on this shader.
 w=instruction(RSX_FP_OPCODE_MOV,1);p=program(w.data());after.reset();
 for(u32 i=0;i<4;++i){p.two_sided_lighting=i&1;p.ctrl=i&2?RSX_SHADER_CONTROL_FLAT_SHADING:0;assert(!std::get<1>(after.fragment(p)));}assert(after.count()==4);
 // Constants are ignored by the original hash/compare; they remain ignored.
 w=instruction(RSX_FP_OPCODE_MAD,4);set_type(w,1,2);std::array<u32,8> constants{};std::copy(w.begin(),w.end(),constants.begin());p=program(constants.data(),32);p.texcoord_control_mask=0x3fe;
 const u32 id=std::get<0>(after.fragment(p)).id;for(u32 i=0;i<100;++i){constants[4]=i;assert(std::get<0>(after.fragment(p)).id==id);}
 return {old,now};
}
void hint_tests(){
 After cache;Hint hint;auto w=instruction(RSX_FP_OPCODE_MOV,4);auto p=program(w.data());
 cache.fragment(p,&hint);assert(!hint.analysed());
 // has_fragment_program returns without reading even an unavailable blob.
 auto unreadable=p;unreadable.data=nullptr;cache.fragment(unreadable,&hint);assert(!hint.analysed());
 hint.invalidate(rsx::fragment_program_state_dirty);p.texcoord_control_mask=1u<<9;cache.fragment(p,&hint);assert(hint.analysed()&&hint.mask()==(1u<<4));
 hint.invalidate(rsx::fragment_program_state_dirty);assert(hint.analysed());p.texcoord_control_mask^=1u<<8;cache.fragment(p,&hint);
 hint.invalidate(rsx::fragment_program_ucode_dirty);assert(!hint.analysed()&&!hint.has_fragment_program());
 w=instruction(RSX_FP_OPCODE_MOV,1);p.two_sided_lighting=true;cache.fragment(p,&hint);assert(hint.mask()==2);
 const auto color=std::get<0>(cache.fragment(p,&hint)).glsl;hint.invalidate(rsx::fragment_program_state_dirty);p.two_sided_lighting=false;assert(std::get<0>(cache.fragment(p,&hint)).glsl!=color);
 hint.invalidate(rsx::fragment_program_ucode_dirty);w=instruction(RSX_FP_OPCODE_IFE,4);p.texcoord_control_mask=1u<<9;cache.fragment(p,&hint);assert(hint.analysed()&&hint.mask()==0xffff);
 hint.invalidate(rsx::fragment_program_state_dirty);assert(hint.mask()==0xffff);assert(hint.get_fragment_input_mask(unreadable)==0xffff);
 // Dirty is applied before the existing prefetch; a new ucode must replace the
 // retained conservative mask even if the old/new metadata lengths match.
 hint.invalidate(rsx::fragment_program_ucode_dirty);w=instruction(RSX_FP_OPCODE_MOV,7);cache.fragment(p,&hint);assert(hint.mask()==(1u<<7));
}
template<class Cache>bool clone_publication(){
 Cache cache;auto words=long_program(512,false);auto p=program(words.data(),static_cast<u32>(words.size()*4));
 clone_probe::target=p.ucode_length;clone_probe::hold=true;clone_probe::entered=false;
 Traits::inspect=[&]{assert(cache.lock_free());};
 std::thread writer([&]{clone_probe::armed=true;cache.fragment(p);});
 while(!clone_probe::entered.load())std::this_thread::yield();
 const bool exposed=cache.observes_borrowed(p.get_data());
 clone_probe::hold=false;writer.join();Traits::inspect={};
 assert(!cache.observes_borrowed(p.get_data()));
 const auto id=std::get<0>(cache.fragment(p)).id;
 words[1]^=0x400u;assert(std::get<0>(cache.fragment(p)).id!=id);
 return exposed;
}
void concurrent_preload(){
 After cache;auto w=instruction(RSX_FP_OPCODE_MOV,4);auto base=program(w.data());base.texcoord_control_mask=2;
 Traits::gate=true;Traits::entered=false;Traits::compilations=0;
 std::thread first([&]{cache.fragment(base);});while(!Traits::entered.load())std::this_thread::yield();
 std::array<std::thread,8> others;
 for(u32 i=0;i<others.size();++i)others[i]=std::thread([&,i]{auto p=base;p.texcoord_control_mask=(i+2)<<1;assert(std::get<1>(cache.fragment(p)));});
 for(auto& t:others)t.join();
 assert(cache.count()==1&&!cache.remembered());
 Traits::gate=false;first.join();assert(Traits::compilations==1);const auto id=std::get<0>(cache.fragment(base)).id;
 for(u32 i=0;i<4;++i)others[i]=std::thread([&,i]{for(u32 j=0;j<2000;++j){auto p=base;p.texcoord_control_mask=((j+i)%511+1)<<1;assert(std::get<0>(cache.fragment(p)).id==id);}});
 others[4]=std::thread([&]{for(u32 j=1;j<512;++j){auto p=base;p.ctrl=j<<16;cache.fragment(p);}});
 for(u32 i=0;i<5;++i)others[i].join();
 assert(std::get<0>(cache.fragment(base)).id==id);
 cache.reset();assert(!cache.remembered());assert(std::get<0>(cache.fragment(base)).id!=id);
}
template<class F>double median_ns(F fn,u32 count){
 std::array<double,7> trials{};u64 sum=0;
 for(auto& ns:trials){const auto start=std::chrono::steady_clock::now();for(u32 i=0;i<count;++i){asm volatile("":::"memory");sum+=fn(i);}
  ns=std::chrono::duration<double,std::nano>(std::chrono::steady_clock::now()-start).count()/count;}
 assert(sum);std::sort(trials.begin(),trials.end());return trials[3];
}
template<class Cache>double cold_lookup(const RSXFragmentProgram& p){
 Cache cache;std::array<double,7> trials{};u64 sum=0;
 for(auto& ns:trials){double total=0;for(u32 i=0;i<700;++i){cache.reset();const auto start=std::chrono::steady_clock::now();sum+=std::get<0>(cache.fragment(p)).id+1;total+=std::chrono::duration<double,std::nano>(std::chrono::steady_clock::now()-start).count();}ns=total/700;}
 assert(sum);std::sort(trials.begin(),trials.end());return trials[3];
}
void benchmarks(){
 std::cout<<",\"hostNanoseconds\":[";bool first=true;Traits::compile_source=false;
 for(u32 length:{16,256,2048}){
 auto words=long_program(length,false);auto p=program(words.data(),static_cast<u32>(words.size()*4));
 const double ba=median_ns([&](u32){auto m=baseline_analysis::fragment_program_utils::analyse_fragment_program(p.get_data());asm volatile(""::"m"(m):"memory");return m.program_ucode_length;},300000/length);
 const double aa=median_ns([&](u32){auto m=fragment_program_utils::analyse_fragment_program(p.get_data());asm volatile(""::"m"(m):"memory");return m.program_ucode_length;},300000/length);
 for(bool props:{false,true}){
 p.texcoord_control_mask=props?0x3ff03ff:0;const double cold_before=cold_lookup<Before>(p),cold_after=cold_lookup<After>(p);
 Before before;After after;Hint hb,ha;before.fragment(p,&hb);after.fragment(p,&ha);
 const double hot_before=median_ns([&](u32){return std::get<0>(before.fragment(p,&hb)).id+1;},100000);
 const double hot_after=median_ns([&](u32){return std::get<0>(after.fragment(p,&ha)).id+1;},100000);
 const double state_before=median_ns([&](u32){hb.invalidate(rsx::fragment_program_state_dirty);return std::get<0>(before.fragment(p,&hb)).id+1;},10000);
 const double state_after=median_ns([&](u32){ha.invalidate(rsx::fragment_program_state_dirty);return std::get<0>(after.fragment(p,&ha)).id+1;},10000);
 if(!first)std::cout<<",";
 first=false;
 std::cout<<"{\"instructions\":"<<length<<",\"nonNeutralProperties\":"<<(props?"true":"false")<<",\"analysisBefore\":"<<ba<<",\"analysisAfter\":"<<aa<<",\"coldLookupBefore\":"<<cold_before<<",\"coldLookupAfter\":"<<cold_after<<",\"hintHitBefore\":"<<hot_before<<",\"hintHitAfter\":"<<hot_after<<",\"stateOnlyBefore\":"<<state_before<<",\"stateOnlyAfter\":"<<state_after<<"}";
 }}std::cout<<"],\"benchmarkCompileBoundaryNoOp\":true";Traits::compile_source=true;
}
int main(int argc,char** argv){
 bool benchmark=false;std::filesystem::path glsl;
 for(int i=1;i<argc;++i){const std::string arg=argv[i];if(arg=="--benchmark")benchmark=true;else if(arg=="--glsl"&&i+1<argc)glsl=argv[++i];else assert(false);}
 const auto results=generator_tests(glsl);const auto counts=variant_trace();hint_tests();
 assert(clone_publication<Before>());assert(!clone_publication<After>());concurrent_preload();
 std::cout<<"{\"equivalentGeneratorVariants\":"<<results.equivalent<<",\"liveVariantsRemainDifferent\":"<<results.live<<",\"fallbackCases\":"<<results.fallback<<",\"parserCases\":"<<results.parsers<<",\"uniqueGlsl\":"<<results.unique<<",\"variantTraceBeforeCompiles\":"<<counts.first<<",\"variantTraceAfterCompiles\":"<<counts.second<<",\"beforeExposedBorrowedKey\":true,\"afterExposedBorrowedKey\":false,\"compileOutsideLock\":true,\"hintLifecycle\":true,\"pendingPreloads\":9,\"concurrentReadyQueries\":8000,\"ownershipRehashClear\":true,\"analysisUnchanged\":true";
 // Append optional timing fields to the same JSON object.
 if(benchmark)benchmarks();
 std::cout<<"}\n";
}


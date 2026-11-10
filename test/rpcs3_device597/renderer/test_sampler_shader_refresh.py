#!/usr/bin/env python3
"""Run complete production load_texture_env methods with deterministic GPU adapters.

The real descriptor type, clip-coordinate producer, and shader uniform copy are
included. Driver objects/texture upload are modeled: this checks CPU selection
and invalidation, not a rendered BO2/AC frame or Metal behavior.
"""
from pathlib import Path
import argparse,hashlib,json,os,platform,shlex,subprocess
from test_vertex_upload_key import block
HERE=Path(__file__).resolve().parent
REL=Path('rpcs3/Emu/RSX/VK/VKDraw.cpp')

PRELUDE=r'''
#include <algorithm>
#include <array>
#include <atomic>
#include <bit>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <memory>
#include <mutex>
#include <vector>
using u8=std::uint8_t;using u16=std::uint16_t;using u32=std::uint32_t;using u64=std::uint64_t;using f32=float;
template<class T> T checked(T x){assert(x);return x;}
#define ensure(x,...) checked(x)
using VkFormat=int;using VkFilter=int;using VkBool32=int;using VkCompareOp=int;
constexpr int VK_FALSE=0,VK_TRUE=1,VK_COMPARE_OP_NEVER=0,VK_FILTER_NEAREST=0,VK_SAMPLER_MIPMAP_MODE_NEAREST=0;
constexpr int VK_BORDER_COLOR_FLOAT_OPAQUE_BLACK=0,VK_SAMPLER_ADDRESS_MODE_REPEAT=0,VK_FORMAT_UNDEFINED=0;
constexpr int VK_FORMAT_FEATURE_SAMPLED_IMAGE_FILTER_LINEAR_BIT=1;
constexpr u32 CELL_GCM_TEXTURE_DEPTH24_D8=100,CELL_GCM_TEXTURE_DEPTH16_FLOAT=103;
constexpr u32 CELL_GCM_TEXTURE_A8R8G8B8=10,CELL_GCM_TEXTURE_D8R8G8B8=11,CELL_GCM_TEXTURE_UN=64;
constexpr u32 CELL_GCM_TEXTURE_LN=128,RSX_SHADER_CONTROL_EMULATE_DEPTH_COMPARE=1;
struct position2i{int x,y;};struct size2i{int width,height;};
struct color4f {
    f32 r=0,g=0,b=0,a=0;
    explicit color4f(f32 v=0):r(v),g(v),b(v),a(v){}
    friend color4f operator+(color4f x,color4f y){x.r+=y.r;x.g+=y.g;x.b+=y.b;x.a+=y.a;return x;}
    friend color4f operator*(color4f x,color4f y){x.r*=y.r;x.g*=y.g;x.b*=y.b;x.a*=y.a;return x;}
};
namespace rsx {
template<class T> using simple_array=std::vector<T>;
using flags32_t=u32;
namespace limits{constexpr u32 fragment_textures_count=16,vertex_textures_count=4;}
enum format_class:u32{RSX_FORMAT_CLASS_UNDEFINED,RSX_FORMAT_CLASS_COLOR,RSX_FORMAT_CLASS_DEPTH};
enum class texture_dimension_extended:u32{texture_dimension_1d,texture_dimension_2d,texture_dimension_cubemap,texture_dimension_3d};
enum class texture_upload_context:u32{shader_read,framebuffer_storage};
enum class deferred_request_command:u32{nop,copy};
enum class texture_minify_filter{nearest};enum class texture_magnify_filter{nearest};
enum class comparison_function{never};
constexpr u32 RSX_HOST_FORMAT_FEATURE_SNORM=1,RSX_HOST_FORMAT_FEATURE_SRGB=2;
namespace texture_control_bits{constexpr u32 SEXT_MASK=1,GAMMA_CTRL_MASK=2;}
constexpr u32 fragment_program_state_dirty=1,vertex_program_state_dirty=2;
__FORMAT_TYPE__;
bool texture_format_ex::hw_SNORM_possible() const{return features&1;}
bool texture_format_ex::hw_SRGB_possible() const{return features&2;}
__DESCRIPTOR_TYPE__;
template<class T> concept Texture=true;
struct texture {
    u32 index=0;bool vertex=false,on=true;
    texture_format_ex format_value{10};
    bool enabled() const{return on;}
    auto format_ex() const{return format_value;}
    u32 format() const{return format_value.format_bits;}
    color4f remapped_border_color(bool)const{return color4f{0.f};}
    u32 border_color(bool)const{return 0;}
    u32 argb_signed()const{return 0;}
    comparison_function zfunc()const{return comparison_function::never;}
    u32 max_aniso()const{return 1;}
    u32 wrap_s()const{return 0;}u32 wrap_t()const{return 0;}u32 wrap_r()const{return 0;}
    u32 get_exact_mipmap_count()const{return 1;}
    texture_minify_filter min_filter()const{return texture_minify_filter::nearest;}
    texture_magnify_filter mag_filter()const{return texture_magnify_filter::nearest;}
    f32 min_lod()const{return 0;}f32 max_lod()const{return 0;}f32 bias()const{return 0;}
};
struct method_regs{std::array<texture,limits::fragment_textures_count> fragment_textures;std::array<texture,limits::vertex_textures_count> vertex_textures;u32 transform_program_start()const{return 19;}} method_registers;
color4f decode_border_color(u32){return color4f{0.f};}
bool is_border_clamped_texture(const texture&){return false;}
format_class classify_format(u32){return RSX_FORMAT_CLASS_COLOR;}
}
using rsx::RSX_FORMAT_CLASS_COLOR;
struct config_t{struct{bool disable_hardware_texel_remapping=false;}video;}g_cfg;
struct flag_set{u32 value=0;void operator|=(u32 x){value|=x;}};
namespace vk {
struct image{int fmt=10;int format()const{return fmt;}};
struct image_view{
    vk::image object;
    int format()const{return object.fmt;}
    vk::image* image(){return &object;}
    image_view* as(int f){object.fmt=f;return this;}
};
struct command_buffer{};
struct depth {void texture_barrier(command_buffer&){}};
struct rtts_t{std::pair<int,depth*>m_bound_depth_stencil{0,nullptr};};
struct descriptor:rsx::sampled_image_descriptor_base{
    image_view* image_handle=nullptr;
    struct deferred {rsx::deferred_request_command op=rsx::deferred_request_command::nop;u32 gcm_format=10;bool do_not_cache=false;f32 exact_mip_count()const{return 1;}}external_subresource_desc;
    bool validate()const{return image_handle||external_subresource_desc.op!=rsx::deferred_request_command::nop;}
    u32 encoded_component_map()const override{return 0;}
};
struct texture_cache {
    using sampled_image_descriptor=descriptor;
    std::array<descriptor,20> replacements;
    bool needs_validation=false,expired=false,toggle_cycle=false;
    u32 uploads=0,expiry_checks=0;
    bool test_if_descriptor_expired(command_buffer&,rtts_t&,descriptor*d,const rsx::texture&){
        ++expiry_checks;if(toggle_cycle)d->is_cyclic_reference=!d->is_cyclic_reference;return expired;
    }
    bool sampler_requires_validation(u32,const descriptor&)const{return needs_validation;}
    u32 prepare_sampler_validation(u32){return 0;}
    void finish_sampler_validation(u32,descriptor&,u32,rtts_t&){}
    descriptor upload_texture(command_buffer&,const rsx::texture&t,rtts_t&){++uploads;return replacements[t.index+(t.vertex?16:0)];}
};
struct minification_filter {int filter=0,mipmap_mode=0;bool sample_mipmaps=false;};
minification_filter get_min_filter(rsx::texture_minify_filter){return {};}
int get_mag_filter(rsx::texture_magnify_filter){return 0;}
f32 max_aniso(u32){return 1;}
int vk_wrap_mode(u32){return 0;}
int get_compare_func(rsx::comparison_function,bool){return 0;}
int get_compatible_snorm_format(int f){return f==20?21:VK_FORMAT_UNDEFINED;}
int get_compatible_srgb_format(int f){return f==30?31:VK_FORMAT_UNDEFINED;}
int get_compatible_sampler_format(int,u32){return 10;}
struct border_color_t {border_color_t(int){};border_color_t(color4f){};border_color_t&operator=(color4f){return *this;}};
struct sampler {template<class...A>bool matches(A&&...)const{return true;}};
struct device {
    struct border_support{bool require_border_color_remap=false;};
    border_support get_custom_border_color_support()const{return {};}
    int get_formats_support()const{return 0;}
    struct props{u32 optimalTilingFeatures=1;};props get_format_properties(int)const{return {};}
};
struct resource_manager {template<class...A>std::unique_ptr<sampler>get_sampler(A&&...){return std::make_unique<sampler>();}} manager;
resource_manager*get_resource_manager(){return &manager;}
struct event{void gpu_wait(command_buffer&,int){}};
struct AsyncTaskScheduler {bool is_recording()const{return false;}bool is_host_mode()const{return true;}event*get_primary_sync_label(){return nullptr;}};
}
struct fxo_t{template<class T>T*try_get(){return nullptr;}} fxo;
fxo_t*g_fxo=&fxo;
__SAMPLER_HELPER__
__CAUSALITY_HELPER__
namespace rsx::texture_cache_helpers {
__CLIP_HELPER__
}
struct VKGSRender {
    vk::device gpu;vk::device*m_device=&gpu;
    vk::command_buffer cmd;vk::command_buffer*m_current_command_buffer=&cmd;
    vk::rtts_t m_rtts;
    std::mutex m_sampler_mutex;
    std::atomic<bool>m_samplers_dirty{false};
    std::array<bool,16>m_textures_dirty{};std::array<bool,4>m_vertex_textures_dirty{};
    std::array<std::unique_ptr<rsx::sampled_image_descriptor_base>,16>fs_sampler_state;
    std::array<std::unique_ptr<rsx::sampled_image_descriptor_base>,4>vs_sampler_state;
    std::array<std::unique_ptr<vk::sampler>,16>fs_sampler_handles;
    std::array<std::unique_ptr<vk::sampler>,4>vs_sampler_handles;
    vk::texture_cache m_texture_cache;
    struct metadata{u32 referenced_textures_mask=0,bx2_texture_reads_mask=0;}current_fp_metadata,current_vp_metadata;
    struct{u32 ctrl=0,offset=0x20000;}current_fragment_program;
    u64 int_flip_index=23;
    struct{u32 draw_calls=17;}m_frame_stats;
    flag_set m_graphics_state;
    struct{bool supports_asynchronous_compute=false;}backend_config;
    int m_async_compute_dependency_info=0;
    u32 renderpass_changes=0;
    void invalidate_render_pass(){++renderpass_changes;}
    void load_texture_env();
};
__LOAD_METHOD__
vk::image_view images[2];
vk::descriptor initial() {
    vk::descriptor d;d.image_handle=&images[0];d.format_class=rsx::RSX_FORMAT_CLASS_COLOR;
    d.image_type=rsx::texture_dimension_extended::texture_dimension_2d;
    d.format_ex=rsx::texture_format_ex{10};
    for(u32 i=0;i<3;++i){d.texcoord_xform.scale[i]=1;d.texcoord_xform.bias[i]=0;}
    d.texcoord_xform.clamp=false;return d;
}
// Model the shader-visible state using the real production uniform-copy body.
struct shader_uniforms {float scale[3],bias[3],clamp_min[2],clamp_max[2];};
std::vector<u32> shader_state(const vk::descriptor& d,bool vertex) {
    if(!d.validate())return {0};
    std::vector<u32> out{1,u32(d.format_class),u32(d.image_type),d.samples};
    if(vertex)return out;
    struct{std::array<shader_uniforms,1>texture_params;} current_fragment_program{};
    const vk::descriptor*sampler_descriptors[]={&d};const u32 i=0;
__UNIFORM_COPY__
    out.push_back(d.format_class!=rsx::RSX_FORMAT_CLASS_COLOR&&d.is_cyclic_reference);
    out.push_back(d.format_ex.features);out.push_back(d.format_ex.features?d.format_ex.texel_remap_control:0);
    for(float v:current_fragment_program.texture_params[0].scale)out.push_back(std::bit_cast<u32>(v));
    for(float v:current_fragment_program.texture_params[0].bias)out.push_back(std::bit_cast<u32>(v));
    out.push_back(d.texcoord_xform.clamp);
    if(d.texcoord_xform.clamp){
        std::memcpy(current_fragment_program.texture_params[0].clamp_min,d.texcoord_xform.clamp_min,4*sizeof(float));
        for(float v:current_fragment_program.texture_params[0].clamp_min)out.push_back(std::bit_cast<u32>(v));
        for(float v:current_fragment_program.texture_params[0].clamp_max)out.push_back(std::bit_cast<u32>(v));
    }
    return out;
}
'''

MAIN=r'''
int main(){
    u64 cases=0,mismatches=0,clean_invalidations=0,fast_uploads=0;
    auto check=[&](vk::descriptor before,vk::descriptor after,bool vertex,u32 mode,bool guest_dirty=false,bool hardware_convert=false){
        namespace cause=rpcs3::ios::renderer_causality;
        cause::profile.reset(101);
        VKGSRender r;u32 flag=vertex?rsx::vertex_program_state_dirty:rsx::fragment_program_state_dirty;
        for(u32 i=0;i<16;++i){rsx::method_registers.fragment_textures[i]={};rsx::method_registers.fragment_textures[i].index=i;}
        for(u32 i=0;i<4;++i){rsx::method_registers.vertex_textures[i]={};rsx::method_registers.vertex_textures[i].index=i;rsx::method_registers.vertex_textures[i].vertex=true;}
        auto& tex=vertex?rsx::method_registers.vertex_textures[0]:rsx::method_registers.fragment_textures[0];
        tex.format_value=after.format_ex;
        if(hardware_convert){tex.format_value.features=1;tex.format_value.texel_remap_control=1;after.format_ex={};}
        if(vertex){r.current_vp_metadata.referenced_textures_mask=1;r.vs_sampler_state[0]=std::make_unique<vk::descriptor>(before);r.vs_sampler_handles[0]=std::make_unique<vk::sampler>();r.m_vertex_textures_dirty[0]=guest_dirty;}
        else{r.current_fp_metadata.referenced_textures_mask=1;r.fs_sampler_state[0]=std::make_unique<vk::descriptor>(before);r.fs_sampler_handles[0]=std::make_unique<vk::sampler>();r.m_textures_dirty[0]=guest_dirty;}
        r.m_texture_cache.replacements[vertex?16:0]=after;
        r.m_samplers_dirty=(mode==0);
        r.m_texture_cache.needs_validation=(mode==1);
        r.m_texture_cache.expired=(mode==2);
        r.m_texture_cache.toggle_cycle=(mode==3);
        if(guest_dirty)r.m_graphics_state.value=flag;
        const auto previous=shader_state(before,vertex);
        r.load_texture_env();
        auto*current=static_cast<vk::descriptor*>(vertex?r.vs_sampler_state[0].get():r.fs_sampler_state[0].get());
        const auto expected=shader_state(*current,vertex);
        const auto actual=(r.m_graphics_state.value&flag)?expected:previous;
        ++cases;mismatches+=(actual!=expected);
        if(previous==expected&&!guest_dirty)clean_invalidations+=bool(r.m_graphics_state.value&flag);
        if(mode==4)fast_uploads+=r.m_texture_cache.uploads;
        const auto observation=cause::profile.take();
        assert(observation.captured&&observation.session==101&&observation.dropped==0);
#ifdef CANDIDATE
        const bool should_record=previous!=expected&&!guest_dirty;
        assert((observation.size!=0)==should_record);
        if(should_record){
            assert(observation.size==1);
            const auto& event=observation.events[0];
            assert(event.session==101&&event.frame==23&&event.draw==17);
            assert(event.fragment_offset==0x20000&&event.vertex_start==19);
            assert(event.vertex==vertex&&event.slot==0&&event.reasons!=0);
            assert(event.kind==(mode==3?cause::Kind::sampler_cyclic_fast:cause::Kind::sampler_refresh));
        }
#else
        assert(observation.size==0);
#endif
    };
    for(u32 mode=0;mode<3;++mode)for(u32 which=0;which<24;++which)for(bool dirty:{false,true}){
        auto a=initial(),b=a;
        if(which<3)b.texcoord_xform.scale[which]*=0.5f;
        else if(which<6)b.texcoord_xform.bias[which-3]=0.25f;
        else if(which<10){
            rsx::texture_cache_helpers::calculate_sample_clip_parameters(a,{0,0},{64,64},{128,128});b=a;
            if(which<8)b.texcoord_xform.clamp_min[which-6]+=0.1f;
            else b.texcoord_xform.clamp_max[which-8]-=0.1f;
        }
        else if(which==10)rsx::texture_cache_helpers::calculate_sample_clip_parameters(b,{16,32},{32,32},{128,128});
        else if(which==11){rsx::texture_cache_helpers::calculate_sample_clip_parameters(a,{0,0},{64,64},{128,128});b=a;b.texcoord_xform.clamp=false;}
        else if(which==12)b.image_type=rsx::texture_dimension_extended::texture_dimension_3d;
        else if(which==13)b.samples=4;
        else if(which==14){a.format_class=b.format_class=rsx::RSX_FORMAT_CLASS_DEPTH;b.is_cyclic_reference=true;}
        else if(which==15)b.format_class=rsx::RSX_FORMAT_CLASS_DEPTH;
        else if(which==16)b.format_ex.features=2;
        else if(which==17){a.format_ex.features=b.format_ex.features=1;b.format_ex.texel_remap_control=1;}
        else if(which==18){b.image_handle=nullptr;b.format_class=rsx::RSX_FORMAT_CLASS_UNDEFINED;}
        else if(which==19){a.image_handle=nullptr;a.format_class=rsx::RSX_FORMAT_CLASS_UNDEFINED;}
        else if(which==20)b.image_handle=&images[1];
        else if(which==21){b.texcoord_xform.clamp_min[0]=123; b.texcoord_xform.clamp_max[1]=-456;}
        else if(which==22)b.is_cyclic_reference=true; // Color shaders do not consume this flag.
        else b.format_ex.texel_remap_control=1; // Ignored without format features.
        check(a,b,false,mode,dirty);
        check(a,b,true,mode,dirty);
    }
    // A real clipping producer changes the sampler coefficients, then an
    // otherwise identical shader must receive that second descriptor's values.
    for(int x=0;x<64;x+=7)for(int y=0;y<64;y+=9)for(int w:{16,32,48}){
        auto a=initial(),b=a;
        rsx::texture_cache_helpers::calculate_sample_clip_parameters(a,{0,0},{64,64},{128,128});
        rsx::texture_cache_helpers::calculate_sample_clip_parameters(b,{x,y},{w,32},{128,128});
        check(a,b,false,0);
    }
    for(bool cycle:{false,true}){
        auto a=initial();a.is_cyclic_reference=cycle;a.format_class=rsx::RSX_FORMAT_CLASS_DEPTH;
        check(a,a,false,3);check(a,a,true,3);
        a.format_class=rsx::RSX_FORMAT_CLASS_COLOR;
        check(a,a,false,3);check(a,a,true,3);
    }
    for(u32 i=0;i<1000;++i){auto a=initial();check(a,a,false,4);check(a,a,true,4);}
    // Hardware SNORM view availability changes the remaining shader conversion.
    auto a=initial();a.format_ex.features=1;a.format_ex.texel_remap_control=1;
    images[1].object.fmt=20;auto b=a;b.image_handle=&images[1];check(a,b,false,0,false,true);
    assert(clean_invalidations==0);assert(fast_uploads==0);
#ifdef CANDIDATE
    assert(mismatches==0);
#else
    assert(mismatches>0);
#endif
    std::cout<<"{\"cases\":"<<cases<<",\"stale_shader_states\":"<<mismatches
      <<",\"unchanged_state_invalidations\":"<<clean_invalidations<<",\"unchanged_fast_path_uploads\":"<<fast_uploads<<"}"<<std::endl;
}
'''

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--source',type=Path,required=True);ap.add_argument('--baseline',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--sanitizer',action='store_true');ap.add_argument('--compiler',default=os.environ.get('CXX','g++'),help='C++ command; defaults to CXX');args=ap.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    source=args.source.resolve();types=(HERE/'fixtures/TextureUtils.h').read_text();helpers=(source/'rpcs3/Emu/RSX/Common/texture_cache_helpers.h').read_text();thread=(source/'rpcs3/Emu/RSX/RSXThread.cpp').read_text()
    clip='template <typename sampled_image_descriptor>\n'+block(helpers,'void calculate_sample_clip_parameters')
    uniform_start=thread.index('std::memcpy(',thread.index('void thread::get_current_fragment_program'))
    uniform_end=thread.index(';',uniform_start)+1
    uniform=thread[uniform_start:uniform_end]
    fmt=block(types,'struct texture_format_ex');desc=block(types,'class sampled_image_descriptor_base')
    helper_path=source/'rpcs3/Emu/RSX/VK/vkutils/sampler_shader_state.hpp';helper=helper_path.read_text().replace('#pragma once','').replace('#include "../../Common/TextureUtils.h"','')
    causality_path=source/'rpcs3/ios/IOSRendererCausality.h';causality=causality_path.read_text().replace('#pragma once','')
    report={'scope':'complete production load_texture_env + real descriptor/clip/uniform copy and bounded diagnostic producer; modeled Vulkan and texture lookup, no GPU','sanitizer':args.sanitizer,'inputs':{},'variants':{}}
    for rel in [REL,Path('rpcs3/Emu/RSX/VK/vkutils/sampler_shader_state.hpp'),Path('rpcs3/ios/IOSRendererCausality.h'),Path('rpcs3/Emu/RSX/Common/texture_cache_helpers.h'),Path('rpcs3/Emu/RSX/RSXThread.cpp')]:report['inputs'][str(rel)]=hashlib.sha256((source/rel).read_bytes()).hexdigest()
    report['support_TextureUtils_sha256']=hashlib.sha256((HERE/'fixtures/TextureUtils.h').read_bytes()).hexdigest()
    for name,base in [('before',args.baseline),('after',source)]:
        method=block((base/REL).read_text(),'void VKGSRender::load_texture_env()')
        cpp=PRELUDE.replace('__FORMAT_TYPE__',fmt).replace('__DESCRIPTOR_TYPE__',desc).replace('__SAMPLER_HELPER__',helper).replace('__CAUSALITY_HELPER__',causality).replace('__CLIP_HELPER__',clip).replace('__UNIFORM_COPY__',uniform).replace('__LOAD_METHOD__',method)+MAIN
        path=args.output/(name+'.cpp');path.write_text(cpp);binary=args.output/name
        cmd=shlex.split(args.compiler)+['-std=c++20','-O2','-g','-UNDEBUG','-Wall','-Wextra','-Werror','-DRPCS3_IOS',str(path),'-o',str(binary)]
        if platform.system()=='Darwin' and os.environ.get('HOST_MACOS_SDK'):
            cmd+=['-isysroot',os.environ['HOST_MACOS_SDK']]
        if name=='after':cmd+=['-DCANDIDATE']
        if args.sanitizer:
            cmd+=['-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-sanitize-recover=all']
            if platform.system()=='Linux':cmd+=['-no-pie']
        build=subprocess.run(cmd,text=True,capture_output=True);(args.output/(name+'-build.log')).write_text(build.stdout+build.stderr);build.check_returncode()
        run=subprocess.run([str(binary)],text=True,capture_output=True,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0'),timeout=45);(args.output/(name+'-run.log')).write_text(run.stdout+run.stderr);run.check_returncode()
        report['variants'][name]={'result':json.loads(run.stdout),'generated_sha256':hashlib.sha256(cpp.encode()).hexdigest(),'command':cmd,'returncode':run.returncode}
    (args.output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report['variants'],indent=2))
if __name__=='__main__':main()

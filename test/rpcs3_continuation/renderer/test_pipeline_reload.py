#!/usr/bin/env python3
"""Compile the exact production load_program body against a deterministic driver shim.

The shim supplies shader resolution/cache objects, not Vulkan or an iPhone GPU.
The production entry point, branches, flag consumption and binding-table writes
are extracted unchanged. A fresh pipeline lookup supplies the independent oracle.
"""
from pathlib import Path
import argparse, hashlib, json, subprocess

HERE = Path(__file__).resolve().parent
REL = Path('rpcs3/Emu/RSX/VK/VKGSRender.cpp')

PRELUDE = r'''
#include <cassert>
#include <cstdint>
#include <iostream>
#include <map>
#include <tuple>
#include <utility>
#include <vector>
using u8 = std::uint8_t;
using u32 = std::uint32_t;
using u64 = std::uint64_t;
#define ensure(x) assert(x)
// Numeric production flag values are supplied from RSXDriverState.h.
__PRODUCTION_FLAGS__
struct flag_set {
    u32 value=0;
    u32 load() const { return value; }
    u32 operator&(u32 mask) const { return value & mask; }
    void clear(u32 mask) { value &= ~mask; }
    void operator|=(u32 mask) { value |= mask; }
};
enum class shader_mode { recompiler, async_recompiler, async_with_interpreter, interpreter_only };
constexpr u32 RSX_SHADER_CONTROL_PROGRAMMABLE_BLENDING = 0x100;
struct shader_input { u32 id=1, ctrl=0; bool valid=true; };
struct shader_metadata { u32 id=1; };
struct shader_object { u32 id=1; };
struct binding_table {};
binding_table table;
struct hint { bool has_vertex_program() const { return true; } bool has_fragment_program() const { return true; } };
struct device { bool get_depth_bounds_support() const { return true; } };
device gpu;
struct config_t { struct { bool debug_overlay=false; } video; struct { bool show_shader_compilation_hint=false; } misc; } g_cfg;
namespace rsx { class thread { public: void begin() {} }; enum class framebuffer_creation_context { context_draw }; }
namespace rsx::overlays { inline void show_shader_compile_notification() {} }
namespace rpcs3::ios { inline void record_rsx_shader_cache_lookup(bool) {} }
namespace vk {
struct vertex_input_assembly_state { u32 primitive=3; bool restart_index_enabled=false; } desired_ia;
struct pipeline_props {
    struct state_t {
        struct ia_t { u32 topology=3; bool primitiveRestartEnable=false; bool operator==(const ia_t&) const=default; } ia;
        u32 other=0;
        void set_primitive_type(u32 x) { ia.topology=x; }
        void enable_primitive_restart(bool x) { ia.primitiveRestartEnable=x; }
        bool operator==(const state_t&) const=default;
    } state;
    u64 renderpass_key=0;
    bool operator==(const pipeline_props&) const=default;
} desired_props;
u32 decodes=0, enters=0;
vertex_input_assembly_state decode_vertex_input_assembly_state() { return desired_ia; }
pipeline_props decode_rsx_state(void*, vertex_input_assembly_state ia, int, int, u8, u8, bool, bool) {
    ++decodes; auto result=desired_props; result.state.ia={ia.primitive,ia.restart_index_enabled}; return result;
}
bool renderpass_has_input_attachments(u64 key) { return (key & 1) != 0; }
void enter_uninterruptible() { ++enters; }
void leave_uninterruptible() { assert(enters); --enters; }
namespace glsl { struct program { u32 vp=0, fp=0; pipeline_props props; bool interpreter=false; }; }
using key_t=std::tuple<u32,u32,u32,bool,u32,u64,bool>;
std::map<key_t,glsl::program> programs;
glsl::program* resolve(u32 vp,u32 fp,pipeline_props p,bool interpreter) {
    key_t key{vp,fp,p.state.ia.topology,p.state.ia.primitiveRestartEnable,p.state.other,p.renderpass_key,interpreter};
    return &programs.try_emplace(key,glsl::program{vp,fp,p,interpreter}).first->second;
}
}
struct cache_t {
    u32 queries=0; bool ready=true; shader_object vp,fp;
    auto get_graphics_pipeline(hint*,const shader_input& v,const shader_input& f,const vk::pipeline_props& props,bool async,bool) {
        ++queries; vp.id=v.id; fp.id=f.id;
        vk::glsl::program* p=(!ready && async)?nullptr:vk::resolve(v.id,f.id,props,false);
        return std::tuple{p,static_cast<const shader_object*>(&vp),static_cast<const shader_object*>(&fp)};
    }
    bool check_cache_missed() const { return false; }
};
struct interpreter_t {
    bool is_interpreter(vk::glsl::program* p) const { return p && p->interpreter; }
    vk::glsl::program* get(const vk::pipeline_props& p,shader_metadata f,shader_metadata v,u32,u32) {
        return vk::resolve(v.id,f.id,p,true);
    }
};
class VKGSRender : public rsx::thread {
public:
    shader_mode m_shader_mode=shader_mode::recompiler;
    flag_set m_graphics_state;
    shader_input current_fragment_program,current_vertex_program;
    shader_metadata current_fp_metadata,current_vp_metadata;
    shader_input pending_fp,pending_vp;
    int fs_sampler_state=0,vs_sampler_state=0;
    vk::pipeline_props m_pipeline_properties;
    vk::glsl::program* m_program=nullptr;
    vk::glsl::program* m_prev_program=nullptr;
    const shader_object* m_vertex_prog=nullptr;
    const shader_object* m_fragment_prog=nullptr;
    interpreter_t m_shader_interpreter;
    u64 m_current_renderpass_key=0;
    void* m_ctx=nullptr;
    struct { std::pair<int,int> m_bound_depth_stencil; } m_rtts;
    int backend_config=0;
    std::vector<int> m_draw_buffers{1};
    device* m_device=&gpu;
    cache_t cache;
    cache_t* m_prog_buffer=&cache;
    hint m_program_cache_hint;
    struct { u32 program_cache_lookups_total=0,program_cache_lookups_ellided=0; } m_frame_stats;
    void* m_overlay_manager=nullptr;
    u32 m_interpreter_state=0;
    const binding_table* m_vs_binding_table=nullptr;
    const binding_table* m_fs_binding_table=nullptr;
    u32 fp_resolves=0,vp_resolves=0;
    bool skip_current_frame=false,swapchain_unavailable=false;
    struct { bool disable_rendering() const { return false; } } cond_render_ctrl;
    void init_buffers(rsx::framebuffer_creation_context) {}
    void begin();
    struct sampled_image { u32 format_class; bool format_ex=false; };
    void late_texture_format_change(bool is_sampler_dirty,u32 previous_format_class,sampled_image* sampler_state) {
        // Execute the exact load_texture_env conditional with its continue target.
        do {
__LATE_TEXTURE_INVALIDATION__
        } while (false);
    }
    void get_current_fragment_program(int) {
        ++fp_resolves;
        if (m_graphics_state & rsx::fragment_program_dirty) {
            current_fragment_program=pending_fp; current_fp_metadata.id=pending_fp.id;
            m_graphics_state.clear(rsx::fragment_program_dirty);
        }
    }
    void get_current_vertex_program(int) {
        ++vp_resolves;
        if (m_graphics_state & (rsx::vertex_program_dirty|rsx::xform_instancing_state_dirty)) {
            current_vertex_program=pending_vp; current_vp_metadata.id=pending_vp.id;
        }
    }
    void invalidate_render_pass() {
        m_current_renderpass_key=!!(current_fragment_program.ctrl & RSX_SHADER_CONTROL_PROGRAMMABLE_BLENDING);
        m_graphics_state |= rsx::pipeline_config_dirty;
    }
    auto get_binding_table() const { return std::pair{&table,&table}; }
    bool load_program();
};
'''

MAIN = r'''
int main() {
    u64 cases=0,mismatches=0,old_native_kept=0,warm_lookups=0,clean_case_lookups=0;
    for (u32 shader_mask=0;shader_mask<8;shader_mask++)
    for (u32 pipe_dirty=0;pipe_dirty<2;pipe_dirty++)
    for (u32 fixed_change=0;fixed_change<2;fixed_change++)
    for (u32 ia_change=0;ia_change<2;ia_change++)
    for (u32 restart_change=0;restart_change<2;restart_change++)
    for (u32 mode=0;mode<4;mode++)
    for (u32 old_kind=0;old_kind<3;old_kind++)
    for (u32 ready=0;ready<2;ready++)
    for (u32 debug=0;debug<2;debug++) {
        // Changes to fixed properties are legal only when their dirty bit is set.
        if (fixed_change && !pipe_dirty) continue;
        VKGSRender r;
        r.cache.ready=ready;
        r.m_shader_mode=static_cast<shader_mode>(mode);
        g_cfg.video.debug_overlay=debug;
        const u32 flags=((shader_mask&1)?rsx::fragment_program_state_dirty:0u)
            |((shader_mask&2)?rsx::vertex_program_state_dirty:0u)
            |((shader_mask&4)?rsx::xform_instancing_state_dirty:0u)
            |(pipe_dirty?rsx::pipeline_config_dirty:0u);
        r.m_graphics_state.value=flags;
        r.pending_fp.id=(shader_mask&1)?2:1;
        r.pending_vp.id=(shader_mask&6)?3:1;
        vk::desired_ia={3+ia_change,bool(restart_change)};
        vk::desired_props={}; vk::desired_props.state.other=fixed_change;
        if (old_kind) {
            r.m_program=vk::resolve(1,1,r.m_pipeline_properties,old_kind==2);
            r.m_prev_program=r.m_program;
        }
        const bool got=r.load_program();
        assert(vk::enters==0);
        assert((r.m_graphics_state.value & (rsx::invalidate_pipeline_bits|rsx::pipeline_config_dirty))==0);
        vk::pipeline_props expected_props=vk::desired_props;
        expected_props.state.ia={vk::desired_ia.primitive,vk::desired_ia.restart_index_enabled};
        // A clean cached native program remains valid even if an async compiler is unavailable.
        const bool clean_native=old_kind==1 && !shader_mask && !fixed_change && !ia_change && !restart_change;
        bool expected_native=(mode!=3 && (ready || mode==0)) || clean_native;
        bool expected_interpreter=!expected_native && (mode==2 || mode==3);
        if (old_kind==2 && !shader_mask && !pipe_dirty && !ia_change && !restart_change && mode==3)
            expected_interpreter=true;
        const bool expected_present=expected_native || expected_interpreter;
        bool match=got==expected_present;
        if (got && expected_present) {
            match &= r.m_program->vp==r.pending_vp.id && r.m_program->fp==r.pending_fp.id;
            match &= r.m_program->props==expected_props;
            match &= r.m_program->interpreter==expected_interpreter;
        }
        if (!match) {
            ++mismatches;
            if (r.m_program && r.m_program->vp==1 && r.m_program->fp==1 && shader_mask) ++old_native_kept;
            if (mismatches<3) std::cerr << "mismatch flags=" << flags << " mode=" << mode << " old=" << old_kind << " ready=" << ready << '\n';
        }
        if (clean_native) clean_case_lookups+=r.cache.queries;
        // A resolved, compiled pipeline and cleared flags need no additional lookup on a warm call.
        if (match && r.m_program && !r.m_program->interpreter && mode!=3) {
            const u32 before=r.cache.queries;
            assert(r.load_program());
            warm_lookups+=r.cache.queries-before;
        }
        ++cases;
    }
    // Exhaustive FP/VP identity sequence with alternating redundant fixed-state writes.
    VKGSRender seq; vk::desired_props={}; vk::desired_ia={}; g_cfg.video.debug_overlay=false;
    seq.m_graphics_state.value=rsx::pipeline_config_dirty;
    assert(seq.load_program());
    u64 sequence_mismatches=0;
    for (u32 i=0;i<20000;i++) {
        seq.pending_fp.id=2+(i%29); seq.pending_vp.id=50+(i%17);
        seq.m_graphics_state.value=rsx::fragment_program_state_dirty|rsx::vertex_program_state_dirty
            |((i%3)?rsx::pipeline_config_dirty:0u);
        assert(seq.load_program());
        if (seq.m_program->vp!=seq.pending_vp.id || seq.m_program->fp!=seq.pending_fp.id) ++sequence_mismatches;
    }
    // Real begin() is not sufficient: upload_texture may reveal a new host
    // format class later in end(), after begin's program-pointer invalidation.
    VKGSRender late; vk::desired_props={}; vk::desired_ia={};
    late.m_program=vk::resolve(1,1,late.m_pipeline_properties,false);
    auto old_program=late.m_program;
    late.m_graphics_state.value=rsx::pipeline_config_dirty;
    late.begin();
    assert(late.m_program==old_program);
    VKGSRender::sampled_image sampler{2,true};
    late.late_texture_format_change(false,1,&sampler);
    assert(late.m_graphics_state.value & rsx::fragment_program_state_dirty);
    late.pending_fp.id=2;
    assert(late.load_program());
    const bool late_texture_mismatch=late.m_program->fp!=2;
    std::cout << "{\"cases\":"<<cases<<",\"mismatches\":"<<mismatches
        <<",\"stale_native_cases\":"<<old_native_kept<<",\"sequence_draws\":20000,\"sequence_mismatches\":"<<sequence_mismatches
        <<",\"warm_extra_lookups\":"<<warm_lookups<<",\"clean_native_lookups\":"<<clean_case_lookups
        <<",\"late_texture_mismatch\":"<<late_texture_mismatch<<"}\n";
}
'''

def extract(text: str) -> str:
    start=text.index('bool VKGSRender::load_program()\n{')
    end=text.index('\nvoid VKGSRender::load_program_env()',start)
    return text[start:end]

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--core',type=Path,required=True);ap.add_argument('--draw-core',type=Path);ap.add_argument('--flags-header',type=Path,default=HERE/'fixtures/RSXDriverState.h');ap.add_argument('--output-dir',type=Path,default=HERE/'evidence');ap.add_argument('--label',required=True);ap.add_argument('--sanitize',action='store_true');ap.add_argument('--expect-failures',action='store_true');ap.add_argument('--generate-only',action='store_true');args=ap.parse_args()
    source=(args.core/REL).read_bytes(); body=extract(source.decode()); flags=args.flags_header.read_text().replace('#pragma once','').replace('#include <util/types.hpp>','')
    draw_path=(args.draw_core or args.core)/'rpcs3/Emu/RSX/VK/VKDraw.cpp';draw=draw_path.read_text()
    begin_start=draw.index('void VKGSRender::begin()\n{');begin_end=draw.index('\nvoid VKGSRender::end()',begin_start)
    begin=draw[begin_start:begin_end]
    late_start=draw.index('\t\tif (!is_sampler_dirty)\n',draw.index('void VKGSRender::load_texture_env()'))
    late_end=draw.index('\n\t\tsampler_state->format_ex = tex.format_ex();',late_start)
    late=draw[late_start:late_end]
    program=PRELUDE.replace('__PRODUCTION_FLAGS__',flags).replace('__LATE_TEXTURE_INVALIDATION__',late)+begin+body+MAIN
    work=args.output_dir;work.mkdir(parents=True,exist_ok=True);cpp=work/(args.label+'.cpp');cpp.write_text(program)
    fingerprints=dict(source_sha256=hashlib.sha256(source).hexdigest(),function_sha256=hashlib.sha256(body.encode()).hexdigest(),draw_source_sha256=hashlib.sha256(draw_path.read_bytes()).hexdigest(),begin_sha256=hashlib.sha256(begin.encode()).hexdigest(),late_texture_block_sha256=hashlib.sha256(late.encode()).hexdigest(),harness_sha256=hashlib.sha256(program.encode()).hexdigest())
    if args.generate_only:
        generated=dict(fingerprints,mode='generate-only',native_compilation=False,native_execution=False)
        (work/(args.label+'.generated.json')).write_text(json.dumps(generated,indent=2)+'\n');print(json.dumps(generated));return
    exe=work/(args.label+'.exe');cmd=['g++','-std=c++20','-DRPCS3_IOS','-Wall','-Wextra','-Werror','-O2',str(cpp),'-o',str(exe)]
    if args.sanitize:cmd[1:1]=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    compiled=subprocess.run(cmd,capture_output=True,text=True);(work/(args.label+'-compile.txt')).write_text(compiled.stdout+compiled.stderr)
    if compiled.returncode:raise SystemExit(compiled.stderr)
    import os
    env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0')
    run=subprocess.run([str(exe)],capture_output=True,text=True,env=env)
    (work/(args.label+'-output.txt')).write_text(run.stdout+run.stderr)
    if run.returncode:raise SystemExit(run.stderr or str(run.returncode))
    result=json.loads(run.stdout)
    assert bool(result['mismatches'])==args.expect_failures,result
    assert bool(result['sequence_mismatches'])==args.expect_failures,result
    assert bool(result['late_texture_mismatch'])==args.expect_failures,result
    assert result['warm_extra_lookups']==0 and result['clean_native_lookups']==0,result
    result.update(fingerprints,command=cmd,sanitized=args.sanitize,scope='Full production load_program and begin, late texture-class invalidation block; deterministic shader/cache/upload stubs; no Vulkan execution')
    (work/(args.label+'.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()

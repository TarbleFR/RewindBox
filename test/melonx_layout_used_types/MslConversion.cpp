// RewindBox (adapt_layout_used_types gate): the fragment conversion of a vertex+fragment pipeline as MoltenVK v1.4.2
// (db660224) does it on an Apple GPU with Metal 3 argument buffers (tier 2, MSL 3.2, iOS): the resource bindings of
// MVKPipelineLayout::populateShaderConversionConfig from the pipeline's descriptor set layouts (pickGPULayout, one
// argument buffer per set, the buffer-size slot), the options of initShaderConversionConfig and
// addFragmentShaderToPipeline, the fragment inputs from the vertex outputs (addPrevStageOutputToShaderConversionConfig),
// then SPIRV-Cross's CompilerMSL::compile, the call that reports "nullptr". Built against MoltenVK's
// SPIRVReflection.h and the SPIRV-Cross revision MoltenVK pins. No Metal device: Metal compilation is not run.
// Usage: MslConversion vertex.spv fragment.spv layout.txt [nativeAtomics=1] [pushSet0=0] [mslVersion=30200] [out.metal]
// layout.txt: "set binding vkDescriptorType count vkShaderStageFlags" per descriptor (the gate fixture's output).
#include "SPIRVReflection.h"
#include <spirv_msl.hpp>
#include <algorithm>
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
using namespace SPIRV_CROSS_NAMESPACE; using namespace std;
static vector<uint32_t> load(const char* p){ifstream f(p,ios::binary);vector<char> b((istreambuf_iterator<char>(f)),{});vector<uint32_t> w(b.size()/4);memcpy(w.data(),b.data(),w.size()*4);return w;}
struct Bind{uint32_t set,binding,type,count,stages;};
enum GPU{None,Texture,Sampler,BufferAux,TexBufSoA,TexSampSoA};
int main(int argc,char**argv){
  auto vs=load(argv[1]), fs=load(argv[2]);
  bool nativeAtomic=argc>4?atoi(argv[4]):1, push0=argc>5?atoi(argv[5]):0; uint32_t mslv=argc>6?atoi(argv[6]):30200;
  vector<Bind> L; {ifstream f(argv[3]); Bind b; while(f>>b.set>>b.binding>>b.type>>b.count>>b.stages) L.push_back(b);}
  uint32_t maxSet=0; for(auto&b:L) maxSet=max(maxSet,b.set);
  vector<mvk::SPIRVShaderOutput> outs; string err;
  if(!mvk::getShaderOutputs(vs,spv::ExecutionModelVertex,"main",outs,err)){cout<<"REFLECTFAIL "<<err<<"\n";return 2;}
  try{
    CompilerMSL m(fs);
    m.set_entry_point("main", spv::ExecutionModelFragment);
    CompilerMSL::Options o;
    o.msl_version=mslv; o.texel_buffer_texture_width=16384; o.r32ui_linear_texture_alignment=16; o.swizzle_texture_samples=false; o.texture_buffer_native=true;
    o.argument_buffers=true; o.force_active_argument_buffer_resources=false; o.pad_argument_buffer_resources=true;
    o.argument_buffers_tier=CompilerMSL::Options::ArgumentBuffersTier::Tier2; o.agx_manual_cube_grad_fixup=true; o.platform=CompilerMSL::Options::iOS;
    o.enable_frag_output_mask=1; o.ios_support_base_vertex_instance=true; o.texture_1D_as_2D=true; o.enable_point_size_builtin=false; o.enable_point_size_default=false; o.default_point_size=1.0f;
    o.enable_frag_depth_builtin=true; o.enable_frag_stencil_ref_builtin=true; o.multiview=false; o.multiview_layered_rendering=true; o.view_index_from_device_index=false;
    o.replace_recursive_inputs=true; o.emulate_subgroups=false; o.ios_use_simdgroup_functions=true;
    // Leftovers of the vertex stage on the shared configuration, then the fragment stage's own.
    o.shader_output_buffer_index=24; o.draw_id_buffer_index=25; o.disable_rasterization=false;
    o.swizzle_buffer_index=28; o.buffer_size_buffer_index=27; o.dynamic_offsets_buffer_index=29; o.view_mask_buffer_index=26;
    o.capture_output_to_buffer=false; o.fixed_subgroup_size=32; o.check_discarded_frag_stores=true; o.force_fragment_with_side_effects_execution=false;
    o.input_attachment_is_ds_attachment=false; o.sample_dref_lod_array_as_grad=false; /* no depth-compare sampling here */ o.force_sample_rate_shading=false;
    for(auto&so:outs) if(so.builtin==spv::BuiltInLayer) o.arrayed_subpass_input=true;
    m.set_msl_options(o);
    for(auto&so:outs){ if(!so.isUsed)continue; MSLShaderInterfaceVariable v; v.location=so.location; v.component=so.component; v.builtin=so.builtin; v.vecsize=so.vecWidth;
      auto bt=so.baseType; v.format=(bt==SPIRType::Float||bt==SPIRType::Int||bt==SPIRType::UInt)?MSL_SHADER_VARIABLE_FORMAT_ANY32:
        (bt==SPIRType::Half||bt==SPIRType::Short)?MSL_SHADER_VARIABLE_FORMAT_ANY16:(bt==SPIRType::UShort?MSL_SHADER_VARIABLE_FORMAT_UINT16:(bt==SPIRType::UByte?MSL_SHADER_VARIABLE_FORMAT_UINT8:MSL_SHADER_VARIABLE_FORMAT_OTHER));
      m.add_msl_shader_input(v);}
    int added=0; uint32_t dBuf=0,dTex=0,dSmp=0;
    for(uint32_t s=0;s<=maxSet;s++){
      vector<Bind> B; for(auto&b:L) if(b.set==s) B.push_back(b);
      sort(B.begin(),B.end(),[](const Bind&a,const Bind&b){return a.binding!=b.binding?a.binding<b.binding:a.stages<b.stages;});
      bool argbuf=!(push0&&s==0) && !B.empty();
      auto gpu=[&](uint32_t t)->GPU{switch(t){case 1:return TexSampSoA; case 0:return Sampler; case 2:case 4:return Texture; case 3:case 5:return nativeAtomic?Texture:TexBufSoA; case 6:case 7:return BufferAux; default:return None;}};
      uint32_t idx=0;
      if(argbuf){ bool size=false; for(auto&b:B) if(gpu(b.type)==BufferAux) size=true;
        if(size){ idx=1; MSLResourceBinding rb; rb.stage=spv::ExecutionModelFragment; rb.desc_set=s; rb.binding=kBufferSizeBufferBinding; rb.count=1; rb.basetype=SPIRType::Void; m.add_msl_resource_binding(rb); added++; } }
      else m.add_discrete_descriptor_set(s);
      for(auto&b:B){ GPU g=gpu(b.type); uint32_t tex=0,buf=0,smp=0;
        if(argbuf){ switch(g){case TexSampSoA:tex=1;smp=1;break; case Texture:tex=1;break; case Sampler:smp=1;break; case BufferAux:buf=1;break; case TexBufSoA:tex=1;buf=1;break; default:break;} }
        else { switch(b.type){case 1:tex=1;smp=1;break; case 0:smp=1;break; case 2:case 4:tex=1;break; case 3:case 5:tex=1;buf=nativeAtomic?0:1;break; case 6:case 7:buf=1;break;} }
        tex*=b.count; buf*=b.count; smp*=b.count;
        bool used=b.stages&16;
        if(!argbuf && !used) continue;
        MSLResourceBinding rb; rb.stage=spv::ExecutionModelFragment; rb.desc_set=s; rb.binding=b.binding; rb.count=b.count;
        if(argbuf){ rb.msl_texture=idx; rb.msl_buffer=idx+tex; rb.msl_sampler=idx+tex; }
        else { rb.msl_buffer=dBuf; rb.msl_texture=dTex; rb.msl_sampler=dSmp; dBuf+=buf; dTex+=tex; dSmp+=smp; }
        GPU gl = argbuf ? g : (b.type==1?TexSampSoA:b.type==0?Sampler:(b.type==6||b.type==7)?BufferAux:(buf?TexBufSoA:Texture));
        switch(gl){case Texture: rb.basetype=SPIRType::Image; m.add_msl_resource_binding(rb); added++; break;
          case Sampler: rb.basetype=SPIRType::Sampler; m.add_msl_resource_binding(rb); added++; break;
          case BufferAux: rb.basetype=SPIRType::Void; m.add_msl_resource_binding(rb); added++; break;
          case TexBufSoA: rb.basetype=SPIRType::Image; m.add_msl_resource_binding(rb); rb.basetype=SPIRType::Void; m.add_msl_resource_binding(rb); added+=2; break;
          case TexSampSoA: rb.basetype=SPIRType::SampledImage; m.add_msl_resource_binding(rb); added++; break; default: break;}
        if(argbuf) idx+=tex+buf+smp;
      }
    }
    string out=m.compile(); cout<<"OK "<<out.size()<<" bindings "<<added<<"\n"; if(argc>7){ofstream(argv[7])<<out;} return 0;
  }catch(CompilerError&e){cout<<"FAIL "<<e.what()<<"\n";return 1;}
}

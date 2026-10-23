#!/usr/bin/env python3
"""Execute production v0.12 policies; device graphics/gameplay are not simulated."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def section(text, start, end):
    begin = text.index(start)
    return text[begin:text.index(end, begin)]


def run(source, sanitize=False):
    source = source.resolve()
    classes = ROOT / 'packages/rpcs3_internal_bridge/ios/Classes'
    texture = (source/'rpcs3/Emu/RSX/VK/VKTextureCache.cpp').read_text()
    coverage = section(texture, '\t\tconst bool fully_overwritten = [&]()', '\n\n\t\tif (desc.force_bg_load)')
    device = (source/'rpcs3/Emu/RSX/VK/vkutils/device.h').read_text()
    support = section(device, '\t\tbool get_shader_interpreter_support() const', '\n\n\t\toperator VkPhysicalDevice')
    renderer = (source/'rpcs3/Emu/RSX/VK/VKGSRender.cpp').read_text()
    fallback = section(renderer, '\tm_shader_mode = g_cfg.video.shadermode.get();', '\n\tm_swapchain_dims.width')
    cpp = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>
#include "RPCS3CPUCompatibilityPolicy.h"
using u32 = uint32_t;
constexpr u32 VK_IMAGE_ASPECT_COLOR_BIT = 1, VK_IMAGE_ASPECT_DEPTH_BIT = 2;
struct image_t { u32 w=64,h=32,a=1; u32 width()const{return w;} u32 height()const{return h;} u32 aspect()const{return a;} };
struct region { image_t* src; u32 src_w,src_h,level,dst_x,dst_y,dst_z,dst_w,dst_h; };
bool covers(u32 dst_aspect, u32 mipmaps, image_t* image, const std::vector<region>& sections_to_copy) {
''' + coverage + r'''
return fully_overwritten;
}
struct gpu_t {
  u32 shader_interpreter_sampler_limit=0;
  struct { struct {u32 maxPerStageDescriptorSampledImages=0;} limits; } props;
''' + support + r'''
  const char* get_name()const{return "fixture";}
};
enum class shader_mode { recompiler, async_with_interpreter, interpreter_only, async_recompiler };
struct device_t { gpu_t hardware; gpu_t& gpu(){return hardware;} };
struct shader_setting { shader_mode value; shader_mode get(){return value;} };
struct { struct { shader_setting shadermode; } video; } g_cfg;
struct { template<class... T> void warning(T...){} } rsx_log;
shader_mode effective(device_t* m_device) {
  shader_mode m_shader_mode;
''' + fallback + r'''
  return m_shader_mode;
}
int main() {
  using namespace rewindbox::rpcs3;
  unsigned queries=0;
  assert(!supports_core(cpu_baseline::armv8_a, false, [&](const char*){++queries;return true;}));
  assert(supports_core(cpu_baseline::armv8_a, true, [&](const char*){++queries;return false;}));
  assert(queries==0);
  for (const char* missing : armv84_features) {
    assert(!supports_core(cpu_baseline::armv8_4_a, true,
      [&](const char* key){return std::strcmp(key,missing)!=0;}));
  }
  assert(!supports_core(cpu_baseline::armv8_4_a, true, [](const char*){return false;}));
  assert(supports_core(bundled_core_baseline, true, [](const char*){return true;}));
  device_t dev;
  for (auto mode : {shader_mode::recompiler,shader_mode::async_with_interpreter,
                    shader_mode::interpreter_only,shader_mode::async_recompiler}) {
    for (u32 samplers : {0u,16u,63u,64u,128u}) for(u32 images : {0u,16u,63u,64u,128u}) {
      dev.hardware.shader_interpreter_sampler_limit=samplers;
      dev.hardware.props.limits.maxPerStageDescriptorSampledImages=images;
      const bool supported=samplers>=64 && images>=64;
      assert(dev.hardware.get_shader_interpreter_support()==supported);
      g_cfg.video.shadermode.value=mode;
      const auto want=!supported && (mode==shader_mode::async_with_interpreter || mode==shader_mode::interpreter_only)
          ? shader_mode::recompiler : mode;
      assert(effective(&dev)==want);
      assert(g_cfg.video.shadermode.value==mode); // Saved choice is never rewritten.
    }
  }
  image_t image;
  unsigned cases=0;
  for(u32 levels=1;levels<32;++levels) {
    std::vector<region> regions;
    for(u32 i=0;i<levels;++i) regions.push_back({&image,64,32,i,0,0,0,std::max(1u,64u>>i),std::max(1u,32u>>i)});
    assert(covers(1,levels,&image,regions));++cases;
    assert(!covers(VK_IMAGE_ASPECT_DEPTH_BIT,levels,&image,regions));++cases;
    auto saved=regions.back();regions.pop_back();assert(!covers(1,levels,&image,regions));++cases;regions.push_back(saved);
    for(unsigned fault=0;fault<9;++fault) {
      auto bad=regions;
      switch(fault) {
        case 0:bad[0].src=nullptr;break;case 1:bad[0].src_w=0;break;case 2:bad[0].src_h=0;break;
        case 3:bad[0].level=levels;break;case 4:bad[0].dst_x=1;break;case 5:bad[0].dst_y=1;break;
        case 6:bad[0].dst_z=1;break;case 7:bad[0].dst_w=63;break;case 8:bad[0].dst_h=31;break;
      }
      assert(!covers(1,levels,&image,bad));++cases;
    }
  }
  assert(!covers(1,0,&image,{}));assert(!covers(1,32,&image,{}));
  std::puts("PASS CPU baseline/probe failures; 100 shader mode/limit cases; saved settings retained");
  std::printf("PASS %u complete/partial mip coverage cases; no GPU rendering claimed\n",cases+2);
}
'''
    compiler = os.environ.get('CXX') or shutil.which('clang++') or shutil.which('g++')
    assert compiler, 'No C++ compiler; native tests were not run'
    with tempfile.TemporaryDirectory(prefix='rpcs3-v012-') as directory:
        temp = Path(directory)
        (temp/'policies.cpp').write_text(cpp)
        flags=['-std=c++20','-O2','-Wall','-Wextra','-Werror']
        if sdk:=os.environ.get('HOST_MACOS_SDK'): flags+=['-isysroot',sdk]
        if sanitize: flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
        subprocess.run([compiler,*flags,'-I',str(classes),str(temp/'policies.cpp'),'-o',str(temp/'policies')],check=True)
        subprocess.run([str(temp/'policies')],check=True)
        iso=source/'rpcs3/ios/tests/run-iso-directory-tests.py'
        subprocess.run(['python3',str(iso),*(['--sanitize'] if sanitize else [])],check=True)
        text=(source/'rpcs3/Loader/ISO.cpp').read_text()
        old='file_name.size() > 1 && file_name != ".." && file_name.ends_with(".")'
        assert text.count(old)==1
        control=temp/'ISO.cpp'
        control.write_text(text.replace(old,'file_name.size() > 1 && file_name.ends_with(".")'))
        failed=subprocess.run(['python3',str(iso),'--source',str(control)],capture_output=True,text=True)
        assert failed.returncode!=0 and 'Assertion' in failed.stderr, failed.stdout+failed.stderr
        print('PASS pre-fix ISO directory negative control rejected')
    # Keep native imports, alignment, GPU retirement and acquire dependencies.
    buffer=(source/'rpcs3/Emu/RSX/VK/vkutils/buffer_object.cpp').read_text()
    assert buffer.index('try_neoswap_buffer(')<buffer.index('vkCreateBuffer(')
    assert '.alignment = memory_reqs.alignment' in buffer and '.dedicated = dedicated' in buffer
    heap=(source/'rpcs3/Emu/RSX/VK/vkutils/data_heap.cpp').read_text()
    grown=section(heap,'constexpr VkFlags grown_heap_flags','\n\t\tif (notify_on_grow)')
    assert grown.count('gc->dispose(')==3 and grown.count('grown_heap_flags')==4
    assert 'VMA_ALLOCATION_CREATE_DEDICATED_MEMORY_BIT' in (source/'rpcs3/Emu/RSX/VK/vkutils/memory.cpp').read_text()
    core=(source/'rpcs3/ios/RPCS3IOS.cpp').read_text()
    pad=section(core,'extern "C" rpcs3_ios_status rpcs3_ios_set_pad_state(', 'extern "C" rpcs3_ios_status rpcs3_ios_get_pad_feedback(')
    assert 'std::lock_guard' not in pad and 'shared_pad_states().update' in pad
    for file,anchor in [('Rpcs3JitBridgePlugin.mm','NSDictionary* args ='),('Rpcs3InternalBridgePlugin.mm','if (_api.handle)')]:
        host=(classes/file).read_text()
        begin=host.index('if (![call.method isEqualToString:@"prepareJit"])') if file.startswith('Rpcs3Jit') else host.index('- (BOOL)loadCoreWithExpandedJit:')
        body=host[begin:]
        assert body.index('RPCS3CPUCompatibilityError()')<body.index(anchor)
    print('PASS native loan/alignment/retirement wiring; existing independent controller path; CPU gate before JIT/Core')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--sanitize',action='store_true')
    args=p.parse_args();run(args.source,args.sanitize)

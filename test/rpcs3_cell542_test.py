#!/usr/bin/env python3
"""Execute production pipeline lookup/normalization and bounded timing contexts."""
import argparse, hashlib, json, os, shlex, subprocess, tempfile
from pathlib import Path
from rpcs3_memory523_test import braced
from rpcs3_cell538_test import cache_identities
ROOT=Path(__file__).resolve().parents[1]
sha=lambda b:hashlib.sha256(b).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--report',type=Path);a=p.parse_args();s=a.source.resolve()
 manifest=json.loads((ROOT/'build-utils/rpcs3/canonical-source.json').read_bytes());rec=manifest['cell542']
 cxx=shlex.split(os.environ.get('CXX','c++'))
 if sdk:=os.environ.get('HOST_MACOS_SDK'):cxx+=['-isysroot',sdk]
 flags=['-std=c++20','-O1','-g','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer']
 result={}
 with tempfile.TemporaryDirectory(prefix='cell542-') as td:
  w=Path(td);b=w/'before'
  for path in rec['modified_paths']+rec['new_files']:
   dest=b/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((s/path).read_bytes())
  subprocess.run(['git','apply','--reverse',str(ROOT/'test/fixtures/rpcs3_cell542.diff')],cwd=b,check=True)
  for path,h in rec['before_sha256'].items():assert sha((b/path).read_bytes().replace(b'\r\n',b'\n'))==h
  preamble='\n'.join('#include <'+h+'>' for h in ['vulkan/vulkan.h','algorithm','array','cassert','cmath','cstdint','cstring','functional','iostream','memory','mutex','shared_mutex','thread','tuple','type_traits','unordered_map','utility','vector'])+'\n'
  aliases='using usz=std::size_t;using uchar=unsigned char;using u64=std::uint64_t;using u32=std::uint32_t;using u16=std::uint16_t;using u8=std::uint8_t;using f32=float;\n'
  fnv=(s/'rpcs3/util/fnv_hash.hpp').read_text().replace('#pragma once','').replace('#include "util/types.hpp"','')
  state=(s/'rpcs3/Emu/RSX/VK/vkutils/graphics_pipeline_state.hpp').read_text().replace('#pragma once','').replace('#include "../VulkanAPI.h"','')
  props=braced((s/'rpcs3/Emu/RSX/VK/VKPipelineCompiler.h').read_text(),'struct pipeline_props\n')+';'
  hashing=braced((s/'rpcs3/Emu/RSX/VK/VKPipelineCompiler.h').read_text(),'inline usz hash_struct<vk::pipeline_props>(')
  common=aliases+fnv+state+'namespace vk {\n'+props+'\n}\nnamespace rpcs3 {template<>\n'+hashing+'\n}\n'
  lookup=(s/'rpcs3/Emu/RSX/Program/ProgramStateCache.h').read_text()
  keys='\n'.join(braced(lookup,'struct '+n+'\n')+';' for n in ['pipeline_key','pipeline_key_hash','pipeline_key_compare'])
  body=braced(lookup,'pipeline_data_type get_graphics_pipeline(')
  adapter=(ROOT/'test/native/rpcs3_pipeline539_adapter.inc').read_text();adapter=adapter[adapter.index('struct Shader'):adapter.index('unsigned test(bool corrected)')]
  adapter='using Props=vk::pipeline_props;\n'+adapter
  adapter=adapter.replace('// KEY_TYPES',keys).replace('// LOOKUP','template<typename... Args>\n'+body)
  tests=(ROOT/'test/native/rpcs3_pipeline542.inc').read_text()
  code='#define VK_NO_PROTOTYPES\n'+preamble
  for label,tree in [('before',b),('after',s)]:
   normalize=(s/'rpcs3/Emu/RSX/VK/vkutils/pipeline_key_normalization.h').read_text().replace('#pragma once','').replace('#include "graphics_pipeline_state.hpp"','') if label=='after' else ''
   validation=braced((tree/'rpcs3/Emu/RSX/VK/VKProgramBuffer.h').read_text(),'void validate_pipeline_properties(')
   code+=('#define CELL542_AFTER\n' if label=='after' else '')+'namespace '+label+' {\n'+common+normalize+'using namespace vk;\n'+adapter.replace('// VALIDATION',validation)+tests+'\n}\n'
   result[label+'ValidationSHA256']=sha(validation.encode())
  render=(s/'rpcs3/Emu/RSX/VK/VKRenderPass.cpp').read_text()
  render_adapter=(ROOT/'test/native/rpcs3_renderpass542.inc').read_text()
  render_adapter=render_adapter.replace('// RENDERPASS_KEY',braced(render,'union renderpass_key_blob\n')+';').replace('// GET_RENDERPASS',braced(render,'VkRenderPass get_renderpass('))
  code+='template<class T> unsigned size32(const T& v) {return static_cast<unsigned>(v.size());}\n'+render_adapter
  code+='#include "ios/IOSShaderTiming.h"\n' 
  code+=(ROOT/'test/native/rpcs3_timing542.inc').read_text()
  code+='''int main() {
 auto b=before::test(false),a=after::test(true);
 auto samples=after::semantic_test();timing_test();
 auto passes=renderpass542::vk::test();
 std::cout<<"{\\"beforeBuilds\\":["<<b[0]<<","<<b[1]<<","<<b[2]<<","<<b[3]
 <<"],\\"afterBuilds\\":["<<a[0]<<","<<a[1]<<","<<a[2]<<","<<a[3]
 <<"],\\"renderpassCompatibilityCases\\":"<<passes<<",\\"blendReferenceCases\\":"<<samples<<"}\\n";
}\n'''
  cpp=w/'pipeline.cpp';cpp.write_text(code);exe=w/'pipeline'
  subprocess.run(cxx+flags+['-I'+str(ROOT/'packages/libretro_internal_bridge/ios/ThirdParty/include'),'-I'+str(s/'rpcs3'),str(cpp),'-o',str(exe)],check=True)
  run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=90,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'))
  if run.returncode:print(run.stderr);run.check_returncode()
  result.update(json.loads(run.stdout));result['harnessSHA256']=sha(cpp.read_bytes())
 # Layout encoding and real driver call are inspected by source-bound checks.
 render=(s/'rpcs3/Emu/RSX/VK/VKRenderPass.cpp').read_text()
 assert 'u64 layout_blob   : 15;' in render and 'u64 input_attachments_mask : 5;' in render
 compiler=(s/'rpcs3/Emu/RSX/VK/VKPipelineCompiler.cpp').read_text()
 assert 'PipelineContextScope context' in compiler and 'reinterpret_cast<u64>(modules[0])' in compiler
 assert 'info.renderPass = vk::get_renderpass' in compiler
 report=dict(passed=True,sanitized=True,physicalDeviceTested=False,gameplayMeasured=False,codegen=cache_identities(s),results=result,
  scope='Exact production pipeline lookup/validation/hash with compiler adapter; synthetic equivalence sequences and independent blend equations. No Metal rendering or device FPS measurement.')
 if a.report:a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Execute exact before/after graphics-cache code with portable backend adapters."""
import argparse,hashlib,json,os,shlex,subprocess,tempfile
from pathlib import Path
from rpcs3_memory523_test import braced
from rpcs3_cell538_test import cache_identities
ROOT=Path(__file__).resolve().parents[1]
sha=lambda b:hashlib.sha256(b).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--report',type=Path);a=p.parse_args()
 source=a.source.resolve();manifest=json.loads((ROOT/'build-utils/rpcs3/canonical-source.json').read_bytes());record=manifest['cell539']
 cxx=shlex.split(os.environ.get('CXX','c++'))
 if sdk:=os.environ.get('HOST_MACOS_SDK'):cxx+=['-isysroot',sdk]
 flags=['-std=c++20','-O1','-g','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer']
 results={}
 with tempfile.TemporaryDirectory(prefix='cell539-') as td:
  w=Path(td);before=w/'before'
  for relative in record['modified_paths']:
   target=before/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((source/relative).read_bytes())
  subprocess.run(['git','apply','--reverse',str(ROOT/'test/fixtures/rpcs3_cell539.diff')],cwd=before,check=True)
  for relative,digest in record['before_sha256'].items():assert sha((before/relative).read_bytes().replace(b'\r\n',b'\n'))==digest
  validation=braced((source/'rpcs3/Emu/RSX/VK/VKProgramBuffer.h').read_text(),'void validate_pipeline_properties(')
  header='\n'.join('#include <'+n+'>' for n in ('algorithm','cassert','functional','iostream','memory','mutex','shared_mutex','tuple','unordered_map','utility','vector'))+'\n'
  code=header
  for label,tree in [('before',before),('after',source)]:
   text=(tree/'rpcs3/Emu/RSX/Program/ProgramStateCache.h').read_text()
   body=braced(text,'pipeline_data_type get_graphics_pipeline(')
   keys='\n'.join(braced(text,'struct '+n+'\n')+';' for n in ('pipeline_key','pipeline_key_hash','pipeline_key_compare'))
   adapter=(ROOT/'test/native/rpcs3_pipeline539_adapter.inc').read_text().replace('// VALIDATION',validation).replace('// KEY_TYPES',keys).replace('// LOOKUP','template<typename... Args>\n'+body)
   code+='namespace '+label+' {\n'+adapter+'\n}\n';results[label+'LookupSHA256']=sha(body.encode())
   # Execute the complete production dirty-state block. The decoder and GPU
   # objects are adapters; branch order, assignments and returns are unmodified.
   render=(tree/'rpcs3/Emu/RSX/VK/VKGSRender.cpp').read_text();load=braced(render,'bool VKGSRender::load_program()')
   block=braced(load,'if (m_graphics_state & rsx::pipeline_state::pipeline_config_dirty)')
   declarations='''
namespace rsx { namespace pipeline_state { enum { pipeline_config_dirty=1 }; } }
struct Flags { unsigned v=1; bool operator&(unsigned b) const {return v&b;} void clear(unsigned b) {v&=~b;} };
struct Props { unsigned renderpass_key=0; bool operator==(const Props&) const=default; };
inline unsigned decodes=0;
namespace vk { using pipeline_props=Props; template<class... A> Props decode_rsx_state(A&&...) {++decodes;return {};} }
struct Renderer {
 Flags m_graphics_state; Props m_pipeline_properties; int* m_program=nullptr;
 struct Interpreter { bool is_interpreter(int*) const {return false;} } m_shader_interpreter;
 int m_ctx=0,vertex_state=0,backend_config=0;
 struct {std::pair<int,int> m_bound_depth_stencil;} m_rtts;
 std::vector<int> m_draw_buffers;
 struct Device {bool get_depth_bounds_support() const{return true;}} device;
 Device* m_device=&device;
 unsigned m_current_renderpass_key=0;
 struct { unsigned ctrl=0; } current_fragment_program;
 bool run() {
'''
   code+='namespace dirty_'+label+' {\nusing u8=unsigned char; constexpr unsigned RSX_SHADER_CONTROL_PROGRAMMABLE_BLENDING=1;\n'+declarations+block+'\nreturn false; }\n};\n'
   code+='''unsigned test(bool corrected) {
 Renderer r; int program=1;r.m_program=&program;
 for(int i=0;i<1000;++i) r.run();
 auto count=decodes;assert(count==(corrected?1u:1000u));
 r.m_graphics_state.v=1;r.m_current_renderpass_key=2;r.run();
 assert(r.m_pipeline_properties.renderpass_key==2 && !r.m_graphics_state.v);
 return count;
}\n}\n'''
   results[label+'DirtyBlockSHA256']=sha(block.encode())
  hash_header=(source/'rpcs3/util/fnv_hash.hpp').read_text().replace('#pragma once','').replace('#include "util/types.hpp"','')
  state=(source/'rpcs3/Emu/RSX/VK/vkutils/graphics_pipeline_state.hpp').read_text().replace('#pragma once','').replace('#include "../VulkanAPI.h"','')
  code='#include <vulkan/vulkan.h>\n#include <cstdint>\n#include <cstring>\n#include <type_traits>\n'+code
  for label,tree in [('before',before),('after',source)]:
   text=(tree/'rpcs3/Emu/RSX/VK/VKPipelineCompiler.h').read_text()
   props=braced(text,'struct pipeline_props\n')+';'
   hashing=braced(text,'inline usz hash_struct<vk::pipeline_props>(')
   code+='namespace '+label+'_hash {\nusing usz=std::size_t;using uchar=unsigned char;using u64=std::uint64_t;using u32=std::uint32_t;using u16=std::uint16_t;using u8=std::uint8_t;using f32=float;\n'+hash_header+state+'namespace vk {\n'+props+'\n}\nnamespace rpcs3 { template<>\n'+hashing+'\n}\n'
   tests=(ROOT/'test/native/rpcs3_pipeline_hash539.inc').read_text()
   code+=tests+'\n}\n'
   results[label+'HashSHA256']=sha(hashing.encode())
  cache_source=(source/'rpcs3/Emu/RSX/rsx_cache.h').read_text()
  assert 'data.pipeline_storage_hash, state_hash);' in cache_source
  assert 'pipeline = data.pipeline_properties;' in cache_source
  # New hashes name future records; loader retains valid legacy records.
  assert 'm_storage.get_hash(pipeline) == data.pipeline_storage_hash' not in cache_source
  code+='''int main() {
 assert(before_hash::test_hash(false)==0); assert(after_hash::test_hash(true)==4);
 const auto old=before::test(false),now=after::test(true);
 const auto d1=dirty_before::test(false),d2=dirty_after::test(true);
 std::cout<<"{\\"beforePipelineBuilds\\":"<<old<<",\\"afterPipelineBuilds\\":"<<now
 <<",\\"requests\\":1000,\\"beforeRepeatedDecodes\\":"<<d1<<",\\"afterRepeatedDecodes\\":"<<d2<<"}\\n";
}\n'''
  cpp=w/'pipeline.cpp';cpp.write_text(code);exe=w/'pipeline'
  subprocess.run(cxx+flags+['-I'+str(ROOT/'packages/libretro_internal_bridge/ios/ThirdParty/include'),str(cpp),'-o',str(exe)],check=True)
  result=subprocess.run([str(exe)],capture_output=True,text=True,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'),timeout=60)
  if result.returncode:print(result.stderr);result.check_returncode()
  results['fixture']=json.loads(result.stdout)
  results['pipelineHashCases']=dict(deterministicCollisionsBefore=4,deterministicCollisionsAfter=0,equalMaskVariants=4096,legacyPropertiesLayoutPreserved=True)
 report=dict(passed=True,sanitized=True,physicalDeviceTested=False,gameplayMeasured=False,codegen=cache_identities(source),results=results,
  scope='Actual production lookup, Vulkan output-mask validation and dirty-state block; portable compiler/GPU adapters. Constructed equivalent-mask sequence, not a replay of device draw calls or a measured FPS gain.')
 if a.report:a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()

// SPDX-License-Identifier: MIT
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <map>
#include <string>
#include <vector>
#include "ios/NeoSwapStorage/SourceClient.h"
using u32=uint32_t;using VkShaderModule=uintptr_t;using VkResult=int;
constexpr VkShaderModule VK_NULL_HANDLE=0;constexpr VkResult VK_SUCCESS=0,VK_ERROR_INVALID_SHADER_NV=-1;
constexpr int VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO=1;
struct VkShaderModuleCreateInfo{int sType=0;const u32* pCode=nullptr;size_t codeSize=0;};
#define ensure(x) do{if(!(x))std::abort();}while(0)
namespace fmt{template<class...Args>[[noreturn]]void throw_exception(const char*,Args&&...){std::abort();}}
namespace glsl{constexpr int glsl_rules_vulkan=0;}
namespace spirv{bool compile_glsl_to_spv(std::vector<u32>& out,const std::string&,u32,int){out={0x07230203,1,2,3};return true;}}
static unsigned module_calls=0,admissions=0,discards=0;static uint64_t released_bytes=0;
static std::map<uint64_t,std::string> archives;static uint64_t next_id=1;
static int device=1;static auto* g_render_device=&device;
int vkCreateShaderModule(int,const VkShaderModuleCreateInfo* info,void*,VkShaderModule* handle){ensure(info->codeSize==16&&info->pCode[0]==0x07230203);*handle=++module_calls;return VK_SUCCESS;}
namespace neostation::storage_client{
struct Ticket{};enum class ModuleResult{ok,retry_source,fatal};enum class CompileResult{ok,source_failure,module_failure};
template<class Compile,class Create>CompileResult compile(Ticket,std::vector<u32>& compiled,Compile&& build,Create&& create){ensure(build(compiled));ensure(create(compiled.data(),compiled.size()*sizeof(u32))==ModuleResult::ok);return CompileResult::ok;}
}
struct Log{template<class...Args>void notice(const char*,Args&&...){}}rsx_log;
const char* to_string(u32){return "shader";}
static uint64_t session(){return 1;}
static int admit(uint64_t epoch,uint32_t,const char* text,uint64_t bytes,uint64_t* id){ensure(epoch==1);*id=next_id++;archives.emplace(*id,std::string(text,bytes));++admissions;return NS_SOURCE_OK;}
static int read(uint64_t epoch,uint64_t id,char* out,uint64_t bytes,int* error){ensure(epoch==1);const auto& s=archives.at(id);ensure(s.size()==bytes);s.copy(out,bytes);*error=0;return NS_SOURCE_OK;}
static void discard(uint64_t,uint64_t id){ensure(archives.erase(id)==1);++discards;}
static void released(uint64_t,uint64_t bytes){released_bytes+=bytes;}
const NeoSwapSourceAPI api{sizeof(api),NEOSWAP_SOURCE_ABI,session,admit,read,discard,released};
struct shader{
 u32 type=0;std::string m_source;std::vector<u32>m_compiled;VkShaderModule m_handle=0;
 neostation::storage_client::Ticket m_storage_ticket;neostation::source_client::ColdSource m_source_archive;
 VkShaderModule compile();
};
#ifdef GLSL_REFERENCE
#include "before.inc"
#else
#include "after.inc"
#endif
int main(){
 ensure(neostation::source_client::install(&api)==NS_SOURCE_OK);unsigned retained=0;uint64_t retained_bytes=0;
 for(size_t bytes:{size_t(4096),size_t(52362),size_t(65535),size_t(65536),size_t(1048576)}){
  shader value;value.m_source=std::string(bytes,'s');const auto expected=value.m_source;ensure(value.compile()!=0);
  std::string restored;int error=0;if(value.m_source_archive.archived()){ensure(value.m_source.empty());ensure(value.m_source_archive.restore(restored,error)==NS_SOURCE_OK&&restored==expected);}
  else{ensure(value.m_source==expected);++retained;retained_bytes+=bytes;}
 }
 ensure(archives.empty()&&discards==admissions);
 std::cout<<"{\"moduleCalls\":"<<module_calls<<",\"admissions\":"<<admissions<<",\"retainedObjects\":"<<retained<<",\"retainedBytes\":"<<retained_bytes<<",\"releasedCapacityBytes\":"<<released_bytes<<",\"exactDebugText\":true,\"balancedRetirement\":true}\n";
}

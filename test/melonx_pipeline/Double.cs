using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Ryujinx.Common.Logging;
using Silk.NET.Vulkan;
namespace Silk.NET.Vulkan {
enum Result { Success=0, PipelineCompileRequired=1000297000, ErrorUnknown=-13,
    ErrorDeviceLost=-4, ErrorOutOfHostMemory=-1, ErrorOutOfDeviceMemory=-2 }
struct PipelineCache {} struct Device {} struct RenderPass {}
struct PipelineShaderStageCreateInfo {}
}
namespace Ryujinx.Common.Logging {
enum LogClass {Gpu}
class Sink { public List<string> Messages=new(); public void PrintMsg(LogClass c,string s)=>Messages.Add(s); }
static class Logger {public static Sink Error=new(),Warning=new();}
}
namespace Ryujinx.Graphics.Vulkan {
enum ProgramLinkStatus {Incomplete,Success,Failure}
class Shader {
 public ProgramLinkStatus CompileStatus;
 public Shader(ProgramLinkStatus status){CompileStatus=status;}
 public PipelineShaderStageCreateInfo GetInfo()=>new();
 public void WaitForCompile(){}
}
class PipelineBase { public PipelineCache PipelineCache; }
class Scheduler { public void PromotePipelineCompile(Task task){} }
class VulkanRenderer { public object Pipeline=new PipelineBase();public Scheduler BackgroundCompilationScheduler=new(); }
class DisposableRenderPass {public RenderPass Value;}
class ProgramPipelineState {
 public PipelineState ToVulkanPipelineState(VulkanRenderer gd){var p=new PipelineState();p.Initialize();return p;}
}
partial class PipelineState {
 public static Queue<Result> Results=new();public static int Live,Calls;
 public PipelineShaderStageCreateInfo[] Stages=new PipelineShaderStageCreateInfo[1];
 public uint StagesCount,SamplesCount=1;public int PipelineLayout,Internal;
 public bool HasTessellationControlShader;
 public void Initialize(){Live++;} public void Dispose(){Live--;}
 public object CreateComputePipeline(VulkanRenderer gd,Device d,ShaderCollection p,PipelineCache c,
  bool throwOnError=true,bool cachePipelineFailure=true) =>
  CreateGraphicsPipeline(gd,d,p,c,new(),throwOnError,cachePipelineFailure);
 public object CreateGraphicsPipeline(VulkanRenderer gd,Device d,ShaderCollection p,PipelineCache c,RenderPass r,
  bool throwOnError=false,bool cachePipelineFailure=true) {
  if(p.Cache.TryGetValue(Internal,out var hit))return hit;
  Calls++;var result=Interpret(Results.Dequeue(),p,throwOnError,cachePipelineFailure);
  if(result!=null)p.Cache.Add(Internal,result);
  return result;
 }
}
class ShaderCollection {
 public bool CompilesInBackground,IsCompute,HasTessellationControlShader;
 public ProgramLinkStatus LinkStatus=ProgramLinkStatus.Incomplete;
 public Dictionary<int,object> Cache=new();
 Shader[] _shaders;Task[] _shaderCompileTasks;Task _compileTask,_initialPipelineCompileTask;
 int _backgroundCompilationDemanded;bool _highPriorityBackgroundCompilation,_initialized;
 VulkanRenderer _gd=new();Device _device;ProgramPipelineState _state=new();
 PipelineShaderStageCreateInfo[] _infos=new PipelineShaderStageCreateInfo[1];
 object _initializeLock=new();public int PipelineLayout;
 public ShaderCollection(bool compute=false,bool async=false,bool moduleFailure=false) {
  IsCompute=compute;CompilesInBackground=async;
  _shaders=new[]{new Shader(moduleFailure?ProgramLinkStatus.Failure:ProgramLinkStatus.Success)};
  _shaderCompileTasks=new[]{Task.CompletedTask};
 }
 public void Start(){_compileTask=BackgroundCompilation();}
 public void Complete(){_compileTask.GetAwaiter().GetResult();GetInfos();}
 public bool Draw() {
  GetInfos();if(LinkStatus!=ProgramLinkStatus.Success)return false;
  var p=new PipelineState{Internal=1}; // actual state differs from speculative state 0
  return p.CreateGraphicsPipeline(_gd,_device,this,new(),new())!=null;
 }
 public void AddGraphicsPipeline(ref int key,object value){Cache.Add(key,value);}
 Task<bool> WaitForShaderModuleCompilation()=>Task.FromResult(EnsureShadersReady(true));
 Task RunBackgroundPipelineCompile(Action<PipelineCache> f,bool highPriority,bool demanded) {
  f(new());return Task.CompletedTask;
 }
 void ClearInitialBackgroundPipelineTask(){}
 DisposableRenderPass CreateDummyRenderPass()=>new();
 bool TryGetInfos(out PipelineShaderStageCreateInfo[] info,bool blocking){info=_infos;return EnsureShadersReady(blocking);}
 /* PRODUCTION_METHODS */
}
}

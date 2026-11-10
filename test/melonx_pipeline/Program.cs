using System;
using System.Text.Json;
using Ryujinx.Graphics.Vulkan;
using Ryujinx.Common.Logging;
using Silk.NET.Vulkan;
bool control=args[0]=="control";
int checks=0;
void Check(bool ok,string label){if(!ok)throw new Exception(label);checks++;}
void Reset(){PipelineState.Results.Clear();PipelineState.Live=PipelineState.Calls=0;Logger.Error.Messages.Clear();Logger.Warning.Messages.Clear();}
// Same shaders, deliberately different dummy and actual render-pass states.
foreach(bool compute in new[]{false,true}) {
 Reset();PipelineState.Results.Enqueue(Result.ErrorUnknown);PipelineState.Results.Enqueue(Result.Success);
 var p=new ShaderCollection(compute);p.Start();p.Complete();
 Check(p.LinkStatus==(control?ProgramLinkStatus.Failure:ProgramLinkStatus.Success),"warm-up does not poison valid modules");
 Check(p.Draw()==!control,"valid real-state draw survives failed warm-up");
 Check(PipelineState.Live==(control?1:0),"temporary pipeline state released after exception");
 Check(p.Cache.Count==(control?0:1),"only real successful state cached");
 Check(control?Logger.Error.Messages.Count==1:Logger.Warning.Messages.Count==1,"warm-up failure is visible");
}
foreach(bool async in new[]{false,true}) {
 Reset();var p=new ShaderCollection(async:async,moduleFailure:true);p.Start();p.Complete();
 Check(p.LinkStatus==ProgramLinkStatus.Failure && !p.Draw(),"module failures remain failures");
 Check(PipelineState.Calls==0 && PipelineState.Live==0,"failed modules do not create pipelines");
 Reset();PipelineState.Results.Enqueue(Result.Success);PipelineState.Results.Enqueue(Result.Success);
 p=new ShaderCollection(async:async);p.Start();p.Complete();
 Check(p.Draw() && PipelineState.Live==0,"successful warm-up and draw preserved");
}
// Lost devices and allocation failures cannot become recoverable warm-up misses.
foreach(Result failure in new[]{Result.ErrorDeviceLost,Result.ErrorOutOfHostMemory,Result.ErrorOutOfDeviceMemory}) {
 Reset();PipelineState.Results.Enqueue(failure);var p=new ShaderCollection();p.Start();
 bool threw=false;try{p.Complete();}catch(VulkanException e){threw=e.Message.Contains(failure.ToString());}
 Check(threw==!control,"fatal synchronous warm-up error propagates");
 Check(PipelineState.Live==(control?1:0),"fatal warm-up state released");
 // Exact production API-result block with errors allowed: no cached null for fatal errors.
 Reset();PipelineState.Results.Enqueue(failure);p=new ShaderCollection();
 var state=new PipelineState();threw=false;
 try{state.CreateGraphicsPipeline(new(),new(),p,new(),new());}catch(VulkanException e){threw=e.Message.Contains(failure.ToString());}
 Check(threw==!control && p.Cache.Count==(control?1:0),"fatal draw error not hidden as a null pipeline");
}
Reset();PipelineState.Results.Enqueue(Result.ErrorUnknown);
var bad=new ShaderCollection();var badState=new PipelineState();
Check(badState.CreateGraphicsPipeline(new(),new(),bad,new(),new())==null,"ordinary failure has no pipeline");
Check(badState.CreateGraphicsPipeline(new(),new(),bad,new(),new())==null && PipelineState.Calls==1,"repeated failure uses cached state");
Check(Logger.Error.Messages.Count==(control?0:1),"one actionable draw error instead of silent missing draws");
Reset();PipelineState.Results.Enqueue(Result.PipelineCompileRequired);
var pending=new ShaderCollection();
Check(new PipelineState().CreateGraphicsPipeline(new(),new(),pending,new(),new())==null && pending.Cache.Count==0 && Logger.Error.Messages.Count==0,"compile-required is not an error or permanent failure");
Console.WriteLine(JsonSerializer.Serialize(new{mode=control?"control":"fixed",checks,passed=true,
 reproducedPoisonedProgram=control,physicalDeviceTested=false,vulkanDouble=true}));

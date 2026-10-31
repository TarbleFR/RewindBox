using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Threading;
using Ryujinx.Common.Configuration;
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;

static class Program
{
    static int checks, scenarios;
    static bool candidate;
    static readonly List<object> results=new();
    static readonly BindingFlags Flags=BindingFlags.NonPublic|BindingFlags.Public|BindingFlags.Instance;
    static void Check(bool value,string why){checks++;if(!value)throw new Exception(why);}
    static object State(PipelineCacheManager m,int worker=0)=>worker<0?typeof(PipelineCacheManager).GetField("_mainState",Flags).GetValue(m):((Array)typeof(PipelineCacheManager).GetField("_workerStates",Flags).GetValue(m)).GetValue(worker);
    static T Get<T>(object state,string field)=>(T)state.GetType().GetField(field,Flags).GetValue(state);
    static void Set(object state,string field,object value)=>state.GetType().GetField(field,Flags).SetValue(state,value);
    static void Force(PipelineCacheManager m,int worker=0)=>typeof(PipelineCacheManager).GetMethod("Maintain",Flags).Invoke(m,new object[]{State(m,worker),true,false});
    static string Disk(object state)=>Get<string>(state,"Path");
    static void Bytes(string path,byte[] expected,string why)=>Check(File.ReadAllBytes(path).SequenceEqual(expected),why);
    static int Exports(Vk api,PipelineCache cache)=>api.ExportCounts.GetValueOrDefault(cache);
    static int Probes(Vk api,PipelineCache cache)=>api.ProbeCounts.GetValueOrDefault(cache);
    sealed class Fixture:IDisposable
    {
        public readonly string Root=Path.Combine(Path.GetTempPath(),"pipeline-pacing-"+Guid.NewGuid().ToString("N"));
        public readonly Vk Api=new();public readonly Lock MainLock=new();public readonly PipelineCacheManager Manager;
        public Fixture(int workers=1,byte[] initial=null,bool reject=false,bool pathless=false)
        {
            AppDataManager.BaseDirPath=pathless?null:Root;VulkanRenderer.PipelineCacheScope=null;
            if(initial!=null){string d=Path.Combine(Root,"cache","vulkan");Directory.CreateDirectory(d);File.WriteAllBytes(Path.Combine(d,"pipeline-00000001-00000002-00000003.worker0.vkpc"),initial);}
            Api.RejectNextSnapshot=reject;Manager=new(Api,new VulkanPhysicalDevice(),new Device(),workers,MainLock);
        }
        public void Dispose(){Manager.Dispose();if(Directory.Exists(Root))Directory.Delete(Root,true);}
    }
    static void NearBudget()
    {
        scenarios++;byte[] old=Enumerable.Repeat((byte)1,60*1024).ToArray();using var f=new Fixture(initial:old);
        var m=f.Manager;object s=State(m);Set(s,"Budget",64L*1024);var cache=m.GetWorkerCache(0);
        for(int i=1;i<=193;i++)
        {
            f.Api.Data[cache][0]=(byte)i;m.NotifyWorkerPipelineCreated(0);
            Check(m.GetWorkerCache(0)==cache,"below-budget actual cache retained");
            Check(Probes(f.Api,cache)==i,"estimated pressure still sizes every creation");
            Check(Exports(f.Api,cache)==(candidate?(i<64?0:1):i),"checkpoint cadence differs only at disk export");
        }
        int creationProbes=Probes(f.Api,cache);int before=Exports(f.Api,cache);Force(m);
        Check(Probes(f.Api,cache)==194,"forced final still probes size");
        Check(Exports(f.Api,cache)==(candidate?2:193),"forced final stores latest generation");
        Bytes(Disk(s),f.Api.Data[cache],"final exact same-size bytes saved");
        int after=Exports(f.Api,cache);Force(m);Check(Exports(f.Api,cache)==after,"clean repeated final avoids export");
        results.Add(new{scenario="nearBudget193Creates",creationProbes,exportsBeforeFinal=before,exportsIncludingFinal=after,bytesIncludingFinal=f.Api.ExportBytes.GetValueOrDefault(cache)});
    }
    static void CountAndTimeGates()
    {
        scenarios++;using var f=new Fixture();var m=f.Manager;object s=State(m);Set(s,"Budget",long.MaxValue/2);var c=m.GetWorkerCache(0);
        for(int i=0;i<63;i++)m.NotifyWorkerPipelineCreated(0);Check(Probes(f.Api,c)==0,"63 clean-budget creations do not checkpoint");
        m.NotifyWorkerPipelineCreated(0);Check(Exports(f.Api,c)==1,"64th creation checkpoints");
        for(int i=0;i<63;i++)m.NotifyWorkerPipelineCreated(0);Check(Exports(f.Api,c)==1,"63 additional creations remain gated");
        Set(s,"LastSaveTimestamp",Environment.TickCount64-15001);m.NotifyWorkerPipelineCreated(0);Check(Exports(f.Api,c)==2,"both aged time and 64 new creations checkpoint");
        for(int i=0;i<64;i++)m.NotifyWorkerPipelineCreated(0);Check(Exports(f.Api,c)==2,"64 new creations alone cannot bypass time gate");
        Set(s,"LastSaveTimestamp",Environment.TickCount64-15001);m.NotifyWorkerPipelineCreated(0);Check(Exports(f.Api,c)==3,"aged time admits accumulated dirty work");
        Force(m);Check(Exports(f.Api,c)==3,"clean forced checkpoint is not exported twice");
    }
    static void DirtySameSize()
    {
        scenarios++;using var f=new Fixture();var m=f.Manager;var c=m.GetWorkerCache(0);var s=State(m);Set(s,"Budget",long.MaxValue/2);
        f.Api.Set(c,3);m.NotifyWorkerPipelineCreated(0);Force(m);Bytes(Disk(s),f.Api.Data[c],"first forced snapshot");
        f.Api.Set(c,7);m.NotifyWorkerPipelineCreated(0);Force(m);Check(Exports(f.Api,c)==2,"same-sized dirty generation exported");Bytes(Disk(s),f.Api.Data[c],"same-sized updated opaque bytes");
        Force(m);Check(Exports(f.Api,c)==2,"same-sized clean generation skipped");
    }
    static void Recycle(bool mainTooLarge,bool createFails,bool opaqueExpansion)
    {
        scenarios++;byte[] initial=Enumerable.Repeat((byte)3,16).ToArray();using var f=new Fixture(initial:initial);var m=f.Manager;var c=m.GetWorkerCache(0);var s=State(m);var main=State(m,-1);
        Set(s,"Budget",32L);Set(main,"Budget",mainTooLarge?32L:100L);f.Api.Data[c]=Enumerable.Repeat((byte)7,48).ToArray();
        f.Api.FailNextCreate=createFails;f.Api.ExpandNextMerge=opaqueExpansion;
        f.Api.BeforeMerge=()=>Check(f.MainLock.IsHeldByCurrentThread,"recycle preservation holds main cache lock");
        m.NotifyWorkerPipelineCreated(0);
        Check(Probes(f.Api,c)==1,"oversize measured immediately before checkpoint count");
        Check(m.GetWorkerCache(0)==c==createFails,"replacement only used after successful creation");
        Bytes(Disk(s),initial,"urgent recycle preserves old disk snapshot");
        if(createFails)
        {
            Check(Get<bool>(s,"Frozen"),"failed create freezes old native cache");m.NotifyWorkerPipelineCreated(0);Force(m);Check(Probes(f.Api,c)==1,"frozen cache not retried in hot path");Check(f.Api.Data.ContainsKey(c),"failed create retains original native handle");
        }
        else
        {
            Check(!f.Api.Data.ContainsKey(c),"successful recycle destroys outgrown native handle");Check(Get<bool>(s,"Recycled"),"recreated ownership recorded");
            Check(f.Api.Merges==(mainTooLarge?0:1),"only admitted main cache preserves outgrown worker");
            if(!mainTooLarge)Check(f.Api.Data[m.MainCache].Take(48).All(x=>x==7),"preservation merges actual old worker bytes");
            if(opaqueExpansion)Check(Get<long>(main,"_measuredBytes")==128,"opaque merged size remeasured");
            Force(m);Bytes(Disk(s),initial,"empty replacement cannot overwrite useful worker checkpoint");
        }
    }
    static void Errors()
    {
        foreach(bool export in new[]{false,true})
        {
            scenarios++;byte[] initial=Enumerable.Repeat((byte)1,16).ToArray();using var f=new Fixture(initial:initial);var m=f.Manager;var c=m.GetWorkerCache(0);var s=State(m);Set(s,"Budget",long.MaxValue/2);
            f.Api.Set(c,9);m.NotifyWorkerPipelineCreated(0);long saved=Get<long>(s,"SavedGeneration");
            f.Api.FailNextExport=export;f.Api.FailNextSize=!export;Force(m);Bytes(Disk(s),initial,"native failure preserves prior snapshot");Check(Get<long>(s,"SavedGeneration")==saved,"native failure does not publish saved generation");
            Force(m);Bytes(Disk(s),f.Api.Data[c],"forced retry exports latest unchanged-size bytes");Check(Get<long>(s,"SavedGeneration")==Get<long>(s,"Generation"),"successful retry publishes generation");
        }
    }
    static void MergeRetry()
    {
        scenarios++;using var f=new Fixture();var m=f.Manager;var c=m.GetWorkerCache(0);Set(State(m),"Budget",long.MaxValue/2);f.Api.Set(c,6);m.NotifyWorkerPipelineCreated(0);
        f.Api.FailNextMerge=true;m.MergeAndSave();Check(Get<long>(State(m),"MergedGeneration")==0,"failed merge leaves worker merge generation dirty");Check(!File.Exists(Disk(State(m,-1))),"failed merge does not export main");
        m.MergeAndSave();Check(Get<long>(State(m),"MergedGeneration")==Get<long>(State(m),"Generation"),"retry marks merge only after success");Bytes(Disk(State(m,-1)),f.Api.Data[m.MainCache],"retry exports merged main bytes");
        int merges=f.Api.Merges,exports=f.Api.Exports;m.MergeAndSave();Check(f.Api.Merges==merges && f.Api.Exports==exports,"clean repeat neither merges nor exports");
    }
    static void RejectedSnapshot()
    {
        scenarios++;byte[] initial=Enumerable.Repeat((byte)12,32).ToArray();using var f=new Fixture(initial:initial,reject:true);var m=f.Manager;var c=m.GetWorkerCache(0);Check(!Get<bool>(State(m),"HasUsableSnapshot"),"rejected driver blob not usable");
        Force(m);Bytes(Disk(State(m)),f.Api.Data[c],"rejected cache replaced by accepted empty state");Check(f.Api.Data[c].Length==16,"fresh cache factory retained");
    }
    static void IndependentWorkersAndPathless()
    {
        scenarios++;using(var f=new Fixture(2))
        {
            for(int w=0;w<2;w++)Set(State(f.Manager,w),"Budget",long.MaxValue/2);
            for(int n=0;n<64;n++)f.Manager.NotifyWorkerPipelineCreated(0);
            Check(Exports(f.Api,f.Manager.GetWorkerCache(0))==1&&Exports(f.Api,f.Manager.GetWorkerCache(1))==0,"workers keep independent pacing");
            f.Api.Set(f.Manager.GetWorkerCache(1),4);f.Manager.NotifyWorkerPipelineCreated(1);f.Manager.MergeAndSave();
            Bytes(Disk(State(f.Manager,1)),f.Api.Data[f.Manager.GetWorkerCache(1)],"final flush saves subinterval worker");
        }
        scenarios++;using(var f=new Fixture(pathless:true))
        {
            var s=State(f.Manager);Set(s,"Budget",32L);var old=f.Manager.GetWorkerCache(0);f.Api.Data[old]=new byte[48];f.Manager.NotifyWorkerPipelineCreated(0);
            Check(f.Manager.GetWorkerCache(0)!=old,"pathless worker still recycles under pressure");Check(f.Api.Exports==0,"pathless caches never export disk data");
        }
    }
    static void Main(string[] args)
    {
        candidate=args[0]=="candidate";
#if INSTRUMENTED_CANDIDATE
        Ryujinx.Common.EmbeddedPerformanceDiagnostics.Start(1);
#endif
        NearBudget();CountAndTimeGates();DirtySameSize();Recycle(false,false,false);Recycle(true,false,false);Recycle(false,true,false);Recycle(false,false,true);Errors();MergeRetry();RejectedSnapshot();IndependentWorkersAndPathless();
#if INSTRUMENTED_CANDIDATE
        Ryujinx.Common.EmbeddedPerformanceDiagnostics.Stop(1);
#endif
        Console.WriteLine(JsonSerializer.Serialize(new{variant=args[0],assertions=checks,scenarios,results}));
    }
}

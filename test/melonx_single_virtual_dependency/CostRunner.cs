using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using System.Runtime.Loader;
using System.Text.Json;

var contexts=new[]{new AssemblyLoadContext("control",true),new AssemblyLoadContext("candidate",true)};
var types=contexts.Select((context,i)=>context.LoadFromAssemblyPath(args[i]).GetType("Program")!).ToArray();
var rows=new List<object>();
try
{
    foreach(bool readback in new[]{false,true})foreach(int dependencies in new[]{0,1,2,8,32})
    {
        var actions=types.Select(t=>(Action)t.GetMethod("CreateOperation")!.Invoke(null,new object[]{dependencies,readback})!).ToArray();
        foreach(var action in actions)for(int n=0;n<3000;n++)action();
        var samples=new[]{new List<double>(),new List<double>()};
        var noGcStarted=new[]{new List<bool>(),new List<bool>()};
        var noGcCompleted=new[]{new List<bool>(),new List<bool>()};
        for(int pair=0;pair<9;pair++)for(int slot=0;slot<2;slot++)
        {
            int variant=(pair+slot)%2;Action action=actions[variant];
            bool noGc=false, completed=false;
            try
            {
                noGc=GC.TryStartNoGCRegion(16*1024*1024,disallowFullBlockingGC:true);
                long start=Stopwatch.GetTimestamp();
                for(int n=0;n<10000;n++)action();
                samples[variant].Add((Stopwatch.GetTimestamp()-start)*1_000_000_000.0/Stopwatch.Frequency/10000);
            }
            finally { if(noGc)try{GC.EndNoGCRegion();completed=true;}catch(InvalidOperationException){} }
            noGcStarted[variant].Add(noGc);noGcCompleted[variant].Add(completed);
        }
        double Median(List<double> values){var sorted=values.Order().ToArray();return sorted[sorted.Length/2];}
        rows.Add(new{readback,dependencies,controlNs=Median(samples[0]),candidateNs=Median(samples[1]),controlSamples=samples[0],candidateSamples=samples[1],controlNoGcStarted=noGcStarted[0],candidateNoGcStarted=noGcStarted[1],controlNoGcCompleted=noGcCompleted[0],candidateNoGcCompleted=noGcCompleted[1]});
    }
    Console.WriteLine(JsonSerializer.Serialize(new{rows,pairedInSameProcess=true,pairs=9,delegatesCreatedBeforeMeasurement=true,noGcRequestedOnlyWithinHostProbe=true}));
}
finally{foreach(var type in types)type.GetMethod("CleanupOperations")!.Invoke(null,null);foreach(var context in contexts)context.Unload();}

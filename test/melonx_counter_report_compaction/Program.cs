using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Gpu.Memory;

sealed class ProbeException : Exception { }
sealed class Counter : ICounterEvent
{
    public bool Invalid { get; set; }
    public Action OnFlush;
    public bool ReserveForHostAccess() => false;
    public void Flush() => OnFlush?.Invoke();
    public void Dispose() { }
}
static class Program
{
    static int checks;
    static void Check(bool ok, string detail) { checks++; if (!ok) throw new Exception(detail); }
    static List<string> trace = new();
    static int[] releases;
    static DeferredCounterReport Add(CounterCache cache, int id, Action publish = null, bool ready = true)
    {
        var report = new DeferredCounterReport(value => { trace.Add("publish:" + id + ":" + value); publish?.Invoke(); },
            () => { releases[id]++; trace.Add("release:" + id); });
        report.Attach(new Counter { OnFlush = () => report.Complete(null, (ulong)(id + 100)) });
        if (ready) report.Complete(null, (ulong)(id + 100));
        cache.AddOrUpdate((ulong)(id * 32), report);
        return report;
    }
    static void Throws(Action action)
    { try { action(); } catch (ProbeException) { checks++; return; } throw new Exception("expected native/publication error"); }
    static object Scenario(int which)
    {
        trace = new(); releases = new int[8192];
        var cache = new CounterCache();
        switch (which)
        {
            case 0:
                cache.FlushPendingReports(); Check(!cache.HasPendingReports, "empty"); break;
            case 1:
                for (int i = 0; i < 4096; i++) Add(cache, i);
                cache.FlushPendingReports();
                for (int i = 0; i < 4096; i++) Check(releases[i] == 1, "batch release");
                Check(trace.Where(x => x.StartsWith("publish:")).Select(x => int.Parse(x.Split(':')[1])).SequenceEqual(Enumerable.Range(0,4096)), "publication order");
                cache.FlushPendingReports(); Check(trace.Count == 8192, "completed report is not repeated"); break;
            case 2:
            {
                var report = Add(cache,0); cache.AddOrUpdate(32,report);
                Check(cache.PendingReportCount == 2,"duplicate identity setup");
                cache.FlushPendingReports(); Check(releases[0] == 1,"duplicate releases once"); break;
            }
            case 3:
                Add(cache,0,() => Add(cache,2)); Add(cache,1);
                cache.FlushPendingReports(); Check(cache.PendingReportCount == 1 && releases[2] == 0,"callback append retained");
                cache.FlushPendingReports(); Check(releases[2] == 1,"appended report subsequently published"); break;
            case 4:
            {
                bool once = true;
                Add(cache,0,() => { if (once) { once=false; cache.FlushPendingReports(); Add(cache,3); } });
                Add(cache,1); Add(cache,2);
                cache.FlushPendingReports(); Check(cache.PendingReportCount == 1 && releases[3] == 0,"reentrant drain does not remove appended work");
                cache.FlushPendingReports(); Check(releases.Take(4).All(n => n == 1),"reentrant release ownership"); break;
            }
            case 5:
                Add(cache,0,cache.CancelPendingReports); Add(cache,1); Add(cache,2);
                cache.FlushPendingReports(); Check(releases.Take(3).All(n => n==1),"cancel releases all exactly once");
                Check(trace.Count(x => x.StartsWith("publish:"))==1,"cancel prevents remaining writes"); break;
            case 6:
            {
                Add(cache,0,() => throw new ProbeException()); Add(cache,1);
                Throws(cache.FlushPendingReports); Check(cache.PendingReportCount==2 && releases[0]==1 && releases[1]==0,"failed publication cleanup ownership");
                cache.FlushPendingReports(); Check(releases[0]==1 && releases[1]==1,"publication failure retry"); break;
            }
            case 7:
            {
                var report=Add(cache,0,ready:false); Add(cache,1);
                report.Attach(new Counter {OnFlush=() => throw new ProbeException()});
                Throws(cache.FlushPendingReports); Check(cache.PendingReportCount==2 && releases[0]==0,"wait failure preserves ownership");
                report.Attach(new Counter {OnFlush=() => report.Complete(null,100)});
                cache.FlushPendingReports(); Check(releases[0]==1 && releases[1]==1,"wait retry"); break;
            }
            case 8:
            case 9:
            {
                using var entered=new ManualResetEventSlim(); using var resume=new ManualResetEventSlim();
                var report=Add(cache,0,ready:false); Add(cache,1);
                report.Attach(new Counter {OnFlush=() => { entered.Set(); if(!resume.Wait(5000))throw new Exception("native wait timeout"); report.Complete(null,100); }});
                Task drain=Task.Run(cache.FlushPendingReports);
                Check(entered.Wait(5000),"wait entered outside cache gate");
                if(which==8)cache.CancelPendingReports();else Add(cache,2);
                resume.Set(); Check(drain.Wait(5000),"drain joined");
                if(which==8) Check(trace.Count(x=>x.StartsWith("publish:"))==0,"concurrent cancellation suppresses writes");
                else Check(cache.PendingReportCount==1 && releases[2]==0,"concurrent append survives prefix cleanup");
                cache.FlushPendingReports(); break;
            }
            case 10:
            {
                using var entered=new ManualResetEventSlim(); using var resume=new ManualResetEventSlim(); int visits=0;
                Add(cache,0,() => { if(Interlocked.Increment(ref visits)==1){ entered.Set(); if(!resume.Wait(5000))throw new Exception("publish timeout"); }});
                Add(cache,1);
                Task outer=Task.Run(cache.FlushPendingReports); Check(entered.Wait(5000),"outer publication entered");
                cache.FlushPendingReports(); Add(cache,2); resume.Set(); Check(outer.Wait(5000),"overlapping drain joined");
                Check(cache.PendingReportCount==1 && releases[2]==0,"changed-prefix fallback retained later report");
                cache.FlushPendingReports(); Check(releases.Take(3).All(n=>n==1),"overlapping drains release once"); break;
            }
            case 11:
                Add(cache,0); Add(cache,1); Check(cache.FindAndFlush(0),"first-address individual flush");
                cache.FlushPendingReports(); Check(releases[0]==1 && releases[1]==1,"individual flush + batch"); break;
            default:
            {
                var random=new Random(which); int id=0;
                for(int i=0;i<250;i++)
                {
                    switch(random.Next(4))
                    {
                        case 0: case 1: Add(cache,id++); break;
                        case 2: cache.FlushPendingReports(); break;
                        case 3: cache.CancelPendingReports(); break;
                    }
                    Check(cache.HasPendingReports==(cache.PendingReportCount!=0),"random pending agreement");
                }
                cache.FlushPendingReports();
                for(int i=0;i<id;i++)Check(releases[i]==1,"random ownership"); break;
            }
        }
        Check(cache.PendingReportCount==0 && !cache.HasPendingReports,"all drained at scenario end");
        return new {which, trace=trace.ToArray()};
    }
    static object Cost(int count)
    {
        var durations=new List<double>(); var allocations=new List<long>();
        for(int repetition=0;repetition<15;repetition++)
        {
            trace=new();releases=new int[8192];var cache=new CounterCache();
            for(int i=0;i<count;i++)
            {
                var report=new DeferredCounterReport(_=>{},()=>{});report.Complete(null,1);cache.AddOrUpdate((ulong)(i*32),report);
            }
            long before=GC.GetAllocatedBytesForCurrentThread(), start=Stopwatch.GetTimestamp();
            cache.FlushPendingReports();
            long end=Stopwatch.GetTimestamp(), allocated=GC.GetAllocatedBytesForCurrentThread()-before;
            if(repetition>=5){durations.Add((end-start)*1_000_000_000.0/Stopwatch.Frequency);allocations.Add(allocated);}
            Check(cache.PendingReportCount==0,"cost run drains");
        }
        durations.Sort();allocations.Sort();
        return new{count,medianNanoseconds=durations[durations.Count/2],allocatedBytes=allocations[allocations.Count/2]};
    }
    static void Main()
    {
#if INSTRUMENTED_CANDIDATE
        Ryujinx.Common.EmbeddedPerformanceDiagnostics.Start(1);
#endif
        var scenarios=Enumerable.Range(0,28).Select(Scenario).ToArray();
        var costs=new[]{0,64,1024,4096}.Select(Cost).ToArray();
#if INSTRUMENTED_CANDIDATE
        Ryujinx.Common.EmbeddedPerformanceDiagnostics.Stop(1);
#endif
        Console.WriteLine(JsonSerializer.Serialize(new{checks,scenarios,costs}));
    }
}

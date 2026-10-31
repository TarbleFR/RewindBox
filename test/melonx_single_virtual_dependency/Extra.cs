using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Ryujinx.Graphics.Gpu.Memory;
using Ryujinx.Memory.Range;

static partial class Program
{
    static readonly List<Fixture> costFixtures = new();
    public static Action CreateOperation(int dependencies, bool readback)
    {
#if INSTRUMENTED_CANDIDATE
        Ryujinx.Common.EmbeddedPerformanceDiagnostics.Start(1);
#endif
        var f = new Fixture(128); costFixtures.Add(f);
        for(int n=0;n<dependencies;n++)f.Add(128,(byte)(21+n));
        f.Context.Renderer.Pipeline.RecordCopies=false;
        return readback ? () => f.Flush(0,128) : () => f.Physical.CopyFromDependantVirtualBuffers();
    }
    public static void CleanupOperations()
    {
        foreach(var f in costFixtures)f.Dispose(); costFixtures.Clear();
#if INSTRUMENTED_CANDIDATE
        Ryujinx.Common.EmbeddedPerformanceDiagnostics.Stop(1);
#endif
    }
    static void SingleDependencyCases()
    {
#if INSTRUMENTED_CANDIDATE
        Ryujinx.Common.EmbeddedPerformanceDiagnostics.Start(1);
#endif
        // A callback can change the dependency set on the GPU-owned path. Both
        // old OrderBy snapshot and candidate captured reference keep this call
        // independent from work appended for the next call.
        foreach(int mutation in new[]{0,1,2})
        {
            using var f=new Fixture(64);var a=f.Add(64,31);MultiRangeBuffer later=null;
            a.AddModifiedRegion(new MultiRange(Fixture.Address,64),1);
            bool once=true;
            f.Context.Renderer.Pipeline.BeforeCopy=()=>
            {
                if(!once)return;once=false;
                if(mutation!=0)f.Physical.RemoveVirtualDependency(a);
                if(mutation!=1){later=f.Add(64,42);later.AddModifiedRegion(new MultiRange(Fixture.Address,64),2);}
            };
            f.Physical.CopyFromDependantVirtualBuffers();
            Check.That(f.Context.Renderer.Pipeline.Copies.Count==1,"one captured dependency consumed despite callback mutation");
            Check.Bytes(f.Context.Renderer.Bytes(f.Physical.Handle),Enumerable.Repeat((byte)31,64).ToArray(),"captured original owns callback data");
            f.Context.Renderer.Pipeline.BeforeCopy=null;
            f.Physical.CopyFromDependantVirtualBuffers();
            Check.That(f.Context.Renderer.Pipeline.Copies.Count==(later==null?1:2),"next invocation sees current dependency set");
            Check.Bytes(f.Context.Renderer.Bytes(f.Physical.Handle),Enumerable.Repeat((byte)(later==null?31:42),64).ToArray(),"later dirty dependency remains available");
        }
        foreach(bool readback in new[]{false,true})
        {
            using var f=new Fixture(64);var a=f.Add(64,31);
            a.AddModifiedRegion(new MultiRange(Fixture.Address,64),1);bool once=true;
            f.Context.Renderer.Pipeline.BeforeCopy=()=>{if(once){once=false;f.Physical.CopyFromDependantVirtualBuffers();}};
            if(readback)f.Flush(0,64);else f.Physical.CopyFromDependantVirtualBuffers();
            var copies=f.Context.Renderer.Pipeline.Copies;
            Check.That(copies.Count==2 && copies[0].source==a.Handle && copies[1].source==a.Handle,
                "single callback reentry preserves existing nested then outer copy ordering");
            Check.Bytes(f.Context.Renderer.Bytes(f.Physical.Handle),Enumerable.Repeat((byte)31,64).ToArray(),"single callback reentry retains source");
            Check.That(f.Context.Renderer.ActiveReads==0,"nested readback leases released");
        }
        foreach(bool readback in new[]{false,true})
        {
            using var f=new Fixture(64);var a=f.Add(64,31);
            a.AddModifiedRegion(new MultiRange(Fixture.Address,64),1);f.Context.Renderer.Pipeline.FailNextCopy=true;
            Check.Throws(()=>{if(readback)f.Flush(0,64);else f.Physical.CopyFromDependantVirtualBuffers();});
            Check.That(f.Context.Renderer.ActiveReads==0,"exception releases readback lease");
            a.AddModifiedRegion(new MultiRange(Fixture.Address,64),2);
            if(readback)f.Flush(0,64);else f.Physical.CopyFromDependantVirtualBuffers();
            Check.Bytes(f.Context.Renderer.Bytes(f.Physical.Handle),Enumerable.Repeat((byte)31,64).ToArray(),"subsequent dirty data can retry");
        }
        // Readback retains its existing read lock: upgrading to a writer from
        // that callback is still rejected instead of silently changing safety.
        {
            using var f=new Fixture(64);var a=f.Add(64,31);a.AddModifiedRegion(new MultiRange(Fixture.Address,64),1);
            f.Context.Renderer.Pipeline.BeforeCopy=()=>f.Physical.RemoveVirtualDependency(a);
            bool rejected=false;try{f.Flush(0,64);}catch(LockRecursionException){rejected=true;}
            Check.That(rejected,"readback read-to-write upgrade remains rejected");
            Check.That(f.Context.Renderer.ActiveReads==0,"read lock failure releases backend lease");
        }
        // A foreign writer must remain blocked while the readback owns the set.
        {
            using var f=new Fixture(64);var a=f.Add(64,31);a.AddModifiedRegion(new MultiRange(Fixture.Address,64),1);
            using var entered=new ManualResetEventSlim();using var release=new ManualResetEventSlim();
            f.Context.Renderer.Pipeline.BeforeCopy=()=>{entered.Set();if(!release.Wait(5000))throw new Exception("readback gate timeout");};
            Task reader=Task.Run(()=>f.Flush(0,64));Check.That(entered.Wait(5000),"readback callback entered");
            using var started=new ManualResetEventSlim();Task writer=Task.Run(()=>{started.Set();f.Physical.RemoveVirtualDependency(a);});
            Check.That(started.Wait(5000),"writer attempted");Check.That(!writer.Wait(50),"writer excluded by readback lock");
            release.Set();Check.That(reader.Wait(5000)&&writer.Wait(5000),"reader and writer complete");
            Check.That(f.Context.Renderer.ActiveReads==0,"concurrent readback releases lease");
        }
    }
}

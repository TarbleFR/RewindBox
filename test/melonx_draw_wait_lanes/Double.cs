// Doubles for melonx_draw_wait_lanes_test.py. The real BackgroundCompilationScheduler.cs and the real GAL ProgramQueue.cs
// are compiled whole with these; a pipeline compile is a timed sleep on the scheduler's own threads.
using System;
using System.Threading;

namespace Silk.NET.Vulkan { struct PipelineCache { public int Index; } }

namespace Ryujinx.Graphics.GAL
{
    enum ProgramLinkStatus { Incomplete, Success, Failure }

    interface IProgram
    {
        ProgramLinkStatus CheckProgramLink(bool blocking);
    }

    interface IRenderer { }
}

namespace Ryujinx.Graphics.GAL.Multithreading
{
    // The demand thread raises its own QoS on Apple platforms; nothing to model on the host.
    static class HostThreadQos
    {
        public static void RaiseCurrentThread() { }
    }
}

namespace Ryujinx.Graphics.GAL.Multithreading.Resources
{
    class ThreadedProgram
    {
        public IProgram Base;
        internal bool Compiled;
        internal int Published;

        internal void PublishLinkStatus(ProgramLinkStatus status, bool queuedCheck)
        {
            Published++;
        }
    }
}

namespace Ryujinx.Graphics.GAL.Multithreading.Resources.Programs
{
    interface IProgramRequest
    {
        ThreadedProgram Threaded { get; set; }
        IProgram Create(IRenderer renderer);
    }
}

namespace Ryujinx.Graphics.Vulkan
{
    class PipelineCacheManager
    {
        public int Notified;

        public Silk.NET.Vulkan.PipelineCache GetWorkerCache(int index) => new() { Index = index };

        public void NotifyWorkerPipelineCreated(int index)
        {
            Interlocked.Increment(ref Notified);
        }
    }
}

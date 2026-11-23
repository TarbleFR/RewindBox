// Doubles for test/melonx_unblocked_sync_queries_test.py. The production SyncManager, MultiFenceHolder, FenceHolder,
// FenceHelper, CommandBufferPool, CommandBufferScoped, BufferUsageBitmap, BitMap, VulkanException, ObjectPool, SpanOwner
// and the GAL SyncMap are compiled from the prepared tree; what they call into is doubled here:
// - Silk.NET.Vulkan: the Vk entry points those files use, backed by GpuModel: fences created, polled, waited (with the
//   timeout semantics of vkWaitForFences), command buffers recorded and submitted; a GPU thread executes the submitted
//   command buffers in submission order, each for the GPU time recorded into it, then signals its fence. vkQueueSubmit
//   spends CPU time on the submitting thread per recorded item, as MoltenVK encodes a command buffer at submission.
// - VulkanRenderer: the members SyncManager uses, with FlushAllCommands modelled on PipelineFull.SubmitCommands (end the
//   render pass, return and rent the command buffer through the real pool, register the flush).
// - RenderStageTimer, Logger, IAuto, and the GAL ThreadedRenderer members SyncMap uses.
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.CompilerServices;
using System.Threading;

namespace Ryujinx.Common.Logging
{
    enum LogClass { Gpu }

    sealed class LogTarget
    {
        public readonly ConcurrentQueue<string> Lines = new();
        public void PrintMsg(LogClass kind, string text) => Lines.Enqueue(text);
        public void Print(LogClass kind, string text, [CallerMemberName] string caller = "") => Lines.Enqueue(caller + ": " + text);
    }

    static class Logger
    {
        public static LogTarget Error = new();
        public static LogTarget Warning = new();
    }
}

namespace Ryujinx.Graphics.GAL.Multithreading
{
    sealed class ThreadedRenderer
    {
        private readonly ManualResetEvent _failure = new(false);
        public WaitHandle FailureWaitHandle => _failure;
        public void ThrowIfFailed() { }
    }
}

namespace Silk.NET.Vulkan
{
    public enum Result { Success = 0, NotReady = 1, Timeout = 2, ErrorDeviceLost = -4 }
    public enum StructureType { SubmitInfo = 4, FenceCreateInfo = 8, CommandPoolCreateInfo = 39, CommandBufferAllocateInfo = 40, CommandBufferBeginInfo = 42 }
    public enum CommandBufferLevel { Primary = 0 }
    [Flags] public enum CommandPoolCreateFlags { None = 0, TransientBit = 1, ResetCommandBufferBit = 2 }
    [Flags] public enum PipelineStageFlags { None = 0 }
    public struct Device { public nint Handle; }
    public struct Queue { public nint Handle; }
    public struct Fence { public ulong Handle; }
    public struct CommandPool { public ulong Handle; }
    public struct CommandBuffer { public nint Handle; }
    public struct Semaphore { public ulong Handle; }
    public struct AllocationCallbacks { }
    public struct FenceCreateInfo { public StructureType SType; }
    public struct CommandBufferAllocateInfo { public StructureType SType; public uint CommandBufferCount; public CommandPool CommandPool; public CommandBufferLevel Level; }
    public struct CommandPoolCreateInfo { public StructureType SType; public uint QueueFamilyIndex; public CommandPoolCreateFlags Flags; }
    public struct CommandBufferBeginInfo { public StructureType SType; }

    public unsafe struct SubmitInfo
    {
        public StructureType SType;
        public uint WaitSemaphoreCount;
        public Semaphore* PWaitSemaphores;
        public PipelineStageFlags* PWaitDstStageMask;
        public uint CommandBufferCount;
        public CommandBuffer* PCommandBuffers;
        public uint SignalSemaphoreCount;
        public Semaphore* PSignalSemaphores;
    }

    /// <summary>The Vulkan entry points the compiled production files use, answered by the GPU model.</summary>
    public unsafe sealed class Vk
    {
        public readonly GpuModel Gpu;
        public Vk(GpuModel gpu) { Gpu = gpu; }

        public Result CreateFence(Device device, in FenceCreateInfo info, AllocationCallbacks* allocator, out Fence fence)
        {
            fence = new Fence { Handle = Gpu.CreateFence() };
            return Result.Success;
        }

        public void DestroyFence(Device device, Fence fence, Span<AllocationCallbacks> allocator) => Gpu.DestroyFence(fence.Handle);
        public Result GetFenceStatus(Device device, Fence fence) => Gpu.IsSignalled(fence.Handle) ? Result.Success : Result.NotReady;
        public Result WaitForFences(Device device, uint fenceCount, ReadOnlySpan<Fence> fences, bool waitAll, ulong timeout) =>
            Gpu.WaitForFences(fences, waitAll, timeout);

        public Result AllocateCommandBuffers(Device device, in CommandBufferAllocateInfo info, out CommandBuffer commandBuffer)
        {
            commandBuffer = new CommandBuffer { Handle = Gpu.AllocateCommandBuffer() };
            return Result.Success;
        }

        public Result CreateCommandPool(Device device, in CommandPoolCreateInfo info, AllocationCallbacks* allocator, out CommandPool pool)
        {
            pool = new CommandPool { Handle = 1 };
            return Result.Success;
        }

        public void DestroyCommandPool(Device device, CommandPool pool, AllocationCallbacks* allocator) { }
        public Result BeginCommandBuffer(CommandBuffer commandBuffer, in CommandBufferBeginInfo info) { Gpu.Begin(commandBuffer.Handle); return Result.Success; }
        public Result EndCommandBuffer(CommandBuffer commandBuffer) => Result.Success;

        public Result QueueSubmit(Queue queue, uint submitCount, in SubmitInfo info, Fence fence)
        {
            Gpu.Submit(info.PCommandBuffers[0].Handle, fence.Handle);
            return Result.Success;
        }
    }

    /// <summary>
    /// The GPU and the driver: fences, command buffer recording, in-order execution with the recorded GPU time, and the
    /// submission's CPU cost on the submitting thread. Manual: no GPU thread, CompleteNext executes the oldest submission.
    /// </summary>
    public sealed class GpuModel
    {
        private readonly object _gate = new();
        private readonly Dictionary<ulong, bool> _fences = new();
        private readonly Dictionary<nint, (long Ticks, long MaxSeq, int Items)> _recording = new();
        private readonly Queue<(ulong Fence, long Ticks, long MaxSeq, long SubmittedAt)> _submitted = new();
        private ulong _nextFence = 1;
        private long _nextCommandBuffer = 0x1000;
        private Thread _thread;
        private bool _running;
        public readonly bool Manual;
        public double EncodeMicrosPerItem;
        public long FencesCreated, FencesDestroyed, Submits, SubmittedItems, Polls, Waits, WaitsInProgress, BusyTicks, IdleTicks;
        public long RecordedSeq, CompletedSeq;

        public GpuModel(bool manual)
        {
            Manual = manual;

            if (!manual)
            {
                _running = true;
                _thread = new Thread(Run) { Name = "Model GPU", IsBackground = true };
                _thread.Start();
            }
        }

        public void Stop()
        {
            lock (_gate)
            {
                _running = false;
                Monitor.PulseAll(_gate);
            }

            _thread?.Join();
        }

        public ulong CreateFence()
        {
            lock (_gate)
            {
                FencesCreated++;
                ulong handle = _nextFence++;
                _fences[handle] = false;
                return handle;
            }
        }

        public void DestroyFence(ulong handle)
        {
            lock (_gate)
            {
                FencesDestroyed++;
            }
        }

        public bool IsSignalled(ulong handle)
        {
            Interlocked.Increment(ref Polls);

            lock (_gate)
            {
                return _fences[handle];
            }
        }

        public Result WaitForFences(ReadOnlySpan<Silk.NET.Vulkan.Fence> fences, bool waitAll, ulong timeout)
        {
            ulong[] handles = new ulong[fences.Length];

            for (int i = 0; i < handles.Length; i++)
            {
                handles[i] = fences[i].Handle;
            }

            Interlocked.Increment(ref Waits);
            long deadline = Stopwatch.GetTimestamp() + (long)Math.Min(timeout / 1_000_000_000.0 * Stopwatch.Frequency, long.MaxValue / 4);
            Interlocked.Increment(ref WaitsInProgress);

            try
            {
                lock (_gate)
                {
                    while (true)
                    {
                        int signalled = 0;

                        foreach (ulong handle in handles)
                        {
                            signalled += _fences[handle] ? 1 : 0;
                        }

                        if (waitAll ? signalled == handles.Length : signalled > 0)
                        {
                            return Result.Success;
                        }

                        long left = deadline - Stopwatch.GetTimestamp();

                        if (timeout == 0 || left <= 0)
                        {
                            return Result.Timeout;
                        }

                        Monitor.Wait(_gate, TimeSpan.FromSeconds(Math.Min(left, Stopwatch.Frequency) / (double)Stopwatch.Frequency));
                    }
                }
            }
            finally
            {
                Interlocked.Decrement(ref WaitsInProgress);
            }
        }

        public nint AllocateCommandBuffer() => (nint)Interlocked.Increment(ref _nextCommandBuffer);

        public void Begin(nint commandBuffer)
        {
            lock (_gate)
            {
                _recording[commandBuffer] = (0, 0, 0);
            }
        }

        /// <summary>Records GPU work into a command buffer (the render thread's draws). Returns the work's sequence number.</summary>
        public long Record(nint commandBuffer, double gpuMicros)
        {
            lock (_gate)
            {
                (long ticks, long _, int items) = _recording.TryGetValue(commandBuffer, out var current) ? current : (0, 0, 0);
                long seq = ++RecordedSeq;
                _recording[commandBuffer] = (ticks + (long)(gpuMicros * Stopwatch.Frequency / 1e6), seq, items + 1);
                return seq;
            }
        }

        public long Recorded { get { lock (_gate) { return RecordedSeq; } } }
        public long Completed { get { lock (_gate) { return CompletedSeq; } } }
        public int Pending { get { lock (_gate) { return _submitted.Count; } } }

        public void Submit(nint commandBuffer, ulong fence)
        {
            (long Ticks, long MaxSeq, int Items) work;

            lock (_gate)
            {
                work = _recording.TryGetValue(commandBuffer, out var current) ? current : (0, 0, 0);
                _recording[commandBuffer] = (0, 0, 0);
            }

            // MoltenVK encodes the Vulkan command buffer into a Metal one at vkQueueSubmit, on the submitting thread.
            Spin.For(EncodeMicrosPerItem * work.Items);

            lock (_gate)
            {
                Submits++;
                SubmittedItems += work.Items;
                _submitted.Enqueue((fence, work.Ticks, work.MaxSeq, Stopwatch.GetTimestamp()));
                Monitor.PulseAll(_gate);
            }
        }

        /// <summary>Manual mode: executes the oldest submission now. False when none is queued.</summary>
        public bool CompleteNext()
        {
            lock (_gate)
            {
                if (_submitted.Count == 0)
                {
                    return false;
                }

                var next = _submitted.Dequeue();
                CompletedSeq = Math.Max(CompletedSeq, next.MaxSeq);
                _fences[next.Fence] = true;
                Monitor.PulseAll(_gate);
                return true;
            }
        }

        private void Run()
        {
            long idleSince = Stopwatch.GetTimestamp();

            while (true)
            {
                (ulong Fence, long Ticks, long MaxSeq, long SubmittedAt) next;

                lock (_gate)
                {
                    while (_running && _submitted.Count == 0)
                    {
                        Monitor.Wait(_gate);
                    }

                    if (!_running)
                    {
                        return;
                    }

                    next = _submitted.Peek();
                }

                long start = Stopwatch.GetTimestamp();
                IdleTicks += start - idleSince;
                Spin.Until(start + next.Ticks);
                long end = Stopwatch.GetTimestamp();
                BusyTicks += end - start;
                idleSince = end;

                lock (_gate)
                {
                    _submitted.Dequeue();
                    CompletedSeq = Math.Max(CompletedSeq, next.MaxSeq);
                    _fences[next.Fence] = true;
                    Monitor.PulseAll(_gate);
                }
            }
        }
    }

    /// <summary>Time spent on the calling thread: sleeps for the bulk of a long interval, spins the rest.</summary>
    public static class Spin
    {
        public static void For(double micros)
        {
            if (micros > 0)
            {
                Until(Stopwatch.GetTimestamp() + (long)(micros * Stopwatch.Frequency / 1e6));
            }
        }

        public static void Until(long deadline)
        {
            while (true)
            {
                long left = deadline - Stopwatch.GetTimestamp();

                if (left <= 0)
                {
                    return;
                }

                if (left > Stopwatch.Frequency * 3 / 1000)
                {
                    Thread.Sleep((int)(left * 1000 / Stopwatch.Frequency) - 2);
                }
                else if (left > Stopwatch.Frequency / 2000)
                {
                    Thread.Yield();
                }
                else
                {
                    Thread.SpinWait(20);
                }
            }
        }
    }
}

namespace Ryujinx.Graphics.Vulkan
{
    using Silk.NET.Vulkan;

    interface IAuto
    {
        bool HasCommandBufferDependency(CommandBufferScoped cbs);
        void IncrementReferenceCount();
        void DecrementReferenceCount(int cbIndex);
        void DecrementReferenceCount();
        void ReleaseCommandBufferOwnership(int cbIndex);
    }

    // Counting double of the production RenderStageTimer's submission counters (their gate is submit-causes).
    static class RenderStageTimer
    {
        public enum SubmitCause { Other, StrictSync, SyncWait, DrawAutoFlush, AttachmentAutoFlush, Query, DisposedWeight, BufferRead,
            TextureRead, StagingFull, Helper, Present, Count }
        public static SubmitCause NextSubmitCause;
        public static long SubmittingSyncs, WaitingSyncs;
    }

    /// <summary>
    /// The renderer members SyncManager uses. FlushAllCommands follows PipelineFull.SubmitCommands: the render pass ends,
    /// the command buffer is returned (submitted) and a new one rented through the production pool, then the flush is
    /// registered with the sync manager (VulkanRenderer.RegisterFlush). A render pass begun again on the framebuffer the
    /// last one ended on is counted as PipelineBase counts "same framebuffer again".
    /// </summary>
    sealed class VulkanRenderer
    {
        public readonly Vk Api;
        public readonly GpuModel Gpu;
        public readonly CommandBufferPool CommandBufferPool;
        public Action<Action> InterruptAction;
        public SyncManager SyncManager;
        public CommandBufferScoped Cbs;
        public long Flushes, PassBegins, PassResumes, DrawsSinceFlush;
        public long LastFlushTicks = Stopwatch.GetTimestamp();
        public readonly long[] FlushesByCause = new long[(int)RenderStageTimer.SubmitCause.Count];
        private int _framebuffer = -1, _lastEnded = -1;
        private bool _passActive;

        public VulkanRenderer(GpuModel gpu)
        {
            Gpu = gpu;
            Api = new Vk(gpu);
            CommandBufferPool = new CommandBufferPool(Api, default, default, new Lock(), 0, false);
            Cbs = CommandBufferPool.Rent();
            SyncManager = new SyncManager(this, default);
        }

        public void FlushAllCommands()
        {
            EndPass();
            FlushesByCause[(int)RenderStageTimer.NextSubmitCause]++;
            RenderStageTimer.NextSubmitCause = RenderStageTimer.SubmitCause.Other;
            Cbs = CommandBufferPool.ReturnAndRent(Cbs);
            SyncManager.RegisterFlush();
            Flushes++;
            DrawsSinceFlush = 0;
            LastFlushTicks = Stopwatch.GetTimestamp();
        }

        public void EndPass()
        {
            if (_passActive)
            {
                _passActive = false;
                _lastEnded = _framebuffer;
            }
        }

        /// <summary>A draw on a framebuffer: switches pass when the framebuffer changes, records the GPU work.</summary>
        public long Draw(int framebuffer, double gpuMicros)
        {
            if (framebuffer != _framebuffer)
            {
                EndPass();
                _framebuffer = framebuffer;
            }

            if (!_passActive)
            {
                PassBegins++;
                PassResumes += _framebuffer == _lastEnded ? 1 : 0;
                _passActive = true;
            }

            DrawsSinceFlush++;
            return Gpu.Record(Cbs.CommandBuffer.Handle, gpuMicros);
        }
    }
}

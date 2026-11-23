using System;
using System.Collections.Generic;
namespace Silk.NET.Vulkan { class Vk { } struct Device { } }
namespace Ryujinx.Common.Logging
{
    enum LogClass { Gpu }
    sealed class LogTarget
    {
        public int Errors;
        public void PrintMsg(LogClass kind, string text) { Errors++; }
        // adapt_unblocked_sync_queries: the sync manager's 5 s journal line (Logger.Warning?.Print).
        public void Print(LogClass kind, string text, [System.Runtime.CompilerServices.CallerMemberName] string caller = "") { }
    }
    static class Logger { public static LogTarget Error = new(); public static LogTarget Warning = new(); }
}
namespace Ryujinx.Graphics.GAL.Multithreading
{
    // adapt_unblocked_sync_queries: the GAL counter of waits for a sync not created yet, read by the journal line.
    static class SyncAvailabilityWaits { public static void Take(out long calls, out long ticks, out long longest) { calls = ticks = longest = 0; } }
}
namespace Ryujinx.Graphics.Vulkan
{
    sealed class FakePool
    {
        public int Returns;
        public void Release(object[] value)
        {
            foreach (var item in value) if (item != null) throw new Exception("Fence array returned uncleared");
            Returns++;
        }
    }
    sealed class MultiFenceHolder
    {
        public static readonly FakePool FencePool = new();
        public readonly object[] Fences = new object[16];
        public bool Signaled;
        public int Waits;
        public Action OnWait;
        public bool WaitForFences(Silk.NET.Vulkan.Vk api, Silk.NET.Vulkan.Device device, ulong timeout)
        {
            Waits++; OnWait?.Invoke(); return Signaled;
        }
    }
    sealed class CommandBufferPool
    {
        public const int MaxCommandBuffers = 16;
        public readonly List<MultiFenceHolder> Added = new();
        public int Strict, Relaxed;
        public void AddWaitable(MultiFenceHolder holder) { Strict++; Added.Add(holder); holder.Fences[0] = this; }
        public void AddInUseWaitable(MultiFenceHolder holder) { Relaxed++; Added.Add(holder); holder.Fences[0] = this; }
    }
    sealed class VulkanRenderer
    {
        public readonly Silk.NET.Vulkan.Vk Api = new();
        public readonly CommandBufferPool CommandBufferPool = new();
        public Action<Action> InterruptAction;
        public Action OnFlush;
        public int Flushes;
        public void FlushAllCommands() { Flushes++; OnFlush?.Invoke(); }
    }
}

// Doubles for melonx_deferred_release_roots_test.py. The real end of VulkanRenderer.Dispose (the device release handed
// to the pipeline cache's loading thread) and, in the candidate, the real VulkanRenderer.DeviceRelease are compiled
// with these doubles. The renderer carries what a closed session keeps reachable through it: its surface callback's
// window and a payload standing for the Switch and the guest's memory.
using System;
using System.Collections.Generic;

namespace Silk.NET.Vulkan
{
    struct Device { public long Handle; }
    unsafe class Vk
    {
        public readonly List<string> Calls;
        public Vk(List<string> calls) { Calls = calls; }
        public void DestroyDevice(Device device, void* allocator) { Calls.Add("device " + device.Handle); }
    }
}
namespace Ryujinx.Graphics.Vulkan
{
    using Silk.NET.Vulkan;

    class VulkanDebugMessenger
    {
        private readonly List<string> _calls;
        public VulkanDebugMessenger(List<string> calls) { _calls = calls; }
        public void Dispose() { _calls.Add("messenger"); }
    }
    class VulkanInstance
    {
        private readonly List<string> _calls;
        public VulkanInstance(List<string> calls) { _calls = calls; }
        public void Dispose() { _calls.Add("instance"); }
    }
    // PipelineCacheManager while MoltenVK still loads the main snapshot: it keeps the action for its loading thread.
    class PipelineCacheManager
    {
        public Action Deferred;
        public bool Loading = true;
        public bool DeferDeviceRelease(Action release)
        {
            if (!Loading) { return false; }
            Deferred = release;
            return true;
        }
    }
    class Session { public readonly byte[] GuestMemory = new byte[8 << 20]; }
    unsafe class VulkanRenderer
    {
        internal Vk Api { get; private set; }
        private Device _device;
        private VulkanDebugMessenger _debugMessenger;
        private VulkanInstance _instance;
        public PipelineCacheManager PipelineCacheManager;
        // The surface callback's closure holds the window, which holds the Switch.
        private readonly Func<Session> _getSurface;
        public VulkanRenderer(List<string> calls, PipelineCacheManager manager, Session session)
        {
            Api = new Vk(calls);
            _device = new Device { Handle = 7 };
            _debugMessenger = new VulkanDebugMessenger(calls);
            _instance = new VulkanInstance(calls);
            PipelineCacheManager = manager;
            _getSurface = () => session;
        }
        public unsafe void DisposeTail()
        {
            /* DISPOSE_TAIL */
        /* RENDERER_METHODS */
    }
}

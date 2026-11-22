"""The device release left to the pipeline cache's loading thread no longer keeps the closed session reachable.

IPA 816-820, 22 November 2026 (private Core journal; counts only). After every close of Super Smash Bros. Ultimate and
of Hogwarts Legacy, "sessionRetention" reads "Switch still reachable 1/1; GpuContext 1/1; Horizon 1/1" and
"retentionChain" reads "renderer 1/1; window 1/1; kernel 1/1; cpuMemory 1/1" after the final collections and again at
the next session's first frame; the managed heap is 468-570 MB at the close and 932-1 273 MB at the next first frame,
and the next session starts with a footprint of 2.3-2.9 GiB instead of about 1.4. The one session that released
everything (title 010038b015560000, 817) is the one whose main pipeline cache finished loading ("primaryReady", 3 s);
in the others the load never completed within the session.

Cause. VulkanRenderer.Dispose hands the destruction of the device and of the instance to the loading thread while
MoltenVK still loads the main snapshot (adapt_pipeline_cache_background: PipelineCacheManager.DeferDeviceRelease). The
action it hands over was a local function of Dispose that reads the renderer's fields, so it captured the renderer;
the loading thread, still running inside the driver, kept that action in the cache manager, hence the renderer, its
surface callback, the window, the Switch and the guest's memory, for as long as the load lasted, across sessions.

Change. The action is built by a static method from the four values it uses (the Vulkan API, the device, the debug
messenger, the instance) and captures nothing else: the same three calls, in the same order, on the same thread as
before. A load that outlives its session keeps the device and the instance until it returns, as designed, and no
longer the session. With the lazy library compilation of MoltenVK (recipe patch, ninth part) the load itself returns
at once; this covers a load that is slow for any other reason. Not measured on an iPhone.
Fail closed on drift: the file must be the preparation after adapt_guest_stop_compile_cancel.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs': '6e7eadf6f370fb124b207c588c3f3cfbf64777ec838af05f337f3b733ada3be3',
}

OLD = '''            // RewindBox (adapt_pipeline_cache_background): while MoltenVK still loads the main snapshot (a cold system Metal
            // cache), the loader thread releases the device and the instance once it returns; the session does not wait.
            void ReleaseDevice()
            {
                Api.DestroyDevice(_device, null);

                _debugMessenger.Dispose();

                // Last step destroy the instance
                _instance.Dispose();
            }

            if (!PipelineCacheManager.DeferDeviceRelease(ReleaseDevice))
            {
                ReleaseDevice();
            }
        }
'''
NEW = '''            // RewindBox (adapt_pipeline_cache_background): while MoltenVK still loads the main snapshot (a cold system Metal
            // cache), the loader thread releases the device and the instance once it returns; the session does not wait.
            // RewindBox (adapt_deferred_release_roots): the action holds the four values it uses, not this renderer.
            Action releaseDevice = DeviceRelease(Api, _device, _debugMessenger, _instance);

            if (!PipelineCacheManager.DeferDeviceRelease(releaseDevice))
            {
                releaseDevice();
            }
        }

        // RewindBox (adapt_deferred_release_roots): static, so the action captures its arguments only. As a local
        // function of Dispose it captured the renderer: the loading thread that keeps the action until MoltenVK returns
        // kept the renderer, its window, the Switch and the guest's memory reachable after the close (IPA 816-820).
        private static unsafe Action DeviceRelease(Vk api, Device device, VulkanDebugMessenger debugMessenger, VulkanInstance instance)
        {
            return () =>
            {
                api.DestroyDevice(device, null);

                debugMessenger.Dispose();

                // Last step destroy the instance
                instance.Dispose();
            };
        }
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    once(paths['src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs'], OLD, NEW)
    return list(paths.values())

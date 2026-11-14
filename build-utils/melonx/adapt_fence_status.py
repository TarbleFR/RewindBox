"""A fence's state is read with vkGetFenceStatus, not with a zero-timeout vkWaitForFences (every title, Vulkan backend).

IPA 736 / Core c4a25b94, Hogwarts Legacy (private journal, pid 2349, five [MeloNX:hot] profiles in the world, 1 080
running samples of the render thread): CommandBufferPool.FreeConsumed 61 samples (5.6 %), of which only 8 in
WaitAndDecrementRef; libsystem_pthread 49 (4.5 %). FreeConsumed runs at every command buffer rented (296 per second
there) and asks whether the oldest submitted command buffer has completed through FenceHolder.IsSignaled, which calls
vkWaitForFences with a timeout of 0. In the MoltenVK the app embeds (MVKSync.mm, mvkWaitForFences), that call builds a
fence sitter, inserts it into the fence's set (a heap node), registers its semaphore in the device-wide list under the
device's _sem4Lock, takes the sitter's own lock, then removes both again: five mutex acquisitions, one of them shared by
every thread that waits on any fence of the device, and an allocation, to read one flag. vkGetFenceStatus reads the
same flag under the fence's lock alone (MVKFence::getIsSignaled).

Change (FenceHolder.cs, MultiFenceHolder.cs): FenceHolder.IsSignaled reads the fence with vkGetFenceStatus (inside the
same spin lock as before where concurrent waits are unsupported); MultiFenceHolder's checks with a timeout of 0 read
each fence the same way and answer false at the first one not ready. A wait with a timeout and the indefinite waits are
unchanged. The answers are the same: VK_SUCCESS is signalled, VK_NOT_READY (VK_TIMEOUT before) is not, any error throws
as FenceHelper does since adapt_runtime.

Expected on the device: CommandBufferPool.FreeConsumed and libsystem_pthread's share of the render thread lower; the
same command buffers recycled. Rollback: drop this adapter from prepare_embedded.py and ORDER.
Not measured on an iPhone. Fail closed on drift.
"""
import hashlib
from adapt_session import once

HOLDER = 'src/Ryujinx.Graphics.Vulkan/FenceHolder.cs'
MULTI = 'src/Ryujinx.Graphics.Vulkan/MultiFenceHolder.cs'
BASELINE = {
    HOLDER: 'a7240d85c36bfd970ff5a61ce8f1d196eb9817d407d260785893b195262baa34',
    MULTI: '5f623fb80fae5bbd529d5a5a98c634390eaf0278f05ea11a6260a6721393c23f',
}

STATUS_OLD = '''        public bool IsSignaled()
        {
            if (_concurrentWaitUnsupported)
            {
                if (!TryAcquireLock())
                {
                    return false;
                }

                try
                {
                    return FenceHelper.AllSignaled(_api, _device, [_fence]);
                }
                finally
                {
                    ReleaseLock();
                }
            }
            else
            {
                return FenceHelper.AllSignaled(_api, _device, [_fence]);
            }
        }
'''
STATUS_NEW = '''        public bool IsSignaled()
        {
            if (_concurrentWaitUnsupported)
            {
                if (!TryAcquireLock())
                {
                    return false;
                }

                try
                {
                    return ReadStatus(_api, _device, _fence);
                }
                finally
                {
                    ReleaseLock();
                }
            }
            else
            {
                return ReadStatus(_api, _device, _fence);
            }
        }

        // RewindBox (adapt_fence_status): the fence's state, as a zero-timeout vkWaitForFences answers it, without the
        // fence sitter MoltenVK builds and registers device-wide for a wait.
        internal static bool ReadStatus(Vk api, Device device, Fence fence)
        {
            Result result = api.GetFenceStatus(device, fence);

            if (result == Result.NotReady)
            {
                return false;
            }

            result.ThrowOnError();

            return true;
        }
'''

CHECK_OLD = '''                if (hasTimeout)
                {
                    signaled = FenceHelper.AllSignaled(api, device, fences[..fenceCount], timeout);
                }
'''
CHECK_NEW = '''                if (hasTimeout && timeout == 0)
                {
                    // RewindBox (adapt_fence_status): a check, not a wait: each fence's state, false at the first one
                    // not ready (what a zero-timeout vkWaitForFences of all of them answers).
                    for (int i = 0; i < fenceCount && signaled; i++)
                    {
                        signaled = FenceHolder.ReadStatus(api, device, fences[i]);
                    }
                }
                else if (hasTimeout)
                {
                    signaled = FenceHelper.AllSignaled(api, device, fences[..fenceCount], timeout);
                }
'''

PAIRS = ((HOLDER, STATUS_OLD, STATUS_NEW), (MULTI, CHECK_OLD, CHECK_NEW))


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, old, new in PAIRS:
        once(paths[name], old, new)
    return list(paths.values())

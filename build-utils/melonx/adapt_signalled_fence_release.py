"""A command buffer whose fence was just read signalled is released without waiting for that fence again (every title).

IPA 740 / Core da2525a1 (adapt_fence_status): CommandBufferPool.FreeConsumed asks whether the oldest submitted command
buffer has completed with FenceHolder.IsSignaled, now a vkGetFenceStatus, and when it has, calls WaitAndDecrementRef,
which began with entry.Fence.Wait(): FenceHelper.WaitAllIndefinitely, a vkWaitForFences looping on a 100 ms timeout, for
a fence that was just read signalled, at each command buffer recycled (about 10 per game frame). In the embedded
MoltenVK (MVKSync.mm) a signalled fence returns early from MVKFence::addSitter (no registration, no allocation); what the
call still costs is about four uncontended mutex pairs, one acquisition of the device's _sem4Lock in removeSitter and a
clock read: a few microseconds per frame, below what the [MeloNX:hot] profiles can attribute (adversarial review of the
740 investigation). Small, kept because it is exact.

Change (CommandBufferPool.cs): WaitAndDecrementRef takes whether the caller saw the fence signalled; FreeConsumed passes
the answer of its IsSignaled, which it only asks when it does not wait anyway. A signalled fence stays signalled: the pool
never resets one (the entry's FenceHolder is disposed and replaced right after). Every other caller (Dispose, the
waiting path of FreeConsumed, the unsignalled ones) waits as before.

Expected on the device: a few microseconds per frame, not visible in the profiles. Not measured on an iPhone. Applied
after adapt_command_buffer_ownership (its post-image). Rollback: drop this adapter from prepare_embedded.py and ORDER.
Fail closed on drift.
"""
import hashlib
from adapt_session import once

POOL = 'src/Ryujinx.Graphics.Vulkan/CommandBufferPool.cs'
BASELINE = {POOL: 'd7534d7c5e15c1181cb1833d6d96e2951b535d3d499faac97d08e6c9a1180101'}

CHECK_OLD = '''                if (wait || !entry.InConsumption || entry.Fence.IsSignaled())
                {
                    WaitAndDecrementRef(index);
'''
CHECK_NEW = '''                // RewindBox (adapt_signalled_fence_release): a fence just read signalled is not waited for again.
                bool signaled = false;

                if (wait || !entry.InConsumption || (signaled = entry.Fence.IsSignaled()))
                {
                    WaitAndDecrementRef(index, signaled: signaled);
'''

WAIT_OLD = '''        private void WaitAndDecrementRef(int cbIndex, bool refreshFence = true)
        {
            ref ReservedCommandBuffer entry = ref _commandBuffers[cbIndex];

            if (entry.InConsumption)
            {
                entry.Fence.Wait();
                entry.InConsumption = false;
            }
'''
WAIT_NEW = '''        private void WaitAndDecrementRef(int cbIndex, bool refreshFence = true, bool signaled = false)
        {
            ref ReservedCommandBuffer entry = ref _commandBuffers[cbIndex];

            if (entry.InConsumption)
            {
                if (!signaled)
                {
                    entry.Fence.Wait();
                }

                entry.InConsumption = false;
            }
'''


def apply(source):
    path = source / POOL
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for _, expected in digests:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, POOL
    once(path, CHECK_OLD, CHECK_NEW)
    once(path, WAIT_OLD, WAIT_NEW)
    return [path]

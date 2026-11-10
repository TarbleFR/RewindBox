"""Release finished kernel-wait references without changing synchronization.

The global waiter-node pool retained each removed node's KThread. A pooled
node could therefore keep a closed kernel/session reachable. Per-thread
WaitSyncObjects likewise retained handles after their native references were
released, and SignaledObj retained the last result after its index was copied.

Clear only after the consumer's last read. Keep list order, duplicate-handle
semantics, cancellation, timeouts and the scheduler unchanged. The syscall's
finally releases only handles actually acquired, then clears its active span.
"""
import hashlib

from adapt_session import once


WAIT_SIGNATURE = '        public Result WaitSynchronization(out int handleIndex, ReadOnlySpan<int> handles, long timeout)'


def apply(source):
    common = source / 'src/Ryujinx.HLE/HOS/Kernel/Common/KSynchronizationObject.cs'
    once(common, '''            WaitingThreads.Remove(node);
            _nodePool.Release(node);
''', '''            WaitingThreads.Remove(node);
            // The process-wide pool must not retain a completed wait's thread.
            node.Value = null;
            _nodePool.Release(node);
''')

    synchronization = source / 'src/Ryujinx.HLE/HOS/Kernel/Threading/KSynchronization.cs'
    once(synchronization, '''                ArrayPool<LinkedListNode<KThread>>.Shared.Return(syncNodesArray, true);
''', '''                // handleIndex now owns the result; do not keep the signaled object alive.
                currentThread.SignaledObj = null;
                ArrayPool<LinkedListNode<KThread>>.Shared.Return(syncNodesArray, true);
''')

    syscall = source / 'src/Ryujinx.HLE/HOS/Kernel/SupervisorCall/Syscall.cs'
    text = syscall.read_text(encoding='utf-8-sig')
    start = text.index(WAIT_SIGNATURE)
    end = text.index('\n        [Svc(0x19)]', start)
    before = text[start:end]
    assert hashlib.sha256(before.encode()).hexdigest() == 'f48cac2706277ff9c55d85895816a987551c25c55f9ec1f4819ba480881c1407', 'Unknown WaitSynchronization body'
    # Exact structural guards keep the cleanup scoped to this overload.
    assert before.count('int processedHandles = 0;') == 1
    assert before.count('currentThread.WaitSyncObjects[index].DecrementReferenceCount();') == 2
    assert before.count('syncObj.IncrementReferenceCount();') == 1
    after = '''        public Result WaitSynchronization(out int handleIndex, ReadOnlySpan<int> handles, long timeout)
        {
            handleIndex = 0;

            if ((uint)handles.Length > KThread.MaxWaitSyncObjects)
            {
                return KernelResult.MaximumExceeded;
            }

            KThread currentThread = KernelStatic.GetCurrentThread();

            Span<KSynchronizationObject> syncObjs = new Span<KSynchronizationObject>(currentThread.WaitSyncObjects)[..handles.Length];
            int processedHandles = 0;

            try
            {
                if (handles.Length != 0)
                {
                    KProcess currentProcess = KernelStatic.GetCurrentProcess();

                    for (; processedHandles < handles.Length; processedHandles++)
                    {
                        KSynchronizationObject syncObj = currentProcess.HandleTable.GetObject<KSynchronizationObject>(handles[processedHandles]);

                        if (syncObj == null)
                        {
                            return KernelResult.InvalidHandle;
                        }

                        syncObjs[processedHandles] = syncObj;

                        syncObj.IncrementReferenceCount();
                    }
                }

                if (timeout > 0)
                {
                    timeout += KTimeManager.DefaultTimeIncrementNanoseconds;
                }

                Result result = _context.Synchronization.WaitFor(syncObjs, timeout, out handleIndex);

                if (result == KernelResult.PortRemoteClosed)
                {
                    result = Result.Success;
                }

                return result;
            }
            finally
            {
                try
                {
                    for (int index = 0; index < processedHandles; index++)
                    {
                        syncObjs[index].DecrementReferenceCount();
                    }
                }
                finally
                {
                    // A shorter later wait must not keep old objects in unused slots.
                    syncObjs.Clear();
                }
            }
        }
'''
    once(syscall, before, after)
    return [common, synchronization, syscall]

"""Keep timer-arm identity in a value instead of allocating an object per arm.

The existing list, lock, deadline arithmetic, earliest-selection order, wake
event and callback code stay in place. A sequence distinguishes two arms for
the same scheduler object/deadline. Its epoch changes only on ulong rollover,
so even a captured cancelled arm cannot remove a later generation on overflow.
The list retains 24 more bytes per slot on 64-bit hosts; repeated arms avoid
the previous 32-byte wrapper allocation after the list's capacity is warm.
"""
from adapt_session import once


def apply(source):
    path = source / 'src/Ryujinx.HLE/HOS/Kernel/Common/KTimeManager.cs'
    once(path, '''        private class WaitingObject
        {
            public IKFutureSchedulerObject Object { get; }
            public long TimePoint { get; }

            public WaitingObject(IKFutureSchedulerObject schedulerObj, long timePoint)
            {
                Object = schedulerObj;
                TimePoint = timePoint;
            }
        }
''', '''        private readonly struct WaitingObject : IEquatable<WaitingObject>
        {
            public IKFutureSchedulerObject Object { get; }
            public long TimePoint { get; }
            private readonly object _epoch;
            private readonly ulong _sequence;

            public bool IsValid => _epoch != null;

            public WaitingObject(IKFutureSchedulerObject schedulerObj, long timePoint, object epoch, ulong sequence)
            {
                Object = schedulerObj;
                TimePoint = timePoint;
                _epoch = epoch;
                _sequence = sequence;
            }

            public bool Equals(WaitingObject other)
            {
                // Preserve the former reference identity across cancellation/rearming.
                return _sequence == other._sequence && ReferenceEquals(_epoch, other._epoch);
            }

            public override bool Equals(object obj) => obj is WaitingObject other && Equals(other);
            public override int GetHashCode() => HashCode.Combine(_epoch, _sequence);
        }
''')
    once(path, '''        private readonly List<WaitingObject> _waitingObjects;
''', '''        private readonly List<WaitingObject> _waitingObjects;
        private object _waitingEpoch = new();
        private ulong _waitingSequence;
''')
    once(path, '''                _waitingObjects.Add(new WaitingObject(schedulerObj, timePoint));
''', '''                ulong sequence = unchecked(++_waitingSequence);

                if (sequence == 0)
                {
                    // A different identity also protects an old arm held by the worker
                    // after cancellation, even when the sequence wraps around.
                    _waitingEpoch = new object();
                }

                _waitingObjects.Add(new WaitingObject(schedulerObj, timePoint, _waitingEpoch, sequence));
''')
    once(path, '''                    if (next != null)
''', '''                    if (next.IsValid)
''')
    once(path, '''            WaitingObject selected = null;
''', '''            WaitingObject selected = default;
''')
    once(path, '''                for (int index = _waitingObjects.Count - 1; index >= 0; index--)
                {
                    if (_waitingObjects[index].Object == schedulerObj)
                    {
                        _waitingObjects.RemoveAt(index);
                    }
                }
''', '''                // Keep the original reverse scan for the usual zero/one-arm
                // cancellation. Compact only after finding a second match.
                int last = -1;

                for (int index = _waitingObjects.Count - 1; index >= 0; index--)
                {
                    if (_waitingObjects[index].Object != schedulerObj)
                    {
                        continue;
                    }

                    if (last < 0)
                    {
                        last = index;
                        continue;
                    }

                    int output = 0;

                    // The suffix after last has no matching arms. Preserve all
                    // survivor identities/order and shift that suffix just once.
                    for (int input = 0; input <= last; input++)
                    {
                        WaitingObject current = _waitingObjects[input];

                        if (current.Object != schedulerObj)
                        {
                            if (output != input)
                            {
                                _waitingObjects[output] = current;
                            }

                            output++;
                        }
                    }

                    // RemoveRange also clears the trailing managed references.
                    _waitingObjects.RemoveRange(output, last + 1 - output);
                    return;
                }

                if (last >= 0)
                {
                    _waitingObjects.RemoveAt(last);
                }
''')
    return [path]

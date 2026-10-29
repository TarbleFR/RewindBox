"""Compute the same A64 register fixed points without full-graph rescans.

Only successors whose predecessor output changed, or predecessors whose
successor input changed, need another visit. Once outputs converge, the
predecessor unions/intersections used by the input equation are constant.
Fold those into the two local mask arrays, retaining all context-call cuts
and the special entry-block rule. A bounded stack/pool worklist avoids adding
per-compilation queue allocations. No masks, host code or guest semantics
are intentionally changed.
"""
import hashlib


SOURCE_SHA256 = 'de7831abfcead47f062c03c1b66a62699e84ae4e6d7e9ffc0e1cbdafb62e02c2'

REPLACEMENT = '''using System;
using System.Buffers;

namespace Ryujinx.Cpu.LightningJit.Graph
{
    static class DataFlow
    {
        public static (RegisterMask[], RegisterMask[]) GetGlobalUses(IBlockList blocks)
        {
            int count = blocks.Count;
            RegisterMask[] globalInputs = new RegisterMask[count];
            RegisterMask[] globalOutputs = new RegisterMask[count];

            if (count == 0)
            {
                return (globalInputs, globalOutputs);
            }

            if (count == 1)
            {
                // Every possible edge stays in the entry block. Its local
                // reads/writes already are the least fixed point, even with a
                // self-loop or a context call; no local scratch arrays needed.
                IBlock block = blocks[0];
                RegisterUse use = block.ComputeUseMasks();
                globalInputs[block.Index] = use.Read;
                globalOutputs[block.Index] = use.Write;
                return (globalInputs, globalOutputs);
            }

            RegisterMask[] localInputs = new RegisterMask[count];
            RegisterMask[] localOutputs = new RegisterMask[count];

            // Most translation units are small. Larger units borrow only two
            // bounded scratch arrays, returned even if a graph operation fails.
            int[] rentedEntries = null;
            byte[] rentedQueued = null;
            Span<int> entries = count <= 128 ? stackalloc int[count] : default;
            Span<byte> queued = count <= 128 ? stackalloc byte[count] : default;

            try
            {
                if (count > 128)
                {
                    entries = (rentedEntries = ArrayPool<int>.Shared.Rent(count)).AsSpan(0, count);
                    queued = (rentedQueued = ArrayPool<byte>.Shared.Rent(count)).AsSpan(0, count);
                }

                queued.Clear();
                Worklist work = new(entries, queued);

                for (int index = 0; index < count; index++)
                {
                    IBlock block = blocks[index];
                    RegisterUse use = block.ComputeUseMasks();
                    localInputs[block.Index] = use.Read;
                    localOutputs[block.Index] = use.Write;
                    work.Add(block.Index);
                }

                while (work.TryRemove(out int index))
                {
                    IBlock block = blocks[index];
                    RegisterMask outputs = localOutputs[index];

                    for (int predecessorIndex = 0; predecessorIndex < block.PredecessorsCount; predecessorIndex++)
                    {
                        IBlock predecessor = block.GetPredecessor(predecessorIndex);

                        if (!predecessor.EndsWithContextStore())
                        {
                            outputs |= globalOutputs[predecessor.Index];
                        }
                    }

                    outputs |= globalOutputs[index];

                    if (outputs != globalOutputs[index])
                    {
                        globalOutputs[index] = outputs;

                        // A saved context cuts the output dependency to successors.
                        if (!block.EndsWithContextStore())
                        {
                            for (int successorIndex = 0; successorIndex < block.SuccessorsCount; successorIndex++)
                            {
                                work.Add(block.GetSuccessor(successorIndex).Index);
                            }
                        }
                    }
                }

                // Outputs are fixed now. Hoist their predecessor unions and
                // intersections instead of recomputing them on each input visit.
                for (int index = 0; index < count; index++)
                {
                    IBlock block = blocks[index];
                    RegisterMask commonOutputs = RegisterMask.Zero;
                    RegisterMask allOutputs = RegisterMask.Zero;
                    bool first = true;
                    bool resetCommon = block.Index == 0;

                    for (int predecessorIndex = 0; predecessorIndex < block.PredecessorsCount; predecessorIndex++)
                    {
                        IBlock predecessor = block.GetPredecessor(predecessorIndex);

                        if (predecessor.EndsWithContextStore())
                        {
                            resetCommon = true;
                            continue;
                        }

                        RegisterMask outputs = globalOutputs[predecessor.Index];
                        allOutputs |= outputs;
                        commonOutputs = first ? outputs : commonOutputs & outputs;
                        first = false;
                    }

                    if (resetCommon)
                    {
                        commonOutputs = RegisterMask.Zero;
                    }

                    RegisterMask writes = localOutputs[index];
                    localInputs[index] = (localInputs[index] | (allOutputs & ~writes)) & ~commonOutputs;
                    localOutputs[index] = ~(writes | commonOutputs);
                }

                // Reverse order retains the cheap one-pass case for forward CFGs.
                for (int index = count - 1; index >= 0; index--)
                {
                    work.Add(index);
                }

                while (work.TryRemove(out int index))
                {
                    IBlock block = blocks[index];
                    RegisterMask inputs = localInputs[index];

                    if (!block.EndsWithContextLoad())
                    {
                        for (int successorIndex = 0; successorIndex < block.SuccessorsCount; successorIndex++)
                        {
                            inputs |= globalInputs[block.GetSuccessor(successorIndex).Index] & localOutputs[index];
                        }
                    }

                    inputs |= globalInputs[index];

                    if (inputs != globalInputs[index])
                    {
                        globalInputs[index] = inputs;

                        for (int predecessorIndex = 0; predecessorIndex < block.PredecessorsCount; predecessorIndex++)
                        {
                            IBlock predecessor = block.GetPredecessor(predecessorIndex);

                            if (!predecessor.EndsWithContextLoad())
                            {
                                work.Add(predecessor.Index);
                            }
                        }
                    }
                }

                return (globalInputs, globalOutputs);
            }
            finally
            {
                if (rentedEntries != null)
                {
                    ArrayPool<int>.Shared.Return(rentedEntries);
                }

                if (rentedQueued != null)
                {
                    ArrayPool<byte>.Shared.Return(rentedQueued);
                }
            }
        }

        // Each block is queued at most once, so capacity is exactly block count.
        private ref struct Worklist
        {
            private readonly Span<int> _entries;
            private readonly Span<byte> _queued;
            private int _head;
            private int _tail;
            private int _count;

            public Worklist(Span<int> entries, Span<byte> queued)
            {
                _entries = entries;
                _queued = queued;
                _head = 0;
                _tail = 0;
                _count = 0;
            }

            public void Add(int index)
            {
                if (_queued[index] != 0)
                {
                    return;
                }

                _queued[index] = 1;
                _entries[_tail] = index;
                _tail = _tail + 1 == _entries.Length ? 0 : _tail + 1;
                _count++;
            }

            public bool TryRemove(out int index)
            {
                if (_count == 0)
                {
                    index = 0;
                    return false;
                }

                index = _entries[_head];
                _head = _head + 1 == _entries.Length ? 0 : _head + 1;
                _queued[index] = 0;
                _count--;
                return true;
            }
        }
    }
}
'''


def apply(source):
    path = source / 'src/Ryujinx.Cpu/LightningJit/Graph/DataFlow.cs'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == SOURCE_SHA256, str(path)
    path.write_text(REPLACEMENT, encoding='utf-8')
    return [path]

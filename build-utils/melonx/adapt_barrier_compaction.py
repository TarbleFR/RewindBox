"""Compact consumed Vulkan barriers once per batch instead of per matching run.

The upstream matching pass removes each consumed run immediately. Alternating
stage flags repeatedly shift the unvisited suffix, up to sixteen times for one
batch. Copy surviving entries stably toward the first hole and remove the one
consumed interval after matching. The unvisited suffix is then shifted once.
The chosen flags, batch capacity, barrier order and final survivor order remain
exact. No barrier is omitted, merged or moved across a native API call.
"""
import hashlib
from adapt_session import once


BASELINE = 'ac30ac1bad76d11a0d4af3d6528f6aa809abf2999dcea9d0a7cd65cbf41b7ae6'


def apply(source):
    path = source / 'src/Ryujinx.Graphics.Vulkan/BarrierBatch.cs'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == BASELINE, str(path)
    text = path.read_text()
    start = text.index('                static void AddBarriers<T, T2>(')
    end = text.index('                if (inRenderPass && _imageBarriers.Count > 0)', start)
    before = text[start:end]
    after = '''                static void AddBarriers<T, T2>(
                    Span<T> target,
                    ref int queuedBarrierCount,
                    ref bool hasBarrier,
                    ref StageFlags flags,
                    ref int count,
                    List<BarrierWithStageFlags<T, T2>> list) where T : unmanaged
                {
                    int consumed = 0;
                    int write = 0;
                    int end = list.Count;

                    for (int read = 0; read < end; read++)
                    {
                        BarrierWithStageFlags<T, T2> barrier = list[read];

                        if (!hasBarrier)
                        {
                            flags = barrier.Flags;
                            hasBarrier = true;
                        }

                        if (flags.Equals(barrier.Flags))
                        {
                            target[count++] = barrier.Barrier;
                            queuedBarrierCount--;
                            consumed++;

                            if (count >= target.Length)
                            {
                                break;
                            }
                        }
                        else
                        {
                            if (consumed != 0)
                            {
                                list[write] = barrier;
                            }

                            write++;
                        }
                    }

                    if (consumed != 0 && consumed == end)
                    {
                        list.Clear();
                    }
                    else if (consumed != 0)
                    {
                        // Matched entries are holes in [0, write + consumed).
                        // The untouched suffix follows that interval. Shift it
                        // once, and let RemoveRange clear retired references.
                        list.RemoveRange(write, consumed);
                    }
                }

'''
    once(path, before, after)
    return [path]

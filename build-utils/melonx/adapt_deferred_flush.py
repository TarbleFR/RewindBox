"""Do not write a texture back into guest memory that the game unmapped after the GPU thread queued the write-back.

Hogwarts Legacy, build 582 (engine e55ca25), 28 October 2026: after 15 s
without a presented frame (the guest's RHI thread at 99 % of a core, six
"Wait on syncpoint ... took more than 1000ms"), the engine ended on
InvalidMemoryRegionException from MemoryTracking.VirtualMemoryEvent, raised
by the HostTracked partition fault handler (AddressSpacePartitionAllocator
Block.VirtualMemoryEvent) on NeoStation.MeloNX.Render, after "Invalid memory
access at virtual address 0x0000001CC01C3000".

The render thread writes guest memory in one place: the flush action of
TextureGroup. When the GPU thread triggers it, BackgroundContextAction
queues it to the render thread (threaded GAL), which runs it after every
command already queued, reads the texture back and stores it into guest
memory through an untracked writable region. A page the guest unmapped in
the meantime is still in the partition block but no longer in the page
table: the fault handler cannot unprotect it and throws from the signal
handler, which ends the process.

The queued action now checks, just before the read-back, that every page of
the slices it flushes is still mapped, and skips the write-back when one is
not (the data has nowhere to go), with a warning. A page unmapped during the
read-back itself is still possible, but no longer during the whole queue's
latency. Flushes requested from other threads (guest faults) are unchanged.

One crash in three sessions of the log; not reproduced on a host. No FPS
gain is claimed. Fail closed on drift.
"""
from adapt_session import once


def apply(source):
    group = source / 'src/Ryujinx.Graphics.Gpu/Image/TextureGroup.cs'
    once(group, '''using Ryujinx.Common.Memory;
using Ryujinx.Graphics.GAL;
''', '''using Ryujinx.Common.Logging;
using Ryujinx.Common.Memory;
using Ryujinx.Graphics.GAL;
''')
    once(group, '''                if (TextureCompatibility.CanTextureFlush(Storage.Info, _context.Capabilities) && !(inBuffer && _flushBufferImported))
                {
                    FlushSliceRange(false, handle.BaseSlice, handle.BaseSlice + handle.SliceCount, inBuffer, Storage.GetFlushTexture());
                }
            });
        }
''', '''                if (TextureCompatibility.CanTextureFlush(Storage.Info, _context.Capabilities) && !(inBuffer && _flushBufferImported))
                {
                    // Queued by the GPU thread, this runs on the render thread after everything already
                    // queued: the guest may have unmapped the texture's memory since, and a store to a page
                    // that is no longer mapped cannot be resolved by the fault handler.
                    if (isGpuThread && !SlicesMapped(handle.BaseSlice, handle.BaseSlice + handle.SliceCount))
                    {
                        Logger.Warning?.Print(LogClass.Gpu, "Texture flush skipped: its guest memory was unmapped before the queued write-back.");

                        return;
                    }

                    FlushSliceRange(false, handle.BaseSlice, handle.BaseSlice + handle.SliceCount, inBuffer, Storage.GetFlushTexture());
                }
            });
        }

        /// <summary>
        /// Checks that every guest page of the given slices is still mapped.
        /// </summary>
        /// <param name="sliceStart">The first slice</param>
        /// <param name="sliceEnd">The slice to finish on (exclusive)</param>
        /// <returns>True if every page is mapped, false otherwise</returns>
        private bool SlicesMapped(int sliceStart, int sliceEnd)
        {
            for (int i = sliceStart; i < sliceEnd; i++)
            {
                (_, int level) = GetLayerLevelForView(i);

                int offset = _allOffsets[i];
                int size = Math.Min(offset + _sliceSizes[level], (int)Storage.Size) - offset;

                MultiRange range = Storage.Range.Slice((ulong)offset, (ulong)size);

                for (int r = 0; r < range.Count; r++)
                {
                    MemoryRange subRange = range.GetSubRange(r);

                    if (subRange.Address == MemoryManager.PteUnmapped)
                    {
                        return false;
                    }

                    ulong end = subRange.Address + subRange.Size;

                    for (ulong page = subRange.Address & ~MemoryManager.PageMask; page < end; page += MemoryManager.PageSize)
                    {
                        if (!_physicalMemory.IsMapped(page))
                        {
                            return false;
                        }
                    }
                }
            }

            return true;
        }
''')
    return [group]

"""Lease the temporary guest snapshot used by fragmented texture uploads.

PhysicalMemory.GetSpan(MultiRange) must return an unowned span, so its fragmented
path allocates a new texture-sized array. Texture upload conversions consume that
span synchronously and create their own output owner: use a scoped, read-only
region for these callers. Contiguous guest spans remain borrowed with no copy.
Only unmapped holes and any tail omitted by a short guest span are cleared.
"""
from adapt_session import once


def apply(source):
    physical = source / 'src/Ryujinx.Graphics.Gpu/Memory/PhysicalMemory.cs'
    once(physical, '''        public ReadOnlySpan<byte> GetSpan(MultiRange range, bool tracked = false)
''', '''        /// <summary>
        /// Borrows contiguous guest data, or owns a pooled snapshot until the texture conversion ends.
        /// </summary>
        internal ReadOnlyRegion GetReadOnlyRegion(MultiRange range, bool tracked = false)
        {
            if (range.Count == 1)
            {
                MemoryRange singleRange = range.GetSubRange(0);
                if (singleRange.Address != MemoryManager.PteUnmapped)
                {
                    return new ReadOnlyRegion(_cpuMemory.GetSpan(singleRange.Address, (int)singleRange.Size, tracked));
                }
            }

            MemoryOwner<byte> owner = MemoryOwner<byte>.Rent(checked((int)range.GetSize()));

            try
            {
                Span<byte> data = owner.Span;
                int offset = 0;

                for (int i = 0; i < range.Count; i++)
                {
                    MemoryRange currentRange = range.GetSubRange(i);
                    int size = (int)currentRange.Size;
                    if (currentRange.Address != MemoryManager.PteUnmapped)
                    {
                        ReadOnlySpan<byte> source = _cpuMemory.GetSpan(currentRange.Address, size, tracked);
                        Span<byte> destination = data.Slice(offset, size);
                        source.CopyTo(destination);
                        // Preserve the zero-initialized snapshot contract even if a memory manager
                        // handles an invalid access by returning fewer bytes instead of throwing.
                        destination[source.Length..].Clear();
                    }
                    else
                    {
                        data.Slice(offset, size).Clear();
                    }

                    offset += size;
                }

                return new ReadOnlyRegion(data, owner);
            }
            catch
            {
                owner.Dispose();
                throw;
            }
        }

        /// <summary>
        /// Gets an unowned span, allocating an independent snapshot when the range is fragmented.
        /// </summary>
        public ReadOnlySpan<byte> GetSpan(MultiRange range, bool tracked = false)
''')
    # A separate source file lets the compiler enforce that the snapshot cannot escape to an async upload.
    region = source / 'src/Ryujinx.Graphics.Gpu/Memory/ReadOnlyRegion.cs'
    assert not region.exists(), str(region)
    region.write_text('''#nullable enable
using Ryujinx.Common.Memory;
using System;

namespace Ryujinx.Graphics.Gpu.Memory
{
    internal readonly ref struct ReadOnlyRegion
    {
        private readonly MemoryOwner<byte>? _owner;
        public ReadOnlySpan<byte> Span { get; }

        internal ReadOnlyRegion(ReadOnlySpan<byte> span, MemoryOwner<byte>? owner = null)
        {
            Span = span;
            _owner = owner;
        }

        public void Dispose() => _owner?.Dispose();
    }
}
''', encoding='utf-8')
    texture = source / 'src/Ryujinx.Graphics.Gpu/Image/Texture.cs'
    once(texture, '''            ReadOnlySpan<byte> data = _physicalMemory.GetSpan(Range);
''', '''            using ReadOnlyRegion guestData = _physicalMemory.GetReadOnlyRegion(Range);
            ReadOnlySpan<byte> data = guestData.Span;
''')

    group = source / 'src/Ryujinx.Graphics.Gpu/Image/TextureGroup.cs'
    text = group.read_text(encoding='utf-8-sig')
    start = text.index('        private void SynchronizePartial(int baseHandle, int regionCount)\n')
    end = text.index('\n        /// <summary>', start)
    method = text[start:end]
    old = '''                        dataSpan = _physicalMemory.GetSpan(Storage.Range.Slice((ulong)spanBase, (ulong)size));
'''
    assert method.count(old) == 1, str(group)
    method = method.replace(old, '''                        guestData.Dispose();
                        guestData = default;
                        guestData = _physicalMemory.GetReadOnlyRegion(Storage.Range.Slice((ulong)spanBase, (ulong)size));
                        dataSpan = guestData.Span;
''')
    prefix = '''        private void SynchronizePartial(int baseHandle, int regionCount)
        {
'''
    assert method.startswith(prefix) and method.endswith('        }\n'), str(group)
    body = method[len(prefix):-len('        }\n')]
    method = prefix + '''            ReadOnlyRegion guestData = default;

            try
            {
''' + ''.join('    ' + line if line.strip() else line for line in body.splitlines(keepends=True)) + '''            }
            finally
            {
                guestData.Dispose();
            }
        }
'''
    group.write_text(text[:start] + method + text[end:], encoding='utf-8')
    return [physical, region, texture, group]

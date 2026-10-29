"""Compare ordered texture data regions once for contiguous physical mappings.

Texture.DataOverlaps builds a fresh nested LINQ enumeration for every slice of
the first texture. With padded array layers, two overlapping allocations can
have no overlapping data: all N*M region pairs are then examined. SizeInfo's
AllRegions enumerates mip/layer offsets in increasing order. When both physical
mappings are contiguous and do not wrap, a two-cursor intersection visits at
most N+M-1 pairs, preserving the same byte-range overlap test.

Keep the existing path for fragmented, unmapped, short or overflowing mappings,
and layouts whose size arithmetic wrapped. Validate the immutable region layout
once, lazily, and remember only the result in one byte. Recheck the mapping on
every call because the texture can be remapped. The interleaved-3D exception and
single-subresource path remain unchanged; no region arrays are retained.
"""
from adapt_session import once


def apply(source):
    texture = source / 'src/Ryujinx.Graphics.Gpu/Image/Texture.cs'
    once(texture, '        private SizeInfo _sizeInfo;\n', '''        private SizeInfo _sizeInfo;
        private byte _dataRegionOrder; // 0: unchecked, 1: ordered and in bounds, 2: invalid.
''')
    once(texture, '            _sizeInfo = sizeInfo;\n', '''            _sizeInfo = sizeInfo;
            _dataRegionOrder = 0;
''')
    once(texture, '''            MultiRange otherRange = texture.Range;

            IEnumerable<MultiRange> regions = _sizeInfo.AllRegions().Select((region) => Range.Slice((ulong)region.Offset, (ulong)region.Size));
''', '''            MultiRange otherRange = texture.Range;

            if (Range.Count == 1 && otherRange.Count == 1)
            {
                MemoryRange thisMapping = Range.GetSubRange(0);
                MemoryRange otherMapping = otherRange.GetSubRange(0);

                // SizeInfo enumerates regions by increasing virtual offset.
                // A contiguous, non-wrapping mapping preserves that order in
                // physical memory. Fragmented and unmapped mappings do not.
                // It must also cover the full layout: Slice's subtraction can
                // underflow for an offset beyond a short mapping's size.
                if (thisMapping.Address != MemoryManager.PteUnmapped &&
                    otherMapping.Address != MemoryManager.PteUnmapped &&
                    thisMapping.EndAddress >= thisMapping.Address &&
                    otherMapping.EndAddress >= otherMapping.Address &&
                    (ulong)_sizeInfo.TotalSize <= thisMapping.Size &&
                    (ulong)texture._sizeInfo.TotalSize <= otherMapping.Size)
                {
                    return DataOverlapsContiguous(texture, otherRange);
                }
            }

            return DataOverlapsUnordered(texture, otherRange);
        }

        // Keep the fallback's captured LINQ state out of the common paths.
        // Otherwise its display class is allocated even before an early return.
        private bool DataOverlapsUnordered(Texture texture, MultiRange otherRange)
        {
            IEnumerable<MultiRange> regions = _sizeInfo.AllRegions().Select((region) => Range.Slice((ulong)region.Offset, (ulong)region.Size));
''')
    once(texture, '''        /// <summary>
        /// Increments the texture reference count.
''', '''        /// <summary>
        /// Validates the immutable layout once. SizeCalculator uses int arithmetic;
        /// overflowing dimensions can otherwise produce a positive total size but
        /// negative or unordered region offsets. Such layouts keep the old path.
        /// </summary>
        private bool HasOrderedDataRegions()
        {
            if (_dataRegionOrder == 0)
            {
                bool valid = _sizeInfo.TotalSize >= 0;
                int previousOffset = 0;

                foreach (Region region in _sizeInfo.AllRegions())
                {
                    if (region.Offset < previousOffset || region.Size < 0 ||
                        (long)region.Offset + region.Size > _sizeInfo.TotalSize)
                    {
                        valid = false;
                        break;
                    }

                    previousOffset = region.Offset;
                }

                _dataRegionOrder = valid ? (byte)1 : (byte)2;
            }

            return _dataRegionOrder == 1;
        }

        /// <summary>
        /// Tests two ordered sets of texture regions without restarting the
        /// second set for every region of the first. Mappings must be contiguous.
        /// </summary>
        private bool DataOverlapsContiguous(Texture texture, MultiRange otherRange)
        {
            using IEnumerator<Region> regions = _sizeInfo.AllRegions().GetEnumerator();
            using IEnumerator<Region> otherRegions = texture._sizeInfo.AllRegions().GetEnumerator();

            if (!regions.MoveNext() || !otherRegions.MoveNext())
            {
                return false;
            }

            Region current = regions.Current;
            Region otherCurrent = otherRegions.Current;
            MemoryRange region = Range.Slice((ulong)current.Offset, (ulong)current.Size).GetSubRange(0);
            MemoryRange otherRegion = otherRange.Slice((ulong)otherCurrent.Offset, (ulong)otherCurrent.Size).GetSubRange(0);

            // The original nested traversal tests this pair first as well.
            // An immediate match needs no proof about later region offsets.
            if (region.OverlapsWith(otherRegion))
            {
                return true;
            }

            if (!HasOrderedDataRegions() || !texture.HasOrderedDataRegions())
            {
                return DataOverlapsUnordered(texture, otherRange);
            }

            while (true)
            {
                // The earlier ending interval cannot intersect a later start
                // in the other set. Only advance that cursor, retaining the
                // current region of the other texture.
                if (region.EndAddress <= otherRegion.EndAddress)
                {
                    if (!regions.MoveNext())
                    {
                        return false;
                    }

                    current = regions.Current;
                    region = Range.Slice((ulong)current.Offset, (ulong)current.Size).GetSubRange(0);
                }
                else
                {
                    if (!otherRegions.MoveNext())
                    {
                        return false;
                    }

                    otherCurrent = otherRegions.Current;
                    otherRegion = otherRange.Slice((ulong)otherCurrent.Offset, (ulong)otherCurrent.Size).GetSubRange(0);
                }

                if (region.OverlapsWith(otherRegion))
                {
                    return true;
                }
            }
        }

        /// <summary>
        /// Increments the texture reference count.
''')
    return [texture]

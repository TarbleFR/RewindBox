"""Use a value cursor for ordered texture-region overlap scans.

Keep SizeInfo.AllRegions and its IEnumerable contract unchanged for LINQ and
unordered mappings. The contiguous overlap scan and its one-time order proof
can walk the same immutable SizeInfo with a stack-local cursor instead of two
heap-allocated iterator state machines on every comparison. Dispose and failed
MoveNext terminate this cursor just as they terminate the original iterator.
"""
from adapt_session import once


def apply(source):
    size = source / 'src/Ryujinx.Graphics.Texture/SizeInfo.cs'
    once(size, '''        public IEnumerable<Region> AllRegions()
''', '''        /// <summary>
        /// Gets an allocation-free cursor for synchronous, ordered region scans.
        /// The existing IEnumerable API remains available to other callers.
        /// </summary>
        public RegionEnumerator GetRegionEnumerator() => new(this);

        public struct RegionEnumerator : IDisposable
        {
            private readonly SizeInfo _size;
            private int _index;
            public Region Current { get; private set; }

            internal RegionEnumerator(SizeInfo size)
            {
                _size = size;
                _index = 0;
                Current = default;
            }

            public bool MoveNext()
            {
                int index = _index;
                _index = -1;

                if (index < 0)
                {
                    return false;
                }

                if (_size._is3D)
                {
                    if (index >= _size._mipOffsets.Length)
                    {
                        return false;
                    }

                    int offset = _size._mipOffsets[index];
                    int maxSize = _size.TotalSize - offset;
                    Current = new Region(offset, Math.Min(maxSize, _size.LevelSizes[index]));
                }
                else
                {
                    if (index >= _size.AllOffsets.Length)
                    {
                        return false;
                    }

                    Current = new Region(_size.AllOffsets[index], _size.SliceSizes[index % _size._levels]);
                }

                _index = index + 1;
                return true;
            }

            public void Dispose() => _index = -1;
        }

        public IEnumerable<Region> AllRegions()
''')
    texture = source / 'src/Ryujinx.Graphics.Gpu/Image/Texture.cs'
    once(texture, '''                foreach (Region region in _sizeInfo.AllRegions())
                {
                    if (region.Offset < previousOffset || region.Size < 0 ||
''', '''                using var regions = _sizeInfo.GetRegionEnumerator();
                while (regions.MoveNext())
                {
                    Region region = regions.Current;
                    if (region.Offset < previousOffset || region.Size < 0 ||
''')
    once(texture, '''            using IEnumerator<Region> regions = _sizeInfo.AllRegions().GetEnumerator();
            using IEnumerator<Region> otherRegions = texture._sizeInfo.AllRegions().GetEnumerator();
''', '''            using var regions = _sizeInfo.GetRegionEnumerator();
            using var otherRegions = texture._sizeInfo.GetRegionEnumerator();
''')
    return [size, texture]

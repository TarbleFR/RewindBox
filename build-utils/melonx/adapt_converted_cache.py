"""Do not create converted-buffer cache ranges while looking up missing data.

Only Add creates a range. TryGetValue, Remove and AddDependency return their
existing missing-entry result without allocating a dictionary/list or retaining
an empty range. Existing entries keep the same first-match and per-entry destruction sequence,
including cached null draw-count values and dependency callbacks.
"""
from adapt_session import once


def apply(source):
    cache = source / 'src/Ryujinx.Graphics.Vulkan/CacheByRange.cs'
    for signature in (
        '        public void AddDependency(int offset, int size, ICacheKey key, Dependency dependency)',
        '        public void Remove(int offset, int size, ICacheKey key)',
    ):
        once(cache, signature + '''
        {
            List<Entry> entries = GetEntries(offset, size);
''', signature + '''
        {
            if (_ranges == null || !_ranges.TryGetValue(PackRange(offset, size), out List<Entry> entries))
            {
                return;
            }
''')
    once(cache, '''        public bool TryGetValue(int offset, int size, ICacheKey key, out T value)
        {
            List<Entry> entries = GetEntries(offset, size);
''', '''        public bool TryGetValue(int offset, int size, ICacheKey key, out T value)
        {
            if (_ranges == null || !_ranges.TryGetValue(PackRange(offset, size), out List<Entry> entries))
            {
                value = default;
                return false;
            }
''')
    return [cache]

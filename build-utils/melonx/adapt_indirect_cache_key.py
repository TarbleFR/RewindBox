"""Keep the converted index buffer in an indirect conversion cache key.

SetBuffer was called on a readonly nested value; C# mutated a defensive copy
and the boxed cached key retained null. Make the owning key and nested field
mutable so its later Dispose can invalidate the actual bound converted buffer.
Cache equality still uses only the original structural fields. This is a
cache-coherence fix, not an asserted performance gain.
"""
from adapt_session import once


def apply(source):
    path = source / 'src/Ryujinx.Graphics.Vulkan/CacheByRange.cs'
    once(path, '    readonly struct TopologyConversionIndirectCacheKey : ICacheKey\n',
         '    struct TopologyConversionIndirectCacheKey : ICacheKey\n')
    once(path, '        private readonly TopologyConversionCacheKey _baseKey;\n',
         '        private TopologyConversionCacheKey _baseKey;\n')
    return [path]

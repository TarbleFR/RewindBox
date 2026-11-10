"""Keep each resource's command-buffer ownership bits inside Auto<T>.

The pinned renderer has sixteen command-buffer slots; its dynamic BitMap
therefore allocates a separate long[1] per Auto. Reuse the existing fixed
BitMapStruct<Array1<long>> without changing dependency/refcount operations.
The field must be mutable: readonly would silently mutate defensive copies.
The explicit capacity check fails closed if the command-buffer contract drifts.
"""
from adapt_session import once


def apply(source):
    vulkan = source / 'src/Ryujinx.Graphics.Vulkan'
    pool = (vulkan / 'CommandBufferPool.cs').read_text()
    assert 'public const int MaxCommandBuffers = 16;' in pool, 'ownership bitmap capacity drift'
    auto = vulkan / 'Auto.cs'
    once(auto, 'using System;\n', 'using Ryujinx.Common.Memory;\nusing System;\n')
    once(auto, '        private readonly BitMap _cbOwnership;\n',
         '''        // Sixteen command-buffer slots fit in the existing inline 64-bit bitmap.
        // Keep this field mutable so Set/Clear update it instead of a defensive copy.
        private BitMapStruct<Array1<long>> _cbOwnership;
''')
    once(auto, '            _cbOwnership = new BitMap(CommandBufferPool.MaxCommandBuffers);\n',
         '            _cbOwnership = new BitMapStruct<Array1<long>>();\n')
    return [auto]

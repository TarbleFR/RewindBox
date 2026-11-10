"""Keep identical Vulkan buffer assignments from rebuilding descriptor sets.

The three setters already compare buffer identity, offset, write access and
range before invalidating per-binding descriptor state. Signal the descriptor
category dirty at that same change point instead of after every call. Keep
GetBuffer and all of its write/mirroring side effects on every assignment.

Existing dirty state is never cleared here. Rebind, program changes, command
buffer changes, CopyFrom and SwapBuffer's command-buffer invalidation still
force their existing updates. Empty assignments keep the previous explicit
dirty behavior. No barrier, resource-acquisition or invalidation method is
removed or changed.
"""
from adapt_session import once


def method(text, signature):
    assert text.count(signature) == 1, signature
    start = text.index(signature)
    opening = text.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


def apply(source):
    updater = source / 'src/Ryujinx.Graphics.Vulkan/DescriptorSetUpdater.cs'
    for signature, flag in (
        ('        public void SetUniformBuffers(CommandBuffer commandBuffer, ReadOnlySpan<BufferAssignment> buffers)', 'Uniform'),
        ('        public void SetStorageBuffers(CommandBuffer commandBuffer, ReadOnlySpan<BufferAssignment> buffers)', 'Storage'),
        ('        public void SetStorageBuffers(CommandBuffer commandBuffer, int first, ReadOnlySpan<Auto<DisposableBuffer>> buffers)', 'Storage'),
    ):
        old = method(updater.read_text(), signature)
        assert old.count('                    currentBufferRef = newRef;') == 1
        assert old.count(f'            SignalDirty(DirtyFlags.{flag});') == 1
        new = old.replace('                    currentBufferRef = newRef;',
                          f'''                    currentBufferRef = newRef;
                    SignalDirty(DirtyFlags.{flag});''')
        new = new.replace(f'            SignalDirty(DirtyFlags.{flag});\n        }}',
                          f'''            if (buffers.IsEmpty)
            {{
                SignalDirty(DirtyFlags.{flag});
            }}
        }}''')
        once(updater, old, new)
    return [updater]

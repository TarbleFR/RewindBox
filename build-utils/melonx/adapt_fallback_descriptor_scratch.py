"""Reuse two one-element stack spans for exceptional descriptor updates.

The template fallback preserves each individual update, including zero-handle
filtering, and its order. DescriptorSetCollection consumes both spans in fixed
blocks during synchronous Vulkan calls; authenticate that consumer as well as
the updater. Scratch is local to each invocation and allocated outside loops.
"""
import hashlib
from adapt_session import once
from adapt_descriptor_updates import method


RELATIVE = 'src/Ryujinx.Graphics.Vulkan/DescriptorSetUpdater.cs'
BASELINE = '78c9662f5cffb07f2b8f7849f19069bcfc8e6817e817f273f957f4ba1d30887b'
CONSUMER = 'src/Ryujinx.Graphics.Vulkan/DescriptorSetCollection.cs'
CONSUMER_HASH = 'f4ed5fd7823f29366c06abb3a4218d9d1bba1d05fcedf8098cf9f39529edc9cb'
SIGNATURE = '        private void UpdateAndBind(CommandBufferScoped cbs, int setIndex, PipelineBindPoint pbp)'


def apply(source):
    path = source / RELATIVE
    assert hashlib.sha256(path.read_bytes()).hexdigest() == BASELINE, str(path)
    consumer = source / CONSUMER
    assert hashlib.sha256(consumer.read_bytes()).hexdigest() == CONSUMER_HASH, str(consumer)
    old = method(path.read_text(), SIGNATURE)
    anchor = '            foreach (ResourceBindingSegment segment in bindingSegments)'
    assert old.count(anchor) == 1
    new = old.replace(anchor, '''            Span<DescriptorImageInfo> imageScratch = stackalloc DescriptorImageInfo[1];
            Span<BufferView> bufferScratch = stackalloc BufferView[1];

''' + anchor)
    for expression in ('imageInfo', 'imageInfos[i]', 'dummyImageInfo'):
        binding = 'index' if expression == 'imageInfo' else 'binding + i'
        needle = f'dsc.UpdateImages(0, {binding}, new[] {{ {expression} }}, DescriptorType.CombinedImageSampler);'
        assert new.count(needle) == 1
        indent = ' ' * (32 if expression == 'imageInfo' else 36)
        new = new.replace(needle, f'imageScratch[0] = {expression};\n{indent}dsc.UpdateImages(0, {binding}, imageScratch, DescriptorType.CombinedImageSampler);')
    for expression in ('bufferView', 'bufferViews[i]', 'default(BufferView)'):
        binding = 'index' if expression == 'bufferView' else 'binding + i'
        needle = f'dsc.UpdateBufferImages(0, {binding}, new[] {{ {expression} }}, DescriptorType.UniformTexelBuffer);'
        assert new.count(needle) == 1
        indent = ' ' * (32 if expression == 'bufferView' else 36)
        new = new.replace(needle, f'bufferScratch[0] = {expression};\n{indent}dsc.UpdateBufferImages(0, {binding}, bufferScratch, DescriptorType.UniformTexelBuffer);')
    assert 'new[]' not in new
    once(path, old, new)
    return [path]

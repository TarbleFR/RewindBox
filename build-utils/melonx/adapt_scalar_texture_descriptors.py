"""Keep identical scalar image descriptors from rebuilding whole Vulkan sets.

Resolve every image-view/sampler and perform every usage/barrier operation as
before, then compare the complete binding record. Only an identical resulting
record may avoid the final category invalidation. TextureBuffer objects can
change their backing view without changing identity, so their paths retain
unconditional invalidation. Existing program/command-buffer/forced dirty state
is never cleared. No persistent cache or additional retained resource is added.
"""
import hashlib
from adapt_session import once
from adapt_descriptor_updates import method


RELATIVE = 'src/Ryujinx.Graphics.Vulkan/DescriptorSetUpdater.cs'
BASELINE = '918ad22abd943608c50d812add2e39076df4cf45a1e48ba2e2c68675a3a243ca'


def apply(source):
    path = source / RELATIVE
    assert hashlib.sha256(path.read_bytes()).hexdigest() == BASELINE, str(path)
    for signature, kind, name in (
        ('        public void SetTextureAndSampler(\n', 'Texture', 'texture'),
        ('        public void SetImage(CommandBufferScoped cbs, ShaderStage stage, int binding, ITexture image)', 'Image', 'image'),
    ):
        old = method(path.read_text(), signature)
        new = old.replace('        {\n', '        {\n            bool changed = true;\n\n', 1)
        if kind == 'Texture':
            assignment = '                iRef = new(stage, view, view.GetImageView(), ((SamplerHolder)sampler)?.GetSampler());'
            replacement = '''                TextureRef newRef = new(stage, view, view.GetImageView(), ((SamplerHolder)sampler)?.GetSampler());
                changed = !iRef.Equals(newRef) || _bufferTextureRefs[binding] != null;
                iRef = newRef;'''
            refs, buffers = '_textureRefs', '_bufferTextureRefs'
        else:
            assignment = '                iRef = new(stage, view, view.GetIdentityImageView());'
            replacement = '''                ImageRef newRef = new(stage, view, view.GetIdentityImageView());
                changed = !iRef.Equals(newRef) || _bufferImageRefs[binding] != null;
                iRef = newRef;'''
            refs, buffers = '_imageRefs', '_bufferImageRefs'
        assert new.count(assignment) == 1
        new = new.replace(assignment, replacement)
        clear = f'                {refs}[binding] = default;\n                {buffers}[binding] = null;'
        assert new.count(clear) == 1
        new = new.replace(clear,
            f'                changed = !{refs}[binding].Equals(default({kind}Ref)) || {buffers}[binding] != null;\n' + clear)
        signal = f'            SignalDirty(DirtyFlags.{kind});'
        assert new.count(signal) == 1
        new = new.replace(signal, f'''            if (changed)
            {{
                SignalDirty(DirtyFlags.{kind});
            }}''')
        once(path, old, new)

    signature = '        public void SetTextureAndSamplerIdentitySwizzle(\n'
    old = method(path.read_text(), signature)
    needle = '''                _textureRefs[binding] = new(stage, view, view.GetIdentityImageView(), ((SamplerHolder)sampler)?.GetSampler());

                SignalDirty(DirtyFlags.Texture);'''
    replacement = '''                TextureRef newRef = new(stage, view, view.GetIdentityImageView(), ((SamplerHolder)sampler)?.GetSampler());
                bool changed = !_textureRefs[binding].Equals(newRef) || _bufferTextureRefs[binding] != null;
                _textureRefs[binding] = newRef;

                if (changed)
                {
                    SignalDirty(DirtyFlags.Texture);
                }'''
    assert old.count(needle) == 1
    once(path, old, old.replace(needle, replacement))

    old = method(path.read_text(), '        public void SetImage(int binding, Auto<DisposableImageView> image)')
    needle = '''            _imageRefs[binding] = new(ShaderStage.Compute, null, image);

            SignalDirty(DirtyFlags.Image);'''
    replacement = '''            ImageRef newRef = new(ShaderStage.Compute, null, image);
            bool changed = !_imageRefs[binding].Equals(newRef) || _bufferImageRefs[binding] != null;
            _imageRefs[binding] = newRef;

            if (changed)
            {
                SignalDirty(DirtyFlags.Image);
            }'''
    assert old.count(needle) == 1
    once(path, old, old.replace(needle, replacement))
    return [path]

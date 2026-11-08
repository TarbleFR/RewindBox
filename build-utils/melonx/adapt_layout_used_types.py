"""A stage's resource layout declares each binding it uses with the type it uses (Core 703).

Hogwarts Legacy, program 890A188FB55B5D5D (host shader cache program 1837): MoltenVK "SPIR-V to MSL conversion
error: nullptr" for its fragment stage (IPAs 688-694), so every draw of that pipeline state is dropped (black holes on
the ground). The fragment uses 36 static textures. The translator gives textures and buffer textures one counter
(GpuAccessorBase.CreateTextureBinding: index = counter, + MaximumTexturesPerStage for a buffer texture, limit
2 x 32), so its 33rd-36th non-buffer textures get bindings 96-99 of set 2; ShaderInfoBuilder declares the stage's
bindings as fixed blocks, 64-95 TextureAndSampler and 96-127 BufferTexture, so the layout says uniform texel buffer
for bindings the shader samples as cube/2D/3D combined samplers. MoltenVK 1.4.2 (Metal 3 argument buffers) then
hands SPIRV-Cross an Image binding without a sampler slot for them, and SPIRV-Cross 6c09849f fails with "nullptr"
(a 2D or cube texture there; with one 3D texture it converts, its sampler aliasing the next binding's slot). The same
holds for images (CreateImageBinding: one counter, + MaximumImagesPerStage for a buffer image).

Change: after declaring the stage's blocks, every single (non-array) texture or image the stage uses is declared with
the type it is used as, at its binding (DeclareUsedTypes): combined texture or buffer texture (image or buffer image),
the two types of the blocks. Bindings the stage does not use keep the block's type, and so does a binding the stage uses
with both types (two counter values a block apart: invalid either way, left as before).
The layout then matches the SPIR-V for every used binding, as Vulkan requires. Usages, binding numbers, arrays and
other stages are unchanged; a program whose bindings stay in their blocks gets the same layout as before. Nothing is
persisted: the layout is rebuilt from ShaderProgramInfo when a program is created or loaded from the cache.
Fail closed on drift: the file must be the pinned upstream one.
"""
import hashlib
from adapt_session import once

BUILDER = 'src/Ryujinx.Graphics.Gpu/Shader/ShaderInfoBuilder.cs'
BASELINE = {
    BUILDER: '31eaf8d65202313dc976ab308f962ae93f8d6d3683b741836d0e35df2d93a2da',
}

CALL_OLD = '''            AddDualDescriptor(stages, ResourceType.Image, ResourceType.BufferImage, imageSetIndex, imageBinding, imagesPerStage);
'''
CALL_NEW = '''            AddDualDescriptor(stages, ResourceType.Image, ResourceType.BufferImage, imageSetIndex, imageBinding, imagesPerStage);

            // RewindBox (adapt_layout_used_types): textures and buffer textures (images and buffer images) share one
            // binding counter, so a stage with more than the per-stage count of one kind has bindings inside the other
            // kind's block: those are declared with the type the stage uses them as.
            DeclareUsedTypes(info.Textures, stages, isImage: false);
            DeclareUsedTypes(info.Images, stages, isImage: true);
'''

METHOD_OLD = '''        private void AddArrayDescriptors(IEnumerable<TextureDescriptor> textures, ResourceStages stages, bool isImage)
'''
METHOD_NEW = '''        /// <summary>
        /// RewindBox (adapt_layout_used_types): declares each single texture or image of a stage with the type it is used
        /// as (combined or buffer texture, image or buffer image), at its binding of the stage's blocks. Bindings the stage
        /// does not use, and a binding the stage uses with both types, keep the block's type.
        /// </summary>
        private void DeclareUsedTypes(IEnumerable<TextureDescriptor> textures, ResourceStages stages, bool isImage)
        {
            ResourceType single = isImage ? ResourceType.Image : ResourceType.TextureAndSampler;
            ResourceType buffer = isImage ? ResourceType.BufferImage : ResourceType.BufferTexture;
            Dictionary<(int Set, int Binding), ResourceType> used = new();
            HashSet<(int Set, int Binding)> both = new();

            foreach (TextureDescriptor texture in textures)
            {
                if (texture.ArrayLength > 1)
                {
                    continue; // Arrays get their own descriptor (AddArrayDescriptors).
                }

                ResourceType type = GetTextureResourceType(texture, isImage);

                if (type != single && type != buffer)
                {
                    continue;
                }

                if (used.TryGetValue((texture.Set, texture.Binding), out ResourceType other) && other != type)
                {
                    both.Add((texture.Set, texture.Binding));
                }

                used[(texture.Set, texture.Binding)] = type;
            }

            foreach (KeyValuePair<(int Set, int Binding), ResourceType> binding in used)
            {
                if (both.Contains(binding.Key))
                {
                    continue;
                }

                List<ResourceDescriptor> descriptors = GetDescriptors(binding.Key.Set);

                for (int index = 0; index < descriptors.Count; index++)
                {
                    ResourceDescriptor descriptor = descriptors[index];

                    if (descriptor.Binding == binding.Key.Binding && descriptor.Stages == stages && descriptor.Count == 1 &&
                        (descriptor.Type == single || descriptor.Type == buffer) && descriptor.Type != binding.Value)
                    {
                        descriptors[index] = new ResourceDescriptor(descriptor.Binding, 1, binding.Value, stages);
                    }
                }
            }
        }

        private void AddArrayDescriptors(IEnumerable<TextureDescriptor> textures, ResourceStages stages, bool isImage)
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    once(paths[BUILDER], CALL_OLD, CALL_NEW)
    once(paths[BUILDER], METHOD_OLD, METHOD_NEW)
    return list(paths.values())

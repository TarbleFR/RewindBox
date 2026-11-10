"""A texture array in its own set no longer forces the main texture set to be written again (Core 723 candidate).

IPA 718, Hogwarts Legacy in play (pid 44597, per 5 s): the render thread spends 0.4-2.5 s in draw descriptors (9.6 ms
per frame in a 97-frame window), its counters give 63 517 texture sets written for 5.39 M descriptors (about 74 per
texture set), and SetTextureArraySeparate runs 17 000-93 500 times. DescriptorSetUpdater.SetTextureArraySeparate,
when the array bound to an extra set (index 4 and up, `_textureArrayExtraRefs`) changes, signals DirtyFlags.Texture:
the next draw then writes the whole main texture set (set 2) again from the next set of its pool. Set 2's content is
the texture, sampler, buffer-texture and non-separate array bindings (`_textureRefs`, `_bufferTextureRefs`,
`_textureArrayRefs`); the extra arrays are never part of it. Only the extra sets need binding again, which
BindExtraSets does when any texture or image flag is set (`arraysKept` false).

Change (DescriptorSetUpdater.cs only, every title):
- a DirtyFlags bit of its own, TextureArrayExtra, part of All (a program or command buffer change still marks every
  set);
- SetTextureArraySeparate signals that bit instead of Texture;
- BindExtraSets rebinds the extra sets when that bit is set too (`arraysKept` false), as it did when Texture was set.
Unchanged: every other setter, ForceTextureDirty (an array element change still writes set 2), image arrays in their
own set (SetImageArraySeparate keeps DirtyFlags.Image), the push-descriptor and template paths, the pools. Not
measured on an iPhone. Fail closed on drift: the file must be the Core 721 preparation's.
"""
import hashlib
from adapt_session import once

UPDATER = 'src/Ryujinx.Graphics.Vulkan/DescriptorSetUpdater.cs'
BASELINE = {
    UPDATER: '911e3fbf38cecefd65c91905336f9b5ead5ceb331bb6927dba5f9ad2ce8d6e3f',
}
TAG = 'RewindBox (adapt_extra_array_dirty)'

FLAGS_OLD = '''            Image = 1 << 3,
            All = Uniform | Storage | Texture | Image,
'''
FLAGS_NEW = '''            Image = 1 << 3,
            // RewindBox (adapt_extra_array_dirty): a texture array bound to its own set changed; set 2 did not.
            TextureArrayExtra = 1 << 4,
            All = Uniform | Storage | Texture | Image | TextureArrayExtra,
'''

SEPARATE_OLD = '''        public void SetTextureArraySeparate(CommandBufferScoped cbs, ShaderStage stage, int setIndex, ITextureArray array)
        {
            ref ArrayRef<TextureArray> arrayRef = ref GetArrayRef(ref _textureArrayExtraRefs, setIndex - PipelineBase.DescriptorSetLayouts);

            if (arrayRef.Stage != stage || arrayRef.Array != array)
            {
                arrayRef.Array?.DecrementBindCount();

                if (array is TextureArray textureArray)
                {
                    textureArray.IncrementBindCount();
                    textureArray.QueueWriteToReadBarriers(cbs, stage.ConvertToPipelineStageFlags());
                }

                arrayRef = new ArrayRef<TextureArray>(stage, array as TextureArray);

                SignalDirty(DirtyFlags.Texture);
            }
        }
'''
SEPARATE_NEW = '''        public void SetTextureArraySeparate(CommandBufferScoped cbs, ShaderStage stage, int setIndex, ITextureArray array)
        {
            ref ArrayRef<TextureArray> arrayRef = ref GetArrayRef(ref _textureArrayExtraRefs, setIndex - PipelineBase.DescriptorSetLayouts);

            if (arrayRef.Stage != stage || arrayRef.Array != array)
            {
                arrayRef.Array?.DecrementBindCount();

                if (array is TextureArray textureArray)
                {
                    textureArray.IncrementBindCount();
                    textureArray.QueueWriteToReadBarriers(cbs, stage.ConvertToPipelineStageFlags());
                }

                arrayRef = new ArrayRef<TextureArray>(stage, array as TextureArray);

                // RewindBox (adapt_extra_array_dirty): only the extra sets are bound again; set 2 does not hold this array.
                SignalDirty(DirtyFlags.TextureArrayExtra);
            }
        }
'''

EXTRA_OLD = '''                BindExtraSets(cbs, program, pbp, arraysKept: (_dirty & (DirtyFlags.Texture | DirtyFlags.Image)) == 0);
'''
EXTRA_NEW = '''                // RewindBox (adapt_extra_array_dirty): a separate texture array change binds them again too.
                BindExtraSets(cbs, program, pbp, arraysKept: (_dirty & (DirtyFlags.Texture | DirtyFlags.Image | DirtyFlags.TextureArrayExtra)) == 0);
'''

PAIRS = ((FLAGS_OLD, FLAGS_NEW), (SEPARATE_OLD, SEPARATE_NEW), (EXTRA_OLD, EXTRA_NEW))


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for old, new in PAIRS:
        once(paths[UPDATER], old, new)
    return list(paths.values())

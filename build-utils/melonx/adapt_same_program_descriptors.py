"""Setting the program already set keeps its bound descriptor sets instead of rewriting all four (Core 705).

IPA 694 (Hogwarts Legacy 1x, pid 40200, Core 699), render stage windows in play: descriptors 1 121.1 ms in draw prepare
(131 351 draws, 108 frames) and 394.2 ms in compute prepare (10 662 dispatches, 10 446 compute descriptor updates of at
most 32 descriptors, 392.2 ms), inside the prepare times. MoltenVK 1.4.2 binds the resources of a set only when it
encodes; on the render thread the cost is the update itself: a new set from the layout's per-command-buffer list, then
vkUpdateDescriptorSetWithTemplate of every binding the program uses, then the bind.

Redundancy: DescriptorSetUpdater.SetProgram marks the four sets dirty on every call. ComputeClass.Dispatch calls
SetProgram before every dispatch, and StateUpdater.UpdateShaderState on every shader state update, also when the program
is the one already set. With the same ShaderCollection the sets bound at its last update are still bound at its bind
point: the only other writers of that bind point are another program (a different ShaderCollection: everything is
dirty again) and the helper shaders, which restore the main pipeline through SignalCommandBufferChange (everything
dirty), as does a new command buffer. Every binding change since that update already marks its own set dirty (the
setters compare their records; Rebind, ForceTextureDirty/ForceImageDirty from the texture and image arrays, SwapBuffer,
CopyFrom). A resource referenced by the command buffer cannot be destroyed before it completes (Auto reference count),
so rewriting the set in that command buffer gives the same descriptors: the rewrite is redundant.

Change: SetProgram with the program already set keeps the dirty flags it has (nothing is cleared) instead of setting
all four; a texture set with buffer textures and an image set with buffer images stay dirty as before, because a
TextureBuffer can take another buffer view without a setter call (SetStorage, its buffer's release). Different
programs, command buffer changes and every setter are unchanged. Counted on the existing pass detail line: descriptor
sets written per set, descriptors written, program sets and those of the program already set.
Fail closed on drift: both files must be the Core 703 preparation's.
"""
import hashlib
from adapt_session import once

UPDATER = 'src/Ryujinx.Graphics.Vulkan/DescriptorSetUpdater.cs'
PIPELINE = 'src/Ryujinx.Graphics.Vulkan/PipelineBase.cs'
BASELINE = {
    UPDATER: '45731f25882508b9833141d01e10ea377cbcb8de1270e628a3ab6b533f85e501',
    PIPELINE: 'dcda6601f7027c2a2f9328ee98971a0e72acce33bf61935b55a60d228de4a68c',
}

SET_PROGRAM_OLD = '''            _program = program;
            _updateDescriptorCacheCbIndex = true;
            _dirty = DirtyFlags.All;
        }
'''
SET_PROGRAM_NEW = '''            RenderDetail.ProgramSets++;

            // RewindBox (adapt_same_program_descriptors): the program already set keeps the sets bound at its last update;
            // every change since marked its own set dirty. Buffer textures and buffer images can change view without a
            // setter call, so their sets are written again as before.
            if (ReferenceEquals(program, _program))
            {
                RenderDetail.SameProgramSets++;
                _updateDescriptorCacheCbIndex = true;
                _dirty |= BufferViewSets(program);
                return;
            }

            _program = program;
            _updateDescriptorCacheCbIndex = true;
            _dirty = DirtyFlags.All;
        }

        private static DirtyFlags BufferViewSets(ShaderCollection program)
        {
            DirtyFlags flags = DirtyFlags.None;

            foreach (ResourceBindingSegment segment in program.BindingSegments[PipelineBase.TextureSetIndex])
            {
                if (segment.Type == ResourceType.BufferTexture)
                {
                    flags |= DirtyFlags.Texture;
                }
            }

            foreach (ResourceBindingSegment segment in program.BindingSegments[PipelineBase.ImageSetIndex])
            {
                if (segment.Type == ResourceType.BufferImage)
                {
                    flags |= DirtyFlags.Image;
                }
            }

            return flags;
        }
'''

COMMIT_OLD = '''            var sets = dsc.GetSets();
            _templateUpdater.Commit(_gd, _device, sets[0]);
'''
COMMIT_NEW = '''            var sets = dsc.GetSets();
            _templateUpdater.Commit(_gd, _device, sets[0]);

            // RewindBox (adapt_same_program_descriptors): sets written and their descriptors, per window.
            RenderDetail.DescriptorSetWrites[setIndex]++;

            foreach (ResourceBindingSegment segment in bindingSegments)
            {
                RenderDetail.DescriptorsWritten += segment.Count;
            }
'''

FIELDS_OLD = '''        public static long ArrayCurrentBinds, ArraySlotsAdded, ArrayFallbacks;
'''
FIELDS_NEW = '''        public static long ArrayCurrentBinds, ArraySlotsAdded, ArrayFallbacks;
        // RewindBox (adapt_same_program_descriptors): template writes of the four main sets (uniform, storage, texture,
        // image) and their descriptors; SetProgram calls and those with the program already set (its sets kept bound).
        public static readonly long[] DescriptorSetWrites = new long[4];
        public static long DescriptorsWritten, ProgramSets, SameProgramSets;
'''

LINE_OLD = '''                .Append(ArrayFallbacks);
'''
LINE_NEW = '''                .Append(ArrayFallbacks);

            // RewindBox (adapt_same_program_descriptors): counted and reset every window.
            text.Append("; descriptor sets written ").Append(DescriptorSetWrites[0]).Append('/').Append(DescriptorSetWrites[1])
                .Append('/').Append(DescriptorSetWrites[2]).Append('/').Append(DescriptorSetWrites[3])
                .Append(" (uniform/storage/texture/image, ").Append(DescriptorsWritten).Append(" descriptors), programs set ")
                .Append(ProgramSets).Append(" (already set ").Append(SameProgramSets).Append(", sets kept bound)");
            Array.Clear(DescriptorSetWrites);
            DescriptorsWritten = ProgramSets = SameProgramSets = 0;
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    once(paths[UPDATER], SET_PROGRAM_OLD, SET_PROGRAM_NEW)
    once(paths[UPDATER], COMMIT_OLD, COMMIT_NEW)
    once(paths[PIPELINE], FIELDS_OLD, FIELDS_NEW)
    once(paths[PIPELINE], LINE_OLD, LINE_NEW)
    return list(paths.values())

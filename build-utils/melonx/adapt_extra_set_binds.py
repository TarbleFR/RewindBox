"""An update of the main sets alone keeps the bindless array sets bound instead of looking them up and binding them
again (Core 715, lot 8, every title).

IPA 694 (Hogwarts Legacy 1x, pid 40200, Core 699, 108 frames): descriptors 1 121.1 ms in draw prepare and 394.2 ms in
compute prepare; lot 3 (board) mapped the remaining repeated work. DescriptorSetUpdater.UpdateAndBindDescriptorSets calls
BindExtraSets whenever any of the four main sets is dirty: a program with a bindless array in an extra set (index 4 and
up) looks the array's descriptor set up again (TextureArray.GetDescriptorSets: its own current slot or the cached set,
the command buffer's ownership of that set, AddReferences) and binds it again on every update, also when only the
uniform or storage set changed (Core 705 fixture: 2 000 uniform-only dispatches, 2 000 lookups and 4 000 binds).

Why the bound set is still right: the extra sets are bound with the program's own pipeline layout, and binding a lower
set with that same layout does not disturb higher sets (Vulkan pipeline layout compatibility); a pipeline bind disturbs
none. Every event that can change or disturb an extra set raises the texture or the image flag: another program
(SetProgram: all four), a new command buffer and the helper shaders' restore of the main pipeline
(SignalCommandBufferChange: all four), CopyFrom (all four), SetTextureArraySeparate/SetImageArraySeparate with another
array or stage (texture/image), an element change of a bound array (TextureArray/ImageArray.SetDirty ->
ForceTextureDirty/ForceImageDirty). With neither flag raised since the extra sets were last bound, the lookup would
return the set already bound in this command buffer, whose ownership and references this command buffer already holds
(Auto keeps a referenced resource alive until the command buffer completes): the lookup and the bind are redundant.

Change: when neither the texture nor the image flag is raised, an extra set holding a texture, sampler or image array is
left bound. Arrays of buffer textures and buffer images keep the delivered path (their views can change without a setter).
Counted on the existing pass detail line through the array counters (current binds, reference passes). Fail closed on
drift: the file must be the Core 713 preparation's.
"""
import hashlib
from adapt_session import once

UPDATER = 'src/Ryujinx.Graphics.Vulkan/DescriptorSetUpdater.cs'
BASELINE = {
    UPDATER: '73731a106dd90e3fd764131d57f0fe236c95ba1e3ec000bd8217e4970ab6821d',
}

CALL_OLD = '''                // Program is using extra sets, we need to bind those too.

                BindExtraSets(cbs, program, pbp);
'''
CALL_NEW = '''                // Program is using extra sets, we need to bind those too.
                // RewindBox (adapt_extra_set_binds): without a texture or image change since their last bind, the array sets
                // bound in this command buffer are still bound and still current.

                BindExtraSets(cbs, program, pbp, arraysKept: (_dirty & (DirtyFlags.Texture | DirtyFlags.Image)) == 0);
'''

SIGNATURE_OLD = '''        private void BindExtraSets(CommandBufferScoped cbs, ShaderCollection program, PipelineBindPoint pbp)
        {
'''
SIGNATURE_NEW = '''        private void BindExtraSets(CommandBufferScoped cbs, ShaderCollection program, PipelineBindPoint pbp, bool arraysKept = false)
        {
'''

LOOP_OLD = '''                ResourceBindingSegment segment = bindingSegments[0];

                if (segment.IsArray)
                {
                    DescriptorSet[] sets = null;
'''
LOOP_NEW = '''                ResourceBindingSegment segment = bindingSegments[0];

                // RewindBox (adapt_extra_set_binds): a texture, sampler or image array set left bound (buffer views can change
                // without a setter: those arrays keep the delivered path).
                if (arraysKept && segment.IsArray && segment.Type is not (ResourceType.BufferTexture or ResourceType.BufferImage))
                {
                    continue;
                }

                if (segment.IsArray)
                {
                    DescriptorSet[] sets = null;
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    once(paths[UPDATER], CALL_OLD, CALL_NEW)
    once(paths[UPDATER], SIGNATURE_OLD, SIGNATURE_NEW)
    once(paths[UPDATER], LOOP_OLD, LOOP_NEW)
    return list(paths.values())

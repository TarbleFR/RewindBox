"""Buffer texture and image arrays queue no image write-to-read barrier (render worker NullReferenceException).

IPA 666 (MeloNX Core 663), Hogwarts Legacy, pid 15186 (private journals, not in the repository): after 21 minutes of
play the render worker died with

    System.NullReferenceException
       at Ryujinx.Graphics.Vulkan.TextureArray.QueueWriteToReadBarriers(CommandBufferScoped, PipelineStageFlags) + 0x78
       at Ryujinx.Graphics.Vulkan.DescriptorSetUpdater.SetTextureArraySeparate(CommandBufferScoped, ShaderStage, ...)

one second after the shader translator logged "Bound bindless TextureSample TextureBuffer through the whole texture
pool (extended handle source)". The session then ended ("Session termination is unproven; restart RewindBox"); the
maintainer saw the game close by itself.

Mechanism, in the Core 663 preparation:
- adapt_bindless_sources binds a bindless TextureBuffer access whose handle no exact rule finds through the whole texture
  pool. The GPU layer then binds a separate buffer texture array (TextureArray created with isBuffer: true) through
  DescriptorSetUpdater.SetTextureArraySeparate, which calls QueueWriteToReadBarriers on every TextureArray it binds.
- A buffer TextureArray holds buffer views only: its constructor allocates _bufferTextureRefs and leaves _views null
  (upstream: _textureRefs null). QueueWriteToReadBarriers walks _views.Length with _storagesDirty initially true, so the
  first separate bind of a buffer array throws. ImageArray has the same constructor split and the same walk of
  _textureRefs (SetImageArraySeparate, a whole-pool imageBuffer access).
- The per-binding path queues no image barrier for a buffer texture either: DescriptorSetUpdater.SetTextureAndSampler and
  SetImage queue QueueWriteToReadBarrier only for a TextureView; a TextureBuffer's buffer is ordered by its own buffer
  tracking when its view is fetched (GetBufferView), unchanged here.

Change: TextureArray.QueueWriteToReadBarriers and ImageArray.QueueWriteToReadBarriers return at once for a buffer array
(_isBuffer, set by the constructor and never changed). Texture and image arrays of views run exactly as before. Applies to
every title (the call threw for any buffer array bound separately; nothing else changes).

Not changed: which arrays are bound, their descriptors, the buffer views and their buffer barriers, every other array
member, the per-binding path. Not measured on an iPhone; on a device the proof is a Hogwarts session past the scene that
first binds the whole-pool TextureBuffer array without "Render worker failed".
Fail closed on drift: each file must be the Core 663 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.Vulkan/TextureArray.cs': '97869b487d1ffa4d96dd4994bd4cd4f0d2e43a1faf9309d4de147fa3f1e4625a',
    'src/Ryujinx.Graphics.Vulkan/ImageArray.cs': 'cf238484e0218aaf4082271bd328187fac89014313b2ec63609580de47799515',
}

TEXTURE_OLD = '''        public void QueueWriteToReadBarriers(CommandBufferScoped cbs, PipelineStageFlags stageFlags)
        {
            HashSet<TextureStorage> storages = _storages;
'''
TEXTURE_NEW = '''        public void QueueWriteToReadBarriers(CommandBufferScoped cbs, PipelineStageFlags stageFlags)
        {
            // RewindBox (adapt_buffer_array_barriers): a buffer texture array holds buffer views only (_views is null), and
            // like a buffer texture bound alone it queues no image barrier. Its first separate bind (a whole-pool
            // TextureBuffer access, adapt_bindless_sources) ended the render worker here (IPA 666).
            if (_isBuffer)
            {
                return;
            }

            HashSet<TextureStorage> storages = _storages;
'''

IMAGE_OLD = '''        public void QueueWriteToReadBarriers(CommandBufferScoped cbs, PipelineStageFlags stageFlags)
        {
            HashSet<TextureStorage> storages = _storages;
'''
IMAGE_NEW = '''        public void QueueWriteToReadBarriers(CommandBufferScoped cbs, PipelineStageFlags stageFlags)
        {
            // RewindBox (adapt_buffer_array_barriers): a buffer image array holds buffer views only (_textureRefs is null),
            // and like a buffer image bound alone it queues no image barrier.
            if (_isBuffer)
            {
                return;
            }

            HashSet<TextureStorage> storages = _storages;
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    once(paths['src/Ryujinx.Graphics.Vulkan/TextureArray.cs'], TEXTURE_OLD, TEXTURE_NEW)
    once(paths['src/Ryujinx.Graphics.Vulkan/ImageArray.cs'], IMAGE_OLD, IMAGE_NEW)
    return list(paths.values())

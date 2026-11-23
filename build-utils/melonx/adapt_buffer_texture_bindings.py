"""Resolve a bound buffer texture once while its handle, pools and texture stay as they were, as other textures are.

IPA 822, Hogwarts Legacy, one 5.5 s window (private performance journal, counts and durations only): 151,232 draws and
7,978 dispatches; gpuWork.bindings 158,472 calls, 716.5 ms, 29,408 KiB allocated; compute 7,774 calls, 665 ms. A
private disk shader cache of the title (1,468 graphics and 493 compute programs, never in the repository; read on the
host through the production loader and translator, counts only) declares 3.5 buffer textures per graphics program on
average (82 % of the programs have some) and 4.8 per compute program (94.5 %), against 10.2 and 5.4 textures in all.

Cause. TextureBindingsManager.CommitTextureBindings and CommitImageBindings keep, per binding slot, the texture they
resolved, and the next commit with the same handle, unmodified pools and a texture whose InvalidatedSequence did not
move takes the fast path. A buffer texture never did ("Cache is not used for buffer texture, it must always rebind"):
every commit of every draw and dispatch looked it up again: SamplerPool.Get, TexturePool.GetForBinding (Items[id],
one or two reads of the 32-byte descriptor through the CPU memory manager, TryGetVirtualContiguous and the partition
walk of MemoryManagerHostTracked), ShaderSpecializationState.MatchesTexture, GetTargetTexture and GetHostSampler, only
to pass the same host texture and range to BufferManager.SetBufferTextureStorage. What must happen at every commit is
that call: the buffer the texture reads may have been recreated, so its storage is bound again.

Change. A buffer texture resolved by the full path records, in its slot, the texture, the sampler, the binding target,
the texture's InvalidatedSequence, the descriptor read and the specialization state, binding index and answer of its
MatchesTexture (MatchesImage). The next commit of that slot with the same texture and sampler ids (and, for an image,
the same format), the same target, neither pool modified (the condition of the existing fast path, which a pool change
or Rebind also clears), a texture whose sequence did not move and a sampler not disposed, takes a fast path: the use
stamp TexturePool.GetInternal gives (Texture.SynchronizeMemory, which for a buffer texture only stamps LastUseEpoch),
the host texture read again (GetTargetTexture, as the full path), and the same SetBufferTextureStorage call with the
texture's current Range. The specialization answer is the recorded one when the specialization state and index are the
same objects, else MatchesTexture (MatchesImage) on the recorded descriptor. A slot resolved by the other branch of the
full path forgets its buffer texture, so the existing paths and their fields (Texture, CachedTexture,
InvalidatedSequence) are written exactly as before. Nothing else changes: the backend receives the same calls in the
same order, the buffer cache the same requests.

Measured on the host only (test/melonx_buffer_texture_bindings_test.py: the production Ryujinx.Graphics.Gpu of control
and candidate, a recording GAL double, guest command buffers through GPFifo with real shader translation, 40,000 draws
and 2,122 dispatches, five alternate runs on a shared x86-64 host): the same backend calls, data and bound bytes at
every draw; texture lookups for a binding 244,603 -> 64,283, sampler lookups 258,987 -> 78,667, descriptor reads from
guest memory 623,866 -> 261,355; GPU thread CPU time median 177.4 -> 164.0 ms (best 166.8 -> 153.9 ms), gpuWork.bindings
median 67.9 -> 57.0 ms for the same 42,122 calls; allocations unchanged (1,519,416 bytes). Not measured on an iPhone:
the device share is known only from the next build's gpuWork.bindings and compute lines.
Fail closed on drift: the file must be the preparation's after every adapter before this one.
"""
import hashlib
from adapt_session import once

BINDINGS = 'src/Ryujinx.Graphics.Gpu/Image/TextureBindingsManager.cs'

BASELINE = {
    BINDINGS: '1dda6c3dc770bff14443371c82c9d18e2c0a47deb7b843d691fb9926a5c6e6de',
}

TAG = 'RewindBox (adapt_buffer_texture_bindings)'

PAIRS = (
    ('''            public int InvalidatedSequence;
            public Texture CachedTexture;
            public Sampler CachedSampler;
        }
''', '''            public int InvalidatedSequence;
            public Texture CachedTexture;
            public Sampler CachedSampler;

            // RewindBox (adapt_buffer_texture_bindings): the buffer texture the full path resolved last in this slot (null
            // once the slot resolves anything else), what it was resolved with and the specialization answer it gave.
            public Texture BufferTexture;
            public Texture BufferPoolItem;
            public Sampler BufferSampler;
            public Target BufferTarget;
            public int BufferInvalidatedSequence;
            public TextureDescriptor BufferDescriptor;
            public ShaderSpecializationState BufferSpecState;
            public int BufferIndex;
            public bool BufferMatches;
        }
'''),
    ('''                    continue;
                }

                state.TextureHandle = textureId;
                state.SamplerHandle = samplerId;

                Sampler sampler = samplerPool?.Get(samplerId);
''', '''                    continue;
                }

                // RewindBox (adapt_buffer_texture_bindings): the buffer texture this slot resolved, still valid under the
                // conditions of the fast path above: its storage is bound again, as the full path below would.
                if (!poolModified &&
                    state.BufferTexture != null &&
                    state.TextureHandle == textureId &&
                    state.SamplerHandle == samplerId &&
                    state.BufferTarget == bindingInfo.Target &&
                    state.BufferTexture.InvalidatedSequence == state.BufferInvalidatedSequence &&
                    state.BufferSampler?.IsDisposed != true &&
                    texturePool.GetCachedItem(textureId) == state.BufferPoolItem)
                {
                    Texture bufferTexture = state.BufferTexture;
                    ITexture bufferHost = bufferTexture.GetTargetTexture(bindingInfo.Target);

                    if (bufferHost != null)
                    {
                        // The use stamp TexturePool.GetInternal gives its item (a buffer texture has no data to synchronise).
                        state.BufferPoolItem.SynchronizeMemory();

                        specStateMatches &= BufferSpecializationMatches(ref state, specState, stage, index, isImage: false);

                        _channel.BufferManager.SetBufferTextureStorage(stage, bufferHost, bufferTexture.Range, bindingInfo, false);

                        continue;
                    }
                }

                state.TextureHandle = textureId;
                state.SamplerHandle = samplerId;

                Sampler sampler = samplerPool?.Get(samplerId);
'''),
    ('''                specStateMatches &= specState.MatchesTexture(stage, index, descriptor);

                ITexture hostTexture = texture?.GetTargetTexture(bindingInfo.Target);
                ISampler hostSampler = sampler?.GetHostSampler(texture);
''', '''                bool textureMatches = specState.MatchesTexture(stage, index, descriptor); // RewindBox (adapt_buffer_texture_bindings)

                specStateMatches &= textureMatches;

                ITexture hostTexture = texture?.GetTargetTexture(bindingInfo.Target);
                ISampler hostSampler = sampler?.GetHostSampler(texture);
'''),
    ('''                    _channel.BufferManager.SetBufferTextureStorage(stage, hostTexture, texture.Range, bindingInfo, false);

                    // Cache is not used for buffer texture, it must always rebind.
                    state.CachedTexture = null;
                }
                else
                {
''', '''                    _channel.BufferManager.SetBufferTextureStorage(stage, hostTexture, texture.Range, bindingInfo, false);

                    // Cache is not used for buffer texture, it must always rebind.
                    state.CachedTexture = null;

                    RecordBufferTexture(ref state, texture, texturePool.GetCachedItem(textureId), sampler, bindingInfo.Target, descriptor, specState, index, textureMatches);
                }
                else
                {
                    state.BufferTexture = null; // RewindBox (adapt_buffer_texture_bindings)
'''),
    ('''                    continue;
                }

                state.TextureHandle = textureId;
                state.ImageFormat = bindingInfo.FormatInfo.Format;
''', '''                    continue;
                }

                // RewindBox (adapt_buffer_texture_bindings): as for buffer textures, an image of a buffer still valid.
                if (!poolModified &&
                    state.BufferTexture != null &&
                    state.TextureHandle == textureId &&
                    state.ImageFormat == bindingInfo.FormatInfo.Format &&
                    state.BufferTarget == bindingInfo.Target &&
                    state.BufferTexture.InvalidatedSequence == state.BufferInvalidatedSequence &&
                    pool.GetCachedItem(textureId) == state.BufferPoolItem)
                {
                    Texture bufferTexture = state.BufferTexture;
                    ITexture bufferHost = bufferTexture.GetTargetTexture(bindingInfo.Target);

                    if (bufferHost != null)
                    {
                        // The use stamp TexturePool.GetInternal gives its item.
                        state.BufferPoolItem.SynchronizeMemory();

                        specStateMatches &= BufferSpecializationMatches(ref state, specState, stage, index, isImage: true);

                        _channel.BufferManager.SetBufferTextureStorage(stage, bufferHost, bufferTexture.Range, bindingInfo, true);

                        continue;
                    }
                }

                state.TextureHandle = textureId;
                state.ImageFormat = bindingInfo.FormatInfo.Format;
'''),
    ('''                specStateMatches &= specState.MatchesImage(stage, index, descriptor);
''', '''                bool imageMatches = specState.MatchesImage(stage, index, descriptor); // RewindBox (adapt_buffer_texture_bindings)

                specStateMatches &= imageMatches;
'''),
    ('''                    _channel.BufferManager.SetBufferTextureStorage(stage, hostTexture, texture.Range, bindingInfo, true);

                    // Cache is not used for buffer texture, it must always rebind.
                    state.CachedTexture = null;
                }
                else
                {
''', '''                    _channel.BufferManager.SetBufferTextureStorage(stage, hostTexture, texture.Range, bindingInfo, true);

                    // Cache is not used for buffer texture, it must always rebind.
                    state.CachedTexture = null;

                    RecordBufferTexture(ref state, texture, pool.GetCachedItem(textureId), null, bindingInfo.Target, descriptor, specState, index, imageMatches);
                }
                else
                {
                    state.BufferTexture = null; // RewindBox (adapt_buffer_texture_bindings)
'''),
    ('''        /// <summary>
        /// Gets the texture descriptor for a given texture handle.
        /// </summary>''', '''        // RewindBox (adapt_buffer_texture_bindings): what the full path resolved a buffer texture (or image) with.
        private static void RecordBufferTexture(
            ref TextureState state,
            Texture texture,
            Texture poolItem,
            Sampler sampler,
            Target target,
            in TextureDescriptor descriptor,
            ShaderSpecializationState specState,
            int index,
            bool matches)
        {
            // Without a pool item (never the case after GetInternal resolved the texture) the slot keeps the full path.
            state.BufferTexture = poolItem != null ? texture : null;
            state.BufferPoolItem = poolItem;
            state.BufferSampler = sampler;
            state.BufferTarget = target;
            state.BufferInvalidatedSequence = texture.InvalidatedSequence;
            state.BufferDescriptor = descriptor;
            state.BufferSpecState = specState;
            state.BufferIndex = index;
            state.BufferMatches = matches;
        }

        // RewindBox (adapt_buffer_texture_bindings): the specialization answer of the full path. The same state and index
        // give the answer recorded with the same descriptor; another shader's state is asked about the recorded descriptor
        // (the pool was not modified since it was read).
        private static bool BufferSpecializationMatches(ref TextureState state, ShaderSpecializationState specState, ShaderStage stage, int index, bool isImage)
        {
            if (ReferenceEquals(state.BufferSpecState, specState) && state.BufferIndex == index)
            {
                return state.BufferMatches;
            }

            bool matches = isImage
                ? specState.MatchesImage(stage, index, state.BufferDescriptor)
                : specState.MatchesTexture(stage, index, state.BufferDescriptor);

            state.BufferSpecState = specState;
            state.BufferIndex = index;
            state.BufferMatches = matches;

            return matches;
        }

        /// <summary>
        /// Gets the texture descriptor for a given texture handle.
        /// </summary>'''),
)

FILE_PAIRS = {BINDINGS: PAIRS}


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, pairs in FILE_PAIRS.items():
        for old, new in pairs:
            once(paths[name], old, new)
    return list(paths.values())

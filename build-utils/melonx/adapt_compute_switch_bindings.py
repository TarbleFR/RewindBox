"""A switch between compute and graphics re-sends the bound textures instead of resolving them again (Core 693).

IPA 691 (Hogwarts Legacy, pid 34380, Core 691), core-performance windows in play (5.1 s each, private journal): the
GPU thread executes command lists 2.2-3.7 s per window and its largest item is gpuWork.bindings, 0.9-1.5 s (about
100 000 commits), ahead of compute (0.7-1.2 s); the game dispatches 1 500-2 500 compute grids per second between its
draws (render-to-compute switches 350-480 and compute-to-render 460-710 per 5 s in the Vulkan pass lines).

Cause (upstream TextureManager.CommitComputeBindings): "since compute work happens less often", every dispatch calls
TextureBindingsManager.Rebind() on the compute bindings before committing them and on the graphics bindings after.
Rebind clears every TextureState and ImageState, so the next commit resolves every bound texture again (sampler pool
Get, texture pool GetForBinding, host sampler, specialization match) only because the backend's binding slots, shared
by compute and graphics, were overwritten.

Change (every title): CommitComputeBindings calls RebindHost() instead, which keeps the resolution and marks the
manager so that its next commit re-sends every binding to the backend: a binding whose cached state is still valid
(same pool sequence, handles, image format, InvalidatedSequence and undisposed sampler: the existing fast path, with
its SynchronizeMemory, SignalModified and scale update) re-sends the cached host texture and sampler; any other binding
is resolved as before and always sent. Texture buffers, texture arrays, pool changes (Rebind on a new pool), channel
switches (TextureManager.Rebind) and every other caller keep the full Rebind. The flag is cleared after the commit.
Not measured on an iPhone. Fail closed on drift: both files must be the Core 691 preparation's.
"""
import hashlib
from adapt_session import once

MANAGER = 'src/Ryujinx.Graphics.Gpu/Image/TextureManager.cs'
BINDINGS = 'src/Ryujinx.Graphics.Gpu/Image/TextureBindingsManager.cs'
BASELINE = {
    MANAGER: 'f8c92175d86d9685937e6be5de65a5de609ced0eae7b1cc119bc2beccd6c3de0',
    BINDINGS: '450aedf92e0d8ca4d5699ab370d40d9589b7f58f2326c77490879b258bce24c2',
}

COMPUTE_OLD = '''            _cpBindingsManager.Rebind();
            bool result = _cpBindingsManager.CommitBindings(specState);
            _gpBindingsManager.Rebind();
'''
COMPUTE_NEW = '''            // RewindBox (adapt_compute_switch_bindings): the other pipeline overwrote the backend's binding slots; the
            // resolved bindings stay valid and are re-sent, not looked up again.
            _cpBindingsManager.RebindHost();
            bool result = _cpBindingsManager.CommitBindings(specState);
            _gpBindingsManager.RebindHost();
'''

REBIND_OLD = '''        public void Rebind()
        {
            Array.Clear(_textureState);
            Array.Clear(_imageState);
        }
'''
REBIND_NEW = '''        public void Rebind()
        {
            Array.Clear(_textureState);
            Array.Clear(_imageState);
        }

        // RewindBox (adapt_compute_switch_bindings): the backend's slots were overwritten by the other pipeline (compute
        // or graphics). The next commit re-sends every binding; bindings whose cached state is still valid are not
        // resolved again.
        private bool _resendHost;

        public void RebindHost()
        {
            _resendHost = true;
        }
'''

COMMIT_OLD = '''            CommitRenderScale();

            return specStateMatches;
        }
'''
COMMIT_NEW = '''            CommitRenderScale();

            _resendHost = false; // RewindBox (adapt_compute_switch_bindings)

            return specStateMatches;
        }
'''

TEX_FAST_OLD = '''                    // The texture is already bound.
                    state.CachedTexture.SynchronizeMemory();

                    if ((usageFlags & TextureUsageFlags.NeedsScaleValue) != 0 &&
                        UpdateScale(state.CachedTexture, usageFlags, index, stage))
                    {
                        ITexture hostTextureRebind = state.CachedTexture.GetTargetTexture(bindingInfo.Target);

                        state.Texture = hostTextureRebind;

                        _context.Renderer.Pipeline.SetTextureAndSampler(stage, bindingInfo.Binding, hostTextureRebind, state.Sampler);
                    }

                    continue;
'''
TEX_FAST_NEW = '''                    // The texture is already bound.
                    state.CachedTexture.SynchronizeMemory();

                    if ((usageFlags & TextureUsageFlags.NeedsScaleValue) != 0 &&
                        UpdateScale(state.CachedTexture, usageFlags, index, stage))
                    {
                        ITexture hostTextureRebind = state.CachedTexture.GetTargetTexture(bindingInfo.Target);

                        state.Texture = hostTextureRebind;

                        _context.Renderer.Pipeline.SetTextureAndSampler(stage, bindingInfo.Binding, hostTextureRebind, state.Sampler);
                    }
                    else if (_resendHost)
                    {
                        // RewindBox (adapt_compute_switch_bindings): the backend slot was overwritten; re-send it.
                        _context.Renderer.Pipeline.SetTextureAndSampler(stage, bindingInfo.Binding, state.Texture, state.Sampler);
                    }

                    continue;
'''
TEX_SLOW_OLD = '''                    bool textureOrSamplerChanged = state.Texture != hostTexture || state.Sampler != hostSampler;
'''
TEX_SLOW_NEW = '''                    // RewindBox (adapt_compute_switch_bindings): after a pipeline switch the slot is always sent.
                    bool textureOrSamplerChanged = _resendHost || state.Texture != hostTexture || state.Sampler != hostSampler;
'''

IMG_FAST_OLD = '''                    if ((usageFlags & TextureUsageFlags.NeedsScaleValue) != 0 && UpdateScale(state.CachedTexture, usageFlags, scaleIndex, stage))
                    {
                        ITexture hostTextureRebind = state.CachedTexture.GetTargetTexture(bindingInfo.Target);

                        state.Texture = hostTextureRebind;

                        _context.Renderer.Pipeline.SetImage(stage, bindingInfo.Binding, hostTextureRebind);
                    }

                    continue;
'''
IMG_FAST_NEW = '''                    if ((usageFlags & TextureUsageFlags.NeedsScaleValue) != 0 && UpdateScale(state.CachedTexture, usageFlags, scaleIndex, stage))
                    {
                        ITexture hostTextureRebind = state.CachedTexture.GetTargetTexture(bindingInfo.Target);

                        state.Texture = hostTextureRebind;

                        _context.Renderer.Pipeline.SetImage(stage, bindingInfo.Binding, hostTextureRebind);
                    }
                    else if (_resendHost)
                    {
                        // RewindBox (adapt_compute_switch_bindings): the backend slot was overwritten; re-send it.
                        _context.Renderer.Pipeline.SetImage(stage, bindingInfo.Binding, state.Texture);
                    }

                    continue;
'''
IMG_SLOW_OLD = '''                    if (state.Texture != hostTexture)
                    {
                        state.Texture = hostTexture;

                        _context.Renderer.Pipeline.SetImage(stage, bindingInfo.Binding, hostTexture);
                    }
'''
IMG_SLOW_NEW = '''                    if (_resendHost || state.Texture != hostTexture) // RewindBox (adapt_compute_switch_bindings)
                    {
                        state.Texture = hostTexture;

                        _context.Renderer.Pipeline.SetImage(stage, bindingInfo.Binding, hostTexture);
                    }
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    once(paths[MANAGER], COMPUTE_OLD, COMPUTE_NEW)
    bindings = paths[BINDINGS]
    once(bindings, REBIND_OLD, REBIND_NEW)
    once(bindings, COMMIT_OLD, COMMIT_NEW)
    once(bindings, TEX_FAST_OLD, TEX_FAST_NEW)
    once(bindings, TEX_SLOW_OLD, TEX_SLOW_NEW)
    once(bindings, IMG_FAST_OLD, IMG_FAST_NEW)
    once(bindings, IMG_SLOW_OLD, IMG_SLOW_NEW)
    return list(paths.values())

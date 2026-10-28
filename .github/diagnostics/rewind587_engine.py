"""The MeloNX engine of private 587, bound with the 586 engine checks.

587 changes the engine of 586 (75a13f7) by ENGINE_COMMITS:
- adapt_device_memory.py: the GPU caches are trimmed when the device, not
  only this process, runs short of memory (kern.memorystatus_level at 7 % or
  less), and one Info line every 30 s says where the memory is (Hogwarts
  Legacy, build 586, 28 October 2026: 90 s at 4-7 % device memory ran at a
  median 4-6 FPS; nothing was released).
- adapt_bindless_sources.py: the bindless handle forms the 586 diagnostic
  named in the same log bind instead of reading 0.

The engine is built and tested by its own run of melonx-core.yml (the
workflow of 577 to 586, the same steps). Every check rewind586_delivery
applies to the 586 engine (exports, the 572-586 adaptation markers, the
decoder, texture pool, journal, session, display and simulator receipts, each
adaptation equal to its commit) is applied here to the 587 engine:
rewind586_delivery's engine constants are set to the 587 ones below, the 586
markers whose count the 587 adaptations change are updated, and the 587
markers are checked on the adapted source the run compiled. Earlier engines,
runs and builds are not proved again (maintainer rule of 28 October 2026).
"""
import json
import zipfile

import rewind586_fast  # noqa: F401  (batched existence checks for the 586 recipe modules)
import rewind586_delivery as d586

MELONX_SOURCE = 'b2a28defbeafe67addf7b2d295ffd928b39e91ea'
MELONX_RUN = 40788062624
MELONX_ARTIFACT = (12861340590, 'f284dd5ce66d11761e0491d91dd83461a1e5ec7d028683c7b5dd05a07315b2d5')
ENGINE_COMMITS = ['983f3016389b904a9882339833ad2e5fefc6898c', 'b2a28defbeafe67addf7b2d295ffd928b39e91ea']
ENGINE587 = {'build-utils/melonx/adapt_device_memory.py', 'build-utils/melonx/adapt_bindless_sources.py',
             'build-utils/melonx/prepare_embedded.py'}
# What the 587 adaptations must have put into the adapted engine source, and how often.
ADAPTED587 = {
    'src/Ryujinx.Memory/HostMemoryBudget.cs': {
        'public static unsafe int DeviceAvailablePercent': 1,
        'SysctlByName("kern.memorystatus_level", &level, &size, null, 0)': 1},
    'src/Ryujinx.Graphics.Gpu/GpuContext.cs': {
        'public void CheckHostMemory()': 1, 'private const int DeviceShortPercent = 7;': 1,
        'if (available >= ComfortableHeadroomBytes && !deviceShort)': 1,
        'if (available >= ComfortableHeadroomBytes)\n': 0,
        '$"Host memory: footprint {HostMemoryBudget.FootprintBytes / TrimMiB} MiB, " +': 1},
    'src/Ryujinx.HLE/Switch.cs': {'Gpu.CheckHostMemory();': 1},
    'src/Ryujinx.Graphics.Gpu/Image/TextureCache.cs': {'public ulong CachedBytes => _cache.TotalSize;': 1},
    'src/Ryujinx.Graphics.Gpu/Image/AutoDeleteCache.cs': {'public ulong TotalSize => _totalSize;': 1},
    'src/Ryujinx.Graphics.Gpu/Memory/BufferCache.cs': {'public ulong CachedBytes => _cachedBufferBytes;': 1},
    'src/Ryujinx.Graphics.Shader/Translation/Optimizations/BindlessElimination.cs': {
        'private static bool TryBindExtendedSources(': 1,
        '!TryBindExtendedSources(block, resourceManager, gpuAccessor, texOp, node))': 1,
        'private static Operand GetSpilledHandleSource(Operand handle, BasicBlock useBlock)': 1,
        'private static bool AreAllPhiLeavesSame(': 1, 'private static bool IsHandleFromMemory(Operand handle)': 1,
        'else if (!texOp.Inst.IsImageStore() &&': 1, '(extended handle source)': 1},
    'src/Ryujinx.Graphics.Gpu/Shader/DiskCache/DiskCacheHostStorage.cs': {
        'private const uint CodeGenVersion = 7353 + 0x5242_0002;': 1},
}
# 586 markers whose count the 587 adaptations change.
OVERRIDES586 = {'src/Ryujinx.Graphics.Gpu/Shader/DiskCache/DiskCacheHostStorage.cs': {
    'private const uint CodeGenVersion = 7353 + 0x5242_0001;': 0}}

d586.MELONX_SOURCE, d586.MELONX_RUN, d586.MELONX_ARTIFACT = MELONX_SOURCE, MELONX_RUN, MELONX_ARTIFACT
d586.ENGINE586 = set(d586.ENGINE586) | ENGINE587
for _name, _texts in OVERRIDES586.items():
    d586.ADAPTED586[_name] = dict(d586.ADAPTED586.get(_name, {}), **_texts)
EXPORTS = d586.EXPORTS586
SYMBOLS = d586.SYMBOLS586
CORE_TEXT = d586.CORE_TEXT586
sha = d586.sha
NEW = d586.NEW


def engine_run():
    """The engine run: the exact commit, its own workflow, every engine step passed."""
    state = d586.previous.api(f'actions/runs/{MELONX_RUN}')
    assert state['head_sha'] == MELONX_SOURCE and state['path'] == d586.MELONX_WORKFLOW, (state['head_sha'], state['path'])
    return d586.previous.completed(MELONX_RUN, MELONX_SOURCE, d586.ENGINE_STEPS586)


def engine_identity():
    return d586.engine_identity()


def engine_evidence():
    """The 586 engine checks on the 587 engine, then the 587 adaptations in the source it compiled."""
    evidence = d586.engine_evidence()
    inputs = json.loads((NEW / 'embedded-inputs.json').read_bytes())
    for path in sorted(ENGINE587):
        assert path in inputs and inputs[path] == sha(path), path
    with zipfile.ZipFile(NEW / 'embedded-adapted-source.zip') as z:
        for name, texts in ADAPTED587.items():
            source = z.read(name).decode('utf-8-sig')
            for text, count in texts.items():
                assert source.count(text) == count, (name, text, source.count(text))
    return dict(evidence, build=587, engineCommits=ENGINE_COMMITS, engine586Source=d586.tree.SOURCE586,
                adapted587=sorted(ADAPTED587), overrides586=OVERRIDES586, deviceMemoryTrim=True,
                bindlessHandleSources=True, imageStoresThroughWholePool=False)

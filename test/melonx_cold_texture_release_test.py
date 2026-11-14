#!/usr/bin/env python3
"""Cold pool-only texture release under device memory pressure (adapt_cold_texture_release) on the real prepared engine.

Usage: melonx_cold_texture_release_test.py <Core 658 prepared MeloNX tree> [--work <dir>]
       melonx_cold_texture_release_test.py <control> --candidate-source <final preparation containing the adapter> [--work <dir>]
--work: where the candidate tree is copied and built (default: a temporary directory, removed at the end); its bin/obj
are removed at the end either way. The Xcode project (src/MeloNX) is not copied: no project built here uses it.

Applies the adapter to a copy of the Core 658 preparation. Static checks bind that each file equals the preparation once
the adapter's replacements are undone (nothing else changes), the wiring (GPU thread, after the device-short trim, the
30 s report line), the one statement added to Texture.SynchronizeMemory, and, in the preparation, the lifetime facts the
release relies on: sampler textures outside the auto delete cache, bound render targets and GPU writes take a reference
or the cache, disposal moves InvalidatedSequence and releases the host texture through the GAL queue, cached bindings
and bindless arrays synchronise their textures and revalidate on InvalidatedSequence, and the Vulkan backend frees a
texture's memory only when the last command buffer using it completes.
Builds the production Ryujinx.Graphics.Gpu, then (test-only InternalsVisibleTo) executes test/melonx_cold_texture_release
against the compiled production GpuContext, TexturePool, Texture, TextureGroup, TextureCache and AutoDeleteCache, with
real guest memory and a recording GAL renderer: (a) release and re-creation from guest memory, (b) GPU-written data
kept, (c) no reload loop, (d) nothing when the device is not short, (e) per-pass bounds.
Writes dist/melonx/cold-texture-release-checks.json. No device, no Metal memory measurement, no FPS claim.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
ARGS = sys.argv[1:]
WORK_ARG = None
if '--work' in ARGS:
    WORK_ARG = Path(ARGS[ARGS.index('--work') + 1]).resolve()
SOURCE = Path(ARGS[ARGS.index('--candidate-source') + 1] if '--candidate-source' in ARGS else ARGS[0]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_cold_texture_release', _HOLD)
import adapt_cold_texture_release  # noqa: E402

def _forward_matches(module_name, work, final_source, names, tmp):
    """The candidate plus the later adapters sharing its files (re-applied forward) is the final preparation."""
    import importlib as _importlib
    from melonx_adapter_control import later_sharing as _later_sharing
    forward = Path(tmp) / ('forward-' + module_name)
    later = _later_sharing(module_name)
    files = set(names).union(*(set(_importlib.import_module(n).BASELINE) for n in later)) if later else set(names)
    for name in files:
        (forward / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(work / name, forward / name)
    for n in later:
        _importlib.import_module(n).apply(forward)
    return {name: (forward / name).read_bytes() == (final_source / name).read_bytes() for name in names}
from adapt_cold_texture_release import apply, BASELINE  # noqa: E402

GPU = 'src/Ryujinx.Graphics.Gpu/'
CONTEXT = GPU + 'GpuContext.cs'
POOL = GPU + 'Image/TexturePool.cs'
TEXTURE = GPU + 'Image/Texture.cs'
DOTNET = os.environ.get('DOTNET', 'dotnet')
HARNESS = ROOT / 'test/melonx_cold_texture_release'
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def member(text, signature):
    """One complete member, its exact body."""
    assert text.count(signature) == 1, signature
    start = text.rindex('\n', 0, text.index(signature)) + 1
    depth, index = 0, text.index('{', text.index(signature))
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


def read(root, name):
    return (root / name).read_text(encoding='utf-8-sig')


def where(root, name, needle):
    """file:line of a needle that must occur exactly once."""
    text = read(root, name)
    check(text.count(needle) == 1, f'{name}: once: {needle[:80]}')
    return f'{name}:{text[:text.index(needle)].count(chr(10)) + 1}'


for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 658 preparation: ' + name)

# Lifetime facts of the preparation the release relies on (file:line receipts).
proof = {}
proof['samplerTexturesOutsideAutoDeleteCache'] = where(SOURCE, GPU + 'Image/TextureCache.cs', '''            // Sampler textures are managed by the texture pool, all other textures
            // are managed by the auto delete cache.
            if (!isSamplerTexture)
            {
                _cache.Add(texture);
            }''')
proof['poolSlotDropsOnlyOnDescriptorChange'] = where(SOURCE, POOL, '''                    if (Interlocked.Exchange(ref Items[id], null) != null)
                    {
                        texture.DecrementReferenceCount(this, id);
                        RemoveAliasList(texture);
                    }''')
proof['poolFetchCreatesFromGuestMemory'] = where(SOURCE, POOL, '''                    TextureInfo info = GetInfo(descriptor, out int layerSize);
                    texture = PhysicalMemory.TextureCache.FindOrCreateTexture(_channel.MemoryManager, TextureSearchFlags.ForSampler, info, layerSize);''')
texture_source = read(SOURCE, TEXTURE)
check('IncrementReferenceCount();' in member(texture_source, 'public void SignalModifying(bool bound)') and
      '_physicalMemory.TextureCache.Lift(this);' in member(texture_source, 'public void SignalModifying(bool bound)'),
      'a bound render target holds a reference and the auto delete cache')
proof['boundRenderTargetHoldsReference'] = where(SOURCE, TEXTURE, '        public void SignalModifying(bool bound)')
check('_physicalMemory.TextureCache.Lift(this);' in member(texture_source, 'public void SignalModified()'),
      'a GPU write lifts the texture into the auto delete cache')
proof['gpuWriteLiftsIntoAutoDeleteCache'] = where(SOURCE, TEXTURE, '        public void SignalModified()')
check('IncrementReferenceCount();' in member(texture_source, 'private void AddView(Texture texture)'), 'a view holds a reference to its storage')
proof['viewHoldsReference'] = where(SOURCE, TEXTURE, '        private void AddView(Texture texture)')
decrement = member(texture_source, 'public bool DecrementReferenceCount()')
check('_physicalMemory.TextureCache.RemoveTextureFromCache(this);' in decrement and 'DeleteIfNotUsed();' in decrement and
      'if (_referenceCount == 0 && _views.Count == 0)' in member(texture_source, 'private void DeleteIfNotUsed()'),
      'the last reference removes the texture from the cache and disposes it when it has no view')
proof['lastReferenceDisposes'] = where(SOURCE, TEXTURE, '        public bool DecrementReferenceCount()')
dispose = member(texture_source, 'private void DisposeTextures()')
check(dispose.index('InvalidatedSequence++;') < dispose.index('HostTexture.Release();'), 'disposal moves InvalidatedSequence and releases the host texture')
proof['disposalMovesSequenceAndReleasesHost'] = where(SOURCE, TEXTURE, '        private void DisposeTextures()')
group = read(SOURCE, GPU + 'Image/TextureGroupHandle.cs')
check(re.search(r'public void DeferCopy\(TextureGroupHandle copyFrom\)\s*\{\s*Modified = false;', group) is not None,
      'a deferred copy clears Modified: copy dependencies are excluded separately')
proof['deferredCopyClearsModified'] = where(SOURCE, GPU + 'Image/TextureGroupHandle.cs', '        public void DeferCopy(TextureGroupHandle copyFrom)')
cache = read(SOURCE, GPU + 'Image/AutoDeleteCache.cs')
check('oldestTexture.FlushModified(false);' in member(cache, 'private void RemoveLeastUsedTexture()'),
      'capacity eviction flushes untracked: the modified flags stay, the texture can be pool-only and modified')
proof['untrackedFlushKeepsModified'] = where(SOURCE, GPU + 'Image/AutoDeleteCache.cs', '                oldestTexture.FlushModified(false);')
manager = read(SOURCE, GPU + 'Image/TextureBindingsManager.cs')
check(manager.count('state.CachedTexture.InvalidatedSequence == state.InvalidatedSequence') == 2 and
      manager.count('state.CachedTexture.SynchronizeMemory();') == 1 and manager.count('cachedTexture.SynchronizeMemory();') == 1,
      'cached texture and image bindings synchronise each use and revalidate on InvalidatedSequence')
proof['cachedBindingSynchronisesAndRevalidates'] = where(SOURCE, GPU + 'Image/TextureBindingsManager.cs', '                    state.CachedTexture.SynchronizeMemory();')
arrays = read(SOURCE, GPU + 'Image/TextureBindingsArrayCache.cs')
check(re.search(r'foreach \(Texture texture in Textures\.Keys\)\s*\{\s*texture\.SynchronizeMemory\(\);', arrays) is not None and
      'if (texture.InvalidatedSequence != invalidatedSequence)' in arrays and
      'entry.ValidateTextures() &&\n                entry.SynchronizeMemoryAndValidate(isStore, resScaleUnsupported))' in arrays,
      'a bindless array synchronises every texture it binds at each use and is rebuilt when one was disposed')
proof['bindlessArraySynchronisesAndRevalidates'] = where(SOURCE, GPU + 'Image/TextureBindingsArrayCache.cs', '                foreach (Texture texture in Textures.Keys)')
switch = read(SOURCE, 'src/Ryujinx.HLE/Switch.cs')
frame = member(switch, 'public void ProcessFrame()')
check(frame.index('Gpu.CheckHostMemory();') < frame.index('Gpu.GPFifo.DispatchCalls();'), 'CheckHostMemory runs before the frame\'s commands')
proof['checkHostMemoryBetweenCommandLists'] = where(SOURCE, 'src/Ryujinx.HLE/Switch.cs', '            Gpu.CheckHostMemory();')
window = read(SOURCE, 'src/Ryujinx.Library/Window/WindowBase.cs')
check(window.index('Device.Gpu.SetGpuThread();') < window.index('Device.ProcessFrame();'), 'ProcessFrame runs on the GPU thread')
proof['processFrameOnGpuThread'] = where(SOURCE, 'src/Ryujinx.Library/Window/WindowBase.cs', '                        Device.ProcessFrame();')
threaded = read(SOURCE, 'src/Ryujinx.Graphics.GAL/Multithreading/Resources/ThreadedTexture.cs')
check(re.search(r'public unsafe void Release\(\)\s*\{\s*_renderer\.New<TextureReleaseCommand>\(\)->Set\(Ref\(this\)\);\s*_renderer\.QueueCommand\(\);', threaded) is not None,
      'a host texture release is queued after the commands already queued')
proof['releaseQueuedInOrder'] = where(SOURCE, 'src/Ryujinx.Graphics.GAL/Multithreading/Resources/ThreadedTexture.cs', '        public unsafe void Release()')
VK = 'src/Ryujinx.Graphics.Vulkan/'
view = read(SOURCE, VK + 'TextureView.cs')
check('_imageView.Dispose();' in member(view, 'protected virtual void Dispose(bool disposing)') and
      'Storage?.DecrementViewsCount();' in member(view, 'protected virtual void Dispose(bool disposing)'), 'Vulkan view release drops its Auto references')
proof['vulkanViewReleaseDropsAuto'] = where(SOURCE, VK + 'TextureView.cs', '                    _imageView.Dispose();')
storage = read(SOURCE, VK + 'TextureStorage.cs')
check('_imageAuto = new Auto<DisposableImage>(new DisposableImage(_gd.Api, device, _image), null, _allocationAuto);' in storage and
      '_imageAuto.Dispose();' in member(storage, 'public void Dispose()'), 'the image Auto holds its memory allocation')
proof['imageHoldsAllocation'] = where(SOURCE, VK + 'TextureStorage.cs', '                _imageAuto = new Auto<DisposableImage>(new DisposableImage(_gd.Api, device, _image), null, _allocationAuto);')
auto = read(SOURCE, VK + 'Auto.cs')
check(re.search(r'if \(_cbOwnership\.Set\(cbs\.CommandBufferIndex\)\)\s*\{\s*if \(_waitable != null\)\s*\{\s*cbs\.AddWaitable\(_waitable\);\s*\}\s*cbs\.AddDependant\(this\);', auto) is not None and
      re.search(r'if \(Interlocked\.Decrement\(ref _referenceCount\) == 0\)\s*\{\s*_value\.Dispose\(\);', auto) is not None,
      'each command buffer using an Auto holds a reference; the value is destroyed at the last one')
proof['commandBufferHoldsReference'] = where(SOURCE, VK + 'Auto.cs', '                cbs.AddDependant(this);')
proof['destroyedAtLastReference'] = where(SOURCE, VK + 'Auto.cs', '            if (Interlocked.Decrement(ref _referenceCount) == 0)')
pool_vk = read(SOURCE, VK + 'CommandBufferPool.cs')
# IPA 740 lot: adapt_signalled_fence_release skips the wait for a fence its caller just read signalled, and
# adapt_command_buffer_ownership stores the dependants as a struct (dependant.Value) and gives the objects an Auto
# references (image, memory) only their command-buffer bit: the Auto's constructor reference keeps them (checked below).
completion = member(pool_vk, 'private void WaitAndDecrementRef(int cbIndex, bool refreshFence = true, bool signaled = false)')
check(re.search(r'if \(entry\.InConsumption\)\s*\{\s*if \(!signaled\)\s*\{\s*entry\.Fence\.Wait\(\);', completion) is not None and
      completion.index('entry.Fence.Wait();') < completion.index('dependant.Value.DecrementReferenceCount(cbIndex);') and
      '(signaled = entry.Fence.IsSignaled())' in member(pool_vk, 'private int FreeConsumed(bool wait)') and
      'dependant.IncrementReferenceCount();' in member(pool_vk, 'public void AddDependant(int cbIndex, IAuto dependant)'),
      'the command buffer releases its references only after its fence signalled (waited for, or just read signalled)')
check(re.search(r'for \(int i = 0; i < referencedObjs\.Length; i\+\+\)\s*\{\s*referencedObjs\[i\]\.IncrementReferenceCount\(\);', auto) is not None and
      re.search(r'_value\.Dispose\(\);[\s\S]*?_referencedObjs\[i\]\.DecrementReferenceCount\(\);', auto) is not None,
      'an Auto keeps the objects it references until it is destroyed (the image its memory, a view its image)')
proof['releasedAfterFence'] = where(SOURCE, VK + 'CommandBufferPool.cs', '                dependant.Value.DecrementReferenceCount(cbIndex);')
blocks = read(SOURCE, VK + 'MemoryAllocatorBlockList.cs')
check('block.Destroy(_api, _device);' in member(blocks, 'public void Free(Block block, ulong offset, ulong size)'),
      'a totally free block is destroyed (vkFreeMemory)')
proof['memoryReturned'] = where(SOURCE, VK + 'MemoryAllocatorBlockList.cs', '        public void Free(Block block, ulong offset, ulong size)')
array_vk = read(SOURCE, VK + 'TextureArray.cs')
check('destroyed |= view.Get(cbs).Value.Handle == 0;' in array_vk, 'a Vulkan texture array detects a destroyed view')
proof['vulkanArrayDetectsDestroyedView'] = where(SOURCE, VK + 'TextureArray.cs', '                destroyed |= view.Get(cbs).Value.Handle == 0;')

replacements = {}
original_once = adapt_cold_texture_release.once
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')


def ignore(directory, names):
    skipped = {'.git', 'bin', 'obj'} & set(names)
    if Path(directory).resolve() == (SOURCE / 'src').resolve() and 'MeloNX' in names:
        skipped.add('MeloNX')
    return skipped


temporary = None
if WORK_ARG is None:
    temporary = tempfile.TemporaryDirectory(prefix='melonx-cold-texture-')
    WORK = Path(temporary.name).resolve()
else:
    WORK = WORK_ARG
    WORK.mkdir(parents=True, exist_ok=True)
work = WORK / 'candidate'
probe = WORK / 'probe'
for stale in (work, probe):
    if stale.exists():
        shutil.rmtree(stale)
report = None
try:
    shutil.copytree(SOURCE, work, ignore=ignore, symlinks=True)
    use_authenticated_libhac_feed(work, ROOT)

    def recording_once(path, old, new):
        replacements.setdefault(path.relative_to(work).as_posix(), []).append((old, new))
        original_once(path, old, new)

    adapt_cold_texture_release.once = recording_once
    try:
        changed = apply(work)
    finally:
        adapt_cold_texture_release.once = original_once
    check(sorted(p.relative_to(work).as_posix() for p in changed) == sorted(BASELINE), 'adapter changed other files')
    if FINAL_PREPARATION:
        # Later adapters editing these files (Core 691: adapt_released_texture_flush, Texture.cs) are re-applied forward.
        forward_ok = _forward_matches('adapt_cold_texture_release', work, FINAL_SOURCE, BASELINE, tempfile.mkdtemp(prefix='melonx-forward-'))
        for name in BASELINE:
            check(forward_ok[name], 'final preparation is the adapter: ' + name)
    for name in BASELINE:
        undone = read(work, name)
        for old, new in reversed(replacements[name]):
            check(undone.count(new) == 1, 'each replacement once: ' + new[:60])
            undone = undone.replace(new, old, 1)
        check(undone == read(SOURCE, name), name + ' is the preparation but the adapter\'s replacements')
    check([len(replacements[n]) for n in (TEXTURE, POOL, CONTEXT)] == [2, 4, 3], 'replacement counts')

    context = read(work, CONTEXT)
    control_context = read(SOURCE, CONTEXT)
    check(member(context, 'public void TrimCaches(MemoryPressureLevel level)') ==
          member(control_context, 'public void TrimCaches(MemoryPressureLevel level)'), 'TrimCaches unchanged')
    host = member(context, 'public void CheckHostMemory()')
    check(host.index('TrimCaches(device <= DeviceCriticalPercent') < host.index('TextureUseEpoch = (int)(now / 1000);') <
          host.index('ReleaseColdTextures(device, now, out _);') < host.index('if (now - _lastHostMemoryReport < HostMemoryReportIntervalMs)'),
          'use clock and release once a second after the device-short trim, before the 30 s report gate')
    check(host.index('if (!GraphicsConfig.EnableHostMemoryBudgetTracking || !HostMemoryBudget.IsConstrained)') <
          host.index('TextureUseEpoch'), 'only where host memory is tracked (iOS)')
    check(host.index('_lastHostMemoryReport = now;') < host.index('MeasurePoolTextures(out int reloads, out int pinned);') <
          host.index('foreach (PhysicalMemory physicalMemory in PhysicalMemoryRegistry.Values)'),
          'the pool-only line is written with the 30 s report, ahead of it')
    report_control = member(control_context, 'public void CheckHostMemory()')
    check(report_control[report_control.index('ulong textures = 0;'):] in host, 'the existing report is unchanged')
    release = member(context, 'internal bool ReleaseColdTextures(int device, long now, out ColdTextureStats stats)')
    check('device < 0 || device > ColdTextureDevicePercent' in release and 'now - _lastColdTextureRelease < ColdTextureIntervalMs' in release,
          'pass gates: device known and at most 10 %, 10 s apart')
    check(release.count('Logger.Info?.Print(') == 1 and 'return true;' in release, 'one journal line per pass')
    for constant in ('private const int ColdTextureDevicePercent = 10;', 'private const long ColdTextureIntervalMs = 10_000;',
                     'private const int ColdTextureInitialAgeSeconds = 60;', 'private const int ColdTextureMaximumAgeSeconds = 480;',
                     'internal const int ColdTextureReloadWindowSeconds = 300;',
                     'internal const ulong ColdTextureMaxBytesPerPass = 64 * TrimMiB;',
                     'internal const int ColdTextureMaxTexturesPerPass = 256;', 'private const int DeviceShortPercent = 7;'):
        check(context.count(constant) == 1, constant)
    texture = read(work, TEXTURE)
    sync = member(texture, 'public void SynchronizeMemory()')
    control_sync = member(texture_source, 'public void SynchronizeMemory()')
    check(sync.replace('''            // RewindBox (adapt_cold_texture_release): a use, whether or not there is anything to synchronise.
            LastUseEpoch = _context.TextureUseEpoch;

''', '', 1) == control_sync, 'Texture.SynchronizeMemory gains one store, nothing else')
    pool = read(work, POOL)
    scan = member(pool, 'internal void ScanColdTextures(')
    for needle in ('!texture.HasOneReference()', 'texture.CacheNode != null', 'texture.ShortCacheEntry != null', 'texture.IsView',
                   'texture.HasViews', 'texture.Group.Storage != texture', 'texture.Target == Target.TextureBuffer',
                   'epoch - texture.LastUseEpoch < minimumAge', 'texture.Group.AnyHandleModified() || texture.Group.HasCopyDependencies',
                   '_aliasLists.ContainsKey(texture)', '_coldPinned.Contains(id)',
                   'stats.Released >= countBudget || stats.ReleasedBytes + size > byteBudget',
                   'Interlocked.CompareExchange(ref items[id], null, texture) != texture', 'LogDeltaChange(id);',
                   'texture.DecrementReferenceCount(this, id)', 'RemoveAliasList(texture);'):
        check(needle in scan, 'scan: ' + needle)
    check('FlushModified' not in scan and 'Flush(' not in scan and 'AddShortCache' not in scan, 'no flush, no short cache')
    check(scan.index('texture.Group.AnyHandleModified()') < scan.index('Interlocked.CompareExchange'), 'modified check before release')
    get = member(pool, 'private ref readonly TextureDescriptor GetInternal(int id, out Texture texture)')
    check(get.index('texture.LastUseEpoch = Context.TextureUseEpoch;') < get.index('Items[id] = texture;') and
          'NoteColdReload(id, releasedEpoch, descriptor.Equals(ref DescriptorCache[id]));' in get and
          get.index('NoteColdReload') < get.index('DescriptorCache[id] = descriptor;'), 'fetch stamps the use and detects reloads first')

    def dotnet(*arguments, cwd, timeout=2400):
        result = subprocess.run([DOTNET, *arguments], capture_output=True, text=True, timeout=timeout, env=environment, cwd=cwd)
        if result.returncode:
            errors = [line for line in result.stdout.splitlines() if ': error ' in line]
            print('\n'.join(dict.fromkeys(errors[:40])), result.stdout[-4000:], result.stderr[-2000:], sep='\n', flush=True)
        return result

    build = dotnet('build', str(work / (GPU + 'Ryujinx.Graphics.Gpu.csproj')), '-c', 'Release', '-nologo', '-m:1',
                   '-p:NuGetAudit=false', cwd=work)
    check(build.returncode == 0, 'production Ryujinx.Graphics.Gpu builds with the adapter')
    production_warnings = sorted({line for line in build.stdout.splitlines() if 'warning' in line and
                                  any(f in line for f in ('GpuContext.cs', 'TexturePool.cs', 'Texture.cs('))})
    check(not production_warnings, 'no compiler warning in the edited files: ' + '\n'.join(production_warnings[:5]))

    # Test-only access to the internal production types; the production build above is without it.
    project = work / (GPU + 'Ryujinx.Graphics.Gpu.csproj')
    text = project.read_text(encoding='utf-8-sig')
    check(text.count('</Project>') == 1, 'Gpu project')
    project.write_text(text.replace('</Project>', '  <ItemGroup><InternalsVisibleTo Include="MeloNXColdTextureProbe" /></ItemGroup>\n</Project>'))
    probe.mkdir(parents=True)
    shutil.copyfile(HARNESS / 'Program.cs', probe / 'Program.cs')
    shutil.copyfile(ROOT / 'test/melonx_gpu_teardown/Fakes.cs', probe / 'Fakes.cs')
    (probe / 'MeloNXColdTextureProbe.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable>
    <AllowUnsafeBlocks>true</AllowUnsafeBlocks><NoWarn>CA1416;CS8632</NoWarn><NuGetAudit>false</NuGetAudit>
    <ManagePackageVersionsCentrally>false</ManagePackageVersionsCentrally>
  </PropertyGroup>
  <ItemGroup>
    <ProjectReference Include="{work}/src/Ryujinx.Graphics.Gpu/Ryujinx.Graphics.Gpu.csproj" />
    <ProjectReference Include="{work}/src/Ryujinx.Cpu/Ryujinx.Cpu.csproj" />
  </ItemGroup>
</Project>
''')
    shutil.copyfile(work / 'global.json', probe / 'global.json')
    shutil.copyfile(work / 'nuget.config', probe / 'nuget.config')
    build = dotnet('build', str(probe / 'MeloNXColdTextureProbe.csproj'), '-c', 'Release', '-nologo', '-m:1', cwd=probe)
    check(build.returncode == 0, 'probe builds against the candidate engine')
    run = subprocess.run([DOTNET, str(probe / 'bin/Release/net10.0/MeloNXColdTextureProbe.dll')], capture_output=True, text=True,
                         timeout=600, env=environment, cwd=probe)
    if run.returncode:
        print(run.stdout[-4000:], run.stderr[-4000:], flush=True)
    check(run.returncode == 0, 'probe runs')
    report = json.loads(next(line for line in run.stdout.splitlines() if line.startswith('{')))
finally:
    for path in (work, probe):
        for sub in path.rglob('*') if path.exists() else []:
            if sub.is_dir() and sub.name in ('bin', 'obj'):
                shutil.rmtree(sub, ignore_errors=True)
    if temporary is not None:
        temporary.cleanup()

for name, value in report.items():
    check('harnessException' not in value, f'{name}: {value.get("harnessException", "")[:3000]}')
MiB = 1 << 20
KiB256 = 256 * 1024

a = report['releaseAndRecreate']
check(a['measuredBefore']['poolOnly'] == 3 and a['measuredBefore']['cold'] == 1 and a['measuredBefore']['coldBytes'] == KiB256 and
      a['measuredBefore']['poolOnlyBytes'] == 3 * KiB256, f'(a) measure: three pool-only textures, one cold: {a["measuredBefore"]}')
check(a['passRan'] and a['pass']['released'] == 1 and a['pass']['releasedBytes'] == KiB256 and a['released'],
      f'(a) the cold texture is released, its host texture released, its sequence moved: {a}')
check(a['deltaLogged'] == 1, '(a) the slot is logged for the bindless delta passes')
check(a['boundOnlyAndFetchedStay'], '(a) a texture synchronised by a cached binding or array, and one fetched recently, stay')
check(a['recreated'] and a['sameInfo'] and a['sameOnNextFetch'], '(a) the next fetch re-creates the same texture once')
check(a['firstUploadIsGuest'] and a['secondUploadIsGuest'] and a['uploadBytes'] == KiB256, '(a) both uploads are the guest memory bytes')
check(a['lateReloadCounted'] == 0 and a['pinnedAfterLateReload'] == 0, '(a) a fetch after the reload window is no reload')
check(len(a['passLines']) == 1 and 'released 1 (0 MiB' in a['passLines'][0] and 'device 8% available' in a['passLines'][0],
      f'(a) one journal line: {a["passLines"]}')

b = report['modifiedKept']
check(b['liftedOnGpuWrite'] and b['poolOnlyWithGpuData'], f'(b) setup: pool-only texture holding GPU-written data: {b}')
check(all(p['released'] == 0 and p['gpuData'] == 1 and p['cold'] == 0 for p in b['passes']), f'(b) never released: {b["passes"]}')
check(b['stillInPool'] and b['hostReleases'] == 0 and b['hostReads'] == 0 and b['stillModified'], f'(b) kept, not flushed: {b}')

c = report['noLoop']
check(c['firstPass']['released'] == 1 and c['reloads'] == 1 and c['pinnedSlots'] == 1, f'(c) released, reloaded, pinned: {c}')
check(all(p['released'] == 0 and p['kept'] == 1 for p in c['laterPasses']) and c['stillInPool'], f'(c) never released again: {c}')
check(c['hostTexturesCreatedForSlot'] == 2, f'(c) one re-creation in total: {c["hostTexturesCreatedForSlot"]}')
check(c['ageBefore'] == 60 and c['ageAfter'] == 120, f'(c) the age doubled once on the reload: {c["ageBefore"]} -> {c["ageAfter"]}')
check(len(c['laterLines']) == 6 and 'reloads of recently released 1 (pinned slots 1)' in c['laterLines'][0] and
      'kept 1' in c['laterLines'][0], f'(c) the counters show it: {c["laterLines"][:1]}')

d = report['notShort']
check(not any(d['ranOrReleasedPerDevice'].values()) and d['linesWhileNotShort'] == 0 and d['untouchedWhileNotShort'],
      f'(d) nothing at -1, 11, 12, 27, 50 or 100 %: {d}')
check(d['ranAtThreshold10'] and d['releasedAtThreshold10'] == 2, f'(d) a pass at 10 %: {d}')
check(not d['ranWithin10s'] and d['releasedWithin10s'] == 0 and d['ranAfter10s'] and d['releasedAfter10s'] == 1,
      f'(d) 10 s between passes: {d}')

g = report['aliasKept']
check(g['aliasCreated'] and g['stillInPool'] and g['hostReleases'] == 0 and all(p['released'] == 0 for p in g['passes']),
      f'a texture with a format alias is never released: {g}')

h = report['scanCost']
check(h['poolOnly'] == 2000 and h['released'] == 0, f'scan cost fixture: 2000 recent pool-only textures, none released: {h}')

e = report['byteBound']
check([p['released'] for p in e['passes']] == [64, 36, 0, 0] and all(p['releasedBytes'] <= 64 * MiB for p in e['passes']) and
      e['passes'][0]['releasedBytes'] == 64 * MiB and e['remainingInPool'] == 0 and e['hostReleases'] == 100 and e['lines'] == 4,
      f'(e) at most 64 MiB a pass: {e}')
f = report['countBound']
check([p['released'] for p in f['passes']] == [256, 44, 0, 0] and f['remainingInPool'] == 0 and f['hostReleases'] == 300 and
      f['lines'] == 4, f'(e) at most 256 textures a pass: {f}')

inputs = ['build-utils/melonx/adapt_cold_texture_release.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_cold_texture_release_test.py', 'test/melonx_cold_texture_release/Program.cs',
          'test/melonx_gpu_teardown/Fakes.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core658Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE} if FINAL_PREPARATION else {},
               lifetimeProof=proof, fixture=report, sdk=sdk, physicalDeviceTested=False, galDoubled=True,
               productionGpuAssemblyBuilt=True, sourceBaseline=BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Real engine with a recording GAL renderer: the Vulkan deferred release is proven by source, not '
                          'executed; how many MiB are cold in Hogwarts (bindless pool arrays synchronise every texture they '
                          'bind at each use) and the Metal memory effect are known only from a device run.')
out = ROOT / 'dist/melonx/cold-texture-release-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk, finalPreparationBound=FINAL_PREPARATION)))

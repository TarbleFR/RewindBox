#!/usr/bin/env python3
"""Whole rebuilds of large bindless arrays keep their arrays instead of allocating them (adapt_array_rebuild_allocations).

Usage: melonx_array_rebuild_allocations_test.py <base prepared MeloNX tree>
       melonx_array_rebuild_allocations_test.py <control> --candidate-source <final preparation containing the adapter>

Applies the adapter to a copy of the base preparation and builds the production Ryujinx.Graphics.Gpu (with
Ryujinx.Graphics.GAL) for the control and the candidate. Static checks bind that the candidate is the control plus
exactly the adapter's edits (reversed through melonx_adapter_control), that only the two whole rebuilds use the new
helpers (the delta runs keep their cache), that lengths up to 4096 still go to the unchanged scratch cache and pool,
that every kept array is cleared and that the large slots are bounded (2 slots, 1048576 elements per element type).
Behaviour and measurement (test/melonx_array_rebuild_allocations/Program.cs): the REAL TextureBindingsArrayCache,
threaded producers, commands and ThreadedArrayPool of each variant run with doubles for pools, textures and backend.
48 random scenarios (texture, sampler and image arrays, threaded and direct, 70 to 65536 elements, forced rebuilds
included) and one cache rebuilding arrays of 4096 to 2,000,000 elements in turn must give identical digests of the
backend contents, the backend call stream, the store/synchronisation sets and the cache's recorded state (per-element
delta state, texture set and sequences, reference counts) for both variants. Then the allocated bytes of whole rebuilds
of 65536-element arrays are read with GC.GetAllocatedBytesForCurrentThread at the boundaries the doubles see, and a
burst of 200 threaded rebuilds is timed with its GC collections (System.GC.ConserveMemory=5 as published). No device.
Writes dist/melonx/array-rebuild-allocations-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, _reverse  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_array_rebuild_allocations', _HOLD)
from adapt_array_rebuild_allocations import apply, BASELINE, CACHE, POOL  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
GAL = 'src/Ryujinx.Graphics.GAL'
MULTI = GAL + '/Multithreading'
FIXTURE_FILES = [
    CACHE,
    'src/Ryujinx.Graphics.Gpu/Image/TextureBindingInfo.cs',
    'src/Ryujinx.Graphics.Gpu/Engine/Types/SamplerIndex.cs',
    'src/Ryujinx.Graphics.Shader/TextureHandle.cs',
    'src/Ryujinx.Graphics.Shader/TextureUsageFlags.cs',
    'src/Ryujinx.Graphics.Shader/ShaderStage.cs',
    GAL + '/Target.cs', GAL + '/ITextureArray.cs', GAL + '/IImageArray.cs',
    MULTI + '/Model/TableRef.cs', POOL, MULTI + '/Commands/IGALCommand.cs',
    MULTI + '/Resources/ThreadedTextureArray.cs', MULTI + '/Resources/ThreadedImageArray.cs',
    MULTI + '/Commands/TextureArray/TextureArraySetTexturesCommand.cs',
    MULTI + '/Commands/TextureArray/TextureArraySetSamplersCommand.cs',
    MULTI + '/Commands/TextureArray/TextureArrayDisposeCommand.cs',
    MULTI + '/Commands/ImageArray/ImageArraySetImagesCommand.cs',
    MULTI + '/Commands/ImageArray/ImageArrayDisposeCommand.cs',
]
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def member(text, signature):
    start = text.rindex('\n', 0, text.index(signature)) + 1
    depth, index = 0, text.index('{', start)
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


for name, expected in BASELINE.items():
    check(sha(SOURCE / name) == expected, 'not the base preparation: ' + name)

environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
texts, reports, compiled = {}, {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-array-rebuild-allocations-') as temporary:
    temporary = Path(temporary).resolve()
    for variant in ('control', 'candidate'):
        work = temporary / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
        if variant == 'candidate':
            changed = apply(work)
            check(sorted(str(p.relative_to(work)) for p in changed) == sorted(BASELINE), 'adapter changed other files')
            if FINAL_PREPARATION:
                for name in BASELINE:
                    check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
        texts[variant] = {name: (work / name).read_text(encoding='utf-8-sig') for name in BASELINE}
        result = subprocess.run([DOTNET, 'build', str(work / 'src/Ryujinx.Graphics.Gpu/Ryujinx.Graphics.Gpu.csproj'), '-c', 'Release',
                                 '-nologo', '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=2400,
                                env=environment, cwd=work)
        if result.returncode:
            print(result.stdout[-5000:], result.stderr[-2000:], flush=True)
        check(result.returncode == 0, variant + ' production Ryujinx.Graphics.Gpu (with Ryujinx.Graphics.GAL) builds')
        print(variant + ': production Ryujinx.Graphics.Gpu and Ryujinx.Graphics.GAL built', flush=True)

        # The fixture compiles the variant's own production files.
        fixture = temporary / ('fixture-' + variant)
        for relative in FIXTURE_FILES:
            (fixture / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(work / relative, fixture / relative)
        compiled[variant] = {p: sha(fixture / p) for p in FIXTURE_FILES}
        shutil.copyfile(ROOT / 'test/melonx_array_rebuild_allocations/Program.cs', fixture / 'Program.cs')
        define = '<DefineConstants>ADAPTED</DefineConstants>' if variant == 'candidate' else ''
        (fixture / 'test.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>
<AllowUnsafeBlocks>true</AllowUnsafeBlocks><Nullable>disable</Nullable><ServerGarbageCollection>false</ServerGarbageCollection>
<EnableNETAnalyzers>false</EnableNETAnalyzers><NuGetAudit>false</NuGetAudit><NoWarn>0649;0162;0168;0219;8981</NoWarn>{define}
</PropertyGroup><ItemGroup>
<RuntimeHostConfigurationOption Include="System.GC.ConserveMemory" Value="5" />
<RuntimeHostConfigurationOption Include="System.GC.HighMemoryPercent" Value="99" />
</ItemGroup></Project>''')
        (fixture / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        for command in ([DOTNET, 'build', str(fixture / 'test.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                        [DOTNET, str(fixture / 'bin/Release/net10.0/test.dll')]):
            result = subprocess.run(command, capture_output=True, text=True, timeout=1800, env=environment, cwd=fixture)
            if result.returncode:
                print(result.stdout[-6000:], result.stderr[-4000:], flush=True)
                result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        print(variant + ': fixture ran, ' + str(reports[variant]['checks']) + ' program checks', flush=True)

    # The candidate is the control plus exactly the adapter's edits.
    reversed_tree = temporary / 'reversed'
    for name in BASELINE:
        (reversed_tree / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(temporary / 'candidate' / name, reversed_tree / name)
    _reverse('adapt_array_rebuild_allocations', reversed_tree)
    for name in BASELINE:
        check((reversed_tree / name).read_bytes() == (temporary / 'control' / name).read_bytes(),
              'candidate is the control plus the adapter edits only: ' + name)

control_text, candidate_text = texts['control'], texts['candidate']
cache, pool = candidate_text[CACHE], candidate_text[POOL]

# Cache: the two whole rebuilds use the new helpers; the delta runs and the small cache are unchanged.
check(cache.count('RentRebuildScratch(_samplerBindingScratch, _largeSamplerBindingScratch, bindingInfo.ArrayLength)') == 2 and
      cache.count('RentRebuildScratch(_textureBindingScratch, _largeTextureBindingScratch, bindingInfo.ArrayLength)') == 2 and
      cache.count('ReturnRebuildScratch(_textureBindingScratch, _largeTextureBindingScratch, textures, ref _nextTextureBindingScratch)') == 2 and
      cache.count('ReturnRebuildScratch(_samplerBindingScratch, _largeSamplerBindingScratch, samplers, ref _nextSamplerBindingScratch)') == 2,
      'both whole rebuilds rent and return through the new helpers')
check('RentBindingScratch(_samplerBindingScratch' not in cache and 'RentBindingScratch(_textureBindingScratch' not in cache and
      'ReturnBindingScratch(_textureBindingScratch' not in cache, 'no whole rebuild left on the old helpers')
for signature in ('private static T[] RentBindingScratch<T>(', 'private static void ReturnBindingScratch<T>(',
                  'private void FlushDeltaRun(', 'private bool UpdateFromPoolDelta(', 'private bool CollectLoggedChanges(',
                  'public void RecordDelta(', 'public void PrepareDelta(', 'private void SetTextureArray(', 'private void SetImageArray('):
    check(member(cache, signature) == member(control_text[CACHE], signature), 'unchanged: ' + signature)
rent = member(cache, 'private static T[] RentRebuildScratch<T>(')
give = member(cache, 'private static void ReturnRebuildScratch<T>(')
keep = member(cache, 'private static void KeepLargeScratch<T>(')
check('if (length <= MaxBindingScratchLength)' in rent and 'return RentBindingScratch(cache, length);' in rent and
      'largeCache[i] = null;' in rent and 'return new T[length];' in rent, 'small lengths unchanged; a kept array is lent once')
check(give.index('ReturnBindingScratch(cache, scratch, ref next);') < give.index('Array.Clear(scratch);') <
      give.index('if (scratch.Length > LargeBindingScratchBudget)') < give.index('KeepLargeScratch(largeCache, scratch);'),
      'small lengths unchanged; every large array is cleared before it is kept; over-budget arrays are dropped')
check('private const int LargeBindingScratchSlots = 2;' in cache and 'private const int LargeBindingScratchBudget = 1 << 20;' in cache and
      'sum -= largeCache[i].Length;' in keep and 'largeCache[i] = null;' in keep, 'large slots bounded: 2 arrays, 1048576 elements')

# Pool: lengths up to 4096 unchanged; large snapshots from bounded, cleared slots under the same lock.
copy, back = member(pool, 'public static T[] Copy(T[] source)'), member(pool, 'public static void Return(T[] snapshot)')
check('else if (length > MaximumLength && length <= LargeBudget)' in copy and copy.count('lock (Cache)') == 2 and
      'LargeCache[i] = null;' in copy and 'new ReadOnlySpan<T>(source).CopyTo(snapshot);' in copy, 'large snapshots taken under the lock')
check(back.index('snapshot.Length > LargeBudget') < back.index('Array.Clear(snapshot);') < back.index('lock (Cache)') <
      back.index('KeepLarge(snapshot);'), 'large snapshots cleared before they are kept')
check('private const int LargeSlots = 2;' in pool and 'private const int LargeBudget = 1 << 20;' in pool and
      'private const int MaximumLength = 4096;' in pool and 'private const int CacheSlots = 8;' in pool, 'pool bounds')

# Behaviour: identical digests.
control, candidate = reports['control'], reports['candidate']
check(not control['adapted'] and candidate['adapted'], 'variants swapped')
check(control['gcSettings']['conserveMemory'] == candidate['gcSettings']['conserveMemory'] == '5', 'published GC setting')
check(len(control['scenarios']) == len(candidate['scenarios']) == 48, 'scenario inventory')
for old, new in zip(control['scenarios'], candidate['scenarios'], strict=True):
    check({k: v for k, v in old.items() if k != 'digest'} == {k: v for k, v in new.items() if k != 'digest'}, 'scenario pairing')
    check(old['digest'] == new['digest'], 'backend contents, calls, synchronisation or recorded state differ: ' + json.dumps(new))
check(sum(s['fullElements'] for s in candidate['scenarios']) > 0, 'scenarios include whole rebuilds')
for old, new in zip(control['mixed'], candidate['mixed'], strict=True):
    check(old['digest'] == new['digest'] and old['updates'] == new['updates'] == 24, 'mixed lengths identical: ' + json.dumps(new)[:400])
for old, new in zip(control['measures'], candidate['measures'], strict=True):
    check(old['digest'] == new['digest'] and old['lookupsPerRebuild'] == new['lookupsPerRebuild'] == 65536,
          'measured rebuilds identical: ' + new['kind'])

# Retention: control has no large slot; the candidate's are bounded and never hold a resource.
for report in control['mixed'] + control['measures']:
    check(not any(s['field'] in ('LargeCache', '_largeTextureBindingScratch', '_largeSamplerBindingScratch') for s in report['retention']),
          'control has no large slots')
for report in candidate['mixed'] + candidate['measures']:
    large = [s for s in report['retention'] if s['field'] in ('LargeCache', '_largeTextureBindingScratch', '_largeSamplerBindingScratch')]
    check(len(large) == 4 and all(s['slots'] == 2 and s['retained'] <= 2 and s['elements'] <= 1 << 20 for s in large),
          'large slots bounded: ' + json.dumps(large))
    check(all(s['live'] == 0 for s in report['retention']), 'kept arrays hold no texture or sampler')

# Measurement.
rows = []
for old, new in zip(control['measures'], candidate['measures'], strict=True):
    per_element = 32 if old['kind'] != 'Image' and old['threaded'] else 16 if old['kind'] != 'Image' or old['threaded'] else 8
    check(old['bytesPerRebuild'] >= per_element * 65536, 'control allocates the whole-length arrays: ' + json.dumps(old)[:300])
    check(new['bytesPerRebuild'] <= 256, 'candidate allocates nothing per element: ' + json.dumps(new)[:300])
    rows.append(dict(threaded=old['threaded'], kind=old['kind'], length=old['length'],
                     controlBytesPerRebuild=old['bytesPerRebuild'], candidateBytesPerRebuild=new['bytesPerRebuild'],
                     controlBytesPerElement=old['bytesPerElement'], candidateBytesPerElement=new['bytesPerElement'],
                     controlMicroseconds=old['microsecondsPerRebuild'], candidateMicroseconds=new['microsecondsPerRebuild'],
                     controlAllocatingSegments={s['segment']: s['bytesPerRebuild'] for s in old['segments'] if s['bytesPerRebuild']},
                     candidateAllocatingSegments={s['segment']: s['bytesPerRebuild'] for s in new['segments'] if s['bytesPerRebuild']}))
check(control['burst']['gen2'] > 0 and candidate['burst']['gen2'] == 0 and
      candidate['burst']['allocatedMiB'] * 100 < control['burst']['allocatedMiB'], 'burst: no gen2 collection, allocations cut by 100x')

inputs = ['build-utils/melonx/adapt_array_rebuild_allocations.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_array_rebuild_allocations_test.py', 'test/melonx_array_rebuild_allocations/Program.cs',
          'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
measurements = dict(rebuilds=rows, burst=dict(control=control['burst'], candidate=candidate['burst']))
receipt = dict(result='passed', checks=checks, programChecks=dict(control=control['checks'], candidate=candidate['checks']),
               measurements=measurements, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'basePreparation',
               postimages={p: sha(FINAL_SOURCE / p) for p in BASELINE} if FINAL_PREPARATION else {},
               sdk=sdk, physicalDeviceTested=False, productionGpuAssemblyBuilt=True, productionGalAssemblyBuilt=True,
               poolsTexturesAndBackendDoubled=True, sourceBaseline=BASELINE, compiledFixtureSources=compiled,
               inputs={p: sha(ROOT / p) for p in inputs},
               limitation='Removes the per-rebuild allocation of the whole-length arrays of large bindless rebuilds on the GPU '
                          'thread (cache scratch and threaded snapshots); measured on the host with doubles for pools, textures '
                          'and backend. Texture creation by pool lookups, a new entry\'s delta state, the Vulkan backend and a '
                          'threaded snapshot still in flight beyond two are unchanged. The share of the device\'s scene-transition '
                          'allocations and GC pauses this removes is known only from a device run (bindings allocatedKiB, gcPause).')
out = ROOT / 'dist/melonx/array-rebuild-allocations-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
for row in rows:
    print(f"{'threaded' if row['threaded'] else 'direct  '} {row['kind']:<7} {row['length']}: "
          f"{row['controlBytesPerRebuild']} -> {row['candidateBytesPerRebuild']} bytes per rebuild "
          f"({row['controlBytesPerElement']} -> {row['candidateBytesPerElement']} per element), "
          f"{row['controlMicroseconds']} -> {row['candidateMicroseconds']} us")
print('burst of 200 threaded 65536-element texture rebuilds: control ' + json.dumps(control['burst']) +
      '; candidate ' + json.dumps(candidate['burst']))
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))

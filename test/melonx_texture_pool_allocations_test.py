#!/usr/bin/env python3
"""adapt_short_cache_reuse on the final preparation, against the same preparation without it, on the production texture path.

Usage: melonx_texture_pool_allocations_test.py <control> --candidate-source <final preparation containing the adapter>

The production Ryujinx.Graphics.Gpu (and Ryujinx.Cpu) of each engine builds; then (test-only InternalsVisibleTo)
test/melonx_texture_pool_allocations/Program.cs runs its TextureManager, TextureBindingsManager, TexturePool, TextureCache,
AutoDeleteCache and Texture on guest memory with a doubled renderer (host textures record creation, views, uploads with the
first texel of level 0, GPU copies of it, and release) and a no-op pipeline generated from the tree's IPipeline. The same
scenarios run on both engines, after warm-up, once with DOTNET_TieredCompilation=0 (fully optimized code, nearest to the
device's NativeAOT) and once with the default runtime settings. Required on both engines: every element of the bindless
array holds, after every pass, a live host texture of the descriptor's size, swizzle and format whose data is what guest
memory holds now through the GPU address (CPU writes, remaps included), and the same observation digest; every host
texture is released exactly once by the close. Required of the control: the cycle (a texture back three presents after it
left is created and uploaded again). Required of the candidate: no creation or upload on that return; CPU writes while away
uploaded on return; a return past 60 presents or after an unmap recreated as in the control; a full list never above 1 024
textures or 32 MiB; every retained texture released by a host memory pressure trim (the device-short call of TrimCaches)
and by the close; fewer bytes allocated where entries are reused. Writes dist/melonx/texture-pool-allocations-checks.json.
No device: host textures are doubles, so the times are not iPhone times.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_short_cache_reuse', _HOLD)
import adapt_short_cache_reuse as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
GPU = 'src/Ryujinx.Graphics.Gpu/'
PIPELINE = 'src/Ryujinx.Graphics.GAL/IPipeline.cs'
MIB = 1024 * 1024
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


for name, expected in adapter.BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 707 preparation: ' + name)

environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
environment.pop('DOTNET_TieredCompilation', None)


def dotnet(*arguments, cwd, timeout=2400):
    result = subprocess.run([DOTNET, *arguments], capture_output=True, text=True, timeout=timeout, env=environment, cwd=cwd)
    if result.returncode:
        errors = [line for line in result.stdout.splitlines() if ': error ' in line]
        print('\n'.join(dict.fromkeys(errors[:40])), result.stdout[-4000:], result.stderr[-2000:], sep='\n', flush=True)
    return result


def noop_pipeline(text):
    """A no-op IPipeline (no allocation per call) from the tree's interface."""
    members = []
    body = text[text.index('public interface IPipeline'):]
    for match in re.finditer(r'^\s+([\w.<>\[\]?]+)\s+(\w+)\(([^)]*)\);', body, re.M):
        result, name, parameters = match.groups()
        members.append(f'    public {result} {name}({parameters}) {{ Calls++; ' + ('' if result == 'void' else 'return default; ') + '}')
    check(len(members) == text.count(');'), 'IPipeline parsed: every member (' + str(len(members)) + ')')
    usings = ''.join(line + '\n' for line in text.splitlines() if line.startswith('using '))
    return (usings + 'using Ryujinx.Graphics.GAL;\n\n// No-op IPipeline generated from the tree\'s IPipeline.cs.\n'
            'sealed class NoopPipeline : IPipeline\n{\n    public static long Calls;\n' + '\n'.join(members) + '\n}\n')


# Static: only the adapter's replacements, fail closed, the release points.
replacements = []
original_once = adapter.once
with tempfile.TemporaryDirectory(prefix='melonx-short-cache-static-') as temporary:
    work = Path(temporary) / 'candidate'
    for name in adapter.BASELINE:
        (work / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / name, work / name)

    def recording_once(path, old, new):
        replacements.append((path.relative_to(work).as_posix(), old, new))
        original_once(path, old, new)

    adapter.once = recording_once
    try:
        changed = adapter.apply(work)
    finally:
        adapter.once = original_once
    check(sorted(p.relative_to(work).as_posix() for p in changed) == sorted(adapter.BASELINE), 'adapter changed other files')
    for name in adapter.BASELINE:
        undone = (work / name).read_text(encoding='utf-8-sig')
        for path, old, new in reversed(replacements):
            if path == name:
                check(undone.count(new) == 1, 'each replacement once: ' + new[:60])
                undone = undone.replace(new, old)
        check(undone == (SOURCE / name).read_text(encoding='utf-8-sig'), name + ' is the preparation but the adapter\'s replacements')
    texts = {name: (work / name).read_text(encoding='utf-8-sig') for name in adapter.BASELINE}
    try:
        adapter.apply(work)
        refused = False
    except AssertionError:
        refused = True
    check(refused, 'fail closed: an adapted tree is refused')
    if FINAL_PREPARATION:
        later = files_edited_later('adapt_short_cache_reuse')
        for name in adapter.BASELINE:
            if name not in later:
                check(texts[name] == (FINAL_SOURCE / name).read_text(encoding='utf-8-sig'), 'final preparation is the adapter: ' + name)

cache = texts[adapter.CACHE]
added = ''.join(new for _, _, new in replacements)
check(re.search(r'GC\.Collect\s*\(', added) is None, 'no collection added')
check('public const int MaxRetainedEntries = 1024;' in cache and 'public const ulong MaxRetainedBytes = 32 * MiB;' in cache and
      'public const long MaxRetainedTicks = 60;' in cache and 'private const int MaxReusableEntries = 256;' in cache, 'bounds')
trim = cache[cache.index('public ulong Trim(MemoryPressureLevel level, bool freeOnly = false)'):]
trim = trim[:trim.index('\n        }\n') + 10]
check(trim.index('ReleaseAllRetained()') < trim.index('if (!GraphicsConfig.EnableHostMemoryBudgetTracking)'),
      'every host memory pressure trim releases the retained textures first')
dispose = texts[adapter.TEXTURE_CACHE]
dispose = dispose[dispose.index('        public void Dispose()\n'):]
check(dispose.index('_cache.ReleaseAllRetained();') < dispose.index('foreach (Texture texture in _textures)'), 'the close releases them')
retain = cache[cache.index('private bool TryRetain(ShortTextureCacheEntry entry)'):]
retain = retain[:retain.index('\n        }\n') + 10]
for condition in ('entry.IsAutoDelete', '!texture.HasOneReference()', 'entry.InvalidatedSequence != texture.InvalidatedSequence',
                  'texture.ChangedMapping', 'texture.Target == Target.TextureBuffer', 'size > MaxRetainedTextureBytes',
                  '_reuse.Retained >= MaxRetainedEntries || _reuse.RetainedBytes + size > MaxRetainedBytes', '!entry.InLookup'):
    check(condition in retain, 'retention condition: ' + condition)
find = cache[cache.index('public Texture FindShortCache(in TextureDescriptor descriptor)'):]
find = find[:find.index('\n        }\n') + 10]
check('entry.InvalidatedSequence == entry.Texture.InvalidatedSequence && !entry.Texture.ChangedMapping' in find,
      'a retained texture is returned only while valid and with its mapping unchanged')

# Executed: control and candidate engines, two runtime settings.
reports = {}
with tempfile.TemporaryDirectory(prefix='melonx-texture-pool-allocations-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj', 'MeloNX'), symlinks=True)
        if variant == 'candidate':
            adapter.apply(work)
            for name in adapter.BASELINE:
                check((work / name).read_text(encoding='utf-8-sig') == texts[name], 'candidate is the adapter: ' + name)
        build = dotnet('build', str(work / (GPU + 'Ryujinx.Graphics.Gpu.csproj')), '-c', 'Release', '-nologo', '-m:1',
                       '-p:NuGetAudit=false', cwd=work)
        check(build.returncode == 0, variant + ' production Ryujinx.Graphics.Gpu builds')
        if variant == 'candidate':
            warnings = sorted({line for line in build.stdout.splitlines() if 'warning' in line and
                               any(f in line for f in ('AutoDeleteCache.cs', 'TextureCache.cs', 'GpuContext.cs'))})
            check(not warnings, 'no compiler warning in the edited files: ' + '\n'.join(warnings[:5]))
        project = work / (GPU + 'Ryujinx.Graphics.Gpu.csproj')
        text = project.read_text(encoding='utf-8-sig')
        project.write_text(text.replace('</Project>', '  <ItemGroup><InternalsVisibleTo Include="MeloNXBindingsProbe" /></ItemGroup>\n</Project>'))
        probe = Path(temporary).resolve() / ('probe-' + variant)
        probe.mkdir()
        shutil.copyfile(ROOT / 'test/melonx_texture_pool_allocations/Program.cs', probe / 'Program.cs')
        shutil.copyfile(ROOT / 'test/melonx_gpu_teardown/Fakes.cs', probe / 'Fakes.cs')
        (probe / 'Pipeline.g.cs').write_text(noop_pipeline((work / PIPELINE).read_text(encoding='utf-8-sig')))
        (probe / 'MeloNXBindingsProbe.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk">
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
        for extra in ('global.json', 'nuget.config'):
            if (work / extra).exists():
                shutil.copyfile(work / extra, probe / extra)
        build = dotnet('build', str(probe / 'MeloNXBindingsProbe.csproj'), '-c', 'Release', '-nologo', '-m:1', cwd=probe)
        check(build.returncode == 0, 'probe builds against the ' + variant + ' engine')
        for setting in ('0', 'default'):
            run_environment = dict(environment)
            if setting == '0':
                run_environment['DOTNET_TieredCompilation'] = '0'
            run = subprocess.run([DOTNET, str(probe / 'bin/Release/net10.0/MeloNXBindingsProbe.dll')], capture_output=True, text=True,
                                 timeout=1200, env=run_environment, cwd=probe)
            if run.returncode:
                print(run.stdout[-4000:], run.stderr[-4000:], flush=True)
            check(run.returncode == 0, f'{variant} probe runs (tiered compilation {setting})')
            report = json.loads(next(line for line in run.stdout.splitlines() if line.startswith('{"engine"')))
            check(report['engine'] == variant, 'the probe ran on the ' + variant + ' engine')
            reports[(variant, setting)] = report

for setting in ('0', 'default'):
    control, candidate = reports[('control', setting)], reports[('candidate', setting)]
    tag = f' (tiered compilation {setting})'
    check(not control['errors'], 'control: every element holds the named texture and data' + tag + ': ' + '; '.join(control['errors'][:3]))
    check(not candidate['errors'], 'candidate: every element holds the named texture and data' + tag + ': ' + '; '.join(candidate['errors'][:3]))
    check(candidate['observation'] == control['observation'], 'same textures, sizes, swizzles, formats and data observed' + tag)
    check(candidate['totals']['texturesCreated'] < control['totals']['texturesCreated'], 'fewer host textures created' + tag)
    for report in (control, candidate):
        close = report['close']
        check(close['liveHostBytesAfter'] == 0 and close['retainedAfter'] == 0, 'the close releases every host texture' + tag)
    c, k = control['results'], candidate['results']
    check(c['returnAfterExpiry']['texturesCreated'] == c['returnAfterExpiry']['uploads'] == 1920,
          'control: the cycle (a texture back three presents after it left is created and uploaded again)' + tag)
    check(k['returnAfterExpiry']['texturesCreated'] == 0 and k['returnAfterExpiry']['uploads'] == 0 and
          k['returnAfterExpiry']['Reused'] == 1920, 'candidate: the same returns create and upload nothing' + tag)
    check(k['returnAfterExpiry']['bytesPerPass'] < c['returnAfterExpiry']['bytesPerPass'] // 10, 'fewer bytes allocated per pass' + tag)
    check(c['returnBeforeExpiry']['texturesCreated'] == k['returnBeforeExpiry']['texturesCreated'] == 0, 'within two presents: no creation' + tag)
    check(k['returnAfterAge']['texturesCreated'] == c['returnAfterAge']['texturesCreated'] > 0 and k['returnAfterAge']['ReleasedByAge'] > 0,
          'back after 70 presents: released by age, recreated as in the control' + tag)
    check(k['cpuModifiedWhileAway']['texturesCreated'] == 0 and
          k['cpuModifiedWhileAway']['uploads'] == c['cpuModifiedWhileAway']['uploads'] == 1920,
          'CPU writes while away: reused, the new data uploaded on return' + tag)
    check(k['descriptorChange']['texturesCreated'] <= c['descriptorChange']['texturesCreated'], 'descriptor changes' + tag)
    check(k['unmapWhileAway']['texturesCreated'] == c['unmapWhileAway']['texturesCreated'] > 0 and k['unmapWhileAway']['Reused'] == 0,
          'unmapped while away: never reused, recreated from the pages mapped now' + tag)
    check(k['referencedElsewhere']['texturesCreated'] <= c['referencedElsewhere']['texturesCreated'], 'referenced elsewhere' + tag)
    for name in ('saturationEntries', 'withinEntryBound', 'saturationBytes'):
        check(k[name]['maxRetained'] <= 1024 and k[name]['maxRetainedBytes'] <= 32 * MIB, 'bounds held: ' + name + tag)
    check(k['saturationEntries']['maxRetained'] == 1024 and k['saturationEntries']['RefusedByBound'] > 0,
          'a full entry list keeps what it holds' + tag)
    check(k['saturationBytes']['RefusedByBound'] > 0 and k['saturationBytes']['texturesCreated'] < c['saturationBytes']['texturesCreated'],
          'a full byte budget keeps what it holds, part of the returns reused' + tag)
    pressure = k['pressure']
    check(pressure['liveHostBytesReleasedByTrims'] > 0 and pressure['liveHostBytesReleasedByTrims'] == pressure['trimReturnedBytes'] and
          pressure['ReleasedAll'] > 0 and c['pressure']['liveHostBytesReleasedByTrims'] == 0,
          'each device-short trim releases the retained textures (bytes reported = host bytes freed)' + tag)
    check(k['swapNoPresent']['bytesPerPass'] < c['swapNoPresent']['bytesPerPass'], 'entries reused within two presents' + tag)

print(json.dumps({f'{v}/{s}': {n: {x: r[x] for x in ('texturesCreated', 'uploads', 'bytesPerPass', 'msPerPass')}
                               for n, r in rep['results'].items()} for (v, s), rep in reports.items()}), flush=True)

inputs = ['build-utils/melonx/adapt_short_cache_reuse.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_texture_pool_allocations_test.py', 'test/melonx_texture_pool_allocations/Program.cs',
          'test/melonx_gpu_teardown/Fakes.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core707Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in adapter.BASELINE} if FINAL_PREPARATION else {},
               comparison=dict(sameObservation=True, cycleInControl=True, bounds=dict(entries=1024, bytes=32 * MIB, presents=60)),
               runs={f'{v}/{s}': dict(observation=r['observation'], results=r['results'], close=r['close'], totals=r['totals'])
                     for (v, s), r in reports.items()},
               sdk=sdk, physicalDeviceTested=False, productionGpuAssemblyBuilt=True, sourceBaseline=adapter.BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Host textures are doubles: creation, upload and release costs of Metal textures are not measured; '
                          'which textures Hogwarts Legacy names again after leaving a pool, and when, is known only from a device run.')
out = ROOT / 'dist/melonx/texture-pool-allocations-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))

#!/usr/bin/env python3
"""Device-short texture trim (adapt_device_short_trim) on the real prepared engine.

Usage: melonx_device_short_trim_test.py <prepared MeloNX tree>

The tree is prepare_embedded.py's output on 13700519 (the Core 631 preparation). Control is the tree as
prepared, candidate adds the adapter. In each, the complete production AutoDeleteCache.cs and the production
Texture reference/view members (IncrementReferenceCount, HasOneReference, DecrementReferenceCount, AddView,
RemoveView, DeleteIfNotUsed, copied with their exact bodies) are compiled with test/melonx_device_short_trim/
Program.cs, whose doubles stand for GPU storage, the texture group's handles and the texture cache listing.

Checks: the delivered trim (this process's own pressure) is the same in both variants and shows the 621
behaviour (pool-referenced textures "released" without being freed, GPU-written ones flushed); the candidate's
device-short trim destroys every byte it evicts, flushes nothing, keeps pool-referenced and GPU-written
textures in LRU order, respects the floor and reports what it kept. The GpuContext and TextureCache wiring is
checked statically here and compiled with the whole GPU assembly by the driver below.
Writes dist/melonx/device-short-trim-checks.json. No device, no FPS claim.

Plan 748 rank 11 (adapt_device_critical_trim), on the final preparation: its AutoDeleteCache.cs must be that adapter on
its pinned baseline; the complete final AutoDeleteCache.cs and the final Texture reference/view members are compiled with
the same doubles (plus test/melonx_device_short_trim/Final.cs for the members the short cache's retained list reads) and run
every candidate scenario (same results), then the thread-static OnlyUnreferencedTrim flag GpuContext.TrimCaches sets for a
Critical level or an escalation while only the device is short: the textures the cache alone holds leave, GPU-written ones
flushed first (and only those), none a pool references, down to the same targets and floor; guest memory the CPU wrote
since is not flushed; the flag set on another thread changes nothing here.
"""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
# Core gate form: <control> --candidate-source <final preparation>; the control tree is not read (the exact Core 631
# control is rebuilt from the final preparation). Standalone form: <prepared tree>.
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import ORDER, control_source, files_edited_later  # noqa: E402
_HOLD = []
# The 631 preparation, or the final preparation (prepare_embedded.py runs this adapter): its exact control.
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_device_short_trim', _HOLD)
from adapt_device_short_trim import apply, BASELINE

TEXTURE = 'src/Ryujinx.Graphics.Gpu/Image/Texture.cs'
TEXTURE_SHA = '1a99f074c951c51f7369802f078b30779bece3266c427db1492995904656a283'
for name, expected in {**BASELINE, TEXTURE: TEXTURE_SHA}.items():
    assert hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the 631 preparation: ' + name
DOTNET = os.environ.get('DOTNET', 'dotnet')
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def member(text, signature):
    """One complete production member, its exact body."""
    assert text.count(signature) == 1, signature
    start = text.index(signature)
    depth, index = 0, text.index('{', start)
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


# Plan 748 rank 11: the final preparation's AutoDeleteCache.cs is adapt_device_critical_trim on its pinned baseline.
CRITICAL = FINAL_PREPARATION and 'adapt_device_critical_trim' in ORDER
if CRITICAL:
    import adapt_device_critical_trim as critical_adapter  # noqa: E402
    check(files_edited_later('adapt_device_critical_trim') == set(), 'no later adapter edits adapt_device_critical_trim\'s files')
    final_cache = (FINAL_SOURCE / critical_adapter.TEXTURES).read_text(encoding='utf-8-sig')
    undone = final_cache
    for old, new in reversed(critical_adapter.EDITS[critical_adapter.TEXTURES]):
        check(undone.count(new) == 1, 'adapt_device_critical_trim replacement once: ' + new.strip().splitlines()[0][:60])
        undone = undone.replace(new, old)
    check(hashlib.sha256(undone.encode('utf-8')).hexdigest() == critical_adapter.BASELINE[critical_adapter.TEXTURES],
          'the final AutoDeleteCache.cs is adapt_device_critical_trim on its pinned baseline')
    walk = member(final_cache, 'private void TrimUnreferencedTextures(ulong target, bool flush = false)')
    check(walk.count('texture.HasOneReference() && (flush || !texture.Group.AnyHandleModified())') == 1 and
          walk.count('texture.FlushModified(false);') == 1 and
          walk.index('if (!texture.CheckModified(false))') < walk.index('texture.Group.SynchronizeDependents(texture);') <
          walk.index('if (flush && texture.Group.AnyHandleModified())') < walk.index('texture.FlushModified(false);') <
          walk.index('_textures.Remove(node);'), 'the walk evicts only single-reference textures, flushing GPU data first when allowed')
    check(member(final_cache, 'private void RemoveLeastUsedTexture()') == member(undone, 'private void RemoveLeastUsedTexture()') and
          member(final_cache, 'private void EnforceCapacity(Texture protectedTexture)') == member(undone, 'private void EnforceCapacity(Texture protectedTexture)'),
          'the capacity eviction is unchanged')

reports = {}
with tempfile.TemporaryDirectory(prefix='melonx-device-short-trim-') as temporary:
    for variant in ('control', 'candidate', 'final') if CRITICAL else ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        source = work / 'source'
        for name in [*BASELINE, TEXTURE]:
            (source / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile((FINAL_SOURCE if variant == 'final' else SOURCE) / name, source / name)
        if variant == 'final':
            shutil.copyfile(ROOT / 'test/melonx_device_short_trim/Final.cs', work / 'Final.cs')
        if variant == 'candidate':
            changed = apply(source)
            check(sorted(str(p.relative_to(source)) for p in changed) == sorted(BASELINE), 'adapter changed other files')
            context = (source / 'src/Ryujinx.Graphics.Gpu/GpuContext.cs').read_text()
            trim = member(context, 'public void TrimCaches(MemoryPressureLevel level)')
            check(trim.count('bool freeOnly = deviceShort && available >= ComfortableHeadroomBytes;') == 1 and
                  trim.index('bool deviceShort =') < trim.index('bool freeOnly') and
                  trim.index('if (_lastTrimTimestamp != 0') < trim.index('bool freeOnly'),
                  'freeOnly must follow the delivered checks and only cover a short device with comfortable headroom')
            check(trim.count('physicalMemory.TextureCache.Trim(level, freeOnly)') == 1 and
                  trim.count('physicalMemory.BufferCache.Trim(level)') == 1, 'buffer trim must stay as delivered')
            check('released {evicted / TrimMiB} MiB of GPU caches{retained}' in trim, 'trim line prefix changed')
            check(context.count('TrimCaches(device <= DeviceCriticalPercent') == 1, 'periodic device-short trim changed')
            texture_cache = (source / 'src/Ryujinx.Graphics.Gpu/Image/TextureCache.cs').read_text()
            check('return _cache.Trim(level, freeOnly);' in texture_cache, 'texture cache forwarding')
        texture = (source / TEXTURE).read_text()
        members = '\n'.join(member(texture, signature) for signature in (
            'private struct TexturePoolOwner',
            'public void IncrementReferenceCount()',
            'public void IncrementReferenceCount(TexturePool pool, int id, ulong gpuVa)',
            'public bool HasOneReference()',
            'public bool DecrementReferenceCount()',
            'public bool DecrementReferenceCount(TexturePool pool, int id = -1)',
            'private void AddView(Texture texture)',
            'private void RemoveView(Texture texture)',
            'private void DeleteIfNotUsed()',
        ))
        (work / 'ProductionTexture.cs').write_text('using System;\nusing System.Collections.Generic;\nusing System.Diagnostics;\n'
                                                  'namespace Ryujinx.Graphics.Gpu.Image {\npartial class Texture {\n' + members + '\n}\n}\n')
        shutil.copyfile(source / 'src/Ryujinx.Graphics.Gpu/Image/AutoDeleteCache.cs', work / 'AutoDeleteCache.cs')
        shutil.copyfile(ROOT / 'test/melonx_device_short_trim/Program.cs', work / 'Program.cs')
        (work / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><LangVersion>preview</LangVersion>
<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><NoWarn>CS0649;CS0414;CS0169</NoWarn>
</PropertyGroup><ItemGroup><Compile Remove="source/**" /></ItemGroup></Project>''')
        (work / 'nuget.config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        build = subprocess.run([DOTNET, 'build', 'Probe.csproj', '-c', 'Release', '-nologo', '-v', 'q'],
                               cwd=work, capture_output=True, text=True, timeout=300)
        if build.returncode:
            print(build.stdout[-5000:], build.stderr[-2000:], flush=True)
            build.check_returncode()
        run = subprocess.run([DOTNET, 'bin/Release/net10.0/Probe.dll', variant], cwd=work, capture_output=True, text=True, timeout=60)
        if run.returncode:
            print(run.stdout, run.stderr, flush=True)
            run.check_returncode()
        reports[variant] = json.loads(run.stdout.strip().splitlines()[-1])
        print(json.dumps(reports[variant]), flush=True)

control, candidate = reports['control']['reports'], reports['candidate']['reports']
check(control['deliveredWarning'] == candidate['deliveredWarning'] and
      control['deliveredCritical'] == candidate['deliveredCritical'], 'delivered trim changed')
critical = dict(executed=False)
if CRITICAL:
    final = reports['final']['reports']
    check(all(final[name] == candidate[name] for name in candidate), 'final: every candidate scenario gives the candidate\'s result')
    w, c = final['onlyUnreferencedWarning'], final['onlyUnreferencedCritical']
    # Warning (an escalated trim) wants 80 of 320 MiB: the five oldest textures the cache alone holds, the GPU-written
    # ones flushed first; the pool-referenced ones walked past are kept. Every byte counted as released is destroyed.
    check(w == dict(evictedMiB=80, destroyedMiB=80, flushes=3, flushCalls=3, dependentSynchronizations=5,
                    leftCache='gpu1,cold2,gpu4,cold5,gpu7', poolReferencedDropped=0, keptMiB=48, totalMiB=240),
          'flagged Warning: ' + json.dumps(w))
    # Critical wants 160 MiB: ten textures, five of them flushed; five pool-referenced kept (80 MiB).
    check(c == dict(evictedMiB=160, destroyedMiB=160, flushes=5, flushCalls=5, dependentSynchronizations=10,
                    leftCache='gpu1,cold2,gpu4,cold5,gpu7,cold8,gpu10,cold11,gpu13,cold14', poolReferencedDropped=0, keptMiB=80,
                    totalMiB=160), 'flagged Critical: ' + json.dumps(c))
    delivered = candidate['deliveredWarning']
    check(delivered['destroyedMiB'] < delivered['evictedMiB'] == w['evictedMiB'] == w['destroyedMiB'] and
          candidate['deviceShortCritical']['destroyedMiB'] < c['destroyedMiB'],
          'the flagged trim destroys all it counts (the delivered one counts pool textures it cannot free), and a Critical one more '
          'than the flush-free trim')
    dirty = final['onlyUnreferencedCpuDirty']
    check(dirty == dict(evictedMiB=80, destroyedMiB=80, flushes=2, flushCalls=2, dependentSynchronizations=4,
                        leftCache='gpu1,cold2,gpu4,cold5,gpu7', poolReferencedDropped=0, keptMiB=48, totalMiB=240),
          'guest memory written by the CPU since: evicted without flush or dependents, as the capacity eviction: ' + json.dumps(dirty))
    check(final['flagOnOtherThread'] == candidate['deliveredWarning'], 'the flag is per thread: another thread\'s flag changes nothing')
    critical = dict(executed=True, flaggedWarningDestroyedMiB=w['destroyedMiB'], flaggedCriticalDestroyedMiB=c['destroyedMiB'],
                    flaggedCriticalFlushes=c['flushes'], poolReferencedDropped=0, candidateScenariosUnchanged=True)
inputs = ['build-utils/melonx/adapt_device_short_trim.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_device_short_trim_test.py', 'test/melonx_device_short_trim/Program.cs', 'test/melonx_adapter_control.py']
if critical['executed']:
    inputs += ['build-utils/melonx/adapt_device_critical_trim.py', 'test/melonx_device_short_trim/Final.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION, sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core631Preparation', postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE} if FINAL_PREPARATION else {}, fixtureChecks={k: v['checks'] for k, v in reports.items()}, reports=reports,
               sdk=sdk, physicalDeviceTested=False, gpuStorageDoubled=True, finalCriticalTrim=critical,
               sourceBaseline={**BASELINE, TEXTURE: TEXTURE_SHA},
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Production AutoDeleteCache and Texture reference members with doubles for storage and '
                          'group handles; the device-memory effect and any stall change are not measured.')
out = ROOT / 'dist/melonx/device-short-trim-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))

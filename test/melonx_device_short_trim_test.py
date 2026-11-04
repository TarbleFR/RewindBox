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
"""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
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


reports = {}
with tempfile.TemporaryDirectory(prefix='melonx-device-short-trim-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        source = work / 'source'
        for name in [*BASELINE, TEXTURE]:
            (source / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / name, source / name)
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
inputs = ['build-utils/melonx/adapt_device_short_trim.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_device_short_trim_test.py', 'test/melonx_device_short_trim/Program.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, fixtureChecks={k: v['checks'] for k, v in reports.items()}, reports=reports,
               sdk=sdk, physicalDeviceTested=False, gpuStorageDoubled=True,
               sourceBaseline={**BASELINE, TEXTURE: TEXTURE_SHA},
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Production AutoDeleteCache and Texture reference members with doubles for storage and '
                          'group handles; the device-memory effect and any stall change are not measured.')
out = ROOT / 'dist/melonx/device-short-trim-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))

#!/usr/bin/env python3
"""Execute the compiled MeloNX GPU teardown with and without adapt_gpu_lifetime.

Usage: melonx_gpu_teardown_test.py <pinned MeloNX checkout>

Both variants build the real Ryujinx.Graphics.Gpu, Ryujinx.Cpu and
Ryujinx.Memory projects from the pinned source. Only the GAL renderer is an
inert double; no Vulkan/Metal device, guest game or iPhone is involved.
The control must reproduce the device failure signature; the fixed variant
must release every cache, the CPU memory reference and the renderer.
"""
from pathlib import Path
import hashlib, json, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_gpu_lifetime import apply

PIN = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
actual = subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip()
assert actual == PIN['revision'], (actual, PIN['revision'])
assert not subprocess.check_output(['git', '-C', str(SOURCE), 'status', '--porcelain', '--', 'src/Ryujinx.Graphics.Gpu',
                                    'src/Ryujinx.Memory', 'src/Ryujinx.Cpu'], text=True).strip()

HARNESS = ROOT / 'test/melonx_gpu_teardown'
PROJECTS = ['Ryujinx.Graphics.Gpu', 'Ryujinx.Cpu', 'Ryujinx.Memory', 'Ryujinx.Common', 'Ryujinx.Graphics.Device',
            'Ryujinx.Graphics.GAL', 'Ryujinx.Graphics.Texture', 'Ryujinx.Graphics.Shader', 'ARMeilleure',
            'Spv.Generator']


def build_variant(work: Path, fixed: bool) -> dict:
    source = work / 'source'
    (source / 'src').mkdir(parents=True)
    for name in ['Directory.Build.props', 'Directory.Packages.props', 'global.json', 'nuget.config']:
        if (SOURCE / name).exists():
            shutil.copyfile(SOURCE / name, source / name)
    for project in PROJECTS:
        if (SOURCE / 'src' / project).is_dir():
            shutil.copytree(SOURCE / 'src' / project, source / 'src' / project,
                            ignore=shutil.ignore_patterns('bin', 'obj'))
    if fixed:
        apply(source)
    gpu = source / 'src/Ryujinx.Graphics.Gpu/Ryujinx.Graphics.Gpu.csproj'
    text = gpu.read_text(encoding='utf-8-sig')
    assert text.count('</Project>') == 1
    # Test-only access to the internal production types; product unchanged.
    gpu.write_text(text.replace('</Project>', '  <ItemGroup><InternalsVisibleTo Include="MeloNXGpuTeardownProbe" /></ItemGroup>\n</Project>'))
    # The probe lives outside the source tree. Pin the same SDK as build_core.sh;
    # a runner's newer preinstalled SDK would otherwise compile preview C#.
    (work / 'global.json').write_text(json.dumps({'sdk': {'version': PIN['dotnet'], 'rollForward': 'disable'}}))
    probe = work / 'probe'
    probe.mkdir()
    for name in ['Program.cs', 'Fakes.cs']:
        shutil.copyfile(HARNESS / name, probe / name)
    (probe / 'MeloNXGpuTeardownProbe.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable>
    <AllowUnsafeBlocks>true</AllowUnsafeBlocks><NoWarn>CA1416;CS8632</NoWarn>
    <ManagePackageVersionsCentrally>false</ManagePackageVersionsCentrally>
  </PropertyGroup>
  <ItemGroup>
    <ProjectReference Include="{source}/src/Ryujinx.Graphics.Gpu/Ryujinx.Graphics.Gpu.csproj" />
    <ProjectReference Include="{source}/src/Ryujinx.Cpu/Ryujinx.Cpu.csproj" />
  </ItemGroup>
</Project>
''')
    variant = 'fixed' if fixed else 'control'
    build = subprocess.run(['dotnet', 'build', str(probe), '-c', 'Release', '-nologo', '-v', 'q'],
                           capture_output=True, text=True, timeout=900)
    if build.returncode:
        errors = [line for line in build.stdout.splitlines() if ': error ' in line]
        print('\n'.join(dict.fromkeys(errors[:40])), build.stdout[-3000:], build.stderr[-3000:], sep='\n')
        build.check_returncode()
    run = subprocess.run(['dotnet', str(probe / 'bin/Release/net10.0/MeloNXGpuTeardownProbe.dll'), variant],
                         capture_output=True, text=True, timeout=300)
    print(run.stdout, flush=True)
    if run.returncode:
        print(run.stderr, flush=True)
        run.check_returncode()
    report = json.loads(next(line for line in run.stdout.splitlines() if line.startswith('{')))
    # Warnings the device journal receives through the engine's Gpu log class.
    report['warnings'] = [line for line in run.stdout.splitlines() if '|W| Gpu' in line]
    return report


def check(control: dict, fixed: dict):
    failures = []

    def expect(condition, message):
        if not condition:
            failures.append(message)

    for report in (control, fixed):
        for name, value in report.items():
            if name == 'warnings':
                continue
            expect(not (isinstance(value, dict) and 'harnessException' in value), f"{report['variant']} {name}: {value}")

    # Device signature reproduced by the shipped code; removed by the fix.
    c, f = control['newTextureLargerThanCacheShare'], fixed['newTextureLargerThanCacheShare']
    expect(c.get('listedAfterCreate') is True and c.get('handlesReleasedBeforeTeardown', 0) > 0,
           'control: an evicted new texture must be listed with released tracking handles')
    expect(c.get('threw') is True and c.get('objectName') == 'Ryujinx.Memory.Tracking.RegionHandle'
           and c.get('throughTextureCacheTeardown') is True, 'control: teardown must reproduce the device RegionHandle stack')
    expect(c.get('cpuReferencesAfter') == c.get('cpuReferencesBefore'), 'control: the CPU memory reference stays retained')
    expect(f.get('listedAfterCreate') is True and f.get('handlesReleasedBeforeTeardown') == 0,
           'fixed: the texture being added stays owned and alive')
    expect(f.get('threw') is False and f.get('cpuReferencesAfter') == f.get('cpuReferencesBefore', 0) - 1
           and f.get('rendererDisposed') is True, 'fixed: teardown releases caches, CPU reference and renderer')

    c, f = control['releasedTextureStillListed'], fixed['releasedTextureStillListed']
    expect(c.get('listedAfterRelease') is True and c.get('threw') is True and c.get('throughTextureCacheTeardown') is True,
           'control: a released-but-listed texture must fail teardown like the device')
    expect(f.get('threw') is False and f.get('otherTextureHandlesReleased') is True
           and f.get('cpuReferencesAfter') == f.get('cpuReferencesBefore', 0) - 1, 'fixed: released texture skipped, others released')

    c, f = control['staleTrackingHandle'], fixed['staleTrackingHandle']
    expect(c.get('threw') is True and c.get('objectName') == 'Ryujinx.Memory.Tracking.RegionHandle', 'control: stale handle fails teardown')
    expect(f.get('threw') is False and f.get('otherTextureHandlesReleased') is True
           and f.get('cpuReferencesAfter') == f.get('cpuReferencesBefore', 0) - 1, 'fixed: stale handle tolerated, rest released')

    c, f = control['unregistrationRacesContextDispose'], fixed['unregistrationRacesContextDispose']
    expect(c.get('threw') is True, 'control: duplicate PhysicalMemory destruction fails')
    expect(f.get('threw') is False and f.get('cpuReferencesAfter') == f.get('cpuReferencesBefore', 0) - 1,
           'fixed: PhysicalMemory destroyed exactly once')

    c, f = control['failingDeferredAction'], fixed['failingDeferredAction']
    expect(c.get('threw') is True and (c.get('rendererDisposed') is False or c.get('laterActionsRun') == 0),
           'control: a failing deferred action skips later releases')
    expect(f.get('threw') is True and f.get('exception') == 'InvalidOperationException' and f.get('rendererDisposed') is True
           and f.get('laterActionsRun') == 1 and f.get('cpuReferencesAfter') == f.get('cpuReferencesBefore', 0) - 1,
           'fixed: the error still surfaces after every release was attempted')

    f = fixed['concurrentDeferredActions']
    expect(f.get('lost') == 0 and f.get('duplicated') == 0 and f.get('queueFailures') == 0,
           f'fixed: concurrent deferred actions run exactly once: {f}')

    warnings = '\n'.join(fixed['warnings'])
    expect('Texture cache kept its texture in use above the 1 MiB share' in warnings,
           'fixed: the retained oversized texture is reported once to the device journal')
    expect('skipped 1 texture(s) already released while still listed and 0 stale' in warnings
           and 'skipped 0 texture(s) already released while still listed and 1 stale' in warnings,
           'fixed: teardown reports released-but-listed textures and stale handles')
    expect(not any('Texture cache' in line for line in control['warnings']), 'control: no new diagnostics')

    f = fixed['consecutiveSessions']
    expect(f.get('cpuReferencesAfterEachSession') == [1] * 5, f'fixed: no reference accumulation across sessions: {f}')
    return failures


with tempfile.TemporaryDirectory(prefix='melonx-gpu-teardown-') as temporary:
    # macOS temporary paths are symlinks (/var -> /private/var). MSBuild would
    # load the same referenced projects under both spellings and race on them.
    work = Path(temporary).resolve()
    control = build_variant(work / 'control', False)
    fixed = build_variant(work / 'fixed', True)
failures = check(control, fixed)
inputs = ['build-utils/melonx/adapt_gpu_lifetime.py', 'test/melonx_gpu_teardown_test.py',
          'test/melonx_gpu_teardown/Program.cs', 'test/melonx_gpu_teardown/Fakes.cs']
receipt = dict(result='failed' if failures else 'passed', failures=failures, control=control, fixed=fixed,
               physicalDeviceTested=False, galDouble=True, upstreamRevision=PIN['revision'],
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs})
out = ROOT / 'dist/melonx/gpu-teardown-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
if failures:
    print('\n'.join(failures))
    sys.exit(1)
print('MeloNX GPU teardown: control reproduces the device signature; fixed passed 7 scenarios.')

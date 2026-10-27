#!/usr/bin/env python3
"""Execute the compiled MeloNX texture pool with and without adapt_texture_pool.

Usage: melonx_texture_pool_test.py <pinned MeloNX checkout>

Both variants build the real Ryujinx.Graphics.Gpu, Ryujinx.Cpu and
Ryujinx.Memory projects from the pinned source; only the GAL renderer is an
inert double (the GPU teardown test's). Pool descriptors are written like the
Hogwarts Legacy pool of the Build 562 app.log (0x5A5A5A5A) and rewritten
before each lookup round. Engine warnings and errors reach the RewindBox
journal (app.log) as EmbeddedRuntime forwards them: the control is the
delivered 562 engine (upstream pool, 562 journal), the fixed variant this
tree's. The control must journal one "Invalid texture format 0x25A5A" per
lookup, as on the device; the fixed variant returns the same results without
any. An in-range address keeps the upstream lookups, only journaled once per
power of two; a real mapped texture is unchanged.
"""
from pathlib import Path
import hashlib, json, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_texture_pool import apply

# The delivered 562 engine's journal (unchanged since 558).
BASELINE = '9b40129fa188f8e2aa6a35c94abea005406062d3'
JOURNAL = 'native/melonx/EmbeddedLaunchDiagnostics.cs'
RUNTIME = (ROOT / 'native/melonx/EmbeddedRuntime.cs').read_text()
assert 'EmbeddedLaunchDiagnostics.RecordEngine(entry.Level == LogLevel.Error, entry.Message);' in RUNTIME
assert 'EmbeddedLaunchDiagnostics.Record(EmbeddedLaunchDiagnostics.Stage,' not in RUNTIME

PIN = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
actual = subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip()
assert actual == PIN['revision'], (actual, PIN['revision'])
assert not subprocess.check_output(['git', '-C', str(SOURCE), 'status', '--porcelain', '--', 'src/Ryujinx.Graphics.Gpu',
                                    'src/Ryujinx.Memory', 'src/Ryujinx.Cpu'], text=True).strip()

HARNESS = ROOT / 'test/melonx_texture_pool'
PROJECTS = ['Ryujinx.Graphics.Gpu', 'Ryujinx.Cpu', 'Ryujinx.Memory', 'Ryujinx.Common', 'Ryujinx.Graphics.Device',
            'Ryujinx.Graphics.GAL', 'Ryujinx.Graphics.Texture', 'Ryujinx.Graphics.Shader', 'ARMeilleure',
            'Spv.Generator']
POOL = 'src/Ryujinx.Graphics.Gpu/Image/TexturePool.cs'
MEMORY = 'src/Ryujinx.Graphics.Gpu/Memory/MemoryManager.cs'


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
        adapted = apply(source)
        assert [p.relative_to(source).as_posix() for p in adapted] == [POOL, MEMORY]
        # The edit only adds the early rejection and widens one helper's access.
        upstream = (SOURCE / POOL).read_text(encoding='utf-8-sig').replace('\r\n', '\n')
        pool = (source / POOL).read_text(encoding='utf-8')
        added = pool[pool.index('                    // Outside the GPU address space'):
                     pool.index('                    TextureInfo info = GetInfo(descriptor, out int layerSize);\n                    texture = PhysicalMemory.TextureCache.FindOrCreateTexture(_channel.MemoryManager, TextureSearchFlags.ForSampler, info, layerSize);\n\n                    // If this happens')]
        assert pool.replace(added, '', 1) == upstream, 'TexturePool changed beyond the early rejection'
        memory = (source / MEMORY).read_text(encoding='utf-8')
        assert memory.replace('internal static bool ValidateAddress', 'private static bool ValidateAddress') == \
            (SOURCE / MEMORY).read_text(encoding='utf-8-sig').replace('\r\n', '\n')
    gpu = source / 'src/Ryujinx.Graphics.Gpu/Ryujinx.Graphics.Gpu.csproj'
    text = gpu.read_text(encoding='utf-8-sig')
    assert text.count('</Project>') == 1
    # Test-only access to the internal production types; product unchanged.
    gpu.write_text(text.replace('</Project>', '  <ItemGroup><InternalsVisibleTo Include="MeloNXTexturePoolProbe" /></ItemGroup>\n</Project>'))
    # build_core.sh's SDK line (10.0); a preinstalled preview SDK would compile preview C#.
    (work / 'global.json').write_text(json.dumps({'sdk': {'version': PIN['dotnet'], 'rollForward': 'latestFeature'}}))
    probe = work / 'probe'
    probe.mkdir()
    shutil.copyfile(HARNESS / 'Program.cs', probe / 'Program.cs')
    shutil.copyfile(ROOT / 'test/melonx_gpu_teardown/Fakes.cs', probe / 'Fakes.cs')
    (probe / 'Journal.cs').write_text((ROOT / JOURNAL).read_text() if fixed else
                                      subprocess.check_output(['git', 'show', f'{BASELINE}:{JOURNAL}'], cwd=ROOT, text=True))
    (probe / 'MeloNXTexturePoolProbe.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk">
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
    (work / 'journal').mkdir()
    run = subprocess.run(['dotnet', str(probe / 'bin/Release/net10.0/MeloNXTexturePoolProbe.dll'), variant,
                          str(work / 'journal/app.log')],
                         capture_output=True, text=True, timeout=600)
    print(run.stdout[-4000:], flush=True)
    if run.returncode:
        print(run.stderr[-4000:], flush=True)
        run.check_returncode()
    return json.loads(next(line for line in run.stdout.splitlines() if line.startswith('{')))


def check(control: dict, fixed: dict):
    failures = []

    def expect(condition, message):
        if not condition:
            failures.append(message)

    for report in (control, fixed):
        for name, value in report.items():
            expect(not (isinstance(value, dict) and 'harnessException' in value), f"{report['variant']} {name}: {value}")
    if failures:
        return failures

    expect(control['journalForwarding'] == 'Record' and fixed['journalForwarding'] == 'RecordEngine',
           'control forwards like the 562 engine, fixed like this tree')

    c, f = control['outOfSpaceGarbage'], fixed['outOfSpaceGarbage']
    # The app.log signature: every lookup after a pool write logs and journals.
    expect(c['nulls'] == c['lookups'] == f['nulls'] == f['lookups'] > 0, f'every lookup of a garbage ID is null: {c} {f}')
    expect(c['invalidFormatLogs'] == c['journalLines'] == c['lookups'],
           f'control: one "Invalid texture format 0x25A5A" logged and written to app.log per lookup: {c}')
    expect(f['invalidFormatLogs'] == f['journalLines'] == 0, f'fixed: nothing logged for an address outside the GPU space: {f}')
    expect(f['allocatedBytes'] * 100 < c['allocatedBytes'], f'fixed: no per-lookup allocation: {f} vs {c}')
    expect(f['milliseconds'] * 10 < c['milliseconds'], f'fixed: at least 10x less time on the looking-up thread: {f} vs {c}')

    c, f = control['unmappedGarbage'], fixed['unmappedGarbage']
    same = ('lookups', 'nulls', 'invalidFormatLogs')
    expect({k: c[k] for k in same} == {k: f[k] for k in same}, f'in-range unmapped address keeps the upstream lookups: {c} {f}')
    expect(c['invalidFormatLogs'] == c['lookups'] == c['nulls'] > 0, f'upstream path still reports an in-range bad format: {c}')
    # 8 first occurrences, then counts 16, 32, 64, 128, 256 of 320.
    expect(c['journalLines'] == c['lookups'] and f['journalLines'] == 8 + 5,
           f'repeated engine text: written once per occurrence in 562, bounded now: {c} {f}')

    c, f = control['mappedTexture'], fixed['mappedTexture']
    expect(c == f, f'a real texture is unchanged: {c} {f}')
    expect(f['created'] and f['width'] == 256 and f['height'] == 256 and f['format'] == 'R8G8B8A8Unorm'
           and f['sameOnSecondLookup'] and f['invalidFormatLogs'] == 0, f'mapped texture: {f}')
    return failures


with tempfile.TemporaryDirectory(prefix='melonx-texture-pool-') as temporary:
    work = Path(temporary).resolve()
    control = build_variant(work / 'control', False)
    fixed = build_variant(work / 'fixed', True)
failures = check(control, fixed)
inputs = ['build-utils/melonx/adapt_texture_pool.py', 'test/melonx_texture_pool_test.py',
          'test/melonx_texture_pool/Program.cs', 'test/melonx_gpu_teardown/Fakes.cs', JOURNAL,
          'native/melonx/EmbeddedRuntime.cs']
receipt = dict(result='failed' if failures else 'passed', failures=failures, control=control, fixed=fixed,
               physicalDeviceTested=False, galDouble=True, upstreamRevision=PIN['revision'],
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               upstreamInputs={p: hashlib.sha256((SOURCE / p).read_bytes()).hexdigest() for p in (POOL, MEMORY)})
out = ROOT / 'dist/melonx/texture-pool-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
if failures:
    print('\n'.join(failures))
    sys.exit(1)
c, f = control['outOfSpaceGarbage'], fixed['outOfSpaceGarbage']
print(f"MeloNX texture pool: {c['lookups']} garbage lookups — 562 engine {c['journalLines']} app.log lines, "
      f"{c['allocatedBytes'] // 1024} KiB, {c['milliseconds']:.1f} ms; fixed {f['journalLines']} lines, "
      f"{f['allocatedBytes'] // 1024} KiB, {f['milliseconds']:.1f} ms; in-range lookups unchanged and journaled "
      f"{fixed['unmappedGarbage']['journalLines']} times instead of {control['unmappedGarbage']['journalLines']}; mapped texture unchanged.")

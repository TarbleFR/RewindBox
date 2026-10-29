#!/usr/bin/env python3
"""Compile the complete production GAL and exercise failed threaded sessions.

All compiled engine files are bound to engine 81 by full-file SHA-256. The
pristine input is prepared with its actual preceding adapters, on a private
copy. The backend is inert; commands, maps, resources, program creation and
the embedded session lifetime are the actual production implementations.
"""
from pathlib import Path
import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
FIXTURE = ROOT / 'test/melonx_threaded_renderer_failures'
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_threaded_renderer_failures import apply, BASELINE

MANIFEST = json.loads((FIXTURE / 'baseline_sources.json').read_text())
EXTRAS = [
    'src/Ryujinx.Graphics.Gpu/Engine/Dma/DmaClass.cs',
    'src/Ryujinx.Graphics.Gpu/Engine/GPFifo/GPFifoDevice.cs',
    'src/Ryujinx.Graphics.Gpu/Image/TextureBindingsArrayCache.cs',
    'src/Ryujinx.Graphics.Vulkan/PipelineConverter.cs',
]
PREREQUISITES = [('adapt_gpu_allocations', 'apply'),
                 ('adapt_upload_lifetime', 'adapt_owner'),
                 ('adapt_shader_waits', 'apply'),
                 ('adapt_bindless_allocations', 'apply')]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


reports = {}
postimages = {}
with tempfile.TemporaryDirectory(prefix='melonx-threaded-failure-') as temporary:
    # macOS /var and /private/var must denote the same MSBuild source root.
    temporary = Path(temporary).resolve()
    baseline = temporary / 'baseline'
    for relative in list(MANIFEST) + EXTRAS:
        path = baseline / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / relative, path)
    renderer = baseline / 'src/Ryujinx.Graphics.GAL/Multithreading/ThreadedRenderer.cs'
    if digest(renderer) == BASELINE['ThreadedRenderer.cs']:
        preparation = 'accepted_exact_engine81'
    else:
        for module, function in PREREQUISITES:
            getattr(importlib.import_module(module), function)(baseline)
        preparation = 'prepared_pristine_to_exact_engine81'
    for relative, expected in MANIFEST.items():
        assert digest(baseline / relative) == expected, relative

    dotnet = os.environ.get('DOTNET', 'dotnet')
    env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1',
               DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
    for variant in ('control', 'candidate'):
        work = temporary / variant
        source = work / 'source'
        shutil.copytree(baseline, source)
        if variant == 'candidate':
            changed = apply(source)
            postimages = {str(p.relative_to(source)): digest(p) for p in changed}
            # Fail closed without mutating the sources used by the executable.
            duplicate = temporary / 'duplicate'
            shutil.copytree(source, duplicate)
            try:
                apply(duplicate)
            except AssertionError:
                pass
            else:
                raise AssertionError('second application unexpectedly accepted')

        (work / 'global.json').write_text('{"sdk":{"version":"10.0.100","rollForward":"disable"}}')
        (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        (work / 'Program.cs').write_text((FIXTURE / 'Program.cs').read_text())
        (work / 'Backend.cs').write_text((FIXTURE / 'Backend.cs').read_text())
        shutil.copyfile(ROOT / 'native/melonx/EmbeddedWindowLifetime.cs', work / 'EmbeddedWindowLifetime.cs')
        includes = ''.join(f'<Compile Include="source/{name}" />' for name in MANIFEST)
        defines = '<DefineConstants>CANDIDATE</DefineConstants>' if variant == 'candidate' else ''
        (work / 'Check.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk">
<PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>
<AllowUnsafeBlocks>true</AllowUnsafeBlocks><EnableDefaultCompileItems>false</EnableDefaultCompileItems>
<Nullable>disable</Nullable><NoWarn>CS0649;CS0067;CS0169</NoWarn>{defines}</PropertyGroup>
<ItemGroup>{includes}<Compile Include="Program.cs"/><Compile Include="Backend.cs"/>
<Compile Include="EmbeddedWindowLifetime.cs"/></ItemGroup></Project>''')
        build = subprocess.run([dotnet, 'build', 'Check.csproj', '-c', 'Release', '--nologo', '-v:q'],
                               cwd=work, env=env, text=True, capture_output=True, timeout=180)
        if build.returncode:
            print(build.stdout, build.stderr)
            raise SystemExit(build.returncode)
        modes = ['normal', 'old-invoke', 'old-preframe'] if variant == 'control' else ['normal', 'failures']
        reports[variant] = {}
        for mode in modes:
            run = subprocess.run([dotnet, 'bin/Release/net10.0/Check.dll', mode], cwd=work,
                                 env=env, text=True, capture_output=True, timeout=45)
            print(f'{variant}/{mode}: {run.stdout.strip()}')
            if run.returncode:
                print(run.stderr)
                raise SystemExit(run.returncode)
            reports[variant][mode] = json.loads(run.stdout.strip().splitlines()[-1])

receipt = {
    'upstream': json.loads((ROOT / 'build-utils/melonx/source.json').read_text()),
    'preparation': preparation, 'sdk': '10.0.100',
    'compiledProductionFiles': MANIFEST,
    'embeddedWindowLifetime': digest(ROOT / 'native/melonx/EmbeddedWindowLifetime.cs'),
    'postimages': postimages, 'reports': reports,
    'adapter': digest(ROOT / 'build-utils/melonx/adapt_threaded_renderer_failures.py'),
    'driver': digest(Path(__file__)),
    'fixtures': {p.name: digest(p) for p in sorted(FIXTURE.iterdir()) if p.is_file()},
    'limitations': ['Inert backend: no Vulkan driver or physical-device execution.',
                    'Only error transport and lifetime ordering are measured; no FPS claim.',
                    'Control reproductions use isolated processes and exit after proving stranded waits.'],
}
out = ROOT / 'dist/melonx/threaded-renderer-failures-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(out)

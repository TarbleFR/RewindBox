#!/usr/bin/env python3
"""Run the complete production cache loader against controlled external boundaries.

Normal and failure scenarios use its actual System.Threading.Thread workers,
BlockingCollection, compilation/validation queues, recovery and packaging code.
A separate candidate build injects only Thread.Start failure through an alias
whose successful calls delegate to real threads. No tested production text is
instrumented or extracted. No GPU performance or iOS behavior is claimed.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
FIXTURE = ROOT / 'test/melonx_shader_loader_lifetime'
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_shader_loader_lifetime import apply, RELATIVE, BASELINE

MANIFEST = json.loads((FIXTURE / 'baseline_sources.json').read_text())
assert MANIFEST[RELATIVE] == BASELINE


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


reports, postimages = {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-shader-loader-lifetime-') as temporary:
    temporary = Path(temporary).resolve()
    baseline = temporary / 'baseline'
    for relative, expected in MANIFEST.items():
        assert digest(SOURCE / relative) == expected, relative
        target = baseline / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / relative, target)

    dotnet = os.environ.get('DOTNET', 'dotnet')
    env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
    for variant in ('control', 'candidate', 'candidate-start-failure'):
        work = temporary / variant
        source = work / 'source'
        shutil.copytree(baseline, source)
        if variant != 'control':
            changed = apply(source)
            actual_postimages = {str(p.relative_to(source)): digest(p) for p in changed}
            if postimages:
                assert actual_postimages == postimages
            else:
                postimages = actual_postimages
                # A rejected second application must never mutate the source
                # that will be compiled; its copy is intentionally disposable.
                duplicate = temporary / 'duplicate'
                shutil.copytree(source, duplicate)
                try:
                    apply(duplicate)
                except AssertionError:
                    pass
                else:
                    raise AssertionError('second application unexpectedly accepted')
        for relative, expected in MANIFEST.items():
            assert digest(source / relative) == postimages.get(relative, expected) if variant != 'control' else digest(source / relative) == expected

        (work / 'global.json').write_text('{"sdk":{"version":"10.0.100","rollForward":"disable"}}')
        (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        for name in ('Program.cs', 'Boundaries.cs'):
            shutil.copyfile(FIXTURE / name, work / name)
        includes = ''.join(f'<Compile Include="source/{relative}" />' for relative in MANIFEST)
        defines = '' if variant == 'control' else 'CANDIDATE'
        if variant == 'candidate-start-failure':
            defines += ';START_FAULT'
        (work / 'Check.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk">
<PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>
<EnableDefaultCompileItems>false</EnableDefaultCompileItems><Nullable>disable</Nullable>
<NoWarn>CS0649;CS9113;CS0162</NoWarn><DefineConstants>{defines}</DefineConstants></PropertyGroup>
<ItemGroup>{includes}<Compile Include="Program.cs"/><Compile Include="Boundaries.cs"/></ItemGroup>
</Project>''')
        build = subprocess.run([dotnet, 'build', 'Check.csproj', '-c', 'Release', '--nologo', '-v:q'],
                               cwd=work, env=env, text=True, capture_output=True, timeout=120)
        if build.returncode:
            print(build.stdout, build.stderr)
            raise SystemExit(build.returncode)
        run = subprocess.run([dotnet, 'bin/Release/net10.0/Check.dll'], cwd=work,
                             env=env, text=True, capture_output=True, timeout=60)
        print(f'{variant}: {run.stdout.strip()}')
        if run.returncode:
            print(run.stderr)
            raise SystemExit(run.returncode)
        reports[variant] = json.loads(run.stdout.strip().splitlines()[-1])

receipt = {
    'upstream': json.loads((ROOT / 'build-utils/melonx/source.json').read_text()),
    'sdk': '10.0.100', 'compiledProductionFiles': MANIFEST,
    'postimages': postimages, 'reports': reports,
    'adapter': digest(ROOT / 'build-utils/melonx/adapt_shader_loader_lifetime.py'),
    'adapterHelper': digest(ROOT / 'build-utils/melonx/adapt_session.py'),
    'driver': digest(Path(__file__)),
    'fixtures': {p.name: digest(p) for p in sorted(FIXTURE.iterdir()) if p.is_file()},
    'limitations': [
        'Full production loader and ten supporting production files; storage, translator, IR, renderer and cache containers are controlled boundaries.',
        'Main control/candidate scenarios use real System.Threading.Thread without an alias or modified source.',
        'Only the separate start-failure executable aliases Thread; every successful Start and Join still uses an actual OS thread.',
        'Control failure cleanup explicitly completes its abandoned queue after observing workers outliving LoadShaders.',
        'Resource-release observation models the owning boundary after LoadShaders termination, not actual GPU disposal.',
        'No native GPU compilation, physical-device execution, launch-time or FPS measurement.'
    ],
}
out = ROOT / 'dist/melonx/shader-loader-lifetime-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(out)

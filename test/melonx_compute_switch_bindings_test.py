#!/usr/bin/env python3
"""adapt_compute_switch_bindings on the final preparation, against the Core 691 files as control, on the real engine.

Usage: melonx_compute_switch_bindings_test.py <control> --candidate-source <final preparation containing the adapter>

IPA 691 in play: the GPU thread spends 0.9-1.5 s per 5 s in gpuWork.bindings while the game alternates 1 500-2 500
compute dispatches per second with its draws; every dispatch cleared the compute and graphics binding state
(TextureBindingsManager.Rebind), so each switch resolved every bound texture again. The candidate keeps the
resolution and re-sends the bindings. For control and candidate the production Ryujinx.Graphics.Gpu builds; then
(test-only InternalsVisibleTo) test/melonx_compute_switch_bindings/Program.cs runs each engine's real TextureManager,
TextureBindingsManager, pools, textures and BufferManager on guest memory, with a GAL pipeline whose texture and image
slots are shared by compute and graphics per binding number (as the Vulkan DescriptorSetUpdater's). Required: after
every commit the committing pipeline's slots hold the textures its handles name now, through handle changes, a pool
rewrite and two draws in a row; control and candidate give the same slot sequence and the same backend calls; steady
compute/graphics pairs are timed on both. Source: only CommitComputeBindings uses RebindHost; every other Rebind
caller is unchanged; the flag is cleared after each commit. Writes dist/melonx/compute-switch-bindings-checks.json.
No device, no FPS claim.
"""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_compute_switch_bindings', _HOLD)
import adapt_compute_switch_bindings as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
GPU = 'src/Ryujinx.Graphics.Gpu/'
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


for name, expected in adapter.BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 691 preparation: ' + name)

environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
reports, texts = {}, {}


def dotnet(*arguments, cwd, timeout=2400):
    result = subprocess.run([DOTNET, *arguments], capture_output=True, text=True, timeout=timeout, env=environment, cwd=cwd)
    if result.returncode:
        errors = [line for line in result.stdout.splitlines() if ': error ' in line]
        print('\n'.join(dict.fromkeys(errors[:40])), result.stdout[-4000:], result.stderr[-2000:], sep='\n', flush=True)
    return result


with tempfile.TemporaryDirectory(prefix='melonx-compute-switch-bindings-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj', 'MeloNX'), symlinks=True)
        if variant == 'candidate':
            changed = adapter.apply(work)
            check(sorted(str(p.relative_to(work)) for p in changed) == sorted(adapter.BASELINE), 'adapter changed other files')
            if FINAL_PREPARATION:
                for name in adapter.BASELINE:
                    check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
        texts[variant] = {name: (work / name).read_text(encoding='utf-8-sig') for name in adapter.BASELINE}
        build = dotnet('build', str(work / (GPU + 'Ryujinx.Graphics.Gpu.csproj')), '-c', 'Release', '-nologo', '-m:1',
                       '-p:NuGetAudit=false', cwd=work)
        check(build.returncode == 0, variant + ' production Ryujinx.Graphics.Gpu builds')
        if variant == 'candidate':
            warnings = sorted({line for line in build.stdout.splitlines() if 'warning' in line and
                               any(f in line for f in ('TextureManager.cs', 'TextureBindingsManager.cs'))})
            check(not warnings, 'no compiler warning in the edited files: ' + '\n'.join(warnings[:5]))
        project = work / (GPU + 'Ryujinx.Graphics.Gpu.csproj')
        text = project.read_text(encoding='utf-8-sig')
        project.write_text(text.replace('</Project>', '  <ItemGroup><InternalsVisibleTo Include="MeloNXBindingsProbe" /></ItemGroup>\n</Project>'))
        probe = Path(temporary).resolve() / ('probe-' + variant)
        probe.mkdir()
        shutil.copyfile(ROOT / 'test/melonx_compute_switch_bindings/Program.cs', probe / 'Program.cs')
        shutil.copyfile(ROOT / 'test/melonx_gpu_teardown/Fakes.cs', probe / 'Fakes.cs')
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
        run = subprocess.run([DOTNET, str(probe / 'bin/Release/net10.0/MeloNXBindingsProbe.dll')], capture_output=True, text=True,
                             timeout=900, env=environment, cwd=probe)
        if run.returncode:
            print(run.stdout[-4000:], run.stderr[-4000:], flush=True)
        check(run.returncode == 0, variant + ' probe runs')
        reports[variant] = json.loads(next(line for line in run.stdout.splitlines() if line.startswith('{')))

control, candidate = reports['control'], reports['candidate']
print(json.dumps({k: {x: v[x] for x in ('errors', 'steadyCalls', 'timedMs', 'timedBackendCalls')} for k, v in reports.items()}), flush=True)
check(not control['errors'], 'control: every committed slot holds the named texture: ' + '; '.join(control['errors'][:3]))
check(not candidate['errors'], 'candidate: every committed slot holds the named texture: ' + '; '.join(candidate['errors'][:3]))
check(candidate['sequence'] == control['sequence'], 'same slot sequence as the control')
check(len(candidate['sequence']) == 24, 'every step committed')
check(candidate['steadyCalls'] == control['steadyCalls'], 'same backend calls in the steady phase')
check(candidate['timedBackendCalls'] == control['timedBackendCalls'], 'same backend calls in the timed phase')
check(candidate['timedMs'] < control['timedMs'], 'steady compute/graphics pairs are cheaper')

mc, mk = texts['control'][adapter.MANAGER], texts['candidate'][adapter.MANAGER]
bc, bk = texts['control'][adapter.BINDINGS], texts['candidate'][adapter.BINDINGS]
check(mk.count('RebindHost();') == 2 and mc.count('Rebind();') - mk.count('Rebind();') == 2, 'only CommitComputeBindings changes caller')
check(bk.count('Array.Clear(_textureState);') == 1 and 'Rebind();\n\n                _cachedTexturePool = texturePool;' in bk.replace('\r', ''),
      'a pool change still clears the state')
check(bk.count('_resendHost = false;') == 1 and bk.index('_resendHost = false;') > bk.index('CommitRenderScale();'),
      'the flag is cleared after the commit')
check(bk.count('_context.Renderer.Pipeline.SetTextureAndSampler(') == bc.count('_context.Renderer.Pipeline.SetTextureAndSampler(') + 1 and
      bk.count('_context.Renderer.Pipeline.SetImage(') == bc.count('_context.Renderer.Pipeline.SetImage(') + 1, 'one re-send per fast path')
check(bc.count('state.CachedTexture.InvalidatedSequence == state.InvalidatedSequence') ==
      bk.count('state.CachedTexture.InvalidatedSequence == state.InvalidatedSequence') == 2, 'fast-path validity checks unchanged')

inputs = ['build-utils/melonx/adapt_compute_switch_bindings.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_compute_switch_bindings_test.py', 'test/melonx_compute_switch_bindings/Program.cs',
          'test/melonx_gpu_teardown/Fakes.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core691Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in adapter.BASELINE} if FINAL_PREPARATION else {},
               control={k: control[k] for k in ('steadyCalls', 'timedMs', 'timedBackendCalls', 'timedPairs')},
               candidate={k: candidate[k] for k in ('steadyCalls', 'timedMs', 'timedBackendCalls', 'timedPairs')},
               sequence=candidate['sequence'], sdk=sdk, physicalDeviceTested=False, productionGpuAssemblyBuilt=True,
               sourceBaseline=adapter.BASELINE, inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs})
out = ROOT / 'dist/melonx/compute-switch-bindings-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))

#!/usr/bin/env python3
"""adapt_pipeline_failure_state and adapt_array_delta_causes on the final preparation, against the Core 693 files.

Usage: melonx_core695_diagnostics_test.py <control> --candidate-source <final preparation containing both adapters>

IPA 692: program 890A188FB55B5D5D (host cache program 1837) fails pipeline creation on the device only, and the bindless
delta passes scan whole 524 288-element arrays for an unknown reason. Both adapters are diagnostics only. For control
and candidate the production Ryujinx.Graphics.Vulkan and Ryujinx.Graphics.Gpu assemblies are built (no compiler warning
in the edited files). A probe compiled against the candidate's assemblies (test-only InternalsVisibleTo) runs the real
NotePipelineFailureState on a PipelineState with two color attachments, depth and two vertex attributes, and the real
NoteDeltaPass on 1024 passes of known causes, with a capturing log target (test/melonx_core695_diagnostics/Program.cs):
the state line's fields, once per (program, state), at most 64 lines; one cause line every 512 passes with each cause
counted. Source: the state line is emitted only on a creation error, after the existing identity line; the delta pass
takes the same branches as the control (the added lines are counters only). Writes
dist/melonx/core695-diagnostics-checks.json. No device.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_STATE = control_source(SOURCE, 'adapt_pipeline_failure_state', _HOLD)
SOURCE, FINAL_DELTA = control_source(SOURCE, 'adapt_array_delta_causes', _HOLD)
FINAL_PREPARATION = FINAL_STATE and FINAL_DELTA
import adapt_pipeline_failure_state as state_adapter  # noqa: E402
import adapt_array_delta_causes as delta_adapter  # noqa: E402

ADAPTERS = (state_adapter, delta_adapter)
FILES = {**state_adapter.BASELINE, **delta_adapter.BASELINE}
DOTNET = os.environ.get('DOTNET', 'dotnet')
VULKAN = 'src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj'
GPU = 'src/Ryujinx.Graphics.Gpu/Ryujinx.Graphics.Gpu.csproj'
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


check(FINAL_STATE == FINAL_DELTA, 'both adapters or neither in the candidate source')
for name, expected in FILES.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 693 preparation: ' + name)

environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')


def dotnet(*arguments, cwd, timeout=2400):
    result = subprocess.run([DOTNET, *arguments], capture_output=True, text=True, timeout=timeout, env=environment, cwd=cwd)
    if result.returncode:
        errors = [line for line in result.stdout.splitlines() if ': error ' in line]
        print('\n'.join(dict.fromkeys(errors[:40])), result.stdout[-4000:], result.stderr[-2000:], sep='\n', flush=True)
    return result


texts = {}
with tempfile.TemporaryDirectory(prefix='melonx-core695-diagnostics-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj', 'MeloNX'), symlinks=True)
        if variant == 'candidate':
            for adapter in ADAPTERS:
                changed = adapter.apply(work)
                check(sorted(str(p.relative_to(work)) for p in changed) == sorted(adapter.BASELINE), 'adapter changed other files')
            if FINAL_PREPARATION:
                for name in FILES:
                    check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapters: ' + name)
        texts[variant] = {name: (work / name).read_text(encoding='utf-8-sig') for name in FILES}
        for project in (VULKAN, GPU):
            build = dotnet('build', str(work / project), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false', cwd=work)
            check(build.returncode == 0, variant + ' production ' + Path(project).stem + ' builds')
            if variant == 'candidate':
                warnings = sorted({line for line in build.stdout.splitlines() if 'warning' in line and
                                   any(Path(f).name in line for f in FILES)})
                check(not warnings, 'no compiler warning in the edited files: ' + '\n'.join(warnings[:5]))

    work = Path(temporary).resolve() / 'candidate'
    for project in (VULKAN, GPU):
        path = work / project
        text = path.read_text(encoding='utf-8-sig')
        path.write_text(text.replace('</Project>', '  <ItemGroup><InternalsVisibleTo Include="MeloNXCore695Probe" /></ItemGroup>\n</Project>'))
    probe = Path(temporary).resolve() / 'probe'
    probe.mkdir()
    shutil.copyfile(ROOT / 'test/melonx_core695_diagnostics/Program.cs', probe / 'Program.cs')
    (probe / 'MeloNXCore695Probe.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable>
    <AllowUnsafeBlocks>true</AllowUnsafeBlocks><NoWarn>CA1416;CS8632</NoWarn><NuGetAudit>false</NuGetAudit>
    <ManagePackageVersionsCentrally>false</ManagePackageVersionsCentrally>
  </PropertyGroup>
  <ItemGroup>
    <ProjectReference Include="{work}/{VULKAN}" />
    <ProjectReference Include="{work}/{GPU}" />
  </ItemGroup>
</Project>
''')
    for extra in ('global.json', 'nuget.config'):
        if (work / extra).exists():
            shutil.copyfile(work / extra, probe / extra)
    build = dotnet('build', str(probe / 'MeloNXCore695Probe.csproj'), '-c', 'Release', '-nologo', '-m:1', cwd=probe)
    check(build.returncode == 0, 'probe builds against the candidate assemblies')
    run = subprocess.run([DOTNET, str(probe / 'bin/Release/net10.0/MeloNXCore695Probe.dll')], capture_output=True, text=True,
                         timeout=900, env=environment, cwd=probe)
    if run.returncode:
        print(run.stdout[-4000:], run.stderr[-4000:], flush=True)
    check(run.returncode == 0, 'probe runs')
    report = json.loads(next(line for line in run.stdout.splitlines() if line.startswith('{')))
print(json.dumps(report), flush=True)

first = report['first']
check(report['stateLines'] == 64, 'at most 64 state lines; the same (program, state) once, another state of it again')
check(first.startswith('Gpu : Pipeline failure state for program 890A188FB55B5D5D (') and first.endswith(' (adapt_pipeline_failure_state)'),
      'an Error line of the Gpu class names the program')
check(re.search(r': ids( [0-9A-F]{16}){9};', first) is not None, 'the nine raw PipelineUid words')
check('rasterizerDiscard False, alphaToCoverage False, depthStencil True, polygon Fill, topology TriangleList, samples 1' in first,
      'rasterization, depth/stencil, topology and samples')
check('; blends 2: [0] on mask F R8G8B8A8Unorm [1] off mask 7 R16G16B16A16Sfloat; depth D32SfloatS8Uint;' in first,
      'every color attachment and the depth format')
check('; integer mask 0, logic ops False;' in first, 'integer mask and logic ops')
check('; vertex attributes 2: 0:R32G32B32Sfloat:0:0 1:R16G16Sfloat:1:12; vertex bindings 2: 0:12:Vertex 1:16:Instance' in first,
      'vertex attributes and bindings')
check('topology TriangleStrip' in report['third'] and '890A188FB55B5D5D' in report['third'], 'another state of the program is logged')

lines = report['deltaLines']
check(len(lines) == 2 and all(line.startswith('Gpu NoteDeltaPass: ') for line in lines), 'one Gpu cause line every 512 passes')
lines = [line[len('Gpu NoteDeltaPass: '):] for line in lines]
check(lines[0] == 'Bindless delta passes: 512 (logged 192; whole scans: samplers 64, aliases moved 64, other pool 64, log overflow 64, '
      'invalidated texture 64); elements visited 167774080, changed 0; epoch rescans 0; full rebuilds 0; textures synchronised '
      'per pass 2000 (adapt_array_delta_causes)', 'each cause counted: ' + lines[0])
check(lines[1].startswith('Bindless delta passes: 1024 (logged 384;'), 'the counters accumulate')

sc, sk = texts['control'][state_adapter.STATE], texts['candidate'][state_adapter.STATE]
check(sk.replace(state_adapter.CALL_NEW, state_adapter.CALL_OLD).replace(state_adapter.METHOD_NEW, state_adapter.METHOD_ANCHOR) == sc,
      'nothing else in PipelineState.cs changes')
check(sk.count('NotePipelineFailureState(program);') == 1 and
      sk.index('NotePipelineFailure(program, result, cachePipelineFailure);') < sk.index('NotePipelineFailureState(program);') <
      sk.index('Draws for this state are unavailable.'), 'on a creation error only, after the identity line')
method = sk[sk.index('private readonly void NotePipelineFailureState('):sk.index('public readonly void Dispose()')]
check('_failedStates.Count >= 64' in method and method.count('Logger.Error?.PrintMsg(') == 1, 'bounded, one line')
check('program.AddGraphicsPipeline' not in method and 'return false' not in method and 'Internal.Id' in method and
      re.search(r'\b(this|Internal|state\.Internal)\.?\w*(\[[^\]]*\])?\s*=[^=]', method) is None and
      re.search(r'\bstate\.\w+\s*=[^=]', method) is None, 'reads the state only')

cc, ck = texts['control'][delta_adapter.CACHE], texts['candidate'][delta_adapter.CACHE]
restored = ck
for old, new in ((delta_adapter.ENTRY_OLD, delta_adapter.ENTRY_NEW), (delta_adapter.EPOCH_OLD, delta_adapter.EPOCH_NEW),
                 (delta_adapter.COUNT_OLD, delta_adapter.COUNT_NEW), (delta_adapter.FINALLY_OLD, delta_adapter.FINALLY_NEW),
                 (delta_adapter.METHOD_OLD, delta_adapter.METHOD_NEW)):
    restored = restored.replace(new, old)
check(restored == cc, 'nothing else in TextureBindingsArrayCache.cs changes')
added = [line.strip() for line in ck.splitlines() if line not in set(cc.splitlines())]
body = ck[ck.index('private void NoteDeltaPass('):ck.index('/// Updates the elements of a pool array whose pool objects changed')]
check(all(not line.startswith(('return', 'continue', 'break', 'goto', 'throw')) for line in added), 'no control flow added to the pass')
check('entry.' not in body and 'texturePool' not in body and 'Synchronize' not in body, 'the counters touch no pass state')
check('_deltaPasses % 512 == 0' in body and body.count('Logger.Warning?.Print(') == 1, 'one line every 512 passes')
check(ck.index('bool otherPool =') < ck.index('CollectLoggedChanges(entry, texturePool, logPosition, out candidates)', ck.index('bool otherPool =')),
      'causes measured before CollectLoggedChanges updates the entry')

inputs = ['build-utils/melonx/adapt_pipeline_failure_state.py', 'build-utils/melonx/adapt_array_delta_causes.py',
          'build-utils/melonx/adapt_session.py', 'test/melonx_core695_diagnostics_test.py',
          'test/melonx_core695_diagnostics/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core693Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in FILES} if FINAL_PREPARATION else {},
               report=report, sdk=sdk, physicalDeviceTested=False, productionVulkanAssemblyBuilt=True,
               productionGpuAssemblyBuilt=True, sourceBaseline=FILES,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs})
out = ROOT / 'dist/melonx/core695-diagnostics-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))

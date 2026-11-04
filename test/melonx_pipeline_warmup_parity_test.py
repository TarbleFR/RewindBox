#!/usr/bin/env python3
"""Pipeline warm-up parity (adapt_pipeline_warmup_parity) on the real prepared engine.

Usage: melonx_pipeline_warmup_parity_test.py <prepared MeloNX tree>

The tree is the output of build-utils/melonx/prepare_embedded.py on 13700519 (Core 631 preparation). Two
copies are compiled with the .NET SDK: control (the tree as prepared) and candidate (plus the adapter). In each,
the production Vulkan backend (with GAL, Common, Shader, Spv) and the production GPU assembly (with its project
references) are built as executables with a fixture Program.cs:

- Vulkan: the warm-up key of PipelineConverter against the draw key after the real PipelineBase
  .SetMultisampleState, looked up in the real HashTableSlim. Control must miss with alpha to coverage or alpha to
  one, candidate must hit; candidate names every key property (reflection proves the list complete) and arrays.
- GPU: ShaderSpecializationState written and read by the real BinarySerializer. Every cache entry must be byte
  for byte the control's (format unchanged); candidate takes alpha to coverage from the specialization state.

Static checks bind the remaining wiring (StateUpdater, ShaderCollection warning). No Vulkan, Metal or device
call; no FPS claim. Writes dist/melonx/pipeline-warmup-parity-checks.json.
"""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_pipeline_warmup_parity import apply, BASELINE, KEY_PROPERTIES

for name, expected in BASELINE.items():
    assert hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the 631 preparation: ' + name

DOTNET = os.environ.get('DOTNET', 'dotnet')
FIXTURES = {'vulkan': 'src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj',
            'gpu': 'src/Ryujinx.Graphics.Gpu/Ryujinx.Graphics.Gpu.csproj'}
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def run(command, cwd, environment):
    result = subprocess.run(command, capture_output=True, text=True, timeout=900, env=environment, cwd=cwd)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
    result.check_returncode()
    return result.stdout


reports = {}
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
with tempfile.TemporaryDirectory(prefix='melonx-warmup-parity-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
        changed = apply(work) if variant == 'candidate' else []
        if variant == 'candidate':
            check(sorted(str(p.relative_to(work)) for p in changed) == sorted(BASELINE), 'adapter changed other files')
            text = {name: (work / name).read_text(encoding='utf-8-sig') for name in BASELINE}
            updater = text['src/Ryujinx.Graphics.Gpu/Engine/Threed/StateUpdater.cs']
            check(updater.index('_pipeline.AlphaToCoverageEnable = alphaToCoverageEnable;') <
                  updater.index('_context.Renderer.Pipeline.SetMultisampleState(') and
                  updater.index('new StateUpdateCallbackEntry(UpdateMultisampleState') <
                  updater.index('new StateUpdateCallbackEntry(UpdateShaderState'),
                  'multisample state not recorded before the shader state takes ProgramPipelineState')
            collection = text['src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs']
            check(collection.count('DescribeInitialKeyDifference(ref key)') == 1 and
                  collection.count('"Background pipeline compile missed on draw - incorrect pipeline state?" +') == 1 and
                  collection.count('PipelineUid warmUp = GetInitialGraphicsPipelineKey();') == 1,
                  'miss warning not wired to the warm-up key description')
            # The description is an argument of Logger.Warning?.Print: not evaluated when warnings are off.
            warning = collection[collection.index('Logger.Warning?.Print(LogClass.Gpu, "Background pipeline'):]
            check(warning.index('DescribeInitialKeyDifference') < warning.index(';'), 'description outside the conditional call')
            spec = text['src/Ryujinx.Graphics.Gpu/Shader/ShaderSpecializationState.cs']
            check(spec.count('WriteWithMagicAndSize(ref pipelineState, PgpsMagic, ProgramPipelineState.PersistedSize)') == 1 and
                  spec.count('WriteWithMagicAndSize(ref pipelineState, PgpsMagic);') == 0, 'pipeline state not written at its persisted size')
        for fixture, relative in FIXTURES.items():
            project = work / relative
            tree = ET.parse(project)
            group = ET.SubElement(tree.getroot(), 'PropertyGroup')
            for name, value in [('OutputType', 'Exe'), ('StartupObject', 'Program'), ('NuGetAudit', 'false'),
                                ('EnableNETAnalyzers', 'false'), ('TreatWarningsAsErrors', 'false')]:
                ET.SubElement(group, name).text = value
            tree.write(project)
            shutil.copyfile(ROOT / 'test/melonx_pipeline_warmup_parity' / fixture / 'Program.cs', project.parent / 'Program.cs')
            run([DOTNET, 'build', str(project), '-c', 'Release', '-nologo', '-m:1'], work, environment)
            arguments = [variant] + ([','.join(KEY_PROPERTIES)] if fixture == 'vulkan' else [])
            output = run([DOTNET, str(project.parent / 'bin/Release/net10.0' / (project.stem + '.dll')), *arguments], work, environment)
            report = json.loads(next(line for line in output.splitlines() if line.startswith('{')))
            print(json.dumps(report), flush=True)
            reports[variant + '-' + fixture] = report

control, candidate = reports['control-vulkan'], reports['candidate-vulkan']
check(control['warmUpHit'] == {'none': True, 'alphaToCoverage': False, 'alphaToOne': False, 'both': False}, 'control misses not reproduced')
check(candidate['warmUpHit'] == {'none': True, 'alphaToCoverage': True, 'alphaToOne': True, 'both': True}, 'candidate still misses')
check(candidate['describedKeyProperties'] == len(KEY_PROPERTIES) == 49, 'description coverage')
control, candidate = reports['control-gpu'], reports['candidate-gpu']
check(control['cacheEntrySha256'] == candidate['cacheEntrySha256'], 'the shader disk cache bytes changed')
check(candidate['persistedSize'] == control['structSize'] and candidate['structSize'] == control['structSize'] + 4,
      'persisted prefix is not the struct every earlier build wrote')
inputs = ['build-utils/melonx/adapt_pipeline_warmup_parity.py', 'test/melonx_pipeline_warmup_parity_test.py',
          'test/melonx_pipeline_warmup_parity/vulkan/Program.cs', 'test/melonx_pipeline_warmup_parity/gpu/Program.cs',
          'build-utils/melonx/adapt_session.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, reports=reports, sdk=sdk, physicalDeviceTested=False, nativeCallsUsed=False,
               sourceBaseline=BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Host fixture of the key, cache bytes and description; the frequency of alpha-to-coverage '
                          'draws in Hogwarts Legacy and any FPS or stall change are not measured.')
out = ROOT / 'dist/melonx/pipeline-warmup-parity-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))

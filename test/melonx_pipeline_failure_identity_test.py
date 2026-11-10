#!/usr/bin/env python3
"""adapt_pipeline_failure_identity on the final preparation, against the Core 689 files as control.

Usage: melonx_pipeline_failure_identity_test.py <control> --candidate-source <final preparation containing the adapter>

IPA 688/690: a pipeline whose fragment shader SPIRV-Cross cannot convert ("nullptr") is not identified, its first
(background) failure is not logged by the Core, and its dropped draws count as "not ready" like async skips. For each
variant the production Vulkan assembly is built. The candidate's real NotePipelineFailure runs with doubles
(test/melonx_pipeline_failure_identity/Program.cs): one line per program with its StableHash, the thread, stages and
samples, at most 32 programs. Source: every async skip and every unavailable pipeline in PipelineBase is counted on its
own, the existing failure line and caching are unchanged. Diagnostics only. Writes
dist/melonx/pipeline-failure-identity-checks.json.
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
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_pipeline_failure_identity', _HOLD)
import adapt_pipeline_failure_identity as adapter  # noqa: E402

def _forward_matches(module_name, work, final_source, names, tmp):
    """The candidate plus the later adapters sharing its files (re-applied forward) is the final preparation."""
    import importlib as _importlib
    from melonx_adapter_control import later_sharing as _later_sharing
    forward = Path(tmp) / ('forward-' + module_name)
    later = _later_sharing(module_name)
    files = set(names).union(*(set(_importlib.import_module(n).BASELINE) for n in later)) if later else set(names)
    for name in files:
        (forward / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(work / name, forward / name)
    for n in later:
        _importlib.import_module(n).apply(forward)
    return {name: (forward / name).read_bytes() == (final_source / name).read_bytes() for name in names}

DOTNET = os.environ.get('DOTNET', 'dotnet')
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def member(text, signature):
    start = text.index(signature)
    start = text.rindex('\n', 0, start) + 1
    depth, index = 0, text.index('{', start)
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


for name, expected in adapter.BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 689 preparation: ' + name)

texts = {}
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
with tempfile.TemporaryDirectory(prefix='melonx-pipeline-failure-identity-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
        if variant == 'candidate':
            changed = adapter.apply(work)
            check(sorted(str(p.relative_to(work)) for p in changed) == sorted(adapter.BASELINE), 'adapter changed other files')
            if FINAL_PREPARATION:
                # Later adapters editing these files (adapt_worker_main_cache_lookup, PipelineState.cs) are re-applied forward.
                forward_ok = _forward_matches('adapt_pipeline_failure_identity', work, FINAL_SOURCE, adapter.BASELINE, temporary)
                for name in adapter.BASELINE:
                    check(forward_ok[name], 'final preparation is the adapter: ' + name)
        texts[variant] = {name: (work / name).read_text(encoding='utf-8-sig') for name in adapter.BASELINE}
        result = subprocess.run([DOTNET, 'build', str(work / 'src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj'), '-c', 'Release',
                                 '-nologo', '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=1800, env=environment, cwd=work)
        if result.returncode:
            print(result.stdout[-5000:], result.stderr[-2000:], flush=True)
        check(result.returncode == 0, variant + ' production Vulkan assembly builds')
    state = texts['candidate'][adapter.STATE]
    note = member(state, 'private readonly void NotePipelineFailure(')
    fixture = Path(temporary).resolve() / 'fixture'
    fixture.mkdir()
    program = (ROOT / 'test/melonx_pipeline_failure_identity/Program.cs').read_text()
    field = '        private static readonly System.Collections.Generic.HashSet<ulong> _failedPrograms = new();\n'
    check(field in state, 'bounded set present')
    (fixture / 'Program.cs').write_text(program.replace('//__NOTE__\n', field + note + '\n'))
    (fixture / 'Fixture.csproj').write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
        '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit></PropertyGroup></Project>\n')
    for command in ([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                    [DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll')]):
        result = subprocess.run(command, capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
        if result.returncode:
            print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
            result.check_returncode()
    report = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
print(json.dumps(report), flush=True)
check(report['count'] == 32, 'at most 32 programs logged')
check(report['first'] == 'Pipeline creation failed for program 0123456789ABCDEF: ErrorInitializationFailed; stages 2, samples 1, '
      'topology TriangleList, background worker (adapt_pipeline_failure_identity)', 'the first attempt names the program and thread')
check('program 0000000000000001' in report['second'], 'the same program is not logged twice')

pc, pk = texts['control'][adapter.PIPELINE], texts['candidate'][adapter.PIPELINE]
create = member(pk, 'private bool CreatePipeline(') if 'private bool CreatePipeline(' in pk else pk
check(pk.count('RenderStageTimer.AsyncSkips++;') == 3 and pk.count('RenderStageTimer.UnavailablePipelines++;') == 2,
      'three async skip sites and two unavailable-pipeline sites counted')
check(pc.count('return false;') == pk.count('return false;'), 'no return added or removed')
check('"; not ready by cause: async skips " + AsyncSkips + ", unavailable pipelines " + UnavailablePipelines' in pk and
      'AsyncSkips = UnavailablePipelines = 0;' in pk, 'line ends with the split; counters reset each window')
sc, sk = texts['control'][adapter.STATE], texts['candidate'][adapter.STATE]
check(sc.count('Draws for this state are unavailable.') == sk.count('Draws for this state are unavailable.') == 1 and
      sk.count('program.AddGraphicsPipeline(ref Internal, null);') == sc.count('program.AddGraphicsPipeline(ref Internal, null);'),
      'the existing failure line and failure caching are unchanged')
check(sk.index('NotePipelineFailure(program, result, cachePipelineFailure);') < sk.index('Draws for this state are unavailable.'),
      'every creation error is noted, worker attempts included')

inputs = ['build-utils/melonx/adapt_pipeline_failure_identity.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_pipeline_failure_identity_test.py', 'test/melonx_pipeline_failure_identity/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core689Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in adapter.BASELINE} if FINAL_PREPARATION else {},
               report=report, sdk=sdk, physicalDeviceTested=False, productionVulkanAssemblyBuilt=True, sourceBaseline=adapter.BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs})
out = ROOT / 'dist/melonx/pipeline-failure-identity-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))

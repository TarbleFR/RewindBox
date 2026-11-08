#!/usr/bin/env python3
"""adapt_worker_main_cache_lookup on the final preparation, against the Core 691 PipelineState.cs before it as control.

Usage: melonx_worker_main_cache_lookup_test.py <control> --candidate-source <final preparation containing the adapter>

IPA 690: about thirty pipelines compiled in earlier sessions are compiled again by the background workers in each
session's first minute: a worker creates in its own pipeline cache and never consults the main one. For each variant
the production Vulkan assembly is built; the worker branch of each variant and the candidate's real
TryCreateFromMainCache overloads and NoteMainCacheLookup run with doubles (test/melonx_worker_main_cache_lookup):
a pipeline the main cache holds is compiled again by the control and found by the candidate (graphics and compute);
a miss compiles once in the worker cache; a busy main lock is never waited for; during a checkpoint the side cache is
tried; without cache control nothing changes; the create flags are restored and the lock is released. Writes
dist/melonx/worker-main-cache-lookup-checks.json.
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
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_worker_main_cache_lookup', _HOLD)
import adapt_worker_main_cache_lookup as adapter  # noqa: E402

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


def inner(block):
    lines = block.splitlines(keepends=True)
    return ''.join(lines[2:-1])


for name, expected in adapter.BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 691 preparation: ' + name)

texts, reports = {}, {}
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
with tempfile.TemporaryDirectory(prefix='melonx-worker-main-cache-lookup-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
        if variant == 'candidate':
            changed = adapter.apply(work)
            check([str(p.relative_to(work)) for p in changed] == [adapter.STATE], 'adapter changed other files')
            if FINAL_PREPARATION:
                # Later adapters editing PipelineState.cs (Core 695: adapt_pipeline_failure_state) are re-applied forward.
                from melonx_adapter_control import later_sharing
                import importlib
                forward = Path(temporary).resolve() / 'forward'
                (forward / adapter.STATE).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(work / adapter.STATE, forward / adapter.STATE)
                for later in later_sharing('adapt_worker_main_cache_lookup'):
                    importlib.import_module(later).apply(forward)
                check((forward / adapter.STATE).read_bytes() == (FINAL_SOURCE / adapter.STATE).read_bytes(), 'final preparation is the adapter')
        text = (work / adapter.STATE).read_text(encoding='utf-8-sig')
        texts[variant] = text
        result = subprocess.run([DOTNET, 'build', str(work / 'src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj'), '-c', 'Release',
                                 '-nologo', '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=1800, env=environment, cwd=work)
        if result.returncode:
            print(result.stdout[-5000:], result.stderr[-2000:], flush=True)
        check(result.returncode == 0, variant + ' production Vulkan assembly builds')
        if variant == 'candidate':
            check(adapter.GRAPHICS_NEW in text and adapter.COMPUTE_NEW in text, 'worker branches present')
            graphics, compute = inner(adapter.GRAPHICS_NEW), inner(adapter.COMPUTE_NEW)
            helpers = '\n'.join([member(text, 'private static unsafe Result TryCreateFromMainCache(VulkanRenderer gd, Device device, GraphicsPipelineCreateInfo* info'),
                                 member(text, 'private static unsafe Result TryCreateFromMainCache(VulkanRenderer gd, Device device, ComputePipelineCreateInfo* info'),
                                 member(text, 'private static void NoteMainCacheLookup(')])
            helpers = ('        private static long _workerMainCacheHits;\n        private static long _workerMainCacheMisses;\n' + helpers + '\n')
        else:
            check(adapter.GRAPHICS_OLD in text and adapter.COMPUTE_OLD in text, 'control worker branches')
            graphics, compute, helpers = inner(adapter.GRAPHICS_OLD), inner(adapter.COMPUTE_OLD), ''
        fixture = Path(temporary).resolve() / ('fixture-' + variant)
        fixture.mkdir()
        program = (ROOT / 'test/melonx_worker_main_cache_lookup/Program.cs').read_text()
        program = program.replace('//__HELPERS__\n', helpers).replace('//__GRAPHICS__\n', graphics).replace('//__COMPUTE__\n', compute)
        (fixture / 'Program.cs').write_text(program)
        (fixture / 'Fixture.csproj').write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
            '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><AllowUnsafeBlocks>true</AllowUnsafeBlocks>'
            '<NoWarn>CS0169;CS0414;CS0649</NoWarn></PropertyGroup></Project>\n')
        for command in ([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                        [DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), variant]):
            result = subprocess.run(command, capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
            if result.returncode:
                print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
                result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        print(json.dumps(reports[variant]), flush=True)

c, k = reports['control'], reports['candidate']
F = 0x104  # Other | FAIL_ON_PIPELINE_COMPILE_REQUIRED
for name in ('hit', 'computeHit'):
    check(c[name]['compiles'] == 1 and c[name]['calls'] == '2:4:7', 'control compiles again what the main cache holds: ' + name)
    check(k[name]['compiles'] == 0 and k[name]['result'] == 'Success' and k[name]['calls'] == f'1:{F}:7' and k[name]['flagsRestored'] and
          k[name]['lockFreeAfter'], 'candidate finds it in the main cache: ' + name)
check(k['miss']['compiles'] == 1 and k['miss']['calls'] == f'1:{F}:8 2:4:8' and k['miss']['flagsRestored'], 'a miss compiles once in the worker cache')
check(c['miss']['calls'] == '2:4:8', 'control: worker cache only')
check(k['lockBusy']['calls'] == '2:4:7' and k['lockBusy']['compiles'] == 1 and k['lockBusy']['blocking'] == 0, 'a busy main lock is not waited for')
check(k['checkpoint']['calls'] == f'3:{F}:7 2:4:7', 'during a checkpoint the side cache is tried, then the worker cache')
check(k['noCacheControl']['calls'] == '2:4:7', 'without cache control the worker branch is unchanged')
check(all(r['blocking'] == 0 for r in k.values() if isinstance(r, dict)), 'the worker never takes the blocking path')
check(k['computeHit']['lines'] >= 1, 'the first hit is logged')
check(texts['control'].count('CreateGraphicsPipelines(') + 1 == texts['candidate'].count('CreateGraphicsPipelines(') and
      texts['control'].count('CreateComputePipelines(') + 1 == texts['candidate'].count('CreateComputePipelines('), 'one main attempt added per kind')

inputs = ['build-utils/melonx/adapt_worker_main_cache_lookup.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_worker_main_cache_lookup_test.py', 'test/melonx_worker_main_cache_lookup/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core691Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in adapter.BASELINE} if FINAL_PREPARATION else {},
               reports=reports, sdk=sdk, physicalDeviceTested=False, productionVulkanAssemblyBuilt=True, sourceBaseline=adapter.BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Doubles of MoltenVK pipeline caches; the count of pipelines compiled again per session is known only after a device run.')
out = ROOT / 'dist/melonx/worker-main-cache-lookup-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))

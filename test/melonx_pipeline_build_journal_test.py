#!/usr/bin/env python3
"""adapt_pipeline_build_journal on the final preparation, against the Core 683 postimage as control.

Diagnostics only: pipelines compiled (50 ms or more) are journaled per title with a key stable across sessions, so a
later session tells a pipeline compiled again (lost by an earlier session) from a new one. Control: the final
preparation with the adapter reversed (melonx_adapter_control), which must be the Core 683 bytes. Executed
(test/melonx_pipeline_build_journal with test/melonx_main_cache_checkpoint/Double.cs) on the variant's real
PipelineCacheManager.cs; PipelineState.cs and ShaderCollection.cs are checked in source.
Writes dist/melonx/pipeline-build-journal-checks.json.
"""
from pathlib import Path
import hashlib, json, os, platform, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
import melonx_adapter_control as control_tools  # noqa: E402
import adapt_pipeline_build_journal as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
MANAGER, STATE = VULKAN + 'PipelineCacheManager.cs', VULKAN + 'PipelineState.cs'
HARNESS = ROOT / 'test/melonx_pipeline_build_journal'
DOUBLE = ROOT / 'test/melonx_main_cache_checkpoint/Double.cs'
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(tree, name):
    return (tree / name).read_text(encoding='utf-8-sig')


def member(text, signature):
    start = text.rindex('\n', 0, text.index(signature)) + 1
    depth, index = 0, text.index('{', start)
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


temporary = tempfile.TemporaryDirectory(prefix='melonx-pipeline-build-journal-')
WORK = Path(temporary.name).resolve()  # resolved: on macOS /var is a link to /private/var
# The adapter's postimage: later adapters sharing its files (adapt_pipeline_cache_growth, Core 687) reversed first; the
# receipt binds the final preparation, which re-applying them forward must give back.
PREPARED = FINAL_SOURCE
POST = WORK / 'post'
LATER = control_tools.postimage('adapt_pipeline_build_journal', FINAL_SOURCE, POST)
replay = WORK / 'replay'
shutil.copytree(POST, replay)
for later in LATER:
    __import__(later).apply(replay)
for name in adapter.BASELINE:
    check((replay / name).read_bytes() == (PREPARED / name).read_bytes(), 'the later adapters reproduce the final preparation: ' + name)
shutil.copyfile(PREPARED / (VULKAN + 'VulkanException.cs'), WORK / 'VulkanException.cs')
FINAL_SOURCE = POST
CONTROL = WORK / 'control'
for name in adapter.BASELINE:
    (CONTROL / name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FINAL_SOURCE / name, CONTROL / name)

# --- Control: the adapter reversed must be the Core 671 bytes; forward reproduces the final preparation ---
control_tools._reverse('adapt_pipeline_build_journal', CONTROL)
for name, expected in adapter.BASELINE.items():
    check(sha(CONTROL / name) == expected, 'control is the Core 683 postimage: ' + name)
forward = WORK / 'forward'
for name in adapter.BASELINE:
    (forward / name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CONTROL / name, forward / name)
changed = sorted(str(p.relative_to(forward)) for p in adapter.apply(forward))
check(changed == sorted(adapter.BASELINE), 'the adapter changes only its files')
for name in adapter.BASELINE:
    check((forward / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)

# --- Static: the exact scope ---
STATE, PROGRAM = adapter.STATE, adapter.PROGRAM
manager = read(FINAL_SOURCE, MANAGER)
restored = manager
for old, new in ((adapter.MANAGER_FIELDS_OLD, adapter.MANAGER_FIELDS_NEW), (adapter.MANAGER_STARTUP_OLD, adapter.MANAGER_STARTUP_NEW),
                 (adapter.MANAGER_METHODS_ANCHOR, adapter.MANAGER_METHODS_NEW), (adapter.MANAGER_PAUSE_OLD, adapter.MANAGER_PAUSE_NEW)):
    restored = restored.replace(new, old)
check(restored == read(CONTROL, MANAGER), 'PipelineCacheManager.cs differs only by the four replacements')
state = read(FINAL_SOURCE, STATE)
check(state.replace(adapter.STATE_START_NEW, adapter.STATE_START_OLD).replace(adapter.STATE_END_NEW, adapter.STATE_END_OLD)
      == read(CONTROL, STATE), 'PipelineState.cs differs only by the timing and the note')
program = read(FINAL_SOURCE, PROGRAM)
check(program.replace(adapter.PROGRAM_FIELD_NEW, adapter.PROGRAM_FIELD_OLD).replace(adapter.PROGRAM_CTOR_NEW, adapter.PROGRAM_CTOR_OLD)
      == read(CONTROL, PROGRAM), 'ShaderCollection.cs differs only by StableHash')
create = member(state, 'public unsafe Auto<DisposablePipeline> CreateGraphicsPipeline(')
check(create.index('long buildStart') < create.index('CreateGraphicsPipelines') < create.index('NotePipelineBuild(') <
      create.index('return program.AddGraphicsPipeline(ref Internal, pipeline);'), 'the note follows the creation and precedes the return')
check('if (buildMs >= PipelineCacheManager.CompiledBuildMs)' in create, 'only compilations (50 ms or more) are noted')
key = member(state, 'private ulong PipelineBuildKey(ShaderCollection program)')
check('Internal.LogicOpsAllowed' in key and 'program.StableHash' in key, 'the key covers the program and the whole pipeline state')
check('StableHash = ComputeStableHash(shaders);' in program and 'shader.BinaryCode' in program, 'the program hash covers its stage code')

# --- Executed: control and candidate fixtures ---
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
reports = {}
for variant in ('control', 'candidate'):
    tree = CONTROL if variant == 'control' else FINAL_SOURCE
    fixture = WORK / ('fixture-' + variant)
    fixture.mkdir()
    shutil.copyfile(tree / MANAGER, fixture / 'PipelineCacheManager.cs')
    shutil.copyfile(WORK / 'VulkanException.cs', fixture / 'VulkanException.cs')
    shutil.copyfile(DOUBLE, fixture / 'Double.cs')
    shutil.copyfile(HARNESS / 'Program.cs', fixture / 'Program.cs')
    constants = '<DefineConstants>$(DefineConstants);CANDIDATE</DefineConstants>' if variant == 'candidate' else ''
    (fixture / 'Fixture.csproj').write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
        '<Nullable>disable</Nullable><AllowUnsafeBlocks>true</AllowUnsafeBlocks><NuGetAudit>false</NuGetAudit>' + constants +
        '<NoWarn>CS0649;CS0414;CS0169;CS8321;CS0162;CS1998;CS8632</NoWarn></PropertyGroup></Project>\n')
    build = subprocess.run([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                           capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
    if build.returncode:
        print('\n'.join(line for line in build.stdout.splitlines() if ': error ' in line)[:6000], flush=True)
    check(build.returncode == 0, variant + ' fixture builds with the real PipelineCacheManager.cs')
    run = subprocess.run([DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), variant],
                         capture_output=True, text=True, timeout=600, env=environment, cwd=fixture)
    if run.returncode:
        print(run.stdout[-4000:], run.stderr[-4000:], flush=True)
    check(run.returncode == 0, variant + ' fixture runs')
    reports[variant] = json.loads(run.stdout.strip().splitlines()[-1])
    print(variant + ': ' + json.dumps(reports[variant]), flush=True)

c, k = reports['control'], reports['candidate']
check(c['journalFile'] is False, 'control (Core 683): no build journal')
check(k['session1Start'] is not None and '0 pipelines compiled in 0 earlier sessions' in k['session1Start'], 'first session: an empty journal')
s1 = k['session1Summary']
check('render thread 3 in 2200 ms, of which compiled again 0 in 0 ms; workers 1 in 120 ms' in s1 and
      'Session: render thread 3 in 2200 ms, compiled again 0 in 0 ms' in s1, 'session 1 counts: %s' % s1)
check(k['journalBytesAfterSession1'] == 36, 'each key journaled once (A, B, C: 3 records of 12 bytes)')
check('3 pipelines compiled in 1 earlier sessions' in k['session2Start'], 'session 2 loads the earlier keys: %s' % k['session2Start'])
s2 = k['session2Pause']
check('render thread 2 in 1450 ms, of which compiled again 1 in 650 ms; workers 1 in 100 ms, of which compiled again 1 in 100 ms' in s2,
      'session 2: A and C are compiled again, D is new: %s' % s2)
check(k['journalBytesAfterSession2'] == 48, 'only the new key D is appended')
check('4 pipelines compiled in 2 earlier sessions' in k['tornTailStart'], 'a torn tail is ignored: %s' % k['tornTailStart'])
check(c['errors'] == 0 and k['errors'] == 0 and k['warnings'] == 0, 'no warning or error line')

inputs = ['build-utils/melonx/adapt_pipeline_build_journal.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_pipeline_build_journal_test.py',
          'test/melonx_main_cache_checkpoint/Double.cs', 'test/melonx_pipeline_build_journal/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=True, sourceKind='finalPreparationWithReversedControl',
               postimages={n: sha(PREPARED / n) for n in adapter.BASELINE},
               testedPostimages={n: sha(FINAL_SOURCE / n) for n in adapter.BASELINE}, reports=reports, sdk=sdk, host=platform.system(),
               physicalDeviceTested=False, gameTested=False, inputs={n: sha(ROOT / n) for n in inputs},
               limitation='Host fixture of the real cache manager with a Vulkan double. That the key is the same for the same pipeline '
                          'in two sessions on the device is shown only by a device run (a second session counting compiled-again pipelines).')
out = ROOT / 'dist/melonx/pipeline-build-journal-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))

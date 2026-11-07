#!/usr/bin/env python3
"""adapt_pipeline_cache_growth on the final preparation, against the Core 685 postimage as control.

The main pipeline cache file is rewritten whole by each checkpoint; the candidate writes it during play only for 8 MiB of
new content (or any 10 min after the last write) and on pause only for new content, and records each decision, write and
recycle in the engine journal. Compute compilations join the build journal. Control: the final preparation with the
adapter reversed (melonx_adapter_control), which must be the Core 685 bytes. Executed (test/melonx_pipeline_cache_growth
with test/melonx_main_cache_checkpoint/Double.cs) on the variant's real PipelineCacheManager.cs; PipelineState.cs is
checked in source. Writes dist/melonx/pipeline-cache-growth-checks.json.
"""
from pathlib import Path
import hashlib, json, os, platform, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
import melonx_adapter_control as control_tools  # noqa: E402
import adapt_pipeline_cache_growth as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
MANAGER, STATE = adapter.MANAGER, adapter.STATE
HARNESS = ROOT / 'test/melonx_pipeline_cache_growth'
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


temporary = tempfile.TemporaryDirectory(prefix='melonx-pipeline-cache-growth-')
WORK = Path(temporary.name).resolve()  # resolved: on macOS /var is a link to /private/var
# The adapter's postimage: later adapters sharing its files reversed first; the receipt binds the final preparation,
# which re-applying them forward must give back.
PREPARED = FINAL_SOURCE
POST = WORK / 'post'
LATER = control_tools.postimage('adapt_pipeline_cache_growth', FINAL_SOURCE, POST)
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

# --- Control: the adapter reversed must be the Core 685 bytes; forward reproduces the final preparation ---
control_tools._reverse('adapt_pipeline_cache_growth', CONTROL)
for name, expected in adapter.BASELINE.items():
    check(sha(CONTROL / name) == expected, 'control is the Core 685 postimage: ' + name)
forward = WORK / 'forward'
for name in adapter.BASELINE:
    (forward / name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CONTROL / name, forward / name)
changed = sorted(str(p.relative_to(forward)) for p in adapter.apply(forward))
check(changed == sorted(adapter.BASELINE), 'the adapter changes only its files')
for name in adapter.BASELINE:
    check((forward / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)

# --- Static: the exact scope ---
manager = read(FINAL_SOURCE, MANAGER)
restored = manager
for old, new in ((adapter.FIELDS_OLD, adapter.FIELDS_NEW), (adapter.STARTUP_OLD, adapter.STARTUP_NEW),
                 (adapter.PLAY_OLD, adapter.PLAY_NEW), (adapter.PAUSE_OLD, adapter.PAUSE_NEW),
                 (adapter.DECISION_ANCHOR, adapter.DECISION_NEW), (adapter.JOURNAL_LOAD_OLD, adapter.JOURNAL_LOAD_NEW),
                 (adapter.SUMMARY_OLD, adapter.SUMMARY_NEW), (adapter.PAUSE_SUMMARY_OLD, adapter.PAUSE_SUMMARY_NEW),
                 (adapter.SAVE_START_OLD, adapter.SAVE_START_NEW), (adapter.SAVE_DONE_OLD, adapter.SAVE_DONE_NEW),
                 (adapter.RECYCLE_OLD, adapter.RECYCLE_NEW)):
    restored = restored.replace(new, old)
check(restored == read(CONTROL, MANAGER), 'PipelineCacheManager.cs differs only by the eleven replacements')
state = read(FINAL_SOURCE, STATE)
check(state.replace(adapter.COMPUTE_START_NEW, adapter.COMPUTE_START_OLD).replace(adapter.COMPUTE_END_NEW, adapter.COMPUTE_END_OLD)
      == read(CONTROL, STATE), 'PipelineState.cs differs only by the compute timing and note')
create = member(state, 'public unsafe Auto<DisposablePipeline> CreateComputePipeline(')
check(create.index('long buildStart') < create.index('CreateComputePipelines') < create.index('NotePipelineBuild(ComputeBuildKey(program)') <
      create.index('return program.AddComputePipeline(ref SpecializationData, pipeline);'), 'the compute note follows the creation')
check('if (buildMs >= PipelineCacheManager.CompiledBuildMs)' in create, 'only compute compilations of 50 ms or more are noted')
key = member(state, 'private ulong ComputeBuildKey(ShaderCollection program)')
check('SpecializationData.Span' in key and 'program.StableHash' in key and '0xC0FFEE0DDBA11C0DUL' in key,
      'the compute key covers the program and its specialization, apart from graphics keys')
graphics = member(state, 'public unsafe Auto<DisposablePipeline> CreateGraphicsPipeline(')
check(graphics == member(read(CONTROL, STATE), 'public unsafe Auto<DisposablePipeline> CreateGraphicsPipeline('), 'graphics creation unchanged')
play = member(manager, 'private void CheckpointMainIfDue()')
check(play.index('MainGrowthWorthWriting(size, now, pause: false)') < play.index('SaveCache(main, size, final: false);'),
      'the play-time write follows the growth decision')
pause = member(manager, 'public void CheckpointMainOnPause()')
check(pause.index('MainGrowthWorthWriting(size, now, pause: true)') < pause.index('SaveCache(main, size, final: false);'),
      'the pause write follows the growth decision')
dispose = member(manager, 'private unsafe void DisposeLocked()')
check('MainGrowthWorthWriting' not in dispose, 'the close save is unchanged')

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
# Control (Core 685): every due checkpoint rewrites the whole file, whatever it gained.
check(c['smallGrowth']['outcome'] == 'written' and c['smallGrowth']['mainFileMiB'] == 102, 'control rewrites the file for 2 MiB: %s' % c['smallGrowth'])
check(c['pause']['unchangedWrites'] == 1, 'control rewrites the file on pause with nothing new in it: %s' % c['pause'])
# Candidate.
check(k['smallGrowth']['outcome'] == 'skipped' and k['smallGrowth']['writes'] == 0 and k['smallGrowth']['mainFileMiB'] == 100,
      'candidate keeps the file for 2 MiB of new content: %s' % k['smallGrowth'])
check(k['largeGrowth']['outcome'] == 'written' and k['largeGrowth']['mainFileMiB'] == 109, 'candidate writes 9 MiB of new content: %s' % k['largeGrowth'])
check(k['staleGrowth']['outcome'] == 'written' and k['staleGrowth']['mainFileMiB'] == 110,
      'candidate writes any new content 10 min after the last write: %s' % k['staleGrowth'])
check(c['largeGrowth']['mainFileMiB'] == k['largeGrowth']['mainFileMiB'] and c['staleGrowth']['mainFileMiB'] == k['staleGrowth']['mainFileMiB'],
      'the same content reaches the file in both variants once it is written')
play = k['playRecords']
check(sum(r.startswith('pipelineCache checkpointSkipped play: main 102.00 MiB, +2.00 MiB') for r in play) == 1, 'skip recorded: %s' % play)
check(sum(r.startswith('pipelineCache checkpoint play: main 109.00 MiB, +9.00 MiB') for r in play) == 1, 'write decision recorded: %s' % play)
check(sum(r.startswith('pipelineCache written main 109.00 MiB in ') for r in play) == 1 and
      sum(r.startswith('pipelineCache written main 110.00 MiB in ') for r in play) == 1, 'each write recorded with its time: %s' % play)
check(k['pause']['firstWrites'] == 1 and k['pause']['firstMiB'] == 50.19, 'pause with new content writes it: %s' % k['pause'])
check(k['pause']['unchangedWrites'] == 0 and any(r.startswith('pipelineCache checkpointSkipped pause: main 50.19 MiB, +0.00 KiB')
                                                 for r in k['pause']['records']), 'pause with nothing new does not rewrite: %s' % k['pause'])
check(c['worker']['recycledInfo'] and k['worker']['recycledInfo'], 'a worker over its budget is recycled in both variants')
check(any(r.startswith('pipelineCache recycled worker0 at') or r.startswith('pipelineCache recycled worker 0 at') for r in k['worker']['records'])
      and any(r.startswith('pipelineBuilds summary Pipeline compilations (last minute): render thread 1 in 300 ms') for r in k['worker']['records']),
      'recycle and build summary reach the engine journal: %s' % k['worker']['records'])
check(any(r.startswith('pipelineBuilds journal 0 pipelines compiled in 0 earlier sessions') for r in k['startRecords']), 'journal start recorded')
check(any(r.startswith('pipelineCache saved main ') for r in k['closeRecords']), 'the close save is recorded: %s' % k['closeRecords'])
check(not c['startRecords'] and not c['playRecords'], 'control records nothing of this')
check(c['errors'] == 0 and k['errors'] == 0 and k['warnings'] == 0 and c['warnings'] == 0, 'no warning or error line')

inputs = ['build-utils/melonx/adapt_pipeline_cache_growth.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_pipeline_cache_growth_test.py',
          'test/melonx_main_cache_checkpoint/Double.cs', 'test/melonx_pipeline_cache_growth/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=True, sourceKind='finalPreparationWithReversedControl',
               postimages={n: sha(PREPARED / n) for n in adapter.BASELINE},
               testedPostimages={n: sha(FINAL_SOURCE / n) for n in adapter.BASELINE}, reports=reports, sdk=sdk, host=platform.system(),
               physicalDeviceTested=False, gameTested=False, inputs={n: sha(ROOT / n) for n in inputs},
               limitation='Host fixture of the real cache manager with a Vulkan double (a cache is a byte count). The write time, '
                          'the memory and the frame-time effect on an iPhone are shown only by a device run.')
out = ROOT / 'dist/melonx/pipeline-cache-growth-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))

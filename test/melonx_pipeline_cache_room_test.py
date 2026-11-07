#!/usr/bin/env python3
"""adapt_pipeline_cache_room on the final preparation, against the Core 679 postimage as control.

The worker pipeline cache snapshots join main at startup (workers start empty), the main budget is 1 GiB, and a worker
does not overwrite its snapshot file before main has been written with the merged content. Control: the final
preparation with the adapter reversed (melonx_adapter_control), which must be the Core 679 bytes. Executed
(test/melonx_pipeline_cache_room with test/melonx_main_cache_checkpoint/Double.cs) for control and candidate on the
variant's real PipelineCacheManager.cs. Writes dist/melonx/pipeline-cache-room-checks.json.
"""
from pathlib import Path
import hashlib, json, os, platform, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
import melonx_adapter_control as control_tools  # noqa: E402
import adapt_pipeline_cache_room as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
MANAGER, STATE = VULKAN + 'PipelineCacheManager.cs', VULKAN + 'PipelineState.cs'
HARNESS = ROOT / 'test/melonx_pipeline_cache_room'
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


temporary = tempfile.TemporaryDirectory(prefix='melonx-pipeline-cache-room-')
WORK = Path(temporary.name).resolve()  # resolved: on macOS /var is a link to /private/var
# The adapter's postimage: later adapters sharing its file (adapt_pipeline_cache_persist, Core 683) reversed first; the
# receipt binds the final preparation, which re-applying them forward must give back.
PREPARED = FINAL_SOURCE
POST = WORK / 'post'
LATER = control_tools.postimage('adapt_pipeline_cache_room', FINAL_SOURCE, POST)
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
control_tools._reverse('adapt_pipeline_cache_room', CONTROL)
for name, expected in adapter.BASELINE.items():
    check(sha(CONTROL / name) == expected, 'control is the Core 679 postimage: ' + name)
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
control = read(CONTROL, MANAGER)
restored = manager
for old, new in ((adapter.BUDGET_OLD, adapter.BUDGET_NEW), (adapter.FIELD_OLD, adapter.FIELD_NEW),
                 (adapter.STARTUP_OLD, adapter.STARTUP_NEW), (adapter.SAVE_OLD, adapter.SAVE_NEW)):
    restored = restored.replace(new, old)
check(restored == control, 'PipelineCacheManager.cs differs only by the four replacements')
check(list(adapter.BASELINE) == [MANAGER], 'the adapter edits only PipelineCacheManager.cs')
check(manager.index('Recycle(worker, workerSize);') < manager.index('Vulkan pipeline cache initialized:'),
      'the startup merge runs in the constructor, before the cache is reported ready')

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
cs, ks = c['startup'], k['startup']
check(cs['mainMiB'] == 580 and cs['worker0MiB'] == 120 and cs['worker1MiB'] == 100 and cs['mergedLine'] is None,
      'control (Core 679): both worker snapshots stay loaded beside main: %s' % cs)
check(ks['worker0MiB'] < 0.01 and ks['worker1MiB'] < 0.01 and ks['mainMiB'] > 799 and
      ks['mergedLine'].startswith('Merged 2 Vulkan worker pipeline cache snapshots'),
      'candidate: both worker snapshots join main and the workers start empty: %s' % ks)
check('Budget 768,00 MiB main' in cs['budgetLine'] or 'Budget 768.00 MiB main' in cs['budgetLine'], 'control budget 768 MiB')
check(('Budget 1,00 GiB main' in ks['budgetLine'] or 'Budget 1.00 GiB main' in ks['budgetLine'] or '1024' in ks['budgetLine'])
      and '128' in ks['budgetLine'], 'candidate budget: 1 GiB main, 128 MiB per worker: %s' % ks['budgetLine'])
cl, kl = c['largeMain'], k['largeMain']
check(cl['ignored'] and cl['mainMiB'] < 0.01, 'control ignores a 900 MiB main snapshot')
check(not kl['ignored'] and kl['mainMiB'] == 900, 'candidate loads a 900 MiB main snapshot')
ch, kh = c['hold'], k['hold']
check(ch['workerAtStartMiB'] == 5 and ch['workerFileAfterDueSaveMiB'] == 6, 'control: worker 0 kept its snapshot and saves as before')
check(kh['workerAtStartMiB'] < 0.01 and kh['workerFileAfterDueSaveMiB'] == 5,
      'candidate: the merged worker snapshot is not overwritten before main holds it: %s' % kh)
check(kh['mainFileAfterCheckpointMiB'] >= 15, 'candidate: the next main checkpoint writes the merged content: %s' % kh)
check(kh['workerFileAfterMainSavedMiB'] < 5, 'candidate: once main holds it, the worker saves its new content again: %s' % kh)
check(c['noMainSnapshot'] == k['noMainSnapshot'] == {'worker0MiB': 5, 'merged': False},
      'with no main snapshot the worker keeps its snapshot in both variants')
check(c['errors'] == 0 and k['errors'] == 0, 'no error line')

inputs = ['build-utils/melonx/adapt_pipeline_cache_room.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_pipeline_cache_room_test.py',
          'test/melonx_main_cache_checkpoint/Double.cs', 'test/melonx_pipeline_cache_room/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=True, sourceKind='finalPreparationWithReversedControl',
               postimages={n: sha(PREPARED / n) for n in adapter.BASELINE},
               testedPostimages={n: sha(FINAL_SOURCE / n) for n in adapter.BASELINE}, reports=reports, sdk=sdk, host=platform.system(),
               physicalDeviceTested=False, gameTested=False, inputs={n: sha(ROOT / n) for n in inputs},
               limitation='Host fixture of the real cache manager with a Vulkan double whose merges add sizes. That MoltenVK '
                          'deduplicates the merged worker content (main grew 4.7 MiB after merges of about 130 MiB on IPA 674) '
                          'and the memory released on the device are known only from a device run.')
out = ROOT / 'dist/melonx/pipeline-cache-room-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))

#!/usr/bin/env python3
"""adapt_variant_replay_all on the final preparation, against the Core 723 preparation as control.

Usage: melonx_variant_replay_all_test.py <final preparation containing the adapter>
       (or --candidate-source <final preparation>)

IPA 724, Hogwarts Legacy (pid 49375): the replay of recorded pipeline states stopped at its session cap, "built 512 ...
still planned 843 of 1357", and the render thread created 701 of the states left behind ("late creations left 869
(4955 ms): new 160, planned not built yet 701"). The candidate makes the journal's own bound (MaxRecords) the cap.

Static: the control is the Core 723 preparation's PipelineCacheManager.cs; the candidate differs by the adapter's two
replacements only (the constant and the class comment); Pump (every scheduling decision) is the control's text byte
for byte; the other bounds are unchanged (2048 records, 2 MiB, 8 sessions, 120 s of compile time, two in flight, one
when costly, the hold at 8 % of device memory). Executed, on the production Ryujinx.Graphics.Vulkan of each side
(test/melonx_pipeline_variant_replay/Program.cs: real PipelineState codec, PipelineVariantJournal and
BackgroundCompilationScheduler, test-only InternalsVisibleTo):
- 600 planned states: control replays 512, candidate 600, each run once;
- IPA 724's list, 1357 planned states over 97 programs: control replays 512 (845 left), candidate all 1357, each run
  once, none failed, never more than two in flight;
- that list with the device's memory at 5 %: nothing starts on either side (the hold is counted);
- both sides: one in flight once replays are costly, nothing speculative while memory is short and a demanded replay
  still served (the scenarios of the Core 711 gate, unchanged).
No device, no Vulkan creation: a replay's cost is simulated (1 ms). Whether the 1357 states are built before the first
draw that needs them, the launch time and the memory on an iPhone are shown only by a device run.
Writes dist/melonx/variant-replay-all-checks.json.
"""
from pathlib import Path
import hashlib, json, os, platform, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
CONTROL, FINAL_PREPARATION = control_source(SOURCE, 'adapt_variant_replay_all', _HOLD)
import adapt_variant_replay_all as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
HARNESS = ROOT / 'test/melonx_pipeline_variant_replay'
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def member(text, signature):
    start = text.rindex('\n', 0, text.index(signature)) + 1
    depth, index = 0, text.index('{', start)
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')


def dotnet(*arguments, cwd, timeout=2400):
    result = subprocess.run([DOTNET, *arguments], capture_output=True, text=True, timeout=timeout, env=environment, cwd=cwd)
    if result.returncode:
        errors = [line for line in result.stdout.splitlines() if ': error ' in line]
        print('\n'.join(dict.fromkeys(errors[:40])), result.stdout[-3000:], result.stderr[-2000:], sep='\n', flush=True)
    return result


check(FINAL_PREPARATION, 'the source given is a final preparation containing adapt_variant_replay_all')
check(not files_edited_later('adapt_variant_replay_all'), 'no later adapter edits the file: the candidate is the final preparation')
temporary = tempfile.TemporaryDirectory(prefix='melonx-variant-replay-all-')
WORK = Path(temporary.name).resolve()

# --- Static: the control is the pinned Core 723 file; the candidate is the control plus the two replacements only ---
control_text = (CONTROL / adapter.MANAGER).read_text(encoding='utf-8-sig')
candidate_text = (FINAL_SOURCE / adapter.MANAGER).read_text(encoding='utf-8-sig')
check(sha(CONTROL / adapter.MANAGER) == adapter.BASELINE[adapter.MANAGER], 'control is the Core 723 preparation')
rebuilt = control_text
for old, new in adapter.PAIRS:
    check(rebuilt.count(old) == 1, 'one site for each replacement')
    rebuilt = rebuilt.replace(old, new)
check(rebuilt == candidate_text, 'the candidate is the control plus the adapter\'s replacements only')
check(len(adapter.PAIRS) == 2, 'two replacements: the class comment and the constant')
check(member(control_text, 'internal void Pump()') == member(candidate_text, 'internal void Pump()'), 'Pump is the control\'s text')
pump = member(candidate_text, 'internal void Pump()')
check('Replayed + ReplayFailed + _inFlight >= MaxReplaysPerSession' in pump and '_replayMs >= ReplayWorkBudgetMs' in pump and
      '_devicePercent() <= LowDevicePercent' in pump and '_inFlight >= limit' in pump, 'the cap, the compile budget, the memory hold and the in-flight limit are still tested')
journal = candidate_text[candidate_text.index('sealed class PipelineVariantJournal'):]
check('internal const int MaxReplaysPerSession = MaxRecords;' in journal and 'MaxReplaysPerSession = 512' not in candidate_text, 'the cap is the journal\'s bound')
check('internal const int MaxReplaysPerSession = 512;' in control_text, 'the control has the 512 cap')
for bound in ('MaxRecords = 2048', 'MaxFileBytes = 2L * 1024 * 1024', 'RecentSessions = 8', 'ReplayWorkBudgetMs = 120_000', 'MaxInFlight = 2',
              'CostlyReplayMs = 300', 'LowDevicePercent = 8'):
    check(bound in journal and bound in control_text, 'bound unchanged: ' + bound)
check(candidate_text.count('MaxReplaysPerSession') == control_text.count('MaxReplaysPerSession') == 2, 'the cap is read in one place (Pump)')


# --- Executed: the production Vulkan assembly of each side, then the Core 711 probe on it ---
def run(side, source):
    work = WORK / side / 'tree'
    shutil.copytree(source, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    project = work / (VULKAN + 'Ryujinx.Graphics.Vulkan.csproj')
    project.write_text(project.read_text(encoding='utf-8-sig').replace(
        '</Project>', '  <ItemGroup><InternalsVisibleTo Include="MeloNXVariantProbe" /></ItemGroup>\n</Project>'))
    probe = WORK / side / 'probe'
    probe.mkdir()
    shutil.copyfile(HARNESS / 'Program.cs', probe / 'Program.cs')
    (probe / 'MeloNXVariantProbe.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable>
    <AllowUnsafeBlocks>true</AllowUnsafeBlocks><NoWarn>CA1416;CS8632</NoWarn><NuGetAudit>false</NuGetAudit>
    <ManagePackageVersionsCentrally>false</ManagePackageVersionsCentrally>
  </PropertyGroup>
  <ItemGroup>
    <ProjectReference Include="{work}/src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj" />
  </ItemGroup>
</Project>
''')
    for extra in ('global.json', 'nuget.config'):
        if (work / extra).exists():
            shutil.copyfile(work / extra, probe / extra)
    build = dotnet('build', str(probe / 'MeloNXVariantProbe.csproj'), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false', cwd=probe)
    check(build.returncode == 0, side + ': the probe builds against the production Vulkan assembly')
    result = subprocess.run([DOTNET, str(probe / 'bin/Release/net10.0/MeloNXVariantProbe.dll')], capture_output=True, text=True,
                            timeout=1200, env=environment, cwd=probe)
    if result.returncode or result.stderr.strip():
        print(result.stdout[-2000:], result.stderr[-3000:], flush=True)
    check(result.returncode == 0 and not result.stderr.strip(), side + ': the probe ran clean')
    return json.loads(result.stdout.strip().splitlines()[-1])


control, candidate = run('control', CONTROL), run('candidate', FINAL_SOURCE)
for side, report in (('control', control), ('candidate', candidate)):
    check(report['requireFailures'] == 0, side + ': the probe\'s own requirements hold')
    check(report['costly']['maxInFlightOnceCostly'] == 1, side + ': one in flight once replays are costly')
    check(report['memory']['executedWhileShort'] == 0 and report['memory']['holds'] > 0 and report['memory']['demandedServedWhileShort'],
          side + ': nothing speculative while memory is short; a demanded replay is served: %s' % report['memory'])
    everything = report['all']
    check(everything['planned'] == 1357 and everything['heldPlanned'] == 1357, side + ': IPA 724\'s list is planned: %s' % everything)
    check(everything['maxInFlight'] <= 2 and everything['mostExecutions'] == 1 and everything['failed'] == 0 and
          everything['executed'] == everything['distinct'] == everything['replayed'],
          side + ': each replay runs once, two at most in flight, none failed: %s' % everything)
    check(everything['heldExecuted'] == 0 and everything['heldReplayed'] == 0 and everything['holds'] > 0,
          side + ': with 5 %% of the device\'s memory nothing starts: %s' % everything)
check(control['cap'] == dict(planned=600, replayed=512, executed=512), 'control: 512 of 600 planned states: %s' % control['cap'])
check(candidate['cap'] == dict(planned=600, replayed=600, executed=600), 'candidate: all 600 planned states: %s' % candidate['cap'])
check(control['all']['replayed'] == 512, 'control: the replay of IPA 724\'s list stops at 512 (845 left): %s' % control['all'])
check(candidate['all']['replayed'] == 1357, 'candidate: all 1357 states of IPA 724\'s list are replayed: %s' % candidate['all'])

inputs = ['build-utils/melonx/adapt_variant_replay_all.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_variant_replay_all_test.py',
          'test/melonx_pipeline_variant_replay/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=True, sourceKind='finalPreparationWithReversedControl',
               productionVulkanAssemblyBuilt=True, postimages={adapter.MANAGER: sha(FINAL_SOURCE / adapter.MANAGER)},
               control=dict(cap=control['cap'], all=control['all']), candidate=dict(cap=candidate['cap'], all=candidate['all']),
               sdk=sdk, host=platform.system(), physicalDeviceTested=False, gameTested=False,
               inputs={name: sha(ROOT / name) for name in inputs},
               limitation='Host run of the production journal and scheduler; no Vulkan device, a replay creates nothing and costs a '
                          'simulated 1 ms. Whether every recorded state is built before the draw that needs it, the launch time and the '
                          'memory on an iPhone are shown only by a device run (journal: "pipelineVariants summary").')
out = ROOT / 'dist/melonx/variant-replay-all-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
